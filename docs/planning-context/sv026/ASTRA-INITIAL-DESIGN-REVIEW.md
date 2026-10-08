# SV026 independent Astra design review

**Changes needed. Do not implement this draft yet.** The restart accumulator and closed-boundary approach is useful, and the proposed placement after recovery cleanup is substantially correct. The draft nevertheless substitutes a narrower quantity for the canonical frame/blob quantity, overlooks a production metadata callback before startup returns, and has several incorrect or missing acceptance conditions. These are bounded design corrections; no H/T/Q/pump choice is needed to resolve them.

Reviewed immutable head `10eed7fbe18b044bf29becd29f3e85ae67f4bb60`, against accepted SV025 checkpoint `1ede8a3`, in `execution/sv016-recorder`. The diff consists only of `docs/planning-context/sv026/DESIGN.md` and `STATUS.md`. I read those immutable objects, the relevant unchanged runtime/test paths, canonical SV015 v2 §§1.4.1/1.4.7/1.4.8, the C-G2 source row, and the planning/permission receipts. No tests, imports, runtime changes or provider calls were made. The design's description of SV025 as still under review is stale: SV025 correction 1 has been accepted as evidence only; update the design provenance without changing its scope.

## Required revisions

### SV026-01 — P2: distinguish the checkpoint baseline from real suffix headers; test stability does not authorize their exclusion

**Locations:** DESIGN `:22–46`, `:98–108`, `:141`, `:243`, `:256`, `:326–327`.

Excluding the newest checkpoint's own frame from an operational “since checkpoint” trigger counter is consistent with the live CK6 reset. That does not erase the frame when physical replay starts at `covers_seq + 1`; the latter remains a separate term in the unresolved recovery bound. D1 can use this convention if the design states that distinction accurately.

A rotation header **after** that checkpoint is different: it is an actual frame in the outstanding suffix. Canonical §1.4.1 counts records since the newest checkpoint, and §1.4.7 measures ledger frames and replayed blobs. Neither gives a general exemption for suffix LEDGER_HEADERs. Writing outside `_commit` is an implementation gap to reconcile, not source authority to exclude them.

**Discriminator:** begin at a checkpoint, create a later rotation header, then enough small direct messages that header plus messages reaches the chosen threshold while messages alone do not. The proposed counter and its filtered oracle both omit the same existing frame; their equality would pass despite the missing canonical work. Compare against a byte walk that retains this header, and require live/restart parity without changing its durability ordering.

The C-G2 conflict is overstated. `test_c_g2_direct_says_checkpoint_after_records_8_and_16` uses `Session.start_fresh`, one initial genesis header and no rotation. Its `[9,18]` positions do not require ignoring later headers. An explicit initial-header baseline can preserve that oracle while accounting for subsequent rotation headers, including those before the first real checkpoint. Do not assert that charging suffix headers necessarily changes this golden fixture.

**Correction required:** specify separately the initial baseline, C_n's own frame, and every subsequent header; reconcile live creation/rotation/continuation with restart accounting. A small writer-to-session accounting interface may be required, so the promise that LedgerWriter cannot change must not prejudge the solution. Opus should propose that interface and its tests in the revision. Do not alter canonical golden values merely to make the implementation convenient.

If the revision deliberately postpones header work, narrow the package to repair of the existing **data-record byte counter**, preserve held record/header behavior, and state prominently that canonical suffix accounting and related threshold guarantees remain incomplete. It must not retain the current “same quantity”/complete-ACC claims or present an oracle that filters the omitted work as proof of the canonical property.

### SV026-02 — P2: validated payload bytes are not all bytes read by replay; the damaged-blob residual needs two quantities

**Locations:** DESIGN `:23–29`, `:42–54`, `:98`, `:245`, A2 at `:252`, D3 at `:328`.

The proposed wrapper measures bytes returned **after** `BlobStore.get` verifies the hash. A DONE file can be read successfully, fail hashing, and still yield a usable lost-payload replay with zero proposed blob charge. That read occurred inside the selected record's replay; it is not a scanner read, retained-only reference, or excluded conversation-base read.

**Concrete trace:** a valid small DONE refers to hash H. Replace the temporary H file with a larger wrong-hash file, still below the 64 MiB reader limit. `DurableOps.read` returns the entire replacement; `BlobStore.get` hashes it and returns None; `_on_done` emits lost-payload text; proposed W charges only the frame. The discrepancy between W and the successful physical read is the replacement's length, not the original CAP_RESULT size. A file over the limit has another distinct path: `DurableOps.read` reads `limit + 1`, raises `ReadTooLarge`, and `BlobStore.get` catches it as OSError and returns None. Neither the proposed W nor the SV025 successful-return observer records those obtained bytes. The relevant source is `chassis_persistence.py:923–929` and `:1079–1086`.

