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
import re
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
        # ADR 0004 operator items 1 and 2 (chosen; decided by John 2026-10-16): a constant ceiling, and the margin
        # as the rated output of bus A's two modules less its load.
        ("tx_power_high", "tx_power_high", None),
        ("power.load_margin_low", "load_margin_low", None),
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
        assert interlock.key.endswith("." + threshold)
        assert interlock in plant.watched_interlocks(world)
    else:
        assert interlock is None and words in problem, problem


def test_the_dwell_count_lives_in_the_truth_and_advances_only_while_the_reading_is_past(world):
    interlock, _ = plant.resolve_interlock(world, "coolant_supply_high")
    dt = plant.tick_seconds(world)
    values = plant.initial_values(world)
    values = plant.step(world, values, dt, [], None, ledger=plant.Ledger())
    assert values[plant.INTERLOCK_DWELL]["thermal.coolant_supply_high"] == 0
    hot = {**values, "coolant_loop_t": 290.0}  # 16.85 C, past the 10 C assert
    assert plant.interlock_past(interlock, plant.point_reading(world, interlock.point, hot))
    counts = {**values[plant.INTERLOCK_DWELL], "thermal.coolant_supply_high": 499}
    after = plant._with_interlock_dwell(world, {**hot, plant.INTERLOCK_DWELL: counts})
    assert after[plant.INTERLOCK_DWELL]["thermal.coolant_supply_high"] == 500
    # 500 ticks of 20 ms is the declared 10 s dwell: tripped at 500, not at 499.
    assert plant.interlock_tripped(world, interlock, after)
    assert not plant.interlock_tripped(world, interlock, {**hot, plant.INTERLOCK_DWELL: counts})
    # Back inside the band, the count starts again.
    cool = plant._with_interlock_dwell(world, {**after, "coolant_loop_t": 280.0})
    assert cool[plant.INTERLOCK_DWELL]["thermal.coolant_supply_high"] == 0
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


def run(built, tmp_path, command: str) -> str:
    submit(tmp_path / "diode" / "alpha", [command])
    built.cycle()
    (body,) = bodies(tmp_path / "diode" / "alpha")
    for path in (tmp_path / "diode" / "alpha" / "output").glob("*.txt"):
        path.unlink()
    return body


def trip(world, built, overrides: dict, name: str) -> None:
    """Put the reading past its threshold and the dwell count past its dwell, and check it trips."""
    interlock, problem = plant.resolve_interlock(world, name)
    assert interlock is not None, problem
    counts = {**(built.truth.get(plant.INTERLOCK_DWELL) or {}), interlock.key: 10**6}
    built.truth = {**built.truth, **overrides, plant.INTERLOCK_DWELL: counts}
    assert plant.interlock_tripped(world, interlock, built.truth), name


def test_a_tripped_interlock_refuses_by_name_and_never_says_the_value(world, tmp_path):
    # Stopping the evaporator under a hot loop is the direction `coolant_supply_high` guards.
    built = executive(world, tmp_path)
    try:
        built.truth = {
            **built.truth,
            "coolant_loop_t": 290.0,
            plant.INTERLOCK_DWELL: {"thermal.coolant_supply_high": 500},
        }
        body = run(built, tmp_path, "set_evaporator_feed vehicle=csm state=off")
    finally:
        built.close()
    assert "refused: INTERLOCK TRIPPED" in body and "coolant_supply_high" in body, body
    assert "thermal.coolant_supply_c" in body and "state=refused" in body
    # The state hash is hex and can contain any run of digits, so it is taken out before the check.
    words = re.sub(r"\b[0-9a-f]{16,}\b", "", body)
    assert "290" not in words and "16.85" not in words and "500" not in words, body


# ADR 0004 §Direction: an interlock guards a direction of its verb, and the safing direction — the
# recovery from the very condition the guard watches — is taken while the guard is tripped.
SAFING = [
    # (interlock, truth past its threshold, the safing command taken, the guarded command refused)
    (
        "coolant_supply_high",
        {"coolant_loop_t": 290.0},
        "set_evaporator_feed vehicle=csm state=on",
        "set_evaporator_feed vehicle=csm state=off",
    ),
    (
        "coolant_supply_high",
        {"coolant_loop_t": 290.0},
        "set_coolant_pump loop=loop_primary pump=pump_2 state=on",
        "set_coolant_pump loop=loop_primary pump=pump_1 state=off",
    ),
    (
        "pump_no_flow",
        {"coolant_flow_kg_s": 0.0},
        "set_coolant_pump loop=loop_primary pump=pump_2 state=on",
        "set_coolant_pump loop=loop_primary pump=pump_1 state=off",
    ),
    (
        "thermal.comm_amp_high",
        {"comm_amp_t": 340.0},
        "set_power_amplifier state=off",
        "set_power_amplifier state=on",
    ),
    (
        "power.bus_a_undervoltage",
        {"bus_a_v": 20.0},
        "set_power_amplifier state=off",
        "set_power_amplifier state=on",
    ),
    (
        "power.load_margin_low",
        {"bus_a_load_w": 2800.0},
        "set_power_amplifier state=off",
        "set_power_amplifier state=on",
    ),
]


