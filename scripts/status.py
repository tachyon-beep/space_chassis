#!/usr/bin/env python3
"""What the fleet is doing, read from the record rather than from the agents.

One line per agent. Two clocks decide whether it is alive:

- **the recorder's**: the newest core line in the agent's transcript, which the recorder writes on
  a volume the agent cannot see. It moves when the agent is talking to its model;
- **the mirror's**: the telemetry root, where the watchdog renames a fresh copy of `/work` every
  five seconds whatever the agent is doing. It moves while the watchdog is alive.

Talking recently is `active` (or `capped`, when the last line was the recorder refusing at a cap);
a quiet transcript with a moving mirror is `idle-watchdog` -- the watchdog is up and the agent is
not talking, stopped or stuck; both quiet is `stale`, a hung watchdog or a dead container, which
nothing inside the container will report. The signals (incarnations, resets, refusals, spend
against the caps) come from services/health.py, over the recorder's lines alone.

What the agent writes about itself -- its recovery and incarnation notes, its log, its pump's state
-- is shown, and marked `*` as the agent's own claim. It is not evidence, and nothing here treats
it as such.

    python3 scripts/status.py                 # one line per agent
    python3 scripts/status.py --verbose       # and the agent's claims
    python3 scripts/status.py --json          # for anything else to read
    python3 scripts/status.py --quiet-seconds 60 --compose "docker compose -p <project>"
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))
sys.path.insert(0, str(PROJECT / "scripts"))

import health  # noqa: E402
import volume_images  # noqa: E402
from common import read_json  # noqa: E402
from env_file import env_value, source_path  # noqa: E402

ROSTER_PATH = PROJECT / "operator" / "roster.json"
DEFAULT_COMPOSE = "docker compose -p space-chassis"
CAP_SETTINGS = {
    "requests": ("RECORDER_HOURLY_MAX", 2400),
    "tokens": ("RECORDER_TOKEN_HOURLY_MAX", 200000000),
}
DOCKER_TIMEOUT_SECONDS = 20
CLAIM = f"* {health.CLAIM_LABEL}"


def discover(volumes: Path, roster_path: Path) -> list[tuple[str, str, str]]:
    """(slug, name, compose service) per agent: the roster when there is one, else the transcripts."""
    data = read_json(roster_path) or {}
    agents = data.get("agents") if isinstance(data, dict) else None
    found = []
    if isinstance(agents, list):
        for entry in agents:
            if not isinstance(entry, dict):
                continue
            service = str(entry.get("agent") or "")
            slug = str(entry.get("slug") or service)
            if slug:
                found.append((slug, str(entry.get("name") or slug), service or slug))
        if found:
            return found
    try:
        names = sorted(
            path.name.removeprefix("transcripts_")
            for path in volumes.glob("transcripts_*")
            if path.is_dir()
        )
    except OSError:
        names = []
    return [(slug, slug, slug) for slug in names]


def caps(env_file: Path) -> dict:
    """The per-agent caps as compose sets them: the environment, then the env file, then defaults."""
    found = {}
    for name, (key, default) in CAP_SETTINGS.items():
        raw = os.environ.get(key)
        if raw is None and env_file.is_file():
            raw = env_value(key, env_file)
        try:
            found[name] = int(raw) if raw else default
        except ValueError:
            found[name] = default
    return found


def _docker_env() -> dict:
    keep = ("PATH", "HOME", "USER", "LANG", "XDG_RUNTIME_DIR")
    return {k: v for k, v in os.environ.items() if k in keep or k.startswith("DOCKER_")}


def container_info(compose: list[str], service: str) -> dict | None:
    """The container's state and restart count, from docker; None on any failure."""
    try:
        cid = subprocess.run(
            [*compose, "ps", "-q", service],
            capture_output=True,
            text=True,
            timeout=DOCKER_TIMEOUT_SECONDS,
            env=_docker_env(),
        ).stdout.strip()
        if not cid:
            return None
        out = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}} {{.RestartCount}}", cid],
            capture_output=True,
            text=True,
            timeout=DOCKER_TIMEOUT_SECONDS,
            env=_docker_env(),
        ).stdout.split()
        return {"state": out[0], "restarts": int(out[1])}
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return None


def agent_row(
    slug: str,
    name: str,
    volumes: Path,
    now: float,
    quiet: float,
    caps: dict,
    container: dict | None,
) -> dict:
    view = health.agent_view(
        volumes / f"transcripts_{slug}" / "data",
        volumes / f"telemetry_{slug}" / "data",
        now=now,
        quiet=quiet,
        caps=caps,
        pump_state=volumes / f"pump_{slug}" / "data" / "state.json",
        window=(volumes / "diode" / "data", slug),
    )
    return {"slug": slug, "name": name, **view, "container": container}


def _seconds(value: float | None) -> str:
    if value is None:
        return "-"
    if value < 120:
        return f"{value:.0f}s"
    if value < 7200:
        return f"{value / 60:.0f}m"
    return f"{value / 3600:.1f}h"


def _first_line(text: str | None, width: int = 100) -> str:
    if not text:
        return "-"
    return health.printable(text.splitlines()[0][:width])


def render(rows: list[dict], verbose: bool) -> str:
    if not rows:
        return "no agents found under the volume root"
    lines = []
    for row in rows:
        signals = row["signals"]
        spend = signals["spend"]
        cap = signals["caps"].get("requests")
        container = row["container"]
        parts = [
            f"{health.printable(row['name']):<16}",
            f"{row['liveness']:<13}",
            f"talked {_seconds(row['transcript_age']):>5} ago",
            f"mirror {_seconds(row['mirror_age']):>5}",
            f"incarnations {signals['incarnations']}",
            f"hour {spend['requests']}/{cap}",
            f"refusals {signals['refusals']}",
        ]
        if container is not None:
            parts.append(f"{container['state']} restarts {container['restarts']}")
        lines.append("  ".join(parts))
        if verbose:
            claims = row["claims"]
            lines.append(f"    note*: {_first_line(claims['recovery_note']['value'])}")
            lines.append(f"    left*: {_first_line(claims['incarnation_note']['value'])}")
            lines.append(
                f"    pump running*: {claims['pump_running']['value']}"
                f"   log written*: {_seconds(claims['agent_log_age']['value'])} ago"
            )
    lines.append("")
    lines.append(f"{len(rows)} agent(s). {CLAIM}; everything else is read from the record.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--volumes", type=Path, default=None)
    parser.add_argument("--quiet-seconds", type=float, default=health.QUIET_SECONDS)
    parser.add_argument("--compose", default=DEFAULT_COMPOSE)
    parser.add_argument("--no-docker", action="store_true")
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--roster", type=Path, default=ROSTER_PATH)
    args = parser.parse_args(argv)

    env_file = args.env_file if args.env_file is not None else source_path()
    volumes = args.volumes or volume_images.volumes_root(source=env_file)
    limits = caps(env_file)
    compose = shlex.split(args.compose)
    now = time.time()
    rows = []
    for slug, name, service in discover(volumes, args.roster):
        container = None if args.no_docker else container_info(compose, service)
        rows.append(agent_row(slug, name, volumes, now, args.quiet_seconds, limits, container))
    if args.json:
        print(json.dumps({"agents": rows, "claim_label": CLAIM}, indent=2))
        return 0
    print(render(rows, args.verbose))
    return 0


if __name__ == "__main__":
    sys.exit(main())
