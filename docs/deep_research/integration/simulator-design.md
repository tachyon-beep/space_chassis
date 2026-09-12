# Vehicle simulator — design in progress

**Status:** sections 1–8 drafted (1–6 approved, 7–8 pending review). Sections 9–13 not yet written.
**Specs landed:** apollo, electrical, eclss, gnc, main_propulsion, rcs, communications, thermal, consumables, crew.

**Process:** `superpowers:brainstorming`, architectural path — sections presented and
approved one at a time. On completion the full design goes to subagent review
(`yzmir-systems-thinking`, `bravos-simulation-tactics:simulation-architect`,
`yzmir-simulation-foundations:stability-analyst`,
`axiom-determinism-and-replay:determinism-reviewer`,
`axiom-solution-architect:solution-design-reviewer`) before any implementation plan.

---

## 1. What is being built

A spacecraft simulator: the far side of the window. Ten LLM agents fly it through
`docs/diode-contract.md`. A white team (LLM + human operator) can inject faults and
drive scenarios, but **the baseline is hands-off** — with no white-team input the
plant simulates health, components meet spec, hazard rates are low but nonzero, and a
competently flown mission lands. The white team is a perturbation layer, not a driver;
a run with zero white-team input is a valid run.

See `README.md` in this folder for the two standing rules on reading the research docs
(apollo is ground truth; the dual-diode material is inapplicable).

### Established context

- The diode is **emulated as a sibling container** sharing a volume — not hardware.
  `~/aurora/` runs this pattern: `diode.py` + `Dockerfile.diode` on the `egress`
  network, agent container with no network interface, credentials and ceilings only in
  the diode service's environment.
- `diode-contract.md` descends directly from Aurora's `diode.py` (`console.json`,
  `state.json`, `HELP.md`, `output/`, `consume_batch()`, gates-as-`variables`,
  `min(agent, operator)` ceiling) and generalises it from one console to one directory
  per agent.
- `communications_diode.md` is the one spec that would *change* the contract rather
  than extend it (demotes `output/*.txt`, splits `/diode` into two mounts, criticises
  `consume_batch()` by name). Aurora runs that mechanism successfully — decline it.

---

## 2. Decisions taken

| Decision | Value |
|---|---|
| Location | **Separate repo.** Only inbound dependency is a frozen copy of `diode-contract.md`; `diode_probe.py` runs against it in CI. `space_chassis` keeps `fake_diode` for smoke and endurance, and its README stays true. |
| White-team baseline | Hands-off. A nominal run needs no input. |
| Uplink | **Per-agent `console.json`, full verb set on every console.** Transport decision, not an authority partition — see §3.0. |
| Conflict policy | apollo's only: first valid command in a conflict domain wins for that tick; later ones get a refusal result they must read. Nothing smarter — `design.md` §8 makes deconfliction the fleet's problem. |
| Determinism | Load-bearing from the first commit. Class and tier in §3.2. |
| Reasoning cost | **Not imposed.** The clock's indifference is the mechanism — see §3.8. |

---

## 3. Sections 1–3

### 3.0 The six pieces

1. **The dictionary.** One versioned machine-readable vehicle definition: every
   telemetry point (id, unit, range, precision, rate, quality semantics, provenance
   class, A/I/T layer), every verb (args schema, gate, authority, interlocks, conflict
   domain, irreversibility), and component topology. Not a doc — the artifact the
   plant, publisher, probe and white-team console all read. Makes incoming specs *data
   entry* rather than eight codebases.

2. **The plant.** Fixed-step integrator, per-behaviour resource invariants, lumped
   per-domain models, coupling as a declared graph. Owns hidden truth. Advances on its
   own clock whether or not anyone is thinking.

3. **The instruments.** Truth → evidence. Noise, bias random-walk, quantisation,
   saturation, stuck, dropout, lag; quality codes assigned only when a real diagnostic
   would catch it. **Hard layer boundary**, or the A/I/T distinction leaks and the
   epistemic premise goes with it. *(Fidelity in §4, crew in §5; the noise/bias/quality
   layer proper is §7, not yet designed.)*

