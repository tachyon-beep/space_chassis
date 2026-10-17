"""Run the vehicle's console unchanged, logging when it touches the window (diagnostics only).

`python3 trace_console.py TRACE_FILE WINDOW_ROOT CONSOLE_PY [console args...]` installs an audit
hook (PEP 578) and then runs CONSOLE_PY as `__main__`, exactly as `python3 CONSOLE_PY` would. For
every `open` of a `console.json` under WINDOW_ROOT (the claim's read), and every `os.rename` (which
`os.replace` raises) whose destination is a `console.json` or lies under an `output/` (the claim's
rewrite; a result's publication), it appends one JSON line: the monotonic clock, the event, the
paths, and the inode then at the destination. Nothing in the console changes; the hook only
observes. It exists to tell a batch erased between a claim's read and its rewrite from one that was
claimed late, for `test_the_vehicle_passes_the_contract_probe`, without editing the vehicle.

**The console now works through directory descriptors** (`open(..., dir_fd=)`, `os.replace(...,
src_dir_fd=, dst_dir_fd=)`), so the paths it passes are relative to a window. A rename's audit event
carries its descriptors, and its destination is resolved through `/proc/self/fd`. An open's event
carries none, so a relative `console.json` is recorded as the console opened it, without an inode:
the console opens no other file of that name.

**And it claims by taking, not by rewriting (#39 option B).** A claim renames `console.json` aside
(`console_take`, a rename whose *source* is the console) and puts the emptied console back with
`os.link`, which never replaces a file (`console_link`); a result is published by a rename or a link
into `output/`. A `console_replace` (a rename *onto* `console.json`) is what the claim did before
option B, and is still recorded so a trace shows one if it ever comes back.
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

    def resolve(path: str, dir_fd) -> str:
        if os.path.isabs(path) or not isinstance(dir_fd, int) or dir_fd < 0:
            return path
        try:
            return os.path.join(os.readlink(f"/proc/self/fd/{dir_fd}"), path)
        except OSError:
            return path

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
                if os.path.basename(path) != "console.json":
                    return
                if not os.path.isabs(path):
                    record("console_open", path=path, mode=str(args[1]), inode=None)
                elif os.path.realpath(path).startswith(root):
                    record("console_open", path=path, mode=str(args[1]), inode=inode(path))
        elif event in ("os.rename", "os.link"):
            source = resolve(os.fsdecode(args[0]), args[2] if len(args) > 2 else None)
            destination = resolve(os.fsdecode(args[1]), args[3] if len(args) > 3 else None)
            if not os.path.realpath(destination).startswith(root):
                return
            if event == "os.link":
                if destination.endswith("console.json"):
                    record("console_link", source=source, path=destination)
                elif f"{os.sep}output{os.sep}" in destination:
                    record("result_publish", path=destination)
                return
            if os.path.basename(source) == "console.json":
                record("console_take", path=source, taken_as=destination)
            elif destination.endswith("console.json"):
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
