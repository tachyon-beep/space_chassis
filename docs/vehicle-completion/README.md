# Landing the vehicle — what is left

As of **2026-10-15**, `main` @ `0036b88`, vehicle at `vehicle/` (absorbed from
`tachyon-beep/space_vehicle` `f75420c`). Written by the governance stream. Every figure here comes from
the vehicle's own tools on that commit unless it says otherwise; re-run them before relying on one.

This suite answers one question: **what has to happen, in what order, for the vehicle to be complete,
accepted and flying under the fleet.** It does not replace the vehicle's own law
(`vehicle/ROADMAP.md`, `vehicle/docs/completion.md`, `evidence.md`, `release.md`, `plant.md`); it
measures the distance to it and plans the route. The 2026-10-04 programme
(`docs/plans/2026-10-04-vehicle-to-green-programme.md`) is the prior plan; where this suite differs,
it says why.

## The answer on one page

**The executive, the window and persistence are real. The physics mostly is not.**

| | now | to be complete |
|---|---|---|
| states a real tick advances | **52 of 139** | 139 |
| states that owe a value / an edge / a rule | 27 / 15 / 45 | 0 / 0 / 0 |
| declared debts (`check_vehicle.py`) | **273** | 0 (`--strict` exit 0) |
| `UNCONFIGURED` scalars | 195 | each one evidenced or scoped out by John |
| faults that reach a running vehicle | 0 of 128 | all applicable |
| accepted physics (gate V) | none | every domain |
| plant speed | ~3,562 µs/tick at 52 states | ≤ 20 ms/tick at `m = 1` with ten windows (binding); 8.7 µs/tick replay (deferred, `governance/decisions.md` D4) |
| milestones | M1 partway; M2–M5 not started | M1–M5 |
| the chassis runs | vehicle `dd79e76` through its pins (pre-WP01) | the accepted vehicle, by exact SHA |

Four things stand between here and a flying vehicle, in this order of difficulty:

1. **Physical evidence (M2).** Most of the 27 states that owe a value, and most of the 195
   unset scalars, need a sourced physical input: time constants, lumped masses, converter impedance,
   RCS jet geometry and impulse. The evidence standard forbids plausible defaults. This is research,
   and it can block a domain indefinitely.
2. **Domain rules (M3).** 45 states owe a rule: 21 discrete state machines, 10 algebraic solves, 7
   stocks, 4 lags, 3 dynamics. Flight dynamics is the deepest hole: no orbit propagation, nothing
   drives attitude, RCS thrust is not a scalar the plant implements.
3. **Faults, instruments and accounting (M3).** No fault reaches a running vehicle until WP09; the
   instrument layer must turn truth into evidence without ever reading the fault state; conservation
   must run on non-trivial transfers.
4. **Acceptance and handoff (M4, M5).** A full 192-hour mission and its degraded and crisis cases,
   deterministic replay, restart continuity, measured timing, then the chassis adopts the accepted SHA.

M1's remaining hardening (`#23`, `#25`–`#30`, `#39` Option B) is the smallest of these and is mostly
written; its blocker was process, not engineering.

## The suite

| file | answers |
|---|---|
| [01-current-state.md](01-current-state.md) | What exists and works today, measured, and what the 2026-10-04 defects look like now |
| [02-remaining-work.md](02-remaining-work.md) | Every remaining work package, M1 to M5, with scope, acceptance and dependencies |
| [03-domain-gaps.md](03-domain-gaps.md) | Every state that does not advance, by domain, and what it owes |
| [04-integration.md](04-integration.md) | What the chassis must do to run the vehicle: Phase B, `#39`, `#23`, the contract, gate E |
| [05-performance.md](05-performance.md) | Where the time goes, the targets, and the route if live real time is missed |
| [06-verification.md](06-verification.md) | Gates D/I/V/M/E, the CI to build, and what counts as evidence |
| [07-sequencing.md](07-sequencing.md) | The critical path, what runs in parallel, worktrees, and choke points |
| [08-risks.md](08-risks.md) | Risks, assumptions, open issues, dependencies, and the decisions that will come back to John |

Decisions taken for this suite are in [`governance/decisions.md`](../../governance/decisions.md)
(2026-10-15, D3–D9, D14). The governance review that preceded it is
[`governance/records/2026-10-15-governance-review.md`](../../governance/records/2026-10-15-governance-review.md).

## How to keep it true

The figures in this suite go stale with the first rule that lands. The vehicle's README holds the
tool-checked numbers; this suite cites them. After a merge that moves a milestone, the governance
stream re-runs `vehicle/tools/plant.py --build-order` and `check_vehicle.py`, updates
[01-current-state.md](01-current-state.md) and [03-domain-gaps.md](03-domain-gaps.md), and notes the
change in `governance/status.md`.
