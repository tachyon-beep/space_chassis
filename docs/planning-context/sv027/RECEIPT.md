# SV-027 receipt: segment rotation at every closed unit boundary (closes R-D's placement gap)

**Result: C1–C5 implemented. On the final bytes, 76 planned case executions passed in 8 approved runner commands (18 new, 58 retained). B0 passed on the unchanged runtime. D1–D7 each failed at their declared behavior assertion.**

**Not accepted.** This awaits the coordinator's commit, scan and backup, and Astra's immutable review. The worker made no Git call.

Inputs:
- Base: the accepted-design archive `bcb3c75225b609b84fcc4e93de5b64e1d9e4f775`.
- Governing: DESIGN.md with L1–L5; ASTRA-DESIGN-ACCEPTANCE.md (SHA-256 `9b80837dd39d2b99e4c37d2b11ad306c9b145d814b03ef0b9a7951212da4d0f4`); `SV-027-bounded-targets.json`.

## 1. What changed

| # | File | Change |
|---|---|---|
| C1 | `services/chassis_session.py` | The five session call sites (`write_note` drop, `adopt_file_edit` drop, file-edit NOTE_WRITTEN, each adopted generation, drop notice) call `self.unit_end()` |
| C2 | `services/chassis_session.py` | `Session.threshold_boundary` is deleted. No reference remains in `services/` or `tests/`. |
| C3 | `services/chassis_startup.py` | `_start_legacy` and `_recover` end with `session.unit_end()`, at the same position: after `_consume_ack`; after the extras' syncs, carrier/RECOVERING retirement and IDENTITY coverage. Comments updated. |
| C4 | `services/chassis_session.py` (module docstring, `adopt_notes`, `unit_end`), `services/chassis.py` (`run` docstring) | text only |
| C5 | `services/chassis_persistence.py` (comment above `MAX_SEGMENT_READ`) | The unproved "one unit's frames" overshoot is replaced by what may be written before the closure, stated as unbounded. The value is unchanged. |

Not changed:
- `unit_end`'s guards and branches;
- `checkpoint`, G2, `_collect`, `_rotate`, `_claim_headers`;
- `LedgerWriter`, including its fences, `sync_inherited` and header claims;
- the counters, constants, caps, schema, oracles and literals;
- intent, acknowledgement and IDENTITY code;
- GC planning;
- every existing test file.

New: `tests/test_chassis_rotation.py` (18 cases).

## 2. Commands

All commands were `python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <literal targets>`, from the repository root, one per message, awaited. Counts are the runner's progress dots. The runner stops at the first failure.

| # | Run | Runtime | Result |
|---|---|---|---|
| 1 | **B0** correlation node | unchanged | **1 passed** |
| 2 | **D1** R1[startup-a9-clean] | unchanged | failed as declared: `[] == ['LEDGER_HEADER']`. The start wrote nothing after C_n. |
| 3 | **D2** R1[startup-after-intent] | unchanged | failed as declared: the recovery core (SYNTH … RECOVERY) ended without a header |
| 4 | **D3** R1[legacy-import] | unchanged | failed at the types assertion first (L1): `[H, LEGACY_IMPORT]`, no H3 |
| 5 | **D4** R1[generations-and-notice] | unchanged | failed as declared: 17 MSG_APPENDs with no interleaved header |
| 6 | **D5** R1[drop-in-write_note] | unchanged | failed as declared: `['RECOVERY']` |
| 7 | **D6** R5[startup-inherited-fsync-eio] | unchanged | failed as declared: DID NOT RAISE (the start made no rotation fsync) |
| 8 | D7 R5[generations-fence-eio-chassis] | unchanged | **setup error, not counted** (correction 1, §3) |
| 9 | **D7** (corrected fixture) | unchanged | failed as declared: DID NOT RAISE. The second run adopted with no rotation, entered main and ended `exit=0 main_returned` |
| 10 | F1 new file | **final** | 8 passed, then `[generation-crossing]` failed (correction 2, §3) |
| 11 | **F1** new file (corrected fixture) | **final** | **18 passed** |
| 12 | **F2** SV026 accounting subset | **final** | **19 passed** |
| 13 | **F3** SV024 batch 2 | **final** | **6 passed** |
| 14 | **F4** SV024 batch 3 | **final** | **11 passed** |
| 15 | **F5** SV024 batch 4 | **final** | **2 passed** |
| 16 | **F6** SV024 batch 5 | **final** | **8 passed** |
| 17 | **F7** notes, metadata, GC adoption, golden | **final** | **11 passed** |
| 18 | **F8** correlation | **final** | **1 passed** |

**Final evidence (commands 11–18):** 8 commands, 76 passed, 0 failed. The runtime bytes did not change after the C1–C5 edit. Only the new test file changed between commands 10 and 11, and only F1 uses it.

No cap was hit and nothing was split. No command was denied, retried unchanged or overlapped. No broad test, shell search, Git, ad-hoc Python, install or `ruff` was used. The SV024 conditional selector `test_o2_2_…[a11]` / `…negative_control…` was not run: no stated condition arose.

## 3. Corrections during execution (both test-only, neither weakening)

