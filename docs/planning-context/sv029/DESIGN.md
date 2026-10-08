# SV029 design — the two residual §1.4.7 inequalities (design only)

Base: accepted head `7936b665c4653ff61ec227ddd3d1589da31f3abe`. Nothing here was executed. No runtime, test, oracle, literal or generator change is proposed or authorized. The proposed package is **test-only**, in a new module, and leaves every accepted test unchanged.

## 0. Outcome in one table

| SV015v2 §1.4.7 inequality | Status before SV029 | SV029 proposal | Evidence kind if accepted |
|---|---|---|---|
| Newest base, bytes `< 25,166,144` | Refuted (SV025/SV026, 27 MiB A11 blob) | — (retained, not re-run) | — |
| Previous base, records `≤ 717` | Refuted (SV025, 730) | — (mechanism reused) | — |
| **Previous base, bytes `< 50,352,266`** | Unproved | **Counterexample N1**: no crash, no oversized unit, default threshold checkpoints firing normally. The retained base spans 7 threshold intervals | Executed default-constant counterexample |
| **Newest base, records `≤ 358`** | Unproved | **Counterexample N3** under a repeated (external edit, process death at CK2 entry) schedule. **Under a single interruption the bound is not refuted; it is also not proved** (explicit premise PR-N, §5.5) | Executed default-constant counterexample, conditional on a stated crash/edit schedule |

If accepted, every one of the four canonical inequalities would have an executed counterexample. **None would be replaced by a proved number.** `U_r`/`U_b` maxima remain unproved and unrefuted (SV025).

## 1. Exact clauses and comparison direction

These are from SV015v2 §1.4.7 (lines 286–305), read directly. Defaults are `RECOVERY_RECORDS_MAX = 256` and `RECOVERY_BYTES_MAX = 8,388,608` (`chassis_session.py:62–63`).

- Newest base: records read `≤ RECOVERY_RECORDS_MAX − 1 + U_r` = 255 + 103 = **358**. This is **non-strict**, so a counterexample needs **≥ 359**.
- Previous base: bytes read (frames + replayed blobs) `< 2(RECOVERY_BYTES_MAX + U_b,max) + 19,978` = 2(8,388,608 + 16,777,536) + 19,978 = **50,352,266**. This is **strict**, so a counterexample needs **≥ 50,352,266**.
- Threshold (§1.4.1, line 213; source `_over`, `chassis_session.py:583–584`): records since `≥ max` or bytes since `≥ max`. This is non-strict in both source and spec.
- The newest base is defined in §1.4.4 (line 256) as "apply the records with `seq > C_n.covers_seq`". The previous base (line 258) applies "every record with `seq > C_n.prev.covers_seq`". The intermediate result must hash to `C_n.conv.sha256`.

The bounds test constants `NEWEST_RECORDS_MAX = 358` and `PREV_BYTES_LT = 50,352,266` (`tests/test_chassis_bounds.py:68–69`) agree with this text. The literal file, generator and SV013 dossier were not needed for these clauses, so they were not reopened.

## 2. What each inequality counts (definitions used by the tests)

**Newest interval `I_n(start)`.** The ledger records with `seq > C_n.covers_seq` that are in the valid prefix `P` when a start begins, before that start commits anything. `C_n` is the newest CHECKPOINT in `P`. Source applies exactly this set (`chassis_startup.py:2236–2237, 2249`), which includes C_n's own frame (`seq = covers_seq + 1`).

- **Primary count `N`** excludes C_n's frame. This is the origin, consistent with the spec's `255 + U_r` derivation and with `uncharged` (`chassis_replay.py:277–279`). A counterexample must exceed 358 under this exclusion, so it also exceeds 358 under the "origin included" reading (`N + 1`).
- Physical `LEDGER_HEADER`s in `I_n` are frames that replay applies, so they count. The counterexample must **also** hold with headers excluded. The constructions below expect zero headers and assert that.
- Torn or quarantined tail bytes are not records. Neither the count nor the bytes include them.
- A replay is a *newest-base* replay when the base file is one whose SHA-256 equals `C_n.conv.sha256` (either file, `:2246`), so `_previous_base` is not entered. The test proves this by observing **no apply with `seq ≤ C_n.covers_seq`**. This avoids SV025's "A9t also used the older base" qualification.

