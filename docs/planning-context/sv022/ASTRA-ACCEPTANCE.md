# SV-022 Astra correction 1 review

**Accept the staged SV-022 package at this immutable checkpoint.** SV022-01 and SV022-02 are closed. I found no further acceptance-blocking regression in the focused correction and its affected startup/deletion paths. This accepts the isolated WIP implementation of checkpoint-safe collection, post-collection recovery and the local recorder-correlation slice under the stated evidence limits. It does not authorize real-session collection, main merge or deployment, and does not accept SV-023.

Reviewed head `f6dcea2016dd1d7f9e00a6d516fec337e04c8a97`, runtime/tests `53c5c44b167f73e7aefb326fdeacfdced5839835`, against `6a2e504a0dd104d20139510dfc0188140af7af7c`. The runtime/test checkpoint and review head differ only in four planning documents. References below identify immutable Git objects. Authority remains canonical SV-015 v2 §§1.1, 1.4.5 and 1.4.9, accepted SV-021, the SV-022 preflight and initial review.

Static implementation and assertion review only: no tests, project imports, provider calls, moving-tree inspection, runtime edits, real-session operations, merge or deployment. This report is the only written output.

## SV022-01 — closed: restart fences the intent's file before unlinking

`services/chassis_gc.py:328–347` opens the segment identified by the verified intent record itself and fsyncs that file. It does not assume the current writer descriptor or a newer segment covers the intent. Open/fsync failure becomes PersistenceFailure, and the temporary descriptor is closed. `services/chassis_startup.py:519–534` calls this gate after validation and the existing frozen-core comparison, immediately before re-running the stored unlink list. Existing namespace fences remain in place. GC_DONE still follows deletion and directory fences; the correction does not publish completion early to obtain a sync.

The startup persistence boundary attempts FSYNC_FAILED and propagates the failure before any session is returned. The added gate therefore prevents deletion when it cannot establish durable authority. It also covers the readable-intent path after an acknowledged original fsync failure. The path with an already compared GC_DONE keeps its existing behavior: no second deletion pass is introduced after later recovery records may have created blobs.

The new regression at `tests/test_chassis_gc.py:1114` onward creates a complete intent whose original fsync never returned, then carries the first process's actual file durability map into the restarted `CutOps`. Restart dies after the first segment deletion and its directory fence; simulated host loss discards only bytes not covered by a returned file sync across those processes. The assertions require convergence over two further starts, one GC_DONE, surviving intent authority, and an explicit log entry syncing the intent's own segment before the first unlink. This directly distinguishes the original process-death → host-loss failure.

The paired EIO fixture requires failure at that segment's fsync, no unlink, no GC_DONE, unchanged inventory, a failure marker and A1 on the next start. The existing second-interruption fixture now also carries the original watermark. Reopening an already tracked file no longer promotes its readable unsynced append to durable in these discriminating cases.

## SV022-02 — closed: deletion lists must cover a surviving prefix

`services/chassis_gc.py:248–266` checks the condition needed by the per-segment fence proof: no named surviving segment may be removed while an older surviving segment is omitted. A listed absent segment must lie below the surviving ledger. `intent_problem` invokes this check at `:305–306`, after schema/order checks and protected-segment exclusion, for both live publication and pending execution.

Thus front-skipping and interior-skipping lists are refused before deletion. An original fixed list with already-removed leading segments remains valid; the implementation neither requires those names to reappear nor replaces the list with a fresh scan. Blob-only plans remain permitted, and the ordinary strict scanner still rejects unrelated ledger gaps. Together with oldest-first deletion and the fence after each segment, the validated list preserves a contiguous surviving suffix at the modeled cuts.

The added pure fixture checks both skipping forms and accepts the legitimate partial-prefix case. The two startup fixtures construct chain-valid malformed intents and require `gc_intent_invalid`/`segment prefix`, with the entire tree unchanged except STOPPED. The live invalid-plan fixture requires refusal before a GC_INTENT is published and no deletion. Existing partial-unlink, stored-list and repeated-interruption assertions remain intact. This closes the validator contract independently of the normal planner, which already emitted prefixes correctly.

## Integrated disposition and evidence

The correction changes two runtime files and the focused GC test file. It leaves the reviewed exact `C_n.prev` selection, full retained reference union, protected namespaces, body/item bounds, fixed-list replay, checkpoint-state restoration and recorder label/strip behavior unchanged. No new persistent schema or authority carrier is introduced, and no prior assertion was weakened. The GC accounting, true previous-base interval and accepted identity/foreign-note/file-binding dependencies remain as described in the initial review.

Checkpoint-001 and RECEIPT §10 report six pre-fix regression failures, followed by 563 selected passes in 11 bounded batches: 50 GC checks, two local recorder/chassis correlation cases and the retained selected recovery/foundation/runtime targets. I inspected the actual new assertions and implementation independently; I did not reproduce these runs. The immutable `git diff --check` completed without whitespace errors. The reported pre-fix failures match both static traces from the initial review.

The accepted claim is that eligible obsolete segments/blobs are collected under a validated bounded intent, interrupted deletion converges under the tested and modeled cuts including the mixed durability trace, required state and the true previous base survive actual collection, and local recorder correlation/stripping holds in the subprocess fixtures.

The existing limits remain: host loss is simulated; real process death is covered only where identified by the script/correlation fixtures. No general power-loss, kernel/storage or newly created rotation-name-loss evidence is claimed. Exact numerical replay bounds, bounded total session disk, remaining acknowledgement resolutions, deployed-provider compatibility and full K-F1 completion beyond the specified slice remain unclaimed. Arbitrary ledger gaps remain refused. No pump/H/T/Q choice is made.

No additional SV-022 correction is requested. The SV-023 preflight may name this accepted runtime as its next base, but its proposed acknowledgement implementation has not been implemented or accepted by this review.
