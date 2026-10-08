# SV-026 design: replay-work accounting and closed-unit threshold checks

**Status: design for independent review (Astra). Nothing implemented, no test run.** Base `2ce8bad76c23a86d0962df90525c0c1509bbd126`. SV016–SV024 runtime accepted; the test-only SV025 correction is under review, and its corrected `RECEIPT.md`/`STATUS.md` are the evidence used here, not the withdrawn first-round claims. Scope: `SV-026-accounting-preflight.md`. Canonical: SV-015 v2 §1.4.1 (units, CKG, threshold) and §1.4.7 (the quantity).

This design implements behavior the canonical text already requires:

- the outstanding frame-plus-replay-blob work since the newest checkpoint survives a restart;
- live units are charged the same quantity that replay performs;
- the threshold is evaluated after each closed unit, including startup, adoption, note drops and GC.

It does **not** revise U_r/U_b or the four §1.4.7 inequalities. It does not cap accepted histories or change previous-file preservation, and it does not touch canonical literals or the generator, the true `prev` tuple, or the H/T/Q/pump/history policies. Correct accounting is not a proof of any numeric bound (§9).

---

## 1. The quantity

### 1.1 Definition

For one ledger record `r` applied by a `Replay` instance:

```
W(r) = (0, 0)                                    if r.type ∈ {CHECKPOINT, LEDGER_HEADER}
W(r) = (1, r.length + Σ len(b))                  otherwise
         where b ranges over the non-None byte strings that Replay.read_blob
         returned to the reducer while apply(r) ran
```

- `r.length` is the whole frame (`49 + plen + 66`). It is `Record.length` from `LedgerWriter.append` (live) or from `parse_record` (read back). Both equal the frame bytes on disk.
- Blob bytes are what the reducer actually received, after `BlobStore.get`'s SHA-256 check (`chassis_persistence.py:1079–1086`). No declared length is used: not `NOTE_WRITTEN.bytes`, `DONE.original_bytes`/`stored_E` or `conv.bytes`. Nothing is read for measurement only, because the reducer already reads these bytes to rebuild memory.
- Each (record, blob) is counted once. No reducer handler reads the same blob twice for one record (inventory §2).

**Counter invariant ACC.** In every unbroken `Session`, `(since_records, since_bytes) = Σ W(r)` over the records with `seq > C_n.seq`. `C_n` is the newest CHECKPOINT; with no checkpoint, every record counts. `W` is measured by the reducer that produced this process's memory: live for records this process wrote, replayed for records it recovered.

### 1.2 What is excluded, and why

| Excluded | Reason | Bounded by |
|---|---|---|
| `C_n`'s own frame | The writer already resets after CK6 (`chassis_session.py:619`), so "since the newest checkpoint" excludes it live. Startup now excludes it too (it currently counts it, `chassis_startup.py:1103` with `suffix` from `:1185`). | one frame per interval |
| `LEDGER_HEADER` frames | `open_segment` writes them outside `_commit` (`chassis_persistence.py:1204–1242`); the live counter has never charged them. Startup currently counts them through `len(suffix)`. Excluding them on both sides keeps the accepted C-G2 oracle (`test_c_g2_direct_says_checkpoint_after_records_8_and_16`, positions [9, 18]) unchanged. | one per segment opened within the interval; rotation needs ≥ `SEGMENT_MAX` frame bytes per segment |
| Retained-only blobs: TURN_RESPONSE `original_blobs`, NOTE_WRITTEN blobs, LEGACY_IMPORT `note.blob`, CHECKPOINT `blobs_live` | Named by `record_refs` for GC (`chassis_replay.py:610–630`) but never opened by the reducer | — |
| Foreign note adoption (`MSG_APPEND{note, foreign: true}`) | The reducer does not open the blob (`chassis_replay.py:455`) | — |
| Reads outside `Replay.apply` | `conversation.json`/`.prev.json` (`_classify_base`, `_retained_prev`); segment scans (`open`, rescan, `_collect`, `_consume_ack`, quarantine, witness); `plan_recovery`'s DONE reads (`chassis_persistence.py:853`); A8's foreign check (`chassis_startup.py:1314`); witnessed verification replay (`:650–658`). None are replay work of the suffix (SV025 §7). | — |
| Physical bytes of a blob that fails its hash | `get` returns None, so the reducer receives nothing (decision D3) | ≤ `BLOB_READ_MAX` per DONE record |
| fsyncs and fences (`sync_inherited`, `_fence_intent_inputs`) | durability, not reads | — |

