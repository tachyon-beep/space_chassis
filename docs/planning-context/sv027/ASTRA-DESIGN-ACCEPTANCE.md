# SV-027 independent Astra design review

**Decision: architecture accepted for bounded implementation, subject to the mandatory launch qualifications below. No separate design-only revision round is necessary. The uncorrected fixture table must not be used as the implementation oracle.**

Reviewed immutable design head `0f113aed48d740c553322e5fdbf09ddb0fecd7af`, tree `2f4db3501dcd1659f5146c0c523759f745ec846a`, against accepted SV026 base `e6016fc1cd5fa3d68c54f40c9c21834210231660`. Only `docs/planning-context/sv027/{DESIGN,STATUS}.md` changed. This review used static immutable Git objects, canonical SV015v2 clauses, SV026 acceptance and the relevant earlier receipts. No tests, imports, runtime changes, providers, workers or real-session operations were run.

The coordinator may archive this report and prepend these governing corrections to DESIGN/STATUS before issuing the separate implementation prompt. Final acceptance still requires review of the actual immutable implementation, assertions and bounded execution evidence.

## Architecture assessment

Replacing the seven `threshold_boundary()` calls with `unit_end()` and deleting the duplicate method is the smallest coherent change. Both existing methods have the same broken/group/queue guards and checkpoint branch; the only added behavior is the existing rotate-if-full fallback. Canonical §1.4.1 defines the relevant closed units, and §1.4.6 permits rotation at their boundaries. This implements the previously identified R-D engineering obligation without changing constants, admission or owner policy.

The retained ordering is sound:

- Startup rotation remains after the recovery core, `_finish_case`, required extra-record syncs, acknowledgement/RECOVERING retirement and durable IDENTITY coverage. A current frozen recovery transaction therefore cannot acquire an unplanned closure header. Pending GC completion remains ahead of any new closure rotation.
- `open_segment` retains inherited-byte sync, namespace fencing, header write, file sync and ledger-directory sync. The header is claimed only after those fences return. The new fallback does not publish a checkpoint or create deletion authority.
- `unit_end` chooses either `checkpoint()` or `_rotate()`. It does not rotate a second time after the checkpoint/G2 path. `checkpoint` continues to allow one non-collecting G2 follow-up and rotates only after its final checkpoint.
- Header work is charged after the current threshold decision and considered at a later closure. There is no immediate header-triggered checkpoint loop. At tiny injected segment limits, startup may close a header-only segment; the accepted bound is one rotation per closure, not a prohibition on all consecutive headers across distinct closures.
- The shared group/queue guards prevent the new fallback from rotating inside a group or before its queued messages are flushed. Per-generation rotation leaves the adopted watermark, pending/foreign facts and mirrors under their existing replay/checkpoint authority.

There is no architecture blocker and no new H/T/Q/pump choice. The following are concrete fixture and evidence corrections, not requests to change runtime behavior to fit the draft.

## Mandatory launch qualifications

### L1 — Correct the legacy import counter, including its blob read

**Priority P2; DESIGN.md:234 (R1 `legacy-import`), trace T3.**

For the proposed A5 list, the trace is H1, LEGACY_IMPORT2, H3 with no checkpoint. Only H1 is the origin. `_start_legacy` commits a blob-backed LEGACY_IMPORT (`chassis_startup.py:918–924`); `_on_legacy_import` calls `_switch_base`, which reads that blob (`chassis_replay.py:511–531`). Rotation does not reset the counter.

The expected counter is therefore:

`(2, frame_length(LEGACY_IMPORT2) + len(serialized imported list) + frame_length(H3))`.

The draft's `(1,h)` is wrong. Merely adding the import frame would still omit its replayed blob. Use a small explicit A5 list, no legacy handoff and no injected checkpoint threshold; assert the absence of a checkpoint, the import blob's expected bytes and the independent frame lengths. A default-limit restart can verify the same counter without another header. If T3 retains a later default OPENING record, qualify it as an empty-list case; a nonempty imported conversation does not need that opening.

### L2 — Scope the non-full I/O control to additional rotation work

**Priority P2; DESIGN.md:244 (R4).**

The draft forbids any `.svl` open during a restart observed by FaultOps. That already fails on the accepted base: `LedgerWriter.continue_after` opens the inherited active segment for append (`chassis_persistence.py:1233–1239`), after its startup namespace fences. No rotation is needed for that open.

Keep the default-size control, but assert an unchanged segment-name set, no new LEDGER_HEADER and no open of a new segment. Preserve the expected inherited-segment open and ordinary startup fences. For the stronger “no event at the new boundaries” assertion, record event windows around each closure or around the fallback itself, excluding the existing startup/record-write work. State the explicit expected record sequence and pre/post markers. Do not suppress `continue_after` to manufacture an empty event trace.

### L3 — Give the real Chassis adoption fault an exact baseline and cut window

**Priority P2; DESIGN.md:248 (R5 `generations-fence-eio-chassis`), T7 and D7.**

With `segment_max=1` injected into every writer, the corrected second run rotates at startup before `resume_session` reaches note adoption. A mark captured before `run.go()` thus includes a startup header, so its entire suffix cannot equal only `[MSG_APPEND, LEDGER_HEADER]`.

Capture two markers: a pre-run marker for the no-request/no-INVOKING assertion, and an adoption-entry marker for the exact `[MSG_APPEND{first pending generation}, LEDGER_HEADER]` failure suffix. Arm the EIO only in that adoption window, specifically at the new header's ledger-directory fence; require that the cut was reached. Record the pending generation IDs and adopted watermark before entry, and assert that only the first pending generation advanced while the rest remain pending. Do not infer IDs merely from “two notes were written.” This can be achieved with the existing APIs and temporary-root helpers.

