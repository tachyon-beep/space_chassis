# Vehicle simulator — design in progress

**Status:** WORK IN PROGRESS. Sections 1–3 presented and approved; section 3 to be
re-opened once `axiom-determinism-and-replay` is loaded. Sections 4+ not yet written.

**Relocates to the vehicle repo** once that exists. It lives here only because that
repo has not been created yet and this needed to survive a session restart.

**Process:** `superpowers:brainstorming`, architectural path. Design is presented in
sections with approval after each. On completion the full design goes to subagent
review — `yzmir-systems-thinking`, `bravos-simulation-tactics:simulation-architect`,
`yzmir-simulation-foundations:stability-analyst`,
`axiom-determinism-and-replay:determinism-reviewer`, and
`axiom-solution-architect:solution-design-reviewer` — before any implementation plan.

---

## 1. What is being built

A spacecraft simulator: the far side of the window that `space_chassis` deliberately
does not contain. Ten LLM agents fly it through `docs/diode-contract.md`. A white team
(LLM + human operator) can inject faults and drive scenarios, but **the baseline is
hands-off**: with no white-team input the plant simulates health, components meet
spec, hazard rates are low but nonzero, and a competently flown mission lands.

The white team is a perturbation layer, not a driver. A run with zero white-team
input is a valid run.

### Established context

- The diode is **emulated as a sibling container** sharing a volume — not hardware.
  `~/aurora/` runs this pattern successfully: `diode.py` + `Dockerfile.diode` on the
  `egress` network, agent container with no network interface, credentials and
  ceilings only in the diode service's environment.
- `space_chassis/docs/diode-contract.md` descends directly from Aurora's `diode.py`
  (`console.json`, `state.json`, `HELP.md`, `output/`, `consume_batch()`,
  gates-as-`variables`, `min(agent, operator)` ceiling) and generalises it from one
  console to one directory per agent.
- **`docs/deep_research/` holds eight ChatGPT deep-research documents**, generated in
  sequence, each citing its predecessors: `apollo` (the experiment), then `electrical`,
  `eclss`, `gnc`, `main_propulsion`, `rcs`, `communications`, `thermal`. Consumables
  is in development.

### How to read the research docs

**The seven subsystem specs are schemas and safety semantics with no vehicle in
them.** Every threshold is `UNSPECIFIED` / `RIP-REF` / `Sim`, deferred to "mission
configuration." `apollo_diode.md` is the only document containing an actual
spacecraft — masses, anchored ranges, the coupling graph, failure chains, a mission
profile, the scenario ladder, coordination metrics.

> **Rule: apollo supplies the vehicle and the experiment; the subsystem specs supply
> the per-domain contracts. Where they disagree on a number, apollo wins — it is the
> only one making a claim about an actual vehicle rather than about a schema.**

All seven subsystem specs also escalate to a **hardware dual-diode** (two simplex
optical paths, per-object crypto, anti-replay). That argument is correct and
**inapplicable** — the asymmetry here is container topology. The specs' own tables
rate the filesystem/service pattern as the right choice for a simulation. Treat the
transport-security layer as answered; the subsystem physics is the payload.

`communications` is the one doc that would require *changing* the contract rather
than extending it (demotes `output/*.txt`, splits `/diode` into two mounts,
criticises `consume_batch()` by name). Given Aurora runs that mechanism
successfully, treat it as a proposal to decline.

---

## 2. Decisions taken

| Decision | Value |
|---|---|
| Location | **Separate repo.** Only inbound dependency is a frozen copy of `diode-contract.md`; `contract/diode_probe.py` runs against it in CI. `space_chassis` keeps `fake_diode` for smoke and endurance, and its README stays true. |
| White-team baseline | Hands-off. Nominal run needs no input. |
| Conflict policy | apollo's only: first valid command in a conflict domain wins for that tick; later ones get a refusal result they must read. Nothing smarter — `design.md` §8 makes deconfliction the fleet's problem. |
| Determinism | Hard requirement from the first commit, not a later feature. |

---

