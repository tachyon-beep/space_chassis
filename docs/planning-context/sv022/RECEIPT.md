# SV-022 receipt — checkpoint-safe collection (K-F1 GC), post-collection recovery, recorder-in-loop correlation

2026-10-08, Australia/Sydney. Base: accepted `630623a4af30a8d08e90f5d9b0d2ef626af20f13` (runtime `f3812dc9d351a231a0f0879f86c9807f0a6a6634`). Interrupted-WIP checkpoint `efc6c03a9b205132f334c3b00eb95d3605e8a61c` (coordinator). Final runtime/test bytes match `efc6c03a9b205132f334c3b00eb95d3605e8a61c` after all mutations were restored and the resumed worker completed with exit 0. Awaiting independent review. Opus 5.5; the approved runner only, one explicit literal command at a time; temporary roots; the local stub upstream; the real recorder only as a local subprocess. No provider, deployment, real-session deletion, pump, H/T/Q, account or settings change. No real stop was acknowledged (`acknowledge()` ran only on temporary roots). The worker made no Git call.

## 1. Final runs (final tree, after every mutation was restored)

`python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <targets>`. Counts are the runner's progress dots; all passes, no failures, no skips.

| # | Targets | Result |
|---|---|---|
| F1 | `tests/test_chassis_gc.py` (new) | 44 passed |
| F2 | `tests/test_chassis_correlation.py` (new; real recorder + real chassis processes) | 2 passed |
| F3 | `tests/test_chassis_recovery_live.py` (incl. 5 real script restarts) | 97 passed |
| F4 | `tests/test_chassis_replay.py tests/test_chassis_session.py` | 61 passed |
| F5 | `tests/test_chassis_notes.py tests/test_chassis_checkpoint.py` | 23 passed |
| F6 | `tests/test_chassis_adoption.py` | 50 passed |
| F7 | accepted foundation: ledger, recovery, durability | 114 passed |
| F8 | `tests/test_chassis_termination.py` | 67 passed |
| F9 | groups, wire, supervisor flap, metadata | 65 passed |
| F10 | the 22 retained `test_chassis.py` + 7 `test_services.py` nodes (target JSON) | 29 passed |
| F11 | the 5 local-stub `test_run_end_to_end.py` nodes (target JSON) | 5 passed |

Total 557 selected passes. No full-suite run; no other test was run.

### Failures during development (all fixed before F1–F11)

- Fixture bugs of mine in `test_chassis_gc.py`: `resume()` called with a Session instead of an Opening; C-G1 read `NOTE_WRITTEN{1}` after collection had already (correctly) removed it; the protected-file snapshot was taken before CK2–CK5 legitimately rewrote run.json/conversation files (now taken when collection starts, after CK6); the backlog test counted CHECKPOINT records in a ledger collection shortens (now asserts the exact records each round appends).
- One retained assertion changed (§4).
- No runtime defect was found by the fixtures after the first full run.

### Interruption

The execution connection aborted after M3 was run; the coordinator checkpointed the preserved tree as unaccepted WIP `efc6c03`. On resumption the tree was inspected: no `MUTATION` marker; M1–M3 restored (per-segment fence, intent-before-unlink, blobs/ fence all present). M4 was then applied, run, restored. F1–F11 were run only after that, on the final tree.

## 2. Negative controls

**Source mutations** (each marked `# MUTATION`, run on the named node, restored; `grep MUTATION services/ tests/` is empty). Their failures are evidence, not passes.

| # | Mutation | Node | Observed failure |
|---|---|---|---|
| M1 | no `fsync(ledger/)` after each segment unlink | `…every_cut…[host-loss-alternate]`; `…ordered_and_fenced` | cut 4: two segment unlinks undecided at once (a gap becomes possible); next call after a segment unlink was another unlink, not the fence |
| M2 | unlink before `GC_INTENT` is appended | `…failed_intent_sync…[intent-fsync]`; `…every_cut…[process-death]` | unlinks happened although the intent's fsync failed; at a cut before the intent, segments were gone and the next start stopped `ledger_prefix_missing` |
| M3 | no `fsync(blobs/)` | `…every_cut…[host-loss-all]` | cut 20: GC_DONE durable while a listed blob reappeared (false completion) |
| M4 | restart writes GC_DONE without re-running the stored list | `…every_cut…[process-death]` | cut 1: one GC_DONE recorded while listed segments 1–5 survived |

