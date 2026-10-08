# SV-025 receipt: replay-work accounting and proof status of SV-015 v2 §1.4.7

**Result: none of the four exact inequalities is proved for the accepted runtime. Two are refuted by executed default-constant counterexamples (newest bytes and previous records). The other two remain unproved with failed premises; the previous-bytes construction is static and unexecuted. Restart byte accounting has a separate executed structural counterexample at an injected threshold.** The accounting and the observer are test-only. No runtime source, limit, literal, generator, oracle or frozen design text was changed. Acceptance of this package would mean the accounting and evidence are sound. It does not mean, and must not be read as meaning, that the numbers hold.

Base: accepted SV024 `944e9d3e21987093cb78ff150d74e4e55900ad57`. Scope: `SV-025-bounds-preflight.md`, manifest `SV-025-bounded-targets.json`. Opus is primary investigator; Astra reviews. The worker made no Git call.

## 1. Sources

- **Canonical:** SV-015 v2 §1.4.1 (units, CKG, threshold), §1.4.4 (newest/previous base), §1.4.5 (retained set), §1.4.6 (limits), §1.4.7 (the bound); SV-013 §2.2.5 l.663 and C-G2 l.1331 (superseded by v2 for the mid-group bound).
- **Literal values:** `SV-015-literal-values-v2.json` (`ledger_frame_max_bytes`, `recovery_unit`, `recovery_bound_defaults`).
- **Generator:** `SV-015-literal-generator-v2.py.txt` l.89–129. Read as text, **not executed**.
- **Canonical claim:** U_r = 103; U_b(turn) = 3,333,164; U_b(say) = 1,048,803; U_b(set_history) = U_b,max = 16,777,536; R = 256; B = 8,388,608; newest ≤ 358 records and < 25,166,144 bytes; previous ≤ 717 records and < 50,352,266 bytes. Bytes are frames plus the blobs replay opens. Retained originals that replay does not open are excluded, and so are reads of conversation.json/conversation.prev.json.

## 2. Quantities (never substituted for one another)

| Quantity | Definition | Where measured |
|---|---|---|
| **Logical interval work** | For the records of one replay interval: Σ frame bytes + Σ bytes of each blob replay opened while applying that record, once per (record, blob) | `interval_work`: frames from a byte walk of the segment files; blob bytes from actual `read` calls attributed to the seq whose `Replay.apply` was running |
| **Distinct blob bytes** | The same blobs, once per name | same |
| **Read calls** | Every `DurableOps.read`: segments, blobs, conversation files, markers; duplicates included | `Observer.reads` |
| **Writer counters** | `Session.since_records` / `since_bytes` | Compared against the above, never used as their oracle |

The canonical bound is about logical interval work. Startup I/O is a different and larger quantity: whole-ledger scans, base-file reads, and repeated reads of the same blob.

## 3. Units and where the threshold is evaluated

`_commit` (`chassis_session.py:216`) adds 1 record and `record.length + replay_bytes` for every record, including recovery's. `unit_end` (`:536`) is the only threshold check. `checkpoint` (`:568`) resets both counters after CK6 (`:619`), then GC commits and then rotation.

