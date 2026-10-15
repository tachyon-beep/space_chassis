# #23 design review r1 — Codex reviewer of record

Received 2026-10-12T04:53:49.837Z; saved verbatim (harness indent removed).

---

**Request changes (issue #23 / WP08.5 clock-seam design).** Reviewed the matching design hash `89389a4c…`, vehicle `7a87eb8`, [issue #23](https://github.com/tachyon-beep/space_vehicle/issues/23), and ADR 0002. (`gh issue view` failed in the Codex run; the issue was fetched through the GitHub connector instead.) Every issue acceptance bullet has a nominal test in section 6, but the recovery mechanism and test coverage are incomplete.

Vehicle paths below refer to the supplied worktree `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9`.

- **P1 — Group commit needs a cycle-aware receipt protocol.** [DESIGN.md:67](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:67) places effects first and publication marks last, without specifying receipts, window deltas or result notes. `console.py:1780–1796` permits a `results_written` note to acknowledge only the immediately preceding row's receipts; `:3418–3425` emits that note at the final tick. Meanwhile, `unwritten_results` finalizes pending receipts on each subsequent row and derives receipt time as `row.tick−1` (`:2485–2488`). First-row receipts therefore break final-row acknowledgement; last-row receipts misstamp commands and leave partial recovery without their state. Specify both readers' changes and first-row counters/deltas. Add `k>1` command replay, partial-prefix recovery, and result-before-note crash tests.

- **P2 — The resume frame-gap promise is incorrect.** [DESIGN.md:74](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:74) promises a shorter gap. With `k=5`, last frame 5, surviving rows 6–7, and resume at 7, the next frame is **12: a seven-tick gap**. Existing resume republishes results, not a recovery frame (`console.py:5354–5365`). Correct the boundary exception and test actual last-visible/first-resumed frames.

- **P2 — Crashed-segment lag summaries lack specified reconstruction data.** [DESIGN.md:33](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:33) repeats cycle lag on every row but requires cycle counts and missed counts. Existing segment headers contain neither `m` nor `k` (`console.py:3476–3483`); publication marks cannot identify boundaries when all windows are unhealthy. Specify segment clock inputs, cycle identification, percentile convention and partial-cycle accounting. Test changed `k`, empty marks and partial tails. Also explicitly reconcile the clean-end summary location with ADR C1's **manifest** requirement (`ADR:386`).

- **P2 — Accepted `k` values contradict ADR B's publication-rate constraint.** [DESIGN.md:47](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:47) accepts any positive integer satisfying `N % k == 0`. Thus `k=10,N=50` passes while publishing only 5 Hz against declared 10 Hz channels. ADR `:334–351` requires honoring those rates and explicitly excludes slower publication without redeclaration. Constrain fresh/resumed values or expressly amend that policy. Likewise, the agreed divisibility requirement supersedes J's "`k` and `N` are independent" (`ADR:630`); identify that amendment explicitly.

- **P2 — `k=1` and "don't pace" do not preserve all existing tests.** [DESIGN.md:94](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:94) overlooks the immediate hand-edit repair assertion (`tests/test_vehicle_config.py:11337–11348`) and the interrupt harness, which replaces `console.time` with a sleep-only object and interrupts its second sleep (`:29045–29062`). At `m=1000`, a behind-schedule scheduler need never sleep. Adapt those tests deliberately. Scheduler tests need an injected monotonic clock/sleeper **with pacing enabled**, covering waiting, catch-up and resume epoch reset. Add individual missing-input and invalid CLI/checkpoint-value cases.

- **P2 — Probe timing cannot simply become 100 ms.** [DESIGN.md:87](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:87) would imply mirror restoration within 150 ms and telemetry movement within 200 ms under the current [probe](/home/john/space_chassis/contract/diode_probe.py:259). Legitimate lag can exceed both. Separate nominal cadence from the observation deadline.

- **P3 — Chassis runtime touch points are complete; maintained documentation is omitted (section 5).** Add [chassis interface:23](/home/john/space_chassis/governance/chassis/interface.md:23), [vehicle interface:33](/home/john/space_chassis/governance/vehicle/interface.md:33), and `vehicle-adoption`'s `README.md:225–234` startup instructions.

**Buildability:** the mechanism **is buildable**. `_append_record` already groups rows; replay already enforces contiguous ticks. Resume changes fit `run_inputs`, but must survive `restore_state` replacing `executive.clock` (`console.py:5201–5206`). Checkpoint validation currently validates only `N` (`checkpoint.py:517–519`). The flag checker must resolve `CLOCK_INPUTS`: `capture_state.clock` is a comprehension (`checkpoint.py:302`), whereas its current parser accepts dictionary literals only (`check_vehicle.py:18295–18300`).

No files changed; no tests, collection, linters or repository tools run.
