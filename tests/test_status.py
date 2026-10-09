"""scripts/status.py against a volume tree in the per-agent layout: `<kind>_<slug>/data`.

The transcript and events are recorder-shaped lines; the mirror, the notes and the pump state are
what the agent's own container writes, and every one of them must come back labelled as its claim.
"""

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import status  # noqa: E402

SYSTEM = {"role": "system", "content": "you are an agent"}
USER = {"role": "user", "content": "begin"}
CAP = "rate limited: at most 4 request(s) per hour on this socket; next available in 60 seconds"


def iso(seconds_ago: float) -> str:
    moment = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=seconds_ago)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def line(seconds_ago: float, response=None, messages=None) -> str:
    return json.dumps(
        {
            "timestamp": iso(seconds_ago),
            "stream": "core",
            "request": {"model": "m", "messages": messages or [SYSTEM, USER]},
            "response": response or {"choices": []},
        }
    )


def make_agent(volumes: Path, slug: str, *, transcript_ago=None, capped=False, mirror_ago=5.0):
    transcripts = volumes / f"transcripts_{slug}" / "data"
    transcripts.mkdir(parents=True)
    if transcript_ago is not None:
        lines = [line(transcript_ago + 30)]
        last = {"error": {"message": CAP}} if capped else None
        turn = [
            SYSTEM,
            USER,
            {"role": "assistant", "content": "", "tool_calls": []},
            {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        ]
        lines.append(line(transcript_ago, response=last, messages=turn))
        (transcripts / "agent_life_transcript.jsonl").write_text("\n".join(lines) + "\n")
        close = {"timestamp": iso(transcript_ago), "event": "close", "stream": "core"}
        close.update({"status": 429} if capped else {"status": 200, "usage": {"total_tokens": 9}})
        (transcripts / "events.jsonl").write_text(json.dumps(close) + "\n")
    telemetry = volumes / f"telemetry_{slug}" / "data"
    tombstones = telemetry / "work" / "tombstones"
    tombstones.mkdir(parents=True)
    (tombstones / "recovery_note.txt").write_text(
        "Recovery event 1: started from the image seed.\n"
    )
    (tombstones / "incarnation_note.txt").write_text("all is well, says the agent\n")
    (telemetry / "work" / "agent_stdout.log").write_text("agent starting autonomous loop\n")
    if mirror_ago is not None:
        when = time.time() - mirror_ago
        os.utime(telemetry, (when, when))
    pump = volumes / f"pump_{slug}" / "data"
    pump.mkdir(parents=True)
    (pump / "state.json").write_text(
        json.dumps({"entries": {"a": {"running": True}, "b": {"running": False}}})
    )
    (volumes / "diode" / "data" / slug / "output").mkdir(parents=True)
    return telemetry


def run_status(
    volumes: Path, *args: str, env_file: Path | None = None
) -> subprocess.CompletedProcess:
    if env_file is None:
        env_file = volumes.parent / "empty.env"
        env_file.write_text("")
    return subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "status.py"),
            "--volumes",
            str(volumes),
            "--env-file",
            str(env_file),
            "--no-docker",
            "--roster",
            str(volumes.parent / "no-roster.json"),
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": os.environ["PATH"]},
    )


def rows(result: subprocess.CompletedProcess) -> dict:
    assert result.returncode == 0, result.stderr
    return {row["slug"]: row for row in json.loads(result.stdout)["agents"]}


def test_a_capped_agent_writing_a_refusal_every_cycle_reads_capped_not_active(tmp_path):
    volumes = tmp_path / "volumes"
    make_agent(volumes, "agent_1", transcript_ago=5)
    make_agent(volumes, "agent_3", transcript_ago=5, capped=True)
    found = rows(run_status(volumes, "--json"))
    assert found["agent_1"]["liveness"] == "active"
    assert found["agent_3"]["liveness"] == "capped"
    assert found["agent_3"]["signals"]["refusals"] == 1


