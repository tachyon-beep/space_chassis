#!/usr/bin/env python3
"""Run the world locally, for as long as a scenario says, and see what survives.

This is the endurance harness. It builds a complete world in a directory --
codebase, per-agent homes, a diary, a window, a pump volume, a telemetry
volume, one recorder -- and runs the real operator-side services in it: the
recorder that holds the credential and writes the transcript, the supervisor
that decides what to do when a run dies, the pump that runs scheduled work.
Nothing here is a mock except the model, and the model is a metronome.

Then it does the thing that cannot be done to a live fleet with a real model:
it hurts them, on a schedule, for thousands of turns in a few minutes.

    crash          kill a run's process mid-flight
    bad_code       write a file that cannot be parsed over the duty entry
    unrecoverable  flood the model socket so a run faults out
    corrupt        replace a run's saved conversation with garbage

Every injury is one the world already has a place for, so the run is a test of
whether the ladder actually catches them -- tier by tier, with the memory
preserved -- rather than a test of whether the fleet is lucky.

What a passing run means, stated narrowly: the machinery around a fleet
survives being run hard. It says nothing about whether a real model would fly
the vehicle, and a scenario that claims otherwise is lying.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SERVICES = PROJECT_DIR / "services"
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "endurance"))
sys.path.insert(0, str(SERVICES))

from common import append_jsonl, iso  # noqa: E402
from report import build_report, write_report  # noqa: E402
from stub_model import Faults, Stub, StubServer, default_script, script_from_file  # noqa: E402

DEFAULT_SLUGS = [
    "agent_1",
    "agent_2",
    "agent_3",
    "agent_4",
    "agent_5",
    "agent_6",
    "agent_7",
    "agent_8",
    "agent_9",
    "agent_10",
]


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
@dataclass
class Scenario:
    name: str = "local"
    agents: int = 3
    timeout_seconds: float = 300.0
    turn_budget: int = 400
    script: Path | None = None
    time_scale: float = 1.0
    think_seconds: float = 0.0
    faults: dict = field(default_factory=dict)
    crashes: dict = field(default_factory=dict)
    run_max_turns: int | None = None
    ending_script: bool = False
    context_window: int = 200_000
    window_eviction: int | None = None
    recorder_hourly_max: int = 100_000
    expectations: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Scenario:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise SystemExit(f"{path}: a scenario is a json object")
        known = set(cls.__dataclass_fields__)
        unknown = set(raw) - known
        if unknown:
            raise SystemExit(f"{path}: unknown scenario keys: {', '.join(sorted(unknown))}")
        scenario = cls(**raw)
        scenario.script = Path(raw["script"]) if raw.get("script") else None
        if scenario.script and not scenario.script.is_absolute():
            scenario.script = Path(path).parent / scenario.script
        return scenario

    def fault_plan(self, seed: int) -> Faults:
        return Faults(seed=seed, **self.faults)


# ---------------------------------------------------------------------------
# The world on disk
# ---------------------------------------------------------------------------
class LocalWorld:
    def __init__(self, root: Path, scenario: Scenario, evidence: Path | None = None) -> None:
        self.root = Path(root)
        self.scenario = scenario
        self.slugs = DEFAULT_SLUGS[: scenario.agents]
        self.work = self.root / "work"
        self.home_root = self.root / "home"
        self.diary_root = self.root / "diary"
        self.transcripts = self.root / "transcripts"
        self.telemetry = self.root / "telemetry"
        self.diode = self.root / "diode"
        self.pump = self.root / "pump"
        self.sockets = self.root / "llm_sock"
        # Process logs land in the run directory rather than the scratch
        # world: they are the first thing anyone reads when a run fails, and
        # the scratch world is deliberately gone by then.
        self.logs = (Path(evidence) / "logs") if evidence else (self.root / "logs")
        for path in (
            self.work,
            self.home_root,
            self.diary_root,
            self.transcripts,
            self.telemetry,
            self.diode,
            self.pump,
            self.sockets,
            self.logs,
        ):
            path.mkdir(parents=True, exist_ok=True)
        self.seed()
        self.model = self.root / "model.sock"

    def seed(self) -> None:
        """Put the seed where the entrypoint would have put it."""
        # The codebase is the duty and its prompts. The runtime
        # (chassis.py) is deliberately *not* here: it runs from the service
        # directory in the image, out of the reach of the thing it supervises.
        for name in ("duty.py", "prompts.py"):
            source = PROJECT_DIR / "tasks" / name
            if source.exists():
                shutil.copy2(source, self.work / name)
        # A readable copy of the runtime, so a fleet can see how it is driven.
        # The supervisor runs the one in services/, never this one.
        shutil.copy2(PROJECT_DIR / "services" / "chassis.py", self.work / "chassis.py")
        brief = self.root / "brief"
        if (PROJECT_DIR / "brief").is_dir():
            shutil.copytree(PROJECT_DIR / "brief", brief, dirs_exist_ok=True)
        for slug in self.slugs:
            (self.home_root / slug / "session").mkdir(parents=True, exist_ok=True)
            (self.diary_root / slug).mkdir(parents=True, exist_ok=True)
            (self.diode / slug / "output").mkdir(parents=True, exist_ok=True)
            (self.pump / slug).mkdir(parents=True, exist_ok=True)
            (self.transcripts / slug).mkdir(parents=True, exist_ok=True)
            (self.telemetry / "agents" / slug).mkdir(parents=True, exist_ok=True)
            console = self.diode / slug / "console.json"
            if not console.exists():
                console.write_text(
                    json.dumps({"commands": [], "variables": {}}, indent=2) + "\n", encoding="utf-8"
                )
        (self.work / ".seeded").write_text(iso() + "\n", encoding="utf-8")

    def env_for(self, slug: str, model_url: str, socket_path: Path) -> dict:
        env = dict(os.environ)
        env.update(
            {
                "AGENT_SLUG": slug,
                "AGENT_NAME": slug,
                "WORK_DIR": str(self.work),
                "SEED_DIR": str(PROJECT_DIR / "tasks"),
                "AGENT_HOME": str(self.home_root / slug),
                "DIARY_DIR": str(self.diary_root / slug),
                "BRIEF_DIR": str(self.root / "brief"),
                "SERVICES_DIR": str(SERVICES),
                "TRANSCRIPTS_DIR": str(self.transcripts),
                "TELEMETRY_DIR": str(self.telemetry),
                "DIODE_DIR": str(self.diode),
                "DIODE_DUTY_DIR": str(self.diode / slug),
                "PUMP_DUTY_DIR": str(self.pump / slug),
                "LLM_BASE_URL": f"{model_url}/v1",
                "UPSTREAM_SOCKET": str(self.model),
                "LLM_API_KEY": "sk-stub",
                "LLM_SOCKET_PATH": str(socket_path),
                "LLM_MODEL": "stub",
                "CONTEXT_WINDOW_TOKENS": str(self.scenario.context_window),
                "SUPERVISOR_INACTIVITY_SECONDS": str(int(self.scenario.timeout_seconds * 2)),
                "TELEMETRY_INTERVAL_SECONDS": "2",
                "PUMP_MAX_ENTRIES": "16",
                "PUMP_MAX_CONCURRENT": "4",
            }
        )
        if self.scenario.window_eviction:
            env["CONTEXT_WINDOW_EVICTION_TOKENS"] = str(self.scenario.window_eviction)
        if self.scenario.run_max_turns:
            env["RUN_MAX_TURNS"] = str(self.scenario.run_max_turns)
        return env


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------
class Runner:
    def __init__(self, world: LocalWorld, destination: Path, seed: int = 1) -> None:
        self.world = world
        self.destination = destination
        self.seed = seed
        self.processes: dict[str, subprocess.Popen] = {}
        self.recorders: dict[str, subprocess.Popen] = {}
        self.stub: StubServer | None = None
        self.injector: threading.Thread | None = None
        self.stop = threading.Event()
        self.crashes: list[dict] = []
        self.started = time.time()

    # -- infrastructure -----------------------------------------------------
    def start_model(self) -> None:
        scenario = self.world.scenario
        script = script_from_file(scenario.script) if scenario.script else default_script()
        stub = Stub(
            script=script,
            faults=scenario.fault_plan(self.seed),
            time_scale=scenario.time_scale,
            think_seconds=scenario.think_seconds,
            journal=self.world.root / "stub-journal.jsonl",
            ending=scenario.ending_script,
        )
        self.stub = StubServer(stub, socket_path=self.world.model).start()

    def start_recorders(self) -> None:
        for slug in self.world.slugs:
            socket_path = self.world.sockets / f"{slug}.sock"
            env = self.world.env_for(slug, self.stub.url if self.stub else "", socket_path)
            env.update(
                {
                    "AGENT_SLUGS": slug,
                    "TRANSCRIPTS_DIR": str(self.world.transcripts),
                    "SOCKET_DIR": str(self.world.sockets),
                    "RECORDER_HOURLY_MAX": str(self.world.scenario.recorder_hourly_max),
                    "RECORDER_REFUSE_DIR": str(self.world.logs),
                    "RECORDER_TOKEN_HOURLY_MAX": "100000000",
                    "RECORDER_TOKEN_GLOBAL_HOURLY_MAX": "1000000000",
                }
            )
            self.recorders[slug] = spawn_logged(
                [sys.executable, str(SERVICES / "recorder.py")],
                env=env,
                log_path=self.world.logs / f"recorder-{slug}.log",
            )

    def wait_for_sockets(self, timeout: float = 30.0) -> None:
        deadline = time.time() + timeout
        for slug in self.world.slugs:
            path = self.world.sockets / f"{slug}.sock"
            while not path.exists():
                if time.time() > deadline:
                    raise SystemExit(f"the recorder never opened {path}")
                time.sleep(0.1)

    def start_agents(self) -> None:
        for slug in self.world.slugs:
            socket_path = self.world.sockets / f"{slug}.sock"
            env = self.world.env_for(slug, self.stub.url if self.stub else "", socket_path)
            self.processes[slug] = spawn_logged(
                [sys.executable, str(SERVICES / "supervisor.py")],
                env=env,
                log_path=self.world.logs / f"supervisor-{slug}.log",
                cwd=str(self.world.work),
            )

    # -- injury -------------------------------------------------------------
    def start_injector(self) -> None:
        plan = self.world.scenario.crashes
        if not plan:
            return
        self.injector = threading.Thread(target=self._inject_loop, args=(plan,), daemon=True)
        self.injector.start()

    def _inject_loop(self, plan: dict) -> None:
        """Hurt the fleet on the scenario's schedule, in a way it must survive.

        The injuries are chosen to be exactly the ones the world already claims
        to handle, so the run is a test of those claims rather than a random
        stress. Anything that is not recoverable by design would make the whole
        run meaningless, so nothing here deletes memory or the record.
        """
        script = Path(__file__).with_name("inject.py")
        kinds = list(plan.get("kinds", ["crash"]))
        every = float(plan.get("every_seconds", 20.0))
        while not self.stop.is_set():
            time.sleep(random_interval(every))
            if self.stop.is_set():
                break
            injury = pick(kinds, self.seed + len(self.crashes))
            slug = pick(self.world.slugs, self.seed + len(self.crashes) * 7)
            try:
                detail = run_injection(script, injury, self.world, slug)
            except Exception as error:  # noqa: BLE001 -- a broken injector must be visible
                detail = f"the injector failed: {type(error).__name__}: {error}"
                print(f"[harness] {detail}", flush=True)
            self.crashes.append({"at": iso(), "kind": injury, "agent": slug, "detail": detail})
            append_jsonl(
                self.destination / "faults.jsonl",
                {"at": iso(), "kind": injury, "agent": slug, "detail": detail},
            )

    # -- the run ------------------------------------------------------------
    def run(self) -> int:
        scenario = self.world.scenario
        print(
            f"[harness] {scenario.name}: {len(self.world.slugs)} agents, "
            f"budget {scenario.turn_budget} turns, timeout {scenario.timeout_seconds}s",
            flush=True,
        )
        self.start_model()
        self.start_recorders()
        self.wait_for_sockets()
        self.start_agents()
        self.start_injector()

        deadline = time.time() + scenario.timeout_seconds
        while time.time() < deadline:
            time.sleep(1.0)
            if self.turns_taken() >= scenario.turn_budget:
                print(
                    f"[harness] turn budget reached at {int(time.time() - self.started)}s",
                    flush=True,
                )
                break
            if all(process.poll() is not None for process in self.processes.values()):
                print("[harness] every agent has stopped", flush=True)
                break
        else:
            print("[harness] timeout", flush=True)

        self.shutdown()
        return 0

    def turns_taken(self) -> int:
        """Turns actually taken, counted from the recorder's own record.

        Counting the transcript rather than the model's journal is deliberate:
        the transcript is the number the fleet cannot influence, so a run that
        decides to trim its own history still shows up here.
        """
        total = 0
        for slug in self.world.slugs:
            path = self.world.transcripts / slug / "agent_life_transcript.jsonl"
            with (
                contextlib.suppress(OSError),
                open(path, encoding="utf-8", errors="ignore") as handle,
            ):
                total += sum(1 for line in handle if line.strip())
        return total

    def shutdown(self) -> None:
        self.stop.set()
        for process in list(self.processes.values()):
            terminate(process)
        for process in list(self.recorders.values()):
            terminate(process)
        if self.stub is not None:
            self.stub.stop()
        if self.crashes:
            append_jsonl(self.destination / "faults.jsonl", {"at": iso(), "faults": self.crashes})


def spawn_logged(argv: list[str], env: dict, log_path: Path, cwd: str | None = None):
    """Start a child whose output lands in a file that outlives this call.

    The handle is opened for the child and closed here, in the parent: passing
    an open file into `Popen` and then leaking it is how a harness ends up
    holding every agent's log open for the length of a run.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab") as log:
        return subprocess.Popen(  # noqa: S603 -- argv is fixed by the harness
            argv,
            env=env,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )


