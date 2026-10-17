"""Crew rules (`domains/crew/rules.py`): where each person is, and the counts the cabins read.

The scripted cases run through the real step loop, so `ask_crew`'s write, the rule that decides
whether the person got there and the hold between commands are the plant's own. The table cases
call the rule with a configuration the mission reaches only by events, and hold the rule's tables
to the declarations they are derived from.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402

SEATS = {"commander": "csm_commander", "lm_pilot": "csm_lower_equipment_bay", "csm_pilot": "csm_navigator"}


@pytest.fixture(scope="module")
def world() -> plant.World:
    return plant.load_world(VEHICLE)


def state(world, sid):
    return next(s for s in world.states if s.id == sid)


def run(world, tmp_path, script, ticks, watch):
    """Run a scripted scenario and return, per tick, each watched state's value and the gaps."""
    document = {
        "scenario": "crew_fixture",
        "script": [{"tick": t, "verb": v, "arguments": a} for t, v, a in script],
    }
    path = tmp_path / "crew_fixture.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    scen = plant.load_scenario(world, path)
    trace: list[dict] = []

    def on_tick(tick, values, ledger, gaps):
        row = {sid: plant.state_level(values, state(world, sid)) for sid in watch}
        row["gaps"] = {g.state.id: f"{g.where}: {g.owed}" for g in gaps}
        trace.append(row)

    plant.run_scenario(world, scen, ticks, on_tick=on_tick)
    return trace


def rule(world, sid):
    return world.rules[sid].function


class Params(dict):
    """The rule's `params`, as the plant freezes them: lists become tuples."""

    def __init__(self, spec):
        super().__init__({k: plant._frozen(v) for k, v in spec.items()})

    def no_value(self, why):
        raise AssertionError(why)


def locate(world, configuration, sent):
    spec = state(world, "crew_location").spec
    return rule(world, "crew_location")({"configuration": configuration, "crew_destination": sent}, Params(spec), 0.02)


ASK = "ask_crew"


def ask(person, position):
    return {"crew_id": person, "position": position, "question": "what do you see?"}


def test_at_met_zero_everyone_is_in_their_own_csm_seat_and_the_csm_breathes_for_three(world, tmp_path):
    trace = run(world, tmp_path, [], 2, ["crew_location", "csm_crew_count", "lm_crew_count", "csm_water_draw_crew"])
    for row in trace:
        assert row["crew_location"] == SEATS
        assert (row["csm_crew_count"], row["lm_crew_count"], row["csm_water_draw_crew"]) == (3.0, 0.0, 3.0)
        for sid in ("crew_location", "csm_crew_count", "lm_crew_count", "csm_water_draw_crew"):
            assert sid not in row["gaps"]


def test_the_potable_tank_now_has_a_driver_and_the_crew_drink_from_it(world, tmp_path):
    """`E-CREW-WATER` read `crew_state`, a node of several states that publishes no value, so the
    tank was blocked on every tick. It reads `csm_water_draw_crew` now and the tank advances."""
    trace = run(world, tmp_path, [], 3, ["water_potable_kg"])
    assert all("water_potable_kg" not in row["gaps"] for row in trace)
    assert isinstance(trace[-1]["water_potable_kg"], float)


def test_asking_the_lm_pilot_at_the_tunnel_takes_them_off_the_bay_and_keeps_them_in_the_csm_count(world, tmp_path):
    """The relocation is the cost: the LM pilot in the tunnel can feel for a leak and cannot read the
    lower equipment bay's breakers, and stays there until asked somewhere else. The tunnel is
    counted with the CSM's cabin, so the CO2 driver does not move."""
    script = [(2, ASK, ask("lm_pilot", "tunnel")), (6, ASK, ask("lm_pilot", "csm_lower_equipment_bay"))]
    trace = run(world, tmp_path, script, 9, ["crew_location", "csm_crew_count"])
    assert trace[1]["crew_location"]["lm_pilot"] == "csm_lower_equipment_bay"
    assert trace[3]["crew_location"]["lm_pilot"] == "tunnel"
    assert trace[5]["crew_location"]["lm_pilot"] == "tunnel"
    assert trace[8]["crew_location"]["lm_pilot"] == "csm_lower_equipment_bay"
    assert {row["csm_crew_count"] for row in trace} == {3.0}


