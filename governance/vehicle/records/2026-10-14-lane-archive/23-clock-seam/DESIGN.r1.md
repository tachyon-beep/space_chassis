# #23 WP08.5 — the clock seam: design (hardening)

Vehicle line, 2026-10-12. Basis: ADR 0002 (A2, B2, J2, G, C1, Consequences) and the read-only mapping
`MAPPING.md` (vehicle HEAD `7a87eb8`). Design only: no code, no tests, no slot. Sections are agreed
with John one at a time, then the whole goes to independent design review before implementation.

## 1. The clock and the cycle — AGREED with John 2026-10-12

- **Accepted values (ADR):** `m = 1`, `k = 5`, `N = tick_hz = 50`, burst = `k` (whole cycles back to
  back, no partial bursts), lag ceiling 30 s (child 8's trigger, not this child's). All three of
  `m`, `k`, `N` are required with no default; the values are what the deployed stack names.
- **Epoch per segment.** Each start or resume reads a monotonic clock `E` at its first tick `t0`;
  tick `t` is due at `E + (t − t0)·dt/m`. A resume is never "hours behind". The existing UTC
  `wall_epoch` stays as the human-readable stamp.
- **Never ahead (John's choice).** A cycle covering ticks `a+1 … a+k` starts at
  `max(due(a+k), end of the previous cycle)`. The published world is never ahead of the mission
  clock; a scheduler that is behind runs whole cycles back to back until it is not.
- **One claim and one publication per cycle.** Each cycle claims every console once, stamps accepted
  effects at `offset_us = 0` of the cycle's first tick (receipt tick = the cycle's start tick, as
  today), steps `k` ticks (the remaining `k − 1` carry no effects) and publishes once. Frames are
  exactly `k` ticks apart; `met_s` differs by `k·dt`.
- **Deferrals settle at cycle starts.** A deferral due mid-cycle settles at the next cycle's start,
  up to `k − 1` ticks late (consistent with "the remaining `k − 1` carry no effects").
- **`N` must be a multiple of `k`;** a start or resume naming otherwise refuses (otherwise a
  `tick % N` checkpoint can be skipped).
