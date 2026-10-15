"""The operator's surfaces: the watcher and the status reader.

Both of these are read-only, and both are only useful if they read the record
rather than the agents. The tests therefore check two things: that the numbers
come out right, and that neither of them can reach into a fleet.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))
sys.path.insert(0, str(PROJECT / "scripts"))


def build_world(root: Path, slugs: list[str]) -> Path:
    """A world with just enough in it for the readers to have something to read."""
    (root / "work").mkdir(parents=True, exist_ok=True)
    for slug in slugs:
        (root / "home" / slug / "session").mkdir(parents=True, exist_ok=True)
        (root / "diary" / slug).mkdir(parents=True, exist_ok=True)
        (root / "transcripts" / slug).mkdir(parents=True, exist_ok=True)
        (root / "telemetry" / "agents" / slug).mkdir(parents=True, exist_ok=True)
        (root / "pump" / slug).mkdir(parents=True, exist_ok=True)
        (root / "diode" / slug / "output").mkdir(parents=True, exist_ok=True)
        (root / "home" / slug / "session" / "run.json").write_text(
            json.dumps(
                {"turn": 12, "context_window": 1000, "context_tokens": 250, "model": "stub"}
            ),
            encoding="utf-8",
        )
        (root / "home" / slug / "session" / "recap.md").write_text(
            "- something\n", encoding="utf-8"
        )
        # The pressure figure is derived from the saved conversation's size, not
        # from the run metadata's own count: the metadata is what the run said
        # about itself, and the conversation is what it actually sent.
        (root / "home" / slug / "session" / "conversation.json").write_text(
            "x" * 1000, encoding="utf-8"
        )
        (root / "diary" / slug / "diary.md").write_text("notes\n" * 10, encoding="utf-8")
        (root / "transcripts" / slug / "agent_life_transcript.jsonl").write_text(
            '{"at": "x", "request": {}, "response": {}}\n' * 5, encoding="utf-8"
        )
        (root / "telemetry" / "agents" / slug / "lifecycle.jsonl").write_text(
            "\n".join(
                json.dumps(record)
                for record in (
                    {"event": "run_start", "agent": slug},
                    {"event": "run_resumed", "agent": slug},
                    {"event": "run_end", "agent": slug, "exit": 42, "note": "handing over"},
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "pump" / slug / "state.json").write_text(
            json.dumps({"entries": {"beat": {"running": True}}}), encoding="utf-8"
        )
    (root / "work" / "roster.json").write_text(
        json.dumps(
            {"agents": [{"agent": slug, "name": f"name-{slug}", "slug": slug} for slug in slugs]}
        ),
        encoding="utf-8",
    )
    return root


def test_the_status_reader_reports_from_the_record(tmp_path, monkeypatch):
    """Every number a person reads must come from something an agent cannot write."""
    root = build_world(tmp_path / "volumes", ["agent_1", "agent_2"])
    monkeypatch.setenv("SC_VOLUMES", str(root))

    import status as status_module  # noqa: PLC0415 -- imported after the env is set

    monkeypatch.setattr(status_module, "VOLUMES", root)
    names = status_module.roster()
    # Two views, because a directory is named by the agent's slug while a person
    # asks about the service. Neither carries a rank.
    assert names["by_service"]["agent_1"]["name"] == "name-agent_1"
    assert names["by_slug"]["agent_1"]["service"] == "agent_1"

    rows = [status_module.agent_row(slug, names) for slug in status_module.slugs()]
    assert len(rows) == 2
    row = rows[0]
    assert row["turns"] == 5, "turns must be counted from the transcript"
    assert row["runs"] == 1
    assert row["resumed"] == 1
    assert row["last_end"] == 42
    assert row["context_pct"] == 25
    assert row["pump_running"] == ["beat"]
    assert row["slug"] == "agent_1"

    rendered = status_module.render(rows, verbose=True)
    assert "name-agent_1" in rendered
    assert "handing over" in rendered
    assert "not from an agent" in rendered


def test_the_status_reader_survives_an_empty_world(tmp_path, monkeypatch):
    """A world with nothing in it is a state, not an error."""
    import status as status_module  # noqa: PLC0415

    monkeypatch.setattr(status_module, "VOLUMES", tmp_path / "nothing")
    rendered = status_module.render([], verbose=False)
    assert "no agents yet" in rendered


def test_the_fleet_monitor_reads_and_never_writes_into_the_fleet(tmp_path, monkeypatch):
    """Its whole vocabulary is observation: read-only mounts, one output directory."""
    root = build_world(tmp_path / "w", ["agent_1"])
    import fleet_monitor  # noqa: PLC0415

    monkeypatch.setattr(fleet_monitor, "TELEMETRY_DIR", root / "telemetry")
    monkeypatch.setattr(fleet_monitor, "TRANSCRIPTS_DIR", root / "transcripts")
    monkeypatch.setattr(fleet_monitor, "WORK_DIR", root / "work")
    monkeypatch.setattr(fleet_monitor, "HOME_ROOT", root / "home")
    monkeypatch.setattr(fleet_monitor, "DIARY_ROOT", root / "diary")
    monkeypatch.setattr(fleet_monitor, "PUMP_ROOT", root / "pump")

    before = {
        path: path.read_bytes()
        for path in (
            root / "home" / "agent_1" / "session" / "run.json",
            root / "work" / "roster.json",
        )
    }
    row = fleet_monitor.agent_row("agent_1")
    summary = fleet_monitor.fleet_summary([row])

    assert row["agent"] == "agent_1"
    assert row["turn"] == 12
    assert row["context_pressure"] == 0.25
    assert row["handoff_present"] is False
    assert row["pump_running"] == ["beat"]
    assert summary["agents"] == 1
    assert summary["turns_total"] == 12

    # Nothing in the fleet's own storage changed: it read, and only read.
    for path, content in before.items():
        assert path.read_bytes() == content, f"{path} was modified by the monitor"

    assert not (root / "work" / ".fleet").exists()


def test_the_monitor_is_not_a_grader():
    """It counts and reports. A monitor that scored a fleet would be a thing for
    the fleet to satisfy instead of its own judgement, so the check is on the
    code's shape: no scoring vocabulary reaches a name, only the prose."""
    import ast  # noqa: PLC0415 -- local to this check

    source = (PROJECT / "services" / "fleet_monitor.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
    lowered = " ".join(names).lower()
    for judgement in ("score", "grade", "verdict", "penal", "reward"):
        assert judgement not in lowered, f"the monitor judges with {judgement!r}"


def test_the_containment_script_exists_and_is_runnable():
    """The claims in the docs are meant to be executable."""
    script = PROJECT / "scripts" / "verify_containment.sh"
    assert script.exists()
    assert script.stat().st_mode & 0o111, "the verifier is not executable"
    result = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, f"the verifier does not parse: {result.stderr}"


def test_prepare_host_refuses_without_a_registry(tmp_path, monkeypatch):
    """A missing crate registry is a broken floor, and the script should say so."""
    script = (PROJECT / "scripts" / "prepare_host.sh").read_text(encoding="utf-8")
    assert "vendor/registry is missing" in script
    assert "build_registry.sh" in script, "the failure must name the fix"
