# Aurora Port, Plan 3b: Bounded Volumes, the Roster and a Generated Compose — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every agent its own bounded, loop-mounted volumes (Aurora's image scheme, adapted to ten containers), move the roster out of the shared volume, and generate a flat `docker-compose.yml` in which every per-agent surface is bound per agent. That closes the cross-tenant pump, socket, console, window and telemetry paths, and the plan 3a deploy gate.

**Architecture:**
- **`scripts/volume_images.py`** is the single manifest of image kinds, sizes and mounts, adapted from Aurora's (`42faf41`) from "per host" to "per agent slug". Agent images are named `<kind>_<slug>`.
- **`scripts/create_volume_image.sh`** is Aurora's creator, uid changed.
- **`scripts/build_compose.py`** writes the whole `docker-compose.yml` from the manifest. Services reference slugs through compose variables (`${FLEET_N_SLUG:-agent_N}`), so the committed file is the same whatever roster was drawn. A test pins committed equal to generated.
- **`scripts/prepare_host.sh`** draws the roster into `operator/`, refuses while the old `volumes/` layout is present, then plans, creates and checks the images. Mounting needs root, and the script prints exactly what to run.

**Tech Stack:** Python 3 standard library, POSIX `sh`, pytest. No Docker daemon and no root in any test.

**Spec:** `docs/superpowers/specs/2026-10-09-aurora-port-design.md`, sections 2, 3, 3.2, 3.3, 5 and 9. Plans 1, 2 and 3a are complete on `aurora-port`.

## John's decisions (2026-10-09) this plan implements

- **Port Aurora's bounded loop images** (rather than plain binds).
- **Default sizes, 137.3 GiB in all** (12.625 GiB per agent and 11.06 GiB shared; John was offered "about 135 GB"):
  - per agent: `state` 2G, `build` 4G, `telemetry` 2G, `transcripts` 4G, `pump` 512M, `llm_sock` 64M, `llm_console` 64M;
  - shared: `shared` 8G, `diode` 2G, `fleet_ledger` 64M, `operator_telemetry` 1G.

  Each size is overridable in `.env`.
- **Old volumes:** `prepare_host.sh` refuses while the old layout is present and prints `mv volumes volumes.pre-aurora-2026-10-09` for the operator to run. It copies the roster out first and moves nothing itself.

## Rulings this plan carries (each also goes in the ledger)

- **Image names are `<kind>_<slug>`,** mounted at `<SPACE_VOLUMES_DIR>/<kind>_<slug>`, with compose sources at `${SPACE_VOLUMES_DIR:-./volumes}/<kind>_${FLEET_N_SLUG:-agent_N}/data`. Spec 5 wrote `./volumes/<x>/<slug>`, but Aurora's creator refuses `/` in a name. The isolation is the same.
- **The window is one shared `diode` image.** The vehicle and the fake diode bind its whole `data/` at `/diode`. Each agent binds only `data/<slug>` at `/diode/<slug>`, which `prepare_host` creates as uid 1000; no root is needed inside a 1000-owned `data/`.
  - The vehicle and diode services keep **short-syntax** `/diode` binds, because `tests/test_vehicle_reconciliation.py` pins `vehicle.volumes == diode.volumes` and a short entry ending `:/diode`. Their source must exist, and `prepare_host`'s check ensures it does.
  - Per-agent diode images would break the vehicle's parent view.
- **`SPACE_*` variable names** replace Aurora's `AURORA_*`:
  - `SPACE_VOLUMES_DIR` (default `./volumes`), `SPACE_VOLUME_IMG_DIR` (default `./volume-images`, outside `volumes/` so the archive `mv` leaves image files alone), `SPACE_VOLUME_WARN_PERCENT`;
  - one `SPACE_<KIND>_SIZE` per kind.

  The agent count and slugs come from the roster block in `.env` (`FLEET_COUNT`, `FLEET_N_SLUG`), not `AURORA_HOSTS`.
