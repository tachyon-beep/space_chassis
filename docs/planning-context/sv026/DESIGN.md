# SV-026 design (revision 1): replay-work accounting and closed-unit threshold checks

**Status: revised design for independent review. Not implemented. No test was run.**

This revision answers `SV-026-Astra-design-review.md` (SV026-01 to SV026-04), which reviewed design head `10eed7fbe18b044bf29becd29f3e85ae67f4bb60`. Provenance:

- Base runtime `2ce8bad76c23a86d0962df90525c0c1509bbd126`; SV016–SV024 runtime is accepted.
- SV025 Correction 1 is **accepted as evidence** at `1ede8a3fca71e515cce047f5deba9f9bd27bb7a9`. The previous draft called it "under review", which is stale. Its exact default-constant counterexamples and its synthetic, legal-domain and emitted distinctions are kept as they are.
- Scope: `SV-026-accounting-preflight.md`. Canonical: SV-015 v2 §1.4.1, §1.4.7 and §1.4.8.

What changed from the reviewed draft, and why:

| Finding | Draft | This revision |
|---|---|---|
| SV026-01 | All LEDGER_HEADERs were excluded, justified by test positions | Only the **interval origin** is uncharged: the newest CHECKPOINT's own frame, or the genesis header seq 1 when no checkpoint exists. Every later header is charged, live through a writer claim list and on restart through replay. C-G2 positions [9, 18] still hold, because that fixture has no later header (§1.3). |
| SV026-02 | Only validated payload bytes were charged | Blob work is the bytes **obtained** by the existing bounded read before the hash decision. `BlobStore.fetch` reports outcome and count with no second read. Accepted, wrong-hash and over-limit probe bytes are charged. Missing files read nothing. Failed I/O is a counted, explicitly unmeasured case (§1.4). |
| SV026-03 | The startup checkpoint called `Chassis._meta_fields` while it still read the empty pre-session list | `meta_source(messages)` receives the list being checkpointed. `Chassis._meta_fields(messages=None)` uses it. A real-Chassis fixture is added. Every callback at that boundary is audited (§5). |
| SV026-04 | Some expectations were wrong and the guard runs were whole modules | Expectations are corrected. Reset/lifetime, post-GC parity, follow-up crash and fence compositions, header and read-outcome discriminators are added. Guard batches are frozen node lists that reuse the accepted SV024/SV025 manifests (§8). |

Retained as Astra found them sound:
- selected-replay lifetime totals plus live deltas;
- the startup boundary after cleanup;
- per-generation adoption units;
- G2: one non-collecting follow-up after a successful GC_DONE.

These are the design now, not open options.

**Not changed and not claimed:**
- U_r/U_b and the four §1.4.7 inequalities;
- canonical literals and the generator;
- history limits and previous-file preservation;
- the H/T/Q/pump/history policies.

Correct trigger accounting proves no numeric bound (§10).

---

## 1. The accounting contract

### 1.1 Interval origin

`O_n` is the newest CHECKPOINT record `C_n`, or, if the lineage has none, the **genesis header**: the LEDGER_HEADER with seq 1 that `LedgerWriter.create` writes into segment 0 (`chassis_persistence.py:1148–1164`). Only seq 1 can be the genesis header: rotations and reuse always write `first_seq = last + 1 ≥ 2`.

The trigger counter covers the records with `seq > O_n.seq`.

The origin's own frame is **not** in the trigger counter:
- live, CK6's reset (`chassis_session.py:619`) starts each interval after C_n;
- `start_fresh` starts at 0 after the genesis header.

It **is** physically read by replay, which starts at `covers_seq + 1 = C_n.seq` (or at seq 1). It is therefore a separate named term, `T_origin`, of the unresolved recovery bound (§10). It is not erased.

### 1.2 Per-record work

For each record `r` with `seq > O_n.seq`, applied by the replay that produced this process's memory:

```
W(r) = (1, frame(r) + obtained(r))
frame(r)    = r.length = 49 + plen + 66                        (every type, LEDGER_HEADER included)
obtained(r) = Σ over each blob fetch the reducer made while applying r of BlobRead.obtained
```

`BlobRead.obtained` (§1.4) is the number of bytes the existing bounded read returned to this process before the hash decision:

| Outcome | obtained | Reducer receives |
|---|---|---|
| `accepted` (hash matches) | `len(data)` | data |
| `rejected_hash` | `len(data)`: the actual file size, which may differ from the original | None |
| `over_limit` (`ReadTooLarge`) | the `limit + 1` bytes `read` actually returned | None |
| `missing` (`FileNotFoundError` at open) | 0 | None |
| `bad_name` (not 64 hex) | 0, no read | None |
| `io_error` (any other `OSError`) | **unknown**: charged 0 **and** counted in `unmeasured` | None |

The reducer's behavior is unchanged in every row. DONE turns None into the lost-payload text (`chassis_replay.py:412–418`); every other blob kind raises `ReplayMismatch`, which stops startup or breaks the live session.

**Counter invariant ACC.** In an unbroken `Session`:
- `since_records` equals the number of records in `(O_n.seq, last]`;
- `since_bytes` equals `Σ frame + Σ obtained` over them, as performed by this process: the live reducer for records it wrote, the selected replay for records it recovered;
- `since_unmeasured` counts the `io_error` fetches among them.

ACC is about the work this process did. A restart whose blob store changed (a deleted, replaced or over-limit DONE blob) charges what *it* read (§1.5).

### 1.3 Headers: three distinct cases

| Header | Charged | Live source | Restart source |
|---|---|---|---|
| genesis (seq 1) | no: it is `O_n` when no checkpoint exists, and below any checkpoint otherwise | — | — |
| rotation after `O_n`, including rotations before the first checkpoint | yes, `(1, frame)` | writer claim (§2.2) at `Session._rotate` | selected replay applies it (`scan_segments` returns headers as records, `chassis_persistence.py:428–466`) |
| `continue_after` reuse of an empty newest segment (O2-5) | yes | writer claim, taken when the startup session is built | it is in the suffix of later restarts |

