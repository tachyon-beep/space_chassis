"""The RCS domain's rules (D5): the attitude service as pointing modes behind `set_attitude_target`.

ADR 0005 and the arc review's decision 5: a rate-limited slew law, not a 6-DOF allocator. The service
holds a target, drives the vehicle toward it along the eigenaxis at the rate the DAP was loaded with,
and inside the deadband it stops steering and pays the minimum-impulse limit cycle the Apollo DAP
paid. What it hands the dynamics is the torque averaged over the tick (`control_torque`); what it
hands the tanks is the thrust that torque took (`thruster_thrust` per jet, `thrust_total_n` summed).

The service reads the vehicle through `vehicle_dynamics` from the previous tick: the controller
samples, then fires, and the rate and attitude it fired against advance after it (`coupling.yaml`
`E-RCS-DYN`). Every number a rule uses is a parameter on its own state, with its provenance there.

Conventions (`vehicle.yaml#conventions`): quaternions are `[w,x,y,z]` and rotate BODY into the
reference frame; rates are BODY-resolved, deg/s on the channels and rad/s inside these functions.
"""

from __future__ import annotations

import math

# --------------------------------------------------------------------------------------------
# Small vector and quaternion arithmetic (`domains/gnc/rules.py` carries its own copy: a rule file
# imports the standard library only).
# --------------------------------------------------------------------------------------------


def _qmul(p, q):
    return (
        p[0] * q[0] - p[1] * q[1] - p[2] * q[2] - p[3] * q[3],
        p[0] * q[1] + p[1] * q[0] + p[2] * q[3] - p[3] * q[2],
        p[0] * q[2] - p[1] * q[3] + p[2] * q[0] + p[3] * q[1],
        p[0] * q[3] + p[1] * q[2] - p[2] * q[1] + p[3] * q[0],
    )


def _conj(q):
    return (q[0], -q[1], -q[2], -q[3])


def _unit(q):
    norm = math.sqrt(sum(c * c for c in q))
    return tuple(c / norm for c in q)


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _inertia(params):
    """The body inertia tensor from the six published figures; ODB products are `sum(m x y)`."""
    ixx, iyy, izz = (float(params[k]) for k in ("ixx_kg_m2", "iyy_kg_m2", "izz_kg_m2"))
    pxy, pxz, pyz = (float(params[k]) for k in ("pxy_kg_m2", "pxz_kg_m2", "pyz_kg_m2"))
    return ((ixx, -pxy, -pxz), (-pxy, iyy, -pyz), (-pxz, -pyz, izz))


def _apply(matrix, v):
    return tuple(sum(matrix[i][j] * v[j] for j in range(3)) for i in range(3))


def _rotate(q, v):
    """`v` rotated by `q`: `q (x) [0, v] (x) q^-1`."""
    return _qmul(_qmul(q, (0.0, *v)), _conj(q))[1:]


def pointing_error(q, target, rolling):
    """The error the service steers out, as (angle rad, unit axis in BODY).

    Holding, it is the whole rotation to the target. In the thermal roll it is only where +X points:
    the roll about +X is the commanded motion, so the error is the angle between the body's +X and
    the target's, about the axis that carries one onto the other.
    """
    if not rolling:
        return rotation_error(q, target)
    wanted = _rotate(_qmul(_conj(q), target), (1.0, 0.0, 0.0))
    axis = _cross((1.0, 0.0, 0.0), wanted)
    sine = math.sqrt(sum(c * c for c in axis))
    angle = math.atan2(sine, wanted[0])
    if sine == 0.0:
        return angle, (0.0, 1.0, 0.0)
    return angle, tuple(c / sine for c in axis)


def rotation_error(q, target):
    """The rotation from the present attitude to the target, as (angle rad, unit axis in BODY).

    `q^-1 (x) q_t` is the target body expressed in the present body; the shorter way round is taken.
    """
    e = _qmul(_conj(q), target)
    if e[0] < 0.0:
        e = tuple(-c for c in e)
    sine = math.sqrt(e[1] * e[1] + e[2] * e[2] + e[3] * e[3])
    angle = 2.0 * math.atan2(sine, e[0])
    if sine == 0.0:
        return 0.0, (1.0, 0.0, 0.0)
    return angle, (e[1] / sine, e[2] / sine, e[3] / sine)


