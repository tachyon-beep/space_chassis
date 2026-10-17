"""Crew domain rules (D5): where each person is, and the counts the cabins and the water tank read.

Each rule is a pure function of the tick's snapshot (`inputs`), its own state's declaration
(`params`) and the horizon (`dt`). Every table a rule uses is a parameter declared, with its
provenance, on the state in `components.yaml`; none is written here. `ask_crew` writes where a
person was sent (`crew_destination`, before the tick) and that they were asked (`crew_roused`);
these rules decide whether they got there, and what the flight plan has them doing.
"""

import math

US_PER_H = 3_600_000_000


def _scheduled(params, met_h):
    """The flight plan's activity at `met_h`: the row whose span holds it, and work outside them."""
    anchors = params["anchors_get_h"]
    for row in params["flight_plan"]:
        start, end = row["get_h"]
        offset = anchors[row["anchor"]]
        if start - offset <= met_h < end - offset:
            return row["activity"]
    return "work"


def _weighted(inputs, params, weights):
    """The sum over a cabin's people of a weight per activity."""
    activity = inputs["crew_activity"]
    cabin = params["cabin_stations"]
    return float(
        sum(weights[activity[p]] for p, where in sorted(inputs["crew_location"].items()) if where in cabin)
    )


def crew_clock_us(inputs, params, dt):
    """MET in whole microseconds: last tick's, plus the horizon."""
    return int(inputs["crew_clock_us"]) + round(dt * 1_000_000)


def crew_scheduled(inputs, params, dt):
    """The flight plan's period at this MET, with last tick's beside it."""
    return {
        "previous": inputs["crew_scheduled"]["now"],
        "now": _scheduled(params, inputs["crew_clock_us"] / US_PER_H),
    }


def _rest_edge(scheduled):
    """Whether a scheduled rest period began or ended at this tick."""
    return (scheduled["previous"] == "sleep") != (scheduled["now"] == "sleep")


def _roused(inputs):
    """Who a question is keeping awake this tick. `crew_roused` is on the sentinel and clears after
    the crew-day states have read it, so a rest period's first and last tick read it as cleared here
    rather than a tick late."""
    if _rest_edge(inputs["crew_scheduled"]):
        return dict.fromkeys(inputs["crew_roused"], False)
    return inputs["crew_roused"]


def crew_roused(inputs, params, dt):
    """Held, except that every flag clears when a scheduled rest period begins or ends: a question
    keeps a person awake through the rest of one period, and no further."""
    return dict(_roused(inputs))


def crew_rest_owed_s(inputs, params, dt):
    """Rest lost to a question grows through a scheduled rest period, and is repaid as sleep outside
    one until it is gone."""
    asleep = inputs["crew_scheduled"]["now"] == "sleep"
    roused = _roused(inputs)
    owed = {}
    for person, seconds in sorted(inputs["crew_rest_owed_s"].items()):
        if asleep and roused[person]:
            owed[person] = seconds + dt
        elif not asleep and not roused[person] and seconds > 0:
            owed[person] = max(0.0, seconds - dt)
        else:
            owed[person] = seconds
    return owed


def crew_activity(inputs, params, dt):
    """The flight plan's period at this MET for everyone, except a person a question has roused is
    awake through a rest period, and a person owed rest sleeps outside one."""
    scheduled = inputs["crew_scheduled"]["now"]
    roused = _roused(inputs)
    owed = inputs["crew_rest_owed_s"]
    activity = {}
    for person in sorted(roused):
        if scheduled == "sleep":
            activity[person] = "work" if roused[person] else "sleep"
        elif owed[person] > 0 and not roused[person]:
            activity[person] = "sleep"
        else:
            activity[person] = scheduled
    return activity


def _reachable(params, configuration, vehicle):
    """The stations a person in `vehicle` can be sent to in this configuration: one list when the
    vehicles are joined or only one is crewed, one list per vehicle when they are apart."""
    table = params["reachable_by_configuration"][configuration]
    if isinstance(table, tuple):
        return table
    return table[vehicle]


