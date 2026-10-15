# #23 design review r2 — simulation architect

Received 2026-10-12T05:59:11.065Z; saved verbatim (harness indent removed).

---

VERDICT (r2, DESIGN.md sha256 c0fcfe06...943855, confirmed by sha256sum): approve with changes. All of my r1 findings are resolved except for one inconsistency the resolution introduced (P2-A below). I found one new cost risk that the 3,000-slot ring creates (P2-B). Read-only; nothing was run. Source is the vehicle worktree at 7a87eb8 (V = /tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9).

CONFIRMATION OF MY R1 FINDINGS
- P1-1 backstop and named stalls: resolved by §5, with test 20.
  - The check happens at a cycle's start, before any claim, so the clean-end checkpoint is always at a boundary (console.py:3079 sets in_cycle only inside cycle()).
  - Exit 3 plus restart gives a fresh epoch, which matches F1 (freeze).
  - Residuals are P3-1 and P3-2 below.
- P2-1 write-ahead row 1: resolved by §4.
  - The claim-to-durable window is one step again, as today.
  - A cycle with nothing to record keeps the single group fsync.
- P2-2 cost and end lag: the intent is resolved, but the implementation as written cannot work (P2-A).
- P2-3 causality: resolved. The paragraph is accurate; "more while catching up" covers the lag-sized backdating.
- P2-4 frame gap: resolved. k'+j after a partial cycle of j rows is correct, and keeping the crossing rule is sound with N mod k = 0.
  - Cadence_classes keying: it is not keyed to anything today. Evidence: `Window.write_frame` (console.py:4919-4954) passes the whole `executive.truth` to `emit_frame` (plant.py:1020) with `tick` and `seq`. I found no rate or period filtering in either, and none in console.py by grep. presentation.yaml:283-301 states membership as "a frame carries the values whose period has elapsed" but nothing implements it yet. If it is implemented later it must key on tick or met_s, never on seq or frame count. Otherwise a resume's k'+j gap shifts the phase of the 5 Hz class. Add that as a one-line constraint in §1. This is limited evidence: I grepped and read only the call sites, not all of emit_frame.
- P2-5 lag_us: resolved. Chain only, never state_hash or lineage, and test 14 covers it.
- P2-6 stagger: resolved. §8 (worst-cycle measurement) is the right gate for the remaining margin. Say explicitly "the cycle after the one that crossed". A repair-triggered static rewrite can still coincide with a checkpoint cycle, which is harmless.
- P3 items:
  - Integer nanosecond due times, epoch placement after recovery, the capped sleep loop, and the deferral due at a+k are all resolved.
  - Deferral due is now `tick + k` instead of console.py:4047's `tick + 1`. The `>=` test at :3627 keeps a resume with a changed k safe.

NEW BOUNDS
- k <= tick_hz / max_rate (= 5): correct and matches ADR B2. It is a ceiling, so k = 1..5 all satisfy it. Use the floor of the ratio when it is not an integer.
- 1 ms <= k*dt/m <= 60 s: consistent with the deployed 100 ms.
  - The lower bound means k = 1 needs m <= 20, so the old `--poll 0` style tests need the "few milliseconds" tick period that §6 already says.
  - The 60 s ceiling sits above the 30 s backstop. That is fine, since the backstop compares start lag against due time, not the period.

FINDINGS

P2-A (§2 with §4): `cycle_us` and end lag cannot be in the rows as specified.
- The cycle's end falls after publication, which follows the record fsync. Rows are written before publication, and under the write-ahead rule row 1 is written before steps 2..k even run. "Each of its k rows carries lag_us and cycle_us" is therefore unimplementable. Start lag is known at cycle start, so it can be in the rows.
- Failure: the implementer either records a cost that excludes publication, which is the part this finding wanted visible, or writes extra rows.
- Fix, either of:
  - (a) Carry the previous cycle's `cycle_us` and end lag in the next cycle's row 1. The final cycle's cost goes only in the manifest.
  - (b) Record cost in a post-publication note, like `results_written`.
- Option (a) costs no extra write and keeps summary equality for a crashed segment, losing only the last cycle's cost. Either way, say which. Test 4 must then compare p50/p95/p99/max over the same cycle population in the reader and the manifest.

P2-B (§7 ring 3,000, §8): per-cycle ring cost grows tenfold and the headroom is about 24 ms.
- Evidence:
  - `write_frame` prunes by calling `ring_frames()` every cycle (console.py:4949-4950).
  - `ring_losses` also calls `ring_frames()` (:4915).
  - `ring_frames` (:4888-4900) lists the telemetry directory, filters and sorts it by integer stem.
  - At 300 slots that is small. At 3,000 slots, times ten windows, at 10 cycles per second, it is about 300,000 directory entries listed per wall second, plus the file count.
- The ADR's feasibility (about 76 of 100 ms) was measured at 300 slots, so this could consume a large part of the margin unmeasured.
- Fix:
  - Add a 3,000-slot ring to `measure_clock` (§6/§8).
  - Prune in O(1): unlink name `seq - ring_slots` directly. Keep the listing scan only for startup or repair.
  - Compute `ring_losses` as `max(0, seq - held)` from a counter, not a listing.
- Also check the per-window storage in the bounded /diode image: 3,000 frames times ten windows.

P3-1: the backstop's exit code and loop.
- §3 says "the console's existing start-refusal exit code" is 3, and `UncomparableState` and `RecordUnwritable` also exit 3. The backstop shares it. The chassis and `status.py` cannot tell a stall backstop from a failure by exit code.
- Under sustained overload (cycle cost above k*dt/m) it is a loop with a roughly 90 s duty cycle at a 150 ms cycle: lag grows, backstop, restart, repeat.
- Fix: use a distinct exit code if one is free, or rely on the journaled `lag_backstop` event and have `status.py` read it. Also include the consecutive-backstop count in the event so an unattended loop is visible.

P3-2: stall thresholds are not numeric.
- "Far later than requested" and "far larger than any cycle's cost" need constants (for example, an overshoot of at least 1 s and at least 10 periods). Without them, test 20's "shorter stall" is ambiguous.

P3-3: parse `m` as a decimal string.
- Use `Fraction(str)`, not `Fraction(float)`, so `0.3` stays 3/10 and the checkpointed "p/q" is stable.

P3-4: rotation after an unaligned resume.
- `(a // k) % n` can repeat the previous index after a resume at a+j. Harmless (the partial cycle published nothing), but "keeps advancing by one" is not guaranteed. Say "rotation stays a function of the tick".

P3-5: SIGTERM must reach the console.
- §5 assumes a handler in the console. The chassis `serve_vehicle.sh` traps TERM. In the per-slug shape, the trap must forward the signal. In the `exec` shape (vehicle-adoption) the console receives it directly.
- Add one line to §7's touch points and keep test 19 covering the container path.

P3-6: §1 mentions "smallest `maximum_queue_age_s` is 10 s". My grep of the domains/*/commands.yaml files saw 30 s as the lowest. It is only a clarification; either is far above 0.1 s. Cite the file.

Limits: nothing was measured, so the cost claims in P2-B rest on code reading and the ADR's figures. I checked the frame-builder call sites only, not the whole of emit_frame. I did not check the chassis scripts.
