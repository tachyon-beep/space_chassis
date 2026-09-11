#!/usr/bin/env python3
"""The supervisor: what happens when a run of the duty ends badly.

A run ends for one of a handful of reasons, and the reason decides what the
next one should be given. That map is the whole of this process:

    0   the duty ended the run cleanly     -> resume the conversation, restart
    42  the duty ended it on purpose       -> keep the handoff, restart
    43  the run's own fault (bad code)     -> climb the ladder
    44  the environment is unusable        -> wait, then retry unchanged
    other/signal                           -> climb the ladder
    alive but making no progress           -> kill it, then climb the ladder

The ladder is the part that matters. Counted over a decaying window:

    1  resume                     restart as-is, conversation intact
    2  restore the floor          put back the seed copies of the runtime files
    3  restore the codebase       put back everything the image carries
    4  give up                    exit; the container's restart policy takes over

Two deliberate choices. First, memory survives every rung: the conversation,
the diary and the agent's home are never touched, because the difference
between "a bad edit cost one run" and "a bad edit cost everything learnt" is
the whole point of having a supervisor at all. Second, this process runs from
the read-only image and is not the file the agents edit; what they edit is
under /work, and the floor beneath it is /opt/agent.

It records what it does. Every decision is appended to
/telemetry/agents/<slug>/lifecycle.jsonl, which the fleet reads and cannot
write, and the whole work tree is mirrored to /telemetry/work every few
seconds so that "what did the code look like when it died" is answerable.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

SERVICES_DIR = Path(os.environ.get("SERVICES_DIR", "/opt/services"))
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))

from common import append_jsonl, env_int, iso, write_text_atomic  # noqa: E402

SEED_DIR = Path(os.environ.get("SEED_DIR", "/opt/agent"))
WORK_DIR = Path(os.environ.get("WORK_DIR", "/work"))
HOME_DIR = Path(os.environ.get("AGENT_HOME", "/home/agent"))
TELEMETRY_DIR = Path(os.environ.get("TELEMETRY_DIR", "/telemetry"))
SESSION_DIR = HOME_DIR / "session"

EXIT_OK = 0
EXIT_HANDOFF = 42
EXIT_DUTY_FAULT = 43
EXIT_ENVIRONMENT = 44

FAILURE_WINDOW = env_int("SUPERVISOR_FAILURE_WINDOW_SECONDS", 900)
LADDER_TIER_2 = env_int("SUPERVISOR_TIER2_FAILURES", 2)
LADDER_TIER_3 = env_int("SUPERVISOR_TIER3_FAILURES", 3)
LADDER_TIER_4 = env_int("SUPERVISOR_TIER4_FAILURES", 5)
ENVIRONMENT_PAUSE = env_int("SUPERVISOR_PAUSE_SECONDS", 60)
INACTIVITY_SECONDS = env_int("SUPERVISOR_INACTIVITY_SECONDS", 86400)
FLAP_COUNT = env_int("SUPERVISOR_FLAP_COUNT", 3)
FLAP_WINDOW = env_int("SUPERVISOR_FLAP_WINDOW_SECONDS", 120)
MIRROR_INTERVAL = env_int("TELEMETRY_INTERVAL_SECONDS", 5)
TERMINATE_GRACE = 10

# Two files, two owners, and the distinction is the whole design.
#
# The duty is the program the fleet becomes: it lives in the shared codebase,
# it is theirs, and they are free to replace it. The chassis is the runtime
# that loads the duty and frames a run: it lives in the image beside this
# process, under the same read-only mount, and no agent can reach it. A
# supervisor that ran the runtime out of the directory the runtime is supposed
# to be repairing would be repairing sand.
#
# Tier 2 restores the duty from the image's pristine copy; tier 3 restores the
# seed's codebase, which is where the fleet's own libraries and tools live.
DUTY_SEED = SEED_DIR / "duty.py"
CHASSIS = SERVICES_DIR / "chassis.py"
SESSION_FILES = ("conversation.json",)


def normalise_exit(code: int) -> int:
    """A run killed by a signal is a crash, and must not read as a clean exit.

    `Popen.poll()` reports a signalled child as a negative number, so a run
    that was killed outright would otherwise land in the same branch as one that
    ended on purpose -- and the flap guard, which is the only thing standing
    between a crash loop and a restart loop, would never fire.
    """
    return 128 + abs(code) if code < 0 else code


def log(message: str) -> None:
    print(f"{iso()} [supervisor] {message}", flush=True)


class Supervisor:
    def __init__(self) -> None:
        self.slug = os.environ.get("AGENT_SLUG", "agent")
        self.name = os.environ.get("AGENT_NAME", self.slug)
        self.entry = Path(os.environ.get("AGENT_ENTRY", str(WORK_DIR / "duty.py")))
        self.chassis = CHASSIS
        self.record_path = TELEMETRY_DIR / "agents" / self.slug / "lifecycle.jsonl"
        self.operations_path = TELEMETRY_DIR / "agents" / self.slug / "operations.jsonl"
        self.failures: list[float] = []
        self.clean_exits: list[float] = []
        self.child: subprocess.Popen | None = None
        self.tier = 0
        self.stopping = False
        self.record_failed = False

    # -- the record ---------------------------------------------------------
    def record(self, event: str, **fields) -> None:
        """Append one line to the record of what this supervisor did.

        A failure to write here is *not* contained and forgotten. The
        lifecycle record is the account of how an agent got where it is, and a
        silent failure would leave an operator with a working fleet and no
        history of it -- which looks exactly like an agent that has never
        restarted. So the first failure is reported once, loudly, and later ones
        are suppressed to keep the log readable.
        """
        try:
            append_jsonl(
                self.record_path,
                {"at": iso(), "event": event, "agent": self.slug, "name": self.name, **fields},
            )
        except OSError as error:
            if not self.record_failed:
                self.record_failed = True
                log(
                    f"cannot write the lifecycle record to {self.record_path}: {error}. "
                    "Every decision about this agent will be unrecorded. The usual "
                    "cause is a directory under volumes/telemetry that is not owned "
                    "by uid 1000; re-run scripts/prepare_host.sh."
                )

    def operations_size(self) -> int:
        with contextlib.suppress(OSError):
            return self.operations_path.stat().st_size if self.operations_path.exists() else 0
        return 0

    # -- running a child ----------------------------------------------------
    @property
    def duty_path(self) -> Path:
        """Where this agent's duty lives, which is not where the supervisor lives."""
        return Path(os.environ.get("AGENT_ENTRY", str(WORK_DIR / "duty.py")))

    def run_child(self) -> int:
        """Start one chassis and wait for it, watching for a wedged one.

        A child that is alive and doing nothing is the failure mode a
        timeout cannot see: it is not crashed, it is stuck. Progress is
        measured by the operations record growing, which the chassis writes
        whenever a tool runs or a turn completes.
        """
        self.child = subprocess.Popen(  # noqa: S603 -- argv is fixed
            [sys.executable, str(CHASSIS)],
            cwd=str(WORK_DIR),
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        last_size = self.operations_size()
        last_progress = time.time()
        while True:
            code = self.child.poll()
            if code is not None:
                return normalise_exit(code)
            if self.stopping:
                self.terminate()
                return self.child.wait()
            time.sleep(2)
            size = self.operations_size()
            if size != last_size:
                last_size, last_progress = size, time.time()
            elif INACTIVITY_SECONDS and time.time() - last_progress > INACTIVITY_SECONDS:
                self.record("inactivity", seconds=INACTIVITY_SECONDS)
                log(f"no progress for {INACTIVITY_SECONDS}s; terminating the run")
                self.terminate()
                return -1

    def terminate(self) -> None:
        if self.child is None or self.child.poll() is not None:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(os.getpgid(self.child.pid), signal.SIGTERM)
        for _ in range(TERMINATE_GRACE * 2):
            if self.child.poll() is not None:
                return
            time.sleep(0.5)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(os.getpgid(self.child.pid), signal.SIGKILL)

    # -- the ladder ---------------------------------------------------------
    def decide(self, code: int) -> tuple[str, int]:
        """Map an exit to an action and the tier it implies."""
        now = time.time()
        self.failures = [t for t in self.failures if now - t <= FAILURE_WINDOW]
        self.clean_exits = [t for t in self.clean_exits if now - t <= FLAP_WINDOW]

        if code == EXIT_HANDOFF:
            self.failures.clear()
            self.record("handoff", exit=code)
            return "resume", 0

        if code == EXIT_ENVIRONMENT:
            self.record("environment", exit=code, pause=ENVIRONMENT_PAUSE)
            return "pause", 0

        if code == EXIT_OK:
            self.clean_exits.append(now)
            if len(self.clean_exits) >= FLAP_COUNT:
                # Exiting cleanly three times in two minutes is not a clean
                # exit; it is a loop, and the conversation is the likeliest
                # thing driving it.
                self.clean_exits.clear()
                self.failures.append(now)
                tier = self.tier_for(len(self.failures))
                self.record("flap", exit=code, tier=tier, action="resume_without_session")
                return "resume_without_session", tier
            return "resume", 0

        self.failures.append(now)
        tier = self.tier_for(len(self.failures))
        self.record("failure", exit=code, tier=tier, recent=len(self.failures))
        if tier >= 4:
            return "give_up", tier
        if tier == 3:
            return "restore_codebase", tier
        if tier == 2:
            return "restore_floor", tier
        return "resume", tier

    @staticmethod
    def tier_for(count: int) -> int:
        if count >= LADDER_TIER_4:
            return 4
        if count >= LADDER_TIER_3:
            return 3
        if count >= LADDER_TIER_2:
            return 2
        return 1

    # -- repairs ------------------------------------------------------------
    def resume(self) -> None:
        return

    def resume_without_session(self) -> None:
        """Start fresh, keeping everything the agent wrote except the conversation.

        The conversation is moved rather than deleted: an agent that wants to
        know what the run that flapped was thinking can still read it.
        """
        stamps = HOME_DIR / "session" / "abandoned"
        stamps.mkdir(parents=True, exist_ok=True)
        for name in SESSION_FILES:
            source = SESSION_DIR / name
            if source.exists():
                target = stamps / f"{int(time.time())}-{name}"
                with contextlib.suppress(OSError):
                    shutil.move(str(source), str(target))

    def restore_floor(self) -> None:
        """Put the duty back from the image's pristine copy.

        This is the rung that answers "you broke what you are". It restores one
        file and touches nothing else: not the conversation, not the memory, not
        anything the fleet built for itself.
        """
        restored = []
        target = self.duty_path
        if DUTY_SEED.exists():
            with contextlib.suppress(OSError):
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(DUTY_SEED, target)
                restored.append(str(target))
        self.record("restore_floor", files=restored)

    def restore_codebase(self) -> None:
        """Put back everything the seed carries and the run may have broken.

        The seed is copied over the work tree file by file rather than by
        replacing the directory: a run's own scratch files, its build caches
        and anything it put in /work that the seed does not name are left
        alone. Memory, the diary and the home are not touched at any tier.
        """
        restored = 0
        for source in sorted(SEED_DIR.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(SEED_DIR)
            if relative.parts and relative.parts[0] == "home":
                continue  # the seed's home is only for a first boot
            if relative.name == "chassis.py":
                continue  # the runtime belongs to the image, not to the codebase
            target = WORK_DIR / relative
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                restored += 1
            except OSError:
                continue
        self.record("restore_codebase", files=restored)

    # -- the mirror ---------------------------------------------------------
    def mirror(self) -> None:
        """Snapshot the work tree where the operators can see it.

        Symlinks are copied as links and never followed, so a link out of the
        tree cannot lift a file into the mirror. The previous snapshot is kept
        as `work.previous`, because the interesting question is usually what
        the code looked like just before it broke.
        """
        target = TELEMETRY_DIR / "work"
        staging = TELEMETRY_DIR / "work.staging"
        previous = TELEMETRY_DIR / "work.previous"
        if not WORK_DIR.exists():
            return
        with contextlib.suppress(OSError):
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            shutil.copytree(
                WORK_DIR,
                staging,
                symlinks=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "target", ".cargo"),
                dirs_exist_ok=False,
            )
            if target.exists():
                if previous.exists():
                    shutil.rmtree(previous, ignore_errors=True)
                os.rename(target, previous)
            os.rename(staging, target)

    # -- the loop -----------------------------------------------------------
    def run(self) -> int:
        self.record("supervisor_start", entry=str(self.entry), seed=str(SEED_DIR))
        log(f"{self.slug} ({self.name}) supervising {self.entry}")
        last_mirror = 0.0
        while not self.stopping:
            if time.time() - last_mirror > MIRROR_INTERVAL:
                self.mirror()
                last_mirror = time.time()
            started = time.time()
            code = self.run_child()
            action, tier = self.decide(code)
            self.tier = tier
            self.record(
                "decision",
                exit=code,
                action=action,
                tier=tier,
                seconds=round(time.time() - started, 1),
            )
            log(f"run exited {code} after {int(time.time() - started)}s -> {action} (tier {tier})")

            if action == "pause":
                self.mirror()
                time.sleep(ENVIRONMENT_PAUSE)
                continue
            if action == "resume_without_session":
                self.resume_without_session()
                continue
            if action == "restore_floor":
                self.restore_floor()
                continue
            if action == "restore_codebase":
                self.restore_codebase()
                last_mirror = 0.0
                continue
            if action == "give_up":
                self.mirror()
                self.record("give_up", tier=tier)
                log("the ladder is exhausted; exiting for the container to decide")
                return 1
            time.sleep(1)
        return 0


def main() -> int:
    supervisor = Supervisor()

    def stop(_signum, _frame):
        supervisor.stopping = True
        supervisor.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with contextlib.suppress(OSError):
        write_text_atomic(
            TELEMETRY_DIR / "agents" / supervisor.slug / "supervisor.pid",
            f"{os.getpid()}\n{iso()}\n",
        )
    return supervisor.run()


if __name__ == "__main__":
    sys.exit(main())
