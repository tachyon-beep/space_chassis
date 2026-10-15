# Operationalise the experiment: assessment and delivery plan

**Status:** proposed, plan-only; no implementation or campaign authorised by this document.

**Goal:** Reach a reproducible experiment in which ten isolated, self-modifying agents control one functioning vehicle through the frozen diode contract, with independently checked mission outcomes and a complete operator record.

**Architecture:** Keep the chassis, vehicle and evidence boundaries. Build one authoritative vehicle executive behind the per-agent directories; make it drive the physical plant, faults, clocks and instruments. Keep fleet coordination and mission strategy for the agents to invent. Improve campaign survival on the chassis side without importing vehicle code there.

**Tech stack:** Python >=3.12 on the host; current image uses Python 3.13. Operator services remain standard-library-only under the existing rules, with the existing chassis OpenAI/httpx model-client exception preserved. Vehicle tools deliberately use PyYAML. Any new runtime dependency or implementation language is a separate design decision, justified by profiling rather than assumed here.

**Prerequisites:** initialized vehicle submodule; local Python test dependencies including PyYAML; permission for local Unix sockets; Docker/Compose for later deployment gates; an offline Rust registry for the agent image. Do not run host preparation against existing state, replace environments, start the fleet, or read model credentials as part of executing the assessment.

**Execution:** Implement reviewed work packages separately. Use the existing Filigree workflows, sentence-style tests, and per-repository commit rules. Re-read the relevant package against the current source before starting. The existing lifespan plan is input to re-plan, not a code patch to copy wholesale.

## 1. Assessment at the inspected checkout

Assessment date: 2026-10-03. Chassis `fa43b25b0fd7d88a3f5e7feb3338e190078517ce`; vehicle `dd79e7608c931df9e5273824a3b2b9f396cb7cb7`. Both began clean on local main. This is a dated snapshot, not a claim about current remote heads or future readiness.

There is substantial local rigor: a linter exercised against broken copies, explicit provenance and refusal rules, deterministic bounded plant tests, and tests for recorder/recovery/containment structure. The weakness is that those checks largely validate declarations and partial mechanisms. They do not establish a complete vehicle or the integrated experiment. Code volume, prose volume, test count and a normal linter exit of zero are unsuitable project-completion measures.

| Area | Evidence at this checkout | Assessment |
|---|---|---|
| Vehicle definition | Eleven domains; 148 channels, 139 states, 58 verbs; normal linter composes | Substantial authored model and vocabulary |
| Finished configuration | Strict linter exits 2; 273 debts: 195 literal unset values and 78 prose obligations | Not complete |
| Runnable plant | 52/139 states advance; 27 await values, 15 edges, 45 rules | Partial reference plant |
| Configuration versus execution | 108/139 states fully configured, but only 52 advance | Configuration completion is not executable completion |
| Served vehicle | Console answers commands and publishes a bounded ring; cycle does not call physical step | Working interface, incomplete vehicle service |
| One vehicle for the fleet | Service launches a console per slug; every console owns its own state map | Shared authoritative vehicle absent |
| Physical telemetry | Console frames publish its value map; full truth-to-instrument-to-published-evidence path not integrated | Experiment observability incomplete |
| Mission runner | Bounded samples report gaps and can exit 0; full 192h mission is cost-gated | Diagnostic tool, not successful flight acceptance |
| Chassis survival | Recorder, runtime, repair ladder, pump, monitor and review exist; long-life critical paths still missing | Campaign not ready |
| Live deployment | `docker compose ps --all` reports no project containers | No current live-stack acceptance |
| Automated delivery | Neither repository has a checked-in CI workflow; broad image dependencies are not locked | Reproducibility/release gate absent |

The 52/139 figure is approximately 37% of declared states executable in the measured tick. It is **not** a percentage completion estimate for the whole project: a held mode can be executable while one missing trajectory or bus solver blocks much of a mission. Likewise 108 configured states (about 78%) do not mean the vehicle is 78% finished.

### Evidence that changes the completion judgment

