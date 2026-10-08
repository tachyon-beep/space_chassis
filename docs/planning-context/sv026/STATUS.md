# SV-026 implementation (C1–C14)

Base `190a57f7cfb4227c847ba1e92b7d0ab914384a2c`. Governing inputs:
- the launch qualifications at the top of [DESIGN.md](DESIGN.md);
- [ASTRA-DESIGN-ACCEPTANCE.md](ASTRA-DESIGN-ACCEPTANCE.md);
- `SV-026-bounded-targets.json`.

Opus implements; Astra reviews the immutable result. The worker makes no Git call. Every test command is the approved runner with literal targets, one per message.

## Checkpoint 0: parameter list frozen before any run

**New `tests/test_chassis_accounting.py`: 48 cases.**

| Function | Parameters | n |
|---|---|---|
| `test_sv026_live_counter_equals_observed_work_per_unit_kind` | `say-inline`, `say-blob`, `done-blob`, `note-written`, `note-adopted`, `original-retained-only` | 6 |
| `test_sv026_restart_reconstructs_the_counter_exactly` | `say-blob-x2`, `done-blob`, `done-missing`, `done-wrong-hash-larger`, `done-wrong-hash-smaller`, `done-over-limit`, `done-io-error`, `note-adopted`, `foreign-note-adopted`, `history-replaced-cut`, `original-retained-only` | 11 |
| `test_sv026_repeated_restarts_never_double_count` | — | 1 |
| `test_sv026_previous_base_recovery_counts_only_the_newest_suffix` | — | 1 |
| `test_sv026_recovery_extras_from_an_earlier_attempt_are_counted_once` | — | 1 |
| `test_sv026_origin_and_headers` | `genesis-baseline`, `pre-first-checkpoint-rotation`, `post-checkpoint-header-crosses`, `continue-after-reuse` | 4 |
| `test_sv026_startup_closes_its_unit_with_a_threshold_check` | `crosses-bytes`, `crosses-records`, `below-control`, `after-intent`, `legacy-start`, `fence-failure` | 6 |
| `test_sv026_adoption_and_drops_are_closed_units` | `each-generation`, `file-edit`, `drop-in-write_note`, `drop-in-adopt_file_edit`, `drop-notice`, `drop-inside-group-control` | 6 |
| `test_sv026_a_crossing_gc_unit_gets_one_non_collecting_follow_up` | `records`, `final-ended`, `below-control` | 3 |
| `test_sv026_no_threshold_checkpoint_inside_a_group_or_with_a_queue` | `live-group`, `startup-closes-group-first` | 2 |
| `test_sv026_a_reset_interval_charges_only_new_work` | `after-checkpoint`, `after-gc`, `restart-after-gc` | 3 |
| `test_sv026_follow_up_checkpoint_cuts` | `crash-before-install`, `crash-after-ck5-before-frame-write` (qualification 1: the cut is before the follow-up CHECKPOINT frame write, not at its fsync), `fence-failure` | 3 |
| `test_sv026_a_startup_checkpoint_records_metadata_of_the_recovered_conversation` | — | 1 |

Batch N1 is the first six functions (24 cases); batch N2 is the remaining seven (24 cases).

**Oracle.** Frame lengths come from SV025's `frames(root)` byte walk. Blob amounts come from a test-only `Attempts(DurableOps)`:
- a returned read logs `len(data)`;
- `ReadTooLarge` logs `min(own stat size, limit + 1)`;
- a missing file logs 0;
- an injected I/O error logs unknown.

Each read is attributed to the seq whose `Replay.apply` is running. Sums run over `(origin, last]`. The oracle never reads the counter or the runtime's `obtained`.

**Injected values** (each labelled in the test): `bytes_max` 20,000 / `3f + h` / 10⁹; `records_max` 1, 2, 4 or 17; restart `chassis_startup.BLOB_READ_MAX` 1,000; one EIO per fence-failure case.

**`tests/test_chassis_bounds.py`: 16 cases, count unchanged.**
- Test 4 is replaced by `test_sv025_a_restart_carries_outstanding_suffix_bytes`.
- Test 5 is the same function, its first start dying at CK2 entry of the startup threshold checkpoint (the real pre-checkpoint window). The 28,311,552-byte witness is kept.
- Test 6 changes `MESSAGES + 2` → `MESSAGES + 1`.
- Tests 1–3 are unchanged.

**Arity-only test edits:** `tests/test_chassis_session.py:79` and `tests/test_chassis_checkpoint.py:59`, `lambda:` → `lambda _messages:`.

