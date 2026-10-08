# SV-023 Astra independent review

**Changes needed. SV-023 is not accepted.** The two repaired-file resolutions have a useful evidence-bound design and substantial focused assertions, but four carrier/recovery defects remain. Three affect the new witnessed transaction directly; the fourth is an acknowledged inherited defect in the same active acknowledgement subsystem. None requires a new H/T/Q or pump decision.

Reviewed immutable head `b878ed62640e2d2a319c94c1a4deb229c4529e5e`, runtime/tests `c5b2ae1f7fe79bc333abd60fc650c5a37e1d7779`, against accepted base `d301d139cf85961a823c874d7661a7000d563d09`. All implementation/test references below refer to those Git objects, not the moving checkout. This was static review: no tests, project imports, providers, runtime edits or real-session operations. Only this report was written.

## Findings

### SV023-01 — P1: carrier corruption can bypass the witnessed verifier entirely

**Location:** `services/chassis_startup.py:263` (`_read_ack`, especially 265–268), reached at 727 before the new verifier at 733.

The new carrier is checksummed, but the dispatcher first treats unreadable JSON, an unrecognized reason/resolution, or a non-string ack_id as *absence*. Consequently the checksum and evidence checks are never reached for several ordinary corruption outcomes. Receipt §10 acknowledges this behavior; its being inherited does not make it safe for newly introduced sealed authority.

**Concrete trace:** create either eligible stop, repair the exact file, and complete its acknowledgement command. STOPPED is durably gone and ACKNOWLEDGED is now the only pending transaction carrier. Change one character in the carrier's reason to an unsupported spelling, leaving valid JSON and the old checksum, or damage a JSON delimiter. On restart `_read_ack` returns None. Ordinary A9 recovery can append the closure and return an effect-capable session with zero RECOVERY_ACK records. The leftover carrier blocks GC but does not stop startup. A validly encoded but differently bound conversation introduced before that restart can instead take ordinary A11; the witnessed transaction's unchanged-evidence gate is likewise bypassed. No hostile resealing is needed.

**Correction:** distinguish absent from present-invalid/unreadable. A present carrier that cannot be classified and verified must stop before ordinary startup mutations; preserve its bytes and grant it no resolution. Dispatch only after safe type/domain validation, so list/dict values in pair fields cannot escape as unhandled membership errors. Preserve valid old-pair compatibility explicitly; do not silently reinterpret a damaged witnessed envelope as a legacy carrier.

**Discriminating regression:** for both new pairs, mutate the acknowledged carrier by invalid JSON, one changed reason character, missing/non-string ack_id and malformed field types. Startup must return a diagnostic stop, write no receipt/closure/request/tool, and preserve everything except the diagnostic marker. Include a valid-JSON wrong-check carrier and a changed-conversation control. The current refusal matrix corrupts STOPPED's witness before the command; it does not cover these post-command dispatcher bypasses.

### SV023-02 — P2: a later old-pair acknowledgement destroys an unfinished witnessed transaction

**Location:** `services/chassis_startup.py:248`–259, particularly the unconditional carrier replacement at 251. Compare the new command's pending-carrier refusal at 643–649.

**Concrete trace:** complete a witnessed CK5 acknowledgement, then fail the consuming start's initial session-directory fence before any receipt write. The persistence boundary records FSYNC_FAILED. The next start correctly produces A1/`fsync_failed_previous_run`. Invoking that existing supported resolution overwrites ACKNOWLEDGED with the old-pair carrier, then removes FSYNC_FAILED and STOPPED. The subsequent start has no witnessed evidence constraint and records only the fsync acknowledgement. The completed CK5 acknowledgement is lost without a receipt. An independent fsync marker introduced after the command gives the same result without any torn ledger. The new A1 test at `tests/test_chassis_acknowledgements.py:840` stops before exercising this second command.

Calling the old permission “superseded” is a new cancellation policy, not a consequence of either canonical resolution. It also discards the only durable association between the operator choice, its original stop and the verified input.

**Correction:** apply pending-carrier conflict handling to every command path. At minimum, refuse the second command byte-identically while preserving both the first carrier and the new stop/failure marker, and document this fail-closed limit. If this tranche is to support continuation through the second stop, preserve and complete both transactions with checked identities and durable receipts; do not overwrite one as an implementation shortcut. No automatic acknowledgement of the later stop is permitted.

**Discriminating regression:** use both new pairs, inject a real persistence failure before their first receipt, produce A1, then invoke the old fsync pair. Require either the explicitly documented unchanged-store refusal or a fully witnessed, crash-tested two-transaction completion. Assert that the original carrier cannot disappear without its durable receipt and that input changes cannot bypass its evidence check. Keep an ordinary old-pair fixture with no competing carrier as the compatibility control.

### SV023-03 — P2: retiring RECOVERING before the carrier strands a valid torn-frame recovery

**Location:** `services/chassis_startup.py:1006`–1007, interacting with `witnessed_evidence` at 604–607 and `derive_core` at 1442–1445.

**Concrete trace:** use the existing own-torn-receipt fixture (`tests/test_chassis_acknowledgements.py:749`). The acknowledged ledger ends with a strict prefix of its receipt frame. Startup verifies those bytes, durably writes RECOVERING, quarantines/truncates the fragment, and writes the exact receipt, UNRUN closure and `RECOVERY{torn_incomplete}`. It then removes RECOVERING at 1006. Kill the process before `_consume_ack` retires ACKNOWLEDGED—for example before `_sync_record` opens the receipt's segment. On restart the carrier still exists but the recovery intent does not. The verifier now compares every post-witness record to the original TC0 plan `[RECOVERY_ACK, UNRUN]`; the legitimate third `torn_incomplete` record exceeds that plan and produces `acknowledgement_unverified`, with no supported resolution. This is ordinary M-1 process death, not arbitrary host-loss garbage or external modification.

