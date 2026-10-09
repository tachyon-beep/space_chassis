# Vehicle Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the chassis side of adopting the vehicle with restart continuity, so it lands as one adoption commit when the vehicle's #21 merges.

The vehicle side is filigree `space_chassis-93010ff54e`, comment 37; its package is `.scratch/vehicle-adoption/PACKAGE.md`.

**Architecture:**
- One `console.py` process serves every window. It takes its slug set from `VEHICLE_SLUGS` alone, and its private state from a vehicle-only `/state` volume image.
- Phase A, which is everything except the pointer and the pins, is built and reviewed now. It runs against vehicle `main` `64fc58c`, in the worktree `.claude/worktrees/vehicle-adoption` on branch `vehicle-adoption`.
- Phase B lands it. On the #21 merge SHA, it adds the pointer bump, the reconciliation pins and the live restart acceptance. Everything is then squashed into one commit on `aurora-port`.

**Tech Stack:** POSIX sh, Python 3.12 standard library, pytest, docker compose.

**Spec:** `docs/superpowers/specs/2026-10-09-aurora-port-design.md`. §5 holds the filesystem and the binds. §8 says the chassis owns the vehicle's deployment and the vehicle states its needs.

## Global Constraints

- **Deconfliction with the Space Vehicle session** (John, 2026-10-09: "I need both of you working"):
  - Never touch `/home/john/space_chassis/docs/deep_research/vehicle`, nor any `codex/*` branch or worktree in the shared module git dir.
  - Never run `git submodule update`.
  - The worktree's vehicle is its own clone (`--reference --dissociate`).