- **Static `HELP.md` / `README.md` every `N` ticks (John's choice),** with the checkpoint cadence:
  once a second at `m = 1`, `N = 50`. An agent's hand-edit lasts until the next rewrite.
- **Tests** get an in-process "don't pace" seam (like `checkpoint_every`), never a CLI flag; the live
  policy never runs unpaced.

## 2. Lag and missed deadlines — AGREED with John 2026-10-12

- **Lag is per cycle, recorded on every tick.** A cycle's lag = its actual start − `due` of its last
  tick. Each of its `k` ticks records that lag; the record says they were stepped together. Per-tick
  measurement would build in structural lag (a cycle's first tick waits for its last by design).
- **A missed deadline** is a cycle whose start lag exceeds one tick period, `dt/m` (20 ms at `m = 1`),
  which absorbs ordinary sleep jitter.
- **Where it lives:**
  - every tick row in the durable record carries `lag_us` (ADR C1);
  - the segment's summary — cycles, lag p50/p95/p99/max, missed count — goes in the clean-end event
    and is printed on stop;
  - a small reader computes the same summary from the record for a segment that crashed.
- **Not this child:** shedding, the 30 s lag ceiling, hold and pause (#26, #27).

## 3. Flags, checkpoint, resume — AGREED with John 2026-10-12 (descriptive names chosen)

- **Flags, all `default=None`:** `--multiplier M` (`m`, positive finite; `1` = real time),
  `--cycle-ticks K` (`k`, integer ≥ 1), `--checkpoint-ticks N` (`N`, integer ≥ 1, a multiple of `K`).
  `--poll` is removed; `--cycles` stays and counts cycles.
- **A serving start naming none refuses,** listing the missing run inputs by name. `--init`, `--plan`
  and `--plan-json` run no clock and need none of them.
- **A resume inherits** `m`, `k`, `N` from the checkpoint; a named different value is accepted and
  journaled in the resume event's `run_inputs`, as `--max-batch` is today. `N mod k = 0` is checked on
  the resulting values.
- **The checkpoint** fills its `clock` slots: `m`, `k`, `N`, `burst_bound = k`; `lag_ceiling_s`
  stays null until #26. Checkpoint validation covers them.
- **Checkpoint cadence:** at the end of any cycle that **crosses** a multiple of `N` (a resume can start
  at any tick, so "tick is a multiple of `N`" could be skipped).
- **`check_console_flags`** reads the checkpoint's `clock` section as well as `run`, with a dest
  mapping, so the three flags are held to the `None`-default rule.
- **Windows:** neither `m` nor `k` is published (ADR: `m` is not); agents see ticks and `met_s`.

## 4. The durable record — proposed

## 4. The durable record — DECIDED (standard write-ahead-log group commit)

- A cycle appends its `k` tick rows and makes them durable with **one** `fsync` (group commit; ADR
  J(i) anticipates it). The first row carries the cycle's accepted effects; every row carries its tick,
  lineage and the cycle's `lag_us`; only the last carries the windows' `published` marks.
- Publication follows the `fsync` (unchanged ordering), so a crash mid-cycle publishes nothing from it.
  Recovery truncates a torn tail and replays to the last durable tick, as now; the resumed segment's
  cycles start there. Rows 2..k carry no effects, so stopping between them loses nothing an agent sent.
- Replay's completeness check becomes one row per tick (identical to today's when `k = 1`).
- Frame spacing is exactly `k` within a segment; across a resume one shorter gap can appear. Receipt and
  frame ticks stay exact.

## 5. The chassis interface delta — DECIDED (vehicle specifies, chassis implements; Governance sequences)

Per `governance/chassis/records/2026-10-10-aur-gov-04-interface-report.md:112`.
- The vehicle service stops passing `--poll "$DIODE_POLL_SECONDS"` and passes `--multiplier`,
  `--cycle-ticks`, `--checkpoint-ticks` from three required environment variables
  (`VEHICLE_MULTIPLIER`, `VEHICLE_CYCLE_TICKS`, `VEHICLE_CHECKPOINT_TICKS`; deployed values 1, 5, 50).
  A stack naming none refuses to start, by design (ADR cross-repo item 3). `--cycles 0` stays.
- Touch points (chassis-owned): `containers/serve_vehicle.sh`, `scripts/build_compose.py` (and the
  generated `docker-compose.yml`), `.env.example`, `tests/test_vehicle_reconciliation.py` (three pins).
- `DIODE_POLL_SECONDS` stays for `contract/fake_diode.py`, which is the chassis fixture's own cadence.
- `contract/diode_probe.py --poll-seconds` (default 5) should reflect the vehicle's cycle (100 ms at the
  deployed values); the probe's timing expectations are the chassis's to adjust.
- Order: the vehicle merges first; the chassis adopts the pin and this delta together in its own
  increment. Until then the chassis's pinned vehicle keeps `--poll`.

## 6. Tests and acceptance — DECIDED

- **Existing tests keep their meaning.** In-process tests build the executive with `k = 1` and the
  "don't pace" seam, so their one-cycle-one-tick assertions stay true. CLI tests replace `--poll 0`
  with `--multiplier 1000 --cycle-ticks 1 --checkpoint-ticks 50`: genuinely paced, fast.
- **New tests, one per acceptance property (issue #23, ADR child 5 row):**
  1. frames exactly `k` ticks apart and `met_s` differs by `k·dt`, including while catching up;
  2. a command lands at the cycle's start tick, `offset_us = 0`, within `k` ticks;
  3. a cycle never steps more than `k` ticks; a scheduler behind runs whole cycles back to back
     (an injected slow cycle via the seam), never ahead of the clock;
  4. lag recorded on every row; the segment summary's p50/p95/p99/max and missed count; the reader's
     summary for a crashed segment equals the clean-end one;
  5. a serving start naming none of the three refuses by name; `--init`/`--plan` do not need them;
  6. `N mod k ≠ 0` refuses;
  7. a resume inherits `m`, `k`, `N`; a named change is accepted and journaled in `run_inputs`;
  8. a checkpoint at the end of every cycle crossing a multiple of `N`, including after a resume at an
     unaligned tick;
  9. a crash after some of a cycle's rows are durable publishes nothing and resumes at the last
     durable tick;
  10. a deferral due mid-cycle settles at the next cycle's start;
  11. static files rewritten every `N` ticks, not every cycle;
  12. `check_console_flags` refuses a clock flag with a non-`None` default.
- `tools/measure_clock.py` gains `p99` and the `k`-tick cycle cost, and its `checkpoint_shaped` clock
  keys are corrected to `CLOCK_INPUTS`.

## 7. Delivery

- One branch from vehicle `main` after #39 option B merges (so the claim code is the published one);
  focused commits per CONTRIBUTING; README round entry; ADR 0002 amendment recording sections 1–4.
- Shared-slot needs (by Governance grant only): bounded selections of the new and touched tests, then
  the full two-lane gate (G-2 shape).
- Independent design review before any code; implementation review after.
