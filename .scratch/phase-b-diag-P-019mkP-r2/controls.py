"""Failure-injection controls for master §22's two cleanup paths in diag.py.

  python3 controls.py [path/to/diag.py]

Nothing here starts a scope, a process or a test. The exact source of `record_failure` and
`terminate_scope` is taken from the hashed diag.py by `ast` and executed against injected fakes:
`unit_state`, `run`, `note` and a fake clock. The module structure the paths depend on — that the
launch's `except` does nothing but call `record_failure`, and that cleanup calls `terminate_scope`
outside that `try` and requires its verdict — is checked from the same parse. Each control prints
PASS or FAIL; the exit status is the number of failures.
"""

import ast
import hashlib
import subprocess
import sys
from pathlib import Path

DIAG = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("diag.py"))
SOURCE = DIAG.read_text()
TREE = ast.parse(SOURCE)
print(f"diag.py sha256 {hashlib.sha256(DIAG.read_bytes()).hexdigest()}")
failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}{(': ' + detail) if detail else ''}")


def function(name: str) -> str:
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(SOURCE, node)


class Clock:
    """time.monotonic and time.sleep, advancing only when slept on."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Result:
    def __init__(self, rc):
        self.returncode, self.stdout, self.stderr = rc, "", ""


def harness(states, stop=None, kill=None):
    """A namespace for terminate_scope: `states` is the sequence of unit_state answers (the last
    repeats); `stop`/`kill` is an exception to raise, or None for rc 0."""
    calls, answers = [], list(states)

    def unit_state():
        calls.append("state")
        return answers.pop(0) if len(answers) > 1 else answers[0]

    def run(argv, timeout=60, cwd=None):
        verb = argv[2]
        calls.append(verb)
        raised = stop if verb == "stop" else kill
        if raised is not None:
            raise raised
        return Result(0)

    clock = Clock()
    namespace = {
        "unit_state": unit_state,
        "run": run,
        "time": clock,
        "subprocess": subprocess,
        "SCOPE": "space-chassis-pdiag-control.scope",
    }
    exec(function("terminate_scope"), namespace)
    return namespace["terminate_scope"], calls, clock


ACTIVE = {"ActiveState": "active", "LoadState": "loaded"}
GONE = {"ActiveState": "inactive", "LoadState": "not-found"}
ERROR = {"error": "TimeoutExpired: systemctl show timed out"}
TIMEOUT = subprocess.TimeoutExpired(["systemctl"], 40)

# ---------------------------------------------------------------- path 2: escalation

# The §22 case: the stop times out, and every state lookup after it fails.
terminate, calls, clock = harness([ACTIVE, ERROR], stop=TIMEOUT)
steps = []
verified = terminate(steps)
check("a failed stop with failed state lookups still attempts SIGKILL", "kill" in calls, str(calls[-3:]))
check("... and never reports termination it did not see", verified is False)
check("... and records both attempts", [list(s)[0] for s in steps] == ["stop_error", "sigkill_rc"], str(steps))
check("... within its bounds (two 15 s waits)", clock.now <= 31, f"{clock.now} s")

# The stop fails, the lookups fail, and the kill fails too: unverified, both errors recorded.
terminate, calls, _ = harness([ACTIVE, ERROR], stop=TIMEOUT, kill=OSError("bus gone"))
steps = []
check("a failed kill after a failed stop is unverified", terminate(steps) is False)
check("... recording stop_error and sigkill_error", [list(s)[0] for s in steps] == ["stop_error", "sigkill_error"], str(steps))

# The stop fails and the scope stays active, then the kill ends it: verified, after the kill.
terminate, calls, _ = harness([ACTIVE] * 35 + [GONE], stop=TIMEOUT)
steps = []
check("a scope the kill ends is verified", terminate(steps) is True and "kill" in calls, str(steps))

# The stop succeeds and the scope ends: no kill.
terminate, calls, _ = harness([ACTIVE, ACTIVE, GONE])
steps = []
check("a scope the stop ends is verified without a kill", terminate(steps) is True and "kill" not in calls, str(calls))

# Already ended (not-found, or failed): nothing is sent.
for label, state in (("not-found", GONE), ("failed", {"ActiveState": "failed", "LoadState": "loaded"})):
    terminate, calls, _ = harness([state])
    check(f"an already-{label} scope is left alone and verified", terminate([]) is True and calls == ["state"], str(calls))

# A lookup error at the very start is not an end: it stops and escalates.
terminate, calls, _ = harness([ERROR])
check("an unanswerable first lookup still stops and kills", calls.count("stop") == 0 and terminate([]) is False and "stop" in calls and "kill" in calls, str(calls))

# ---------------------------------------------------------------- path 1: best-effort reporting


class Undescribable(Exception):
    def __str__(self):
        raise RuntimeError("cannot describe")


def reporting(note_raises):
    def note(event, **fields):
        if note_raises:
            raise OSError("No space left on device")

    namespace = {"note": note}
    exec(function("record_failure"), namespace)
    return namespace["record_failure"]


supervision = []
try:
    reporting(note_raises=True)(supervision, Undescribable())
    returned = True
except BaseException as error:  # noqa: BLE001
    returned = repr(error)
check("reporting returns when the receipt write and the error's text both raise", returned is True, str(returned))
check("... and keeps the verdict entry", supervision == ["supervisor error after the launch: (undescribable)"], str(supervision))

supervision = []
reporting(note_raises=False)(supervision, KeyError("x"))
check("an ordinary error is reported with its text", supervision == ["supervisor error after the launch: KeyError: 'x'"], str(supervision))


class Unappendable(list):
    def append(self, item):
        raise MemoryError("append")


try:
    reporting(note_raises=True)(Unappendable(), ValueError("v"))
    returned = True
except BaseException as error:  # noqa: BLE001
    returned = repr(error)
check("reporting returns even when the verdict list cannot be appended to", returned is True, str(returned))

# ---------------------------------------------------------------- structure: cleanup is unconditional

launch_try = next(
    n for n in TREE.body if isinstance(n, ast.Try) and any(isinstance(h.type, ast.Name) and h.type.id == "BaseException" for h in n.handlers)
)
handler = next(h for h in launch_try.handlers if h.type.id == "BaseException")
body = [ast.get_source_segment(SOURCE, s) for s in handler.body]
check("the launch's except does nothing but call record_failure", body == ["record_failure(supervision, error)"], str(body))
check("... and the try has no finally or else that could raise first", not launch_try.finalbody and not launch_try.orelse)
after = TREE.body[TREE.body.index(launch_try) + 1 :]
after_text = "\n".join(ast.get_source_segment(SOURCE, s) for s in after)
check("cleanup calls terminate_scope at module level, after the try", 'cleanup["scope_terminated"] = terminate_scope(cleanup["steps"])' in after_text)
check("cleanup is verified only when termination is", 'cleanup["verified"] = (\n    cleanup["scope_terminated"]' in after_text)
inside = ast.get_source_segment(SOURCE, launch_try)
check("termination is not inside the launch's try", "terminate_scope(" not in inside)

print(f"{failures} failure(s)")
sys.exit(failures)