Excluding `C_n` and headers from the counter is a counter convention only. Whether the canonical inequality should carry terms for them (SV025 §3 "C_n's frame") is left to the separate bounds work (§9).

### 1.3 Missing and damaged blobs

- **DONE** (`_on_done`, `chassis_replay.py:412`) tolerates `None` and appends the lost-payload text. W is then the frame only.
  - **L1.** If a DONE blob is damaged or deleted between the live write and a restart, the restart charges `len(blob)` less than the dead process did.
  - If identical bytes are later re-put by another record (blobs are content-addressed), a still later replay reads them again. It is then charged more than the earlier restart was.
  - The gap is at most the stored result (`CAP_RESULT`) per such DONE record. It exists only under the corruption fault model. It is stated, not hidden.
- **Every other replay-opened blob** goes through `_blob`, which raises `ReplayMismatch` on None. Startup stops with `replay_mismatch`; the live session breaks with `SessionInvariant`. No counter exists in that case, and none is guessed.

---

## 2. Inventory: every production blob read inside `Replay.apply`

All are reached through `self.read_blob` (`chassis_replay.py:284`). There is no other read in the reducer.

| Record | Handler (`chassis_replay.py`) | Call | Missing/damaged |
|---|---|---|---|
| DONE | `_on_done` :408–419 | `read_blob(payload.blob)` :412 | lost text, W = frame |
| MSG_APPEND with `blob` (text > 4,096 bytes) | `_on_msg_append` → `_text` :309–312 | `_blob` :291 | ReplayMismatch |
| MSG_APPEND `note`, not foreign | `_on_msg_append` :455–456 | `_blob(entry.blob)` | ReplayMismatch |
| MSG_APPEND `note`, foreign | :455 | none | — |
| HISTORY_REPLACED | :463–470 | `_blob_list(new_blob)` | ReplayMismatch |
| EXTERNAL_EDIT / LEGACY_IMPORT / LEGACY_REIMPORT with `blob` | `_switch_base` :472–479 | `_blob_list(blob)` | ReplayMismatch |
| EXTERNAL_DELETE; switches without `blob` | :486–489 | none | — |
| RECOVERY `conversation_adopted` (A10) | `_on_recovery` :578–587 | `_blob_list(detail.blob)` | ReplayMismatch |
| every other type | — | none | — |

The production `Replay` constructions are: `Session.start_fresh` (`chassis_session.py:178`), `_replay` (`chassis_startup.py:1519–1523`) and `_previous_base` (`:1282`). All three pass a `BlobStore.get` with `BLOB_READ_MAX = 64 MiB`.

### 2.1 Every writer charge today, and after

| Call site | Record | Charge today (`replay_bytes`) | After: measured W |
|---|---|---|---|
| `record_result` `chassis_session.py:326–340` | DONE | `len(data)` | frame + bytes read back (= `len(data)` when intact) |
| `_append` blob branch :383 | MSG_APPEND | `len(data)` | same, measured |
| `adopt_notes` :498 | MSG_APPEND note | `entry["bytes"]` (**declared**), 0 if foreign | measured; 0 blob if foreign |
| `replace_history` :520–525 | HISTORY_REPLACED | `len(data)` | measured |
| `_start_legacy` `chassis_startup.py:920` | LEGACY_IMPORT with list | `len(data)` | measured (note blob stays excluded) |
| `_recover` ADOPT :1105–1112 | RECOVERY conversation_adopted | `len(data)` | measured |
| `_finish_case` :1320 | EXTERNAL_EDIT / LEGACY_REIMPORT | `len(data)` | measured |
| all other `_commit` calls | — | 0 | frame only (the reducer opens nothing) |
| `LedgerWriter.open_segment` (create, rotate, `continue_after` reuse) | LEDGER_HEADER | not committed | excluded (§1.2) |

The manual parameter is not wrong at any current call site. It is removed so that no future call site can diverge from what replay does, and so that the note adoption charge stops trusting a declared size.

---

## 3. Source-to-change map

