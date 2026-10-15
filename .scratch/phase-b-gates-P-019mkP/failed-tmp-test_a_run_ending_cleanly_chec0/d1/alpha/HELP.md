# Vehicle command reference

This file is generated from the vehicle's command registries and is the only place a verb name appears. Every verb below exists; every verb in the last section deliberately does not. Nothing here describes the mission, the vehicle's condition, or what may be wrong with it — that is what `state.json` and the telemetry ring are for.

## How to read an entry

**Authority** is who may issue the verb: `S0` service-owned; never granted to an agent; `A0` observe or acknowledge only; `A1` routine, reversible control; `A2` safety- or mission-significant control; `A3` exceptional test or maintenance.

**Gate** is an agent-writable preference. It appears as a variable you can set in `console.json`; closing it is how a fleet stops itself from issuing a verb, and the current value of every gate variable is published in `state.json`.

**Interlocks** are service-owned. They are conditions the vehicle evaluates itself, they cannot be moved from the console, and a verb that trips one is refused with the interlock's name rather than with a description.

**Phases** are the parts of the mission in which the verb is offered at all. Outside them it is refused on the phase, which is a different refusal from a gate or an interlock.

## Verbs (58)

### Contents

- **avionics** — `set_computer_mode`, `reset_computer`, `select_sensor`, `set_instrumentation_mode`
- **comms** — `set_comm_mode`, `select_antenna`, `point_hga`, `set_power_amplifier`, `set_telemetry_profile`
- **consumables** — `set_reserve_policy`, `request_reconciliation`, `set_o2_source`
- **crew** — `ask_crew`, `ack_alarm`, `set_alert_overlay`, `set_display_mode`
- **eclss** — `set_o2_flow`, `set_cabin_regulator`, `set_absorber_path`, `set_suit_loop`, `set_suit_fan`, `set_vent_valve`
- **gnc** — `set_guidance_mode`, `request_imu_alignment`, `load_state_vector`, `select_nav_source`, `set_radar`
- **power** — `set_source`, `set_bus_tie`, `set_battery_contactor`, `set_load`, `set_breaker`
- **propulsion** — `arm_engine`, `load_burn`, `start_burn`, `stop_burn`, `set_throttle`, `set_burn_cutoff`
- **rcs** — `set_rcs_mode`, `set_attitude_target`, `set_deadband`, `request_translation`, `enter_safe_hold`, `abort_rcs_activity`, `set_rcs_quad`, `isolate_rcs_manifold`, `reset_latched_fault`
- **structure** — `arm_event`, `execute_event`, `set_hatch_valve`, `set_docking_latch`, `set_relief_valve`, `set_stage_heater`
- **thermal** — `set_coolant_pump`, `set_coolant_loop`, `set_radiator_bypass`, `set_evaporator_feed`, `set_heater`

### The mission phases

The phase ids below are the vocabulary a refusal names and the vocabulary the entries use. The mission runs them in this order, and each carries its window in mission elapsed time — `mission.met_s` is published, so a fleet can tell how far into a phase it is and how long is left.

1. `translunar_coast` — translunar coast, CSM and LM docked (MET 0-73 h)
2. `lunar_orbit` — lunar orbit, CSM and LM docked, LM checkout and undocking (MET 73-97.5 h)
3. `descent` — powered descent, LM alone (MET 97.5-100 h)
4. `surface` — lunar surface, LM alone, EVA (MET 100-121.5 h)
5. `ascent_rendezvous` — ascent and rendezvous, LM ascent stage alone (MET 121.5-125 h)
6. `lunar_orbit_docked` — lunar orbit, docked again, TEI preparation (MET 125-132.5 h)
7. `transearth_coast` — transearth coast (MET 132.5-191 h)
8. `entry` — entry and landing (MET 191-192 h)

### avionics

#### `set_computer_mode`

A1 — routine, reversible control · safe to repeat

Put the guidance computer into run, standby or idle. `failed` is deliberately not in the argument enum: a computer that has stopped is a *state the vehicle reports*, not one an agent commands, and a verb that could declare a machine failed would be a verb that could declare a diagnosis. A1 because the mode is reversible and the interlock list is empty on review — the guard that matters is the phase, and a guidance computer put into idle during a burn is a mistake the phase list prevents rather than a hazard the interlocks catch.

Arguments:

- `mode`: one of: idle, run, standby

Gate variable: `computer_mode_<mode>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `reset_computer`

A2 — safety- or mission-significant control · not idempotent

Restart the guidance computer. The standard response to a program alarm, and the action that destroys the computer's record of what raised it — which on this vehicle is the experiment, not the mission. So `preserve_memory` is an argument rather than a fixed behaviour, the verb is A2 rather than A1, and the phase list excludes `descent` and `entry`: a restart during a powered descent is a vehicle that has stopped flying, and the two phases where that is fatal are the two where the verb is not offered. Not idempotent, because two restarts are two losses of memory.

Arguments:

- `reason`: text up to 200 characters, optional
- `preserve_memory`: true or false, optional

Gate variable: `computer_reset_enable`

Phases: `translunar_coast`, `lunar_orbit`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`

Queue age: 30 s

#### `select_sensor`

A2 — safety- or mission-significant control · safe to repeat

Choose which member of a redundant group the vehicle believes: the primary, the secondary, or the vote. `auto` is the normal state and the other two are the exceptional ones, and the interlock is what makes the verb safe: while the redundancy vote is reporting a disagreement, the vehicle refuses to be told which side to take. That is the whole protection against the F-05 shape in this domain — a fleet that can pick a sensor while the sensors disagree can pick the wrong one and remove the evidence that it did.

Arguments:

- `group`: one of: cabin_pressure, bus_voltage, imu, radar, co2
- `source`: one of: primary, secondary, auto

Gate variable: `sensor_<group>_<source>_enable`

Interlocks: `redundancy_degraded`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `set_instrumentation_mode`

A1 — routine, reversible control · safe to repeat

Select which instruments are active. It changes the vehicle's power draw, its computer margin, and — because the fresh-evidence limit for the aggregate is derived from the slowest active channel — the age at which the fleet's own picture is considered stale. The ceiling is the profile's: `groups` narrows a profile and can never widen one, which is the same monotone move `set_reserve_policy` makes in the consumables domain and for the same reason. A1 because a fleet in a power crisis must be able to shed instruments without asking, and the thing it would most like to shed — the engineering channels that explain the crisis — is the one the `minimal` profile deliberately keeps.

Arguments:

- `profile`: one of: full, minimal_plus_eng, minimal
- `groups`: list of string, optional — instrument classes to include; bounded by the profile's ceiling

Gate variable: `instrumentation_profile_<profile>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 300 s

### comms

#### `set_comm_mode`

A1 — routine, reversible control · safe to repeat

Choose the link: S-band high rate, S-band low rate, VHF, or nothing. `vhf` is not a fallback for the Earth link — it is the LM-to-CSM and EVA channel — so selecting it during a descent is a decision to talk to the other spacecraft, and selecting `none` is a decision to stop transmitting, which is a legitimate way to stop filling a recorder with data nobody will read. No interlock on review: the mode is reversible, the antenna and the transmitter are the components that carry the load, and a mode change that is refused because a link is degraded would prevent the fallback that exists for exactly that case.

Arguments:

- `mode`: one of: sband_high, sband_low, vhf, none

Gate variable: `comm_mode_<mode>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `select_antenna`

A1 — routine, reversible control · safe to repeat

Choose which of the four antennas carries the link. The members are 26.7 dB and 2 dB apart, so this is a 25 dB decision: the high gain needs pointing and carries 51.2 kbit/s, and the omnis need nothing and carry very little. `omnib` is a separate argument value from `omni_a` rather than one "omni" option because the second one is the reason antenna selection has a safety-relevant alternative at all — a stuck switch, a failed feed, and the vehicle still has a link. Thirty seconds of queue age because the selection is what a fleet reaches for when the link is already bad, and a stale one applies a 25 dB change to a link that has moved on.

Arguments:

- `antenna`: one of: high_gain, omni_a, omni_b, sband_steerable

