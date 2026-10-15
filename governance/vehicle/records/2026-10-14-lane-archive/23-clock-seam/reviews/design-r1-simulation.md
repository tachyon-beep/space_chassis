# #23 design review r1 — simulation architect

Received 2026-10-12T04:52:25.426Z; saved verbatim (harness indent removed).

---

VERDICT: approve with changes. Sections 1-3 are sound and I did not relitigate them. I found no cases where the design contradicts the ADR on a settled point. There is one P1 on interim overload safety, and several P2s that are cheap to fix at design time. Read-only review: no tests or tools were run. Source is the vehicle worktree at 7a87eb8 (V = /tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9).

P1-1. Overload and stall are unbounded until #26 (design 1, 2; ADR A answers, C3)
- Evidence: the ADR relies on the 30 s ceiling and C3 hold to bound overload. ADR:320 says that without them lag "reaches the 30 s ceiling within a minute or two". Design section 2 and the "Not this child" list leave the ceiling out, and `lag_ceiling_s` stays null in the checkpoint (design 3).
- Failure scenario A, sustained overload: if cycle cost exceeds k*dt/m (100 ms), lag grows without bound. Examples are slow fsync, ten large windows, or a checkpoint plus static rewrite landing in one cycle. Mission time then runs slower than m for hours. That is the silent dilation ADR A1 and ROADMAP exclude. It is recorded, but nothing acts on it.
- Failure scenario B, stall then catch-up burst: CLOCK_MONOTONIC keeps running through SIGSTOP, `docker pause` and host stalls. After a 1 h stall the process owes about 3 h of mission time. It then runs back-to-back cycles at roughly 1.3x real time for hours. (ADR A: about 0.4 s of lag recovered per wall second at 76 ms per 100 ms cycle.) The fleet gets frames faster than it can react, which is "advance by guessed time" in effect.
- Fix: choose one before the chassis adopts the delta (design 5):
  - (a) Gate chassis adoption of #23 on #26, and say so in section 7. Or
  - (b) Add an interim backstop in #23. When a cycle's start lag exceeds a constant (the ADR's 30 s), finish nothing further: write the clean-end checkpoint, journal "lag backstop", and exit 3. The restart policy resumes with a fresh epoch, which is consistent with downtime F1 (freeze). This keeps C4 (never drop ticks) intact and stays within the "Not this child" boundary. The constant is a placeholder that #26 replaces with the checkpointed `lag_ceiling_s`.
- Also record a stall that is not overload (a long sleep return, or a gap far larger than any cycle) as a distinct journal event.

P2-1. Section 4: claimed commands are exposed for about 5x longer
- Evidence: `window.claim()` takes the console by rename (console.py:4373-4380). `_ingest` runs at :3129-3133, then `advance`, then `_record_cycle` (:3155). A claimed command therefore exists only in memory until the fsync.
- Failure scenario: today that gap is one step. Under the design it is k steps (about 50 of the 76 ms cycle at the measured costs), so a SIGKILL or OOM kill mid-cycle loses the agent's batch with no result and no record.
- The statement "stopping between them loses nothing an agent sent" is true only if row 1 is durable before steps 2..k. As written (k rows appended after k steps, one fsync) it is false.
- Fix: when row 1 carries effects, verdicts or deferral deltas, append and fsync it before stepping ticks 2..k. Pure no-effect cycles keep the single group fsync. The cost is one extra fsync on command-bearing cycles only. Alternatively, state the widened loss window explicitly as accepted debt.

P2-2. Section 2: lag and missed-deadline hide cycle cost
- A cycle starts at due(last tick) and then takes about 76 ms, so the frame appears about 76 ms after its tick's due time. "Lag = start - due(last)" reads about 0 for that, and a cycle costing 95 ms never counts as missed. ADR completion.md's deadline is "20 ms/m plus amortised I/O", which is a completion measure.
- Fix: record `cycle_us` (end - start) and the end lag (end - due(last)) alongside `lag_us`, and give p50/p95/p99/max for both in the summary. Keep the miss rule on start lag as agreed, and add "overran" (cycle_us > k*dt/m) as a second count. This also makes `measure_clock.py` comparable with live data.
- A 20 ms miss threshold can false-fire under container CFS throttling, which can stall up to a 100 ms quota period. Say so in the ADR amendment.

P2-3. Section 1, causality: effects are backdated by up to k ticks plus cost
- A cycle starts at due(a+k) but stamps effects at tick a, whose due time was k*dt/m earlier. A command written at wall time w is applied at mission time a, which is up to 100 ms (plus cost, plus any catch-up lag) before w. The agent saw frame a published at due(a)+cost, and the effect lands in the step from a.
- ADR B's "takes effect at most k ticks after it was written" holds only in the sense that it appears in the next frame. This does not contradict the ADR, since the ADR's A2 also steps due ticks at the start. But the contract note should say it plainly. During catch-up, the backdating is the lag.
- Fix: say so in the ADR amendment and in the cycle docstring. Keep the receipt tick as the cycle's start tick (as today, console.py:3557-3560), and put no claim-time-in-mission-ticks field in windows. Optionally record the claim's wall offset in the tick row.