def random_interval(seconds: float) -> float:
    """Jitter around the scenario's interval so injuries do not land in step."""
    import random

    return max(1.0, random.uniform(seconds * 0.5, seconds * 1.5))


def pick(items: list, seed: int):
    import random

    return random.Random(seed).choice(items)


def run_injection(script: Path, injury: str, world: LocalWorld, slug: str) -> str:
    """Apply one injury, in a helper process so the harness stays simple."""
    try:
        finished = subprocess.run(
            [sys.executable, str(script), injury, str(world.root), slug],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return (finished.stdout or finished.stderr or "").strip()[:400]
    except subprocess.TimeoutExpired:
        return "the injection timed out"
    except OSError as error:
        return f"the injection could not run: {error}"


def terminate(process: subprocess.Popen, grace: float = 10.0) -> None:
    if process.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    deadline = time.time() + grace
    while time.time() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.2)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)


# ---------------------------------------------------------------------------
def snapshot_world(world: LocalWorld, destination: Path) -> None:
    """Keep the evidence, drop the bulk.

    Transcripts, lifecycle records, the pump state and the diaries are what a
    report is made of; the tree of files a fleet built is usually huge and
    rarely read. `--keep-world` keeps everything.
    """
    destination.mkdir(parents=True, exist_ok=True)
    for name, path in (
        ("transcripts", world.transcripts),
        ("telemetry", world.telemetry),
        ("pump", world.pump),
        ("diary", world.diary_root),
    ):
        if path.exists():
            shutil.copytree(path, destination / name, dirs_exist_ok=True, symlinks=True)
    with contextlib.suppress(OSError):
        shutil.copy2(world.root / "stub-journal.jsonl", destination / "stub-journal.jsonl")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("scenario", type=Path, help="a scenario json file")
    parser.add_argument("--out", type=Path, default=PROJECT_DIR / "endurance" / "runs")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--keep-world", action="store_true", help="keep the whole world, not just the record"
    )
    parser.add_argument("--tag", default="", help="a name for this run")
    args = parser.parse_args(argv)

    scenario = Scenario.load(args.scenario)
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    destination = args.out / f"{args.tag or scenario.name}-{stamp}"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    # The world is built outside the repository and under a short path, because
    # a unix socket's address is capped at about a hundred bytes and the
    # repository's own path is long enough to spend most of it. What matters
    # afterwards -- transcripts, lifecycle records, diaries -- is copied back
    # into the run directory, which is the part anyone reads.
    runtime_root = Path(tempfile.mkdtemp(prefix="sc-"))
    world_root = runtime_root / "w"

    try:
        world = LocalWorld(world_root, scenario, evidence=destination)
        shutil.copy2(args.scenario, destination / "scenario.json")
        runner = Runner(world, destination, seed=args.seed)
        try:
            runner.run()
        finally:
            runner.shutdown()
        snapshot_world(world, destination)
        report = build_report(destination, scenario, runner)
        write_report(destination, report)
        print(json.dumps(report["verdict"], indent=2))
        return 0 if report["verdict"]["passed"] else 1
    finally:
        if args.keep_world:
            print(f"[harness] world kept at {world_root}", flush=True)
        else:
            shutil.rmtree(runtime_root, ignore_errors=True)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        sys.exit(main())


# Re-exported so a test can build a world without running one.
__all__ = ["LocalWorld", "Runner", "Scenario", "snapshot_world"]
