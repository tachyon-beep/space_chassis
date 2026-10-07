# SV-021 independent Astra initial review

**Changes needed. Do not accept the integrated runtime activation yet.** Seven concrete findings remain. The implementation has substantial useful machinery, but its repeated-restart paths do not yet preserve the advertised identity and memory authority.

Reviewed immutable head `2717d7c5f6adc40c6326142efa9a40a62e3aeced`, runtime/tests `3b145c6aea18a0fc537de9cd74fe1adc539039f6`, against accepted base `437b52d765269dbfb127505e27d6b8dca4ed99e6`. All implementation/test references below refer to those Git objects, not a moving worktree. This was a static review: no tests, imports of project code, providers, installations, tracker initialization, runtime edits, merge or deployment. This report is the only deliverable written by the reviewer.

Sources: canonical SV-013 dossier §2.2 and fixtures; SV-015 integrated closure v2 §1.2–1.4 and §2.3, its literal values and generator shapes; SV-015 v2 independent review (including corrected O1-5 and conditional numeric-domain guidance); SV-021 Astra preflight; repository AGENTS/design guidance; accepted SV-020 foundation review. The reported 465 selected passes across nine bounded runs, including four real process restart cases, are implementation evidence. I inspected source and relevant assertions independently; I did not reproduce those runs.

## Findings

### SV021-01 — P1: a second ambiguous tail can reuse request and turn identities

**Location:** `services/chassis_startup.py:714`, especially `:751–754`; `services/chassis_replay.py:532–542`; receipt §3 “Request identity”.

The allocator skips `floor(current_tail_length / 117) + 1` turns after TC4, but a hidden recovery record can itself contain a much larger previously computed skip. The receipt explicitly conditions correctness on no such earlier hidden skip; neither the classifier nor the live writer establishes that condition. This is an identity correctness condition, not the deferred exact replay-work bound.

**Failure trace:** from a valid prefix with next turn 1, acknowledge a 117,000-byte ambiguous tail. Recovery records next turn 1002, truncates the old tail into quarantine, and removes its intent. Send request `lineage:1002:1`, then die before the response/checkpoint. Damage the headers of the short replacement suffix beginning with the first recovery record, including the request, so it becomes another TC4 with no later-valid header. Its current length is far smaller than 117,000. The second acknowledgement computes a next turn far below 1002 from the same prefix. Normal successful turns eventually allocate `lineage:1002:1` again. No malicious writer, missing acknowledged permission, sequence overflow or A15 violation is required. The earlier quarantined tail survives, but this allocator does not use it. Hidden call keys can likewise be reused.

**Required correction:** make the next identity exceed every possibly allocated identity after arbitrary repeated recovery, with its evidence durable before any dependent request/tool effect. A validated durable allocation high-water mark outside the suffix being discarded is one possible engineering approach; its creation, corruption, missing-file and crash cases must themselves fail closed. Another complete bound may use retained evidence, but it must cover recursive earlier skips, not just current tail length. Preserve the established label grammar and conservative notices. Where valid allocation evidence cannot establish uniqueness, stop before new effects; `P` and `L` alone cannot certify “no hidden earlier skip”. Merely documenting the condition or incrementing the current formula again is insufficient. This needs no H/T/Q or pump decision.

**Discriminating regression:** two successive TC4 recoveries, first large and second small, with a request actually observed by a local stub under the first skipped identity; preserve the first quarantine and finish the first recovery normally before the second damage. Assert every later label/call key stays above all possibly used identities, or that the second recovery diagnostically stops before a send. Include another crash during the corrected allocator's reservation/cleanup. Existing `test_o1_4...` and `test_script_an_ambiguous_tail...` assert only a single skip and encode the faulty formula.

### SV021-02 — P1: checkpoint rotation can destroy the base advertised by `prev`

**Location:** `services/chassis_session.py:487–530`, especially `:494` and `:502`; `services/chassis_persistence.py:1448–1454`; recovery `services/chassis_startup.py:572–589` and `:632–636`.

The installer always rotates the current file into `conversation.prev.json`, while the new checkpoint always advertises `self.last_checkpoint` as its previous base. After A10 or A14 these are different snapshots. They can also differ after an external edit/reimport. Checking the installed new hash does not verify the retained previous hash.

