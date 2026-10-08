# SV030 design, revision 2 — segment readability across interrupted startup checkpoints (design only)

Base: accepted head `b946fb4a73b3f58295e89a919b725e3aa3fbaafc`.

Revision 1 is the immutable head `cd72f00a9604c00eb5f16f07c9696024d76160d1`. Its independent review (`sv016-context/SV-030-Astra-design-review.md`, archived as `ASTRA-INITIAL-DESIGN-REVIEW.md`) accepted the default recurrence and required SV030-01 to SV030-03. This revision replaces revision 1's §§5–7 and corrects §0. §§2–3 are unchanged in substance.

Nothing here was executed. No runtime, test, constant, cap, oracle or canonical text was changed. R2 (§5) is a **proposal** that needs independent review before any implementation or launch.

## Corrections made for SV030-01 to SV030-03

| Finding | Correction |
|---|---|
| **SV030-01** `group is None` does not show a completed frontier; ordinary RECOVERING+A11 can grow; the bounded-exceptions claim is unsupported | R2 admits only one case: **A11 at a completed frontier** (§5.2: conjuncts E1–E9 over named startup variables). An outstanding REQUEST_SENT is excluded because the derived core then contains `possible_duplicate_spend`. A trailing HISTORY_REPLACED is excluded explicitly. The pending-GC branch is **removed**. RECOVERING+A11, A10/A12 alternation, the pending-GC sibling, the other excluded frontiers and global readability are listed as **unresolved** (§5.5). |
| **SV030-02** reuse header; one-shot lifetime; placement; P1/P3 | There is **no one-shot state**. R2 fires only if this start's writer has written no header (`writer.inherited`). A reused empty successor therefore suppresses R2, and its header is charged once by the Session constructor. The closure rotation rule is unchanged. At default constants it cannot fire after R2 (§5.3). The exact placement is between `chassis_startup.py:2143` and `:2144`; `chassis_session.py` is unchanged. §5.4 resolves P1 and P3 from source, together with fsync/fence order, charging, `now`/`decision.suffix`, core comparison and the next start's behaviour. |
| **SV030-03** test plan | 8 new nodes, 13 selected cases in total (§6), plus 8 retained nodes. The new cases add: a refusal-first S1 helper with header-aware prefix count; one registered capped observer; a crash before successor open, repeated twice, then convergence; an inherited-fsync EIO; an empty successor (real cut) reused at injected size 1, followed by a live unit; and an exclusion matrix with unanswered-request, open-group, history-replaced, pending-collection, plain-carrier and A12 cases. Each new case has a stated pre-change outcome. |

Also corrected: the R1 counter-example (§5.1), S3's scan signature (`scan_segments(segments, LINEAGE)`), and S4's labelling as domain arithmetic.

## 0. Outcome

| Question | Answer | Evidence kind |
|---|---|---|
| Can a runtime-written crash prefix exceed `MAX_SEGMENT_READ = 33,554,432` before a successful rotation, making the next start stop `ledger_unreadable` before replay? | **Yes, for the SV029 family** (A10, then repeated edited A11 starts, each dying at CK2 entry). | Source construction at default constants (§3). Not executed. The first 109 starts are the executed SV029 N3 history. |
| Default count | `f_j = 432 + d(E_j) + d(F) + d(first) + d(last_j)` bytes per start, where `d` is the decimal digit count, so 436 ≤ f_j ≤ 480. From SV029's prefix the limit is passed after **at most 76,960** edited starts. Any entry below 16 MiB needs at least 34,953. | Exact encoder arithmetic (§2) |
| Resolution of the stop | None: `ledger_unreadable` is not in `RESOLUTION_MECHANISM` (`startup:118–125`). Later starts stop at A0. | Source |
| Proposed repair | **R2**: a clean A11 start (E1–E9) whose inherited newest segment is already full rotates it before its EXTERNAL_EDIT. | Proposal |
| What R2 closes | **Only the admitted clean-A11 recurrence.** Under R2 every segment of this family stays below `SEGMENT_MAX + 1 KiB` (§5.3). | Proof from source, conditional on the stated E-conditions |
| What R2 does not close | Cross-start growth in any excluded frontier or case (§5.5), unit maxima / the single-closure overshoot `W`, and readability of all writer-produced segments. | Explicit nonclaim |

## 1. Receipts and scope

All line citations refer to the working tree at the base head. No hashes were computed because no commands were run.

**Revision-1 sources:**