1. **D7 fixture ordering.** The class-level `sync_dir` wrapper computed the armed segment's path before checking that it was armed. During startup's namespace fence it therefore called `segment_name(-1)` and raised `LedgerError`. That is a setup failure, so it was not counted as a discriminator. The fix tests "armed" first. No assertion changed. The rerun failed at the intended `pytest.raises`.
2. **R2 `generation-crossing` observation.** With **[injected]** `records_max = 1`, `segment_max = 1` and collection on, the second generation's checkpoint correctly collects the segment holding generation 1's records. A later ledger read therefore began at a surviving header (`closure[0] == 'LEDGER_HEADER'`). The fix logs the sequence as written, at `LedgerWriter.append` and `open_segment`, from the adoption entry. The assertions are unchanged: 3 closures, each starting with MSG_APPEND and ending with exactly one header, 1–2 checkpoints, ≤ 1 GC intent, no consecutive headers.

   This is the L5 situation: collection changes what a later read can see. It is recorded here rather than worked around by disabling collection.

## 4. What the evidence establishes, by kind

All of this is in-process simulation in temporary roots, plus one real `Chassis.run()` against a fake client (R5 `generations-fence-eio-chassis`) and one real-process recorder correlation (F8). Every non-default value is injected and labelled.

- **Every closed boundary rotates a full segment (R1):**
  - startup A9 clean;
  - recovery after a RECOVERING intent;
  - legacy import;
  - file-edit adoption;
  - each of 16 generations and the drop notice;
  - both drops.

  At startup the inherited segment is fsynced before the new segment opens, and the new name is fenced. After an intent, RECOVERING's unlink and `session/` fence and any IDENTITY rename come before the new segment's open. At `open_segment` entry RECOVERING and ACKNOWLEDGED are absent and IDENTITY covers every used turn. The recovery core stays in the inherited segment.
- **L1.** The A5 trace is exactly H1, LEGACY_IMPORT, H3, with no checkpoint. The counter is `(2, frame(LEGACY_IMPORT) + len(conversation_bytes(list)) + frame(H3))` from the independent byte walk, and the blob file's size equals the list length. A default-limit restart reproduces the counter with no further header.
- **One closure's bounded work (R2, L4).** Startup crossing with an unreferenced orphan blob gives exactly CHECKPOINT, GC_INTENT, GC_DONE, follow-up CHECKPOINT, one LEDGER_HEADER, and nothing after. The orphan is listed in the intent and its file is gone. Generation crossing gives one header per closure. A header is charged but evaluated only at the next closure: the counter is `(2, frame(say) + h)` with no checkpoint, and the next say checkpoints.
- **Guards (R3).** There is no rotation inside a tool group or while messages are queued; the turn's checkpoint, or the flush and checkpoint, rotates once.
- **L2 (R4).** At default size, startup, a file edit and three generations make exactly 5 rotation checks. Each returns False with an empty filesystem event window. Segment names are unchanged, there is no new header, and the only `.svl` open is the inherited append-open after the `session/` and `ledger/` fences.
- **Failures and crashes (R5).**
  - **Startup EIO, at the inherited-segment fsync** (asserted `writer.inherited` at entry): `PersistenceFailure`, FSYNC_FAILED, no new file, next start A1.
  - **Startup EIO, at the new header's `ledger/` fence:** `PersistenceFailure`, FSYNC_FAILED, the complete header is present, next start A1.
  - **Startup crash at that fence, then the name unlinked (simulated M-2):** the restart recreates the segment with the same header payload, and seqs are contiguous.
  - **Real `Chassis.run`, EIO at the adoption header's fence (L3):**
    - pending generations and watermark are as written at adoption entry;
    - the suffix after entry is exactly `[MSG_APPEND{first gen}, LEDGER_HEADER]`, and the later generation stays pending in the newest checkpoint;
    - lifecycle shows `run_start` and `runtime_bound`, then no `run_resumed`/`run_fresh`, `turn` or `run_end`;
    - no main or bootstrap marker, no request sent, and no REQUEST_SENT, INVOKING, CHECKPOINT or RUN_END after the pre-run marker;
    - FSYNC_FAILED exists, and the next start is A1;
    - the first run's ordinary main return wrote no note.
  - **Process death at the fence after generation 1:** two restarts adopt every generation exactly once.
- **Retained (58).** No existing test was modified.
  - SV026 accounting: 19.
  - SV024 batches 2–5: 27.
  - Notes, metadata and GC adoption under tiny segments: 7.
  - C-G2 `[9, 18]`, O2-3, rotation placement and CKG: 4.
  - Real-process correlation: 1. Its launcher forces `segment_max = 1` into every writer, so it now runs the new startup and legacy rotations under collection and a killed in-flight request.
- **L5.** G6 ran in SV024 (161 selected / 159 distinct) but not in SV026; B0 passed on the current runtime before the change. Predictions about unchanged cuts and default sizes are limited to these selected nodes.

## 5. Limits (unchanged)

R-D's placement gap is closed: every closed unit boundary evaluates rotation. Not proved:
- `MAX_SEGMENT_READ`'s slack, and what a full segment may still receive before its closure: the rest of a unit (unit maxima unresolved), the closure's checkpoint and GC frames, a startup core, and their repetition across interrupted starts;
- `T_origin` and the older previous-base span;
- unknown partial-I/O cost;
- RSS and latency;
- U_r/U_b and any of the four §1.4.7 inequalities.

19,978 is the source's claimed checkpoint frame size, not an established maximum; SV025's valid-domain 21,173-byte witness stands. At injected sub-header segment sizes, a startup closure may close a header-only segment, one header per closure. No constant, literal, generator, oracle, history rule, previous-file rule, acknowledgement/bootstrap semantics or H/T/Q/pump policy changed. No real session, provider, merge or deployment was involved.
