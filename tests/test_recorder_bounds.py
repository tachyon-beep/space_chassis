"""The recorder's structure, memory, connection and response bounds (SV-018 / R-B3).

Expected values are SV-015 v2 section 2.2 (pre-scan caps, the reservation
arithmetic) and fixtures O4-3...O4-7, with SV-013's R-B4, R-B6 and R-B7
response fixtures. The memory tests are arithmetic on a reservation, never a
real 148 MiB allocation; nothing here measures interpreter RSS, and the
reservation constants remain commissioning assumptions.
"""

from __future__ import annotations

import json
import socket
import socketserver
import threading
import time
from pathlib import Path

import pytest
import recorder as recorder_module
from recorder import MemoryBudget, prescan, sse_usage
from test_recorder_requests import (  # noqa: F401 -- make_rig is a fixture
    SLUG,
    chat,
    completion,
    make_rig,
    read_jsonl,
    stub_reply,
)

MiB = 1024 * 1024


class RawUpstream:
    """A unix-socket upstream that reads one request and writes scripted raw bytes."""

    def __init__(self, path: Path, script) -> None:
        self.path = path
        self.script = script  # callable(sock) that writes the response
        self.requests = 0
        upstream = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                data = b""
                while b"\r\n\r\n" not in data:
                    chunk = self.request.recv(65536)
                    if not chunk:
                        return
                    data += chunk
                head, _, rest = data.partition(b"\r\n\r\n")
                length = 0
                for line in head.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        length = int(line.split(b":", 1)[1])
                while len(rest) < length:
                    chunk = self.request.recv(65536)
                    if not chunk:
                        return
                    rest += chunk
                upstream.requests += 1
                try:
                    upstream.script(self.request)
                except OSError:
                    pass

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True

        self.server = Server(str(path), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05})
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)


@pytest.fixture
def raw_upstream(make_rig, monkeypatch):
    made = []

    def build(rig, script):
        upstream = RawUpstream(rig.root / "raw.sock", script)
        made.append(upstream)
        monkeypatch.setattr(recorder_module, "UPSTREAM_SOCKET", str(upstream.path))
        return upstream

    yield build
    for upstream in made:
        upstream.stop()


def http_response(body: bytes, *, framing: str = "length", content_type: str = "application/json") -> bytes:
    head = f"HTTP/1.1 200 OK\r\nContent-Type: {content_type}\r\n"
    if framing == "length":
        return (head + f"Content-Length: {len(body)}\r\n\r\n").encode() + body
    if framing == "chunked":
        chunks = b"".join(
            f"{len(body[i:i + 300]):x}\r\n".encode() + body[i : i + 300] + b"\r\n"
            for i in range(0, len(body), 300)
        )
        return (head + "Transfer-Encoding: chunked\r\n\r\n").encode() + chunks + b"0\r\n\r\n"
    return (head + "Connection: close\r\n\r\n").encode() + body  # delimited by close


# ---------------------------------------------------------------------------
# The pre-scan
# ---------------------------------------------------------------------------
def test_the_pre_scan_counts_containers_strings_keys_and_scalars():
    scan = prescan(b'{"a":[1,2,{"b":"x"}]}', recorder_module.REQUEST_CAPS)
    assert (scan.depth, scan.containers, scan.values, scan.exceeded) == (3, 3, 8, None)


def test_punctuation_and_escapes_inside_strings_are_not_structure():
    body = b'{"k":"{[\\"}]\\\\","e":"\\\\\\"[["}'
    assert json.loads(body) == {"k": '{["}]\\', "e": '\\"[['}
    scan = prescan(body, recorder_module.REQUEST_CAPS)
    assert (scan.depth, scan.containers, scan.values) == (1, 1, 5)


def test_o4_3_two_mebibytes_of_empty_objects_are_refused_before_any_parse(make_rig, monkeypatch):
    """O4-3: 699,050 `{}`; containers pass 32,768 long before the end; json.loads never runs."""
    body = b"[" + b",".join([b"{}"] * 699_050) + b"]"
    assert len(body) <= 2 * MiB
    scan = prescan(body, recorder_module.REQUEST_CAPS)
    assert scan.exceeded == "containers" and scan.containers == 32_769

    rig = make_rig()

    def never(*_args, **_kwargs):
        raise AssertionError("the body was parsed")

    monkeypatch.setattr(recorder_module, "parse_request", never)
    status, _headers, payload = rig.post(body)
    assert status == 400 and json.loads(payload)["error"]["code"] == "structure_limit"
    (close,) = rig.closes()
    assert close["outcome"] == "structure_limit"
    assert not [e for e in rig.events() if e["event"] == "open"]
    assert rig.upstream.requests == []
    assert recorder_module.MEMORY.used == 0, "nothing was reserved for a refused body"


