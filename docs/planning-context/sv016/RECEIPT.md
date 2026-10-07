# SV-016 recorder package — implementation receipt

Package: R-0, R-A1, R-A2, R-B1, R-B2 of the Space Vehicle recorder workstream. Implemented 2026-10-08 in an isolated local clone; awaiting independent Astra review by the coordinator. This receipt claims only what is listed under "checked". It makes **no** R-B3 (watchdog, deadlines, memory admission, SSE usage, response cap) or R-B4 (custody, durability, `append_record`) claim.

## 1. Custody and controls

| Item | Value |
|---|---|
| Checkout | `/home/john/Documents/Codex/2026-10-07/task/execution/sv016-recorder`, local clone, no remote |
| Branch / base | `sv016/recorder-cleared` / `fa43b25b0fd7d88a3f5e7feb3338e190078517ce` (the reviewed chassis source revision) |
| Model / mode | Opus 5.5, normal permissioned execution; Fast off per the coordinator; no subagents, no external reviewer |
| Not touched | `/home/john/space_chassis`, the vehicle submodule (not initialized), `docs/plans/`, frozen evidence, chassis/pump/vehicle code |
| Not done | push, fetch, merge, deploy, fleet/Docker/endurance runs, provider calls, installs |
| Tracking | Filigree not used (its session-context previously failed on a read-only original database; not retried). `STATUS.md` and `checkpoint-00N-*.md` are the ledger |

Design inputs (SHA-256 computed this session):

