"""The propulsion rules: main-engine thrust from the firing engine, the chamber pressure behind it,
and the SPS's helium pressurization that sets the feed.

`domains/propulsion/rules.py` (D5). Every expected figure is computed here from the published
constants in `domains/propulsion/components.yaml#components`, not from the states' copies, and the
relaxations are checked against the closed form `F (1 - exp(-t / tau))` rather than re-run.

Nothing in the plant moves an engine to `ignition` or `mainstage` yet (`start_burn` stages no state),
so these tests put an engine's state there directly and run the real step loop from it.
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
_PROP = yaml.safe_load((VEHICLE / "domains/propulsion/components.yaml").read_text())
COMPONENTS = {row["id"]: row for row in _PROP["components"]}
STATES = {row["id"]: row for row in _PROP["state"]}
SPS_N = COMPONENTS["sps"]["thrust_n"]
APS_N = COMPONENTS["aps"]["thrust_n"]
RULED = ("thrust_main_n", "chamber_pressure_pct", "pressurant_pressure_psi", "feed_pressure_pct")
_CONSUMABLES = yaml.safe_load((VEHICLE / "domains/consumables/components.yaml").read_text())
HELIUM = next(row for row in _CONSUMABLES["state"] if row["id"] == "pressurant_he_kg")
_COUPLING = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
PRESS_EDGE = next(edge for edge in _COUPLING["edges"] if edge["id"] == "E-PRESS-PROP")
REGULATED = COMPONENTS["pressurant_regulator"]["working_psia"]


@pytest.fixture(scope="module")
def world() -> plant.World:
    return plant.load_world(VEHICLE)


def run(world, values, ticks):
    """The real step loop, `ticks` times; returns the values and the propulsion rules' gaps."""
    gaps: list[plant.Gap] = []
    for _ in range(ticks):
        tick_gaps: list[plant.Gap] = []
        values = plant.step(world, values, DT, tick_gaps)
        gaps.extend(g for g in tick_gaps if g.state.id in RULED)
    return values, gaps


def firing(world, **engines):
    values = plant.initial_values(world)
    for engine, state in engines.items():
        values[f"{engine}_state"] = state
    return values


def test_the_rules_copies_of_the_rated_thrusts_agree_with_the_engines_own_figures():
    for state in RULED[:2]:
        assert STATES[state]["rated_thrust_n"] == {"sps": SPS_N, "aps": APS_N}, state
        assert STATES[state]["engine_states"] == {
            "sps": "sps_state",
            "dps": "dps_state",
            "aps": "aps_state",
        }, state
    # The DPS is absent on purpose: its thrust at a throttle setting is the owed curve.
    assert "dps" not in STATES["thrust_main_n"]["rated_thrust_n"]


def test_with_no_engine_firing_thrust_and_chamber_pressure_hold_at_zero(world):
    values, gaps = run(world, plant.initial_values(world), 50)
    assert not gaps, [(g.state.id, g.owed) for g in gaps]
    assert values["thrust_main_n"] == 0.0
    assert values["chamber_pressure_pct"] == 0.0


def test_an_sps_in_mainstage_builds_to_its_rated_thrust_with_the_half_second_constant(world):
    ticks = 50  # 1 s, two time constants
    values, gaps = run(world, firing(world, sps="mainstage"), ticks)
    assert not gaps, [(g.state.id, g.owed) for g in gaps]
    tau = STATES["thrust_main_n"]["tau_s"]
    assert values["thrust_main_n"] == pytest.approx(SPS_N * (1 - math.exp(-ticks * DT / tau)))
    values, _ = run(world, values, 500)  # 10 s more: settled
    assert values["thrust_main_n"] == pytest.approx(SPS_N, rel=1e-9)
    assert values["chamber_pressure_pct"] == pytest.approx(100.0, rel=1e-6)


def test_chamber_pressure_follows_thrust_rather_than_leading_it(world):
    """Two lags in series: the chamber relaxes toward `100 x F / F_rated` while `F` is still rising,
    so it sits below the thrust's own fraction during the build-up and meets it once both settle."""
    values, _ = run(world, firing(world, aps="ignition"), 10)
    fraction = 100.0 * values["thrust_main_n"] / APS_N
    assert 0.0 < values["chamber_pressure_pct"] < fraction


def test_shutdown_tails_thrust_off_toward_zero(world):
    values, _ = run(world, firing(world, sps="mainstage"), 600)
    values["sps_state"] = "shutdown"
    values, gaps = run(world, values, 50)
    assert not gaps
    tau = STATES["thrust_main_n"]["tau_s"]
    assert values["thrust_main_n"] == pytest.approx(SPS_N * math.exp(-50 * DT / tau), rel=1e-6)


def test_a_firing_descent_engine_is_a_gap_because_its_throttle_law_is_owed(world):
    _, gaps = run(world, firing(world, dps="mainstage"), 1)
    owed = {g.state.id: g.owed for g in gaps}
    assert set(owed) == set(RULED[:2])
    assert "thrust_curve" in owed["thrust_main_n"]


def test_two_engines_firing_at_once_is_a_gap_and_not_a_sum(world):
    _, gaps = run(world, firing(world, sps="mainstage", aps="mainstage"), 1)
    assert {g.state.id for g in gaps} == set(RULED[:2])
    assert all("all firing" in g.owed for g in gaps)


def test_thrust_now_reaches_the_delta_v_accumulator(world):
    """`accumulated_dv_m_s` is driven by `thrust_main_n`, which until these rules no tick advanced.
    Over a settled SPS burn the accumulator gains `F t / m` at the declared configuration mass."""
    values, _ = run(world, firing(world, sps="mainstage"), 600)
    start = values["accumulated_dv_m_s"]
    values, _ = run(world, values, 500)
    mass = STATES["accumulated_dv_m_s"]["mass_kg"]
    assert values["accumulated_dv_m_s"] - start == pytest.approx(SPS_N * 500 * DT / mass, rel=1e-3)


