"""The recorder's custody of its record (SV-017 / R-B4), on faults the test controls.

The contract is SV-015 v2 section 1.5 (the append helper, the boundary check
from disk, per-slug name fencing, result classes, record-before-relay) with
SV-013 section 2.1.8's failure and status rules and fixtures R-C1...R-C8.

Faults are injected through `common.FileOps`, the one place the store makes its
system calls, so every short write, ENOSPC, EINTR and failed sync here is
deterministic and nothing patches the process-wide `os`. A mocked fsync proves
what the code does with each answer; it proves nothing about what a disk does
on power loss, and nothing here claims to. Process death is a real child
process killed with SIGKILL.
"""

from __future__ import annotations

import errno
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
import recorder as recorder_module
from common import FileOps, RecordStore, encode_record
from test_recorder_requests import (  # noqa: F401 -- make_rig is a fixture
    RECORDER_KEY,
    SLUG,
    FakeUpstream,
    chat,
    completion,
    make_rig,
    read_jsonl,
    stub_reply,
)

SERVICES = Path(__file__).resolve().parent.parent / "services"


class FaultOps(FileOps):
    """Real system calls, with a script of faults keyed by file name."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.names: dict[int, str] = {}
        self.write_plan: list[tuple] = []  # (file name, action, argument), consumed in order
        self.fdatasync_fail: set[str] = set()
        self.sync_dir_fail: set[str] = set()
        self.chunk: int | None = None

    def open(self, path, flags, mode):
        self.calls.append(("open", Path(path).name, bool(flags & os.O_EXCL)))
        fd = super().open(path, flags, mode)
        self.names[fd] = Path(path).name
        return fd

    def write(self, fd, data):
        name = self.names[fd]
        if self.write_plan and self.write_plan[0][0] == name:
            _name, action, argument = self.write_plan.pop(0)
            self.calls.append(("write", name, action))
            if action == "raise":
                raise OSError(argument, os.strerror(argument))
            if action == "eintr":
                raise InterruptedError(errno.EINTR, "interrupted")
            if action == "zero":
                return 0
            if action == "short":
                return super().write(fd, data[:argument])
        self.calls.append(("write", name, "ok"))
        if self.chunk is not None:
            return super().write(fd, data[: self.chunk])
        return super().write(fd, data)

    def fdatasync(self, fd):
        name = self.names[fd]
        self.calls.append(("fdatasync", name))
        if name in self.fdatasync_fail:
            raise OSError(errno.EIO, "injected EIO")
        super().fdatasync(fd)

    def sync_dir(self, path):
        self.calls.append(("sync_dir", path))
        if path in self.sync_dir_fail:
            raise OSError(errno.EIO, "injected EIO")
        super().sync_dir(path)

    def close(self, fd):
        self.calls.append(("close", self.names.pop(fd, "?")))
        super().close(fd)


@pytest.fixture
def root():
    path = Path(tempfile.mkdtemp(prefix="sv17-", dir="/tmp"))
    yield path
    import shutil  # noqa: PLC0415 -- teardown only

    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def store(root):
    ops = FaultOps()
    made = RecordStore(root, ops=ops)
    (root / "a").mkdir()
    yield made
    made.close()


def lines(path: Path) -> list[bytes]:
    return path.read_bytes().split(b"\n")


def parsed(path: Path) -> list[dict]:
    """The records a reader sees: every line that parses; a torn fragment is skipped."""
    records = []
    for line in lines(path):
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


_SWAPPED: list[RecordStore] = []


@pytest.fixture(autouse=True)
def _close_swapped_stores():
    yield
    while _SWAPPED:
        _SWAPPED.pop().close()


# ---------------------------------------------------------------------------
# The serializer
# ---------------------------------------------------------------------------
def test_a_record_is_one_ascii_json_line_and_non_finite_numbers_are_refused(store, root):
    line = encode_record({"k": "é\ud800", "n": 1})
    assert line == b'{"k":"\\u00e9\\ud800","n":1}\n'
    assert json.loads(line) == {"k": "é\ud800", "n": 1}
    result = store.append_record(root / "a" / "events.jsonl", {"x": float("nan")})
    assert result.status == "failed" and result.detail == "unserializable"
    assert not (root / "a" / "events.jsonl").exists()


# ---------------------------------------------------------------------------
# Name fencing: per slug, per file, root rule
# ---------------------------------------------------------------------------
def test_the_first_append_fences_the_file_its_slug_and_the_root_in_order(store, root):
    """O3-2: create, sync the slug directory, sync the root, write, data-sync -> durable."""
    result = store.append_record(root / "a" / "events.jsonl", {"n": 1})
    assert result.status == "durable" and not result.dir_unsynced
    assert [c for c in store.ops.calls if c[0] != "close"] == [
        ("open", "events.jsonl", True),
        ("sync_dir", str(root / "a")),
        ("sync_dir", str(root)),
        ("write", "events.jsonl", "ok"),
        ("fdatasync", "events.jsonl"),
    ]


def test_each_new_slug_gets_its_own_root_sync_and_each_new_file_its_directory_sync(store, root):
    """O3-7: slug B discovered later is fenced by its own root sync; a second file in A needs none."""
    store.append_record(root / "a" / "events.jsonl", {"n": 1})
    store.ops.calls.clear()
    assert store.append_record(root / "a" / "agent_life_transcript.jsonl", {"n": 2}).status == "durable"
    syncs = [c for c in store.ops.calls if c[0] == "sync_dir"]
    assert syncs == [("sync_dir", str(root / "a"))], "the root was already fenced for slug a"
    (root / "b").mkdir()
    store.ops.calls.clear()
    assert store.append_record(root / "b" / "events.jsonl", {"n": 3}).status == "durable"
    syncs = [c for c in store.ops.calls if c[0] == "sync_dir"]
    assert syncs == [("sync_dir", str(root / "b")), ("sync_dir", str(root))]


def test_the_root_level_file_is_fenced_by_the_root_alone(store, root):
    result = store.append_record(root / "recorder.jsonl", {"event": "recorder_start"})
    assert result.status == "durable"
    syncs = [c for c in store.ops.calls if c[0] == "sync_dir"]
    assert syncs == [("sync_dir", str(root))]


def test_a_failed_root_sync_is_never_reported_durable_and_is_retried(store, root):
    """O3-7 fault variant: readable, `appended` with `dir_unsynced`, until a whole fence returns."""
    store.ops.sync_dir_fail.add(str(root))
    path = root / "a" / "events.jsonl"
    first = store.append_record(path, {"n": 1})
    assert first.status == "appended" and first.dir_unsynced and first.readable
    second = store.append_record(path, {"n": 2})
    assert second.status == "appended" and second.dir_unsynced
    store.ops.sync_dir_fail.clear()
    third = store.append_record(path, {"n": 3})
    assert third.status == "durable" and not third.dir_unsynced
    assert [r["n"] for r in parsed(path)] == [1, 2, 3]


def test_a_failed_slug_directory_sync_is_never_reported_durable(store, root):
    store.ops.sync_dir_fail.add(str(root / "a"))
    result = store.append_record(root / "a" / "events.jsonl", {"n": 1})
    assert result.status == "appended" and result.dir_unsynced


def test_an_existing_file_from_a_dead_process_is_reopened_and_fenced_again(root):
    """O3-3: this process did not create it, and does not trust whoever did."""
    (root / "a").mkdir()
    path = root / "a" / "events.jsonl"
    path.write_bytes(b'{"n":0}\n')
    ops = FaultOps()
    store = RecordStore(root, ops=ops)
    try:
        assert store.append_record(path, {"n": 1}).status == "durable"
    finally:
        store.close()
    assert ops.calls[:2] == [("open", "events.jsonl", True), ("open", "events.jsonl", False)]
    assert ("sync_dir", str(root / "a")) in ops.calls and ("sync_dir", str(root)) in ops.calls
    assert [r["n"] for r in parsed(path)] == [0, 1]


def test_without_a_data_sync_a_line_is_appended_not_durable(store, root):
    result = store.append_record(root / "a" / "events.jsonl", {"n": 1}, fsync=False)
    assert result.status == "appended" and not result.dir_unsynced
    assert not [c for c in store.ops.calls if c[0] == "fdatasync"]


# ---------------------------------------------------------------------------
# Writes: short, interrupted, failed, partial, zero
# ---------------------------------------------------------------------------
def test_short_writes_and_eintr_still_complete_one_line(store, root):
    path = root / "a" / "events.jsonl"
    store.ops.chunk = 5
    store.ops.write_plan = [("events.jsonl", "eintr", None)]
    result = store.append_record(path, {"message": "x" * 40})
    assert result.status == "durable" and result.written == len(encode_record({"message": "x" * 40}))
    assert parsed(path) == [{"message": "x" * 40}]


def test_enospc_before_any_byte_is_failed_and_the_next_append_is_clean(store, root):
    path = root / "a" / "events.jsonl"
    store.append_record(path, {"n": 1})
    store.ops.write_plan = [("events.jsonl", "raise", errno.ENOSPC)]
    failed = store.append_record(path, {"n": 2})
    assert failed.status == "failed" and failed.errno == errno.ENOSPC and failed.written == 0
    assert ("close", "events.jsonl") in store.ops.calls, "the descriptor is dropped after an error"
    assert store.append_record(path, {"n": 3}).status == "durable"
    assert path.read_bytes() == b'{"n":1}\n{"n":3}\n'


def test_enospc_after_a_prefix_is_partial_and_the_next_line_starts_on_a_boundary(store, root):
    """R-C2: 100 bytes of a 300-byte line, then ENOSPC; the next record is still a record."""
    path = root / "a" / "agent_life_transcript.jsonl"
    record = {"pad": "y" * (300 - len(encode_record({"pad": ""})))}
    assert len(encode_record(record)) == 300
    store.ops.write_plan = [
        ("agent_life_transcript.jsonl", "short", 100),
        ("agent_life_transcript.jsonl", "raise", errno.ENOSPC),
    ]
    partial = store.append_record(path, record)
    assert partial.status == "partial" and partial.written == 100 and not partial.readable
    after = store.append_record(path, {"n": 2})
    assert after.status == "durable"
    raw = path.read_bytes()
    assert raw == encode_record(record)[:100] + b"\n" + b'{"n":2}\n'
    assert parsed(path) == [{"n": 2}], "one unparseable 100-byte fragment, then one record"
    # The negative control: appending without the boundary check joins them.
    with pytest.raises(json.JSONDecodeError):
        json.loads(encode_record(record)[:100] + b'{"n":2}')


def test_a_zero_byte_write_ends_the_append_instead_of_spinning(store, root):
    path = root / "a" / "events.jsonl"
    store.ops.write_plan = [("events.jsonl", "zero", None)]
    result = store.append_record(path, {"n": 1})
    assert result.status == "failed" and result.detail == "zero_write"
    store.ops.chunk = 3
    store.ops.write_plan = [("events.jsonl", "ok", None), ("events.jsonl", "zero", None)]
    result = store.append_record(path, {"n": 2})
    assert result.status == "partial" and result.written == 3
    assert store.append_record(path, {"n": 3}).status == "durable"
    assert parsed(path) == [{"n": 3}]


def test_a_failed_data_sync_is_readable_degraded_and_stays_degraded(store, root):
    """R-C6 at the helper: the bytes are there; their durability is unknown, and says so."""
    path = root / "a" / "agent_life_transcript.jsonl"
    store.ops.fdatasync_fail.add("agent_life_transcript.jsonl")
    result = store.append_record(path, {"n": 1})
    assert result.status == "appended_fsync_failed" and result.readable and result.errno == errno.EIO
    assert store.degraded(path)
    store.ops.fdatasync_fail.clear()
    assert store.append_record(path, {"n": 2}).status == "durable"
    assert store.degraded(path), "a later success proves nothing about earlier bytes"
    assert [r["n"] for r in parsed(path)] == [1, 2]


def test_a_torn_tail_left_by_a_dead_process_is_repaired_by_a_new_store(root):
    """O3-1 / the v2 restart trace, with a real child process dying mid-line."""
    (root / "a").mkdir()
    path = root / "a" / "agent_life_transcript.jsonl"
    record = {"pad": "z" * (300 - len(encode_record({"pad": ""})))}
    script = (
        "import os, sys\n"
        "fd = os.open(sys.argv[1], os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)\n"
        "os.write(fd, bytes.fromhex(sys.argv[2]))\n"
        "os._exit(0)\n"
    )
    subprocess.run(
        [sys.executable, "-I", "-c", script, str(path), encode_record(record)[:100].hex()],
        check=True,
        timeout=30,
    )
    store = RecordStore(root)
    try:
        result = store.append_record(path, {"n": 1})
    finally:
        store.close()
    assert result.status == "durable"
    assert path.read_bytes() == encode_record(record)[:100] + b"\n" + b'{"n":1}\n'
    assert parsed(path) == [{"n": 1}]


def test_concurrent_appends_to_one_file_never_interleave(store, root):
    path = root / "a" / "events.jsonl"
    barrier = threading.Barrier(8)
    results = []

    def writer(number):
        barrier.wait()
        for index in range(50):
            results.append(store.append_record(path, {"w": number, "i": index, "pad": "p" * 200}))

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert all(r.status == "durable" for r in results) and len(results) == 400
    records = parsed(path)
    assert len(records) == 400 and len(lines(path)) == 401
    assert sorted((r["w"], r["i"]) for r in records) == [(w, i) for w in range(8) for i in range(50)]


def test_the_path_count_is_bounded_and_a_closed_store_writes_nothing(root):
    (root / "a").mkdir()
    store = RecordStore(root, max_paths=1)
    assert store.append_record(root / "a" / "events.jsonl", {"n": 1}).status == "durable"
    over = store.append_record(root / "a" / "other.jsonl", {"n": 1})
    assert over.status == "failed" and over.errno == errno.EMFILE
    store.close()
    assert store.append_record(root / "a" / "events.jsonl", {"n": 2}).status == "failed"
    with pytest.raises(ValueError):
        RecordStore(root).append_record(root / "a" / "deep" / "x.jsonl", {})


# ---------------------------------------------------------------------------
# The handler: record before relay, custody before spend
# ---------------------------------------------------------------------------
def fault_store(rig) -> FaultOps:
    """Give the rig's agent a store whose system calls the test scripts."""
    ops = FaultOps()
    swapped = RecordStore(rig.root / "transcripts", ops=ops)
    _SWAPPED.append(swapped)
    rig.recorder.state.store = swapped
    return ops