The existing torn-frame recovery test finishes without a second interruption. Its separate crash case stops before truncate, while RECOVERING still exists. The ordinary acknowledgement cut matrix starts with a clean ledger, so none detects this cleanup window.

**Correction:** preserve enough checked transaction context to verify the *whole* own recovery prefix through final cleanup, including the deterministic torn-tail recovery record. Validate that context and the quarantined tail before allowing its records; do not admit arbitrary RECOVERY records merely by kind. A simple reversal of the two removals is insufficient: with ACKNOWLEDGED gone and RECOVERING left, the current recovery intent has no witnessed receipt context, so re-derived core ordering can differ. Define and test both cleanup directions or use one durable completion authority that makes every surviving carrier combination unambiguous.

**Discriminating regression:** for torn receipt and torn closure, interrupt after each completed recovery record and before/after each RECOVERING removal/fence, receipt sync and ACKNOWLEDGED removal/fence. Restart twice, carrying true durability watermarks for mixed M-1/M-2 cases. Require one original acknowledgement receipt, one corresponding torn-tail record, exact preserved quarantine bytes, unchanged epoch/notes/identity, and no new operator choice. Include a changed recovery record/quarantine control that still fails closed.

### SV023-04 — P2: the old-pair branch still retires a carrier over a merely readable receipt

**Location:** `services/chassis_startup.py:1251`–1260; contrast the actual segment sync at 1248 for new pairs.

This is inherited rather than introduced, and Receipt §10 correctly identifies it. It is nevertheless a concrete durability defect in the shared active subsystem, directly reachable through the old resolutions retained by this package. The canonical chassis table marks RECOVERY_ACK synchronous; SV-013's resolution rule requires its record. Merely documenting a false completion is insufficient for acceptance of this acknowledgement closure.

**Concrete trace:** use an old fsync-failure acknowledgement on an otherwise clean bound root with no closure to append. Its first consuming start writes a complete receipt, then dies before that append's file fsync. A second process reads the complete unsynced frame. `_consume_ack` finds its ack_id, removes ACKNOWLEDGED and fences session/, without syncing the receipt segment. `continue_after`'s namespace fences do not make the existing file data durable. A subsequent simulated host loss can remove the receipt while keeping the carrier removal: no receipt and no remaining transaction authority. This is the same mixed durability history already tested for new pairs at lines 639–687.

**Correction:** make the shared retirement condition a verified, durable matching receipt for every implemented pair. Fence the actual segment containing an already-written receipt before retiring its carrier; a fence failure must preserve the transaction and take the existing persistence failure boundary. Keep reason/resolution and applicable tail binding checks, not just an arbitrary matching identifier. This does not enable another resolution or change TC4 outcome semantics.

**Discriminating regression:** extend the readable-unsynced-receipt fixture to the retained pairs, with carried byte/name watermarks and a second host loss after retirement. Include a no-extra-append case so another record's fsync cannot hide the missing fence. Assert exactly one surviving receipt and no unnecessary rewrite; retain the negative control that removes the fence and loses the receipt. For TC4 retain its conservative closure and identity assertions.

## What the evidence does establish

The implementation adds exactly the two proposed pairs and retains explicit refusal of other resolutions. Its pure verifier checks the original chain/end, checked identity reservation, exact current checkpoint and metadata hash, state blobs and replay. It rejects changed bindings, pending collection/recovery at command time and independent FSYNC_FAILED. STOPPED is removed only after the new sealed carrier is durable. The new consumption branch explicitly fences a readable receipt's actual segment before retirement.

The assertions inspect full non-history state, notes/foreign flags, request labels, exact archive preservation and absence of automatic effects. The post-GC cases physically remove source records, preserve the older checkpoint relation, then exercise subsequent collection and previous-base recovery. The real CLI case invokes the actual command and local recorder/stub processes, holds the next request behind a barrier, and verifies label progression and stripping. These are meaningful controls, not merely exit-status checks.

The external receipt reports **607 selected passes: 44 new plus 563 retained, across 12 bounded commands**, exit 0. I did not rerun them. The documented V9/V10 overlap violated serialization but remained inside the shared resource scope; the external flock correction is separate orchestration evidence and changes no implementation bytes. Neither pass counts nor that correction closes the four static traces above.

## Bounded acceptance and remaining work

The following remain honest limits: the two-pair scope; refusing legacy stops without a witness; refusing readable-but-invalid CK5 forms; failing closed on arbitrary changed/garbage tails that cannot be authenticated as the transaction's own; no bootstrap, lost/damaged/ahead-ledger resolution, exact replay-bound claim, user-session repair or deletion. The three carrier behaviors listed in Receipt §10 at lines 150–152 are **findings**, not acceptable scope exemptions.

Correct the four findings on an isolated checkpoint, add the discriminating bounded fixtures, and submit immutable bytes for re-review. SV024/O2-5 remains preparation only until SV023 acceptance. Its namespace fixtures should retain the corrected acknowledgement cleanup controls; if any additional durable carrier/context is introduced, include it in GC's pending-transaction guard and preservation review. Existing GC deletion authority and retained-reference policy must not be broadened to discard such evidence.

No new product-policy choice is necessary for these corrections. A minimal conflict refusal for SV023-02 is acceptable if explicit; supporting a second transaction instead requires its concrete crash protocol. H/T/Q, pump holds, main merge, deployment, live providers and all real-session operations remain outside this review and unapproved.
