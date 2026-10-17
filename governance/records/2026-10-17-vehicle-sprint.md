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
- 13:49 John: borderline scope questions get an independent Fable evaluation (D36). The
  "Independent review of the arc report decisions" thread starts on the eleven, pointing modes and
  D-06 first.
- 13:50–13:51 John: fidelity has to add an interesting option, not a forced move (D37). The
  fidelity ledger gains a "what option it adds" column, filled as lanes report.
- 13:47–13:48 #47 triaged: it carries all engine work for other lanes (`status.md`); `gated_by`
  held; truth bytes change, so per-tick hashes differ from `main`. Merge order unchanged. Comms
  raises the high-gain antenna to TN D-6723 Table I (pointing becomes a crew trade); a `measured`
  pattern linter change goes to lane 9. Thermal's bays and pump speed stay below sourced fidelity
  until the research thread reads its documents. The research thread drops ECLSS and SPS (those
  lanes fetch their own); RCS pages first.
- 13:58–14:00 The independent review of the arc report's eleven lands; the coordinator answers all
  eleven on it (D38). D-07 (crew dialogue per console or shared) stays John's, *per-console* by
  default. Lanes 7 (GNC and RCS) and 8 (Crew) start at 13:59. The instrument layer has no owner yet.
- 13:59–14:00 John: what fidelity is worth (D40); the ledger classes each option as signal,
  confounder, event/noise or none. 14:00 John picks *per console* for D-07 (D39).
- 14:04 The instrument layer goes to the fault-injection lane after #47 (it owns `plant.py` and
  `console.py`); then the delay at the window, the fair-chance stamps, and the `fleet_class` and
  `acts` lints last. The comms `measured` antenna pattern landed on #47 at `2e9f79e`.
- 14:06 Structure raises fidelity on #51 (`173216c`): two tunnel hatches, no pyro at undocking,
  two ascent circuit interrupters at staging; the hatch card is closed. The interrupter edge goes to
  power if those states are power's.
- 14:10 Governance PR #52 merged (`910adc9`); later governance changes go on a follow-up PR.
- 14:06–14:10 Research delivered `sources/structure.md`, `comms.md`, `propulsion.md`. Tunnel
  volume is published (11.6 ft³, ODB Vol I Fig 4.2-8.1). Docked burns need 9 of 12 latches: routed
  to propulsion as an interlock edge.
- 14:08 ECLSS models O2 supply pressure on the heater relay (865/935 psia) on #46; 21 of 25 ready.
- 14:12 Draft #54 (crew). It merges after #47 with the rest. ECLSS writes its CO2 edges against it.
- 14:06–14:13 Power removes the shed ladder (cautions only). Ascent interrupters deferred to the LM
  power slice. ECLSS resolves O2 supply pressure on #46 (`57c5db3`) and routes the cryo heaters to
  power as a periodic load. Crew's #54 takes the census to 156 states. `fleet_class` vocabulary owed
  by lane 9. `sources/rcs.md` shows the CM jet differs from the SM's; the CM-jet answer is reopened
  with the RCS lane.