**In-test controls** (monkeypatched, permanent nodes that pass by asserting the control *fails* the property):

| Control | Node | What it distinguishes |
|---|---|---|
| newest-state-only references | `test_reference_union_negative_control_newest_only…` | C_p.state's original and the interval DONE blob are removed; A14 then stops `replay_mismatch` |
| C_p = the CHECKPOINT before C_n (not `C_n.prev`) | `test_o2_2_negative_control_the_last_two_checkpoints…` | after A11, the true previous checkpoint is unlinked; A14 stops `conversation_unreadable_unbound` |
| restart deletes by a fresh unreferenced scan | `test_o2_4_negative_control_a_fresh_scan…` | leftovers outside the stored batch are removed |
| mirror/watermark facts derived from surviving records | `test_c_g1_negative_control_state_derived_from_surviving_records_readopts` | N1 comes back after collection (R11-3 shape) |

The preflight's literal "watermark only from surviving MSG_APPEND" mutation is not constructible as such: `adopted_through` with an empty pending list cannot be lowered without failing checkpoint validation. The mirror-fact control above is the reachable equivalent and is what was run.

## 3. Source → mechanism → fixtures

| Source | Mechanism | Fixtures |
|---|---|---|
| `services/chassis_gc.py` (new) | `retained_basis`: C_p exactly as `C_n.prev` names it (seq, covers, conv sha, bytes), states validated, whole interval present, refs = C_n.state ∪ C_p.state ∪ records > floor; refusal otherwise. `plan_collection`: closed segments below the first retained record's segment (a prefix, never a partly retained one), unreferenced 64-hex blob names; deterministic bounded batch (`GC_BATCH_MAX` 4096). `intent_problem`/`structure_problem`: keys, int segment numbers ≤ 999,999, 64-hex blobs, ascending/unique, 1…4096 items, encoded body ≤ MAX_LEDGER_BODY, immediately after its checkpoint, exact cover, no protected/active segment, no retained or later-referenced blob. `unlink_intent`: segments oldest first each fenced, blobs, `fsync(blobs/)`, `fsync(ledger/)`; ENOENT idempotent; other errors PersistenceFailure. `unauthorized_prefix`, `pending_intent` | all of `test_chassis_gc.py` |
| `services/chassis_session.py` | `collect` (default False), `gc_batch_max`; `_collect` after CK6, before rotation: blocked by RECOVERING/ACKNOWLEDGED/STOPPED/FSYNC_FAILED; plan from the ledger read back (must end at this checkpoint); validate; GC_INTENT → unlinks → GC_DONE; failure → `_fail` (marker once, broken); prunes `checkpoints` at/below the floor; never checkpoints | backlog, failed-gate/fence, live refusal, C-G1, O2-1, union, O2-2 |
| `services/chassis_startup.py` | `ledger_prefix_missing` stop; `_pending_collection` (must end P, revalidated, else `gc_intent_invalid`); GC_DONE first in the recovery core; stored list re-run before any startup blob write (skipped once GC_DONE is in `extra`); `known` checkpoints pruned at/below any intent's floor | O2-4 cut matrix, second interruption, invalid/torn/damaged intents, lost DONE, gaps, prefix |
| `services/chassis.py` | activation: `collect=True` passed by `run()` only | correlation fixtures, retained F3/F8/F10/F11 |
| `services/chassis_replay.py` | docstrings only (`retained_refs` now described as the SV-021 helper) | — |

**Preflight fixture table → nodes (`tests/test_chassis_gc.py` unless stated)**

