# SV-017 checkpoint 001 — R-B4 custody implemented and checked

Date: 2026-10-08. Branch `sv016/recorder-cleared`. Base `afec0a8` (accepted SV-016). Implementation commit `606a91d3e2c1cd68e23d2221cfcaff652993461a`.

## Changed files

`services/common.py`, `services/recorder.py`, `tests/test_recorder_custody.py` (new), `tests/test_recorder_requests.py` (minimal adjustments). Details and the contract → test map: `RECEIPT.md`.

## Commands and results

1. `…/SV-016-bounded-check.py --cpu 23 tests/test_recorder_custody.py` → 28 passed.
2. Selected set (budget, requests, custody, 4 `test_services.py` nodes, 2 `test_run_end_to_end.py` nodes) → stopped at a test race (`test_an_estimate_too_large_for_the_socket_is_refused_before_the_upstream` read events before the post-relay close); test fixed to wait.
3. Same selected set → 116 passed, 2 expected `SystemExit` thread warnings.

## Denied (not bypassed)

A `git commit` whose message contained a brace-quote sequence was denied by the permission layer; the commit was retried with reworded text (nothing else changed).

## Next step

Docs commit (this file, STATUS, RECEIPT, SV-016 status-wording fix); then independent Astra review.

## Blockers

None. Real filesystem crash/power-loss evidence remains a deployment gate, not a blocker for this commit.
