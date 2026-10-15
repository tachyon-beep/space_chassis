"""The smoke stack: three agents, their recorders, a cued stub model and the fake diode.

Everything it makes lives under one scratch root in the repository (.smoke-<pid>/, gitignored and
outside the build context): plain data/ directories standing in for the bounded volume images
(creating real images needs root, which stays the operator's), a cue directory for the stub, an
env file, and a compose override. Nothing under the real volumes/, operator/ or .env is read or
written, and the project name is its own, so it can never touch a running space-chassis stack.

The model key is a dummy. Compose lets the shell's environment beat --env-file, so every docker
call here runs with an allowlisted environment: whatever the operator's shell exports, no key and
no upstream reaches the smoke recorders.

It builds and runs its own image tags, SMOKE_IMAGE and, with the vehicle as its window,
SMOKE_VEHICLE_IMAGE, so the operator's `space-chassis-agent` and `space-chassis-vehicle` are never
rebuilt from a working tree, and it puts back whatever console seed the operator's prepare_host.sh
left (the build needs one from .env.example). The scratch directories are plain host directories
the containers write as uid 1000, the image's agent: on a host whose user is another uid, the first
symptom is the 60-second wait for a cue that is never claimed.

start() prepares, builds and brings the stack up, and tears it down if any of that fails. down()
is idempotent and also registered with atexit, and it marks itself done only once compose has
returned, so a teardown interrupted by a second Ctrl-C is retried at exit. Every docker call has a
timeout, so a wedged daemon fails a test instead of hanging the suite.
"""

from __future__ import annotations

import atexit
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import volume_images  # noqa: E402

ALLOWED_VARIABLES = ("PATH", "HOME", "USER", "LANG", "XDG_RUNTIME_DIR")
SMOKE_IMAGE = "space-chassis-agent:smoke"
# The vehicle's own image (Dockerfile.agent's `vehicle` stage): the agents' carries nothing of it.
SMOKE_VEHICLE_IMAGE = "space-chassis-vehicle:smoke"
DECLARED_AGENTS = 10
CONSOLE_SEED = REPO / "llm_console_seed.json"
DOCKER_TIMEOUT_SECONDS = 120
BUILD_TIMEOUT_SECONDS = 3600
STUB_PORT = 8199
DUMMY_KEY = "sk-smoke-dummy"
# The window's two implementations: the contract fixture, or the vehicle itself.
WINDOWS = ("diode", "vehicle")
# The vehicle checkpoints every 50 ticks; at the operator's 5 s poll that is minutes per check.
VEHICLE_SMOKE_POLL = "0.2"
# A seed no window has any reason to contain, so live/test_vehicle.py can look for it in every file
# an agent can read: the world's identity belongs in the window root's .executive.json alone.
SMOKE_VEHICLE_SEED = "8675309"

# The live run's budget (Governance, 2026-10-11): one smoke stack at a time, inside 5 CPUs and
# 14 GiB in all, overhead included. What is enforced, each by the kernel:
# - every container the stack starts: `cpus`, and `mem_limit` with `memswap_limit` equal to it, so
#   nothing swaps past it (tmpfs pages are charged to the container too). The sum is STACK_CPUS and
#   STACK_MEMORY; tests/test_live_stack.py holds the rendered config to it, and live/conftest.py
#   reads every running container's cgroup back before a test runs;
# - the containment check's throwaway image sweep (scripts/verify_containment.sh), one at a time
#   beside the stack: SWEEP_CPUS and SWEEP_MEMORY;
# - pytest and the docker clients: the user scope the run must be inside (HOST_CPUS, HOST_MEMORY;
#   live/conftest.py refuses to start a stack outside one).
# What is left (BUDGET minus those) is a reserve for the docker daemon's own work, which no client
# can cap: it is not enforced. Agents keep the operator's 3g; their CPU is 0.75.
CAPS = {
    "agent": ("0.75", "3g"),
    "recorder": ("0.2", "512m"),
    "window": ("1.0", "512m"),
    "stub": ("0.2", "256m"),
    "fleet_monitor": ("0.1", "256m"),
    "review": ("0.25", "512m"),
}
STACK_CPUS = 4.4
STACK_MEMORY = 12 << 30
SWEEP_CPUS, SWEEP_MEMORY = "0.2", "256m"
HOST_CPUS = 0.35
HOST_MEMORY = 1 << 30
BUDGET_CPUS = 5.0
BUDGET_MEMORY = 14 << 30
HOST_SCOPE_COMMAND = "systemd-run --user --scope -p CPUQuota=35% -p MemoryMax=1G nice -n 19 python3 -m pytest live -q"
# One stack at a time: a lock every checkout and session of this user shares, held from start() to
# down(), and a refusal to start beside any smoke project already running on the daemon.
SMOKE_PROJECT_PREFIX = "space_chassis_smoke_"
SMOKE_LOCK = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "space_chassis_smoke.lock"
# Where docker's systemd cgroup driver puts a container: system.slice/docker-<id>.scope.
DOCKER_CGROUPS = Path("/sys/fs/cgroup/system.slice")