def test_sending_two_people_into_the_docked_lm_moves_two_out_of_the_csm_count(world, tmp_path):
    script = [(2, ASK, ask("commander", "lm_commander")), (2, ASK, ask("lm_pilot", "lm_pilot"))]
    trace = run(world, tmp_path, script, 5, ["crew_location", "csm_crew_count", "lm_crew_count"])
    assert trace[-1]["crew_location"] == {**SEATS, "commander": "lm_commander", "lm_pilot": "lm_pilot"}
    assert (trace[-1]["csm_crew_count"], trace[-1]["lm_crew_count"]) == (1.0, 2.0)


@pytest.mark.parametrize(
    ("configuration", "expected"),
    [
        ("docked", SEATS),
        ("undocked", {"commander": "lm_commander", "lm_pilot": "lm_pilot", "csm_pilot": "csm_navigator"}),
        ("separated", {"commander": "lm_commander", "lm_pilot": "lm_pilot", "csm_pilot": "csm_navigator"}),
        ("abandoned", SEATS),
    ],
)
def test_a_person_never_sent_anywhere_is_in_their_own_seat_in_the_vehicle_the_configuration_puts_them_in(
    world, configuration, expected
):
    assert locate(world, configuration, SEATS) == expected


def test_a_destination_the_configuration_takes_out_of_reach_returns_the_person_to_their_seat(world):
    """The LM pilot sent to the tunnel while docked is stranded by the undocking: the tunnel no longer
    exists, and the rule puts them in the LM, where the configuration says the surface party is."""
    sent = {**SEATS, "lm_pilot": "tunnel", "csm_pilot": "lm_commander"}
    assert locate(world, "docked", sent) == {**SEATS, "lm_pilot": "tunnel", "csm_pilot": "lm_commander"}
    undocked = locate(world, "undocked", sent)
    assert undocked["lm_pilot"] == "lm_pilot"
    assert undocked["csm_pilot"] == "csm_navigator"


def test_the_surface_is_reachable_only_from_an_lm_that_has_not_left_its_descent_stage(world):
    sent = {**SEATS, "commander": "surface_eva"}
    assert locate(world, "undocked", sent)["commander"] == "surface_eva"
    assert locate(world, "separated", sent)["commander"] == "lm_commander"
    assert locate(world, "docked", sent)["commander"] == "csm_commander"


def test_a_person_on_the_surface_breathes_neither_cabin(world):
    spec = state(world, "lm_crew_count").spec
    where = {"commander": "surface_eva", "lm_pilot": "lm_pilot", "csm_pilot": "csm_navigator"}
    assert rule(world, "lm_crew_count")({"crew_location": where}, Params(spec), 0.02) == 1.0
    spec = state(world, "csm_crew_count").spec
    assert rule(world, "csm_crew_count")({"crew_location": where}, Params(spec), 0.02) == 1.0


def test_the_rule_tables_are_the_declarations_they_are_derived_from(world):
    """`stations` is `mission.yaml#crew.positions[].stations` verbatim, every configuration value has
    a row, every person is in a vehicle where they have a seat, and the two cabin lists together are
    every station a person breathes cabin air at."""
    mission = yaml.safe_load((VEHICLE / "mission.yaml").read_text())
    spec = state(world, "crew_location").spec
    assert spec["stations"] == {p["id"]: p["stations"] for p in mission["crew"]["positions"]}
    unit = state(world, "configuration").spec["unit"]
    values = set(unit[len("enum[") : -1].split(","))
    assert set(spec["vehicle_by_configuration"]) == values == set(spec["reachable_by_configuration"])
    for row in spec["vehicle_by_configuration"].values():
        for person, vehicle in row.items():
            assert vehicle in spec["stations"][person]
    surface_party = {p["id"] for p in mission["crew"]["positions"] if p["goes_to_surface"]}
    for configuration in ("undocked", "separated"):
        row = spec["vehicle_by_configuration"][configuration]
        assert {p for p, v in row.items() if v == "lm"} == surface_party
    cabins = set(state(world, "csm_crew_count").spec["cabin_stations"]) | set(
        state(world, "lm_crew_count").spec["cabin_stations"]
    )
    location_unit = state(world, "crew_location").spec["unit"]
    every = set(location_unit[location_unit.index("enum[") + 5 : -2].split(","))
    assert every - cabins == {"surface_eva"}