Why C-G2 is unaffected: `test_c_g2_direct_says_checkpoint_after_records_8_and_16` uses `Session.start_fresh` (genesis only) and never rotates. `test_o2_3_a_threshold_never_checkpoints_inside_a_group` is the same, so its `13 == 8 - 1 + 6` stays. No canonical golden value changes.

### 1.4 Exposing the read outcome without a second read

`DurableOps.read` (`chassis_persistence.py:923–929`) already reads `limit + 1` bytes and raises `ReadTooLarge` past the limit. `BlobStore.get` (`:1079–1086`) catches it as `OSError`. The change:

```
class ReadTooLarge(OSError):
    def __init__(self, message, obtained=None): super().__init__(message); self.obtained = obtained
DurableOps.read: raise ReadTooLarge(..., obtained=len(data))                 # the bytes it holds already

@dataclass(frozen=True) class BlobRead: data: bytes | None; outcome: str; obtained: int | None
BlobStore.fetch(sha, limit) -> BlobRead          # the body of today's get, classified as in §1.2
BlobStore.get(sha, limit) -> bytes | None:  return self.fetch(sha, limit).data   # every existing caller unchanged
```

A `ReadTooLarge` raised by a test `DurableOps` without `obtained` is classified `io_error` (unknown), never 0. **Partial I/O under arbitrary read errors is outside the metric.** It is counted in `unmeasured`, so it is never presented as zero work, and the counter does not guess its size.

### 1.5 The two damaged-blob quantities, kept apart

- **Historical valid-payload delta.** A DONE whose valid stored result was charged live (`obtained = len(result)`), and whose blob is missing at a later restart, is charged 0 there. The difference is the previously valid stored result. Its size is bounded by `record_result`'s cap, `CAP_RESULT` at default caps; the exact relation between escaped units and bytes is not claimed here. This is the old L1.
- **Discarded physical read work.** A wrong-hash file is charged its actual size, which may exceed the original. Its upper limit is the reducer's read limit, `BLOB_READ_MAX = 64 MiB`. A file over the limit is charged its `limit + 1` probe bytes. These are charged, not bounded away.

Neither quantity substitutes for the other. A validated-payload-only figure is not the threshold quantity. It is not exposed as a counter; tests derive it from the observer where needed.

### 1.6 What stays outside the counter

