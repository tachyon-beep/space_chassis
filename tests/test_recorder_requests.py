"""The recorder's handler, end to end, against an upstream the test controls.

The recorder runs in this process -- a real listener on a real unix socket --
and forwards to a fake upstream, also on a unix socket, that keeps exactly
what it received: the header lines as sent, the body bytes, and how many
requests reached it. Nothing here starts a container, calls a model provider
or opens a port beyond loopback, and every server the fixture starts it also
stops.

The expected values are the SV-013 dossier's fixtures (section 3.4: R-C7, the
end-to-end R-A rows, R-H1...R-H7, R-B1, R-B3) written before this code; the
assertions read the record the recorder left, not its internals, wherever the
record can say it.
"""

from __future__ import annotations

import http.client
import json
import shutil
import socket
import socketserver
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest
import recorder as recorder_module
from recorder import AgentState, Budget, Recorder

SLUG = "otter"
ROUTE = "/api/v1/chat/completions"
# Synthetic, and only ever sent to the fake upstream below.
RECORDER_KEY = "RECORDER-DUMMY-KEY"


def stub_reply(body: dict, status: int = 200) -> tuple[int, dict, bytes]:
    return status, {"Content-Type": "application/json"}, json.dumps(body).encode()


def completion(total: int = 30) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": total - 10, "completion_tokens": 10, "total_tokens": total},
    }


class FakeUpstream:
    """An upstream on a unix socket that records each request and answers on cue."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.requests: list[dict] = []
        self.respond = lambda request: stub_reply(completion())
        self.gate: threading.Event | None = None
        upstream = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_POST(self):  # noqa: N802 -- base class API
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                request = {
                    "path": self.path,
                    "headers": list(self.headers.items()),
                    "body": body,
                }
                upstream.requests.append(request)
                if upstream.gate is not None:
                    upstream.gate.wait(10)
                reply = upstream.respond(request)
                if reply is None:
                    # Read the request, then hang up without a status line.
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                status, headers, payload = reply
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True

        self.server = Server(str(path), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05})
        self.thread.start()

    def stop(self) -> None:
        if self.gate is not None:
            self.gate.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)


class Rig:
    def __init__(self, root: Path, budget: Budget, recorder: Recorder, upstream: FakeUpstream):
        self.root = root
        self.budget = budget
        self.recorder = recorder
        self.upstream = upstream
        self.socket = recorder.socket_path
        self.dir = root / "transcripts" / SLUG

    def post(
        self,
        body: bytes,
        headers: dict | None = None,
        path: str = ROUTE,
        method: str = "POST",
        raw_headers: list[tuple[str, str]] | None = None,
    ) -> tuple[int, dict, bytes]:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(15)
        sock.connect(str(self.socket))
        connection = http.client.HTTPConnection("localhost", timeout=15)
        connection.sock = sock
        try:
            if raw_headers is None:
                connection.request(method, path, body=body, headers=headers or {})
            else:
                connection.putrequest(method, path, skip_accept_encoding=True)
                for name, value in raw_headers:
                    connection.putheader(name, value)
                connection.endheaders(body)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def events(self) -> list[dict]:
        return read_jsonl(self.dir / "events.jsonl")

    def transcript(self) -> list[dict]:
        return read_jsonl(self.dir / "agent_life_transcript.jsonl")

    def raw_record(self) -> str:
        text = ""
        for path in sorted((self.root / "transcripts").rglob("*.jsonl")):
            text += path.read_text(encoding="utf-8", errors="replace")
        return text

    def closes(self, count: int = 1, timeout: float = 5.0) -> list[dict]:
        """The `close` events, once there are `count` of them: they follow the relay."""
        deadline = time.monotonic() + timeout
        while True:
            closes = [e for e in self.events() if e.get("event") == "close"]
            if len(closes) >= count or time.monotonic() > deadline:
                return closes
            time.sleep(0.02)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


@pytest.fixture
def make_rig(monkeypatch):
    """Build a rig; the limits are the dossier fixture's unless a test says otherwise."""
    built: list[Rig] = []
    roots: list[Path] = []

    def build(rq: int = 3, tk: int = 100, g: int = 150, upstream_socket: str | None = None) -> Rig:
        # A short path: a unix socket's address is capped near a hundred bytes.
        root = Path(tempfile.mkdtemp(prefix="sv16-", dir="/tmp"))
        roots.append(root)
        for name in ("sock", "transcripts", "markers"):
            (root / name).mkdir()
        upstream = FakeUpstream(root / "up.sock")
        monkeypatch.setattr(recorder_module, "SOCKET_DIR", root / "sock")
        monkeypatch.setattr(recorder_module, "TRANSCRIPTS_DIR", root / "transcripts")
        monkeypatch.setattr(recorder_module, "REFUSE_DIR", root / "markers")
        monkeypatch.setattr(
            recorder_module,
            "UPSTREAM_SOCKET",
            upstream_socket if upstream_socket is not None else str(upstream.path),
        )
        monkeypatch.setenv("LLM_BASE_URL", "http://upstream.invalid/v1")
        monkeypatch.setenv("LLM_API_KEY", RECORDER_KEY)
        monkeypatch.delenv("UPSTREAM_STREAMING", raising=False)
        budget = Budget(g)
        assert budget.register(SLUG, rq, tk)
        recorder = Recorder(AgentState(SLUG, root / "transcripts"), budget, "")
        recorder.start()
        deadline = time.monotonic() + 10
        while recorder.server is None or not recorder.socket_path.exists():
            assert time.monotonic() < deadline, "the recorder never opened its socket"
            time.sleep(0.01)
        rig = Rig(root, budget, recorder, upstream)
        built.append(rig)
        return rig

    yield build
    for rig in built:
        rig.recorder.stop()
        rig.recorder.join(5)
        rig.upstream.stop()
    for root in roots:
        shutil.rmtree(root, ignore_errors=True)