# --- the SPS's helium pressurization ---------------------------------------------------------


def test_the_pressurization_rules_copies_agree_with_their_homes():
    tank, feed = STATES["pressurant_pressure_psi"], STATES["feed_pressure_pct"]
    assert tank["regulator_psia"] == REGULATED
    assert feed["nominal_psia"] == REGULATED
    assert tank["bottle_fill_psia"] == COMPONENTS["helium_bottles"]["fill_psia"]
    assert tank["bottle_fill_kg"] == HELIUM["initial"]
    assert tank["helium_state"] == "pressurant_he_kg"
    # The feed's initial is a derived figure the linter does not evaluate on a `dynamics` state.
    assert feed["initial"] == pytest.approx(100.0 * tank["initial"] / REGULATED, rel=1e-12)


def test_the_helium_a_newton_spends_re_derives_by_another_route():
    """The edge's figure is a density times a volume over `Isp g0`. Here it is the gas law with the
    textbook helium constant (2,077.1 J/kg K) and the propellant volume summed per component."""
    prop = COMPONENTS["sps_propellants"]
    t_c = (prop["reference_temperature_f"] - 32) * 5 / 9
    rho_he = REGULATED * 6894.757 / (2077.1 * (t_c + 273.15))
    r = prop["mixture_ratio"]
    rho_ox = 1000 * (
        prop["oxidizer_density_g_cc"]["at_0_c"] - prop["oxidizer_density_g_cc"]["per_c"] * t_c
    )
    rho_fu = 1000 * (prop["fuel_density_g_cc"]["at_0_c"] - prop["fuel_density_g_cc"]["per_c"] * t_c)
    m3_per_kg = (r / (1 + r)) / rho_ox + (1 / (1 + r)) / rho_fu
    isp = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())["propulsion"]["sps"]["isp_s"]
    per_newton = rho_he * m3_per_kg / (isp * 9.80665)
    assert PRESS_EDGE["sensitivity"]["value"] == pytest.approx(per_newton, rel=1e-4)
    # And the load closes with helium to spare: the full SPS load expels less than the bottles hold.
    sps_kg = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())["propulsion"]["sps"]["mass_kg"]
    assert rho_he * m3_per_kg * sps_kg < HELIUM["initial"]


def test_between_burns_the_tanks_hold_and_no_helium_is_spent(world):
    start = plant.initial_values(world)
    values, gaps = run(world, start, 200)
    assert not gaps, [(g.state.id, g.owed) for g in gaps]
    assert values["pressurant_pressure_psi"] == STATES["pressurant_pressure_psi"]["initial"]
    assert values["feed_pressure_pct"] == pytest.approx(STATES["feed_pressure_pct"]["initial"])
    assert values["pressurant_he_kg"] == pytest.approx(start["pressurant_he_kg"], abs=1e-9)


def test_an_sps_burn_brings_the_tanks_up_to_the_regulated_pressure_and_the_feed_to_100(world):
    ticks = 250  # 5 s, one ullage time constant
    values, gaps = run(world, firing(world, sps="mainstage"), ticks)
    assert not gaps, [(g.state.id, g.owed) for g in gaps]
    tau = STATES["pressurant_pressure_psi"]["tau_s"]
    p0 = STATES["pressurant_pressure_psi"]["initial"]
    expected = REGULATED + (p0 - REGULATED) * math.exp(-ticks * DT / tau)
    assert values["pressurant_pressure_psi"] == pytest.approx(expected, rel=1e-9)
    values, _ = run(world, values, 1500)  # 30 s more
    assert values["pressurant_pressure_psi"] == pytest.approx(REGULATED, rel=1e-4)
    assert values["feed_pressure_pct"] == pytest.approx(100.0, rel=1e-4)


def test_a_settled_sps_burn_drains_the_bottles_at_the_edges_rate(world):
    values, _ = run(world, firing(world, sps="mainstage"), 600)
    start = values["pressurant_he_kg"]
    values, _ = run(world, values, 500)
    spent = start - values["pressurant_he_kg"]
    assert spent == pytest.approx(PRESS_EDGE["sensitivity"]["value"] * SPS_N * 500 * DT, rel=1e-3)


def test_an_ascent_engine_burn_does_not_pressurize_the_sps_tanks(world):
    values, gaps = run(world, firing(world, aps="mainstage"), 250)
    assert not gaps
    assert values["pressurant_pressure_psi"] == STATES["pressurant_pressure_psi"]["initial"]


def test_bottles_below_the_regulator_blow_the_tanks_down_to_the_sps_press_light(world):
    """With the bottles at 150 psia the regulator is wide open and the tanks follow the bottles, below
    `pressurant_low`'s 157 psia: the light a leaking helium system ends a burn on."""
    values = firing(world, sps="mainstage")
    values["pressurant_he_kg"] = (
        HELIUM["initial"] * 150.0 / COMPONENTS["helium_bottles"]["fill_psia"]
    )
    values, gaps = run(world, values, 2000)
    assert not gaps
    light = next(
        t
        for t in yaml.safe_load((VEHICLE / "domains/propulsion/profiles.yaml").read_text())[
            "thresholds"
        ]
        if t["id"] == "pressurant_low"
    )["assert"]
    assert values["pressurant_pressure_psi"] < light
    assert values["feed_pressure_pct"] < 100.0 * light / REGULATED