- `containers/serve_vehicle.sh` launches one `tools/console.py` process per slug. `Console.__init__` creates `initial_values(world)` per instance; `Console.apply` updates only that instance. A bounded two-window demonstration changed A's bus tie to closed while B remained open, even with both constructed from the same loaded World. The fleet currently does not command one shared physical state.
- `tools/console.py:Console.cycle` settles and claims commands, resolves them, increments a counter and publishes. It never calls `plant.step`. Its phase stays fixed. `--plan` generates a scenario fault plan, but the live cycle does not execute that plan.
- `tools/plant.py:step` has a real derived-order walk and sub-tick command effects, but effects validation, conservation, instrument production and several executive responsibilities remain delegated or stubbed. The rigid-body dynamics branch only implements a scalar delta-v rule, not the required general orbit/attitude integrator.
- `plant.md` asks for exact stock-transfer conservation and a physical/evidence boundary. No `assert_conservation` implementation is invoked; no current coupling edge declares `conserve`. An assertion with no covered transfers would be a vacuous acceptance gate.
- Root tests and the endurance harness exercise important mechanisms, but the harness uses a stub model and never flies the physical vehicle. Scenario identity/fault-plan tests and the contract probe do not prove nominal/degraded/crisis mission success.
- The existing long-life plan describes absent mechanisms: total request budgeting, tool-output bounds, safe handoff/checkpoints, compact/reset, persisted ladder and run-rate protection. Two prior fixes are present: chronological resume and removal of stored recap frames. Reuse those; do not redo them.

### Validation performed for this assessment

Current normal/strict lint, readiness, build order, bounded determinism and mission diagnostics were rerun. The 50-tick mission diagnostic reproduces the same 87 gaps from the first tick, with deterministic bounded repeats; it does not traverse all eight phases. Its timing under concurrent tests is load-sensitive and is not a production benchmark.

Full-suite and affected-area test results are recorded in the final validation update below. Initial root-suite operator failures occurred because this sandbox denies Unix socket binds. A socket-enabled rerun of the end-to-end and review groups passed all 37 tests, then the complete socket-enabled four-worker root suite passed all 445 tests with no skips. Existing tests pass while the physical/integrated acceptance gaps described above remain.

Historical scratch completion reports, prior endurance reports and saved fleet records were used for context only. Saved status reports three full context windows and fault exits, but there is no running stack; these are historical symptoms, not a fresh live health check. No full mission, new containment run, paid model call or fleet campaign was performed.

## 2. What green means

Use separate gates. Passing development checks must never advertise experimental readiness.

| Gate | Required evidence | What it permits |
|---|---|---|
| G0 — reproducible development | Clean checkout of both SHAs, explicit dependencies, all required tests collected, lint and compose parsing pass; ordinary vehicle linter exit 0 | Continue development with known, explicit debts |
| G1 — integrated vehicle slice | Two windows command one authoritative state through the production executive; deterministic conflicts and command receipts; clocks and measured evidence come from the stepped plant | Demonstrate integration using an explicitly incomplete scratch fixture |
| G2 — functionally complete vehicle | Strict lint exit 0; every declared state executable across every applicable phase/configuration; all intended command effects; independently checked physics, conservation, faults and instruments | Run functional mission acceptance, not the agents yet |
| G3 — accepted vehicle and campaign substrate | Complete 192h/50Hz mission under scripted control with no unresolved state gaps; nominal/degraded/crisis acceptance, deterministic replay, measured live and replay performance; chassis survival/restart/record gates | Operational stack preflight; paid-model smoke additionally requires P7 containment and stub deployment checks |
| G4 — operational experiment | Built immutable images and preserved run manifests; live containment and window probes; bounded one-agent smoke followed by ten-agent short trials; operator can observe, stop and restore | Longer experimental campaign |
| G5 — scientifically interpretable campaign | Preregistered question, fixed trial protocol/seeds/budgets, baseline control, objective outcome evaluator, reproducible traces and classified failures | Make claims about coordination, resilience or mission performance |

G5 does not require the agents to win every trial. A lost crew can be a valid recorded experimental result. Infrastructure corruption, independent per-agent spacecraft, missing physical behavior, hidden truth leaks or unrecorded inputs make a trial invalid instead. Green means the apparatus is ready and results are interpretable; mission success remains an outcome to measure.

Preserve the current full eleven-domain/192h objective. A smaller demonstrator is useful for G1 and cannot be relabelled G2/G3. The recorded operator direction says the fleet waits for functional completion and vehicle scenarios. Relaxing that scope, the evidence standard, or the mission/replay performance objective requires a documented operator decision.

## 3. Delivery order and bounded work packages

