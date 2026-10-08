# SV-028 Astra implementation review

**Decision: changes needed.** The archive transaction and most L1–L7 requirements are implemented with meaningful bounded evidence. Two concrete corrections remain: physical replacement headers are counted as logical recovery-plan records on interrupted preserving recovery, and late-copy refusal messages falsely claim that nothing changed. These require a focused implementation correction, not a new design or owner-policy round.

Reviewed immutable head `517de5b4a41bded9b58a7be54199eee7b814d112`, tree `673417b9658fa128a15b8474d4014c3905b6ee5f`, runtime/test commit `2b535227f7e603f986db05676aeec941ee592a36`, against accepted architecture base `a70620ae0c496276864e1da20179f88d0c9d3e2b`. Governing acceptance is `docs/planning-context/sv028/ASTRA-DESIGN-ACCEPTANCE.md`, including L1–L7. All runtime/test line references below are at the reviewed head.

Static review only: I inspected immutable Git objects, test assertions, the supplied receipt and canonical/review constraints. I ran no tests, imported no project code, and performed no provider, runtime-edit, worker or real-session action. Only this report was written. The two main file hashes independently calculated from Git objects match the coordinator receipt: startup `65510082c204165d03ddc4642b124c28e574edaf557a1c823a78c54dd2d46840`; new test module `6b3c0ef80c42bf75aac32e175a699e0d150457d67a1fb64f282316693b132f1a`.

## Findings

### SV028-09 — P2: a recreated physical header prevents logical recovery-plan resumption

**Locations:** `services/chassis_startup.py:1824` (carrier-free completeness check), `:2092` (extra-to-core comparison), `:2099` and `:2119` (physical counts used for logical length/slicing). Supporting admission/reconstruction paths: `:1170`, `:1558`, `:2180`; `services/chassis_persistence.py:428` and `:1208`.

The preserving verifier and the planned core correctly distinguish physical LEDGER_HEADER records from logical Π records. `_recover`'s resumed `extra` processing does not: it compares every physical record directly with the next logical item and uses `len(extra)` to decide what remains. The carrier-free preserving check has the same mismatch. This produces a diagnostic stop for an admitted, ordinary crash shape.

**Reachable shape and exact failure trace:**

1. An ordinary rotation creates segment S+1, then the process dies before writing its header. The newest segment is empty. `scan_segments` accepts that newest empty file as a clean end (`chassis_persistence.py:467–474`). A later A14-unbound diagnostic over this store can carry a valid witness: `stop_witness` records both `last_segment=S` and `end_segment=S+1`, and `witness_problem` explicitly permits that relation (`chassis_startup.py:479–488,514–516`). No forged carrier, unauthorized gap, new stop reason or non-neutral suffix is needed.
2. Phase A admits W1 and preserves the empty successor file along with the remaining inventory. Phase B's `LedgerWriter.continue_after` reuses the empty S+1 and starts its header (`chassis_persistence.py:1231–1234`). Let this write tear. `_next_own_frame` explicitly recognizes that exact header prefix as the transaction's next physical frame (`chassis_startup.py:719–725`).
3. The next start publishes RECOVERING anchored at the last complete record in S, copies/truncates the original header fragment, and recreates the complete header in S+1. Let it die after the header is durable but before RECOVERY_ACK is written.
4. On the following start, B0 correctly excludes the header from the logical owned prefix. `_from_intent` returns `p0` through the anchor in S, and `extra=[LEDGER_HEADER]`. The frozen logical core is `[RECOVERY_ACK, spend?, EXTERNAL_DELETE, T]`, with T documenting the original torn header.
5. At `:2093`, the header is compared with RECOVERY_ACK. The start stops `recovery_intent_mismatch` instead of completing the acknowledged recovery. STOPPED then blocks automatic retry. The live unreadable conversation and archive remain preserved; this is an availability/crash-convergence defect, **not a demonstrated data-loss trace**.

There is a second exact variant: allow step 3 to finish Π+T and retire the carrier, then die before removing RECOVERING. The carrier-free start sees `extra=[LEDGER_HEADER, *Π, T]`; `:1825` rejects its physical length as greater than the logical core. This violates the accepted carrier-free completion rule even though every required logical record is already present and the live conversation was durably removed.