- **The manifest is space code adapted from Aurora's, and is linted;** it is not a vendored file. Aurora's tests are ported by name where they carry over, with the adaptations listed in each task.
- **Operator telemetry is its own image.** `fleet_monitor` writes `fleet.jsonl` to `/telemetry` (rw), and each agent's telemetry image is bound read-only at `/telemetry/agents/<slug>` in the monitor and the review panel. The watchdog's `mirror_work` deletes everything else under an agent's `TELEMETRY_DIR`, so the two can never share a root.
- **Review and the monitor read old-format files that Aurora's harness no longer writes,** so they will show empty panels until plan 4 adapts them. 3b only gives them correct, read-only per-agent binds.
- **No transcripts mount for agents.** That is the spec's default; spec 10, item 4 is still open.
- **`/build` is a 4 GiB per-agent image,** where spec 5's table says "image, tmpfs". This carries plan 3a's ruling forward: a tmpfs counts against the 3 GB memory limit, the entrypoint empties the image at every start, and the lifetime is the same.
- **The fleet's size comes from the `.env` file alone.** `fleet()` reads `FLEET_COUNT`, `FLEET_SLUGS` and `FLEET_N_SLUG` from the env file, never from the process environment. Aurora lets the environment win, but here a stray `FLEET_COUNT=3` in the shell would make the volume tool disagree with the roster. The roster block is the one source.

## Global Constraints

- **No test runs as root, calls `mount`, `losetup` or `sudo`, or touches the real `volumes/`.** Host effects are faked with Aurora's `Probes` (manifest) and `Stubs` (creator and `prepare_host`) patterns, in `tmp_path`.
- **uid and gid 1000 everywhere Aurora says 65532:** `SERVICE_UID`, the creator's printed `chown` line, and the test constants.
- **The generated compose is flat, with no anchors, merge keys or `x-` sections.** It keeps:
  - `name: space-chassis`;
  - `worknet {internal: true}`, `modelnet {}`, `reviewnet {internal: true}` and `windowside {}`;
  - profiles: `agent_1` and `recorder_1` with no profile; agents and recorders 2–10 in `fleet`; `diode` in `diode`; `vehicle` in `vehicle`.
- **Every bounded per-agent mount is long-syntax** with `bind: {create_host_path: false}`. No agent mounts a parent directory that holds another agent's subdirectory. That is spec 2's one rule.
- **Agents** (`image: space-chassis-agent`; `agent_1` alone also carries `build: {context: ., dockerfile: Dockerfile.agent}`, so the image is built once):
  - `restart: unless-stopped`, which spec 3 relies on: a dead watchdog ends the container, and the restart reseeds;
  - `hostname: agent_N` and `stop_grace_period: 20s`;
  - `networks: [worknet]` and nothing else;
  - `read_only: true`, `cap_drop: [ALL]`, `no-new-privileges`, `init: true`;
  - tmpfs at `/tmp`, `/work` (1g), `/home/agent` (256m) and `/run/agent` (64m), each `uid=1000,gid=1000`;
  - `mem_limit ${AGENT_MEM:-3g}`, `cpus ${AGENT_CPUS:-1.0}`, `pids_limit 1024`;
  - environment `OPENROUTER_API_KEY: "sk-dummy"`, `LLM_MODEL`, `CONTEXT_WINDOW_TOKENS`, `PUMP_MAX_*`, `AGENT_SLUG`, `AGENT_NAME`, and no credential;
  - `depends_on: [recorder_N]`.
- **Recorders** (`image: space-chassis-agent`, `restart: unless-stopped`, `hostname: recorder_N`):
  - `entrypoint: ["python", "/usr/local/lib/recorder/proxy.py"]`;
  - `networks: [modelnet]` with `dns: [1.1.1.1, 8.8.8.8]`;
  - environment `AGENT_SLUG`, `FLEET_LEDGER_PATH: /ledger/ledger.jsonl`, `TRANSCRIPT_DIR: /transcripts`, `LLM_SOCKET_PATH: /llm/sock/core.sock`, `LLM_CONSOLE_FILE: /llm/console/console.json`, `LLM_BASE_URL: ${LLM_BASE_URL:-}` (empty by default, so `OPENROUTER_API_KEY` is used), `LLM_API_KEY`, `OPENROUTER_API_KEY`, `RECORDER_HOURLY_MAX`, `RECORDER_TOKEN_HOURLY_MAX`, `RECORDER_TOKEN_GLOBAL_HOURLY_MAX`, `RECORDER_CORE_RESPONSE_RESERVE`, and the `STREAM_*` block;
  - `read_only`, `tmpfs /tmp`, `pids_limit 512`, `mem_limit 512m`.