Each package ends with observable behavior, relevant focused tests, then the enclosing gates. No package is accepted on changed documentation or a falling debt count alone. Package descriptions give the target and acceptance interface; detailed numerical physics code is intentionally deferred until its inputs and independent oracle are established. This is an operational programme plan, not an executable 273-debt patch.

### P0. Establish the baseline and turn acceptance gaps into a backlog

**Owner/repository:** chassis coordinates; vehicle keeps its own local tests.

**Files:** `pyproject.toml`, `Dockerfile.agent`, `requirements-agent.txt`, `scripts/build_registry.sh`; vehicle `pyproject.toml`; new `docs/experiment-acceptance.md` and `scripts/check_development.py`; proposed `.github/workflows/chassis-checks.yml` and vehicle `.github/workflows/vehicle-checks.yml` after dependency setup is specified.

**Work:**
1. Record both commits, Python/tool/library versions, test collection counts and skip reasons in an assessment manifest.
2. Create a reproducible development environment and immutable build inputs. Record base-image digest, resolved Python dependencies/system packages and offline-registry manifest; keep development dependencies separate from operator runtime dependencies. Rebuild from a fresh environment to prove the manifest is sufficient.
3. Keep normal lint as a development gate while debts exist. Add a separately failing readiness report for strict lint/state coverage/integration; never configure a successful development job to imply a finished vehicle.
4. Convert the derived value/edge/rule worklist and verified integration gaps into bounded Filigree packages with owners, blockers, tests and completion evidence. Retain existing lifespan issue IDs; do not claim unrelated ready work. Link vehicle work without mixing commit custody.
5. Specify first integration regressions: two agent windows observing one bus tie, a console cycle consuming a physical tick, and an executed fault changing observable evidence. Capture bounded failing reproductions in gitignored scratch as P0 evidence. Each production regression lands with its implementation in P1/P4: demonstrate red locally, then pass the full required suite before committing that package. P0 can pass the development baseline while its readiness report explicitly fails G1/G2; do not commit intentionally failing or permanently expected-failing tests to make a release look green.

**Gate:** G0. Exact current commands are in section 5. Required vehicle collection must not silently disappear via optional PyYAML skips. CI records test results and readiness failures separately. Test-count and README pins remain consistent.

### P1. One executive, one vehicle, many ingress directories

**Depends on:** P0 acceptance contract.

**Owner/repository:** vehicle; chassis wiring only in a separate change.

**Files:** vehicle `tools/console.py`, `tools/plant.py`, proposed `tools/executive.py`, `tests/test_vehicle_config.py`; chassis `containers/serve_vehicle.sh`, `tests/test_vehicle_reconciliation.py`, `docker-compose.yml`, `docs/deep_research/integration/reconciliation/README.md`.

**Work:** separate the per-slug file adapter from authoritative state ownership. One executive owns the plant state, mission clock, accepted-input trace and shared conflict/interlock/event state. It claims every agent ingress and writes attributed receipts/evidence back to each window. Keep the frozen directory contract and its at-most-once intake semantics. The executive's receipt ordering implements the existing vehicle conflict policy; it does not assign fleet roles or supply a fleet dispatcher.

Give the vehicle service a proposed private durable `/vehicle-state` mount, backed by an isolated run-specific host directory or named volume that no agent mounts. Current `/diode` is agent-writable and `/tmp` is volatile, so neither can hold authoritative checkpoints/quotas/effect ledger. Persist state, event queue, integer clock, stock residuals, fault/RNG state and effect decisions against the configuration/run identity; `pending.json` in a writable window cannot be trusted as physical truth. Export operator evidence through a separately controlled path without publishing hidden truth to the fleet.

**Acceptance:**
- A command from window A produces a plant-state change observed through window B.
- Conflicting A/B commands in one tick produce one winning effect and an attributed refusal under the declared policy; identical recorded input order replays identically.
- Each accepted effect has one authoritative ID/tick/offset and outcome. Malformed batches, stale gates and irreversible arm-token rules are exercised across windows.
- Restart at intake/effect/receipt boundaries either preserves the committed effect and reports it, or explicitly records uncertainty; never silently reapplies an irreversible action. Decide and document crash guarantees that the frozen intake contract does not supply.
- Vehicle-internal restart data is not writable as authoritative truth by the agents; agent-facing mirrors remain inputs to no physical rule.

