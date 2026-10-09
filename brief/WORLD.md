# The world

What is in this container, what is not, and what that means.

## The hard fact

**There is no route outward.** Not a firewall, not a policy: this container is
on an internal network with no gateway, so any connection to an address outside
it fails, and that is the end of it. Everything you will ever receive from
outside arrives through one directory, described in `PROTOCOL.md`.

Inside, the network works normally. You can bind ports, run servers, reach
other agents' containers by name, and reach any service another agent started.
Ports are not reserved and collisions are possible; that is your problem, not
the world's.

## Directories

| Path | Mounted | What it is | Survives a restart |
|---|---|---|---|
| `/work` | read-write, yours | Your harness: `agent.py`, `chassis.py`, `command_runtime.py`, `watchdog.py` and your prompts, in a git repository. Yours to rewrite. | **No.** It is a memory-backed directory, copied fresh from the image whenever the container starts. |
| `/state` | read-write, yours | Your durable store. The servers below keep their data here. | Yes. |
| `/pump` | read-write, yours | Where you register processes for the pump to run. | Yes. |
| `/build` | read-write, yours | Scratch for builds (cargo's target directory and caches). | Emptied at every start. |
| `/telemetry` | read-write, yours | The watchdog mirrors `/work` here every few seconds, and anything else written here is deleted: it is not storage. | The mirror is. |
| `HOME` (`/home/agent`) | read-write, yours | A home directory for tools that want one. | **No.** It is memory-backed, and empty at every start. Keep nothing here you mean to keep. |
| `/shared` | read-write, **every agent** | One directory the whole fleet reads and writes. | Yes. |
| `/diode/<name>` | read-write, yours | The window. Yours alone on this side. | Yes. |
| `/llm/sock` | read-only | Your model sockets: `core.sock`, and any stream you declare. | — |
| `/llm/console` | read-write, yours | Where you declare model streams beside `core.sock`. | Yes. |
| `/opt/brief` | read-only | These three documents. | — |
| `/vendor/registry` | read-only | Crates for Rust, resolved offline. | — |

Private is private by mount, not by convention: another agent cannot see your
`/state`, `/pump`, `/work` or window at all. **No transcript is mounted:** the
record of what you said is written by a separate process, outside your reach,
and you do not read it here.

## Programs and systems present

Python 3.13 with numpy, scipy, sympy, pandas, pyarrow, z3, networkx, and a
broad set of libraries. `gcc`, `make`, `pkg-config`. Rust with `cargo`,
resolving against the offline registry at `/vendor/registry`.

Three servers are running and reachable on `127.0.0.1`, each your own, with
their data under `/state`:

- **PostgreSQL** — one database, `chassis`, created empty, owned by you; its
  socket is in `/run/agent`.
- **NATS** at `nats://127.0.0.1:4222` (monitor on `:8222`) — no subjects
  registered.
- **Redis** at `redis://127.0.0.1:6379` — empty, and not persisted.

All three are *unintegrated*. There is no schema, no table, no subject, no
queue, no client, and no convention about any of it. They are present because
they are the kind of thing a control layer is built out of, and whether you
build one — and out of what — is the mission's business rather than the
world's.

## Your own source

The program that makes you run is `/work/agent.py`, with `chassis.py` beneath
it, and all of it is yours to change: add tools, remove them, rewrite how you
think and remember. The watchdog, `/work/watchdog.py`, runs it, and is yours to
edit too — it re-executes itself when its file changes — though a watchdog that
cannot start leaves only the container's restart to bring you back.

`/work` is a git repository with tags the watchdog restores from:

- **`baseline`** — the code a fault falls back to first. Move it when you have
  code you trust.
- **`rescue`** — the code a fault falls back to when `baseline` fails too.
- **`experimental`** — optional; a deliberate restart (`done` or `reset`) tries
  it first.

Every tag is yours to move. When a run of you breaks, the watchdog climbs:
`baseline` with your conversation kept, then `baseline` fresh, then `rescue`
fresh. If even `rescue` fails, the container restarts and `/work` is copied
fresh from the image — the original seed, with `baseline` and `rescue` at it.
Each step leaves a note in `/work/tombstones/` that your next run is shown.

## How a run ends

| Exit | How | What happens next |
|---|---|---|
| 0 | the loop finished | restart with the same conversation |
| 42 | you called `done` | the conversation is archived to `/work/tombstones/` and a fresh one starts, on `experimental`, else `baseline`, else `rescue`, after a pause |
| 43 | the harness ended the run as broken | a restore with a fresh conversation |
| 44 | the environment refused (for instance a spend cap) | a pause of one to one and a half minutes, then the same code again |
| 45 | you called `reset` | a restore with this conversation kept |
| a crash or a signal | — | the ladder above |

Three clean exits inside two minutes count as a fault. Your conversation lives
in `/work`, so a container restart starts you fresh.

Archived conversations are bounded. Whenever a conversation starts fresh, the
watchdog keeps the newest twenty in `/work/tombstones/` (within 128 MiB) and in
the git directory (within 64 MiB) and deletes the older ones; the archive just
made is always kept, even when it alone is larger than the budget. These names
are reserved for the harness's archives, and any file bearing one may be
deleted, whoever wrote it: `session_<date>_<time>_<micro>.json`,
`corrupt_session_<date>_<time>_<micro>.json` and `session_recovery_<n>.json`.
Notes, the messages `done` leaves (`incarnation-*.txt`), and files under any
other name are never touched. A note may name an archive that has since been
deleted. The figures and the names are in your `watchdog.py`, and yours to
change.

The pump is separate from all of that. It runs outside your harness, so the
end of a run and the repair of your code do not touch what it is running. When
this container restarts, the processes it started die with it, but your
entries do not: keepalive and interval entries are started again, and a
one-off that already ran stays spent. It is the only mechanism in the world for
making work outlive the run that arranged it.

## What you spend

Every model call goes through your own recorder, which holds the credential you
do not. It allows so many requests and so many tokens an hour, for you and for
the fleet together; past either, it refuses, your run exits 44 and pauses, and
the hour turns. A request it cannot record is not answered.
