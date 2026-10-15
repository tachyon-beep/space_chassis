# Chassis — interface to the vehicle line

As of **2026-10-10**, `aurora-port` @ `84b1c49` and `vehicle-adoption` @ `044b5c5`. Maintained by
the Space Chassis session. **Verify against the code before trusting any line here.** The other
side is `../vehicle/interface.md`. Edits to this file are the chassis's to make. The vehicle line
proposes changes on filigree `space_chassis-93010ff54e` or by message.

## What the two lines share

Only `docs/diode-contract.md`, which is frozen. It is owned by the vehicle line, which implements
it, and a change to it needs both lines to adopt. On the chassis side, `contract/diode_probe.py`
walks an implementation through it, and `contract/fake_diode.py` is a fixture that satisfies it and
models nothing. Both are the chassis's.

## What the chassis provides the vehicle

The service as it lands with the adoption (`vehicle-adoption`; the generator is
`scripts/build_compose.py` `_vehicle`):

| | |
|---|---|
| Service | `vehicle`, profile `vehicle`. It is an alternative to the `diode` fixture profile, never both. |
| Process | `containers/serve_vehicle.sh` `exec`s **one** `tools/console.py` for every window: `--dir /opt/vehicle --diode-dir /diode --state-dir /state --scenario --seed --ring-slots --poll --cycles 0`, plus `--slug` repeated, and no `--phase`. It runs under `init: true`, so `docker stop`'s SIGTERM reaches the console. |
| Slugs | `VEHICLE_SLUGS`, which compose fills from the roster (`${VEHICLE_SLUGS:-${FLEET_SLUGS:-vehicle}}`). They are deduplicated and checked against the roster's alphabet, with globbing off. `vehicle` is served only when there is no roster. The window root is never scanned, because the slug set is the world's identity. |
| Mounts | `/diode` is the whole window image, read-write. `/state` is the 40G `vehicle_state` image, which only this service mounts. Each is a bind of its own image; neither is under the other. |
| Network | `network_mode: none` (`0ccc4cc`). |
| Hardening | `read_only: true`, `tmpfs: [/tmp]`, `cap_drop: [ALL]`, `no-new-privileges`, `mem_limit: 512m`, `restart: unless-stopped`. |
| Image | The shared agent image, `FROM python:3.13-slim@sha256:70729b46…`. The vehicle's checkpoint records the Python patch version and libc, so changing that digest is a new-world event (README "The vehicle"). |
| Operator procedures | README "The vehicle" covers the first start, restart, a deliberate new world and exit 3, from the vehicle's adoption package §3–§4. |

On `aurora-port` today (vehicle `dd79e76`), the service still runs the pre-adoption script, which
starts one console per slug and has no `/state`. That script is replaced only by the adoption
commit, never before.

## What the agents see of the vehicle

Each agent binds only its own `/diode/<slug>` and cannot write the window root.
`scripts/verify_containment.sh` holds that, plus "no agent mounts `vehicle_state`" (read host-side)
and "the vehicle binds `/diode` and `/state` and nothing else".

**Open, P1 (`open.md`):** every agent runs the same image, which bakes the whole vehicle definition
at `/opt/vehicle` (`Dockerfile.agent:76`). As user `agent`, any fleet agent can read every
`domains/*/fault_policy.yaml`, the failure chains, `plant.md` and the vehicle's design notes. It can
also run `tools/console.py --plan` to print the mission's fault schedule, and the default scenario
and seed are guessable. This was confirmed on 2026-10-10.

## Adoption status

- **Pinned:** `dd79e76`.
- **Adopting:** the merge of vehicle #21 (WP08.3, resume after a restart), when it is posted on
  `space_chassis-93010ff54e`.
- **The adoption commit holds all of these together:**
  - the pointer bump;
  - the reconciliation pins, retaken from the merge SHA (482 tests and 882 `report.refuse` sites at
    the dry-run SHA `06f08a3`);
  - the fixture copying `tools/checkpoint.py`;
  - Phase A;
  - the live vehicle checks.

  It lands on `aurora-port` as one commit.
