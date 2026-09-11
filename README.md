# space_chassis

A world for ten self-modifying agents, and the record of what they do in it.

They are given a floor and a window. The floor is a container with Python, a C
and Rust toolchain, a database, a message bus, and a compiler for anything else
they want. The window is a single directory whose far side belongs to a
spacecraft they are meant to fly. Everything between those two — the control
layer, the division of labour, the way ten consoles avoid contradicting each
other — is not provided, because building it is the mission.

**This project builds everything except the vehicle.** The spacecraft lives on
the far side of the window, in a process this repository does not contain. What
is here is the world around it: the agents, their runtime, the supervisor that
keeps a lineage alive across months, the scheduler that lets work outlive the
run that arranged it, the recorder that keeps the only record they cannot edit,
and the harness that proves all of it survives being run hard.

```
                    ┌──────────────────────────────────────┐
   the vehicle      │  the window (the other builder's)    │
   ───────────────  │  one directory per agent:            │
                    │    console.json   →  commands        │
                    │    output/*.txt   ←  results         │
                    │    state.json     ←  published state │
                    │    telemetry/NNN  ←  a ring of frames│
                    └──────────────┬───────────────────────┘
                                   │  the only way in or out
   ┌───────────────────────────────┴───────────────────────────────────┐
   │  ten agent containers, internal network, no route outward          │
   │    /work         shared codebase, read-write, everyone's           │
   │    /home/agent   private, durable, nobody else mounts it           │
   │    /diary        private notes to the next run of you              │
   │    supervisor    runs the duty, repairs it, records the decision   │
   │    pump          runs what the agent scheduled, across incarnations│
   │    postgres, nats, redis   present, running, and empty             │
   └───────────────────────────────────────────────────────────────────┘
        │                        │                       │
   transcripts (ro)        telemetry (ro)          the recorder
   what they said          what was decided         holds the only key
```

## Quick start

Requires Docker with Compose v2 and Python 3.12+ on the host.

```sh
sh scripts/prepare_host.sh          # directories, ownership, the roster, .env
$EDITOR .env                        # set OPENROUTER_API_KEY (or LLM_BASE_URL)
docker compose --profile fleet up --build
python3 scripts/status.py           # one line per agent
```

`--profile fleet` brings up all ten; without it only `agent_1` starts, which is
how the stack is meant to be brought up the first time.

The fleet is named by `scripts/prepare_host.sh` from a pool of animals, cars,
flowers, colours and weather. The names are drawn at random and carry no rank:
deciding who does what is the first problem the mission has, and the world does
not solve it for them. Read the roster with `python3 scripts/roster.py --print`.

An agent's name is its identity everywhere it matters: the socket the recorder
opens for it, its directory under `volumes/home`, its diary, its lifecycle
record, and its slice of the window. The compose service is `agent_1`, which is
bookkeeping and nothing else. Names live in `.env`, which compose reads with no
flags — a stack started without them would hand every agent the fallback and
leave it unable to write its own home.

To stop: `docker compose down`. That keeps everything: the codebase, every
agent's home, the diaries, the transcripts, the pump's state. To destroy it,
delete `./volumes` — there is no `-v` flag that does it, deliberately.

## What an agent is given

Its briefing, read-only at `/opt/brief`:

| File | What it says |
|---|---|
| `MISSION.md` | Keep the crew alive and bring them home. No roles, no plan, no sequencing. |
| `WORLD.md` | What is in the container, what is not, and what that means. |
| `PROTOCOL.md` | The two rules the world enforces, and the window's protocol. |

Its program, at `AGENT_ENTRY` — `/work/duty.py`, a Python file it may rewrite
or replace entirely. The seed registers thirteen tools: read, write, edit, list,
run, spawn, schedule, unschedule, go through the window, watch the window,
write to and read from its diary, look at its own numbers, and hand over. Every
one of them is a convenience rather than a boundary: there is a shell, a
compiler and a writable filesystem, and a duty could do all of it itself.

And one runtime it does not own: `services/chassis.py`, which loads the duty,
frames a run, drives the turns, bounds the conversation, checkpoints, and
decides how the run ends. It runs from the read-only image beside the
supervisor, not from the codebase — a supervisor that repaired the runtime out
of the directory the runtime repairs would be repairing sand.