The accepted runtime does **not** automatically write a pending note merely because main returns. `run()` records the `main_returned` reason, final checkpoint and RUN_END (`chassis.py:1203–1207,1242–1260`); `write_note` is reached through `handoff`, not that return path. The coordinator's possible extra-note concern was a hypothesis, not an established defect. Explicit baseline assertions settle the fixture without inventing a cleanup requirement.

Also preserve the actual lifecycle boundary: `run()` constructs the client and loads/binds the duty before `resume_session` (`chassis.py:1168–1199`). A failure inside `adopt_notes` may therefore follow `run_start` and `runtime_bound`; it occurs before bootstrap, duty main, any request or invoked tool, and before `run_resumed`. `Run.go()` should raise PersistenceFailure; the outer CLI handler maps it to 44. Assert that the second run reaches no main/bootstrap marker, request, tool invocation or terminal run-end path. Do not claim the duty was never loaded or the client never constructed. Distinguish the earlier successful run's lifecycle entries using a captured offset or run identity.

### L4 — Exercise G2 rather than leaving its branch optional

**Priority P2; DESIGN.md:239–240 (R2).**

Keep both threshold-crossing controls and the three-case R2 count, but make one crossing fixture demonstrably eligible for collection and force the GC pair to cross its injected threshold. A bounded unreferenced blob in a fixture with a valid retained checkpoint basis is sufficient; assert that it was actually selected. Require at least one exact local subsequence:

`unit record(s), CHECKPOINT, GC_INTENT, GC_DONE, CHECKPOINT, LEDGER_HEADER`.

The final header must be unique in that closure, with no second header or further checkpoint after it. Other generation closures can allow collection to be absent. Scope the three-generation header count and the no-consecutive-header assertion from adoption entry, excluding any distinct startup closure. Preserve the header-evaluated-next control and both CKG/queue controls. This tightens an existing fixture; it does not add a test file, a case or a broader suite.

### L5 — Correct provenance and restrict unchanged-test predictions

**Priority P3; DESIGN.md:201–209,278; STATUS.md frozen-proposal claims.**

G6 was executed in SV024. Its correction receipt and independent acceptance report record **161 selected executions / 159 distinct cases**, including one conditional recorder/chassis correlation case. It was not selected for SV026. Retain B0 as a useful baseline on the current accepted runtime, but replace “never executed in SV024 or SV026” with that accurate history.

The local proposition “the added fallback performs no I/O when the segment is not full” is supported. The universal proposition “every other test uses defaults, never reaches 16 MiB, and has an identical event trace” is not established by this finite review. Restrict the prediction to the explicitly selected nodes and their setup, injection and arming windows. For selected GC controls, retain semantic cuts and each test's own calibrated probe; do not rewrite a shifted cut or weaken an assertion merely to regain the expected count. Record any observed change in what a cut reaches. No broad scan or broad test rerun is required to replace the universal claim with a bounded one.

At DESIGN.md:306, call 19,978 the **source literal/claimed checkpoint frame size**, not an established current maximum. The retained SV025 test has a valid-domain 21,173-byte checkpoint witness (`tests/test_chassis_bounds.py:246–261`); it does not prove that witness's long-history reachability, but it already prevents using 19,978 as an unconditional supported bound. SV027 must preserve that distinction.

## Bounded launch and acceptance criteria

The proposed arithmetic is consistent: R1–R5 give `7+3+2+1+5=18` new cases; retained groups give `19+27+5+2+4+1=58`; post-change runs give **76 cases in eight commands**. L1–L5 can be incorporated without changing those counts. Expand the retained selections to exact node IDs from the accepted manifests before launch. B0 and D1–D7 are separate baseline/discriminator commands, not part of the final 76.

Discriminators must collect on the unchanged accepted runtime and fail at the named behavioral assertion or expected unreached cut, not an import, missing API, arity or malformed setup. In particular, D3 must first distinguish the absent H3; the corrected counter must then distinguish bad accounting in the fixed run. D7 must distinguish the absent adoption rotation from a startup or setup failure. No weakened retained test, raised resource cap or unreported selector substitution is authorized.

The explicit retained scope is proportionate: accounting/header reconstruction and all affected closures, pending-GC/previous-base recovery, acknowledgement retirement, note persistence, golden placement and one real-process recorder correlation. The writer implementation and G2 implementation remain unchanged; the new fixtures exercise their newly reachable composition points. Broader provider, filesystem-power-loss and numerical-bound claims do not follow from those selections.

## Remaining limits and next planning step

Acceptance of a future implementation can close R-D's boundary-placement gap only. It cannot prove MAX_SEGMENT_READ slack, maxima for a unit or startup core, repeated interrupted recovery growth, unknown partial-I/O cost, older previous-base span, `T_origin`, RSS, latency or any of the four §1.4.7 inequalities. The SV025 exact counterexamples and SV026 accounting qualifications remain in force. No constant, oracle, preservation rule, real-session authority or held apparatus policy is changed.

After SV027 acceptance, a useful next **design-only** package is the roadmap's narrowly admitted canonical `bootstrap-preserving` resolution where predecessor lineage, epoch, note state and identity are provable. Its deliverable should be an exact admission/refusal envelope and preservation/activation crash transaction: every pre-resolution file preserved as independent bytes, explicit epoch+1, durable manifest, idempotent activation and cleanup, and GC exclusion of preserved evidence. Cases with unprovable predecessor facts must remain refused and their missing semantics be identified rather than chosen. That recommendation does not authorize implementation or bootstrap on any real session; it supplies no alternative numerical-bound guarantee and makes no H/T/Q/pump decision.