def chat(**extra) -> bytes:
    body = {"model": "stub", "messages": [{"role": "user", "content": "hi"}]}
    body.update(extra)
    return json.dumps(body, separators=(",", ":")).encode()


def one_close_each(events: list[dict]) -> None:
    ids = [e["id"] for e in events if e.get("event") == "close"]
    assert len(ids) == len(set(ids)), f"a request was closed twice: {ids}"


# ---------------------------------------------------------------------------
# R-A2: the handler and the budget
# ---------------------------------------------------------------------------
def test_a_turn_is_opened_charged_at_its_actual_and_closed_once(make_rig):
    rig = make_rig(tk=1000, g=1000)
    body = chat()
    status, _headers, payload = rig.post(body)
    assert status == 200 and json.loads(payload)["usage"]["total_tokens"] == 30
    (close,) = rig.closes()
    (opened,) = [e for e in rig.events() if e["event"] == "open"]
    assert opened["id"] == close["id"]
    assert opened["bytes_in"] == opened["bytes_forwarded"] == len(body)
    assert opened["estimate"] == close["estimate"] == len(body) // 4
    assert close["outcome"] == "ok" and close["status"] == 200
    assert close["usage_class"] == "known" and close["charged_tokens"] == 30
    assert close["usage"]["total_tokens"] == 30
    assert close["relayed"] is True and close["upstream_status"] == 200
    assert isinstance(close["duration_seconds"], float)
    snap = rig.budget.snapshot(SLUG)
    assert (snap["requests_used"], snap["tokens_used"], snap["live"]) == (1, 30, 0)
    assert len(rig.transcript()) == 1


def test_a_refused_connection_is_closed_once_and_the_request_refunded(make_rig, monkeypatch):
    """R-C7 / L5. The base code wrote two `close` events for this one request."""
    rig = make_rig()
    # Bound but never listening: connect() is refused outright.
    deaf = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    deaf.bind(str(rig.root / "deaf.sock"))
    monkeypatch.setattr(recorder_module, "UPSTREAM_SOCKET", str(rig.root / "deaf.sock"))
    try:
        status, _headers, payload = rig.post(chat())
    finally:
        deaf.close()
    assert status == 502
    assert json.loads(payload)["error"]["code"] == "upstream_connect"
    (close,) = rig.closes()
    time.sleep(0.1)
    assert len(rig.closes()) == 1
    assert close["outcome"] == "upstream_connect" and close["status"] == 502
    assert close["usage_class"] == "none" and close["charged_tokens"] == 0
    assert close["usage"] is None
    snap = rig.budget.snapshot(SLUG)
    assert (snap["requests_used"], snap["tokens_used"], snap["live"]) == (0, 0, 0)
    assert rig.upstream.requests == []