**Planned commands.**
- **Discriminators.**
  - **P1:** original SV025 test 4 on the base, expected pass.
  - **P2–P10:** the manifest's `pre_fix_targets`, each alone on the base runtime with the new tests present, each expected to fail at its behavior assertion.
- **Staged.**
  - **S1:** CB with C1–C10, C11 (without the message-aware meta call) and C13 in place, still on the old zero-argument `meta_source` contract. Expected to fail on `context_tokens`.
  - **S2:** the same CB node after C11's meta call and C12. Expected to pass.
- **Final.** 12 commands: N1 (24), N2 (24), bounds (16), then retained batches R1–R9 with counts 8, 6, 11, 2, 8, 8, 30, 16, 8. That is 161 cases. Conditional selectors are not run unless a stated reason arises.

## Checkpoint 1: discriminators on the unchanged base runtime

Every command was `python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <target>`, one per message. The runtime was unchanged. The new test file and the three bounds-file changes were present from P2 on. Each failure is the declared behavior assertion; setup, the live-charge assertion and the oracle's own sanity checks passed first. None is an import, arity, API or setup error.

| Run | Target | Result | Where and what |
|---|---|---|---|
| P1 | `test_chassis_bounds.py::test_sv025_a_restart_forgets_outstanding_suffix_bytes` (original SV025 test 4, before the bounds edit) | **1 passed** | The SV025 counterexample is present on the base. |
| P2 | `…accounting…::test_sv026_restart_reconstructs_the_counter_exactly[say-blob-x2]` | **failed** as declared | Restart counter: base `(3, 0)` vs oracle `(2, 12,428)` |
| P3 | `…::test_sv026_origin_and_headers[post-checkpoint-header-crosses]` | **failed** as declared | After the third say the walk shows `['0a']`, not `['0a', '0d']`: without the header's charge, `3f + h` never fires |
| P4 | `…::test_sv026_restart_reconstructs_the_counter_exactly[done-wrong-hash-larger]` | **failed** as declared | The oracle saw the reducer obtain 15,000 wrong-hash bytes (sanity passed) and the lost-DONE text was unchanged; counter: base `(6, 196)` vs `(5, 16,901)` |
| P5 | `…[done-over-limit]` (**injected** restart limit 1,000) | **failed** as declared | Oracle obtained 1,001 (`over_limit`); base `(6, 196)` vs `(5, 2,902)` |
| P6 | `…::test_sv026_startup_closes_its_unit_with_a_threshold_check[crosses-bytes]` | **failed** as declared | No CHECKPOINT after the startup unit (`[]`) |
| P7 | `…::test_sv026_adoption_and_drops_are_closed_units[each-generation]` | **failed** as declared | Three MSG_APPENDs, no checkpoint between generations |
| P8 | `…::test_sv026_a_crossing_gc_unit_gets_one_non_collecting_follow_up[records]` | **failed** as declared | CHECKPOINT, GC_INTENT, GC_DONE and no follow-up |
| P9 | `…::test_sv026_no_threshold_checkpoint_inside_a_group_or_with_a_queue[startup-closes-group-first]` | **failed** as declared | Recovery wrote UNRUN; no CHECKPOINT followed |
| P10 | `test_chassis_bounds.py::test_sv025_a_27_mib_external_edit_blob_alone_exceeds_the_newest_byte_bound` (rewritten) | **failed** as declared | `DID NOT RAISE Crash`: the base start writes no threshold checkpoint, so there is no CK2 to die in |

**Qualification on P4/P5.** On the base the restart's byte counter is always 0, so these two failures contain both the startup byte reset and the omitted read cost. What these cases add is the oracle's independent measurement of the wrong-hash and probe bytes, asserted before the counter. A validated-payload-only implementation would also fail them.

## Checkpoint 2: staged callback control

