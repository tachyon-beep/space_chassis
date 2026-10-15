# #23 implementation review, candidate 0 — systems

Received 2026-10-12T10:16:09.441Z; saved verbatim (harness indent removed).

---

**#23 candidate 0: systems implementation review**

I reviewed the frozen diff fd81861b…2367 against design 4e8d0d6a…, reading it beside the worktree `v-23-clock` on top of 7a87eb8. This was read only: nothing was run, so the timing and flakiness judgements below come from reading the code.

**Verdict: approve with changes.** The runtime code is correct on every point you asked about. All three P2 findings are in what certifies it, not in the vehicle itself:
- two places where `tools/measure_clock.py` would understate what §8 has to decide;
- one flaky mode in the reworked interrupt harness.

## Checked and correct

**Cycle order at each crash point** (`console.py` `cycle`, `_record_cycle`, `_commit`)
- The order is: wait → open, settle, claim → step into locals → write-ahead row 1 → steps 2..k → group append → commit → root record → publish → checkpoint on crossing → cost carried forward (`_end_cycle`).
- Write-ahead fires only when k>1 and row 1's effects, receipts or `windows` are non-empty. It appends `[row1]` with header-on-first-append, sets `durable = 1`, and the rest go as `rows[durable:]`. Nothing reaches `tick`, `truth` or `lineage` before its rows are durable.
- The six crash points behave as designed:
  - before row 1 is durable: the residual of one step, as before #23;
  - after row 1, before the group fsync: replay reaches a+1 and row 1's receipts are owed;
  - a torn group append: a whole-line prefix replays;
  - after the group fsync: unchanged from today;
  - during publish or notes: unchanged from today;
  - during the checkpoint: unchanged from today.
- A compare-point refusal (`UncomparableState`) appends only rows not yet durable:
  - j=1 records nothing;
  - j=2 on a write-ahead cycle appends nothing;
  - a quiet cycle appends rows 1..j−1;
  - it commits `steps[:durable]`, and `main` names `last_durable_tick`.
- The readers accumulate per cycle. `unwritten_results` skips rows without `prev_cycle_us`, and at a cycle's first row it moves still-pending receipts into the unwritten list rather than dropping them. `_verified_lines` checks the row invariant against the header's `k` and requires each note to follow its cycle's last row.

**The Pacer** (`_await_cycle`, `_due_ns`)
- Due times are integer nanoseconds: `epoch + round(Fraction(Δt·tick_us·1000)/m)`, absolute from the epoch, rounded once.
- The epoch is read on the first `_await_cycle`. That is only ever reached from `run()`, after the genesis checkpoint or the resume and its pre-serve checkpoint.
- Never ahead: the wait loops `while now < due` with each sleep capped at 100 ms, and re-checks the stop flag around each sleep.
- Catching up is by whole cycles: when behind, nothing sleeps and the lag is `now − due(a+k)`.
- On a stop during the wait, `cycle()` returns `[]`, `main` detects that from `stats.cycles` and breaks, and `--cycles` counts only cycles that started.

**Stall and backstop**
- A stall is a sleep at least 1 s late, or a lag jump of at least max(1 s, 10·k·dt/m). The backstop fires when lag exceeds `LAG_CEILING_S`.
- Both are checked before anything is opened or claimed.
- With a state directory: `LagBackstop` leads to the `lag_backstop` event, the clean-end checkpoint, then the manifest last. The run prints the fixed line `[console] lag_backstop lag_s=… consecutive=…` and returns `EXIT_BACKSTOP` (4). The 4 survives the `outcome or 3` path.
- The consecutive count is read back through the boot marker. `previous_manifest` reads backwards over at most 64 unchained events, steps over a torn tail, and any chained line means "no manifest", which resets the count.
- Without a state directory: the epoch is rebased, the event is journaled where a journal exists, the same line is printed, and the run continues.

**Signals**
- Handlers are installed on the main thread just before `start()`, so before recovery. That is after argument parsing and `load_world`, not at the very top of `main`; this is harmless, since nothing is claimed before it.
- They are restored in a `finally`, with `None` mapped to `SIG_DFL`.
- SIGTERM or SIGINT during recovery sets the flag. Recovery finishes, the loop never starts a cycle, and the clean end writes the manifest. The checkpoint is skipped because `last_checkpoint_tick == tick`. So the run ends at the first boundary, as designed.
- The existing `except KeyboardInterrupt` path is safe. It is now dead on the main thread, and it stays the fallback when `main` runs off it, where no handler can be installed.
- A sleep interrupted by the signal resumes for the rest of its time (PEP 475), but that is at most 100 ms.

**The ring cache**
- `open_handles` makes one `fstat` per window per cycle and drops the cache when `(st_dev, st_ino)` changes.
- The directory is scanned only:
  - on a segment's first cycle (`refresh=True` at construction);
  - on the reconcile in the cycle after a crossing (`publish` sets `ring=None`);
  - after a `repair`;
  - when the directory's identity changes.
- `write_frame` pushes the new frame and prunes oldest-first by name; `ring_counts` gives `held` and `losses` with no listing.

**Static-file stagger**
- `_refresh_next` is set in the crossing cycle, and the next cycle refreshes every window. A window that is unhealthy in that cycle keeps `refresh` set until it publishes.
- At N = k, every cycle rewrites the static files and rescans the rings. The design accepts that, and `measure_clock`'s "both" case times it.

## Findings

