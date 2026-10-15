"""Bounded synchronous subprocess execution, without changing Python tool state."""

import contextlib
import locale
import math
import os
import selectors
import signal
import subprocess
import tempfile
import threading
import time

COMMAND_TIMEOUT_SECONDS = 120
OUTPUT_LIMIT_BYTES = 65536
TERMINATION_GRACE_SECONDS = 0.2


class CommandTimeout(BaseException):
    """Dispatch-level timeout; ordinary tool exception handlers cannot retry it."""

    def __init__(self, result):
        self.result = result
        super().__init__("ordinary command deadline reached")


def run_command(
    command,
    *,
    cwd=None,
    env=None,
    shell=False,
    input=None,
    timeout=COMMAND_TIMEOUT_SECONDS,
    output_limit=OUTPUT_LIMIT_BYTES,
    decode_output=True,
    _popen_options=None,
    _capture_complete=False,
):
    """Run one command with a wall deadline capped at 120 seconds and bounded output.

    Timeout terminates this command's process group. Detached sessions are outside that
    scope; the result reports group liveness and reaping rather than promising all work
    stopped. Successful commands may leave legitimate asynchronous children running.
    """
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    if not isinstance(output_limit, int) or output_limit < 0:
        raise ValueError("output_limit must be a nonnegative integer")
    timeout = min(timeout, COMMAND_TIMEOUT_SECONDS)
    if input is not None and not isinstance(input, (str, bytes)):
        raise TypeError("input must be text or bytes")
    payload = input.encode() if isinstance(input, str) else input
    if payload is not None:
        payload = memoryview(payload)
    options = dict(_popen_options or {})
    unsupported = options.keys() - {
        "stdin",
        "stdout",
        "stderr",
        "executable",
        "bufsize",
        "close_fds",
        "pass_fds",
        "restore_signals",
        "umask",
        "user",
        "group",
        "extra_groups",
        "pipesize",
    }
    if unsupported:
        raise TypeError(f"unsupported bounded subprocess options: {sorted(unsupported)}")
    options.setdefault("stdin", subprocess.PIPE if payload is not None else subprocess.DEVNULL)
    options.setdefault("stdout", subprocess.PIPE)
    options.setdefault("stderr", subprocess.PIPE)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    truncated = {"stdout": False, "stderr": False}
    captured = {}
    spools = {}
    complete = {}
    proc = None
    selector = None
    started = time.monotonic()
    deadline = started + timeout
    timed_out = False
    killed = False
    termination_deadline = None

    def signal_group(sig):
        if proc is not None:
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                pass

    try:
        proc = subprocess.Popen(
            command, cwd=cwd, env=env, shell=shell, start_new_session=True, **options
        )
        selector = selectors.DefaultSelector()
        for name in buffers:
            stream = getattr(proc, name)
            captured[name] = stream is not None
            if stream is not None:
                if _capture_complete:
                    spools[name] = tempfile.TemporaryFile()
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
        if proc.stdin is not None:
            if payload:
                os.set_blocking(proc.stdin.fileno(), False)
                selector.register(proc.stdin, selectors.EVENT_WRITE, "stdin")
            else:
                proc.stdin.close()

        def close_stream(stream):
            selector.unregister(stream)
            stream.close()

        while selector.get_map() or proc.poll() is None:
            now = time.monotonic()
            if not timed_out and now >= deadline:
                timed_out = True
                signal_group(signal.SIGTERM)
                termination_deadline = now + TERMINATION_GRACE_SECONDS
            if timed_out and now >= termination_deadline:
                if not killed:
                    signal_group(signal.SIGKILL)
                    killed = True
                    termination_deadline = now + TERMINATION_GRACE_SECONDS
                else:
                    break
            end = termination_deadline if timed_out else deadline
            for key, _ in selector.select(max(0, min(0.05, end - now))):
                stream, name = key.fileobj, key.data
                if name == "stdin":
                    try:
                        written = os.write(stream.fileno(), payload[:16384]) if payload else 0
                        payload = payload[written:]
                    except BrokenPipeError:
                        payload = memoryview(b"")
                    if not payload:
                        close_stream(stream)
                    continue
                try:
                    chunk = os.read(stream.fileno(), 16384)
                except BlockingIOError:
                    continue
                if not chunk:
                    close_stream(stream)
                    continue
                if name in spools:
                    spools[name].write(chunk)
                buffers[name].extend(chunk)
                if len(buffers[name]) > output_limit:
                    del buffers[name][: len(buffers[name]) - output_limit]
                    truncated[name] = True
        if timed_out:
            signal_group(signal.SIGKILL)
        try:
            proc.wait(timeout=TERMINATION_GRACE_SECONDS)
            reaped = True
        except subprocess.TimeoutExpired:
            reaped = False
        if not timed_out:
            for name, spool in spools.items():
                spool.seek(0)
                complete[name] = spool.read()
    except BaseException:
        signal_group(signal.SIGKILL)
        if proc is not None:
            try:
                proc.wait(timeout=TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                pass
        raise
    finally:
        for spool in spools.values():
            spool.close()
        if selector is not None:
            selector.close()
        if proc is not None:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
    group_alive = None
    if timed_out:
        try:
            os.killpg(proc.pid, 0)
            group_alive = True
        except ProcessLookupError:
            group_alive = False
        except PermissionError:
            group_alive = None

    def output(name):
        raw = complete.get(name, bytes(buffers[name]))
        if decode_output:
            return raw.decode("utf-8", errors="replace")
        return raw if captured[name] else None

    return {
        "status": "timeout" if timed_out else "completed",
        "timeout_seconds": timeout if timed_out else None,
        "returncode": proc.returncode,
        "stdout": output("stdout"),
        "stderr": output("stderr"),
        "output_truncated": truncated,
        "output_captured": captured,
        "termination": {
            "scope": "command_process_group",
            "process_reaped": reaped,
            "group_alive": group_alive,
        }
        if timed_out
        else None,
    }


def bounded_subprocess_run(
    *popenargs,
    input=None,
    capture_output=False,
    timeout=None,
    check=False,
    command_limit=COMMAND_TIMEOUT_SECONDS,
    **kwargs,
):
    """CompletedProcess-compatible subset of run, with an unconditional command cap.

    Unsupported Popen options fail before launch. A caller cannot request a separate
    session/process group or a preexec callback; bounded execution owns the group.
    Successful capture is complete, spooled to temporary storage while running. Timeout
    results retain only the last OUTPUT_LIMIT_BYTES of each captured stream.
    """
    if len(popenargs) > 1 or (popenargs and "args" in kwargs):
        raise TypeError("expected one command argument")
    command = popenargs[0] if popenargs else kwargs.pop("args")
    if input is not None and "stdin" in kwargs:
        raise ValueError("stdin and input arguments may not both be used")
    if capture_output:
        if "stdout" in kwargs or "stderr" in kwargs:
            raise ValueError("stdout and stderr arguments may not be used with capture_output")
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    kwargs.setdefault("stdout", None)
    kwargs.setdefault("stderr", None)
    kwargs.setdefault("stdin", subprocess.PIPE if input is not None else None)
    encoding = kwargs.pop("encoding", None)
    errors = kwargs.pop("errors", None)
    text = kwargs.pop("text", None)
    universal = kwargs.pop("universal_newlines", None)
    if text is not None and universal is not None and bool(text) != bool(universal):
        raise subprocess.SubprocessError("text and universal_newlines disagree")
    text_mode = bool(text or universal or encoding or errors)
    encoding = encoding or locale.getencoding()
    if input is not None:
        if text_mode:
            if not isinstance(input, str):
                raise TypeError("text mode input must be str")
            input = input.encode(encoding, errors or "strict")
        elif not isinstance(input, bytes):
            raise TypeError("binary mode input must be bytes")
    cwd, env, shell = (
        kwargs.pop(name, default)
        for name, default in (("cwd", None), ("env", None), ("shell", False))
    )
    if timeout is None:
        effective_timeout = command_limit
    elif isinstance(timeout, (int, float)) and math.isfinite(timeout):
        effective_timeout = max(0.000001, min(timeout, command_limit))
    else:
        raise ValueError("timeout must be finite")
    result = run_command(
        command,
        cwd=cwd,
        env=env,
        shell=shell,
        input=input,
        timeout=effective_timeout,
        decode_output=False,
        _popen_options=kwargs,
        _capture_complete=True,
    )
    if result["status"] == "timeout":
        for name in ("stdout", "stderr"):
            if result[name] is not None:
                result[name] = result[name].decode("utf-8", errors="replace")
        raise CommandTimeout(result)
    if text_mode:
        for name in ("stdout", "stderr"):
            if result[name] is not None:
                result[name] = (
                    result[name]
                    .decode(encoding, errors or "strict")
                    .replace("\r\n", "\n")
                    .replace("\r", "\n")
                )
    completed = subprocess.CompletedProcess(
        command, result["returncode"], result["stdout"], result["stderr"]
    )
    if check:
        completed.check_returncode()
    return completed


@contextlib.contextmanager
def ordinary_command_scope(timeout=COMMAND_TIMEOUT_SECONDS):
    """Intercept subprocess.run only on the current inline tool-dispatch thread."""
    original_run = subprocess.run
    owner_thread = threading.get_ident()
    active = True

    def scoped_run(*args, **kwargs):
        if not active or threading.get_ident() != owner_thread:
            return original_run(*args, **kwargs)
        return bounded_subprocess_run(*args, command_limit=timeout, **kwargs)

    subprocess.run = scoped_run
    try:
        yield
    finally:
        active = False
        subprocess.run = original_run
