# AUR-GOV-02 — vehicle custody inventory (report v1)

As of **2026-10-10T08:51Z**. Reporting owner: **Space Vehicle [610587]**, Claude Code session
`a728e992-9471-46ab-9efe-ce550d7ece5f` (Opus 5.5). Accountable line: vehicle. For Emmy under
`../../MASTER_GOVERNANCE_PLAN.md` §3–4. This record is the report; the plan is Emmy's to update.

## 1. Repositories and exact versions

| what | full SHA | note |
|---|---|---|
| vehicle `origin/main` (live `ls-remote`, 08:51Z) | `64fc58c71ab52c2ababafdeb9430feddaa8a69c2` | WP08.4 (#38); the newest merged vehicle |
| vehicle `origin/codex/wp08-resume` (live) | `45f426763280aa1274732fc35f99584b4d7f9ebc` | #21, pushed; equals the local branch |
| chassis `main` | `fa43b25b0fd7d88a3f5e7feb3338e190078517ce` | gitlink `dd79e7608c931df9e5273824a3b2b9f396cb7cb7` |
| chassis `aurora-port` | `db1ed2d940afea636e243a874b1b871c9d2ae2ec` | gitlink `dd79e76…` (same); holds `governance/` |
| submodule checkout (`docs/deep_research/vehicle`) | `8c6f71ddc44597b204078c12b5232ef47ed5f99a` | branch `codex/vehicle-delivery-scaffold`, clean; **differs from the gitlink on purpose — preserve; never `git submodule update`** |
| #21 reviewed heads | `06f08a33933a465cf43420ed2fb3cd0642ed98c3` (code review), `0647ee2e8e8fccb9ad5a7ceed2a2e63af1e69db5`, `d0a20dcde7a9856e5834fc4612a73d6db906d918`, `f12e522dda31ea5ad8aa8944095e61814b40eac1`, `a38cee184c4c20e0a108bfd72becd84f778d3c56`, `45f426763280aa1274732fc35f99584b4d7f9ebc` (confirmations 1–5) | the master plan's `13a6ab4` was a mid-round-1 snapshot; superseded |

Object store: `/home/john/space_chassis/.git/modules/docs/deep_research/vehicle` (the submodule's
git dir; every vehicle worktree hangs off it). Local `main` is stale (`dd79e76`, behind 54); nothing
relies on it.

## 2. Worktrees (vehicle object store)

| path | HEAD | owner | preserve? |
|---|---|---|---|
| `/home/john/space_chassis/docs/deep_research/vehicle` | `8c6f71d…` `codex/vehicle-delivery-scaffold` | chassis main checkout's submodule; touched only when deconflicted | **yes** |
| `$SP/wp08-3` | `45f4267…` `codex/wp08-resume` | #21 implementer (subagent of [610587]); tests running in it | **yes, until #21 merges** |
| `$SP/probe-45f4267-ca87a9/wt` | `45f4267…` detached | [610587] probes | no — remove after the PR |
| (queued) `$SP/gate-res6-ca87a9` | will be `45f4267…` detached | [610587] final gate | no — removed after the gate |

`$SP` = `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad`
(session-ephemeral, 968 MB). Everything a successor needs from it is copied to
`/home/john/space_chassis/.scratch/wp01-handoff/evidence/wp08-3-custody/` (§5).

## 3. Branches and dirty state

- Submodule checkout: clean. `$SP/wp08-3`: clean (the implementer commits each change; it writes
  only under `$SP/fix-wp083/`).
- Local vehicle branches other than `codex/wp08-resume`: earlier merged packages
  (`codex/wp01-*`, `codex/wp08-{design,checkpoint-format,state-dir,encoder}`,
  `codex/window-record-no-seed`, `codex/ci-referee-timeout`, `codex/issue16-citation-identity`) and
  September `vehicle/*` integration branches. None carries unfinished vehicle-line work; keep, no action.
- Chassis-side paths the vehicle line wrote: `governance/vehicle/**` (committed by the chassis through
  `db1ed2d`; **uncommitted now**: `decisions.md` +2 rows from the scope exchange, and this record);
  `.scratch/wp01-handoff/**` (gitignored; PR/issue drafts, evidence copies).
- Not the vehicle's, preserve as found: the chassis's dirty filigree skill files, `docs/plans/`,
  `governance/MASTER_GOVERNANCE_PLAN.md` (Emmy's).

## 4. In flight — #21 (WP08.3 resume)

**Reviews: done.** Codex `gpt-6-astra` high confirmed each round; round 5's confirmation, scoped to
`a38cee1..45f4267` by the binding termination rule (`records/…-review-fixes-5.md`), **approved at
`45f4267`: no P1/P2, no new P3 in the diff** (K1 cleanup rule, K2, J4 leftovers confirmed; executed
file-free probes; filesystem pytest not run by Codex). Earlier verdicts are the headers of
`records/2026-10-10-wp08-3-review-fixes{,-2,-3,-4,-5}.md`. Residual P3s filed as **#40**.

**Validation done (local, owner's own):** gate at `f12e522`, both lanes (3.12.3, 3.13.15): ruff 0,
`check_vehicle` exit 0 (273 debts), `--strict` exit 2 (expected), readiness/build-order/measure exit 0,
**515 passed, 0 skipped, 0 failed** each. Probes and SIGKILL stress ×15 in both journal layouts at
`a38cee1` and `45f4267`: contiguous ticks, whole-record replay from genesis equal at every tick,
0 duplicates, 0 recorded without result, 0 result without record.

**Remaining (all running or queued; no new paid runs):**
1. Implementer per-commit suites (3.12): done through `d9513ca` (538 passed); `2c3a70a` running.
   Every commit `98bd804..d9513ca` passes except `29becaf` (documented, `git bisect skip`); `36fdd91`
   has no per-commit run yet → queued by [610587] (`bfgh1bs0v`).
2. Implementer gate at `45f4267`: three full 3.12 runs, touched tests on 3.13 (`$SP/fix-wp083/gate5-*`).
3. [610587] gate at `45f4267`, both lanes (`b01ohz550`, waits for 2) → `$SP/evidence/wp08-3-45f4267-ca87a9/`.
4. PR from the drafted body (`.scratch/wp01-handoff/pr-wp08-3.md`; placeholders: the final count),
   gate comment, hosted CI, merge commit (merges authorised once CI is green).
5. After merge: post the merge SHA with its pin counts on filigree `space_chassis-93010ff54e`
   (`report.refuse(` sites 882 at `45f4267`); update `governance/vehicle/`; remove worktrees.

**Dependencies:** chassis Phase B (adoption) waits only on the merge SHA (chassis ETA 1–2 h after it).

## 5. Evidence (durable copies)

`/home/john/space_chassis/.scratch/wp01-handoff/evidence/wp08-3-custody/`:
`briefs/` (design note, fix briefs 1–5, #39 and #40 bodies), `reviews/` (first-round Codex and Fable
reports), `scratch-evidence/` (every gate, stress, per-commit and probe output for `06f08a3` → `45f4267`,
each with its owner suffix; `wp08-3-06f08a3/CONTAMINATED.txt` marks the one invalidated run),
`implementer/` (per-commit tables, gate scripts and summaries), `probes/` (Opus probes, stress harness,
`probe_race.py`). Binding briefs and first-round reviews are also in `records/`.
Gaps: the Codex confirmation reports for rounds 1–5 exist only as their summaries in the next round's
brief header and here (verbatim texts are in subagent transcripts under
`/tmp/claude-1000/-home-john-space-chassis/0eb2f673-…/tasks/`, ephemeral). The Claude Opus round-1
code review is summarised in `records/…-review-fixes.md`; its probes are kept.

## 6. Sessions and agents

- **[610587]** (this session): the vehicle line's voice and #21's owner. Subagents: the implementer
  (`a2ecd17b4446e02ea`, writes only `$SP/wp08-3` and `$SP/fix-wp083/`); Codex reviewers (read-only, done).
- **Space Vehicle [666827]**: an earlier duplicate resume (it ran the first Codex/Fable reviews and once
  collided on a gate path — the invalidated run above). Idle; has said it will not act; owns nothing.
- Chassis voice: **Space Chassis [8a7d49]**; [f0c915] is an idle Desktop twin.
- Shared scratch rule: every gate/probe path carries an owner suffix; one owner per branch (`practice.md`).

## 7. Scope and lead agreements (2026-10-10, with [8a7d49]; `decisions.md`)

Vehicle leads: the contract (chassis adopts), #21's merge SHA, #27 pause semantics/interface, #23's
spec, #28's shutdown bound and `/state` retention, #39 and any contract sentence it needs. Chassis
leads: the deployment (compose, image, serve script, volumes, `stop_grace_period`), the adoption and
issue `93010ff54e`, the operator's invocation of pause, the archive procedure. Window leak: the
window half is closed at the merge SHA (no scenario, seed, arms or dwell in any window — checked
live at `45f4267`); `HELP.md` designer prose remains (#35, deferred by John).

## 8. Decisions needed

None blocking #21 or custody. Open owner items, unchanged: #15 branch protection (John); #35 timing
(John deferred). The chassis decides exit-3 restart policy in Phase B (vehicle position recorded).

## 9. Next atomic slice after #21

**#39** — the claim's read-then-rewrite erases a batch written in between (P2, pre-existing on `main`
and in the chassis's `dd79e76`; probe and fix directions in the issue). Then WP08 children #23, #25–#30.

## 10. Custody readiness (owner's assessment)

Documentation-ready for this task, with one condition: **#21 is mid-validation.** If the session
ends before the merge, a successor resumes from §4: the branch is pushed at `45f4267`, reviews are
complete, and the remaining steps are mechanical (re-run the gate in a fresh unique path if the
running jobs are lost, open the PR from the draft, merge on green CI, post the SHA). No unlocatable
change exists. The `$SP` scratchpad and running background jobs are session-bound — their loss costs
only re-running tests, not work.
