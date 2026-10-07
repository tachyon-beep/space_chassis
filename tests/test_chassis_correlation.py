"""Recorder in the loop (SV-022 D): the real chassis, the real recorder, a local stub upstream.

Evidence kind: real processes on one host. `services/recorder.py` runs as the
end-to-end tests run it (conftest's `Stack`), relaying over unix sockets to an
in-process stub model that records every body it receives; real
`services/chassis.py` processes are killed and restarted against one
temporary root. Dummy credentials only; no provider, no internet endpoint, no
deployment.

Correlation is by the recorder's request id: its `open` event carries
`client_label`, and the transcript record with the same id carries the request
as forwarded. The label is a hint the chassis sends, never an authenticated or
idempotency key: nothing here (or in the recorder) deduplicates by it, and
these tests do not treat it as proof of anything beyond equality of the two
records.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import chassis
import chassis_persistence as cp
import chassis_session as cs
import chassis_startup as st
import pytest
from conftest import Stack, World
from stub_model import Reply, Stub, ToolCall

SERVICES = Path(__file__).resolve().parent.parent / "services"
KEY = chassis.CORRELATION_KEY

DUTY = '''
import os
import time

import chassis

tools = chassis.ToolRegistry()


@tools.register
def note_it(text: str) -> str:
    """Note."""
    with open(os.path.join(os.environ["COUNT_DIR"], "note_it"), "a") as handle:
        handle.write("x")
    return "noted " + text


def main(context):
    started = os.environ.get("STARTED_MARKER")
    if started:
        # Startup and recovery are over; the first request waits for the test.
        open(started, "w").close()
        deadline = time.time() + 60
        while not os.path.exists(os.environ["RELEASE_MARKER"]):
            if time.time() > deadline:
                raise SystemExit(3)
            time.sleep(0.05)
    for _ in range(int(os.environ.get("ASKS", "1"))):
        context.ask("go")
'''

# A test-only launcher (the accepted FAULT_LAUNCHER pattern): small segments,
# so a short run rotates and collects whole segments; then the real runtime.
SMALL_SEGMENTS = '''
import os, runpy, sys
services = sys.argv[1]
sys.path.insert(0, services)
import chassis_persistence as cp
original = cp.LedgerWriter.__init__
def init(self, *args, **kwargs):
    original(self, *args, **kwargs)
    self.segment_max = int(os.environ["SEGMENT_MAX_TEST"])
cp.LedgerWriter.__init__ = init
sys.argv = [os.path.join(services, "chassis.py")]
runpy.run_path(sys.argv[0], run_name="__main__")
'''


class Recording(Stub):
    """The stub upstream, keeping every body it receives; request number `hold` waits for the test."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.bodies: list[dict] = []
        self.hold: int | None = None
        self.held = threading.Event()
        self.release = threading.Event()

    def handle(self, body):
        self.bodies.append(json.loads(body))
        if self.hold is not None and len(self.bodies) == self.hold:
            self.held.set()
            self.release.wait(60)  # the test kills the runtime meanwhile
        return super().handle(body)