- `services/chassis_persistence.py` `:41–56, 184–195, 289–313, 777–839, 923–950, 1133–1141, 1207–1318, 1350–1367, 1402–1493`
- `services/chassis_session.py` `:62–63, 180–182, 264–274, 586–744`
- `services/chassis_startup.py` `:118–139, 1675–1729, 1963–2183, 2285–2297, 2349–2389, 2462–2481, 2600–2628`
- `services/chassis_replay.py` `:28–62`
- Canonical SV015v2 §§1.4.1, 1.4.4–1.4.10 and 5.8
- `tests/test_chassis_replay_residual.py:225–393`
- `tests/test_chassis_rotation.py:60–194, 322–503`
- `tests/test_chassis_bounds.py:358–452`
- `tests/test_chassis_recovery_live.py:56–125`
- `tests/test_chassis_accounting.py:80–103`
- SV029 DESIGN and acceptance; SV027 acceptance

**Added for this revision:**

- `chassis_replay.py:330–640`: the request, group, switch and RECOVERY reducers
- `chassis_startup.py`:
  - `:196–425`: acknowledge and `read_carrier`
  - `:2634–2689`: `derive_core`
- `chassis_persistence.py:440–494`: scan of an empty newest segment
- `chassis_session.py:196–325`: `_fail`, `_commit`, `_claim_headers`, `reserve_turns`, `send`
- `tests/test_chassis_durability.py:1–110` (`FaultOps`, `Crash`)
- `tests/test_chassis_recovery_live.py:1–56, 86–206` (`partial_turn`, `respond`, A1)
- `tests/test_chassis_gc.py:1–292` (`CutOps`, `collection_ready`, `collect_with`)
- `tests/test_chassis_acknowledgements.py:1–340`
- The SV030 Astra review

The SV024, SV026 and SV028 boundaries come from the obligation review's table and the governing source comments.

## 2. Obligation and per-start recurrence (unchanged; confirmed by review)

**Obligation O-RW.** Every segment the writer produces under accepted crash schedules is ≤ `MAX_SEGMENT_READ`. Otherwise startup refuses it at `:1726–1729`.

- `append` has no size admission (`persistence:1293–1310`).
- Rotation happens only through `unit_end`, either instead of a threshold checkpoint or at the end of a successful one (`session:596–599, 689`).

**The A11 frame.** Its payload is `{blob, conv_sha, epoch, notices:[UNMERGED_NOTICE(first, last, calls="")], recap_folded}`.

- The JSON skeleton is 193 bytes plus `d(E) + d(F)`.
- The notice is 124 bytes (including a 3-byte en dash) plus `d(first) + d(last)`.
- The frame adds 115 bytes, giving `f_j = 432 + d(E_j) + d(F) + d(first) + d(last_j)`.

Here `E_j = E_{j−1} + 1`, `last_j` is the last seq of P, and F = 0. In this family an A11 start writes nothing else into the segment.

## 3. Default reachability (source construction; unchanged)

1. Start from the SV029 prefix. Let `s_1` be the newest segment's size after A10.
2. Each edited start j ≥ 2 is A11, appends `f_j` bytes and dies at CK2 entry.
3. Let K be the least k with `s_1 + Σ f ≥ 33,554,433`. Then K ≤ ⌈33,554,433/436⌉ = **76,960**.
4. Start K+2 returns `("A2", "ledger_unreadable", {"error": "ReadTooLarge"})`.

**Induction hypothesis H_j:**

- **Ledger:** one valid prefix with no tail.
- **Stop and transaction files:** no `STOPPED`, `FSYNC_FAILED`, `RECOVERING` or `ACKNOWLEDGED`.
- **Origin:** newest checkpoint B; `.prev.json` holds B's bytes; `run.json` is CK5 (covers ≤ last seq).
- **IDENTITY:** unchanged.
- **Size:** `s ≤` the read limit.

**Step:** under H_j, start j is TC0, has no intent, `collecting` is None and `derive_core` returns `[]`. It classifies A11, because the file differs from the latest binding and from the strict replay. It commits one EXTERNAL_EDIT, then `unit_end` with `_over()` true enters the checkpoint, which dies at install entry. This establishes H_{j+1}.

Only the segment size, the record count and digit widths depend on j. Neither `MAX_COUNTER` nor `MAX_SEQ` is approached. Nothing caps the suffix length. No quarantine, GC or rotation occurs.

A default-size loop is not to be run: it would mean terabytes of reads and about 3·10⁹ record applications.

## 4. The reader limit

`read_segments` refuses on size alone, before any scan. The same bound applies to collection's scan (which degrades to `gc_refused`) and to `quarantine_tail`. Neither is reached in this family before the startup read refuses.

## 5. Repair

### 5.1 Rejected options

**Raising `MAX_SEGMENT_READ`.** A finite cap against a repeatable recurrence.

**R1: rotate before the checkpoint inside `unit_end`.** The EXTERNAL_EDIT is appended before `unit_end` (`startup:2155` precedes `:2180`).

- *Corrected example:* after that append `writer.inherited` is False (`persistence:1306`), so `sync_inherited` is a no-op. The relevant cut is a death **immediately before the successor's `ops.open`** in `open_segment` (`:1264`). The next start continues in the same full segment and appends again, so the recurrence is unchanged.
- R1 would also reorder accepted live closures, e.g. `test_chassis_rotation.py:360, 373`.

