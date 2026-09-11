"""Fixtures for the host-side suite.

The tests run the real services -- the recorder, the supervisor, the chassis --
against a stub model, because the properties worth testing here are the ones
that only appear when the pieces are wired together: a conversation that
survives a run ending, a run that pauses instead of dying when the upstream
refuses, a record that exists after the process is gone.

Nothing in this file touches Docker. The container tests are separate and
skipped unless a stack is up.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
SERVICES = PROJECT / "services"
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(SERVICES))
sys.path.insert(0, str(PROJECT / "endurance"))
sys.path.insert(0, str(PROJECT / "contract"))

from common import utc_now  # noqa: E402
from stub_model import Faults, Reply, Stub, StubServer, ToolCall, default_script  # noqa: E402


class World:
    """A whole world on a short path, with one agent in it by default."""

    def __init__(self, root: Path, slug: str = "agent_1") -> None:
        self.root = root
        self.slug = slug
        self.work = root / "work"
        self.home = root / "home" / slug
        self.diary = root / "diary" / slug
        self.transcripts = root / "transcripts"
        self.telemetry = root / "telemetry"
        self.diode = root / "diode"
        self.pump = root / "pump"
        self.sockets = root / "sock"
        for path in (
            self.work,
            self.home / "session",
            self.diary,
            self.transcripts,
            self.telemetry,
            self.diode / slug / "output",
            self.pump / slug,
            self.sockets,
        ):
            path.mkdir(parents=True, exist_ok=True)
        for name in ("duty.py", "prompts.py"):
            source = PROJECT / "tasks" / name
            if source.exists():
                shutil.copy2(source, self.work / name)
        shutil.copy2(PROJECT / "services" / "chassis.py", self.work / "chassis.py")
        (self.work / "roster.json").write_text('{"agents": []}\n', encoding="utf-8")

    def env(self, base_url: str, socket_path: Path, upstream_socket: Path) -> dict:
        env = dict(os.environ)
        env.update(
            {
                "AGENT_SLUG": self.slug,
                "AGENT_NAME": "otter",
                "WORK_DIR": str(self.work),
                "SEED_DIR": str(PROJECT / "tasks"),
                "AGENT_HOME": str(self.home),
                "DIARY_DIR": str(self.diary),
                "BRIEF_DIR": str(PROJECT / "brief"),
                "SERVICES_DIR": str(SERVICES),
                "TRANSCRIPTS_DIR": str(self.transcripts),
                "TELEMETRY_DIR": str(self.telemetry),
                "DIODE_DIR": str(self.diode),
                "DIODE_DUTY_DIR": str(self.diode / self.slug),
                "PUMP_DUTY_DIR": str(self.pump / self.slug),
                "LLM_BASE_URL": base_url,
                "UPSTREAM_SOCKET": str(upstream_socket),
                "LLM_API_KEY": "sk-test",
                "LLM_SOCKET_PATH": str(socket_path),
                "LLM_MODEL": "stub",
                "OPENROUTER_API_KEY": "sk-dummy",
                "CONTEXT_WINDOW_TOKENS": "200000",
                "SUPERVISOR_INACTIVITY_SECONDS": "600",
                "TELEMETRY_INTERVAL_SECONDS": "1",
                "RECORDER_HOURLY_MAX": "10000",
                "RECORDER_TOKEN_HOURLY_MAX": "100000000",
                "RECORDER_TOKEN_GLOBAL_HOURLY_MAX": "1000000000",
                "RECORDER_REFUSE_DIR": str(self.root / "markers"),
            }
        )
        (self.root / "markers").mkdir(exist_ok=True)
        return env


class Stack:
    """The recorder, running, plus the stub model it forwards to."""

    def __init__(self, world: World, script=None, faults: Faults | None = None) -> None:
        self.world = world
        self.model_socket = world.root / "model.sock"
        self.stub = Stub(
            script=script or default_script(),
            faults=faults or Faults(),
            think_seconds=0.0,
            journal=world.root / "stub-journal.jsonl",
        )
        self.server: StubServer | None = None
        self.recorder: subprocess.Popen | None = None

    def __enter__(self) -> Stack:
        self.server = StubServer(self.stub, socket_path=self.model_socket).start()
        socket_path = self.world.sockets / f"{self.world.slug}.sock"
        env = self.world.env(f"{self.server.url}/v1", socket_path, self.model_socket)
        env["AGENT_SLUGS"] = self.world.slug
        env["SOCKET_DIR"] = str(self.world.sockets)
        self.recorder = subprocess.Popen(
            [sys.executable, str(SERVICES / "recorder.py")],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 20
        while not socket_path.exists():
            if time.time() > deadline:
                raise RuntimeError("the recorder never opened its socket")
            time.sleep(0.05)
        self.env = env
        return self

    def __exit__(self, *_exc) -> None:
        if self.recorder is not None:
            self.recorder.terminate()
            try:
                self.recorder.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                self.recorder.kill()
        if self.server is not None:
            self.server.stop()

    # -- driving the chassis -------------------------------------------------
    def run_chassis(
        self, timeout: float = 60.0, extra_env: dict | None = None
    ) -> subprocess.CompletedProcess:
        env = dict(self.env)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(SERVICES / "chassis.py")],
            env=env,
            cwd=str(self.world.work),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def run_supervisor(
        self, timeout: float = 90.0, extra_env: dict | None = None
    ) -> subprocess.CompletedProcess:
        env = dict(self.env)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(SERVICES / "supervisor.py")],
            env=env,
            cwd=str(self.world.work),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    # -- reading the record --------------------------------------------------
    def transcript(self) -> list[dict]:
        return read_jsonl(self.world.transcripts / self.world.slug / "agent_life_transcript.jsonl")

    def events(self) -> list[dict]:
        return read_jsonl(self.world.transcripts / self.world.slug / "events.jsonl")

    def lifecycle(self) -> list[dict]:
        return read_jsonl(self.world.telemetry / "agents" / self.world.slug / "lifecycle.jsonl")

    def conversation(self) -> list[dict]:
        path = self.world.home / "session" / "conversation.json"
        if not path.exists():
            return []
        import json

        return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    import json

    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


@pytest.fixture
def world(tmp_path: Path) -> World:
    # A short path under the session workspace: a unix socket's address is
    # capped around a hundred bytes, and pytest's tmp_path is deep.
    root = Path(os.environ.get("SC_SCRATCH", "/home/john/space_chassis/.scratch"))
    root = root / "pytest" / f"w{os.getpid()}-{utc_now().strftime('%H%M%S%f')}"
    root.mkdir(parents=True, exist_ok=True)
    yield World(root)
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def stack(world: World) -> Stack:
    with Stack(world) as running:
        yield running


@pytest.fixture
def scripted():
    """A script that ends a run on purpose, so the ladder's path is exercised."""

    def build(*replies: Reply) -> list[Reply]:
        return list(replies)

    return build


def tool_call(name: str, **arguments) -> ToolCall:
    return ToolCall(name, arguments)


__all__ = [
    "Stack",
    "World",
    "read_jsonl",
    "tool_call",
    "Faults",
    "Reply",
    "ToolCall",
    "default_script",
]
