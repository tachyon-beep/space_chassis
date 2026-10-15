import json

import pytest

import proxy
import recorder_streams
from hostile_inputs import FIFO_CASE, hostile_cases, read_with_hang_guard

CAP = recorder_streams.CONSOLE_MAX_BYTES


def _valid(value):
    return {"enable_streams": True, "streams": {"aux": {"budget": 1}}, "x": value}


def _cases(tmp_path):
    return list(hostile_cases(tmp_path, CAP, _valid))


def test_every_hostile_case_returns_an_error_string(tmp_path):
    for name, path in _cases(tmp_path):
        if name == FIFO_CASE:
            result = read_with_hang_guard(lambda p=path: recorder_streams.load_console(p), path)
        elif name == "symlink_dangling":
            assert recorder_streams.load_console(path) == ({}, False, None)
            continue
        elif name == "huge_integer":
            declarations, enabled, error = recorder_streams.load_console(path)
            assert error is None and enabled is True
            continue
        elif name == "empty":
            result = recorder_streams.load_console(path)
        else:
            result = recorder_streams.load_console(path)
        declarations, enabled, error = result
        assert declarations is None, name
        assert enabled is False, name
        assert isinstance(error, str) and error, name


def test_specific_reasons(tmp_path):
    reasons = {
        name: recorder_streams.load_console(path)[2]
        for name, path in _cases(tmp_path)
        if name != FIFO_CASE
    }
    assert reasons["over_cap"] == "console is too large"
    assert reasons["deeply_nested"] == "console is not valid json"
    assert reasons["infinity"] == "console is not valid json"
    assert reasons["nan"] == "console is not valid json"
    assert reasons["invalid_utf8"] == "console is not valid json"
    assert reasons["symlink_to_file"] == "console is not readable"
    assert reasons["symlink_to_device"] == "console is not readable"
    assert reasons["directory"] == "console is not readable"


def test_fifo_does_not_block(tmp_path):
    fifo = dict(_cases(tmp_path))[FIFO_CASE]
    result = read_with_hang_guard(lambda: recorder_streams.load_console(fifo), fifo)
    assert result == (None, False, "console is not readable")


def test_read_agent_file_reasons(tmp_path):
    cases = dict(_cases(tmp_path))
    read = recorder_streams._read_agent_file
    assert read(cases["over_cap"], CAP) == (None, "over cap")
    assert read(cases["directory"], CAP) == (None, "not a regular file")
    assert read(cases["symlink_to_file"], CAP) == (None, "not a regular file")
    assert read(cases["symlink_dangling"], CAP) == (None, "absent")
    assert read(str(tmp_path / "nothing"), CAP) == (None, "absent")
    assert read(cases["empty"], CAP) == (b"", None)


