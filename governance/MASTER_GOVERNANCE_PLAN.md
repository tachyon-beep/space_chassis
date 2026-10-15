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

## 18. Grant SPACE-20261011-P-01 — 2026-10-11 10:47 AEDT

**GRANTED by Emmy's delegated Space governance coordinator**, in chat
`01a12501-b067-7581-b5b2-3d4945441dc2`, following the parent coordinator's explicit instruction
to make this readiness decision. **Holder: existing Chassis Code owner**
`session_019mkPNN5J3Atit9tUA6zrNY` / `[8a7d49]`. State: **RESERVED FOR CHASSIS; awaiting browser
delivery/owner start receipt, not reported running**. No other Space selection may use the slot
until explicit release. Owner notification through Emmy's existing cloud browser route is needed;
this writer sends no owner message and launches no tests.

### Exact qualification and capacity

Increment **P**, tree **`af671d04908817e914668750b7cd4f6f74034bf4`**, has independent **LAND**
verdicts from `.scratch/phase-b-reviews/review-phase-b-P-{opus,astra}.md`, with no Critical or
Important findings. Optional Opus minors do not block. Both refer to this exact Git-object tree
and vehicle `f44399645fb2633e695a5d758cb5a41f43fb848c`, also verified in P's gitlink.
Saved P diff SHA256: `3b1ea8cf067a5fae54f6a9326c993b224db7279c30becf2aded1e2f119f1e8b4`;
P-versus-3 delta: `4c2684bb0b230d3ab3b7f99d99910fa2bacd0b3c0166a20e8a88f3bc7f243254`.

The adoption index currently matches **R** `dd16772e6d537db0baf52f9741b58b2fc17ef3c7`, with no
unstaged adoption paths. This grant is **not** permission to test that tree under P's identity.
The existing owner must preserve R and materialize P exactly using its already recorded safe
checkpoint procedure, retaining both increments and their evidence. The coordinator has not
changed either worktree or index.

Fresh host check **10:47:19–21 AEDT (23:47:19–21 UTC, 2026-10-10)**: 24 logical CPUs;
load **2.83/3.16/3.88**; **42,095 MiB available RAM (41.1 GiB)**; two-second sampled CPU busy
**13.8%**; recent memory pressure averages zero. Targeted process inspection found no Space
pytest/xdist/build driver, and Docker's Compose-project listing was empty. No matching ELSPETH
pytest driver appeared in this snapshot; this is not a declaration that ELSPETH work is complete
or permission to interrupt anything. All ELSPETH/Simic work remains protected.

### Authorised sequence and limits

1. P root gate: `python3 -m pytest tests -q -p no:cacheprovider -n 2`.
2. **Only after root exits 0**, P whole gate: `python3 -m pytest -q -p no:cacheprovider -n 2`.

Run one selection at a time, **maximum TWO pytest workers total across Space**, **nice -n 19**,
no GPU. Use the owner's requested per-run user scope `CPUQuota=200%`, `MemoryMax=8G`, covering
the driver and its descendants. Record the actual scope and enforcement readback; if unavailable,
hold and report rather than silently drop the limit. No persistent system policy change is
authorised. The 30–40 minute full-suite estimate is allowed validation time, not a 30-minute cutoff.

Before each start, verify exact P working/index tree and vehicle identity, no competing Space
driver, MemAvailable >=20 GiB, load1 <12 and sampled CPU busy <75%. Refresh rather than rely on
this snapshot if browser delivery is delayed. Keep the slot reserved between these two selections;
do not use it for implementation, R tests, builds or live tests. Monitor the owned selection and
host using section 17's five-second samples and abort thresholds (available RAM <12 GiB;
CPU busy >85% or load1 >20 for three samples). Never terminate unrelated jobs.

Record each command, start/end, candidate before/after, result/count/skips, actual limits and
session-unique evidence paths. On root failure, abort, candidate drift or a capacity problem,
do not start full; preserve evidence and report. No automatic retry or retry-until-green.
After full completes (pass or fail), or after an earlier stop, verify the owned test process and
children have ended and send the release/result receipt through Emmy/browser; the coordinator
then marks the slot FREE. Until that receipt, the reservation persists. No automatic handoff
to Vehicle or R, commit, merge, publication or required-test waiver is part of this grant.

**R/live separation:** current R's Astra review still finds inconsistent lock identity across
session environments and untracked/orphanable containment sweeps. Those remain with the existing
owner; root/full P qualification is not blocked by them. Any revised R needs its own exact review
and subsequent slot decision. Ordinary monitored serial builds remain possible later under
section 17, with no hard aggregate-cap claim and no privileged builder. No build/live grant now.

## 19. SPACE-20261011-P-01 completed and released — 2026-10-11 11:35 AEDT

**Current shared Space slot: FREE / RELEASED.** This supersedes section 18's reservation,
on the existing Chassis owner's explicit release and verified cleanup, not merely on absent
processes or a terminal log. Holder `session_019mkPNN5J3Atit9tUA6zrNY` / `[8a7d49]` wrote
`.scratch/phase-b-gates-P-019mkP/RELEASE-RECEIPT.md`: “The chassis releases grant
SPACE-20261011-P-01's slot.” Receipt SHA256:
`e060944add69c9a1afc02c032c71bc100192a331f14ba924729b7ec76e5795dd`.

| Selection | Start / terminal time (2026-10-11 AEDT) | Owner-reported counts / terminal exit |
|---|---|---|
| P root | 10:51:21 / 10:51:55 | 592 passed, no skips or failures; rc 0 |
| P full | 10:52:10 / 11:23:31 | 1940 passed, 1 failed; rc 1 |

Both selections recorded exact tree **`af671d04908817e914668750b7cd4f6f74034bf4`** and vehicle
**`f44399645fb2633e695a5d758cb5a41f43fb848c`**, clean before and after. Each used two pytest
workers, nice 19, with scope readback `cpu.max=200000 100000`, `memory.max=8589934592`.
The terminal receipts and logs remain alongside the release receipt. Full receipt SHA256:
`36188c1f50e4689f8b0eca19a90ae45e94e8e81810cd1294ca69976ae01f931e`.

The failed test was vehicle-owned
`test_a_run_ending_cleanly_checkpoints_its_last_completed_cycle_and_an_interrupt_mid_cycle_does_not`
in `docs/deep_research/vehicle/tests/test_vehicle_config.py`: its helper did not exit within
120 seconds after SIGINT. **The full gate remains failed and does not qualify P.** The owner
attributes the timeout to the gate driver's background shell launch inheriting ignored SIGINT,
and records signal-disposition microchecks. This coordinator has not independently reproduced
that diagnosis. A corrected driver is preparation only; no retry has been granted here.

Both terminal receipts report zero remaining scope processes, and the owner explicitly confirms
no run pytest, console or helper remains. Independent read-only host inspection at approximately
11:33–11:34 AEDT found both `space-chassis-p-root-1791676279.scope` and
`space-chassis-p-full-1791676328.scope` absent and no matching Space pytest/execnet/interruptible
helper processes. This supports the owner's release. No unrelated process was stopped.

The owner reports P remains materialised, R tree `dd16772e6d537db0baf52f9741b58b2fc17ef3c7`
remains in Git objects, and R2 work remains in `.scratch/phase-b-increment-R2-wip/`.
Only these coordinator-owned reservation records were updated; implementation, candidate trees
and staging were preserved. There is **no new selection, retry, R/build/live grant, automatic
handoff, commit or merge authorisation**. Further gate work needs a separate readiness/capacity
decision and grant. Vehicle product decisions remain pending.

## 20. SIGINT diagnosis and diagnostic grant SPACE-20261011-P-DIAG-01 — 2026-10-11 11:39 AEDT

Emmy authorises bounded diagnostic continuation by the **existing Chassis owner only**,
`session_019mkPNN5J3Atit9tUA6zrNY` / `[8a7d49]`. This coordinator issues the narrow grant below;
**slot RESERVED FOR CHASSIS DIAGNOSTICS, awaiting parent browser delivery, not reported running**.
The prior grant remains released and its failed full result remains unchanged. No broad rerun
is granted yet. Parent Emmy owns browser relay; this writer sends no owner message.

### Independent diagnosis and driver review

Read-only inspection found the unchanged test's real SIGINT followed by
`communicate(timeout=120)` at vehicle `tests/test_vehicle_config.py:28491–28492`; its helper
sleeps for 120 seconds at the selected interrupt point. The original failure occurred there.
Original `gate.sh` backgrounds the scoped command. Current `gate-v2.sh:78–80` explicitly resets
SIGINT to `SIG_DFL` before exec; this is stronger than merely moving the command to foreground.

Independent harmless controls through the existing user systemd bus, each with 2 CPU/8 GiB
limits and nice 19, produced:

| Launch path | Python SIGINT disposition | Result / cleanup |
|---|---|---|
| Original background-shell semantics | `SIG_IGN` (`1`) | rc 0; scope absent afterward |
| Foreground control | `default_int_handler` | rc 0; scope absent afterward |
| v2 explicit reset, even with background parent | `default_int_handler` | rc 0; scope absent afterward |

The first control attempt could not connect because this coordinator shell lacked the user-bus
environment; it launched no scope. The successful controls supplied the existing
`/run/user/1000/bus` address locally, without changing host/session settings. **The signal
mechanism is independently confirmed; causation of the test failure still needs the paired
unchanged-test diagnostic.** No pytest was executed by this coordinator or its reviewer.

Driver hashes reviewed by this coordinator and the independent read-only reviewer:

- `gate.sh`: `768efdda060e733e8756a0c67b775e1b10d4a93e02900df8ef81b98ae8d12c80`.
- `gate-v2.sh`: `b924a9a9829fdeaab6120cc53cce0899d56bad0b1af9cb6e5e693ab76b6a679f`.

**Broad-run verdict: HOLD.** v2 corrects signal restoration but retains supervision defects:

1. Lines 53–57 log rather than enforce scope/cap readback. Monitoring can end on a failed
   query or watcher error; line 82 ignores watcher status. No verified-monitor startup handshake.
2. Lines 81–89 return pytest's status despite abort, failed post-run identity or residual
   processes. Failed cgroup reads can misleadingly become a zero process count.
3. Lines 68–69 do not verify stop success; neither driver has bounded cancellation/exit cleanup.
   A surviving scope descendant can keep the watcher wait unbounded.
4. Lines 58–61 omit attributable OOM checks and parts of section 17's required telemetry.
5. Lines 41–42 can miss repository-relative pytest commands and treat Docker query failure as
   no smoke projects. Reused selection names overwrite logs while appending other evidence.

The existing owner may correct only the scratch gate driver/supervision within this task.
Preserve the original drivers and every failed artifact. Submit the resulting exact driver hash
for independent review before any broad rerun. No product or test change is authorised.

### Narrow diagnostic selection and safeguards

At 11:38 AEDT the read-only host check found **41.4 GiB available**, load
**2.49/2.93/3.57**, sampled CPU busy **13.7%**, no matching Space pytest/execnet/helper/build
process, and no Compose projects. At 11:39 the adoption index matched P exactly, with no
tracked difference or untracked non-ignored paths, and the vehicle was clean at the pinned SHA.
Refresh capacity/identity and process/cgroup admission **before each arm**; this is not a stale
capacity waiver. Preserve P and R/R2 evidence.

Exact P: `af671d04908817e914668750b7cd4f6f74034bf4`.
Exact vehicle: `f44399645fb2633e695a5d758cb5a41f43fb848c`.
Unchanged vehicle test file SHA256:
`3b917de30861c432c467d92d6a75b1faf7b31cd0e62626dfde095997110c4a53`.

Only this node is authorised, once per arm, using the same `-q -p no:cacheprovider -n 2`
arguments from the adoption root:

`docs/deep_research/vehicle/tests/test_vehicle_config.py::test_a_run_ending_cleanly_checkpoints_its_last_completed_cycle_and_an_interrupt_mid_cycle_does_not`

1. Reproduce with the original driver's background/SIGINT inheritance path.
2. **Only if arm 1 reproduces the same SIGINT timeout and its owned processes are gone**, run
   the same unchanged node with corrected SIGINT restoration. Unexpected results stop the
   comparison for reporting; no repeated attempts to obtain the expected pattern.

