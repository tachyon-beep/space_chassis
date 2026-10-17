"""The quiet-coast power rules (`domains/power/rules.py`), each against an independent oracle.

`docs/vehicle-completion/09-quiet-coast-episode.md` §7 steps 2 and 6, and ADR 0003 items 1-3. The
oracles are written out by hand here rather than read from the rules: the per-module terminal line
`V = E0 - R i` (WP02 E-2, `docs/evidence/wp02-electrical.md`), the J-mission EPS handout's
per-ampere reactant table (p. 2.6-21), and the load inventory's own `demand_w`.

The bus-A load reads `comms.transmitter_on`, which the comms rules declare. Where the definition
under test does not declare it yet, `definition()` plants it on `link` exactly as comms declares it
(initial `off`), so these tests run before and after the two branches meet.
"""

from __future__ import annotations

import importlib.util
import itertools
import math
import shutil
import sys
from pathlib import Path

import pytest
import yaml

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402

DT = 0.02
LB = 0.45359237
_COUNTER = itertools.count()

# Every fuel-cell module connected, as at MET 0 (`source_enabled`).
ALL_ON = {"fc_1": "on", "fc_2": "on", "fc_3": "on"}
# ... and every module at its published resistance (WP02 E-2).
HEALTHY = {f"fc_{n}_resistance_ohm": 0.1008 for n in (1, 2, 3)}

# The published per-module terminal line (WP02 E-2) and its envelope, written out by hand.
E0 = 32.30
R = 0.1008

TRANSMITTER_ON = """  - id: transmitter_on
    node: link
    method: discrete
    unit: "enum[on,off]"
    initial: "off"
    initial_provenance: {basis: chosen, reason: "test fixture standing in for comms' declaration"}
    moved_by: ["command:set_power_amplifier"]
    provenance: {basis: chosen, reason: "test fixture standing in for comms' declaration"}
"""


def definition(tmp_path: Path, *, drop_edge: str | None = None) -> Path:
    """A writable copy of the vehicle, with `comms.transmitter_on` planted if it is not declared, and
    optionally one coupling edge removed."""
    root = tmp_path / f"power{next(_COUNTER)}"
    root.mkdir()
    for name in plant.CORPUS_TOP_LEVEL:
        shutil.copy(VEHICLE / name, root / name)
    shutil.copytree(VEHICLE / "domains", root / "domains")
    comms = root / "domains" / "comms" / "components.yaml"
    text = comms.read_text()
    if "  - id: transmitter_on\n" not in text:
        assert text.count("\nstate:\n") == 1
        comms.write_text(text.replace("\nstate:\n", "\nstate:\n" + TRANSMITTER_ON, 1))
        coupling = root / "coupling.yaml"
        ctext = coupling.read_text()
        old = "    state_order: [tx_power, link_snr]\n"
        assert ctext.count(old) == 1
        coupling.write_text(
            ctext.replace(old, "    state_order: [transmitter_on, tx_power, link_snr]\n")
        )
    if drop_edge is not None:
        coupling = root / "coupling.yaml"
        ctext = coupling.read_text()
        start = ctext.index(f"  - id: {drop_edge}\n")
        end = ctext.index("\n  - id: ", start + 1) + 1
        coupling.write_text(ctext[:start] + ctext[end:])
    return root


@pytest.fixture(scope="module")
def world(tmp_path_factory) -> plant.World:
    return plant.load_world(definition(tmp_path_factory.mktemp("power")))