L1's “at most CAP_RESULT” can correctly describe the difference between a previously valid result's payload charge and zero at a later restart, at default result caps. It **cannot** also bound omitted physical replay reads. Likewise the exclusion table's physical-read bound must account for the over-limit probe, rather than stating simply `<= BLOB_READ_MAX`.

**Correction required:** choose and name the implemented measure honestly. For canonical frame/blob-read accounting, specify how the existing bounded read exposes byte/outcome information before hash rejection, including the over-limit case, without reading the blob again. Separate missing-file/failed-I/O attempts, obtained bytes rejected by validation, accepted payload bytes, and the historical payload-charge difference. A validated-payload-only diagnostic can be useful, but it is a narrower measure and cannot silently replace the specified threshold quantity.

Add discriminators for a wrong-hash file whose length differs from the original and an over-limit read. A small injected reader limit is sufficient for the latter if explicitly labeled; no 64 MiB allocation is necessary. State whether exact partial I/O under arbitrary read errors is outside the metric rather than inventing zero physical work. Keep the lost-DONE semantic outcome unchanged.

### SV026-03 — P2: startup checkpointing invokes production metadata before Chassis has adopted the recovered session

**Locations:** DESIGN C6/C9 at `:103`, `:106`, startup pseudocode `:133`; source `services/chassis.py:1031–1034`, `:1141–1161`, `:654–656`.

The new startup checkpoint would call the existing `meta_source=self._meta_fields` while still inside `open_session`. `Chassis.run` assigns `self.session = opening.session` only after that function returns. Until then `Chassis.messages` returns the initial `_messages`, not the recovered session's messages. `_meta_fields` derives `context_tokens` from that stale list.

**Failure trace:** recover a nonempty, over-threshold suffix → proposed end-of-open checkpoint → install the correctly recovered conversation → `_meta_fields()` sees the new Chassis's empty `_messages` → persist a run.json context count for the empty list. A subsequent startup failure before a later checkpoint leaves that inconsistent metadata on disk. Direct `Root.start` fixtures with the default empty metadata callback do not detect it.

**Correction required:** the design must make callbacks used before `open_session` returns consume the recovered checkpoint state, or otherwise supply equivalent truthful startup metadata. Audit callback readiness at that exact boundary; do not solve it by weakening the metadata assertion or discarding fields. Add one bounded fixture using the actual Chassis metadata/install integration, with a nonempty recovered conversation and a threshold checkpoint before duty/client activity. Verify the stored context count against that conversation. This is ordinary integration work, not an owner policy choice, but C9 cannot remain “text only” without a concrete solution.

### SV026-04 — P2: correct and complete the finite acceptance manifest before freezing it

**Locations:** DESIGN `:247–308`, particularly A1/A2/A6/A7/A9 and R3–R12.

The proposed 34-node arithmetic is correct, but several expectations are not:

- **A1 is not wholly a pre-fix pass.** After the specified `establish` and A9 startup, the current runtime has `since_records == 1` from C_n's frame. An oracle excluding it disagrees even if bytes agree. Distinguish the record-offset discriminator from the already-correct live blob charge.
- **A2 lost DONE cases still have recovery records.** `partial_turn(..., 4)` leaves the later call unclosed, so restart emits its closure. The missing/damaged formulas must include newly written recovery-frame work as the intact formula does; do not assert only `c1 - len(blob)` for that setup.
- **A6 needs a precise starting helper.** `Root.start()` A4 writes LEGACY_IMPORT after the genesis header; `Session.start_fresh()` does not. “Fresh start + 3 says = 3” and a subsequent suffix containing C_n require an explicit setup consistent with the chosen baseline. Separate initial-header and later-rotation cases as required by SV026-01.
- **A7 cannot require an IDENTITY rename on every recovery.** `reserve_turns` returns without writing when the durable reservation already covers the target. In the ordinary partial-turn setup it normally does. Require verified durable coverage before the new checkpoint and the correct order **when a reservation write is needed**, rather than requiring an unnecessary write.

Add a focused lifetime/reset case: charge a blob, checkpoint, then commit another record using the same Replay instance, and compare the new interval with an independent observation. Repeat with a post-checkpoint GC pair. This discriminates accidentally assigning cumulative lifetime work to the interval after a reset.

