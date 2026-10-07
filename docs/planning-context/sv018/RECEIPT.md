# SV-018 / R-B3 recorder bounds — implementation receipt

Branch `sv016/recorder-cleared`, base `11e0e26fd5e3e78f2b05f383a2493ef8cd8f1547` (accepted SV-016 + SV-017). Commits: part 1 (mechanisms + integration, checkpoint) and part 2 (regressions, compose, this receipt) — ids in `STATUS.md` and the final report. For independent Astra review; no merge, push or deployment.

Contract: SV-015 v2 §2.1, §2.2, §2.6, O3-4…O3-6, O4-3…O4-7 (supersede SV-013's relative timeout coupling and memory multipliers); retained SV-013 §2.1.7, §2.1.9, §2.1.11 non-superseded defaults, R-B2, R-B4…R-B8; the coordinator's preflight decisions (listed in `STATUS.md`).

## 1. What changed

| File | Change |
|---|---|
| `services/recorder.py` | `Timing` (from env; `timing_problems`), `CLOCK`/`now()`, `Deadlines`; `Watchdog` (heap of owned/pending entries; fire marks and shuts down under its own lock; cancel-before-close ownership; compaction of cancelled entries; bounded diagnostics deque + writer thread, `dropped` cleared only by reported amounts); `CONNECTIONS` cap before thread spawn with canned 503; `Accepted` carries t0; handler: header phase (watchdog + per-op timeout, canned 408 with no invented close), `parse_request` refuses a fired header phase, one request per connection (`Connection: close`), latest-start check, slots before the body, `_read_body` under the body deadline (408 body_deadline / 400 short_body), `prescan` (400 structure_limit), `MemoryBudget` reservation (429 memory), forward check after the open (503 deadline_insufficient), `Upstream` with watched UDS/TCP/TLS connections (TLS handshake under the watch, socket rebound after wrap), explicit send loop, `http.client.HTTPResponse` on the watched socket, capped read (`MAX_RESPONSE` + 1), incomplete Content-Length → transport error, fired flag classifies an EOF; `view_response` (cap → raw prefix, unknown usage; SSE by content; response pre-scan → raw + `structure_limit`); transcript gains `usage`, `usage_class`, `structure_limit`; `close` gains `elapsed_s`, `custody_s`, `deadline_overrun`; `REQUEST_MAX_BYTES` default 2 MiB; `UPSTREAM_TIMEOUT_SECONDS` (600 s per operation) replaced by `RECORDER_IO_TIMEOUT_SECONDS` (60 s per operation); startup refuses an inconsistent profile |
| `docker-compose.yml` | recorder `REQUEST_MAX_BYTES` default 2097152; recorder now receives `RECORDER_TIMEOUT_SECONDS` (same default 600 as the agents), comments at both sites to keep them equal |
| `tests/test_recorder_bounds.py` | new, 22 tests |
| `tests/test_recorder_deadlines.py` | new, 16 tests |

No existing test was changed in this package.

## 2. Design → test map

| Design point | Test(s) |
|---|---|
| t0 at accept; 570/540/480; body from header completion, capped by latest start | `test_recorder_deadlines.py::test_the_deadlines_are_anchored_at_accept` |
| O3-4 arithmetic and the 620 negative control | `::test_o3_4_a_late_start_still_ends_at_t0_plus_540_and_answers_before_the_client_gives_up` |
| O3-4 real sockets (scaled): silent upstream cut at t0 + cutoff, 502 before client timeout, no success line | `::test_o3_4_a_silent_upstream_is_cut_at_the_absolute_deadline` |
| absolute (not connect-relative) upstream deadline after a slot wait | `::test_o3_4_a_slot_wait_does_not_move_the_upstream_deadline` |
| forward check → 503 deadline_insufficient, open recorded, no admission/contact (fake 481 s stall); boundary at exactly 480 proceeds | `::test_a_request_past_its_latest_start_after_the_open_is_refused_before_admission`, `::test_a_request_exactly_at_its_latest_start_still_goes` |
| O3-5 custody stall: ready at 600, `custody_s` 70, `deadline_overrun`, recorded, not withheld, client gone → `relayed false` | `::test_o3_5_a_custody_stall_is_reported_not_hidden` |
| startup refuses inconsistent profiles | `::test_an_inconsistent_profile_is_refused_at_startup` |
| R-B5 chunked drip cut by the watchdog | `::test_r_b5_a_dripping_chunked_upstream_is_cut_at_the_deadline` |
| R-B2 body drip → 408 within body deadline + tick; close, no open | `::test_r_b2_a_dripping_body_gets_a_408_within_its_deadline` |
| header drip → canned 408, no close, `request_overdue` via the writer | `::test_dripping_headers_get_a_canned_408_and_no_invented_request` |
| watchdog fire/cancel; SHUT_RD; diagnostics queued | `::test_a_due_entry_fires_and_shuts_its_socket_and_a_cancelled_one_does_not` |
| stale entry never reaches a reused descriptor | `::test_a_stale_entry_never_reaches_a_reused_descriptor` |
| cancelled entries retired (bounded heap) | `::test_cancelled_entries_do_not_pile_up_behind_long_deadlines` |
| fire during a TLS wrap shuts the new socket | `::test_a_deadline_that_fires_during_a_tls_wrap_shuts_the_new_socket_too` |
| O3-6 blocked writer: sockets shut, queue 2, dropped 1, failed write keeps the count | `::test_o3_6_a_blocked_diagnostic_writer_never_delays_a_deadline` |
| pre-scan counting; strings/escapes not structure | `test_recorder_bounds.py::test_the_pre_scan_counts_containers_strings_keys_and_scalars`, `::test_punctuation_and_escapes_inside_strings_are_not_structure` |
| O4-3 (no json.loads, no reservation), O4-4, O4-5 (+ scalar values cap), O4-6 | `::test_o4_3_…`, `::test_o4_4_…`, `::test_o4_5_…`, `::test_o4_6_…` |
| reservation arithmetic (98 + 50 = 148 MiB; 5 fit in 768; typical 68.9) | `::test_the_reservation_arithmetic_matches_the_design` |
| O4-7 contention and handler 429 memory before parse, refund/no spend, exact release | `::test_o4_7_a_second_worst_case_reservation_waits_then_is_refused`, `::test_o4_7_a_request_without_memory_is_refused_before_parsing_and_spends_nothing` |
| release under a control exception (memory, slot, phases) | `::test_resources_are_released_when_a_control_exception_unwinds_after_the_reservation` |
| response cap (SV-013 R-B4) under Content-Length, chunked and close-delimited; prefix usage not trusted; exactly-at-cap relayed; cut-short body | `::test_a_response_over_the_cap_is_recorded_in_part_and_not_relayed[length/chunked/close]`, `::test_a_response_exactly_at_the_cap_is_relayed_whole`, `::test_a_body_cut_short_before_its_content_length_is_a_transport_failure` |
| R-B6 / R-B7 SSE; dialect rules; over-structured event | `::test_r_b6_…`, `::test_r_b7_…`, `::test_sse_dialect_variants_are_parsed_by_the_stated_rules`, `::test_an_over_structured_sse_event_is_flagged_in_the_record` |
| connection cap before a handler exists | `::test_a_connection_over_the_bound_gets_a_canned_503_and_no_handler` |
| one request per connection | `::test_one_request_per_connection_and_the_response_says_so` |
| phase/memory cleanup after ordinary and refused requests | `::test_every_phase_is_released_after_ordinary_and_refused_requests` |
| R-B8 client disconnect; accounting/custody/credential invariants | retained SV-016/017 tests (all passing) |

## 3. Checks run (bounded runner, `--cpu 23`, one command at a time; `SC_SCRATCH=/tmp/sv018-integration-check`)

| Run | Targets | Result |
|---|---|---|
| 1 | `tests/test_recorder_requests.py` (after integration) | 46 passed, 2 expected warnings |
| 2 | `tests/test_recorder_custody.py` | 33 passed |
| 3 | `tests/test_recorder_bounds.py` | 22 passed, 1 expected warning |
| 4 | `tests/test_recorder_deadlines.py` | stopped at 8: the slot-wait test held the slot 1.0 s against a 0.6 s scaled body deadline, so the agreed contract correctly answered 408 body_deadline. Test changed to a 0.4 s wait (the deployed 30 s wait is likewise shorter than its 60 s body deadline) |
| 5 | same | stopped at 10: the test helper read only the reply's headers; the 408 was correct. Helper reads to EOF |
| 6 | same | 16 passed |
| 7 | complete selected set: budget, requests, custody, bounds, deadlines files + 4 `test_services.py` recorder nodes + 2 `test_run_end_to_end.py` route/credential nodes | **159 passed**, 3 warnings — `PytestUnhandledThreadExceptionWarning` from the three deliberate `SystemExit` injections (two SV-016, one new) |

No pre-fix runs: the new tests exercise new mechanisms. The negative controls are arithmetic (O3-4's 620/621) and behavioural (truncated prefix with valid usage stays unknown; stale entry vs reused descriptor; blocked writer vs deadlines).

## 4. Deviations and choices, stated

- **Header timeout** gets a canned 408 and a rate-limited counter, and no `close`: no request was parsed. If the deadline fires as the headers complete, the parsed request is refused `408 header_deadline` with a `close`.
- **`request_overdue`** is enqueued when a phase fires (v2 §2.1), not after an extra `OVERDUE_GRACE` (SV-013).
- **Pre-slot latest-start check:** a request already past its latest start before taking a slot is refused `503 deadline_insufficient` with no `open` (the post-open forward check remains).
- **Body strictness:** once the body deadline has passed, the request is refused even if the remaining bytes were already buffered.
- **Inline diagnostics kept:** `durability_degraded`, `recorder_start` and `slug_refused` stay synchronous (accepted SV-017 behaviour). Only watchdog diagnostics and counters go through the deque.
- **Per-operation timeout** is now 60 s (`RECORDER_IO_TIMEOUT_SECONDS`), not the former 600 s `UPSTREAM_TIMEOUT_SECONDS`; that name is no longer read.
- **Memory:** every admitted request reserves its own M_req plus the fixed worst-case M_resp (50 MiB at defaults), so at most 15 small requests hold reservations at once within 768 MiB (more than the 12 slots).
- **Response-cap record:** `raw_body` is the kept prefix decoded with `backslashreplace` (invalid bytes as `\xNN` text), `raw_body_truncated`, `response_cap_exceeded`, `kept_bytes`. An over-structured JSON response is recorded as `raw_body` (UTF-8 `ignore`, 1,000,000-character truncation, as before) with `structure_limit`.
- **SSE:** CRLF normalized; bare CR line endings are not. Provider dialects beyond the stated rules are unvalidated.
- **Refused connections:** the canned 503 is written from the accept thread with a 1 s timeout, so a slow refused client can delay accepting by up to 1 s each.

## 5. What is and is not bounded (honest limits)

- **Enforced:** structure counts, body and response byte caps, the reservation arithmetic, accepted connections, slots, phase deadlines on existing sockets (deadline + tick + scheduling).
- **Not bounded [X]:** DNS inside a TCP connect; CPU time of the pre-scan and parse (per-byte Python loop over ≤ 2 MiB, unmeasured); filesystem calls (preflight, record appends) — reported via `custody_s`/`deadline_overrun`, never prevented; the effect of `shutdown` on TLS and AF_UNIX sockets beyond the local tests [N:K].
- **Assumed, unmeasured [N:F]:** that the 4/6/256-byte constants bound real interpreter allocation (commissioning C1 RSS). No 1 GiB process guarantee.
- **Unperformed gates:** live TLS handshake under deadline, DNS timing, real provider SSE dialects and stripped-label tolerance, real RSS, deployment, the full repository suite, ruff.
- Accepted SV-016/017 limits stand: one recorder per root, durable root precondition, no power-loss evidence, decoded (not byte-exact) transcript, `status` is the selected/attempted status, `relayed` is completion of the recorder's write.
