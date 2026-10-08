# SV-027 status

## Design round 0: complete, awaiting independent review. Not implemented. Not accepted.

- **Base inspected:** `a17115f89b3775ca0a34cd759be79bd1fe38c9e3`. It contains the SV026 implementation, which was under review during drafting and was subsequently accepted without runtime correction; the coordinator archived that acceptance at `e6016fc1cd5fa3d68c54f40c9c21834210231660`. This proposal modifies none of its code, tests or receipts.
- **SV025:** accepted as evidence at `1ede8a3`.
- **Obligation:** R-D, deferred by SV026 (DESIGN §4.4; RECEIPT §6; ASTRA-DESIGN-ACCEPTANCE "does not close the all-boundaries rotation obligation").
- **Files written:** only `docs/planning-context/sv027/DESIGN.md` and this file. No runtime or test file was touched.

### Proposal in one paragraph

SV-015 v2 §1.4.6 requires rotation "at a unit boundary when ≥ `SEGMENT_MAX`". That predicate is separate from §1.4.1's checkpoint threshold, and evaluating one does not evaluate the other. The SV026 sites check only the threshold: startup (`_recover`, `_start_legacy`), each adopted generation, the drop notice, file-edit adoption and both note drops. `unit_end` already has the same guards and the same checkpoint branch, plus a rotate-if-full fallback. `checkpoint` already rotates once at its end. The smallest coherent change is therefore to delete `Session.threshold_boundary` and call `unit_end()` at its seven call sites (DESIGN §3–§4, C1–C5), with docstring and comment text corrected.

At default constants this adds I/O only when the active segment already holds ≥ 16 MiB. Each closure still writes at most one checkpoint, one G2 follow-up and one header. No rotation happens inside a group or with a queue. No owner choice is needed: the change only adds rotation where §1.4.6 permits it and changes no constant or policy (DESIGN §1).

### Frozen proposal (nothing run)

- **New file `tests/test_chassis_rotation.py`: 18 nodes.**
  - R1, every closed boundary: 7.
  - R2, one closure's bounded work: 3.
  - R3, group and queue guards: 2.
  - R4, default non-full control: 1.
  - R5, new failure and crash compositions: 5.
- **Retained: 58 explicit nodes.**
  - SV026 accounting subset: 19 (SV026 acceptance now satisfied).
  - SV024 batches 2–5, verbatim: 27.
  - Notes and metadata: 5.
  - GC adoption under tiny segments: 2.
  - C-G2/O2-3 golden and placement: 4.
  - Correlation, promoted from conditional: 1.
- **Total:** 76 cases in 8 post-change commands.
- **Before the edit:** B0, a baseline of the promoted correlation node, expected to pass; and D1–D7, single-node discriminators expected to fail at behaviour assertions on the unchanged runtime.
- SV024 batch 1 is excluded: writer-level only, with no changed line.
- No existing test changes. No numeric fault cut is affected: at defaults the event trace is identical, and the cuts in the injected-segment tests are semantic or self-calibrated outside the new sites (DESIGN §7.1).

### Not claimed

There is no maximal segment-read bound and the `MAX_SEGMENT_READ` slack is not proved. The following remain open:
- the unit-size term (P1);
- the closure checkpoint/GC frames;
- a startup core into an inherited full segment;
- crash-loop accumulation (L2);
- `T_origin`;
- the true older previous-base terms;
- partial I/O.

None of the §1.4.7 inequalities, U_r/U_b, constants, generator, oracles, history limits, previous-file preservation, acknowledgement/bootstrap loss semantics or H/T/Q/pump/history policies changes (DESIGN §11).

### Inputs read (dedicated Read/Glob/Grep tools only)

- `AGENTS.md`, `CLAUDE.md`.
- SV-015 v2 §1.4.1–§1.4.10 (`sv016-context/SV-015-integrated-apparatus-closure-v2.md`).
- `docs/planning-context/sv026/` `DESIGN.md`, `ASTRA-DESIGN-ACCEPTANCE.md`, `RECEIPT.md`, `STATUS.md`.
- `sv016-context/SV-024-bounded-targets.json`, `SV-026-bounded-targets.json`.
- `services/chassis_session.py` (whole file).
- `services/chassis_persistence.py`: read bounds, `LedgerWriter`.
- `services/chassis_startup.py`: `open_session`, `_start_legacy`, `_recover`, `_finish_case`, `_consume_ack`.
- `services/chassis_gc.py`: `retained_basis`, `unauthorized_prefix`, `plan_collection`.
- `services/chassis.py`: `turn_once` end, recap fold, `run`, `_open_session`, `resume_session`, `main`.
- Tests: `test_chassis_gc.py` (harness, cut mechanisms, affected tests), `test_chassis_correlation.py`, `test_chassis_durability.py` (O2-5/SV020-01), `test_chassis_ledger.py` (rotation), `test_chassis_session.py` (C-G2, rotation), `test_chassis_accounting.py` (A6–A8, CB), `test_chassis_termination.py` (`make_run`), `test_chassis_recovery_live.py` (helpers).

### Execution log and deviations

- No shell command, test, runner, Python, install, Git operation, provider, real session, credential, raw log, original repository, account or settings action.
- **Denied action:** one `Glob` for `SV-02[4-6]*` under `/home/john/Documents/Codex/2026-10-07/task` was denied automatically. The path is outside the allowed working directories, and the session has no approval surface. It was not retried and no workaround was attempted. The needed manifests were found in the already-allowed `sv016-context` directory.
- Filigree was not used (its store previously failed read-only; no retry, init, repair or claim).

**Stopping here.** SV026 acceptance is satisfied; SV027 implementation waits for its own design review and a separate reviewed prompt.