**Required correction:** use a preserving-specific logical cursor/projection for Π/T comparisons, completeness, remaining-core slicing and extra classification. Continue to validate, replay/account for and sync every physical header exactly once; strict scan/chain/segment checks must remain authoritative. Do not merely relax the mismatch assertion or discard headers from the physical replay. Keep prior acknowledgement mechanisms' semantics unchanged unless a separately evidenced adjustment is necessary. This can be corrected within the existing startup module and W1 scope.

**Why the existing passes do not close this:** N8 covers receipt/spend/activation tears in an existing segment, while the N6 sweep starts from the ordinary `run-end` fixture. N1's collected/rotated fixture proves a completed header in its neutral suffix, not this empty-successor → torn-header → recreated-header → second-death path. The scanner/writer's supported empty-successor shape is therefore not exercised by those passing cases.

**Freeze three new cases under one exact node:**

`tests/test_chassis_bootstrap_preserving.py::test_sv028_an_own_torn_header_preserves_the_logical_recovery_plan[uninterrupted]`

`tests/test_chassis_bootstrap_preserving.py::test_sv028_an_own_torn_header_preserves_the_logical_recovery_plan[header-only-restart]`

`tests/test_chassis_bootstrap_preserving.py::test_sv028_an_own_torn_header_preserves_the_logical_recovery_plan[carrier-retired-restart]`

Build the empty successor before taking the real stop, preferably using a cut at the actual writer's rotation/header write. Assert `end_segment == last_segment+1`, an empty successor and a valid actual A14 witness. After Phase A, create a strict prefix of the genuine next header and prove TC1; do not place a header illegally inside an existing segment. Reuse the real recovery path and fault hooks for the subsequent cut. Assert exactly one physical replacement header, one logical Π, one T bound to the original fragment, epoch+1 once, unchanged pending-note/request state except the specified closure, preserved independent inventory, no request/tool effects, retired carrier/intent and a later ordinary restart writing no extra records.

**Pre-correction expectations:** `uninterrupted` passes as the control; `header-only-restart` and `carrier-retired-restart` fail at the resumed opening's expected successful BP/convergence assertion with actual `recovery_intent_mismatch`. Require those behavioral failures after complete setup, not an API/import/fixture error. All three must pass after correction. The latter case must establish that the carrier is absent and RECOVERING still present before the tested restart.

### SV028-10 — P2: late-copy refusal still reports a false no-change outcome

**Locations:** `services/chassis_startup.py:424–429`, `:876–884`, `:1117–1122`; visible CLI rendering `services/chassis.py:1767–1769`. Existing discriminator: `tests/test_chassis_bootstrap_preserving.py:1659`.

L3 correctly changed the transaction documentation to preserve the completed prefix on a late refusal. The actual exception path still uses the shared `_refuse`, which appends `; nothing was changed` to every message. `AcknowledgementRefused`'s class docstring also makes that unconditional claim.

**Concrete trace:** the existing late-copy test publishes MANIFEST and copies STOPPED and earlier entries, then changes `agent-notes.txt` before `_copy_entry` reads it. The code raises:

`preserved_source_changed: ... changed after the inventory; the inventory and earlier copies are kept; nothing was changed`

The last clause is false, and the CLI prints it verbatim. The test verifies the real partial inventory/copies but matches only the leading token, so it passes despite the contradictory operational report. Late `_read_source` failures—missing source, over-limit source, or read failure—also inherit the same false suffix after earlier archive mutations.

**Required correction:** make late-copy diagnostics accurately state that the transaction stopped with its already published inventory/copies retained. Preserve the existing “nothing was changed” wording for genuinely pure admission and prior-pair refusals; do not globally alter their semantics to repair this new stage. Apply the stage distinction to `_copy_entry`'s hash mismatch and all `_read_source` refusal paths used during copying. Correct the exception class's overly broad docstring. Do not convert these refusal conditions into permission to repair a source, roll back evidence, publish a carrier, or fabricate FSYNC_FAILED; retain the existing late-I/O/marker rules.

**Bounded regression:** strengthen the existing `test_sv028_a_source_change_during_copy_keeps_the_published_inventory_and_prior_copies` to capture the exception and assert a stage-accurate retained-prefix message with no “nothing was changed” claim. Add finite internal companions for a source disappearing and an injected over-limit source at the same late-copy boundary; no large file is needed. A controlled late read error may be included in that same fixture. Each companion must first prove MANIFEST and an earlier copy already exist, then assert no carrier, activation or live-conversation deletion. Keep a pure-admission message control in the existing refusal node. These refinements need not add pytest-selected node counts.

