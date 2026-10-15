# #23 design review r1 — systems (ordering, durability, rollout)

Received 2026-10-12T05:01:36.632Z; saved verbatim (harness indent removed).

---

**Verdict: request changes.** The design gets the cycle order right: claim, stamp, step k ticks, write k rows with one fsync, publish, then checkpoint when the cycle crosses a multiple of N. Its torn-tail recovery and its #39 interaction hold up. But it changes the record's row layout and the tick step without following two existing consumers that assume one tick per cycle. Both break silently at the deployed values (k=5, up to 10 windows), and the design's choice to keep existing tests at k=1 hides both.

## P1

**P1-1. `unwritten_results` lists every recorded verdict as unwritten once k>1, so results get duplicated.**
- **Evidence:** `tools/console.py:2476-2491`. Each tick row flushes the previous row's pending receipts into `unwritten` and replaces `pending` with its own (`unwritten.extend(pending.values()); pending = {...}`). Notes pop from `pending`. Design §4 puts receipts on row a+1 and the `results_written` notes after row a+k, once publishing is done (`_note_window_results` at :3407-3425, called from `publish` at :4808).
- **Scenario:** when row a+2 is read, row a+1's receipts are declared unwritten. The cycle's notes then pop from an empty `pending`. Every resume treats every verdict since the checkpoint anchor as owed (`resume_executive` :5190, then `publish_obligations` :3275).
  - `results_on_disk` stops after `OUTPUT_SCAN_ENTRIES`/`OUTPUT_SCAN_BYTES` (:2591). An agent's `output/` grows for the whole run, so past that limit the result is written a second time. That breaks the contract's one result per command.
  - Under the limit the result is found, but it still costs a wasted fsync.
  - The anchor is at most N ticks back, but a run of failed cadence checkpoints widens that.
  - Design §4 changes only replay's completeness check.
- **Fix:**
  - Keep receipts, effects and window deltas on row 1. That preserves `tick: row["tick"] - 1` (:2487) and replay's dwell stamp `(tick-1)*tick_us + offset_us` (:2418).
  - Change `unwritten_results` so a row with no receipts does not flush `pending`. Simplest: accumulate, pop on notes, flush at segment end. Receipts are unique per (window, local).
  - Say so in §4.
- **Tests:**
  - A k=5 run followed by a clean resume: `unwritten_results == []` and no duplicate result files.
  - A crash after the rows and before the notes: exactly that cycle's receipts are listed.
- `tools/measure_clock.py:385` also calls this function.

**P1-2. The arbitration rotation collapses when k divides into the window count (ADR 0001 choice A).**
- **Evidence:** `order()` at `console.py:3051-3061` rotates by `tick % n`. ADR 0001 :53 and :133 say "no name holds a permanent priority". The vehicle test at `test_vehicle_config.py:21947` pins `sorted(slugs)[tick % len(slugs)]`.
- **Scenario:** the cycle-start tick now steps by k, so only n/gcd(n,k) starting positions are ever used.
  - n=10, k=5: the windows at sorted index 0 and 5 go first in every cycle, for both deferral settlement and claims (`cycle` :3087-3133). They win every conflict-domain contest, permanently.
  - n=5: one window always goes first.
  - This applies to the vehicle-adoption shape (one executive, repeated `--slug`). Aurora-port runs one process per slug, so it has no cross-window arbitration.
- **Fix:** rotate by cycle index, `(cycle_start_tick // k) % n`. It advances by exactly 1 per cycle even from an unaligned resume tick, and equals `tick % n` at k=1, so existing tests keep their meaning. Replay re-runs no validation, so determinism is unaffected.
- **Test:** n=10, k=5, ten consecutive cycles: each window goes first exactly once.

## P2