class Loop:
    """One temporary root: the recorder, the stub upstream, and real chassis processes."""

    def __init__(self, replies) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="sv22-", dir="/tmp"))  # unix socket paths stay short
        self.world = World(self.root)
        (self.world.work / "duty.py").write_text(DUTY, encoding="utf-8")
        (self.root / "launch.py").write_text(SMALL_SEGMENTS, encoding="utf-8")
        (self.root / "counts").mkdir()
        self.stack = Stack(self.world)
        self.stub = self.stack.stub = Recording(script=replies)
        self.stack.__enter__()

    def close(self) -> None:
        self.stub.release.set()
        self.stack.__exit__(None, None, None)
        shutil.rmtree(self.root, ignore_errors=True)

    @property
    def session_dir(self) -> Path:
        return self.world.home / "session"

    def env(self, **extra) -> dict:
        env = dict(self.stack.env)
        for name in ("RUN_MAX_TURNS", "RUN_MAX_SECONDS", "CONTEXT_WINDOW_EVICTION_TOKENS", "AGENT_ENTRY"):
            env.pop(name, None)
        env.update({"COUNT_DIR": str(self.root / "counts"), "SOCKET_WAIT_SECONDS": "10", "SEGMENT_MAX_TEST": "1"})
        env.update(extra)
        return env

    def popen(self, *, small: bool = False, **extra) -> subprocess.Popen:
        command = [sys.executable, str(self.root / "launch.py"), str(SERVICES)] if small else [sys.executable, str(SERVICES / "chassis.py")]
        return subprocess.Popen(command, cwd=str(self.world.work), env=self.env(**extra), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def finish(self, process: subprocess.Popen) -> None:
        out, err = process.communicate(timeout=60)
        assert process.returncode == 0, out[-2000:] + err[-2000:]

    def killed_in_flight(self, *, small: bool = False, **extra) -> None:
        """A run whose next request reaches the upstream, and then the process is killed."""
        self.stub.hold = len(self.stub.bodies) + 1
        self.stub.held.clear()
        self.stub.release.clear()
        process = self.popen(small=small, ASKS="1", **extra)
        assert self.stub.held.wait(30), "the request never reached the upstream"
        process.kill()
        process.communicate(timeout=30)
        self.stub.release.set()

    def behind_a_barrier(self, *, small: bool = False, **extra):
        """A run held at the duty's first request; returns (process, release marker)."""
        started, release = self.root / f"started-{time.monotonic_ns()}", self.root / f"release-{time.monotonic_ns()}"
        process = self.popen(small=small, STARTED_MARKER=str(started), RELEASE_MARKER=str(release), **extra)
        deadline = time.time() + 30
        while not started.exists():
            assert process.poll() is None, process.communicate()[1][-2000:]
            assert time.time() < deadline, "the duty never started"
            time.sleep(0.05)
        return process, release

    def records(self) -> list:
        segments = cp.read_segments(self.session_dir / "ledger")
        return list(cp.scan_segments(segments, st._segment_lineage(segments)).records)

    def sent(self) -> list[str]:
        return [r.payload["label"] for r in self.records() if r.type_name == "REQUEST_SENT"]

    def opens(self) -> list[dict]:
        return [event for event in self.stack.events() if event.get("event") == "open"]

    def counts(self) -> dict:
        return {p.name: len(p.read_text()) for p in (self.root / "counts").iterdir()}


@pytest.fixture
def loop():
    opened: list[Loop] = []

    def build(replies) -> Loop:
        world = Loop(replies)
        opened.append(world)
        return world

    yield build
    for world in opened:
        world.close()


def assert_stripped(world: Loop) -> None:
    """The label never reaches the upstream, and the transcript records the request as forwarded."""
    assert world.stub.bodies and all(KEY not in body for body in world.stub.bodies)
    for record in world.stack.transcript():
        assert KEY not in record["request"], "the label reached the transcript's request"


def test_recorder_in_loop_labels_correlate_and_an_interrupted_attempt_advances_identity(loop):
    world = loop([Reply(text="fine", repeat=100)])
    world.killed_in_flight()
    (first,) = world.sent()
    assert [event["client_label"] for event in world.opens()] == [first], "REQUEST_SENT == open.client_label"
    lineage, turn, attempt = first.rsplit(":", 2)
    # Restart: recovery runs to the duty's barrier without contacting anything.
    process, release = world.behind_a_barrier(ASKS="1")
    assert len(world.stub.bodies) == 1 and len(world.opens()) == 1, "recovery sent nothing to the recorder or upstream"
    spend = [r.payload for r in world.records() if r.type_name == "RECOVERY"]
    assert [p["kind"] for p in spend] == ["possible_duplicate_spend"] and spend[0]["detail"]["label"] == first
    release.touch()
    world.finish(process)
    second = f"{lineage}:{turn}:{int(attempt) + 1}"
    assert world.sent() == [first, second], "the interrupted attempt is never reused"
    opens = world.opens()
    assert [event["client_label"] for event in opens] == [first, second]
    assert len({event["id"] for event in opens}) == 2, "two recorder requests, correlated by id"
    by_id = {record["id"]: record for record in world.stack.transcript()}
    assert opens[1]["id"] in by_id and by_id[opens[1]["id"]]["request"]["messages"]
    assert not opens[1].get("label_seen_before")
    assert_stripped(world)


def test_recorder_in_loop_identity_survives_collection_and_a_later_interruption(loop):
    world = loop([Reply(tool_calls=[ToolCall("note_it", {"text": "a"})], repeat=100)])
    first = world.popen(small=True, ASKS="4")
    world.finish(first)
    lineage = json.loads((world.session_dir / "run.json").read_text())["lineage_id"]
    early = [event["client_label"] for event in world.opens()]
    assert early == [f"{lineage}:{turn}:1" for turn in (1, 2, 3, 4)]
    assert world.counts() == {"note_it": 4}
    # Collection ran in the real runtime: segment 0 and the first requests' records are gone.
    assert not (world.session_dir / "ledger" / cp.segment_name(0)).exists()
    assert early[0] not in world.sent(), "the first REQUEST_SENT was collected"
    assert [r for r in world.records() if r.type_name == "GC_DONE"]
    # A restart after collection: recovery contacts nothing; the next identity is new.
    process, release = world.behind_a_barrier(small=True, ASKS="1")
    assert len(world.opens()) == 4 and len(world.stub.bodies) == 4
    release.touch()
    world.finish(process)
    fifth = world.sent()[-1]
    assert fifth == f"{lineage}:5:1" and fifth not in early
    assert world.opens()[-1]["client_label"] == fifth
    # Interrupted after collection: the next run uses a new attempt, again without contact before its barrier.
    world.killed_in_flight(small=True)
    interrupted = world.sent()[-1]
    assert interrupted == f"{lineage}:6:1" and world.opens()[-1]["client_label"] == interrupted
    process, release = world.behind_a_barrier(small=True, ASKS="1")
    assert len(world.opens()) == 6 and len(world.stub.bodies) == 6, "recovery sent nothing"
    release.touch()
    world.finish(process)
    retried = world.sent()[-1]
    assert retried == f"{lineage}:6:2" and world.opens()[-1]["client_label"] == retried
    labels = [event["client_label"] for event in world.opens()]
    assert len(labels) == len(set(labels)) == 7, "no label was ever sent twice"
    assert cs.read_identity(world.session_dir, lineage) >= 6
    assert world.counts() == {"note_it": 6}, "no tool was replayed by any recovery"
    assert_stripped(world)
