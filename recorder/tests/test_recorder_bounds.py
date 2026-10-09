"""Structural bounds on what agents send, ported from the SV workstream (R-B3 / O4).

An agent writes the body its recorder parses, and the recorder is the process holding the real key.
A body can be small in bytes and enormous in structure (two mebibytes of `{}` is seven hundred
thousand objects), or nested deeper than the parser's recursion allows. So a linear byte pre-scan
counts depth, containers and values before anything parses the body, and every parser behind it is
total: a `RecursionError` is a parse error, never a dead handler thread.
"""

# ruff: noqa: F811 -- the fixtures are imported from test_proxy by name, and pytest injects them.

import json

import proxy
import pytest
import recorder_streams
from test_proxy import (  # noqa: F401 -- fixtures, by name
    _BufferedResponse,
    _entries,
    _events,
    _post,
    _used_tokens,
    core_server,
    registry,
    stream_env,
    stream_factory,
    transcripts,
    upstream,
)


def _raw_post(path, body: bytes):
    import httpx

    transport = httpx.HTTPTransport(uds=path)
    with httpx.Client(transport=transport, base_url="http://localhost") as client:
        return client.post(
            "/api/v1/chat/completions",
            content=body,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )


def _nested(levels: int) -> bytes:
    return b"[" * levels + b"]" * levels


def test_the_pre_scan_counts_containers_strings_keys_and_scalars():
    assert recorder_streams.prescan(b'{"a":[1,2,{"b":"x"}]}') == (3, 3, 8)


def test_punctuation_and_escapes_inside_strings_are_not_structure():
    assert recorder_streams.prescan(b'{"a":"[{\\"}]\\\\","b":"}"}') == (1, 1, 5)
    assert recorder_streams.prescan(b'"unterminated [ {') == (0, 0, 1)


def test_two_mebibytes_of_empty_objects_are_refused_before_any_parse(
    stream_factory, upstream, transcripts, registry, monkeypatch
):
    path = stream_factory()
    calls = []
    upstream["response"] = lambda: calls.append(1) or _BufferedResponse(b"{}")
    body = b"[" + b",".join([b"{}"] * 699_050) + b"]"
    real = json.loads

    def refuse_the_body(text, *args, **kwargs):
        if len(text) > 1_000_000:
            raise AssertionError("the body was parsed")
        return real(text, *args, **kwargs)

    monkeypatch.setattr(json, "loads", refuse_the_body)
    response = _raw_post(path, body)
    assert response.status_code == 400
    assert "structure_limit" in response.json()["error"]["message"]
    assert calls == []
    assert _used_tokens(registry) == 0
    assert [e["status"] for e in _events(transcripts) if e["event"] == "close"] == [400]


def test_sixty_five_levels_are_too_deep_and_sixty_four_are_not():
    assert recorder_streams.over_caps(_nested(64), recorder_streams.REQUEST_CAPS) is None
    assert recorder_streams.over_caps(_nested(65), recorder_streams.REQUEST_CAPS) == "depth"


def test_the_value_cap_is_exact():
    def scalars(count: int) -> bytes:
        return b"[" + b",".join([b"1"] * count) + b"]"

    caps = recorder_streams.REQUEST_CAPS
    # The list itself is one value, so 131,071 scalars reach the cap of 131,072 exactly.
    assert recorder_streams.over_caps(scalars(131_071), caps) is None
    assert recorder_streams.over_caps(scalars(131_072), caps) == "values"
    containers = b"[" + b",".join([b"[]"] * 32_768) + b"]"
    assert recorder_streams.over_caps(containers, caps) == "containers"


def test_a_deeply_nested_body_on_a_declared_stream_is_a_400_not_a_dead_handler(
    stream_factory, upstream, transcripts
):
    path = stream_factory()
    response = _raw_post(path, _nested(200_000))
    assert response.status_code == 400
    assert "structure_limit" in response.json()["error"]["message"]
    assert _post(path, {"model": "m", "messages": []}).status_code == 200


def test_a_deeply_nested_body_on_the_core_socket_is_a_400(core_server, upstream, transcripts):
    response = _raw_post(core_server, _nested(200_000))
    assert response.status_code == 400
    assert upstream["seen"] == {}


def test_the_parsers_behind_the_scan_are_total():
    deep = _nested(200_000)
    assert recorder_streams.compose_body(deep, {}) == (None, "request body is not a json object")
    assert recorder_streams.reservation_for(deep, 10) >= 10
    import core_caps

    assert core_caps.core_reservation(deep, 5) >= 5
    record = proxy.StreamRecord()
    record.feed(deep)
    record.finish()
    data = proxy.stream_response_data(record)
    assert "raw_body" in data


def test_a_refused_body_is_recorded_bounded(core_server, upstream, transcripts):
    body = b'{"x":[' + b",".join([b'"padding-padding-padding"'] * 150_000) + b"]}"
    assert len(body) > 3_000_000
    response = _raw_post(core_server, body)
    assert response.status_code == 400
    line = (transcripts / "transcript.jsonl").read_bytes()
    assert len(line) < 1_100_000
    entry = _entries(transcripts)[-1]
    assert entry["request"]["raw_body_truncated"] is True


