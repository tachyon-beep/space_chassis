# SV-023 checkpoint 001: Astra correction 1 (SV023-01 … SV023-04)

2026-10-08. Review: `SV-023-Astra-review.md` (context directory), read in full before any edit. Reviewed head `b878ed62640e2d2a319c94c1a4deb229c4529e5e`, runtime/tests `c5b2ae1f7fe79bc333abd60fc650c5a37e1d7779`: changes needed, all four findings. The worker made no Git call; the coordinator commits after the worker stops. **Not accepted; awaiting re-review.** All work ran on temporary fixture roots in this isolated checkout. No real session was touched, and no provider was contacted.

## 1. Execution provenance (correcting the initial record)

- **Initial package (V1–V12 in RECEIPT §1).** The coordinator found that the initial V9 and V10 invocations overlapped. I had submitted several runner commands in one message, so STATUS checkpoint 2's statement "one literal runner command each" did not describe serial execution. The overlap stayed inside the shared resource scope; it changes no recorded pass or failure, but those runs were not serial. The coordinator then added a cross-process flock to the external runner, which refuses a competing invocation with exit 75 before any test starts.
- **This correction.** Each pre-fix and post-fix command was submitted alone and awaited, with one exception: the final retained batches C10, C11 and C12 (§6) were submitted in one message as three tool calls. With the flock, an overlapping invocation would have exited 75 before testing. All three exited 0 with complete progress output, so none was refused, but the submission did not follow the one-at-a-time instruction. No command was retried, and no runner file was read or changed.

## 2. Pre-fix evidence (regressions written first, run alone on the unmodified reviewed runtime)

Each node below is in `tests/test_chassis_acknowledgements.py` (section "SV-023 correction 1"). Each failed exactly as the review traced:

| Finding | Node | Pre-fix failure |
|---|---|---|
| SV023-01 | `test_sv023_01_a_present_carrier…[a14-reason-one-character]` | `Opening(classification='A9', session=…)`: the changed carrier was treated as absent; an effect-capable session was returned |
| SV023-01 | `…[ck5-reason-a-list]` | `TypeError: unhashable type: 'list'` in `_read_ack` (startup crashed instead of stopping) |
| SV023-01 | `test_sv023_01_a_damaged_old_pair_carrier_also_fails_closed[a-witnessed-envelope]` | A9: a witnessed envelope with an old pair was consumed as a legacy carrier |
| SV023-02 | `test_sv023_02_a_later_acknowledgement_never_replaces…[ck5-failed-first-fence]` | `DID NOT RAISE`: after a real injected EIO before the first receipt, then A1, the fsync acknowledgement replaced the pending CK5 carrier |
| SV023-03 | `test_sv023_03_the_reviewed_window_between_the_two_removals[receipt]` | `acknowledgement_unverified`, "records after the witnessed end are not this acknowledgement's own" (the stranded torn recovery) |
| SV023-04 | `test_sv023_04_an_old_pair_readable_receipt_is_synced_before_retirement` | the restart's log before `unlink(ACKNOWLEDGED)` held only `sync_dir(session)`, `sync_dir(ledger)`, `open(000000.svl)`: no fsync of the receipt's segment |
| SV023-04 | `test_sv023_04_a_failed_receipt_sync_keeps_the_carrier…` | `DID NOT RAISE`: there was no sync whose failure could keep the carrier |
| SV023-04 (found here) | `test_sv023_04_tc4_keeps_its_conservative_closure…[dies-before-the-carrier-removal-process-death]` | **two** RECOVERY_ACK records, the second with `tail_sha256: null` |

The last row is a defect the review did not name, in the same retirement class. Old pairs removed RECOVERING before the carrier. A plain process death between the two left a pending TC4 carrier over a TC0 ledger, and `tail_ack` was applied regardless of the tail, so `derive_core` wrote a second, tail-unbound receipt. No host loss is needed. The `…-host-loss` variant also lost the final notice: the intent was retired over intent-core records that had been read but never synced.

## 3. Fixes (`services/chassis_startup.py` only)

**SV023-01: one carrier classifier, fail-closed.**
- `read_carrier` returns `absent | old | witnessed | invalid`. Only absence grants and stops nothing.
- A present file is invalid if it is unreadable or oversize, not an object, has non-string `reason`/`resolution` (checked *before* the pair lookup), names a pair outside the allowlist, or fails its schema.
- The old-pair schema is exact: `{reason, resolution, ack_id}`, plus `tail_sha256` (hex64) only and always for TC4; `ack_id` is 32 hex; any witnessed-envelope key makes it invalid.
- A witnessed carrier must pass `carrier_problem` (keys, seal, pair, ack_id, witness, evidence binding).
- `open()` stops `acknowledgement_unverified` (`ACK`, no resolution) on an invalid carrier, right after A0/A1 and before any other read-dependent step or mutation. Only STOPPED is written; the carrier's bytes are kept.

