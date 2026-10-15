# #23 implementer report, candidate 0

Received 2026-10-12T10:10:25.553Z; saved verbatim (harness indent removed).

---

## #23 WP08.5 (clock seam): implementation report

The tests and the implementation are in the worktree `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock` (branch `codex/23-clock-seam`, base `7a87eb8`), uncommitted. **Nothing has been run** beyond `py_compile` and `ruff check`, so none of this is proven yet. No test, no repository program, no systemd and no docker was run. Nothing was committed, stashed or pushed. I did not touch the chassis's submodule checkout, the #39 worktree, the chassis's files, `governance/` or the chassis delta of design §7.

The progress log is `/home/john/space_chassis/.scratch/wp08-23/IMPLEMENTATION-LOG.md`. It holds the frozen seam names, 18 numbered judgment calls, the verification results and handoff notes.

### git diff --stat
```
 README.md                                          |   67 +-
 docs/decisions/0002-mission-clock-and-continuity.md |  105 +-
 tests/test_vehicle_config.py                       | 1344 ++++++++++++++++++--
 tools/check_vehicle.py                             |   77 +-
 tools/checkpoint.py                                |  140 +-
 tools/console.py                                   | 1217 +++++++++++++++---
 tools/generate_help.py                             |    4 +-
 tools/generate_readme.py                           |    4 +-
 tools/measure_clock.py                             |  197 ++-
 9 files changed, 2790 insertions(+), 365 deletions(-)
```
The referee test count goes from 537 to 558.

### What was built
- **`tools/console.py`:**
  - The scheduler: `Pacer(now_ns, sleep)` with a `stopping` flag. Tick `t` is due at `E + (t−t0)·dt/m` in integer nanoseconds, with `m` held as a `Fraction`. The epoch is read at the segment's first wait. A cycle never runs ahead, and each sleep is capped at 100 ms.
  - The cycle: one claim, `k` steps (the effect report and dwell against step 1), one publication. Row 1 is written ahead when it carries anything. A compare-point refusal at step `j` appends only the rows not yet durable and puts `last_durable_tick` on the `UncomparableState` it raises.
  - The record is format v3: the segment header gains `m`/`k`/`N`, every row gains `lag_us`, and a cycle's first row gains `prev_cycle_us` and `prev_end_lag_us`. `_verified_lines` and `unwritten_results` check the row invariant and accumulate receipts per cycle.
  - Lag and summaries: `CycleStats`, `cycle_summary`, `segment_summaries`, and a `manifest` event written at a clean end.
  - Stalls, backstop and stopping: `stall` events; the backstop raises `LagBackstop`, exits 4 and prints `[console] lag_backstop lag_s=<n> consecutive=<n>`; without a state directory it rebases the epoch instead. The consecutive count is read back from the previous segment's manifest. SIGTERM/SIGINT handlers are installed at the top of `main` and restored on exit.
  - Flags: `--multiplier`, `--cycle-ticks` and `--checkpoint-ticks`, all defaulting to `None`; `--poll` is removed. Each invalid value and each missing input is refused by name with exit 3.
  - On a resume, `m`, `k` and `N` are resolved after the replay: the named flag, else the newest recovered policy. A named change is journaled in `run_inputs`.
  - Deferrals are due at `a + k`. Arbitration rotates by cycle, `(tick//k)%n`. The static files are rewritten on the staggered `N` cadence. The telemetry ring is now a persistent cache on the `Window`, rescanned at boot, after a repair, on the `N` reconcile, or when `telemetry/` is replaced.