@pytest.mark.parametrize(("name", "overrides", "safing", "guarded"), SAFING)
def test_the_safing_direction_is_taken_while_tripped(world, tmp_path, name, overrides, safing, guarded):
    built = executive(world, tmp_path)
    try:
        trip(world, built, overrides, name)
        taken = run(built, tmp_path, safing)
        trip(world, built, overrides, name)
        refused = run(built, tmp_path, guarded)
    finally:
        built.close()
    assert "state=accepted" in taken and "INTERLOCK" not in taken, taken
    assert "refused: INTERLOCK TRIPPED" in refused and name.rpartition(".")[2] in refused, refused


def test_the_dwell_map_is_keyed_by_domain_qualified_threshold_id(world):
    """Two domains may each declare a bare id; their counts must never be one count."""
    keys = [interlock.key for interlock in plant.watched_interlocks(world)]
    assert len(keys) == len(set(keys))
    assert all("." in key for key in keys), keys
    values = plant.step(
        world, plant.initial_values(world), plant.tick_seconds(world), [], None, ledger=plant.Ledger()
    )
    assert set(values[plant.INTERLOCK_DWELL]) == set(keys)


def test_the_load_margin_is_bus_a_s_rated_generation_less_its_load(world):
    """ADR 0004 operator item 1: two 1,420 W modules on bus A (AOH p. 2.6-2; TN D-7609 p. 5), less
    the bus's load, and no longer the cells' output published under the margin's name."""
    values = plant.initial_values(world)
    load = values["bus_a_load_w"]
    assert plant.point_reading(world, "power.load_margin_w", values) == pytest.approx(2840.0 - load)
    assert plant.point_reading(world, "power.load_margin_w", values) != values.get("fuel_cell_power_w")


def test_the_amplifier_s_interlocks_are_all_evaluated_and_it_is_taken(world, tmp_path):
    built = executive(world, tmp_path)
    try:
        submit(tmp_path / "diode" / "alpha", ["set_power_amplifier state=on"])
        built.cycle()
        (body,) = bodies(tmp_path / "diode" / "alpha")
    finally:
        built.close()
    assert "state=accepted" in body and "evaluated and none tripped" in body, body


def test_one_unreadable_interlock_still_refuses_the_command_as_unevaluated(world, tmp_path):
    # `set_absorber_path` declares `co2_caution`, which reads, and `co2_absorber_low`, whose point is
    # read from no state the plant advances. No scenario: the quiet coast's verbs do not include it.
    built = console.Executive(world, tmp_path / "diode", phase="translunar_coast")
    built.attach("alpha")
    try:
        submit(tmp_path / "diode" / "alpha", ["set_absorber_path vehicle=csm path=secondary"])
        built.cycle()
        (body,) = bodies(tmp_path / "diode" / "alpha")
    finally:
        built.close()
    assert "refused: INTERLOCK UNEVALUATED" in body, body
    assert "declares 1 interlock(s) this executive cannot evaluate" in body, body
    assert "co2_absorber_low" in body, body
    # The readable one is evaluated, not listed as unevaluable.
    assert "co2_caution" not in body, body


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