def test_o4_4_sixty_five_levels_are_too_deep_and_sixty_four_are_not():
    assert prescan(b"[" * 65 + b"]" * 65, recorder_module.REQUEST_CAPS).exceeded == "depth"
    body = b'{"a":' + b"[" * 63 + b"]" * 63 + b"}"
    assert prescan(body, recorder_module.REQUEST_CAPS) == recorder_module.Scan(64, 64, 65, None)


def test_o4_5_object_elements_hit_the_container_cap_and_scalars_the_value_cap():
    """O4-5 as given exceeds containers first; a scalar array proves the values cap separately."""
    objects = b"[" + b",".join([b'{"a":0}'] * 262_000) + b"]"
    assert len(objects) <= 2 * MiB
    assert prescan(objects, recorder_module.REQUEST_CAPS).exceeded == "containers"
    at_cap = b"[" + b",".join([b"0"] * 131_071) + b"]"
    over = b"[" + b",".join([b"0"] * 131_072) + b"]"
    assert prescan(at_cap, recorder_module.REQUEST_CAPS).values == 131_072
    assert prescan(at_cap, recorder_module.REQUEST_CAPS).exceeded is None
    assert prescan(over, recorder_module.REQUEST_CAPS).exceeded == "values"


def test_o4_6_an_over_structured_response_is_recorded_raw_and_its_usage_not_trusted(make_rig):
    """O4-6: 40,000 `{}` in a response: not parsed, structure_limit, usage unknown, estimate charged."""
    rig = make_rig(tk=10_000, g=10_000)
    body = b'{"usage":{"total_tokens":5},"x":[' + b",".join([b"{}"] * 40_000) + b"]}"
    rig.upstream.respond = lambda request: (200, {"Content-Type": "application/json"}, body)
    request = chat()
    status, _headers, payload = rig.post(request)
    assert status == 200 and payload == body, "the client still gets the provider's bytes"
    (close,) = rig.closes()
    assert close["usage_class"] == "unknown" and close["charged_tokens"] == len(request) // 4
    (turn,) = rig.transcript()
    assert turn["structure_limit"] is True and turn["response"]["structure_limit"] is True
    assert turn["usage_class"] == "unknown"
    assert turn["response"]["raw_body"].startswith('{"usage"')


