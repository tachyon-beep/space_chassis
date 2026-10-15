# Governance

The single place a new session, agent or person reads first to know what this project is, who owns
what, what has been decided, and where each line of work stands. It is meant to become the single
source of truth in time; until it is, **the code, the issue trackers and the decision records it points
to are authoritative wherever they disagree with it.**

## The two lines

The project divides into exactly two lines of work, with no third line and nothing co-owned:

| line | what it is | where it lives | governance |
|---|---|---|---|
| **space_chassis** | the AI chassis: the world the fleet of agents lives in — Aurora's harness per agent, recorder, pump, services, containers, the brief | this repository | `chassis/` |
| **space_vehicle** | the mission simulator: one spacecraft behind per-agent windows | `tachyon-beep/space_vehicle`, vendored here as `docs/deep_research/vehicle/` | `vehicle/` |

The two meet only at the frozen window contract, `docs/diode-contract.md`, and at the deployment of the
vehicle service. Each line describes its side of that meeting in its own `interface.md`.

## Ownership

*(chassis to complete from its list: vehicle line — the space_vehicle repository and its CI, the frozen
corpus `docs/deep_research/*.md` and `integration/`, `docs/diode-contract.md`, the local
`vehicle-standalone` branch, filigree issues labelled `side:vehicle`, `governance/vehicle/`; chassis
line — everything else, including the submodule pointer and adoption commits, `governance/README.md`,
`governance/coordination.md`, `governance/chassis/`.)*

## What each line folder holds

| file | what | changes |
|---|---|---|
| `snapshot.md` | where the line stands now: repo, branch, SHA, merged and in-flight work, measures | every merge |
| `decisions.md` | the decision log: what, who (John, or a session under his delegation), when, where recorded | append-only |
| `practice.md` | how the line is worked: constraints, how work lands, gates, reviewers | when practice changes |
| `interface.md` | what the line offers the other and needs from it | when the boundary moves |
| `open.md` | in-flight items, next steps, open issues, risks, owner questions | every merge or decision |
| `records/` | historical records worth keeping (design notes, review reports, handoff packages), dated, never edited | append-only |

## Maintenance rules

1. Every file starts with **"As of <date>, <repo> @ <sha>"** and a "verify against the code" note.
2. Every fact carries a pointer — file:line, issue, PR, commit, ADR — never a paraphrase with no source.
3. The owning line updates its files **in the same change** that merges work or records a decision; a
   snapshot older than the last merge is stale and says so.
4. Decisions are appended, never rewritten; a reversal is a new dated entry that points back.
5. Nothing here may reach a fleet agent: `governance/` is in `.dockerignore`, and no image COPYs it.
6. A line proposes an edit to the other line's file through the shared filigree issue or a message; the
   owner decides and writes it.
7. Paths to session scratch (`/tmp/…`, `.scratch/`) are not durable; copy what must survive into
   `records/`.
