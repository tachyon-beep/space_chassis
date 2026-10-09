# AGENTS.md — space_chassis

A world for ten self-modifying agents: a floor of capability, one window outward, and a record they
cannot reach. This is what an agent needs before touching anything. `CLAUDE.md` covers the same
ground for Claude Code, `docs/design.md` is the rationale for every decision here, and
`docs/superpowers/specs/2026-10-09-aurora-port-design.md` is the design of the world as it now is —
read those before arguing with a rule below.

## The scope boundary

**This repository builds everything except the vehicle.** Nothing here models physics or names a
spacecraft verb. The vehicle answers a per-agent directory from behind `docs/diode-contract.md`, and
that contract is the only thing the two halves share.

| | |
|---|---|
| **Here** | the world: `harness/` (Aurora's agent, chassis and watchdog, the seed each agent rewrites), `recorder/`, `pump/`, `services/` (the operator's monitor and review panel), `containers/`, `brief/`, `contract/` (the probe and a fixture that models nothing), the generated compose topology, `live/` and the tests |
| **The vehicle** | `docs/deep_research/vehicle/` — **its own repository**, `tachyon-beep/space_vehicle`, mounted here as a git submodule: its configuration, reference plant, linter and referee |
| **The evidence** | `docs/deep_research/*_diode.md` and `integration/` — the corpus the vehicle was built from. **Frozen: read, cite, never edit.** A round that "fixes" one of them is editing the evidence |

A request that sounds like "add a thruster command" belongs on the far side of the window. A request
that sounds like "the fleet cannot see the window" belongs here.

## Getting started

```sh
git submodule update --init --recursive     # the vehicle is a submodule; without it, collection is partial
python3 -m pytest -q -n 8                   # the whole suite, no Docker needed
uvx ruff check . --no-cache                 # ruff is not installed here; uvx fetches it
docker compose --profile fleet config -q    # the topology parses
sh scripts/prepare_host.sh                  # roster, .env, and the bounded volume images
python3 scripts/status.py --verbose         # one line per agent, from the record
sh scripts/verify_containment.sh --all      # safety claims vs. a running stack
python3 -m pytest live -q                   # the smoke stack: three agents, a stub model; the fastest end-to-end proof
```

One `pytest` collects every suite: the operator side and the assertions about this repository's own
files (`tests/`), Aurora's harness, recorder and pump with what this repository added to them
(`harness/tests`, `recorder/tests`, `pump/tests`), and the vehicle's referee through the submodule
(`docs/deep_research/vehicle/tests/`). It is minutes, not seconds, and it is the only thing that
runs every refusal, so run it before you commit. `live/` is separate because it starts containers.

## Layout