**Previous interval `I_p`.** All records with `seq > C_p.covers_seq`, where `C_p` is the checkpoint **actually named by `C_n.prev`**, not `C_{n−1}`. The interval includes C_p's own frame, every intermediate CHECKPOINT frame, C_n's frame and the suffix (`_previous_base`, `:2331` and `:2337–2338`).

- **Bytes** = Σ frame lengths of every applied record in `I_p` (from an independent byte walk) + Σ blob bytes that reads attributed to `Replay.apply` of those records returned, once per (record, blob).
- The runtime counter is **not** the oracle here: `uncharged` exempts *every* CHECKPOINT frame, and the older interval runs on a separate instance that the trigger never sees (SV026).
- The primary comparison uses the **blob-only lower bound**. Frame conventions therefore cannot decide the outcome.

**Attribution of I/O (only the first row is compared with an inequality):**

| Class | Counted in `N` / `I_p` bytes? | How it is observed |
|---|---|---|
| Successful reducer work: frames applied, blob bytes obtained during `apply(seq)` | Yes | Byte walk + `Observer.reads` tagged with the applying seq |
| Scanner segment reads, `conversation.json`/`.prev.json` base reads, CK3 hashing reads | No (spec `[X]`: base files are O(conversation)) | `Observer.of("segment"/"conversation")`, reported only |
| Planning/verification reads (`read_blob` outside apply), quarantine/archive I/O | No | Reads with `applying is None` |
| Failed reads (ENOENT, over-limit, EIO) | No (not returned) | Not logged by design (SV025 observer) |
| Global startup work (IDENTITY, RECOVERING, run.json, installs) | No | Not claimed |
| Synthetic arithmetic (canonical 103, 16,777,536, 19,978) | Only as the bound's right-hand side | Copied constants |

A passing contradiction assertion is **evidence against the number**, not a numerical guarantee of anything else.

## 3. Source-to-claim matrix

| Claim / premise | Source (current head) | Used for |
|---|---|---|
| Threshold checked only at closed boundaries; reset only after a committed CHECKPOINT frame | `chassis_session.py:583–599` (`_over`, `unit_end`), `:683–685` | Both: at most 255 outstanding at a non-checkpointing boundary |
| A turn always checkpoints at its end; nothing else sits between closed boundaries except one open unit | `chassis.py:786–828` (`:822`) | PR-N analysis |
| Startup charges its selected replay, commits its core, then calls `unit_end` | `chassis_startup.py:2141–2153, 2180` | N3/N4: every loop start attempts a threshold checkpoint |
| Clean starts derive no core; spend notice only for `failed_unknown`; A14 notice/restored binding once | `derive_core` `:2634–2689`; `:2388`, `:2406` | Why only external change or new damage can grow `I_n` |
| A10 writes ADOPT once; afterwards the adopted binding makes the file A9t | `:2290–2295`, `_binding` `:2477–2478`, `:2286–2289` | N4: no growth from repeated deaths alone |
| A11 when the file differs from the latest binding; one EXTERNAL_EDIT (+ small blob) | `:2296–2297`, `:2349–2380`, `_binding` `:2473–2474` | N3: one record per edited start |
| Death at CK2 entry leaves files untouched (no install, run.json or frame) | `checkpoint` `:646–649`; accepted SV025/SV026 window (`test_chassis_bounds.py:569–576`) | N3/N4 loop step |
| Death after CK5 before the CK6 write leaves `conversation.json` = new list, `.prev.json` = C_n's bytes | `checkpoint` `:647–683`; accepted cut `ck6-before-write → A10` (`test_chassis_recovery_live.py:622–669`) | N3/N4 prefix: puts C_n's bytes in `.prev.json` |
| CK3 keeps an older bound `.prev.json` whenever the current file is unbound | `_retained_prev` `chassis_session.py:610–625` | N1: `C_r.prev = A` for every round |
| Known checkpoints exclude only those at/below a GC floor; floor = `C_n.prev.covers` | `chassis_startup.py:2273–2274`; `chassis_session.py:736–739` | N1: A stays nameable; nothing in `I_p` is collected |
| A14 only for an *unreadable* (present) file; absent is A12 | `:178–206`, `:2298–2311` | N1/N2 trigger (same as the 730 witness) |
| Previous-base replay = C_p interval then suffix, with a hash check at C_n | `_previous_base` `:2316–2339` | N1/N2 |
| Reducer charges frame + obtained blob bytes; CHECKPOINT frames are uncharged | `chassis_replay.py:277–279, 311–323, 387–396` | Why the observer, not `since_*`, is the oracle |
| Direct message ≤ 1 MiB escaped units; > 4,096 bytes → a blob | `chassis_session.py:59–60, 415–433` | N1 unit size |
| Blobs are content-addressed | `BlobStore.put` (via `append_with_blob`, `chassis_persistence.py:1331–1342`) | N1 uses distinct texts so logical = distinct bytes |
| Conversation and blob read bounds 64 MiB | `chassis_startup.py:103`, `chassis_session.py:67` | N1 file sizes are far below |

