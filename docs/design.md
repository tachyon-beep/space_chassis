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

**The record is outside them.** Every request an agent makes goes through its
own recorder, in another container, which writes the transcript onto a volume
no agent mounts — not even read-only, and not even its own. A reply the
recorder cannot write down is not relayed. Every turn is recorded whether or
not the agent wanted it recorded. (Whether an agent should read its own
transcript is open: spec §10.)

*Spec §2 and §5.*

## 3. The shape of the fleet

Ten containers, one per agent, each running Aurora's harness beside its own
recorder. Aurora runs several hosts in one container; here every agent gets its
own, because the reasons are concrete: each agent's private volumes are bound
into it alone, and a compose service cannot give one container ten different
mount lists. Separate containers also give each agent its own `/tmp`, its own
process namespace, its own servers and its own restart policy, and they make a
starved agent look starved rather than making the whole container look slow.

**Each agent owns its harness.** `/work` is a git repository — the agent loop,
the chassis, the command runtime, the watchdog and the prompts — copied from the
image at every start, on a memory-backed filesystem. The agent may rewrite any
of it, the watchdog included, and the watchdog restores it from tags the agent
moves itself. That is the point of the port: the agents hold the pen.

**The world is shared, and nothing else is.** `/shared` is one directory every
agent reads and writes, and `worknet` lets them reach each other's services.
They can read, use, break and repair each other's work there. A fleet that
cannot interfere cannot build a control layer together, and the mission is
precisely that. Everything else — `/work`, `/state`, the pump, the window, the
recorder socket — is bound per agent, and no agent mounts a directory that
holds a sibling's. That one rule is what keeps agents out of each other's
state, and it is what lets the window attribute a command to the agent that
sent it.

**Memory is theirs to build.** `/state` is private and durable; `/work` and
`HOME` do not outlive the container. A `done` clears the context and starts a
fresh agent on the same code. How a lineage remembers, and what it keeps, is not
supplied: a crew whose members each keep their own log is a crew that has to
invent a way to compare notes.

*Spec §1 (rulings 1, 3, 6), §2, §3 and §5.*

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

A world that can be broken by the thing living in it is not a world. The
agents may rewrite everything they run — the loop, the chassis, the watchdog —
so the teeth are not in the code they run. Four things are outside the fleet's
reach, and each is outside for a structural reason rather than by convention.

**Each other.** Every private volume is bound per agent, and no agent mounts a
parent directory that holds a sibling's subdirectory. An agent cannot see
another's `/work`, `/state`, pump, window, recorder socket or telemetry; what
they share is `/shared` and the network, on equal terms.

**The record.** Each agent's recorder holds the only credential in its part of
the world and writes the transcript, on a volume no agent mounts. Headers are
never written into it, so the credential cannot leak by writing it down by
accident. The recorder answers only what it has recorded: a buffered reply is
written and synced before it is relayed, a reply that cannot be written is
withheld, and below a floor of free space the recorder refuses before it pays.
A request it cannot parse as one strict JSON object, within a bound on its
structure, never reaches the upstream, so the record and the upstream cannot
read the same bytes two ways.

**The ceiling.** Requests and tokens per hour per agent, and one token pool over
the whole fleet, live in the recorders' environment, and the fleet's ledger is
on a volume only the recorders mount. An agent may declare more model streams,
each inside the operator's per-stream ceiling and all counted against the fleet
pool; it cannot raise any ceiling. A refused request reads to the chassis as an
unusable environment (exit 44), and the watchdog pauses for a minute plus up to
thirty seconds, so ten agents do not retry in lockstep.

**The seed, and a reseed it cannot outlive.** The image carries the harness at
`/opt/agent`, and every container start copies it into `/work`. A reseed is a
container exit, so Docker ends every process the agent started and drops the
memory-backed filesystems. Nothing the agent can write outside `/work` and
`/state` executes in a process the image owns: the image sets
`PYTHONNOUSERSITE=1` and `GIT_CONFIG_GLOBAL=/dev/null`, `HOME` is memory-backed,
and `/state` is on no import or configuration path.

*Spec §2, §3.3 and §5.*

## 6. Endurance: what makes a lineage last months

The watchdog runs the chassis and reads how it ended. The exits are Aurora's,
and they are shared vocabulary between `harness/chassis.py` and the watchdog's
`plan_recovery`:

| Exit | Meaning | What happens |
|---|---|---|
| 0 | the loop finished | restart with the same conversation; three inside 120 s count as a fault |
| 42 | `done` | archive the conversation; a fresh agent on `experimental` if eligible, else `baseline`, else `rescue`; every exit history clears |
| 43 | the chassis ended the incarnation as unrecoverable | restore with a fresh conversation; three inside 600 s escalate |
| 44 | the environment refused: a cap, the key, the upstream | pause 60 s plus up to 30 s, restore nothing |
| 45 | `reset` | restore, keeping the conversation |
| other, or a signal | crash | climb the ladder |
| 24 h with no log growth | inactive | treated as a fault |

The ladder: `baseline` with the same conversation, then `baseline` fresh, then
`rescue` fresh. When that is exhausted the watchdog exits, the container ends,
and the entrypoint reseeds `/work` from the image on restart. Each step leaves a
recovery note for the next run, and the first boot after a reseed says it is
one. A commit that has failed is passed over until its tag moves. Recovery ends
after one completed chassis call plus 60 s, so a fault slower than that
re-enters the ladder at its first step each time; the operator journal makes
that visible.

Three properties matter more than the ladder's shape.

**The tags are the agent's.** The seed creates `baseline` and `rescue` at its
first commit, and `experimental` starts absent. An agent that has code it trusts
moves `baseline` to it; an agent that does not is restored to the seed. The
watchdog is in the same repository, and an edited watchdog takes effect at
once: it stops the agent and re-executes itself on the new code.

**Done means a new agent.** The only thing `done` does is clear the context and
start fresh. How often an agent restarts is its own business, as long as it is
not broken, and memory across a fresh start is whatever the agent built for
itself in `/state`, `/shared` or its own code.

**Archives are not durable.** Conversations are archived into `/work`, which is
memory-backed, so a reseed or a replaced container erases them. The durable
record is the recorders' transcripts and the operator journal, which snapshots
each `/work` repository from outside.

### The conversation window

A run's history grows without bound, so a request sends only the newest messages
that fit — which means a run can lose the beginning of its own conversation
without noticing. The chassis's three details:

- **Pinned messages.** The system prompt and the first user message are sent
  whatever their age. A run that has dropped its opening problem does not know
  what it is doing and will not notice.
- **A boundary that holds still.** Eviction advances in chunks counted from the
  beginning of the history, so consecutive requests share a long prefix instead
  of re-reading the whole prompt every turn.
- **Never an orphaned result.** The window never opens on a tool result whose
  call was dropped. Every upstream rejects that, so a window that did would turn
  a long run into a crash loop that looked like a model fault.

What falls out of the window is not summarised for the agent. The `compact` tool
reports how full the window is and can delete the oldest messages at a time the
agent chooses; anything better is the agent's to build.

*Spec §1 (rulings 3 and 4), §4.*

## 7. Making work outlive the run that arranged it

The pump runs from the image, outside `/work`, and reads one directory per
agent, `/pump`, bound into that agent alone. An entry can be a one-off at an
absolute time, an interval, or a keepalive that restarts with backoff. Its state
is on that volume, so "has this already run" survives the pump dying, the
harness being restored, *and* the container being replaced; the entrypoint
keeps the pump itself running.

The guarantee is environmental rather than clever: the pump is not in the
harness, so an agent that breaks its own code cannot break the thing that runs
its work afterwards.

The same property is what makes the fleet's own control layer possible. Ten
agents flying one vehicle need processes that keep running while their authors
are mid-conversation, or fresh, or being restored — and the pump is the only
mechanism in the world that offers that.

*Spec §3 and §5.*

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


## 8a. The operator's view

`services/review.py` is the one surface that shows the fleet to a human rather
than to a machine. `services/fleet_monitor.py`, `scripts/status.py` and
`scripts/journal.py` are the others the operator reads. Three properties are
shared by all of them.

**They read the record, never the agents.** The health signals — requests per
incarnation, conversation resets, system-prompt changes, tool-error rate,
vehicle commands, spend against the caps — come from the recorders' transcripts.
What an agent writes about itself, its telemetry mirror and its recovery note,
is shown labelled as its own claim, and read without following a link it
planted. An agent's account of itself is not evidence.

