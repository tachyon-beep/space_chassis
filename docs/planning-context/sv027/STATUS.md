# SV-027 status

## Implementation checkpoint 2: complete and tested. Not accepted.

**Status:** C1–C5 are implemented. On the final bytes, **76 cases passed in 8 commands** (F1 18; F2 19; F3–F6 6, 11, 2, 8; F7 11; F8 1). Full log: [RECEIPT.md](RECEIPT.md).

**Discriminators on the unchanged runtime.**
- B0 passed (1).
- D1–D7 each failed at their declared behavior assertion:
  - D1, D2, D4, D5: no header at the closure;
  - D3: types `[H, LEGACY_IMPORT]`, before the counter;
  - D6, D7: DID NOT RAISE.
- The first D7 attempt hit a fixture setup error. It was not counted, and was corrected and rerun.

**One test-only correction after the runtime edit.** F1's first run failed in R2 `generation-crossing`, because collection legitimately unlinked the segments a later ledger read relied on. The sequence is now logged as written; the assertions are unchanged. The rerun passed 18/18.

**Files.**
- Runtime: `services/chassis_session.py`, `services/chassis_startup.py`, `services/chassis.py` (docstring only), `services/chassis_persistence.py` (comment only).
- New test: `tests/test_chassis_rotation.py`.
- Docs: this file and RECEIPT.md.
- No existing test changed.

**Limits retained:** RECEIPT §5. **Next:** the coordinator's commit, scan and backup, then Astra's immutable implementation review.

## Implementation checkpoint 1: discriminators (unchanged runtime)

| Run | Result |
|---|---|
| B0 | 1 passed |
| D1 `[startup-a9-clean]` | failed: `[] == ['LEDGER_HEADER']` |
| D2 `[startup-after-intent]` | failed: the core ends in RECOVERY, no header |
| D3 `[legacy-import]` | failed at the types assertion: no H3 |
| D4 `[generations-and-notice]` | failed: index 1 is `MSG_APPEND`, not `LEDGER_HEADER` |
| D5 `[drop-in-write_note]` | failed: `['RECOVERY']` |
| D6 `[startup-inherited-fsync-eio]` | failed: DID NOT RAISE PersistenceFailure |
| D7 `[generations-fence-eio-chassis]` | first attempt: setup `LedgerError` (a wrapper computed `segment_name(-1)` before checking it was armed), **not counted**. After the fix: failed, DID NOT RAISE; the second run entered main and ended `exit=0`. |

## Implementation checkpoint 0: cases frozen before any run

Base: accepted-design archive `bcb3c75225b609b84fcc4e93de5b64e1d9e4f775`. Governing inputs:
- DESIGN.md, with L1–L5 at its top;
- ASTRA-DESIGN-ACCEPTANCE.md (review SHA-256 `9b80837d…4d0f4`);
- `sv016-context/SV-027-bounded-targets.json`.

Opus implements and Astra reviews the immutable result. The worker makes no Git call. Every test command is the approved runner with literal targets, one per message.

**New `tests/test_chassis_rotation.py`: 18 cases.** Its helpers come from accepted modules only (`test_chassis_recovery_live`, `test_chassis_bounds.frames`, `test_chassis_termination.make_run`/`reply`). Three small helpers are local.

| Function | Parameters | n |
|---|---|---|
| `test_sv027_every_closed_boundary_rotates_a_full_segment` | `startup-a9-clean`, `startup-after-intent`, `legacy-import`, `file-edit`, `generations-and-notice`, `drop-in-write_note`, `drop-in-adopt_file_edit` | 7 |
| `test_sv027_one_closure_writes_at_most_one_checkpoint_one_follow_up_and_one_header` | `startup-crossing`, `generation-crossing`, `header-evaluated-next` | 3 |
| `test_sv027_no_rotation_inside_a_group_or_with_a_queue` | `drop-inside-group`, `queued-messages` | 2 |
| `test_sv027_a_nonfull_segment_adds_no_event_at_the_new_boundaries` | — | 1 |
| `test_sv027_rotation_failures_and_crashes_at_the_new_boundaries` | `startup-inherited-fsync-eio`, `startup-ledger-fence-eio`, `startup-name-lost-is-recreated`, `generations-fence-eio-chassis`, `generations-crash-converges` | 5 |

**Injection.** Each value is labelled in the test:
- `segment_max = 1` for writers built during a start, through a test-local patch of `LedgerWriter.__init__` (the accepted `SMALL_SEGMENTS` pattern);
- `session.writer.segment_max = 1` on an open session;
- `records_max` 1 or 2.

Faults are armed by semantic predicates only: a path, the new segment's existence, `writer.inherited`, or a running method. None counts calls.