- **Nothing reaches `aurora-port` before the #21 SHA.** A `--state-dir` serve script on `dd79e76` would refuse: that vehicle has no checkpoint resume, so any restart is exit 3.
- **The slug set is the world's identity:**
  - `VEHICLE_SLUGS` only, deduplicated; order does not matter.
  - `vehicle` is served only when no roster is given (compose's fallback). It is never added to a fleet's set.
  - Never a scan of the diode root.
- **The vehicle's `/state`:**
  - one image, `vehicle_state`, 40G, `SPACE_VEHICLE_STATE_SIZE`;
  - mounted read-write by the `vehicle` service alone;
  - never under the diode image and never a second bind of it;
  - uid 1000.
- **Operator-side code is standard library only.** Tests are named as sentences and never skip for a missing docker.

## Review Focus

1. **A stray directory, or a roster that names `vehicle`, in the window root.** The slug set stays the roster's, deduplicated, and a stray directory never joins it. Task 1 tests it.
2. **`docker stop` reaching the console.** The script `exec`s, so the console is the container's process, and there is no background child left orphaned. Task 1 tests it: the console's parent is the script's parent.
3. **Any service but the vehicle mounting `vehicle_state`.** This includes the review panel and the monitor, which mount every fleet role's images. Task 2 tests it over the whole generated compose file.
4. **The volume plan and its stated totals drifting.** Today it is 137.3125G; it becomes 177.3125G. Task 2 tests it.
5. **A fleet stack that expects `/diode/vehicle`.** Tasks 1 and 3 test it: no chassis check expects it in a roster stack.

---

### Phase A: now, against 64fc58c

### Task 1: One console for every window (`containers/serve_vehicle.sh`)

**Files:**
- Modify: `containers/serve_vehicle.sh`
- Modify: `tests/test_vehicle_reconciliation.py` (`test_the_vehicle_is_servable_from_the_compose_file`, the script-run half)

**Interfaces:**
- The script's environment:
  - `DIODE_DIR` (/diode);
  - `VEHICLE_DIR` (/opt/vehicle);
  - `VEHICLE_STATE_DIR` (/state; new);
  - `VEHICLE_SLUGS` (comma-separated; empty means `vehicle`);
  - `VEHICLE_SCENARIO`, `VEHICLE_SEED`, `DIODE_POLL_SECONDS`, `VEHICLE_RING_SLOTS` (unchanged).
- The script execs `python3 $VEHICLE_DIR/tools/console.py` with these flags:
  - `--dir`, `--diode-dir`, then `--slug S` for each slug;
  - `--state-dir $VEHICLE_STATE_DIR`;
  - `--scenario`, `--seed`, `--ring-slots`, `--poll`, `--cycles 0`;
  - no `--phase`.

- [ ] **Step 1: Failing tests.** Rewrite the script-run half. The stub `console.py` writes `{"argv": ..., "pid": os.getpid(), "ppid": os.getppid()}` to `<diode>/served.json`, then sleeps.
  - `--slug` is repeated once per slug, giving the roster `mackerel,cinnabar,scabious` (`VEHICLE_SLUGS`).
  - A stray `diode/stray/` directory and a file in the root are not served.
  - `vehicle` is not served when a roster is given.
  - `--state-dir /state` is passed, and `--phase` is not.
  - Exactly one console runs, and its `ppid` is the test process's pid: the script `exec`ed.
  - A second run with `VEHICLE_SLUGS` empty serves exactly `vehicle`.
  - A third run with `VEHICLE_SLUGS=mackerel,vehicle,mackerel` serves `mackerel` and `vehicle` once each.
- [ ] **Step 2:** Run `python3 -m pytest tests/test_vehicle_reconciliation.py -k servable -q`. Expected: FAIL. Today the script forks one console per slug and scans the directory.
- [ ] **Step 3: Rewrite the script.**
  - Read the slug list from `VEHICLE_SLUGS`, deduplicated in first-seen order, with `vehicle` when the list is empty.
  - `mkdir -p` each window.
  - Validate each slug against `[a-z][a-z0-9_]{0,31}`, as the roster draws them, so a bad name stops the service with a message and does not reach the console.
  - `exec` the console.
  - Rewrite the header: one executive for every window; the slug set is the world's identity; no scan; `vehicle` only without a roster, and why (a window no agent holds is a command authority on the one world).
- [ ] **Step 4:** Run the reconciliation file and `tests/test_agent_image.py`. Expected: PASS, except the two pins Phase B moves.
- [ ] **Step 5:** Commit with the message `vehicle: one console for every window, its slugs the roster's, exec'd`.

### Task 2: The vehicle's private `/state` image

**Files:**
- Modify: `scripts/volume_images.py`. Add the role `vehicle` to `FLEET_ROLES`, and `Kind("vehicle_state", "40G", "SPACE_VEHICLE_STATE_SIZE", SHARED, (("vehicle", "/state", False, ""),))`.
- Modify: `scripts/build_compose.py`. The `vehicle` service binds the window plus `mounts_for("vehicle", None, count)`, and its environment gains `VEHICLE_STATE_DIR: /state`. Regenerate `docker-compose.yml`.
- Modify:
  - `.env.example`: `#SPACE_VEHICLE_STATE_SIZE=40G` under "shared", and the totals sentence (shared 51.0625G, total 177.3125G);
  - `scripts/prepare_host.sh`, only if it states a total.
- Test: `tests/test_volume_images.py`, `tests/test_compose_generated.py`, `tests/test_vehicle_reconciliation.py`.

- [ ] **Step 1: Failing tests:**
  - `test_the_default_plan_for_ten_agents_totals_177_gibibytes` replaces the 137 test: shared is 51.0625G, and the total is 177.3125G.
  - `test_only_the_vehicle_mounts_its_state` checks that no service but `vehicle` has a volume whose source contains `/vehicle_state/`, and that `vehicle` binds it at `/state` read-write.
  - `test_the_vehicle_state_is_not_the_window` checks that the two sources differ, and that neither is under the other.
  - In the reconciliation test, `vehicle`'s volumes are the window bind plus the state bind.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. `live/stack.py`'s `prepare` makes every image's `data/` from `volume_images.names`, so the smoke stack picks up the new kind; check that its offline tests still pass.
- [ ] **Step 4:** Run `python3 -m pytest tests -n 8 -q` and `docker compose --profile fleet --profile vehicle config -q`. Expected: PASS, apart from the two pins.
- [ ] **Step 5:** Commit with the message `vehicle: its own 40G /state image, mounted by nothing else`.

### Task 3: Containment

**Files:**
- Modify: `scripts/verify_containment.sh`
- Test: `tests/test_verify_containment.py`

- [ ] **Step 1: Failing test** in the existing style of `tests/test_verify_containment.py`. Read how that file drives the script, and use the same mechanism. The new checks:
  - no agent container mounts a source under `vehicle_state`;
  - `/diode`'s root is not writable from an agent (`in_agent touch /diode/.probe` fails);
  - when the `vehicle` service runs, its mounts are exactly `/diode` and `/state`.
- [ ] **Step 2:** Run it. Expected: FAIL.
- [ ] **Step 3:** Implement the three checks.
  - `.executive.json` in the window root needs no change in any lister. The agent sees only its own `/diode/<slug>`, and `diode_probe.py --list` prints directories only. Record that in the ledger.
  - No check may expect `/diode/vehicle` in a roster stack.
- [ ] **Step 4:** Run `python3 -m pytest tests/test_verify_containment.py -q`. Expected: PASS.
- [ ] **Step 5:** Commit with the message `containment: no agent sees the vehicle's state or writes the window root`.

### Task 4: Docs and the operator procedures

**Files:**
- Modify:
  - `CLAUDE.md`: the vehicle row, with `/state` and one process for every window;
  - the spec's §8 requirement list;
  - `README.md`: a short "The vehicle" section with PACKAGE §4's procedures (first start is a new world on cleared windows; restarts resume by themselves; a deliberate new world; diagnosing an exit 3);
  - `.env.example`: the window section, saying the slug set is the world's identity.
- Test: `tests/test_doc_claims.py`. Its false-claim patterns gain "one console per slug" and "one process per slug". A positive test checks that README names the four procedures.

- [ ] **Step 1:** Failing tests. **Step 2:** FAIL. **Step 3:** Write the docs. **Step 4:** PASS. **Step 5:** Commit with the message `docs: the vehicle's deployment and the operator's procedures`.

### Task 5: Phase A reviews

- [ ] Run the whole suite in the worktree (expected: everything but the two pins), ruff, and compose config for every profile.
- [ ] **Opus subagent review** of `aurora-port..vehicle-adoption`, then one fix pass.
- [ ] **Astra (high) final review** through codex-cli, then one fix pass.
- [ ] Push `vehicle-adoption`; it is not merged.
- [ ] Post the state on `space_chassis-93010ff54e`.

### Phase B: on the #21 merge SHA (posted on the issue)

### Task 6: Pointer, pins, live acceptance, landing

- [ ] **Pointer.** In the worktree's vehicle clone, fetch and check out the SHA, then stage the gitlink. Never touch the main checkout's vehicle.
- [ ] **Pins.** Take the referee test count and the `report.refuse` count from the adopted SHA. Update the reconciliation README and the tests. The suite is then green.
- [ ] **Live.** Add a live vehicle check to `live/`, a smoke stack variant with the `vehicle` profile in place of `diode`. On a roster of three:
  - every window's `state.json` advances, and `executive.world_id` is the same in each;
  - `docker kill` the vehicle, and after the restart policy brings it back: the same `world_id`, the tick continuing, a new `boot_id`, no lost result;
  - `docker stop` ends it within the grace period.
- [ ] **Containment and volumes.** Run `verify_containment.sh --all` against that stack, and `volume_images.py check` with the new image.
- [ ] **Review and land.**
  - Run the Opus review of the delta, then the Astra final review.
  - Squash `vehicle-adoption` into one adoption commit on `aurora-port`.
  - Run the full merged suite and live, then push.
  - Close vehicle #16 on the issue.
