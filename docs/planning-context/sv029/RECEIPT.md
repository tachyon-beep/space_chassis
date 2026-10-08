# SV029 receipt: test-only residual replay-bound evidence

**Status: implemented and executed; awaiting independent immutable Astra review. Not accepted.**

- Design base: accepted design head `7224b36fb4ae343aa5273eeeed1a93a3d3149d3b`.
- Governing review: `SV-029-Astra-design-review.md` L1–L6.
- Target manifest: `SV-029-bounded-targets.json` (12 cases, 2 commands).

## Files changed

| File | Change |
|---|---|
| `tests/test_chassis_replay_residual.py` | **New**: 4 test nodes, the test-local `CheckpointWriteDeath` ops and the `probes` fixture |
| `docs/planning-context/sv029/DESIGN.md` | Line 3 corrected (L6); a governing L1–L6 corrections section added; the draft is otherwise kept as history |
| `docs/planning-context/sv029/STATUS.md` | New current-status section prepended |
| `docs/planning-context/sv029/RECEIPT.md` | This file |

Unchanged: all runtime code under `services/`, every existing test (including the reused helper definitions in `test_chassis_bounds.py`, `test_chassis_recovery_live.py` and `test_chassis_durability.py`), canonical sources, literals and the generator.

## Commands (exactly the manifest's two, serially, each completed before the next)

1. `python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23` with the 4 new node IDs → output `....  [100%]`: **4 passed**.
2. The same runner with the 8 retained node IDs → output `........  [100%]`: **8 passed**.

**Total: 12/12 passed in 2 commands.** Both ran on the first attempt, so there were no failures, corrected expectations or reruns. There were no cap hits and no permission denials. No other command was run: no collect-only, no Git, and no ad hoc Python.

The runner printed only pass dots. It reported no timing or resource figures, so none are claimed. Every value below is fixed by an exact or bracketing assertion that passed; none comes from printed output.

## Measured results (asserted)

### N1: retained previous base spanning seven threshold intervals, previous-bytes counterexample

- Every round:
  - The start is A11 and stays below the threshold.
  - Units 1–7 write no checkpoint; the 8th unit's threshold checkpoint follows it at once, with only GC records after it.
  - The interval satisfies `work − last unit < 8,388,608 ≤ work < 25,166,144`, so the newest-row premise holds in each interval.
- All seven checkpoints have `prev == A`, and `.prev.json` holds A's bytes unchanged throughout.
- There is no LEDGER_HEADER. The only CHECKPOINT frames after A are B and the seven round checkpoints.
- Final start: A14, no stop.
  - Applies are exactly `A.covers+1 … end of P`, each once and in order.
  - There are **63** returned blob reads, with 63 distinct names and 63 distinct applying seqs. They are the 56 message blobs of 1,048,576 B each and the 7 edit blobs of known size.
  - Raw returned bytes equal `interval_work`'s logical and distinct sums.
- **Message blob bytes = 58,720,256 ≥ 50,352,266, exceeding it by 8,367,990**, independent of frame counting.
  - The total (frames, including every CHECKPOINT frame, plus blobs) is larger still.
  - Frame bytes are bracketed: `0 < checkpoint frames < all frames < 1,000,000`.
- The SV026 trigger after A14 is `since_bytes < 8,388,608 <` the measured total, so the counter does not see this interval.
- After recovery, the messages equal C₇'s list plus `A14_NOTICE`. `conversation.json` is restored to C₇'s hash, and `.prev.json` is unchanged.

### N2: control, immediate previous base

- Round 2 has no edit and starts A9. `C₂.prev == C₁`, and `.prev.json` hashes to C₁'s conversation (rotated).
- A14 applies exactly `C₁.covers+1 … end`. It reads exactly round 2's eight blobs: **8,388,608 B** in 8 reads with distinct seqs.
- `8,388,608 ≤ total < 25,166,144 < 50,352,266`, so it is in bound. The previous-bytes contradiction depends on the retained span, not on message size.

### N3: repeated edited starts dying before their checkpoint, newest-records counterexample under that schedule

The prefix (L3-proved):

