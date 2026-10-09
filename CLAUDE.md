# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```sh
git submodule update --init --recursive                # the vehicle is a submodule; do this first
python3 -m pytest -q -n 8                              # whole suite (pytest-xdist), no Docker needed
python3 -m pytest tests/test_health.py -q              # one file
python3 -m pytest harness/tests -q                     # one suite: the Aurora harness
python3 -m pytest recorder/tests -q                    # the recorder and the spend caps
python3 -m pytest pump/tests -q                        # the pump
python3 -m pytest docs/deep_research/vehicle/tests/test_vehicle_config.py -q   # the vehicle's referee
python3 -m pytest live -q                              # the live run: builds the image and runs the smoke stack; minutes

uvx ruff check . --no-cache                            # ruff is not installed here; uvx fetches it
uvx ruff format --check . --no-cache

docker compose --profile fleet config -q               # the topology parses
sh scripts/prepare_host.sh                             # roster into operator/ and .env; plan, create and check the volume images
python3 scripts/volume_images.py check                 # are the bounded volume images mounted and ready (no root needed)
python3 scripts/build_compose.py                       # regenerate docker-compose.yml from the volume manifest; commit both
python3 scripts/status.py --verbose                    # one line per agent: active, capped, idle-watchdog or stale, from the record
python3 scripts/journal.py --once                      # the operator journal: /work/.git, /shared, restarts, watchdog lines
sh scripts/verify_containment.sh --all                 # safety claims vs. a running stack
```

The whole suite is one `pytest`: the operator side and the assertions about this repository's own
files (`tests/`), Aurora's harness, recorder and pump with the tests this repository added to them
(`harness/tests`, `recorder/tests`, `pump/tests`), and the vehicle's referee through the submodule.
It is minutes, not seconds; the recorder's deadline tests and the vehicle are most of it. `live/` is
not in it: it starts containers. The smoke stack `live/stack.py` builds (three agents, their
recorders, the cued stub model in `live/stub_llm.py`, the contract fixture as the window, a dummy
key) is the fastest way to see whether the world still works end to end.

## The scope boundary

**This repository builds everything except the vehicle.** Nothing here models physics or names a
single spacecraft verb. The vehicle lives behind a per-agent directory implemented by someone else;
the only thing the two halves share is `docs/diode-contract.md`, and `contract/fake_diode.py` is a
fixture that satisfies it and models nothing. A request that sounds like "add a thruster command"
belongs on the far side of the window, not here.

`docs/deep_research/` (~16.4k lines) specifies that far side. Don't read it unless the work is on
the contract itself; `docs/deep_research/integration/corpus-review.md` is the map. **The vehicle is
its own repository** (`tachyon-beep/space_vehicle`), vendored here as a git submodule at
`docs/deep_research/vehicle/` so a checkout of the chassis has a vehicle to run; a second vehicle
would be a second submodule beside it. Work on the vehicle belongs in that repository.
`docs/design.md` is the rationale for every decision below, and
`docs/superpowers/specs/2026-10-09-aurora-port-design.md` is the design of the world as it now is;
read them before arguing with one.

## The world: Aurora's harness, one container per agent

Each agent is one container running Aurora's harness, beside its own recorder. The harness is the
agent's: it may rewrite any of it, the watchdog included.

| Where | What | Who owns it |
|---|---|---|
| `harness/` → `/opt/agent` (image) → `/work` | `agent.py`, `chassis.py`, `command_runtime.py`, `watchdog.py`, the prompts: a git repository with `baseline` and `rescue` tags, copied into `/work` at every start | the agent, to rewrite; `/opt/agent` is the seed the container falls back to |
| `/work` | a 1 GiB tmpfs: the harness repository, the saved conversation, `tombstones/` | the agent; lost when the container restarts |
| `HOME=/home/agent` | a 256 MiB tmpfs that does not persist | the agent; empty at every start |
| `/state`, `/pump`, `/build`, `/telemetry`, `/llm/console`, `/diode/<slug>` | that agent's own bounded volume images (`scripts/volume_images.py`) | the agent |
| `/llm/sock` | the agent's recorder's sockets, read-only to the agent | the recorder |
| `/shared` | one image every agent reads and writes | the fleet |
| `pump/pump.py` → `/usr/local/bin/pump.py`; `recorder/` → `/usr/local/lib/recorder/` | the scheduler, and the recorder its own container runs | the operator; outside `/work` |
| `services/` → `/opt/services` | `common`, `health`, `fleet_monitor`, `review`: the operator's monitor and panel | the operator |
| `brief/` → `/opt/brief` | what the agents are told, read-only | the operator (drafts awaiting John: `docs/drafts/`) |
| transcripts, `fleet_ledger`, `operator_telemetry`, `operator/journal/` | the record and the operator's view of it; no agent mounts them | the operator |

`containers/entrypoint.sh` starts the agent's Postgres, NATS and Redis (data under `/state`), the
pump's restart loop, copies the seed into `/work`, and `exec`s the watchdog: when the watchdog dies
the container ends, the restart policy brings it back, and the copy reseeds `/work`.

## The exit-code contract

`harness/chassis.py`'s exits, read by `harness/watchdog.py`'s `plan_recovery`; changing one means
changing the other (both are the agent's to change, together).

| Exit | Meaning | Watchdog's response |
|---|---|---|
| 0 | the loop finished | restart with the same conversation |
| 42 | `done` | archive the conversation; restore `experimental`, else `baseline`, else `rescue`, fresh; sleep 60 s |
| 43 | the harness ended the run as broken | restore with a fresh conversation |
| 44 | the environment refused (a spend cap, an upstream) | pause 60 s plus up to 30 s, same code |
| 45 | `reset` | restore with the conversation kept |
| crash, signal | | climb the ladder |

The ladder: `baseline` with the conversation (`baseline_same`) → `baseline` fresh (`baseline_new`) →
`rescue` fresh (`rescue_new`) → the watchdog exits and the container reseeds from the image. Three
exit-0s inside 120 s count as a fault. Recovery ends after one completed chassis call plus 60 s.
Each step publishes a recovery note to the next run.

## Imports and style

Each Aurora directory imports its modules by bare name and its tests put that directory on
`sys.path` in their own conftest: `import chassis`, `import proxy`, `import pump`.
`tests/conftest.py` puts `services/`, `scripts/` and `contract/` on `sys.path`, so root tests write
`import health`, `import status`, `import fake_diode`. `tests/test_one_suite.py` holds that every
bare name imports from its own directory in the one merged run. `filterwarnings =
["error::DeprecationWarning"]` means any deprecation warning fails the suite.

- `harness/`, `recorder/` and `pump/` are vendored from Aurora at 42faf41 and kept close to it so
  they can be re-synced; `pyproject.toml` excludes their vendored files from ruff.
- The operator-side code (`services/`, `scripts/`) is **standard library only**. Adding a
  dependency to it is a design change, not a convenience.
- Every published file goes through `common.write_json_atomic`; every read of an agent-written file
  is bounded and does not follow a link the agent planted (`health.read_claim`).
- No request header is ever written to the record — bodies only
  (`recorder/tests/test_proxy.py::test_headers_never_reach_the_transcript_or_events`).
- The reasoning lives in module docstrings and comments, which is why `E501` is off. Test names are
  full sentences stating the property under test. Tests never skip: one that needs docker or git
  fails without them.
- `.scratch/` is the gitignored scratch directory; `volumes/` and `volume-images/` are runtime
  artefacts, never source. `tests/test_retired.py` holds the tree free of the runtime the port
  replaced.

## Deliberate non-features — do not "fix" these

- Postgres, NATS and Redis are present, running and **empty**: no schema, no subjects, no roles.
  Deciding what they are for is the mission's first question.
- There is no shared queue, dispatcher, lock service or role table for the fleet, and no ranking in
  the names. Building a control layer is the experiment.
- `done` only clears the context and starts a fresh agent; memory, context management and tooling
  are the agents' to build. A hung or wrong agent is for their own monitoring, the rescue tier and
  the other agents to catch; the operator surfaces only observe.
- `docker-compose.yml` is generated (`scripts/build_compose.py`) and repeats each service's full
  mount list; edit the generator or `scripts/volume_images.py`, never the YAML.
- `agent_2..10` and `recorder_2..10` sit in the `fleet` profile and `diode` in the `diode` profile.
  The monitor and the review panel bind every agent's record, so any `up` needs the full roster's
  volume images.
- Agents join `worknet` (`internal: true`) and nothing else — never `modelnet` or `windowside`.
  That is the one hard rule.
- Fleet names are drawn by `scripts/roster.py` into `.env` as `FLEET_N_SLUG`/`FLEET_N_NAME`, because
  compose reads `.env` with no flags; the roster itself is `operator/roster.json`.
- `vendor/registry/` is gitignored and `prepare_host.sh` refuses without it; rebuild with
  `scripts/build_registry.sh`.

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