Use session-unique evidence paths outside the candidate, preserving both original scripts/logs.
Keep worker topology and every product/test assertion and timeout identical. Record inherited
signal disposition under each launch path (including the existing systemd boundary), exact
driver/wrapper hashes, test-file hash before/after, commands, start/end, pytest exit/counts,
scope result and cleanup. Observation/control probes must not install a test/helper signal
handler or otherwise change the behaviour under test.

The **existing owner supplies independent supervision** of these two short diagnostics so the
reviewed drivers' gaps cannot silently invalidate safety or result reporting. Require verified
scope caps and a functioning monitor before allowing test execution; hold/abort on missing
readback or monitoring failure. At most **two pytest workers total across Space**, nice 19,
per-run **CPUQuota=200%, MemoryMax=8G**, no GPU, no overlap. Start thresholds remain available
RAM >=20 GiB, load1 <12, CPU busy <75%. Sample every five seconds; abort the owned selection on
available RAM <12 GiB, CPU busy >85% or load1 >20 for three samples, or attributable OOM.
Use a ten-minute outer safety deadline per arm, distinct from and without modifying the test's
120-second timeout. Deadline/monitor/cleanup failures are diagnostic aborts, never expected
test failures or passes. No shared daemon or unrelated process may be stopped.

Keep raw pytest status separate from supervisory status; candidate drift, failed observation,
abort or unverified cleanup prevents a successful gate claim. Cleanup must cover driver,
workers, helpers and monitor, be bounded, and verify the owned scope and descendants ended.
An unreadable or unknown scope is not evidence of zero processes. Hold the reservation if
cleanup is uncertain; never start the second arm until the first is verified ended.

