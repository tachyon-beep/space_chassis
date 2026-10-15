# Aurora Port, Plan 3a: The Agent Image, Entrypoint and Pump — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the image every agent and recorder runs into Aurora's shape: a seed git repository with `baseline` and `rescue` tags at `/opt/agent`, the pump and recorder sources outside it, a hardened environment, and an entrypoint that reseeds `/work`, starts the agent's loopback servers with their data under `/state`, starts the pump, and hands the container to the watchdog with `exec`. Everything is tested without Docker.

**Architecture:**
- **Pump:** `pump/pump.py` is vendored from Aurora at `42faf41`, with its tests in `pump/tests` as their own process, because `services/pump.py` shares its module name until plan 5.
- **Image and entrypoint:** `Dockerfile.agent` and `containers/entrypoint.sh` are rewritten in place. The vehicle test pins the `Dockerfile.agent` filename and two of its lines.
- **Entrypoint testability:** every path and binary the entrypoint uses has an environment override whose default is the real value. Tests in the root suite then run it in a temp directory, with stub `python`, `initdb`, `postgres`, `nats-server` and `redis-server` on `PATH`.

**Tech Stack:** POSIX `sh`, Docker build syntax, Python 3 standard library, and pytest. No Docker daemon is needed for this plan.

**Spec:** `docs/superpowers/specs/2026-10-09-aurora-port-design.md`, sections 2, 3, 3.2, 4 and 5. Plans 1 and 2 are complete on `aurora-port`.

**The programme, revised.** Plan 3 is split three ways:
- **3a, this plan:** image, entrypoint, pump.
- **3b:** bounded volumes and compose. That is the loop-image manifest and creator, which John chose to port on 2026-10-09; a generated flat `docker-compose.yml` with per-agent binds; ten recorders and the recorder-only ledger volume; and `prepare_host.sh` with the roster moved out of the shared volume.
- **3c, live:** the console seed, the three-agent smoke stack, `verify_containment.sh`, and spec acceptance checks 1–8.

Plans 4 (operator surfaces) and 5 (retirement and words) follow.

## Deviations and rulings this plan carries (each also goes in the ledger)

- **uid 1000, not Aurora's 65532.** The spec (3.2) says so, for the vehicle and the existing volumes. Aurora's uid assertions in `test_host_scripts.py` are not carried. The user gets an explicit gid of 1000, so the recorder's `0660` socket is reachable by agent and recorder alike: same image, same user.
- **`/state` and the entrypoint.** Aurora's `test_persistent_state.py` forbids `/state` in `entrypoint.sh`. Here the entrypoint must start Postgres, NATS and Redis with their data under `/state`, per spec 3.2. The test's point is kept, narrowed: no harness or service module names `/state` (`agent.py`, `chassis.py`, `watchdog.py`, `pump.py`, `proxy.py`, `recorder_streams.py`, `core_caps.py`). In the entrypoint, `/state` appears only as the servers' data and log directories.
- **`/build` is a disk-backed per-agent volume, wiped at start, not tmpfs.** Spec 5 lists it as tmpfs, but a tmpfs counts against the 3 GB memory limit and a Rust build would starve it. Aurora's own answer is a disk-backed volume that the entrypoint empties, which gives the same lifetime. 3b gives it a bounded image.
- **The unbounded-volume reference.** `warn_if_unbounded` compares each mount root's device with that of `/vendor/registry`, a plain host bind in this image. Aurora compares with `/vendor`, which space does not mount whole.
- **`containers/agent.env` is left alone.** The new entrypoint does not read it, and `serve_vehicle.sh` sources it, guarded. Plan 5 retires what no longer applies.
- **Server logs go to `$RUN_DIR/logs`, a tmpfs, not `/state`.** Spec 3.2 says "tmpfs for the run and log directories". Logs in the agent's durable store would grow without bound. The pump loop's own output stays on the container log, as in Aurora.
- **Each start empties `/work` before reseeding it,** as Aurora's further-host loop does. On a tmpfs that is fresh at container start it changes nothing, but it costs nothing either.

## Global Constraints

- **Vendored code** comes from `git -C ~/aurora show 42faf41:<path>` and is excluded from ruff by exact path.
- **The `Dockerfile.agent` lines the vehicle test pins stay byte-identical:**
  - `COPY --chown=agent:agent docs/deep_research/vehicle/ /opt/vehicle/`
  - the `containers/serve_vehicle.sh /usr/local/bin/serve_vehicle.sh` COPY

  `.dockerignore` must keep the vehicle in the build context. `tests/test_vehicle_reconciliation.py` must pass unchanged.
