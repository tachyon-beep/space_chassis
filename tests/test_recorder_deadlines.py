"""The recorder's deadlines and its watchdog (SV-018 / R-B3).

Expected values are SV-015 v2 section 2.1 (the t0 anchor, 570/540/480, the
forward check, the startup check, diagnostics off the enforcement path) and
fixtures O3-4, O3-5 and O3-6, with SV-013's R-B2 and R-B5 drip fixtures.

The 540/570/620 arithmetic, the forward check and the custody overrun run on a
fake clock. The socket branches run for real on short, scaled profiles: every
deadline here is under a few seconds, every server is stopped, and nothing
waits on the default 600-second profile. Nothing here measures TLS, DNS or a
real provider; those are commissioning gates.
"""

from __future__ import annotations

import errno
import json
import socket
import threading
import time

import pytest
import recorder as recorder_module
from common import FileOps, RecordStore
from recorder import Deadlines, Timing, Watchdog, timing_problems
from test_recorder_bounds import RawUpstream
from test_recorder_requests import (  # noqa: F401 -- make_rig is a fixture
    ROUTE,
    SLUG,
    chat,
    completion,
    make_rig,
    read_jsonl,
    stub_reply,
)


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start
        self.lock = threading.Lock()

    def monotonic(self) -> float:
        with self.lock:
            return self.t

    def set(self, value: float) -> None:
        with self.lock:
            self.t = value

    def advance(self, seconds: float) -> None:
        with self.lock:
            self.t += seconds


# A short real-time profile: E2E 3.7 s, upstream cutoff 3.4 s, latest start 2.4 s.
SHORT = Timing(
    client_timeout=4.0,
    client_margin=0.3,
    custody_reserve=0.3,
    min_upstream=1.0,
    header=0.5,
    body=0.6,
    client_write=1.0,
    io_timeout=10.0,  # longer than every deadline: only the watchdog can cut these
    tick=0.05,
)
SLACK = 0.5  # scheduling latency allowed on top of the tick


# ---------------------------------------------------------------------------
# The arithmetic
# ---------------------------------------------------------------------------
def test_the_deadlines_are_anchored_at_accept():
    deadlines = Deadlines(0.0, Timing())
    assert deadlines.e2e_end == 570
    assert deadlines.upstream_abs == 540
    assert deadlines.latest_start == 480
    assert deadlines.header_end == 30
    assert deadlines.body_end(0.5) == 60.5
    assert deadlines.body_end(470) == 480, "every pre-upstream phase is capped by the latest start"


def test_o3_4_a_late_start_still_ends_at_t0_plus_540_and_answers_before_the_client_gives_up():
    """O3-4 arithmetic: a 30 s slot wait and a 1 s body still end the upstream at 540."""
    timing = Timing()
    deadlines = Deadlines(0.0, timing)
    upstream_starts = 30 + 1
    assert deadlines.upstream_abs - upstream_starts == 509
    assert deadlines.upstream_abs + timing.custody_reserve <= deadlines.e2e_end < timing.client_timeout
    # The negative control, SV-013's relative deadline measured from connect:
    relative_end = upstream_starts + 540
    assert relative_end + 50 == 621 > timing.client_timeout
    assert 30 + 540 + 50 == 620 > 600, "the review's literal check"


def test_an_inconsistent_profile_is_refused_at_startup(monkeypatch, tmp_path):
    assert timing_problems(Timing()) == []
    assert timing_problems(SHORT) == []
    assert timing_problems(Timing(client_timeout=100.0)), "40 s of upstream < 60 + 30"
    assert timing_problems(Timing(tick=0)), "a non-positive value"
    monkeypatch.setattr(recorder_module, "TRANSCRIPTS_DIR", tmp_path)
    monkeypatch.setattr(recorder_module, "TIMING", Timing(client_timeout=100.0))
    assert recorder_module.main() == 1


# ---------------------------------------------------------------------------
# The forward check and the custody overrun, on a fake clock
# ---------------------------------------------------------------------------
class ClockOps(FileOps):
    """Real file calls; named writes and data syncs move the fake clock."""

    def __init__(self, clock: FakeClock, on_write: dict, on_sync: dict) -> None:
        self.clock = clock
        self.on_write = on_write  # file name -> absolute time to set, once
        self.on_sync = on_sync  # file name -> seconds to advance, once
        self.names: dict[int, str] = {}

    def open(self, path, flags, mode):
        fd = super().open(path, flags, mode)
        self.names[fd] = path.rsplit("/", 1)[-1]
        return fd

    def write(self, fd, data):
        target = self.on_write.pop(self.names.get(fd), None)
        if target is not None:
            self.clock.set(target)
        return super().write(fd, data)

    def fdatasync(self, fd):
        step = self.on_sync.pop(self.names.get(fd), None)
        if step is not None:
            self.clock.advance(step)
        super().fdatasync(fd)


