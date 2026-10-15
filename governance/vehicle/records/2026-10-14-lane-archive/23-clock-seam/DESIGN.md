# #23 WP08.5 — the clock seam: design, revision 3 (hardening)

Vehicle line, 2026-10-12. Basis: ADR 0002 (A2, B2, C1, G, J, Consequences), ADR 0001 (choice A), the
read-only mapping `MAPPING.md` (vehicle HEAD `7a87eb8`), and two rounds of four independent design
reviews in `reviews/`. r1 (on `DESIGN.r1.md`, `89389a4c…`): simulation approve with changes; Codex,
determinism, systems request changes. r2 (on `DESIGN.r2.md`, `c0fcfe06…`): simulation, determinism,
systems approve with changes; Codex request changes. §10 maps r1 findings, §11 r2 findings, to their
resolutions. Design only: no code, no tests, no slot.

**John's decisions:** cycles never run ahead (§1); static files every `N` ticks (§1); lag per cycle
(§2); descriptive flag names (§3); an interim lag backstop until #26 (§5); about 5 minutes of
telemetry history, 3,000 frames (§7). Everything else follows a named standard or the ADR.

## 1. The clock and the cycle

- **Accepted values (ADR):** `m = 1`, `k = 5`, `N = tick_hz = 50`, burst = `k` (whole cycles back to
  back), lag ceiling 30 s. `m`, `k`, `N` are required with no default; the deployed stack names them.
- **Clock:** `time.monotonic_ns()` (CLOCK_MONOTONIC). All due-time arithmetic is integer nanoseconds:
  `m` is parsed from its decimal string as a `fractions.Fraction` (never through a float), and `due_ns(t) = E_ns + (t − t0)·dt_ns/m` is evaluated per
  cycle from the epoch (absolute, so no drift accumulates) and rounded once.
- **Epoch per segment:** `E` is read after the start's or resume's recovery and pre-serve checkpoint,
  immediately before the first wait, so recovery time never counts as lag. `t0` is the segment's
  first tick; its first cycle covers `t0+1 … t0+k`.
- **Never ahead (John):** a cycle covering `a+1 … a+k` starts at `max(due(a+k), end of the previous
  cycle)`. The wait is a loop (`while now < due: sleep(min(due − now, 100 ms))`) so early wake-ups
  and signals are handled; the 100 ms cap keeps SIGTERM responsive.
- **Bounds on the inputs:** `k·dt/m` must be finite, ≥ 1 ms and ≤ 60 s, so neither a vanishing nor an
  unbounded sleep can be configured.
- **Publication rate (ADR B :334–351):** a cycle's frame rate, `tick_hz / k` frames per mission second,
  must be at least the highest declared channel rate (10 Hz today), so `k ≤ tick_hz / max_rate` = 5.
  A start or resume naming a larger `k` refuses by name. This is the ADR's rule, not a new policy.
