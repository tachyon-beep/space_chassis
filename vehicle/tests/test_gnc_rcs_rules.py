"""The pointing modes behind `set_attitude_target` (ADR 0005): the slew law, the rigid body it
flies, and what each costs in propellant.

The rules are exercised two ways. Directly, for the arithmetic that has a closed-form answer (a
torque-free spin keeps its energy and momentum, the hold's limit cycle costs ten times as much at
0.5 deg as at 5 deg, a malformed quaternion is refused). And through the real step loop, for the
one claim that only the loop can make: a commanded slew reaches its target and the tank pays for
it. The vectors are seeded through a scenario overlay because the plant seeds only scalar
`dynamics` initials until #47 lands, and the commanded quaternion is written as its effect will
write it until the engine carries array arguments.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402

DT = 0.02


def _rules(domain: str):
    spec = importlib.util.spec_from_file_location(
        f"_{domain}_rules_under_test", VEHICLE / "domains" / domain / "rules.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GNC = _rules("gnc")
RCS = _rules("rcs")


@pytest.fixture(scope="module")
def world() -> plant.World:
    return plant.load_world(VEHICLE)


def _spec(world, state_id):
    return next(s for s in world.states if s.id == state_id).spec


def _state(world, state_id):
    return next(s for s in world.states if s.id == state_id)


def _level(world, values, state_id):
    state = next(s for s in world.states if s.id == state_id)
    return plant.state_level(values, state)


def _qmul(p, q):
    return (
        p[0] * q[0] - p[1] * q[1] - p[2] * q[2] - p[3] * q[3],
        p[0] * q[1] + p[1] * q[0] + p[2] * q[3] - p[3] * q[2],
        p[0] * q[2] - p[1] * q[3] + p[2] * q[0] + p[3] * q[1],
        p[0] * q[3] + p[1] * q[2] - p[2] * q[1] + p[3] * q[0],
    )


def test_a_torque_free_spin_keeps_its_energy_and_momentum(world):
    """The PTC roll on the docked stack: 0.3 deg/s about +X, which is not a principal axis, so the
    rate cones. The midpoint step must not pump energy into it over a long coast."""
    params = _spec(world, "body_rate")
    inertia = GNC.inertia_tensor(params)
    rate = [0.3, 0.0, 0.0]

    def invariants(r):
        w = tuple(math.radians(c) for c in r)
        h = GNC._apply(inertia, w)
        return 0.5 * sum(a * b for a, b in zip(w, h, strict=True)), math.sqrt(sum(c * c for c in h))

    energy0, momentum0 = invariants(rate)
    for _ in range(30_000):  # ten minutes of coast
        rate = GNC._body_rate({"body_rate": rate, "control_torque": [0.0, 0.0, 0.0]}, params, DT)
    energy, momentum = invariants(rate)
    assert abs(energy / energy0 - 1.0) < 1e-6
    assert abs(momentum / momentum0 - 1.0) < 1e-6
    # And it does cone: the products of inertia move rate off the roll axis.
    assert abs(rate[1]) + abs(rate[2]) > 1e-4


def test_the_hold_costs_ten_times_as_much_at_half_a_degree_as_at_five(world):
    params = _spec(world, "thruster_thrust")
    narrow = sum(RCS._hold_cycle_pulse_rate_hz(params, math.radians(0.5)))
    wide = sum(RCS._hold_cycle_pulse_rate_hz(params, math.radians(5.0)))
    assert narrow / wide == pytest.approx(10.0)


@pytest.mark.parametrize(
    "text", ["", "current-ish", "[1, 0, 0]", "[1, 0, 0, 0, 0]", "[2, 0, 0, 0]", "[a, b, c, d]"]
)
def test_a_quaternion_that_is_not_four_numbers_of_unit_length_is_refused(text):
    assert RCS.parse_quaternion(text) is None


def test_a_unit_quaternion_is_read_in_any_bracketing():
    for text in ("[1, 0, 0, 0]", "(1,0,0,0)", "1, 0, 0, 0", "[0.999, 0, 0, 0]"):
        q = RCS.parse_quaternion(text)
        assert q is not None and q[0] == pytest.approx(1.0)


def _seeded(world):
    initial = {k: _spec(world, k)["initial"] for k in ("attitude", "body_rate", "held_target")}
    initial["impulse_total"] = 0.0
    return plant.initial_values(world, plant.Scenario(name="gnc_rcs_fixture", initial=initial))


def _apply(values, delta):
    for key, value in delta.items():
        if key == "internal":
            values["internal"] = {**values["internal"], **value}
        else:
            values[key] = value


def test_a_commanded_slew_reaches_its_target_and_the_tank_pays_for_it(world):
    values = _seeded(world)
    start = _level(world, values, "attitude")
    half = math.radians(10.0) / 2
    target = _qmul(start, (math.cos(half), 0.0, math.sin(half), 0.0))  # 10 deg about pitch
    _apply(
        values,
        plant.apply_command(
            world,
            values,
            "set_attitude_target",
            {
                "frame": "EARTH_J2000",
                "quaternion": "[" + ",".join(repr(c) for c in target) + "]",
                "rate_limit_deg_s": "0.5",
            },
        ),
    )
    # The window cannot carry the quaternion into the state yet (an array argument, owed to the
    # engine after #47), so the test writes what the effect will write.
    target_text = "[" + ",".join(repr(c) for c in target) + "]"
    _apply(values, plant.state_values(world, _state(world, "attitude_target"), target_text))
    tank = _level(world, values, "prop_rcs_kg")
    peak = 0.0
    for _ in range(int(30 / DT)):
        values = plant.step(world, values, DT, [])
        peak = max(peak, abs(_level(world, values, "body_rate")[1]))
    # Flown at the commanded rate, never faster.
    assert peak == pytest.approx(0.5, abs=0.01)
    assert _level(world, values, "attitude_error") < 0.05
    spent = tank - _level(world, values, "prop_rcs_kg")
    # Spin up and spin down: 2 x I w / (arm Isp g0), with the -7.25 deg quad offset putting yaw
    # couples to work beside the pitch ones. About 1.35 kg each way on the docked stack.
    assert 2.4 < spent < 3.0


def test_the_thermal_roll_spins_up_then_drifts_free_with_the_sun_across_the_roll_axis(world):
    values = _seeded(world)
    _apply(values, plant.apply_command(world, values, "set_ptc_roll", {"rate_deg_s": "0.3"}))
    for _ in range(int(10 / DT)):
        values = plant.step(world, values, DT, [])
    assert _level(world, values, "body_rate")[0] == pytest.approx(0.3, abs=0.001)
    _apply(values, plant.apply_command(world, values, "set_rcs_mode", {"mode": "free_drift"}))
    tank = _level(world, values, "prop_rcs_kg")
    sun = []
    for _ in range(int(60 / DT)):
        values = plant.step(world, values, DT, [])
        sun.append(_level(world, values, "sun_direction_body"))
    # Free drift is free, and the roll axis sits on the ecliptic pole, so the Sun stays across it
    # while it turns about it: 18 degrees in a minute at 0.3 deg/s.
    assert _level(world, values, "prop_rcs_kg") == tank
    assert max(abs(s[0]) for s in sun) < 0.05
    turned = math.degrees(math.atan2(sun[-1][2], sun[-1][1]) - math.atan2(sun[0][2], sun[0][1]))
    assert abs(turned) == pytest.approx(18.0, abs=0.5)


def test_ending_the_roll_holds_where_the_vehicle_is_rather_than_turning_back(world):
    values = _seeded(world)
    _apply(values, plant.apply_command(world, values, "set_ptc_roll", {"rate_deg_s": "0.3"}))
    for _ in range(int(60 / DT)):
        values = plant.step(world, values, DT, [])
    _apply(values, plant.apply_command(world, values, "set_ptc_roll", {"rate_deg_s": "0.0"}))
    for _ in range(int(20 / DT)):
        values = plant.step(world, values, DT, [])
    assert max(abs(w) for w in _level(world, values, "body_rate")) < 0.001
    assert _level(world, values, "attitude_error") < 0.5
