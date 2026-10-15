"""Fixes from plan 4b's final reviews (Opus and Astra): each test names the gap it closes."""

# ruff: noqa: F811 -- the fixtures are imported from test_proxy by name, and pytest injects them.

import json
import socket
import threading
import time

import proxy
import pytest
import recorder_streams
from test_proxy import (  # noqa: F401 -- fixtures, by name
    ENOSPC_BODY,
    _BufferedResponse,
    _connect,
    _post,
    _raw_request,
    _used_tokens,
    core_server,
    registry,
    stream_env,
    stream_factory,
    transcripts,
    upstream,
)
from test_recorder_deadlines import _read_request, real_upstream  # noqa: F401


def _short_length_reply(conn):
    _read_request(conn)
    conn.sendall(
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 1000\r\n\r\n"
        b'{"choices": []}'
    )


def _short_length_stream(conn):
    _read_request(conn)
    conn.sendall(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: 1000\r\n\r\n"
        b"data: {}\n\n"
    )


def test_a_reply_shorter_than_its_content_length_is_not_relayed_as_complete(
    stream_factory, real_upstream, registry
):
    """Astra: the bounded read returned a short body as if whole, and it went out as a 200."""
    real_upstream(_short_length_reply)
    path = stream_factory(max_tokens=400)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 502
    assert "upstream_incomplete" in response.json()["error"]["message"]
    assert _used_tokens(registry) >= 400, "it reached the upstream, so it is charged"


def test_a_stream_shorter_than_its_content_length_ends_without_a_terminator(
    stream_factory, real_upstream
):
    real_upstream(_short_length_stream)
    path = stream_factory(max_tokens=10)
    client = _connect(path)
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
    client.close()
    assert not received.endswith(b"0\r\n\r\n")


def test_composition_never_leaves_two_keys_that_differ_only_in_case(stream_factory, upstream):
    """Astra and Opus: a composed field was added beside the agent's case variant of it."""
    path = stream_factory(model="declared", max_tokens=10)
    _post(
        path,
        {
            "Model": "agent-choice",
            "messages": [],
            "stream": True,
            "stream_options": {"Include_Usage": False},
        },
    )
    forwarded = upstream["seen"]["data"]
    assert proxy.strict_request(forwarded) is None, forwarded
    data = json.loads(forwarded)
    assert data["model"] == "declared" and "Model" not in data
    assert data["stream_options"] == {"include_usage": True}


def test_the_forwarded_content_type_is_fixed_json(stream_factory, upstream, monkeypatch):
    """Astra: an agent-chosen charset would have the upstream decode other text than recorded."""
    seen = {}
    real = proxy.forward_open

    def capture(request, timeout=None):
        seen.update({k.lower(): v for k, v in request.header_items()})
        return real(request, timeout=timeout)

    monkeypatch.setattr(proxy, "forward_open", capture)
    path = stream_factory(max_tokens=10)
    import httpx

    with httpx.Client(transport=httpx.HTTPTransport(uds=path), base_url="http://localhost") as c:
        c.post(
            "/api/v1/chat/completions",
            content=json.dumps({"model": "m", "messages": []}).encode(),
            headers={"Content-Type": "application/json; charset=iso-8859-1"},
            timeout=10,
        )
    assert seen["content-type"] == "application/json"


