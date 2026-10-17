"""ECLSS's domain rules (D5, `plant.md` §2): the suit circuit's flow and the cabin leak by gas.

Every number a rule uses is a field on its own state in `components.yaml`, where its provenance is.
Each function is `rule(inputs, params, dt) -> value`; `None` is a gap, not a value.
"""

from __future__ import annotations

import math


def _suit_loop_flow(inputs, params, dt):
    """The suit compressor as flow: relax toward the rated delivery while it runs, else toward zero.

    The compressor is the only thing that moves the suit circuit (`initial_provenance`). It runs
    while `set_suit_fan` has it on (`suit_fan`) and its electrical load is powered
    (`power.load_enabled`), as the coolant pump does. A switch map that does not name its element is
    a gap rather than a stopped fan.
    """
    enabled = inputs["load_enabled"]
    load = params["compressor_load"]
    switch = params["compressor_switch"]
    commanded = inputs[switch["state"]]
    if load not in enabled:
        return params.no_value(f"power.load_enabled names no {load!r}")
    if switch["element"] not in commanded:
        return params.no_value(f"{switch['state']} names no {switch['element']!r}")
    running = enabled[load] == "on" and commanded[switch["element"]] == "on"
    target = float(params["rated_flow_cfm"]) if running else 0.0
    current = float(inputs["suit_loop_flow_cfm"])
    return target + (current - target) * math.exp(-dt / float(params["tau_s"]))


def _leak_share(inputs, params, dt):
    """One gas's share of the cabin leak: the leak's mass flow times the gas's mass fraction.

    A leak through a seal is bulk flow, so the cabin loses each gas in proportion to its share of the
    mass. An empty cabin has no fraction to take, which is a zero outflow rather than a gap.
    """
    total = sum(float(inputs[stock]) for stock in params["cabin_stocks"])
    if total <= 0.0:
        return 0.0
    share = max(float(inputs[params["gas_stock"]]), 0.0) / total
    return float(params["leak_kg_per_h"]) / 3600.0 * share


RULES = {
    "suit_loop_flow_cfm": _suit_loop_flow,
    **{
        f"{cabin}_leak_{gas}_kg_s": _leak_share
        for cabin in ("csm", "lm")
        for gas in ("o2", "n2", "co2")
    },
}
