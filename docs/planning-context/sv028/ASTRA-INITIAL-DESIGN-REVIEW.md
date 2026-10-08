# SV-028 independent Astra design review

**Decision: changes needed. Request one design-only correction round before implementation.** The narrowly admitted W1 resolution is a viable engineering package, but the proposed activation transaction has an evidenced mixed-crash failure and its preservation/capacity contract is incomplete. These need a corrected transaction and test matrix, not launch qualifications alone.

Reviewed immutable head `1058c5475db656b10e0ec14bd47dae1cfc9c190b`, tree `b46d27fe4b0337553922676c9bc4607d05b608da`, against accepted SV027 base `5c2366cef7851b39d5363bdadcce3e1c0b25711c`. Only the SV028 design/status documents are proposed. This review used static immutable objects, canonical SV013/SV015v2 and accepted review evidence. No tests, project imports, providers, runtime edits, workers or real-session operations were performed.

## Supported scope and semantics

W1's valid stop witness, exact ledger/IDENTITY/checkpoint/run.json bindings, neutral suffix, verified state blobs and refusal of unprovable predecessor cases are a reasonable narrow admission envelope. A generic CLI resolution name remains insufficient authority. Keep W2, TC4, missing/ahead/damaged ledger, A6, newer integrity stops and conflicting carriers refused.

For this envelope, **E1 + S1 + R1 + N1 is supportable engineering**: use the accepted EXTERNAL_DELETE base-switch behavior with an exact operator-preserving cause/binding, retain the lineage and pending-note facts, reset the conversation/fold index, increment the proved epoch once, and reuse A12's resume order. Leaving recap bytes in place and adding no new model-visible notice avoid inventing a new duty-visible behavior. S1 means notes can make the conversation nonempty and therefore prevent a bootstrap callback; it does not promise to invoke that callback despite pending memory. An operator's explicit choice is still required for each real session; implementing/testing the resolution in temporary roots is a separate authorization.

No new H/T/Q/pump or owner-policy choice is needed to correct the engineering below. A notice with new ordering, dropping notes, clearing recap, selecting unproved predecessor facts or widening to TC4 would be separate design/source work and is not recommended in this tranche.

## Findings requiring correction

### SV028-01 — P1: fence the inherited activation before deleting its live source

**DESIGN.md:299–307,327–337,403–405.** B3 unlinks and fences conversation.json before B4 syncs readable own extras. A readable activation frame is not proof that its fsync returned.

Concrete trace:

1. Phase A completes. Start 1 writes the exact activation frame but dies before its fsync returns. The carrier, archive and live unreadable conversation remain.
2. Start 2 finds that full frame readable. B0 accepts it as the own prefix; B2 writes nothing further.
3. B3 unlinks conversation.json and successfully fsyncs session/. Start 2 dies before B4 syncs the activation's segment.
4. Honest host loss removes the unsynced activation bytes while preserving the fenced absence of conversation.json. The carrier survives.
5. The next verification sees a pre-activation prefix but an absent conversation; its own before-LP rule refuses. The promised convergence is lost even though the archive is intact.

**Required correction:** establish durability of the verified own prefix, including the activation frame's actual segment and necessary inherited-prefix/name dependencies, **before any B3 unlink**. A newly committed activation already has its returned sync; a readable inherited activation must be re-fenced. On sync failure, leave the live conversation untouched and take the existing persistence boundary. Retain receipt/carrier/intent retirement ordering after durable completion; do not merely move a number or relax the missing-file check.

**Discriminator:** the exact two-process trace above, with carried byte/name watermarks, a second death after the unlink's directory fence but before the former B4 point, then host loss and two restarts. Include a failed pre-unlink activation sync that proves no unlink. N5 must assert the revised order. Describe readable activation, re-established durability and completed activation separately: an earlier process's fsync never returning does not forbid a later process from syncing and completing that same frame.

### SV028-02 — P1: freeze a complete plan and specify carrier-free intent resumption

**DESIGN.md:244–250,285–298,326,332,366.** The proposed B1 replay includes own extras and then derives the core. That cannot be an unspecified recomputation from the mutated replay. In the failed-unknown variant, applying the readable possible_duplicate_spend changes `requests.last.outcome`; deriving again then omits that record. Applying a readable activation also changes the epoch. A plan reconstructed from that state can shrink, mismatch the already-written prefix or increment a second time.

**Required correction:** derive the complete expected receipt/optional spend/activation and the activation epoch from the original witnessed checkpoint state and neutral suffix, before applying any owned prefix. Keep that plan immutable. Validate the owned records against it; apply each once to a separate replay and append only the missing continuation. Keep physical header records distinct from logical core positions.

