# #23 design review r2 — determinism and replay

Received 2026-10-12T05:59:52.906Z; saved verbatim (harness indent removed).

---

## Verdict for #23 confirmation round r2: approve with changes

Every determinism and replay finding from my r1 review is resolved in the design. The new write-ahead row 1 keeps the record replayable and verifiable. Both clean ends keep "resume continues the same world" true. One new P2 remains: the design asks every row to carry a cost (`cycle_us`) that does not exist yet when the row is written. There are also five P3 precision items. None of these needs another full round; they can be folded into the implementation plan.

This was read only. I checked `DESIGN.md` (sha256 c0fcfe06…3855, matches) against `tools/console.py` at 7a87eb8 and ran no tests or tools. All line numbers below are in `console.py` unless another file is named.

## r1 findings, confirmed

**P1-A (receipts and notes across a cycle's rows): resolved.**
- §4 states the row-1 invariant: effects, receipts, `windows` deltas and the receipt counter go on row 1. Rows 2..k carry empty lists and objects, and only the last row carries `published`. The reader verifies all of this.
- `_verified_lines` and `unwritten_results` now reset their receipt sets at a cycle's first row, worked out from `first_tick + i·k`. Today both reset at every row (~:1797-1799 and :2483-2487). The note's tick check (~:1780) still holds because the note follows row k.
- `m`, `k` and `N` go into the chained segment header and are mirrored into the checkpoint's segment entries, which is needed because an anchored read rebuilds the header from that entry (:2096).
- The record format becomes v3, as `_HEADER_KEYS` and `_ROW_KEYS` are exact sets (:1353-1356). The v2 point is correct: `engine_identity` hashes the engine tools (`tools/checkpoint.py:176-198`), so a v2 world never reaches a v3 reader.
- Receipts on row 1 keep `row.tick − 1` (:2486) and replay's dwell stamp (:2418) correct.
- Tests 9 and 16 cover it.

**P1-B (dwell computed against the wrong step): resolved.** §1 says: step `a+1` with the effects, run `_report_effect` and the dwell bookkeeping on that step's before and after, then take the k−1 steps that carry no effects. That is replay's per-row order (:2410-2418 against :4110-4111). Test 13 runs at k=5, uses a target that keeps changing after its step, and checks the whole `executive` (including dwell) and `windows`. That closes the k=1-only gap in `tests/test_vehicle_config.py:25897`.

**P2-A (compare-point refusal partway through a cycle): resolved.** Stepping goes into local variables. A refusal at step j>1 appends the j−1 completed rows, commits nothing past them and exits 3. A refusal at step 1 records nothing, as today (:3142-3150, :5779). Test 18 covers it. One detail on write-ahead cycles is in P3-4.

**P2-B (wall data in the rows): resolved for `lag_us`.** It is an integer from `monotonic_ns`, clamped at 0, and validated as a count (`_count`, :1364). It enters only the chain (`record_chain`, :1177-1183, which already chains the header's `wall_epoch`). It never enters `state_hash`, lineage or any replay decision, and #26 is told to record its decisions rather than re-derive them from lag. `cycle_us` meets the same type rules but cannot be filled in as specified; see the new P2 below.

**P2-C (proving pacing and k stay out of the trace): resolved by tests 14 and 15.** Both need a comparison scope stated; see P3-2.

**P2-D (arbitration rotation): resolved.** The rotation becomes `(a // k) % n`. At k=1 it equals today's `tick % n` (:3051-3062). With n=10 and k=5 every window goes first once in ten cycles, and it advances by one after a resume at an unaligned tick. Test 17 covers it. Arbitration outcomes are recorded, so this has no replay effect.

**P3 items: resolved.**
- **Deferral due tick:** a deferral is now due at `a + k`, and its text says so (replacing `due = self.tick + 1`, ~:4043). After a resume that changes k at an unaligned tick, settlement lands at the first cycle start at or after the due tick. That is a live decision, recorded through `deferred_added` and `deferred_removed`, so it is not a replay hazard.
- **Static files:** they use the crossing rule, staggered one cycle after the checkpoint, plus a segment's first cycle and the cycle after a repair.
- **Lag reader:** it uses nearest-rank percentiles over cycles, treats a partial final cycle as one cycle with its rows, and reads `m` from the header for the missed-deadline threshold.

## Write-ahead row 1 with a crash before the rows-2..k fsync: sound
- **The record:** the segment ends after row 1, a partial final cycle the reader must accept because rows 1..k−1 carry `published == {}`.
- **Replay:** row 1 replays at tick `a+1` with its effects and the dwell stamp `a·tick_us`. Nothing was published, because publication follows the last fsync.
- **What is owed:** `unwritten_results` owes exactly row 1's receipts, and their receipt line names tick `a`, as the live receipt would have.
- **The next segment:** it begins at `first_tick = a+1`, and `concatenated` accepts the unaligned join (:2229-2262).
- **Overall:** what an agent sent is durable before the steps that carry no effects.
- **Coverage:** test 9 (j in 1..k−1).

## The two clean ends: "same world" holds
- **SIGTERM / SIGINT:** the handler only sets a flag, which the loop reads at cycle boundaries. Nothing is raised in the middle of a cycle, which is better than today's `KeyboardInterrupt` path (:5776-5778). The current cycle completes, and the clean-end checkpoint is taken with `in_cycle` false, at a cycle boundary. Test 19 covers it.
- **Backstop:**
  - It writes a checkpoint at a cycle boundary and exits 3; the resume replays from it and starts a fresh epoch. No ticks are dropped and the epoch is not state.
  - Its events (`lag_backstop`, `stall`, the manifest) are unchained startup-style lines that the trace reader skips without advancing the chain (`_startup_event`, :1801-1803, as `checkpoint_failed` is today), so they cannot break verification.
  - This holds only if the check runs before the claim; see P3-1.

## Findings

### P2 (new): `cycle_us` cannot be written into its own cycle's rows
- §2 defines `cycle_us = end − start` and says each of the cycle's k rows carries it, with "overran" meaning cost over `k·dt/m`, the completion deadline.
- Every row is fsynced before publication (the J rules, unchanged by §4), and row 1 is written ahead of steps 2..k. So the cycle's end is unknown when any of its rows is written.
- **The risk:** to fill the field, an implementer may move the row fsync after publication. That breaks "record before anything is published" (:3151-3155).
- **The test problem:** test 4's "crashed-segment reader equals clean-end summary" cannot hold for cost and overran as written.
- **Fix:**
  - Define the row field as the previous completed cycle's cost (`prev_cycle_us`; 0 on a segment's first cycle), so all k rows of a cycle carry the same known value.
  - Say that the last completed cycle's cost appears only in the manifest, so a crashed segment loses at most one cost sample.
  - Restate test 4's equality against that definition.
- `lag_us` (start lag) is known at the cycle's start and is unaffected.

### P3
1. **Backstop ordering:** say that the 30 s start-lag check runs before any `open_handles` or claim in that cycle (:3092ff), so the backstop never exits holding a claimed batch that is not recorded. "Finishes nothing further" is ambiguous on this.
2. **Comparison scope for tests 14 and 15:**
   - Two executives get different `world_id` and `boot_id` (`uuid4`, :2901), so the comparison must exclude those or pin them.
   - Rows also differ in `chain`, because the chain covers `lag_us`.
   - Checkpoint bodies differ in each segment's `wall_epoch`, `chain` and `offset`, since byte offsets move with the width of the lag digits.
   - The physics and bookkeeping fields must be exactly equal: `tick`, `state_hash`, `lineage`, `effects`, `receipts`, `receipt`, `windows`, `published`, `failures`, and the body's `executive` and `windows`.
3. **Header encoding and propagation points:**
   - Encode `m` in the header as the same `"p/q"` string the checkpoint uses, and type all three in `_header_problem` (:1514-1525).
   - The new keys must be carried at three sites: `_append_record`'s segment entry (:3473-3480), the anchored header rebuild (:2096), and replay's new segment entries (:2452-2456).
4. **Write-ahead details:**
   - A refusal at step j>1 on a write-ahead cycle appends rows 2..j−1 only, because row 1 is already durable.
   - The write-ahead trigger should be "row 1's effects, receipts or `windows` is non-empty", not only "effects, receipts or deferral deltas", so arms, spend and receipt-counter-only deltas are written ahead too.
5. **Inheritance after a fall-back (optional, no effect on determinism):** the resume inherits m, k and N from the base checkpoint (pattern at :5206). If it falls back to an older generation, it can silently undo a change journaled after that generation. Now that headers carry m, k and N, it could inherit from the last replayed segment's header when that is newer. Replay does not depend on k, so this does not affect equivalence.

I re-confirmed the cited lines (:2096, :2455, :2901, :5206) against source this round. The rest come from my r1 reading at the same HEAD. Whether the implementation matches this design is for the implementation review.