| Input | SHA-256 |
|---|---|
| `SV-013-user-uploaded-dossier-2026-10-07.md` (§2.1, §3.3–3.4, §4.2) | `f88fd0b7ab9b49d39c1ef6c68c2885130b6d1d67897141473d6d6ba3dd4401a9` (matches the baseline identity in SV-015 v2 §0.1) |
| `SV-015-integrated-apparatus-closure-v2.md` (§2.5 supersedes the SV-013 `Budget` clock API; O8-4) | `eb8c39508a1e3a1a3e550f92bd26ee3cd49991e0f5b12fcc9ab1d2d75e70d569` (matches the v2 review's custody table) |
| `SV-015-independent-review.md` | `a310bcc4089f124c5360097bbc44f0b8fb80daa5d5ab09c0dd10084b4d7c193b` |
| `SV-015-v2-independent-review.md` | `083161037fc7373baa871cc61035974f46c50f3a36167f64d2944793a1d1639e` |

Both reviews mark R-0, R-A1/R-A2, R-B1/R-B2 usable. The v2 review's new findings (V2-01…V2-06) concern executive/pump/vehicle batches and were not acted on.

## 2. Commits and revert map

| Commit | Content | Revert unit | Depends on |
|---|---|---|---|
| `3c0106a` | R-0 `endurance/report.py` `count_requests`; ledger | alone, but its four report tests live in `tests/test_recorder_budget.py` (section "R-0") and go with it | — |
| `95676e6` | R-A1 `Budget` + R-A2 handler, `recorder.jsonl`, slug bound, tests | **one unit**: `Allowance`/`SharedTokens` were replaced, so R-A1 cannot stand without the handler rewiring | — |
| `b467b21` | R-B1 `parse_request`, correlation, framing | alone (reverting restores lenient forwarding) | `95676e6` |
| `0031aab` | R-B2 `outbound_headers`, `Upstream`/`UnixHTTPConnection`, urllib removed; source-grep test replaced | alone (reverting restores the interim urllib path and the source-grep test) | `95676e6` |
| `925eaad` | final checkpoint, receipt, STATUS | docs only | — |
| correction commit after `925eaad` | Astra initial-review fixes SV016-01…06, conditional hardenings, regressions, checkpoint 005 | alone (reverting restores `925eaad` behaviour, including the six defects) | `0031aab` |

Recorder state is in memory; every revert behaves like an ordinary restart (counters reset). Events and transcripts are append-only; new fields are additive.

## 3. Checked — exact targeted commands

All through `python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <targets>`, one command at a time, no xdist.

| Run | Targets | Result |
|---|---|---|
| baseline (unmodified base) | `tests/test_services.py::test_a_pool_of_zero_refuses_rather_than_crashing`, `::test_an_allowance_counts_requests_and_tokens_separately`, `::test_the_shared_pool_empties_at_the_top_of_the_hour`, `::test_the_recorder_accepts_any_chat_completions_prefix`, `::test_no_service_ever_writes_a_request_header_to_the_record` | 5 passed |
| final ×2 | `tests/test_recorder_budget.py tests/test_recorder_requests.py` + the first four `test_services.py` nodes above (the fifth was replaced) | 72 passed, twice |

Intermediate runs and the one test-setup failure are in checkpoints 001–003.

### Fixture → test map

`tests/test_recorder_budget.py` (pure, fake clocks, barriers):

| Fixture | Test |
|---|---|
| R-A1 | `test_an_estimate_larger_than_the_limit_is_refused_even_in_an_empty_window` |
| R-A2 | `test_admission_uses_current_effective_charges_not_historical_estimates` |
| R-A3 / L1 | `test_two_admissions_racing_for_the_last_request_slot_admit_exactly_one` |
| R-A4 / L2 | `test_two_sockets_racing_for_the_fleets_last_tokens_admit_exactly_one` |
| R-A5 | `test_a_settlement_in_the_next_hour_corrects_the_hour_it_was_charged_to` |
| R-A6 | `test_a_settlement_after_its_entry_left_the_window_is_reported_late_not_recharged` |
| R-A7 | `test_a_settlement_two_hours_later_still_knows_its_hour` |
| R-A8 | `test_a_second_close_changes_nothing_and_an_evicted_tombstone_is_unknown` |
| R-A9 | `test_a_duplicate_request_id_is_refused_without_a_charge` |
| R-A10 | `test_cancelling_a_reservation_refunds_everything_and_forbids_sending` |
| R-A11 | `test_a_wall_clock_that_steps_back_keeps_the_accounting_hour` |
| R-A12 | `test_an_estimate_larger_than_the_fleet_limit_can_never_fit` |
| R-A13 | `test_zero_closes_a_socket_pool_and_unlimits_the_fleet_pool` |
| R-A14 | `test_a_forward_wall_jump_is_applied_before_any_check_and_shown_by_snapshot` |
| L3 | `test_a_settlement_and_an_admission_have_exactly_two_possible_outcomes` (both serial orders + 50 barrier races) |
| L4 | `test_forwarding_and_cancelling_one_reservation_cannot_both_win` (50 barrier races) |
| L5 | `test_an_admitted_request_that_never_connected_is_refunded`; end to end below |
| O8-4 | `test_the_first_caller_to_take_the_lock_reads_the_earlier_time` (deque `[0, 1]`; every clock read asserted under the lock; head-only prune at 3600.5), `test_the_budget_methods_take_no_caller_timestamps` |
| waits / windows | exact request and token wait boundaries, inclusivity at exactly 3600 s, forward wall jump, unknown-keeps-estimate and overshoot, no expiry of a live reservation, O(n) middle cancellation, slug bound, estimate validation, slug pattern |
| R-K1, R-K2 | `test_the_report_counts_opened_ids_not_half_the_lines`, `test_the_report_ignores_boot_style_lines`; plus unmatched open, duplicate and non-string ids, other report fields kept |

`tests/test_recorder_requests.py` (in-process recorder on a real UDS, fake upstream on UDS or loopback TCP):

| Fixture | Test |
|---|---|
| R-C7 (UDS) | `test_a_refused_connection_is_closed_once_and_the_request_refunded` (`ECONNREFUSED`; one close; refunded; zero upstream requests) |
| R-C7 (network) | `test_a_refused_network_connection_is_refunded_too` (also an unsupported scheme) |
| R-A end to end | ok path, transport failure after forwarding (estimate kept), R-A1 refusal, closed pool text |
| accounting after exceptions | transcript append raises (settled known first, response withheld, `500`), client gone before relay (`relayed: false`), exception before send (cancelled), exception after send (unknown at estimate), in-flight refusal, 404/405 single close |
| recorder.jsonl | `test_the_recorder_start_goes_to_its_own_file_and_bad_names_are_not_served` |
| R-H3 | `test_an_untouched_body_is_forwarded_byte_for_byte` (60 bytes, SHA-256 `795b56c3…032f2`, est 15) |
| R-H4 | `test_the_correlation_label_is_stripped_and_the_body_re_encoded` (30 bytes, SHA-256 `0d1a07f0…0b3212`, est 7) and `test_a_label_reaches_neither_the_upstream_nor_the_transcript` |
| R-H5 | `test_an_invalid_label_is_described_and_never_kept`, `test_an_invalid_label_is_recorded_as_type_and_size_only` |
| R-H6 | `test_a_non_finite_number_is_refused_with_or_without_a_transformation`, `test_a_refused_body_writes_one_close_and_no_open_and_reaches_nobody` |
| R-H7 | `test_a_duplicate_key_is_forwarded_untouched_or_refused_if_it_would_be_re_encoded`, `test_a_duplicate_key_body_without_a_transformation_is_forwarded_verbatim` |
| R-B1 | `test_a_body_shorter_than_its_length_is_refused_and_never_forwarded` |
| R-B3 (input) | `test_two_content_lengths_are_refused` |
| totality | `test_the_parser_is_total_over_hostile_bytes` (incl. 100,000-deep nesting, 5,000-digit integer, encoded surrogate) |
| R-H1 | `test_no_request_header_is_ever_written_to_the_record_and_the_upstream_gets_seven` — UDS and loopback HTTP both observed, compared equal, record free of `CLIENT-DUMMY`, `DUMMY-123`, `RECORDER-DUMMY-KEY` |
| R-H2 | `test_with_no_key_configured_no_authorization_is_sent_at_all` (both transports, 6 headers) |
| headers | allowlist end to end; builder unit cases; verified TLS defaults (`CERT_REQUIRED`, `check_hostname`); no hidden auto-connect |

Fixture setup notes (expected values unchanged): R-A4 and R-A11 build "glob = 120/140 from other sockets' entries" from sockets B **and** C (B alone at `Tk = 100` could not hold 120 and then admit 20 more). R-A8's tombstone eviction runs in a fresh budget with `max_tombstones=2`. The synthetic key `RECORDER-DUMMY-KEY` goes only to the fake upstream.

## 4. Not checked — unperformed gates

- **Repository full suite** (`python3 -m pytest -q`): not run, by the phase's bounded-check instruction. Its result is unknown. This includes `tests/test_run_end_to_end.py` (whose `world` fixture defaults to `/home/john/space_chassis/.scratch`, the original checkout), `tests/test_review.py`, `tests/test_observer.py`, `tests/test_chassis.py` and the vehicle referee.
- `uvx ruff check` / `ruff format --check`: not run (would fetch a tool).
- Negative controls against the base code were not executed: the new tests import names the base lacks. The dossier's stated negative controls are cited, not reproduced.
- Live TLS handshake, real provider, Docker stack, endurance mission: not run.
- `/tmp/sv16-*` cleanup after the runs could not be listed (path outside the allowed directories); each fixture `rmtree`s its root in teardown.

## 5. Remaining limits (honest, labelled)

- **No hard billed-token cap** [X]: known actual replaces the estimate, unknown keeps it; an overshoot blocks later admissions until the window rolls.
- **R-B3 absent**: no header/body/upstream/client-write deadlines or watchdog; no `MAX_CONNECTIONS`; no memory admission or JSON pre-scan; responses are fully buffered without a cap; SSE usage is not parsed (SSE responses settle `unknown`); `UPSTREAM_TIMEOUT` (600 s, per operation) remains the only upstream bound. A stalled client or upstream can hold a slot.
- **R-B4 absent**: since the correction pass (checkpoint 005) the recorder writes its own lines with `write_record_line` (ASCII-escaped JSON), so lone-surrogate escapes in accepted bodies and responses are recorded. That is serialization only: no fsync, directory sync, torn-line repair, append locking or free-space preflight. A transcript failure is `500 internal_error`, not `502 record_failed`; there is no `recorded` field, no custody classification, no `503 record_unavailable`/`record_capacity`. The R-A2 event fields are therefore a **narrower** interpretation of SV-013 §2.1.10: accounting fields (`outcome`, `estimate`, `usage_class`, `charged_tokens`, `late_adjustment`, `upstream_status`, `relayed`) only. These tests validate no R-B4 guarantee.
- **Budget API preconditions**: request ids must never be reused (the handler's `<boot>-<counter>` ids are unique; `admit` additionally refuses an id still indexed in the socket's pools or tombstones). Tombstones retire FIFO, not LRU. A `known` usage counts only as a non-negative non-bool int; anything else settles as unknown. A late settlement with zero delta produces no `late_adjustment` entry (narrower than the design's unconditional late-destination table).
- **Placement deviations** (checkpoint 002): in-flight slots are taken after the body read, and the operator marker is still checked after the body read, pending R-B3's body deadline.
- `open.peer` (`SO_PEERCRED`) is not added.
- Process death: by construction nothing fabricates a `close` for a previous boot; no crash test was run.
- Watchdog and custody durability guarantees are **not** claimed.

## 6. Visible behaviour changes for review

- `close` is written after the relay (so it can carry `relayed`); every request has exactly one `close`, including `upstream_connect` (formerly two). Pre-parse refusal `close` events now carry a string `id`.
- Request ids are `<boot>-<counter>` (were 16 random hex digits).
- Out-of-domain bodies are refused `400` locally (were forwarded).
- Only reviewed headers go upstream; SDK headers and the client's key are dropped; no `Authorization` without a configured key. `RECORDER_FORWARD_HEADERS` is the opt-in for X- headers.
- Proxy environment variables are no longer honoured and HTTP redirects are no longer followed (urllib did both automatically); none is configured or relied on in this repository. Non-2xx upstream responses are relayed as received.
- (Correction pass) Recorder record lines are ASCII JSON: non-ASCII text appears as `\u` escapes; records are JSON-equal to before. `close.relayed` is always present and is true only when the recorder's write of the upstream's own response completed (not proof that the client application consumed it). `close.status` is the status selected for the client once a response attempt began — not proof of delivery. A `close` written while a control exception (e.g. `SystemExit`) unwinds has `outcome: "aborted"`, and `status: null` only if no response attempt had begun; an abort at the start of the relay can record `status: 200, relayed: false` (wording corrected in SV-017 after the Astra correction-1 review). Any `Transfer-Encoding` field, even empty, is refused `411`.
- Announced slugs must match `^[a-z0-9_-]{1,64}$` and fit `RECORDER_MAX_SLUGS` (32).
- New settings: `RECORDER_MAX_TOMBSTONES` 4096, `RECORDER_MAX_SLUGS` 32, `RECORDER_MAX_INFLIGHT_PER_SOCKET` 2, `RECORDER_MAX_INFLIGHT_TOTAL` 12, `RECORDER_INFLIGHT_WAIT_SECONDS` 30, `RECORDER_MAX_LABEL_LRU` 64, `RECORDER_FORWARD_HEADERS` (empty).

## 7. Where a reviewer should look first

1. `Budget.admit` / `Budget.close` in `services/recorder.py`: check order, clock reads under the lock, cancel vs settle, late adjustments.
2. `Handler._post` and `_finish`: the connect → `begin_forward` → exchange ordering, the accounting in each `except`, and the single `close` path.
3. `parse_request`: the transformation condition, the duplicate-key refusal, totality.
4. `outbound_headers` and `Upstream`: the credential boundary and the absence of any reconnect after the send gate.

## 8. Permission denials during the session (not bypassed)

Reading the bounded runner file (outside the allowed directories) — its allowlist was discovered by probing; compound shell commands; `git -C` and `git check-ignore`; `python3 -I -c` for literal recomputation; a heredoc containing non-ASCII whitespace; listing `/tmp`.