- **The fleet ledger image is mounted by recorders only,** rw at `/ledger`.
- **`/vendor/registry` and the cargo config stay plain read-only binds,** so the entrypoint's unbounded-volume reference is a real host filesystem.
- **Test names are full sentences. No skips and no xfails.** Deprecation warnings are errors.

## Review Focus

1. **A roster slug that would escape a path,** such as `../x`, a slash or a space, must never reach an image name, a mount point or a compose source. The roster's slug alphabet is checked again where names are built. (Task 2: `test_a_slug_outside_the_name_alphabet_is_refused_before_any_path_is_built`)
2. **A roster block in `.env` that disagrees with itself** (`FLEET_COUNT` ≠ the number of `FLEET_SLUGS` ≠ the number of `FLEET_N_SLUG` entries, or a gap in N), or a `FLEET_COUNT` set in the process environment, must make `plan` and `list` refuse or ignore the stray value, never plan for the wrong fleet. (Task 2: `test_a_roster_block_that_disagrees_with_itself_is_refused`, `test_a_fleet_count_in_the_process_environment_is_ignored`)
3. **Old data under `volumes/`** must stop `prepare_host` before any image is created, with the one `mv` command printed, and nothing moved. (Task 5: `test_prepare_host_refuses_the_old_layout_and_prints_the_archive_command`)
4. **No service mounts another agent's surface,** and the ledger is mounted by recorders only. This is checked over the generated text for every agent index. (Task 4: `test_no_agent_mounts_another_agents_surface`, `test_only_recorders_mount_the_ledger`)
5. **The recorder's key resolution.** With `LLM_BASE_URL` empty by default, a recorder uses `OPENROUTER_API_KEY`. A compose default of the OpenRouter URL would silently send an empty key. (Task 4: `test_the_recorder_upstream_defaults_empty_so_the_openrouter_key_is_used`)

---

## File structure

| Path | Responsibility |
|---|---|
| `scripts/env_file.py` | `value_text`, `env_value(key, path)`, `source_path()`: Aurora's `.env` reading, ported from `build_console_seed.py` |
| `scripts/roster.py` | modified: `--roster-dir` (default `./operator`) replaces `--work-dir` |
| `operator/` | gitignored; holds `roster.json` |
| `scripts/volume_images.py` | the manifest: kinds, sizes, `mounts_for(role, index, slug)`, `plan`, `check`, `list`, `fstab`, `names`, `root` |
| `scripts/create_volume_image.sh` | Aurora's creator, with uid 1000 in its printed `data/` line |
| `scripts/build_compose.py` | writes `docker-compose.yml` from the manifest |
| `docker-compose.yml` | generated, committed |
| `scripts/prepare_host.sh` | rewritten |
| `scripts/status.py` | reads `operator/roster.json` |
| `tests/compose_text.py` | Aurora's PyYAML-free compose reader, vendored |
| `tests/test_roster_location.py`, `tests/test_volume_images.py`, `tests/test_volume_creator.py`, `tests/test_compose_generated.py`, `tests/test_prepare_host.py` | root suite |
| `.env.example`, `.gitignore`, `CLAUDE.md` | sizes and variables, `operator/`, commands |

---

### Task 1: Move the roster to `operator/`

**Files:** Modify `scripts/roster.py`, `scripts/status.py`, `tests/conftest.py`, `tests/test_observer.py`, `.gitignore`. Create `tests/test_roster_location.py`.

**Interfaces:**
- **Produces:**
  - `roster.py --roster-dir DIR`, default `$ROSTER_DIR` or `./operator`, writing `DIR/roster.json` with the same fields as today. `--work-dir` is accepted as a deprecated alias for one release; it prints a stderr line and behaves as `--roster-dir`.
  - `status.py` reads `PROJECT/operator/roster.json`, through `status.ROSTER_PATH`.
- **Unchanged:** the `.env` block (`FLEET_COUNT`, `FLEET_NAMES`, `FLEET_SLUGS`, `FLEET_N_NAME`, `FLEET_N_SLUG`), and the slug alphabet `[a-z][a-z0-9_]*`. Check that alphabet in `roster.py` and pin it in Step 1.
- **Fixed:** when a roster already exists and `--env-file` is given, `roster.py` now rewrites that env file's block from it. Today it returns before writing, so `prepare_host.sh`'s "`.env` refreshed from the existing roster" line has been silently false, and a fresh `.env` never gets the block.

