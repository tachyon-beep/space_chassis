# Chassis — open items

As of **2026-10-10**, `space_chassis` `aurora-port` @ `84b1c49`. **Verify against the code and
filigree before trusting any line here.** Filigree (`filigree list --status open`) is authoritative
for issues; this file holds the ones that steer the line, and the questions for John.

## P1

1. **The fleet can read the vehicle's hidden design.**
   - **What:** every agent service runs `space-chassis-agent`, which bakes the vehicle at
     `/opt/vehicle` (`Dockerfile.agent:76`), readable by user `agent`. That includes every
     `domains/*/fault_policy.yaml`, the failure chains, `plant.md` and the vehicle's design notes.
     `python3 /opt/vehicle/tools/console.py --dir /opt/vehicle --plan --scenario nominal --seed 0`
     prints the mission's fault schedule: 62 armed faults with their onset times. The default
     scenario and seed are guessable. Confirmed 2026-10-10 against the smoke image. It breaks John's
     principle that information management is the agents' job.
   - **Recommended fix:** two build targets in `Dockerfile.agent`. The agent target carries no
     `/opt/vehicle`; the vehicle target adds `/opt/vehicle` and `serve_vehicle.sh`. Compose gives
     each service its target, and a test asserts that no agent image contains `/opt/vehicle`. Also
     keep the scenario and seed out of the agents' reach.
   - **Owner:** chassis. **Needs John's go** (it changes the image topology).
2. **Adopt the vehicle at #21's merge (plan 7 Phase B).** This waits for the merge SHA on
   `space_chassis-93010ff54e`. It carries over the dry-run harness (`9f6a20b`, `76ea7ce`, `397d032`
   on `phase-b-dryrun`), retakes the pins from the merge SHA, and lands as one commit on
   `aurora-port`.
3. **Land the port on `main`.** `aurora-port` is 100 commits ahead. The merge is John's call. When
   it lands, close the superseded filigree issues. They are listed in epic `space_chassis-c8e27e645c`
   comment 30, with the four the spec names in §7: `835d551619`, `a5c2a27876`, `3cb643af8e`,
   `833a01f2de`.

## Questions for John (spec §10)

- **The cap figures** (§10.3): per agent per hour, the fleet per hour, and the declared-stream pools.
  Also which models the stream allow lists permit; both ship empty in `.env.example`.
- **The transcript mount** (§10.4): whether each agent mounts its own transcript read-only. The
  default is no.
- **Scheduling the journal**: `scripts/journal.py --every 300` has no service or cron yet.
- **The pinned base on `aurora-port`**: the pin is on `vehicle-adoption` and lands with the
  adoption. Say if you want it earlier.

## Other open items

- **Long-life follow-ups still open** (epic `space_chassis-c8e27e645c`): `3c98f068b5` and
  `deae4f4801` are addressed and await closing. The agents'-business items stay open, as recorded in
  comment 30.
- **Deferred minors** are listed per plan in `docs/superpowers/ledgers/plan-{5,6,7}-ledger.md`.
  Examples: the slug-validation tests exercise only one check; the vehicle bind check ignores named
  volumes.
- **Not this line's, and left alone:**
  - the untracked `docs/plans/` in the main checkout (John's earlier rule: do not touch);
  - the modified filigree skill files under `.agents/` and `.claude/`;
  - the stale `/tmp/head_tree` worktree.
- **This session's filigree MCP connection fails**; the CLI works.
