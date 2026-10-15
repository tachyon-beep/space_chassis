# #23 implementation review, candidate 1 — systems

Received 2026-10-12T10:32:38.646Z; saved verbatim (harness indent removed).

---

**#23 candidate 1: systems confirmation**

Read only. I checked the frozen diff f73126…ebd0 and the delta 702db4…afe against the worktree `v-23-clock`. Nothing was run, so all of this is from reading the code.

**Verdict: approve.** All five of my candidate-0 findings are resolved in the code. Only P3 notes remain, none blocking: four on how the §8 run is carried out and documented, and one optional ring nicety.

## My c0 findings

- **P2-1 (`measure_clock` sampling and fit rule): resolved.**
  - Every case now runs over `--samples` cycles (default 200) through `sampled()`. Each case reports p50, p95, p99, max and `over_budget`, the fraction of its cycles over budget.
  - The run fits only if every case's p99 is at most 0.8 of the budget (`FIT_MARGIN`); the single worst cycle is reported beside that.
  - The new `combined` case puts a command in every window together with the take barriers, the write-ahead fsync, the static rewrite, the ring rescan and a checkpoint, at N = k (`measure_clock.py:~445-590`).
- **P2-2 (where the measurement writes): resolved.**
  - `--diode-root` and `--state-root` create `mkdtemp` directories on the two filesystems.
  - `filesystem_of` reports each root's device, mount type and source from `/proc/self/mountinfo`, so a run that landed on tmpfs is visible.
  - The temporary directories are removed in a `finally`.
  - These flags apply only to the clock section. That is acceptable, because the §8 decision rests on that section.
- **P2-3 (interrupt harness flakiness): resolved.** `INTERRUPTIBLE_CONSOLE` now injects time as well as the sleeper (`now` moves only inside `sleep`). Every wait therefore sleeps, so the `sleep` point (`claims == 2`) is always reached, whatever the machine's load.
  - The other modes key on claim or step counts.
  - The holds poll `pacer.stopping` in real time.
  - The handler is installed before `start()`.
  - Nothing in the harness depends on timing any more.
- **P3: failure on the append of rows 2..k: resolved.** `_record_cycle` (`console.py:~4036-4043`) commits `steps[:durable]` before re-raising. When row 1 was written ahead, `main`'s message now names the tick recovery will actually reach.
- **P3: second signal: resolved.** `Pacer.stop` (`console.py:2930`) handles a second signal by restoring the default handler (`default_int_handler` for SIGINT, `SIG_DFL` for SIGTERM) and calling `raise_signal`. A second SIGINT becomes a `KeyboardInterrupt`; a second SIGTERM ends the process. Either can land mid-recovery or mid-clean-end, and both of those paths are crash-safe (atomic checkpoint, record cut back). The subprocess test, which asserts exit −15 for SIGTERM, is deterministic.

## The items you asked me to check

- **The ring unlink fix is safe.** Each frame leaves the cache only after its `unlink` succeeds or finds it already gone. Any other `OSError` sets `ring = None` and re-raises.
  - At that point the frame is written, `seq` has advanced and the results are already landed and noted.
  - `cycle()`'s handler for a failed publication records the failure and owes nothing extra.
  - `marked_seq` does not move `seq` a second time, because `seq` is already past the mark.
  - The next `write_frame` rescans.
  - The realistic trigger is an agent putting a directory where a cached frame was (`EISDIR`). That heals itself, because the rescan only counts regular files.
  - Optional P3: an unlink failure that keeps happening would skip that window's mirror and `pending.json` every cycle and rescan its 3,000 entries each time. Skipping the mirror happened before #23 too, since unlink errors propagated then as well. Recording the prune failure and carrying on with the mirror would be gentler.
- **The guarded backstop journal write is correct.**
  - An ordinary append failure that can be cut back is still swallowed by `journal_event` as advisory, and the run still exits 4 with its manifest.
  - Only a `RecordUnwritable` that cannot be cut back becomes `stopped at tick N`, exit 3, with no traceback and no clean end. That is right: it is a real fault, not a backstop.
- **Test 19's new `step` mode is free of flakes and not vacuous.**
  - The hook patches `console.step`, which `advance` looks up as a module global (`console.py:1280`); `advance` is the only caller.
  - A fresh start replays nothing, so the step count is exact. The hold sits at the first cycle's second step, after its claim, and so after row 1 has been written ahead and fsynced.
  - Injected time removes every timing dependence.
  - The assertions cover:
    - ticks 1–5 recorded;
    - checkpoint at tick 5;
    - both commands answered at receipt tick 0;
    - `(SIGTERM)` in the stop message;
    - a manifest showing one cycle.
  - The test exercises the write-ahead row and SIGTERM together.
- **The `combined` case and the §8 command measure the right quantities, conservatively.**
  - Windows sit on the diode image and the record on the state image, with 10 windows, k = 5, full plant rings, 3,000-slot telemetry rings, take barriers, write-ahead and a separate record fsync.
  - `combined` sets static rewrite plus checkpoint plus commands in one cycle. At N = 50 the stagger means steady state never reaches that; it happens only on a segment's first cycle, or at N = k. Requiring its p99 to fit within 0.8 of the budget is therefore stricter than the deployment needs.
  - P3: add verdict + checkpoint and verdict + static cases, which are the realistic worst ordinary cycles at N = 50. Or label `combined` as a conservative bound, so a near miss is not read as infeasible.

## Remaining P3 notes on running §8 (documentation only)

- **Run it with the stack stopped**, for example `docker compose run --rm --no-deps --entrypoint python3 vehicle …`:
  - `mkdtemp` under `/diode` creates a top-level directory there. The aurora-port serve script treats every directory in `/diode` as a slug, and the monitor binds `/diode`.
  - It also writes beside the live `/state`.
  - A run interrupted by a kill can leave either directory behind.
- **Check free space first.** The run temporarily needs about frame bytes × 3,000 × 10 extra on the 2 GB shared diode image.
- **Record the host's load.** An idle host understates the deployment, where ten agents compete for CPU and disk. The 0.8 margin is the only allowance for that, so the record should say how loaded the host was.

## Coverage

- **Read:** in the worktree, `Pacer.stop`, the end of `_record_cycle`, `write_frame`, `run()`'s handling of the backstop and its exits, `INTERRUPTIBLE_CONSOLE` and `interrupted_console`, tests 19 and the second-signal test with its `SECOND_SIGNAL` script, and the `measure_clock` clock section with its doc block. Also the implementer's c1 report and the opening of the delta.
- **Not re-reviewed:** the reader-invariant, crashed-segment-summary and test 4/7/13/14/15 changes, which come from the other reviewers' findings.

## Files

- `/home/john/space_chassis/.scratch/wp08-23/candidate-1/23-candidate-1.diff`
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock/tools/console.py`
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock/tools/measure_clock.py`
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock/tests/test_vehicle_config.py`
