# SV-022 status

**Interrupted WIP checkpoint; not accepted.** Base: accepted `630623a4af30a8d08e90f5d9b0d2ef626af20f13` (runtime `f3812dc9d351a231a0f0879f86c9807f0a6a6634`). Package: checkpoint-safe collection (K-F1 GC) with post-collection recovery and a recorder-in-loop correlation slice. No Git call is made by the worker; the coordinator checkpoints after the worker stops.

## Checkpoint 0 — design fixed, nothing active

Inputs read: `SV-022-Astra-preflight.md`, `SV-021-Astra-correction-2-review.md` (= `docs/planning-context/sv021/ASTRA-ACCEPTANCE.md`), sv021 STATUS/RECEIPT/checkpoint-002, canonical v2 1.1 (M-1…M-6), 1.3, 1.4.1–1.4.10, O2 rows, SV-013 C-G1, `SV-022-bounded-targets.json`.

Design decisions (details in RECEIPT.md once written):

1. New module `services/chassis_gc.py`: pure planner, pure intent validator, the unlink executor. Nothing else deletes.
2. Segment unlinks oldest first, each followed by `fsync(ledger/)` before the next: under M-2 only a suffix of the listed segments can survive any cut, so no internal gap is ever produced. A simulated gap is refused (A2), not reinterpreted.
3. Restart reader: a pending valid intent in P is re-validated against retained evidence and its fixed list re-run (never a fresh scan) before any startup blob write; `GC_DONE` is the first recovery-core record. A torn/damaged intent is never authority.
4. A missing segment prefix is accepted only if a retained `GC_INTENT` names the segment just below the oldest present one.
5. Activation: the restart reader is unconditional; the live collector is `Session(collect=True)`, passed only by `chassis.run`.

## Coordinator interruption checkpoint

At 2026-10-07 21:54 UTC the execution connection had aborted. Host verification found the original worker PID and resource scope absent, no Claude worker process, and no final exit receipt. No duplicate worker was launched. The coordinator preserved exact changed files and hashes outside the repository before committing this WIP.

The last saved events show mutation controls M1 (remove per-segment fence), M2 (unlink before intent) and M3 (remove blob-directory fence) tested and restored. The last completed Edit restores M3. M4 was announced but not applied. No deliberate MUTATION marker remains in the implementation at this checkpoint. Those expected negative-control failures are not a final passing suite. No test was in flight at the last saved event, and no completed-package or independent-acceptance claim is made. Final validation, correlation evidence, receipt completion and independent review remain pending.

Continuation should inspect the saved state, verify all deliberate mutations are restored, then finish the bounded work in the same native session if available. Original projects and real sessions remain untouched.
