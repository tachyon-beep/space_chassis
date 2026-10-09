#!/usr/bin/env python3
"""The fleet monitor: what an operator can see without asking anyone.

Every few seconds it reads each agent's record -- the recorder's transcript and events, the
watchdog's mirror root, the vehicle's result files -- through services/health.py, and publishes
the fleet's signals: /telemetry/fleet.json, the current snapshot the review panel renders, and one
summary line per pass appended to /telemetry/fleet.jsonl.

Two properties are deliberate:

* **It cannot influence anything.** Every agent bind is read-only, it has no network, and it writes
  to exactly one directory. Its whole vocabulary is observation.
* **It is not a grader.** It counts incarnations, requests, refusals and tool errors, and says
  which agents are talking, idle or silent. It does not decide whether any of that is good. A
  monitor that scored the fleet would be another thing for the fleet to satisfy instead of their
  own judgement.

What an agent writes about itself (its notes, its log) is published as its claim, labelled so, and
read without following a link it planted.
"""

from __future__ import annotations

import contextlib
import os
import sys
import time
from pathlib import Path

SERVICES_DIR = Path(os.environ.get("SERVICES_DIR", "/opt/services"))
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))

import health  # noqa: E402
from common import (  # noqa: E402
    JSONL_MAX_BYTES,
    append_jsonl,
    env_int,
    iso,
    slugs_from_env,
    write_json_atomic,
)

TRANSCRIPTS_DIR = Path(os.environ.get("TRANSCRIPTS_DIR", "/transcripts"))
MIRROR_DIR = Path(os.environ.get("MIRROR_DIR", "/mirror"))
DIODE_DIR = Path(os.environ.get("DIODE_DIR", "/diode"))
TELEMETRY_DIR = Path(os.environ.get("TELEMETRY_DIR", "/telemetry"))
LIVENESS = ("active", "capped", "idle-watchdog", "stale", "unknown")


def caps() -> dict:
    return {
        "requests": env_int("RECORDER_HOURLY_MAX", 2400),
        "tokens": env_int("RECORDER_TOKEN_HOURLY_MAX", 200000000),
    }


def agent_row(slug: str, now: float, quiet: float, limits: dict) -> dict:
    view = health.agent_view(
        TRANSCRIPTS_DIR / slug,
        MIRROR_DIR / slug,
        now=now,
        quiet=quiet,
        caps=limits,
        window=(DIODE_DIR, slug),
    )
    name = os.environ.get(f"AGENT_NAME_{slug}") or slug
    return {"slug": slug, "name": name, **view}


def fleet_summary(rows: list[dict]) -> dict:
    summary = {"agents": len(rows)}
    for state in LIVENESS:
        summary[state.replace("-", "_")] = sum(1 for row in rows if row["liveness"] == state)
    summary["refusals_last_hour"] = sum(row["signals"]["spend"]["refused"] for row in rows)
    return summary


def publish(slugs: list[str], now: float) -> dict:
    quiet = float(env_int("QUIET_SECONDS", health.QUIET_SECONDS))
    limits = caps()
    rows = [agent_row(slug, now, quiet, limits) for slug in slugs]
    snapshot = {
        "at": iso(),
        "claim_label": health.CLAIM_LABEL,
        "agents": rows,
        "summary": fleet_summary(rows),
    }
    write_json_atomic(TELEMETRY_DIR / "fleet.json", snapshot)
    # A summary derived from the transcripts, on the bounded operator_telemetry image: it rotates.
    append_jsonl(
        TELEMETRY_DIR / "fleet.jsonl",
        {"at": snapshot["at"], "summary": snapshot["summary"]},
        max_bytes=JSONL_MAX_BYTES,
    )
    return snapshot


def discover_slugs() -> list[str]:
    """The agents to watch: AGENT_SLUGS when set, else the transcript binds it was given."""
    configured = slugs_from_env("AGENT_SLUGS")
    if configured:
        return configured
    with contextlib.suppress(OSError):
        return sorted(path.name for path in TRANSCRIPTS_DIR.iterdir() if path.is_dir())
    return []


def main() -> int:
    interval = env_int("MONITOR_INTERVAL_SECONDS", 15)
    slugs = discover_slugs()
    if not slugs:
        print(f"[fleet] nothing to watch: no agent under {TRANSCRIPTS_DIR}", file=sys.stderr)
        return 1
    print(f"{iso()} [fleet] watching {len(slugs)} agent(s) every {interval}s", flush=True)
    while True:
        try:
            publish(slugs, time.time())
        except Exception as error:  # noqa: BLE001 -- the watcher must not die of a bad read
            print(f"{iso()} [fleet] pass failed: {type(error).__name__}: {error}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
