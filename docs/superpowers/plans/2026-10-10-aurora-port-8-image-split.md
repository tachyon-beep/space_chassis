# Image Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** No fleet agent can read anything of the vehicle. The agent image carries no `/opt/vehicle`, and the vehicle runs from an image of its own.

**Architecture:** `Dockerfile.agent` becomes two build targets.
- `agent` is today's image without the vehicle and without its serve script.
- `vehicle` is `FROM agent`, adding `/opt/vehicle` and `serve_vehicle.sh`.

Compose builds and tags them separately (`space-chassis-agent` and `space-chassis-vehicle`). Every service except `vehicle` runs the agent image. Tests hold the split at the source level, and `verify_containment.sh` holds it against a running stack.

**Tech Stack:** Docker multi-stage builds (BuildKit), compose, POSIX sh, pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-aurora-port-design.md` §2 (what the agent cannot reach), §5, §8. Governance: `governance/chassis/open.md` P1.

## Global Constraints

- **John, 2026-10-10:** "yes absolutely, we don't want any risk of information sharing." The agent image must not contain the vehicle in any form: no `/opt/vehicle`, no `serve_vehicle.sh`, and no vehicle file under another path.
- **Branch:** work on `aurora-port` in the main checkout. Its `docs/deep_research/vehicle` working tree is the vehicle line's: never stage the gitlink, never `submodule update`, stage files by name.
- **`vehicle-adoption`**, which is parked, is rebased onto this later. Its Phase A changes the `vehicle` service; this plan changes only that service's image and build.
- `docker-compose.yml` is generated; edit `scripts/build_compose.py`, then regenerate.
- The live smoke stack builds its own tags. It gains a vehicle tag only when it runs the vehicle; on `aurora-port` it runs the fixture.

## Review Focus

1. **A vehicle file under a path other than `/opt/vehicle` in the agent image.** For example, `COPY docs/` widened by a future `.dockerignore` change, or the serve script. Task 1 tests the agent stage's COPY sources. Task 3 tests a running agent container (no `/opt/vehicle`, no `serve_vehicle.sh`).
2. **The vehicle stage drifting from the agent stage's base.** The vehicle's checkpoint records the Python patch version and libc, so the vehicle image must be built `FROM` the agent stage, with no second `FROM python`. Task 1 tests it.
3. **A service quietly running the vehicle image**, or the vehicle running the agent image. Task 2 tests every service's image and build target.
4. **The operator's `docker compose build`** must build both images. A stale vehicle image would serve an old vehicle. Task 2 gives both services a build section.
5. **A containment check that passes because the probe could not run.** Task 3 makes the new check fail closed, like the others.

---

### Task 1: Two build targets in `Dockerfile.agent`

**Files:**
- Modify: `Dockerfile.agent`
- Test: `tests/test_agent_image.py`

**Interfaces:**
- Produces: the Dockerfile stages `agent` (first) and `vehicle` (`FROM agent AS vehicle`, last). The stage order is pinned so a bare `docker build` builds the vehicle image; compose always names the target.

- [ ] **Step 1: Failing tests** in `tests/test_agent_image.py`:
  - Add `test_the_agent_stage_carries_nothing_of_the_vehicle`:
    - parse `Dockerfile.agent` into stages, split at `FROM` lines;
    - the agent stage's COPY sources contain no `docs/` path and no `serve_vehicle.sh`;
    - its text has no `/opt/vehicle`.
  - Add `test_the_vehicle_stage_is_the_agent_image_plus_the_vehicle`:
    - the second stage's `FROM` is `agent` (`FROM agent AS vehicle`);
    - it copies `docs/deep_research/vehicle/` to `/opt/vehicle/` and `containers/serve_vehicle.sh`;
    - it ends as `USER agent`;
    - there are exactly two `FROM` lines, and only the first names `python:`.
  - Replace `test_the_image_still_carries_the_vehicle`: the vehicle stage carries it, so its assertions move into the test above.
- [ ] **Step 2:** Run `python3 -m pytest tests/test_agent_image.py -q`. Expected: FAIL (one stage).
- [ ] **Step 3: Implement.**
  - `FROM python:3.13-slim AS agent`, with everything today except the vehicle COPY and the serve script.
  - The entrypoint's chmod stays in the agent stage.
  - Then `FROM agent AS vehicle`: `USER root`, the two COPYs (with `--chown=agent:agent` for the vehicle), `chmod 0755` the serve script, prune `__pycache__` under `/opt/vehicle`, then `USER agent`.
  - Each stage's header comment says why the split exists: John's ruling, and the agents could otherwise read the fault policies and run `--plan`.
- [ ] **Step 4:** Run `python3 -m pytest tests/test_agent_image.py tests/test_vehicle_reconciliation.py -q`. Expected: PASS (the reconciliation test's Dockerfile assertions may need the stage-aware form, changed here).
- [ ] **Step 5:** Commit with the message `image: the agent image carries nothing of the vehicle; the vehicle builds its own`.

### Task 2: Compose builds and runs the two images

**Files:**
- Modify: `scripts/build_compose.py`, `docker-compose.yml` (regenerated)
- Test: `tests/test_compose_generated.py`, `tests/test_vehicle_reconciliation.py`

**Interfaces:**
- Produces:
  - `build_compose.IMAGE = "space-chassis-agent"` and `build_compose.VEHICLE_IMAGE = "space-chassis-vehicle"`;
  - `agent_1`'s build gains `target: agent`;
  - `vehicle` gains `build: {context: ., dockerfile: Dockerfile.agent, target: vehicle}` and `image: space-chassis-vehicle`.

- [ ] **Step 1: Failing tests:**
  - `test_the_image_is_built_once` becomes `test_each_image_is_built_once_from_its_own_target`:
    - the builders are `["agent_1", "vehicle"]`, with targets `agent` and `vehicle`;
    - every service except `vehicle` has image `space-chassis-agent`;
    - `vehicle` has `space-chassis-vehicle`.
  - In the servable reconciliation test, `service["image"] == reference["image"]` becomes an assertion that the vehicle runs `space-chassis-vehicle` and the fixture runs the agent image. State the reason in a comment: the fixture models nothing and needs no vehicle.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement.** Make the generator change and regenerate. Then run `docker compose --profile fleet --profile vehicle --profile diode config -q`, and check that `docker compose build --dry-run` (if available) or `config` names both images.
- [ ] **Step 4:** Run `python3 -m pytest tests -n 8 -q`. Expected: PASS.
- [ ] **Step 5:** Commit with the message `compose: the vehicle runs its own image; every other service the agent's`.