**Failure trace:** checkpoint C binds list B. Append a message and complete CK4 installing N, then die before CK6. A10 correctly replays N using the B now in `conversation.prev.json`; `last_checkpoint` remains C. The next successful checkpoint rotates N over the only retained B, but publishes `prev.conv_sha256 = hash(B)` and C's cover/sequence. Damage the new `conversation.json`. A14 cannot find B in either file and stops `conversation_unreadable_unbound`, despite this being the advertised one-file fallback. If the next checkpoint changes the conversation again, the same mismatch holds. After A14, the deliberate repair write also installs a replay-plus-notice file that is not the snapshot in `last_checkpoint`, exposing the same next-checkpoint defect.

**Required correction:** preserve the actual bound previous snapshot through recovery and the next checkpoint, and make the published `prev` tuple name the file retained for it. Do not solve this by accepting an unbound file or skipping the intermediate hash check. Review CK3/CK4 crash cuts after recovery as well as ordinary uninterrupted rotation; recovery must not silently overwrite its only verified base.

**Discriminating regression:** C(B) → append → crash after CK4(N) → A10 → successful next checkpoint → assert `sha256(conversation.prev.json) == newest.prev.conv_sha256` → corrupt newest conversation → A14 reconstructs exactly. Repeat after A14 repair and A11/A8 adoption. Existing checkpoint tests compare consecutive uninterrupted checkpoints; `test_checkpoint_crash_cuts...:618` ends after the first recovered opening, so it misses the subsequent rotation.

### SV021-03 — P1: an interrupted legacy import permanently suppresses its unadopted note

**Location:** `services/chassis_startup.py:372–380`; `services/chassis_replay.py:491–501`; `services/chassis_session.py:388–390`.

`LEGACY_IMPORT` marks the legacy handoff hash as processed before the separate `NOTE_WRITTEN{legacy}` is durable. A process death in that gap leaves no pending generation but prevents the mirror from being adopted.

**Failure trace:** a readable legacy list does not contain prefix + N, and HANDOFF.md contains N. Persist `LEGACY_IMPORT` with `legacy_unadopted_unproven` and the handoff hash; die before `write_legacy_note`. Restart replays that import and restores `handoff_md_sha256`, with an empty pending list. `resume_session` calls `adopt_file_edit`, which returns immediately for that hash; `adopt_notes` has nothing to append. All subsequent runs continue suppressing N. This contradicts the accepted conservative migration direction (duplicate rather than lose).

**Required correction:** make import's unadopted-note obligation recoverable, carrying the required durable text/blob or a resumable migration step; mark it processed only when matching/adoption evidence actually exists. Preserve exactly-once generation behavior when the NOTE_WRITTEN did finish. Apply the same reasoning to A8 migration.

**Discriminating regression:** crash immediately after LEGACY_IMPORT sync and before NOTE_WRITTEN, then resume twice: N appears once, with one recoverable generation and no repeated import. Also cut after NOTE_WRITTEN and after note MSG_APPEND. `test_an_interrupted_legacy_import...:225` currently closes only after `root.start()` has already completed both records, so it does not test this gap.

### SV021-04 — P1: repeated A12 startup treats one deletion as multiple deletions and can erase a durable note

**Location:** `services/chassis_startup.py:541–544`, `:562–563`, `:618–620`; `services/chassis_replay.py:486–489`; `services/chassis.py:1294–1304`.

An EXTERNAL_DELETE is recognized as already performed only in `extra`, the records of a still-active tail-recovery transaction. A deletion already in the ordinary suffix is ignored for authority classification. Because recovery deliberately does not checkpoint/install a conversation, a subsequent process restart sees the same absent file and performs another deletion.

**Failure trace:** checkpoint has pending note N. The duty/operator deletes conversation.json once. Startup records EXTERNAL_DELETE; resume appends N durably through MSG_APPEND and advances its adoption watermark. Kill the process before a checkpoint. On restart, replay reconstructs that note and watermark; the still-absent file nevertheless selects A12 again. A second EXTERNAL_DELETE clears the just-replayed list. N is no longer pending and its unchanged mirror is already processed, so resume loses it permanently. A new message written durably after the first deletion is similarly discarded without a second file deletion.

**Required correction:** persist/reconstruct the current source-file authority state, including an already-consumed absence, across ordinary suffix replay. A single external deletion must be consumed once; it must not replay as a new user decision merely because no checkpoint has yet recreated the filename. Preserve detection of an actual later delete after a file was installed.

