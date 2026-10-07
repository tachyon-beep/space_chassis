# SV-018 recorder package (R-B3 deadlines, structure, memory, response cap, SSE) — STATUS

Ledger for SV-018 (Filigree not used). Branch `sv016/recorder-cleared`, base `11e0e26fd5e3e78f2b05f383a2493ef8cd8f1547` (accepted SV-016 + SV-017). No push, merge, deployment or host change.

Contract: SV-015 v2 §2.1 (t0-anchored deadlines, forward check, watchdog diagnostics off the enforcement path, startup check), §2.2 (pre-scan caps, memory reservation), §2.6, fixtures O3-4…O3-6, O4-3…O4-7; retained SV-013 §2.1.7, §2.1.9, §2.1.11 (non-superseded defaults), R-B2, R-B4…R-B8. Coordinator decisions (Astra preflight): one request per connection with `Connection: close`; slot and memory waits share 30 s of actual waiting; BODY_DEADLINE anchored at header completion; O3-5 models a disconnected client; elapsed_s/custody_s measure to their endpoint before the close append; diagnostics in a bounded deque under the watchdog's own lock; SSE structure excess in any event makes usage unknown; O4-5 object-array exceeds containers first, a scalar array proves the values cap.

| Step | State | Where |
|---|---|---|
| Mechanisms: `Timing`/`timing_problems`/`CLOCK`/`Deadlines`, `Watchdog` (heap, owned/pending entries, shutdown under its lock, diag deque + writer thread), connection cap before thread spawn, `prescan`, `MemoryBudget`, `sse_usage`, `view_response` | done (checkpoint commit 1) | `services/recorder.py` |
| Handler integration: header phase + canned 408, slots before body, body deadline, pre-scan → 400 structure_limit, memory → 429 memory, forward check → 503 deadline_insufficient, absolute upstream deadline, capped response read, response_cap_exceeded, SSE usage, transcript usage/usage_class, close elapsed_s/custody_s/deadline_overrun, Connection: close | done (checkpoint commit 1) | `services/recorder.py` |
| Existing coverage after integration | `test_recorder_requests.py` 46 passed (2 expected SystemExit warnings); `test_recorder_custody.py` 33 passed | — |
| Header-phase fix: `parse_request` refuses a fired header phase (a fragment is never parsed as a request) | done (part 2) | `services/recorder.py` |
| New regressions `tests/test_recorder_bounds.py` (22), `tests/test_recorder_deadlines.py` (16) | done (part 2) | — |
| compose: 2 MiB body default, RECORDER_TIMEOUT_SECONDS wiring | done (part 2) | `docker-compose.yml` |
| Complete selected run | 159 passed, 3 expected SystemExit warnings | `RECEIPT.md` §3 |
| Receipt | done | `RECEIPT.md` |