def memory_bytes(text: str) -> int:
    """A compose memory value as bytes: `512m`, `3g`."""
    return int(text[:-1]) << {"m": 20, "g": 30}[text[-1]]


def cgroup_limits(directory: Path) -> tuple[float, int, int | None]:
    """A cgroup v2 directory's CPUs, memory and swap limits; -1 where unlimited, None where absent."""

    def number(text: str) -> int:
        return -1 if text.strip() == "max" else int(text)

    quota, period = (directory / "cpu.max").read_text().split()
    cpus = -1.0 if quota == "max" else int(quota) / int(period)
    memory = number((directory / "memory.max").read_text())
    swap_file = directory / "memory.swap.max"
    swap = number(swap_file.read_text()) if swap_file.exists() else None
    return cpus, memory, swap


def own_cgroup() -> Path:
    """This process's cgroup v2 directory."""
    line = Path("/proc/self/cgroup").read_text().strip().splitlines()[0]
    return Path("/sys/fs/cgroup" + line.split("::", 1)[1])


def allowed_environment(extra: dict | None = None) -> dict:
    """The process environment docker runs with: an allowlist, never the operator's whole shell."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key in ALLOWED_VARIABLES or key.startswith("DOCKER_")
    }
    env.update(extra or {})
    return env


def _capped(kind: str) -> list[str]:
    """A service's caps, as override lines: its CPUs, and its memory with no swap past it."""
    cpus, memory = CAPS[kind]
    return [f'    cpus: "{cpus}"', f"    mem_limit: {memory}", f"    memswap_limit: {memory}"]


def wait_for(predicate, *, timeout: float, every: float = 1.0, what: str):
    """Poll predicate until it returns something truthy; raise naming what was awaited."""
    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value:
            return value
        if time.monotonic() >= deadline:
            raise TimeoutError(f"waited {timeout}s for {what}")
        time.sleep(every)


