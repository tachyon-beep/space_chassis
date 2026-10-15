import errno
import gzip
import http.client
import importlib
import io
import json
import os
import re
import socket
import threading
import time
import urllib.error

import httpx
import pytest

import proxy
import recorder_streams


def _proxy():
    import proxy

    return importlib.reload(proxy)


def test_build_forward_headers_injects_auth_when_key_present():
    proxy = _proxy()
    headers = {"Content-Type": "application/json", "Authorization": "Bearer sk-dummy", "Host": "x"}
    out = proxy.build_forward_headers(headers, "sk-real")
    assert out["Authorization"] == "Bearer sk-real"
    assert "Host" not in out


def test_build_forward_headers_preserves_auth_when_no_key():
    proxy = _proxy()
    headers = {"Content-Type": "application/json", "Authorization": "Bearer sk-dummy"}
    out = proxy.build_forward_headers(headers, "")
    assert out["Authorization"] == "Bearer sk-dummy"


def test_build_forward_headers_drops_hop_by_hop():
    proxy = _proxy()
    headers = {
        "Content-Length": "5",
        "Connection": "keep-alive",
        "Accept-Encoding": "gzip",
        "X-Title": "t",
    }
    out = proxy.build_forward_headers(headers, "")
    for h in ("Content-Length", "Connection", "Accept-Encoding"):
        assert h not in out
    assert out["X-Title"] == "t"


def test_transcript_dir_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSCRIPT_DIR", str(tmp_path))
    import proxy

    proxy = importlib.reload(proxy)
    assert os.path.dirname(proxy.TRANSCRIPT_FILE) == str(tmp_path)


def test_build_forward_headers_drops_uppercase_host():
    proxy = _proxy()
    out = proxy.build_forward_headers({"HOST": "evil", "X-Title": "t"}, "")
    assert "HOST" not in out and "Host" not in out
    assert out["X-Title"] == "t"


def test_archive_name_is_timestamped_gz():
    proxy = _proxy()
    name = proxy.archive_name("/t/agent_life_transcript.jsonl", stamp="20260813_101500")
    assert name == "/t/agent_life_transcript-20260813_101500.jsonl.gz"


def test_archive_name_default_stamp_is_compact_utc():
    proxy = _proxy()
    name = proxy.archive_name("/t/agent_life_transcript.jsonl")
    stamp = name[len("/t/agent_life_transcript-") : -len(".jsonl.gz")]
    assert re.fullmatch(r"\d{8}_\d{6}", stamp)


def test_rotate_if_needed_below_threshold_is_noop(tmp_path):
    proxy = _proxy()
    live = tmp_path / "agent_life_transcript.jsonl"
    live.write_text('{"a": 1}\n' * 10, encoding="utf-8")
    result = proxy.rotate_if_needed(str(live), max_bytes=10_000)
    assert result is None
    assert live.read_text(encoding="utf-8") == '{"a": 1}\n' * 10
    assert list(tmp_path.glob("*.gz")) == []


def test_rotate_if_needed_archives_and_truncates(tmp_path):
    import gzip

    proxy = _proxy()
    live = tmp_path / "agent_life_transcript.jsonl"
    original = '{"a": 1}\n' * 1000
    live.write_text(original, encoding="utf-8")
    result = proxy.rotate_if_needed(str(live), max_bytes=100)
    assert result is not None and result.endswith(".jsonl.gz")
    with gzip.open(result, "rt", encoding="utf-8") as f:
        assert f.read() == original
    assert live.read_text(encoding="utf-8") == ""
    with open(live, "a", encoding="utf-8") as f:
        f.write('{"b": 2}\n')
    assert live.read_text(encoding="utf-8") == '{"b": 2}\n'
    assert not list(tmp_path.glob("*.tmp"))


def test_rotate_if_needed_missing_file_is_noop(tmp_path):
    proxy = _proxy()
    result = proxy.rotate_if_needed(str(tmp_path / "absent.jsonl"), max_bytes=1)
    assert result is None


def test_rotate_if_needed_failure_leaves_live_file_intact(tmp_path, monkeypatch):
    proxy = _proxy()
    live = tmp_path / "agent_life_transcript.jsonl"
    original = '{"a": 1}\n' * 100
    live.write_text(original, encoding="utf-8")

    def broken_rename(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(proxy.os, "rename", broken_rename)
    result = proxy.rotate_if_needed(str(live), max_bytes=100)
    assert result is None
    assert live.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob("*.tmp"))


def test_rotate_if_needed_non_oserror_is_contained(tmp_path, monkeypatch):
    proxy = _proxy()
    live = tmp_path / "agent_life_transcript.jsonl"
    original = '{"a": 1}\n' * 100
    live.write_text(original, encoding="utf-8")

    def broken_copyfileobj(src, dst, bufsize):
        raise RuntimeError("zlib boom")

    monkeypatch.setattr(proxy.shutil, "copyfileobj", broken_copyfileobj)
    result = proxy.rotate_if_needed(str(live), max_bytes=100)
    assert result is None
    assert live.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob("*.tmp"))


def test_rotate_if_needed_never_overwrites_an_existing_archive(tmp_path, monkeypatch):
    proxy = _proxy()
    live = tmp_path / "agent_life_transcript.jsonl"
    live.write_text('{"a": 1}\n' * 100, encoding="utf-8")
    monkeypatch.setattr(
        proxy, "archive_name", lambda path, stamp=None: str(tmp_path / "fixed.jsonl.gz")
    )
    first = proxy.rotate_if_needed(str(live), max_bytes=10)
    assert first == str(tmp_path / "fixed.jsonl.gz")
    live.write_text('{"b": 2}\n' * 100, encoding="utf-8")
    second = proxy.rotate_if_needed(str(live), max_bytes=10)
    assert second is None
    assert live.read_text(encoding="utf-8") == '{"b": 2}\n' * 100
    import gzip

    with gzip.open(str(tmp_path / "fixed.jsonl.gz"), "rt", encoding="utf-8") as f:
        assert f.read() == '{"a": 1}\n' * 100


@pytest.fixture
def stream_env(monkeypatch):
    for var in (
        "STREAM_MODEL_ALLOW_TEXT",
        "STREAM_MODEL_ALLOW_VISION",
        "STREAM_UPSTREAM_URL",
        "STREAM_HOURLY_MAX",
        "STREAM_TOKEN_HOURLY_MAX",
        "LLM_BASE_URL",
        "LLM_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-stream-test")
    return monkeypatch