def crew_location(inputs, params, dt):
    """Each person at the station they were sent to while it is reachable from the vehicle the
    configuration puts them in, and in their own seat in that vehicle otherwise."""
    configuration = inputs["configuration"]
    vehicles = params["vehicle_by_configuration"].get(configuration)
    if vehicles is None:
        return params.no_value(
            f"configuration {configuration!r} has no row in `vehicle_by_configuration`"
        )
    stations = params["stations"]
    sent = inputs["crew_destination"]
    placed = {}
    for person in sorted(stations):
        vehicle = vehicles[person]
        home = stations[person][vehicle]
        destination = sent[person]
        if destination in _reachable(params, configuration, vehicle):
            placed[person] = destination
        else:
            placed[person] = home
    return placed


def csm_crew_count(inputs, params, dt):
    """The people breathing the CSM's cabin air: its three stations and the tunnel."""
    cabin = params["cabin_stations"]
    return float(sum(1 for where in inputs["crew_location"].values() if where in cabin))


def lm_crew_count(inputs, params, dt):
    """The people breathing the LM's cabin air; a person on the surface is on the suit's loop."""
    cabin = params["cabin_stations"]
    return float(sum(1 for where in inputs["crew_location"].values() if where in cabin))


def crew_availability(inputs, params, dt):
    """Resting while asleep, on suit on the surface, available otherwise; incapacitated holds."""
    activity = inputs["crew_activity"]
    location = inputs["crew_location"]
    available = {}
    for person, previous in sorted(inputs["crew_availability"].items()):
        if previous == "incapacitated":
            available[person] = previous
        elif location[person] == "surface_eva":
            available[person] = "suit"
        elif activity[person] == "sleep":
            available[person] = "resting"
        else:
            available[person] = "available"
    return available


def csm_metabolic_crew(inputs, params, dt):
    """The CSM cabin's awake-equivalents: each person there at their activity's metabolic factor."""
    return _weighted(inputs, params, params["metabolic_factor"])


def lm_metabolic_crew(inputs, params, dt):
    """The LM cabin's awake-equivalents."""
    return _weighted(inputs, params, params["metabolic_factor"])


def csm_water_draw_crew(inputs, params, dt):
    """The CSM's potable-water drinkers at the planning rate, weighted by when in the day they draw."""
    return _weighted(inputs, params, params["draw_weight"])


def crew_busy_s(inputs, params, dt):
    """The seconds a question still occupies each person: set by `ask_crew`, counted down here."""
    return {person: max(0.0, seconds - dt) for person, seconds in sorted(inputs["crew_busy_s"].items())}


def crew_workload_index(inputs, params, dt):
    """A first-order lag toward the crew's demand: the highest of the people not incapacitated, each
    0 asleep, 1 at a meal or at work, and 2 while a question keeps them busy."""
    demand = params["demand"]
    present = [
        p for p, state in sorted(inputs["crew_availability"].items()) if state != "incapacitated"
    ]
    target = max(
        (
            demand["busy"] if inputs["crew_busy_s"][p] > 0 else demand[inputs["crew_activity"][p]]
            for p in present
        ),
        default=0.0,
    )
    previous = float(inputs["crew_workload_index"])
    return previous + (target - previous) * (1.0 - math.exp(-dt / params["tau_s"]))


def crew_workload(inputs, params, dt):
    """The band the workload index is in."""
    index = inputs["crew_workload_index"]
    bands = params["bands"]
    if index < bands["low"]:
        return "low"
    if index < bands["medium"]:
        return "medium"
    return "high"


RULES = {
    "crew_clock_us": crew_clock_us,
    "crew_scheduled": crew_scheduled,
    "crew_roused": crew_roused,
    "crew_rest_owed_s": crew_rest_owed_s,
    "crew_activity": crew_activity,
    "crew_location": crew_location,
    "crew_availability": crew_availability,
    "csm_crew_count": csm_crew_count,
    "lm_crew_count": lm_crew_count,
    "csm_metabolic_crew": csm_metabolic_crew,
    "lm_metabolic_crew": lm_metabolic_crew,
    "csm_water_draw_crew": csm_water_draw_crew,
    "crew_busy_s": crew_busy_s,
    "crew_workload_index": crew_workload_index,
    "crew_workload": crew_workload,
}
