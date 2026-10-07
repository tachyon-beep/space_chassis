# SV-023 receipt: witnessed `continue-from-bound` for A14 and CK5 file-repair stops

2026-10-08. Launch base `d301d139cf85961a823c874d7661a7000d563d09`; accepted SV-022 runtime `53c5c44b167f73e7aefb326fdeacfdced5839835` (final review `SV-022-Astra-correction-1-review.md` = `docs/planning-context/sv022/ASTRA-ACCEPTANCE.md`). Scope: `SV-023-Astra-preflight.md`; targets `SV-023-bounded-targets.json`. Opus 5.5. Only the approved runner was used, with literal commands and temporary roots. The coordinator observed overlapping V9/V10 Bash invocations despite the serial-execution instruction; see the provenance note below. The local stub was the only upstream, and the real recorder ran only as a local subprocess. No provider, deployment, real-session repair, acknowledgement, deletion or resumption, pump, H/T/Q, account or settings change, and no broad suite. The worker made no Git call. **Awaiting independent review; not accepted.**

## 1. Final runs (final tree, after every mutation was restored)

`python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <targets>`. Counts are the runner's progress dots. Everything passed; there were no failures or skips.

| # | Targets (exact) | Result |
|---|---|---|
| V1 | `tests/test_chassis_acknowledgements.py` (new) | 44 passed |
| V2 | `tests/test_chassis_recovery_live.py` (incl. its real script restarts) | 97 passed |
| V3 | `tests/test_chassis_gc.py` | 50 passed |
| V4 | `tests/test_chassis_correlation.py` (real recorder + chassis processes) | 2 passed |
| V5 | `tests/test_chassis_replay.py tests/test_chassis_session.py` | 61 passed |
| V6 | `tests/test_chassis_notes.py tests/test_chassis_checkpoint.py` | 23 passed |
| V7 | `tests/test_chassis_adoption.py` | 50 passed |
| V8 | `tests/test_chassis_ledger.py tests/test_chassis_recovery.py tests/test_chassis_durability.py` | 114 passed |
| V9 | `tests/test_chassis_termination.py` | 67 passed |
| V10 | `tests/test_chassis_groups.py tests/test_chassis_wire.py tests/test_supervisor_flap.py tests/test_chassis_metadata.py` | 65 passed |
| V11 | the 22 retained `tests/test_chassis.py::…` + 7 `tests/test_services.py::…` nodes, listed literally as in the target JSON | 29 passed |
| V12 | the 5 `tests/test_run_end_to_end.py::…` local-stub nodes, listed literally as in the target JSON | 5 passed |

