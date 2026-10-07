# SV-021 status

**Independently accepted after correction 2.** Runtime/tests `f3812dc9d351a231a0f0879f86c9807f0a6a6634`, reviewed documentation head `24f452a491ed7f24837990236337698478749c5d`. All ten Astra findings are closed; final review: `ASTRA-ACCEPTANCE.md`. Reported selected evidence: 511 passes across nine bounded batches, including 97 recovery checks and five real script restarts. Acceptance covers the isolated WIP package with the staged limits below.


## Correction 2

Each of the three findings has a regression written first and run alone on `06fbc40`; all four regression nodes failed there as the review's traces predict. Final tree: 511 selected passes across 9 bounded runs, no failures (RECEIPT.md §7). Map, pre-fix outcomes, the one changed assertion, new carriers/domains and GC closure notes: `checkpoint-002-astra-corrections.md`.

- SV021-08: RECOVERING sealed by a checksum over all its fields and fully validated before use (else `recovery_intent_invalid`, nothing changed); the live checked IDENTITY is reconciled with the frozen reservation (`identity_inconsistent` if lower) and carried forward as the maximum, never lowered.
- SV021-09: A14 records `RECOVERY{conversation_restored}` (the restored file's hash) before restoring it; the next start is `A9t` with memory intact; cuts converge; a real edit back after a new binding is still `A11`.
- SV021-10: LEGACY_REIMPORT records `foreign_gens`; the per-generation `foreign` mark lives in pending note state until adoption consumes it; text matching removed.

Files touched by correction 2 (relative to `06fbc40`): `services/chassis.py` (resume no longer passes `foreign_texts`), `services/chassis_replay.py`, `services/chassis_session.py`, `services/chassis_startup.py`; `tests/test_chassis_recovery_live.py`; docs `STATUS.md`, `RECEIPT.md`, `checkpoint-002-astra-corrections.md`. No Git call was made.

## Earlier: correction 1 (committed at `06fbc40e4df3287f8995bb54713ce316164b29d7`)

Reviewed head `2717d7c5f6adc40c6326142efa9a40a62e3aeced` (runtime/tests `3b145c6aea18a0fc537de9cd74fe1adc539039f6`).

Base: accepted `437b52d765269dbfb127505e27d6b8dca4ed99e6`. Foundation acceptance and its limits: `docs/planning-context/sv020/ASTRA-ACCEPTANCE.md`.

## Coordinator checkpoint (reviewed commit, preserved)

The worker completed with exit 0. Its two repository-location Git checks were denied by its CLI, and it made no commits. The coordinator used the already-authorized commit workflow after the worker stopped: runtime/tests `3b145c6aea18a0fc537de9cd74fe1adc539039f6`. No runtime/test bytes were changed by committing. R1–R9 results refer to the tested files committed there. Astra reviewed immutable objects: changes needed (SV021-01…07). No merge or deployment occurred.

## Correction 1

All seven findings fixed, each with a regression written first and run against the reviewed code: 12 regression nodes failed there as the review's traces predict. Final corrected tree: 488 selected passes across 9 bounded runs, no failures (RECEIPT.md §6). Finding → fix → regression map, pre-fix outcomes, changed assertions and new deviations: `checkpoint-001-astra-corrections.md`.

- SV021-01: durable `IDENTITY` reservation before every REQUEST_SENT; TC4 allocates above it; no valid reservation → `identity_unproven` stop before any change. Length formula removed.
- SV021-02: CK3 keeps a bound snapshot in `.prev.json` and `prev` names what that file holds; A14 restores the newest checkpoint's verified bytes.
- SV021-03: LEGACY_IMPORT carries its unadopted note as a pending generation in the same record.
- SV021-04/-05: the file's authority is the latest binding transition (checkpoint, switch, deletion, A10 adoption record), not switch-history membership.
- SV021-06: refusal and omitted-call notices are appended by the reducer as part of the records that owe them.
- SV021-07: `history()` returns a deep copy.

Files touched by correction 1 (relative to `3b145c6`): `services/chassis.py`, `services/chassis_envelope.py`, `services/chassis_persistence.py` (`install_conversation(rotate=)` and docs), `services/chassis_replay.py`, `services/chassis_session.py`, `services/chassis_startup.py`; `tests/test_chassis_adoption.py`, `tests/test_chassis_checkpoint.py`, `tests/test_chassis_notes.py`, `tests/test_chassis_recovery_live.py`, `tests/test_chassis_session.py`; docs `STATUS.md`, `RECEIPT.md`, `checkpoint-001-astra-corrections.md`. The worker made no Git call; the coordinator committed runtime/tests at `06fbc40e4df3287f8995bb54713ce316164b29d7` after exit 0, without changing their bytes.

## Activation boundary

As in the reviewed commit (RECEIPT §1–§5), plus the correction: request identity is reserved durably before each request; startup converges on every repeated start through recorded bindings without a startup checkpoint.

Staged / not claimed (unchanged): destructive GC disabled (no C-G1/O2-4, no bounded total disk); v2 1.4.7 numeric bounds unclaimed; only three acknowledgement resolutions (others, and the stops `identity_unproven`, `identity_inconsistent`, `recovery_intent_invalid`, refused without change); no recorder-side label check, provider compatibility, deployment or power-loss evidence. Process-death evidence is separate from power-loss evidence.

## Next

SV022: the separately reviewed destructive-GC/post-collection-recovery package, with a local recorder-in-loop correlation slice. Protect IDENTITY and sealed RECOVERING, per-generation foreign state, current file-binding suffix, added blob references and the exact retained C_n.prev tuple. See the final acceptance for dependencies. No merge, deployment, real-session collection or broader commissioning claim follows from this acceptance.

The worker made no push; the coordinator separately verified the authorized WIP backup at `24f452a491ed7f24837990236337698478749c5d`.
