# SV-025 status

**Complete; awaiting the coordinator's commit/backup and Astra's independent review. Not accepted.** Test-only replay-work accounting and proof package. No runtime source was changed.

**Outcome.** Newest bytes < 25,166,144 is **refuted** at default constants by a 28,311,552-byte A11 suffix blob that replay opens. Restart accounting is **refuted** structurally: `since_bytes` restarts at 0. Previous records ≤ 717 is **refuted** at default constants: the actual retained `prev` is A, three checkpoints back, and A14 replays 730 records. Newest records ≤ 358 and previous bytes < 50,352,266 are **not proved**: their premises fail statically and neither has been executed as a counterexample. The current serializer shapes exceed 7 literal maxima. Follow-up obligations P1–P5 and design options are in [RECEIPT.md](RECEIPT.md) §6 and §9. The maintenance item is separate: the `after-first-record` cut is now tied to the first recovery append, 8/8 passing. Final validation: **20 passes in 2 commands** (M1 8, B1 12), plus control M0.

Base: accepted SV024 `944e9d3e21987093cb78ff150d74e4e55900ad57` (SV024 accepted: `SV-024-Astra-correction-1-review.md` = `docs/planning-context/sv024/ASTRA-ACCEPTANCE.md`). Launch manifest: `SV-025-bounded-targets.json`. Scope: `SV-025-bounds-preflight.md`. Runner: `python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <targets>`, one literal command per message, awaited, from the repository root. The worker makes no Git call; the coordinator commits and backs up.

## Checkpoint 0: inputs read, parameterization frozen, nothing run

Read as source text: SV-013 §2.2.5 and C-G2 (l.663, l.1331); SV-015 v2 §§1.2, 1.4.1–1.4.10; `SV-015-literal-values-v2.json` (`ledger_frame_max_bytes`, `recovery_unit`, `recovery_bound_defaults`); `SV-015-literal-generator-v2.py.txt` l.89–129 (read, **not executed**); the SV024 acceptance and coverage qualification. Runtime: `services/chassis_session.py`, `chassis_startup.py`, `chassis_replay.py`, `chassis_persistence.py`, `chassis_gc.py`, `chassis_envelope.py` and the session paths in `chassis.py`. The static reconciliation is in [RECEIPT.md](RECEIPT.md).

### Declared finite parameterization of the new `tests/test_chassis_bounds.py` (frozen before its first run; 12 cases)

All fixtures use temporary roots and the accepted runtime unchanged. Instrumentation is test-only. The `Observer` is a `DurableOps` subclass that records every `read` (kind, name, bytes returned) and keeps no data. A monkeypatched wrapper attributes each `Replay.apply` to the record's seq, so a blob read can be tied to the record whose replay opened it. Frame lengths come from an independent byte walker over the segment files (`49 + plen + 66` read from each header), not from the writer and not from `since_bytes`.

1. `test_sv025_canonical_maximal_shapes_reproduce_through_the_runtime_encoder` — 1 case. The generator's maximal payloads (from its text, l.90–117) are encoded with `cp.encode_frame` at seq 10¹²−1. Expected: the 13 literal frame sizes are reproduced exactly (TURN_RESPONSE 680,003 … CHECKPOINT 19,978). The generator's ORIGINAL_EVICTED `{"sha256"}` is refused by the runtime, which requires `sha`; the runtime shape is 189 bytes.
2. `test_sv025_current_serializer_shapes_exceed_the_canonical_maxima` — 7 cases, as id → canonical → expected current frame:
   - `request-sent-lineage16`: 208 → 216 (runtime lineage `uuid4().hex[:16]`); `-64` legacy lineage → 264, in the same case
   - `recovery-spend-next`: 206 → 270 (`detail.next`, 16-character lineage)
   - `unrun-ended-reason`: 254 → 263 (runtime text `not run: the run ended by handoff in call <wire>`)
   - `done-exception-type`: 415 → 1,351 (`raised:` plus a 1,000-character exception class name; no runtime cap)
   - `msg-append-inline-control`: 4,259 → 24,739 (4,096 UTF-8 bytes of U+0001 stay inline; the body escapes each byte as `\u0001`)
   - `note-adoption-gen`: 227 → 244 (MSG_APPEND `note` with `gen`; replay opens its blob)
   - `checkpoint-current-state`: 19,978 → 21,746 (16-character lineage, `requests.next`, `adopted_mirror_sha256`, `dropped_pending_limit`, pending `mirror_sha256` and `foreign`)