class SmokeStack:
    def __init__(
        self,
        agents: int = 3,
        recorder_overrides: dict[int, dict] | None = None,
        root: Path | None = None,
        runner=subprocess.run,
        window: str = "diode",
        lock: Path | None = None,
    ) -> None:
        if window not in WINDOWS:
            raise ValueError(f"window must be one of {WINDOWS}, not {window!r}")
        self.agents = agents
        self.recorder_overrides = recorder_overrides or {}
        self.window = window
        # A vehicle stack is its own project and scratch root; it never runs beside the fixture's.
        suffix = "" if window == "diode" else f"_{window}"
        self.project = f"{SMOKE_PROJECT_PREFIX}{os.getpid()}{suffix}"
        self.root = (
            Path(root)
            if root is not None
            else REPO / f".smoke-{os.getpid()}{suffix.replace('_', '-')}"
        )
        self._runner = runner
        self._torn_down = False
        self.lock = Path(lock) if lock is not None else SMOKE_LOCK
        self._lock_fd: int | None = None
        # Override files added after `up` by recreate(), kept on every later compose call.
        self.overrides: list[Path] = []
        atexit.register(self.down)

    @property
    def slugs(self) -> list[str]:
        return [f"agent_{n}" for n in range(1, self.agents + 1)]

    @property
    def volumes(self) -> Path:
        return self.root / "volumes"

    @property
    def cues(self) -> Path:
        return self.root / "cues"

    # ---------------------------------------------------------------- files

    def prepare(self) -> None:
        for name in volume_images.names(self.slugs):
            (self.volumes / name / "data").mkdir(parents=True, exist_ok=True)
        for slug in self.slugs:
            (self.volumes / "diode" / "data" / slug / "output").mkdir(parents=True, exist_ok=True)
        # The monitor and the review panel bind every agent the compose file declares, under its
        # default slug, and docker refuses a missing bind source: the absent agents' records are
        # empty directories.
        for n in range(self.agents + 1, DECLARED_AGENTS + 1):
            for kind in ("transcripts", "telemetry"):
                (self.volumes / f"{kind}_agent_{n}" / "data").mkdir(parents=True, exist_ok=True)
        self.cues.mkdir(parents=True, exist_ok=True)
        (self.root / "smoke.env").write_text(self.env_text(), encoding="utf-8")
        (self.root / "override.yml").write_text(self.override_text(), encoding="utf-8")

    def env_text(self) -> str:
        return "".join(
            f"{key}={value}\n"
            for key, value in (
                ("OPENROUTER_API_KEY", DUMMY_KEY),
                ("LLM_BASE_URL", f"http://stub:{STUB_PORT}/v1"),
                ("LLM_API_KEY", "sk-stub"),
                ("SPACE_VOLUMES_DIR", str(self.volumes)),
                ("FLEET_SLUGS", ",".join(self.slugs)),
            )
        )

    def override_text(self) -> str:
        lines = [
            "services:",
            "  stub:",
            f"    image: {SMOKE_IMAGE}",
            *_capped("stub"),
            '    entrypoint: ["python", "/opt/live/stub_llm.py"]',
            "    environment:",
            f'      VERIFY_STUB_PORT: "{STUB_PORT}"',
            "      STUB_CUE_DIR: /cues",
            '      VERIFY_STUB_DELAY_SECONDS: "2.0"',
            '      VERIFY_STUB_TURNS_PER_INCARNATION: "40"',
            "    volumes:",
            "      - ./live:/opt/live:ro",
            f"      - {self.cues}:/cues",
            "    networks: [modelnet]",
            "    read_only: true",
            "    cap_drop: [ALL]",
            '    security_opt: ["no-new-privileges:true"]',
        ]
        for n in range(1, self.agents + 1):
            lines += [f"  agent_{n}:", f"    image: {SMOKE_IMAGE}", *_capped("agent")]
            lines += [f"  recorder_{n}:", f"    image: {SMOKE_IMAGE}", "    depends_on: [stub]"]
            lines += _capped("recorder")
            overrides = self.recorder_overrides.get(n)
            if overrides:
                lines.append("    environment:")
                lines += [f'      {key}: "{value}"' for key, value in overrides.items()]
        if self.window == "diode":
            lines += [
                "  diode:",
                f"    image: {SMOKE_IMAGE}",
                *_capped("window"),
                '    entrypoint: ["python", "/opt/fake/fake_diode.py"]',
                "    environment:",
                f"      AGENT_SLUGS: {','.join(self.slugs)}",
                "    volumes:",
                "      - ./contract/fake_diode.py:/opt/fake/fake_diode.py:ro",
            ]
        else:
            # The vehicle serves VEHICLE_SLUGS, which compose fills from smoke.env's FLEET_SLUGS.
            lines += [
                "  vehicle:",
                f"    image: {SMOKE_VEHICLE_IMAGE}",
                *_capped("window"),
                "    environment:",
                f'      DIODE_POLL_SECONDS: "{VEHICLE_SMOKE_POLL}"',
                f'      VEHICLE_SEED: "{SMOKE_VEHICLE_SEED}"',
            ]
        lines += [
            "  fleet_monitor:",
            f"    image: {SMOKE_IMAGE}",
            *_capped("fleet_monitor"),
            "    environment:",
            f"      AGENT_SLUGS: {','.join(self.slugs)}",
            '      MONITOR_INTERVAL_SECONDS: "5"',
            '      QUIET_SECONDS: "20"',
            "  review:",
            f"    image: {SMOKE_IMAGE}",
            *_capped("review"),
            "    ports: !reset []",
            "    environment:",
            f"      AGENT_SLUGS: {','.join(self.slugs)}",
        ]
        return "\n".join(lines) + "\n"

    # ---------------------------------------------------------------- docker

    def compose_command(self, *args: str) -> list[str]:
        return [
            "docker",
            "compose",
            "-p",
            self.project,
            "--env-file",
            str(self.root / "smoke.env"),
            "-f",
            str(REPO / "docker-compose.yml"),
            "-f",
            str(self.root / "override.yml"),
            *[argument for path in self.overrides for argument in ("-f", str(path))],
            "--profile",
            "fleet",
            "--profile",
            self.window,
            *args,
        ]

    def run(
        self,
        argv: list[str],
        *,
        check: bool = True,
        stdin: str | None = None,
        timeout: float = DOCKER_TIMEOUT_SECONDS,
    ):
        return self._runner(
            argv,
            cwd=str(REPO),
            env=allowed_environment(),
            input=stdin,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
        )

    def compose(
        self,
        *args: str,
        check: bool = True,
        stdin: str | None = None,
        timeout: float = DOCKER_TIMEOUT_SECONDS,
    ):
        return self.run(self.compose_command(*args), check=check, stdin=stdin, timeout=timeout)

    def build(self) -> None:
        kept = CONSOLE_SEED.read_bytes() if CONSOLE_SEED.exists() else None
        try:
            self.run(
                [
                    sys.executable,
                    str(REPO / "scripts" / "build_console_seed.py"),
                    "--source",
                    ".env.example",
                ]
            )
            # The vehicle is in its own profile and image: built only by name, and only when it
            # serves. One build at a time (Governance, 2026-10-11): compose builds the services it
            # is given in parallel, so each is its own call.
            self.compose("build", "agent_1", timeout=BUILD_TIMEOUT_SECONDS)
            if self.window == "vehicle":
                self.compose("build", "vehicle", timeout=BUILD_TIMEOUT_SECONDS)
        finally:
            if kept is None:
                CONSOLE_SEED.unlink(missing_ok=True)
            else:
                CONSOLE_SEED.write_bytes(kept)

    def up(self) -> None:
        self.compose("up", "-d", *self.services())

    def recreate(self, service: str, environment: dict[str, str]) -> None:
        """Recreate one running service alone, with its environment changed and nothing else."""
        path = self.root / f"recreate-{service}.yml"
        lines = ["services:", f"  {service}:", "    environment:"]
        # JSON's string is a YAML double-quoted scalar; `$$` is compose's literal dollar.
        lines += [
            f"      {key}: {json.dumps(str(value).replace('$', '$$'))}"
            for key, value in environment.items()
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if path not in self.overrides:
            self.overrides.append(path)
        self.compose("up", "-d", "--force-recreate", "--no-deps", service)

    def others_running(self) -> list[str]:
        """Every other smoke project with a container up on this daemon."""
        label = "com.docker.compose.project"
        template = f'{{{{.Label "{label}"}}}}'
        result = self.run(["docker", "ps", "--filter", f"label={label}", "--format", template])
        running = {line.strip() for line in result.stdout.splitlines()}
        return sorted(
            p for p in running if p.startswith(SMOKE_PROJECT_PREFIX) and p != self.project
        )

    def services(self) -> list[str]:
        services = ["stub"]
        services += [f"recorder_{n}" for n in range(1, self.agents + 1)]
        services += [f"agent_{n}" for n in range(1, self.agents + 1)]
        return services + [self.window, "fleet_monitor", "review"]

    def enforced_caps(self) -> dict[str, tuple[float, int, int | None]]:
        """What the kernel enforces on each running service: its container's own cgroup (v2), read
        from the host side, so nothing inside the container is trusted or needs to answer."""
        caps = {}
        for service in self.services():
            short = self.container_id(service)
            assert short, f"{service} has no container"
            full = self.run(["docker", "inspect", "-f", "{{.Id}}", short]).stdout.strip()
            scope = DOCKER_CGROUPS / f"docker-{full}.scope"
            assert scope.is_dir(), f"{service}'s cgroup is not at {scope}"
            caps[service] = cgroup_limits(scope)
        return caps

    def _hold_the_lock(self) -> None:
        fd = os.open(self.lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise RuntimeError(f"one smoke stack at a time: another holds {self.lock}") from None
        self._lock_fd = fd

    def _release_the_lock(self) -> None:
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    def _refuse_beside_another(self) -> None:
        others = self.others_running()
        if others:
            raise RuntimeError(f"one smoke stack at a time: {', '.join(others)} is running")

    def start(self) -> None:
        self._hold_the_lock()
        try:
            self._refuse_beside_another()
            self.prepare()
            self.build()
            # Again after the build: a stack started meanwhile by anything not holding the lock.
            self._refuse_beside_another()
            self.up()
        except BaseException:
            self.down()
            raise

    def exec(self, service: str, *argv: str, stdin: str | None = None):
        return self.compose("exec", "-T", service, *argv, check=False, stdin=stdin)

    def logs(self, service: str) -> str:
        return self.compose("logs", "--no-color", "--no-log-prefix", service).stdout

    def container_id(self, service: str) -> str:
        return self.compose("ps", "-q", service).stdout.strip()

    def restart_count(self, service: str) -> int:
        result = self.run(
            ["docker", "inspect", "-f", "{{.RestartCount}}", self.container_id(service)]
        )
        return int(result.stdout.strip())

    def recorder_ip(self, n: int) -> str:
        network = f"{self.project}_modelnet"
        template = f'{{{{(index .NetworkSettings.Networks "{network}").IPAddress}}}}'
        result = self.run(["docker", "inspect", "-f", template, self.container_id(f"recorder_{n}")])
        return result.stdout.strip()

    def _write_cue(self, n: int, payload: dict, timeout: float = 60.0) -> None:
        path = self.cues / f"{self.recorder_ip(n)}.json"
        wait_for(lambda: not path.exists(), timeout=timeout, what=f"agent_{n}'s previous cue")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temporary, path)

    def cue(self, n: int, tool: str, arguments: dict) -> None:
        self._write_cue(n, {"name": tool, "arguments": arguments})

    def stop(self, n: int) -> None:
        self._write_cue(n, {"stop": True})

    def down(self) -> None:
        try:
            if self._torn_down:
                return
            if (self.root / "override.yml").exists():
                self.compose("down", "-v", "--remove-orphans", "--timeout", "5", check=False)
            self._torn_down = True
            shutil.rmtree(self.root, ignore_errors=True)
        finally:
            self._release_the_lock()