After both arms, or an earlier stop, send an explicit result/cleanup/**release** receipt via
the parent browser route. The reservation persists until that receipt is verified. If the
unchanged test fails under the old path and passes under corrected restoration, and the
corrected broad driver passes independent review, the coordinator may make a **separate fresh
P full-rerun grant** under Emmy's delegation. This diagnostic is not full qualification or
automatic permission to rerun. No R/build/live run, new writer, host/security-setting change,
commit, merge or required-test waiver is authorised.

## 21. DIAG-01 pre-test stop, verified release and bounded correction review — 2026-10-11 11:54 AEDT

**Current slot: FREE / RELEASED. No renewed diagnostic or broad gate is granted.** Parent Emmy
reported the existing owner's early stop and authorised this bounded verification/review without
a new user decision. The explicit release is
`.scratch/phase-b-diag-P-019mkP/RECEIPT-arm1-stop.md`, SHA256
`ccbdb7ba3d8cc6141fc3416fa412015268595390a0ec030dad811731afa06427`.
It states: “The chassis releases the SPACE-20261011-P-DIAG-01 reservation.”

The original supervisor admitted the arm at **11:45:07 AEDT**, then queried the bare unit name,
which addressed a nonexistent `.service` rather than the live `.scope`. It never wrote the
go-file. Its terminal receipt at **11:45:57 AEDT** records `supervision=ABORTED`, `ran=false`,
`pytest_rc=null`, no outcomes, and cleanup not yet verified. The later owner release receipt
records the launcher ending after its go-wait and subsequent cleanup. These are distinct events:
the original failed supervisor receipt is preserved, not rewritten into successful cleanup.
Neither test arm ran; this is **not a pytest attempt or result**. The original full failure also
remains unchanged. The launcher recorded inherited SIGINT ignored without modifying arm 1.

Independent host inspection at approximately **11:53 AEDT** confirms
`space-chassis-pdiag-arm1-1791679505.scope` is `LoadState=not-found`, `ActiveState=inactive`,
with empty ControlGroup and absent cgroup directory. No matching launcher, diagnostic driver,
pytest, worker or helper was found, and the active Space scope and Compose-project lists were
empty with successful queries. The go-file and arm 2 directory are absent. Adoption index and
tracked files still match exact P `af671d04908817e914668750b7cd4f6f74034bf4`; vehicle remains
clean at `f44399645fb2633e695a5d758cb5a41f43fb848c`. Test-file SHA256 remains
`3b917de30861c432c467d92d6a75b1faf7b31cd0e62626dfde095997110c4a53`.
Capacity was **41.3 GiB available**, CPU busy **13.6%**, load **2.86/2.66/2.96**.
Capacity is sufficient; supervision correctness is the remaining blocker.

### Exact correction reviewed, but renewal held

Preserved as-run supervisor `diag-r1-as-run.py` SHA256:
`02d8ca4929202014a6c042ee0741c7a8169dc03c8a549f8d05d317a51e16e520`.
Corrected, unrun `diag.py` SHA256:
`4a8d2d45ad40aae64a4b56474b815b45c64657030217aaef7d1dc62a0e3d5ced`.
Unchanged `launch.py` SHA256:
`91a813dc8563ce50489e5619e32a23f9f8dfc468571bc1bedfbc0ef66b2c0ccd`.

The diff correctly uses `<unit>.scope` for show, stop and kill; its end check no longer treats
an unknown ActiveState as ended, and explicitly recognises a collected, not-found scope.
The launcher keeps the causal arm difference limited to restoring SIGINT. However, this
coordinator and the independent read-only reviewer find **two concrete remaining blockers**:

1. **P1 — Exceptions skip cleanup.** `diag.py:382` can raise when a process exits between the
   cgroup listing and `/proc` reads. There is no post-launch `finally` guaranteeing cleanup.
   A stop-command timeout at line 409 likewise bypasses escalation. The existing owner should
   tolerate vanished process samples and ensure bounded owned-scope cleanup/escalation runs
   on post-launch errors, including failed/timed-out stop commands.
2. **P1 — Monitor errors are missed at admission/completion boundaries.** Lines 364–375 release
   the go-file after any first heartbeat, even if that sample has an abort or inactive scope.
   After the driver exits, monitor errors arriving before/during `watcher.join` are not merged
   into the final supervision verdict. Require a healthy active first sample and no pending
   abort before release; merge final monitor failures after joining before determining result.

Isolated in-memory control-flow checks (fake processes, no driver or pytest execution) confirmed
that a preexisting first-sample abort still writes the go-file, and a disappearing-process error
escapes the loop without reaching subsequent cleanup. The final-monitor-result issue is a
static finding. These are bounded corrections to the existing scratch supervisor, not new
framework work. The existing owner retains the pen; no product or test edits are authorised.

The fixed script currently accepts only `arm1`/`arm2`, and `arm1/` already exists. A **fresh
evidence parent with byte-identical reviewed scripts** avoids overwriting it without changing
arm semantics; do not merely pass unsupported `arm1b` or reuse/delete old evidence. Return
the minimally corrected supervisor/hash for bounded review, then a fresh diagnostic grant can
be considered with renewed capacity. All section 20 identity, two-arm, timeout, resource,
monitoring and explicit cleanup/release conditions remain requirements. No new writer, owner
message, test launch, broad rerun, R/build/live grant or host/security change occurred here.

## 22. Bounded supervisor recheck — 2026-10-11 12:02 AEDT

**Slot remains FREE / RELEASED; diagnostic renewal remains held on incomplete cleanup fixes.**
Reviewed `.scratch/phase-b-diag-P-019mkP-r2/diag.py`, SHA256
`d90fb3def47cc88255e96aed06d76e5963ec7540d72b93f0a3ff3416bb231697`, against the preserved
`4a8d2d45…` supervisor and section 21's two blockers. The independent read-only reviewer agrees
with this bounded verdict. No new framework, product/test edit or writer is requested.

**Fixed:** `live_infos` tolerates disappearing process entries; first-sample checks now reject
reported aborts, inactive scope and an ended watcher; final monitor failures are merged after
joining. State-query timeouts are represented as errors. Stop timeouts no longer immediately
escape the stop call, and escalation works when a subsequent state query positively says active.

**Remaining parts of the existing cleanup blocker:**

1. At **line 430**, the post-launch exception handler calls fallible `note()` before cleanup.
   A broken stdout pipe or failed receipt write can cause the original failure and then fail
   again while reporting it, skipping all owned-scope cleanup. Make exception reporting
   best-effort and place cleanup on an unconditional path, such as `finally`.
2. At **line 447**, escalation still requires a positively observed `active` state. If stop
   times out/fails and the following state query also fails, SIGKILL is skipped even though the
   known owned scope has not been shown to end. Attempt bounded escalation against that exact
   owned scope unless termination is positively established. If control remains unavailable,
   retain cleanup-unverified and hold the reservation; do not equate killing the shell with
   ending its descendants.

Isolated in-memory controls using the actual exception-handler and cleanup branch confirmed
both paths: reporting failure skipped the subsequent cleanup marker; stop timeout followed by
state-query error attempted only stop, never kill. These controls used fake I/O/processes,
launched no real scope or pytest and wrote no files. Syntax compiled in memory successfully.
The owner's claimed Ruff pass was **not reproduced under the repository's configuration**:
`uvx --offline ruff check --no-cache` on the two explicit scripts reports C402 at lines 76/90
and B905 at line 334. These lint findings are not additional diagnostic-renewal blockers;
avoid unrelated style expansion. No automatic fixes were applied.

Preservation checks: launcher remains byte-identical at
`91a813dc8563ce50489e5619e32a23f9f8dfc468571bc1bedfbc0ef66b2c0ccd`; old supervisor and release
hashes still match section 21, and the original failed full log remains
`1e46921be8a0131e0dddf01d38a8f87881ad67c36e039d74369a92dae16d766c`. The new evidence parent
contains only scripts and a diff, no arm directory/result. Existing arm 1 receipt SHA256:
`60c20e6313a5f31351073f689c132ad7de1563f23c1152d8340b7ca65176a4fd`.
P index/tracked files, pinned clean vehicle and unchanged test-file hash still match section 20.

Fresh host inspection at approximately **12:01 AEDT**: no Space scopes, no matching test,
launcher, diagnostic or build process, no Compose project; successful listing queries.
Available RAM **41.4 GiB**, sampled CPU busy **13.6%**, load **2.69/2.69/2.84**. Capacity is not
the blocker. No test or scope was launched by this review, and no owner/browser message was
sent. Parent browser relay should request only these two remaining cleanup corrections and a
new exact hash for bounded recheck. No renewed diagnostic, broad, R/build/live or retry grant
has been issued. No new user decision is required for these already-authorised corrections.

## 23. Renewed diagnostic grant SPACE-20261011-P-DIAG-02 — 2026-10-11 12:08 AEDT

**GRANTED under Emmy's delegated authority to existing Chassis owner**
`session_019mkPNN5J3Atit9tUA6zrNY` / `[8a7d49]`. **Current slot: RESERVED FOR CHASSIS
DIAGNOSTICS; awaiting parent browser delivery, not reported running.** This replaces the
section 22 hold for the narrow two-arm diagnostic only. DIAG-01 remains released, with zero
pytest attempts; its supervisor abort and the original failed full gate remain preserved.
No broad rerun, R/build/live selection, product/test edit, new writer or host/security change.

### Exact repair and independent evidence

Reviewed supervisor `.scratch/phase-b-diag-P-019mkP-r2/diag.py`, SHA256
**`2ead42bee98575b0d44b734c13aaf082dc7323ca70414b9b4c5a1b4ba6e1d94e`**.
Previous supervisor is preserved as `diag-d90fb3de.py` at the exact section 22 hash.
Launcher `launch.py` is unchanged, SHA256
`91a813dc8563ce50489e5619e32a23f9f8dfc468571bc1bedfbc0ef66b2c0ccd`.

Both remaining cleanup blockers are **fixed**: `record_failure()` makes reporting best-effort
so it cannot bypass subsequent cleanup; `terminate_scope()` attempts bounded stop and owned
SIGKILL unless termination is positively established, including when state queries fail.
Cleanup acceptance additionally requires its termination result. Earlier process-sampling and
monitor-boundary fixes remain in place. This coordinator and the independent read-only reviewer
find no remaining blocker within this bounded recheck.

The coordinator inspected `controls.py`: it extracts the two functions from the actual parsed
supervisor, uses fake process/control/clock/I/O functions, and checks their integration in the
module. Running those isolated controls against the exact hash above returned **20 PASS,
0 failures, rc 0**, byte-for-byte matching `controls-2ead42be.out`. In-memory syntax compilation
also passed. No actual scope, launcher or pytest was executed by this validation. The fake
clock's two 15-second waits do not establish total real cleanup wall time: real bounded
systemctl calls have their own timeouts. Actual run supervision/cleanup still needs receipts.

At **12:08:14 AEDT**, successful host queries found no Space scopes, no matching Space
test/launcher/diagnostic/build process and no Compose projects. Available RAM **41.4 GiB**,
sampled CPU busy **13.6%**, load **2.39/2.50/2.71**. Exact P index/tracked files are unchanged,
with no untracked non-ignored paths, and vehicle is clean at the pinned SHA. The new evidence
parent has no arm directories. Old arm 1 receipt, explicit release and original full log hashes
still match the preceding records. Staging was preserved.

### Authorised pair and release conditions

Use only the reviewed supervisor/launcher above, with fresh admission before each arm, on:

- P tree `af671d04908817e914668750b7cd4f6f74034bf4`.
- Vehicle `f44399645fb2633e695a5d758cb5a41f43fb848c`.
- Test file SHA256 `3b917de30861c432c467d92d6a75b1faf7b31cd0e62626dfde095997110c4a53`.
- Node `docs/deep_research/vehicle/tests/test_vehicle_config.py::test_a_run_ending_cleanly_checkpoints_its_last_completed_cycle_and_an_interrupt_mid_cycle_does_not`.

Run **once per arm**, sequentially, from the existing owner's session:

1. `nice -n 19 python3 .scratch/phase-b-diag-P-019mkP-r2/diag.py arm1`
2. Only after arm 1's unchanged test reproduces the original SIGINT/120-second timeout,
   supervision holds, exact identity remains and cleanup is verified:
   `nice -n 19 python3 .scratch/phase-b-diag-P-019mkP-r2/diag.py arm2`

The supervisor enters the adoption root and runs the same exact node with
`-q -p no:cacheprovider -n 2`. Arm 1 preserves inherited ignored SIGINT; arm 2 changes only
SIGINT restoration at the launcher. Preserve every assertion and timeout. Compare raw pytest
exit/count/failure site as well as supervision: the supervisor's exit 0 alone is not a test pass.
An unexpected arm-1 outcome, diagnostic abort, identity drift or uncertain cleanup stops the
pair; no repeated attempt is authorised. Arm 2 is expected to pass the same unchanged node,
but its actual outcome must be recorded without retry.

Maximum **two pytest workers total across Space**, **nice 19**, verified per-run scope
**CPUQuota=200%, MemoryMax=8G**, no GPU or overlap. Before each arm require available RAM
>=20 GiB, load1 <12, CPU busy <75%, no competing selection, exact identities and verified
limits/healthy monitoring before go. Sample every five seconds; abort only owned work if RAM
<12 GiB, busy >85% or load1 >20 for three samples, attributable OOM, observation failure or
the **600-second outer deadline**. The outer deadline does not modify any test timeout.

Use the fresh `r2/arm1` and `r2/arm2` evidence paths; never reuse old arm1 or invent arm1b.
The reviewed supervisor still contains the historical DIAG-01 label. **Do not change its hash
just for that label:** the owner's outer start/result/release receipt must explicitly identify
**DIAG-02**, this exact supervisor hash and these new arm paths. This section is the governing
renewal; embedded historical labels do not revive DIAG-01 or grant retries.

After both arms or any earlier stop, verify the owned scope, launcher, shell, workers, helper
and monitor have ended, then send an explicit result/cleanup/**release** receipt through the
parent browser route. Preserve both signal records, logs, identities and raw outcomes. Hold
the reservation if cleanup cannot be verified; an unreadable state is not proof of release.
Only this coordinator may mark the slot free after verifying that receipt. The original failed
full result remains unqualified. Any broad rerun requires a separate review/readiness decision
and fresh grant. Parent alone sends the browser message; no owner message or real test/scope
was launched by this coordinator.

## 24. DIAG-02 accepted and released; full-driver handoff pending — 2026-10-11 12:17 AEDT

**Current slot: FREE / RELEASED.** Existing owner `[8a7d49]` explicitly released DIAG-02 in
`.scratch/phase-b-diag-P-019mkP-r2/RECEIPT-DIAG-02.md`, SHA256
`19735575f8e548d78eb73d73bc3c2c580250b844b6526c8296c59f5bc68c97e8`.
The outer grant mapping/release log SHA256 is
`a97a5e37568cc1d19bb403c29d017e68c2425fa14b892c80856e8337fc284faa`.
Its explicit release is timestamped **12:14:01 AEDT**. This coordinator verified the underlying
arm receipts, raw logs, launcher records, monitoring and current host cleanup before marking
the reservation released. Neither the original full failure nor DIAG-01's pre-test abort is erased.

| Selection, exactly once | Released / terminal receipt (AEDT) | Raw pytest outcome | Supervision |
|---|---|---|---|
| arm 1, inherited ignored SIGINT | 12:10:58 / 12:13:08 | exit 1, one failed; same node, 120-second timeout at `interrupted_console`'s `communicate(timeout=120)` | held, no abort reasons; cleanup verified |
| arm 2, SIGINT restored | 12:13:23 / 12:13:33 | exit 0, one passed | held, no abort reasons; cleanup verified |

Both arms used exact supervisor `2ead42be…` and unchanged launcher `91a813dc…`. The launcher
records and observed pytest/worker/helper processes show SIGINT ignored throughout arm 1 and
not ignored in arm 2. All observed scoped processes were nice 19. Before/after identity receipts
match P `af671d04908817e914668750b7cd4f6f74034bf4`, vehicle
`f44399645fb2633e695a5d758cb5a41f43fb848c`, and unchanged test-file SHA256
`3b917de30861c432c467d92d6a75b1faf7b31cd0e62626dfde095997110c4a53`.
Scope readbacks were `cpu.max=200000 100000`, `memory.max=8589934592` before release.

Raw log hashes match their result receipts: arm 1
`abf5edc7875950b4e5a9de2baa13289e920ff826eb783739c993ef9bbc5bf51a`; arm 2
`0e0e01393285e70131d7f525375b9e0e3dab6d212f4b7bd06e6264b91c7d4cdf`.
Independent aggregation found 27/3 monitor samples, minimum available RAM 42,086/42,137 MiB,
maximum CPU busy 17.7/17.6%, maximum load1 2.61/2.82, and no observed OOM events or abort
threshold crossings. Arm 1 cleanup completed before arm 2 admission.

**Accepted causal finding:** restoring SIGINT at launch is sufficient to make this unchanged
test pass; preserving the original launch inheritance reproduces the original failure at the
same site. This establishes the gate-driver launch confound for that failure, with no product
or test change. It does **not** qualify the full P suite or exclude other failures in a new run.

Independent host check at **12:16:35 AEDT** found both
`space-chassis-pdiag-arm1-1791681055.scope` and
`space-chassis-pdiag-arm2-1791681200.scope` not-found/inactive with absent cgroups, no remaining
matching launcher/diagnostic/pytest/worker/helper process, no Space scopes and no Compose
projects. Available RAM **41.4 GiB**, sampled CPU busy **13.9%**, load **2.51/2.58/2.66**.
Current tracked/index P identity, clean pinned vehicle and test-file hash remain exact.

### Precise remaining full-rerun prerequisite

No minimally adapted corrected full-suite driver was found in the owner evidence directories
or scratch inventories inspected for this handoff. The full-capable
`.scratch/phase-b-gates-P-019mkP/gate-v2.sh` remains SHA256
`b924a9a9829fdeaab6120cc53cce0899d56bad0b1af9cb6e5e693ab76b6a679f`, unchanged from section 20's
rejected supervision. The accepted Python supervisor remains diagnostic-only: hardcoded node,
arm1/arm2 selection and a 600-second diagnostic deadline. Neither can be granted as the
corrected full-suite driver on the current evidence.

Parent browser relay should request the **existing owner's minimal full-suite adaptation** of
the accepted supervisor and unchanged SIGINT-restoring launcher, in fresh evidence paths.
Retain its admission, verified caps, monitoring, outcome/identity checks, bounded cleanup and
explicit release; select only `python3 -m pytest -q -p no:cacheprovider -n 2`, always restoring
SIGINT. Set a full-suite-appropriate outer safety deadline rather than retaining the diagnostic
ten-minute limit, and submit the exact path/hash plus minimal diff for review before launch.
No new framework or unrelated supervisor expansion is requested. **No root duplicate is
needed:** P/product/tests have not changed and the 592-pass root evidence remains valid.

The coordinator may grant P full only after that concrete driver review and refreshed capacity.
No full grant, real test/scope execution, owner/browser message, new writer, R/build/live run,
product/test edit or automatic retry occurred here. P/R and all failed evidence remain preserved.

## 25. P full-only grant SPACE-20261011-P-FULL-01 — 2026-10-11 12:23 AEDT

**GRANTED under Emmy's delegated authority to the existing Chassis owner**
`session_019mkPNN5J3Atit9tUA6zrNY` / `[8a7d49]`. **Current slot: RESERVED FOR CHASSIS P FULL;
awaiting parent browser delivery, not reported running.** This resolves section 24's concrete
driver prerequisite. DIAG-02 remains released and accepted. No root duplicate is required:
the original 592-pass root result is retained on the unchanged P tree.

### Exact accepted driver and validation

Driver: `.scratch/phase-b-full-P-019mkP/full.py`, SHA256
**`2557d326492e27e766dc13850aef68165eaad89119a475208a266de0c721a13f`**.
Minimal diff: `full.vs-diag-2ead42be.diff`, **101 lines**, SHA256
`f00ad993b1437f1de384639322af42889ff70b96a077e24f4a4f8318d0292445`.
Launcher: `.scratch/phase-b-full-P-019mkP/launch.py`, byte-identical to the accepted diagnostic
launcher, SHA256 `91a813dc8563ce50489e5619e32a23f9f8dfc468571bc1bedfbc0ef66b2c0ccd`.

The submitted diff matches a freshly generated comparison against accepted diagnostic
supervisor `2ead42be…`. All top-level function ASTs are identical. The adaptation selects only
the full-suite command, always restores SIGINT, records the supplied grant ID, uses a fresh
`full/` evidence directory and full-specific scope name, sets **OUTER_DEADLINE=5400 seconds**,
and records full-suite errors instead of diagnostic-only timeout fields. Accepted admission,
caps, monitoring, identity, result and cleanup behaviour is preserved. The independent
read-only reviewer also accepts this bounded adaptation with no remaining blocker.

The coordinator inspected and reran the existing isolated AST/fake controls against this exact
`full.py`: **20 PASS, 0 failures, rc 0**, matching `controls-full-2557d326.out` byte-for-byte.
In-memory syntax compilation passed. These controls launch no real scope or test. `full/`
does not yet exist; the driver's exclusive creation refuses evidence reuse. No actual scope,
launcher or pytest was executed by this coordinator.

At **12:23:07 AEDT**, successful host queries found no Space scopes or Compose projects and
no matching Space test/launcher/diagnostic/full/build process. Available RAM **41.3 GiB**,
sampled CPU busy **13.6%**, load **2.65/2.63/2.65**. Current index/tracked files equal P exactly,
with no untracked non-ignored paths; vehicle remains clean at the pinned SHA. Test file and
original failed full log hashes remain unchanged, as does the DIAG-02 explicit release receipt.

### One authorised full selection

From `/home/john/space_chassis`, existing owner runs **once**:

`nice -n 19 python3 .scratch/phase-b-full-P-019mkP/full.py SPACE-20261011-P-FULL-01`

The reviewed driver enters the existing adoption worktree and invokes exactly:
`python3 -m pytest -q -p no:cacheprovider -n 2`, with no node filter and SIGINT restored by the
unchanged launcher. It must use exact P **`af671d04908817e914668750b7cd4f6f74034bf4`**, vehicle
**`f44399645fb2633e695a5d758cb5a41f43fb848c`**, and unchanged vehicle test-file SHA256
`3b917de30861c432c467d92d6a75b1faf7b31cd0e62626dfde095997110c4a53`. No assertions, product
source or test timeout may change. Preserve P, R/R2 and every original failed artifact.

Refresh admission immediately before launch: exact identity, no competing Space selection,
available RAM >=20 GiB, load1 <12, sampled CPU busy <75%. At most **two pytest workers total
across Space**, **nice 19**, verified per-run scope **CPUQuota=200%, MemoryMax=8G**, no GPU or
overlap. Require correct scope readback and healthy monitoring before release. Sample every
five seconds. Abort only owned work on available RAM <12 GiB; CPU busy >85% or load1 >20 for
three consecutive samples; attributable OOM; failed supervision; or the **5,400-second
(90-minute) outer safety deadline**. This ceiling is accepted for the full run and changes no
test timeout; the previous 31-minute run is an estimate, not a cutoff. Protect unrelated work.

Use only fresh `.scratch/phase-b-full-P-019mkP/full/` evidence. Record actual start/end,
identities/hashes before/after, cap/signal readback, monitoring, raw pytest counts/skips/errors
and exit, and supervision status separately. **Supervisor exit 0 alone does not mean pytest
passed.** Failure, abort, drift or uncertain cleanup receives an accurate failed/aborted report;
no automatic retry or test waiver. The original full failure remains in the record.

At terminal completion, verify the owned scope, launcher, shell, pytest workers/helpers and
monitor have ended; send an explicit result/cleanup/**release** receipt through parent browser.
The slot remains reserved until this coordinator verifies that explicit receipt. Unreadable
state or a missing result is not release. There is **no root repeat, R/build/live grant,
automatic next selection, new writer, host/security-setting change, commit or merge authority**.
Parent alone relays the grant; this coordinator sends no owner/browser message.

## 26. P full gate passed and slot explicitly released — 2026-10-11 13:01 AEDT

**Current slot: FREE / RELEASED.** SPACE-20261011-P-FULL-01 completed successfully, and this
coordinator accepts the existing owner's explicit release after reconciling raw logs, terminal
receipts and independent host cleanup. Tests were released at **12:26:17 AEDT**; terminal result
and cleanup were recorded at **12:57:30 AEDT** (**31 minutes 13 seconds**). The owner's outer
release entry is **12:57:58 AEDT**, distinct from test completion.

**Raw pytest: exit 0, 1,941 passed, zero failures/errors/skips. Supervision: held, no abort or
failure reasons.** The raw log reaches 100% and independently counts exactly 1,941 passing
progress marks, matching the terminal result and owner receipt. The owner reports supervisor
exit 0. Actual command was `python3 -m pytest -q -p no:cacheprovider -n 2`, with no node filter.

Exact identities before/after, also checked against the current worktree:

- P tree `af671d04908817e914668750b7cd4f6f74034bf4`.
- Clean vehicle `f44399645fb2633e695a5d758cb5a41f43fb848c`.
- Driver `2557d326492e27e766dc13850aef68165eaad89119a475208a266de0c721a13f`.
- Unchanged launcher `91a813dc8563ce50489e5619e32a23f9f8dfc468571bc1bedfbc0ef66b2c0ccd`.
- Unchanged test-file hash `3b917de30861c432c467d92d6a75b1faf7b31cd0e62626dfde095997110c4a53`.

Caps read back as `cpu.max=200000 100000`, `memory.max=8589934592`; observed scope processes
were nice 19 with SIGINT not ignored. Independent aggregation of **374 monitor samples** found
minimum available RAM **41,217 MiB**, maximum CPU busy **27.3%**, maximum load1 **5.28**, scope
peak **3,164,946,432 bytes**, and no OOM events or abort-threshold crossings. The 5,400-second
outer deadline was not reached.

Explicit release: `.scratch/phase-b-full-P-019mkP/RECEIPT-P-FULL-01.md` states “the chassis
releases the SPACE-20261011-P-FULL-01 reservation.” Its SHA256 is
`4f03dc0e60896166d7e5dfd1c03c9f6bdce0661c94323d376762bd66e90e26f8`.
Outer receipt `P-FULL-01-outer-receipt.log` SHA256:
`f6cf654cf1b2af0219a4af0eeb3c0c7b5770b32d9712d37019d6a693b7e11c4c`.
Terminal `full/receipt.jsonl` SHA256:
`e319fe445e84163f193efc7808ece1fa2d63b30b09b9469ef6d6eb1628a23b10`.
Raw `full/pytest.log` SHA256:
`ea5741cf2c090550ca658090de3d2521e8c1f3e0483f376cb0e63ac64ba94e90`.

At **13:01:14 AEDT / 02:01:14 UTC**, independent host inspection confirmed
`space-chassis-pfull-1791681974.scope` is not-found/inactive, ControlGroup empty, cgroup absent,
and no active/loaded matching Space scope or remaining matching owned launcher/full-driver/
pytest/worker/helper process. The terminal cleanup receipt separately records the monitor
ended, shell exit 0, no helpers and verified scope termination. Explicit owner release and
cleanup both support the FREE state; neither elapsed time nor process absence alone was used.

**Bounded conclusion:** exact P now has the retained **592-pass root** evidence and this
**1,941-pass whole-suite** evidence. This grants no R qualification, build/live acceptance,
commit, merge, publication or automatic next selection. The original full failure hash and
DIAG-02 release hash remain unchanged as separate evidence; P/R and staging were preserved.
Vehicle issue 39 product decisions remain pending. No ELSPETH admission work was done; its
admission still waits for John's requested root-command output. Only coordinator-owned
reservation records were updated, with no owner/browser message or extra execution.

## 27. R2c root supervisor accepted; one root slot reserved — 2026-10-11 13:58 AEDT

**Current slot: RESERVED — `SPACE-20261011-R2C-ROOT-01`.** John directly authorised this
coordination task to review the R2c supervisor, reserve the shared slot, and have the existing
chassis owner run the root-only tests once on Nyx, capped at two CPUs and 8 GiB for ten minutes.
This is a grant to owner `session_019mkPNN5J3Atit9tUA6zrNY` / `[8a7d49]`; parent Emmy retains
the browser relay. No test has been launched by this coordinator. Delivery is still pending:
this session has no available browser surface or cross-task send tool.

### Reviewed identity and controls

- Candidate R2c tree: `148a31c4951e43c1cdafdf30c15b029dc7e104a8` in the existing adoption worktree.
- Clean vehicle: `f44399645fb2633e695a5d758cb5a41f43fb848c`.
- Supervisor `.scratch/phase-b-R2c-root-019mkP/root.py`, SHA256
  `6eac172448026b6f4fe604ba5aa205439d5099c533cf33a1976e08f0a4dfc6b9`.
- Unchanged launcher SHA256
  `91a813dc8563ce50489e5619e32a23f9f8dfc468571bc1bedfbc0ef66b2c0ccd`.
- Reviewed 76-line `root.vs-full-2557d326.diff`, SHA256
  `2de2204370c362b3c30899a65b9e7193c465cba07afb58f035938053ace8a933`, matches the actual GNU diff
  against accepted full supervisor `2557d326492e27e766dc13850aef68165eaad89119a475208a266de0c721a13f`.
- Vehicle test-file SHA256 remains
  `3b917de30861c432c467d92d6a75b1faf7b31cd0e62626dfde095997110c4a53`.

The adaptation changes the candidate, root selection, evidence/unit names and outer deadline to
600 seconds. Cleanup and failure-reporting controls are retained. Both Python files compile in
memory; the coordinator reran all 20 isolated fake-based controls, with zero failures and no
scope/test execution. Current index and tracked files match R2c exactly, with no untracked
non-ignored files, and the new `root/` evidence directory does not yet exist. The retained
identity-failure message still says P; the actual identity predicate correctly binds R2c.

At **13:57:45 AEDT / 02:57:45 UTC**, successful independent host queries found no Space scopes,
Compose projects or matching Space test/build/launcher processes. Available RAM **40.56 GiB**,
sampled CPU busy **13.4%**, load1 **2.80**. The main repository index remains unchanged at SHA256
`86487638e8c0ae03e2c8739565e25d819e157e95967f4c17c5d1fc7c7623ac2a`.

### One authorised root selection

After parent browser delivery and fresh admission, the existing owner runs once from
`/home/john/space_chassis`:

`nice -n 19 python3 .scratch/phase-b-R2c-root-019mkP/root.py SPACE-20261011-R2C-ROOT-01`

The reviewed driver runs exactly `python3 -m pytest tests -q -p no:cacheprovider -n 2` in
`.claude/worktrees/vehicle-adoption`. Require the exact identities above, no competing Space
selection, available RAM >=20 GiB, load1 <12 and sampled CPU busy <75% immediately before launch.
At most two pytest workers total across Space, nice 19, verified per-run scope CPUQuota=200%
and MemoryMax=8G, and restored SIGINT. Cap readback and a healthy monitoring sample precede test
release. The outer deadline is **600 seconds from test release**; bounded termination and cleanup
follow any abort. It changes no individual test timeout.

Sample every five seconds. Abort only owned work for available RAM <12 GiB, CPU busy >85% or
load1 >20 for three consecutive samples, attributable OOM, supervision failure or the deadline.
Protect unrelated work. Keep raw pytest exit/counts and supervision verdict separate; supervisor
exit zero alone is not a passing gate. Record identities before/after, cap/signal readback,
monitoring, raw output, actual timing and verified scope/process/monitor cleanup in fresh
`.scratch/phase-b-R2c-root-019mkP/root/` evidence. No retry on failure or abort.

Return an explicit result/cleanup/**release** receipt through parent browser. The slot remains
reserved until this coordinator verifies that receipt. A root pass advances only R2c root
qualification; full-suite qualification remains pending. There is no full/build/live grant,
automatic next selection, new writer, host/security-setting change, commit or merge authority.
P's accepted root/full evidence and all failed artifacts remain preserved. Vehicle issue 39
remains a separate pending product decision.

## 28. R2c root accepted and shared slot released — 2026-10-11 14:13 AEDT

**Current slot: FREE / RELEASED.** Parent Emmy relayed completion and explicit owner release
for `SPACE-20261011-R2C-ROOT-01`. This coordinator independently reconciled the raw log,
receipts, monitoring, current candidate and fresh host cleanup. R2c root qualification is
accepted: **617 passed, zero failures/errors/skips, pytest exit 0; supervision held with no
abort reasons.** Selection was exactly `python3 -m pytest tests -q -p no:cacheprovider -n 2`.
Independent raw-progress counting finds 617 passing marks and no other outcomes.

Tests were released at **03:08:38 UTC / 14:08:38 AEDT**, and terminal result plus verified
cleanup were recorded at **03:09:13 UTC / 14:09:13 AEDT**, 35 seconds later. Owner explicit
release is recorded at **03:10:34 UTC / 14:10:34 AEDT**, distinct from terminal completion.

Exact identities match before, after and current checkout:

- R2c tree `148a31c4951e43c1cdafdf30c15b029dc7e104a8`; tracked/index state exact, no untracked paths.
- Clean vehicle `f44399645fb2633e695a5d758cb5a41f43fb848c`.
- Supervisor `6eac172448026b6f4fe604ba5aa205439d5099c533cf33a1976e08f0a4dfc6b9`.
- Launcher `91a813dc8563ce50489e5619e32a23f9f8dfc468571bc1bedfbc0ef66b2c0ccd`.
- Vehicle test-file SHA256 `3b917de30861c432c467d92d6a75b1faf7b31cd0e62626dfde095997110c4a53`.

Caps read back before release as `cpu.max=200000 100000`, `memory.max=8589934592`.
Eight monitor samples independently aggregate to minimum available RAM **41,705 MiB**, maximum
CPU busy **22.2%**, maximum load1 **3.07**, and peak sampled scope memory **247,164,928 bytes**.
No OOM or abort threshold occurred. All observed scope processes had nice 19. The launcher
restored SIGINT; pytest/xdist did not ignore it. The two ignored-SIGINT samples belong to the
background shell/sleep fixtures deliberately created by the timed-out-group test.

The bounded scope stop returned zero and removed the remaining `sleep 30` from the unchanged
`tests/test_journal.py::test_a_stream_that_never_ends_times_out` fixture. The file is identical
between P and R2c. This retained test-hygiene observation does not invalidate the gate: owned
cleanup succeeded, and no fixture or product code was changed under this grant.

At **03:12:40 UTC / 14:12:40 AEDT**, independent successful host queries found
`space-chassis-r2c-root-1791688115.scope` not-found/inactive with empty ControlGroup, its cgroup
absent, no Space scopes or Compose projects, and no matching owned driver/launcher/pytest/
worker/helper processes or known remaining sleep PID. The terminal receipt also verifies
scope termination, ended monitor, shell exit zero and no helpers. Explicit release plus
verified cleanup supports FREE; process absence alone was not used as release.

Full SHA256 evidence identities under `.scratch/phase-b-R2c-root-019mkP/`:

| evidence | SHA256 |
|---|---|
| `RECEIPT-R2C-ROOT-01.md` (explicit release) | `ac0f8d103a0444dae342e63549bbee0b4337b8e27f72f0bf10b60087289de80e` |
| `R2C-ROOT-01-outer-receipt.log` | `92c709bd17f7d4c1d3125314eb2debc40ff21c02c4c0bdbde4a80789698cee77` |
| `root/receipt.jsonl` | `df6ab6d4f9b7457bc1c24ad074ea170df60f5222310d3db1947a93b205091352` |
| `root/pytest.log` | `4ee78bc0044854e43789c0ed631bda8633d6095612b8ea3e7669f6a345970670` |
| `root/monitor.jsonl` | `d3b0c63695bca8331aaf7bbc210c28e75bc3aeb4e710187151766ee1e1bb4bce` |
| `root/launcher.json` | `c75c84d4fb22f8e01f97257f682cc61f30b39aa8020f32e4083c3920ce381127` |
| `root.supervisor.out` | `edd1e841ffd8d8117ef186114dabc1519c967d2eb36011ee748eced2285f5c2d` |

**Board effect:** R2c moves from root pending to **root passed / full pending**. P's separate
592-root/1,941-full evidence remains preserved. R2c full/build/live gates remain ungranted;
Phase B is not complete and vehicle issue 39 remains a separate product decision. Recommended
next step is preparation and review of an exact-R2c full-suite proposal for a separate grant.
This closure reserves or launches nothing further and permits no retry, commit or merge.
Only coordinator records changed; the main index SHA256 remains
`86487638e8c0ae03e2c8739565e25d819e157e95967f4c17c5d1fc7c7623ac2a`.

## 29. Option B allocation preparation and tier-1 brief drafting — 2026-10-11 21:53 AEDT

John, through Emmy, directs this coordinator to use the existing shared-slot allocation authority
for the existing Vehicle owner's Option B workflow, subject to exact selections/identity, bounded
run count/deadlines, justified CPU/RAM enforcement, abort/cleanup evidence, independent implementation
review and fresh capacity/ownership checks before any grant. Option B implementation is already
authorised; no renewed implementation permission is required. **No allocation or run is granted here.**

Scope-specific reconciliation: P full and R2c root were completed and explicitly released (§§26,28).
John separately granted tier-1 bounded/full tests at 08:09:55 UTC in the Vehicle transcript; the
Vehicle owner recorded release at 09:11 UTC. Those grants do not allocate Option B. John approved
tier-1 publication/merge on green CI and Option B implementation after merge at 09:14:04 UTC
(Vehicle transcript `a728e992-9471-46ab-9efe-ce550d7ece5f`, line 9378). PR #43 merged at 10:08:46 UTC,
`f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f`. Earlier statements that the tier choice is pending
are historical. Issue 42 preference persistence remains a separate undecided package.

At **10:52:31 UTC / 21:52:31 AEDT**, read-only host inspection found **42.43 GiB available RAM**,
**15.3% sampled CPU busy**, load1 **4.13**, no matching Space pytest/build/launcher processes,
no listed Space or named Nyx CI/release scopes and no Compose projects. This is preparation evidence,
not proof that all ELSPETH work is idle, and must be refreshed immediately before a grant/launch.
ELSPETH keeps priority; Sultai GPU reservation is untouched; Space gets no GPU, one selection,
maximum two workers total and nice 19. Historical R2c CPU/RAM caps are not an Option B allocation.

Vehicle's existing `b-39-ca87a9` worktree is based on `f75420c`, with two modified files and no
frozen candidate receipt. Observed `git diff --binary HEAD --` SHA256 at this check:
`b5981141b99d47c92850970d277f9f591aa36727785544778ab2deed96bf64ea`.
This observation does not freeze the owner's work. Only design reviews B1–B5 were located;
the exact implementation needs independent review before tests under this direction.

**Route blocker:** no browser surfaces (`apps=[]`, `browsers=[]`) and no cross-task send tool
are available in this coordinator session. Emmy's existing browser route must deliver the two
prepared requests to Vehicle [610587] and Chassis [ad1acf]. No owner message has been delivered here.
Vehicle is to return a frozen candidate/review and concrete bounded run/supervisor proposal.
Chassis is to draft the finished tier-1 brief replacement now, including the conflicting next-cycle
promise at `brief/PROTOCOL.md:59–60`, and return exact target text for John's final-text approval.
Drafting is already authorised; adopting/publishing final brief text waits for that approval
under the design spec §6. Existing owner work is not interrupted and no substitute writer is created.

## 30. Option B candidate-3 verified; C0/S1 supervisor review held — 2026-10-11 22:23 AEDT

**No allocation/grant.** Reviewed the existing owner's `B-sel1` proposal without executing or
importing it, running controls, collecting tests, or launching a scope. C0 and S1 remain separate
unallocated selections. No duplicate owner instructions were sent; findings return through Emmy.

Verified proposal SHA256 `8d77dbbf9eefceee0deb45909991122eab1739ea81e5d3c4c85497ba72d97247`;
supervisor `206db6c9471e33233bb18315f65077b5f3175e02e2372ae5ccb963cc21fd0576`;
launcher `b600a314f18722841a60c32aed0927cbff8aa98bc7e1145972393465b9255525`.
Both spec hashes match the proposal. Current HEAD is `f75420c`; current diff matches candidate-3
`0a00336feb10dcd5c8839893cabafbdc5cbea20474f918d76dc1e0eca3f2d01d`. All 92 tracked blobs match
stored tree `b447955f60c528e78d05c324ecc4c4317128d1a1`, with no untracked non-ignored paths.
Read the complete implementation review chain 0–3. Final source-only delta review approves;
receipt SHA256 `41da8155ed3f5b16bb4d378fe6c0e896f915f8505d84bd426670b29a478fbe07`.
Static AST inspection confirms S1's 25 unique named functions, each defined once without decorators.
No C0/S1 evidence directory exists. Implementation review is accepted as submitted source evidence,
not runtime qualification.

Supervisor blockers (all line references in `B-sel1/supervise.py` unless stated):

- P1: no exception-safe cleanup after launch (137 onwards); reporting itself can prevent cleanup (212).
- P1: failed status queries count as ended; no empty/absent-cgroup or owned-process proof before release
  (225–249). Scope ownership is not positively established before later stop/kill operations.
- P2: admission sees only argv-matched pytest and two same-unit states (59–71,114–124), missing relative
  argv/cwd, other Space drivers/scopes/build/live and failed/deactivating lookups; pre-GO sample is logged
  rather than checked against admission health (158–165).
- P2: systemctl/identity subprocesses have no timeout; launcher GO wait is infinite; the only deadline
  starts after GO and cleanup commands/waits can remain unbounded (98–102,142,166,213–225; launch.sh:9).
- P2: shell `trap - INT` does not establish restoration from inherited-ignore; use explicit signal
  restoration and disposition evidence (launch.sh:6). Terminal OOM may be missed when the controller
  exits before the next sample (173–186). Candidate identity is not checked after execution (99–106).
- Validation gap: the sole 12-second success control exercises none of the abort/reporting/lookup/
  deadline/cleanup failures. Require deterministic failure-injection controls against corrected code
  before allocating the separate host smoke control; success alone cannot qualify supervision.

The explicit proposed 2 CPU/6 GiB/no-swap ceiling is distinct from R2c's limits, but 6 GiB is a declared
ceiling, not a measured peak. Explain the changed 16 GiB admission/10 GiB abort floors and absence of
CPU-busy admission/abort checks against ELSPETH priority before grant. Refresh capacity and slot
ownership only after corrected supervisor evidence is ready; the earlier capacity sample is not a
launch admission. Preserve one Space selection, two workers total, nice 19 and no GPU.
Chassis owns the final brief draft and Vehicle its contract wording; no final brief approval exists.
Issue 42 remains separate. No source/spec/owner-report changes were made by this coordinator.

## 31. B-sel1/v5 reviewed; K allocation blocked by Nyx process visibility — 2026-10-11 23:11 AEDT

**No K allocation, reservation or execution.** The current request is Vehicle's 20 serial
failure-injection controls only, with no pytest. The released R2c ROOT-01 allocation is historical;
no stale grant or owner instruction was sent, through a browser or any other route. This session's
browser inventory remains empty and findings return to Emmy for the existing owner relay.

### Exact source and review coverage

Independently verified v5 `PROPOSAL.md` SHA256
`3c10398f63ba6f9bfb3fe01e3d833b57aa015fd69b0a59734aa27f5d81c5af6a`, and `SHA256SUMS`
`e66c1223a9147afa56052389a705bf900ee90836c06226e47749890800774c31`, including all 26 entries.
Candidate HEAD remains `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f`; diff SHA256 remains
`0a00336feb10dcd5c8839893cabafbdc5cbea20474f918d76dc1e0eca3f2d01d`. All 92 tracked blobs match
tree `b447955f60c528e78d05c324ecc4c4317128d1a1`, with no untracked non-ignored files. None of the
20 control evidence directories or the controls summary exists.

Read the complete v2, v3, v4 and v5 supervisor reviews, the current supervisor, launcher, recorder,
harness, plan and all control specs, and compared the v4-to-v5 source changes. The v2 baseline
review was followed by explicit disposition of its eight findings in v3/v4; v5 closes the four
reported v4 P2s (harness unknown discovery/exception handling, final recorder result, deadline
checks and K10 injection). This supports the stated source-review termination rule, not runtime
qualification or a blanket allocation clearance.

The three reported v5 P3s are dispositioned as follows:

- Terminal `show` may finish beyond the terminal-wait budget before being accepted
  (`supervise.py:495-505`). Accept as a post-control timing residual for K: the payload is already
  terminal and this does not reopen its systemd runtime limit. Do not claim an exact terminal-wait
  bound from that loop.
- Exception recovery may say units "were stopped" without proving successful discovery or stop
  (`run_controls.py:140-150`). That text is never release evidence. The suite fails and ends;
  explicit owner release plus independently verified unit/cgroup/process/decoy cleanup is required.
- The dropped `release_contains` assertion has no consumer in the supplied plan. No K control
  depends on it. The proposal's K02 claim that the receipt says `exit=3` is inaccurate: current
  receipts attest cleanup only; K02 checks actual return code, receipt presence and missing summary.

### Concrete host admission blocker

Read-only host checks at **12:09:34 UTC / 23:09:34 AEDT** found 24 logical CPUs, **31.04 GiB
MemAvailable**, **17.9% CPU busy** over two seconds, load1 **3.95**, and no listed Space user units
or Space-named containers. Two unrelated containers remain untouched. This is capacity evidence,
not a launch admission or proof of exclusive ownership.

The same checks, repeated with only access outcomes printed, found uid-1000 processes whose
`cmdline` is readable but `cwd`, `exe` and `environ` return **EACCES (13)**: PID 1594 (user systemd),
1623 (sd-pam), and seven SSH processes. This is a current host fact, not a simulated failure.
`supervise.py:199-209` reads cwd/exe for every same-user process before classifying it; any such
non-ancestor process causes admission refusal. Its cleanup token scan (`252-264`) and the harness
scan (`run_controls.py:51-68`) also treat these unreadable environments as unknown. Thus the exact
package cannot complete a valid K00 on this host; even a pre-launch refusal fails independent
no-token-process proof. Capacity alone cannot make the submitted admission/cleanup predicates pass.
The existing independent reviewer `/root/review_governance` confirmed this source mapping and
returned BLOCK for K allocation, after reading the full review chain and current source.

Return to the existing Vehicle owner for a narrowly scoped process-discovery/ownership-proof
correction and reviewed delta, preserving fail-closed handling of potentially owned workloads.
Do not blanket-ignore EACCES, run as root, or weaken host security settings. No implementation
permission is reopened, and no product code needs to change for this harness issue.

The next allocation proposal also needs an explicit total K deadline and bounded recovery path.
The current harness has 16 supervisor timeouts of 325 seconds, K08 at 301, K08b/K16 at 275 each,
and K17 at 299: **6,350 seconds total**, excluding decoy setup, verification and recovery. The
approximately eight-minute estimate is not an enforced suite deadline. An outer deadline wrapper
was considered but neither adopted nor run; any supplied wrapper must cover its owned processes
and preserve systemd cleanup/unknown-state handling. Per-payload RuntimeMaxSec is 95 seconds
normally, 71 for K08, 45 for K08b/K16, and 69 for K17; stop is 15 seconds and cleanup 60 seconds.

Retain the decoy startup recovery edge (`run_controls.py:94-99`): service creation can succeed
before a timeout/interrupt prevents the handle reaching the caller. Its 120-second runtime bounds
the sleep, but control-prefix cleanup does not match `space-decoy-*`. Owner recovery and final
release proof must include these decoys explicitly. Decoys start before supervisor admission,
so a future K grant needs fresh allocation-level admission before starting the harness as well.

K03 remains last and intentionally returns 4 without a supervisor release receipt. Even if its
independent harness checks pass, the shared slot may be released only by the owner's explicit
receipt plus coordinator-verified absence; unknown proof keeps it held. S1, retries, full suites,
build and live runs remain ungranted. Proposed payload caps remain 2 CPUs/6 GiB/no swap (K09:
64 MiB), not R2c's 8 GiB. ELSPETH keeps priority, Sultai's GPU reservation remains untouched,
and Space gets no GPU, one selection and at most two test workers when separately allocated.
Chassis brief v5 remains an approved draft awaiting John's final-text approval; no adoption follows.
No reviewed code, control, test or unit was executed here. Only these coordinator records changed;
the main index SHA256 remains `86487638e8c0ae03e2c8739565e25d819e157e95967f4c17c5d1fc7c7623ac2a`.

## 32. B-sel1/v7 source accepted; stale Vehicle watcher blocks fresh admission — 2026-10-11 23:33 AEDT

**No allocation or launch.** The v7 source corrections satisfy §31 for the submitted K controls,
but fresh Nyx admission still finds an existing Vehicle-owned shell matching the workload rule.
Return this operational blocker through Emmy's existing browser relay; no direct owner message
or old ROOT/R2c grant was sent.

Verified final proposal SHA256 `4fe7c40ca3e094fa64a807605feee7d02c882cc324f3256420f40a082495fdb8`.
Replacing its single `WorkingDirectory=.../v7` occurrence with `.../v6` reproduces the reviewed
proposal hash exactly: `ad79fee54f55e2526376b938668059b7aaba3489191bcd68f3787a2f2a16313e`.
Thus the final proposal differs only by the disclosed directory correction. Manifest SHA256
`422ff9aa4ed7573fc9e79117f57e7135ac10c7f8cdfde2d44fcee53b78f55b32` and all 26 entries match.
Supervisor hash `a702a4e1381f39a40385a4dcc4d159b342e13e3ee7c917cc46cc7f6b3314372b`;
harness `fe6ea874c3de127311b36ac0e514d46975ba2f88f50d0f9f8b0b42f59fcd331a`;
control plan `d59d65dfa3c7ff840aebfe4e0403d0f3e34308b47c807d948ec2178f769125a8`.
Launcher and recorder are unchanged. Candidate HEAD, diff and all 92 tree blobs remain the §31
identities, with no untracked non-ignored files. Neither K nor S1 evidence directory exists.

Read the full v6/v7 reviews and actual v5-to-v7 and v6-to-v7 source changes. All 20 control specs
are unchanged from v5 except evidence paths; ordering remains serial with K03 last. The existing
independent reviewer also accepts v7 source for K subject to fresh admission and exclusive allocation.
Cleanup now excludes unreadable processes only when their readable start time predates run creation;
newer/unknown ones still fail. Admission separately classifies the narrowly enumerated host processes,
requires readable argv, and explicitly relies on Governance for exclusive allocation. This is
acceptable for these fixed payloads, not general proof that an old process cannot acquire a token.
The actual enclosing service alone is excluded from unit discovery. Decoy unit names are registered
before launch and recovered/proved by suite prefix.

The 1,800-second suite budget now reserves 120 seconds per post-control check and requires at least
210 seconds before starting another control. Queries/stops consume the remaining suite budget;
recovery has 180 seconds, with an outer service RuntimeMaxSec of 2,040 and stop timeout of 30.
These are the proposed K bounds, not an allocation. Separate payload services retain their §31
caps/runtime limits. K03's expected exit 4 is not automatic release; explicit owner receipt plus
independent final unit/cgroup/process/decoy proof remains mandatory.

Residuals: terminal-status acceptance may overshoot its small terminal wait after execution has
ended; retain this nonblocking timing residual. Misleading "were stopped" exception wording is
removed. `release_contains` still has no supplied consumer. K02 correctly describes a cleanup-only
receipt. The reviewed proposal's v6 WorkingDirectory P3 is fixed by the verified one-line correction.

At **12:30:28 UTC / 23:30:28 AEDT**, fresh read-only checks found **31.91 GiB available RAM**,
**21.1% CPU busy** over two seconds, load1 **5.02**, no Space user services/scopes or Space-named
containers; the proposed `space-vehicle-b-suite-k1.service` is not-found/inactive. The previously
unreadable host processes now fit v7's narrow classification, with no unclassified unreadable process.

However **PID 1664354**, bash, PPID 1410330, cwd `/home/john/space_chassis`, belongs to Vehicle
session `a728e992-9471-46ab-9efe-ce550d7ece5f`. Its argv contains an old polling loop for
`tasks/b2em98w09.output`, checking `pgrep -f "pytest tests/test_vehicle_config.py -q -x -p no:cacheprovider -k"`
and sleeping three seconds. It is an old result watcher, not evidence of a currently running test.
Nevertheless its executable/argv/cwd exactly match v7's documented admission predicate and it is
not an ancestor of the new systemd-launched supervisor. V7 therefore refuses K00 while it remains.
The loop can match its own argv, explaining why it can persist. A second read confirmed the shell
still present with a child and unchanged watcher command. It was not stopped by this coordinator.

Next action for the existing Vehicle owner: verify current PID/start identity and retire this
specific obsolete watcher through its owning task, preserving the output and unrelated work.
Do not loosen the admission predicate or modify the approved candidate to accommodate it. Return
watcher cleanup and refreshed admission/slot evidence for the K grant; no additional source review
is required if the exact package is unchanged. Capacity snapshots alone are not launch admission.
ELSPETH priority, Sultai GPU reservation, no GPU, one Space selection, and at most two workers remain.
S1/retries/full/build/live remain ungranted. Chassis brief stays draft pending John's text approval.
No reviewed code, controls, tests, collection or unit launch occurred. Main index hash is unchanged.

## 33. V7 K-only allocation granted; shared slot reserved — 2026-10-11 23:44 AEDT

**CURRENT SLOT: RESERVED — `SPACE-20261011-B-V7-K1`.** Under the existing delegated authority,
grant the existing Vehicle owner `session_01GRfs7dVMu4v5airK6q3w9C` / session
`a728e992-9471-46ab-9efe-ce550d7ece5f` exactly **one v7 K harness invocation**, at most the
20 serial controls in the reviewed plan, with K03 last. No pytest, collection, S1, retry, full suite,
build or live run follows. Emmy retains the existing browser relay; no direct owner message or
execution occurred in this coordination turn.

**Launch expiry: 2026-10-11 13:00:00 UTC / 2026-10-12 00:00:00 AEDT.** If not launched by then,
the launch permission expires; report NOT STARTED and return for refreshed admission/allocation.
Expiry never releases a launched or uncertain run. Once launched, hold the slot until explicit
owner release and coordinator-verified cleanup. No other Space selection is allocated concurrently.

### Cleanup and admission verified

Read the owner retirement receipt and matching transcript evidence: the owner revalidated PID
1664354/startticks 53945734/UID 1000/PPID 1410330, preserved its output, and reports TERM to that
PID alone at 12:40:03 UTC, followed by absence at 12:40:15. Independently confirmed PID absent,
parent 1410330 still present, and unrelated watcher 1605464 still present at fresh inspection.
The latter does not match admission and remains outside this grant; no cleanup of it is required.
Original and preserved output bytes match SHA256
`2fa18ba6805656128e5d45a0c259b5a63b7ae0921ebe5c14e03d178b3b818ef9`.
Retirement `RECORD.md`: `95cbecdad7c80776c47c1e71499755ebc3e813ec054bacc8b74514b46a0ae245`;
owner admission snapshot: `b72674606c3d9b27712d12cf1e60ddd9cba78bdcf06edd57c97e858c689f44ba`.

Independent read-only Nyx check at **12:43:41 UTC / 23:43:41 AEDT**: 24 logical CPUs,
**37.76 GiB available**, **21.8% CPU busy** over two seconds, load1 **5.92**; no v7 predicate
matches or unclassified unreadable processes, no Space user units or Space-named containers.
The nine protected host processes fit v7's narrow classification. Proposed suite unit is
not-found/inactive with empty ControlGroup. Two unrelated containers and interactive/MCP processes
remain untouched. Existing allocation records and the waiting owner's receipt identify no other
active Space grant. Discovery is a secondary check, not the source of exclusive allocation.

### Frozen grant identities

- Proposal SHA256: `4fe7c40ca3e094fa64a807605feee7d02c882cc324f3256420f40a082495fdb8`.
- Manifest SHA256: `422ff9aa4ed7573fc9e79117f57e7135ac10c7f8cdfde2d44fcee53b78f55b32`;
  all 26 entries independently reverified. Script/plan identities and accepted residuals are §32.
- Candidate HEAD: `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f`.
- Candidate diff SHA256: `0a00336feb10dcd5c8839893cabafbdc5cbea20474f918d76dc1e0eca3f2d01d`.
- Candidate tree: `b447955f60c528e78d05c324ecc4c4317128d1a1`; all 92 tracked blobs reverified,
  no untracked non-ignored paths. K and S1 evidence directories still absent.

Immediately before the suite launch (within 60 seconds), the owner must independently refresh
identity, evidence freshness, slot ownership and v7 admission: MemAvailable >=16 GiB, CPU busy
<=50% over two seconds (unknown refuses), load1 <=12, no competing Space selection/process/unit/
container, and the exact suite name unused. Do not start after a failed/unknown check or alter the
reviewed predicates to pass. Admission must precede the harness because it creates decoys before
per-control admission. No overlapping Space work may be launched by either owner during this grant.

### Exact one-shot command for the owner

After the checks above, execute once as the existing unprivileged owner on Nyx, with the working
user systemd bus. These commands produce the same argv as the reviewed proposal; no source change:

```sh
K_V7=/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7
mkdir -p "$K_V7/controls-evidence"
systemd-run --user --no-block --collect --unit=space-vehicle-b-suite-k1 -p RuntimeMaxSec=2040 -p KillMode=control-group -p TimeoutStopSec=30 -p Nice=19 -p Environment=CUDA_VISIBLE_DEVICES= -p "WorkingDirectory=$K_V7" -p "StandardOutput=file:$K_V7/controls-evidence/harness.out" -p "StandardError=file:$K_V7/controls-evidence/harness.out" /usr/bin/python3 "$K_V7/run_controls.py" "$K_V7/controls.json"
```

Require a fresh evidence directory, no reused unit and no rerun after any result. A failed launch
must be reconciled as possibly created until successful unit/cgroup/process queries prove otherwise.
Record UTC launch time and outer unit InvocationID, MainPID, ControlGroup and property readback.

### Bounds, abort and release

K contains no test workers. Retain the program maximum of two workers and one Space selection.
The outer harness and payload services use Nice=19, and all reviewed payloads use no GPU.
Each serial payload service has CPUQuota=200%, MemoryMax=6G, MemorySwapMax=0, OOMPolicy=stop;
K09 deliberately uses 64M. Payload cap readback precedes GO. These are per-payload caps; the outer
harness/control clients and tiny sleep decoys are not collectively covered by that memory/CPU cap.
Do not describe it as an aggregate 6-GiB cgroup ceiling. ELSPETH retains priority, Sultai's GPU
reservation is untouched, and no host security changes or privilege escalation are authorised.

Suite budget is 1,800 seconds, with a 120-second post-control reserve and a 210-second minimum
remaining before another control starts. Each supervisor timeout is at most its declared bound
(325 seconds normally; K08 301, K08b/K16 275, K17 299), further reduced by the remaining suite
budget/reserve. Recovery is bounded to 180 seconds, ending by 1,980 seconds under the reviewed
normal scheduling assumptions. Outer RuntimeMaxSec is 2,040 seconds and TimeoutStopSec 30:
the operational outer deadline is **launch + 2,070 seconds (34.5 minutes)**. Separate payload
units retain RuntimeMaxSec 95 normally, 71 for K08, 45 for K08b/K16, 69 for K17, with 15-second
stop; the owned decoy unit has RuntimeMaxSec 120. Missing deadline evidence is failure, not pass.

Per-control admission/pre-GO health checks and five-second monitoring remain enforced. MemAvailable
below 10 GiB, attributable unexpected OOM, lost supervision/ownership or deadline failure aborts
owned work; CPU >85% (unknown counts high) or load1 >20 for three samples also aborts. Expected
injected OOM/deadline/interrupt/refusal results count only with their exact cause assertions and
independent cleanup checks. Do not confuse a deliberate control failure with permission to retry.
If ELSPETH needs the slot or monitoring/cleanup becomes uncertain, stop only this allocation's
outer/control/decoy units and preserve the evidence; keep the slot held pending reconciliation.

Return the 20 per-control rows/checks, raw harness output and status, all available supervisor
logs/receipts/summaries, caps/signals/samples/terminal evidence, suite token/final recovery proof,
actual start/end times, and unchanged before/after identities. Acceptance requires exactly the
intended controls, every expected assertion, and clean final proof; wrapper exit or unit absence
alone is insufficient. A missing/partial report, unknown discovery, timeout or unmatched cause
is not qualification.

**K03 is last and deliberately returns 4 with no supervisor release receipt.** Its expected result
does not release the slot. The owner must return an explicit result/cleanup/RELEASE receipt after
the suite ends. This coordinator independently verifies the outer unit and every logged control/
owned decoy unit are absent/inactive with absent cgroups, no owned token/helper/decoy processes,
and no live monitor or harness remains. Only then mark the slot FREE. Failed/unknown proof keeps
it HELD and is escalated through Emmy; no blanket stop or change to unrelated processes.

K success would qualify these supervision controls only. It does not qualify candidate3's vehicle
tests, grant S1, advance chassis adoption, approve final brief text or close issue 42. No execution,
control, test, collection, commit or owner source edit was performed by this coordinator; only
coordinator records changed. Main index SHA256 remains
`86487638e8c0ae03e2c8739565e25d819e157e95967f4c17c5d1fc7c7623ac2a`.

## 34. K1 accepted and released; separate S1 allocation review prepared — 2026-10-12 00:01 AEDT

**CURRENT SLOT: FREE / RELEASED — `SPACE-20261011-B-V7-K1` complete.** Accepted the owner's
explicit release after independently reconciling raw control evidence and current owned cleanup.
**All 20 controls passed their expected outcomes, once, serially, with K03 last.** This qualifies
the submitted K supervision controls only; no pytest or S1 ran and no next allocation follows.

### Evidence reconciliation

The owner prelaunch record shows fresh identity/admission checks from 12:48:37 to 12:48:39 UTC,
then one suite launch at **2026-10-11 12:48:39.461 UTC**, before the grant's launch expiry.
Outer InvocationID `0eb412ca87ef44aaad5fc21f4c8e8885`, MainPID 268508; owner transcript readback
confirms RuntimeMaxUSec=34min, TimeoutStopUSec=30s, KillMode=control-group, Nice=19 and the expected
cgroup. Raw control events span **12:48:39.535–12:54:31.499 UTC**, about 352 seconds.
The owner terminal observation at **12:54:38 UTC** reports unit not-found/inactive, Result=success.
Owner explicit release was written **12:55:24 UTC**; it remained held until this verification.

Independently verified all **122 evidence-file hashes**, all 26 source/spec manifest entries,
and unchanged final proposal/candidate HEAD/diff/92 tree blobs. Raw harness rows exactly equal
the summary's 20 control rows and match the plan order. Each has one start/outcome, matching
script/spec hashes, expected return code, receipt presence/absence, cause text, terminal fields,
JSON assertions and required files. Consecutive control event ranges do not overlap. Result
distribution: two exit 0, fourteen exit 3, three exit 2, one exit 4, exactly as planned.
K03 has **no RELEASE.txt** and its exit 4 is expected; its `checks.release=true` means the expected
absence assertion passed, not that its supervisor released the slot.

Fifteen payload cap readbacks match the actual specs (including K05's deliberately mismatched
comparison target), all 15 recorded launcher SIGINT restorations hold, and all available post-run
identity records match except K11's explicit injected digest. Current candidate identity is exact.
Across 34 monitoring samples, minimum available RAM is **34,714 MiB**, maximum CPU busy **33.3%**,
maximum load1 **5.38**. Maximum recorded control memory peak is **64 MiB**, from the intentional
OOM control; this is not a pytest memory measurement. Expected timeout/OOM/interrupt controls
have the required cause evidence. Suite final proof has empty control/decoy unit lists,
decoy processes ended, recovery within deadline, and `proven_clean=true`.

Evidence identities under `B-sel1/`:

| Evidence | SHA256 |
|---|---|
| `v7/v7-K1-evidence.SHA256SUMS` (122 entries) | `98cc13330c66346bb58baaf41f796de2a7560c6dcecb664b792c6b0810c504e9` |
| `v7/controls-evidence/controls-summary.json` | `a13af7abe9586f087d1c374d08145fc238af9c8d7d724eeb37ddeaab0c9618d3` |
| `v7/controls-evidence/harness.out` | `99c60b0ac5494e469332ec681dbdcea1b85931c0a2f1c06d952bfda476883aed` |
| `v7-K1-prelaunch.txt` | `4de53749bbd132f80e50dc7ea13c8605a4952d14d9df374ec20147b8691059f9` |
| `v7-K1-postrun.txt` | `c2edea86b56e8a5ec5a43e0075a268568d531a4883e1b68a19dbffc74a104829` |
| `v7-K1-OWNER-RELEASE.md` | `06c4483f6c506eb72470bb0521ca3d090b98a72e6c68c0a3387f141bc5a8ba59` |

### Independent release proof

At **12:59:39 UTC October 11 / 23:59:39 AEDT**, successful independent systemctl queries
confirmed all **22 known unit names** (outer, 20 control names including admission refusals, and
owned decoy) not-found/inactive with empty ControlGroup. All 22 known/derived cgroup paths are
absent; no Space cgroup remains under app.slice, and successful listings find no Space user unit
or Space-named container. No own-user process carries any of the **21 suite/control tokens**.
All 11 unreadable process environments have readable start times older than a conservative
pre-suite lower bound; no unknown newer process remains. No recorded payload/MainPID survives.
A further scan finds no remaining unit-referencing polling monitor, harness or supervisor.
Explicit owner release plus this positive cleanup proof releases the slot; neither K03's expected
status nor process absence alone was used as release authority.

### Prepared S1 review — not a grant

The existing independent reviewer inspected actual S1 spec and supervisor acceptance handling.
Spec SHA256 `6bcb9af009b52c880a03c9d4cb788da1c49c9753e58935648d64f546d221d3a1` selects one
Python 3.12 pytest invocation, two workers and 25 exact node IDs. Static inspection finds all 25
functions in candidate3 without parametrization decorators; no collection was performed.
`v7/evidence-S1` remains absent. No new scoped source blocker was found.

The separate grant must bind an outer supervisor lifecycle as well as the existing payload bounds.
Prepared envelope: unique `space-vehicle-b-supervisor-s1-1.service`, RuntimeMaxSec=900,
TimeoutStopSec=30, KillMode=control-group, Nice=19, empty CUDA visibility, launching only
`/usr/bin/python3 V7/supervise.py V7/spec-S1.json`. Keep outer output outside `evidence-S1`
(for example `V7/s1-supervisor.out`) because the supervisor requires its evidence directory absent.
This provides a 930-second operational outer envelope; the separately launched payload retains
its own 420-second run deadline, RuntimeMaxSec=485, 15-second stop, 60-second cleanup and
2-CPU/6-GiB/no-swap caps. Outer exit never proves the payload unit gone.

**S1 acceptance must independently check actual pytest success.** The supervisor treats both
`success` and `exit-code` terminal results as completed and merely records JUnit counts; therefore
`supervisor_exit=0` or a cleanup receipt alone is insufficient. Require SERVICE_RESULT=success,
EXIT_CODE=exited, EXIT_STATUS=0, exactly the intended 25 JUnit testcases, zero failures/errors/skips,
consistent raw output/JUnit, unchanged identities, and independently verified cleanup plus explicit
owner release. Missing JUnit, count mismatch, nonzero payload status or unknown evidence fails S1.

Remaining allocation work: set the exact outer command/log identity, fresh unused unit/output/
evidence paths, a finite launch expiry, and fresh capacity/one-selection admission immediately
before a separate grant and launch. Current capacity (39.15 GiB available, CPU 13.4%, load1 3.75)
is only a release-time snapshot, not that grant. No new product decision or repeated implementation
review is needed if identities remain unchanged. ELSPETH priority and Sultai's GPU reservation
remain; no S1/retry/full/build/live run, chassis adoption or brief-text approval is granted here.
No direct owner message, execution, tests or source changes occurred in this coordinator turn;
only coordinator records changed and the main index hash remains unchanged.

## 35. Separate S1 allocation granted; shared slot reserved — 2026-10-12 00:11 AEDT

**CURRENT SLOT: RESERVED — `SPACE-20261011-B-V7-S1-01`.** Under the parent's explicit delegated
instruction to decide this separate allocation, grant the existing Vehicle owner
`session_01GRfs7dVMu4v5airK6q3w9C` / local session `a728e992-9471-46ab-9efe-ce550d7ece5f`
**one invocation of the exact v7 S1 spec: 25 named tests, Python 3.12, two pytest workers**.
This is a new allocation decision following the prepared §34 review and fresh checks, not an
automatic consequence of K success. No material decision beyond existing authority is required.
No retry, additional selection, full suite, build/live gate, source repair, commit or merge follows.
Emmy retains the single browser relay; nothing launched or directly messaged by this coordinator.

**Launch before 2026-10-11 13:25:00 UTC / 2026-10-12 00:25:00 AEDT.** Launch permission expires
if unused; report NOT STARTED for refreshed allocation. Expiry never frees a launched or uncertain
run. Hold the slot until the explicit owner release and independent cleanup verification below.

### Fresh checks and exact identities

At **13:09:37 UTC October 11 / 00:09:37 AEDT October 12**, independent read-only Nyx inspection
found **38.56 GiB MemAvailable**, **27.1% CPU busy** over two seconds, load1 **7.00**, no matching
Space workload or unclassified unreadable process, no Space user unit/cgroup, and no Space-named
container. `space-vehicle-b-supervisor-s1-1.service` is not-found/inactive with empty ControlGroup.
Three container inspections identify ELSPETH CI workdirs/mounts; a generic Postgres container has
no Space-identifying workdir/mount. All remain untouched. K1 is explicitly released under §34 and
there is no concurrent Space allocation. The unrelated old output watcher remains outside scope.
The slot reservation, coordinated through Emmy, enforces exclusivity; process discovery remains
a documented secondary heuristic.

Independently reverified all 26 manifest entries and these exact identities:

| Artifact | Identity |
|---|---|
| `v7/PROPOSAL.md` SHA256 | `4fe7c40ca3e094fa64a807605feee7d02c882cc324f3256420f40a082495fdb8` |
| `v7/SHA256SUMS` SHA256 | `422ff9aa4ed7573fc9e79117f57e7135ac10c7f8cdfde2d44fcee53b78f55b32` |
| `v7/supervise.py` SHA256 | `a702a4e1381f39a40385a4dcc4d159b342e13e3ee7c917cc46cc7f6b3314372b` |
| `v7/launch.py` SHA256 | `be38cdb6bd73ea24aff1ad9338cba1d38732dfc316b5b4f68469a5874a250aae` |
| `v7/record.py` SHA256 | `1ab08ff4818ceb78ef3e0261e9415fcf9982ab28c0ca99c851ba0ded47df2c33` |
| `v7/spec-S1.json` SHA256 | `6bcb9af009b52c880a03c9d4cb788da1c49c9753e58935648d64f546d221d3a1` |
| Candidate HEAD/base | `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f` |
| Candidate diff SHA256 | `0a00336feb10dcd5c8839893cabafbdc5cbea20474f918d76dc1e0eca3f2d01d` |
| Candidate tree | `b447955f60c528e78d05c324ecc4c4317128d1a1` |

Candidate worktree:
`/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9`.
All 92 tracked blobs match, with no untracked non-ignored paths. All 25 unique node IDs match
one function each, without decorators, by static AST inspection; no collection was performed.
The specified venv interpreter exists. Both `v7/evidence-S1` and `v7/s1-supervisor.out` are absent.
Retain the accepted §32 terminal-timing residual and §34 independent pytest-result acceptance rule.

### Owner admission and exact one-shot launch

Within **60 seconds before launch**, refresh hashes/candidate, unused outer unit/log/evidence paths,
exclusive allocation and host admission: MemAvailable >=16 GiB, CPU busy <=50% over two seconds,
load1 <=12; unknown measurements, unreadable unclassified processes, or another Space workload/
unit/container refuse. Both owners must keep other Space selections stopped throughout this grant.
ELSPETH retains priority; no GPU is used and Sultai's reservation remains untouched. Do not bypass
the predicates, enlarge a bound or rename/reuse evidence to retry. Refuse on any identity drift.

Run the following exactly once as the existing unprivileged owner on Nyx with its working user
systemd bus. **Do not create `evidence-S1` beforehand**; the supervisor creates it. Outer output
is deliberately outside that directory. No source/spec edits are needed:

```sh
S1_V7=/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7
systemd-run --user --no-block --collect --unit=space-vehicle-b-supervisor-s1-1 -p RuntimeMaxSec=900 -p KillMode=control-group -p TimeoutStopSec=30 -p Nice=19 -p Environment=CUDA_VISIBLE_DEVICES= -p "WorkingDirectory=$S1_V7" -p "StandardOutput=file:$S1_V7/s1-supervisor.out" -p "StandardError=file:$S1_V7/s1-supervisor.out" /usr/bin/python3 "$S1_V7/supervise.py" "$S1_V7/spec-S1.json"
```

This launches the reviewed payload through the spec's exact interpreter and arguments, including
`-m pytest -p no:cacheprovider -n 2 -q -rfEs -o addopts=` and the 25 listed node IDs/JUnit path.
No extra collection or preliminary pytest invocation is authorised. Capture UTC launch time,
outer InvocationID/MainPID/ControlGroup and read back RuntimeMaxUSec=15min, TimeoutStopUSec=30s,
KillMode=control-group, Nice=19 and intended command. A mismatch invalidates the run and requires
owned cleanup, not adjustment and continuation. A failed launch is possibly created until proved absent.

### Resource, time and abort limits

One Space selection; **two pytest workers total**. The payload cgroup, including its workers,
has CPUQuota=200%, MemoryMax=6G, MemorySwapMax=0, OOMPolicy=stop, Nice=19 and no GPU. The reviewed
supervisor verifies cap readback and healthy pre-GO state before releasing tests. The outer
supervisor is separately niced and bounded; the 6-GiB cap is a payload ceiling, not an aggregate
outer-plus-payload cgroup cap or a measured S1 requirement.

Admission deadline 60 seconds; setup 30; launcher GO wait 35; payload run deadline **420 seconds**;
payload systemd RuntimeMaxSec **485**, stop timeout 15; terminal wait 20 (retained small late-query
residual); cleanup 60. The outer supervisor's independent limit is **900 seconds plus 30 seconds
shutdown**, operational deadline **launch + 930 seconds**. Its termination does not certify that
the separately launched payload unit has ended; explicitly reconcile both on any abnormal exit.

Sample every five seconds. Abort owned work for available RAM below 10 GiB, any attributable OOM,
lost supervision/ownership, cap/identity failure, deadline or operator priority withdrawal. CPU
busy >85% (unknown counts high), or load1 >20, for three consecutive samples also aborts. If
ELSPETH needs the capacity, stop only this allocation's owned outer/payload/helper processes.
No host/security-setting change or unrelated process/container stop is authorised. An abort or
uncertain cleanup retains the slot; no rerun to green.

### Acceptance and explicit release

Require **actual payload SERVICE_RESULT=success, EXIT_CODE=exited, EXIT_STATUS=0**, plus exactly
the intended **25 JUnit testcases**, no duplicates/unexpected cases, and **zero failures, errors
or skips**, reconciled against raw pytest output. Require unchanged before/after candidate/script/
spec identities, valid cap/signal/monitor/terminal evidence, and no abort reasons. Neither
`supervisor_exit=0`, an outer success state, nor RELEASE.txt alone establishes a passing test gate.
Missing JUnit, wrong count, missing selected case, nonzero payload status or unknown evidence fails.

Return raw `evidence-S1/payload.out`, JUnit, supervisor.log, samples, READY/TERMINAL/summary/receipt,
outer `s1-supervisor.out`, unit property/timing evidence, memory peak and evidence hashes. Separate
the pytest result from supervision and cleanup verdicts. Preserve every failure artifact unchanged.
The owner must explicitly release `SPACE-20261011-B-V7-S1-01` after the run ends, even after a pass.
This coordinator must independently verify outer and logged payload units not-found/inactive with
absent cgroups, no owned token/worker/helper process or remaining monitor, and reconcile the receipt.
Unknown proof keeps the slot HELD and returns through Emmy; no automatic release or next selection.

If S1 passes, only candidate3's bounded 25-test selection advances. Full two-lane qualification,
PR/merge, chassis adoption, build/live and final brief text remain separate. No product decision
is reopened and issue 42 remains separate. No execution, collection, test, owner message or source
change occurred here; only coordinator records changed. Main index SHA256 remains
`86487638e8c0ae03e2c8739565e25d819e157e95967f4c17c5d1fc7c7623ac2a`.

## 36. S1 accepted and released; Option B final-package preparation next — 2026-10-12 00:23 AEDT

**CURRENT SLOT: FREE / RELEASED — `SPACE-20261011-B-V7-S1-01` complete.** Independently
verified the owner's raw evidence and current cleanup before accepting the explicit release.
**Exactly the 25 selected tests passed, actual pytest exit 0, zero failures/errors/skips.**
This advances candidate3's bounded S1 selection only. No full-gate or other execution grant follows.

### Result and identity verification

Owner prelaunch checks ran 13:15:46–13:15:48 UTC October 11; launch was **13:15:48.192 UTC**
(00:15:48 AEDT October 12), inside the grant. Outer invocation
`c121704d83e94f61ba9029f63cf0a11c`, MainPID 479440, with owner transcript readback of the exact
supervisor/spec command, 900-second runtime, 30-second stop, KillMode=control-group and Nice=19.
Payload unit `space-vehicle-b-s1-0a704983bae8.service`, invocation
`5d2bbdd7b7154a9b967f85fa7e22343a`, MainPID 479785. GO at **13:15:51.463**; terminal evidence
at **13:16:21.498**, cleanup verified on first attempt at **13:16:21.532**, outcome 0 at
**13:16:21.552 UTC**. Owner observed the outer unit unloaded by **13:16:33 UTC**, with
Result=success and ExecMainStatus=0. The explicit owner release was written **13:17:14 UTC**.

Raw pytest output says `25 passed in 25.75s`. Independently parsed JUnit: 25 unique cases exactly
equal to the spec's node IDs, no missing/extra/duplicate case, no failure/error/skipped elements;
suite counts 25/0/0/0 and time 25.752 seconds. Recorded payload arguments match the exact spec,
including `-n 2`. TERMINAL.json reports success/exited/0, matching summary and log. No aborts,
OOM or cgroup read problem; SIGINT restored; readback is cpu.max `200000 100000`, memory.max
`6442450944`, memory.swap.max `0`. Six samples: minimum available RAM **38,354 MiB**, maximum
CPU busy **34.0%**, maximum load1 **6.15**. Recorded payload memory peak **586,248,192 bytes**
(559.09 MiB). This measures S1, not the full suite's memory requirement.

All eight evidence-manifest entries and all 26 source/spec-manifest entries verify. Start records
match the exact supervisor/launcher/recorder/spec hashes; post-run identity and fresh current
HEAD/diff/92 tracked blobs match §35. No untracked non-ignored files. Candidate remains uncommitted,
with only `tools/console.py` and `tests/test_vehicle_config.py` changed. Main index unchanged.

Evidence identities under `B-sel1/`:

| Evidence | SHA256 |
|---|---|
| `v7/v7-S1-evidence.SHA256SUMS` | `a72518fd98e589e1d5d8f95b1b2c7e520607f47906379a24ea3e8782593b6f07` |
| `v7/evidence-S1/junit.xml` | `72a0a99b3727ff38ba6149881c873b1423a277072c14bdc0a16c62d262e863c9` |
| `v7/evidence-S1/summary.json` | `af5868c13851d2799548009108c03889fd61998dc043fd873eb395d88491bc8a` |
| `v7/evidence-S1/TERMINAL.json` | `b8294c92adf931012378c8a9ac6cbbf18b90bed1cf1b0cfe155863b71a1772bd` |
| `v7/evidence-S1/payload.out` | `d97d3108347ad158d4b105905538463c26d8193e33315c75e93f7ed0738e29d5` |
| `v7/evidence-S1/supervisor.log` | `7c03b1585db6d6beefa72a76a6ab8d3d8e89c4b8f5b6b2dee824e18651adbc33` |
| `v7/s1-supervisor.out` (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `v7-S1-prelaunch.txt` | `7d11f97ce4cc911c0c365b51e4cb387fe07fece46bc1843d39a68b6d1df32aed` |
| `v7-S1-postrun.txt` | `c0b5963133ede7d1778ff4e81411c49105591aa282fd38c827b163effd69d253` |
| `v7-S1-OWNER-RELEASE.md` | `5d9021cb5047fd47c9553de2594aaf4e1e8adcaf8b12d4473c1ab88e94dea059` |

### Independent release proof

At **13:21:21 UTC October 11 / 00:21:21 AEDT October 12**, successful independent queries find
both outer and payload units not-found/inactive, empty ControlGroup, absent recorded/derived
cgroups, no Space user units, no Space app.slice cgroups and no Space-named containers. No process
carries the payload token, both recorded PIDs are absent, and no associated helper/monitor remains.
All 11 unreadable own-process environments have readable start ticks older than a conservative
pre-run lower bound; no unknown newer process remains. Together with the owner's explicit release,
this proves release under §35. Supervisor success and its cleanup-only receipt were not used as
substitutes for pytest acceptance or owner release.

### Next action for Emmy's existing Vehicle relay

**Prepare Option B's final integration package and an exact bounded full-development-gate proposal;
do not execute it yet.** This is continuation of John's approved Option B implementation, not a
request to approve implementation again. Reconcile candidate3's design/implementation review chain,
K and S1 evidence; prepare required README round/ADR or other package metadata and final review
material. Preserve the distinction between 25 selected passes and an as-yet unmeasured full-suite
count. Freeze any metadata delta explicitly; do not silently change the approved source identity.

The owner's checkpoint 22 already identifies full qualification in Python 3.12 and 3.13 as next.
Current candidate `CONTRIBUTING.md` requires the full development gate and whole suite with zero
skips before commit. `governance/vehicle/practice.md` additionally calls for detached exact-head
qualification in hash-locked environments on both lanes, followed by independent code/evidence
review. The proposal must reconcile pre-commit validation with final committed-head qualification,
and give exact commands/selections, frozen source, interpreter/lock identity, fresh separate evidence
paths, serial lane ordering, at most two workers, explicit resource/deadline/abort/cleanup bounds,
and expected results. Use the existing repository-defined gate; no new test scope is invented here.
Full-gate **execution needs a separate allocation** with fresh admission. No such grant is issued.

Prepare the focused `vehicle:` commit message and PR body locally. Actual commit must satisfy
the repository's gate requirements. Final independent review must cover the actual final diff and
acceptance evidence; retained candidate3 approval need not be repeated without a delta. Corrective
deltas need the appropriate confirming review and requalification, never a retry-to-green claim.

**External publication remains a separate John decision for Option B.** Direct transcript evidence
at 09:11–09:14 UTC shows his "yes agree with both your recs" approved (1) tier-1 push/PR/merge on
green CI, and (2) Option B code after that merge. It does not establish Option B publication
approval. Vehicle practice explicitly says "Ask John before external publication"; prepare the
concrete qualified package before seeking that decision. Its standing green-CI merge rule applies
once publication is authorised, with required Development checks (3.12, 3.13, readiness diagnostic)
and independent review/blocker resolution. No direct implementation push to main. The existing
independent governance reviewer confirms this authority distinction; implementation is not reopened.

After an authorised merge, publish the exact merge-SHA adoption package through the existing
Vehicle-to-Chassis route. Chassis separately owns its pointer/reconciliation change and adoption
gates. Chassis brief remains draft awaiting John's final-text approval, and issue 42 is separate.
ELSPETH priority and Sultai's reservation remain intact. No new writer, direct owner message,
execution, retry, commit or publication was performed here. Only coordinator records changed;
main index SHA256 remains `86487638e8c0ae03e2c8739565e25d819e157e95967f4c17c5d1fc7c7623ac2a`.
