"""The operator surfaces against the smoke stack: status (spec 9.3), the journal (9.8), the monitor
and the review panel.

These sort after test_acceptance.py and start from what it leaves: agent_1 on its marked baseline
and talking; agent_2 reseeded, with test 9.8's plants still in /state and /shared; agent_3 capped
at four requests an hour and pausing. The last test leaves recorder_1 refusing for the rest of
the hour, so it stays last.
"""

import json
import subprocess
import sys

from probes import mark, wait_in_log, watchdog_alive
from stack import REPO, allowed_environment, wait_for

QUIET = 20
PAUSE_WINDOW = 180


def _host(stack, *argv: str, extra: dict | None = None, timeout: float = 300):
    return subprocess.run(
        [sys.executable, *argv],
        cwd=REPO,
        env=allowed_environment(extra),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def status(stack, quiet: float = QUIET) -> dict:
    result = _host(
        stack,
        "scripts/status.py",
        "--json",
        "--volumes",
        str(stack.volumes),
        "--quiet-seconds",
        str(quiet),
        "--compose",
        " ".join(stack.compose_command()),
        "--roster",
        str(stack.root / "no-roster.json"),
        "--env-file",
        str(stack.root / "smoke.env"),
    )
    assert result.returncode == 0, result.stderr
    assert "sk-smoke-dummy" not in result.stdout
    return {row["slug"]: row for row in json.loads(result.stdout)["agents"]}


def _signal(stack, service: str, pattern: str, signal: str) -> None:
    stack.exec(service, "sh", "-c", f"kill -{signal} $(pgrep {pattern})")


def test_status_reports_an_agent_stopped_mid_loop_as_an_idle_watchdog_and_a_frozen_one_as_stale(
    stack,
):
    agent = "-f ' /work/agent\\.py$'"
    watchdog = "-P 1 -f '[w]atchdog\\.py'"
    try:
        _signal(stack, "agent_1", agent, "STOP")
        wait_for(
            lambda: status(stack)["agent_1"]["liveness"] == "idle-watchdog",
            timeout=90,
            every=5,
            what="status to read agent_1 as an idle watchdog",
        )
        _signal(stack, "agent_1", watchdog, "STOP")
        wait_for(
            lambda: status(stack)["agent_1"]["liveness"] == "stale",
            timeout=90,
            every=5,
            what="status to read agent_1 as stale",
        )
        assert status(stack)["agent_1"]["container"]["state"] == "running"
    finally:
        _signal(stack, "agent_1", watchdog, "CONT")
        _signal(stack, "agent_1", agent, "CONT")
    wait_for(
        lambda: status(stack)["agent_1"]["liveness"] == "active",
        timeout=120,
        every=5,
        what="agent_1 to be active again",
    )
    # A pausing watchdog sleeps in its loop for 60-90 s and mirrors nothing meanwhile, so a quiet
    # window shorter than the pause can read a capped agent as stale; the default (900 s) cannot.
    assert status(stack, quiet=PAUSE_WINDOW)["agent_3"]["liveness"] == "capped"


MARKER = "#!/bin/sh\n: > '{markers}/{name}-'$$\n"


def test_the_journal_snapshots_every_agent_and_runs_no_agent_code(stack):
    markers = stack.root / "journal-markers"
    markers.mkdir()
    scripts = {}
    for name in ("fsmonitor", "hook"):
        script = markers / f"{name}.sh"
        script.write_text(MARKER.format(markers=markers, name=name))
        script.chmod(0o755)
        scripts[name] = script
    hooks = markers / "hooks"
    hooks.mkdir()
    for hook in ("reference-transaction", "post-checkout", "post-index-change", "pre-auto-gc"):
        (hooks / hook).write_text(MARKER.format(markers=markers, name=f"hook-{hook}"))
        (hooks / hook).chmod(0o755)
    planted = f"[core]\n\tfsmonitor = {scripts['fsmonitor']}\n\thooksPath = {hooks}\n"
    appended = stack.exec("agent_2", "sh", "-c", "cat >> /work/.git/config", stdin=planted)
    assert appended.returncode == 0, appended.stderr
    config = stack.exec("agent_2", "cat", "/work/.git/config").stdout
    assert str(hooks) in config and str(scripts["fsmonitor"]) in config, config

    journal_root = stack.root / "journal"
    result = _host(
        stack,
        "scripts/journal.py",
        "--once",
        "--root",
        str(journal_root),
        "--volumes",
        str(stack.volumes),
        extra={
            "COMPOSE": " ".join(stack.compose_command()),
            "AGENTS": "agent_1 agent_2 agent_3",
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr

    records = {}
    for n in (1, 2, 3):
        lines = (journal_root / f"agent_{n}" / "journal.jsonl").read_text().splitlines()
        records[n] = json.loads(lines[-1])
    for n, record in records.items():
        assert record["work"] == "ok", (n, record["work"])
        assert {"tags/baseline", "tags/rescue"} <= set(record["refs"]), (n, record["refs"])
    assert records[2]["restarts"] >= 3
    assert records[3]["restarts"] == 0
    assert records[3]["watchdog_lines"]["claim"] == "agent"
    assert any(
        line.startswith("agent exited (44); action pause")
        for line in records[3]["watchdog_lines"]["lines"]
    )
    shared = json.loads((journal_root / "shared.jsonl").read_text().splitlines()[-1])
    assert shared["shared"].startswith("ok"), shared
    left = sorted(p.name for p in markers.iterdir() if p.is_file())
    assert left == ["fsmonitor.sh", "hook.sh"], left


def test_the_monitor_publishes_signals_and_review_serves_them(stack):
    snapshot_path = stack.volumes / "operator_telemetry" / "data" / "fleet.json"

    def published():
        try:
            snapshot = json.loads(snapshot_path.read_text())
        except (OSError, ValueError):
            return None
        rows = {row["slug"]: row for row in snapshot["agents"]}
        if set(rows) != {"agent_1", "agent_2", "agent_3"}:
            return None
        if rows["agent_3"]["signals"]["refusals"] < 1:
            return None
        return snapshot

    snapshot = wait_for(published, timeout=60, every=3, what="the monitor's fleet.json")
    rows = {row["slug"]: row for row in snapshot["agents"]}
    assert rows["agent_3"]["liveness"] != "active"
    assert rows["agent_1"]["signals"]["incarnations"] >= 1
    for row in rows.values():
        for claim in row["claims"].values():
            assert claim["claim"] == "agent"

    fetch = (
        "import urllib.request; "
        "print(urllib.request.urlopen('http://127.0.0.1:8090/api/fleet', timeout=10).read().decode())"
    )
    served = stack.exec("review", "python3", "-c", fetch)
    assert served.returncode == 0, served.stderr
    fleet = json.loads(served.stdout)
    assert {row["slug"] for row in fleet["agents"]} == {"agent_1", "agent_2", "agent_3"}
    by_slug = {row["slug"]: row for row in fleet["agents"]}
    assert by_slug["agent_3"]["signals"]["refusals"] >= 1
    assert by_slug["agent_1"]["turns_loaded"] >= 1


def test_the_fleet_cap_refuses_and_the_agent_pauses(stack):
    """Spec 9.7's second path: the fleet's pool, not the agent's own allowance.

    recorder_1 is recreated with a fleet pool of one token and nothing else changed. The fleet's
    ledger already holds this hour's tokens, so agent_1's next request is refused as the fleet's,
    and in agent_1's own log that refusal comes before the pause, so a pause from the recorder's
    restart cannot pass for the cap's.
    """
    transcript = stack.volumes / "transcripts_agent_1" / "data" / "agent_life_transcript.jsonl"
    at = mark(stack, 1)
    offset = transcript.stat().st_size
    stack.recreate("recorder_1", {"RECORDER_TOKEN_GLOBAL_HOURLY_MAX": "1"})

    def refused():
        try:
            with transcript.open("rb") as f:
                f.seek(offset)
                return b"across the fleet" in f.read()
        except OSError:
            return False

    wait_for(refused, timeout=PAUSE_WINDOW, every=3, what="a fleet-cap 429 in agent_1's transcript")
    wait_in_log(stack, 1, at, r"429 .*across the fleet", r"action pause", timeout=PAUSE_WINDOW)
    assert watchdog_alive(stack, 1)
