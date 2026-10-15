# #23 WP08.5 clock seam — implementation log

Implementer: Claude (subagent), 2026-10-12. Worktree:
`/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock`
(branch `codex/23-clock-seam`, base `7a87eb8`). Design: `DESIGN.md` (sha256 4e8d0d6a…).

Rules in force: no test, no repository program run; only `py_compile` and `ruff`. Nothing committed.

## Status

- [x] orientation (design, mapping, conventions, console.py regions)
- [x] tests (§6 new 1–21; adaptations) — written, py_compile + ruff clean; never run (rules)
- [x] tools/checkpoint.py (FORMAT v3, clock functions, clock + segment validation)
- [x] tools/console.py (Pacer, scheduler, cycle of k, write-ahead, v3 record + readers, ring cache,
      static cadence, deferral due, rotation, backstop/stall/manifest, resume resolution, flags, signals)
- [x] tools/check_vehicle.py (`_checkpoint_clock_keys`, `CHECKPOINT_CLOCK_FLAG_DESTS`)
- [x] tools/measure_clock.py (p99, `clock_cycle_costs` section, CLOCK_INPUTS keys, v3 rows) — unverified
- [x] tools/generate_help.py, tools/generate_readme.py (the "about once a mission second" sentence)
- [x] README round entry (+ the `--poll` example at README.md:67), ADR 0002 (xlvi) + inline notes at
      A, B, C answers and J item 2, console.py module docstring
- [x] py_compile + ruff (see "Verification" below)

## Plan (as settled before writing)

- `Pacer` (injected `now_ns`, `sleep`, `stopping` flag) on the executive; `pacer=None` is the
  in-process "always on time" clock (no wait, lag 0, cost 0). `main(argv, pacer=None)` builds the real
  one (CLOCK_MONOTONIC, `time.sleep`). The interrupt harness passes `pacer=` (the injected sleeper).
- `Executive(..., multiplier=1, cycle_ticks=1, checkpoint_every=tick_hz)` in-process defaults are the
  test seam (k = 1, as §6 says); `main` always passes the three resolved values.
- `cycle()`: wait (epoch lazily at the first wait), stall/backstop check before any handle, claim and
  validate, step 1 with effects (+ `_report_effect` on that step), write-ahead row 1 when it carries
  anything, steps 2..k into locals, group append, root record, publish, checkpoint on crossing a
  multiple of N.
- Record v3: header + `m` (`"p/q"`), `k`, `N`; every row + `lag_us`; a cycle's first row also
  `prev_cycle_us`, `prev_end_lag_us` (two exact key sets, position-checked by the reader).
- Checkpoint: clock filled; segments entries mirror m/k/N; `checkpoint.FORMAT` bumped to v3 (see
  judgment calls).

## Frozen seams (tests and implementation are written against exactly these)

checkpoint.py (pure, imported by console):
- `FORMAT = "vehicle.checkpoint.v3"`; `LAG_CEILING_S = 30`; `MIN_CYCLE_NS = 1_000_000`;
  `MAX_CYCLE_NS = 60_000_000_000`.
- `parse_multiplier(text: str) -> Fraction` (ValueError with a sentence; never via float);
  `multiplier_text(m) -> "p/q"`; `clock_section(m, k, n) -> {"m","k","N","burst_bound","lag_ceiling_s"}`;
  `clock_problem(m, k, n, *, tick_hz, max_rate=None) -> (key, sentence) | None`, key in m/k/N.
- `_structure_problem`: checks `clock.m|k|N|burst_bound|lag_ceiling_s` (check names `clock.<key>`) and
  `segments[i]` gains `m` (str), `k` (int), `N` (int).

