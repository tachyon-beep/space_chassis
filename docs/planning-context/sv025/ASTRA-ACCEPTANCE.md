# SV025 correction 1 — independent Astra review

**Accept the bounded test/evidence package.** SV025-01 and SV025-02 are closed at the corrected, explicitly separated evidence levels. The read-observer and recovery-cut wording corrections are also complete. No remaining blocker was established in this immutable correction review.

This acceptance does **not** establish any of the four canonical numerical recovery guarantees, a maximal reachable turn/checkpoint, or authority to change runtime behavior, limits, canonical sources or oracles. Earlier persistence acceptance and remaining project holds are unchanged.

## Reviewed checkpoint and method

- Head: `2ce8bad76c23a86d0962df90525c0c1509bbd126`.
- Test commit: `082d5efa3f56bac2b27b85498bf9c049c3cbddbc`.
- Prior reviewed head: `43c1d615e24cc9b4eaa4d850b76df65f152b0d06`.
- Accepted runtime base: `944e9d3e21987093cb78ff150d74e4e55900ad57`.

Static immutable Git-object review of the test/document delta, relevant accepted serializer/admission/session paths, and `results/SV-025-correction-1-test-receipt.json`. No tests, project imports, providers or runtime edits were performed. The correction changes only the bounds test and its STATUS/RECEIPT. The service diff from the accepted runtime base is empty; test/service bytes agree between the test commit and reviewed head. The recovery maintenance file is unchanged from the prior reviewed head.

## Finding closure

### SV025-01: closed with the model/reachability boundary preserved

The test module and current receipt distinguish three different claims:

1. **Synthetic arithmetic:** the canonical generator's supplied payloads reproduce its frame lengths through the encoder. They are not asserted to be valid runtime states.
2. **Domain models:** current field shapes and legal-width values are measured, with additional state validation for CHECKPOINT. They are not claimed to have been reached through an execution history.
3. **Emitted records:** actual session methods write records whose lengths are independently walked on disk.

The replacement checkpoint model (`tests/test_chassis_bounds.py:209–258`) now constructs `SessionState` and uses its actual `to_wire` method. The test requires an exact `from_wire(...).to_wire(...)` round-trip. It checks contiguous pending generations and the next-generation relation, bounded item and aggregate original sizes, 80 distinct sorted live references, 17 mirror references, pending write positions, and the previous/cover/frame/next-sequence ordering within the counter limit. The resulting measured domain model is **21,173 bytes**, replacing the invalid 21,746-byte construction.

Four negative controls (`:270–302`) show why the original encoder-only test was insufficient: the old generator-derived state, a generation-order violation, repeated live references, and an oversized original all encode but fail `SessionState.from_wire`. These controls exercise the missing distinction rather than merely restating the frame-size expectation.

This establishes serializer/state-domain evidence, **not global history reachability**. Hashes and high counters are modeled; no matching long history, full checkpoint install, or maximum reachable checkpoint was executed. Acceptance preserves the receipt's explicit qualification. A later proof must not promote 21,173 to an emitted maximum or assume that individually legal high counters prove a feasible whole history.

The other modeled rows are now labeled at the same domain level. Their source relations are made more precise: accepted lineage grammar and generated request labels; recovery's next attempt following the labeled attempt; an invokable UNRUN index of 15 under default caps; and the note-adoption payload shape. They remain models rather than executed request/recovery/adoption witnesses.

The two stronger size witnesses (`:306–332`) use actual session paths:

- A direct 4,096-byte control-character message is admitted, remains inline, and produces a **24,726-byte** frame. Its text and absence of a blob field are checked.
- A registered fixture tool raises an exception with a 1,000-character class name. The fixture passes through the actual `Chassis.invoke_outcome`, the INVOKING gate and `Session.record_result`. The emitted DONE is **1,313 bytes**, with `stored_E == original_bytes == 1,013 <= 32,768`. This removes the invalid inherited `stored_E = BIG` premise. It is a session-method fixture, not a provider or CLI run.

