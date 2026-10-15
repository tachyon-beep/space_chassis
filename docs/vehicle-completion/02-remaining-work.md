# Remaining work, M1 to M5

As of **2026-10-15**, `main` @ `{{MAIN}}`. The work packages are the vehicle's own (WP01–WP13,
`vehicle/ROADMAP.md`); their issues are on `tachyon-beep/space_vehicle` (#1–#13, WP08's children
#19–#30) until they are recreated here (`governance/decisions.md` D10). This file states, for each
package that is not closed: what is left, what accepts it, what it needs first, and a size.

Sizes use the 2026-10-04 programme's bands, in focused engineering effort including tests, review
and rework: **S** 1–3 days, **M** 4–10 days, **L** 2–6 weeks, **XL** months or unbounded research.
They are judgements, not estimates from measurement, and they do not add up to a date: evidence can
block a package indefinitely, and parallel work does not remove integration cost.

## Summary

| milestone | package | state | left | size | needs first |
|---|---|---|---|---|---|
| M1 | WP01 executive and ingress | **closed** | — | — | — |
| M1 | WP08 clock, persistence, continuity | 5 of 12 children merged | `#23`, `#25`–`#30` | M (code largely written for `#23`) | — |
| M1 | `#39` claim race | tier 1 merged; Option B written, unqualified | qualify and merge Option B; chassis adopts | S | Option B pushed (residual 1) |
| M2 | WP02 electrical, thermal, consumables evidence | not started | every unset input in those domains | L–XL | — |
| M2 | WP03 flight, propulsion, RCS evidence | not started | effectivity, geometry, impulse, mass properties | L–XL | — |
| M3 | WP04 electrical solve | not started | nodal solve, source/load coupling | L | WP02 inputs for power |
| M3 | WP05 transitions, dwell, protection, FDIR | not started | the discrete state machines, protection | L | WP04 |
| M3 | WP06 thermal, cabin, consumables, feed rules | not started | the remaining lag, stock and algebraic rules | L | WP02 |
| M3 | WP07 orbit, attitude, navigation, propulsion dynamics | **slice 1 in flight** (orbit propagation for `gnc.orbital_state`, Repo readiness thread, worktree `vehicle/wp07-orbit`, from 2026-10-15) | the rest: attitude, navigation, allocator, burns | L–XL | WP03 for evidenced inputs; slice 1 can start on the integrator against an analytic orbit |
| M3 | WP09 execute faults; measured evidence | not started | fault injection; the instrument layer | L | WP01, WP08 |
| M3 | WP10 conservation and cycle accounting | not started | non-vacuous mass ledgers; energy trend | M | WP01, WP08 |
| M3 | WP11 coverage and complete-vehicle gate | not started | the coverage matrix; gate V | M–L | WP04–WP10 |
| M4 | WP12 mission, scenarios, replay, performance | not started | full mission; degraded and crisis cases; timing | L | WP11 |
| M5 | WP13 release evidence and chassis handoff | not started | durable archive; tagged release; adoption | M | WP12 |

The bounded episode (`governance/decisions.md` D14) sits across WP02, WP04, WP06, WP10 and WP11: it is
the first time a subset of M3 is accepted as a whole. It is a milestone on the way, not a package.

## M1 — shared executive and clock

### WP08 children still open (all hardening)

| child | issue | what it adds | depends on | state |
|---|---|---|---|---|
| 5 clock seam | `#23` | fixed-rate scheduler; `m`, `k`, `N` required flags; retires `--poll`; record format v3; 3,000 ring slots; interim 30 s lag backstop (exit 4) | — | design settled 2026-10-12; candidate 3a (+3,518/−367) review-complete, **never tested**, on John's machine |
| 7 budget on mission clock | `#25` | command budget on mission time (ADR 0002 E2); closes "budget wall clock resets at restart" | 1, 3 | not started |
| 8 overload | `#26` | shed → dilate → hold, 30 s lag ceiling (ADR 0002 C) | 5, 6 | not started |
| 9 pause | `#27` | operator pause the fleet cannot trigger (D1); the vehicle leads the semantics, the chassis the invocation | 5 | not started |
| 10 downtime and retention | `#28` | graceful SIGTERM, `--new-world`, retention; mission time frozen while down (F1) | 3, 5 | not started |
| 11 phase from tick | `#29` | the mission phase is a function of the tick | — (3 for restart) | not started |
| 12 result stamps | `#30` | MET-rendered result names; idempotent re-publication | 4 | not started |

**Accepts M1:** WP08's issue acceptance at the merged SHA, then a gate-I record: the deployed-path
executive advances one authoritative state, two windows command and observe it, arbitration and
receipts are deterministic, and evidence is generated from stepped truth (`completion.md`, gate I).
Gate I needs the instrument path from WP09 to be honest about evidence versus truth; until then it is
"delivered in parts" (AUR-GOV-07 §3).

**Order:** `#23` first (D3); then `#29` and `#30`, which are small and independent; then `#25`,
`#27`, `#28`; `#26` last, because overload behaviour should be tuned against a plant that does real
work.

### `#39` — the claim race

Tier 1 (quiet cycles write nothing) merged as `f75420c`. Option B (take by rename, then republish only
if absent) is the real fix for silent command loss. It is a local commit, `7a87eb82`, with six review
rounds behind it. **Left:** push it (D11), run it through CI with the ≥ 30 gate runs as a test (D8),
merge, and let the chassis adopt it with `CONTRACT-PACKAGE-B.md`. Contract wording issues V-1 to V-3
(`chassis/records/2026-10-14-chassis-lane-status.md`) are the vehicle's to settle in the same change.
`#42` (gates reopen on resume) and `#40` (P3 residuals of `#21`) stay separate.

## M2 — evidenced physical inputs (research)

M2 is research, and it runs alongside M1 (D3). Each research child answers one exact question to the
standard in `vehicle/docs/evidence.md`: the primary source and page, hardware and mission effectivity,
operating regime, units and bounds, the derivation, the consumer in this model, and an independent
validation case. Closing a research child needs the model change and the validation of its consumer,
not just a PDF. A question with no answer stays a named blocker and goes to John as a scope decision.

### WP02 — electrical, thermal, consumables

| question | consumer | blocks |
|---|---|---|
| Fuel-cell and source converter dynamics (`tau_s`) and impedance | `power.source_converter_v`, bus voltages | WP04 |
| Battery usable energy, derate curve and its basis | `power.battery_usable_j_j`, `battery_soc` | WP04 |
| Thermal node aggregation: lumped masses, initial temperatures, conductances | `thermal.zone_*`, coolant loops | WP06 |
| O₂ and H₂ supply regulation (`tau_s`, basis), cryogenic tank behaviour | `consumables`, `eclss` | WP06 |
| Cabin leak, CO₂ absorber capacity, water balance | `eclss` stocks | WP06 |
| Recorder capacity (`domains/comms/components.yaml`) if the bounded episode uses data delivery | `comms` | the bounded episode |

### WP03 — flight, propulsion, RCS

| question | consumer | blocks |
|---|---|---|
| Vehicle mass properties and inertia per configuration (CSM/LM stack, docked, undocked, ascent) | `gnc` dynamics | WP07 |
| RCS jet geometry: positions, directions, cant, per-quad layout; delivered impulse per pulse | `rcs.thruster_thrust`, `E-RCS-DYN` | WP07 |
| Main engine thrust, Isp and gimbal per engine (SPS, DPS, APS) with effectivity | `propulsion` | WP07 |
| Helium pressurant feed (`pressurant_he_kg` minimum flow) | `propulsion` | WP06, WP07 |
| Reference trajectory and orbital elements for each phase | `gnc.orbital_state` initial conditions | WP07, WP12 |

The Apollo-shaped vehicle is a composite. Effectivity is decided in a decision record before a
dependent value changes; a scalar cant is not a jet geometry, and RCS command timing is not impulse
(`evidence.md`).

## M3 — complete executable vehicle

Rules go into `vehicle/domains/<name>/` as standard-library Python modules (D5); the plant keeps the
scheduler, integrators and step loop. Every rule lands with: an independent analytic or reference
case (never only a comparison of two runs of the same code), its linter rows, and the build-order
count moving with a recorded reason.

### WP04 — electrical solve and source/load coupling

Nodal solve to consistency each tick for bus voltages and currents, tie and LCL currents, and load
margin (`plant.md` §3, algebraic class). Source and load coupling with the fuel cells, batteries and
every consumer's draw. **Accepts:** analytic equilibria and transients; a load step changes bus voltage
by the evidenced impedance; removing a coupling makes a test fail. **States:** `power.bus_a_v`,
`bus_b_v` and the other power rules in [03-domain-gaps.md](03-domain-gaps.md).

### WP05 — transitions, dwell, protection, FDIR

The 21 discrete states: trips, dwell timers on the monotonic clock, hysteresis, valve states, staging,
pulse modulation, `crew_location`, `rcs.safety_state`, `gnc.maneuver_state`, `structure.pyro_fired`,
`power.lcl_tripped`. Sub-tick event queue with integer-microsecond stamps (`plant.md` §5). Irreversible
events happen exactly once or refuse honestly. **Accepts:** every protection action fires on its
evidenced threshold with hysteresis, through the real executive; a latched state on a delayed cycle has
hysteresis (linter rule 5).

### WP06 — thermal, cabin, consumables, propulsion feed

The remaining lag, stock and algebraic rules in thermal, eclss, consumables and propulsion feed.
Stocks use the residual accumulator and exact integer transfers (`plant.md` §4); every flow declares a
minimum magnitude. **Accepts:** conservation with non-zero transfers and external sources and sinks;
the nominal cabin leak happens below instrument precision; zero crossings raise events and record a
shortfall.

### WP07 — orbit, attitude, navigation, propulsion dynamics

The deepest hole. Rigid-body 6-DOF: position, velocity, quaternion, body rates; semi-implicit or
Verlet in coast, RK4 in burns; quaternion renormalised every tick (`plant.md` §3). Orbit propagation
(`gnc.orbital_state`), navigation covariance (`gnc.nav_covariance`), attitude driven by RCS torques
(`E-RCS-DYN` with a sensitivity), control allocation (`rcs.attitude_error`), main-engine burns.
**In flight:** slice 1, the orbit propagation rule for `gnc.orbital_state` (and the attitude/body-rate
drive if it falls out), taken by the Repo readiness thread on 2026-10-15 in worktree `vehicle/wp07-orbit`;
vehicle code and tests only. It can be accepted against an analytic orbit before WP03 supplies the
mission's real state vector (`mission.yaml.initial_state.position_xyz_km` is `UNCONFIGURED`).

**Accepts:** two-body propagation against an analytic orbit over the mission horizon within the
published precision; torque-free rotation conserves angular momentum; a reference burn reproduces its
Δv within the evidenced tolerance; the 6-DOF integrator class is added to the plant and the linter.

### WP09 — execute faults; measured evidence

Faults scheduled by `tools/faults.py` (128 declared, 15 failure chains) are injected into hidden truth
and change physical behaviour; hazard faults accumulate `∫λ dt` against a pre-drawn `Exp(1)`. The
instrument layer turns truth into published evidence with noise, bias, quantisation, saturation,
stuck, dropout and lag; **the quality-assignment function's signature does not contain the fault
state** (`plant.md` §7). Crew perception is computed before the GM composes, which needs the display
contract `crew_diode.md:42` says was never supplied (conflict D-06). **Accepts:** each fault changes
its intended mechanism; a silently biased sensor stays `GOOD`; no window carries a fault label,
seed or truth.

### WP10 — conservation and cycle accounting

`assert_conservation` with an exact integer residual on every transfer; energy as a tolerance band and
trend, never an assertion (`plant.md` §4, §9); the ledger and the observation published as a pair.
**Accepts:** the assertion executes on non-trivial transfers (not vacuously on empty ledgers); a
deliberately leaking transfer fails it.

### WP11 — coverage and the complete-vehicle gate

The coverage matrix: every applicable state, phase, configuration, command effect, fault and
observation route, each linked to its requirement, implemented consumer, independent reference and
deployed-path test. Intentionally forbidden commands close by their rationale and an executable
refusal. **Accepts gate V:** `check_vehicle.py --strict` exit 0, no executable-state gaps, and the
matrix complete with independent physics, protection, conservation, fault and instrument checks.

## M4 — accepted mission (WP12)

The full 192-hour nominal mission (34,560,000 ticks at 50 Hz) and the specified degraded and crisis
cases through the same executive; expected terminal outcomes, including a designated unrecoverable
crisis reaching its outcome; deterministic replay (byte-identical per-tick hashes, same build and
platform); restart continuity; measured live and replay timings ([05-performance.md](05-performance.md)).
A bounded phase-spanning run precedes the expensive full run. **Accepts gate M**, signed off by the
operator.

## M5 — release and handoff (WP13)

A durable acceptance archive with the manifest `release.md` requires (source SHAs, hashes, versions,
seed, clock policy, invocations, outcomes, raw traces, checksums, limitations, reviewer sign-off); a
release tag at the exact SHA where V and M passed; and the chassis's adoption of that SHA with its
complete gate and live probes ([04-integration.md](04-integration.md)). Gate E (experiment apparatus)
is then the chassis's and the operator's.
