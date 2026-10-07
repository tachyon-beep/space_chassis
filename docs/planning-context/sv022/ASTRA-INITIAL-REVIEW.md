# SV-022 Astra initial review

**Changes needed.** Two bounded corrections are required before accepting destructive GC activation: the restart path must make a readable pending intent durable before unlinking, and the intent validator must enforce the segment-prefix condition on which the strict-scanner recovery design depends. Keep SV-022 unaccepted on the isolated WIP branch. SV-021's acceptance is unchanged.

Reviewed immutable head `6a2e504a0dd104d20139510dfc0188140af7af7c`, runtime/tests `efc6c03a9b205132f334c3b00eb95d3605e8a61c`, against accepted base `630623a4af30a8d08e90f5d9b0d2ef626af20f13`. Only RECEIPT and STATUS differ between the runtime/test checkpoint and review head. References below are to these immutable objects. Authority: canonical SV-015 v2 §§1.1, 1.4.5 and 1.4.9; the SV-022 preflight; accepted SV-021 state/identity/recovery contracts. Static implementation and assertion review only: no tests, project imports, providers, runtime edits, real-session deletion, merge or deployment. This report is the only written output.

## Required corrections

### SV022-01 — P1: startup unlinks under a readable intent whose file bytes may still be unsynced

**Location:** `services/chassis_startup.py:518–531`; compare `services/chassis_persistence.py:1164–1196`, `:1294–1308`. The modeled-durability blind spot is in `tests/test_chassis_gc.py:153–159`, `:207–214`, `:603–636`.

The live collector correctly syncs GC_INTENT before unlinking. Startup does not repeat that gate. A complete intent readable after a process death can be an append whose original fsync never returned. `LedgerWriter.continue_after` syncs the session and ledger directories, then opens the existing segment; it does not sync that segment's data. Startup subsequently calls `unlink_intent` before writing GC_DONE or any other ledger record. Directory fences do not establish the durability of the intent's appended bytes.

**Failure trace under M-1 followed by M-2:**

1. A durable checkpoint has a valid collection plan naming several old segments. GC_INTENT's full write returns; the process dies immediately before its file fsync. No deletion has occurred. The full intent remains readable under M-1.
2. Restart classifies the clean tail as TC0, validates that intent and its retained basis, and calls `continue_after`. Only namespace fences return.
3. Restart unlinks the first listed segment and successfully fsyncs ledger/. Crash before GC_DONE is appended or any file fsync covers GC_INTENT.
4. On host loss, preserve the fenced deletion but discard the original unsynced intent append. The checkpoint remains durable. The next start has a shortened prefix and no intent naming the newly missing boundary, so it stops `ledger_prefix_missing`. The valid interrupted collection no longer converges, and deletion has outlived its authority.

The same missing gate applies when resuming a readable intent after an acknowledged intent-fsync failure. An acknowledgement grants continuation; it is not a data sync. This is within the stated mixed-failure model and requires neither hostile file rewriting nor checksum forgery.

**Correction:** after validating a pending intent, sync the file containing its verified frame before the first unlink. Retain the existing namespace fences and the exact stored deletion list. A failed sync must take the persistence-failure boundary, attempt the marker, and perform no unlink or later effect. Do not write GC_DONE early merely to obtain a file sync: completion must still follow the deletion fences. Ensure the fence covers the intent's actual segment rather than assuming any newly opened segment's sync covers it. Preserve the frozen recovery-core comparison and append-only completion behavior.

**Discriminating regression:** carry the original file durability watermark across an initial process-death restart; do not promote all readable bytes to durable on opening a new test descriptor. Crash after the original intent write but before its fsync, restart, cut after a segment unlink's directory fence but before GC_DONE, then simulate host loss using only syncs that actually returned across both processes. Require authority to survive and two subsequent starts to converge with one completion. Add a failure of the new startup file-sync gate and require zero unlinks. An event-order assertion should require that successful file sync before restart's first unlink.

The existing second-interruption fixture starts after the original intent was synced. Its new `CutOps` also initializes each opened segment's durable length from its current readable size. The single-transaction cut matrix and M2 negative control therefore do not discriminate this mixed process-death → host-loss trace. Preserve those useful tests and extend their durability model for this case.

### SV022-02 — P2: intent validation accepts an eligible sorted list that creates a ledger gap

**Location:** `services/chassis_gc.py:221–289`, especially `:234–235` and `:278–280`; deletion at `:314–316`; startup consumption at `services/chassis_startup.py:561–580` and `:527–531`.

The normal planner emits a prefix of the existing eligible segments. The validator checks ascending unique numbers and the retained/active upper bound, but does not require the named segments to cover a prefix of the surviving ledger. The stronger per-segment fence proves contiguity only when that additional condition holds.