## 3. Section 1 — the six pieces (approved)

1. **The dictionary.** One versioned machine-readable vehicle definition: every
   telemetry point (id, unit, range, precision, rate, quality semantics, provenance
   class, A/I/T layer), every verb (args schema, gate, authority, interlocks,
   conflict domain, irreversibility), and component topology. Not a doc — the artifact
   the plant, publisher, probe and white-team console all read. Makes incoming specs
   *data entry* rather than six codebases.

2. **The plant.** Fixed-step integrator, conserved stocks, lumped per-domain models,
   cross-domain coupling as a declared graph. Owns hidden truth. Advances on its own
   clock whether or not anyone is thinking.

3. **The instruments.** Truth → evidence. Noise, bias random-walk, quantisation,
   saturation, stuck, dropout, lag; quality codes assigned only when a real diagnostic
   would catch it. **Hard layer boundary** or the A/I/T distinction leaks and the
   epistemic premise goes with it.

4. **The executive.** Vehicle-side authority: intake per contract §2.2, closed
   vocabulary, gates, `min(agent, operator)` allowance, deferral re-checked at the
   moment of effect, interlocks, an abort agents cannot reach.

5. **The window.** Contract-conformant publisher, one directory per agent. Already
   specified and already tested — `diode_probe.py` walks twelve properties and
   `fake_diode.py` passes them. The simulator is structurally `fake_diode` with a
   vehicle behind it.

6. **The white-team plane.** A separate channel agents cannot see or write: fault
   injection, scenario and time control, truth inspection, researcher metrics.
   Researcher observability and agent observability are different design questions,
   so it is a different surface — not a privileged verb set on the same one.

### Build order

Dictionary + linter → **spike on electrical → thermal → consumables** →
instruments → executive → window (green on `diode_probe.py`) → white-team plane →
remaining domains → mission profile.

---

## 4. Section 2 — the vehicle definition (approved)

The subsystem specs are each written about one domain in isolation, so none can
supply a cross-domain value. Mass is the canonical case: GNC needs it for inertia
and Δv, propulsion for depletion, consumables for propellant-as-resource-and-mass,
structure for loads — and it changes across the mission. Same for inertia tensor,
CoM, configuration/staging state, mission phase, MET epoch, crew size and metabolic
rates, coordinate frames.

```
vehicle.yaml          globals — mass, inertia, CoM, configuration/staging, frames
mission.yaml          profile — phases, durations, crew, MET epoch, targets
coupling.yaml         the cross-domain graph: what feeds, heats, loads, drains what
domains/<name>/       components · points · profiles · commands · fault_policy
scenarios/<name>.yaml seed, hazard rates, fault schedule
```

Five files per domain, matching `thermal`'s factoring (`tcs_components`, `tcs_points`,
`tcs_profiles`, `tcs_commands`, `tcs_fault_policy`), so an incoming spec lands as five
files and the linter says whether it composed. **`coupling.yaml` is the one nothing
supplies** — apollo has that graph as a mermaid diagram, and turning it into data is
most of what integration means here.

### The linter

`thermal` specifies it; generalise it to the whole vehicle. Refuse a build on: a
safety-critical zone missing limits or freshness bounds, duplicate point IDs,
dimensional-unit mismatches, inverted hysteresis, direct commands aimed at passive
hardware, unresolved actuator dependencies, any normal verb able to override an `S0`
interlock.