@pytest.fixture
def transcripts(tmp_path, monkeypatch):
    monkeypatch.setattr(proxy, "TRANSCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(proxy, "TRANSCRIPT_FILE", str(tmp_path / "transcript.jsonl"))
    monkeypatch.setattr(proxy, "PLAIN_TRANSCRIPT_FILE", str(tmp_path / "transcript.txt"))
    monkeypatch.setattr(proxy, "EVENTS_FILE", str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(proxy, "_active_bindings", set())
    return tmp_path


class _BufferedResponse:
    status = 200

    def __init__(self, body):
        self._body = body

    def read(self, size=-1):
        body, self._body = self._body, b""
        return body

    def getheaders(self):
        return [("Content-Type", "application/json")]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _StreamingResponse:
    status = 200

    def __init__(self, pieces, gate=None, gate_after=1, fail_after=None):
        self._pieces = list(pieces)
        self._served = 0
        self._gate = gate
        self._gate_after = gate_after
        self._fail_after = fail_after

    def read1(self, size=-1):
        if self._gate is not None and self._served == self._gate_after:
            self._gate.wait(10)
        if self._fail_after is not None and self._served == self._fail_after:
            raise OSError("upstream went away")
        if self._served >= len(self._pieces):
            return b""
        piece = self._pieces[self._served]
        self._served += 1
        return piece

    def getheaders(self):
        return [("Content-Type", "text/event-stream")]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def upstream(monkeypatch):
    """Serve one prepared upstream response; tests swap in their own."""
    holder = {
        "response": lambda: _BufferedResponse(
            json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode("utf-8")
        ),
        "seen": {},
    }

    def fake_urlopen(request, timeout=None):
        holder["seen"]["data"] = request.data
        holder["seen"]["url"] = request.full_url
        return holder["response"]()

    monkeypatch.setattr("proxy.forward_open", fake_urlopen)
    return holder


@pytest.fixture
def core_server(tmp_path, transcripts, stream_env, upstream, registry):
    # Attached exactly as main() attaches them, so the `stream != "core"` guards
    # on admission and charging are live under test. Without a registry here
    # they are dead code and removing them fails nothing.
    path = str(tmp_path / "core.sock")
    instance = proxy.UnixHTTPServer(path, proxy.ProxyHTTPRequestHandler)
    instance.stream_name = "core"
    instance.registry = registry
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield path
    instance.shutdown()
    instance.server_close()


@pytest.fixture
def registry():
    return recorder_streams.StreamRegistry()


@pytest.fixture
def stream_factory(tmp_path, transcripts, stream_env, upstream, registry):
    servers = []

    def make(**declaration):
        settings = {"budget": 100}
        settings.update(declaration)
        registry.apply({"aux": settings}, {})
        path = str(tmp_path / "aux.sock")
        instance = proxy.UnixHTTPServer(path, proxy.ProxyHTTPRequestHandler)
        instance.stream_name = "aux"
        instance.registry = registry
        servers.append(instance)
        threading.Thread(target=instance.serve_forever, daemon=True).start()
        return path

    yield make
    for instance in servers:
        instance.shutdown()
        instance.server_close()


def _event(payload):
    return "data: " + json.dumps(payload) + "\n\n"


def _post(path, payload):
    transport = httpx.HTTPTransport(uds=path)
    with httpx.Client(transport=transport, base_url="http://localhost") as client:
        return client.post("/api/v1/chat/completions", json=payload, timeout=10)


def _connect(path):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(10)
    client.connect(path)
    return client


def _raw_request(payload, route="/api/v1/chat/completions", extra=()):
    body = json.dumps(payload).encode("utf-8")
    lines = [
        f"POST {route} HTTP/1.1",
        "Host: localhost",
        "Content-Type: application/json",
        f"Content-Length: {len(body)}",
    ]
    lines.extend(extra)
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii") + body


def _read_head(fp):
    status = fp.readline().decode("latin-1").rstrip("\r\n")
    headers = {}
    while True:
        line = fp.readline().decode("latin-1").rstrip("\r\n")
        if not line:
            break
        key, _, value = line.partition(":")
        headers[key.strip().lower()] = value.strip()
    return status, headers


def _read_chunk(fp):
    size = int(fp.readline().decode("latin-1").strip(), 16)
    if size == 0:
        fp.readline()
        return b""
    piece = fp.read(size)
    fp.readline()
    return piece


def _read_message(fp):
    status, headers = _read_head(fp)
    if headers.get("transfer-encoding") == "chunked":
        body = b""
        while True:
            piece = _read_chunk(fp)
            if not piece:
                break
            body += piece
    else:
        body = fp.read(int(headers.get("content-length", 0)))
    return status, headers, body


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    value = predicate()
    while not value and time.monotonic() < deadline:
        time.sleep(0.01)
        value = predicate()
    return value


def _lines(path):
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    return [json.loads(line) for line in text.splitlines() if line]


def _entries(transcripts):
    return _lines(transcripts / "transcript.jsonl")


def _events(transcripts):
    return _lines(transcripts / "events.jsonl")


def _used_tokens(registry):
    return registry.state(streams_enabled=True)["streams"]["aux"]["tokens"]["used"]


def test_the_handler_speaks_http_1_1_with_a_bounded_idle_timeout():
    assert proxy.ProxyHTTPRequestHandler.protocol_version == "HTTP/1.1"
    assert proxy.ProxyHTTPRequestHandler.timeout == 300


def test_a_non_streamed_response_is_framed_by_content_length(core_server):
    client = _connect(core_server)
    try:
        client.sendall(_raw_request({"model": "m", "messages": []}))
        fp = client.makefile("rb")
        status, headers, body = _read_message(fp)
    finally:
        client.close()

    assert status.startswith("HTTP/1.1 200")
    assert headers["content-length"] == str(len(body))
    assert "transfer-encoding" not in headers
    assert json.loads(body)["choices"][0]["message"]["content"] == "hi"


def test_two_requests_share_one_connection(core_server):
    client = _connect(core_server)
    try:
        fp = client.makefile("rb")
        for _ in range(2):
            client.sendall(_raw_request({"model": "m", "messages": []}))
            status, headers, body = _read_message(fp)
            assert status.startswith("HTTP/1.1 200")
            assert headers.get("connection", "").lower() != "close"
            assert json.loads(body)["choices"][0]["message"]["content"] == "hi"
    finally:
        client.close()


def test_an_unknown_route_is_framed_and_closes_the_connection(core_server):
    client = _connect(core_server)
    try:
        client.sendall(_raw_request({"model": "m"}, route="/api/v1/other"))
        fp = client.makefile("rb")
        status, headers, body = _read_message(fp)
    finally:
        client.close()

    assert status.startswith("HTTP/1.1 404")
    assert headers["content-length"] == str(len(body))
    assert headers.get("connection", "").lower() == "close"


def test_reconstruction_skips_the_terminator_and_undecodable_events():
    chunks = [
        _event({"choices": [{"index": 0, "delta": {"content": "a"}}]}),
        "data: {not json\n\n",
        ": keep-alive comment\n\n",
        "data: [DONE]\n\n",
    ]
    completion = proxy.reconstruct_completion(chunks)
    assert completion["choices"][0]["message"]["content"] == "a"


def test_reconstruction_reads_an_event_split_across_pieces():
    text = _event({"choices": [{"index": 0, "delta": {"content": "split"}}]})
    completion = proxy.reconstruct_completion([text[:12], text[12:]])
    assert completion["choices"][0]["message"]["content"] == "split"


def test_reconstruction_reads_a_trailing_event_without_a_newline():
    text = _event({"choices": [{"index": 0, "delta": {"content": "tail"}}]}).rstrip("\n")
    completion = proxy.reconstruct_completion([text])
    assert completion["choices"][0]["message"]["content"] == "tail"


def test_stream_record_holds_the_completion_and_not_the_body(monkeypatch):
    # The recorder used to hold the whole streamed body several times over
    # while it relayed and then re-parsed it. The record is fed each piece as
    # it passes and keeps what the deltas describe, plus a bounded prefix of
    # the raw bytes for a body that carries no events.
    monkeypatch.setattr(proxy, "STREAM_RETAIN_BYTES", 4096)
    record = proxy.StreamRecord()
    for i in range(500):
        record.feed(_event({"choices": [{"index": 0, "delta": {"content": f"{i:03d} "}}]}).encode())
    record.feed(b"data: [DONE]\n\n")
    record.finish()

    completion = record.completion()
    assert completion["choices"][0]["message"]["content"] == "".join(
        f"{i:03d} " for i in range(500)
    )
    assert record.raw_bytes > 4096
    assert len(record.raw) <= 4096
    assert record.raw_truncated is True
    assert record.events == 500


def test_stream_record_drops_an_oversized_line_and_resumes(monkeypatch):
    monkeypatch.setattr(proxy, "STREAM_RETAIN_BYTES", 256)
    record = proxy.StreamRecord()
    record.feed(b"data: " + b"x" * 1000)
    record.feed(b"y" * 1000 + b"\n\n")
    record.feed(_event({"choices": [{"index": 0, "delta": {"content": "after"}}]}).encode())
    record.finish()

    assert record.completion()["choices"][0]["message"]["content"] == "after"
    assert record.events == 1


def test_reconstruct_completion_concatenates_content_and_reasoning():
    chunks = [
        _event(
            {
                "id": "c1",
                "model": "m",
                "created": 7,
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": "he"}}],
            }
        ),
        _event({"choices": [{"index": 0, "delta": {"reasoning": "be"}}]}),
        _event({"choices": [{"index": 0, "delta": {"content": "llo", "reasoning": "cause"}}]}),
        "data: [DONE]\n\n",
    ]
    completion = proxy.reconstruct_completion(chunks)
    assert completion["id"] == "c1"
    assert completion["model"] == "m"
    assert completion["created"] == 7
    assert completion["object"] == "chat.completion"
    message = completion["choices"][0]["message"]
    assert message["role"] == "assistant"
    assert message["content"] == "hello"
    assert message["reasoning"] == "because"


def test_reconstruct_completion_keeps_the_reasoning_field_name_the_deltas_used():
    chunks = [_event({"choices": [{"index": 0, "delta": {"reasoning_content": "why"}}]})]
    message = proxy.reconstruct_completion(chunks)["choices"][0]["message"]
    assert message["reasoning_content"] == "why"
    assert "reasoning" not in message


def test_reconstruct_completion_reassembles_tool_calls_by_index():
    chunks = [
        _event(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_a",
                                    "type": "function",
                                    "function": {"name": "write_file", "arguments": '{"co'},
                                }
                            ]
                        },
                    }
                ]
            }
        ),
        _event(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 1,
                                    "id": "call_b",
                                    "function": {"name": "validate", "arguments": "{}"},
                                }
                            ]
                        },
                    }
                ]
            }
        ),
        _event(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [{"index": 0, "function": {"arguments": 'ntent": 1}'}}]
                        },
                    }
                ]
            }
        ),
    ]
    message = proxy.reconstruct_completion(chunks)["choices"][0]["message"]
    assert message["content"] is None
    assert message["tool_calls"] == [
        {
            "id": "call_a",
            "type": "function",
            "function": {"name": "write_file", "arguments": '{"content": 1}'},
        },
        {
            "id": "call_b",
            "type": "function",
            "function": {"name": "validate", "arguments": "{}"},
        },
    ]


