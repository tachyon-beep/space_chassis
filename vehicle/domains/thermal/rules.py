"""The thermal domain's rules (D5): heat rates over enabled loads, the loop balance, the radiator
at the loop's temperature, the evaporator, the pump as flow and the four node balances.

Every parameter is read from the state's own declaration in `components.yaml`, where its provenance
is. Each function is `rule(inputs, params, dt) -> value`. ADR 0003 (items 4, 5, 9-11) is the
decision record, and `09-quiet-coast-episode.md` §3 is the closure these rules serve.

A rule that reads a node scheduled after its own reads that node's value from the previous tick.
Two places do this, and both are an explicit Euler step rather than an accident. The loop balance's
heat terms are this tick's, and its load is last tick's (`loop_primary_load_w` lives on the
sentinel, which is walked last). The evaporator reads last tick's loop temperature.
"""

from __future__ import annotations

import math

# --------------------------------------------------------------------------------------------
# Heat rates: the zone's loads, summed over the ones `power.load_enabled` has on.
# --------------------------------------------------------------------------------------------


def _zone_heat(inputs, params, dt):
    enabled = inputs["load_enabled"]
    dissipating = params["dissipation_loads"]
    total = 0.0
    for load, watts in sorted(params["heat_loads_w"].items()):
        if enabled[load] != "on":
            continue
        if load in dissipating:
            total += float(inputs[dissipating[load]])
        else:
            total += float(watts)
    return total


def _loop_load(inputs, params, dt):
    return sum(float(inputs[state]) for state in params["zone_heat_states"])


def _cabin_eq_on_loop(inputs, params, dt):
    """The supply this tick (`coolant_loop_t`) plus the cabin's own rise, Q/G."""
    supply = float(inputs[params["supply_state"]])
    return supply + float(inputs[params["heat_state"]]) / float(params["conductance_w_per_k"])


def _cabin_eq_on_declared_supply(inputs, params, dt):
    """As above over a loop with no temperature state: its declared supply."""
    supply = float(params["supply_k"])
    return supply + float(inputs[params["heat_state"]]) / float(params["conductance_w_per_k"])


# --------------------------------------------------------------------------------------------
# The pump, the radiator, the evaporator and the loop.
# --------------------------------------------------------------------------------------------


def flow_fraction(pumps, enabled, pump_loads):
    """1 while a primary-loop pump is commanded on and its load is powered; 0 otherwise."""
    for pump, load in sorted(pump_loads.items()):
        if pumps[pump] == "on" and enabled[load] == "on":
            return 1.0
    return 0.0


def _pump_running(inputs, params, dt):
    """Each pump `on` while it is selected and its load, if it declares one, is powered."""
    enabled = inputs["load_enabled"]
    loads = params["pump_loads"]
    return {
        pump: "on" if state == "on" and (pump not in loads or enabled[loads[pump]] == "on") else "off"
        for pump, state in sorted(inputs[params["pump_state"]].items())
    }


def _coolant_flow(inputs, params, dt):
    fraction = flow_fraction(
        inputs[params["pump_state"]], inputs["load_enabled"], params["pump_loads"]
    )
    target = fraction * float(params["rated_flow_kg_s"])
    current = float(inputs["coolant_flow_kg_s"])
    return target + (current - target) * math.exp(-dt / float(params["tau_s"]))


def _pump_speed(inputs, params, dt):
    """The shaft speed as a fraction of rated, relaxing as the flow does: 1 while the pump is
    commanded on and powered, 0 otherwise."""
    pump = params["pump"]
    fraction = flow_fraction(
        {pump: inputs[params["pump_state"]][pump]},
        inputs["load_enabled"],
        {pump: params["pump_load"]},
    )
    current = float(inputs["pump_1_speed_frac"])
    return fraction + (current - fraction) * math.exp(-dt / float(params["tau_s"]))


