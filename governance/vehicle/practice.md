# Vehicle — practice: how the line is worked

As of **2026-10-10**, `tachyon-beep/space_vehicle` main @ `64fc58c`. The repository's own
`CONTRIBUTING.md`, `ROADMAP.md` ("Keep the programme honest") and `docs/{completion,evidence,release}.md`
are authoritative; this file records how they are applied in practice, and the hard-won rules that
are not written there. **Verify against those files before trusting this one.**

## Hard constraints

- **The vehicle never edits the chassis.** Compose, mounts, the serve script, chassis tests and the
  submodule pointer are the chassis line's; the vehicle states needs (`interface.md`) and the chassis
  decides. The frozen `docs/diode-contract.md` changes only with both lines adopting it.
- **Never work in the chassis's submodule checkout** (`/home/john/space_chassis/docs/deep_research/vehicle`,
  left on `codex/vehicle-delivery-scaffold` @ `8c6f71d`, pointer showing `M`) and never run
  `git submodule update` there. Vehicle work happens in **git worktrees** of that module's object store
  (`git -C <checkout> worktree add …`), in a session scratch directory, one worktree per branch.
- **Never `git stash`** (hook-blocked, and it hides work from other sessions). Never a broad `git add`.
- **Standard library only** in vehicle tools; no new runtime dependency without an operator decision.
- **Windows carry nothing the agents should work out for themselves** — no scenario, seed, fault plan,
  truth, or designers' diagnosis (owner, 2026-10-09). Clean agent-facing text as you touch it.
- **Ask John before** external publication, settings changes (e.g. branch protection, #15), release,
  deployment or a paid-model campaign. Respect platform denials; never route around one.
- **One owner per branch.** Two sessions (including two resumes of one conversation) must never commit,
  push or gate on the same branch or paths; agree an owner by message first, and give every scratch
  path a session-unique suffix. A shared worktree or evidence directory contaminates both runs
  (2026-10-10, #21).

## How a package lands

1. **Issue with observable acceptance** (child issues for anything broad; WP08's are #19–#30).
2. **Design before code** for anything stateful or cross-cutting: a decision record (`docs/decisions/`)
   or a design note; owner questions asked with a recommendation, never chosen silently when they are
   the owner's (operator-visible or fleet-visible behaviour, scope, targets).
3. **Independent design review** (two reviewers from different model families where possible); their
   findings become **binding addenda** to the note before implementation.
4. **Implementation** by an implementer agent in its own worktree: tests first (full-sentence names,
   reasoning docstrings, independent oracles — for resume and replay, an uninterrupted run's own
   per-tick compare-points, never the code path's own output), each test seen failing before its fix,
   focused commits `vehicle: <finding/outcome>`, a README round section above "## The invariants…"
   with the referee count before/after, dated ADR amendments.
5. **Gate at the exact head** in a detached worktree, on both lanes (below).
6. **Independent code review**: Codex (`gpt-6-astra`, high effort, read-only) and Claude Opus (with
   end-to-end probes); Fable when available. Findings → one consolidated fix brief with rulings →
   fix commits **on top** (no history rewrite once others cite a SHA) → a confirming review of the
   delta → re-gate.
7. **PR** with the body in the repository's voice, the local gate evidence posted as a comment;
   **hosted CI green** (≈ 45–50 min per lane; job timeout 90 min); **merge commit** (`gh pr merge
   --merge`) — merges are authorised once CI is green.
8. **After merge**: delete the branch and worktrees, archive evidence, update `snapshot.md`,
   `decisions.md`, `open.md` here, and tell the chassis on `space_chassis-93010ff54e` if anything it
   adopts changed.

## The gate (both lanes, at the exact SHA, in a detached worktree)

Environment: Python 3.12 and 3.13 virtualenvs built from `requirements-dev.lock` with
`--require-hashes` (`CONTRIBUTING.md`). Then:

```
python -m ruff check . --no-cache                 # exit 0
python tools/check_vehicle.py                     # exit 0, "COMPOSES, with 273 declared debt(s)" (count moves only with a recorded reason)
python tools/check_vehicle.py --strict            # exit 2 expected (honest debts); 1/3/crash = failure
python tools/plant.py --readiness                 # exit 0
python tools/plant.py --build-order               # exit 0
python tools/measure_clock.py --samples 10        # exit 0
python -m pytest -n 6 -q -o addopts='' -rs --junitxml=<evidence>/tests-<lane>.xml   # all pass, ZERO skips
```

Rules: never gate a worktree you are editing; never share a gate worktree or evidence directory
between sessions; an interrupted or aborted run proves nothing — say so rather than cite it; a test
that fails only under load is a defect to fix (make it load-robust), not to retry until green.

## Reviewers and their failure modes

- Codex runs read-only in a sandbox and often cannot execute filesystem tests; it reasons from source
  and in-memory probes — strong on integrity and ordering defects.
- Claude Opus with a scratch worktree runs end-to-end probes (SIGKILL/resume, stress) — strong on
  operator-visible behaviour and test quality.
- Agents can be cut off by usage limits mid-task: always check the worktree and branch state before
  trusting a report, and resume the same agent (it keeps its context) rather than starting fresh.
