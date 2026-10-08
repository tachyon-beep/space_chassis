# SV-028 Astra design correction 2 review

**Decision: accept the W1 architecture for bounded implementation, subject to the mandatory launch qualifications below.** No further architecture/design-only invocation is required if the coordinator incorporates these qualifications as governing instructions before launch. This is design acceptance, not acceptance of runtime code or authorization for a real-session acknowledgement.

Reviewed immutable head `8e30cf865764f565ba4bf255a9b92f8492cdcf18`, tree `20a7c972cf5c6d28530f9442767e65c0d8bde019`, against governing residual review SHA-256 `64d8377115b5eb71d12249c9182470d9ad9858d3413880cdde2e6b74acfa5a14`, archived at base `05cc4f8616c108855246c8c8ea13a571eb9731c8`. The diff from that base changes only `docs/planning-context/sv028/DESIGN.md` and `STATUS.md`. Line references below use the reviewed DESIGN unless stated otherwise. Review was static: no tests, imports, providers, runtime changes, workers or real-session actions. Only this report was written.

## Closure of the residual findings

**SV028-06 is addressed by the specified mechanism.** E fsyncs every set file, then all containing directories from leaves to root, then `preserved/` and its parent (lines 342–358). It covers both new and reused destinations, runs before sealing, and re-establishes a sealed set before carrier publication on retry. N16 now exercises the exact reused-copy trace without an incidental later leaf write, including a mutation omitting its fence and an EIO control. N17 and the identity-keyed namespace model specifically preserve pending child-name obligations across the ancestor rename. Final implementation review must inspect the actual fault model and mutation result, not merely the test's name.

**SV028-07 is addressed by the selected reuse rule.** MANIFEST is published once and never rewritten. Its allocation delta is zero on reuse; E allocates no files. N19 distinguishes accepted exact-cap reuse from the old unbudgeted rewrite in complete-partial, reverted-rename and sealed states. All branches must actually run the capacity predicate, as qualified below.

**SV028-08 is addressed by the fixed inventory and ownership rule.** The sealed inventory precedes copying, binds the stop/witness/pair and exact file set, and is not silently recomputed on retry. Changed source bytes refuse without discarding the copied original. A mismatching unsealed copy may be replaced only after its live source verifies against that fixed inventory. Pre-existing ACKNOWLEDGED-shaped temps are now independently inventoried; only later, demonstrably transaction-created artifacts are excluded. Scratch cleanup stays bounded and conditional on verified surviving originals. These are appropriate engineering choices within the admitted namespace.

The previously accepted directions remain sound: one truthful six-pair registry; immutable Π derived from the witnessed head before replaying owned records; optional spend exactly once; fixed epoch increment; sealed carrier-free context; T after Π; B3 before live-conversation deletion even on a restart writing no core frame; A12-compatible note/bootstrap ordering; and ordinary older-known-prev/GC behavior. No held H/T/Q/pump decision is needed.

## Mandatory launch qualifications

### L1 — Explicitly establish an inherited readable inventory before further archive mutation

Lines 269, 299, 424–435 and 538 currently conflate a readable inherited MANIFEST with a returned durable boundary, deferring explicit re-establishment to E. Make the retry sequence explicit: after pure validation/admission succeeds, re-establish the validated MANIFEST's file and name dependencies, including its ancestor names, **before cleanup, child-directory creation or copying**. Do not rewrite the inventory. Failure takes the Phase A persistence boundary and grants no subsequent authority.

Calibration: I do **not** establish the suggested “durable copies survive but their MANIFEST disappears” failure under the complete existing A3 order. A3 requires the set-root directory fence when establishing `session`/`home`, before any copy can be durably created there; this implicitly fences the MANIFEST name. That is why this is an explicit launch-order qualification rather than a new architecture blocker. Avoid relying on that incidental effect, especially during an interruption between the first child `mkdir` and its parent fence.

Add `test_sv028_a_readable_inherited_inventory_is_established_before_archive_mutation`. P1 dies after MANIFEST rename and before its directory fence. P2 carries the pending names, validates the same immutable inventory, and must log its dependency establishment before any cleanup or child `mkdir`. Exercise a second interruption before that establishment returns and one immediately after it, with host loss and convergence. Before the establishment returns, P2 must not create descendants; afterwards, the inventory must survive. Do not claim an old-code corruption failure from this ordering control if the old A3 fence still prevents it.

