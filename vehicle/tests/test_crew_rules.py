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
        # Three people at work: the water draw is three at the waking weight, between meals.
        assert (row["csm_crew_count"], row["lm_crew_count"]) == (3.0, 0.0)
        assert row["csm_water_draw_crew"] == pytest.approx(3 * 0.9863)
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


# --------------------------------------------------------------------------------------------------
# The crew day: the Apollo 11 flight plan, a question at night, and what the cabins and the tank read.
# --------------------------------------------------------------------------------------------------

PEOPLE = ("commander", "csm_pilot", "lm_pilot")


def params(world, sid):
    return Params(state(world, sid).spec)


def walk(world, hours, step_s=60.0, questions=(), location=SEATS):
    rules = {sid: rule(world, sid) for sid in world.rules if state(world, sid).domain == "crew"}
    values = {
        "crew_clock_us": 0,
        "crew_scheduled": {"previous": "work", "now": "work"},
        "crew_roused": dict.fromkeys(PEOPLE, False),
        "crew_rest_owed_s": dict.fromkeys(PEOPLE, 0.0),
        "crew_activity": dict.fromkeys(PEOPLE, "work"),
        "crew_availability": dict.fromkeys(PEOPLE, "available"),
        "crew_location": dict(location),
    }
    pending = sorted(questions, key=lambda q: q[1])
    rows = []
    for _ in range(int(hours * 3600 / step_s)):
        met_h = values["crew_clock_us"] / 3.6e9
        while pending and pending[0][1] <= met_h:
            values["crew_roused"] = {**values["crew_roused"], pending.pop(0)[0]: True}
        for sid in ("crew_clock_us", "crew_scheduled", "crew_rest_owed_s", "crew_activity", "crew_availability"):
            values[sid] = rules[sid](values, params(world, sid), step_s)
        values["crew_roused"] = rules["crew_roused"](values, params(world, "crew_roused"), step_s)
        draw = rules["csm_water_draw_crew"](values, params(world, "csm_water_draw_crew"), step_s)
        metabolic = rules["csm_metabolic_crew"](values, params(world, "csm_metabolic_crew"), step_s)
        rows.append(
            (values["crew_clock_us"] / 3.6e9, dict(values["crew_activity"]), dict(values["crew_availability"]),
             dict(values["crew_rest_owed_s"]), draw, metabolic)
        )
    return rows


def met(world, anchor, get_h):
    return get_h - state(world, "crew_scheduled").spec["anchors_get_h"][anchor]


def test_the_flight_plan_rows_sit_inside_the_phase_they_are_anchored_to_and_never_overlap(world):
    mission = yaml.safe_load((VEHICLE / "mission.yaml").read_text())
    phases = {p["id"]: (p["starts_at_h"], p["starts_at_h"] + p["duration_h"]) for p in mission["phases"]}
    spans = []
    for row in state(world, "crew_scheduled").spec["flight_plan"]:
        start, end = (met(world, row["anchor"], g) for g in row["get_h"])
        low, high = phases[row["anchor"]]
        assert low <= start < end <= high, row
        if row["activity"] == "meal":
            assert end - start == pytest.approx(1.0), "FP11 p1-13: eat periods are 1 hour"
        spans.append((start, end))
    spans.sort()
    for (_, end), (start, _) in zip(spans, spans[1:], strict=False):
        assert end <= start + 1e-9


def test_the_anchors_put_each_apollo_11_event_at_this_missions_start_of_its_phase(world):
    """GET 4:17 ejection, GET 75:49:50 LOI-1 and GET 135:23:42 TEI (MR11), at MET 0, 73 and 132.5."""
    anchors = state(world, "crew_scheduled").spec["anchors_get_h"]
    mission = yaml.safe_load((VEHICLE / "mission.yaml").read_text())
    starts = {p["id"]: p["starts_at_h"] for p in mission["phases"]}
    for phase, get_h in {"translunar_coast": 4 + 17 / 60, "lunar_orbit": 75 + 49 / 60 + 50 / 3600,
                         "transearth_coast": 135 + 23 / 60 + 42 / 3600}.items():
        assert anchors[phase] == pytest.approx(get_h - starts[phase], abs=1e-4)