**Discriminating regression:** the trace above with two restarts before the next checkpoint must retain N, advance history_epoch once and contain one EXTERNAL_DELETE; then install/checkpoint and explicitly delete again, which must advance the epoch a second time. `test_c_k3...:521` checks only the first start; the watermark tests cover explicit history replacement/edit, not repeated absent-file startup.

### SV021-05 — P2: any historical switch hash can suppress a genuine later external edit

**Location:** `services/chassis_startup.py:538–559`.

`switched_suffix` is a set of every LEGACY_IMPORT/EXTERNAL_EDIT/LEGACY_REIMPORT source hash after the checkpoint. Matching any one of them selects A10 and keeps the newest replayed messages. A previous source hash is not evidence that the current file is still the latest adopted source.

**Failure trace:** after checkpoint B, write list X and restart (A11, EXTERNAL_EDIT X), then stop before a checkpoint. Write a distinct list Y and restart (A11, EXTERNAL_EDIT Y), again before a checkpoint. Now intentionally restore file X. Strict replay yields Y, but X is in `switched_suffix`; startup selects A10 and silently keeps Y. The user-visible edit back to X is ignored. This is distinguishable from rewriting the currently processed file with identical bytes: the last processed source here was Y.

**Required correction:** bind the current source-file hash/absence to the latest relevant authority transition, not membership in the entire switch history. Coordinate this with SV021-04 so repeated startup converges without suppressing later real edits.

**Discriminating regression:** X → Y → X across three pre-checkpoint startups adopts X, advances the epoch for each actual edit, and leaves no duplicate transition on a fourth unchanged-file restart. Include A8/legacy switch followed by edits. Current base-switch reducer assertions demonstrate individual switches, not this classifier sequence.

### SV021-06 — P2: durable response adoption does not preserve required notice obligations across crashes

**Location:** `services/chassis_session.py:205–207`, `:218–222`, `:320–328`; `services/chassis_replay.py:367–381`; recovery `services/chassis_startup.py:591–631`.

For 33–256 calls the omission notice exists only in `Session.group_notice` until the group flush. TURN_RESPONSE stores the omitted count/hash, but the replay reducer and startup do not reconstruct the pending notice. For a refused 257-call response, RESPONSE_REFUSED advances the request state without appending or retaining the notice obligation; the subsequent MSG_APPEND is a separate write.

**Failure traces:** (a) persist the 33-call TURN_RESPONSE and die inside the first invoked tool or immediately after the final DONE but before `flush`; recovery closes calls correctly but never tells the model that call 33 was omitted. (b) die after RESPONSE_REFUSED sync and before MSG_APPEND; restart advances to the next turn with no assistant and no refusal notice. These are derived runtime facts already made durable, unlike the explicitly volatile duty-message queue.

**Required correction:** make these notice obligations part of deterministic replay/closure, with exactly-once completion after the group's results, before queued messages/checkpoint. Recover from the stored counts; do not replay omitted calls or fabricate results for them. Either atomic reducer behavior or a durable pending/completed notice identity can work if all crash cuts converge.

**Discriminating regressions:** 33/256-call cuts after TURN_RESPONSE, during a tool, after last DONE and after notice MSG_APPEND; 257-call cuts after RESPONSE_REFUSED and after its notice. After repeated restart assert exactly one appropriate notice, unchanged stored/invoked call counts and no checkpoint with an unfulfilled notice. `test_33_calls...:366` and `test_257_calls...:393` inspect completed adoption/flush, missing these cuts.

### SV021-07 — P2: the public history copy still exposes nested authoritative message objects

**Location:** `services/chassis.py:512–514`; integration with `services/chassis_replay.py:88–101`, `:367–378` and `services/chassis_session.py:492–529`.

`RunContext.history()` returns shallow dict copies. Its nested `tool_calls` list and function dictionaries still reference the session's authoritative message. The unchanged helper now violates the newly activated one-owner/exact-replay contract.

**Failure trace:** an ordinary registered tool obtains `h = context.history()` and prepares a local edit to `h[assistant_index]['tool_calls'][0]['function']['arguments']`, believing the documented copy contract. This immediately mutates the stored assistant while the group is open, without a ledger record or the set_history group guard. The following checkpoint hashes the edited assistant; previous-base replay reconstructs the original TURN_RESPONSE and fails the intermediate hash check. Death before the checkpoint instead silently reverts the apparent edit. Neither private-attribute access nor deliberate ledger tampering is required.

