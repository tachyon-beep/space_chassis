# This window

You are talking to one spacecraft through one directory. This file is the protocol: what the files here are, what a reading *means*, what a refusal means, and what this vehicle does not publish. It is generated from the vehicle's own configuration, so it cannot describe a window that is not the one you are reading.

## The files

| file | direction | what it is |
|---|---|---|
| `console.json` | you → vehicle | your commands, and the variables you may set |
| `state.json` | vehicle → you | the mirror: what is available, what is open, what is left in the allowance |
| `HELP.md` | vehicle → you | every verb you may use, with its gates and its arguments |
| `README.md` | vehicle → you | this file |
| `telemetry/NNN.json` | vehicle → you | a ring of recent frames |
| `output/<stamp>_<slug>_<cmd>.txt` | vehicle → you | one result per submitted command |
| `pending.json` | vehicle → vehicle | the vehicle's own queue. Not yours to read or write |

The telemetry is a **ring**, not a snapshot, and it is bounded to a fixed number of slots: when it is full the oldest frame is dropped and the loss is counted. `state.json`'s `ring` key states the bound, what is held, and what has been lost, so a gap in what you can see is never a mystery.

## What a reading means

Every published value carries a layer and a quality code, and the two answer different questions: the layer says *what the number is about*, and the code says *how much to trust the instrument that produced it*.

| layer | means | what it is |
|---|---|---|
| **A** — authoritative | `measurement` | what the instrument reports |
| **I** — inferred | `estimate` | what the vehicle concluded |
| **A** — service | `service` | what the vehicle did |

**Truth is never published.** A value is what an instrument reported, what the vehicle concluded, or what the vehicle did — never the simulation's own state.

**A commanded state is not a sensor.** A `service` value reports what the vehicle did, not what an instrument read.

## The shape of a command cycle

1. **claim** — the console is read and emptied **before** anything runs.
2. **validate** — schema, authority, phase, gate, interlock and freshness, in that order.
3. **act** — at most one command per conflict domain per tick, first valid wins.
4. **publish** — `state.json` and `HELP.md` rewritten, one frame appended to the ring.

A command that cannot be attempted is not an error and not a silence: it produces exactly one result file, of the same shape as a success, whose text says what refused it and why.

## What a refusal means

| code | meaning |
|---|---|
| `REJECTED` | the batch or the command did not survive validation: schema, authority or phase |
| `PHASE` | the verb is not available in the mission phase the vehicle is in |
| `GATE` | an agent-writable gate variable is closed; the variable is named in `state.json` |
| `INTERLOCK` | a service-owned condition blocks the verb; no console variable can move it |
| `CONFLICT_SUPERSEDED` | a later command replaced this one before it took effect |
| `STALE_STATE` | the evidence the command depends on was older than its maximum decision age |
| `EXPIRED` | the command's queue age exceeded its `maximum_queue_age_s` before effect |
| `INHIBITED` | the vehicle is in a state that inhibits effectful verbs |
| `INDETERMINATE` | the vehicle restarted with the effect unproven; the journal is the record |

## How often this vehicle speaks

148 channels are published across 5 cadence classes. The class a channel is in is a statement about how fast the quantity moves, and it is why a frame's `values` map does not have the same members twice: a frame carries the values whose period has elapsed, so an absent slow channel is a cadence rather than a dropout.

| class | rule | channels |
|---|---|---|
| `fast` | rate_hz >= 5 | 21 |
| `control` | 1 <= rate_hz < 5 | 85 |
| `slow` | 0.5 <= rate_hz < 1 | 8 |
| `resource` | 0 < rate_hz < 0.5 | 30 |
| `event` | rate_hz == 0 | 4 |

Every frame carries 13 envelope fields besides the values: `schema`, `seq`, `boot_id`, `sim_step`, `met_s`, `sensor_time_s`, `publish_time_s`, `state_revision`, `vehicle`, `phase`, `values`, `quality`, `injected`.

## What this vehicle does not tell you

Some quantities are deliberately withheld, and saying so is part of the protocol: **38 named channels** and **0 described categories** are not published. A quantity that is missing from a frame is either one of those or a channel that could not be computed this tick — never a value the vehicle declined to guess.

The mirror is bounded: 24.

---

The vehicle writes this file from its own configuration. Editing it by hand changes nothing that survives the next cycle.
