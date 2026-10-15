# #23 design review r2 — systems

Received 2026-10-12T06:01:15.142Z; saved verbatim (harness indent removed).

---

**#23 design r2 confirmation (systems).** Reviewed `DESIGN.md` at sha256 c0fcfe06…3855, read only, against vehicle source at 7a87eb8 and the chassis.

**Verdict: approve with changes.** All of my r1 findings are resolved. Two changes are needed before implementation, and both are text changes to the design that a targeted check can confirm without another full round:
- **N1 (P1):** with 3,000 slots, the per-cycle telemetry ring scans probably no longer fit the 100 ms cycle.
- **N2 (P2):** `cycle_us` on every row cannot be known when those rows are written.

The other new items are P2 and P3.

## r1 findings: all resolved

- **P1-1 (`unwritten_results` and duplicate results): resolved.**
  - §4 fixes the row-1 invariant (effects, receipts, `windows` deltas and the `receipt` counter on row 1 only; `published` on the last row only). That keeps `row.tick − 1` correct (`console.py:2487`) and replay's dwell stamp correct (`:2418`).
  - `unwritten_results` and `_verified_lines` reset per cycle, using the `k` now in the header.
  - Format v3, and tests 9 and 16.
  - Implementation note: at the cycle reset, `unwritten_results` must move what is still pending into `unwritten`, not discard it. That is how a cycle whose publication failed stays owed.
- **P1-2 (rotation): resolved.** `(a // k) % n` advances by exactly one per cycle, including from an unaligned resume, and equals `tick % n` at k=1 (test 17). After a resume at a+j inside a cycle, the same window can go first twice in a row. That is harmless.
- **P2-1 (refusal partway through a cycle): resolved.** §1 steps into locals, records rows 1..j−1 and exits 3 naming the last recorded tick; `_report_effect` and dwell are taken against step 1 (test 18).
  - Wording: with write-ahead, row 1 of a command-bearing cycle is already durable, so "the j−1 rows are appended with one fsync" should read "rows 2..j−1".
- **P2-2 (SIGTERM): resolved.** §5 adds a stop flag, checks it at cycle boundaries, caps the wait, and takes the clean-end path (test 19). Docker's 10 s default grace covers one cycle plus the checkpoint.
- **P2-3 (rollout): resolved.** §7 names the values explicitly with no `:?`, passes each flag only when set, carries the operator step for refused checkpoints, targets the vehicle-adoption shape, sets the ring to 3,000, adds the `git submodule status` check, and separates the probe's cadence from its deadlines. Ring depth raises N1 below.
- **P2-4 (measurement and seam): resolved in principle.** §8 gates adoption on `measure_clock` and §6 injects the clock and sleeper. §8 does not name the ring size or the write-ahead fsync as measured variables (N1, N7).
- **P3 items: all resolved.**
  - `CLOCK_MONOTONIC` named.
  - Integer-ns due times with `m` held as a `Fraction`.
  - Epoch read after recovery; the wait is a loop.
  - Bounds of 1 ms ≤ k·dt/m ≤ 60 s.
  - Frame gap across a resume corrected.
  - Deferral due at a+k.
  - Static files use the crossing rule and are also written on the first cycle and after a repair.
  - Format v3, with cycle grouping taken from the header and nearest-rank percentiles.
  - `N` precedence and the refusal exit code.
  - Submodule drift.

## The write-ahead row 1 at each crash point

The ordering is claim → take retired → validate → step 1 → row 1 appended and fsynced → steps 2..k → rows 2..k with one fsync → publish → notes → checkpoint.

| Crash point | Outcome |
|---|---|
| After the take is retired, before row 1 is durable | The batch is lost. This is the residual #39 accepted, now one step long, as today. |
| After row 1 is durable, during steps 2..k or before the group fsync | Replay reaches a+1. Row 1's receipts are owed, because the cycle-scoped set has no note and the segment ends. `published_tick` stays at a, deferral deltas replay, and the resume starts at a+1. **Correct.** |
| Torn group append (whole rows through a+j) | Replays to a+j. `append_or_restore` cuts an in-process failure back to just after row 1, and the chain continues from row 1. **Correct.** |
| After the group fsync, during publication, notes or checkpoint | Unchanged from today. |

- A `RecordUnwritable` on the group append ends the segment after row 1, and the next boot owes row 1's receipts. **Correct.**
- Minor: after a crash at a+j, a deferral due at a+k settles at a+j+k, so its result text names a tick that is again not honoured. The text could say "the next cycle's start, tick a+k (later across a restart)". P3.

## The backstop under `restart: unless-stopped`

- **It cannot hot-loop.** Lag can only reach 30 s after at least 30 s of wall time since the epoch.
  - With a sustained cycle cost c above the 100 ms period, the backstop fires after about 30·c/(c − 100 ms) seconds: 330 s at c = 110 ms, 60 s at c = 200 ms.
  - It then takes a clean end (checkpoint plus manifest), so nothing is lost, and the restart begins a fresh epoch.
  - The container has run for more than 10 s, so docker's backoff stays at its base. The result is a periodic restart roughly every 30 s to 5 min, not a tight loop.
