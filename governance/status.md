# Programme status

As of **2026-10-17 17:12 UTC**, `tachyon-beep/space_chassis` `main` @ `ecd44af`. Kept by the
governance thread during the vehicle sprint (`decisions.md` D30) and refreshed after each merge,
decision or lane event the coordinator relays. **Verify against the code and the PRs before trusting
any line here.** This is the page a new agent reads to learn who owns what and what waits on whom;
the sprint's rules and history are in
[`records/2026-10-17-vehicle-sprint.md`](records/2026-10-17-vehicle-sprint.md).

## Where the code is

| | where | checked |
|---|---|---|
| `main` | `b525b48` (PR #42); since 2026-10-15: #2–#9, #35–#38, #40 tranche 2 (`54257b7`), #41 recovery fix (`c1b244d`), #42 | `git log --first-parent origin/main` |
| vehicle | 152 states, **74 ready**, 24 owe a value, 14 an edge, 40 a rule; **265** declared debts | `vehicle/tools/plant.py --build-order`; `check_vehicle.py` on `b525b48` |
| quiet-coast episode | accepted after #40 (policies A/B full success, C partial, D physical loss; restart at tick 60,000 reproduces every hash). A milestone, not a record: lanes may move its numbers (D29) | PR #40 |
| CI | `required` rolls up lint, the aurora suite, the vehicle check on 3.12 and 3.13 (~50 min each), readiness and the quiet-coast episode jobs (hours); vehicle jobs skip when a change cannot touch `vehicle/` | `.github/workflows/ci.yml` |
| nyx checkout | `main` `475840a`, 100 commits behind; untracked `FIXME.md`; not fetched | Remote Control read, 2026-10-17 13:26 (D28) |

## Vehicle sprint: who holds what

Merge order: ~~#45~~ (merged 14:46, `e990b25`) **→ #46 → #58 → #47 → the rest** (#58 inserted at 15:26). From 16:09 each PR also needs a non-blocking independent review verdict (D54) (rebase onto `main`, merge when `required` is green).
After the lanes merge: a light-touch fidelity calibration pass per station (D45).
#45 is on `main`; every lane rebases. A PR that closes a state no longer touches the test figures #45
unpinned; the census figures #45 kept stay pinned until #58 merges, and only after that does such a PR
leave every figure, the README status paragraph and `plant.py` alone. README count-line conflicts
resolve to `main`'s side plus a test re-run.

| # | lane | PR | state | waits on |
|---|---|---|---|---|
| 0 | Unpin vehicle test figures | [#45](https://github.com/tachyon-beep/space_chassis/pull/45) | **merged** 14:46 as `e990b25`, `required` green with both episode jobs | — |
| 0 | Unpin the census figures #45 kept | [#58](https://github.com/tachyon-beep/space_chassis/pull/58) | draft (`claude/vehicle-unpin-figures-ojibgi`, `11c8a95`); crowded nodes, sentinel, commanded/dwell, tick order, cross-domain reads, reads list, verb/channel/fault/point counts, mover and seed censuses, domain-clause and `faults.py` fixtures, 152-state docstrings, each held to the linter's `domain_figures`, the plant's world, or found by pattern | #46 |
| 6 | ECLSS states | [#46](https://github.com/tachyon-beep/space_chassis/pull/46) | out of draft; D54 review blocking since 16:55 on one stale test assertion (`vehicle/tests/test_vehicle_config.py:3313`) until ECLSS pushes the one-line fix (engine helper: two-argument interlock condition); 21 of 25 ready; `fleet_class` on all 21 faults (12 onboard, 9 precursor), 261 debts on its branch; CO2 and humidity wait on crew | #45 |
| 9 | Fault injection into the step loop | [#47](https://github.com/tachyon-beep/space_chassis/pull/47) | draft; carries the engine work for other lanes (list below); per-tick hashes differ from `main` (nothing pins them) | #45, #46 |
| 1 | Burn down power subsystem | [#43](https://github.com/tachyon-beep/space_chassis/pull/43) | draft; per-cell fuel cells, PWR-02, battery tie; standby pump *off* with thermal's MET-0 re-derivation (`efd60cf`: environment heat 1,285.5 W, radiator start 288.02 K, hot-hold 293.40 K, evaporator hold 984.8 W; ADR 0003 item 9); policy D's non-loss is the corrected physics, so #43 carries the `aurora/tests` expectation change (D42), and now also the `D_TICKS` 9500 → 11000 change in `aurora/tests/test_quiet_coast_window.py` with an ADR 0003 bullet (`a0c6db3`, D56); vehicle fixes at `5e16f21`; main bus bands and `csm_bus_a/b` `v_band` ceiling 30.5 → 31.0 V (ODB Fig 4.1-11 nominal range; the corpus's 30.5 marked Sim; bus A reads 30.96 V at MET 0; floor stays 27.0, so quiet-coast margins are unchanged); the 13 remaining red tests are census pins a trial merge of #58 clears | #58 (goes green after it); #47 before the PWR-02 `fault:` row |
| — | Source RCS thruster geometry | [#44](https://github.com/tachyon-beep/space_chassis/pull/44) | draft at `b4c3c44`; SM and LM jets sourced; full CM jet table, SM radii, LM jet 4 note corrected; CM engine split (D43); minimum impulse bit owed | #45; primary sources (now reachable, D32) |
| 5 | Comms remainder | [#48](https://github.com/tachyon-beep/space_chassis/pull/48) | draft; occultation from the orbit; `carrier_lock` waits on #47's seeding; fixing nine census pins and an int mapping key after its rebase (`7f04536`). Next, its own PR: the Apollo 13 epoch (patch `vehicle-status/comms-lane/apollo13-epoch.patch` in the shared folder): `met_epoch_utc` 1970-04-11T21:54:47Z (MSC-02680 range zero p. 2-1 plus TLI 2:41:47.2 GET, Table 4-II), Moon from Horizons, elements re-derived (a 306,840 km, e 0.97861), `trajectory.py` targeting the Mission Report's 415.8 n mi periselene (pericynthion 770.8 km, return perigee 39.4 km, arrival light time 1.36 s, occultation MET 72.82–73.27 h, Goldstone first sees the vehicle at MET 0.22 h); unresolved: the Mission Report's text says 415.8 n mi where Table 4-III says 86.8 n mi, and the ladder keeps a 73.0 h arrival against 75.24 h as flown | rebase onto `main` (the 265-debt docstring test should clear), #47 |
| 2 | Finish thermal | [#49](https://github.com/tachyon-beep/space_chassis/pull/49) | draft, rebased onto `e990b25` as `0427cac`, lint clean, 259 debts; SM service bay off the glycol loop (D50; `cooled_by: space` with a required `cooled_by_note` is on #47 at `d221c8a`); SM side area from `thermal.md` Q5 (154 in diameter, 155 in AOH or 162 in ODB long; no printed side area, so thermal chooses and cites); `heater_bank_duty` held | #47 (`cooled_by: space` on it at `d221c8a`) and lane 9's numeric-argument change |
| 3 | Propulsion and propellant | [#50](https://github.com/tachyon-beep/space_chassis/pull/50) | draft, head `26532d3`; on its branch ready 74 → 80, debts 265 → 256; scope answers D41 | #45; primary sources (now reachable, D32) |
| 4 | Structure states | [#51](https://github.com/tachyon-beep/space_chassis/pull/51) | draft at `aa3231c`; hatch *Latched*; tunnel volume set (ODB Vol I); `fleet_class` on all 11 faults (7 precursor, 3 onboard, STR-04 out of scope with note); `acts: crew` on all thresholds; `structure.docking_talkbacks` from the 1-5-9 / 3-7-11 wiring; latch count for the docked-burn guard; work depending on #46/#47 held as patches in the project's shared folder (`vehicle-status/structure-lane/`); tunnel pressure a follow-up (D50) | #46, #47 |
| 7 | GNC and RCS lane | [#56](https://github.com/tachyon-beep/space_chassis/pull/56) | draft (`claude/vehicle-gnc-rcs-03b5j4`, `312c89c`, 24 census-pin fixes, CI re-running); slew law behind `set_attitude_target`, rigid body, RCS propellant debit; ADR 0005; scope answers D46; `gnc.sun_direction_body` on `vehicle_dynamics`; verb `set_ptc_roll` (0.0 or 0.3 deg/s, A1, translunar and transearth coast, interlock `rcs_uncommanded_rate`); `set_attitude_target` quaternion declared uncarried until array arguments land; `select_nav_source` acts as a reduced Apollo-shaped model (D52: a ground vector gives position σ 185 m, chosen, and velocity σ from the Apollo 13 MSFN table; onboard sources coast on the last vector; `ground_uplink` is never refused, the four onboard choices are refused while the estimator diverges; deviation in ADR 0005 on #56, needs ECLSS's vent state; gnc-internal states `nav_source`, `msfn_arc_s`, `nav_vector_arc_s`, `nav_coast_s`, `nav_velocity_sigma`, `nav_position_sigma` in progress); after #44, a separate CM RCS stock (298,750 N·s from #44's `thruster_cm`) that nothing in coast draws, the coast slew law allocating SM quads only, and E-RCSP-RCS keeping 277.8 s for SM jets only; next per-quad availability | #44, #47 (three engine asks) |
| 8 | Crew lane | [#54](https://github.com/tachyon-beep/space_chassis/pull/54) | draft (`claude/vehicle-crew-bogej1`, `e26945e`, #47's branch merged in, 16 gate pins updated, CI re-running); per-cabin crew count, location as a rule, potable water drains; next the crew day (sleep, meals, work as sourced activities; meals as water draws to tell from a leak); D-06 revision 1 (D38), dialogue per console (D39) | #45, #47 |
| 10 | Avionics FDIR | — | not started | last; needs lane 9's faults |
| 9 | Instrument layer (after #47) | — | owned by the fault-injection lane (it lives in `plant.py`/`console.py`); its order after #47: `gated_by` on state conditions, the instrument layer, the `ask_crew` `perceive()` caller (needs #54 on `main`; perceived by the asking console only, audit to the evaluator, never in the diode), the decision-age delay at the window, the fair-chance stamps, then the `fleet_class` and `acts` lints | #47 |

Engine work on #47 (at `4a531df`) for other lanes: `refused_bands` on numeric arguments, and
`minimum`/`maximum` now enforced everywhere (they were declared and read by nothing; all lanes told); the fault hook (`becomes`, `scale`, `becomes_from: magnitude`);
ruled-discrete seeding (structure, comms); the `arm_event` effect; numeric carried arguments,
refused not clamped (thermal); per-argument command routing `when:`; burn sequencing as a discrete
machine with command and logic movers (propulsion); node-read interlocks (propulsion's
`resolve_interlock` from a coupling node); the ECLSS sentinel fix (`_walk` overwrote
`values["internal"]`); the interlock test fixed at `fdbedf9` with `set_vent_valve` (structure warned
that making `hatch_open_with_pressure` readable moves that test). Held: `gated_by`, waiting on the in-burn-guard answer's application (D35).
Burn sequencing and node-read interlocks change truth bytes; side effect, ECLSS
`co2_absorber_low` becomes evaluable. From GNC (#56): seeding a ruled `dynamics` state's vector initial is on #47 at `4761970`
(deep-copied initials); GNC edits the `MULTI_STATE_NODE_FIGURES` prose on #56; array-valued
arguments come after the crew perception caller (console form comma-separated, no spaces). Queued for lane 9 after #47: an argument check for `set_throttle` (`dps_throttle_band`) and
`gated_by` on a state condition (propulsion). The "61 nodes" prose
count goes in lane 9's rebase over #46; the linter's derived line becomes the only figure. The comms `measured` antenna pattern is on #47 at `2e9f79e`
(bound G ≤ 41253/θ², `historical` provenance required). #46 also carries a state-level `preloaded:` in `advance()`/`_classify()`.

Cross-lane follow-ups: ECLSS publishes a vent state (waste water, urine, O2 overboard) for GNC's navigation edge (D52, D53); power's 400 Hz AC distribution (D47) lands in one PR straight after #43;
research (`sources/power.md` Q7) infers the normal inverter configuration from the Apollo 11 CSM-107
checklist's malfunction steps (no stated table): S-band telecom group 1 on AC1 and group 2 on AC2; a
glycol pump, the battery charger and suit compressor 2 on AC bus 1 (a **confounder**: a main-A fault
shows as glycol, charger and comms trouble together). It comes with the glycol pumps at 52 W AC each, the cryo fans and comms' S-band rows (the PA is a 45/90 W AC
load, AOH 2.8-40); thermal's `amp_dissipation_w` follows. The CSM transmit-chain figures in comms are
still LM figures. Power's shed ladder is cautions only (E-BUS-SHED and its tiers removed;
regime rows dropped from E-BUS-GNC, E-BUS-COMM, E-BUS-RCS and E-BUS-INST; comms and GNC told). The
ascent circuit interrupters wait for the LM power slice; structure holds a placeholder
`lm_ascent_interrupter`. ECLSS routes each cryo tank's 166.7 W heater and fan to power as a periodic
load (a confounder): power cannot read `o2_tank_heaters` on node `internal` (`plant.md` §2 sentinel
rule), so ECLSS puts it on its own node on #46 (commit 0007, edges E-O2-HTR-BUSA/BUSB, 166.68 W each),
and power adds, after `main` has it, the two gated loads (tank 1 on main A, tank 2 on main B), splitting the 166.7 W figure: each tank's heaters are 113.88 W DC and its 52.8 W of fans go as AC rows on power's AC PR (AOH Fig 2.6-2, found in #46's review); the CRYO PRESS caution follows #46. Crew (#54) adds `csm_crew_count` and
`lm_crew_count`, taking the README census from 152 to 156, so lanes adding states rewrite it from the
tools on rebase (sprint rule 4). `fleet_class` vocabulary is published (14:15; the project's shared folder,
`vehicle-status/fault-injection-lane/fleet-class-vocabulary.md`): `precursor | onboard |
out_of_scope`, with a required `fleet_class_note` on `out_of_scope`. After #47 the lint refuses
`service` with `precursor`, a `precursor` whose latency is only sub-minute, and `out_of_scope`
without a note; a missing field is debt until every domain has it. Every fault-owning lane adds the
field now. Propulsion takes the docked-burn requirement (9 of 12 latches) as an interlock
edge from structure; structure's tunnel volume is published (11.6 ft³, ODB Vol I Fig 4.2-8.1),
correcting the repo's "unpublished" note. ECLSS takes the structural-leak drain edge into `cabin_leak_csm`/`lm` after
#51 lands. Lane-map correction: cabin water vapour waits on crew, like CO2.

Cross-lane changes in flight: the standby-pump fix (D29) is power's `load_enabled` line in #43 plus
thermal's re-derived MET-0 equilibrium and service-bay G (29.6875 W/K) and C (213,750 J/K),
now on power's branch (`efd60cf`); the service-bay 380 W G and C follow on #49 after #43 is on
`main`.

## Waiting on John

| item | options | asked in |
|---|---|---|
| D22 pilot credentials for the 10-minute smoke | — | Vehicle to smoke-ready |
| archive `space_vehicle` (D21) | a repository setting; safe since PR #35 | `records/2026-10-15-space-vehicle-archive-check.md` |

## Answered for John (confirmed by him at 14:39, D45)

Answered by John today: target scenario Apollo 13, so station handovers are in (D48, 14:47);
power d / standby pump *off* (D29, 13:35); any domain, read-only (D32, 13:46);
D-07 crew dialogue *per console* (D39, 14:00).

Answered by the coordinator on the independent review at 14:00: the arc report's eleven (D38).

Answered by the coordinator under D33 at 13:50 (D35), each the lane's recommended option:

| item | answer | lane |
|---|---|---|
| power a: bus tie | *apollo* (battery-to-main-bus tie, fuel cell 2 cross-feed, no A–B tie) | #43 |
| power b: shed ladder | *crew* (cautions only; the crew sheds) | #43 |
| power c: source converter | *retire* (with PWR-01) | #43 |
| RCS: the CM jet | **split** (D43): the CM engine its own article, 96.0 lbf (427.0 N) and 272.0 s on its 12 jets; was *owe* at 13:50 while the data was missing | #44 |
| comms: Earth-link delay | computed per tick from the orbit; 1.3 s constant retired; the window-side consumer raised separately | #48 |
| thermal: pump speed | *fraction* of rated | #49 |
| thermal: bay thermal masses | *chosen* C and G in a heat balance | #49 |
| structure: `hatch_state` initial | *Latched* | #51 |
| ECLSS: `o2_supply_pressure_psi` | resolved from sources on #46 (`57c5db3`); six source choices recorded at the end of `sources/eclss.md` in the project's shared folder | #46 |
| propulsion: in-burn monitors | leave `start_burn`'s admission list, become mainstage-gated monitors; pressurant from sources, 186 psia design value if primaries disagree | #50 |

## Unowned debt

| debt | why deferred | candidate owner |
|---|---|---|
| `vehicle.yaml` `consumables.metabolic` uses the NR-glossary 0.91/0.91 kg per man-day; the AOH Block I table gives CO2 2.12, O2 1.84 and water vapour 4.0 lb per man-day. Moving shifts CO2 by ~5 % and cascades through derived nominals | adds no decision (D37, D40) | whoever owns `consumables.metabolic`: the avionics lane or a cleanup pass |

## Fidelity ledger

"Preference more fidelity where it doesn't start creating significant delivery risk" (D34, D31). Added fidelity must add an interesting option for a scenario, behaviour, decision or challenge,
not a single forced move (D37). "What option it adds" is classed **signal** (a new signal to debug),
**confounder** (first- or second-order effects on another reading), **event/noise** (barks and
non-mission events the team must triage), **decision** (a choice the crew or fleet faces) or
**none** (D37, D40). Standing input for every row: the target scenario is **Apollo 13** (D48).
Keep *none* entries listed: the ledger is the input to the calibration pass
that closes the sprint (D45). One line per lane: the fidelity it builds
to, the option it adds, and any approximation it deliberately keeps. Filled from what lanes report
to the coordinator; *not reported* means the lane has not said yet.

| lane | builds to | what option it adds | approximations kept |
|---|---|---|---|
| power (#43) | Apollo EPS as flown: each fuel cell a module (AOH 2.6); a, b, c as answered (D35): battery-to-main-bus tie plus fuel cell 2 cross-feed, no automatic shed ladder (cautions only, the crew sheds), source converter retired; batteries A and B tie onto the main buses through `set_source` as Thevenin sources behind diodes (JEPS 37.1 V, 0.364 Ω); `acts` on all 14 thresholds (`lcl_overcurrent`, `tie_dv_limit` automatic); `fleet_class` on all 11 faults (PWR-02/07/10 precursor, PWR-03/08 out of scope with notes, the rest onboard) | **decision**: tie the batteries in when fuel cell 1 degrades under PWR-02, at the cost of entry reserve; after #43, AC distribution adds a **confounder** (an AC load's DC cost depends on what else its inverter carries) and a **decision** (inverter failure, moving an AC bus) (D47) | for lack of a text source: fuel-cell terminal a linear secant of the AOH envelope, not the polarization curve (graphical only, A14DB), extrapolated below 400 W per module; no feeder or motor-switch drop (0–1 V, WP02 E-2); no AC buses or inverters on #43, so the glycol pumps are 250 W DC loads until the AC PR (52 W AC each, D47); load draws mostly `chosen`, constant-power, no inrush; battery derate, temperature and internal resistance unsourced (AOH 0.234 Ω and JEPS 0.364 Ω disagree; JEPS taken for J-mission effectivity unless John says otherwise); charger output current graphical only; named gaps: battery C diode feed; battery charge spend (`battery_charge_j` held, charger edge E-BUS-BAT owed, research asked to digitise AOH Fig 2.6-11); the A–B tie is replaced by BAT A/C, BAT B/C and the fuel cell 2 cross-feed in a follow-up after #43 (~55 test fixtures reference it); O2 tank heater load gated once #46 is on `main` |
| thermal (#49) | the loop as heat balances; bays `C dT/dt = Q − G(T − T_coolant)`; the SM service bay radiates to space, not into the loop (D50), and the glycol pumps sit in `csm_avionics_bay` | removes a false **confounder** (the bay mimicking a loop fault); adds a **signal** (an attitude-following bay trend), a **confounder** (PTC roll against HGA hold drives the bay, radiator and SPS line together) and a **signal** (fuel-cell heat leak about 310 W at 80 °F, ODB Fig 4.1-21, an edge from power's fuel-cell current) | bay C and G are `chosen`, bounded by limits (ADR 0003 item 11); pump speed as a fraction of rated (no rated rpm found); both below sourced fidelity until the research thread reads TIR 580-S-7159, NTRS 19670039777, LM0-510-1036 and the AOH §2.7 table; crew food-prep heaters approximated (a periodic signal adding no decision; meal events are crew's); `sources/thermal.md` finds the SM bays are not glycol-cooled, so the service-bay-to-coolant coupling on `main` has no physical basis (thermal decides the fix on #49) |
| comms (#48) | `link_snr` rule from Bellcomm CR-125670 Table II (SNR = 12.5 dB + margin); blackout and `light_time_s` from geometry; recorder capacity 92.16 Mbit sourced; high-gain antenna from TN D-6723 Table I (25.7/18.0/8.0 dB at 4.4/11.3/40°), chosen over the 1969 AOH because the post-flight report says the narrow-beam spec was not realizable; `carrier_lock` waits on #47 | **confounder**: SNR moves with PA on/off, antenna, range and pointing; **signal**: blackout and light time; **event/noise**: recorder fill; pointing a crew trade | recorded as debt: recorder inflow owed; `frame_loss` owed (no SNR-to-loss relation sourced); ground end at the Earth's centre for now; station-gated visibility follows in comms' own PR after #48, handovers modelled geometrically from coordinates of the Apollo 13 MSFN network as flown (`sources/comms.md`: nine 30-ft sites, three 85-ft primes with wing stations, USNS Vanguard, four ARIA, Parkes and the Goldstone 210-ft) and cross-checked against the flight plan's planned bars, since no as-flown rise/set table exists; Vanguard and ARIA positions are pre-flight press-kit values labelled as planned (D51); `met_epoch_utc` moves to Apollo 13's TLI (D48, D49; comms sources the times); candidates: the 30-ft antenna keyhole (**signal**), the ground-station command computer faults at 3:58 and 11:56 GET (**event/noise**); tracking station choice (210-ft dish +8 dB); receiver noise knee and saturation; the Moon in the ground beam; omni look-angle wander; medium and wide beams |
| propulsion (#50) | SPS helium pressurization as rules (178 psia loaded, 186 psia regulated, blowdown below it; E-PRESS-PROP drain 5.797e-7 kg/s per N); thrust a first-order lag to rated; chamber pressure proportional to thrust | **signal**: the coast feed reads 95.7 against 100 in a burn, which exposes PRP-01's stuck-high sensor; a helium leak becomes a TEI helium-margin **decision** | recorded as adding no decision: isothermal ideal-gas bottles, no launch ullage helium (~6.6 kg margin), no injector line drop (no source), 5 s ullage fill chosen; bottle cooling near blowdown approximated for now; DPS thrust and chamber pressure gaps (throttle-to-thrust law unsourced, `main_propulsion_diode.md:36`); no start transient (none published) |
| RCS geometry (#44) | per-jet SM, LM and CM geometry from primary sources (CM from the rendered Data Book pages), linter-checked; the CM engine its own article (D43) | not reported | minimum impulse bit owed |
| fault injection (#47) | onset as a step change on the moved state, same tick | not reported | a ramp is a domain rule's job, not the plant's |
| structure (#51) | two tunnel hatches (CM forward, LM overhead) in `hatch_state`, so the ring seal matters only with a tunnel hatch open; undocking fires no pyro (CSM News Reference p. 88); staging also fires two ascent circuit interrupters (Grumman study guide p. 93); latches, hatch and pyro as discrete devices; after #47: `pyro_health` fail-to-fire, descent stage separates only when all five staging devices fire, jettison only when the ring charge fires, `leak_sources_g_s` summed by the leak rule | **decision** (close the tunnel before latch release) and **confounder** (tunnel versus cabin leak); talkbacks add a **confounder** (a stuck switch holds the barber pole) and a **decision** (an unindicated latch failure found only by tunnel inspection, as Apollo 16's latch 10); tunnel pressure (D50) adds a **signal** and **decisions** (the latch-release guard, a hatch-integrity check, the pre-jettison vent) | latches move instantly to the drive (1 s dwell only; actuation time unsourced); the `one` scope is recorded and acts on nothing (re-cocking a failed latch unsourced); leak with an unlatched hatch or unseated ring above 0.5 psid is a named gap (aperture and seal unsourced; tunnel volume now set); configuration states still flip on the event until #47; `hatch_open_with_pressure` unevaluable (prose `gated_by`) |
| ECLSS (#46, 21 of 25 ready; CO2 edges written against #54) | cabin leak per gas (bulk-flow shares); `set_o2_source` partly guarded through a general two-argument interlock condition (ADR 0004 amended; lane 7 can use it for its two verbs); suit loop on its compressor at 35 cfm, switched by `set_suit_fan`; O2 supply pressure on the Apollo heater relay (on 865 / off 935 psia, rate from the AOH p. 2.6-13 repressurization table; the Apollo 11-dated AOH chosen over the Apollo 13 Review Board's 950 psia caution and 983 psig relief); crew-count CO2 edges derive from `co2_kg_per_crew_day` (held as a patch in the project's shared folder, `vehicle-status/eclss-lane/held/`, applied once #54 is on `main`); next after CRYO PRESS: CO2 removal as a rule (suit-loop flow × concentration × spent-absorber efficiency); the ~12 h LiOH canister change (`crew.md` 64, 82–101) goes into the CO2 removal piece as a crew event; CO2 removal sourced (`sources/eclss-co2.md`: single-pass efficiency about 0.7, flat to about 70 % bed life then falling, Apollo 13 canister test CSD-A-1066), landing in ECLSS's CO2 removal PR after #46 with two repo ratings corrected (LM secondary cartridge 17.9 man-hours, not 78, Apollo 13 MR 6-10, spares one primary plus two PLSS, not six; CSM element 36 man-hours, changed alternately every 12 h, 20 carried, TN D-6718) and a `set_overboard_dump` verb (D53) | **signal**: the heater-cycle sawtooth changes shape with quantity, and a pressure that will not hold is the Apollo 13 signature; CO2 removal is also a **signal**, and fixes constant crew-nominal removal draining the empty LM's CO2 at MET 0; **decision** plus **signal**: LiOH capacity against crew count is the Apollo 13 CO2 decision surface | cabin H2O waits on crew production (D-06), like CO2, since a removal-only vapour stock would dry the cabin; crew O2 uptake waits on `crew_state`, so cabin O2 still rises by the metabolic term; humidity waits on a sourced condensing heat exchanger rate, then uses 4.0 lb per man-day vapour |
| unpin (#45) | — (test figures, no model) | — | — |
| crew (#54 at `e26945e`) | `crew_activity` (sleep, meal, work) on `crew_state`; metabolic crew-equivalents with sleep at 0.7 (D44); per-cabin crew count; location as a rule; a `perceive()` lookup for D-06 (its caller is engine work for lane 9 after #47); `fleet_class` on 7 crew faults (CRW-01/05/06 onboard, 02/03/04/07 precursor); `acts: automatic` on all 9 crew thresholds (annunciations and lie-prevention refusals; none spends a resource) | **event/noise**: meals as water draws the team must tell from a leak (D40); the potable-water heater's 45 W sleep switch-off (FP11 pp. 3-11, 3-16) is a **confounder** for PWR-02, routed to power and gated on `crew_activity`; asking the crew as a **decision**; **signal**: `crew_workload_index` (D55) separates a busy silence from incapacitation (a CRW-01 false positive), at the cost of repeated questions; **decision**: CRW-01 split per person, so a scenario can take out one named crew member | recorded as debts: reading time per gauge not modelled (waking a sleeper is); no surface rest schedule (it would add a 4–5 h window where nobody answers); EVA egress not gated on hatch or suit loop (other domains' sentinel states; it would add only a refusal); alerts do not feed workload yet (`alert_lifecycle` has no rule), a crew debt; workload demand levels, highest-not-mean and the 120 s busy time are chosen values (D55) |
| GNC + RCS (#56) | a rate-limited eigenaxis slew on the SM's DAP couples through the docked stack's full inertia tensor; every slew and hold debits the tank (10° at 0.5°/s ≈ 2.7 kg; hold ≈ 3.2 kg/day at 0.5° deadband, 0.32 kg/day at 5°); a torque-free PTC roll cones from the products of inertia | **decision**: slew rate and deadband against the propellant reserve; **confounder**: `impulse_total` and propellant drain diverge in a long hold; sun direction in body frame into PTC heating (D46); **decision**: the PTC roll (`set_ptc_roll`), propellant (spin-up ≈ 0.095 kg, stop ≈ 0.12 kg, free drift 0 with 2–4° coning over ten minutes) against thermal balance and HGA hold; navigation (`select_nav_source`, D52): **signal**: when the 1,800 m divergence alarm fires depends on when the ground was last used (leaving it 2 h after TLI, about 1.6 h; at 55 h, about 14 h); **decision**: uplink timing, waste-water dump against navigation, P52 timing, which source to trust after a vent; **confounder**: slow pointing bias from IMU gyro drift (about 2 meru 1σ, seen in P52 torquing angles), sightings lost to vent particles, `rcs.propellant_remaining_pct` reading high in long holds (hold pulses at about 173 s effective Isp against 277.8 s) ; **decision**: pressurizing the isolated CM ring early buys attitude authority and opens a leak and consumption path against a one-shot entry reserve | navigation a reduced covariance record, not the corpus's 15×15 error-state EKF (D52); ground position σ a scope decision; no sun ephemeris (a fixed EARTH_J2000 sun line at Apollo 13 TLI, 1970-04-11 21:54:47 UT, from JPL Horizons DE441 and the Review Board report Table 3-II); no 6-DOF translation; pointing a rate-limited slew law, not a full control loop |

## Future direction (not a decision, no work item)

John, 14:49: "don't let this change the work now, but this will eventually either become or inform
the design of a kerbalesque style 'ad-hoc' mission system for defined craft". The Apollo 13 scenario
(D48) is expected to become, or inform, a Kerbal-style ad-hoc mission system for defined craft.
Nothing in the sprint changes for it.

## Known gaps in CI

| gap | why | closes when |
|---|---|---|
| `vehicle/tests/test_vehicle_config.py::test_a_sub_tick_effect_lands_where_a_short_tick_would_have_put_it` is deselected in `ci.yml` | it needs more than 13 GB; a hosted runner has 16 GB | the vehicle line makes it fit and the `--deselect` line goes |
| the aurora suite is not held to zero skips | two tests skip by design (`aurora/tests/test_doc_claims.py`) | — |
| the live smoke stack is not a required check | `live.yml` builds the image and proves the world, not a change | run it by hand before any adoption merge |

## History

- 2026-10-14: both lanes made durable and reported (`*/records/2026-10-14-*-lane-status.md`).
- 2026-10-15: three-stream restructure (#2); governance review; D1–D23.
- 2026-10-17: tranche 2 (#40) accepted the quiet-coast episode; #41 and #42 merged; the vehicle
  sprint opened (D24–D31, [`records/2026-10-17-vehicle-sprint.md`](records/2026-10-17-vehicle-sprint.md));
  governance batches #52, #53, #55, #57, #59 (D24–D55); D56 onward since.
