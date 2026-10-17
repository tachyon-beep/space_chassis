"""The environment split (ADR 0003 item 9, John 2026-10-15: "Hold in episode only").

The sun-on-radiator hot hold, `environment_heat_w` = 2,477 W, applies only inside the quiet-coast
episode (`scenarios/quiet_coast.yaml`). The default vehicle starts in rotating flight (passive
thermal control) at an absorbed load chosen so that its MET-0 operating point is an equilibrium with
the radiator alone carrying the loop, and the radiator's outlet inside Apollo's 5-15 C band.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402

SCENARIO = VEHICLE / "scenarios" / "quiet_coast.yaml"
THERMAL = yaml.safe_load((VEHICLE / "domains" / "thermal" / "components.yaml").read_text())
STATES = {row["id"]: row for row in THERMAL["state"]}
ENV = THERMAL["radiator_model"]["environment"]
VEHICLE_DOC = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
LOOP = next(x for x in VEHICLE_DOC["thermal"]["loops"] if x["id"] == "loop_primary")
RADIATOR = STATES["radiator_eq_t"]
EPS_SIGMA_A = RADIATOR["emissivity"] * RADIATOR["stefan_boltzmann"] * RADIATOR["area_effective_m2"]
CAPACITY = RADIATOR["rated_flow_kg_s"] * RADIATOR["specific_heat_j_per_kg_k"]
SUPPLY_K = LOOP["supply_c"] + 273.15
OUTLET_BAND_C = LOOP["radiator_outlet_c"]
DT = 0.02


@pytest.fixture(scope="module")
def world() -> plant.World:
    return plant.load_world(VEHICLE)


@pytest.fixture(scope="module")
def scenario(world) -> plant.Scenario:
    return plant.load_scenario(world, SCENARIO)


def run(world, values, ticks):
    for _ in range(ticks):
        ledger = plant.Ledger()
        gaps: list[plant.Gap] = []
        values = plant.step(world, values, DT, gaps, ledger=ledger)
        plant.assert_conservation(ledger)
        assert "environment_heat_w" not in {gap.state.id for gap in gaps}
    return values


def outlet_c(world, values) -> float:
    frame = plant.emit_frame(
        world,
        tick=0,
        seq=0,
        boot_id="0" * 32,
        met_s=0.0,
        sensor_time_s=0.0,
        values=values,
        quality={},
        phase="translunar_coast",
        vehicle="csm",
        state_revision=0,
    )["values"]
    return float(frame["thermal.coolant_return_c"])


def test_the_scenario_s_hold_is_the_vehicle_s_own_derived_hot_hold():
    """The episode's 2,477.02 W is the derivation the linter evaluates (`sun_hold_w`), not a copy."""
    held = yaml.safe_load(SCENARIO.read_text())["initial"]["environment_heat_w"]
    product = ENV["solar_flux_w_m2"] * ENV["absorptivity"] * ENV["projected_area_m2"]
    assert held == pytest.approx(product, abs=1e-9)
    assert STATES["environment_heat_w"]["sun_hold_w"] == pytest.approx(held, abs=0.05)
    assert STATES["environment_heat_w"]["provenance"]["computes"] == "sun_hold_w"


def test_the_scenario_overlay_produces_the_hot_hold_and_the_default_does_not(world, scenario):
    episode = plant.initial_values(world, scenario)
    default = plant.initial_values(world)
    assert episode["environment_heat_w"] == pytest.approx(2477.02)
    assert default["environment_heat_w"] == pytest.approx(1285.5)
    assert episode["zone_radiator_t"] == 293.40 and default["zone_radiator_t"] == 288.02

    # A boundary is *held*: a minute of ticks moves neither, and the plant never re-derives the
    # default over the scenario's value.
    episode = run(world, episode, 3000)
    default = run(world, default, 3000)
    assert episode["environment_heat_w"] == pytest.approx(2477.02, abs=1e-12)
    assert default["environment_heat_w"] == pytest.approx(1285.5, abs=1e-12)
    # And the hold is what the episode's radiator rejects against: under it the evaporator works.
    assert episode["evaporator_duty_w"] > 900.0
    assert default["evaporator_duty_w"] == 0.0


def test_the_passive_thermal_control_load_is_the_met0_equilibrium_it_says_it_is():
    """`environment_heat_w.initial`'s stated derivation, by hand: the radiator alone carries the
    MET-0 collected load with the loop at its supply, so its outlet is the supply."""
    load_w = 1401.0
    inlet_k = SUPPLY_K + load_w / CAPACITY
    panel_k = SUPPLY_K + load_w / (2 * CAPACITY)
    absorbed = EPS_SIGMA_A * panel_k**4 - load_w
    assert STATES["environment_heat_w"]["initial"] == pytest.approx(absorbed, abs=0.05)
    assert STATES["zone_radiator_t"]["initial"] == pytest.approx(panel_k, abs=0.01)
    assert STATES["evaporator_duty_w"]["initial"] == 0.0
    # The evaporator's inlet (the radiator's outlet) is below its actuation, so it stays off.
    assert inlet_k - load_w / CAPACITY < STATES["evaporator_duty_w"]["actuation_k"]
    provenance = STATES["environment_heat_w"]["initial_provenance"]
    assert provenance["basis"] == "chosen"
    assert "Hold in episode only" in provenance["reason"]
    assert "SP-368 p.525" in provenance["reason"]


def test_the_default_met0_radiator_outlet_sits_inside_apollo_s_band(world, scenario):
    """The reason for the split: under the hot hold at MET 0 the outlet is 18.0 C, outside
    `radiator_outlet_c` [5, 15]; in passive thermal control it is inside, and under 283 K."""
    low, high = OUTLET_BAND_C
    default = plant.initial_values(world)
    for values in (default, run(world, default, 3000)):
        reading = outlet_c(world, values)
        assert low <= reading <= high, reading
        assert reading + 273.15 <= 283.0
    assert outlet_c(world, plant.initial_values(world, scenario)) > high
