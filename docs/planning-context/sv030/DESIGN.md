# SV030 design — segment readability across interrupted startup checkpoints (design only)

Base: accepted head `b946fb4a73b3f58295e89a919b725e3aa3fbaafc` (SV029 acceptance archived). Nothing here was executed. No runtime, test, constant, cap, oracle or canonical text is changed. §5 *proposes* a runtime change (R2), and §6 a future evidence package. Both need independent Astra design review before any implementation or launch. This invocation was stopped once and then resumed under a specific approval; STATUS.md records both events.

## 0. Outcome

| Question | Answer | Evidence kind |
|---|---|---|
| Can a runtime-written, crash-interrupted ledger make a segment exceed `MAX_SEGMENT_READ = 33,554,432` without a successful rotation, so that the next start stops `ledger_unreadable` before replay? | **Yes, for the exact SV029 family** (A10, then repeated edited A11 starts, each dying at CK2 entry). | Source construction at default constants (§3). The construction is **not executed**. Its first 109 starts are the executed SV029 N3 history. |
| How many edited starts at default constants? | Each start adds `f_j = 432 + d(E_j) + d(F) + d(first) + d(last_j)` bytes, where `d` is the decimal digit count, so 436 ≤ f_j ≤ 480. From SV029's prefix, the newest segment exceeds the limit after **at most 76,960** edited starts. Any family entered with a segment below 16 MiB needs **at least 34,953**. | Exact frame arithmetic from the encoder and the notice template (§2) |
| Does it recur? | Yes. Each start depends only on a fresh external edit and an M-1 death. No admission, threshold, quarantine, GC, sequence or segment-number limit stops it before the reader does. | Source induction (§3.2) |
| Does the stop resolve? | No. `("ledger_unreadable", *)` is in no implemented resolution (`chassis_startup.py:118–125`). Later starts stop at A0 on `STOPPED` (`:1704–1705`). | Source |
| Narrowest repair | **R2** (§5): a start whose inherited newest segment is already full rotates it **before the first record that start writes**. With a pending GC intent, the rotation comes right after the start's GC_DONE. Under a recovery intent, carrier, preserving plan or open group, R2 does not fire. One startup transaction still writes at most one header. | Proposal |
| What R2 closes | Only **cross-start accumulation**: no start appends to a segment that was already full when the start began, except in transaction cases that are bounded per event (§5.4). **It does not prove that every writer-produced segment is readable.** That would also need the single-closure overshoot `W ≤ SEGMENT_MAX + 1`, which remains unproved (SV025/SV027 nonclaims). | Proposal + proof obligations |
| Rejected | Raising `MAX_SEGMENT_READ`: a finite cap against a repeatable mechanism. **R1**, rotating before the checkpoint inside `unit_end`: the same recurrence survives with the death moved before the rotation's `open` (§5.2). | Trace |

## 1. Receipts and scope

**Sources read** (working tree at the base head; the session started clean; no hashes were computed because no commands were run):

- `services/chassis_persistence.py`:
  - frame layout `:41–51`; `MAX_SEQ` `:55`; `SEGMENT_MAX` `:56`
  - `canonical_body` `:184–195`; `encode_frame` `:289–313`
  - plan notices `:777–839`
  - `DurableOps.read` `:923–929`; read-bound comment and `MAX_SEGMENT_READ` `:944–950`
  - `read_segments` `:1133–1141`; `continue_after` `:1207–1243`; `open_segment` `:1245–1285`
  - `append` `:1293–1310`; `rotate_if_full` `:1312–1318`; `sync_inherited` `:1350–1367`
  - quarantine `:1402–1493`
- `services/chassis_session.py`:
  - `RECOVERY_*` `:62–63`; header claim `:180–182, 264–274`
  - `unit_end` `:586–599`; `_rotate` `:601–608`; `_retained_prev` `:610–625`
  - `checkpoint` `:627–690`; `_collect` `:692–744`
- `services/chassis_startup.py`:
  - `UNMERGED_NOTICE` `:136–139`; resolution registry `:118–125`
  - stop writing `:1675–1682`; A0 `:1704`; segment read and A2 `:1726–1729`
  - intent/carrier/collecting `:1963–2061`; second read `:2094`; `continue_after` `:2108`
  - Session and core loop `:2134–2153`; retirement, IDENTITY and `unit_end` `:2156–2180`
  - A10/A11 classification `:2285–2297`; A11 commit `:2349–2380`
  - `_binding` `:2462–2481`; `_unmerged_notice` `:2600–2628`
