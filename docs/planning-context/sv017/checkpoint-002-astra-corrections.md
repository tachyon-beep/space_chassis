# SV-017 checkpoint 002 — correction pass for the Astra initial R-B4 review

Date: 2026-10-08. Branch `sv016/recorder-cleared`, from clean HEAD `1c6224c` (implementation `606a91d`). Input: `../sv016-context/SV-017-Astra-initial-review.md`. Scope unchanged: R-B4 only.

## Finding → change → regression

| Finding | Change | Regression (`tests/test_recorder_custody.py`) | Pre-fix result on `606a91d` |
|---|---|---|---|
| SV017-01 (P2) reporting failure discards a readable result | `recorder.append_with_custody`: the degradation log and diagnostic run inside `except Exception` and the `AppendResult` is always returned; `log()` suppresses `OSError`/`ValueError` from a gone stdout (attempt-only); the `close` stderr fallback likewise. Control exceptions are not caught. No retry, no report-about-the-report | `test_a_failing_degradation_report_never_withholds_a_readable_answer[diagnostic-fails]` and `[log-and-diagnostic-fail]` (transcript `fdatasync` EIO on a readable line; `record_diagnostic` raises; stdout raises `BrokenPipeError`): both requests relayed 200 with the upstream body, `recorded: appended_fsync_failed`, known usage 30 charged each, one close each, sole socket slot reusable, diagnostic attempted exactly once | `500` (`internal error: RuntimeError`) |
| SV017-02 (P3) `dir_unsynced` erased by descriptor retirement | `common.RecordStore`: on `fdatasync` error the append's `names_durable` is read before `_drop` | `test_a_data_sync_failure_keeps_the_namespace_fact_of_its_own_append`: fenced + sync failure → `dir_unsynced False`; failed slug-dir fence + sync failure → `True`; next append reopens, re-fences (slug-dir sync observed) and is `durable`; both paths stay `degraded` | `dir_unsynced=True` for the fenced case |
| SV017-03 (P3) append admitted before `close()` reopens after it | `append_record` rechecks `_closed` under the path lock (taking `_paths_lock` inside it, the same order `_fence_names` uses; `close()` never holds both) and returns `failed` / `detail="closed"` | `test_an_append_waiting_for_its_lock_when_the_store_closes_writes_nothing` (event-driven pause between `_state` and the path lock; `close()` returns; resume): no deadlock, `failed` with 0 bytes, no `open` after close, no cached fd, file unchanged | append reopened and wrote (`durable`) |

Evidence gaps named by the review:

| Gap | Fixture | Pre-fix |
|---|---|---|
| per-path lock under small writes | `test_concurrent_appends_to_one_file_never_interleave` now forces every append through 7-byte writes (8 threads × 50 records) | passed (no defect; stronger evidence) |
| O3-8 two slugs discovered together | `test_two_slugs_discovered_together_each_get_their_own_root_sync` (barrier holds both after their slug-dir syncs; each thread's sequence is slug-dir sync then its own root sync; both durable) | passed (no defect; new evidence) |

Lock order inspected: `_state`, `degraded`: `_paths_lock` only. Append: path lock → `_paths_lock` (closure recheck, root-sync cache). `close()`: `_paths_lock` released before taking each path lock in turn. No cycle.

## Test-only ordering fixes found while running

Each `close` is written after its own reply, so two sequential requests' `close` lines can land in either order. Four assertions compared order; they now compare outcomes as a multiset: `test_low_space_refuses_before_the_open_and_before_any_spend` (failed once in this pass), `test_a_partial_transcript_is_withheld_and_the_next_turn_is_recorded_cleanly`, `test_success_and_provider_errors_are_relayed_with_their_record_class`, and `test_recorder_requests.py::test_a_failing_fleet_slot_acquire_gives_the_socket_slot_back`. No runtime change.

## Commands and results (bounded runner, `--cpu 23`)

1. Pre-fix, one per command: SV017-01 → failed (`500`); SV017-02 → failed (`dir_unsynced=True`); SV017-03 → failed (`durable`); O3-8 + strengthened concurrency → 2 passed.
2. `tests/test_recorder_custody.py` after the fixes → stopped at `test_low_space…` (ordering race above); fixed the assertion.
3. Complete selected set — `tests/test_recorder_budget.py tests/test_recorder_requests.py tests/test_recorder_custody.py`, the four `test_services.py` recorder nodes, `tests/test_run_end_to_end.py::test_a_run_reaches_the_model_through_the_recorder` and `::test_the_recorder_injects_a_credential_the_agent_never_has` (`SC_SCRATCH=/tmp/sv017-integration-check` inherited) → **121 passed**, 2 warnings (`PytestUnhandledThreadExceptionWarning` from the two deliberate `SystemExit` tests, unchanged since SV-016).
