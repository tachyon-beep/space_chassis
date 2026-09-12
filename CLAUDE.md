# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```sh
python3 -m pytest -q                                   # whole suite, no Docker needed
python3 -m pytest tests/test_chassis.py -q             # one file
python3 -m pytest tests/test_chassis.py::test_a_conversation_round_trips -q

uvx ruff check . --no-cache                            # ruff is not installed here; uvx fetches it
uvx ruff format --check . --no-cache

docker compose --profile fleet config -q               # the topology parses
sh scripts/prepare_host.sh                             # directories, ownership, roster, .env
python3 scripts/status.py --verbose                    # one line per agent, from the record
sh scripts/verify_containment.sh --all                 # safety claims vs. a running stack

python3 endurance/run_local.py endurance/scenarios/short.json    # fastest end-to-end proof
```

The suite is not a unit suite: it runs the real recorder, supervisor and chassis in a
temporary world against `endurance/stub_model.py`, a model that answers on cue. The smoke
stack in `docker-compose.override.example.yml` (three agents, the stub, the contract
fixture as the window) costs nothing and is the fastest way to see whether the world is
still intact after a change.

## The scope boundary

**This repository builds everything except the vehicle.** Nothing here models physics or
names a single spacecraft verb. The vehicle lives behind a per-agent directory implemented
by someone else; the only thing the two halves share is `docs/diode-contract.md`, and
`contract/fake_diode.py` is a fixture that satisfies it and models nothing. A request that
sounds like "add a thruster command" belongs on the far side of the window, not here.

`docs/deep_research/` (~13k lines) specifies that far side. Don't read it unless the work is
on the contract itself. `docs/design.md` is the rationale for every decision below; read it
before arguing with one.

## Operator side vs. fleet side

| In the repo | In a container | Who owns it |
|---|---|---|
| `services/` | `/opt/services`, read-only from the image | the operator; the fleet cannot touch it |
| `brief/` | `/opt/brief`, read-only | the operator |
| `containers/agent.env` | `/etc/agent.env` | the operator; the world's constants |
| `tasks/` | baked at `/opt/agent`, copied once into `/work` (marker `.seeded`) | the fleet, to rewrite; `/opt/agent` is the seed the ladder restores from |

The supervisor and the runtime run from the image, never from `/work` — a supervisor that
repaired the runtime out of the directory the runtime repairs would be repairing sand.
`test_the_supervisor_never_runs_the_runtime_out_of_the_codebase` enforces it.

That produces the repo's sharpest gotcha: there are **two copies of `chassis.py`** in a
container. A run's working directory is `/work`, so a bare `import chassis` picks up the
inert copy, and loading the real file yourself creates a *second* module object with a
different `ToolRegistry` class — the duty registers tools on one, the chassis looks them up
on the other, and every tool call fails as unknown. `_load_runtime()` in `tasks/duty.py`
handles this by preferring `sys.modules["chassis"]`. Don't "simplify" it into an import.

## The exit-code contract

Shared vocabulary between `services/chassis.py` and `services/supervisor.py`; changing one
means changing the other.

| Exit | Meaning | Supervisor's response |
|---|---|---|
| 0 | ended cleanly | resume |
| 42 | ended on purpose (handoff) | resume, and the note opens the next run |
| 43 | the run's own fault | climb the ladder |
| 44 | environment unusable | wait, retry unchanged |
| other/signal | crash | climb the ladder |
| alive, no progress | wedged | kill, then climb the ladder |

Ladder rungs: resume → restore the duty from the image → restore the whole seed codebase →
give up. Two invariants tests hold in place: a run that hits its turn or time budget exits
**42, not 0 and not 43** (a busy fleet must not make the ladder climb), and **no rung ever
touches `/home`, `/diary`, or the saved conversation**.

## Imports and style

Every service does `sys.path.insert(0, SERVICES_DIR)` then `from common import ...`;
`tests/conftest.py` puts `services/`, `endurance/` and `contract/` on `sys.path`, so tests
write `from common import ...`, `from stub_model import ...`, `import chassis` — never
`from services.common import ...`. `filterwarnings = ["error::DeprecationWarning"]` means any
deprecation warning fails the suite.

- The operator-side services are **standard library only**. Adding a dependency to them is a
  design change, not a convenience.
- Every published file goes through `common.write_json_atomic`; every read of an
  agent-writable file is bounded by `MAX_READ_BYTES`.
- No request header is ever written to the record — bodies only. A test enforces it.
- The reasoning lives in module docstrings and comments, which is why `E501` is off. Test
  names are full sentences stating the property under test.
- `.scratch/` is the gitignored scratch directory; `endurance/runs/` and `volumes/` are
  runtime artefacts, never source.

## Deliberate non-features — do not "fix" these

- Postgres, NATS and Redis are present, running and **empty**: no schema, no subjects, no
  roles. Deciding what they are for is the mission's first question.
- There is no shared queue, dispatcher, lock service or role table for the fleet, and no
  ranking in the names. Building a control layer is the experiment.
- Each compose service repeats its full mount list: a YAML sequence alias cannot be merged
  into a longer list, so adding one mount to the fleet means ten edits.
- `agent_2..10` sit in the `fleet` profile and `diode` in the `diode` profile, so a bare
  `docker compose up` is a cheap one-agent stack.
- Agents join `worknet` (`internal: true`) and nothing else — never `modelnet` or
  `windowside`. That is the one hard rule.
- Fleet names are drawn by `scripts/roster.py` into `.env` as `FLEET_N_SLUG`/`FLEET_N_NAME`,
  because compose reads `.env` with no flags. A roster file would need `--env-file` on every
  command, and a stack started without it hands every agent a fallback name and a home it
  cannot write.
- `vendor/registry/` is gitignored and `prepare_host.sh` refuses without it; rebuild with
  `scripts/build_registry.sh`.

<!-- filigree:instructions:v3.3.0:c1c023c3 -->
<!-- filigree:last-writer:filigree install -->
## Filigree Issue Tracker

`filigree` tracks this project's work. Use it to find, claim, update and close
issues: `filigree session-context` at session start, then
`filigree start-next-work --assignee <name>`.

Full reference: the **filigree-workflow** skill (patterns, priorities,
observations, error codes), `filigree --help`, and the `mcp__filigree__*` tool
schemas. Prefer the MCP tools when available; fall back to the CLI.

Two rules `--help` will not tell you:

1. Claim atomically: `work_start` / `work_start_next` (MCP) or `start-work` /
   `start-next-work` (CLI). Never chain a claim with a separate status update;
   that two-step form races other agents.
2. On `SCHEMA_MISMATCH` the installed filigree is older than the project
   database. Surface it to the user; do not retry.
<!-- /filigree:instructions -->
