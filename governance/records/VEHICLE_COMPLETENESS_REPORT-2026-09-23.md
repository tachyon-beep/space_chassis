# Vehicle completeness — review and status

## Current update — 2026-09-23

Published vehicle main is `dd79e7608c931df9e5273824a3b2b9f396cb7cb7`; published chassis main is
`fa43b25b0fd7d88a3f5e7feb3338e190078517ce`, whose submodule pointer names that vehicle
commit. Both working trees are clean. This update supersedes every older use of "current" below;
the sections after it remain dated audit snapshots.

| Completion gate | Current result |
|---|---|
| Strict definition | **Open:** `check_vehicle.py --strict` exits 2 with 273 declared debts: 195 literal `UNCONFIGURED` scalars and 78 prose obligations. |
| Executable plant | **Open:** 52 of 139 states advance in a tick; build order is 52 ready, 27 waiting for a value, 15 for a coupling edge, and 45 for rule code. The full 192-hour mission and wall-clock budget were not revalidated in this round. |
| Window and service | Contract probe and operator-side tests passed in the full chassis suite; nominal/degraded/crisis mission acceptance was not rerun. |
| Repository split | **Met:** vehicle commits are in `tachyon-beep/space_vehicle`; chassis records only the updated submodule pointer and a separate reconciliation commit. |
| Drift gate | 344/344 vehicle referee tests passed; 6/6 chassis reconciliation tests passed; the complete 445-test chassis suite passed with four workers and local socket access. Ruff and `git diff --check` passed. |

Three source rounds corrected the post-ejection P00/active-DAP initial modes, removed an LM-3
thermal citation that could not source CSM or LM-5 bay values, and corrected the docked axial
relation to `X_A = 1422.75 - X_E`. The J-2 lateral rotation is now an explicit debt. The operator
requires measured or applicable primary-source values for missing synthetic converter and thermal
parameters; neither was filled with a guessed bound. The live research obligations and source
effectivity limits are in [the gap register](../apollo/FACT_GAP_REGISTER_2026-09-23.md).

**Historical snapshot:** commit `e85b1f2` (committed 2026-09-18 **19:52** +1000), tree clean, re-audited
2026-09-18 21:1x–21:3x AEST. **Original snapshot:** commit `2b83fe6` (2026-09-18 02:16), tree clean when
the first pass began at 03:47. **§2–§9 are the original review** of the 12 hours ending at
`2b83fe6`, annotated where the re-audit changed their conclusions; **§1 and §3 carry that snapshot's
figures**, and **§10 is the re-audit** — the eighteen rounds between the two snapshots, and what the
criteria now read.
**Concurrency caveat (original pass):** a second session was editing the folder while the first pass
ran; the corpus YAML was not touched by either session in that period, and the tree was clean again
at `e85b1f2`.
**Scope:** the vehicle seed at `docs/deep_research/vehicle/` — the far side of the window that
`space_chassis` deliberately does not contain.
**Nature of this document:** a *point-in-time snapshot*, not a declaration of record. The vehicle's
own status board is `docs/deep_research/vehicle/README.md`, and the test suite holds its figures to
the tools. Every number below was re-derived from the tools at the snapshot named; §7 carries the
commands.

---

## 0. Re-audit at vehicle `a446b1a` / chassis `997d221` — read this first

> **The figures below have since moved again, and the block is kept as the `a446b1a` snapshot.** At
> vehicle `58641b1` / chassis `0d81e32` (round 83) the tools report: **273** declared debts,
> **50 / 28 / 15 / 46** build order, **50 of 139** advancing, **107** configured, **32** with a debt,
> **195** `UNCONFIGURED` scalars, **844** `report.refuse` call sites, **336** tests. `--strict` still
> exits **2**; criteria 3 and 4 are still met and criteria 1 and 2 are still short. **The live figures
> are in `.scratch/apollo/HANDOVER-NEXT.md` §2**, which is the document a session should read.
>
> **And one operator decision is now settled:** the remaining launch positions are to be **sourced**,
> not decided — recorded in `.scratch/apollo/HANDOVER-NEXT.md` §4.4.

*Added by the cleanup round that followed round 78. §1's table below is the `e85b1f2` snapshot and is
kept as history. This block re-runs the same five criteria against the live tools; every figure was
measured at vehicle `a446b1a` / chassis `997d221`, both trees clean.*

