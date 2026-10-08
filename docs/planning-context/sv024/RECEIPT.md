# SV-024 receipt: integrated O2-5, a rotation's new segment name lost after actual collection

2026-10-08. Base: accepted SV-023 head `8bffe49ecf546d8581fb6e34bff6eb9e096d8841`, runtime/tests `fb638a6f4f65e382a7cdb7f691fe9cd82cbd208e` (`SV-023-Astra-correction-2-review.md`). Scope: `SV-after-023-roadmap.md` and `SV-024-targets-preflight.md`; frozen targets `SV-024-bounded-targets.json`. Opus 5.5. Only the approved runner was used, one literal command per message, each awaited before the next. Temporary roots only. The worker made no provider call, real-session operation, install, Git call, ad-hoc script or broad suite run. **Awaiting the coordinator's checkpoint and independent review; not accepted.**

## 1. Runs

Runner: `python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <targets>`. Counts are the runner's progress dots. No command was denied or retried, and none overlapped.

| # | Tree | Targets (exact, as in the frozen JSON) | Result |
|---|---|---|---|
| R1 | unmodified runtime | `tests/test_chassis_namespace.py` | 15 passed, then 1 FAILED (`…second_restart…[at-its-checkpoint]`: A15). The runner stops at the first failure, so 6 nodes did not run. This is the pre-fix trace (§3). |
| R2 | fixed | `tests/test_chassis_namespace.py` | 22 passed |
| M1 | fixed + mutation M1 | `…survivors_recover_without_a_gap[after-fence-host-vanish-drop]` | FAILED as expected (§6); mutation restored |
| F1 | final | batch A, 8 `test_chassis_durability.py` nodes | 8 passed |
| F2 | final | batch B, 6 SV022-01/02 `test_chassis_gc.py` nodes | 6 passed |
| F3 | final | batch C, 11 post-GC `test_chassis_gc.py` nodes | 11 passed |
| F4 | final | batch D, 2 `test_chassis_recovery_live.py` nodes | 2 passed |
| F5 | final | batch E, 8 `test_chassis_acknowledgements.py` nodes | 8 passed |
| F6 | final | conditional: `tests/test_chassis_correlation.py::test_recorder_in_loop_identity_survives_collection_and_a_later_interruption` | 1 passed |
| F7 | final | `tests/test_chassis_namespace.py` | 22 passed |

Final evidence: 35 retained + 1 conditional + 22 new = **58 selected passes in 7 serial commands** on the final tree. F1–F5 are exactly the 35 frozen retained cases.

The conditional correlation node was added for a concrete reason. The fix changes `Session.checkpoint`, which every resumed start runs, including the real `chassis.py` process before its first request. The two O2-2 conditional nodes were **not** run, because previous-base selection is unchanged. No unselected test was run (see §8 for the static blast-radius note).

## 2. Fault model extension (tests only; `tests/test_chassis_namespace.py`)

- `NameOps(CutOps)` keeps the accepted SV-022 byte watermarks and unfenced-unlink bookkeeping. It also records each `.svl` name created with `O_CREAT` since the last returned `fsync(ledger/)`. Only a returned directory fsync clears that list.
- **Name durability and file-byte durability are tracked separately.** A returned file fsync raises the byte watermark and leaves the name unfenced. A returned ledger/ fence covers the name and leaves the bytes alone.
- **Carried across process death.** `inherit()` hands the *same* dictionaries to the next process. Opening or reading a file promotes nothing, and the test asserts this directly (`second_restart[before-its-fence]`: after the restart had read the complete header, the name is still unfenced and its watermark is still 0).
- **No current-readable baseline.** After a *simulated host loss*, the next process starts a fresh model, because the on-disk state is then the durable state. After a *process death*, it never does.
- `host_loss(ops, names, data)` takes back only what neither kind of evidence covers. `names = vanish|keep` applies to names whose fence never returned. `data = drop|torn|keep` applies to bytes after a file's watermark; `torn` keeps a strict prefix of at most 30 bytes. Unfenced unlinks are undone. Every case asserts that nothing else was taken: no undone collection unlink, and unsynced bytes only in the new segment.

## 3. Defect found and fixed (SV024-01)