3. `test_sv025_positive_an_ordinary_unit_crosses_the_byte_threshold_once` — 1 case. Injected `bytes_max = 20,000`. After a restart at a clean checkpoint, four 6,000-byte direct messages (blob-bearing) run in one process. Expected: for units 1–3, observed frame + opened-blob bytes after C_n's frame equal `since_bytes`, stay below 20,000, and no checkpoint is written. Unit 4 checkpoints at once, and the observed interval lies in [20,000, 20,000 + that unit). This is structural evidence only, not proof of the default constants.
4. `test_sv025_a_restart_forgets_outstanding_suffix_bytes` — 1 case. Same injected threshold. Two blob messages, then process death (no checkpoint). The restart observes the outstanding suffix with `since_bytes == 0` (`since_records` is rebuilt). Two more messages follow and no checkpoint is written, and a third start observes outstanding suffix work ≥ 20,000. Expected: the contradiction is asserted explicitly.
5. `test_sv025_a_27_mib_external_edit_blob_alone_exceeds_the_newest_byte_bound` — 1 case. Default constants. Establish, replace conversation.json with a valid ASCII list of exactly 28,311,552 bytes (27 MiB), then A11. Expected: the startup's counter is ≥ RECOVERY_BYTES_MAX with no checkpoint, and the live reducer re-reads its own blob once. On restart (A9t, nothing written), replay opens the EXTERNAL_EDIT blob once for 28,311,552 bytes. That is above 25,166,144 on its own, read separately from the excluded base-file read of conversation.json. `since_bytes == 0`, and accepted memory and classification are unchanged.
6. `test_sv025_the_retained_previous_base_can_be_older_than_the_last_checkpoint` — 1 case. Default constants and production `collect=True`. Establish A (prev none) and B (prev A). Then 3 rounds, each of: an external edit, restart A11, 240 direct messages (no threshold checkpoint: peak `since_records` 242 < 256), and one boundary checkpoint. Expected: every new checkpoint names `prev = A` and `.prev.json` still holds A's bytes. Checkpoint intervals are 3, 242, 242 and 242 records. conversation.json is then damaged in the temporary root, giving A14. The actual previous-base replay applies seqs 4..733 once each, which is 730 records > 717, and its intermediate hash matches C_n. The restored file equals C_n and the A14 notice is appended. Static minimum for this shape: 3 rounds × 236 messages (718); 240 is used for margin.

Declared expectation: cases 1, 2 and 3 pass as positive or shape controls, and cases 4, 5 and 6 pass by asserting the observed contradiction of a canonical premise. A pass of 4, 5 or 6 is a counterexample, not a guarantee.

### Declared maintenance (separate from replay-bound claims): 8 cases of one function

`tests/test_chassis_recovery_live.py::test_a_crash_inside_recovery_never_turns_unknown_into_unrun`. The `after-first-record` cut fires on the second `.svl` fsync, which since SV024 is the truncation fence. It is replaced by a predicate tied to the first recovery record: an fsync of a `.svl` whose immediately preceding filesystem event was a write to the same path, which is an append's own fsync. After the crash, for both TC2 and TC4, the test verifies the following. The last two events are that write and that fsync, and exactly two `.svl` fsyncs (pre-intent fence and truncation) preceded them. The ledger ends `TURN_RESPONSE, SYNTH{[turn,0], unknown_damaged_tail}`. RECOVERING and exactly one ledger quarantine copy exist. Every existing assertion and the other three cuts are unchanged.

Runs, in order:
- **M0** (control): the new verification with the **old** numeric trigger. Expected: an `after-first-record` case fails at the event check, because the crash is at the truncation fsync and no append preceded it.
- **M1**: the semantic predicate. Expected: 8 passed.
- **B1**: `tests/test_chassis_bounds.py`. Expected: 12 passed.

## Execution log

(one literal runner command per message; filled in as runs complete)

- **M0** (control; old numeric trigger plus new verification): 6 passed (after-intent, after-copy and after-truncate × TC2/TC4), then `[after-first-record-tc2-invoking]` FAILED at the new event check. The runner stops at the first failure, so `[after-first-record-tc4-acknowledged]` did not run. Observed last events: `truncate(000000.svl)`, `open(000000.svl)`, `fsync(000000.svl)`. The old cut is the truncation fence and no append preceded it, as the SV024 qualification said. Not a pass; control evidence only.
- **M1** (semantic predicate, final): `tests/test_chassis_recovery_live.py::test_a_crash_inside_recovery_never_turns_unknown_into_unrun` — **8 passed**. For TC2 and TC4, the crash is in the first recovery record's own fsync, after the pre-intent fence and truncation fsyncs, with SYNTH{[turn,0], unknown_damaged_tail} durable-readable and RECOVERING present. All earlier assertions hold.
- **B1** (final): `tests/test_chassis_bounds.py` — **12 passed** on the first run. Every pre-registered exact value matched: 13 literal frames, 7 current shapes, 28,311,552-byte blob read once with 2 segment scans, 730 replayed records, interval sizes 3/242/242/242.

Neither file changed after its run. No command was denied, retried or overlapped. No broad suite, provider, real session, install, Git call or ad-hoc Python was used. `ruff` was not run.

## Files changed by SV-025 (relative to `944e9d3`)

New: `tests/test_chassis_bounds.py`, `docs/planning-context/sv025/STATUS.md`, `docs/planning-context/sv025/RECEIPT.md`. Modified (test only): `tests/test_chassis_recovery_live.py` (one function's `after-first-record` trigger and its added verification). No runtime file changed.
