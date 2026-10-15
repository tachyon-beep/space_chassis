# Ordinary serial-build readiness for the live gate (chassis, 2026-10-11)

Owner: Space Chassis Claude Code `session_019mkPNN5J3Atit9tUA6zrNY` (peer `[8a7d49]`). This is documentation only:
**no build, live run or container was started to write it.** It covers the two image builds that R2's live
suite runs before its stacks. The scope rules (master §17) apply throughout: ordinary serial builds on the
default builder, observed and abortable, with **no hard aggregate cap claimed** and no privileged builder.

## The commands, exactly as the harness runs them

`SmokeStack.build()` (`live/stack.py`, tree R2 `0471251a`) runs these one after another, never in parallel:

1. `python3 scripts/build_console_seed.py --source .env.example`. This writes `llm_console_seed.json`, which
   the image copies; the operator's own copy is restored afterwards. The generator is deterministic: no time,
   random or uuid input.
2. `docker compose -p space_chassis_smoke_<pid>[_vehicle] --env-file <root>/smoke.env -f docker-compose.yml
   -f <root>/override.yml --profile fleet --profile <diode|vehicle> build agent_1`. This builds
   `Dockerfile.agent` target `agent`, tagged `space-chassis-agent:smoke`, with the context at the worktree root.
3. Only for the vehicle stack: the same command with `build vehicle`. This builds target `vehicle`, tagged
   `space-chassis-vehicle:smoke`.

Each compose call has a client timeout of 3,600 s (`BUILD_TIMEOUT_SECONDS`). The fixture stack builds (2);
the vehicle stack builds (2) and then (3). R2 runs the stacks one at a time, so the second stack's builds
start after the first stack is down. The rendered build sections were checked offline with
`docker compose config`, which only parses:
- `agent_1`: context = worktree, dockerfile `Dockerfile.agent`, target `agent`;
- `vehicle`: the same, with target `vehicle`.

## Image inputs

**Base:** `python:3.13-slim@sha256:70729b46…` (digest-pinned).

**Layers in `base`:**
- `apt-get` (network);
- `pip install -r requirements-agent.txt` (network);
- a cargo config pointing at `/vendor/registry`. This is a runtime path: the worktree's `vendor/registry` is
  empty and is not copied;
- user and group setup;
- directory creation;
- COPYs of:
  - the harness files;
  - `pump/pump.py`;
  - `recorder/{proxy,recorder_streams,core_caps}.py`;
  - `llm_console_seed.json`;
  - `brief/`;
  - `services/{common,health,fleet_monitor,review}.py`;
  - `containers/entrypoint.sh`;
- `chmod` and `git init` steps.

**`vehicle` stage:** COPY `docs/deep_research/vehicle/`, which bakes the submodule's working tree; then COPY
`containers/serve_vehicle.sh`; then a `__pycache__` prune.

**`agent` stage:** the default target, which carries nothing of the vehicle.

**Context filter:** `.dockerignore` excludes `volumes/`, `volume-images/`, `tests/`, `docs/` (except the
vehicle), `.git/`, `governance/`, `.scratch/`, `.smoke-*/` and caches.

## Observed evidence (read-only, 2026-10-11 ~13:15 AEDT)

| what | observed |
|---|---|
| inputs since the last builds | `git diff b29bf8af 0471251a` over `Dockerfile.agent`, `.dockerignore`, `requirements-agent.txt`, `harness/`, `pump/`, `recorder/`, `brief/`, `services/`, `containers/`, `docker-compose.yml`, `scripts/build_console_seed.py`, `.env.example` and the vehicle gitlink: **empty**, so no image input changed |
| vehicle source = gitlink | the worktree's vehicle clone is at `f44399645fb2633e695a5d758cb5a41f43fb848c`, and that is R2's recorded gitlink. The build-safety condition from AUR-GOV-03 v1.1 holds in this worktree; it does not hold in the main checkout |
| current images | `space-chassis-agent:smoke` `sha256:83fc40b1…`, created 2026-10-10 18:21:20 AEDT. `space-chassis-vehicle:smoke` `sha256:75077b77…`, created 22:20:12 AEDT |
| earlier builds were cache hits | the agent image was **not** recreated by the live gates of 21:59–22:21 or 22:22–22:42, both of which ran `build agent_1`. The vehicle image was created at 22:20 during the first gate, when the gitlink first moved to `f443996`, and was not recreated by the second. These are inferences from image creation times; the build logs were not captured |
| builder cache | `docker builder du`: 60.21 GB, all reclaimable, so the cache is present |

## Still to be demonstrated (each needs a slot grant)

- **Cache hits.** That both builds are full cache hits now: every step `CACHED`, and the image IDs unchanged
  before and after. Expected from the evidence above, but not observed.
- **Wall time and load.** The builds' wall time, and the daemon's CPU and memory during them.
  `dockerd`/`containerd` CPU and RSS can be sampled from `/proc`, the way the diagnostic supervisor already
  does. That load is shared, so it can't all be attributed to Space.
- **Cancellation.** Not demonstrated at all.
  - The harness stops the compose client: a Python timeout kills it.
  - BuildKit is documented to cancel a solve when its client session ends. **No observation here shows the
    daemon-side work stopping**, so it must not be claimed.
  - The harness cannot bound a build's daemon-side work, by design (no privileged builder). A cache miss
    would show up as daemon CPU, not as a bounded cost.
  - A cancellation demonstration would mean deliberately interrupting a real build under observation. That
    needs its own decision.
- **Images built from the R2 tree itself.** `.dockerignore` keeps `tests/`, `docs/` and `live/` out of the
  context, so this is expected to be identical. Confirming it takes a build.

## A proposed observation step, not requested here

Before or as the first part of R2's live gate:
1. run (2) and then (3) on their own, with `--progress plain` logged, the client at nice 19, and five-second
   samples of host and daemon load against the §17 abort thresholds;
2. record the image IDs before and after;
3. treat any non-`CACHED` step as observable work, not as an abort by itself.

The decision on demonstrating cancellation stays with Governance.