### 5.2 R2: exact admission (SV030-01)

A start is **admitted** if and only if all of the following hold at the placement point. Each condition uses a variable that already exists in `_Context._recover`.

| # | Predicate | Source of the value | What it excludes |
|---|---|---|---|
| E1 | `intent is None` | `:1963` (read) or `:2084` (published for a new tail); `extra == ()` then (`:1984`) | Any recovery intent, existing or new, and therefore any tail and any extras comparison |
| E2 | `receipt is None and self.ack is None` | `:1985–1993`; carrier `:1708` | Every carrier (plain, witnessed, tail) |
| E3 | `preserving is None` | `:1995–1997` | SV028 preserving |
| E4 | `collecting is None` | `:2040` | Pending GC intent |
| E5 | `not core` | `:2046–2064`, after the ADOPT/GC_DONE/RECOVERY_ACK prefixes | Open-group closure (`derive_core:2649–2663`); an unanswered request, whose `requests_last.outcome == "failed_unknown"` yields `possible_duplicate_spend` (`:2685–2688`; the reducer leaves the outcome `failed_unknown` until a response or that RECOVERY, `replay:403, 411, 606–616`); any tail RECOVERY; A10's ADOPT |
| E6 | `decision.replay.group is None` | Replay | Stated explicitly. It is implied by E5, because an open group always has an unanswered invoke call: non-invoke calls close the group themselves, `replay:366–374` |
| E7 | `p0[-1].type_name != "HISTORY_REPLACED"` | Scan | An unfinished `set_history` unit (HISTORY_REPLACED plus its checkpoint, §1.4.1; `session:568–573`) |
| E8 | `decision.case == "A11"` | `:2297` | Every other classification, including A10, A12, A14, A8, BP and A9/A9t. Witnessed carriers can only be A9/A9t (`:2049–2050`), and preserving is BP. |
| E9 | `writer.inherited and writer.segment_bytes >= writer.segment_max` | `continue_after` `:1236–1243` (`inherited = True`) versus the reuse branch `:1231–1235` (left False). Nothing is appended between `:2108` and the placement, because E1 means there is no extras sync. | A start that already wrote a header (a reused empty successor), and a segment that is not full |

**Why E1–E7 mean the inherited prefix ends at a completed unit boundary.** The units of §1.4.1 are: turn, direct `say`/`note`/`write_note`, `set_history`, recovery/adoption step, and GC.

| Unit | When it is incomplete at P's end | Excluded by |
|---|---|---|
| Turn | Its request is unanswered, or its group is open | E5/E6 |
| Turn with queued messages | Queued messages are in memory only. No later process writes them, and recovery owes no record for them (`derive_core` writes none). | Not owed |
| `say`/`note` | Never: a single record | — |
| `set_history` | P ends with HISTORY_REPLACED. If a later record follows it, a later unit (a start) has already been appended after it, so nothing will write its checkpoint as part of that unit. | E7 |
| Recovery step | Its RECOVERING intent or carrier is not yet retired. Retirement precedes `unit_end` (`:2156–2168`). | E1/E2 |
| GC | Its intent has no GC_DONE | E4 |

The threshold checkpoint due at that boundary is not a unit record. §1.4.6 orders rotation only as "at a unit boundary when ≥ SEGMENT_MAX".

**The accepted family is admitted.**

- The SV029 family's P ends with `RECOVERY{conversation_adopted}` (after the A10 start) or with EXTERNAL_EDIT.
- There are no tails, intents or carriers, and no GC (`collect` is off by default).
- The only request was answered in `establish`, so `requests_last.outcome == "responded"`, and no group is open.
- `derive_core` therefore returns `[]` for every edited start (SV029 N3 asserted exactly one new record per start), and each such start is A11.

### 5.3 Exact placement and code

**Placement.** In `_Context._recover`, after the replay counters are added (`:2141–2143`) and before the core loop (`:2144`):

```python
        # SV030: a clean A11 start whose inherited newest segment is already full
        # completes that inherited boundary's rotation (v2 1.4.6) before its edit
        # is written. Admission E1-E9: docs/planning-context/sv030/DESIGN.md 5.2.
        if (
            decision.case == "A11" and intent is None and receipt is None and self.ack is None
            and preserving is None and collecting is None and not core
            and decision.replay.group is None and p0[-1].type_name != "HISTORY_REPLACED"
            and writer.inherited and writer.segment_bytes >= writer.segment_max
        ):
            session._rotate()
```

The size comparison precedes the call. A non-full start therefore makes **no extra `rotate_if_full` call**, which preserves SV027 R4's count of five (`rotation:401`).

**The header budget, with no new state.**