**Concrete malformed-intent trace:** use the existing `planned`/`write_intent` fixture boundary with present eligible segments `[1,2,3,4,5]` before retained segment 6. Change only the deletion list to `[2,3,4,5]`, preserving the valid checkpoint, cover, blob list and a correctly framed GC_INTENT. `intent_problem` returns no problem: the list is ordered and every named segment lies below the retained limit. Startup executes it and appends GC_DONE. Segment 1 survives followed by segment 6, so the next strict scan stops `ledger_damaged_at`. A similarly sorted list skipping an interior eligible segment has the same defect.

This is an incomplete invalid-intent validation contract, not a claim that the current planner spontaneously produces that list or that M-3 can forge a valid frame. It is the same chain-valid malformed-payload boundary already exercised by the retained-blob, cover and protected-segment startup fixtures. The claimed validator currently approves a list that violates the collector's own recovery invariant.

**Correction:** validate the prefix property before either live intent publication or pending-intent execution. No named surviving segment may be deleted while an older surviving segment is omitted. Reject holes that would leave an internal gap. At restart, continue to allow already-removed leading items in the original fixed list and ENOENT idempotence; do not replace that list with a fresh scan or reject an ordinary partial prefix deletion. Retain the existing refusal of unrelated ledger gaps.

**Discriminating regression:** add front-skipping and interior-skipping sorted lists to the pure validation cases, plus a chain-valid pending-intent startup case requiring `gc_intent_invalid` and byte-identical state except STOPPED before any unlink. A live invalid-plan control should also refuse before GC_INTENT publication. Keep the partial-unlink restart fixtures passing to distinguish validation from a blanket rejection of absent listed segments.

## Mechanisms and evidence that should be preserved

- **Retention:** `retained_basis` validates the exact `C_n.prev` tuple, both checkpoint states and the available interval, then unions newest-state, previous-state and retained-record references. It includes the true older previous checkpoint after A11. The union and last-two-checkpoints controls discriminate important losses; O2-2 assertions check actual removed segments, previous-file hash, exact recovered messages and no new INVOKING.
- **Live transaction and namespace:** the live owner publishes and syncs a bounded intent before unlinking, deletes only canonical segment/blob names, fences each segment unlink and then blob deletions before GC_DONE, and stops mutation on persistence failure. The 4096-item default fits the record-body limit; one batch per checkpoint avoids recursive checkpointing. The stronger segment fence is a sound design choice once its list precondition and restart data gate are enforced.
- **Pending ownership:** startup validates the retained intent before deletion and processes its fixed list before new startup blobs can be written. It does not silently collect leftovers. GC_DONE is first in the recovery core, and an existing compared completion avoids repeating deletion after new recovery records. Preserve this ordering while adding the missing durability gate.
- **State and protected authority:** IDENTITY and RECOVERING are outside the deletion namespace; unresolved recovery/acknowledgement/stop files block new live collection. Pending foreign-adoption flags remain checkpoint state alongside their retained blobs. The latest file-binding suffix remains above the retained floor. Imported-note and adopted-conversation blobs remain in `record_refs`. The state fixture physically removes request, note, recap and history source records and compares restored state, memory and labels.
- **Local correlation:** the two recorder/chassis subprocess fixtures inspect ledger/open-label equality, attempt advancement, no recorder/upstream request before the restart barrier, actual collection and no repeated tools. They check upstream and transcript stripping; the first fixture joins the completed request's transcript to its open event by recorder ID. This supports local-stub correlation, not authentication, idempotency or deployed-provider behavior.
- **Retained alias assertion:** replacing genesis replay with checkpoint-based startup replay is justified after collection. The live/history/file equality and A14 previous-base assertions remain. No need to restore a genesis-only expectation that depends on obsolete blobs remaining on disk.

## Evidence and correction boundary

RECEIPT reports 557 selected passes in 11 bounded batches, four restored source mutations and four in-test controls, with worker exit 0 after the interrupted session resumed. I inspected the relevant assertions and immutable final bytes independently; these are reported runs, not tests reproduced by this review. `git diff --check` found no whitespace errors. Test count and restored mutations do not cover SV022-01's mixed crash sequence or SV022-02's missing prefix validation.

Return these two focused corrections to the implementer, retain the successful assertions, and freeze a new runtime/test checkpoint for independent re-review. Temporary-root fault injection and the existing bounded targets suffice; no broad suite, live provider, real-session deletion or new product decision is required.

The explicit nonclaims in RECEIPT §§7/9 remain appropriate: exact numerical replay bounds, bounded total disk, real power loss/kernel behavior, newly created rotation-name loss simulation, remaining acknowledgement resolutions, deployed compatibility and full K-F1 completion remain outside this package. Refusing arbitrary gaps is acceptable. It does not resolve a gap that the validator itself authorizes or authority lost by the new restart path. Main merge, deployment and pump/H/T/Q work remain outside authorization.