console.py:
- `Pacer(now_ns=None, sleep=None)`: `.now_ns()`, `.sleep(s)`, `.stopping` (bool), `.stop(signum=None)`.
- `main(argv=None, *, pacer=None)`; flags `--multiplier` (str, dest `multiplier`), `--cycle-ticks`
  (int, dest `cycle_ticks`), `--checkpoint-ticks` (int, dest `checkpoint_ticks`), all `default=None`;
  `--poll` removed. SIGTERM/SIGINT handlers (`pacer.stop`) installed at the top of `main`, restored in
  a `finally`, skipped off the main thread.
- `Executive(..., multiplier=1, cycle_ticks=1, checkpoint_every=None, pacer=None)`; attributes
  `multiplier` (Fraction), `cycle_ticks`, `checkpoint_every`, `pacer`, `clock` (the checkpoint dict),
  `stats` (`CycleStats`), `epoch_ns`, `epoch_tick`, `backstops` (consecutive, carried), `stalls`;
  method `set_clock(m, k, n)` (validates; ValueError).
- `cycle()` returns `[]` without running when the pacer is stopping during the wait; `stats.cycles`
  counts cycles run.
- `LagBackstop(Exception)`: `.lag_ns`, `.consecutive`; raised by `cycle()` before any handle is opened.
- `UncomparableState` raised out of `cycle()` gains `.last_durable_tick`.
- Events (unchained, journaled): `manifest` {event, wall, boot_id, world_id, tick, ended
  ("clean"|"lag_backstop"), clock {m,k,N}, summary, backstops}; `stall` {event, wall, boot_id,
  world_id, tick, kinds [...], late_us, jump_us}; `lag_backstop` {event, wall, boot_id, world_id, tick,
  lag_s, consecutive, action ("stop"|"rebase")}.
- `BACKSTOP_LINE = "[console] lag_backstop lag_s={lag_s} consecutive={consecutive}"` (lag_s an integer).
  Exit `4` (`EXIT_BACKSTOP`).