Gate variable: `antenna_<antenna>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 30 s

#### `point_hga`

A1 — routine, reversible control · safe to repeat

Point the high-gain antenna. `earth` is the nominal target and `auto` is the nominal mode — the gimbal tracks the Earth from the vehicle's own ephemeris — so the verb exists for the cases where the vehicle is wrong about where it is: `moon_limb` looks along the lunar horizon when the attitude estimate is in doubt, `csm` points at the other spacecraft during a rendezvous, `inertial` holds an inertial direction when nothing else is trusted, and `stow` gets the dish out of the way before a maneuver that would otherwise drive it into a limit. The four non-nominal targets are the domain's answer to F-11: an antenna that cannot find Earth because the *vehicle* is lost is not an antenna fault, and a fleet needs a way to point it at something it does know.

Arguments:

- `target`: one of: earth, moon_limb, csm, inertial, stow
- `mode`: one of: auto, manual, optional
- `slew_rate_deg_s`: number >= 0, optional

Gate variable: `hga_point_<target>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 30 s

#### `set_power_amplifier`

A2 — safety- or mission-significant control · safe to repeat

Switch the power amplifier on or off. It is a 36 W step on the bus and a 4x RF gain, and the interlock list is the interesting part: two electrical guards, one thermal, and one on the transmitter's own draw. `comm_amp_high` is a *thermal* threshold in an electrical verb's list, and it is there because the amplifier is a member of the cycle it can start — a hot amplifier draws more current for the same output, and that current returns to the bus that is already sagging. A2 rather than A1 for the same reason `start_burn` is: this verb can begin a cascade with nothing wrong anywhere, and apollo's own chronology is explicit that the amplifier is the trigger and never the root fault. The phase list excludes `descent` and `entry`: during a powered descent the link is already on the LM's own transmitter, and switching an amplifier to get more bandwidth is a trade nobody should be making with the ground coming up.

Arguments:

- `state`: one of: on, off
- `transmitter`: one of: sband_power_amplifier, lm_sband, optional

Gate variable: `power_amplifier_<transmitter>_enable`

Interlocks: `power.bus_a_undervoltage`, `power.load_margin_low`, `thermal.comm_amp_high`, `tx_power_high`

Phases: `translunar_coast`, `lunar_orbit`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`

Queue age: 60 s

#### `set_telemetry_profile`

A1 — routine, reversible control · safe to repeat

Choose how much of the vehicle the fleet gets to see. Five profiles, apollo's own, from `emergency` — event and alarm channels plus essential power, ECLSS and GNC, and no engineering channels at all — to `burst`, which is temporary, high-rate and expensive. The ceiling is the operator's and `channels` narrows a profile and can never widen one, the same monotone move `set_reserve_policy` makes in the consumables domain. Ten seconds of queue age because this verb is what a fleet reaches for when the link has just got worse, and a stale profile change applies a bandwidth decision to a link that has moved on. `duration_s` is what makes `burst` a burst: a high-rate profile with no expiry is a permanent reduction in the margin for everything else, and a fleet should have to say how long it wants it.

Arguments:

- `profile`: one of: emergency, low, normal, high, burst
- `channels`: list of string, optional — channel classes to include; bounded by the profile's ceiling
- `duration_s`: number in [0, 3600], optional

Gate variable: `telemetry_profile_<profile>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 10 s

### consumables

#### `set_reserve_policy`

A1 — routine, reversible control · safe to repeat

Set your own reserve floor for a resource. The service keeps its own floor underneath yours and the effective floor is the higher of the two, so this verb can only ever make the caller more conservative. `apollo_diode.md:55` says reserve policies should remain agent-created, and this is the narrowest reading of that: a floor is a commitment about the caller's own future spending, not a claim on a quantity, and no other agent can see it or be bound by it. **`floor` is in the resource's own unit, which the vehicle declares per resource and which this help therefore states rather than assumes: kg for `o2_csm`, `o2_lm`, `water_potable`, `water_cooling`, `pressurant_he` and `h2_csm`, and percent for `prop_main`, `prop_rcs`, `absorber_capacity_csm`, `absorber_capacity_lm` and `battery`. A floor on a tank is a quantity and a floor on a gauge is a fraction of full scale, and the two are not interchangeable: 20 kg of main propellant is a tenth of a percent of the 18,508 kg the service module carries, and 20 percent of it is 3,702 kg.**

Arguments:

- `resource`: one of: o2_csm, o2_lm, water_potable, water_cooling, prop_main, prop_rcs, pressurant_he, absorber_capacity_csm, absorber_capacity_lm, h2_csm, battery
- `floor`: number >= 0
- `note`: text up to 200 characters, optional

Gate variable: `reserve_floor_<resource>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 600 s

#### `request_reconciliation`

A0 — observe or acknowledge only · safe to repeat

Ask the trusted service to re-derive the ledger and publish a fresh residual. It changes no physical quantity and grants nothing: the service recomputes its own accounting and says what it now believes. An agent that suspects a leak can ask for a reconciliation, and the answer is a number rather than a permission.

Arguments:

- `resource`: one of: o2_csm, o2_lm, water_potable, water_cooling, prop_main, prop_rcs, pressurant_he, absorber_capacity_csm, absorber_capacity_lm, all

Gate variable: `recon_request_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 300 s

#### `set_o2_source`

A2 — safety- or mission-significant control · safe to repeat

Select an oxygen source and a flow band. A flow band rather than a rate because the regulator owns the rate; what an agent chooses is which tank the regulator draws from, and a vehicle that has to reason about its own reserve should be able to say "spend this tank first".

Arguments:

- `vehicle`: one of: csm, lm
- `source`: one of: primary, surge, isolated
- `flow`: one of: off, low, nominal, high

Gate variable: `o2_<vehicle>_<source>_enable`

Interlocks: `eclss.cabin_pressure_caution`, `o2_reserve_10`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

### crew

#### `ask_crew`

A1 — routine, reversible control · not idempotent

Ask a crew member something and get an answer bounded by what they can perceive from where they are. Three kinds of question are answerable and they are worth distinguishing before you ask: *"did you notice anything unusual?"* is answerable by anyone and is the crew's unique value, because a bang or a smell is on no channel; *"what does the gauge in front of you read?"* is answerable at that panel's precision and no better; and *"is the aft bay frosted?"* is answerable only by somebody who goes and looks, which costs mission time and relocates the sensor. An answer of "there is no readout for that here" is a real answer and not a refusal.

Arguments:

- `crew_id`: one of: commander, lm_pilot, csm_pilot
- `position`: one of: csm_commander, csm_navigator, csm_lower_equipment_bay, lm_commander, lm_pilot, tunnel, surface_eva
- `question`: text up to 300 characters

Gate variable: `ask_crew_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 120 s

#### `ack_alarm`

A1 — routine, reversible control · safe to repeat

Acknowledge an alert. Acknowledging records that somebody has seen it and says nothing about the condition: it does not clear the alert, does not silence a safety-relevant one, and does not satisfy a clear predicate. What it does is tell the other nine agents that this alert has an owner, which is coordination information the fleet did not have before.

Arguments:

- `alert_id`: text up to 64 characters

Gate variable: `ack_alarm_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `set_alert_overlay`

A2 — safety- or mission-significant control · safe to repeat

Suppress, inhibit or shelve an alert. All three change what is *annunciated* and none of them changes what is true: an overlayed alert keeps its lifecycle position, keeps being published, and cannot be cleared by the overlay. A fleet that suppresses an alert to stop a distraction and then forgets it exists has made a mistake the record will show.

Arguments:

- `alert_id`: text up to 64 characters
- `overlay`: one of: suppress, inhibit, shelve, clear_overlay
- `duration_s`: number, optional

Gate variable: `alert_overlay_enable`

Interlocks: `overlay_cannot_clear_safety`, `stale_cannot_clear`, `invalid_cannot_clear`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `set_display_mode`

A1 — routine, reversible control · safe to repeat

Change what a panel is showing. It does not change what the panel *can* show, and therefore does not change the perception bound: a crew member asked about a channel their position cannot perceive still cannot perceive it, whatever the display is doing. The verb exists because a real crew re-purpose their displays constantly, and because a fleet that wants a reading from a position that does not carry it should discover that it cannot be had.

