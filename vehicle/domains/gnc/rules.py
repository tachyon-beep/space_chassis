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


RULES = {
    "body_rate": _body_rate,
    "attitude": _attitude,
}
