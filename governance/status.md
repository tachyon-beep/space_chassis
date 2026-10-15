# Programme status

As of **2026-10-15**, `tachyon-beep/space_chassis` `main` @ `0036b88`. Reconciled against the code
by the governance stream; refreshed after any merge that moves a milestone. **Verify against the code
before trusting any line here.** The stream files (`chassis/snapshot.md`, `vehicle/snapshot.md`,
`*/open.md`) hold the detail; this page is the picture.

## Where the code is

| | where | checked |
|---|---|---|
| the repository | one, three streams: `vehicle/`, `aurora/`, `governance/`; `docs/` for how it works | PR #2 merged to `main` on 2026-10-15 |
| vehicle | `vehicle/` = `space_vehicle` `f75420c` with its history; tier 1 of `#39` included | `git log vehicle/` |
| chassis | `aurora/`; the Aurora port (plans 1–6, 8) complete; plan 7 Phase A on `vehicle-adoption`, Phase B staged on John's machine | `chassis/snapshot.md` |
| what the chassis runs | vehicle `dd79e76` through its pins; the image bakes `vehicle/` at build time | `aurora/tests/test_vehicle_reconciliation.py` |
| CI | root CI (D6): `.github/workflows/ci.yml` runs lint, the aurora suite and the vehicle referee on 3.12 and 3.13 on every pull request and push to `main`; `live.yml` builds and runs the smoke stack on demand | `.github/workflows/` |
| `aurora-port`, `vehicle-adoption`, `wip/sv-recorder-opus-20261008` | `aurora-port` is merged into `main`; the other two are parked | `git branch -r` |

## The vehicle

| measure | value | tool |
|---|---|---|
| states a real tick advances | **52 / 139** | `plant.py --build-order` |
| owe a value / an edge / a rule | 27 / 15 / 45 | same |
| declared debts | **273**; `--strict` exit 2 | `check_vehicle.py` |
| `UNCONFIGURED` scalars | 195 | `plant.py --readiness` |
| faults reaching a running vehicle | 0 of 128 | WP09 not started |
| µs per tick | 3,562 (52 states, no instruments) | `plant.py --mission --ticks 500` |
| M1 | WP01 closed; WP08 5 of 12 children merged; `#23` written, untested | `vehicle/open.md` |
| M2, M3, M4, M5 | not started | `vehicle/ROADMAP.md` |

The full picture and the plan: [`docs/vehicle-completion/`](../docs/vehicle-completion/README.md).

## Work that exists only on John's machine

| what | where | goes to (D11) |
|---|---|---|
| `#39` Option B | commit `7a87eb82`, branch `codex/39-take-by-rename`, no upstream | `wip/vehicle/39-option-b` |
| `#23` clock seam, candidate 3a | uncommitted worktree `/home/john/space_vehicle_worktrees/23-clock-seam` | `wip/vehicle/23-clock-seam` |
| Phase B increments P, R2c | `refs/preserve/phase-b-*` | `wip/aurora/phase-b` |
| tier-1 brief wording v5 | `.scratch/tier1-brief-draft/` | with the tier-1 adoption |
| the chassis lane's evidence | `refs/preserve/chassis-lane-evidence-2026-10-14` | `aurora/`'s records where small |

Approved (D18); waits for a session on his machine to push them.

## What is blocked, and on whom

| item | blocked on |
|---|---|
| everything in the table above | a session on John's machine (approved, D18) |
| Phase B's full and live gates; tier-1 adoption; Option B's qualification; `#23`'s first test | the push above, then CI (D6) and an environment that can build the image |
| branch protection | root CI green first (D20) |
| any paid run | the bounded episode's acceptance; then the three stages in D22 |
| nothing else | — |

## Known gaps in CI

| gap | why | closes when |
|---|---|---|
| `vehicle/tests/test_vehicle_config.py::test_a_sub_tick_effect_lands_where_a_short_tick_would_have_put_it` is deselected in `ci.yml` (not skipped in the test) | it needs more than 13 GB; a hosted runner has 16 GB shared with the other workers | the vehicle line makes it fit (D6: a smaller horizon or a streamed comparison) and the `--deselect` line is removed |
| the aurora suite is not held to zero skips | two tests skip by design (`aurora/tests/test_doc_claims.py`) | — |
| the live smoke stack is not a required check | it builds the image and proves the world, not a change | run `live.yml` by hand before any adoption merge |

## Decisions since the last status

2026-10-15: restrictions lifted; D1–D17 in [`decisions.md`](decisions.md). John answered the five residual decisions the same day: D18–D22. None is open.

## History

- 2026-10-14: both lanes made durable and reported; every item waiting on John (`*/records/2026-10-14-*-lane-status.md`).
- 2026-10-15: readiness review and status report in the Space Aurora project; three-stream restructure (PR #2); governance review ([`records/2026-10-15-governance-review.md`](records/2026-10-15-governance-review.md)).
