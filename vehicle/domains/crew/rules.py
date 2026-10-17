"""Crew domain rules (D5): where each person is, and the counts the cabins and the water tank read.

Each rule is a pure function of the tick's snapshot (`inputs`), its own state's declaration
(`params`) and the horizon (`dt`). Every table a rule uses is a parameter declared, with its
provenance, on the state in `components.yaml`; none is written here. `ask_crew` writes where a
person was sent (`crew_destination`, before the tick); these rules decide whether they got there.
"""


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


def csm_water_draw_crew(inputs, params, dt):
    """The people drinking from the CSM's potable tank, each at the planning rate."""
    return float(inputs["csm_crew_count"])


RULES = {
    "crew_location": crew_location,
    "csm_crew_count": csm_crew_count,
    "lm_crew_count": lm_crew_count,
    "csm_water_draw_crew": csm_water_draw_crew,
}
