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

import hashlib
import http.client
import json
import shutil
import socket
import socketserver
import ssl
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest
import recorder as recorder_module
from recorder import (
    AgentState,
    Budget,
    ParsedRequest,
    Recorder,
    RequestRefusal,
    parse_request,
)

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
    """An upstream that records each request and answers on cue.

    On a unix socket by default; with `path=None`, on a loopback TCP port.
    """

    def __init__(self, path: Path | None) -> None:
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

        class TCPServer(socketserver.ThreadingTCPServer):
            daemon_threads = True

        if path is None:
            self.server = TCPServer(("127.0.0.1", 0), Handler)
            self.url = "http://127.0.0.1:%d/v1" % self.server.server_address[1]
        else:
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
                connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
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

    def build(rq: int = 3, tk: int = 100, g: int = 150, network: bool = False) -> Rig:
        # A short path: a unix socket's address is capped near a hundred bytes.
        root = Path(tempfile.mkdtemp(prefix="sv16-", dir="/tmp"))
        roots.append(root)
        for name in ("sock", "transcripts", "markers"):
            (root / name).mkdir()
        upstream = FakeUpstream(None if network else root / "up.sock")
        monkeypatch.setattr(recorder_module, "SOCKET_DIR", root / "sock")
        monkeypatch.setattr(recorder_module, "TRANSCRIPTS_DIR", root / "transcripts")
        monkeypatch.setattr(recorder_module, "REFUSE_DIR", root / "markers")
        monkeypatch.setattr(
            recorder_module, "UPSTREAM_SOCKET", "" if network else str(upstream.path)
        )
        monkeypatch.setenv(
            "LLM_BASE_URL", upstream.url if network else "http://upstream.invalid/v1"
        )
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("RECORDER_FORWARD_HEADERS", raising=False)
        # The free-space preflight is exercised on its own in
        # tests/test_recorder_custody.py; here it must not depend on how full
        # the test host's /tmp happens to be.
        monkeypatch.setattr(recorder_module, "MIN_FREE_BYTES", 1)
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
    recorder_module.close_stores()
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
    rig.closes()  # the close follows the reply; wait for it rather than race it
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
    """The transcript append fails; the turn was paid for, and the budget says so.

    Since R-B4 (SV-017) this is the custody refusal `502 record_failed`; before
    it, the same failure surfaced as `500 internal_error`.
    """
    rig = make_rig(tk=1000, g=1000)
    (rig.dir / "agent_life_transcript.jsonl").mkdir()
    status, _headers, payload = rig.post(chat())
    assert status == 502
    assert json.loads(payload)["error"]["code"] == "record_failed"
    assert b"choices" not in payload, "a response without a record was relayed"
    (close,) = rig.closes()
    assert close["outcome"] == "record_failed" and close["status"] == 502
    assert close["recorded"] == "failed"
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


