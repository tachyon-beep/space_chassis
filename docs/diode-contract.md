# The curtain

What this project builds, what it deliberately does not, and the interface
between them.

---

## 1. The division

This project builds **everything except the vehicle**: the fleet, the world they
live in, the record of what they do, the machinery that keeps a lineage alive
across months, the harness that proves it, and this document.

It does not build the diode — the process on the far side of the window. That is
where the spacecraft lives: its physics, its hidden state, its sensors, its
verbs, its alarms, its failures. Nothing in this repository models a vehicle,
and nothing here knows a single verb of the one that will be mounted.

The interface between the two halves is one directory per agent. Everything
below is the contract for that directory, and it is written to be implemented
without reference to anything else in this repository. `contract/fake_diode.py`
is a fixture that satisfies it and models nothing.

## 2. The shape

For each agent, named `slug`:

```
<DIODE_DIR>/<slug>/console.json          agent  -> vehicle   (the only uplink)
<DIODE_DIR>/<slug>/output/<result>.txt   vehicle -> agent    (one file per command)
<DIODE_DIR>/<slug>/state.json            vehicle -> agent    (published every cycle)
<DIODE_DIR>/<slug>/HELP.md               vehicle -> agent    (verbs currently open)
<DIODE_DIR>/<slug>/README.md             vehicle -> agent    (the protocol, in the vehicle's words)
<DIODE_DIR>/<slug>/telemetry/NNN.json    vehicle -> agent    (a ring of recent frames)
<DIODE_DIR>/<slug>/pending.json          vehicle -> vehicle  (the vehicle's own deferral queue)
```

Both sides mount the volume. The vehicle's process and its credentials are not
in the agents' containers and are not reachable from them.

### 2.1 Why one ingress file per agent

A single shared `console.json` for ten writers is a lost-update race: two agents
read it, both rewrite it, one batch vanishes, and the record cannot say whose it
was. Per-agent ingress costs one directory and buys two things the experiment
needs — reliable transport, and attribution that comes from the operating system
rather than from a field an agent could write.

Consolidating the ten ingresses into the vehicle's own command queue is the
vehicle's business. The agents are given no shared queue, no bus, no lock
service and no convention for using one; if the fleet wants a dispatcher, that
is a thing for the fleet to build, and the fact that they built it should be
visible in their work rather than supplied by the world.

### 2.2 `console.json` — the uplink

```json
{
  "commands": ["<verb> <argument>", "<verb> <argument>"],
  "variables": {"<gate>": true, "allowance": 4}
}
```

- `commands` is a list of lines: a verb, a space, its arguments.
- `variables` is a flat map of gate settings the vehicle chooses to honour.
  Persistent — the vehicle never clears it.
- **Intake is destructive and atomic.** Each cycle the vehicle reads the file,
  then rewrites it with `commands` emptied and `variables` preserved, through a
  temporary file and a rename. A command therefore takes effect **at most once**,
  even if the vehicle dies mid-cycle: the batch was already claimed.
- **Clear before you act.** The claim happens before any command runs. A crash
  mid-batch loses the rest of that batch; it never replays it.
- **One malformed element refuses the whole batch.** If any element of
  `commands` is not a string, none of it runs, and exactly one result file
  records that. Partial execution of a malformed batch is worse than none.
- A batch written while a cycle is in progress is not claimed by that cycle.
  It runs on the next one.
- An agent writing the file in place rather than replacing it may be read
  half-written. Refusing is correct; the result file says so.

### 2.3 `output/` — the downlink

Every command produces exactly one file, whether it succeeded, was refused for
an unopened gate, hit an allowance, or raised inside the vehicle:

```
<UTC stamp>_<slug>_<sanitised command>.txt
20260912T021345_123456Z_otter_diode_set_mode_standby.txt
```

- The stamp is UTC with microseconds, so ordering is total and filenames sort
  chronologically.
- The command text travels in the filename with every non-alphanumeric character
  replaced by an underscore and the whole truncated at 160 **bytes**, so no
  separator, traversal sequence, or partial multi-byte character can reach the
  filesystem.
- The body is plain UTF-8 text. Binary artifacts are written with an extension
  that says what they are and are never executed by the vehicle.
- **Nothing overwrites anything.** Results accumulate. `output/` is append-only
  and the agents clean it up if they want it cleaned.
- **A refusal is a result.** Unavailable verb, allowance exhausted, bad
  argument, internal error: one file each, same shape. The agent must read the
  content; the shape tells it nothing.

There is no callback, no subscription, and no wait. An agent submits and reads
later. A command that takes longer than one cycle — a burn, a deploy, a
self-test — completes asynchronously and reports when it is done.

### 2.4 `state.json` — the mirror

Rewritten every cycle whether or not anything was submitted. Suggested keys:

