# #23 implementer report, candidate 1

Received 2026-10-12T10:29:39.243Z; saved verbatim (harness indent removed).

---

## #23 candidate 1: report

Candidate 1 is in the same worktree (`/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock`) and is uncommitted. All eleven items are done. Only `py_compile` and `ruff check` were run; no test, no repository program, no systemd and no docker. Nothing was committed, stashed or pushed. Each fix is recorded in `/home/john/space_chassis/.scratch/wp08-23/IMPLEMENTATION-LOG.md` under "Candidate 1".

### git diff --stat 7a87eb82
```
 README.md                                          |   77 +-
 .../decisions/0002-mission-clock-and-continuity.md |  110 +-
 tests/test_vehicle_config.py                       | 1645 ++++++++++++++++++--
 tools/check_vehicle.py                             |   77 +-
 tools/checkpoint.py                                |  140 +-
 tools/console.py                                   | 1315 +++++++++++++---
 tools/generate_help.py                             |    4 +-
 tools/generate_readme.py                           |    4 +-
 tools/measure_clock.py                             |  309 +++-
 9 files changed, 3314 insertions(+), 367 deletions(-)
```
Referee tests: 537 → 563 (candidate 0 had 558; this round adds 5).

### Fixes (worktree line numbers)
1. **Ring cache.** `tools/console.py:5685` (`write_frame`): a frame leaves the cache only after its `unlink` succeeds or finds it gone. Any other `OSError` clears the cache (`ring = None`) and re-raises, so the window's publication failure is recorded and the next publication rescans.
   - Test: `test_a_frame_the_ring_cannot_delete_is_kept_and_the_next_publication_rescans` (tests:32296).
2. **Backstop journal write.** `console.py:6623`: the `lag_backstop` `journal_event` is now guarded. A `RecordUnwritable` there becomes `[console] stopped at tick N: …`, exit 3, with no clean end.
   - Test: `test_a_backstop_whose_event_the_record_cannot_take_is_a_named_refusal_and_never_a_traceback` (:32342). An ordinary, cut-back append failure still exits 4 and writes the manifest; one that cannot be cut back exits 3 with no traceback.
3. **Reader invariant.** `_cycle_row_problem` (`console.py:1574`) now receives the cycle's first-row `(receipt, lag_us)`, tracked in `_verified_lines` at :1907, and refuses an interior row that differs. Replay always reads through `_verified_lines`, so it is covered without its own check.
   - Test: `test_a_cycles_interior_rows_repeat_its_first_rows_receipt_counter_and_lag_and_the_reader_refuses_one_that_does_not` (:32386). A re-chained suffix with a raised counter is refused at tick 7, and so is one with a different lag; the untouched copy reads.
4. **Crashed-segment summary.** `Record.events` (`console.py:1976`) reads a segment's own unchained events.
   - `segment_summaries` (:3039) counts `stall` and `lag_backstop` events.
   - It also takes the last cycle's cost from the segment's manifest, which now carries `last_cycle_us` and `last_end_lag_us` (:3636).
   - Test 4 (:31381) is rewritten:
     - the crashed segment's reader summary equals the live summary over the same cycles;
     - the resumed segment (k = 1, with a 2 s stall) has a reader summary equal to its manifest `summary` exactly, percentiles, stalls and backstops included.
   - Test 20 (:32160) now also asserts reader == manifest for every run, the rebase run included.
5. **`measure_clock.py`.** None of this has been executed.
   - (a) A `combined` case: commands in every window, the static rewrite and a checkpoint in one cycle (N = k).
   - (b) Every case uses `--samples` (`sampled`, :443).
   - (c) Each case reports its fraction over budget. The verdict is a fit only if every case's p99 ≤ 0.8 × budget (`FIT_MARGIN`, :456); the worst single cycle is reported beside it.
   - (d) `--diode-root` and `--state-root` (:808). Each root's device and filesystem type is printed, using `filesystem_of` (:415).
   - (e) The §8 command is documented at :62: `--windows 10 --full-ring --cycle-ticks 5 --ring-slots 3000 --diode-root /diode --state-root /state`.
