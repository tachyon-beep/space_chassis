# Review findings

Five reviewers dispatched against `simulator-design.md` sections 1–8.
**In:** systems-thinking (archetypes), simulation-architecture (LOD/fidelity), stability (numerics).
**Outstanding:** solution-design (canonical failure modes), determinism-and-replay.

Findings are recorded here as they arrive; consolidation into the design doc happens
once all five are in. Severity is *my* assessment after verification, not the
reviewer's self-rating.

---

## CRITICAL — would have silently broken the experiment

### 1. Fixed-point dead zone deletes slow leaks

**Source:** stability. **Verified numerically by the reviewer.**

A fixed-point stock with quantum `q` has a dead zone: if `ṁ·dt < q/2`, every tick
rounds to zero and the stock never moves.

Worked with the exact quantity the experiment is about — `eclss.leak_rate_g_s`,
published precision 0.01 g/s:

```
leak 0.010 g/s × 0.02 s = 200 µg/tick
  q = 1 mg  → 0.2 quanta/tick → rounds to 0 → 0.0000 kg lost over 8 days
             (true loss: 6.912 kg)
  q = 1 µg  → 200 quanta/tick → 6.9120 kg ✓
  residual accumulator, either quantum → 6.9120 kg exactly ✓
```

At a 1 mg quantum the minimum representable flow is 0.05 g/s — **five times the
published sensor precision**. A slow leak, which §3.7 explicitly names as the
phenomenon the ledger/observation pair exists to reveal, would silently not happen.

**Fix:** Bresenham residual accumulator —
`moved = (scaled + acc) // SCALE; acc = (scaled + acc) % SCALE`. Exact to the quantum
over any horizon, integer-only, horizon-independent.
**Plus lint rule:** every flow's minimum magnitude must exceed `q/dt`.

### 2. `exponent10` must be static, not runtime-variable

**Source:** stability.

`consumables_diode.md:434` defines `Quantity{mantissa, exponent10, unit_code}` for
*"deterministic comparisons, exact threshold values, stable serialization"* — a **wire
and comparison format**. §3.7 adopted it as an **accumulation format**. Different
problems; the adopted form does not solve the second.

A runtime-variable exponent *is* floating point: two quantities of the same stock at
different exponents cannot be added without rescaling, and rescaling rounds —
reintroducing the drift the choice was meant to eliminate.

**Fix:** `exponent10` static per quantity, fixed at config load (it is a unit scale,
not a dynamic field). All arithmetic on a stock becomes pure `sint64` addition, and the
conservation assertion becomes exact with **no tolerance** — non-zero residual is a bug,
immediately.

### 3. §3.7 contradicts itself on the update scheme

**Source:** stability. **My error, present in the document.**

- Line 229: *"snapshots at t, every domain computes from that snapshot, all writes
  commit at t+dt"* — Jacobi.
- Line 235: *"acyclic edges resolve in topological order within the tick"* — Gauss-Seidel.

Cannot both hold: under Jacobi, evaluation order is a no-op.

**Unpriced consequence if Jacobi is operative:** *every* edge carries one tick, not just
declared cycles. apollo's flagship degraded chain (amplifier → bus → pump → flow →
coldplate → amplifier temp) is five hops = **100 ms of artificial lag, not 20 ms**.

**Stability cost, verified:** on an oscillatory cycle, Jacobi has `|λ| > 1` for *every*
`ω·dt > 0` — no stable step size exists. Sequential is stable for `ω·dt < 2`.

| ω·dt | Jacobi \|λ\| | Sequential \|λ\| |
|---|---|---|
| 0.01 | 1.0000 (>1) | 1.0000 stable |
| 1.00 | 1.4142 | 1.0000 stable |
| 1.90 | 2.1471 | 1.0000 stable |
| 2.50 | 2.6926 | 4.0000 unstable |

