# SV-018 Astra correction-pass 2 review

2026-10-08, Australia/Sydney. Reviewed immutable commit `055345d1cd3d13845ffc12b9834787b17d67d23d`, parent `8b24b4908fdb84a7efab5a228874bc5f30107c1d`, including its runtime/test delta and committed receipt/checkpoint.

**Verdict: accept R-B3 as the bounded, conditional implementation package. No remaining blocking review findings.** SV018-01/02/03 remain closed by correction 1; SV018-04 is closed by this correction. This acceptance permits the prepared SV-019 work to proceed on the accepted base. It is not deployment or commissioning acceptance.

## SV018-04 closure

`services/recorder.py`, `WatchedConnection._tcp_connect` (around lines 2330–2360): ordinary socket-factory errors now save the failure and continue to the next resolved address. The remaining-time check stays outside and before that exception boundary, so an exhausted deadline terminates attempts. A failed creation acquires neither a socket owner nor a watch; successful creation retains watch-before-connect and cancel-before-close behavior. After every failed connect, the previous socket/watch is released before another address is attempted. HTTP and HTTPS still share this path.

The eight new parameterized checks discriminate the requested branches:

- EAFNOSUPPORT and EPROTONOSUPPORT on the first family, followed by a usable IPv4 socket, for HTTP and HTTPS.
- Every creation fails: both addresses attempted, no socket made, no watch leaked, handler returns `502 upstream_connect`, and request/token reservations are refunded.
- A failed creation consumes the remaining deadline: the second factory call never occurs, no request bytes are sent, and accounting is refunded.

The HTTPS success-path fixture deliberately reaches only successful TCP fallback before wrapping a socket double fails. Its assertions establish that IPv4 was reached and cleanup completed; they do not claim a successful TLS handshake. That limitation is accurately stated.

The existing deadline, SSE, non-finite-profile and custody behavior was not changed by this narrow patch. Static inspection found no new ownership, retry or accounting regression in the correction.

## Exception wording and evidence

Checkpoint 002 and receipt now correctly describe `_shutdown` as containing ordinary `Exception` failures. There is no runtime change to swallow `BaseException`; control exceptions remain outside the suppression boundary.

Checkpoint 003 reports an actual pre-fix EAFNOSUPPORT failure, then **60 deadline tests passed** and **209 selected bounded tests passed**, with **three expected deliberate SystemExit warnings**. These are implementer-run results inspected by this reviewer, not independently rerun results. The receipt still repeats the historical 201-pass correction-1 bullet beneath the new section; checkpoint 003 and the explicit 209-pass entry identify the final run unambiguously. Moving that historical bullet is optional documentation cleanup, not an acceptance blocker.

## Remaining commissioning boundaries

Acceptance retains the canonical conditions: DNS, CPU parsing and filesystem calls are not interrupted; acceptance/scheduling latency assumptions remain; real TLS/kernel shutdown behavior, provider SSE dialects/request tolerance and interpreter RSS constants remain commissioning gates. Tests with fake resolution/socket doubles prove control flow and accounting, not live DNS, platform family support or TLS behavior.

Accepted SV-016/SV-017 limits remain: one recorder per durable root, no general power-loss proof, decoded rather than byte-exact transcript custody, selected/attempted status semantics, and `relayed` as completion of the recorder's write. No broad suite, provider call, deployment or merge was performed or authorized by this review. Reviewer actions were immutable source/document inspection and this report only.
