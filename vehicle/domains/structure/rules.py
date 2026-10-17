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


def latches_engaged(inputs, params, dt):
    """How many ring latches are drawn down and locked: the count the guards and the crew read."""
    return sum(1 for position in inputs["docking_latch_state"].values() if position == "engaged")


def docking_talkback(inputs, params, dt):
    """Each docking-system talkback: gray once every switched latch in its system has been actuated
    (the switches open and the parallel circuit breaks), barber pole while any one has not."""
    latches = inputs["docking_latch_state"]
    return {
        system: ("gray" if all(latches[latch] == "engaged" for latch in switched) else "barber_pole")
        for system, switched in sorted(params["switches"].items())
    }


def structural_leak_g_s(inputs, params, dt):
    """The structure's leak in excess of the nominal cabin leak: zero while every path with pressure
    behind it is sealed, and no value while one is not, because the vent rate of an open hatch or an
    unseated ring is set by an aperture and a seal this vehicle does not carry.

    A crew hatch faces space. A tunnel hatch faces the tunnel, which is itself open to space only
    when the vehicles are not docked or the ring holds fewer latches than seal it; on a sealed ring
    an open tunnel hatch joins the tunnel to its cabin and loses nothing. With both tunnel hatches
    open on a sealed ring the two cabins are one volume, so the pressure behind either crew hatch is
    the higher of the two: a pressurised CSM vents through an open LM forward hatch however empty
    the LM cabin reads."""
    floor = params["pressure_floor_psid"]
    per_psi = params["pascals_per_psi"]
    hatches = inputs["hatch_state"]
    tunnel_hatches = set(params["tunnel_hatches"])
    engaged = sum(1 for position in inputs["docking_latch_state"].values() if position == "engaged")
    docked = inputs["lm_separation_state"] == "docked"
    tunnel_sealed = docked and engaged >= params["seal_min_engaged"]
    pressure = {cabin: inputs[cabin] for cabin in set(params["hatch_cabin"].values())}
    joined = tunnel_sealed and all(hatches.get(hatch) not in (None, "latched") for hatch in tunnel_hatches)
    if joined:
        pressure = dict.fromkeys(pressure, max(pressure.values()))
    for hatch, cabin in sorted(params["hatch_cabin"].items()):
        position = hatches.get(hatch)
        if position is None:
            return params.no_value(f"{hatch} has no position; `hatch_state.initial` is owed")
        if position == "latched" or (hatch in tunnel_hatches and tunnel_sealed):
            continue
        dp = pressure[cabin] / per_psi
        if dp <= floor:
            continue
        if hatch not in tunnel_hatches:
            through = ", the two cabins joined through the open tunnel" if joined else ""
            return params.no_value(
                f"{hatch} is {position} with {dp:.2f} psid behind it{through}; its vent rate is owed "
                f"(`{hatch}.seal_leak_g_s`)"
            )
        if docked:
            return params.no_value(
                f"{hatch} is {position} with {dp:.2f} psid behind it and the docked ring has "
                f"{engaged} latches engaged, fewer than the {params['seal_min_engaged']} that seal "
                "it; the vent rate through the unseated ring seal is owed"
            )
        return params.no_value(
            f"{hatch} is {position} with {dp:.2f} psid behind it and nothing docked beyond it; "
            f"its vent rate is owed (`{hatch}.seal_leak_g_s`)"
        )
    return 0.0


def tunnel_vent_dp_psi(inputs, params, dt):
    """The pressure a tunnel hatch would open against once the tunnel is open to space: the higher
    cabin's, in psi, while the vehicles are undocked or the ring holds fewer latches than seal it,
    and zero while the tunnel is a sealed volume. Until the tunnel's own pressure is a state this is
    the one number that tells a guard a tunnel hatch faces vacuum."""
    if inputs["lm_separation_state"] == "docked" and inputs["latches_engaged"] >= params["seal_min_engaged"]:
        return 0.0
    cabins = (inputs["csm_cabin_pressure_pa"], inputs["lm_cabin_pressure_pa"])
    return max(cabins) / params["pascals_per_psi"]


RULES = {
    "arm_age_s": arm_age_s,
    "arm_state": arm_state,
    "pyro_fired": pyro_fired,
    "docking_latch_state": docking_latch_state,
    "latches_engaged": latches_engaged,
    "docking_talkback": docking_talkback,
    "structural_leak_g_s": structural_leak_g_s,
    "tunnel_vent_dp_psi": tunnel_vent_dp_psi,
}
