"""The transcript made durable before a buffered reply is relayed (SV R-B4), and John's rule for when
it cannot be: the reply is withheld (502 record_failed) and still charged.

append_record is the one writer of the JSON transcript: it repairs a torn tail, writes the whole
line through short writes and EINTR, syncs the data, and fences the directory on a path's first
append. Faults are injected at the recorder's own indirections (_os_write, _fdatasync, _fsync,
_statvfs), never at the process-wide os module.
"""

# ruff: noqa: F811 -- the fixtures are imported from test_proxy by name, and pytest injects them.

import errno
import json
import os
import threading

import proxy
import pytest
from test_proxy import (  # noqa: F401 -- fixtures, by name
    ENOSPC_BODY,
    _BufferedResponse,
    _entries,
    _events,
    _post,
    _used_tokens,
    _wait_until,
    registry,
    stream_env,
    stream_factory,
    transcripts,
    upstream,
)


@pytest.fixture(autouse=True)
def _fresh_fences(monkeypatch):
    monkeypatch.setattr(proxy, "_fenced", set())
    monkeypatch.setattr(proxy, "_degraded_reported", False)


class _Syncs:
    def __init__(self, monkeypatch, fail=()):
        self.paths, self.fail = [], set(fail)
        real = os.fsync

        def fsync(fd):
            target = os.readlink(f"/proc/self/fd/{fd}")
            self.paths.append(target)
            if target in self.fail:
                raise OSError(errno.EIO, "sync failed")
            return real(fd)

        monkeypatch.setattr(proxy, "_fsync", fsync)


def test_the_first_append_fsyncs_the_file_and_its_directory(tmp_path, monkeypatch):
    syncs = _Syncs(monkeypatch)
    data_syncs = []
    monkeypatch.setattr(proxy, "_fdatasync", lambda fd: data_syncs.append(fd))
    path = tmp_path / "t" / "transcript.jsonl"
    assert proxy.append_record(str(path), b'{"a": 1}') == "durable"
    assert data_syncs, "the data was synced"
    assert str(tmp_path / "t") in syncs.paths
    assert str(tmp_path) in syncs.paths, "a directory makedirs created is fenced in its parent"
    syncs.paths.clear()
    assert proxy.append_record(str(path), b'{"a": 2}') == "durable"
    assert syncs.paths == [], "a fenced path is not fenced again"
    assert path.read_bytes() == b'{"a": 1}\n{"a": 2}\n'


def test_a_failed_directory_sync_is_never_reported_durable_and_is_retried(tmp_path, monkeypatch):
    syncs = _Syncs(monkeypatch, fail={str(tmp_path)})
    path = tmp_path / "transcript.jsonl"
    assert proxy.append_record(str(path), b"{}") == "appended"
    syncs.fail.clear()
    syncs.paths.clear()
    assert proxy.append_record(str(path), b"{}") == "durable"
    assert str(tmp_path) in syncs.paths


def test_a_short_write_after_a_prefix_is_partial_and_the_next_line_starts_on_a_boundary(
    tmp_path, monkeypatch
):
    path = tmp_path / "transcript.jsonl"
    real = os.write
    calls = []

    def short_then_full(fd, data):
        calls.append(len(data))
        if len(calls) == 1:
            return real(fd, data[:5])
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(proxy, "_os_write", short_then_full)
    assert proxy.append_record(str(path), b'{"first": "line"}') == "partial"
    monkeypatch.setattr(proxy, "_os_write", real)
    assert proxy.append_record(str(path), b'{"second": 2}') in proxy.READABLE
    lines = path.read_bytes().split(b"\n")
    assert lines[0] == b'{"fir'
    assert json.loads(lines[1]) == {"second": 2}


def test_eintr_is_retried_and_a_short_write_is_completed(tmp_path, monkeypatch):
    path = tmp_path / "transcript.jsonl"
    real = os.write
    calls = []

    def awkward(fd, data):
        calls.append(1)
        if len(calls) == 1:
            raise InterruptedError
        return real(fd, data[:3])

    monkeypatch.setattr(proxy, "_os_write", awkward)
    assert proxy.append_record(str(path), b'{"whole": true}') in proxy.READABLE
    assert path.read_bytes() == b'{"whole": true}\n'


