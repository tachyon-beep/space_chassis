> **Historical record**, copied into governance on 2026-10-10 from a session scratchpad. Paths under `scratchpad/` or `/tmp/` inside it were ephemeral and may no longer exist; line numbers refer to the commits it names. Do not edit — supersede with a new dated record.

# Chassis package: adopt the vehicle with restart continuity (vehicle WP01 + WP08 children 1, 2, 3, 4, 6)

From the Space Vehicle session, 2026-10-09. Filigree `space_chassis-93010ff54e` is the issue; this
file is the whole of what the chassis needs, and supersedes the item list in its description and the
`/state` notes in its comments.

**Status of the vehicle side.** Vehicle `main` is `64fc58c`: shared executive (WP01), checkpoint
format, `--state-dir`, durable per-cycle record, compare-point encoder, and no scenario, seed or
designer commentary in any window. **Resume after a restart (vehicle #21, WP08 child 3) is being
built now.** The pointer this package adopts is **the merge commit of #21**; the vehicle session
will post that SHA on the filigree issue when it merges. Everything below except the pointer bump and
the pinned counts can be prepared against `64fc58c` today: the chassis-facing interface (flags,
files, exit codes) does not change in #21 except as stated in §3.

Ownership rule (aurora-port spec §8, as rewritten): the chassis owns the vehicle service's
deployment — compose entry, networks, mounts, serve script. The vehicle states its needs; it does not
edit chassis files.

---

## 1. What the vehicle needs from its deployment

| Need | Value |
|---|---|
| Network | none (done: `network_mode: none`, aurora-port `0ccc4cc`) |
| Processes | **one** `tools/console.py` serving every slug (`--slug a --slug b …`). The executive takes an exclusive lock; a second process on the same state directory exits 3 |
| Diode | the whole window root, read-write, at `/diode` (unchanged) |
| Private state | a writable directory at `/state`, passed as `--state-dir /state` |
| Memory | measured at `64fc58c`: 68 MB peak RSS for 11 windows with full 300-slot rings. `mem_limit: 512m` is ample |
| Disk, `/state` | the record is ≈ 365 + 27 × windows bytes per tick, plus a few KB on commanded ticks; measured 0.72 KB/tick at 11 windows. Two checkpoint generations, ≈ 0.3–0.5 MB each. Nothing is pruned (the record is the replay trace). **40 GB** for a 192 h mission |
| Disk, `/diode` | measured ≈ 1.4 MB per window with a full 300-slot ring (unchanged from today) |

## 2. Chassis changes, one commit

1. **Pointer.** `docs/deep_research/vehicle` → the #21 merge SHA (posted on the issue).

2. **`containers/serve_vehicle.sh`: one process, a fixed slug set, `exec`.**
   - Build the slug list from `VEHICLE_SLUGS` alone (compose already passes `${VEHICLE_SLUGS:-${FLEET_SLUGS:-vehicle}}`), deduplicated. `vehicle` is served **only** when no roster is given (that default), never added to a fleet's set: under the shared executive every window commands the one world, so a `vehicle` window beside the fleet's is a command authority no agent holds, and a probe run against it by hand would actuate the vehicle the fleet is flying. (Corrected 2026-10-09; the first version said "plus `vehicle`".) Order does not matter — the world record sorts the set — but the set must be the same at every restart.
   - **Drop the scan of `$DIODE_DIR/*` for slugs.** The slug set is part of the world's identity in
     the checkpoint: a resume whose slug set differs from the checkpoint's refuses (exit 3). A stray
     directory in the diode root would change the set and turn every restart into a crash loop.
   - Pass every slug to one `console.py`, with `--state-dir /state` added to today's flags
     (`--dir`, `--diode-dir`, `--scenario`, `--seed`, `--ring-slots`, `--poll`, `--cycles 0`). Do
     **not** pass `--phase` (a resume takes the phase from the checkpoint; naming one that disagrees
     refuses).
   - `exec` the console instead of backgrounding and `wait`ing, so `docker stop`'s `SIGTERM` reaches
     the vehicle directly. Remove the `PIDS`/`trap` machinery.
   - Rewrite the header comment: "one console per slug" and the roster-from-directory paragraph are
     now wrong.

3. **A private `/state` volume for the vehicle (`scripts/volume_images.py`, `scripts/build_compose.py`).**
   - One image, not per-agent: e.g. `Kind("vehicle_state", "40G", "SPACE_VEHICLE_STATE_SIZE", SHARED-or-a-new-single-scope, (("vehicle", "/state", False, ""),))`, mounted **only** on the `vehicle` service, read-write.
   - Never under the diode volume and never a second bind of it (the vehicle's containment check is
     by path and the diode directory's inode; a second bind of the same volume would pass it).
   - **No agent, monitor, review panel or recorder mounts it.** It holds the lock, `serves.json`, the
     journal segments and the checkpoints: hashes, lineage and hidden truth.
   - Owned by uid 1000 (the vehicle runs as `agent`, `Dockerfile.agent:96`). The vehicle requires
     every record file it appends to be owned by its own uid, and makes them `0600` itself; the
     directory's mode is not checked.
   - `read_only: true` and `tmpfs: [/tmp]` stay; `/state` and `/diode` are its only writable mounts.
   - `.env.example` and `prepare_host.sh`'s allocation note: the host's volume-image total grows by
     40 GB (from ≈ 137 GB for ten agents).

4. **Containment and probes.**
   - The diode root now carries one vehicle dotfile, `.executive.json` (the windows' copy of the
     checkpoint's identity, rewritten every publication). With `--state-dir`, `.executive.lock` is in
     `/state`, not the diode root. Anything that lists the diode root must tolerate `.executive.json`.
   - `scripts/verify_containment.sh`: add that no agent can see the vehicle's `/state`, and that no
     agent can write the diode root (the per-slug mounts, `adf38d6`, already make it so).
   - Note, not a change: agents and the vehicle share uid 1000, so the separation is by mount alone.

5. **Reconciliation pins** (`tests/test_vehicle_reconciliation.py`, `docs/deep_research/integration/reconciliation/README.md`).
   - The vehicle referee's test count (433 at `64fc58c`; #21 adds tests) and the `report.refuse`
     call-site count (881 at `64fc58c`) — take both from the adopted SHA, not from this file.
   - `test_the_vehicle_is_servable_from_the_compose_file`: hold the new shape — one process, the
     `/state` mount, no slug scan, no network.
   - This closes vehicle issue #16 once it lands.

6. **Docs.** `CLAUDE.md`'s table row for the vehicle (add `/state`, "one process for every window"),
   aurora-port spec §8's requirement list, and the operator procedures in §4 below wherever the
   operator runbook lives.

## 3. What #21 changes in the vehicle's behaviour (the contract this package relies on)

| Situation | At `64fc58c` (today) | After #21 |
|---|---|---|
| First start, empty `/state`, empty windows | binds a new world, exit 0 when stopped | same |
| Restart (container restart, crash, `docker kill`, host reboot) | **exit 3**: "a verified checkpoint … resuming it is WP08 child 3" — crash loop under `restart: unless-stopped` | **resumes**: same `world_id`, same tick sequence, `boot_id` changes, `met_s` and each window's `seq` continue; every command whose cycle was recorded has exactly one result (a batch claimed in the cycle the crash interrupted, before its record, is lost with no result — `docs/diode-contract.md:67–72`, "a crash mid-batch … never replays it"); the downtime is journaled and mission time does not advance while down (ADR 0002 F1). Restart work is bounded by one checkpoint interval (50 ticks), not by how long the vehicle had run |
| Restart with a different `--scenario`, `--seed`, `--ring-slots` or slug set than the world was bound with | — | exit 3, naming the flag and both values |
| Restart after the image was rebuilt with a changed `tools/plant.py`, `tools/console.py` or `tools/faults.py`, a different Python, or a different platform | — | exit 3: the checkpoint is **incompatible** (it records an engine hash of those three files, the Python version and the platform). A vehicle pointer bump mid-mission therefore means a new world |
| Corrupt current checkpoint, previous generation verifies | exit 3 | **resumes** from the previous generation; the record covers the gap, so it reaches the same tick (ADR 0002 K2) |
| Both checkpoint generations corrupt, or the record cannot continue the checkpoint | exit 3 | exit 3, naming the file and the check |
| A start with no checkpoint on a `/state` that already holds a record | — | exit 3: one state directory is one world's |
| `--max-batch` named differently on a restart | — | the new value applies, journaled |
| `--closed-interlock` on a restart | — | **added** to the saved set, journaled; a restart can trip an interlock but never clears one (omitting the flag does not un-trip it). Clearing one is a new world until WP05 |

Revised 2026-10-09 after #21's design review (rows marked above). No new flag is required of the chassis by #21. Exit codes are 0 (stopped) and 3 (refused, with one
sentence on stderr saying why and what clears it).

**Not in this package (later vehicle children; each will come as its own small chassis delta):**
- #28 (child 10): graceful `SIGTERM` (finish the cycle, checkpoint, exit 0); fallback to the previous
  checkpoint generation when the current one is corrupt; `--new-world` as the operator's one-shot
  recorded escape. Until then a `SIGTERM` ends the process abruptly, which resume handles (it costs
  at most the cycles since the last durable record, and the record recovers those).
- #23 (child 5): the clock. `DIODE_POLL_SECONDS` is retired and `m`, `k`, `N` become required
  flags; a stack that names none refuses by design.
- #27 (child 9): the operator pause control, not reachable from any `/diode/<slug>/`.
- `scripts/status.py` reading the checkpoint header (never truth) — optional, ADR 0002 H.

## 4. Operator procedures

- **First start after adoption: a new world on clean windows.** Windows written by the vehicle the
  chassis runs today (`dd79e76`, per-slug processes) carry that vehicle's records; clear
  `volumes/diode/data/*` (including `.executive.json`) and start with an empty `/state`.
- **Restart: nothing to do.** `restart: unless-stopped` brings it back and it resumes.
- **Deliberate new world** (a new mission, a changed roster, scenario or seed, a vehicle bump, or an
  exit 3 crash loop): stop the `vehicle` service; move `/state`'s contents and the window directories'
  contents aside (keep them: they are the previous world's record); start. After #28 this becomes a
  one-shot `docker compose run --rm vehicle … --new-world`, which keeps the record and writes the
  discontinuity into it.
- **Diagnosing an exit 3:** `docker compose logs vehicle` — the last line names the file, the check
  and what clears it.

## 5. Acceptance (chassis evidence for the adoption commit)

1. Full chassis suite green, including the reconciliation pins at the adopted SHA;
   `docker compose --profile fleet config -q` and `--profile vehicle config -q` parse.
2. `python3 scripts/volume_images.py check` reports the vehicle's `/state` image mounted and ready.
3. Live: start the vehicle with the roster; every agent's `/diode/<slug>/state.json` advances, and
   `executive.world_id` is the same in every window.
4. Live restart: note `executive.tick` and `world_id` in one window; `docker kill` the vehicle
   container; after the restart policy brings it back, the same `world_id`, the tick sequence
   continuing (no reset to 0), and a new `boot_id` in the frames. No window lost a result.
5. Containment: `sh scripts/verify_containment.sh --all` passes with the new checks; no agent
   container can list `/state` or write `/diode/`'s root.
6. `docker stop vehicle` stops it within the stop grace period (no orphaned console processes).