Recovery uses one coherent committed-tick generation tying physical state, residuals, event/fault queues, RNG cursor, input/effect ledger cursor, per-principal authority/allowance state and configuration identity together. Individually atomic files are not a transaction. Kill/fail-write tests cover each installation boundary and verify restart reconstructs the same committed tick. If a promised restart case cannot reconstruct an effect, its acceptance test fails; if an unexpected live incident leaves an effect unknowable, mark that trial invalid and retain evidence rather than inventing a flight outcome.

Bound per-principal batches, aggregate pending/deferred queues, per-tick ingest/receipt/publication work and disk growth. Verify one flooding, malformed or slow window cannot starve the shared engine, legitimate other windows or the physical clock. Limits implement operator ceilings and transport fairness, not mission roles or an agent coordination strategy.

**Gate:** G1 using a deliberately small test plant. This slice demonstrates command-to-physics-to-evidence integration before undertaking every remaining model rule. It is not a fleet campaign and not functional vehicle completion.

### P2. Close the data and coupling blockers with evidence

**Depends on:** P0; can proceed alongside P1 and chassis hardening.

**Owner/repository:** vehicle, with applicable reconciliation updates in chassis.

**Files:** vehicle `vehicle.yaml`, `mission.yaml`, `coupling.yaml`, `domains/*/{components,points,profiles,commands,fault_policy}.yaml`, `tools/check_vehicle.py`, `tests/test_vehicle_config.py`; parent reconciliation records only as applicable.

**Work:** classify every debt as source research, measured parameter, valid derivation, permitted explicit design choice, missing linkage or implementation rule. Group by blocked capability and dependency leverage, not file or raw debt count. For each research item record the required article/configuration, units, operating conditions, source location, and whether the source is actually applicable to this synthetic composite.

**Priority evidence blockers:**
- Converter incremental output resistance/source behavior for A/B bus voltage; this blocks much of the electrical ladder. Apollo fuel-cell averages or entry-battery resistance do not establish the synthetic converter parameter.
- CSM/LM-applicable thermal node-to-zone heat capacities, conductances and initial temperatures. The LM-3 citation does not supply CSM or LM-5 aggregates.
- RCS jet-system/path membership, applicable thrust transients/minimum impulse, lever arms, Y/Z mass properties and full docked-frame rotation, then a defensible allocation matrix.
- SPS helium feed/regulator flow, remaining valve/pump/sensor parameters, keyed LCL/breaker identity and initial panel positions.
- Remaining initial positions, including the forward EVA hatch, kept distinct from the docking tunnel hatch. Use the latest gap register to supersede older handover assumptions.

**Acceptance:** each closed item is sourced, independently re-derived or explicitly authorised as a model decision, and its runtime consumer is demonstrated. Absent applicable evidence remains a blocker. Keep frozen research unchanged; do not remove declarations, invent plausible values or weaken strict checks to eliminate debts.

**Gate:** complete evidence coverage for G2, measured by strict lint and capability coverage, not a predetermined number of easy debt closures. If required evidence cannot be obtained, stop that package with named blockers or bring an explicit scope/model decision to the operator.

### P3. Implement the missing plant rules in capability groups

**Depends on:** P2 inputs for each group; P1 needed for integrated acceptance.

**Owner/repository:** vehicle.

**Files:** `tools/plant.py`, `plant.md`, domain YAML and `coupling.yaml` as applicable; proposed `tests/test_plant_physics.py` in addition to the existing refusal suite. New test files must still keep all README/test-count/reconciliation pins honest. The current chassis reconciliation counter counts functions in the single referee file; extend it or distinguish that count from actual total collection when adding files, rather than reporting the old counter as whole-suite coverage.

**Packages, each separately reviewed:**
- P3a: electrical nodal/source/load solve, tie/battery/current relationships and keyed-load instantiation. Exercise load changes against an independent circuit solution and dimensional limits.
- P3b: discrete comparator/dwell/zero-crossing transitions, FDIR and protection ladders. Test ordering on both sides of sub-tick boundaries and closed-loop oscillation cases.
- P3c: complete thermal, cabin/life-support/consumable and propulsion feed/stock rules as their inputs become available. Test coupled step responses, depletion, pressure/temperature envelopes and shortfalls.
- P3d: actual orbital/rigid-body/attitude/nav dynamics, RCS allocation/pulses and phase/configuration/staging changes. Test analytic coast/burn/rotation cases, conservation and mode-appropriate integrators. Scalar accumulated delta-v is not an orbit.
- P3e: fixed-point stock transfers and declared algebraic-cycle treatment. Produce non-vacuous mass balances across source/sink/consumption ledgers and test accumulator behavior over long horizons. Account explicitly for open-system sources/sinks; energy has the declared tolerance/trend treatment rather than a false exact assertion.

