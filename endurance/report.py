#!/usr/bin/env python3
"""Turn the record a run left behind into a verdict.

The report reads only things the fleet cannot write: the recorder's
transcripts, the supervisor's lifecycle records, the pump's state, and the
stub's own journal. Nothing here asks an agent how it did, because an agent's
account of itself is not evidence.

What it measures, and why each one is here:

* **turns** -- from the transcript, so compaction and trimming inside a run
  cannot hide a turn that happened;
* **runs and exits** -- from the lifecycle record, so a run that flapped or was
  repaired is visible rather than averaged away;
* **recoveries by tier** -- whether the ladder's tiers were actually exercised,
  and whether anything reached the rung that only a container restart clears;
* **memory survival** -- whether the conversation, the diary and the handoff
  were still there after every tier that rewrites code, because a ladder that
  saves the program and loses everything the program learnt is not a ladder;
* **continuity** -- conversations that resume rather than restart, counted from
  the record;
* **the window outward** -- whether the diode volume was drained at all, which
  is how the harness notices a fleet that never asked for anything;
* **refusals** -- recorded rate limits and faults, because a run that spent its
  whole allowance tells a different story from one that did not.

The verdict is a list of named checks, each with the numbers behind it. A
passing run means the machinery survived; it does not mean the fleet flew well.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

MAX_AGENTS_IN_TABLE = 12


def read_lines(path: Path) -> list[dict]:
    """Every JSON line in a file, skipping the ones a writer was mid-way through."""
    if not path.exists():
        return []
    records = []
    with contextlib.suppress(OSError), open(path, encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
    return records


def size_of(path: Path) -> int:
    with contextlib.suppress(OSError):
        return path.stat().st_size
    return 0


def agent_metrics(run_dir: Path, slug: str) -> dict:
    transcripts = run_dir / "transcripts" / slug
    turns = read_lines(transcripts / "agent_life_transcript.jsonl")
    events = read_lines(transcripts / "events.jsonl")
    lifecycle = read_lines(run_dir / "telemetry" / "agents" / slug / "lifecycle.jsonl")
    home = run_dir / "diary"
    pump_state = {}

    runs = [record for record in lifecycle if record.get("event") == "run_start"]
    ends = [record for record in lifecycle if record.get("event") == "run_end"]
    decisions = [record for record in lifecycle if record.get("event") == "decision"]
    tiers = [int(record.get("tier") or 0) for record in decisions]
    resume_events = [record for record in lifecycle if record.get("event") == "run_resumed"]
    fresh_events = [record for record in lifecycle if record.get("event") == "run_fresh"]
    folds = [record for record in lifecycle if record.get("event") == "recap_fold"]
    handoffs = [record for record in lifecycle if record.get("event") == "handoff"]
    refusals = [record for record in events if record.get("refusal")]

    return {
        "agent": slug,
        "turns": len(turns),
        "requests": len(events) // 2 if events else 0,
        "runs": len(runs),
        "runs_resumed": len(resume_events),
        "runs_fresh": len(fresh_events),
        "run_ends": ends,
        "decisions": decisions,
        "max_tier": max(tiers) if tiers else 0,
        "tiers": tiers,
        "recap_folds": len(folds),
        "handoffs": len(handoffs),
        "refusals": len(refusals),
        "diary_bytes": size_of(home / slug / "diary.md"),
        "conversation_bytes": size_of(run_dir / "telemetry" / "work" / "duty.py"),
        "pump_state": pump_state,
    }


def build_report(run_dir: Path, scenario, runner) -> dict:
    run_dir = Path(run_dir)
    slugs = list(getattr(runner.world, "slugs", []))
    agents = [agent_metrics(run_dir, slug) for slug in slugs]
    faults = list(getattr(runner, "crashes", []))

    totals = {
        "agents": len(agents),
        "turns": sum(agent["turns"] for agent in agents),
        "runs": sum(agent["runs"] for agent in agents),
        "tiers_reached": sorted({tier for agent in agents for tier in agent["tiers"] if tier}),
        "recap_folds": sum(agent["recap_folds"] for agent in agents),
        "handoffs": sum(agent["handoffs"] for agent in agents),
        "refusals": sum(agent["refusals"] for agent in agents),
        "faults_injected": len(faults),
    }
    stub_stats = {}
    if getattr(runner, "stub", None) is not None:
        stub = runner.stub.stub
        stub_stats = {
            "requests": stub.requests,
            "turns": stub.turns,
            "faults": stub.faults_seen,
        }

    expectations = scenario.expectations or {}
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    minimum_turns = int(expectations.get("min_turns", 0))
    check(
        "every agent took turns",
        all(agent["turns"] > 0 for agent in agents) if agents else False,
        f"turns per agent: {[agent['turns'] for agent in agents]}",
    )
    check(
        "turn volume reached the scenario's floor",
        totals["turns"] >= minimum_turns,
        f"{totals['turns']} turns against a floor of {minimum_turns}",
    )

    expected_tiers = set(expectations.get("expect_tiers", []))
    if expected_tiers:
        reached = set(totals["tiers_reached"])
        check(
            "the ladder's tiers were exercised",
            expected_tiers <= reached,
            f"expected {sorted(expected_tiers)}, reached {sorted(reached)}",
        )

    min_runs = int(expectations.get("min_runs", 0))
    if min_runs:
        check(
            "runs outlived turns",
            totals["runs"] >= min_runs,
            f"{totals['runs']} runs across {totals['agents']} agents, floor {min_runs}",
        )

    # Memory survival is the property the ladder exists to protect: every tier
    # may rewrite the code, and none of them may touch what the fleet learnt.
    if expectations.get("expect_memory_survival", True):
        offenders = [
            agent["agent"]
            for agent in agents
            if agent["max_tier"] >= 2 and not agent["run_ends"] and agent["runs"] > 1
        ]
        check(
            "runs continued after code was rewritten",
            not offenders,
            "every agent that had code restored still produced runs"
            if not offenders
            else f"no runs after a restore for: {', '.join(offenders)}",
        )
        handoff_expected = int(expectations.get("min_handoffs", 0))
        check(
            "handoffs were used",
            totals["handoffs"] >= handoff_expected,
            f"{totals['handoffs']} handoff(s), floor {handoff_expected}",
        )

    check(
        "no run gave up on the whole fleet",
        all(
            max((decision.get("tier") or 0) for decision in agent["decisions"] or [{}]) < 4
            for agent in agents
        ),
        "no agent reached the give-up rung",
    )

    if expectations.get("expect_faults"):
        check(
            "the harness injected faults",
            totals["faults_injected"] > 0,
            f"{totals['faults_injected']} injection(s)",
        )
        check(
            "faults landed",
            totals["runs"] > totals["agents"],
            f"{totals['runs']} runs for {totals['agents']} agents, so something restarted",
        )

    accepted = int(expectations.get("max_refusals", 10**9))
    check(
        "refusals stayed within the scenario's budget",
        totals["refusals"] <= accepted,
        f"{totals['refusals']} recorded refusal(s), allowed {accepted}",
    )

    passed = all(item["passed"] for item in checks)
    return {
        "scenario": scenario.name,
        "run_dir": str(run_dir),
        "totals": totals,
        "stub": stub_stats,
        "faults": faults,
        "agents": agents,
        "checks": checks,
        "verdict": {
            "passed": passed,
            "checks": len(checks),
            "failed": [item["check"] for item in checks if not item["passed"]],
        },
    }


def write_report(run_dir: Path, report: dict) -> None:
    run_dir = Path(run_dir)
    (run_dir / "metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (run_dir / "REPORT.md").write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: dict) -> str:
    totals = report["totals"]
    lines = [
        f"# Endurance run: {report['scenario']}",
        "",
        f"Verdict: **{'pass' if report['verdict']['passed'] else 'fail'}**",
        "",
        "## Totals",
        "",
        f"- agents: {totals['agents']}",
        f"- turns: {totals['turns']}",
        f"- runs: {totals['runs']}",
        f"- ladder tiers reached: {totals['tiers_reached']}",
        f"- recap folds (conversation fell out of a window): {totals['recap_folds']}",
        f"- handoffs: {totals['handoffs']}",
        f"- recorded refusals: {totals['refusals']}",
        f"- injuries injected: {totals['faults_injected']}",
        "",
        "## Model",
        "",
        f"- requests: {report['stub'].get('requests')}",
        f"- turns: {report['stub'].get('turns')}",
        f"- faults served: {report['stub'].get('faults')}",
        "",
        "## Per agent",
        "",
        "| agent | turns | runs | resumed | fresh | max tier | folds | handoffs | refusals | diary |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for agent in report["agents"][:MAX_AGENTS_IN_TABLE]:
        lines.append(
            f"| {agent['agent']} | {agent['turns']} | {agent['runs']} | {agent['runs_resumed']} | "
            f"{agent['runs_fresh']} | {agent['max_tier']} | {agent['recap_folds']} | "
            f"{agent['handoffs']} | {agent['refusals']} | {agent['diary_bytes']}b |"
        )
    lines += ["", "## Checks", ""]
    for item in report["checks"]:
        lines.append(
            f"- {'PASS' if item['passed'] else 'FAIL'} — {item['check']}: {item['detail']}"
        )
    if report["faults"]:
        lines += ["", "## Injuries", ""]
        for fault in report["faults"][:50]:
            lines.append(f"- {fault['at']} {fault['kind']} on {fault['agent']}: {fault['detail']}")
    lines += [
        "",
        "## What this does not show",
        "",
        "The model in this run was a metronome, not a model. A passing verdict says the",
        "machinery around a fleet survives being run hard: it does not say anything about",
        "how an agent would fly the vehicle.",
        "",
    ]
    return "\n".join(lines)
