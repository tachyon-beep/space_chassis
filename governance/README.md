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

| project team (line) | what it builds | where it lives | governance |
|---|---|---|---|
| **space_chassis** | The AI chassis: the world the fleet of agents lives in. Aurora's harness per agent, the recorder, the pump, the operator services, the containers, the brief, and the vehicle's deployment. | this repository | `chassis/` |
| **space_vehicle** | The mission simulator: one spacecraft behind per-agent windows. | `tachyon-beep/space_vehicle`, vendored here as `docs/deep_research/vehicle/` | `vehicle/` |

The two lines' parts of the product meet at the window contract, `docs/diode-contract.md`, and at
the deployment of the vehicle service. Each line describes its side in its own `interface.md`.

## Ownership

Every path and every piece of plumbing has exactly one owner. Anything not listed under the vehicle
line is the chassis line's.

| owner | owns |
|---|---|
| **vehicle line** | the `tachyon-beep/space_vehicle` repository (`docs/deep_research/vehicle/`) and its CI, including filigree `space_chassis-4d7a6afd1f` |
| | the frozen corpus `docs/deep_research/*.md` and `docs/deep_research/integration/`, including the reconciliation rows' content |
| | `docs/diode-contract.md`, which it implements; a change still needs the chassis to adopt it |
| | the local `vehicle-standalone` branch |
| | filigree issues labelled `side:vehicle` |
| | `governance/vehicle/` |
| **chassis line** | `harness/`, `recorder/`, `pump/`, `services/`, `scripts/` |
| | `containers/`, `serve_vehicle.sh` included: the vehicle's deployment is the chassis's |
| | `Dockerfile.agent`, `docker-compose.yml` and its generator, `live/` |
| | `tests/`, including `test_vehicle_reconciliation.py`, the chassis's referee of what it deploys |
| | `contract/` (the probe and the fixture) and `brief/` |
| | `docs/design.md`, `docs/brief-claims.md`, `docs/superpowers/` |
| | the root documents (`CLAUDE.md`, `AGENTS.md`, `README.md`, `.env.example`) and `vendor/` |
| | this repository's CI, and the filigree tracker itself with every issue not labelled `side:vehicle` |
| | the submodule pointer, the reconciliation pins and every adoption commit |
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
5. **Nothing here may reach a fleet agent.** `governance/` is in `.dockerignore`, and no image COPYs
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