def test_status_reads_the_new_volume_layout_and_labels_every_claim(tmp_path):
    volumes = tmp_path / "volumes"
    make_agent(volumes, "agent_1", transcript_ago=5)
    row = rows(run_status(volumes, "--json"))["agent_1"]
    assert row["transcript_age"] < 60
    assert row["mirror_age"] < 60
    assert row["signals"]["incarnations"] == 1
    assert row["signals"]["spend"]["tokens"] == 9
    assert row["container"] is None
    claims = row["claims"]
    assert set(claims) >= {"recovery_note", "incarnation_note", "pump_running", "agent_log_age"}
    for name, claim in claims.items():
        assert claim["claim"] == "agent", name
    assert claims["pump_running"]["value"] == 1
    assert "image seed" in claims["recovery_note"]["value"]
    text = run_status(volumes).stdout
    assert "* the agent's own claim" in text


def test_slugs_come_from_the_roster_or_else_the_transcript_directories(tmp_path):
    volumes = tmp_path / "volumes"
    for slug in ("otter_one", "heron_two"):
        make_agent(volumes, slug, transcript_ago=5)
    roster = tmp_path / "roster.json"
    assert [slug for slug, _, _ in status.discover(volumes, roster)] == ["heron_two", "otter_one"]
    roster.write_text(
        json.dumps({"agents": [{"agent": "agent_1", "name": "Otter", "slug": "otter_one"}]})
    )
    assert status.discover(volumes, roster) == [("otter_one", "Otter", "agent_1")]


def test_status_survives_an_empty_volume_root(tmp_path):
    volumes = tmp_path / "volumes"
    volumes.mkdir()
    result = run_status(volumes, "--json")
    assert rows(result) == {}
    assert run_status(tmp_path / "absent").returncode == 0


def test_without_docker_the_container_column_is_absent_not_a_failure(tmp_path):
    volumes = tmp_path / "volumes"
    make_agent(volumes, "agent_1", transcript_ago=5)
    assert status.container_info(["no-such-binary-anywhere", "compose"], "agent_1") is None
    row = rows(run_status(volumes, "--json"))["agent_1"]
    assert row["container"] is None


def test_status_never_prints_a_key_from_the_env_file(tmp_path):
    volumes = tmp_path / "volumes"
    make_agent(volumes, "agent_1", transcript_ago=5)
    marker = "sk-or-v1-marker-that-must-never-print"
    env_file = tmp_path / "operator.env"
    env_file.write_text(f"OPENROUTER_API_KEY={marker}\nRECORDER_HOURLY_MAX=7\n")
    as_json = run_status(volumes, "--json", env_file=env_file)
    as_text = run_status(volumes, "--verbose", env_file=env_file)
    assert rows(as_json)["agent_1"]["signals"]["caps"]["requests"] == 7
    for result in (as_json, as_text):
        assert marker not in result.stdout + result.stderr


def test_the_mirror_clock_is_the_telemetry_root_not_the_copied_tree(tmp_path):
    volumes = tmp_path / "volumes"
    telemetry = make_agent(volumes, "agent_1", transcript_ago=5000, mirror_ago=3)
    old = time.time() - 5000
    os.utime(telemetry / "work", (old, old))
    os.utime(telemetry / "work" / "agent_stdout.log", (old, old))
    os.utime(telemetry, (time.time() - 3,) * 2)
    row = rows(run_status(volumes, "--json", "--quiet-seconds", "60"))["agent_1"]
    assert row["liveness"] == "idle-watchdog"
    os.utime(telemetry, (old, old))
    row = rows(run_status(volumes, "--json", "--quiet-seconds", "60"))["agent_1"]
    assert row["liveness"] == "stale"


def test_status_text_output_carries_no_terminal_control_characters(tmp_path):
    volumes = tmp_path / "volumes"
    telemetry = make_agent(volumes, "agent_1", transcript_ago=5)
    note = telemetry / "work" / "tombstones" / "recovery_note.txt"
    note.write_text("Recovery event 1\x1b]0;pwned\x07\x1b[2J\x9b\n")
    result = run_status(volumes, "--verbose")
    assert result.returncode == 0, result.stderr
    for control in ("\x1b", "\x07", "\x9b"):
        assert control not in result.stdout
    assert "Recovery event 1" in result.stdout


def test_a_truncated_window_is_marked_in_the_text(tmp_path, monkeypatch):
    volumes = tmp_path / "volumes"
    make_agent(volumes, "agent_1", transcript_ago=5)
    row = status.agent_row("agent_1", "agent_1", volumes, time.time(), 60, {"requests": 1}, None)
    row["signals"]["window"]["truncated"] = True
    assert "incarnations 1+" in status.render([row], verbose=False)
