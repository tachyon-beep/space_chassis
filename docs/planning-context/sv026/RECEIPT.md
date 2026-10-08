# SV-026 receipt: replay-work accounting and closed-unit threshold checks (C1–C14)

**Result: the reviewed C1–C14 tranche is implemented. On the final bytes, 161 planned case executions passed in 12 approved runner commands: 48 new, 16 bounds, 97 retained.**

The discriminators behaved as declared:
- **P1** (the original SV025 restart counterexample) passed on the base.
- **P2–P10** each failed on the base at their behavior assertion.
- The staged callback control failed on `context_tokens` (0 vs 6,100) under the old contract and passed after the fix.

SV025's default-constant counterexamples are preserved:
- the 28,311,552-byte suffix blob, now witnessed in the real pre-checkpoint crash window;
- the 730-record previous-base replay.

No numerical recovery bound is claimed. **Not accepted: awaiting the coordinator's commit, scan and backup, and Astra's immutable review.**

Base `190a57f7cfb4227c847ba1e92b7d0ab914384a2c`. Governing inputs:
- DESIGN.md (the launch qualifications at its top govern);
- ASTRA-DESIGN-ACCEPTANCE.md;
- `SV-026-bounded-targets.json`.

The worker made no Git call.

## 1. What the runtime now does

| Mechanism | Where |
|---|---|
| **Read outcome without a reread.** <ul><li>`ReadTooLarge.obtained` carries the `limit + 1` bytes `DurableOps.read` already held.</li><li>`BlobStore.fetch` returns `BlobRead(data, outcome, obtained)`: `accepted` and `rejected_hash` report the file's length, `over_limit` the probe, `missing` and `bad_name` 0, and `io_error` None (unknown).</li><li>`get` is `fetch(...).data`, unchanged for every caller.</li></ul> | `chassis_persistence.py`: `DurableOps.read`, `ReadTooLarge`, `BlobStore.get`/`fetch`, `BlobRead` |
| **Durable header claims.** `open_segment` appends `(seq, frame length)` to `opened_headers` only after the header's write, file fsync and `ledger/` fsync returned. `take_opened_headers()` hands them over. No write, fsync, name or fence order changed. | `LedgerWriter.__init__`, `open_segment`, `take_opened_headers` |
| **Replay work.** <ul><li>`Replay` keeps lifetime `work_records`/`work_bytes`/`work_unmeasured`.</li><li>Every record except an interval origin (CHECKPOINT; the LEDGER_HEADER with seq 1) is charged its frame plus the blob bytes its fetches obtained.</li><li>One read path, `_read`, serves both `_blob` and `_on_done`.</li><li>A refusal raises before any charge.</li><li>`read_blob` (bytes-only) stays for verification and test callers; `fetch_blob` is the measured path.</li></ul> | `chassis_replay.py`: `uncharged`, `Replay.__init__`, `_read`, `_blob`, `apply`, `_on_done` |
| **Live deltas and claims.** <ul><li>`_commit` charges the replay's before/after delta; the manual `replay_bytes` argument is gone, including the declared `entry["bytes"]` for note adoption.</li><li>`_claim_headers` (in `__init__` and `_rotate`) charges every claimed header except seq 1.</li><li>`since_unmeasured` counts unknown-amount fetches.</li><li>CK6 resets all three counters; the Replay lifetime sums are untouched.</li></ul> | `chassis_session.py` |
| **Startup reconstruction.** <ul><li>The selected replay's work is added with `+=` (keeping a `continue_after` reuse-header claim), after the readable extras are applied.</li><li>The previous-base interval runs on its own `middle` instance.</li><li>Rejected candidates and witnessed verification never contribute.</li></ul> | `chassis_startup.py` `_recover`, `_classify_base`, `_previous_base`, `_replay`; `_Decision.suffix_records` removed |
| **Closed units.** `threshold_boundary()` (the guards of `unit_end`; checkpoint on the threshold; no rotation, R-D) runs:<ul><li>at the end of `_recover`, after `_finish_case`, the extras' syncs, the carrier and RECOVERING retirement, and IDENTITY coverage;</li><li>at the end of `_start_legacy`, after `_consume_ack`;</li><li>after each note drop (`write_note`, `adopt_file_edit`), each file-edit NOTE_WRITTEN, each adopted generation and the drop notice.</li></ul> | `chassis_startup.py`, `chassis_session.py` |
| **G2.** `_collect` returns True only after its GC_DONE is durable. If it collected and the GC pair reaches the threshold, `checkpoint` writes exactly one `follow_up=True` checkpoint with the same `ended` and returns it. The follow-up never collects. The one rotation happens after it. | `Session.checkpoint`, `_collect` |
| **Truthful startup metadata.** <ul><li>`meta_source(messages)` receives the list the checkpoint installs, and `Chassis._meta_fields(messages=None)` uses it.</li><li>`Chassis._open_session(**overrides)` is the extracted startup wiring, unchanged in production (no overrides).</li><li>The `run()` docstring states the startup checkpoint.</li></ul> | `chassis_session.py`, `chassis.py` |

