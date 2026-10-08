# SV-024 status

**Accepted within the isolated temporary-fixture engineering scope.** Independent acceptance: [ASTRA-ACCEPTANCE.md](ASTRA-ACCEPTANCE.md), reviewed head `9e792a56d9db4292fe7b358442c39031e78735c2`, runtime/tests `9bdfb37a5518687666f414b7579d245e3c6a7c95`. SV024-01 and SV024-02 are closed. Final validation: 161 pass executions representing159 unique cases. Earlier statuses below are historical and superseded here.

Acceptance covers declared simulated post-GC segment-name/data outcomes, inherited bytes before checkpoint publication, and recoverable input evidence before intent publication. No real power-loss or unsimulated reversion, exact replay-bound, real-session, merge/deployment, provider or held policy claim. Coverage qualification: the retained numeric `after-first-record` fsync cut moved to truncation after the new prerequisite; its old cut placement is not claimed. A test-only semantic-cut repair is staged with SV025 before future evidence advertises that cut again.

---


## Correction 1 (Astra SV024-02) — complete; awaiting the coordinator's checkpoint and Astra re-review. Not accepted.

SV024-02 is fixed in `services/chassis_startup.py`. Before a new RECOVERING is published, `_fence_intent_inputs` fsyncs the anchor's and the tail's segments and fences ledger/. A failure there is a persistence failure with no intent, copy or truncation. SV024-01 is unchanged.

The new regressions were run first on the reviewed runtime: `[name-lost]` and `[name-kept-data-lost]` stopped `recovery_intent_copy_missing` as traced, and the `[segment-fsync]` control found RECOVERING already published. Final serial runs: namespace 28, recovery_live 97, frozen batches 8+6+11+2+8, conditional 1 — 161 passes in 8 commands, with no failures. The cut index of one existing recovery_live node shifted; its assertions are unchanged. Details: `checkpoint-001-astra-corrections.md`.

Initial declaration (kept):

Review: `SV-024-Astra-review.md`, head `d94bc78e3cf69daec028b43fee180f88e559897d`, runtime/tests `0ac2245fc93032146a1fc19060ece18276ce9157`. SV024-01 was accepted for its A15 trace and is kept unchanged. SV024-02 (P2) is open: a durable RECOVERING could be published before the unfenced, unsynced torn header it names was durable.

Provenance: an earlier correction attempt was interrupted after it had read the review and the runtime sources. The coordinator verified that its process and scope were absent, that no completion receipt existed and that the checkout was clean. No edits or tests from that attempt are evidenced. This attempt continues the same task from that state.

**Declared extension of `tests/test_chassis_namespace.py`** (frozen before its first run). There are 6 new cases, so 28 in total, and the original 22 are unchanged.

1. `test_sv024_02_a_partial_header_behind_a_published_intent_converges` — 3 cases. The first process's armed rotation header write stores only 30 bytes, then the process dies (M-1 in-flight write; watermark 0, name unfenced). A restart inherits both maps and dies at its first call after RECOVERING's `rename` + `fsync(session/)` returned, before any quarantine copy. Then:
   - `name-lost`: host loss `vanish/drop`.
   - `name-kept-data-lost`: host loss `keep/drop`.
   - `interrupted-again`: process death only. A third process inherits the maps and dies at its first call after the quarantine `truncate`. Then host loss `vanish/drop` is applied over all three processes.

   The next start converges, with exact fragment evidence (one corrupt/ copy equal to the 30 bytes, one `torn_incomplete`), then the dependent unit and two further starts, all with the existing `recover`/`continue_and_converge` oracle.
2. `test_sv024_02_a_failed_pre_intent_fence_publishes_nothing` — 2 cases: `segment-fsync` and `ledger-fence`. Same partial header; the restart's pre-intent fence returns EIO. The test expects no RECOVERING published, no corrupt/ copy, no truncation, no `.svl` write, the fragment unchanged, FSYNC_FAILED present and A1 next. After acknowledgement in the temporary root, the start converges.
3. `test_sv024_01_a_failed_inherited_segment_fsync_publishes_no_checkpoint` — 1 case. After a `before-file-sync` process death, the restart's `sync_inherited` fsync returns EIO inside its first checkpoint. The test expects no CK4/CK5 change (conversation.json, run.json byte-identical), no CHECKPOINT, no new segment created, the session broken, no effect and A1 next.

Expectation on the unmodified reviewed runtime: cases 1 fail (the `recovery_intent_copy_missing` stop or a lost name), cases 2 fail (there is no pre-intent fence), and case 3 passes (SV024-01 is present).

---

**Implementation and bounded validation complete; awaiting the coordinator's checkpoint and independent Astra review. Not accepted.** The integrated O2-5 slice is closed in the fault model, and one evidenced defect (SV024-01: a false A15 after a readable but unsynced rotation header was covered by a durable checkpoint cover) is fixed in `services/chassis_persistence.py` and `services/chassis_session.py`. Final tree: 58 selected passes in 7 serial commands (35 retained + 1 conditional + 22 new), with no failures. Pre-fix failure R1 and mutation M1 are control evidence, not passes. Details, mappings and non-claims: [RECEIPT.md](RECEIPT.md). No Git call; temporary roots only.