@pytest.mark.parametrize(
    "value", [int("9" * 4300), 2**63, -(2**63) - 1], ids=["4300-digits", "2^63", "-2^63-1"]
)
def test_an_integer_outside_64_bits_is_refused(core_server, stream_factory, upstream, value):
    """Astra: 4,300 nines passed validation and then crashed composition's serializer."""
    body = ('{"model":"m","messages":[],"max_tokens":' + str(value) + "}").encode()
    import httpx

    for path in (core_server, stream_factory()):
        with httpx.Client(
            transport=httpx.HTTPTransport(uds=path), base_url="http://localhost"
        ) as c:
            response = c.post(
                "/api/v1/chat/completions",
                content=body,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
        assert response.status_code == 400


def test_a_connect_that_fails_after_the_deadline_fired_is_still_refunded(
    stream_factory, upstream, registry, monkeypatch
):
    """Astra: refund eligibility was computed only when the deadline had not fired."""
    monkeypatch.setattr(proxy, "TIMING", proxy.Timing(upstream=0.5, latest_start=0.4, operation=60))

    def slow_unreachable(request, timeout=None):
        time.sleep(0.8)
        assert request.deadline.fired
        raise TimeoutError("connect timed out")

    monkeypatch.setattr(proxy, "forward_open", slow_unreachable)
    path = stream_factory(max_tokens=400)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 502
    assert _used_tokens(registry) == 0


def test_unknown_usage_at_the_hour_boundary_does_not_drop_the_reservation():
    """Astra: settling with unknown usage before any roll cleared the flight, and the next roll
    then dropped a reservation the hour had to keep."""

    class Clock:
        now = recorder_streams.BUDGET_WINDOW - 1

        def __call__(self):
            return self.now

    clock = Clock()
    registry = recorder_streams.StreamRegistry(clock=clock)
    registry.apply({"aux": {"budget": 5, "max_tokens": 10}}, {})
    _, refusal, ticket = registry.admit("aux", b'{"model": "m", "messages": []}')
    assert refusal is None
    clock.now = recorder_streams.BUDGET_WINDOW + 1
    registry.settle("aux", ticket, None)
    assert registry.state(streams_enabled=True)["shared_tokens"]["used"] > 0


def test_append_record_reports_failure_rather_than_raising(tmp_path, monkeypatch):
    def broken(*args):
        raise OSError(5, "I/O error")

    monkeypatch.setattr(proxy, "_pread", broken)
    path = tmp_path / "t.jsonl"
    path.write_bytes(b"x")
    assert proxy.append_record(str(path), b"{}") == "failed"
    monkeypatch.setattr(proxy, "_fstat", broken)
    assert proxy.append_record(str(path), b"{}") == "failed"


def test_a_broken_stdout_does_not_cost_a_written_record(transcripts, monkeypatch):
    class Broken:
        def write(self, text):
            raise BrokenPipeError

        def flush(self):
            raise BrokenPipeError

    monkeypatch.setattr("sys.stdout", Broken())
    result = proxy.ProxyHTTPRequestHandler.log_transcript(
        None, {"model": "m", "messages": []}, {"choices": []}
    )
    assert result in proxy.READABLE
    assert (transcripts / "transcript.jsonl").read_bytes()


def test_capacity_that_cannot_be_checked_refuses_rather_than_pays(
    stream_factory, upstream, registry, monkeypatch
):
    def unknown(path):
        raise OSError(5, "I/O error")

    monkeypatch.setattr(proxy, "_statvfs", unknown)
    calls = []
    upstream["response"] = lambda: calls.append(1) or _BufferedResponse(b"{}")
    path = stream_factory(max_tokens=400)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 503
    assert calls == [] and _used_tokens(registry) == 0
    assert threading and socket  # used by the helpers imported above


def _line_size(transcripts):
    return len((transcripts / "transcript.jsonl").read_bytes().splitlines()[-1])


def test_a_reply_of_control_bytes_is_recorded_as_base64_not_six_times_its_size(
    stream_factory, upstream, transcripts
):
    """The security review of 45ed794: recording raw replies whole let escapes inflate a line six
    times past the bytes relayed (each NUL becomes \\u0000), past the free-space floor."""
    import base64

    reply = b"\x00" * (2 << 20)
    upstream["response"] = lambda: _BufferedResponse(reply)
    path = stream_factory(max_tokens=10)
    assert _post(path, {"model": "m", "messages": []}).status_code == 200
    entry = json.loads((transcripts / "transcript.jsonl").read_bytes().splitlines()[-1])
    assert base64.b64decode(entry["response"]["raw_body_base64"]) == reply
    assert _line_size(transcripts) < 1.5 * len(reply)


def test_non_ascii_text_costs_its_own_size_in_the_transcript(stream_factory, upstream, transcripts):
    text = "é" * (1 << 20)
    upstream["response"] = lambda: _BufferedResponse(json.dumps(ENOSPC_BODY).encode())
    path = stream_factory(max_tokens=10)
    assert (
        _post(path, {"model": "m", "messages": [{"role": "user", "content": text}]}).status_code
        == 200
    )
    entry = json.loads((transcripts / "transcript.jsonl").read_bytes().splitlines()[-1])
    assert entry["request"]["messages"][0]["content"] == text
    assert _line_size(transcripts) < 1.2 * len(text.encode("utf-8"))


def test_the_free_space_floor_fits_the_largest_line():
    assert proxy.RECORDER_MIN_FREE_BYTES >= 128 * 1024 * 1024