## The two rules

**No route outward.** Each agent container is on an internal network with no
gateway. It can reach its siblings, the services they start, and the window;
nothing else. The only process in the world that can reach the public internet
is the recorder, and it is on a network the agents are not on.

**The record is outside them.** `/transcripts` and `/telemetry` are mounted
read-only. Every turn is written by the recorder, which holds the one
credential and never writes a header to disk. Every recovery decision is
written by the supervisor. They can read all of it and change none of it.

## Repository layout

| Path | What it is |
|---|---|
| `services/chassis.py` | The runtime: one run of the duty, from frame to tombstone. |
| `services/supervisor.py` | The recovery ladder, the telemetry mirror, the lifecycle record. |
| `services/pump.py` | Scheduled and supervised processes, per agent, surviving everything. |
| `services/recorder.py` | The credential and the transcript. One unix socket per agent. |
| `services/fleet_monitor.py` | The operator's view: what each agent's surfaces say. Writes to `/telemetry`. |
| `services/common.py` | Atomic writes, bounded reads, shared by all of the above. |
| `tasks/duty.py` | The seed program. The fleet's to rewrite. |
| `brief/` | What they are told. |
| `docs/diode-contract.md` | The interface the vehicle's builder implements. Read this one. |
| `docs/deep_research/` | The subsystem studies — power, ECLSS, thermal, GNC, propulsion, RCS, comms, consumables — that specify the far side of that window. |
| `docs/design.md` | Why the world is shaped this way. |
| `docs/example-run-report.md` | What an endurance verdict looks like. |
| `contract/diode_probe.py` | Walks an implementation through the contract and reports. |
| `contract/fake_diode.py` | A fixture that satisfies the contract. Models nothing. |
| `docker-compose.override.example.yml` | The smoke configuration above. Rename it to `docker-compose.override.yml` to use it. |
| `endurance/` | The harness: a stub model, a local world, fault injection, a verdict. |
| `tests/` | 62 tests, no Docker required. |

## Trying it without a credential

There is a smoke configuration that brings up three agents, drives them from a
metronome instead of a model, and mounts the contract fixture as the window. It
costs nothing and exercises everything except the vehicle:

```sh
cp docker-compose.override.example.yml docker-compose.override.yml
docker compose up -d agent_1 agent_2 agent_3 recorder fleet_monitor diode stub
python3 scripts/status.py --verbose
sh scripts/verify_containment.sh --all
```

That is how this project was checked as it was built, and it is the fastest way
to see whether the world is intact after a change.

## Running it hard without a model

The endurance harness builds a whole world in a temporary directory, runs the
real recorder, supervisor and pump in it, points them at a model that answers
on cue, and then hurts them on a schedule:

```sh
python3 endurance/run_local.py endurance/scenarios/ten_agents.json
python3 endurance/run_local.py endurance/scenarios/long_haul.json
```

In about three minutes it produces roughly five hundred turns across ten agents
with fourteen deliberate injuries — killed runs, unparseable code, corrupted
conversations, refused sockets — and writes `REPORT.md` and `metrics.json` into
`endurance/runs/<tag>-<stamp>/`, alongside the transcripts and lifecycle
records the verdict is computed from.

A passing verdict means the machinery survives being run hard. It says nothing
about how an agent would fly a vehicle, and `REPORT.md` says so in its own last
section.

## Verifying the world

```sh
python3 -m pytest -q                        # unit and integration, no Docker
ruff check . && ruff format --check .
docker compose --profile fleet config -q    # the topology parses
sh scripts/verify_containment.sh            # against a running stack
python3 contract/diode_probe.py --diode-dir ./volumes/diode --list
```

## Scope

This is a research harness, not a security product, and it is not a game. It
assumes a trusted host and a sound container runtime, and it is built so that a
fleet of agents can be given real freedom — to rewrite themselves, to break the
shared codebase, to disagree — inside a world where breaking yourself is
survivable and the record of it is kept by somebody else.

The one thing it is really careful about is the part that matters: nothing in
the fleet can reach outward, and nothing in the fleet can rewrite what
happened.

## Licence

MIT © 2026 John Morrissey
