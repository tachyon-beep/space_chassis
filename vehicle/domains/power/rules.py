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


def solve_bus(load_w, cells_in_parallel, open_circuit_v, resistance_ohm, envelope_a):
    """(current A, voltage V) of `cells_in_parallel` identical modules delivering `load_w`, or None.

    Per module V = E0 - R*i; n modules in parallel share the bus current, so the bus sees
    V = E0 - (R/n)*I. Delivering P = V*I gives (R/n)*I^2 - E0*I + P = 0, whose smaller root is the
    stable operating point (the larger is past the maximum-power point). It is written as
    2P / (E0 + sqrt(E0^2 - 4(R/n)P)), which is the same root without the cancellation at small P.
    No real root means the load exceeds E0^2 / (4R/n), more than the cells can deliver: None.
    A module current outside the published envelope is an extrapolation of the secant: None.
    """
    r_bus = float(resistance_ohm) / float(cells_in_parallel)
    e0 = float(open_circuit_v)
    p = float(load_w)
    discriminant = e0 * e0 - 4.0 * r_bus * p
    if discriminant < 0.0:
        return None
    current = 2.0 * p / (e0 + math.sqrt(discriminant))
    per_module = current / float(cells_in_parallel)
    low, high = (float(x) for x in envelope_a)
    if not low <= per_module <= high:
        return None
    return current, e0 - r_bus * current


def why_unsolved(load_w, cells_in_parallel, open_circuit_v, resistance_ohm, envelope_a):
    """The named gap behind `solve_bus`'s None: past the cells' maximum power, or a module current
    outside the published normal envelope (AOH p. 2.6-2: 400-1,420 W a module), where the secant is
    an extrapolation. Below the envelope is the case a light bus meets: under 400 W a module, so
    under 800 W on two-module bus A and 400 W on bus B."""
    n = float(cells_in_parallel)
    r_bus = float(resistance_ohm) / n
    e0 = float(open_circuit_v)
    p = float(load_w)
    if e0 * e0 - 4.0 * r_bus * p < 0.0:
        return (
            f"a load of {p:.0f} W is more than {cells_in_parallel} module(s) can deliver "
            f"(E0^2 / (4 R/n) = {e0 * e0 / (4.0 * r_bus):.0f} W)"
        )
    low, high = (float(x) for x in envelope_a)
    current = 2.0 * p / (e0 + (e0 * e0 - 4.0 * r_bus * p) ** 0.5)
    per_module = current / n
    side = "below" if per_module < low else "above"
    edge = low if per_module < low else high
    return (
        f"a load of {p:.0f} W puts each of {cells_in_parallel} module(s) at {per_module:.2f} A, "
        f"{side} the published normal envelope's {edge:.3f} A (400-1,420 W a module, AOH p. 2.6-2), "
        "where the terminal relation is an extrapolation of its secant (WP02 E-2)"
    )


def _bus_v(inputs, params, load_w):
    connected = _connected(inputs, params)
    if connected is None:
        return params.no_value("a module on this bus has no position in `source_enabled`")
    if not connected:
        return 0.0
    solved = solve_bus(
        load_w,
        len(connected),
        params["cell_open_circuit_v"],
        params["cell_resistance_ohm"],
        params["cell_current_envelope_a"],
    )
    if solved is None:
        return params.no_value(
            why_unsolved(
                load_w,
                len(connected),
                params["cell_open_circuit_v"],
                params["cell_resistance_ohm"],
                params["cell_current_envelope_a"],
            )
        )
    return solved[1]


def bus_a_v(inputs, params, dt):
    return _bus_v(inputs, params, inputs["bus_a_load_w"])


def bus_b_v(inputs, params, dt):
    return _bus_v(inputs, params, inputs["bus_b_load_w"])


def _bus_current(inputs, params, bus):
    """(bus current A, connected modules) for one entry of `buses`, or (None, why)."""
    connected = _connected(inputs, bus)
    if connected is None:
        return None, f"{bus['load']}: a module on this bus has no position in `source_enabled`"
    if not connected:
        return 0.0, connected
    load_w = inputs[str(bus["load"])]
    solved = solve_bus(
        load_w,
        len(connected),
        params["cell_open_circuit_v"],
        params["cell_resistance_ohm"],
        params["cell_current_envelope_a"],
    )
    if solved is None:
        why = why_unsolved(
            load_w,
            len(connected),
            params["cell_open_circuit_v"],
            params["cell_resistance_ohm"],
            params["cell_current_envelope_a"],
        )
        return None, f"{bus['load']}: {why}"
    return solved[0], connected


def fuel_cell_current_a(inputs, params, dt):
    """The connected modules' summed current: each bus's solve, at the bus's own load, added."""
    total = 0.0
    for bus in params["buses"]:
        current, why = _bus_current(inputs, params, bus)
        if current is None:
            return params.no_value(why)
        total += current
    return total


def fc_1_current_a(inputs, params, dt):
    """One module's own current: its bus's current shared equally among the connected modules on
    that bus (they are identical, `components.fc_[n]`), and 0 A when it is disconnected."""
    cell = params["cell"]
    for bus in params["buses"]:
        if cell not in bus["cells"]:
            continue
        current, connected = _bus_current(inputs, params, bus)
        if current is None:
            return params.no_value(connected)
        if cell not in connected:
            return 0.0
        return current / len(connected)
    return params.no_value(f"{cell} is on no bus in `buses`")


def bus_a_rated_w(inputs, params, dt):
    """The rated output of the modules connected to main bus A: what `power.load_margin_w` is
    measured against (ADR 0004 operator item 1), so a module taken off line leaves the margin."""
    connected = _connected(inputs, params)
    if connected is None:
        return params.no_value("a module on bus A has no position in `source_enabled`")
    return float(sum(params["rated_w"][cell] for cell in connected))


RULES = {
    "bus_a_load_w": bus_a_load_w,
    "bus_b_load_w": bus_b_load_w,
    "bus_a_v": bus_a_v,
    "bus_b_v": bus_b_v,
    "fuel_cell_current_a": fuel_cell_current_a,
    "fc_1_current_a": fc_1_current_a,
    "bus_a_rated_w": bus_a_rated_w,
}
