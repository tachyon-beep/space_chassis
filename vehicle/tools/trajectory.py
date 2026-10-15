#!/usr/bin/env python3
"""The translational truth: where the vehicle is, under the Earth's and the Moon's gravity.

`apollo_diode.md:743` asks for "Earth and Moon in a rigid-body 6-DOF integration" and `plant.md` §3
gives the translational half "semi-implicit/Verlet in coast, RK4 in burns". This module is that half,
and it is also the arithmetic that produced the state vector the integration starts from, because
those two have to be the same model: a start state designed in one gravity field and flown in
another is a trajectory that misses.

**The model.** Two point masses and the vehicle, in `EARTH_J2000` (`vehicle.yaml#frames`), with the
vehicle's acceleration

    a = -mu_E r / |r|^3  -  mu_M (r - r_M) / |r - r_M|^3  -  mu_M r_M / |r_M|^3

where the last term is the indirect one: the frame is centred on the Earth, and the Earth is itself
accelerated toward the Moon. The Moon moves on its own two-body orbit about the Earth with
`mu_E + mu_M`, seeded from the recorded JPL Horizons vector (`mission.yaml#initial_state.
lunar_ephemeris_at_arrival`). That is a Keplerian Moon rather than DE441: over a nine-day mission
the solar perturbation moves the real Moon by a few hundred kilometres from the conic, which shifts
*where* the free return passes and not *whether* it does, and it keeps the vehicle independent of
an ephemeris file the repository does not carry.

**Why the start state is designed rather than declared.** `mission.yaml`'s osculating elements
were solved as a conic that reaches the Moon's *centre* at MET 73 h, and that conic, flown under the
Moon's gravity, strikes the surface about three hours early: both mirror planes the elements left
open do. A transfer that reaches the Moon has to be aimed past it, and the aim point is what
`design()` solves for, under the mission's own constraints. `mission.yaml` records the result and
the targets, and `check_free_return` in the linter re-flies the recorded vector against them.

Units inside this module are SI (m, m/s, s). The configuration speaks km and km/s where its sources
do, and the conversions happen at the boundary, once.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

import yaml

Vec = list[float]

# The Verlet step the plant takes is the tick (20 ms at 50 Hz); the design propagates the same
# equations with RK4 at a coarser step, because a nine-day flight at 50 Hz is 39 million steps. The
# two are held together by `check_free_return`, which flies the recorded vector with the design
# integrator, and by `test_the_plant_and_the_design_agree_on_a_coast`, which flies an hour both ways.
DESIGN_STEP_S = 30.0
# Near either body the field changes fast enough that a 30 s RK4 step costs metres per step. Inside
# these radii the design steps at 5 s.
NEAR_MOON_M = 60_000e3
NEAR_EARTH_M = 20_000e3
NEAR_STEP_S = 5.0


def _add(a: Vec, b: Vec, scale: float = 1.0) -> Vec:
    return [a[0] + scale * b[0], a[1] + scale * b[1], a[2] + scale * b[2]]


def _norm(a: Vec) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _cross(a: Vec, b: Vec) -> Vec:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _point_mass(r: Vec, mu: float) -> Vec:
    n = _norm(r)
    k = -mu / (n * n * n)
    return [k * r[0], k * r[1], k * r[2]]


class Gravity:
    """The two gravitational parameters, read from `vehicle.yaml#environment` and nowhere else."""

    def __init__(self, mu_earth: float, mu_moon: float) -> None:
        self.mu_earth = float(mu_earth)
        self.mu_moon = float(mu_moon)

    @classmethod
    def from_vehicle(cls, vehicle: dict[str, Any]) -> Gravity:
        env = {row.get("id"): row.get("value") for row in vehicle.get("environment") or []}
        return cls(env["gravity_earth_mu"], env["gravity_moon_mu"])

    def vehicle(self, r: Vec, moon: Vec) -> Vec:
        """The vehicle's acceleration in the Earth-centred frame, the indirect term included."""
        direct = _add(_point_mass(r, self.mu_earth), _point_mass(_add(r, moon, -1.0), self.mu_moon))
        # The Earth falls toward the Moon at mu_M / |r_M|^2; the frame falls with it.
        return _add(direct, _point_mass(moon, self.mu_moon))

    def moon(self, moon: Vec) -> Vec:
        """The Moon about the Earth: the relative two-body problem, so the sum of the parameters."""
        return _point_mass(moon, self.mu_earth + self.mu_moon)


