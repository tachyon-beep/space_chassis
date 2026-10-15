#!/usr/bin/env python3
"""What the fleet is doing, read from the record rather than from the agents.

One line per agent, plus a summary. Every number here comes from a file the
agents cannot write: the recorder's transcripts, the supervisor's lifecycle
record, the pump's state, the window's published state. An agent's own account
of itself is not evidence, and this tool does not ask for one.

    python3 scripts/status.py                 # one line per agent
    python3 scripts/status.py --verbose       # and what each one last did
    python3 scripts/status.py --json          # for anything else to read
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))

from common import read_json, tail_jsonl  # noqa: E402

VOLUMES = PROJECT / "volumes"


def size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def last_event(path: Path) -> dict:
    """The newest line of a JSONL file, without reading the whole thing."""
    records = tail_jsonl(path, max_bytes=64 * 1024)
    return records[-1] if records else {}


def count_lines(path: Path, chunk: int = 1 << 20) -> int:
    """Count the JSON lines in a file by streaming it, never by loading it.

    These files grow without bound: a transcript records the whole conversation
    on every turn, so a fleet that has been running a while has transcripts
    measured in tens of megabytes. A bounded "read the whole thing" helper
    returns None for those -- which would report a busy agent as having taken no
    turns at all, the one number an operator most needs to be right.
    """
    total = 0
    tail = b""
    try:
        with open(path, "rb") as handle:
            while True:
                block = handle.read(chunk)
                if not block:
                    break
                block = tail + block
                lines = block.split(b"\n")
                tail = lines.pop()
                total += sum(1 for line in lines if line.strip())
        if tail.strip():
            total += 1
    except OSError:
        return 0
    return total


def roster() -> dict[str, dict[str, str]]:
    """Two views of the roster, because a directory is named by its slug.

    `by_service` answers "who is agent_4"; `by_slug` answers "what is this
    directory called". Both are bookkeeping. Neither carries a rank.
    """
    data = read_json(VOLUMES / "work" / "roster.json") or {}
    agents = data.get("agents")
    if not isinstance(agents, list):
        return {"by_service": {}, "by_slug": {}}
    by_service: dict[str, dict[str, str]] = {}
    by_slug: dict[str, dict[str, str]] = {}
    for entry in agents:
        if not isinstance(entry, dict):
            continue
        service = str(entry.get("agent", ""))
        slug = str(entry.get("slug") or entry.get("name") or service)
        record = {"service": service, "name": str(entry.get("name", "")), "slug": slug}
        if service:
            by_service[service] = record
        by_slug[slug] = record
    return {"by_service": by_service, "by_slug": by_slug}


def slugs() -> list[str]:
    """Which agents exist, from the directories the world created for them.

    Read from the volumes rather than from the compose file: the question is
    which agents have ever run, and a container that was never started has no
    home to report on.
    """
    found = sorted(
        path.name
        for path in (VOLUMES / "home").glob("*")
        if path.is_dir() and path.name != ".gitkeep"
    )
    if found:
        return found
    return sorted(
        path.name for path in (VOLUMES / "telemetry" / "agents").glob("*") if path.is_dir()
    )


def agent_row(slug: str, names: dict[str, dict[str, str]]) -> dict:
    """One agent's facts, from the record.

    `slug` here is the directory's name, which is the name the agent was given.
    The service a directory belongs to comes from the roster, not from a
    positional guess: the naming is random, so there is no index to count.
    """
    record = names.get("by_slug", {}).get(slug, {})
    display = record.get("name", "")
    transcripts = VOLUMES / "transcripts" / slug
    telemetry = VOLUMES / "telemetry" / "agents" / slug
    home = VOLUMES / "home" / slug
    diary = VOLUMES / "diary" / slug
    pump = VOLUMES / "pump" / slug
    diode = VOLUMES / "diode" / slug

    meta = read_json(home / "session" / "run.json") or {}
    ended = last_event(telemetry / "lifecycle.jsonl")
    decisions = tail_jsonl(telemetry / "lifecycle.jsonl", max_bytes=256 * 1024)
    run_ends = [record for record in decisions if record.get("event") == "run_end"]
    resumed = sum(1 for record in decisions if record.get("event") == "run_resumed")
    pump_state = read_json(pump / "state.json") or {}
    entries = pump_state.get("entries") if isinstance(pump_state.get("entries"), dict) else {}
    running = [
        name
        for name, record in entries.items()
        if isinstance(record, dict) and record.get("running")
    ]
    # The window is bounded by eviction, so a figure above 100% means the
    # checkpoint predates the window tightening rather than that anything is
    # broken. Clamped and labelled, rather than printed as 187%.
    context = meta.get("context_window")
    used = meta.get("context_tokens")
    window_pct = None
    if isinstance(used, int) and isinstance(context, int) and context > 0:
        window_pct = min(100, round(100 * used / context))

    return {
        "agent": record.get("service", slug),
        "name": display,
        "slug": slug,
        "turns": count_lines(transcripts / "agent_life_transcript.jsonl"),
        "runs": sum(1 for record in decisions if record.get("event") == "run_start"),
        "resumed": resumed,
        "last_end": ended.get("exit"),
        "last_note": (ended.get("note") or "")[:160],
        "tier": ended.get("tier"),
        "context_pct": window_pct,
        "handoff": (home / "HANDOFF.md").exists(),
        "recap_bytes": size_of(home / "session" / "recap.md"),
        "diary_bytes": size_of(diary / "diary.md"),
        "pump_running": running,
        "window_ready": (diode / "state.json").exists(),
        "results": len(list((diode / "output").glob("*"))) if (diode / "output").is_dir() else 0,
        "exit_history": [record.get("exit") for record in run_ends[-12:]],
    }


def render(rows: list[dict], verbose: bool) -> str:
    if not rows:
        return (
            "no agents yet: nothing under volumes/home.\n"
            "Run `sh scripts/prepare_host.sh` and then `docker compose --profile fleet up --build`."
        )
    width = max(5, max(len(row["name"] or row["agent"]) for row in rows))
    lines = [
        f"{'agent':<9}  {'name':<{width}}  {'turns':>6}  {'runs':>5}  {'res':>4}  "
        f"{'ctx%':>5}  {'diary':>7}  {'out':>4}  {'window':<6} last"
    ]
    for row in rows:
        lines.append(
            f"{row['agent']:<9}  {row['name'] or '-':<{width}}  {row['turns']:>6}  {row['runs']:>5}  "
            f"{row['resumed']:>4}  {row['context_pct'] if row['context_pct'] is not None else '-':>5}  "
            f"{row['diary_bytes']:>7}  {row['results']:>4}  "
            f"{'yes' if row['window_ready'] else 'no':<6} {row['last_end']}"
        )
        if verbose:
            if row["last_note"]:
                lines.append(f"{'':<9}  {row['last_note']}")
            history = ", ".join(str(exit) for exit in row["exit_history"][-8:])
            pump = ", ".join(row["pump_running"]) or "nothing"
            lines.append(
                f"{'':<9}  exits: {history or '-'} | pump: {pump} | "
                f"handoff: {'yes' if row['handoff'] else 'no'} | recap: {row['recap_bytes']}b"
            )
    total_turns = sum(row["turns"] for row in rows)
    total_runs = sum(row["runs"] for row in rows)
    worst = max((row["context_pct"] or 0) for row in rows)
    running = sum(len(row["pump_running"]) for row in rows)
    lines += [
        "",
        f"{len(rows)} agent(s), {total_turns} turn(s), {total_runs} run(s), "
        f"fullest window {worst}%, {running} scheduled process(es) running",
        "Every number here is read from the record, not from an agent.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    names = roster()
    rows = [agent_row(slug, names) for slug in slugs()]
    if args.json:
        print(json.dumps({"agents": rows}, indent=2))
        return 0
    print(render(rows, args.verbose))
    return 0


if __name__ == "__main__":
    sys.exit(main())
