# Coordination between the lines

*(Draft input from the vehicle line for the chassis line to edit and own.)*

## Channels

| channel | for |
|---|---|
| filigree `space_chassis-93010ff54e` (chassis tracker) | the adoption of a vehicle by the chassis: requirements, packages, merge SHAs, dry-run results — the durable cross-line record |
| GitHub issues on `tachyon-beep/space_vehicle` | vehicle work packages and their acceptance |
| session messages (SendMessage between local Claude sessions) | fast coordination; anything decided there is written to a durable channel above or to `governance/` |
| `governance/` | the standing picture each line maintains |

## Rules

- **Ownership follows the line**, never the file's location. The chassis owns the vehicle service's
  deployment (compose entry, networks, mounts, serve script, image) even though it serves the vehicle;
  the vehicle states its needs in `vehicle/interface.md` and does not edit chassis files.
- **A request goes where its receiver reads.** A requirement written into one line's spec and addressed
  to the other line is not delivered (2026-10-09: chassis spec §8 asked the vehicle line to keep its
  service off worknet while only chassis artefacts placed it there; nothing changed until it was routed
  to the chassis as a chassis action). Route cross-line requests to the shared filigree issue or a
  message, and to the owner's `interface.md`.
- **Adoption is by exact SHA.** The vehicle posts a merge SHA on the adoption issue; the chassis adopts
  that SHA in one commit with the pointer, the pins and its live checks. A dry run against an unmerged
  head is welcome evidence and never a landing.
- **One owner per branch and per working path.** Before two sessions touch one package, agree the owner
  by message. Give every scratch path a session-unique suffix. Two resumes of one conversation share a
  scratch directory and will collide (2026-10-10: two gates shared one worktree and evidence directory
  and both runs were void); close a duplicate resume.
- **Owner decisions go to John** with a recommendation; a line may decide within John's standing
  delegation and records it as "coordinator" in its `decisions.md`, open to his revision.