def verlet(
    gravity: Gravity, r: Vec, v: Vec, moon_r: Vec, moon_v: Vec, dt: float, thrust: Vec | None = None
) -> tuple[Vec, Vec, Vec, Vec]:
    """One velocity-Verlet (kick-drift-kick) step of the vehicle and the Moon together.

    Symplectic, so a coast's energy error stays bounded rather than drifting, which is the property
    `plant.md` §3 asks for and forward Euler lacks (+1.06 % in semi-major axis over eight days).
    `thrust` is an acceleration held constant over the step and is added to both half-kicks.
    """
    extra = thrust or [0.0, 0.0, 0.0]
    a = _add(gravity.vehicle(r, moon_r), extra)
    am = gravity.moon(moon_r)
    half = 0.5 * dt
    v_half = _add(v, a, half)
    mv_half = _add(moon_v, am, half)
    r_new = _add(r, v_half, dt)
    m_new = _add(moon_r, mv_half, dt)
    a_new = _add(gravity.vehicle(r_new, m_new), extra)
    am_new = gravity.moon(m_new)
    return r_new, _add(v_half, a_new, half), m_new, _add(mv_half, am_new, half)


def rk4(
    gravity: Gravity, r: Vec, v: Vec, moon_r: Vec, moon_v: Vec, dt: float
) -> tuple[Vec, Vec, Vec, Vec]:
    """One classical RK4 step of the same twelve equations, for the design's long propagations."""

    def deriv(s: list[Vec]) -> list[Vec]:
        return [s[1], gravity.vehicle(s[0], s[2]), s[3], gravity.moon(s[2])]

    s0 = [r, v, moon_r, moon_v]
    k1 = deriv(s0)
    k2 = deriv([_add(s0[i], k1[i], dt / 2) for i in range(4)])
    k3 = deriv([_add(s0[i], k2[i], dt / 2) for i in range(4)])
    k4 = deriv([_add(s0[i], k3[i], dt) for i in range(4)])
    out = [
        [s0[i][j] + dt / 6 * (k1[i][j] + 2 * k2[i][j] + 2 * k3[i][j] + k4[i][j]) for j in range(3)]
        for i in range(4)
    ]
    return out[0], out[1], out[2], out[3]


def moon_two_body(gravity: Gravity, moon_r: Vec, moon_v: Vec, seconds: float) -> tuple[Vec, Vec]:
    """The Moon carried `seconds` along its conic (negative is backward), by RK4 at 60 s."""
    steps = max(1, math.ceil(abs(seconds) / 60.0))
    h = seconds / steps
    mu = gravity.mu_earth + gravity.mu_moon

    def deriv(s: list[Vec]) -> list[Vec]:
        return [s[1], _point_mass(s[0], mu)]

    r, v = list(moon_r), list(moon_v)
    for _ in range(steps):
        s0 = [r, v]
        k1 = deriv(s0)
        k2 = deriv([_add(s0[i], k1[i], h / 2) for i in range(2)])
        k3 = deriv([_add(s0[i], k2[i], h / 2) for i in range(2)])
        k4 = deriv([_add(s0[i], k3[i], h) for i in range(2)])
        r, v = (
            [
                s0[i][j] + h / 6 * (k1[i][j] + 2 * k2[i][j] + 2 * k3[i][j] + k4[i][j])
                for j in range(3)
            ]
            for i in range(2)
        )
    return r, v