The carrier-free path also needs an exact algorithm. Accepted RECOVERING.witnessed currently contains only `ack_id`, `receipt` and `after_seq` (`chassis_startup.py:1515–1537`); it does not contain the witness, manifest hash, epoch or original evidence dictionary. After carrier retirement, the draft says to take BP from that context but does not say how the required facts are recovered and authenticated.

Choose and document one bounded method: for example, reconstruct the witness/evidence from the independently preserved STOPPED and MANIFEST, verify all bindings against the intent's exact receipt/evidence digest, and derive the same frozen plan; or carry a sufficient sealed, bounded preserving context in the intent. Do not guess missing facts or reclassify the absent file as fresh permission. Preserve full intent domain/checksum validation and fail closed on missing/corrupt/foreign transaction data.

Write explicit traces for receipt torn, optional spend torn/readable, activation torn/readable, a second interruption, and carrier absent with RECOVERING present. Explain where the ordinary torn-tail RECOVERY record sits relative to the preserving core and how the intent freezes that recovery prefix. N8's claim that an additional torn_incomplete record is emitted must agree with B0's permitted record list and B1's core comparison. Do not rely on “same SV023 rule” without this composition.

### SV028-03 — P2: make the preservation promise match an exact admitted inventory

**DESIGN.md:18,30,145,190–214,266–276,346–357.** The proposal promises every file is kept and independent copies of every file ordinary operation can replace, but uses a closed canonical-name inventory and asserts that excluded files cannot be rewritten. That assertion is false for corrupt/ and HANDOFF.md. `quarantine_tail` rewrites its deterministic destination (`chassis_persistence.py:1457–1481`); a pre-existing file at that destination with different bytes is not immutable. Ordinary write_note replaces the named handoff mirror. Leaving these paths in place is not independent preservation of their prior bytes.

**Required correction:** define the exact preservation domain and handle every admitted file in it. Prefer a bounded independent inventory of the admitted session-file namespace, with explicit treatment of corrupt entries, unknown names and temporary leftovers. Refuse unsupported path kinds/depth/names before any mutation rather than silently excluding them. Existing sealed preservation sets can remain separately immutable; do not recursively copy archives into archives. Distinguish pre-resolution evidence from scratch files created by this transaction.

Resolve the named HANDOFF.md explicitly: if it is inside the package's promise, pass/resolve its trusted home path and copy that one known artifact; if the contract is session-directory-only, state that limit and its source basis rather than claiming HANDOFF is never rewritten. This is not a request for an arbitrary whole-home backup or a new owner gate.

Tests must compare the full declared pre-resolution inventory to independent archived bytes, not merely a list generated by the same selective helper. Include an excluded-name candidate and a pre-existing corrupt destination, and demonstrate preservation across the later ordinary operation that can replace it. Snapshot original inode identities before live files are unlinked; an after-activation stat of the removed conversation cannot prove independence. Use the hardlink negative control against the real mutable-file trace.

Clarify retry semantics for published versus unfinished archives. The text says damaged preserved bytes are never repaired, while A2 unconditionally rewrites destinations on retry. Either reject a damaged sealed archive and keep it untouched, or explicitly describe a separately authorized reconstruction rule; do not have both promises. A simple policy is to populate/retry an unfinished set, then verify and re-fence a sealed set without silently replacing changed bytes.

### SV028-04 — P2: enforce physical retry capacity and actual serialization bounds

**DESIGN.md:109–110,216–222,238–247,269–277,482–486.** P12 excludes the current ack directory although that directory may contain arbitrarily many allowed, never-deleted copy temps. Repeated process deaths after writing a large temp and before rename leave a new file each retry. Each retry excludes those bytes, passes the same projected inventory check and writes another temp. The stated all-sets file/byte cap therefore does not bound actual usage. Even a normal rewrite temporarily holds both the existing target and its new temp.

**Required correction:** budget actual existing usage, including the current set, manifests and transaction-created leftovers, plus the maximum additional allocation needed by the next copy/publication step. Define consistent exact-cap behavior. Safe bounded cleanup/reuse of unambiguously owned unpublished scratch is permissible engineering; deleting pre-resolution evidence or another set is not. If leftovers exhaust capacity, refuse before another allocation and document that bounded outcome rather than promising unconditional retry convergence. Also reconcile “temps are never deleted” with `write_bytes_durable`'s existing OSError cleanup (`chassis_persistence.py:985–991`).

Preflight the **actual canonical serialized MANIFEST and carrier**, including their seals, before writing anything. Approximate 160-byte entries and a 1 MiB read limit do not constrain what Phase A writes. `suffix_types` has no declared count bound; an admitted neutral suffix can produce an ACKNOWLEDGED larger than its 64 KiB reader accepts. Use a bounded digest/count representation or an explicit pure refusal, and verify all epoch/sequence/domain limits needed by the frozen plan. Do not publish a carrier the consuming reader cannot read.

