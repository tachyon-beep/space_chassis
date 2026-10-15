# Independent review — vehicle-to-green programme

Reviewed 2026-10-04. Scope: programme correctness and commissioning readiness, not implementation acceptance.

Reviewed artifact: [2026-10-04-vehicle-to-green-programme.md](/home/john/Documents/Codex/2026-10-04/task-5/2026-10-04-vehicle-to-green-programme.md). SHA-256 at review: `53cc228a5545bcf46f7b9dddc6fd0ddedcc9b006b37a24ce4724ffe75467a0d5`.

## Outcome

**Suitable as the programme direction, with one material dependency to resolve before commissioning the resource episode and three minor corrections. No critical blocker to commissioning A1, B0/C0 or the evidence investigation.** This review does not authorize implementation or a model-backed pilot, certify the six reported reproductions, or accept I/T/B/V/M/E.

The sequence is sound: establish custody and development evidence; decide shared ownership, clock and recovery together; prove the real two-window path; close a bounded physical dependency set with independent references; then accept an episode. Full breadth and full mission acceptance remain separate and explicitly necessary on the default route. The proposed prototype exception is visible and requires a recorded operator decision.

## Blockers

No critical programme blocker found. The resource-episode dependency below must be resolved at its design/feasibility gate; it does not justify blocking unrelated executive, privacy or evidence work.

## Major finding

### M1 — Give the first episode a productive activity and completion observable before calling its closure feasible

**Location:** programme lines 108–114, package F/H at 86–88, F0 at 164, decision at 176.

The proposal makes “a declared amount of useful work/data by a contact deadline” the reason to spend resources, and requires two distinct successful schedules. But it has not selected what produces that work/data, which existing command changes its rate, how completion is measured, or which dependencies belong to that productive path. F0's two explicit evidence questions cover electrical-source/load response and thermal/cooling aggregation. Those alone cannot establish that the proposed task is achievable or has the two promised strategies.

This is a concrete uncertainty in the source, not a request to write a detailed execution plan. The existing [mission objectives](/home/john/space_chassis/docs/deep_research/vehicle/mission.yaml:889) specify crew survival, surface mission, return, resource margins and externally measured coordination; they do not identify this new work/data-delivery objective. The existing [power load command](/home/john/space_chassis/docs/deep_research/vehicle/domains/power/commands.yaml:94) switches named equipment, which is not by itself a useful-work production model. If the intended task is transmitting stored data, the [onboard recorder capacity](/home/john/space_chassis/docs/deep_research/vehicle/domains/comms/components.yaml:174) remains `UNCONFIGURED`, and transfer/comms dependencies become part of the closure. A contact schedule accepted as a boundary condition does not establish the data-production or delivery mechanism.

**Requested disposition:** include an explicit F0/H design decision selecting one existing activity and its command → physical operation → measurable completion path, or record that a separately declared task model is required. Name the minimum productive-path inputs and independent oracle alongside the electrical and thermal questions. Keep the two viable policies as an acceptance hypothesis to demonstrate, not a reason to tune unsupported physics. If no evidenced activity fits, return a blocked episode choice with alternatives to John. This can be a short addition at programme level; no numerical values or implementation need be invented now.

**Why major:** without it, the recommended first episode can consume the proposed engineering tranche yet still have no physically meaningful task to schedule. This affects the episode's dependency closure and effort, not merely its wording. The programme already defers feasibility to F, so this is a missing explicit question rather than a claim that the draft has falsely passed F.

## Minor findings

### m1 — Distinguish deliberately declined verbs from unfinished effects in the coverage ledger

**Location:** programme line 126 says every verb, “including presently declined verbs,” gets a row with an implemented consumer and independent reference, with unresolved rows left visible.

Some declined/not-implemented entries are permanent protections, not backlog. Examples are [resource reservation/allocation](/home/john/space_chassis/docs/deep_research/vehicle/domains/consumables/commands.yaml:140), deliberately withheld so agents must invent their own arrangements, and [set_sensor_good / override_stale_limit](/home/john/space_chassis/docs/deep_research/vehicle/domains/avionics/commands.yaml:153), whose absence is a safety property. Requiring an effect consumer for these would either leave V impossible or invite implementing prohibited authority.