def test_a_failed_transcript_withholds_the_answer_and_the_actual_usage_is_charged(make_rig):
    """R-C1: upstream 200 with usage, transcript ENOSPC -> 502 record_failed."""
    rig = make_rig(tk=1000, g=1000)
    ops = fault_store(rig)
    ops.write_plan = [("agent_life_transcript.jsonl", "raise", errno.ENOSPC)]
    status, _headers, payload = rig.post(chat())
    assert status == 502 and json.loads(payload)["error"]["code"] == "record_failed"
    assert b"choices" not in payload
    (close,) = rig.closes()
    assert close["outcome"] == "record_failed" and close["recorded"] == "failed"
    assert close["relayed"] is False and close["upstream_status"] == 200
    assert close["usage_class"] == "known" and close["charged_tokens"] == 30
    assert rig.budget.snapshot(SLUG)["tokens_used"] == 30
    assert len(rig.upstream.requests) == 1


def test_a_partial_transcript_is_withheld_and_the_next_turn_is_recorded_cleanly(make_rig):
    """R-C2 through the handler."""
    rig = make_rig(rq=10, tk=1000, g=1000)
    ops = fault_store(rig)
    ops.write_plan = [
        ("agent_life_transcript.jsonl", "short", 100),
        ("agent_life_transcript.jsonl", "raise", errno.ENOSPC),
    ]
    assert rig.post(chat())[0] == 502
    assert rig.post(chat())[0] == 200
    closes = rig.closes(2)
    assert [c["recorded"] for c in closes] == ["partial", "durable"]
    raw = (rig.dir / "agent_life_transcript.jsonl").read_bytes().split(b"\n")
    assert len(raw[0]) == 100 and json.loads(raw[1])["status"] == 200 and raw[2] == b""