| path | what it is |
|---|---|
| `harness/` | Aurora's `agent.py`, `chassis.py`, `command_runtime.py`, `watchdog.py` and the prompts: baked at `/opt/agent` and copied into each agent's `/work` at every start, as a git repository with `baseline` and `rescue` tags. The agent's to rewrite, all of it |
| `recorder/` | `proxy.py` and `recorder_streams.py`: one recorder per agent, holding the credential, writing the transcript, enforcing the spend caps (`core_caps.py`) |
| `pump/` | `pump.py`: the agent's scheduled and kept-alive processes, run from the image, outliving every run |
| `services/` | The operator's half: `health.py` (signals from the transcripts), `fleet_monitor.py`, `review.py`, `common.py` (atomic writes, bounded reads) |
| `brief/` | What the agents are told (`/opt/brief`); `docs/brief-claims.md` sources each claim it and the prompts make |
| `containers/` | `entrypoint.sh` (servers, pump, seed, then the watchdog) and `serve_vehicle.sh` (the vehicle service's entrypoint) |
| `contract/` | `diode_probe.py` (the instrument against the window) and `fake_diode.py` (a fixture that satisfies the contract and models nothing) |
| `scripts/` | `prepare_host.sh`, `roster.py`, `volume_images.py`, `build_compose.py`, `status.py`, `journal.py`, `verify_containment.sh` |
| `live/` | The smoke stack (`stack.py`, the cued `stub_llm.py`) and the checks run against it |
| `docs/diode-contract.md` | **The interface.** The vehicle's builder implements it; this side probes it. Changing it means changing both halves |
| `docs/deep_research/` | The corpus (frozen) and `integration/` — the reconciliation register, the canonical vocabulary, the design and review maps |
| `docs/deep_research/vehicle/` | **The vehicle, as a submodule** of `tachyon-beep/space_vehicle` |
| `tests/` | The suite's root: the operator side and this repository's own files |

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

- **The agent holds the pen on its whole harness, the watchdog included.** Nothing in the image, a
  test or a hook may make `/work` read-only. Containment comes from the binds and the networks, not
  from keeping code out of the agent's reach.
- **The exit-code contract** is shared vocabulary between `harness/chassis.py` and
  `harness/watchdog.py`'s `plan_recovery`; changing one means changing the other. `0` restart with
  the conversation, `42` `done` (a fresh agent), `43` the harness ended the run as broken, `44` the
  environment refused (pause 60 s plus up to 30 s), `45` `reset` (restore, conversation kept),
  anything else climbs the ladder: `baseline_same` → `baseline_new` → `rescue_new` → the container
  ends and reseeds from the image. Three exit-0s inside 120 s count as a fault.
- **Every per-agent volume is bound per agent** (`volumes/<kind>_<slug>/data`, and the window `volumes/diode/data/<slug>`), and no agent mounts a
  directory that holds a sibling's. That one rule is what keeps agents out of each other's state,
  and it is what attributes a command at the window.
- **`harness/`, `recorder/` and `pump/` are vendored from Aurora at 42faf41** and kept close to it so
  they can be re-synced; they import by bare name, with their own conftest on `sys.path`.
- **The operator-side code (`services/`, `scripts/`) is standard library only.** Adding a dependency
  is a design change, not a convenience. The vehicle's tools need PyYAML deliberately and are wired
  into nothing; nothing there may be imported here, and nothing here may be imported there.
- Every published file goes through `common.write_json_atomic`; every read of an agent-written file
  is bounded and does not follow a link the agent planted. **No request header is ever written to
  the record — bodies only**, and a test enforces it.
- `filterwarnings = ["error::DeprecationWarning"]`: a deprecation warning fails the suite.
- Tests are named as sentences stating the property under test, and the reasoning lives in module
  docstrings and comments — which is why `E501` is off. Add to the suite; don't rewrite it.
- `.scratch/` is gitignored scratch; `volumes/` and `volume-images/` are runtime artefacts.
  `tests/test_retired.py` keeps the tree free of the runtime the port replaced.

## Deliberate non-features — do not "fix" these

- Postgres, NATS and Redis are present, running and **empty**: no schema, no subjects, no roles.
  Deciding what they are for is the mission's first question.
- There is no shared queue, dispatcher, lock service or role table for the fleet, and no ranking in
  the names. Building a control layer is the experiment.
- `done` archives the conversation and starts a fresh agent on the newest checkpoint the agent tagged
  (`experimental`, else `baseline`, else `rescue`); what it did not commit and tag is gone. Memory,
  context management and tooling
  are the agents' to build, and churn is their business; the operator surfaces observe and never act.
- `docker-compose.yml` is generated by `scripts/build_compose.py` and repeats each service's full
  mount list; edit the generator, never the YAML.
- `agent_2..10` and `recorder_2..10` sit in the `fleet` profile and `diode` in the `diode` profile.
  `vehicle` is a third profile, an alternative to `diode` rather than a neighbour — two publishers
  into one slug is two vehicles wearing one name.
- **Agents join `worknet` (`internal: true`) and nothing else** — never `modelnet` or `windowside`.
  That is the one hard rule. The vehicle service and the diode fixture are on no network an agent is on.
- Fleet names are drawn by `scripts/roster.py` into `.env` as `FLEET_N_SLUG`/`FLEET_N_NAME`, because
  compose reads `.env` with no flags; the roster itself is `operator/roster.json`, which no agent mounts.
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