**Acceptance:** every declared state advances or holds under its defined rule, with no unresolved gap in every applicable mission phase/configuration. Every command has its intended effect or an honest, tested refusal. The tick's ready set agrees with the actual runner. Independent physics oracles must not simply repeat a relation from the same YAML that the implementation reads.

**Gate:** G2's runnable-model half plus physics checks. A test that demands the current gap count is useful as a progress pin, not a completed-model acceptance test.

### P4. Connect mission clock, faults and measured evidence

**Depends on:** P1; complete acceptance depends on P2/P3.

**Owner/repository:** vehicle.

**Files:** `tools/executive.py` (proposed), `tools/console.py`, `tools/plant.py`, `tools/faults.py`, `mission.yaml`, `presentation.yaml`, `channels.yaml`; proposed `tests/test_vehicle_execution.py`.

**Work:** advance one authoritative 50Hz mission clock, enforce phase/configuration transitions, apply recorded agent/white-team inputs and scenario faults at exact ticks/offsets, and run truth-to-instruments-to-published-evidence rather than raw plant-state publication. Integrate required stochastic hazard/demand behavior; a printed fault schedule is not an executed fault. Build the existing posture/objective and GM mechanisms only where the frozen design requires them; do not add mission policy to the chassis.

Define `m` as simulated seconds per wall second and record the mission/wall epoch mapping, multiplier and every change as inputs. The mission advances independently of agent thinking and filesystem polling. Specify overload/catch-up, operator pause, downtime and restart policy before deployment: no implicit time dilation when a console blocks or publishing falls behind. Test late inputs and timestamp boundaries against that policy; replay consumes the recorded tick/offset mapping rather than sampling a fresh wall clock. A clock-policy breach is apparatus failure/invalid trial, not extra thinking time silently granted to the agents.

**Acceptance:** seeded fault produces a causal physical trajectory and diagnosable measured evidence; sensors show specified noise/lag/staleness/dropouts/quality without leaking hidden fault identity. Sample and publish clocks/rates, blackout/contact, ring gaps and losses are correct. Measurement truth is structurally unreachable by fleet code. Replay of one recorded seed/input trace has identical per-tick hashes on the supported same-build/platform tier, including phase boundaries, queued events and faults.

**Gate:** the observability/executive half of G2. This package must include event and restart behavior; a publishing loop that only increments frame numbers fails it.

### P5. Make the chassis survive the intended campaign

**Depends on:** P0; run parallel to vehicle work. Does not require starting agents against an incomplete vehicle.

**Owner/repository:** chassis; existing epic `space_chassis-c8e27e645c`.

**Files:** `services/chassis.py`, `services/supervisor.py`, `services/pump.py`, `services/recorder.py`, `services/common.py`, `services/fleet_monitor.py`, `services/review.py`, `tasks/duty.py`, `containers/{agent.env,entrypoint.sh}`, `.env.example`, `docker-compose.yml`, `scripts/status.py`, `brief/{WORLD,PROTOCOL}.md`; affected files in `tests/` and `endurance/`.

**Bounded packages in dependency order:**
1. Valid request/checkpoint lifecycle: complete a handoff tool protocol before checkpointing; bounded/pruned checkpoints with last-good recovery; validate adopted histories and carry metadata. Existing issues `f976098d48`, `8c5e97f029`, `833a01f2de`.
2. Honest request budgeting: recap, pinned content, schemas, retained tail and output reservation inside the actual model window; bound/spill tool output; truthful composition/rate telemetry. Existing `8da4399e69`, `3622348dc9`, `f83364fe22`, `29d9c64d2d`. Verify the selected provider's current client/model contract before specifying reasoning-token behavior.
3. Recovery that terminates faults: persist ladder history; detect short handoff/crash loops; distinguish environmental waiting from product faults; archive an irrecoverably poisoned conversation only under the documented boundary decision below. Existing `835d551619`, `3cb643af8e`, `d96d548f41`.
4. Agent lifespan control: explicit compact/reset/recap rewrite mechanisms and bounded memory bootstrap; no operator policy choosing when an agent should compact or reset. Existing `a5c2a27876`, `bbe02a114d`, `1dca8e8841`, `60a9b11711`.
5. Campaign bounds and durable auxiliary work: choose measured run/watchdog defaults; test pump once/interval/keepalive state after process/container restart; persist or explicitly bound recorder restart effects on spending limits; bound storage while preserving evidence and run identities. Existing `80382730d2`, `420d18b7fa`, `13599e63b4`, `639443e993`, plus verified new findings if needed.

