# Space Aurora — master governance and custody plan

As of **2026-10-11 10:04 AEDT (2026-10-10 23:04 UTC)**, `tachyon-beep/space_chassis` `aurora-port` @
`613557528ffc42d4ea8d4ae0a3b3a2c453825ffa`. Verify against the current repositories,
owner reports and decision evidence before relying on this baseline.

**Current report verdicts:** AUR-GOV-02 v1, AUR-GOV-03 v1.1, AUR-GOV-04 v1.3 and AUR-GOV-07 v1
are **SUFFICIENT** for their bounded documentary tasks. AUR-GOV-04 v1.3 is a verified working
file, not published. Section 14 records resumption and its bounded re-check; earlier states are history.
Programme-wide readiness and exclusive custody acceptance remain **NOT ISSUED**.
**Delivery:** required validation ran; the full suite failed. Coordinator commit/publication is
blocked by that concrete gate failure (section 12), not by the earlier testing-scope restriction.
Section 13 separates report sufficiency/publication from commit-gate compliance and records the
minimum operator decision needed. No documentation-only waiver has been granted.

**Programme leadership is effective now.** John at **2026-10-10 08:48 UTC (19:48 AEDT)**:
“I've told the space vehicle claude twins that you're taking over as lead - you can interact with
them via your computer and via writing to the governance folder we setup”. Provenance: quoted
instruction relayed in the delegation from coordinating chat `01a12334-35ad-748b-99eb-2d3a16598084`
to documentation chat `01a12501-b067-7581-b5b2-3d4945441dc2`; this writer did not independently
inspect the original user message. This appoints Emmy programme lead and authorises governance
coordination. It neither declares the owners offline nor transfers exclusive operational custody.

**Earlier custody instruction retained:** the original plan, prepared in chat
`01a1236b-d294-7280-9eec-b4a5527a66d9`, recorded John's relayed direction that Emmy review the
handover, John offline both designated Claude owners, and Emmy accept full custody only after
John confirms that step. Sections 4 and 7 retain that future transfer gate. It is not a condition
of recognising Emmy's present programme leadership, and no shutdown is requested by this update.

**Current custody:** the Space Chassis and Space Vehicle Claude owners remain responsible for
their ongoing assigned work under Emmy's programme leadership. Neither is declared finished or
offline. Emmy coordinates direction, cross-line dependencies, decision provenance and handover
review; exclusive engineering/operational custody has **not** transferred.

## 1. Program and scope

**Space Aurora is the umbrella program.** Space Chassis and Space Vehicle are its two separate
project teams / lines of effort of equal importance, with separate repositories, building one
product in parallel. The umbrella supplies direction,
dependency management and program acceptance; it is not a third implementation line. No repository
move, split, consolidation or submodule update is proposed or authorised here.

| Responsibility | Current accountable owner | Boundary |
|---|---|---|
| Program objectives, reserved choices and transfer authorisation | John | Existing delegations remain in force; this plan grants no new operational approval. |
| Chassis engineering and deployment | Space Chassis Claude owner | `tachyon-beep/space_chassis`: harness, recorder, pump, operator surfaces, images, mounts, deployment, integration checks, adoption pointer and pins. |
| Vehicle engineering and physical evidence | Space Vehicle Claude owner | `tachyon-beep/space_vehicle`, represented here by `docs/deep_research/vehicle/`; simulator, its CI, physics and evidence obligations. |
| Programme leadership, coordination and custody review | Emmy | Coordinate cross-line direction and dependencies; collect evidence, identify decisions reserved to John and assess readiness. Each team retains its assigned engineering work; exclusive custody transfer remains subject to section 7. |

The detailed path allocation is [README.md](README.md); cross-line rules are
[coordination.md](coordination.md). Every task has one lead team; the other team follows that
lead's rule on its side. Programme leadership is not a third implementation team. Any unresolved ownership conflict must be reported,
not silently settled by this plan. The frozen corpus is read-and-cite only.

**Current bounded documentation assignment:** update this coordinator-owned plan and the applicable
coordination entry in `coordination.md`; perform required repository validation and commit/publish
only those files, under the continuation authority recorded in section 11. Owner reports, tracker
state, implementation and repository structure remain outside this assignment. A separate
native-browser worker handles owner contact; this writer sends no owner messages. Owners continue
separately authorised work. No experiments, mission runs, builds, host cleanup, submodule updates
or main merge are authorised. ELSPETH retains resource priority.

## 2. Starting evidence — a moving baseline, not a freeze

### Documentation inspection checkpoint — 19:51 AEDT, 2026-10-10

Read-only inspection confirmed Nyx, the working directory and the local refs below. No remote
fetch, hosted CI inspection or validation run was performed. Owner reports are attributed reports,
not independently repeated checks. The earlier baseline is retained below as history.

| Item | Current source-backed observation |
|---|---|
| Chassis checkout | `aurora-port` @ `db1ed2d940afea636e243a874b1b871c9d2ae2ec`; local `main` remains `fa43b25b0fd7d88a3f5e7feb3338e190078517ce`. |
| Recorded vs actual vehicle | Gitlink remains `dd79e7608c931df9e5273824a3b2b9f396cb7cb7`; actual clean submodule checkout is `codex/vehicle-delivery-scaffold` @ `8c6f71ddc44597b204078c12b5232ef47ed5f99a`. Preserve the difference. |
| Vehicle refs | Local `main` is still `dd79e7608c931df9e5273824a3b2b9f396cb7cb7`; cached `origin/main` is `64fc58c71ab52c2ababafdeb9430feddaa8a69c2`; `codex/wp08-resume` is `45f426763280aa1274732fc35f99584b4d7f9ebc`. The owner snapshot's “main” names its reported upstream baseline, not this local `main` ref. |
| Adoption preparation | `vehicle-adoption` @ `be63f93402f5bf6662e92e8ce509d55f1bb12a4f`; `.claude/worktrees/vehicle-adoption` is actually on `phase-b-dryrun` @ `39ba76d3acc247600cfcbbff458cbcb9aea8b08f`. Neither observation establishes adoption. |
| Image isolation | [Plan-8 ledger](../docs/superpowers/ledgers/plan-8-ledger.md) records implementation through `e3eff27`, reviews, root 569 and live 14/14; later dry run at `39ba76d` records root 592 and live 18/18 against vehicle `06f08a3`. These are owner receipts, not new validation. Old operator `:latest`/`:warm` images still require operator migration per that ledger; current runtime not inspected. |
| Vehicle review / gates | [Vehicle snapshot](vehicle/snapshot.md) reports round-5 diff confirmation approved at `45f4267`, residuals #40, and a both-lane gate at earlier `f12e522`. It still lists final-head gates → PR → CI → merge → posted SHA as next steps. None is inferred complete here. |
| Adoption tracker | Live read of `space_chassis-93010ff54e`: open, unassigned, `side:vehicle`; comments end at 40 with a dry run, not a #21 merge SHA. The chassis remains lead for adoption under standing path ownership. |
| Concurrent owner input | Uncommitted `vehicle/decisions.md` adds a scope exchange attributed to Space Vehicle `[610587]` and Space Chassis `[8a7d49]`, plus a vehicle recommendation on exit-3 restart policy. These are owner-authored inputs, not a coordinator-ratified handover or a chassis policy decision. Preserve verbatim; bridge to confirm live identities and reciprocal evidence. |

### Historical creation baseline — 12:34 AEDT, 2026-10-10

The plan writer confirmed `nyx.foundryside.dev` and `/home/john/space_chassis`. The target file
was absent and had no history in local Git refs before creation. Git metadata and governance were
read without altering the owners' working paths. Remote refs were not fetched; a cached remote ref
does not prove current GitHub or CI state.

| Item observed locally on 2026-10-10 | Exact SHA / condition |
|---|---|
| Chassis `aurora-port` | `f7a3357b72f991ebacbb2a0b5cba90ed05f10d51`; adds the image-split implementation plan, not its implementation. |
| Chassis `main` | `fa43b25b0fd7d88a3f5e7feb3338e190078517ce` at the earlier inspection; refresh for custody. |
| Chassis recorded vehicle pointer | `dd79e7608c931df9e5273824a3b2b9f396cb7cb7` at the earlier inspection; refresh for custody. |
| Main checkout's actual vehicle | `8c6f71ddc44597b204078c12b5232ef47ed5f99a`, intentionally different from the recorded pointer; preserve. |
| Cached vehicle `origin/main` | `64fc58c71ab52c2ababafdeb9430feddaa8a69c2`. |
| Vehicle local `codex/wp08-resume` | `13a6ab4bebfe5ea8890e2c6c443fa32d9bae24db`; review fixes advancing beyond reviewed `06f08a33933a465cf43420ed2fb3cd0642ed98c3`. Commit subjects are not closure evidence. |
| Chassis adoption preparation | `vehicle-adoption` @ `044b5c5093ce03e43d2a0856545872a283674b90` at the earlier inspection; parked pending exact vehicle merge SHA. |
| Chassis adoption worktree | `/home/john/space_chassis/.claude/worktrees/vehicle-adoption`, currently `phase-b-dryrun` @ `397d03275e4e492e62ded0bb3e4f028fe3512db8`. A directory name is not a branch identity. |
| Existing dirty work | Five modified Filigree skill/reference files under each of `.agents/skills/filigree-workflow/` and `.claude/skills/filigree-workflow/`; vehicle pointer difference; untracked `docs/plans/`. Preserve all. This plan will itself be a new untracked file. |
| Other worktree metadata | `/tmp/head_tree` is listed as prunable because its gitdir target is missing; report, do not prune. Vehicle scratch worktrees also require owner inventory. |