## 4. Previous-base bytes: counterexample N1 and control N2

### 4.1 Construction N1 (reachable, crash-free)

This is the SV025 730-record mechanism (`test_chassis_bounds.py:619–661`) with two changes: the units are 1 MiB direct messages, and the checkpoints are the **default threshold checkpoints**, not explicit calls.

1. `establish(root)` creates checkpoint A (`prev = None`) and B (`prev = A`). `.prev.json` holds A's bytes, which stay unchanged throughout.
2. For each round r = 1..**7**:
   - Write `conversation.json` = `conversation_bytes([{"role":"user","content":f"EDIT {r}"}])`. This is an external edit.
   - `root.start(collect=True)` classifies **A11** and writes EXTERNAL_EDIT with a small blob. The startup `unit_end` stays below threshold.
   - Make 8 calls to `session.append_message("user", t_{r,m})`. Each `t_{r,m}` is distinct ASCII, exactly 1,048,576 bytes: a prefix `f"{r}:{m}:"` padded with `a`. That is 1,048,576 escaped units, the admitted maximum.
   - The **8th** call's `unit_end` crosses `RECOVERY_BYTES_MAX` and writes threshold checkpoint `C_r`. At CK3 the current file `E_r` is unbound and `.prev.json` (A) is bound, so `C_r.prev = A`. GC floor = `A.covers`.
   - `session.close()`.
3. Damage the file: `conversation.json = b"\x00damaged in the temporary root"`, as the 730 witness does.
4. `root.start(ops=observer, collect=True)` classifies **A14**. Replay runs from `.prev.json` (A) through `I_p = (A.covers, end of P]`, which covers B's interval, 7 rounds, 7 checkpoint frames and the suffix after `C_7`.

The external actions are seven file edits and one damaged file, both already used by the accepted witness. Every ledger record is written by the runtime. No threshold, cap or segment size is injected.

### 4.2 Arithmetic before measurement

- Blob bytes in `I_p` from messages alone: 7 × 8 × 1,048,576 = **58,720,256 ≥ 50,352,266**. The margin is **8,367,990**, before counting any frame or the seven edit blobs.
- Six rounds would give 50,331,648, which is 20,618 short and would depend on frame bytes. **Seven is the smallest round count that does not depend on any frame convention.**
- Each round fires exactly one threshold checkpoint:
  - After 7 messages, blob bytes are 7,340,032. The frames since `C_{r−1}` are ≤ 2 GC records + 1 EXTERNAL_EDIT + its blob + 7 MSG_APPEND frames, each a few hundred bytes, so the total is ≪ 1,048,576. That stays below 8,388,608.
  - The 8th message reaches ≥ 8,388,608.
- **The newest-row premise holds in every interval.** Each round's work satisfies 8,388,608 ≤ W_r < 8,388,608 + one 1 MiB message + < 10 KB of frames < 25,166,144. Every unit is a direct message, far below `U_b,max`.
- The contradiction therefore comes from the **span** (`C_n.prev` skipping six later checkpoints), not from an underestimated unit. That separates it from SV025's newest-bytes witness.
- Records in `I_p` are ≈ 7 × (1 + 8 + 1 + ≤ 2) + B's interval, < 100. This is not a records claim.