**Acceptance:** forced handoff, crash, malformed tool history, oversized output, upstream outage, poisoned checkpoint, supervisor/pump/recorder restart and code repair preserve required private memory and operator evidence. No permanent fault/restart loops, duplicated one-shot job or unaccounted spending. Budget-stop exit remains 42; exit vocabulary remains shared. Operator can distinguish active work, waiting, gaps, exhaustion and restart loops from the record.

Exercise pump once/interval/keepalive jobs across an actual new process, including spent-job replay, future deadlines, orphan process identity and dead-pump detection; reading a saved dictionary is not a restart proof. Exercise concurrent recorder requests, reservation against agent/fleet ceilings, an oversized first request and reconciliation to actual returned token usage. Inspect recorded upstream requests to establish the effective ceiling, not just in-memory counters. Decide restart-surviving campaign budget semantics before the soak; these are mandatory gates rather than incidental dashboard polish.

**Gate:** G3 substrate. Start with focused property tests, then repair the endurance injector/verdict to confirm each requested injury actually happened and memory-survival is checked by content. Require a passing bounded ten-agent stub endurance run and restart tests, followed by an explicitly configured multi-hour substrate soak. The current `endurance/scenarios/long_haul.json` has a 900-second timeout and does not prove multi-hour survival; add a proposed `endurance/scenarios/campaign_readiness.json` with duration, faults, storage/spend limits and required content-integrity/recovery outcomes derived from the campaign target. A paid-model campaign is still later.

### P6. Prove full mission correctness and performance under scripted control

**Depends on:** P2–P4; container integration can use P5 afterward.

**Owner/repository:** vehicle acceptance core, chassis host/file-contract runner.

**Files:** proposed vehicle `tools/acceptance.py`, `tests/test_mission_acceptance.py`; chassis proposed `endurance/run_vehicle.py`, `endurance/vehicle_scenarios/{nominal,degraded,crisis}.json`; reuse `contract/diode_probe.py` and maintain cross-repository boundaries. Exact new adapter ownership must be confirmed before implementation; no operator import of vehicle libraries.

**Work:** deterministic scripted command traces exercise one complete nominal mission and defined degraded/crisis recovery cases through the same executive used in deployment. Separate scenario identity from demonstrated causal faults/outcomes. Exercise all phases and phase/configuration boundaries, full 192h/34,560,000 ticks, irreversible commands, contact loss, depleted resources, protection and crew outcome checks.

**Acceptance:** strict lint 0; no unresolved state gap; all expected effect/receipt/evidence checks; non-vacuous conservation; no truth leak; independent mission/outcome invariants; same input trace deterministic end-to-end. A successful flight is mandatory for the defined control baseline, while a designated unrecoverable crisis must reach its explicit expected terminal result.

**Performance:** profile before choosing optimisation. With `m` simulated seconds per wall second, live 50Hz operation requires the executive/tick and amortised publication/input overhead to meet `20ms / m` wall deadlines under ten-window load; 20ms applies at `m=1`. Record p50/p95/p99/max, queue ages, missed deadlines and overload-policy behavior, including floods and stalled file I/O. Replay separately retains the documented full-mission/300s target (about 8.7us/tick). A slow reference plant might meet real time yet miss replay by orders of magnitude; these are distinct gates. Current short loaded timings do not decide a language rewrite. Multi-rate instruments, cache/precomputation and compiled kernels are candidates only after correctness-preserving profiling; do not subsample conserved flows or slow the mission clock to hide missed deadlines.

**Gate:** G3 vehicle. Any revision of the 300s goal is an explicit operator-approved design change. Do not spend an overnight full run merely to rediscover the known 87 gaps: require G2 and a bounded phase-spanning proof before the expensive run.

### P7. Release and validate the operational stack

**Depends on:** G3 vehicle and substrate.

**Owner/repository:** chassis deployment, vehicle immutable artifact.

