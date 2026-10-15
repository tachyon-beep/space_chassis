# #23 design review r1 — determinism and replay

Received 2026-10-12T05:00:18.699Z; saved verbatim (harness indent removed).

---

## Verdict: request changes

Simulated state and physics replay hold up under the design. Replay applies each row's recorded effects and deltas tick by tick, so it never needs k, and no wall-clock value reaches the plant, the compare-points or the lineage. The problem is the record's non-physics invariants (notes, receipts, owed results) and the dwell clock. The design leaves both unspecified, and the obvious implementation breaks them. P1-A means every resume refuses its record. P1-B is a silent live-versus-replay divergence. Both are fixed in the design text and tests, not in the architecture.

This was a read-only review at vehicle HEAD 7a87eb8. I ran no tests or tools. All line numbers are in `.../b-39-ca87a9/tools/console.py` unless another file is named.

## Findings

### P1-A. A k-row cycle breaks the record's note/receipt binding, so resume refuses the record
- **What the design leaves open:** §4 puts effects on row 1 and marks on row k. It does not say which row carries `receipts`, the `windows` deltas or the `receipt` counter.
- **Evidence:**
  - `_verified_lines` resets `receipts, noted = {row["receipts"]...}, set()` at every tick row (~:1797-1799).
  - A `results_written` note must name `last_tick` and only receipts in `receipts - noted` (~:1777-1788).
  - `_note_window_results` writes the note with `tick = self.tick`, which will be start+k, after the row-k fsync (:3407-3425).
- **Trigger:** any k>1 cycle with a verdict, with receipts on row 1.
- **Consequence:** at row k the receipt set has been reset to row k's (empty). The note is refused ("names results its row did not issue"), `read_record` raises, and the resume refuses. The world cannot continue.
- **Second bug, same cause:** `unwritten_results` (:2462-2490) flushes `pending` into `unwritten` at every tick row. With the verifier fixed, row 1's receipts are declared unwritten as soon as row 2 is read. Every resume then re-owes every receipt after the snapshot (filter at `_resume`, ~:5218) and relies on the bounded on-disk scan to avoid duplicate results.
- **Putting receipts on row k instead is worse:**
  - A crash after rows 1..j (j<k) leaves the effects durable and replayed while the receipts, window deltas and counter are lost. The command took effect with no receipt to owe, which breaks "exactly one result", and counters can repeat.
  - `unwritten_results` derives a receipt's tick as `row["tick"] - 1` (:2486). On row k that gives the wrong receipt tick.
- **Fix:**
  - State as an invariant that row 1 carries `effects`, `receipts`, the `windows` deltas and the new `receipt` value. Rows 2..k carry `effects: []`, `receipts: []`, `windows: {}`, and only row k carries `published`.
  - The reader verifies that invariant. Within a cycle, `_verified_lines` and `unwritten_results` keep accumulating the cycle's receipts and reset only at the cycle's first row.
- **Does the record need k or cycle boundaries?** Physics replay does not: effects sit on rows keyed by tick. The verifier, `unwritten_results`, the "effects only on the first tick" check and the crashed-segment lag reader all do.
  - The `resumed` event's `run_inputs` cannot supply k: `_startup_event` (:1801-1803) drops it from the trace, unchained.
  - Put `m`, `k`, `N` in the chained segment header. Boundaries are then `first_tick + i·k` within a segment, which handles a k=5 → k=1 resume.
  - Mirror them in the checkpoint's `segments` entries, because an anchored read rebuilds the header from that entry (:2096).
- **Format bump:** `_HEADER_KEYS` and `_ROW_KEYS` are exact-set checks (:1353-1356), so this and `lag_us` require `RECORD_FORMAT` v3 (:315).
  - Reading v2 records again is not an issue. `engine_identity` hashes the engine tools (`tools/checkpoint.py:176-198`), so a v3 engine already refuses a v2 world's checkpoint.
  - Update the hard-coded `"vehicle.record.v2"` in `tests/test_vehicle_config.py:26412` and the row builder in `tools/measure_clock.py:371-379`.
- **Add tests:**
  - A k=5 cycle with verdicts reads back, its notes verify, and `unwritten_results` is empty after a clean cycle.
  - After a crash with rows 1..j durable, exactly row 1's receipts are owed.

### P1-B. Dwell must be computed against the first tick's before/after, or live and replayed state diverge silently
- **How the two paths compute it:**
  - Live: `_report_effect(verdict, before, self.truth)` (:3147-3148, :4097-4118) stamps `now_us = verdict.tick*tick_us + offset` and calls `dwell_after_effect(before, after)`. That function restarts the dwell clock only where a target's value changed, and stores `value_of(after)` (:1274-1296).
  - Replay calls it with the row's tick-1 stamp and the truth before and after that row's single step (:2418).
- **Trigger:** an implementation that steps k ticks and then reports the effects, against start truth versus truth at start+k. Any target state that keeps changing after tick 1 then gives a different "changed" set or stored value. Moving effects to row k would also shift `now_us` by (k−1)·tick_us.
- **Consequence:** `dwell` is checkpointed (`tools/checkpoint.py:306`) but is not in `state_hash`. Compare-points and lineage still agree, so replay passes, but a resumed world's dwell guards differ from the world that never stopped. "Resume continues the same world" fails silently.
- **Gap in existing coverage:** the only live-versus-replay body check, `replayed.body["executive"] == live["executive"]` (`tests/test_vehicle_config.py:25897`), runs at k=1. Design §6 keeps in-process tests at k=1.
- **Fix:**
  - Specify: step tick 1 with the effects, run `_report_effect` and dwell on that step's (before, after), then step the remaining k−1 ticks with no effects.
  - Add a k=5 test, using a verb whose target keeps changing after the step, that asserts the replayed body's `executive` and `windows` equal the live checkpoint's.

