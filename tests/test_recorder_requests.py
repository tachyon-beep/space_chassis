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