def test_success_and_provider_errors_are_relayed_with_their_record_class(make_rig):
    rig = make_rig(rq=10, tk=1000, g=1000)
    assert rig.post(chat())[0] == 200
    rig.upstream.respond = lambda request: stub_reply({"error": {"message": "busy"}}, 503)
    assert rig.post(chat())[0] == 503
    closes = rig.closes(2)
    assert [(c["outcome"], c["recorded"], c["relayed"]) for c in closes] == [
        ("ok", "durable", True),
        ("upstream_http", "durable", True),
    ]
    assert len(rig.transcript()) == 2


def test_a_failed_data_sync_still_relays_and_is_reported_once(make_rig):
    """R-C6: readable bytes are relayed; durability_degraded goes to recorder.jsonl, once."""
    rig = make_rig(rq=10, tk=1000, g=1000)
    ops = fault_store(rig)
    ops.fdatasync_fail.add("agent_life_transcript.jsonl")
    assert rig.post(chat())[0] == 200
    assert rig.post(chat())[0] == 200
    closes = rig.closes(2)
    assert [c["recorded"] for c in closes] == ["appended_fsync_failed"] * 2
    assert all(c["relayed"] for c in closes)
    diagnostics = read_jsonl(rig.root / "transcripts" / "recorder.jsonl")
    degraded = [d for d in diagnostics if d.get("event") == "durability_degraded"]
    assert degraded == [{**degraded[0], "file": f"{SLUG}/agent_life_transcript.jsonl"}]