def elements_to_state(
    mu: float, a: float, e: float, i_deg: float, raan_deg: float, argp_deg: float, nu_deg: float
) -> tuple[Vec, Vec]:
    """Classical elements (SI) to a position and velocity in the elements' own frame."""
    i, om, w, nu = (math.radians(x) for x in (i_deg, raan_deg, argp_deg, nu_deg))
    p = a * (1.0 - e * e)
    rmag = p / (1.0 + e * math.cos(nu))
    h = math.sqrt(mu * p)
    co, so, ci, si, cw, sw = (
        math.cos(om),
        math.sin(om),
        math.cos(i),
        math.sin(i),
        math.cos(w),
        math.sin(w),
    )

    def rot(x: float, y: float) -> Vec:
        return [
            (co * cw - so * sw * ci) * x + (-co * sw - so * cw * ci) * y,
            (so * cw + co * sw * ci) * x + (-so * sw + co * cw * ci) * y,
            (sw * si) * x + (cw * si) * y,
        ]

    return (
        rot(rmag * math.cos(nu), rmag * math.sin(nu)),
        rot(-mu / h * math.sin(nu), mu / h * (e + math.cos(nu))),
    )


def flyby(
    gravity: Gravity,
    r: Vec,
    v: Vec,
    moon_r: Vec,
    moon_v: Vec,
    *,
    moon_radius_m: float,
    earth_radius_m: float,
    max_seconds: float = 9 * 86400.0,
) -> dict[str, float]:
    """Fly a coast from MET 0 and report the three numbers a free return is judged by.

    `periselene_alt_km` and `periselene_met_h` are the closest approach to the Moon and when it
    happens. `return_perigee_alt_km` is the vacuum perigee of the osculating Earth conic thirty hours
    after the flyby, outside the Moon's sphere of influence: a smooth function of the start state,
    where "the lowest altitude reached" is not (it jumps when the vehicle grazes the Earth). Negative
    means the return conic intersects the Earth, which is what an entry is.
    """
    t = 0.0
    closest, closest_t = math.inf, 0.0
    past = False
    while t < max_seconds:
        near = _norm(_add(r, moon_r, -1.0)) < NEAR_MOON_M or _norm(r) < NEAR_EARTH_M
        h = NEAR_STEP_S if near else DESIGN_STEP_S
        r, v, moon_r, moon_v = rk4(gravity, r, v, moon_r, moon_v, h)
        t += h
        d = _norm(_add(r, moon_r, -1.0))
        if not past:
            if d < closest:
                closest, closest_t = d, t
            elif d > closest + 5_000e3:
                past = True
        elif t > closest_t + 30 * 3600.0:
            rr, vv = _norm(r), _norm(v)
            energy = vv * vv / 2.0 - gravity.mu_earth / rr
            a = -gravity.mu_earth / (2.0 * energy)
            p = _norm(_cross(r, v)) ** 2 / gravity.mu_earth
            e = math.sqrt(max(0.0, 1.0 - p / a))
            return {
                "periselene_alt_km": (closest - moon_radius_m) / 1e3,
                "periselene_met_h": closest_t / 3600.0,
                "return_perigee_alt_km": (a * (1.0 - e) - earth_radius_m) / 1e3,
            }
    raise RuntimeError("the flight never left the Moon's neighbourhood: no return to judge")


# --- the configuration boundary ---------------------------------------------------------------