def test_a_failure_after_forwarding_keeps_the_estimate_charged(make_rig):
    """The upstream read the request and hung up: provider work is unknown, never "none"."""
    rig = make_rig()
    rig.upstream.respond = lambda request: None
    body = chat()
    status, _headers, _payload = rig.post(body)
    assert status == 502
    (close,) = rig.closes()
    assert close["outcome"] == "upstream_transport"
    assert close["usage_class"] == "unknown" and close["charged_tokens"] == len(body) // 4
    snap = rig.budget.snapshot(SLUG)
    assert (snap["requests_used"], snap["tokens_used"], snap["live"]) == (1, len(body) // 4, 0)
    assert len(rig.upstream.requests) == 1


def test_an_estimate_too_large_for_the_socket_is_refused_before_the_upstream(make_rig):
    """R-A1 end to end: an open, a 429 close, and no upstream call."""
    rig = make_rig(tk=10)
    status, _headers, payload = rig.post(chat())
    assert status == 429
    assert "can never fit" in json.loads(payload)["error"]["message"]
    events = rig.events()
    assert [e["event"] for e in events] == ["open", "close"]
    assert events[1]["outcome"] == "estimate_exceeds_limit"
    assert "usage_class" not in events[1], "a refused request was never charged"
    assert rig.upstream.requests == []


def test_a_closed_socket_pool_refuses_with_the_text_it_always_had(make_rig):
    rig = make_rig(rq=0)
    status, _headers, payload = rig.post(chat())
    assert status == 429
    message = json.loads(payload)["error"]["message"]
    assert message.startswith("rate limited: at most 0 request(s) per hour on this socket")
    (close,) = rig.closes()
    assert close["refusal"] == message and close["outcome"] == "requests_closed"
    assert rig.upstream.requests == []


def test_known_usage_is_settled_before_a_transcript_failure(make_rig):
    """The transcript append raises; the turn was paid for, and the budget says so."""
    rig = make_rig(tk=1000, g=1000)
    (rig.dir / "agent_life_transcript.jsonl").mkdir()
    status, _headers, payload = rig.post(chat())
    assert status == 500
    assert json.loads(payload)["error"]["code"] == "internal_error"
    assert b"choices" not in payload, "a response without a record was relayed"
    (close,) = rig.closes()
    assert close["outcome"] == "internal_error" and close["status"] == 500
    assert close["usage_class"] == "known" and close["charged_tokens"] == 30
    assert close["upstream_status"] == 200
    snap = rig.budget.snapshot(SLUG)
    assert (snap["tokens_used"], snap["live"]) == (30, 0)
    (rig.dir / "agent_life_transcript.jsonl").rmdir()
    assert rig.post(chat())[0] == 200, "the failed request kept its slot"


def test_a_client_gone_before_the_relay_leaves_a_settled_record(make_rig):
    """The relay fails; the transcript and the accounting do not depend on it."""
    rig = make_rig(tk=1000, g=1000)
    rig.upstream.gate = threading.Event()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(rig.socket))
    body = chat()
    sock.sendall(
        f"POST {ROUTE} HTTP/1.1\r\nHost: x\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body
    )
    deadline = time.monotonic() + 5
    while not rig.upstream.requests:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    sock.close()
    rig.upstream.gate.set()
    (close,) = rig.closes()
    assert close["outcome"] == "ok" and close["relayed"] is False
    assert close["usage_class"] == "known" and close["charged_tokens"] == 30
    assert len(rig.transcript()) == 1
    assert rig.budget.snapshot(SLUG)["live"] == 0