P2-4. Section 4: partial-group crash recovery needs the "published" invariant spelled out
- Evidence: the replay completeness check (:2405-2408) and `marks` (:3358) are written for one row per cycle. After a crash with only rows 1..j durable (j<k):
  - the last durable row has no published marks;
  - row 1's effects and results were never published;
  - the resume starts at a+j, mid-cycle.
- This is the case test 9 should pin. Recovery must treat row 1's results as owed (the existing recovery path for a durable-but-unpublished tick) and must not read "no mark" as "nothing owed". The first resumed cycle should then be k ticks from a+j, so one gap is k+j rather than the "one shorter gap" section 4 describes.
- Fix: correct the "shorter" wording, and add a test with j in 1..k-1 that includes effects in row 1. Also consider a one-time realigning first cycle after an unaligned resume, covering ticks up to the next multiple of k. Then all frame and receipt ticks are multiples of k across runs, and "crosses a multiple of N" becomes redundant given N mod k = 0. This is a one-off short cycle, not a catch-up partial burst, so it does not touch your "no partial bursts" rule. If you decline, keep the crossing rule.
- Unverified: whether the ring's cadence_classes (5 Hz channels in every second frame) are keyed by tick or by seq. I found no use of them in console.py by grep, only in generate_readme.py and check_vehicle.py. If they are keyed by frame count, an unaligned resume shifts their phase. Check this.

P2-5. Section 2/4: `lag_us` is wall data in a row that is replay-checked
- The row carries `chain` (running hash) plus `state_hash` and `lineage`, which replay compares (:2395-2425). `lag_us` must not enter `state_hash`, `lineage` or the compare-point. If the row chain covers the whole row, it can; but replay must not recompute or compare `lag_us`.
- Fix: say so, and add a test: two runs with different lag series replay to identical state_hash and lineage.

P2-6. Section 1: static files and checkpoint land in the same cycle
- Design 1 puts the HELP/README rewrite on the checkpoint cadence (N), so every second one cycle carries a checkpoint (about 9 ms by ADR) and 78 KB + 7 KB static rewrites for ten windows. That is the likeliest regular cause of a missed deadline.
- Unmeasured: `measure_clock.py` (mapping section 2) has no static-write case.
- Fix: stagger the static rewrite to a different cycle (for example the cycle after the checkpoint), and add the static rewrite to `measure_clock.py`. Report the worst-cycle cost, not only p50.

P3-1. Due-time arithmetic (section 1)
- Absolute `E + (t - t0)*dt/m` recomputed per cycle does not accumulate drift. Good. Make it integers: `time.monotonic_ns()`, with `due_ns = E_ns + n * 10**9 * q`, where m is held as a rational (`fractions.Fraction`) or as dt_ns/m rounded once per cycle. Then `lag_us` is exact and tests do not depend on float rounding.
- Define t0: it is the tick count at the resume, and the first cycle covers t0+1..t0+k, so it starts at E + k*dt/m. Read E after restore/replay and just before the first cycle, not at process start. Otherwise replay time shows as lag.
- Sleep: use a loop (sleep until due, recheck, repeat), because early wakeups happen. Cap the sleep so SIGINT/SIGTERM stay responsive.
- `time.sleep(args.poll)` at :5773 is the only wait today. The F1 graceful stop on SIGTERM ("finish the current cycle", ADR F) now has a cycle of about 76 ms, and the catch-up loop never sleeps. Check signals between cycles.

P3-2. Deferrals (section 1)
- `due = self.tick + 1` (console.py:4047) means every deferral settles exactly k ticks after acceptance, not "up to k-1 late". Always k-1 late for k=5.
- Harmless today: registry `maximum_queue_age_s` is 30 s or more (domains/*/commands.yaml), against the 80 ms lateness. Keep the age check in simulated seconds (`(tick - accepted_tick)*dt`, :3627-3640) and state that lateness is fixed at k-1.
- Test 10 should assert the fixed value.

P3-3. Static docstring and misc
- The `publish()` docstring at :4780-4784 ("every cycle ... hand-edit lasts until the next cycle") changes. State in HELP/README text for agents that their edit lasts about 1 s.
- `--cycles` counting cycles changes the meaning of existing CLI tests that count ticks. Section 6 covers it.
- `N mod k` refusal on resume uses the resulting values (section 3). Good.

Confirmed OK (no finding):
- Per-segment epoch: matches downtime F1 (freeze, ADR:464-490). A resume is never "hours behind".
- Catch-up by whole cycles with no burst beyond k: matches the ADR answer (ADR:302-314). It overrides the ADR:275 option text, as the mapping noted.
- Crossing-multiple-of-N checkpoint: the correct fix for unaligned resume (the ADR's J(xxii) "tick is a multiple of N" would skip).
- Receipt tick as the cycle's start tick with offset 0: same as today (console.py:3557-3560, 4094).
- Replay dwell at `(tick-1)*tick_us + offset_us` stays valid, because row 1 is tick a+1 (:2418).
- The 76 ms per 100 ms feasibility (ADR:316-327) leaves about 24 ms of headroom, which is thin for a checkpoint plus static cycle (P2-6).

Limits: I did not measure anything. The cycle cost figures are the ADR's. I did not verify the ring cadence_classes keying (P2-4) or whether the row chain covers `lag_us` (P2-5).
