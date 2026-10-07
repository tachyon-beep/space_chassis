# SV-016 checkpoint 001 — R-0 and R-A1 written and checked

Date: 2026-10-08. Branch `sv016/recorder-cleared`, base `fa43b25b0fd7d88a3f5e7feb3338e190078517ce`.

## Changed files

- `endurance/report.py` — `count_requests(events)`: distinct string ids of `open` events (R-0). `agent_metrics["requests"]` uses it; every other field unchanged.
- `services/recorder.py` — `Allowance` and `SharedTokens` replaced by `SystemClock`, `Entry`, `RollingPool`, `HourBucket`, `Reservation`, `Usage`, `Admitted`, `Refused`, `Closed`, `Budget`, `refusal_message` (R-A1). Handler **not yet rewired** at this checkpoint (it still references the removed classes at run time; nothing is committed in that state).
- `tests/test_recorder_budget.py` — new (runner-allowed file).
- `tests/test_services.py` — the three ceiling tests (`:266-295` at base) rewritten against `Budget`, intent kept.

## Commands and results

All through `python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 …`, one at a time.

| Command targets | Result |
|---|---|
| baseline: `tests/test_services.py::` the 5 recorder nodes (pool of zero, allowance, shared pool, prefix, header source-grep) on the unmodified base | 5 passed |
| `tests/test_recorder_budget.py` (first run) | 20 passed, 1 failed: a test-setup error (3 entries filled `Rq=3` so `requests` correctly refused first); fixed the test's `rq`, not the oracle |
| `tests/test_recorder_budget.py` | 33 passed |
| `tests/test_services.py::test_a_pool_of_zero_refuses_rather_than_crashing`, `::test_an_allowance_counts_requests_and_tokens_separately`, `::test_the_shared_pool_empties_at_the_top_of_the_hour` | 3 passed |

## Next step

R-A2: rewire the handler to one `Budget` per recorder process; one close event; `recorder.jsonl`; in-flight slots; end-to-end tests over a UDS stub.

## Blockers / limits

- The runner file and its allowlist could not be read (outside allowed directories, permission denied). Allowed new test files were found by probing: `tests/test_recorder_budget.py`, `tests/test_recorder_requests.py` allowed; `test_recorder.py`, `test_recorder_handler.py`, `test_report.py`, `test_recorder_e2e.py`, `test_recorder_report.py`, `test_recorder_integration.py`, `test_recorder_transport.py`, `test_endurance_report.py` refused.
- `git check-ignore` and `git -C` were denied; plain `git status` from the checkout works.
