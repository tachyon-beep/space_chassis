"""The operator's surfaces: the watcher and the status reader.

Both of these are read-only, and both are only useful if they read the record
rather than the agents. The tests therefore check two things: that the numbers
come out right, and that neither of them can reach into a fleet.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))
sys.path.insert(0, str(PROJECT / "scripts"))


SYSTEM = {"role": "system", "content": "you are an agent"}
USER = {"role": "user", "content": "begin"}
CAP = "rate limited: at most 4 request(s) per hour on this socket"


def _line(seconds_ago: float, *, capped: bool = False, fresh: bool = True) -> str:
    moment = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=seconds_ago)
    messages = [SYSTEM, USER]
    if not fresh:
        messages += [{"role": "assistant", "content": "", "tool_calls": []}]
    return json.dumps(
        {
            "timestamp": moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "stream": "core",
            "request": {"model": "m", "messages": messages},
            "response": {"error": {"message": CAP}} if capped else {"choices": []},
        }
    )


def build_world(root: Path, slugs: list[str]) -> Path:
    """The monitor's view of the per-agent layout: its own read-only binds, one directory each."""
    for slug in slugs:
        transcripts = root / "transcripts" / slug
        transcripts.mkdir(parents=True)
        capped = slug.endswith("3")
        lines = [_line(40), _line(10, fresh=False), _line(5, capped=capped, fresh=False)]
        (transcripts / "agent_life_transcript.jsonl").write_text("\n".join(lines) + "\n")
        (transcripts / "events.jsonl").write_text("")
        tombstones = root / "telemetry" / "agents" / slug / "work" / "tombstones"
        tombstones.mkdir(parents=True)
        (tombstones / "recovery_note.txt").write_text("Recovery event 1: a claim.\n")
        (root / "diode" / slug / "output").mkdir(parents=True)
        (root / "diode" / slug / "output" / f"20000101T000000_000000Z_{slug}_x.txt").write_text("")
    return root


def _point_monitor_at(monkeypatch, fleet_monitor, root: Path) -> None:
    monkeypatch.setattr(fleet_monitor, "TRANSCRIPTS_DIR", root / "transcripts")
    monkeypatch.setattr(fleet_monitor, "MIRROR_DIR", root / "telemetry" / "agents")
    monkeypatch.setattr(fleet_monitor, "DIODE_DIR", root / "diode")
    monkeypatch.setattr(fleet_monitor, "TELEMETRY_DIR", root / "telemetry")


def test_the_monitor_publishes_signals_for_every_agent_in_the_new_shape(tmp_path, monkeypatch):
    root = build_world(tmp_path / "w", ["agent_1", "agent_3"])
    import fleet_monitor  # noqa: PLC0415

    _point_monitor_at(monkeypatch, fleet_monitor, root)
    monkeypatch.setenv("AGENT_NAME_agent_1", "Otter")
    snapshot = fleet_monitor.publish(["agent_1", "agent_3"], now=time.time())
    on_disk = json.loads((root / "telemetry" / "fleet.json").read_text())
    assert on_disk == snapshot
    rows = {row["slug"]: row for row in snapshot["agents"]}
    assert rows["agent_1"]["name"] == "Otter"
    assert rows["agent_1"]["liveness"] == "active"
    assert rows["agent_3"]["liveness"] == "capped"
    assert rows["agent_1"]["signals"]["incarnations"] == 1
    assert rows["agent_3"]["signals"]["refusals"] == 1
    assert snapshot["summary"]["agents"] == 2
    assert snapshot["summary"]["capped"] == 1
    lines = (root / "telemetry" / "fleet.jsonl").read_text().splitlines()
    assert len(lines) == 1 and set(json.loads(lines[0])) == {"at", "summary"}


def test_the_monitor_labels_every_mirror_value_as_the_agent_s_claim(tmp_path, monkeypatch):
    root = build_world(tmp_path / "w", ["agent_1"])
    import fleet_monitor  # noqa: PLC0415

    _point_monitor_at(monkeypatch, fleet_monitor, root)
    row = fleet_monitor.publish(["agent_1"], now=time.time())["agents"][0]
    assert row["claims"]
    for name, claim in row["claims"].items():
        assert claim["claim"] == "agent", name
    assert "a claim" in row["claims"]["recovery_note"]["value"]


def test_the_monitor_never_writes_outside_its_telemetry_directory(tmp_path, monkeypatch):
    root = build_world(tmp_path / "w", ["agent_1"])
    import fleet_monitor  # noqa: PLC0415

    _point_monitor_at(monkeypatch, fleet_monitor, root)
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    fleet_monitor.publish(["agent_1"], now=time.time())
    after = {p for p in root.rglob("*") if p.is_file()}
    assert after - set(before) == {
        root / "telemetry" / "fleet.json",
        root / "telemetry" / "fleet.jsonl",
    }
    for path, content in before.items():
        assert path.read_bytes() == content, path


def test_the_monitor_mounts_the_window_read_only():
    sys.path.insert(0, str(PROJECT / "tests"))
    import compose_text  # noqa: PLC0415

    monitor = compose_text.services((PROJECT / "docker-compose.yml").read_text())["fleet_monitor"]
    windows = [v for v in monitor["volumes"] if isinstance(v, dict) and v["target"] == "/diode"]
    assert len(windows) == 1 and windows[0]["read_only"] == "true"
    environment = monitor["environment"]
    for key in ("QUIET_SECONDS", "RECORDER_HOURLY_MAX", "RECORDER_TOKEN_HOURLY_MAX"):
        assert key in environment, key


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