def test_reconstruct_completion_carries_finish_reason_and_usage():
    chunks = [
        _event({"choices": [{"index": 0, "delta": {"content": "x"}, "finish_reason": None}]}),
        _event({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}),
        _event({"choices": [], "usage": {"prompt_tokens": 3, "total_tokens": 9}}),
        "data: [DONE]\n\n",
    ]
    completion = proxy.reconstruct_completion(chunks)
    assert completion["choices"][0]["finish_reason"] == "tool_calls"
    assert completion["usage"] == {"prompt_tokens": 3, "total_tokens": 9}


def test_reconstruct_completion_keeps_choices_apart():
    chunks = [
        _event(
            {
                "choices": [
                    {"index": 1, "delta": {"content": "second"}},
                    {"index": 0, "delta": {"content": "first"}},
                ]
            }
        )
    ]
    completion = proxy.reconstruct_completion(chunks)
    assert [choice["index"] for choice in completion["choices"]] == [0, 1]
    assert completion["choices"][0]["message"]["content"] == "first"
    assert completion["choices"][1]["message"]["content"] == "second"


def test_iter_response_chunks_reads_a_real_http_response_incrementally():
    server_side, client_side = socket.socketpair()
    try:
        server_side.sendall(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/event-stream\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n"
            b"5\r\nfirst\r\n6\r\nsecond\r\n0\r\n\r\n"
        )
        server_side.close()
        response = http.client.HTTPResponse(client_side)
        response.begin()
        pieces = list(proxy.iter_response_chunks(response))
    finally:
        client_side.close()
    assert b"".join(pieces) == b"firstsecond"
    assert len(pieces) >= 2


def test_relay_chunks_frames_each_piece_and_terminates():
    written = []

    class _Writer:
        def write(self, data):
            written.append(data)

    record = proxy.StreamRecord()
    error = proxy.relay_chunks(_Writer(), _StreamingResponse([b"ab", b"cde"]), record)
    assert error is None
    assert record.raw == b"abcde"
    assert written == [b"2\r\nab\r\n", b"3\r\ncde\r\n", b"0\r\n\r\n"]


def test_relay_chunks_writes_no_terminator_after_a_failed_write():
    written = []

    class _Writer:
        def write(self, data):
            if len(written) == 1:
                raise BrokenPipeError("client went away")
            written.append(data)

    record = proxy.StreamRecord()
    error = proxy.relay_chunks(_Writer(), _StreamingResponse([b"ab", b"cde"]), record)
    assert isinstance(error, BrokenPipeError)
    assert record.raw == b"abcde"
    assert written == [b"2\r\nab\r\n"]


def test_a_streamed_response_reaches_the_client_incrementally(stream_factory, upstream):
    gate = threading.Event()
    pieces = [
        _event({"choices": [{"index": 0, "delta": {"content": "first"}}]}).encode("utf-8"),
        _event({"choices": [{"index": 0, "delta": {"content": "second"}}]}).encode("utf-8"),
        b"data: [DONE]\n\n",
    ]
    upstream["response"] = lambda: _StreamingResponse(pieces, gate=gate, gate_after=1)
    path = stream_factory()

    client = _connect(path)
    try:
        client.sendall(_raw_request({"model": "m", "messages": [], "stream": True}))
        fp = client.makefile("rb")
        status, headers = _read_head(fp)
        assert status.startswith("HTTP/1.1 200")
        assert headers["transfer-encoding"] == "chunked"
        assert "content-length" not in headers
        assert _read_chunk(fp) == pieces[0]
        gate.set()
        rest = b""
        while True:
            piece = _read_chunk(fp)
            if not piece:
                break
            rest += piece
        assert rest == pieces[1] + pieces[2]
    finally:
        gate.set()
        client.close()