**SV023-02: no command replaces an unfinished carrier** (the review's bounded fail-closed option).
- The old-pair command calls `read_carrier` before its write. It proceeds only if there is no carrier or the held carrier equals the one it would write, i.e. the same stop bytes, pair and binding: a same-transaction retry.
- The witnessed command already refused other carriers; it now uses the same classifier.
- The refusal is a LedgerError (`… pending and is never replaced …`) before any write, leaving the prior carrier, the new STOPPED and FSYNC_FAILED in place.
- No cancellation, supersession or two-transaction continuation is introduced.

**SV023-03: checked context through every cleanup combination.**
- When the witnessed consumption has to set aside its own torn frame, its RECOVERING carries a sealed `witnessed` context: `{ack_id, receipt, after_seq}`, where `after_seq` is the witnessed ledger end. It is covered by the intent's existing SHA-256 `check` and validated by `witnessed_context_problem`. `_validated_intent` accepts exactly `INTENT_KEYS` or `INTENT_KEYS ∪ {witnessed}`, and the context requires `ack is None`.
- At consumption the verifier accepts an open RECOVERING only if its context equals this carrier's receipt and witnessed end.
- In `_recover`, the receipt and witnessed end come from the carrier, or from the intent's context once the carrier is gone. The receipt is placed first in the core iff no matching receipt follows the witnessed end in P.
- A witnessed intent may hold exactly its core: an extra record → `recovery_intent_mismatch`. This rejects arbitrary RECOVERY records, and the quarantined tail is still checked by `_from_intent` (hash of the original tail or its corrupt/ copy).
- **Order for the witnessed transaction:** sync the receipt's segment, retire the carrier, then remove RECOVERING. The surviving combinations are all checked:
  - (carrier + intent): verifier, then the intent's exact core;
  - (intent only): the sealed context and the exact core;
  - (neither): done.
  - (carrier only, with torn-recovery records) cannot arise; each removal is fenced before the next.
- The evidence check is unchanged.

**SV023-04: shared durable retirement, every pair.**
- `_consume_ack` now retires the carrier only over **exactly one** receipt that equals the expected payload. For old pairs that is the carrier itself, so reason, resolution and ack_id must match, plus `tail_sha256` for TC4. For witnessed pairs it is `receipt_payload`.
- It fsyncs that receipt's own segment first. A sync failure is a PersistenceFailure: the carrier stays, the boundary attempts FSYNC_FAILED, and the next start is A1.
- A non-tail receipt is still committed once if absent. A TC4 receipt still comes only from its tail's recovery.
- The TC4 duplicate: a pending TC4 carrier over an empty tail with no intent is accepted only if its exact tail-bound receipt is already recorded (then only the carrier is retired). Otherwise the start stops `acknowledgement_unverified` before any change.
- Before any RECOVERING removal, the segments of records an earlier start wrote under that intent are fsynced. Readable intent-core records are not assumed durable.
- TC4 closure, spend, identity and notice semantics are unchanged. No resolution is added.

**GC interplay.** The only new durable context lives inside RECOVERING. RECOVERING and ACKNOWLEDGED are both already in `chassis_session.GC_BLOCKERS`, and both are outside GC's namespace. No collection runs while either exists, and nothing in either is ever a deletion candidate. GC authority and the retained-reference policy are unchanged.

## 4. New and changed tests (no prior assertion changed)

| Finding | Nodes |
|---|---|
| SV023-01 | `test_sv023_01_a_present_carrier_that_does_not_verify_stops_before_any_change[a14,ck5 × invalid-json, not-an-object, reason-one-character, reason-an-old-pair, ack-id-missing, ack-id-not-a-string, reason-a-list, resolution-a-dict, wrong-check, control-changed-conversation]`: stop, only STOPPED changed, no receipt, no effect, then A0. `test_sv023_01_a_damaged_old_pair_carrier_also_fails_closed[4]`. Control: `test_sv023_01_control_a_valid_old_pair_carrier_is_still_consumed` |
| SV023-02 | `test_sv023_02_a_later_acknowledgement_never_replaces_an_unfinished_carrier[a14,ck5 × failed-first-fence (real injected EIO), independent-marker]`: refusal byte-identical; carrier, STOPPED and FSYNC_FAILED kept; A0; no receipt. Control: `test_sv023_02_control_an_old_pair_retry_of_the_same_stop_is_still_supported` (crash after the carrier and FSYNC_FAILED's removal, before STOPPED's; the retry completes; one receipt). The retained old-pair fixtures in `test_chassis_recovery_live.py` are unchanged and pass |
| SV023-03 | `test_sv023_03_every_cut_after_an_own_torn_frame_converges[receipt,closure × process-death,host-loss]`: a cut before **every** armed call of the consuming start (intent write, quarantine copy and fences, truncate, each core record write and fsync, receipt-segment sync, carrier unlink and fence, intent-core sync, intent unlink and fence, as logged by a probe run); then a second interruption at the same position of the restart's own log, host loss again with carried watermarks, then two starts. Each asserts one original receipt, one `torn_incomplete` whose `tail_sha256`/`bytes` are the fragment's, the corrupt/ copy byte-equal to the fragment, full state, epoch, notes, identity and next label, and that no STOPPED is ever written. Also `…the_reviewed_window_between_the_two_removals[2]`; `…the_torn_recovery_is_ordered_and_its_intent_carries_the_context[2]`; fail-closed `…a_changed_recovery_record_or_quarantine_still_fails_closed[recovery-record, quarantine-copy, extra-record-after-retirement]`; control `…negative_control_an_intent_without_the_context_strands_the_recovery` |
| SV023-04 | `test_sv023_04_an_old_pair_readable_receipt_is_synced_before_retirement` (fsync pair, no extra append, carried watermarks, host loss after retirement: one receipt, never rewritten); control `…negative_control_without_the_fence_an_old_receipt_is_lost`; `…a_failed_receipt_sync_keeps_the_carrier_and_takes_the_persistence_boundary`; `…tc4_keeps_its_conservative_closure_and_identity_across_mixed_crashes[completes, dies-before-the-carrier-removal × process-death, host-loss]` (one tail-bound receipt, one spend at `reserved+1`, one notice, next label); `…a_pending_tc4_carrier_whose_tail_is_gone_grants_nothing` |

**Source mutation M5** (marked, run, restored; `grep MUTATION` empty): the witnessed transaction's intent removed before its carrier. `test_sv023_03_every_cut…[receipt-process-death]` failed at cut 14, before the receipt-segment sync's `open`: `acknowledgement_unverified`, the review's exact window. The pre-fix runs in §2 are the remaining discriminating controls for SV023-01, -02 and -04.

## 5. Residual limits (honest, not exemptions)

- **Fail-closed conflicts (SV023-02).** Any later stop raised while an earlier carrier is unconsumed cannot be acknowledged; the store stays at A0/A1 with both preserved until a later, explicitly designed continuation. This includes an existing-pair case, `corrupt_quarantine_full` raised while a TC4 carrier is being consumed, which an earlier runtime would have "resolved" by replacing the carrier.
- **Fail-closed carriers.** `acknowledgement_unverified`, from a damaged carrier, changed evidence, or a TC4 carrier whose tail is gone without its receipt, has no resolution.
- **Host-loss garbage.** Garbage in the witnessed transaction's own unsynced region is still refused rather than authenticated (unchanged).
- **Unmodelled host loss.** An un-synced truncation reverting under host loss is not simulated; the corrupt/ copy and intent cover it, but no fixture claims it.
- Everything else in RECEIPT §10 still applies, except the three carrier behaviours there, which this correction resolves (§3).

## 6. Final runs (final tree, after M5 was restored)

`python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <targets>`, same exact targets as RECEIPT §1:

| # | Targets | Result |
|---|---|---|
| C1 | `tests/test_chassis_acknowledgements.py` | 94 passed (44 initial + 50 correction) |
| C2 | `tests/test_chassis_recovery_live.py` | 97 passed |
| C3 | `tests/test_chassis_gc.py` | 50 passed |
| C4 | `tests/test_chassis_correlation.py` | 2 passed |
| C5 | replay + session | 61 passed |
| C6 | notes + checkpoint | 23 passed |
| C7 | adoption | 50 passed |
| C8 | ledger + recovery + durability | 114 passed |
| C9 | termination | 67 passed |
| C10 | groups + wire + supervisor flap + metadata | 65 passed |
| C11 | the 29 retained legacy nodes (target JSON, literal) | 29 passed |
| C12 | the 5 local-stub end-to-end nodes (target JSON, literal) | 5 passed |

Total: 657 selected passes, no failures (94 focused + 563 retained, the same retained set). For the C10–C12 submission, see §1.