Discriminators: repeated crashes leaving own copy temps; an existing destination plus rewrite-temp peak; exact and over-limit serialized manifests/carriers; a long neutral suffix; and boundary-cap refusal with no mutation. These can remain compact injected-limit fixtures.

Remove the claimed one-file/64 MiB production peak. Admission calls `read_segments`, scans and constructs records/replays before or alongside inventory handling; aggregate ledger bytes and parsed objects may be retained. A per-file read bound is not a peak-RSS bound. State the actual operations and leave RSS unproved, or separately account for all simultaneous data structures without claiming a new guarantee here.

### SV028-05 — P2: make capability registration and the finite proof plan truthful

**DESIGN.md:366–370,399–411,429–433.** A separate preserving subgroup is reasonable; keeping an allegedly complete `IMPLEMENTED_RESOLUTIONS` set incomplete solely to satisfy its old equality test is not. `acknowledge`, `read_carrier` and intent-context validation need one coherent source of supported pairs, with mechanism-specific subsets. Widen the real complete registry/union and make a small reviewed update to the old capability pin. Preserve old refusal/transaction tests; do not preserve a false “only these pairs are implemented” assertion through a dispatch before the allowlist. N13 should verify the actual union, exact new pair and continued refusal of all unimplemented reasons, with new-pair admission tested separately from its refusal on a repaired store.

The matrix also needs these concrete corrections:

- **N1 state:** define the sequence normalization explicitly when comparing checkpoint state to `wire(state)`; the accepted helper uses `next_seq=1`. In the failed-unknown variant, allow and assert the specified requests.last outcome change to possible_duplicate_spend, with requests.next retained from C_n (send already advanced its attempt). Assert physical sequence/chain continuity separately. Separate exact protocol records from legitimate headers and later ordinary boundary checkpoint/rotation work.
- **N2 visibility:** the accepted resume helper adopts notes and adds an opening only if the list remains empty. The proposed pending-note fixture yields the note, **not “note then opening.”** Compare it to a same-state A12 control. Add a finite no-pending-note control if the package claims bootstrap/default-opening behavior; specify any resulting case-count change.
- **N6/N7 fault model:** AckOps records unfenced renames/unlinks and inherited segment byte watermarks, but it does not model loss of newly created archive directory names or copy-temp names (`test_chassis_acknowledgements.py:68–116`, `test_chassis_gc.py:155–175,199–206`). Extend the bounded test adapter to cover those new namespace dependencies, or narrow the claimed simulation. Carry both byte and name durability across the second process. At minimum include archive-directory creation loss and the SV028-01 mixed-activation trace. A call-count sweep alone is not a model of all advertised host-loss outcomes.
- **N6 before-LP:** state whether an assertion is made immediately after the initial cut or after convergence. Convergence can re-sync a readable activation and then legitimately unlink. Use returned fences in the current/carry-forward durability model, not an inference that the first process returned its LP.
- **N3/§9:** P10 excludes C_n and its exact previous-base recovery, not every older known checkpoint. A different known C_k may still inhabit conversation.prev.json. `_retained_prev` preserves that bound file (`chassis_session.py:621–625`), so the first post-activation checkpoint need not have prev=null and may permit ordinary collection. Keep the existing rule; remove the unconditional first/second-checkpoint prediction. Build the GC preservation fixture with a demonstrated collection candidate and assert the actual reference graph.

The proposed arithmetic itself is correct: 22 new + 47 retained = 69 cases in eight final commands, plus four baseline/discriminator commands. Those are proposed counts only. Re-freeze the finite matrix after these corrections; modest count changes for the missing controls should be explicit rather than hidden inside an old headline. Retain exact nodes, meaningful behavior failures and the existing resource caps. D1–D3 must collect on the old runtime without requiring new-module APIs at import/setup. D2 is a reason-specific refusal control, not proof of activation safety.

## Required next delivery

Return a corrected design/STATUS only, with:

1. A complete immutable plan and admission schema, including carrier-free recovery-context reconstruction and exact serialization bounds.
2. Revised B0–B5 ordering that fences activation before unlink, plus explicit mixed-restart/torn-prefix traces.
3. A precise preservation namespace, sealed-set retry policy and bounded scratch/capacity accounting.
4. A truthful supported-pair registry and narrowly identified retained-test pin changes.
5. Corrected expected states/visibility, a namespace-capable crash model, and a finite frozen node/command manifest.

No implementation is accepted or requested by this review. Once these engineering corrections are reviewed, the recommended W1 semantics can proceed without inventing new owner policy. Real-session acknowledgement, deletion/resumption, widening the reason set, numerical replay/read/segment guarantees and all held apparatus choices remain outside this package.
