# SV-019 chassis package — implementation receipt

Branch `sv016/recorder-cleared`, base `764d70e2c3c3379a12a3c7cd1305f98c748a8893`. For independent Astra review. I made no push, merge or deployment; the coordinator's authorized WIP backups are durability of the work, not readiness.

| Commit | Unit | Revert |
|---|---|---|
| `71b2644d49102411c1a0afd4def5d442770fc502` | K-A2 narrow flap fix | alone (with its one legacy assertion) |
| `43edf300bf1469ba5c7c4417823667d030e3a638` | K-E1 pure helpers | alone (K-B1 uses `escaped_units`/`normalize_text` for the queue bound: revert K-B1 first) |
| `5788a1e676722ff3643fab681f76ca2dbc565ec9` | K-G1 pure repair + group-atomic outgoing view | alone |
| `1f9f1d79740647495629157b5a8460de8ba41636` | K-B1 termination/control flow + K-A1 staged metadata | one unit (they share the run lifecycle) |
| this docs commit | STATUS, RECEIPT | docs only |

Contracts: SV-013 §2.2.2/2.2.4/§4.1 (K-A1, staged), §2.2.7 first paragraph + SV-015 v2 §3.8/§4.7 (K-A2; v2 withdraws SV-013's flap give-up claim), §2.2.4 message/exit portion (K-B1), SV-015 v2 §2.3 (K-E1, replacing SV-013's UTF-8 rules), SV-013 §2.2.6 atomic groups/repair with v2 §2.3's unchanged window policy (K-G1). Preflight `SV-019-Astra-preflight.json`.

## 1. Contract → test map

**K-A2** (`tests/test_supervisor_flap.py`, 11; plus `test_services.py::test_repeated_clean_exits_are_treated_as_a_loop`, assertion updated)
| Point | Test |
|---|---|
| defaults the trace assumes (3/120, tiers 2/3/5, 900 s) | `test_the_defaults_are_the_ones_the_trace_assumes` |
| C-S1: resume ×3, `flap{tier 1, action resume}`, one failure | `test_c_s1_three_quick_clean_exits_resume_and_count_one_failure` |
| v2 group 4.7: 3/6/9/12/15/18 exits → 1–6 flaps, tiers 1/2/3/3/4/4, always `resume` | `test_group_7_every_flap_resumes_even_at_tier_4[…]` (6 cases) |
| control: five exit-43 → `give_up` | `test_the_ordinary_ladder_still_gives_up_after_five_failures` |
| 18-exit loop: memory/work byte-identical, no restore, tier 4 reached, all `resume` | `test_eighteen_clean_exits_leave_memory_and_shared_work_byte_identical` |
| `resume_without_session`, `SESSION_FILES` removed | `test_the_moving_action_no_longer_exists` |

**K-E1** (`tests/test_chassis_wire.py`, 31): escaped-unit table (incl. DEL and U+2028); C-B11 normalization; revised C-B1…C-B4 and O4-1 with hashes recomputed against the published prefixes/suffixes plus the longest-prefix check; C-B3/C-B4 full hashes; whole text normalized; surrogate in K/N/H; astral never split; too-small cap refused; C-B8, C-B9/O4-12, C-B10, O4-9 (any JSON type), base-length rules, adversarial uniqueness.

**K-G1** (`tests/test_chassis_groups.py`, 11): same objects when well-formed; missing result → `REPAIRED_UNKNOWN_RESULT` ("may or may not have run", never "not run"); system message moved after its group; stray/duplicate results → `[orphan tool result for <id>]: …` user notices; group ends at the first non-tool/system message; call-order pairing incl. duplicate ids; idempotence; window never opens inside a group at an interposed system message; outgoing view repaired while the stored list is unchanged; pinned/budget view unchanged; repeated folding over broken groups with every evicted message recorded exactly once and no repair text in the recap.

**K-B1** (`tests/test_chassis_termination.py`, 37)
| Point | Test |
|---|---|
| C-T1 (message/exit portion) | `test_c_t1_a_handoff_from_a_tool_answers_every_call_and_runs_no_more` |
| C-T2 swallowed handoff, no false end | `test_c_t2_a_duty_that_swallows_the_handoff_continues_without_a_false_end` |
| C-T3 bare `sys.exit(42)` | `test_c_t3_a_bare_sys_exit_42_is_not_a_handoff` |
| C-T4 `SystemExit(['x'])` → 43 | `test_c_t4_an_invalid_exit_payload_is_the_runs_fault_not_an_escape` |
| C-T5 nested ask | `test_c_t5_a_nested_ask_is_refused_as_the_tools_error_and_the_turn_goes_on` |
| C-T6 note after all results | `test_c_t6_a_note_from_a_tool_lands_after_all_of_the_groups_results` |
| C-T7 set_history refused | `test_c_t7_history_cannot_be_replaced_from_inside_a_tool` |
| C-T8 interrupt → unknown, 44 | `test_c_t8_an_interrupt_during_a_call_leaves_its_outcome_unknown` |
| every control class (EnvironmentFailure, DutyFault, Turn/WallLimitReached, PersistenceFailure, GeneratorExit, custom BaseException, SystemExit None/str/300/True, finish) → owner, one result per call, later unrun, no further invocation | `test_every_control_exception_ends_the_run_with_every_call_answered[…]` (12 cases) |
| ordinary exception stays text | `test_an_ordinary_tool_exception_is_still_the_models_text` |
| direct handoff/finish/SystemExit(42)/invalid/return from main | `test_direct_ends_from_main_are_typed[…]` (6 cases) |
| queue order, 17th refused, nothing silently dropped | `test_queued_messages_keep_their_order_and_the_seventeenth_is_refused` |
| 64 KiB escaped-unit bound (ASCII/BMP/controls at and over) | `test_a_queued_message_is_measured_in_escaped_units[…]` (5 cases) |
| queue flushed after a terminated group | `test_a_message_queued_before_a_handoff_is_flushed_after_the_group` |
| say/note outside a group append at once | `test_say_and_note_outside_a_group_append_at_once` |
| failed final checkpoint → 44 `persistence_failure`, `checkpoint_failed` recorded | `test_a_failed_final_checkpoint_becomes_persistence_failure` |
| failed turn checkpoint → 44, no further turn | `test_a_failed_turn_checkpoint_ends_the_run_as_an_environment_failure` |

