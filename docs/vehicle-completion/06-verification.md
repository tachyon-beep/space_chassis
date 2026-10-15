# Verification: gates, CI and what counts as evidence

As of **2026-10-15**, `main` @ `{{MAIN}}`. The gates are the vehicle's (`vehicle/docs/completion.md`
D, I, V, M; E jointly with the chassis). This file says what each needs that does not exist yet, and
specifies the CI that D6 (`governance/decisions.md`) decided.

## The gates and their distance

| gate | requires | today | missing |
|---|---|---|---|
| **D** reproducible development | locked deps; lint 0; the whole referee, zero skips, both Python lanes; independent review | met per merged vehicle PR; **not enforced**: the vehicle's workflow does not run from this repository's root; no branch protection | root CI (below); branch protection (residual 3) |
| **I** integrated slice | the deployed-path executive advances one authoritative state; two windows command and observe it; deterministic arbitration and receipts; evidence from stepped truth | WP01 and `#21` deliver the executive, ingress, receipts and persistence; the console steps the plant | a gate-I record on the deployed path (the chassis's live vehicle checks after Phase B) showing a command in window A changing a stepped quantity seen in window B; honest instrument evidence (WP09) for "evidence from stepped truth" |
| **V** complete vehicle | strict lint 0; no executable-state gaps; every applicable phase, configuration and command effect exercised; independent physics, protection, conservation, fault and instrument checks | strict exit 2; 87 states blocked; no coverage matrix | M2, M3 in full; WP11's matrix |
| **M** accepted mission | the full nominal mission and specified degraded and crisis cases; expected outcomes; deterministic replay; restart continuity; measured budgets | replay-from-record and resume exist | WP12 |
| **E** experiment apparatus | exact SHAs; containment and diode probes; campaign-ready chassis; preflight; fixed protocol and evaluator | containment script and probe exist; no built image in the cloud yet | WP13 and the chassis's gate E work ([04-integration.md](04-integration.md) §8) |

## Root CI (D6)

`.github/workflows/` at the repository root, path-filtered so a documentation change does not run
the referee. The vehicle's existing `vehicle/.github/workflows/development.yml` is the template for
its job and keeps its exact steps (hash-locked install, lint, `check_vehicle.py`, the referee with
JUnit and the zero-skip check, the readiness diagnostic as an artifact).

| workflow | triggers on paths | jobs |
|---|---|---|
| `vehicle.yml` | `vehicle/**` | `check (3.12)`, `check (3.13)`: `cd vehicle`, `pip install --require-hashes -r requirements-dev.lock`, `ruff check`, `check_vehicle.py`, `pytest -n 2 -o addopts='' --junitxml`, zero skips; `readiness`: `check_vehicle.py --strict` (exit 2 tolerated and published), `plant.py --readiness`, `--build-order`, `--mission --ticks 500` as artifacts, so every PR shows the counts and the µs/tick |
| `aurora.yml` | `aurora/**`, `docs/design.md`, `docs/brief-claims.md`, root files | `lint`: `uvx ruff@0.17.0 check . && format --check .`; `tests`: `pip install -r requirements-dev.txt`, `pytest aurora/tests aurora/harness/tests aurora/recorder/tests aurora/pump/tests -n 4`; `compose`: `docker compose --profile fleet config -q` from `aurora/` |
| `docs.yml` | `docs/**`, `governance/**` | the doc guards: `pytest aurora/tests/test_retired.py aurora/tests/test_doc_claims.py aurora/tests/test_citations.py` |
| `live.yml` (manual, `workflow_dispatch`) | — | builds `space-chassis-agent:smoke` and the vehicle image, runs `pytest aurora/live`; needs a runner that can reach `deb.debian.org`; run before any adoption merge |

Known obstacles, each with its fix:

- **One referee test needs more than 13 GB**
  (`test_a_sub_tick_effect_lands_where_a_short_tick_would_have_put_it`): a GitHub-hosted runner has
  7 GB. The test is made to fit (a smaller horizon or a streamed comparison), never skipped; until
  then it is the one deselected test, named in the workflow with this reason.
- **The referee takes 30–45 minutes per lane.** Acceptable with `timeout-minutes: 90` as the
  vehicle's own workflow already sets; a `pytest-xdist` split by file is not available (one file), so
  the long-term fix is splitting the referee by domain, which WP11 wants anyway.
- **`test_journal.py::test_an_unreadable_shared_file_is_skipped…` fails as root.** CI runners are
  not root; the cloud container is. Documented, not changed.
- **The operator suite needs `openai` and `httpx`** (`requirements-dev.txt`, PR #2).

## What counts as evidence

From `vehicle/docs/release.md` and `evidence.md`, restated as the rule every PR follows:

- **A test is evidence of the property its name states**, at the SHA it ran at, with zero skips. An
  interrupted run proves nothing. A green badge proves the development gate only.
- **A physical rule is accepted against an independent reference**: an analytic solution, a
  published figure with its source and effectivity, or a reference implementation that is not this
  code. Comparing two runs of the same code proves determinism, not physics.
- **Conservation is checked on non-trivial transfers**: a ledger assertion that passes on empty flows
  is vacuous and WP10 refuses it.
- **A fault is accepted when it changes its intended mechanism** through hidden truth, and the
  window shows only what an instrument would show.
- **A value is closed with its provenance** (source, page, effectivity, units, bounds, consumer,
  validation case) in its canonical YAML home.
- **Acceptance artifacts live in a durable archive with a manifest** (source SHAs, hashes, versions,
  seed, clock policy, invocation, outcomes, raw traces, checksums, limitations, reviewer sign-off);
  CI artifacts expire and are development evidence only. WP13 establishes the archive; until then
  `governance/<stream>/records/` holds pointers and small files, never diffs of unqualified code.
- **Failed evidence is kept** beside the passing run.

## Review

One independent review per PR, from a different model family where possible; two for the window
contract, persistence and restart, the containment boundary, and text an agent reads
(`governance/practice.md`). Review rounds end when a round finds only P3 or cosmetic findings, which
are filed as one issue (the stopping rule, `vehicle/decisions.md` 2026-10-10). A physics reviewer is
named for each M3 package's acceptance, and it may not be the implementer.
