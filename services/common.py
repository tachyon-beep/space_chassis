"""Shared pieces for every operator-side service.

Standard library only, and deliberately small: this module is imported by the
recorder, the supervisor, the pump and the watcher, all of which run from the
read-only image and are never visible to an agent.

The one thing worth stating out loud is `write_json_atomic`. Every service here
publishes a file that somebody else reads while it is being written -- the
pump's state, the supervisor's lifecycle record, the recorder's socket
directory. A reader that catches a half-written file must not conclude anything
about the world, so every published file is built in a temporary beside it and
moved into place.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

# A single file an agent can write is bounded everywhere it is read, so a
# corrupt or hostile file costs a refusal rather than a service.
MAX_READ_BYTES = 4 * 1024 * 1024


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def stamp(now: dt.datetime | None = None) -> str:
    """A filesystem-safe UTC timestamp: 20260912T021345_123456Z."""
    now = now or utc_now()
    return now.strftime("%Y%m%dT%H%M%S_%f") + "Z"


def iso(now: dt.datetime | None = None) -> str:
    return (now or utc_now()).isoformat().replace("+00:00", "Z")


def slugify(text: str, max_bytes: int = 160) -> str:
    """Every character that is not alphanumeric becomes an underscore.

    Truncation is by *bytes* after encoding, so a multi-byte character at the
    boundary cannot produce a partial sequence, and no separator or traversal
    sequence can survive into a path.
    """
    safe = "".join(ch if ch.isalnum() else "_" for ch in text)
    return safe.encode("utf-8")[:max_bytes].decode("utf-8", "ignore")


def read_bounded(path: Path, limit: int = MAX_READ_BYTES) -> bytes | None:
    """Read at most `limit` bytes; None when the file is missing or larger.

    Reading exactly one byte past the limit is what makes "larger" knowable
    without stat(), which would race with a writer.
    """
    try:
        with open(path, "rb") as handle:
            data = handle.read(limit + 1)
    except OSError:
        return None
    if len(data) > limit:
        return None
    return data


def read_json(path: Path, limit: int = MAX_READ_BYTES) -> Any | None:
    """Parse a bounded JSON file, or None if it is absent, oversized or broken."""
    raw = read_bounded(path, limit)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def write_json_atomic(path: Path, data: Any, mode: int = 0o644) -> None:
    """Serialise `data` to `path`, replacing it in one move.

    The temporary is created in the destination directory so the rename stays
    on one filesystem, and its mode is forced rather than inherited from the
    umask: a published file's permissions should not depend on how a service
    happened to be started.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


def write_text_atomic(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


def append_jsonl(path: Path, record: dict) -> None:
    """Append one JSON record. Failure is the caller's to contain.

    Append-only is the point: a record of what happened is not something a
    later event should be able to rewrite.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def tail_jsonl(path: Path, max_bytes: int = 512 * 1024) -> list[dict]:
    """The records in a JSONL file, from an offset that is a line boundary.

    A reader that starts at byte zero of a file an agent can append to will
    eventually read a partial line; the first partial line of the window is
    therefore discarded rather than parsed hopefully.
    """
    if not path.exists():
        return []
    size = path.stat().st_size
    start = max(0, size - max_bytes)
    records: list[dict] = []
    with open(path, "rb") as handle:
        if start:
            handle.seek(start)
            handle.readline()
        for raw in handle:
            try:
                records.append(json.loads(raw.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
    return records


@contextlib.contextmanager
def env_defaults(**values: str) -> Iterator[None]:
    """Temporarily set environment defaults, restoring what was there after."""
    saved = {key: os.environ.get(key) for key in values}
    for key, value in values.items():
        os.environ.setdefault(key, value)
    try:
        yield
    finally:
        for key, previous in saved.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


def env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_optional_int(name: str) -> int | None:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def env_bool(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def slugs_from_env(name: str = "AGENT_SLUGS", default: str = "") -> list[str]:
    raw = (os.environ.get(name) or default).strip()
    return [item.strip() for item in raw.split(",") if item.strip()]
