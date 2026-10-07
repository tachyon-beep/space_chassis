# SV-019 checkpoint 002 — correction 1 (Astra initial review + K-G1 review)

Date: 2026-10-08. Branch `sv016/recorder-cleared`, from clean `3251057e175f26a35d652953a13e5c560e2d69a2` (coordinator WIP-backed; a backup, not acceptance). Inputs: `../sv016-context/SV-019-Astra-initial-review.md`, `SV-019-Astra-K-G1-review.md`, `SV-019-integration-targets.json`. Correction commit: `2f0567c1e1aaa0ca900adfa5f4ce1eaa40a783a9`. K-A2 (`71b2644`) and K-E1 (`43edf30`) are unchanged.

## Finding → change → regression → pre-fix result

| Finding | Change (`services/chassis.py`) | Regression | Pre-fix (run on `3251057` code) |
|---|---|---|---|
| SV019-G1-01 newest oversized group split | `selection` calls `_whole_unit_start`: a start inside a group moves forward to the next unit if there is one, else back to the group's head (the newest group is kept whole even over budget). Indices stay in the original history; `window_bounds`/fold use the same start | `test_chassis_groups.py`: `test_the_window_never_opens_inside_a_group_at_an_interposed_system_message` (now a group-atomic oracle over original indices, last-index exemption removed, budgets 1…1600 × chunks 1/50/400), `test_an_oversized_newest_single_call_group_is_kept_whole` (indices `[0,1,2]`, start 1, fold `(1, 2)`, outgoing view = the same objects, no orphan), `…multi_call_group_is_kept_whole_with_its_system_messages`, `test_a_trailing_system_message_does_not_split_the_newest_group`, `test_an_older_group_is_dropped_whole_and_the_newest_ordinary_tail_kept`, `test_repeated_folding_never_folds_part_of_a_retained_oversized_group` | selection `[0, 2]` instead of `[0, 1, 2]` |
| SV019-B1-01 queue measures normalized, stores original | `queue_message` stores the normalized text it measured | `test_chassis_termination.py::test_queued_text_is_stored_normalized_exactly_as_it_was_measured[few-surrogates, surrogates-at-cap (65,536 ⇒ 65,536 `?`), surrogates-over-cap (65,537 ⇒ refused)]`: in-memory, saved and every outgoing request checked for any U+D800–U+DFFF; queue order; refusal, not truncation | stored `'\ud800'×10 + 'ok'` instead of `'?'×10 + 'ok'` |
| SV019-B1-02 two module identities in script mode | `if __name__ == "__main__": sys.modules["chassis"] = sys.modules[__name__]` before `main()` (before any duty code) | `test_chassis_termination.py::test_script_mode_controls_from_an_imported_runtime_reach_their_owner[…]` — 14 cases: {`import chassis`, seed-style `sys.modules["chassis"]`} × {EnvironmentFailure 44, TurnLimitReached 42, DutyFault 43, typed `RunTermination("handoff")` 42, `finish` 0, `SystemExit(300)` → status 44, `SystemExit(-1)` → 255}, each a real `python3 services/chassis.py` subprocess with temporary roots against the local stub model over a unix socket; asserts module identity, process status, `run_end.reason`, one result for the active call, "not run" for the later call, no later invocation. Plus `test_script_mode_a_swallowed_handoff_continues_and_ends_as_main_returned` | `same_module: False`; invoked `[main, read_file, act, write_file]`; exit 0 `main_returned` (the imported EnvironmentFailure became tool text and the later call ran) |
| SV019-B1-03 0–255 exit policy | `classify_exit`: any `int` (bool included, as `int(True) == 1`) → that int, reason `exit_<n>_without_termination_record`; `None`, `str` and other payloads unchanged (other → 43) | `test_an_integer_exit_is_passed_on_unchanged[…]` (0, 42, 300, −1, True, False, None, str, list, float); CONTROL fixture now expects 300 → 300, −1 → −1, True → 1, `[1]` → 43; script mode 300 → status 44, −1 → 255 | `(43, 'invalid_exit_payload', 'SystemExit(300)')` |
| Doc: CH1 `run_ended_unresumable` | comment now: a label, not a reset; `resume()` adopts any readable conversation whatever the exit | — | — |
| Doc: "every upstream will accept" | `repair_structure`/`prepared_view` docstrings: ordering and pairing only; provider schema and id acceptance unvalidated | — | — |

No temporary rollback was needed: every pre-fix result above is a run of the new regression against the unchanged committed runtime, before the fix was applied. The earlier denied `git stash` was not retried.

## Runs (bounded runner, `--cpu 23`, one at a time; `SC_SCRATCH=/tmp/sv019-integration-check`)

1. `tests/test_chassis_groups.py::test_an_oversized_newest_single_call_group_is_kept_whole` → failed (pre-fix, above).
2. `tests/test_chassis_termination.py::test_queued_text_is_stored_normalized_exactly_as_it_was_measured` → failed (pre-fix).
3. `tests/test_chassis_termination.py::test_an_integer_exit_is_passed_on_unchanged` → failed at 300 (pre-fix).
4. `tests/test_chassis_termination.py::test_script_mode_controls_from_an_imported_runtime_reach_their_owner[environment-import-chassis]` → failed (pre-fix).
5. After the fixes: `tests/test_chassis_groups.py` → 16 passed.
6. `tests/test_chassis_termination.py` → 67 passed.
7. Complete SV-019 selected set (5 new files + 29 legacy nodes) → **161 passed**, no warnings.
8. `SV-019-integration-targets.json` nodes (`test_run_end_to_end.py` handoff, second run, turn limit, lifecycle, route) → **5 passed**.

## Limits

Script-mode tests run the real script entry against the local stub model, not a recorder, provider or supervisor; the identity binding is shown for `import chassis` and the seed's `sys.modules` lookup, not for a duty that loads a file by path under another module name (that duty would build its own runtime, as before). A run killed mid-group still leaves its stored list unpaired (only the outgoing view is repaired; K-G2). Exit statuses above 255 or below 0 are the operating system's arithmetic and are not re-mapped.