def test_an_over_structured_response_is_relayed_and_recorded_raw_with_its_usage_not_trusted(
    stream_factory, upstream, transcripts, registry
):
    path = stream_factory()
    over = b'{"usage":{"total_tokens":1},"x":[' + b",".join([b"[]"] * 9_000) + b"]}"
    upstream["response"] = lambda: _BufferedResponse(over)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 200
    assert response.content == over
    entry = _entries(transcripts)[-1]
    assert entry["response"]["structure_limit"] is True
    assert "raw_body" in entry["response"]
    assert _used_tokens(registry) > 1, "the reservation stands; the claimed usage is not trusted"


def test_a_response_over_its_byte_cap_is_withheld_and_recorded_truncated(
    stream_factory, upstream, transcripts, monkeypatch
):
    path = stream_factory()
    monkeypatch.setattr(proxy, "RESPONSE_MAX_BYTES", 1024)
    upstream["response"] = lambda: _BufferedResponse(b'{"pad":"' + b"x" * 4096 + b'"}')
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 502
    assert "response_too_large" in response.json()["error"]["message"]
    entry = _entries(transcripts)[-1]
    assert entry["response"]["raw_body_truncated"] is True


def test_a_body_built_to_make_the_scan_backtrack_is_scanned_in_linear_time():
    """A string that cannot close (an odd backslash run at the end) must not cost a rescan of the
    rest of the body at every quote: the security review of 91065d6 found the regex did."""
    import time

    for body in (b'"\\' * 200_000, b'"' + b'\\"' * 200_000 + b"\\", b'["\\\\\\' * 100_000):
        started = time.monotonic()
        recorder_streams.over_caps(body, recorder_streams.REQUEST_CAPS)
        recorder_streams.prescan(body)
        assert time.monotonic() - started < 2.0, body[:12]


def _reference(value, depth=1):
    """(max depth, containers, values) of a parsed document, counted the way the scan counts."""
    if isinstance(value, dict):
        deepest, containers, values = depth, 1, 1
        for _key, item in value.items():
            values += 1
            d, c, v = _reference(item, depth + 1)
            deepest, containers, values = max(deepest, d), containers + c, values + v
        return deepest, containers, values
    if isinstance(value, list):
        deepest, containers, values = depth, 1, 1
        for item in value:
            d, c, v = _reference(item, depth + 1)
            deepest, containers, values = max(deepest, d), containers + c, values + v
        return deepest, containers, values
    return depth - 1, 0, 1


@pytest.mark.parametrize(
    "document",
    [
        {"a": [1, 2, {"b": "x"}]},
        {"q": 'he said "[{}]"', "e": "\\", "f": '\\\\"', "g": ["\\", '"', 'a\\"b']},
        [[[]], {}, {"": [None, True, False, -1.5e3]}],
        {"text": "line\nbreak\ttab ☃ \\u0022"},
        [{"k" * 5: [{"deep": [[[["v"]]]]}]}],
    ],
)
def test_the_scan_never_counts_less_than_the_parser_sees(document):
    for body in (
        json.dumps(document).encode(),
        json.dumps(document, separators=(",", ":")).encode(),
    ):
        assert recorder_streams.prescan(body) == _reference(document), body


@pytest.mark.parametrize(
    "body",
    [
        b'{"model":"m","messages":[{"role":"user","content":"seen"}],"messages":[]}',
        b'{"model":"m","messages":[],"temperature":NaN}',
        b'{"model":"m","messages":[],"stream":true,"temperature":Infinity}',
        b'{"model":"m","messages":[{"role":"user","content":"a","content":"b"}]}',
    ],
    ids=["duplicate-top", "nan", "infinity-streamed", "duplicate-nested"],
)
def test_a_body_parsers_could_read_two_ways_is_refused_before_contact(
    stream_factory, core_server, upstream, transcripts, registry, body
):
    """The record must be what the upstream read. A duplicate key (which value wins?) or a
    non-finite number (a streamed reply relayed, then a line that cannot be written) would let an
    exchange happen that the transcript does not show: the security review of 28ab56d."""
    calls = []
    upstream["response"] = lambda: calls.append(1) or _BufferedResponse(b"{}")
    for path in (core_server, stream_factory(max_tokens=10)):
        response = _raw_post(path, body)
        assert response.status_code == 400
        assert response.json()["error"]["message"].startswith("ambiguous_json")
    assert calls == []
    assert _used_tokens(registry) == 0


def test_a_body_that_is_not_strict_utf8_json_is_refused_on_the_core_socket_too(
    core_server, upstream
):
    calls = []
    upstream["response"] = lambda: calls.append(1) or _BufferedResponse(b"{}")
    for body in (b"not json", b"[1, 2]", b'{"model": "\xff"}', b'{"a": 1} trailing'):
        response = _raw_post(core_server, body)
        assert response.status_code == 400
        assert response.json()["error"]["message"] == "request body is not a json object"
    assert calls == []