- Per start, at most one of these headers is written early: the **reuse header** from `continue_after`, or the **R2 header**. They are mutually exclusive through E9.
- The startup closure then applies its **existing** rule, unchanged: `unit_end` either rotates or checkpoints, and the checkpoint's final `_rotate` follows the G2 follow-up exactly as today (`session:686–689`).
- Nothing is suppressed, so nothing can leak into a later live unit.

**At default constants the closure cannot rotate after R2.** The fresh segment holds:

- the R2 header (payload ≤ 64-character lineage, 64-character chain and two counters; frame < 400 B);
- one EXTERNAL_EDIT (≤ 480 B);
- at most two CHECKPOINTs, one GC_INTENT and one GC_DONE, each ≤ `MAX_LEDGER_BODY + 115` (`persistence:52, 258`).

That totals < 4.2 MiB, which is below `SEGMENT_MAX`. So at defaults an admitted start writes exactly one header.

Under injected sizes below that total, the closure may write its own header too. Each header belongs to its own boundary, SV027's "≤ 1 header per closure" still holds, and each header is charged once.

**Bound for this family under R2.** An admitted start begins a segment ≥ `SEGMENT_MAX` only by rotating it first. A non-admitted start of this family is only the single A10 start, which adds one RECOVERY frame (< 400 B). So every family segment is < `SEGMENT_MAX` + 480 + 400 < `SEGMENT_MAX + 1 KiB`, far below 33,554,432.

### 5.4 Ordering obligations, resolved from source

**P1: empty successor.**

1. A newest empty segment scans to `LedgerScan(..., tail=b"", tail_segment=newest, tail_offset=0)` (`persistence:472–474`). An empty *newest* file is not a stop (`:467`).
2. `scan0.tail` is falsy, so no intent is published (`startup:2067`).
3. `continue_after` takes the reuse branch and writes and fences the header (`:1231–1235`, `open_segment(reuse_empty=True)`), leaving `inherited` False.
4. `Session.__init__` claims that header (`session:180–182`).
5. E9 is therefore false and R2 does not fire. The EXTERNAL_EDIT lands in the reused segment.
6. The old segment's bytes are durable: R2's own `sync_inherited` fsynced them before the `O_EXCL` create in the dying start (`persistence:1256–1264`).

**Fsync and namespace order** (`open_segment`, `:1255–1285`):

1. `_usable`
2. `sync_inherited` (a real fsync, because `inherited` is True)
3. `_fence_namespace` (already done in `continue_after`)
4. `O_EXCL` open
5. header write
6. fsync of the new file
7. `sync_dir(ledger/)`
8. close of the old fd

Only then does `_finish_case` append (§1.4.8, "only then may the next record go there").

**Failure path.** Any `OSError` breaks the writer. The marker is written by the writer, or else by `Session._fail` (`session:226–234`). `_rotate` turns this into `PersistenceFailure` (`:601–605`), and `open_session` propagates it after `mark_fsync_failed` (`startup:1683–1687`). The session is then broken, so no core, blob, edit or IDENTITY write can follow.

**P3: IDENTITY, request and effect boundary.**

- **Checks already done before placement:** `read_identity` (`:1967`). There is no frozen-intent comparison (E1) and no TC4 `identity_unproven` (TC0).
- **Still pending:** the exact reservation `reserve_turns(target, exact=True)` at `:2171–2174`.
- **Why early rotation is safe here:**
  - A header authorizes no request and uses no turn.
  - The only request path is `Session.send`, which reserves IDENTITY first and then commits REQUEST_SENT (`session:307–314`).
  - INVOKING requires a response (live turn).
  - An Opening is returned only after `:2174` and `:2180`. If R2 raises, no Opening exists.
  - Excluded frontiers (E5: unanswered request, open group) keep their closure records before any rotation, exactly as today.
  - `target` is computed from `now.records` (REQUEST_SENT turn_seqs) and the replay state. The header carries neither, so the target is identical with or without R2.

**Charging.**

- The R2 header is charged exactly once, by `_rotate → _claim_headers` (`session:264–274`), which drains `opened_headers`.
- It is not in `now`, `decision.suffix` or the replay, and the live session applies no header.
- The next start replays it as a charged suffix record (SV026).
- Placing R2 after the replay counters (`:2141–2143`) is additive and order-free.
- A reused-empty header is charged by `__init__`. An inherited readable header from an earlier process is charged only through replay work.

**`now` and `decision.suffix`.**

- With E1, `extra == ()`, so there is no core comparison and no `logical`/`after_core` effect this start.
- `used` (`:2171`) lists REQUEST_SENT records only.
- The notice is frozen from `decision.suffix + core` (`:2358–2361`): `last` = P's last seq. The R2 header follows P and carries no message, so the notice ("records first–last … are not in it") stays exact, and `f_j` is identical before and after R2 (asserted by S1).
- A **later** start that publishes an intent anchors at its own P, which includes the header. Its extras are only its own later records.

