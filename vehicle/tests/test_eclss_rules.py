"""ECLSS's rules (D5, `domains/eclss/rules.py`), each against an independent analytic case.

Every expected figure is computed here from the published constant (the ECS study guide's 35 cfm
normal-space delivery, quoted in the state's `initial_provenance`) by a closed form rather than by
the rule's own step.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402

DT = 0.02
SUIT = next(
    s
    for s in yaml.safe_load((VEHICLE / "domains/eclss/components.yaml").read_text())["state"]
    if s["id"] == "suit_loop_flow_cfm"
)


@pytest.fixture(scope="module")
def world() -> plant.World:
    return plant.load_world(VEHICLE)


def walk(world, values, ticks):
    for _ in range(ticks):
        values = plant.step(world, values, DT, [], None, ledger=plant.Ledger())
    return values


def suit_flow(values):
    # Read as every reader does, by the state's own key first (`plant.state_level`): the sentinel's
    # sub-map entry is not what a frame publishes.
    return values["suit_loop_flow_cfm"]


def test_the_suit_loop_holds_the_published_delivery_while_its_compressor_runs(world):
    assert "35 cubic feet per minute" in SUIT["initial_provenance"]["source"]
    values = walk(world, plant.initial_values(world), 50)
    assert suit_flow(values) == pytest.approx(35.0)


def test_the_suit_loop_spins_down_with_its_time_constant_when_the_compressor_load_is_off(world):
    values = plant.initial_values(world)
    enabled = dict(values["load_enabled"])
    assert enabled[SUIT["compressor_load"]] == "on"
    enabled[SUIT["compressor_load"]] = "off"
    values = {**values, "load_enabled": enabled}
    ticks = 250  # 5 s, one time constant
    after = walk(world, values, ticks)
    expected = 35.0 * math.exp(-ticks * DT / SUIT["tau_s"])
    assert suit_flow(after) == pytest.approx(expected, rel=1e-6)
    # And it spins back up once the load is on again.
    enabled[SUIT["compressor_load"]] = "on"
    back = walk(world, {**after, "load_enabled": dict(enabled)}, ticks)
    recovered = 35.0 - (35.0 - expected) * math.exp(-ticks * DT / SUIT["tau_s"])
    assert suit_flow(back) == pytest.approx(recovered, rel=1e-6)


def test_the_suit_loop_advances_on_a_real_tick(world):
    gaps: list[plant.Gap] = []
    plant.step(world, plant.initial_values(world), DT, gaps)
    assert "suit_loop_flow_cfm" not in {gap.state.id for gap in gaps}


def test_set_suit_fan_off_stops_the_circuit_with_its_load_still_powered(world):
    """`set_suit_fan` used to move nothing: the verb was accepted and the circuit kept flowing."""
    values = plant.initial_values(world)
    assert values["suit_fan"] == {"csm": "on", "lm": "off"}
    assert values["load_enabled"][SUIT["compressor_load"]] == "on"
    staged = plant.apply_command(world, values, "set_suit_fan", {"vehicle": "csm", "state": "off"})
    values = {**values, **staged}
    ticks = 250
    after = walk(world, values, ticks)
    assert after["load_enabled"][SUIT["compressor_load"]] == "on"
    assert suit_flow(after) == pytest.approx(35.0 * math.exp(-ticks * DT / SUIT["tau_s"]), rel=1e-6)


# --------------------------------------------------------------------------------------------
# The oxygen supply tanks: the AOH's heater relay and its repressurization table (SM2A-03-BLOCK
# II-(1) pp. 2.6-12/13), quoted in the two states' own provenance.
# --------------------------------------------------------------------------------------------

STATES = {
    s["id"]: s
    for s in yaml.safe_load((VEHICLE / "domains/eclss/components.yaml").read_text())["state"]
}
TANK = STATES["o2_supply_pressure_psi"]
HEATERS = STATES["o2_tank_heaters"]



def rules_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "eclss_rules", VEHICLE / "domains/eclss/rules.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("quantity, minutes", [(100, 4.0), (50, 10.8), (30, 13.0), (5, 24.0)])
def test_a_stroke_at_the_tables_flow_takes_the_tables_time(quantity, minutes):
    # 70 psi, 865 to 935 psia, with heaters and fans on and 1 lb/h drawn from the tank.
    assert "595.87 Btu/hour" in TANK["provenance"]["source"]
    rate = rules_module().tank_pressure_rate_psi_h(True, quantity, 1.0, TANK)
    assert 70.0 / rate * 60.0 == pytest.approx(minutes)


@pytest.mark.parametrize("quantity, m_max", [(100, 3.56), (35, 17.56), (10, 8.76)])
def test_at_the_tables_maximum_flow_the_heaters_just_hold_pressure(quantity, m_max):
    assert rules_module().tank_pressure_rate_psi_h(True, quantity, m_max, TANK) == pytest.approx(
        0.0, abs=1e-9
    )


def test_heaters_off_the_leak_alone_cannot_hold_a_full_tank_and_nearly_holds_a_third():
    # The AOH's minimum dq/dm region (p. 2.6-12): "the heat leak of the tank is sufficient to
    # maintain design pressures" there, and nowhere near it at a full tank.
    rate = rules_module().tank_pressure_rate_psi_h
    full, region = rate(False, 100, 1.0, TANK), rate(False, 30, 1.0, TANK)
    assert full < -300.0  # psi per hour
    assert -10.0 < region < 0.0


@pytest.mark.parametrize(
    "pressure, before, after",
    [(864.0, "off", "on"), (865.0, "off", "on"), (900.0, "on", "on"), (900.0, "off", "off"),
     (935.0, "on", "off"), (940.0, "on", "off")],
)
def test_the_pressure_switch_closes_at_865_opens_at_935_and_holds_between(pressure, before, after):
    assert "865 psia" in HEATERS["provenance"]["source"]
    inputs = {"o2_supply_pressure_psi": pressure, "o2_tank_heaters": before}
    assert rules_module()._tank_heaters(inputs, HEATERS, DT) == after


def test_the_tank_pressure_moves_on_a_real_tick_at_the_rate_the_table_gives(world):
    values = plant.initial_values(world)
    assert values["o2_tank_heaters"] == "off"
    after = walk(world, values, 50)  # one second
    per_tank_lb_h = (
        (values["fc_o2_draw_kg_s"] + values["cabin_o2_supply_csm_kg_s"])
        * 3600.0
        / TANK["kg_per_lb"]
        / TANK["tanks"]
    )
    quantity = 100.0 * values["o2_csm_kg"] / TANK["tanks"] / (TANK["full_lb_per_tank"] * TANK["kg_per_lb"])
    expected = rules_module().tank_pressure_rate_psi_h(False, quantity, per_tank_lb_h, TANK) / 3600.0
    assert after["o2_supply_pressure_psi"] - 900.0 == pytest.approx(expected, rel=1e-3)
    assert after["o2_tank_heaters"] == "off"


# --------------------------------------------------------------------------------------------
# The CM's surge tank (AOH ECS p. 2.7-7): `set_o2_source` moves the regulator's draw between the
# S/M supply and the surge tank, and `isolated` or a closed regulator stops it.
# --------------------------------------------------------------------------------------------

SUPPLY = STATES["cabin_o2_supply_csm_kg_s"]
SURGE = STATES["o2_surge_csm_kg"]


def test_the_surge_tank_starts_full_and_the_cabin_draws_on_the_service_module(world):
    assert "3.7 pounds" in SURGE["initial_provenance"]["source"]
    assert SURGE["initial"] == pytest.approx(3.7 * 0.45359237, rel=1e-6)
    values = plant.initial_values(world)
    assert values["o2_source"] == {"csm": "primary", "lm": "primary"}
    after = walk(world, values, 50)
    assert after["cabin_o2_supply_csm_kg_s"] == pytest.approx(SUPPLY["nominal_kg_s"])
    assert after["cabin_o2_surge_supply_csm_kg_s"] == 0.0
    assert after["o2_surge_csm_kg"] == pytest.approx(SURGE["initial"])


def test_set_o2_source_surge_moves_the_draw_to_the_surge_tank(world):
    values = walk(world, plant.initial_values(world), 1)
    staged = plant.apply_command(
        world, values, "set_o2_source", {"vehicle": "csm", "source": "surge", "flow": "nominal"}
    )
    values = walk(world, {**values, **staged}, 2)  # the regulator acts on the next tick's selection
    sm_before = values["o2_csm_kg"]
    ticks = 500  # 10 s
    after = walk(world, values, ticks)
    assert after["cabin_o2_supply_csm_kg_s"] == 0.0
    assert after["cabin_o2_surge_supply_csm_kg_s"] == pytest.approx(SUPPLY["nominal_kg_s"])
    drawn = values["o2_surge_csm_kg"] - after["o2_surge_csm_kg"]
    assert drawn == pytest.approx(SUPPLY["nominal_kg_s"] * ticks * DT, rel=1e-2)
    # The S/M tanks now feed only the fuel cells.
    assert sm_before - after["o2_csm_kg"] == pytest.approx(
        values["fc_o2_draw_kg_s"] * ticks * DT, rel=1e-2
    )


@pytest.mark.parametrize("source, regulator", [("isolated", "primary"), ("primary", "closed")])
def test_an_isolated_source_or_a_closed_regulator_admits_nothing(world, source, regulator):
    values = plant.initial_values(world)
    values = {
        **values,
        "o2_source": {"csm": source, "lm": "primary"},
        "cabin_regulator_position": regulator,
    }
    after = walk(world, values, 5)
    assert after["cabin_o2_supply_csm_kg_s"] == 0.0
    assert after["cabin_o2_surge_supply_csm_kg_s"] == 0.0


def test_an_empty_surge_tank_stops_the_flow_rather_than_filling_the_cabin_from_nothing():
    rule = rules_module().RULES["cabin_o2_surge_supply_csm_kg_s"]

    class Params(dict):
        def no_value(self, why):
            raise AssertionError(why)

    params = Params(STATES["cabin_o2_surge_supply_csm_kg_s"])
    inputs = {
        "o2_source": {"csm": "surge", "lm": "primary"},
        "cabin_regulator_position": "primary",
        "o2_surge_csm_kg": 0.0,
    }
    assert rule(inputs, params, DT) == 0.0
    inputs["o2_surge_csm_kg"] = 1.0e-7
    assert rule(inputs, params, DT) == pytest.approx(1.0e-7 / DT)
    inputs["o2_surge_csm_kg"] = 1.0
    assert rule(inputs, params, DT) == pytest.approx(params["nominal_kg_s"])