def parse_quaternion(text):
    """A commanded quaternion as the window carried it (`1,0,0,0` or `[1,0,0,0]`), normalised; or
    None when it is not four numbers or not within 1 % of unit length. A target the service cannot
    read is not a target, and the service keeps the one it had."""
    cleaned = str(text).strip().strip("[]()").replace(" ", "")
    parts = [p for p in cleaned.split(",") if p]
    if len(parts) != 4:
        return None
    try:
        q = tuple(float(p) for p in parts)
    except ValueError:
        return None
    norm = math.sqrt(sum(c * c for c in q))
    if not all(math.isfinite(c) for c in q) or abs(norm - 1.0) > 0.01:
        return None
    return tuple(c / norm for c in q)


# --------------------------------------------------------------------------------------------
# The control axes. The SM quads sit 7.25 deg round from the body Y and Z axes (`quad_offset_deg`),
# and the DAP fires about those axes: a couple's torque is bounded per control axis, not per body
# axis.
# --------------------------------------------------------------------------------------------


def _to_control(v, offset_rad):
    c, s = math.cos(offset_rad), math.sin(offset_rad)
    return (v[0], c * v[1] + s * v[2], -s * v[1] + c * v[2])


def _from_control(v, offset_rad):
    c, s = math.cos(offset_rad), math.sin(offset_rad)
    return (v[0], c * v[1] - s * v[2], s * v[1] + c * v[2])


def couple_torque_nm(params):
    """The torque one two-jet couple delivers about each control axis (roll, pitch, yaw), N m.

    A couple's two jets push opposite ways at opposite ends of a diameter, so their forces cancel and
    so does the centre of mass's axial position: the torque is `2 F r cos(cant)` whatever the
    configuration, with the roll jets on their own radius.
    """
    thrust = float(params["thrust_n"])
    cant = math.radians(float(params["cant_deg"]))
    inch = 0.0254
    pitch_yaw = 2.0 * thrust * float(params["pitch_yaw_radius_in"]) * inch * math.cos(cant)
    roll = 2.0 * thrust * float(params["roll_radius_in"]) * inch * math.cos(cant)
    return (roll, pitch_yaw, pitch_yaw)


def holding(torque, mode):
    """Whether the service is inside its deadband: in `auto` and asking for no torque at all."""
    return mode == "auto" and all(float(t) == 0.0 for t in torque)


# --------------------------------------------------------------------------------------------
# The states.
# --------------------------------------------------------------------------------------------


def _held_target(inputs, params, dt):
    """The target the service is steering to, resolved into EARTH_J2000.

    The commanded text and frame are what the effect path wrote; this resolves them once, when they
    change, because a BODY-frame target is relative to the attitude *when it was asked for* — read
    every tick it would move with the vehicle and never be reached. `current` holds the attitude the
    vehicle has now (an abort, a hold where it stands, or the start and end of the thermal roll,
    which re-resolve it because the roll changes). LVLH waits on the orbit-referenced frame
    (`open_debts`), so a target given in it is recorded and not steered to.
    """
    previous = inputs["held_target"]
    text = str(inputs["attitude_target"])
    frame = str(inputs["target_frame"])
    roll = float(inputs["roll_rate_command"])
    if (
        previous.get("source") == text
        and previous.get("frame") == frame
        and float(previous.get("roll", 0.0)) == roll
    ):
        # A fresh record with the quaternion as a list: the plant hands a rule its inputs frozen, and
        # the truth holds what JSON gives back, so a checkpoint restores the same value.
        return {**previous, "q": list(previous["q"])}
    present = tuple(float(c) for c in inputs["attitude"])
    resolved = {"source": text, "frame": frame, "roll": roll, "q": list(previous["q"])}
    if text == "current":
        resolved["q"] = list(_unit(present))
        resolved["status"] = "held"
        return resolved
    commanded = parse_quaternion(text)
    if commanded is None:
        resolved["status"] = "unreadable"
    elif frame in params["inertial_frames"]:
        resolved["q"] = list(commanded)
        resolved["status"] = "held"
    elif frame == "BODY":
        resolved["q"] = list(_unit(_qmul(present, commanded)))
        resolved["status"] = "held"
    else:
        resolved["status"] = "frame_owed"
    return resolved