Standing sources: [chassis snapshot](chassis/snapshot.md), [vehicle snapshot](vehicle/snapshot.md),
both lines' `decisions.md`, `practice.md`, `interface.md` and `open.md`; the dated
[vehicle records](vehicle/records/2026-10-09-chassis-adoption-package.md); chassis plan ledgers;
Filigree `space_chassis-93010ff54e` and the vehicle's GitHub issues. September `.scratch/apollo/`
handovers and `.scratch/status/VEHICLE_COMPLETENESS_REPORT.md` are historical evidence, not current
operating instructions. Existing governance headers lag current commits and require reconciliation
in reports. No numerical readiness tool was rerun for this plan.

## 3. Pulling work and reporting

Task IDs below are stable. An owner is the accountable reporting role; it does not mean the task
has been claimed. Each role must identify the actual session/person before work starts, especially
where two sessions share a display name.

1. Request a claim by task ID in this conversation. Emmy checks dependencies and records claimant,
   claim time and state in section 8 before work proceeds. One claimant per task; contributors are
   named. This plan does not itself send requests to owners or claim tracker issues.
2. Emmy serialises edits to this file. Agents submit their reports through the conversation;
   they do not concurrently overwrite the plan. If a different writer is needed, explicitly hand
   over the pen first. No additional report file is required.
3. Supply the bounded report and evidence required by the task. Mark unavailable evidence and
   access limits explicitly. Do not run missing validation merely to fill a report.
4. Emmy checks source links, scope, exact versions and unresolved questions. She either accepts
   the report or lists concrete corrections under the same ID. Revise until sufficient for custody.
   Report acceptance does not approve the product or close its engineering issues.
5. Refresh reports affected by owner changes before readiness and again at the offline checkpoint.

States: **READY → CLAIMED → SUBMITTED → CORRECTIONS → SUBMITTED → SUFFICIENT**.
Use **WAITING** for an unmet documentation dependency; **BLOCKED** for a named missing input or
access, with next owner/action. A task may reach SUFFICIENT while product work remains incomplete
if the remaining work, risk, authority and next action are explicit. No elapsed time implies approval.

## 4. Documentation task board

All tasks were unclaimed at creation. The table retains initial states; sections 8–14 record subsequent
activity. Dependencies refer to reports, not completion of implementation. Tasks 09–12 concern a
future exclusive custody transfer and do not delay current programme leadership or owner work.

| ID | Accountable reporting owner | Dependencies | Initial state | Deliverable and acceptance evidence |
|---|---|---|---|---|
| AUR-GOV-01 | Emmy, with both line owners contributing | None | READY | Program and path ownership report: Space Aurora hierarchy; one accountable owner per path/branch; current owner identities and delegations; operator and program acceptance responsibility. Cite `README.md`, `coordination.md` and authority for disagreements. Explicitly reconcile adoption issue `side:vehicle` with chassis deployment ownership; propose correction without changing the tracker. |
| AUR-GOV-02 | Space Vehicle Claude owner | None | READY | Vehicle custody inventory: repo/object-store/worktree paths, full SHAs, branches, cached vs live remote knowledge, dirty/untracked work, in-flight #21 fixes, reviewer state, evidence locations and preservation needs. Map each unfinished change to its owner, next action and exact reviewed head. Account for duplicate sessions and shared scratch paths. |
| AUR-GOV-03 | Space Chassis Claude owner | None | READY | Chassis custody inventory: full SHAs, actual gitlink vs submodule checkout, adoption/dry-run branches and worktrees, paused SV work, dirty/untracked paths and outstanding code/docs debts. Preserve unrelated changes; identify provenance or unknown ownership rather than moving, staging or deleting anything. Include plan 8 and adoption interaction. |
| AUR-GOV-04 | Space Chassis Claude owner, with vehicle contribution | 02, 03 | WAITING | Architecture/interface report: trace agents → recorder/pump/operator surfaces and per-agent diode → vehicle; map mounts, networks, credentials and hidden truth. Reconcile both `interface.md` files with `docs/diode-contract.md`, current deployed/pinned code and proposed adoption. Identify contract authority, exact adoption inputs, one-process/slugs/private-state requirements and future clock/pause deltas. Both sides' responses are evidence; unilateral inference is flagged. |
| AUR-GOV-05 | Emmy, with both owners supplying provenance | 01 | WAITING | Decision and question register: decision, status, authority, date, retrievable source, affected version, reserved approval and next action. Cover image isolation, base digest, cap/model choices, transcript visibility, journal scheduling, port landing, branch protection, clock/pause/recovery choices and physical evidence scope. Distinguish direct John decisions, relayed authority, delegated rulings, drafts and unknowns. Resolve conflicting status text through evidence, not inferred approval. |
| AUR-GOV-06 | Emmy, with each owner providing its receipts | 02, 03 | WAITING | Validation receipt index: exact SHA/range, environment/image, command or review scope, date, result/exit code/skips, durable evidence pointer, limitations and invalidated runs. Separate design/code review, focused/full local validation, hosted CI and live acceptance. Preserve evidence formerly in scratch; if unavailable, record the gap and next action. Do not commission new runs. |
| AUR-GOV-07 | Space Vehicle Claude owner | 02 | WAITING | Known capability/debt report: physics and executable coverage, strict-lint debts, WP01/WP08 completion and residuals, M2–M5 dependencies, #21 findings/dispositions, missing physical evidence and acceptance gates D/I/V/M/E. Link each material gap to issue/source and next owner/action. Counts need source SHA/date; configured states, advancing states and accepted physics are different measures. No invented values or completion percentage. |
| AUR-GOV-08 | Space Chassis Claude owner, with vehicle contribution | 04, 05, 07 | WAITING | Run/recovery guidance report: current pinned stack vs adoption candidate; prerequisites; operator-only setup; first start, normal stop/restart, crash, refusal, incompatible checkpoint and deliberate new world. Explain harness exit-code ladder separately from vehicle exits 0/3. Identify secrets without reading `.env` or recording values; archive/reset actions remain unexecuted and subject to existing authority. Cite exact-version runbooks; flag unimplemented clock, pause and graceful-stop behaviour. |
| AUR-GOV-09 | Emmy | 01–08 SUFFICIENT | WAITING | Reconciled handover report: read all reports against sources; list corrections, stale claims and remaining custody blockers; show every risk/unknown with owner, consequence and next action. Include an exact-version evidence index and a bounded next-work queue. An inherited product blocker is allowed; an unlocatable active change or missing essential recovery authority is a custody blocker. |
| AUR-GOV-10 | Emmy | 09 SUFFICIENT | WAITING | Explicit **READY FOR CUSTODY** or **NOT READY FOR CUSTODY** assessment in section 7, with evidence cut-off, report versions, inherited gaps, conditions and recommendation to John. No assessment is issued by creation or review of this plan. |
| AUR-GOV-11 | John | 10 says READY FOR CUSTODY | WAITING | John offlines BOTH designated Claude owners and explicitly confirms their identities and offline time. Final inventory reconciles any changes since readiness; no automatic shutdown, timeout inference or owner self-certification substitutes for John's confirmation. Material deltas return to Emmy review before acceptance. |
| AUR-GOV-12 | Emmy | 11 confirmed by John; final deltas reconciled | WAITING | Explicit **CUSTODY ACCEPTED** statement: effective time, both owner identities/offline confirmation reference, final SHAs/dirty-state/evidence checkpoint, inherited work and next actions. Only then does Emmy assume full responsibility, within John's standing authority. |

## 5. Issues the reports must resolve or carry forward explicitly

- **Image isolation has advanced since creation.** [Plan 8](../docs/superpowers/plans/2026-10-10-aurora-port-8-image-split.md)
  records John's approval; its ledger now records implementation and review through `e3eff27`.
  This closes the source/image-build work reported by the owner, not operator migration of old
  images or scenario/seed exposure at pinned `dd79e76`. The owner corrected the historical
  “Needs John's go” wording in `chassis/open.md` at `486960c`; approval is no longer an open
  question for that image split.
- **Adoption is separate from a dry run.** Filigree `space_chassis-93010ff54e` comment 40 reports
  4/4 live checks and 579 root tests against vehicle `06f08a3`, plus merged-run failures. It is not
  a green full gate or adoption. Vehicle #21 requires confirming review, exact-head gates, hosted
  CI, merge and a posted merge SHA before chassis adoption. That sequence is existing engineering
  work, not a prerequisite for documentation custody if its state and next owner are understood.
- **Ownership disagrees with a label.** The adoption issue was observed open with `side:vehicle`,
  while its action belongs to chassis and `README.md` routes that label to vehicle. Record who owns
  the action and the proposed routing correction; no relabel or issue closure is authorised here.
- **Missing physics remains material.** `vehicle/snapshot.md` at `64fc58c` reports 273 declared
  debts, 195 UNCONFIGURED scalars and strict exit 2; M2–M5 remain open in that snapshot. These are
  historical tool receipts until refreshed by owner evidence, not fresh measurements or acceptance.
- **Authority and evidence can be incomplete.** Several decision pointers say only “session
  instruction”; the port spec's header still says awaiting review/no implementation authorised.
  Review records have historical `/tmp/` links, and overlapping gate runs were declared void in
  `coordination.md`. Preserve retrievable evidence or name the unresolved gap. Never upgrade a
  reported result or invalid run into independent verification.

## 6. What status words mean

These are separate facts, each tied to an exact version and scope; they are not automatic promotions.