def test_an_exception_before_sending_cancels_the_reservation(make_rig, monkeypatch):
    rig = make_rig()

    def broken() -> str:
        raise RuntimeError("secret-bearing text https://example.invalid/?key=x")

    monkeypatch.setattr(recorder_module, "upstream_key", broken)
    status, _headers, payload = rig.post(chat())
    assert status == 500
    assert "secret-bearing" not in payload.decode()
    (close,) = rig.closes()
    assert close["outcome"] == "internal_error" and close["usage_class"] == "none"
    assert "secret-bearing" not in rig.raw_record()
    snap = rig.budget.snapshot(SLUG)
    assert (snap["requests_used"], snap["tokens_used"], snap["live"]) == (0, 0, 0)
    assert rig.upstream.requests == []


def test_an_exception_after_sending_settles_at_the_estimate(make_rig, monkeypatch):
    rig = make_rig()

    def broken(payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(recorder_module, "decode_payload", broken)
    body = chat()
    status, _headers, _payload = rig.post(body)
    assert status == 500
    (close,) = rig.closes()
    assert close["outcome"] == "internal_error"
    assert close["usage_class"] == "unknown" and close["charged_tokens"] == len(body) // 4
    snap = rig.budget.snapshot(SLUG)
    assert (snap["requests_used"], snap["live"]) == (1, 0)


def test_a_socket_with_no_free_slot_refuses_without_opening(make_rig, monkeypatch):
    rig = make_rig(tk=1000, g=1000)
    monkeypatch.setattr(recorder_module, "INFLIGHT_WAIT_SECONDS", 0.2)
    rig.recorder.state.slots = threading.BoundedSemaphore(1)
    rig.upstream.gate = threading.Event()
    first: dict = {}
    thread = threading.Thread(target=lambda: first.setdefault("r", rig.post(chat())))
    thread.start()
    deadline = time.monotonic() + 5
    while not rig.upstream.requests:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    status, _headers, payload = rig.post(chat())
    assert status == 429 and json.loads(payload)["error"]["code"] == "inflight"
    rig.upstream.gate.set()
    thread.join(10)
    assert first["r"][0] == 200
    closes = rig.closes(2)
    assert sorted(c["outcome"] for c in closes) == ["inflight", "ok"]
    assert len([e for e in rig.events() if e["event"] == "open"]) == 1
    one_close_each(rig.events())


def test_a_wrong_route_and_a_get_each_write_one_close_with_an_id(make_rig):
    rig = make_rig()
    assert rig.post(chat(), path="/nope")[0] == 404
    assert rig.post(b"", method="GET")[0] == 405
    closes = rig.closes(2)
    assert sorted(c["outcome"] for c in closes) == ["method_not_allowed", "not_found"]
    assert all(isinstance(c["id"], str) for c in closes)
    assert not [e for e in rig.events() if e["event"] == "open"]


def test_the_recorder_start_goes_to_its_own_file_and_bad_names_are_not_served(
    make_rig, monkeypatch
):
    """`main` is driven for one discovery pass: the loop's sleep ends the test."""
    rig = make_rig()
    monkeypatch.setenv("AGENT_SLUGS", "Bad,../x,otter")
    monkeypatch.setattr(recorder_module, "MAX_SLUGS", 0)

    class Stop(Exception):
        pass

    class Clock:
        monotonic = staticmethod(time.monotonic)
        time = staticmethod(time.time)

        @staticmethod
        def sleep(_seconds):
            raise Stop

    monkeypatch.setattr(recorder_module, "time", Clock)
    with pytest.raises(Stop):
        recorder_module.main()
    lines = read_jsonl(rig.root / "transcripts" / "recorder.jsonl")
    assert lines[0]["event"] == "recorder_start" and lines[0]["boot"] == recorder_module.BOOT
    assert sorted(line.get("reason") for line in lines[1:]) == ["max_slugs", "slug_pattern"]
    assert "Bad" not in json.dumps(lines)
    assert not (rig.root / "transcripts" / "Bad").exists()
    assert not [e for e in rig.events() if e.get("event") == "recorder_start"]
