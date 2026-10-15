# Sequencing: the critical path and what runs beside it

As of **2026-10-15**, `main` @ `{{MAIN}}`. Decisions D3 (harden M1 and build physics in parallel),
D5 (rules in `domains/<name>/`), D6 (root CI) and D14 (the bounded episode as a milestone) shape this.
Sizes are the bands from [02-remaining-work.md](02-remaining-work.md) and are not dates.

## The critical path

```
push local work ─► Phase B + tier 1 adopted ─► #23 ─► WP08 rest ─► gate I
      │                                                               │
      └► WP02/WP03 evidence ─► WP04/WP06 rules ─► bounded episode ─► WP05, WP07, WP09, WP10 ─► WP11 (V) ─► WP12 (M) ─► WP13, gate E
```

The longest chain is **WP03 evidence → WP07 flight dynamics → WP11 → WP12**: flight dynamics has
the most unknown inputs (mass properties, jet geometry, impulse, a state vector) and the most new
code (a 6-DOF integrator class, propagation, navigation, burns, the allocator). Everything else can
finish while it is in progress, and M4 cannot start without it. Start WP03's evidence questions on
day one.

## Tranche 0: unblock (S, one session on John's machine plus one in the cloud)

| step | who | output |
|---|---|---|
| Push the local-only work (D11) | a session on John's machine, after residual 1 | `wip/vehicle/39-option-b`, `wip/vehicle/23-clock-seam`, `wip/aurora/phase-b`, the brief v5 and `.scratch` evidence under `governance/*/records/` where small |
| Root CI (D6) | governance or aurora stream | `.github/workflows/{vehicle,aurora,docs}.yml`; the first green run on `main` |
| Recreate the vehicle's issues here (D10) | governance stream | #1–#13, #19–#30, #35, #39, #40, #42 as `stream:vehicle` issues with links back |
| Housekeeping (D17) | the session on John's machine | watcher killed; `#23` committed |

## Tranche 1: land what is written (S–M, two streams in parallel)

| strand | packages | notes |
|---|---|---|
| **vehicle A: `#39` Option B, then `#23`** | the two local candidates | CI qualifies them (D8); `#23` is built on `#39`'s commit, so in that order; `#23`'s `measure_clock` run with ten windows is the first live timing |
| **aurora: Phase B and tier 1** | plan 7 Phase B rebased onto `vehicle/` at `{{VMAIN}}`; D7 | the chassis finally runs the stepping vehicle; the live vehicle checks run in an environment that can build the image |
| **vehicle B: WP02 and WP03 evidence questions** | the tables in 02 §M2 | research, in its own worktree, writing provenance into YAML and decision records; no plant code |

Exit: `main` runs the WP08-era vehicle through the chassis; `#23` merged; the first evidenced values
in `coupling.yaml`.

## Tranche 2: the first rules and the bounded episode (M–L)

| strand | packages | depends on |
|---|---|---|
| vehicle A: WP08 children `#29`, `#30`, then `#25`, `#27`, `#28`, `#26` | M1 to completion | `#23` |
| vehicle B: WP04 (electrical solve) and WP06 (thermal, consumables rules) in `domains/power/`, `domains/thermal/`, `domains/eclss/`, `domains/consumables/` | the first domain code | tranche 1's evidence for the states each rule reads |
| vehicle C: WP10 conservation on the stocks WP06 drives | small, lands with the first transfers | WP06's first stock |
| aurora: the episode driver and evaluator; `#27`/`#28` chassis deltas | scripted policies through the window; the evaluator reading `/state` | Phase B |
| governance: the coverage ledger (WP11's matrix, started early) | one row per state, phase, command, fault | — |

Exit: the **bounded quiet-coast episode** (D14): two scripted policies meet a declared objective by
different trajectories through the real executive; conservation runs on non-trivial transfers;
restart mid-episode resumes; the evaluator decides independently of receipts. Then the tranche review:
re-estimate, decide the paid pilot (residual 5).

## Tranche 3: breadth (L–XL, as many worktrees as there are evidenced domains)

| strand | packages |
|---|---|
| vehicle D: WP07 flight dynamics (the 6-DOF integrator class in the plant first, then `domains/gnc/`, `domains/rcs/` allocator, `domains/propulsion/` burns) | the long pole; its integrator class is plant work and should start as soon as WP03 has mass properties and jet geometry |
| vehicle E: WP05 protection and FDIR (`domains/power/` ladder and LCLs, `domains/avionics/` votes and debounces, `domains/structure/` arm and staging, `domains/rcs/` safety ladder) | after WP04 for power; the avionics rules after the states they vote on advance |
| vehicle F: WP09 faults and instruments (`tools/faults.py` into truth; the instrument layer; crew perception once D-06's display contract is written) | after WP08; the instrument layer is also the performance fork ([05-performance.md](05-performance.md)) |
| aurora: WP09's window checks; `#26`'s needs if any; the preflight pieces of gate E | as the vehicle lands them |

Exit: WP11, gate V.

## Tranche 4: acceptance and handoff (L)

WP12 (bounded phase-spanning runs, then the full mission, degraded and crisis cases, replay and
restart, timing), WP13 (archive, tag, chassis adoption), gate E. Operator sign-off on M and E.

## What may run in parallel, and what may not

**Parallel, in separate worktrees:** evidence research per domain; rules per domain under
`domains/<name>/` (D5); the WP08 children in `console.py`; chassis work in `aurora/`; the coverage
ledger. Eleven domains could in principle run as eleven worktrees; in practice the evidence, not the
coding, sets the pace, and four or five strands is the most that integrates cleanly.

**Serialised, because they are choke points:**

| choke point | why | rule |
|---|---|---|
| `tools/plant.py` | the scheduler, integrator classes and step loop; the 6-DOF class (WP07) and any new integrator go here | one owner at a time; a rule that needs a plant change files the plant change first as its own PR |
| `tests/test_vehicle_config.py` | one 21,000-line file every change touches | append-only sections per package; split by domain when WP11's matrix lands |
| `coupling.yaml` | 46 debts; every evidence PR edits it | small PRs, one edge group each, rebased often |
| `tools/console.py` | WP08's children all touch it | one child at a time, in dependency order |
| the reconciliation pins and the adoption commit | the chassis's catch-up | one adoption per vehicle milestone, not per PR |

**Never in parallel:** two sessions on one branch or worktree (`governance/practice.md`).

## What the governance stream does during this

Keeps `governance/status.md` reconciled after every merge that moves a milestone; keeps the coverage
ledger; re-runs the tools and refreshes [01-current-state.md](01-current-state.md) and
[03-domain-gaps.md](03-domain-gaps.md); carries decision points to John when they arise
([08-risks.md](08-risks.md)); runs the tranche reviews.