def _control_torque(inputs, params, dt):
    """The torque the service asks of the jets this tick, averaged over the tick, N m in BODY.

    The slew law is the DAP's phase plane reduced to one axis, the eigenaxis to the target: the rate
    the service steers to is the loaded maneuver rate, or the rate from which the jets can still
    stop the vehicle on the target (`sqrt(2 alpha theta)`), whichever is smaller. The torque is what
    closes the rate error in one tick plus the gyroscopic term, scaled down as a whole until no
    control axis is asked for more than its couple can give, so the slew keeps its axis.

    Inside the deadband, with the rate below what one minimum-impulse pulse can correct, the service
    asks for nothing: that is the hold, and the limit cycle it costs is `thruster_thrust`'s.

    In the thermal roll (`roll_rate_command`, set by `set_ptc_roll`) the rate it steers to carries
    the roll about +X as well, and the error is only where +X points. Apollo spun up this way and
    then switched the jets off; the vehicle does the same when the fleet selects `free_drift`, and
    from then on the roll is a torque-free spin that cones.
    """
    mode = str(inputs["mode"])
    if mode != "auto":
        return [0.0, 0.0, 0.0]
    q = tuple(float(c) for c in inputs["attitude"])
    omega = tuple(math.radians(float(w)) for w in inputs["body_rate"])
    target = tuple(float(c) for c in inputs["held_target"]["q"])
    roll = math.radians(float(inputs["roll_rate_command"]))
    spin = (roll, 0.0, 0.0)
    angle, axis = pointing_error(q, target, roll != 0.0)
    inertia = _inertia(params)
    offset = math.radians(float(params["quad_offset_deg"]))
    limits = couple_torque_nm(params)

    deadband = math.radians(float(inputs["deadband_deg"]))
    rate_floor = math.radians(float(params["rate_floor_deg_s"]))
    speed = math.sqrt(sum((w - s) ** 2 for w, s in zip(omega, spin, strict=True)))
    if angle <= deadband and speed <= rate_floor:
        return [0.0, 0.0, 0.0]

    # The acceleration the jets can give about the eigenaxis: the largest scale of `I axis` that no
    # control axis's couple limit is exceeded by.
    demand = _to_control(_apply(inertia, axis), offset)
    alpha = min(lim / abs(d) for lim, d in zip(limits, demand, strict=True) if d != 0.0)
    rate_limit = math.radians(float(inputs["slew_rate_limit"]))
    steer = 0.0 if angle <= deadband else min(rate_limit, math.sqrt(2.0 * alpha * angle))
    wanted = tuple(s + steer * a for s, a in zip(spin, axis, strict=True))

    error = tuple(w_d - w for w_d, w in zip(wanted, omega, strict=True))
    gyro = _cross(omega, _apply(inertia, omega))
    request = tuple(
        i_e / dt + g for i_e, g in zip(_apply(inertia, error), gyro, strict=True)
    )
    in_control = _to_control(request, offset)
    scale = min(
        [1.0] + [lim / abs(t) for lim, t in zip(limits, in_control, strict=True) if t != 0.0]
    )
    return list(_from_control(tuple(scale * t for t in in_control), offset))


def _hold_cycle_pulse_rate_hz(params, deadband_rad):
    """Minimum-impulse pulses per second, per control axis, holding inside a deadband of half-width
    `deadband_rad` with no disturbance.

    One couple pulse changes the rate by `dw = 2 I_bit arm / I_axis`; the symmetric limit cycle runs
    at half that rate across the whole band, `2 deadband`, and pulses once per crossing:
    `rate = dw / (4 deadband)` (R-577 s. 3.2, Fig. 3.2-8's minimum-impulse cycle EFGH).
    """
    impulse = float(params["pulse_impulse_ns"])
    cant = math.cos(math.radians(float(params["cant_deg"])))
    inch = 0.0254
    arms = (
        float(params["roll_radius_in"]) * inch * cant,
        float(params["pitch_yaw_radius_in"]) * inch * cant,
        float(params["pitch_yaw_radius_in"]) * inch * cant,
    )
    inertias = tuple(float(params[k]) for k in ("ixx_kg_m2", "iyy_kg_m2", "izz_kg_m2"))
    rates = []
    for arm, inertia in zip(arms, inertias, strict=True):
        dw = 2.0 * impulse * arm / inertia
        rates.append(dw / (4.0 * deadband_rad))
    return rates