**Next start after each cut.**

| Cut | Next start |
|---|---|
| Death before `O_EXCL` open | No new file. The next start sees the same state and repeats R2 before writing (N5). |
| Death after create, before header bytes | Empty successor, then P1 (N7). |
| Death after the header write | The header is readable (M-1). The next writer continues the new segment with `inherited = True`. It is not full, so R2 is false, and its own append's fsync covers the header. `sync_inherited` precedes CK5 (SV024). |
| Torn header (M-2) | The existing TC1/TC2 header rows apply. Under the resulting intent R2 is excluded (E1). |

**P4.** Settled by §5.3: no deferral state exists.

**P2 (pending-GC branch).** Dropped from this package (§5.5).

### 5.5 Explicitly unresolved

R2 makes **no claim** about the following:

1. **RECOVERING + A11** (the reviewer's counter-family). One torn tail's ordinary intent stays unretired across deaths, and each changed file appends another EXTERNAL_EDIT beyond the fixed core (`:2114–2127, 2349–2380`). Excluded by E1 and E5. Growth is not bounded by this package.
2. **A10/A12 alternation**: deletion, then recreation equal to the replay, repeated. Each start writes one ADOPT or EXTERNAL_DELETE. Excluded by E8 and not analysed.
3. **The pending-GC sibling**: each start commits a checkpoint over a threshold-sized edit and dies after GC_INTENT. Excluded by E4.
4. Repeatability of the other excluded frontiers: unanswered request, open group, trailing HISTORY_REPLACED, carriers, A14, A8.
5. The single-closure overshoot `W`, unit maxima, and **readability of all writer-produced segments**.

No read-cap increase, write-side refusal, history restriction or new stop resolution is proposed.

## 6. Future bounded evidence package (proposal; not launched)

**New module:** `tests/test_chassis_segment_readability.py`. It uses only existing runtime APIs, so pre-change collection cannot fail on a new name.

**Imports:**

| From | Names |
|---|---|
| `test_chassis_rotation` | `small_segments` (`:60–73`), `once`, `segment_path`, `after` |
| `test_chassis_replay_residual` | `probes`, `edit`, `sha`, `HEX` |
| `test_chassis_bounds` | `Observer`, `frames`, `newest_checkpoint` |
| `test_chassis_recovery_live` | `Root`, `establish`, `partial_turn`, `LINEAGE`, `FaultOps` (with unlink) |
| `test_chassis_durability` | `Crash` |
| `test_chassis_gc` | `CutOps`, `collection_ready`, `collect_with` |

**Module-local helpers:**

- `ModelOps(cp.DurableOps)`:
  - `cap` (applied as `min(limit, cap)` to `*.svl` reads, then the real `DurableOps.read`);
  - `armed`/`fired` (a write whose bytes are a CHECKPOINT frame header raises `Crash` before any byte, as in SV029 `:225–237`).
- `CappedObserver(Observer)`: the same read cap. It also records the apply log, because it is registered by a local `capped_watch` fixture, a copy of `watch` (`bounds:388–411`) whose `new(cap)` constructs and registers a `CappedObserver`. `capped_watch` and `watch` are never used in the same test.
- `attempt(root, probes, ops)`:
  1. Patch `cp.install_conversation` to count calls and raise `Crash`.
  2. Run `root.start(ops=ops)`. If it raises `Crash`, the result is `None`; otherwise it is the returned `Opening`.
  3. Close every writer that `probes` tracked.
  4. Return `(fired, opening)`.

  It never uses `pytest.raises`, so a returned refusal reaches the caller's refusal assertion.
- `prefix(root, probes, ops)`:
  1. `establish(root).close()`; `b = newest_checkpoint`.
  2. Start A9 with `ops`, `ops.armed = True`.
  3. Call `append_message("user", f"say {i}")` until `Crash`, for at most 256 calls.
  4. Require `ops.fired == 1` and `n + h == 256`, where `n` is the number of messages appended and `h` the number of LEDGER_HEADERs walked after `b`. Charged headers count toward the threshold (`session:264–274`).
  5. Require `h ≥ 1` in the S1/S2 model, then CK3/CK4/CK5 as in SV029 `:290–299`.
- `full_inherited(root)`:
  1. `establish(root).close()`.
  2. A9 start; 20 calls `append_message("user", f"{i:03d}:" + "m" * 396)` (400 inline characters, each frame ≥ 515 B); close.
  3. Record `mark` (the last seq), `old` (the segment number) and `size` (its byte size, ≥ 10,300).
  4. Then `data = edit(root, label)`.

  A later start under `small_segments(monkeypatch, size)` inherits a segment that is exactly full. R2's header plus the edit (< 900 B) cannot fill a successor of that size, and since stays far below 256 at these starts, so the closure takes `unit_end`'s rotate branch, not the threshold checkpoint.

All injected sizes are labelled **[injected]**. Everything else uses defaults. Crashes are in-process simulations.

### 6.1 Nodes

`F` = the file `tests/test_chassis_segment_readability.py`.

**N1: `F::test_sv030_s1_repeatedly_interrupted_clean_a11_starts_never_append_to_a_full_segment`**

- **Parameters:** [injected] `SEG = 16,384` (`small_segments`, whole test) and `READ = 32,768` (ModelOps cap on every start); `EDITED = 80`.
- **Steps:**
  1. `prefix`.
  2. One A10 `attempt`.
  3. 80 edited `attempt`s.
  4. One final unchanged non-dying start.
- **Immediate per-start assertions:**
  - `opening is None`, else fail with `(classification, stop, detail)`.
  - `fired == [1]`, case A11.
  - The EXTERNAL_EDIT payload's notice equals `UNMERGED_NOTICE.format(first, last, calls="")` (walk-derived), and its walked length equals `f_j`.
- **Deferred assertions**, collected per start and asserted after the loop, so that the pre-change failure is the refusal:
  - The new records are `["LEDGER_HEADER", "EXTERNAL_EDIT"]` (header seq = pre-start end + 1, segment = old + 1, `prev_chain` = the old last chain) if the newest segment was ≥ SEG before the start; otherwise `["EXTERNAL_EDIT"]` in the same segment.
  - At least one header-first start occurs. This is guaranteed: 80 × 436 > 2·SEG.
- **Final start:** A9t, then one CHECKPOINT, preceded by one header if and only if the segment was full (unadmitted case, existing rule). No STOPPED and no `corrupt/`. Every `.svl` ≤ READ.

**N2: `F::test_sv030_s2_control_a_committed_startup_checkpoint_rotates_after_its_edit`**

- **Parameters:**
  - The prefix and A10 run under [injected] SEG and READ.
  - The family then runs under [injected] `SEG_F = s_A10 + 2,048`, where `s_A10` is the measured newest size. This guarantees that the crossing start begins below `SEG_F`.
- **Steps:** dying A11 attempts while the predicted `s + f_next < SEG_F` (at most 5); then one non-dying edited start whose edit crosses `SEG_F`; then an unchanged start.
- **Assertions:**
  - The new records are exactly `[EXTERNAL_EDIT, CHECKPOINT, LEDGER_HEADER]`, with the header at segment +1, `first_seq` = CK.seq + 1 and `prev_chain` = CK.chain.
  - The next start is A9 and writes nothing.
  - R2 is not involved, because the pre-start size is below `SEG_F`.

**N3: `F::test_sv030_s3_control_the_refusal_is_the_reader_limit_on_valid_bytes`**

- **Parameters:** default sizes. `establish`; A9; 3 messages; close. `X` = the newest segment size.
- **Assertions:**
  - `cp.scan_segments(cp.read_segments(ledger, limit=X), LINEAGE)` has no stop and no tail and ends at the last message.
  - A start with `capped_watch(X)` is A9 and writes nothing.
  - A start with `capped_watch(X − 1)`:
    - returns `("A2", "ledger_unreadable", {"error": "ReadTooLarge"})` and writes `STOPPED`;
    - `observer.applies == []`;
    - the segment SHA-256, `run.json`, IDENTITY and the conversation files are byte-identical.
  - The next plain start is A0.
  - `("ledger_unreadable", "continue-from-bound") not in st.IMPLEMENTED_RESOLUTIONS`.

**N4: `F::test_sv030_s4_default_constants_and_the_edit_frame_width_arithmetic`**

- **Parameters:** none. This is **labelled domain arithmetic, not a reached history**.
- **Assertions:**
  - `cp.SEGMENT_MAX == 16,777,216` and `cp.MAX_SEGMENT_READ == 33,554,432`.
  - `len(cp.encode_frame(1, "EXTERNAL_EDIT", payload, "0" * 64)[0])` is 436 for `(E, F, first, last) = (1, 0, 1, 1)` and 480 for all four set to `10**11`. The payload has exactly the runtime's five keys, with 64-hex blob and `conv_sha`.
  - ⌈33,554,433/436⌉ = 76,960 and ⌈16,777,217/480⌉ = 34,953.

**N5: `F::test_sv030_deaths_before_successor_open_leave_the_full_segment_untouched_then_converge`**

- **Setup:** `full_inherited`.
- **Two attempts**, each under `small_segments(size)` with `FaultOps` fault `("open", path == new, Crash())`:
  - `Crash` is raised.
  - `("open", new)` occurred, preceded by `("fsync", old)`.
  - Abandoned fds are closed (`ops.paths`).
  - There are no records after `mark`, no `new` file, and the old segment's bytes are unchanged.
- **Converge**, under `small_segments(size)` with no fault:
  - A11.
  - After `mark`: `[LEDGER_HEADER(old + 1, mark + 1, first_seq = mark + 1, prev_chain = last.chain), EXTERNAL_EDIT(old + 1, conv_sha = blob = sha(data))]`.
  - `(since_records, since_bytes) == (22, Σ walked frames of the 20 messages, header and edit + len(data))`. This is an independent walk and shows the header is charged once.
- **Then:** a default start is A9t and writes nothing.

**N6: `F::test_sv030_inherited_sync_failure_before_the_edit_writes_nothing`**

- **Setup:** `full_inherited`; `small_segments(size)`; `FaultOps` fault `("fsync", once(path == old), EIO)`.
- **Assertions:**
  - The start raises `cp.PersistenceFailure`.
  - `("fsync", old)` occurred and `("open", new)` did not.
  - There are no records after `mark` and the blob `sha(data)` is absent: no edit, core or effect.
  - IDENTITY bytes are unchanged and `FSYNC_FAILED` exists.
  - The next start returns `("A1", "fsync_failed_previous_run")`.

**N7: `F::test_sv030_empty_successor_is_reused_without_a_second_early_header`**

- **Setup:** `full_inherited`; `small_segments(size)`; `FaultOps` fault `("write", path == new, Crash())`.
- **First start:**
  - `Crash`.
  - `new` exists with size 0.
  - There are no records after `mark`.
- **Restart** under [injected] `small_segments(1)`, which exposes duplicates:
  - A11 with no stop.
  - After `mark`: exactly `[LEDGER_HEADER(old + 1, mark + 1, prev_chain = last.chain), EXTERNAL_EDIT(old + 1), LEDGER_HEADER(old + 2, mark + 3, prev_chain = edit.chain)]`. These are the reuse header, the edit and the closure header. A third header would mean R2 fired after the reuse.
  - Counter `== (23, Σ frames + len(data))`.
- **Live unit:** `append_message("user", "after")` appends `MSG_APPEND` followed by `LEDGER_HEADER`, and the counter is 25. Ordinary rotation is unchanged and there is no residual state.
- **Then:** close; a default start is A9t and writes nothing.

**N8: `F::test_sv030_excluded_frontiers_keep_their_records_before_any_rotation[case]`**

- **Common parts:**
  - Each case builds its history through real paths, closes or abandons, then edits the conversation (except `a12-delete`).
  - It restarts under [injected] `small_segments(1)`.
  - Assertions: no stop; the expected classification; the new records equal the case's exact list; every non-header record is in the inherited segment; exactly one LEDGER_HEADER, and it is last (the existing closure rotation).

| `case` | History through real paths | Expected classification and new records |
|---|---|---|
| `unanswered-request` | `establish`; `partial_turn(session, 1)` | A11: `[RECOVERY(possible_duplicate_spend), EXTERNAL_EDIT, LEDGER_HEADER]` |
| `open-group` | `establish`; `partial_turn(session, 3)` (call 0 invoked, no DONE; call 1 not invoked) | A11: `[SYNTH(unknown), UNRUN, EXTERNAL_EDIT, LEDGER_HEADER]` |
| `history-replaced` | `establish`; with `cp.install_conversation` raising `Crash`, `replace_history([{"role": "user", "content": "R"}])` raises `Crash` | A11: `[EXTERNAL_EDIT, LEDGER_HEADER]` |
| `pending-collection` | `collection_ready(tmp_path / "r", ops=CutOps())`; `ops.crash_when = lambda c, p, f: c == "unlink"`; `collect_with` raises `Crash`; P ends GC_INTENT | A11: `[GC_DONE, EXTERNAL_EDIT, LEDGER_HEADER]` |
| `plain-carrier` | `establish`; A9 start with `FaultOps` fsync EIO `once` on `.svl`; `append_message` raises `PersistenceFailure`; the next start is A1; `st.acknowledge(session_dir, "fsync_failed_previous_run", "continue-from-bound")` (`startup:256–299`) | A11: `[EXTERNAL_EDIT, RECOVERY_ACK, LEDGER_HEADER]`; `ACKNOWLEDGED` is removed |
| `a12-delete` | `establish`; close; unlink `conversation.json` | A12: `[EXTERNAL_DELETE, LEDGER_HEADER]` |

N8 is identical before and after the change. It discriminates **guard designs**: revision 1's group-only guard would put the header first in `unanswered-request`, `history-replaced` and `plain-carrier`, and its pending-GC branch would put a header after GC_DONE. The real intent suppression is retained node 2.

### 6.2 Pre-change expectations

These are runs on the unchanged runtime; any other outcome invalidates the discriminator.

| Node | Expected result before R2 |
|---|---|
| N1 | **Fails** at the per-start refusal assertion with `('A2', 'ledger_unreadable', {'error': 'ReadTooLarge'})`. It happens at the first edited start whose pre-start walked newest segment exceeds 32,768 bytes, which is at the latest the 77th (`76 × 436 ≥ 32,769`). |
| N5 | **Fails** at the first attempt's "no records after mark": `["EXTERNAL_EDIT"]` was appended before the closure's open. |
| N6 | **Fails** at "no records after mark". The EXTERNAL_EDIT bytes precede the failing append fsync, and the blob is present. |
| N7 | **Fails** at the first start's "no records after mark": `["EXTERNAL_EDIT"]`. |
| N2, N3, N4, N8 × 6 | Pass |

### 6.3 Retained nodes

The only changed source path is the guarded block in `_recover`, which every format-2 start evaluates.

1. `tests/test_chassis_rotation.py::test_sv027_every_closed_boundary_rotates_a_full_segment[startup-a9-clean]`: A9 is excluded; the single closure header is unchanged.
2. `tests/test_chassis_rotation.py::test_sv027_every_closed_boundary_rotates_a_full_segment[startup-after-intent]`: real intent suppression; rotation stays after retirement.
3. `tests/test_chassis_rotation.py::test_sv027_a_nonfull_segment_adds_no_event_at_the_new_boundaries`: still five `rotate_if_full` calls.
4. `tests/test_chassis_rotation.py::test_sv027_rotation_failures_and_crashes_at_the_new_boundaries[startup-name-lost-is-recreated]`: the reuse path still writes one header.
5. `tests/test_chassis_replay_residual.py::test_sv029_repeated_edited_starts_dying_before_their_checkpoint_grow_the_newest_suffix_past_358`: admitted A11 at default size, never full; the trace is unchanged and has no header.
6. `tests/test_chassis_replay_residual.py::test_sv029_control_repeated_deaths_without_an_external_change_add_no_records`
7. `tests/test_chassis_acknowledgements.py::test_a_witnessed_file_repair_stop_resumes_from_the_bound_checkpoint[a14]`: the witnessed carrier passes through the guard with exactly `[RECOVERY_ACK, UNRUN]`.
8. `tests/test_chassis_recovery_live.py::test_c_k2_a11_an_edited_list_is_adopted_as_an_edit`: an ordinary non-full A11 start is unchanged.

### 6.4 Commands

Run serially, with explicit node IDs only, no collection step, and unchanged caps (CPU 120 s, wall 180 s and AS 512 MiB per command; aggregate CPU 50%, memory 2 GiB, Tasks 64, nice 15).

| # | When | Nodes | Expected |
|---|---|---|---|
| 1 | Pre-change | N1 | 1 failure, as stated |
| 2 | Pre-change | N5, N6, N7 | 3 failures, as stated |
| 3 | Pre-change | N2, N3, N4, N8 × 6 | 9 passed |
| 4 | Post-change | N1 | Pass |
| 5 | Post-change | N2–N7, N8 × 6 | 12 passed |
| 6 | Post-change | The 8 retained nodes | Pass |

**Totals:** 13 new selected cases (8 nodes) and 8 retained, in 6 commands.

**Resource estimates** (unmeasured):

- **N1:** ≤ 82 starts, suffix ≤ ≈ 340 records, segments ≤ 33 KB. Smaller than SV029 N3. ≤ 60 s.
- **N2:** ≤ 8 starts.
- **N5–N8:** each ≤ 4 starts on a ledger of ≤ 40 records. `pending-collection` reuses SV022's three-turn fixture.
- **Commands 3 and 5:** ≤ 60 s each.
- **Disk and memory:** < 5 MiB disk and < 150 MiB RSS for any node.

**Scope if accepted and executed:**

- **Established:**
  - the executed reduced-model incompatibility (pre-change N1);
  - its closure for admitted clean A11 starts in that model;
  - the ordering of R2's pre-append crash and failure behaviour;
  - reuse without a duplicate header;
  - unchanged excluded frontiers;
  - the reader-path identity of the stop;
  - the encoder width arithmetic.
- **Not established:** a default-size execution, `W`, closure of anything in §5.5, all-segment readability, real-host durability, or any I/O, RSS or latency figure.

## 7. Recommendation

1. Astra reviews revision 2.
2. If accepted, a bounded implementation package runs commands 1–3, then adds the §5.3 block to `chassis_startup.py` (the only runtime change), then runs commands 4–6.
3. §5.5 stays open. Its candidates are separate reviewed packages:
   - a frontier/case-specific analysis of RECOVERING+A11, the A10/A12 alternation and the pending-GC sibling;
   - a proved `W`;
   - or a separately reviewed write-side refusal.

Nothing here selects H/T/Q/history/pump/previous-file semantics or owner defaults. All existing nonclaims stand: numerical replacement bounds, total I/O, unknown partial I/O, RSS, latency and real host loss.
