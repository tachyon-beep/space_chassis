"""Structure domain rules (D5): the arm token's lifecycle, the pyros, the ring latches and the leak.

Each rule is a pure function of the tick's snapshot (`inputs`), its own state's declaration
(`params`) and the horizon (`dt`). Every number a rule uses is a parameter declared, with its
provenance, on the state in `components.yaml`; none is written here. The commands write the
transitions a fleet causes (`command_value`, applied before the tick); these rules write the ones
that follow from them or from time.
"""


def arm_age_s(inputs, params, dt):
    """Each token's age: advanced by the horizon while it is armed, held otherwise. Arming writes zero
    (`command_value`), so a re-arm starts the window again."""
    state = inputs["arm_state"]
    return {
        event: (age + dt if state[event] == "armed" else age)
        for event, age in inputs["arm_age_s"].items()
    }


def arm_state(inputs, params, dt):
    """An armed token whose age has reached the window is `expired`; every other position holds.
    `consumed` and `expired` are both terminal until the next arm, which is the audit trail the
    two-step exists to keep."""
    ttl = params["ttl_s"]
    age = inputs["arm_age_s"]
    return {
        event: ("expired" if position == "armed" and age[event] >= ttl else position)
        for event, position in inputs["arm_state"].items()
    }


def pyro_fired(inputs, params, dt):
    """A device is fired once any executed event declares it in its `fires_<event>` list, and unfired
    otherwise. Computed from the record of events rather than from last tick's map, so a fired device
    stays fired because the record never forgets an event. An event whose list is unset refuses on the
    ticks after it has been executed, and only then."""
    fired = dict.fromkeys(params["devices"], False)
    for event, done in sorted(inputs["events_fired"].items()):
        if not done:
            continue
        for device in params[f"fires_{event}"]:
            if device not in fired:
                return params.no_value(
                    f"`fires_{event}` names {device!r}, which is not one of this state's `devices`"
                )
            fired[device] = True
    return fired


def docking_latch_state(inputs, params, dt):
    """Every latch follows the `all` drive: engaged under `engage`, released under `release`. A latch
    that has failed is the fault path's to hold, and nothing here can fail one yet; a `one` drive acts
    only on a failed latch, so until the fault path supplies one it has nothing to act on."""
    target = {"engage": "engaged", "release": "released"}[inputs["latch_drive"]["all"]]
    return dict.fromkeys(params["latches"], target)


def structural_leak_g_s(inputs, params, dt):
    """The structure's leak in excess of the nominal cabin leak: zero while every path with pressure
    behind it is sealed, and no value while one is not, because the vent rate of an open hatch or an
    unseated ring is set by an aperture and a seal this vehicle does not carry."""
    floor = params["pressure_floor_psid"]
    per_psi = params["pascals_per_psi"]
    hatches = inputs["hatch_state"]
    for hatch, cabin in sorted(params["hatch_cabin"].items()):
        position = hatches[hatch]
        if position == "latched":
            continue
        dp = inputs[cabin] / per_psi
        if dp > floor:
            return params.no_value(
                f"{hatch} is {position} with {dp:.2f} psid behind it; its vent rate is owed "
                f"(`{hatch}.seal_leak_g_s`)"
            )
    if inputs["lm_separation_state"] == "docked":
        engaged = sum(1 for position in inputs["docking_latch_state"].values() if position == "engaged")
        if engaged < params["seal_min_engaged"]:
            return params.no_value(
                f"the docked ring has {engaged} latches engaged, fewer than the "
                f"{params['seal_min_engaged']} that seal it; the tunnel's leak is owed (`tunnel.volume_m3`)"
            )
    return 0.0


RULES = {
    "arm_age_s": arm_age_s,
    "arm_state": arm_state,
    "pyro_fired": pyro_fired,
    "docking_latch_state": docking_latch_state,
    "structural_leak_g_s": structural_leak_g_s,
}
