# SV-023 Astra correction 1 review

**Changes needed. The four original failure traces are closed, but one residual TC4 transaction defect prevents acceptance.** The correction's new duplicate-receipt guard handles an empty tail, but not later detectable corruption of the final recovery notice while the acknowledged carrier remains. That case can both duplicate the acknowledgement under a different tail hash and create a recovery intent that fails its own validator after another interruption.

Reviewed immutable head `aff938862f82cc3b62beb584b6077029e9d446d5`, runtime/tests `914bcfeb3df9453ff58579cfb91b8f4ccfcc3fbd`, against initial reviewed `b878ed62640e2d2a319c94c1a4deb229c4529e5e` and accepted base `d301d139cf85961a823c874d7661a7000d563d09`. Runtime/test commit to head changes documentation only. This review used static Git objects, canonical source clauses and the supplied external receipt; no tests, imports, providers or runtime changes. This report is the only written output.

## Original findings

| Finding | Assessment of correction |
|---|---|
| SV023-01, invalid carrier treated as absent | Closed. `read_carrier` at `services/chassis_startup.py:272` distinguishes absence from present-invalid, validates pair types before lookup, rejects witnessed envelope fields in old carriers, and sends invalid carriers to the diagnostic boundary at 763. The new corruption cases assert no session, no receipt/effect, preserved bytes and subsequent A0. |
| SV023-02, old command replaces unfinished new carrier | Closed by the permitted fail-closed option. Lines 251–255 reject any other pending carrier before writes; exact same-stop retries remain allowed. Tests cover both new pairs, a real injected first-fence EIO and an independent marker, with byte-identical refusal and an old-pair retry control. |
| SV023-03, torn recovery loses its context between removals | Closed for the reviewed trace. Optional sealed `RECOVERING.witnessed` carries the exact receipt and witnessed end; it is schema/domain checked at 1440–1469. The carrier-plus-intent path requires context equality, and the intent-only path reconstructs the same receipt/core. Witnessed extra records cannot exceed the exact core. Cleanup at 1076–1080 now retires the carrier before the intent, each removal fenced. This implements the necessary context change rather than merely reversing two unproven removals. |
| SV023-04, old receipt readable but unsynced | Closed for the reviewed durability trace. `_consume_ack` at 1310 matches the full expected receipt, requires uniqueness and fsyncs its actual segment before carrier retirement. The no-extra-append mixed-crash fixture discriminates the missing fence; the EIO fixture retains the carrier and reaches A1. Lines 1071–1075 also fence previously read intent-core segments before removing RECOVERING. The related TC4 duplicate fix is incomplete as described below. |

The torn-frame matrix covers each logged filesystem cut for receipt and closure fragments, followed by another interruption and carried durability watermarks. It checks one receipt, one correctly bound torn record, exact quarantine bytes, full state, identities and absence of a new stop. Corrupted recovery records/quarantine and additional records after retirement remain refusal controls. These assertions materially strengthen the earlier evidence.

## SV023-05 — P2: a consumed TC4 permission is applied again when the remaining tail is nonempty

**Location:** `services/chassis_startup.py:947`–954, interacting with intent construction at 1003–1015, `derive_core` at 1549–1551 and intent validation at 1431–1439. The new guard is conditional on `not scan0.tail`.

**Concrete in-model trace:**

1. Create and acknowledge an actual TC4 stop. Let its recovery write and sync its tail-bound RECOVERY_ACK, conservative outcome/spend records and final hidden-turn `MSG_APPEND` notice.
2. Stop the process after RECOVERING has been removed durably, before ACKNOWLEDGED is removed. This is the already-tested old-pair cleanup window; the exact original receipt remains in the valid prefix.
3. Under canonical M-3, change one byte of the final notice's body while retaining its protected header and full length. It is an ordinary TC2 final MSG_APPEND. The earlier receipt and conservative records remain valid. No truncation, checksum resealing, hostile writer or invented product choice is involved.
4. Restart. Because the tail is nonempty, line 947 does not recognize the existing receipt or clear `tail_ack`. `plan_recovery` permits the normal TC2 recovery (its acknowledgement hash gate applies only to TC4). `derive_core` therefore adds another RECOVERY_ACK with the **same ack_id but the new damaged-notice tail hash**.
5. The new RECOVERING is also internally inconsistent: its `tail_sha256` names the damaged notice, while its `ack.tail_sha256` still names the original ambiguous tail. If recovery finishes uninterrupted, two receipts for one operator acknowledgement remain and the old carrier is retired by matching the original one. If the process instead dies after the new intent's durable write and before truncation, the next start fails `_validated_intent` with `recovery_intent_invalid` / field `ack`, with no supported resolution.