- **Only the six runtime files go into `/opt/agent`**, by explicit name from `harness/`: `agent.py chassis.py command_runtime.py watchdog.py system_prompt.txt user_prompt.txt`. No directory COPY, so `harness/tests` and the untracked `harness/session_context.json` can never land in the seed.
- **The seed repository:**
  - `git init -q`, then repo-local `user.email agent@localhost` and `user.name agent`;
  - `.gitignore` containing exactly `tombstones/` and `session_context.json`;
  - one commit, `baseline`, then `git tag baseline` and `git tag rescue`;
  - no `experimental` tag.
- **The hardened environment in the image** (spec 2):
  - `PYTHONNOUSERSITE=1` and `GIT_CONFIG_GLOBAL=/dev/null`;
  - `HOME=/home/agent`, which becomes a tmpfs in 3b's compose;
  - `CARGO_HOME=/build/.cargo`, `CARGO_TARGET_DIR=/build/target` and `XDG_CACHE_HOME=/build/.cache`.
- **The entrypoint ends `exec "$PYTHON" watchdog.py`**, run from `$WORK_DIR`, as its single `exec` and its last non-blank line. That is Aurora's form: a dead watchdog ends the container, and the restart reseeds.
- **Test names are full sentences. No skips and no xfails.** Deprecation warnings are errors.

## Review Focus

1. **A read-only root.** The Debian `/usr/bin` Postgres tools are `pg_wrapper` shims that need a writable `/etc/postgresql`. The entrypoint uses `/usr/lib/postgresql/*/bin/` through a glob (overridable as `PG_BIN`), and puts the server socket in `$RUN_DIR` (default `/run/agent`) with `-k`. (Task 2: `test_postgres_is_initialised_once_under_state_and_started_from_the_versioned_bin`)
2. **A second start must not re-run `initdb`** over a cluster that already exists in `/state`, which would destroy the agent's database. (Task 2: same test, with the cluster present)
3. **A server that fails to start must not stop or delay the container.** The world's servers are the agent's to use, not a precondition for the watchdog. The Postgres chain (`initdb`, start, wait, `createdb`) runs as one backgrounded subshell. A stale `postmaster.pid` from a container that was killed is removed first, since nothing else can hold that data directory in a fresh container. (Task 2: `test_a_server_that_fails_to_start_does_not_stop_the_handoff`, `test_a_stale_postmaster_pid_is_cleared_before_postgres_starts`)
4. **A pump that crashes is restarted** by its loop, and that loop is started before the `exec`, in the background. (Task 2: `test_a_crashing_pump_is_restarted_by_the_loop`, `test_the_pump_loop_is_started_before_the_exec`)
5. **The seed cannot carry a test session or the tests**, and the build context cannot carry them into the image either. (Task 3: `test_the_dockerignore_keeps_test_leftovers_and_tests_out_of_the_image`)

---

## File structure

| Path | Responsibility |
|---|---|
| `pump/pump.py` | Aurora's process scheduler. Vendored unchanged. |
| `pump/tests/test_pump.py`, `pump/tests/hostile_inputs.py`, `pump/tests/conftest.py` | Aurora's pump tests, minus the one that reads Aurora's Dockerfile |
| `containers/entrypoint.sh` | rewritten: reseed `/work`, servers under `/state`, `/build` wipe, mount-root warnings, pump loop, `exec` the watchdog |
| `Dockerfile.agent` | rewritten: packages unchanged; uid and gid 1000; seed repo with tags; pump and recorder outside `/opt/agent`; hardened environment; mountpoints |
| `.dockerignore` | adds the harness, recorder and pump test directories and the harness test leftovers |
| `tests/test_agent_entrypoint.py` | root suite: the entrypoint run with stubs |
| `tests/test_agent_image.py` | root suite: the Dockerfile and `.dockerignore` read as text |

---

### Task 1: Vendor Aurora's pump

