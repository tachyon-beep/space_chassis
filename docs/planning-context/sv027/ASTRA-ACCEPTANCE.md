# SV-027 independent Astra implementation review

**Decision: accept the bounded SV027 implementation. No blocking correction is required. R-D's closed-boundary rotation-placement gap is closed; no numerical segment or replay guarantee is accepted.**

Reviewed immutable head `4e738afc52be2693907ba3c654267e9fc88388f1`, tree `312c1af225553c670e5ca32f9c498e27feee069d`, runtime/test commit `89a26a7a6c25df0e5b552cca570ac197745991fc`, against accepted-design base `bcb3c75225b609b84fcc4e93de5b64e1d9e4f775`. The second commit changes only `sv027/RECEIPT.md` and `STATUS.md`. Review used static immutable Git objects and the supplied receipts. No tests, project imports, providers, workers, runtime edits or real-session operations were performed by this reviewer.

## Runtime and ordering

The functional diff is the reviewed change: five session call sites and two startup call sites now use `unit_end()`, and `threshold_boundary` is removed. No reference to the deleted method remains in `services/` or `tests/`. `unit_end` retains its existing guards and mutually exclusive checkpoint/rotation branches. The other service-file changes are comments/docstrings.

The writer implementation, checkpoint/G2 logic, collection, accounting, header claims, constants, schemas and existing tests are unchanged. In particular:

- `chassis_session.py:594–608` still returns before either branch when broken, a group is open or the queue is nonempty. It does not append a second rotation after `checkpoint()`.
- The unchanged checkpoint path (`:683–690`) resets the interval only after its frame, permits one non-collecting G2 follow-up, and rotates after the final checkpoint. The added fallback does not change that path.
- `_recover` invokes the unified boundary at the same point after closure, extra-record syncs, carrier/RECOVERING retirement and IDENTITY reservation. `_start_legacy` invokes it after import and acknowledgement consumption. Neither moves rotation into a frozen recovery transaction or between GC_INTENT and GC_DONE.
- `open_segment` continues to sync inherited bytes before rotating away and fence the new header's file and name before returning. Header accounting remains after successful rotation. Failed rotation follows the existing persistence boundary; it is not permission for a later request or tool effect.
- Each adopted generation is committed and reduced before its boundary. Rotation between generations changes no watermark, pending-note, foreign-adoption or mirror fact.

The comments now distinguish the rotation-placement rule from the still-unproved read slack. No source constant or oracle was revised to claim a numerical result.

## L1–L5 closure and assertions

**L1 — legacy counter:** `tests/test_chassis_rotation.py:195–212` uses an explicit nonempty A5 list, requires exactly H1, LEGACY_IMPORT, H3, and derives `(2, import frame + imported list bytes + H3 frame)` from the independent frame walk and known serialization. It checks the blob size and obtains the same counter on a default-limit restart with no extra header. The no-H3 discriminator precedes the counter assertion.

**L2 — non-full I/O:** `:380–409` allows the inherited append-open and requires it to follow the session/ledger fences. It requires an unchanged segment-name set and the exact no-header record suffix. Five observed `rotate_if_full` calls—startup, file edit and three adoptions—must each return False with no filesystem events. The windows are non-vacuous. STATUS correctly notes that this five-call assertion would fail on the old runtime; it is a post-change control, not a claimed pre-fix passing node.

**L3 — adoption failure:** `:506–564` records separate pre-run and adoption-entry sequence markers, actual pending IDs and watermark, and injects EIO only at the first adoption header's ledger-directory fence. It requires that cut to be reached. The exact suffix from adoption entry is the first pending generation's MSG_APPEND followed by one header, with no later generation append. The checkpoint baseline still contains the original pending list. There is no request, INVOKING, checkpoint or RUN_END after the pre-run marker; the client sends nothing; main/bootstrap markers remain absent. The lifecycle assertions preserve the real ordering: run_start/runtime_bound occur, while run_resumed/run_fresh/turn/run_end do not. FSYNC_FAILED leads to A1 at the next start. The first run is explicitly checked to have written no note merely by returning from main.