**K-A1** (`tests/test_chassis_metadata.py`, 7): additive keys and no `format`/`writer`/`checkpoint`/`history_epoch`; plain list byte-compatible; stable lineage and `previous_run_ended`/`turns_before_this_run` from the previous run; invalid lineage replaced and recorded; fold progress survives resume with no duplicate recap lines; fold point clamped to a shortened list; a startup failure before `main` writes no end and touches no memory.

## 2. Runs (bounded runner, `--cpu 23`, one command at a time)

| Run | Targets | Result |
|---|---|---|
| 1 | `tests/test_supervisor_flap.py` (pre-fix) | failed at C-S1: `('resume_without_session', 1)` |
| 2 | flap file + 7 legacy supervisor nodes | 18 passed |
| 3 | `tests/test_chassis_wire.py` (pre-fix) | collection error: helpers absent |
| 4 | same | 1 failure: my cost table said DEL = 1, but `json.dumps(ensure_ascii=True)` escapes DEL as `\u007f` (6). v2 counts only *printable* ASCII as 1: code and test row corrected to the definition |
| 5 | same | 1 failure: my test expected a unique valid 49-character id to be rewritten; it is correctly kept. Test corrected to a duplicated 49-character id |
| 6 | same | 31 passed |
| 7 | `tests/test_chassis_groups.py` (pre-fix) | collection error: helpers absent |
| 8 | same | 11 passed; 9 legacy window/recap nodes passed |
| 9 | `tests/test_chassis_termination.py` | 1 failure: my test assumed an assistant message after a refused queue entry; the next message is the duty's own second `ask`. Assertion made exact |
| 10 | same | 37 passed |
| 11, 12 | C-T1, C-T4 single nodes | passed — **against the new code**: an attempted `git stash` to obtain pre-fix runs was denied by the permission layer, so these are not pre-fix evidence |
| 13 | `tests/test_chassis_metadata.py` | 7 passed |
| 14 | complete SV-019 selected set: the 5 new files + all 29 legacy nodes | **126 passed**, no warnings |

Pre-fix evidence for K-B1/K-A1 is therefore by source, not by a run: before `1f9f1d7`, calls after a handoff were left unanswered (the loop simply stopped), `int(['x'])` raised `TypeError` inside the `SystemExit` handler, `invoke` let only `SystemExit` through (a tool's `DutyFault` or budget exception became text), `run.json` held no `recap_folded` (every resume folded from 0), and a failed final checkpoint was suppressed.

Not run: the full repository suite, ruff, the vehicle referee, pump, live supervisor, real provider.

## 3. Staged exclusions (not implemented; not claimed)

- **Ledger and recovery (K-D):** no `REQUEST_SENT`/`TURN_RESPONSE`/`INVOKING`/`DONE`/`TERMINATION`/`UNRUN`/`CHECKPOINT` records, no `write_bytes_durable`, no CK1–CK6, no A0–A15 classification, no `--acknowledge-stop`. Hence no `format`/`writer`/`checkpoint` in run.json (preflight staging exception: retained rule A7 would read them as a lost ledger).
- **Notes (K-F):** handoff notes keep legacy `HANDOFF.md` storage and today's re-append-on-every-resume behaviour; no generations, exactly-once adoption or legacy migration. C-T2's "adopted once" portion is **not** claimed.
- **Envelope (K-E2):** helpers are not wired into stored responses; no response-count caps, argument elision, `TURN_RESPONSE`/original blobs, wire-id rewriting of real calls, or request-size refusal. Provider acceptance of rewritten ids is a later gate.
- **Durable repair (K-G2):** repair applies to the outgoing view only; persisted histories are never rewritten.
- **Supervisor:** no new give-up, pause, reset or restore policy; the flap tier stays diagnostic.

## 4. Behaviour changes for review

- `close`-style exit reasons now appear in `run_end` (`reason`) and `run.json.ended`.
- A tool's `DutyFault`, `EnvironmentFailure`, budget or `PersistenceFailure` now ends the run (with its owner's exit code) instead of becoming text.
- `SystemExit` with a bool, an int outside 0–255, or a non-str/non-int payload exits 43 `invalid_exit_payload` (an int like 300 used to be passed on and wrap).
- During a tool group `ask`/`set_history` raise and `say`/`note` queue; queued text over 16 messages or 64 Ki escaped units raises `ValueError`.
- A failed checkpoint is exit 44 `persistence_failure` (mid-run, or at the end unless already 44); an unserializable final checkpoint is 43 `checkpoint_failed`.
- The outgoing request is the repaired view (synthesized unknown results, moved system messages, orphan notices); the window never starts inside a group.
- Flaps resume at every tier; `session/abandoned/` is never written.

## 5. Evidence limits

All runs are local fakes: no provider, model, socket or live supervisor. In-memory pairing is complete going forward; a run killed mid-group still leaves an unpaired stored list (only the outgoing view is repaired), and crash outcomes stay unclassified until K-D. Startup failures before `main(context)` (directories, run.json read, recorder connection, duty load, tool binding, resume/bootstrap) produce no `ended`/`run_end` and no checkpoint, by design.
