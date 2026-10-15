# Programme status

As of **2026-10-15**, `tachyon-beep/space_chassis` `main` @ `{{MAIN}}`. Reconciled against the code
by the governance stream; refreshed after any merge that moves a milestone. **Verify against the code
before trusting any line here.** The stream files (`chassis/snapshot.md`, `vehicle/snapshot.md`,
`*/open.md`) hold the detail; this page is the picture.

## Where the code is

| | where | checked |
|---|---|---|
| the repository | one, three streams: `vehicle/`, `aurora/`, `governance/`; `docs/` for how it works | PR #2 merged to `main` on 2026-10-15 |
| vehicle | `vehicle/` = `space_vehicle` `{{VMAIN}}` with its history; tier 1 of `#39` included | `git log vehicle/` |
| chassis | `aurora/`; the Aurora port (plans 1–6, 8) complete; plan 7 Phase A on `vehicle-adoption`, Phase B staged on John's machine | `chassis/snapshot.md` |
| what the chassis runs | vehicle `dd79e76` through its pins; the image bakes `vehicle/` at build time | `aurora/tests/test_vehicle_reconciliation.py` |
| CI | none at the root yet (D6 decided) | `.github/` absent |
| `aurora-port`, `vehicle-adoption`, `wip/sv-recorder-opus-20261008` | `aurora-port` is merged into `main`; the other two are parked | `git branch -r` |

## The vehicle

| measure | value | tool |
|---|---|---|
| states a real tick advances | **52 / 139** | `plant.py --build-order` |
| owe a value / an edge / a rule | 27 / 15 / 45 | same |
| declared debts | **273**; `--strict` exit 2 | `check_vehicle.py` |
| `UNCONFIGURED` scalars | 195 | `plant.py --readiness` |
| faults reaching a running vehicle | 0 of 128 | WP09 not started |
| µs per tick | 3,077 (52 states, no instruments) | `plant.py --mission --ticks 500` |
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

Blocked on residual decision 1 (a session on his machine pushes them).

## What is blocked, and on whom

| item | blocked on |
|---|---|
| everything in the table above | John: residual 1 |
| Phase B's full and live gates; tier-1 adoption; Option B's qualification; `#23`'s first test | the push above, then CI (D6) and an environment that can build the image |
| branch protection | John: residual 3 |
| any paid run | John: residual 2 |
| nothing else | — |

## Decisions since the last status

2026-10-15: restrictions lifted; D1–D17 in [`decisions.md`](decisions.md). Residual decisions for
John: five, listed there.

## History

- 2026-10-14: both lanes made durable and reported; every item waiting on John (`*/records/2026-10-14-*-lane-status.md`).
- 2026-10-15: readiness review and status report in the Space Aurora project; three-stream restructure (PR #2); governance review ([`records/2026-10-15-governance-review.md`](records/2026-10-15-governance-review.md)).