**Required correction:** return a detached deep copy of the supported JSON history structure. Keep actual edits routed through the existing validated HISTORY_REPLACED operation; do not relax the no-history-replacement-inside-group rule.

**Discriminating regression:** obtain history during a real tool call and mutate nested call IDs/names/arguments and nested JSON content from set_history; assert the session and serialized ledger replay are unchanged until an authorized set_history outside the group. Follow a normal checkpoint with A14 recovery to verify the intermediate hash. The new owner cannot claim all public mutations are ledgered while this alias remains.

## Source deviations and retained mechanisms

The following are useful and should be preserved during correction:

- REQUEST_SENT and INVOKING are appended/synced before their callbacks; DONE stores its blob first. The reviewed failure tests assert absence of effects, not merely raised exceptions. The unified PersistenceFailure identity and broken-session guard support the intended gate rule.
- The shared reducer reconstructs fixed message key order, derives unknown/unrun/known-payload-lost distinctions from ledger evidence, and preserves non-invokable admission text without inventing execution. Storing `admit_text` instead of separate UNRUN records is a coherent documented adjustment; its different record accounting is honestly excluded from the exact bound claim.
- The RECOVERING carrier retains the original tail classification across copy/truncate and partial outcome writes. Quarantine re-admission checks exact existing copy bytes, re-fences the namespace, and does not truncate at capacity. ACKNOWLEDGED is durable before STOPPED removal; the tested early acknowledgement cuts remain fail closed. These mechanisms do not repair the independent identity and ordinary base-switch issues above.
- Whole-body request sizing includes selected messages, tool schemas, model, tool_choice and correlation label before REQUEST_SENT. Response caps, stored/invoked/hard call-count boundaries, wire-ID reservation and originals FIFO limits are present. The literal envelope tests distinguish complete serializer shapes; no claim of live SDK/provider compatibility follows from them.
- Previous-base replay checks the intermediate conversation hash before adopting newest checkpoint state. Keep that check: SV021-02 is a retention/binding defect, not a reason to weaken the verifier.

Receipt §3's **no resume-time checkpoint** deviation is not accepted as currently closed: it leaves the false previous-base binding and repeated deletion/switch paths above. It can remain only if corrected durable authority and base retention make every repeated-start path converge. The **unpublished first lineage** distinction is a reasonable way to recover a first run before CK5; it must still complete the legacy-note migration obligation. Copying A6 evidence while leaving the original in place is a sensible fail-closed choice. Carrying exact base-switch lists and notices as blobs is appropriate.

The following are safe staged deferrals by themselves:

- **Destructive GC disabled:** retaining segments/blobs conservatively preserves evidence. Do not claim bounded total disk, C-G1/O2-4 execution or full K-F1 completion. The retained-reference function is preparatory evidence only.
- **Exact replay bounds unclaimed:** this is consistent with V2-06's domain caution and the receipt's additional payload shapes. The review does not accept 358/717-record or corresponding byte bounds, measured resource behavior, or the test name “largest frame” as a universal domain proof. Threshold/rotation machinery does not by itself establish those claims.
- **Unimplemented acknowledgement resolutions refused without mutation:** deferring bootstrap-preserving and the other listed resolutions is fail closed, and is acceptable for an explicitly limited WIP tranche. Do not advertise full operational resolution coverage. This does not excuse an implemented continue-conservative path that allocates unsafe identities.
- **Volatile queued duty messages and external recap append-before-fold:** the receipt discloses their limits. SV021-06 concerns required runtime notices derived from durable records, not the voluntary volatile queue.

## Correction and evidence boundary

Return these findings to the Opus implementer as one focused correction pass. Repair identity allocation first, then the source-file authority/previous-base transaction, legacy-note closure, notice closure and detached history view. Add the discriminating local fixtures above, using bounded temporary roots, injected crash cuts and local stub effects. Preserve existing assertions and the corrected O1-5 pair; do not replace failing expectations with the current behavior.

The coordinator should select bounded runs for the affected recovery/checkpoint/notes/session/adoption paths and retained termination/group/script integrations. Another whole repository suite, live model call, actual stop acknowledgement, deployment, merge, pump change or H/T/Q decision is unnecessary and remains outside this review. Obtain a new immutable correction commit and repeat independent review before accepting activation. The seven findings are supported by static execution traces; their proposed regressions are not claimed as newly run failures.