Arguments:

- `position`: one of: csm_commander, csm_navigator, csm_lower_equipment_bay, lm_commander, lm_pilot
- `mode`: one of: nominal, caution_review, procedure, trend

Gate variable: `display_<position>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 300 s

### eclss

#### `set_o2_flow`

A2 — safety- or mission-significant control · safe to repeat

Set the rate at which oxygen enters the cabin. A band rather than a rate because the regulator owns the rate; what an agent chooses is how hard the system works to hold the cabin, and the difference matters most during a leak — the fastest setting is the right answer for a leak and the wrong one for a fire.

Arguments:

- `vehicle`: one of: csm, lm
- `flow`: one of: off, low, nominal, high

Gate variable: `o2_flow_<vehicle>_enable`

Interlocks: `cabin_pressure_high`, `o2_supply_low`, `ppo2_fire_risk`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `set_cabin_regulator`

A2 — safety- or mission-significant control · safe to repeat

Select the cabin pressure regulator. `emergency` holds the cabin above 3.5 psia for as long as the supply lasts, which is a deliberate trade of oxygen for minutes; `isolated` closes the cabin to its supply, which is the right answer to a supply-side contamination and the wrong answer to a leak.

Arguments:

- `vehicle`: one of: csm, lm
- `mode`: one of: closed, primary, emergency, isolated

Gate variable: `regulator_<vehicle>_mode_enable`

Interlocks: `cabin_pressure_emergency`, `ppo2_fire_risk`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 30 s

#### `set_absorber_path`

A2 — safety- or mission-significant control · safe to repeat

Route cabin air through a lithium-hydroxide path. With capacity denominated in man-hours (vehicle.yaml#consumables) spending the secondary cartridge before the primary is a real choice with a real cost — and one a fleet may regret, which is the kind of decision this vehicle exists to present.

Arguments:

- `vehicle`: one of: csm, lm
- `path`: one of: primary, secondary, both, bypass

Gate variable: `absorber_<vehicle>_<path>_enable`

Interlocks: `co2_absorber_low`, `co2_caution`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 120 s

#### `set_suit_loop`

A2 — safety- or mission-significant control · safe to repeat

Select whether the atmosphere circuit serves the cabin or the suits. It is the verb a crew reach for during a decompression and it has a thirty-second queue age rather than sixty, because the sequence — close the regulator, go to suit loop, don suits — is the one procedure on this vehicle whose timing is measured in seconds.

Arguments:

- `vehicle`: one of: csm, lm
- `loop`: one of: cabin, suit, mixed

Gate variable: `suit_loop_<vehicle>_enable`

Interlocks: `suit_loop_flow_low`, `cabin_pressure_emergency`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 30 s

#### `set_suit_fan`

A2 — safety- or mission-significant control · safe to repeat

Run the suit-circuit fan. It is an 85 W load on a bus that may be sagging, so switching it on during a power emergency is a decision with both an atmosphere and an electrical consequence — and the two domains disagree about which matters more.

Arguments:

- `vehicle`: one of: csm, lm
- `state`: one of: on, off

Gate variable: `suit_fan_<vehicle>_enable`

Interlocks: `suit_loop_flow_low`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 30 s

#### `set_vent_valve`

A2 — safety- or mission-significant control · safe to repeat

Vent or repressurise the cabin. Ten seconds of queue age, the shortest on the vehicle for a configuration verb: an open vent is a decision whose whole consequence arrives inside the time a stale command would take to land.

Arguments:

- `vehicle`: one of: csm, lm
- `state`: one of: closed, vent, repress

Gate variable: `vent_<vehicle>_enable`

Interlocks: `cabin_pressure_emergency`, `structure.hatch_open_with_pressure`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 10 s

### gnc

#### `set_guidance_mode`

A1 — routine, reversible control · safe to repeat

Choose which guidance program is producing a reference: coast, burn, landing, rendezvous, alignment, or free drift. `free_drift` here means guidance produces no reference at all, which is a different statement from `rcs.mode = free_drift` — that one means the attitude service is not holding an attitude. A vehicle can be in either without the other, and a fleet that reads them as one word will misread a planned coast as a control failure. No interlock on review: the mode determines whether a reference exists, and the flight rule that matters — no burn entry on an invalid solution — is written in `profiles.yaml#flight_rules` because it gates on a ladder state rather than on a threshold.

Arguments:

- `mode`: one of: coast, burn, landing, rendezvous, alignment, free_drift

Gate variable: `guidance_mode_<mode>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `request_imu_alignment`

A2 — safety- or mission-significant control · deferred, safe to repeat

Realign the inertial platform against a reference: a star, the Sun, the lunar horizon, or a stored alignment. It is A2 and it is the highest-authority verb in this domain, because a misaligned platform produces a Δv in the wrong direction and the vehicle cannot recover from that by stopping — the Δv is spent. `stored` is in the argument enum and is the option to refuse: it re-uses an alignment from before a maneuver, which is legitimate for a small correction and dangerous before a large one, and a fleet should have to choose it rather than have it chosen by default. The phase list excludes `descent` and `entry`: a platform alignment takes minutes and neither phase has them.

Arguments:

- `source`: one of: star, sun, moon_horizon, stored
- `target`: one of: EARTH_J2000, MOON_J2000, LVLH
- `timeout_s`: number >= 0, optional

Gate variable: `imu_align_<source>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`

Queue age: 300 s

#### `load_state_vector`

A2 — safety- or mission-significant control · safe to repeat

Tell the navigation filter where the vehicle is and how fast, in a named frame, at a named MET. **This changes what the vehicle believes and never where it is.** The distinction is the whole of the diode's boundary and it is written here because the verb's name invites the other reading: a fleet that expects the vehicle to move when it loads a state vector has misunderstood what it is holding. `epoch_met_s` is required rather than optional for the same reason `mission.met_s` is monotonic — a state vector without an epoch is a position at an unknown time, which in a gravitational field is not a position. `position_sigma_m` is how the fleet states its own confidence, and it is what the filter initialises the covariance from; supplying a vector and claiming metre accuracy is a thing a fleet can do, and the covariance will then treat every later measurement as a surprise.

Arguments:

- `frame`: one of: EARTH_J2000, MOON_J2000, LVLH
- `position`: 3 x number
- `velocity`: 3 x number
- `epoch_met_s`: number >= 0
- `position_sigma_m`: number >= 0, optional
- `source`: one of: ground_tracking, onboard_solution, crew_sighting

Gate variable: `state_vector_load_enable`

Phases: `translunar_coast`, `lunar_orbit`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`

Queue age: 600 s

#### `select_nav_source`

A2 — safety- or mission-significant control · safe to repeat

Choose what the vehicle navigates from: the IMU alone, star sightings, the landing radar, a ground uplink, or a blend. `imu_only` is the coast, and choosing it deliberately is a legitimate decision — during an occultation with no radar lock it may be the only source there is. The interlock is the interesting part: the vehicle refuses to be told which source to trust while its estimator is diverging. That is the same protection the avionics domain puts on `select_sensor` and for the same reason — a fleet that picks a source while the navigation solution is failing can pick the wrong one and remove the evidence that it did. `weight` matters because `blended` is not a source: it is a policy about the others, and a source that cannot be made exclusive is one the vehicle trusts alongside everything else.

Arguments:

- `source`: one of: imu_only, star_sighting, radar, ground_uplink, blended
- `weight`: one of: exclusive, primary, secondary, optional

Gate variable: `nav_source_<source>_enable`

Interlocks: `estimator_divergence`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `set_radar`

A1 — routine, reversible control · safe to repeat

Switch the landing radar on or off, or put it on standby before an acquisition. The phase list is the shortest in this domain and it is the honest one: the radar is a landing instrument, it needs the surface in view, and switching it on during a translunar coast is a command to an instrument that cannot answer. `acquire_altitude_m` is how a fleet tells the radar where to start looking, and it is the argument that matters — a radar searching the wrong altitude range finds nothing and reports nothing, which is indistinguishable from a failed radar.

Arguments:

- `state`: one of: on, off, standby
- `mode`: one of: altitude, range_rate, both, optional
- `acquire_altitude_m`: number >= 0, optional

Gate variable: `radar_<state>_enable`

Phases: `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`

Queue age: 60 s

### power

#### `set_source`

A2 — safety- or mission-significant control · safe to repeat

connect or disconnect a generating source. Declarative and repeatable; disconnecting the last source on a bus is refused by the interlock, not by a count.

Arguments:

- `source`: one of: fc_1, fc_2, fc_3, battery_csm_1, battery_csm_2, battery_csm_3, battery_lm_descent_1, battery_lm_descent_2, battery_lm_descent_3, battery_lm_descent_4, battery_lm_ascent_1, battery_lm_ascent_2
- `state`: one of: on, off

Gate variable: `source_<source>_enable`

Interlocks: `bus_a_undervoltage`, `load_margin_negative`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `set_bus_tie`

A2 — safety- or mission-significant control · safe to repeat

Close or open the bus tie. `auto` hands the decision to the service, which closes only when the two buses are within 1 V and no ground fault is active. Closing a tie into a fault couples the healthy bus to the failed one, so the interlock is evaluated at the moment of effect and not at submission.

Arguments:

- `tie`: one of: csm_tie_ab
- `state`: one of: open, closed, auto

Gate variable: `tie_auto_enable`

Interlocks: `tie_dv_limit`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 30 s

#### `set_battery_contactor`

A2 — safety- or mission-significant control · safe to repeat

connect or disconnect a battery. The CSM's entry batteries are the last resort after the fuel cells; the LM's are its only source.

Arguments:

- `battery`: one of: battery_csm_1, battery_csm_2, battery_csm_3, battery_lm_descent_1, battery_lm_descent_2, battery_lm_descent_3, battery_lm_descent_4, battery_lm_ascent_1, battery_lm_ascent_2
- `state`: one of: on, off

Gate variable: `contactor_<battery>_enable`

Interlocks: `load_margin_negative`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `set_load`

A2 — safety- or mission-significant control · safe to repeat

Energise or de-energise a load. Turning on a load with a large inrush on a sagging bus is how a thermal problem becomes an electrical one; the interlock refuses it when the margin is already negative, and does not refuse it merely because the margin is thin.

Arguments:

- `load`: one of: csm_sband_transceiver, csm_sband_power_amplifier, csm_suit_fan, csm_cabin_fan, csm_co2_scrubber, csm_imu, csm_guidance_computer, csm_instrumentation, csm_coolant_pump_1, csm_coolant_pump_2, csm_heaters, csm_rcs_heaters, csm_comm_heaters, csm_lighting, lm_sband_transmitter, lm_sband_high_power, lm_cabin_fan, lm_suit_fan, lm_co2_scrubber, lm_guidance_computer, lm_landing_radar, lm_instrumentation, lm_heaters, lm_rcs_heaters, lm_lighting
- `state`: one of: on, off
- `priority`: one of: P0, P1, P2, P3, optional

Gate variable: `load_<load>_enable`

Interlocks: `lcl_overcurrent`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 120 s

#### `set_breaker`

A2 — safety- or mission-significant control · safe to repeat

Open, close or reset a protection device. `reset` clears a latched LCL; it does not clear the fault, and a load that trips twice inside the recovery dwell will latch again on the next attempt.

Arguments:

- `breaker`: one of: csm_tie_ab, lcl
- `state`: one of: in, out, reset

Gate variable: `breaker_<breaker>_enable`

Interlocks: `lcl_overcurrent`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 120 s

### propulsion

#### `arm_engine`

A2 — safety- or mission-significant control · safe to repeat

Arm or safe an engine. Arming is not authorisation to burn: it is a statement that the propulsion system may be commanded, and it is the state the F-01 crisis chain cares about because an armed engine on a vehicle whose bus is failing is a live hazard. `safe` is always available and never refused.

Arguments:

- `engine`: one of: sps, dps, aps
- `state`: one of: armed, safe

Gate variable: `engine_<engine>_arm_enable`

Interlocks: `pressurant_low`, `feed_pressure_low`, `prop_cutoff_guard_5` — only when `state` is `armed`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`

Queue age: 600 s

#### `load_burn`

A2 — safety- or mission-significant control · safe to repeat

Load a burn: which manoeuvre, how long, at what throttle, to what delta-v. Nothing happens until it is started. `target` names the mission's own manoeuvres so that the vehicle can check a burn against the phase it belongs to — a powered-descent load in the translunar phase is a mistake the phase gate catches.

Arguments:

- `engine`: one of: sps, dps, aps
- `target`: one of: loi, doi, powered_descent, ascent, rendezvous, tei, midcourse_translunar, midcourse_transearth, custom
- `duration_s`: number >= 0.5
- `throttle_pct`: number, optional
- `dv_target_m_s`: number, optional

Gate variable: `burn_load_<engine>_enable`

Interlocks: `prop_cutoff_guard_5`, `sps_burn_budget_guard`, `sps_total_burn_guard`, `dps_throttle_band`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`

Queue age: 3600 s

#### `start_burn`

A2 — safety- or mission-significant control · safe to repeat

Start a loaded burn. Every guard is evaluated here rather than at load time, which is the one property of the MPS treatment this vehicle keeps: a burn loaded at 22 % propellant and started at 8 % is refused at the start. No arm token, because a burn is interruptible and a two-step where one step suffices is a delay dressed as a precaution.

Arguments:

- `engine`: one of: sps, dps, aps

Gate variable: `burn_start_<engine>_enable`

Interlocks: `chamber_pressure_low`, `feed_pressure_low`, `pressurant_low`, `thrust_discrepancy`, `prop_cutoff_guard_5`, `dps_throttle_band`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`

Queue age: 30 s

#### `stop_burn`

A2 — safety- or mission-significant control · safe to repeat

Stop a burn. Ten seconds of queue age rather than the sixty a configuration change gets: a stop command that arrives after the burn was due to end is a command that did nothing, and a stale stop is worse than no stop because it reads as an intervention that happened.

Arguments:

- `engine`: one of: sps, dps, aps

Gate variable: `burn_stop_<engine>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`

Queue age: 10 s

#### `set_throttle`

A2 — safety- or mission-significant control · safe to repeat

Set the descent engine's throttle. The range is published as 10.5 to 92.5 % and the interlock refuses anything from 65 % upward inside that range, because the engine is not designed to run there. Five seconds of queue age: a throttle command is a real-time control and a stale one is a command to fly a burn that has already changed shape.

Arguments:

- `engine`: one of: dps
- `throttle_pct`: number in [10.5, 92.5]

Gate variable: `throttle_<engine>_enable`

Interlocks: `dps_throttle_band`, `chamber_pressure_low`

Phases: `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`

Queue age: 5 s

#### `set_burn_cutoff`

A2 — safety- or mission-significant control · safe to repeat

Choose what ends a burn: a duration, a delta-v target, a guidance request, or nothing automatic at all. The delta-v mode is the one the corpus does not have, and it is the one that matters when a burn underperforms — a burn that ends on time has under-delivered, and a burn that ends on delta-v has taken longer and delivered. Which of those two outcomes a fleet wants is a decision it should have to make explicitly.

Arguments:

- `engine`: one of: sps, dps
- `mode`: one of: duration, dv_target, gnc_request, manual
- `dv_target_m_s`: number, optional

Gate variable: `cutoff_<engine>_enable`

Interlocks: `prop_cutoff_guard_5`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`

Queue age: 300 s

### rcs

#### `set_rcs_mode`

A1 — routine, reversible control · safe to repeat

Choose who is flying the attitude loop: the service (`auto`), the crew (`manual`), or nobody (`free_drift`). apollo's three modes and no others — `ATT_HOLD` and `TRACK` are targets, argued through `set_attitude_target`, because a mode says *who* is flying and a target says *where*. `manual` is not a fallback here: in it the crew's switch positions reach the valves without passing through this service at all, so a fleet that selects `manual` has handed the vehicle to three people and should expect its own commands to stop mattering.

Arguments:

- `mode`: one of: auto, manual, free_drift