**P2-1. How k steps commit, and what a failure partway through a cycle does, is unspecified.**
- **Evidence:** today one `advance` runs in locals, then truth, tick and lineage commit together (:3140-3151), and `main` reports "the lineage ends at tick {executive.tick}" on `UncomparableState` (:5779-5783).
- **Scenario:** if this is implemented as a loop of today's body, a refusal at step j>1 leaves the executive at a+j-1 in memory with no row written. The stderr line then names the wrong tick. The cycle's claimed batches (takes already retired, :4483-4499) are neither recorded nor answered, so they are lost.
- **Fix:** state either of these:
  - (a) Step into locals. On a refusal at step j>1, append the j-1 completed rows (row 1 carries receipts, no marks), fsync, then stop with exit 3, so the batch is owed and answered on resume.
  - (b) Commit nothing, and record the batch loss as an accepted residual.
- Also specify `_report_effect(verdict, before, after)` (:3148): after step 1, which matches the receipt tick, or after step k.

**P2-2. A SIGTERM that lands mid-cycle loses the claimed batch, and #23 makes that routine.**
- **Evidence:**
  - The take is retired inside `_ingest` before `advance` and `_record_cycle` (:3129-3155).
  - `console.py` installs no signal handler; only SIGINT reaches `KeyboardInterrupt` (:5775).
  - On aurora-port, `serve_vehicle.sh:124` forwards TERM to the consoles. On vehicle-adoption the script `exec`s the console, so docker's SIGTERM goes straight to it.