def fake_clock_rig(make_rig, monkeypatch, on_write=None, on_sync=None):
    clock = FakeClock(0.0)
    monkeypatch.setattr(recorder_module, "CLOCK", clock)
    rig = make_rig(tk=10_000, g=10_000)
    store = RecordStore(rig.root / "transcripts", ops=ClockOps(clock, on_write or {}, on_sync or {}))
    rig.recorder.state.store = store
    return rig, clock, store


def test_a_request_past_its_latest_start_after_the_open_is_refused_before_admission(make_rig, monkeypatch):
    """O3-4 variant: a stall in the open append leaves the request at t0 + 481 > 480."""
    rig, clock, store = fake_clock_rig(make_rig, monkeypatch, on_write={"events.jsonl": 481.0})
    try:
        status, _headers, payload = rig.post(chat())
        assert status == 503 and json.loads(payload)["error"]["code"] == "deadline_insufficient"
        (close,) = rig.closes()
        assert close["outcome"] == "deadline_insufficient" and "usage_class" not in close
        assert close["elapsed_s"] == 481.0 and close["deadline_overrun"] is False
        assert [e["event"] for e in rig.events()] == ["open", "close"], "the open is on record"
        assert rig.upstream.requests == []
        assert rig.budget.snapshot(SLUG)["requests_used"] == 0
    finally:
        store.close()


def test_a_request_exactly_at_its_latest_start_still_goes(make_rig, monkeypatch):
    rig, clock, store = fake_clock_rig(make_rig, monkeypatch, on_write={"events.jsonl": 480.0})
    try:
        assert rig.post(chat())[0] == 200
    finally:
        store.close()