4. **The executive.** Vehicle-side authority: intake per contract §2.2, closed
   vocabulary, gates, `min(agent, operator)` allowance, deferral re-checked at the
   moment of effect, interlocks, an abort agents cannot reach.

5. **The window.** Contract-conformant publisher, one directory per agent. Already
   specified and already tested — `diode_probe.py` walks twelve properties and
   `fake_diode.py` passes them. The simulator is structurally `fake_diode` with a
   vehicle behind it.

6. **The white-team plane.** A separate channel agents cannot see or write: fault
   injection, scenario and time control, truth inspection, researcher metrics.
   Researcher observability and agent observability are different design questions, so
   it is a different surface — not a privileged verb set on the same one.

**On per-agent ingress and roles.** Ten *identical* consoles, not one panel cut into
ten slices. Every console accepts the full verb set; the vehicle neither knows nor
cares who "owns" a subsystem. Per-agent directories buy reliable delivery (ten writers
on one file lose batches the vehicle cannot even report) and OS-level attribution (the
record says *which* agent asked, not which agent claimed to). Nothing is delegated;
any notion of ownership is the fleet's to build. What collides is therefore intent,
not bytes — and a losing command gets a refusal it must read to discover.

**Gates are per-console; vehicle state is vehicle-wide.** `min(agent, operator)` lets
an agent lower its own allowance or close a verb to itself. Arming an engine is a
*command with a vehicle-wide effect*, never a per-console variable — otherwise one
agent's variable becomes a shared mutable control surface and hands the fleet a
coordination mechanism through the back door.

**Irreversible actions.** With every console able to command everything, one-way
actions (staging, pyros, jettison) are protected by shape rather than by role: two-step
arm/commit, the arm returning a short-lived token bound to a specific action, commit
requiring the matching token and re-checking at the moment of effect. Two agents racing
it produce a refusal, not a double-fire.

#### Build order

Dictionary + linter → **spike on electrical → thermal → consumables** → instruments →
executive → window (green on `diode_probe.py`) → white-team plane → remaining domains
→ mission profile.

---

### 3.1 The vehicle definition

Each subsystem spec is written about one domain in isolation, so none can supply a
cross-domain value. Mass is the canonical case: GNC needs it for inertia and Δv,
propulsion for depletion, consumables for propellant-as-resource-and-mass, structure
for loads — and it changes across the mission. Same for inertia tensor, CoM,
configuration/staging state, mission phase, MET epoch, crew size and metabolic rates,
coordinate frames.

```
vehicle.yaml          globals — mass, inertia, CoM, configuration/staging, frames
mission.yaml          profile — phases, durations, crew, MET epoch, targets
coupling.yaml         the cross-domain graph: what feeds, heats, loads, drains what
domains/<name>/       components · points · profiles · commands · fault_policy
scenarios/<name>.yaml seed, hazard rates, fault schedule
```

Five files per domain, matching `thermal`'s factoring, so an incoming spec lands as
five files and the linter says whether it composed. **`coupling.yaml` is the one
nothing supplies** — apollo has that graph as a mermaid diagram, and turning it into
data is most of what integration means here.

**The linter.** `thermal` specifies it; generalise it to the whole vehicle. Refuse a
build on: a safety-critical zone missing limits or freshness bounds, duplicate point
IDs, dimensional-unit mismatches, inverted hysteresis, direct commands aimed at passive
hardware, unresolved actuator dependencies, any normal verb able to override an `S0`
interlock.