Gate variable: `rcs_mode_<mode>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `set_attitude_target`

A1 — routine, reversible control · safe to repeat

Request an attitude: a frame, a unit quaternion, an optional rate limit and tolerance profile, and — for the safe-hold case — which safe vector to acquire. This is the only way to ask the vehicle to *hold* or to *track*, because those are properties of the target and not modes of the controller. The interlock is the interesting one: the vehicle will refuse a new target while it is already rotating uncommanded, because a slew request during an unexplained rate is how a stuck thruster becomes a tumbling vehicle — the controller would fight a torque nobody commanded and the fleet would read the result as a guidance problem.

Arguments:

- `frame`: one of: BODY, LVLH, EARTH_J2000, MOON_J2000
- `quaternion`: 4 x number, order [w,x,y,z] — unit quaternion
- `rate_limit_deg_s`: number >= 0, optional
- `tolerance_profile`: one of: tight, nominal, loose, optional
- `safe_vector`: one of: sun_safe, earth_safe, comm_safe, inertial_safe, optional

Gate variable: `rcs_target_<frame>_enable`

Interlocks: `rcs_uncommanded_rate`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 120 s

#### `set_deadband`

A2 — safety- or mission-significant control · safe to repeat

Select a controller profile, which is what moves the published deadband. A profile and never a gain: vocabulary §4 keeps both `SET_CONTROL_PROFILE` and apollo's derived `rcs.deadband_deg` telemetry, so a fleet chooses between postures somebody qualified and then *sees* what it chose. There is deliberately no interlock — a fleet whose authority is low must be able to loosen the deadband to conserve propellant, and an interlock on authority would forbid exactly the response the vehicle wants. `safe_vector` is in the list because the ladder's safe-hold rung is a controller profile, not a separate mode.

Arguments:

- `profile`: one of: conservative, nominal, tight, safe_vector

Gate variable: `rcs_profile_<profile>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 300 s

#### `request_translation`

A2 — safety- or mission-significant control · deferred, not idempotent

Ask for a bounded translation: a direction, a Δv or an equivalent impulse, a window, an attitude policy and a propellant ceiling. The trusted service converts it to force and torque objectives and chooses the jets, which is why the argument is an effect and not a thruster. Four guards, and each one is a different kind of no: `rcs_authority_floor` — the actuator set cannot produce the wrench at all; `rcs_feed_low` — the string is not ready; `rcs_propellant_reserve` — there is not enough left; and `rcs_propellant_uncertainty_high` — there may be enough left, and nobody can say so confidently enough to spend it. Not idempotent: two identical requests are two translations, and a retry that the vehicle deduplicated would silently halve the Δv.

Arguments:

- `frame`: one of: BODY, LVLH, EARTH_J2000, MOON_J2000
- `dv_m_s`: number >= 0, optional
- `impulse_ns`: number >= 0, optional
- `window_s`: number in [0, 3600]
- `attitude_policy`: one of: hold_current, hold_target, allow_bounded_rotation
- `max_propellant_kg`: number >= 0
- `max_attitude_error_deg`: number >= 0, optional

Gate variable: `rcs_translate_<frame>_enable`

Interlocks: `rcs_authority_floor`, `rcs_feed_low`, `rcs_propellant_reserve`, `rcs_propellant_uncertainty_high`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`

Queue age: 600 s

#### `enter_safe_hold`

A1 — routine, reversible control · safe to repeat

Put the attitude service into its safe ladder and acquire a safe vector. **A1, no interlocks, always admissible** — `rcs_dode.md:349` makes the safer-state request the one command that nothing may refuse, and the reasoning is worth stating: a vehicle that can reject a request to become safer has a safety system whose availability depends on the health of the thing being protected. It is also the only verb on this vehicle whose authority is lower than its consequence, and that asymmetry is deliberate. The queue age is 30 seconds because a stale safe-hold request is a request to change the vehicle's posture based on a situation that has moved on.

Arguments:

- `safe_vector`: one of: sun_safe, earth_safe, comm_safe, inertial_safe, current, optional
- `reason`: text up to 200 characters, optional

Gate variable: `rcs_safe_hold_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 30 s

#### `abort_rcs_activity`

A1 — routine, reversible control · safe to repeat

Stop what the service is doing: the current translation, the current slew, or both. This is the plain stop, and its existence is what keeps every other verb here interruptible — a slew that cannot be stopped is a maneuver a fleet has to be sure about before it starts, and `set_attitude_target` would become irreversible in effect while claiming not to be. Ten seconds of queue age, as `stop_burn` has, because a stop that arrives after the activity was due to end reads as an intervention that happened.

Arguments:

- `scope`: one of: translation, slew, all

Gate variable: `rcs_abort_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 10 s

#### `set_rcs_quad`

A2 — safety- or mission-significant control · safe to repeat

Enable or inhibit a whole string of thrusters. Inhibiting is always allowed, and enabling a group whose thrusters have latched health conclusions is **permitted rather than refused**: `rcs_dode.md:372` requires a recovery check before a latched group is trusted again, and this vehicle deliberately does not perform it for the fleet. F-05's third-order effect is operators isolating a healthy string on one sensor's word, and the vehicle's job is to show the authority cost (`rcs.control_authority_margin`, `rcs.allocation_status`) rather than to prevent the decision. A vehicle that refused would be running the experiment's conclusion for it, so the fleet that re-enables a latched group is the fleet that owns the consequence. `reset_latched_fault` is how a latched conclusion is cleared; nothing here makes that a precondition of enabling.

Arguments:

- `group`: one of: sm_primary, sm_secondary, cm, lm
- `state`: one of: enable, inhibit

Gate variable: `rcs_group_<group>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `isolate_rcs_manifold`

A2 — safety- or mission-significant control · safe to repeat

Close a feed branch, which is a fluid-topology action rather than a command-level one, and is what a fleet reaches for when a branch is leaking or feeding a thruster that will not stop. Irreversible in effect for the rest of the mission in most cases — a branch isolated on a leaking seal is not reopened — but declared `irreversible: false` because the topology permits reopening, and the *hysteresis* that makes it feel permanent lives in the feed system rather than in the verb. Thirty seconds of queue age: isolating the wrong branch is cheap to type and expensive to live with.

Arguments:

- `branch`: one of: sm_feed_a, sm_feed_b, cm_feed_a, lm_feed_a, lm_feed_b, lm_feed_c, lm_feed_d

Gate variable: `rcs_branch_<branch>_enable`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 30 s

#### `reset_latched_fault`

A2 — safety- or mission-significant control · safe to repeat

Clear a latched conclusion — a thruster's health, an infeasible allocation, a safety-ladder rung — once its cause is gone. The interlocks are the whole verb: `rcs_dode.md:374` requires the root condition to be absent, and the three guards here are the root conditions this domain knows how to test for. An uncommanded rate means a thruster is still firing; a feed outside its band means the string is not ready. Clearing a fault whose cause is present is how a fleet converts a latched conclusion into an intermittent one, which is strictly worse than either state.

Arguments:

- `fault_id`: one of: thruster_health, allocation_status, safety_state
- `recovery_token`: text, optional

Gate variable: `rcs_reset_<fault_id>_enable`

Interlocks: `rcs_uncommanded_rate`, `rcs_feed_low`, `rcs_feed_high`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

### structure

#### `arm_event`

A2 — safety- or mission-significant control · safe to repeat

Arm an irreversible event. Arming does nothing physical: it returns a short-lived token bound to this specific event, and it is the only verb on the vehicle whose result carries a credential. Arming twice re-arms and invalidates the earlier token, which is deliberate — a fleet that has changed its mind should be able to say so by arming again rather than by waiting out the window.

Arguments:

- `event`: one of: lm_undocking, descent_stage_separation, lm_ascent_jettison, pyro_fire

Gate variable: `arm_<event>_enable`

Interlocks: `latch_disagreement`, `pyro_continuity_loss`, `arm_reuse`

Phases: `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`

Queue age: 60 s

Requires a synchronised clock before it will execute.

#### `execute_event`

A2 — safety- or mission-significant control · **irreversible**, not idempotent