### Task 3: Containment checks the agent cannot see the vehicle

**Files:**
- Modify: `scripts/verify_containment.sh`
- Test: `tests/test_verify_containment.py`

- [ ] **Step 1: Failing tests:**
  - `test_an_agent_that_can_see_the_vehicle_is_a_failure`:
    - the fake docker answers an exec containing `/opt/vehicle` with `VEHICLE_SIGHT` when it is set;
    - `absent` gives `PASS  agent_1 has no vehicle in its image`;
    - `present` gives `FAIL  agent_1 can read the vehicle`;
    - no output gives `FAIL  agent_1 could not be probed for the vehicle`.
  - `test_the_vehicle_probe_says_nothing_when_it_cannot_run`: the probe's own text, run with an empty PATH, does not print `absent`. This follows the window-root probe's test.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement.** The per-agent probe is
  `sh -c 'command -v ls >/dev/null 2>&1 || exit 0; if [ -e /opt/vehicle ] || ls /usr/local/bin/serve_vehicle.sh >/dev/null 2>&1; then echo present; else echo absent; fi'`.
  Map its verdict as above.
- [ ] **Step 4:** Run `python3 -m pytest tests/test_verify_containment.py -q`. Expected: PASS.
- [ ] **Step 5:** Commit with the message `containment: an agent has no vehicle in its image`.

### Task 4: Live, docs, governance

**Files:**
- Modify:
  - `live/stack.py`: `build()` builds `agent_1` only, as today; the smoke stack runs the fixture;
  - `CLAUDE.md` (the vehicle row);
  - `README.md` ("The vehicle");
  - `governance/chassis/{open,interface,decisions,snapshot}.md`.
- Test: `live/test_containment.py`, run as part of `pytest live`.

- [ ] **Step 1:** Run `python3 -m pytest live -q`. Expected: 14/14, including `verify_containment.sh` with the new "no vehicle in its image" PASS for each agent. The smoke image is built from the `agent` target. Set `target: agent` in the smoke override if compose's build of `agent_1` needs it.
- [ ] **Step 2: Docs.**
  - CLAUDE.md's vehicle row: the vehicle image `space-chassis-vehicle` alone carries `/opt/vehicle`.
  - README "The vehicle": the vehicle has its own image, built by `docker compose build`.
  - Governance:
    - `decisions.md`: John, 2026-10-10, separate images;
    - `open.md`: P1 moves to done, with the commits;
    - `interface.md`: the Image row;
    - `snapshot.md`: the head SHA.
  - `tests/test_doc_claims.py`: a false-claim pattern for "every agent service runs the image that carries the vehicle", or the like, if the docs said so anywhere.
- [ ] **Step 3:** Run the whole suite and ruff. Expected: PASS.
- [ ] **Step 4:** Commit with the message `docs: the vehicle's own image; governance records the split`. Push `aurora-port`.

### Task 5: Reviews

- [ ] Opus subagent code review of the range, then one fix pass.
- [ ] One Astra (high) final review through codex-cli, then one fix pass.
- [ ] Rebase `vehicle-adoption` onto the new `aurora-port`. Resolve `_vehicle` (Phase A's init, `/state` and env, plus this plan's image and build) and the Dockerfile's digest pin in the agent stage's `FROM`. Then run the suite, push, and tell the vehicle session that the branch's SHAs changed and its gitlink did not.
- [ ] Commit the ledger to `docs/superpowers/ledgers/plan-8-ledger.md`.