def test_an_unsynced_slug_directory_is_recorded_as_appended_with_dir_unsynced(make_rig):
    rig = make_rig()
    ops = fault_store(rig)
    ops.sync_dir_fail.add(str(rig.dir))
    assert rig.post(chat())[0] == 200
    (close,) = rig.closes()
    assert close["recorded"] == "appended" and close["dir_unsynced"] is True


def test_an_unrecordable_open_refuses_before_admission_or_contact(make_rig):
    """R-C4: 503 record_unavailable; no reservation; zero upstream calls; one close."""
    rig = make_rig()
    ops = fault_store(rig)
    ops.write_plan = [("events.jsonl", "raise", errno.ENOSPC)]
    status, _headers, payload = rig.post(chat())
    assert status == 503 and json.loads(payload)["error"]["code"] == "record_unavailable"
    (close,) = rig.closes()
    assert close["outcome"] == "record_unavailable" and "usage_class" not in close
    assert not [e for e in rig.events() if e["event"] == "open"]
    snap = rig.budget.snapshot(SLUG)
    assert (snap["requests_used"], snap["live"]) == (0, 0)
    assert rig.upstream.requests == []


def test_low_space_refuses_before_the_open_and_before_any_spend(make_rig, monkeypatch):
    """R-C5. A prediction, not a reservation; and an unknowable answer is not a yes."""
    rig = make_rig()
    monkeypatch.setattr(recorder_module, "MIN_FREE_BYTES", 1 << 62)
    status, _headers, payload = rig.post(chat())
    assert status == 503 and json.loads(payload)["error"]["code"] == "record_capacity"
    monkeypatch.setattr(recorder_module, "MIN_FREE_BYTES", 1)
    monkeypatch.setattr(recorder_module, "free_bytes", lambda path: None)
    status, _headers, payload = rig.post(chat())
    assert status == 503 and json.loads(payload)["error"]["code"] == "record_unavailable"
    assert [c["outcome"] for c in rig.closes(2)] == ["record_capacity", "record_unavailable"]
    assert not [e for e in rig.events() if e["event"] == "open"]
    assert rig.upstream.requests == []
    assert rig.budget.snapshot(SLUG)["requests_used"] == 0