Neither emitted size is called a maximum. The invalid old values are expressly withdrawn in current RECEIPT/STATUS.

### SV025-02: closed

The pure default-cap adoption fixture (`:336–348`) uses 32 distinct malformed argument strings, each 603 bytes. Actual `adopt_response` yields 16 `bad_args` calls followed by 16 `not_run_call_limit` calls. The asserted original fields are exactly arguments 0–15, plus content/reasoning only when each exceeds its cap. The at-cap comparison excludes those two originals. Distinctness and the per-item retention limit are also checked.

The fixture and source branching support **at most 18 newly offered originals per response at default caps**. They do not establish a FIFO eviction count, and the corrected receipt no longer claims one. The 34-original construction and its count-eviction conclusion are withdrawn.

The aggregate `U_r = 103` and `U_b(turn) = 3,333,164` are now explicitly **unproved, not refuted**. The receipt recognizes that conservative component sums and mutually exclusive outcomes prevent inferring an aggregate violation from a changed component alone. No replacement complete-turn counterexample is claimed or required for this evidence package.

## Retained evidence and wording

The observer, positive threshold control, injected restart-accounting fixture and two default-constant counterexample bodies are unchanged. Their core assertions remain sound under the correction:

| Claim | Accepted evidence level |
|---|---|
| Newest-suffix bytes below 25,166,144 | Executed default-constant counterexample: the A11 EXTERNAL_EDIT blob is 28,311,552 bytes and replay opens it once, separately from the excluded conversation-file read. The A9t restart also uses the older base; only the measured newest suffix is attributed to this comparison. |
| Previous-base records at most 717 | Executed default-constant counterexample: the true retained A tuple persists across later checkpoints, and A14 applies exactly 730 records, with the expected intermediate hash/restored file and preserved previous file. |
| Restart byte accounting | Structural counterexample at injected threshold 20,000; not a third executed default inequality refutation or an actual subprocess/host-loss experiment. |
| Newest records and previous bytes | Unproved; no executed counterexamples for these two exact inequalities. |

The observer is correctly described as recording **successful returned reads**; failed attempts are excluded. Logical interval work, distinct blob bytes and repeated read calls remain distinct quantities.

The recovery-cut record is now described as **written and readable**, with no claim that its interrupted fsync completed. The prior semantic-cut placement and restart assertions remain unchanged. The preserved first-round STATUS section is explicitly historical and superseded where it conflicts with the correction, so it is not the current acceptance claim.

## Execution evidence and limits

The correction receipt reports **16/16 bounds cases in one bounded command**, exit 0, with no denials or retries. The unchanged maintenance function retains its earlier **8-pass** evidence and was not rerun. These are not 24 fresh executions. The committed file hashes match the receipt:

```text
tests/test_chassis_bounds.py
9b9509c6c00d2d95224d9c1ab95287bbc3a26bd6dadc87740b607cde64a462b8

tests/test_chassis_recovery_live.py
d24cf01dbb2c620053dc74929af6dda85f5d57760ab382202ff2d6a704b0769c
```

Counts support checkpoint provenance; acceptance rests on the inspected assertions, source relationships and calibrated claims. No broad tests or additional execution were needed for this static review.

## Follow-up boundary

The original review's engineering/design distinction remains in force. Reconstructing the specified replay-work accounting and honoring existing thresholds at defined closed unit boundaries are source-specified engineering obligations, subject to a separately reviewed concrete plan and preservation of recovery, acknowledgement and GC ordering. This report neither designs that implementation nor treats the proposed SV026 preflight as authorization.

Revised canonical numerical guarantees, changed accepted-history limits or representations, and a bounded previous-base strategy still require explicit contract/design closure and a proof that includes crash windows. No source/oracle mutation, runtime change, real-session operation, merge/deployment, or H/T/Q/pump choice follows from SV025 evidence acceptance.
