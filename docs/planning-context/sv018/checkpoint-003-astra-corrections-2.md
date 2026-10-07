# SV-018 checkpoint 003 — correction pass 2 (SV018-04)

Date: 2026-10-08. Branch `sv016/recorder-cleared`, from clean `8b24b4908fdb84a7efab5a228874bc5f30107c1d` (coordinator-pushed WIP backup, tree `f4c9ab518a1fdcf4126bcdb45df9bb59ce6ef2a2`; a backup, not acceptance or deployment). Input: `../sv016-context/SV-018-Astra-correction-1-review.md`. Scope: SV018-04 and the exception wording only.

## Finding → change → regression

| Finding | Change (`services/recorder.py`) | Regression (`tests/test_recorder_deadlines.py`) | Pre-fix result |
|---|---|---|---|
| SV018-04 socket-creation failure skips usable fallback addresses | `WatchedConnection._tcp_connect`: `NEW_SOCKET(...)` moved inside its own `try/except OSError`; on failure the error is kept and the next address is tried. Nothing was created, so nothing is watched or closed. The `_attempt_timeout()` deadline check stays first and outside that boundary, so `UpstreamDeadline` ends the loop instead of being retried | `::test_an_address_whose_socket_cannot_be_created_falls_back_to_the_next[http/https × EAFNOSUPPORT/EPROTONOSUPPORT]` (IPv6 then IPv4; IPv4 attempted with the 60 s time left; HTTP: only its live watch, released to baseline on close; HTTPS: shared path up to the connected IPv4 double, whose TLS wrap then fails — not a handshake test); `::test_when_no_address_can_be_created_nothing_is_sent_and_the_request_is_refunded[http/https]` (handler: both creations fail → 502 `upstream_connect`, `usage_class none`, refunded, no socket, no watch); `::test_a_failed_creation_that_uses_up_the_time_ends_the_attempts[http/https]` (open at 480, failed creation spends to 540 → no second creation, nothing sent, refunded, no watch) | `OSError: [Errno 97] Address family not supported by protocol` raised from `_tcp_connect` at `NEW_SOCKET` (no fallback) |
| Exception wording | checkpoint 002 and receipt §6 now say *ordinary* exceptions (`Exception`) are contained by `_shutdown`; control exceptions (`BaseException`) are not suppressed and no survival claim is made. No code change: suppression was not broadened | — | — |

## Commands and results (bounded runner, `--cpu 23`, one at a time; `SC_SCRATCH=/tmp/sv018-integration-check`)

1. Pre-fix: `tests/test_recorder_deadlines.py::test_an_address_whose_socket_cannot_be_created_falls_back_to_the_next` → failed (`[http-97]`, `OSError` errno 97 from `NEW_SOCKET`).
2. After the fix: `tests/test_recorder_deadlines.py` → 60 passed.
3. Complete selected set (budget, requests, custody, bounds, deadlines + 4 `test_services.py` recorder nodes + 2 `test_run_end_to_end.py` route/credential nodes) → **209 passed**, 3 warnings (`PytestUnhandledThreadExceptionWarning` from the three deliberate `SystemExit` injections, unchanged).

## Limits

Fake resolver, socket doubles and a fake clock: these prove the attempt control flow, ownership and accounting, not kernel family support, DNS behaviour or a TLS handshake. All earlier SV-018 limits stand (receipt §5).