Total: 607 selected passes (44 new + 563 retained; 563 is SV-022's final retained count). Selection rationale: `chassis_startup.open_session` is on every start path, so every retained file that starts a session was run. That is the whole frozen allowlist. Nothing outside it was run.

### Failures during development (fixed before V1–V12)

- My fixture: the refusal case `missing-suffix-blob` deleted a DONE result blob and was accepted. That is correct behaviour. A lost result blob is not required: the accepted replay states it as `known_payload_lost` (C-D3), which is exactly what ordinary recovery does. The case now deletes a blob the replay requires (a long suffix MSG_APPEND), and that is refused.
- My fixture: the after-collection test counted retained GC_DONE records. Collection removes old ones with their segments, the same pitfall SV-022 recorded. It now compares the newest GC_DONE's seq.
- No retained assertion was changed. No runtime defect was found by the retained files.

## 2. Exactly the new pairs

`chassis_startup.WITNESSED_RESOLUTIONS = {(conversation_unreadable_unbound, continue-from-bound), (run_json_unreadable, continue-from-bound)}`, added to the explicit `IMPLEMENTED_RESOLUTIONS`. The three existing pairs are unchanged in code and behaviour. `chassis_persistence.ACK_RESOLUTIONS`/`DEFAULT_RESOLUTIONS` are untouched, and a test shows they still admit e.g. `ledger_missing/continue-from-bound` at the low level while `acknowledge` refuses it. Every bootstrap-preserving request is still refused, as are the lost/damaged/ahead-of-ledger requests and every newer integrity stop: `identity_*`, `recovery_intent_*`, `gc_intent_invalid`, `ledger_prefix_missing` and the new `acknowledgement_unverified`. In total 70 reason×resolution pairs were exercised, each with a byte-identical store afterwards.

## 3. Schemas and domains (engineering additions, not canonical fields)

**Stop witness**, in `STOPPED.detail.witness` (only for the two reasons):

| Field | Domain |
|---|---|
| `version` | `1` |
| `reason` | one of the two reasons; must equal the stop's |
| `stop_id` | 32 lowercase hex, random per stop (two stops with equal facts stay distinct) |
| `lineage_id` | the chassis lineage rule `[A-Za-z0-9._:-]{1,64}`, from the oldest segment header, never from run.json |
| `ledger` | `first_seq`, `last_seq` (≥1, first ≤ last), `last_chain` (hex64), `last_segment` ≤ `end_segment` ≤ 999,999, `end_offset` (counter): the strictly clean physical end |
| `checkpoint` | `checkpoint_seq`, `covers_seq` < `checkpoint_seq`, `conv_sha256`, `conv_bytes`, `chain` (the CHECKPOINT record's), `run_sha256`: the newest checkpoint |
| `identity_reserved` | the checked IDENTITY value; must cover every turn the records show |
| `check` | SHA-256 of the canonical JSON of all other fields (M-3 detection; not tamper-proof, M-6 is out of model) |

The witness is captured only when the ledger scan has no A2 stop and no tail (TC0); no RECOVERING, ACKNOWLEDGED or FSYNC_FAILED exists; there is no unauthorized prefix and no pending GC intent; the newest CHECKPOINT state validates; and IDENTITY is checked and ≥ every used turn. For A14 there must also be no recovery intent and no collection in this start. Otherwise the stop is written exactly as before (`detail: null`) and is ineligible.

**Carrier**, ACKNOWLEDGED: `{reason, resolution, ack_id, witness, evidence, check}`. `ack_id` = SHA-256(STOPPED bytes ‖ `\n reason \n resolution`)[:32], as today. `check` seals everything else.

**Evidence** (the verified plan): `witness_check`, `conv_sha256`, `run_sha256`, `replay_sha256` (the bound replay's serialized messages), `state_sha256` (canonical `to_wire` of the replayed state), `open_group` ([turn, answered] or null), `closure_sha256` (the TC0 closure `derive_core` produces).

**Receipt**, RECOVERY_ACK: `{reason, resolution, ack_id, stop_id, evidence_sha256}`. The required keys (`reason`, `resolution`) are as in v2's record table; the rest are additions. `validate_payload` is unchanged.

Sizes: the witness is under 1 KB and the carrier under 3 KB, within the existing 64 KiB marker read bound.

## 4. Mechanism (`services/chassis_startup.py`, the only runtime file changed)

1. **Stop**: `stop_witness` is called at the A14 raise (`_classify_base`, using `self.clean_end` set in `_recover`) and at the CK5 raise (`open`).
2. **Pure verifier** `witnessed_evidence`. It reuses the strict scanner, `gc.unauthorized_prefix`/`pending_intent`, `SessionState.from_wire`, `read_identity`, `_binding`, the strict `_replay`, `plan_recovery` and `derive_core`. There is no new, more permissive scanner. It requires:
   - no FSYNC_FAILED; at acknowledgement time, no RECOVERING;
   - lineage, first/last record, chain, segment and physical end exactly as witnessed;
   - IDENTITY exactly as witnessed, and the same newest checkpoint;
   - no switch, deletion or adoption after the checkpoint; the latest binding is C_n's hash (its own CHECKPOINT, or a `conversation_restored` of that hash);
   - conversation.json is exactly C_n's bytes; run.json's SHA-256 equals C_n's `run_sha256`, and its format-2 lineage, covers and conv agree;
   - every `blobs_live` blob, the suffix replay and the closure verify.
3. **Command** (`_acknowledge_witnessed`): verify, durable carrier, then STOPPED removal. It refuses before any write. Repeated with STOPPED present, it rewrites the identical carrier and removes STOPPED. Repeated after STOPPED's removal, it only re-fences session/. Any other pending carrier is refused rather than replaced. It writes no ledger record and contacts nothing.
4. **Consumption** (next start). In `open()`, right after A0/A1 and before anything else, `_verify_carrier` re-runs the verifier over the records up to the witnessed end. After that end it allows only this transaction's own deterministic sequence: headers; RECOVERY_ACK; then exactly the derived closure, in order. That sequence may end in a strict byte prefix of its next frame (an M-1 torn append), and a RECOVERING may exist if anchored at or after the witnessed end. The evidence must equal the carrier's; otherwise the start stops `acknowledgement_unverified` (no resolution, only STOPPED written). On success it fences session/. `_recover` then must classify A9/A9t and puts RECOVERY_ACK **first** in the core, unless this transaction already wrote it. The ordinary rules follow: TC0 closure, or TC1 handling of its own torn frame. `_consume_ack` finds exactly one receipt, fsyncs its segment (it may be an earlier start's readable-but-unsynced append), then removes the carrier. IDENTITY is rewritten only after that, by the existing `reserve_turns`.

Nothing in this path truncates, rewrites, rotates or deletes the ledger, blobs, corrupt/ or the fixture archive. The single exception is the existing TC1 rule applied to this transaction's own torn frame: a corrupt/ copy first, then truncation.

## 5. Reason → fixture / refusal matrix (`tests/test_chassis_acknowledgements.py`)

| Preflight fixture | Nodes |
|---|---|
| A14 file repair | `test_a_witnessed_file_repair_stop_resumes…[a14]`. The actual stop; the stop changes only STOPPED; both bad files archived; conversation.json restored from saved bytes. Then A9; messages, full state wire, epoch, next label, one receipt (first record, before UNRUN); no request or tool; prev.json untouched |
| CK5 metadata repair | the same node `[ck5]`, comparing full state and identity |
| Idempotence | `test_the_same_command_repeated_is_idempotent[a14,ck5]` |
| Refusal matrix | `test_every_refusal_leaves_the_store_byte_identical[a14,ck5]`, 24 shared cases plus 1 (A14) or 2 (CK5) file cases, snapshot equal per case: wrong reason (the other new reason), wrong resolutions, absent stop, legacy stop without witness, damaged witness, a witness for the other reason, not repaired, changed record, changed tail, older replacement ledger, empty new segment, IDENTITY lower/higher/damaged/foreign/absent, resealed lower identity, missing state blob, missing required suffix blob, open RECOVERING, pending GC (witness resealed to isolate the GC check), independent FSYNC_FAILED (kept), another carrier; A14 unbound list; CK5 reformatted and older-checkpoint metadata. Control: `test_the_refusal_matrix_control…` (the unmutated repair is accepted) |
| Ineligible stops | `test_stops_without_a_safe_witness…` (A14/CK5 over a torn tail, CK5 without IDENTITY, CK5 with RECOVERING open); `test_an_a14_stop_over_a_pending_collection…` |
| No unintended expansion | `test_only_the_two_new_pairs…` (70 pairs, low-level enum shown non-authoritative); `test_newer_integrity_stops_acquire_no_resolution[5]` |
| Every transaction cut | `test_the_transaction_is_ordered_and_fenced` (the order itself); `test_every_cut_of_the_acknowledgement_converges_with_one_receipt[a14,ck5 × process-death,host-loss]` (every armed call of the command and the consuming start); `test_a_second_interruption_then_host_loss_still_converges[3]` |
| Mixed durability | `test_a_readable_unsynced_receipt_is_synced_before_its_carrier_is_retired`; `test_the_consuming_start_fences_stopped_removal_before_its_receipt`; controls in §7 |
| Own torn frame (M-1) | `test_a_torn_frame_of_this_transaction_is_set_aside…[receipt,closure]`; `test_a_crash_inside_setting_aside_its_own_torn_frame_converges` |
| Stale permission | `test_a_stale_permission_never_authorizes_a_changed_store[garbage-tail,valid-record,file-damaged-again,identity-raised]`; `test_an_old_carrier_cannot_unlock_a_later_stop_with_the_same_reason`; `test_an_independent_fsync_failure_after_the_acknowledgement_keeps_a1_authority` |
| After actual collection | `test_both_pairs_after_actual_collection[a14,ck5]`: segment 0 and both NOTE_WRITTEN records physically gone; pending gens 1 (foreign) and 2; full state and mirrors equal; adoption appends only gen 2; the next checkpoint's `prev` is exactly C_n's tuple; collection resumes; a later A14 recovers from the true previous base without a stop; no genesis replay |
| One real CLI restart | `test_cli_acknowledgement_and_restart_behind_the_first_request_barrier`. Real recorder, local stub, real `chassis.py`. CK5 then A14: each real stop exits 44 with a witness; the explicit repair; the actual `--acknowledge-stop <reason> --resolution continue-from-bound` exits 0. During the command and recovery, up to the duty's first-request barrier, there are zero recorder `open` events and zero upstream bodies; one receipt each. Released, the run sends labels `:2:1` then `:3:1`, each equal to the recorder's `client_label` and not `label_seen_before`; the label is stripped from every upstream body and transcript request |

## 6. Crash cuts (in-process; `Crash` = process death before the call; host loss simulated)

`AckOps` extends SV-022's `CutOps`. Segment byte watermarks are as there. In addition, renames and unlinks are undone on host loss unless a later fsync of their directory returned. Watermarks are carried into each restart. The modelled transaction: carrier temp `open`/`write`/`fsync`, `rename(ACKNOWLEDGED)`, `fsync(session/)`, `unlink(STOPPED)`, `fsync(session/)`; then at the start `fsync(session/)` (carrier fence), namespace fences, `open` segment, receipt `write`+`fsync`, closure `write`+`fsync`, receipt-segment `open`+`fsync`, `unlink(ACKNOWLEDGED)`, `fsync(session/)`, IDENTITY.

| Cut class | Outcome |
|---|---|
| before or inside the carrier write, before its fence (host loss: carrier gone) | STOPPED remains (A0); the same command repeated converges |
| carrier durable, before or after STOPPED's unlink, before its fence | process death: start consumes; host loss: STOPPED back, the repeated command rewrites the identical carrier |
| start before its carrier fence, or before the receipt | the receipt is written first, once |
| receipt written, fsync not returned | process death: readable, not rewritten, synced before retirement; host loss: lost, rewritten once |
| closure written, unsynced; crash at the receipt-segment sync | host loss: closure re-derived, written once |
| before or after the carrier unlink, before its fence | process death: ordinary start; host loss: carrier back, finds its own receipt and closure, retires |
| torn receipt or closure frame (M-1) | ordinary TC1: RECOVERING, corrupt/ copy, `RECOVERY{torn_incomplete}`, one receipt; crash before truncation converges |
| second interruption in the restart, then host loss over both processes | converges with one receipt |

Every cut asserts no request or tool, at most one receipt at the cut, and after convergence: A9, equal messages and full state, the same epoch, the next unused label, one receipt, no STOPPED/ACKNOWLEDGED/RECOVERING/FSYNC_FAILED, IDENTITY not lowered, and archive/ and corrupt/ byte-identical. The second start writes no record.

## 7. Negative controls

**Source mutations** (each marked `# MUTATION`, run on the named node, then restored; `grep MUTATION services/ tests/` is empty). Their failures are evidence, not passes.

| # | Mutation | Node | Observed failure |
|---|---|---|---|
| M1 | STOPPED removed before the carrier is written | `…every_cut…[a14-process-death]` | a cut between the two: the next start continues with no carrier, and no receipt is ever written |
| M3 | no own-prefix check of records after the witnessed end | `…stale_permission…[valid-record]` | a foreign record is taken for this transaction's; the start writes its closure, then fails with 0 receipts. The store was mutated instead of stopping |

**In-test controls** (permanent nodes that pass by showing the control breaks the property):

| Control | Node | What it distinguishes |
|---|---|---|
| no receipt-segment sync | `test_negative_control_without_the_receipt_sync…` | the carrier is retired over a never-durable receipt; after host loss there is no receipt and no carrier (false completion) |
| restart initializes durability from readable bytes | `test_negative_control_initializing_durability_from_readable_bytes…` | the harness discriminator: with promoted watermarks the missing sync is invisible |
| no session/ fences (carrier fence and writer namespace fence) | `test_negative_control_without_the_session_fences…` | STOPPED returns over a durable receipt and the operator can no longer acknowledge |
| no evidence check at consumption | `test_negative_control_without_the_evidence_check…` | a permission for another store is transcribed |
| witness seal ignored | `test_negative_control_without_the_witness_seal…` | a witness whose sealed facts changed (lowered identity) is accepted |
| a reset note fact (foreign mark dropped) | `test_negative_control_a_reset_note_fact…` | the full-state comparison fails |
| a reset request identity | `test_negative_control_a_reset_request_identity…` | the label assertion fails; turn 1 would be reissued |

## 8. Source deviations and decisions (for review)

- **Witness, carrier, evidence and receipt fields** are engineering additions (§3). None is claimed canonical.
- **RECOVERY_ACK first.** For these pairs it is the consuming start's first record. The existing pairs keep their position (after the core and notices).
- **The command writes no ledger record.** SV-013 l.558 says the command "appends RECOVERY_ACK and removes STOPPED". As in the existing implementation, the append is the next start's (via the carrier, ACK before STOPPED removal). The command never opens the ledger writer.
- **A9/A9t only.** These resolutions require the conversation file to be directly bound to C_n: no fallback to the previous file, no A10 adoption, no A11 edit (preflight).
- **CK5 only for the unreadable form.** The two readable-but-invalid run.json variants (`detail.field = lineage_id | checkpoint`) carry no witness and stay ineligible.
- **A lost DONE result blob is not "required"** (§1); ordinary C-D3 semantics apply. State blobs and blobs the replay reads are required.
- **New stop `acknowledgement_unverified`** (no resolution): a pending carrier whose evidence no longer holds stops before any change, with only STOPPED written.
- **Own torn frame** is identified by exact bytes (deterministic frames from the witnessed chain) and handed to the accepted TC1 rule.

## 9. Evidence kinds

In-process simulation on temporary roots (process death real within the process; host loss **simulated**). Real processes on one host: recorder, chassis and command, with a local stub (V1's CLI node, V2's script restarts, V4). No power-loss, kernel or storage experiment.

## 10. Remaining limits and findings (not claimed)

- **Host-loss garbage in this transaction's own unsynced region.** M-2 allows arbitrary bytes there, and they cannot be told apart from an external change before consumption. Such bytes stop the start (`acknowledgement_unverified`); the store is safe but needs a later resolution. Absent or prefix bytes converge.
- `acknowledgement_unverified`, the remaining resolutions (bootstrap-preserving, lost/damaged/ahead ledger) and legacy stops without a witness remain refused. No real session is acknowledged retroactively.
- **Unreadable carrier.** An unreadable or garbage ACKNOWLEDGED is ignored by the existing `_read_ack`, so the start proceeds as ordinary without a receipt, and the leftover file blocks collection. This is unchanged behaviour.
- **Supersession.** An acknowledgement of a later, independent stop (an existing pair, e.g. a new FSYNC_FAILED) overwrites a pending witnessed carrier through the existing command. The superseded carrier then grants nothing and is never transcribed.
- **Finding, not fixed (outside this package):** the existing pairs' `_consume_ack` removes ACKNOWLEDGED after finding a receipt that is merely readable, without syncing its segment (the SV022-01 class). The new pairs sync it. Changing the existing pairs was out of scope.
- Exact numerical bounds, total disk, deployed recorder ordering, provider compatibility, merge and deployment: unchanged and not claimed.

## 11. File manifest

Changed: `services/chassis_startup.py` (allowlist; witness, verifier, carrier, command; startup consumption; docstrings). New: `tests/test_chassis_acknowledgements.py`, `docs/planning-context/sv023/STATUS.md`, `docs/planning-context/sv023/RECEIPT.md`. No other file changed, and no retained assertion changed.

## 12. Coordinator execution provenance

Filtered events show V10 started before V9 reported completion. Both remained within the shared CPU50%, memory2GiB, tasks64 scope. This was a deviation from the one-command-at-a-time instruction, not a test failure. After these runs the coordinator added a nonblocking cross-process lock to the external bounded runner, inherited by the pytest child. A held-lock check returned75 before starting tests. Exact receipt: `results/SV-test-serialization-receipt.json` in the coordinator workspace. Source/test bytes were unchanged by this orchestration fix.

## 13. Correction 1 (Astra SV023-01 … SV023-04)

§1–§11 describe runtime/tests `c5b2ae1f7fe79bc333abd60fc650c5a37e1d7779`. The independent review (`SV-023-Astra-review.md`, head `b878ed6`) found four defects, and all are corrected in `services/chassis_startup.py`. The three carrier behaviours §10 listed as limits or out of scope (unreadable carrier ignored, supersession by a later acknowledgement, old-pair retirement over a merely readable receipt) were findings, not exemptions. All three are now fixed: fail-closed classification, conflict refusal, and durable matching-receipt retirement for every pair. The review's fourth finding, the stranded own-torn-frame recovery, is fixed by sealed witnessed context in RECOVERING and carrier-first retirement. One further defect of the same class was found and fixed: a duplicate, tail-unbound TC4 receipt after process death between the two removals. Regressions were written first and failed on the reviewed runtime. Final tree: 657 selected passes across 12 bounded commands. Details, pre-fix failures, schema/ordering, tests, mutation M5, residual limits and this correction's own execution provenance: `checkpoint-001-astra-corrections.md`. Not accepted; awaiting re-review.
