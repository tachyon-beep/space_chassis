# SV-027 design: segment rotation at every closed unit boundary (closes R-D)

**Status: design only, for independent review. Not implemented. No test was run. No runtime or test file was changed.**

Provenance:
- Base inspected: `a17115f89b3775ca0a34cd759be79bd1fe38c9e3`. It contains the SV026 C1–C14 implementation (receipt: 161 passed in 12 commands), which was under review while this proposal was drafted. The coordinator subsequently verified SV026 implementation acceptance in `sv026/ASTRA-ACCEPTANCE.md`, archived at `e6016fc1cd5fa3d68c54f40c9c21834210231660`, with no runtime correction. The inspected source is therefore unchanged. SV027 implementation still waits for its own design review and a separate prompt.
- SV025 evidence is accepted at `1ede8a3fca71e515cce047f5deba9f9bd27bb7a9`.
- The obligation is R-D, deferred by SV026: DESIGN §4.4, RECEIPT §6, and ASTRA-DESIGN-ACCEPTANCE ("does **not** close the all-boundaries rotation obligation").
- Canonical text: SV-015 v2 §1.4.1, §1.4.6 (the segment row), §1.4.8 and §1.4.10 (the segment-rotation row).
- Uploaded and context documents are design evidence, not new authority.

---

## 1. The canonical rule, verified

| Source | Text | What it governs |
|---|---|---|
| §1.4.1 Units | "A **unit** is one of: a turn …, one direct `say`/`note`, one direct `write_note`, one `set_history` …, one recovery/adoption step, one GC." | where boundaries are |
| §1.4.1 Threshold | "After each unit, if records since the newest checkpoint ≥ `RECOVERY_RECORDS_MAX` or their bytes … ≥ `RECOVERY_BYTES_MAX`, checkpoint." | the **checkpoint** predicate |
| §1.4.6 Ledger segment | "rotate at a unit boundary when ≥ `SEGMENT_MAX = 16 MiB`" | the **rotation** predicate |
| §1.4.8 | New segment: `O_EXCL` open, `LEDGER_HEADER{first_seq = last+1, prev_chain}`, `fsync(file)`, `fsync(ledger/)`; "Only then may the next record go there." A lost name leaves the old segment ending TC0. | rotation durability |
| §1.4.10 Segment rotation | LP: `fsync(ledger/)` after the header frame. Next permitted action: "append next record". | rotation linearization |