| # | File:lines | Change |
|---|---|---|
| C1 | `chassis_replay.py:277–357` | `Replay` gains `work_records`, `work_bytes` (lifetime sums of W) and `_received` (blob bytes for the record being applied). `_read(sha)` wraps `self.read_blob` and adds `len(data)` when not None. `_blob` (:291) and `_on_done` (:412) call `_read`. `apply` resets `_received`, runs the handler, then adds W unless the type is in `UNCHARGED = {"CHECKPOINT", "LEDGER_HEADER"}`. A handler that raises adds nothing. `read_blob` stays a public attribute, unchanged in signature. |
| C2 | `chassis_session.py:216–235` | `_commit` drops `replay_bytes`. It adds the replay's `work_*` delta around `apply`. Call sites :339, :383, :498, :524 lose the argument. |
| C3 | `chassis_startup.py:920, 1111, 1320` | Same argument removal. |
| C4 | `chassis_startup.py:1099–1103`; `_Decision.suffix_records` :1397 | `session.since_records, session.since_bytes = replay.work_records, replay.work_bytes`. `replay` here is `decision.replay` after the `extra` loop (:1081–1088). Remove `suffix_records` (its only use). |
| C5 | `chassis_session.py` new `_over()` / `threshold_boundary()`; `unit_end` :536–543 | `_over()` is the existing comparison. `threshold_boundary()` uses the same guards as `unit_end` (broken, open group, queue) and checkpoints if `_over()`. Unlike `unit_end` it never rotates (decision D7). `unit_end` itself is unchanged in behavior. |
| C6 | `chassis_startup.py:1137` (before `return`) and `:925` (`_start_legacy`, before `return`) | `session.threshold_boundary()` (§4.1). |
| C7 | `chassis_session.py:424–426` (write_note drop), :469–471 (file-edit drop), :479 (after file-edit NOTE_WRITTEN), :498 (each adopted generation), :502 (drop notice) | `threshold_boundary()` after each (§4.2). |
| C8 | `chassis_session.py:568–623` (`checkpoint`), :625–675 (`_collect`) | `_collect` returns True iff it committed GC_INTENT/GC_DONE. `checkpoint(ended=None, *, follow_up=False)`: when GC committed records and `_over()`, it writes exactly one follow-up checkpoint with `follow_up=True` and the **same `ended`**. A follow-up never collects. Only under decision D4 = G2 (§5). |
| C9 | docstrings: `chassis_session.py` module (:25–28) and `_collect` (:633); `chassis.py:1119–1131` (`run`: "deliberately, no checkpoint" before main) | State that startup may write one threshold checkpoint after its transaction, and that a crossing GC unit gets one non-collecting follow-up. Text only. |

Nothing else changes. That includes: `LedgerWriter`, `BlobStore`, `plan_recovery`, `derive_core`, `_classify_base`'s candidate order, GC planning/validation, quarantine, IDENTITY, the acknowledgement code, `envelope`, the caps and every constant.

---

## 4. Algorithms

### 4.1 Startup reconstruction and the startup unit

```
_recover (only C4 and C6 differ from today):
  ... plan_recovery, intent checks, _classify_base(...)      # candidates each own a Replay
  decision.replay                                            # exactly one is kept:
      newest base:   _replay(base, C_n.state, suffix)        # suffix = seq > C_n.covers
      previous base: Replay(middle.messages, C_n.state).apply(suffix)   # a fresh instance; the
                     interval (C_p.covers, C_n.covers] is applied to another instance (`middle`)
      lenient:       _replay([], C_n.state, suffix)          # only built when strict is None
      no checkpoint: _replay([], fresh, p0)
  ... RECOVERING written (if a tail), quarantine, rescan, continue_after
  for r in extra: replay.apply(r)                            # an earlier attempt's readable records
  session = Session(..., replay)
  session.since_* = replay.work_*                            # C4: suffix after C_n + extra, by ACC
  commit core[len(extra):]                                   # each _commit charges W
  _finish_case(...)                                          # switch / delete / notices / A14 binding
  sync extras' segments; retire carrier and RECOVERING       # both fenced (_remove: unlink + fsync session/)
  reserve IDENTITY
  session.threshold_boundary()                               # C6: the startup unit closes here
  return Opening(...)
```

Why each property holds:

- **No multiplication across candidates.** The counter reads only `decision.replay`'s accumulators. A rejected candidate is either a separate instance (`middle`, a lenient replay never built) or a stop. In the stop case no session or counter exists.
- **Previous-base replay.** The interval's work is in `middle` and is excluded. The counter is the newest suffix only, which is what the next threshold governs. The interval length is P4, which this design does not address (§9).
- **The C_n frame** is applied but not charged (`UNCHARGED`). This replaces the current +1.
- **Extras** are charged once, on the instance the session continues with. Their comparison to `core` (`:1083`) is unchanged.
- **Newly committed recovery records** (GC_DONE, RECOVERY_ACK, SYNTH/UNRUN, RECOVERY, ADOPT, switches, notices, `conversation_restored`) are charged by `_commit`.
- **No zero fallback.** `from_wire` failure, `ReplayMismatch` and every other stop leave no session. A `Session` is constructed only after its replay succeeded, and its counter comes only from that replay.
- **Post-collection suffix.** GC never removes a record with `seq > C_p.covers` or a blob that a retained record names. GC deletion therefore never changes W for the suffix. A DONE blob lost to an external fault is L1.

**Why the startup unit closes only at the end.** A checkpoint is never written while RECOVERING exists. A checkpoint written under an intent would be an `extra` record of that intent at the next start. `_classify_base` takes `newest` from `p0` only, so the freshly installed `conversation.json` would no longer match the binding and would be misread as an external edit. A witnessed recovery would stop with `recovery_intent_mismatch` (SV023-03, `:1089–1091`).

The check therefore follows, in this order:

1. the extras' segment syncs (SV023-04);
2. the carrier retirement and the RECOVERING removal, both durable through `_remove`'s `sync_dir`;
3. the IDENTITY reservation.

It also runs after the SV024 fences, the quarantine admission and the pending-GC completion, which all happen earlier in `_recover`. `checkpoint()` itself still calls `sync_inherited` first (`chassis_session.py:577`).

The threshold checkpoint is an ordinary checkpoint. `_retained_prev` uses `decision.checkpoints`, so previous-file binding follows the SV021-02 rule. `_collect` runs if `collect=True`; by then RECOVERING and (when consumed) ACKNOWLEDGED are gone, so its GC_BLOCKERS check sees only real blockers. A TC4 acknowledgement whose receipt does not exist yet keeps ACKNOWLEDGED, so GC is refused with `gc_refused` as it is today.

`_start_legacy` (A4/A5) closes the same way, after `_consume_ack`. CKG holds: `derive_core` closes the open group (`chassis_startup.py:1580–1594`), and nothing is ever queued at startup. If a group were somehow still open, `threshold_boundary` would return without checkpointing, as `unit_end` does.

### 4.2 Adoption and drop units (C7)

```
write_note:        if pending ≥ 16: _drop_note(); threshold_boundary(); return None   # skipped inside a group
adopt_file_edit:   drop  -> _drop_note();  threshold_boundary()
                   adopt -> NOTE_WRITTEN;  threshold_boundary()
adopt_notes:       for each pending generation: MSG_APPEND{note[, foreign]}; threshold_boundary()
                   if notes_dropped: notice MSG_APPEND; threshold_boundary()
```

A checkpoint between two adopted generations is consistent. `adopted_through`, `pending` (with `foreign` marks), `mirror_sha256s` and `notes_dropped` are all checkpoint state (§1.4.2, SV021-10), and the next resume continues with the remaining generations. Inside a tool group (a `handoff` in a tool that hits the 17th-note drop) the guard skips the check. The group's closure is then followed by the unconditional turn-end or run-end checkpoint (`chassis.py:822`, `:1251`).

### 4.3 Units that are already closed (no change)

| Unit | Closure today | Source |
|---|---|---|
| direct say/note | `unit_end` | `chassis_session.py:395` |
| direct `write_note` (no group) | `unit_end` | :444–445 |
| turn, including its flush | unconditional checkpoint at turn end; on every exception path `close_group` then `checkpoint(ended)` | `chassis.py:818–822`, `:1248–1251` |
| `set_history` | immediate checkpoint | `chassis_session.py:526` |
| recap fold | `unit_end` | `chassis.py:993–994` |
| `RUN_END` | none: the process's last record; the next start's §4.1 check covers it | `chassis.py:1263` |

`flush` gets no check of its own. A checkpoint always follows it, so a check would only add a redundant checkpoint.

---

## 5. A GC unit that crosses the threshold

