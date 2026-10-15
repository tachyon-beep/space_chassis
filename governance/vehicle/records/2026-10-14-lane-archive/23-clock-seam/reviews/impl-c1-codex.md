# #23 implementation review, candidate 1 — Codex reviewer of record

Received 2026-10-12T10:36:00.162Z; saved verbatim (harness indent removed).

---

**Request changes (issue #23, candidate 1).** The worktree matches the frozen SHA `f7312656…` and base `7a87eb82`. Static inspection only; no tests, repository programs or file changes. Paths below are in the worktree `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock`.

Remaining findings:

- **P2 — Second SIGTERM does not provide the promised escape for PID 1.** Restoring `SIG_DFL` and raising SIGTERM leaves Linux namespace PID 1 immune to its default termination action, and removes the working handler. The new test uses an ordinary subprocess. Use an explicit termination action effective for PID 1. `tools/console.py:2938`, `tests/test_vehicle_config.py:32499`

- **P2 — Summary equality remains incomplete after advisory event loss.** The reader counts surviving events, while the manifest counts events observed in memory. The new rolled-back backstop-write test explicitly produces a clean manifest with one backstop but no corresponding event; reconstruction reports zero. Use manifest counts for clean segments, and distinguish journaled counts from complete counts for crashed segments. `tools/console.py:3065`, `tests/test_vehicle_config.py:32378`

- **P2 — The feasibility gate changed from worst-cycle to p99.** The combined workload is fixed, but `fits` now ignores the observed maximum. With 200 samples, 198 at 50 ms and two at 150 ms, a 100 ms budget passes. That contradicts the frozen design's worst-cycle requirement. Retain that gate or explicitly amend its acceptance policy. `tools/measure_clock.py:543`, `/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:296`

- **P3 — Zero-cycle boots disappear from reconstructed summaries.** A backstop in the first wait can write a manifest without emitting a segment header. `segment_summaries` visits only recorded segments, so that boot's stall/backstop summary is omitted. `tools/console.py:3053`

- **P3 — Test 13's synthetic state has inconsistent representations.** It changes `internal.mode` but leaves flat `mode` unchanged, although the plant prefers the latter. Update both representations. The test can exercise the intended dwell case; this is **not** a predicted test failure. `tests/test_vehicle_config.py:31878`, `tools/plant.py:2090`

**The other c0 findings are resolved statically:**

- In `tools/console.py`: ring unlink ordering/cache invalidation **5685–5696**; guarded backstop write **6625–6635**; counter/lag invariant **1597–1601, 1907**; durable-prefix commit on suffix failure **4026–4033**.
- In `tests/test_vehicle_config.py`: tick-0 durability assertion **26533–26554**; deterministic interrupt clock **29092–29116**; test 7's independent/mixed changes **31575–31592**; test 19's post-claim, second-step SIGTERM at `k=5` **32137–32157**. Test 4 now compares the full manifest summary **31443–31449**, subject to the failure-path finding above.

**New judgment calls:** `last_cycle_us` is appropriate. Clock-only measurement roots and test 15's effectful command change are sound. The mid-cycle invariant exemption is safe for normal recovery because the partial anchor ends a dead segment; that premise should remain explicit. `free_drift` is a valid synthetic target, subject to keeping its representations consistent. The reader counting only journaled events is the source of the second P2 above.