def test_o3_5_a_custody_stall_is_reported_not_hidden(make_rig, monkeypatch):
    """O3-5: upstream done at 530, the transcript's data sync stalls 70 s, the client has gone.

    The answer is recorded, not withheld for being late; the close says it
    was ready at 600, 70 s of it custody, past the 570 budget.
    """
    rig, clock, store = fake_clock_rig(
        make_rig, monkeypatch, on_sync={"agent_life_transcript.jsonl": 70.0}
    )
    rig.upstream.respond = lambda request: (clock.set(530.0), stub_reply(completion()))[1]
    body = chat()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(rig.socket))
    sock.sendall(f"POST {ROUTE} HTTP/1.1\r\nHost: x\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
    sock.close()  # the client gave up
    try:
        (close,) = rig.closes(timeout=10)
        assert close["outcome"] == "ok" and close["recorded"] == "durable"
        assert close["relayed"] is False
        assert close["elapsed_s"] == 600.0 and close["custody_s"] == 70.0
        assert close["deadline_overrun"] is True
        assert close["usage_class"] == "known" and close["charged_tokens"] == 30
        assert len(rig.transcript()) == 1
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Real sockets on a short profile
# ---------------------------------------------------------------------------
@pytest.fixture
def short(monkeypatch):
    monkeypatch.setattr(recorder_module, "TIMING", SHORT)
    return SHORT


def test_o3_4_a_silent_upstream_is_cut_at_the_absolute_deadline(make_rig, short):
    """Scaled O3-4: the upstream never answers; the client gets 502 by t0 + 3.4 s (+ tick)."""
    rig = make_rig()
    rig.upstream.gate = threading.Event()  # never set until teardown
    request = chat()
    started = time.monotonic()
    status, _headers, payload = rig.post(request)
    waited = time.monotonic() - started
    assert status == 502 and json.loads(payload)["error"]["code"] == "upstream_transport"
    assert "deadline" in json.loads(payload)["error"]["message"]
    assert short.upstream_offset - 0.05 <= waited <= short.upstream_offset + short.tick + SLACK
    assert waited < short.client_timeout
    (close,) = rig.closes()
    assert close["outcome"] == "upstream_transport" and close["usage_class"] == "unknown"
    assert close["charged_tokens"] == len(request) // 4 and close["deadline_overrun"] is False
    assert rig.transcript() == [], "no success line"


def test_o3_4_a_slot_wait_does_not_move_the_upstream_deadline(make_rig, short):
    """The upstream phase starts after a 0.4 s slot wait and still ends at t0 + 3.4 s, not later.

    The wait is shorter than the 0.6 s body deadline, as the deployed 30 s wait
    is shorter than its 60 s: the body deadline counts from header completion,
    so a wait longer than it would end the request as 408 body_deadline.
    """
    rig = make_rig()
    rig.upstream.gate = threading.Event()
    rig.recorder.state.slots = threading.BoundedSemaphore(1)
    rig.recorder.state.slots.acquire()
    threading.Timer(0.4, rig.recorder.state.slots.release).start()
    started = time.monotonic()
    status, _headers, _payload = rig.post(chat())
    waited = time.monotonic() - started
    assert status == 502
    assert short.upstream_offset - 0.05 <= waited <= short.upstream_offset + short.tick + SLACK


def test_r_b5_a_dripping_chunked_upstream_is_cut_at_the_deadline(make_rig, short, monkeypatch):
    """R-B5: one byte per 0.1 s keeps every recv under its timeout; the watchdog ends it."""
    rig = make_rig()
    stop = threading.Event()

    def drip(sock):
        sock.sendall(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n")
        while not stop.is_set():
            sock.sendall(b"1\r\nx\r\n")
            time.sleep(0.1)

    upstream = RawUpstream(rig.root / "drip.sock", drip)
    monkeypatch.setattr(recorder_module, "UPSTREAM_SOCKET", str(upstream.path))
    try:
        started = time.monotonic()
        status, _headers, _payload = rig.post(chat())
        waited = time.monotonic() - started
    finally:
        stop.set()
        upstream.stop()
    assert status == 502
    assert waited <= short.upstream_offset + short.tick + SLACK
    (close,) = rig.closes()
    assert close["outcome"] == "upstream_transport" and close["usage_class"] == "unknown"


def drip_and_read(sock: socket.socket, first: bytes, drip: bytes) -> tuple[bytes, float]:
    """Send `first`, then one byte of `drip` every 0.1 s, while reading the reply."""
    stop = threading.Event()

    def dripper():
        for byte in drip:
            if stop.is_set():
                return
            try:
                sock.sendall(bytes([byte]))
            except OSError:
                return
            time.sleep(0.1)

    sock.sendall(first)
    started = time.monotonic()
    thread = threading.Thread(target=dripper)
    thread.start()
    reply = b""
    answered = None
    try:
        sock.settimeout(5)
        while True:  # the response says Connection: close; read it to the end
            chunk = sock.recv(4096)
            if answered is None and chunk:
                answered = time.monotonic() - started
            if not chunk:
                break
            reply += chunk
    finally:
        stop.set()
        thread.join(5)
        sock.close()
    return reply, answered


def test_r_b2_a_dripping_body_gets_a_408_within_its_deadline(make_rig, short):
    """R-B2: Content-Length 100, 10 bytes, then a byte per 0.1 s; the body phase ends it."""
    rig = make_rig()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(rig.socket))
    head = f"POST {ROUTE} HTTP/1.1\r\nHost: x\r\nContent-Length: 100\r\n\r\n".encode()
    reply, answered = drip_and_read(sock, head + b"x" * 10, b"y" * 60)
    assert reply.startswith(b"HTTP/1.1 408") and b"body_deadline" in reply
    assert short.body - 0.05 <= answered <= short.body + short.tick + SLACK
    (close,) = rig.closes()
    assert close["outcome"] == "body_deadline"
    assert not [e for e in rig.events() if e["event"] == "open"]
    assert rig.upstream.requests == []


def test_dripping_headers_get_a_canned_408_and_no_invented_request(make_rig, short):
    """The request line never completes: a 408, a counter, an overdue diagnostic -- no close."""
    rig = make_rig()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(rig.socket))
    reply, answered = drip_and_read(sock, b"P", b"OST /api/v1/chat/completions HTTP/1.1")
    assert reply.startswith(b"HTTP/1.1 408") and b"header_deadline" in reply
    assert answered <= short.header + short.tick + SLACK
    time.sleep(0.2)
    assert rig.events() == [], "a request that was never parsed is not closed"
    deadline = time.monotonic() + 5
    overdue = []
    while not overdue and time.monotonic() < deadline:
        overdue = [
            d for d in read_jsonl(rig.root / "transcripts" / "recorder.jsonl")
            if d.get("event") == "request_overdue" and d.get("phase") == "header"
        ]
        time.sleep(0.05)
    assert overdue, "the watchdog's diagnostic reached recorder.jsonl through the writer"


# ---------------------------------------------------------------------------
# The watchdog itself
# ---------------------------------------------------------------------------
@pytest.fixture
def watchdog():
    clock = FakeClock(0.0)
    dog = Watchdog(clock=clock, tick=0.05, queue_size=8)
    dog.clock = clock
    yield dog
    dog.stop()


