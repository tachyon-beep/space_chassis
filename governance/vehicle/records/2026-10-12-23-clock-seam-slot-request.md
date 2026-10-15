# #23 WP08.5 clock seam: design settled, implementation started, two allocation requests (vehicle, 2026-10-12)

Owner: Space Vehicle Claude Code `session_01GRfs7dVMu4v5airK6q3w9C`, the sole Vehicle writer. Written for
Governance's coordination of the one shared Space test slot. **Kind of work: hardening** (WP08, M1,
continuity). John directed on 2026-10-12: keep pushing the continuity milestone, start #23's
implementation, and request these allocations.

**Nothing here is requested ahead of #39.** #39's G-2 sequence (G312s → G312p → G313s → G313p, per MASTER
§37) keeps priority. Both requests below are for slots after it, or between its stages only if
Governance judges that harmless. ELSPETH priority, Sultai's GPU reservation, one Space selection, at most
two workers, nice 19 and no GPU all stand.

## The design (settled; no execution)

- `.scratch/wp08-23/DESIGN.md`, sha256 `4e8d0d6aaeb83319a120586fe086cd7744f0171a9f291f6b7cdb4b2dcc2787af`.
- Three rounds of four independent design reviews (simulation, determinism and replay, systems, Codex):
  `.scratch/wp08-23/reviews/`. Every finding is mapped to its resolution in §§10–12. No design finding is
  open.
- John's choices: cycles never run ahead of the mission clock; static HELP/README every `N` ticks; lag per
  cycle; flags `--multiplier`, `--cycle-ticks`, `--checkpoint-ticks` (required, no default; `--poll`
  retired); an interim 30 s lag backstop (clean end, exit 4) until #26; 3,000 telemetry ring slots
  (about 5 minutes at 10 frames/s).
- It changes the chassis interface (§7, vehicle specifies, chassis implements, Governance sequences):
  three required values named in the generated compose, `--poll`/`DIODE_POLL_SECONDS` retired for the
  vehicle service only, the probe's deadlines separated from the cadence, `status.py`/`journal.py` gain
  the vehicle service's backstop line. Nothing is asked of the chassis until the vehicle merges.

## Implementation (started; no execution)

On a new branch `codex/23-clock-seam` from the local, unqualified option B commit
`7a87eb82cfef55dcc74248df41720883587ca7af`, in its own worktree under the session scratchpad. Tests are
written first. Until an allocation exists, the only checks are static (syntax compilation and ruff on
the changed files); no test, collection, or console execution runs, and nothing is committed.

## Request 1 — iterative bounded selections for #23 (development)

- **Purpose:** see each new test fail before its fix and pass after, per the vehicle practice; then
  confirm the touched existing tests.
- **Shape:** the v7 supervisor (K-qualified), as for S1: Python 3.12, `-n 2 --max-worker-restart=0`,
  nice 19, 2 CPUs, 6 GiB, no swap, no GPU; one named selection per run (the new #23 tests, or a named
  set of touched tests), with node IDs and expected counts frozen in a spec before each launch.
- **Size:** each selection a few minutes (S1's 25 tests took 26 s); an estimated 5–10 selections over
  the implementation. Each is separately admitted, cleaned up and released; no retry to green.
- I will send each selection's spec for allocation; this request asks only whether Governance will
  schedule such selections after #39's G-2 sequence.

## Request 2 — the feasibility measurement (design §8)

- **Purpose:** decide whether the deployed values fit before the chassis adopts them: `m = 1`, `k = 5`,
  3,000 ring slots, ten windows, with option B's take barriers, the write-ahead `fsync`, the static
  rewrite coinciding with a checkpoint, on the deployment's volume images.
- **Shape:** one `tools/measure_clock.py` run under the v7 supervisor, single process, no pytest, a few
  minutes; its output records the worst cycle, p50/p95/p99, frame size and the ring's share of the diode
  image.
- **After:** if the worst cycle does not fit 100 ms with margin, `k`, the window count or the ring size
  goes back to John.

## Not requested

No push, PR, publication, merge, adoption or pin change. #39 publication remains John's decision after
its gate and evidence review. Issue #42 stays separate.