- [ ] **Step 1: Failing tests in `tests/test_roster_location.py`:**
  - `test_the_roster_is_written_to_the_operator_directory`: `roster.py --count 3 --seed 1 --roster-dir <tmp>/operator --env-file <tmp>/.env` writes `operator/roster.json` and the `.env` block.
  - `test_the_old_work_dir_flag_still_writes_but_says_it_is_deprecated`.
  - `test_every_drawn_slug_fits_the_image_name_alphabet`: 200 seeds, every slug fullmatches `[a-z][a-z0-9_]*`.
  - `test_status_reads_the_operator_roster`.
  - `test_an_existing_roster_refreshes_the_env_block`: draw into `operator/`, then run again with a new, empty `--env-file`. The block is written, and its slugs equal the roster's.

  Update `tests/test_observer.py`'s world to the new path. `tests/conftest.py`'s stub roster needs no change, because nothing reads it.
- [ ] **Step 2:** Run them and watch them fail on the missing flag and path.
- [ ] **Step 3: Implement.** Add `operator/` to `.gitignore`, with a comment that the roster is drawn per host.
- [ ] **Step 4:** Run `python3 -m pytest tests -p no:cacheprovider`. Expected: `129 passed` (124 + 5), and `test_observer` passes with its world moved. Run ruff (clean).
- [ ] **Step 5: Commit:** `roster: drawn into operator/, out of the volume the agents shared`.

---

### Task 2: The volume manifest

**Files:** Create `scripts/env_file.py`, `scripts/volume_images.py`, `tests/test_volume_images.py`.

**Interfaces:**
- `env_file`: `_value_text(raw) -> str` (private, as in Aurora), `env_value(key, path) -> str | None`, `source_path() -> Path` (`.env` if present, else `.env.example`). These are Aurora's `build_console_seed.py` lines 41–93, unchanged in behaviour.
- `volume_images`:
  - **Constants:** `SERVICE_UID = 1000`, `DATA_MODE = 0o755`, `FSTAB_OPTIONS`, `MIN_FREE_PERCENT = 10`, `DEFAULT_WARN_PERCENT = 80`, `CRITICAL_PERCENT = 95`, `SOURCE_ROOT = "${SPACE_VOLUMES_DIR:-./volumes}"`.
  - **`Kind(name, default_size, size_variable, scope, mounts)`,** where `scope` is `PER_AGENT` or `SHARED` and `mounts` is `((role, target, read_only, subpath), …)`.
    - **Roles:** `agent`, `recorder`, `monitor`, `review`, `window` (the vehicle and the fake diode).
    - **`subpath`:** `""` for the whole `data/`; `"{slug}"` binds `data/<slug>`, used only by the shared `diode` kind for agents; `"agents/{slug}"`.
    - **Targets** may contain `{slug}`.
  - **`KINDS`:**
    - `state` (agent `/state` rw)
    - `pump` (agent `/pump` rw)
    - `build` (agent `/build` rw)
    - `telemetry` (agent `/telemetry` rw; monitor and review `/telemetry/agents/{slug}` ro)
    - `transcripts` (recorder `/transcripts` rw; monitor and review `/transcripts/{slug}` ro)
    - `llm_sock` (agent `/llm/sock` ro; recorder `/llm/sock` rw)
    - `llm_console` (agent `/llm/console` rw; recorder `/llm/console` ro)
    - `shared` (shared: agent `/shared` rw)
    - `diode` (shared: agent `/diode/{slug}` rw with subpath `{slug}`; window `/diode` rw)
    - `fleet_ledger` (shared: recorder `/ledger` rw)
    - `operator_telemetry` (shared: monitor `/telemetry` rw; review `/telemetry` ro)

    Sizes are John's figures above.
  - **Functions:**
    - `fleet(source=None, environ=None) -> list[str]` returns the slugs from `FLEET_COUNT` and `FLEET_N_SLUG`, refusing gaps, mismatches and slugs outside the alphabet.
    - `names(slugs) -> list[str]`
    - `mounts_for(role, index, count) -> list[(source, target, read_only)]` emits sources and targets with `${FLEET_<index>_SLUG:-agent_<index>}` interpolation, for compose.
    - `plan`, `check`, `list_lines`, `fstab_lines`, `Probes`, `plan_report`, `check_image`, `check_report`, `main(argv, *, source, environ, probes)`, with subcommands `list`, `fstab`, `plan`, `check`, `names` and `root`. Each takes its slugs from `fleet()`.
  - Images are mounted at `<SPACE_VOLUMES_DIR>/<image name>`, with files at `<SPACE_VOLUME_IMG_DIR>/<image name>.img`. `SPACE_VOLUME_IMG_DIR` defaults to `./volume-images`, sibling to `volumes/`, so the archive `mv` leaves it alone.