**Admissibility conditions** (each one asserted):

- Default `records_max`/`bytes_max`, `DEFAULT_CAPS` and segment size.
- Every round is classified A11.
- Exactly one CHECKPOINT per round, immediately after the 8th MSG_APPEND (its type `0d` follows type `0a` in the walk).
- Every `C_r.prev == checkpoint_tuple(A)`.
- `.prev.json` bytes are unchanged from setup.
- No LEDGER_HEADER after B.
- 56 distinct message blobs.
- The final start is classified A14 with no stop. Its applies with `seq ≤ end of P` are exactly `range(A.covers+1, end+1)`, each once.

### 4.3 Expected N1 assertions

- `work = interval_work(observer, walked, A.covers, end)`:
  - `work.blob_bytes ≥ 58,720,256`
  - `work.distinct_blob_bytes == work.blob_bytes`
  - `work.blob_calls == 56 + 7`
  - `work.total ≥ work.blob_bytes ≥ 50,352,266` (the contradiction)
- The reported (not compared) value includes all CHECKPOINT frames.
- **Trigger blindness** (SV026 limitation, made visible): after the A14 start, `session.since_bytes < RECOVERY_BYTES_MAX`.
- Outcome: messages == `C_7`'s list + `A14_NOTICE`. The restored `conversation.json` hashes to `C_7.conv.sha256`. `.prev.json` is unchanged.

### 4.4 Positive / discriminating control N2

The history is the same except that only round 1 has an edit; round 2 starts on the bound file (**A9**). With two rounds:

- `C_2.prev == checkpoint_tuple(C_1)`.
- After `C_2`, `.prev.json` hashes to `C_1.conv.sha256` (rotation happened).
- The A14 start applies exactly `(C_1.covers, end]`. Its blob bytes == 8 × 1,048,576 = 8,388,608, and `work.total < 25,166,144 < 50,352,266`.

This makes the observer non-vacuous below the bound and isolates the single varied cause: an unbound current file at checkpoint time. An A12 deletion per round would produce the same span. It is noted but not selected, to stay on the accepted A11 mechanism.

## 5. Newest-base records: analysis, counterexample N3, control N4

### 5.1 Where records after `C_n` can come from (source trace)

At any durable state, `I_n` minus the origin is:

- (a) **≤ 255** records counted at the last closed boundary that did not checkpoint;
- (b) the records of **at most one** open unit. A turn ends in an unconditional checkpoint, and RUN_END follows the final checkpoint;
- (c) the records of **every start whose threshold checkpoint did not commit**.

(a) and (b) are the spec's `255 + U_r`. (c) is outside the spec's derivation.

A start adds core records only for a new tail (TC1/TC2/acknowledged TC4) or a new external change of `conversation.json` (A10 once, A11, A12). Clean, repeated, unchanged starts add nothing. N4 tests exactly this.

### 5.2 Construction N3 (repeated edit + process death)

1. `establish(root)`, then `root.start(ops=D)`. This is A9 with `since_records == 0`. B is `C_n`.
2. Make 256 calls to `session.append_message("user", f"say {i}")` (inline, ~200 B frames). The 256th `unit_end` reaches `since_records == 256` and begins a threshold checkpoint.
   - `D` raises `Crash` on the `write` whose data is a CHECKPOINT frame (header type field), **before any byte**. This is the accepted `ck6-before-write` cut.
   - CK3 has rotated B's bytes into `.prev.json` and CK4 has installed `M` (BASE + 256 messages).
3. **Start 1** (no edit) classifies A10 and writes `RECOVERY{conversation_adopted}`. `unit_end` begins a checkpoint, which dies at **CK2 entry**: `cp.install_conversation` is patched to raise `Crash`, the accepted SV025/SV026 window.
4. **Starts j = 2..109**: before each, write `conversation.json` = `[{"role":"user","content":f"EDIT {j}"}]` (distinct). The start classifies A11 (the binding is the previous ADOPT/EXTERNAL_EDIT and the file differs). It writes one EXTERNAL_EDIT, `unit_end` begins a checkpoint, and that checkpoint dies at CK2 entry.
5. **Start 110**: no edit, no death. It classifies **A9t**, the threshold checkpoint commits, and `since` returns to 0.

