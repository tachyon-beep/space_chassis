# SV-016 checkpoint 005 — correction pass for the Astra initial package review

Date: 2026-10-08. Branch `sv016/recorder-cleared`. Input: `../sv016-context/SV-016-Astra-initial-package-review.md` (target `0031aab`, implementation-identical to `925eaad`). Scope unchanged: no R-B3, no R-B4, no product policy.

## Finding → change → regression

| Finding | Change (`services/recorder.py`) | Regression (pre-fix failure observed on `925eaad`) |
|---|---|---|
| SV016-01 lone surrogate unwritable | `write_record_line`: recorder-local ASCII-escaped JSON lines for `open`, `close`, transcript and `recorder.jsonl`. `common.append_jsonl` unchanged for other services. No fsync, directory sync, torn-line repair or preflight | `test_recorder_requests.py::test_a_lone_surrogate_in_an_accepted_body_is_recorded_and_settled` — content and model, untouched and transformed; upstream bytes identical / single re-encoding; settled at actual 30; one close each; record decodes to the same strings. Pre-fix: `500` (`UnicodeEncodeError`) |
| SV016-02 `relayed` | `Exchange.relayed` defaults `False` and is set only by the upstream-response relay; `_refuse` no longer sets it. `close.relayed` is now always present | `::test_a_completion_withheld_after_a_transcript_failure_is_not_relayed` (pre-fix: `relayed: true`); `::test_relayed_means_the_upstream_response_reached_the_client` (ok and provider 429 → true; transport, connect, 404 → false); existing client-disconnect test (false) |
| SV016-03 Transfer-Encoding | refused when `get_all("Transfer-Encoding") is not None`, before the body | `::test_any_transfer_encoding_field_is_refused_even_an_empty_one` (empty; empty then `chunked`; 60-byte R-H3 body) — 411, no open, no admission, no upstream. Pre-fix: `200` |
| SV016-04 slot leak on raise | `_take_slots` releases the socket slot in `finally` unless the fleet slot was taken; timeout path unchanged | `::test_a_failing_fleet_slot_acquire_gives_the_socket_slot_back` (one socket slot, injected `_Injected` on the first fleet acquire). Pre-fix: second request `429 inflight` |
| SV016-05 control exceptions | `do_POST` `except BaseException`: outcome `aborted`, status cleared unless a response was already sent, then re-raise; `_finish` still cancels/settles, releases and writes one close | `::test_a_control_exception_before_sending_cancels_and_closes_once_with_a_typed_outcome` (cancelled, refunded, slot reusable), `::test_a_control_exception_after_sending_settles_unknown_and_closes_once` (unknown at estimate, `upstream_status 200`, `relayed false`, slot reusable). Pre-fix: `outcome null` |
| SV016-06 X-name spellings | `forward_header_names` keeps one spelling per lower-cased name; `outbound_headers` skips any name already present ignoring case | `::test_a_configured_header_name_in_two_spellings_is_sent_once` (fake upstream sees one `X-Title`; duplicated inbound still dropped), `::test_the_builder_itself_deduplicates_extra_names_ignoring_case` (default empty allowlist unchanged). Pre-fix: three names |

Conditional items:

| Item | Resolution | Test |
|---|---|---|
| RB1-03 serialization-stage totality | label and forwarded-body encodings (`_encode_label`, `_encode_forwarded`) run inside the parser's `ValueError`/`RecursionError` guard → `400 unsupported_json`. No failing depth is claimed to exist today | `::test_the_parser_stays_total_near_the_recursion_limit` (sweep ±40 around the recursion limit, label / transformed / stream-strip shapes), `::test_a_failing_re_encoding_is_a_fixed_refusal` (forced raise) |
| RA1-01 id reuse | handler ids unchanged (one boot + one counter). Bounded hardening: `admit` also refuses an id still indexed in the socket's rolling pools. Never-reuse stays the documented precondition across sockets | `test_recorder_budget.py::test_a_reused_id_whose_tombstone_was_retired_is_still_refused_while_its_entry_counts` (pre-fix: admitted), `::test_the_handler_ids_are_unique_across_threads` |
| Usage validation | `Budget.close` treats a `known` usage as known only for a non-bool non-negative int; else unknown | `::test_usage_is_known_only_for_whole_non_negative_counts` (zero, negative, bool, float, string, prompt+completion fallback, partial, non-dict, invalid direct `Usage`) |
| FIFO vs LRU; zero-delta late | code comments state FIFO tombstone retirement and omitted zero-delta `late` entries; receipt aligned. The label hint memory is a true LRU (unchanged) | — |
| evidence-field scope; urllib consequences | receipt §5/§6 updated | — |

## Commands and results

Pre-fix, one finding per command (`--cpu 23`), each failed as described above: SV016-01, -02, -03, -04, -05 (after-send), -06, RA1-01.

After the final code change, once:

`python3 …/SV-016-bounded-check.py --cpu 23 tests/test_recorder_budget.py tests/test_recorder_requests.py tests/test_services.py::test_a_pool_of_zero_refuses_rather_than_crashing tests/test_services.py::test_an_allowance_counts_requests_and_tokens_separately tests/test_services.py::test_the_shared_pool_empties_at_the_top_of_the_hour tests/test_services.py::test_the_recorder_accepts_any_chat_completions_prefix` → **86 passed**, 2 warnings: `PytestUnhandledThreadExceptionWarning` for the deliberately injected `SystemExit` that the fix lets propagate out of the handler thread.

Not run: `tests/test_run_end_to_end.py::test_a_run_reaches_the_model_through_the_recorder` and `::test_the_recorder_injects_a_credential_the_agent_never_has`, though allowed. Their `world` fixture writes under `/home/john/space_chassis/.scratch` (the original checkout) unless `SC_SCRATCH` is set, and whether the runner passes an override through cannot be verified here. `tests/test_services.py::test_no_service_ever_writes_a_request_header_to_the_record` no longer exists (replaced in R-B2).