| Excluded | Why |
|---|---|
| `T_origin` (C_n's frame, or the genesis header) | the interval origin; a separate bound term (§10) |
| Reads outside the selected reducer's `apply` | not replay work of the suffix (SV025 §7): <ul><li>conversation files (`_classify_base`, `_retained_prev`)</li><li>segment scans (open, rescan, `_collect`, `_consume_ack`, quarantine, witness)</li><li>`plan_recovery`'s DONE reads (`chassis_persistence.py:853`)</li><li>A8's foreign check (`chassis_startup.py:1314`)</li><li>the witnessed verification replay (`:650–658`)</li><li>rejected or unselected candidates</li></ul> |
| Retained-only references: TURN_RESPONSE `original_blobs`, NOTE_WRITTEN blobs, the LEGACY_IMPORT note blob, `blobs_live`, the foreign-note blob | the reducer never fetches them (`chassis_replay.py:455`, `:460–461`, `:610–630`) |
| fsyncs and fences | durability, not reads |

---

## 2. Interfaces (the smallest needed)

### 2.1 Replay

```
Replay(messages, state, read_blob=None, *, lenient=False, fetch_blob=None)    # exactly one reader given
  self.read_blob = read_blob or (lambda sha: fetch_blob(sha).data)            # kept public, same contract
  lifetime sums: work_records, work_bytes, work_unmeasured; per-apply: _obtained, _unmeasured

  _read(sha):                       # replaces direct read_blob calls at :292 (_blob) and :412 (_on_done)
      if fetch_blob is None: data = read_blob(sha); obtained = len(data) if data is not None else None
      else: got = fetch_blob(sha); data, obtained = got.data, got.obtained
      if obtained is None: self._unmeasured += 1 else: self._obtained += obtained
      return data

  apply(r):
      self._obtained = self._unmeasured = 0
      handler(r)                                                   # raising adds nothing
      if not (r.type_name == "CHECKPOINT" or (r.type_name == "LEDGER_HEADER" and r.seq == 1)):
          work_records += 1; work_bytes += r.length + _obtained; work_unmeasured += _unmeasured
```

`CHECKPOINT` is uncharged by type. In any suffix the only CHECKPOINT is C_n, the origin; a live CHECKPOINT is followed by the reset. Existing tests that build `Replay` with a bytes reader (`test_chassis_session.py:45`, `test_chassis_replay.py:117`) are unchanged: without `fetch_blob`, a missing blob is unmeasured, not zero.

Every production construction passes `fetch_blob`:
- `chassis_session.py:178`
- `chassis_startup.py:1282` and `:1520` (through `_replay`)

### 2.2 Writer → session header claims

```
LedgerWriter.__init__:  self.opened_headers: list[tuple[int, int]] = []         # (seq, frame length), unclaimed
LedgerWriter.open_segment (end, after write → fsync → sync_dir returned and state advanced):
                        self.opened_headers.append((seq_of_header, len(frame)))
LedgerWriter.take_opened_headers() -> list: return and clear the list
Session._claim_headers(): for seq, length in writer.take_opened_headers():
                              if seq == 1: continue                              # the genesis origin
                              since_records += 1; since_bytes += length
```

The claim is appended only after the header's fsync and the `ledger/` fsync returned. No write, fsync, name or fence order changes. A failed `open_segment` breaks the writer and claims nothing; the bytes, if any, are the next start's to classify and charge.

`_claim_headers` is called:
- at the end of `Session.__init__` (the genesis claim from `create` is skipped; a `continue_after` reuse claim is charged);
- in `Session._rotate` after `rotate_if_full`.

`continue_after`, `create` and `rotate_if_full` are the only callers of `open_segment`.

### 2.3 Session counters and boundaries

```
_commit(type, payload, *, blob=None):                 # `replay_bytes` removed
    append → (r0, b0, u0) = replay.work_*; replay.apply(record); since_* += replay.work_* − (r0, b0, u0)
_over():  since_records >= records_max or since_bytes >= bytes_max
unit_end():               unchanged contract: guards; checkpoint if _over() else _rotate()
threshold_boundary():     same guards; checkpoint if _over(); no rotation (§4.4)
```

---

## 3. Source-to-change map

| # | Location | Change |
|---|---|---|
| C1 | `chassis_persistence.py:923–933` | `ReadTooLarge(message, obtained=None)`; `DurableOps.read` passes `obtained=len(data)` |
| C2 | `chassis_persistence.py:1079–1086` | `BlobRead` dataclass; `BlobStore.fetch`; `get` delegates to it |
| C3 | `chassis_persistence.py:1132–1144`, `:1204–1242` | `opened_headers`, appended at the end of `open_segment`; `take_opened_headers()` |
| C4 | `chassis_replay.py:280–295`, `:353–357`, `:412` | §2.1 |
| C5 | `chassis_session.py:147–148`, `:159`, `:178`, `:216–235`, `:536–549` | counters including `since_unmeasured`; `_claim_headers` in `__init__` and `_rotate`; `meta_source` default `lambda _messages: {}`; `start_fresh` passes `fetch_blob`; `_commit` delta; `_over`; `threshold_boundary` |
| C6 | `chassis_session.py:339`, `:383`, `:498`, `:524`; `chassis_startup.py:920`, `:1111`, `:1320` | drop the `replay_bytes=` argument |
| C7 | `chassis_startup.py:945` (`fetch_blob = lambda sha: blobs.fetch(sha, BLOB_READ_MAX)`), `:1023`, `:1178–1209`, `:1264–1285`, `:1519–1523` | the selected-replay paths (strict, previous-base suffix and interval, lenient, no-checkpoint) use `fetch_blob`. `read_blob` stays for `plan_recovery` (`:995`, `:1069`) and `witnessed_evidence` (`:650–658`), which are uncharged by construction. |
| C8 | `chassis_startup.py:1099–1103`, `:1397` | `session.since_* += replay.work_*` (`+=` keeps a reuse-header claim taken in `__init__`). Remove `_Decision.suffix_records`. |
| C9 | `chassis_startup.py:1137` (before `return Opening`), `:925` (`_start_legacy`, before `return`) | `session.threshold_boundary()` (§4.1) |
| C10 | `chassis_session.py:424–426`, `:469–471`, `:479`, `:498`, `:502` | `threshold_boundary()` after each drop, file-edit NOTE_WRITTEN, adopted generation and drop notice (§4.2) |
| C11 | `chassis_session.py:568–623` (`checkpoint`), `:591`, `:625–675` (`_collect`) | `meta = dict(self.meta_source(self.messages))`; `_collect` returns True only after `GC_DONE`'s `_commit` returned; G2 (§4.3) |
| C12 | `chassis.py:1023–1036` | `_meta_fields(self, messages=None)`: `context_tokens` from `messages` when given (§5) |
| C13 | `chassis.py:1141–1153` | extract `Chassis._open_session(self, **overrides)` with the same kwargs; `run` calls it in the same `try`. No behavior change; it lets the callback fixture use run's actual wiring. |
| C14 | docstrings: `chassis_session.py:7–28`, `:536`, `:625–634`; `chassis.py:1119–1131` | §4 and §5 as stated text: startup may write one threshold checkpoint before `main`, and a crossing GC unit gets one non-collecting follow-up |

**Test files changed** (implementation phase, precisely):
- `tests/test_chassis_session.py:79` and `tests/test_chassis_checkpoint.py:59`: `session.meta_source = lambda: {...}` becomes `lambda _messages: {...}`. The callback contract changes arity; no assertion changes.
- `tests/test_chassis_bounds.py` tests 4, 5 and 6 (§8.3).

Unchanged: `envelope`, caps and constants, `plan_recovery`, `derive_core`, the candidate order, GC planning and validation, quarantine, IDENTITY, the acknowledgement code, `install_conversation`, `Carried`.

---

## 4. Algorithms

### 4.1 Startup

```
_recover (changes marked ◆):
  plan_recovery (read_blob, uncharged) … intent and acknowledgement checks … quarantine admission
  decision = _classify_base(…, fetch_blob)  ◆   # one selected Replay; rejected candidates stop or are never built
  … RECOVERING (after the SV024 fences), quarantine, rescan, continue_after (may claim a reuse header)
  for r in extra: replay.apply(r)                # charged once on the selected instance
  pending GC completion (intent sync + unlinks) as today
  session = Session(…, replay)                   # __init__ claims headers (reuse: charged; genesis: skipped)
  session.since_* += replay.work_*  ◆            # suffix (O_n excluded) + extras
  commit core[len(extra):]; _finish_case         # each _commit charges its delta
  sync extras' segments; retire carrier/RECOVERING in today's witnessed or plain order (each fenced by _remove)
  reserve IDENTITY (writes only if the reservation does not already cover the target)
  session.threshold_boundary()  ◆
```

- **One selected replay.** Strict newest-base, the previous-base suffix instance (`:1282`; the interval runs on `middle`, a separate instance), lenient (built only when strict is None) and the no-checkpoint full replay are alternatives. Exactly one becomes `decision.replay`. A rejected state stops, so no counter exists and none is guessed.
- **Position of the check.** It runs after `_finish_case`, the extras' syncs, the retirement order, the IDENTITY coverage, quarantine admission and pending-intent completion, which are all unchanged. A checkpoint under RECOVERING would be an unplanned extra of that intent: newest would come from `p0` only, the binding would be misread, and a witnessed exact core would stop.
- **The startup checkpoint is an ordinary one.** It calls `sync_inherited` first; `_retained_prev` uses `decision.checkpoints`; `_collect` sees only real GC_BLOCKERS; G2 applies.
- **A failure** is the startup `PersistenceFailure` boundary as today (marker, exit 44). A crash is an ordinary CK cut (§6).
- `_start_legacy` (A4/A5) ends the same way after `_consume_ack`.

### 4.2 Adoption and drops: per-generation closed units

```
write_note:      pending ≥ 16 → _drop_note(); threshold_boundary(); return None    # guards skip inside a group
adopt_file_edit: drop → _drop_note(); threshold_boundary()   |  NOTE_WRITTEN{file_edit}; threshold_boundary()
adopt_notes:     each generation: MSG_APPEND{note[,foreign]}; threshold_boundary()
                 notes_dropped → notice MSG_APPEND; threshold_boundary()
```

`adopted_through`, `pending` with foreign marks, `mirror_sha256s` and `notes_dropped` are all checkpoint state (§1.4.2, SV021-10). A checkpoint between generations is therefore a consistent resume point. Inside a tool group, CKG's guard skips the check; the whole group and its flush are the unit, closed by the turn-end or run-end checkpoint (`chassis.py:822`, `:1248–1251`).

### 4.3 GC crossing: G2, bounded and non-recursive

```
checkpoint(ended=None, *, follow_up=False):
    CK1 … CK6; record = CHECKPOINT; self.checkpoints[...] = …; since_* = 0
    collected = self.collect and not follow_up and self._collect(record)    # True only after GC_DONE returned
    if collected and self._over():
        return self.checkpoint(ended, follow_up=True)     # same `ended`; returns the final record
    self._rotate()                                        # claims any header into the new interval
    return record
```

- **Depth at most 1.** The follow-up never collects, so it adds no GC unit and cannot re-enter.
- **No follow-up after a failure.** A refused plan writes nothing and returns False. A failed unlink, fence or `GC_DONE` raises through `_fail` before any follow-up.
- **`ended`** is carried to the follow-up, so the final checkpoint's `run.json.ended` survives.
- **Rotation** happens once, at the end of the last checkpoint written.
- **`prev`.** The follow-up's `prev` is the first checkpoint (bound and newer, SV021-02). Items left by the batch stay for the next ordinary checkpoint.
- **Reachability.** At defaults a GC unit is 2 records, and GC_INTENT's body is refused above `MAX_LEDGER_BODY` (`chassis_gc.py:241`). The branch is therefore reachable only at injected thresholds (static arithmetic).

### 4.4 Threshold versus rotation; no loops at tiny thresholds

**Placement.**
- The threshold is evaluated only at a closed unit: `unit_end`, `threshold_boundary`, the turn-end, run-end and `set_history` checkpoints, and G2's single re-check.
- Rotation happens only in `_rotate`: `unit_end`'s non-checkpoint branch, and the end of `checkpoint`.
- A header is charged to the interval it was written in and is evaluated at the **next** closure. It never triggers a checkpoint itself.

So one closure produces at most:
- one threshold checkpoint;
- one G2 follow-up;
- one rotation (one header).

There is no checkpoint → header → checkpoint loop, even at `records_max = 1` or `bytes_max = 1`. Each later closure again produces at most one of each.

**Deferred rotation obligation (labelled: R-D).** `threshold_boundary` (startup end, adoption, drops) does not rotate. Today none of these boundaries rotates either, so this keeps accepted behavior rather than adding rotation points. A segment that is already full when one of them closes, including a startup writer that inherited a full segment, is rotated at the first of:

1. the threshold checkpoint itself, if one fires (`checkpoint` rotates at its end);
2. the next `unit_end`: direct say/note, direct `write_note`, recap fold, or the default opening in `resume_session` (`chassis.py:1323`);
3. the end of the next checkpoint: turn end, `set_history`, run end.

In a run that adopts nothing and starts a turn at once, that is the first turn's checkpoint. The segment can then exceed `SEGMENT_MAX` by the frames of the startup unit, the adoption units and one turn. Blobs are not in segments. `MAX_SEGMENT_READ = 2 × SEGMENT_MAX`'s slack argument (`chassis_persistence.py:936–939`) is unchanged and unproven. This design does not claim that every unit boundary rotates.

---

## 5. Production callbacks at the `open_session` boundary

Audit of what `Chassis.run` passes (`chassis.py:1141–1153`) and whether each is valid before `self.session` is assigned (`:1159`):

| Callback | Uses | Ready before assignment? |
|---|---|---|
| `install=self.carried.install` | the `messages` argument the session passes (`chassis.py:265–269`) | yes |
| `meta_source=self._meta_fields` | `self.messages` → `Chassis.messages` → `self._messages` while `session is None` (`:653–656`) | **no**: `context_tokens` would describe the empty pre-session list, and `review.py:615–618` reads that field |
| `lifecycle=self.record` | telemetry only | yes (already used by startup) |
| `repair=self._repair_adopted` | its arguments, plus `record` | yes |
| `new_lineage` | `uuid4` | yes |

`_meta_fields`' other fields are truthful for this run at that instant:
- `agent`, `name`, `run`, `model`, `context_window` and `entry` are fixed;
- `turn` is 0 and `usage` is zero, because no turn has run;
- `updated` is now.

`run.json` gains no `ended`, exactly as for every non-final checkpoint. The previous run's `ended` and `turn` are already captured in `previous_meta` before `open_session` (`chassis.py:1135–1136`, used by `status()`).

**Change (C5, C11, C12).** The contract becomes `meta_source(messages) -> dict`. `Session.checkpoint` passes the list it is about to install, and `Chassis._meta_fields(messages=None)` computes `context_tokens = estimate_tokens(messages if messages is not None else self.messages)`. The later assignment `self.session.meta_source = self._meta_fields` (`:1160`) keeps working. All existing fields and the install semantics are kept.

Rejected alternative: assigning `Chassis.session` from inside `open_session`. It would expose a partly opened session to every Chassis view on a failing start.

**Documented-contract change (C14).** `chassis.run`'s docstring says startup failures leave "no checkpoint". A startup whose outstanding work crosses the threshold now writes one ordinary checkpoint, with truthful `run.json` metadata, before the duty loads. `test_a_startup_failure_before_main_writes_no_end_and_touches_no_memory` stays below the threshold and must pass unchanged.

---

## 6. Preserved invariants, failure and crash behavior

| Invariant | Preservation |
|---|---|
| CKG | every new check uses `unit_end`'s guards; `checkpoint` keeps its own refusal (`:571`) |
| Intent, extras and witnessed exact core (SV021-08, SV023-03) | the startup check runs after durable retirement; no record is added under an intent |
| Acknowledgement receipt sync and carrier order (SV023-04) | unchanged; the check comes after it |
| IDENTITY | durable coverage of every used turn and `requests_next` is established before the check; a write happens only when needed (`reserve_turns` returns early otherwise, `chassis_session.py:257–258`) |
| SV024 pre-intent fence and inherited-byte fence | unchanged; `checkpoint` → `sync_inherited`; `open_segment` → `sync_inherited` |
| Quarantine pre-admission, pending-GC order | unchanged and earlier than the check |
| Previous-file binding and GC floor | `_retained_prev` with `decision.checkpoints`; `_collect`'s pruning unchanged |
| Failure boundary | any new checkpoint's `PersistenceFailure` breaks the session; FSYNC_FAILED is attempted; no later effect, and `record_run_end` is skipped when broken |

Crash cuts of a new checkpoint are the CK1–CK6 rows of §1.4.10:
- before CK4: A9 or A9t; the counter is rebuilt and the check fires again;
- CK4 to CK6: A10; ADOPT is charged and the check fires again.

A crash after GC_DONE and before the follow-up's CK6 leaves a spent intent (followed by its GC_DONE), which is never re-run. **L2:** repeated deaths in the CK4–CK6 window each add an ADOPT record with a conversation blob of up to 64 MiB. That is crash-loop accumulation (§10), not recursion.

---

## 7. Independent oracle for the tests

`O(lo, hi)`, computed in test code only:
- **Frames:** `frames(root)` (SV025, a byte walk of `49 + plen + 66`), **every** type, over `lo < seq ≤ hi`. It excludes only the origin: `lo` is `C_n.seq`, or 1 for the genesis header.
- **Blobs:** a test-only `AttemptObserver(Observer)` overrides `read` around `super().read`:
  - a returned read is logged with `len(data)`;
  - `ReadTooLarge` is logged with `min(os.stat(path).st_size, limit + 1)` from its **own** stat, not the runtime's `obtained`;
  - `FileNotFoundError` is logged with 0 and outcome `missing`;
  - any other `OSError` is logged as `unknown`.

  Entries are attributed to the seq whose `Replay.apply` is running (SV025's `watch` wrapper).
- The oracle is the frame sum plus the attributed blob amounts, and the count of `unknown` entries.

The counter never feeds the oracle. The wrong-hash and over-limit cases are where a validated-payload counter would disagree.

---

## 8. Finite manifest (frozen proposal; nothing run in this phase)

Rules:
- temporary roots and default `Caps` only;
- every non-default threshold or read limit is labelled **[injected]**;
- one test process per command, through the approved runner, with its limits unchanged: CPU 120 s / wall 180 s / AS 512 MiB; aggregate CPU 50 %, 2 GiB, 64 tasks, nice 15;
- one literal command per message, awaited.

Helpers come from `test_chassis_bounds.py` (`Observer`, `watch`, `frames`, `Work`), `test_chassis_recovery_live.py` (`Root`, `establish`, `resume`, `respond`, `partial_turn`), `test_chassis_durability.py` (`FaultOps`, `Crash`), `test_chassis_gc.py` (`start`, `tool_turn`) and `test_chassis_termination.py` (`make_run`, `reply`). None of those modules is modified.

### 8.1 New `tests/test_chassis_accounting.py`: 48 nodes

| Node | Params | Expected after the fix | Pre-fix |
|---|---|---|---|
| A1 `test_sv026_live_counter_equals_observed_work_per_unit_kind` | `say-inline`, `say-blob` (6,000), `done-blob` (5,000-char result, before the turn checkpoint), `note-written`, `note-adopted`, `original-retained-only` (content at cap+1) | after `establish` and an A9 start: **(a)** the per-unit delta of the counter equals the per-unit O; **(b)** the absolute counter equals `O(C_n.seq, last)` | (a) passes: the live blob charge is already correct. (b) fails: the A9 start leaves `since_records = 1` (C_n). |
| A2 `test_sv026_restart_reconstructs_the_counter_exactly` | `say-blob-x2`, `done-blob`, `done-missing`, `done-wrong-hash-larger` (3× the original length), `done-wrong-hash-smaller` (half), `done-over-limit` (**[injected]** restart `st.BLOB_READ_MAX = 1,000`, blob 5,000), `done-io-error` (the test ops raise `EIO` on that blob path), `note-adopted`, `foreign-note-adopted` (SV021-10 `test_sv021_10_the_foreign_mark_is_checkpoint_state_until_consumed` setup, then `adopt_notes`, then death), `history-replaced-cut` (`Crash` at `install_conversation` inside `replace_history`'s checkpoint), `original-retained-only` | Process 1's counter at death is `c1 == O₁`. The restart counter equals `O_restart(C_n.seq, last)`, which **includes the restart's own new records** (for `partial_turn(…, 4)`, the closure of the later call). DONE cases: `restart == c1 − obtained₁(D) + obtained₂(D) + W(new records)`, where `obtained₂` is 0 (missing), the file size (wrong hash), 1,001 (over limit) or unknown (io-error: `since_unmeasured == 1`). Lost-DONE text is unchanged. Foreign: no blob attributed to that seq. | fails: bytes 0 and `since_records` +1 at restart |
| A3 `test_sv026_repeated_restarts_never_double_count` | 1 | `say-blob-x2`, death; three A9 starts give identical counters, each equal to O, and the ledger is unchanged | fails |
| A4 `test_sv026_previous_base_recovery_counts_only_the_newest_suffix` | 1 | `establish` (A; B with prev A), two blob says, death, `conversation.json` damaged → A14 via `_previous_base`. The observer shows `(A.covers, B.covers]` applied on `middle`. The counter equals `O(B.seq, last)`, including the A14 notice and `conversation_restored`. | fails |
| A5 `test_sv026_recovery_extras_from_an_earlier_attempt_are_counted_once` | 1 | The SV025 `after-first-record` TC2 cut is rebuilt from the shared helpers. The restart applies the readable SYNTH extra once; the counter equals O, and `applies` contains that seq once. | fails |
| A6 `test_sv026_origin_and_headers` | `genesis-baseline`: `Root.start()` A4 (genesis, then LEGACY_IMPORT), 3 says, so `since_records == 4`; death; restart parity, with `O(1, last)` | genesis uncharged; counter equals O live and after restart | fails at restart (counts seq 1; bytes 0) |
| | `pre-first-checkpoint-rotation`: A4, `writer.segment_max = 1` for one say (header H written after it), then restored, then 2 says | live counter includes H; restart parity | live fails (H unclaimed) |
| | `post-checkpoint-header-crosses` (Astra's discriminator): `establish`, A9 start, `segment_max = 1` for say 1 only (header H, frame h), every say the same inline text (frame f, asserted equal by the walk); then **[injected]** `bytes_max = 3f + h` | no checkpoint after say 2 (`2f + h`); a checkpoint right after say 3; without H it would not fire. Live and restart counters before say 3 are equal and include h. | fails (no checkpoint) |
| | `continue-after-reuse`: the O2-5 surviving empty segment setup (`test_o2_5_a_surviving_empty_segment_is_reused_with_the_same_first_seq`) | the reuse header is charged at startup; a later restart includes it | fails |
| A7 `test_sv026_startup_closes_its_unit_with_a_threshold_check` | `crosses-bytes` (4×6,000 written at defaults, death, restart **[injected bytes_max 20,000]**), `crosses-records` (5 says, restart **[injected records_max 4]**), `below-control` (**[injected bytes_max 10⁹]**), `after-intent` (TC2 tail, `collect=True`, **[injected records_max 1]**), `legacy-start` (A5 list of 30,000 bytes, **[injected bytes_max 20,000]**), `fence-failure` (`crosses-bytes` plus `EIO` on the startup checkpoint's `sync_dir(session/)`) | Crossing cases: the start ends with its CHECKPOINT, counter `(0, 0, 0)` plus any rotation claim. `after-intent`, checked by a `Session.checkpoint` wrapper at entry: RECOVERING and ACKNOWLEDGED absent; `read_identity ≥` every used turn and `requests_next`; `FaultOps.events` show RECOVERING's unlink and `sync_dir(session/)` before the conversation temp open; **if** an IDENTITY rename occurred, it precedes too; no `gc_refused` naming RECOVERING. `fence-failure`: `PersistenceFailure` from `open_session`, FSYNC_FAILED present, no CHECKPOINT after the core, next start A1. Control: nothing written. | crossing cases and `fence-failure` fail; control passes |
| A8 `test_sv026_adoption_and_drops_are_closed_units` | `each-generation` (3 pending, **[injected records_max 2]** after open), `file-edit` (**[injected records_max 1]**), `drop-in-write_note` (16 pending, **[injected records_max 1]**), `drop-in-adopt_file_edit`, `drop-notice`, `drop-inside-group-control` | `each-generation`: MSG(g1), MSG(g2), CHECKPOINT (`adopted_through` 2, pending [g3]), MSG(g3); a restart adopts nothing twice. Drop cases: CHECKPOINT right after the RECOVERY or notice. Control: none inside the group; the turn-end checkpoint closes it. | first five fail; control passes |
| A9 `test_sv026_a_crossing_gc_unit_gets_one_non_collecting_follow_up` | `records` (**[injected records_max 2]**, `collect=True`, one eligible blob), `final-ended` (same via `checkpoint(ended=…)`), `below-control` (defaults) | Tail: CHECKPOINT, GC_INTENT, GC_DONE, CHECKPOINT, then at most one header, and no GC after the follow-up. The return value is the follow-up. `run.json.ended` equals the argument. Control: one checkpoint plus GC; counter equals `O` (GC frames plus any header). | first two fail; control passes |
| A10 `test_sv026_no_threshold_checkpoint_inside_a_group_or_with_a_queue` | `live-group` (**[injected records_max 1]**, a turn with queued messages), `startup-closes-group-first` (`partial_turn` 4 steps, restart **[injected records_max 1]**) | no CHECKPOINT between REQUEST_SENT and the flush's last MSG_APPEND; at startup the closure records precede the CHECKPOINT | `live-group` passes (retained invariant); the other fails |
| A11 `test_sv026_a_reset_interval_charges_only_new_work` | `after-checkpoint` (blob say, checkpoint, blob say on the same Replay), `after-gc` (`collect=True` with an eligible item: the counter after the checkpoint equals O over GC_INTENT, GC_DONE and any header; then one say), `restart-after-gc` (death after that say; the restart equals the pre-death counter) | the counter equals O of the new interval; `replay.work_bytes > since_bytes` (lifetime sums are not the interval) | implementation discriminator: pre-fix passes `after-checkpoint`; the other two fail only if a header is involved; it exists to catch a lifetime-assignment bug |
| A12 `test_sv026_follow_up_checkpoint_cuts` | `crash-before-install` (**[injected records_max 2]**, `ended` given; `Crash` at the follow-up's conversation temp open), `crash-after-ck5` (`Crash` at the follow-up's CHECKPOINT fsync), `fence-failure` (`EIO` at the follow-up's `sync_dir(session/)`) | **Crash cases:** on restart (**[injected records_max 2]**), no unlink of any name in the spent intent (`FaultOps.events`); at most 2 CHECKPOINTs and at most one GC pair written by that start; `conversation.json` then damaged → A14 recovers the same messages. `crash-after-ck5`: the crashed CK5's `run.json.ended` equals the argument, and the restart's checkpoint writes no `ended`. **`fence-failure`:** FSYNC_FAILED present, no CHECKPOINT after GC_DONE, no RUN_END, next start A1. | G2 not present: all three fail at setup (no follow-up) |
| CB `test_sv026_a_startup_checkpoint_records_metadata_of_the_recovered_conversation` | 1 | `make_run` root; one completed run; then a direct session appends 4×6,000 blob says and dies. A new `Chassis` (via `make_run`, client never called) runs `instance._open_session(bytes_max=20_000)` **[injected]**. The start writes a CHECKPOINT. A `_meta_fields` wrapper observes `instance.session is None` at the call. `run.json`: `context_tokens == chassis.estimate_tokens(opening.session.messages) != estimate_tokens([])`; `turn == 0`; no `ended`; the 10 legacy keys present; `conversation.json == conversation_bytes(opening.session.messages)`. | pre-fix: fails (no checkpoint). **Staged:** after C9 and before C11/C12, it must fail on `context_tokens`. |

Count: A1 6 + A2 11 + A3 1 + A4 1 + A5 1 + A6 4 + A7 6 + A8 6 + A9 3 + A10 2 + A11 3 + A12 3 + CB 1 = **48**.

### 8.2 Retained guard batches: explicit node lists, 97 nodes

| Batch | Nodes | Why it depends on this change |
|---|---|---|
| G1 | the 35 `retained_batches` node IDs of the accepted `SV-024-bounded-targets.json`, verbatim, in its 5 batches: durability fences 8, GC sync/gap 6, GC/rotation/prev 11, A0/A1 2, acknowledgements 8 | fences, rotation, pending GC, previous-base after collection and acknowledgement retirement all run through the changed `_commit`, `open_segment`, `checkpoint` and startup tail |
| G2 | `tests/test_chassis_recovery_live.py::test_a_crash_inside_recovery_never_turns_unknown_into_unrun`: 8 cases (SV025 retained manifest) | the semantic first-record cut and the fence order before RECOVERING |
| G3 | `test_chassis_session.py`: `test_a_session_replays_exactly_and_its_checkpoint_binds_the_file` (lambda changed), `test_a_second_checkpoint_names_the_first_as_prev_and_keeps_the_old_file`, `test_a_checkpoint_install_or_metadata_failure_breaks_the_session_and_marks[conversation]`, `[run.json]`, `test_ckg_no_checkpoint_inside_a_group_or_with_queued_messages`, `test_o2_3_a_threshold_never_checkpoints_inside_a_group`, `test_c_g2_direct_says_checkpoint_after_records_8_and_16`, `test_a_byte_threshold_counts_frames_and_replayed_blobs`, `test_rotation_happens_only_at_a_unit_boundary`, `test_a_result_blob_is_durable_before_done_and_its_failure_writes_no_done`, `test_a_successful_done_follows_its_blob`, `test_retained_originals_are_blobbed_first_and_evicted_fifo`, `test_direct_messages_are_normalized_bounded_and_blobbed_when_long`, `test_set_history_is_blobbed_then_checkpointed_and_bad_lists_write_nothing`, `test_a_recap_fold_is_a_record_the_replay_follows`, `test_run_end_is_best_effort`: **16** | C-G2 and O2-3 golden values, the threshold, meta_source arity, blob charges |
| G4 | `test_chassis_checkpoint.py`: `test_ck1_ck6_happen_in_order_with_their_fences`, `test_run_json_keeps_the_legacy_keys_and_mirrors_the_checkpoint` (lambda changed), `test_the_retained_reference_graph_covers_every_blob_replay_reads`, the four `test_sv021_02_the_previous_base_survives_*` nodes, `test_o2_2_previous_base_replay_reads_the_interval_and_the_suffix_only`: **8** | CK order, metadata, previous base |
| G5 | `test_chassis_replay.py`: `test_c_d3_a_missing_done_blob_says_what_kind_of_outcome_was_lost`, `test_c_n2_equal_text_generations_stay_distinct_and_are_both_adopted`, `test_note_adoption_is_in_generation_order_only`, `test_a_foreign_adoption_advances_the_watermark_without_appending`, `test_history_replaced_installs_the_blob_and_bounds_the_fold`, `test_external_edit_delete_and_reimport_switch_the_base`: **6** | the reducer's read path (`_read`) |
| G6 | `test_chassis_notes.py`, all 13 top-level tests, none parametrized: from `test_c_n1_a_note_is_adopted_by_the_next_run_once` through `test_a_pending_note_and_a_tail_ambiguity_both_survive_acknowledgement` | every test drives adoption or drop paths that gain checks |
| G7 | `test_chassis_metadata.py`: `test_a_startup_failure_before_main_writes_no_end_and_touches_no_memory`, `test_run_json_keeps_its_keys_and_publishes_authority_only_with_the_ledger`, `test_the_lineage_is_stable_and_the_next_run_sees_how_this_one_ended`: **3** | real `Chassis.run` with the changed `_meta_fields` and the extracted `_open_session` |
| G8 | `test_chassis_recovery_live.py`: `test_sv021_10_a_crash_after_a_reimport_keeps_its_foreign_note_adoption`, `test_sv021_10_the_foreign_mark_is_checkpoint_state_until_consumed`, `test_sv021_09_a14_cuts_converge_without_an_edit[after-notice-before-binding]`, `[after-binding-before-restore]`, `test_sv021_09_a14_before_any_checkpoint_binds_its_replay`, `test_sv021_04_one_deletion_is_consumed_once_across_restarts`, `test_sv021_09_a14_after_an_a10_adoption_keeps_memory_across_restarts`, `test_sv021_09_a14_after_an_external_edit_keeps_memory_across_restarts`: **8** | foreign adoption, A14 binding, restarts |

Total 35 + 8 + 16 + 8 + 6 + 13 + 3 + 8 = **97**. The SV024 `conditional_batches` (3 nodes) stay conditional exactly as accepted there.

### 8.3 `tests/test_chassis_bounds.py` (SV025, accepted): 16 nodes, count unchanged

- **Tests 1, 2a–2e and 3 are unchanged.** Test 3: the A9 start has counter `(0, 0)` and no rotation occurs.
- **Test 4: structural expectation replaced; renamed** `test_sv025_a_restart_carries_outstanding_suffix_bytes`. The original function runs once on the base as the pre-fix discriminator (P1).
  - First restart `("A9", 0, 0)`.
  - Two messages give `carried` (SV025 executed: 12,428).
  - Second restart `(2, carried)`, equal to the outstanding work after C_n.
  - The next message does not checkpoint (3 units < 20,000); the following one does, with the walked total in `[20,000, 20,000 + one unit)`.
  - A third start shows a newer C_n and `(0, 0)`. **[injected bytes_max 20,000]**
- **Test 5: cut moved to the real pre-checkpoint crash window; the counterexample is kept.**
  - First start: A11, whose startup threshold checkpoint dies at CK2 entry. `Crash` comes from a monkeypatched `cp.install_conversation`, after EXTERNAL_EDIT's fsync returned and before any checkpoint byte. The counter at entry is `(1, EE frame + 28,311,552) ≥ RECOVERY_BYTES_MAX`, and the live reducer re-read the blob once.
  - Second start: A9t. For `seq ≤ edit` the applies are unchanged, and there is one 28,311,552-byte blob read; the suffix is `(2, TARGET, TARGET, 1)`, still **`> NEWEST_BYTES_LT`**. The counter at the threshold checkpoint's entry equals `suffix.total − frame(C_n)`.
  - That start then writes exactly one CHECKPOINT after `edit`.
  - Conversation reads are the two classification reads followed by `_retained_prev`'s two reads (attributed None). Segment reads are two whole scans. The final counter is `(0, 0)`.
  - About 5 × 27 MiB live at peak. If AS 512 MiB is hit, that is reported and the cap is not raised.
- **Test 6:** `since_records == MESSAGES + 2` becomes `MESSAGES + 1`, because C_n is the origin. The 730-record witness, the intervals 3/242/242/242, `prev = A` and the file equality are unchanged. No rotation and no startup crossing (1 record).

### 8.4 Run plan for the implementation phase

The runner stops at the first failure, so discriminators run one node per command, before the runtime edit. They use existing APIs only; nodes that need new APIs run after the fix only.

- **P1:** original SV025 test 4 on the base; expected **pass** (the counterexample is present).
- **Expected failures:**
  - **P2** A2[say-blob-x2]
  - **P3** A6[post-checkpoint-header-crosses]
  - **P4** A2[done-wrong-hash-larger]
  - **P5** A2[done-over-limit]
  - **P6** A7[crosses-bytes]
  - **P7** A8[each-generation]
  - **P8** A9[records]
  - **P9** A10[startup-closes-group-first]
  - **P10** the rewritten test 5: no `Crash` raised
- **Staged:**
  - **S1** CB after C9 and before C11/C12: expected to fail on `context_tokens`;
  - **S2** CB after: expected to pass.

**After the change:**

| Run | Target | Expected |
|---|---|---|
| R1a | `test_chassis_accounting.py` A1–A6 | 24 passed |
| R1b | A7–A12 and CB | 24 passed |
| R2 | `test_chassis_bounds.py` | 16 passed |
| R3–R7 | G1's five SV024 batches | 8, 6, 11, 2, 8 passed |
| R8 | G2 | 8 passed |
| R9 | G3 + G4 + G5 | 30 passed |
| R10 | G6 + G7 | 16 passed |
| R11 | G8 | 8 passed |

That is 48 + 16 + 97 = 161 nodes in 13 commands, plus the discriminators. A command that hits the wall cap is split by node list and reported. No cap is raised, no meaningful case is removed, and no fixture is weakened.

---

## 9. Smallest implementable tranche

All of SV026-01 to -04 can be closed honestly, so no narrower byte-counter package is proposed. The tranche is C1–C14 together:

- the accounting (C1–C8, C11's meta call);
- the boundaries (C9, C10);
- G2 (C11);
- the callback (C5, C12, C13);
- the docstrings (C14).

The one deliberate deferral is R-D (§4.4), and it is labelled.

## 10. Unresolved, outside SV026

- `T_origin` (C_n's frame, or the genesis header) as a term of the recovery inequalities.
- P1: a per-unit byte maximum for the startup unit (a 64 MiB switch or ADOPT blob) and for adoption units.
- P4: the previous-interval count.
- P5: current shapes against the literal maxima.
- `unmeasured` partial I/O.
- L2: crash-loop ADOPT accumulation.
- R-D: the segment overshoot it allows.
- RSS, wall-clock and total startup I/O.

None of the four §1.4.7 inequalities becomes proved. SV025's default-constant refutations stand: newest bytes (test 5, with its cut moved into the real crash window, not removed) and previous records (test 6).