- **One claim and one publication per cycle.** Each cycle claims every console once, stamps accepted
  effects at `offset_us = 0` of its first tick (receipt tick = the cycle's start tick, as today), steps
  `k` ticks (the remaining `k − 1` carry no effects) and publishes once. Within a segment, frames are
  exactly `k` ticks apart and `met_s` differs by `k·dt`.
- **Causality, stated plainly (for the ADR amendment and the cycle docstring):** a command written
  while tick `a` is the newest frame is applied from tick `a`, whose due time has passed by up to
  `k·dt/m` plus the cycle's cost (more while catching up). "Takes effect within `k` ticks" means it
  appears in the next frame. No claim-time field is published to windows.
- **Stepping and effects (determinism review P1-B):** step tick `a+1` with the cycle's effects; run
  `_report_effect` and the dwell bookkeeping against **that** step's before and after; then step the
  remaining `k − 1` ticks with no effects. This is exactly what replay does per row.
- **A refusal partway through a cycle:** stepping runs into locals. If the compare-point refuses at
  step `j > 1`, only the completed rows **not yet durable** are appended, with one `fsync`: rows
  `1 … j−1` on a quiet cycle; rows `2 … j−1` on a write-ahead cycle (§4), which is nothing at all when
  `j = 2`. Row 1 carries the cycle's receipts, so they are owed and answered on resume. Nothing past
  the durable rows is committed to `tick`, `truth` or `lineage`, and the run stops with exit 3, naming
  the **last durable tick** (not `executive.tick`). If that suffix append itself fails, the durable
  prefix stands and the message names its last tick. A refusal at step 1 records nothing, as today.
- **Deferrals:** a deferral accepted in a cycle is due at tick `a + k`, the next cycle's start, and
  settles at the **first cycle boundary at or after** its due tick. Its result text says "due at tick
  `a + k` (later across a restart)": after a crash mid-cycle and a resume at `a + j`, boundaries move to
  `a + j + i·k`. (Today's `due = tick + 1` would name a tick that is never honoured.) Expiry stays in
  simulated seconds; the smallest `maximum_queue_age_s` in the corpus is 5 s
  (`domains/propulsion/commands.yaml`), against at most 0.1 s of settlement delay.
- **Arbitration (ADR 0001 choice A):** the window order rotates by **cycle**, `(a // k) % n`, not by
  tick. That gives each window the first place once per `n` cycles whatever `gcd(n, k)`, equals today's
  `tick % n` at `k = 1`, and stays a function of the tick (after an unaligned resume one window may go
  first twice in a row, which is harmless: the partial cycle published nothing).
- **Static `HELP.md` / `README.md` (John: every `N` ticks):** rewritten at the end of **the cycle after
  the one that crossed** a multiple of `N`, so the static and checkpoint costs normally fall in
  different cycles; also on a segment's first cycle and the cycle after a `repair`. **Exceptions,
  stated:** when `N = k` every cycle checkpoints, and a first-cycle or repair rewrite can coincide with a
  checkpoint; those cycles carry both, and §8 measures that worst case. An agent's hand-edit lasts about
  a second; HELP and README say so.
- **Frame contents are keyed by tick:** if presentation cadence classes (a channel present only in
  every second frame) are implemented later, membership keys on tick or `met_s`, never on frame `seq`,
  so a resume's gap cannot shift their phase. Nothing implements them today.
- **`N mod k = 0`** stays required (agreed), which supersedes ADR J's "`k` and `N` are independent"; the
  ADR amendment says so. Checkpoints and static files both use the crossing rule, so an unaligned
  resume never skips them.

## 2. Lag, cost and missed deadlines

- **Per cycle, recorded on every tick (John):** a cycle's **start lag** = actual start − `due(a+k)` is
  known when it starts, so each of its `k` rows carries `lag_us`. Its **cost** (`cycle_us` = end −
  start, with end after publication **and** any cadence checkpoint, since the next cycle cannot start
  before that) and **end lag** (end − `due(a+k)`) are known only after its rows
  are durable, so they are **carried forward**: row 1 of each cycle carries the **previous** cycle's
  `prev_cycle_us` and `prev_end_lag_us` (0 on a segment's first cycle). The segment's last cycle's cost
  goes only in the manifest at a clean end; a crashed segment reports it as unknown. All are integers,
  clamped at ≥ 0, validated as counts by the reader.
- **Missed** = a cycle whose start lag exceeds one tick period, `dt/m`. **Overran** = a cycle whose cost
  exceeds `k·dt/m` (the completion deadline in ADR `completion.md`). Both are counted. The ADR amendment
  notes that container CPU throttling can stall up to a 100 ms quota period, so a sporadic miss is not
  necessarily overload.
- **Summary:** cycles, start-lag and cost p50/p95/p99/max (nearest-rank, over cycles; cost over the
  cycles whose cost is known), missed, overran, stalls and backstops. It is written in the segment's **manifest** (ADR C1: the clean-end event is the
  segment's manifest; the amendment states this) and printed on stop. A crashed segment's summary is
  computed by a reader from the record; a partial final cycle counts as one cycle with its rows.
- **`lag_us`, `prev_cycle_us` and `prev_end_lag_us` are wall data:** they enter the row chain (per-record integrity) but never
  `state_hash`, lineage, compare-points or any replay decision. The record format comment says so.
  Shedding (#26) must record its decisions, never re-derive them from lag.

## 3. Flags, checkpoint, resume (agreed; names are John's)

- **Flags, all `default=None`:** `--multiplier M` (`m`, positive), `--cycle-ticks K` (`k`, integer
  ≥ 1, ≤ `tick_hz / max_rate`), `--checkpoint-ticks N` (`N`, integer ≥ 1, multiple of `K`). `--poll`
  is removed. `--cycles` stays and counts cycles.
- **A serving start naming none refuses,** with the console's existing start-refusal exit code (3) and
  every missing input named. `--init`, `--plan`, `--plan-json` run no clock and need none.
- **Precedence, for each of `m`, `k`, `N` on a resume:** an explicitly named flag; else the **newest
  recovered clock policy**, i.e. the newer of the base checkpoint's `clock` and the last replayed
  segment's header (so a fall-back to an older checkpoint generation cannot silently undo a journaled
  change). It is resolved **after** replay (today `N` is picked before replay and reinstated after
  `restore_state`, `console.py:5148`, `:5205–5206`), and the bounds and `N mod k` are validated on the
  three resulting values together. A named change is journaled in the resume event's `run_inputs` (as
  `--max-batch`) and survives `restore_state`. The in-process `checkpoint_every` seam remains a test seam
  only.
- **The checkpoint** fills `clock`: `m` (as a string `"p/q"`), `k`, `N`, `burst_bound = k`,
  `lag_ceiling_s = 30` (the backstop's value, §5). Checkpoint validation covers each.
- **`check_console_flags`** resolves `CLOCK_INPUTS` (the `clock` comprehension in `capture_state`, which
  its dict-literal parser cannot read today) and maps them to the three flag dests, so the
  `None`-default rule holds them.
- **Windows:** neither `m` nor `k` is published.

## 4. The durable record — `RECORD_FORMAT` v3 (standard write-ahead logging)

- **Segment header** gains `m` (as the checkpoint's `"p/q"` string), `k`, `N`, chained and typed in
  `_header_problem`, so readers know each segment's cycle boundaries: `first_tick + i·k`. They are
  carried at all three sites that build segment entries: `_append_record`'s entry, the anchored header
  rebuild (an anchored read rebuilds the header from the checkpoint's `segments` entry, which mirrors
  them), and replay's new segment entries. `_HEADER_KEYS` and `_ROW_KEYS` are exact sets, so this is format v3.
  (A v3 engine already refuses a v2 world's checkpoint through `engine_identity`; no v2 reader needed.)
- **Row invariant, verified by the reader:** a cycle's **first** row carries `effects`, `receipts`,
  the `windows` deltas, the new `receipt` counter value and the carried-forward cost; rows 2..k carry
  `effects: []`, `receipts: []`, `windows: {}` and **repeat** the `receipt` counter value (replay reads
  it on every row); only the **last** row carries `published`. Every row carries its tick, lineage,
  `state_hash` and `lag_us`. Receipts stay on row 1, so `unwritten_results`' tick
  derivation (`row.tick − 1`) and replay's dwell stamp stay correct.
- **Write-ahead for command-bearing cycles:** when row 1's `effects`, `receipts` or `windows` is
  non-empty (so arms, spend and counter-only deltas too), it is appended and `fsync`ed **before** steps 2..k; rows 2..k follow with one `fsync`. A cycle with
  nothing to record uses one group `fsync` for all `k` rows. This keeps the window in which a claimed
  batch exists only in memory to one step, as today.
- **Readers accumulate per cycle:** `_verified_lines` and `unwritten_results` reset their receipt sets at
  a cycle's first row (from the header's `k`), not at every row, so a `results_written` note after row
  `k` acknowledges row 1's receipts. At that reset `unwritten_results` moves whatever is still pending
  into `unwritten` (never discards it), so a cycle whose publication failed stays owed. A crash after row 1 and before the notes leaves exactly that
  cycle's receipts owed.
- **Ordering unchanged:** publication follows the record's `fsync`. Recovery truncates a torn tail and
  replays to the last durable tick; a partial cycle publishes nothing.
- **Frame gap across a resume** (corrected): within a segment frames are `k` apart; across a resume the
  gap is `k′ + j` after a partial cycle of `j` rows (longer, not shorter), plus downtime. Receipt and
  frame ticks stay exact. Acceptance test 1 applies within a segment.

## 5. Stall, overload and stopping

- **Interim lag backstop (John):** the check runs at a cycle's start, **before** any handle is opened
  or console claimed, so no claimed batch is ever held. If the start lag exceeds 30 s (the ADR's
  ceiling), the executive writes the clean-end checkpoint and manifest, journals a `lag_backstop` event
  with the lag and the count of consecutive backstops, and exits with **its own code, 4** (the console
  uses 0 and 3 today; argparse 2), with a fixed-format stderr line (§7). The consecutive count is read
  back on resume from the previous segment's manifest and reset by any segment that ends otherwise. The restart policy resumes with a fresh epoch, so the
  world freezes through a stall rather than racing to catch up (ADR downtime F1). #26 replaces the
  constant with the checkpointed `lag_ceiling_s` and adds shedding and dilation. Ticks are never
  dropped (C4). Under sustained overload this is a periodic clean restart (every 30 s to about 5 min
  depending on the overrun), not a hot loop; each restart is a new segment, a new `boot_id` agents can
  see, and a replay. The §8 gate exists so that does not happen at the deployed values.
- **Without a state directory** (the per-slug shape, which has no checkpoint), the backstop cannot end
  cleanly; it rebases the epoch instead and records a `lag_backstop` event in the journal when one is
  configured (`--journal` works without a state directory), always with the fixed-format stderr line,
  so a window is never left stopped by a sibling-waiting launcher.
- **Stalls are named:** a wait that returns at least 1 s later than requested, or a start lag that jumps
  by at least `max(1 s, 10·k·dt/m)` between consecutive cycles, is journaled as a `stall` event,
  distinct from overload.
- **Suspend:** CLOCK_MONOTONIC stops during host suspend, so the world pauses with no lag. It keeps
  running through `docker pause`, SIGSTOP and VM steal; those are what the backstop bounds.
- **SIGTERM:** a handler, installed **before** recovery (so a stop during a long resume ends at the
  first boundary), sets a stop flag. The loop checks it at cycle boundaries, and the wait is
  interruptible, so a docker stop finishes the current cycle and takes the clean-end path (checkpoint
  and manifest). SIGINT behaves the same; tests that interrupt with SIGINT now assert that graceful
  completion.

## 6. Tests and acceptance

- **The scheduler is tested against an injected clock and sleeper with pacing on.** This covers
  never-ahead, waiting, catch-up by whole cycles, epoch reset at resume, lag, cost, missed, overran,
  stall and the backstop. In-process tests that are not about the scheduler build the executive at
  `k = 1` with the injected clock always on time. CLI tests use an `m` whose tick period is a few
  milliseconds, so they really wait.
- **Existing tests adapted deliberately, not assumed unchanged:** the hand-edit repair assertion
  (`test_vehicle_config.py:11337–11348`, now every `N` ticks), the interrupt harness that replaces
  `console.time` (`:29045–29062`, now the injected sleeper), the rotation test (`:21947`, now per cycle),
  the record-format literal (`:26412`), and the 90 `--poll` CLI literals.
- **New tests:**
  1. Frames exactly `k` apart and `met_s` by `k·dt` within a segment, including while catching up.
  2. A command lands at the cycle's start tick, `offset_us = 0`.
  3. A cycle never steps more than `k`. A scheduler behind runs whole cycles back to back and is never
     ahead of the clock.
  4. `lag_us` on every row and the carried-forward cost on row 1; the manifest's summary. The
     crashed-segment reader's summary equals the clean-end one over the same cycle population (the last
     cycle's cost unknown to the reader), including a partial final cycle and a resume that changes `k`.
  5. A serving start naming none of the three refuses by name, one case per missing input and per
     invalid value. `--init` and `--plan` need none.
  6. `N mod k ≠ 0` refuses, `k > tick_hz/max_rate` refuses, and out-of-bounds `k·dt/m` refuses, both at
     the CLI and in the checkpoint.
  7. A resume inherits `m`, `k`, `N`. A named change is accepted, journaled in `run_inputs`, and
     survives `restore_state`. After a fall-back to an older checkpoint generation, the newer values in
     the last replayed segment's header survive.
  8. A checkpoint ends every cycle crossing a multiple of `N`, including after an unaligned resume.
  9. A crash after rows `1..j` of a command-bearing cycle (`j` in `1..k−1`) publishes nothing, and the
     resume owes exactly row 1's receipts. Separately, a crash after the rows and before the notes.
  10. A deferral accepted in a cycle settles at the next cycle's start, with text naming that tick; after
      a crash mid-cycle and an unaligned resume (same `k`), it settles at the first boundary at or after
      its due tick.
  11. Static files are rewritten on the staggered `N` cadence, on a segment's first cycle and after a
      repair, and not every cycle.
  12. `check_console_flags` refuses a clock flag with a non-`None` default.
  13. **Live equals replay at `k = 5`:** a verb whose target keeps changing after its step. The replayed
      body's `executive` (including dwell) and `windows` equal the live checkpoint's.
  14. **Pacing stays out of the trace:** the same ingress script run unpaced and under injected slow
      cycles, with `world_id` and `boot_id` pinned. Exactly equal: every row's `tick`, `state_hash`,
      `lineage`, `effects`, `receipts`, `receipt`, `windows`, `published`, `failures`, and the checkpoint
      body's `executive` and `windows`. Excluded: the wall fields, row chains, and segments' `wall_epoch`,
      `chain` and byte `offset`.
  15. **`k`-independence:** a `k = 5` world crashes mid-cycle and resumes with `k = 1` across an `N`
      boundary; replay equals live.
  16. A `k = 5` clean cycle with verdicts reads back with its notes verified, and `unwritten_results`
      is empty. A clean resume writes no duplicate result.
  17. Arbitration with `n = 10`, `k = 5`: each window goes first exactly once in ten cycles.
  18. A compare-point refusal at step `j > 1`, on a quiet and on a write-ahead cycle (including
      `j = 2`), appends only the rows not yet durable, exits 3 naming the last durable tick, and the
      batch is answered on resume.
  19. SIGTERM during a command-bearing cycle: the cycle completes, a clean end follows, and the batch is
      answered.
  20. The backstop: an injected stall beyond 30 s ends cleanly with `lag_backstop` and exit 4, and
      resumes with a fresh epoch; without a state directory it rebases instead. A shorter stall is
      journaled as `stall`.
  21. The telemetry ring at 3,000 slots: prune, `held` and `losses` stay correct without a per-cycle
      directory scan, including after an agent deletes frames (reconciled within `N` ticks), after an
      agent replaces `telemetry/` (identity change), and after a repair; ordinary cycles do not rescan.
- **`tools/measure_clock.py`:** add p99, the `k`-tick cycle with option B's take barriers and the
  write-ahead `fsync`, a full 3,000-slot ring, the static rewrite (alone and coinciding with a
  checkpoint), ten windows, and a worst-cycle report. Fix its `checkpoint_shaped` clock keys
  (`CLOCK_INPUTS`) and its row builder (v3).

## 7. The chassis interface delta (vehicle specifies; chassis implements; Governance sequences)

Per AUR-GOV-04's row for #23 (`governance/chassis/records/2026-10-10-aur-gov-04-interface-report.md:112`).

- **Values named explicitly:** the generated compose sets `VEHICLE_MULTIPLIER=1`,
  `VEHICLE_CYCLE_TICKS=5`, `VEHICLE_CHECKPOINT_TICKS=50`, with no `:?` interpolation, so `compose
  config` and agent-only `up`s keep working. The launch script passes each flag only when its variable
  is set (`${VEHICLE_MULTIPLIER:+--multiplier "$VEHICLE_MULTIPLIER"}`), so a resume can inherit. It
  reaches the console's refusal by name, not a shell `set -u` abort. `--cycles 0` stays.
- **Telemetry history (John): about 5 minutes,** `VEHICLE_RING_SLOTS = 3000` at 10 frames/s. Ring size
  is world identity, so it is set before the first deploy of #23.
- **The ring at that size (vehicle):** the held-frame list is a **persistent cache on the `Window`**,
  independent of handle lifetime: handles keep their secure per-cycle open and close. Today
  `ring_frames()` scans the whole `telemetry/` directory four
  times per window per cycle (prune, `held`, `losses`, `pending.json`), about 120,000 entries per cycle
  at 3,000 slots and ten windows. The held-frame list moves into memory: one scan when the handle opens
  (boot, repair), then push and prune by name per frame, `held` and `losses` computed once per
  publication from it. A full scan happens only at boot, after a `repair`, on a reconcile every `N`
  ticks (so an agent's deletions show within a second), and when the opened `telemetry/` directory's
  identity (`st_dev`, `st_ino`) differs from the previous cycle's (an agent replaced the directory).
  `open_handles` runs every cycle, so "when the handle opens" is **not** a scan trigger.
- **Storage:** about 3,000 frame files per window (≈ 33,000 files across ten windows plus ring
  overhead) in the shared `diode` image (2 GB default, which also holds every agent's `output/`); §8
  measures the frame size and the share of the image before the first deploy.
- **SIGTERM reaches the console:** in the `exec` (one-executive) shape directly, where the console is
  PID 1 and only the §5 handler makes SIGTERM effective at all. The per-slug script's trap must forward
  it **and wait** for the consoles (`trap 'kill $PIDS 2>/dev/null || true; wait' TERM INT`); otherwise
  the shell, as PID 1, exits and the kernel kills the consoles mid-cycle.
- **Operator visibility of backstops (chassis):** the backstop prints a fixed-format stderr line in both
  shapes, `[console] lag_backstop lag_s=<n> consecutive=<n>`, kept by `docker compose logs vehicle`.
  `scripts/status.py` and `scripts/journal.py` gain the `vehicle` service: its restart count and that
  line. Until that lands, the chassis cannot tell a backstop from a fault; exit 4 alone is not relied on
  (docker's state after an automatic restart may not show it).
- **Touch points (chassis-owned):**
  - `containers/serve_vehicle.sh`, on both the `aurora-port` and `vehicle-adoption` shapes. The
    one-executive `vehicle-adoption` shape is the target; the per-slug shape has no state directory,
    so it gets the cadence but no record, lag rows or checkpoint.
  - `scripts/build_compose.py` and the generated `docker-compose.yml`.
  - `.env.example`.
  - `tests/test_vehicle_reconciliation.py` (`:206–212`, `:571–573`, `:610`/`:622–623`).
  - `governance/chassis/interface.md:23`, `governance/vehicle/interface.md:33`, and
    `vehicle-adoption`'s `README.md:225–234`.
- **`DIODE_POLL_SECONDS`** stays for `contract/fake_diode.py`, the fixture's own cadence.
- **The probe:** `contract/diode_probe.py` separates the nominal cadence (`k·dt/m`, 100 ms) from its
  observation deadlines, which stay around 1 s, because legitimate lag can exceed 150–200 ms.
- **Adoption carries an operator step:** any vehicle bump changes `engine_identity`, so the existing
  `/state` checkpoint is refused and must be cleared (a new world), as on every bump.
- **Order:** the vehicle merges first. The chassis adopts the pin, this delta and the image rebuild
  together. A new image with the old compose restart-loops by design; the old image with the new
  compose falls back to `DIODE_POLL_SECONDS` and works. Before any gate, check `git submodule status`:
  the chassis's vehicle checkout (`8c6f71d`) is ahead of its pin (`dd79e76`).

## 8. Feasibility before deployment values are fixed

The ADR's cost figures (about 76 ms p50 and 90 ms p95 per 100 ms cycle with ten windows, plus about
9 ms on a checkpoint cycle) predate option B, which adds up to three directory or file `fsync`s per
window with a non-empty console. Before the chassis adopts `m = 1`, `k = 5`, 3,000 ring slots for ten windows, run `measure_clock` (§6:
take barriers, write-ahead `fsync`, full ring, static and checkpoint together) on the deployment's
volume images, under a Governance slot, and record the frame size and the ring's share of the diode
image. If the worst cycle does not fit `k·dt/m` with margin, `k`, the window count or the ring size is
revisited with John, not silently dilated.

## 9. Delivery

- One branch from vehicle `main` after #39 option B merges; focused commits per CONTRIBUTING; a README
  round entry; an ADR 0002 amendment recording §§1–5, including the superseded "`k` and `N`
  independent", the manifest location, causality, and the format v3.
- Shared-slot needs, by Governance grant only: the `measure_clock` run (§8), bounded selections of the
  new and touched tests, then the full two-lane gate (G-2 shape).
- This revision goes to confirmation review (the same reviewers) before any code; an implementation
  review follows.

## 10. Review r1 findings and their resolutions

| finding | reviewer(s) | resolution |
|---|---|---|
| Group commit breaks the note/receipt binding: resume refuses its record; `unwritten_results` re-owes everything and can duplicate results | Codex P1, determinism P1-A, systems P1-1 | §4: row-1 invariant, per-cycle accumulation, `m`/`k`/`N` in the header, format v3; tests 9, 16 |
| Dwell computed after `k` steps diverges live from replay | determinism P1-B | §1 stepping rule; test 13 |
| Arbitration rotation collapses when `gcd(n, k) > 1` | systems P1-2, determinism P2-D | §1 rotation by cycle; test 17 |
| Overload and stalls unbounded until #26 | simulation P1-1 | §5 interim backstop (John) and named stalls; test 20 |
| Claimed batch held in memory for `k` steps | simulation P2-1 | §4 write-ahead row 1 on command-bearing cycles |
| A refusal partway through a cycle is unspecified | determinism P2-A, systems P2-1 | §1; test 18 |
| SIGTERM mid-cycle loses the batch; no clean end in docker | systems P2-2 | §5 handler; test 19 |
| Lag hides cycle cost | simulation P2-2 | §2 `cycle_us`, end lag, overran count |
| Causality and backdating not stated | simulation P2-3 | §1 causality paragraph |
| Frame gap across a resume misstated | simulation P2-4, Codex P2, determinism P3, systems P3 | §4 corrected; test 1 scoped to a segment |
| `lag_us` and hash rules | simulation P2-5, determinism P2-B | §2: integers, clamped, chain only; test 14 |
| Static rewrite shares a cycle with the checkpoint | simulation P2-6 | §1 staggered; measured (§6) |
| Crashed-segment summary lacks data; manifest location | Codex P2, determinism P3 | §2 and §4: header inputs, nearest-rank, partial cycles, manifest |
| `k` could break ADR B's publication rates; ADR J independence superseded | Codex P2 | §1 bound and amendment; test 6 |
| `k = 1` does not preserve every existing test; the seam cannot test never-ahead | Codex P2, systems P2-4 | §6 injected clock and the listed adaptations |
| Probe timing cannot become 100 ms | Codex P2, systems P3 | §7 cadence separated from deadlines |
| Rollout unspecified: values, inheritance, old checkpoints, target shape, ring depth | systems P2-3 | §7 (ring depth: John) |
| Feasibility unmeasured under option B | systems P2-4 | §8 |
| Pacing not proven out of the trace; `k`-independence | determinism P2-C | tests 14, 15 |
| Integer due times, epoch placement, sleep loop, input bounds | simulation P3-1, systems P3 | §1 |
| Deferral due tick | simulation P3-2, determinism P3, systems P3 | §1; test 10 |
| Static-file crossing rule, repair, first cycle | determinism P3, systems P3 | §1; test 11 |
| `N` precedence; refusal exit code | systems P3 | §3 |
| Docs touch points; submodule drift | Codex P3, systems P3 | §7 |
| `check_console_flags` cannot parse the `clock` comprehension | Codex buildability note | §3 |

## 11. Review r2 findings and their resolutions

| finding | reviewer(s) | resolution |
|---|---|---|
| A cycle's cost cannot be in rows written before it ends | Codex P1, determinism P2, simulation P2-A, systems N2 | §2: carried forward on the next cycle's row 1; last cycle's cost in the manifest; test 4 |
| Ring scans at 3,000 slots likely exceed the cycle budget; storage unstated | systems N1 (P1), simulation P2-B, systems N5 | §7: in-memory held list, reconciled every `N`; storage stated; §8 measures; test 21 |
| Refusal path would re-append durable row 1; failed suffix append | Codex P2, determinism P3-4, systems wording | §1: only the non-durable suffix; last durable tick named; test 18 |
| Deferral promise across an unaligned resume | Codex P2, systems note | §1 "first boundary at or after"; text; test 10 |
| Static/checkpoint separation impossible for `N = k`, first cycle, repair | Codex P2, systems N6, simulation P2-6 note | §1 exceptions stated; §8 measures the coincidence |
| Per-slug shape: backstop stops a window for good | systems N3 | §5 rebase without a state directory |
| Backstop shares exit 3 with faults; consecutive count | simulation P3-1, systems N4 | §5 exit 4 and the count |
| Stall constants; wait cap; handler before recovery | simulation P3-2, systems N6 | §1, §5 |
| `m` parsed through a float | simulation P3-3 | §1 decimal string |
| Rotation wording after an unaligned resume | simulation P3-4, systems | §1 |
| SIGTERM must reach the console | simulation P3-5 | §7 |
| Queue-age figure | simulation P3-6 | §1: 5 s, `domains/propulsion/commands.yaml` |
| Cadence classes must key on tick | simulation P2-4 note | §1 |
| Backstop check before the claim | determinism P3-1 | §5 |
| Test 14 comparison scope | determinism P3-2, Codex P3 | §6 test 14 |
| Header encoding and its three propagation sites | determinism P3-3 | §4 |
| Write-ahead trigger includes `windows` deltas | determinism P3-4 | §4 |
| Inheritance after a fall-back | determinism P3-5 | §3 newest of checkpoint and last header |
| Rows 2..k repeat the receipt counter | Codex P3 | §4 |
| Pending moved, not discarded, at the reset | systems note | §4 |
| SIGINT tests assert graceful completion | Codex note | §5 |
| §8 omits the write-ahead `fsync` | systems N7 | §6, §8 |

## 12. Review r3 (targeted) findings and their resolutions

| finding | reviewer | resolution |
|---|---|---|
| "One scan when the handle opens" is per cycle, since handles open every cycle | systems R1 | §7: scan triggers are boot, repair, reconcile every `N`, directory identity change; test 21 |
| No chassis surface can see exit 4 or `lag_backstop` | systems R2 | §5 and §7: fixed-format stderr line; `status.py`/`journal.py` gain the vehicle service |
| Per-slug trap exits before the consoles finish | systems R3 | §7: the trap forwards and waits |
| Cycle end must include the cadence checkpoint | systems P3 | §2 |
| Where the consecutive-backstop count persists | systems P3 | §5: previous segment's manifest || `N` inheritance contradictory; resolve after replay | Codex P2 (r3) | §3 precedence; test 7 |
| Ring cache must not be tied to handle lifetime | Codex P2 (r3) | §7 persistent `Window` cache; test 21 |
| No state directory ≠ no journal | Codex P3 (r3) | §5 journal when configured, stderr always |

**Design status:** r3 targeted confirmations — systems approve with changes, Codex approve with changes
— all changes folded in above. Simulation and determinism approved r2 with changes, folded in r3. No
open design finding. Next: implementation (§9), which needs a Governance slot for every test run.