def test_when_transcript_and_events_both_fail_one_bounded_line_reaches_stderr(make_rig, capfd):
    """R-C3: the open is there, the close is not, and the container log says why."""
    rig = make_rig(tk=1000, g=1000)
    ops = fault_store(rig)
    ops.write_plan = [
        ("events.jsonl", "ok", None),
        ("agent_life_transcript.jsonl", "raise", errno.ENOSPC),
        ("events.jsonl", "raise", errno.ENOSPC),
    ]
    status, _headers, payload = rig.post(chat(), headers={"Authorization": "Bearer CLIENT-DUMMY"})
    assert status == 502 and json.loads(payload)["error"]["code"] == "record_failed"
    deadline = time.monotonic() + 5
    err = ""
    while '"close_unrecorded"' not in err and time.monotonic() < deadline:
        time.sleep(0.02)
        err += capfd.readouterr().err
    fallback = [json.loads(line) for line in err.splitlines() if '"close_unrecorded"' in line]
    assert len(fallback) == 1
    assert set(fallback[0]) == {"id", "agent", "outcome", "status", "transcript", "close_unrecorded"}
    assert fallback[0]["outcome"] == "record_failed" and fallback[0]["transcript"] == "failed"
    assert "CLIENT-DUMMY" not in err and RECORDER_KEY not in err
    events = rig.events()
    assert [e["event"] for e in events] == ["open"], "an open without a close, nothing fabricated"
    assert rig.budget.snapshot(SLUG)["tokens_used"] == 30


def test_the_recorder_refuses_to_start_without_its_root_and_does_not_create_it(monkeypatch, tmp_path):
    missing = tmp_path / "no-such-transcripts"
    monkeypatch.setattr(recorder_module, "TRANSCRIPTS_DIR", missing)
    assert recorder_module.main() == 1
    assert not missing.exists()


def test_an_agent_directory_is_created_only_inside_an_existing_root(tmp_path):
    with pytest.raises(FileNotFoundError):
        recorder_module.AgentState("otter", tmp_path / "absent")
    recorder_module.close_stores()