# The same rule outside the episode (re-review A): every verb with a readable interlock names the
# direction it guards, so in the default world the recovery is taken while the guard is tripped.
DEFAULT_WORLD_SAFING = [
    (
        "cabin_pressure_emergency",
        {"csm_cabin_pressure_pa": 20000.0},  # 2.9 psia, past the 3.5 psia assert
        "set_cabin_regulator vehicle=csm mode=emergency",
        "set_cabin_regulator vehicle=csm mode=isolated",
    ),
    (
        "ppo2_fire_risk",
        {"csm_cabin_o2_kg": 3.5},  # about 341 mmHg, past the 300 mmHg assert
        "set_o2_flow vehicle=csm flow=off",
        "set_o2_flow vehicle=csm flow=high",
    ),
    (
        "cabin_pressure_high",
        {"csm_cabin_pressure_pa": 40000.0},  # 5.8 psia, past the 5.6 psia assert
        "set_o2_flow vehicle=csm flow=off",
        "set_o2_flow vehicle=csm flow=nominal",
    ),
    (
        "suit_loop_flow_low",
        {"suit_loop_flow_cfm": 0.0},
        "set_suit_fan vehicle=csm state=on",
        "set_suit_fan vehicle=csm state=off",
    ),
    # `set_o2_source` (ADR 0004, amended 2026-10-17): its guards name source and flow together.
    (
        "cabin_pressure_caution",
        {"csm_cabin_pressure_pa": 30000.0},  # 4.35 psia, past the 4.5 psia caution, above the emergency
        "set_o2_source vehicle=csm source=surge flow=high",
        "set_o2_source vehicle=csm source=primary flow=off",
    ),
    (
        "o2_reserve_10",
        {"o2_csm_kg": 20.0},  # past the 27.9 kg floor
        "set_o2_source vehicle=csm source=surge flow=nominal",
        "set_o2_source vehicle=csm source=primary flow=nominal",
    ),
    (
        "load_margin_negative",
        {"bus_a_load_w": 3000.0},  # above bus A's 2,840 W rated generation
        "set_battery_contactor battery=battery_csm_1 state=on",
        "set_battery_contactor battery=battery_csm_1 state=off",
    ),
    (
        "bus_a_undervoltage",
        {"bus_a_v": 20.0},
        "set_source source=fc_1 state=on",
        "set_source source=fc_1 state=off",
    ),
]


@pytest.mark.parametrize(("name", "overrides", "safing", "guarded"), DEFAULT_WORLD_SAFING)
def test_outside_a_scenario_the_safing_direction_is_taken_while_tripped(
    world, tmp_path, name, overrides, safing, guarded
):
    built = console.Executive(world, tmp_path / "diode", phase="translunar_coast")
    built.attach("alpha")
    try:
        trip(world, built, overrides, name)
        taken = run(built, tmp_path, safing)
        trip(world, built, overrides, name)
        refused = run(built, tmp_path, guarded)
    finally:
        built.close()
    assert "state=accepted" in taken and "INTERLOCK" not in taken, taken
    assert "refused: INTERLOCK TRIPPED" in refused and name in refused, refused


def test_every_readable_interlock_names_its_direction_or_is_whole_on_purpose(world):
    """A verb with a readable interlock declares `interlocks_when`, except the three ADR 0004 lists as
    guarded whole because no argument value is plainly the recovery."""
    whole = {"request_translation", "start_burn", "select_nav_source"}
    for verb, spec in world.verbs.items():
        readable = [
            name
            for name in (spec or {}).get("interlocks") or []
            if plant.resolve_interlock(world, str(name))[0] is not None
        ]
        if readable and verb not in whole:
            assert plant.interlock_conditions(spec), verb
    # An unconditional entry guards every command: the vent valve's hatch guard.
    vent = world.verbs["set_vent_valve"]
    for state in ("closed", "vent", "repress"):
        assert "structure.hatch_open_with_pressure" in plant.guarding_interlocks(vent, {"state": state})
    assert "cabin_pressure_emergency" not in plant.guarding_interlocks(vent, {"state": "repress"})


def test_a_guard_over_two_arguments_applies_to_the_combinations_it_names(world):
    """`set_o2_source` (ADR 0004 §Direction, amended 2026-10-17): the cabin caution guards cutting the
    cabin's oxygen, an isolated source or a flow of `off`; the reserve guards drawing on `primary`."""
    spec = world.verbs["set_o2_source"]

    def guards(source: str, flow: str) -> list[str]:
        return plant.guarding_interlocks(spec, {"vehicle": "csm", "source": source, "flow": flow})

    for flow in ("off", "low", "nominal", "high"):
        assert "eclss.cabin_pressure_caution" in guards("isolated", flow)
        assert "o2_reserve_10" not in guards("isolated", flow)
        assert "o2_reserve_10" not in guards("surge", flow)
    for source in ("primary", "surge"):
        assert "eclss.cabin_pressure_caution" in guards(source, "off")
        for flow in ("low", "nominal", "high"):
            assert "eclss.cabin_pressure_caution" not in guards(source, flow)
    assert guards("primary", "off") == ["eclss.cabin_pressure_caution"]
    assert guards("primary", "high") == ["o2_reserve_10"]
    # A leak on a low reserve: the surge tank is the one source both guards admit.
    assert guards("surge", "high") == []