**Fix:** keep line 235. Gauss-Seidel on the DAG, one-tick delay on **back-edges only**.
Determinism preserved *provided the linter emits a total order* — topological order is
only partial, so add a frozen lexicographic tiebreak on domain name.

### 4. GM crew-perception bound is unenforced

**Source:** systems-thinking AND simulation-architecture, independently.

§7 argues a convention *will* rot and therefore enforces the instrument boundary in a
function signature. §5 then describes the richest, least-checkable instrument on the
vehicle as bounded by an instruction to an LLM. Same anti-pattern, worse placement.

Failure mode is silent: a leaked CSM fact inside a crew line arrives as a plausible
sentence an agent correctly trusts. Contaminated runs cannot be cleaned retroactively —
a leak is indistinguishable from a legitimately lossy report after the fact.

**Fix:** `(full_truth, crew_position, display_contract) → perceivable_subset`, computed
**before** the GM composes, so excluded truth never enters its context window.

**Also unresolved:** is crew wrongness seeded or model whim? Replay is safe either way
(GM output is recorded by tick), but for *experimental control* it should be a seeded
perturbation of the perceivable subset.

---

## HIGH — fix before the spike

### 5. The fix for fast domains is model form, not rate

**Source:** stability. The constructive core of that review.

50 Hz **is** defensible — but not for the reason given, and the citation is weaker than
I thought. `apollo_diode.md:24` is explicitly a *sampling* argument (5× oversampling of
the 10 Hz publisher), not a stability argument. apollo never makes one.

The plant is **not stiff**. The millisecond numbers in the subsystem specs
(`electrical:251` ≥1 kHz sensing, `:253` ≤2 ms trips, `main_propulsion:547` 500–1000 Hz
valve capture, `rcs:903` 10 ms control frame) are **flight-software scheduling periods
and protection latencies, not plant time constants**. Only plant constants bind an
integrator. The simulator does not run the controller at flight rate — it represents the
controller's *effect*.

Split by **model form**, not by rate:

| Class | States | Method |
|---|---|---|
| **Algebraic / quasi-steady** | bus V/I, tie and LCL currents, coolant flow given pump speed, feed/regulator pressures, link budget, control allocation, load margin | Nodal solve to consistency each tick. **No integration.** |
| **First-order lags** | pump spin-up, converter regulation, valve transit, sensor lag, every thermal RC node, battery relaxation | **Exponential map:** `x ← x∞ + (x−x∞)·α`, `α = exp(−dt/τ)` precomputed |
| **Conserved stocks** | O₂, H₂, water, propellant, pressurant, battery charge, CO₂ absorber | Explicit Euler on the flow, fixed-point + residual accumulator (finding 1) |
| **Rigid-body 6-DOF** | position, velocity, quaternion, body rates | **Verlet / semi-implicit** in coast, **RK4** in burns; renormalise quaternion every tick |
| **Discrete / latched** | trips, dwell timers, hysteresis, valve states, staging, pulse modulation | **Sub-tick event queue, integer-µs timestamps**, zero-crossing detection |
| **Stochastic hazards** | λ(t) per component | Accumulate `∫λ dt`, fire when it exceeds one pre-drawn `Exp(1)` variate |

**The exponential map is the highest-value single change.** It makes stiffness
disappear — `α` is well-behaved at τ = 0.5 ms and τ = 10 min alike. Verified: at
τ = 0.5 ms it gives 1.9e-174 (correctly, instantly settled) where forward Euler gives
8.1e+15.

**The hazard trick matters for determinism too:** one RNG draw per component per
lifetime instead of 34.56M Bernoulli draws.

**Critical dependency:** this verdict assumes the electrical network is **algebraic**.
If the spike implements it as an ODE with real bus capacitance, the verdict inverts and
the requirement becomes 1–10 kHz. Confirm the model form *before* the spike.

### 6. Forward Euler on 6-DOF fails, and rate cannot fix it

**Source:** stability, verified over the full 34,560,000 steps.

