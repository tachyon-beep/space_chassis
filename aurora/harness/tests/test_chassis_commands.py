import json
import os
import subprocess
import types

import pytest

import chassis
import command_runtime


def response(tool_name):
    calls = (
        []
        if tool_name is None
        else [
            types.SimpleNamespace(
                id="call", function=types.SimpleNamespace(name=tool_name, arguments="{}")
            )
        ]
    )
    return types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(
                    content="finished" if tool_name is None else "",
                    tool_calls=calls,
                    reasoning_content=None,
                    model_extra=None,
                )
            )
        ]
    )


def run_stub_loop(monkeypatch, tmp_path, func):
    answers = iter((response("ordinary"), response(None)))
    monkeypatch.setattr(chassis, "create_with_recovery", lambda *a: next(answers))
    monkeypatch.setattr(chassis, "SESSION_FILE", str(tmp_path / "session_context.json"))
    monkeypatch.setattr(chassis, "record_progress", lambda: None)
    monkeypatch.setattr(
        chassis, "ordinary_command_scope", lambda: command_runtime.ordinary_command_scope(0.04)
    )
    history = [{"role": "user", "content": "same incarnation"}]
    tools = types.SimpleNamespace(schemas=[], tools={"ordinary": func})
    chassis.run_agent_loop(object(), "stub", history, tools)
    return history


def test_sleep_timeout_returns_result_in_same_incarnation_no_retry(monkeypatch, tmp_path):
    pid = os.getpid()
    calls = []

    def ordinary():
        calls.append(os.getpid())
        try:
            subprocess.run("sleep 8h", shell=True, capture_output=True)
        except Exception:
            pytest.fail("timeout reached tool's retry handler")
        pytest.fail("sleep completed")

    history = run_stub_loop(monkeypatch, tmp_path, ordinary)
    assert os.getpid() == pid
    assert calls == [pid]
    assert history[0]["content"] == "same incarnation"
    result = json.loads(history[2]["content"])
    assert result["status"] == "timeout"
    assert history[-1]["content"] == "finished"
    assert json.loads((tmp_path / "session_context.json").read_text()) == history


def test_ordinary_python_global_mutations_remain_in_parent(monkeypatch, tmp_path):
    values = []

    def ordinary():
        values.append("persist")
        return "ok"

    run_stub_loop(monkeypatch, tmp_path, ordinary)
    assert values == ["persist"]


@pytest.mark.parametrize("exit_code", [42, 44, 45])
def test_lifecycle_exits_propagate_and_restore_subprocess_module(monkeypatch, tmp_path, exit_code):
    original = subprocess.run

    def ordinary():
        raise SystemExit(exit_code)

    with pytest.raises(SystemExit) as exc:
        run_stub_loop(monkeypatch, tmp_path, ordinary)
    assert exc.value.code == exit_code
    assert subprocess.run is original


def test_failed_atomic_session_save_preserves_previous_context(monkeypatch, tmp_path):
    path = tmp_path / "session_context.json"
    path.write_text('[{"role":"user","content":"previous"}]')
    monkeypatch.setattr(chassis, "SESSION_FILE", str(path))

    def fail_dump(messages, stream):
        stream.write("partial")
        raise OSError("disk full")

    monkeypatch.setattr(chassis.json, "dump", fail_dump)
    chassis.save_session([{"role": "user", "content": "new"}])
    assert "previous" in path.read_text()
    assert not (tmp_path / "session_context.json.tmp").exists()