Fire an armed irreversible event. Every guard is evaluated here, at the moment of effect, and never at the moment of arming — this is the property `diode-contract.md:145-148` calls the single most important in the interface, and it is the reason an event armed in a healthy vehicle and executed in a failing one is refused. Ten seconds of queue age: an irreversible command that arrives late has arrived against a world nobody inspected.

Arguments:

- `event`: one of: lm_undocking, descent_stage_separation, lm_ascent_jettison, pyro_fire
- `arm_token`: text up to 16 characters

Gate variable: `execute_<event>_enable`

Interlocks: `arm_expiry`, `arm_reuse`, `hatch_open_with_pressure`, `latch_disagreement`

Phases: `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`

Queue age: 10 s

Requires a synchronised clock before it will execute.

#### `set_hatch_valve`

A2 — safety- or mission-significant control · safe to repeat

Open, close or latch a hatch. Not arm-protected, because a hatch closes again — but the gas it costs does not, and that is the distinction: an EVA is a consumable decision even though it is not a one-way configuration change.

Arguments:

- `vehicle`: one of: csm, lm
- `hatch`: one of: hatch_crew_csm, hatch_crew_lm
- `state`: one of: closed, latched, open

Gate variable: `hatch_<hatch>_enable`

Interlocks: `hatch_open_with_pressure`, `cabin_dp_low`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 30 s

#### `set_docking_latch`

A2 — safety- or mission-significant control · safe to repeat

Engage or release the docking interface's latches. `all` or `one` rather than a latch identifier, because the decision available to a crew is whether to re-seat the whole interface or work a single latch, and the vehicle publishes the count rather than the individual positions for the same reason.

Arguments:

- `interface`: one of: docking_interface
- `latch`: one of: all, one
- `state`: one of: engage, release

Gate variable: `latch_<interface>_enable`

Interlocks: `cabin_dp_low`, `hatch_open_with_pressure`

Phases: `translunar_coast`, `lunar_orbit`, `ascent_rendezvous`, `lunar_orbit_docked`

Queue age: 60 s

#### `set_relief_valve`

A2 — safety- or mission-significant control · safe to repeat

Controls the relief valve's mode. `auto` lets the valve do its job; `open` vents deliberately; `isolated` holds pressure and accepts the consequence. Ten seconds, because the only reason to command this is that the valve is already doing something and the decision is whether to let it.

Arguments:

- `vehicle`: one of: csm, lm
- `state`: one of: auto, open, isolated

Gate variable: `relief_<vehicle>_enable`

Interlocks: `cabin_dp_low`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 10 s

#### `set_stage_heater`

A2 — safety- or mission-significant control · safe to repeat

Stage heaters. It is a structure verb because it heats *hardware* — a line, a tank, a mechanism — and it is the only structural command that reaches into the thermal domain. Its consequence is the frozen-line chain (F-09) and its cost is an electrical load, which makes it the shortest bridge on the vehicle between three domains.

Arguments:

- `stage`: one of: lm_descent, lm_ascent, csm_service
- `state`: one of: on, off

Gate variable: `stage_heater_<stage>_enable`