**Threshold and rotation are separate predicates over separate quantities.** The threshold measures replay work since the interval origin (SV026's counter) and writes a CHECKPOINT. Rotation measures the active segment's bytes (`LedgerWriter.segment_bytes`) and writes a LEDGER_HEADER into a new file. Neither resets the other:
- a checkpoint does not empty the segment;
- a rotation does not reset the counter; its header is *charged* to it (SV026 §1.3).

So a closed boundary must evaluate both, and evaluating one is not evaluating the other. SV026's `threshold_boundary` evaluates only the first. That is R-D.

**Reading of "at a unit boundary".** The canonical sentence does not say "every" or "first". This design takes it as **the first closed unit boundary at which `segment_bytes ≥ segment_max`**, for three reasons:
- it is the reading the runtime already implements in `unit_end` (`chassis_session.py:581–588`);
- the `MAX_SEGMENT_READ` comment (`chassis_persistence.py:944–946`) relies on it;
- SV026's acceptance names the all-boundaries obligation.

If a reviewer instead reads §1.4.6 as permitting rotation at *some* boundary, the current runtime already complies, and SV027 is a strengthening rather than a correction. Either way, the change only adds rotation at points where §1.4.6 permits it (unit boundaries). It changes no constant, threshold or policy, so **no owner choice is required**.

## 2. Current behaviour at the base

Closed boundaries and what each evaluates today:

| Boundary (§1.4.1 unit) | Code | Threshold | Rotation |
|---|---|---|---|
| turn end | `chassis.py:822` → `Session.checkpoint` | always checkpoints | yes, at the end of `checkpoint` (`chassis_session.py:690`) |
| run end | `chassis.py:1248` → `checkpoint(ended=…)` | always | yes |
| `set_history` | `replace_history` → `checkpoint` (`:568`) | always | yes |
| GC | inside `checkpoint` (G2) | one follow-up | yes, once, after the last checkpoint |
| direct say/note | `append_message` → `unit_end` (`:429`) | yes | yes |
| direct `write_note` (stored) | `unit_end` (`:479–480`) | yes | yes |
| recap fold | `chassis.py:994` → `unit_end` | yes | yes |
| **direct `write_note` (17th dropped)** | `threshold_boundary` (`:460`) | yes | **no** |
| **file-edit adoption** | `threshold_boundary` (`:516`) | yes | **no** |
| **file-edit dropped** | `threshold_boundary` (`:506`) | yes | **no** |
| **each adopted generation** | `threshold_boundary` (`:542`) | yes | **no** |
| **drop notice** | `threshold_boundary` (`:545`) | yes | **no** |
| **legacy import (A4/A5)** | `threshold_boundary` (`chassis_startup.py:924`) | yes | **no** |
| **recovery transaction (A8–A15)** | `threshold_boundary` (`chassis_startup.py:1147`) | yes | **no** |

`_recover` and `_start_legacy` are the only startup paths that return a session (`chassis_startup.py:826`, `:844`, `:926`, `:1149`). No other closure exists.

`threshold_boundary` (`:590–600`) and `unit_end` (`:581–588`) have **identical guards** (`broken`, an open group, a non-empty queue) and an identical `checkpoint()` branch. The only difference is `unit_end`'s `else: self._rotate()`.

## 3. The change: one closed-boundary step

**Delete `Session.threshold_boundary`. Each of its seven call sites calls `unit_end()` instead.**

```
unit_end():                                   # unchanged code
    if broken or group open or queue: return  # CKG guards
    if _over(): checkpoint()                  # CK1–CK6, optional GC, ≤1 follow-up, then _rotate() once
    else:       _rotate()                     # rotate_if_full(); then _claim_headers()
```

At a non-full segment, `_rotate` does no I/O. `rotate_if_full` returns at `segment_bytes < segment_max` after `_usable()`, and `_claim_headers` takes an empty list. **At default constants, therefore, the event trace changes only when the active segment already holds ≥ 16 MiB.** Every existing default-constant test whose segment is below that sees byte-identical filesystem calls (§7.1).

### Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| Keep `threshold_boundary` and add `self._rotate()` after it at the call sites | When the threshold fires, `checkpoint` already rotates at its end. A second `_rotate` writes a second header whenever the first header's segment is itself "full" (at injected `segment_max = 1`, always). That breaks "one closure, at most one header". R2 (§8) is built to catch exactly this. |
| Give `threshold_boundary` a rotation branch | It duplicates `unit_end` under a second name. It is one more method to keep in step with CKG. |
| Rotate inside `_commit` or `append` when full | It would rotate inside a group or a recovery unit, against §1.4.6 "at a unit boundary" and SV026's no-rotation-inside-a-group property. |

The write_note stored path keeps `if self.replay.group is None: self.unit_end()` (`:479–480`). It is redundant with the guard but behaviourally the same, and it is left alone to avoid churn.

## 4. Source-to-change map (implementation phase)

| # | Location (base `a17115f`) | Change |
|---|---|---|
| C1 | `services/chassis_session.py:460` (`write_note` drop), `:506` (`adopt_file_edit` drop), `:516` (file-edit NOTE_WRITTEN), `:542` (each generation), `:545` (drop notice) | `self.threshold_boundary()` → `self.unit_end()`; the comment at `:460` says "a closed unit: threshold, then rotation" |
| C2 | `services/chassis_session.py:590–600` | delete `threshold_boundary` and its docstring |
| C3 | `services/chassis_startup.py:924` (`_start_legacy`), `:1147` (`_recover`) | `session.threshold_boundary()` → `session.unit_end()`; the comments at `:924` and `:1143–1146` add "or rotate a full segment", keeping the stated position |
| C4 | docstrings: `chassis_session.py:30–35` (module), `:528–530` (`adopt_notes`), `:582` (`unit_end`: "the one closed-boundary step"); `chassis.py:1137–1140` (`run`: startup may also write one segment header before the duty loads) | text only |
| C5 | `services/chassis_persistence.py:944–946` (comment above `MAX_SEGMENT_READ`) | Replace "so it can exceed that by one unit's frames" with a statement that it can exceed `SEGMENT_MAX` by what is written before the next closed boundary, which is not bounded here (§11). `MAX_SEGMENT_READ`'s value is unchanged. |

**Unchanged:** `LedgerWriter` (`open_segment`, `rotate_if_full`, `sync_inherited`, `_fence_namespace`, header claims), `checkpoint`, `_collect`, G2, `_claim_headers`, the counter, the constants and caps, `plan_recovery`, the intent/acknowledgement/IDENTITY code, GC planning and validation, quarantine, `install_conversation`, `Carried`, and every existing test file. No canonical literal, generator, oracle, history size or representation, previous-file rule, acknowledgement/bootstrap loss semantics, or H/T/Q/pump/history policy changes.

## 5. Ordering at each new rotation point

### 5.1 Startup (`_recover`)

```
… plan, classification, RECOVERING (fenced inputs), quarantine, rescan, continue_after
for r in extra: replay.apply(r)
pending GC completion (sync_intent, unlink_intent) when no extra
Session(...)  (+ selected replay's work)
commit core[len(extra):]  → into the inherited segment, full or not: a recovery unit is never split
_finish_case
sync extras' segments
retire carrier / RECOVERING (each fenced by _remove)
reserve IDENTITY (durable coverage)
unit_end():                                                ◆ was threshold_boundary
   over  → checkpoint: sync_inherited, CK1–CK6, _collect (no blocker remains), ≤1 follow-up, _rotate
   else  → _rotate: rotate_if_full → open_segment:
             sync_inherited()   fsync(inherited segment)   only if no core record was appended
             _fence_namespace() cached by continue_after: no I/O
             open(N+1, O_EXCL) → write header → fsync(file) → fsync(ledger/)
           then _claim_headers(): (1, h) into since_*
return Opening
```

- **Recovery-intent inputs.** RECOVERING names the tail's `segment`/`offset` and the anchor, fenced before the intent (`_fence_intent_inputs`, SV024-02). The new header is written only after RECOVERING's durable removal. No intent can therefore name it, and no `extra` re-derived under an intent can be a closure header. The witnessed exact core (SV023-03) is unaffected: the check `len(extra) > len(core)` runs under the intent, before the closure.
- **GC deletion authority.** A rotation writes no GC_INTENT and unlinks nothing. It advances `writer.segment_no`, the active segment, which `plan_collection` never lists (`chassis_gc.py:204`). The closed segment becomes eligible only when a later checkpoint's `C_p.covers_seq` passes its last seq (§1.4.5). A pending startup collection is completed (`unlink_intent`, then GC_DONE as the first core record) before the closure, so no header can fall between a GC_INTENT and its GC_DONE. That matters because `_pending_collection` requires the pending intent to be P's last record.
- **Inherited bytes (SV024).** `open_segment` calls `sync_inherited()` first, so the startup never rotates away from bytes no fsync covered. If the start appended any core record, `inherited` is already False and no extra fsync happens.
- **Acknowledgements (SV023-04).** `_consume_ack` (receipt sync, then carrier removal) completes before the closure. The rotation does not touch the receipt or the carrier.
- **IDENTITY.** Coverage is durable before the closure. A rotation is not an effect and reserves nothing.

`_start_legacy`: `start_fresh` (genesis segment 0) → LEGACY_IMPORT → `_consume_ack` → `unit_end()`. At defaults, segment 0 holds two frames and never rotates here; only an injected `segment_max` reaches this branch.

### 5.2 Adoption and drops

```
adopt_notes:   for each generation: MSG_APPEND{note[,foreign]}; unit_end()
               notes_dropped → notice MSG_APPEND; unit_end()
adopt_file_edit: drop → RECOVERY{note_dropped}; unit_end()   |  NOTE_WRITTEN{file_edit}; unit_end()
write_note:    pending ≥ 16 → RECOVERY{note_dropped}; unit_end(); return None
```

A header between generations is harmless to replay. The watermark, pending generations, foreign marks, `mirror_sha256s` and `notes_dropped` are checkpoint and replay state, and a LEDGER_HEADER mutates none of them. Inside a tool group (a `handoff`/`finish` drop), CKG's guard returns before either branch, so no rotation happens inside a group; the turn-end checkpoint rotates.

### 5.3 One closure's bounded work

Per closure, at most:
- one threshold checkpoint;
- one G2 follow-up;
- **one** rotation (one header).

The header is claimed into the new interval *after* the threshold decision and is evaluated at the **next** closure. A closure happens only after a unit's records. So even at `records_max = 1` and `segment_max = 1` there is no checkpoint → header → checkpoint loop and no header → header loop within a closure (traces T4, T5).

**Degenerate case at injected thresholds only.** A header-only segment counts as full when `segment_max` is below one header frame. A closure with no preceding record can then close a header-only segment. The two cases are startup after a `continue_after` reuse, and repeated starts after deaths before any record. This is bounded to one header per closure, and per start under a crash loop. At default `SEGMENT_MAX` a freshly opened segment is ~200 bytes and never full.

## 6. Failure and crash behaviour of the new rotation points

Every new I/O is `open_segment`'s existing sequence. Its failures already have one shape: `LedgerWriter._fail` (marker attempted) → `PersistenceFailure` → `Session._rotate` → `Session._fail` (no second marker attempt when the writer recorded one) → the session is broken.

| Where | New failure path | Result |
|---|---|---|
| startup, `_recover`/`_start_legacy` | `fsync(inherited segment)` (A9 with nothing to commit), `open(O_EXCL)`, header `write`, `fsync(file)`, `fsync(ledger/)` | `PersistenceFailure` out of `open_session`. It attempts FSYNC_FAILED again, best effort, as today (`chassis_startup.py:771–775`). `Chassis.run` → `_end_before_main(44)`. No duty is loaded, the client is never called, and there is no request or tool effect. Next start: A1 if the marker exists. |
| between generations, file edit, drop, notice (in `resume_session`) | the same five calls | `PersistenceFailure` out of `resume_session`. That call is before `run()`'s `try` (`chassis.py:1199`), so it propagates out of `run()` → `main()` exit 44 (`chassis.py:1790–1792`). Not reached: `bootstrap`, `main`, any request, any tool. A broken session refuses every later mutation and effect (`_usable`). Next start: A1 if the marker exists. |
| `write_note` drop, direct | the same | the same as the stored `write_note` path, which already rotates through `unit_end`: no new failure kind |

Pre-existing and unchanged: a `LedgerError` from segment-number exhaustion (`MAX_SEGMENT_NO = 999_999`) or seq width propagates as it does from every existing `unit_end`. At startup it is now reachable too, at the same practically unreachable width.

**Crash cuts of a new rotation** are §1.4.8/§1.4.10's rows, unchanged:
- **Before `open`:** nothing; the next closure rotates.
- **After `open`, before or within the header:** an empty or torn newest segment is O2-5's reuse, under the existing quarantine and intent machinery.
- **After the header's fsync, before `fsync(ledger/)`:**
  - process death leaves a complete header-only segment, which the next writer fences (SV020-01);
  - host loss may remove the name, and the old segment then ends TC0 and is recreated with the same `first_seq` (O2-5).

## 7. Traces that select the tests

Below, H is a LEDGER_HEADER. Test labels refer to §8.

- **T1. A9 with an inherited full segment** (the case R-D allows).
  - Base: P ends at C_n (seq k) in segment s, with `segment_bytes ≥ max`. The start writes nothing and resume adopts nothing. Turn 1 (REQUEST_SENT, a TURN_RESPONSE of up to 680,003 bytes, INVOKING/DONE …, CHECKPOINT) goes into s; only then does `checkpoint` rotate.
  - New: the start's closure does fsync(s), open s+1, H(k+1), fsync, fsync(ledger/), then the claim `(1, h)`. Turn 1 goes into s+1.
  - → R1[startup-a9-clean], R5[startup-inherited-fsync-eio], R5[startup-ledger-fence-eio], R5[startup-name-lost-is-recreated].
- **T2. Recovery with a core.**
  - Base: RECOVERING, then core into s, then retire, then IDENTITY; no header.
  - New: the same, then one header after the retirement.
  - → R1[startup-after-intent] (ordering against RECOVERING's unlink and session fence, and IDENTITY).
- **T3. Legacy A5, [injected] `segment_max = 1`.**
  - Base: H1, LEGACY_IMPORT 2 | OPENING 3, H4.
  - New: H1, LEGACY_IMPORT 2, **H3** | OPENING 4, H5.
  - → R1[legacy-import].
- **T4. Generations, [injected] `segment_max = 1` after open.**
  - Base: MSG g1, MSG g2, ….
  - New: MSG g1, H, MSG g2, H, …, notice, H.
  - With `records_max = 1` and `collect`, each closure is MSG, CHECKPOINT [GC_INTENT, GC_DONE, CHECKPOINT], H: exactly one header.
  - → R1[generations-and-notice], R2[generation-crossing].
- **T5. The rejected double rotation.** `threshold_boundary(); _rotate()` at `segment_max = 1` gives CHECKPOINT, H (from `checkpoint`), H′ (the header-only segment is "full"). → R2[startup-crossing] and R2[generation-crossing] assert exactly one header per closure.
- **T6. A header never triggers its own checkpoint.** [injected] `records_max = 2`, with one record of suffix at restart:
  - `since = 1`, not over → rotate → claim → `since = 2`, and no checkpoint is written at this closure;
  - the next say makes `since = 3` → CHECKPOINT, H.
  - → R2[header-evaluated-next].
- **T7. EIO at `fsync(ledger/)` after g1** (real `Chassis.run`): MSG g1, H (bytes present) → `PersistenceFailure` → no g2, no `main`, no request. → R5[generations-fence-eio-chassis].
- **T8. Crash at the same fence:** restart adopts g2 and g3 once; g1 is not repeated. → R5[generations-crash-converges].

### 7.1 Existing tests the new rotations reach (evidence)

The `_rotate` fallback writes only when the segment is full. Existing tests reach it only where `segment_max` is injected:

| Test / helper | Injection | New rotation reached? | Prediction |
|---|---|---|---|
| `test_chassis_gc.py` `start()` (`:50–55`) | `segment_max = 1` **after** `open_session` returns | startup closure: **no** (that writer had the default). Adoption in `resume()`/`adopt_notes()`: **yes** | Pass. Assertions are on segment and record *sets* and state, never on literal segment numbers. One extra header-only segment per adopted generation stays far below `GC_BATCH_MAX = 4096`. Directly affected: `test_c_g1_…`, `test_o2_1_…`, `test_restored_state_and_identity_without_their_source_records`. |
| `test_chassis_gc.py` `CutOps.crash_at` / `crash_when` | positional cuts are calibrated by the same test's own `probe`, and armed only inside `collect_with` (`:239–255`) or `gc.unlink_intent` (`:620–626`); the other cuts are keyed by frame type (`"11"`, `"12"`) or `unlink` | no substituted call site lies in an armed window | no cut needs remapping |
| `test_chassis_correlation.py` `SMALL_SEGMENTS` launcher (`:73–85`) | `segment_max = 1` in **every** writer, startup's included, in real `chassis.py` processes | **yes**: legacy import, every startup closure | Pass, by trace: segment 0 becomes [H1, LEGACY_IMPORT 2] and closes at the legacy closure. It is still collected once a later `C_p` covers seq 2. Labels, identity, counts and "recovery contacts nothing" do not depend on headers. |
| `test_chassis_session.py:273`, `test_chassis_accounting.py:442/485`, `test_chassis_ledger.py`, `test_chassis_durability.py` | session-level injection with no new call site, or writer-level only | no | unchanged |
| every other test (default `SEGMENT_MAX`) | none | no: no segment reaches 16 MiB | byte-identical event traces, so no numeric fault cut or fsync counter shifts |

**Golden values.** C-G2 `[9, 18]` and O2-3 `13 == 8 − 1 + 6` use `Session.start_fresh` with no closure site and no full segment, so they are unchanged.

---

## 8. Finite new fixture matrix: `tests/test_chassis_rotation.py`, 18 nodes (frozen proposal)

Rules:
- temporary roots and default `Caps`;
- every non-default value is labelled **[injected]**;
- `segment_max` for a **startup** writer is injected by a test-local `monkeypatch` of `cp.LedgerWriter.__init__`, the accepted `SMALL_SEGMENTS` pattern of `test_chassis_correlation.py:73–85`, in process and active only around the start under test;
- for an open session, `session.writer.segment_max = 1`, the `test_chassis_gc.py:54` pattern.

Helpers are imported from accepted modules only:
- `test_chassis_recovery_live`: `Root`, `establish`, `resume`, `respond`, `turn7_open`, `frame_after`, `append_raw`, `damaged`, `FaultOps`, `Crash`;
- `test_chassis_bounds`: `frames`;
- `test_chassis_termination`: `make_run`, `reply`.

Three small helpers (`types_after`, `origin`, `counter`) are defined locally, so nothing is imported from SV026's `test_chassis_accounting.py`. No existing test file is modified.

| Function | Params | Expected after the change | On the base |
|---|---|---|---|
| **R1** `test_sv027_every_closed_boundary_rotates_a_full_segment` | `startup-a9-clean`: `establish`; restart **[injected `segment_max = 1`]** | `types_after(P) == ["LEDGER_HEADER"]`, in segment `P.segment + 1`, `first_seq == P.seq + 1`, `prev_chain == P.chain`. Events: fsync of segment s, then `open` of s+1, then `sync_dir(ledger/)`. The counter is `(1, h)`. A second restart at defaults writes nothing. | fails: `[]` |
| | `startup-after-intent`: the TC2 tail of SV026 A7 `after-intent` (`turn7_open`, `damaged(frame_after(INVOKING))`); restart **[injected `segment_max = 1`]** | Every core record lies in the inherited segment, and the header is the start's last record. In `FaultOps.events`, `unlink(RECOVERING)` and then `sync_dir(session/)` precede the new segment's `open`; any IDENTITY rename precedes it too. An `open_segment` wrapper records that RECOVERING and ACKNOWLEDGED were absent at entry. | fails: no header |
| | `legacy-import`: A5 list, start **[injected `segment_max = 1`]** | `types[:3] == ["LEDGER_HEADER", "LEGACY_IMPORT", "LEDGER_HEADER"]`; counter `(1, h)` | fails |
| | `file-edit`: HANDOFF.md edited; `segment_max = 1` after open **[injected]** | `types_after(mark) == ["NOTE_WRITTEN", "LEDGER_HEADER"]` | fails |
| | `generations-and-notice`: 16 pending, a 17th dropped, checkpoint; restart; `segment_max = 1` **[injected]**; `adopt_notes` | `types_after(mark) == ["MSG_APPEND", "LEDGER_HEADER"] × 17` (16 generations and the notice); a restart adopts nothing twice | fails |
| | `drop-in-write_note`: 16 pending; `segment_max = 1` **[injected]** | `write_note(...) is None`; `types_after(mark) == ["RECOVERY", "LEDGER_HEADER"]` | fails |
| | `drop-in-adopt_file_edit`: 16 pending; HANDOFF.md edited; restart; `segment_max = 1` **[injected]** | `["RECOVERY", "LEDGER_HEADER"]` | fails |
| **R2** `test_sv027_one_closure_writes_at_most_one_checkpoint_one_follow_up_and_one_header` | `startup-crossing`: `establish`, 5 says, restart **[injected `records_max = 4`, `segment_max = 1`, `collect=True`]** | After the last say: CHECKPOINT, optionally the GC pair and one follow-up CHECKPOINT, then **exactly one** LEDGER_HEADER, and nothing after it | passes (control for T5) |
| | `generation-crossing`: 3 pending; restart **[injected `records_max = 1`, `segment_max = 1`, `collect=True`]** | Per generation: MSG, then ≤ 2 CHECKPOINTs and ≤ 1 GC pair, then exactly one header. Never two consecutive headers. Headers after the mark == 3. | passes (control for T5) |
| | `header-evaluated-next`: `establish`, 1 say, restart **[injected `records_max = 2`, `segment_max = 1`]**, then the default segment max, then 1 say | after the start, `types_after(P) == ["LEDGER_HEADER"]` (counter `(2, frame(say) + h)`: over, yet no checkpoint at this closure); after the say, `[…, "MSG_APPEND", "CHECKPOINT"]` | fails: `[]` |
| **R3** `test_sv027_no_rotation_inside_a_group_or_with_a_queue` | `drop-inside-group`: 16 pending, `segment_max = 1` **[injected]**, `respond` with one call, `write_note` drop inside the group, then the call answered and `checkpoint` | no LEDGER_HEADER between REQUEST_SENT and the group's last record; exactly one header, after the turn's CHECKPOINT | passes (retained CKG) |
| | `queued-messages`: inside a group, one `queue_message`; the last call answered (group closed, queue non-empty); `segment_max = 1` **[injected]**; `adopt_file_edit` of an edit | no header while the queue is non-empty; after `flush` and `checkpoint`, one header | passes (retained guard) |
| **R4** `test_sv027_a_nonfull_segment_adds_no_event_at_the_new_boundaries` | 1 (defaults): `establish`, 2 pending and a HANDOFF.md edit; restart with `FaultOps`; `adopt_file_edit`; `adopt_notes` | no `open` of any `.svl` and no LEDGER_HEADER after P; the record types equal SV026's sequence | passes (default control) |
| **R5** `test_sv027_rotation_failures_and_crashes_at_the_new_boundaries` | `startup-inherited-fsync-eio`: as R1[startup-a9-clean]; an `open_segment` wrapper asserts `writer.inherited is True` at entry and arms one EIO for the next fsync of segment s | `open_session` raises `PersistenceFailure`; FSYNC_FAILED exists; no segment s+1 file; the ledger is unchanged; the next start is `("A1", "fsync_failed_previous_run")` | fails: DID NOT RAISE (no rotation fsync on the base) |
| | `startup-ledger-fence-eio`: as above, with EIO armed for `sync_dir(ledger/)` once segment s+1 exists (the fence after the header, not continue_after's cached fence) | `PersistenceFailure`; FSYNC_FAILED; s+1 holds one complete header; next start A1 | fails: DID NOT RAISE |
| | `startup-name-lost-is-recreated`: `Crash` at the same fence (process death); then unlink s+1 (simulated M-2 loss of the unfenced name); restart **[injected `segment_max = 1`]** | The restart is A9 with the old segment ending TC0; its closure recreates s+1 with the **same** `first_seq` and `prev_chain`; seqs are contiguous; exactly one header after P | fails: no `Crash` raised |
| | `generations-fence-eio-chassis`: `make_run` first run; a direct session writes 2 notes, checkpoints and closes (the SV026 CB pattern); the second `make_run` has **[injected `segment_max = 1`]** for every writer and an EIO armed for `sync_dir(ledger/)` only while `Session.adopt_notes` is executing | `run.go()` raises `PersistenceFailure`; `run.client.sent == []`; no REQUEST_SENT or INVOKING after the mark; `types_after(mark) == ["MSG_APPEND", "LEDGER_HEADER"]` (g1 only); FSYNC_FAILED exists; next start A1 | fails: DID NOT RAISE (no rotation inside `adopt_notes`, so the fault never arms) |
| | `generations-crash-converges`: 3 pending; restart; `segment_max = 1` **[injected]**; `Crash` at `sync_dir(ledger/)` of the rotation after g1 | Restart at defaults, then `resume`: the generation messages are g1, g2, g3 exactly once each; `adopted_through == 3`; pending `[]`; a further restart adopts nothing | fails at setup assertion "the cut was reached" (no rotation, so no `Crash`) |

Count: R1 7 + R2 3 + R3 2 + R4 1 + R5 5 = **18**.

Pre-fix assertions target behaviour only. They check the presence and position of a header, raised persistence failures and absent effects. They never check a literal segment number, an fsync count or a shifted event index. Each fault is armed by a semantic predicate (a path, `writer.inherited`, a running method), never by "the Nth fsync".

## 9. Retained guards: explicit nodes, 58

| Batch | Nodes | Why |
|---|---|---|
| **G1**: SV026 nodes through the substituted sites, at defaults (**SV026 acceptance now satisfied**; IDs as frozen in `SV-026-bounded-targets.json`) | `tests/test_chassis_accounting.py::test_sv026_origin_and_headers` (4), `::test_sv026_startup_closes_its_unit_with_a_threshold_check` (6), `::test_sv026_adoption_and_drops_are_closed_units` (6), `::test_sv026_no_threshold_checkpoint_inside_a_group_or_with_a_queue` (2), `::test_sv026_a_startup_checkpoint_records_metadata_of_the_recovered_conversation` (1): **19** | the exact SV026 record sequences at all seven sites must be unchanged when the segment is not full |
| **G2**: SV024 `retained_batches` 2, 3, 4, 5, verbatim | 6 + 11 + 2 + 8 = **27** | the startup closure follows pending-GC completion (2), collection and restart under `segment_max = 1` (3; `test_restored_state_…` reaches the adoption rotation), A0/A1 stops relied on by R5 (4), and acknowledgement retirement before the closure (5) |
| **G3**: notes and metadata (subset of SV026 R8) | `tests/test_chassis_notes.py::test_c_n1_a_note_is_adopted_by_the_next_run_once`, `::test_o2_6_a_seventeenth_note_is_dropped_and_reported_after_the_sixteen`, `::test_an_agent_edit_to_handoff_md_is_adopted_once_as_a_new_generation`, `::test_sv021_03_a_crash_between_legacy_import_and_its_note_loses_nothing`, `tests/test_chassis_metadata.py::test_a_startup_failure_before_main_writes_no_end_and_touches_no_memory`: **5** | real `resume_session` through each adoption site and the legacy site; the startup-failure contract |
| **G4**: GC adoption under tiny segments (directly affected; not in an earlier manifest) | `tests/test_chassis_gc.py::test_c_g1_an_adopted_note_is_never_readopted_after_its_records_are_collected`, `::test_o2_1_pending_generations_outlive_their_collected_records`: **2** | new rotation after each adopted generation, then collection |
| **G5**: golden values and placement | `tests/test_chassis_session.py::test_c_g2_direct_says_checkpoint_after_records_8_and_16`, `::test_o2_3_a_threshold_never_checkpoints_inside_a_group`, `::test_rotation_happens_only_at_a_unit_boundary`, `::test_ckg_no_checkpoint_inside_a_group_or_with_queued_messages`: **4** | C-G2/O2-3 unchanged; rotation never splits a group |
| **G6**: promoted from SV024's conditional selectors | `tests/test_chassis_correlation.py::test_recorder_in_loop_identity_survives_collection_and_a_later_interruption`: **1** | the only existing test whose startup writers have a full segment: the new startup and legacy rotations in real `chassis.py` processes, with collection and a killed in-flight request |

SV024 batch 1 (8 durability/namespace nodes) is **not** selected. Every node constructs a `LedgerWriter` directly; none calls `open_session` or `Session`; and `LedgerWriter` is unchanged. SV024's other conditional batch (`test_o2_2_…[a11]`, `…negative_control…`) stays conditional, as accepted. SV025 bounds tests are not selected: the over-threshold branch is the same `checkpoint()` call under both names, and G1's A7 crossing cases cover it cheaply. That avoids test 5's ~5 × 27 MiB peak.

Total: 19 + 27 + 5 + 2 + 4 + 1 = **58**.

## 10. Run plan (implementation phase; nothing run here)

The approved runner, limits unchanged: CPU 120 s / wall 180 s / AS 512 MiB per process; aggregate CPU 50 %, 2 GiB, 64 tasks, nice 15; ELSPETH priority. One literal command per message, awaited.

**Before the runtime edit** (the base with SV026 accepted; the new test file present; runtime unchanged):

| Run | Target | Expected |
|---|---|---|
| B0 | G6 (correlation) | **pass**: a baseline. It was conditional and never executed in SV024 or SV026, so a later failure must be distinguishable from a pre-existing one. |
| D1 | R1[startup-a9-clean] | fail at `types_after(P) == ["LEDGER_HEADER"]` (`[]`) |
| D2 | R1[startup-after-intent] | fail: no header after the retirement |
| D3 | R1[legacy-import] | fail at `types[:3]` |
| D4 | R1[generations-and-notice] | fail: MSG without interleaved headers |
| D5 | R1[drop-in-write_note] | fail: `["RECOVERY"]` |
| D6 | R5[startup-inherited-fsync-eio] | fail: DID NOT RAISE |
| D7 | R5[generations-fence-eio-chassis] | fail: DID NOT RAISE |

Every discriminator collects on the base: the tests use no new API, because the change is internal. None may fail on import, arity, a missing API or setup.

**After the edit** (8 commands, 76 cases):

| Run | Target | Expected |
|---|---|---|
| F1 | `tests/test_chassis_rotation.py` | 18 passed |
| F2 | G1 | 19 passed |
| F3–F6 | G2, SV024 batches 2, 3, 4, 5 | 6, 11, 2, 8 passed |
| F7 | G3 + G4 + G5 | 11 passed |
| F8 | G6 | 1 passed |

Planned: 18 new + 58 retained = **76 case executions in 8 commands**, plus B0 and D1–D7. These are proposed counts, not observed passes. A command that hits the wall cap is split by node list and reported. No cap is raised, and no fixture is weakened to recover a count. An unexpected failure is reported with its output.

## 11. Not claimed; still open

Closing R-D means **every closed unit boundary evaluates rotation**. It does not bound a segment:
- **What may be appended to a full segment before its rotation:**
  - the rest of the current unit, whose maximum is unresolved (P1: U_b of a turn, a startup unit, an adoption unit);
  - at the closure, a threshold CHECKPOINT (canonical maximal frame 19,978), a GC_INTENT (body up to `MAX_LEDGER_BODY`), a GC_DONE and one follow-up CHECKPOINT;
  - at startup, the whole recovery core appended to an inherited full segment;
  - under a crash loop that dies before the startup closure, a repetition of that per start (L2).
- `MAX_SEGMENT_READ = 2 × SEGMENT_MAX` stays a chosen read bound. The slack argument is **not proved**; C5 only removes the comment's unproved "one unit".
- Unchanged and unresolved:
  - `T_origin`;
  - the true older previous-base terms (P4);
  - current shapes against literal maxima (P5);
  - `unmeasured` partial I/O;
  - arbitrary partial-I/O and crash-loop terms;
  - RSS, wall-clock and total startup I/O;
  - none of the four §1.4.7 inequalities, nor U_r/U_b.
- No canonical literal, generator, oracle, history size or representation, previous-file preservation, acknowledgement or bootstrap loss semantics, or H/T/Q/pump/history policy is revised.
- An existing inconsistency is outside SV027 and is recorded, not changed. `open_segment` writes no marker on an `O_EXCL` open failure, because no byte is in doubt (`test_an_open_failure_writes_no_marker_because_no_byte_is_in_doubt`). But `Session._fail` then attempts one, because the writer recorded none. This applies equally to every existing `unit_end` rotation.