**Key property: a value that is needed and unset fails the build, loudly, naming what
wants it.** (`thermal`'s `UNCONFIGURED ≠ nominal`, generalised.) You do not enumerate
what the simulator needs up front — you add a domain, run the linter, and it tells you
what you now owe it. The config is a conversation with the linter, not a form.

### Provenance

No spec asks for this; add it anyway. Every value that matters records whether it is
apollo-anchored, a spec `RIP-REF`/`Sim` default, or chosen to make the thing run. When
a run goes strangely you want to know in one grep whether the driving value was
anchored or invented. Required on values the linter classes safety-critical or
experiment-affecting; optional elsewhere.

### Also liftable from `thermal`

Typed thermal graph (`ThermalNode → ThermalZone → SensorEvidence → LocalController →
ThermalActuator/TransportPath → ResultingState`); passive hardware as observable
objects with no command interface; paired heat/cool thresholds with minimum dwell
mandatory for regulated zones.

---

## 5. Section 3 — the plant and coupling graph (approved; TO RE-OPEN)

> Re-examine with `axiom-determinism-and-replay` and `yzmir-simulation-foundations`
> loaded. The determinism claims below were made without them, and the integrator
> choice needs a stability argument rather than a convenience argument.

**Domains do not call each other.** Each is a pure function over a state snapshot,
declaring what it reads and writes; `coupling.yaml` declares the edges. Scheduler
snapshots at *t*, every domain computes from that snapshot, all writes commit at
*t+dt*. Nothing reads another domain's half-updated values.

If domains call each other directly the coupling goes invisible within a week and
"why did the amplifier overheat" becomes archaeology. As declared data the graph is
lintable for undeclared reads, renderable, and — critically — **feedback loops are
explicit**. Power → thermal → equipment → power is a cycle; cycles must be declared
as such with a named one-tick delay. Acyclic edges resolve in topological order
within the tick.

**Rate:** single-rate 50 Hz (matching apollo), each domain declaring its natural rate
in config but the scheduler ignoring that for now. Thermal and consumables have
time constants in minutes to hours and are absurd to integrate at 50 Hz, so multi-rate
is the obvious optimisation — but it is an optimisation. Design the interface so rates
*can* split; do not build the machinery until a profiler says to.

**Stocks are conserved as a runtime assertion.** Consumables change only through
declared flows; each tick checks mass in = mass out + delta stored within tolerance.
Violation is a modelling bug and stops the run. In a harness whose premise is that
agents reason about resource margins, silently leaking oxygen because two domains both
decremented a tank corrupts the experiment invisibly — the worst available failure.

**Determinism (PROVISIONAL):** fixed step, no wall-clock reads inside the plant,
per-stream PRNG keyed on `(master_seed, domain, purpose)` rather than one shared
generator. Shared-generator looks fine until you add a domain and every previous run's
noise sequence shifts, at which point replay comparison is worthless. *Not yet
addressed: bit-exact vs logically-equivalent replay, snapshot cadence, divergence
localisation protocol.*

**The spike.** Electrical → thermal → consumables, driving apollo's degraded chain:
amplifier on → bus load step → voltage sag → marginal pump → coolant flow falls →
coldplate ΔT climbs → amplifier temperature rises. Plus the fuel cell, because
O₂ + H₂ → power + water + heat ties consumables to both neighbours at once.

Exercises a declared feedback cycle, a conserved stock with production, a slow
constant beside a fast one, and three inferred quantities (load margin, SOC,
time-to-limit). If it runs from config with no hand-wired special cases, the remaining
domains are volume. If it needs special-casing, that is learned at three domains
instead of twelve.

---

## 6. Not yet designed

| Section | Content |
|---|---|
| 4 | **Instruments.** The layer deciding whether this is an epistemics experiment or a gauge panel. |
| 5 | **Fidelity ladder.** What to simulate vs fake, per domain — `bravos-simulation-tactics` scrutiny-based LOD. |
| 6 | **The executive.** Intake, gates, effect-time revalidation, interlocks, S0. |
| 7 | **The window.** Publisher; green on `diode_probe.py`. |
| 8 | **White-team plane.** Fault injection, scenario/time control, truth inspection, metrics. |
| 9 | **Time.** Sim-time ratio — 1:1, compressed, or phase-dependent (fast through coast, real-time through burns). ~8-day profile. Named as a design axis, not yet decided. |
| 10 | **Mission profile & scenario ladder.** apollo's nominal / degraded / crisis. |

### Open questions

- Sim-time ratio (section 9) — unresolved.
- Does `endurance/` ever point at the real sim, or stay on `fake_diode` permanently?
- Consumables spec lands soon; expect it to want a place in the core, not the tail.
