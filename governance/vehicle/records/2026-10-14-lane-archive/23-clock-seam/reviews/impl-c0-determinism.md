# #23 implementation review, candidate 0 — determinism and replay

Received 2026-10-12T10:15:50.923Z; saved verbatim (harness indent removed).

---

## Verdict for #23 candidate 0 (determinism and replay): approve with changes

Every determinism and replay finding from my design reviews is implemented correctly in the code. I found no defect in the record, replay or resume paths. The one required change is to test 13: as written it cannot catch the regression P1-B exists to prevent. Two other test suggestions are optional.

I read the worktree at `.../scratchpad/v-23-clock`; `git diff | sha256sum` matches the frozen `fd81861b…2367`. I ran no tests. To scan the corpus YAML for which states commands move, I ran one standalone `python3 -I` script that only reads files.

## Design findings, checked in the code

**Row-1 invariant and reader accumulation (P1-A): implemented.**
- **Keys:** a first row uses `_CYCLE_ROW_KEYS = _ROW_KEYS | {prev_cycle_us, prev_end_lag_us}` (`console.py:1393-1397`).
- **Position check:** `_cycle_row_problem` (`:1617-1640`) places each row on the header's grid, `first_tick + i·k`. Rows 2..k may not carry effects, receipts or deltas, and only the last row may carry `published`.
- **Verifier:** `_verified_lines` resets its receipt set only at a cycle's first row (`:1883-1887`), checked after `_cycle_row_problem` (`:1878`).
- **Owed results:** `unwritten_results` moves pending receipts to the unwritten list only at a first row and skips rows 2..k (`:2586-2598`). Pending receipts are moved, never dropped, so a failed publication stays owed.

**m, k, N at all three propagation sites: implemented.**
- `_append_record` writes them into the segment entry and header (`:4064-4078`), with `m` as `"p/q"` from `clock_section`. They are typed in `_header_problem` through `_segment_clock_problem` (`:1609-1615`).
- The anchored read rebuilds them from the checkpoint entry and validates them (`:2189-2201`).
- Replay copies them into the segments it adds (`:2556-2561`).
- The checkpoint validates its segment entries (checkpoint.py diff, the `segments[index]` check).

**Dwell stepping rule (P1-B): implemented.** `_record_cycle` (`:3906-3922`) steps tick `a+1` with the effects and calls `_report_effect(verdict, before, truth)` against that one step. The other `k−1` steps get `[]` effects. The stamp is still `verdict.tick·tick_us` = `a·tick_us`, which equals replay's `(row_tick − 1)·tick_us` on row 1 (`:2418` equivalent).

**Refusal partway through a cycle (P2-A): implemented.**
- `except UncomparableState` (`:3942-3952`) appends only `rows[durable:]`. That is rows `1..j−1` on a quiet cycle, `2..j−1` after a write-ahead, and nothing at `j=2`.
- `_commit` runs only on durable steps, `last_durable_tick` names the right tick, and a failed suffix append keeps the durable prefix.
- At `j=1` the step raises before `_report_effect`, so dwell is untouched.
- `run` returns 3 and never cycles again in the same segment (`:6545-6555`), so the grid cannot be broken by a continued run.

**`lag_us` and `prev_*` (P2-B): implemented.**
- All are `max(0, …) // 1000` on integer ns (`:3492`, `:3532-3538`, `:3593`). The reader validates them as counts (`:1517-1518`).
- Nothing in the window or publication code reads them; no occurrence after `:4100`. `capture_state` has no wall field.
- They appear in rows (and so in the chain), and in unchained `stall` and `manifest` events, which `_startup_event` skips.

**Pacing kept out of the trace: implemented.**
- `_await_cycle` returns only `(start, lag)`. The stall and backstop checks run before any handle is opened or console claimed (`:3466-3496`).
- With no pacer the clock is always on time, `(0, 0)`.
- The cadence uses the crossing rule (`:3700`), which depends only on ticks.

**Rotation by cycle (P2-D): implemented** as `(self.tick // self.cycle_ticks) % n` (`:3400-3416`). The documented "one window may go first twice after an unaligned resume" is acceptable: outcomes are recorded, and the partial cycle published nothing.

**Deferral due tick: implemented.** `due = self.tick + self.cycle_ticks` (`:4641`), and the text says "(later across a restart)" (`:4656`). This is a live decision and is recorded, so it is not a replay hazard.

**Write-ahead (design §4): implemented.** Row 1 is appended alone when `k > 1` and its effects, receipts or `windows` are non-empty (`:3936-3938`). This covers arms, spend and counter-only deltas, as my r2 P3-4 asked.

**Clock inheritance on resume:** the clock is resolved after replay, preferring the newest replayed segment's header over an older checkpoint's `clock` (`:5880-5899`). This resolves my r2 P3-5.

## Judgment calls

**Checkpoint format v3 (call 1): correct.** `verify` checks `format` first and refuses with `CheckpointIncompatible`, which `choose_generation` never falls back from (checkpoint.py `:1017ff`, `:1109-1110`). Without the bump, a v2 body would fail the new shape check as *corrupt*, because its segment entries lack m/k/N. That shape check runs before the engine-identity check, so the resume would fall back, with the misleading "rejected" handling. The bump is required, not just tidy.

