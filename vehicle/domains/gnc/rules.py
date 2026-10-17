"""The GNC domain's rules (D5): the vehicle's rotational truth, as a rigid body.

Pointing modes, not 6-DOF (the arc review, decision 5; ADR 0005): the RCS service decides a torque
(`rcs.control_torque`, from the slew law behind `set_attitude_target`), and this domain integrates
what that torque does to a body with the vehicle's inertia tensor. Two states, in the order
`vehicle_dynamics.state_order` declares: the rate integrates first, then the attitude integrates the
rate.

What is *not* here, on purpose: the per-jet allocator, pulse widths and the 100 Hz inner loop. The
torque the service hands over is its average over the tick, so a slew is a rigid-body response to a
bounded torque and nothing finer. Everything a rule uses is a parameter on its own state, with its
provenance there.

Conventions (`vehicle.yaml#conventions`): the quaternion is `[w,x,y,z]` and rotates a vector from
BODY into the reference frame (EARTH_J2000), and the body rate is resolved in BODY, in deg/s.
"""

from __future__ import annotations

import math

# --------------------------------------------------------------------------------------------
# Small vector and quaternion arithmetic. Rules import the standard library only, so these are
# written out; `domains/rcs/rules.py` carries its own copy for the same reason.
# --------------------------------------------------------------------------------------------


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _qmul(p, q):
    """The Hamilton product p (x) q, both `[w,x,y,z]`."""
    return (
        p[0] * q[0] - p[1] * q[1] - p[2] * q[2] - p[3] * q[3],
        p[0] * q[1] + p[1] * q[0] + p[2] * q[3] - p[3] * q[2],
        p[0] * q[2] - p[1] * q[3] + p[2] * q[0] + p[3] * q[1],
        p[0] * q[3] + p[1] * q[2] - p[2] * q[1] + p[3] * q[0],
    )


def _unit(q):
    norm = math.sqrt(sum(c * c for c in q))
    return tuple(c / norm for c in q)


def inertia_tensor(params):
    """The body inertia tensor (kg m^2) from the six published figures.

    The Operational Data Book prints products of inertia as `PXY = sum(m x y)`, so the tensor's
    off-diagonal terms are their negatives.
    """
    ixx, iyy, izz = (float(params[k]) for k in ("ixx_kg_m2", "iyy_kg_m2", "izz_kg_m2"))
    pxy, pxz, pyz = (float(params[k]) for k in ("pxy_kg_m2", "pxz_kg_m2", "pyz_kg_m2"))
    return ((ixx, -pxy, -pxz), (-pxy, iyy, -pyz), (-pxz, -pyz, izz))


def _apply(matrix, v):
    return tuple(sum(matrix[i][j] * v[j] for j in range(3)) for i in range(3))


def _solve(matrix, v):
    """`matrix^-1 v` by Cramer's rule: three equations, no library."""
    (a, b, c), (d, e, f), (g, h, i) = matrix
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    x = (
        v[0] * (e * i - f * h) - b * (v[1] * i - f * v[2]) + c * (v[1] * h - e * v[2])
    ) / det
    y = (a * (v[1] * i - f * v[2]) - v[0] * (d * i - f * g) + c * (d * v[2] - v[1] * g)) / det
    z = (a * (e * v[2] - v[1] * h) - b * (d * v[2] - v[1] * g) + v[0] * (d * h - e * g)) / det
    return (x, y, z)


def angular_acceleration(inertia, omega, torque):
    """Euler's equation for a rigid body in its own axes: I w' = tau - w x (I w), in rad/s^2."""
    gyro = _cross(omega, _apply(inertia, omega))
    return _solve(inertia, tuple(t - g for t, g in zip(torque, gyro, strict=True)))


# --------------------------------------------------------------------------------------------
# The two states.
# --------------------------------------------------------------------------------------------


def _body_rate(inputs, params, dt):
    """The body rate after one tick of the service's torque, deg/s in BODY.

    A midpoint step, not a forward Euler one: the gyroscopic term is what makes a spin about an axis
    that is not principal wander (the coning a passive thermal control roll develops), and forward
    Euler adds energy to a torque-free spin every tick, which over a coast of days is a vehicle that
    spins itself up for no reason.
    """
    inertia = inertia_tensor(params)
    omega = tuple(math.radians(float(w)) for w in inputs["body_rate"])
    torque = tuple(float(t) for t in inputs["control_torque"])
    first = angular_acceleration(inertia, omega, torque)
    middle = tuple(w + 0.5 * dt * a for w, a in zip(omega, first, strict=True))
    second = angular_acceleration(inertia, middle, torque)
    return [math.degrees(w + dt * a) for w, a in zip(omega, second, strict=True)]