def test_a_streamed_exchange_is_recorded_like_a_buffered_one(
    stream_factory, upstream, transcripts, registry
):
    pieces = [
        _event(
            {
                "id": "c1",
                "model": "m",
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": "part "}}],
            }
        ).encode("utf-8"),
        _event(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_a",
                                    "type": "function",
                                    "function": {"name": "read_file", "arguments": "{"},
                                }
                            ]
                        },
                    }
                ]
            }
        ).encode("utf-8"),
        _event(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "}"}}]},
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        ).encode("utf-8"),
        _event(
            {
                "choices": [],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        ).encode("utf-8"),
        b"data: [DONE]\n\n",
    ]
    upstream["response"] = lambda: _StreamingResponse(pieces)
    path = stream_factory()

    response = _post(path, {"model": "m", "messages": [], "stream": True})
    assert response.status_code == 200

    entries = _wait_until(lambda: _entries(transcripts))
    (entry,) = entries
    assert entry["stream"] == "aux"
    message = entry["response"]["choices"][0]["message"]
    assert message["content"] == "part "
    assert message["tool_calls"] == [
        {"id": "call_a", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
    ]
    assert entry["response"]["choices"][0]["finish_reason"] == "tool_calls"
    assert entry["response"]["usage"]["total_tokens"] == 15

    # The close event follows the transcript line, which it reports on (plan 4b), so it is
    # waited for like the line itself.
    closes = _wait_until(
        lambda: [event for event in _events(transcripts) if event["event"] == "close"]
    )
    assert closes[-1]["usage"]["total_tokens"] == 15
    assert _wait_until(lambda: _used_tokens(registry) == 15)


def test_a_streamed_declared_request_asks_the_upstream_for_usage(stream_factory, upstream):
    upstream["response"] = lambda: _StreamingResponse([b"data: [DONE]\n\n"])
    path = stream_factory()
    _post(path, {"model": "m", "messages": [], "stream": True})
    forwarded = json.loads(upstream["seen"]["data"].decode("utf-8"))
    assert forwarded["stream_options"]["include_usage"] is True


def test_a_streamed_response_without_usage_keeps_its_reservation(
    stream_factory, upstream, registry, transcripts
):
    # No usage event arrived, so the reservation admission took stands rather
    # than being released. Releasing it would make truncating a stream a way to
    # spend against the recorder's key without being metered.
    upstream["response"] = lambda: _StreamingResponse(
        [_event({"choices": [{"index": 0, "delta": {"content": "x"}}]}).encode("utf-8")]
    )
    path = stream_factory(max_tokens=128, reasoning_effort="none")
    _post(path, {"model": "m", "messages": [], "stream": True})
    assert _wait_until(lambda: _used_tokens(registry) >= 128)


def test_a_stream_broken_mid_relay_keeps_its_reservation(
    stream_factory, upstream, registry, transcripts
):
    upstream["response"] = lambda: _StreamingResponse(
        [_event({"choices": [{"index": 0, "delta": {"content": "x"}}]}).encode("utf-8")],
        fail_after=1,
    )
    path = stream_factory(max_tokens=64, reasoning_effort="none")
    try:
        _post(path, {"model": "m", "messages": [], "stream": True})
    except httpx.HTTPError:
        pass
    assert _wait_until(lambda: _used_tokens(registry) >= 64)


def test_a_response_without_usage_keeps_its_reservation(
    stream_factory, upstream, registry, transcripts
):
    # An upstream that reports no usage leaves the spend unknown, streamed or
    # not. The reservation is what admission already counted against the
    # window, so it stays; releasing it would hand back capacity that may well
    # have been consumed.
    path = stream_factory(max_tokens=128, reasoning_effort="none")
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 200
    _wait_until(lambda: _entries(transcripts))
    assert _used_tokens(registry) >= 128


def test_a_non_streamed_response_charges_its_reported_usage(
    stream_factory, upstream, registry, transcripts
):
    upstream["response"] = lambda: _BufferedResponse(
        json.dumps(
            {"choices": [{"message": {"content": "hi"}}], "usage": {"total_tokens": 42}}
        ).encode("utf-8")
    )
    path = stream_factory()
    _post(path, {"model": "m", "messages": []})
    assert _wait_until(lambda: _used_tokens(registry) == 42)


def test_core_forwards_a_streamed_body_verbatim(core_server, upstream, transcripts):
    upstream["response"] = lambda: _StreamingResponse([b"data: [DONE]\n\n"])
    body = b'{"model": "m", "messages": [], "stream": true}'
    transport = httpx.HTTPTransport(uds=core_server)
    with httpx.Client(transport=transport, base_url="http://localhost") as client:
        response = client.post(
            "/api/v1/chat/completions",
            content=body,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
    assert response.status_code == 200
    assert upstream["seen"]["data"] == body


def test_headers_never_reach_the_transcript_or_events(stream_factory, upstream, transcripts):
    upstream["response"] = lambda: _StreamingResponse(
        [
            _event({"choices": [{"index": 0, "delta": {"content": "x"}}]}).encode("utf-8"),
            b"data: [DONE]\n\n",
        ]
    )
    path = stream_factory()
    transport = httpx.HTTPTransport(uds=path)
    with httpx.Client(transport=transport, base_url="http://localhost") as client:
        client.post(
            "/api/v1/chat/completions",
            json={"model": "m", "messages": [], "stream": True},
            headers={"Authorization": "Bearer sk-secret-token", "X-Title": "secret-title"},
            timeout=10,
        )
    names = ("transcript.jsonl", "transcript.txt", "events.jsonl")
    assert _wait_until(lambda: all((transcripts / name).exists() for name in names))
    for name in names:
        text = (transcripts / name).read_text(encoding="utf-8")
        assert "sk-secret-token" not in text
        assert "secret-title" not in text
        assert "authorization" not in text.lower()


def _record(text):
    record = proxy.StreamRecord()
    record.feed(text.encode("utf-8"))
    record.finish()
    return record


def test_stream_response_data_reassembles_the_deltas():
    text = _event({"choices": [{"index": 0, "delta": {"content": "hi"}}]})
    assert proxy.stream_response_data(_record(text))["choices"][0]["message"]["content"] == "hi"


def test_stream_response_data_keeps_a_body_that_carried_no_events():
    assert proxy.stream_response_data(_record('{"error": {"message": "no"}}')) == {
        "error": {"message": "no"}
    }
    assert proxy.stream_response_data(_record("data: {broken\n\n")) == {
        "raw_body": "data: {broken\n\n"
    }


def test_stream_response_data_notes_a_raw_body_it_could_not_keep_whole(monkeypatch):
    monkeypatch.setattr(proxy, "STREAM_RETAIN_BYTES", 8)
    data = proxy.stream_response_data(_record("0123456789abcdef"))
    assert data == {"raw_body": "01234567", "raw_body_truncated": True}


def test_an_upstream_error_event_reaches_the_transcript(
    stream_factory, upstream, transcripts, registry
):
    upstream["response"] = lambda: _StreamingResponse(
        [_event({"error": {"message": "upstream refused"}}).encode("utf-8")]
    )
    path = stream_factory()
    _post(path, {"model": "m", "messages": [], "stream": True})
    entries = _wait_until(lambda: _entries(transcripts))
    assert "upstream refused" in json.dumps(entries[0]["response"])


def test_a_streamed_response_leaves_the_connection_usable(stream_factory, upstream):
    pieces = [
        _event({"choices": [{"index": 0, "delta": {"content": "x"}}]}).encode("utf-8"),
        b"data: [DONE]\n\n",
    ]
    upstream["response"] = lambda: _StreamingResponse(pieces)
    path = stream_factory(max_tokens=10)

    client = _connect(path)
    try:
        fp = client.makefile("rb")
        for _ in range(2):
            client.sendall(_raw_request({"model": "m", "messages": [], "stream": True}))
            status, headers, body = _read_message(fp)
            assert status.startswith("HTTP/1.1 200")
            assert headers["transfer-encoding"] == "chunked"
            assert body == b"".join(pieces)
    finally:
        client.close()


def test_a_refusal_leaves_the_connection_usable(stream_factory, upstream):
    path = stream_factory(budget=1, max_tokens=10)
    client = _connect(path)
    try:
        fp = client.makefile("rb")
        client.sendall(_raw_request({"model": "m", "messages": []}))
        status, headers, body = _read_message(fp)
        assert status.startswith("HTTP/1.1 200")

        client.sendall(_raw_request({"model": "m", "messages": []}))
        status, headers, body = _read_message(fp)
        assert status.startswith("HTTP/1.1 429")
        assert headers["content-length"] == str(len(body))
        assert "request(s) per hour" in json.loads(body)["error"]["message"]
    finally:
        client.close()


def test_a_relay_that_cannot_send_its_headers_closes_the_connection():
    class _Broken(proxy.ProxyHTTPRequestHandler):
        def __init__(self):
            self.close_connection = False

        def send_response(self, code, message=None):
            raise BrokenPipeError("client went away")

    handler = _Broken()
    record = handler._relay(200, [], _StreamingResponse([b"x"]))
    assert record.raw == b"" and record.events == 0
    assert handler.close_connection is True


def test_a_refused_body_leaves_the_connection_usable(stream_factory, upstream):
    path = stream_factory()
    client = _connect(path)
    try:
        fp = client.makefile("rb")
        body = b"[1, 2]"
        client.sendall(
            b"POST /api/v1/chat/completions HTTP/1.1\r\nHost: localhost\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
        )
        status, headers, payload = _read_message(fp)
        assert status.startswith("HTTP/1.1 400")
        assert headers["content-length"] == str(len(payload))
        assert json.loads(payload)["error"]["message"] == "request body is not a json object"

        client.sendall(_raw_request({"model": "m", "messages": []}))
        status, headers, payload = _read_message(fp)
        assert status.startswith("HTTP/1.1 200")
        assert json.loads(payload)["choices"][0]["message"]["content"] == "hi"
    finally:
        client.close()


def test_core_is_neither_admitted_nor_charged(core_server, registry, transcripts):
    # core.sock is uncapped by design (CLAUDE.md invariant 3): the key budget is
    # its ceiling. With a registry attached, dropping either `stream != "core"`
    # guard would start metering it, so this pins the exemption itself rather
    # than relying on "core" being a reserved declaration name.
    registry.apply({"aux": {"budget": 1, "token_budget": 1}}, {})

    for _ in range(3):
        client = _connect(core_server)
        try:
            client.sendall(_raw_request({"model": "m", "messages": []}))
            fp = client.makefile("rb")
            status, _, _ = _read_message(fp)
        finally:
            client.close()
        assert status.startswith("HTTP/1.1 200")

    # core is always listed as a socket, but carries no allowance of either
    # kind and accrues no history.
    reported = registry.state()["streams"]["core"]
    assert "budget" not in reported and "tokens" not in reported
    assert registry._token_histories.get("core", []) == []
    assert registry._histories.get("core", []) == []


def test_a_chunked_request_body_is_refused_and_closes_the_connection(core_server):
    # HTTP/1.1 keeps the connection open, but the request body is framed by
    # Content-Length alone. A chunked request body would otherwise leave its
    # bytes in the socket to be parsed as the next request line.
    client = _connect(core_server)
    try:
        client.sendall(
            b"POST /api/v1/chat/completions HTTP/1.1\r\n"
            b"Host: agent\r\n"
            b"Content-Type: application/json\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"\r\n"
            b"5\r\nhello\r\n0\r\n\r\n"
        )
        fp = client.makefile("rb")
        status, headers, body = _read_message(fp)
        trailing = fp.read()
    finally:
        client.close()

    assert status.startswith("HTTP/1.1 411")
    assert headers.get("connection") == "close"
    assert b"chunked" in body.lower() or b"length" in body.lower()
    assert trailing == b""


def test_a_request_body_above_the_cap_is_refused_and_closes_the_connection(
    core_server, monkeypatch, upstream
):
    # Content-Length is the agent's to set, and the recorder read the whole
    # body into memory before doing anything else with it. The cap keeps a
    # single request from taking the recorder past its memory limit; the
    # unread body is left in the socket, so the connection closes.
    monkeypatch.setattr(proxy, "REQUEST_MAX_BYTES", 64)
    payload = {"model": "m", "messages": [{"role": "user", "content": "x" * 200}]}
    client = _connect(core_server)
    try:
        client.sendall(_raw_request(payload))
        fp = client.makefile("rb")
        status, headers, body = _read_message(fp)
        trailing = fp.read()
    finally:
        client.close()

    assert status.startswith("HTTP/1.1 413")
    assert headers.get("connection") == "close"
    assert b"64" in body
    assert trailing == b""
    assert "data" not in upstream["seen"]


def test_a_request_body_at_the_cap_is_forwarded(core_server, monkeypatch, upstream):
    monkeypatch.setattr(proxy, "REQUEST_MAX_BYTES", 4096)
    payload = {"model": "m", "messages": [{"role": "user", "content": "x" * 100}]}
    response = _post(core_server, payload)
    assert response.status_code == 200
    assert json.loads(upstream["seen"]["data"]) == payload


def test_an_upstream_error_releases_the_reservation(stream_factory, upstream, registry):
    # An upstream that answers with an error status generated nothing, so the
    # request settles at zero rather than holding its permitted maximum for
    # the hour; otherwise a run of cheap 400s exhausts the socket's quota.
    def refused(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"error": {"message": "no"}}')
        )

    upstream["response"] = None
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("proxy.forward_open", refused)
        path = stream_factory(max_tokens=400)
        response = _post(path, {"model": "m", "messages": []})

    assert response.status_code == 400
    assert _used_tokens(registry) == 0


def test_a_transport_failure_after_connecting_keeps_its_reservation(stream_factory, upstream, registry):
    # A request that failed in transit after its connection was made may have reached the
    # upstream and been generated; its spend is unknown, so the reservation stands.
    def dropped(request, timeout=None):
        request.deadline.register(None)
        raise OSError("connection reset")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("proxy.forward_open", dropped)
        path = stream_factory(max_tokens=400)
        response = _post(path, {"model": "m", "messages": []})

    assert response.status_code == 500
    assert _used_tokens(registry) >= 400


def test_a_transport_failure_before_connecting_is_refunded(stream_factory, upstream, registry):
    # Nothing reached the upstream, so nothing was generated: the reservation is cancelled.
    def unreachable(request, timeout=None):
        raise OSError("connection refused")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("proxy.forward_open", unreachable)
        path = stream_factory(max_tokens=400)
        response = _post(path, {"model": "m", "messages": []})

    assert response.status_code == 500
    assert _used_tokens(registry) == 0


def test_a_close_event_carries_cache_usage_fields(core_server, upstream, transcripts):
    upstream["response"] = lambda: _BufferedResponse(
        json.dumps(
            {
                "choices": [{"message": {"content": "hi"}}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 5,
                    "total_tokens": 105,
                    "cache_discount": 0.0009,
                    "prompt_tokens_details": {"cached_tokens": 90, "cache_write_tokens": 10},
                },
            }
        ).encode("utf-8")
    )

    response = _post(core_server, {"model": "m", "messages": []})
    assert response.status_code == 200

    closes = _wait_until(
        lambda: [event for event in _events(transcripts) if event["event"] == "close"]
    )
    usage = closes[-1]["usage"]
    assert usage["total_tokens"] == 105
    assert usage["cached_tokens"] == 90
    assert usage["cache_write_tokens"] == 10
    assert usage["cache_discount"] == 0.0009


def test_a_close_event_ignores_malformed_cache_usage_fields(core_server, upstream, transcripts):
    upstream["response"] = lambda: _BufferedResponse(
        json.dumps(
            {
                "choices": [{"message": {"content": "hi"}}],
                "usage": {
                    "total_tokens": 7,
                    "cache_discount": "free",
                    "prompt_tokens_details": {"cached_tokens": None},
                },
            }
        ).encode("utf-8")
    )

    response = _post(core_server, {"model": "m", "messages": []})
    assert response.status_code == 200

    closes = _wait_until(
        lambda: [event for event in _events(transcripts) if event["event"] == "close"]
    )
    usage = closes[-1]["usage"]
    assert usage["total_tokens"] == 7
    assert "cached_tokens" not in usage
    assert "cache_discount" not in usage


# --- upstream error relay -------------------------------------------------

import http.server  # noqa: E402

import openai  # noqa: E402

import chassis  # noqa: E402


class _StubUpstream:
    """A loopback upstream that answers every POST with one prepared response."""

    def __init__(self, status, headers, body):
        outer = self
        self.requests = 0
        self.auth_seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                outer.requests += 1
                outer.auth_seen.append(self.headers.get("Authorization"))
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.send_response(status)
                for k, v in headers:
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/api/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def live_upstream(tmp_path, transcripts, stream_env):
    """Serve a prepared upstream response through the real forwarding opener."""
    created = []
    servers = []

    def make(status, headers, body):
        stub = _StubUpstream(status, headers, body)
        created.append(stub)
        stream_env.setenv("LLM_BASE_URL", stub.url)
        stream_env.setenv("LLM_API_KEY", "sk-real-key")
        path = str(tmp_path / f"core{len(servers)}.sock")
        instance = proxy.UnixHTTPServer(path, proxy.ProxyHTTPRequestHandler)
        instance.stream_name = "core"
        threading.Thread(target=instance.serve_forever, daemon=True).start()
        servers.append(instance)
        return stub, path

    yield make
    for instance in servers:
        instance.shutdown()
        instance.server_close()
    for stub in created:
        stub.close()


def _classify_relayed(response):
    """Classify a relayed error the way the chassis sees it, via the SDK's factory."""
    client = openai.OpenAI(api_key="dummy")
    wire = httpx.Response(
        response.status_code,
        content=response.content,
        request=httpx.Request("POST", "http://upstream.invalid/chat/completions"),
    )
    return chassis.classify_error(client._make_status_error_from_response(wire))


_NOISY = (
    '{"error": {"message": "%s", "type": "t_kind", "code": 1, "metadata": '
    '{"raw": "provider text", "headers": {"cf-ray": "abc"}}}, "user_id": "acct-9"}'
)
_NOISY_HEADERS = [
    ("Content-Type", "application/json"),
    ("Retry-After", "7"),
    ("Set-Cookie", "session=secret"),
    ("CF-Ray", "ray-123"),
    ("X-RateLimit-Remaining", "0"),
    ("X-Account-Id", "acct-9"),
]


def _assert_no_leak(response):
    names = {k.lower() for k in response.headers}
    assert not names & {"set-cookie", "cf-ray", "x-ratelimit-remaining", "x-account-id"}
    for leaked in (b"acct-9", b"provider text", b"cf-ray", b"metadata", b"127.0.0.1"):
        assert leaked not in response.content


def test_an_error_with_a_message_relays_only_the_message(live_upstream, transcripts, capsys):
    body = (_NOISY % "Insufficient credits").encode()
    _, path = live_upstream(402, _NOISY_HEADERS, body)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 402
    assert response.json() == {
        "error": {"message": "Insufficient credits", "code": 402, "type": "t_kind"}
    }
    assert response.headers["retry-after"] == "7"
    _assert_no_leak(response)
    # classification: 402 is transient
    assert _classify_relayed(response) == "transient"
    # the transcript carries the sanitised body; the raw body goes to stderr only
    transcript = (transcripts / "transcript.jsonl").read_text()
    assert "provider text" not in transcript and "acct-9" not in transcript
    assert "ray-123" not in transcript and "Set-Cookie" not in transcript
    err = capsys.readouterr().err
    assert "provider text" in err
    assert "ray-123" not in err and "secret" not in err


def test_an_exhaustion_phrase_still_classifies_as_transient(live_upstream):
    body = b'{"error": {"message": "You exceeded your current quota"}}'
    _, path = live_upstream(429, [("Content-Type", "application/json")], body)
    response = _post(path, {"model": "m", "messages": []})
    assert response.json() == {"error": {"message": "You exceeded your current quota", "code": 429}}
    assert _classify_relayed(response) == "transient"
    # an exhaustion phrase under a status that is otherwise a request fault
    _, path = live_upstream(403, [], b'{"error": {"message": "insufficient_quota"}}')
    assert _classify_relayed(_post(path, {"model": "m", "messages": []})) == "transient"


def test_a_model_error_message_keeps_the_model_swap_path(live_upstream):
    body = b'{"error": {"message": "gpt-x is not a valid model ID"}}'
    _, path = live_upstream(400, [], body)
    response = _post(path, {"model": "m", "messages": []})
    assert _classify_relayed(response) == "model"


@pytest.mark.parametrize(
    "status, body, expected",
    [
        (500, b'{"user_id": "acct-9"}', "transient"),
        (400, b'{"error": {"message": 5}}', "invalid_request"),
        (400, b"[1, 2]", "invalid_request"),
        (503, b"", "transient"),
        (402, b"<html>payment required acct-9</html>", "transient"),
        (400, b"plain words " * 60, "invalid_request"),
        (500, b"<html>Error. Ray ID: acct-9 cf-ray</html>", "transient"),
        (400, b'{"error": {"message": "truncated acct-9", "metadata": ', "invalid_request"),
        # JSON behind a prefix fails json.loads but is no plain message
        (400, b"\xef\xbb\xbf" + (_NOISY % "bom").encode(), "invalid_request"),
        (500, b"data: " + (_NOISY % "sse").encode(), "transient"),
        (400, b")]}'\n" + (_NOISY % "xssi").encode(), "invalid_request"),
    ],
)
def test_an_unparseable_error_relays_the_fixed_body(live_upstream, status, body, expected):
    _, path = live_upstream(status, _NOISY_HEADERS, body)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == status
    assert response.json() == {"error": {"message": "upstream error", "code": status}}
    _assert_no_leak(response)
    assert _classify_relayed(response) == expected


@pytest.mark.parametrize("status", [301, 302, 307])
@pytest.mark.parametrize("shape", ["html", "text", "json"])
def test_a_redirect_is_refused_not_followed_and_not_relayed(
    live_upstream, transcripts, capsys, status, shape
):
    final = _StubUpstream(200, [], b'{"choices": []}')
    try:
        location = final.url + "/final"
        body = {
            "html": f'<a href="{location}">Moved</a>'.encode(),
            "text": f"Redirecting to {location}".encode(),
            "json": json.dumps({"message": f"moved to {location}"}).encode(),
        }[shape]
        _, path = live_upstream(status, [("Location", location)], body)
        response = _post(path, {"model": "m", "messages": []})
    finally:
        final.close()
    assert response.status_code == status
    assert response.json() == {"error": {"message": "upstream error", "code": status}}
    assert "location" not in {k.lower() for k in response.headers}
    relayed = response.content + repr(dict(response.headers)).encode()
    assert b"127.0.0.1" not in relayed and b"/final" not in relayed
    assert location not in (transcripts / "transcript.jsonl").read_text()
    assert final.requests == 0
    assert final.auth_seen == []
    assert location in capsys.readouterr().err
    assert _classify_relayed(response) == "transient"


def test_the_redirect_target_is_logged_capped(live_upstream, capsys):
    long_target = "http://127.0.0.1:9/" + "a" * 5000
    _, path = live_upstream(301, [("Location", long_target)], b"")
    _post(path, {"model": "m", "messages": []})
    err = capsys.readouterr().err
    line = next(x for x in err.splitlines() if "redirect refused" in x)
    assert len(line) < proxy.REDIRECT_LOG_MAX + 100


def test_error_message_and_body_are_capped(live_upstream):
    huge = '{"error": {"message": "%s"}}' % ("m" * 10000)
    _, path = live_upstream(400, [], huge.encode())
    response = _post(path, {"model": "m", "messages": []})
    assert len(response.json()["error"]["message"]) == proxy.ERROR_MESSAGE_MAX
    # a body past the read cap is cut before parsing and gets the fixed body
    over = b'{"error": {"message": "x"}, "pad": "' + b"p" * (proxy.ERROR_BODY_READ_MAX + 10) + b'"}'
    _, path = live_upstream(400, [], over)
    response = _post(path, {"model": "m", "messages": []})
    assert response.json() == {"error": {"message": "upstream error", "code": 400}}
    _assert_no_leak(response)


def test_a_non_string_error_code_falls_through_to_a_top_level_reason(live_upstream):
    body = b'{"error": {"message": "m", "code": 402}, "code": "insufficient_quota"}'
    _, path = live_upstream(400, [], body)
    error = _post(path, {"model": "m", "messages": []}).json()["error"]
    assert error["reason"] == "insufficient_quota"


def test_the_stderr_copy_of_an_error_body_is_capped(live_upstream, capsys):
    _, path = live_upstream(400, [], b"z" * 20000)
    _post(path, {"model": "m", "messages": []})
    err = capsys.readouterr().err
    assert "z" * proxy.ERROR_LOG_MAX in err
    assert "z" * (proxy.ERROR_LOG_MAX + 1) not in err


def test_a_transport_exception_relays_a_fixed_body(live_upstream, monkeypatch, capsys):
    _, path = live_upstream(200, [], b"{}")

    def broken(*args, **kwargs):
        raise OSError("connect to http://10.0.0.5/secret-path failed")

    monkeypatch.setattr("proxy.forward_open", broken)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 500
    assert response.json() == {"error": {"message": "proxy error"}}
    assert b"10.0.0.5" not in response.content
    assert "10.0.0.5" in capsys.readouterr().err


def test_the_success_path_relays_only_allow_listed_headers(live_upstream):
    body = json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode()
    _, path = live_upstream(200, _NOISY_HEADERS, body)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["retry-after"] == "7"
    _assert_no_leak(response)


def test_a_streamed_success_keeps_its_content_type(live_upstream):
    body = b'data: {"choices": [{"delta": {"content": "hi"}}]}\n\ndata: [DONE]\n\n'
    headers = [("Content-Type", "text/event-stream"), ("Set-Cookie", "s=1"), ("CF-Ray", "r")]
    _, path = live_upstream(200, headers, body)
    response = _post(path, {"model": "m", "messages": [], "stream": True})
    assert response.headers["content-type"] == "text/event-stream"
    assert "set-cookie" not in response.headers and "cf-ray" not in response.headers


@pytest.mark.parametrize(
    "status, body, content_type, expected",
    [
        # base classification in the comment; none of these may change
        (403, b'{"detail": "Insufficient credits"}', "application/json", "transient"),
        (403, b"Insufficient credits", "text/plain", "transient"),
        (
            400,
            b'{"error": {"message": "Request denied", "code": "insufficient_quota"}}',
            "application/json",
            "transient",
        ),
        (
            404,
            b'{"object": "error", "message": "The model `x` does not exist."}',
            "application/json",
            "model",
        ),
        (
            403,
            b'{"error": "Insufficient credits", "user_id": "acct-9"}',
            "application/json",
            "transient",
        ),
    ],
)
def test_other_error_shapes_keep_their_classification(
    live_upstream, status, body, content_type, expected
):
    _, path = live_upstream(status, [("Content-Type", content_type)], body)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == status
    assert b"acct-9" not in response.content
    assert _classify_relayed(response) == expected


def test_reason_and_message_sources_are_reduced(live_upstream):
    body = (
        b'{"error": {"message": "m", "code": "' + b"r" * 100 + b'", "metadata": {"raw": "x"}},'
        b' "message": "top", "detail": "d"}'
    )
    _, path = live_upstream(400, [], body)
    error = _post(path, {"model": "m", "messages": []}).json()["error"]
    assert error == {"message": "m", "code": 400, "reason": "r" * 64}


def test_a_model_phrase_only_in_metadata_is_not_relayed(live_upstream):
    # Accepted loss: the phrase lives only in error.metadata.raw, which is
    # never relayed, so the model-swap path is not taken.
    body = (
        b'{"error": {"message": "Provider returned error", "metadata": {"raw": "model not found"}}}'
    )
    _, path = live_upstream(400, [], body)
    response = _post(path, {"model": "m", "messages": []})
    assert _classify_relayed(response) == "invalid_request"


def test_a_surrogate_error_still_settles_the_reservation(stream_factory, registry, monkeypatch):
    def refused(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url,
            400,
            "Bad Request",
            {},
            io.BytesIO(b'{"error": {"message": "\\ud800", "type": "\\udfff"}}'),
        )

    monkeypatch.setattr("proxy.forward_open", refused)
    path = stream_factory(max_tokens=400)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 400
    assert _used_tokens(registry) == 0


def test_the_key_is_redacted_from_the_logged_exception(live_upstream, monkeypatch, capsys):
    _, path = live_upstream(200, [], b"{}")
    monkeypatch.setenv("LLM_API_KEY", "sk-secret-value\n")

    def broken(request, timeout=None):
        raise ValueError(f"bad header {request.get_header('Authorization')!r}")

    monkeypatch.setattr("proxy.forward_open", broken)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 500
    err = capsys.readouterr().err
    assert "sk-secret-value" not in err
    assert "[key]" in err


def test_lone_surrogates_in_message_and_type_relay_without_raising(live_upstream):
    _, path = live_upstream(400, [], b'{"error": {"message": "\\ud800x", "type": "\\udfff"}}')
    error = _post(path, {"model": "m", "messages": []}).json()["error"]
    assert error["message"].endswith("x") and error["type"] == "?"
    _, path = live_upstream(400, [], b'{"error": {"message": 5, "type": "\\ud800"}}')
    error = _post(path, {"model": "m", "messages": []}).json()["error"]
    assert error == {"message": "upstream error", "code": 400, "type": "?"}


# ---------- retention: committed records are never deleted ----------


def _numbered_archives(monkeypatch):
    """Give each rotation its own archive name, as distinct seconds would."""
    counter = iter(range(1, 100))

    def name(path, stamp=None):
        root, ext = os.path.splitext(path)
        return f"{root}-{next(counter):02d}{ext}.gz"

    monkeypatch.setattr(proxy, "archive_name", name)


@pytest.mark.parametrize("live_name", ["transcript.jsonl", "events.jsonl", "transcript.txt"])
def test_every_rotation_leaves_its_archive_beside_the_live_file(tmp_path, monkeypatch, live_name):
    _numbered_archives(monkeypatch)
    live = tmp_path / live_name
    written = []
    for n in range(1, 5):
        text = f"record {n}\n" * 20
        live.write_text(text, encoding="utf-8")
        written.append(text)
        assert proxy.rotate_if_needed(str(live), max_bytes=10) is not None
        assert live.read_text(encoding="utf-8") == ""
    stem, ext = os.path.splitext(live_name)
    archives = sorted(tmp_path.glob(f"{stem}-*{ext}.gz"))
    assert len(archives) == 4
    assert [gzip.open(a, "rt", encoding="utf-8").read() for a in archives] == written
    assert not list(tmp_path.glob("*.tmp"))


def _copy_enospc(monkeypatch, fired):
    """A copy that writes part of the archive, then runs out of space."""
    real = proxy.shutil.copyfileobj

    def copy(src, dst, bufsize):
        dst.write(src.read(8))
        fired.append(os.path.exists(dst.name))
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(proxy.shutil, "copyfileobj", copy)
    return real


@pytest.mark.parametrize("live_name", ["transcript.jsonl", "events.jsonl", "transcript.txt"])
def test_a_rotation_that_runs_out_of_space_commits_nothing_and_keeps_earlier_archives(
    tmp_path, monkeypatch, capsys, live_name
):
    _numbered_archives(monkeypatch)
    live = tmp_path / live_name
    for n in range(1, 3):
        live.write_text(f"earlier {n}\n" * 20, encoding="utf-8")
        assert proxy.rotate_if_needed(str(live), max_bytes=10) is not None
    stem, ext = os.path.splitext(live_name)
    before = {a.name: a.read_bytes() for a in tmp_path.glob(f"{stem}-*{ext}.gz")}
    assert len(before) == 2
    original = "current\n" * 20
    live.write_text(original, encoding="utf-8")
    capsys.readouterr()

    fired = []
    _copy_enospc(monkeypatch, fired)
    assert proxy.rotate_if_needed(str(live), max_bytes=10) is None

    assert fired == [True]  # the failure fired with a partial archive on disk
    assert live.read_text(encoding="utf-8") == original
    assert {a.name: a.read_bytes() for a in tmp_path.glob(f"{stem}-*{ext}.gz")} == before
    assert not list(tmp_path.glob("*.tmp"))
    assert "Error rotating transcript: [Errno 28]" in capsys.readouterr().err


def test_the_only_removals_in_the_recorder_are_its_own_temporary_and_socket_files():
    import ast

    tree = ast.parse(open(proxy.__file__, encoding="utf-8").read())
    removals = []

    def visit(node, function):
        if isinstance(node, ast.FunctionDef):
            function = node.name
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"remove", "unlink", "rmtree", "rmdir", "truncate"}
        ):
            removals.append((function, node.func.attr))
        for child in ast.iter_child_nodes(node):
            visit(child, function)

    visit(tree, "<module>")
    assert ("rotate_if_needed", "remove") in removals
    assert {name for name, _ in removals} == {
        "rotate_if_needed",
        "server_bind",
        "sweep_stale_sockets",
        "bind_stream",
        "poll_once",
        "main",
    }
    assert [kind for name, kind in removals if name != "rotate_if_needed"] == ["unlink"] * 5
    assert [kind for name, kind in removals if name == "rotate_if_needed"] == ["remove"]


