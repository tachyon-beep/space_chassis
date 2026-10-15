#!/usr/bin/env python3
"""The fleet monitor: what an operator can see without asking anyone.

It reads the surfaces the world already publishes -- the supervisor's lifecycle
record, each agent's session metadata and conversation, the recorder's
transcripts, the pump's state -- and writes one line per agent per interval to
/telemetry/fleet.jsonl, plus a single current snapshot at
/telemetry/fleet.json.

Two properties are deliberate:

* **It cannot influence anything.** Every mount is read-only, it has no
  network, and it writes to exactly one directory. Its whole vocabulary is
  observation.
* **It is not a grader.** It counts turns, measures the conversation against
  the window, and notes when a conversation was folded into a recap. It does
  not decide whether any of that is good. A monitor that scored the fleet would
  be another thing for the fleet to satisfy instead of their own judgement.

The interesting quantity is `context_pressure`: how full the conversation is
against the window it is being sent in. A fleet that has run for a long time
will show it climbing, and what a team does about that is the team's problem.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from pathlib import Path

SERVICES_DIR = Path(os.environ.get("SERVICES_DIR", "/opt/services"))
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))

from common import (  # noqa: E402
    append_jsonl,
    env_int,
    iso,
    read_bounded,
    read_json,
    slugs_from_env,
    write_json_atomic,
)

TELEMETRY_DIR = Path(os.environ.get("TELEMETRY_DIR", "/telemetry"))
TRANSCRIPTS_DIR = Path(os.environ.get("TRANSCRIPTS_DIR", "/transcripts"))
WORK_DIR = Path(os.environ.get("WORK_DIR", "/work"))
HOME_ROOT = Path(os.environ.get("HOME_ROOT", "/home"))
DIARY_ROOT = Path(os.environ.get("DIARY_ROOT", "/diary"))
PUMP_ROOT = Path(os.environ.get("PUMP_ROOT", "/pump"))
FLEET_PATH = TELEMETRY_DIR / "fleet.jsonl"
SNAPSHOT_PATH = TELEMETRY_DIR / "fleet.json"
# Where each agent writes its own name, so the watcher needs no list either.
ANNOUNCE_DIR = Path(os.environ.get("ANNOUNCE_DIR", "/work/.fleet"))


def tail_size(path: Path) -> int:
    with contextlib.suppress(OSError):
        return path.stat().st_size
    return 0


def last_lifecycle(slug: str) -> dict:
    """The newest lifecycle line for one agent, without reading the whole file."""
    path = TELEMETRY_DIR / "agents" / slug / "lifecycle.jsonl"
    raw = read_bounded(path, 256 * 1024)
    if not raw:
        return {}
    for line in reversed(raw.decode("utf-8", "ignore").splitlines()):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            return record
    return {}


def transcript_stats(slug: str) -> dict:
    """Turn count and last-turn time, from the recorder's record rather than the model's."""
    path = TRANSCRIPTS_DIR / slug / "agent_life_transcript.jsonl"
    raw = read_bounded(path, 512 * 1024)
    if not raw:
        return {"turns": 0, "bytes": tail_size(path), "last_turn_at": None}
    lines = [line for line in raw.decode("utf-8", "ignore").splitlines() if line.strip()]
    turns = 0
    last_at = None
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        turns += 1
        last_at = record.get("at") or last_at
    # The tail may undercount; the file's size is the honest lower bound on turns.
    return {"turns_sampled": turns, "bytes": tail_size(path), "last_turn_at": last_at}


def agent_row(slug: str) -> dict:
    home = HOME_ROOT / slug
    session = home / "session"
    meta = read_json(session / "run.json") or {}
    conversation_path = session / "conversation.json"
    conversation_bytes = tail_size(conversation_path)
    context_tokens = None
    context_window = meta.get("context_window")
    if isinstance(conversation_bytes, int) and conversation_bytes:
        context_tokens = conversation_bytes // 4
    pressure = None
    if context_tokens and isinstance(context_window, int) and context_window > 0:
        pressure = round(min(1.0, context_tokens / context_window), 4)

    lifecycle = last_lifecycle(slug)
    pump_state = read_json(PUMP_ROOT / slug / "state.json") or {}
    pump_entries = pump_state.get("entries") if isinstance(pump_state.get("entries"), dict) else {}
    running = [
        name
        for name, record in pump_entries.items()
        if isinstance(record, dict) and record.get("running")
    ]

    return {
        "at": iso(),
        "agent": slug,
        "name": os.environ.get(f"AGENT_NAME_{slug}", ""),
        "last_event": lifecycle.get("event"),
        "last_event_at": lifecycle.get("at"),
        "last_run_exit": lifecycle.get("exit"),
        "last_action": lifecycle.get("action"),
        "last_tier": lifecycle.get("tier"),
        "turn": meta.get("turn"),
        "model": meta.get("model"),
        "conversation_bytes": conversation_bytes,
        "context_tokens_est": context_tokens,
        "context_window": context_window,
        "context_pressure": pressure,
        "recap_present": (session / "recap.md").exists(),
        "handoff_present": (home / "HANDOFF.md").exists(),
        "diary_bytes": tail_size(DIARY_ROOT / slug / "diary.md"),
        "transcript": transcript_stats(slug),
        "pump_running": running,
        "pump_entries": len(pump_entries),
    }


def fleet_summary(rows: list[dict]) -> dict:
    pressures = [
        row["context_pressure"] for row in rows if isinstance(row.get("context_pressure"), float)
    ]
    return {
        "at": iso(),
        "agents": len(rows),
        "turns_total": sum(row.get("turn") or 0 for row in rows),
        "context_pressure_mean": round(sum(pressures) / len(pressures), 4) if pressures else None,
        "context_pressure_max": max(pressures) if pressures else None,
        "with_handoff": sum(1 for row in rows if row.get("handoff_present")),
        "with_recap": sum(1 for row in rows if row.get("recap_present")),
        "pump_processes_running": sum(len(row.get("pump_running") or []) for row in rows),
    }


def discover_slugs() -> list[str]:
    """Which agents to watch, from the record rather than from a list.

    The telemetry tree is written by the supervisors, one directory per agent,
    named by the agent. Reading it means the watcher needs no configuration and
    cannot be told about an agent that was never started.
    """
    configured = slugs_from_env("AGENT_SLUGS")
    if configured:
        return configured
    found = set()
    root = TELEMETRY_DIR / "agents"
    if root.is_dir():
        found |= {path.name for path in root.iterdir() if path.is_dir()}
    announced = ANNOUNCE_DIR
    if announced.is_dir():
        found |= {path.stem for path in announced.glob("*.agent")}
    return sorted(found)


def main() -> int:
    interval = env_int("MONITOR_INTERVAL_SECONDS", 15)
    slugs = discover_slugs()
    if not slugs:
        print(
            "[fleet] nothing to watch yet: no agent has announced itself in "
            f"{ANNOUNCE_DIR} and none has written to {TELEMETRY_DIR / 'agents'}",
            file=sys.stderr,
        )
        return 1
    print(f"{iso()} [fleet] watching {len(slugs)} agent(s) every {interval}s", flush=True)
    while True:
        try:
            rows = [agent_row(slug) for slug in slugs]
            summary = fleet_summary(rows)
            with contextlib.suppress(OSError):
                append_jsonl(FLEET_PATH, summary)
                for row in rows:
                    append_jsonl(FLEET_PATH, row)
                write_json_atomic(
                    SNAPSHOT_PATH,
                    {"summary": summary, "agents": rows, "work_tree_files": count_work()},
                )
        except Exception as error:  # noqa: BLE001 -- the watcher must not die of a bad read
            print(f"{iso()} [fleet] cycle failed: {type(error).__name__}: {error}", flush=True)
        time.sleep(interval)


def count_work() -> int:
    total = 0
    for _, _, files in os.walk(WORK_DIR):
        total += len(files)
        if total > 100_000:
            break
    return total


if __name__ == "__main__":
    sys.exit(main())