**Predictions corrected by L1–L5, before any run:**
- **L1 `legacy-import`:** a two-message A5 list with no handoff. Types are exactly `[H1, LEGACY_IMPORT, H3]`, with no checkpoint. The counter is `(2, frame(LEGACY_IMPORT) + len(conversation_bytes(list)) + frame(H3))` from the byte walk, and the blob file's size equals that length. A default-limit restart reproduces the counter with no new header. On the base, D3 fails first at the types assertion (no H3).
- **L2 R4:**
  - every `rotate_if_full` call is wrapped and must return False with an empty `FaultOps` event window;
  - exactly 5 calls are expected: the startup closure, the file edit and 3 generations;
  - the segment name set is unchanged and there is no new LEDGER_HEADER;
  - the record types after P are `[NOTE_WRITTEN, MSG_APPEND ×3]`;
  - the inherited append-open of segment s is present, after the `session/` and `ledger/` fences.

  **Changed prediction:** the call-count assertion (which keeps the windows non-vacuous) would fail on the unchanged runtime. R4 is not a discriminator and is not run before the edit.
- **L3 `generations-fence-eio-chassis`:**
  - The markers are the last seq before the second run, and the seq, active segment, pending generation IDs and watermark at `adopt_notes` entry.
  - EIO is armed only while `adopt_notes` runs, at `sync_dir(ledger/)` once segment `entry+1` exists. The test requires that cut to be reached.
  - After entry, the records are exactly `[MSG_APPEND{gen = first pending}, LEDGER_HEADER]`, and no MSG_APPEND carries a later pending gen.
  - The second run's lifecycle has `run_start` and `runtime_bound`, but no `run_resumed`/`run_fresh`, `turn` or `run_end`. No main or bootstrap marker is written, the client sent nothing, and there is no REQUEST_SENT, INVOKING, CHECKPOINT or RUN_END after the pre-run marker. FSYNC_FAILED exists and the next start is A1.
  - The first run's ledger holds no NOTE_WRITTEN: an ordinary main return creates no note.
- **L4 `startup-crossing`:** an unreferenced orphan blob is put before two says. The restart has **[injected]** `records_max = 2`, `collect=True` and `segment_max = 1`. After the last say the records are exactly `[CHECKPOINT, GC_INTENT, GC_DONE, CHECKPOINT, LEDGER_HEADER]`; the orphan is in the intent and its file is gone. `generation-crossing` counts headers from the adoption entry: 3 closures, each ending with exactly one header.
- **L5:** G6 ran in SV024 (161 selected / 159 distinct, including that conditional case) but not in SV026. B0 re-establishes it on the current runtime. Unchanged-cut and default-size predictions are limited to the selected nodes.

**Planned commands.**
- B0: G6 alone, expected pass.
- D1–D7: the manifest's `pre_fix_targets`, each alone on the unchanged runtime, each expected to fail at its behavior assertion.
- After the C1–C5 edit: F1 (18), then the seven retained batches (19, 6, 11, 2, 8, 11, 1): **76 cases in 8 commands**.

## Governing implementation qualifications — independent review accepted

Astra accepted the architecture at immutable design `0f113aed48d740c553322e5fdbf09ddb0fecd7af`, subject to **L1–L5 in [ASTRA-DESIGN-ACCEPTANCE.md](ASTRA-DESIGN-ACCEPTANCE.md)**. Those qualifications supersede conflicting historical text below; implementation remains unaccepted until its own review.

- L1: the A5 counter is `(2, LEGACY_IMPORT frame + imported blob bytes + H3 frame)`, with only H1 excluded and no checkpoint. Distinguish nonempty import from the empty-list OPENING trace.
- L2: the non-full control preserves the inherited append-open and startup fences. Assert unchanged names/no new header or new-segment open; use precise closure event windows.
- L3: use pre-run and adoption-entry markers. Arm only the new adoption header's directory fence; assert baseline pending IDs/watermark and only first-generation progress. Client construction/duty loading precede adoption, while main/bootstrap/request/tool invocation and the second run's run-end do not. Ordinary main return does not create a pending note.
- L4: one existing crossing fixture must actually select collectible evidence and exercise CHECKPOINT, GC_INTENT, GC_DONE, follow-up CHECKPOINT, exactly one header. Count generation headers from adoption entry, excluding startup.
- L5: G6 ran in SV024, but not SV026; B0 establishes the current baseline. Limit unchanged-cut/default-size predictions to selected nodes, and preserve observed cut semantics. 19,978 is the source's claimed checkpoint frame size, not an established maximum; SV025's valid-domain 21,173-byte witness remains.

The finite matrix remains 18 new + 58 retained cases in eight final commands, plus B0 and D1–D7. No broad test, policy, literal or resource-cap change follows from acceptance.

## Design round 0: complete, awaiting independent review. Not implemented. Not accepted.

- **Base inspected:** `a17115f89b3775ca0a34cd759be79bd1fe38c9e3`. It contains the SV026 implementation, which was under review during drafting and was subsequently accepted without runtime correction; the coordinator archived that acceptance at `e6016fc1cd5fa3d68c54f40c9c21834210231660`. This proposal modifies none of its code, tests or receipts.
- **SV025:** accepted as evidence at `1ede8a3`.
- **Obligation:** R-D, deferred by SV026 (DESIGN §4.4; RECEIPT §6; ASTRA-DESIGN-ACCEPTANCE "does not close the all-boundaries rotation obligation").
- **Files written:** only `docs/planning-context/sv027/DESIGN.md` and this file. No runtime or test file was touched.