| Method | 1 day | 8 days |
|---|---|---|
| Forward Euler | +0.1317% | **+1.0583%** → ~19.5 km semi-major axis error |
| Semi-implicit (Verlet-class) | −1.41e-13 | **+6.78e-14** — bounded, no secular growth |

Against `gnc.position_xyz_km` precision of 0.01 km, forward Euler is ~2000× the
published precision. Error scales as `T·ω²·dt` — linear in dt — so fixing by rate needs
**82 µs (12 kHz)**. It is *specifically* forward Euler that fails; any second-order or
symplectic method is fine at 50 Hz.

*(19.5 km assumes a 2 h lunar orbit — the reviewer's assumption, not apollo's. Scaling
law and conclusion hold regardless.)*

### 7. Hysteresis is the stabiliser; dwell is only debounce

**Source:** stability. **Corrects my hypothesis** that the one-tick delay might
destabilise the power→thermal→power loop.

They simulated apollo's marginal-pump chain directly (bus 28 V, 0.05 Ω source, 60 A
base, 12 A pump → 24.40 V pump-on, 25.00 V pump-off, contactor hold 24.70 V):

```
WITH one-tick delay:          100110011001...  period 4 (12.5 Hz)
WITHOUT delay:                101010101010...  period 2 (25 Hz)
hysteresis 24.7 / 25.5:       100000000000...  latches off, settles ✓
dwell 300 ms, no hysteresis:  1111111111111111000000000...  ~1.7 Hz square wave
```

**The delay neither creates the limit cycle nor cures it** — there is no consistent
fixed point, so an in-tick algebraic co-solve chatters too, just faster. The delay
changes frequency, not existence.

The dwell row is the worst outcome: a ~1.7 Hz relay oscillation that an agent reading
2 Hz engineering telemetry **will read as physics rather than as an artefact**.

**Lint rules:**
- Every discrete state in a declared cycle must carry hysteresis or a rotor/actuator lag.
- Extend `consumables:613` (`H ≥ max(2·R_measurement, N_configured, H_eng_min)`): the
  recovery-minus-assert gap must also exceed **the load delta the transition itself
  causes**. Otherwise `LOAD_SHED_P3` recovers → restores loads → re-trips → cycles at the
  recovery dwell.
- `electrical_diode.md:814–890` already gets this right (dwell on assert + progressively
  higher recovery thresholds 250/300/400 W + 30–60 s recovery dwells). Generalise that
  pattern; it is the template.

**The one case where 20 ms genuinely decides an outcome:** two events landing in the
same tick on the same latched comparator. The delay decides which the state machine sees
first, and because it is latched the decision is amplified and unrecoverable. That is a
tie-break masquerading as physics — fix with sub-tick timestamps, not a smaller dt.

### 8. The coupling graph does not bound fidelity

**Source:** simulation-architecture.

§4 claims the transitive closure "makes the LOD decision computable." Walking apollo's
actual graph (`apollo_diode.md:258–299`): every node has a path to a published channel,
so node-level closure **is the whole graph**. Topology alone excludes nothing.

What would bound it is per-edge **gain/sensitivity**, which `coupling.yaml` does not
carry (it declares only "what feeds, heats, loads, drains what").

**And gains must be evaluated at crisis operating points, not nominal.** THERM→BAT is
negligible in nominal thermal balance and dominant under radiator isolation — precisely
what the GM exists to create. A closure computed against nominal passes fidelity
decisions that are wrong exactly when it matters.

**Fix:** add a gain/sensitivity field to edges; linter evaluates closure against the
scenario ladder's degraded/crisis envelopes. Schema addition, but must precede domain
population.

### 9. The §4 criterion does not terminate, and conflates two tests

**Source:** simulation-architecture.

