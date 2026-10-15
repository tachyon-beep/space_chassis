# Coordination between the lines

As of **2026-10-10 20:30 AEDT**, `tachyon-beep/space_chassis` `aurora-port` @ `1effa040`. Owned by the chassis
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
them does not ratify a handover or change their status. Emmy's explicit review in master-plan
sections 9–10 marks **AUR-GOV-02 v1 SUFFICIENT** and **AUR-GOV-03 v1.1 SUFFICIENT**, with exact
report versions, closed correction findings and carried evidence limits. Section 11 now claims
AUR-GOV-04 for the existing Chassis Code owner and AUR-GOV-07 for the existing Vehicle Code owner;
AUR-GOV-06 waits for those inputs and separate assignment. The browser worker routes the claims.
These assignments do not accept the product or transfer custody. Owner reports remain unchanged
by Emmy's documentation writer. Required validation and coordinator-only commit/publication are
now authorised; section 11 supersedes the earlier validation-scope blocker without waiving gates.
Section 12 records the completed checks: root 569 passed, lint/format passed, but the full suite
failed its vehicle malformed-batch contract probe (1 failed, 1722 passed). The coordinator files
remain uncommitted and unpublished pending resolution of that required gate; the claims remain
recorded locally for the browser worker to route.

## Channels

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