- **`tools/checkpoint.py`:** the clock functions (`parse_multiplier`, `multiplier_text`, `clock_section`, `cycle_ns`, `clock_problem`), validation of the `clock` section, and `m`/`k`/`N` added to the segment entries.
- **`tools/check_vehicle.py`:** `_checkpoint_clock_keys` resolves the `CLOCK_INPUTS` comprehension, and `CHECKPOINT_CLOCK_FLAG_DESTS` maps the three keys to their flags.
- **`tools/measure_clock.py`:** adds p99, a clock-seam section (a k-tick cycle with take barriers and the write-ahead `fsync`, full 3,000-slot rings, static rewrite alone and with a checkpoint, a worst-cycle check against the budget), the `CLOCK_INPUTS` keys and v3 rows.
- **Docs:** the README round entry plus the README:67 example; ADR 0002 amendment (xlvi) with short notes at the answers to A, B and C and at J item 2; the "about once a mission second" sentence in the generated HELP and README; module docstrings updated.

### New tests (design §6 items 1–21)
1. `test_frames_are_exactly_k_ticks_apart_within_a_segment_even_while_the_scheduler_catches_up`
2. `test_a_command_lands_at_its_cycles_start_tick_at_offset_zero_and_takes_effect_in_the_next_frame`
3. `test_a_cycle_never_steps_more_than_k_and_a_scheduler_behind_runs_whole_cycles_back_to_back_never_ahead_of_the_clock`
4. `test_every_row_carries_its_cycles_start_lag_and_its_first_row_the_cost_carried_forward_and_the_reader_summarises_as_the_clean_end_does`
5. `test_a_serving_start_naming_no_clock_refuses_by_name_and_init_and_plan_need_none`
6. `test_a_clock_whose_n_is_not_a_multiple_of_k_whose_k_outruns_the_channel_rates_or_whose_cycle_is_out_of_bounds_refuses_at_the_cli_and_in_the_checkpoint`
7. `test_a_resume_inherits_m_k_and_n_a_named_change_is_journaled_and_kept_and_a_fall_back_keeps_the_newer_policy`
8. `test_a_checkpoint_ends_every_cycle_that_crosses_a_multiple_of_n_including_after_an_unaligned_resume`
9. `test_a_crash_inside_a_command_bearing_cycle_publishes_nothing_and_the_resume_owes_exactly_its_first_rows_receipts`
10. `test_a_deferral_settles_at_the_next_cycles_start_and_after_an_unaligned_resume_at_the_first_boundary_at_or_after_its_due_tick`
11. `test_the_generated_files_are_rewritten_on_the_staggered_n_cadence_on_a_segments_first_cycle_and_after_a_repair_and_not_every_cycle`
12. `test_the_linter_refuses_a_clock_flag_whose_default_is_not_none_and_a_clock_section_it_cannot_resolve`
13. `test_live_equals_replay_at_k_5_including_the_dwell_a_commands_first_step_stamps`
14. `test_pacing_stays_out_of_the_trace`
15. `test_a_k_5_world_that_crashes_mid_cycle_resumes_at_k_1_across_an_n_boundary_and_replay_equals_live`
16. `test_a_k_5_cycle_with_verdicts_reads_back_with_its_notes_verified_and_a_clean_resume_writes_no_duplicate_result`
17. `test_with_ten_windows_at_k_5_each_window_goes_first_exactly_once_in_ten_cycles`
18. `test_a_compare_point_refusal_inside_a_cycle_appends_only_the_rows_not_yet_durable_and_stops_at_the_last_durable_tick`
19. `test_sigterm_during_a_command_bearing_cycle_completes_the_cycle_answers_the_batch_and_ends_cleanly`
20. `test_a_stall_past_the_lag_ceiling_ends_cleanly_with_exit_4_resumes_on_a_fresh_epoch_and_without_a_state_directory_rebases`
21. `test_the_telemetry_ring_at_3000_slots_is_kept_in_memory_and_rescanned_only_at_boot_after_a_repair_every_n_ticks_or_when_replaced`