**Correction:** say that ledger rows distinguish implemented effects, outstanding implementation, intentionally refused commands and accepted scope exclusions. A deliberately declined verb closes through its rationale and an executable refusal/no-effect check where applicable. It does not become implementation debt. Other passages preserve these boundaries, so this is a local ambiguity rather than an overall design reversal.

### m2 — Repair the authoritative-source links for the delivered artifact location

**Location:** programme line 18.

All four relative links to the roadmap, completion contract, evidence policy and contribution rules resolve to nonexistent paths from the saved `task-5` directory. I checked their resolved paths. The assessment link at line 33 resolves correctly.

**Correction:** use working absolute workspace links in this deliverable, or place a repository-relative copy only in a separately authorized repository documentation action. The user should be able to inspect the actual authorities without guessing a future installation location.

### m3 — Disambiguate package letters from acceptance gates at the pilot decision

**Location:** programme line 179, “Only after B evidence”; also the D/E labels used for both packages and existing gates.

Package B is the shared executive; `B(episode)` is bounded mission readiness. This sentence should explicitly name `B(episode)` if that is the intended prerequisite. Lines 58 and 63 otherwise make the stronger pilot condition clear, so I do not interpret the draft as authorizing an early launch. Still, this is a poor place to leave two plausible referents.

**Correction:** spell out the bounded episode gate in decisions and use “package” or “gate” when D/E could be misread. No wholesale renaming is needed.

## Checks that support the programme

- **Gate fidelity:** the full target and D/I/V/M/E meanings agree with [completion.md](/home/john/space_chassis/docs/deep_research/vehicle/docs/completion.md:1). The 192-hour × 50 Hz calculation is 34,560,000 ticks; the live `20 ms / multiplier` and 300-second replay targets are accurately presented as targets, not measurements. Strict 0 is necessary but not sufficient. The fixture never closes physical or mission acceptance.
- **Dependency order:** B/C design is joined before persistence implementation; D relies on settled interfaces and actual command physics; E relies on the relevant plant path; H waits for scope physics and chassis boundaries. Early evidence research is permitted independently. This respects [ROADMAP.md](/home/john/space_chassis/docs/deep_research/vehicle/ROADMAP.md:14), while sensibly splitting package implementation from integrated closure. Deferring large flight implementation does not remove it from J.
- **Full ambition:** all eleven named domains remain covered by the programme's groups and coverage requirement. Applicable configurations, phases, command effects, faults and observation routes survive. No percentage complete, reduced timestep or green-by-deletion is proposed.
- **Authority and recovery:** the private effect journal, effect-time checks, lower-only allowance, OS-backed attribution and preserved ceilings reflect [the diode contract](/home/john/space_chassis/docs/diode-contract.md:132). The draft correctly retains destructive at-most-once intake and claimed-batch crash loss from [section 2.2](/home/john/space_chassis/docs/diode-contract.md:55), rather than promising exactly-once submission. Exactly-once committed irreversible effects are a recovery property to prove, not an intake guarantee.
- **Frozen interface:** `pending.json` remains an explicit unresolved compatibility decision. One final result per command and protected private lifecycle storage are compatible with the frozen interface. Resolving permissions and commit semantics before coding is appropriate; this review does not certify any particular mount solution.
- **Physics and perception:** independent oracles, sources/sinks, nonzero conservation, timestep refinement, mutation/negative controls and explicit effectivity meet [evidence.md](/home/john/space_chassis/docs/deep_research/vehicle/docs/evidence.md:1). The epistemic boundary and prohibition on a fault-label/quality shortcut agree with [plant.md section 7](/home/john/space_chassis/docs/deep_research/vehicle/plant.md:263). Preserve the source's structural requirement that quality assignment cannot inspect private fault state when package E is designed.
- **Research validity:** organization is tied to an agent-created artifact/routine used by another agent with a consequential decision trace. The draft does not supply a strategic dispatcher or require role formation, and retains simpler/single-agent comparisons, compute-budget accounting and failures as valid experimental outcomes. This matches the deliberate absence of assigned roles and coordination infrastructure in the chassis rules and [design.md](/home/john/space_chassis/docs/design.md:178).
- **Effort and decisions:** estimates are explicitly uncertain, overlapping effort bands, with bounded research questions and no upper bound for full breadth. Clock/pause policy, physical tolerances, prototype authorization and model expenditure remain decisions before their dependent work. The missing productive-task choice is the notable addition needed.