| Unit (v2 §1.4.1) | Records | Replay-opened blob | `replay_bytes` passed | Threshold check after it |
|---|---|---|---|---|
| Turn | REQUEST_SENT, TURN_RESPONSE/RESPONSE_REFUSED, ORIGINAL_EVICTED×k, INVOKING/DONE, TERMINATION, SYNTH/UNRUN, NOTE_WRITTEN/RECOVERY in group, queued MSG_APPEND | DONE blob; MSG_APPEND blob (> 4,096 bytes) | len(DONE blob), len(MSG blob) | none (`chassis.py:822` checkpoints unconditionally at turn end) |
| Direct say/note | MSG_APPEND | blob if > 4,096 bytes | len(blob) | `unit_end` (`chassis_session.py:395`) |
| Direct write_note | NOTE_WRITTEN | **none** (pending metadata only, `chassis_replay.py:460`) | 0 | `unit_end` (`:445`) |
| Note-drop | RECOVERY{note_dropped_pending_limit} | none | 0 | **none** (`write_note` returns at `:426` before `unit_end`; also from `adopt_file_edit` `:470`) |
| set_history | HISTORY_REPLACED, then checkpoint | new_blob (≤ 16 MiB) | len(blob) | immediate checkpoint (`:526`) |
| Recap fold | RECAP_FOLD | none | 0 | `unit_end` (`chassis.py:994`) |
| **Recovery core** (startup) | GC_DONE, RECOVERY_ACK, SYNTH/UNRUN, RECOVERY…, ADOPT (A10) | `conversation_adopted` blob (≤ 64 MiB) | len(file) for ADOPT | **none** (`chassis_startup.py:1104–1114`) |
| **Base switch** (startup) | LEGACY_IMPORT, EXTERNAL_EDIT, LEGACY_REIMPORT, EXTERNAL_DELETE; A14 notice + RECOVERY{conversation_restored} | whole list blob (≤ 64 MiB: `CONVERSATION_READ_MAX`, `BLOB_READ_MAX`) | len(list) | **none** (`:920`, `:1320`, `:1325`, `:1338–1350`) |
| **Adoption** (resume) | NOTE_WRITTEN{file_edit}; MSG_APPEND{note}×≤16; drop notice | note blob unless `foreign` | 0 for NOTE_WRITTEN; `entry["bytes"]` or 0 (foreign) | **none** (`chassis_session.py:452–503`, `chassis.py:1312–1313`) |
| **GC** (after CK6) | GC_INTENT (≤ 4,096 items, body < 1 MiB), GC_DONE | none | 0 | **none** (`:620–667`), counted after the reset |
| RUN_END | RUN_END | none | 0 | none (after the final checkpoint) |
| Rotation | LEDGER_HEADER | none | **not committed**: in neither counter | — |

**Startup reconstruction** (`chassis_startup.py:1099–1103`). `since_records = len(suffix) + len(extra)`. The suffix is `seq > C_n.covers_seq`, which includes C_n's own frame, so it is one more than the live counter. That is conservative. `since_bytes` is never set and stays 0 from `Session.__init__` (`chassis_session.py:148`). Executed in test 4: the process that died held `(3, 12,428)` (its own start rebuilt 1 for C_n's frame; then two messages). The restart holds `(3, 0)`.

**C_n's frame.** Newest-base replay applies `seq > C_n.covers_seq`, and that starts with C_n's own frame (`chassis_startup.py:1185`). The writer's counter excludes it. The canonical newest row does not add it, though the previous row adds 19,978 for C_n and nothing for C_p's own frame, which also lies inside `(C_p.covers, C_n.covers]`.

## 4. Replay-opened versus retained-only blobs

`rp.record_refs` (retention and GC) and replay reads differ. Retained-only blobs are TURN_RESPONSE `original_blobs`, NOTE_WRITTEN blobs until adoption, foreign note adoption, the LEGACY_IMPORT note blob, and CHECKPOINT `blobs_live`. Replay-opened blobs are DONE (`chassis_replay.py:412`), MSG_APPEND with blob or a non-foreign note (`:312`, `:456`), HISTORY_REPLACED (`:465`), base switches (`:474`) and RECOVERY{conversation_adopted} (`:583`). The test observer confirms replay-opened reads for MSG_APPEND blobs (tests 3, 4) and EXTERNAL_EDIT (tests 5, 6).

## 5. Frame and payload shapes (tests 1, 2: modeled payloads through the actual encoder)

The generator's 13 maximal shapes are reproduced exactly by `cp.encode_frame`, so the frame arithmetic `49 + plen + 66` is the runtime's. The generator's ORIGINAL_EVICTED `{"sha256"}` is **refused** by the runtime (`missing keys: sha`); the runtime shape is 189 bytes. Runtime payloads whose frames exceed the literal maxima:

| Case | Literal | Runtime | Source of the difference |
|---|---|---|---|
| REQUEST_SENT | 208 | 216 / 264 | lineage `uuid4().hex[:16]` (`chassis.py:1146`) / legacy lineage ≤ 64 (`chassis_startup.py:86`) |
| RECOVERY possible_duplicate_spend | 206 | 270 | `detail.next` (`chassis_startup.py:1619`) + lineage |
| UNRUN | 254 | 263 | `"not run: the run ended by handoff in call …"` (`chassis_session.py:367`) |
| DONE | 415 | 1,351 (1,000-character type) | `raised:<type name>` has no cap (`chassis.py:952`); bounded only by `MAX_LEDGER_BODY` |
| MSG_APPEND inline | 4,259 | 24,739 | inline decision on UTF-8 bytes ≤ 4,096 (`chassis_session.py:380`); the body escapes control characters 6:1 |
| MSG_APPEND note adoption | 227 | 244 | `gen` key (`:495`); not in U_b at all (a resume-time unit) |
| CHECKPOINT | 19,978 | 21,746 | `requests.next`, `adopted_mirror_sha256`, `dropped_pending_limit`, pending `mirror_sha256`/`foreign`, lineage (`chassis_replay.py:156`) |

Static only, not executed: TURN_RESPONSE now also carries `originals[]`, `admit_text` and `omitted_notice` (`chassis_envelope.py:321`). Its maximum is bounded by `MAX_LEDGER_BODY` (frame ≤ 1,048,691), not by 680,003. Per turn, ORIGINAL_EVICTED is one record per evicted sha (`chassis_session.py:299–303`). A response with content, reasoning and 32 invalid-JSON arguments over 512 bytes (`chassis_envelope.py:435–438`, ≈ 20 KB, under the 2 MiB response cap) brings 34 originals. Against 64 already retained, that evicts 34 by count, not 17. The omitted-calls notice is no longer a separate record, because the reducer appends it from TURN_RESPONSE (SV021-06). So U_r = 103 and U_b(turn) = 3,333,164 are not runtime maxima either. U_b,max is still dominated by the set_history and base-switch terms below.

## 6. Inequality verdicts

| Inequality | Premises the proof needs | Verdict | Evidence |
|---|---|---|---|
| **Newest bytes < 25,166,144** | (a) every unit ≤ U_b,max = 16,777,536; (b) a threshold check after every unit; (c) `since_bytes` equals outstanding suffix work at all times | **Refuted** at default constants | **Test 5:** a valid 28,311,552-byte list is adopted by A11. The EXTERNAL_EDIT blob is opened once by the restart's replay: suffix after C_n = 2 records, blob 28,311,552 bytes, ≥ 25,166,144 on its own. This is separate from the excluded base-file read, which here is the same 27 MiB again. (a) fails because base switches and A10 adoption are bounded by the 64 MiB readers, not 16 MiB. (b) fails because startup commits ≥ RECOVERY_BYTES_MAX with no checkpoint. (c) fails per test 4. |
| **Newest bytes, restart accounting** | (c) | **Refuted structurally** (injected `bytes_max` 20,000) | **Test 4:** process death leaves 12,428 counted bytes. The restart sees exactly that work after C_n's frame but has `since_bytes = 0`. After two more units, observed work after C_n's frame is ≥ 20,000 with no checkpoint. This is structural evidence; the default-constant analogue (repeated deaths under 8 MiB each) was not executed. |
| **Newest records ≤ 358** | (b); U_r = 103; C_n's frame excluded | **Not proved; premises fail statically** | Recovery core, base switches, adoption (≤ 18 per resume) and GC (2 after every reset) bypass `unit_end`. ORIGINAL_EVICTED can be ≥ 34 per turn. C_n's frame adds 1. **No executed counterexample**: the record counter survives restarts (+1), so the failure needs threshold-bypassing records, which this package did not build. |
| **Previous records ≤ 717** | `C_p` is the checkpoint immediately before `C_n` (two adjacent intervals); C_p's frame is not counted | **Refuted** at default constants | **Test 6:** after A (prev none) and B (prev A), three rounds of external edit → A11 → 240 messages → checkpoint each name `prev = A`, because `_retained_prev` (`chassis_session.py:551`) keeps the bound `.prev.json` while conversation.json is unbound. The checkpoint intervals are 3, 242, 242 and 242 records, all < 256, with peak `since_records` 242. A14 replays seqs 4..733 once each: **730 records > 717**. The intermediate hash matches C_n, the restored file equals C_n, and `.prev.json` is unchanged. The static minimum for this shape is 3 rounds × 236 = 718. Separately, the formula's +1 counts C_n but not C_p's own frame. |
| **Previous bytes < 50,352,266** | both above, plus (a) | **Not proved; premises fail** | Static construction, **not executed**: test 6's shape with two 27 MiB edits in A's interval gives > 54 MB of replay-opened base-switch blobs. The older-prev relation alone also makes the interval count unbounded. |