## 2. Files

- **Runtime:** `services/chassis_persistence.py`, `services/chassis_replay.py`, `services/chassis_session.py`, `services/chassis_startup.py`, `services/chassis.py`.
- **New test:** `tests/test_chassis_accounting.py` (48 cases, the frozen list in STATUS).
- **Modified tests:**
  - `tests/test_chassis_bounds.py`: test 4 replaced and renamed; test 5's cut moved to the crash window; test 6 changed `+2` → `+1`; module docstring.
  - `tests/test_chassis_session.py:79` and `tests/test_chassis_checkpoint.py:59`: zero-argument `meta_source` lambdas become one-argument. Arity only; no assertion changed.
- **Docs:** `docs/planning-context/sv026/STATUS.md`, this receipt.

Nothing else was touched: no frozen document, contract, vehicle, generator, literal or oracle, and no recorder, provider or runtime configuration.

## 3. Corrections made during execution (both reported, neither weakening)

1. **Bounds test 5: fixture ordering (test only).** The first bounds run failed at `suffix == (2, TARGET, TARGET, 1)` with `(0, 0, 0, 0)`. The rewrite had read `newest_checkpoint(root)` *after* the second start, which by then had written its own threshold checkpoint after `edit`, so the interval was empty. The fix reads C_n before that start, which is SV025's interval. No expectation changed. The rerun passed 16/16.
2. **`_classify_base` reader contract (runtime).** Retained R7 failed in `test_the_retained_reference_graph_covers_every_blob_replay_reads`, an accepted test that calls the private `_classify_base(..., reads)` with a bytes-returning reader. My edit had repurposed that positional parameter as `fetch_blob` (`AttributeError: 'bytes' object has no attribute 'data'`). The fix restores the positional `read_blob` contract and adds `fetch_blob` as a keyword that only `_recover` passes. `_previous_base` and `_replay` take the same reader choice. This is the legacy/fetch distinction ASTRA-DESIGN-ACCEPTANCE asked to keep. Production behavior is unchanged by the fix, but the bytes changed, so all twelve final commands were run again on the final bytes (§4).

## 4. Commands

All commands were `python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <literal targets>`, from the repository root, one per message, awaited. Targets are exactly those in STATUS and `SV-026-bounded-targets.json`. Counts are the runner's progress dots.

| # | Run | Bytes | Result |
|---|---|---|---|
| 1 | P1 original SV025 test 4 | base | 1 passed |
| 2–10 | P2–P10 | base runtime | each failed at its declared assertion (STATUS, checkpoint 1) |
| 11 | S1 CB, staged (old zero-argument contract) | staged | failed: `context_tokens` 0 vs 6,100, after the startup checkpoint was written and the callback ran once with `Chassis.session` None |
| 12 | S2 CB after C11/C12 | pre-correction-2 | 1 passed |
| 13 | N1 | pre-correction-2 | 24 passed |
| 14 | N2 | pre-correction-2 | 24 passed |
| 15 | bounds | pre-correction-1 | 14 passed, then test 5 failed (correction 1); test 6 not run |
| 16 | bounds | pre-correction-2 | 16 passed |
| 17–22 | R1–R6 | pre-correction-2 | 8, 6, 11, 2, 8, 8 passed |
| 23 | R7 | pre-correction-2 | 18 passed, then failed (correction 2); 11 not run |
| 24 | **R7** | **final** | **30 passed** |
| 25 | **R8** | **final** | **16 passed** |
| 26 | **R9** | **final** | **8 passed** |
| 27 | **N1** | **final** | **24 passed** |
| 28 | **N2** | **final** | **24 passed** |
| 29 | **bounds** | **final** | **16 passed** |
| 30–35 | **R1–R6** | **final** | **8, 6, 11, 2, 8, 8 passed** |