**Trace, observed in R1 on the unmodified runtime.** A collection ended at GC_DONE seq 41. Its rotation created segment 8 and wrote header seq 42. The process died before the header's file fsync (M-1: the bytes were readable and unsynced, the name unfenced). The restart's `continue_after` fenced the name, so `fsync(ledger/)` returned, but nothing synced the readable header. Its first checkpoint made `run.json` durable with `covers_seq = 42` (CK5) and then died before the CHECKPOINT frame's fsync. Simulated host loss over both processes kept the fenced name and dropped the never-synced header, leaving an empty segment 8. The next start stopped with `checkpoint_ahead_of_ledger` (A15, covers 42 > last 41). That is a false stop where O2-5 requires convergence.

**Cause.** Bytes a writer continues after are readable, which is not the same as durable (the SV022-01 class). A checkpoint could publish a cover for them before any fsync of their segment.

**Fix.** Two runtime files, no other change:
- `services/chassis_persistence.py`:
  - New `LedgerWriter.inherited` attribute. `continue_after` sets it when it continues an existing segment, and any returned append fsync clears it.
  - New `sync_inherited()` fsyncs that segment once. A failure goes through `_fail`: the writer is broken and FSYNC_FAILED is attempted.
  - `open_segment` calls it before rotating away from inherited bytes. With today's call sites this matters only for a rotation with no append since the continue. The retained isolated O2-5 node `test_o2_5_a_lost_segment_name…` does exactly that.
- `services/chassis_session.py`: `Session.checkpoint` calls `writer.sync_inherited()` before CK1–CK5. A failure takes the session's persistence boundary.

The extra fsync happens only when a writer created by `continue_after` reaches a checkpoint or a rotation before any append. Every other path's call sequence is unchanged. After the fix, R2 and F7 pass, and in `[at-its-checkpoint]` the header survives the host loss whole while the unsynced CHECKPOINT does not.

The same mechanism also covers an ordinary readable but unsynced record at the end of the continued segment. Only the rotation-header slice is evidenced (§9).

## 4. Source → fixture map

| Source | Fixture (node) |
|---|---|
| v2 §1.4.8: new segment `O_EXCL`, header, `fsync(file)`, `fsync(ledger/)` | `test_o2_5_the_rotation_calls_are_exactly_the_mapped_cuts`: the armed log is exactly open/write `01`/fsync `01`/`sync_dir ledger`, and the next gate is written and synced only after it |
| §1.4.8: "a crash before the directory sync may lose the new segment's name … TC0 at the old segment's end" | `survivors…[*-host-vanish-drop]` with `absent`: `assert_old_end` (TC0, last record = GC_DONE in segment n, tail segment n, `unauthorized_prefix` None) |
| §1.4.10 rotation row: "header damage → A2" versus a torn header | `[before-file-sync-host-keep-torn]`: TC1, one corrupt/ copy equal to the torn bytes, one `torn_incomplete`, segment reused |
| O2-5: "recovery ends at the old segment (TC0); the next record recreates segment n+1 with `first_seq = last + 1`; forbidden: a seq gap reported as damage" | every `survivors…` case and `continue_and_converge`: contiguous seqs and segment numbers, each header continuing its predecessor's seq/chain, no stop |
| v2 §1.4.5 / SV-022: collection really removed segment 0 and the old records | fixture `collected` plus `rotate_after_collection`, which asserts that the armed rotation directly follows a GC_DONE whose intent's segments are physically gone |
| SV020-01: names found are not durable until a fence returns; a failed fence permits no effect | `second_restart[before-its-fence / after-its-fence]`; `failed_namespace_fence[rotation / restart]` |
| v2 §1.4.9: sync error → PersistenceFailure, FSYNC_FAILED best effort, A1 next | `failed_namespace_fence[*]`: marker present, A1 changes nothing but STOPPED |
| O2-2 after collection | `previous_base_replay…[absent, torn]`: the accepted `assert_a14_recovers_exactly`, run from the real retained previous base after the name loss |

## 5. Crash-cut map

Armed calls (`open_segment`): 0 `open(n+1, O_CREAT|O_EXCL)`, 1 `write(header)`, 2 `fsync(n+1)`, 3 `fsync(ledger/)`. "Dies before" means `Crash` raised before the call.