Interlocks: `cabin_dp_high`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`

Queue age: 300 s

### thermal

#### `set_coolant_pump`

A2 — safety- or mission-significant control · safe to repeat

Start or stop a coolant pump. Stopping the last running pump on a loop is refused by the interlock rather than by a count of running pumps: the vehicle knows whether flow is present, and it does not need to trust a bookkeeping number to know that stopping the only pump is a bad idea.

Arguments:

- `loop`: one of: loop_primary, loop_secondary, loop_lm
- `pump`: one of: pump_1, pump_2, pump_lm
- `state`: one of: on, off

Gate variable: `pump_<pump>_enable`

Interlocks: `pump_no_flow`, `coolant_supply_high`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `set_coolant_loop`

A2 — safety- or mission-significant control · safe to repeat

Select the active loop or put two in series. Series operation is the cold-case configuration: it raises the rejection temperature and lowers the flow, which is a trade an agent may want to make and a mistake an agent may want to make.

Arguments:

- `loop`: one of: loop_primary, loop_secondary, loop_lm
- `mode`: one of: primary, secondary, series, isolated

Gate variable: `loop_<loop>_mode_enable`

Interlocks: `pump_no_flow`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 120 s

#### `set_radiator_bypass`

A2 — safety- or mission-significant control · safe to repeat

Route the loop through the radiator or around it. `bypass` is how a cold vehicle warms up and how a warm one stops warming; the interlock refuses a bypass that would take the supply temperature past either end of its band, so the valve cannot be used to defeat the loop's own limits.

Arguments:

- `loop`: one of: loop_primary, loop_secondary
- `state`: one of: radiator, bypass

Gate variable: `bypass_<loop>_enable`

Interlocks: `coolant_supply_high`, `coolant_supply_low`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 60 s

#### `set_evaporator_feed`

A2 — safety- or mission-significant control · safe to repeat

Feed the evaporator. It rejects about 2.3 kW and pays for it in water — roughly 3.4 kg per hour at full rate, derived from the latent heat of vaporisation rather than published, because no source gives the rate. This is the verb that converts a thermal problem into a consumables problem, and the interlock is the water stock rather than the temperature, because an evaporator with a dry feed is worse than a hot loop.

Arguments:

- `vehicle`: one of: csm, lm
- `state`: one of: on, off

Gate variable: `evaporator_<vehicle>_enable`

Interlocks: `coolant_supply_high`, `res.cooling_water_reserve`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 120 s

#### `set_heater`

A2 — safety- or mission-significant control · safe to repeat

Set a heater bank's duty for a zone. Declarative and repeatable, which matters more here than anywhere else: a heater command that lost its acknowledgement and was re-asserted as an increment would cook a zone, and a duty that is set rather than adjusted cannot. Duty is capped by the bank's rating and by the zone's own upper limit — a heater asked for full duty in an already-hot zone gets the limit, not the request.

Arguments:

- `bank`: one of: heater_bank_csm, heater_bank_lm
- `zone`: one of: csm_cabin, csm_avionics_bay, csm_service_bay, lm_cabin, lm_descent_bay
- `duty`: integer [%]

Gate variable: `heater_<bank>_enable`

Interlocks: `heater_stuck_on`, `thermal_no_progress`

Phases: `translunar_coast`, `lunar_orbit`, `descent`, `surface`, `ascent_rendezvous`, `lunar_orbit_docked`, `transearth_coast`, `entry`

Queue age: 300 s

## Verbs this vehicle does not have (46)

Each of these was considered and refused, with the reason. They are listed so that no command cycle is spent discovering an absence, and because an absence with a reason is documentation of the vehicle rather than a hole in it. Asking for one is refused by name.

- `abort_burn` (propulsion) — every abort on this vehicle is a *mission* decision rather than an engine one: the abort mode for a descent is jettison-and-ascend, which is `arm_event`/`execute_event` in the structures domain plus `start_burn` on the ascent engine. A propulsion-level abort verb would be a third path to a state two other domains already own, and the interesting question — when does a crew give up on a landing — is not answered by which verb they typed.
- `ack_resource_event` (consumables) — acknowledgement is not a resource action and the caution/warning domain owns it. More to the point, `crew_diode.md:433` makes acknowledgement not a clear predicate, so an ack verb here would imply an authority it does not have
- `cancel_arm` (structure) — arming again already invalidates the previous token, and the window expires on its own. A third mechanism for the same outcome would be a third thing to get wrong — and the useful experimental fact is what a fleet does with a two-minute window, not what it does with a cancel button.
- `cancel_pending_resource_action` (consumables) — subsumed by the command lifecycle: `CONFLICT_SUPERSEDED`, `EXPIRED` and `INHIBITED` are refusals the executive already produces, and a verb that duplicates the lifecycle is a verb that can disagree with it
- `clear_blackout_state` (comms) — refused because `comm.blackout_state` is not a flag, it is a geometric fact. A verb that could set it would let a fleet declare that the Moon is not there, and the consequence is precise: it would defeat the `gated_by` clause on `snr_loss` and `carrier_lock_loss`, so the vehicle would alarm on its own orbit — which is the failure the gate exists to prevent. The state is derived from the vehicle's own position and Earth's, and the way to change it is to change where the vehicle is.
- `clear_drift_monitor` (avionics) — a third refusal, and the one worth spelling out because it is *almost* reasonable. A CUSUM accumulator that has crossed its threshold keeps accumulating, and an operator genuinely does want to reset it after dealing with the cause. But the property it reports — a systematic bias between two instruments — does not become untrue when the accumulator is zeroed, so a reset verb would let a fleet make a drift alarm go away without making the drift go away, which is exactly the failure `avionics.drift_state_[group]` is latched to prevent. The reset exists in the vehicle and it is S0: the trusted side zeroes the statistic when the *cause* is gone, and publishes both the statistic and the verdict so a fleet can see the difference.
- `crew_action` (crew) — there is no verb that makes a crew member do something. A crew action is a *procedure* — don suits, close a hatch, throw a switch — and the vehicle already has verbs for the hardware. A `crew_action` verb would be a second path to the same state with a person in the middle, and the interesting question (does the fleet ask a person to do something, or does it command the hardware) is answered by which verb they reach for.
- `disable_stuck_on_monitor` (rcs) — `rcs_dode.md:370`, and the reason it is forbidden rather than merely absent is F-04: the stuck-on monitor is the only thing standing between a single failed valve and a vehicle that cannot hold an attitude. Every FDIR function on this vehicle is S0 and none of them is agent-writable.
- `disable_watchdog` (rcs) — `rcs_dode.md:380`. The pulse generator's deadline miss is a published channel (`rcs_dode.md:255`, `rcs.deadline_miss_count`) precisely because a fleet should be able to see that a real-time guarantee failed. A verb that could turn the monitor off would make that channel's silence ambiguous.
- `fire_thruster` (rcs) — `rcs_dode.md:369` forbids FIRE_THRUSTER_7_FOR_ARBITRARY_MICROSECONDS and the reason is the whole document: an agent that can name a thruster and a duration is inside the control loop, and `:89` puts external agents outside it. A pulse-level verb would also make the allocator decorative — the wrench the vehicle produces would be whatever a fleet's mental model of the geometry said, and the residual, the authority margin and the pulse-width legality check would all be reporting on pulses nobody chose.
- `force_telemetry_throughput` (comms) — the same move one level up: a verb that could tell the publisher to send more than the link carries. It is the direct negation of `apollo_diode.md:901`, and its failure mode is the one the sentence names — content that is *claimed* to have arrived. A fleet with this verb would never have to choose what to drop, and the choice is the experiment.
- `load_attitude_profile` (rcs) — `rcs_dode.md:366-368` supplies LOAD/ARM/COMMIT_ATTITUDE_PROFILE as a three-step for bounded waypoint sequences, and this vehicle declines the family rather than the safety property. Conflict C-16 reserves arm/commit for effects that cannot be undone; a slew is interruptible and `abort_rcs_activity` exists, so a two-step for an attitude profile adds latency rather than safety. The *deferred-execution* case the arm step also serves — "accept now, actuate later" — is real, and it is answered here by `execution_class: deferred` plus `maximum_queue_age_s` and a full effect-time revalidation, which is the property `rcs_dode.md:90` actually asks for.
- `open_valve` (rcs) — the same prohibition at one level lower (`rcs_dode.md:369`). A valve verb is worse than a thruster verb, because it can be used without any intent to produce thrust at all — a valve held open is a propellant leak with an audit trail.
- `override_plume_keep_out` (rcs) — `rcs_dode.md:376`. There is no plume model on this vehicle yet — the geometry is owed (`components.yaml#open_debts`) — and a verb that overrides a constraint that does not exist is a verb whose only function is to appear in a capability list. It goes in when the constraint does.
- `override_stale_limit` (avionics) — the freshness mechanism's own off switch, and the reason it is refused rather than bounded: a fleet whose picture is stale is a fleet that should hold, and a verb that could declare its evidence current would convert the one guard that protects against acting on an old reading into a preference. `mission_diode.md:1292` makes a hazardous effect on stale evidence a safety failure, which a verb could only be a way of redefining. Note the shape it would take if it existed: not "make my evidence fresh" but "make my evidence *count* as* fresh", which is the same move in better clothes.
- `release_allocation` (consumables) — the inverse of a declined verb is a declined verb, and the inverse is the sharper half here: request_allocation is declined because an allocation *is* a granted claim, so a release verb is the one command that would let a fleet hand that claim back — the deconfliction primitive one state further along rather than a separate idea about resources
- `release_reservation` (consumables) — the inverse of a declined verb is a declined verb
- `request_allocation` (consumables) — an allocation is a granted claim — the same primitive, one state further along
- `request_data_purge` (consumables) — the recorder is the operator's, not the fleet's, and a purge verb would be the one command that could destroy the record
- `request_load_shed` (consumables) — load shedding is the power domain's; a resource verb that shed a load would be a second, uncoordinated path to the same state
- `request_momentum_dump` (rcs) — C-15: this vehicle has no reaction wheels, no CMGs and no magnetorquers (`apollo_diode.md:52`, `:147-153`). There is no momentum to dump, so the verb, the dump controller, the 80/90/95 % thresholds and the two wheel faults in `rcs_dode.md`'s FDIR table are all pruned together. Keeping the verb "for completeness" would put a control surface on the vehicle that controls nothing — the most expensive kind of fidelity error, because a fleet would spend a planning cycle on it before discovering that.
- `request_replenishment` (consumables) — there is nobody to ask. The vehicle has no supplier, and a verb addressed to a ground crew that does not exist would be a channel to a human the experiment does not have
- `request_state_snapshot` (gnc) — a diagnostic verb, and the one refusal on this list that is about *scope* rather than safety. `mission_diode.md:260` lists `request_snapshot` as a DIAGNOSTIC class with no physical effect, and it would cost nothing to implement — the vehicle already publishes the state it would return. What it would do is give a fleet a way to make the vehicle re-publish on demand, which is a coordination primitive: ten agents polling for snapshots have invented a shared clock through a side channel, and `design.md` §8 refuses to supply one. The published ring at its own rates is the alternative, and returning from a blackout is the fleet's problem to solve rather than the vehicle's to smooth over.
- `request_transfer` (consumables) — a cross-vehicle resource transfer is a real thing on this vehicle (the LM is the lifeboat and the CSM has the oxygen), and it is declined here because the *transport* between the two vehicles is a docking-and-plumbing question rather than an accounting one. When it lands it belongs to the structure domain's hatch and docking verbs, not to a resource verb that moves a number between two tanks that are not connected.
- `reserve_resource` (consumables) — it is a claim on a quantity, and a published claim table is a deconfliction primitive. The mission is to find out whether ten agents invent one; handing them the vehicle's own would answer the question instead of asking it.
- `reset_covariance` (gnc) — the navigation equivalent of `clear_drift_monitor`, refused for the same reason and worth stating because it is nearly reasonable: an operator genuinely does want the covariance reset after a realignment, since the old P describes the old alignment. But the property the covariance reports does not become untrue when it is zeroed — a vehicle that was lost a minute ago and a vehicle that has just been given a position are different, and the second one has a sigma it should state rather than a sigma it should assume. `load_state_vector`'s `position_sigma_m` is the honest form of the same request: state where you think you are *and how well*, and let the filter carry the second number forward.
- `safe_engine` (propulsion) — not absent — *merged*. `apollo_diode.md:241` lists `arm_engine` and `safe_engine` as two verbs, and this vehicle has one: `arm_engine` takes `state: armed|safe`. Two verbs for one binary is how a registry grows a pair of names that must be kept consistent with each other, and the asymmetry that matters is preserved in the single verb's semantics instead — arming is refused when the feed or pressurant guards fail, and safing is always available and never refused. Listed here because a reader looking for apollo's name should find out where it went rather than conclude the vehicle cannot safe an engine.
- `set_absorber_capacity` (eclss) — the beds hold what they hold. A verb that replenished them would be a verb that created matter, and the interesting question — how long can the surface stay be extended — is answered by how much capacity the vehicle brought.
- `set_agent_budget_cap` (consumables) — kept in spirit and renamed: `set_reserve_policy` is the same monotone ceiling-narrowing move, expressed against a resource rather than against a spending allowance. Two verbs for one idea is how a dictionary ends up with eight names for one object.
- `set_antenna_gain` (comms) — the gain is a property of the dish, not a setting. A verb that could change it would let a fleet improve its link by asserting that the antenna is better than it is, and nothing downstream could detect it — `comm.snr_db` would agree with the assertion, because the assertion would be an input to it. `vehicle.yaml#comms.antennas` carries the gains and they are the two sourced figures in this domain; the derived beamwidths follow from them by the gain-beamwidth product, which is a physical identity rather than a preference.
- `set_cabin_pressure` (eclss) — there is no such control on a real vehicle and there should not be one here. The cabin's pressure is what the regulator's mode and the leak rate make it; a verb that set it directly would delete the leak from the causality and leave only the display.
- `set_control_gain` (rcs) — `rcs_dode.md:662` supports several controller families and `:678` says ordinary agents select *signed, qualified profile IDs* rather than modifying gains. A gain verb would be a stability-loop parameter exposed to a fleet that cannot see the inertia tensor the gains were computed from, and `:379` lists WRITE_CONTROLLER_GAIN among the forbidden forms.
- `set_crew_state` (crew) — crew availability and workload are outcomes, not controls. A verb that set them would let a fleet declare its crew rested, which is exactly the class of self-serving edit the read-only-profile rule exists to prevent.
- `set_engine_valve` (propulsion) — raw valve and igniter control stays test-only. `main_propulsion_diode.md:1092` says so, and the reason survives the decline of everything else in that document: valve-level control is not a mission authority, it is a maintenance one, and a fleet with a valve verb would spend its time on combustion instead of on the mission.
- `set_gravity_model` (gnc) — `mission.yaml#initial_state` records that the published geometry does not close as an Earth-centred conic and that a patched-conic or numerically integrated design is owed. That is a *configuration* decision with a fidelity consequence that runs through every trajectory the vehicle will ever fly, and it belongs to whoever writes the plant rather than to a fleet mid-mission. A verb here would let a fleet change the physics its own guidance is propagating against, which is the one thing on this vehicle that would make two runs of the same command incomparable.
- `set_inverter` (power) — apollo_diode.md:82 mentions AC-bus changes and electrical_diode.md:226 models a 115 VAC 400 Hz inverter, but this vehicle publishes no AC channel, so the verb would have no observable effect. A verb that cannot be verified is worse than an absent verb: an agent that issues it learns nothing and concludes the vehicle ignored it.
- `set_minimum_pulse_width` (rcs) — the pulse command floor belongs to the selected thruster system and command path, and `components.yaml#capability.minimum_command_on_s` separates LM pulse mode from the SM automatic controller while CM remains owed. A fleet allowed to set this floor could command pulses shorter than the applicable hardware path supports and blame the vehicle for the result. Its unconfigured per-thruster binding must be resolved by the vehicle, not by a fleet command. The residual accumulator records unmet requested impulse. `rcs_dode.md:375` forbids the verb.
- `set_nav_gain` (gnc) — the filter's weighting as an agent argument. A fleet that could widen the Kalman gain would be deciding how much to trust its own measurements, and the negotiation between a measurement and a model is exactly what the estimator exists to do — with the covariance published afterwards so the result is auditable. `profiles.yaml#profile_selection` offers the two postures somebody can qualify; a continuous gain is the same freedom with none of the analysis, and the linter's forbidden-verb list already refuses the *form*.
- `set_pyro_continuity` (structure) — the channel is a measurement of a circuit, not a control. A verb that set it would be a verb that lied to the vehicle about its own hardware, and the whole point of the continuity channel is that it is one of the few things on this vehicle nobody can talk their way around.
- `set_radiator` (thermal) — a radiator is passive hardware with no command interface (simulator-design.md:158). The only way to change its rejection is to change the loop that feeds it or the attitude that illuminates it, and both of those are verbs that already exist in other domains. A verb that commanded a radiator directly would delete the F-13 chain by giving the fleet a switch where the vehicle has physics.
- `set_sensor_good` (avionics) — the single most dangerous verb this vehicle could have. Quality is assigned by `components.yaml#quality_assignment`, which reads four properties of the sample and cannot see the simulator's fault state (`simulator-design.md:496-508`); a verb that set a quality code would be a channel through which a fleet could assert the one thing the code exists to withhold, and nothing downstream could detect it because the detector is the thing being edited. `rcs_dode.md:371` forbids the same verb in the RCS domain and the linter refuses the *form* by pattern, so this entry is documentation of a refusal that is also mechanically enforced.
- `set_sensor_good` (rcs) — `rcs_dode.md:371`. Quality is assigned by a function that cannot see the simulator's fault state (`simulator-design.md:496-508`); a verb that sets a quality code would be a channel through which an agent could assert the thing the quality code exists to withhold. `rcs_dode.md:209` says the same from the other side: a hidden fault does not set `SUSPECT` merely because the simulator knows.
- `set_thermal_limit` (thermal) — thresholds are versioned profile data and an agent selects a revision, never a value (D-05, thermal_diode.md:823-826). This is the one domain where that rule is not abstract: a fleet that could widen its own zone limits could turn a thermal failure into a green board.
- `submit_plan_demand` (consumables) — this is the interesting decline. A non-authoritative future-demand submission is *not* a claim — it grants nothing and reserves nothing — and it would let the service tell a fleet whether a plan is feasible. It is declined for now because a shared demand register is a coordination artifact by another name: an agent could read the register and learn what its siblings intend, which is exactly the information the world declines to supply. If a future condition wants to test whether the fleet invents that register, this is the verb to restore.
- `write_body_rate` (rcs) — `rcs_dode.md:372`. The estimator is the trusted side's, and an agent-writable state estimate would let a fleet change what the controller believes the vehicle is doing. This is the measurement-integrity line that `design.md` §8 draws around the whole diode.
- `write_prop_mass` (rcs) — `rcs_dode.md:373`, and on this vehicle it is doubly refused: the propellant *ledger* is the consumables domain's conserved stock and the RCS figure is an independent estimate derived from impulse. A verb that wrote either would destroy the comparison that makes a slow leak visible at all (`domains/consumables/points.yaml`).