```json
{
  "published_at": "<UTC ISO-8601>",
  "available_commands": ["..."],
  "variables": {"...": true},
  "budget": {"used_this_window": 3, "limit_per_window": 120,
             "window_seconds": 3600, "oldest_expires_in_seconds": 2880},
  "queue_depth": 2,
  "vehicle": {"phase": "...", "mode": "..."}
}
```

**Published state is never read back as input.** Editing it changes nothing:
an allowance does not return because a file says it did.

Name the two budget fields so a single number cannot be mistaken for the limit.
An agent that reads `used: 1` as "one operation per hour" and propagates it to
its siblings has done nothing wrong; the surface invited the error.

## 3. Authority

- **Closed vocabulary.** Verbs are names with arguments. Never code, never
  paths, never URLs, never a program. Every reachable effect was written
  deliberately by whoever built the vehicle.
- **Gates are published.** Every verb's gate variable appears in `HELP.md` and
  `state.json`, so a verb that is closed is a door with a label rather than a
  dead end. A hidden verb is the deliberate exception and must be **inert**:
  text only, no egress, no spend, no state change — hidden verbs bypass gate
  evaluation by construction, so they must be safe ungated.
- **The allowance is `min(agent, operator)`.** A variable may lower what is
  permitted and may never raise it. Every ceiling that matters lives in the
  vehicle's own environment.
- **Authority is re-evaluated at the moment of effect.** A command deferred at
  one moment and executed at another is checked again at execution: gates,
  interlocks, allowances and phase. Nothing is captured at scheduling time.
  This is the single most important property in the whole interface.
- **The vehicle holds the abort.** Safing, thermal cutouts, structural limits
  and the protective envelope are the vehicle's own and are reachable from no
  file the agents can write. Not because the agents are hostile, but because a
  vehicle that can be fully commanded from inside has no floor beneath a
  confused command.

## 4. Commands

- **Declarative over imperative.** `set_mode standby` must be safe to repeat.
  `increment_x` is not: a run that lost an acknowledgement cannot tell whether
  it already applied, and cannot recover by re-asserting.
- **Idempotent where the physics allows.** At-most-once intake protects against
  duplicate *submission*; it does not protect against a crash between effect and
  result file, where the agent genuinely cannot know whether the command landed.
  Declarative shape is what makes that recoverable.
- **Mark irreversibility, in the verb's shape if possible.** A verb that cannot
  be undone should say so — in its documentation, and in its arguments. A verb
  exposing only `enable: true` and no inverse *is* a claim that no inverse
  exists, and it will be read that way. Genuinely one-way actions deserve a
  two-step arm/commit so that a single misread line cannot fire them.
- **The parameter shape is documentation.** It will be read as carefully as the
  prose, and it should agree with the prose.

## 5. Telemetry

- **Physics runs on its own clock.** The vehicle is not reactive: it drifts,
  heats, drains, tumbles and fails whether or not anyone asked. Continuous
  physics at tens of hertz is plenty; the interesting coupling is thermal,
  electrical and consumable, and those are slower than that.
- **Publication has a cadence, and it varies.** Fast channels (rates, voltages,
  chamber pressure) want a few hertz; engineering channels a fraction of that;
  consumables and slow thermal trends want a tenth of that. The distinction
  between "fast control variable" and "slow resource trend" is the one the
  agents need in order to plan rather than react.
- **Publish a ring, not a snapshot.** An agent that was blocked inside one long
  conversation turn wakes up blind if all it has is the latest frame: it cannot
  distinguish a stall from a shut-down, or a trend from a transient. A bonded
  ring of recent frames with a fixed slot count is self-describing about its own
  cadence and its own losses — and it teaches the agents to reason about missed
  frames, which is the correct epistemology for telemetry.
- **Burst around events.** Raise the rate around burns and faults for a bounded
  window. The interesting failures are transients, and a slow rate turns them
  into a step change that looks like nothing happened.

### 5.1 Three epistemic layers

Every published field is one of three things, and the agents should be able to
tell which:

| Layer | Meaning | Published as |
|---|---|---|
| **A — authoritative** | What the instrument reports. Authoritative *about the report*, not about the world. It may be wrong, drifting, saturated, stuck, or lying about a fault. | The reading, with its unit and precision |
| **I — inferred** | Derived from one or more readings, or from a model. May be wrong without any sensor having failed. | The estimate, marked as an estimate, with its inputs visible |
| **T — truth** | The simulation's actual state | **Never.** Not in any file |

Consequences worth stating plainly:

- **Failures are information problems.** A credible crisis does not publish
  `oxygen_tank_exploded: true`. It publishes a current spike, a brief dropout, an
  off-scale reading, a falling pressure, a bus undervoltage, a rising load — and
  leaves the agents to assemble the diagnosis before the cascade outruns their
  organisation.
- **Do not publish a diagnosis the vehicle would not have.** `pump_state:
  "stalled"` is a conclusion. `commanded: true`, `current: high`, `flow: ~0` is
  evidence, and it is what the crew would have had.