def test_hostile_console_keeps_existing_streams(tmp_path, monkeypatch):
    monkeypatch.setattr(proxy, "TRANSCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(proxy, "EVENTS_FILE", str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(proxy, "_active_bindings", set())
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    registry = recorder_streams.StreamRegistry()
    servers = {}
    console = tmp_path / "console.json"
    state = tmp_path / "streams.json"
    console.write_text(json.dumps({"enable_streams": True, "streams": {"aux": {}}}))
    proxy.poll_once(registry, servers, str(tmp_path), str(console), str(state))
    try:
        assert "aux" in servers
        console.write_bytes(b"[" * 60000)
        proxy.poll_once(registry, servers, str(tmp_path), str(console), str(state))
        assert "aux" in servers
        assert json.loads(state.read_text())["console_error"] == "console is not valid json"
    finally:
        for server in servers.values():
            server.shutdown()
            server.server_close()


def test_huge_integer_in_a_declaration_is_judged_by_field(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    big = 10**399
    for field in ("budget", "token_budget", "max_tokens"):
        settings, reason = recorder_streams.validate_declaration("aux", {field: big})
        assert reason is None and settings[field] == big, field
    assert recorder_streams.validate_declaration("aux", {"temperature": big}) == (
        None,
        "temperature must be a number from 0 to 2",
    )
    assert recorder_streams.validate_declaration("aux", {"top_p": big}) == (
        None,
        "top_p must be a number from 0 to 1",
    )
    accepted, rejected = recorder_streams.evaluate_console(
        {"a": {"budget": big, "max_tokens": big}, "b": {"temperature": big}}, True
    )
    assert "a" in accepted and "b" in rejected
    registry = recorder_streams.StreamRegistry()
    registry.apply(accepted, rejected)
    registry.state(streams_enabled=True, console_error=None)


def test_poll_fault_does_not_end_the_loop(tmp_path, monkeypatch, capsys):
    def boom(path=None):
        raise RecursionError("deep")

    monkeypatch.setattr(recorder_streams, "load_console", boom)
    registry = recorder_streams.StreamRegistry()
    servers = {"kept": object()}
    proxy.poll_safely(registry, servers, str(tmp_path), "c.json", str(tmp_path / "s.json"))
    assert servers == {"kept": servers["kept"]}
    err = capsys.readouterr().err
    assert err.count("poll fault") == 1


def test_main_loop_survives_a_poll_fault(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_SOCKET_PATH", str(tmp_path / "core.sock"))
    monkeypatch.setattr(proxy, "TRANSCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(proxy, "EVENTS_FILE", str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(proxy, "_active_bindings", set())
    monkeypatch.setattr(recorder_streams, "load_console", lambda path=None: 1 / 0)

    class FakeServer:
        def __init__(self, *args, **kwargs):
            pass

        def server_close(self):
            pass

        def serve_forever(self):
            pass

    class FakeThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(proxy, "UnixHTTPServer", FakeServer)
    monkeypatch.setattr(proxy.threading, "Thread", FakeThread)

    class Stop(Exception):
        pass

    sleeps = []

    def stop_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise Stop

    monkeypatch.setattr(proxy.time, "sleep", stop_sleep)
    with pytest.raises(Stop):
        proxy.main()
    assert len(sleeps) == 2
    assert capsys.readouterr().err.count("poll fault") == 2


def test_a_bind_that_raises_once_is_retried(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(proxy, "TRANSCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(proxy, "EVENTS_FILE", str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(proxy, "_active_bindings", set())
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    real = proxy.UnixHTTPServer
    calls = []

    def flaky(path, handler):
        calls.append(path)
        if len(calls) == 1:
            raise RuntimeError("bind")
        return real(path, handler)

    monkeypatch.setattr(proxy, "UnixHTTPServer", flaky)
    registry = recorder_streams.StreamRegistry()
    servers = {}
    console = tmp_path / "console.json"
    state = tmp_path / "streams.json"
    console.write_text(json.dumps({"enable_streams": True, "streams": {"aux": {}}}))
    try:
        proxy.poll_once(registry, servers, str(tmp_path), str(console), str(state))
        assert "aux" not in servers
        assert "bind fault" in capsys.readouterr().err
        proxy.poll_once(registry, servers, str(tmp_path), str(console), str(state))
        assert "aux" in servers
        assert json.loads(state.read_text())["streams"]["aux"]["status"] == "active"
    finally:
        for server in servers.values():
            server.shutdown()
            server.server_close()


def test_a_thread_start_that_raises_once_is_retried(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(proxy, "TRANSCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(proxy, "EVENTS_FILE", str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(proxy, "_active_bindings", set())
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    real_thread = proxy.threading.Thread
    starts = []

    class FlakyThread(real_thread):
        def start(self):
            starts.append(self)
            if len(starts) == 1:
                raise RuntimeError("can't start new thread")
            super().start()

    monkeypatch.setattr(proxy.threading, "Thread", FlakyThread)
    registry = recorder_streams.StreamRegistry()
    servers = {}
    console = tmp_path / "console.json"
    state = tmp_path / "streams.json"
    console.write_text(json.dumps({"enable_streams": True, "streams": {"aux": {}}}))
    try:
        proxy.poll_once(registry, servers, str(tmp_path), str(console), str(state))
        assert servers == {}
        assert not (tmp_path / "aux.sock").exists()
        proxy.poll_once(registry, servers, str(tmp_path), str(console), str(state))
        assert "aux" in servers
        assert starts[1].is_alive()
    finally:
        for server in servers.values():
            server.shutdown()
            server.server_close()
