"""The window's contract, against its fixture: contract/fake_diode.py, which the smoke stack mounts
as the window (live/stack.py).

Each test pins a property that only shows up when the window is driven hard: a claim that must not
replay, an allowance that must not be raisable by the thing it bounds, a malformed batch that must
run none of itself.
"""

from __future__ import annotations

import json
import time

import fake_diode
import pytest


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
