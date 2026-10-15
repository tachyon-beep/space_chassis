# Governance review (governance stream, 2026-10-15)

As of **2026-10-15**, `tachyon-beep/space_chassis` `main` @ `0036b88`, the first `main` to carry the
three-stream layout. Written by the governance stream at John's request: "have a third stream review
the current governance component ... Assume that all restrictions from me are lifted and all obvious
answers are put in place (given my strategic intent)". **Verify against the code before trusting any
line here.** This record is dated and is not edited later; the decisions it leads to are in
[`../decisions.md`](../decisions.md) and the practice it replaces is [`../practice.md`](../practice.md).

## Verdict

`governance/` did its first job well and its second job badly.

- **First job, keeping two lines from colliding: done.** One owner per path, adoption by exact SHA,
  "a request goes where its receiver reads", records with pointers instead of paraphrase, and the rule
  that nothing here reaches a fleet agent. None of the 2026-10-10 collisions (two sessions on one
  worktree, two "Space Vehicle" sessions) recurred after the rules were written. These rules are kept.
- **Second job, moving the product forward: failed.** Since 2026-09-21 no package added simulated
  behaviour (`vehicle/open.md`, "Kind of work"), and from 2026-10-12 to 2026-10-15 nothing in either
  line moved at all: every item waited on John (`orientation/status-report.md` §3). The process cost
  more than the work it governed, the state it governed lived mostly on one workstation, and the
  documents became a log rather than a picture.

The rest of this record is the evidence for that verdict, then what changes.

## What was reviewed

Everything under `governance/` on `main` (16,449 lines in 268 files): `README.md`, `coordination.md`,
`MASTER_GOVERNANCE_PLAN.md`, both lines' `snapshot`, `open`, `decisions`, `practice` and `interface`
files, and their `records/`, including the 2026-10-14 lane archive. They were checked against the code
on `main`, the vehicle's own tools, the 2026-10-15 readiness review and status report
(`/mnt/project-files/orientation/`), and the restructure plan
(`docs/plans/2026-10-15-three-stream-restructure.md`).

## Findings

### F1. The test-slot regime consumed the programme (severity: decisive)

