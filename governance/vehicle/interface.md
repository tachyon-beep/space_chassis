# Vehicle — interface: what the vehicle offers, and what it needs

As of **2026-10-10**, `tachyon-beep/space_vehicle` main @ `64fc58c` (rows marked **#21** describe the
resume branch `codex/wp08-resume`, not yet merged). Owned by the vehicle line; the chassis side is
`../chassis/interface.md`. Either line may propose an edit to the other's interface file through
filigree `space_chassis-93010ff54e` or a message; the owner decides. **Verify against the code before
trusting a row** — `tools/console.py`'s `main` and `docs/diode-contract.md` are authoritative.

## The contract it implements

`docs/diode-contract.md` (in the chassis repository; owned by the vehicle line, frozen — a change
needs both lines to adopt it). One directory per agent, `/diode/<slug>/`:

| file | direction | the vehicle's obligation |
|---|---|---|
| `console.json` | agent → vehicle | claimed (read and emptied) before anything runs; a crash mid-batch loses the rest of the batch, never replays it (contract §2.2) |
| `output/<stamp>_<slug>_<cmd>.txt` | vehicle → agent | exactly one result per command whose cycle was recorded, refusals included |
| `state.json` | vehicle → agent | the mirror, rewritten every cycle whether or not anything was submitted |
| `telemetry/NNN.json` | vehicle → agent | a bounded ring; losses counted in `state.json`'s `ring` |
| `HELP.md`, `README.md` | vehicle → agent | generated from the configuration; the protocol only (see below) |
| `pending.json` | vehicle-internal | a published copy; never read back as authority |

**What a window never carries** (owner's rule, 2026-10-09: information and action management are the
agents' to manage): no scenario, no seed, no fault plan, no truth (`plant.md` §7), no designers'
diagnostic commentary. Enforced by referee tests on the generated README and on window JSON; `HELP.md`
verb texts still carry some commentary (#35).

## Process interface

**Command line the chassis runs** (one process for every window):

```
python3 /opt/vehicle/tools/console.py --dir /opt/vehicle --diode-dir /diode --state-dir /state \
    --slug <s1> --slug <s2> ... --scenario <posture> --seed <n> --ring-slots 300 --poll 5 --cycles 0
```

- `--slug` repeated, one per agent; the set is fixed for a world. Serve `vehicle` only when there is no
  roster — never beside a fleet.
- Do **not** pass `--phase` (a resume takes it from the checkpoint). `--max-batch` and
  `--closed-interlock` default to unset; on a restart a new `--max-batch` replaces the saved one and a
  `--closed-interlock` is added to the saved trips (a restart never clears one) — **#21**.
- `--poll` is retired by WP08.5 (#23), which makes `m`, `k`, `N` required flags.

**Exit codes:** `0` stopped cleanly; `3` refused, with one stderr sentence naming what and what clears
it. Anything else is a crash.

**Files it writes:**

| where | what |
|---|---|
| `/diode/.executive.json` | the windows' copy of the world's identity (rewritten every publication) |
| `/diode/<slug>/…` | the six files above |
| `/state/.executive.lock` | the exclusive lock (one executive per state directory) |
| `/state/serves.json` | which diode directory this state directory serves |
| `/state/journal.<boot_id>.jsonl` | the durable per-cycle record, one segment per boot, never pruned |
| `/state/checkpoint.json`, `checkpoint.prev.json` | two generations, every 50 ticks — **#21** |
| `/state/checkpoint.rejected.<boot>.json` | a refused generation moved aside on fall-back — **#21** |

## Restart behaviour (**#21**; today on main a start beside a verified checkpoint exits 3)

| situation | behaviour |
|---|---|
| restart (crash, `docker kill`, reboot, `docker stop`) | resumes: same `world_id`, tick continues, `boot_id` changes, `met_s` and each window's `seq` continue; mission time frozen while down (F1); work bounded by the rows since the last checkpoint |
| a scenario, seed, ring size, phase or slug set different from the world's | exit 3 naming the flag and both values |
| current checkpoint corrupt, previous verifies | resumes from the previous generation (K2) |
| both unusable, or the record cannot continue the checkpoint, or a record file that cannot be verified | exit 3 naming the file and the check |
| no checkpoint but `/state` holds a record | exit 3: one state directory is one world's |
| image rebuilt with a changed engine (corpus files or `plant.py`/`console.py`/`faults.py`), Python version (full, including patch), or platform (OS, machine, libc) | exit 3: the checkpoint is incompatible → a new world |

A deliberate new world (until `--new-world`, #28): stop the service, archive `/state` whole, each
window's contents and `/diode/.executive.json`, start.

## What the vehicle needs from its deployment

| need | value | why |
|---|---|---|
| network | **none** | its only interface is the volume; on a network it is an observable host |
| processes | **one** console for every slug | the executive is the one world; a second process refuses on the lock |
| `/diode` | the whole window root, read-write, for the vehicle alone | it writes every window and the root record |
| agent mounts | each agent sees only its own `/diode/<slug>/` | the root record, the lock and OS-level attribution assume it; the kept root-record refusals assume it |
| `/state` | private, writable, its own volume (never the diode volume or a second bind of it), uid 1000, **40 GB**, on disk | lock, journal, checkpoints: hashes, lineage and hidden truth |
| no other mount of `/state` | no agent, monitor, review panel or recorder | it holds what the fleet must not see |
| memory | 512 MB is ample (68 MB measured at 11 windows) | |
| **agents must not see `/opt/vehicle`** | today they can (the shared image bakes it) — owned by the chassis, P1 in `../chassis/open.md` | the configuration, fault policies and `--plan` reveal the fault schedule |
