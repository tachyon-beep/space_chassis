# SV-024 checkpoint 001: Astra correction (SV024-02)

2026-10-08. Review: `SV-024-Astra-review.md` (head `d94bc78e3cf69daec028b43fee180f88e559897d`, runtime/tests `0ac2245fc93032146a1fc19060ece18276ce9157`). SV024-01 was accepted for its A15 trace and is unchanged. SV024-02 (P2) is fixed here. Opus 5.5. Only the approved runner was used, one literal command per message, each awaited. Temporary roots only. The worker made no Git call, provider call, real-session operation, ad-hoc script or broad suite run. **Not accepted; awaiting the coordinator's checkpoint and Astra re-review.**

## 0. Provenance

An earlier correction attempt was interrupted after it had read the review and the runtime sources. The coordinator verified that its process and scope were absent, that no completion receipt existed and that the checkout was clean. No source/test edits or test runs from it are evidenced. This attempt started from the clean reviewed tree and re-read the full review before editing.

## 1. Pre-fix evidence (reviewed runtime `0ac2245`, new regressions only)

The regressions were written first and declared in STATUS before any run.

| Run | Node | Result on the unmodified runtime |
|---|---|---|
| P1 | `test_sv024_02_a_partial_header_behind_a_published_intent_converges[name-lost]` | FAILED: `Opening(classification='intent', stop='recovery_intent_copy_missing', detail={'copy': 'ledger-000008-0-faf733f4c7645855.bin'})` |
| P2 | `…[name-kept-data-lost]` | FAILED: the same stop, with the same missing copy |
| P3 | `test_sv024_02_a_failed_pre_intent_fence_publishes_nothing[segment-fsync]` | FAILED: `no intent`. RECOVERING already existed, because the segment's first fsync was the quarantine truncation's, after the intent |

Trace, exactly the review's:
1. After an actual collection ending at GC_DONE seq 41, the rotation's header write to segment 8 stores 30 bytes and the process dies inside the write (M-1). The test asserts a file watermark of 0 and an unfenced name.
2. A restart inherits both maps (nothing promoted) and writes RECOVERING{segment 8, offset 0, hash/length of the 30 bytes}. It dies at its first call after RECOVERING's `rename` + `fsync(session/)` returned, so no copy exists.
3. Simulated host loss removes the name (`vanish/drop`), or keeps it and drops the bytes (`keep/drop`).
4. The next start's `_from_intent` finds neither the original bytes nor the copy and stops.

The fragment never came from a host-loss setup, so it was never promoted to a durable baseline.

`[interrupted-again]` and `[ledger-fence]` were not run pre-fix individually. The three runs above already show the missing dependency and the missing pre-intent boundary.

## 2. Fix: the source-fence option (`services/chassis_startup.py` only)

New `_fence_intent_inputs(session_dir, scan, ops)`, called in `_recover` immediately before `write_bytes_durable(RECOVERING)`, only when a new intent is published (`scan0.tail and intent is None`):

1. `fsync` the segment holding P's last record (the intent's anchor: `last_seq`, `chain`).
2. `fsync` the tail's segment (the exact bytes behind `tail_sha256`/`tail_bytes`/`offset`). Steps 1 and 2 are one fsync when they are the same segment.
3. `fsync(ledger/)` for both names.
4. Only then is RECOVERING written (temp, fsync, rename, `fsync(session/)`). Quarantine (admission, corrupt/ fence, durable copy, truncate, fsync) and everything after it are unchanged.

**Why this is sufficient.** Once RECOVERING exists, what it names is durable:
- The anchor and tail bytes are covered by a returned file fsync.
- Their names are covered by a returned ledger/ fence.
- ledger/'s own name was fenced in session/ before its first segment was created (SV020-01 `create`).
- Segments older than the anchor's were synced before anything rotated away from them, by an append fsync or by SV024-01's `sync_inherited` in `open_segment`.

So any host loss after publication leaves either the original tail at (segment, offset) or a later state that the existing protocol already handles: a durable copy written before truncation. `_from_intent` then always finds one of them.

**Kept unchanged:**
- admission and caps, copy-before-truncate, exact hash and length matching in `_from_intent`
- intent identity and seal, and the witnessed/acknowledgement context in the intent
- GC and no-effect semantics
- `recovery_intent_copy_missing` for a genuinely missing copy: no unmatched intent is discarded and no bytes are guessed

The review's alternative (a pre-admitted copy before the intent) was not chosen, because it would reorder the cap stop ahead of intent publication.

**Failure behaviour.** An `OSError` from any pre-intent open, fsync or fence raises `PersistenceFailure` before the intent exists. `open_session` attempts FSYNC_FAILED (§1.4.9). No intent is published, nothing is copied or truncated, and no session is returned, so no effect can follow. The next start stops A1. Both pre-intent controls assert this (§3).

**Changed call sequence.** A start that publishes a new recovery intent now makes one or two extra segment fsyncs and one `fsync(ledger/)` before RECOVERING. Nothing else changes.

## 3. Tests (`tests/test_chassis_namespace.py`; the original 22 cases unchanged)

