import os
import sys
import time

import pytest

from command_runtime import run_command


def python(code, **kwargs):
    return run_command([sys.executable, "-c", code], **kwargs)


def test_eight_hour_sleep_returns_timeout_without_restarting_caller():
    caller = os.getpid()
    started = time.monotonic()
    result = run_command(["sleep", "8h"], timeout=0.04)
    assert result["status"] == "timeout"
    assert result["termination"]["process_reaped"]
    assert time.monotonic() - started < 2
    assert os.getpid() == caller
    assert python("print('next command')")["stdout"] == "next command\n"


def test_binary_partial_output_and_large_streams_are_bounded():
    result = python(
        "import os,time; os.write(1,b'x'*100000+b'\\xff'); "
        "os.write(2,b'error\\xfe'); time.sleep(30)",
        timeout=0.12,
        output_limit=128,
    )
    assert result["status"] == "timeout"
    assert len(result["stdout"]) <= 128
    assert "\ufffd" in result["stdout"]
    assert "\ufffd" in result["stderr"]
    assert result["output_truncated"]["stdout"]


def test_parent_exit_with_child_holding_pipe_still_times_out():
    result = python(
        "import subprocess,sys; subprocess.Popen([sys.executable,'-c',"
        "'import time; time.sleep(30)']); print('parent finished')",
        timeout=0.1,
    )
    assert result["status"] == "timeout"
    assert "parent finished" in result["stdout"]
    assert result["termination"]["scope"] == "command_process_group"


def test_shell_pipeline_children_stop_at_deadline():
    started = time.monotonic()
    result = run_command("sleep 8h | cat", shell=True, timeout=0.05)
    assert result["status"] == "timeout"
    assert result["termination"]["process_reaped"]
    assert time.monotonic() - started < 2


def test_ignoring_term_is_killed_without_unbounded_drain():
    result = python(
        "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "print('ready',flush=True); time.sleep(30)",
        timeout=0.15,
    )
    assert result["status"] == "timeout"
    assert result["returncode"] == -9


def test_input_binary_and_nonzero_completed_result():
    result = python(
        "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()); sys.exit(7)",
        input=b"\xffbinary",
    )
    assert result["stdout"] == "\ufffdbinary"
    assert result["returncode"] == 7
    assert result["status"] == "completed"
    assert result["termination"] is None


def test_large_input_to_hung_child_obeys_wall_cap():
    result = python("import time; time.sleep(30)", input=b"x" * 1000000, timeout=0.04)
    assert result["status"] == "timeout"


@pytest.mark.parametrize("timeout,limit", [(0, 1), (1, -1)])
def test_invalid_bounds_rejected(timeout, limit):
    with pytest.raises(ValueError):
        python("pass", timeout=timeout, output_limit=limit)


def test_raw_binary_capture_and_encoding_adapter():
    import subprocess
    from command_runtime import ordinary_command_scope

    with ordinary_command_scope(timeout=1):
        raw = subprocess.run(
            [sys.executable, "-c", "import os;os.write(1,b'\\xff')"], capture_output=True
        )
        text = subprocess.run(
            [sys.executable, "-c", "import os;os.write(1,b'\\xff\\r\\n')"],
            capture_output=True,
            encoding="latin-1",
        )
        assert raw.stdout == b"\xff"
        assert text.stdout == "ÿ\n"
        with pytest.raises(subprocess.CalledProcessError) as exc:
            subprocess.run(
                [sys.executable, "-c", "import os,sys;os.write(2,b'\\xff');sys.exit(3)"],
                capture_output=True,
                check=True,
            )
        assert exc.value.returncode == 3
        assert exc.value.stderr == b"\xff"


def test_inline_timeout_escapes_tool_exception_handler_and_restores_patch():
    import subprocess
    from command_runtime import CommandTimeout, ordinary_command_scope

    original = subprocess.run
    retried = False
    with pytest.raises(CommandTimeout) as exc:
        with ordinary_command_scope(timeout=0.03):
            try:
                subprocess.run("sleep 8h", shell=True, capture_output=True, timeout=100000)
            except Exception:
                retried = True
    assert exc.value.result["status"] == "timeout"
    assert not retried
    assert subprocess.run is original


def test_patch_restored_on_lifecycle_exit():
    import subprocess
    from command_runtime import ordinary_command_scope

    original = subprocess.run
    with pytest.raises(SystemExit) as exc:
        with ordinary_command_scope(timeout=0.01):
            raise SystemExit(45)
    assert exc.value.code == 45
    assert subprocess.run is original


