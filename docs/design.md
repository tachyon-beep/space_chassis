# Design

Why this world is shaped the way it is, and what each decision costs.

---

## 1. What this project is, and what it is not

It is the world around ten agents who are meant to fly a spacecraft, and the
record of what they do in it.

It is **not** the spacecraft. The vehicle lives on the far side of a directory
whose other side belongs to whoever builds it — physics, sensors, verbs, alarms,
failures, and the abort authority. Nothing in this repository models a vehicle,
and nothing here names a single verb. The interface between the two halves is
`docs/diode-contract.md`, and it is the only thing the two halves share.

That division is deliberate rather than incidental. The world's job is to make a
long experiment possible: ten agents that can rewrite themselves, a record they
cannot edit, recovery that survives them breaking things, and a way to run the
whole thing hard without a real model in the loop.

## 2. The physics of the world

Four rules. Everything else is a consequence.

**No route outward.** Each agent container is on an internal network with no
gateway. The hard rule the operator set, and it is the only one: nothing in the
fleet can reach the public internet, and everything the fleet receives arrives
through the window.

**The image is the floor, not the cage.** The container carries Python, a C and
Rust toolchain, a database and a bus — the things you cannot bootstrap from
nothing. Everything above that, the agents build. Nothing is pre-run for them:
Postgres is present with one empty database and no schema, NATS is present with
no subjects, Redis is empty. Deciding what any of it is *for* is the first real
question the mission has to answer, and the world refuses to answer it.

**Time and compute are real.** No simulation clock, no privileged accelerators,
a fixed CPU and memory budget per agent. The fleet is on one machine, and what
it cannot do in a turn it cannot do.

**The record is outside them.** Transcripts and lifecycle records are written by
processes in other containers, onto volumes the agents mount read-only. Every
turn is recorded whether or not the agent wanted it recorded.

## 3. The shape of the fleet

Ten containers, one per agent, rather than Aurora's one container holding
several hosts. The reasons are concrete: an agent needs its own writable
`/home` and its own `/diary`, and a named volume cannot carry a variable in its
name, so ten private homes in one container would need ten hand-written mount
lists anyway. Separate containers also give each agent its own `/tmp`, its own
process namespace, and its own restart policy, and they make a starved agent
look starved rather than making the whole container look slow.

Two consequences are accepted rather than solved:

- **The codebase is shared and read-write.** One volume, mounted into every
  agent. They can read, use, break and repair each other's work. A fleet that
  cannot interfere cannot build a control layer together, and the mission is
  precisely that. The recovery ladder is what makes the interference survivable.
- **Memory is private.** Each agent's home and diary are mounted into it alone.
  This is not containment — the shared codebase is wide open — it is *shape*: a
  crew whose members each keep their own log is a crew that has to invent a way
  to compare notes.

## 4. What is given, and what that is not

The image carries a broad Python stack (numerics, ephemerides, data handling,
drivers for the database and the bus), `gcc`/`make`, Rust 1.85 with an offline
crate registry, `psql`, `nats-server`, `redis-server`, and the usual Unix
tooling. That list is a decision about *capability*.

Every additional thing would have been a decision about *design*: a schema is a
claim about what matters, a subject name is a claim about who talks to whom, and
a service already running is a claim about what the fleet should be doing. So
the servers run and hold nothing, and the drivers are installed but unused.

The agents are told all of this in `brief/WORLD.md`, in the same voice: here is
what exists, here is what is empty, and here is why it is empty.

## 5. Where the teeth are

A world that can be broken by the thing living in it is not a world. Three
things are therefore outside the fleet's reach, and each is outside for a
structural reason rather than by convention.

**The runtime.** `chassis.py` loads the duty, frames a run, drives the turns and
decides how it ends. It lives in the read-only image beside the supervisor, not
in the codebase. The codebase gets a readable copy so a fleet can see how it is
driven, and the copy is never executed: a supervisor that repaired the runtime
out of the directory the runtime repairs would be repairing sand. (This is not
hypothetical. An earlier revision of this project ran the runtime from the
codebase, and the ladder's "restore the codebase" rung could not fix a broken
runtime because the runtime *was* the thing being checked.)

**The record.** The recorder holds the only credential in the world and writes
the transcript. The agents mount that volume read-only. Headers are never read
into it, so the credential cannot leak by writing it down by accident.

**The ceiling.** Every allowance — requests and tokens per hour per agent, one
pool over the whole fleet — lives in the recorder's environment. An agent may
lower its own allowance and never raise it.

## 6. Endurance: what makes a run last months

A run of a duty ends for one of five reasons, and the reason decides what the
next run is given. That map is the whole of `services/supervisor.py`:

| Exit | Meaning | What happens |
|---|---|---|
| 0 | ended cleanly | resume |
| 42 | ended on purpose, usually with a handoff | resume, and the note opens the next run |
| 43 | the run's own fault | climb the ladder |
| 44 | the environment is unusable | wait, retry unchanged |
| other, or a signal | crash | climb the ladder |
| alive, no progress | wedged | kill it, then climb the ladder |

The ladder, counted over a decaying window: **1** resume, **2** restore the duty
from the image, **3** restore the whole seed codebase, **4** give up and let the
container's restart policy decide.

Two properties matter more than the ladder's shape.

**Memory survives every rung.** Neither repair touches `/home` or `/diary`. The
difference between "a bad edit cost one run" and "a bad edit cost everything the
lineage had learnt" is the entire reason to have a supervisor rather than a
restart policy, and it is one line of code in each repair.

