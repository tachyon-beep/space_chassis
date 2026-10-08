# SV029 independent Astra design review

**Decision: accept the bounded test-only architecture, with the mandatory launch qualifications below.** No further design-only round is needed. This accepts a plan for producing evidence, not either numerical guarantee or an already-executed counterexample. Implementation and its immutable evidence still require independent review.

Reviewed immutable head `c2cb7ebae13ac02c524b974c880a9379bde006b9`, tree `9a8ae82433baba56907a98057855e5af429c801a`, against accepted base `7936b665c4653ff61ec227ddd3d1589da31f3abe`. The diff contains only `docs/planning-context/sv029/DESIGN.md` and `STATUS.md`. I read those objects, the relevant accepted runtime and test-helper objects, SV015v2 §§1.4.1, 1.4.4 and 1.4.7, and the supplied design receipt. I ran no tests, collection, project imports, providers or workers and changed no source, runtime, oracle or existing test.

## Why the proposed witnesses are viable

The canonical default claims are newest records ≤ `256 − 1 + 103 = 358` and previous bytes < `2 × (8,388,608 + 16,777,536) + 19,978 = 50,352,266`. Canonical previous replay starts after the `covers_seq` of the actual checkpoint named by `C_n.prev`; it does not permit substituting the immediately preceding checkpoint. The observer therefore needs both base attribution and a byte/record interval fixed before startup.

**N1: retained-base span.** `services/chassis_session.py:610–625` retains a known `.prev.json` when the current conversation bytes are unbound. An external edit before each round supplies exactly that condition. Eight admitted, distinct, ASCII 1 MiB direct messages cross the default byte threshold; their individual units remain below the canonical per-unit byte maximum. The automatic checkpoint can keep naming A on all seven rounds. `chassis_gc.py:94–126` retains the union of references after A's cover, so enabling collection does not remove those 56 message blobs merely because there are intervening checkpoints. The single small ledger segment also cannot be collected out from under A.

On final A14, `chassis_startup.py:2320` reconstructs the interval from A, verifies the intermediate newest conversation hash, and then replays the newest suffix. Earlier edit records replace the evolving message list, but their preceding message blobs have already been read. The 56 direct-message blob returns alone total `58,720,256` bytes, exceeding the strict bound by `8,367,990`. This lower bound is independent of checkpoint-frame counting, scanner reads and conversation-file reads. The seven edit blobs and frames only increase it. This is a reachable current-runtime shape, not a synthetic checkpoint state or raised-cap fixture.

**N2: span control.** Omitting the second external edit leaves C1's bound bytes in the current file. The next checkpoint can rotate them to `.prev.json` and name C1. Its A14 replay opens the second interval's eight message blobs, not the first interval's blobs already represented in the base file. This discriminates retention span from message size. Assert the actual C2.prev tuple and the observer's applied interval; a passing small total without those assertions would be insufficient.

**N3: interrupted checkpoint plus repeated edits.** The initial 256 inline messages reach the record threshold. Death before CK6 writes any checkpoint frame leaves B as the newest committed checkpoint, B's bytes available in `.prev.json`, the expanded conversation installed, and CK5 covering existing message records. That is an A10 setup, not an A15 setup. A10 adds one adoption record. Each subsequent different external file then takes A11, adds one edit record, and reaches a checkpoint whose installation is interrupted before CK2 changes files. Nothing commits a newer origin. There is no torn tail or quarantine-cap consumption in this schedule. The final unchanged start therefore replays 365 non-origin records from the newest checkpoint B, even though the bytes providing B happen to be in the file named `conversation.prev.json`. Logical checkpoint identity, not that filename, determines which numerical row is being tested.

**N4: no-edit control.** After the first A10 has durably bound the installed list, unchanged restarts are A9t and add no new adoption or edit. Repeated CK2 deaths keep the suffix at 257. This separates the effect of a genuinely changed external binding from restart count alone.

These traces support implementation; they do not substitute for actual assertions and bounded execution. In particular, source tracing does not prove the proposed timing or memory estimates.

## Mandatory launch qualifications

### L1 — Correct the per-start counter contract

Replace the blanket `since_records == N_j + 1` in DESIGN §5.4 with `N_j + delta_new_core` for these header-free fixtures. The exact expectations are:

| Fixture/start | Entry replay records, excluding B's own checkpoint | New core | Counter at checkpoint entry |
|---|---:|---:|---:|
| N3 and N4, first dying start | 256 | 1 adoption | 257 |
| N3, edited dying starts j = 2…109 | j + 255 | 1 edit | j + 256 |
| N3, final unchanged start 110 | 365 | 0 | 365 |
| N4, unchanged dying starts 2…4 | 257 | 0 | 257 |
| N4, final unchanged start 5 | 257 | 0 | 257 |

The successful final checkpoint resets the counter to zero. Capture checkpoint-entry values before installation, not after the committed checkpoint. Fix the pre-start endpoint before invoking startup so its new core and final checkpoint cannot contaminate `N_j`. Count B's own frame separately: physical applies for the original entry suffix include it, while the conservative contradiction already holds without it. Assert exact classifications, core types and counts, absence of unexpected headers/groups, and no checkpoint frame between B and the final successful checkpoint. A declared death hook must fire once at its intended operation.

### L2 — Preserve independent measurement and exact interval attribution

Keep the existing helpers unchanged. Use the same observer returned by `watch()` as the `ops` passed to each measured start: `watch()` constructs its own Observer and does not register an independently constructed subclass. The initial checkpoint-write-death wrapper can build the prefix without being the measured startup observer.

