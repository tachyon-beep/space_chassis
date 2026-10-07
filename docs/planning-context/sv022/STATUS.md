# SV-022 status

**Independently accepted after correction 1.** Runtime/tests `53c5c44b167f73e7aefb326fdeacfdced5839835`, reviewed documentation head `f6dcea2016dd1d7f9e00a6d516fec337e04c8a97`. Both findings are closed. Final review: `ASTRA-ACCEPTANCE.md`. Final selected evidence: 563 passes across 11 bounded commands. Acceptance covers the isolated WIP implementation and stated limits; real-session collection, merge and deployment remain outside it.


**Implementation and bounded validation complete after resumption; runtime/tests at `efc6c03a9b205132f334c3b00eb95d3605e8a61c`, awaiting independent review. Not accepted.** Final tree: 557 selected passes across 11 bounded commands, no failures (RECEIPT.md §1). Base: accepted `630623a4af30a8d08e90f5d9b0d2ef626af20f13` (runtime `f3812dc9d351a231a0f0879f86c9807f0a6a6634`). Package: checkpoint-safe collection (K-F1 GC) with post-collection recovery and a recorder-in-loop correlation slice. No Git call is made by the worker; the coordinator checkpoints after the worker stops.

## Correction 1 (Astra SV022-01, SV022-02) — awaiting coordinator checkpoint and re-review

Review: `SV-022-Astra-initial-review.md` (head `6a2e504`, runtime/tests `efc6c03`): changes needed. Both findings fixed, each with regressions written first and run alone on the unmodified reviewed runtime — six nodes, all failing as traced (SV022-01's mixed trace stopped `ledger_prefix_missing`; the gate-failure node did not raise; skipping lists were accepted, executed at startup and published live). Final corrected tree: 563 selected passes across 11 bounded commands, no failures. Map, pre-fix outcomes and limits: `checkpoint-001-astra-corrections.md`.

- SV022-01: restart fsyncs the pending intent's own segment before its first unlink (`chassis_gc.sync_intent`); a failed gate is a PersistenceFailure with zero unlinks.
- SV022-02: `intent_problem` requires the segment list to cover a prefix of the surviving segments (`segment prefix`); already-removed leading items remain valid.

Files: `services/chassis_gc.py`, `services/chassis_startup.py`, `tests/test_chassis_gc.py` (harness watermark + 6 nodes; no assertion changed); docs. No Git call. SV-022 remains unaccepted.

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

## Resumed execution (worker, same native session)

- Inspected the tree at `efc6c03`: `grep MUTATION services/ tests/` empty; `unlink_intent` has the per-segment `fsync(ledger/)`, the `fsync(blobs/)` and the final `fsync(ledger/)`; `_collect` appends GC_INTENT before any unlink. (The worker's own transcript ended after M3's run, before its restore edit; the restored bytes were confirmed on disk, not assumed.)
- M4 (restart writes GC_DONE without re-running the stored list) applied, run on `…every_cut…[process-death]` — failed at cut 1 as expected (GC_DONE recorded, listed segments 1–5 survived) — and restored; `grep MUTATION` empty again.
- Final bounded validation F1–F11 on the final tree only: 557 passes, no failures. M1–M4 failures are negative-control evidence, not passes.
- RECEIPT.md written: runs, controls, source→fixture map, crash matrix, recorder-in-loop evidence, deviations, file manifest, claims and non-claims.

## Activation boundary

The restart reader (finish a pending valid intent; refuse invalid intents and unauthorized missing prefixes) is active for every start. The live collector runs only with `Session(collect=True)`, which only `chassis.run` passes, on this isolated WIP branch. All exercised deletion was in temporary test roots. No real session was collected.

## Deferred (not claimed)

Bounded total disk; v2 1.4.7 numeric bounds; power-loss/kernel/storage evidence; loss of a new segment's name during the post-collection rotation; convergence (rather than refusal) for a gap among listed segments; the remaining acknowledgement resolutions (refused); provider compatibility, deployed recorder, deployment, merge, pump/vehicle/H/T/Q.

## Files changed by SV-022 (relative to `630623a`)

New: `services/chassis_gc.py`, `tests/test_chassis_gc.py`, `tests/test_chassis_correlation.py`, `docs/planning-context/sv022/STATUS.md`, `RECEIPT.md`. Modified: `services/chassis_session.py`, `services/chassis_startup.py`, `services/chassis.py`, `services/chassis_replay.py` (docstrings), `tests/test_chassis_session.py` (one assertion; RECEIPT §4). The worker made no Git call.

## Coordinator final checkpoint

Resumed worker completed with exit 0 at 2026-10-07 22:00:33 UTC. The final runtime/test bytes equal the interrupted WIP commit `efc6c03a9b205132f334c3b00eb95d3605e8a61c`; only STATUS and RECEIPT documentation changed after the final validation. No additional source/test edits or redundant validation run were needed to assign the documentation checkpoint. The package remains unaccepted until independent Astra review.

Coordinator committed the stopped correction worker's source/test bytes unchanged at `53c5c44b167f73e7aefb326fdeacfdced5839835`. Exact correction mapping and tests: `checkpoint-001-astra-corrections.md`.

## Next package

SV023 implements only the two preflighted file-repair `continue-from-bound` pairs with intact ledger/identity proof, on temporary fixtures. Its acceptance is separate. Bootstrap, lost-ledger and newer integrity-stop resolutions remain refused.