def test_background_run_not_capped_by_inline_dispatch_scope():
    import subprocess
    import threading
    from command_runtime import ordinary_command_scope

    result = []
    with ordinary_command_scope(timeout=0.01):
        thread = threading.Thread(
            target=lambda: result.append(
                subprocess.run(
                    [sys.executable, "-c", "import time;time.sleep(0.06);print('collected')"],
                    capture_output=True,
                )
            )
        )
        thread.start()
        thread.join(timeout=1)
    assert not thread.is_alive()
    assert result[0].stdout == b"collected\n"


def test_background_child_of_successful_command_can_continue(tmp_path):
    sentinel = tmp_path / "collected"
    code = (
        "import subprocess,sys;subprocess.Popen([sys.executable,'-c',"
        f"{('import pathlib,time;time.sleep(0.05);pathlib.Path(' + repr(str(sentinel)) + ').write_text("done")')!r}"
        "],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)"
    )
    result = python(code, timeout=1)
    assert result["status"] == "completed"
    deadline = time.monotonic() + 1
    while not sentinel.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert sentinel.read_text() == "done"


def test_invalid_input_fails_before_process_start(monkeypatch):
    import command_runtime

    monkeypatch.setattr(
        command_runtime.subprocess, "Popen", lambda *a, **k: pytest.fail("launched")
    )
    with pytest.raises(TypeError):
        run_command(["sleep", "30"], input=object())
    for timeout in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            run_command(["sleep", "30"], timeout=timeout)


def test_unsupported_preexec_or_process_group_options_fail_before_launch(monkeypatch):
    import command_runtime

    monkeypatch.setattr(
        command_runtime.subprocess, "Popen", lambda *a, **k: pytest.fail("launched")
    )
    for key in ("preexec_fn", "start_new_session", "process_group"):
        with pytest.raises(TypeError, match="unsupported"):
            command_runtime.bounded_subprocess_run(["sleep", "30"], **{key: None})


def test_retained_run_alias_reverts_to_original_after_scope(monkeypatch):
    import subprocess
    from command_runtime import ordinary_command_scope

    original = subprocess.run
    with ordinary_command_scope(timeout=0.001):
        alias = subprocess.run
    result = alias(
        [sys.executable, "-c", "import time;time.sleep(0.03);print('done')"], capture_output=True
    )
    assert result.stdout == b"done\n"
    assert subprocess.run is original


def test_successful_large_binary_and_utf8_captures_remain_complete():
    import subprocess
    from command_runtime import ordinary_command_scope

    with ordinary_command_scope(timeout=1):
        binary = subprocess.run(
            [sys.executable, "-c", "import os;os.write(1,b'\\xff'*100000)"],
            capture_output=True,
        )
        text = subprocess.run(
            [sys.executable, "-c", "print('€'*30000,end='')"],
            capture_output=True,
            text=True,
        )
    assert binary.stdout == b"\xff" * 100000
    assert text.stdout == "€" * 30000


def test_inherited_output_does_not_write_python_sink(monkeypatch, capfd):
    import subprocess
    from command_runtime import CommandTimeout, ordinary_command_scope

    class BlockingSink:
        def write(self, value):
            pytest.fail("Python inherited sink write would block the command deadline")

        def flush(self):
            pytest.fail("Python inherited sink flush would block the command deadline")

    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", BlockingSink())
        with ordinary_command_scope(timeout=0.05):
            with pytest.raises(CommandTimeout) as exc:
                subprocess.run(
                    [sys.executable, "-c", "import os,time;os.write(1,b'raw\\xff');time.sleep(30)"]
                )
    assert exc.value.result["stdout"] is None
    assert not exc.value.result["output_captured"]["stdout"]
    assert "raw" in capfd.readouterr().out
    with ordinary_command_scope(timeout=1):
        result = subprocess.run([sys.executable, "-c", "print('success')"])
    assert result.stdout is None and result.stderr is None
    assert "success" in capfd.readouterr().out


def test_backpressured_output_fd_cannot_block_parent_deadline():
    import subprocess
    from command_runtime import CommandTimeout, ordinary_command_scope

    read_fd, write_fd = os.pipe()
    try:
        os.set_blocking(write_fd, False)
        while True:
            try:
                os.write(write_fd, b"x" * 4096)
            except BlockingIOError:
                break
        os.set_blocking(write_fd, True)
        started = time.monotonic()
        with ordinary_command_scope(timeout=0.03):
            with pytest.raises(CommandTimeout) as exc:
                subprocess.run(
                    [sys.executable, "-c", "import os;os.write(1,b'blocked')"], stdout=write_fd
                )
        assert time.monotonic() - started < 2
        assert exc.value.result["termination"]["process_reaped"]
        assert exc.value.result["stdout"] is None
        assert not exc.value.result["output_captured"]["stdout"]
    finally:
        os.close(read_fd)
        os.close(write_fd)
