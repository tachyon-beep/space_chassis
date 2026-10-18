"""The thermal rules of the quiet-coast episode, each against an independent analytic case.

`domains/thermal/rules.py` (D5) and ADR 0003 items 4, 5 and 9-11; `09-quiet-coast-episode.md` §3,
§5 and §7 steps 3-4. Every expected figure here is computed in the test from the published
constants, by a method other than the rule's own (a closed form, a Newton solve where the rule
bisects, a sum over the power inventory where the rule sums its own copy), so a rule that agrees
with itself and not with the physics fails.

**The fixture.** The thermal rules read `power.load_enabled` (power puts it on `load_shed_state`,
which thermal reads) and `comms.amp_dissipation_w` (on `link`), which the power and comms rules
land in their own commits. Until those merge, `episode_definition` writes them into a copy of the
definition in the shape their authors declared: every CSM load on, every LM load off (power's
MET-0 positions), the transmitter off. Power's state goes on a fixture node of its own,
`load_switches`, so the fixture does not depend on power's plant fix for a keyed state on a shared
node. Each injection is skipped when the declaration is already present, so on the merged tree
the fixture injects nothing and tests the real states.
"""

from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402

DT = 0.02
SIGMA = 5.670374419e-08
LATENT_J_PER_KG = 2.45e6  # E-WATER-RAD's 1 / 2.45e6

# --------------------------------------------------------------------------------------------
# The published constants, read from their homes rather than from the thermal states' copies.
# --------------------------------------------------------------------------------------------
_VEHICLE_DOC = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
_LOOP = next(x for x in _VEHICLE_DOC["thermal"]["loops"] if x["id"] == "loop_primary")
_LM_LOOP = next(x for x in _VEHICLE_DOC["thermal"]["loops"] if x["id"] == "loop_lm")
_ZONES = {z["id"]: z for z in _VEHICLE_DOC["thermal"]["zones"]}
_THERMAL = yaml.safe_load((VEHICLE / "domains/thermal/components.yaml").read_text())
_POWER = yaml.safe_load((VEHICLE / "domains/power/components.yaml").read_text())
_RAD = _THERMAL["radiator_model"]["csm"]
_ENV = _THERMAL["radiator_model"]["environment"]
EPS_SIGMA_A = _RAD["emissivity"] * SIGMA * _RAD["area_effective_m2"]
Q_ENV = _ENV["solar_flux_w_m2"] * _ENV["absorptivity"] * _ENV["projected_area_m2"]
CP = _LOOP["specific_heat_j_per_kg_k"]
RATED_FLOW = _LOOP["nominal_flow_lb_per_h"] * 0.45359237 / 3600
C_LOOP = _LOOP["coolant_mass_kg"] * CP
SUPPLY_K = _LOOP["supply_c"] + 273.15
DEMAND = {row["id"]: row["demand_w"] for row in _POWER["loads"]}
STATES = {row["id"]: row for row in _THERMAL["state"]}
EVAPORATOR_W = next(c for c in _THERMAL["components"] if c["id"] == "evaporator_csm")["rejection_w"]

# Power's MET-0 positions (rules-power, 2026-10-15): every CSM load on, every LM load off; the
# amplifier's 72 W are dissipated only while comms' transmitter is on, and it starts off.
MET0_ENABLED = {load: ("on" if load.startswith("csm_") else "off") for load in DEMAND}
AMP_DISSIPATION_ON_W = 72.0 - 11.2  # comms: dc 72 W less 11.2 W RF (NR ch. 18)


# --------------------------------------------------------------------------------------------
# The fixture: the episode's cross-domain declarations, injected only where absent.
# --------------------------------------------------------------------------------------------


def _replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert text.count(old) == 1, (path, old)
    path.write_text(text.replace(old, new))