**A note must follow its cycle's last row (`:1863-1864`): sound.**
- Notes come only from `Window.publish` for the current cycle's verdicts (`:5428-5434`), after all k rows are durable and committed, with `tick = self.tick = a+k`. Obligations republished at resume write no note.
- At `k=1` the rule is always true.
- A partial cycle never publishes, so no legitimate record breaks the rule.
- Checkpoint anchors fall at cycle ends, after that cycle's notes. The resume's own checkpoint at an unaligned tick anchors at the dead segment's end, after which only a new header follows. So anchored reads cannot see a note placed against the rule.

## Would tests 9, 13, 14, 15 and 16 catch a regression?

**Test 9 (`tests/test_vehicle_config.py:31642`): yes.**
- Without write-ahead, the kill at step 2 or 4 leaves ticks 1..5 and the `== list(range(1, 7))` assertion fails.
- It also pins that the receipts are on row 6, nothing is published, each result is written exactly once, and the stamp is tick 5.
- One per-row-reset regression in `unwritten_results` would still pass here, because receipts are moved, not dropped. Test 16 catches that one.

**Test 16 (`:31951`): yes.** If the verifier reset at every row, `read_record` would refuse. If `unwritten_results` reset at every row, `unwritten_results(record) == []` would fail. The note ticks are pinned to {5, 10, 15, 20}.

**Test 14 (`:31851`): yes, and the comparison scope is right.**
- World and boot ids are pinned. The comparison covers `TRACE_FIELDS` per row plus the body's `executive` and `windows`.
- The paced run has a real 2 s stall and charged costs, and it asserts it was slow, so the test cannot pass vacuously.
- Any path from lag or cost into ticks, effects, receipts, marks or state would fail it.

**Test 15 (`:31897`): yes.**
- A k=1 oracle's per-tick compare-points must equal those of a k=5 world killed in its second cycle (record ends at tick 6) and resumed at k=1 to tick 20.
- Whole-record replay from genesis must equal live, and the segment header k values must be [5, 1].
- Effects on row k instead of row 1 would break tick 1's compare-point.

**Test 13 (`:31816`): partly.**
- It catches effects moved to row k: replay would stamp `(k−1)·tick_us` and the `executive` equality fails. It also pins `changed_at_us == 0`.
- It cannot catch the P1-B regression itself: dwell computed against the truth `k` steps on, with effects still on row 1. If the command's target holds its value from step 1 to step k, both computations give the same moved set and value.
- `set_rcs_mode` moves `mode` and is commanded only. The script's `set_rcs_quad` targets `rcs.thruster_valve`. That state is also moved by `logic:the allocator commands each valve from the requested wrench` (`domains/rcs/components.yaml`), but with no wrench requested in coast it very likely stays still. The scan found only one other state moved both by a command and by something else: `structure.pyro_fired` (event plus `execute_event`), which latches.
- So no verb in the current script reliably keeps changing its target. This confirms the implementer's noted gap.

## Findings

**P2 — test 13 is vacuous for the regression it exists to catch.**
- **Fix:** make the command's target change on a later step of the same cycle, the same way live and in replay.
- **How:** patch `console.step` (both live and replay reach it through `advance`; `killed_at_step` already patches it, `:31629-31639`) with a wrapper that is a *pure function of its arguments*:
  - When the effects are empty and the truth's `mode` equals the value just commanded (`manual`), it returns the real step with `mode` set to another valid value of its enum.
  - So step 2 of the cycle moves the target and steps 3..k hold it.
  - Do not key it on a call counter, which differs between live and replay.
- **Precondition:** add an assertion that the record's truth at tick `a+1` and tick `a+k` differ in that target, so the test cannot quietly become vacuous again.
- **Mutation check:** report against `truth` after the loop instead of after step 1. The `replayed.body["executive"] == live["executive"]` assertion should then fail on `dwell["mode"]["value"]`.
- **Alternative:** if a slot is available, check whether `set_rcs_quad` with an attitude command under the allocator really moves `thruster_valve` within 4 ticks. Still assert the precondition either way.

**P3 (optional)**
1. **Test 15:** the command on the killed cycle is `zzz_on_the_killed_cycle`, a refused non-verb, so the write-ahead partial cycle carries a receipt but no effect. Using an effectful command such as `set_rcs_mode mode=auto` would check effect placement on a partial write-ahead cycle against the k=1 oracle; the oracle also applies it at tick 6, so the expectations still hold.
2. **Test 14:** could also compare the body's `obligations`, `rng`, and `segments` without `wall_epoch`, `chain` and `offset`, which closes the remaining checkpoint fields wall data could reach. No current leak exists.

## Not verified
- No test was run. All "would catch" judgments come from reading the code and the tests.
- Whether the allocator moves `thruster_valve` after the step is unverified, as stated above.
- `segment_summaries` and the percentile reader are outside this review's determinism scope. They are wall data and no simulated state depends on them.