- **Scenario:** a stop or restart that lands between the last take's retirement and the row fsync consumes the batch: the console is emptied, no row is written, and no result ever appears.
  - This is an existing residual (the #39 memo names its class).
  - At k=5 the window spans 5 plant steps, about 50 ms of an about 76 ms busy 100 ms cycle (ADR feasibility figures). Today it is one step per 5 s poll.
  - The deployed stack would also never write a clean-end checkpoint or the clean-end lag summary from design §2, because docker stops it with SIGTERM.
- **Fix:**
  - Add a SIGTERM handler that sets a stop flag. The loop checks it at cycle boundaries, and the pacing sleep is interruptible.
  - A stop then follows the existing clean-end path.
- **Test:** SIGTERM during a cycle that claimed a batch; the batch is answered after the restart.

**P2-3. The cross-repo rollout leaves four things for the implementer to decide.**
- **(a) Where the deployed values live.** "Three required env vars" plus "a stack naming none refuses" fits three incompatible implementations:
  - Compose defaults `${VEHICLE_MULTIPLIER:-1}`: the stack names the values and never refuses.
  - `.env` only: `prepare_host.sh`/`roster.py` would have to write them, and they are not in §5's touch points. Without them the vehicle restart-loops.
  - `${VAR:?}`: compose interpolation fails for every command, including `docker compose --profile fleet config -q` and agent-only `up`s.

  Also, under `set -eu` an unset variable aborts the script itself with exit 2, naming only that one variable, instead of reaching the console's refusal by name. And a resume should inherit the values, so the script should pass each flag only when it is set, e.g. `${VEHICLE_MULTIPLIER:+--multiplier "$VEHICLE_MULTIPLIER"}`.

  Recommend: the generated compose names 1/5/50 explicitly ("what the deployed stack names", ADR :1127-1129), never `:?`, and the script passes each flag only when set.
- **(b) Old checkpoints are refused after the pin bump.** `engine_identity` (`checkpoint.py:176-199`) hashes the engine tools, so any `console.py` change makes the existing checkpoint refused, and the console will not start a fresh world over it (`console.py:5745-5750`). On vehicle-adoption (`VEHICLE_STATE_DIR=/state`, bound via `_binds`) the pin bump therefore restart-loops until the operator clears `/state`. This happens on every vehicle bump, but the adoption increment must carry that operator step.
- **(c) Which chassis shape the delta targets.**
  - Aurora-port's `serve_vehicle.sh` runs one console per slug with no `--state-dir`. It has no record, so it gets no lag rows, no group commit and no checkpoint; lag is visible only through the stop print, and only on SIGINT.
  - Vehicle-adoption `exec`s one executive with `/state`.
  - The test pins sit at different lines: :610 versus :622/:623.
- **(d) Ring depth.** `VEHICLE_RING_SLOTS=300` at 10 frames/s holds 30 s of telemetry history, against 25 min at today's 5 s poll. Ring size is world identity (a restart naming another refuses), so it must be chosen before the first deploy.
- **Coexistence:** the order (vehicle merges first; the chassis adopts pin and delta together) is sound. The pinned `dd79e76` keeps `--poll`, and nothing deployed breaks as long as pin, delta and image rebuild land together. A new image with the old compose restart-loops by design. The old image with the new compose falls back to `DIODE_POLL_SECONDS=5` and works.

**P2-4. Feasibility has not been measured under option B, and the test seam cannot check "never ahead".**
- **Feasibility:** the ADR's figures (76 ms p50, about 90 ms p95, plus 9 ms on a checkpointing cycle, out of 100 ms) predate option B. HEAD `7a87eb8` is the option B commit. Each window with a non-empty console now adds:
  - a take directory fsync;
  - a republish file fsync (`sync_file=durable`);
  - a removal directory fsync.

  That comes on top of the output directory fsync and the note fsync, plus one record fsync per cycle. On loop-backed volume images that can exceed the remaining headroom. With no ceiling or shedding until #26, a sustained overrun builds lag without limit. Fix: re-measure with `measure_clock`, including the take barriers, on the deployment volume images before fixing m=1, k=5 for ten windows. Add this to §6's `measure_clock` changes.
- **The seam:** a boolean "don't pace" seam cannot test never-ahead or lag. CLI tests at m=1000, k=1 have a 20 µs period, so they are always behind: the sleep path never runs and every row counts as missed. "Genuinely paced" is therefore inaccurate. Fix: inject the clock (`monotonic_ns` and a sleep-until) and test never-ahead and lag against a fake clock. If CLI tests should exercise the real sleep, pick an m with a period of a few ms.

## P3 (unspecified or imprecise)

- **The clock.**
  - Name `CLOCK_MONOTONIC` (`time.monotonic_ns`). It stops during host suspend, so the world pauses with no lag. It keeps running through `docker pause`, SIGSTOP or VM steal, which then cause a catch-up storm. Without #26's ceiling, a 1 h freeze costs hours of back-to-back cycles on a full core. Say that is accepted until #26.
  - Compute due times in integer ns.
  - Validate that k·dt/m is finite and at least 1 ns, and bound it above: a tiny m makes the sleep infinite, and `time.sleep(inf)` raises `OverflowError`.
  - Sleep in a `while now < due` loop.
  - Read E just before the first wait, after the resume's recovery and checkpoint, or the first cycles start behind and count as missed.
- **Frame gap across a resume.** It is longer, not shorter: k+j (j<k) after a partial-cycle tail, plus downtime. It is shorter only when a resume names a smaller k. Correct §4 and limit acceptance test 1 to within a segment.
- **Deferrals.**
  - `due = self.tick + 1` (:4044), so at k>1 every deferral falls due mid-cycle and settles exactly k ticks after acceptance.
  - The result text (:4060) tells the agent "due at tick {tick+1}", which is never honoured. Set `due = tick + k`, or reword the text.
  - Expiry is unaffected: the smallest `maximum_queue_age_s` in the corpus is 10 s, against k·dt = 0.1 s.
- **Static file cadence.**
  - Use the same "crossed a multiple of N" predicate as the checkpoint; `tick % N == 0` never fires after an unaligned resume, which §4 allows.
  - Also write HELP and README on a segment's first cycle and on the cycle after a repair. `repair` (:4329-4350) writes neither, so today the next publish restores them.
  - Tying the cadence to N means an operator who raises N to reduce checkpoint cost also delays the HELP and README rewrites.
  - Cost: the files are written without fsync (`write_text_atomic` defaults, :429-430). That is about 850 KB of page cache per rewrite across ten windows: 0.85 MB/s at N=50, against 8.5 MB/s if written every cycle. That is acceptable.
- **The record.**
  - The row key set is exact (:1354), so adding `lag_us` needs a `RECORD_FORMAT` bump or a reader that accepts both. Specify which.
  - Specify the field that groups a cycle's rows ("stepped together"), and whether the percentiles count per cycle or per tick. A partial final cycle otherwise makes the crashed-segment reader's summary differ from the clean-end one (acceptance test 4).
- **Precedence of N:** the `checkpoint_every` seam versus `--checkpoint-ticks` versus the inherited value (:5148, :5205).
- **Refusal exit code:** argparse exits 2; the mapping assumed exit 3. The chassis tests will pin one of them.
- **Submodule drift:** the chassis's vehicle checkout is at `8c6f71d`, ahead of the recorded pin `dd79e76`. A tree advanced past #23 before the adoption fails `--poll` in `tests/test_vehicle_reconciliation.py:211`, so check `git submodule status` before gates.
- **Probe timing:** `diode_probe.check_state_is_a_mirror` sleeps `poll × 1.5`, which is 150 ms at 0.1 s. Under the scheduler delays recorded in AUR-GOV-04, about 1 s is safer.

## Checked and clean

- **Torn multi-row append.** `append_or_restore` cuts back an in-process failure. A crash between the write and the fsync, or a short write under SIGKILL, can persist whole lines a+1..a+j. Replay accepts them: the ticks are contiguous, the chain verifies, and `published: {}` is valid (:1499-1508). `published_tick` stays put, so the guard at :5196-5197 is fine. Row a+1's receipts are owed once P1-1 is fixed. The resume starts at a+j, and the crossing rule keeps the checkpoint cadence.
- **#39 option B.** The claim runs once per `cycle()` whatever k is (:3129-3133 → :4353). Take names are per boot plus `take_seq` (:4421), and the take's whole lifecycle completes inside the claim. Retries now happen every 100 ms; stderr lines repeat at that rate, but docker logs are capped at 10 MB. The design changes no barrier order. The batch loss in P2-2 is pre-existing and only becomes more frequent.

## Coverage

- **Read:**
  - DESIGN.md and MAPPING.md.
  - `console.py`: `cycle`, `_record_cycle`, `_append_record`, `replay_record`, `unwritten_results`, `results_on_disk`, `order`, `claim` and the option B take path, `_settle`/defer, `publish`, `run`/`main` stop paths, `resume_executive`.
  - `checkpoint.py`: `Compatibility`, `engine_identity`, `capture_state`.
  - ADR 0002 :300-330 and :660-670; ADR 0001's rotation lines.
  - The #39 decision memo.
  - The chassis on aurora-port and vehicle-adoption: `serve_vehicle.sh`, `build_compose.py`'s vehicle block, the reconciliation test pins; and `diode_probe.py`'s timing.
- **Not read:** `check_vehicle.py` `check_console_flags`, `measure_clock.py` internals, `test_vehicle_config.py` beyond the rotation test, the rest of the ADR.
- **Not run:** no tests, collection or linters, per the read-only instruction.
- **Uncertain:** the per-fsync cost on the deployment's loop-backed images; that is why P2-4 asks for a measurement and makes no claim.

## Files

- `/home/john/space_chassis/.scratch/wp08-23/DESIGN.md`
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9/tools/console.py`
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9/tools/checkpoint.py`
- `/home/john/space_chassis/containers/serve_vehicle.sh`
- `/home/john/space_chassis/scripts/build_compose.py`
- `/home/john/space_chassis/tests/test_vehicle_reconciliation.py`
- `/home/john/space_chassis/contract/diode_probe.py`
- `/home/john/space_chassis/governance/vehicle/records/2026-10-11-39-claim-race-decision-memo.md`