The four premises that fail, as exact follow-up obligations: (P1) a per-unit byte maximum that includes base-switch, adoption and recovery units; (P2) a threshold evaluation after every unit, including startup, adoption and GC; (P3) `since_bytes` that survives restart; (P4) a bound on the number of intervals between the actual `prev` and C_n. P5 is a records/bytes domain over the current serializer shapes (§5).

## 7. I/O and durability inventory (not the suffix quantity)

Each start reads every retained segment **twice**: in `open` and in the post-transaction rescan (`chassis_startup.py:811`, `:1066`). Test 5 observed exactly 2 reads of the whole segment. Further whole-ledger reads happen in `_consume_ack` (`:1374`, once or twice with an acknowledgement), `_collect` after every checkpoint with `collect=True` (`chassis_session.py:640`), quarantine (`chassis_persistence.py:1405`) and witness verification.

Base files: `_classify_base` reads both conversation files (observed in test 5: 28,311,552 bytes plus the `.prev` bytes). `_retained_prev` hashes both files in full at every checkpoint, up to 64 MiB each (`chassis_session.py:562`; static).

Duplicate blob reads: the live reducer re-reads every blob it has just written (`_commit` → `apply`). This was observed: 1 per blob message in test 3, and the 27 MiB A11 blob in test 5. In test 5 the restart reads the same 27 MiB once as conversation.json and once as the blob.

SV024 added two fences. `sync_inherited` is one segment fsync per resumed writer before its first checkpoint or rotation, if it has not appended (`chassis_persistence.py:1302`). `_fence_intent_inputs` is ≤ 2 segment fsyncs + 1 `ledger/` fsync before a new RECOVERING (`chassis_startup.py:323`); it opens O_RDONLY and fsyncs, so it makes no read call. Both are durability obligations, not suffix bytes. They are counted here and not in the canonical quantity, which they do not change. The maintenance test now asserts both fsyncs precede the first recovery record. Read bounds that bound none of this: segments ≤ 32 MiB each (`MAX_SEGMENT_READ`), blobs/conversation ≤ 64 MiB.

## 8. Modeled versus actual

| Item | Kind |
|---|---|
| Literal frame maxima and the current-shape sizes (tests 1, 2) | **Modeled** payloads through the **actual** encoder. Reachability is argued from cited source lines, not by driving each path. |
| Byte threshold in one process (test 3), restart loss (test 4) | **Actual** runtime, injected small threshold |
| 27 MiB A11 blob (test 5), older prev and 730-record A14 (test 6) | **Actual** runtime, **default** constants, temporary roots |
| Records-newest failure, U_r/ORIGINAL_EVICTED, TURN_RESPONSE maximum, previous-bytes construction, checkpoint file hashing | **Static** only |