# ---------- ENOSPC on every recording path ----------

ENOSPC_BODY = {"choices": [{"message": {"content": "hi"}}], "usage": {"total_tokens": 7}}


class _Full:
    """Makes the nth append (or every open for write) of one file raise ENOSPC."""

    def __init__(self, monkeypatch, path, nth=1):
        self.path, self.nth, self.calls, self.raised = path, nth, 0, 0
        real_open = open

        def guarded(file, mode="r", *args, **kwargs):
            if file == self.path and mode.startswith("a"):
                self.calls += 1
                if self.calls == self.nth:
                    self.raised += 1
                    raise OSError(errno.ENOSPC, "No space left on device")
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(proxy, "open", guarded, raising=False)


def _stderr_until(capsys, text):
    seen = []

    def check():
        seen.append(capsys.readouterr().err)
        return text in "".join(seen)

    assert _wait_until(check), "".join(seen)
    return "".join(seen)


def _assert_forwarded(response):
    assert response.status_code == 200
    assert response.json() == ENOSPC_BODY


@pytest.fixture
def full_upstream(upstream):
    upstream["response"] = lambda: _BufferedResponse(json.dumps(ENOSPC_BODY).encode("utf-8"))
    return upstream


def test_a_full_volume_withholds_the_reply_and_still_charges_it(
    core_server, transcripts, monkeypatch, capsys, full_upstream
):
    # John's rule (plan 4b): every reply an agent acts on is on record, so a reply that cannot be
    # recorded is withheld. The events stay best-effort and still say what happened.
    raised = []

    def full(fd, data):
        raised.append(1)
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(proxy, "_os_write", full)
    monkeypatch.setattr(proxy, "_fenced", set())
    response = _post(core_server, {"model": "m", "messages": []})
    assert response.status_code == 502
    assert response.json()["error"]["message"].startswith("record_failed")
    assert raised
    assert _entries(transcripts) == []
    events = _events(transcripts)
    assert [e["event"] for e in events] == ["open", "close"]
    assert events[-1]["record"] == "failed"
    assert "Error writing event" not in capsys.readouterr().err


