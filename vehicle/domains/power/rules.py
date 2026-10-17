"""Power's domain rules (D5, `plant.md` §2): the CSM's two main buses as Apollo flew them.

ADR 0003 items 1-3 (`docs/decisions/0003-quiet-coast-model-corrections.md`): no source converter, so
each main bus's voltage is an algebraic solve of the fuel-cell modules feeding it; fuel cells 1 and
2 in parallel on main bus A and fuel cell 3 on main bus B; reactants charged per ampere of module
current. Every number a rule uses is a field on its own state (`params`), with provenance there.

A rule returns `None` when it cannot give an honest value, which the plant reports as a gap on the
state: a switch map missing a load, a load beyond what the cells can deliver, or a module current
outside the published normal envelope, where the linear terminal relation is an extrapolation
(`components.fc_1.source_resistance_provenance`: "a rule must not use it there").

Each fuel-cell module is connected or not (`source_enabled`, moved by `set_source`): "one fuel cell
can be disconnected from the buses increasing the loads on the remaining fuel cells" (AOH p. 2.6-28).
A bus is solved over the modules on it that are connected, and a bus with none is dead: its loads
draw nothing and it reads 0 V, because in coast the batteries are off the main buses (TN D-7609).
"""

from __future__ import annotations

import math


def _connected(inputs, params):
    """The modules in this bus's `cells` that `source_enabled` leaves connected, in declared order.

    A module missing from the switch map is a gap, not a disconnected module: the map is the whole
    source inventory, so a missing key is a renamed or forgotten source."""
    switches = inputs["source_enabled"]
    connected = []
    for cell in params["cells"]:
        if cell not in switches:
            return None
        if switches[cell] == "on":
            connected.append(cell)
    return connected


def _enabled_load_w(inputs, params):
    """The watts the enabled loads on one bus draw, or None if a switch position is missing.

    A load in `transmitter_gated` draws only while `comms.transmitter_on` is `on` as well as its own
    switch: the amplifier's watts have one home, the load inventory, and the transmitter state says
    whether that load is drawing (ADR 0003 item 5). The transmitter is read only when it matters.
    """
    connected = _connected(inputs, params)
    if connected is None:
        return None
    if not connected:
        return 0.0
    switches = inputs["load_enabled"]
    gated = set(params["transmitter_gated"])
    total = 0.0
    for load_id, watts in params["loads_w"].items():
        if load_id not in switches:
            return None
        if switches[load_id] != "on":
            continue
        if load_id in gated and inputs["transmitter_on"] != "on":
            continue
        total += float(watts)
    return total


def bus_a_load_w(inputs, params, dt):
    return _enabled_load_w(inputs, params)


def bus_b_load_w(inputs, params, dt):
    return _enabled_load_w(inputs, params)


def solve_modules(load_w, open_circuit_v, resistances_ohm, envelope_a, below_envelope="refuse"):
    """(bus current A, voltage V, module currents A) of modules in parallel delivering `load_w`.

    Per module V = E0 - R_k*i_k, every module at the one bus voltage and the same E0 (the published
    secant, WP02 E-2), so the bus sees V = E0 - R_eq*I with R_eq = 1 / sum(1/R_k), and module k
    carries i_k = (E0 - V) / R_k: a module whose resistance has risen carries less, and the others
    more (PWR-02's "one source current falls while the others rise"). Delivering P = V*I gives
    R_eq*I^2 - E0*I + P = 0, whose smaller root is the stable operating point (the larger is past the
    maximum-power point), written 2P / (E0 + sqrt(E0^2 - 4 R_eq P)) to avoid the cancellation at
    small P. Returns (None, why) when there is no root (the load exceeds E0^2 / (4 R_eq)) or when a
    module current falls outside the published envelope, where the secant is an extrapolation —
    except below it when `below_envelope` is "extrapolate": a lightly loaded module reads the line
    between its 31 V envelope edge and its 32.30 V intercept, a bounded extrapolation, rather than
    leaving the bus with no voltage.
    """
    e0 = float(open_circuit_v)
    p = float(load_w)
    resistances = [float(r) for r in resistances_ohm]
    r_eq = 1.0 / sum(1.0 / r for r in resistances)
    n = len(resistances)
    discriminant = e0 * e0 - 4.0 * r_eq * p
    if discriminant < 0.0:
        return None, (
            f"a load of {p:.0f} W is more than {n} module(s) can deliver "
            f"(E0^2 / (4 R/n) = {e0 * e0 / (4.0 * r_eq):.0f} W)"
        )
    current = 2.0 * p / (e0 + math.sqrt(discriminant))
    volts = e0 - r_eq * current
    modules = [(e0 - volts) / r for r in resistances]
    low, high = (float(x) for x in envelope_a)
    for per_module in modules:
        if per_module < low and below_envelope == "extrapolate":
            continue
        if not low <= per_module <= high:
            side = "below" if per_module < low else "above"
            edge = low if per_module < low else high
            which = "each of" if len(set(resistances)) == 1 else "one of"
            return None, (
                f"a load of {p:.0f} W puts {which} {n} module(s) at {per_module:.2f} A, "
                f"{side} the published normal envelope's {edge:.3f} A (400-1,420 W a module, "
                "AOH p. 2.6-2), where the terminal relation is an extrapolation of its secant "
                "(WP02 E-2)"
            )
    return (current, volts, modules), None


