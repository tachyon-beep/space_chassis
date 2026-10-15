"""Run the vehicle's console unchanged, logging when it touches the window (diagnostics only).

`python3 trace_console.py TRACE_FILE WINDOW_ROOT CONSOLE_PY [console args...]` installs an audit
hook (PEP 578) and then runs CONSOLE_PY as `__main__`, exactly as `python3 CONSOLE_PY` would. For
every `open` of a `console.json` under WINDOW_ROOT (the claim's read), and every `os.rename` (which
`os.replace` raises) whose destination is a `console.json` or lies under an `output/` (the claim's
rewrite; a result's publication), it appends one JSON line: the monotonic clock, the event, the
paths, and the inode then at the destination. Nothing in the console changes; the hook only
observes. It exists to tell a batch erased between a claim's read and its rewrite from one that was
claimed late, for `test_the_vehicle_passes_the_contract_probe`, without editing the vehicle.
"""

from __future__ import annotations

import json
import os
import runpy
import sys
import time


def main() -> None:
    trace_path, root, console = sys.argv[1], os.path.realpath(sys.argv[2]), sys.argv[3]
    handle = open(trace_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives as long as the process
    inside = False

    def inode(path: str) -> int | None:
        try:
            return os.stat(path).st_ino
        except OSError:
            return None

    def record(event: str, **fields) -> None:
        nonlocal inside
        inside = True
        try:
            handle.write(
                json.dumps({"event": event, "monotonic_ns": time.monotonic_ns(), **fields}) + "\n"
            )
        finally:
            inside = False

    def hook(event: str, args: tuple) -> None:
        if inside:
            return
        if event == "open":
            path = args[0]
            if isinstance(path, (str, bytes, os.PathLike)):
                path = os.fsdecode(path)
                if path.endswith("console.json") and os.path.realpath(path).startswith(root):
                    record("console_open", path=path, mode=str(args[1]), inode=inode(path))
        elif event == "os.rename":
            source, destination = os.fsdecode(args[0]), os.fsdecode(args[1])
            if not os.path.realpath(destination).startswith(root):
                return
            if destination.endswith("console.json"):
                record(
                    "console_replace",
                    source=source,
                    path=destination,
                    inode_before=inode(destination),
                )
            elif f"{os.sep}output{os.sep}" in destination:
                record("result_publish", path=destination)

    sys.addaudithook(hook)
    sys.argv = [console, *sys.argv[4:]]
    sys.path[0] = os.path.dirname(os.path.abspath(console))
    runpy.run_path(console, run_name="__main__")


if __name__ == "__main__":
    main()
