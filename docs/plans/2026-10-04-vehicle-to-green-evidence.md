# Evidence for the vehicle-to-green programme

Dated local planning evidence, collected 2026-10-03 UTC for the 2026-10-04 programme. This is not a live readiness dashboard. The [programme](2026-10-04-vehicle-to-green-programme.md) contains proposed work; the [independent review](2026-10-04-vehicle-to-green-review.md) records its challenge review and disposition.

## Baseline preserved

| Item | Observed starting value |
|---|---|
| Chassis HEAD | `fa43b25b0fd7d88a3f5e7feb3338e190078517ce` |
| Parent's recorded vehicle gitlink | `dd79e7608c931df9e5273824a3b2b9f396cb7cb7` |
| Working vehicle HEAD | `9080b0558bb90e6a291fb344430883f6a23a0e1e` |
| Chassis status | Modified `docs/deep_research/vehicle`; untracked `docs/plans/` |
| Vehicle status | Clean |
| Existing untracked plan SHA-256 | `6bd0971ab1414723e295ae2e050f757c5546dc849c6d9bde51f2107bcd6821a4` |
| Existing untracked review JSON SHA-256 | `8303a8ee500e72ea9e1232cb7e35405022b538a5f9b1489319cdaf28a7621a1e` |

The old files are `2026-10-03-operationalise-experiment.md` and `2026-10-03-operationalise-experiment.review.json` in this directory. They and the vehicle pointer were preserved. The new programme does not inherit their approval status or their full-suite result. The raw initial inventory is [starting-baseline.json](/home/john/Documents/Codex/2026-10-04/task-5/starting-baseline.json).

## Inputs read and authority checked

- Both repository `AGENTS.md` files; chassis `docs/design.md`, `docs/diode-contract.md`, existing plan/review and relevant lifespan control flow.
- Vehicle `ROADMAP.md`, `CONTRIBUTING.md`, `docs/completion.md`, `docs/evidence.md`, `docs/release.md`, `docs/decisions/README.md`, current development workflow and decisive console/plant paths.
- Prior [SPACE_ASSESSMENT.md](/home/john/Documents/Codex/2026-10-04/task-3/SPACE_ASSESSMENT.md), SHA-256 `51973942745dea947475a36145e85a4faa95ac28cb3bd88cd4d21ea858c4468c`.
- Prior [astra-boundary-check.py](/home/john/Documents/Codex/2026-10-04/task-3/astra-boundary-check.py), SHA-256 `72500bac4b4a5a7be137d7a34e8ef26c694c4862b517d67fc5e401f56c1b2400`, and its recorded output. Read before execution; it creates temporary console directories and performs no mission or network calls.
- Historical scratch completion/gap material used as context, especially `FACT_GAP_REGISTER_2026-09-23.md`; not treated as current acceptance. No primary historical numerical source was newly validated.
- Solution-architect and systems-thinking router/relevant reference guidance; systematic-debugging at `/home/john/.agents/skills/superpowers/systematic-debugging/SKILL.md`; repository-local Filigree skill. The architecture guidance is scaled to John's requested programme, not represented as a completed detailed architecture package.

## Fresh checks

All Python checks used `PYTHONDONTWRITEBYTECODE=1`; pytest disabled its cache provider. Outputs went to the task workspace, and console reproductions wrote only temporary directories. Installed Python was 3.12.3. No dependencies were installed.

| Invocation and working directory | Observed result | Scope |
|---|---|---|
| `python3 tools/check_vehicle.py --strict`, vehicle root | Exit 2; composes with 273 declared debts | Honest incompleteness; not a finished build |
| `python3 tools/plant.py --readiness`, vehicle root | Exit 0; 139 states, 195 unset scalars; 52 advance/hold, 87 gaps | One diagnostic tick, not a mission |
| `python3 tools/plant.py --build-order`, vehicle root | Exit 0; ready/value/edge/rule buckets `52 / 27 / 15 / 45` | Derived worklist, not a completion percentage |
| `python3 -m pytest -q -p no:cacheprovider tests/test_chassis.py`, chassis root | Exit 0; all 22 offline tests pass | Runtime unit/functional subset only |
| Existing Astra boundary reproducer, run independently by verification agent | All six expected failures reproduced | Current defects confirmed, not fixed |
| `filigree session-context`, chassis root | Database initialization attempted write; `sqlite3.OperationalError: attempt to write a readonly database` | Tracker context unavailable; no claim/status update made |

