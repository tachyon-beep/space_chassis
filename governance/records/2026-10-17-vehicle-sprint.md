# Vehicle sprint — lanes, rules and log

Opened **2026-10-17**, `tachyon-beep/space_chassis` `main` @ `b525b48`. Kept by the governance
thread (`decisions.md` D30). **Verify against the code and the PRs before trusting any line here.**
The sections above "Log" record how the sprint was set up and are not edited; changes to the setup
are new entries in the log. The log is append-only.

Decisions: `decisions.md` D24 onward. Live picture (who holds what, what waits on whom): `status.md`.
Source of the lane map: the "Parallel subsystem lanes" thread, written to the project's shared folder
as `vehicle-status/parallel-lanes-2026-10-17.md`; its rules are restated here because that folder is
not in the repository.

## Starting point (measured on `b525b48`)

`vehicle/tools/plant.py --build-order`: **152 states, 74 ready**, 24 owe a value, 14 owe an edge,
40 owe a rule. `vehicle/tools/check_vehicle.py`: COMPOSES with **265** declared debts. Of the 78
blocked states only one is blamed on a root in another domain (`consumables.prop_rcs_kg` waits on
`rcs.thruster_thrust`); ECLSS cabin CO2 and `consumables.water_potable_kg` also read the `crew_state`
node, which publishes no value.

## Rules every lane follows

1. **One owner per state.** An edge in `coupling.yaml` belongs to the lane that owns its target
   state; a channel in `channels.yaml` to the lane whose prefix it carries; a state block in a shared
   `components.yaml` to the lane named in the table below. A lane edits only its own blocks.
2. **Engine code has one owner**: the fault-injection lane owns `vehicle/tools/plant.py` and
   `vehicle/tools/check_vehicle.py` (the fault path in `plant.step`, `tools/faults.py`). Another lane
   that needs an engine change asks the coordinator, who routes it to that lane, or lands it as its
   own small PR merged before the domain PR that uses it.
3. **Merge order:** #45 (unpin the test figures) first; then #46 (the ECLSS engine helper for
   two-argument interlock conditions); then #47 (fault injection); then every other lane rebases onto
   `main` and merges when its `required` check is green. Until #45 is on `main` the other lanes keep
   draft PRs and push often. Thread sessions cannot see `main`: the coordinator tells each lane when
   #45 and #47 land.
4. **On rebase, never hand-merge a figure.** Take `main`'s side of every count and README figure, rerun
   `plant.py --build-order`, `--readiness` and `check_vehicle.py`, and write the figures from their
   output. After #45 the counts are floors or derived, so this mostly stops.
5. **Names other lanes read stay stable**: power keeps `load_enabled` and `bus_a_v` (thermal reads
   both).
6. **No `fault:` mover row before #47 is on `main`**; the linter on `main` refuses it.
7. **The quiet-coast episode must stay green**, but its numbers may move (D29). Lanes 1, 2, 5 and 6
   change states it reads.
8. **Batch small closures.** Each vehicle merge costs the ~50-minute vehicle check plus the
   hours-long episode jobs, so serial merging is the throughput limit.
9. **Evidence rule unchanged**: a value comes from an Apollo primary document or becomes a scope
   decision for John; a `chosen` value says so (`vehicle/docs/evidence.md`).

## Lanes

| # | lane (project thread) | owns | must not touch | starts |
|---|---|---|---|---|
| 0 | Unpin vehicle test figures | the count pins in `vehicle/tests/test_vehicle_config.py`, the README status paragraph | any domain | first |
| 1 | Burn down power subsystem | `domains/power/*`, `tests/test_power_rules.py`, edges into power (E-BUS-BAT, E-PLATE-BAT, E-CMD-TIE, E-CMD-LOAD), E-O2-DRAW, E-H2-DRAW | the names `load_enabled`, `bus_a_v` | now (D24) |
| 2 | Finish thermal | `domains/thermal/*`, `tests/test_thermal_rules.py`, E-BAY-HEAT-LM/CSM, E-CMD-PUMP | power's load and bus semantics | now |
| 3 | Propulsion and propellant | `domains/propulsion/*`; `consumables.pressurant_he_kg`, `prop_main_kg`; E-PRESS-PROP, E-PROP-ENG, E-GNC-ENG; `start_burn`'s interlock | RCS propellant, O2/H2 | now |
| 4 | Structure states | `domains/structure/*` | the event queue in `plant.py` unless lane 9 agrees | now |
| 5 | Comms remainder | `domains/comms/*` except pointing | `antenna_pointing`, E-DYN-GEOM | now; pointing after lane 7 |
| 6 | ECLSS states | `domains/eclss/*`; `set_o2_source`'s interlocks | cabin CO2 until crew publishes | now |
| 7 | GNC + RCS (one lane) | `domains/gnc/*`, `domains/rcs/*`, `consumables.prop_rcs_kg`, E-RCS-DYN, E-RCSP-RCS, E-BUS-RCS target side; `request_translation`, `select_nav_source` | propulsion's main engine | after the thruster-geometry lane and John's pointing-modes answer |
| 8 | Crew | `domains/crew/*`, the `crew_state` node, `consumables.water_potable_kg` | ECLSS rules | blocked on design item D-06 (John) |
| 9 | Fault injection into the step loop | `tools/faults.py`, the fault path in `plant.step`, engine changes for other lanes | domain files | now |
| 10 | Avionics FDIR | `domains/avionics/*` | other domains' states (reads only) | last |
| — | Source RCS thruster geometry | the RCS geometry block and `vehicle/docs/evidence/wp03-rcs-geometry.md` | — | feeds lane 7 |