## Independence, evidence and limitations

I read the current chassis and vehicle AGENTS.md, the programme, vehicle ROADMAP/CONTRIBUTING/completion/evidence/release documents, relevant sections of the frozen contract, plant contract, chassis design, completeness report and selected canonical mission/domain files. I did not rely on the draft's clearance statement or a previous review disposition.

Read-only Git checks independently matched chassis HEAD `fa43b25b0fd7d88a3f5e7feb3338e190078517ce` and working vehicle HEAD `9080b0558bb90e6a291fb344430883f6a23a0e1e`. The vehicle was clean; the parent showed the modified submodule and untracked `docs/plans/`. I did not alter either repository or the programme.

The required `filigree session-context` attempt could not initialize the tracker because its database write was denied as read-only. No issue was claimed or changed. This is not a schema-mismatch diagnosis and does not block this file review.

No network, live stack, whole-suite run, mission run, paid-model call or repeated boundary reproducer was used. The author's six reproductions and 22 tests remain author-reported evidence for this review; my conclusion is about programme design. Physical-source applicability was not re-researched, remote issue state and GitHub enforcement were not verified, and the provisional quiet-coast policies were not simulated. This is not an eligible GitHub approving review or independent numerical certification. Any revised programme should record dispositions against the reviewed findings and its new artifact hash.

## Follow-up review of revised programme — 2026-10-04

Independently re-read the revised passages and checked link destinations. Revised programme SHA-256: `cad661b4d219b1028855cccbb19b0b1986187d4d552e0e82650c8306696c7c23`.

**Outcome: all four original programme-level findings are addressed. No remaining programme-design blocker found.** This accepts the proposed sequence and its treatment of unresolved work; it does not accept an implementation, establish episode feasibility or authorize execution.

| Finding | Disposition and evidence in revised programme |
|---|---|
| M1 — productive task closure | Addressed. Package F explicitly includes the productive activity and task/transfer dependencies (line 86). The episode calls the activity a proposal, names its command → physical operation → completion path, identifies stored-data dependencies and unset recorder capacity, and returns a blocked choice if no evidenced activity fits (line 108). F0 now starts with a bounded task-definition spike, including rates/capacities/initial inputs and an independent completion oracle, before its electrical/thermal questions (line 164). The two policies are explicitly feasibility hypotheses, and John's episode decision includes the new dependency (line 176). No invented productive mechanism or physical constant has been supplied. |
| m1 — declined commands | Addressed. The ledger separates implemented/intended effects from intentionally forbidden commands and accepted exclusions; forbidden commands close by rationale and refusal/no-effect evidence rather than implementation (line 126). |
| m2 — authoritative-source links | Addressed. All four links at line 18 now resolve to existing absolute local files. The assessment link also resolves. |
| m3 — B ambiguity | Addressed. The pilot budget decision explicitly requires **gate B(episode)** (line 179); H and the regression table qualify package references where needed. |

One delivery-assembly item remains at the time of this check: the new relative “companion review” link at line 188 targets `2026-10-04-vehicle-to-green-review.md`, which has not yet been created beside the reviewed programme. The evidence companion exists. Create the planned review companion or point the link to the actual independent report before delivery, and verify those companion links again at the publication location. This is a packaging item, not an unresolved programme dependency; the author has been notified.

The remaining physical/evidence questions, clock and recovery design, runtime feasibility, independent numerical acceptance, prototype exception and trial budget are properly left as future gates and decisions. Their explicit presence is not a defect in a programme at this level. No new test, repository edit, source research, network access or live run was performed for this follow-up, and the original review's limitations continue to apply.