M-3 explicitly allows a durable final record to change value; TC2 provides its ordinary recovery rule. The correction document's fail-closed limit for arbitrary garbage in a witnessed append does not cover this old-pair, valid-header corruption trace. The current `test_sv023_04_tc4_keeps_its_conservative_closure_and_identity_across_mixed_crashes` leaves that final notice intact, so its four variants cannot distinguish this defect.

**Bounded correction:** when there is no existing recovery intent, decide whether the TC4 carrier has already been consumed from its exact recorded receipt independently of whether the current tail is empty. If that receipt exists, do not feed the old permission into recovery of another tail; retain the carrier only for durable retirement. If no matching receipt exists, require the current tail to be the carrier's exact acknowledged bytes before using the permission; otherwise refuse before mutation. Never serialize an intent whose embedded acknowledgement disagrees with that intent's tail identity. Keep re-derivation under an existing checked intent unchanged: its frozen acknowledgement is still needed to verify its already-written prefix. Do not loosen TC4 classification or synthesize a new operator choice.

**Discriminating bounded regressions:** extend the existing TC4 cleanup-window fixture by flipping one body byte in its last MSG_APPEND, verifying that it classifies TC2. In one variant complete startup and require only the original exact tail-bound receipt, one original conservative spend transition, preserved identity high-water, no effects and the ordinary damaged-message recovery. In another, interrupt immediately after the new RECOVERING becomes durable and restart twice; its acknowledgement must be null for this independent TC2 transaction and recovery must converge without `recovery_intent_invalid`. Carry durability watermarks through a subsequent simulated host loss. Add a no-recorded-receipt control with a different present tail: unchanged-store refusal, no new receipt. Retain the existing empty-tail control and the original TC4 mixed-crash nodes.

## Evidence and limits

The supplied receipt reports **657 selected passes: 94 focused plus 563 retained**, eight pre-fix failures, worker exit 0 and no denials. I reviewed the new assertions and did not rerun them. The last three commands were submitted together contrary to the one-at-a-time instruction; the enforced exclusive runner lock and all-zero outcomes support serialized actual test lifetimes. This is documented orchestration provenance, not a reason to disregard the passing results or the static counterexample.

The new context lives only in RECOVERING. Both RECOVERING and ACKNOWLEDGED are existing `GC_BLOCKERS` (`chassis_session.py:109`), outside collection's ledger/blob deletion namespace. No retained-reference or deletion-authority expansion was introduced. Carrier conflicts intentionally remain stopped with both transactions' evidence preserved; that is the explicitly allowed bounded limit, not an implicit cancellation policy. Invalid carriers and unauthenticated garbage likewise remain stopped. Unsynced truncation reversion is explicitly not simulated and must not be claimed as tested.

SV023 remains unaccepted pending this narrow correction and immutable re-review. SV024/O2-5 remains preparation only. No bootstrap, lost/damaged/ahead-ledger resolution, exact replay-bound claim, real-session authority, H/T/Q choice, pump work, merge, deployment or provider use is authorized by this review.

## Provisional SV024 retention additions

After SV023 acceptance, retain the existing 27-target preflight and these seven exact focused guards from `tests/test_chassis_acknowledgements.py`; no execution is requested now:

```text
tests/test_chassis_acknowledgements.py::test_the_consuming_start_fences_stopped_removal_before_its_receipt
tests/test_chassis_acknowledgements.py::test_sv023_02_a_later_acknowledgement_never_replaces_an_unfinished_carrier[a14-failed-first-fence]
tests/test_chassis_acknowledgements.py::test_sv023_03_every_cut_after_an_own_torn_frame_converges[receipt-process-death]
tests/test_chassis_acknowledgements.py::test_sv023_03_every_cut_after_an_own_torn_frame_converges[closure-host-loss]
tests/test_chassis_acknowledgements.py::test_sv023_04_an_old_pair_readable_receipt_is_synced_before_retirement
tests/test_chassis_acknowledgements.py::test_sv023_04_a_failed_receipt_sync_keeps_the_carrier_and_takes_the_persistence_boundary
tests/test_chassis_acknowledgements.py::test_sv023_04_tc4_keeps_its_conservative_closure_and_identity_across_mixed_crashes[dies-before-the-carrier-removal-host-loss]
```

Add the eventual SV023-05 interrupted-independent-tail recovery guard once its actual node exists and is independently reviewed; its exact selector must not be guessed. These additions target startup fences, cleanup and carried durability, not another broad suite.