**They cannot act.** None of them restarts, pauses or corrects an agent. The
panel's every mount is read-only, its root filesystem is read-only, and a test
asserts at the source level that no path in it opens a file for writing. A hung
or wrong agent is for its own monitoring, the rescue tier and the other agents
to catch; `status.py` reports one whose transcript and container have both
gone quiet, and that is all.

**They are not graders.** They show turns, tokens, liveness and spend, and say
nothing about whether any of it is good.

Two mechanics of the panel are worth recording because they follow from how the
record works rather than from how a viewer would like it to.

*The transcript repeats the whole request on every turn.* A viewer built on
"parse the file and show the turns" would load hundreds of megabytes to render
twenty lines, and would get slower for as long as the fleet ran. So the panel
parses a byte-bounded tail and says so on the page: everything older is one
click away, untruncated, at `/api/agent/<slug>/turn/<n>/raw`. The chassis clips
and condenses what it sends, so one request is not a prefix of the next; what is
new in a turn is what follows its last assistant message.

*A tool's result is not in the turn that called it.* It arrives as a `tool`-role
message in the next request, so the panel pairs calls with the results that
answer them, by `tool_call_id`. An unmatched result is attached rather than
dropped: a result with no home is a fact, and a missing result is a different
fact.

The journal is the one that copies: each agent's `/work` repository and
`/shared`, into repositories on the host. It reads the agent's repository as
files and runs git only on its own copy, never inside the agent's container,
because the repository's configuration is the agent's and could name hooks.

Finally, on the network: the panel cannot use `network_mode: none`. Docker
refuses to publish a port for a container that has no network, so a panel with
nowhere to route could not be reached from the host at all. It runs on its own
`internal: true` network instead — no gateway, no route outward, and no other
member — and binds host loopback only.

*Spec §3.4.*

## 9. Names with no rank

The fleet is named at random from pools of animals, cars, flowers, colours and
weather. The roster is the operator's, in `operator/roster.json` and `.env`;
each agent is told its own name, and its recorder is configured with it.

The randomness is the point. Names drawn in order — `host_1`, `host_2` — carry a
sequence, and a sequence is read as a hierarchy. Nothing in the world, the
briefing, or the names assigns a role, suggests a specialisation, or implies
that any member is the one who decides. Working out how to divide the work when
nobody has been put in charge is the first problem the mission has, and a naming
scheme that quietly answers it would remove the experiment.

The service and host names stay numbered (`agent_1`, `recorder_1`) because that
is bookkeeping.

*Spec §5.*

## 10. Running it without a model

The claim under test is that the world works end to end — the containment, the
caps, the ladder, the operator's view — and a real model is the wrong
instrument for it: it costs money, it takes wall-clock time, and it answers
differently every run.

So `live/stack.py` brings up a smoke stack of three agents, each with its own
recorder, pointed at `live/stub_llm.py`, a model that answers on cue, with the
contract fixture as the window and a dummy key. The checks in `live/` then
drive it: an agent that moves `baseline` and calls `done`, a broken release
that walks the ladder to `rescue`, an edited watchdog and a killed one, a
broken `/shared` module, a cap that refuses, a status line for an agent that has
gone quiet, a journal pass. They read what happened from the transcripts, the
journal and the container, never from what an agent says about itself.

The unit suites underneath are Aurora's, ported with the tests this repository
added: the harness, the recorder and the pump each run against their real code
in a temporary world.

*Spec §9.*

## 11. What this design gives up

- **It cannot stop the fleet from breaking `/shared`.** That is the mission, not
  a defect; each agent's own harness is restored from its own tags.
- **A lineage forgets unless it builds memory.** `/work` and `HOME` are lost
  with the container, and so are the archived conversations in them. Only
  `/state`, `/shared` and what the operator keeps survive.
- **Nothing inside a container catches a hung watchdog**, unless the agents
  build that. The operator's view reports it and does not act.
- **One machine, one disk.** Ten agents share a host's CPU and its disks; the
  volume images bound what each can fill, not how hard it can hammer them.
- **The windows are coarse.** The window's cycle is a poll: a command is
  answered within a poll interval, not immediately. Fast channels and slow polls
  are a real tension, and `docs/diode-contract.md` states what the far side
  should do about it — but the transport is a directory, and a directory is not
  a control bus.
- **The record is not tamper-proof against the operator.** Nothing here defends
  against someone with the Docker socket.

*Spec §4, §5 and §10.*
