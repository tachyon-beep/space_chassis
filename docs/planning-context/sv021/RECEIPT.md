# SV-021 receipt — integrated K-D1/K-D2 adoption (with K-E2 bounds, K-F1 identities, K-G2 replay)

> **Correction 1 (Astra SV021-01…07) supersedes parts of §3 and §4**: request identity after TC4 (now the durable IDENTITY reservation, not the length formula), previous-base retention and the A14 repair (now restores the newest checkpoint's bytes), the file-authority rule (latest binding transition), legacy-import notes, notice obligations and the history copy. See `checkpoint-001-astra-corrections.md` and §6 below. §1–§5 describe the reviewed commit `3b145c6`.

2026-10-08, Australia/Sydney. Base `437b52d765269dbfb127505e27d6b8dca4ed99e6`. Runtime/test checkpoint `3b145c6aea18a0fc537de9cd74fe1adc539039f6`, committed by the coordinator after the worker stopped (see STATUS.md). Awaiting independent review. Opus 5.5, the approved bounded runner only, temporary roots, the local stub model over unix sockets. No provider, deployment, pump, H/T/Q, account or settings change. No real stop was acknowledged: `acknowledge()`/`--acknowledge-stop` ran only on temporary test roots.

## 1. Runs (final tree, one command at a time)

`python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <targets>`. The runner prints progress dots only; counts below are the dots, all passes, no failures, no skips.

| # | Targets | Result |
|---|---|---|
| R1 | `tests/test_chassis_adoption.py` | 50 passed |
| R2 | `tests/test_chassis_replay.py tests/test_chassis_session.py` | 60 passed (31 + 29) |
| R3 | `tests/test_chassis_notes.py tests/test_chassis_checkpoint.py` | 17 passed (11 + 6) |
| R4 | `tests/test_chassis_recovery_live.py` | 58 passed (54 in-process simulations + 4 real script restarts) |
| R5 | `tests/test_chassis_ledger.py tests/test_chassis_recovery.py tests/test_chassis_durability.py` (accepted foundation) | 114 passed |
| R6 | `tests/test_chassis_termination.py` (retained; includes 14 script-mode subprocess runs) | 67 passed |
| R7 | `tests/test_chassis_groups.py tests/test_chassis_wire.py tests/test_supervisor_flap.py tests/test_chassis_metadata.py` (retained) | 65 passed |
| R8 | the 22 retained `tests/test_chassis.py` nodes + the 7 retained `tests/test_services.py` nodes (target JSON) | 29 passed |
| R9 | the 5 local-stub `tests/test_run_end_to_end.py` nodes (target JSON) | 5 passed |

Total 465 selected passes. No full-suite run; no other repository test was run. After R1–R9, only `chassis_persistence.py`'s module docstring changed (it still claimed production imported nothing from it); R5 was re-run afterwards: 114 passed. R1–R4 and R6–R9 predate that docstring-only edit.

### Earlier runs and failures (all fixed before R1-R9)

- Baseline before any change: `test_chassis_metadata.py` 7 passed.
- Session (C): `test_o1_7…` failed — a broken session refused `send` with an invariant error instead of PersistenceFailure (no effect ran); fixed by checking usability first. `test_retained_originals…` failed — test helper used default caps.
- Recovery (D): three test-harness errors (lineage in a helper, FaultOps fd registration, FaultOps lacking `unlink`), and one wrong expectation (a CHECKPOINT written but unsynced is readable after process death: A9, not A10).
- Startup source was briefly unparseable after reverting mutation 1 (a joined line); fixed before any further run.
- Activation (E): `test_run_json_gains_the_staged_keys_and_no_authority_markers` failed as designed (see §4). **A real defect**: the first local-stub run exited 44 — a handoff in the *last* call of a group wrote TERMINATION after the DONE that closed the group; fixed (TERMINATION now precedes the call's answer) with a regression test. **A second real defect** from the first real-process restart: a fresh lineage whose first run died before its first checkpoint stopped as `run_json_unreadable`; fixed (§3, authority) with three regression tests.
- Runtime adoption tests: three wrong expectations of mine (window eviction made 1 MB `say`s fit — the test now uses pinned system notes; a refused turn ends without a second reply; the fake client JSON-encodes arguments).

### Negative controls (mutations, each reverted; `grep MUTATION services/` is empty)

1. Startup ignores `RECOVERING` → `test_a_crash_inside_recovery_never_turns_unknown_into_unrun[after-truncate-tc2-invoking]` fails: call_a "not run" instead of unknown.
2. `Session.invoke` runs the tool before INVOKING is durable → `test_o1_7_a_failed_invoking_sync_never_starts_the_tool` fails (`['tool'] == []`), and the real-process `test_script_a_failed_gate_sync…` fails (`{'act': 1, 'read_file': 1}`).

Other tests were not individually mutation-checked.

## 2. Source → mechanism → tests

| Source | Mechanism | Tests (fixtures) |
|---|---|---|
| `services/chassis_envelope.py` (new) | K-E2: E units, marker truncation, wire ids (moved unchanged from chassis.py), caps and `invalid_caps`, `adopt_response` (16 invoked / 32 stored / 256 hard; omitted hash + notice; name/argument dispositions; originals offered), `request_bytes` | `test_chassis_adoption.py`: O4-8 counts 1/16/17/32/33/256/257 (pure and live), C-B5, C-B6 (exact 109-byte elision), C-B7, O4-1, C-B8/9/10, O4-9, O4-12 + negative control, O4-10 literal reproduction, O4-11, malformed names, argument dispositions, largest TURN_RESPONSE frame ≤ MAX_LEDGER_BODY, live local refusal (no request, no REQUEST_SENT), live label = recorded label; retained `test_chassis_wire.py` |
| `services/chassis_replay.py` (new) | One reducer for live and replay; fixed key order; state wire schema + validation; `retained_refs` | `test_chassis_replay.py` (FX-C BASE literal hash, turn 7, C-1 partial states, C-D3 literal, order refusals, admission-text answers, C-N2, foreign adoption, drop notice, HISTORY_REPLACED, base switches, originals FIFO, 11 schema refusals) |
| `services/chassis_session.py` (new) | The owner: REQUEST_SENT/INVOKING gates, blob-before-DONE, MSG_APPEND, notes, HISTORY_REPLACED, RECAP_FOLD, CK1–CK6, thresholds, rotation at unit boundaries, single FSYNC_FAILED boundary | `test_chassis_session.py` (replay equality after every scenario, O1-7, failed REQUEST_SENT, blob failure, install/run.json failure, marker-once, CKG, O2-3, C-G2, byte threshold, rotation, control exceptions, typed end incl. last-call regression, 33/257 live, originals FIFO/256 KiB) ; `test_chassis_checkpoint.py` (CK order, plain list, run.json mirror, prev chaining, reference graph, O2-2 shape) |
| `services/chassis_startup.py` (new) | A0–A15 authority, tail classes → recovery transaction (`RECOVERING`), previous-base replay with hash check, A8/A11/A12/A14 switches, acknowledgements (`ACKNOWLEDGED`) | `test_chassis_recovery_live.py` (A0, A1/C-K7, A4, A5, C-N3/4, A6/C-K5, A7, unreadable/missing run.json, A13 interrupted first run, interrupted legacy import, C-1a…f + idempotent second start, C-D3, O1-1a/1b, O1-2, O1-5 corrected both ways, C-D1, O1-4 + ack, stale ack, unimplemented resolutions, O1-6, C-K2/A11 with and without unmerged suffix, C-K3/A12, C-K4/A15, A14/O2-2, O2-2 negative, A14 unbound, C-K6/A8, CK cuts, recovery cuts, ack cuts, O2-7, 4 real script restarts); `test_chassis_notes.py` (C-N1, C-N2, O2-1, O2-6, mirrors, unwritten mirror, file edit, TC2 NOTE_WRITTEN, watermark through set_history/edit, note + open group, note + TC4) |
| `services/chassis.py` | Activation: every mutation through the session; startup before the socket/duty; request sizing + correlation label; adoption before tools; TERMINATION once; RUN_END; `--acknowledge-stop` | retained R6–R9; live tests in R1 |
| `services/chassis_persistence.py` | Three deliberate edits (§3) | R5 |

## 3. Decisions, deviations and additions (for review)

**Authority and recovery**
- *Recovery transaction.* `RECOVERING` (durable, before copy/truncate) names P's end and the tail hash; a restart rebuilds the tail from its quarantined copy, re-derives the same outcome and writes only what is missing. Without it a crash after truncation turns "unknown" into "unrun" (mutation 1).
- *Authority without run.json:* a ledger with no CHECKPOINT is "unpublished" — our own interrupted first run (A13) — whatever run.json says; with a CHECKPOINT and no run.json it is a deletion → new stop `run_json_missing`; with a CHECKPOINT and a non-format-2 run.json it is A8.
- *A6* copies into `corrupt/` and leaves the file in place (moving it would make the next start see an absent file). *A14* copies, appends a notice, and replaces `conversation.json` durably **without rotation**, so `conversation.prev.json` keeps its bound base.
- *Base switches* (LEGACY_IMPORT, EXTERNAL_EDIT, LEGACY_REIMPORT) carry the adopted list as a blob plus `recap_folded`, so the suffix replays exactly; switches carry this recovery's notices (a notice before a switch would be replaced). A4 writes `LEGACY_IMPORT{conv_sha: null}`.
- *No resume-time checkpoint.* Recovery/resume records are bound by the next threshold, turn-end or run-end checkpoint; until then the suffix replays them (convergence is tested: interrupted import, A10 via a recorded switch). This also keeps the retained "startup failure touches no memory" test true.
- *Request identity.* REQUEST_SENT sets `requests.last.outcome = failed_unknown` and `requests.next = attempt+1` until a response is recorded, so any failure (status-less or not) retries under a new label. A request still unanswered at a start gets one RECOVERY{possible_duplicate_spend}. After an acknowledged TC4 the next turn is `requests_next.turn + ⌊L/117⌋ + 1`, attempt 1: **conditional** on the hidden L bytes containing no earlier skip of this kind (each hidden turn needs ≥ one 117-byte frame).
- *Acknowledgements:* implemented for `ledger_tail_ambiguous/continue-conservative`, `fsync_failed_previous_run/continue-from-bound`, `corrupt_quarantine_full/continue-from-bound`. Every other reason/resolution (including every `bootstrap-preserving`) is **refused with no change** — deferred, not half-performed.

**Records and state (extensions to v2 1.2/1.4.2, all additive keys)**
- `TURN_RESPONSE.calls[].admit_text` and `originals[]`; `normalization.coerced_fields`. Calls with `admit ≠ invoke` are answered by `admit_text` when the group reaches them — **no UNRUN record** — because the accepted frontier closes the group at the last invokable call (so v2 1.4.7's U_r over-counts; not claimed anyway).
- `MSG_APPEND{note}` carries its blob; `foreign: true` (A8, already in the list); notice `reports` resets the drop count.
- `RECOVERY{note_dropped_pending_limit}` (v2 1.4.6 names the drop, not a record; without one a drop after the newest checkpoint is lost on replay). `RECOVERY_ACK{ack_id, tail_sha256?}`. RECOVERY details carry `tail_sha256`.
- State: `requests.next`, `notes.adopted_mirror_sha256`, `notes.dropped_pending_limit`, `pending[].mirror_sha256`.
- TERMINATION precedes the answer of the call it ended in (the answer may close the group).

**Foundation edits (`chassis_persistence.py`, accepted SV020)** — R5 still 114 passed:
1. `quarantine_tail` skips re-admission when its identical copy already exists (re-run after copy-before-truncate).
2. `BlobStore.get(sha, limit)` (base-switch blobs use 64 MiB, today's conversation read bound).
3. The legal-next frontier now matches the live owner: after an unanswered REQUEST_SENT, unit-boundary types are reachable too (a duty can survive a failed request); RECOVERY is reachable inside a group (17th-note drop). `test_chassis_recovery.py`'s frontier assertion was updated accordingly.

**Behaviour changes visible to a duty**
- Tool results, notes and messages are now bounded and normalized (CAP_RESULT 32 KiB E with marker; notes 64 KiB E; direct `say`/`note` must be text, ≤ 1 MiB E; queued ≤ 64 KiB E; `set_history` a list of dicts with string roles, JSON-serializable, ≤ 16 MiB).
- A handoff note is adopted once per generation (C-N1), not every run. The legacy `Chassis.resume` remains only for session-less objects; retained `test_resuming_repeatedly_adds_the_handoff_and_no_pinned_recap` (and the other bare-instance resume nodes) now exercise only that helper.
- `run.json` publishes `format: 2`, `writer`, `history_epoch`, `checkpoint` — retained `test_chassis_metadata.py`'s first test was deliberately rewritten (and renamed) to assert they are present and mirror a ledger CHECKPOINT.
- Unified exception identity: `chassis.PersistenceFailure is chassis_persistence.PersistenceFailure` (an OSError).

**Known limits of the implementation**
- Queued messages are memory-only until the group closes: process death loses them (they were never durable).
- `recap.md` is not ledgered; RECAP_FOLD records only the fold point, written after the recap append (a crash between repeats lines, never loses them).
- Reading `conversation.json`/`.prev.json` stays O(conversation size) [X].

## 4. Crash-cut matrix (tested)

| Cut | Expected | Test |
|---|---|---|
| CK2 temp fsync / CK3 prev rotation | A9, file unchanged | `test_checkpoint_crash_cuts…[ck2-temp|ck3-prev]` |
| CK4 install / CK5 run.json / CK6 before write | A10 (equals replay), no EXTERNAL_EDIT | `…[ck4-install|ck5-run-json|ck6-before-write]` |
| CK6 written, unsynced (process death) | A9 | `…[ck6-written-unsynced]` |
| turn 7 after each record | C-1a…f | `test_c_1_…[c-1a…c-1f]` |
| recovery: after intent / copy / truncate / first record × TC2-INVOKING, acknowledged TC4 | same outcome as uninterrupted; nothing written twice; one copy; intent removed | `test_a_crash_inside_recovery…` (8) |
| acknowledgement: after ACKNOWLEDGED, before STOPPED removed | A0 (no permission) | `test_acknowledgement_crash_cuts…` |
| ack transcription: after RECOVERY_ACK, before ACKNOWLEDGED removed | one RECOVERY_ACK | `test_an_fsync_acknowledgement_is_transcribed_once` |
| gate fsync fails (REQUEST_SENT, INVOKING), blob fsync before DONE, install, run.json, marker itself | no effect; marker attempted once; session refuses everything after | `test_chassis_session.py` |
| quarantine at capacity | no copy, no truncation, stop; continues after acknowledgement | `test_o2_7…` |
| **real process:** death inside a tool; SIGKILL with a request in flight; injected EIO on the INVOKING fsync; damaged tail between runs | unknown/unrun, no re-invocation, no request during recovery; new attempt label; tool never started + A1 stop + CLI ack + unknown; TC4 stop, CLI ack, hidden-turn notice in the next request and skipped turn | `test_script_*` (4) |

## 5. Not claimed

GC is disabled (no GC_INTENT/GC_DONE execution): no C-G1/O2-4 pass, no bounded total disk; segments and blobs are retained. `retained_refs` (refs(C_n) ∪ refs(C_p) ∪ refs(retained suffix)) is tested complete for what replay reads, not used. Thresholds (256 records / 8 MiB) and unit-boundary rotation are active, but the v2 1.4.7 bounds (358/717 records, 25,166,144/50,352,266 bytes) are **not claimed**: they also assume fields this runtime does not bound (e.g. RECOVERY detail sizes, notice texts, admission texts) and the U_r composition differs (§3). Counter domains: every integer the ledger header or a COUNTER_FIELDS key carries is ≤ 12 digits, refused before writing; checkpoint state counters are validated on read. No recorder-side label check (the recorder strips/records the label, R-B1; here only the stub and fake client saw it): the external label portion of C-1a/O1-6 is not claimed. No power-loss, kernel/storage, provider-compatibility, deployment or full-suite result.

## 6. Correction 1 runs (final corrected tree)

Runtime/test correction committed by the coordinator at `06fbc40e4df3287f8995bb54713ce316164b29d7` after worker exit 0; committing changed no source/test bytes. Independent re-review pending.

Pre-fix evidence (each regression node alone, on the unmodified reviewed code) is in `checkpoint-001-astra-corrections.md`: 12 regression nodes failed as the review's traces predict (SV021-01 ×2 incl. a real-process run, -02 ×3, -03, -04, -05, -06 ×3, -07); one coverage cut (`…legacy_note_is_appended…`) passed before and after.

During the post-fix runs, `test_o4_8_257…` failed once on its exact payload pin (the new `notice` key) and was updated as listed there; no other failure occurred. Final batches, one command at a time, same runner:

| # | Targets | Result |
|---|---|---|
| C1 | `tests/test_chassis_adoption.py` | 50 passed |
| C2 | `tests/test_chassis_replay.py tests/test_chassis_session.py` | 61 passed (31 + 30) |
| C3 | `tests/test_chassis_notes.py tests/test_chassis_checkpoint.py` | 23 passed (13 + 10) |
| C4 | `tests/test_chassis_recovery_live.py` | 74 passed (69 in-process + 5 real script restarts) |
| C5 | accepted foundation: ledger, recovery, durability | 114 passed |
| C6 | `tests/test_chassis_termination.py` (incl. 14 script-mode runs) | 67 passed |
| C7 | groups, wire, supervisor flap, metadata | 65 passed |
| C8 | the 22 retained `test_chassis.py` + 7 `test_services.py` nodes | 29 passed |
| C9 | the 5 local-stub `test_run_end_to_end.py` nodes | 5 passed |

Total 488 selected passes, no failures, no full-suite run. The pre-correction negative controls (§1) were not repeated; the 12 pre-fix failures above are this correction's negative evidence.