- [ ] **Step 1: Port Aurora's `tests/test_volume_images.py`** at `42faf41` into `tests/test_volume_images.py`, keeping its `Probes`/`World` fakes.
  - **Carried with the same assertions,** apart from variable names (`AURORA_` → `SPACE_`) and uid strings (65532 → 1000): `parse_size_*`; the settings-precedence tests; the path tests; every alias-refusal test; `list_prints…`; `root_prints…`; `fstab_lines_carry…`; all `plan_*`; `healthy_image_is_ready`; the 17-case `check_fails_an_image_that_is_not_ready`; the symlink tests; the fill tests; `check_subcommand…`; `mountinfo_parsing…`; `manifest_does_not_import_the_compose_generator…`; `no_image_copies_the_host_volume_tooling`.

    Their helpers change: `_env_file()` writes a roster block (for example 3 slugs) into every env file, and every `_plan(tmp_path, count)` or `main([..., "--hosts", N])` call becomes a roster of N slugs, since `plan`, `list` and `check` take the fleet from `.env`.
  - **Rewritten for this topology:**
    - the image-count test (7 per agent + 4 shared: 74 at 10 agents, 25 at 3);
    - `names_are_listed…` (per-slug names);
    - `the_table_holds…figures` (John's sizes);
    - `list_reads_the_fleet_from_the_env_file`;
    - `a_kind_added…reaches_every_subcommand`;
    - `volumes_stays_out_of_git…`, which now asserts both `volumes/` and `volume-images/` in both `.gitignore` and `.dockerignore`;
    - `the_documented_image_totals_match_the_manifest`, against the total stated in `.env.example`'s comment rather than Aurora's README.
  - **Dropped:**
    - the build-dir warnings, `sense_console` and the host-suffix tests (Aurora-only);
    - `names_reads_no_file` and `names_requires_a_host_count`, because `names` now reads the roster from `.env`, which `prepare_host`'s old-layout check needs.
  - **New:**
    - `test_a_slug_outside_the_name_alphabet_is_refused_before_any_path_is_built`
    - `test_a_roster_block_that_disagrees_with_itself_is_refused`
    - `test_each_agent_s_images_are_named_by_its_slug`
    - `test_the_shared_window_is_bound_whole_only_by_the_window_services_and_by_subdirectory_for_agents`
    - `test_the_default_plan_for_ten_agents_totals_137_gibibytes`: exactly 12.625 GiB × 10 + 11.0625 GiB.
    - `test_a_fleet_count_in_the_process_environment_is_ignored`
- [ ] **Step 2:** Run them and watch them fail on the missing module.
- [ ] **Step 3: Implement** `scripts/env_file.py` and `scripts/volume_images.py`. The module docstring keeps Aurora's statement that this is operator tooling, run on the host, invoked by no component and shipped in no image. Add `volume-images/` to `.gitignore` and `.dockerignore`. Without it, the first `compose build` after `prepare_host` would tar about 137 GiB of images into the build context.
- [ ] **Step 4:** Run `python3 -m pytest tests -p no:cacheprovider`. Expected: everything green. Record the new count in the ledger, since the ported test file's size is only known after the port. Run ruff (clean).
- [ ] **Step 5: Commit:** `volumes: the bounded-image manifest, per agent, adapted from Aurora's`.

---

### Task 3: The image creator

**Files:** Create `scripts/create_volume_image.sh` (from `42faf41`) and `tests/test_volume_creator.py`.

- [ ] **Step 1:** Port Aurora's `tests/test_host_scripts.py` creator and mount-point tests (its lines 205–885 at `42faf41`), with the `Stubs` and `allocating` fixtures, into `tests/test_volume_creator.py`. Change `DATA_LINE` and the stubs' uid from 65532 to 1000. Drop the sense, corpus, vendor and garden script tests.
- [ ] **Step 2:** Copy the creator. Run the tests and watch exactly the uid assertions fail.
- [ ] **Step 3:** Change the creator's printed `chown -h 65532:65532` to `chown -h 1000:1000`.
- [ ] **Step 4:** Run the root suite (all green; count recorded in the ledger) and ruff.
- [ ] **Step 5: Commit:** `volumes: Aurora's image creator, with this world's uid`.

---

### Task 4: The generated compose

**Files:** Create `tests/compose_text.py` (from `42faf41`), `scripts/build_compose.py` and `tests/test_compose_generated.py`. Regenerate `docker-compose.yml`. Update `docker-compose.override.example.yml` minimally:
- `recorder` becomes `recorder_1`, and `UPSTREAM_SOCKET` and `UPSTREAM_STREAMING`, which the old recorder read, are dropped;
- the `diode` service's `./volumes/diode:/diode` becomes `${SPACE_VOLUMES_DIR:-./volumes}/diode/data:/diode`. Compose merges volumes by target, so the old line would replace the base bind with the image root, where `serve_vehicle.sh` would sweep `data` and `lost+found` as slugs.

3c rewrites the file.

**Interfaces:**
- `build_compose.build_text(count: int = 10) -> str` and `main()`, which writes `docker-compose.yml` atomically.
- Services:
  - `agent_1`..`agent_N` and `recorder_1`..`recorder_N`;
  - `fleet_monitor`, `review`, `diode` and `vehicle`, carrying today's keys and environment, with their volumes replaced by the manifest's binds;
  - `vehicle` and `diode` keep the short-syntax `${SPACE_VOLUMES_DIR:-./volumes}/diode/data:/diode`.
- Every service has a json-file logging block (`max-size 10m`, `max-file 5`). `HEADER` says the file is generated, and how to regenerate it. It also says that `--profile fleet` needs a roster of `FLEET_COUNT` = 10: the file always declares ten, and a smaller roster has no images for agents past it, so `create_host_path: false` refuses them.

- [ ] **Step 1: Failing tests in `tests/test_compose_generated.py`,** reading with `compose_text`:
  - `test_the_committed_compose_is_exactly_what_the_generator_writes`
  - `test_no_agent_mounts_another_agents_surface`: for each index, every agent bind source carries only that index's slug variable, or is `shared` or `/vendor`.
  - `test_only_recorders_mount_the_ledger`
  - `test_every_bounded_mount_binds_an_image_data_directory_that_must_exist`: a long syntax with `create_host_path: false` and a source under `SOURCE_ROOT/<name>/data` (plus `/<slug>` for the agents' diode).
  - `test_agents_join_only_worknet_and_recorders_only_modelnet`
  - `test_the_agent_runs_read_only_with_its_tmpfs_and_limits`
  - `test_the_agent_environment_carries_no_credential_and_the_dummy_key`, adapted from Aurora's `test_agent_credentials`.
  - `test_the_recorder_upstream_defaults_empty_so_the_openrouter_key_is_used`
  - `test_each_agent_depends_on_its_own_recorder`
  - `test_agents_and_recorders_past_the_first_are_in_the_fleet_profile`
  - `test_every_service_logs_with_a_bounded_json_file`
  - `test_only_the_read_only_vendor_mounts_are_outside_the_volumes_root`
  - `test_every_agent_and_recorder_restarts_unless_stopped`
  - `test_the_smoke_override_binds_the_window_image_data_not_its_mount_point`

  Also port Aurora's reader tests for `compose_text`: long-syntax parsing, short syntax, and eight-space keys. `tests/test_vehicle_reconciliation.py` must still pass unchanged.
- [ ] **Step 2:** Run them and watch them fail on the missing generator.
- [ ] **Step 3: Implement** `build_compose.py` using `volume_images.mounts_for`, and run it to write `docker-compose.yml`. Then run `docker compose --profile fleet config -q`, as CLAUDE.md lists it, if `docker` is on `PATH`: it is a parse check that starts nothing. If `docker` is absent, ledger that.
- [ ] **Step 4:** Run the root suite (all green; count recorded) and ruff.
- [ ] **Step 5: Commit:** `compose: generated from the volume manifest, every agent bound to its own surfaces`.

---

### Task 5: `prepare_host.sh`

**Files:** Rewrite `scripts/prepare_host.sh`. Create `tests/test_prepare_host.py`. Modify `.env.example` (the `SPACE_*` variables with sizes and a commented total; `STREAM_*` names left for 3c) and `CLAUDE.md` (the Commands lines for `prepare_host`, `volume_images.py check` and `build_compose.py`).

**Behaviour:**
1. **Registry.** Refuse without `vendor/registry`. Keep the two strings `test_observer` pins.
2. **`.env`.** Copy `.env.example` to `.env` when absent.
3. **Roster.** Run `roster.py --roster-dir operator --env-file .env`, which keeps an existing roster unless `REROLL=1`. **First**, if `volumes/work/roster.json` exists and `operator/roster.json` does not, copy it there.
4. **Old layout.** If any of `volumes/{work,home,diary,pump,transcripts,telemetry,llm_sock}` exists, print the old-layout paragraph and `mv volumes volumes.pre-aurora-2026-10-09`, and exit 2 without changing anything else. None of these is ever an image mount point in the new layout, since the per-agent images are `<kind>_<slug>`. `volumes/diode` is left out, because it is the shared window image's mount point; any real old layout also has `work/`.
   - This check comes before the creator runs: once images are mounted under `volumes/`, the archive `mv` would no longer be possible.
   - Ordering note for the operator: `compose up` must not run before `prepare_host` has completed, because the vehicle and diode short-syntax binds would create a root-owned `volumes/diode/data` that the creator then refuses to mount over.
5. **Plan.** Run `volume_images.py plan`; a failure is fatal.
6. **Create.** For each `list` line, run `create_volume_image.sh`, collecting exit-2 operator steps into a BLOCK. Any other non-zero exit is fatal.
7. **Window directories.** When the `diode` and `operator_telemetry` images are mounted and their `data/` exist, make `diode/data/<slug>/output` and `operator_telemetry/data/agents/<slug>` for each slug, as uid 1000, with no sudo.
8. **fstab.** Print `volume_images.py fstab` under "/etc/fstab lines that mount the images at boot:".
9. **Finish.** With a BLOCK, print it and exit 2. Otherwise run `volume_images.py check` and exit with its result.

The script itself never runs `sudo`. Only the creator's `sudo -n mount` does, as in Aurora.

- [ ] **Step 1: Failing tests in `tests/test_prepare_host.py`,** with a `PreparedTree` adapted from Aurora's: a temp copy of the scripts, stub `python3` helpers, and stub `sudo`/`mount`:
  - `test_prepare_host_refuses_without_the_crate_registry`
  - `test_prepare_host_copies_an_old_roster_into_the_operator_directory_once`: also asserts that a fresh `.env` (copied from `.env.example`) ends with the roster block, which is Task 1's fix.
  - `test_prepare_host_refuses_the_old_layout_and_prints_the_archive_command`: exit 2, the `mv` line printed, and nothing under `volumes/` moved or created.
  - `test_prepare_host_collects_operator_steps_and_exits_2`
  - `test_a_fatal_creator_error_stops_prepare_host`
  - `test_prepare_host_makes_each_agent_s_window_and_telemetry_directories_when_the_images_are_mounted`
  - `test_prepare_host_ends_with_the_check_when_nothing_is_left_for_the_operator`
- [ ] **Step 2:** Run them and watch them fail against the current script.
- [ ] **Step 3: Implement** the script, `.env.example` and CLAUDE.md.
- [ ] **Step 4:** Run the root suite and the harness, recorder and pump suites (all green; counts recorded), plus ruff.
- [ ] **Step 5: Commit:** `host: prepare_host draws the roster, refuses the old layout, and plans and checks the images`.

---

## What this plan does not do

- **Run `prepare_host.sh` for real, create any image, mount anything, or edit `/etc/fstab`.** Those need root on John's host. The plan's output is the script and its printed steps; John runs them, or approves 3c doing so.
- **The console seed, the smoke stack, `verify_containment.sh` and the first image build (3c).**
- **Adapting review, the monitor and status to Aurora's formats (plan 4).**
- **For 3c:** the entrypoint's `MOUNT_ROOTS` lists `/diode`, now the image's rootfs mountpoint, so the unbounded warning never covers `/diode/<slug>`. 3c should list the agent's actual window path.
- **Rewriting CLAUDE.md's invariants or `docs/design.md` (plan 5).**

The plan 3a deploy gate (per-agent `/pump` and `/telemetry`) is closed by Task 4's generated compose. That is pinned by `test_no_agent_mounts_another_agents_surface`, and 3c re-verifies it live.
