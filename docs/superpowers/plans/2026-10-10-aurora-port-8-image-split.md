# Image Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The **image** every fleet agent runs carries nothing of the vehicle. The vehicle runs from an image of its own. Revision 2, after the Opus plan review.

**Architecture:** `Dockerfile.agent` becomes three stages:
- `base`: today's image without the vehicle;
- `vehicle`: `FROM base`, adding `/opt/vehicle` and `serve_vehicle.sh`, with its own entrypoint;
- `agent`: `FROM base`, last, so that a bare `docker build` produces the agent image and the default fails closed.

Compose tags the targets separately (`space-chassis-agent` and `space-chassis-vehicle`). Every service except `vehicle` runs the agent image. Tests hold the split at the source level (an allow-list), and `verify_containment.sh` holds it against a running stack with a filesystem sweep.

**Tech Stack:** Docker multi-stage builds (BuildKit), compose v5, POSIX sh, pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-aurora-port-design.md` §2, §3.2, §5, §8. Governance: `governance/chassis/open.md` P1.

## Global Constraints

- **John, 2026-10-10:** "yes absolutely, we don't want any risk of information sharing."
- **Scope:** this plan closes the **image** half of P1. The other half stays open until the vehicle adoption lands (plan 7 Phase B). At the pinned vehicle `dd79e76`, the window itself carries the run's identity:
  - `console.py` writes `scenario`, `seed`, `arms` and `dwell` into `<diode>/<slug>/pending.json`, and `vehicle.scenario` into `state.json`;
  - from vehicle `64fc58c` the identity moves to the window root's `.executive.json`, which no agent binds.
- **Branch:** `aurora-port` in the main checkout. Its `docs/deep_research/vehicle` working tree is the vehicle line's: never stage the gitlink, never `submodule update`, stage files by name.
- **Never rebuild the operator's tags.** Builds made for verification use their own tags (`:plan8`) and remove them afterwards.
- Every `USER` line is `USER agent` (`tests/test_agent_image.py:98`). Use `COPY --chown`, and `COPY --chmod` (BuildKit), never `USER root`.
- `docker-compose.yml` is generated: edit `scripts/build_compose.py`, then regenerate.

## Review Focus

1. **A vehicle file reaching the agent image by any path.** Task 1 holds the base and agent stages' COPY sources to an exact allow-list, and the vehicle stage to exactly two COPYs. Task 3 sweeps a running agent's filesystem for the vehicle's files by name.
2. **The default target.** `agent` is the last stage, so a bare `docker build -f Dockerfile.agent -t space-chassis-agent .` carries no vehicle. Task 1 tests the stage order.
3. **A service on the wrong image.** Task 2 tests every service's image and build target.
4. **A stale vehicle image.** A bare `docker compose build`, or `--profile fleet up --build`, skips the profiled `vehicle` service. The docs say so and give the vehicle's build line. Task 2 verifies that both targets actually build.
5. **A containment check that passes because its probe could not run.** Task 3's probe fails closed, and the live test asserts the per-agent PASS line.

---

### Task 1: Three stages in `Dockerfile.agent`

**Files:**
- Modify: `Dockerfile.agent`, `.dockerignore` (the comment only)
- Test: `tests/test_agent_image.py`

**Interfaces:**
- Produces: stages `base` (`FROM python:3.13-slim AS base`), `vehicle` (`FROM base AS vehicle`) and `agent` (`FROM base AS agent`), in that order, with `agent` last.

- [ ] **Step 1: Failing tests** in `tests/test_agent_image.py`. Add a helper, `_stages()`, which splits the Dockerfile's *instructions*, without comments, into `(name, from, instructions)` at each `FROM`.
  - `test_the_agent_image_is_the_default_target_and_carries_nothing_of_the_vehicle`:
    - the stages are exactly `[("base", "python:3.13-slim…"), ("vehicle", "base"), ("agent", "base")]`;
    - `agent` is last and adds no instruction;
    - only `base` names `python:`.
  - `test_the_base_stage_copies_exactly_its_allow_list`:
    - the base stage's COPY sources equal an explicit list: `requirements-agent.txt`, the six harness files, `pump/pump.py`, the three recorder files, `llm_console_seed.json`, `brief/`, the four services files and `containers/entrypoint.sh`;
    - no source is `.`, `docs/` or `containers/`.
  - `test_the_vehicle_stage_adds_the_vehicle_and_its_entrypoint_only`:
    - the vehicle stage's COPYs are exactly the vehicle directory to `/opt/vehicle/` (with `--chown=agent:agent`) and `containers/serve_vehicle.sh` (with `--chmod=0755`);
    - its entrypoint is `["/usr/local/bin/serve_vehicle.sh"]`.
  - Replace `test_the_image_still_carries_the_vehicle`; its assertions move into the vehicle-stage test.
- [ ] **Step 2:** Run `python3 -m pytest tests/test_agent_image.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Rename the first stage `base`, and move the vehicle COPY and the serve script out of it.
  - The entrypoint's chmod stays in `base`.
  - Add `FROM base AS vehicle`: `COPY --chown=agent:agent docs/deep_research/vehicle/ /opt/vehicle/`, `COPY --chmod=0755 containers/serve_vehicle.sh /usr/local/bin/serve_vehicle.sh`, a `RUN` that prunes `__pycache__` under `/opt/vehicle` (as `agent`), and `ENTRYPOINT ["/usr/local/bin/serve_vehicle.sh"]`.
  - Add `FROM base AS agent` last.
  - The header comment states John's ruling and why: the agents could otherwise read the fault policies and run `--plan`. It also says that `docker compose build` builds the vehicle only under `--profile vehicle`.
  - Update `.dockerignore`'s comment, which says the vehicle is baked into "the image".