| Term | Required evidence |
|---|---|
| Draft / proposed | Author and proposal source; no approval claimed. |
| Decided / authorised | Named authority, date, retrievable decision and scope; delegated or relayed status explicit. |
| Reviewed | Reviewer, exact head/range, scope, verdict and unresolved findings; review is not test execution. |
| Validated | Actual receipt for stated checks/environment/version, including failures, skips and limits. Local and hosted receipts are separate. |
| Merged | Exact merge commit, destination branch/repository and evidence of landing. A local branch or pushed head is not a merge. |
| Adopted | Chassis commit records the exact vehicle SHA, matching pins/deployment changes and required integration receipts. A dry run is not adoption. |
| Product accepted | Named acceptance gate, criteria, exact versions, evidence and authorised accepting party. Vehicle development green does not establish physical, mission or experiment acceptance. |
| Ready for custody | Emmy has sufficient documentation/evidence to own the known state and actionable unknowns. Owners still hold custody pending John's offline confirmation. |
| Custody accepted | Section 7's sequence completed; responsibility transferred explicitly. Product acceptance may still be open. |

Custody does **not** require completing the product, merging #21, adopting the vehicle, clearing
physics debts or running a campaign. It requires knowing what exists, what can be trusted, what is
unfinished, who can decide, and the next safe authorised action. Unknowns are acceptable when
bounded and actionable; essential custody unknowns remain blockers until resolved or explicitly
addressed by John on Emmy's recommendation. This never waives the required offline confirmation.

## 7. Custody checkpoint — currently NOT ISSUED

| Checkpoint | Current state | Required recorded statement |
|---|---|---|
| Emmy readiness assessment (AUR-GOV-10) | NOT ISSUED | Verdict; date/time; reviewed report versions and evidence cut-off; open product risks vs custody blockers; conditions and recommendation. |
| John's offline confirmation (AUR-GOV-11) | NOT RECEIVED | Both designated Claude owner identities; explicit confirmation both are offline; time and message reference; final delta inventory. |
| Emmy custody acceptance (AUR-GOV-12) | NOT ISSUED | Effective time; John's confirmation reference; final repository/worktree/evidence checkpoint; inherited work and next actions. |

These are gates for **exclusive custody**, not for programme leadership, which is already effective.
Until all three are satisfied in order, the current owners retain their assigned engineering and
operational responsibility under Emmy's programme leadership. Emmy must
reassess material changes after readiness. Offlining one owner, silence, a completed report,
a green CI run or an owner's intent to stop does not transfer custody. If an owner becomes
unavailable early, record that loss and ask John to resolve custody; do not silently assume it.

## 8. Claims, reports and review corrections

This section retains the receipt history. **Sections 9–10 contain the inventory reviews**;
section 10 is the latest disposition and supersedes review-pending/correction states below.

**Coordinator checkpoint, 2026-10-10 19:51 AEDT:** Emmy (documentation chat
`01a12501-b067-7581-b5b2-3d4945441dc2`) claims **AUR-GOV-01**, with a partial source-backed report
in sections 1–2. State **CORRECTIONS**: programme authority and line ownership are recorded;
live owner identities, complete branch/path ownership and the reciprocal scope-exchange receipt
remain to be reconciled through the bridge. The proposed adoption-label correction is to route
`space_chassis-93010ff54e` to the chassis lead; no tracker mutation is made. This claim is solely
for the documentation task, not any engineering issue.

**AUR-GOV-03 / SUBMITTED — review pending** (previously CLAIMED)
- Claimant: Claude Code `session_019mkPNN5J3Atit9tUA6zrNY`; reported Space Chassis owner `[8a7d49]`;
  model Opus 5.5.
- Line: Chassis. Contributors: none.
- Requested: **2026-10-10 19:45 AEDT**. Accepted by Emmy: **2026-10-10**.
- Authority/provenance: assignment relayed by coordinating chat
  `01a12334-35ad-748b-99eb-2d3a16598084`; Emmy reread this section and the task before recording it.
  No competing AUR-GOV-03 claim was present, and the chassis inventory matches its scope.
- Possible Desktop mirror `[f0c915]` remains unresolved and is **not a claimant**.
- Scope: the owner supplies its chassis custody report; coordinator-document edits remain Emmy's.
  [Report v1](chassis/records/2026-10-10-aur-gov-03-chassis-custody-inventory.md) received through
  the bridge and verified locally in commit `486960c515b0d9d3d6e0a677f3c9fec27eb965b0`.
  Submission is recorded before review; no sufficiency verdict or custody transfer follows yet.

**AUR-GOV-02 / SUBMITTED — review pending.** Vehicle owner `[610587]`, Claude Code
`a728e992-9471-46ab-9efe-ce550d7ece5f`, supplied
[report v1, 08:51 UTC](vehicle/records/2026-10-10-aur-gov-02-vehicle-custody-inventory.md), now
committed by concurrent owner work in chassis `3ec1b4ec1a5cc540b713d6cc4a26d967b2f15436`.
This supersedes the earlier observation that no owner report had arrived. Its upstream live-ref
checks, review/probe results, session inventory and readiness opinion are owner-attributed;
this writer has not independently verified them. It reports duplicate `[666827]` idle and owning
nothing, and chassis `[f0c915]` idle; those claims do not substitute for the bridge's live identity
check or John's future offline confirmation. The report calls `.scratch/wp01-handoff/evidence/`
copies durable, but they remain gitignored local material under the standing maintenance rule;
confirmation reviews 1–5 survive only in summaries/ephemeral transcripts according to its §5.
The reported invalid run is marked by
`.scratch/wp01-handoff/evidence/wp08-3-custody/scratch-evidence/wp08-3-06f08a3/CONTAMINATED.txt`
(marker path confirmed locally); exclude it from valid gate evidence. Carry those retention
limits into AUR-GOV-06; do not mark the report SUFFICIENT yet. No earlier AUR-GOV-02 claim was
recorded in this plan; receipt of the owner-authored submission is recorded without inventing a
retrospective claim time. AUR-GOV-07's inventory dependency is now available for review, not yet
accepted as sufficient.

**Additional bridge observations (received after the 19:51 checkpoint):** the parent reports
both owners accepted Emmy's coordination; vehicle K1 `f808f97` had 535 passing tests, with later
round-5 gates still outstanding. That earlier per-commit receipt does not supersede report v1's
later per-commit progress or establish final-head validation. John reportedly answered chassis
numbered item 1: “Yes, default to yes - aurora is our technical gold star for containerisation
(but also look at aurora-prime as it might have enhancements you can use)”. Record this as a
**relayed, scoped Plan 9 approval**; the surrounding numbered proposal has not been inspected by
this writer, so no broader defaults or implementation permission are inferred. `/history` design
or brief, chassis-main merge/landing and root authority remain unapproved by this checkpoint;
silence is not approval. This task performs no Plan 9 implementation.

AUR-GOV-05/06 have preliminary inputs here and in section 2 but remain WAITING under their
existing dependencies. AUR-GOV-09–12 remain WAITING; no readiness or acceptance statement is issued.
Emmy remains the serial writer of this plan.

**Smallest next documentation actions, for the bridge to coordinate without duplicate requests:**