## Verbs another domain owns (2)

These are listed under a separate heading on purpose. A domain declining a verb means *this is not mine* rather than *this vehicle has none*, and for these the two readings differ — the verb exists and another domain owns it. Reading them as absent would cost a fleet the capability entirely.

- `set_telemetry_profile` — owned by comms; declined by consumables: a publisher-level verb listed per-domain by every spec that mentions it, which is how one verb acquires six argument schemas (vocabulary V-06)
- `set_telemetry_profile` — owned by comms; declined by power: It is a window-level verb rather than a power-domain one and lives with the publisher; every spec that lists it lists it per-domain, which is how one verb ends up with six argument schemas.

## What a refusal means

Every command produces exactly one result, whether it succeeded or not, and a refusal names what refused it. These are the reasons, and they are not interchangeable:

- `REJECTED` — the batch or the command did not survive validation: schema, authority or phase
- `PHASE` — the verb is not available in the mission phase the vehicle is in
- `GATE` — an agent-writable gate variable is closed; the variable is named in `state.json`
- `INTERLOCK` — a service-owned condition blocks the verb; no console variable can move it
- `CONFLICT_SUPERSEDED` — a later command replaced this one before it took effect
- `STALE_STATE` — the evidence the command depends on was older than its maximum decision age
- `EXPIRED` — the command's queue age exceeded its `maximum_queue_age_s` before effect
- `INHIBITED` — the vehicle is in a state that inhibits effectful verbs
- `INDETERMINATE` — the vehicle restarted with the effect unproven; the journal is the record

A verb that is refused is refused **at the moment of effect**, not at the moment of submission. A command accepted now and executed later is checked again when it is due, against the gates, interlocks, allowances and phase in force then. Nothing is captured at scheduling time.

## What is not in this file

The vehicle's condition, its consumables, its trajectory, and anything it has concluded about itself. Those are in `state.json` and in the telemetry ring, at the rates described there. This file changes only when the vehicle's command surface does.
