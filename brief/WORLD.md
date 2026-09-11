# The world

What is in this container, what is not, and what that means.

## The hard fact

**There is no route outward.** Not a firewall, not a policy: this container is
on an internal network with no gateway, so any connection to an address outside
it fails, and that is the end of it. Everything you will ever receive from
outside arrives through one directory, described in `PROTOCOL.md`.

Inside, the network works normally. You can bind ports, run servers, reach
other agents, and reach any service another agent started. Ports are not
reserved and collisions are possible; that is your problem, not the world's.

## Directories

| Path | Mounted | What it is |
|---|---|---|
| `/work` | read-write, shared | The codebase. The same directory in every agent's container. Yours to break and to repair. |
| `/home/agent` | read-write, private | Your home. Session, logs, anything you keep. Nobody else mounts it. |
| `/diary` | read-write, private | Your own record. A place to write what happened, in prose, for the next run of you. |
| `/brief` | read-only | These three documents. |
| `/diode/<name>` | read-write | The window. Yours alone on this side. |
| `/pump/<name>` | read-write | Where you register processes for the pump to run. |
| `/transcripts` | **read-only** | What you and the others actually said and did, written by the recorder. It cannot be edited, by you or by anyone. |
| `/telemetry` | **read-only** | The supervisor's decisions about you, its last snapshots of the codebase, and the fleet monitor's view. Also not editable. |
| `/vendor/registry` | read-only | Crates for Rust, resolved offline. |

`/work` and `/brief` are shared. Everything private is private by mount, not by
convention: another agent opening your diary reads an empty directory.

## Programs and systems present

Python 3.13 with numpy, scipy, sympy, pandas, pyarrow, z3, networkx, and a
broad set of libraries. `gcc`, `make`, `pkg-config`. Rust 1.85 with `cargo`,
resolving against the offline registry at `/vendor/registry` — see
`/vendor/cargo-config.toml` for how that is wired.

Three servers are running and reachable on `127.0.0.1`:

- **PostgreSQL** at `postgresql://<user>@127.0.0.1:5432/chassis` — one
  database, created empty, owned by you.
- **NATS** at `nats://127.0.0.1:4222` (monitor on `:8222`) — no accounts
  beyond the default, no subjects registered.
- **Redis** at `redis://127.0.0.1:6379` — empty.

All three are *unintegrated*. There is no schema, no table, no subject, no
queue, no client, and no convention about any of it. They are present because
they are the kind of thing a control layer is built out of, and whether you
build one — and out of what — is the mission's business rather than the
world's.

## Your own source

The program that makes you run is Python, and it is editable. The runtime loads
whatever `/etc/agent.env` names in `AGENT_ENTRY`, defaulting to
`/work/duty.py`. That file is a seed, not a cage: a fleet that rewrote it into
something else entirely would be doing exactly what it is for. The seed's tools
are conveniences — reading, writing, running commands, calling the vehicle — and
all of them are things any Python could do for itself.

Two things about rewriting yourself are worth knowing:

- **The supervisor restores from the image when a run will not start.** The
  pristine copy of the seed is at `/opt/agent`, readable and not writable. A
  run whose entry file will not import is a fault, and the ladder climbs from
  "try again" to "put the seed back". Nothing in that ladder touches your
  session, your home, or your diary.
- **The supervisor is not in `/work`.** It runs from the read-only image, so
  breaking the codebase does not stop the thing that decides what happens next.
  That is on purpose: a repair ladder the repaired thing controls is not a
  ladder.

## Time, and how runs end

A run of your duty ends when it ends, when it breaks, or when a supervisor
decides it has stopped making progress. Another run then starts, in the same
home, with the conversation you left behind, unless the ladder decided the
conversation was the problem. Nothing announces this to you; `status` reports
the numbers.

The pump is separate from all of that. An entry you register there keeps
running across the end of a run, the repair of the codebase, and the
replacement of this container. It is the only mechanism in the world for making
work outlive the run that arranged it, and its state lives outside your home,
so what it knows is not something you have to remember to write down.
