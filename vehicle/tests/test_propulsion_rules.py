"""The propulsion rules: main-engine thrust from the firing engine, and the chamber pressure behind it.

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
RULED = ("thrust_main_n", "chamber_pressure_pct")


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
    for state in RULED:
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
    assert set(owed) == set(RULED)
    assert "thrust_curve" in owed["thrust_main_n"]


def test_two_engines_firing_at_once_is_a_gap_and_not_a_sum(world):
    _, gaps = run(world, firing(world, sps="mainstage", aps="mainstage"), 1)
    assert {g.state.id for g in gaps} == set(RULED)
    assert all("all firing" in g.owed for g in gaps)


def test_thrust_now_reaches_the_delta_v_accumulator(world):
    """`accumulated_dv_m_s` is driven by `thrust_main_n`, which until these rules no tick advanced.
    Over a settled SPS burn the accumulator gains `F t / m` at the declared configuration mass."""
    values, _ = run(world, firing(world, sps="mainstage"), 600)
    start = values["accumulated_dv_m_s"]
    values, _ = run(world, values, 500)
    mass = STATES["accumulated_dv_m_s"]["mass_kg"]
    assert values["accumulated_dv_m_s"] - start == pytest.approx(SPS_N * 500 * DT / mass, rel=1e-3)
