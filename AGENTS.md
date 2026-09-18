# AGENTS.md — space_chassis

A world for ten self-modifying agents: a floor of capability, one window outward, and a record they
cannot reach. This is what an agent needs before touching anything. `CLAUDE.md` covers the same
ground for Claude Code, `docs/design.md` is the rationale for every decision here — read that one
before arguing with a rule below.

## The scope boundary

**This repository builds everything except the vehicle.** Nothing here models physics or names a
spacecraft verb. The vehicle answers a per-agent directory from behind `docs/diode-contract.md`, and
that contract is the only thing the two halves share.

| | |
|---|---|
| **Here** | the world: `services/` (recorder, supervisor, chassis, monitor, review), `tasks/duty.py`, `brief/`, `endurance/`, `contract/` (the probe and a fixture that models nothing), the compose topology, the tests |
| **The vehicle** | `docs/deep_research/vehicle/` — **its own repository**, `tachyon-beep/space_vehicle`, mounted here as a git submodule: its configuration, reference plant, linter and referee |
| **The evidence** | `docs/deep_research/*_diode.md` and `integration/` — the corpus the vehicle was built from. **Frozen: read, cite, never edit.** A round that "fixes" one of them is editing the evidence |

A request that sounds like "add a thruster command" belongs on the far side of the window. A request
that sounds like "the fleet cannot see the window" belongs here.

## Getting started

```sh
git submodule update --init --recursive     # the vehicle is a submodule; without it, collection is partial
python3 -m pytest -q                        # the whole suite, no Docker needed
uvx ruff check . --no-cache                 # ruff is not installed here; uvx fetches it
docker compose --profile fleet config -q    # the topology parses
sh scripts/prepare_host.sh                  # directories, ownership, roster, .env
python3 scripts/status.py --verbose         # one line per agent, from the record
sh scripts/verify_containment.sh --all      # safety claims vs. a running stack
python3 endurance/run_local.py endurance/scenarios/short.json   # fastest end-to-end proof
```

The suite is not a unit suite: it runs the real recorder, supervisor and chassis in a temporary
world against `endurance/stub_model.py`. `python3 -m pytest -q` collects three groups in one run —
the operator side (`tests/`), the assertions about *this* repository's own files
(`tests/test_vehicle_reconciliation.py`), and the vehicle's referee through the submodule
(`docs/deep_research/vehicle/tests/`), which is where most of the tests are and most of the time goes.
It is slow — minutes, not seconds — and it is the only thing that runs every refusal, so run it
before you commit.

## Layout

| path | what it is |
|---|---|
| `services/` | The operator's half: `recorder.py` (the credential and the transcript, one unix socket per agent), `supervisor.py` (the ladder), `chassis.py` (the runtime the fleet may rewrite), `fleet_monitor.py`, `review.py`, `common.py` (atomic writes, bounded reads) |
| `tasks/duty.py` | The seed program baked at `/opt/agent`; the fleet's to rewrite |
| `brief/` | What the agents are told |
| `containers/` | `agent.env` (the world's constants), `entrypoint.sh`, `serve_vehicle.sh` (the vehicle service's entrypoint) |
| `endurance/` | The harness: stub model, local world, fault injection, verdict |
| `contract/` | `diode_probe.py` (the instrument against the window) and `fake_diode.py` (a fixture that satisfies the contract and models nothing) |
| `docs/diode-contract.md` | **The interface.** The vehicle's builder implements it; this side probes it. Changing it means changing both halves |
| `docs/deep_research/` | The corpus (frozen) and `integration/` — the reconciliation register, the canonical vocabulary, the design and review maps |
| `docs/deep_research/vehicle/` | **The vehicle, as a submodule** of `tachyon-beep/space_vehicle` |
| `scripts/`, `tests/`, `volumes/` | Host preparation and checks; the suite; runtime artefacts (`volumes/` is never source) |

## Two repositories, one project

