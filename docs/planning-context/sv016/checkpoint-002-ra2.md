# SV-016 checkpoint 002 — R-A2 handler integration

Date: 2026-10-08. Branch `sv016/recorder-cleared`. Previous commit: R-0 (see `git log`).

## Changed files

- `services/recorder.py`
  - `Budget` (from checkpoint 001); its bounds now read the module settings at construction.
  - `BOOT`, `next_rid()` (`<boot>-<counter>`), `TOTAL_SLOTS`, `record_diagnostic()` → `TRANSCRIPTS_DIR/recorder.jsonl`.
  - `Exchange`: per-request flags (admitted, accounted, slots, responded, event_written).
  - Handler: every POST/GET ends in `_finish` — budget close if admitted and not yet closed (cancel when `RESERVED`, settle unknown when `FORWARDING`), slot release, one `close` append attempt; a failed `close` append prints one stderr JSON line. Order: framing → body → operator marker → parse → forwarded bytes and estimate → slots (`429 inflight`, no `open`) → `open` → `admit` (`429`, today's text) → connect (`502 upstream_connect`, cancelled and refunded) → `begin_forward` → send/read (`502 upstream_transport`, estimate kept) → `extract_usage` → `Budget.close` (settled before transcript and relay) → transcript → relay (`relayed`) → `close`.
  - `UnixUpstream` connects before the send gate with `auto_open = 0`. `UrllibUpstream` is an **interim** network path: urllib connects inside `urlopen`, after the gate, so every failure there is counted as possibly sent (never refunded). R-B2 replaces it.
  - `extract_usage()`: `total_tokens`, else prompt + completion, as non-negative non-bool ints; else unknown.
  - `main()`: one `Budget`; `recorder_start{boot,pid}` in `recorder.jsonl`; slugs must match `^[a-z0-9_-]{1,64}$` and fit `RECORDER_MAX_SLUGS` (default 32); each refusal reason is reported once, without the name.
- `tests/test_recorder_requests.py` — new (runner-allowed), in-process recorder against a fake UDS upstream.

## New event fields

- `open`: `bytes_in`, `bytes_forwarded`, `estimate`.
- `close`: `outcome` always; `estimate` when computed; for admitted requests `duration_seconds`, `usage` (dict or null, as before), `usage_class` (`known`/`unknown`/`none`), `charged_tokens`, `late_adjustment` (when non-zero and late); `upstream_status`; `relayed`. Refusal `close` events keep `refusal` text. Every `close` now carries a string `id` (pre-parse refusals used `null`).

## Commands and results

| Targets | Result |
|---|---|
| `tests/test_recorder_requests.py` | 12 passed |
| `tests/test_recorder_budget.py` + the 5 recorder nodes of `tests/test_services.py` | 38 passed |

## Deliberate deviations from the SV-013 step list (documented, not silent)

- The in-flight slot is taken **after** the body is read (SV-013 H5 puts it before). Without R-B3's body deadline, a slot taken before the body would let one stalled client hold a socket's capacity indefinitely; today's behaviour for the body read is kept until R-B3.
- The operator marker stays after the body read (SV-013 H4 moves it before). Moving it would close connections with unread bodies; existing transport behaviour is kept.
- No `MAX_CONNECTIONS`/header deadline (H0/H1), no `503 record_unavailable`/`record_capacity` (H9/H10), no `recorded` field: R-B3/R-B4. An `open` append failure currently becomes `500 internal_error` with no admission.
- `late_adjustment` entries with a zero delta are omitted (no adjustment exists to report).

## Next step

R-B1: strict parsing, three request representations, correlation label, short body, duplicate `Content-Length`.
