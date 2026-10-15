# Governance

As of **2026-10-15**, `tachyon-beep/space_chassis` `main` @ `{{MAIN}}`. Owned by the governance
stream. **Verify against the code before trusting any line here.**

This is the place a new session, agent or person reads first, to learn who owns what, what has been
decided, and where each stream stands. The code, the issues and the decision records it points to are
authoritative wherever they disagree with it.

**Scope (John, 2026-10-15): governance is purely for the agents to deconflict and report.** How the
project works (design, specs, plans, the contract, the corpus, the vehicle-completion suite) lives in
[`../docs/`](../docs/README.md). New plans go there, not here.

## Read in this order

1. [`status.md`](status.md): where the programme is, reconciled against the code.
2. [`decisions.md`](decisions.md): the programme decision log, including the 2026-10-15 lifting of
   John's restrictions (D1–D17) and the residual decisions that still need him.
3. [`practice.md`](practice.md): how every stream works: the loop, the gates, what is still not
   allowed, what is still John's.
4. [`coordination.md`](coordination.md): channels and the rules between streams.
5. The stream you are working in: `vehicle/` or `chassis/` (`snapshot.md`, `open.md`,
   `decisions.md`, `practice.md`, `interface.md`, `records/`).

## One program, three streams, one product

**Space Aurora is one program building one product**: a fleet of self-modifying agents and the
spacecraft they fly. Two streams build it, of equal importance and in parallel; a third coordinates
and reports (John, 2026-10-10 and 2026-10-15). Emmy is programme lead (2026-10-10). The work divides,
never the product: every path, branch and task has exactly one owning stream, and there are no
shared tasks: the lead stream sets the rule and the other follows it on its side.

| stream | builds | lives in | governance folder | branches |
|---|---|---|---|---|
| **vehicle** | the mission simulator: one spacecraft behind per-agent windows | `vehicle/` (absorbed from `tachyon-beep/space_vehicle` on 2026-10-15, with its history) | `vehicle/` | `vehicle/<topic>` |
| **aurora** (the chassis line) | the world the fleet lives in: harness, recorder, pump, operator services, containers, brief, and the vehicle's deployment | `aurora/` | `chassis/` | `aurora/<topic>` |
| **governance** | coordination, status, decision records; the programme documents under `docs/vehicle-completion/` | `governance/` | this folder | `governance/<topic>` |

The two build streams meet at the window contract, `docs/diode-contract.md`, and at the deployment
of the vehicle service. Each describes its side in its `interface.md`. Agents work in git worktrees
of this one repository (`make worktree STREAM=… TOPIC=…`); the layout and what moved:
[`docs/plans/2026-10-15-three-stream-restructure.md`](../docs/plans/2026-10-15-three-stream-restructure.md).
Paths in records written before 2026-10-15 are as they were: `harness/` is now `aurora/harness/`,
`docs/deep_research/vehicle/` is `vehicle/`.

## Ownership

Every path has exactly one owner. Anything not listed is the aurora stream's.

| owner | owns |
|---|---|
| **vehicle** | `vehicle/`; the frozen corpus `docs/deep_research/`; `docs/diode-contract.md` (a change still needs the chassis to adopt it); `governance/vehicle/`; issues labelled `stream:vehicle` |
| **aurora** | `aurora/` entire, including the vehicle's deployment (`containers/serve_vehicle.sh`, the `vehicle` compose service and image), `aurora/contract/`, `aurora/brief/`, `aurora/tests/` with `test_vehicle_reconciliation.py`; `docs/design.md`, `docs/brief-claims.md`, `docs/superpowers/`, `docs/README.md`; the root files (`CLAUDE.md`, `AGENTS.md`, `README.md`, `Makefile`, `pyproject.toml`, `requirements-dev.txt`); every adoption of a vehicle commit into the chassis's pins; the parked `vehicle-adoption` and `wip/sv-recorder-opus-20261008`; `governance/chassis/`; issues labelled `stream:aurora` |
| **governance** | `governance/README.md`, `status.md`, `decisions.md`, `practice.md`, `coordination.md`, `records/`, `MASTER_GOVERNANCE_PLAN.md` (closed); `docs/vehicle-completion/`; the root CI workflows until a build stream takes them; issues labelled `stream:governance` |

## What each stream folder holds

| file | what | changes |
|---|---|---|
| `snapshot.md` | where the stream stands: branch, SHA, merged and in-flight work, measures | every merge |
| `decisions.md` | the stream's decision log: what, who (John, or a session under his delegation), when, where recorded | append-only |
| `practice.md` | what is particular to how the stream is worked; the shared rules are in [`practice.md`](practice.md) | when practice changes |
| `interface.md` | what the stream offers the other and needs from it | when the boundary moves |
| `open.md` | in-flight items, next steps, risks, questions for John | every merge or decision |
| `records/` | dated records worth keeping, never edited | append-only |

## Rules

1. Every file starts with **"As of <date>, <repo> @ <sha>"** and a "verify against the code" note.
2. Every fact carries a pointer (file:line, issue, PR, commit, ADR), never a paraphrase with no source.
3. The owning stream updates its files **in the same change** that merges work or records a
   decision. A snapshot older than the last merge is stale and says so.
4. Decisions are appended, never rewritten. A reversal is a new dated entry that points back.
5. **Nothing here may reach a fleet agent.** `governance/` is outside the agents' build context
   (`aurora/`), so no image can `COPY` it. It holds design reasoning the agents must not see.
6. A stream proposes an edit to another stream's file on an issue; the owner decides and writes it.
7. Paths to session scratch (`/tmp/…`, `.scratch/`) are not durable. Copy what must survive into
   `records/`, except unqualified code, which goes to a `wip/` branch (`decisions.md` D11).
8. Each stream commits its own governance files on its own branch. (The 2026-10-10 rule that the
   chassis committed `governance/vehicle/` verbatim is retired, `decisions.md` D13.)
9. `aurora/tests/test_retired.py` exempts `governance/`, because the records hold history.
