# Governance

As of **2026-10-10**, `tachyon-beep/space_chassis` `aurora-port` @ `1177d47`. Owned by the chassis
line. **Verify against the code before trusting any line here.**

This is the single place a new session, agent or person reads first, to learn:
- what this project is;
- who owns what;
- what has been decided;
- where each line of work stands.

It is meant to become the single source of truth in time. Until it is, **the code, the issue
trackers and the decision records it points to are authoritative wherever they disagree with it.**

## One program, two project teams, one product

**Space Aurora is one program building one product**: a fleet of self-modifying agents and the
spacecraft they fly. Two project teams build it, of equal importance and working together in
parallel; Emmy coordinates the program (John, 2026-10-10). This folder calls each project team a
*line*. What divides is the work, never the product: every path, branch and task has exactly one
owning team, there is no third team, and nothing is co-owned (John, 2026-10-10).

**There are no shared tasks.** Every task has one lead team, and the lead sets the rule. Where the
other team has to do the same thing on its side, it follows the lead's rule rather than setting its
own (John, 2026-10-10).

| project team (line) | what it builds | where it lives | governance |
|---|---|---|---|
| **space_chassis** | The AI chassis: the world the fleet of agents lives in. Aurora's harness per agent, the recorder, the pump, the operator services, the containers, the brief, and the vehicle's deployment. | `aurora/` | `chassis/` |
| **space_vehicle** | The mission simulator: one spacecraft behind per-agent windows. | `vehicle/` (absorbed from `tachyon-beep/space_vehicle` @ `8c6f71d` on 2026-10-15) | `vehicle/` |

**Since 2026-10-15 the program is one repository with three streams** (John, 2026-10-15):
`vehicle/` (the vehicle sim), `aurora/` (the Aurora container), `governance/` (this folder). Agents
work in git worktrees of this one repository, on branches named for their stream. The plan, what
moved and what it broke: [`plans/2026-10-15-three-stream-restructure.md`](plans/2026-10-15-three-stream-restructure.md).
Paths in older records below and in `chassis/`, `vehicle/` and `MASTER_GOVERNANCE_PLAN.md` are as
they were written: `harness/` is now `aurora/harness/`, `docs/deep_research/vehicle/` is `vehicle/`.

The two lines' parts of the product meet at the window contract, `docs/diode-contract.md`, and at
the deployment of the vehicle service. Each line describes its side in its own `interface.md`.

## Ownership

Every path and every piece of plumbing has exactly one owner. Anything not listed under the vehicle
line is the chassis line's.

| owner | owns |
|---|---|
| **vehicle line** | `vehicle/` (formerly the `tachyon-beep/space_vehicle` repository) and its CI, including filigree `space_chassis-4d7a6afd1f` |
| | the frozen corpus `docs/deep_research/*.md` and `docs/deep_research/integration/`, including the reconciliation rows' content |
| | `docs/diode-contract.md`, which it implements; a change still needs the chassis to adopt it |
| | the local `vehicle-standalone` branch |
| | filigree issues labelled `side:vehicle` |
| | `governance/vehicle/` |
| **chassis line** | `aurora/`: `harness/`, `recorder/`, `pump/`, `services/`, `scripts/` |
| | `aurora/containers/`, `serve_vehicle.sh` included: the vehicle's deployment is the chassis's |
| | `aurora/Dockerfile.agent`, `aurora/docker-compose.yml` and its generator, `aurora/live/` |
| | `aurora/tests/`, including `test_vehicle_reconciliation.py`, the chassis's referee of what it deploys |
| | `aurora/contract/` (the probe and the fixture) and `aurora/brief/` |
| | `aurora/docs/` (`design.md`, `brief-claims.md`, `superpowers/`, `plans/`) |
| | the root and `aurora/` documents (`CLAUDE.md`, `AGENTS.md`, `README.md`, `Makefile`, `aurora/.env.example`) and `aurora/vendor/` |
| | this repository's CI, and the filigree tracker itself with every issue not labelled `side:vehicle` |
| | the reconciliation pins and every adoption (subtree) merge into `vehicle/` |
| | the paused SV branch `wip/sv-recorder-opus-20261008` |
| | `governance/README.md`, `governance/coordination.md`, `governance/chassis/` |

## What each line folder holds

| file | what | changes |
|---|---|---|
| `snapshot.md` | where the line stands now: repo, branch, SHA, merged and in-flight work, measures | every merge |
| `decisions.md` | the decision log: what, who (John, or a session under his delegation), when, where recorded | append-only |
| `practice.md` | how the line is worked: constraints, how work lands, gates, reviewers | when practice changes |
| `interface.md` | what the line offers the other line and needs from it | when the boundary moves |
| `open.md` | in-flight items, next steps, open issues, risks, questions for John | every merge or decision |
| `records/` | historical records worth keeping (design notes, review reports, handoff packages), dated and never edited | append-only, optional |

## Maintenance rules

1. Every file starts with **"As of <date>, <repo> @ <sha>"** and a "verify against the code" note.
2. Every fact carries a pointer (file:line, issue, PR, commit, ADR), never a paraphrase with no
   source.
3. The owning line updates its files **in the same change** that merges work or records a decision.
   A snapshot older than the last merge is stale and says so.
4. Decisions are appended, never rewritten. A reversal is a new dated entry that points back.
5. **Nothing here may reach a fleet agent.** `governance/` is outside the agents' build context (`aurora/`) and in `aurora/.dockerignore`, and no image COPYs
   it. It holds design reasoning the agents must not see.
6. A line proposes an edit to the other line's file through the shared filigree issue or a message.
   The owner decides and writes it.
7. Paths to session scratch (`/tmp/…`, `.scratch/`) are not durable. Copy what must survive into
   `records/`.
8. **Commits:** this folder lives in the chassis repository, so the chassis line commits it. The
   vehicle line writes `governance/vehicle/` directly, and the chassis commits it verbatim, never
   editing it, on its next commit to `aurora-port`, or sooner on request
   (`coordination.md`).
9. `tests/test_retired.py` exempts `governance/`, because the decision logs record history.
