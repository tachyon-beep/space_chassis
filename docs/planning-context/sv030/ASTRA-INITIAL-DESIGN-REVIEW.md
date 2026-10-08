# SV030 independent Astra design review

**Decision: changes needed in a bounded design-only revision before implementation.** The default-size source construction is persuasive, and early rotation is a plausible narrow repair direction. The proposed admission rule, header-budget state and claimed closure are not yet precise enough to launch runtime work. These are engineering corrections within the approved task; no new owner-policy decision is needed.

Reviewed immutable head `cd72f00a9604c00eb5f16f07c9696024d76160d1`, tree `2f7477467ff5fb9761cd303b215a79578c40e88f`, against accepted base `b946fb4a73b3f58295e89a919b725e3aa3fbaafc`. The diff contains SV030 DESIGN/STATUS and the disclosed SV029 STATUS typo correction; no runtime/test change. Review used immutable runtime/test objects, the design, prior accepted boundaries and the specific-read approval receipt. No tests, collection, project imports, providers or workers were run. This report is the only output.

The recorded approval permits the exact canonical document read and resumption, not a directory expansion or retry of the denied parent search. The corrected STATUS preserves the original deviation. That process record supplies no additional runtime or execution authority.

## Sound parts of the proposal

The exact frame calculation in DESIGN §2 matches the encoder and this A11 payload: canonical JSON contributes the stated fixed skeleton, the notice contains a three-byte en dash, and the frame adds 115 bytes. Thus `432 + d(epoch) + d(recap_folded) + d(first) + d(last)` is the relevant recurrence for the unrotated family. The conservative 436–480 range and ceiling arithmetic, including 76,960 as an upper bound on edited starts from a nonnegative initial size, are sound. The more specific five-digit argument is consistent with that finite count. S4 must still bind the formula to the actual encoder, while labeling its extreme-width payload as arithmetic/domain evidence rather than a reached live history.

The source construction extends the interrupted portion of accepted SV029 N3, omitting its successful final checkpoint. Each new edit changes the binding; the existing checkpoint remains B; one edit frame is appended before the CK2-entry interruption; no new checkpoint, collection, tail or quarantine is required. Until the first size crossing, the source exposes no smaller admission limit stopping this finite family. Environmental storage and execution time are assumptions, not guarantees. The construction is source evidence, not an executed 32 MiB witness.

The reader consequence is real: `DurableOps.read` reads at most limit+1 and raises `ReadTooLarge`; startup maps that to `ledger_unreadable` before replay. `read_segments(..., limit=X)` is a valid API (`chassis_persistence.py:1133`), so S3's explicit read limit is not an API defect. `scan_segments` additionally needs the lineage argument. The implemented resolution registry does not resolve this stop.

Rejecting R1 as a complete repair is justified: an interruption before rotation opens its successor still follows the edit append. Correct its example, however: after that append the writer's inherited flag is false, so `sync_inherited` normally does not perform the suggested failing fsync. Use a cut immediately before the successor open. No cap increase is justified by this recurrence.

## Required corrections

### SV030-01 — High: define the clean eligible frontier and narrow the closure claim

**Location:** DESIGN §5.3–5.4, especially lines 192–200, the RECOVERING row at 230, and the claim at 238; corresponding Outcome/STATUS wording.

`replay.group is None` is insufficient evidence that the inherited prefix is a completed unit. A recorded REQUEST_SENT with no response leaves `group` unset (`chassis_replay.py:398–405`), while `derive_core` still owes `possible_duplicate_spend` (`chassis_startup.py:2672–2688`). The proposed guard rotates before that closure even though canonical §1.4.1 defines the turn from REQUEST_SENT onward. The design must not equate “no tool group” with “every recovery/turn boundary has completed.”

The stronger claim that all suppressed transaction cases have bounded growth is also unsupported. There is a concrete counter-family for an ordinary, non-witnessed RECOVERING intent:

1. Publish an ordinary recovery intent for one torn tail, preserve the tail and append the intended recovery core.
2. A changed conversation classifies A11. `_finish_case` appends its EXTERNAL_EDIT before the intent is removed.
3. Interrupt immediately before intent retirement, leaving that same intent. Change the conversation again and restart.
4. The extra-record loop checks the fixed core prefix but permits records beyond it when `receipt is None` (`startup:2114–2127`). Replayed earlier edits do not make the new file equal their binding. A11's branch appends another edit before the later `decision.carried` shortcut (`:2349–2380`). Interrupt again before retirement.

That repeats with one original torn tail, not one new quarantine entry per start. Therefore the 64-file quarantine cap does not prove the stated exception bounded. R2 is suppressed throughout this family. This finding does **not** require solving it now or reopening accepted intent semantics; it requires an honest narrower claim.

**Finite correction:** specify eligibility for the proven clean-start recurrence, with an actual completed frontier and no unresolved core/transaction. Give the exact cases and predicates, and show why the accepted A11 family remains eligible. Prefer dropping the new pending-GC branch from this package rather than implementing an untested sibling mechanism merely to retain a broad claim. Explicitly leave ordinary RECOVERING+A11 growth, other suppressed cases and global writer/reader compatibility unresolved. There is no need to select a new loss policy or general recovery algorithm.

### SV030-02 — High: close header reuse, one-shot lifetime and placement before coding

