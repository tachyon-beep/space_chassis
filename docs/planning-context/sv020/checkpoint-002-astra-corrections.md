# SV-020 checkpoint 002 — correction 1 (Astra initial review)

2026-10-08, same Opus 5.5 session. Start: clean `4534cc02ec95b45f06b68d6d660ca0992381166f` (coordinator WIP backup, tree `3b7387f0…`). Review: `SV-020-Astra-initial-review.md` (read in full). Correction commit: `8b897931be6986e2da9a299c63060d0925a817f3`. Module SHA-256 `48a48ad68e5878ca0137959a0a6d97b04b0ccfea2da6a2f6874d7aaa70cd1868`.

Regressions were written before the fixes. Each "pre-fix" result below is a bounded-runner run of that exact node against `4534cc0`'s module.

## Finding → fix → test

### SV020-01 (P1) — surviving names were treated as fenced

Fix: `LedgerWriter._fence_namespace` fsyncs `session/` then `ledger/`, once per writer, cached only after both return. It is called by `create` (also when `ledger/` survived), by `continue_after` before returning (so before any gate), and by `open_segment`/`append`. A failure breaks the writer, attempts the marker and raises `PersistenceFailure`. `BlobStore.ensure` fsyncs `blobs/`'s parent on first use, new or surviving, and caches per store. `quarantine_tail` fsyncs `corrupt/`'s parent on every call before the copy, and so before truncation. `session/` itself is an explicit durable-root precondition.

| Test (`tests/test_chassis_durability.py`) | Pre-fix | Post-fix |
|---|---|---|
| `test_sv020_01_a_complete_surviving_segment_is_fenced_before_any_effect`: rotation dies after the complete header's fsync, before `fsync(ledger/)`; the header is scanned into P; `continue_after`, then a REQUEST_SENT gate; `fsync(ledger/)` and `fsync(session/)` returned before the gate frame's write and its effect | **failed**: events before the effect were only `open`, `write`, `fsync` of `000001.svl` | passed |
| `test_sv020_01_a_failed_restart_fence_permits_no_effect`: `fsync(ledger/)` EIO on restart → `PersistenceFailure`, effect never called, segment byte-identical | **failed**: did not raise (the effect ran) | passed |
| `test_sv020_01_a_surviving_ledger_directory_is_fenced_in_session_before_its_first_segment`: Crash before `fsync(session/)` leaves `ledger/`; a fresh create with a failing session fence raises and creates no segment; a fresh create has `fsync(session/)` return before segment 0's `open` | **failed**: did not raise | passed |
| `test_sv020_01_a_surviving_blobs_directory_is_fenced_before_a_blob_is_written`: same for `blobs/`; failing fence → no blob a record could name; the fence precedes the blob temp `open`; one fence per store | **failed**: did not raise | passed |
| `test_sv020_01_a_surviving_corrupt_directory_is_fenced_before_copy_and_truncation`: same for `corrupt/`; failing fence → original tail byte-identical, no copy; the fence precedes the copy `open` and the `truncate` | **failed**: did not raise (the old code copied **and truncated** behind an unfenced `corrupt/`) | passed |

`FaultOps.sync_dir` now records `("fenced", path)` after the fsync *returns*, so these tests assert completion, not just an attempt. Two existing order assertions filter that record out; their meaning is unchanged.

### SV020-02 (P2) — acknowledged TC4 omitted the mirror check

Fix: an acknowledged TC4 plan sets `handoff_mirror_check`. This is a recommendation only: comparison, generation allocation and adoption are SV-021.

| Test (`tests/test_chassis_recovery.py`) | Pre-fix | Post-fix |
|---|---|---|
| O1-8 (P inside an open group): flag asserted alongside both calls unknown, notice, `damaged_tail_acknowledged` | **failed** (`handoff_mirror_check=False`) | passed |
| O1-9 (P after REQUEST_SENT): flag alongside spend, `0f1e:8:2`, notice, no calls | not run separately (same code path) | passed |
| unit-boundary TC4: flag alongside spend, notice, no calls | not run separately (same code path) | passed |
| `test_acknowledgement_is_bound_to_the_stopped_bytes_and_resolution`: none, stale, unbound and bootstrap-preserving acknowledgements → stop, no quarantine, no mirror flag, no calls/records/notices; the directory is byte-identical across planning | passed (control) | passed |