The new follow-up checkpoint also needs a small crash/failure composition fixture, not just three successful tails: cross with an actual GC pair, interrupt the follow-up around installation/CK6, restart, and verify previous-base recoverability, no replay of spent deletion authority, bounded further checkpointing and the intended `ended` behavior. Include one failed new checkpoint fence with no later effect. Existing ordinary checkpoint/GC tests remain valuable but do not establish these newly composed transitions by themselves.

R3–R12 lists ten complete files without frozen node/parameter counts or a dependency rationale. This is not an exact bounded manifest yet. Select the affected account/replay/notes/checkpoint checks and the accepted startup, acknowledgement cleanup, pending-GC and namespace guards explicitly; reuse the prior accepted guard manifests where applicable. Whole affected modules may be justified where coverage is genuinely shared, but report their finite expanded counts and split commands within the existing caps before launch. Include the production callback fixture above. Do not restore test counts by removing meaningful cases.

## Sound parts to retain

**Accumulator mechanics.** Lifetime `Replay.work_*` sums plus a before/after delta for each live `_commit` are a sound approach. Session counters can reset after CK6 without resetting the lifetime sums. Startup must initialize from only the selected `decision.replay` after its readable extras have been applied, then charge only newly committed records. The previous-base `middle` replay uses a separate instance; its historical interval must not be multiplied into the newest trigger counter. Rejected candidates and witnessed verification likewise must not contribute. The draft correctly identifies these distinctions. Correct the W definition first, then retain this architecture and add the reset discriminator.

**Startup transaction boundary.** The check belongs after `_finish_case`, durable sync of inherited extras, the appropriate witnessed/non-witnessed carrier/intent retirement order, and IDENTITY coverage. It must remain after quarantine admission and pending-intent completion. A checkpoint under RECOVERING would be an unplanned extra and can break exact replay/binding authority; the draft correctly avoids that. Do not reorder these operations to simplify accounting. A live stop or rejected state must not be converted to a guessed zero counter.

**Per-generation adoption.** D5's separate closed generations/file-edit/drop checks are supportable: pending generations, adopted watermark, foreign marks, mirror hashes and drop count are checkpoint state. CKG guards must still prevent a checkpoint during a tool group or while its queue is nonempty. The whole group/flush remains the relevant unit there.

**GC G2.** One non-collecting follow-up is a coherent way to handle an injected threshold crossed by a GC pair. GC is optional after CK6, so declining GC on the follow-up is not a new product-policy choice. Preserve the same `ended`, return the final checkpoint record, keep ordinary previous-file binding, and make recursion/rotation placement explicit. The follow-up must be attempted only after successful GC_DONE, never after a partial collection or persistence failure. G1 is a deliberate delayed-check deviation, not equivalent canonical closure. G2 needs the composition tests above, not user selection between artificial alternatives.

**Threshold versus rotation.** D7 may keep threshold evaluation and rotation as separate operations, but “segment numbers would change in tests” is not a correctness rationale. Explain when an already-full segment is next rotated at a permitted closed boundary, including a startup whose writer inherited it. If rotation is deliberately deferred in a smaller tranche, state that limit; do not claim that all unit-boundary behavior has been closed. If live headers are charged, specify the post-rotation counter and avoid checkpoint/header loops at tiny injected thresholds.

## Recommended revision and authority boundary

Return a corrected **design only**: a precise baseline/read-outcome accounting contract; the smallest measurement/accumulator changes it actually requires; the safe startup and per-generation boundaries; G2's bounded follow-up; production callback handling; and a corrected finite manifest. Preserve the two SV025 default-constant counterexamples, moving the 27 MiB fixture's cut to the genuine pre-checkpoint crash window as proposed. Do not conflate corrected trigger accounting with proof of the 358/717 or byte inequalities.

If the header/read-outcome interface cannot be closed in this tranche, prefer an explicitly narrower byte-counter reconstruction package over implementing the draft's deceptive equality. State exactly what remains uncharged and do not change record/header conventions or frozen oracles under that narrower package. Opus remains responsible for proposing the concrete design; this review supplies acceptance conditions, not an implementation.

No genuine H/T/Q/pump or real-session user choice was discovered. Revised numerical contracts, a different accepted-history cap/representation, or a constant previous-base strategy still require separate source/design closure. A deliberate source exclusion of real suffix/failed-validation work would also require explicit contract treatment; it cannot be justified by old test positions. None of these decisions is made here.

The documented native permission denial was a compound read-only shell request lacking an approval surface; the receipt records the later dedicated-search deviation. It is provenance, not a host automatic-review rejection or additional authority. This review did not retry it or rely on an escalation. Implementation remains held pending the corrected immutable design review.