def load(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    vehicle = yaml.safe_load((root / "vehicle.yaml").read_text(encoding="utf-8"))
    mission = yaml.safe_load((root / "mission.yaml").read_text(encoding="utf-8"))
    return vehicle, mission


def environment_value(vehicle: dict[str, Any], key: str) -> float:
    for row in vehicle.get("environment") or []:
        if row.get("id") == key:
            return float(row["value"])
    raise KeyError(key)


def moon_at_met0(vehicle: dict[str, Any], mission: dict[str, Any]) -> tuple[Vec, Vec]:
    """The Moon at MET 0, carried back along its conic from the recorded ephemeris epoch."""
    eph = mission["initial_state"]["lunar_ephemeris_at_arrival"]
    r = [x * 1e3 for x in eph["position_km"]]
    v = [x * 1e3 for x in eph["velocity_km_s"]]
    return moon_two_body(Gravity.from_vehicle(vehicle), r, v, -float(eph["epoch_met_h"]) * 3600.0)


def declared_start(mission: dict[str, Any]) -> tuple[Vec, Vec] | None:
    """`initial_state`'s position and velocity in SI, or None while either is unset."""
    state = mission["initial_state"]
    pos, vel = state.get("position_xyz_km"), state.get("velocity_xyz_m_s")
    if not isinstance(pos, list) or not isinstance(vel, list):
        return None
    return [float(x) * 1e3 for x in pos], [float(x) for x in vel]


def fly_declared(root: Path) -> dict[str, float]:
    return fly(*load(root))


def fly(vehicle: dict[str, Any], mission: dict[str, Any]) -> dict[str, float]:
    """The declared start vector flown under both bodies' gravity: what `check_free_return` holds."""
    start = declared_start(mission)
    if start is None:
        raise ValueError("mission.yaml#initial_state declares no position and velocity")
    moon_r, moon_v = moon_at_met0(vehicle, mission)
    return flyby(
        Gravity.from_vehicle(vehicle),
        start[0],
        start[1],
        moon_r,
        moon_v,
        moon_radius_m=environment_value(vehicle, "moon_mean_radius_km") * 1e3,
        earth_radius_m=environment_value(vehicle, "earth_equatorial_radius_km") * 1e3,
    )


def designed_start(mission: dict[str, Any], mu_earth: float) -> tuple[Vec, Vec]:
    """The start vector the recorded design figures produce, in SI: what the declared one must be."""
    state = mission["initial_state"]
    osc = state["osculating_elements"]
    scale = float(state["free_return_design"]["solution"]["speed_scale"])
    return _start(
        mu_earth,
        osc,
        float(osc["right_ascension_of_ascending_node_deg"]),
        float(osc["argument_of_perigee_deg"]),
        scale,
    )


# --- the design ----------------------------------------------------------------------------------


def _start(
    mu: float, osc: dict[str, Any], raan: float, argp: float, speed_scale: float
) -> tuple[Vec, Vec]:
    r, v = elements_to_state(
        mu,
        float(osc["semi_major_axis_km"]) * 1e3,
        float(osc["eccentricity"]),
        float(osc["inclination_deg"]),
        raan,
        argp,
        float(osc["true_anomaly_at_cutoff_deg"]),
    )
    return r, [x * speed_scale for x in v]


def design(root: Path, *, verbose: bool = True) -> dict[str, Any]:
    """Solve the free-return start state from `mission.yaml#initial_state.free_return_design`.

    Three controls move off the declared conic: the node, the argument of perigee and a scale on the
    perigee speed. The inclination and the perigee radius stay the parking orbit's. Three targets
    pin them: the closest approach to the Moon at `arrival_at_moon_h`, a return conic whose vacuum
    perigee is `return_perigee_alt_km` (the entry corridor's), and, of the one-parameter family of
    free returns those two leave, the one whose pericynthion is lowest, since that is the one the
    lunar-orbit insertion has least to correct. Slow: minutes of pure-Python propagation.
    """
    vehicle, mission = load(root)
    gravity = Gravity.from_vehicle(vehicle)
    osc = mission["initial_state"]["osculating_elements"]
    spec = mission["initial_state"]["free_return_design"]
    t_arrival = float(osc["arrival_at_moon_h"])
    return_alt = float(spec["return_perigee_alt_km"])
    moon_r, moon_v = moon_at_met0(vehicle, mission)
    kw = {
        "moon_radius_m": environment_value(vehicle, "moon_mean_radius_km") * 1e3,
        "earth_radius_m": environment_value(vehicle, "earth_equatorial_radius_km") * 1e3,
    }

    def fly(raan: float, argp: float, scale: float) -> dict[str, float]:
        r, v = _start(gravity.mu_earth, osc, raan, argp, scale)
        return flyby(gravity, r, v, moon_r, moon_v, **kw)

    def arrive(
        raan: float, argp: float, scale: float, alt: float
    ) -> tuple[float, float, dict[str, float]]:
        """Newton on (argp, scale) for a pericynthion of `alt` km at the arrival time."""
        for _ in range(20):
            got = fly(raan, argp, scale)
            ra = got["periselene_alt_km"] - alt
            rt = got["periselene_met_h"] - t_arrival
            # A metre of pericynthion is about 0.1 km of return perigee, so the arrival is solved
            # to two metres: the bisection above it cannot see a target finer than this one.
            if abs(ra) < 0.002 and abs(rt) < 0.001:
                return argp, scale, got
            dw, ds = 0.002, 2e-6
            gw, gs = fly(raan, argp + dw, scale), fly(raan, argp, scale + ds)
            j = [
                [
                    (gw["periselene_alt_km"] - got["periselene_alt_km"]) / dw,
                    (gs["periselene_alt_km"] - got["periselene_alt_km"]) / ds,
                ],
                [
                    (gw["periselene_met_h"] - got["periselene_met_h"]) / dw,
                    (gs["periselene_met_h"] - got["periselene_met_h"]) / ds,
                ],
            ]
            det = j[0][0] * j[1][1] - j[0][1] * j[1][0]
            argp += max(-0.2, min(0.2, (-ra * j[1][1] + rt * j[0][1]) / det))
            scale += max(-5e-5, min(5e-5, (-j[0][0] * rt + j[1][0] * ra) / det))
        raise RuntimeError(f"no arrival at {alt} km and {t_arrival} h from node {raan}")

    def free_return(
        raan: float, argp: float, scale: float
    ) -> tuple[float, float, float, dict[str, float]]:
        """Bisect the pericynthion for the return perigee; the return falls as the pericynthion rises."""
        lo, hi = float(spec["search_periselene_km"][0]), float(spec["search_periselene_km"][1])
        got: dict[str, float] = {}
        alt = lo
        for _ in range(30):
            alt = (lo + hi) / 2
            argp, scale, got = arrive(raan, argp, scale, alt)
            miss = got["return_perigee_alt_km"] - return_alt
            if verbose:
                print(
                    f"  node {raan:.4f}  pericynthion {alt:9.3f} km  return {got['return_perigee_alt_km']:10.3f} km",
                    flush=True,
                )
            if abs(miss) < 1.0:
                return argp, scale, alt, got
            lo, hi = (alt, hi) if miss > 0 else (lo, alt)
        raise RuntimeError(f"no free return from node {raan}")

    # The lowest pericynthion of the family: three nodes bracketing it, the vertex of the parabola
    # through them, and the free return solved at the vertex. A golden-section search reaches the
    # same node to the same tolerance in ten solves rather than four, and each solve is minutes.
    argp, scale = float(spec["seed_argument_of_perigee_deg"]), float(spec["seed_speed_scale"])
    nodes = [float(x) for x in spec["bracket_node_deg"]]
    heights = []
    for node in nodes:
        argp, scale, alt, _ = free_return(node, argp, scale)
        heights.append(alt)
    (x0, x1, x2), (y0, y1, y2) = nodes, heights
    denom = (x0 - x1) * (x0 - x2) * (x1 - x2)
    qa = (x2 * (y1 - y0) + x1 * (y0 - y2) + x0 * (y2 - y1)) / denom
    qb = (x2 * x2 * (y0 - y1) + x1 * x1 * (y2 - y0) + x0 * x0 * (y1 - y2)) / denom
    if qa <= 0:
        raise RuntimeError(f"the bracket {nodes} does not hold a minimum: {heights}")
    node = round(-qb / (2 * qa), 4)
    argp, scale, alt, got = free_return(node, argp, scale)
    r, v = _start(gravity.mu_earth, osc, node, argp, scale)
    return {
        "right_ascension_of_ascending_node_deg": node,
        "argument_of_perigee_deg": argp,
        "speed_scale": scale,
        "position_xyz_km": [x / 1e3 for x in r],
        "velocity_xyz_m_s": v,
        "flyby": got,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--dir", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument(
        "--design", action="store_true", help="re-solve the free-return start state (slow)"
    )
    args = parser.parse_args(argv)
    root = Path(args.dir)
    if args.design:
        out = design(root)
        for key, value in out.items():
            print(f"{key}: {value}")
        return 0
    got = fly_declared(root)
    for key, value in got.items():
        print(f"{key}: {value:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