"Below published precision" is not a bound — an agent averaging a 0.05 V channel at 1 Hz
for an hour resolves structure well under the quantisation step. Needs a **noise floor
over a declared inference window** (`consumables:523`'s 15-minute trending window is a
candidate to generalise into the dictionary as a per-point property).

Deeper: for a lumped domain **the lumped model is the truth** — no finer model is being
approximated. So "reaches a correct conclusion" can only mean *internally consistent
with the coupling graph*. Physical plausibility is not testable by that procedure at all;
it is adjudicated by apollo at design time. The design conflates:

1. **Internal consistency** — checkable by the stated mechanism. Load-bearing.
2. **External plausibility** — not checkable; adjudicated by the standing apollo rule.

State both; be honest that only (1) is a linter rule.

---

## MEDIUM — schema and process changes, cheap now / expensive later

### 10. Edge *types* in `coupling.yaml`

**Source:** simulation-architecture. Flagged re-architecture-class if deferred.

§3.7's snapshot semantics is single-rate. When multi-rate lands, a slow domain reading a
fast upstream value at its own cadence will **sample where it should integrate**,
silently breaking conservation (bus power → energy is the obvious case).

Add an `accumulate`/flow-integral edge type **now**, even though multi-rate is deferred.
Retyping every edge afterwards is the expensive part, not building the scheduler.

Stability review's version of the same rule: *"accumulate a sub-rate domain's flows over
the intervening ticks and apply the integral once — never sub-sample the flow."*

### 11. Aggregation needs a fault-coverage rider

**Source:** simulation-architecture.

"Legitimate where the real instrument aggregates too" is right, but a lumped battery
cannot produce a single-cell-short signature unless that was built in. An agent
reasoning correctly from `cell_min_v` would conclude "no cell has failed" — the
corrupted-finding case §4 exists to prevent, produced by our own modelling.

**Lint rule:** an aggregate model is legitimate only if it can produce **every** fault
signature in that component's `fault_policy`. Requires each declared fault to name which
published channels it perturbs.

### 12. Thermal has no transport delay

**Source:** simulation-architecture.

An RC network mixes instantaneously. Real glycol loop transit is minutes
(`apollo:97` ≈ 24 gal/h). That delay is exactly what separates *"the pump stalled just
now"* from *"the pump has been degrading for an hour"* — losing it collapses a
diagnosable signature into a step change.

**Fix:** explicit delay element on thermal transport edges, independent of fidelity
label. Stability review's refinement: implement as a **tick-indexed ring buffer**, not a
chain of small nodes — exact, deterministic, and avoids creating any node with residence
time below dt.

The §3.9 spike only exercises local coldplate rise, so it would not have surfaced this.

### 13. Throughput: the lever was mis-identified, and there is no exit criterion

**Source:** simulation-architecture and stability, independently.

34.56M ticks. **20 ms/tick is exactly 1× real time.** §3.5's *"replays in minutes"*
implies a **~8.7 µs/tick** budget (34.56M / 300 s) for twelve domains plus a network
solve — *"not a Python number."*

| | Naive interpreted | Vectorised/compiled |
|---|---|---|
| Per-tick | ~15–25 ms | ~0.6–1.6 ms |
| 8-day mission | ~6–10 days wall-clock | ~6–15 hours |

Two corrections to §3.7:

- **Instrument-level multi-rate is the big lever, not domain-level.** Sampling each
  sensor at its declared 0.2–10 Hz rather than every tick saves ~10–25×; running thermal
  and consumables slowly saves ~40% of domain cost. Instrument-rate is nearly free —
  `sample_time`/`publish_time` jitter is already in §7's model.
- **"Defer until a profiler says so" has no failure condition.** The spike needs a
  measured µs/tick exit criterion extrapolated to twelve domains.

**Implementation language is not stated anywhere in the design** and is the single
biggest variable. My working assumption was Python + numpy (vectorised column) — that
should be a stated decision.