# ---------------------------------------------------------------------------
# R-B1: the request body, its three representations and the correlation label
# ---------------------------------------------------------------------------
R_H3 = b'{"model":"stub","messages":[{"role":"user","content":"hi"}]}'
R_H4 = b'{"model":"stub","x_chassis_correlation":"0f1e:7:1","messages":[]}'
R_H4_FORWARDED = b'{"model":"stub","messages":[]}'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_an_untouched_body_is_forwarded_byte_for_byte():
    """R-H3, against the dossier's literal length and digest."""
    assert len(R_H3) == 60
    assert sha(R_H3) == "795b56c3b951d80f6ffa8cad2e652063496a078c992da7bf8596567d501032f2"
    parsed = parse_request(R_H3, streaming=True)
    assert isinstance(parsed, ParsedRequest)
    assert parsed.forwarded is R_H3 and parsed.transformed is False
    assert max(1, len(parsed.forwarded) // 4) == 15
    assert parsed.label is None and parsed.label_invalid is None


def test_the_correlation_label_is_stripped_and_the_body_re_encoded():
    """R-H4, against the dossier's literal forwarded bytes and digest."""
    assert len(R_H4) == 65
    assert sha(R_H4).startswith("7ec0d4bb") and sha(R_H4).endswith("a7af2")
    parsed = parse_request(R_H4, streaming=True)
    assert parsed.forwarded == R_H4_FORWARDED and len(parsed.forwarded) == 30
    assert sha(parsed.forwarded) == "0d1a07f04e6f1fe940b9b125fa8bc66405291d62e4099a57eaa8eaeded0b3212"
    assert max(1, len(parsed.forwarded) // 4) == 7
    assert parsed.label == "0f1e:7:1"
    assert "x_chassis_correlation" not in parsed.recorded


def test_an_invalid_label_is_described_and_never_kept():
    """R-H5: 200 characters, and a number. Both stripped; neither recorded."""
    long_label = "a" * 200
    body = json.dumps({"x_chassis_correlation": long_label, "messages": []}).encode()
    parsed = parse_request(body, streaming=True)
    assert parsed.label is None and parsed.label_invalid == {"type": "str", "bytes": 200}
    assert long_label.encode() not in parsed.forwarded
    parsed = parse_request(b'{"x_chassis_correlation":42,"messages":[]}', streaming=True)
    assert parsed.label_invalid == {"type": "int", "bytes": 2}
    assert parsed.forwarded == b'{"messages":[]}'
    for bad in ("", "has space", "semi;colon", "é", "\ud800", "a" * 129):
        body = json.dumps({"x_chassis_correlation": bad}).encode()
        parsed = parse_request(body, streaming=True)
        assert parsed.label is None and parsed.label_invalid["type"] == "str", bad
    body = json.dumps({"x_chassis_correlation": "a" * 128}).encode()
    assert parse_request(body, streaming=True).label == "a" * 128


def test_a_non_finite_number_is_refused_with_or_without_a_transformation():
    """R-H6. With the stream strip, the old code re-encoded 1e400 as `Infinity`."""
    for body in (
        b'{"messages":[],"t":1e400}',
        b'{"messages":[],"t":-1e400}',
        b'{"messages":[],"t":NaN}',
        b'{"messages":[],"t":Infinity}',
        b'{"messages":[],"t":[-Infinity]}',
        b'{"messages":[],"stream":true,"t":1e400}',
    ):
        for streaming in (True, False):
            refusal = parse_request(body, streaming=streaming)
            assert isinstance(refusal, RequestRefusal), body
            assert refusal.code == "nonfinite_number" and refusal.status == 400, body


def test_a_duplicate_key_is_forwarded_untouched_or_refused_if_it_would_be_re_encoded():
    """R-H7, at the top level and nested."""
    body = b'{"a":1,"a":2,"messages":[]}'
    parsed = parse_request(body, streaming=True)
    assert parsed.forwarded is body and parsed.duplicate_keys is True
    assert parsed.recorded["a"] == 2
    labelled = b'{"a":1,"a":2,"messages":[],"x_chassis_correlation":"l"}'
    assert parse_request(labelled, streaming=True).code == "duplicate_keys"
    nested = b'{"messages":[{"k":1,"k":2}],"x_chassis_correlation":"l"}'
    assert parse_request(nested, streaming=True).code == "duplicate_keys"
    streamed = b'{"messages":[{"k":1,"k":2}],"stream":true}'
    assert parse_request(streamed, streaming=False).code == "duplicate_keys"
    assert parse_request(streamed, streaming=True).forwarded is streamed


def test_streaming_off_strips_the_stream_keys_whenever_the_stream_key_is_present():
    for value in ("true", "false", "null"):
        body = ('{"messages":[],"stream":%s,"stream_options":{"include_usage":true}}' % value).encode()
        parsed = parse_request(body, streaming=False)
        assert parsed.forwarded == b'{"messages":[]}' and parsed.transformed, value
        assert "stream" not in parsed.recorded and "stream_options" not in parsed.recorded
    body = b'{"messages":[],"stream_options":{}}'
    assert parse_request(body, streaming=False).forwarded is body, "no stream key, no strip"
    body = b'{"messages":[],"stream":true}'
    assert parse_request(body, streaming=True).forwarded is body


def test_a_re_encoded_body_is_ascii_and_keeps_every_character():
    content = "é€\U0001f600\u0000 "
    body = json.dumps(
        {"messages": [{"content": content}], "x_chassis_correlation": "l", "lone": "\ud800"}
    ).encode()
    parsed = parse_request(body, streaming=True)
    parsed.forwarded.decode("ascii")
    assert json.loads(parsed.forwarded) == {"messages": [{"content": content}], "lone": "\ud800"}


def test_the_parser_is_total_over_hostile_bytes():
    """Every input ends in a parse or a fixed refusal; none raises, none echoes the parser."""
    cases = {
        b"": "body_not_json",
        b"\xff\xfe": "body_not_utf8",
        b'{"a":"\xed\xa0\x80"}': "body_not_utf8",  # an encoded surrogate is not UTF-8
        b"[]": "body_not_object",
        b"null": "body_not_object",
        b"1": "body_not_object",
        b'"x"': "body_not_object",
        b"{": "body_not_json",
        b'{"a":1}{"b":2}': "body_not_json",
        b"[" * 100_000 + b"]" * 100_000: "unsupported_json",
        b'{"n":' + b"9" * 5000 + b"}": "unsupported_json",
    }
    for body, code in cases.items():
        result = parse_request(body, streaming=False)
        assert isinstance(result, RequestRefusal) and result.code == code, body[:20]
        assert "line" not in result.message and "column" not in result.message


def test_a_label_reaches_neither_the_upstream_nor_the_transcript(make_rig):
    """R-H4 end to end: the fake upstream saw the 30 bytes; only the open event names the label."""
    rig = make_rig()
    status, _headers, _payload = rig.post(R_H4)
    assert status == 200
    (request,) = rig.upstream.requests
    assert request["body"] == R_H4_FORWARDED
    (opened,) = [e for e in rig.events() if e["event"] == "open"]
    assert opened["client_label"] == "0f1e:7:1" and opened["transformed"] is True
    assert opened["estimate"] == 7 and opened["bytes_forwarded"] == 30
    rig.closes()
    (turn,) = rig.transcript()
    assert "x_chassis_correlation" not in turn["request"]
    assert rig.raw_record().count("0f1e:7:1") == 1, "the label is in the open event only"


def test_a_repeated_label_is_a_hint_and_the_hint_memory_is_bounded(make_rig, monkeypatch):
    rig = make_rig(rq=10, tk=1000, g=1000)
    monkeypatch.setattr(recorder_module, "MAX_LABEL_LRU", 2)
    for label in ("l1", "l1", "l2", "l3", "l1"):
        body = json.dumps({"messages": [], "x_chassis_correlation": label}).encode()
        assert rig.post(body)[0] == 200
    opens = [e for e in rig.events() if e["event"] == "open"]
    assert [e.get("label_seen_before", False) for e in opens] == [False, True, False, False, False]
    assert len(rig.recorder.state._labels) == 2
    assert len(rig.upstream.requests) == 5, "a repeated label suppresses nothing"


def test_an_invalid_label_is_recorded_as_type_and_size_only(make_rig):
    rig = make_rig()
    body = json.dumps({"messages": [], "x_chassis_correlation": "SECRET-LABEL value!"}).encode()
    assert rig.post(body)[0] == 200
    (opened,) = [e for e in rig.events() if e["event"] == "open"]
    assert opened["client_label_invalid"] == {"type": "str", "bytes": 19}
    assert "client_label" not in opened
    assert b"SECRET-LABEL" not in rig.upstream.requests[0]["body"]
    rig.closes()
    assert "SECRET-LABEL" not in rig.raw_record()


def test_a_refused_body_writes_one_close_and_no_open_and_reaches_nobody(make_rig):
    """R-H6 / R-H7 end to end."""
    rig = make_rig()
    status, _headers, payload = rig.post(b'{"messages":[],"t":1e400}')
    assert status == 400 and json.loads(payload)["error"]["code"] == "nonfinite_number"
    labelled = b'{"a":1,"a":2,"messages":[],"x_chassis_correlation":"l"}'
    status, _headers, payload = rig.post(labelled)
    assert status == 400 and json.loads(payload)["error"]["code"] == "duplicate_keys"
    closes = rig.closes(2)
    assert sorted(c["outcome"] for c in closes) == ["duplicate_keys", "nonfinite_number"]
    assert not [e for e in rig.events() if e["event"] == "open"]
    assert rig.upstream.requests == []
    assert rig.budget.snapshot(SLUG)["requests_used"] == 0


def test_a_duplicate_key_body_without_a_transformation_is_forwarded_verbatim(make_rig):
    rig = make_rig()
    body = b'{"a":1,"a":2,"messages":[]}'
    assert rig.post(body)[0] == 200
    assert rig.upstream.requests[0]["body"] == body
    (opened,) = [e for e in rig.events() if e["event"] == "open"]
    assert opened["duplicate_keys"] is True and opened["transformed"] is False


def test_streaming_off_end_to_end_records_what_was_forwarded(make_rig, monkeypatch):
    rig = make_rig()
    monkeypatch.setenv("UPSTREAM_STREAMING", "0")
    assert rig.post(b'{"messages":[],"stream":true,"stream_options":{}}')[0] == 200
    assert rig.upstream.requests[0]["body"] == b'{"messages":[]}'
    rig.closes()
    assert rig.transcript()[0]["request"] == {"messages": []}


def raw_exchange(rig: Rig, head: bytes, body: bytes) -> bytes:
    """Send bytes, half-close, read whatever comes back."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(str(rig.socket))
    try:
        sock.sendall(head + body)
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        sock.close()


def test_a_body_shorter_than_its_length_is_refused_and_never_forwarded(make_rig):
    """R-B1: Content-Length 100, 60 bytes, then end of stream."""
    rig = make_rig()
    head = f"POST {ROUTE} HTTP/1.1\r\nHost: x\r\nContent-Length: 100\r\n\r\n".encode()
    reply = raw_exchange(rig, head, R_H3)
    assert reply.startswith(b"HTTP/1.1 400") and b"short_body" in reply
    (close,) = rig.closes()
    assert close["outcome"] == "short_body"
    assert not [e for e in rig.events() if e["event"] == "open"]
    assert rig.upstream.requests == []
    assert rig.budget.snapshot(SLUG)["live"] == 0


def test_two_content_lengths_are_refused(make_rig):
    """R-B3: the base code used the first value."""
    rig = make_rig()
    head = (
        f"POST {ROUTE} HTTP/1.1\r\nHost: x\r\nContent-Length: 60\r\nContent-Length: 60\r\n\r\n"
    ).encode()
    reply = raw_exchange(rig, head, R_H3)
    assert reply.startswith(b"HTTP/1.1 400") and b"duplicate_content_length" in reply
    head = f"POST {ROUTE} HTTP/1.1\r\nHost: x\r\nContent-Length: 6_0\r\n\r\n".encode()
    assert raw_exchange(rig, head, R_H3).startswith(b"HTTP/1.1 400")
    closes = rig.closes(2)
    assert sorted(c["outcome"] for c in closes) == ["bad_content_length", "duplicate_content_length"]
    assert rig.upstream.requests == []


# ---------------------------------------------------------------------------
# R-B2: what goes upstream, on both transports
# ---------------------------------------------------------------------------
CLIENT_HEADERS = [
    ("Host", "localhost"),
    ("aUtHoRiZaTiOn", "Bearer CLIENT-DUMMY"),
    ("X-Secret-Marker", "DUMMY-123"),
    ("Accept", "text/event-stream"),
    ("User-Agent", "client/1"),
    ("Content-Length", str(len(R_H3))),
]
REVIEWED = {
    "accept-encoding": "identity",
    "content-length": str(len(R_H3)),
    "content-type": "application/json",
    "accept": "text/event-stream",
    "user-agent": "space-chassis-recorder/0.2",
}


def headers_received(rig: Rig, client_headers=CLIENT_HEADERS) -> list[tuple[str, str]]:
    status, _headers, _payload = rig.post(R_H3, raw_headers=client_headers)
    assert status == 200
    rig.closes()
    return rig.upstream.requests[-1]["headers"]


def without_host(headers: list[tuple[str, str]]) -> dict[str, str]:
    return {name.lower(): value for name, value in headers if name.lower() != "host"}


def test_no_request_header_is_ever_written_to_the_record_and_the_upstream_gets_seven(make_rig):
    """R-H1, on the unix-socket path and the network path, compared.

    This replaces the source-grep that asserted the recorder's text mentioned
    `self.headers.items()`: it watches what the upstream actually received
    and what the record actually holds. The key is synthetic and goes only to
    the fake upstream.
    """
    received = {}
    for network in (False, True):
        rig = make_rig(network=network)
        headers = headers_received(rig)
        names = sorted(name.lower() for name, _ in headers)
        assert names == sorted([*REVIEWED, "host", "authorization"]), (network, headers)
        received[network] = without_host(headers)
        assert received[network] == {**REVIEWED, "authorization": f"Bearer {RECORDER_KEY}"}
        record = rig.raw_record()
        assert record, "the request was recorded"
        for secret in ("CLIENT-DUMMY", "DUMMY-123", RECORDER_KEY):
            assert secret not in record, (network, secret)
        assert "authorization" not in record.lower()
    assert received[False] == received[True], "the two transports send different headers"


def test_with_no_key_configured_no_authorization_is_sent_at_all(make_rig, monkeypatch):
    """R-H2: the client's own key is never a fallback."""
    for network in (False, True):
        rig = make_rig(network=network)
        monkeypatch.setenv("LLM_API_KEY", "")
        headers = headers_received(rig)
        assert len(headers) == 6
        assert without_host(headers) == REVIEWED
        assert "CLIENT-DUMMY" not in json.dumps(headers)


def test_only_allowlisted_single_printable_x_headers_are_passed_on(make_rig, monkeypatch):
    rig = make_rig()
    monkeypatch.setenv(
        "RECORDER_FORWARD_HEADERS",
        "X-Title, x-api-key, Authorization, X-Twice, X-Ctl, X-Long, Bad Name, Y-Other",
    )
    client = [
        ("Host", "localhost"),
        ("X-Title", "space chassis"),
        ("X-Api-Key", "CLIENT-API-KEY"),
        ("X-Twice", "a"),
        ("X-Twice", "b"),
        ("X-Ctl", "a\tb"),
        ("X-Long", "a" * 257),
        ("Y-Other", "y"),
        ("Content-Length", str(len(R_H3))),
    ]
    headers = without_host(headers_received(rig, client))
    extras = {name: value for name, value in headers.items() if name.startswith(("x-", "y-"))}
    assert extras == {"x-title": "space chassis"}
    assert "CLIENT-API-KEY" not in rig.raw_record()


def test_the_outbound_builder_ignores_case_and_refuses_credentials_by_name():
    import email.message  # noqa: PLC0415 -- the header type http.server hands the handler

    def message(*pairs):
        built = email.message.Message()
        for name, value in pairs:
            built[name] = value
        return built

    build = recorder_module.outbound_headers
    assert build(message(("ACCEPT", " Text/Event-Stream ")), "")["Accept"] == "text/event-stream"
    assert build(message(("Accept", "*/*")), "")["Accept"] == "*/*"
    assert build(message(("Accept", "application/json; q=1")), "")["Accept"] == "application/json"
    twice = message(("Accept", "text/event-stream"), ("Accept", "*/*"))
    assert build(twice, "")["Accept"] == "application/json"
    assert build(message(), "")["Accept"] == "application/json"
    assert "Authorization" not in build(message(("Authorization", "Bearer x")), "")
    assert build(message(), "k")["Authorization"] == "Bearer k"
    denied = message(("Cookie", "c"), ("X-Api-Key", "k"), ("Authorization", "a"))
    assert set(build(denied, "", ("Cookie", "X-Api-Key", "Authorization"))) == {
        "Content-Type",
        "Accept",
        "User-Agent",
    }


def test_the_network_path_uses_verified_tls_and_ignores_the_unix_socket_when_unset(monkeypatch):
    monkeypatch.setattr(recorder_module, "UPSTREAM_SOCKET", "")
    monkeypatch.setenv("LLM_BASE_URL", "https://model.invalid/api/v1")
    connection = recorder_module.upstream_connection()
    assert isinstance(connection, http.client.HTTPSConnection)
    assert connection._context.verify_mode == ssl.CERT_REQUIRED
    assert connection._context.check_hostname is True
    assert (connection.host, connection.port) == ("model.invalid", 443)
    assert recorder_module.request_path(recorder_module.upstream_url()) == "/api/v1/chat/completions"
    monkeypatch.setattr(recorder_module, "UPSTREAM_SOCKET", "/tmp/x.sock")
    assert isinstance(recorder_module.upstream_connection(), recorder_module.UnixHTTPConnection)


def test_nothing_is_sent_without_a_connection_made_before_the_send_gate(make_rig):
    """No hidden auto-connect: a dropped connection fails the exchange instead of reopening."""
    rig = make_rig()
    unconnected = recorder_module.Upstream()
    with pytest.raises(http.client.NotConnected):
        unconnected.exchange({}, b"{}")
    upstream = recorder_module.Upstream()
    upstream.connect()
    assert upstream.connection.auto_open == 0
    upstream.close()
    with pytest.raises(http.client.NotConnected):
        upstream.exchange({}, b"{}")
    assert rig.upstream.requests == []


def test_a_refused_network_connection_is_refunded_too(make_rig, monkeypatch):
    """R-C7 on the network path, which urllib could not tell from a send failure."""
    rig = make_rig(network=True)
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{port}/v1")
    status, _headers, payload = rig.post(chat())
    assert status == 502 and json.loads(payload)["error"]["code"] == "upstream_connect"
    (close,) = rig.closes()
    assert close["usage_class"] == "none" and close["charged_tokens"] == 0
    snap = rig.budget.snapshot(SLUG)
    assert (snap["requests_used"], snap["tokens_used"], snap["live"]) == (0, 0, 0)

    monkeypatch.setenv("LLM_BASE_URL", "ftp://upstream.invalid/v1")
    status, _headers, payload = rig.post(chat())
    assert status == 502 and "upstream.invalid" not in payload.decode()
    assert rig.closes(2)[-1]["outcome"] == "upstream_connect"
    assert rig.budget.snapshot(SLUG)["requests_used"] == 0


# ---------------------------------------------------------------------------
# Correction pass: the findings of the SV-016 Astra initial package review
# ---------------------------------------------------------------------------
LONE = "\ud800"


def test_a_lone_surrogate_in_an_accepted_body_is_recorded_and_settled(make_rig):
    """SV016-01. Valid JSON escapes a lone surrogate; the record must hold it too.

    In content and in model, with and without the label strip. The upstream
    gets the untouched bytes or the one ASCII re-encoding, the turn settles at
    its actual usage, and every record line parses back to the same strings.
    """
    rig = make_rig(rq=10, tk=10_000, g=10_000)
    rig.upstream.respond = lambda request: stub_reply(
        {**completion(), "choices": [{"message": {"role": "assistant", "content": LONE}}]}
    )
    cases = [
        {"model": "stub", "messages": [{"role": "user", "content": LONE}]},
        {"model": LONE, "messages": [{"role": "user", "content": "hi"}]},
        {"model": "stub", "messages": [{"role": "user", "content": LONE}], "x_chassis_correlation": "l"},
        {"model": LONE, "messages": [], "x_chassis_correlation": "l"},
    ]
    for number, case in enumerate(cases, start=1):
        body = json.dumps(case).encode("ascii")
        status, _headers, _payload = rig.post(body)
        assert status == 200, case
        sent = rig.upstream.requests[-1]["body"]
        if "x_chassis_correlation" in case:
            expected = {k: v for k, v in case.items() if k != "x_chassis_correlation"}
            assert sent == json.dumps(expected, separators=(",", ":")).encode("ascii")
        else:
            assert sent == body, "an untouched body was not forwarded byte for byte"
        closes = rig.closes(number)
        assert len(closes) == number
        assert closes[-1]["outcome"] == "ok" and closes[-1]["charged_tokens"] == 30
        turn = rig.transcript()[-1]
        assert turn["request"] == {k: v for k, v in case.items() if k != "x_chassis_correlation"}
        assert turn["response"]["choices"][0]["message"]["content"] == LONE
        opened = [e for e in rig.events() if e["event"] == "open"][-1]
        assert opened["model"] == case["model"]
    one_close_each(rig.events())
    assert rig.budget.snapshot(SLUG)["tokens_used"] == 30 * len(cases)


def test_relayed_means_the_upstream_response_reached_the_client(make_rig, monkeypatch):
    """SV016-02. A recorder error that reached the client is not a relayed response."""
    rig = make_rig(rq=10, tk=10_000, g=10_000)
    assert rig.post(chat())[0] == 200
    rig.upstream.respond = lambda request: stub_reply({"error": {"message": "slow down"}}, 429)
    assert rig.post(chat())[0] == 429
    rig.upstream.respond = lambda request: None
    assert rig.post(chat())[0] == 502
    rig.upstream.respond = lambda request: stub_reply(completion())
    assert rig.post(chat(), path="/nope")[0] == 404
    closes = rig.closes(4)
    by_outcome = {c["outcome"]: c for c in closes}
    assert by_outcome["ok"]["relayed"] is True
    assert by_outcome["upstream_http"]["relayed"] is True
    assert by_outcome["upstream_http"]["upstream_status"] == 429
    assert by_outcome["upstream_transport"]["relayed"] is False
    assert by_outcome["not_found"]["relayed"] is False

    deaf = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    deaf.bind(str(rig.root / "deaf.sock"))
    monkeypatch.setattr(recorder_module, "UPSTREAM_SOCKET", str(rig.root / "deaf.sock"))
    try:
        assert rig.post(chat())[0] == 502
    finally:
        deaf.close()
    close = rig.closes(5)[-1]
    assert close["outcome"] == "upstream_connect" and close["relayed"] is False


def test_a_completion_withheld_after_a_transcript_failure_is_not_relayed(make_rig):
    """SV016-02 / R-C1's relay field: the provider answered 200, the client got the recorder's 502."""
    rig = make_rig(tk=1000, g=1000)
    (rig.dir / "agent_life_transcript.jsonl").mkdir()
    status, _headers, payload = rig.post(chat())
    assert status == 502 and b"choices" not in payload
    (close,) = rig.closes()
    assert close["upstream_status"] == 200 and close["charged_tokens"] == 30
    assert close["relayed"] is False


def test_any_transfer_encoding_field_is_refused_even_an_empty_one(make_rig):
    """SV016-03. Presence, not truthiness: an empty first field hid a later `chunked`."""
    rig = make_rig()
    heads = [
        f"POST {ROUTE} HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: \r\nContent-Length: 60\r\n\r\n",
        (
            f"POST {ROUTE} HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: \r\n"
            "Transfer-Encoding: chunked\r\nContent-Length: 60\r\n\r\n"
        ),
    ]
    for head in heads:
        reply = raw_exchange(rig, head.encode(), R_H3)
        assert reply.startswith(b"HTTP/1.1 411"), reply[:40]
    closes = rig.closes(2)
    assert [c["outcome"] for c in closes] == ["length_required", "length_required"]
    assert not [e for e in rig.events() if e["event"] == "open"]
    assert rig.upstream.requests == []
    assert rig.budget.snapshot(SLUG)["requests_used"] == 0


class _Injected(Exception):
    pass


class FailOnceSemaphore:
    """A fleet slot pool whose first acquire raises; afterwards an ordinary semaphore."""

    def __init__(self) -> None:
        self.real = threading.BoundedSemaphore(4)
        self.failures = 1

    def acquire(self, timeout=None):
        if self.failures:
            self.failures -= 1
            raise _Injected("injected acquire failure")
        return self.real.acquire(timeout=timeout)

    def release(self):
        self.real.release()


def test_a_failing_fleet_slot_acquire_gives_the_socket_slot_back(make_rig, monkeypatch):
    """SV016-04. One socket slot; the first request's fleet acquire raises; the next still gets in."""
    rig = make_rig(rq=10, tk=1000, g=1000)
    monkeypatch.setattr(recorder_module, "INFLIGHT_WAIT_SECONDS", 0.2)
    monkeypatch.setattr(recorder_module, "TOTAL_SLOTS", FailOnceSemaphore())
    rig.recorder.state.slots = threading.BoundedSemaphore(1)
    assert rig.post(chat())[0] == 500
    assert rig.post(chat())[0] == 200, "the socket slot leaked"
    assert [c["outcome"] for c in rig.closes(2)] == ["internal_error", "ok"]


def test_a_control_exception_before_sending_cancels_and_closes_once_with_a_typed_outcome(
    make_rig, monkeypatch
):
    """SV016-05. SystemExit propagates; no status is claimed; the reservation is cancelled."""
    rig = make_rig()
    rig.recorder.state.slots = threading.BoundedSemaphore(1)
    original = recorder_module.upstream_key

    def abort() -> str:
        raise SystemExit(3)

    monkeypatch.setattr(recorder_module, "upstream_key", abort)
    with pytest.raises((http.client.HTTPException, OSError)):
        rig.post(chat())
    (close,) = rig.closes()
    time.sleep(0.1)
    assert len(rig.closes()) == 1
    assert close["outcome"] == "aborted" and close["status"] is None
    assert close["usage_class"] == "none" and close["relayed"] is False
    snap = rig.budget.snapshot(SLUG)
    assert (snap["requests_used"], snap["live"]) == (0, 0)
    assert rig.upstream.requests == []
    monkeypatch.setattr(recorder_module, "upstream_key", original)
    assert rig.post(chat())[0] == 200, "the slot was not released"


def test_a_control_exception_after_sending_settles_unknown_and_closes_once(make_rig, monkeypatch):
    rig = make_rig()
    rig.recorder.state.slots = threading.BoundedSemaphore(1)

    def abort(payload):
        raise SystemExit(3)

    monkeypatch.setattr(recorder_module, "decode_payload", abort)
    body = chat()
    with pytest.raises((http.client.HTTPException, OSError)):
        rig.post(body)
    (close,) = rig.closes()
    assert close["outcome"] == "aborted" and close["status"] is None
    assert close["usage_class"] == "unknown" and close["charged_tokens"] == len(body) // 4
    assert close["upstream_status"] == 200 and close["relayed"] is False
    snap = rig.budget.snapshot(SLUG)
    assert (snap["requests_used"], snap["live"]) == (1, 0)
    monkeypatch.setattr(recorder_module, "decode_payload", lambda payload: json.loads(payload))
    assert rig.post(chat())[0] == 200, "the slot was not released"


def test_a_configured_header_name_in_two_spellings_is_sent_once(make_rig, monkeypatch):
    """SV016-06. The fake upstream must see one X-Title field, not two."""
    rig = make_rig()
    monkeypatch.setenv("RECORDER_FORWARD_HEADERS", "X-Title,x-title, X-TITLE")
    assert recorder_module.forward_header_names() == ("X-Title",)
    client = [("Host", "localhost"), ("X-Title", "hello"), ("Content-Length", str(len(R_H3)))]
    headers = headers_received(rig, client)
    assert [name.lower() for name, _ in headers].count("x-title") == 1
    twice = [
        ("Host", "localhost"),
        ("X-Title", "a"),
        ("x-title", "b"),
        ("Content-Length", str(len(R_H3))),
    ]
    headers = headers_received(rig, twice)
    assert "x-title" not in [name.lower() for name, _ in headers], "a duplicated inbound field passed"


def test_the_builder_itself_deduplicates_extra_names_ignoring_case():
    import email.message  # noqa: PLC0415 -- the header type http.server hands the handler

    inbound = email.message.Message()
    inbound["X-Title"] = "hello"
    headers = recorder_module.outbound_headers(inbound, "", ("X-Title", "x-title", "X-TITLE"))
    assert [name for name in headers if name.lower() == "x-title"] == ["X-Title"]
    assert recorder_module.outbound_headers(email.message.Message(), "", ())  == {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "space-chassis-recorder/0.2",
    }


def test_the_parser_stays_total_near_the_recursion_limit():
    """Review condition RB1-03: re-encoding (the label, the transformed body) is inside the guard.

    A sweep of nesting depths around the interpreter's limit, in a label and
    in a transformed body. Each ends in a parse or a fixed refusal; this does
    not claim a depth that fails today, only that none can escape.
    """
    import sys  # noqa: PLC0415 -- only this sweep needs the limit

    limit = sys.getrecursionlimit()
    for depth in range(max(1, limit - 40), limit + 40, 4):
        nested = b"[" * depth + b"]" * depth
        bodies = (
            b'{"messages":[],"x_chassis_correlation":' + nested + b"}",
            b'{"messages":' + nested + b',"x_chassis_correlation":"l"}',
            b'{"messages":' + nested + b',"stream":true}',
        )
        for body in bodies:
            result = parse_request(body, streaming=False)
            assert isinstance(result, (ParsedRequest, RequestRefusal)), depth


def test_a_failing_re_encoding_is_a_fixed_refusal(monkeypatch):
    """The guard itself, forced: the serializer raising is a refusal, not an escape."""
    def too_deep(*_args, **_kwargs):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(recorder_module, "_encode_forwarded", too_deep)
    result = parse_request(b'{"messages":[],"x_chassis_correlation":"l"}', streaming=True)
    assert isinstance(result, RequestRefusal) and result.code == "unsupported_json"
    monkeypatch.setattr(recorder_module, "_encode_label", too_deep)
    result = parse_request(b'{"messages":[],"x_chassis_correlation":[1]}', streaming=True)
    assert isinstance(result, RequestRefusal) and result.code == "unsupported_json"
