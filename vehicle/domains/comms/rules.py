"""Comms domain rules (D5): the transmit chain and the quiet-coast task model.

Each rule is a pure function of the tick's snapshot (`inputs`), its own state's declaration
(`params`) and the horizon (`dt`). Every number a rule uses is a parameter declared, with its
provenance, on the state in `components.yaml`; none is written here.
"""

import math


def tx_power(inputs, params, dt):
    """The transmit chain's DC input (`comm.tx_power_w`): the transceiver's, plus the amplifier's
    while it is switched on. A published measurement, not a load: power counts the loads."""
    power = params["transceiver_dc_w"]
    if inputs["transmitter_on"] == "on":
        power = power + params["amplifier_dc_w"]
    return float(power)


def amp_dissipation_w(inputs, params, dt):
    """The amplifier's heat: its DC input less the RF it radiates, while it is on (ADR 0003 item 5)."""
    if inputs["transmitter_on"] != "on":
        return 0.0
    return float(params["amplifier_dc_w"]) - float(params["amplifier_rf_w"])


def link_ok(inputs, params, dt):
    """The episode's link boundary (ADR 0003 item 8): the high-gain antenna, the high-rate S-band
    mode at the high profile's rate, the power amplifier on, and the Earth not behind the Moon.

    The occultation is evaluated here from this tick's orbit, by the function `blackout` calls,
    rather than read from `blackout`: that state is on the sentinel, which advances after
    `ground_received`, and it has no value before the first tick."""
    if not (
        inputs["antenna_selection"] == "high_gain"
        and inputs["comm_mode"] == "sband_high"
        and inputs["telemetry_rate"] == params["high_rate_bps"]
        and inputs["transmitter_on"] == "on"
    ):
        return False
    orbit = inputs["orbital_state"]
    hidden = occulted(orbit["position_m"], orbit["moon_position_m"], float(params["moon_radius_m"]))
    if hidden is None:
        return params.no_value(
            "the vehicle is inside the Moon's mean radius, where the trajectory has no meaning"
        )
    return not hidden


def occulted(vehicle_m, moon_m, moon_radius_m):
    """Whether the Moon hides the Earth's centre from the vehicle, or None inside the Moon's radius.

    Earth-centred positions in metres. The Earth is behind the Moon when the angle between the
    vehicle's directions to the Moon's centre and to the Earth's is less than the Moon's angular
    radius, `arcsin(R_moon / |vehicle -> Moon|)`, and the Moon is the nearer of the two.
    """
    to_moon = [moon_m[i] - vehicle_m[i] for i in range(3)]
    to_earth = [-vehicle_m[i] for i in range(3)]
    d_moon = math.sqrt(sum(x * x for x in to_moon))
    d_earth = math.sqrt(sum(x * x for x in to_earth))
    if d_moon <= moon_radius_m:
        return None
    cosine = sum(to_moon[i] * to_earth[i] for i in range(3)) / (d_moon * d_earth)
    angle = math.acos(max(-1.0, min(1.0, cosine)))
    return d_moon < d_earth and angle < math.asin(moon_radius_m / d_moon)


def blackout(inputs, params, dt):
    """`occulted` while the Moon is between the vehicle and the Earth, from this tick's orbit
    (`gnc.orbital_state`, which carries the Moon beside the vehicle), and `clear` otherwise."""
    orbit = inputs["orbital_state"]
    hidden = occulted(orbit["position_m"], orbit["moon_position_m"], float(params["moon_radius_m"]))
    if hidden is None:
        return params.no_value(
            "the vehicle is inside the Moon's mean radius, where the trajectory has no meaning"
        )
    return "occulted" if hidden else "clear"


def playback_rate(inputs, params, dt):
    """Bits per second leaving the recorder for the ground: the playback rate while the recorder
    plays over an ok link, and nothing otherwise."""
    if inputs["recorder_play"] == "on" and inputs["link_ok"]:
        return float(params["play_rate_bps"])
    return 0.0


RULES = {
    "tx_power": tx_power,
    "amp_dissipation_w": amp_dissipation_w,
    "link_ok": link_ok,
    "blackout": blackout,
    "playback_rate": playback_rate,
}