| Preflight fixture | Nodes |
|---|---|
| C-G1 | `test_c_g1_an_adopted_note_is_never_readopted…` (+ control) |
| O2-1 | `test_o2_1_pending_generations_outlive_their_collected_records` (gens 2,3,4 = N2,N3,N2; records and segments absent; blobs kept; adopted once; third run none) |
| Reference union | `test_reference_union_keeps_each_kind_until_it_is_eligible_in_turn` (+ control); suffix blob via `retained_basis` on a crashed suffix |
| O2-2 after GC, and after A10/A14/A11 | `test_o2_2_previous_base_recovery_after_actual_collection`, `…following_a_corrected_transition[a10,a14,a11]` (A11 asserts `C_n.prev` older than the preceding CHECKPOINT), + last-two control |
| O2-4 | `test_o2_4_the_collection_unit_is_ordered_and_fenced`, `…every_cut…[process-death, host-loss-all, host-loss-alternate]`, `…second_interruption…[4 cuts]`, `…reruns_the_stored_list…` (+ fresh-scan control) |
| Directory-persistence cuts | the two host-loss cut-matrix nodes (subset-of-unlinks restored); `test_a_gap_among_listed_segments_is_refused_not_reinterpreted` |
| Failed gate/fence | `test_a_failed_intent_sync_unlink_or_fence…[5 targets]`, `test_a_failed_fence_whose_marker_also_fails…` |
| Intent validation/corruption | `test_the_plan_is_valid…`, `test_invalid_intents_are_refused_before_any_unlink` (20 mutations), `test_an_intent_over_the_body_cap_is_refused`, `test_the_live_owner_refuses_an_invalid_plan…`, `test_startup_refuses_an_invalid_pending_intent…[5]`, `test_a_torn_or_damaged_intent_is_never_deletion_authority`, `test_a_valid_intent_whose_done_was_damaged_is_finished_once` |
| Rotation and retained headers | `test_rotation_continues_from_a_nonzero_oldest_segment…`, `test_gaps_collection_did_not_make_still_stop`, `test_a_lineage_that_never_collected_does_not_accept_a_missing_segment_0` |
| Identity/state without records | `test_restored_state_and_identity_without_their_source_records` (REQUEST_SENT ×all, NOTE_WRITTEN, MSG_APPEND note, RECAP_FOLD, HISTORY_REPLACED absent; state/messages/label equal; acknowledged TC4 allocates `reserved+1` with no REQUEST_SENT left) |
| Bounded backlog | `test_a_backlog_is_collected_in_bounded_batches_without_recursion`, `test_the_planner_bounds_a_long_backlog_to_one_batch` |
| Recorder-in-loop pair | `tests/test_chassis_correlation.py` (§6) |

## 4. Changed retained assertion

`tests/test_chassis_session.py::test_sv021_07_editing_the_history_copy_inside_a_tool_changes_nothing` replayed the whole ledger from genesis after a real chassis run. With collection active, the HISTORY_REPLACED blob it read was (correctly) collected, so that replay failed. It now compares the live messages with startup's own replay (`open_session` → A9, newest checkpoint + suffix) and the file; its A14 previous-base check is unchanged. This is the preflight's "no genesis replay that only works because old files remained".

## 5. Crash matrix (in-process; `Crash` = process death; host loss simulated)

`test_o2_4_every_cut…` cuts before **every** armed filesystem call of the collection unit and the rotation after it, read from a probe run. By construction the fixture's unit is: `write`+`fsync` GC_INTENT; 5 × (`unlink` segment, `fsync(ledger/)`) for segments 1–5; `unlink` × the listed blobs (3 DONE blobs + 2 orphans); `fsync(blobs/)`; `fsync(ledger/)`; `write`+`fsync` GC_DONE; rotation `open`, header `write`, `fsync`, `fsync(ledger/)`. Each cut × {process death; host loss undoing all unfenced unlinks and unsynced bytes; host loss undoing alternate unlinks}, then two restarts. Every case asserts: at most one segment unlink undecided; removed ⊆ listed; IDENTITY, run.json, both conversation files and HANDOFF.md byte-identical to CK6's; with a surviving intent, exactly one GC_DONE and every listed item absent; without one, nothing removed; the second restart writes and removes nothing.

