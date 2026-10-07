# SV-020 chassis persistence foundation — implementation receipt

Branch `sv016/recorder-cleared`. Accepted pre-foundation base `6f6c054f396ccbd30e940267ebc9b9e0d6e646d9` (accepted runtime `2f0567c`, receipt `bb4812a`, coordinator provenance `6f6c054`). The interrupted draft was checkpointed by the coordinator at `afe11a0c35721a22e5e3accdb5718558ff432d01` (file SHA-256 `ea35302a6ef8cbad007c3ac588a704b6549ebc43430898082db690d4cdea08a5`, untested). This session assessed that draft against its sources, corrected it, and tested it. For independent Astra review. I made no push, merge or deployment.

| Commit | Unit | Revert |
|---|---|---|
| `61833d8a0f73155a0e6cfb4e5e011008c002d0be` | draft corrections in `services/chassis_persistence.py` | with the tests (they assert the corrected behaviour) |
| `add1627444c1eb1e33a7371734a5cfe711b61752` | `tests/test_chassis_{ledger,recovery,durability}.py` | alone |
| `4534cc02ec95b45f06b68d6d660ca0992381166f` | STATUS, RECEIPT, checkpoint 001 | docs only |
| `8b897931be6986e2da9a299c63060d0925a817f3` | **correction 1** (Astra SV020-01/02/03): module + regressions | alone (tests assert the corrected behaviour) |
| this docs commit | checkpoint 002, RECEIPT §3a, STATUS | docs only |

Module SHA-256 after the initial correction: `62155833a4b19d5b7f0765d73989a5f4312742a094431196184abb6496588bbe`. **After correction 1: `48a48ad68e5878ca0137959a0a6d97b04b0ccfea2da6a2f6874d7aaa70cd1868`.** **No production code imports it** (repository search: only the three test files and STATUS name it). Chassis startup, `run.json` (no `format`), conversation storage and every live request/tool path are unchanged. `common.write_json_atomic`/`write_text_atomic` and the recorder `RecordStore` are untouched and not repurposed.

Sources read: SV-020 Astra preflight; SV-015 v2 §1.1–1.4 (full), §4.1, §4.2, §4.9–4.10; v2 independent review V2-06; SV-013 §2.2.2 A0–A15 table, §2.2.3 records and call texts, C-D1/C-D3 rows; SV-015 v2 literal values (ledger entries) and literal generator lines 1–51 (read, not executed); SV-020 literal-source addendum; SV-020 bounded targets.

## 1. Draft assessment and corrections (`61833d8`)

The draft's framing, D13 texts (verbatim against SV-013 lines 582–587), TC0–TC4 ordering, probe and gate-before-effect structure matched the sources. Defects found and corrected:

| # | Draft defect | Correction | Source |
|---|---|---|---|
| 1 | `segment_name` `{:06d}` with a 6-digit-only reader: segment 1,000,000 written but never read | `MAX_SEGMENT_NO = 999_999`; refusal before any file is created | V2-06(3) width domains |
| 2 | `json.loads` accepted `NaN`, duplicate keys, other spellings | body must equal `canonical_body(payload)` | v2 §1.2 BODY definition |
| 3 | segment numbers not checked for contiguity | `number == previous + 1` | v2 §1.3 contiguous prefix |
| 4 | a hand-built scan whose tail is a valid frame would be classified TC2 | `classify_tail` raises: rescan | O1-5 correction (see §3) |
| 5 | TC2 `LEDGER_HEADER` → notice | stop `ledger_damaged_at` | v2 §1.4.10 rotation row "header damage → A2" |
| 6 | `RECOVERY` details named the type `"INVOKING"` | type id hex (`"05"`) as v2 O1-1a/O1-2 state | v2 §4.1 |
| 7 | TC4 acknowledgement not bound to the damaged bytes | `tail_stop_detail` puts the tail SHA-256 in `STOPPED`; `acknowledge_stop` carries it; the plan requires it to match | v2 §1.3 acknowledgement is permission for *this* stop |
| 8 | never-invoked calls (`admit ≠ invoke`) kept a group open indefinitely | openness counts admitted calls only | v2 §1.3 call table row 2 |
| 9 | `quarantine_tail` could truncate any tail, including an unacknowledged TC4 | requires a plan with `action == continue` and `quarantine_tail`, for the same tail length | v2 §1.3 TC4 "nothing truncated" |
| 10 | FSYNC_FAILED written on a failed `open` (no byte in doubt); not on a blob sync failure | marker only after write/sync errors; blob failure breaks the writer and attempts the marker | v2 §1.4.9 |
| 11 | an empty segment 0 left after quarantining a torn creation could not be recreated | `create` reuses an existing **empty** segment 0, refuses a non-empty one | v2 §1.4.8 |

