"""ECLSS's domain rules (D5, `plant.md` §2): the suit circuit's flow, the cabin leak by gas, the
regulator's draw on the store its source selects, and the oxygen supply tanks' pressure under their
heater relay.

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


def _o2_supply(inputs, params, dt):
    """The regulator's demand from one store: the nominal flow while the vehicle's source selects
    this store, its flow band is not `off` and the cabin regulator is open, else nothing.

    The store is debited by this value on the *next* tick, at that tick's step, so the flow stops
    once the store holds less than a tick of it: a flow scaled down to the last milligrams over this
    step would be credited to the cabin now and could outrun the store on a shorter step next.
    """
    for switch in (params["source_switch"], params["flow_switch"]):
        if switch["element"] not in inputs[switch["state"]]:
            return params.no_value(f"{switch['state']} names no {switch['element']!r}")
    source, flow = params["source_switch"], params["flow_switch"]
    if inputs[source["state"]][source["element"]] != params["draws_on"]:
        return 0.0
    if inputs[flow["state"]][flow["element"]] == "off":
        return 0.0
    if inputs[params["regulator_state"]] not in params["regulator_open"]:
        return 0.0
    demand = float(params["nominal_kg_s"])
    if float(inputs[params["stock_state"]]) < demand * dt:
        return 0.0
    return demand


def _tank_heaters(inputs, params, dt):
    """The cryogenic oxygen tanks' pressure switch: on at or below the low setting, off at or above
    the high one, and where it was in between. It reads the pressure the previous tick left, because
    the pressure is advanced after it and acts on what the heaters are doing now."""
    pressure = float(inputs[params["pressure_state"]])
    if pressure <= float(params["energize_psia"]):
        return "on"
    if pressure >= float(params["deenergize_psia"]):
        return "off"
    return inputs["o2_tank_heaters"]


def _interpolate(table, column, quantity_pct):
    """A column of the repressurization table at a quantity, linear between rows and held at the ends."""
    rows = sorted((float(row[0]), float(row[column])) for row in table)
    if quantity_pct <= rows[0][0]:
        return rows[0][1]
    for (q0, v0), (q1, v1) in zip(rows, rows[1:], strict=False):
        if quantity_pct <= q1:
            return v0 + (v1 - v0) * (quantity_pct - q0) / (q1 - q0)
    return rows[-1][1]


def tank_pressure_rate_psi_h(heaters_on, quantity_pct, flow_lb_h, params):
    """dP/dt of one tank, psi per hour: `K * (Q_in - m * dq/dm)`.

    The heat a tank needs per pound withdrawn at constant pressure, `dq/dm`, is what the table's
    maximum flow says it is: at that flow the heaters, fans and leak just hold the low setting, so
    `dq/dm = Q_full / m_max`. The pressure's sensitivity to net heat, `K`, is what the table's
    repressurization time says it is: 70 psi in `T` minutes at the stated flow with everything on.
    """
    table = params["repressurization_table"]
    m_max = _interpolate(table, 2, quantity_pct)
    minutes = _interpolate(table, 1, quantity_pct)
    full = float(params["heat_in_full_btu_h"])
    dq_dm = full / m_max
    span = float(params["deenergize_psia"]) - float(params["energize_psia"])
    k = span / ((minutes / 60.0) * (full - float(params["table_flow_lb_h"]) * dq_dm))
    heat_in = full if heaters_on else float(params["heat_leak_btu_h"])
    return k * (heat_in - flow_lb_h * dq_dm)


def _tank_pressure(inputs, params, dt):
    """The supply tanks' pressure: the two tanks as one, each carrying half the stock and half the
    draw, relieved at the relief valve's crack pressure because venting is not modelled."""
    per_tank_kg = float(inputs[params["stock_state"]]) / float(params["tanks"])
    quantity_pct = 100.0 * per_tank_kg / (float(params["full_lb_per_tank"]) * float(params["kg_per_lb"]))
    draw_kg_s = sum(float(inputs[state]) for state in params["draw_states"])
    flow_lb_h = draw_kg_s * 3600.0 / float(params["kg_per_lb"]) / float(params["tanks"])
    heaters_on = inputs[params["heater_state"]] == "on"
    rate = tank_pressure_rate_psi_h(heaters_on, quantity_pct, flow_lb_h, params)
    pressure = float(inputs["o2_supply_pressure_psi"]) + rate * dt / 3600.0
    return min(max(pressure, 0.0), float(params["relief_psia"]))


RULES = {
    "suit_loop_flow_cfm": _suit_loop_flow,
    "o2_tank_heaters": _tank_heaters,
    "cabin_o2_supply_csm_kg_s": _o2_supply,
    "cabin_o2_surge_supply_csm_kg_s": _o2_supply,
    "o2_supply_pressure_psi": _tank_pressure,
    **{
        f"{cabin}_leak_{gas}_kg_s": _leak_share
        for cabin in ("csm", "lm")
        for gas in ("o2", "n2", "co2")
    },
}
