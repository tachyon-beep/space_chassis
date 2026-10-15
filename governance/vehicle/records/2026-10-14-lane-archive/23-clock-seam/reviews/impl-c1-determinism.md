# #23 implementation review, candidate 1 — determinism and replay

Received 2026-10-12T10:31:43.660Z; saved verbatim (harness indent removed).

---

## Verdict for #23 candidate 1 (determinism and replay): approve

My P2 on test 13 is resolved, both optional items are done, and the new check on rows inside a cycle is sound for anchored reads. Nothing blocks.

This was read only. `git diff | sha256sum` in the worktree matches the frozen `f73126562a…ebd0`. I ran no tests, so every "would fail" below comes from reading the code.

## P2: test 13 now has teeth — resolved
**The wrapper is pure** (`tests/test_vehicle_config.py:31850ff`).
- `drifting(world_, truth, dt, rng, effects)` reads only its arguments. When there are no effects and the incoming `internal.mode == "manual"`, it returns the real step with `mode` set to `free_drift`.
- It has no counter, so the live run and replay compute the same thing.
- It replaces `console.step`, which both the live cycle and `replay_record` reach through `advance`.

**The "report after the loop" mutation would fail it twice.**
- Live would compare the start truth (`auto`) with tick 5 (`free_drift`) and record `dwell["mode"]["value"] == ["free_drift"]`.
- Replay compares across row 1 only and records `["manual"]`.
- So both `executive.dwell["mode"]["value"] == ["manual"]` and `replayed.body["executive"] == live["executive"]` would fail.
- Moving the effects to row k instead is still caught by `changed_at_us == 0` and by the replay-equals-live comparison.

**Will the plant carry `free_drift` over later steps in coast?** Very likely, and if not, the test fails loudly rather than passing vacuously.
- `rcs.mode` is declared `method: discrete`, `unit: "enum[auto,manual,free_drift]"`, `moved_by: ["command:set_rcs_mode"]` only (`domains/rcs/components.yaml:519ff`). No logic or event moves it, so nothing in a step should rewrite it.
- If the plant did revert it, the wrapper would fire again each tick. The asserted precondition (replayed truth `manual` at tick 1, `free_drift` at tick 5) would then fail by name.
- If injecting `free_drift` broke something else in coast (an `Unconfigured` or `UncomparableState` error), the test would also fail rather than pass.
- One residual unknown, which only running the test can settle: whether the attitude loop accepts `free_drift` in `translunar_coast` without raising.

**The later script entry cannot disturb it.** `CLOCK_SCRIPT` index 5 commands `set_rcs_mode mode=auto` at tick 25. `dwell_refusal` (`console.py:4439ff`) refuses it on time alone: held 0.5 s < `min_on_s: 2`, whatever the current value. So the `changed_at_us == 0` and `["manual"]` assertions hold in both runs.

## Optional items — done
**Test 15** (`:31965ff`):
- The killed cycle carries `set_rcs_mode mode=manual`, which is accepted because `mode` has never changed and so has no dwell floor.
- The test asserts that row 6 holds the `set_rcs_mode` effect. The k=1 oracle applies the same command at tick 6, so the per-tick compare-points and lineage agree.
- That now checks where an effect lands in a partial write-ahead cycle.
- The tick-0 change to `set_rcs_quad … enable` is fine: the effect and lineage are identical in both runs, and the reason given (`mode=auto` after `manual` would be refused by the 2 s dwell) is correct.

**Test 14** (`:31911ff`):
- It now also compares `obligations` and `rng`, plus each segment entry without `wall_epoch`, `chain` and `offset`.
- It asserts the segment list is non-empty, so the comparison cannot pass vacuously.
- Both runs use the same `m`, `k` and `N`, so the entries' clock fields must match.

## The new check on rows inside a cycle — sound
**What it checks** (`console.py:1574-1603`):
- `_cycle_row_problem` refuses a row inside a cycle whose `(receipt, lag_us)` differs from that cycle's first row.
- `_verified_lines` sets `cycle_first` at each first row (`:1907`) and clears it at each header (`:1854`).

**The writer always satisfies it.** Every row of a cycle is built from the same `self.receipt` and the same `lag_us` (`_record_cycle`, `:3990ff`). No receipt is drawn during stepping, and the write-ahead row 1 uses the same variables.

**The skip for a read that starts mid-cycle cannot be reached in practice.** A read only starts at a checkpoint's anchor, and anchors are always at a cycle boundary:
- the genesis checkpoint is at tick 0;
- the cadence checkpoint and the clean end are taken with `in_cycle` false;
- SIGTERM completes the cycle first, and the backstop fires before anything is claimed;
- the checkpoint a resume takes before serving anchors at the end of the dead segment, after which only a new header can follow, and that header resets the state.

So every anchored read meets a first row before any row inside a cycle, and the check runs in full.

**Even if one did start mid-cycle,** the skip would drop only this cross-row consistency check. The chain still covers every line. Replay still refuses a receipt counter that goes backwards (the `row["receipt"] < receipt` check). The rule that rows inside a cycle carry no effects, receipts or deltas still applies.

**Optional hardening (P3):** a read that starts mid-cycle in a segment with rows after it is not something this writer produces. A future revision could refuse it by name instead of skipping the check. That is optional, not needed.

## Also checked
**Suffix append failure** (`:4026-4032`): a `RecordUnwritable` on rows 2..k now commits exactly the durable prefix, `steps[:durable]`, before re-raising. Memory then matches what recovery will reach.
- A failure of the write-ahead append itself is not caught. It commits nothing, which is correct: `append_or_restore` has cut the row back.
- The refusal path for a compare-point failure partway through a cycle (`:4016-4024`) is unchanged and still correct.