def rules_module():
    spec = importlib.util.spec_from_file_location(
        "power_rules_under_test", VEHICLE / "domains" / "power" / "rules.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def spec_of(world: plant.World, state_id: str) -> dict:
    return next(s.spec for s in world.states if s.id == state_id)


def tick(world, values, effects=None, ledger=None):
    gaps: list[plant.Gap] = []
    after = plant.step(world, values, DT, gaps, effects or [], ledger=ledger)
    return after, {gap.state.id: gap for gap in gaps}


def power_yaml() -> dict:
    return yaml.safe_load((VEHICLE / "domains" / "power" / "components.yaml").read_text())


# ------------------------------------------------------------------------------------------------
# The rules' parameters are copies; these hold them to the declarations they copy.
# ------------------------------------------------------------------------------------------------


def test_the_rule_parameters_are_the_inventory_and_the_cells_they_copy():
    doc = power_yaml()
    states = {s["id"]: s for s in doc["state"]}
    cells = {c["id"]: c for c in doc["components"] if c.get("class") == "source"}
    for sid in ("bus_a_v", "bus_b_v", "fuel_cell_current_a", "fc_1_current_a"):
        assert states[sid]["resistance_of"] == {c: f"{c}_resistance_ohm" for c in cells}, sid
        for cell in cells.values():
            assert states[sid]["cell_open_circuit_v"] == cell["open_circuit_intercept_v"]
            low_w, high_w = cell["normal_power_w"]
            high_v, low_v = cell["terminal_v_at_normal_power"]
            assert states[sid]["cell_current_envelope_a"] == [
                round(low_w / high_v, 3),
                round(high_w / low_v, 3),
            ]
    # The modules that can feed a bus are the cells whose `normal_bus` it is, in every copy.
    feeding = {"csm_bus_a": [], "csm_bus_b": []}
    for cid, cell in cells.items():
        feeding[cell["normal_bus"]].append(cid)
    assert feeding == {"csm_bus_a": ["fc_1", "fc_2"], "csm_bus_b": ["fc_3"]}
    assert states["bus_a_v"]["cells"] == states["bus_a_load_w"]["cells"] == feeding["csm_bus_a"]
    assert states["bus_b_v"]["cells"] == states["bus_b_load_w"]["cells"] == feeding["csm_bus_b"]
    assert states["bus_a_rated_w"]["cells"] == feeding["csm_bus_a"]
    assert states["bus_a_rated_w"]["rated_w"] == {
        c: cells[c]["rated_w"] for c in feeding["csm_bus_a"]
    }
    for sid in ("fuel_cell_current_a", "fc_1_current_a"):
        assert {b["bus"]: b["cells"] for b in states[sid]["buses"]} == feeding, sid
        assert [b["load"] for b in states[sid]["buses"]] == ["bus_a_load_w", "bus_b_load_w"], sid
    # Every module starts at its published resistance, and the margin's nominal is that resistance.
    for cid, cell in cells.items():
        assert states[f"{cid}_resistance_ohm"]["initial"] == cell["source_resistance_ohm"]
        assert states["bus_a_rated_w"]["cell_resistance_ohm"] == cell["source_resistance_ohm"]
    assert states["bus_a_rated_w"]["resistance_of"] == {
        c: f"{c}_resistance_ohm" for c in feeding["csm_bus_a"]
    }
    assert (
        states["fc_1_current_a"]["cell_current_envelope_a"]
        == states["bus_a_v"]["cell_current_envelope_a"]
    )
    # `source_enabled` is the whole of `set_source`'s argument space, every source in it a component.
    commands = yaml.safe_load((VEHICLE / "domains" / "power" / "commands.yaml").read_text())
    verb = next(c for c in commands["commands"] if c["verb"] == "set_source")
    initial = states["source_enabled"]["initial"]
    assert list(initial) == verb["argument_schema"]["source"]["values"]
    assert {k for k, v in initial.items() if v == "on"} == set(cells)
    # Each bus load lists exactly the CSM loads `loads[].bus` puts on it, at their `demand_w`.
    for sid, bus in (("bus_a_load_w", "csm_bus_a"), ("bus_b_load_w", "csm_bus_b")):
        on_bus = {row["id"]: row["demand_w"] for row in doc["loads"] if row["bus"] == bus}
        assert states[sid]["loads_w"] == on_bus, sid
    # Together they are the whole CSM inventory, and the reference fields are its split.
    a, b = states["bus_a_load_w"], states["bus_b_load_w"]
    assert a["bus_a_load_w"] == sum(a["loads_w"].values()) == 1148
    assert b["bus_b_load_w"] == sum(b["loads_w"].values()) == 575
    assert a["bus_a_load_w"] + b["bus_b_load_w"] == doc["load_budget"]["csm_total_demand_w"]
    # ADR 0003 item 2: about two thirds of the load on the two-cell bus.
    assert 0.6 < a["bus_a_load_w"] / doc["load_budget"]["csm_total_demand_w"] < 0.7


def test_every_load_has_a_met_zero_position_and_the_csm_ones_are_the_configured_total():
    doc = power_yaml()
    initial = next(s for s in doc["state"] if s["id"] == "load_enabled")["initial"]
    assert set(initial) == {row["id"] for row in doc["loads"]}
    on = [row for row in doc["loads"] if initial[row["id"]] == "on"]
    assert {row["vehicle"] for row in on} == {"csm"}
    # Every CSM load but the standby glycol pump, which thermal's `coolant_pump` holds off
    # (TN D-6718 p. 11: the loop runs on one pump).
    csm = {row["id"] for row in doc["loads"] if row["vehicle"] == "csm"}
    assert csm - {row["id"] for row in on} == {"csm_coolant_pump_2"}
    thermal = yaml.safe_load((VEHICLE / "domains" / "thermal" / "components.yaml").read_text())
    pumps = next(s for s in thermal["state"] if s["id"] == "coolant_pump")["initial"]
    assert pumps["pump_1"] == "on" and pumps["pump_2"] == "off"
    assert sum(row["demand_w"] for row in on) == 1723 - 250 == 1473
    # Below TN D-7609 p. 2's 60-80 A coast band at the 28 V nominal: 52.6 A. The inventory is short
    # of Apollo's coast load, and the switch map does not hide it.
    assert 1473 / 28 < 60


# ------------------------------------------------------------------------------------------------
# Bus voltage: V = E0 - R I per module, at two currents, computed by hand.
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("module_current_a", [20.0, 45.0])
def test_bus_b_voltage_is_the_cells_terminal_line_at_two_currents(world, module_current_a):
    """One module on bus B. Pick the current, compute V and the load P = V I by hand, hand the rule
    P, and it must give back V (and the current)."""
    v_hand = E0 - R * module_current_a  # 30.284 V at 20 A, 27.764 V at 45 A
    p_hand = v_hand * module_current_a
    rules = rules_module()
    spec = spec_of(world, "bus_b_v")
    assert rules.bus_b_v(
        {"bus_b_load_w": p_hand, "source_enabled": ALL_ON, **HEALTHY}, spec, DT
    ) == (pytest.approx(v_hand, abs=1e-9))
    current, volts = rules.solve_bus(p_hand, 1, E0, R, [12.903, 52.593])
    assert (current, volts) == pytest.approx((module_current_a, v_hand), abs=1e-9)


@pytest.mark.parametrize("bus_current_a", [30.0, 80.0])
def test_bus_a_voltage_is_two_cells_in_parallel_at_two_currents(world, bus_current_a):
    """Two modules on bus A share the current: each carries I/2, so V = E0 - R (I/2)."""
    v_hand = E0 - R * (bus_current_a / 2)  # 30.788 V at 30 A, 28.268 V at 80 A
    p_hand = v_hand * bus_current_a
    rules = rules_module()
    inputs = {"bus_a_load_w": p_hand, "source_enabled": ALL_ON, **HEALTHY}
    assert rules.bus_a_v(inputs, spec_of(world, "bus_a_v"), DT) == (pytest.approx(v_hand, abs=1e-9))


def test_the_solve_refuses_a_load_the_cells_cannot_deliver_or_an_extrapolation():
    rules = rules_module()
    envelope = [12.903, 52.593]
    # Beyond the maximum-power point E0^2 / 4R there is no operating point at all.
    assert rules.solve_bus(E0**2 / (4 * R) + 1.0, 1, E0, R, envelope) is None
    # Below 12.9 A per module, or above 52.6 A, the secant is an extrapolation.
    assert rules.solve_bus(200.0, 1, E0, R, envelope) is None
    assert rules.solve_bus(1600.0, 1, E0, R, envelope) is None
    assert rules.solve_bus(1600.0, 2, E0, R, envelope) is not None


def test_a_bus_below_the_module_minimum_is_a_named_gap_not_a_bare_none(world):
    """Under 400 W a module (AOH p. 2.6-2's normal minimum) the solve extrapolates the secant, bounded
    by the 31 V envelope edge and the 32.30 V intercept; past the cells' maximum power it has no value,
    and the gap says why rather than "no value"."""
    rules = rules_module()
    for state, key, light, cells in (
        ("bus_a_v", "bus_a_load_w", 780.0, 2),
        ("bus_b_v", "bus_b_load_w", 380.0, 1),
    ):
        params = plant.RuleParams(spec_of(world, state), f"state {state}")
        volts = getattr(rules, state)({key: light, "source_enabled": ALL_ON, **HEALTHY}, params, DT)
        r_bus = R / cells
        i_hand = (E0 - math.sqrt(E0**2 - 4 * r_bus * light)) / (2 * r_bus)
        assert volts == pytest.approx(E0 - r_bus * i_hand, abs=1e-9)
        assert 31.0 < volts < E0
        # Without the declared extrapolation, the same load is a named refusal.
        refused, why = rules.solve_modules(light, E0, [R] * cells, [12.903, 52.593])
        assert refused is None
        assert f"a load of {light:.0f} W puts each of {cells} module(s) at" in why
        assert "below the published normal envelope's 12.903 A" in why, why
        heavy = plant.RuleParams(spec_of(world, state), f"state {state}")
        heavy_inputs = {key: E0**2 / (4 * R / cells) + 1.0, "source_enabled": ALL_ON, **HEALTHY}
        assert getattr(rules, state)(heavy_inputs, heavy, DT) is None
        assert "more than" in heavy.why_none and "can deliver" in heavy.why_none, heavy.why_none
    # And the plant's gap carries the reason.
    heavy_w = E0**2 / (4 * R / 2) + 1.0
    values = dict(plant.initial_values(world), bus_a_load_w=heavy_w)
    state = next(s for s in world.states if s.id == "bus_a_v")
    with pytest.raises(plant.Unconfigured) as refused:
        plant.call_rule(world, state, values, DT)
    assert f"has no value this tick: a load of {heavy_w:.0f} W" in str(refused.value), refused.value


def test_the_buses_start_inside_the_flown_envelope(world):
    """ADR 0003 acceptance: bus A starts inside 26.5-31 V, and so does bus B."""
    after, gaps = tick(world, plant.initial_values(world))
    for sid in ("bus_a_load_w", "bus_b_load_w", "bus_a_v", "bus_b_v", "fuel_cell_current_a"):
        assert sid not in gaps, gaps[sid]
    # MET 0: the transmitter is off, so the amplifier's 72 W is switched on and not drawing.
    # And the standby glycol pump's 250 W is off.
    assert after["bus_a_load_w"] == 1148 - 72 - 250 and after["bus_b_load_w"] == 575
    assert after["fuel_cell_power_w"] == 1401
    for bus in ("bus_a_v", "bus_b_v"):
        assert 26.5 <= after[bus] <= 31.0, (bus, after[bus])
    # The current is the two buses' solves added: P_A / V_A + P_B / V_B.
    assert after["fuel_cell_current_a"] == pytest.approx(
        after["bus_a_load_w"] / after["bus_a_v"] + after["bus_b_load_w"] / after["bus_b_v"]
    )


# ------------------------------------------------------------------------------------------------
# Reactants per ampere, against the J-mission EPS handout's table (p. 2.6-21).
# ------------------------------------------------------------------------------------------------


def test_reactants_per_ampere_match_the_j_mission_table_at_60_amps(world):
    """O2 2.04e-2, H2 2.57e-3 and water 2.297e-2 lb/h per ampere: at 60 A, 1.224, 0.1542 and
    1.3782 lb/h. The draws are evaluated from their own derivations at a 60 A reading."""
    readings = {"fuel_cell_current_a": 60.0}
    o2_kg_s, why = plant.derivation_value(
        spec_of(world, "fc_o2_draw_kg_s")["provenance"]["derivation"], world.documents, readings
    )
    assert o2_kg_s is not None, why
    h2_kg_s, why = plant.derivation_value(
        spec_of(world, "fc_h2_draw_kg_s")["provenance"]["derivation"], world.documents, readings
    )
    assert h2_kg_s is not None, why
    per_hour_lb = 3600 / LB
    assert o2_kg_s * per_hour_lb == pytest.approx(1.224, rel=2e-4)
    assert h2_kg_s * per_hour_lb == pytest.approx(0.1542, rel=2e-4)
    water = next(e for e in world.edges if e.id == "E-FC-WATER").sensitivity["value"]
    assert o2_kg_s * water * per_hour_lb == pytest.approx(1.3782, rel=2e-4)
    # Mass closes across the reaction: the water is the oxygen and the hydrogen it came from.
    assert o2_kg_s + h2_kg_s == pytest.approx(o2_kg_s * water, rel=1e-4)


def test_the_tick_draws_the_tanks_per_ampere_and_the_ledger_closes(world):
    """Fifty ticks: every transfer booked is an integer of its quantum (no tolerance), and the cell's
    draw edge on each tank moves the per-ampere rate times the current the bus solve gives. The
    oxygen tank has a second consumer, the cabin supply, so the cell's share is read off its own edge."""
    values = plant.initial_values(world)
    ledgers = []
    expected = {"E-O2-DRAW": 0.0, "E-H2-DRAW": 0.0}
    o2_per_a = next(e for e in world.edges if e.id == "E-FC-DRAW-O2").sensitivity["value"]
    h2_per_a = next(e for e in world.edges if e.id == "E-FC-DRAW-H2").sensitivity["value"]
    for _ in range(50):
        ledger = plant.Ledger()
        values, gaps = tick(world, values, ledger=ledger)
        assert "o2_csm_kg" not in gaps and "h2_csm_kg" not in gaps
        expected["E-O2-DRAW"] += values["fuel_cell_current_a"] * o2_per_a * DT
        expected["E-H2-DRAW"] += values["fuel_cell_current_a"] * h2_per_a * DT
        ledgers.append(ledger)
    assert plant.assert_conservation(ledgers[-1], nontrivial=True) >= 0
    for ledger in ledgers:
        plant.assert_conservation(ledger)
    for edge, stock in (("E-O2-DRAW", "o2_csm_kg"), ("E-H2-DRAW", "h2_csm_kg")):
        quantum = float(spec_of(world, stock)["quantum"])
        moved = (
            sum(t.quanta for ledger in ledgers for t in ledger.transfers if t.edge == edge)
            * quantum
        )
        assert moved > 0, edge
        # The integer transfers carry their residual, so the total is within one quantum.
        assert moved == pytest.approx(expected[edge], abs=quantum), edge


# ------------------------------------------------------------------------------------------------
# set_load through the real step loop.
# ------------------------------------------------------------------------------------------------


def test_set_load_off_moves_the_bus_load_and_the_bus_voltage_in_the_same_tick(world):
    values, _ = tick(world, plant.initial_values(world))
    lighting = plant.Effect(0, "set_load", {"load": "csm_lighting", "state": "off"})
    after, gaps = tick(world, values, [lighting])
    assert after["load_enabled"]["csm_lighting"] == "off"
    assert after["bus_b_load_w"] == values["bus_b_load_w"] - 100
    assert after["fuel_cell_power_w"] == values["fuel_cell_power_w"] - 100
    # The voltage rises to the terminal line at the smaller load, by hand: one module.
    p = after["bus_b_load_w"]
    i_hand = (E0 - math.sqrt(E0**2 - 4 * R * p)) / (2 * R)
    assert after["bus_b_v"] == pytest.approx(E0 - R * i_hand, abs=1e-9)
    assert after["bus_b_v"] > values["bus_b_v"]
    # Bus A did not move, and the reactant draw fell with the current.
    assert after["bus_a_v"] == values["bus_a_v"]
    assert after["fc_o2_draw_kg_s"] < values["fc_o2_draw_kg_s"]
    assert not {"bus_b_v", "bus_b_load_w"} & set(gaps)
    # And it holds: the next tick does not put the load back.
    held, _ = tick(world, after)
    assert held["load_enabled"]["csm_lighting"] == "off" and held["bus_b_v"] == after["bus_b_v"]


def test_the_amplifier_draws_only_while_the_transmitter_is_on(world):
    """One home for the amplifier's 72 W: the inventory row, gated on its switch *and* on
    `comms.transmitter_on`. The transmitter is set in the value map directly, because the verb that
    moves it is comms' to define."""
    values, _ = tick(world, plant.initial_values(world))
    assert values["transmitter_on"] == "off"
    after, _ = tick(world, {**values, "transmitter_on": "on"})
    assert after["bus_a_load_w"] == values["bus_a_load_w"] + 72
    assert after["bus_a_v"] < values["bus_a_v"] and after["bus_b_v"] == values["bus_b_v"]
    # With its own switch off the amplifier draws nothing, transmitter on or not.
    off = plant.Effect(0, "set_load", {"load": "csm_sband_power_amplifier", "state": "off"})
    later, _ = tick(world, after, [off])
    assert later["transmitter_on"] == "on"
    assert later["bus_a_load_w"] == values["bus_a_load_w"]


# ------------------------------------------------------------------------------------------------
# A coupling that matters: without it the same-tick test above fails.
# ------------------------------------------------------------------------------------------------


def test_removing_the_cell_to_bus_b_coupling_makes_the_bus_lag_a_tick(tmp_path):
    """`E-FC-BUSB` is what orders the `fuel_cell` node (the bus loads) before `bus_b`. Remove it and
    the frozen tiebreak puts `bus_b` first, so `bus_b_v` solves last tick's load: the set_load test's
    same-tick assertion is what fails."""
    broken = plant.load_world(definition(tmp_path, drop_edge="E-FC-BUSB"))
    assert broken.schedule.index("bus_b") < broken.schedule.index("fuel_cell")
    values, _ = tick(broken, plant.initial_values(broken))
    lighting = plant.Effect(0, "set_load", {"load": "csm_lighting", "state": "off"})
    after, _ = tick(broken, values, [lighting])
    assert after["bus_b_load_w"] == values["bus_b_load_w"] - 100
    assert after["bus_b_v"] == values["bus_b_v"], "the bus solved this tick's load without the edge"


def test_removing_the_per_ampere_draw_edge_stops_the_oxygen_tank(tmp_path):
    """`E-FC-DRAW-O2` is the one home of the oxygen cost per ampere; without it the draw has no
    value and the tank it drains is not advanced."""
    broken = plant.load_world(definition(tmp_path, drop_edge="E-FC-DRAW-O2"))
    _, gaps = tick(broken, plant.initial_values(broken))
    assert "fc_o2_draw_kg_s" in gaps and "o2_csm_kg" in gaps


# ------------------------------------------------------------------------------------------------
# What stays off the episode path.
# ------------------------------------------------------------------------------------------------


def test_the_source_converter_is_read_by_nothing_on_the_bus_path(world):
    """ADR 0003 item 1: no converter. Its lag stays owed, and no edge or rule on the bus path reads it."""
    assert spec_of(world, "source_converter_v")["tau_s"] == "UNCONFIGURED"
    assert not [e.id for e in world.edges if e.source == "source_converter"]
    text = (VEHICLE / "domains" / "power" / "rules.py").read_text()
    assert "source_converter" not in text
    _, gaps = tick(world, plant.initial_values(world))
    assert "source_converter_v" in gaps and "bus_a_v" not in gaps and "bus_b_v" not in gaps


# ------------------------------------------------------------------------------------------------
# set_source: a module taken off line (AOH p. 2.6-28), through the real step loop.
# ------------------------------------------------------------------------------------------------


def test_fuel_cell_1_publishes_its_own_current_and_shares_bus_a_equally(world):
    after, gaps = tick(world, plant.initial_values(world))
    assert not {"fc_1_current_a", "bus_a_rated_w"} & set(gaps)
    # MET 0: bus A carries 826 W on two modules, so each carries half the bus current.
    i_bus = (E0 - math.sqrt(E0**2 - 4 * (R / 2) * 826)) / (2 * (R / 2))
    assert after["fc_1_current_a"] == pytest.approx(i_bus / 2, abs=1e-9)
    assert after["bus_a_rated_w"] == 2840


def test_taking_fuel_cell_1_off_line_puts_bus_a_on_one_module_in_the_same_tick(world):
    values, _ = tick(world, plant.initial_values(world))
    off = plant.Effect(0, "set_source", {"source": "fc_1", "state": "off"})
    after, gaps = tick(world, values, [off])
    assert after["source_enabled"]["fc_1"] == "off"
    assert not {"bus_a_v", "fc_1_current_a", "fuel_cell_current_a"} & set(gaps)
    # The load stays; fuel cell 2 carries all of it, by hand: one module, V = E0 - R I.
    p = after["bus_a_load_w"]
    assert p == values["bus_a_load_w"]
    i_hand = (E0 - math.sqrt(E0**2 - 4 * R * p)) / (2 * R)
    assert after["bus_a_v"] == pytest.approx(E0 - R * i_hand, abs=1e-9)
    assert after["bus_a_v"] < values["bus_a_v"]
    assert after["fc_1_current_a"] == 0.0
    # The margin loses the module's 1,420 W, and bus B did not move.
    assert after["bus_a_rated_w"] == 1420
    assert after["bus_b_v"] == values["bus_b_v"]
    # The reactant draw follows the summed current, which rises: one module at a lower voltage.
    assert after["fuel_cell_current_a"] > values["fuel_cell_current_a"]
    # And back on: the bus returns to the two-module operating point.
    on = plant.Effect(0, "set_source", {"source": "fc_1", "state": "on"})
    back, _ = tick(world, after, [on])
    assert back["bus_a_v"] == pytest.approx(values["bus_a_v"], abs=1e-12)


def test_a_bus_with_no_connected_module_is_dead(world):
    """Fuel cell 3 off: in coast the batteries are off the main buses (TN D-7609), so bus B has no
    source. Its loads draw nothing, it reads 0 V, and the generation and draw lose its share."""
    values, _ = tick(world, plant.initial_values(world))
    off = plant.Effect(0, "set_source", {"source": "fc_3", "state": "off"})
    after, gaps = tick(world, values, [off])
    assert not {"bus_b_v", "bus_b_load_w", "fuel_cell_current_a"} & set(gaps)
    assert after["bus_b_load_w"] == 0.0 and after["bus_b_v"] == 0.0
    assert after["fuel_cell_power_w"] == values["bus_a_load_w"]
    assert after["fuel_cell_current_a"] == pytest.approx(after["bus_a_load_w"] / after["bus_a_v"])
    assert after["bus_a_v"] == values["bus_a_v"]


# ------------------------------------------------------------------------------------------------
# PWR-02: a degrading module, as its rising source resistance.
# ------------------------------------------------------------------------------------------------


def test_modules_at_unequal_resistance_share_one_voltage_by_hand():
    """Two modules in parallel at one bus voltage: i_k = (E0 - V) / R_k, and the bus is
    V = E0 - R_eq I with R_eq = 1 / (1/R_1 + 1/R_2). Pick V, compute the load by hand."""
    rules = rules_module()
    r1, r2, v = 1.5 * R, R, 29.8
    i1, i2 = (E0 - v) / r1, (E0 - v) / r2
    solved, why = rules.solve_modules(v * (i1 + i2), E0, [r1, r2], [12.903, 52.593])
    assert why is None
    current, volts, modules = solved
    assert (current, volts) == pytest.approx((i1 + i2, v), abs=1e-9)
    assert modules == pytest.approx([i1, i2], abs=1e-9)


def test_a_degraded_fuel_cell_1_carries_less_and_its_partner_more(world):
    """R_1 x 1.5, PWR-02's "loses a third of its capacity and its internal resistance rises": fuel
    cell 1 carries 0.4 of bus A's current instead of 0.5, fuel cell 2 takes it up, bus A sags, and the
    margin loses a third of fuel cell 1's 1,420 W. At the flown 23 A a module (Apollo 14 Mission
    Report 7.2.2) that is a 4.6 A drop, inside AOH p. 2.6-25's 3-5 A degradation-purge cue."""
    rules = rules_module()
    v_flown = E0 - R * 23.0
    solved, _ = rules.solve_modules(v_flown * 46.0, E0, [1.5 * R, R], [12.903, 52.593])
    assert 3.0 <= 23.0 - solved[2][0] <= 5.0, solved
    values, _ = tick(world, plant.initial_values(world))
    degraded, gaps = tick(world, {**values, "fc_1_resistance_ohm": 1.5 * R})
    assert not {"bus_a_v", "fc_1_current_a", "bus_a_rated_w"} & set(gaps)
    assert degraded["fc_1_current_a"] < values["fc_1_current_a"]
    # Bus A by hand at R_eq = 1 / (1/1.5R + 1/R) = 0.6 R.
    p = degraded["bus_a_load_w"]
    r_eq = 0.6 * R
    i_hand = (E0 - math.sqrt(E0**2 - 4 * r_eq * p)) / (2 * r_eq)
    v_hand = E0 - r_eq * i_hand
    assert degraded["bus_a_v"] == pytest.approx(v_hand, abs=1e-9)
    assert degraded["fc_1_current_a"] == pytest.approx((E0 - v_hand) / (1.5 * R), abs=1e-9)
    assert degraded["bus_a_v"] < values["bus_a_v"]
    assert degraded["bus_a_rated_w"] == pytest.approx(1420 / 1.5 + 1420)
    # The held resistance stays where the fault put it, and bus B never saw it.
    assert degraded["fc_1_resistance_ohm"] == 1.5 * R
    assert degraded["bus_b_v"] == values["bus_b_v"]
    # Taking the degraded module off line restores none of its rating, and a healthy module alone
    # carries bus A.
    off = plant.Effect(0, "set_source", {"source": "fc_1", "state": "off"})
    isolated, _ = tick(world, degraded, [off])
    assert isolated["bus_a_rated_w"] == 1420 and isolated["fc_1_current_a"] == 0.0