6. **Journal-fsync test** (:26508). The `main` assertion is now "stopped at tick 0". In process, the tick, truth, lineage head and lineage length are asserted unchanged by the failed cycle.
7. **Tests that did not establish their claims.**
   - Test 13 (:31850) follows the determinism recipe:
     - a pure `console.step` wrapper (no call counter) turns `mode` from `manual` into `free_drift` on an effect-free step;
     - the precondition is asserted from the replayed truth: `manual` at tick 1, `free_drift` at tick 5;
     - the dwell records `["manual"]`, with `was` `["auto"]`.
   - Test 19 (:32137) runs at k = 5 using a new harness mode, `step`. It holds the first cycle's second step, after the claim. It asserts tick 5, rows 1–5, both commands answered at receipt tick 0, the manifest, and "(SIGTERM)".
   - Test 7 (:31547) adds `--multiplier` alone, `--checkpoint-ticks` alone, and all three mixed, each journaled as its change. It also names `--cycle-ticks 2 --checkpoint-ticks 15`: each is valid alone against the inherited k = 5, N = 10, and together they are refused. The refusal writes no `resumed` event, and the next resume inherits as before.
8. **Interrupt harness** (`INTERRUPTIBLE_CONSOLE`, :29080). It now injects time as well as the sleeper. Time moves only when the scheduler sleeps, so every wait sleeps and `sleep` mode is reached deterministically. It also gains the `step` mode and a `clock=` parameter on `interrupted_console`.
9. **Suffix-append failure.** `console.py:4032`: a `RecordUnwritable` on rows 2..k now commits the durable prefix (`steps[:durable]`) before re-raising.
   - Test: `test_a_record_that_takes_a_cycles_first_row_and_not_the_rest_stops_at_that_rows_tick` (:32420). In process the executive stands at tick 6 with row 6's lineage; through `main` the run stops at "tick 1".
10. **Second signal.** `Pacer.stop` (`console.py:2930`): the second signal restores the default handler and re-raises it.
    - Test: `test_a_second_stop_signal_is_the_signals_default_action` (:32487), run in subprocesses.
11. **Optional strengthenings, both done.**
    - Test 15 (:31965): the killed cycle's command is now effectful, `set_rcs_mode mode=manual`, and row 6's effect is asserted.
    - Test 14 (:31911) also compares `obligations`, `rng`, and the segment entries without `wall_epoch`, `chain` and `offset`.

The README round entry and ADR 0002 (xlvi) are updated to match: the manifest's last cost, the reader counting stalls and backstops, the counter-and-lag invariant, and the second signal.

### New judgment calls
- **The manifest carries `last_cycle_us` and `last_end_lag_us`** (`None` if no cycle ran). This follows design §2: the last cycle's cost goes only in the manifest. With it, the reader's summary of a clean segment equals the manifest's exactly. A crashed segment has no manifest, so test 4 compares it with the live summary over the same cycles instead.
- **A read that begins inside a cycle skips the counter/lag check**, because it has no first row to hold the others to. No anchor starts a read there.
- **The reader counts journaled events.** If an advisory journal append fails, the live count and the reader's count differ; I stated this rather than closing it.
- **`--diode-root` and `--state-root` apply to the clock section only**, the one the §8 decision rests on; the older sections stay in the temporary directory.
- **Test 13 uses `free_drift`.** I could not verify that the plant accepts it over later steps in coast. It is a declared value, and the asserted precondition would expose a failure.
- **Test 15's tick-0 command is now `set_rcs_quad … enable`.** The suggested `mode=auto` after `manual` would be refused by the 2 s dwell in both runs, and would carry no effect.

### Verification
- `py_compile` passes on every `tools/*.py` file and on the test file.
- `ruff check tools/ tests/ --no-cache`: all checks passed.