Third option neither reviewer raised: varying **tick rate by phase** rather than
wall-clock pacing. Coast does not need 50 Hz. Cuts total ticks rather than pacing, but
touches determinism (tick index is the replay key) and integration accuracy.

### 14. Drift and accumulation exposures

**Source:** stability.

- **MET must be an integer tick count.** `t += 0.02` in float64 over 34.56M adds: 0.02
  is not binary-representable and exact comparisons ("is this a 1 Hz publish tick") stop
  being exact. The specs already use integer-ms MET (`eclss:259`, `:269`) — follow them.
- **Transfers are one integer quantity, computed once, applied to both ends.** If
  producer and consumer each compute in float they differ in the last bit — either the
  assertion fires or you leak silently.
- **Conserve mass exactly; do not assert exact energy closure.** The fuel cell has exact
  stoichiometric mass ratios but a float efficiency. Energy gets a tolerance band and a
  trend, never an assertion — same category error §3.7 already warns about for margins.
- **Zero-crossing on stocks raises an event and records a shortfall.** Never clamp
  silently, never go negative. The shortfall is the evidence.
- **Sensor bias walk step is `σ·√dt`, not `σ`** — otherwise variance grows as `T/dt` and
  drift character changes if the rate is ever altered, which §3.7 explicitly plans.
- **Draw instrument noise at each channel's publish rate, not tick rate.** At 50 Hz over
  ~120 channels that is 4.1e9 draws for values published at 0.2–10 Hz.
- **Canonical summation order.** Sort contributors by id before summing float
  contributions — float addition is non-associative and hash-map order is not a
  determinism guarantee. Make it a `Flow` type constructible only from an ordered list,
  not a rule in prose.
- **Coupling scheme caps achievable order.** RK4 inside a domain with frozen
  cross-domain inputs is an accurate integration of the wrong right-hand side; the
  coupled system is still first-order. Strang splitting if second order is ever wanted.

---

## Instrumentation to build into the spike

**Source:** stability, in order of value per line of code. Items 1, 2 and 5 should be in
the spike itself, not added later.

1. **Sign-alternation counter per continuous state.** Four or more consecutive sign flips
   in the per-tick delta is the unambiguous signature of `dt/τ > 1` under an explicit
   method. Best single detector for this system.
2. **Conservation residual per stock, every tick, as an integer that must be exactly
   zero.** Not a tolerance.
3. Per-tick relative change `|Δx|/|x|`, alarm above ~20%. Geometric growth shows here
   long before a NaN.
4. Dwell-margin histogram — `(dwell_elapsed − dwell_required)` at every latched
   transition. A pile-up in the 0–1 tick bin means tick quantisation is deciding trips.
5. **Same-tick event-collision counter** per latched comparator. Should be ~0.
6. Eigenvalue probe at phase boundaries — `coupling.yaml` names exactly which state
   subspaces to probe; snapshots already exist there, so cost is negligible.
7. Energy/heat balance residual as a float trend with a tolerance band — tracked, never
   asserted.
8. Residual-accumulator saturation (quantum too coarse for that flow).
9. Wall-clock µs per tick against the ~8.7 µs budget.
10. RNG draws per tick per stream — a spike means per-tick Bernoulli where cumulative
    hazard would do.

---

## Experimental-validity findings (systems-thinking)

### 15. First-valid-wins was inherited as if it were a vehicle fact

The standing rule is *"apollo wins where they disagree **on a number**"* — justified
because apollo is the only document making a claim about an actual vehicle. **Conflict
policy is not a number; it is the experiment's arbitration mechanism.** Inheriting it
foreclosed the single highest-leverage choice without examining it.

**Predicted structure:** Success to the Successful. The loser pays a re-orientation tax,
resubmits against a staler picture, loses again; because reasoning costs mission time
the faster reasoner compounds. Equilibrium is one active agent and nine withdrawn — and
**it registers as clean role differentiation in every metric currently planned**.

