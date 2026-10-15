# Aurora port, plan 4b: the recorder protections carried over from SV

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-implement, in the ported recorder (`recorder/proxy.py`, `recorder/core_caps.py`, `recorder/recorder_streams.py`), the four protections the SV workstream built for the old `services/recorder.py`. That is the decision John recorded in spec §10.1 on 2026-10-09. The four, in priority order:
1. structural bounds on agent-supplied bodies;
2. an absolute per-request deadline;
3. the transcript made durable before a buffered reply is relayed;
4. settle-once spend accounting, tested at the contended last unit.

**Architecture:** The protections are added at the existing hooks of Aurora's recorder; SV's own machinery is not ported:
- a byte pre-scan before every `json.loads` of a request body or a buffered response;
- a per-request deadline enforced by a connection class in the forward opener, which registers its socket so a timer can shut it at the absolute cutoff;
- a typed, fsynced append for the JSON transcript, with the reply withheld when the record is not readable;
- settle-once tickets and last-unit race tests in `core_caps.py`.

SV's `Budget`, `RecordStore`, memory budget, correlation labels and slot machinery stay behind.

**Tech Stack:** Python 3 standard library, as the recorder already is. Tests go in `recorder/tests/`, which runs as its own pytest process (`python3 -m pytest recorder/tests -q`).

**Spec:** `docs/superpowers/specs/2026-10-09-aurora-port-design.md`, §3.3 and §10.1 (the decision). The **specification of each property** is the SV branch's tests and recorder comments, read with `git show origin/wip/sv-recorder-opus-20261008:<path>`. Each task names the SV tests whose property it ports. The branch is not merged.

## John's decisions (2026-10-09)

1. **The record is complete: a reply that cannot be recorded is withheld.** A buffered reply whose transcript line is not readable on disk gets `502` with the message `record_failed: the recorder could not write this exchange to the transcript`. Its usage is still charged. This reverses Aurora's `test_a_full_volume_does_not_stop_the_json_transcript_append`, which this plan rewrites. The plain-text transcript and the events stay best-effort.
2. **Durability covers the buffered path.**
   - Streamed replies stay incremental.
   - They are appended and fsynced after relay, and their transcript line carries `"recorded_after_relay": true`.
   - The seed harness never streams.
3. **`REQUEST_MAX_BYTES` stays 16 MiB.** The pre-scan bounds structure at any size.
4. **The declared-stream pools keep in-flight reservations across the hour boundary.** This fixes `StreamRegistry._shared_roll`.

## Rulings this plan rests on

1. **t0 is per request, not per connection.** SV anchored deadlines at accept, with one request per connection. The port keeps connections alive and three tests pin that. t0 is taken at the start of `do_POST`. Over a Unix socket, header time is negligible.
   - The harness's OpenAI client allows 600 s of read gap per operation, with 2 client retries and 5 chassis retries.
   - So SV's profile carries unchanged: `CLIENT_TIMEOUT = 600`, `MARGIN = 30`, `END_TO_END = 570`, `UPSTREAM_DEADLINE = 540`, `LATEST_START = 480`, and per-operation socket timeout `min(60, left)`.
   - The handler's 300 s idle timeout stays.
2. **SV's memory reservation is dropped.** Its own receipt marks the arithmetic as never commissioned. What the port takes from that work is the pre-scan, which needs no reservation to refuse an over-structured body.
3. **No connection-count limit, header deadline or TLS rebind.** The port has no slot machinery, and nothing in its threat model needs them.
4. **Refund on a no-send failure (SV `test_an_admitted_request_that_never_connected_is_refunded`)** comes with Task 2's connection class. That class is what can tell "never connected" apart from "sent". Before Task 2 the port cannot tell, and keeps the reservation.
5. **A reply the recorder already knows it could not record is refused before it is paid for.** Withholding (decision 1) has a known failure mode. A `502 record_failed` is retried by the OpenAI client (twice, on any status ≥ 500) inside each of the chassis's 5 transient retries (1–16 s backoff). That is up to 18 charged and withheld upstream calls in about 45 s, then exit 44, a pause of 60 s plus jitter, and the cycle repeats.
   - SV guarded this, and the port does too. Before admission, a stdlib `os.statvfs` check refuses with `503 record_capacity` when the transcript directory has less than `RECORDER_MIN_FREE_BYTES` free (default 64 MiB).
   - Nothing is charged for that refusal. A full transcript volume then costs pauses, not tokens.
   - The `open` event stays best-effort (`test_a_full_volume_does_not_stop_the_open_or_the_close_event`). The free-space floor is the gate, not the event.
