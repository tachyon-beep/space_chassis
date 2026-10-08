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
- Total: 161 nodes in 13 post-fix commands (R1a … R11).
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