def flow_share(inputs, params):
    """The loop's flow as a fraction of the published rate, in [0, 1]."""
    share = float(inputs[params["flow_state"]]) / float(params["rated_flow_kg_s"])
    return min(max(share, 0.0), 1.0)


def radiator_share(inputs, params):
    """The share of the panel's rejection the loop receives: the flow share while the bypass valve
    is at `radiator`, and nothing at `bypass`. Linear in flow below the published rate: the panel
    and the evaporator can only take heat out of the coolant that passes through them."""
    if inputs[params["bypass_state"]][params["loop"]] != "radiator":
        return 0.0
    return flow_share(inputs, params)


def radiator_mean_k(inlet_k, capacity_w_per_k, environment_w, eps_sigma_a):
    """The glycol's mean temperature in the panel: the root of
    `T - T_ri + (eps_sigma_a * T^4 - environment_w) / (2 * capacity_w_per_k)`, by bisection
    between the inlet and the panel's own sink. With no capacity (no flow) it is the sink, where
    the panel rejects nothing."""
    sink = (environment_w / eps_sigma_a) ** 0.25
    if capacity_w_per_k <= 0.0:
        return sink
    low, high = min(inlet_k, sink), max(inlet_k, sink)
    for _ in range(80):
        middle = 0.5 * (low + high)
        excess = (
            middle - inlet_k + (eps_sigma_a * middle**4 - environment_w) / (2.0 * capacity_w_per_k)
        )
        if excess > 0.0:
            high = middle
        else:
            low = middle
    return 0.5 * (low + high)


def rated_capacity(params):
    """`m_dot * c_p` at the published flow. The stream's temperature rise across the loads is the
    load over this whatever the flow: below the published rate the stream carries the same share
    of the load as of the flow (the loop balance keeps the rest), so the rise does not run away as
    the pump spins down."""
    return float(params["rated_flow_kg_s"]) * float(params["specific_heat_j_per_kg_k"])


def _eps_sigma_a(params):
    return (
        float(params["emissivity"])
        * float(params["stefan_boltzmann"])
        * float(params["area_effective_m2"])
    )


def _radiator_eq(inputs, params, dt):
    capacity = 0.0
    if radiator_share(inputs, params) > 0.0:
        capacity = float(inputs[params["flow_state"]]) * float(params["specific_heat_j_per_kg_k"])
    inlet = float(inputs[params["supply_state"]]) + float(inputs[params["load_state"]]) / (
        rated_capacity(params)
    )
    return radiator_mean_k(
        inlet, capacity, float(inputs[params["environment_state"]]), _eps_sigma_a(params)
    )


def _radiator_rejection(inputs, params, dt):
    surface = float(inputs[params["surface_state"]])
    return _eps_sigma_a(params) * surface**4 - float(inputs[params["environment_state"]])


def _evaporator_duty(inputs, params, dt):
    if inputs[params["feed_state"]][params["vehicle"]] != "on":
        return 0.0
    if float(inputs[params["water_state"]]) <= 0.0:
        return 0.0
    flow = float(inputs[params["flow_state"]])
    if flow <= 0.0:
        return 0.0
    capacity = flow * float(params["specific_heat_j_per_kg_k"])
    share = flow_share(inputs, params)
    rejected = float(inputs[params["rejection_state"]]) if radiator_share(inputs, params) else 0.0
    inlet = float(inputs[params["supply_state"]]) + (
        float(inputs[params["load_state"]]) - rejected
    ) / rated_capacity(params)
    setpoint = float(params["outlet_setpoint_k"])
    latched = float(inputs["evaporator_duty_w"]) > 0.0
    if not (inlet > float(params["actuation_k"]) or (latched and inlet > setpoint)):
        return 0.0
    return min(max(capacity * (inlet - setpoint), 0.0), float(params["capacity_w"]) * share)