## 2. Contract → test map (`add1627`)

All tests use temporary roots, literal bytes and `DurableOps` fault injection. "Pure" means bytes in, plan out; no file is touched.

**`tests/test_chassis_ledger.py` (44)**
| Point | Test |
|---|---|
| O1-11: 144-byte frame, line SHA-256 `2b3281e0…e7f1`, `hck` over bytes 0–31 = `b315afbdc6651093`; 33-byte span `1090633068e00112` rejected; `encode_frame` reproduces frame and chain `7a09058a…fccb` | `test_o1_11_header_check_covers_bytes_0_to_31_and_the_literal_frame_reproduces` |
| 49/32/66/117 byte constants; genesis | `test_frame_sizes_follow_the_fixed_header_and_trailer` |
| invalid header check, type, seq, body key, chain, short, trailer, non-object, missing key, bool counter, NaN, spacing, duplicate key, non-JSON | `test_an_invalid_frame_is_named_for_its_first_defect[14]` |
| declared `plen > MAX_LEDGER_BODY` refused before the body is read | `test_a_declared_body_over_the_maximum_is_refused_before_it_is_read` |
| seq domain 1..10¹²−1 (bool, 0, negative, 13 digits) | `test_a_seq_outside_…[4]`, `test_the_largest_seq_still_fits_its_field` |
| counter widths, attempt ≥ 1, `raised:` type, blob hash, CKG, call order/admit, `call_key`, unknown type, NaN | `test_an_unencodable_record_is_refused[13]` |
| oversize body / 13th seq digit refused with the segment byte-identical | `test_an_oversize_body_…`, `test_the_writer_refuses_a_thirteenth_seq_digit_without_writing` |
| segment number width | `test_the_segment_number_is_bounded_by_its_file_name_width` |
| writer ↔ scanner round trip across rotation; header payload chain continuity | `test_writer_and_scanner_round_trip_across_a_rotation` |
| invalid record / trailing bytes in a non-newest segment → A2 | `test_an_invalid_record_in_an_older_segment_…`, `test_bytes_after_p_in_an_older_segment_stop` |
| foreign lineage never forms P | `test_another_lineages_ledger_never_forms_a_prefix` |
| skipped segment number → TC2 header → stop | `test_a_skipped_segment_number_does_not_continue_the_prefix` |
| `LEDGER_HEADER` inside a segment invalid | `test_a_ledger_header_inside_a_segment_is_invalid` |