## 9. Minimal follow-up design options (separate review; none implemented)

1. **Restate the canonical inequalities over the real unit set** (P1, P5). Add U_b(base switch/adoption) = frame + `CONVERSATION_READ_MAX` and the current shapes. Impact: changes oracle numbers; canonical source review.
2. **Count across restarts** (P3). Startup already replays the suffix; it could set `since_bytes` from the observed frames and opened blobs. Impact: runtime accounting change; small.
3. **Evaluate the threshold after startup, adoption and GC units** (P2). Impact: more checkpoints at start; changes checkpoint timing and ordering. This does not remove the crash window while a large switch blob already exists, so option 1 still needs the switch term.
4. **Bound the previous interval** (P4). Example: after a checkpoint that kept an older `.prev.json`, write one more checkpoint once the current file is bound, so a bound newer snapshot replaces A (SV021-02 allows newer and bound). Alternatively, restate the previous bound as a sum over all intervals since the retained prev. Impact: previous-base preservation and install-ordering policy; design review.
5. **Cap or re-represent accepted external lists** (alternative to 1): a cap at `SET_HISTORY_MAX`, or a retained-file reference instead of a replayed blob. Impact: accepted history sizes and external-edit semantics; product/design decision.

## 10. Separate: semantic-cut maintenance (not a replay-bound claim)

`tests/test_chassis_recovery_live.py::test_a_crash_inside_recovery_never_turns_unknown_into_unrun`. `after-first-record` used to fire on the 2nd `.svl` fsync, which since SV024 is the truncation fence. It now fires on the first `.svl` fsync whose preceding event is a write to that same segment, which is the first recovery record's own append. For TC2 and TC4, the test now checks the following after the crash. The last two events are that write and that fsync. Exactly two `.svl` fsyncs preceded them: the SV024 pre-intent fence and the truncation. The ledger ends `TURN_RESPONSE, SYNTH{[turn,0], unknown_damaged_tail}`. RECOVERING exists, with one ledger quarantine copy. Every existing assertion and the other three cuts are unchanged.

## 11. Commands and counts

Each command was `python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <target>` from the repository root, serial, one per message. Counts are the runner's progress dots.

| Run | Target | Result |
|---|---|---|
| M0 (control) | the maintenance function, old numeric trigger plus new verification | 6 passed, then `[after-first-record-tc2-invoking]` FAILED at the event check: last events `truncate`, `open`, `fsync` of `000000.svl`. The runner stops at the first failure; 1 node not run. Not a pass. |
| M1 | the maintenance function, semantic predicate (final) | **8 passed** |
| B1 | `tests/test_chassis_bounds.py` (final) | **12 passed**: 1 + 7 + 1 + 1 + 1 + 1, each pre-registered exact value matched on the first run |

Final validation: **20 passes in 2 commands**, both on the final tree; neither file changed after its run. No command was denied, retried or overlapped. No broad suite, provider, real session, install, Git call or ad-hoc Python was used. `ruff` was not run, because it needs `uvx` to fetch it.

## 12. Remaining limits

No maximal 64 MiB case, no previous-bytes or newest-records execution, and no default-constant crash loop for restart accounting. RSS, wall-clock and total startup I/O are not measured or bounded. The observer patches `Replay.apply` with a wrapper that calls the original; it attributes reads but has not been shown to be perturbation-free beyond the identical assertions. The shape cases are payload models through the real encoder. Nothing here is real power-loss evidence. Exact replay bounds, real-session authority, merge/deployment and all earlier holds remain unclaimed.

## Files

New: `tests/test_chassis_bounds.py`, `docs/planning-context/sv025/STATUS.md`, `docs/planning-context/sv025/RECEIPT.md`. Modified (test only): `tests/test_chassis_recovery_live.py`, one function's `after-first-record` trigger plus its added verification. No runtime file changed.