**A designed end carries the conversation.** A run that hits its turn budget
exits 42, not 0 and not 43. A budget is not a fault, and treating it as one
would have the ladder climbing on a fleet that was merely busy — and eventually
resetting the conversation of a lineage that was working perfectly. This was
found by a test, not by reasoning: the first version reset a busy agent.

### The conversation window

The window is the subtle part of endurance. A run's history grows without bound,
so a request sends only the newest messages that fit — which means a run can
lose the beginning of its own conversation without noticing. Three details:

- **Pinned messages.** The system prompt and the first user message are sent
  whatever their age. A run that has dropped its opening problem does not know
  what it is doing and will not notice.
- **A recap of what was dropped.** Evicted messages are recorded, in the order
  they left, into a recap that is pinned into every request. It is lossy and it
  says so. A long run can then see the shape of what it no longer has.
- **A boundary that holds still.** Eviction advances in chunks counted from the
  beginning of the history, so consecutive requests share a long prefix instead
  of re-reading the whole prompt every turn. The first version computed the
  boundary from the live start, which made it constant, which made the window
  creep one message per turn. A test caught it; the numbers are in
  `tests/test_chassis.py`.

The window never opens on a tool result whose call was dropped. Every upstream
rejects that, so a window that did would turn a long run into a crash loop that
looked like a model fault.

## 7. Making work outlive the run that arranged it

The pump runs from the read-only image and reads one file per agent. An entry
can be a one-off at an absolute time, an interval, or a keepalive that restarts
with backoff. Its state is on its own volume, so "has this already run" survives
the pump dying *and* the container being replaced.

The guarantee is environmental rather than clever: the pump is outside the
codebase, so a duty that breaks its own code cannot break the thing that runs
its work afterwards.

The same property is what makes the fleet's own control layer possible. Ten
agents flying one vehicle need processes that keep running while their authors
are mid-conversation, or dead, or being repaired — and the pump is the only
mechanism in the world that offers that.

## 8. Ten consoles, one vehicle

The window gives each agent its own ingress file. That is a deliberate choice
against a shared `console.json`, and the reason is not security:

- **A shared file loses updates.** Two agents read it, both rewrite it, and one
  batch vanishes. Whatever the vehicle does about that is the vehicle's
  business, but the *transport* should not be the source of the loss.
- **Attribution should come from the operating system.** Per-agent directories
  mean the vehicle knows who asked without trusting a field in a file. The
  research this project was briefed against recommended this explicitly, and it
  is right.
- **Consolidating the ten ingresses is the vehicle's job.** No shared queue, no
  bus, no lock service, no convention: if the fleet wants a dispatcher, that is
  a thing for the fleet to build, and the fact that they built it should be
  visible in their work rather than supplied by the world.

The deconfliction problem — two agents asking the vehicle for contradictory
things in the same minute — is therefore *theirs*. The world will relay the
consequences and nothing else. That is not a gap in the design; a crew that
flies a good trajectory into a contradiction has failed, and the world is built
so that this failure is visible in the record rather than hidden by a
convenience.

## 9. Names with no rank

The fleet is named at random from pools of animals, cars, flowers, colours and
weather, and the names are published in `/work/roster.json` so every agent can
name every other.

The randomness is the point. Names drawn in order — `host_1`, `host_2` — carry a
sequence, and a sequence is read as a hierarchy. Nothing in the world, the
briefing, or the roster assigns a role, suggests a specialisation, or implies
that any member is the one who decides. Working out how to divide the work when
nobody has been put in charge is the first problem the mission has, and a naming
scheme that quietly answers it would remove the experiment.

The service and volume identifiers stay numbered (`agent_1`, `home_1`) because
that is bookkeeping, and the briefing says so.

## 10. The endurance harness

The claim under test is that the machinery survives being run hard, and the
harness exists because that claim cannot be checked any other way. A real model
is the wrong instrument: it costs money, it takes wall-clock time, and it
answers differently every run.

So the harness builds a complete world in a temporary directory, runs the *real*
recorder, supervisor and pump in it against a model that answers on cue, and
then hurts the fleet on a schedule: kills a running chassis, writes a duty entry
that cannot be parsed, corrupts a saved conversation, makes the recorder refuse
one agent for twenty seconds, and serves transient, malformed and missing-model
responses at fixed intervals.

Two properties of the harness are deliberate:

- **It only inflicts injuries the world claims to survive.** Anything
  unrecoverable would make the run meaningless, so nothing here deletes memory
  or the record.
- **It reads the record to decide, never the agents.** Turns come from the
  recorder's transcript; recoveries from the supervisor's lifecycle record;
  the fault schedule from a journal. Nothing asks an agent how it did, because
  an agent's account of itself is not evidence — and because a report built from
  agent-writable files would be a report the fleet could write for itself.

The scenario file declares what passing means, and the verdict is a list of
named checks with the numbers behind them. `REPORT.md` ends with a section
saying what the run does *not* show, because a metronome is not a model.

## 11. What this design gives up

- **It cannot stop the fleet from breaking the shared codebase.** That is the
  mission, not a defect; the ladder bounds the damage to one run.
- **One machine, one disk.** Ten agents share a host's CPU and a bind-mounted
  volume. A fleet that hammers the volume will slow itself down.
- **The windows are coarse.** The window's cycle is a poll: a command is
  answered within a poll interval, not immediately. Fast channels and slow polls
  are a real tension, and `docs/diode-contract.md` states what the far side
  should do about it — but the transport is a directory, and a directory is not
  a control bus.
- **The record is not tamper-proof against the operator.** Nothing here defends
  against someone with the Docker socket.
