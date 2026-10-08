# SV-026 status

## Design phase: complete, awaiting Astra's independent review. Not implemented. Not accepted.

Base: `2ce8bad76c23a86d0962df90525c0c1509bbd126` (SV016–SV024 runtime accepted; the SV025 test-only correction is under review). Scope: `SV-026-accounting-preflight.md`. Opus is the primary designer and implementer; Astra reviews. Implementation waits for the coordinator's reviewed implementation prompt.

Deliverable: [DESIGN.md](DESIGN.md).
- the quantity (§1)
- the reducer blob-read inventory and writer charges (§2)
- the source-to-change map (§3)
- the algorithms (§4), the GC crossing (§5), invariants and failure behavior (§6)
- the finite test manifest and run plan (§7), the smallest subset (§8)
- decisions D1–D7 and the unresolved contracts (§9)

### Inputs read (source text only)

- `SV-026-accounting-preflight.md`
- canonical SV-015 v2 §1.4 (1.4.1–1.4.10)
- `docs/planning-context/sv025/RECEIPT.md` and `STATUS.md` (Correction 1 governs; withdrawn first-round rows not used)
- `CLAUDE.md`
- runtime:
  - `services/chassis_session.py` (whole)
  - `services/chassis_replay.py` (whole)
  - `services/chassis_startup.py` (`open_session` through `_consume_ack`, `_remove`, `_replay`, `derive_core`)
  - `services/chassis_persistence.py` (`Record`, `scan_segments`, `_call_outcome`, `BlobStore.get`/`put`, `continue_after`, `open_segment`, `append`, `rotate_if_full`, `append_with_blob`, `sync_inherited`)
  - `services/chassis_gc.py` (batch and body bounds)
  - `services/chassis.py` (`turn_once`, `close_group`, recap fold, `checkpoint`, `write_handoff`, `run`, `resume_session`)
- tests:
  - `tests/test_chassis_bounds.py` (observer, oracle helpers, tests 3–6)
  - `tests/test_chassis_session.py` (threshold tests)
  - `tests/test_chassis_recovery_live.py` (`Root`, `establish`, `resume`, the SV021-09/-10 setups)
  - helper signatures in `tests/test_chassis_gc.py`
  - `FaultOps`/`Crash` in `tests/test_chassis_durability.py`

The repository guides' bootstrap, install and broad-suite commands were not run. The bounded scope takes precedence.

### Findings that shaped the design

1. Every production blob read during replay goes through `Replay.read_blob`. The charge can therefore be measured where the reducer already reads, with no extra read and no declared length.
2. Startup leaves `since_bytes` at 0. It counts C_n's own frame and suffix LEDGER_HEADERs, which the live writer never charges.
3. `adopt_notes` charges the declared `entry["bytes"]`.
4. Startup, file-edit adoption, note adoption, both drop paths and GC bypass the threshold.
5. A startup checkpoint must follow the durable removal of RECOVERING (`_remove` fsyncs `session/`). Otherwise it would become an intent "extra" and break classification or a witnessed exact core.
6. At default constants a GC unit (2 records, GC_INTENT body ≤ 1 MiB) cannot cross the threshold alone. This is static arithmetic.

### Decisions requiring review (none silently selected)

D1 C_n frame, D2 LEDGER_HEADER, D3 damaged blobs, D4 GC crossing (G2 recommended, G1 alternative), D5 adoption granularity, D6 startup placement, D7 check-only boundaries. The recommendation, alternative and cost of each are in DESIGN.md §9.

### Proposed manifest (frozen only after review)

- New `tests/test_chassis_accounting.py`: **34 nodes** (33 under G1).
- `tests/test_chassis_bounds.py`: **16 nodes, unchanged in count**:
  - test 4's structural expectation is replaced after the fix (renamed);
  - test 5's cut is moved to the real pre-checkpoint crash window, and its newest-bytes counterexample is kept;
  - test 6 has one assertion change (`MESSAGES + 2` → `MESSAGES + 1`);
  - tests 1–3 are unchanged.
- Pre-fix discriminators: P1–P7, one node per command.
- Post-fix runs: R1–R12, one file per command, through the approved runner (CPU 120 s / wall 180 s / AS 512 MiB, one process).

### Execution log

No test, runner, Python, install or Git command was run. Only source reads and these two files were written.

One read-only compound shell search was **denied** by the permission layer: it needed approval, and this session has no approval surface. It was **not retried**. Its parts were done with the dedicated search tool instead:
- `BLOB_READ_MAX`/`CONVERSATION_READ_MAX`
- the `install_conversation` temp name
- the `Crash` helper
- the `Replay(` constructions

Nothing it would have shown is missing from the design.

The Filigree store was not used (it is read-only, and earlier session-context retrieval failed). No retry, repair or claim was made. There was no provider call, no real-session action, no credential or raw log access, no edit to an original repository, and no push, merge or deployment.

### Not claimed

None of the four §1.4.7 inequalities is proved or improved by this design. Numeric bounds, U_r/U_b, history caps, previous-file policy, H/T/Q/pump/history policies, canonical literals and the generator are untouched. SV025's refutations stand.