def test_the_water_weights_put_half_a_day_of_water_in_the_three_meal_hours(world):
    """Re-derived from the translunar rows: three one-hour meals carry half of 24 crew-hours of
    draw, and the waking hours outside them carry the other half."""
    spec = state(world, "csm_water_draw_crew").spec
    rows = [r for r in state(world, "crew_scheduled").spec["flight_plan"] if r["anchor"] == "translunar_coast"]
    rest = sum(r["get_h"][1] - r["get_h"][0] for r in rows if r["activity"] == "sleep") / 3
    assert spec["draw_weight"]["meal"] == pytest.approx(0.5 * 24 / 3)
    assert spec["draw_weight"]["work"] == pytest.approx(0.5 * 24 / (24 - 3 - rest), abs=5e-5)
    assert spec["draw_weight"]["sleep"] == 0.0
    lm = state(world, "lm_metabolic_crew").spec["metabolic_factor"]
    assert lm == state(world, "csm_metabolic_crew").spec["metabolic_factor"]


def test_the_first_crew_day_eats_at_the_flight_plans_hours_and_sleeps_through_the_first_rest_period(world):
    rows = walk(world, 18.5)
    def at(h):
        return min(rows, key=lambda r: abs(r[0] - h))
    first_meal = met(world, "translunar_coast", 8.0)
    first_rest = met(world, "translunar_coast", 18.0)
    assert set(at(first_meal)[1].values()) == {"meal"}
    assert set(at(first_rest)[1].values()) == {"sleep"}
    assert set(at(first_rest)[2].values()) == {"resting"}
    assert set(at(first_meal + 2)[1].values()) == {"work"}
    # Three people, so the tank's driver is 12 crew-equivalents at a meal, 2.96 at work, none asleep,
    # and the cabin breathes at 0.7 of awake while they sleep.
    assert at(first_meal)[4] == pytest.approx(12.0)
    assert at(first_rest)[4] == 0.0
    assert at(first_rest)[5] == pytest.approx(2.1)
    assert at(first_meal + 2)[5] == pytest.approx(3.0)


def test_waking_the_commander_at_night_costs_the_morning(world):
    """Asked four hours into the first rest period, the commander is awake for the rest of it and the
    others sleep on. The rest lost is owed, so when the period ends the commander sleeps on while the
    others start the day, and does not answer until it is repaid."""
    start = met(world, "translunar_coast", 13.5)
    end = met(world, "translunar_coast", 22.0)
    asked = start + 4.0
    rows = walk(world, end + 6.0, questions=[("commander", asked)])
    def at(h):
        return min(rows, key=lambda r: abs(r[0] - h))
    awake = at(asked + 1.0)
    assert awake[1] == {"commander": "work", "csm_pilot": "sleep", "lm_pilot": "sleep"}
    assert awake[2]["commander"] == "available"
    owed_at_end = at(end - 0.01)[3]["commander"]
    assert owed_at_end == pytest.approx((end - asked) * 3600, abs=180)
    morning = at(end + 1.0)
    assert morning[1]["commander"] == "sleep" and morning[2]["commander"] == "resting"
    assert morning[1]["csm_pilot"] != "sleep"
    repaid = at(end + (end - asked) + 0.2)
    assert repaid[3]["commander"] == 0.0 and repaid[1]["commander"] != "sleep"


def test_a_question_by_day_changes_nothing_and_is_forgotten_when_the_rest_period_begins(world):
    start = met(world, "translunar_coast", 13.5)
    rows = walk(world, start + 1.0, questions=[("lm_pilot", 2.0)])
    def at(h):
        return min(rows, key=lambda r: abs(r[0] - h))
    assert at(2.5)[1]["lm_pilot"] == "work"
    assert at(start + 0.5)[1]["lm_pilot"] == "sleep"
    assert all(r[3]["lm_pilot"] == 0.0 for r in rows)


def test_a_person_on_the_surface_is_on_suit_and_an_incapacitated_one_stays_so(world):
    spec = params(world, "crew_availability")
    out = rule(world, "crew_availability")(
        {
            "crew_activity": dict.fromkeys(PEOPLE, "work"),
            "crew_location": {"commander": "surface_eva", "lm_pilot": "lm_pilot", "csm_pilot": "csm_navigator"},
            "crew_availability": {"commander": "available", "lm_pilot": "incapacitated", "csm_pilot": "available"},
        },
        spec,
        0.02,
    )
    assert out == {"commander": "suit", "lm_pilot": "incapacitated", "csm_pilot": "available"}