1. Incorporate the native-browser worker's current owner identities and work-in-flight deltas
   into AUR-GOV-01/02/03; reuse existing owner records by exact version rather than request new
   parallel reports. Vehicle `[610587]` and chassis `[8a7d49] are reported identifiers, not this
   writer's verified session inventory; resolve the second vehicle session and its working paths.
2. Link the final-head vehicle gate/review receipts and eventual merge-SHA comment when the owner
   supplies them. Chassis then owns exact-SHA adoption evidence (pointer, pins, deployment and
   integration); a dry-run receipt cannot substitute. Record #39 command-loss and #40 residuals
   as inherited gaps, and keep physical acceptance separate from development gates.
3. Complete AUR-GOV-05 from existing decisions: retain John-reserved cap/model, transcript,
   journal scheduling, chassis-main landing and branch-protection choices; distinguish agreed
   clock/pause semantics from future implementation. Confirm the reported scope exchange from
   both owners; the vehicle's restart recommendation is not chassis acceptance.
4. Preserve final receipts now referenced only through scratch or generic “session instruction”
   when their owners supply durable copies. Record any essential recovery/authority gap before
   a future custody assessment; do not initiate owner shutdown to close a documentation task.

**Preservation checkpoint:** no files were staged. Pre-existing changes were the five files
`SKILL.md`, `references/commands.md`, `references/error-codes.md`,
`references/team-coordination.md`, `references/workflow-patterns.md` under each of
`.agents/skills/filigree-workflow/` and `.claude/skills/filigree-workflow/`; the submodule difference;
`governance/vehicle/decisions.md`; and untracked `docs/plans/` containing
`2026-10-03-operationalise-experiment.md`, `2026-10-03-operationalise-experiment.review.json`,
`2026-10-04-vehicle-to-green-evidence.md`, `2026-10-04-vehicle-to-green-programme.md`, and
`2026-10-04-vehicle-to-green-review.md`. This master plan was already untracked. Preserve all;
do not stage owner files or the gitlink with this update. `/tmp/head_tree` remains prunable and
untouched. Vehicle worktrees reported by Git remain the owner's to inventory; no cleanup is done.

The two coordinator document originals and their review diff are session-local aids under
`/tmp/space-aurora-governance-01a12501/`; they are not durable validation receipts. The reviewable
result is this plan and `coordination.md`. No commit or push is claimed: the required commit gates
in `AGENTS.md` and `chassis/practice.md` are not run under this no-tests assignment.

**Final inspection delta, 19:54 AEDT:** concurrent chassis commit
`3ec1b4ec1a5cc540b713d6cc4a26d967b2f15436` committed the vehicle decisions verbatim, added the
AUR-GOV-02 report and linked it from the vehicle snapshot. Consequently `vehicle/decisions.md`
is no longer dirty. This writer did not make that commit or edit those three owner files; the
19:51 inventory above is historical. The remaining unrelated dirty/untracked paths are unchanged,
and the index is empty. Independent read-only review accepted the leadership/custody framing and
requested this new report/checkpoint reconciliation, now recorded. No runtime, hosted or product
validation is claimed.

Use one compact block per task, retaining earlier verdicts when revised:

```text
Task ID / state:
Claimant identity, accountable line, contributors, claim time:
Report version / as-of time / repo and full SHA(s):
Deliverable: facts, boundaries and remaining work, with source paths/lines or issue/comment IDs.
Evidence: exact reviewed/validated/merged/adopted/accepted scope, receipts and durable locations.
Unknowns/blockers: consequence, owner, next action, approval needed and access limitations.
Changes since baseline: branches, dirty paths, evidence and in-flight work; no secrets.
Emmy review: date, SUFFICIENT or CORRECTIONS, concrete missing items and report version reviewed.
```

At the final checkpoint, include the exact dirty/untracked path inventory and preservation
instructions, not merely “tree dirty.” Link report acceptance to the reviewed version. Do not
clear or collapse an unresolved question just to make the board look complete.

## 9. Inventory sufficiency review — 2026-10-10 20:02 AEDT

Reviewer: Emmy, coordinator documentation chat `01a12501-b067-7581-b5b2-3d4945441dc2`.
Criteria: sections 3, 4 (AUR-GOV-02/03) and 6. Both reports were read in full against the task
requirements, current local Git/worktree evidence and the cited decision/ledger records. These
are **inventory sufficiency judgments**, not engineering validation, product acceptance, an
AUR-GOV-10 readiness assessment or custody acceptance. The bridge's report that John stood back
at 08:57 UTC leaves Emmy coordinating and does not authorise owner shutdown.

| Task / verdict | Exact report reviewed | Reasons and limits |
|---|---|---|
| **AUR-GOV-02 — SUFFICIENT** | [Vehicle v1](vehicle/records/2026-10-10-aur-gov-02-vehicle-custody-inventory.md), as of 08:51 UTC; chassis commit `3ec1b4ec1a5cc540b713d6cc4a26d967b2f15436`; file SHA256 `cc85727a0880b57b59c9387c531d6e6787c676359d3b3166eeadf4742a7cb91a` | §§1–4 locate the repository/object store, refs, worktrees, dirty state and #21 continuation at exact head `45f426763280aa1274732fc35f99584b4d7f9ebc`. §§5–6 identify evidence limits, the implementer, duplicate session and shared-path incident; §§7–10 name boundaries, residuals and next owner/action. Missing final gates are explicitly unfinished work. Review/gate/probe results and remote vehicle claims remain attributed to the owner, not revalidated. |
| **AUR-GOV-03 — CORRECTIONS** | [Chassis v1](chassis/records/2026-10-10-aur-gov-03-chassis-custody-inventory.md), in `486960c515b0d9d3d6e0a677f3c9fec27eb965b0`; file SHA256 `8eda758447c8ef64f0acfd744ffbea69321a8c69b6379ea8e219f81aa66864c8` | The inventory otherwise locates the required work, ownership, debts and preserved unknowns, including paused SV work and plan 8/adoption interaction. One material correction: §11 line 114's adoption-directory build instruction is unsafe without §6's verified HEAD/gitlink equality; §2 already shows that directory does not satisfy it. Also correct the approximate “20:15 AEDT” cutoff (later than its 19:59:19 commit and this review) and the blanket “all branches below were pushed” claim despite two local-only entries. A short dated owner addendum suffices; no implementation, rebuild, checkout change or full replacement report is required. |

**Independent evidence checked:** host `nyx.foundryside.dev`, cwd `/home/john/space_chassis`, branch
`aurora-port`, HEAD `486960c…`; commit content touches only the chassis inventory, decisions and
open-items files, not coordinator documents. Live `git ls-remote --heads origin
refs/heads/aurora-port` at approximately 20:01 AEDT returned the full `486960c…` SHA, independently
confirming publication. Initial sandbox DNS resolution failed; the authorised read-only lookup
succeeded. Local worktree inspections confirm `phase-b-dryrun` at `39ba76d…`, its vehicle clone at
`06f08a3…` against gitlink `dd79e76…`, and the vehicle implementation/probe worktrees at `45f4267…`.
No fetch, tests, hosted CI inspection, Docker operation, `.env` read or implementation was done.

**Evidence limits retained:** the vehicle `CONTAMINATED.txt` was read and explicitly says two
sessions wrote one gate directory; that run must never support a pass. Its referenced clean rerun
was not revalidated here. `.scratch/` evidence remains local and gitignored; rounds 1–5 confirmation
texts are represented by summaries, with originals ephemeral. Chassis's 569 root passes are an
owner receipt at `3ec1b4e` in report §10, plus the bridge's report of 569 for the submission commit;
no exact-commit raw test log was inspected. Source inspection confirms no tracked `.github/`
directory here, but that alone does not prove absence of every possible hosted check. Preserve
the owner's “no hosted CI” statement as attributed, not an independent hosted-service audit.

### Scoped decisions now recorded

At `486960c`, `chassis/decisions.md:50–52` and report §8 supply the previously missing context.
John's **Plan 9 six defaults are approved**, as reported directly by the receiving chassis owner:
visible core/fleet budgets and corrected allowance text; `aurora_history` without model summaries;
recorder connection cap/idle timeout only; hash-pinned dependencies; rejected bodies above 64 KiB
as SHA256 plus preview; Aurora stream limits (1200 requests, 2M tokens per stream, 20M fleet per
hour). Aurora is the containerisation reference; Aurora Prime is to be inspected for enhancements.
The owner must write/review the plan before implementation; this review performs neither.

**Own full history is approved in principle**, read-only and restricted to the agent's own lineage,
with the three-hour reasoning-recovery acceptance story. A database is an acceptable design option;
using it as the official record from which context is read is **still a proposal**. Detailed history
design, all brief/prompt wording, chassis-main landing and host/root actions remain John-reserved.
The peer-write prohibition remains in force. These are scoped owner-reported decisions, not a
blanket approval from silence or Emmy's leadership. Both owners now record the scope exchange;
no further duplicate report is needed merely to establish reciprocal attribution.

### Carried risks and precise next actions (route through the bridge)

| Item | Classification / accountable owner | Next documentation action |
|---|---|---|
| `[f0c915]` mirror identity; vehicle `[666827]` said idle | Open final-transfer identity dependency, not missing inventory. Bridge/John own confirmation. | Confirm live identity, alias relationship and whether either has independent working paths before any future AUR-GOV-11. No owner is stopped or declared offline by this review. |
| Stale operator images and example-valued `llm_console_seed.json` | Host readiness/recovery work owned by John; authority is already explicitly reserved. Not a missing ownership fact or a prerequisite to accepting these inventories. | Carry into AUR-GOV-08: John retains rebuild/removal/`prepare_host.sh` decisions; record eventual receipts before a real start or recovery claim. Do not run cleanup or treat these actions as transferred to Emmy. If exclusive host custody is later requested, resolve its scope explicitly. |
| Vehicle build provenance | **AUR-GOV-03 correction**, Chassis owner; no build guard is authorised. | Add an explicit correction to §11: neither listed checkout currently satisfies production-build pin equality. Require verified vehicle HEAD/gitlink equality at the intended adopted SHA before such a build. Adoption-directory naming is no exemption (`06f08a3` vs `dd79e76` today). Preserve intentional dry-run evidence separately. No checkout/reset/build is requested here. |
| Vehicle #21 gates, merge and Phase B | Known unfinished engineering; Vehicle supplies merge SHA, Chassis adopts. Not inventory blockers. | Owners refresh exact-head receipts and adoption status when their existing work changes. Chassis should distinguish its next commit on `vehicle-adoption` from final landing on `aurora-port`; neither is `main` approval. No ETA is accepted as a commitment by this review. |
| Plan 9, own-history design and DB-as-context proposal | Known scoped engineering/design work; Chassis leads, John decides reserved matters. | Write/review the authorised plan; return detailed history design/brief wording and the still-proposed DB-as-context choice for John's decision when concrete. Do not reopen the approved own-history principle or six defaults. |
| Raw evidence retention | Bounded evidence gap; respective owners supply receipts, Emmy indexes under AUR-GOV-06. | Preserve existing local evidence, export any surviving confirmation texts when available, or record irrecoverable originals and retained summaries by exact SHA. Exclude the contaminated run. No fresh tests commissioned for this report. |
| Chassis report metadata | Small AUR-GOV-03 corrections alongside the build instruction; Chassis owner. | In the same dated addendum, supply the actual observation cutoff or explicitly unknown; narrow “all branches below were pushed” to the named published branches, preserving the table's local-only states. Leave v1 unchanged. This review makes no 20:15 observation claim. |

**Task consequences:** AUR-GOV-07 has its AUR-GOV-02 dependency satisfied and is **READY, unclaimed**,
not automatically assigned or complete. AUR-GOV-04/06 remain WAITING for the small AUR-GOV-03
addendum and re-check. AUR-GOV-01 still needs the bridge's live identity reconciliation;
AUR-GOV-05 therefore remains WAITING, with the scoped decisions above ready as inputs.
AUR-GOV-08–12 remain WAITING. No new John decision is required to supply these corrections. The remaining
identity, recovery guidance and evidence work must be reconciled before any programme-wide
readiness assessment; both owners continue their assigned work.

Independent read-only review agreed AUR-GOV-02 is sufficient and identified the AUR-GOV-03
build/metadata corrections above. Emmy adopted those findings before closing this review.

## 10. Chassis v1.1 re-check and coordinator checkpoint — 20:11 AEDT

**AUR-GOV-03: SUBMITTED v1.1 → SUFFICIENT.** Emmy reviewed the dated addendum to
[the chassis inventory](chassis/records/2026-10-10-aur-gov-03-chassis-custody-inventory.md) at
`1effa040d47fda5f6c919e1ddd45e9846ec0ffcc`; complete report SHA256
`f70222a1c4fe0da4886595876e1c69321500a64821359a5af0587fcfc24f0781`.
This supersedes section 9's CORRECTIONS verdict for v1. Its three findings are closed:

| Finding | Exact closure evidence |
|---|---|
| Unsafe adoption-directory build advice | Addendum C2 explicitly withdraws v1 §11's advice, states neither listed checkout qualifies, and requires vehicle HEAD equal the parent gitlink **and** a clean included build context. The same commit removes the misleading parenthetical from `chassis/open.md`. Local read-only checks confirm main vehicle `8c6f71d…` and adoption vehicle `06f08a3…` both still differ from `dd79e76…`; no checkout was changed. |
| Future-dated observation cutoff | C1 corrects v1 to 19:51–19:58 AEDT, preceding its verified commit time 19:59:19. The addendum separately records a 20:07:24 AEDT re-observation; its commit is timestamped 20:08:44 AEDT. |
| Blanket publication claim | C3 withdraws the claim, distinguishes the two branches this owner pushed, and labels `phase-b-dryrun` and `vehicle-standalone` local-only. A live remote-ref lookup returned neither of those branches. |

Independent read-only re-check also confirmed all three findings closed and the inventory
sufficient, limited to those findings and the related `chassis/open.md` correction.

Live `git ls-remote` at approximately 20:11 AEDT returned `aurora-port` at the full `1effa040…`
SHA, confirming publication. Exact diff from `486960c` contains only the appended chassis report
and its `open.md` correction (66 insertions, one deletion); coordinator documents were untouched.
The bridge reports 569 root tests passing for this owner commit. That receipt remains attributed
and does not satisfy checks for a later coordinator commit with a different staged tree. The
addendum's ignored-file/Docker matching observations are owner-attributed and not verified by a
build here; the conservative clean-context requirement is accepted without claiming such a build.

**AUR-GOV-02 v1 remains SUFFICIENT**, at the unchanged report/file identity in section 9. Its
contaminated-run exclusion, ephemeral confirmation-review evidence and unfinished final gates
remain carried limitations. Neither inventory verdict accepts the product or transfers custody.
Mirror identity and host-operation authority remain distinct follow-ups; no owner is offlined.

**Next bounded handover tasks:** AUR-GOV-04 (Chassis-led interface report), AUR-GOV-06 (Emmy's
receipt index) and AUR-GOV-07 (Vehicle capability/debt report) are **READY, unclaimed**. Reuse the
accepted inventories and existing sources; the bridge routes claims to avoid duplicate owner work.
AUR-GOV-01 still requires the live identity reconciliation; AUR-GOV-05 then incorporates the
scoped decisions already recorded. AUR-GOV-08 follows its existing report dependencies; no
readiness/offline/custody step is advanced automatically.

**Coordinator commit status: BLOCKED BY REQUIRED CHECKS, not attempted.** `AGENTS.md:44–48`
requires the whole suite before committing. `chassis/practice.md:28–32` requires the root suite
(`python3 -m pytest tests -p no:cacheprovider -n 8`) after staging, plus ruff check/format. No
documentation-only exception is stated. This assignment prohibits heavy tests and bypassing
required gates; previous owner receipts are for different trees. Therefore only this plan and
`coordination.md` are edited, both remain unstaged/uncommitted, and no push is made. This is a
written workflow constraint, not an observed hook failure or automatic approval rejection.
No change to the commit policy is inferred. A later authorised commit needs the required checks
against the intended staged coordinator files, preserving every unrelated path.

## 11. Next claims and durability continuation — 20:16 AEDT

The coordinating chat `01a12334-35ad-748b-99eb-2d3a16598084` now explicitly authorises the
repository-required tests/checks and commit/publication of **only** the two coordinator documents.
It clarifies that the earlier no-heavy-tests limit was Emmy's task-scoping precaution, not a user
ban. This supersedes section 10's validation-scope blocker; no gate is waived. Inspect resource
use first, run validation sequentially with reduced scheduling priority, and preserve owner work.

Emmy reread the task board and current claim history: neither AUR-GOV-04 nor AUR-GOV-07 had a
claim. Their inventory dependencies are satisfied. The following bounded assignments are recorded
at **2026-10-10 20:16 AEDT**, by the coordinating chat's explicit instruction:

| Task / state | Claimant / line | Scope and identity provenance |
|---|---|---|
| **AUR-GOV-04 / CLAIMED** | Existing Chassis Code owner `session_019mkPNN5J3Atit9tUA6zrNY`; Chassis | Interface report specified in section 4. Same claimant as AUR-GOV-03; reported peer `[8a7d49]`. Vehicle may contribute through the bridge; no additional claimant is assigned. |
| **AUR-GOV-07 / CLAIMED** | Existing Vehicle Code owner `session_01GRfs7dVMu4v5airK6q3w9C`; Vehicle | Capability/debt report specified in section 4. Browser-facing identity supplied by the coordinating chat; AUR-GOV-02 used local session `a728e992-9471-46ab-9efe-ce550d7ece5f` / peer `[610587]`. Their alias mapping has not been independently verified by this writer; the bridge must route to its named existing owner, not start a second writer. No competing task claim is present. |
| **AUR-GOV-06 / WAITING, unclaimed** | No new assignment | Per the continuation instruction, wait for AUR-GOV-04/07 inputs and a separate owner assignment. Existing inventory sufficiency remains unchanged. |

These entries authorise bounded reports, not new engineering. The browser worker delivers the
assignments; this writer does not message owners. Mirror identity and future custody confirmation
remain open independently of these claims.

The durability receipt belongs to the coordinator commit message and final chat response: exact
staged file scope, commands/results, commit and published ref. Earlier uncommitted-state entries
above remain historical checkpoints; this document alone does not assert that publication passed.

## 12. Validation receipt and delivery blocker — 20:30 AEDT

Only `governance/MASTER_GOVERNANCE_PLAN.md` and `governance/coordination.md` were staged by name
before the gates. Tested source HEAD: `1effa040d47fda5f6c919e1ddd45e9846ec0ffcc`, vehicle working
checkout `8c6f71ddc44597b204078c12b5232ef47ed5f99a` (preserved; gitlink remains `dd79e76…`).
Tests ran sequentially at `nice -n 19`, eight workers, so other host work retained scheduling
priority. This was normal repository validation, not a live-container or mission run.

| Check | Actual result |
|---|---|
| Initial sandboxed root suite | 557 passed, 3 failed, 9 errors; local HTTP tests could not create sockets (`PermissionError`). Not counted as a passing gate. |
| `python3 -m pytest tests -p no:cacheprovider -n 8`, with local socket access | **569 passed**, 33.36 s, exit 0. |
| `python3 -m pytest -p no:cacheprovider -n 8`, with local socket access | **1 failed, 1722 passed**, 655.91 s, exit 1. |
| `uvx ruff check . --no-cache` | All checks passed, exit 0. |
| `uvx ruff format --check . --no-cache` | 110 files already formatted, exit 0. |

**Concrete blocker:** `tests/test_vehicle_reconciliation.py::test_the_vehicle_passes_the_contract_probe`
failed at line 259. The probe reported `FAIL a non-string element refuses the whole batch` with
**0 result files**; its other results were 13 passed and one skipped (no deferring verb published).
`contract/diode_probe.py:212–221` submits a valid command plus integer `42` and expects at least
one refusal result. The same test passed in the root-only gate, so the runs disagree. Cause is
**not established**: no claim is made that load, the known vehicle claim race or a timeout explains
it. No retry-until-green, waiver or implementation fix was performed.

Evidence lives under `/tmp/space-aurora-governance-01a12501/delivery/` (local, not durable):
`root-tests-host.log`, `full-tests.log`, `ruff-check.log`, `ruff-format.log`. Full-run log SHA256:
`4f2ee9c136da13effc26f2157d99c0b460a29a25e124e77157757ed9861b5a1b`.
The staged document SHA256s tested before adding this receipt were respectively
`f4a93605decc131d2cf7d6828ab25cd0a65ab7fd82cb169de0b25ef842a53273` and
`b736099b5027f78db0687f99a46905d5e2da0392b4a8811ee92fc1f7b85642c9`.
The receipt itself is a subsequent coordinator-only edit; no passing gate is claimed for a new
commit. All protected owner/unrelated file hashes were unchanged at the final validation check.

**No coordinator commit or push was attempted.** The full-suite requirement in `AGENTS.md`
prevents publication after this result. The parent/bridge should route this evidence to the
Chassis owner for a bounded investigation, with Vehicle contribution if the failure crosses the
interface. That is a proposed next action, not an implementation assignment from this task.
AUR-GOV-04/07 remain claimed; AUR-GOV-06 remains waiting. No owner report, checkout, runtime,
repository structure, main branch or custody status was changed to get around the gate.

## 13. Interface and capability report review — 20:41 AEDT

This is a read-only review of owner reports, with updates only to the two coordinator documents.
No test, reproduction, instrumentation, build, cleanup, reset, staging, commit, push or owner
message was performed for this review. The index was preserved. Existing coordinator staging
therefore remains an earlier checkpoint; this review is a later working-tree edit.

### Versions and publication

| Report | Exact reviewed version | File SHA256 | Verdict |
|---|---|---|---|
| [AUR-GOV-04](chassis/records/2026-10-10-aur-gov-04-interface-report.md) | v1.2, `613557528ffc42d4ea8d4ae0a3b3a2c453825ffa`; includes v1.1 corrections and the stopped-reproduction receipt | `aef1d2644c18f4cf04df73242e9ef2c44085de8bffcf2ddfb4f8bae0d6464338` | **CORRECTIONS** |
| [AUR-GOV-07](vehicle/records/2026-10-10-aur-gov-07-vehicle-capability-debt.md) | v1, `d82827f5740f3b39286f76466855cb17c26e0409` | `70dbd1654621aee22bf663f4f55d407c73ceb5430889cead751d5918a520d056` | **SUFFICIENT** |

Live `git ls-remote --heads origin refs/heads/aurora-port` at 20:41 AEDT returned the full
`613557528…` SHA. Both report commits are in that published history; the current report files
match the reviewed versions. Publication is verified, but does not establish commit-gate
compliance or make the coordinator documents durable. No hosted CI or live acceptance is claimed.

### AUR-GOV-04: two bounded corrections

**C4-1 — incorrect contract comparison, report line 81 and related decision at line 174.** The
report says `pending.json` is absent from the contract's section 2 and proposes naming it there
or moving it. In fact, `docs/diode-contract.md:35` expressly lists
`<DIODE_DIR>/<slug>/pending.json` as the vehicle's own deferral queue. This is also present at
the report's source baseline `1effa040`; it is not a subsequent contract change. The false
absence claim creates an unnecessary cross-line decision and fails the reconciliation criterion.

**Next owner/action:** Chassis Code supplies a bounded addendum correcting the row and withdrawing
the absence-based decision. If it identifies a remaining difference between the contract's queue
description and the vehicle's published-copy semantics, state that precise difference with source
evidence and vehicle response; do not change the contract merely to resolve this review. Keep
the separately established hidden-identity exposure on the old pin and its adoption dependency.
The bridge routes this correction; this writer has not instructed the owner directly.

**C4-2 — existing gate precedence framed as unresolved, report lines 162–171.** Practice
expressly defers to AGENTS.md, so the existing whole-suite rule applies. The owner addendum
should distinguish that established precedence from a request for new authority to create a
documentation-only exception. Retain the candid validation disclosure; do not recast the old
commits as compliant. The detailed interpretation and minimum operator decision are below.

The rest of the report maps the interfaces, mounts, networks, credentials, hidden truth, exact
adoption inputs and future clock/pause work sufficiently for this bounded report. Its latest
v1.2 supersedes the earlier statement that a reproduction was running: it was stopped before
execution, and no source was changed. #39 is a hypothesis for the failed probe; causation remains
unproven and scheduler delay remains open. No finding here requires another test or a code fix.
An independent read-only reviewer confirmed both corrections and the AUR-GOV-07 sufficiency
verdict. No owner contact or additional testing was commissioned by that review.

### AUR-GOV-07: sufficient, with evidence limits carried

The report distinguishes **108/139 configured**, **52/139 advancing** and **no accepted physics**;
it reports 195 unset scalars, 273 declared lint debts and strict exit 2 without calling that a
pass. It maps WP01/WP08 residuals, M2–M5, #21 review dispositions, #39/#40, missing physical inputs
and gates D/I/V/M/E to sources, owners and next actions. These meet section 4's report criteria.

Read-only checks matched the stored `f12e522` readiness/build-order outputs in both Python lanes,
the normal-lint receipt, and `docs/completion.md` at `64fc58c`. Corpus comparison showed no YAML,
domain or `plant.md` change across the cited baselines; the inspected later `plant.py` change
hardens corpus enumeration errors, not the readiness calculation. No measurement was rerun.
The remaining review, CI and stress claims remain owner-attributed receipts at their stated
cut-offs, not independent reruns or fresh acceptance of #21. The owner's session alias mapping
is now explicitly self-attributed in the report; that does not resolve every AUR-GOV-01 identity.

The report calls its scratch copies durable, but they remain local ignored evidence, with no
durable archive established by this review. AUR-GOV-06 must preserve or index them with that
limitation. Its phrase that the chassis “runs” `dd79e76` is accepted only as the named recorded
gitlink baseline: the actual preserved working checkout remains `8c6f71d`, and no running stack
was inspected. Configured/advancing counts do not describe that older pinned product. The #39
explanation remains a hypothesis for the coordinator failure, not proof of its cause.

### Commit-gate compliance is a separate decision

The Chassis owner discloses at report lines 162–165 that governance commits used the **root
suite (569) and ruff, not the whole suite**. Lines 207–212 attribute a root run, started after
20:34:49 and finished before 20:36:58 AEDT, to commits `d82827f` and `f99d0d3`, and disclose **no
tests for the addendum commit**. The bridge likewise reports addenda without new tests. These
are attributed receipts; this review ran no tests and does not invent checks for any commit.
The v1.2 receipt establishes that the contemplated coordinator reproduction never ran, so the
reported root run did not overlap such a reproduction.

There is no unresolved precedence question in the written rules: `AGENTS.md:44–48` requires
the whole suite before committing, and `chassis/practice.md:3–5` expressly names `AGENTS.md`
as authoritative. Its root-suite-after-staging and ruff requirements at lines 28–32 do not waive
the whole-suite requirement. Neither document states a documentation-only exception. The
disclosed root-only report gates therefore did not satisfy the whole-suite rule; the no-test
addendum disclosure also departs from the practice gate. Publication and content sufficiency do
not retrospectively approve those departures. The coordinator's full-suite failure remains open.

**Minimum operator decision for coordinator-document durability:** John must either explicitly
authorise a narrow documentation-only exception or revise the applicable gate for these two
named coordinator files while retaining the failed receipt; or retain the current rule, leaving
publication blocked until separately authorised diagnosis/remediation and the required successful
validation. Emmy recommends a prospective, explicit decision, not an inferred or retroactive
waiver. This review neither grants that exception nor authorises another run. Clarifying practice
wording is subsequent line-owned work, not an edit made here.

**Task consequences:** AUR-GOV-04 is CORRECTIONS with its existing claimant; AUR-GOV-07 is
SUFFICIENT. AUR-GOV-02/03 remain SUFFICIENT. AUR-GOV-06 remains WAITING, unclaimed, for the
corrected interface input and the separately required assignment; AUR-GOV-08 still waits for
04/05. AUR-GOV-01 identity reconciliation and all readiness/offline/custody gates remain open.
No new implementation, shutdown, custody acceptance or product acceptance is implied.

## 14. Morning resumption and owner-routing checkpoint — 2026-10-11 10:04 AEDT

John's instruction at 2026-10-10 23:00 UTC, relayed through coordinating chat
`01a12334-35ad-748b-99eb-2d3a16598084`, resumes Space Vehicle, governance and chassis in parallel
with ELSPETH. It supersedes the evening pause, not any product decision, review or commit gate.
This writer verified `nyx.foundryside.dev`, `/home/john/space_chassis`, `aurora-port` at `613557528…`.
Only the coordinator's two working documents are updated; existing staging and owner files stay intact.

### Verified checkpoints

- Vehicle PR #41 is **MERGED**, merge SHA `f44399645fb2633e695a5d758cb5a41f43fb848c`, from a live
  GitHub read; remote `main` names that SHA. Its Git tree equals tested `45f4267`:
  `4f1bdfe55249ff9770749dcb036c1f3b99fb7b7f`. The chassis's main vehicle checkout is still clean
  at `8c6f71d`; no submodule update or reset was performed.
- Chassis `.claude/worktrees/vehicle-adoption` is `phase-b-adoption`, HEAD `be63f934…`.
  Its actual index entries exactly match frozen tree `b29bf8af40dab08bdb890039483fb205f8fccbfe`.
  `.scratch/phase-b-candidate-2.diff` still hashes to
  `5af0d332638c2b513adf6004856d41798a2e6d2022b5659bdcc6c5f6adf17fec`.
  `.scratch/phase-b-gates-2/summary.txt` records root 592, full 1941 and live 19 passing on that
  same tree before and after its run. These are inspected prior receipts, not new tests or proof
  that the review findings are fixed. `review-phase-b-confirm.md` still names three Important
  findings and one minor wording correction.
- `.scratch/CHECKPOINT-2026-10-10-night.md` and
  `.scratch/wp01-handoff/diag-contract-probe/CHECKPOINT.md` preserve the two owners' night state.
  Diagnostic archive SHA256 remains `6e3387cd9d49c41c107b07a7e56aeb2982ac3576cc60b2fbba03390cae5e7a10`.
  It supports erased batches in the captured runs; the original coordinator failure had no such
  trace, so its exact cause remains inferred, not observed. No diagnostic rerun was made.
- AUR-GOV-04 working v1.3 SHA256 is
  `0ec00b3c879137bc4901a3b0402265fa6e00659df8b60725e76500cc1ee8553e`. Both C4-1 and C4-2 are
  fixed against the contract and practice. An independent read-only bounded re-check agrees:
  **SUFFICIENT for documentary content**. Its old pause/instrumentation wording is historical
  and superseded by the subsequent diagnostic authority and this resumption. Publication and
  commit compliance remain separate; no exact-current-coordinator-tree passing gate is claimed.

### Existing owners and next disjoint increments

| Owner identity retained from checkpoints | Next bounded increment after contact confirmation | Paths / boundary |
|---|---|---|
| Chassis Code `session_019mkPNN5J3Atit9tUA6zrNY`, peer `[8a7d49]` | Finish Phase B's second correction pass: refresh identity enumeration after vanished files and parse the already-read text; prove the command falls within the actual checkpoint/recovery interval; correct different-world and startup-refusal wording. Refreeze, independent confirmation, then required gates in the coordinated capacity slot. | Existing `phase-b-adoption` worktree; chassis owns tests/runbooks. It remains the sole driver of cross-line probe reproductions. Do not combine coordinator staging into owner commits. |
| Vehicle Code `session_01GRfs7dVMu4v5airK6q3w9C`, local `a728e992-9471-46ab-9efe-ce550d7ece5f`, peer `[610587]` | Resume #39 design v2 and decision preparation; address held-descriptor identity, type-exact comparisons, restart variables and same-cycle publication. Do not select pending platform or double-race semantics. Independent design review precedes implementation. | Vehicle-owned design and subsequent console changes in its own branch/worktree; no chassis implementation. Diagnostic `1caab23` remains unqualified evidence, not an adoption candidate. |
| This coordinator | Record the verified resumption, close the two report findings, return routing/capacity needs to the bridge. AUR-GOV-06 awaits its separate assignment; report inputs are now available. | Only master plan and coordination working files. No implementation, test driver or duplicate owner worker. |

**Initial local contact limitation (superseded by the cloud-route receipt below):** these were
checkpoint-verified identities, not live session-route verification by this writer.
The available app list exposes review chats but no verified Claude owner route; this chat has no
Claude `ListAgents`/`SendMessage` tool or thread-send tool, and computer inventory returns no apps
or browsers. Host inspection finds existing Claude processes (including one in the adoption
worktree); their sleeping state does not establish that either owner is idle or offline. No
supported process-to-session mapping was established. The bridge must refresh the existing
owner routes and relay these bounded handoffs once, recording acknowledgment. **Recipients
messaged by this writer: none. No new worker or project entry was created.**

The bridge initially reported its Velma browser initialization failed (missing Windows platform
directory, HRESULT `0x80070003`) and it had no callable Claude connector. This was a local route
limitation, not global browser unavailability. Current host evidence
includes Claude PIDs `944145`, `944568`, `1410330` and `4020598` in the main chassis directory,
and `1962796` in the adoption worktree, all in sleeping state at inspection. This is evidence of
existing processes, not session attribution or permission to replace them. At that checkpoint,
implementation handoff awaited a supported owner contact/acknowledgment route. **No new Codex implementation task is
necessary or safe to assign against these already-owned paths yet.** Read-only governance work
continues here; a new direct-project task would not solve the ownership uncertainty. No manual
SSH, custom UI workaround, process intervention or custody transfer was attempted.

**Cloud-route update — 10:07 AEDT:** Emmy reports that the authenticated cloud browser is
available and its browser worker has opened the existing Vehicle Claude session. That worker
is handling resume instructions for **both existing owners**, using the verified checkpoints
and the shared one-selection/two-workers-total cap. Owner acknowledgments have not yet been
relayed here. This is bridge-attributed route evidence; this writer did not inspect that browser.
The browser worker is the sole sender; no duplicate sends or replacement owners are authorised
by this update. Both #39 product questions have been asked of John and remain **PENDING**.
This coordinator continues only independent governance work while awaiting those receipts.

### Capacity and remaining decisions

Host inspection found 24 logical CPUs, about 28 GiB available memory, and the active ELSPETH
qualification driver with six worker processes in `nyx-ci-shards-084-20261011`. Repository
index/HEAD lock files checked were absent; live Filigree database locks exist and were untouched.
Absence of a Git lock is not ownership permission. No Space test or build was started here.

**Capacity receipt:** the bridge relays ELSPETH owner's 23:02 UTC observation (24 logical CPUs,
load 3.68, 27.8 GiB available RAM; one running/five sleeping workers, about one CPU measured)
and permission for **one bounded Space test selection with at most TWO workers total across
both lines**. That allowance has not been consumed here. One agreed driver must claim the slot;
it is not two per-line allowances or blanket capacity for full/live/build gates. The proposal
is `nice -n 19`; coordinate before any increase or heavy gate. Keep required coverage and arrange
any mandated worker count separately. Low-CPU design and review can proceed in parallel. Leave
ELSPETH's qualification and serial PostgreSQL phase untouched. No GPU work, Simic/Sultai
management or host changes here.

John's decisions remain open on Linux/filesystem compatibility when atomic exchange is unavailable
(named refusal versus a qualified fallback) and the during-claim second-batch rule. Resumption
does not approve either. No main merge, deployment, build-guard approval, gate exception or
exclusive custody transfer is inferred. Phase B's prior green tree does not qualify its next
corrected tree or the main checkout's coordinator documents. Preserve all required gate receipts.

## 15. Shared Space test slot and live-resource assessment — 2026-10-11 10:16 AEDT

**Owner acknowledgment:** Emmy confirms both existing Claude owners received the bounded resume
instructions and are active. Vehicle is preparing conditional #39 design v2; Chassis is correcting
the three Phase B findings in `live/test_vehicle.py` and `README.md`, then refreezing for independent
review. The cloud browser worker remains the sole sender. Neither product decision is approved.

**Slot ledger: FREE / NOT GRANTED.** This coordinator controls one shared Space test selection,
maximum TWO workers total, nice 19, no GPU. Chassis is the next intended holder after its exact
candidate and independent-review readiness receipt. Vehicle has no simultaneous test allocation.
A 30–40 minute two-worker full suite is allowed validation time; the 30-minute implementation
increment does not truncate it. Before an actual grant, refresh host capacity and confirm no
Space driver owns the slot; return the grant through Emmy/browser, recording owner, selection,
candidate identity, start and eventual exit/evidence. Do not infer readiness from elapsed time.

At 10:15 AEDT the host had 24 logical CPUs, load 4.56/4.28/4.86 and 41,342 MiB available RAM
(40.4 GiB). ELSPETH qualification PID 2222075 was active in `nyx-ci-shards-084-20261011`;
an additional ELSPETH process was present in `nyx-release-integration-084-20261011`. They were
left untouched. No Space pytest driver or smoke container was observed in the targeted checks.
One unrelated Docker container was present and was not inspected beyond its ID/name. This is
a capacity snapshot, not a future grant; prior six-worker status is not assumed still current.

### Existing live configuration: concrete limits, not measured demand

Read `live/stack.py`, `live/conftest.py`, `scripts/build_compose.py` and the generated compose
configuration in the adoption worktree. Compose was rendered read-only using `.env.example`
and a sanitized process environment; no stack was prepared or started, and operator `.env`
was not read. Docker uses the systemd cgroup driver and cgroup v2.

| Service, per smoke stack | Count | Configured CPU quota each | Configured RAM maximum each |
|---|---:|---:|---:|
| agents | 3 | 1 CPU | 3 GiB; memory+swap also 3 GiB |
| recorders | 3 | none | 512 MiB |
| fleet monitor | 1 | none | 256 MiB |
| review | 1 | none | 512 MiB |
| diode fixture **or** vehicle | 1 | none | 512 MiB |
| stub | 1 | none | none |
| pytest driver and Docker client processes | outside containers | none; nice is priority only | none |

The listed Docker CPU/memory fields are runtime enforcement settings when those containers are
created, not evidence from running smoke containers (none existed). Non-agent swap ceilings are
not explicitly set. Each stack has **10 containers**, with **11.75 GiB of specified RAM maxima
plus an unbounded stub**, and three individually CPU-capped agents plus seven uncapped services.
The two session-scoped fixtures can coexist: **20 containers, 23.5 GiB specified RAM plus two
unbounded stubs**, and no aggregate CPU bound. Pytest `-n 2` would risk duplicating session fixtures;
live selections should use one serial driver, not xdist, and explicitly tear down one stack before
the other. Splitting fixture-backed tests and `live/test_vehicle.py` into sequential selections
can retain all 19 tests; the owner must retain collection/evidence and validate the ordering.

Builds are also unbounded: `SmokeStack.build()` calls Compose build for agent and, in the vehicle
variant, vehicle targets in one invocation; it does not set build parallelism or CPU/RAM limits.
The second stack's build can happen while the first stack remains alive. The existing builder
is BuildKit v0.33.1 with the Docker driver. Docker's service reports CPUQuota and MemoryMax infinity,
and its cgroup files confirm `cpu.max = max 100000`, `memory.max = max`. Compose's installed
`--memory` help explicitly says it is unsupported by BuildKit. Buildx advertises `--resource`
(memory and CPU quota) and `--cgroup-parent`, but the current harness does not use them and no
enforcement qualification was performed. Per-build-container controls alone do not bound concurrent
build steps, shared builder/daemon overhead or the host test driver.

### Ordering, held phase and concrete option for decision

1. Finish fixes, freeze candidate and obtain independent confirmation; request the shared slot.
2. Fresh capacity check, then required root/full validation sequentially at two workers, nice 19.
   Preserve all results, including failures; no duplicate suite for status. Driver/subprocess RAM
   and CPU beyond worker count are not currently hard-capped; report peaks and stop new phase
   starts if capacity changes. The full suite itself does not collect `live/`.
3. **Live/build phase HELD ONLY:** existing configuration cannot meet a bounded combined allocation.
   No live authorization is issued merely because two pytest workers are permitted. Keep the
   required live gate outstanding; do not weaken assertions or omit tests.

One concrete **proposed, not authorised or qualified** serial live envelope preserves the existing
agent maxima: each agent 1 CPU/3 GiB; each recorder 0.125 CPU/512 MiB; monitor 0.125 CPU/256 MiB;
review 0.125 CPU/512 MiB; stub 0.125 CPU/256 MiB; window 0.5 CPU/512 MiB. That is **4.25 CPUs and
12 GiB per single stack**. Reserve driver/client 0.25 CPU/1 GiB and builder/daemon overhead headroom
0.5 CPU/1 GiB: **5 CPUs/14 GiB total requested live envelope**. The overhead reservation is not
an enforceable per-Space daemon quota on the shared daemon. Two simultaneous proposed stacks
would already require 8.5 CPUs/24 GiB before overhead, so are excluded from this option.

For builds, propose a separate no-stack phase, one target and one execution step at a time,
**2 CPUs/8 GiB for the builder plus 0.5 CPU/2 GiB driver/daemon headroom** (2.5 CPUs/10 GiB
reservation). These are planning budgets, not measured requirements. Enforcing aggregate limits
requires an owner-reviewed harness/builder/cgroup arrangement; existing Buildx flags alone do not
prove this. Do not reconfigure the shared Docker daemon or add a builder under the current task.

**Specific decision needed through Emmy:** either authorise a bounded Chassis-owned test-harness
resource-control increment and agree a numeric live/build CPU+RAM envelope (the proposal above
exceeds a hypothetical two-CPU total cap while respecting the two-worker rule), or provide a
smaller envelope for the owner to qualify without changing test semantics. If strict aggregate
accounting must include shared Docker daemon overhead, an approved isolation mechanism is also
needed. Until that decision and enforcement evidence arrive, hold live/build only. Fresh capacity
and exact reviewed-candidate readiness still precede any full-suite grant. No host, access,
security, deployment or spending change is authorised by these options.

## 16. Resource-control preparation authorised; candidate readiness — 10:19 AEDT

Emmy clarifies that John's Chassis resumption covers the small test-harness resource-control
increment required to run existing gates safely. **The same Chassis owner is the sole writer**;
the browser worker relays the instruction. This coordinator neither sends duplicate instructions
nor creates another test writer. This supersedes section 15's request for preparation scope and
numeric ceilings; it does not grant the test slot.

**Authorised preparation:** ordinary per-run Docker CPU/memory limits and sequential stack/build
execution, preserving existing test behavior and assertions. One live stack at a time, ceiling
**5 CPUs/14 GiB including reserved overhead**; separate serial builds, ceiling **2.5 CPUs/10 GiB**.
All 19 live tests remain, with teardown between serial stack selections. Builds must not overlap
stacks or each other. Independently review the harness change and freeze its exact tree/diff
identity. Record configured limits separately from actual runtime enforcement evidence. Reserved
shared-daemon overhead is not an enforced quota. If strict accounting needs shared-daemon, host
security, access, persistent isolation or network-policy changes, leave that portion unimplemented
and report the residual; none of those changes is authorised. No spending, deployment or GPU use.

**Root/full eligibility is independent of live-harness preparation.** A qualified root/full
candidate may receive its own grant after review readiness and a fresh capacity check, at maximum
two total workers and nice 19. Do not delay it merely because the later live phase is unqualified.
If the owner changes the candidate during validation, preserve that receipt's original identity
and qualify the new tree separately; never present one tree's pass as another's.

The owner has submitted
`chassis/records/2026-10-11-phase-b-test-slot-request.md`. Its frozen candidate is
`04dff0beaa37294bc839122885f3543535520fc5`, verified against the actual adoption index.
Candidate diff SHA256 is `f7bb4c662b144d83128bc337854b011c3506d19d859134e26bef8eaf8a990735`;
delta from the previous candidate is
`bc3dc07330f9b1cd97ed4f6b605660fc5625023d339e8537330ccf9b798f4edf`.
The request's estimates, cache expectations and monitoring proposal are not enforcement evidence;
its proposed overlapping live stacks are superseded by the one-stack ceiling above. Its proposed
automatic retention of the slot through selections 1–3 is not granted. No status-only proof run
is requested.

**Current readiness: NOT READY.** Inspected independent Astra confirmation
`.scratch/phase-b-reviews/review-phase-b-confirm-3-astra.md` says land after fixes: one Important
finding remains. `live/test_vehicle.py:312` requires positive replay before the crossed-checkpoint
retry, so a healthy resume with checkpoint equal to recovered tick and zero replay fails before
retrying. Validate the replay count, handle the crossed-checkpoint attempt, then require positive
replay for the qualifying attempt. The identity scan and README findings are confirmed fixed.
This is the existing owner's correction, not an implementation assignment to this writer.

| Shared slot field | Current receipt |
|---|---|
| Holder | None; FREE / NOT GRANTED |
| Next intended owner | Existing Chassis Code owner, via Emmy/browser |
| Candidate / selection | `04dff0be…` submitted for root then full; remains review-blocked |
| Grant time | None |
| Limits when granted | One selection, max two workers total, nice 19; no GPU |
| Required next receipt | Corrected frozen identity and independent confirmation; fresh capacity and no competing Space driver before grant |
| Release receipt | None: no slot has been granted or run started by this coordinator |

The earlier 10:15 capacity sample is not reused as a later launch check. Live/build grants also
require the independently reviewed resource harness, exact identity and enforcement-verification
plan within the ceilings. Owner-facing grants and status go only through Emmy/browser. Existing
staging and owner work remain preserved; no tests, builds or implementation edits occurred here.

## 17. Ordinary-build feasibility and corrected resource scope — 10:37 AEDT

Emmy clarifies that the numeric live/build ceilings originated as coordination proposals, not
a user requirement to create a new privileged build subsystem. **Do not create privileged buildx
containers, expand daemon/host access, add persistent isolation or build a scheduling platform.**
Ordinary existing serial builds may be assessed for a dedicated Space slot using measured host
headroom and abort thresholds, explicitly **without a hard aggregate build cap**. This supersedes
any reading of sections 15–16 that makes a privileged builder or strict daemon quota necessary.
Keep ordinary per-run container limits and the prohibition on overlapping Space phases.

### Fresh assessment, not a launch grant

At **10:36:20–22 AEDT**, host `uptime`, `free -m`, `/proc/stat` and pressure files showed:
24 logical CPUs; load 4.25/4.25/4.65; **40,453 MiB available (39.5 GiB)**; a two-second sample
**15.4% CPU busy and 0.4% I/O wait**; memory pressure avg10/60/300 all zero. ELSPETH pytest
PID 2222075 remained active. No Space test driver was found in the targeted process check;
the two listed running Docker containers were not Space smoke projects. No workload was changed.

Current builder: existing `default`, **Docker driver / BuildKit v0.33.1**, using the existing
Docker daemon and socket authority. No rootless security option is advertised. This is the
ordinary existing daemon privilege boundary, not a newly privileged builder container. Client
nice/scopes do not constrain daemon-side build execution. Build CPU/RAM demand remains unmeasured:
no build ran for this assessment, and expected cache hits are not a resource bound.

**Feasibility:** current measured headroom supports considering one monitored serial build
selection; no present RAM/CPU deficit warrants a blanket build ban. This is not a proof of peak
build demand or a slot grant. Recheck immediately before launch and retain an abortable driver.
Only the current Space selection may run: build one image at a time with no smoke stack alive;
complete/cancel and verify that build before the next image. Finish required image builds before
starting one capped live stack; preserve evidence and tear it down before the next stack. Do not
overlap root/full tests, builds, or live stacks. No test assertion or required selection is waived.

### Proposed monitoring and stop thresholds for an ordinary-build slot

- Start only with **MemAvailable >= 20 GiB**, one-minute load **< 12**, and sampled CPU busy
  **< 75%**, with no other Space driver/build/stack. These are coordination thresholds, not
  inferred user requirements or kernel limits. A grant must record its own fresh sample.
- Every **5 seconds**, log UTC time, host CPU busy/iowait, MemAvailable, load, memory pressure,
  the Space driver PID/state/RSS, and daemon/containerd CPU/RSS. For live phases also log each
  smoke container's CPU/RAM and startup cgroup-limit evidence. Shared daemon figures include
  other projects and cannot be attributed entirely to Space. Preserve build progress/logs and
  image identity; cache misses are observable work, not justification for ignoring thresholds.
- Cancel **only the current Space selection** if MemAvailable drops below **12 GiB**, or CPU
  busy exceeds **85% for three consecutive samples**, or one-minute load exceeds **20 for
  three consecutive samples**. Stop immediately on an observed OOM attributable to the run.
  These response thresholds allow detection/cancellation lag; they are not hard aggregate caps.
- Cancellation must target the owned build request/test process and smoke projects only; never
  stop the shared daemon or ELSPETH/Simic. Confirm the build request has ended and any owned
  containers are down before releasing the slot. If cancellation cannot be verified, hold the
  slot and report the residual rather than declaring resource release. Retain the receipt as
  aborted, not passed; do not automatically retry to green.

Residual risk is explicit: a build or shared daemon can burst between samples, consume more than
a planning reservation, or take time to cancel. Reservations and monitoring are not enforced
daemon quotas. No additional privileged-builder decision is requested; only an ordinary slot
grant after readiness and fresh capacity remains. Defer build/live only if those checks fail or
the existing owner cannot implement the bounded monitoring/cancellation path within current scope.

### Candidate and phase separation

Candidate `8db6db9fc6749a7ea76126adcca65718af280874` and its preceding `04dff0be…` tree objects
remain available, with saved diffs preserved. Astra confirms the original Phase B fixes (Part A),
but the combined resource candidate is not live-ready. Opus's now-present candidate-4 confirmation
also identifies the Docker `ps` formatting defect; the owner is already handling it. Atomic
start reservation, accurate resource claims and other concrete guard defects require correction
and independent review before affected live gates. Do not duplicate that writer's work.

The original reviewed Phase B fix should be retained as a **separately identified atomic
checkpoint** by the existing owner, alongside the resource increment. Do not treat `04dff0be…`
as fully corrected: it precedes the replay/retry fix. This coordinator preserves the existing
trees/diffs and does not reconstruct or restage the owner's changes. Root/full readiness and
grant handling remain independent of live-harness repair. Slot remains **FREE / NOT GRANTED**;
no tests/builds or owner messages were launched for this assessment. Vehicle decisions remain
pending; no host, security, access, network or deployment change is authorised.
