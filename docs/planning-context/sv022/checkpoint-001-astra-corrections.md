# SV-022 correction 1 — Astra SV022-01, SV022-02

2026-10-08, Australia/Sydney. Against review `SV-022-Astra-initial-review.md`: reviewed head `6a2e504a0dd104d20139510dfc0188140af7af7c`, runtime/tests `efc6c03a9b205132f334c3b00eb95d3605e8a61c`, accepted SV-021 base `630623a4af30a8d08e90f5d9b0d2ef626af20f13`. Same model/allowance/limits; the approved runner only, one explicit literal command at a time; temporary roots; the local stub. No Git call, provider, deployment, real-session deletion or real stop acknowledgement. Only these two findings were changed; the retention, fixed-list, namespace, state, correlation and alias-assertion mechanisms the review lists are kept, and no existing assertion was changed.

Runtime/tests committed by the coordinator at `53c5c44b167f73e7aefb326fdeacfdced5839835` after worker exit 0, without changing their tested bytes. Independent re-review pending.

Method: each regression written first and run alone (one runner command per node) on the unmodified reviewed runtime; then the fixes; then the batches below.

## Finding → fix → regression (pre-fix outcome)

| Finding | Fix | Regressions and pre-fix result |
|---|---|---|
| **SV022-01** P1: restart unlinked under a readable intent whose bytes may never have been synced | `chassis_gc.sync_intent`: open the segment file holding the pending intent's verified frame (by the record's own segment number, not the writer's newly opened segment) and fsync it. `chassis_startup._recover` calls it after validation and the frozen-prefix comparison, immediately before `unlink_intent`, only when the intent is still pending (no GC_DONE in `extra`). Failure → `PersistenceFailure` → the startup boundary attempts FSYNC_FAILED; no unlink, no GC_DONE, no later effect. Namespace fences unchanged; GC_DONE still follows the deletion fences; GC_DONE is still the first core record. | `test_sv022_01_a_restart_syncs_the_readable_intent_before_its_first_unlink` — Astra's trace: intent written, crash before its fsync (process death), restart with the **first process's durability watermark carried over** (`CutOps(durable=...)`; reopening no longer promotes readable bytes), crash after the first segment unlink and its `ledger/` fence, then simulated host loss of bytes whose fsync never returned in either process. **Pre-fix: failed** — next start stopped `ledger_prefix_missing` (oldest segment 2): the deletion outlived its authority. Post-fix it converges over two starts with one GC_DONE, and the event log shows `fsync(<intent segment>)` before the first unlink, then `fsync(ledger/)`. `test_sv022_01_a_failed_restart_intent_sync_removes_nothing` — EIO on that gate. **Pre-fix: failed** (`DID NOT RAISE PersistenceFailure`: no gate existed, startup deleted). Post-fix: raises; zero unlinks; no GC_DONE; inventory unchanged; FSYNC_FAILED present; next start A1. |
| **SV022-02** P2: the validator accepted a sorted eligible list that leaves a gap | `chassis_gc.segments_form_prefix`, checked in `intent_problem` (so before live GC_INTENT publication and before pending execution): no listed surviving segment may be deleted while an older surviving segment is omitted, and listed segments already gone must lie below every survivor. Already-removed leading items of the original fixed list stay valid (ENOENT idempotence); no fresh scan; unrelated-gap refusal unchanged. Problem string `segment prefix`. | `test_sv022_02_a_list_skipping_a_surviving_segment_is_refused_and_a_partial_prefix_is_not` (front `[2,3,4,5]` and interior `[1,3,4,5]` of `[1..5]` refused; the original list with segments 1–2 already removed accepted). **Pre-fix: failed** — front-skip returned no problem. `test_sv022_02_startup_refuses_a_pending_intent_that_would_leave_a_gap[front]`, `[interior]` — chain-valid pending intent; require `gc_intent_invalid`/`segment prefix` and a byte-identical tree except STOPPED. **Pre-fix: both failed** — startup classified A9 and executed the list. `test_sv022_02_the_live_owner_refuses_a_skipping_plan_before_publishing_it`. **Pre-fix: failed** — the live owner published and executed it (`gc_collected`, intent 36). Post-fix: `gc_refused`/`segment prefix`, no GC_INTENT, nothing removed. |

Six pre-fix runs, all failing as the review traced (the pure node stops at its first, front, case; the interior case's pre-fix failure is shown by the startup `[interior]` node).

## Harness change (no assertion changed)

`CutOps(durable=None)`: may share another process's watermark. Default behaviour is unchanged. The existing second-interruption fixture now passes the first process's map (its intent was synced, so its outcome is unchanged), as the review asked to extend the durability model there.

## Post-fix runs (final corrected tree)

| # | Targets | Result |
|---|---|---|
| C1 | `tests/test_chassis_gc.py` | 50 passed (44 + 6 new; includes the partial-prefix restarts: three cut matrices, second interruption, stored-list rerun) |
| C2 | `tests/test_chassis_correlation.py` | 2 passed |
| C3 | `tests/test_chassis_recovery_live.py` | 97 passed |
| C4 | `tests/test_chassis_replay.py tests/test_chassis_session.py` | 61 passed |
| C5 | `tests/test_chassis_notes.py tests/test_chassis_checkpoint.py` | 23 passed |
| C6 | `tests/test_chassis_adoption.py` | 50 passed |
| C7 | `tests/test_chassis_termination.py` | 67 passed |
| C8 | the 5 local-stub `test_run_end_to_end.py` nodes | 5 passed |
| C9 | the 22 retained `test_chassis.py` + 7 `test_services.py` nodes | 29 passed |
| C10 | groups, wire, supervisor flap, metadata | 65 passed |
| C11 | accepted foundation: ledger, recovery, durability | 114 passed |

Total 563 selected passes, no failures, no full-suite run. The six pre-fix failures above are this correction's negative evidence; M1–M4 from the original package were not repeated.

## Files touched by this correction

`services/chassis_gc.py` (`segments_form_prefix`, `sync_intent`, docstring), `services/chassis_startup.py` (the gate call, docstrings), `tests/test_chassis_gc.py` (`CutOps(durable=)`, second-interruption watermark, 6 regression nodes), docs `STATUS.md`, `RECEIPT.md` (§10), this file.

## Evidence kinds and limits

The mixed trace is in-process: process death is a raised `Crash` (M-1, completed calls kept); host loss is simulated by truncating to returned-fsync watermarks and undoing unfenced unlinks (M-2). No real power loss or kernel/storage behaviour is exercised. Real process death appears only in the correlation and script-restart fixtures. Still unclaimed: exact v2 1.4.7 replay bounds, bounded total disk, rotation-name loss, remaining acknowledgement resolutions, provider/deployment compatibility, general power-loss behaviour.