- `CycleStats`: `.add(lag_us)`, `.cost(cost_us)`, `.summary(tick_us, m, k)`;
  `cycle_summary(lags, costs, *, tick_us, m, k)` (pure); `segment_summaries(record, tick_us)` →
  `{boot_id: summary}` (reader; last cycle's cost unknown). Summary keys: `cycles`,
  `start_lag_us` {p50,p95,p99,max}|None, `cycle_us` {...}|None, `costs_known`, `missed`, `overran`.
  Manifest summary adds `stalls`, `backstops`.
- Record v3: `RECORD_FORMAT = "vehicle.record.v3"`; header + `m`,`k`,`N`; `_ROW_KEYS` + `lag_us`;
  `_CYCLE_ROW_KEYS` = `_ROW_KEYS` + `prev_cycle_us`, `prev_end_lag_us`.
- `resume_executive(..., multiplier=None, cycle_ticks=None, checkpoint_every=None, pacer=None)`;
  `run_inputs["m"|"k"|"N"] = [inherited, named]` (m as "p/q").
- Window: `refresh` (static files + ring rescan owed), `ring` (cached `[(n, name)]` or None),
  `ring_dir` (`(st_dev, st_ino)`); `ring_frames()` stays the scan.

## Judgment calls

1. **`checkpoint.FORMAT` → `vehicle.checkpoint.v3`.** The design adds `m`/`k`/`N` to the segment
   entries (§4, "mirrors them") and validates the clock (§3). `checkpoint.verify` checks the body's
   shape *before* the engine identity, so a v2 checkpoint read by this engine would be refused as
   *corrupt* (and fallen back from) rather than *incompatible*; the module's own rule is "a change to
   how a checkpoint is read is a change of `format`". The design is silent; the module's law decides.
2. **In-process defaults `m = 1`, `k = 1`, `N = tick_hz`** for `Executive(...)` (the `checkpoint_every`
   seam widened to the three); the CLI flags stay `default=None` and required on a fresh serving start.
3. **Two exact row key sets** (`_ROW_KEYS` for every row; `_CYCLE_ROW_KEYS` = that + `prev_cycle_us`,
   `prev_end_lag_us` for a cycle's first row), held to position by the header's `k`.
4. **`run_inputs` keys for a clock change are the checkpoint's clock names** `"m"`, `"k"`, `"N"`, each
   `[inherited, named]`, `m` as `"p/q"` (the design says "as `--max-batch`", whose key is its dest).
5. **Write-ahead only when `k > 1`**: at `k = 1` the single row is the whole cycle, so a k=1 cycle keeps
   exactly today's one append and one `fsync` (existing fsync-counting tests stay valid).
6. **A refusal without a journal** commits nothing and names the cycle's start tick (nothing is
   durable); with a journal, the durable prefix is committed to tick/truth/lineage and named.
7. **`UncomparableState` carries `last_durable_tick`** (and `unwritable` if the suffix append failed)
   rather than a new exception class, so existing `pytest.raises(UncomparableState)` tests hold.
8. **The no-state-dir rebase's `consecutive`** is the segment's backstop count (each rebase stays in
   one segment); the stop path's is the manifest-carried count + 1.
9. **One `stall` event per cycle** with `kinds` (`wait`, `lag_jump`), `late_us`, `jump_us`, `lag_us`;
   the jump is against the previous cycle's start lag, reset to none after a rebase.
10. **The ring reconcile every N ticks runs in the same cycle as the static rewrite** (the cycle after
    the crossing; `Window.refresh` covers both). The design names the trigger but not the cycle.
11. **Manifest fields**: `consecutive_backstops` top level; `summary.backstops` = this segment's count;
    `summary.stalls`; `clock` {m,k,N}; `ended` `clean`|`lag_backstop`. Written after the clean-end
    checkpoint, as the segment's last event. Also printed as one `[console] clock: …` line.
12. **The previous segment's manifest** is found through the boot marker's previous boot id (the boot
    that ended, header or not), reading its journal file backwards past ≤ 64 unchained events.
13. **`clock_problem` names `m` for the wall-time bound**; the CLI refusal is `"<flag> <value>: <sentence>"`.
14. **Individually invalid values** (`--multiplier` unparsable/≤0, `--cycle-ticks`/`--checkpoint-ticks`
    < 1) refuse for every start, before the world loads; missing inputs and the combined bounds refuse
    only on a fresh serving start (a resume validates the resolved triple). `--init` builds with what
    it names, else m=1, k=1, N=tick_hz (it runs no clock).
15. **`Pacer.stop` is the handler**; handlers restored in `main`'s `finally`; "stopped after N tick(s)
    (SIGTERM|SIGINT)" printed only for a signal stop; banners show `m= k= N=` where `poll=` was.
16. **A note must follow its cycle's last row** (`_verified_lines`): implied by the invariant, not
    spelled out in the design; it tightens the reader, never loosens it.
17. **ADR placement**: one consolidated amendment (xlvi) after (xlv), before K, plus inline notes.
18. **`measure_clock`** fills each ring by copying the first real frame `slots` times and moving `seq`;
    cases are separated by `set_clock` (N far away, then N = k) and `_refresh_next`.

## Additional adaptations found while implementing

- `test_a_checkpoints_segment_entry_carries_the_byte_offset_just_after_the_last_line_it_covers`: the
  entry's exact key set gains `m`, `k`, `N` (+ an assertion of their values at the in-process defaults).

- Final review fix: tests 7 and 20 selected events with `journal_events(state, name)[-1]`, which over
  a multi-boot state directory is ordered by boot id (a uuid), not time. A helper `latest_event`
  (newest by `tick`) replaces every such pick; the ADR (xlvi) sentence on the missing-input refusal
  was reworded ("a fresh serving start that does not name all three refuses with exit 3").

## Remaining / handoff notes

- Nothing has been run. First Governance-granted run should be a bounded selection: the 21 new tests,
  the adapted interrupt test, the sixth-file test, the rotation test, the record/checkpoint format tests,
  `test_the_linter_refuses_a_flag_the_checkpoint_remembers_whose_default_is_not_none`, the start-path
  injection test (my `os.fstat` in `Window.open_handles` and `previous_manifest`'s calls add to its
  per-call walk; both are inside handled paths), then the full gate.
- `tools/measure_clock.py`'s new section is unverified code (rules forbid running it); it is the §8 run.
- Chassis §7 is out of scope (the chassis's own work).
- Test 13 gap: see above.


## Tests written (tests/test_vehicle_config.py)

Adaptations: 78 `"--poll", "0"` / `"0.05"` literals → `*CLOCK` / `*SLOW_CLOCK` (module constants
near the top: m=10,k=1,N=50 and m=0.4,k=1,N=50); `start()`'s default extra; the interrupt harness
(`INTERRUPTIBLE_CONSOLE`, now `main(argv, pacer=)` with the injected sleeper, holds polling
`pacer.stopping`, `INTERRUPTIBLE_CLOCK` m=0.2 so a wait certainly falls between cycles, new `batch`
mode, `signal_name=`/`commands=` params); its test renamed
`..._an_interrupt_mid_cycle_completes_the_cycle_first` (graceful completion: tick 3, manifest);
the hand-edit assertion in `test_the_window_s_sixth_file_is_generated_from_the_configuration` (now the
N cadence, N=5); the rotation test (per cycle); format pins (record v3, checkpoint v3, the "flipped"
literal moved to v4); `TICK_ROW_KEYS` (+ lag_us, prev_cycle_us, prev_end_lag_us); hand-built rows and
headers (+ wall fields, + m/k/N).

New (section "#23 (WP08.5): the clock seam", end of file), helpers `InjectedClock`, `paced_executive`,
`charge_publication`, `schedule_oracle`, `nearest_rank`, `summary_oracle`, `clock_start`,
`killed_at_step`, `CLOCK_SCRIPT`, `TRACE_FIELDS`:
1 test_frames_are_exactly_k_ticks_apart_within_a_segment_even_while_the_scheduler_catches_up
2 test_a_command_lands_at_its_cycles_start_tick_at_offset_zero_and_takes_effect_in_the_next_frame
3 test_a_cycle_never_steps_more_than_k_and_a_scheduler_behind_runs_whole_cycles_back_to_back_never_ahead_of_the_clock
4 test_every_row_carries_its_cycles_start_lag_and_its_first_row_the_cost_carried_forward_and_the_reader_summarises_as_the_clean_end_does
5 test_a_serving_start_naming_no_clock_refuses_by_name_and_init_and_plan_need_none
6 test_a_clock_whose_n_is_not_a_multiple_of_k_whose_k_outruns_the_channel_rates_or_whose_cycle_is_out_of_bounds_refuses_at_the_cli_and_in_the_checkpoint
7 test_a_resume_inherits_m_k_and_n_a_named_change_is_journaled_and_kept_and_a_fall_back_keeps_the_newer_policy
8 test_a_checkpoint_ends_every_cycle_that_crosses_a_multiple_of_n_including_after_an_unaligned_resume
9 test_a_crash_inside_a_command_bearing_cycle_publishes_nothing_and_the_resume_owes_exactly_its_first_rows_receipts
10 test_a_deferral_settles_at_the_next_cycles_start_and_after_an_unaligned_resume_at_the_first_boundary_at_or_after_its_due_tick
11 test_the_generated_files_are_rewritten_on_the_staggered_n_cadence_on_a_segments_first_cycle_and_after_a_repair_and_not_every_cycle
12 test_the_linter_refuses_a_clock_flag_whose_default_is_not_none_and_a_clock_section_it_cannot_resolve
13 test_live_equals_replay_at_k_5_including_the_dwell_a_commands_first_step_stamps
14 test_pacing_stays_out_of_the_trace
15 test_a_k_5_world_that_crashes_mid_cycle_resumes_at_k_1_across_an_n_boundary_and_replay_equals_live
16 test_a_k_5_cycle_with_verdicts_reads_back_with_its_notes_verified_and_a_clean_resume_writes_no_duplicate_result
17 test_with_ten_windows_at_k_5_each_window_goes_first_exactly_once_in_ten_cycles
18 test_a_compare_point_refusal_inside_a_cycle_appends_only_the_rows_not_yet_durable_and_stops_at_the_last_durable_tick
19 test_sigterm_during_a_command_bearing_cycle_completes_the_cycle_answers_the_batch_and_ends_cleanly
20 test_a_stall_past_the_lag_ceiling_ends_cleanly_with_exit_4_resumes_on_a_fresh_epoch_and_without_a_state_directory_rebases
21 test_the_telemetry_ring_at_3000_slots_is_kept_in_memory_and_rescanned_only_at_boot_after_a_repair_every_n_ticks_or_when_replaced

Known gap (test 13): no verb was *verified* (nothing may run) to have a target that keeps moving after
its step; the test uses `set_rcs_mode` and pins the stamp (`changed_at_us == 0`, the cycle's start)
and live == replay. The "keeps changing" half of P1-B is exercised only if such a target is in the
script; a reviewer with a slot should confirm or swap in such a verb.

## Verification (the only execution permitted)

`venv3.12/bin/python -m py_compile` on every changed Python file (tools/console.py, checkpoint.py,
check_vehicle.py, measure_clock.py, generate_help.py, generate_readme.py, tests/test_vehicle_config.py):
all compile. `venv3.12/bin/ruff check tools/ tests/ --no-cache`: "All checks passed!".
`ruff format --check`: the same files that the base (`7a87eb8`) leaves unformatted are unformatted
now (console, checkpoint, check_vehicle, measure_clock, generate_readme, the tests); generate_help is
formatted before and after — the repository does not enforce `ruff format` (CONTRIBUTING runs `ruff
check` only), and no file's status changed. No test, no repository program, no systemd, no docker was
run; nothing was committed, stashed or pushed.

## Candidate 1 (2026-10-12): the review round on candidate 0

Reviews: `reviews/impl-c0-codex.md`, `impl-c0-systems.md`, `impl-c0-determinism.md`. Same rules: static
checks only; nothing run, nothing committed. Line numbers are the worktree's after the change.

1. **Ring cache (Codex P2)** — `tools/console.py:5685` (`Window.write_frame`): peek at the oldest, `unlink`,
   pop only on success or `ENOENT`; any other `OSError` sets `ring = None` and re-raises (the window's
   recorded publish failure), so the next publication rescans. Test
   `test_a_frame_the_ring_cannot_delete_is_kept_and_the_next_publication_rescans` (tests :32296).
2. **Backstop journal write (Codex P2)** — `console.py:6623`: the `lag_backstop` `journal_event` in the
   `LagBackstop` handler is guarded; `RecordUnwritable` → `[console] stopped at tick N: …`, exit 3, no
   clean end. Test `test_a_backstop_whose_event_the_record_cannot_take_is_a_named_refusal_and_never_a_traceback`
   (:32342): an ordinary rolled-back failure still exits 4 with its manifest; the unrestorable one exits 3.
3. **Reader invariant (Codex P2)** — `_cycle_row_problem` (`console.py:1574`) takes `cycle_first`
   (`(receipt, lag_us)` of the cycle's first row, tracked in `_verified_lines`, :1907) and refuses an
   interior row that differs. Replay itself is unchanged: every replay reads through `_verified_lines`.
   Mutation test `test_a_cycles_interior_rows_repeat_its_first_rows_receipt_counter_and_lag_and_the_reader_refuses_one_that_does_not`
   (:32386): re-chained suffixes with a raised counter, and with a different lag, are refused at tick 7.
4. **Crashed-segment summary (Codex P2)** — `Record.events` (`console.py:1976`) reads a segment's own
   unchained events (from the file's previous segment end or its start, since a boot can journal a
   stall before its header); `segment_summaries` (:3039) counts `stall` and `lag_backstop` and takes the
   last cycle's cost from the segment's manifest, which now carries `last_cycle_us`/`last_end_lag_us`
   (:3636). Test 4 (:31381) rewritten: the crashed segment's reader summary equals the live executive's
   over the same cycles; the resumed (k=1, 2 s stall) segment's reader summary equals its manifest's
   `summary` exactly, percentiles included. Test 20 (:32160) also asserts reader == manifest for every
   run, the rebase run included. `summary_oracle` now returns the full summary (stalls, backstops).
5. **measure_clock (Codex, systems)** — `tools/measure_clock.py`: (a) a `combined` case (commands in
   every window + static rewrite + checkpoint, N = k); (b) every case uses `--samples` (`sampled`, :443);
   (c) each case reports `over_budget`, and `fits` only if every case's p99 ≤ `FIT_MARGIN` (0.8, :456) ×
   budget, with `worst_us` beside it; (d) `--diode-root`/`--state-root` (:808), each root's device and
   filesystem type and source from `/proc/self/mountinfo` (`filesystem_of`, :415), printed; (e) the §8
   command in the module docstring (:62). Still unexecuted.
6. **Journal-fsync test (Codex P2)** — `test_a_record_that_cannot_be_made_durable_stops_the_run_before_the_cycle_is_published`
   (:26508): main now expects "stopped at tick 0"; in process, tick, truth, lineage head and lineage
   length are unchanged by the failed cycle.
7. **Tests that did not establish their claims** — test 13 (:31850) follows the determinism recipe: a
   pure `console.step` wrapper (no counter) turns `mode` `manual` into `free_drift` on an effect-free
   step; precondition asserted from replay (`mode` at tick 1 `manual`, tick 5 `free_drift`); dwell value
   `["manual"]`, was `["auto"]`. Test 19 (:32137) uses `k = 5` and the new harness mode `step`, which
   holds the second step of the first cycle after its claim; asserts tick 5, rows 1–5, both answered at
   receipt tick 0, manifest, "(SIGTERM)". Test 7 (:31547) adds `--multiplier` alone, `--checkpoint-ticks`
   alone, all three mixed, and `--cycle-ticks 2 --checkpoint-ticks 15`, each valid alone against the
   inherited k=5, N=10 and refused together (no resumed event; the next resume inherits).
8. **Interrupt harness (systems P2-3, Codex P3)** — `INTERRUPTIBLE_CONSOLE` (:29080) injects time as well
   as the sleeper (time moves only in the sleeper, so every wait sleeps and `sleep` mode is reached
   deterministically); new `step` mode; `interrupted_console(..., clock=)`.
9. **Suffix-append failure (Codex P3, systems P3)** — `console.py:4032`: `RecordUnwritable` on rows 2..k
   commits `steps[:durable]` first. Test
   `test_a_record_that_takes_a_cycles_first_row_and_not_the_rest_stops_at_that_rows_tick` (:32420):
   in process tick 6 and row 6's lineage; through `main` "stopped at tick 1".
10. **Second signal (systems P3)** — `Pacer.stop` (`console.py:2930`): a second signal restores the
    default (`default_int_handler` for SIGINT, `SIG_DFL` otherwise) and re-raises it. Test
    `test_a_second_stop_signal_is_the_signals_default_action` (:32487), in subprocesses.
11. **Optional determinism strengthenings** — test 15 (:31965): the killed cycle's command is effectful
    (`set_rcs_mode mode=manual`; tick 0 is now `set_rcs_quad … enable`, because `mode=auto` after `manual`
    would be refused by the 2 s dwell in both runs and carry no effect), and the partial row 6's effect is
    asserted. Test 14 (:31911) also compares `obligations`, `rng`, and segment entries without
    `wall_epoch`, `chain`, `offset`.

Docs: README round entry (review paragraph; figures 537 → **563**) and ADR (xlvi) record the manifest's
last cost, the reader's stalls/backstops, the counter/lag invariant, the second signal.

### Candidate 1 judgment calls
- C1-1. **The manifest carries `last_cycle_us`/`last_end_lag_us`** (design §2: "the last cycle's cost goes
  only in the manifest"), `None` when no cycle ran; the reader adds it, so reader == manifest exactly
  for a clean segment. Test 4 compares the crashed segment with the live executive's summary at the
  crash (same population) rather than with a manifest a crashed segment cannot have.
- C1-2. **A read that begins inside a cycle** (no first row seen) skips the counter/lag check; no anchor
  does so.
- C1-3. **The reader's stall/backstop counts are the journaled events**; a live count whose advisory
  journal append failed would differ (stated; not reachable in the tests).
- C1-4. **measure_clock's roots apply to the clock section only** (the §8 decision); the older sections
  stay in the temporary directory.
- C1-5. **Test 13's target**: `free_drift`, the third enum value, so the moved value differs from both
  the commanded `manual` and the initial `auto`. Unverified that the plant accepts `free_drift` in coast
  over later steps (it is declared valid); the asserted precondition would expose it.
- C1-6. **Test 15's tick-0 command** changed to `set_rcs_quad group=sm_primary state=enable` (dwell 0/0)
  so the effectful `set_rcs_mode` on the killed cycle is not dwell-refused.
- C1-7. **The second-signal test** runs in subprocesses (an in-process SIGTERM default would end the
  worker).

### Candidate 1 verification
`py_compile` on every `tools/*.py` and the test file: all compile. `ruff check tools/ tests/ --no-cache`:
all checks passed. Referee tests 563. Nothing run (no test, no repository program), nothing committed,
stashed or pushed.

## Candidate 2 (2026-10-12): the review round on candidate 1

Reviews: `reviews/impl-c1-codex.md` (request changes), `impl-c1-systems.md`, `impl-c1-determinism.md`
(approve). Same rules: static checks only; nothing run, nothing committed.

1. **Second SIGTERM for PID 1 (Codex P2)** — `Pacer.stop` (`tools/console.py:2955`): a second SIGTERM
   writes `[console] a second SIGTERM: stopping now, without a clean end` to stderr, flushes, and
   `os._exit(128 + SIGTERM)` (143); the docstring says why the default action is not used (a namespace's
   PID 1 ignores an unhandled default). A second SIGINT still raises `KeyboardInterrupt`. Test
   `test_a_second_stop_signal_is_the_signals_default_action` asserts exit 143 and the line (tests :32522).
2. **Manifest-authoritative counts (Codex P2)** — `segment_summaries` (`console.py:3097`): with the
   segment's manifest, `stalls`/`backstops` come from its `summary`; without (crashed), the journaled
   counts, and the summary gains `"counts": "journaled"` (a lower bound). Test 4 (:31437 and the mid-run
   check) expects the marker for the crashed segment and exact manifest equality for the clean one; the
   rolled-back backstop-write test (:32357) now asserts reader == manifest with the event lost; test 20
   unchanged (reader == manifest).
3. **Feasibility gate (Codex P2, systems P3)** — `tools/measure_clock.py`: new `verdict_static` (N far,
   commands + static) and `verdict_checkpoint` (N = k, commands, no refresh) cases;
   `REALISTIC_CASES = quiet, verdict, verdict_checkpoint, verdict_static` (:478); `fits` iff every
   realistic case has max ≤ budget AND p99 ≤ 0.8·budget (:591); `static_and_checkpoint` and `combined`
   reported as `conservative_bound_us`, labelled as not deciding the verdict at N > k. Rule stated in
   the module docstring and `clock_cycle_costs`'s.
4. **Zero-cycle boots (Codex P3)** — chose **writing the header first**: `Executive.open_segment`
   (`console.py:3637`), called on every clean end before the clean-end checkpoint (:6710). A header-only
   segment is already a record shape every reader takes (a torn first cycle), so no rule is added and
   every manifest belongs to a segment; the reader needs no file listing outside the record. Test
   `test_a_boot_that_backstops_in_its_first_wait_leaves_a_header_only_segment_its_manifest_belongs_to`
   (:32532).
5. **Test 13 (Codex P3)** — the wrapper (:31880) reads `mode` as `plant.state_level` does (flat key
   first) and moves both the flat `mode` (when present) and `internal.mode`; still a pure function.
6. **Ring prune failure (systems P3)** — `console.py:5741`: a persistent `unlink` failure drops the cache,
   records a `prune` failure (tick = the cycle's start) and breaks out of the prune; the mirror and
   `pending.json` are still written, their counts from a rescan. The ring test (:32307, renamed) asserts
   the `prune` failure, the same-publication rescan (scans `[4]`), held 4 / losses 0 at tick 4, and the
   prune at tick 5 with no further scan.
7. **Mid-cycle premise (Codex, determinism)** — comment at the skip (`console.py:1597`).
8. **§8 instructions (systems P3)** — module docstring steps (:73): stack stopped, `docker compose run
   --rm --no-deps --entrypoint python3 vehicle …`, free space ≈ frame bytes × 3,000 × 10, keep output,
   remove leftovers; `host_load` (:481: `os.getloadavg()` and MemAvailable) captured before and after the
   section and printed.

README entry (figures 537 → **564**) and ADR (xlvi) updated for 1, 2, 3 and 4.

### Candidate 2 judgment calls
- C2-1. The crashed-segment lower-bound marker is a key `"counts": "journaled"` added to the summary,
  keeping `stalls`/`backstops` names, so a clean segment's summary stays equal to its manifest's.
- C2-2. A manifest whose `summary` counts are not counts falls back to the journaled counts with the marker.
- C2-3. `open_segment` runs on every clean end with a journal (not only backstops): a stop before the
  first cycle has the same gap.
- C2-4. The prune failure's recorded tick is `executive.tick − k` (the cycle's start), like the other
  window failures.
- C2-5. `verdict_static` is measured at N far with the `everything` setup (commands + refresh, no
  checkpoint); `verdict_checkpoint` at N = k with refresh suppressed.

### Candidate 2 verification
`py_compile` on every `tools/*.py` and the test file: all compile. `ruff check tools/ tests/ --no-cache`:
all checks passed. Referee tests 564. Nothing run, nothing committed, stashed or pushed.

## Candidate 3 (owner's own edits, 2026-10-12) — answers the candidate 2 reviews

Determinism and systems approved candidate 2; Codex requested one P2. Small enough that the owner made
them directly; static checks only (py_compile, ruff check: pass); nothing run, nothing committed.
- Codex P2: the second SIGTERM's line is one non-blocking `os.write` to fd 2 (dropped if it would block),
  never a buffered write and flush, before `os._exit(143)` (`Pacer.stop`). Test renamed
  `test_a_second_stop_signal_ends_the_process_now_even_when_stderr_cannot_be_written`; its helper gains a
  `full-stderr` mode (fd 2 dup'd to a pipe nobody reads, filled until it would block) asserting exit 143.
- Codex P3 / determinism P3: `open_segment`'s docstring says a clean-end checkpoint lists the header
  **when one is taken**, and why a zero-cycle resumed boot's unlisted header is consistent.
- Systems P3: `Pacer.stop` docstring no longer claims a signal ends a cycle stuck in an `fsync`; it ends a
  slow stop that is still making progress.
- Codex P3: measure_clock's labels name repairs beside the first cycle and `N = k` for the bound cases.
- Systems P3: the documented §8 command uses `/opt/vehicle/tools/measure_clock.py` (the vehicle stage's
  WORKDIR is `/opt/agent`) and says `--state-root /state` assumes the one-executive shape.
- Candidate 3 confirmation (Codex): code approved; one P3 wording fix applied in place — `Pacer.stop` no
  longer claims only SIGKILL ends a blocked syscall; it says handler execution may be delayed and is no
  guarantee during blocked kernel I/O. Docstring only.