def test_a_full_volume_does_not_stop_the_plain_transcript_append(
    core_server, transcripts, monkeypatch, capsys, full_upstream
):
    full = _Full(monkeypatch, str(transcripts / "transcript.txt"))
    response = _post(core_server, {"model": "m", "messages": []})
    _stderr_until(capsys, "Error writing plain transcript: [Errno 28]")
    _assert_forwarded(response)
    assert full.raised == 1
    assert len(_entries(transcripts)) == 1


@pytest.mark.parametrize("nth,survivor", [(1, "close"), (2, "open")])
def test_a_full_volume_does_not_stop_the_open_or_the_close_event(
    core_server, transcripts, monkeypatch, capsys, full_upstream, nth, survivor
):
    full = _Full(monkeypatch, str(transcripts / "events.jsonl"), nth=nth)
    response = _post(core_server, {"model": "m", "messages": []})
    err = _stderr_until(capsys, "Error writing event: [Errno 28]")
    _assert_forwarded(response)
    assert _wait_until(lambda: full.calls == 2)
    assert full.raised == 1
    assert [e["event"] for e in _events(transcripts)] == [survivor]
    assert err.count("Error writing event") == 1
    assert len(_entries(transcripts)) == 1


def test_a_full_volume_loses_the_usage_with_its_close_event_and_nothing_else(
    core_server, transcripts, monkeypatch, capsys, full_upstream
):
    # Usage travels inside the close event; there is no event of its own.
    _Full(monkeypatch, str(transcripts / "events.jsonl"), nth=2)
    response = _post(core_server, {"model": "m", "messages": []})
    _stderr_until(capsys, "Error writing event: [Errno 28]")
    _assert_forwarded(response)
    assert all("usage" not in e for e in _events(transcripts))
    assert _entries(transcripts)[0]["response"]["usage"] == {"total_tokens": 7}