---

Earlier status (kept): **In progress (worker). Not accepted.** Base: accepted SV-023 head `8bffe49ecf546d8581fb6e34bff6eb9e096d8841`, runtime/tests `fb638a6f4f65e382a7cdb7f691fe9cd82cbd208e` (final review `SV-023-Astra-correction-2-review.md` = `docs/planning-context/sv023/ASTRA-ACCEPTANCE.md`). Scope: `SV-after-023-roadmap.md` (integrated O2-5), `SV-024-targets-preflight.md`, frozen targets `SV-024-bounded-targets.json` (35 retained cases, two conditional batches, new `tests/test_chassis_namespace.py`). Opus 5.5. The worker makes no Git call; the coordinator commits, scans and backs up after the worker stops.

## Checkpoint 0: design fixed, parameterization declared, nothing run

Inputs read: the roadmap and preflight, the SV-023 final review, SV-015 v2 §1.4.8, the §1.4.10 rotation row and O2-5 (l.957), sv022/sv023 STATUS and RECEIPT; `services/chassis_persistence.py` (`LedgerWriter`), `chassis_session.py` (checkpoint, collection, rotation), `chassis_startup.py` (`_recover`), `chassis_gc.py` (`unauthorized_prefix`); harnesses `tests/test_chassis_gc.py` (`CutOps`, `lose_unsynced`), `test_chassis_durability.py` (isolated O2-5, SV020-01), `test_chassis_recovery_live.py` (`Root`).

**Gap confirmed statically.** `CutOps` carries segment-byte watermarks and undoes unfenced unlinks. It never takes back a *created* name, so the integrated matrix cannot lose a rotation's new segment.

**Fault model (tests only).** `NameOps(CutOps)` also records each segment name created with `O_CREAT` since the last returned `fsync(ledger/)`. A returned directory fsync clears that list. Byte watermarks (returned file fsyncs) and name fences (returned directory fsyncs) are separate. After a process death, both are handed to the next process by reference (`inherit()`). Opening or reading a file promotes neither. `host_loss(ops, names, data)` can take back only what neither covers. It may remove a name whose fence never returned (`vanish`) and drop bytes after a file's watermark (`drop`), keep a strict prefix (`torn`, ≤ 30 bytes) or keep them (`keep`). Unfenced unlinks are undone, as in SV-022. After a simulated host loss, the next process starts with a fresh model, because the on-disk state is then the durable state.

**Fixture.** The lineage is built with `begin` plus three tool turns, using collection on and `segment_max = 1`. Segment 0 and the oldest records are physically gone. One message is then appended. The next checkpoint collects for real: GC_INTENT, unlinks and fences, then GC_DONE. Only the rotation that follows that GC_DONE is armed, and the test asserts that this is so.

**Armed rotation calls** (`LedgerWriter.open_segment`): 0 `open(n+1, O_CREAT|O_EXCL)`, 1 `write(header)`, 2 `fsync(n+1)`, 3 `fsync(ledger/)`. These map to the cuts as follows:

| cut | process dies before | name | header bytes |
|---|---|---|---|
| `before-write` | call 1 | created, unfenced | none |
| `before-file-sync` | call 2 | created, unfenced | written, unsynced |
| `before-dir-sync` | call 3 | created, unfenced | synced |
| `after-fence` | after the rotation returned, the next unit's REQUEST_SENT gate was synced into n+1 and its effect ran | fenced | synced |

**Declared finite parameterization of `tests/test_chassis_namespace.py`** (frozen before its first run; 22 cases). Only physically permitted outcomes are included, with no cross-product:

1. `test_o2_5_after_gc_rotation_survivors_recover_without_a_gap` — 13 cases (cut, loss → expected new-name shape):
   - `before-write`: process death → empty; host `vanish/drop` → absent; host `keep/drop` → empty
   - `before-file-sync`: process death → complete; host `vanish/drop` → absent; `keep/drop` → empty; `keep/torn` → torn; `keep/keep` → complete
   - `before-dir-sync`: process death → complete; host `vanish/drop` → absent; `keep/drop` → complete (a returned file fsync protects bytes, not the name)
   - `after-fence`: process death → complete; host `vanish/drop` → complete (a returned directory fence protects the name)