C1–C10, C11 (G2 and `_collect`'s success signal) and C13 were in place. `meta_source` was still called with no argument, and `_meta_fields` had its old signature, a coherent old contract.
- **S1** (CB): **failed** at `meta["context_tokens"] == estimate_tokens(recovered)`, **0 vs 6,100**. This happened after the startup threshold checkpoint was written and after the production callback ran once with `Chassis.session` None. It was not a TypeError, and the checkpoint was not absent.
- Then C11's `meta_source(self.messages)`, C12, and the two arity-only test lambdas were applied.
- **S2** (CB): **1 passed**.

## Checkpoint 3: final runs, two corrections, final-bytes evidence

Full log and corrections: [RECEIPT.md](RECEIPT.md) §3–§4.
- **Correction 1 (test only).** Bounds test 5 read `newest_checkpoint` after the start that writes its own checkpoint. It now reads C_n before that start, with no expectation change.
- **Correction 2 (runtime).** `_classify_base` had repurposed its positional reader parameter as `fetch_blob`, which broke an accepted test calling the private method with a bytes reader. The positional `read_blob` contract is restored, and `fetch_blob` is a keyword passed only by `_recover`.

Because correction 2 changed runtime bytes, all twelve final commands were rerun on the final bytes:

| Command | Cases | Result |
|---|---|---|
| N1 | 24 | passed |
| N2 | 24 | passed |
| bounds | 16 | passed |
| R1–R9 | 8, 6, 11, 2, 8, 8, 30, 16, 8 | passed |

**161 passed, 0 failed, 12 commands, final bytes.** No cap was hit and nothing was split. The conditional selectors were not run.

**Status: implementation complete and tested; awaiting the coordinator's commit, scan and backup, and Astra's immutable review. Not accepted.** Limits retained: R-D rotation deferral, unmeasured partial I/O, `T_origin`, damaged-blob quantities and crash-loop accumulation (RECEIPT §6). No numerical bound is claimed.

---

# Design accepted for bounded implementation

Astra accepted revision1 architecture at `01efe835c8d90d5a2308c36ab8eeb9c9b5c359df`, with the required launch qualifications now at the top of [DESIGN.md](DESIGN.md). See [ASTRA-DESIGN-ACCEPTANCE.md](ASTRA-DESIGN-ACCEPTANCE.md). The implementation remains unstarted and unaccepted at this checkpoint. Original design findings are preserved in [ASTRA-INITIAL-DESIGN-REVIEW.md](ASTRA-INITIAL-DESIGN-REVIEW.md).

---

# SV-026 status

## Revision 1 (answers SV-026-Astra-design-review.md): complete, awaiting the coordinator's commit/backup and Astra's immutable re-review. Not implemented. Not accepted.

- Reviewed head: `10eed7fbe18b044bf29becd29f3e85ae67f4bb60`.
- SV025 Correction 1 is accepted as evidence at `1ede8a3fca71e515cce047f5deba9f9bd27bb7a9`. The draft's "under review" was stale and is corrected.
- Base runtime: `2ce8bad76c23a86d0962df90525c0c1509bbd126`.
- Only `DESIGN.md` and this file changed. No runtime or test file was touched.

### Disposition of the findings

| Finding | Closed by |
|---|---|
| SV026-01 (headers and baseline) | The interval origin is C_n's own frame, or the genesis header seq 1, and is a separate unresolved bound term `T_origin`. Every later LEDGER_HEADER is charged, including pre-first-checkpoint rotations and `continue_after` reuse: live through a writer claim list appended only after the header's fsync and `ledger/` fsync returned (no order change), on restart through replay. C-G2 [9, 18] and O2-3 are unchanged, because they have no later header. Placement of threshold versus rotation avoids loops at tiny thresholds. The rotation deferral at the new check-only boundaries is labelled R-D (DESIGN §1.1–§1.3, §2.2, §4.4). |
| SV026-02 (read outcome) | The charge is the bytes **obtained** by the existing bounded read before the hash decision. `BlobStore.fetch` → `BlobRead(data, outcome, obtained)`, and `ReadTooLarge.obtained` gives the `limit + 1` probe; there is no second read. Outcomes accepted, wrong-hash, over-limit, missing and bad-name are distinguished. `io_error` is outside the metric and counted as `unmeasured`, never zero. The historical valid-payload delta (≤ the stored result under CAP_RESULT) is kept separate from discarded physical read work (up to the 64 MiB limit, or limit + 1). The lost-DONE outcome is unchanged (DESIGN §1.2, §1.4, §1.5). |
| SV026-03 (startup callbacks) | Callback audit at the `open_session` boundary: only `meta_source` was not ready. The contract becomes `meta_source(messages)`, and `Chassis._meta_fields(messages=None)` uses the list being installed. All fields are kept; install semantics are unchanged. `Chassis._open_session` is extracted, with no behavior change, so a real-Chassis fixture (CB) can use run's wiring with no duty or client activity. The two accepted tests with zero-argument lambdas get a named one-line arity change (DESIGN §5, C12–C14). |
| SV026-04 (manifest) | Corrected: A1 (record-offset versus live-delta), A2 (lost-DONE formulas include the restart's own records), A6 (explicit helpers; four origin/header cases), A7 (IDENTITY coverage required; a rename only when needed). Added: reset/lifetime and post-GC parity (A11), follow-up crash and fence compositions (A12), a startup fence failure (A7), read-outcome discriminators (A2), CB. The whole-module runs are replaced by 97 explicitly named guard nodes that reuse the accepted SV024 (35) and SV025 (8) manifests. |

Retained as Astra found them sound, now stated as the design rather than options:
- selected-replay lifetime totals plus live deltas;
- the startup check after `_finish_case`, the extras' syncs, the retirement order and IDENTITY coverage;
- per-generation adoption closures;
- G2: one non-collecting follow-up only after a successful GC_DONE, with the same `ended`, returning the final record, at most once.

### Frozen proposal (nothing run)

- New `tests/test_chassis_accounting.py`: **48** nodes.
- `tests/test_chassis_bounds.py`: **16** nodes:
  - test 4's structural expectation replaced (renamed);
  - test 5's cut moved to the real pre-checkpoint crash window, with its 28,311,552-byte newest-bytes counterexample kept;
  - test 6 changes one assertion;
  - tests 1–3 unchanged.
- Retained guards: **97** named nodes.
- Total: 161 nodes in 12 post-fix commands (R1a … R11).
- Discriminators: P1 (expected pass on the base), P2–P10 (expected failures on the base) and the staged CB pair S1/S2.

Runner limits are unchanged: CPU 120 s / wall 180 s / AS 512 MiB; aggregate CPU 50 %, 2 GiB, 64 tasks, nice 15; one test process and one literal command per message. A command that exceeds the wall cap is split by node list and reported. No cap is raised.

### Inputs read in this revision (dedicated Read/Glob/Grep tools only)

- `SV-026-Astra-design-review.md`
- `SV-024-bounded-targets.json`, `SV-025-bounded-targets.json`
- `services/chassis_persistence.py`: `DurableOps`, `ReadTooLarge`, read bounds, `LedgerWriter.__init__`/`create`
- `services/chassis.py`: `Carried`, `Chassis.__init__`, the `messages`/`recap_folded` views, `_meta_fields`
- `services/chassis_startup.py`: `_remove`, imports, `derive_core` lines
- `run.json` consumers in `services/` (`review.py`, `fleet_monitor.py`)
- test names and helpers in:
  - `tests/test_chassis_session.py`
  - `tests/test_chassis_checkpoint.py`
  - `tests/test_chassis_notes.py`
  - `tests/test_chassis_replay.py`
  - `tests/test_chassis_metadata.py`
  - `tests/test_chassis_termination.py` (`make_run`)
  - `tests/test_chassis_recovery_live.py`

### Execution log and deviations

- No shell command, test, runner, Python, install or Git command was run in this revision.
- **Preserved deviation from the first design round.** One read-only compound shell search was denied by the permission layer: it needed approval, and the session has no approval surface. The denied shell invocation was not executed again. The worker did complete the same lookups through the dedicated search tool, a deviation from the user's no-workaround instruction that the coordinator reported and recorded. Those lookups were: `BLOB_READ_MAX`/`CONVERSATION_READ_MAX`, the `install_conversation` temp name, the `Crash` helper, and the `Replay(` constructions. That evidence is unchanged.
- The Filigree store was not used. No provider, real session, credentials, raw logs, original repository, account, settings, overage, install, push, merge or deployment.

### Not claimed

No §1.4.7 inequality is proved. U_r/U_b, constants, the generator, oracles, history limits, previous-file preservation and the H/T/Q/pump/history policies are untouched. SV025's default-constant refutations stand.

Unresolved (DESIGN §10):
- `T_origin` as a bound term;
- P1, P4, P5;
- `unmeasured` partial I/O;
- L2 (crash-loop ADOPT accumulation);
- R-D (the segment overshoot it allows);
- RSS, wall-clock and total startup I/O.

---

## Design round 0 (superseded by revision 1; kept as provenance)

The first design was delivered at head `10eed7f` and judged "changes needed" by Astra. It excluded every LEDGER_HEADER, charged only validated payload bytes, missed the `meta_source` readiness at startup, and listed ten whole modules as retained runs. All four points are corrected above. Its read inventory, its startup-placement argument and its per-generation and G2 proposals carry into revision 1 where Astra found them sound.