def episode_definition(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    for name in plant.CORPUS_TOP_LEVEL:
        shutil.copy(VEHICLE / name, destination / name)
    shutil.copytree(VEHICLE / "domains", destination / "domains")
    domains = destination / "domains"
    coupling = destination / "coupling.yaml"

    power = domains / "power" / "components.yaml"
    if "id: load_enabled" not in power.read_text():
        _replace_once(
            coupling,
            "nodes:\n",
            "nodes:\n  load_switches: {domain: power, kind: discrete, unit: enum, key_space: by_state}\n",
        )
        _replace_once(power, "writes: [fuel_cell,", "writes: [load_switches, fuel_cell,")
        initial = ", ".join(f'{k}: "{v}"' for k, v in sorted(MET0_ENABLED.items()))
        _replace_once(
            power,
            "state:\n",
            "state:\n  - id: load_enabled\n    node: load_switches\n    method: discrete\n"
            '    unit: "map[load_id,enum[on,off]]"\n'
            f"    initial: {{{initial}}}\n"
            '    moved_by: ["command:set_load"]\n'
            "    command_value:\n      - verb: set_load\n        argument: state\n        key: load\n",
        )

        # Power's own commit puts the state on `load_shed_state`, beside `load_shed_class`, with a
        # plant fix for a keyed state on a shared node; this fixture gives it a node of its own so
        # it does not depend on that fix, and lets thermal read it there.
        thermal = domains / "thermal" / "components.yaml"
        _replace_once(thermal, "reads: [fuel_cell,", "reads: [load_switches, fuel_cell,")

    comms = domains / "comms" / "components.yaml"
    if "id: transmitter_on" not in comms.read_text():
        text = comms.read_text()
        start = text.index("  - id: tx_power\n")
        head, tail = text[:start], text[start:]
        tail = tail.replace("        selects: UNCONFIGURED", "        selects: transmitter_on", 1)
        comms.write_text(
            head + "  - id: transmitter_on\n    node: link\n    method: discrete\n"
            '    unit: "enum[on,off]"\n    initial: "off"\n'
            '    moved_by: ["command:set_power_amplifier"]\n'
            "    command_value:\n      - verb: set_power_amplifier\n        argument: state\n"
            "  - id: amp_dissipation_w\n    node: link\n    method: algebraic\n    unit: W\n"
            f"    on_w: {AMP_DISSIPATION_ON_W!r}\n" + tail
        )
        _replace_once(
            coupling,
            "    state_order: [tx_power, link_snr]",
            "    state_order: [transmitter_on, tx_power, amp_dissipation_w, link_snr]",
        )
        rules = domains / "comms" / plant.RULES_FILE
        assert not rules.exists()
        rules.write_text(
            "def amp_dissipation_w(inputs, params, dt):\n"
            "    return float(params['on_w']) if inputs['transmitter_on'] == 'on' else 0.0\n\n\n"
            "RULES = {'amp_dissipation_w': amp_dissipation_w}\n"
        )
    return destination


@pytest.fixture(scope="module")
def world(tmp_path_factory) -> plant.World:
    return plant.load_world(episode_definition(tmp_path_factory.mktemp("episode") / "vehicle"))


# The episode's hot hold is the scenario's, not the vehicle's (ADR 0003 item 9, John 2026-10-15:
# "Hold in episode only"): every test here starts where `scenarios/quiet_coast.yaml` puts it.
EPISODE_SCENARIO = VEHICLE / "scenarios" / "quiet_coast.yaml"
EPISODE_INITIAL = yaml.safe_load(EPISODE_SCENARIO.read_text())["initial"]


def episode_start(world) -> dict:
    """The quiet-coast episode's MET-0 values: the vehicle's, with the scenario's overrides."""
    return plant.initial_values(world, plant.load_scenario(world, EPISODE_SCENARIO))


def run(world, values, ticks, effects=None, dt=DT, on_tick=None):
    """The real step loop, `ticks` times; `effects` maps a tick to its commands."""
    for tick in range(ticks):
        ledger = plant.Ledger()
        gaps: list[plant.Gap] = []
        before = values
        values = plant.step(world, values, dt, gaps, (effects or {}).get(tick), ledger=ledger)
        thermal_gaps = [g for g in gaps if g.state.domain == "thermal" and g.state.id in RULED]
        assert not thermal_gaps, [(g.state.id, g.owed) for g in thermal_gaps]
        plant.assert_conservation(ledger)
        if on_tick is not None:
            on_tick(tick, before, values, ledger)
    return values


RULED = {
    "environment_heat_w",
    "cabin_heat_csm_w",
    "cabin_heat_lm_w",
    "service_bay_heat_w",
    "descent_bay_heat_w",
    "avionics_bay_heat_w",
    "loop_primary_load_w",
    "loop_lm_load_w",
    "cabin_eq_csm_k",
    "cabin_eq_lm_k",
    "coolant_flow_kg_s",
    "radiator_eq_t",
    "radiator_rejection_w",
    "evaporator_duty_w",
    "coolant_loop_t",
    "zone_csm_avionics_t",
    "comm_amp_t",
    "zone_csm_service_t",
    "zone_lm_descent_t",
    "pump_1_speed_frac",
}


def effect(verb, **arguments):
    return plant.Effect(0, verb, arguments)


# --------------------------------------------------------------------------------------------
# Hand solutions, by methods other than the rules'.
# --------------------------------------------------------------------------------------------


def met0_loop_load_w() -> float:
    """The CSM loop's collected load at MET 0: every CSM load on, the amplifier dissipating nothing."""
    zones = ("csm_cabin", "csm_service_bay", "csm_avionics_bay")
    loads = [load for zone in zones for load in _THERMAL["heat_inputs"][zone]["loads"]]
    return float(sum(DEMAND[load] for load in loads if load != "csm_sband_power_amplifier"))


def panel_mean_newton(supply_k: float, load_w: float, capacity: float) -> float:
    """Newton on `T - T_ri + (a T^4 - Q_env) / (2W) = 0` from the inlet (the rule bisects)."""
    inlet = supply_k + load_w / capacity
    t = inlet
    for _ in range(50):
        f = t - inlet + (EPS_SIGMA_A * t**4 - Q_ENV) / (2 * capacity)
        t -= f / (1 + 4 * EPS_SIGMA_A * t**3 / (2 * capacity))
    return t


# --------------------------------------------------------------------------------------------
# 1. The copies the rules read agree with their homes.
# --------------------------------------------------------------------------------------------


def test_each_heat_rate_state_copies_its_zone_s_loads_and_the_power_inventory_s_figures():
    """A rule reads only its own state's declaration, so each heat-rate state carries its loads'
    `demand_w`. This is the check that the copy cannot drift: the key set is the zone's
    `heat_inputs` and every figure is the power inventory's."""
    for zone in _VEHICLE_DOC["thermal"]["zones"]:
        name = zone.get("heat_state")
        if name is None:
            continue
        state = STATES[name]
        assert set(state["heat_loads_w"]) == set(_THERMAL["heat_inputs"][zone["id"]]["loads"]), name
        for load, watts in state["heat_loads_w"].items():
            assert watts == DEMAND[load], (name, load)
        assert sum(state["heat_loads_w"].values()) == state["total_w"], name


def test_the_rules_copies_of_the_loop_and_radiator_constants_agree_with_their_homes():
    for name in ("radiator_eq_t", "radiator_rejection_w"):
        assert STATES[name]["emissivity"] == _RAD["emissivity"]
        assert STATES[name]["area_effective_m2"] == _RAD["area_effective_m2"]
        assert STATES[name]["stefan_boltzmann"] == SIGMA
    for name in ("radiator_eq_t", "evaporator_duty_w"):
        assert STATES[name]["specific_heat_j_per_kg_k"] == CP
    for name in (
        "coolant_flow_kg_s",
        "coolant_loop_t",
        "radiator_eq_t",
        "evaporator_duty_w",
        "zone_csm_avionics_t",
        "zone_csm_service_t",
    ):
        assert STATES[name]["rated_flow_kg_s"] == pytest.approx(RATED_FLOW, rel=1e-15)
    assert STATES["zone_lm_descent_t"]["supply_k"] == pytest.approx(_LM_LOOP["supply_c"] + 273.15)
    assert STATES["pump_1_speed_frac"]["tau_s"] == STATES["coolant_flow_kg_s"]["tau_s"]
    assert STATES["coolant_loop_t"]["heat_capacity_j_per_k"] == pytest.approx(C_LOOP, rel=1e-12)
    assert STATES["evaporator_duty_w"]["capacity_w"] == EVAPORATOR_W
    assert STATES["evaporator_duty_w"]["outlet_setpoint_k"] == pytest.approx(SUPPLY_K)
    assert STATES["evaporator_duty_w"]["actuation_k"] == pytest.approx(
        _LOOP["evaporator_actuation_c"] + 273.15
    )
    # The AOH's evaporator-mode band, 48-50.5 F, holds the actuation; its 38-45 F outlet band
    # holds the setpoint (SM2A-03 Vol. 1 p. 2.7-18).
    f_to_k = lambda f: (f - 32) / 1.8 + 273.15  # noqa: E731
    assert f_to_k(48) <= STATES["evaporator_duty_w"]["actuation_k"] <= f_to_k(50.5)
    assert f_to_k(38) <= STATES["evaporator_duty_w"]["outlet_setpoint_k"] <= f_to_k(45) + 1e-9
    for cabin, zone in (
        ("cabin_eq_csm_k", "zone_csm_cabin_t"),
        ("cabin_eq_lm_k", "zone_lm_cabin_t"),
    ):
        assert STATES[cabin]["conductance_w_per_k"] == STATES[zone]["conductance_w_per_k"]
    pumps = {
        c["id"]: c.get("power_load") for c in _THERMAL["components"] if c.get("class") == "pump"
    }
    assert STATES["coolant_flow_kg_s"]["pump_loads"] == {k: pumps[k] for k in ("pump_1", "pump_2")}
    assert STATES["pump_1_speed_frac"]["pump_load"] == pumps["pump_1"]


def test_every_chosen_value_carries_the_adr_0003_item_11_label():
    for name in ("zone_csm_avionics_t", "comm_amp_t", "zone_csm_service_t", "zone_lm_descent_t"):
        provenance = STATES[name]["provenance"]
        assert provenance["basis"] == "chosen"
        assert "chosen, pending operator, ADR 0003 item 11" in provenance["reason"]
    for name in ("zone_csm_service_t", "zone_lm_descent_t"):
        assert "chosen, pending operator, ADR 0003 item 11" in (
            STATES[name]["initial_provenance"]["reason"]
        )


# --------------------------------------------------------------------------------------------
# 2. Heat rates over enabled loads.
# --------------------------------------------------------------------------------------------


def test_heat_rates_are_summed_over_enabled_loads_and_a_shed_load_stops_heating_that_tick(world):
    start = episode_start(world)
    assert start["loop_primary_load_w"] == pytest.approx(met0_loop_load_w())
    assert start["cabin_heat_lm_w"] == 0.0 and start["descent_bay_heat_w"] == 0.0

    after = run(world, start, 1, {0: [effect("set_load", load="csm_lighting", state="off")]})
    assert after["cabin_heat_csm_w"] == pytest.approx(
        start["cabin_heat_csm_w"] - DEMAND["csm_lighting"]
    )

    amp = run(world, start, 1, {0: [effect("set_power_amplifier", state="on")]})
    assert amp["cabin_heat_csm_w"] == pytest.approx(
        start["cabin_heat_csm_w"] + AMP_DISSIPATION_ON_W
    )


# --------------------------------------------------------------------------------------------
# 3. The radiator at a given temperature: Stefan-Boltzmann.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("surface_k", [260.0, 282.23, 300.0, 322.06])
def test_radiator_rejection_is_stefan_boltzmann_at_the_panel_temperature_less_the_hold(
    world, surface_k
):
    values = episode_start(world)
    values = {**values, "zone_radiator_t": surface_k}
    rule = world.rules["radiator_rejection_w"]
    readable = world.rule_reads.get("thermal") or plant.rule_readable(world, {})["thermal"]
    state = next(s for s in world.states if s.id == "radiator_rejection_w")
    got = rule.function(
        plant.RuleInputs(values, readable, "thermal", "test"),
        plant.RuleParams(state.spec, "test"),
        DT,
    )
    expected = 0.85 * SIGMA * 8.1 * surface_k**4 - 1361 * 0.2 * 9.1
    assert got == pytest.approx(expected, abs=1e-9)
    # At the panel's own sink the rejection is zero: the hold is all it absorbs.
    if surface_k == 282.23:
        assert abs(got) < 0.1


# --------------------------------------------------------------------------------------------
# 4. The loop's steady state against a hand energy balance.
# --------------------------------------------------------------------------------------------


def test_the_loop_s_steady_state_is_the_hand_energy_balance(world):
    """At MET 0 the episode starts at its own equilibrium (ADR 0003 item 10). Hand balance: the
    loads put Q in; the panel's glycol sits at the Newton root of its own balance; the panel
    rejects `eps sigma A T^4 - Q_env`; the evaporator takes the rest and holds the loop at its
    280.35 K setpoint. Ten minutes through the step loop, the loop has not moved."""
    q = met0_loop_load_w()
    capacity = RATED_FLOW * CP
    panel = panel_mean_newton(SUPPLY_K, q, capacity)
    q_rad = EPS_SIGMA_A * panel**4 - Q_ENV
    q_evap = q - q_rad
    assert EPISODE_INITIAL["environment_heat_w"] == pytest.approx(Q_ENV, abs=1e-9)
    assert EPISODE_INITIAL["zone_radiator_t"] == pytest.approx(panel, abs=0.01)
    assert EPISODE_INITIAL["evaporator_duty_w"] == pytest.approx(q_evap, abs=0.1)

    values = run(world, episode_start(world), 30_000)
    assert values["coolant_loop_t"] == pytest.approx(SUPPLY_K, abs=0.01)
    assert values["radiator_eq_t"] == pytest.approx(panel, abs=1e-3)
    assert values["zone_radiator_t"] == pytest.approx(panel, abs=0.01)
    assert values["radiator_rejection_w"] == pytest.approx(q_rad, abs=0.5)
    assert values["evaporator_duty_w"] == pytest.approx(q_evap, abs=0.5)
    assert values["radiator_rejection_w"] + values["evaporator_duty_w"] == pytest.approx(q, abs=0.5)
    # The plate and the amplifier at their own equilibria over the chosen conductances.
    plate = SUPPLY_K + 360 / 120
    assert values["zone_csm_avionics_t"] == pytest.approx(plate, abs=1e-3)
    assert values["comm_amp_t"] == pytest.approx(plate, abs=1e-3)
    assert STATES["zone_csm_avionics_t"]["initial"] == pytest.approx(plate, abs=1e-4)


def test_with_the_radiator_alone_carrying_the_load_no_water_is_spent(world):
    """ADR 0003's acceptance: a test fails if water drains while the radiator alone carries the
    load. Shed loads until the panel can carry the rest: the evaporator's inlet falls below its
    setpoint, it unlatches, and the tank stops moving."""
    shed = [
        "csm_coolant_pump_2",
        "csm_heaters",
        "csm_lighting",
        "csm_rcs_heaters",
        "csm_comm_heaters",
        "csm_co2_scrubber",
        "csm_suit_fan",
        "csm_cabin_fan",
        "csm_instrumentation",
        "csm_guidance_computer",
        "csm_sband_transceiver",
        "csm_imu",
    ]
    values = episode_start(world)
    values = run(
        world, values, 1, {0: [effect("set_load", load=load, state="off") for load in shed]}
    )
    assert values["loop_primary_load_w"] <= 250.0
    values = run(world, values, 3000)
    assert values["evaporator_duty_w"] == 0.0
    water = values["water_cooling_kg"]
    values = run(world, values, 3000)
    assert values["water_cooling_kg"] == water


# --------------------------------------------------------------------------------------------
# 5. The evaporator's water is its duty over the latent heat, on the ledger.
# --------------------------------------------------------------------------------------------


def test_evaporator_water_drained_is_duty_over_latent_heat_on_the_ledger(world):
    water = next(s for s in world.states if s.id == "water_cooling_kg")
    numerator, denominator = plant.stock_quantum(water, "water")
    quantum_kg = numerator / denominator
    booked = 0
    expected_kg = 0.0

    def on_tick(tick, before, after, ledger):
        nonlocal booked, expected_kg
        booked += sum(t.quanta for t in ledger.transfers if t.edge == "E-WATER-RAD")
        # E-WATER-RAD is the back-edge of C-WATER-BUDGET: the tank pays for last tick's duty.
        expected_kg += before["evaporator_duty_w"] * DT / LATENT_J_PER_KG

    start = episode_start(world)
    values = run(world, start, 15_000, on_tick=on_tick)
    assert booked > 0
    assert booked * quantum_kg == pytest.approx(expected_kg, abs=quantum_kg)
    assert start["water_cooling_kg"] - values["water_cooling_kg"] == pytest.approx(
        booked * quantum_kg, abs=1e-12
    )


def test_feed_off_spends_no_water_and_the_loop_warms(world):
    values = episode_start(world)
    values = run(world, values, 1, {0: [effect("set_evaporator_feed", vehicle="csm", state="off")]})
    before = values
    values = run(world, values, 3000)
    assert values["evaporator_duty_w"] == 0.0
    assert values["water_cooling_kg"] == before["water_cooling_kg"]
    assert values["coolant_loop_t"] > before["coolant_loop_t"] + 0.5


# --------------------------------------------------------------------------------------------
# 6. The pump as flow, and pump off through the real step loop.
# --------------------------------------------------------------------------------------------


def test_set_coolant_pump_moves_the_flow_as_a_fraction_of_the_published_rate(world):
    values = episode_start(world)
    assert values["coolant_flow_kg_s"] == pytest.approx(RATED_FLOW)
    off = run(
        world,
        values,
        1,
        {0: [effect("set_coolant_pump", loop="loop_primary", pump="pump_1", state="off")]},
    )
    assert off["coolant_pump"]["pump_1"] == "off"
    off = run(world, off, 2000)  # 40 s, five spin-down constants
    assert off["coolant_flow_kg_s"] == pytest.approx(RATED_FLOW * math.exp(-40.02 / 8), rel=1e-6)
    on = run(
        world,
        off,
        1,
        {0: [effect("set_coolant_pump", loop="loop_primary", pump="pump_2", state="on")]},
    )
    on = run(world, on, 3000)
    assert on["coolant_flow_kg_s"] == pytest.approx(RATED_FLOW, rel=1e-3)


def test_pump_off_raises_the_loop_temperature_through_the_real_step_loop(world):
    """With no flow nothing leaves the loop: the panel and the evaporator take heat only from
    coolant that passes them. Hand bound: after the 8 s spin-down the loop warms at Q/C."""
    values = episode_start(world)
    start = values["coolant_loop_t"]
    pump_off = {0: [effect("set_coolant_pump", loop="loop_primary", pump="pump_1", state="off")]}
    values = run(world, values, 15_000, pump_off)  # 300 s
    q = met0_loop_load_w()
    rise = values["coolant_loop_t"] - start
    # The removal is the flow share times what it was: integral of exp(-t/8) over 300 s is 8 s of
    # full removal, so the rise is Q * (300 - 8) / C, to within the share's own transient.
    assert rise == pytest.approx(q * (300 - 8) / C_LOOP, rel=0.02)
    assert values["evaporator_duty_w"] < 1.0
    assert values["zone_csm_avionics_t"] > STATES["zone_csm_avionics_t"]["initial"] + 1.0


# --------------------------------------------------------------------------------------------
# 6b. The pump's speed, as a fraction of its rated speed (ADR 0003 item 4).
# --------------------------------------------------------------------------------------------


def test_pump_1_speed_follows_its_own_pump_and_not_the_loop_s_flow(world):
    """Stopping pump 1 spins its shaft down with the 8 s constant; starting pump 2 restores the
    flow and leaves pump 1's speed at zero. That separation is what the speed channel is for."""
    values = episode_start(world)
    assert values["pump_1_speed_frac"] == 1.0
    off = run(
        world,
        values,
        1,
        {0: [effect("set_coolant_pump", loop="loop_primary", pump="pump_1", state="off")]},
    )
    off = run(world, off, 2000)  # 40 s
    assert off["pump_1_speed_frac"] == pytest.approx(math.exp(-40.02 / 8), rel=1e-6)
    on = run(
        world,
        off,
        1,
        {0: [effect("set_coolant_pump", loop="loop_primary", pump="pump_2", state="on")]},
    )
    on = run(world, on, 3000)
    assert on["coolant_flow_kg_s"] == pytest.approx(RATED_FLOW, rel=1e-3)
    assert on["pump_1_speed_frac"] < 1e-5


def test_a_shed_pump_load_stops_the_shaft_with_the_command_still_on(world):
    values = episode_start(world)
    values = run(world, values, 1, {0: [effect("set_load", load="csm_coolant_pump_1", state="off")]})
    values = run(world, values, 400)  # 8 s more, one constant
    assert values["coolant_pump"]["pump_1"] == "on"
    assert values["pump_1_speed_frac"] == pytest.approx(math.exp(-8.02 / 8), rel=1e-6)


# --------------------------------------------------------------------------------------------
# 6c. The two bays: heat balances on their loops (ADR 0003 items 10-11).
# --------------------------------------------------------------------------------------------


def _band_middle_k(zone):
    low, high = _ZONES[zone]["limit_c"]
    return (low + high) / 2 + 273.15


def test_each_bay_starts_in_the_middle_of_its_band_and_its_g_holds_it_under_its_limit():
    for state, zone, heat_w, supply_k in (
        ("zone_csm_service_t", "csm_service_bay", met0_service_bay_w(), SUPPLY_K),
        ("zone_lm_descent_t", "lm_descent_bay", 180.0, _LM_LOOP["supply_c"] + 273.15),
    ):
        spec = STATES[state]
        assert spec["initial"] == pytest.approx(_band_middle_k(zone))
        # The powered equilibrium, supply + Q/G, sits inside the band and under the upper limit.
        equilibrium = supply_k + heat_w / spec["conductance_w_per_k"]
        assert abs(equilibrium - spec["initial"]) < 0.05, state
        assert equilibrium < _ZONES[zone]["limit_c"][1] + 273.15
    # C/G is the time constant each zone carried as a lag.
    for state, tau in (("zone_csm_service_t", 7200), ("zone_lm_descent_t", 10800)):
        spec = STATES[state]
        capacity = spec["lumped_mass_kg"] * spec["specific_heat_j_per_kg_k"]
        assert capacity / spec["conductance_w_per_k"] == pytest.approx(tau)


def met0_service_bay_w() -> float:
    return float(sum(DEMAND[load] for load in _THERMAL["heat_inputs"]["csm_service_bay"]["loads"]))


def test_the_service_bay_relaxes_to_its_equilibrium_with_its_own_time_constant(world):
    """Displaced 10 K, the bay returns as `exp(-t/tau)` with `tau = C/G`, over coolant the loop
    holds at its supply. Hand solution in closed form; the rule steps it explicitly. The bay only:
    the loop is fed the bay's raw heat, not this transfer, so the loop's side of the transient is a
    declared debt (`components.yaml#open_debts`, the loop collects its nodes' heat) until the
    space-sink follow-up's coupled energy-balance test."""
    spec = STATES["zone_csm_service_t"]
    tau = spec["lumped_mass_kg"] * spec["specific_heat_j_per_kg_k"] / spec["conductance_w_per_k"]
    values = dict(episode_start(world))
    assert values["zone_csm_service_t"] == pytest.approx(spec["initial"])
    values["zone_csm_service_t"] = spec["initial"] + 10.0
    values = run(world, values, 3600, dt=1.0)
    equilibrium = values["coolant_loop_t"] + met0_service_bay_w() / spec["conductance_w_per_k"]
    assert values["zone_csm_service_t"] == pytest.approx(
        equilibrium + 10.0 * math.exp(-3600 / tau), abs=0.05
    )


def test_the_service_bay_warms_while_the_loop_is_stopped(world):
    values = episode_start(world)
    start = values["zone_csm_service_t"]
    pump_off = {0: [effect("set_coolant_pump", loop="loop_primary", pump="pump_1", state="off")]}
    values = run(world, values, 300, pump_off, dt=1.0)
    assert values["zone_csm_service_t"] > start + 0.3


def test_the_descent_stage_holds_unpowered_and_warms_at_q_over_c_with_its_radar_on(world):
    """At MET 0 the LM is unpowered and its pump off: nothing heats the stage and nothing cools it.
    The landing radar on with the pump still off warms it at exactly `Q / C`."""
    spec = STATES["zone_lm_descent_t"]
    capacity = spec["lumped_mass_kg"] * spec["specific_heat_j_per_kg_k"]
    values = episode_start(world)
    held = run(world, values, 600, dt=1.0)
    assert held["zone_lm_descent_t"] == spec["initial"]
    radar = {0: [effect("set_load", load="lm_landing_radar", state="on")]}
    warmed = run(world, values, 3600, radar, dt=1.0)
    rise = DEMAND["lm_landing_radar"] * 3600 / capacity
    assert warmed["zone_lm_descent_t"] - spec["initial"] == pytest.approx(rise, rel=1e-3)


def test_the_descent_stage_cools_toward_the_lm_supply_with_the_lm_pump_on(world):
    spec = STATES["zone_lm_descent_t"]
    tau = spec["lumped_mass_kg"] * spec["specific_heat_j_per_kg_k"] / spec["conductance_w_per_k"]
    supply = _LM_LOOP["supply_c"] + 273.15
    pump_on = {0: [effect("set_coolant_pump", loop="loop_lm", pump="pump_lm", state="on")]}
    values = run(world, episode_start(world), 7200, pump_on, dt=1.0)
    expected = supply + (spec["initial"] - supply) * math.exp(-7200 / tau)
    assert values["zone_lm_descent_t"] == pytest.approx(expected, abs=1e-3)


# --------------------------------------------------------------------------------------------
# 7. The bypass valve.
# --------------------------------------------------------------------------------------------


def test_radiator_bypass_takes_the_panel_out_of_the_loop(world):
    values = episode_start(world)
    values = run(
        world, values, 1, {0: [effect("set_radiator_bypass", loop="loop_primary", state="bypass")]}
    )
    assert values["radiator_bypass"]["loop_primary"] == "bypass"
    sink = (Q_ENV / EPS_SIGMA_A) ** 0.25
    assert values["radiator_eq_t"] == pytest.approx(sink, abs=1e-6)
    values = run(world, values, 15_000)
    # The evaporator takes the whole load within its capacity, and the loop holds.
    assert values["evaporator_duty_w"] == pytest.approx(values["loop_primary_load_w"], abs=1.0)
    assert values["coolant_loop_t"] == pytest.approx(SUPPLY_K, abs=0.05)


# --------------------------------------------------------------------------------------------
# 8. The 40-minute baseline.
# --------------------------------------------------------------------------------------------

APOLLO_14_EVAPORATED_KG = 9.0 * 0.45359237  # A14 MR §7.10.4, the whole flight


def coast(world, ticks, dt, effects=None):
    peaks = {
        "zone_csm_avionics_t": -1.0,
        "comm_amp_t": -1.0,
        "coolant_loop_t": -1.0,
        "zone_csm_cabin_t": -1.0,
    }
    lows = {"zone_csm_cabin_t": 1e9}
    duty = []

    def on_tick(tick, before, after, ledger):
        for key in peaks:
            peaks[key] = max(peaks[key], after[key])
        lows["zone_csm_cabin_t"] = min(lows["zone_csm_cabin_t"], after["zone_csm_cabin_t"])
        duty.append(after["evaporator_duty_w"])

    start = episode_start(world)
    end = run(world, start, ticks, effects, dt=dt, on_tick=on_tick)
    return start, end, peaks, lows, duty


def test_a_forty_minute_coast_at_nominal_loads_holds_the_water_bound_and_the_thresholds(world):
    """`09` §2: 40 min, the declared hot hold, MET-0 loads, no commands. Run at a 1 s horizon
    (2,400 ticks of the same step loop; the slowest constant the step resolves is the pump's 8 s
    spin-up, which does not move here). §5's thermal margins: coldplate < 50 C, comm amp < 60 C,
    coolant supply < 10 C, cabin within 10-30 C."""
    start, end, peaks, lows, duty = coast(world, 2400, 1.0)
    used = start["water_cooling_kg"] - end["water_cooling_kg"]
    assert 0.0 < used < APOLLO_14_EVAPORATED_KG
    assert peaks["zone_csm_avionics_t"] < 50 + 273.15
    assert peaks["comm_amp_t"] < 60 + 273.15
    assert peaks["coolant_loop_t"] < 10 + 273.15
    assert lows["zone_csm_cabin_t"] > 10 + 273.15 and peaks["zone_csm_cabin_t"] < 30 + 273.15
    assert max(duty) <= EVAPORATOR_W


def test_the_same_coast_with_the_amplifier_on_throughout_still_holds(world):
    """Policy A's thermal half: the transmitter on for the whole 40 minutes."""
    amp_on = {0: [effect("set_power_amplifier", state="on")]}
    start, end, peaks, lows, duty = coast(world, 2400, 1.0, amp_on)
    used = start["water_cooling_kg"] - end["water_cooling_kg"]
    assert used < APOLLO_14_EVAPORATED_KG
    assert peaks["comm_amp_t"] < 60 + 273.15
    assert peaks["zone_csm_avionics_t"] < 50 + 273.15