- `services/chassis_replay.py` `:28–62`: the only counter domain is `MAX_COUNTER = 10¹² − 1`, and no suffix-length cap exists.
- Canonical SV015v2:
  - §1.4.1 (`:205–213`)
  - §1.4.6 segment row (`:284`): "rotate at a unit boundary when ≥ SEGMENT_MAX". It is silent on ordering relative to the threshold checkpoint.
  - §1.4.8 (`:309`): the header is durable before the next record.
  - §1.4.10 rotation row (`:338`); §5.8 (`:1230–1239`)
- Tests:
  - `tests/test_chassis_replay_residual.py:225–393` (SV029 N3/N4)
  - `tests/test_chassis_rotation.py:60–73, 125–194, 322–337, 380–409, 426–503` (SV027)
  - `tests/test_chassis_bounds.py:358–452` (Observer/frames)
  - `tests/test_chassis_recovery_live.py:56–125`; `tests/test_chassis_accounting.py:80–103`
- Acceptance and planning documents:
  - Read in full: SV029 acceptance and DESIGN (L1–L6); SV027 acceptance.
  - The SV024, SV026 and SV028 boundaries are taken from the independent review's table and the source comments they govern (SV024 `sync_inherited`; SV026 header charging; SV028-09 physical headers, `:2110–2113`). Their acceptance files were not re-read here.

Historical STATUS proposals were not used as authority. Nothing in the accepted SV027 placement or SV029 evidence is reopened. This package extends SV027's disclosed read-slack nonclaim.

## 2. The compatibility obligation and the exact recurrence

**Obligation O-RW.** Every segment the writer produces under accepted crash schedules must be one that `read_segments` accepts, i.e. ≤ `MAX_SEGMENT_READ` bytes. Otherwise a valid prefix becomes a startup stop.

- The writer has no size admission: `append` encodes, fences, writes and fsyncs (`persistence:1293–1310`).
- The only size logic is `rotate_if_full` at closed boundaries (`:1312–1318`). Reached through `unit_end`, it runs either instead of a threshold checkpoint or at the **end** of a successful one (`session:596–599, 689`).
- The reader refuses at `limit + 1` (`:926–928`). Startup's first act after the run.json read is that read, and a failure becomes A2 `ledger_unreadable` with `STOPPED` written (`startup:1726–1729, 1675–1682`).

**Per-start frame (A11 in this family).** `_finish_case` commits `EXTERNAL_EDIT` with the payload `{blob, conv_sha, epoch, notices, recap_folded}` (`startup:2360–2377`):

- `plan.notices` is empty for a TC0 ledger with no pending request (`persistence:777–839`).
- `notices = [UNMERGED_NOTICE.format(first, last, calls="")]`. The suffix holds MSG_APPEND records and no TURN_RESPONSE.
- `first` is the seq of the first MSG_APPEND after B. `last` is the last seq of P (`startup:2600–2628`).

In canonical JSON (`ensure_ascii=False`, sorted keys, no spaces):

- The skeleton is 193 bytes, plus `d(E) + d(F)`.
- The notice is 81 + 3 (the UTF-8 en dash) + 40 = 124 bytes, plus `d(first) + d(last)`.
- The frame adds 49 + 66.

```
f_j = 432 + d(E_j) + d(F) + d(first) + d(last_j)
E_j = E_{j-1} + 1   (epoch = state.history_epoch + 1)
last_j = seq of the previous start's record
F = 0              (one-message edit, nothing folded)
```

Every field is a counter ≤ `MAX_COUNTER`, so 436 ≤ f_j ≤ 480. Over the default-size history, `d(F) = 1`, `d(first) ≤ 3` and `d(E), d(last) ≤ 5`, so f_j ∈ [436, 446]. The segment recurrence is `s_j = s_{j−1} + f_j`. **No other byte reaches the segment in an A11 start**:

- no core, because there is no tail;
- no notice MSG_APPEND, because A11 returns before them (`:2380`);
- no intent syncs, no carrier, no header;
- no checkpoint frame, because of the CK2-entry death;
- no GC, which runs only after CK6.