def solve_bus(load_w, cells_in_parallel, open_circuit_v, resistance_ohm, envelope_a):
    """(current A, voltage V) of `cells_in_parallel` identical modules delivering `load_w`, or None:
    `solve_modules` with every module at one resistance, so V = E0 - (R/n)*I."""
    solved, _ = solve_modules(
        load_w, open_circuit_v, [resistance_ohm] * int(cells_in_parallel), envelope_a
    )
    return None if solved is None else solved[:2]


def why_unsolved(load_w, cells_in_parallel, open_circuit_v, resistance_ohm, envelope_a):
    """The named gap behind `solve_bus`'s None: past the cells' maximum power, or a module current
    outside the published normal envelope (AOH p. 2.6-2: 400-1,420 W a module), where the secant is
    an extrapolation. Below the envelope is the case a light bus meets: under 400 W a module, so
    under 800 W on two-module bus A and 400 W on bus B."""
    _, why = solve_modules(
        load_w, open_circuit_v, [resistance_ohm] * int(cells_in_parallel), envelope_a
    )
    return why


def _solve(inputs, params, cells, load_w):
    """((bus current, voltage, {module: current}), None) for the modules in `cells` that are
    connected, at their resistances this tick, or (None, why). A bus with no connected module is
    dead: 0 A at 0 V."""
    connected = _connected(inputs, {"cells": cells})
    if connected is None:
        return None, "a module on this bus has no position in `source_enabled`"
    if not connected:
        return (0.0, 0.0, {}), None
    resistance_of = params["resistance_of"]
    missing = [cell for cell in connected if cell not in resistance_of]
    if missing:
        return None, f"{missing} have no resistance state in `resistance_of`"
    solved, why = solve_modules(
        load_w,
        params["cell_open_circuit_v"],
        [inputs[resistance_of[cell]] for cell in connected],
        params["cell_current_envelope_a"],
        params["below_envelope"],
    )
    if solved is None:
        return None, why
    current, volts, modules = solved
    return (current, volts, dict(zip(connected, modules, strict=True))), None


def _bus_v(inputs, params, load_w):
    solved, why = _solve(inputs, params, params["cells"], load_w)
    if solved is None:
        return params.no_value(why)
    return solved[1]


def bus_a_v(inputs, params, dt):
    return _bus_v(inputs, params, inputs["bus_a_load_w"])


def bus_b_v(inputs, params, dt):
    return _bus_v(inputs, params, inputs["bus_b_load_w"])


def fuel_cell_current_a(inputs, params, dt):
    """The connected modules' summed current: each bus's solve, at the bus's own load, added."""
    total = 0.0
    for bus in params["buses"]:
        solved, why = _solve(inputs, params, bus["cells"], inputs[str(bus["load"])])
        if solved is None:
            return params.no_value(f"{bus['load']}: {why}")
        total += solved[0]
    return total


def fc_1_current_a(inputs, params, dt):
    """One module's own current, from its bus's solve, and 0 A when it is disconnected."""
    cell = params["cell"]
    for bus in params["buses"]:
        if cell not in bus["cells"]:
            continue
        solved, why = _solve(inputs, params, bus["cells"], inputs[str(bus["load"])])
        if solved is None:
            return params.no_value(f"{bus['load']}: {why}")
        return solved[2].get(cell, 0.0)
    return params.no_value(f"{cell} is on no bus in `buses`")


def bus_a_rated_w(inputs, params, dt):
    """The rated output of the modules connected to main bus A: what `power.load_margin_w` is
    measured against (ADR 0004 operator item 1), so a module taken off line leaves the margin.

    A module's rating is its power at the envelope's 27 V terminal, (E0 - 27) / R_k amperes at 27 V,
    so under the secant it scales as R / R_k from the published 1,420 W: a module whose resistance
    has risen by half has lost a third of its rating, PWR-02's own mechanism."""
    connected = _connected(inputs, params)
    if connected is None:
        return params.no_value("a module on bus A has no position in `source_enabled`")
    resistance_of = params["resistance_of"]
    nominal = float(params["cell_resistance_ohm"])
    return float(
        sum(
            params["rated_w"][cell] * nominal / float(inputs[resistance_of[cell]])
            for cell in connected
        )
    )


def _held_resistance(state_id):
    """A module's source resistance, held: nothing aboard moves it (`dX/dt = 0`). A fault (PWR-02)
    or a scenario sets it; the rule returns what it carries, so a checkpoint restores it."""

    def hold(inputs, params, dt):
        return float(inputs[state_id])

    return hold


RULES = {
    "bus_a_load_w": bus_a_load_w,
    "bus_b_load_w": bus_b_load_w,
    "bus_a_v": bus_a_v,
    "bus_b_v": bus_b_v,
    "fuel_cell_current_a": fuel_cell_current_a,
    "fc_1_current_a": fc_1_current_a,
    "bus_a_rated_w": bus_a_rated_w,
    "fc_1_resistance_ohm": _held_resistance("fc_1_resistance_ohm"),
    "fc_2_resistance_ohm": _held_resistance("fc_2_resistance_ohm"),
    "fc_3_resistance_ohm": _held_resistance("fc_3_resistance_ohm"),
}
