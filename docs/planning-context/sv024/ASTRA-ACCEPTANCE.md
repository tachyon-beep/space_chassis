# SV-024 Astra correction 1 review

**Accept SV024 within its existing staged engineering scope.** SV024-02's durable-intent dependency is closed, SV024-01 remains unchanged, and this static re-review found no remaining activation blocker for the bounded integrated O2-5 package. Acceptance does not authorize real-session operations, merge, deployment, providers or held H/T/Q/pump work.

Accepted immutable head: `9e792a56d9db4292fe7b358442c39031e78735c2`. Runtime/tests: `9bdfb37a5518687666f414b7579d245e3c6a7c95`. Correction base: `d94bc78e3cf69daec028b43fee180f88e559897d`; prior accepted foundation: `8bffe49ecf546d8581fb6e34bff6eb9e096d8841`. Runtime/test commit to reviewed head changes documentation only. I read static Git objects, checkpoint-001, updated STATUS/RECEIPT, relevant retained assertions and the external test receipt. No tests, imports, providers, moving-tree inspection or runtime edits were performed. This report is the only written output.

## Closure and ordering

`services/chassis_startup.py:323` adds `_fence_intent_inputs`. It fsyncs both the segment containing the valid-prefix anchor and the segment containing the tail, deduplicating them when they are the same file, then fences ledger/. Line 1060 calls it immediately before publishing a new sealed RECOVERING. The quarantine copy and truncation remain afterwards.

This closes both reviewed loss modes. A host loss after intent publication can no longer remove the newly named segment or drop its fragment: returned file syncs cover the anchor/tail bytes, and the returned directory sync covers their names. The existing writer protocol establishes the ledger-directory parent and earlier segment durability; SV024-01 additionally fences inherited bytes before rotation. Later truncation still depends on the already durable exact quarantine copy. The correction preserves intent hashing, identity and acknowledgement context, admission caps, copy-before-truncate ordering and missing-copy refusal for genuinely missing evidence.

Open/fsync/directory-fence errors propagate as PersistenceFailure before intent publication, copying or truncation in this path. The existing startup boundary attempts FSYNC_FAILED and returns no usable session. The new failure controls verify the preserved fragment, absent intent/copy, no ledger write/truncation, A1 precedence and explicit temporary-root acknowledgement. The added SV024-01 error control also verifies that a failed inherited-segment sync publishes no checkpoint files or record, rotates nothing and prevents further requests/messages.

## Discriminating evidence

The new partial-header fixture performs a short actual write through the fault shim and raises the in-process crash during that write. It explicitly verifies the zero byte watermark and unfenced new name before restart. It therefore does not repeat the earlier test's host-loss setup that made the surviving fragment a durable baseline.

The restart inherits those maps and is interrupted immediately after RECOVERING's rename and session-directory fence, before a copy exists. Both attempted name loss and kept-name/data loss now leave the required evidence intact. Recovery asserts exact fragment preservation, contiguous headers/seq/chain, the original checkpoint and protected state, no repeated collection, no effects, and subsequent convergence. A third variant interrupts again after truncation and recovers through the durable copy. It does not simulate truncation reversion, and no such claim is accepted.

The external receipt reports three discriminating pre-fix failures, then **161 successful selected executions across eight serial commands, representing 159 distinct cases**: 28 namespace, 97 recovery_live, 35 frozen retained and one conditional recorder/chassis case; the two startup-precedence cases overlap the 97. Worker exit 0 and no denials/retries/overlaps are reported. I inspected the assertions independently and did not rerun them. The earlier interrupted attempt is separately documented as reads only with a clean checkout and no evidenced edits/tests; it contributes no validation result.

## Coverage qualification

The worker correctly discloses a shifted retained cut. `tests/test_chassis_recovery_live.py:700` implements `after-first-record` by failing the second `.svl` fsync. The added pre-intent fsync moves that interruption to the quarantine truncation's fsync. Its unknown-versus-unrun and no-duplicate assertions remain useful, but this final run is **not** evidence of the first recovery-record fsync cut for those two variants.

This is a test-maintenance issue, not an additional demonstrated runtime failure: the correction adds a durability prerequisite before the unchanged recovery core, and the selected acknowledgement cut matrices exercise interrupted core/cleanup paths. Before advertising the old named cut as retained in future evidence, replace its numeric fsync count with a predicate tied to the intended record and verify that the intended append happened before interruption. Do not silently claim that unchanged assertions imply unchanged fault placement. No broad suite is required solely for that correction.

## Scope and next package

The accepted evidence covers the declared simulated segment-name/data outcomes after actual GC, the reported inherited-byte checkpoint failure, and the new pre-intent evidence dependency. It does not establish real power-loss/storage behavior, rename/truncation reversion, arbitrary torn shapes, all possible multi-crash compositions or exact replay-work bounds. No GC reference union, deletion authority, previous-base selection or acknowledgement policy was widened; unresolved carriers remain GC blockers.

SV024's acceptance prerequisite for the proposed SV025 proof/accounting package is now satisfied. SV025 remains a separately staged, proof-only proposal: rebase its immutable inspection on the accepted checkpoint, include these added pre-intent read/sync paths in the accounting inventory, and preserve canonical limits/oracles and duty-visible behavior. This review neither launches nor accepts SV025 and requests no additional execution.
