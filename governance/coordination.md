# Coordination between the lines

As of **2026-10-11 10:04 AEDT**, `tachyon-beep/space_chassis` `aurora-port` @ `61355752`. Owned by the chassis
line, from a draft by the vehicle line. **Verify against the code before trusting any line here.**

## Programme leadership — 2026-10-10

**Emmy is programme lead now; both Claude line owners continue their assigned work.** John's
08:48 UTC (19:48 AEDT) instruction, relayed through coordinating chat
`01a12334-35ad-748b-99eb-2d3a16598084`, authorises taking over as lead and working through the
computer and this governance folder. The quotation, provenance and bounded documentation scope
are recorded in [MASTER_GOVERNANCE_PLAN.md](MASTER_GOVERNANCE_PLAN.md). Space Aurora remains one
programme, two equal project teams and one product, with one lead team per task and separate
repositories; no restructuring is authorised.

Programme leadership is distinct from a future transfer of exclusive engineering/operational
custody. That transfer still requires the master plan's readiness review, John's explicit
confirmation that both designated owners are offline, final delta reconciliation and Emmy's
acceptance. None has been declared here; recognising leadership requires no owner shutdown.

For this documentation checkpoint, owner contact is handled by the coordinating chat's separate
native-browser worker. The documentation writer records proposed follow-ups in the master plan
and sends no duplicate owner instructions. Line-owned reports remain theirs to write; reading
them does not ratify a handover or change their status. Emmy's explicit reviews in master-plan
sections 9–10 and 13 mark **AUR-GOV-02 v1, AUR-GOV-03 v1.1 and AUR-GOV-07 v1 SUFFICIENT**.
**AUR-GOV-04 v1.2 requires CORRECTIONS**: its claim that `pending.json` is absent from the
contract contradicts `docs/diode-contract.md:35`. The existing Chassis Code claimant owns the
bounded addendum, also correcting its unresolved-precedence framing because practice explicitly
defers to AGENTS.md; the browser worker routes it. Both report versions are verified published
through `613557528ffc42d4ea8d4ae0a3b3a2c453825ffa`. AUR-GOV-06 still waits for the corrected
input and separate assignment. These verdicts do not accept the product or transfer custody.
Owner reports remain unchanged by Emmy's documentation writer. Section 11's coordinator-only
validation/publication authority did not waive any gate; this review ran no tests or commits.
Section 12 records the completed checks: root 569 passed, lint/format passed, but the full suite
failed its vehicle malformed-batch contract probe (1 failed, 1722 passed). The coordinator files
remain uncommitted and unpublished pending resolution of that required gate. Section 13 records
the owner's root-only report gates and no-test addendum disclosure separately from content
acceptance: practice expressly defers to AGENTS.md, so it cannot waive the whole-suite rule.
John's explicit, scoped gate decision is needed to permit documentation-only durability while
that failure remains; otherwise the existing gate stands. No exception has been inferred.
The existing index is preserved, with this review recorded only in the working coordinator files.

## Channels

**Morning resumption (master §14):** John's relayed 23:00 UTC instruction resumes the existing
Space owners alongside ELSPETH. AUR-GOV-04 working v1.3 now closes both review findings and is
SUFFICIENT for content, but remains unpublished. Vehicle #21/PR #41 merge `f443996` and Chassis
Phase B index `b29bf8af` were verified; three Phase B review findings remain. Chassis's next
increment is that correction pass; Vehicle's is #39 design v2 with the two product decisions
still explicit. **10:07 AEDT update:** Emmy reports an authenticated cloud browser worker has
opened the existing Vehicle Claude session and is handling resume instructions for both owners.
The earlier Velma browser failure is a local route limitation, not global unavailability.
That worker is the sole sender; acknowledgments will arrive through Emmy. Neither owner is
replaced, and no duplicate send is made here. Both #39 product decisions have been asked of John
and remain PENDING. ELSPETH's owner permits one bounded Space test
selection with at most two workers total across both lines; the slot is unused, with nice 19
proposed and coordination required before any increase. Its qualification remains untouched.
No test/build was launched.
The full-suite gate and all reserved operator decisions remain intact. Earlier entries above
describe the prior checkpoint; section 14 is the current resumption record.