def test_a_due_entry_fires_and_shuts_its_socket_and_a_cancelled_one_does_not(watchdog):
    a, b = socket.socketpair()
    c, d = socket.socketpair()
    try:
        fired = watchdog.register(a, 1.0, "r1", "body", socket.SHUT_RD)
        spared = watchdog.register(c, 1.0, "r2", "body", socket.SHUT_RD)
        assert watchdog.cancel(spared) is False
        watchdog.clock.set(2.0)
        watchdog.fire_due()
        a.settimeout(1)
        assert a.recv(10) == b"", "the read side was shut"
        assert fired.fired and watchdog.cancel(fired) is True
        d.sendall(b"ok")
        c.settimeout(1)
        assert c.recv(10) == b"ok", "a cancelled entry never touches its socket"
        assert watchdog.queue[0]["event"] == "request_overdue" and watchdog.queue[0]["phase"] == "body"
        assert watchdog.counts()["active"] == 0
    finally:
        for sock in (a, b, c, d):
            sock.close()


def test_a_stale_entry_never_reaches_a_reused_descriptor(watchdog):
    """Owners cancel before closing; a new socket on the old number is untouched."""
    a, b = socket.socketpair()
    entry = watchdog.register(a, 1.0, "r1", "upstream", socket.SHUT_RDWR)
    old_fd = a.fileno()
    watchdog.cancel(entry)
    a.close()
    b.close()
    c, d = socket.socketpair()
    try:
        reused = old_fd in (c.fileno(), d.fileno())
        watchdog.clock.set(5.0)
        watchdog.fire_due()
        d.sendall(b"still here")
        c.settimeout(1)
        assert c.recv(20) == b"still here"
        c.sendall(b"and here")
        d.settimeout(1)
        assert d.recv(20) == b"and here"
        assert not entry.fired
        assert reused or True  # the number is usually reused; the property holds either way
    finally:
        c.close()
        d.close()


def test_cancelled_entries_do_not_pile_up_behind_long_deadlines(watchdog):
    a, b = socket.socketpair()
    try:
        entries = [watchdog.register(a, 1_000.0, f"r{i}", "upstream", socket.SHUT_RDWR) for i in range(500)]
        for entry in entries:
            watchdog.cancel(entry)
        counts = watchdog.counts()
        assert counts["active"] == 0 and counts["heap"] <= 200
    finally:
        a.close()
        b.close()


def test_a_deadline_that_fires_during_a_tls_wrap_shuts_the_new_socket_too(watchdog):
    a, b = socket.socketpair()
    c, d = socket.socketpair()
    try:
        entry = watchdog.register(a, 1.0, "r1", "upstream", socket.SHUT_RDWR)
        watchdog.clock.set(2.0)
        watchdog.fire_due()
        watchdog.rebind(entry, c)
        c.settimeout(1)
        assert c.recv(10) == b""
        watchdog.cancel(entry)
    finally:
        for sock in (a, b, c, d):
            sock.close()


def test_o3_6_a_blocked_diagnostic_writer_never_delays_a_deadline():
    """O3-6: the writer is stuck on recorder.jsonl; three deadlines still shut their sockets.

    DIAG_QUEUE 2. The writer holds one earlier diagnostic and blocks; the three
    overdue records find room for two: queue 2, dropped 1. Released, a failed
    write keeps the dropped count; the next readable one reports and clears it.
    """
    clock = FakeClock(0.0)
    release = threading.Event()
    written: list[dict] = []
    results = iter([True, False, True, True])

    class Result:
        def __init__(self, readable):
            self.readable = readable

    def writer(record):
        if record.get("event") == "earlier":
            release.wait(10)
        written.append(record)
        return Result(next(results))

    dog = Watchdog(clock=clock, tick=0.05, queue_size=2, writer=writer)
    pairs = [socket.socketpair() for _ in range(3)]
    try:
        dog.put_nowait({"event": "earlier"})
        deadline = time.monotonic() + 5
        while dog.counts()["queued"]:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        entries = [dog.register(a, 1.0, f"r{i}", "upstream", socket.SHUT_RDWR) for i, (a, _b) in enumerate(pairs)]
        clock.set(1.0)
        dog.fire_due()
        for a, _b in pairs:
            a.settimeout(1)
            assert a.recv(10) == b"", "shut while the writer is blocked"
        assert all(entry.fired for entry in entries)
        counts = dog.counts()
        assert (counts["queued"], counts["dropped"]) == (2, 1)
        release.set()
        deadline = time.monotonic() + 5
        while len(written) < 3:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert [w["event"] for w in written] == ["earlier", "request_overdue", "request_overdue"]
        assert written[1]["diag_dropped"] == 1, "reported with the first later diagnostic"
        assert written[2]["diag_dropped"] == 1, "that write failed, so the count stood"
        deadline = time.monotonic() + 5
        while dog.counts()["dropped"]:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        for entry in entries:
            dog.cancel(entry)
    finally:
        release.set()
        dog.stop()
        for a, b in pairs:
            a.close()
            b.close()
    assert dog._writer_thread is None or (dog._writer_thread.join(5) or not dog._writer_thread.is_alive())