The test does **not** directly assert `second.chassis.session.state` after the EIO. That is not a blocking evidence gap for this diff. The baseline plus exact durable suffix establish persistent progress; static inspection supplies the live-state implication: unchanged `_commit` applies the reducer before returning (`chassis_session.py:250–262`), and unchanged note reduction removes the first pending entry and advances its watermark (`chassis_replay.py:487–497`) before `adopt_notes` calls `unit_end` (`chassis_session.py:539–547`). The failure is later, in rotation. No subsequent generation runs. This is a code-backed inference, not a direct post-failure memory assertion. The separate process-death composition (`tests/test_chassis_rotation.py:435–453`) directly checks exactly-once generations and final watermark/pending state over two restarts. No additional test or correction round is required for L3.

**L4 — actual G2 branch:** `:266–281` plants a bounded unreferenced blob and requires the exact sequence CHECKPOINT, GC_INTENT, GC_DONE, follow-up CHECKPOINT, one LEDGER_HEADER, with nothing afterward. The blob must be listed and deleted, so collection and its follow-up cannot be vacuous. The generation-crossing case (`:283–321`) counts from adoption entry and observes completed real writer operations. Its wrappers first call the unchanged real append/open methods and then log completion; they do not replace persistence or fabricate the expected sequence. This is a sound correction to observing a later ledger from which legitimate GC has already removed earlier generations. It preserves three distinct closures, exactly one header per closure, bounded checkpoint/GC-intent counts and no duplicate closure header. The header-evaluated-next case separately verifies that the newly charged header does not trigger a checkpoint in the same closure.

**L5 — calibration:** The final receipt correctly records the earlier SV024 correlation execution, the new B0 baseline, finite selected-node scope, and the source's 19,978-byte claim versus SV025's valid-domain 21,173-byte checkpoint witness. It does not claim universal unchanged traces or a proved maximal frame size.

The remaining fixtures cover all seven new closure sites, inherited-byte ordering, transaction retirement before rotation, group/queue refusal, EIO before creation and at the new-name fence, and simulated loss/recreation of an unfenced header name with the same sequence/chain. The injected segment size is explicit; the tests do not claim to construct a default-size 16 MiB segment or perform real host-power-loss experiments.

## Receipt and immutable-byte checks

I verified all five final source/test SHA-256 values in `results/SV-027-implementation-test-receipt.json` against the immutable head. The four pre-edit runtime hashes in `results/SV-027-discriminator-runtime-receipt.json` match the accepted-design base; that receipt records an empty runtime diff during discrimination. No existing test file differs from the base.

The execution receipt has 18 commands. Its final eight tool results report no error and contain dot counts **18, 19, 6, 11, 2, 8, 11, 1**, totaling **76 selected cases: 18 new and 58 retained**. The receipt records no runtime/test edits after that final series began, no permission denials or multi-command-message overlap, and worker exit 0. I inspected the outputs and assertions, not independently rerun them.

B0 passed on the old runtime. D1–D7 have the specified behavioral failures. The earlier D7 `segment_name(-1)` setup failure is explicitly excluded; its armed-state ordering was repaired before the meaningful discriminator. The first F1 failure was the GC-observation issue described above, not a runtime correction or weakening of collection. Only the new fixture changed before the final eight commands. These development failures are preserved separately from the final passing evidence.

The 58 retained cases cover the selected SV026 accounting/closure paths, GC startup and missing-prefix authority, previous-base recovery, acknowledgement retirement, notes/metadata, golden placement and one real-process recorder correlation using tiny segments. That correlation is local controlled-process evidence, not provider or deployment qualification.

## Scope of acceptance

SV027 closes the accepted R-D placement deferral on the isolated WIP: the reviewed startup, note, file-edit, adoption and drop boundaries now evaluate rotation through the existing unified boundary. It does not prove a segment-size maximum, MAX_SEGMENT_READ slack, unit/startup-core maxima, crash-loop growth, unknown partial-I/O cost, older previous-base span, `T_origin`, RSS, latency or any of the four §1.4.7 inequalities. SV025's exact counterexamples and SV026's accounting qualifications remain in force.

This acceptance changes no history, previous-file, acknowledgement/bootstrap or H/T/Q/pump policy and authorizes no real-session operation, provider call, merge or deployment. No remaining blocker was established within this bounded review.
