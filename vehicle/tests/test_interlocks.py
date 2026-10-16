"""Interlock evaluation (ADR 0004, narrowing ADR 0001 choice C): evaluate what can be read, refuse what cannot.

A verb's declared interlock resolves through the registry to a threshold (comparator, `assert`, assert
dwell) on a point that is a reading of a state. Where that chain reads, the executive evaluates it:
tripped when the reading has been past `assert` for at least the dwell, by a per-threshold count of
consecutive ticks that the plant keeps in the truth (`plant.INTERLOCK_DWELL`), so a checkpoint and a
replay of the record carry it. Where it does not read, the refusal is INTERLOCK UNEVALUATED as before.
An operator's `--closed-interlock` still wins.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import console  # noqa: E402
import plant  # noqa: E402

QUIET_COAST = VEHICLE / "scenarios" / "quiet_coast.yaml"


@pytest.fixture(scope="module")
def world() -> plant.World:
    return plant.load_world(VEHICLE)


def submit(window: Path, commands: list[str]) -> None:
    (window / "console.json").write_text(json.dumps({"commands": commands, "variables": {}}))


def bodies(window: Path) -> list[str]:
    return [path.read_text() for path in sorted((window / "output").glob("*.txt"))]


@pytest.mark.parametrize(
    ("name", "threshold", "words"),
    [
        ("power.bus_a_undervoltage", "bus_a_undervoltage", None),
        ("thermal.comm_amp_high", "comm_amp_high", None),
        ("coolant_supply_high", "coolant_supply_high", None),
        ("res.cooling_water_reserve", "cooling_water_reserve", None),
        ("pump_no_flow", "pump_no_flow", None),
        # Not readable, and not given a band here: the band is UNCONFIGURED.
        ("tx_power_high", None, "whose band is 'UNCONFIGURED'"),
        # Not readable: the point is an estimate over two channels with prose for arithmetic.
        ("power.load_margin_low", None, "whose arithmetic is prose"),
        # Not readable: a template family's point (and a 2 ms dwell inside a 20 ms tick).
        ("lcl_overcurrent", None, "template family"),
        # Not readable: a threshold that says it compares another quantity than its channel's level
        # (here the difference between the buses), or that is gated by a condition no field declares.
        ("tie_dv_limit", None, "'V of difference between the two buses, not a level on either'"),
        ("hatch_open_with_pressure", None, "gated by 'any hatch in the `open` or `latched` position'"),
    ],
)
def test_each_episode_interlock_resolves_or_names_the_link_that_does_not_read(
    world, name, threshold, words
):
    interlock, problem = plant.resolve_interlock(world, name)
    if threshold is not None:
        assert interlock is not None and problem is None, problem
        assert interlock.threshold == threshold
        assert interlock in plant.watched_interlocks(world)
    else:
        assert interlock is None and words in problem, problem


def test_the_dwell_count_lives_in_the_truth_and_advances_only_while_the_reading_is_past(world):
    interlock, _ = plant.resolve_interlock(world, "coolant_supply_high")
    dt = plant.tick_seconds(world)
    values = plant.initial_values(world)
    values = plant.step(world, values, dt, [], None, ledger=plant.Ledger())
    assert values[plant.INTERLOCK_DWELL]["coolant_supply_high"] == 0
    hot = {**values, "coolant_loop_t": 290.0}  # 16.85 C, past the 10 C assert
    assert plant.interlock_past(interlock, plant.point_reading(world, interlock.point, hot))
    counts = dict(values[plant.INTERLOCK_DWELL], coolant_supply_high=499)
    after = plant._with_interlock_dwell(world, {**hot, plant.INTERLOCK_DWELL: counts})
    assert after[plant.INTERLOCK_DWELL]["coolant_supply_high"] == 500
    # 500 ticks of 20 ms is the declared 10 s dwell: tripped at 500, not at 499.
    assert plant.interlock_tripped(world, interlock, after)
    assert not plant.interlock_tripped(world, interlock, {**hot, plant.INTERLOCK_DWELL: counts})
    # Back inside the band, the count starts again.
    cool = plant._with_interlock_dwell(world, {**after, "coolant_loop_t": 280.0})
    assert cool[plant.INTERLOCK_DWELL]["coolant_supply_high"] == 0
    # The count is part of what the compare-point hashes.
    assert plant.state_hash(after) != plant.state_hash({**after, plant.INTERLOCK_DWELL: counts})


def executive(world, tmp_path, **kwargs) -> console.Executive:
    loaded = console.load_scenario_file(world, QUIET_COAST)
    built = console.Executive(
        world, tmp_path / "diode", phase="translunar_coast", scenario_file=loaded, **kwargs
    )
    built.attach("alpha")
    return built


def test_a_readable_interlock_inside_its_band_lets_the_command_through(world, tmp_path):
    built = executive(world, tmp_path)
    try:
        submit(tmp_path / "diode" / "alpha", ["set_evaporator_feed vehicle=csm state=on"])
        built.cycle()
        (body,) = bodies(tmp_path / "diode" / "alpha")
    finally:
        built.close()
    assert "state=accepted" in body and "INTERLOCK" not in body, body


def test_a_tripped_interlock_refuses_by_name_and_never_says_the_value(world, tmp_path):
    built = executive(world, tmp_path)
    try:
        built.truth = {**built.truth, "coolant_loop_t": 290.0, plant.INTERLOCK_DWELL: {"coolant_supply_high": 500}}
        submit(tmp_path / "diode" / "alpha", ["set_evaporator_feed vehicle=csm state=on"])
        built.cycle()
        (body,) = bodies(tmp_path / "diode" / "alpha")
    finally:
        built.close()
    assert "refused: INTERLOCK TRIPPED" in body and "coolant_supply_high" in body, body
    assert "thermal.coolant_supply_c" in body and "state=refused" in body
    assert "290" not in body and "16.85" not in body and "500" not in body, body


def test_one_unreadable_interlock_still_refuses_the_command_as_unevaluated(world, tmp_path):
    built = executive(world, tmp_path)
    try:
        submit(tmp_path / "diode" / "alpha", ["set_power_amplifier state=on"])
        built.cycle()
        (body,) = bodies(tmp_path / "diode" / "alpha")
    finally:
        built.close()
    assert "refused: INTERLOCK UNEVALUATED" in body, body
    assert "declares 2 interlock(s) this executive cannot evaluate" in body, body
    assert "tx_power_high" in body and "load_margin_low" in body
    # The two readable ones are evaluated, not listed as unevaluable.
    assert "comm_amp_high`" not in body and "bus_a_undervoltage`" not in body, body


def test_an_operator_s_closed_interlock_still_wins(world, tmp_path):
    built = executive(world, tmp_path, tripped_interlocks={"coolant_supply_high"})
    try:
        submit(tmp_path / "diode" / "alpha", ["set_evaporator_feed vehicle=csm state=on"])
        built.cycle()
        (body,) = bodies(tmp_path / "diode" / "alpha")
    finally:
        built.close()
    assert "state=refused" in body and "is closed" in body, body
    assert "INTERLOCK TRIPPED" not in body and "UNEVALUATED" not in body, body