Raw run manifest: [verification-results.json](/home/john/Documents/Codex/2026-10-04/task-5/verification-results.json). Raw outputs: [strict lint](/home/john/Documents/Codex/2026-10-04/task-5/strict-lint.txt), [readiness](/home/john/Documents/Codex/2026-10-04/task-5/readiness.txt), [build order](/home/john/Documents/Codex/2026-10-04/task-5/build-order.txt), [offline chassis tests](/home/john/Documents/Codex/2026-10-04/task-5/offline-chassis-tests.txt). These local artifact paths are provenance for this review; future acceptance needs the durable archive required by `vehicle/docs/release.md`.

## Mechanically rechecked source facts

References are at the exact baseline above. `vehicle/` below abbreviates `docs/deep_research/vehicle/`.

| Finding | Decisive source |
|---|---|
| Per-window physical state | `containers/serve_vehicle.sh:104–124`; `vehicle/tools/console.py:236` |
| Console loop does not advance physics | `vehicle/tools/console.py:814–847` |
| Synthetic timestamps/raw state | `vehicle/tools/console.py:967–979` |
| Authority mismatch | `vehicle/tools/console.py:614–629`, `773–794`; published variables/budget at `857–878` |
| Unsupported generic success | `vehicle/tools/console.py:586–590` |
| Checkpoint omits physical values | `vehicle/tools/console.py:333–369`, `914–934` |
| Irreversible event no-op | `vehicle/tools/console.py:681–687` |
| Writable all-window mount/common ownership/vehicle image | `docker-compose.yml:114` and repeated fleet mounts; `scripts/prepare_host.sh:89–92`; `Dockerfile.agent:63` |
| Instrument helper is only a partial projection | `vehicle/tools/plant.py:984–1127` |
| Conservation/instrument steps remain contracts/comments | `vehicle/tools/plant.py:2240–2243`, `2268–2270` |
| Handoff precedes tool-result append | `services/chassis.py:406–409`, `588–602` |
| Vehicle CI scaffold now exists | `vehicle/.github/workflows/development.yml`; `vehicle/requirements-dev.lock` |

The boundary reproducer observed 114 raw frame keys and zero registry keys, including `internal`, `csm_cabin_o2_kg` and `prop_main_kg`; an impossible-location crew query succeeded without evidence; false gate/zero allowance still changed bus tie; a second console remained unchanged; restart reset bus tie while retaining dwell; undocking consumed its arm token without changing the state hash. The producer's “success” message was not used as evidence of physical effect.

Corrections carried into the programme: do not treat `emit_frame` as a complete instrument model; do not claim live containment from YAML inspection; preserve at-most-once claim semantics and explicit lost-remainder behaviour; preserve the contract's `pending.json` path or decide compatibility explicitly; distinguish published code/model laws from hidden run-specific state.

## Limits and remaining blockers

No new full-suite run, live Docker stack, containment penetration test, full mission, benchmark, remote issue/CI query or paid model-backed trial was performed. Past full-suite claims in the prior plan are left attributed to that prior plan. No V/M/E gate was closed. Applicable electrical/thermal/flight numerical evidence, clock/durability decisions and later experiment scope/budget remain work, not resolved facts.

Only the new programme, evidence note and independent review are intended additions to `docs/plans/`. No source, frozen corpus/interface, vehicle file, prior plan, tracked pointer, issue status or runtime lineage was intentionally changed. Final publication includes a second hash/status check and a reread of the saved documents.