def test_a_torn_tail_left_by_a_dead_process_is_repaired(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_bytes(b'{"complete": 1}\n{"torn')
    assert proxy.append_record(str(path), b'{"next": 2}') in proxy.READABLE
    assert path.read_bytes().split(b"\n")[-2] == b'{"next": 2}'


def test_concurrent_appends_never_interleave(tmp_path):
    path = tmp_path / "transcript.jsonl"
    payloads = [json.dumps({"n": n, "pad": "x" * 70_000}).encode() for n in range(40)]
    threads = [threading.Thread(target=proxy.append_record, args=(str(path), p)) for p in payloads]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    lines = path.read_bytes().splitlines()
    assert sorted(json.loads(line)["n"] for line in lines) == list(range(40))


def test_a_failed_data_sync_relays_and_is_reported_once(
    stream_factory, upstream, transcripts, monkeypatch, capsys
):
    def broken(fd):
        raise OSError(errno.EIO, "sync failed")

    monkeypatch.setattr(proxy, "_fdatasync", broken)
    upstream["response"] = lambda: _BufferedResponse(json.dumps(ENOSPC_BODY).encode())
    path = stream_factory(max_tokens=10)
    for _ in range(2):
        response = _post(path, {"model": "m", "messages": []})
        assert response.status_code == 200
    assert capsys.readouterr().err.count("transcript durability degraded") == 1


def test_a_failed_transcript_withholds_the_answer_and_the_usage_is_charged(
    stream_factory, upstream, transcripts, registry, monkeypatch
):
    def full(fd, data):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(proxy, "_os_write", full)
    upstream["response"] = lambda: _BufferedResponse(json.dumps(ENOSPC_BODY).encode())
    path = stream_factory(max_tokens=400)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 502
    assert response.json()["error"]["message"].startswith("record_failed")
    assert "choices" not in response.text, "the answer is withheld"
    close = [e for e in _events(transcripts) if e["event"] == "close"][-1]
    assert close["record"] == "failed"
    assert _used_tokens(registry) == 7, "the usage the upstream reported is charged"


def test_a_partial_transcript_is_withheld_and_the_next_turn_is_recorded_cleanly(
    stream_factory, upstream, transcripts, monkeypatch
):
    real = os.write
    state = {"short": True}

    def once_short(fd, data):
        if state["short"]:
            state["short"] = False
            real(fd, data[:4])
            raise OSError(errno.ENOSPC, "No space left on device")
        return real(fd, data)

    monkeypatch.setattr(proxy, "_os_write", once_short)
    clock = {"now": 0.0}
    monkeypatch.setattr(proxy, "RECORD_CLOCK", lambda: clock["now"])
    upstream["response"] = lambda: _BufferedResponse(json.dumps(ENOSPC_BODY).encode())
    path = stream_factory(max_tokens=10)
    assert _post(path, {"model": "m", "messages": []}).status_code == 502
    # The failed record holds new requests back until a probe write succeeds after the cool-off.
    clock["now"] += proxy.RECORD_RETRY_SECONDS + 1
    assert _post(path, {"model": "m", "messages": []}).status_code == 200
    lines = (transcripts / "transcript.jsonl").read_bytes().split(b"\n")
    assert json.loads(lines[1])["response"] == ENOSPC_BODY


def test_a_streamed_reply_is_recorded_after_relay_and_says_so(
    stream_factory, upstream, transcripts
):
    from test_proxy import _event, _StreamingResponse

    upstream["response"] = lambda: _StreamingResponse(
        [
            _event({"choices": [{"delta": {"content": "hi"}}]}).encode(),
            _event({"choices": [], "usage": {"total_tokens": 3}}).encode(),
            b"data: [DONE]\n\n",
        ]
    )
    path = stream_factory(max_tokens=10)
    response = _post(path, {"model": "m", "messages": [], "stream": True})
    assert response.status_code == 200
    # Recorded after the relay, so after the client already has its reply.
    assert _wait_until(lambda: _entries(transcripts))
    assert _entries(transcripts)[-1]["recorded_after_relay"] is True


def test_rotation_makes_the_archive_durable_before_truncating(tmp_path, monkeypatch):
    path = tmp_path / "transcript.jsonl"
    path.write_text('{"a": 1}\n' * 100)
    order = []
    real_fsync = os.fsync

    def fsync(fd):
        order.append(("fsync", os.readlink(f"/proc/self/fd/{fd}")))
        return real_fsync(fd)

    real_open = open

    def watched_open(file, mode="r", *args, **kwargs):
        if str(file) == str(path) and mode.startswith("w"):
            order.append(("truncate", str(file)))
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(proxy, "_fsync", fsync)
    monkeypatch.setattr(proxy, "open", watched_open, raising=False)
    archive = proxy.rotate_if_needed(str(path), max_bytes=10)
    assert archive is not None
    truncate = order.index(("truncate", str(path)))
    # The archive is synced under its temporary name, then renamed into place.
    assert ("fsync", archive + ".tmp") in order[:truncate]
    assert ("fsync", str(tmp_path)) in order[:truncate]


def test_a_reply_carrying_a_non_finite_number_is_relayed_and_recorded_raw(
    stream_factory, upstream, transcripts, registry
):
    """Plan 4b final review: a NaN in the upstream's reply used to fail the record every time,
    withholding a reply that was paid for. It is now recorded as the bytes it was, its usage not
    trusted, and the line stays strict JSON."""
    reply = b'{"choices": [{"message": {"content": "hi"}}], "usage": {"total_tokens": 1}, "x": NaN}'
    upstream["response"] = lambda: _BufferedResponse(reply)
    path = stream_factory(max_tokens=400)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 200
    assert response.content == reply
    line = (transcripts / "transcript.jsonl").read_bytes().splitlines()[-1]

    def refuse(name):
        raise ValueError(name)

    entry = json.loads(line, parse_constant=refuse)
    assert entry["response"]["raw_body"] == reply.decode()
    assert _used_tokens(registry) >= 400, "the claimed usage is not trusted"


def test_a_relayed_raw_reply_is_recorded_whole(stream_factory, upstream, transcripts):
    over = b'{"x":[' + b",".join([b"[]"] * 9_000) + b'],"pad":"' + b"p" * 1_500_000 + b'"}'
    upstream["response"] = lambda: _BufferedResponse(over)
    path = stream_factory(max_tokens=10)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 200
    entry = _entries(transcripts)[-1]
    assert entry["response"]["raw_body"] == over.decode()
    assert "raw_body_truncated" not in entry["response"]


def test_a_failed_record_refuses_new_requests_until_the_volume_takes_a_write_again(
    stream_factory, upstream, transcripts, registry, monkeypatch
):
    """A failure that free space cannot see (EROFS, EIO, EACCES) would otherwise repeat on every
    paid-for request: after one, requests are refused uncharged until a probe write succeeds."""
    clock = {"now": 1000.0}
    monkeypatch.setattr(proxy, "RECORD_CLOCK", lambda: clock["now"])
    monkeypatch.setattr(proxy, "_record_failed_at", None)
    real = os.write

    def read_only(fd, data):
        raise OSError(errno.EROFS, "Read-only file system")

    monkeypatch.setattr(proxy, "_os_write", read_only)
    upstream["response"] = lambda: _BufferedResponse(json.dumps(ENOSPC_BODY).encode())
    path = stream_factory(max_tokens=10)
    assert _post(path, {"model": "m", "messages": []}).status_code == 502
    calls = []
    upstream["response"] = lambda: (
        calls.append(1) or _BufferedResponse(json.dumps(ENOSPC_BODY).encode())
    )
    used = _used_tokens(registry)
    refused = _post(path, {"model": "m", "messages": []})
    assert refused.status_code == 503
    assert "record_capacity" in refused.json()["error"]["message"]
    assert calls == [] and _used_tokens(registry) == used
    clock["now"] += proxy.RECORD_RETRY_SECONDS + 1
    assert _post(path, {"model": "m", "messages": []}).status_code == 503, "the probe still fails"
    monkeypatch.setattr(proxy, "_os_write", real)
    clock["now"] += proxy.RECORD_RETRY_SECONDS + 1
    assert _post(path, {"model": "m", "messages": []}).status_code == 200
    assert not [p for p in transcripts.iterdir() if p.name.startswith(".record-probe")]


def test_too_little_free_space_refuses_before_admission_and_charges_nothing(
    stream_factory, upstream, transcripts, registry, monkeypatch
):
    class Full:
        f_bavail = 1
        f_frsize = 4096

    monkeypatch.setattr(proxy, "_statvfs", lambda path: Full())
    calls = []
    upstream["response"] = lambda: calls.append(1) or _BufferedResponse(b"{}")
    path = stream_factory(max_tokens=400)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 503
    assert "record_capacity" in response.json()["error"]["message"]
    assert calls == []
    assert _used_tokens(registry) == 0


def test_a_failed_directory_sync_is_appended_not_durable(tmp_path, monkeypatch):
    _Syncs(monkeypatch, fail={str(tmp_path)})
    assert proxy.append_record(str(tmp_path / "t.jsonl"), b"{}") == "appended"


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "m", "messages": [1]},
        {"model": "m", "messages": [{"role": 7, "content": "x"}]},
        {"model": "m", "messages": [{"role": "assistant", "tool_calls": ["a"]}]},
        {"model": "m", "messages": [{"role": "assistant", "tool_calls": [{"function": None}]}]},
    ],
    ids=["number-message", "number-role", "string-call", "null-function"],
)
@pytest.mark.parametrize("streamed", [False, True], ids=["buffered", "streamed"])
def test_an_odd_message_shape_is_still_recorded_and_closed(
    stream_factory, upstream, transcripts, payload, streamed
):
    """Plan 4b final review: the transcript's display code ran before the record was written and
    raised on shapes like these, so a streamed reply went out unrecorded and a buffered one was
    charged with no record, no close and no reply."""
    from test_proxy import _StreamingResponse

    if streamed:
        upstream["response"] = lambda: _StreamingResponse([b"data: [DONE]\n\n"])
    else:
        upstream["response"] = lambda: _BufferedResponse(json.dumps(ENOSPC_BODY).encode())
    path = stream_factory(max_tokens=10)
    response = _post(path, dict(payload, stream=streamed))
    assert response.status_code == 200
    assert _wait_until(lambda: _entries(transcripts))
    assert _wait_until(lambda: [e for e in _events(transcripts) if e["event"] == "close"])


@pytest.mark.parametrize(
    "reply",
    [b"[1, 2]", b'{"choices": [{"message": null}]}', b'{"choices": ["x"]}'],
    ids=["list", "null-message", "string-choice"],
)
def test_an_odd_reply_shape_is_still_recorded_and_relayed(
    stream_factory, upstream, transcripts, reply
):
    upstream["response"] = lambda: _BufferedResponse(reply)
    path = stream_factory(max_tokens=10)
    response = _post(path, {"model": "m", "messages": []})
    assert response.status_code == 200
    assert response.content == reply
    assert _entries(transcripts)
