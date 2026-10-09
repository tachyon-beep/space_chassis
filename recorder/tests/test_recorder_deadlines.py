"""An absolute deadline per request, ported from the SV workstream (O3), per request not per connection.

Every request's clock starts when its handler starts. However late the upstream phase begins, it
ends at t0 + upstream: a timer shuts the upstream socket, so a silent upstream and one that drips a
byte inside every recv timeout are both cut. A shut socket can read as a clean end of body, so the
`fired` flag, not the read, decides: a cut buffered reply is a 502, and a cut stream gets no
chunked terminator. A request that never reached the upstream is refunded; one that did is charged.
"""

# ruff: noqa: F811 -- the fixtures are imported from test_proxy by name, and pytest injects them.

import contextlib
import json
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time

import proxy
import pytest
from test_proxy import (  # noqa: F401 -- fixtures, by name
    _BufferedResponse,
    _connect,
    _events,
    _post,
    _raw_request,
    _read_message,
    _used_tokens,
    registry,
    stream_env,
    stream_factory,
    transcripts,
    upstream,
)

RECORDER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOLERANCE = 0.25 + 1.0


class _Upstream(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _serve(behaviour):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(30)
            with contextlib.suppress(OSError):
                behaviour(self.request)

    server = _Upstream(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _read_request(conn):
    data = b""
    while b"\r\n\r\n" not in data:
        piece = conn.recv(65536)
        if not piece:
            return
        data += piece


def silent(conn):
    _read_request(conn)
    time.sleep(20)


def drip_content_length(conn):
    _read_request(conn)
    conn.sendall(
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 100000\r\n\r\n"
    )
    for _ in range(80):
        conn.sendall(b" ")
        time.sleep(0.5)


def drip_chunked(conn):
    _read_request(conn)
    conn.sendall(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n"
    )
    for _ in range(80):
        conn.sendall(b"1\r\n \r\n")
        time.sleep(0.5)


def hang_up(conn):
    _read_request(conn)


@pytest.fixture
def real_upstream(monkeypatch):
    """Point declared streams at a local upstream that behaves as asked; restore forward_open."""
    servers = []

    def make(behaviour):
        server = _serve(behaviour)
        servers.append(server)
        host, port = server.server_address
        monkeypatch.setenv("STREAM_UPSTREAM_URL", f"http://{host}:{port}/api/v1/chat/completions")
        return server

    monkeypatch.setattr(proxy, "forward_open", proxy._real_forward_open)
    yield make
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture
def short(monkeypatch):
    timing = proxy.Timing(
        client_timeout=600, margin=30, upstream=2.0, latest_start=1.0, operation=1.0
    )
    monkeypatch.setattr(proxy, "TIMING", timing)
    return timing


class _Clock:
    def __init__(self, *readings):
        self.readings = list(readings)

    def __call__(self):
        return self.readings.pop(0) if len(self.readings) > 1 else self.readings[0]


def test_the_deadlines_count_from_the_start_of_the_request():
    timing = proxy.Timing()
    assert (timing.client_timeout, timing.margin, timing.upstream, timing.latest_start) == (
        600,
        30,
        540,
        480,
    )
    deadline = proxy.Deadline(timing, clock=_Clock(100.0, 100.0))
    assert deadline.t0 == 100.0
    assert deadline.left() == 540.0
    assert deadline.may_start()


def test_a_late_start_still_ends_at_t0_plus_the_upstream_deadline():
    timing = proxy.Timing()
    late = proxy.Deadline(timing, clock=_Clock(0.0, 470.0, 470.0, 470.0))
    assert late.may_start()
    assert late.left() == 70.0
    assert late.operation_timeout() == 60.0
    near = proxy.Deadline(timing, clock=_Clock(0.0, 530.0, 530.0))
    assert near.left() == 10.0
    assert near.operation_timeout() <= 10.0 + proxy.OPERATION_GRACE
    assert not proxy.Deadline(timing, clock=_Clock(0.0, 481.0)).may_start()
    assert proxy.Deadline(timing, clock=_Clock(0.0, 480.0)).may_start()


def test_an_inconsistent_timing_profile_is_refused_at_startup():
    assert proxy.timing_problems(proxy.Timing()) == []
    for bad in (
        proxy.Timing(latest_start=540),
        proxy.Timing(upstream=580),
        proxy.Timing(operation=600),
        proxy.Timing(upstream=float("nan")),
        proxy.Timing(margin=-1),
    ):
        assert proxy.timing_problems(bad), bad
    env = {"PATH": os.environ["PATH"], "OPENROUTER_API_KEY": "sk-x", "RECORDER_LATEST_START": "999"}
    result = subprocess.run(
        [sys.executable, "-c", "import proxy; proxy.main()"],
        cwd=RECORDER_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert "timing" in (result.stdout + result.stderr)


def test_a_request_past_its_latest_start_is_refused_before_contact(
    stream_factory, upstream, registry, transcripts, monkeypatch
):
    path = stream_factory(max_tokens=400)
    calls = []
    upstream["response"] = lambda: calls.append(1) or _BufferedResponse(b"{}")
    monkeypatch.setattr(proxy, "DEADLINE_CLOCK", _Clock(0.0, 481.0))
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 503
    assert "deadline_insufficient" in response.json()["error"]["message"]
    assert calls == []
    assert _used_tokens(registry) == 0
    assert registry.state(streams_enabled=True)["streams"]["aux"]["budget"]["used"] == 0


def test_a_request_exactly_at_its_latest_start_still_goes(stream_factory, upstream, monkeypatch):
    path = stream_factory()
    monkeypatch.setattr(proxy, "DEADLINE_CLOCK", _Clock(0.0, 480.0))
    assert _post(path, {"model": "m", "messages": []}).status_code == 200


def _timed_post(path, payload):
    started = time.monotonic()
    response = _post(path, payload)
    return response, time.monotonic() - started


def test_a_silent_upstream_is_cut_at_the_absolute_deadline(
    stream_factory, real_upstream, registry, transcripts, short, monkeypatch
):
    # The default operation timeout, so the deadline, not a recv timeout, is what ends it.
    monkeypatch.setattr(proxy, "TIMING", proxy.Timing(upstream=2.0, latest_start=1.0, operation=60))
    real_upstream(silent)
    path = stream_factory(max_tokens=400)
    response, waited = _timed_post(path, {"model": "m", "messages": []})
    assert response.status_code == 502
    assert "upstream_deadline" in response.json()["error"]["message"]
    assert short.upstream - 0.05 <= waited <= short.upstream + TOLERANCE
    assert _used_tokens(registry) >= 400, "a request that reached the upstream is charged"


def test_a_dripping_upstream_is_cut_at_the_deadline_though_no_recv_times_out(
    stream_factory, real_upstream, registry, short
):
    real_upstream(drip_content_length)
    path = stream_factory(max_tokens=400)
    response, waited = _timed_post(path, {"model": "m", "messages": []})
    assert response.status_code == 502
    assert waited <= short.upstream + TOLERANCE
    assert _used_tokens(registry) >= 400


@pytest.mark.parametrize(
    "behaviour", [drip_content_length, drip_chunked], ids=["length", "chunked"]
)
def test_a_dripping_stream_is_cut_without_a_terminator(
    stream_factory, real_upstream, short, behaviour
):
    real_upstream(behaviour)
    path = stream_factory()
    client = _connect(path)
    started = time.monotonic()
    client.sendall(_raw_request({"model": "m", "messages": [], "stream": True}))
    received = b""
    client.settimeout(10)
    while True:
        try:
            piece = client.recv(65536)
        except OSError:
            break
        if not piece:
            break
        received += piece
    waited = time.monotonic() - started
    client.close()
    assert waited <= short.upstream + TOLERANCE
    assert b"200" in received.split(b"\r\n", 1)[0]
    assert not received.endswith(b"0\r\n\r\n"), "a cut stream must not look complete"


def test_an_upstream_that_never_connected_is_refunded(
    stream_factory, real_upstream, registry, monkeypatch
):
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    monkeypatch.setattr(proxy, "forward_open", proxy._real_forward_open)
    monkeypatch.setenv("STREAM_UPSTREAM_URL", f"http://127.0.0.1:{port}/api/v1/chat/completions")
    path = stream_factory(max_tokens=400)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 500
    assert response.json()["error"]["message"] == "proxy error"
    assert _used_tokens(registry) == 0
    assert registry.state(streams_enabled=True)["streams"]["aux"]["budget"]["used"] == 0


def test_an_upstream_that_failed_after_connecting_keeps_its_reservation(
    stream_factory, real_upstream, registry
):
    real_upstream(hang_up)
    path = stream_factory(max_tokens=400)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 500
    assert _used_tokens(registry) >= 400


def test_the_deadline_is_per_request_on_a_kept_alive_connection(
    stream_factory, upstream, transcripts
):
    path = stream_factory(max_tokens=10)
    client = _connect(path)
    reader = client.makefile("rb")
    client.sendall(_raw_request({"model": "m", "messages": []}))
    assert _read_message(reader)[0].endswith("200 OK")
    time.sleep(1.2)
    client.sendall(_raw_request({"model": "m", "messages": []}))
    assert _read_message(reader)[0].endswith("200 OK")
    client.close()
    closes = [e for e in _events(transcripts) if e["event"] == "close"]
    assert len(closes) == 2
    assert all(e["elapsed_s"] < 1.0 for e in closes), closes


def test_no_timer_outlives_its_request(stream_factory, upstream):
    path = stream_factory(max_tokens=10)
    for _ in range(3):
        assert _post(path, {"model": "m", "messages": []}).status_code == 200
    time.sleep(0.1)
    assert not [t for t in threading.enumerate() if t.name.startswith("recorder-deadline")]
    assert json  # the module is used by the helpers above