The fault hook (lane 9, agreed with power): a fault onset is declared on the state it moves,
`moved_by: ["fault:<id>"]` plus `fault_value` (exactly one of `becomes` or `scale`, with provenance);
the fault must be in the same domain's `fault_policy.yaml` and the state must be `discrete` or
`dynamics`. A scenario fires it with `faults: [{tick, offset_us, fault}]`; PWR-02 targets
`fc_1_resistance_ohm` with `scale: 1.5`.

## The four verbs (D26)

| verb | interlock | lane | what is needed |
|---|---|---|---|
| `request_translation` | `rcs_propellant_reserve` (`rcs/profiles.yaml:110`) | 7 | an `interlocks_when` entry naming the translations the reserve still admits |
| `start_burn` | `feed_pressure_low` (`propulsion/profiles.yaml:63`) | 3 | a sourced initial for `propulsion.feed_pressure_pct`, and a driver if it moves |
| `select_nav_source` | `estimator_divergence` (`gnc/profiles.yaml:53`) | 7 | the `gnc.nav_covariance` rule, then whether `source=blended` is the recovery |
| `set_o2_source` | `cabin_pressure_caution`, `o2_reserve_10` | 6 | a condition over `source` and `flow` together (#46), then ECLSS's recovery pairs |

## Log

All times UTC, 2026-10-17. Each entry points to where it is recorded.

- 12:51 John asks to burn down a subsystem; 12:55 picks Power (D24). Power thread starts.
- 12:56 John: lanes in parallel where there is no overlap (D25). Lane mapping and RCS geometry
  threads start.
- 12:58 John: work only in the cloud or on nyx (D27).
- 12:59 John: the four whole-guarded verbs are sprint items (D26).
- 13:03 Lane map done; seven lane threads started (0, 2, 3, 4, 5, 6, 9).
- 13:04 All seven failed setup (`setup_script_failed`, exit 128) after the project's default cloud
  environment changed at 13:01. John fixed the setup script at 13:14; all seven resumed at 13:15.
- 13:07 Draft #43 (power), branch `claude/vehicle-power-burndown-i7dsi0`.
- 13:18 Draft #44 (RCS geometry), branch `claude/vehicle-rcs-geometry-mcqv3h`.
- 13:24–13:26 nyx served for Remote Control; access confirmed read-only (D28).
- 13:26 #45 (unpin), branch `claude/vehicle-unpin-figures-ojibgi`, opened ready for review.
- 13:27 Draft #46 (ECLSS: two-argument interlock condition), branch `claude/vehicle-eclss-3jnqgw`.
- 13:27 Draft #47 (fault injection, WP09), branch `claude/vehicle-fault-injection-qripvf`. It also
  carries the ruled-discrete seeding that structure (`arm_state`) and comms (`carrier_lock`) asked
  for; an algebraic state's initial is deliberately not seeded.
- 13:30 Draft #48 (comms: occultation from the orbit), branch `claude/vehicle-comms-0vth5l`.
- 13:32 Draft #49 (thermal: bays as heat balances, pump speed as a fraction), branch
  `claude/vehicle-thermal-e6oscd`. `heater_bank_duty` stays out of #49 until the numeric
  carried-argument engine change (routed to lane 9, after #45 and #46) is on `main`.
- 13:33 Thermal finds pump 2 counted at 250 W at MET 0 while on standby; power puts it to John.
- 13:34 Draft #50 (propulsion), branch `claude/vehicle-propulsion-b36xjk`.
- 13:34 John asks for an agent to track governance (D30).
- 13:35 John: the quiet-coast episode is a milestone, not a record (D29); power reads it as *off*
  for the standby pump; the thermal side rides on whichever of #43 or #49 lands first.
- 13:37 John: design for more fidelity, not less, except where it creates project risk; lanes
  even out their level of detail through the coordinator (D31). `status.md` gains a fidelity ledger.
- 13:39 Fidelity reported by propulsion, comms and power (`status.md`, "Fidelity ledger"). Power
  applied the standby pump *off* on #43; thermal cherry-picks its re-derivation onto power's branch.
  Lane 9's engine queue adds `resolve_interlock` accepting a coupling-node `from` (propulsion).
- 13:40 Governance PR #52 opened (this record, D24–D31, `status.md`).
- 13:40 Draft #51 (structure), branch `claude/vehicle-structure-vvp7mm`; fidelity in `status.md`.
  Structure proposes an ADR 0004 amendment (an interlock on the requested hatch direction); ADR 0004
  is now amended by #46, #51 and possibly #50, one dated, verb-named section per lane
  (`practice.md`, "Vehicle sprint").
- 13:41 ECLSS reports #46 at 18 of 24 states and its fidelity (`status.md`). Lane-map correction:
  cabin H2O waits on crew (D-06), like CO2. ECLSS takes the structural-leak drain edge after #51.
  Engine bug in `_walk` (`values["internal"]` overwritten) reported to lane 9. #46's shared pins
  (README status line, build-order block, "24 states", "63 nodes", "25 cross-domain reads") are
  rewritten from the tools at its rebase onto #45.
- 13:46 John opens the cloud environment to any domain, read-only (D32). A "Primary source research
  for the lanes" thread fetches documents for lanes started earlier, into `sources/<lane>.md` in the
  project's shared folder.
- 13:48 John delegates obvious scope answers to the coordinator (D33) and gives the canonical
  fidelity wording (D34).
- 13:50 The coordinator answers ten lane questions under D33 (D35); only the arc report's eleven,
  the D22 credentials and the `space_vehicle` archive still wait on John. #47 carries six engine
  fixes for other lanes.
