"""The smoke stack: three agents, their recorders, a cued stub model and the fake diode.

Everything it makes lives under one scratch root in the repository (.smoke-<pid>/, gitignored and
outside the build context): plain data/ directories standing in for the bounded volume images
(creating real images needs root, which stays the operator's), a cue directory for the stub, an
env file, and a compose override. Nothing under the real volumes/, operator/ or .env is read or
written, and the project name is its own, so it can never touch a running space-chassis stack.

The model key is a dummy. Compose lets the shell's environment beat --env-file, so every docker
call here runs with an allowlisted environment: whatever the operator's shell exports, no key and
no upstream reaches the smoke recorders.

It builds and runs its own image tag, SMOKE_IMAGE, so the operator's `space-chassis-agent` is never
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
CONSOLE_SEED = REPO / "llm_console_seed.json"
DOCKER_TIMEOUT_SECONDS = 120
BUILD_TIMEOUT_SECONDS = 3600
STUB_PORT = 8199
DUMMY_KEY = "sk-smoke-dummy"


def allowed_environment(extra: dict | None = None) -> dict:
    """The process environment docker runs with: an allowlist, never the operator's whole shell."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key in ALLOWED_VARIABLES or key.startswith("DOCKER_")
    }
    env.update(extra or {})
    return env


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
    ) -> None:
        self.agents = agents
        self.recorder_overrides = recorder_overrides or {}
        self.project = f"space_chassis_smoke_{os.getpid()}"
        self.root = Path(root) if root is not None else REPO / f".smoke-{os.getpid()}"
        self._runner = runner
        self._torn_down = False
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
            lines += [f"  agent_{n}:", f"    image: {SMOKE_IMAGE}"]
            lines += [f"  recorder_{n}:", f"    image: {SMOKE_IMAGE}", "    depends_on: [stub]"]
            overrides = self.recorder_overrides.get(n)
            if overrides:
                lines.append("    environment:")
                lines += [f'      {key}: "{value}"' for key, value in overrides.items()]
        lines += [
            "  diode:",
            f"    image: {SMOKE_IMAGE}",
            '    entrypoint: ["python", "/opt/fake/fake_diode.py"]',
            "    environment:",
            f"      AGENT_SLUGS: {','.join(self.slugs)}",
            "    volumes:",
            "      - ./contract/fake_diode.py:/opt/fake/fake_diode.py:ro",
            "    networks: !override [windowside]",
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
            "--profile",
            "fleet",
            "--profile",
            "diode",
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
            self.compose("build", "agent_1", timeout=BUILD_TIMEOUT_SECONDS)
        finally:
            if kept is None:
                CONSOLE_SEED.unlink(missing_ok=True)
            else:
                CONSOLE_SEED.write_bytes(kept)

    def up(self) -> None:
        services = ["stub"]
        services += [f"recorder_{n}" for n in range(1, self.agents + 1)]
        services += [f"agent_{n}" for n in range(1, self.agents + 1)]
        services.append("diode")
        self.compose("up", "-d", *services)

    def start(self) -> None:
        try:
            self.prepare()
            self.build()
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
        if self._torn_down:
            return
        if (self.root / "override.yml").exists():
            self.compose("down", "-v", "--remove-orphans", "--timeout", "5", check=False)
        self._torn_down = True
        shutil.rmtree(self.root, ignore_errors=True)