def _attitude(inputs, params, dt):
    """The attitude after one tick at this tick's body rate: q <- q (x) exp(w dt / 2), renormalised.

    `attitude_ref_from_body` rotates BODY into the reference frame, so the body-resolved rate
    multiplies on the right. The exponential is exact for a rate held over the tick.
    """
    q = tuple(float(c) for c in inputs["attitude"])
    omega = tuple(math.radians(float(w)) for w in inputs["body_rate"])
    angle = math.sqrt(sum(w * w for w in omega)) * dt
    if angle == 0.0:
        return list(_unit(q))
    s = math.sin(0.5 * angle) / (angle / dt)
    step = (math.cos(0.5 * angle), omega[0] * s, omega[1] * s, omega[2] * s)
    return list(_unit(_qmul(q, step)))


def _sun_direction_body(inputs, params, dt):
    """The sun line in BODY: `q^-1 (x) s (x) q`, with `s` the fixed EARTH_J2000 unit vector."""
    q = tuple(float(c) for c in inputs["attitude"])
    sun = tuple(float(c) for c in params["sun_earth_j2000"])
    conj = (q[0], -q[1], -q[2], -q[3])
    return list(_qmul(_qmul(conj, (0.0, *sun)), q)[1:])


# --------------------------------------------------------------------------------------------
# Where the navigation solution comes from, reduced (ADR 0005, "Navigation sources"). Not the
# 15-state filter `gnc_diode.md:790` describes: the ground's tracking arc, how long the vehicle
# has coasted on the vector it holds, and the two sigmas those give. Apollo's ground rule is that
# the ground navigates and the onboard sightings are the backup, so the source that matters is
# whether the vehicle holds the ground's vector or is coasting on an old one.
# --------------------------------------------------------------------------------------------

FT_TO_M = 0.3048


def _msfn_arc_s(inputs, params, dt):
    """How long the ground has tracked the vehicle since its solution last started over."""
    return float(inputs["msfn_arc_s"]) + dt


def _nav_vector_arc_s(inputs, params, dt):
    """The tracking arc behind the vector the vehicle holds: the ground's own while the vehicle
    takes the ground's vector, frozen at the moment it stopped."""
    if str(inputs["nav_source"]) == "ground_uplink":
        return float(inputs["msfn_arc_s"])
    return float(inputs["nav_vector_arc_s"])


def _nav_coast_s(inputs, params, dt):
    """How long the vehicle has navigated without the ground's vector."""
    if str(inputs["nav_source"]) == "ground_uplink":
        return 0.0
    return float(inputs["nav_coast_s"]) + dt


def msfn_velocity_sigma_m_s(arc_s, table):
    """The 1-sigma velocity the ground knows after `arc_s` of tracking: the RSS of the three axes'
    3-sigma, divided by three, interpolated in the arc and held at the table's ends."""
    rows = [(float(row[0]) * 3600.0, math.sqrt(sum(float(v) ** 2 for v in row[1:]))) for row in table]
    if arc_s <= rows[0][0]:
        three = rows[0][1]
    elif arc_s >= rows[-1][0]:
        three = rows[-1][1]
    else:
        for (t0, v0), (t1, v1) in zip(rows, rows[1:], strict=False):
            if t0 <= arc_s <= t1:
                three = v0 + (v1 - v0) * (arc_s - t0) / (t1 - t0)
                break
    return three / 3.0 * FT_TO_M


def _nav_velocity_sigma(inputs, params, dt):
    """The velocity sigma of the vector held: the ground's at the arc behind it."""
    return msfn_velocity_sigma_m_s(float(inputs["nav_vector_arc_s"]), params["msfn_3sigma_ft_s"])


def _nav_position_sigma(inputs, params, dt):
    """The position sigma: the ground's at the uplink, grown by the velocity error over the coast."""
    ground = float(params["ground_position_sigma_m"])
    grown = float(inputs["nav_velocity_sigma"]) * float(inputs["nav_coast_s"])
    return math.sqrt(ground * ground + grown * grown)


RULES = {
    "body_rate": _body_rate,
    "attitude": _attitude,
    "sun_direction_body": _sun_direction_body,
    "msfn_arc_s": _msfn_arc_s,
    "nav_vector_arc_s": _nav_vector_arc_s,
    "nav_coast_s": _nav_coast_s,
    "nav_velocity_sigma": _nav_velocity_sigma,
    "nav_position_sigma": _nav_position_sigma,
}