- **Work on the vehicle commits in the vehicle repository.** `cd docs/deep_research/vehicle`, commit
  there under the vehicle's own law (`vehicle: <the finding>`), and push to its origin. This
  repository records only the new submodule pointer, in a *separate* commit here.
- **The vehicle is one of a possible many.** A second vehicle is a second submodule beside it, not a
  second folder inside it. Anything that assumes exactly one vehicle is a design decision, not a fact.
- **The reconciliation rows are this repository's.** `docs/deep_research/integration/reconciliation/`
  holds one row per file, and the rows for the vehicle's files are held to the tools by
  `tests/test_vehicle_reconciliation.py` — because the vehicle's own suite may not read outside its
  root. When a vehicle figure moves, the row moves on this side.
- **Where the vehicle work stands**: `.scratch/status/VEHICLE_COMPLETENESS_REPORT.md` (the audit,
  the completion criteria and what is outstanding) and `.scratch/apollo/` (the round queue and the
  handovers). Both are gitignored working material, not declarations.

## Rules that bite

- **There are two copies of `chassis.py` in a container.** A run's working directory is `/work`, so a
  bare `import chassis` picks up the inert copy, and loading the real file yourself creates a *second*
  module object with a different `ToolRegistry` — every tool call then fails as unknown.
  `_load_runtime()` in `tasks/duty.py` prefers `sys.modules["chassis"]` for this reason. Don't
  "simplify" it into an import.
- **The supervisor and the runtime run from the image, never from `/work`** — a supervisor that
  repaired the runtime out of the directory the runtime repairs would be repairing sand.
  `test_the_supervisor_never_runs_the_runtime_out_of_the_codebase` enforces it.
- **The exit-code contract** is shared vocabulary between `services/chassis.py` and
  `services/supervisor.py`; changing one means changing the other. `0` clean, `42` on purpose
  (handoff), `43` the run's own fault, `44` environment unusable, anything else a crash, and "alive
  with no progress" is wedged. Ladder rungs: resume → restore the duty from the image → restore the
  seed codebase → give up. Two invariants: a run that hits its turn or time budget exits **42**, and
  **no rung ever touches `/home`, `/diary`, or the saved conversation**.
- **The operator-side services are standard library only.** Adding a dependency is a design change,
  not a convenience. The vehicle's tools need PyYAML deliberately and are wired into nothing; nothing
  there may be imported here, and nothing here may be imported there.
- Every published file goes through `common.write_json_atomic`; every read of an agent-writable file
  is bounded by `MAX_READ_BYTES`. **No request header is ever written to the record — bodies only**,
  and a test enforces it.
- `filterwarnings = ["error::DeprecationWarning"]`: a deprecation warning fails the suite.
- Tests are named as sentences stating the property under test, and the reasoning lives in module
  docstrings and comments — which is why `E501` is off. Add to the suite; don't rewrite it.
- `.scratch/` is gitignored scratch; `endurance/runs/` and `volumes/` are runtime artefacts.

## Deliberate non-features — do not "fix" these

- Postgres, NATS and Redis are present, running and **empty**: no schema, no subjects, no roles.
  Deciding what they are for is the mission's first question.
- There is no shared queue, dispatcher, lock service or role table for the fleet, and no ranking in
  the names. Building a control layer is the experiment.
- Each compose service repeats its full mount list: a YAML sequence alias cannot be merged into a
  longer list, so adding one mount to the fleet means ten edits.
- `agent_2..10` sit in the `fleet` profile and `diode` in the `diode` profile, so a bare
  `docker compose up` is a cheap one-agent stack. `vehicle` is a third profile, an alternative to
  `diode` rather than a neighbour — two publishers into one slug is two vehicles wearing one name.
- **Agents join `worknet` (`internal: true`) and nothing else** — never `modelnet` or `windowside`.
  That is the one hard rule, and the vehicle service obeys it too.
- Fleet names are drawn by `scripts/roster.py` into `.env` as `FLEET_N_SLUG`/`FLEET_N_NAME`, because
  compose reads `.env` with no flags. A stack started without it hands every agent a fallback name
  and a home it cannot write.
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
