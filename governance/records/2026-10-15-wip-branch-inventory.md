# The `wip/` branches pushed under D18: inventory and disposition

2026-10-15. Written by the cloud triage thread from `git fetch origin` against `main` @ `30b9adf`.
The 17 branches were pushed from John's machine (nyx) by his local session under D18; nothing on
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
| `wip/23-clock-seam` | `7a87eb8` above | `7e2a4b1`: the uncommitted `#23` clock-seam work (candidate 3a) as a snapshot commit. 9 files under `tools/`, `tests/`, `docs/decisions/0002`, README; +3,518/−367 over `7a87eb8` | cherry-picked `-X subtree=vehicle` onto `main`, clean, on `vehicle/clock-seam` |
| `wip/diag-contract-probe-loss` | chassis `6135575` (2026-10-10) | `73f7082`: snapshot of the probe-diag worktree. The probe's `--trace`, the probe test's evidence directory, two trace readers; also a submodule pointer bump to vehicle `8c6f71d` | re-applied onto `main` on `aurora/probe-diag`: files moved to `aurora/`, the pointer bump dropped (the vehicle is `vehicle/` at `f75420c` now), one path fixed to `AURORA / "tests"` |
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
| `wip/local-state` | one commit on `0036b88` (post-restructure) adding five files under `governance/records/`: `VEHICLE_COMPLETENESS_REPORT-2026-09-23.md`, `filigree-export-2026-10-15.jsonl`, `brief-wording-tier1-v5.md` and its review prompt and review. **These are the latest copies** of the completeness report, the filigree tracker and brief v5; none is on `main` |

`wip/sv-recorder-opus-20261008` (on chassis `fa43b25`, 2026-10-08, 125 files) is also on `origin`
but was not part of this push; it predates D18 and stays parked, as the restructure plan lists it.

## Not pushed, per the nyx session

The 17 dropped-stash commits, the vehicle branches mirrored to `space_vehicle`, and extra scratch
notes wait on a decision. The host migration (`volumes/ volume-images/ operator/ .env
llm_console_seed.json` into `aurora/`) is not done; the session reported 11 unmanaged postgres
containers running.