### L2 — Validate Phase B against preserved stop authority, not a live STOPPED that was intentionally removed

Section 7.2, lines 282–288, says its validation applies in Phase B and recomputes every binding from “current STOPPED and witness.” B0 explicitly invokes it (line 459), but successful Phase A has removed live STOPPED. Implement a phase-specific binding input to the common strict validator:

- Phase A: use the live validated STOPPED and its witness, as specified.
- Phase B: use the validated carrier/witness and the independently preserved `session/STOPPED` entry. Verify that entry's size/hash and manifest membership, parse the saved stop, recompute its `stop_sha256`, stop identifier and acknowledgement identifier/pair binding, and require its witness/lineage bindings to agree with the carrier and witnessed head. The carrier's manifest digest binds the exact manifest bytes.

Never recreate live STOPPED merely to make a success path validate; never omit the stop binding when the live file is absent. Keep the already specified carrier-free RECOVERING route self-contained—it does not gain a new archive dependency. N1 must exercise normal Phase B with live STOPPED absent; include the preserved-stop/binding refusal among N9's bounded corruption/conflict controls. These fit the existing nodes.

### L3 — Make failure claims describe the actual completed prefix

The blanket statements at lines 365 and 445–446 and in STATUS are false for failures late in a transaction. For example, a seal-directory fsync error occurs **after** the seal rename; a carrier-directory fsync error can leave a readable carrier; a STOPPED-removal fence error occurs after the unlink. A source change detected by A4 can occur after the inventory and earlier copies were written.

Required distinction:

- A pure admission refusal changes nothing.
- A later source/refusal condition stops subsequent work and leaves the already created inventory/copies for diagnosis; it does not roll the store back or claim that no writes occurred.
- A persistence failure propagates, attempts the existing best-effort marker, and stops further transaction advancement. Prior completed renames/unlinks can remain visible. Helper cleanup and the marker attempt are permitted failure-path operations.
- A pre-seal E failure cannot subsequently publish the carrier or remove STOPPED. A late failure must be described by its actual stage, not that pre-seal assertion.
- Phase A never removes the live conversation. Later startup obeys the existing STOPPED/FSYNC_FAILED priorities; marker persistence is conditional on its successful creation, not guaranteed after arbitrary I/O failure.

Add `test_sv028_late_phase_a_io_failure_preserves_the_completed_prefix[seal-fence|carrier-fence|stop-retirement-fence]`. Inject EIO at each exact fence, assert the already completed prefix, propagation/marker attempt, no subsequent transaction action, and intact live conversation/evidence. Do not promise general recovery or power-loss semantics after fsync error.

Add `test_sv028_a_source_change_during_copy_keeps_the_published_inventory_and_prior_copies`: change an admitted source between admission and its copy read after at least one earlier copy completed. Assert the specific refusal, unchanged immutable inventory and earlier copy, no carrier/activation/live deletion, and a later retry refusing the now-mismatched source. This is distinct from N18's pure retry refusal, whose whole-root equality assertion remains appropriate.

### L4 — Run exact capacity admission on every lifecycle branch; state both peaks accurately

Section 8.2 explicitly calls P13 only in the partial post-boundary branch (line 431). The none/pre-boundary and sealed branches must also compute and check their full P12/P13 plans **before any cleanup, dependency fsync, allocation or authority publication**. In particular, N19's sealed `cap=U−1` refusals must pass by execution of that predicate, not by incidental shape rejection. Reusing a sealed set does not exempt measured usage from the cap.

Let `F = U − D + A_M + ΣA_C`. F is the peak during the post-cleanup allocation phase and the final logical usage. The whole-invocation peak is `max(U, F)` separately for files and bytes. Preserve the explicitly selected engineering rule allowing verified cleanup to reduce pre-existing over-cap usage, followed by allocations only when `F ≤ cap`; do not describe that as an invocation that never exceeded the cap. No new owner decision is needed for this clarification.