**Files:** `Dockerfile.agent`, `docker-compose.yml`, `scripts/{prepare_host.sh,verify_containment.sh,status.py}`, proposed `scripts/check_release.py`, `docs/runbook.md`.

**Work:** build pinned images/submodule/configuration; create isolated run directories without overwriting the saved fleet; record manifests and boot/health diagnostics. Test entrypoint readiness of the empty Postgres/NATS/Redis capability floor. Validate all mount/network/credential/record boundaries against the running stack, not just YAML. Establish pause/stop/resume, restart, export/backup/restore and disk/spend alarm procedures.

**Acceptance:** zero unexpected failures in containment and diode probes; any skip named and justified. No new modelnet/windowside reach from agents or vehicle. Two-agent/ten-window physical state observation agrees. Runtime readiness detects a dead vehicle executive, recorder, pump or capability-floor service. An operator can safely stop a spending campaign and resume the same defined state or explicitly start a new trial, with the P4 clock/pause/downtime policy recorded. A restart cannot silently reset a phase, RNG stream, ledger or clock epoch.

**Gate:** G4 deployment. Launch order: isolated scripted vehicle, stub-model agents, one model-backed smoke, ten-agent short runs, then longer campaigns. Starting model calls, consuming real credentials or changing existing saved-lineage state is a later execution action, not authorised by this plan alone.

### P8. Freeze the experiment protocol and run interpretable trials

**Depends on:** protocol definition starts at P0; execution waits for G4.

**Owner/repository:** chassis experiment harness/reporting; vehicle owns hidden truth and outcome semantics.

**Files:** proposed `docs/experiment-protocol.md`, `endurance/run_experiment.py`, `endurance/report.py`, trial manifest and outcome schemas.

**Work:** write the specific hypothesis/question, unit of analysis and success/failure taxonomy before a long campaign. Specify model/provider identifier, prompt/seed-duty hash, fleet size, seed/scenario sample plan, initial state, mission clock multiplier, request/token/spend/CPU/storage limits, allowed operator interventions, timeouts and stopping criteria. Compare against a scripted control baseline; optionally one-agent/fixed-coordination baselines if needed for the claimed causal question. Provide controls as separate trials, never as a coordination layer silently supplied to the experimental fleet.

**Acceptance:** every trial binds both code/config commits and image digests to a complete input trace, effects/receipts, measurement sequence/loss accounting, lifecycle/turn usage and objective terminal result. Record clock multiplier/epoch, overload, pause and downtime decisions; verify reasoning time really consumes mission time under that contract. Separate vehicle loss/crew loss, coordination failure, model refusal/capacity, world infrastructure failure, timeout and operator intervention. Reports must not infer success from turns, uptime or agent self-reports. Replay and independent evaluator reproduce the result; an unreconstructable effect, missing input trace or violated clock contract makes the trial invalid rather than successful.

**Gate:** G5. Pilot duration and seed sample count are selected against measured cost and the question, then fixed before the campaign. No scientifically defensible trial count or calendar completion estimate can be supplied from the present partial plant and unresolved data requirements.

## 4. Decisions and blockers

These are explicit entry conditions for later implementation, not requests to approve unfinished work now.

1. **Model evidence/effectivity:** preserve current source/measurement requirements for synthetic converter and thermal parameters. Supply measurements/applicable source or formally authorise a changed model/fidelity objective. Older CSM/LM simulator data cannot silently become measured J-2 hardware truth.
2. **Conversation custody:** `AGENTS.md` says no repair rung touches the saved conversation, while an existing issue/plan proposes archiving irrecoverable conversations. Before implementing that policy, document an explicit bounded exception: preserve original checkpoint/diary/handoff/recap and record the reset reason; no broad deletion or memory erasure. Until settled, detection/quarantine reporting may be implemented, but that recovery behavior is not green.
3. **Performance objectives:** keep real-time and accelerated replay budgets separate. Retain the declared replay goal unless an operator changes it with implications for campaign/research turnaround stated.
4. **Recorder restart/cost custody:** define hourly and total campaign limits across recorder restarts, operator emergency stop and storage pressure. Current in-memory counters are not a total campaign budget.
5. **Existing runtime state:** do not reuse or clean historic volumes until classified and explicitly chosen for resume or archive; new proof runs get isolated roots.
6. **Scientific question:** preserve agent-invented coordination; choose which trial-level claim to test rather than treating generated output or mission rhetoric as a hypothesis.

