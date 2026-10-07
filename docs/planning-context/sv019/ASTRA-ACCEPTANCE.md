# SV-019 Astra correction review

2026-10-08, Australia/Sydney. Runtime: immutable `2f0567c1e1aaa0ca900adfa5f4ce1eaa40a783a9`, parent `3251057e175f26a35d652953a13e5c560e2d69a2`. Supporting final receipt/checkpoint: docs commit `bb4812a2d362d70bf011126c3a6e23951a82c8e3`.

**Verdict: accept the bounded SV-019 package (staged K-A1, K-A2, K-B1, pure K-E1 and outgoing K-G1). All four findings are closed; no remaining blocking findings.** The prepared inactive SV-020 persistence foundation may proceed on this accepted base. This is not acceptance of ledger activation, K-E2/K-F/K-G2, deployment or provider compatibility.

## Finding closure

- **SV019-G1-01:** `selection` now delegates to `_whole_unit_start`. A cut inside an older group advances to a following unit; a cut inside the newest group moves back to its assistant head. The same original-history index feeds `window_bounds` and recap folding. The new oracle checks assistant/result membership over original selected indices, with no last-index exemption. Single/multiple calls, oversized newest results, interposed/trailing systems, budgets/chunk boundaries and repeated folding are covered. The correction preserves the complete newest group rather than repairing its isolated result into an orphan notice.
- **SV019-B1-01:** `queue_message` retains the normalized string and uses that exact value for both escaped-unit admission and stored content. Tests inspect in-memory, saved and outgoing messages at 65,536 surrogate code points and one over the limit; accepted text contains question marks, and over-cap input is refused without truncation. Queue order remains asserted.
- **SV019-B1-02:** the script entry binds `sys.modules["chassis"]` to the executing module before `main()` loads duty code. Canonical imports and the seed's module lookup therefore share the runtime's exception classes. The new real-script subprocess fixtures cover imported EnvironmentFailure, TurnLimitReached, DutyFault, typed handoff and finish, exact call results, unrun later calls and no later invocation. A swallowed direct handoff still continues with final reason `main_returned`. This is stronger evidence than the earlier imported-module-only harness.
- **SV019-B1-03:** `classify_exit` again preserves all integer values, converting bool to its integer representation; string, None and invalid non-integer behavior remains explicit. Direct/runtime tests cover 300, −1, True/False and invalid list/float payloads. Script tests separately assert process status 44 for 300 and 255 for −1, while preserving the recorded original reason. No new supervisor policy is introduced.

K-A2 and pure K-E1 remain unchanged from their accepted checkpoints. Metadata/plain-list staging remains intact, with no format2 authority markers. Documentation now correctly explains the historical unresumable label without asserting memory reset, and limits outgoing repair claims to ordering/pairing rather than universal provider acceptance.

## Evidence

The immutable correction checkpoint reports all four new regressions failing against the pre-correction runtime without temporary rollback, followed by **16 group tests**, **67 termination tests**, **161 selected tests passed**, and **five local-stub integration tests passed**, with no warnings reported. Fifteen termination cases execute the actual script entry in subprocesses over local Unix sockets. Integration covers handoff, second run, turn limit, lifecycle and route.

This reviewer inspected the runtime/test delta and committed evidence; no tests were rerun and no implementation files were edited. Earlier denied stash actions remain accurately excluded from pre-fix evidence; they were not retried.

Receipt §5 retains the earlier phrase “All runs are local fakes: no ... socket.” That no longer describes the correction's subprocess/local-stub tests. The coordinator may correct this documentation in its provenance commit: initial unit checks used fakes; correction checks include actual script processes and local stub sockets, but no live model/provider or deployed supervisor stack. This is a known documentation cleanup, not a runtime blocker or reason for another test run.

## Acceptance limits

The package improves in-memory control flow and outgoing view repair. It does not establish crash recovery, atomic two-file checkpoint binding, durable ledger effect gates, note generation/exactly-once adoption, or persisted recovery repair. Startup before duty main remains outside terminal finalization as documented. Full response-envelope caps and live wire-ID rewriting remain K-E2 work; provider schema/ID acceptance is unvalidated. Explicitly loading another runtime under a different module name remains outside canonical-import identity guarantees.

Accepted recorder packages retain their earlier conditional deadline, RSS and custody limits. No broad suite, pump/H/T/Q change, live provider call, deployment or main merge is part of this review.