| Node | Asserts |
|---|---|
| `test_sv024_02_a_partial_header_behind_a_published_intent_converges[name-lost]` | partial header (M-1, watermark 0, unfenced); restart inherits and dies right after the intent is published; host `vanish/drop`. Then the intent's fragment was fenced and synced before the intent; the host loss took nothing; the next start is A9 and writes exactly LEDGER_HEADER, RECOVERY{torn_incomplete}; one corrupt/ copy equal to the 30 bytes; the reused header continues GC_DONE; contiguous seq/chain/segments; newest CHECKPOINT, IDENTITY, run.json, conversation files, state and messages unchanged; no GC record after GC_DONE, no blob or segment removed, no REQUEST_SENT/INVOKING; the dependent unit, then two more starts, the last writing nothing |
| `…[name-kept-data-lost]` | the same, with host `keep/drop` |
| `…[interrupted-again]` | after the published intent, process death only. A third process inherits the maps and dies after the quarantine truncation, before its fsync. Then host `vanish/drop` over all three processes, and the same convergence via the durable copy |
| `test_sv024_02_a_failed_pre_intent_fence_publishes_nothing[segment-fsync]`, `[ledger-fence]` | EIO at the pre-intent segment fsync or at `fsync(ledger/)`. Then PersistenceFailure; no RECOVERING rename; no truncation, `.svl` write or corrupt/ copy; the fragment is byte-identical; FSYNC_FAILED exists; A1 changes only STOPPED. After acknowledgement in the temporary root: LEDGER_HEADER, RECOVERY{torn_incomplete}, RECOVERY_ACK, exact fragment copy, convergence |
| `test_sv024_01_a_failed_inherited_segment_fsync_publishes_no_checkpoint` | requested by the review. After a `before-file-sync` process death, EIO at `sync_inherited`'s fsync in the restart's first checkpoint. Then PersistenceFailure; session and writer broken; protected files byte-identical (no CK2–CK5); no CHECKPOINT; no new segment; the only rename is FSYNC_FAILED; no `.svl` write; no request or message accepted; the next start is A1 |

## 4. Final runs (fixed tree)

| # | Targets | Result |
|---|---|---|
| C1 | `tests/test_chassis_namespace.py` | 28 passed |
| C2 | `tests/test_chassis_recovery_live.py` (whole file: the intent-publication path changed) | 97 passed |
| C3 | frozen batch A, 8 durability nodes | 8 passed |
| C4 | frozen batch B, 6 SV022 nodes | 6 passed |
| C5 | frozen batch C, 11 post-GC nodes | 11 passed |
| C6 | frozen batch D, 2 recovery_live nodes (also inside C2) | 2 passed |
| C7 | frozen batch E, 8 SV023 acknowledgement nodes | 8 passed |
| C8 | conditional `tests/test_chassis_correlation.py::test_recorder_in_loop_identity_survives_collection_and_a_later_interruption` | 1 passed |

Total: 161 selected passes in 8 serial commands (159 distinct nodes; the 2 batch-D nodes ran twice). No failures, denials, retries or overlaps. P1–P3 are pre-fix evidence, not passes. No source mutation was applied in this correction, so `grep MUTATION` over services/tests stays empty.

## 5. Residual limits and boundaries

- **Shifted cut in an existing node, no assertion changed.** `test_chassis_recovery_live.py::test_a_crash_inside_recovery_never_turns_unknown_into_unrun[after-first-record-*]` crashes before the second `.svl` fsync of the recovering start. With the pre-intent fsync that is now the quarantine truncation's fsync, not the first core record's. The node still passes, but its cut now lands earlier than its name says. A crash before the first core record's fsync is no longer exercised by that node. I did not edit it.
- **Unselected tests were not run.** Other acknowledgement or recovery tests that count fsyncs or ledger fences inside an intent-publishing start could see shifted indices (the 8 selected SV023 nodes and all of recovery_live pass).
- The model limits from RECEIPT §9 still apply:
  - truncation and rename reversion are not simulated (`interrupted-again` keeps the truncation)
  - name loss is modelled for ledger segments only
  - the torn shape is one 30-byte prefix
  - host loss is simulated and process death is in-process
- `_fence_intent_inputs` applies to every new recovery intent (TC1/TC2/acknowledged TC4, witnessed context). It is evidenced here for the O2-5 torn-header slice, and the full recovery_live file and the selected SV023 nodes are unchanged in outcome. Its anchor argument relies on earlier segments having been synced before rotation, which holds for this runtime's writers (append fsync; SV024-01 `sync_inherited`).
- Unchanged and not claimed: real power loss or storage, exact replay bounds, bootstrap and lost-ledger resolutions, providers, real sessions, merge or deployment, H/T/Q/pump.

## 6. Files

Modified: `services/chassis_startup.py` (`_fence_intent_inputs`, its call, the module docstring), `tests/test_chassis_namespace.py` (6 cases appended), `docs/planning-context/sv024/STATUS.md`, `docs/planning-context/sv024/RECEIPT.md` (pointer). New: this file. `chassis_persistence.py` and `chassis_session.py` (SV024-01) are unchanged since `0ac2245`.