- 14:14 ECLSS holds its crew-count CO2 edges until #54 is on `main`; CO2 removal becomes a rule after CRYO PRESS.
- 14:15 Lane 9 publishes the `fleet_class` vocabulary; every fault-owning lane adds the field now.
- 14:16 Thermal adds `fleet_class` and `acts` on #49 (`efdb857`; only `pump_no_flow` and `heater_stuck_on` act automatically) and records Fraction and Chosen in ADR 0003 (`b60c310`).
- 14:17 Propulsion models SPS helium pressurization on #50 (`26532d3`; branch ready 74 → 80, debts 265 → 256). The coordinator answers its scope questions under D33 (D41).
- 14:19 Power ties batteries A and B to the main buses on #43 (`a9c27d5`) and adds `acts` and `fleet_class`; the A–B tie's replacement follows #43.
- 14:20 ECLSS classes all 21 faults on #46. The O2 tank heaters move onto a coupling node so power can load them.
- 14:21 #43's aurora job is red: policy D no longer overheats inside the window at 1,401 W. The coordinator lets #43 carry the matching `aurora/tests` assertion if thermal's re-derivation does not fix it (D42), posted to John to override.
- 14:22 The CM jet is split (D43) on #44 (`b4c3c44`), which also carries the full CM jet table.
- 14:22 #47 (`4a531df`) adds `refused_bands` and enforces `minimum`/`maximum` everywhere. Lane 9's order after #47 now starts with `gated_by` on state conditions.
- 14:27 The coordinator chooses the crew-day values under D33 (D44). The potable-water heater's sleep switch-off goes to power as a PWR-02 confounder. #47's interlock test fixed at `fdbedf9`.
- 14:28 ECLSS puts the O2 tank heaters on their own node (#46 commit 0007). Metabolic figures in `vehicle.yaml` differ from the AOH; recorded as unowned debt in `status.md`.
- 14:29 Thermal's MET-0 re-derivation is on #43 (`efd60cf`). Policy D's non-loss is the corrected physics, so #43 carries the `aurora/tests` expectation change (D42).
- 14:31 Governance PR #53 merged (`e90d9f1`).
- 14:32 Structure publishes the docking-latch count on #51 (`3dd1e64`) for propulsion's docked-burn guard.
- 14:34 Crew reports #54's fidelity (`ed840ef`). The `perceive()` caller goes to lane 9 after #47.
- 14:35 Lane 9's order after #47 adds the `ask_crew` `perceive()` caller after the instrument layer.
- 14:36 Docking-latch talkback wiring sourced (TN D-6854 Fig A-7(b)); the research thread's earlier reading is struck through in `structure.md`.
- 14:39 John confirms the delegated decisions and adds a closing phase: a light-touch fidelity calibration pass per station after the lanes merge (D45).
- 14:41 Comms reports #48's fidelity: `link_snr` from Bellcomm CR-125670. Open across lanes: the CSM transmit chain uses LM figures, and the PA is an AC load whose inverter path is power's call.
- 14:41–14:43 Draft #56 (GNC and RCS, `claude/vehicle-gnc-rcs-03b5j4`): pointing modes, ADR 0005; rebases after #44 and #47. GNC scope answers under D33 (D46); three engine asks to lane 9.
- 14:44 Research lane finished: eight source files under `sources/` in the project's shared folder. `thermal.md` finds the SM bays are not glycol-cooled; thermal decides the fix on #49.
- 14:46 Power's AC distribution and comms' ground end decided under D33 (D47). GNC's dynamics seeding is on #47 (`4761970`).
- 14:46 #45 (unpin) merged as `e990b25`, `required` green including both episode jobs. Every lane rebases; #46 next, then #47. From now on a closing PR does not touch the pinned figures, the README status paragraph or `plant.py`.
- 14:47 John: "we want to be able to model apollo 13" (D48). Station handovers come into the episode; MET 0 moves to Apollo 13's TLI.
- 14:48 John confirms the epoch shift (D49). 14:49 He notes a future direction, a Kerbal-style ad-hoc mission system, that must not change current work (`status.md`, "Future direction").
- 14:51 Structure #51 (`aa3231c`) and thermal #49 (`0427cac`, rebased onto `e990b25`) report. Scope answers under D33 (D50): tunnel pressure as a follow-up; the SM service bay off the glycol loop. Research infers the inverter configuration from the Apollo 11 checklist.
- 14:53 #47 carries `cooled_by: space` with a required `cooled_by_note` (`d221c8a`).
- 15:01 GNC + RCS #56 rebased on `e990b25` as `d50194c` (268 debts, 0 refusals): `gnc.sun_direction_body` from a fixed Apollo 13 TLI sun line, and `set_ptc_roll` (0.3 deg/s, as flown at three revolutions per hour). The PTC roll goes in the ledger as a decision.
- 15:02 Research delivers the Apollo 13 MSFN network as flown (`sources/comms.md`); no as-flown rise/set table. D51: Vanguard and ARIA positions from the pre-flight press kit, labelled planned. Comms models handovers in its own PR after #48.
- 15:03 Governance #55 merged as `7ad188f` (D41–D44, lane events to 14:30); the next batch carries D45–D51.
- 15:23 D52: GNC navigation (`select_nav_source`) as a reduced Apollo-shaped covariance model, not the corpus's 15×15 EKF; recorded as a dated deviation in ADR 0005 on #56. ECLSS owes a vent state; GNC owns the edge into navigation.
- 15:26 Merge order becomes #46 → #58 → #47 → the rest. Lane 0's draft #58 (`11c8a95`) unpins the census figures #45 kept on purpose, judging that keeping them pinned was the wrong call for a parallel sprint.
- 15:26 ECLSS sources LiOH CO2 removal (`sources/eclss-co2.md`) and finds two repo ratings wrong (LM secondary cartridge, CSM element count); D53 gives ECLSS the removal stock, absorber counters, vent state and `set_overboard_dump`.
- 15:31 GNC + RCS (lane's call, coordinator agrees): the CM RCS becomes a separate stock isolated in coast, as flown; the slew law allocates SM quads only, which removes the ~2 % CM pricing error in E-RCSP-RCS. Lands on #56 after #44.
- 16:10 Governance #57 merged as `6814102` (D45–D51) on a green `required`, seconds before D54 reached this thread; its review follows the merge.
- 16:10 D54: every PR that leaves draft gets an independent Fable review report for John (`vehicle-status/reviews/pr-<N>.md`); merges need green plus a non-blocking verdict.
- 16:11 John confirms D54 on the card: "Merge on clear".
- 16:12 Comms builds the Apollo 13 epoch as its own PR after #48: `met_epoch_utc` at TLI, re-derived elements, periselene-targeted trajectory. Two source conflicts recorded, unresolved (415.8 vs 86.8 n mi; 73.0 h vs 75.24 h arrival). #48 is fixing census pins after its rebase.
- 16:12 The engine lane allows prose-only edits in `check_vehicle.py` and `plant.py` on a lane's own PR when its data change makes the prose stale; logic still goes through the engine lane.
- 16:15 Crew #54 at `e26945e` with #47's branch merged in. D55: a workload driver (`crew_workload_index`) and CRW-01 split per person.
- 16:18 D54 verdicts: #57 clear after its merge (one wording fix: the post-#45 figure convention holds fully only after #58, fixed on #59); #59 clear (#46's draft state fixed); #46 clear with follow-ups. The review finds the cryo O2 fans are AC loads and the heaters 113.88 W DC per tank, so power splits its 166.7 W figure.
- 17:07 GNC + RCS #56 at `312c89c` (24 census-pin fixes): `select_nav_source` now acts, with a divergence alarm whose timing depends on when the ground was last used.
- 17:11 D56: John puts the quiet-coast window `D_TICKS` change on #43 ("On #43"). Power raises the main bus band ceiling to 31.0 V and records the O2 tank split (113.88 W DC heater, 52.8 W AC fans); #43 goes green after #58.
- 16:55 The D54 review of #46 turns blocking on one stale test assertion (`test_vehicle_config.py:3313`) until ECLSS pushes a one-line fix.
- 18:26 Governance #60 merged as `cd80375` (D56).
- 19:33 ECLSS #46 merged as `9a0430a` after a clear D54 review with follow-ups, the first lane on `main`; `main` now 160 states, 86 ready, 261 debts (`plant.py --build-order`, `check_vehicle.py`). Aurora #61 (diode-probe deflake) reviewed clear. The vehicle status report is out; a trial merge of nine PRs measured 124 of 179 ready. #49 and #50 are green, waiting for their slots; power #43 and GNC #56 resolve #46 conflicts by hand; #58 goes ready next, then #47.
- 19:36 Governance #62 reviewed clear. #47 is out of draft at `fbaf9bb`, with `main` merged through #46, and in review. #49 and #50 were green only on a pre-#46 base; both still need a rebase, a CI run and a review.
- 19:51 Governance #62 merged as `e18e022`.
- 20:12 D54 reviews: #58 clear with follow-ups (merges on green, a lane-0 follow-up PR after); #49 clear with follow-ups (bays marked interim). #48 rebased at `23209b6`, queued for review. Thermal moves the descent stage to `cooled_by: space` in the post-#47 space-sink follow-up, a confounder in the ledger (the thermal half of F-09).
- 20:23 Aurora #61 (diode-probe deflake) merged as `4f969aa`, all checks green, review clear; branches carrying `main` past it stop hitting the `test_tier1_gate_runs.py` flake.
- 20:25 Governance #63 reviewed clear with follow-ups (the #49, #58, #48 rows and the header), fixed on #63.
- 20:37 D54 reviews: #47 (`fbaf9bb`), #48 (`23209b6`) and #51 (`8a8c68b`) clear with follow-ups. D57: #51 carries an engine linter rule, owned by lane 9 after merge. Lane 9 picks up #47's follow-ups and the unevaluated `arm_expiry`/`arm_reuse` guards. Research sources the LM descent-stage blanket (emittance 0.01, LMO-510-1070).
- 20:54 Thermal's descent-stage space sink is prototyped (`wip/vehicle-thermal-bay-space` at `2969234`), lands after #47 and power's AC PR; ledger class signal (it removes a false confounder); DPS propellant heat capacity not coupled, recorded as settled for less. Coordinator adds an ascent-stage exterior zone for `lm_rcs_heaters` to the same follow-up.
- 21:09 ECLSS opens draft #64: the CM surge O2 store as a real 3.7 lb store, `set_o2_source` selects the feeding store, CRYO PRESS caution at 800/950 psia; draft until the full suite and CI are green; merge order unchanged.
- 21:13 D58: thermal's LM RCS heater zone is `lm_rcs_clusters` (the four quads, 8 × 17.5 W each, calibrated to Apollo 13's 55–97 °F PTC range), not an ascent-stage exterior; power takes `lm_rcs_heaters` 60 → 560 W; fault injection retires `check_thermal_bay_source_scope`; the uncoupled DPS propellant is a confounder (the lump runs colder than LM-3 past about two days). Posted to John for override.
- 21:25 Governance #63 merged as `f4d576a` (clear with follow-ups, folded in).
- 21:30 D58's band confirmed as the quad caution limits (LM AOH Table 2.9-3, >241 °F or <130 °F, around the 140 ± 8 °F thermostat); Apollo 13's heaters-off 55–97 °F sits below it by design.
- 21:41 Codex reviews run on nyx (John, 21:21) and fold into the D54 reports. #58: a Low for the unpin follow-up (the census test cannot see a feedback or one-way misclassification). #47: six findings confirmed, verdict unchanged; two Mediums lead lane 9's first post-#47 PR (dark-node interlock drops the command result, gating #50; a numeric identity effect refused by the completeness check, gating thermal's duty PR); the 10.5 % DPS throttle floor against TN D-7143's 10 % goes to propulsion. #48: a P1 (power margin published as SNR, CR-125670) and four P2s under review; comms holds #48's merge until the verdict is re-issued.
- 21:44 D59: #48 publishes `link_margin_db` (CR-125670 power margin) in place of `link_snr`; true SNR out; amplifier step 20.0 dB; beamwidth 4.4° and a `vehicle_dynamics` → `ground_received` ordering edge on #48's post-#47 rebase; #48 re-reviewed before merge. Posted to John for override.
- 21:49 Codex pass, verdicts unchanged: #48 keeps its slot, fixes on its post-#47 rebase; #49 non-blocking with a declared transient energy-imbalance debt (met at `660387a`), closed by the space-sink follow-up; #51 keeps its slot, names the tunnel-vent P1 in its pressure-path debt and adds an interim undocked tunnel-hatch guard on its rebase; lane 9 gains a Low (an algebraic gap should clear the published reading). ECLSS #64 out of draft at `e8f8ed5`, with the reviewer, merging after #58 and #47.
- 21:58 #64 reviewed clear with follow-ups at `e8f8ed5`; merges once its `flow: off` Medium is fixed, after #58 and #47. D60: the CRYO PRESS high trip uses CSM-109's 975 psia if sourced (Apollo 11's 950 in provenance); posted to John for override. Fourteen Codex outputs are under `vehicle-status/reviews/codex/`.
- 21:58 D60 sourced (975 psia, A13RB p. 5-22, reproduces the masked trip at 55:54:29). #64 ledger classes recorded. Structure fixes #51's tunnel-vent P1 outright and adds `tunnel_vent_dp_psi` with a 0.5 psid guard, pushing on its post-#47 rebase. Lane 9 gains a depletion-ordering Low. Codex reviewed #63 at `977141e` against `4f969aa`.
- 22:18 #58 merged as `032d12c` (head `d935d4f`, `required` green with both episodes). #47 is unblocked and merges next; every lane resolves census pins to `main`'s side; lane 0's follow-up PR comes off `main`.
- 23:06 Governance #65 merged as `ee08d50` (D57–D60, the Codex pass; clear with follow-ups, and every review and Codex finding folded in).
- 23:18 Power's #43 out of draft at `d603041`, reviewed clear with follow-ups (Codex pass included), merging after #47; owed before `set_source` enters a scenario: a Battery C refusal, a per-bus live signal (read by thermal, ECLSS, comms) and battery drain. #64 reviewed clear at `44e4876` with both Lows fixed, merging after #47. Lane 0's #66 (#58's follow-ups) reviewed clear, holding for #47.
- 23:45 D61: `interlocks_when` gains a state-condition form (lane 9's third post-#47 PR); derived channels only for what the crew sees; first user ECLSS's `o2_reserve_10` on `set_o2_flow`. Power's dead-bus signal is `power.load_powered` (node `load_shed_state`), read by thermal, ECLSS and comms in follow-ups.
- 23:51 ECLSS ledger line from #64 at `bf36a59`: the reserve re-open gap (`set_o2_flow` can re-open a primary S/M draw under `o2_reserve_10` until lane 9's state condition lands), class confounder, Medium follow-up. Lane 9 queues a per-vehicle command vocabulary (refusing LM surge at the command) beside the state condition and per-element dwell.