- [ ] **Step 4:** Run `python3 -m pytest tests/test_agent_image.py tests/test_vehicle_reconciliation.py -q`. Expected: PASS. The reconciliation test's Dockerfile assertions stay as they are: they search the whole file.
- [ ] **Step 5:** Commit with the message `image: the agent image carries nothing of the vehicle; the vehicle builds its own`.

### Task 2: Compose builds and runs the two images

**Files:**
- Modify: `scripts/build_compose.py` (`docker-compose.yml` is regenerated), `README.md` (quick start), `scripts/prepare_host.sh` (its closing `up --build` line)
- Test: `tests/test_compose_generated.py`, `tests/test_vehicle_reconciliation.py`, `tests/test_startup.py`

**Interfaces:**
- Produces:
  - `build_compose.IMAGE = "space-chassis-agent"` and `build_compose.VEHICLE_IMAGE = "space-chassis-vehicle"`;
  - `agent_1`'s build gains `target: agent`;
  - `vehicle` gains `build: {context: ., dockerfile: Dockerfile.agent, target: vehicle}`, `image: space-chassis-vehicle`, and no `entrypoint:` (the image's own).

- [ ] **Step 1: Failing tests:**
  - `test_the_image_is_built_once` becomes `test_each_image_is_built_once_from_its_own_target`:
    - the builders are `agent_1` (target `agent`) and `vehicle` (target `vehicle`);
    - every other service runs `space-chassis-agent`;
    - `vehicle` runs `space-chassis-vehicle`.
  - In the reconciliation servable test, replace `service["image"] == reference["image"]` with: the vehicle runs `space-chassis-vehicle`, the fixture runs `space-chassis-agent`, and the vehicle's entrypoint is the image's.
  - `test_the_quick_start_builds_the_vehicle_image` (`tests/test_startup.py`): README's quick start names `docker compose --profile vehicle build`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement.** Make the generator change and regenerate. README's quick start and `prepare_host.sh`'s closing hint gain the vehicle's build line, and say that rebuilding the agent image no longer rebuilds the vehicle.
- [ ] **Step 4: Build both targets, for real, under verification tags.**
  - `docker build -f Dockerfile.agent --target agent -t space-chassis-agent:plan8 .`, `--target vehicle -t space-chassis-vehicle:plan8`, and a bare `docker build -t space-chassis-default:plan8 .`.
  - Then check:
    - the agent image and the default image have no `/opt/vehicle` and no `serve_vehicle.sh`;
    - the vehicle image has `/opt/vehicle/tools/console.py` and an executable `serve_vehicle.sh`;
    - `docker compose --profile fleet --profile vehicle --profile diode config -q` passes.
  - Remove the `:plan8` tags.
- [ ] **Step 5:** Run `python3 -m pytest tests -n 8 -q`. Expected: PASS. Commit with the message `compose: the vehicle runs its own image; every other service the agent's`.

### Task 3: Containment sweeps an agent for the vehicle

**Files:**
- Modify: `scripts/verify_containment.sh`, `live/test_containment.py`
- Test: `tests/test_verify_containment.py`

- [ ] **Step 1: Failing tests:**
  - `test_an_agent_that_can_see_the_vehicle_is_a_failure`. The fake docker answers an exec containing `/opt/vehicle` with `$VEHICLE_SIGHT` when it is set:
    - `absent` gives `PASS  agent_1 has no vehicle in its image`;
    - `present` gives `FAIL  agent_1 can read the vehicle`;
    - nothing gives `FAIL  agent_1 could not be probed for the vehicle`.
  - `test_the_vehicle_probe_says_nothing_when_it_cannot_run`: the probe's own text, run with an empty `PATH`, does not print `absent`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement the probe.** It runs only when `find` exists, so it fails closed:
  ```
  command -v find >/dev/null 2>&1 || exit 0
  hits=$(find / -xdev \( -path /proc -o -path /sys -o -path /diode \) -prune -o \( -path /opt/vehicle -o -name serve_vehicle.sh -o -name mission.yaml -o -name vehicle.yaml -o -name coupling.yaml -o -name plant.md -o -name fault_policy.yaml \) -print 2>/dev/null | head -1)
  [ -n "$hits" ] && echo present || echo absent
  ```
  The window `/diode` is excluded, because it is the agent's own and is published by contract.
  In `live/test_containment.py`, assert `PASS  agent_<n> has no vehicle in its image` for every agent.
- [ ] **Step 4:** Run `python3 -m pytest tests/test_verify_containment.py -q`. Expected: PASS. Commit with the message `containment: an agent has no vehicle in its image`.

### Task 4: Live, docs, governance

**Files:**
- Modify:
  - `CLAUDE.md` (the table row for the vehicle);
  - `AGENTS.md` (line ~58);
  - spec §3.2 ("one agent image"), with a dated note;
  - `governance/chassis/{open,interface,decisions,snapshot}.md`.
- Rename: `test_claude_md_states_43_s_escalation_and_the_vehicle_in_the_image` to `…_and_where_the_vehicle_lives`.

- [ ] **Step 1:** Run `python3 -m pytest live -q`. Expected: 14/14, with "has no vehicle in its image" passing for every agent. `live/stack.py` needs no change on `aurora-port`: compose merges the base `build:` under the override's `image:`.
- [ ] **Step 2: Docs.**
  - The vehicle image `space-chassis-vehicle` alone carries `/opt/vehicle`.
  - Governance:
    - `decisions.md`: John, 2026-10-10, separate images;
    - `open.md`: P1's image half done, with the commits, and its window half open until adoption;
    - `interface.md`: the Image row;
    - `snapshot.md`.
  - The README section "The vehicle" exists only on `vehicle-adoption`; its wording is fixed in the rebase (Task 5).
- [ ] **Step 3:** Run the whole suite and ruff. Expected: PASS. Commit with the message `docs: the vehicle's own image; governance records the split`, and push `aurora-port`.

### Task 5: Reviews, then the rebase of the adoption branches

- [ ] Opus subagent code review of the range, then one fix pass.
- [ ] One Astra (high) final review through codex-cli, then one fix pass.
- [ ] **Rebase `vehicle-adoption` onto `aurora-port`**, from the worktree. Expect:
  - `test_the_base_image_is_pinned_by_digest`: the `FROM` line becomes `FROM python:3.13-slim@sha256:… AS base`, and the test matches it with ` AS base`;
  - the replaced `test_the_image_still_carries_the_vehicle`;
  - `FAKE_DOCKER` cases and EOF tests in `test_verify_containment.py`;
  - the agent loop in `verify_containment.sh`;
  - `build_compose.py` `_vehicle`. Regenerate `docker-compose.yml`; never hand-merge it.
  - Docs that say "the shared agent image", or "a rebuild of the agent image", become "the vehicle image": README "The vehicle", `interface.md`'s Image row, and CLAUDE.md's vehicle row. Reword the libc claim: the apt layer, not only the digest, decides libc on an uncached rebuild.
- [ ] **Rebase `phase-b-dryrun`** onto the rebased `vehicle-adoption`, in its worktree. `live/stack.py`'s vehicle mode gains `SMOKE_VEHICLE_IMAGE = "space-chassis-vehicle:smoke"`, and `build()` builds `agent_1` and, for a vehicle stack, `vehicle` under `--profile vehicle`. Its offline test asserts the vehicle tag.
- [ ] Run the suites, push `vehicle-adoption`, and tell the vehicle session: the SHAs changed, the gitlink did not.
- [ ] Commit the ledger to `docs/superpowers/ledgers/plan-8-ledger.md`.