GC_INTENT and GC_DONE are committed after the reset (`chassis_session.py:619`, :662, :667) and are charged into the new interval. At defaults the GC unit cannot cross by itself:

- it is 2 records;
- GC_INTENT's body is refused above `MAX_LEDGER_BODY` (`chassis_gc.py:241`), so its frame is ≤ 49 + 1,048,576 + 66;
- the counter is 0 just before it;
- 2 < 256, and the GC unit stays under 8 MiB. This is static arithmetic, not executed.

A crossing is reachable only with an injected `records_max ≤ 2` or `bytes_max` below the GC frames.

The canonical text says a GC is a unit and that the threshold is checked after each unit. The CK6 row lists "GC (optional), next unit". Re-checking after GC with ordinary semantics could chain checkpoint → GC → checkpoint indefinitely under a tiny threshold. That is a tension in the text, not a forced contradiction. **Decision D4 (for review; not silently selected):**

- **G2 (recommended): one non-collecting follow-up.**
  - If `_collect` committed records and `_over()`, `checkpoint` writes one follow-up checkpoint at once, with `follow_up=True`. The follow-up never collects, so it adds no GC unit and cannot re-enter. At most two checkpoints result per call.
  - The follow-up carries the same `ended` (the final checkpoint's `run.json.ended` must survive).
  - `checkpoint` returns the follow-up's record.
  - This satisfies "check after every unit", because the GC after a checkpoint is optional.
  - The follow-up's `prev` is the first checkpoint, which is bound and newer (SV021-02). Deferred items stay eligible for the next ordinary checkpoint's batch.
- **G1: today's behavior, documented.** No check after GC. The GC unit's charge is evaluated at the next unit's boundary, so the overshoot is "one unit + one GC unit". This needs no code, but it is a stated deviation from §1.4.1's wording.

The tests in §7 cover G2. If G1 is chosen, node A9 is replaced by the G1 node given there, and C8 is dropped.

---

## 6. Preserved invariants and failure behavior

| Invariant | How it is preserved |
|---|---|
| CKG (no checkpoint in an open group or with a queue) | every new check goes through the `unit_end` guards; `checkpoint` keeps its own refusal (:571) |
| RECOVERING / intent semantics, extras comparison, witnessed exact core | the startup check runs after both are retired durably (§4.1); no record is added under an intent |
| Acknowledgements, receipt sync, carrier retirement order (SV023-03/-04) | unchanged; the check comes after them |
| IDENTITY reservation before any request | unchanged; the check comes after it; a checkpoint never reserves or sends |
| Inherited-byte fence (SV024) | `checkpoint` → `sync_inherited` first, as today |
| Pre-intent fence and the maintenance cut | unchanged: the new checkpoint comes after the first recovery record and after RECOVERING removal |
| Quarantine pre-admission | unchanged; checkpoints do not quarantine |
| Pending GC ordering (GC_DONE first, before any blob of this start) | unchanged; any startup threshold GC is a new intent after it |
| Previous-file binding (SV021-02), the GC floor on `checkpoints` | `_retained_prev` with `decision.checkpoints`; `_collect`'s pruning unchanged |
| One failure boundary | a startup threshold checkpoint's `PersistenceFailure` breaks the session (FSYNC_FAILED attempted), leaves `open_session` like every other startup persistence failure, and the run ends 44 |

**Crash cuts of the new checkpoints.** They are the ordinary CK1–CK6 rows of §1.4.10. A death before CK4 gives A9 or A9t: the counter is reconstructed and the check fires again. A death after CK4 and before CK6 gives A10: ADOPT is charged and the check fires again. Each start writes at most one threshold checkpoint, plus one follow-up under G2. **L2:** repeated deaths in the CK4–CK6 window each add an ADOPT record carrying a conversation blob of up to 64 MiB. That accumulation is the crash-loop/unit-size question of §9, not a recursion.

---

## 7. Finite test manifest (proposed; frozen only after review)

Rules:
- temporary roots only; default `Caps` everywhere;
- threshold values other than the defaults are labelled **[injected]**;
- one runner process per command: the approved runner (CPU 120 s / wall 180 s / AS 512 MiB), one literal command per message, awaited, from the repository root;
- no broad suite; the runner was not read or changed.

**Independent oracle `O(lo, hi)`.** From SV025's `test_chassis_bounds.py` helpers:
- frame lengths come from `frames(root)`, a byte walk of `49 + plen + 66`;
- blob bytes come from `Observer.reads` of kind `blob`, attributed to the seq whose `Replay.apply` was running;
- the oracle is summed over `lo < seq ≤ hi`, excluding walked types `0d` (CHECKPOINT) and `01` (LEDGER_HEADER).

The counter never feeds the oracle. The damaged-blob case shows on purpose where the two differ.

### 7.1 New file `tests/test_chassis_accounting.py` (34 nodes)

| Node | Params | Expected after the fix | Pre-fix |
|---|---|---|---|
| A1 `test_sv026_live_counter_equals_observed_work_per_unit_kind` | `say-inline`, `say-blob` (6,000), `done-blob` (one tool result of 5,000 chars, before the turn checkpoint), `note-written`, `note-adopted`, `original-retained-only` (content at cap+1) | after `establish` and an A9 start with the observer, one unit; `since == O(C_n.seq, last)`; blob part 0 for `say-inline`/`note-written`/`original-retained-only` | passes (**retained regression, not discriminating**: the old explicit charges were equal) |
| A2 `test_sv026_restart_reconstructs_the_counter_exactly` | `say-blob-x2`, `done-blob` (`partial_turn` 4 steps), `done-blob-missing` (its blob file deleted before the restart), `done-blob-damaged` (overwritten, same length, other bytes), `note-adopted` (`adopt_notes`, then death), `foreign-note-adopted` (SV021-10 setup of `test_sv021_10_the_foreign_mark_is_checkpoint_state_until_consumed`, then `adopt_notes`, then death), `history-replaced-cut` (`Crash` at `install_conversation` inside `replace_history`'s checkpoint), `original-retained-only` | process 1's final counter `c1` equals its own O. The restart's counter equals O over its own applies and commits. For intact cases, restart counter == `c1` + the W of recovery records. `missing`: restart charge = `c1 − len(blob)`, the observer logs no read. `damaged`: counter = O − len(blob), because the observer logged a read that failed its hash. `foreign`: no blob read attributed to that seq. | fails: `since_bytes == 0` and `since_records` +1 at restart |
| A3 `test_sv026_repeated_restarts_never_double_count` | 1 | `say-blob-x2`, death, then three A9 starts each with a new observer: identical counters, each == O, ledger unchanged | fails (bytes 0) |
| A4 `test_sv026_previous_base_recovery_counts_only_the_newest_suffix` | 1 | `establish` (A, then B with prev A), two blob says, death, `conversation.json` damaged → A14 via `_previous_base`. The observer shows `(A.covers, B.covers]` applied. The counter equals `O(B.seq, last)` (suffix + A14 notice + `conversation_restored`), not the interval. | fails |
| A5 `test_sv026_recovery_extras_from_an_earlier_attempt_are_counted_once` | 1 | The SV025 `after-first-record` TC2 cut is rebuilt from the shared helpers (`Root`, `establish`, `partial_turn`, `FaultOps`, `Crash`); `test_chassis_recovery_live.py` is not modified. The restart applies the readable SYNTH as an extra once. Counter == O(C_n.seq, last), and `applies` contains that seq exactly once. | fails (+1, bytes 0) |
| A6 `test_sv026_ledger_headers_and_the_newest_checkpoint_are_never_charged` | 1 | fresh start (header seq 1) + 3 says → `since_records == 3`; `segment_max` lowered so that `unit_end` rotates; the header is not charged; death; the restart suffix walks C_n + a `01` frame, and the counter equals the pre-death value | fails at restart (counts C_n and the header) |
| A7 `test_sv026_startup_evaluates_the_threshold_after_its_transaction` | `crosses-bytes` (4×6,000 written at defaults, death, restart **[injected bytes_max 20,000]**), `crosses-records` (5 says, restart **[injected records_max 4]**), `below-control` (restart **[injected bytes_max 10⁹]**), `after-intent` (TC2 tail + `collect=True`, **[injected records_max 1]**), `legacy-start` (A5 list of 30,000 bytes, **[injected bytes_max 20,000]**) | Crossing cases: the ledger ends with that start's CHECKPOINT and `since == (0, 0)`. `after-intent`: `FaultOps.events` show `unlink RECOVERING` + `sync_dir session/`, then the IDENTITY rename, then the conversation temp, then the CHECKPOINT append; no `gc_refused` naming RECOVERING. Control: nothing written. | crossing cases fail (no checkpoint); control passes |
| A8 `test_sv026_adoption_and_drop_are_closed_units` | `each-generation` (3 pending, **[injected records_max 2]** after open), `file-edit` (**[injected records_max 1]**), `drop-in-write_note` (16 pending), `drop-in-adopt_file_edit`, `drop-notice`, `drop-inside-group-control` | `each-generation`: ledger order MSG(g1), MSG(g2), CHECKPOINT (state: `adopted_through` 2, pending [g3]), MSG(g3); a restart adopts nothing twice. Drop cases: CHECKPOINT immediately after the RECOVERY or notice. Control: no checkpoint until the group closes. | first five fail; control passes |
| A9 `test_sv026_a_crossing_gc_unit_gets_one_non_collecting_checkpoint` *(G2 only)* | `records` (**[injected records_max 2]**, `collect=True`, one eligible blob), `final-ended` (same, via `checkpoint(ended=…)`), `below-control` (defaults) | Tail: CHECKPOINT, GC_INTENT, GC_DONE, CHECKPOINT, and no GC after the last. The returned record is the follow-up. `run.json.ended` is kept. Control: one checkpoint + GC, `since == O` (2 GC frames). | `records`/`final-ended` fail; control passes |
| A10 `test_sv026_no_threshold_checkpoint_inside_a_group_or_with_a_queue` | `live-group` (**[injected records_max 1]**, a turn with queued messages), `startup-closes-group-first` (`partial_turn` 4 steps, restart **[injected records_max 1]**) | no CHECKPOINT between REQUEST_SENT and the flush's last MSG_APPEND; at startup the closure records precede the CHECKPOINT | `live-group` passes (retained invariant); the other fails |

Count: 6 + 8 + 1 + 1 + 1 + 1 + 5 + 6 + 3 + 2 = **34**. Under G1, A9 becomes `test_sv026_gc_records_are_charged_and_checked_at_the_next_unit` (2 params: `records`, `below-control`), for 33.

### 7.2 `tests/test_chassis_bounds.py` (SV025): moved cuts, with the precise behavior change each

Node count is unchanged at 16. Tests 1, 2a–2e and 3 are unchanged; test 3's `("A9", 0)` still holds because the C_n frame is excluded on both sides.

- **Test 4: structural expectation replaced.** The function is renamed `test_sv025_a_restart_carries_outstanding_suffix_bytes`. The old function stays the pre-fix discriminator (run P1 below) and is then replaced.
  - First restart: `("A9", 0, 0)`.
  - Two messages give `carried` (SV025 executed: 12,428).
  - Second restart: `(since_records, since_bytes) == (2, carried)`, which equals the outstanding work after C_n's frame.
  - The next message does not checkpoint (3 units < 20,000). The following one does: the walked total at the crossing lies in `[20,000, 20,000 + one unit)`.
  - A third start shows a newer C_n and `(0, 0)`.
  - **[injected bytes_max 20,000]**, as before.
- **Test 5: cut moved to the real pre-checkpoint crash window.** The counterexample is kept.
  - First start: an A11 start whose threshold checkpoint dies at CK2 entry. `Crash` comes from a monkeypatched `cp.install_conversation`, i.e. after EXTERNAL_EDIT's fsync returned and before any checkpoint byte. A `Session.checkpoint` wrapper logs the counter at entry: `(1, EE frame + 28,311,552) ≥ RECOVERY_BYTES_MAX`. The live reducer still re-reads the blob once.
  - Second start: A9t. For `seq ≤ edit`, the applies and the single 28,311,552-byte blob read are as before, with suffix `(2, TARGET, TARGET, 1)`. **`suffix.total > NEWEST_BYTES_LT` still holds.** The counter at the threshold checkpoint's entry equals `suffix.total − walked[C_n.seq].length`.
  - Changed expectations:
    - the start now writes one CHECKPOINT ("wrote nothing" becomes "wrote exactly one CHECKPOINT after `edit`");
    - the conversation reads are the two classification reads followed by `_retained_prev`'s two reads (both attributed None);
    - the segment reads are still 2 whole-segment scans;
    - the final counter is `(0, 0)` (it was `(2, 0)`).
  - Memory: about 5 copies of 27 MiB at peak. If the AS 512 MiB cap is hit, that is reported. The cap is not raised.
- **Test 6:** one assertion. `since_records == MESSAGES + 2` becomes `MESSAGES + 1`, because C_n is no longer counted. The 730-record witness, the intervals 3/242/242/242, `prev = A` and the file equality are unchanged. The startup check does not fire (1 record).

### 7.3 Run plan for the implementation phase

The runner stops at the first failure, so pre-fix discriminators run one node at a time.

**Before the runtime change**, with the new test file written and the bounds file still at its SV025 state. Each is expected to FAIL at the stated assertion:

- **P1** A2[say-blob-x2] at `since_bytes`
- **P2** A6 at restart `since_records`
- **P3** A7[crosses-bytes]: no checkpoint
- **P4** A8[each-generation]: no checkpoint between generations
- **P5** A9[records] (G2)
- **P6** A10[startup-closes-group-first]
- **P7** the rewritten test 5 node, run against the base: no `Crash` raised, because there is no startup checkpoint

**After the change**, each expected to pass in full:

| Run | Target | Expected |
|---|---|---|
| R1 | `tests/test_chassis_accounting.py` | 34 passed |
| R2 | `tests/test_chassis_bounds.py` | 16 passed |
| R3–R12 | `test_chassis_session.py`, `test_chassis_replay.py`, `test_chassis_notes.py`, `test_chassis_adoption.py`, `test_chassis_checkpoint.py`, `test_chassis_gc.py`, `test_chassis_recovery_live.py`, `test_chassis_acknowledgements.py`, `test_chassis_namespace.py`, `test_chassis_recovery.py` | each passes in full (retained regressions) |

Any file that exceeds the caps is split by node list, never re-capped. Any failure is reported with its output. No fixture may be weakened to hide an unresolved bound.

---

## 8. Smallest implementable subset

- **S1** Accounting: C1–C4. This is the core of the preflight. With S1 alone, A1–A6 pass.
- **S2** Startup unit closure: C6 + C5. Needed for A7 and A10.
- **S3** Adoption and drop closures: C7 (uses C5). Needed for A8.
- **S4** GC crossing: C8, only if D4 = G2.
- **S5** Docstrings: C9.

S1–S3 and S5 are the required minimum. S4 depends on D4. Test changes in `test_chassis_bounds.py` follow S1 (test 6, and test 4's first half) and S2 (test 4's crossing, test 5).

## 9. Decisions for review, and what stays unresolved

| ID | Decision | Recommended | Alternative and its cost |
|---|---|---|---|
| D1 | `C_n`'s own frame | excluded on both sides | included on both sides: the writer starts each interval at (1, C_n.length); C-G2 positions become [9, 17], and SV025 test 3 shifts |
| D2 | LEDGER_HEADER | excluded on both sides | charged on both sides: needs a writer hook; C-G2 becomes [8, 17]; GC tests with `segment_max = 1` change their counters |
| D3 | damaged/missing blob | validated bytes the reducer received | physical attempted bytes: needs a `BlobStore.get` variant that reports the attempt size |
| D4 | GC crossing | G2 | G1 (§5) |
| D5 | adoption granularity | one closed unit per generation, per file edit and per drop | one check after the whole of `adopt_file_edit` + `adopt_notes` (overshoot up to 16 notes + notice) |
| D6 | where startup closes | the end of `open_session`'s success paths (§4.1) | in `chassis.run` after `open_session`: misses direct callers and keeps tests blind to it |
| D7 | new boundaries | check only, no rotation | `unit_end` with rotation: new rotation points shift segment numbering in GC tests with `segment_max = 1` |

**Not resolved by SV026** (separate contracts):
- P1: a per-unit byte maximum covering the startup unit, which can carry a 64 MiB switch or ADOPT blob, plus adoption units;
- P4: the number of intervals between the actual `prev` and `C_n` (SV025 test 6);
- P5: the current serializer shapes against the literal maxima;
- whether the canonical inequalities carry terms for `C_n`'s frame and headers (§1.2);
- L1 (DONE blob loss and re-materialization) and L2 (crash-loop ADOPT accumulation);
- RSS, wall-clock and total startup I/O.

None of the four §1.4.7 inequalities becomes proved. SV025's refutations stand: newest bytes in the crash window (test 5, moved, not removed) and previous records (test 6).