# ---------------------------------------------------------------------------
# The memory reservation
# ---------------------------------------------------------------------------
def test_the_reservation_arithmetic_matches_the_design():
    assert recorder_module.memory_for_request(2 * MiB, 131_072) == 98 * MiB
    assert recorder_module.memory_for_response() == 50 * MiB
    worst = 98 * MiB + 50 * MiB
    assert 5 * worst <= recorder_module.MEMORY_BUDGET_BYTES < 6 * worst
    typical = recorder_module.memory_for_request(MiB // 2, 10_000) + 50 * MiB
    assert round(typical / MiB, 1) == 68.9


def test_o4_7_a_second_worst_case_reservation_waits_then_is_refused():
    budget = MemoryBudget(200 * MiB)
    assert budget.reserve(148 * MiB, 0)
    started = time.monotonic()
    assert budget.reserve(148 * MiB, 0.2) is False
    assert time.monotonic() - started >= 0.2
    assert budget.used == 148 * MiB
    budget.release(148 * MiB)
    assert budget.reserve(148 * MiB, 0) and budget.used == 148 * MiB
    assert MemoryBudget(100 * MiB).reserve(148 * MiB, 10) is False, "can never fit: no wait"


def test_o4_7_a_request_without_memory_is_refused_before_parsing_and_spends_nothing(make_rig, monkeypatch):
    rig = make_rig()
    pool = MemoryBudget(200 * MiB)
    monkeypatch.setattr(recorder_module, "MEMORY", pool)
    monkeypatch.setattr(recorder_module, "INFLIGHT_WAIT_SECONDS", 0.3)
    assert pool.reserve(151 * MiB, 0)  # another request's worst case, held
    status, _headers, payload = rig.post(chat())
    assert status == 429 and json.loads(payload)["error"]["code"] == "memory"
    (close,) = rig.closes()
    assert close["outcome"] == "memory"
    assert not [e for e in rig.events() if e["event"] == "open"]
    assert rig.upstream.requests == [] and rig.budget.snapshot(SLUG)["requests_used"] == 0
    assert pool.used == 151 * MiB
    pool.release(151 * MiB)
    assert rig.post(chat())[0] == 200
    rig.closes(2)
    assert pool.used == 0, "every reservation was released exactly once"


def test_resources_are_released_when_a_control_exception_unwinds_after_the_reservation(make_rig, monkeypatch):
    rig = make_rig()
    rig.recorder.state.slots = threading.BoundedSemaphore(1)
    before = recorder_module.WATCHDOG.counts()["active"]

    def abort(*_args, **_kwargs):
        raise SystemExit(3)

    original = recorder_module.parse_request
    monkeypatch.setattr(recorder_module, "parse_request", abort)
    with pytest.raises(Exception):
        rig.post(chat())
    (close,) = rig.closes()
    assert close["outcome"] == "aborted"
    assert recorder_module.MEMORY.used == 0
    monkeypatch.setattr(recorder_module, "parse_request", original)
    assert rig.post(chat())[0] == 200, "the slot was released"
    rig.closes(2)
    assert recorder_module.WATCHDOG.counts()["active"] == before


# ---------------------------------------------------------------------------
# The response cap
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("framing", ["length", "chunked", "close"])
def test_a_response_over_the_cap_is_recorded_in_part_and_not_relayed(make_rig, raw_upstream, monkeypatch, framing):
    """SV-013 R-B4 with MAX_RESPONSE = 1000 and a 1,500-byte body, under every framing.

    The prefix carries a valid usage: a truncated response is never billing evidence.
    """
    rig = make_rig(tk=10_000, g=10_000)
    monkeypatch.setattr(recorder_module, "MAX_RESPONSE", 1000)
    body = b'{"usage":{"total_tokens":7},"pad":"' + b"p" * 1500 + b'"}'
    upstream = raw_upstream(rig, lambda sock: sock.sendall(http_response(body, framing=framing)))
    request = chat()
    status, _headers, payload = rig.post(request)
    assert status == 502 and json.loads(payload)["error"]["code"] == "response_cap_exceeded"
    assert b"pad" not in payload
    (close,) = rig.closes()
    assert close["outcome"] == "response_cap_exceeded" and close["recorded"] == "durable"
    assert close["relayed"] is False and close["upstream_status"] == 200
    assert close["usage_class"] == "unknown" and close["charged_tokens"] == len(request) // 4
    (turn,) = rig.transcript()
    response = turn["response"]
    assert response["raw_body"] == body[:1000].decode()
    assert response["raw_body_truncated"] is True and response["kept_bytes"] == 1000
    assert turn["usage_class"] == "unknown" and turn["usage"] is None
    assert upstream.requests == 1


def test_a_response_exactly_at_the_cap_is_relayed_whole(make_rig, raw_upstream, monkeypatch):
    rig = make_rig()
    monkeypatch.setattr(recorder_module, "MAX_RESPONSE", 1000)
    body = b'{"usage":{"total_tokens":7},"pad":"' + b"p" * (1000 - 37) + b'"}'
    assert len(body) == 1000
    raw_upstream(rig, lambda sock: sock.sendall(http_response(body, framing="chunked")))
    status, _headers, payload = rig.post(chat())
    assert status == 200 and payload == body
    (close,) = rig.closes()
    assert close["usage_class"] == "known" and close["charged_tokens"] == 7


def test_a_body_cut_short_before_its_content_length_is_a_transport_failure(make_rig, raw_upstream):
    rig = make_rig()
    raw_upstream(
        rig,
        lambda sock: sock.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n" + b"x" * 40),
    )
    request = chat()
    assert rig.post(request)[0] == 502
    (close,) = rig.closes()
    assert close["outcome"] == "upstream_transport" and close["charged_tokens"] == len(request) // 4


# ---------------------------------------------------------------------------
# Server-sent events
# ---------------------------------------------------------------------------
def stub_sse(total: int | None = 30, separator: str = "\n") -> bytes:
    """The stub's own format (endurance/stub_model.py:360-389)."""
    chunks = [
        {"id": "c1", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": "hi"}}]},
        {"id": "c1", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}}]},
    ]
    if total is not None:
        chunks[1]["usage"] = {"prompt_tokens": total - 10, "completion_tokens": 10, "total_tokens": total}
    text = "".join(f"data: {json.dumps(chunk)}{separator}{separator}" for chunk in chunks)
    return (text + f"data: [DONE]{separator}{separator}").encode()


