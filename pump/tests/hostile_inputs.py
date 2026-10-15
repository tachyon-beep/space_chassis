"""Hostile-input cases for readers of files that another party can write.

A helper module, not a test module: pytest does not collect it.
"""

import json
import os
import threading

FIFO_CASE = "fifo"


def hostile_cases(directory, cap, build_valid):
    """Write each hostile case under directory and yield (case_name, path).

    cap is the reader's byte limit. build_valid(value) returns a JSON-ready
    document in the reader's own shape with value placed in one field.
    """
    directory = str(directory)

    def put(name, data):
        path = os.path.join(directory, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    yield "deeply_nested", put("deeply_nested", b"[" * 60000)
    yield "infinity", put("infinity", json.dumps(build_valid(float("inf"))).encode())
    marker = json.dumps(build_valid("__overflow__")).replace('"__overflow__"', "1e999")
    yield "overflow_float", put("overflow_float", marker.encode())
    yield "nan", put("nan", json.dumps(build_valid(float("nan"))).encode())
    yield "huge_integer", put("huge_integer", json.dumps(build_valid(10**399)).encode())
    fifo = os.path.join(directory, FIFO_CASE)
    os.mkfifo(fifo)
    yield FIFO_CASE, fifo
    zero = os.path.join(directory, "symlink_zero")
    os.symlink("/dev/zero", zero)
    yield "symlink_to_device", zero
    outside = os.path.join(directory, "outside")
    os.mkdir(outside)
    target = os.path.join(outside, "target.json")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(build_valid(1), f)
    link = os.path.join(directory, "symlink_outside")
    os.symlink(target, link)
    yield "symlink_to_file", link
    dangling = os.path.join(directory, "symlink_dangling")
    os.symlink(os.path.join(outside, "missing.json"), dangling)
    yield "symlink_dangling", dangling
    as_dir = os.path.join(directory, "directory")
    os.mkdir(as_dir)
    yield "directory", as_dir
    valid = json.dumps(build_valid(1)).encode()
    yield "over_cap", put("over_cap", valid + b" " * (cap + 1 - len(valid)))
    yield "invalid_utf8", put("invalid_utf8", b'{"x": "\xff\xfe"}')
    yield "empty", put("empty", b"")


def read_with_hang_guard(fn, fifo_path, timeout=1.0):
    """Run fn() in a daemon thread and return its result; fail when it blocks.

    On a hang the write end of fifo_path is opened so the stuck reader is
    released before the failure is raised.
    """
    outcome = {}

    def run():
        try:
            outcome["value"] = fn()
        except BaseException as e:  # reported to the caller below
            outcome["error"] = e

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        try:
            os.close(os.open(fifo_path, os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass
        thread.join(timeout)
        raise AssertionError("reader blocked on a FIFO")
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]
