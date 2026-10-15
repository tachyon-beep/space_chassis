# Coordination between the lines

As of **2026-10-10**, `tachyon-beep/space_chassis` `aurora-port` @ `84b1c49`. Owned by the chassis
line, from a draft by the vehicle line. **Verify against the code before trusting any line here.**

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