**Reachability holds at every step, not only the first:**

- Before start j ≥ 2, `I_n` minus the origin has 256 + 1 + (j − 2) ≥ 257 records, so the startup `unit_end` *always* reaches `checkpoint`.
- CK2-entry death leaves `.prev.json` (B), the ledger prefix and run.json exactly as before, plus that start's one durable record.
- The next external edit therefore yields A11 again. Nothing is forged, no admission is bypassed and no tail is constructed.

### 5.3 Arithmetic before measurement

- `N_1 = 256`. For j ≥ 2, `N_j = 256 + 1 + (j − 2)`.
- `N_j ≥ 359 ⇔ j ≥ 104`. The chosen final start j = 110 gives **`N_110 = 365 > 358`** (margin 7), or 366 with the origin included.
- Nothing caps this growth at default settings:
  - There is no quarantine, because there are no tails.
  - The segment holds ≈ 256 × 200 + 108 × ~400 B + establish ≪ 16 MiB, so there is no rotation and no header.
  - The edit blobs are ~60 B each.
- The loop is bounded only by MAX_SEQ and disk. Neither is claimed.

**Admissibility:**

- Default constants and caps throughout.
- Start 1 writes exactly one record, of type RECOVERY with `kind == "conversation_adopted"`.
- Each start j ∈ 2..109 writes exactly one EXTERNAL_EDIT and nothing else.
- The patched install is reached once per dying start.
- No CHECKPOINT frame after B until start 110.
- `.prev.json` hashes to `B.conv.sha256` at every start.
- No REQUEST_SENT/INVOKING after B.
- No apply with `seq ≤ B.covers` at any start, so the base is always the newest one.
- No LEDGER_HEADER after B.
- The 256 messages are inline (no blobs).

### 5.4 Expected N3/N4 assertions

**N3:**

- A fresh observer per start. `walked` is taken before the start. `N_j` is the number of distinct applied seqs `s` with `B.seq < s ≤ max(walked)` whose type is not a header. Each such seq is applied exactly once.
- The equation `N_j = 256 + [j ≥ 2]·(1 + j − 2)` holds for all j.
- At the dying checkpoint entry, the runtime `since_records == N_j + 1`. This is a comparison, not the oracle.
- `N_110 == 365 > NEWEST_RECORDS_MAX`. Start 110 is classified `"A9t"`, followed by a committed CHECKPOINT frame and `since_records == 0`.

**N4 (discriminating control, M-1 only).** The prefix is identical (steps 1–3). Starts 2..4 have **no edit** and die at CK2 entry; start 5 is normal. Expected:

- Starts 2–4 add **zero** records. `N_1 = 256`, `N_2..N_5 = 257 ≤ 358`.
- Start 5 is A9t and commits its checkpoint.
- No `corrupt/` file.

This shows that growth needs a fresh external change per start, and that a single interruption does not exceed 358 for this history.

### 5.5 What remains unproved: premise PR-N

N3 refutes the **literal, unconditional** newest-records clause. Its schedule is 108 consecutive external edits, each followed by process death in the same accepted window. It does **not** refute the clause under the following premise:

> **PR-N.** Between two committed origins, at most one start's threshold checkpoint fails to commit, and no external change of `conversation.json` occurs during that window.

Under PR-N, `N ≤ 255 + (records of one unit + its startup closure) + 1 (A10 ADOPT)`. Whether that is ≤ 358 depends on actual `U_r`, including closure, being ≤ 102. **That remains unproved.** SV025 holds `U_r = 103` as unproved, not refuted. This design neither proves nor refutes it.

A second traced mechanism is **not selected**. Repeated *torn* CK6 frames (M-2 host loss, TC1, `classify_tail` `:678–679`) add one `RECOVERY{torn_incomplete}` per start. That loop is bounded by `MAX_CORRUPT_FILES = 64` (`chassis_persistence.py:1402, 1467–1469`). Reaching 359 that way would also need a crashed unit of ≥ 39 records, for example a 50-record 16-call/16-queue turn. N3 is preferred because it needs no constructed bytes, no provider-shaped turn and no cap argument.

## 6. Independent observation scheme

