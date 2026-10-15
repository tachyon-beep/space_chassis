# The `wip/` branches pushed under D18: inventory and disposition

2026-10-15. Written by the cloud triage thread from `git fetch origin` against `main` @ `30b9adf`.
Origin holds **37** `wip/` branches from this push: the first round of 17 below, then nine more
(`wip/stashes`, six `wip/vehicle-*` aliases, `wip/host-prep-2026-10-15`, and a second commit on
`wip/local-state`), listed under "Second round", then eleven mirrors of `space_vehicle`'s
`codex/*` branches ("Mirrored from space_vehicle"). The branches were pushed from John's machine (nyx) by his local session under D18; nothing on
them was rewritten, and nothing here deletes them. `wip/*` stay the untouched originals; anything
re-applied to `main` goes on a new `<stream>/<topic>` branch.

"Predates the restructure" means the branch does not contain `0036b88` (PR #3, which moved the
chassis under `aurora/` and the vehicle under `vehicle/`). Every branch but `wip/local-state`
predates it. Vehicle commits name paths as the vehicle repository did (`tools/console.py`, not
`vehicle/tools/console.py`); chassis commits name pre-move paths (`live/`, `tests/`, `containers/`).

## Live work

| branch | base | carries | disposition |
|---|---|---|---|
| `wip/39-take-by-rename` | vehicle `f75420c` | `7a87eb8` (2026-10-12), `#39` Option B: the claim takes the console by rename and never writes over a file. 4 files, +929/−75 | re-applied under `vehicle/` with `#23` below, on `vehicle/clock-seam` |
| `wip/23-clock-seam` | `7a87eb8` above | `7e2a4b1`: the uncommitted `#23` clock-seam work (candidate 3a) as a snapshot commit. 9 files under `tools/`, `tests/`, `docs/decisions/0002`, README; +3,518/−367 over `7a87eb8` | cherry-picked `-X subtree=vehicle` onto `main`, clean, on `vehicle/clock-seam` (PR #9) |
| `wip/diag-contract-probe-loss` | chassis `6135575` (2026-10-10) | `73f7082`: snapshot of the probe-diag worktree. The probe's `--trace`, the probe test's evidence directory, two trace readers; also a submodule pointer bump to vehicle `8c6f71d` | re-applied as PR #8, **merged to `main` as `2c72d7b`**: files moved to `aurora/`, the pointer bump dropped (the vehicle is `vehicle/` at `f75420c` now), one path fixed to `AURORA / "tests"` |
| `wip/phase-b-adoption-staged` | chassis `6262dc8` (2026-10-10) | plan 7: the 12 Phase A commits of `vehicle-adoption` (`6a45936`..`be63f93`) plus `ff83ac4`, the uncommitted Phase B work in the vehicle-adoption worktree. Its tree is identical to `wip/preserve-phase-b-R2c` | **not re-applied; conflicts with landed work** (below) |
| `wip/phase-b-dryrun` | chassis `6262dc8` | the same 12 Phase A commits plus 5 (`ed7a0d3`..`39ba76d`): the vehicle as the smoke stack's window, its resume checked, and `bd74535` "DRY RUN ONLY: reconciliation pins at vehicle 06f08a3". Superseded by `phase-b-adoption-staged`, which carries all of it forward (the staged tree takes `39ba76d` further in 16 files, +1,116/−110, and keeps the dry-run pin) | not re-applied separately; goes with Phase B |

### Phase B: why it was not re-applied

Rebasing `6262dc8..wip/phase-b-adoption-staged` onto `main` with rename detection stops on three of
its 13 commits:

- `1295e94` (one console for every window): `aurora/containers/serve_vehicle.sh`'s header and the
  serve test in `aurora/tests/test_vehicle_reconciliation.py`, against the restructure's path fixes
  (`3a32253`: `REPO` became the root and `AURORA` the stream, the vehicle path became `vehicle/`).
- `7ecbca1` (the vehicle's deployment and the operator's procedures): `aurora/CLAUDE.md` and
  `aurora/README.md`, which the restructure rewrote for the `aurora/` working directory.
- `ff83ac4` (the staged Phase B): `AGENTS.md`, `pyproject.toml` (testpaths, rewritten by the
  restructure), `docs/deep_research/integration/reconciliation/README.md` (figures `bbc301c`
  re-pinned to the absorbed vehicle `f75420c`, where Phase B pinned `06f08a3`), the submodule
  pointer (gone), and `live/test_vehicle.py`, added under a directory that moved.

The first two are path conflicts a careful rebase resolves. The third is substantive: Phase B's
reconciliation pins and image wiring were written against the submodule and the pre-split Docker
context, and `main` has since absorbed the vehicle and moved it to a named build context
(`vehicle_src`). That resolution belongs to whoever owns plan 7 (the chassis line), with the
restructure plan's note that Phase B "expects a rebase onto the new layout before commit"
(`docs/plans/2026-10-15-three-stream-restructure.md`).

## Already on `main`: superseded, nothing to do

Each is a pre-rebase copy of a commit that later landed: same author, same author timestamp, same
subject, and `git range-diff` shows only README and test-count context changed by the rebase.

| branch | commit | landed as |
|---|---|---|
| `wip/wp01-shared-executive` | 12 commits on vehicle `8c6f71d`, 2026-10-09 | 11 patch-identical on `main`; `1aa183f` is `168c7ca` |
| `wip/rcs-command-on-scope` | `03b13df` (2026-09-23) | `4c8f594` |
| `wip/docked-frame-axis` | `24688df` (2026-09-23) | `dd79e76` |
| `wip/thermal-source-scope` | `c07f0c3` (2026-09-23) | `8b8713d` |

## Recorded only

| branch | what it is |
|---|---|
| `wip/preserve-phase-b-P`, `-R`, `-R2`, `-R2b`, `-R2c` | parentless commits wrapping `refs/preserve/phase-b-*`: whole chassis trees (204 files, pre-restructure layout) for Phase B increments P to R2c. Against `be63f93` they add 10, 13, 17, 17 and 17 files' changes. R2c is identical to `wip/phase-b-adoption-staged` |
| `wip/preserve-chassis-lane-evidence-2026-10-14` | parentless; 189 files: `.scratch/phase-b-*` gate, diagnosis and review evidence, `.scratch/tier1-brief-draft/`, and five `governance/{chassis,vehicle}/records/` files |
| `wip/preserve-chassis-lane-status-2026-10-14` | parentless; one file, `governance/chassis/records/2026-10-14-chassis-lane-status.md`, identical to the copy on `main` |
| `wip/local-state` | two commits on `0036b88` (post-restructure). `d230fd0` adds five files under `governance/records/`: `VEHICLE_COMPLETENESS_REPORT-2026-09-23.md`, `filigree-export-2026-10-15.jsonl` (234 records), `brief-wording-tier1-v5.md` and its review prompt and review. **These are the latest copies** of the completeness report, the filigree tracker and brief v5; none is on `main`. `1f01ed4` adds the remaining scratch notes: `CHECKPOINT-2026-10-10-night.md` and `governance-drafts/{README,coordination}.md` |

## Second round

| branch | what it is | disposition |
|---|---|---|
| `wip/stashes` | 102 chained commits, oldest first, root `fa3dc34` parentless. Each commit's tree is one dropped stash's tree byte for byte (old layout); its message names the stash sha, branch, base and time, so `git diff <base> <commit>` shows what it held. Selected on nyx from 331 dangling stashes (the pre-commit hook stashes on every commit) by dropping those equal to their base, duplicates, and trees already committed on a ref. Bases: 92 on `aurora-port` (37 at `6135575`), 6 on `phase-b-adoption` (`be63f93`), 2 on `phase-b-dryrun`, 1 each on `vehicle-adoption` and `diag/contract-probe-loss`. The latest (`stash 097`..`102`, 2026-10-12 to 2026-10-15) are successive snapshots of the same governance drafts (`MASTER_GOVERNANCE_PLAN.md`, `coordination.md`, `governance/vehicle/*`, the filigree skill references), which PR #4's governance rewrite has since replaced | recorded only |
| `wip/vehicle-39-take-by-rename`, `-23-clock-seam`, `-wp01-shared-executive`, `-docked-frame-axis`, `-rcs-command-on-scope`, `-thermal-source-scope` | aliases: the same commits as the unprefixed branches above (`7a87eb8`, `7e2a4b1`, `7290108`, `24688df`, `03b13df`, `c07f0c3`) | as their unprefixed names |
| `wip/host-prep-2026-10-15` | one commit on `main` `30b9adf` adding `governance/records/host-prep-2026-10-15.md`: nyx's ledger of these pushes and the host step | recorded only |

The vehicle work on nyx lives in the old submodule's git dir (origin `space_vehicle`), so the
vehicle branches carry only their new commits, in the vehicle's root layout and unrebased; they
re-apply with `git cherry-pick -X subtree=vehicle`.

`wip/sv-recorder-opus-20261008` (on chassis `fa43b25`, 2026-10-08, 125 files) is also on `origin`
but was not part of this push; it predates D18 and stays parked, as the restructure plan lists it.

## Mirrored from `space_vehicle`

Eleven `codex/*` branches of `tachyon-beep/space_vehicle`, pushed here as `wip/vehicle-<name>` so
the code is durable before D21 archives that repository. Ten are already wholly on `main` (their
tips are ancestors of `main`, through the vehicle's absorbed history):

| `wip/vehicle-…` | tip | on `main` |
|---|---|---|
| `39-quiet-skip` | `7ac9791` | yes |
| `ci-referee-timeout` | `b3c328d` | yes |
| `vehicle-delivery-scaffold` | `d4f7d04` | yes |
| `window-record-no-seed` | `e756ceb` | yes |
| `wp01-on-issue16` | `bdfaf8b` | yes |
| `wp08-checkpoint-format` | `25fffb5` | yes |
| `wp08-design` | `47856fa` | yes |
| `wp08-encoder` | `b1feb0e` | yes |
| `wp08-resume` | `45f4267` | yes |
| `wp08-state-dir` | `770159e` | yes |
| `diag-ingress-trace` | `1caab23` on vehicle `8c6f71d` | **no**: one commit, an env-gated ingress trace (`VEHICLE_INGRESS_TRACE`) that PR #8's diagnosis run reads where the vehicle has one. Recorded, not re-applied; it re-applies with `git cherry-pick -X subtree=vehicle` when the probe diagnosis resumes |

This covers the branches the nyx session named as still on `space_vehicle`. Whether that
repository holds anything else (tags, other branches, issues per D21) was not checked from here.

## Host step (nyx)

Done, per `host-prep-2026-10-15.md`: with the stack down, `volumes/`, `.env` and
`llm_console_seed.json` moved into `aurora/`; `volume-images/` and `operator/` never existed and
`prepare_host.sh` creates them; the checkout is on `main` @ `30b9adf`. 11 unmanaged
`postgres:16-alpine` containers are listed there and were not touched.