- A9 start, `since = (0, 0)`. After 255 inline messages, `since_records = 255` and B is still the newest checkpoint.
- The 256th message's threshold checkpoint (counter at entry 256) dies at its CHECKPOINT frame write, before any byte; the hook fired once.
- After B there are exactly 256 MSG_APPEND frames, all inline: no checkpoint frame and no header.
- CK4 installed the new list, CK3 kept B's bytes in `.prev.json`, and CK5 covers the last message.

The starts:

| Start | Case (probe) | `N_j` (after B's frame) | New core | Counter at checkpoint entry |
|---|---|---:|---|---:|
| 1 (dies at install entry) | A10 | 256 | 1 RECOVERY `conversation_adopted` | 257 |
| j = 2…109 (edit, dies at install entry) | A11 | j + 255 | 1 EXTERNAL_EDIT with the edited file's `conv_sha` | j + 256 |
| 110 (unchanged, normal) | A9t (`Opening` and probe) | **365** | none; then 1 CHECKPOINT | 365 |

Every measured start satisfied all of the following:

- `.prev.json` held B's exact bytes.
- Applies were exactly `B.seq … endpoint`, each once and in order, so nothing at or below B's cover was replayed and no previous base was used.
- There was no header.
- The install-entry death fired exactly once.
- `conversation.json`, `.prev.json` and `run.json` were unchanged by the dying start.
- Abandoned writers were closed.

Results:

- **Start 104 is the first to read 359.** The final start reads **365 > 358** (366 counting B's own frame).
- The interval up to the new checkpoint holds exactly 256 MSG_APPEND, 1 RECOVERY and 108 EXTERNAL_EDIT records (365).
- After the final checkpoint, `since = (0, 0)`, no group is open, and there is no `corrupt/` directory.

### N4: control, repeated deaths without an external change

- Start 1: A10, `N = 256`, one adoption, counter 257.
- Starts 2–4: A9t, `N = 257`, **no new record**, counter 257, each dying at install entry.
- Start 5: A9t, `N = 257 ≤ 358`, counter 257, one CHECKPOINT, then `since_records = 0`. There is no `corrupt/` directory.
- The N3 growth therefore needs a fresh external change per start. Restarts alone do not produce it.

### Retained (8, unchanged)

The SV025 threshold-once and 730-record retained-base witnesses, SV026 previous-base counting and no-double-count, the `[ck6-before-write-A10]` and `[ck2-temp-A9]` crash cuts, A11 adoption, and A14 rebuild: all passed.

## Resource notes (estimates, not measurements)

- **N1:** cumulative message-blob return work is 280 MiB (56 MiB live re-reads + 168 MiB from the A11 starts' previous-base reconstruction + 56 MiB at the final A14). Peak disk is ≈ 70 MiB.
- **N2:** peak disk is ≈ 40 MiB.
- **N3:** 110 starts over a ledger of under 400 records.
- **Caps:** both commands completed inside the runner's 120 CPU-s / 180 wall-s / 512 MiB address-space caps and the aggregate CPU 50% / 2 GiB / 64 tasks / nice 15 scope. No RSS, latency or I/O total was measured.

## Limitations and nonclaims

- **Scope of the two counterexamples.** If accepted, they are default-current-runtime counterexamples to the two remaining exact inequalities, in temporary roots. A pass that asserts a contradiction is evidence against the canonical number, not a replacement bound.
- **N3's schedule.** N3 depends on a stated schedule: 108 external edits, each followed by simulated in-process death at install entry. It does not refute the newest-records bound under PR-N, and the N4 control does not prove that bound for every single-interruption history. PR-N, and any `U_r ≤ 102` formula, remain unproved research obligations.
- **Simulated crashes.** These are in-process simulations (`Crash` raised from injected calls), not subprocess death or host-loss/kernel evidence.
- **Final recovery work versus build work.** The final recovery work measured here is distinct from N1's build-time lifetime work.
- **Not established:**
  - `U_r`/`U_b` maxima;
  - `T_origin`;
  - total startup I/O, base-file reads and scanner reads;
  - unknown partial I/O;
  - segment read slack;
  - RSS, latency and lifetime bounds.
- **Not authorized:** no runtime/oracle/policy change, real-session operation, provider call, merge or deployment, and no H/T/Q/pump/history/previous-file decision.