| # | Criterion | At `e85b1f2` | **Now** | Evidence |
|---|---|---|---|---|
| 1 | `tools/check_vehicle.py --strict` exits **0** | Not met | **Still not met** | exits **2**; **276** declared debts stand (was 273) — 199 literal `UNCONFIGURED` scalars and 77 prose |
| 2 | `tools/plant.py` advances **all** states across the full 192.0 h mission at the declared tick (no gaps, conservation where declared, two-run determinism, fixed-point loops, and `--build-order`'s "ready now" agreeing with a real tick) | Partial, closer | **Partial, much closer — and one half is still vacuous** | **45 of 139** advance (was 36). **`discrete` now advances 8 of 43** (was none) — round 67's hold and round 75's `event_value` — so every integrator class the corpus names now advances at least one state. `ready == advanced` (45 = 45), held by `test_the_tick_can_read_what_the_build_order_promises`. Determinism 8/8 bit-identical. **The mission-length run mode now exists** (`plant.py --mission`: 8 phases, 192.0 h = 34,560,000 ticks at 50 Hz, `--ticks N`); `--full` refuses by cost — re-measured at `a446b1a`: **1,598 µs/tick**, so ~15.3 h of wall clock, **184×** `plant.md` §10's 8.7 µs/tick budget — and `--anyway` overrides. **Conservation is the open half:** `assert_conservation` appears in `step()`'s docstring as a *comment* and nowhere else (no function, no call), and `kind: conserve` has **zero instances** in `coupling.yaml`, so "conservation where declared" is currently vacuous — **a finding rather than a pass.** 47 states still owe a rule, **22 of them `discrete`** (the largest single class) |
| 3 | A scenario runner plays nominal/degraded/crisis through `tools/console.py`; `contract/diode_probe.py` passes with 0 failures; the ring is bounded with loss accounting; the window's `README.md` is generated; the vehicle is servable from the compose `vehicle` service | **Met** (one defect found) | **Met, and the recorded defect is fixed** | Round 66 (`4455cee`) fixed the resumed-window defect §10.4 recorded: `--scenario`/`--seed`/`--ring-slots` default to `None`, so "named nothing" is tellable from "named the default", and `check_console_flags` refuses the next flag that is its own default. Probe **re-measured at `a446b1a`: 14 passed, 0 failed, 1 skipped** — unchanged, and the skip is real (§9 check 9 has no deferring verb at this phase). Ring bounded with loss accounting; `README.md` generated; compose `vehicle` profile on `worknet` only |
| 4 | The folder moves to its own repository with history; `space_chassis` keeps a pointer plus the frozen `docs/diode-contract.md` | **Planned, not started** | **Met** | The folder **is** its own repository — `tachyon-beep/space_vehicle` — vendored into `space_chassis` as the submodule at `docs/deep_research/vehicle`. The chassis keeps the pointer, the frozen corpus (`docs/deep_research/*_diode.md`) and `docs/diode-contract.md`, and its own residue suite (`tests/test_vehicle_reconciliation.py`: 6 passed) holds the changelog row to the vehicle's tools |
| 5 | No silent drift: every README figure has a reader; no live declaration contradicts another | Mostly holding | **Holding** | **331** vehicle tests (was 316); `test_the_readme_status_matches_the_tools` pins every live README figure and the embedded `--build-order` transcript; the chassis row holds the linter's **820** `report.refuse` call sites; the test count, the debt figure and the ablation arithmetic are pinned in both directions. 29 conflicts recorded and none marked Open |

**Assessment in one sentence, now:** criterion 3 is closed and its recorded defect fixed, criterion 4
has since landed, and criterion 2 has moved from 36 to 45 states advancing while gaining the mission
clock it was missing — but **criterion 1 is still not met**, because 276 debts stand and `--strict`
still exits 2. **The vehicle is not complete**, and the distance is dominated by the 47 rule states,
22 of them `discrete`.

---

## 1. Bottom line

At `e85b1f2` the vehicle **composes, serves a window, and flies part of itself**. Of the objective's
five completion criteria:

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | `tools/check_vehicle.py --strict` exits **0** | **Not met** | exits **2**; **273** declared debts stand (was 261 — the last round found eleven defects that had been reported as zero) |
| 2 | `tools/plant.py` advances **all** states across the full 192.0 h mission at the declared tick (no gaps, conservation where declared, two-run determinism, fixed-point loops, and `--build-order`'s "ready now" agreeing with a real tick) | **Partial, closer** | **36 of 139** states advance (was 25); the classifier now *equals* the tick (`ready == advanced`, held by `test_the_tick_can_read_what_the_build_order_promises`); every computational method class now advances at least one state — `algebraic` 24, `stock` 7, `lag` 3, `delay` 1, `dynamics` 1 — and **`discrete` (43 states) advances none**; determinism 8/8 bit-identical; still no mission-length run mode, and 64 states owe a rule |
| 3 | A scenario runner plays nominal/degraded/crisis through `tools/console.py`; `contract/diode_probe.py` passes with 0 failures; the ring is bounded with loss accounting; the window's `README.md` is generated; the vehicle is servable from the compose `diode` service | **Met** (one defect found) | all five landed between `e76c1d7` and `b774e59`: `--scenario`/`--seed`/`--plan`, a bounded ring with `state.json.ring` accounting losses, a generated sixth file (`tools/generate_readme.py`), and a compose `vehicle` profile running `containers/serve_vehicle.sh` on `worknet` only. Probe reproduced at `e85b1f2`: **14 passed, 0 failed, 1 skipped**. *Defect:* `--scenario`/`--seed` are ignored on a **resumed** window (§10.4) |
| 4 | The folder moves to its own repository with history; `space_chassis` keeps a pointer plus the frozen `docs/diode-contract.md` | **Planned, not started** | a decision document exists (`.scratch/apollo/CRITERION-4-PLAN.md`) recommending "split by reach": the referee moves with the vehicle, the two reconciliation assertions stay; no move yet |
| 5 | No silent drift: every README figure has a reader; no live declaration contradicts another | **Mostly holding** | every README figure and the build-order transcript are pinned by tests; 29 conflicts recorded and **none marked Open** — C-25 and C-26 were put to the operator and resolved, as were C-27/C-28 |

**Assessment in one sentence:** in eighteen further rounds the session closed criterion 3 outright and
roughly halved the distance on criterion 2 (25 → 36 states advancing, `ready == advanced`, the
`delay` and first `dynamics` integrators landed), at the cost of an honest debt rise 261 → 273; what
remains is dominated by the 64 rule states and, for the first time, by a decision about the move.

---

## 2. The original window: what the 12 hours ending at `2b83fe6` delivered

**17 commits in 12 hours** (rounds 28–44 of the current session's numbering; mean gap **38 minutes**,
range 23–54; first at 16:15, last at 02:16), 23 files touched, 9,897 insertions / 372 deletions. All
17 subjects are `vehicle:` — **no operator-side (chassis) work happened in the window**; the tree was
clean when the last commit landed (a second session started editing after this review began — see
the caveat above).

Scale of the artefact being maintained: **27,619 lines of YAML** corpus, **20,407 lines** of tools,
a **15,140-line** round-log README and a **16,705-line** test file, 4.7 MB in total.

| commit | time | the finding | headline movement |
|---|---|---|---|
| `a611d7f` | 16:15 | the frame omitted what it could compute; the arithmetic was in the registry | 4 channels gained evaluable derivations; debts 247; tests 266→268 |
| `e70adb9` | 17:07 | twenty lags began at their driver, and nothing declared that | debts 247→**257** (10 hidden obligations declared); configured 114→109; tests 268→270 |
| `00b9fb0` | 17:45 | the frame published a node's number under the channel's unit, seven times | debts →258; frame values 26→25; tests 270→272 |
| `40f93a5` | 18:22 | the residual was the observation; eight ledger names were published by nothing | debts →259; frame values 25→23; tests 272→274 |
| `5b836dd` | 18:55 | the oxygen supply had no tank; the ECS guide has it on one page (900 psig, PDF p. 12) | debts →262; states 134→135; tests 274→275 |
| `b8a7c32` | 19:49 | a band is a claim about the values a channel reads — three were wrong | debts →261; configured 109→110; tests 275→277 |
| `70229d3` | 20:22 | three channels claimed three temperatures from one state; two were the supply | debts →262; frame values 25→28; tests 277→279 |
| `968863f` | 21:01 | the mission's clock was inside its epoch's provenance; step 7 was a comment | 50/50 determinism compare-points; tests 279→282 |
| `b1bcb64` | 21:46 | four blocks the linter holds could be deleted, and the corpus still composed | tests 282→284; verifier 21 cases |
| `095698d` | 22:15 | the coolant's return was the wrong station; a healthy loop would have tripped its warning | conflicts 27→28 (C-28); tests 284→285 |
| `1baa01e` | 22:46 | the zone's heat rate was found by node name, so four of six zones were skipped | debts →263; zones joined 2→4; tests 285→286 |
| `7bf3b23` | 23:09 | the changelog row for the linter was four figures stale | stale figures 4→0; tests 286→287 |
| `6e39b92` | 23:53 | the worklist's rule about declared arithmetic was unreachable on the sentinel | 111/136 configured; advanced 19→20; tests 287→288 |
| `38d3655` | 00:20 | the loop's collected load was a sentence, and its ingredients were all declared | states 136→138; build order 30·25·14·69; tests 288→289 |
| `205adcc` | 00:43 | the second coolant loop had no declared role; the document that answers it was already cited | states 138; refusal call sites 769→771; tests 289→290 |
| `795dbb8` | 01:22 | the coolant's specific heat was prose; the loop's own three terms derive it (TN D-6718) | c_p derived = 3,626.1 J/kg-K; conflicts 28→29 (C-29); tests 290→291 |
| `2b83fe6` | 02:16 | the radiator had no temperature, so the loop's other half could not be computed | debts **262→261**; states 139; nodes 58; edges 80; advanced 22→**25**; tests 291 |

### The shape of the work

- **Six of the seventeen rounds (095698d → 2b83fe6) are one thread: the coolant/thermal loop.** It
  began with a wrong station, found the collected load was a sentence, gave the loop a declared role,
  derived its specific heat from a published source, and ended with the radiator's own fourth-power
  law solved for temperature — so the heat balance now closes from the first tick (panel 322.06 K,
  rejection 1,723.1 W, inlet 26.06 °C, return 7.2 °C = the supply).
- **Five rounds are the frame/window's correctness** (a611d7f, e70adb9, 00b9fb0, 40f93a5, 70229d3):
  the values a fleet actually reads were wrong in unit, in source, or absent.
- **Two rounds are process/metadata repair** (b1bcb64: dead blocks the linter held; 7bf3b23: a
  changelog row four figures stale).
- **The rest are structural**: the oxygen supply tank, the band semantics, the mission clock, the
  worklist sentinel, the second loop's role.

### Was it verified?

Yes, and by more than the author's word:

- **+25 tests** in the window (266 → **291** test functions, 291 collected), each round adding the
  test that breaks a copy and asserts the linter's *own words*.
- **Every round carries a verifier** in `.scratch/rNN/` (r28…r44). I re-ran round 44's verifier at
  HEAD: **19 of 19 cases green**, including "a panel starting at its 285 K design point is refused".
- **I re-derived the last round's arithmetic independently** (round 44, the radiator): the law at
  `(2477+1723)/(0.85·σ·8.1)` gives **322.0575 K**; the corpus's own design point at 285 K gives
  **2,575.7 W**; TN D-6718's three terms give **3,626.07 J/kg-K**; the loop's inlet lands at
  **26.058 °C** and the return at the supply. All four agree with the commit's figures.
- **No frozen file was touched** in the window: `git diff --name-only 2246e3a..HEAD` contains no
  `*_diode.md`, no `docs/diode-contract.md`, and no `integration/{simulator-design,corpus-review,review-findings}.md`.

### The one number that went the wrong way, and why

The debt headline is **247 at the window's start and 261 now (+14)**. That is not a regression in
the corpus; it is the instrument getting stricter and the declarations getting more honest:

- `e70adb9` alone took 247 → 257 by declaring **ten obligations that had been invisible** (twenty
  lags silently starting at their driver) — the honest direction, but it reads as +10 in the
  headline while configured states *fell* 114 → 109.
- `5b836dd` added a real state (the oxygen supply tank) that immediately owes its time constant,
  its provenance basis and its rule: +3.
- `1baa01e` added a prose obligation for the six-zone join: +1.
- Offsetting: `b8a7c32` (−1), `6e39b92` (−1) and `2b83fe6` (−1).

**The metric that moved the right way is "states a real tick advances": 19 → 25** (of 134 → 139
states). The debt count is a shopping list, not a score — but the README should probably say so
next to the headline, because read at 12-hour intervals it looks like drift backwards.

---

## 3. Where the vehicle stands — at the original snapshot and now

| figure | 12 h before `2b83fe6` (`2246e3a`) | at `2b83fe6` | **now (`e85b1f2`)** |
|---|---|---|---|
| linter, default | COMPOSES, exit 0 | COMPOSES, exit 0 | COMPOSES, exit 0 |
| linter, `--strict` | exit 2 | exit 2 | exit 2 |
| declared debts | 247 | 261 (112 scalars + 149 prose) | **273** |
| notes (not debts) | — | 36 | 36 |
| channels / edges / chains / phases | 148 / 79 / 15 / 8 | 148 / 80 / 15 / 8 | 148 / 80 / 15 / 8 |
| states / nodes | 134 / 57 | 139 / 58 | 139 / 58 |
| states fully configured | 114 / 134 (85.1 %) | 114 / 139 (82.0 %) | 114 / 139 (82.0 %) |
| states a real tick advances | 19 / 134 (14.2 %) | 25 / 139 (18.0 %) | **36 / 139 (25.9 %)** |
| edges with a sensitivity | 68 / 79 | 69 / 80 | 69 / 80 |
| `UNCONFIGURED` scalars (plant's count) | 175 | 186 | 186 |
| build order | 27 ready · 20 value · 16 edge · 71 rule | 33 · 25 · 13 · 68 | **36 · 23 · 16 · 64** |
| derived channels with an evaluable derivation | 9 (before round 28) | 15 of 71 | 15 of 71 |
| frame values (t=0) | 16 (before round 29) | 28 | **39** |
| recorded numeric conflicts | 26 | 29 (C-25, C-26 open) | 29 (**none open**; C-25…C-28 resolved) |
| vehicle tests | 266 | 291 | **316** |
| linter refusal call sites (`report.refuse`) | 748 (row claimed 661) | 772 | **790** |
| determinism (8 ticks) | — | 8 / 8 identical | 8 / 8 identical |
| integrator classes implemented | lag, stock | lag, stock | **lag, stock, delay, algebraic, + one `dynamics`** |

Where the corpus now says it stops, in its own words:

- `plant.py --readiness`: *"80 states over 58 nodes, then the 59 on the `internal` sentinel"*;
  *"25 of 139 states advanced, 114 could not — of the 114, 37 are the debt and 77 are states that
  read one."*
- `plant.py --build-order`: *"33 ready now · 25 owes a value · 13 owes an edge · 68 owes a rule."*
- the linter: *"148 channels, 80 edges, 15 failure chains, 8 mission phases. COMPOSES, with 261
  declared debt(s)."*

---

## 4. What was still outstanding at `2b83fe6` (superseded by §10.5)

### 4.1 The four buckets (`plant.py --build-order`)

| bucket | count | what it means |
|---|---|---|
| **owes a rule** | **68 (49 %)** | `algebraic`, `discrete`, `dynamics`, `hazard` — **domain code the configuration deliberately does not carry**. This is the single largest block between here and criterion 1. `plant.md` §3's four rule classes are where the law for each is written. |
| **owes a value** | 25 (18 %) | the cheapest class: a number with a named owner (`source_converter_v` needs `tau_s`, `pressurant_he_kg` needs `min_flow_per_s`, two thermal zones need `initial` and `lumped_mass_kg`, …). |
| **owes an edge** | 13 (9 %) | a coupling with no sensitivity or a state nothing drives (`imu_platform`, `prop_main_kg`, `thrust_main_n`, `attitude`, `body_rate`, …). |
| **ready now** | 33 (24 %) | of which **25 actually advance** in a real tick. The gap is stated in the README's own status paragraph and is precisely the objective's second completion criterion; the classification-vs-`advance` disagreements are separately documented and pinned by `test_the_build_order_and_advance_disagree_only_the_two_documented_ways`. |

### 4.2 Where the debts live (261 owed, by owner)

`domains/rcs` 38 · `coupling.yaml` 30 · `domains/gnc` 22 · `domains/comms` 19 ·
`domains/consumables` 18 · `domains/structure` 16 · `domains/thermal` 16 · `domains/avionics` 14 ·
`domains/eclss` 14 · `domains/power` 12 · `domains/crew` 10 · `vehicle.yaml` 10 · `mission.yaml` 9 ·
`channels.yaml` 8 · `domains/propulsion` 7 · `presentation.yaml` 5.

The graph itself (`coupling.yaml`) is the second-largest owner: 30 owed edges/sensitivities, which
is what "owes an edge" and much of "owes a rule" resolve to.

### 4.3 The declared queue (`.scratch/apollo/SOURCES.md` §0.40.1, in order)

1. **The rule layer — 68 states.** Group them by shared rule, not one at a time; the cheapest first
   are the `algebraic` states whose inputs all exist (`bus_a_load_w`, `feed_pressure`,
   `propellant_estimate`, `attitude_error`, `authority_margin`, `cabin_dp_psi`, `structural_leak_g_s`,
   `radar`, `pulse_width`, `sample_age`, `clock_offset`).
2. **The environment as a function of attitude** — `radiator_model.environment.lunar_ir_w_m2` and
   `albedo_load_w` are `UNCONFIGURED`, so `environment_heat_w` is permanently the bad-attitude case,
   and F-13's cold/hot-panel chain is unreachable by attitude.
3. **C-29's heat fraction** — the electrical demand (1,723 W) against the heat-rejection requirement
   (1,421.4 W): a per-load heat fraction or a lunar peak-load figure (302 W unexplained).
4. **The AOH SECS scans** (`.scratch/apollo/aoh_secs.pdf`, 53 pages, no usable text layer) — the last
   unread candidate for a fluid-property table; every other candidate has been ruled out.
5. **The shallow staged merge** (`_advance_into`): values["internal"] gains at most one computed
   sentinel state per tick because the staged sub-map is replaced rather than merged.
6. **§0.27 the ledger accumulator + residual** (8 channels).
7. **§0.25.2 two owed starting values** (bay temperatures — NASA CR `LM0-510-1036` to fetch; the
   pump's rated speed).
8. **The template-instantiation decision** (~17 keyed-state projection channels; placeholders as an
   enumeration rather than a regex).
9. **The `relation` audit** — every `derived` provenance whose `relation` no tool re-derives.
10. **C-25 and C-26** — ask the user.

### 4.4 The criterion-3 gap, item by item

| requirement | state |
|---|---|
| console loop against the window | **exists** (`tools/console.py`), writes `state.json`, `HELP.md`, one result file per refusal |
| `contract/diode_probe.py` passes with 0 failures | **verified in this review: 14 passed, 0 failed, 1 skipped** against a live `console.py` — exactly the figure `presentation.yaml` claims, and the skip (check 9) is honest: no deferring verb is reachable at this phase |
| nominal / degraded / crisis through the console | **missing**: `console.py` has no `--posture`, `--seed` or fault input; `tools/faults.py` schedules 128 faults but nothing feeds them to the console (`state.json`'s `posture` is emitted empty) |
| ring bounded with loss accounting | **missing**: `presentation.yaml#ring` declares cadence classes and the membership rule, and explicitly says the slot count is the far side's; no tool bounds anything or accounts for loss |
| the window's `README.md` generated | **missing**: the window directory carries `state.json`, `HELP.md`, `pending.json`, `console.json`, `telemetry/`, `output/` — no `README.md` |
| vehicle servable from compose's `diode` service | **missing**: `docker-compose.yml`'s `diode` service still runs `/opt/diode/diode.py` (the contract fixture); the vehicle has no equivalent entrypoint and no Dockerfile |

### 4.5 Decisions that need a human

- **C-25 — the cabin's water-vapour share.** `csm_ecs_study_guide.pdf` p. 31 (50 °F dew point →
  9.209 mmHg) versus the LM ECS document p. 44 (0.0276 lb H₂O/lb O₂ → 12.09–12.68 mmHg). Moving it
  moves `eclss.pp_o2_mmhg`'s band, the LM's two ppO₂ thresholds, the four-gas closure and both
  channels' ranges. Which does the cabin fly at, and do the two compartments get separate shares?
- **C-26 — the RCS engine's specific impulse.** The study guide p. 90 says 275 s ("approx") and its
  own flow rates corroborate 277.9 s; `domains/rcs/components.yaml` declares 290 s, which is 4.3 %
  off the published flow rate.
- **Smaller recorded decisions**: which CSM station each crew member occupies (the corpus names three
  stations and never says who sits where); what the LM's cabin pressure control actually is
  (regulator / relief valve / continuous bleed); whether crew speech is a channel at all (D-07); how
  the P1 load ladder is expressed (a fifth threshold or a four-rung enum).

---

## 5. Assessment

*(Written at `2b83fe6`; the risk list below is superseded by §10 — criterion 3 has since landed, the
two-session collision did not recur, and the ready-vs-advance gap it names is now closed.)*

### What is working

- **The process is real, and it is the strongest thing here.** Every round: fix the corpus, add the
  refusal, add the test that breaks a copy, move the pins, write the README section, verify against
  broken copies in `.scratch/rNN/`, commit one finding per commit. 170 `vehicle:` commits have run
  this loop; the window's 17 all carry a verifier and a measured "figures" paragraph.
- **The corpus is the source of truth, not the prose.** Values are `historical` (with document *and*
  page), `derived` (with a relation the tools re-evaluate), `chosen` (with a reason), or
  `UNCONFIGURED` with a named owner — never a plausible number. I checked the window's two most
  load-bearing numbers and both re-derive exactly.
- **The instruments catch the author.** The radiator round was *found* by a test the earlier rounds
  had written (`test_no_published_frame_value_sits_outside_its_channel_s_band`), and the specific-heat
  round was *found* by the debt sentence the linter holds. That is the machinery working as designed.
- **Honest self-reporting.** The commits record their own mistakes (a blanket pin replacement that
  cost a suite cycle; a classifier that promised agreement and then disagreed 36 times).

### What is at risk

- **The headline metric reads as regression.** Over 12 hours: debts 247 → 261, configured share
  85.1 % → 82.0 %. The *real* progress (advanced 19 → 25; five new states; an evaluable derivation
  count up; a whole thermal loop closed) is invisible in the two figures a casual reader sees first.
  The README states both, but the direction of travel deserves a sentence beside the headline.
- **The remaining work is dominated by a different kind of task.** 68 of 139 states owe *rule*
  implementation — domain code, not data. The window's rate (about one state advancing per two
  hours) was achieved mostly in the cheap classes; the rule layer is the expensive one, and no
  estimate exists for it. Criterion 2 (all 139 states advancing across 192 h) is the long pole, not
  criterion 1.
- **The ready-vs-advance gap is pinned, not closed.** `--build-order` says 33 ready; a real tick
  advances 25, and the README's status paragraph states both figures against the objective's own
  wording. The disagreement *classes* (the worklist counting more than `advance` needs; the
  `internal` sentinel; a third class now at zero) are documented in
  `test_the_build_order_and_advance_disagree_only_the_two_documented_ways` — honest, but criterion 2
  asks the two to agree, so this remains outstanding work rather than a solved problem.
- **Criterion 3 has not been started in earnest.** Console, probe and fixture exist; the scenario
  runner, ring bounding/loss accounting, generated window README and a servable diode are all
  absent, and they are a different discipline (serving, I/O, bandwidth) from corpus completion.
- **The effort is now two sessions on one folder, without a claim protocol between them.** While
  this review ran, a second session began editing the same five files (observed 03:56–03:59,
  uncommitted). The folder's own handover treats this as a trap to check for, not as a workflow —
  there is no lock, no claim and no round-number coordination between them, and two rounds
  interleaving on `README.md`/`plant.py` is how pins drift. Two of the five criteria (4, and much of
  3) are not corpus work at all and will need to be scheduled deliberately rather than absorbed into
  the round loop.

### Findings from the original review — status at `e85b1f2`

1. **The vehicle README's diode block cannot be run as written.** ✅ **Fixed.** The README now reads
   `python3 ../../../contract/diode_probe.py …` with a paragraph explaining that the probe is one
   level out of the folder, plus the repo-root form. (This review's first finding, and the smallest.)
2. **The debt headline has no trend context.** ✅ **Addressed.** The README carries a section,
   *"The debt count was missing eleven of its own debts"*, that explains the round-65 rise; the
   headline is now 273 with the reason stated.
3. **`plant.py --frame` emits one frame (t=0)**; the post-tick value count is only observable through
   the test suite. ⚠️ **Still true** — `--frame` prints 39 values at t=0 and the post-tick count is
   still a test-side measurement.
4. **NEW (this re-audit): `--scenario`/`--seed` are ignored on a resumed window** — see §10.4.

---

## 6. Verification performed for this report

| check | result |
|---|---|
| `python3 tools/check_vehicle.py` | COMPOSES, 261 debts, **exit 0** |
| `python3 tools/check_vehicle.py --strict` | **exit 2** |
| `python3 tools/plant.py --readiness` | 139 states / 58 nodes / 80 edges; 114 configured; 69/80 sensitivities; 25 advanced |
| `python3 tools/plant.py --build-order` | 33 · 25 · 13 · 68 |
| `python3 tools/plant.py --determinism --ticks 8` | 8 of 8 compare-points identical |
| `.scratch/r44/verify_radiator.py` (round 44's verifier, re-run at HEAD) | **19 of 19 green** |
| independent arithmetic re-derivation (radiator, c_p, loop) | agrees to the published figures |
| `python3 -m pytest -q --ignore=tests/test_vehicle_config.py` | **89 passed** (operator side intact) |
| `python3 -m pytest tests/test_vehicle_config.py` in two halves (291 tests) | **291/291 green** — 152/152 and 139/139, no failures |
| `tools/console.py --cycles 0 --poll 0.2` + `contract/diode_probe.py --poll-seconds 2` | **14 passed, 0 failed, 1 skipped** (the probe must be run *while the console is live*; run after the console exits it reports 8 failures that are an artefact of a dead window, not a defect) |
| scope boundary: vehicle tools' imports / operator-side references | clean — vehicle tools import stdlib + `yaml` only, nothing in `services/`, `tasks/`, `endurance/` or `contract/` references `deep_research` |
| `uvx ruff check . --no-cache` | All checks passed |
| `git diff --name-only 2246e3a..HEAD` vs the frozen corpus | no frozen file touched |
| baseline extraction at `2246e3a` for the before/after table | `git archive` into `.scratch/status/base`, gates re-run there |
| concurrent-session check | `git status --short` at 03:47 clean; at 04:06 five files modified by another session (none by this review) |

---

## 7. Reproducing every figure

```sh
cd /home/john/space_chassis/docs/deep_research/vehicle
python3 tools/check_vehicle.py | tail -2                     # channels, edges, chains, phases, debts
python3 tools/check_vehicle.py --strict; echo $?              # 2
python3 tools/check_vehicle.py --debts                        # 261 owed + 36 notes, grouped
python3 tools/plant.py --readiness                            # states, nodes, configured, sensitivities, scalars
python3 tools/plant.py --build-order                          # the four buckets
python3 tools/plant.py --frame                                # the t=0 frame (28 values)
python3 tools/plant.py --determinism --ticks 8                # bit-identity
python3 tools/plant.py --state                                # the mirror + capability snapshot
python3 tools/faults.py --seed 20260912 --posture crisis      # the crisis schedule (128 faults)
python3 tools/faults.py --seed 20260912 --posture degraded

cd /home/john/space_chassis
python3 -m pytest tests/test_vehicle_config.py -q             # 291 tests, both halves
python3 -m pytest -q --ignore=tests/test_vehicle_config.py    # 89 operator-side tests
UV_CACHE_DIR=/tmp/uvcache UV_TOOL_DIR=/tmp/uvtools uvx ruff check . --no-cache

# the window's diff and its safety property
git log --since='12 hours ago' --pretty=format:'%h %ad %s' --date=format:'%H:%M'
git diff --name-only 2246e3a..HEAD | grep -E '_diode\.md|diode-contract\.md' || echo "no frozen file touched"
```

## 8. What I would do next (as written at `2b83fe6`; superseded by §10.5–§10.6)

1. **Keep the round loop exactly as it is, and spend the next window on the rule layer (68 states),
   in groups that share one rule.** It is the largest block before criterion 1 and the only class
   that is *code* rather than data; the handover's own advice — start with the `algebraic` states
   whose inputs already exist — is the right first group. *(Done in part: 68 → 64, and the whole
   computational layer now advances at least one state.)*
2. **Give criterion 3 its own budget, deliberately.** Scenario runner (posture/seed input to
   `console.py`), ring bound + loss accounting, generated window `README.md`, and a servable diode
   entrypoint. *(✅ All four landed between `e76c1d7` and `b774e59`.)*
3. **Decide criterion 4's shape early.** The folder "moves wholesale with history", but
   `tests/test_vehicle_config.py` (16,705 lines, 291 tests — the gate that runs every refusal) lives
   at the *repo root* and cannot move with it unchanged; the split needs a plan for where the gate
   lives and how `space_chassis` keeps running it, or the move will silently drop the only thing that
   proves the vehicle composes. *(✅ Plan written — `.scratch/apollo/CRITERION-4-PLAN.md`, option A;
   the decision is now the operator's.)*
4. **Put C-25 and C-26 in front of a human at the next pause.** *(✅ Both were put to the operator and
   resolved: the ECS water-vapour share kept, the RCS Isp moved to the guide's 277.8 s.)*
5. **Add the direction of travel beside the debt headline.** *(✅ The README now carries
   "The debt count was missing eleven of its own debts".)*
6. **Fix the README's diode command block.** *(✅ Fixed.)*

---

## 9. Per-subsystem completeness at `2b83fe6` (superseded by §10.3)

Read at commit `4598164` (round 45, one round past the snapshot; its headline totals — 261 debts,
114/139 configured, 69/80 sensitivities — are unchanged from `2b83fe6`). Generated by
`.scratch/status/per_domain.py`, which reads `plant.load_world`, `build_order`, a real first tick and
`check_vehicle.py --debts` rather than any prose.

**Execution view** — what a tick can do with each subsystem today:

| subsystem | states | configured | advances now | ready | owes value | owes edge | owes rule |
|---|---|---|---|---|---|---|---|
| **thermal** | 24 | 19 | **15** | 15 | 5 | 2 | 2 |
| **eclss** | 17 | 16 | **6** | 8 | 1 | 4 | 4 |
| **power** | 13 | 9 | 2 | 2 | 4 | 1 | 6 |
| **consumables** | 10 | 9 | 2 | 8 | 1 | 1 | 0 |
| **crew** | 7 | 4 | 0 | 0 | 3 | 0 | 4 |
| **avionics** | 13 | 12 | 0 | 0 | 1 | 1 | **11** |
| **gnc** | 12 | 10 | 0 | 0 | 2 | 3 | 7 |
| **rcs** | 13 | 10 | 0 | 0 | 3 | 0 | 10 |
| **propulsion** | 10 | 8 | 0 | 0 | 2 | 1 | 7 |
| **comms** | 10 | 7 | 0 | 0 | 3 | 0 | 7 |
| **structure** | 10 | **10** | 0 | 0 | 0 | 0 | **10** |
| **all eleven** | 139 | 114 | 25 | 33 | 25 | 13 | 68 |

**Declaration view** — how much each subsystem has written down:

| subsystem | debts owed | of which unset scalars | notes | edges (declared) | thresholds | verbs (declined) | faults | points (withheld) |
|---|---|---|---|---|---|---|---|---|
| **eclss** | 14 | 9 | 1 | 11 (11) | 20 | 6 (2) | 21 | 16 (3) |
| **thermal** | 16 | 12 | 2 | 19 (14) | 17 | 5 (2) | 11 | 15 (3) |
| **power** | 12 | 6 | 1 | 17 (15) | 17 | 5 (2) | 12 | 11 (3) |
| **consumables** | 18 | 8 | 1 | 5 (4) | 16 | 3 (0) | 11 | 11 (3) |
| **crew** | 10 | 4 | 4 | 2 (2) | 9 | 4 (2) | 7 | 10 (3) |
| **avionics** | 14 | 6 | 1 | 4 (3) | 13 | 4 (3) | 11 | 14 (4) |
| **gnc** | 22 | 10 | 1 | 7 (6) | 9 | 5 (4) | 11 | 16 (4) |
| **rcs** | **38** | 17 | 1 | 4 (4) | 11 | 9 (**12**) | 11 | 17 (5) |
| **propulsion** | 7 | **7** | 1 | 3 (3) | 12 | 6 (3) | 11 | 12 (3) |
| **comms** | 19 | 11 | 1 | 5 (4) | 9 | 5 (3) | 11 | 10 (4) |
| **structure** | 16 | 12 | 1 | 1 (1) | 9 | 6 (2) | 11 | 10 (3) |

*Edges are assigned to the domain of their target node; 2 of the 80 do not resolve to a domain and
are excluded, which is why the column sums to 78 (67 declared) against the global 69/80.*

**The top-level files** are the graph and the profile, not a subsystem — and the graph is the single
largest owner of obligations:

| file | owed debts | unset scalars | notes | what it owes |
|---|---|---|---|---|
| `coupling.yaml` | **30** | 0 | 11 | edge sensitivities and missing laws: every thermal time constant and conductance, the transport and plate edges, the throttle law, the inertia tensor, the crisis gains, the source resistance, the radiator's second edge |
| `vehicle.yaml` | 10 | 0 | 7 | the environment's lunar terms (`lunar_ir_w_m2`, `albedo_load_w`), configuration 4's mass properties, two RCS minimum-impulse bits, antenna 3's gain and beamwidth, the secondary loop's role |
| `mission.yaml` | 9 | 0 | 1 | the initial state vector and parking orbit, the entry corridor, three burn durations, the crew-to-station mapping, the posture guards' thresholds |
| `channels.yaml` | 8 | 0 | 0 | registry-level decisions: the 58 `range` assignments, template instantiation, precision confirmation, the `origin` field, crew speech |
| `presentation.yaml` | 5 | 0 | 1 | the ring's slot count and burst window, two mirror keys, the `available_commands` algorithm, the `not_published` registry |

### What the per-subsystem view shows

- **Configured ≠ executable.** `structure` is **10 of 10 configured and 0 advancing**: every one of
  its states owes a *rule* (separation, configuration, descent stage, arm, pyro, hatch, latches,
  relief valve, plus `cabin_dp_psi` and `structural_leak_g_s`). `avionics` is 12 of 13 configured
  and 0 advancing, with 11 of 13 owing a rule — and only 6 unset scalars, so its debt is *code, not
  numbers*. `consumables` is the opposite: 9 of 10 configured and only 2 advancing, because its
  stocks are drained by edges whose drivers are elsewhere — the "77 states that read one" class.
- **Two subsystems carry the executable half**: thermal (15 of 24 advance) and eclss (6 of 17) are
  where the last twelve hours went, and they are the only domains with a working tick.
- **The mode machines are the frontier.** The 68 rule states concentrate in avionics (11), rcs (10),
  structure (10), gnc (7), propulsion (7), comms (7), power (6) — precisely the domains whose states
  are discrete machines and computed conclusions rather than lags and stocks.
- **`rcs` is the heaviest single subsystem**: 38 debts (17 unset scalars — the most of any domain),
  12 declined verbs (the most), 10 rule states and no advancing state. C-26 (the engine's specific
  impulse) sits here, and it gates the mass-flow chain the whole domain rests on.
- **`coupling.yaml` alone owes 30** — more than any domain. The wiring is now the bottleneck for
  "owes an edge" and much of "owes a rule", which is why the handover's next unit of work is the
  rule layer with the graph's sensitivities as its companion.

---

## 10. Re-audit at `e85b1f2` — eighteen rounds after the snapshot

### 10.1 The eighteen rounds

Between `4598164` (04:16) and `e85b1f2` (19:52) the session landed eighteen commits — 15.6 hours, a
mean gap of **55 minutes**. Seven are criterion-2 work, four are criterion 3, and the rest are corpus
repair:

| commit | time | the finding | what moved |
|---|---|---|---|
| `4598164` | 04:16 | a state's rule the plant computed and the linter never evaluated | linter now evaluates it; tests 292 |
| `1ab53c1` | 04:56 | three files stated three sizes for one schedule, and no two agreed | 4 stated counts now agree with the derived schedule; tests 293 |
| `5366342` | 08:21 | the lag integrator ignored the conversion its own edge declared | advanced 25 → **28**; **C-25 and C-26 resolved**; tests 297 |
| `aff9150` | 08:48 | the seventh integrator class had no implementation at all | `delay` implemented; advanced → 29; tests 298 |
| `b58b410` | 09:24 | two states whose relation was a sentence, and one was a citation | advanced → 31; build order 40·25·12·62; tests 300 |
| `7276743` | 09:40 | the cell's output is the load, read the other way | advanced → 32; tests 301 |
| `9d19a2b` | 10:11 | the plant integrates its first dynamics state, and it is not the 6-DOF one | advanced → 33; tests 302 |
| `e76c1d7` | 10:38 | a run can say which scenario it is | **criterion 3**: `--scenario`, `--seed`, `--plan`; tests 304 |
| `078054f` | 11:04 | the telemetry ring was unbounded, and had nothing to account for | **criterion 3**: bounded ring + loss accounting; tests 305 |
| `20ada0f` | 11:35 | the window's sixth file, generated | **criterion 3**: `tools/generate_readme.py`; tests 306 |
| `b774e59` | 12:08 | the window was a slot, and nobody had filled it | **criterion 3**: compose `vehicle` profile + `serve_vehicle.sh`; tests 307 |
| `f0b4ab6` | 12:54 | two states computed a coefficient where their unit declared a rate | unit/quantity repair; tests 309 |
| `2effa45` | 13:18 | the worklist was a second classifier, and it promised two states no tick reached | **`ready == advanced`**, held by `test_the_tick_can_read_what_the_build_order_promises`; tests 309 |
| `751090d` | 14:21 | the command path wrote a keyed state into its siblings' slots | advanced 36; refusal sites 784; tests 311 |
| `58170f2` | 15:23 | two crew members could share an id, and the vehicle held where only one was | debts 261 → 260; tests 312 |
| `33a93a9` | 16:01 | three sentences about the value map said twelve, forty-eight and eleven of twelve | docstring/claim repair; tests 313 |
| `e64df52` | 16:51 | the check that counts the channels carried its own copy, and the copy was stale | refusal sites 790; tests 314 |
| `cc76e36` | 18:17 | the worklist blamed the wrong state, and sent an implementer to write a rule that would not help | tests 315 |
| `e85b1f2` | 19:52 | thirteen edges multiply by a number that does not exist | debts 260 → **273**; tests 316 |

**How to read the debt rise.** The window's debt count went 261 → 273, and the last round is the
reason: thirteen edges multiplied by an undeclared number that had been *reported as zero* — eleven
defects that were always there and were invisible. Of the whole set, the round's own words are the
right summary: "this is the first round in five that *increased* the debt count, which is the honest
direction." Meanwhile the executable half grew 25 → 36 states, so the two measures moved in opposite
directions for the right reasons.

### 10.2 The criteria, re-read

| # | at `2b83fe6` | at `e85b1f2` |
|---|---|---|
| 1 `--strict` exit 0 | no (261 debts) | **no** (273 debts) |
| 2 all states advance over 192 h | 25/139; ready 33 ≠ advanced 25; four rule classes unimplemented | **36/139; `ready == advanced`; every computational method class advances at least one state; `discrete` (43 states) advances none; no mission-length run** |
| 3 live experiment | console + probe only | **all five items landed** (scenario runner, probe, bounded ring with loss accounting, generated window `README.md`, compose `vehicle` service on `worknet`), with one defect found below |
| 4 own repository | not started | **planned** — `.scratch/apollo/CRITERION-4-PLAN.md`, recommendation "split by reach" |
| 5 no silent drift | 29 conflicts, 2 open | 29 conflicts, **none open**; every README figure pinned; the linter's changelog row holds 790 call sites and its own test count |

### 10.3 Per-subsystem now (execution view at `e85b1f2`)

| subsystem | states | configured | advances now | ready | owes value | owes edge | owes rule | debts owed (unset scalars) |
|---|---|---|---|---|---|---|---|---|
| **thermal** | 24 | 19 | **16** | 16 | 5 | 1 | 2 | 16 (12) |
| **eclss** | 17 | 16 | **8** | 8 | 1 | 6 | 2 | 14 (9) |
| **consumables** | 10 | 9 | **5** | 5 | 1 | 3 | 1 | 18 (8) |
| **power** | 13 | 9 | **4** | 4 | 4 | 1 | 4 | 12 (6) |
| **rcs** | 13 | 10 | **1** | 1 | 3 | 0 | 9 | **38 (17)** |
| **propulsion** | 10 | 8 | **1** | 1 | 2 | 1 | 6 | 7 (7) |
| **structure** | 10 | **10** | **1** | 1 | 0 | 0 | 9 | 16 (12) |
| **crew** | 7 | 4 | 0 | 0 | 1 | 0 | 6 | 11 (4) |
| **avionics** | 13 | 12 | 0 | 0 | 1 | 1 | **11** | 14 (6) |
| **gnc** | 12 | 10 | 0 | 0 | 2 | 3 | 7 | 22 (10) |
| **comms** | 10 | 7 | 0 | 0 | 3 | 0 | 7 | 19 (11) |
| **all eleven** | 139 | 114 | 36 | 36 | 23 | 16 | 64 | 273 (112) |

Movement since §9: thermal +1, eclss +2, consumables +3, power +2, and three subsystems advanced
their first state (rcs, propulsion, structure). **The subsystems that advance nothing fell from
seven to four** — `avionics`, `crew`, `gnc` and `comms` — and `structure`, which was 10 of 10
configured and advancing nothing, now advances one.
The advances break down by method as: `algebraic` 24, `stock` 7, `lag` 3, `delay` 1, `dynamics` 1,
and **`discrete` 0 of 43** — the mode machines are now the whole of the executable gap.

Top-level files at `e85b1f2`: `coupling.yaml` **42** owed (was 30 — the round-65 finding),
`vehicle.yaml` 10, `mission.yaml` 8, `channels.yaml` 8, `presentation.yaml` 5.

### 10.4 A defect this re-audit found: the scenario flag is ignored on a resumed window

`tools/console.py` records the run's identity as a scenario/seed pair, and its own comment states the
intended semantics:

> *"A resumed console keeps its scenario unless the caller names another."* (`console.py:309`)

The implementation restores unconditionally, so **a caller who names another is ignored, silently**.
Reproduced at `e85b1f2`:

```
# fresh window, first run
python3 tools/console.py --diode-dir .scratch/dv3 --slug vehicle --cycles 2 --scenario degraded --seed 7
  → [console] … scenario=degraded seed=7 ; state.json.vehicle.scenario == "degraded"

# same window, asking for a different scenario and seed
python3 tools/console.py --diode-dir .scratch/dv3 --slug vehicle --cycles 2 --scenario crisis --seed 9
  → [console] … scenario=degraded seed=7     ← the request was dropped
    exit 0 ; state.json.vehicle.scenario == "degraded"
```

**Why it matters.** Criterion 3 asks for a runner that plays nominal, degraded and crisis. Today a
window's scenario can only be changed by deleting it, and a caller who believes they have switched
to `crisis` gets a `degraded` run recorded as `degraded` — the *record* stays truthful, but the
*request* is discarded without an error. The console's own failure-mode doctrine ("a name nothing
resolves reads exactly like a name that did nothing", from the same feature's test) is what this
breaks one step over.

**Why the suite misses it.** `test_a_run_can_say_which_scenario_it_is` covers three cases — a fresh
run with flags, a restart *without* flags (keeps the pair), and an unknown scenario (refused) — and
the "caller names another" case is the one it does not cover. A fix needs the CLI to distinguish
"caller named nothing" from "caller named the default `nominal`" (the argparse default is the
sentinel's job), and a fourth case in that test.

### 10.5 What is outstanding now

From the session's own queue (`.scratch/apollo/SOURCES.md`, round 65):

1. **The crowded-source decision** — eleven edges across five domains read a node that publishes no
   key for what they need; the cheapest concrete option is per-node (a crew-count state on
   `crew_state`, an output-power state on `fuel_cell`), and it only pays off if the new state gets
   its own node.
2. **The rule layer — 64 states**, and the value layer — 23 states (273 declarations owed).
   *Source internal resistance* is named the highest-value single item.
3. **Three key-argument mismatches.**
4. **A dimensional check over derivations**; `crew_location`'s mover rule; the 6-DOF
   `orbital_state`; the template-instantiation decision; `E-PROP-ENG`'s backwards unit; C-29; the
   AOH SECS scans; the §0.27 ledger; the §0.25.2 owed starting values; the `relation` audit.
5. **Criterion 4 — the move**, which now has a plan.

### 10.6 The decision in front of the operator: criterion 4

`.scratch/apollo/CRITERION-4-PLAN.md` frames it: `tests/test_vehicle_config.py` (16,964 lines
/ 297 tests at the time of writing, 316 test functions now) is the gate that runs every refusal, and
it lives at the repo root because the suite is one suite — while the folder it tests is the thing
that moves. Three options are laid out; the recommendation is **A, "split by reach"**:

- the ~290 fixture-breaking tests move **with the vehicle** (the referee is already
  path-parameterised through `VEHICLE`);
- the two assertions about `docs/deep_research/integration/reconciliation/README.md` stay behind in
  a small `tests/test_vehicle_reconciliation.py`, because the linter must not read outside its own
  folder;
- `space_chassis`'s `pytest -q` must run both, or the move silently drops the only thing that proves
  the vehicle composes;
- history via `git filter-repo --path docs/deep_research/vehicle --path tests/test_vehicle_config.py`;
- the pointer left behind: a one-file `README.md` naming the new repository and split commit, with
  `docs/diode-contract.md` frozen where it is.

This is the one criterion whose cost grows if deferred: every round adds tests to a file that has to
be split.

### 10.7 Verification performed for the re-audit

All at `e85b1f2`, from a `git archive` extraction (so a concurrently-edited working tree cannot
contaminate the figures):

| check | result |
|---|---|
| `python3 tools/check_vehicle.py` | COMPOSES, **273** declared debts, exit 0 |
| `python3 tools/check_vehicle.py --strict` | **exit 2** |
| `python3 tools/plant.py --readiness` | 139 states / 58 nodes / 80 edges; 114 configured; 25 with a debt; 69/80 sensitivities; 186 unset scalars; **36 advanced**, 103 blocked (32 the debt, 71 reading one) |
| `python3 tools/plant.py --build-order` | **36 · 23 · 16 · 64** |
| `python3 tools/plant.py --determinism --ticks 8` | 8 of 8 compare-points identical |
| `python3 tools/plant.py --frame` | **39** values at t=0 |
| per-domain script (`.scratch/status/per_domain.py`) | the §10.3 tables; advances by method `algebraic` 24 · `stock` 7 · `lag` 3 · `delay` 1 · `dynamics` 1 · `discrete` 0 |
| `tools/console.py --scenario degraded …` + `contract/diode_probe.py` | **14 passed, 0 failed, 1 skipped** against a live scenario-driven console |
| window contents | six files present including a generated `README.md`; `state.json.ring = {slots: 300, held: 118, losses: 0}` |
| `docker compose --profile vehicle config -q` | parses (and `--profile diode` still parses) |
| `uvx ruff check . --no-cache` | All checks passed |
| scenario-override reproduction | **the flag is ignored on a resumed window** (§10.4) |
| `python3 -m pytest tests/test_vehicle_config.py` in halves (316 tests) | **316/316 green** — 164/164 and 152/152, no failures |
| original-review findings re-checked | README diode path **fixed**; debt-direction context **added**; `--frame` still t=0 only |
| conflicts register | 29 entries, **0 marked Open**; C-25…C-28 explicitly resolved |

### 10.8 What I would do next, now

1. **Fix the scenario-override defect (§10.4) in one round.** It is small, it is testable with a
   fourth case in an existing test, and it is the only thing standing between criterion 3 and a
   clean "met".
2. **Decide criterion 4 and start it.** Option A is recommended, and the plan's own argument is that
   this is the one criterion whose cost grows with every round — 316 test functions now against 297
   when the plan was written.
3. **Spend the rounds on `discrete`.** It is 43 of the 103 blocked states and the whole of the
   executable gap now that every other method class advances something; the mode machines share a
   handful of patterns (hysteresis, dwell, one-way arming, commanded selection) that the linter
   already refuses to let an author get wrong, so they can be landed in groups rather than one at a
   time.
4. **Take the crowded-source decision** (eleven edges, five domains) — it gates three of the stocks
   and is the cheapest structural unlock left.
5. **Keep the debt headline's direction-of-travel sentence** the README now carries; with the count
   at 273 and rising honestly, the explanation is what stops it reading as regression.

## 11. Criterion 4 executed — the vehicle is its own repository

**Done at `486a02b` (space_chassis) / `b65fef2` (vehicle), 2026-09-18 ~23:5x AEST.** Criterion 4
asked for the folder to move to its own repository with history, with `space_chassis` keeping a
pointer plus the frozen contract. The operator chose the shape: a **git submodule at the existing
path**, as a permanent fixture, so more vehicles can be added later as more submodules.

### What was created

| | |
|---|---|
| repository | **`tachyon-beep/space_vehicle`** (private, matching the chassis's visibility) |
| history | **188 commits**, split with `git subtree split -P docs/deep_research/vehicle` — the folder's own history back to `6d72b70` ("deep research: reconcile the corpus, and seed the vehicle"), byte-identical to the folder at `e85b1f2` (verified file-list *and* blob-level before the split was used) |
| mount | `docs/deep_research/vehicle` — a git submodule at the same path, so every existing doc, compose mount, `.dockerignore` entry and Dockerfile `COPY` keeps working |
| contract | `docs/diode-contract.md` stays frozen in `space_chassis`, unchanged, as the only shared interface |

### The gate went with it — split by reach (the plan's option A)

| | count | where |
|---|---|---|
| fixture-breaking referee (copies the folder, breaks one thing, asserts the linter's words) | **312** | vehicle repo, `tests/test_vehicle_config.py` |
| assertions that need this repository's files — the frozen corpus citations, `contract/diode_probe.py`, the reconciliation rows, the compose service, `.dockerignore` | **6** | `space_chassis`, `tests/test_vehicle_reconciliation.py` |
| operator-side | 89 | `space_chassis`, `tests/` (unchanged) |

`pyproject.toml`'s `testpaths` now lists both, so **`pytest -q` at the chassis root still runs one
suite of 407 tests** — a pointer is not a gate, and the move must not silently drop the only thing
that proves the vehicle composes.

### One assertion changed sides rather than moving

`test_the_presentation_references_resolve_and_the_table_is_whole` stat-ed `presentation.yaml`'s
contract and probe and `coupling.yaml`'s two corpus references against the *repository root*. That
was correct while the two halves shared a root and is a boundary violation now: the vehicle may not
open files outside its own repository. The vehicle's copy now asserts the four citations are
**named**; the new residue test asserts they **resolve** — which only the chassis side can check.
This was found by running the moved suite, not by inspection, and it is the first thing the split
taught: the boundary is only real if both sides' tests respect it.

### Verified after the swap

| check | result |
|---|---|
| linter through the mount (`docs/deep_research/vehicle/tools/check_vehicle.py`) | COMPOSES, 273 declared debts, exit 0 |
| residue suite (`tests/test_vehicle_reconciliation.py`) | **6/6** |
| the vehicle referee through the mount (312 tests, two halves) | **312/312 green** — 162/162 and 150/150, no failures |
| the chassis side (`pytest -q tests/`) | **95/95 green** (89 operator + 6 residue) |
| **a fresh clone** — `git clone` the chassis, `git submodule update --init` | **works**: registered, cloned from GitHub, checked out `b65fef2`; in the clone the linter COMPOSES, the residue suite is 6/6 and a vehicle test passes |
| collection at the chassis root | **407** (89 + 6 + 312) |
| `docker compose --profile vehicle config -q` | parses |
| ruff at the chassis root, submodule included | All checks passed |
| vehicle repo standalone | 188 commits, clean tree, referee collected at 312, remote tip = local tip = the submodule pointer |
| full suite in one process | *not run to completion*: the serial 407-test run exceeded its 40-minute cap, so it was replaced by the four runs above — the same tests, split, all green |

### Follow-ups this move leaves open

1. ~~**`space_chassis`'s own GitHub remote is empty.**~~ **Done** — pushed at `486a02b`
   (`git push -u origin main`, 2026-09-18 14:47 UTC), and verified the way that matters: a
   **clean `git clone` from GitHub** followed by `git submodule update --init` registers the
   submodule, clones `space_vehicle` from its own URL, checks out `b65fef2`, and in that clone the
   linter COMPOSES (273 debts), the residue suite is 6/6, a vehicle test passes and
   `docker compose --profile vehicle config -q` parses. Nothing was tracked that should not be:
   `.env` is gitignored, the only "env" files in the tree are the example and the operator's
   constants, and the largest blob in the history is the vehicle's ~1 MB round log.
2. **The vehicle's own CI is not set up.** The repository carries `pyproject.toml` (pytest + ruff)
   but no workflow; the natural gate is `pytest -q` plus `check_vehicle.py` (exit 0 — a debt is a
   deliverable, so `--strict` cannot be the CI gate).
3. **The next vehicle round commits in the vehicle repository now, not in the chassis.** The round
   law is unchanged (fix, refusal, test, pins, README section, verifier, one commit), but `cd` is the
   submodule and the reconciliation row is edited on the chassis side — where the residue suite
   holds it.
4. **The old `.scratch/rNN/` verifiers** were gitignored in the folder and could not ride along with
   the split; they are preserved at `space_chassis/.scratch/vehicle-verifiers/` (42 entries, r36–r58
   plus the diode dirs) and a fresh clone of the vehicle will not have them.
5. **A stray local branch `vehicle-standalone`** remains in `space_chassis` — the split's source
   branch, kept as a safety net until the vehicle repository is confirmed on a fresh clone. It can
   be deleted with `git branch -D vehicle-standalone`.

---

Originally written at `2b83fe6`, re-audited at `e85b1f2`, and extended at `486a02b`; every pass only
read, except the move recorded in §11, which is the operator's decision executed.