- **Costs under persistent overload:**
  - Each restart is a new boot. A new segment file and history entry appear (I did not find a bound on the checkpoint's `segments` list).
  - Every window's `boot_id` changes, so agents see the vehicle restart every few minutes.
  - Each restart pays the engine-identity hash, the replay and a pre-serve checkpoint.
- **Acceptable until #26 under two conditions:**
  - The §8 gate actually passes at the deployed values, which depends on N1.
  - The backstop can be told apart from a fault (N4).

## New findings

**N1 (P1). At 3,000 slots, the telemetry-ring scans probably exceed the cycle budget, and §8 does not measure them.**
- **Evidence:** `Window.ring_frames()` (`console.py:4888-4913`) does a full `scandir` of `telemetry/`, a Python check per entry, and a sort. Each window runs it four times per cycle:
  - `write_frame`'s prune (`:4949`);
  - `mirror()`'s `held` and `losses` fields (`:4866-4867`; `ring_losses` rescans, `:4915-4917`);
  - `pending.json`'s `ring_losses` (`:4831`).
- **Scale:** at 3,000 slots that is 4 × 3,000 × 10 windows = 120,000 entries per cycle, 1.2 million per second at 10 cycles/s.
- **Estimate (not measured; this review is read only):** at roughly 0.5–1 µs per entry, that is about 60–120 ms of each 100 ms cycle in ring scans alone.
  - The same scans cost about a tenth of that at 300 slots. The ADR's roughly 24 ms publication figure was taken on a full ring at the old default size.
  - The ADR leaves only about 10–24 ms of headroom.
- **Consequence:** sustained overrun. Under N2's backstop that becomes the periodic restarts described above. The ring size is world identity, so it cannot simply be lowered after the first deploy.
- **Fix:**
  - Keep the held-frame list in memory: one scan when the handle opens, at boot and after a repair, then pop and push per frame. Reconcile with one scan every N ticks, so `held` and `losses` stay derived from disk to within a second when an agent deletes frames.
  - Compute `held` and `losses` once per publication.
  - State in §8 that `measure_clock` runs on a full 3,000-slot ring with ten windows.
  - Add ring size to the list of things §8 may revisit with John.

**N2 (P2). `cycle_us` and end lag on every row cannot be computed when the rows are written.**
- **Evidence:** §2 defines `cycle_us` = end − start and end lag = end − due, and puts `cycle_us` on all k rows. But row 1 is fsynced before steps 2..k, and rows 2..k are fsynced before publication (§4: "publication follows the record's fsync"). None of the rows can know the cycle's end.
- **Fix:** pick and state one of these:
  - Row 1 of each cycle carries the previous cycle's `cycle_us` and end lag. The final cycle's cost goes in the manifest at a clean end, and the crashed-segment reader reports it as unknown. Test 4's equality then excludes that cycle, or the clean-end manifest drops it as well.
  - Define cost as start until the record is durable. This omits publication, about 24 ms, and so understates "overran".

  The first preserves what §2 is for.

**N3 (P2). The backstop on the per-slug (aurora-port) shape stops a window for good.**
- **Evidence:** §7 says the per-slug shape "gets the cadence". There, `serve_vehicle.sh` backgrounds one console per slug and `wait`s for all of them (`:104-125`).
  - A backstop exit 3 is restarted by nothing until every console has exited.
  - Without `--state-dir` there is no clean-end checkpoint, so a restart would be a fresh world, not a resume.
- **Fix:** do either of these:
  - Without a state directory, the backstop rebases the epoch and reports a stall instead of exiting.
  - State that #23 does not support the per-slug shape and take that shape out of §7's touch points.

**N4 (P3). The backstop exits with the same code as real faults.** Exit 3 is also `UncomparableState` and `RecordUnwritable` (`:5784`, `:5787`). Give the backstop its own exit code, or rely on the `lag_backstop` journal event. Either way, the chassis status and journal surfaces should show backstops, so a host that keeps tripping it is visible.

**N5 (P3). The design should state the 3,000-slot storage cost.**
- The shared `diode` image defaults to 2G (`scripts/volume_images.py:129-133`) and also holds every agent's `output/`.
- Ring storage is (frame bytes, block-rounded) × 3,000 × windows: about 33,000 files and inodes. At an assumed 4–12 KB per frame, that is roughly 130–400 MB.
- Frame churn is about 100 files created and unlinked per second, without fsync.
- Since the ring cannot shrink without a new world, §8 should record the measured frame size and the share of `SPACE_DIODE_SIZE` before the first deploy, along with whether `volume_images.py check`'s fill warning moves.

**N6 (P3). The stop and stall parameters are unspecified.**
- The value of the wait cap. Suggest 100 ms or less.
- The meaning of "far later" in stall detection.
- That the SIGTERM handler is installed before recovery, so a stop during a long resume ends at the first boundary.
- When N = k, every cycle crosses a multiple of N, so the static rewrite cannot be staggered from the checkpoint. Say so.

**N7 (P3). §8 omits the write-ahead fsync.** A command-bearing cycle now makes two record fsyncs. §8's measurement should include it alongside option B's take barriers.

## Coverage

- **Read:**
  - r2 `DESIGN.md` in full.
  - `console.py`: the ring path (`:4888-4953`), the mirror (`:4860-4886`), the publish (`:4779-4837`), and the stop and exit paths.
  - `volume_images.py`'s diode image, and the chassis `serve_vehicle.sh` shapes.
  - The r1 evidence carried over.
- **Not read:** the other three r1 reviews in full; I relied on §10 for their mapping.
- **Not run:** nothing, as asked. The N1 cost and N5 sizes are estimates, which is why both fixes include a measurement.

## Files

- `/home/john/space_chassis/.scratch/wp08-23/DESIGN.md`
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9/tools/console.py`
- `/home/john/space_chassis/containers/serve_vehicle.sh`
- `/home/john/space_chassis/scripts/volume_images.py`
