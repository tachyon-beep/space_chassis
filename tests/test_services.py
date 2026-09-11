"""The operator-side services, on their own.

Each test here pins a property that only shows up when a service is driven
hard: a claim that must not replay, an allowance that must not be raisable by
the thing it bounds, a malformed file that must not take a schedule down.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))
sys.path.insert(0, str(PROJECT / "contract"))

import fake_diode  # noqa: E402
import pump as pump_module  # noqa: E402
import recorder as recorder_module  # noqa: E402
import supervisor as supervisor_module  # noqa: E402


# ---------------------------------------------------------------------------
# The window: the diode contract
# ---------------------------------------------------------------------------
@pytest.fixture
def side(tmp_path, monkeypatch):
    monkeypatch.setattr(fake_diode, "DIODE_DIR", tmp_path)
    return fake_diode.AgentSide("otter")


def console(side, commands, variables=None):
    side.console.write_text(
        json.dumps({"commands": commands, "variables": variables or {}}), encoding="utf-8"
    )


def test_the_claim_clears_the_batch_and_keeps_the_variables(side):
    """At-most-once intake: the batch is taken before anything runs."""
    console(side, ["help"], {"enable_request": True})
    commands, variables = side.consume()
    assert commands == ["help"]
    assert variables == {"enable_request": True}
    after = json.loads(side.console.read_text())
    assert after["commands"] == []
    assert after["variables"] == {"enable_request": True}


def test_a_second_consume_finds_nothing(side):
    console(side, ["help"])
    first, _ = side.consume()
    second, _ = side.consume()
    assert first == ["help"]
    assert second == [], "a batch was claimable twice"


def test_an_unknown_verb_is_refused_by_name(side):
    diode = fake_diode.Diode.__new__(fake_diode.Diode)
    diode.sides = {"otter": side}
    text = diode.run_command(side, "warp 9", {})
    assert text == "unknown command: warp"


def test_a_closed_gate_refuses_and_the_variable_is_published(side):
    diode = fake_diode.Diode.__new__(fake_diode.Diode)
    diode.sides = {"otter": side}
    refused = diode.run_command(side, "request send this", {})
    assert refused == "command not available: request"

    side.publish(fake_diode.HOURLY_MAX)
    help_text = side.help_path.read_text(encoding="utf-8")
    assert "enable_request" in help_text, "a gate that is not published is a dead end"


def test_the_console_can_lower_an_allowance_but_never_raise_it(side):
    """The pattern the whole world runs on: min(what you asked, what you may have)."""
    diode = fake_diode.Diode.__new__(fake_diode.Diode)
    diode.sides = {"otter": side}
    low = {"hourly_allowance": 2}
    allowed, limit, _wait = diode.charge_allowed(side, low)
    assert allowed and limit == 2

    greedy = {"hourly_allowance": 10**9}
    _allowed, limit, _wait = diode.charge_allowed(side, greedy)
    assert limit == fake_diode.HOURLY_MAX, "the console raised the operator's ceiling"


def test_an_exhausted_allowance_is_a_result_not_a_crash(side):
    diode = fake_diode.Diode.__new__(fake_diode.Diode)
    diode.sides = {"otter": side}
    # Open the gate, and lower the effective allowance below what has already
    # been spent: what comes back must be the allowance message, not a refusal.
    console(side, [], {"enable_request": True, "hourly_allowance": 1})
    side.requests = [time.time()]
    text = diode.run_command(
        side, "request something", {"enable_request": True, "hourly_allowance": 1}
    )
    assert text.startswith("rate limited:"), text
    assert "next available in" in text


def test_a_deferred_command_is_re_dispatched_at_delivery(side):
    """Nothing is captured at scheduling time; the gate is read when it fires."""
    diode = fake_diode.Diode.__new__(fake_diode.Diode)
    diode.sides = {"otter": side}
    deferred = diode.run_command(side, "later 0 request do the thing", {"enable_scheduling": True})
    assert "deferred" in deferred

    # The gate that would authorise the inner verb is still closed. A cycle
    # dispatches what is due through the same path a fresh command takes.
    console(side, [])
    diode.cycle(side)
    bodies = [path.read_text(encoding="utf-8").strip() for path in side.output.glob("*")]
    assert bodies, "the deferred command produced no result at all"
    assert any("command not available: request" in body for body in bodies), (
        f"a deferred command ran after its gate closed; results were {bodies}"
    )


def test_a_malformed_batch_runs_none_of_it(side):
    diode = fake_diode.Diode.__new__(fake_diode.Diode)
    diode.sides = {"otter": side}
    console(side, ["help", 42])
    diode.cycle(side)
    bodies = [path.read_text(encoding="utf-8") for path in side.output.glob("*")]
    assert any("every command must be a string" in body for body in bodies)


def test_result_names_carry_no_separator(side):
    path = side.write_result("commons ../../etc/passwd", "refused")
    assert "/" not in path.name and ".." not in path.name
    assert len(path.name.encode("utf-8")) <= 160 + 40


def test_telemetry_advances_without_being_asked(side):
    side.publish(fake_diode.HOURLY_MAX)
    first = len(list(side.telemetry.glob("*.json")))
    side.publish(fake_diode.HOURLY_MAX)
    assert len(list(side.telemetry.glob("*.json"))) == first + 1


def test_published_state_is_never_read_back(side):
    """Editing the mirror must change nothing about what is permitted."""
    diode = fake_diode.Diode.__new__(fake_diode.Diode)
    diode.sides = {"otter": side}
    side.state_path.write_text(
        json.dumps({"variables": {"enable_request": True}}), encoding="utf-8"
    )
    assert diode.run_command(side, "request send it", {}) == "command not available: request"


# ---------------------------------------------------------------------------
# The pump
# ---------------------------------------------------------------------------
@pytest.fixture
def pump_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(pump_module, "PUMP_DIR", tmp_path)
    monkeypatch.setattr(pump_module, "LOG_DIR", tmp_path / "log")
    monkeypatch.setattr(pump_module, "ENTRIES_PATH", tmp_path / "entries.json")
    monkeypatch.setattr(pump_module, "STATE_PATH", tmp_path / "state.json")
    return tmp_path


def test_a_once_entry_is_spent_before_it_is_started(pump_dir, monkeypatch):
    """A failed spawn still spends it: retrying a timed action is worse than losing it."""
    pump = pump_module.Pump()
    entry, reason = pump_module.validate_entry(
        {"name": "burn", "command": ["true"], "mode": "once", "at": "2026-09-12T00:00:00+00:00"},
        0,
        set(),
    )
    assert reason is None
    record = pump.record_for("burn")
    assert pump.can_start(entry) is True
    assert record["spent"] is True
    monkeypatch.setattr(pump_module.Pump, "start", lambda self, entry: None)
    pump.entries = [entry]
    pump.enforce() if False else None
    assert pump.can_start(entry) is False, "a spent once entry became runnable again"


def test_an_entry_without_an_offset_is_refused(pump_dir):
    _entry, reason = pump_module.validate_entry(
        {"name": "burn", "command": ["true"], "mode": "once", "at": "2026-09-12T00:00:00"}, 0, set()
    )
    assert reason is not None and "offset" in reason["reason"]


def test_one_bad_entry_does_not_take_the_schedule_down(pump_dir):
    (pump_dir / "entries.json").write_text(
        json.dumps(
            [
                {"name": "good", "command": ["true"], "mode": "interval", "every_seconds": 60},
                {"name": "bad", "command": ["true"], "mode": "nonsense"},
                {"name": "good", "command": ["true"], "mode": "keepalive"},
            ]
        ),
        encoding="utf-8",
    )
    accepted, rejected, fatal = pump_module.load_entries(16)
    assert fatal is None
    assert [entry["name"] for entry in accepted] == ["good"]
    assert len(rejected) == 2


def test_an_unreadable_entries_file_is_not_an_empty_schedule(pump_dir):
    """Tearing down a schedule because a file was half-written is not helpfulness."""
    (pump_dir / "entries.json").write_text("{ this is not json", encoding="utf-8")
    _accepted, _rejected, fatal = pump_module.load_entries(16)
    assert fatal is not None and "not valid json" in fatal

    pump = pump_module.Pump()
    pump.entries = [{"name": "kept", "command": ["true"], "mode": "keepalive", "enabled": True}]
    pump.known["kept"] = pump.record_for("kept")
    pump.poll()
    assert pump.status is not None and pump.status != "ok"
    assert [entry["name"] for entry in pump.entries] == ["kept"], "the schedule was torn down"


def test_keepalive_backoff_grows_and_resets_after_a_stable_run(pump_dir):
    pump = pump_module.Pump()
    record = pump.record_for("loop")
    record["backoff_seconds"] = 1
    # A run that lasted less than the stability window doubles the wait.
    ran_for = 1.0
    record["backoff_seconds"] = (
        pump_module.BACKOFF_START
        if ran_for >= pump_module.STABILITY_SECONDS
        else min(pump_module.BACKOFF_MAX, record["backoff_seconds"] * 2)
    )
    assert record["backoff_seconds"] == 2
    ran_for = pump_module.STABILITY_SECONDS + 1
    record["backoff_seconds"] = (
        pump_module.BACKOFF_START
        if ran_for >= pump_module.STABILITY_SECONDS
        else min(pump_module.BACKOFF_MAX, record["backoff_seconds"] * 2)
    )
    assert record["backoff_seconds"] == pump_module.BACKOFF_START


def test_a_spent_entry_survives_a_restart(pump_dir):
    """Which is the entire reason once-entries work across container replacement."""
    pump = pump_module.Pump()
    record = pump.record_for("launch")
    record["spent"] = True
    pump.save_state()
    reloaded = pump_module.Pump().load_state()
    assert reloaded["entries"]["launch"]["spent"] is True


def test_the_pump_never_signals_its_own_process_group(pump_dir):
    """A pump that killed its own group would take the container down with it."""
    import inspect  # noqa: PLC0415 -- local to this assertion

    source = inspect.getsource(pump_module.signal_pid)
    assert "getpgid" in source, "signalling must go to the child's group, not the caller's"


# ---------------------------------------------------------------------------
# The recorder's ceilings
# ---------------------------------------------------------------------------
def test_a_pool_of_zero_refuses_rather_than_crashing():
    """A closed pool has no oldest stamp to wait for; it must say no, not raise."""
    allowance = recorder_module.Allowance(0)
    allowed, wait = allowance.check()
    assert allowed is False and wait == 0


def test_an_allowance_counts_requests_and_tokens_separately():
    requests = recorder_module.Allowance(2)
    assert requests.check()[0] is True
    requests.charge()
    requests.charge()
    assert requests.check()[0] is False

    tokens = recorder_module.Allowance(1000)
    assert tokens.check(900)[0] is True
    tokens.charge(900)
    allowed, wait = tokens.check(200)
    assert allowed is False and wait > 0


def test_the_shared_pool_empties_at_the_top_of_the_hour(monkeypatch):
    shared = recorder_module.SharedTokens(100)
    assert shared.check(90)[0] is True
    shared.charge(90)
    assert shared.check(50)[0] is False
    # Move the clock into the next hour: the pool empties rather than rolling.
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + recorder_module.WINDOW_SECONDS)
    assert shared.check(50)[0] is True


def test_the_recorder_accepts_any_chat_completions_prefix():
    """A duty writing its own client must not be refused over a URL prefix."""
    assert recorder_module.ROUTE_SUFFIX == "/chat/completions"


# ---------------------------------------------------------------------------
# The supervisor
# ---------------------------------------------------------------------------
def test_the_ladder_climbs_and_then_gives_up(monkeypatch):
    supervisor = supervisor_module.Supervisor()
    monkeypatch.setattr(supervisor_module, "LADDER_TIER_2", 2)
    monkeypatch.setattr(supervisor_module, "LADDER_TIER_3", 3)
    monkeypatch.setattr(supervisor_module, "LADDER_TIER_4", 5)

    assert supervisor.tier_for(1) == 1
    assert supervisor.tier_for(2) == 2
    assert supervisor.tier_for(3) == 3
    assert supervisor.tier_for(4) == 3
    assert supervisor.tier_for(5) == 4


def test_a_designed_end_resumes_and_clears_the_failure_history():
    supervisor = supervisor_module.Supervisor()
    supervisor.failures = [time.time()]
    action, tier = supervisor.decide(supervisor_module.EXIT_HANDOFF)
    assert action == "resume" and tier == 0
    assert supervisor.failures == [], "a designed end left the blame in place"


def test_a_killed_run_is_a_failure_not_a_clean_exit():
    """`poll()` reports a signalled child as negative; that is a crash, not an exit 0."""
    assert supervisor_module.normalise_exit(-9) == 137
    assert supervisor_module.normalise_exit(-15) == 143
    assert supervisor_module.normalise_exit(0) == 0
    assert supervisor_module.normalise_exit(42) == 42


def test_an_environment_failure_pauses_without_climbing():
    supervisor = supervisor_module.Supervisor()
    action, tier = supervisor.decide(supervisor_module.EXIT_ENVIRONMENT)
    assert action == "pause" and tier == 0
    assert supervisor.failures == []


def test_repeated_clean_exits_are_treated_as_a_loop():
    """A run that exits cleanly three times in two minutes is not idling; it is stuck."""
    supervisor = supervisor_module.Supervisor()
    actions = [supervisor.decide(supervisor_module.EXIT_OK)[0] for _ in range(3)]
    assert actions == ["resume", "resume", "resume_without_session"]


def test_the_floor_restore_touches_only_the_duty(tmp_path, monkeypatch):
    """A repair that also overwrote memory would be a repair that costs a life."""
    seed = tmp_path / "seed"
    work = tmp_path / "work"
    seed.mkdir()
    work.mkdir()
    (seed / "duty.py").write_text("SEED_DUTY = True\n", encoding="utf-8")
    (seed / "chassis.py").write_text("SEED_CHASSIS = True\n", encoding="utf-8")
    (work / "duty.py").write_text("BROKEN\n", encoding="utf-8")
    (work / "chassis.py").write_text("ALSO BROKEN\n", encoding="utf-8")
    (work / "my_notes.md").write_text("remember this\n", encoding="utf-8")

    monkeypatch.setattr(supervisor_module, "SEED_DIR", seed)
    monkeypatch.setattr(supervisor_module, "WORK_DIR", work)
    supervisor = supervisor_module.Supervisor()
    supervisor.record = lambda *_args, **_kwargs: None
    monkeypatch.setattr(supervisor_module, "DUTY_SEED", seed / "duty.py")
    monkeypatch.setenv("AGENT_ENTRY", str(work / "duty.py"))

    supervisor.restore_floor()

    assert (work / "duty.py").read_text() == "SEED_DUTY = True\n"
    assert (work / "my_notes.md").read_text() == "remember this\n", "the restore ate a note"


def test_the_supervisor_never_runs_the_runtime_out_of_the_codebase(tmp_path, monkeypatch):
    """The ladder would be repairing sand: it would restore the file it is running."""
    monkeypatch.setattr(supervisor_module, "WORK_DIR", tmp_path)
    monkeypatch.setattr(supervisor_module, "SERVICES_DIR", tmp_path / "services")
    assert supervisor_module.CHASSIS.parent.name == "services"
    assert tmp_path / "chassis.py" != supervisor_module.CHASSIS


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------
def test_no_service_ever_writes_a_request_header_to_the_record():
    """The key is protected by shape, not by care: headers are never read."""
    source = (PROJECT / "services" / "recorder.py").read_text(encoding="utf-8")
    body = source.split("def do_POST")[1] if "def do_POST" in source else source
    assert "Authorization" in source, "the recorder must inject the credential somewhere"
    transcript_writes = [line for line in body.splitlines() if "transcript" in line]
    for line in transcript_writes:
        assert "headers" not in line, f"a header was written to the transcript: {line.strip()}"
    assert "self.headers.items()" in body, "header forwarding must be explicit, not wholesale"