2. `test_o2_5_a_second_restart_preserves_file_and_name_durability` — 3 cases. The first process dies `before-file-sync` (a readable, unsynced header and an unfenced name), and its evidence is inherited. The finishing restart (start + resume) is then interrupted `before-its-fence` (before its first `fsync(ledger/)`), `after-its-fence` (at the first call after that fence returned) or `at-its-checkpoint` (before its CHECKPOINT frame's fsync). Host loss `vanish/drop` is then applied over both processes, followed by a third start.
3. `test_o2_5_a_failed_namespace_fence_after_gc_allows_no_effect` — 2 cases: `rotation` (the live rotation's `fsync(ledger/)` fails) and `restart` (after `before-dir-sync` process death, the restart's own ledger fence fails, then host loss).
4. `test_o2_5_previous_base_replay_survives_a_lost_rotation_name` — 2 cases: `absent` (`before-dir-sync`, `vanish/drop`) and `torn` (`before-file-sync`, `keep/torn`). After recovery, the accepted `assert_a14_recovers_exactly` runs from the real retained previous base.
5. `test_o2_5_negative_control_an_ineffective_rotation_fence_loses_an_effects_gate` — 1 case. An in-test control in which the ledger fence covers no name shows that the `after-fence` oracle detects an effect whose gate vanished.
6. `test_o2_5_the_rotation_calls_are_exactly_the_mapped_cuts` — 1 case: the armed call log equals the mapping above.

**Assertions per recovery:** the start does not stop (so no false `ledger_prefix_missing`) and classifies A9. Old-end TC0 at GC_DONE is checked when the name vanished. The recreated header continues seq and chain with no segment-number gap. A torn header leaves exactly one corrupt/ copy and one `torn_incomplete`. State, messages and next label are unchanged (for `after-fence`, one possible spend and attempt+1). The newest CHECKPOINT record, IDENTITY and the other protected files are unchanged. GC_INTENT/GC_DONE counts and blobs are unchanged, and no segment is removed. Recovery writes no REQUEST_SENT/INVOKING and runs no effect. A further start writes nothing.

**Defect hypothesis, to be confirmed or refuted by case 2 `at-its-checkpoint` on the unmodified runtime.** `continue_after` fences names but not bytes it only found readable. A finishing restart's first checkpoint can therefore make `run.json` durable with `covers_seq` = the inherited header's seq before any fsync of that segment (CK5 before CK6). Host loss then leaves the fenced name empty, and the next start would stop `checkpoint_ahead_of_ledger` (A15). Runtime code is changed only if the trace demonstrates this.

## Execution log

(one literal runner command per message; filled in as runs complete)

- **R1** `tests/test_chassis_namespace.py`, unmodified runtime (pre-fix): 15 passed, then `test_o2_5_a_second_restart_preserves_file_and_name_durability[at-its-checkpoint]` FAILED; the runner stops at the first failure, so the 6 later nodes did not run. Observed: `Opening(classification='A15', stop='checkpoint_ahead_of_ledger', detail={'covers_seq': 42, 'last_seq': 41})`. Trace: rotation after GC_DONE seq 41 wrote header seq 42 into segment 8; process death before its file fsync; the restart fenced the name (ledger/ fsync returned) but never synced the readable header; its first checkpoint made `run.json` durable with `covers_seq = 42` (CK5), then died before the CHECKPOINT frame's fsync; host loss kept the fenced name and dropped the never-synced header; the next start stopped A15. **The defect hypothesis is confirmed**; the fix follows.
- **Fix (SV024-01).** In `services/chassis_persistence.py`, `LedgerWriter.inherited` is set by `continue_after` when it continues an existing segment and is cleared by any returned append fsync. The new `sync_inherited()` fsyncs that segment once, and is called by `services/chassis_session.py` `Session.checkpoint` before CK1–CK5 and by `open_segment` before rotating away. A failure is the ordinary persistence boundary. No other runtime change.
- **R2** `tests/test_chassis_namespace.py`, fixed tree: 22 passed.
- **M1** (source mutation): removed `sync_dir(ledger/)` from `open_segment`. `…survivors…[after-fence-host-vanish-drop]` FAILED as expected (`assert 'absent' == 'complete'`: the name holding an effect's synced gate vanished). Restored byte-for-byte; `grep MUTATION services/ tests/` is empty.
- Conditional selection: the fix changes `Session.checkpoint` on every resumed start, including the real script before its first request. So the frozen conditional `tests/test_chassis_correlation.py::test_recorder_in_loop_identity_survives_collection_and_a_later_interruption` is added. Previous-base selection is unchanged, so the two O2-2 conditional nodes are not added.
- **Final tree** (after M1's restore), serial: F1 batch A 8 passed; F2 batch B 6 passed; F3 batch C 11 passed; F4 batch D 2 passed; F5 batch E 8 passed; F6 conditional correlation 1 passed; F7 `tests/test_chassis_namespace.py` 22 passed. Total 58 passes. No command was denied, retried or overlapped.

## Activation boundary

SV024-01 is active on every resumed start: one extra segment fsync when a continued writer reaches a checkpoint or rotation before any append. All exercised faults were in temporary roots. No real session was read, written, repaired, acknowledged or deleted.

## Files changed by SV-024 (relative to `8bffe49`)

Modified: `services/chassis_persistence.py`, `services/chassis_session.py`. New: `tests/test_chassis_namespace.py`, `docs/planning-context/sv024/STATUS.md`, `docs/planning-context/sv024/RECEIPT.md`. No retained test or assertion changed. The worker made no Git call.
