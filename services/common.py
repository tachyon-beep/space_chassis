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
import errno as errno_module
import json
import os
import tempfile
import threading
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


# ---------------------------------------------------------------------------
# Custody: the recorder's append-only record (SV-015 v2 section 1.5)
# ---------------------------------------------------------------------------
# `append_jsonl` above stays as it is for every other service. The recorder's
# transcript and events go through `RecordStore.append_record`, which says what
# actually happened to each line instead of raising:
#
#   failed                 no byte of the line was written
#   partial                some bytes were written, then an error; not a record
#   appended               every byte written and the line starts on a line
#                          boundary -- readable -- but either no data sync was
#                          asked for or a name on its path is not yet synced
#                          (`dir_unsynced`)
#   appended_fsync_failed  every byte written and readable; the data sync failed,
#                          so its durability is unknown (and stays degraded)
#   durable                readable, data synced, and every directory entry on
#                          its path synced after it was seen to exist
#
# "Durable" means what returned syscalls mean under an honest flush. Nothing
# here was checked against a real power loss; that is a deployment question.
#
# The assumptions, stated once: one process writes a given root (two recorders
# would race the boundary check); the root already exists and its own durability
# is the host's business; every path is a direct child of the root or of one of
# its slug directories.
APPEND_RESULT_STATUSES = ("failed", "partial", "appended", "appended_fsync_failed", "durable")
READABLE_STATUSES = frozenset({"appended", "appended_fsync_failed", "durable"})


class AppendResult:
    """The outcome of one append: its class, bytes written, and any errno."""

    __slots__ = ("status", "written", "errno", "dir_unsynced", "detail")

    def __init__(
        self,
        status: str,
        written: int = 0,
        errno: int | None = None,
        dir_unsynced: bool = False,
        detail: str | None = None,
    ) -> None:
        self.status = status
        self.written = written
        self.errno = errno
        self.dir_unsynced = dir_unsynced
        self.detail = detail

    @property
    def readable(self) -> bool:
        """Every byte is on disk and starts on a line boundary: a reader sees one record."""
        return self.status in READABLE_STATUSES

    def __repr__(self) -> str:
        return (
            f"AppendResult({self.status!r}, written={self.written}, errno={self.errno}, "
            f"dir_unsynced={self.dir_unsynced})"
        )


class FileOps:
    """The system calls the store makes, in one place so a test can fail any of them."""

    def open(self, path: str, flags: int, mode: int) -> int:
        return os.open(path, flags, mode)

    def fstat_size(self, fd: int) -> int:
        return os.fstat(fd).st_size

    def pread(self, fd: int, length: int, offset: int) -> bytes:
        return os.pread(fd, length, offset)

    def write(self, fd: int, data: memoryview) -> int:
        return os.write(fd, data)

    def fdatasync(self, fd: int) -> None:
        os.fdatasync(fd)

    def sync_dir(self, path: str) -> None:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def close(self, fd: int) -> None:
        os.close(fd)


def encode_record(record: dict) -> bytes:
    """One record as one ASCII JSON line. Raises ValueError/TypeError/RecursionError.

    ASCII escapes keep a lone surrogate representable and keep the transient
    string at one byte per character; `allow_nan=False` keeps every line JSON.
    """
    text = json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    return text.encode("ascii") + b"\n"


class _PathState:
    __slots__ = ("lock", "fd", "names_durable", "degraded")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.fd: int | None = None
        self.names_durable = False
        self.degraded = False


