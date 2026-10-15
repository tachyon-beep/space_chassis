"""Comms domain rules (D5): the transmit chain and the quiet-coast task model.

Each rule is a pure function of the tick's snapshot (`inputs`), its own state's declaration
(`params`) and the horizon (`dt`). Every number a rule uses is a parameter declared, with its
provenance, on the state in `components.yaml`; none is written here.
"""


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
    mode at the high profile's rate, and the power amplifier on."""
    return (
        inputs["antenna_selection"] == "high_gain"
        and inputs["comm_mode"] == "sband_high"
        and inputs["telemetry_rate"] == params["high_rate_bps"]
        and inputs["transmitter_on"] == "on"
    )


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
    "playback_rate": playback_rate,
}