The scheme reuses accepted helpers unchanged: `Observer`, `watch`, `frames`, `interval_work`, `newest_checkpoint` (`test_chassis_bounds.py:358–452`) and `Root`/`establish` (`test_chassis_recovery_live.py:56–125`).

- **Frame lengths and types** come only from the segment byte walk (`49 + plen + 66`), and every file must end on a frame boundary.
- **Applies** come from the pass-through `Replay.apply` patch. **Blob bytes** come from successful `DurableOps.read` calls tagged with the applying seq. Failed reads are absent by construction.
- **Record kinds and payloads** (ADOPT kind, `prev` tuples) come from `root.records()`. File identity comes from SHA-256 of the bytes read by the test.
- The runtime's `since_*` values and `Opening.classification` are **only compared**, never used to compute an expected value.
- New test-local helpers (in the new module only):
  - `CheckpointWriteDeath(Observer)`: overrides `write(fd, data)` and raises `Crash` before writing when `bytes(data[:5]) == cp.MAGIC` and the header type field equals CHECKPOINT's `TYPE_IDS` hex. When disarmed it passes through.
  - A small `ck2_death` context, which patches `cp.install_conversation` to count and raise `Crash`.
  - Tracking of writer fds opened through the ops wrapper, so the test can close abandoned descriptors after each `Crash`.

## 7. Proposed test matrix

New module **`tests/test_chassis_replay_residual.py`** (SV029). It imports the helpers above and changes no existing file.

| Node ID | Parameters | Expected outcome |
|---|---|---|
| `tests/test_chassis_replay_residual.py::test_sv029_a_retained_previous_base_spanning_threshold_checkpoints_exceeds_the_previous_byte_bound` | ROUNDS = 7, MESSAGES = 8, TEXT = 1,048,576 B distinct; default constants; `collect=True` | Pass, asserting §4.2/§4.3 (the contradiction) |
| `tests/test_chassis_replay_residual.py::test_sv029_control_an_immediately_previous_base_reads_one_interval_below_the_bound` | ROUNDS = 2, edit in round 1 only | Pass, asserting §4.4 (in-bound, `prev = C_1`) |
| `tests/test_chassis_replay_residual.py::test_sv029_repeated_edited_starts_dying_before_their_checkpoint_grow_the_newest_suffix_past_358` | SAYS = 256, EDITED_STARTS = 108, FINAL_START = 110 | Pass, asserting §5.3/§5.4 (`N_110 = 365`) |
| `tests/test_chassis_replay_residual.py::test_sv029_control_repeated_deaths_without_an_external_change_add_no_records` | SAYS = 256, unchanged restarts = 3 | Pass, asserting §5.4 N4 (`257` constant) |

No hidden parametrization: these are 4 selected cases.

**Retained selection (8):** each item is a direct dependency of the new nodes.

| Node ID | Dependency |
|---|---|
| `tests/test_chassis_bounds.py::test_sv025_positive_an_ordinary_unit_crosses_the_byte_threshold_once` | Observer/frames helpers; once-per-crossing threshold |
| `tests/test_chassis_bounds.py::test_sv025_the_retained_previous_base_can_be_older_than_the_last_checkpoint` | N1's mechanism (730 witness, unchanged) |
| `tests/test_chassis_accounting.py::test_sv026_previous_base_recovery_counts_only_the_newest_suffix` | Trigger blindness to `I_p` (N1 §4.3) |
| `tests/test_chassis_accounting.py::test_sv026_repeated_restarts_never_double_count` | N3/N4 restart counter comparison |
| `tests/test_chassis_recovery_live.py::test_checkpoint_crash_cuts_classify_by_the_bound_rule[ck6-before-write-A10]` | N3/N4 prefix cut → A10 |
| `tests/test_chassis_recovery_live.py::test_checkpoint_crash_cuts_classify_by_the_bound_rule[ck2-temp-A9]` | CK2 death leaves the bound classification |
| `tests/test_chassis_recovery_live.py::test_c_k2_a11_an_edited_list_is_adopted_as_an_edit` | A11 per edited start |
| `tests/test_chassis_recovery_live.py::test_a14_o2_2_an_unreadable_file_is_rebuilt_from_the_previous_base` | A14 path and hash check (N1/N2) |

