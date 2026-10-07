# SV-016 checkpoint 003 — R-B1 parsing/correlation and R-B2 headers/transport

Date: 2026-10-08. Branch `sv016/recorder-cleared`.

## Changed files

R-B1 (committed separately):
- `services/recorder.py` — `parse_request(body, *, streaming) -> ParsedRequest | RequestRefusal`, `classify_label`, `CORRELATION_KEY`, `LABEL_PATTERN`, `MAX_LABEL_LRU` (`RECORDER_MAX_LABEL_LRU`, default 64), `AgentState.label_seen_before`. Handler: exactly one plain-digit `Content-Length` (`missing_content_length`, `duplicate_content_length`, `bad_content_length`), `short_body`, parse refusals before any `open`; `open` gains `transformed`, `duplicate_keys`, `client_label` / `client_label_invalid`, `label_seen_before`; the transcript `request` is the recorded object.
- `tests/test_recorder_requests.py` — R-H3…R-H7, R-B1, R-B3 fixtures, totality cases.

R-B2 (this commit):
- `services/recorder.py` — `outbound_headers(inbound, key, extra)`, `forward_header_names()` (`RECORDER_FORWARD_HEADERS`, default empty), `UnixHTTPConnection(http.client.HTTPConnection)`, `upstream_connection()` (UDS when `UPSTREAM_SOCKET`, else `HTTPSConnection` with `ssl.create_default_context()` or `HTTPConnection` for `http:`; other schemes refused at connect), `Upstream` (connect, then `exchange` with `auto_open = 0`; `NotConnected` instead of any reconnect). `urllib.request`/`urllib.error` removed (`urllib.parse.urlsplit` remains for URL splitting). `HOP_BY_HOP` removed.
- `tests/test_services.py` — the source-grep `test_no_service_ever_writes_a_request_header_to_the_record` removed; a comment points to its behavioural replacement.
- `tests/test_recorder_requests.py` — R-H1 (UDS and loopback HTTP compared), R-H2, allowlist, builder unit cases, verified-TLS defaults, no hidden auto-connect, network-path connect refund.

## Commands and results

| Targets | Result |
|---|---|
| `tests/test_recorder_requests.py` after R-B1 | 28 passed (includes the dossier's literal lengths and SHA-256 for R-H3/R-H4) |
| `tests/test_recorder_requests.py` after R-B2 | 35 passed |

Attempted and denied (not performed): a stdlib `python3 -I -c` recomputation of the fixture digests (permission denied); the tests assert the dossier literals directly instead.

## Visible behaviour changes (reviewed in SV-013 RV-14 / §2.1.6, listed for the receipt)

- Bodies outside the supported domain (non-UTF-8, non-JSON, NaN/Infinity, non-object, unsupported nesting/number) are refused `400` locally instead of forwarded.
- Upstream headers are built fresh: the client's `Authorization`, cookies, SDK headers (`X-Stainless-*`, its `User-Agent`) are no longer forwarded; `Accept` only as one of three values; `User-Agent: space-chassis-recorder/0.2`; no `Authorization` when no key is configured.
- `http.client` does not consult proxy environment variables (urllib did). None is configured in this repository's compose or scripts.
- Upstream failure text in records and client errors is the exception type plus a fixed sentence.

## Next step

Final verification across the three allowed target sets, STATUS update, implementation receipt.