def _coolant_loop(inputs, params, dt):
    temperature = float(inputs["coolant_loop_t"])
    rejected = float(inputs[params["rejection_state"]]) * radiator_share(inputs, params)
    net = float(inputs[params["load_state"]]) - rejected - float(inputs[params["evaporator_state"]])
    return temperature + dt * net / float(params["heat_capacity_j_per_k"])


# --------------------------------------------------------------------------------------------
# The four lumped nodes that sit on the loops.
# --------------------------------------------------------------------------------------------


def _node_capacity(params):
    return float(params["lumped_mass_kg"]) * float(params["specific_heat_j_per_kg_k"])


def _coldplate(inputs, params, dt):
    temperature = float(inputs["zone_csm_avionics_t"])
    fraction = min(float(inputs[params["flow_state"]]) / float(params["rated_flow_kg_s"]), 1.0)
    conductance = float(params["conductance_w_per_k"]) * max(fraction, 0.0)
    coolant = float(inputs[params["coolant_state"]])
    net = float(inputs[params["heat_state"]]) - conductance * (temperature - coolant)
    return temperature + dt * net / _node_capacity(params)


def _service_bay(inputs, params, dt):
    """The coldplate's balance with the loop's supply as the sink: the bay's heat is part of the
    loop's collected load, so the coolant is what carries it away."""
    temperature = float(inputs["zone_csm_service_t"])
    conductance = float(params["conductance_w_per_k"]) * flow_share(inputs, params)
    coolant = float(inputs[params["coolant_state"]])
    net = float(inputs[params["heat_state"]]) - conductance * (temperature - coolant)
    return temperature + dt * net / _node_capacity(params)


def _descent_bay(inputs, params, dt):
    """As the service bay, over a loop with no temperature or flow state: its declared supply, and
    a flow that is the LM pump's commanded state."""
    temperature = float(inputs["zone_lm_descent_t"])
    flowing = inputs[params["pump_state"]][params["pump"]] == "on"
    conductance = float(params["conductance_w_per_k"]) if flowing else 0.0
    net = float(inputs[params["heat_state"]]) - conductance * (temperature - float(params["supply_k"]))
    return temperature + dt * net / _node_capacity(params)


def _comm_amp(inputs, params, dt):
    temperature = float(inputs["comm_amp_t"])
    plate = float(inputs[params["plate_state"]])
    net = float(inputs[params["dissipation_state"]]) - float(params["conductance_w_per_k"]) * (
        temperature - plate
    )
    return temperature + dt * net / _node_capacity(params)


def _environment_hold(inputs, params, dt):
    """The radiator's absorbed environmental load, held: a declared boundary of the run (ADR 0003
    item 9). The default vehicle starts in passive thermal control; the quiet-coast scenario starts
    it in the sun-on-radiator hold. Nothing aboard moves it, so it is what it started as."""
    return float(inputs["environment_heat_w"])


RULES = {
    "environment_heat_w": _environment_hold,
    "cabin_heat_csm_w": _zone_heat,
    "cabin_heat_lm_w": _zone_heat,
    "service_bay_heat_w": _zone_heat,
    "descent_bay_heat_w": _zone_heat,
    "avionics_bay_heat_w": _zone_heat,
    "loop_primary_load_w": _loop_load,
    "loop_lm_load_w": _loop_load,
    "cabin_eq_csm_k": _cabin_eq_on_loop,
    "cabin_eq_lm_k": _cabin_eq_on_declared_supply,
    "coolant_flow_kg_s": _coolant_flow,
    "coolant_pump_running": _pump_running,
    "pump_1_speed_frac": _pump_speed,
    "radiator_eq_t": _radiator_eq,
    "radiator_rejection_w": _radiator_rejection,
    "evaporator_duty_w": _evaporator_duty,
    "coolant_loop_t": _coolant_loop,
    "zone_csm_avionics_t": _coldplate,
    "zone_csm_service_t": _service_bay,
    "zone_lm_descent_t": _descent_bay,
    "comm_amp_t": _comm_amp,
}