**`tests/test_chassis_recovery.py` (28)**
| Point | Test |
|---|---|
| O1-1a: byte 60 `x→9` (SHA-256 `9eb741ae…681e`) → TC2 05; call_a unknown (damaged-tail text), call_b unrun; `RECOVERY{damaged_final, "05", 144}` | `test_o1_1a_…` |
| O1-1b: identical bytes built independently → equal plans | `test_o1_1b_…` |
| O1-2: first 100 bytes → TC1 05; unrun; `torn_incomplete{100, "05"}` | `test_o1_2_…` |
| O1-3: 23 bytes `SVL1 000000000023 05 00` → TC1 | `test_o1_3_…` |
| O1-4: 300 bytes, header check fails → TC4 stop, no quarantine, no calls | `test_o1_4_…` |
| **O1-5 corrected**: valid INVOKING + 10 bytes → frame in P, TC1, call **unknown** (scanner on disk + literal parse + classifier refusal) | `test_o1_5_corrected_…` |
| O1-5 genuine TC3: invalid full frame + 10 bytes → TC3 stop | `test_o1_5_genuine_tc3_…` |
| O1-10: later-valid frames at 144, 454, 598 → A2 at 23 | `test_o1_10_…` |
| C-D1: seq 23 damaged (body or header), 24–26 follow → A2 `ledger_damaged_at` 23; directory byte-identical | `test_c_d1_…[body, header]` |
| O1-6: damaged `REQUEST_SENT{8,1}` after checkpoint → spend; next `0f1e:8:2` | `test_o1_6_…` |
| O1-8: 908-byte tail SHA-256 `20a64606…0672` reproduced; TC4 stop; acknowledged → call_a **and** call_b unknown, hidden-turn notice, `damaged_tail_acknowledged{908}` (v1 rule's "call_b unrun" excluded) | `test_o1_8_…` |
| O1-9: 818-byte tail SHA-256 `35d55b60…9b95` reproduced; TC4; acknowledged → spend, `0f1e:8:2`, notice, no call listed | `test_o1_9_…` |
| acknowledgement: stale tail, unbound, bootstrap-preserving all stay stopped; STOPPED not removed | `test_acknowledgement_is_bound_…` |
| `acknowledge_stop` checks reason and resolution | `test_acknowledge_stop_checks_…` |
| acknowledged TC4: `bad_args` call stays not invoked; unit-boundary TC4 → no calls, spend, notice | two tests |
| C-D3: `raised:ValueError`, 23 bytes, `34a19b10…b75f`, blob missing → exact D13 raised text; returned → exact returned text | `test_c_d3_…`, `test_a_returned_result_…` |
| present blob → known; corrupted blob → payload lost | `test_a_present_blob_…` |
| TC2 `DONE` → invoked call stays unknown | `test_a_damaged_final_done_…` |
| TC2 `CHECKPOINT`/`NOTE_WRITTEN`/`MSG_APPEND` per-type rule | `test_tc2_at_a_unit_boundary_…[3]` |
| quoted frame inside a TC2 body not probed; negative control with outer header damaged → A2 | `test_a_quoted_frame_…` |
| reference frontier transitions; injected frontier decides TC2 vs TC4 | two tests |
| scan + classify + plan of a torn tail changes no file | `test_scanning_classifying_and_planning_…` |

**`tests/test_chassis_durability.py` (21)**
| Point | Test |
|---|---|
| O1-7: ledger fsync EIO → tool not started, writer broken, marker written | `test_o1_7_a_failed_invoking_sync_…` |
| O1-7: every fsync fails → marker attempted, `marker_written False`, no marker/temp; process-only restart sees INVOKING → unknown | `test_o1_7_when_the_marker_fails_too_…` |
| O1-7: host loss leaves the unsynced frame absent/short → TC0/TC1 → unrun (true: effect never ran) | `test_o1_7_after_host_loss_…[absent, short]` |
| REQUEST_SENT gate write/fsync failure never sends | `test_a_failed_request_gate_never_sends[2]` |
| effect called only after write + fsync events; non-gate types refused | `test_a_gate_calls_its_effect_only_after_…` |
| blob rename and `blobs/` fsync precede the DONE write; failed blob → no DONE, call unknown | two tests |
| `write_bytes_durable` order and failure leaves the old file, no temp | `test_write_bytes_durable_…` |
| open failure: no marker | `test_an_open_failure_writes_no_marker_…` |
| O2-5: crash before `ledger/` fsync; name lost → TC0 at old segment, `n+1` recreated, `first_seq = last+1`, no gap; empty survivor reused; torn header quarantined then reused | three tests |
| segment 0 recreated only when empty | `test_segment_0_can_be_recreated_only_when_empty` |
| O2-7: at file cap no copy, no truncation, `STOPPED{corrupt_quarantine_full}`, tail byte-identical | `test_o2_7_…` |
| strict byte cap (limit−1 refused, limit admitted); copy equals tail; truncation to P | `test_the_byte_cap_is_strict_with_no_overshoot` |
| copy fenced before truncation; copy fence failure → no truncation | `test_the_copy_is_durable_before_the_truncation` |
| unacknowledged TC4 / mismatched plan never truncated | `test_an_unacknowledged_ambiguous_tail_is_never_truncated` |
| CK1 bytes equal `common.write_json_atomic` output; CK3 link before rename, CK4 dir fsync last; failure keeps the installed file | two tests |

## 3. O1-5 source-oracle correction

v2 §4.1 O1-5 states "the 144-byte valid frame + 10 bytes → TC3 → A2". Under v2 §1.3's contiguous-prefix definition that frame is valid, so it is in P and the 10 bytes are a TC1 tail. Its INVOKING is in P, so the call is **unknown**, not unrun. This is the contradiction identified in independent review V2-06(2) and SV-020 preflight item 3. Both fixtures are kept: corrected O1-5 (valid + 10 → TC1, unknown) and genuine TC3 (invalid full frame + 10 → stop). The scanner was not weakened to match the erroneous expectation. Its classifier refuses a scan that presents a valid frame as a tail.

During testing, two of my own expectations (not source oracles) were stricter than written: a valid frame *after* a damaged one is A2 by the probe (v2 §1.3 probes everything outside the first frame's declared extent, before TC3). I corrected the foreign-lineage test and C-D1's body variant to A2, which is SV-013's stated C-D1 outcome.

## 3a. Correction 1 (Astra initial review, `8b89793`)

Full finding → fix → test map with per-node pre-fix outcomes: `checkpoint-002-astra-corrections.md`. In summary:

- **SV020-01 namespace fences.** Assumption, stated as a precondition: `session/` is a durable root, and its own name in its parent is not fenced by this module. Every name below it that this module depends on is fenced by a returned directory fsync in the current process before first dependence, whether the name is new or survived a process death:
  - `ledger/` in `session/`, and segment names in `ledger/`: once per `LedgerWriter`, before any write, in `create` and in `continue_after` before it returns. A gate therefore cannot run before both fences.
  - `blobs/` in `session/`: once per `BlobStore`, before the first blob write. Each blob name is then fenced in `blobs/` by `write_bytes_durable`, before the record that names it.
  - `corrupt/` in `session/`: on every `quarantine_tail`, before the copy. The copy's name is fenced in `corrupt/` before truncation.

  Existence checks (`is_dir`/`exists`) now only decide whether to `mkdir`; they never replace a fence. A fence failure is `PersistenceFailure`, and the dependent effect, blob write or truncation does not happen. The fixtures are ordered injected faults, not power-loss experiments.
- **SV020-02.** Every acknowledged TC4 plan recommends the HANDOFF.md mirror check (open group, after REQUEST_SENT, unit boundary). Unacknowledged and stale acknowledgements stay stopped with no recommendations and no file change. Comparison and adoption are SV-021.
- **SV020-03 representation policy.** Explicit refusal before any byte, seq or chain change of any payload whose canonical body would not decode back to the same bytes and a valid payload. Within supported JSON payloads with string keys, this includes a string (key or value) containing a high-surrogate code unit immediately followed by a low-surrogate code unit. Lone surrogates (in either order) and genuine non-BMP scalars are accepted and scan. The read side is unchanged: escaped-pair bytes from elsewhere remain invalid and are never normalised. Duplicate-key and NaN rejection are kept.

Counts after correction 1: **114 passed** (ledger 60 = 44 + 16; recovery 28, with assertions strengthened in four tests; durability 26 = 21 + 5).

## 4. Runs (bounded runner, `--cpu 23`, one command at a time)

`python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <targets>`

| # | Targets | Result |
|---|---|---|
| 1 | `tests/test_chassis_ledger.py` | 1 failed (my TC3 expectation; see §3), stopped |
| 2 | same | 44 passed |
| 3 | `tests/test_chassis_recovery.py` | 1 failed (test helper passed size into `outcome`), stopped |
| 4 | same | 28 passed |
| 5 | `tests/test_chassis_durability.py` | 21 passed |
| 6 | mutation: `gate` runs effect before append; O1-7 node | failed as required (`['tool'] == []`) |
| 7 | mutation: v1 TC4 rule (frontier only); O1-8 node | failed as required (call_b `unrun`) |
| 8 | mutation: copy into `corrupt/` before admission; O2-7 node | failed as required (extra file) |
| 9 | all three files, committed module (mutations reverted; SHA-256 equal to `HEAD`) | 93 passed |

Before any run, the C-D1 header variant was switched to the generator's `damage_headers` rule, so the damaged byte always changes value.

## 5. Not implemented; not claimed (activation prerequisites)

- **Integrated K-D1/K-D2 activation**: the full A0–A15 authority table with the v2 A3 replacement (legacy corruption stop, A7 lost ledger, A15 checkpoint ahead, A11/A12 external edit/deletion, A14 previous-base hash validation), `format: 2` publication, and startup recovery. A writer-only rollout is unsafe; nothing here is wired into the chassis.
- **Gate placement**: REQUEST_SENT before the HTTP effect, INVOKING before each tool body, blob durable before DONE, at the live boundaries (`chassis.py` request/tool/checkpoint/resume paths). Only the primitives (`LedgerWriter.gate`, `append_with_blob`) exist.
- **Legal-next frontier from live state**: `legal_next_types` is a reference derivation over P and `classify_tail` accepts an injected frontier. That production derives the same frontier from its state machine is unproven.
- **Complete checkpoint state** (v2 §1.4.2: notes generations/pending blobs, request attempts, originals, history epochs) and honest notes/identity mutation recording with K-F1. Only the CKG invariant is validated on a CHECKPOINT body. No checkpoint writer, replay functions, previous-base replay, GC or `GC_INTENT` execution.
- **K-E2 bounds**: no maximal-shape or 358-record / 25,166,144-byte recovery-bound claim. `MAX_LEDGER_BODY` is enforced before writing. Integer fields named in `COUNTER_FIELDS` are bounded to 12 digits. Other numeric/string fields carry no width proof. Read bounds (`MAX_SEGMENT_READ` 32 MiB, `MAX_BLOB_READ` 16 MiB) and `MAX_CORRUPT_FILES` 64 / `MAX_CORRUPT_BYTES` 64 MiB are local choices [CM], not design values.
- **Operator controls**: `acknowledge_stop` is a tested capability. No CLI, no real stop acknowledged, no RECOVERY_ACK append or STOPPED removal sequencing in a run. Bootstrap-preserving remains the operator's explicit choice. TC4 next-request numbering at a unit boundary (`last_turn + 1`, attempt 2) is a conservative placeholder pending live state.
- **Exception identity**: `chassis_persistence.PersistenceFailure` is separate from the chassis's. Unifying them is an activation step.
- **Global FSYNC_FAILED coverage** (Astra, preserved staging limit): only `LedgerWriter` attempts the v2 §1.4.9 marker itself (including on a namespace-fence failure). `write_bytes_durable`, `install_conversation`, `quarantine_tail`, `write_stop` and a standalone `BlobStore` raise `PersistenceFailure` without attempting it. The session-level error boundary must guarantee the attempt for every relevant sync failure, without recursing on marker failure, before activation.
- **RECOVERY_ACK-before-clear** ordering is the caller's responsibility at activation. `acknowledge_stop` only prepares permission.
- **Durable root**: the session directory's own name is a deployment precondition, not fenced here.
- Out of scope: H/T/Q, pump, notes adoption, policy choices, bootstrap actions, `NOT_INVOKED` admission texts (K-E2's; the plan reports status only).

## 6. Evidence limits

- These are pure simulations and injected faults. They are **not** C-1a…f, C-K1…K7, O2-2 or C-T1…T8 real chassis crash/restart passes. They give no real power-loss, kernel, storage, provider or deployed-supervisor evidence.
- `Crash` stands in for process death, and file deletion/truncation stands in for what M-2 permits a host loss to lose. Real fsync/rename semantics are assumed, not measured.
- Repository full suite, ruff and other repository tests were not run (phase constraint).
- Negative controls are the three mutations in §4. The other tests were not each mutation-checked.