### P2-A. A refused state partway through a cycle is unspecified
- Today `advance` commits nothing until the step is accepted (:1230-1241, :3142-3150), and `run` exits 3 at the last consistent tick (:5779).
- With k steps before one append, a refusal at step i leaves ticks 1..i−1 stepped in memory, consoles already claimed, and nothing recorded.
- **Fix:**
  - Advance into locals.
  - On a refusal at step i, append rows 1..i−1 in one fsync (row 1 holds the receipts, so they are owed on resume), then stop. Never commit `self.tick`, `truth` or `lineage` past the recorded rows.
  - Extend `test_a_state_the_compare_point_refuses_stops_the_run_at_its_last_consistent_tick` to k>1.

### P2-B. `lag_us` in the record is compatible with the hash rules, with conditions
- `record_chain` hashes the whole canonical row (:1177-1183), so the chain becomes wall-dependent. That is acceptable:
  - The chain is per-record integrity, and the header's `wall_epoch` is already chained (:3481).
  - Replay holds rows only to `state_hash` and `lineage`, and `lineage_link` covers only the digest and effects (:1241).
  - Nothing compares chains across runs; the :26414 test only uses them as forbidden strings.
- **Conditions:**
  - Compute `lag_us` with integer arithmetic (`time.monotonic_ns()`, integer-ns due times) and clamp it to ≥ 0. The reader should validate it as `_count` (:1364).
  - A float, or a −1 µs rounding artifact, written by the writer would be refused by the reader at the next resume, leaving the world unresumable.
  - Document in the record comment (:1117-1124) that `lag_us` is excluded from run equivalence.
  - Forward note for #26: shedding decisions must be recorded (marks), never re-derived from `lag_us`.

### P2-C. No test proves pacing stays out of the trace
- Tests 3 and 4 check pacing and that lag is recorded, but nothing shows the trace is unaffected by pacing. Source currently supports that: `capture_state` takes named keys only, and `clock` only `CLOCK_INPUTS` (`tools/checkpoint.py:273-318`).
- **Add:**
  - The same per-cycle ingress script under two schedules, unpaced and with injected slow cycles that force back-to-back catch-up. Every row must be identical apart from `lag_us`, and the checkpoint bodies identical apart from `segments[*].wall_epoch`, chain and offset.
  - A k-independence test: a k=5 world crashes after rows 1..j of a cycle and resumes with k=1 across an N boundary. `replay_record(genesis, whole record).body` must equal the live checkpoint's `executive` and `windows`.

### P2-D. Arbitration rotation is coupled to k (fairness, not replay)
- `order()` rotates by `tick % n` (:3051-3062), evaluated at cycle starts.
- With k=5 and n=10 (the fleet roster) only offsets {0, 5} ever occur. With n=5 one window is always first. That regresses ADR choice A's "no name holds a permanent priority".
- Not a replay hazard: arbitration outcomes are recorded, and validation is not re-run.
- **Fix:** rotate by cycle, e.g. `(cycle_start_tick // k) % n`, which stays consecutive after an unaligned resume. Test with gcd(k, n) > 1.

### P3
1. **Deferrals:** `due = self.tick + 1` (~:4043) always falls inside the current cycle, so every deferral settles at start+k, while the verdict text says "due at tick start+1" (~:4058). Reword the text, or set `due = start + k`.
2. **Design §4's "one shorter gap" across a resume is wrong:** after a partial cycle the gap is j + k′, which is longer. Correct the text and test 1.
3. **Static HELP/README rewrites** must use the same crossing rule as checkpoints. Otherwise, after an unaligned resume, `tick % N` never matches a cycle end and the files are never rewritten again.
4. **The lag reader** needs `m` for the missed-deadline threshold of `dt/m` (P1-A puts `m` in the header). Use nearest-rank percentiles so per-tick and per-cycle summaries agree for whole cycles. A crashed segment's last cycle may have fewer than k rows.

## The caller's questions, answered directly
- **Wall-clock leaks:** none into truth, compare-points, lineage or validation. `lag_us` reaches only the chained row bytes (acceptable, P2-B). Cycle boundaries and the number of catch-up cycles decide which tick an ingress lands on. That is the input boundary and it is recorded, not a leak.
- **Is replay independent of k?** Yes. Replay is per row, and segment joins accept unaligned ticks (`concatenated`, :2229-2262). The record's verifier and `unwritten_results` are not, which is P1-A.
- **Deferral settlement as a function of k:** not a replay hazard. Replay applies the recorded `deferred_removed`/`deferred_added` deltas, verdicts and effects, and never re-runs `_settle` (:3612-3650). Expiry is unaffected: the smallest `maximum_queue_age_s` in the corpus is 10 s, against at most 0.08 s of extra delay.
- **Crash between rows of one cycle:** sound as designed, provided row 1 carries the receipts and deltas (P1-A). It is one write plus one fsync, and a failed append is cut back by `append_or_restore` (~:3510). A power-loss prefix of chained rows replays to start+j with nothing published. The resume's pre-serve checkpoint at an unaligned tick is covered by test 8.
- **Does the record need cycle boundaries or k?** Not for physics replay. Yes for the verifier, `unwritten_results` and the lag reader (P1-A).
- **Is `lag_us` compatible with the identity/hash rules?** Yes, with the conditions in P2-B.

## Not done
I ran no checks. All findings come from reading source, so each needs the named test to confirm it against the implementation.
