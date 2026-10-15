# Vehicle — decision log

As of **2026-10-10**, `tachyon-beep/space_vehicle` main @ `64fc58c`. Append-only: a decision that is
revised gets a new dated entry pointing back, never an edit in place. **Who** is either *John* (the
owner/operator) or *coordinator* (a Space Vehicle session deciding under John's standing delegation,
open to his revision). **Where** is the authoritative record; this log only indexes it.

## Standing delegations and rules from John

| date | decision | where |
|---|---|---|
| 2026-10-08 | Work autonomously until a hard blocker; lean towards closing blockers by picking the best answer rather than stopping | session instruction |
| 2026-10-08 | Ask before external publication, merges, settings changes, release, deployment or paid-model campaigns; respect platform denials | session instruction |
| 2026-10-09 | PR merges authorised once CI is green; pushes allowed | session instruction |
| 2026-10-09 | Reviewers: Fable while available, plus a Codex CLI agent at `gpt-6-astra` high effort and a Claude Opus reviewer | session instruction |
| 2026-10-09 | **Information and action management are the agents' to manage — we do not solve it for them.** Windows carry no scenario, seed, fault plan or designers' diagnostic commentary | session instruction → #36, #37, #35 |
| 2026-10-09 | Clean agent-facing text as we go; a full sweep at the end (HELP.md verb texts first) | session instruction → #35 |

## ADR 0001 — the shared executive (`docs/decisions/0001-shared-executive.md`)

| date | decision | who |
|---|---|---|
| 2026-10-08 | A: rotating cross-window arbitration order | John |
| 2026-10-08 | B: a batch above `--max-batch` (32) is refused whole with one result | John |
| 2026-10-08 | C: an interlock that cannot be evaluated refuses (`INTERLOCK UNEVALUATED`) | John |
| 2026-10-08 | D: a window or directory bound to another world refuses (until WP08) | John |
| 2026-10-08 | Post-review clarifications: root record authoritative (later amended by ADR 0002 H), settle-first deferrals, preserved vs honoured variables, window-local receipts, `--init` union, `--plan` on bound directories | coordinator |
| 2026-10-09 → 10 | Dated amendments for per-slug agent mounts (chassis `adf38d6`) and for choice D under resume (#21) | coordinator |

## ADR 0002 — mission clock and continuity (`docs/decisions/0002-mission-clock-and-continuity.md`)

| decision | value | who |
|---|---|---|
| A — wall time to ticks | multiplier **m = 1**, fixed-rate scheduler (A2) | John |
| B — claim/publication cadence | **k = 5** ticks per cycle; burst bound k (catch up by whole cycles) | John |
| C — overload | **shed → dilate → hold**, lag ceiling 30 wall seconds | John |
| D — pause | **D1** operator pause the fleet cannot trigger | John |
| E — command budget time base | **E2** mission time | John |
| F — downtime | **F1** freeze: mission time does not advance while down | John |
| G — checkpoint contents; H — where it lives | H1: a private writable mount (`--state-dir`), never under the diode volume | coordinator |
| I — atomicity, integrity, compatibility | engine hash + Python (full version) + platform (system, machine, libc) + tick_hz | coordinator |
| J — cadence and record | **J2**: full checkpoint every **N = tick_hz = 50** ticks + durable per-cycle record + published-tick marks | coordinator; N accepted by John |
| K — corrupt checkpoint | **K2** fall back to the previous verified generation; `--new-world` the only recorded escape | John |
| L(a) — `seq` after restart | **L1** continues | coordinator |
| L(b) — result filename clock | **MET rendered as UTC** | John |
| M — phase | a function of the tick | coordinator |

## Delivery decisions

| date | decision | who | where |
|---|---|---|---|
| 2026-10-09 | The chassis owns the vehicle service's deployment topology (compose, networks, mounts, serve script); the vehicle states its needs. The vehicle runs with **no network** (`network_mode: none`) | coordinator after a systems analysis; John set the goal | chassis spec §8; `interface.md` |
| 2026-10-09 | Vehicle `/state` volume sized **40 GB** (record ≈ 13–22 GB per 192 h mission, nothing pruned) | coordinator | filigree `space_chassis-93010ff54e` c.29 |
| 2026-10-09 | The `vehicle` window is served only when no roster is given — never beside a fleet (it would be an unowned command authority over the shared world); never run `diode_probe` against a live mission | coordinator | `records/2026-10-09-chassis-adoption-package.md` §2.2 |
| 2026-10-09 | CI job timeout 45 → 90 min | coordinator | #34 |
| 2026-10-09 | #21 design addenda A1–A8, B1–B13: restart cost bounded by the checkpoint anchor; exactly-once qualified as the contract allows (a batch lost before its row has no result); K2 fallback tested in #21; `--closed-interlock` across a restart is a union (a restart never clears a trip); a world's slug set is fixed; cadence checkpoint failures continue, journaled and on stderr; the budget's wall-clock reset is a residual until #25 | coordinator | `records/2026-10-09-wp08-3-resume-design.md`; ADR 0002 J (xxi)–(xxix) on the #21 branch |
| 2026-10-10 | Pin the agent image's Python base by digest (`python:3.13-slim@sha256:70729b46…`, Python 3.13.16); a digest change is a new-world event | **John** | chassis `vehicle-adoption` `044b5c5` |
| 2026-10-10 | #21 review fix round rulings R1–R5: one rule for an unparseable record line (torn only as a file's last line or before a new boot's header; elsewhere corruption); a result counts as delivered only after its file and the output directory are fsync'd; the interrupt test uses a subprocess and a real SIGINT; fixes on top of `06f08a3`, no history rewrite | coordinator | `records/2026-10-10-wp08-3-review-fixes.md` |