### SV020-03 (P2) — the encoder accepted a body the scanner rejects

Policy: **explicit domain refusal**, not read-side normalisation. `decode_body` is the single rule used by both `parse_record` and `encode_frame`. `encode_frame` refuses (`LedgerError: … unsupported representation …`) any payload whose canonical body would not decode back to the same bytes and a valid payload. The refusal happens before any byte is written and before the writer's seq or chain changes. For this encoder (`json.dumps(ensure_ascii=False, sort_keys=True, separators=(",",":"), allow_nan=False)` then UTF-8 with `backslashreplace`), the refused domain is exactly any string, key or value, containing a high-surrogate code unit (U+D800–U+DBFF) **immediately followed by** a low-surrogate code unit (U+DC00–U+DFFF). Its two `\uXXXX` escapes decode as one non-BMP scalar whose canonical bytes differ. Lone high, lone low, low-then-high and genuine non-BMP scalars round-trip and are accepted. On read, nothing changes: such escaped-pair bytes from any other source remain `body is not canonical` and are never normalised. Duplicate-key and NaN rejection are unchanged.

| Test (`tests/test_chassis_ledger.py`) | Pre-fix | Post-fix |
|---|---|---|
| `test_sv020_03_the_pair_fixture_is_two_code_units` (fixture guard) | passed | passed |
| `…_an_encodable_payload_parses_to_its_own_bytes[pair]` (the review's exact payload) | **failed**: did not raise | passed |
| same `[pair-in-key]`, `[pair-inside-text]` | not run separately | passed |
| same `[lone-high, lone-low, low-then-high, non-bmp-scalar]`: encode then parse gives an equal payload and chain | passed | passed |
| `…_every_accepted_append_scans_and_a_refusal_changes_nothing[pair]`: refusal leaves segment bytes, `next_seq`, chain and `broken` unchanged; a later valid frame scans TC0 | **failed**: did not raise | passed |
| same `[pair-in-key, pair-inside-text]` | not run separately | passed |
| same `[lone-high, lone-low, low-then-high, non-bmp-scalar]`: accepted append + later frame, scan TC0 with both texts | passed | passed |
| `…_escaped_pair_bytes_from_elsewhere_are_still_invalid_not_normalized` | passed | passed |
| existing NaN / duplicate-key / spacing invalid-frame cases | — | passed (unchanged) |

## Runs (bounded runner, `--cpu 23`, one command at a time)

| # | Targets | Result |
|---|---|---|
| 1 | ledger `[pair]` encode node | failed (did not raise) |
| 2 | ledger `[pair]` writer node | failed (did not raise) |
| 3 | 10 ledger SV020-03 nodes (guard, 4 accepted × 2, escaped-pair read) | 10 passed |
| 4–8 | each SV020-01 durability node | failed (as tabled) |
| 9 | recovery O1-8 | failed (mirror flag) |
| 10 | recovery acknowledgement-binding control | passed. An earlier invocation of the same node had its output filtered out by my grep and is not counted. |
| 11 | after the fixes: all 13 SV020 test functions (25 nodes) | 25 passed |
| 12 | all three files | **114 passed** (ledger 60, recovery 28, durability 26) |

During drafting, a shell heredoc that would have appended the SV020-03 tests was refused for its quoting, and was not retried. The tests were added with the editor instead. My first draft had also spelled `PAIR` as a literal scalar; I corrected it to `chr(0xD83D) + chr(0xDE00)` before any run, and a fixture guard test now pins it.

## Preserved and still staged

Preserved: canonical framing, the O1-5 correction, gate ordering, tail-bound acknowledgements, quarantine admission. Production chassis still does not import the module.

Still staged, not claimed:
- a global FSYNC_FAILED marker attempt for every sync failure outside `LedgerWriter` (`write_bytes_durable`, `install_conversation`, quarantine/stop helpers, and `BlobStore` used alone);
- durable RECOVERY_ACK-before-clear ordering;
- next-request identity after hidden turns;
- complete replay, state, notes and live frontier;
- response bounds;
- runtime activation.
