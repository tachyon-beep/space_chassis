# Programme status

As of **2026-10-17 14:07 UTC**, `tachyon-beep/space_chassis` `main` @ `b525b48`. Kept by the
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

Merge order: **#45 → #46 → #47 → the rest** (rebase onto `main`, merge when `required` is green).
Lanes keep draft PRs until the coordinator tells them #45 is on `main`.

| # | lane | PR | state | waits on |
|---|---|---|---|---|
| 0 | Unpin vehicle test figures | [#45](https://github.com/tachyon-beep/space_chassis/pull/45) | ready for review | its `required` check; merges first |
| 6 | ECLSS states | [#46](https://github.com/tachyon-beep/space_chassis/pull/46) | draft (engine helper: two-argument interlock condition) | #45 |
| 9 | Fault injection into the step loop | [#47](https://github.com/tachyon-beep/space_chassis/pull/47) | draft; carries the engine work for other lanes (list below); per-tick hashes differ from `main` (nothing pins them) | #45, #46 |
| 1 | Burn down power subsystem | [#43](https://github.com/tachyon-beep/space_chassis/pull/43) | draft; per-cell fuel cells and PWR-02 pushed; standby pump *off* | #45; #47 before the PWR-02 `fault:` row |
| — | Source RCS thruster geometry | [#44](https://github.com/tachyon-beep/space_chassis/pull/44) | draft; SM and LM jets sourced; CM jets, SM offsets, minimum impulse bit owed | #45; primary sources (now reachable, D32) |
| 5 | Comms remainder | [#48](https://github.com/tachyon-beep/space_chassis/pull/48) | draft; occultation from the orbit; `carrier_lock` waits on #47's seeding | #45, #47 |
| 2 | Finish thermal | [#49](https://github.com/tachyon-beep/space_chassis/pull/49) | draft; bays and pump speed advance; re-deriving MET-0 at 1,401 W; `heater_bank_duty` held | #45; the numeric-argument engine change (lane 9) |
| 3 | Propulsion and propellant | [#50](https://github.com/tachyon-beep/space_chassis/pull/50) | draft | #45; primary sources (now reachable, D32) |
| 4 | Structure states | [#51](https://github.com/tachyon-beep/space_chassis/pull/51) | draft; hatch starts *Latched* (`173216c`); `arm_state` waits on #47's seeding; configuration states move to device firing after #47; the interrupter edge goes to power if the states are power's | #45, #47 |
| 7 | GNC and RCS lane | — | started 13:59; attitude as pointing modes, a rate-limited slew law behind `set_attitude_target` (D38) | the geometry lane (#44) |
| 8 | Crew lane | — | started 13:59 on D-06 revision 1 (D38); crew dialogue per console (D39) | — |
| 10 | Avionics FDIR | — | not started | last; needs lane 9's faults |
| 9 | Instrument layer (after #47) | — | owned by the fault-injection lane (it lives in `plant.py`/`console.py`); its order after #47: instrument layer, then the delay at the window, then the fair-chance stamps, then the `fleet_class` and `acts` lints | #47 |

Engine work on #47 for other lanes: the fault hook (`becomes`, `scale`, `becomes_from: magnitude`);
ruled-discrete seeding (structure, comms); the `arm_event` effect; numeric carried arguments,
refused not clamped (thermal); per-argument command routing `when:`; burn sequencing as a discrete
machine with command and logic movers (propulsion); node-read interlocks (propulsion's
`resolve_interlock` from a coupling node); the ECLSS sentinel fix (`_walk` overwrote
`values["internal"]`). Held: `gated_by`, waiting on the in-burn-guard answer's application (D35).
Burn sequencing and node-read interlocks change truth bytes; side effect, ECLSS
`co2_absorber_low` becomes evaluable. The comms `measured` antenna pattern is on #47 at `2e9f79e`
(bound G ≤ 41253/θ², `historical` provenance required). #46 also carries a state-level `preloaded:` in `advance()`/`_classify()`.

Cross-lane follow-ups: ECLSS takes the structural-leak drain edge into `cabin_leak_csm`/`lm` after
#51 lands. Lane-map correction: cabin water vapour waits on crew, like CO2.

Cross-lane changes in flight: the standby-pump fix (D29) is power's `load_enabled` line in #43 plus
thermal's re-derived MET-0 equilibrium and service-bay G (29.6875 W/K) and C (213,750 J/K),
which thermal cherry-picks onto power's branch. Power has applied *off* on #43 (MET-0 CSM load
1,401 W).

## Waiting on John

| item | options | asked in |
|---|---|---|
| D22 pilot credentials for the 10-minute smoke | — | Vehicle to smoke-ready |
| archive `space_vehicle` (D21) | a repository setting; safe since PR #35 | `records/2026-10-15-space-vehicle-archive-check.md` |

## Answered for John, his to override

Answered by John today: power d / standby pump *off* (D29, 13:35); any domain, read-only (D32, 13:46);
D-07 crew dialogue *per console* (D39, 14:00).

Answered by the coordinator on the independent review at 14:00: the arc report's eleven (D38).

Answered by the coordinator under D33 at 13:50 (D35), each the lane's recommended option:

| item | answer | lane |
|---|---|---|
| power a: bus tie | *apollo* (battery-to-main-bus tie, fuel cell 2 cross-feed, no A–B tie) | #43 |
| power b: shed ladder | *crew* (cautions only; the crew sheds) | #43 |
| power c: source converter | *retire* (with PWR-01) | #43 |
| RCS: the CM jet | *owe* (thrust and Isp owed until the CSM data book is read) | #44 |
| comms: Earth-link delay | computed per tick from the orbit; 1.3 s constant retired; the window-side consumer raised separately | #48 |
| thermal: pump speed | *fraction* of rated | #49 |
| thermal: bay thermal masses | *chosen* C and G in a heat balance | #49 |
| structure: `hatch_state` initial | *Latched* | #51 |
| ECLSS: `o2_supply_pressure_psi` | from sources; *Relay* if unsettled | #46 |
| propulsion: in-burn monitors | leave `start_burn`'s admission list, become mainstage-gated monitors; pressurant from sources, 186 psia design value if primaries disagree | #50 |

## Fidelity ledger

"Preference more fidelity where it doesn't start creating significant delivery risk" (D34, D31). Added fidelity must add an interesting option for a scenario, behaviour, decision or challenge,
not a single forced move (D37). "What option it adds" is classed **signal** (a new signal to debug),
**confounder** (first- or second-order effects on another reading), **event/noise** (barks and
non-mission events the team must triage), **decision** (a choice the crew or fleet faces) or
**none** (D37, D40). One line per lane: the fidelity it builds
to, the option it adds, and any approximation it deliberately keeps. Filled from what lanes report
to the coordinator; *not reported* means the lane has not said yet.

| lane | builds to | what option it adds | approximations kept |
|---|---|---|---|
| power (#43) | Apollo EPS as flown: each fuel cell a module (AOH 2.6); a, b, c as answered (D35): battery-to-main-bus tie plus fuel cell 2 cross-feed, no automatic shed ladder (cautions only, the crew sheds), source converter retired | not reported | for lack of a text source: fuel-cell terminal a linear secant of the AOH envelope, not the polarization curve (graphical only, A14DB), extrapolated below 400 W per module; no feeder or motor-switch drop (0–1 V, WP02 E-2); no AC buses or inverters, so the glycol pumps (AC, likely tens of watts) are 250 W DC loads; load draws mostly `chosen`, constant-power, no inrush; battery derate, temperature and internal resistance unsourced (AOH 0.234 Ω and JEPS 0.364 Ω disagree; JEPS taken for J-mission effectivity unless John says otherwise); charger output current graphical only |
| thermal (#49) | the loop as heat balances; bays `C dT/dt = Q − G(T − T_coolant)` | not reported | bay C and G are `chosen`, bounded by limits (ADR 0003 item 11); pump speed as a fraction of rated (no rated rpm found); both below sourced fidelity until the research thread reads TIR 580-S-7159, NTRS 19670039777, LM0-510-1036 and the AOH §2.7 table |
| comms (#48) | blackout as exact sphere geometry per tick from the propagated orbit, Moon at real distance; link budget designed in full; light time `range/c`, 0.02–1.32 s, for the window to apply | **signal**: pointing becomes a crew trade: TN D-6723 Table I gives the high-gain array as 4.4° / 25.7 dB (not the derived 26.7 dB / 9.4°), so the loss at 2° off-axis goes from −0.54 to about −2.5 dB/° | ground end is Earth's centre, not MSFN stations (no station coordinates; stations would change `link_ok` in the episode, so only as a deliberate change); no link-budget constant sourced (TN D-6723 and the USB tables are behind blocked `ntrs.nasa.gov`); `carrier_lock` a discrete with a numeric acquisition timer once #47 is on `main` |
| propulsion (#50) | thrust a first-order lag to rated; chamber pressure proportional to thrust | not reported | DPS thrust and chamber pressure left as gaps (throttle-to-thrust law unsourced, `main_propulsion_diode.md:36` refuses it); feed pressure held at 100 % of nominal with no regulator or line loss; regulator lock-up, bottle blowdown and helium displacement wait on reachable sources; no start transient (none published) |
| RCS geometry (#44) | per-jet SM and LM geometry from primary sources, linter-checked | not reported | all 44 jets treated as one article; CM jets owed |
| fault injection (#47) | onset as a step change on the moved state, same tick | not reported | a ramp is a domain rule's job, not the plant's |
| structure (#51) | two tunnel hatches (CM forward, LM overhead) in `hatch_state`, so the ring seal matters only with a tunnel hatch open; undocking fires no pyro (CSM News Reference p. 88); staging also fires two ascent circuit interrupters (Grumman study guide p. 93); latches, hatch and pyro as discrete devices; after #47: `pyro_health` fail-to-fire, descent stage separates only when all five staging devices fire, jettison only when the ring charge fires, `leak_sources_g_s` summed by the leak rule | **decision** (close the tunnel before latch release) and **confounder** (tunnel versus cabin leak) | latches move instantly to the drive (1 s dwell only; actuation time unsourced); the `one` scope is recorded and acts on nothing (re-cocking a failed latch unsourced); leak with an unlatched hatch or unseated ring above 0.5 psid is a named gap (aperture, seal, tunnel volume unsourced); configuration states still flip on the event until #47; `hatch_open_with_pressure` unevaluable (prose `gated_by`) |
| ECLSS (#46, 18 of 24 states) | cabin leak per gas (bulk-flow shares); `set_o2_source` partly guarded through a general two-argument interlock condition (ADR 0004 amended; lane 7 can use it for its two verbs); suit loop on its compressor at 35 cfm, switched by `set_suit_fan` | not reported | cabin H2O waits on crew production (D-06), like CO2, since a removal-only vapour stock would dry the cabin; crew O2 uptake waits on `crew_state`, so cabin O2 still rises by the metabolic term; `o2_supply_pressure_psi` on a card to John (cryo tank sources on blocked hosts) |
| unpin (#45) | — (test figures, no model) | — | — |
| GNC + RCS | attitude as pointing modes: a rate-limited slew law behind `set_attitude_target` (D38) | not reported | 6-DOF deferred; it would replace only the law |

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
  sprint opened (D24–D31, [`records/2026-10-17-vehicle-sprint.md`](records/2026-10-17-vehicle-sprint.md)).
