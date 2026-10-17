# Programme status

As of **2026-10-17 13:42 UTC**, `tachyon-beep/space_chassis` `main` @ `b525b48`. Kept by the
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
| 9 | Fault injection into the step loop | [#47](https://github.com/tachyon-beep/space_chassis/pull/47) | draft (also ruled-discrete seeding for structure and comms) | #45, #46 |
| 1 | Burn down power subsystem | [#43](https://github.com/tachyon-beep/space_chassis/pull/43) | draft; per-cell fuel cells and PWR-02 pushed; standby pump *off* | #45; John's a, b, c; #47 before the PWR-02 `fault:` row |
| — | Source RCS thruster geometry | [#44](https://github.com/tachyon-beep/space_chassis/pull/44) | draft; SM and LM jets sourced; CM jets, SM offsets, minimum impulse bit owed | #45; John's CM-jet answer; allowed domains |
| 5 | Comms remainder | [#48](https://github.com/tachyon-beep/space_chassis/pull/48) | draft; occultation from the orbit; `carrier_lock` waits on #47's seeding | #45, #47; John's Earth-link delay |
| 2 | Finish thermal | [#49](https://github.com/tachyon-beep/space_chassis/pull/49) | draft; bays and pump speed advance; re-deriving MET-0 at 1,401 W; `heater_bank_duty` held | #45; the numeric-argument engine change (lane 9); John's two cards |
| 3 | Propulsion and propellant | [#50](https://github.com/tachyon-beep/space_chassis/pull/50) | draft | #45; allowed domains for primary sources |
| 4 | Structure states | — | in progress; `arm_state` waits on #47's seeding | #47 |
| 7 | GNC + RCS | — | not started | the geometry lane (#44); John's pointing-modes answer |
| 8 | Crew | — | not started | John: design item D-06 |
| 10 | Avionics FDIR | — | not started | last; needs lane 9's faults |

Engine requests queued with lane 9: ruled-discrete seeding (structure, comms; in #47); numeric
carried arguments with range refusal in `plant.command_effect` (thermal, after #45 and #46);
`resolve_interlock` accepting a coupling-node `from` (propulsion).

Cross-lane changes in flight: the standby-pump fix (D29) is power's `load_enabled` line in #43 plus
thermal's re-derived MET-0 equilibrium and service-bay G (29.6875 W/K) and C (213,750 J/K),
which thermal cherry-picks onto power's branch. Power has applied *off* on #43 (MET-0 CSM load
1,401 W).

## Waiting on John

One word each. Lanes carry on with the recommended option where they can.

| item | options (recommended first) | asked in |
|---|---|---|
| power a: bus tie (lane building *apollo*) | apollo / keep | Burn down power subsystem, 12:57 |
| power b: shed ladder (lane building *crew*) | crew / auto | same |
| power c: source converter (lane building *retire*) | retire / keep | same |
| RCS: the CM jet | keep / split / owe | Source RCS thruster geometry, 13:18 |
| comms: Earth-link delay at the window | geometric / constant / none | Comms remainder, 13:31 (card) |
| thermal: pump speed | fraction / rpm / unset (lane building *fraction*) | Finish thermal, 13:19 (card) |
| thermal: bay thermal masses | chosen / hold / out (lane building *chosen*) | same |
| the arc report's eleven decisions, including attitude as pointing modes (lane 7) and D-06 (lane 8) | in the report | Whole-vehicle arc assessment |
| allowed domains `ibiblio.org`, `ntrs.nasa.gov`, `www.nasa.gov` in the cloud environment | a setting only John can change | project chat, 13:35 |
| D22 pilot credentials for the 10-minute smoke | — | Vehicle to smoke-ready |
| archive `space_vehicle` (D21) | a repository setting; safe since PR #35 | `records/2026-10-15-space-vehicle-archive-check.md` |

Answered today: power d, standby pump, read as *off* from D29 (13:35).

## Fidelity ledger

Design for more fidelity, not less, except where it creates project risk (D31). One line per lane:
the fidelity it builds to, and any approximation it deliberately keeps. Filled from what lanes report
to the coordinator; *not reported* means the lane has not said yet.

| lane | builds to | approximations kept |
|---|---|---|
| power (#43) | Apollo EPS as flown: each fuel cell a module (AOH 2.6); building the recommended a, b, c: battery-to-main-bus tie plus fuel cell 2 cross-feed, no automatic shed ladder (cautions only, the crew sheds), source converter retired | battery derate and temperature owed (no source); pump draws carried at 250 W though WP02 found tens of watts AC |
| thermal (#49) | the loop as heat balances; bays `C dT/dt = Q − G(T − T_coolant)` | bay C and G are `chosen`, bounded by limits (ADR 0003 item 11); pump speed as a fraction of rated (no rated rpm found) |
| comms (#48) | blackout as exact sphere geometry per tick from the propagated orbit, Moon at real distance; link budget designed in full; light time `range/c`, 0.02–1.32 s, for the window to apply | ground end is Earth's centre, not MSFN stations (no station coordinates; stations would change `link_ok` in the episode, so only as a deliberate change); no link-budget constant sourced (TN D-6723 and the USB tables are behind blocked `ntrs.nasa.gov`); `carrier_lock` a discrete with a numeric acquisition timer once #47 is on `main` |
| propulsion (#50) | thrust a first-order lag to rated; chamber pressure proportional to thrust | DPS thrust and chamber pressure left as gaps (throttle-to-thrust law unsourced, `main_propulsion_diode.md:36` refuses it); feed pressure held at 100 % of nominal with no regulator or line loss; regulator lock-up, bottle blowdown and helium displacement wait on reachable sources; no start transient (none published) |
| RCS geometry (#44) | per-jet SM and LM geometry from primary sources, linter-checked | all 44 jets treated as one article; CM jets owed |
| fault injection (#47) | onset as a step change on the moved state, same tick | a ramp is a domain rule's job, not the plant's |
| ECLSS, structure, unpin | not reported | — |
| GNC + RCS | not started; the arc report recommends attitude as pointing modes until a decision needs 6-DOF | open with John; D31 bears on it |

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