@pytest.mark.parametrize("live", ["transcript.jsonl", "transcript.txt", "events.jsonl"])
def test_a_full_volume_does_not_stop_a_rotation_of_either_file(
    core_server, transcripts, monkeypatch, capsys, full_upstream, live
):
    _numbered_archives(monkeypatch)
    target = str(transcripts / live)
    monkeypatch.setattr(proxy, "TRANSCRIPT_MAX_BYTES", 1 if live != "events.jsonl" else 10**9)
    monkeypatch.setattr(proxy, "EVENTS_MAX_BYTES", 1 if live == "events.jsonl" else 10**9)
    fired = []
    real_copy = proxy.shutil.copyfileobj

    def copy(src, dst, bufsize):
        if os.path.basename(src.name) == live:
            dst.write(src.read(8))
            fired.append(dst.name)
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_copy(src, dst, bufsize)

    monkeypatch.setattr(proxy.shutil, "copyfileobj", copy)
    response = _post(core_server, {"model": "m", "messages": []})
    err = _stderr_until(capsys, "Error rotating transcript: [Errno 28]")
    _assert_forwarded(response)
    assert _wait_until(lambda: os.path.exists(target) and os.path.getsize(target) > 0)
    assert len(fired) >= 1  # the injected failure fired
    assert not list(transcripts.glob("*.tmp"))
    stem, ext = os.path.splitext(live)
    assert not list(transcripts.glob(f"{stem}-*{ext}.gz"))  # no archive of the failed file
    assert os.path.getsize(target) > 0  # the live file still holds its records
    assert "Error rotating transcript" in err