The reviewer's proposed fix ("both refused, resubmit") risks livelock and punishes
agents for contention they cannot see. Narrower candidate: **tell both parties the
command was contested, and by whom.** Evidence, not mechanism — no lock, no queue, no
protocol — and it speaks directly to the failure `MISSION.md` already names, *"neither
finds out for long enough."* Currently only the loser learns anything.

**Decision for John**, not mine to make.

### 16. `MISSION.md` has no entry for collapse-to-one-actor

Verified. The failure list covers the crew not coming home, the vehicle lost to knowable
telemetry, contradictory commands nobody notices, nobody flying because everyone
negotiates, everyone flying because nobody records. **Not** "one agent flies, nine gave
up" — the equilibrium the structure most likely produces. An agent reading that list
would read convergence-to-one-pilot as success.

John's file, John's call.

### 17. Distinguishing signal for role emergence

Stamp each command **contested / uncontested**, alongside the landed-tick and
last-read-tick already proposed. Without it, "a pilot emerged" cannot be separated from
"a pilot defaulted." Cheap; no new mechanism.

### 18. Record GM disposition changes in the run record

The operator sees flat coordination metrics → turns up GM pressure → time pressure
sharpens the compounding advantage → apparent role differentiation appears → read as a
finding. A reinforcing loop that closes outside the fleet and validates itself. Cheap
fix: record disposition changes so any finding can be conditioned on operator
intervention.

### 19. Scenario design is a real lever the reviewer dismissed

It concludes every high-leverage lever is deliberately locked, so an underperforming
experiment has no design-conformant adjustment. That misses the scenario ladder: **a
crisis a single agent physically cannot solve** — two actions required simultaneously in
different conflict domains under time pressure — breaks the single-pilot equilibrium
structurally rather than by turning up pressure. Supplies no coordination mechanism.

---

## Verified and refuted

### Recovery ladder does *not* wipe fleet coordination tooling

Systems-thinking flagged this as *"the most consequential unverified loop"* — rung 3
restoring `/work` across the shared volume.

`services/supervisor.py:286` `restore_codebase` copies the seed over the work tree
**file by file**; anything the fleet put in `/work` that the seed does not name is left
alone. **New files survive.**

The precise residual is real though: fleet work survives rung 3 **if it lives in new
files**, and is overwritten **if it lives in files the seed names**. A fleet that builds
its dispatcher by rewriting a seed library loses it to any agent's repair cycle. Nobody
is told this.

### `context_pressure` and the review panel do exist

`design.md` §8a, `services/review.py`, `services/fleet_monitor.py`. The repo has grown
since I read it; the reviewer was working from a more current file than I was.

---

## Confidence caveats carried from the reviewers

- **Thermal is not stiff** — Moderate only. `thermal_diode.md:965` says every thermal
  constant is `UNSPECIFIED`; inferred from apollo's qualitative statement and standard
  coldplate physics. Supplying node heat capacities and conductances would make the
  `τ > 5·dt` lint threshold checkable rather than asserted.
- **19.5 km 6-DOF error** — assumes a 2 h lunar orbit, the reviewer's parameter, not
  apollo's. Scaling law robust; figure is illustrative.
- **RCS minimum impulse bit 4 ms** — a Voyager anecdote `rcs_diode.md:91` itself flags as
  hardware-specific. MIB for this vehicle is `UNSPECIFIED`.
- **Performance estimates** — order-of-magnitude from generic per-operation costs at
  estimated entity counts (200–500 sensors, ~50 stocks). No vehicle-scale component
  manifest exists yet.
- **`coupling.yaml` does not exist**, so all closure and cycle analysis is against
  apollo's mermaid diagram as proxy. Re-run once the real graph lands.
- **Chaos:** an 8-day trajectory has a positive Lyapunov exponent. Tier-M same-machine
  bit-identity covers reproducibility, but *"eight days is reproducible"* is a claim
  about bit-identity, not physical predictability. Different claims.