`interval_work` uses a set of applied sequences and a dictionary keyed by `(seq, blob)`; by itself it can conceal duplicate applications or reads. Retain the design's explicit once-only, ordered application assertion and enforce the read multiplicity independently. For N1 final recovery, the 56 distinct message blob reads plus seven distinct edit blob reads must account for all 63 interval blob calls, with raw returned-byte sum equal to the reported logical sum. Verify each large message's actual UTF-8 length, admissible escaped length, distinct hash and reference, not just a nominal allocation size.

Measure the full previous interval from `A.covers_seq`, including intervening checkpoint frames. For N3/N4, assert that `.prev.json` still has B's exact bytes and that no applied sequence is at or below B's cover at every measured start. Reconstruct expected frame lengths independently from bytes. Runtime counters and classifications remain comparisons and path evidence, never the numerical oracle. Keep excluded conversation/scanner/planning reads explicitly separate from the replay quantity.

### L3 — Close fixture lifetimes and discriminate real cut behavior

`establish(root)` returns an open Session (`tests/test_chassis_recovery_live.py:117–125`). Close it before opening another writer. Close each normal session and every abandoned descriptor after simulated `Crash`, including failed-start writers for which no Opening was returned. The 110-start schedule must not accumulate writers or patch state.

The prefix fault must match the actual CHECKPOINT frame type and raise before its write; prove the frame is absent and that CK4/CK5 have the expected state. The subsequent fault is at entry to `cp.install_conversation`, before any install work, with B and the existing metadata unchanged. Distinguish that local injected cut from the retained `[ck2-temp-A9]` test's different, later CK2 cut. No test may obtain its result through setup failure, a missing API, an altered threshold, raw fabricated ledger frames or a raised cap.

### L4 — Correct resource accounting without relaxing limits

DESIGN §8 omits repeated previous-base reconstruction while building N1. Later A11 starts replay 8, 16, 24, 32, 40 and 48 MiB of prior message blobs: **168 MiB extra**. Together with 56 MiB of live blob returns and 56 MiB at the final A14, the schedule performs **280 MiB of message-blob return work**, before small edit blobs, base reads and scans. This is cumulative work, not peak live memory and not the final recovery measurement.

The N2 disk estimate of approximately 35 MiB also misses a checkpoint-install overlap: before CK2 finishes, 16 MiB of blobs, the old 8 MiB current conversation and the new 16 MiB temporary conversation coexist, approximately 40 MiB plus metadata. Recalculate estimates from actual fixture phases and label RSS/wall figures as estimates. Do not describe estimates as guarantees.

The proposed two final commands can remain: four new exact nodes, then eight retained exact nodes. Retain 120 CPU seconds / 180 wall seconds / 512 MiB address-space per invocation and the aggregate 50% CPU / 2 GiB / 64 tasks / nice 15 constraints. A cap hit stops dependent execution for review; it does not authorize a cap increase or an automatic retry. No broad scan, suite or provider operation is added.

### L5 — Freeze explicit targets; remove collection-only work

The four new names in DESIGN §7 and its eight retained nodes are sufficient for this test-only package: **12 cases in two final explicit-node commands**, with no case-count change from these qualifications. The retained function names exist in the immutable source. The two parameter IDs are statically supported by the exact `(cut, expected)` tuples at `tests/test_chassis_recovery_live.py:623–635`: `[ck6-before-write-A10]` and `[ck2-temp-A9]`. Remove the proposed `--collect-only` command. No wildcard or whole-file selection is needed.

No pre-fix runtime run or mutation is required because the runtime remains unchanged. N2 and N4 are the bounded mechanism controls. Implementation review must inspect their actual assertions and the final new tests, not infer discrimination from their names or pass totals.

### L6 — Calibrate claims and follow-up obligations

Fix DESIGN line 3 to say no **existing-test** change: this package does create a new test module. Keep STATUS and receipts conditional until the corresponding numerical assertions execute successfully. Distinguish final recovery work from lifetime/build work and simulated process interruption from actual subprocess restart or host-loss durability.

If the cases pass as specified, they add default-current-runtime counterexamples for the two exact remaining inequalities. They do not establish a replacement bound, global per-unit maxima, total startup I/O, or the truth of any bound under PR-N. The small no-edit control is not a proof for every single-interruption history. State any proposed PR-N formula as an unproved research obligation, not a repaired canonical guarantee. “No default cap bounds the growth” should mean no relevant admission/quarantine/threshold cap stops this finite 108-edit schedule, not a claim of mathematical infinity in a finite sequence domain.

DESIGN §10 is too categorical in saying numerical closure is not an engineering task. Further measurement, reachable-shape proof and analysis remain engineering work within their authorized scope. Changing a canonical bound, adding a schedule premise, changing retention semantics or changing threshold scope requires explicit contract/design closure; this package selects none of those alternatives. No new owner gate is needed merely to implement these four evidence cases.

## Acceptance boundary

The architecture has no remaining material validity blocker identified by this static review. The coordinator can archive this report, make L1–L6 governing launch instructions and freeze the literal 12-case manifest without another design invocation. Opus may then implement the new test module and evidence documentation under the existing limits. Final acceptance requires an immutable implementation review and the bounded results.

All SV025–SV028 numerical, read-slack, partial-I/O, resource and policy nonclaims remain. This review authorizes no runtime/oracle/source-policy correction, real-session mutation, provider use, merge, deployment, or held H/T/Q/pump decision.