6. **A `400 structure_limit` is `invalid_request` to the chassis** (chassis.py:236). It gets one deep repair, then exits 43, which the ladder handles. That is acceptable for the seed harness, which never sends such a body.
7. **SV's R-A5 differs here by John's decision 4.** SV corrected the originating hour and reported the settle as late. The port's declared pools carry in-flight reservations into the new hour instead.

## Global Constraints

- Standard library only in `recorder/`.
- No request header is ever written to any record (`test_proxy.py:866`). No new `.py` file under `recorder/`: `test_recorder_contents.py` pins the module set to `proxy.py`, `recorder_streams.py` and `core_caps.py`.
- `forward_open(req, timeout=60)` keeps its signature. Over 40 tests monkeypatch it as `fake(request, timeout=None)`. The deadline travels on the `Request` object (`req.deadline`).
- A refusal the recorder answers itself (`_finish_local`) is relayed even when its own transcript append fails, since nothing was spent.
- Every existing recorder test keeps passing unless this plan names it as rewritten.
- `log_transcript` stays callable unbound with `self=None` (`test_recorder_events.py:101,112`).
- Refusals keep the recorder's existing shape: `{"error": {"message": ...}}`, with the status code in the HTTP status and in the `close` event.
- Live: `python3 -m pytest live -q -p no:cacheprovider` stays 12/12 after the last task.

## Review Focus

1. **A body that crashes a parser before the pre-scan runs.** Every parse of agent input must sit behind the pre-scan, or be total. That includes `core_reservation`, `compose_body`, `reservation_for` and the handler's own parse. (Task 1: the declared-stream deep-nesting regression.)
2. **An upstream that drips forever.** Each recv lands inside its per-operation timeout, yet the request must still end at `t0 + 540`. This applies on the buffered path and while relaying a stream. (Task 2: the drip test.)
3. **A transcript append that is torn, short or interrupted.** The next line must start on a line boundary, and a reply is never relayed on a line that was not written whole. (Task 3.)
4. **Two admissions racing for the last unit**, in threads and across processes. Exactly one may win. (Task 4.)
5. **A test of the reversed behaviour that still asserts the old one.** Every test that pinned "a full volume still forwards the reply" must be rewritten to the withholding rule, not deleted. (Task 3.)

---

### Task 1: Structural bounds, and parsing that cannot crash

**Files:**
- Modify: `recorder/proxy.py`, `recorder/recorder_streams.py`, `recorder/core_caps.py`.
- Create: `recorder/tests/test_recorder_bounds.py`.

**Interfaces (Produces):**
- `prescan(data: bytes) -> tuple[int, int, int]` in `recorder_streams.py`, returning `(max_depth, containers, values)`.
  - It is a linear pass that skips string literals and honours backslash escapes.
  - It counts each `{`/`[` as a container and a value, each string literal (keys included) as a value, and each scalar token as a value.
  - It does not validate JSON.
- `REQUEST_CAPS = (64, 32768, 131072)` and `RESPONSE_CAPS = (64, 8192, 32768)`, as (depth, containers, values).
- `over_caps(data: bytes, caps) -> str | None`: the first cap exceeded, by name (`"depth"`, `"containers"`, `"values"`), or `None`.
- `RESPONSE_MAX_BYTES`, env `RESPONSE_MAX_BYTES`, default 16 MiB. A buffered upstream response is read at most this far.

**Behaviour:**
- **Over-structured request.** In `do_POST`, right after the body is read (proxy.py:623) and before any admission or parse, a body over `REQUEST_CAPS` gets `400` with `structure_limit: <cap> over its limit`.
  - It logs an `open` and a `close` with status 400, and writes one transcript line with the error response.
  - It never contacts the upstream, and nothing is reserved.
- **Total parsing.** `compose_body` (recorder_streams.py:490), `reservation_for` (:438) and `stream_response_data` (proxy.py:583) treat `RecursionError` like a parse error, as defence in depth behind the pre-scan. `core_reservation` already does (core_caps.py:67).
- **Bounded raw bodies.** The refused-body path never parses the body. The `raw_body` it records, and every other `raw_body` the recorder writes or prints, is cut to 1,000,000 characters with `raw_body_truncated: true`.
- **Over-structured response.** A buffered upstream response over `RESPONSE_CAPS` is relayed to the agent unchanged and recorded as `{"raw_body": <first 1_000_000 chars>, "structure_limit": true}`. Its usage is unknown, so the reservation stands.
- **Oversized response.** A buffered response over `RESPONSE_MAX_BYTES` is not relayed. It gets `502` with `response_too_large`, is recorded as `{"raw_body": <prefix>, "raw_body_truncated": true}`, and its usage is unknown.
- **Streamed path.** Each SSE event payload is pre-scanned before its own `json.loads` (proxy.py:386). An over-structured event is kept raw and does not count for usage.