### Proposal in one paragraph

SV-015 v2 §1.4.6 requires rotation "at a unit boundary when ≥ `SEGMENT_MAX`". That predicate is separate from §1.4.1's checkpoint threshold, and evaluating one does not evaluate the other. The SV026 sites check only the threshold: startup (`_recover`, `_start_legacy`), each adopted generation, the drop notice, file-edit adoption and both note drops. `unit_end` already has the same guards and the same checkpoint branch, plus a rotate-if-full fallback. `checkpoint` already rotates once at its end. The smallest coherent change is therefore to delete `Session.threshold_boundary` and call `unit_end()` at its seven call sites (DESIGN §3–§4, C1–C5), with docstring and comment text corrected.

At default constants this adds I/O only when the active segment already holds ≥ 16 MiB. Each closure still writes at most one checkpoint, one G2 follow-up and one header. No rotation happens inside a group or with a queue. No owner choice is needed: the change only adds rotation where §1.4.6 permits it and changes no constant or policy (DESIGN §1).

### Frozen proposal (nothing run)

- **New file `tests/test_chassis_rotation.py`: 18 nodes.**
  - R1, every closed boundary: 7.
  - R2, one closure's bounded work: 3.
  - R3, group and queue guards: 2.
  - R4, default non-full control: 1.
  - R5, new failure and crash compositions: 5.
- **Retained: 58 explicit nodes.**
  - SV026 accounting subset: 19 (SV026 acceptance now satisfied).
  - SV024 batches 2–5, verbatim: 27.
  - Notes and metadata: 5.
  - GC adoption under tiny segments: 2.
  - C-G2/O2-3 golden and placement: 4.
  - Correlation, promoted from conditional: 1.
- **Total:** 76 cases in 8 post-change commands.
- **Before the edit:** B0, a baseline of the promoted correlation node, expected to pass; and D1–D7, single-node discriminators expected to fail at behaviour assertions on the unchanged runtime.
- SV024 batch 1 is excluded: writer-level only, with no changed line.
- No existing test changes. No numeric fault cut is affected: at defaults the event trace is identical, and the cuts in the injected-segment tests are semantic or self-calibrated outside the new sites (DESIGN §7.1).

### Not claimed

There is no maximal segment-read bound and the `MAX_SEGMENT_READ` slack is not proved. The following remain open:
- the unit-size term (P1);
- the closure checkpoint/GC frames;
- a startup core into an inherited full segment;
- crash-loop accumulation (L2);
- `T_origin`;
- the true older previous-base terms;
- partial I/O.

None of the §1.4.7 inequalities, U_r/U_b, constants, generator, oracles, history limits, previous-file preservation, acknowledgement/bootstrap loss semantics or H/T/Q/pump/history policies changes (DESIGN §11).

### Inputs read (dedicated Read/Glob/Grep tools only)

- `AGENTS.md`, `CLAUDE.md`.
- SV-015 v2 §1.4.1–§1.4.10 (`sv016-context/SV-015-integrated-apparatus-closure-v2.md`).
- `docs/planning-context/sv026/` `DESIGN.md`, `ASTRA-DESIGN-ACCEPTANCE.md`, `RECEIPT.md`, `STATUS.md`.
- `sv016-context/SV-024-bounded-targets.json`, `SV-026-bounded-targets.json`.
- `services/chassis_session.py` (whole file).
- `services/chassis_persistence.py`: read bounds, `LedgerWriter`.
- `services/chassis_startup.py`: `open_session`, `_start_legacy`, `_recover`, `_finish_case`, `_consume_ack`.
- `services/chassis_gc.py`: `retained_basis`, `unauthorized_prefix`, `plan_collection`.
- `services/chassis.py`: `turn_once` end, recap fold, `run`, `_open_session`, `resume_session`, `main`.
- Tests: `test_chassis_gc.py` (harness, cut mechanisms, affected tests), `test_chassis_correlation.py`, `test_chassis_durability.py` (O2-5/SV020-01), `test_chassis_ledger.py` (rotation), `test_chassis_session.py` (C-G2, rotation), `test_chassis_accounting.py` (A6–A8, CB), `test_chassis_termination.py` (`make_run`), `test_chassis_recovery_live.py` (helpers).

### Execution log and deviations

- No shell command, test, runner, Python, install, Git operation, provider, real session, credential, raw log, original repository, account or settings action.
- **Denied action:** one `Glob` for `SV-02[4-6]*` under `/home/john/Documents/Codex/2026-10-07/task` was denied automatically. The path is outside the allowed working directories, and the session has no approval surface. It was not retried and no workaround was attempted. The needed manifests were found in the already-allowed `sv016-context` directory.
- Filigree was not used (its store previously failed read-only; no retry, init, repair or claim).

**Stopping here.** SV026 acceptance is satisfied; SV027 implementation waits for its own design review and a separate reviewed prompt.
