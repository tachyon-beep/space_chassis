# #23 WP08.5 — the clock seam: design, revision 2 (hardening)

Vehicle line, 2026-10-12. Basis: ADR 0002 (A2, B2, C1, G, J, Consequences), ADR 0001 (choice A), the
read-only mapping `MAPPING.md` (vehicle HEAD `7a87eb8`), and four independent design reviews of
revision 1 (`DESIGN.r1.md`, sha256 `89389a4c…`), in `reviews/`: simulation (approve with changes),
Codex of record (request changes), determinism and replay (request changes), systems (request
changes). §10 maps every finding to its resolution. Design only: no code, no tests, no slot.

**John's decisions:** cycles never run ahead (§1); static files every `N` ticks (§1); lag per cycle
(§2); descriptive flag names (§3); an interim lag backstop until #26 (§5); about 5 minutes of
telemetry history, 3,000 frames (§7). Everything else follows a named standard or the ADR.

## 1. The clock and the cycle

- **Accepted values (ADR):** `m = 1`, `k = 5`, `N = tick_hz = 50`, burst = `k` (whole cycles back to
  back), lag ceiling 30 s. `m`, `k`, `N` are required with no default; the deployed stack names them.
- **Clock:** `time.monotonic_ns()` (CLOCK_MONOTONIC). All due-time arithmetic is integer nanoseconds:
  `m` is held as a `fractions.Fraction`, and `due_ns(t) = E_ns + (t − t0)·dt_ns/m` is evaluated per
  cycle from the epoch (absolute, so no drift accumulates) and rounded once.
- **Epoch per segment:** `E` is read after the start's or resume's recovery and pre-serve checkpoint,
  immediately before the first wait, so recovery time never counts as lag. `t0` is the segment's
  first tick; its first cycle covers `t0+1 … t0+k`.
- **Never ahead (John):** a cycle covering `a+1 … a+k` starts at `max(due(a+k), end of the previous
  cycle)`. The wait is a loop (`while now < due: sleep(min(due − now, cap))`) so early wake-ups and
  signals are handled; the cap keeps SIGTERM responsive.
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
  step `j > 1`, the `j − 1` completed rows are appended with one `fsync` (row 1 carries the cycle's
  receipts, so they are owed and answered on resume), nothing past them is committed to `tick`,
  `truth` or `lineage`, and the run stops with exit 3, naming the last recorded tick. A refusal at step
  1 records nothing, as today.
- **Deferrals:** a deferral accepted in a cycle is due at the **next cycle's start**, `a + k`, and its
  result text says so. (Today's `due = tick + 1` would fall mid-cycle and settle at `a + k` anyway, with
  text naming a tick that is never honoured.) Expiry stays in simulated seconds; the smallest
  `maximum_queue_age_s` in the corpus is 10 s against 0.1 s.
- **Arbitration (ADR 0001 choice A):** the window order rotates by **cycle**, `(a // k) % n`, not by
  tick. That gives each window the first place once per `n` cycles whatever `gcd(n, k)`, keeps
  advancing by one after an unaligned resume, and equals today's `tick % n` at `k = 1`.
- **Static `HELP.md` / `README.md` (John: every `N` ticks):** rewritten at the end of any cycle that
  crosses a multiple of `N`, **staggered one cycle after the checkpoint's** so the two costs never share
  a cycle; also on a segment's first cycle and the cycle after a `repair`. An agent's hand-edit lasts
  about a second; HELP and README say so.
- **`N mod k = 0`** stays required (agreed), which supersedes ADR J's "`k` and `N` are independent"; the
  ADR amendment says so. Checkpoints and static files both use the crossing rule, so an unaligned
  resume never skips them.

## 2. Lag, cost and missed deadlines

- **Per cycle, recorded on every tick (John):** the cycle's **start lag** = actual start − `due(a+k)`,
  its **cost** `cycle_us` = end − start, and its **end lag** = end − `due(a+k)`. Each of its `k` rows
  carries `lag_us` (start lag) and `cycle_us`; integers, clamped at ≥ 0, validated as counts by the
  reader.
- **Missed** = a cycle whose start lag exceeds one tick period, `dt/m`. **Overran** = a cycle whose cost
  exceeds `k·dt/m` (the completion deadline in ADR `completion.md`). Both are counted. The ADR amendment
  notes that container CPU throttling can stall up to a 100 ms quota period, so a sporadic miss is not
  necessarily overload.
- **Summary:** cycles, start-lag and cost p50/p95/p99/max (nearest-rank, over cycles), missed, overran,
  stalls and backstops. It is written in the segment's **manifest** (ADR C1: the clean-end event is the
  segment's manifest; the amendment states this) and printed on stop. A crashed segment's summary is
  computed by a reader from the record; a partial final cycle counts as one cycle with its rows.