### Adapted existing tests
- **The `--poll` literals:** all 78 were replaced by `*CLOCK` (m=10, k=1, N=50; 2 ms ticks) or, for the two that ran on `--poll 0.05`, by `*SLOW_CLOCK` (m=0.4). The mapping's count of 90 was an overcount. `start()`'s default arguments follow.
- **The interrupt harness:** `INTERRUPTIBLE_CONSOLE` now passes its sleeper through `main(argv, pacer=)`, and its holds poll `pacer.stopping`, because a plain sleep would resume after the handler (PEP 475). It runs on m=0.2 so a wait always falls between cycles, and gains a `batch` mode and `signal_name`/`commands` parameters.
- **The interrupt test is renamed** `test_a_run_ending_cleanly_checkpoints_its_last_completed_cycle_and_an_interrupt_mid_cycle_completes_the_cycle_first`. It now asserts graceful completion: tick 3, checkpoint 3 and a manifest.
- The hand-edit assertion in `test_the_window_s_sixth_file_is_generated_from_the_configuration` now follows the `N` cadence (N=5).
- The rotation test `test_a_conflict_domain_is_won_once_a_tick_and_the_rotation_decides_by_whom` now rotates per cycle.
- **Format pins:** record v3 in two places, checkpoint v3, and the "value flipped" checkpoint literal moved to v4.
- `TICK_ROW_KEYS` gains the three wall fields.
- The hand-built rows and headers gain the wall fields and `m`/`k`/`N`.
- Found while implementing: the exact key set in `test_a_checkpoints_segment_entry_carries_the_byte_offset_just_after_the_last_line_it_covers` gains `m`, `k`, `N`.

### Judgment calls where the design was silent (all 18 are in the log)
- **The checkpoint format moves to `vehicle.checkpoint.v3`.** This is the only call that changes how an old file on disk is refused. The checkpoint reader checks a body's shape before its engine identity, so a v2 checkpoint would otherwise be read as *corrupt* and fallen back from, instead of being refused as *incompatible*. The module's own rule is that a change to how a checkpoint is read is a change of format. ADR (xlvi) records it.
- **In-process `Executive` defaults are m=1, k=1, N=tick_hz** and there is no pacer, which behaves as a clock that is always on time. This is the test seam, as `checkpoint_every` was. `main` always passes the resolved values.
- **A cycle's first row and its other rows are two exact key sets**, checked by position.
- **Write-ahead only applies when k > 1**, so a k=1 cycle keeps today's single `fsync`.
- **A refusal without a journal commits nothing** and names the cycle's start tick.
- **`run_inputs` keys are `"m"`, `"k"` and `"N"`**, with `m` written as `"p/q"`.
- **The rebase's `consecutive`** is that segment's backstop count.
- **One `stall` event per cycle**, with a `kinds` list.
- **The ring reconcile runs in the same cycle as the static rewrite.**
- **Manifest field names:** `consecutive_backstops` at the top level, and `summary.backstops`.
- **The previous manifest is found through the boot marker**, reading back past at most 64 events.
- **`clock_problem` names `m` for the wall-time bounds.**
- **Individually invalid values are refused for every start**, including `--init` and `--plan`. Missing inputs and the combined bounds are checked only on a fresh serving start or a resume.
- **The reader now requires a note to follow its cycle's last row.** This tightens the reader; it does not loosen it.

### What I could not do or verify
- **Every test is unrun**, as the rules require; they were checked only by reading.
- **`measure_clock.py`'s new section is unexecuted code.** It is the §8 run that needs a Governance slot.
- **Test 13 has a known gap.** I could not verify a verb whose target keeps changing after its step, so the test uses `set_rcs_mode`. It pins the dwell stamp (`changed_at_us == 0`) and live == replay. The "keeps changing" half of the determinism review's P1-B should be confirmed, or the verb swapped, when a slot allows.
- **The new `os.fstat` in `Window.open_handles` and `previous_manifest`'s calls add calls to the start-path EIO-injection test's walk.** Both sit inside handled paths; that test should be in the first bounded selection.
- **The chassis delta (§7) is not done**, by instruction.

### Verification
- `py_compile`: every changed Python file compiles.
- `ruff check tools/ tests/ --no-cache`: all checks passed.
- `ruff format --check`: no file's status changed. `generate_help.py` is formatted before and after; the other six changed Python files were already unformatted at `7a87eb8`. The repository runs `ruff check` only.
- The design file is unchanged (sha256 `4e8d0d6a…`).