## What the implementation and assertions establish

- The six-pair registry and its mechanism subsets are coherent, and the prior capability test changes only the reviewed SUPPORTED pair. The CLI change is the intended trusted home-directory argument.
- Phase A makes its admission decisions before mutation, validates a fixed MANIFEST on retries, distinguishes owned scratch from pre-existing temp-shaped evidence, and applies the capacity predicate after every lifecycle branch. L1's explicit inherited-inventory establishment precedes cleanup/mkdir/copy. The source-change refusal retains its bytes; the remaining issue there is its diagnostic claim.
- New and reused set files receive file fsyncs and the containing leaf-to-root directory fences. Equal MANIFEST reuse allocates nothing. N16's omission mutation actually leaves the pending reused entry under the sealed ancestor and loses it in simulated host loss; N17 covers both ancestor-rename reversal and removal without resurrection. The helper re-resolves directory identities for each undo.
- N19's repaired hook is now explicitly scoped to the live session parent. This avoids cutting on the independent archived pre-existing ACK temp file during E. Its complete-partial/reverted-rename/sealed assertions and below-cap companions are discriminating. N15 also measures the permitted U>cap cleanup case, distinguishing the invocation peak from the post-cleanup allocation bound.
- Phase B validates the saved STOPPED entry and recomputes the acknowledgement/binding against the carrier; it does not require the intentionally absent live STOPPED. N9 independently changes the saved stop while adjusting outer entry/digest checks, isolating the stop-binding rejection.
- Frozen continuation derivation occurs before owned records are replayed. The spend-readable mutation changes the derived plan and triggers the expected own-prefix failure. B3's inherited-activation fence precedes the destructive unlink, including a restart that writes no frame. The second-death and omitted-B3 mutation controls distinguish readable from durable activation.
- The finite late-EIO cases assert the actual completed prefixes—seal present, carrier possibly present, STOPPED possibly absent—and permit only failure handling afterward. They do not falsely require rollback or prove arbitrary recovery after an I/O error.
- The preservation inventory is computed independently of the production selector, includes the planted unknown/corrupt/HANDOFF/temp evidence, and checks independent inode identities. Later ordinary replacement and GC controls demonstrate real changes to live files while the archive stays unchanged. Pending-note versus no-note cases match the accepted A12 path; older-known-prev is exercised with a real collection.
- The real CLI control uses the real local recorder and a local stub, asserts no traffic before the request barrier, then checks the next label, no seen-before marker and stripped headers. This is useful bounded integration evidence, not a provider or real-session test.

## Receipt calibration and correction scope

The supplied `results/SV-028-implementation-test-receipt.json` records 15 commands: B0 and D1–D3 before the first runtime edit, ten successful final selections, and the earlier failed F7 attempt. Successful counts are `[14,1,1,9,10,1,22,35,1,14]` = **108 selected cases**, with 58 new and 50 retained. The stated last runtime edit precedes the final batches. The one later fixture edit is local to N19's cut predicate, and its full F7 selection was rerun. Source inspection supports the receipt's limited interpretation; these passes do not establish the missing header case or correct the late diagnostic.

For a **preserving-specific logical cursor** and stage-aware late refusal correction, **the same 108 selected cases plus the three exact new header cases are sufficient for the next bounded acceptance attempt: 111 final selected cases**. Keep the 50 retained targets and existing resource/serialization limits. Add the three new cases as a separate small final command, avoiding expansion of unrelated suites; run their pre-correction control/failures separately. The diagnostic companions remain within the existing selected node. A fix that instead changes shared old-pair semantics would require a separately justified focused selection; that broader change is not requested here.

Update RECEIPT/STATUS with the two failures, their bounded correction evidence and precise test counts. No new architecture round, source/oracle change, owner choice, real-session acknowledgement, provider call, merge or deployment is authorized or required. Numerical replay, aggregate startup reads/RSS, kernel power loss and held H/T/Q/pump/history policies remain outside acceptance. SV028 runtime acceptance remains held until immutable correction review.
