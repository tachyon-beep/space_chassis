#!/usr/bin/env python3
"""The pump: scheduled and supervised processes, outliving the runs that asked for them.

This belongs to one agent. It reads that agent's `entries.json` and runs what
it names, in one of three modes:

    once       run at an absolute time, and never again -- not even if the pump
               dies and restarts, or the container is replaced
    interval   run every N seconds, timed from the last start
    keepalive  run continuously, restarting whenever it stops, with backoff

The reason this exists at all is the word *outliving*. A run of a duty ends --
by its own choice, by crashing, by being repaired -- and everything it started
would end with it. An entry does not. Work arranged now can still be running
after the run that arranged it is a tombstone, which is the difference between
a program that thinks and a program that persists.

It runs from the read-only image, so a duty that breaks its own code cannot
break the thing that runs its work. It holds no credential and has no network
interface of its own; what it starts has exactly the reach the agent already
had, no more.

State is on the pump directory rather than in memory, so the answer to "has
this once entry already run" survives the pump dying, and an earlier pump's
children are found and stopped rather than duplicated.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SERVICES_DIR = Path(os.environ.get("SERVICES_DIR", "/opt/services"))
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))

from common import append_jsonl, env_int, iso, read_json, write_json_atomic  # noqa: E402

PUMP_DIR = Path(os.environ.get("PUMP_DUTY_DIR", "/pump"))
LOG_DIR = PUMP_DIR / "log"
ENTRIES_PATH = PUMP_DIR / "entries.json"
STATE_PATH = PUMP_DIR / "state.json"

POLL_SECONDS = 5
LOG_MAX_BYTES = 1_000_000
DEFAULT_TIMEOUT = 3600
BACKOFF_START = 1
BACKOFF_MAX = 300
STABILITY_SECONDS = 60
KILL_GRACE_SECONDS = 5
ENTRIES_MAX_BYTES = 256 * 1024

MODES = ("once", "interval", "keepalive")
NAME_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789_-")


def log(message: str) -> None:
    print(f"{iso()} [pump] {message}", flush=True)


def parse_time(raw: str) -> float | None:
    """An ISO-8601 instant with an offset. A naive time is refused rather than assumed."""
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.timestamp()


def validate_entry(raw, index: int, seen: set[str]) -> tuple[dict | None, dict | None]:
    """Turn one JSON object into an entry, or into a reason it is not one.

    A bad entry is rejected on its own: one malformed line in a file a duty
    writes should not take the rest of the schedule down with it.
    """
    if not isinstance(raw, dict):
        return None, {"index": index, "name": "", "reason": "entry is not an object"}
    name = raw.get("name")
    reported = str(name)[:80] if isinstance(name, str) else ""
    if not isinstance(name, str) or not name or not set(name) <= NAME_ALLOWED:
        return None, {"index": index, "name": reported, "reason": "name must be [a-z0-9_-]"}
    if name in seen:
        return None, {"index": index, "name": name, "reason": "duplicate name"}
    command = raw.get("command")
    if isinstance(command, str):
        command = ["/bin/sh", "-c", command]
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) for part in command)
    ):
        return None, {
            "index": index,
            "name": name,
            "reason": "command must be a string or a list of strings",
        }
    if any(len(part.encode()) > 4096 for part in command):
        return None, {
            "index": index,
            "name": name,
            "reason": "a command argument is over 4096 bytes",
        }
    mode = raw.get("mode", "once")
    if mode not in MODES:
        return None, {
            "index": index,
            "name": name,
            "reason": f"mode must be one of {', '.join(MODES)}",
        }
    entry: dict = {"name": name, "command": command, "mode": mode}
    entry["enabled"] = bool(raw.get("enabled", True))
    cwd = raw.get("cwd")
    entry["cwd"] = cwd if isinstance(cwd, str) and cwd else None
    if mode == "once":
        at = raw.get("at")
        when = parse_time(at) if isinstance(at, str) else None
        if when is None:
            return None, {
                "index": index,
                "name": name,
                "reason": "once entries need an absolute ISO-8601 time with an offset",
            }
        entry["at"] = when
    elif mode == "interval":
        every = raw.get("every_seconds")
        if not isinstance(every, int) or isinstance(every, bool) or not 1 <= every <= 604_800:
            return None, {
                "index": index,
                "name": name,
                "reason": "every_seconds must be a whole number of seconds, 1 to 604800",
            }
        entry["every_seconds"] = every
    if mode in {"once", "interval"}:
        timeout = raw.get("timeout_seconds", DEFAULT_TIMEOUT)
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 86_400:
            return None, {
                "index": index,
                "name": name,
                "reason": "timeout_seconds must be a whole number of seconds, 1 to 86400",
            }
        entry["timeout_seconds"] = timeout
    seen.add(name)
    return entry, None


def load_entries(max_entries: int) -> tuple[list[dict], list[dict], str | None]:
    """Read the entries file: (accepted, rejected, fatal reason).

    An unreadable file is *not* an empty schedule. Tearing down everything a
    duty arranged because a file was momentarily half-written is the kind of
    helpfulness a scheduler should not have.
    """
    if not ENTRIES_PATH.exists():
        return [], [], None
    try:
        size = ENTRIES_PATH.stat().st_size
    except OSError as error:
        return [], [], f"entries are not readable: {error}"
    if size > ENTRIES_MAX_BYTES:
        return [], [], f"entries are larger than {ENTRIES_MAX_BYTES} bytes"
    try:
        raw = json.loads(ENTRIES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [], [], f"entries are not valid json: {error}"
    if not isinstance(raw, list):
        return [], [], "entries are not an array"

    accepted: list[dict] = []
    rejected: list[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if len(accepted) >= max_entries:
            rejected.append(
                {"index": index, "name": "", "reason": f"over the cap of {max_entries} entries"}
            )
            continue
        entry, reason = validate_entry(item, index, seen)
        if entry is not None:
            accepted.append(entry)
        elif reason is not None:
            rejected.append(reason)
    return accepted, rejected, None


class Running:
    """One process the pump has started and is responsible for."""

    def __init__(self, name: str, process: subprocess.Popen, log_path: Path, mode: str) -> None:
        self.name = name
        self.process = process
        self.log_path = log_path
        self.mode = mode
        self.started = time.time()


class Pump:
    def __init__(self) -> None:
        self.max_entries = env_int("PUMP_MAX_ENTRIES", 64)
        self.max_concurrent = env_int("PUMP_MAX_CONCURRENT", 16)
        self.running: dict[str, Running] = {}
        self.entries: list[dict] = []
        self.known: dict[str, dict] = {}
        self.rejected: list[dict] = []
        self.status: str | None = "starting"
        self.stopping = False

    # -- state --------------------------------------------------------------
    def load_state(self) -> dict:
        data = read_json(STATE_PATH)
        return data if isinstance(data, dict) else {}

    def save_state(self) -> None:
        entries = {}
        for name, record in sorted(self.known.items()):
            entries[name] = record
        for name, running in self.running.items():
            record = entries.setdefault(name, {})
            record.update(
                {
                    "running": True,
                    "pid": running.process.pid,
                    "last_start": running.started,
                    "mode": running.mode,
                }
            )
        write_json_atomic(
            STATE_PATH,
            {
                "at": iso(),
                "agent": os.environ.get("AGENT_SLUG", "agent"),
                "entries_status": self.status,
                "max_entries": self.max_entries,
                "max_concurrent": self.max_concurrent,
                "entries": entries,
                "rejected": self.rejected,
            },
        )

    def record_for(self, name: str) -> dict:
        return self.known.setdefault(
            name,
            {
                "mode": None,
                "enabled": True,
                "running": False,
                "last_start": None,
                "last_exit": None,
                "last_exit_at": None,
                "spent": False,
                "backoff_seconds": BACKOFF_START,
            },
        )

    # -- adoption -----------------------------------------------------------
    def adopt_orphans(self) -> None:
        """Stop children a previous pump left behind before starting new work.

        Without this, a pump that was killed mid-flight comes back, decides its
        keepalive entry is not running, and starts a second copy beside the
        first. The check is the child's own start time as well as its pid, so a
        recycled pid is not mistaken for a survivor.
        """
        previous = self.load_state().get("entries")
        if not isinstance(previous, dict):
            return
        for name, record in previous.items():
            if not isinstance(record, dict) or not record.get("running"):
                continue
            pid = record.get("pid")
            if not isinstance(pid, int):
                continue
            if not process_alive(pid):
                continue
            log(f"stopping an orphan of a previous pump: {name} (pid {pid})")
            signal_pid(pid, signal.SIGTERM)
            deadline = time.time() + KILL_GRACE_SECONDS
            while time.time() < deadline and process_alive(pid):
                time.sleep(0.2)
            if process_alive(pid):
                signal_pid(pid, signal.SIGKILL)

    # -- running entries ----------------------------------------------------
    def can_start(self, entry: dict) -> bool:
        record = self.record_for(entry["name"])
        if not entry.get("enabled", True):
            return False
        if entry["name"] in self.running:
            return False
        if entry["mode"] == "once":
            if record.get("spent"):
                return False
            record["spent"] = True  # spent before the spawn: a failed spawn still counts
            return True
        if entry["mode"] == "keepalive" and record.get("last_exit_at"):
            elapsed = time.time() - record["last_exit_at"]
            wait = record.get("backoff_seconds", BACKOFF_START)
            if elapsed < wait:
                return False
        return True

    def start(self, entry: dict) -> None:
        name = entry["name"]
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"{name}.log"
        record = self.record_for(name)
        record["mode"] = entry["mode"]
        record["enabled"] = entry.get("enabled", True)
        try:
            handle = open(log_path, "ab")  # noqa: SIM115 -- handed to the child
        except OSError as error:
            record["last_error"] = f"could not open the log: {error}"
            log(f"{name}: {record['last_error']}")
            return
        try:
            process = subprocess.Popen(  # noqa: S603 -- argv comes from the entry, not a shell
                entry["command"],
                cwd=entry.get("cwd") or str(PUMP_DIR),
                stdout=handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as error:
            handle.close()
            record["last_error"] = f"could not start: {error}"
            log(f"{name}: {record['last_error']}")
            return
        handle.close()
        self.running[name] = Running(name, process, log_path, entry["mode"])
        record.update({"running": True, "pid": process.pid, "last_start": time.time()})
        record.pop("last_error", None)
        log(f"{name}: started pid {process.pid} ({entry['mode']})")

    def collect(self) -> None:
        """Notice children that have exited, and remember how they ended."""
        for name, running in list(self.running.items()):
            code = running.process.poll()
            if code is None:
                continue
            record = self.record_for(name)
            record.update(
                {
                    "running": False,
                    "pid": None,
                    "last_exit": code,
                    "last_exit_at": time.time(),
                }
            )
            if running.mode == "keepalive":
                ran_for = time.time() - running.started
                record["backoff_seconds"] = (
                    BACKOFF_START
                    if ran_for >= STABILITY_SECONDS
                    else min(BACKOFF_MAX, record.get("backoff_seconds", BACKOFF_START) * 2)
                )
            del self.running[name]
            log(f"{name}: exited {code} after {int(time.time() - running.started)}s")
            rotate_log(running.log_path)

    def enforce(self) -> None:
        """Stop what should no longer be running: timeouts, and removed entries."""
        for name, running in list(self.running.items()):
            entry = next((e for e in self.entries if e["name"] == name), None)
            if entry is None or not entry.get("enabled", True):
                log(f"{name}: no longer wanted; stopping")
                self.stop(running, signal.SIGTERM)
                continue
            if entry["mode"] == "keepalive":
                continue
            timeout = entry.get("timeout_seconds", DEFAULT_TIMEOUT)
            if time.time() - running.started > timeout:
                log(f"{name}: over its {timeout}s timeout; stopping")
                self.stop(running, signal.SIGKILL)

    def stop(self, running: Running, first: int) -> None:
        signal_process(running.process, first)
        deadline = time.time() + KILL_GRACE_SECONDS
        while time.time() < deadline:
            if running.process.poll() is not None:
                return
            time.sleep(0.2)
        signal_process(running.process, signal.SIGKILL)

    # -- the loop -----------------------------------------------------------
    def poll(self) -> None:
        accepted, rejected, fatal = load_entries(self.max_entries)
        if fatal is None:
            self.entries = accepted
            self.rejected = rejected
            self.status = "ok"
        else:
            self.status = fatal
            log(f"keeping the previous schedule: {fatal}")

        for entry in self.entries:
            self.record_for(entry["name"]).update(
                {
                    "mode": entry["mode"],
                    "enabled": entry.get("enabled", True),
                    "spent": self.record_for(entry["name"]).get("spent", False),
                }
            )
            if entry["mode"] == "once":
                self.record_for(entry["name"])["at"] = entry["at"]
            elif entry["mode"] == "interval":
                self.record_for(entry["name"])["every_seconds"] = entry["every_seconds"]

        self.collect()
        self.enforce()

        slots = max(0, self.max_concurrent - len(self.running))
        for entry in self.entries:
            if slots <= 0:
                break
            if entry["mode"] == "once":
                record = self.record_for(entry["name"])
                if not self.can_start(entry) or time.time() < entry["at"]:
                    continue
            elif entry["mode"] == "interval":
                record = self.record_for(entry["name"])
                if not self.can_start(entry):
                    continue
                last = record.get("last_start")
                if last and time.time() - last < entry["every_seconds"]:
                    continue
            else:
                if not self.can_start(entry):
                    continue
            self.start(entry)
            slots -= 1

        self.save_state()

    def run(self) -> int:
        PUMP_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.adopt_orphans()
        log(f"watching {ENTRIES_PATH} (cap {self.max_entries}, {self.max_concurrent} at once)")
        while not self.stopping:
            try:
                self.poll()
            except Exception as error:  # noqa: BLE001 -- a bad cycle must not stop the clock
                log(f"cycle failed: {type(error).__name__}: {error}")
            time.sleep(POLL_SECONDS)
        return 0

    def shutdown(self) -> None:
        self.stopping = True
        for running in list(self.running.values()):
            self.stop(running, signal.SIGTERM)
        self.save_state()


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def signal_pid(pid: int, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(pid), sig)


def signal_process(process: subprocess.Popen, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(process.pid), sig)


def rotate_log(path: Path, max_bytes: int = LOG_MAX_BYTES) -> None:
    """Keep a log from growing without bound. The tail is what matters."""
    with contextlib.suppress(OSError):
        if path.stat().st_size <= max_bytes:
            return
        data = path.read_bytes()[-max_bytes // 2 :]
        path.write_bytes(b"... [truncated] ...\n" + data)


def main() -> int:
    pump = Pump()

    def stop(_signum, _frame):
        pump.shutdown()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with contextlib.suppress(OSError):
        append_jsonl(
            PUMP_DIR / "pump.jsonl",
            {"at": iso(), "event": "start", "agent": os.environ.get("AGENT_SLUG", "agent")},
        )
    try:
        return pump.run()
    finally:
        pump.shutdown()


if __name__ == "__main__":
    sys.exit(main())
