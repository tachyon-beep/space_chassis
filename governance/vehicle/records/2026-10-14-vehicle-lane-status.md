# Vehicle lane: durability and status (vehicle, 2026-10-14)

As of **2026-10-14**, `tachyon-beep/space_vehicle` main @ `f75420c` (local remote-tracking ref; not
re-fetched today). Owner: Space Vehicle, Claude Code `session_01GRfs7dVMu4v5airK6q3w9C` (local
`a728e992-9471-46ab-9efe-ce550d7ece5f`), the sole Vehicle writer. **Verify every hash and path below
against the repository and the archive manifest before acting on it.**

John asked on 2026-10-14 for the lane to be made durable and for a status report. This record does
both. Nothing was run, committed, pushed or published to produce it: no test, collection, gate,
supervisor or container; no `git add`; no change to `MASTER_GOVERNANCE_PLAN.md` or `coordination.md`.

## 1. Status at a glance

**Kind of work: hardening throughout** (WP08 / M1 continuity, plus #39). No extension work since
2026-09-21: a real tick still advances **50 of 139** states, with **273** declared debts
([open.md](../open.md), "Kind of work").

| item | kind | state | blocked on |
|---|---|---|---|
| #39 option B (claim by rename) | hardening | local commit `7a87eb82cfef55dcc74248df41720883587ca7af` (parent `f75420c`, tree `ccc2782e…`), branch `codex/39-take-by-rename`, no upstream. **UNQUALIFIED / UNPUBLISHED.** G-2 package final, reviews r1–r6 (r6 approves) | MASTER §39: G312s on **authorisation hold**; grant `SPACE-20261011-B-G312S-01` revoked unused; a fresh allocation needs John's explicit approval of the one-time 3.12 static run, then new identity/capacity/admission checks and a new grant ID |
| #23 WP08.5 clock seam | hardening | design settled (`DESIGN.md` `4e8d0d6a…`); implementation candidate 3a review-complete **statically** (Codex, determinism, systems all approve; `py_compile` and `ruff check` pass). **No test has run.** Uncommitted | Governance slots ([slot request](2026-10-12-23-clock-seam-slot-request.md)): bounded selections, then the §8 `measure_clock` feasibility run; both queued behind #39's G-2 sequence. #23 is built on #39's commit, so it publishes after #39 |
| #25–#30 (WP08 children 7–12) | hardening | not started | #23 (5) for most; see [open.md](../open.md) |
| #40, #35, #16, #15 | — | unchanged since [open.md](../open.md) | as listed there (#15 is John's) |
| #42 | — | kept separate, unchanged | — |

## 2. What was made durable today

`/tmp` is wiped at boot and age-cleaned at 30 days (`/usr/lib/tmpfiles.d/tmp.conf`: `D /tmp 1777 root root 30d`),
so everything in the session scratchpad
`/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad` (`$SP`)
is volatile. `.scratch/` survives reboots but is gitignored and not durable under
[README](../../README.md) rule 7.

### 2.1 Moved out of `/tmp`

- **The #23 worktree** moved with `git worktree move` from `$SP/v-23-clock` to
  **`/home/john/space_vehicle_worktrees/23-clock-seam`** (outside the chassis tree). Verified after
  the move: HEAD `7a87eb82cfef55dcc74248df41720883587ca7af`, branch `codex/23-clock-seam`,
  `git diff 7a87eb82 | sha256sum` = `9de5a0dd68426491885b0a7323d7466e7ec010146e6f87abd6c6ce84cc9bada8`
  (unchanged), nine modified files, nothing untracked. Documents in the archive written before today
  still name the old `$SP/v-23-clock` path; this location supersedes it.

### 2.2 Copied into governance: `records/2026-10-14-lane-archive/`

Byte-identical copies, 226 files plus the manifest itself, about 0.8 MB (1.5 MB on disk), manifest
[`ARCHIVE.SHA256SUMS`](2026-10-14-lane-archive/ARCHIVE.SHA256SUMS)
(sha256 `c396ebd8486b31f0aa1523d479c4b0261a4efdb53defa50bd2151f452d29a6a4`; check with
`cd governance/vehicle/records/2026-10-14-lane-archive && sha256sum -c ARCHIVE.SHA256SUMS`).
The `.scratch` originals remain the execution copies at their recorded paths; the archive is for
recovery and record only.

| folder | contents | proof of identity |
|---|---|---|
| `23-clock-seam/` | `DESIGN.md` (`4e8d0d6a…`) and r1/r2, `MAPPING.md`, `IMPLEMENTATION-LOG.md`, implementer reports c0–c2, all design and implementation reviews, the 3→3a delta (`4fe710e2…`) | `cmp` against `.scratch/wp08-23/` |
| `39-option-b/gate/` | the frozen G-2 package: `SHA256SUMS` (`4956e7ae…`), four specs, `gate_worktree.sh`, `gate_lane.py` **as `gate_lane.py.txt`**, `interpreters.txt`, `COMMIT_MESSAGE.txt`, `PR_BODY.md`, `CONTRACT-PACKAGE-B.md`, `PROPOSAL-G.md` | `sha256sum -c` against the package's own `SHA256SUMS` (11 file entries pass; the two diff entries are covered in §2.3) |
| `39-option-b/` | `G-RELAY-FINAL.md` (`a0669a93…`), `CHECKPOINT.md` (the lane's working log, checkpoints 1–30) | `cp -p` |
| `39-option-b/design/`, `reviews/` | option B design `39-design-B.md`…`B5.md`; final-package reviews r1–r6 | `cp -p` |
| `39-option-b/v7-supervisor/` | the K-qualified v7 supervisor (`supervise.py`, `launch.py`, `record.py`, `run_controls.py`, each **as `*.py.txt`**), its `PROPOSAL.md`, `controls.json`, `spec-S1.json`, the K1 controls and their evidence, the S1 evidence, owner releases and pre/post-run records | `sha256sum -c` against the supervisor's `SHA256SUMS` and the K1/S1 evidence manifests: all pass |
| `venvs/` | `pip freeze` and `python -VV` of both gate venvs; `requirements-dev.lock` (`6d127105…`) | both freezes hash to `4535babc…`, matching `interpreters.txt` today |

Python sources are stored as `.py.txt` so the chassis's `ruff check .` and pytest never pick them up;
the content is unchanged (the manifests above check the bytes).

### 2.3 Deliberately not copied: the code diffs

Both diffs are unqualified vehicle code. The chassis pushes `governance/` to GitHub, so putting them
here would publish them by a side channel. They are regenerable from durable git objects in
`/home/john/space_chassis/.git/modules/docs/deep_research/vehicle`:

- #39: `git diff f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f 7a87eb82cfef55dcc74248df41720883587ca7af`
  → sha256 `0d4da11e9cbe56fcad7e09c48e027340d41f1bae438adfe8cce9dcc889a951d0` (re-verified today).
- #23: `git -C /home/john/space_vehicle_worktrees/23-clock-seam diff 7a87eb82` → `9de5a0dd…`;
  the frozen copy is also at `.scratch/wp08-23/candidate-3a/23-candidate-3a.diff`.
- #39's review delta `delta-4-to-5.diff` (sha256 `790982da4180f092a991ba7411094e06a8f03beac9d54ea92b45d743cc3f621c`,
  the package's second diff entry) is **not** regenerable from git: candidate 4 was never committed.
  It exists only at `.scratch/wp01-handoff/diag-contract-probe/B-candidate-5/`. That is a known gap;
  it is review context, not the qualified artefact, and falls under question 1.

The #23 work exists only as an uncommitted working tree plus that `.scratch` copy. See question 1 in §5.

### 2.4 Still exposed, by design

The frozen G-2 specs and MASTER §38/§39 name `$SP/venv3.12/bin/python`, `$SP/venv3.13`,
and the gate worktree `$SP/gate-C-7a87eb8` (created by `gate_worktree.sh` at launch; absent now);
`gate_worktree.sh` also takes `$SP/b-39-ca87a9` as its source repository (`REPO=`, line 20).
These stay in `/tmp` because moving them would change the frozen, reviewed package (a new manifest
and an r7 review). `$SP/b-39-ca87a9` also stays: it is clean, the frozen script needs it at that path, and its commit
and branch are durable in the vehicle git directory. **If `/tmp` is wiped** (a reboot), recreate before any G-2 launch:

1. `python3.12` (3.12.3) and `python3.13` (3.13.15) venvs at the same `$SP/venv3.12` and `$SP/venv3.13`
   paths, installed from `requirements-dev.lock` sha256 `6d127105…`.
2. Prove fidelity: `pip freeze | sha256sum` must equal
   `4535babcc5a2e230b30d864b4af05d1838aafd5f4b5c885710b30fcd0709b4cb` for both, and `python -VV`
   must match `venvs/*-python-VV.txt`.
3. `git worktree prune`, then `git worktree add $SP/b-39-ca87a9 codex/39-take-by-rename`. This is
   required, because `gate_worktree.sh` reads from that path. Identity check: HEAD `7a87eb82…`,
   clean.
4. Report the recreation to Governance before the next allocation's identity checks. If Governance
   would rather not rely on recreation, the alternative is re-freezing on durable paths (question 3).

## 3. Resume recipe for a new session

1. Read this record, then [open.md](../open.md), MASTER §§37–39, and `39-option-b/CHECKPOINT.md`.
2. Verify the anchors:
   - `git -C /home/john/space_vehicle_worktrees/23-clock-seam rev-parse HEAD codex/39-take-by-rename`
     → both `7a87eb82…`.
   - The `git diff` hashes in §2.3.
   - `sha256sum .scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/SHA256SUMS` → `4956e7ae…`.
   - `sha256sum -c` in the archive.
3. Work on vehicle code only in worktrees, never in the chassis submodule checkout
   `docs/deep_research/vehicle` (at `8c6f71d`), and never `git submodule update` it.
4. Standing constraints:
   - No test, collection, control, unit, scope or qualification without a concrete Governance
     allocation. Don't retry to green or enlarge bounds.
   - Unknown cleanup keeps the slot; exit 4 does not release it.
   - Preserve ELSPETH priority and Sultai's GPU reservation: one Space selection, ≤ 2 workers,
     nice 19, no GPU.
   - No push, PR, merge, adoption or pin change without John's approval.
   - Never `git stash`; no broad `git add`.
   - `governance/` never reaches an image.

## 4. Housekeeping

- **Obsolete watcher, PID 1605464:** a `bash` loop running for about 4½ days, polling every 2 s for a
  finished task file (`$SP/tasks/b2em98w09.output`). It does nothing else and holds no slot. Left
  running pending John's instruction. It ends at a reboot, or with `kill 1605464`.
- **Other worktrees** in the vehicle git directory: `$SP/diag-ingress-ca87a9` (`1caab23`, branch
  `codex/diag-ingress-trace`, clean; diagnostic only, its commit durable).
- **Uncommitted vehicle-line governance files**, for the chassis to commit verbatim by path
  ([README](../../README.md) rule 8, "sooner on request"; requested now):
  - `governance/vehicle/open.md`
  - `governance/vehicle/snapshot.md`
  - `governance/vehicle/decisions.md`
  - `governance/vehicle/records/2026-10-11-39-claim-race-decision-memo.md`
  - `governance/vehicle/records/2026-10-11-39-tier1-adoption-package.md`
  - `governance/vehicle/records/2026-10-12-23-clock-seam-slot-request.md`
  - this record
  - `governance/vehicle/records/2026-10-14-lane-archive/`

## 5. Decisions needed from John

1. **#23's durability as code** (and #39's `delta-4-to-5.diff`, §2.3). #23's only copies are the uncommitted worktree and `.scratch`. Should it
   become a local, unpushed commit on `codex/23-clock-seam` (needs a §37-style Governance exception),
   or should the diff go into `records/`, which is published when the chassis pushes? Until you
   decide, it stays as it is.
2. **G312s.** MASTER §39 holds #39's first gate stage for your explicit approval of the one-time
   Python 3.12 static run (2 CPUs, 6 GiB, no GPU, five-minute payload deadline). Nothing on #39 or
   #23 moves until then.
3. **The `/tmp` paths in the frozen G-2 package:** recreate the venvs on loss (§2.4), or re-freeze the
   package on durable paths (a new manifest and one more review round)? I recommend recreating on
   loss.
4. **PID 1605464:** may I kill it?
