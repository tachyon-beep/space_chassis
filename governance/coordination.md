# Coordination between the streams

As of **2026-10-15**, `tachyon-beep/space_chassis` `main` @ `0036b88`. Owned by the governance
stream. **Verify against the code before trusting any line here.**

The test-slot log that filled this file from 2026-10-11 to 2026-10-12 (grants `SPACE-20261011-*`,
holds, releases, host admission checks) is closed and kept verbatim in
[`records/2026-10-11-coordination-slot-log.md`](records/2026-10-11-coordination-slot-log.md), with the
master plan it indexed ([`MASTER_GOVERNANCE_PLAN.md`](MASTER_GOVERNANCE_PLAN.md)). Neither binds any
more (`decisions.md` D2).

## Who works here

| stream | builds | folder | branches |
|---|---|---|---|
| vehicle | the mission simulator behind the window | `vehicle/` | `vehicle/<topic>` |
| aurora (the chassis line) | the world the fleet lives in, and the vehicle's deployment | `aurora/` | `aurora/<topic>` |
| governance | coordination, status and decision records; the programme documents in `docs/vehicle-completion/` | `governance/` | `governance/<topic>` |

John is the owner and operator. Emmy was appointed programme lead on 2026-10-10
(`MASTER_GOVERNANCE_PLAN.md` header) and that appointment stands; the governance stream does the
coordination work in the repository and reports to John and Emmy alike.

## Channels

| channel | for |
|---|---|
| GitHub issues on `tachyon-beep/space_chassis`, labelled `stream:<name>` | Work items, cross-stream requests, and acceptance evidence. The channel of record (`decisions.md` D10). |
| Pull requests on `tachyon-beep/space_chassis` | Every change. The PR names its issue; the merge SHA is the only SHA that counts for adoption. |
| `governance/` | The standing picture: `status.md` for the programme, `snapshot.md` and `open.md` per stream, and the decision logs. |
| The Space Aurora project threads | Conversation with John. Anything decided there is written to an issue or a decision log. |
| filigree (John's machine only) | A local view for sessions on that machine. Not the record between streams. |

## Rules

- **Ownership follows the stream, never the file's location.** The chassis owns the vehicle's
  deployment (compose entry, networks, mounts, `serve_vehicle.sh`, the vehicle image) even though it
  serves the vehicle. The vehicle states its needs in `vehicle/interface.md`.
- **Every task has one lead; there are no shared tasks** (John, 2026-10-10). The lead sets the rule;
  the other stream follows it on its side. When the lead is unclear, settle it on the issue before
  either starts, and ask John if the two disagree.
- **A request goes where its receiver reads.** A requirement written into one stream's spec and
  addressed to another is not delivered (2026-10-09, chassis spec §8). Open an issue labelled for the
  receiving stream, and name it in the receiver's `interface.md` if the boundary moves.
- **The window contract** (`docs/diode-contract.md`) is led by the vehicle: it writes the sentence, and
  the change takes effect when the chassis adopts it with the fixture (`aurora/contract/fake_diode.py`),
  the brief and `docs/brief-claims.md` in one commit.
- **Adoption is by exact SHA.** The vehicle posts the merge SHA of the change to adopt on the adoption
  issue; the chassis adopts it in one commit with the reconciliation pins and its live checks. Since
  2026-10-15 the vehicle is in this repository, so "adopting" means the chassis's pins, image and live
  checks catch up with `vehicle/` at a named commit.
- **One owner per branch and per working path.** Give every scratch path a session-unique suffix.
  Two sessions resuming one conversation share a scratch directory and will collide; close the
  duplicate (2026-10-10, both gates void).
- **Owner decisions go to John with a recommendation**, and only those `practice.md` lists as his.
  Everything else a stream decides and records, open to his revision.
