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


def light_time_s(inputs, params, dt):
    """The one-way light time between the vehicle and the ground, from this tick's range: the
    vehicle's distance from the Earth's centre over the speed of light."""
    position = inputs["orbital_state"]["position_m"]
    return math.sqrt(sum(x * x for x in position)) / float(params["speed_of_light_m_s"])


def link_snr(inputs, params, dt):
    """The downlink's signal-to-noise ratio in the telemetry bit-rate bandwidth at an 85-ft MSFN
    station (`comm.snr_db`): the received carrier power, scaled from Bellcomm's lunar-range
    prediction by range, less the high-gain antenna's pointing loss, against the carrier power the
    commanded telemetry rate needs.

    SNR = required SNR + (received - required carrier power): the circuit margin is the SNR the
    link has over the SNR the mode needs (TN D-6723), so a zero margin is 12.5 dB. There is no
    S-band carrier to measure in `vhf` or `none`, or with the Earth behind the Moon, and the state
    is then a gap rather than a low number, so a planned blackout raises no SNR alarm.
    """
    mode = inputs["comm_mode"]
    if mode not in ("sband_high", "sband_low"):
        return params.no_value(f"the vehicle radiates no S-band carrier in `{mode}` mode")
    orbit = inputs["orbital_state"]
    hidden = occulted(orbit["position_m"], orbit["moon_position_m"], float(params["moon_radius_m"]))
    if hidden is None:
        return params.no_value(
            "the vehicle is inside the Moon's mean radius, where the trajectory has no meaning"
        )
    if hidden:
        return params.no_value("the Earth is behind the Moon, so no carrier reaches the ground")
    antenna = inputs["antenna_selection"]
    family = (
        "high_gain"
        if antenna == "high_gain"
        else "omni"
        if antenna in ("omni_a", "omni_b")
        else None
    )
    if family is None:
        return params.no_value(f"no received-power prediction covers the `{antenna}` antenna")
    received = float(params["received_carrier_dbm"][family])
    if inputs["transmitter_on"] != "on":
        received += float(params["power_amplifier_off_db"])
    position = orbit["position_m"]
    range_m = math.sqrt(sum(x * x for x in position))
    received += 20.0 * math.log10(float(params["reference_range_m"]) / range_m)
    if family == "high_gain":
        error = float(inputs["antenna_pointing"])
        ratio = error / float(params["hga_beamwidth_deg"])
        received -= float(params["pattern_loss_db_at_beamwidth"]) * ratio * ratio
    # Keyed by the rate as a string: a mapping key is a name, and the linter walks names as text.
    required = params["required_carrier_dbm"]
    rate = inputs["telemetry_rate"]
    key = str(int(rate)) if isinstance(rate, (int, float)) else str(rate)
    if key not in required:
        return params.no_value(f"no required carrier power is declared for {rate} bit/s")
    return float(params["required_snr_db"]) + received - float(required[key])


RULES = {
    "tx_power": tx_power,
    "amp_dissipation_w": amp_dissipation_w,
    "link_ok": link_ok,
    "blackout": blackout,
    "light_time_s": light_time_s,
    "link_snr": link_snr,
    "playback_rate": playback_rate,
}
