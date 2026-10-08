# Independent acceptance — SV025

Accepted by OpenAI Astra at immutable head `2ce8bad76c23a86d0962df90525c0c1509bbd126` (test commit `082d5efa3f56bac2b27b85498bf9c049c3cbddbc`). See [ASTRA-ACCEPTANCE.md](ASTRA-ACCEPTANCE.md) for the precise evidence levels and [ASTRA-INITIAL-REVIEW.md](ASTRA-INITIAL-REVIEW.md) for closed findings.

This is acceptance of the test/evidence package, not a numerical recovery guarantee or runtime change. Two exact inequalities have executed default-constant counterexamples; the two others and the aggregate turn maxima remain unproved. Corrected bounds16 passed in one command; unchanged maintenance8 retain their earlier evidence, not24 fresh executions. Services remain unchanged from accepted SV024. All real-session, deployment, source/oracle and product-policy holds remain.

---

# SV-025 status

## Correction 1 (Astra SV025-01, SV025-02 and two wording items): complete, C1 16 passed. Not accepted.

Review: `SV-025-Astra-review.md`. Reviewed head `43c1d615e24cc9b4eaa4d850b76df65f152b0d06`; test commit `a6ca2b6f217c49f4d1ccfe4bc38139ad59d825fb`. Only `tests/test_chassis_bounds.py`, this file and RECEIPT.md change. No runtime service, canonical generator or literal, or maintenance test changes.

**What is superseded.** The first round's "current serializer shapes exceed 7 literal maxima" claim is withdrawn as stated. Three of those rows were not valid runtime witnesses:
- the 21,746-byte CHECKPOINT came from a state that `SessionState.from_wire` rejects;
- the 1,351-byte DONE inherited `stored_E = 10¹²−1`, but `record_result` stores at most 32,768;
- the inline MSG_APPEND used kind `notice` with a 12-digit epoch for a direct message.

The receipt's "34 originals, so 34 evictions" argument and its conclusion that U_r = 103 and U_b(turn) = 3,333,164 "are not runtime maxima" are also withdrawn (SV025-02). The historical text below is kept as provenance. Where it differs from this section, this section governs.

**Frozen correction parameterization of `tests/test_chassis_bounds.py`** (declared before its first run; 16 cases). Unchanged: case 1 (generator reproduction, now labelled synthetic arithmetic) and cases 3–6 (positive control, restart accounting, 27 MiB, older prev). Old case 2 (7 nodes) is removed and replaced by:

- **2a** `test_sv025_legal_domain_models_exceed_the_canonical_maxima` — 4 legal-domain models, not driven through a real history. Each case asserts its source-domain relations first. Exact sizes are pre-registered:
  - `request-sent-lineage16` 216/264 (lineage length of `uuid4().hex[:16]`; a 64-character legacy lineage accepted by `LINEAGE_ID`)
  - `recovery-spend-next` 270 (label attempt 10¹²−2, `next.attempt` = that + 1, as `derive_core` emits)
  - `unrun-ended-reason` 263 (call index 15 < CAP_CALLS; wire id ≤ 64 characters matching `WIRE_ID`)
  - `note-adoption-gen` 244 (distinct blob hash)
- **2b** `test_sv025_a_valid_current_checkpoint_state_round_trips_and_exceeds_the_literal` — 1 case, a legal-domain model. The state is built as `SessionState` and serialized by `to_wire(next_seq = covers + 2)`; `from_wire(...).to_wire(...)` round-trips exactly. The test asserts:
  - 16 contiguous pending generations after `adopted_through`, `next_gen` following them, each 65,536 bytes;
  - 64 originals of 65,536 bytes each (≤ 256 KiB item; aggregate exactly 4 MiB);
  - 80 distinct sorted live names and 17 mirrors;
  - `recap_folded` ≤ the message count of a 64 MiB readable list;
  - `prev.covers_seq < prev.checkpoint_seq ≤ covers_seq < seq = covers_seq + 1`, and `next_seq = seq + 1 ≤ 10¹²−1`.

  The frame is then measured. Pre-registered by hand from the delta to the generator shape: **21,173 > 19,978**. If the measurement differs, the measured value is reported. If it does not exceed 19,978, the exceedance is withdrawn.
- **2c** `test_sv025_encoder_acceptance_alone_does_not_validate_a_checkpoint_state` — 4 controls: `generator-model` (the first-round model), `noncontiguous-generation`, `repeated-live-set` and `oversize-original`. Each is accepted by `encode_frame` and rejected by `SessionState.from_wire` with StateError.
- **2d** `test_sv025_emitted_records_exceed_the_canonical_maxima` — 1 case, **emitted**. After `establish`, a direct `append_message("user", "\x01" × 4,096)` stays inline: 24,726 bytes on disk > 4,259. One invoked call's exception, a class named with 1,000 characters, goes through the actual `chassis.Chassis.invoke_outcome` and `record_result`. The result is DONE with `stored_E = original_bytes = 1,013` ≤ 32,768, at 1,313 bytes on disk > 415.
- **2e** `test_sv025_default_caps_admit_at_most_18_new_originals_per_response` — 1 case, pure `adopt_response` with default Caps and 32 distinct malformed JSON argument strings of 603 bytes. Expected admits: calls 0–15 `bad_args`, calls 16–31 `not_run_call_limit`. With content and reasoning each at cap+1, the original fields are content, reasoning_content and arguments 0–15: 18 distinct, each ≤ 256 KiB. At exactly their caps, only the 16 argument originals appear. No eviction-record count is claimed.

Count: 1 + 4 + 1 + 4 + 1 + 1 + 4 = 16. Run plan: **C1** `tests/test_chassis_bounds.py` (expected 16 passed). Maintenance is unchanged and not rerun.

