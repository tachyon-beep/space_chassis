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
is here is the world around it: each agent's own harness, which it may rewrite
from end to end; the watchdog that restores it from checkpoints when a rewrite
breaks it; the scheduler that lets work outlive the run that arranged it; the
recorder that keeps the only record they cannot reach; and the operator's view
of all of it.

The harness is Aurora's, ported: the agent
loop, the chassis, the watchdog and its three checkpoint tiers come across
unchanged, and Aurora's entertainments are replaced by a lunar mission.

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
   │  ten agent containers on an internal network, no route outward     │
   │    /work         its own harness, a git repository; memory-backed  │
   │    /state        its own durable store, and the servers' data      │
   │    /shared       one directory the whole fleet reads and writes    │
   │    watchdog      runs the harness, restores it from its tags       │
   │    pump          runs what the agent scheduled, across restarts    │
   │    postgres, nats, redis   present, running, and empty             │
   └───────────────────────────────┬───────────────────────────────────┘
                                   │  a unix socket, one per agent
   ┌───────────────────────────────┴───────────────────────────────────┐
   │  ten recorders: the only key, the spend caps, the transcripts      │
   │  — on volumes no agent mounts                                      │
   └───────────────────────────────────────────────────────────────────┘
```

## Quick start

Requires Docker with Compose v2 and Python 3.12+ on the host, and root once, to
mount the volume images.

```sh
sh scripts/build_registry.sh        # once: the offline crate registry, vendor/registry (gitignored)
sh scripts/prepare_host.sh          # the roster, .env, and the bounded volume images
$EDITOR .env                        # set OPENROUTER_API_KEY (or LLM_BASE_URL)
python3 scripts/volume_images.py check
docker compose --profile fleet up --build
python3 scripts/status.py           # one line per agent
```

The vehicle runs from an image of its own, the only one that carries it: no agent's image holds any
of it. (Until the vehicle adoption lands, the pinned vehicle still writes the run's scenario and seed
into each agent's window; see `governance/chassis/open.md`.) A bare `docker compose build`, or
`up --build`, skips the profiled vehicle: build it by name with
`docker compose --profile vehicle build vehicle` before starting it, and again after any change to it.
Rebuilding the agents' image no longer rebuilds the vehicle's.

Every volume an agent or a recorder writes is a preallocated ext4 image,
loop-mounted under `volumes/`, so a full disk is one image's problem and never
the host's or the record's. `prepare_host.sh` plans and creates the images and
never runs `sudo` itself: what needs root it prints as one block of commands,
followed by the `/etc/fstab` lines that mount them at boot. It exits 2 until
there is nothing left for the operator to do.

`--profile fleet` brings up all ten agents and their recorders; without it only
`agent_1` and `recorder_1` start, beside the monitor and the review panel. The
monitor and the panel read every agent's record, so every `up` needs all ten
agents' images mounted.

The fleet is named by `scripts/prepare_host.sh` from a pool of animals, cars,
flowers, colours and weather. The names are drawn at random and carry no rank:
deciding who does what is the first problem the mission has, and the world does
not solve it for them. Read the roster with `python3 scripts/roster.py --print`;
it lives in `operator/roster.json` and, as `FLEET_N_SLUG`/`FLEET_N_NAME`, in
`.env`, which compose reads with no flags.

An agent's name is its identity everywhere it matters: its volumes, its
recorder and transcript, and its slice of the window. The compose service and
host name `agent_1` are bookkeeping and nothing else.

## Reading what an agent did

`http://127.0.0.1:8090` is a read-only panel over the record. Per agent it shows
the conversation turn by turn: what the model said, its reasoning when it
returned any, every tool call with the arguments it was given and the result
that came back, and the tokens each turn cost. Beside that it shows the
monitor's view — whether the agent is active, capped, idle, or stale, its
incarnations, and its spend against the caps — all derived from the recorder's
transcripts. What the agent writes about itself, such as its recovery note, is
shown labelled as the agent's own claim.

It reads; it cannot write. It is on its own internal network with no gateway and
binds host loopback only, because a panel that can read everything an agent
thought should not appear on a network by accident. There is a JSON API behind
it (`/api/fleet`, `/api/agent/<slug>`, `/api/agent/<slug>/turn/<n>/raw`) for
anything that would rather not scrape a page, and `scripts/status.py` remains
the one-line-per-agent view for a terminal.

A transcript records the whole request on every turn, so the files grow fast,
and the panel therefore parses a bounded tail of each file rather than the whole
of it. Each turn in that window is served untruncated in its raw form; anything
older is read from the transcript on the host. A tool's *result*
is not in the turn that called it: it arrives in the next request, so the panel
pairs them by id.

`scripts/journal.py` keeps the other half of the record: periodic snapshots of
each agent's `/work` repository (its commits, branches and tags) and of
`/shared`, with container restart counts and the watchdog's exit lines, in
`operator/journal/`. `/work` is memory-backed and lost when a container is
replaced, so the journal is how a reseed or a moved tag is attributable after
the fact. It never runs git inside an agent's container.

To stop: `docker compose down`. That keeps `/state`, `/pump`, `/shared`, the
window and every transcript; each agent's `/work` and `HOME` are memory-backed
and start again from the image. Nothing in compose deletes the record: the
volumes are bind mounts of loop-mounted images, and removing them is a host
operation.