**Final evidence (commands 24–35, all on the final bytes): 12 commands, 161 passed, 0 failed.** No command hit a cap, so none was split. No command was denied, retried unchanged or overlapped. The SV024 conditional selectors were not run: no stated condition for them arose. No shell search, Git, ad-hoc Python, install, `ruff` (it needs `uvx`), broad suite, provider or real session was used.

## 5. What the tests establish, by evidence kind

All evidence is in-process simulation in temporary roots, with default caps. Injected values are labelled in each test.

- **Counter = independent oracle.** Frames come from a byte walk; blob amounts from `Attempts`, which takes its own measurement. Counter and oracle agree:
  - live, per unit kind;
  - after restart, for every read outcome: intact, missing, wrong hash larger and smaller, the over-limit probe, I/O error (unmeasured 1);
  - with foreign and retained-only references;
  - across three repeated restarts;
  - with previous-base recovery (the interval excluded);
  - with readable extras applied once;
  - with the genesis origin, pre-first-checkpoint rotation and a `continue_after` reuse header;
  - after reset and after GC, live and after restart.
- **Boundaries.**
  - **Startup:** the bytes, records, legacy and after-intent cases fire a checkpoint; the startup fence failure gives FSYNC_FAILED, no CHECKPOINT, then A1; the below-threshold control writes nothing. After-intent ordering: RECOVERING's unlink and `session/` fence come before the checkpoint's temp open; IDENTITY covers every used turn and `requests_next`; no `gc_refused` names RECOVERING.
  - **Adoption and drops:** per generation, file edit, both drops, the notice. Inside a group there is no checkpoint (CKG control).
  - **Recovery:** it closes the group before its checkpoint.
- **G2.**
  - **Success:** exactly CHECKPOINT, GC_INTENT, GC_DONE, CHECKPOINT; the follow-up is returned; `ended` is kept; the control does not cross.
  - **`crash-before-install`** and **`crash-after-ck5-before-frame-write`** (qualification 1). After the crash:
    - the follow-up frame is missing, and the restart rebuilds exactly the GC pair's work;
    - the restart writes a replacement checkpoint without `ended`, with no unlink of any name in the spent intent and at most 2 checkpoints and 1 GC intent;
    - classification is not forced (A9 or A10);
    - a later A14 recovers the underlying conversation plus the ordinary A14 notice, and the restored file matches the newest checkpoint's hash.
  - **`fence-failure`:** FSYNC_FAILED present, no follow-up CHECKPOINT, no RUN_END, then A1.
- **Callback (real `Chassis`).** The startup checkpoint's `run.json` has `context_tokens == estimate_tokens(recovered)`, `turn` 0, no `ended`, and the ten legacy keys. The client was never called.
- **SV025 bounds.**
  - Test 4 asserts the repair: `(2, 12,428)` rebuilt, and a checkpoint at the fourth unit across the restart.
  - Test 5 keeps the 28,311,552-byte suffix blob, `> 25,166,144`. It is replayed by the start after a death at CK2 entry of the A11 start's threshold checkpoint; the counter at that start's checkpoint entry equals the suffix after C_n's frame.
  - Test 6 keeps 730 > 717 records.

## 6. Limits (unchanged by this implementation)

- **R-D.** The new startup, adoption and drop boundaries do not rotate. A full segment rotates at the next `unit_end` or the end of the next checkpoint. The segment overshoot this allows, and the `MAX_SEGMENT_READ` slack, are not proved.
- **Unmeasured partial I/O.** An I/O error's amount is unknown. It is counted in `since_unmeasured` and never added to `since_bytes`, so the threshold does not cover it.
- **`T_origin`.** C_n's own frame (or the genesis header) is replayed but is not in the counter. It remains a separate term of the unresolved bound.
- **Damaged-blob quantities.** The historical valid-payload delta and the discarded physical read work are charged as measured. Neither is bounded here.
- **Crash-loop accumulation.** ADOPT records from repeated deaths in the CK4–CK6 window still accumulate.

None of the four §1.4.7 inequalities, U_r/U_b, global startup I/O, RSS or latency is proved. SV025's refutations stand. No constant, generator, oracle, history limit, previous-file rule or H/T/Q/pump/history policy changed. No real-session action, merge or deployment.