**Location:** DESIGN §5.3's `rotation_spent` sketch and §5.4 P1/P3/P4; §7's proposal to settle P1/P3 during implementation.

P1 is answerable from the current source: a newest empty segment produces an empty tail with its own segment number and offset zero (`persistence:474–483`). `continue_after` consequently calls `open_segment(reuse_empty=True)` and returns a writer that has already created and fenced a header (`:1207–1235`). Session construction immediately drains that writer's `opened_headers` into its counters (`session:180–182,264–274`).

The proposed early check does not account for this path. With the explicitly retained `segment_max=1` model, the reused header is already “full”; the new `_rotate()` can create another successor, then set the flag and suppress only the final rotation. Thus the proposed “one startup transaction still writes at most one header” contract fails. This is a design-contract counterexample, not a claim that the old code already guaranteed one header across every reuse-plus-closure composition.

**Finite correction:** define what the budget covers, including a header created by `continue_after`, and state exactly when the startup-local suppression is initialized, spent and cleared. Account for the fact that Session construction consumes the pending-header list. A non-full ordinary start must not gain an extra `rotate_if_full` call, and the suppression must not leak into the next live unit. Distinguish new headers written in this startup from inherited readable headers. Explain the checkpoint/GC-follow-up path without adding a second generic rotation policy.

Resolve P3 in the revised design as well. A neutral header does not itself authorize a request or reuse an identity, so early placement is not inherently an owner-policy change. But the proof must identify which IDENTITY validations already ran, which reservation remains pending, why excluded frontiers cannot bypass their closure, and why every request/effect still waits for reservation. Preserve `sync_inherited`, file/name fences and persistence-error handling before any dependent core append.

Specify whether early rotation occurs before or after the selected replay's counters are added, and why its header is charged exactly once. The old `now` scan and `decision.suffix` do not include that newly written header: explain why they remain valid for identity extraction and frozen edit-notice construction, rather than silently recomputing a different plan or feeding a physical header into logical core comparison. These are finite placement questions, not reasons for a broader audit.

### SV030-03 — Medium: revise the finite test plan to exercise the changed ordering

**Location:** DESIGN §6 and §7. The original four new/eight retained plan does not exercise the new empty-successor interaction or a failure before an A11 edit could be appended; its clean A9 failure control has no such edit to block. Nor does it cover the proposed new GC path. Do not preserve the original count at the expense of those assertions.

Keep S1–S4's useful purposes, with these concrete corrections and bounded additions:

- **S1 outcome helper:** it must inspect an ordinary returned Opening for `ledger_unreadable` before demanding that the install-entry crash fired. Reusing SV029's unconditional `pytest.raises(Crash)` helper would fail as “DID NOT RAISE,” not at the required reader-refusal assertion. Capture the first refusal and the pre-start walked sizes; other setup failures invalidate the discriminator. The prefix needs its specified header-aware message count, not SV029's hard-coded 256-message helper.
- **Observer interface:** define how the injected read limit and `watch()` share one registered observer. `watch()` constructs an Observer; it does not automatically register an arbitrary subclass. S3 must really observe zero applications on refusal, while retaining the real bounded read and actual unchanged-file assertions. Explicit `read_segments(limit=X)` is supported; use the real `encode_frame(seq, type_name, payload, prev_chain)` and scan signatures.
- **Empty-successor control:** create the real early-rotation cut after successor creation and before header bytes, then restart with the injected size that exposes duplicate headers. Require the exact header count/chain/charge, successful continuation, and clearing of the startup suppression before a subsequent live unit. Do not manufacture a header as the recovery result.
- **Pre-append durability controls:** use an eligible full-segment A11 start. Repeat a death immediately before successor open at least twice and prove that neither edit appends to the old segment; then converge. Separately inject inherited-file-sync failure and require no edit/core/effect afterward, the existing persistence boundary, and A1 if the marker was successfully written. Existing inherited-A9 coverage alone cannot establish this ordering.
- **Excluded-frontier controls:** the revised explicit-node plan must demonstrate its newly chosen guard on an unanswered request and pending collection. Retain the real intent-suppression control. Identify existing suitable carrier/preserving/open-group controls or supply a finite parameter list where needed; do not claim exclusions solely from a comment. If the GC rotation branch is removed, test unchanged suppression/ordinary completion rather than solving the GC sibling recurrence.

The revised design must freeze actual names, parameter cases, count and serial command grouping. No large default crash loop, broad suite, collection-only command or resource increase is needed. State pre-change behavior failures at their intended assertions; helpers/new APIs must not cause preliminary collection or setup failures. Bounds, time and memory remain those already approved.

## Bounded path forward

One design-only correction should be sufficient: retain the recurrence and injected reader discriminator; narrow R2 to the proven clean-start family; resolve P1/P3 and the header-budget lifecycle; remove the unsupported transaction-growth assertion; defer the GC addition; and update the finite evidence plan. Then return an immutable design for independent review before runtime or test launch.

The canonical rotation boundary and ordering constraints support engineering such a narrow repair. This review does not select a read-cap increase, a write-side refusal, a history restriction or new stop resolution. Unit maxima, single-closure overshoot, all-segment readability, ordinary-intent growth, numerical replay guarantees, partial-I/O costs, resource measurements and real host durability remain open. Prior SV024–SV029 acceptances and all real-session/provider/deployment/H/T/Q/pump/history holds stand.