def test_r_b6_stub_sse_usage_is_known_and_the_client_gets_identical_bytes(make_rig):
    rig = make_rig(tk=10_000, g=10_000)
    body = stub_sse(30)
    rig.upstream.respond = lambda request: (200, {"Content-Type": "application/json"}, body)
    status, _headers, payload = rig.post(chat(stream=True))
    assert status == 200 and payload == body
    (close,) = rig.closes()
    assert close["usage_class"] == "known" and close["charged_tokens"] == 30
    assert close["usage"] == {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
    (turn,) = rig.transcript()
    assert turn["usage_class"] == "known" and turn["usage"]["total_tokens"] == 30
    assert "raw_body" in turn["response"], "the record keeps the established raw shape"


def test_r_b7_sse_without_usage_settles_at_the_estimate(make_rig):
    rig = make_rig(tk=10_000, g=10_000)
    rig.upstream.respond = lambda request: (200, {"Content-Type": "text/event-stream"}, stub_sse(None))
    request = chat(stream=True)
    assert rig.post(request)[0] == 200
    (close,) = rig.closes()
    assert close["usage_class"] == "unknown" and close["charged_tokens"] == len(request) // 4
    assert close["usage"] is None


def test_sse_dialect_variants_are_parsed_by_the_stated_rules():
    usage, limited = sse_usage(stub_sse(30, separator="\r\n"))
    assert (usage.cls, usage.actual, limited) == ("known", 30, False)
    joined = b': keepalive\n\nevent: chunk\ndata: {"usage":\ndata:  {"total_tokens": 9}}\n\ndata: [DONE]\n\n'
    usage, _ = sse_usage(b"\n  " + joined)
    assert (usage.cls, usage.actual) == ("known", 9)
    later_invalid = b'data: {"usage":{"total_tokens":4}}\n\ndata: {"usage":{"total_tokens":-1}}\n\n'
    assert sse_usage(later_invalid)[0].actual == 4, "the last *valid* usage counts"
    garbage = b'data: {not json}\n\ndata: {"usage":{"total_tokens":6}}\n\n'
    assert sse_usage(garbage)[0].actual == 6
    deep = b'data: {"x":' + b"[" * 70 + b"]" * 70 + b"}\n\n"
    usage, limited = sse_usage(deep + b'data: {"usage":{"total_tokens":3}}\n\n')
    assert (usage.cls, limited) == ("unknown", True), "any over-structured event makes usage unknown"
    assert recorder_module.is_event_stream(b"\r\n data: x") and not recorder_module.is_event_stream(b'{"data":1}')


def test_an_over_structured_sse_event_is_flagged_in_the_record(make_rig):
    rig = make_rig(tk=10_000, g=10_000)
    deep = b'data: {"x":' + b"[" * 70 + b"]" * 70 + b"}\n\n"
    body = deep + stub_sse(30)
    rig.upstream.respond = lambda request: (200, {"Content-Type": "text/event-stream"}, body)
    request = chat(stream=True)
    status, _headers, payload = rig.post(request)
    assert status == 200 and payload == body
    (close,) = rig.closes()
    assert close["usage_class"] == "unknown" and close["charged_tokens"] == len(request) // 4
    (turn,) = rig.transcript()
    assert turn["structure_limit"] is True


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------
def test_a_connection_over_the_bound_gets_a_canned_503_and_no_handler(make_rig, monkeypatch):
    rig = make_rig()
    monkeypatch.setattr(recorder_module, "CONNECTIONS", threading.BoundedSemaphore(1))
    holder = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    holder.connect(str(rig.socket))  # holds the one connection, sending nothing
    try:
        time.sleep(0.2)
        second = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        second.settimeout(5)
        second.connect(str(rig.socket))
        reply = b""
        while True:
            chunk = second.recv(4096)
            if not chunk:
                break
            reply += chunk
        second.close()
    finally:
        holder.close()
    assert reply.startswith(b"HTTP/1.1 503") and b'"connections"' in reply
    assert b"Connection: close" in reply
    deadline = time.monotonic() + 5
    while recorder_module.CONNECTIONS._value != 1:  # the held one is released when it closes
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert rig.events() == [], "a refused connection has no request to record"


def test_one_request_per_connection_and_the_response_says_so(make_rig):
    rig = make_rig(rq=10)
    body = chat()
    one = f"POST /api/v1/chat/completions HTTP/1.1\r\nHost: x\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(str(rig.socket))
    sock.sendall(one + one)  # pipelined: the second must not be served on this connection
    reply = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        reply += chunk
    sock.close()
    assert reply.count(b"HTTP/1.1 200") == 1 and b"Connection: close" in reply
    rig.closes()
    time.sleep(0.2)
    assert len([e for e in rig.events() if e["event"] == "open"]) == 1
    assert len(rig.upstream.requests) == 1


def test_every_phase_is_released_after_ordinary_and_refused_requests(make_rig):
    rig = make_rig(rq=10)
    before = recorder_module.WATCHDOG.counts()["active"]
    assert rig.post(chat())[0] == 200
    assert rig.post(chat(), path="/nope")[0] == 404
    assert rig.post(b"[]")[0] == 400
    rig.closes(3)
    assert recorder_module.WATCHDOG.counts()["active"] == before
    assert recorder_module.MEMORY.used == 0