**Files:**
- Create: `pump/pump.py` and `pump/tests/test_pump.py` (from `42faf41`); `pump/tests/hostile_inputs.py` (copied from `recorder/tests/hostile_inputs.py`, which is byte-identical to Aurora's); `pump/tests/conftest.py`
- Modify: `pyproject.toml` (ruff `exclude`: `"pump/pump.py"`, `"pump/tests/test_pump.py"`, `"pump/tests/hostile_inputs.py"`), `CLAUDE.md` (Commands)

**Interfaces:**
- Produces: the module `pump`, importable in `pump/tests`. Environment: `PUMP_DIR` (default `/pump`), `PUMP_MAX_ENTRIES` (32), `PUMP_MAX_CONCURRENT` (8).

- [ ] **Step 1:** Copy `pump.py` and `tests/test_pump.py` with `git -C ~/aurora show 42faf41:<path>`. Copy `hostile_inputs.py` from `recorder/tests/`, after checking with `cmp` that it matches Aurora's at `42faf41`.
- [ ] **Step 2:** Write `pump/tests/conftest.py`. At import, put `pump/` first on `sys.path` and `pump/tests` second; inserts go in reverse. Add an autouse `monkeypatch.chdir` into `pump/`.
- [ ] **Step 3:** Delete `test_the_image_ships_the_pump_outside_the_agent_workspace` from `pump/tests/test_pump.py`. It reads Aurora's `Dockerfile`; Task 3 re-adds its claim against `Dockerfile.agent`.
- [ ] **Step 4:** Run `python3 -m pytest pump/tests -p no:cacheprovider`. Expected: `100 passed`, measured on a scratch copy on 2026-10-09. Also run `git status --short pump`. Expected: only the four new files, so the tests leave nothing behind.
- [ ] **Step 5:**
  - Add the three ruff excludes.
  - Add to CLAUDE.md's Commands: `python3 -m pytest pump/tests -q   # Aurora's pump: its own process until plan 5 retires services/pump.py`.
  - Run `uvx ruff check . --no-cache`. Expected: `All checks passed!`
  - Commit: `pump: vendor Aurora's process scheduler at 42faf41`.

---

### Task 2: The entrypoint

**Files:**
- Rewrite: `containers/entrypoint.sh`
- Create: `tests/test_agent_entrypoint.py`

**Interfaces:**
- **Environment overrides, each with its real default:**
  - `SEED_DIR=/opt/agent`, `WORK_DIR=/work`, `STATE_DIR=/state`, `BUILD_DIR=/build`, `RUN_DIR=/run/agent`
  - `PUMP_BIN=/usr/local/bin/pump.py`, `PYTHON=python`
  - `PG_BIN` (default: the first match of `/usr/lib/postgresql/*/bin`)
  - `MOUNT_ROOTS="/state /shared /diode /pump /build /telemetry /llm/console /llm/sock"`
  - `UNBOUNDED_REFERENCE=/vendor/registry`
  - `PUMP_RESTART_SECONDS=5`
- **Behaviour, in order:**
  1. **Mount-root warnings.** For each root in `MOUNT_ROOTS` that is a directory, if `stat -c %d` matches `UNBOUNDED_REFERENCE`'s, write `warning: <root> shares a filesystem with the host; its size boundary is absent` to stderr. Each check is guarded, so it never ends the script.
  2. **Wipe the build area.** Empty `BUILD_DIR`'s contents with `chmod -R u+rwX` then `find -mindepth 1 -maxdepth 1 -exec rm -rf {} +`, guarded.
  3. **Start the servers,** each guarded, after `mkdir -p "$STATE_DIR/nats" "$STATE_DIR/redis" "$RUN_DIR/logs"`:
     - **Postgres,** as one backgrounded subshell:
       1. If `$STATE_DIR/postgres/PG_VERSION` is absent, run `"$PG_BIN/initdb" -D "$STATE_DIR/postgres" --auth=trust -U "$(id -un)"`.
       2. Otherwise run `rm -f "$STATE_DIR/postgres/postmaster.pid"`.
       3. Run `"$PG_BIN/postgres" -D "$STATE_DIR/postgres" -k "$RUN_DIR" -c listen_addresses=127.0.0.1 >> "$RUN_DIR/logs/postgres.log" 2>&1 &`.
       4. Wait up to 10 s for `"$PG_BIN/pg_isready" -h "$RUN_DIR"`.
       5. Run `"$PG_BIN/createdb" -h "$RUN_DIR" chassis`, guarded. It needs no `-U`, because the OS user is the superuser `initdb` created.
     - **NATS:** `nats-server -a 127.0.0.1 -p 4222 -m 8222 -sd "$STATE_DIR/nats" >> "$RUN_DIR/logs/nats.log" 2>&1 &`.
     - **Redis:** `redis-server --bind 127.0.0.1 --port 6379 --dir "$STATE_DIR/redis" --save '' --appendonly no >> "$RUN_DIR/logs/redis.log" 2>&1 &`.
  4. **Start the pump loop:** `( while true; do "$PYTHON" "$PUMP_BIN" || true; sleep "$PUMP_RESTART_SECONDS"; done ) &`.
  5. **Reseed the harness:** empty `$WORK_DIR` (`find -mindepth 1 -maxdepth 1 -exec rm -rf {} +`, guarded), then `cp -r "$SEED_DIR/." "$WORK_DIR/"` and `cd "$WORK_DIR"`.
  6. **Hand off:** `exec "$PYTHON" watchdog.py`.
- **What it no longer does:**
  - no `.fleet` announcement, no `.seeded` marker, no home seeding;
  - no sourcing of `/etc/agent.env`, no supervisor loop, no diode entry;
  - no `/state` reads beyond the servers' own directories.

- [ ] **Step 1: Write the failing tests.**

  **Harness.** The entrypoint backgrounds a pump loop, so it cannot run under `subprocess.run` with captured pipes: the loop inherits them, and the run never sees EOF. Instead:
  - **The `world` fixture:** a temp root holding `seed/` (with a `watchdog.py` marker file), `work/` (holding one stale file), `state/`, `build/` (with one file and a read-only subdirectory), `run/`, `pgbin/` and `bin/`.
  - **Starting the entrypoint:** `subprocess.Popen(["sh", "containers/entrypoint.sh"], env=..., start_new_session=True, stdout=<file>, stderr=<file>)` with the overrides pointing into the fixture, `PATH=bin:$PATH` and `PUMP_RESTART_SECONDS=0.05`.
  - **Waiting:** `wait(timeout=20)` for the exec'd watchdog stub, then poll `calls.log` with a 10 s deadline for anything a background process produces.
  - **Teardown:** `os.killpg(proc.pid, signal.SIGTERM)`, guarded, so no loop or stub outlives the test.

  **The stubs** write their argv, cwd and an order stamp to `calls.log`:
  - `bin/python`: for the watchdog it records and exits 0. For the pump, it exits 1 on its first call and then `exec sleep 60`, so the restarted pump blocks instead of spinning.
  - `pgbin/initdb` creates `PG_VERSION`.
  - `pgbin/pg_isready` exits 0.
  - `pgbin/postgres`, `pgbin/createdb`, `bin/nats-server` and `bin/redis-server` record and exit 0.

  **The tests:**
  - `test_the_seed_replaces_work_and_the_watchdog_runs_from_there`: `work/watchdog.py` exists, the stale file is gone, and the `python watchdog.py` call's cwd is `work/`.
  - `test_the_watchdog_is_the_one_exec_and_the_last_line`: read as text, the last non-blank line is `exec "$PYTHON" watchdog.py`, and exactly one line, stripped, starts with `exec `. That is Aurora's form; `find -exec` is not a line start.
  - `test_the_pump_loop_is_started_before_the_exec`:
    - Read as text, the loop line ends in `&` and its index is below the `exec` line's.
    - Dynamically, both the pump and the watchdog were called. There is no timing assertion, because the two race.
  - `test_a_crashing_pump_is_restarted_by_the_loop`: `python pump.py` appears at least twice in `calls.log` before the deadline.
  - `test_the_build_area_is_emptied_without_being_removed`: `build/` exists and is empty, the read-only subdirectory included.
  - `test_postgres_is_initialised_once_under_state_and_started_from_the_versioned_bin`:
    - The first run calls `pgbin/initdb -D <state>/postgres`, then `pgbin/postgres` with `-D <state>/postgres -k <run>`, then `pgbin/createdb` (polled for).
    - A second run, with `PG_VERSION` now present, calls `postgres` and not `initdb`.
  - `test_a_stale_postmaster_pid_is_cleared_before_postgres_starts`: with `PG_VERSION` and a `postmaster.pid` present beforehand, the `.pid` file is gone by the time `postgres` is called. The `postgres` stub records whether it existed.
  - `test_nats_and_redis_keep_their_data_under_state`: `nats-server … -sd <state>/nats` and `redis-server … --dir <state>/redis` are called with `127.0.0.1`, and `<state>/nats`, `<state>/redis` and `<run>/logs` exist afterwards.
  - `test_a_server_that_fails_to_start_does_not_stop_the_handoff`: make `pgbin/initdb`, `nats-server` and `redis-server` exit 1. The watchdog call still happens within the wait.
  - `test_a_mount_root_on_the_host_filesystem_draws_the_factual_warning`: set `MOUNT_ROOTS` to one directory on the same filesystem as `UNBOUNDED_REFERENCE`, both inside `tmp_path`. The warning sentence is *in* stderr, and the watchdog still runs. With `UNBOUNDED_REFERENCE=/proc`, a different filesystem, the sentence is absent.
  - `test_the_entrypoint_names_state_only_for_the_servers`: every non-comment line of `entrypoint.sh` that mentions `STATE_DIR` or `/state` matches `postgres|nats|redis|MOUNT_ROOTS|STATE_DIR[:=]`.
  - `test_no_harness_or_recorder_module_names_state`: none of `harness/{agent,chassis,watchdog}.py`, `pump/pump.py` or `recorder/{proxy,recorder_streams,core_caps}.py` contains `"/state"`. This is Aurora's rule, kept for the modules.
- [ ] **Step 2:** Run `python3 -m pytest tests/test_agent_entrypoint.py -p no:cacheprovider`. Expected: the behaviour tests fail against the current entrypoint, which sources `/etc/agent.env`, seeds once with a marker and runs a supervisor loop. `test_no_harness_or_recorder_module_names_state` passes already; it is a guard on the vendored modules.
- [ ] **Step 3:** Rewrite `containers/entrypoint.sh` to the behaviour above, with a header comment that says what it decides and why, in this repository's style: why `exec`, why reseed every start, why the servers are guarded. `#!/bin/sh` and `set -u`, without `set -e` around guarded steps.
- [ ] **Step 4:** Run `python3 -m pytest tests -p no:cacheprovider`. Expected: `113 passed`, which is the 101 existing tests plus 12 here. `test_vehicle_reconciliation.py` is unaffected.
- [ ] **Step 5:** Run `uvx ruff check . --no-cache` (expected: clean). Commit: `containers: an entrypoint in Aurora's form, with the world's servers under /state`.

---

### Task 3: The image

**Files:**
- Rewrite: `Dockerfile.agent`
- Modify: `.dockerignore`
- Create: `tests/test_agent_image.py`

**Interfaces:**
- Consumes: Task 1's `pump/pump.py`; plan 1's `harness/` runtime files; plan 2's `recorder/{proxy,recorder_streams,core_caps}.py`; Task 2's entrypoint.
- Produces, in the image:
  - `/opt/agent`: the seed repo, owned by `agent`.
  - `/usr/local/bin/pump.py`
  - `/usr/local/lib/recorder/{proxy.py,recorder_streams.py,core_caps.py}`. 3b's recorder service runs `python /usr/local/lib/recorder/proxy.py`.
  - `/opt/brief` and `/opt/vehicle`, unchanged.
  - `/opt/services`, kept until plans 4 and 5, for the review and monitor tools.
  - mountpoints owned by uid 1000: `/work /state /shared /diode /pump /build /telemetry /llm/sock /llm/console /run/agent /home/agent`, plus `/vendor`, root-owned and read-only.

- [ ] **Step 1: Write the failing tests in `tests/test_agent_image.py`**, reading `Dockerfile.agent` and `.dockerignore` as text:
  - `test_the_agent_image_copies_exactly_the_six_runtime_files_into_the_seed`: exactly one COPY targets `/opt/agent/`, and its sources are `harness/{agent.py,chassis.py,command_runtime.py,watchdog.py,system_prompt.txt,user_prompt.txt}`.
  - `test_the_seed_is_a_repository_with_baseline_and_rescue_tags_and_no_experimental`: `git init`, the repo-local identity, the `.gitignore` contents, `git tag baseline` and `git tag rescue` are present, and `git tag experimental` is absent. This is the test plan 1 held back.
  - `test_the_pump_and_the_recorder_ship_outside_the_seed`:
    - `pump/pump.py` is copied to `/usr/local/bin/pump.py`;
    - the recorder's three files go to `/usr/local/lib/recorder/`;
    - no COPY puts either under `/opt/agent`.

    This replaces Aurora's pump-image test held back in Task 1.
  - `test_the_image_runs_as_uid_and_gid_1000`: `groupadd --gid 1000 agent`, then `useradd … --uid 1000 --gid 1000 … agent`, then `USER agent`.
  - `test_the_environment_keeps_agent_writable_files_off_every_image_owned_process`: the ENV block sets `PYTHONNOUSERSITE=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `HOME=/home/agent`, `CARGO_HOME=/build/.cargo`, `CARGO_TARGET_DIR=/build/target` and `XDG_CACHE_HOME=/build/.cache`.
  - `test_every_mountpoint_is_made_and_owned_by_the_agent`: the `mkdir -p` and `chown` lines cover each mountpoint above.
  - `test_the_image_carries_no_aurora_world`: no `filigree`, `books`, `garden`, `sense` or `video` in `Dockerfile.agent`, matched on word boundaries so that `license` does not count as `sense`.
  - `test_the_dockerignore_keeps_test_leftovers_and_tests_out_of_the_image`: `.dockerignore` excludes `harness/tests/`, `harness/session_context.json`, `harness/tombstones/`, `recorder/tests/` and `pump/tests/`.
- [ ] **Step 2:** Run `python3 -m pytest tests/test_agent_image.py -p no:cacheprovider`. Expected: all fail against the current Dockerfile.
- [ ] **Step 3: Rewrite `Dockerfile.agent`,** in this order:
  1. The apt and pip layers and the cargo `config.toml`, unchanged.
  2. `groupadd --gid 1000 agent` and `useradd --create-home --uid 1000 --gid 1000 --shell /bin/bash agent`, before any `COPY --chown=agent:agent`.
  3. As root, `mkdir -p` and `chown agent:agent` for every mountpoint, `/work` included, so that `WORKDIR /work` does not create it root-owned.
  4. The COPYs:
     - the six-file seed into `/opt/agent/`;
     - `pump/pump.py` to `/usr/local/bin/pump.py`;
     - the recorder's three files to `/usr/local/lib/recorder/`;
     - the brief to `/opt/brief/`;
     - `services/` to `/opt/services/`;
     - the two pinned vehicle lines, byte-identical;
     - the entrypoint, and `containers/agent.env` to `/etc/agent.env`.
  5. The existing `chmod` and `__pycache__` cleanup.
  6. The ENV block. Keep `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1` and `LANG=C.UTF-8`, and add the six hardening variables. Drop the old supervisor's `AGENT_USER`, `AGENT_HOME`, `WORK_DIR`, `SEED_DIR` and `DIARY_DIR`, since the entrypoint's defaults carry those paths.
  7. `USER agent`, `WORKDIR /opt/agent`, then the seed `RUN`: Aurora's `git -c commit.gpgsign=false commit`, after the repo-local identity.
  8. `WORKDIR /work` and `ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]`.

  In `.dockerignore`, add the five exclusions.
- [ ] **Step 4:** Run `python3 -m pytest tests -p no:cacheprovider`. Expected: `121 passed`, which is 113 plus 8, with `test_vehicle_reconciliation.py` passing unchanged. Then run `python3 -m pytest harness/tests recorder/tests pump/tests` as separate processes. Expected: 210, 394 and 100, unchanged.
- [ ] **Step 5:** Run `uvx ruff check . --no-cache` (expected: clean). Commit: `image: Aurora's seed repository, the pump and the recorder in the agent image`.

---

## What this plan does not do

- **No `docker build` and no running container (3c).** The Postgres version under `/usr/lib/postgresql/*/bin` is verified when 3c first builds the image, and "the image builds and `pg_isready` answers on `$RUN_DIR`" is a 3c acceptance item.
- **No compose, volumes, loop images, roster or `prepare_host.sh` (3b).** These are handed to 3b, because they decide whether this image starts:
  - agents become `read_only: true`, with tmpfs at `/run/agent`, `/tmp`, `/home/agent` and `/work`;
  - every mount is a per-agent bind;
  - `LLM_SOCKET_PATH` moves to Aurora's default, `/llm/sock/core.sock`, inside each agent's own socket bind, replacing today's `/llm/sock/${slug}.sock`;
  - the `/shared` bind;
  - the recorder service runs `python /usr/local/lib/recorder/proxy.py`, with `TRANSCRIPT_DIR` (not `TRANSCRIPTS_DIR`) and `LLM_BASE_URL:-` empty by default, so the key is not lost.
- **No console seed (3c).** It needs `STREAM_MODEL_ALLOW_*` in `.env.example`, which is absent today, so the default seed would declare no streams.
- **No change to `containers/agent.env`, `serve_vehicle.sh` or the old services (plan 5).**