- **Inferred quantities are where plans are made and where they die.**
  Remaining propellant, state vectors, time-to-limit, absorber breakthrough:
  publish the measurements they rest on, and mark the estimate as an estimate.

## 6. Determinism, restarts, and the vehicle's own state

- The vehicle's process may restart. Nothing an agent has already submitted
  should run twice because of that (see the claim in §2.2), and nothing already
  executed should be forgotten: the vehicle's journal and its published state
  are its own to keep, and the operator's ceiling counters should survive a
  restart rather than refilling.
- A command's identity is its text. Two identical lines in one batch are two
  commands; the same line in two batches is two commands.
- Time is UTC everywhere, and the stamp in a result filename is the vehicle's
  clock, not the agent's.

## 7. What the subsystem research adds

`docs/deep_research/` carries eight subsystem studies — power, ECLSS, thermal,
GNC, propulsion, RCS, communications, consumables — written after this contract
was first drafted. They converge, independently, on a stronger interface than the
one above for anything that moves physical hardware:

| The studies recommend | Why it matters to this side of the wall |
|---|---|
| **Typed command objects** rather than free-form `"<verb> <argument>"` strings | Range checking, versioning, deterministic parsing, and authority are all impossible to state about a line of text |
| **Per-principal ingress**, merged service-side, with the service stamping the identity | Already the shape here: one directory per agent. The studies reach the same conclusion from the lost-update direction, and confirm that attribution must come from the transport rather than from a field an agent writes |
| **A command lifecycle**: submitted → validated → armed → committed → effective → superseded, each with a record | A request that produced one file at the end cannot express *when* it became effective, which a burn needs |
| **Anti-replay**: a monotonic sequence per principal, plus an idempotency key | At-most-once intake covers a restart mid-batch. It does not cover a command replayed later by an agent that never learned whether it landed |
| **Explicit authority levels**, with a safety authority (S0) no command can reach | The agent's claim about its own authority must not be the authority |
| **Telemetry metadata per value**: sample time, quality flags, provenance, uncertainty, range, and direct-versus-estimated | A number without an age is a number an agent will reason about as if it were now |
| **Multi-rate bounded history plus event streams**, not a latest-value mirror | Already stated here; the studies add that the rates must be explicit and the history bounded by construction |
| **All interlocks service-owned**; agent-writable variables must never gate life-protection | This supersedes the gate-variable pattern for physical verbs. A gate variable is a preference; an interlock is not a preference |

None of that changes anything in this repository, because this repository does
not implement the eye. Three things about the fleet's side are worth stating
anyway, since they are what let the stronger contract be implemented without
touching the world:

1. **The result filename is a forward-compatible record.** The studies' command
   lifecycle wants a correlation id, a state, and an effect time. This contract
   fixes the stamp, the agent's name, and the command text, and says nothing
   about what may follow. An implementation that appends a correlation id and a
   lifecycle state is conforming: a reader that wants the fields it knows can
   take them, and one that wants only the command can still read the command.
2. **`variables` is not where interlocks live.** An implementation whose
   protective envelope is agent-writable has implemented the envelope as a
   preference. The world hands over a writable `variables` map because a
   convoy needs to be able to ask for less, never for more.
3. **The console is the fleet's only hand, and it is per agent.** If a vehicle
   ever wants commands from a principal that is not an agent — a ground
   operator, a safety authority — that principal needs its own ingress
   directory, not a share of an agent's.

The studies are the reference for the eye. This document is the reference for
the wall, and the two are meant to be read together.

## 8. What the agents are told

They are told the shape above and nothing about the vocabulary. `HELP.md`,
`state.json` and `README.md` are the vehicle's documentation of itself, written
in whatever voice the vehicle's builder chooses, and they are the only place a
verb name can appear. Nothing in this repository names a verb, and nothing in
the fleet's briefing describes the mission's systems.

## 9. Checking conformance

`contract/diode_probe.py` walks an implementation through the properties that
can be checked mechanically:

1. a submitted batch is claimed, and the console is left with `variables`
   preserved and `commands` empty;
2. every command in a batch produces exactly one result file, refusals included;
3. a non-string element refuses the whole batch and runs none of it;
4. an unknown verb is refused by name;
5. a closed gate is refused by name, and its variable is published;
6. a hidden verb produces text and no wider effect;
7. `state.json` is not read back: corrupting it changes nothing;
8. an allowance may be lowered by the console and never raised;
9. a deferred command is re-checked when it is due, not when it was scheduled;
10. `output/` grows and never overwrites;
11. a result filename carries no separator or traversal sequence;
12. telemetry advances on its own, and a frame exists for a period when nothing
    was submitted.

Run it against a candidate implementation before trusting it:

```sh
python3 contract/diode_probe.py --diode-dir ./volumes/diode --slug otter --timeout 120
```