| Cut class | Outcome |
|---|---|
| before intent write | nothing removed, no intent |
| intent written, fsync not returned | process death: intent readable → finished at restart; host loss: intent lost → nothing removed |
| after intent sync, during/after each segment unlink or fence, during blob unlinks, after either final fence | restart re-runs the stored list; ENOENT tolerated; one GC_DONE |
| before GC_DONE write | restart writes GC_DONE first |
| GC_DONE written unsynced | process death: complete; host loss: re-run, one GC_DONE |
| rotation after GC_DONE | complete; an empty new segment is reused (O2-5 path) |
| second crash inside the finishing restart (first unlink, after first fence, blob unlink, before GC_DONE) + host loss | third start converges |
| EIO on intent fsync / segment unlink / ledger fence / blob unlink / blobs fence | no unlink after the failure, no GC_DONE, FSYNC_FAILED written once, no request; next start A1 with nothing changed; after `continue-from-bound` the readable intent is finished |
| fence fails and the marker fails | no marker, no stop: the next start finishes the intent (v2 1.4.9 limitation retained) |
| torn intent (TC1) / damaged full intent (TC2) | `torn_incomplete` / `damaged_final` + notice; nothing removed |
| valid intent, damaged GC_DONE (TC2) | quarantined; intent finished; one valid GC_DONE |
| simulated gap among listed segments (outside the fenced order) | A2 `ledger_damaged_at`; nothing removed — **refusal, not convergence** |
| missing middle segment / missing oldest segment not named by a retained intent / missing segment 0 in a never-collected lineage | A2 `ledger_damaged_at` / `ledger_prefix_missing` / `ledger_prefix_missing` |

## 6. Recorder in the loop (`tests/test_chassis_correlation.py`)

Real `services/recorder.py` (conftest `Stack`) over unix sockets to an in-process recording stub; real `services/chassis.py` processes (and the accepted test-only launcher pattern to set a 1-byte segment threshold). Dummy credentials; temporary `/tmp` roots.

- *Labels and an interrupted attempt*: request 1 reaches the stub, the process is SIGKILLed. REQUEST_SENT label = the recorder `open.client_label`. The restart runs to the duty's barrier with the stub still at 1 body and the recorder at 1 open event, `possible_duplicate_spend` already durable; released, it sends `lineage:turn:2`; ledger labels = open labels in order, two recorder ids; no `label_seen_before`; the label absent from every upstream body and every transcript `request`.
- *Identity after collection*: four turns with a tool each under 1-byte segments; segment 0 and the first REQUEST_SENT are gone, GC_DONE present. Restart behind a barrier contacts nothing; next label `lineage:5:1`, equal to the open label. Then an interrupted request (`lineage:6:1`), a restart that contacts nothing before its barrier, and `lineage:6:2`. Seven open labels, all distinct; IDENTITY ≥ 6; tool invoked 6 times (no replay); stripping holds.

The label is compared, never authenticated or used to deduplicate. This is local-stub evidence, not a deployed recorder.

## 7. Decisions and deviations (for review)

