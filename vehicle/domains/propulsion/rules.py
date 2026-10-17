"""The propulsion domain's rules (D5): main-engine thrust from the firing engine, and the chamber
pressure that follows it.

Every parameter is read from the state's own declaration in `components.yaml`, where its provenance
is. Each function is `rule(inputs, params, dt) -> value`.

Both rules are first-order relaxations, the same exponential map the plant's `lag` integrator uses,
written here because each state's driver is a mode (which engine is firing) rather than one edge's
quantity. Neither invents a throttle law: a firing DPS has no rated thrust in this vehicle
(`thrust_curve` is owed), so its thrust and chamber pressure are gaps rather than numbers.
"""

from __future__ import annotations

import math


def firing_engine(inputs, params):
    """The one engine whose state is in `firing_states`: `(engine, None)`, `(None, None)` when none
    fires, or `(None, why)` when more than one does."""
    firing = sorted(
        engine
        for engine, state in params["engine_states"].items()
        if str(inputs[state]) in params["firing_states"]
    )
    if len(firing) > 1:
        return None, f"engines {firing} are all firing, which no configuration of this vehicle does"
    return (firing[0] if firing else None), None


def _relax(target, current, tau, dt):
    return target + (current - target) * math.exp(-dt / tau)


def _thrust_main(inputs, params, dt):
    engine, why = firing_engine(inputs, params)
    if why:
        params.no_value(why)
        return None
    if engine is None:
        target = 0.0
    elif engine not in params["rated_thrust_n"]:
        params.no_value(
            f"the {engine} is firing and has no rated thrust here: its thrust at a throttle setting "
            "is `thrust_curve`'s owed law"
        )
        return None
    else:
        target = float(params["rated_thrust_n"][engine])
    return _relax(target, float(inputs["thrust_main_n"]), float(params["tau_s"]), dt)


def _chamber_pressure(inputs, params, dt):
    engine, why = firing_engine(inputs, params)
    if why:
        params.no_value(why)
        return None
    if engine is None:
        target = 0.0
    elif engine not in params["rated_thrust_n"]:
        params.no_value(
            f"the {engine} is firing and has no rated thrust here, so no chamber pressure is "
            "defined against it"
        )
        return None
    else:
        thrust = float(inputs[params["thrust_state"]])
        target = 100.0 * thrust / float(params["rated_thrust_n"][engine])
    return _relax(target, float(inputs["chamber_pressure_pct"]), float(params["tau_s"]), dt)


RULES = {
    "thrust_main_n": _thrust_main,
    "chamber_pressure_pct": _chamber_pressure,
}