Do not promise a date for full green until P0, the P1 tracer and the P2 research classifications establish the amount of code, attainable evidence and measured runtime cost. The immediate engineering work is bounded; some completion gates genuinely depend on unavailable data or an operator model decision.

## 5. Verification and release discipline

Current commands, run from the stated repository with a suitable isolated environment:

```sh
# chassis root: complete collected suite, including submodule referee
python3 -m pytest -q
uvx ruff check . --no-cache
docker compose --profile fleet --profile vehicle config -q

# vehicle root: independent gates; strict remains red until finished
python3 tools/check_vehicle.py
python3 tools/check_vehicle.py --strict
python3 tools/plant.py --readiness
python3 tools/plant.py --build-order
python3 tools/plant.py --determinism --ticks 50
python3 tools/plant.py --mission --ticks 50
python3 -m pytest -q

# chassis infrastructure proof; this is not a spacecraft flight
python3 endurance/run_local.py endurance/scenarios/short.json
python3 endurance/run_local.py endurance/scenarios/ten_agents.json
```

Success: full required collection, exit 0 for all development tests/lint/config; zero unexplained skips. Strict must exit 0 for vehicle-release readiness. Diagnostic mission exit 0 with reported gaps does not satisfy G2/G3. Do not use `--anyway --full` before the bounded prerequisites and measured cost are acceptable.

Future acceptance/release runners must fail on unresolved gaps and missing evidence, emit machine-readable results plus a concise report, and record exact commands, both SHAs, environment, elapsed time and exit status. Existing prose figures are snapshots; derive live worklists from tools.

Vehicle changes commit in the vehicle repository under its law. Chassis pointer and applicable reconciliation changes are separate commits. Required full suites precede commit per each repository's instructions. Local validation, commit, push, hosted CI, image build, deployment and campaign acceptance remain separate recorded states. No cleanup of frozen evidence, wholesale test rewrite or newly supplied fleet roles is part of this plan.

## 6. First execution batch

The first reviewable batch should contain P0's baseline/development acceptance definition and scratch reproductions, followed by the P1 shared executive tracer and P5's handoff/checkpoint/request-budget repairs. Production regressions land with their passing P1/P4 implementations. P2 source research proceeds in parallel as bounded questions. This tests the central product path and addresses immediate campaign-fatal faults before further broad generation.

At its checkpoint deliver: reproducible development evidence, a demonstrable two-window shared-state command/effect/evidence path, correct handoff/checkpoint/request behavior under stress, a classified model-data blocker register, and an updated measured plant worklist. This is intermediate progress, not full experimental green.

## 7. Final validation update

Completed 2026-10-03 at the inspected commits, Python 3.12.3:

- `python3 -m pytest -n 4 -q -o addopts='' --junitxml=.scratch/orientation-2026-10-03/temp/pytest-full.xml`: **445 passed in 638.36s, exit 0, zero failures/errors/skips**, using approved local Unix socket access and the already-installed pytest-xdist. JUnit shows 101 chassis-root tests (including 6 reconciliation tests) and 344 vehicle referee tests. This supersedes the interrupted socket-restricted run and the earlier 37-test socket-enabled subset. No dependencies were installed.
- `UV_CACHE_DIR=/home/john/space_chassis/.scratch/uvcache UV_TOOL_DIR=/home/john/space_chassis/.scratch/uvtools uvx --offline ruff check . --no-cache`: **all checks passed, exit 0**.
- `docker compose --profile fleet --profile vehicle config -q`: **exit 0**. This validates parsing, not live containment or vehicle execution.
- Current normal vehicle lint composes; **strict exit 2 / 273 debts** and **52/139 executable states** remain the vehicle-completion failures.
- Independent reality, architecture, quality and systems plan reviews resolved their blocking findings: P0 regression sequencing, private/coherent vehicle persistence, smoke/preflight order, suite-count interpretation, real pump/recorder tests, multiplier-aware clocks, uncertainty invalidation and bounded merged ingress. Approval is for this proposed programme; detailed package designs and numerical evidence still precede implementation.

Raw test log, JUnit and parsed summary are under `.scratch/orientation-2026-10-03/temp/`; the adjacent `.review.json` is the review synthesis. No runtime code, vehicle source, frozen evidence, issue status or existing runtime state was changed. No deployment, paid model trial or complete physical mission was performed. Tests/lint/parse are a sound starting baseline and do not close G1–G5.