- **`lag_us` and `cycle_us` are wall data:** they enter the row chain (per-record integrity) but never
  `state_hash`, lineage, compare-points or any replay decision. The record format comment says so.
  Shedding (#26) must record its decisions, never re-derive them from lag.

## 3. Flags, checkpoint, resume (agreed; names are John's)

- **Flags, all `default=None`:** `--multiplier M` (`m`, positive), `--cycle-ticks K` (`k`, integer
  ≥ 1, ≤ `tick_hz / max_rate`), `--checkpoint-ticks N` (`N`, integer ≥ 1, multiple of `K`). `--poll`
  is removed. `--cycles` stays and counts cycles.
- **A serving start naming none refuses,** with the console's existing start-refusal exit code and every
  missing input named. `--init`, `--plan`, `--plan-json` run no clock and need none.
- **A resume inherits** `m`, `k`, `N` from the checkpoint; a named different value is accepted and
  journaled in the resume event's `run_inputs` (as `--max-batch`), and survives `restore_state`
  replacing `executive.clock`. The bounds and `N mod k` are checked on the resulting values.
- **Precedence for `N`:** a named flag, else the checkpoint's; the in-process `checkpoint_every` seam
  remains a test seam only and is overridden by neither in production paths.
- **The checkpoint** fills `clock`: `m` (as a string `"p/q"`), `k`, `N`, `burst_bound = k`,
  `lag_ceiling_s = 30` (the backstop's value, §5). Checkpoint validation covers each.
- **`check_console_flags`** resolves `CLOCK_INPUTS` (the `clock` comprehension in `capture_state`, which
  its dict-literal parser cannot read today) and maps them to the three flag dests, so the
  `None`-default rule holds them.
- **Windows:** neither `m` nor `k` is published.

## 4. The durable record — `RECORD_FORMAT` v3 (standard write-ahead logging)

- **Segment header** gains `m`, `k`, `N` (chained), so readers know each segment's cycle boundaries:
  `first_tick + i·k`. The checkpoint's `segments` entries mirror them, since an anchored read rebuilds
  the header from that entry. `_HEADER_KEYS` and `_ROW_KEYS` are exact sets, so this is format v3.
  (A v3 engine already refuses a v2 world's checkpoint through `engine_identity`; no v2 reader needed.)
- **Row invariant, verified by the reader:** a cycle's **first** row carries `effects`, `receipts`,
  the `windows` deltas and the new `receipt` counter; rows 2..k carry none of them (`effects: []`,
  `receipts: []`, `windows: {}`); only the **last** row carries `published`. Every row carries its tick,
  lineage, `state_hash`, `lag_us` and `cycle_us`. Receipts stay on row 1, so `unwritten_results`' tick
  derivation (`row.tick − 1`) and replay's dwell stamp stay correct.
- **Write-ahead for command-bearing cycles:** when row 1 carries effects, receipts or deferral deltas,
  it is appended and `fsync`ed **before** steps 2..k; rows 2..k follow with one `fsync`. A cycle with
  nothing to record uses one group `fsync` for all `k` rows. This keeps the window in which a claimed
  batch exists only in memory to one step, as today.
- **Readers accumulate per cycle:** `_verified_lines` and `unwritten_results` reset their receipt sets at
  a cycle's first row (from the header's `k`), not at every row, so a `results_written` note after row
  `k` acknowledges row 1's receipts. A crash after row 1 and before the notes leaves exactly that
  cycle's receipts owed.
- **Ordering unchanged:** publication follows the record's `fsync`. Recovery truncates a torn tail and
  replays to the last durable tick; a partial cycle publishes nothing.
- **Frame gap across a resume** (corrected): within a segment frames are `k` apart; across a resume the
  gap is `k′ + j` after a partial cycle of `j` rows (longer, not shorter), plus downtime. Receipt and
  frame ticks stay exact. Acceptance test 1 applies within a segment.

## 5. Stall, overload and stopping

- **Interim lag backstop (John):** if a cycle's start lag exceeds 30 s (the ADR's ceiling), the
  executive finishes nothing further: it writes the clean-end checkpoint and manifest, journals a
  `lag_backstop` event with the lag, and exits 3. The restart policy resumes with a fresh epoch, so the
  world freezes through a stall rather than racing to catch up (ADR downtime F1). #26 replaces the
  constant with the checkpointed `lag_ceiling_s` and adds shedding and dilation. Ticks are never
  dropped (C4).
- **Stalls are named:** a wait that returns far later than requested, or a gap far larger than any
  cycle's cost, is journaled as a `stall` event, distinct from overload.
- **Suspend:** CLOCK_MONOTONIC stops during host suspend, so the world pauses with no lag. It keeps
  running through `docker pause`, SIGSTOP and VM steal; those are what the backstop bounds.
- **SIGTERM:** a handler sets a stop flag. The loop checks it at cycle boundaries, and the wait is
  interruptible, so a docker stop finishes the current cycle and takes the clean-end path (checkpoint
  and manifest). SIGINT behaves the same.

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
  4. `lag_us` and `cycle_us` on every row, and the manifest's summary. The crashed-segment reader's
     summary equals the clean-end one, including a partial final cycle and a resume that changes `k`.
  5. A serving start naming none of the three refuses by name, one case per missing input and per
     invalid value. `--init` and `--plan` need none.
  6. `N mod k ≠ 0` refuses, `k > tick_hz/max_rate` refuses, and out-of-bounds `k·dt/m` refuses, both at
     the CLI and in the checkpoint.
  7. A resume inherits `m`, `k`, `N`. A named change is accepted, journaled in `run_inputs`, and
     survives `restore_state`.
  8. A checkpoint ends every cycle crossing a multiple of `N`, including after an unaligned resume.
  9. A crash after rows `1..j` of a command-bearing cycle (`j` in `1..k−1`) publishes nothing, and the
     resume owes exactly row 1's receipts. Separately, a crash after the rows and before the notes.
  10. A deferral accepted in a cycle settles at the next cycle's start, with text naming that tick.
  11. Static files are rewritten on the staggered `N` cadence, on a segment's first cycle and after a
      repair, and not every cycle.
  12. `check_console_flags` refuses a clock flag with a non-`None` default.
  13. **Live equals replay at `k = 5`:** a verb whose target keeps changing after its step. The replayed
      body's `executive` (including dwell) and `windows` equal the live checkpoint's.
  14. **Pacing stays out of the trace:** the same ingress script run unpaced and under injected slow
      cycles. Rows are identical apart from `lag_us` and `cycle_us`; checkpoint bodies are identical
      apart from wall stamps and chains.
  15. **`k`-independence:** a `k = 5` world crashes mid-cycle and resumes with `k = 1` across an `N`
      boundary; replay equals live.
  16. A `k = 5` clean cycle with verdicts reads back with its notes verified, and `unwritten_results`
      is empty. A clean resume writes no duplicate result.
  17. Arbitration with `n = 10`, `k = 5`: each window goes first exactly once in ten cycles.
  18. A compare-point refusal at step `j > 1` records `j − 1` rows, exits 3 naming the last recorded
      tick, and the batch is answered on resume.
  19. SIGTERM during a command-bearing cycle: the cycle completes, a clean end follows, and the batch is
      answered.
  20. The backstop: an injected stall beyond 30 s ends cleanly with `lag_backstop` and resumes with a
      fresh epoch. A shorter stall is journaled as `stall`.
- **`tools/measure_clock.py`:** add p99, the `k`-tick cycle with option B's take barriers, the
  staggered static rewrite, and a worst-cycle report. Fix its `checkpoint_shaped` clock keys
  (`CLOCK_INPUTS`) and its row builder (v3).

## 7. The chassis interface delta (vehicle specifies; chassis implements; Governance sequences)

Per AUR-GOV-04's row for #23 (`governance/chassis/records/2026-10-10-aur-gov-04-interface-report.md:112`).

- **Values named explicitly:** the generated compose sets `VEHICLE_MULTIPLIER=1`,
  `VEHICLE_CYCLE_TICKS=5`, `VEHICLE_CHECKPOINT_TICKS=50`, with no `:?` interpolation, so `compose
  config` and agent-only `up`s keep working. The launch script passes each flag only when its variable
  is set (`${VEHICLE_MULTIPLIER:+--multiplier "$VEHICLE_MULTIPLIER"}`), so a resume can inherit. It
  reaches the console's refusal by name, not a shell `set -u` abort. `--cycles 0` stays.
- **Telemetry history (John): about 5 minutes,** `VEHICLE_RING_SLOTS = 3000` at 10 frames/s. Ring size
  is world identity, so it is set before the first deploy of #23. (Implementation checks the console's
  ring-size bound and the per-window storage.)
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
window with a non-empty console. Before the chassis adopts `m = 1`, `k = 5` for ten windows, run
`measure_clock` (§6) on the deployment's volume images, under a Governance slot. If the worst cycle
does not fit `k·dt/m` with margin, `k` or the window count is revisited with John, not silently
dilated.

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
