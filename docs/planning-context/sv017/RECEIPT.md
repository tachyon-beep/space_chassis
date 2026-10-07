# SV-017 / R-B4 recorder custody — implementation receipt

Implementation commit **`606a91d3e2c1cd68e23d2221cfcaff652993461a`** on `sv016/recorder-cleared`, parent `afec0a8aab81237c6c09ef55ecf9cd205494d3f6` (the accepted SV-016 base). This document and the SV-016 wording fix are in the following docs commit. For independent Astra review; no merge, push or deployment.

Contract: SV-015 v2 §1.5 (supersedes SV-013 §2.1.8's helper and custody rule); SV-013 §2.1.8 failure/status rules, §2.1.9 outcome table and fixtures R-C1…R-C8; SV-015 v2 O3-1…O3-3, O3-7, O3-9; SV-015 v2 independent review (R-B4 promoted to usable design); SV-016 Astra correction-1 review (status wording).

## 1. What changed

| File | Change |
|---|---|
| `services/common.py` | New: `AppendResult`, `FileOps` (the store's system calls, injectable), `encode_record`, `RecordStore` with `append_record(path, obj, *, fsync)` and `close()`. `append_jsonl` and every other helper unchanged; other services untouched |
| `services/recorder.py` | `write_record_line` replaced by `store_for(root)` / `append_with_custody` / `close_stores`; `AgentState` creates only its slug directory (`parents=False`) and holds the root's store; `main()` refuses to start (exit 1, stderr) without `TRANSCRIPTS_DIR`; handler: free-space preflight and readable-`open` gate before admission; transcript gate before relay; `close.recorded` / `close.dir_unsynced`; `durability_degraded` diagnostic once per file; bounded stderr fallback when the `close` is unwritable; `decode_payload` keeps non-finite numbers as `{"__nonfinite__": literal}` and unparseable nesting/digits as text. New settings: `RECORDER_RECORD_FSYNC` (default on), `RECORDER_MIN_FREE_BYTES` (default 1 GiB) |
| `tests/test_recorder_custody.py` | New, 28 tests |
| `tests/test_recorder_requests.py` | Minimal adjustments: two transcript-failure tests now expect `502 record_failed` (was `500 internal_error`); the rig closes stores at teardown and sets `MIN_FREE_BYTES = 1` so it does not depend on the host's free space; one test now waits for the post-relay `close` instead of racing it |

## 2. Contract → test map (`tests/test_recorder_custody.py` unless noted)

| Contract point | Test |
|---|---|
| §1.5.1 ASCII line, `allow_nan=False` | `test_a_record_is_one_ascii_json_line_and_non_finite_numbers_are_refused`; lone surrogates end to end: `test_recorder_requests.py::test_a_lone_surrogate_in_an_accepted_body_is_recorded_and_settled` |
| §1.5.2 per-path lock, not the Budget's | `test_concurrent_appends_to_one_file_never_interleave` (8 threads × 50 lines, all parse) |
| §1.5.3 create/reopen, slug-dir sync, per-slug root sync (O3-2, O3-7) | `test_the_first_append_fences_the_file_its_slug_and_the_root_in_order`, `test_each_new_slug_gets_its_own_root_sync_and_each_new_file_its_directory_sync` |
| root-level file rule | `test_the_root_level_file_is_fenced_by_the_root_alone` |
| fence failure never durable (O3-7 fault variant) | `test_a_failed_root_sync_is_never_reported_durable_and_is_retried`, `test_a_failed_slug_directory_sync_is_never_reported_durable`; handler: `test_an_unsynced_slug_directory_is_recorded_as_appended_with_dir_unsynced` |
| existing file from a dead process (O3-3) | `test_an_existing_file_from_a_dead_process_is_reopened_and_fenced_again` |
| root precondition (O3-9) | `test_the_recorder_refuses_to_start_without_its_root_and_does_not_create_it`, `test_an_agent_directory_is_created_only_inside_an_existing_root` |
| §1.5.4 boundary from disk every append; restart trace (O3-1) | `test_a_torn_tail_left_by_a_dead_process_is_repaired_by_a_new_store` (real child writes 100 of 300 bytes and `_exit`s) |
| §1.5.5 write loop: short writes, EINTR, 0-byte error → failed, k>0 → partial, zero-byte return | `test_short_writes_and_eintr_still_complete_one_line`, `test_enospc_before_any_byte_is_failed_and_the_next_append_is_clean`, `test_enospc_after_a_prefix_is_partial_and_the_next_line_starts_on_a_boundary` (R-C2, with the concatenation negative control), `test_a_zero_byte_write_ends_the_append_instead_of_spinning` |
| §1.5.6 fdatasync: durable / appended+dir_unsynced / appended_fsync_failed + sticky degraded | `test_a_failed_data_sync_is_readable_degraded_and_stays_degraded`, `test_without_a_data_sync_a_line_is_appended_not_durable` |
| descriptor/path bounds, shutdown | `test_the_path_count_is_bounded_and_a_closed_store_writes_nothing` |
| R-C1 transcript fails after 200 + usage | `test_a_failed_transcript_withholds_the_answer_and_the_actual_usage_is_charged`; also `test_recorder_requests.py::test_known_usage_is_settled_before_a_transcript_failure`, `::test_a_completion_withheld_after_a_transcript_failure_is_not_relayed` |
| R-C2 partial then clean | `test_a_partial_transcript_is_withheld_and_the_next_turn_is_recorded_cleanly` |
| R-C3 transcript and events fail | `test_when_transcript_and_events_both_fail_one_bounded_line_reaches_stderr` (fixed keys; no client or recorder key in stderr; open without close) |
| R-C4 open fails | `test_an_unrecordable_open_refuses_before_admission_or_contact` |
| R-C5 low space | `test_low_space_refuses_before_the_open_and_before_any_spend` (and unknowable space → `record_unavailable`) |
| R-C6 fdatasync EIO | `test_a_failed_data_sync_still_relays_and_is_reported_once` |
| custody rule on success and non-2xx | `test_success_and_provider_errors_are_relayed_with_their_record_class` |
| R-C7 (kept) | `test_recorder_requests.py::test_a_refused_connection_is_closed_once_and_the_request_refunded`, `::test_a_refused_network_connection_is_refunded_too` |
| R-C8 process death, no fabricated close | `test_a_recorder_killed_mid_request_leaves_an_open_and_no_fabricated_close` (real child recorder, SIGKILL while forwarding = cut R3, restart, second boot answers) |
| serializer totality for responses | `test_a_non_finite_response_number_is_recorded_as_a_marker` |

## 3. Checks run (bounded runner, `--cpu 23`, one command at a time)

| Run | Targets | Result |
|---|---|---|
| 1 | `tests/test_recorder_custody.py` | 28 passed |
| 2 | budget, requests, custody files + 4 `test_services.py` recorder nodes + `test_run_end_to_end.py::test_a_run_reaches_the_model_through_the_recorder`, `::test_the_recorder_injects_a_credential_the_agent_never_has` (`SC_SCRATCH` inherited as `/tmp/sv017-integration-check`) | **failed at 40**: `test_an_estimate_too_large_for_the_socket_is_refused_before_the_upstream` read events before the post-relay `close` existed — a pre-existing test race exposed by sync latency, not a custody defect. Fixed the test to wait |
| 3 | same as 2 | **116 passed**, 2 warnings (`PytestUnhandledThreadExceptionWarning` from the two deliberate `SystemExit` tests, as in SV-016) |

Pre-fix failures were not run for the new custody tests: they exercise a new API (`RecordStore`) that does not exist at `afec0a8`, so they would fail on import, which discriminates nothing. Behaviour-level evidence of the change: the two SV-016 tests that asserted `500 internal_error` for a transcript failure passed at `afec0a8` and now assert `502 record_failed`; the R-C2 test carries an explicit negative control (concatenation without the boundary repair is not valid JSON).

Not run: the full repository suite; ruff; live disk faults; power loss.

## 4. Deployment preconditions

- **One recorder process per `TRANSCRIPTS_DIR`** (M-5). Two writers would race the boundary check.
- **`TRANSCRIPTS_DIR` exists before start, and its own durability is the host's.** `scripts/prepare_host.sh` creates `volumes/transcripts`; compose bind-mounts it read-write for the recorder only. The recorder now exits 1 without it. Host-side root creation durability is unverified [N:D].
- Free-space threshold `RECORDER_MIN_FREE_BYTES` (1 GiB) is a prediction, not a reservation: concurrent writers can still fill the disk.
- `RECORDER_RECORD_FSYNC` on by default; every record line costs a `fdatasync` (and directory syncs on first use of each file).

## 5. Evidence limits and residual risks

- **No power-loss or crash-consistency claim.** Syncs were mocked or real on a test filesystem; "durable" means the syscalls returned (honest-flush assumption M-2). Real filesystem behaviour after `fsync` error and per-slug directory-entry persistence are evidence gates E-K1/E-K2/E-K6.
- **No latency claim.** Syncs and appends block under a per-file lock. Without R-B3 there is no deadline: a stalled filesystem stalls the requests writing to that file (and the `open`/`close`/transcript steps), with no watchdog.
- **Diagnostics are written in-line**, not by a separate writer thread (that design is R-B3's). A stalled `recorder.jsonl` stalls the request that is reporting degradation.
- Sticky `degraded` is per path and per process; it is reported once per file per process in `recorder.jsonl` (and once in the container log). A restart forgets it.
- After an `fsync` error the descriptor is dropped and reopened; the bytes already written remain visible (`appended_fsync_failed`). What the page cache did is unknown [N:K].
- `close.recorded` reports the **transcript** append class only; the `open`/`close` events' own classes are not recorded beyond the gate (`open` must be readable; an unreadable `close` goes to stderr).
- `decode_payload` change (non-finite marker, nesting/digit fallback to text) is the minimum taken from R-B3's response rules so the strict serializer cannot refuse a valid upstream answer. No other R-B3 behaviour (response cap, SSE usage, pre-scan) is implemented.
- Shutdown: production `main()` does not close stores explicitly; process exit closes descriptors. Tests close them in teardown.
- `status` semantics (SV-016 wording corrected): `close.status` is the selected/attempted status, not proof of delivery; `relayed` records completion of the recorder's write of the upstream response, not consumption.
