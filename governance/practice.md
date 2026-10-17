# Practice — how every stream works

As of **2026-10-17**, `tachyon-beep/space_chassis` `main` @ `b525b48`. Replaces the permission and
slot rules in `chassis/practice.md`, `vehicle/practice.md` and `coordination.md` (`decisions.md` D1,
D2). Each stream's own `practice.md` keeps only what is particular to it: the chassis's plan, review
and live-check cycle, and the vehicle's gate and evidence discipline. Where they disagree with this
file, this file wins; where `CLAUDE.md`, `AGENTS.md` or a test disagrees with it, they win.

## The loop

1. **Pick work** from GitHub issues on this repository, labelled by stream (`decisions.md` D10). Say
   you are taking it with a comment on the issue before starting; one owner per issue.
2. **Branch in a worktree**: `make worktree STREAM=<vehicle|aurora|governance> TOPIC=<topic>`, which
   gives `.claude/worktrees/<stream>-<topic>` on branch `<stream>/<topic>`. A branch touches only its
   stream's folder, except an adoption commit, which is the chassis's and may touch `vehicle/` pins.
3. **Design first** for anything stateful, cross-cutting, or that changes what an agent sees: a short
   note in the issue, or a decision record (`vehicle/docs/decisions/`, `docs/superpowers/specs/`).
4. **Test first.** Each behavioural change has a test seen failing before the fix. Test names are full
   sentences. No skip or xfail is added to get green.
5. **Run the stream's gate locally** (below), then **push and open a draft pull request** against
   `main`. Pushing and opening a PR need nobody's approval.
6. **CI green, then one independent review** (a reviewer agent from a different model family where
   available, or John). A second review only for the window contract, persistence and restart, the
   containment boundary, or text an agent will read.
7. **Merge** with a merge commit once CI is green and the review has no open blocking finding. The
   author may merge. Then update the stream's `snapshot.md` and `open.md` in the same or the next
   commit, and comment the merge SHA on the issue.

## Gates

| stream | gate before pushing | CI (once D6 lands) |
|---|---|---|
| vehicle | `cd vehicle && python -m ruff check . --no-cache && python tools/check_vehicle.py && python -m pytest -n auto -q -o addopts=''`; `check_vehicle.py --strict` exit 2 is expected, 1/3/crash is a failure | both Python lanes, zero skips, readiness diagnostic |
| aurora | `uvx ruff check . --no-cache && uvx ruff format --check . --no-cache` from the root; `python3 -m pytest aurora/tests -q`; image, compose or deployment changes also `python3 -m pytest aurora/live -q` where Docker can build | lint, operator suite, compose config |
| governance and docs | the doc guards: `python3 -m pytest aurora/tests/test_retired.py aurora/tests/test_doc_claims.py aurora/tests/test_citations.py -q` | doc guards |

An interrupted run proves nothing; say so rather than cite it. A test that fails only under load is a
defect to fix, not to retry until green.

## Still not allowed

These are safety and hygiene rules, not permissions, and D1 does not lift them:

- No secret in git, argv, logs or the smoke stack; never read a real `.env` (`.env.example` is fine).
- `governance/` never enters an image; agents join `worknet` only (`CLAUDE.md`, "the one hard rule").
- Windows carry no scenario, seed, fault plan, hidden truth or designers' diagnosis
  (`vehicle/decisions.md` 2026-10-09).
- A value with no evidence stays `UNCONFIGURED` (`vehicle/docs/evidence.md`); nobody fills a physical
  input with a plausible number to unblock a state.
- No `git stash` and no broad `git add` (both hide or sweep up another session's work); no rewriting
  history on a branch someone else has cited.
- Nothing on the internet is changed: research reads any domain, but no post, upload, sign-up or
  other write outside this project and repository (`decisions.md` D32).
- No root, mount or volume-image action on John's host, and no `prepare_host.sh` against his real tree.

## Still John's

Only these, because they spend money, change a setting only he can change, or act on his machine:

- any model-backed (paid) run, and the spend caps (`decisions.md` D16);
- repository settings: branch protection, archiving `space_vehicle`;
- host actions on his workstation: moving `volumes/`, `volume-images/`, `operator/`, `.env` and
  `llm_console_seed.json` into `aurora/`, killing processes, pushing local-only work;
- a change to the vehicle's objective (eleven domains, 192 hours, 50 Hz) or its evidence standard.

Everything else a stream may decide, recording it in its `decisions.md` as *coordinator* or
*governance*, open to his revision. A blocked lane's scope question with an obvious answer is the
coordinator's to answer and list to John (`decisions.md` D33); only a question without one waits on
him.

## Where work runs

Only in the cloud or on nyx (`decisions.md` D27). nyx is a Remote Control device for the project
(`nyx.foundryside.dev`, `/home/john/space_chassis`, D28); start a session there only when John asks
for work on nyx. Never start a device session on his Windows/WSL machine.

## Vehicle sprint (from 2026-10-17)

The vehicle is being burned down in parallel lanes, one per subsystem (D24, D25). The lane table,
the full rules and the running log are in
[`records/2026-10-17-vehicle-sprint.md`](records/2026-10-17-vehicle-sprint.md); who holds what now is
in [`status.md`](status.md). While the sprint runs these rules add to the loop above:

- **A lane is a project thread with one draft PR.** It edits only its own blocks in shared YAML: an
  edge belongs to the lane owning its target state, a channel to the lane whose prefix it carries.
- **Engine code (`vehicle/tools/plant.py`, `check_vehicle.py`, `faults.py`) belongs to the
  fault-injection lane.** Other lanes route engine needs through the coordinator, or land them as a
  small PR merged before the domain PR that uses them.
- **Merge order**: #45 (unpin), then #46 (ECLSS engine helper), then #47 (fault injection), then the
  rest rebase and merge when `required` is green. Figures are rewritten from the tools on rebase,
  never hand-merged.
- **Shared decision records take one dated section per verb.** ADR 0004
  (`vehicle/docs/decisions/0004-interlock-evaluation.md`) is being amended by ECLSS (#46), structure
  (#51) and possibly propulsion (#50): each lane adds its own dated, verb-named section and rebases
  over the others, never editing another lane's section.
- **The quiet-coast episode must stay green; its numbers may move** (D29).
- **Fidelity**: "preference more fidelity where it doesn't start creating significant delivery
  risk" (John, D34; D31). Each
  lane tells the coordinator the fidelity it builds to and any approximation it keeps; the
  coordinator evens the lanes out, and the governance thread writes the ledger in `status.md`.
- **Sources**: any domain may be read (D32). Lanes started before 13:46 on 2026-10-17 get primary
  documents through the "Primary source research for the lanes" thread, as cited excerpts in the
  project's shared folder (`sources/<lane>.md`); values from them carry the document and page.
- **Reporting**: lanes report to the coordinator; the governance thread is the only writer of
  `governance/` outside `vehicle/` and `chassis/` for the sprint (D30).

## Reporting

Each stream's `snapshot.md` is current as of its last merge; `status.md` reconciles the programme
against the code and is refreshed by the governance stream after any merge that moves a milestone.
A status word needs a pointer: a SHA, a file and line, a test, an issue. "Done" means merged with CI
green, not written.