def test_a_non_finite_response_number_is_recorded_as_a_marker(make_rig):
    """The custody serializer refuses NaN; the response is kept, marked, and relayed."""
    rig = make_rig()
    body = b'{"usage":{"total_tokens":30},"x":NaN,"y":1e999}'
    rig.upstream.respond = lambda request: (200, {"Content-Type": "application/json"}, body)
    status, _headers, payload = rig.post(chat())
    assert status == 200 and payload == body
    (close,) = rig.closes()
    assert close["recorded"] == "durable" and close["charged_tokens"] == 30
    response = rig.transcript()[0]["response"]
    assert response["x"] == {"__nonfinite__": "NaN"} and response["y"] == {"__nonfinite__": "1e999"}


# ---------------------------------------------------------------------------
# R-C8: process death never fabricates a close
# ---------------------------------------------------------------------------
def start_recorder(root: Path, upstream: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(
        {
            "SERVICES_DIR": str(SERVICES),
            "TRANSCRIPTS_DIR": str(root / "transcripts"),
            "SOCKET_DIR": str(root / "sock"),
            "AGENT_SLUGS": SLUG,
            "UPSTREAM_SOCKET": str(upstream),
            "LLM_BASE_URL": "http://upstream.invalid/v1",
            "LLM_API_KEY": RECORDER_KEY,
            "RECORDER_MIN_FREE_BYTES": "1",
            "RECORDER_REFUSE_DIR": str(root / "markers"),
        }
    )
    (root / "sock" / f"{SLUG}.sock").unlink(missing_ok=True)
    child = subprocess.Popen(
        [sys.executable, str(SERVICES / "recorder.py")],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 20
    while not (root / "sock" / f"{SLUG}.sock").exists():
        if child.poll() is not None or time.monotonic() > deadline:
            child.kill()
            child.wait(10)
            raise RuntimeError("the child recorder never opened its socket")
        time.sleep(0.05)
    return child


def raw_post(socket_path: Path, body: bytes) -> bytes:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(20)
    sock.connect(str(socket_path))
    try:
        sock.sendall(
            b"POST /api/v1/chat/completions HTTP/1.1\r\nHost: x\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )
        chunks = []
        while True:
            try:
                chunk = sock.recv(65536)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        sock.close()


def test_a_recorder_killed_mid_request_leaves_an_open_and_no_fabricated_close(root):
    """R-C8 at cut R3 (forwarding, before the response), with a real SIGKILL and restart."""
    for name in ("transcripts", "sock", "markers"):
        (root / name).mkdir()
    upstream = FakeUpstream(root / "up.sock")
    upstream.gate = threading.Event()
    children: list[subprocess.Popen] = []
    try:
        first = start_recorder(root, upstream.path)
        children.append(first)
        replies: dict = {}
        client = threading.Thread(
            target=lambda: replies.setdefault("first", raw_post(root / "sock" / f"{SLUG}.sock", chat()))
        )
        client.start()
        deadline = time.monotonic() + 20
        while not upstream.requests:
            assert time.monotonic() < deadline, "the request never reached the upstream"
            time.sleep(0.02)
        first.send_signal(signal.SIGKILL)
        first.wait(10)
        client.join(20)
        assert not replies["first"].startswith(b"HTTP/1.1 200"), "the dead recorder answered"
        upstream.gate.set()

        second = start_recorder(root, upstream.path)
        children.append(second)
        reply = raw_post(root / "sock" / f"{SLUG}.sock", chat())
        assert reply.startswith(b"HTTP/1.1 200")
        deadline = time.monotonic() + 10
        events_path = root / "transcripts" / SLUG / "events.jsonl"
        while len([e for e in read_jsonl(events_path) if e["event"] == "close"]) < 1:
            assert time.monotonic() < deadline
            time.sleep(0.02)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(10)
        upstream.stop()

    events = read_jsonl(root / "transcripts" / SLUG / "events.jsonl")
    opens = [e["id"] for e in events if e["event"] == "open"]
    closes = [e["id"] for e in events if e["event"] == "close"]
    assert len(opens) == 2 and len(closes) == 1
    assert opens[0] not in closes, "a close was fabricated for the killed request"
    assert closes == [opens[1]]
    boots = [d["boot"] for d in read_jsonl(root / "transcripts" / "recorder.jsonl") if d["event"] == "recorder_start"]
    assert len(boots) == 2 and boots[0] != boots[1]
    assert opens[0].split("-")[0] == boots[0] and opens[1].split("-")[0] == boots[1]
    assert len(read_jsonl(root / "transcripts" / SLUG / "agent_life_transcript.jsonl")) == 1