Extend the existing N15 cleanup/cap fixture with a small injected case where `U > cap`, admitted cleanup reduces it and `F ≤ cap`. Assert monotone reduction before allocations, accurate measured `max(U,F)`, and no allocation exceeding the admitted post-cleanup bound. Keep N19's equality and below-cap refusal companions. No additional pytest node is needed for this extension.

### L5 — Freeze the actual finite fixtures, not “as round 1” shorthand

The standalone rewrite omits N4a/N4b's finite definitions (lines 649–650), and abbreviates several other unchanged assertions. The implementation prompt/manifest must explicitly incorporate the immutable prior source:

`d47b5c19fc5a0cbdf7221c45d7b8361982734508:docs/planning-context/sv028/DESIGN.md`, lines 556–572, as the unchanged assertion/fixture baseline, overridden by correction 2 and this review. In particular, N4a/N4b are exactly the finite cases at prior lines 560–561, plus correction 2's unowned-scratch case. Do not inherit the old archive transaction order or filename exclusion from that baseline.

N4a retains the four non-neutral suffix shapes, readable/absent/oversize conversation, previous-base, missing/damaged witness, changed-record/tail, identity, state-blob, run-json, pending-GC, transaction and foreign-carrier refusals, and unimplemented reason/pair controls. N4b retains unsupported kind/depth/name/HANDOFF shapes, foreign preservation shape, both own-set names and damaged sealed set. Clarify diagnostic precedence: a missing inventoried source must produce N18's `preserved_source_missing`; added paths produce `preserved_domain_changed`. Avoid a blanket path-set mismatch test that makes the missing-source token unreachable.

Use the exact retained node list from current §14.4; no broader retained sweep is requested. Pre-fix collection must still use accepted APIs, and D1–D3 failures must occur at their stated behavior assertions rather than imports or fixture setup.

### L6 — Keep the namespace model honest through reversal as well as publication

The identity-keyed design and N16/N17 are the right correction. Implement ancestor lookup/reversal so a cached identity→path map cannot leave pending descendants addressed by an obsolete path after an unfenced ancestor rename is undone. Re-resolve/rebase as needed, and do not resurrect descendants of a removed, unfenced directory. This is harness correctness within the existing N6/N7/N16/N17 cases, not a new production feature or a claim to simulate every filesystem behavior. Verify that N16's omitted-leaf-fence mutation actually loses the reused entry under the **sealed** name before convergence.

### L7 — Calibrate the remaining prose

- Replace “this acknowledgement can never complete” after a source mismatch (line 321 and §15/STATUS) with “cannot complete while the fixed-inventory checks fail.” The design itself permits a later exact restoration of the original source bytes; it has no durable terminal-refusal marker. This does not authorize this package to perform such a restoration or silently choose a new snapshot.
- Keep marker durability explicitly best-effort in STATUS and §15 as well as the transaction section.
- Correct the source-map's A1–A9 reference to the actual A1–A8 steps plus the qualified inherited-inventory fence.
- Preserve the unproved aggregate RSS/read costs, non-quota capacity convention and existing numerical/policy nonclaims.

## Exact bounded launch delta and acceptance boundary

The reviewed design's arithmetic is correct: **53 new + 50 retained = 103 cases**, final command sizes `[14,1,1,9,10,1,17,35,1,14]`, plus four pre-fix commands.

The qualifications above add exactly **five cases**: L1's one inherited-inventory node; L3's three late-EIO parameters; and L3's one mid-copy source-change node. Put these in F7, giving **58 new + 50 retained = 108 cases in ten final commands**, sizes `[14,1,1,9,10,1,22,35,1,14]`, with the same four pre-fix commands. The N1/N9/N15 refinements and model obligations stay inside existing nodes. Freeze literal names/parameters before launch. Retain the existing serial runner and resource limits; these are small temporary-root controls, not justification for a broad run or larger limits. Resource estimates remain estimates.

The coordinator may archive this report and prepend its governing qualifications to STATUS/the implementation prompt without another design-only worker invocation. Implementation acceptance still requires an immutable review of the actual transaction, assertions, fault-model behavior, mutation outcomes and bounded receipts. This review establishes neither numeric replay guarantees nor actual power-loss guarantees, and authorizes no real-session deletion/resumption, providers, merge, deployment, new resolution reason or held policy choice.