- [ ] **Step 1: Failing tests.** In `recorder/tests/test_recorder_bounds.py`, porting SV's `test_recorder_bounds.py` properties:
  - `test_the_pre_scan_counts_containers_strings_keys_and_scalars`: `{"a":[1,2,{"b":"x"}]}` gives `(3, 3, 8)`.
  - `test_punctuation_and_escapes_inside_strings_are_not_structure`
  - `test_two_mebibytes_of_empty_objects_are_refused_before_any_parse`: 699,050 `{}`. Assert 400, no upstream contact (counting upstream), `json.loads` never called on the body (monkeypatched to raise), and no reservation.
  - `test_sixty_five_levels_are_too_deep_and_sixty_four_are_not`
  - `test_the_value_cap_is_exact`: a list of 131,071 scalars passes and 131,072 is refused.
  - `test_a_deeply_nested_body_on_a_declared_stream_is_a_400_not_a_dead_handler`: 200,000 levels on a declared stream's socket. Before the fix the connection drops with no reply.
  - `test_the_parsers_behind_the_scan_are_total`: `compose_body`, `reservation_for`, `core_reservation` and `stream_response_data`, given 200,000 levels each, return their parse-error result and do not raise. `core_reservation` passes already; the ledger says so.
  - `test_a_refused_body_is_recorded_bounded`: a 16 MiB over-structured body leaves a transcript line under 1.1 MB.
  - `test_an_over_structured_response_is_relayed_and_recorded_raw_with_its_usage_not_trusted`
  - `test_a_response_over_its_byte_cap_is_withheld_and_recorded_truncated`
- [ ] **Step 2:** Run `python3 -m pytest recorder/tests/test_recorder_bounds.py -q -p no:cacheprovider`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `python3 -m pytest recorder/tests -q -p no:cacheprovider`, expecting PASS, then `uvx ruff check . --no-cache`.
- [ ] **Step 5:** Commit: `recorder: a structure pre-scan before every parse of agent input, and parsers that cannot crash`.

### Task 2: An absolute deadline per request

**Files:**
- Modify: `recorder/proxy.py`.
- Create: `recorder/tests/test_recorder_deadlines.py`.

**Interfaces (Produces):**
- `Timing(client_timeout=600, margin=30, upstream=540, latest_start=480, operation=60)`, read from env `RECORDER_CLIENT_TIMEOUT`, `RECORDER_DEADLINE_MARGIN`, `RECORDER_UPSTREAM_DEADLINE`, `RECORDER_LATEST_START` and `RECORDER_OPERATION_TIMEOUT`.
- `timing_problems(timing) -> list[str]`: a non-finite value, a non-positive value, `latest_start >= upstream`, `upstream > client_timeout - margin`, or `operation > upstream`. A non-empty list stops the recorder at startup with the problems on stderr.
- `Deadline(t0: float, timing)` with these members:
  - `left() -> float`;
  - `may_start() -> bool`, true when `now - t0 <= latest_start`;
  - `operation_timeout() -> float`, `min(operation, left())`.