The shared-workstation rules (one test selection at a time, at most two workers, nice 19, ELSPETH
priority, Sultai's GPU reserved, a written grant per run) turned every test into a negotiated event.
`MASTER_GOVERNANCE_PLAN.md` §§14-39 and `coordination.md` lines 144-399 record about thirty grants,
holds, releases and re-reviews between 2026-10-11 10:04 and 2026-10-12 01:24 AEDT. Examples:

- To run Option B's first gate (a five-minute static check, G312s), the lane built a supervisor, put
  it through review rounds r1 to v7, ran 20 failure-injection controls on the supervisor itself (K1)
  and a 25-test qualification (S1). The grant was then revoked unused because a browser relay was
  denied (§39). The gate never ran.
- Phase B's P increment passed its root suite (592) and full suite (1,941) only after a diagnosis of
  the gate driver's own SIGINT handling (§§19-26). R2c passed root (617) and its full suite never ran
  for want of a "go".
- `#23`, the clock seam, has a reviewed design and an implementation reviewed three times, and **no
  test has ever run on it** (`vehicle/open.md`).

The regime existed for a real reason: both lines shared John's workstation with other projects. A
cloud session or a CI runner has no such contention. **Disposition:** retired (`decisions.md`
2026-10-15 D1, D2). The history stays readable in `records/`.

### F2. The work that matters exists only on John's machine (severity: blocking)

| what | where it is | reachable from GitHub |
|---|---|---|
| `#39` Option B, the silent command-loss fix | local commit `7a87eb82` on `codex/39-take-by-rename`, no upstream | no |
| `#23` clock seam, candidate 3a (+3,518/−367, 9 files) | uncommitted worktree `/home/john/space_vehicle_worktrees/23-clock-seam`, plus `.scratch/wp08-23/` | no |
| Phase B increments P and R2c (vehicle adoption) | staged trees held by `refs/preserve/phase-b-*` | no |
| tier-1 brief wording v5 (reviewed APPROVE) | `.scratch/tier1-brief-draft/` | no |
| filigree, the chassis tracker | `/home/john/.local/bin/filigree` and its local database | no |
| G-2 gate venvs and worktrees | `/tmp/claude-1000/...`, wiped at reboot | no |

Governance recorded all of this carefully (`vehicle/records/2026-10-14-vehicle-lane-status.md` §2,
`chassis/records/2026-10-14-chassis-lane-status.md` "Durability"), but recording a local path does not
make it durable or shareable. No agent other than one on that workstation can continue any of it.
The vehicle lane kept the diffs out of `governance/` deliberately, to avoid publishing unqualified code
by a side channel. **Disposition:** everything above goes to a `wip/` branch on GitHub as it stands,
unqualified work labelled as such (`decisions.md` D11). It needs a session on John's machine, which is
the first residual decision.

### F3. Status words drifted from the code (severity: high)

Every per-line file still carries a 2026-10-10 "as of" except `vehicle/open.md` (2026-10-14).

- `vehicle/snapshot.md` says `#21` is "in flight ... no PR yet"; it merged on 2026-10-10 (PR #41,
  `f443996`), and tier 1 of `#39` merged after it (PR #43, `f75420c`).
- `vehicle/open.md` and the vehicle lane status say a tick advances **50** of 139 states. The tool says
  **52** (`vehicle/tools/plant.py --build-order` on `main`; AUR-GOV-07 §1 says 52 too).
- `chassis/snapshot.md` describes the submodule era: `docs/deep_research/vehicle` at `dd79e76`, a second
  vehicle clone per worktree, `main` 100 commits behind. All three stopped being true on 2026-10-15.
- `coordination.md` line 115 still says "separate repositories; no restructuring is authorised".
- `README.md` says "there is no third team", the same day John set up a third stream.

**Disposition:** the line files get current snapshots in this change; one programme status file,
[`../status.md`](../status.md), now reconciles governance against the code and is the only place a
reader needs for "where are we".

### F4. Coordination became a ledger (severity: high)

`coordination.md` (349 lines) and `MASTER_GOVERNANCE_PLAN.md` (2,670 lines) are mostly append-only
chronology: grant identifiers, host load figures, PIDs and SHA-256 sums. That is valuable as evidence
and useless as coordination: the current rules in `coordination.md` start at line 413, after 270 lines
of slot history, and a reader cannot tell which of 39 master sections still binds. Several
participants are named but never introduced (Emmy, Nyx, Velma, ELSPETH, Sultai, the "browser worker").
**Disposition:** the slot log moves verbatim to
[`2026-10-11-coordination-slot-log.md`](2026-10-11-coordination-slot-log.md); `coordination.md` keeps
only rules that still apply; the master plan is marked closed and kept as a record.

### F5. The channels a cloud agent can use are not the channels of record (severity: high)

Governance names three durable channels: filigree `space_chassis-93010ff54e`, GitHub issues on
`tachyon-beep/space_vehicle`, and session messages between local Claude sessions. A cloud session
reaches none of them: filigree is local, the vehicle's issues live in a repository that is no longer
where the vehicle is developed, and `SendMessage` reaches local sessions only. **Disposition:** GitHub
issues and pull requests on `tachyon-beep/space_chassis` become the channel of record for every stream
(`decisions.md` D10). Filigree stays usable on John's machine as a local view, not the record.

### F6. Nothing enforces the gates the practice describes (severity: high)

The vehicle's CI workflow moved with the vehicle to `vehicle/.github/workflows/development.yml`, where
GitHub never runs it. The repository root has no `.github/` at all. The chassis never had CI (its gate
was "run the suite after `git add`"). Branch protection (`#15`) was never turned on. Practice that
cannot be checked by a machine depended on every session's discipline and on review rounds, which is
why review rounds multiplied. **Disposition:** root CI is decided (`decisions.md` D6) and specified in
[`docs/vehicle-completion/06-verification.md`](../../docs/vehicle-completion/06-verification.md);
branch protection is a residual decision because only John can set it.

### F7. Review depth did not scale with risk (severity: medium)

`#21` (resume) went through a design review, four code reviews and five fix rounds before the
"stopping rule" (`vehicle/decisions.md` 2026-10-10). The tier-1 brief wording went through v1 to v5.
The care found real defects, and the stopping rule was the right instinct. But the same depth was
applied to a gate driver's supervisor as to the vehicle's persistence path. **Disposition:** one
independent review per change, a second only for persistence, the window contract or anything an
agent sees; CI replaces the review rounds that were standing in for missing automation
(`../practice.md`).

### F8. Ownership rules assumed two repositories (severity: medium)

Rule 8 (the chassis commits `governance/vehicle/` verbatim for the vehicle line) and the "chassis never
touches the vehicle's checkout" rules exist because there were two repositories and one submodule
pointer. In one repository with worktrees, each stream commits its own files on its own branch.
**Disposition:** rule 8 retired; ownership by path stays; the governance stream owns `governance/`
and the programme documents it writes under `docs/` (`decisions.md` D12, D13).

### F9. Kept, because it works

- One owner per path and branch; session-unique scratch paths; no shared worktrees.
- Adoption by exact SHA, now as `git subtree pull --prefix=vehicle` or a direct merge into `vehicle/`,
  in one commit with the pins and live checks.
- Decisions appended, never rewritten; reversals point back.
- Every fact carries a pointer.
- `governance/` never enters an image: it is outside the `aurora/` build context, so no `COPY` can
  reach it.
- The non-adversarial threat model for the window (`vehicle/decisions.md` 2026-10-11) and the
  information rule (windows carry no scenario, seed, fault plan or truth).
- The vehicle's evidence standard: a value without evidence stays `UNCONFIGURED` (`vehicle/docs/evidence.md`).

## What changes in this change

| file | change |
|---|---|
| `decisions.md` (new) | Programme decision log: the lifted restrictions and the decisions this review takes, each with its reason |
| `practice.md` (new) | How every stream works now; the stream `practice.md` files keep only what is particular to them |
| `status.md` (new) | One reconciled status for the programme, checked against the code |
| `README.md` | Three streams; read order; rules updated (rule 8 retired; channels) |
| `coordination.md` | Rewritten to the rules that still apply; the slot log moved to `records/` |
| `MASTER_GOVERNANCE_PLAN.md` | Marked closed on 2026-10-15; kept as a record |
| `chassis/` and `vehicle/` `snapshot.md`, `open.md`, `practice.md` | Current as of this `main`; practice points at `../practice.md` |
| `records/2026-10-11-coordination-slot-log.md` | The slot history from `coordination.md`, verbatim |
| `../docs/vehicle-completion/` | The documentation suite for what is left to land the vehicle |

## Residual decisions for John

Kept to what genuinely needs him; everything else was decided under his 2026-10-15 instruction and is
open to his revision in `decisions.md`.

1. **Push local work:** may a session on his machine push the local-only work in F2 to `wip/` branches?
2. **Spend caps:** adopt Aurora's figures (`decisions.md` D16) for the per-agent and fleet caps?
3. **Branch protection** on `main`, requiring CI, once CI is green?
4. **Archive `tachyon-beep/space_vehicle`** and move its open issues here?
5. **Paid pilot:** run a model-backed pilot on the first bounded episode before full V/M acceptance?