## What an agent is given

Its briefing, read-only at `/opt/brief`:

| File | What it says |
|---|---|
| `MISSION.md` | Keep the crew alive and bring them home. No roles, no plan, no sequencing. |
| `WORLD.md` | What is in the container, what is not, and what that means. |
| `PROTOCOL.md` | The rules the world enforces, and the window's protocol. |

`docs/brief-claims.md` lists every claim the brief and the prompts make about
the world, and the code or test that makes it true.

Its harness, at `/work`: a git repository holding `agent.py`, `chassis.py`,
`command_runtime.py`, `watchdog.py` and the prompts, copied from the image at
every start. All of it is the agent's to rewrite, the watchdog included. The
seed registers eleven tools: Aurora's eight (`read_file`, `write_file`,
`validate`, `migrate`, `done`, `reset`, `list_dir`, `compact`) and a mission kit
of three (`read_path` and `write_path` anywhere the agent can see, and `run`, a
bounded command runner, through which it has git). Every one of them is a
convenience rather than a boundary: there is a shell, a compiler and a writable
filesystem.

The watchdog restores the harness from git tags the agent moves itself:
`baseline`, `rescue`, and an optional `experimental`. `done` archives the
conversation and starts a fresh agent; a fault climbs from `baseline` with the
conversation kept, to `baseline` fresh, to `rescue` fresh, and past that the
container ends and reseeds `/work` from the image.

## The two rules

**No route outward.** Each agent container is on an internal network with no
gateway. It can reach its siblings, the services they start, and the window;
nothing else. The only processes in the world that can reach the public
internet are the recorders, on a network the agents are not on.

**The record is outside them.** Every request is written by the agent's own
recorder, which holds the one credential and never writes a header to disk, onto
a volume no agent mounts. A reply the recorder cannot record is not relayed. No
agent can read or change any transcript, its own included.

## Repository layout

| Path | What it is |
|---|---|
| `harness/` | Aurora's agent, chassis, command runtime, watchdog and prompts: the seed at `/opt/agent`. |
| `recorder/` | The credential, the transcript and the spend caps. One recorder per agent, one unix socket each. |
| `pump/` | Scheduled and kept-alive processes, per agent. The schedule survives every restart; a process does not outlive its container, and keepalives are started again. |
| `services/` | The operator's view: `health.py`, `fleet_monitor.py`, `review.py`, and `common.py` (atomic writes, bounded reads). |
| `containers/` | The agent's entrypoint, and the vehicle service's. |
| `brief/` | What they are told. |
| `scripts/` | Host preparation, the roster, the volume images, the compose generator, status, the journal, containment checks. |
| `live/` | The smoke stack and the checks that run against it. |
| `docs/diode-contract.md` | The interface the vehicle's builder implements. Read this one. |
| `docs/deep_research/` | The vehicle study (`apollo_diode.md`) and the eleven subsystem studies — power, ECLSS, thermal, GNC, propulsion, RCS, comms, consumables, avionics, structural/sequential events, crew C&W — that specify the far side of that window. `integration/corpus-review.md` says what is in them. |
| `docs/deep_research/vehicle/` | **The vehicle itself, as a git submodule** of [`tachyon-beep/space_vehicle`](https://github.com/tachyon-beep/space_vehicle): its configuration, its reference plant, its linter and its referee. `git submodule update --init` after cloning; a second vehicle would be a second submodule beside it. |
| `docs/design.md` | Why the world is shaped this way. |
| `docs/superpowers/specs/2026-10-09-aurora-port-design.md` | The design of the port: what came from Aurora, what was kept, what was retired. |
| `contract/diode_probe.py` | Walks an implementation through the contract and reports. |
| `contract/fake_diode.py` | A fixture that satisfies the contract. Models nothing. |
| `tests/` | The operator-side tests and the assertions about this repository's own files. One `pytest` also runs the harness, recorder and pump suites and the vehicle's referee. No Docker required. |

## Trying it without a credential

The smoke stack brings up three agents and their recorders, answers them from a
stub model that replies on cue instead of a real one, and mounts the contract
fixture as the window, on scratch directories with a dummy key and its own
compose project. It costs nothing and exercises everything except the vehicle:

```sh
python3 -m pytest live -q
```

It builds the image, runs the containment and acceptance checks against the
running stack — no route out, the binds, the caps, a `done`, a reseed — and
tears it down. It takes a few minutes, and it is the fastest way to see whether
the world is intact after a change.

## Verifying the world

```sh
python3 -m pytest -q -n 8                   # every suite; no containers
uvx ruff check . --no-cache && uvx ruff format --check . --no-cache
docker compose --profile fleet config -q    # the topology parses
sh scripts/verify_containment.sh --all      # against a running stack
python3 contract/diode_probe.py --diode-dir ./volumes/diode/data --list
```

## Scope

This is a research harness, not a security product, and it is not a game. It
assumes a trusted host and a sound container runtime, and it is built so that a
fleet of agents can be given real freedom — to rewrite themselves, to break the
shared directory, to disagree — inside a world where breaking yourself is
survivable and the record of it is kept by somebody else.

The one thing it is really careful about is the part that matters: nothing in
the fleet can reach outward, and nothing in the fleet can rewrite what
happened.

## Licence

MIT © 2026 John Morrissey