The edit blob goes to `blobs/`, not into the segment.

## 3. Default reachability (source construction; not executed)

### 3.1 Construction

1. The SV029 prefix, executed and accepted:
   - `establish`, then A9.
   - 256 inline messages. The 256th message's threshold checkpoint dies before its CHECKPOINT write, after CK3/CK4/CK5.
   - Start 1 (no edit) is A10. It writes one `RECOVERY{conversation_adopted}` and dies at CK2 entry.
   - Let `s_1` be the newest segment's size. SV029 N3 asserted that no header appears after B, so `s_1` holds establish plus 257 small frames, ≪ 16 MiB.
2. Starts j = 2, 3, …: before each start, write a distinct one-message `conversation.json` (an external edit). The start is A11, writes one EXTERNAL_EDIT (f_j bytes) and dies at CK2 entry.
3. Let K be the least k with `s_1 + Σ_{j=2}^{k+1} f_j ≥ 33,554,433`. Start K+2 refuses at `:1727`.

From `s_1 ≥ 0` and f ≥ 436: **K ≤ ⌈33,554,433 / 436⌉ = 76,960**. For any entry size below 16 MiB: K ≥ ⌈16,777,217 / 480⌉ = 34,953. Entering with a segment just below 16 MiB, for example after a long run whose last ordinary rotation left a nearly full segment, needs ≈ 16,777,217 / 446 ≈ 37,600 starts. That variant is noted, not selected.

The exact K for SV029's prefix needs the measured `s_1`. It is not computed here, and no default loop should be run: each start reads the full segment at least twice (`:1727, :2094`) and replays a suffix that grows by one record per start. Over ≈ 75,000 starts that is on the order of terabytes of reads and ≈ 3·10⁹ record applications.

### 3.2 Induction: nothing in the path depends on j except sizes and digit widths

Hypothesis H_j, before start j ≥ 2:

- **Ledger:** one valid prefix with no tail, ending in start j−1's record.
- **Stop and transaction files:** no `STOPPED`, `FSYNC_FAILED`, `RECOVERING` or `ACKNOWLEDGED`.
- **Origin:** newest CHECKPOINT = B. `.prev.json` = B's bytes. `run.json` is the prefix's CK5 (covers = the last message, ≤ last seq, so no A15).
- **IDENTITY:** unchanged.
- **Size:** `s_{j−1} ≤ 33,554,432`.

Start j under H_j:

- **Reads:** both segment reads succeed.
- **Scan and plan:** TC0, format 2, no intent, `collecting = None` (no GC_INTENT exists, and `Root.start` defaults to no collection), and `plan` continues with no notices.
- **Classification:**
  - `conversation.json` (the new edit) differs from B and from the latest binding (start j−1's EXTERNAL_EDIT or adoption; `_binding` `:2462–2481`).
  - The strict replay's list is the previous edit's list, so the file is not A10.
  - Therefore A11 (`:2285–2297`).
- **Writes and threshold:**
  - `derive_core` yields `[]`. The session counter is N_j ≥ 257 ≥ `RECOVERY_RECORDS_MAX`.
  - One EXTERNAL_EDIT is committed.
  - No intent syncs and no carrier. IDENTITY is rewritten only if missing or lower (`:2171–2174`).
  - `unit_end` sees `_over()` and calls `checkpoint`, which runs `sync_inherited` (a no-op after the append), then `_retained_prev`, then install. The death occurs at install entry, before any file change.
- **Result:** H_{j+1} holds with `s_j = s_{j−1} + f_j`.

The other constraints:

| Constraint | Status in this family |
|---|---|
| Sequence, epoch, IDENTITY | Counters stay ≪ 10¹². IDENTITY never moves. |
| Segment number | Never advances. |
| Quarantine | Never invoked: no tail, no unreadable file. |
| GC | Needs a committed CK6. The active segment is never deleted. |
| Carrier and transactions | None present. |
| Replay | No cap on suffix length (`chassis_replay.py`). |
| Reads | The conversation and blob reads are tiny against their 64 MiB bounds. |
| Executed coverage | SV029 N3 executed this exact step for j = 2…109 with every per-start invariant asserted (A11, one EXTERNAL_EDIT, files unchanged, no header, no `corrupt/`). For j > 109 only `s_j`, `N_j` and digit widths change. The only size-sensitive checks are the two segment reads. |

Disk use (≈ K blob files) is environmental and is not claimed.

### 3.3 Final state

- Start K+2 returns `Opening("A2", stop="ledger_unreadable", detail={"error": "ReadTooLarge"})` and writes `STOPPED`.
- Every later start is A0, and no resolution exists. The bytes are a valid, chained, frame-aligned prefix written entirely by the runtime.
- This is a **physical** incompatibility. A logical-record bound would not have exposed it: SV029's record counts never touch the segment size.

## 4. What the reader limit is not

It is not a malformed-frame stop. `read_segments` refuses on size alone, before any scan.

It is also not specific to `open`:

- Collection's scan (`session:708–711`) and `quarantine_tail` (`persistence:1453`) apply the same bound.
- Collection degrades to `gc_refused`.
- Neither is reached in this family before the startup read refuses.

## 5. Repair

### 5.1 Requirements

A repair must:

- preserve CKG and closed-group boundaries;
- preserve completed recovery, carrier and IDENTITY transactions and the shared extra-record comparison;
- keep SV024 inherited-byte and namespace fences;
- keep GC_DONE immediately after its intent;
- keep SV026 exact header charging and previous-base authority;
- keep the existing bounded refusal behaviour;
- keep SV027's "at most one header per closure".

### 5.2 Rejected: R1, rotate before the checkpoint inside `unit_end`

R1 (when `_over()` and the segment is full, rotate first, then checkpoint) shifts the vulnerable window without closing it.

- The start's EXTERNAL_EDIT is appended **before** `unit_end`, into the full inherited segment.
- A death anywhere in `open_segment` before its `ops.open` (for example at its `sync_inherited` fsync) leaves no new file.
- The next start continues in the same full segment and appends again. The recurrence `s_j = s_{j−1} + f_j` is unchanged.

R1 would also reorder every live closure (CHECKPOINT then LEDGER_HEADER becomes LEDGER_HEADER then CHECKPOINT). That changes accepted SV027 traces such as `test_chassis_rotation.py:360, 373`. Rejected.

### 5.3 Proposed: R2, finish the inherited boundary's rotation before this start writes

A start's inherited prefix ends at a closed unit boundary: the previous start's or unit's last record. §1.4.6 already required a rotation there when the segment was full. The previous process died before performing it. R2 performs it at the next start, **before any new record**, and never checkpoints there. A checkpoint before A11's record would install memory over the user's edit.

Placement in `_recover` (`startup:2134–2153`), after Session construction:

```
eligible = (intent is None and receipt is None and self.ack is None and preserving is None
            and replay.group is None)                    # no frozen transaction, closed boundary
if eligible and collecting is None and writer.segment_bytes >= writer.segment_max:
    session._rotate(); session.rotation_spent = True     # before the core and _finish_case
# in the core loop: right after committing the GC_DONE of `collecting`, the same guarded rotation
```

- `_rotate` gains a one-shot check: if `rotation_spent` is set, clear it, claim headers and return without rotating.
- Only the startup closure's single `_rotate` consumes it. That is the `unit_end` else-branch or the final rotation in `checkpoint`. A G2 follow-up still ends in one `_rotate`.
- The guard compares sizes **before** calling `rotate_if_full`, so a non-full start makes no extra call. SV027 R4 counts exactly five calls (`test_chassis_rotation.py:401`).

### 5.4 Changed traces and ordering proof obligations

**This family, before R2:**

```
s, +f, +f, … > 32 MiB → A2 stop
```

**After R2:**

- Starts append to segment k until a start ends with `s_k ≥ 16 MiB`.
- The next start writes LEDGER_HEADER(k+1), then EXTERNAL_EDIT into k+1, then dies at CK2.
- k is frozen below 16 MiB + 480. Segment k+1 grows by f per start until full, and the cycle repeats.
- Each header is charged once by `_claim_headers` and replayed by later starts, so `N_j` gains one record per ≈ 37,600 starts.
- At default size SV029 N3/N4 never fill a segment, so their traces are unchanged.

| Situation | Behaviour under R2 | Obligation |
|---|---|---|
| Death before `ops.open` in R2's `open_segment` | No new file. The next start retries R2 before writing. k does not grow. | — |
| Death after `O_EXCL` create, before header bytes | An empty k+1. The next `continue_after` reuses it (`persistence:1231–1235`, the O2-5 path) and writes the header before anything else. | **P1:** confirm against `scan_segments` that an empty newest segment yields `tail_segment = k+1`, offset 0, and an empty tail, with no intent. Not re-read here. |
| Death after the header write, before its fsyncs | The header is readable. The next writer continues in k+1 with `inherited = True`, and `sync_inherited` runs before CK5. This is SV024 behaviour. | — |
| Torn header (M-2) | Existing TC1/TC2 header rows apply: quarantine under an intent (R2 is suppressed there), or A2 `ledger_damaged_at`. The quarantine count is a lifetime cap of 64 files (`corrupt/` is never collected). | Bounded, not repeatable. |
| RECOVERING intent present | R2 is suppressed: a header would be an unplanned extra and would break the extras-to-core comparison (`:2115–2126`; SV028-09 exempts only preserving). Rotation stays at the closure, after retirement (SV027 `startup-after-intent`). Repeated deaths under one intent re-use its fixed core. | Growth is bounded by one core per new tail. New tails need M-2 tears, capped at 64 per lifetime. |
| Carrier, witnessed or preserving | Suppressed. The carrier is consumed before `unit_end`, so the next start is eligible. | Each case needs one operator act. |
| Pending GC intent | Rotation follows GC_DONE, which completes the GC unit (§1.4.1 lists GC as a unit). "GC_DONE first" is kept. | **P2:** this closes a sibling schedule: a start commits its checkpoint, then dies after GC_INTENT; with an edit large enough to stay over the threshold, each start would otherwise append GC_DONE + EXTERNAL_EDIT + CHECKPOINT + GC_INTENT to k. That schedule was traced by source only. |
| Open group at P's end | Suppressed: CKG forbids rotation inside a group. The core closes the group, and the next start is eligible. A new open group needs a live turn, which only follows a completed startup `unit_end`, and that rotates. | Bounded by one turn plus its closure. |
| IDENTITY | For A9/A11 starts R2 runs before `reserve_turns`. A header carries no request, and the reservation still precedes any request. | **P3:** confirm that the `:2175–2179` comment's IDENTITY precondition guarded only the checkpoint and intent-extra concerns. |
| Collection scans, previous base | Unchanged rules. k becomes a closed segment, collectible under §1.4.5. R2 changes no `prev`, checkpoint map or conversation file. | — |
| Header per closure | R2's header belongs to the inherited boundary. `rotation_spent` keeps the startup transaction at ≤ 1 header, so SV027 `startup-a9-clean` (`:130–153`, injected `segment_max = 1`) keeps exactly one header and counter `(1, header)`. | **P4:** with `rotation_spent`, a start whose own writes fill the new segment defers that rotation to the next boundary. This is the same single-closure overshoot class. |

**What R2 proves.** Assuming P1–P4: no start appends a record to a segment that was already ≥ `segment_max` when the start began, except in the bounded per-event cases above. Cross-start accumulation by M-1 deaths and external edits is closed.

**What R2 does not prove.**

- A numerical segment maximum.
- That every segment fits in `MAX_SEGMENT_READ`. That needs `W` (one process's appends to a segment between rotation opportunities) ≤ 16 MiB + 1. `W` depends on unit maxima, which remain unproved.
- Behaviour under unbounded operator acknowledgements or deletion of `corrupt/` files, which are outside the model.

A backstop that makes `append` refuse frames which would exceed the reader limit is **not** proposed. It would turn this case into a write refusal, a different stop. Whether that stop is preferable is a separate design question.

R2 changes no canonical text. Rotation stays "at a unit boundary when ≥ SEGMENT_MAX". It does change accepted startup header placement for eligible A9/A11 starts with a full inherited segment. That needs Astra design review.

## 6. Future bounded evidence package (proposal; not launched)

The new module is `tests/test_chassis_segment_readability.py`. It reuses `small_segments` (rotation `:60–73`); SV029's `CheckpointWriteDeath`, `probes` and `edit`; and `watch`/`frames`/`newest_checkpoint`.

Labels:

- **[injected]** `SEG = 16,384` via `small_segments(monkeypatch, SEG)`, applied to every writer.
- **[injected]** `READ = 32,768 = 2·SEG`, via an ops subclass whose `read` applies `min(limit, READ)` to `*.svl` paths only. It calls the real `DurableOps.read`, so the refusal is the real `ReadTooLarge`.

Everything else uses defaults (256 records, 8 MiB, caps, no collection). Crashes are in-process simulations, as in SV029. The reduced model shows the *mechanism* through the real writer and reader paths. **Default counts rest only on §2–3.** S4 ties the formula to the real encoder.

| Node | Parameters | Pre-R2 expectation | Post-R2 expectation |
|---|---|---|---|
| `tests/test_chassis_segment_readability.py::test_sv030_repeatedly_interrupted_startups_never_append_to_a_full_segment` (S1, discriminator) | SEG, READ; prefix then A10; `EDITED = 80` dying A11 starts; then one unchanged start | **Fails** at the per-start no-stop assertion with `('A2', 'ledger_unreadable', {'error': 'ReadTooLarge'})` at the first start whose walked newest segment exceeded 32,768 bytes. That start is at most the 77th edited start (f ≥ 436). Any other failure (setup, a Crash not raised, a frame walk, a formula mismatch) invalidates the run. | Passes |
| `…::test_sv030_control_a_committed_startup_checkpoint_rotates_a_full_segment` (S2, positive control) | SEG, READ; same prefix; dying A11 starts while the predicted next f keeps s < SEG; then one **non-dying** edited start whose EXTERNAL_EDIT crosses SEG | Passes | Passes (R2 does not fire: s < SEG at the start) |
| `…::test_sv030_control_the_refusal_is_the_reader_limit_on_valid_bytes` (S3, reader control) | Default SEG; establish, A9, 3 messages; X = newest segment size | Passes | Passes |
| `…::test_sv030_default_constants_and_the_edit_frame_recurrence` (S4, source tie) | None | Passes | Passes |

**Decisive assertions.**

S1 prefix:

- Messages are appended until the CHECKPOINT write dies, exactly once, at ≤ 256 messages. Headers charged in the interval trigger the threshold earlier.
- After B only MSG_APPEND and LEDGER_HEADER appear, with ≥ 1 header. This shows the injected writer rotates at ordinary boundaries.
- CK3/CK4/CK5 state is as in SV029.
- The start is A10 with exactly one adoption.

S1, every edited start:

- The case is A11 and the opening is `None` (a Crash at install entry, fired once). Abandoned writers are closed.
- The EXTERNAL_EDIT payload equals the template with independently walked `first`/`last`, and its walked frame length equals `f_j`.
- **Deferred** to after the loop (so the pre-R2 failure is the reader refusal, not an earlier structural check):
  - the new records are `["EXTERNAL_EDIT"]`, or `["LEDGER_HEADER", "EXTERNAL_EDIT"]` exactly when the newest segment was ≥ SEG before the start;
  - no record lands in a segment whose pre-start size was ≥ SEG.

S1 final state:

- The final start is A9t and commits a CHECKPOINT, preceded by one header iff the segment was full.
- No `STOPPED`, no `corrupt/`. Every `.svl` file is ≤ READ.

S2:

- Before the crossing start s < SEG; after its edit s ≥ SEG.
- The new records are exactly `["EXTERNAL_EDIT", "CHECKPOINT", "LEDGER_HEADER"]`. The header has segment +1, `first_seq` = CK.seq + 1 and `prev_chain` = CK.chain.
- The next unchanged start is A9, writes nothing and does not stop.
- This isolates the dying cut as S1's only difference.

S3:

- `scan_segments(read_segments(ledger, limit=X))` has no stop and no tail and ends at the last message.
- A start with a cap of X is A9 and writes nothing.
- A start with a cap of X−1 returns `("A2", "ledger_unreadable", {"error": "ReadTooLarge"})`, writes `STOPPED`, applies no record (`observer.applies == []`), and leaves the segment's SHA-256, `run.json`, IDENTITY and conversation files unchanged.
- A plain next start is A0.
- `("ledger_unreadable", "continue-from-bound") ∉ IMPLEMENTED_RESOLUTIONS`.

S4:

- `SEGMENT_MAX == 16,777,216` and `MAX_SEGMENT_READ == 33,554,432`.
- The real `encode_frame("EXTERNAL_EDIT", …)` with `st.UNMERGED_NOTICE` has length 436 at digit widths (1,1,1,1) and 480 at (12,12,12,12).
- ⌈33,554,433/436⌉ = 76,960 and ⌈16,777,217/480⌉ = 34,953.
- S4 is an arithmetic tie only, not reachability evidence.

**Retained nodes (8)**, each justified by source:

1. `tests/test_chassis_replay_residual.py::test_sv029_repeated_edited_starts_dying_before_their_checkpoint_grow_the_newest_suffix_past_358`: the same family at default size. Must stay header-free.
2. `tests/test_chassis_replay_residual.py::test_sv029_control_repeated_deaths_without_an_external_change_add_no_records`
3. `tests/test_chassis_rotation.py::test_sv027_every_closed_boundary_rotates_a_full_segment[startup-a9-clean]`: R2 now writes the single header. Expected unchanged.
4. `tests/test_chassis_rotation.py::test_sv027_every_closed_boundary_rotates_a_full_segment[startup-after-intent]`: suppression under an intent.
5. `tests/test_chassis_rotation.py::test_sv027_a_nonfull_segment_adds_no_event_at_the_new_boundaries`: still five `rotate_if_full` calls.
6. `tests/test_chassis_rotation.py::test_sv027_rotation_failures_and_crashes_at_the_new_boundaries[startup-inherited-fsync-eio]`: the SV024 fence before rotating away, now at R2's point.
7. `tests/test_chassis_rotation.py::test_sv027_rotation_failures_and_crashes_at_the_new_boundaries[startup-name-lost-is-recreated]`: crash during the startup rotation, then recreation.
8. `tests/test_chassis_recovery_live.py::test_checkpoint_crash_cuts_classify_by_the_bound_rule[ck6-before-write-A10]`: the prefix cut.

The parameter IDs are the literal case strings (`rotation:119–122, 415–418`; SV029-accepted for 8).

**Commands** (explicit node IDs only, no collection step, unchanged runner caps):

- Pre-R2:
  - (1) S1 alone, expected to fail as stated.
  - (2) S2, S3 and S4.
- Post-R2:
  - (3) S1 alone.
  - (4) S2, S3 and S4.
  - (5) The eight retained nodes.

That is 4 new + 8 retained, in 5 commands.

**Resource estimates** (unmeasured):

| Node | Size of run | Wall | Disk / RSS |
|---|---|---|---|
| S1 | Prefix ≈ 260 starts' worth of frames, then ≤ 81 dying starts with suffixes ≤ ≈ 340 records and segments ≤ 33 KB. Smaller than SV029 N3 (110 starts, 365 records). | ≤ 60 s | < 2 MiB disk, < 100 MiB RSS |
| S2 | ≤ 45 starts | ≤ 40 s | < 2 MiB disk, < 100 MiB RSS |
| S3 | — | ≤ 5 s | — |
| S4 | — | < 1 s | — |

S1 runs alone so that one command stays well under 120 s CPU / 180 s wall.

**Scope if accepted and executed:**

- The executed reduced-model incompatibility (pre-R2 S1).
- Its closure by R2 for this family in that model.
- The reader-path identity of the stop on valid bytes.
- An encoder-tied recurrence.

It would **not** establish a default-size execution, a segment maximum, `W`, all-segment readability, real-host durability, or any I/O, RSS or latency figure.

## 7. Recommendation

1. Astra reviews this design: the §3 construction, the rejection of R1, R2's placement and P1–P4, and the §6 plan.
2. If accepted, a bounded implementation package runs pre-R2 S1–S4, applies R2 (`chassis_startup.py` placement plus the `rotation_spent` one-shot in `chassis_session._rotate`), then runs commands 3–5. P1 and P3 are resolved by source reading within that package.
3. `W` and all-segment readability remain a separate open obligation. The candidates are a proved unit-maximum argument or a separately reviewed write-side refusal. No cap is raised.

Nothing here selects H/T/Q/history/pump/previous-file semantics or owner defaults. All existing nonclaims stand: numerical replacement bounds, total I/O, unknown partial I/O, RSS, latency and real host loss.