**Commands** (under the unchanged runner caps; explicit node IDs only; no file or suite run):

1. The 4 new nodes in one `pytest -q -p no:cacheprovider` command.
2. The 8 retained nodes in a second command.

The total is **12 selected cases in 2 final commands**. There is no pre-fix run, because the runtime is unchanged and discrimination comes from N2 and N4. The parametrized IDs `[ck6-before-write-A10]` and `[ck2-temp-A9]` follow pytest's joining of the `(cut, expected)` values. Collection must confirm them with `--collect-only` on those two IDs before the final run.

## 8. Resource estimates (unchanged caps: CPU 50%, memory 2 GiB, Tasks 64, nice 15)

| Node | Peak disk in tmp root | Writes | Reducer + other reads | Peak RSS (est.) | Wall (est.) |
|---|---|---|---|---|---|
| N1 | ≈ 70 MiB (56 MiB blobs + 8 MiB `conversation.json` + transient 8 MiB install temp) | ≈ 120 MiB | ≈ 56 MiB live re-reads + ≈ 56 MiB A14 replay + small base/scanner reads | < 200 MiB (≤ 8 MiB live list, plus serialization and hash copies) | ≤ 30 s |
| N2 | ≈ 35 MiB | ≈ 40 MiB | ≈ 25 MiB | < 200 MiB (16 MiB list at `C_2`) | ≤ 10 s |
| N3 | < 1 MiB | small; ≈ 110 starts × ~6 fsyncs | ≈ 110 × (segment ≤ 120 KB × ~3 scans) ≈ 40 MB, plus ~6k tiny blob reads | < 100 MiB | ≤ 60 s (fsync-bound) |
| N4 | < 1 MiB | small | small | < 100 MiB | ≤ 10 s |
| Retained 8 | as previously accepted (largest is the 730 witness) | — | — | as before | ≤ 60 s |

These run as a single process with no workers and no provider or network access. The 27 MiB SV025 witness is **not** re-run.

## 9. Scope of what acceptance would establish

**It would establish:**

- An executed default-constant counterexample to previous bytes `< 50,352,266` on the current runtime, caused by the retained-base span.
- An executed default-constant counterexample to the unconditional newest records `≤ 358`, under a stated repeated edit/death schedule.
- Two discriminating controls.

**It would not establish:**

- Any proved replacement bound.
- `U_r`/`U_b` maxima.
- The newest-records bound under PR-N.
- `T_origin` or physical-replay totals.
- Total startup I/O, base-file O(conversation) reads, or the cost of unknown partial I/O (`since_unmeasured`).
- Segment/`MAX_SEGMENT_READ` slack, or lifetime work.
- RSS, latency, or kernel/power-loss behaviour. Process deaths are in-process simulations.

It also changes nothing for real sessions and authorizes no operation, merge, deployment, history/previous-file semantic change, cap change, or H/T/Q/pump/owner policy.

## 10. Recommendation and the decisions this exposes

**Next step: a test-only package**, exactly §7 (4 new + 8 retained, 2 commands), implemented by Opus and reviewed independently by Astra on an immutable head. No source decision blocks the *evidence*, because both constructions use only the current accepted behaviour.

After that evidence, numerical closure of §1.4.7 is **not** an engineering task. It needs an owner or contract decision dossier. These decisions are named here and not chosen:

- **D1 — previous-base row.** Choose one:
  - (a) Restate the bound as a function of the number of threshold intervals `k` spanned by the retained base. Note that `k` is unbounded by external edits/deletions today.
  - (b) Change the retained-previous rule so `C_n.prev` cannot span more than a bounded number of intervals. This is a previous-file semantic change and is not authorized here.
  - (c) Withdraw the row in favour of a stated nonclaim.
- **D2 — newest-records row.** Decide whether §1.4.7 quantifies over arbitrary crash/edit schedules:
  - If yes, the row is refuted and would need a term for non-committing starts. No current cap bounds the A11 variant.
  - If no, the contract must state a premise like PR-N, and a proof must still establish `U_r` (with closure) ≤ 102.
- **D3 — trigger scope.** Whether the threshold should ever account for previous-base work. Today it deliberately does not (SV026).

Each is a source/owner choice that this package must not make.