**P2-1. `measure_clock` caps the clock section at 30 samples per case.**
- Evidence: `clock_cycle_costs` sets `count = min(samples, 30)` (diff, `measure_clock.py` new section), although `--samples` defaults to 200.
- With 30 samples, p99 is effectively the maximum. `worst_us` becomes a worst-of-30, which understates the fsync-driven tail that §8 must set against the 100 ms budget.
- `worst_fits_budget` also compares that maximum to the budget with no margin, while §8 says "with margin".
- Fix:
  - Use `samples` (≥200; about 20 s per case at 100 ms) for at least the quiet and verdict cases.
  - Report the fraction of cycles over the budget.
  - Apply an explicit margin, for example fits only if p99 ≤ 0.8·budget.
  - Document the §8 command as `--windows 10 --full-ring --cycle-ticks 5 --ring-slots 3000`. The ADR's 76 ms figure was taken with the plant ring full; the docstring example omits `--full-ring`.

**P2-2. `measure_clock` cannot put the windows and the state on the deployment's two volume images.**
- Evidence: everything goes under a single `tempfile.TemporaryDirectory(prefix="measure_clock_")`, which only honours `TMPDIR`. The diode and state directories are `tmpdir/clock-diode{n}` and `tmpdir/clock-state{n}`.
- §8 requires the run "on the deployment's volume images". In the deployment, windows sit on the shared diode image and the record on the vehicle's state image, which are separate filesystems. If `TMPDIR` is a tmpfs, every fsync is nearly free and the verdict figure, with its take barriers and write-ahead, means nothing.
- Fix:
  - Add `--diode-root` and `--state-root` flags, or at minimum document `TMPDIR`.
  - Print each root's filesystem type and device in the output, so a run on tmpfs is visible in the record.

**P2-3. The interrupt harness's `sleep` mode is likely to flake under load.**
- Evidence: in `INTERRUPTIBLE_CONSOLE`, the hook fires only for a sleep made while `claims[0] == 2`.
- At m=0.2 and k=1, cycle 3 is due at E+300 ms. If cycles 1 and 2 run long enough (fsync stalls under `-n 8`), the wait before cycle 3 is already past due and never calls sleep. Cycle 3 then claims, the count becomes 3, and the hook never fires again.
- The test then fails with "never reached the point" after its deadline, and the console runs until the `finally` kills it.
- The `claim` and `batch` modes key on claim counts, so they are deterministic.
- Fix:
  - Fire on `claims[0] >= 2 and not ready.exists()`, and assert that the checkpoint tick equals the "stopped after N" tick rather than exactly 2;
  - or lengthen the period (m=0.05, 400 ms) so the slack absorbs load.

**P3s**
- **Stop message after a durable write-ahead row.** If the group append of rows 2..k raises `RecordUnwritable` after row 1 is durable, the exception is not caught in `_record_cycle`, so nothing is committed. `main` then prints "stopped at tick {executive.tick}" (a) while the record holds a+1. Only the message is wrong. Fix: commit `steps[:durable]` before re-raising, or name the last durable tick, as the compare-point path does.
- **No escalation on a second signal.** A repeated SIGINT or SIGTERM does nothing, so a cycle stuck in an fsync can only be killed with SIGKILL. That is fine under docker's grace period, but awkward interactively. Consider restoring the default handler on the second signal.
- **Inode reuse.** If an agent deletes and recreates `telemetry/` between two cycles' opens, the new directory may get the same inode and the identity check misses it. The reconcile every N ticks bounds the error, and pruning a name that is already gone is suppressed. Harmless.
- **Rebase count is not consecutive.** On the rebase path, `consecutive` is the segment's total backstop count (noted by the implementer). Acceptable.
- **Chassis side still open.** The chassis surfaces that read `lag_backstop`, and the per-slug trap that waits for its consoles (my r3 R2 and R3), belong to the chassis delta. This candidate correctly does not touch them; they stay open for the adoption increment.

## Tests

- **Test 19 (SIGTERM): not flaky, not vacuous.**
  - The hook is held at claim 1 until the flag is set, so where it lands does not depend on timing.
  - Without the handler, Python's default SIGTERM action would end the process and the assertions for exit 0, checkpoint at tick 1, both results answered and the manifest would fail.
  - The hook sits before the take, but since the handler only sets a flag, every landing point inside a cycle behaves the same.
- **Test 20 (backstop): deterministic and not vacuous.** It runs on `InjectedClock`, whose time moves only by sleeps and stalls, so `lag_s = 31` is exact. It exercises exit 4, the count across boots (1, 2, reset to 0, 1), the reset when a run ends cleanly, `stall` events of both kinds, a fresh epoch on each resume (`lag_us` 0) and the rebase path.
- **Test 21 (ring): deterministic and not vacuous.** It counts `ring_frames` calls in-process and checks each trigger: first cycle, no rescans on ordinary cycles, a deletion invisible until the reconcile at tick 6, a replaced directory (renamed rather than deleted, so its inode is not freed for reuse), and a repair. It also checks `held + losses == seq`.
- **The interrupt test's `claim` mode: deterministic, and now asserts graceful completion** (tick 3, checkpoint 3, manifest). Its `sleep` mode is P2-3.

## Coverage

- **Read in full:** the `console.py` diff, the tests above, `InjectedClock`, the `measure_clock` diff, and the implementer report.
- **Spot-checked in the worktree:** `Executive`'s state and journal setup, `append_journal_line`, `_line_ending_at`, `_startup_event`.
- **Not reviewed:** the `checkpoint.py` and `check_vehicle.py` diffs beyond the names they export, the ADR and README text, and tests 1–18.
- **Not run:** no tests or tools, per instruction.

## Files

- `/home/john/space_chassis/.scratch/wp08-23/candidate-0/23-candidate-0.diff`
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock/tools/console.py`
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock/tools/measure_clock.py`
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock/tests/test_vehicle_config.py` (interrupt harness about :29064–29178, `InjectedClock` :31184)