def _thruster_thrust(inputs, params, dt):
    """Each SM jet's thrust averaged over the tick, N, keyed `sm_<DAP jet>`.

    In a slew, the couple for each control axis and sign fires for the fraction of the tick its
    torque needs (`|tau| / couple`), both jets alike. In the hold, the limit cycle's pulses are
    spread over the four jets of each axis's two couples. The CM and LM jets do not fire: the
    docked stack is flown on the SM's (`open_debts`).
    """
    torque = tuple(float(t) for t in inputs["control_torque"])
    mode = str(inputs["mode"])
    jets = {f"sm_{n}": 0.0 for n in range(1, 17)}
    couples = params["couples"]
    thrust = float(params["thrust_n"])
    if holding(torque, mode):
        deadband = math.radians(float(inputs["deadband_deg"]))
        rates = _hold_cycle_pulse_rate_hz(params, deadband)
        impulse = float(params["pulse_impulse_ns"])
        for rate, name in zip(rates, ("roll", "pitch", "yaw"), strict=True):
            # Each pulse fires one couple, two jets; over a cycle the two signs alternate.
            per_jet = rate * 2.0 * impulse / 4.0
            for sign in ("+", "-"):
                for jet in couples[sign + name]:
                    jets[f"sm_{jet}"] += per_jet
        return jets
    offset = math.radians(float(params["quad_offset_deg"]))
    limits = couple_torque_nm(params)
    in_control = _to_control(torque, offset)
    for value, limit, name in zip(in_control, limits, ("roll", "pitch", "yaw"), strict=True):
        if value == 0.0:
            continue
        duty = min(abs(value) / limit, 1.0)
        for jet in couples[("+" if value > 0 else "-") + name]:
            jets[f"sm_{jet}"] += duty * thrust
    return jets


def _thrust_total_n(inputs, params, dt):
    """The summed thrust the propellant drain prices (`E-RCSP-RCS`, at the steady-state Isp), N.

    In steady firing this is the delivered thrust. A minimum-impulse pulse burns more propellant per
    newton-second than steady firing does (the Data Book's 0.00545 lb per 14 ms pulse against its
    4.2 N s impulse), so in the hold the delivered thrust is scaled up by that ratio: the tank pays
    for the pulse it fired, and `impulse_total` books only the impulse it delivered.
    """
    delivered = sum(float(v) for v in inputs["thruster_thrust"].values())
    if holding(tuple(inputs["control_torque"]), str(inputs["mode"])):
        priced = (
            float(params["pulse_propellant_kg"])
            * float(params["isp_s"])
            * float(params["g0_m_s2"])
            / float(params["pulse_impulse_ns"])
        )
        return delivered * priced
    return delivered


def _impulse_total(inputs, params, dt):
    """`rcs.total_impulse_ns`: every newton-second the jets delivered, summed."""
    delivered = sum(float(v) for v in inputs["thruster_thrust"].values())
    return float(inputs["impulse_total"]) + delivered * dt


def _deadband_deg(inputs, params, dt):
    """The angular deadband the selected profile holds, deg (`by_profile_deg`)."""
    return float(params["by_profile_deg"][str(inputs["control_profile"])])


def _attitude_error(inputs, params, dt):
    """The angle between the attitude and the held target, deg; in the thermal roll, between the
    body's +X and the target's, because the roll itself is not an error."""
    q = tuple(float(c) for c in inputs["attitude"])
    target = tuple(float(c) for c in inputs["held_target"]["q"])
    rolling = float(inputs["roll_rate_command"]) != 0.0
    return math.degrees(pointing_error(q, target, rolling)[0])


RULES = {
    "deadband_deg": _deadband_deg,
    "control_torque": _control_torque,
    "thruster_thrust": _thruster_thrust,
    "thrust_total_n": _thrust_total_n,
    "held_target": _held_target,
    "impulse_total": _impulse_total,
    "attitude_error": _attitude_error,
}