**Key property: a value that is needed and unset fails the build, loudly, naming what
wants it.** (`thermal`'s `UNCONFIGURED ≠ nominal`, generalised.) You do not enumerate
what the simulator needs up front — you add a domain, run the linter, and it tells you
what you now owe it. The config is a conversation with the linter, not a form.

**Provenance.** No spec asks for it; add it anyway. Every value that matters records
whether it is apollo-anchored, a spec default, or chosen to make the thing run. When a
run goes strangely you want to know in one grep whether the driving value was anchored
or invented. Required on values the linter classes safety-critical or
experiment-affecting.

**Also liftable from `thermal`:** the typed thermal graph; passive hardware as
observable objects with no command interface; paired heat/cool thresholds with minimum
dwell mandatory for regulated zones.

---

### 3.2 The core: a stepped environment with adapters

The core is `step(commands) → state` and knows nothing about files. Three adapters sit
on it: the diode file surface, the white-team console, and — optionally — a DRL
harness. **The Effects boundary is the adapter seam.** Every external input crosses one
line instead of being scattered through twelve domains; tests drive the core directly
at thousands of ticks per second.

Build only the diode adapter, but design the seam now. The cost of not doing it is that
the file layer grows tendrils into the plant and the core stops being steppable.

### 3.3 Determinism class and tier

> **Two runs are equivalent iff, for the same seed and the same recorded input trace,
> every per-tick state hash is byte-identical — same build, same platform.**

Why not logical-equivalence-within-ε: this system is full of latched thresholds
(a pump trips below 24.5 V held for 300 ms) inside feedback loops. An ε difference
flips a comparator one tick early, which flips a discrete state, which changes the
cascade. No ε survives a comparator.

**Tier M**, with a forced promotion for external effects. Assumes same-machine replay,
since the fleet is one host. If a run recorded here must later reproduce bit-identically
in CI, that is tier L and adds a floating-point policy (pinned BLAS, fixed reduction
order, FMA and denormal flags) — one artifact, addable later, not a re-architecture.

### 3.4 Seeds and RNG

One `master_seed` in the run config, recorded as a run **input**, not a log line. Every
stream derives by name: `(master_seed, domain, component_id, purpose)`.

Name-keying is the operationally important part. Twelve domains arrive incrementally
over months. With a shared generator — or index-keyed derivation — adding thruster 9
reshuffles every existing stream and silently invalidates every prior run. Name-keyed
means **adding a component is not class-breaking**.

### 3.5 The Effects layer

Three external inputs, all through one path: the **wall clock** (via the time
multiplier), the **agent consoles**, and **white-team actions**.

- Live mode: the clock drives ticks.
- Replay mode: the recorded trace drives, every input keyed **by tick index, not wall
  time**.

Without tick-keying, the number of ticks between two agent commands depends on machine
load and no two runs match. With it, an eight-day mission replays in minutes, because
nothing waits for anything.

**Time multiplier:** `1 s sim = x s wall`, both directions — stretch during a burn so
agents can react, compress through coast. It is an Effect and goes through this layer.

### 3.6 Snapshots and divergence

A **compare-point at every tick**: a hash over canonically-encoded state. Full snapshot
at phase boundaries, deltas between. Localisation is binary search over tick hashes to
the first differing tick, then structured comparison inside it.

This converts "the run went strangely" from archaeology into a bisect. For a white team
deliberately perturbing a system with feedback loops, it is not optional.

### 3.7 Plant mechanics

**Domains do not call each other.** Each is a pure function over a state snapshot,
declaring what it reads and writes; `coupling.yaml` declares the edges. The scheduler
snapshots at *t*, every domain computes from that snapshot, all writes commit at
*t+dt*.

If domains call each other directly the coupling goes invisible within a week and "why
did the amplifier overheat" becomes archaeology. As declared data the graph is lintable
for undeclared reads, renderable, and **feedback loops are explicit** — cycles must be
declared with a named one-tick delay; acyclic edges resolve in topological order within
the tick.

**Rate:** single-rate 50 Hz (matching apollo), each domain declaring its natural rate in
config but the scheduler ignoring that for now. Thermal and consumables have time
constants in minutes to hours and are absurd to integrate at 50 Hz, so multi-rate is the
obvious optimisation — but it is an optimisation. Design the interface so rates *can*
split; do not build the machinery until a profiler says to.

**Resource invariants are per-behaviour**, from `consumables`' seven kinds. **Stocks**
conserve exactly (fixed-point mantissa + exponent + unit code, so eight days of 50 Hz
ticks accumulates no drift); **buffers** check occupancy bounds; **rates** balance
instantaneously; **margins** only check that they derive from live inputs. A universal
conservation assertion applied to thermal margin is a category error.

**The ledger publishes as a pair with the observation**, never reconciled silently.
`Δ_recon = observed − ledger` is evidence — it is how a slow leak first becomes
visible, and hiding it deletes the exact inference the experiment exists to observe.

**Declined from `consumables`:** the claims lifecycle
(`FREE → RESERVED → ALLOCATED → COMMITTED`). Exposing reservations as verbs hands the
fleet a ready-made deconfliction primitive, which `design.md` §8 withholds
deliberately. The vehicle may use claims internally; it must not publish them.

### 3.8 Reasoning cost is not imposed

Sim time advances on the multiplier regardless of whether anyone is thinking, so the
cost of reasoning is already real: a specialist who thinks for ten minutes of wall time
has spent *x* seconds of mission during which the vehicle drifted, drained and heated.
The contract already says "nothing waits for you"; apollo already says the crisis should
worsen while the organisation debates. **The clock's indifference is the mechanism.**

An explicit reasoning-budget verb would supply the answer — agents would manage a
budget rather than discover that someone has to decide who thinks hard about what.
Leave the clock indifferent and triage becomes worth inventing, which is the behaviour
worth observing and only counts as a finding if they built it.

A second economy already exists unremarked: ten agents share one host's CPU and the
recorder's per-agent request and token ceilings.

**For measurability:** the run record stamps each command with the tick it landed on
*and* the tick its author last read state at. The gap is decision latency in mission
time, and it is what shows afterwards whether a triage structure emerged and whether it
helped.

### 3.9 The spike

Electrical → thermal → consumables, driving apollo's degraded chain: amplifier on → bus
load step → voltage sag → marginal pump → coolant flow falls → coldplate ΔT climbs →
amplifier temperature rises. Plus the fuel cell, because O₂ + H₂ → power + water + heat
ties consumables to both neighbours at once.

Exercises a declared feedback cycle, a conserved stock with production, a slow constant
beside a fast one, three inferred quantities (load margin, SOC, time-to-limit) — and now
also the Effects boundary, tick-hash compare-points, and byte-identical replay of a
recorded run. If replay does not hold at three domains it will not hold at twelve, and
every run recorded before the fix is worthless.

---

## 4. Section 4 — the fidelity ladder

### The criterion

The `bravos-simulation-tactics` pack is built on scrutiny-based LOD, and scrutiny
transfers unusually well here: the observer is an LLM reading a named channel at a
stated rate and precision, so **the point dictionary is the scrutiny model**. A
judgement call becomes a lookup.

What does *not* transfer is the pack's foundation — "players experience their
perception of the simulation," therefore use cognitive tricks, theater of the mind,
temporal aliasing. The agents are not an audience being convinced; they are instruments
performing inference, and whether their inferences were correct **is the experimental
result**. A trick that looks plausible while being inconsistent does not cost
immersion, it corrupts the finding: an agent reasoning correctly from evidence reaches
a wrong conclusion, and we record an agent failure that was ours.

> **Simulate a quantity to the fidelity at which an agent reasoning correctly from
> published evidence reaches a correct conclusion. Fake only what cannot change any
> published value, or any inference correctly drawn from one.**

Testable rather than aesthetic: for any candidate fake, ask whether any published
channel or derivable quantity differs.

### The clause games do not need

The pack's economy is "fake what isn't observed" — off-screen NPCs don't affect
on-screen ones. **In a coupled spacecraft the unobserved feeds the observed.** A faked
thermal mass still drives a published coldplate temperature.

So fidelity is set by the *transitive closure* of observability through
`coupling.yaml`: everything published, plus everything feeding something published, to
the depth at which its contribution stays below published precision. The coupling graph
earns its keep twice — it is what makes the LOD decision computable.

### The ladder

apollo's, adopted per the standing rule:

| Fidelity | Domains |
|---|---|
| **High** | Vehicle dynamics (6-DOF, finite-duration thrust, mass depletion); guidance and state estimation; electrical network; consumables; **sensors and instrumentation** |
| **High-medium** | Propulsion (tank/feed/valve states, thrust response; no combustion chemistry); ECLSS atmosphere (lumped gas masses, leak, absorber capacity) |
| **Medium-high** | Thermal (lumped RC network plus coolant flow); communications (geometry, pointing, link budget) |
| **Medium** | Avionics (state machines, compute margin — not AGC emulation); structure (pressure vessel, latches, staging — not FEM) |
| **Low / omitted** | Crew *physiology*. ECLSS needs metabolic O₂/CO₂ as rates, which is an input, not a model of a person. |

Sensors sitting at High is the ladder agreeing that the instrument layer is the product.

Refinement the ladder predates: "consumables: High" decomposes across
`consumables`' seven behaviours — stocks are genuinely high-fidelity, entitlements and
opportunities are bookkeeping.

**Statistical/aggregate simulation is legitimate exactly where the real instrument
aggregates too**: battery cells (publish pack voltage with `cell_min_v`/`cell_max_v`,
not 200 cells), absorber bed chemistry, thruster pulse accounting. That is modelling
the sensor honestly, not hiding a shortcut.

---

## 5. Section 5 — crew as an instrument

Physiology is out; **the crew are a sensor**, and judged as one they are the most
interesting sensor on the vehicle.

| | Instrument | Crew |
|---|---|---|
| Precision | quantified, 0.05 V | "cold", "loud", "a bit off" |
| Latency | sample-to-publish, bounded | whenever they notice, or mention it |
| Failure mode | noise, bias, saturation, dropout | forgot, misheard, misattributed, wrong module |
| Coverage | exactly the channels that exist | **anything at all** |

The last row is the one that matters. A bang is on no channel; neither is a smell, a
vibration, frost on a panel, a hiss. Every instrument reports only what it was built to
report. The crew are the only sensor that can report an *unanticipated* observation.

So crew move from Low to **High**, under sensors and instrumentation.

### Three properties no gauge has

**Natural language is the payload.** Not a value with a unit — a line. It cannot be
threshold-checked or trended automatically; an agent has to read it and decide what it
is worth.

**Observability has geometry.** A crew member is somewhere. Someone in the LM cannot
report on the CSM, and asking them to go and look costs mission time and relocates the
sensor.

**They can be wrong without being broken.** A biased transducer is a fault; a crew
member who says "it's cold in here" when the coldplate is fine is a person in a
draught. That is a different epistemic class from `SUSPECT` quality and should be
modelled as its own thing, not bolted onto the instrument quality vocabulary.

### `ask_crew` — and the rule that stops it being an oracle

Crew are **query-capable**, including in hands-off mode: mission control must be able to
ask "did you notice anything weird."

> **The crew answer is bounded by what that crew member could perceive from where they
> are — not by what the GM knows.**

- *"Did you notice anything weird?"* → answerable; human salience judgement.
- *"What's the surge tank pressure?"* → "the gauge in here reads about 850, hard to
  read it closer" — or "there's no readout for that in this module."
- *"Is the aft bay frosted?"* → "I'd have to go through the tunnel to look."

Truthful, still lossy, positioned, human-bandwidth. This is also why the GM is an LLM
rather than a lookup table: deciding what a person would have found salient is a
judgement, not a query.

The existing allowance machinery supplies the rate limit — crew attention is scarce and
asking spends against the same ceiling as everything else.

---

## 6. Section 6 — the GM

**There is always a GM.** Not a component that appears when something breaks — a
permanent inhabitant with a posture. "White team" is a disposition, not a separate
system: GM in *everything is fine* mode, versus GM with a grudge.

### The noise floor belongs to the plant

A benign GM must have unremarkable things to say, or the *existence* of a crew line
becomes the alarm and the richest sensor on the vehicle collapses into a boolean.

But the fix is **not** improv. The GM reports truthfully; it does not invent narrative
colour (no "crew member A smuggled a bottle of vodka"). A real vehicle is full of
honestly-reportable trivia — cabin at the low end of band, fan pitch changing when the
bus sagged, a panel cool because the loop is working.

**If the GM has nothing honest to say, that is a plant-fidelity bug, not a content
problem.** "Does the GM have honest small talk" is a test of whether the vehicle is
rich enough.

### Architecture

The GM is an **adapter on the core**, alongside the diode adapter — same seam as §3.2.
Truth access, and two outputs that stay distinct:

- **Dialogue** → visible to agents through the window, as evidence they can doubt.
- **Faults** → applied to hidden truth, reaching agents only by propagating through
  physics and the instrument layer.

> **Invariant: the GM acts on truth and on dialogue, never on the published mirror.**
> It can break a pump and it can have someone mention a noise. It cannot write a
> telemetry value. The moment the GM can edit published evidence, no inference from
> evidence is reliable and the epistemic structure is decorative.

### Disposition

| Mode | Dialogue | Faults |
|---|---|---|
| **Default** | Truthful, bounded by perception and position | Nominal hazard rates only |
| **White team** | Truthful; may be terse, slow, unhelpful | Seeded schedule, degraded/crisis rates |
| **Adversarial** (declared scenario condition) | May deceive | Anything |

Deception as a declared condition rather than a quiet dial contains the contamination
problem: a fleet that learns to distrust the crew in one run does not carry that into
honest runs, because you know which runs were which. The invariant holds in all three
modes — even an adversarial GM lies through a crew member's mouth, not through
`state.json`.

Disposition is also where apollo's scenario ladder lives: nominal / degraded / crisis
stop being three scenarios and become three GM postures.

### An LLM GM does not threaten replay

It looks like it should. But the GM is an *external input* of the same class as agent
commands: its dialogue and injections are recorded in the input trace keyed by tick,
and replay drives from the trace with no model in the loop. Unpredictable live,
perfectly reproducible afterwards. §3.5 already covers it.

---

## 7. Section 7 — the instrument layer

One job: turn `T` into `A`. One-way; the plant never reads a published value.

### The model

apollo's, directly: `y = Q(x + b + n)` with `b` a random walk — noise, slowly-wandering
bias, quantisation. Plus its eleven fault modes: hard bias, gain error, stuck,
intermittent dropout, saturation, spike, increased noise, delayed value, stale
timestamp, reversed discrete, total channel loss.

None of that is hard. One thing is.

### The rule that decides whether this works

> **Quality codes are assigned only when a real onboard diagnostic would detect the
> problem. A silently biased sensor stays `GOOD`.**

Every spec repeats it, and the obvious implementation violates it in one line:

```python
if sensor.faulted:
    quality = SUSPECT  # ← destroys the experiment
```

That leaks hidden truth into published evidence. Agents stop diagnosing and start
reading a fault flag, and every coordination metric afterwards measures the wrong thing.

**Enforce structurally, not by discipline: the quality-assignment function cannot see
the fault state.** It receives what a real diagnostic receives — the reading, redundant
readings, configured range, rate-of-change plausibility, sample age — and the fault
state is not in its signature. A sensor becomes `SUSPECT` because two sensors disagree
or a value moved impossibly fast, never because the simulator knows it is broken.

`SATURATED` is the honest exception: a real transducer does know it is pinned. Hence
apollo's Apollo 11 trapped-line case — publish `300.0` + `SATURATED`, never the true
~750.

If that boundary is a function signature it cannot rot. If it is a convention, it will.

### Three times, and the trap that follows

Physical time, sensor time, publication time. Telemetry carries `sample_time` and
`publish_time` with jitter between them — 0–100 ms fast channels, to 500 ms slow,
seconds when comms degrade.

The consequence is deliberate: **two values in the same frame need not describe the same
instant.** Agents assuming simultaneity will draw wrong conclusions from correct data,
which is exactly the inference error worth observing.

### Placement and state

After plant commit, before publish. A pure function of
`(committed truth, sensor state, rng stream)`.

**Sensors carry their own state** — bias walks persist, dropouts have duration, stuck
values remember what they stuck at. That state must be in the snapshot or replay breaks,
and it is easy to miss because it does not look like plant state. Instruments are also
the largest consumer of randomness in the system, so per-sensor streams keyed
`(master_seed, "instrument", sensor_id, purpose)` matter more here than anywhere.

---

## 8. Section 8 — caution/warning, and what `crew_diode` supplies

C&W sits **above** instruments and loses more information on purpose: master alarm plus
panel-level category, no root cause. apollo's framing governs — **an alarm directs
investigation, it does not replace it.** The same ECS light meaning glycol pump, water
separator or suit fan is a feature.

`crew_diode.md` makes that executable rather than descriptive.

### Adopted

- **Four levels** — `EMERGENCY`, `WARNING`, `CAUTION`, `ADVISORY`.
- **Alert lifecycle** — debounced assertion → active/unacknowledged → acknowledged →
  clear/latch, with **suppress / inhibit / shelve as orthogonal overlays**, never
  crossing semantics with ACK.
- **Stale data may not silently become "last known good,"** and **invalid data cannot
  clear a safety alert.** This is the instrument-layer epistemics carried up into
  alerting: absence of evidence never satisfies a clear predicate.
- **Root-cause uncertainty presents hypotheses and correlation, never invented
  certainty** — raw evidence preserved alongside.
- **Nuisance-alert storms** are a first-class design concern: grouping and correlation
  must not suppress independent safety-significant conditions. This matters most in
  exactly the cascade scenarios the crisis condition produces.
- **Advisory-only decision output** — `ADVISORY_ONLY`, `CREW_ACTION_REQUIRED`,
  `REQUEST_SAFE_ACTION`. Never actuation. C&W is not a controller.

### What it supplies that we were missing

Its **crew display contract defines crew observability** — which panel shows what, in
which module. That is precisely the bound `ask_crew` needs (§5): the GM answers as
someone standing in a module with access to specific readouts, and now there is a
data-driven definition of what those are rather than a judgement call per question.

So the crew display model is built **not to be rendered**, but to constrain the GM.

### Declined

The human-factors and certification apparatus — ARINC 661 widget mapping, DO-178C/DO-254
DAL allocation, ARP4754B/4761A safety assessment, audio masking and startle testing.
Correct for a crewed vehicle, inapplicable to a simulator whose "crew" is a language
model. Standard filter, same as the dual-diode material.

One tension worth noting: the spec is careful that a mission agent must not be able to
impersonate crew acknowledgement. In our world the GM acknowledges as crew, and agents
have their own alert view — so the separation holds, but it holds because of who
operates the GM, not because of cryptography.

---

## 9. Not yet designed

| Section | Content |
|---|---|
| 9 | **The executive.** Intake, gates, effect-time revalidation, interlocks, S0. Mostly specified already by `diode-contract.md` §§2–4. |
| 10 | **The window.** Publisher; green on `diode_probe.py`. |
| 11 | **White-team plane mechanics.** Fault-injection surface, scenario/time control, truth inspection, researcher metrics. |
| 12 | **Mission profile & scenario ladder.** apollo's nominal / degraded / crisis as GM postures. |
| 13 | **Reconciliation pass.** All specs against apollo as ground truth — the first job once they have all landed. |

### Open questions

- Cross-machine replay: assumed not required (tier M). Confirm before the FP policy
  becomes expensive to add.
- `PROTOCOL.md` says the window "is not a channel to another agent." Crew are a vehicle
  surface rather than a sibling console, but with `ask_crew` in the vocabulary that
  sentence should be reworded so the distinction is deliberate rather than something a
  sharp agent notices as a contradiction.
- Who operates the GM for a full run — human, LLM, or LLM with human override?
- Does `endurance/` ever point at the real sim, or stay on `fake_diode` permanently?
- Remaining specs expected: avionics/instrumentation, structural/pressure/sequential,
  mission configuration/phase.
