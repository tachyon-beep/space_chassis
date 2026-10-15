# Performance: where the time goes, and the route if it is missed

As of **2026-10-15**, `main` @ `0036b88`. Decision D4 (`governance/decisions.md`): stay in Python;
live real time is the binding target; the 300-second replay is deferred to WP12.

## The two targets

| target | figure | source | status |
|---|---|---|---|
| **Live, binding.** One executive, ten windows, `m = 1`: every tick plus amortised window I/O inside `20 ms / m` | 20 ms per tick | `vehicle/docs/completion.md`, "Performance"; ADR 0002 A (m = 1) | **met with headroom at 52 states**: 3.56 ms/tick measured, plant only |
| **Replay, deferred.** The full mission (34,560,000 ticks) replayed in about 300 s | 8.7 µs per tick | `plant.md` §10 | **409× out**; deferred to WP12 (D4) |

The live target is what a fleet experiences: with `m = 1` and k = 5 ticks per cycle (ADR 0002 B),
the executive has 100 ms per cycle to step five ticks, claim and publish every window. The replay
target serves bisection of a divergent run and endurance campaigns, which the per-tick compare-point
hashes make cheap to localise even at slow replay (binary search to the first differing tick, then
structured comparison inside it, `plant.md` §6).

## Measured

```
$ python3 tools/plant.py --mission --ticks 500
500 tick(s) x 1 run(s) in 1.781 s per run = 3,562 µs/tick
```

Conditions: 52 of 139 states advancing; no instruments sampled; no window I/O; Python 3.12; a 4-vCPU
cloud container. A process-level restart costs about 5.5 s, dominated by YAML loading
(`vehicle/snapshot.md`); a checkpoint costs about 12 ms warmed every 50 ticks; 68 MB RSS for eleven
windows (#21's measurements).

## What will change it

| growth | effect on the per-tick cost | basis |
|---|---|---|
| 87 more states advancing (M3) | roughly 2–3× if cost scales with states advanced; the 6-DOF integrator (RK4 in burns, four evaluations) and the nodal electrical solve are the expensive ones | proportionality from 52 states at 3.6 ms; WP07's RK4 is four right-hand-side evaluations per tick in burns |
| the instrument layer sampling 148 channels (WP09) | the big unknown: naive per-tick sampling of every channel could dominate; sampling at each sensor's declared 0.2–10 Hz keeps it near free | `plant.md` §10: instrument-rate multi-rate "nearly free", 10–25× saving over naive |
| conservation assertions on every transfer (WP10) | small: integer arithmetic | `plant.md` §4 |
| ten windows' claim and publish per cycle | the measured 68 MB and sub-millisecond claims at #21 suggest small; `#23`'s `measure_clock` feasibility run is the test | `vehicle/records/2026-10-12-23-clock-seam-slot-request.md` §8 |

A plausible complete vehicle in Python lands at 8–15 ms per tick before any optimisation: inside the
live budget, with little margin, and with the instrument layer deciding which side of the line it
falls.

## The route, in order

1. **Measure first.** `#23` lands the fixed-rate scheduler and `measure_clock.py`; its feasibility
   run (10 windows, `m = 1`, 3,000 ring slots) is the first live measurement of the whole loop. Every
   WP that adds rules re-runs `plant.py --mission --ticks 500` and records the figure in its PR, so
   the trend is visible before it is a problem.
2. **Instrument-level multi-rate** when WP09 lands the instruments: sample each sensor at its
   declared rate, not every tick. `sample_time` and `publish_time` jitter are already in the model.
   Estimated 10–25× on the instrument cost (`plant.md` §10).
3. **Domain-level multi-rate** if still needed: thermal and consumables have time constants of minutes
   to hours. `coupling.yaml` already carries `accumulate` so that a slow consumer integrates a fast
   producer's flow rather than sampling it (`plant.md` §10). Estimated ~40 % of domain cost.
4. **Profile and fix hot spots** in the Python: the schedule walk, state staging and commit, hash
   encoding. Ordinary optimisation, no semantic change.
5. **A native plant core** (Rust; the image already carries a Rust toolchain for the agents) only if
   steps 1–4 leave live real time unmet. It is a port of `step()` and the integrator classes behind
   the same `Effects` seam, with byte-identical compare-points as the acceptance test. Not planned.

## What may not be done to get green

`completion.md` and `plant.md` §6 are explicit, and D4 does not relax them: no silent timestep change,
no hidden time dilation, no omitted ledger, no relaxed evidence. Overload is shed → dilate → hold with
the lag visible to the operator (ADR 0002 C, `#26`), never a quietly stretched second. Replay
equivalence stays byte-identical per-tick hashes on the same build and platform.

## Decision points that return to John

- If the complete vehicle misses 20 ms per tick after step 4, the choice between a native core
  (months) and `m < 1` (a slower-than-real-time world, which changes the research meaning of
  "thinking costs time") is his.
- If replay at WP12 is needed faster than the measured rate allows for the acceptance campaign, the
  300-second target is re-decided then, with measured figures.
