# SV-017 Astra correction-pass review

Date: **2026-10-08, Australia/Sydney**. Reviewed immutable correction **`11e0e26fd5e3e78f2b05f383a2493ef8cd8f1547`**, parent `1c6224cc317c496341fc2d3c6873ae3109c3e62c`, against the previously reviewed R-B4 implementation `606a91d3e2c1cd68e23d2221cfcaff652993461a`. Read the committed correction checkpoint and receipt. Review used git objects, source/test inspection and a clean `git diff --check`; no moving-worktree inspection, test execution, model call or implementation edit was performed.

**Verdict: ACCEPT the SV017 correction pass and the completed SV016 + SV017 packages within their documented scope.** All three R-B4 review findings are closed; no new blocking implementation regression was identified. This accepts the bounded accounting/parser/header/custody work for handoff, not deployment or physical durability guarantees.

## Finding disposition

**SV017-01 — closed.** `services/recorder.py:834–858` preserves the primary AppendResult and catches ordinary exceptions from auxiliary degradation reporting. The catch is `Exception`, not BaseException; control exceptions still propagate. `log` contains ordinary closed/broken-stream failures, and the stderr fallback remains a single attempt without recursive reporting. The two new parameterized cases cover diagnostic failure alone and diagnostic failure with a persistently broken stdout. They assert unchanged provider response delivery, two readable append classes, known usage charged, sole slot reusable and exactly one degradation-diagnostic attempt. Reporting failure no longer becomes a relay/custody failure. Degradation reporting is attempted once per file/process; the close fallback remains at most once per request.

**SV017-02 — closed.** `common.py` saves `state.names_durable` before `_drop` in the fdatasync error branch. The returned qualifier now describes this append's namespace evidence while descriptor/cache retirement still prepares the next open correctly. The test distinguishes successful fences plus data-sync failure from failed namespace fencing plus data-sync failure, checks refencing on reopen and preserves sticky degradation.

**SV017-03 — closed.** `common.py:320–331` rechecks `_closed` while holding the path lock. If close already finished, the append refuses without opening/writing; if append passed the check first, close waits for that path lock and retires the descriptor afterward. The nesting order is path lock → paths lock, matching namespace-cache access. `close()` releases paths lock before taking any path lock, so no reverse-order cycle is introduced. The deterministic pause fixture reproduces the actual gap between state lookup and path-lock acquisition and verifies refusal, no reopen, no residual descriptor, unchanged file and no deadlock.

## Regression-test assessment

The single-file concurrency fixture now forces 7-byte writes and still verifies all 400 unique writer/index pairs as separately parseable records. This is materially stronger evidence for the path lock than whole-line append calls. O3-8 now synchronizes two slug append threads and verifies each thread's own slug-directory then root sync, with both final results durable under the syscall model.

The four order-insensitive changes are justified: a client can receive response A before A's close append, then receive response B whose close lands first. The expected outcome multiplicities are retained; the provider-error test preserves the complete `(outcome, recorded, relayed)` tuple within each record. The partial-write test retains failed-first/successful-second HTTP results and exact on-disk fragment/new-record checks; only the close-class ordering becomes a multiset. Low-space and semaphore tests retain no-spend or next-request-admission assertions. These changes do not skip errors or loosen accepted values.

Those multiset assertions are not, by themselves, proof of request-ID association; the tests did not previously provide an explicit ID join either. Existing single-request accounting/close checks, unique-ID/one-close coverage and the unchanged request-owned Exchange remain relevant. A future test refinement could join the durable close to the complete transcript ID, but this is not a blocking defect or reason to broaden this correction pass.

## Evidence and exact remaining limits

Checkpoint 002 reports all three regressions failed on the pre-fix implementation, followed by **121 selected checks passed after final changes**, with two expected warnings from deliberately propagated SystemExit. The selected set includes Budget/request/custody files, four legacy recorder service nodes and the two authorized route/credential integration nodes using `/tmp/sv017-integration-check`. I inspected the tests and committed receipt; these are implementer-run results, not independently rerun checks by this reviewer.

The accepted custody properties remain conditional on one recorder process per transcript root, an already existing root whose host-side durability is provided by deployment, and honest filesystem flush behavior. “Durable” describes successful required sync calls under those assumptions. Real SIGKILL evidence covers R3 only; the tail-repair child writes a prefix and exits. Neither demonstrates kernel-crash or power-loss persistence, nor all R1–R6 cuts.

Records preserve the documented decoded JSON/text representation, including nonfinite markers and raw-text truncation; they are not a byte-exact wire archive. Client payload bytes remain unchanged. `status` is selected/attempted status; `relayed` records completion of the recorder's upstream-response write, not application consumption. Auxiliary diagnostics/fallbacks are attempt-only evidence whose absence proves nothing.

R-B3 remains excluded: no end-to-end watchdog/deadlines, response cap, SSE usage parsing, connection/memory admission envelope or process-memory/latency bound. Inline diagnostics and per-file disk operations can block. The full repository suite, live provider/TLS interoperability, live disk faults, real power loss, deployment, vehicle/pump protocols and product-policy choices remain outside the evidence and acceptance.

**Remaining blocking findings: none in the reviewed selected scope.**