- **Intent schema extension**: `GC_INTENT` adds `checkpoint_seq` (the C_n it was planned under) to v2's `records_through, segments[], blobs[]`; segments are integers, never names. The foundation's `validate_payload` is unchanged; authority checks live in `chassis_gc`.
- **Stronger fence ordering** instead of a gap-tolerant reader: each segment unlink is fenced before the next. Claim: under M-2 a collection never leaves an internal gap; a gap that appears anyway is refused (A2), not repaired.
- **New startup stops**: `ledger_prefix_missing` (missing oldest segments not named by a retained intent — this also applies to lineages that never collected, which previously started from any oldest segment) and `gc_intent_invalid`. Neither is acknowledgeable; both are refused like the other unimplemented resolutions.
- **A readable intent whose fsync failed** is finished after the operator's `continue-from-bound` acknowledgement (it is valid, readable, revalidated deletion authority). Without acknowledgement the A1 stop holds.
- **One batch per checkpoint**; leftovers wait for later checkpoints. A collection re-reads and re-verifies the retained ledger at every checkpoint (O(retained segments) per checkpoint [CM]).
- **Frontier after collection**: `prefix_state` sees only retained records; a failed request whose REQUEST_SENT was collected no longer widens F(P). Only more conservative (TC4 instead of TC2) classification can follow.
- **Checkpoints at or below a floor** are never offered as a later `prev` (in-run map and startup `known` both pruned).
- SV-021 dependencies kept: IDENTITY and RECOVERING are outside the namespace and RECOVERING blocks collection; the latest file binding is in the retained suffix; `notes.pending[].foreign` lives in state with its blob in `blobs_live`; `conversation_adopted.detail.blob` and `LEGACY_IMPORT.note.blob` stay in `record_refs`; C_p is the exact `C_n.prev` tuple.

## 8. File manifest

Before (base `630623a`): no `services/chassis_gc.py`, `tests/test_chassis_gc.py`, `tests/test_chassis_correlation.py`, `docs/planning-context/sv022/`.

After: new `services/chassis_gc.py`, `tests/test_chassis_gc.py`, `tests/test_chassis_correlation.py`, `docs/planning-context/sv022/STATUS.md`, `RECEIPT.md`; modified `services/chassis_session.py`, `services/chassis_startup.py`, `services/chassis.py` (one kwarg + comment), `services/chassis_replay.py` (docstrings), `tests/test_chassis_session.py` (one assertion, §4). No other file changed by the worker.

## 9. Claims

**Established (subject to review), under the tested and modelled cuts:** explicitly eligible obsolete segments and blobs are collected by a durable, validated, bounded intent; nothing outside an intent is removed; a valid interrupted intent converges idempotently with exactly one GC_DONE, including a second interruption; a torn/damaged/invalid intent removes nothing; failed gates and fences stop at the existing persistence boundary; required state (pending generations, watermark/mirror, request identity, recap, history epoch, originals, file binding) survives physical deletion of its source records; previous-base recovery uses the true retained base after actual collection, including after A10/A14/A11; backlog is batched without recursion; recorder-in-loop label equality, stripping, attempt advancement and no-contact recovery against a local stub. Relevant canonical rows: C-G1, O2-1, O2-2 (post-collection), O2-4; C-G2's previous-base part.

**Not claimed:** bounded total session disk (the conversation is unbounded; corrupt/ is protected); v2 1.4.7's 358/717-record or byte bounds; power loss, kernel or storage behaviour (host loss is simulated, process death is real only in F2/F3 script runs); directory-entry loss of a newly created segment during the rotation after collection (not simulated); recovery of a gap among listed segments (refused); the remaining acknowledgement resolutions (still refused); provider compatibility, deployed recorder ordering, deployment, merge, pump/vehicle work; full K-F1 completion beyond these fixtures.

## 10. Correction 1 (Astra SV022-01, SV022-02)

§1–§9 describe runtime/tests `efc6c03`. Correction 1 adds, without changing any existing assertion: (SV022-01) a restart fsyncs the pending intent's own segment file before its first unlink — failure is a PersistenceFailure with no unlink; (SV022-02) an intent's segment list must cover a prefix of the surviving segments, checked before live publication and pending execution. Pre-fix evidence: six regression nodes failed on the reviewed runtime as the review traced (the mixed process-death → host-loss trace stopped `ledger_prefix_missing`). Final corrected tree: 563 selected passes across 11 bounded commands. Details, map and limits: `checkpoint-001-astra-corrections.md`.

Updates to §5 and §9: the crash matrix gains the mixed trace (intent written, fsync not returned, process death; restart unlinks one fenced segment; crash; host loss of every byte no fsync covered in either process) → converges with one GC_DONE, and a failed restart intent gate → zero unlinks, A1. The §9 convergence claim now includes that mixed sequence under the simulated model; a skipping/holey segment list is refused (`segment prefix`), not executed.
