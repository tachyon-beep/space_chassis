# Current state, measured

As of **2026-10-15**, `main` @ `0036b88`, vehicle at `vehicle/` = `space_vehicle` `f75420c`. Every
number below was produced on that commit by the commands shown, in a cloud container on 2026-10-15.
The configuration corpus (`*.yaml`, `domains/`, `plant.md`) has not changed since vehicle `64fc58c`
(AUR-GOV-07 §1 checked that on 2026-10-10), so these figures hold for every vehicle commit since.

## What exists and works

| part | what it is | evidence |
|---|---|---|
| The configuration | Eleven domains (`domains/*/`), 139 states over 59 nodes, 81 coupling edges, 148 channels in 5 cadence classes, 38 withheld truths, 128 declared faults, 15 failure chains, 8 mission phases | `python3 tools/check_vehicle.py`: "COMPOSES"; `plant.py --readiness` |
| The referee | `tests/test_vehicle_config.py`, 528 test functions, one file; CI on two Python lanes with zero skips (`vehicle/.github/workflows/development.yml`, not yet running at this repository's root) | `grep -c "^def test_" vehicle/tests/test_vehicle_config.py` |
| The linter | `tools/check_vehicle.py` (18,768 lines): vocabulary, channel resolution, unset values, budget, the schedule, the `plant.md` §11 refusals | its own output |
| The plant | `tools/plant.py`: the scheduler (total order over nodes, Gauss-Seidel on the DAG), the lag, stock and scalar integrator classes, the residual accumulator, the sub-tick event queue, canonical compare-point hashes, `step()` | `plant.py --determinism` prints two identical hash sequences |
| The executive and the window | `tools/console.py`: one process for every window, claim and arbitration across windows, receipts, the mirror, the ring, generated `HELP.md`/`README.md`; it steps the plant every cycle since WP01 | `console.py` `advance()` → `plant.step` (vehicle main); the contract probe passes against it (`aurora/tests/test_vehicle_reconciliation.py`) |
| Persistence | Checkpoint format (#19), private `--state-dir` with lock, `serves.json` and journal segments (#20), the durable per-cycle record v2 and replay-from-record (#22), resume from checkpoint after any restart (#21), the compare-point encoder (#24) | vehicle PRs #32, #33, #38, #41, #31 |
| Mass and Δv closure | SPS 12.9 % reserve, LM DPS 7.4 %, APS 4.9 % | `check_vehicle.py` |
| Information rule | No window carries scenario, seed, fault plan or truth; the agents' image carries nothing of the vehicle | vehicle #36, #37; chassis plan 8 |

## What does not exist yet

### A tick advances 52 of 139 states

```
$ python3 tools/plant.py --build-order
139 states, by what blocks them:
    52   37 %  ready now — the states a real tick advances
    27   19 %  owes a value — the cheapest to close, and the debt count already tracks them
    15   11 %  owes an edge — a coupling with no sensitivity, or a state nothing drives
    45   32 %  owes a rule — `algebraic`, `discrete`, `dynamics` or `hazard`: domain code
```

The bucket is derived by running one tick and following each refusal to its root, so it says what
a tick cannot do, not what a declaration lacks (`plant.py` `build_order` docstring). By domain:

| domain | states | advance | owe a value | owe an edge | owe a rule |
|---|---:|---:|---:|---:|---:|
| thermal | 24 | 16 | 5 | 1 | 2 |
| eclss | 17 | 9 | 1 | 6 | 1 |
| consumables | 10 | 6 | 1 | 2 | 1 |
| structure | 10 | 5 | 1 | 0 | 4 |
| power | 13 | 5 | 4 | 1 | 3 |
| propulsion | 10 | 4 | 2 | 1 | 3 |
| comms | 10 | 3 | 2 | 0 | 5 |
| rcs | 13 | 2 | 4 | 0 | 7 |
| gnc | 12 | **1** | 2 | 3 | 6 |
| avionics | 13 | **1** | 3 | 1 | 8 |
| crew | 7 | **0** | 2 | 0 | 5 |
| **all** | **139** | **52** | **27** | **15** | **45** |

The 45 rules owed, by the class of state: 21 discrete, 10 algebraic, 7 stock, 4 lag, 3 dynamics.
The full list with each state's root cause is [03-domain-gaps.md](03-domain-gaps.md).

### The declaration is incomplete in 273 places

```
$ python3 tools/check_vehicle.py            # COMPOSES, with 273 declared debt(s). exit 0
$ python3 tools/check_vehicle.py --strict   # exit 2: honest debts remain (1, 3 or a crash would be a failure)
$ python3 tools/plant.py --readiness
states fully configured   108 / 139
states with a debt         31 / 139
edges with a sensitivity   69 / 81
UNCONFIGURED scalars      195
```

Of the 273 debt lines, 142 are `UNCONFIGURED` scalars and the rest are declared open debts in
prose. By file: `coupling.yaml` 46, `vehicle.yaml` 17, `mission.yaml` 9, `channels.yaml` 8,
`presentation.yaml` 6, and the rest across `domains/*/`. Two are worth naming because they block
flight dynamics outright: `mission.yaml.initial_state.position_xyz_km` and `velocity_xyz_m_s` are
`UNCONFIGURED`, so there is no state vector to propagate even once WP07 writes the propagator.

### Flight dynamics

`gnc.orbital_state` and `gnc.nav_covariance` have no rule; `gnc.attitude` and `gnc.imu_platform`
are dynamics with no incoming edge, so nothing drives them; `gnc.body_rate` is driven by `E-RCS-DYN`,
which has no sensitivity; `rcs.thruster_thrust` "is a `dynamics` state whose rule is not the scalar
one this plant implements" (the plant has `dv/dt = F/m`; `plant.md` §3 asks for 6-DOF with Verlet in
coast and RK4 in burns). There is no orbit, no attitude and no thrust vector. The mission's phase
ladder still advances, because phases are tick ranges (`plant.py --mission`), not trajectory events.

### Faults

128 faults and 15 failure chains are declared and `tools/faults.py` draws a schedule from the master
seed. The console uses it for `--plan` and to place the faults in the run record; **no fault changes
a physical state**, because WP09 (execute faults) has not started and `faults.py` writes nothing into
truth. The instrument layer that would turn truth into evidence under a fault (`plant.md` §7) is the
same package.

### Speed

```
$ python3 tools/plant.py --mission --ticks 500
500 tick(s) x 1 run(s) in 1.781 s per run = 3,562 µs/tick
the declared mission is 34,560,000 ticks, which at this rate is 34.19 h of wall clock
  — 409x the 8.7 µs/tick budget plant.md §10 sets
```

That is with 52 states advancing and no instruments sampled. Against the binding live target (20 ms
per tick at `m = 1`, `vehicle/docs/completion.md`) the plant has about 5× headroom today;
against the deferred replay target it is two and a half orders of magnitude out
([05-performance.md](05-performance.md)).

## The 2026-10-04 defects, re-checked

The vehicle-to-green programme listed six boundary defects reproduced at chassis `fa43b25` with the
vehicle at `9080b05` (`docs/plans/2026-10-04-vehicle-to-green-evidence.md`). Their state now:

| defect (2026-10-04) | now |
|---|---|
| One console per window; shared configuration, not shared state | **Fixed.** WP01 (#17): one executive serves every window; `serve_vehicle.sh` `exec`s one `console.py` with `--slug` repeated (`chassis/interface.md`) |
| The console loop never calls `step()` | **Fixed** on vehicle main: `console.py` `advance()` steps the plant each cycle. (True of the chassis's pinned `dd79e76` until Phase B lands) |
| Synthetic timestamps and raw state in frames | **Partly.** Frames come from the stepped state; the instrument model (noise, lag, quality) waits on WP09 |
| Closed gate and zero allowance still admit a command; static capability checks | **Fixed** for the executive: revalidation at effect time (ADR 0001; WP01). Physical consequence of most commands waits on M3 |
| `ask_crew` has no target and returns generic success | **Open.** Crew is 0 of 7 advancing; the display contract D-06 is still unsupplied |
| Restart restores metadata and resets physical values | **Fixed.** #21: one coherent world generation from checkpoint and record; K2 fallback; engine identity check |
| Armed `lm_undocking` consumes its token and changes nothing | **Open** until WP05/WP07 give staging a physical effect; the token lifecycle (`structure.arm_state`) owes a rule |
| Agents mount all of `/diode` writable; image carries the vehicle | **Fixed.** Per-slug binds (chassis `adf38d6`); separate images (plan 8); window identity moved to the root record (#36) |

## What the chassis runs today

`aurora/` pins the vehicle at `dd79e76` in its reconciliation tests and its image bakes whatever
`vehicle/` holds at build time. `dd79e76` predates WP01: one console per slug, no `/state`, no
stepping. Phase B (`vehicle-adoption`, P and R2c) moves the chassis to the stepping vehicle and is
staged on John's machine ([04-integration.md](04-integration.md)).

## Reproduce

```sh
cd vehicle
python3 tools/check_vehicle.py; python3 tools/check_vehicle.py --strict
python3 tools/plant.py --readiness
python3 tools/plant.py --build-order
python3 tools/plant.py --mission --ticks 500
python3 -m pytest -n auto -q -o addopts=''          # the referee; one test needs > 13 GB, see 06-verification.md
```