Wording corrections: the observer logs **successful returned reads** only; the recovery cut's SYNTH is **written and readable at the injected process-death cut**, not durable (its fsync had not run).

### Correction 1 execution log

- **C1** `python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 tests/test_chassis_bounds.py` — **16 passed**, first run, no failures. Every pre-registered value matched:
  - legal-domain sizes 216/264, 270, 263 and 244;
  - the validated CHECKPOINT measured at **21,173 > 19,978**, so the CHECKPOINT exceedance stands at the legal-domain level, with the new value;
  - 4 encoder-accepted, `from_wire`-rejected controls;
  - emitted inline MSG_APPEND **24,726** and DONE **1,313** (`stored_E` 1,013);
  - the default admission split, 16 `bad_args` and 16 `not_run_call_limit`, with **18** new originals;
  - unchanged cases 1 and 3–6 (28,311,552-byte blob; 730 records).

  No command was denied, retried or overlapped. The maintenance function is unchanged and was not rerun. No Git call, ad-hoc Python, broad suite, provider or real session.

**Status: Correction 1 complete; awaiting the coordinator's commit/backup and Astra's re-review. Not accepted.** Current verdicts are in RECEIPT.md:
- **refuted** at default constants: newest bytes (test 5) and previous records (test 6);
- **structural**, at an injected threshold: restart accounting (test 4);
- **unproved**: newest records, previous bytes, and the aggregates U_r = 103 and U_b(turn) = 3,333,164;
- not claimed: ORIGINAL_EVICTED counts.

---

## Historical (first round; superseded where Correction 1 says so)

**Complete; awaiting the coordinator's commit/backup and Astra's independent review. Not accepted.** Test-only replay-work accounting and proof package. No runtime source was changed.

**Outcome.** Newest bytes < 25,166,144 is **refuted** at default constants by a 28,311,552-byte A11 suffix blob that replay opens. Restart accounting is **refuted** structurally: `since_bytes` restarts at 0. Previous records ≤ 717 is **refuted** at default constants: the actual retained `prev` is A, three checkpoints back, and A14 replays 730 records. Newest records ≤ 358 and previous bytes < 50,352,266 are **not proved**: their premises fail statically and neither has been executed as a counterexample. The current serializer shapes exceed 7 literal maxima. Follow-up obligations P1–P5 and design options are in [RECEIPT.md](RECEIPT.md) §6 and §9. The maintenance item is separate: the `after-first-record` cut is now tied to the first recovery append, 8/8 passing. Final validation: **20 passes in 2 commands** (M1 8, B1 12), plus control M0.

Base: accepted SV024 `944e9d3e21987093cb78ff150d74e4e55900ad57` (SV024 accepted: `SV-024-Astra-correction-1-review.md` = `docs/planning-context/sv024/ASTRA-ACCEPTANCE.md`). Launch manifest: `SV-025-bounded-targets.json`. Scope: `SV-025-bounds-preflight.md`. Runner: `python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <targets>`, one literal command per message, awaited, from the repository root. The worker makes no Git call; the coordinator commits and backs up.

## Checkpoint 0: inputs read, parameterization frozen, nothing run

Read as source text: SV-013 §2.2.5 and C-G2 (l.663, l.1331); SV-015 v2 §§1.2, 1.4.1–1.4.10; `SV-015-literal-values-v2.json` (`ledger_frame_max_bytes`, `recovery_unit`, `recovery_bound_defaults`); `SV-015-literal-generator-v2.py.txt` l.89–129 (read, **not executed**); the SV024 acceptance and coverage qualification. Runtime: `services/chassis_session.py`, `chassis_startup.py`, `chassis_replay.py`, `chassis_persistence.py`, `chassis_gc.py`, `chassis_envelope.py` and the session paths in `chassis.py`. The static reconciliation is in [RECEIPT.md](RECEIPT.md).

### Declared finite parameterization of the new `tests/test_chassis_bounds.py` (frozen before its first run; 12 cases)

All fixtures use temporary roots and the accepted runtime unchanged. Instrumentation is test-only. The `Observer` is a `DurableOps` subclass that records every successful returned `read` (kind, name, bytes returned) and keeps no data; failed or missing-file attempts are not logged (wording corrected in Correction 1). A monkeypatched wrapper attributes each `Replay.apply` to the record's seq, so a blob read can be tied to the record whose replay opened it. Frame lengths come from an independent byte walker over the segment files (`49 + plen + 66` read from each header), not from the writer and not from `since_bytes`.

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
- **M1** (semantic predicate, final): `tests/test_chassis_recovery_live.py::test_a_crash_inside_recovery_never_turns_unknown_into_unrun` — **8 passed**. For TC2 and TC4, the crash is in the first recovery record's own fsync, after the pre-intent fence and truncation fsyncs, with SYNTH{[turn,0], unknown_damaged_tail} written and readable at the injected process-death cut (its fsync had not run; no host-loss durability is claimed; wording corrected in Correction 1) and RECOVERING present. All earlier assertions hold.
- **B1** (final): `tests/test_chassis_bounds.py` — **12 passed** on the first run. Every pre-registered exact value matched: 13 literal frames, 7 current shapes, 28,311,552-byte blob read once with 2 segment scans, 730 replayed records, interval sizes 3/242/242/242.

Neither file changed after its run. No command was denied, retried or overlapped. No broad suite, provider, real session, install, Git call or ad-hoc Python was used. `ruff` was not run.

## Files changed by SV-025 (relative to `944e9d3`)

New: `tests/test_chassis_bounds.py`, `docs/planning-context/sv025/STATUS.md`, `docs/planning-context/sv025/RECEIPT.md`. Modified (test only): `tests/test_chassis_recovery_live.py` (one function's `after-first-record` trigger and its added verification). No runtime file changed.