| Node id | Dies before | Loss | Survivor | Start 1 writes |
|---|---|---|---|---|
| `before-write-process-death` | 1 | process death | empty | LEDGER_HEADER (reuse) |
| `before-write-host-vanish-drop` | 1 | host | absent | nothing |
| `before-write-host-keep-drop` | 1 | host | empty | LEDGER_HEADER |
| `before-file-sync-process-death` | 2 | process death | complete (unsynced) | nothing |
| `before-file-sync-host-vanish-drop` | 2 | host | absent | nothing |
| `before-file-sync-host-keep-drop` | 2 | host | empty | LEDGER_HEADER |
| `before-file-sync-host-keep-torn` | 2 | host | torn (30 B) | LEDGER_HEADER, RECOVERY{torn_incomplete} |
| `before-file-sync-host-keep-keep` | 2 | host | complete | nothing |
| `before-dir-sync-process-death` | 3 | process death | complete | nothing |
| `before-dir-sync-host-vanish-drop` | 3 | host | absent (bytes were synced; the name was not) | nothing |
| `before-dir-sync-host-keep-drop` | 3 | host | complete | nothing |
| `after-fence-process-death` | after the rotation returned, the REQUEST_SENT gate synced into n+1 and its effect ran | process death | complete + gate | RECOVERY{possible_duplicate_spend} |
| `after-fence-host-vanish-drop` | same | host (vanish requested; the fenced name is kept) | complete + gate | RECOVERY{possible_duplicate_spend} |

**Second restart** (`test_o2_5_a_second_restart_preserves_file_and_name_durability`). The first process dies before call 2; its evidence is inherited, and a restart (start + `resume`) dies at the cut below. Host loss (`vanish/drop`) is applied over both processes, then a third start.

| Node id | Restart dies | Survivor | Third start writes |
|---|---|---|---|
| `before-its-fence` | before its first `fsync(ledger/)` (after `fsync(session/)`) | absent | nothing |
| `after-its-fence` | at its first call after that fence returned (the `open` of segment n+1) | empty, name kept | LEDGER_HEADER |
| `at-its-checkpoint` | before its CHECKPOINT frame's fsync (CK4/CK5 done) | complete (header synced by SV024-01; CHECKPOINT dropped) | nothing; pre-fix: A15 stop |

**Failed fences** (`…failed_namespace_fence…`):
- `rotation`: the live rotation's `fsync(ledger/)` returns EIO.
- `restart`: after a process death before call 3, the restart's own ledger fence returns EIO, and no session is returned; host loss then takes the unfenced name.

**Every recovery asserts:**
- no stop (hence no false `ledger_prefix_missing`) and classification A9
- exactly the listed records written, none of them REQUEST_SENT/INVOKING
- no GC record after the cut's GC_DONE, no `gc_collected`
- blobs unchanged; segments only gain n+1
- the newest CHECKPOINT record identical to the one before the cut
- IDENTITY and the other protected files byte-identical (in the second-restart cases: IDENTITY, conversation.json, HANDOFF.md; `run.json`'s `covers_seq` ≤ the ledger's last seq)
- no RECOVERING/STOPPED/FSYNC_FAILED/ACKNOWLEDGED left
- messages, and full state where no possible spend is involved, equal to the pre-cut values
- for `after-fence`: one surviving gate, one possible spend for its label, next label attempt+1, and the effect ran once

The next dependent unit is then appended and rotated. Two further starts follow: the first continues A9 with the expected messages, and the second writes and removes nothing.

## 6. Controls

| Control | Node / run | Result | Distinguishes |
|---|---|---|---|
| M1, source mutation: `fsync(ledger/)` removed from `open_segment` (marked `# MUTATION`) | run M1 on `…[after-fence-host-vanish-drop]` | FAILED, `'absent' == 'complete'` | the integrated oracle detects a rotation whose name is unfenced when an effect depends on it. Restored byte-for-byte; `grep MUTATION` over services/tests is empty |
| Pre-fix runtime | R1 `…[at-its-checkpoint]` | FAILED with A15 | the second-restart oracle detects readable-but-unsynced bytes covered by a durable checkpoint cover. The unmodified code is the control; no separate mutation was needed |
| In-test control: once armed, `fsync(ledger/)` returns but protects no name | `test_o2_5_negative_control_an_ineffective_rotation_fence_loses_an_effects_gate` (passes by showing the property break) | the effect ran, its REQUEST_SENT vanished with the name, and the next start would reuse the sent label | the model can lose a name only where no fence returned |
| Model discriminator: reading is not promotion | `second_restart[before-its-fence]` | the read header stays unfenced and unsynced in the model | inheritance, not readable bytes, sets the baseline |