**Shared test slot — 10:16 AEDT (master §15):** Emmy confirms both existing owners are active.
Chassis is fixing Phase B, then refreezing/reviewing; Vehicle is preparing conditional #39 design
v2. Slot FREE, not granted: one selection, two workers total, nice 19; owner-facing grants route
only through Emmy/browser after readiness and a fresh capacity check. A 30–40 minute full suite
is allowed validation time. Live/build is separately HELD: current smoke sidecars/stubs, builder
and host driver lack aggregate CPU/RAM bounds; both session fixtures can overlap. Section 15
records per-container limits, sequential phase ordering and concrete resource-control options
requiring a budget/scope decision. Required tests remain required. No tests or builds started here.

| channel | for |
|---|---|
| filigree `space_chassis-93010ff54e` (the chassis's tracker) | Adopting a vehicle: requirements, packages, merge SHAs, dry-run results. This is the durable record between the lines. Use the MCP tools or the CLI (`filigree add-comment --actor <line> …`). |
| GitHub issues on `tachyon-beep/space_vehicle` | The vehicle's work packages and their acceptance. |
| session messages (`SendMessage` between local Claude sessions) | Fast coordination. Anything decided there is written to a durable channel above, or to `governance/`. |
| `governance/` | The standing picture each line maintains. |

**Addressing a session.** A session's socket path changes when it restarts or is resumed. Call
`ListAgents` before messaging, and reply to a message's `from` address. Two sessions can carry the
same name (2026-10-10: two "Space Vehicle" sessions). When that happens, send to both, or ask which
one owns the work.

## Rules

- **Ownership follows the line, never the file's location.**
  - The chassis owns the vehicle service's deployment (compose entry, networks, mounts, serve
    script, image), even though that deployment serves the vehicle.
  - The vehicle states its needs in `vehicle/interface.md` and does not edit chassis files.
  - The chassis does not edit the vehicle repository, or the vehicle line's working tree in the
    chassis checkout.
- **Every task has one lead; there are no shared tasks** (John, 2026-10-10). The lead team sets the
  rule. Where the other team has to do the same thing on its side, it follows the lead's rule and
  does not set its own. When the lead is unclear, settle it by message before either team starts,
  and ask John if the two disagree.
- **A request goes where its receiver reads.** A requirement written into one line's spec and
  addressed to the other line is not delivered. On 2026-10-09, chassis spec §8 asked the vehicle line
  to keep its service off worknet, while only chassis artefacts placed it there; nothing changed until
  the request was routed to the chassis as a chassis action. Route cross-line requests to the shared
  filigree issue or a message, and to the owner's `interface.md`.
- **Adoption is by exact SHA.**
  - The vehicle posts a merge SHA on the adoption issue.
  - The chassis adopts that SHA in one commit, together with the pointer, the pins and its live
    checks.
  - A dry run against an unmerged head is welcome evidence (2026-10-10, comment 40), but it is never
    a landing, and the adoption branch stays parked until the SHA is posted.
- **One owner per branch and per working path.**
  - Before two sessions touch one package, agree the owner by message.
  - Give every scratch path a session-unique suffix.
  - Two resumes of one conversation share a scratch directory and will collide. On 2026-10-10 two
    gates shared one worktree and evidence directory, and both runs were void. Close a duplicate
    resume.
  - The chassis works in its own worktree under `.claude/worktrees/`, with its own vehicle clone
    (`chassis/practice.md`).
- **The vehicle line's files under `governance/vehicle/`** are written by the vehicle line and
  committed verbatim by the chassis. That happens on the chassis's next commit to `aurora-port`, or
  sooner when the vehicle line asks.
- **Owner decisions go to John** with a recommendation. A line may decide within John's standing
  delegation; it records the decision as "coordinator" in its `decisions.md`, open to his revision. A
  decision that reaches a session through the other line is relayed, so the receiving line says so to
  John (2026-10-10: the base-image digest pin).