class RecordStore:
    """Append-only JSON-line files under one root, each behind its own lock.

    The per-path lock is never the budget's: a slow disk stalls the requests
    writing to that one file and nothing else. Descriptors are cached per path
    and dropped after any error, so the next append reopens and re-fences the
    names. The number of paths is capped (the recorder's are bounded by its
    slug cap); a path beyond the cap is refused as `failed`, never evicted.
    """

    def __init__(self, root: Path, *, max_paths: int = 256, ops: FileOps | None = None) -> None:
        self.root = Path(root)
        self.max_paths = max_paths
        self.ops = ops or FileOps()
        self._paths: dict[Path, _PathState] = {}
        self._paths_lock = threading.Lock()
        self._root_synced_for: set[Path] = set()  # slug directories whose root sync returned
        self._closed = False

    # -- path bookkeeping ---------------------------------------------------
    def _state(self, path: Path) -> _PathState | None:
        with self._paths_lock:
            if self._closed:
                return None
            state = self._paths.get(path)
            if state is None:
                if len(self._paths) >= self.max_paths:
                    return None
                state = self._paths[path] = _PathState()
            return state

    def degraded(self, path: Path) -> bool:
        with self._paths_lock:
            state = self._paths.get(Path(path))
        return bool(state and state.degraded)

    def _check_path(self, path: Path) -> None:
        parent = path.parent
        if parent != self.root and parent.parent != self.root:
            raise ValueError("a record path is a child of the root or of a slug directory")

    # -- the append ---------------------------------------------------------
    def append_record(self, path: Path, record: dict, *, fsync: bool = True) -> AppendResult:
        path = Path(path)
        self._check_path(path)
        try:
            line = encode_record(record)
        except (ValueError, TypeError, RecursionError):
            return AppendResult("failed", detail="unserializable")
        state = self._state(path)
        if state is None:
            return AppendResult("failed", errno=errno_module.EMFILE, detail="no_capacity")
        with state.lock:
            return self._append_locked(path, state, line, fsync)

    def _append_locked(self, path: Path, state: _PathState, line: bytes, fsync: bool) -> AppendResult:
        ops = self.ops
        if state.fd is None:
            try:
                state.fd = self._open(path)
            except OSError as error:
                return AppendResult("failed", errno=error.errno, detail="open")
            state.names_durable = False
        if not state.names_durable:
            state.names_durable = self._fence_names(path)
        fd = state.fd
        # Boundary from disk, before every append: a fragment left by an
        # earlier failed write -- this process's or a dead one's -- becomes
        # its own unparseable line instead of swallowing this record.
        try:
            size = ops.fstat_size(fd)
            prefix = b"\n" if size > 0 and ops.pread(fd, 1, size - 1) != b"\n" else b""
        except OSError as error:
            self._drop(state)
            return AppendResult("failed", errno=error.errno, detail="boundary")
        data = memoryview(prefix + line)
        written = 0
        while written < len(data):
            try:
                count = ops.write(fd, data[written:])
            except InterruptedError:
                continue
            except OSError as error:
                self._drop(state)
                status = "partial" if written else "failed"
                return AppendResult(status, written, error.errno, detail="write")
            if not count:
                # A regular file never accepts zero bytes of a non-empty
                # write; looping on it would never end.
                self._drop(state)
                return AppendResult("partial" if written else "failed", written, detail="zero_write")
            written += count
        if not fsync:
            return AppendResult("appended", written, dir_unsynced=not state.names_durable)
        try:
            ops.fdatasync(fd)
        except OSError as error:
            state.degraded = True
            self._drop(state)
            return AppendResult(
                "appended_fsync_failed",
                written,
                error.errno,
                dir_unsynced=not state.names_durable,
                detail="fdatasync",
            )
        if state.names_durable:
            return AppendResult("durable", written)
        return AppendResult("appended", written, dir_unsynced=True)

    def _open(self, path: Path) -> int:
        flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC
        try:
            return self.ops.open(str(path), flags | os.O_EXCL, 0o644)
        except FileExistsError:
            return self.ops.open(str(path), flags, 0o644)

    def _fence_names(self, path: Path) -> bool:
        """Sync the file's directory, and the root once per slug. True only if all returned.

        A failure leaves the path's names unfenced; the next append tries again,
        and nothing is reported durable until a whole fence has returned.
        """
        parent = path.parent
        try:
            self.ops.sync_dir(str(parent))
        except OSError:
            return False
        if parent == self.root:
            # A root-level file: the root's own entry is the host's to fence.
            return True
        with self._paths_lock:
            done = parent in self._root_synced_for
        if done:
            return True
        try:
            self.ops.sync_dir(str(self.root))
        except OSError:
            return False
        with self._paths_lock:
            self._root_synced_for.add(parent)
        return True

    def _drop(self, state: _PathState) -> None:
        if state.fd is not None:
            with contextlib.suppress(OSError):
                self.ops.close(state.fd)
        state.fd = None
        state.names_durable = False

    def close(self) -> None:
        """Close every cached descriptor; later appends are refused as `failed`."""
        with self._paths_lock:
            self._closed = True
            states = list(self._paths.values())
        for state in states:
            with state.lock:
                self._drop(state)


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