- `WatchedHTTPConnection` / `WatchedHTTPSConnection` (subclasses of `http.client`'s), and handler classes whose `http_open`/`https_open` call `self.do_open(functools.partial(Watched…, deadline=req.deadline), req)`. `forward_open(req, timeout=60)` keeps its signature; the handler reads the deadline from the request.
  - Each connection registers its socket with the `Deadline` once `connect()` returns. For HTTPS, that is the wrapped socket, registered after the wrap.
- **The timer.** A `threading.Timer(t0 + upstream - now)` with `daemon=True` is cancelled in a `finally`. When it fires, it sets `deadline.fired` and calls `socket.socket.shutdown(sock, SHUT_RDWR)` on the registered socket, suppressing `OSError`/`EBADF`. A registration made after `fired` shuts the socket at once.
- **Connect is bounded by the per-operation timeout only.** No socket exists until `create_connection` returns, so with several resolved addresses a connect can overrun the deadline by a few multiples. SV says the same of DNS.
- `connected: bool` and `fired: bool` on the `Deadline`. `Deadline` takes an injectable `clock` (default `time.monotonic`).

**Behaviour:**
- t0 is taken at the start of `do_POST`.
- Past `latest_start` before contact, the request gets `503 deadline_insufficient` and is refunded.
- The upstream phase (connect, send, status, body, and stream relay) ends at `t0 + upstream` however late it began.
- **A shut socket can read as a clean end of body.** `read1`/`readinto` on a Content-Length body return `b""` after `shutdown` without raising, and `relay_chunks` would then write the chunked terminator. So `deadline.fired` is checked after the buffered `read()` and after every `read1` in the relay:
  - a fired buffered read is `502 upstream_deadline`, charged, even when no exception was raised;
  - a fired relay writes no terminator and closes the connection, and the reservation stands, as `test_a_stream_broken_mid_relay_keeps_its_reservation` already expects.
- **Refund when nothing was sent** (ruling 4). The boundary is `forward_open`:
  - When an exception leaves `forward_open` with `deadline.connected` false (unreachable, refused, DNS), the reservation is cancelled, request count included, through a new `cancel(ticket)` on `CoreCaps` and `StreamRegistry`. The status stays `500 proxy error`, as `test_a_transport_exception_relays_a_fixed_body` (test_proxy.py:1410) pins.
  - Once `forward_open` has returned, or `connected` is true, the request counts as sent and its reservation stands. That covers the fake responses of the existing tests.
  - This rewrites `test_a_transport_failure_keeps_its_reservation` (test_proxy.py:1110) into a never-connected case that is refunded and a connected-then-failed case that is kept.

- [ ] **Step 1: Failing tests,** porting SV's `test_recorder_deadlines.py` properties:
  - `test_the_deadlines_count_from_the_start_of_the_request`
  - `test_a_late_start_still_ends_at_t0_plus_the_upstream_deadline`: arithmetic, with negative controls.
  - `test_an_inconsistent_timing_profile_is_refused_at_startup`
  - `test_a_request_past_its_latest_start_is_refused_before_contact` and `test_a_request_exactly_at_its_latest_start_still_goes`
  - `test_a_silent_upstream_is_cut_at_the_absolute_deadline`: deadline shrunk to 2 s; 502 by the cutoff; charged; no success line in the transcript.
  - `test_a_dripping_upstream_is_cut_at_the_deadline_though_no_recv_times_out`: one byte every 0.5 s with a 1 s operation timeout. It is parametrised over the buffered path, a chunked stream, and a **Content-Length-framed stream**. The last one would otherwise relay a truncated body as complete. A cut stream ends without a chunked terminator.
  - Timing assertions use SV's tolerance: `upstream − 0.05 ≤ waited ≤ upstream + 0.25 + 1.0`.
  - `test_the_deadline_is_per_request_on_a_kept_alive_connection` observes `elapsed_s` on each `close` event, which this task adds.
  - `test_a_request_past_its_latest_start_is_refused_before_contact` drives the injectable clock.
  - `test_no_timer_outlives_its_request`: after a request, `threading.enumerate()` holds no deadline timer.
  - `test_an_upstream_that_never_connected_is_refunded`
  - `test_an_upstream_that_failed_after_connecting_keeps_its_reservation`
  - `test_the_deadline_is_per_request_on_a_kept_alive_connection`: two sequential requests on one connection each get their own t0.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** Run the recorder suite (PASS) and ruff.
- [ ] **Step 5:** Commit: `recorder: an absolute deadline per request, enforced on the upstream socket itself`.

### Task 3: The transcript durable before a buffered reply is relayed

**Files:**
- Modify: `recorder/proxy.py`, `recorder/tests/test_proxy.py` (the reversed tests).
- Create: `recorder/tests/test_recorder_custody.py`.

**Interfaces (Produces):**
- `append_record(path: str, line: bytes) -> str` in `proxy.py`, returning `"failed"`, `"partial"`, `"appended"`, `"appended_fsync_failed"` or `"durable"`. It:
  - takes a module lock per path;
  - opens with `O_RDWR|O_APPEND|O_CREAT|O_CLOEXEC`, because the last byte has to be read;
  - reads the last byte with `os.pread`, and when it is not `\n`, prefixes the buffer with `\n`, repairing a torn tail;
  - writes prefix and line as one buffer in a short-write/EINTR loop;
  - runs `os.fdatasync`;
  - on the first append to a path in this process, and after any failure, also fsyncs the containing directory (and that directory's parent when `makedirs` created it);
  - returns `durable` only when the data sync and any directory sync it needed have both returned. A failed directory sync returns `appended`, and the sync is retried on the next append.
- `READABLE = {"appended", "appended_fsync_failed", "durable"}`.
- `log_transcript(self, request_data, response_data, stream="core", *, after_relay=False) -> str` returns the JSON transcript's append result. It keeps its unbound call form. The plain-text transcript stays best-effort.
- The transcript line is `json.dumps(entry, ensure_ascii=True, allow_nan=False)`. A non-finite number makes the record fail rather than write invalid JSON.

**Behaviour:**
- **Before admission.** If `os.statvfs` on `TRANSCRIPT_DIR` shows less than `RECORDER_MIN_FREE_BYTES` free (env, default 64 MiB), the request gets `503 record_capacity` and nothing is charged (ruling 5).
- **Buffered path.** In this order: settle, `log_transcript`, then:
  - result in `READABLE`: relay;
  - otherwise: relay `502 record_failed` in place of the answer. The `close` event carries `"record": <result>` and the usage is charged.
  - `appended_fsync_failed`: relay, and log one stderr line per process, `transcript durability degraded: …`.
- **Streamed path.** Relay as now, then `log_transcript(..., after_relay=True)`, which adds `"recorded_after_relay": true` to the line. A failure there is logged, since nothing is left to withhold.
- **Rotation.** `rotate_if_needed` fsyncs the gzip archive and the directory before it truncates the live file.
- **Rewritten tests:**
  - `test_a_full_volume_does_not_stop_the_json_transcript_append` (test_proxy.py:1690) becomes `test_a_full_volume_withholds_the_reply_and_still_charges_it`: 502 `record_failed`, `close` carries `record: failed`, the reservation stands. Its ENOSPC is injected at `proxy.os.write` for the JSON transcript's fd. `_Full` guards the builtin `open`, which `append_record` no longer calls. The plain-transcript and event tests keep `_Full`, because those writers stay on the builtin `open`.
  - `test_a_full_volume_does_not_stop_the_plain_transcript_append` and `test_a_full_volume_does_not_stop_the_open_or_the_close_event` keep their meaning. Those records stay best-effort.

- [ ] **Step 1: Failing tests,** porting SV's custody properties:
  - `test_the_first_append_fsyncs_the_file_and_its_directory`
  - `test_a_failed_directory_sync_is_never_reported_durable_and_is_retried`
  - `test_a_short_write_after_a_prefix_is_partial_and_the_next_line_starts_on_a_boundary`: ENOSPC injected after N bytes.
  - `test_a_torn_tail_left_by_a_dead_process_is_repaired`
  - `test_concurrent_appends_never_interleave`
  - `test_a_failed_data_sync_relays_and_is_reported_once`
  - `test_a_failed_transcript_withholds_the_answer_and_the_usage_is_charged`
  - `test_a_partial_transcript_is_withheld_and_the_next_turn_is_recorded_cleanly`
  - `test_a_streamed_reply_is_recorded_after_relay_and_says_so`
  - `test_rotation_makes_the_archive_durable_before_truncating`
  - `test_a_non_finite_number_fails_the_record_rather_than_writing_invalid_json`
  - `test_too_little_free_space_refuses_before_admission_and_charges_nothing`
  - `test_a_failed_directory_sync_is_appended_not_durable`
  - These unit tests fail at first on the missing `append_record` symbol. That is expected; the handler tests fail on behaviour.
  - plus the rewritten `test_a_full_volume_withholds_the_reply_and_still_charges_it`
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** Run the recorder suite (PASS) and ruff.
- [ ] **Step 5:** Commit: `recorder: the transcript durable before a buffered reply is relayed; a reply that cannot be recorded is withheld`.

### Task 4: Settle-once accounting, the contended last unit, and the declared pools across the hour

**Files:**
- Modify: `recorder/core_caps.py`, `recorder/recorder_streams.py`, `recorder/proxy.py` (the `close` event).
- Create: `recorder/tests/test_recorder_settlement.py`.

**Behaviour:**
- **A ticket settles once.**
  - A second `settle` on a ticket in `CoreCaps` or `FleetLedger` changes nothing and returns `"already_settled"`.
  - The ledger writes `settled: true` on the ticket's line. The latest line still wins, and a later line for a settled ticket is ignored.
  - The ticket carries its reservation (`(local, fleet_ticket, reserved)`) so a late settle can compute its delta.
- **A settle whose ticket left the window** is not recharged:
  - It returns `{"late": <delta>}`, which the handler puts on the `close` event as `late_adjustment`.
  - `FleetLedger._read` exposes expired tickets until compaction drops them. After compaction, an unknown ticket returns `"unknown"` and the `close` carries `late_adjustment: "unknown"`.
- **`cancel(ticket)`** on `CoreCaps` and `StreamRegistry` refunds a reservation and its request count, for Task 2's no-send refund. `settle(ticket, 0)` only zeroes tokens.
- **`StreamRegistry`'s shared pool keeps its in-flight reservations when the clock hour turns** (John's decision 4):
  - Entries gain an in-flight flag, set by `admit`, cleared by `settle` and `cancel`, and false for `charge()` entries.
  - Only flagged entries are carried into the new hour, so `test_the_shared_pool_refreshes_at_the_top_of_the_hour` (test_recorder_streams.py:1145) keeps passing.
- **Health parity.** `services/health.spend()` counts a `close` as refused only when it is a cap refusal: 429, or 503 with `fleet ledger unavailable`. A 503 `record_capacity` or `deadline_insufficient` is an error, not a cap. This matches `CAP_WORDS` (one line in `services/health.py`, plus a test in `tests/test_health.py`).

- [ ] **Step 1: Failing tests,** porting SV's `test_recorder_budget.py` properties against the port's classes:
  - `test_two_threads_racing_for_the_last_request_slot_admit_exactly_one`: `CoreCaps` at allowance − 1, `threading.Barrier`.
  - `test_two_processes_racing_for_the_fleets_last_tokens_admit_exactly_one`: `FleetLedger`, two `multiprocessing` processes, one ledger file.
  - `test_a_settlement_and_an_admission_have_exactly_two_possible_outcomes`
  - `test_a_second_settle_changes_nothing`
  - `test_a_settle_after_its_ticket_left_the_window_is_reported_late_not_recharged`
  - `test_a_declared_pool_keeps_an_in_flight_reservation_across_the_hour`
  - `test_a_charged_entry_is_not_carried_across_the_hour`
  - `test_cancel_refunds_the_reservation_and_the_request_count`
  - `test_a_settle_after_compaction_is_unknown_not_recharged`
- [ ] **Step 2:** FAIL. The two race tests and `test_a_settlement_and_an_admission_have_exactly_two_possible_outcomes` pass before implementation (admission is under one lock and flock). They pin properties the port already has; record them as such in the ledger. **Step 3:** Implement. **Step 4:** Run the recorder suite (PASS) and ruff.
- [ ] **Step 5:** Commit: `recorder: a ticket settles once, a late settle is reported, and the declared pools keep their in-flight reservations across the hour`.

### Task 5: The live run, and the docs

- [ ] **Step 1:** Rebuild and run the live suite: `python3 -m pytest live -q -p no:cacheprovider`. Expected: 12/12. Fix any defect test-first in the recorder.
- [ ] **Step 2:** Add one live check to `live/test_containment.py`: `test_an_agent_s_deeply_nested_request_is_refused_by_its_recorder`. Inside agent_1, Python posts a 100,000-level body to `/llm/sock/core.sock` and gets 400 `structure_limit`. Then agent_1's chassis is still completing calls: its progress advances within 120 s.
- [ ] **Step 3:** In `.env.example`, document the new settings: `REQUEST_MAX_BYTES` (wired already, undocumented), `RESPONSE_MAX_BYTES`, `RECORDER_MIN_FREE_BYTES` and the five `RECORDER_*` timing values. In `scripts/build_compose.py`, pass them to the recorders, with defaults, then regenerate `docker-compose.yml`.
- [ ] **Step 4:** Run the root, harness, recorder and pump suites and ruff. Commit: `recorder: live check of the structure bound; the new settings documented and wired`.

---

## What this plan does not do

- Port SV's chassis half (paused by John).
- Port SV's memory reservation, connection limits, header deadline, correlation labels or recorder diagnostics file.
- Make streamed replies record-before-relay (John's decision 2).
- Gate admission on a readable `open` event (SV R-C4). The free-space floor (ruling 5) is the gate instead.
- Lower `REQUEST_MAX_BYTES` (John's decision 3).