## 7. Observed behaviour, not changed

In the integrated session path a vanished name is recreated **at the next unit boundary**. The start itself writes nothing (TC0). The next unit's record is appended to the old segment, already at or over `segment_max`, and the rotation that follows creates n+1 with `first_seq` equal to that record's seq + 1. The isolated foundation test rotates explicitly before appending. This is consistent with v2 §1.4.6 (rotation only at unit boundaries; the read bound allows one unit's overshoot). The node asserts it exactly, and no runtime change was made for it.

## 8. Scope and blast radius

Runtime files changed: `services/chassis_persistence.py` and `services/chassis_session.py` (SV024-01 only). New: `tests/test_chassis_namespace.py`, `docs/planning-context/sv024/STATUS.md`, this receipt. No retained test or assertion was changed.

Static note on unselected tests, which were not run. The only behavioural difference is one extra segment fsync when a continued writer reaches a checkpoint or rotation before any append. An unselected test that asserts an exact call sequence or counts the n-th `.svl` fsync inside such a first checkpoint could see a shifted index. I did not find such an assertion among the retained harnesses I read. For example, `recovery_live` `CUTS[after-first-record]` counts fsyncs in a recovering start that appends its core before any checkpoint. I did not inspect all files, and no broader suite was run. The coordinator or reviewer may choose to widen the selection.

## 9. Evidence kinds and residual non-claims

- **Modelled versus actual process evidence:**
  - Actual process: the in-process "process death" (`Crash` before a real filesystem call; completed calls stay), and the one conditional real-process node F6 (real recorder and `chassis.py` with a local stub; it does not exercise name loss).
  - Modelled: every host loss, name disappearance, byte loss and torn prefix. These are simulated by `host_loss` on real files in temporary roots.
- No real power-loss, kernel, filesystem or storage experiment is claimed, and nothing about real-session behaviour.
- **Truncation reversion is not simulated.** For example, the quarantine's truncation of a torn header cannot revert in the model. Like SV-023, no such claim is made.
- Rename reversion (run.json, conversation files, IDENTITY, blobs, markers) is **not** modelled here. Name loss is modelled for ledger segment names only. Names of ledger/, blobs/ and corrupt/ remain covered by the accepted isolated SV020-01 nodes, not by this matrix.
- The torn survivor uses one prefix length (30 bytes) under a valid TC1. Arbitrary garbage under M-2 is not in this slice.
- SV024-01 also covers a readable but unsynced ordinary record at the end of the continued segment before a checkpoint. That case is **not** separately evidenced.
- Not examined or claimed: a RECOVERING intent written over a readable but unsynced prefix before `continue_after` (a possibly analogous ordering in `_recover`). It is outside this slice and was not traced.
- Unchanged and not claimed: exact replay bounds, bootstrap-preserving and lost-ledger resolutions, provider/deployment evidence, merge, H/T/Q, pump.

## 10. Correction 1 (Astra SV024-02)

§1–§9 describe runtime/tests `0ac2245fc93032146a1fc19060ece18276ce9157`. The independent review (`SV-024-Astra-review.md`, head `d94bc78`) accepted SV024-01 for its A15 trace. It found SV024-02: a durable RECOVERING could be published before the unfenced, unsynced torn header it names was durable, so after a host loss the next start stopped `recovery_intent_copy_missing`. §9's caveat about an untraced recovery intent was this case.

The fix is in `services/chassis_startup.py` (`_fence_intent_inputs` before intent publication). Six regressions and controls were added to `tests/test_chassis_namespace.py`; the review's trace and one control failed first on the reviewed runtime. Final: 161 selected passes in 8 serial commands. Details, ordering, failure behaviour, the one shifted cut in an existing node and limits: `checkpoint-001-astra-corrections.md`. Not accepted; awaiting re-review.
