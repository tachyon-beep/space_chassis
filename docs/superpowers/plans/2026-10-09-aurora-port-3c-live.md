# Aurora Port, Plan 3c: The First Live Run — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the agent image for the first time. Run a three-agent smoke stack against a stub model, with the contract fixture as the window. Prove the spec's acceptance checks 1–8 and its containment invariants against real containers.

**Architecture:**
- **Console seed:** ported from Aurora, so agents start with a declared console.
- **Stub model:** Aurora's, ported and extended with *cues*: a file per recorder that makes the stub's next reply a chosen tool call. Without them a stub could never call `done`, `reset` or `run`.
- **Smoke stack:** a Python orchestrator in `live/` builds a scratch volume root of plain `data/` directories (no images, no root), an env file with no real credential, and a generated override. It brings up `stub`, `recorder_1..3`, `agent_1..3` and the fake diode.
- **Acceptance suite:** `live/` is outside the root `testpaths` and run explicitly. A session fixture owns the stack.
- **Containment script:** `scripts/verify_containment.sh` is rewritten for the per-agent topology, with the T9 key leak closed.

**Tech Stack:** Docker 29.8 and Compose v5.6 on the host; Python 3 standard library and pytest; POSIX `sh`.

**Spec:** `docs/superpowers/specs/2026-10-09-aurora-port-design.md`, sections 2, 3.3, 5 and 9. Plans 1, 2, 3a and 3b are complete on `aurora-port`.

## Rulings this plan carries (each also goes in the ledger)

- **The smoke run uses plain directories, not mounted images.** `SPACE_VOLUMES_DIR` points at a scratch tree under the repository (`.smoke-*/`, gitignored, on the same filesystem as `/vendor/registry`, as Aurora's verify keeps it). Creating images needs root, which stays John's. So the smoke run proves topology, containment and lifecycle, but not the size bounds: every mount root draws the "no size boundary" warning, which is expected and asserted. The bounds are already proven offline by plan 3b's tests.
- **Slugs default to `agent_N`.** The smoke env file carries no roster block, so compose's `${FLEET_N_SLUG:-agent_N}` defaults apply, and the real `.env`'s roster and key never reach the smoke stack. The orchestrator always passes `--env-file`.
- **The fake diode joins `windowside` only.** The base gives `diode` `[worknet, windowside]`, and spec 5 says the fake diode does not join `worknet`. The override uses `networks: !override [windowside]`; Compose v5.6 supports it.
- **The live fleet-cap check is not run live.** Its arithmetic is pinned by plan 2's unit tests and its wiring by plan 3b's compose tests. Live, the per-agent cap is exercised on `recorder_3`, set low through the override. A live fleet cap would starve every agent in the run.
- **The smoke stack runs only the six fleet services, the stub and the fake diode.** `fleet_monitor` and `review` bind all ten agents' records and still run the old services until plan 4.

## Global Constraints

- **No `sudo`, no image creation, no `mount`, and nothing written under the real `volumes/`, `operator/` or `.env`.** The smoke project name is `space_chassis_smoke_<pid>`, so it can never touch a `space-chassis` stack.
- **Teardown always runs,** even on failure: `compose down -v --remove-orphans` for the smoke project, then the scratch tree is removed. The tree is owned by uid 1000, which is the operator's, so no root container is needed.
- **The real model key never enters the smoke stack, a process's argv, or a log.** The env file sets `OPENROUTER_API_KEY` to `sk-smoke-dummy` and points `LLM_BASE_URL` at the stub.
- **Live tests are in `live/`, outside `testpaths`,** and are run with `python3 -m pytest live -q`. They take minutes; the ledger records the time. No live test is skipped or marked xfail: a missing docker is a failure with that message.
- **Test names are full sentences.** Every offline test lands in the root suite or its own directory's suite, as before.

## Review Focus

1. **A crash or Ctrl-C mid-run must still tear the smoke stack down.** The session fixture's finalizer and an `atexit` both call `down`, and a second `down` is harmless. (Task 3: `test_the_orchestrator_tears_down_even_when_setup_fails`)
2. **A cue file for one recorder must never steer another agent's stub replies.** Cues are keyed by the requesting recorder's IP address, resolved by the orchestrator from `docker inspect`. (Task 2: `test_a_cue_is_served_only_to_its_own_client`)
3. **The containment script must never put a secret in argv.** The key is passed to `grep -F -f -` on stdin and compared by fingerprint, and the script never echoes it. (Task 4: `test_verify_containment_passes_no_secret_in_any_argv`)
4. **The smoke env file must hold no real credential, and compose must read it rather than `.env`.** (Task 3: `test_the_smoke_env_file_carries_no_real_key_and_compose_is_pointed_at_it`)
5. **Every recovery-timing wait must be bounded and must fail with what it was waiting for,** never hang. That covers the `done` 60 s sleep, the 60 s probation, and the ladder's restarts. (Task 5: the `wait_for` helper, used by every live test)

---

## File structure

| Path | Responsibility |
|---|---|
| `scripts/build_console_seed.py` | Aurora's generator: `STREAM_MODEL_ALLOW_*` → `llm_console_seed.json` (gitignored) |
| `Dockerfile.agent`, `containers/entrypoint.sh` | COPY the seed to `/usr/local/share/space/llm_console_seed.json`; cp-if-absent into `/llm/console/console.json`; `MOUNT_ROOTS` adds `/diode/*` |
| `live/stub_llm.py` | Aurora's `verify_stub_llm.py`, plus cues |
| `live/stack.py` | the smoke orchestrator: scratch root, env file, override, build, up, exec, logs, down |
| `live/conftest.py`, `live/test_acceptance.py`, `live/test_containment.py` | the live suite |
| `scripts/verify_containment.sh` | rewritten for the per-agent topology |
| `tests/test_console_seed.py`, `tests/test_live_stub.py`, `tests/test_live_stack.py`, `tests/test_verify_containment.py` | offline tests in the root suite |

---

### Task 1: The console seed

**Files:**
- Create: `scripts/build_console_seed.py` (from Aurora `42faf41`, `REPO_ROOT` and output path unchanged), `tests/test_console_seed.py`
- Modify: `Dockerfile.agent`, `containers/entrypoint.sh`, `.env.example`, `.gitignore`, `scripts/prepare_host.sh`, `tests/test_agent_image.py`, `tests/test_agent_entrypoint.py`

**Behaviour:**
- **Generator:** `build_console_seed.py [--source PATH]` writes `llm_console_seed.json` at the repository root. It reads `STREAM_MODEL_ALLOW_TEXT` and `STREAM_MODEL_ALLOW_VISION` from `--source`, else from `.env`, else from `.env.example`. With both empty it writes `{"enable_streams": true, "streams": {}}`. More than eight streams is refused.
- **`.env.example`:** gains active, empty `STREAM_MODEL_ALLOW_TEXT=`, `STREAM_MODEL_ALLOW_VISION=`, `STREAM_HOURLY_MAX=` and `STREAM_TOKEN_HOURLY_MAX=` lines, with a comment saying declared streams are off until a model is allowed.
- **Image:** `Dockerfile.agent` copies `llm_console_seed.json` to `/usr/local/share/space/llm_console_seed.json`, outside `/opt/agent`.
- **Entrypoint:** before the hand-off, runs `[ -e "$LLM_CONSOLE_DIR/console.json" ] || cp "$CONSOLE_SEED" "$LLM_CONSOLE_DIR/console.json" || echo "warning: could not seed the llm console" >&2`, with `LLM_CONSOLE_DIR=/llm/console` and `CONSOLE_SEED=/usr/local/share/space/llm_console_seed.json` as overrides.
- **Host:** `prepare_host.sh` runs the generator after the roster and before the images.

- [ ] **Step 1:** Port Aurora's `tests/test_llm_console_seed.py` into `tests/test_console_seed.py`:
  - Aurora's `ROOT/"entrypoint.sh"` becomes `containers/entrypoint.sh`.
  - Aurora's `ROOT/"Dockerfile"` and `/usr/local/share/aurora/` become `Dockerfile.agent` and `/usr/local/share/space/`.
  - `recorder_streams` is imported from `recorder/`.
  - The generator tests run it with `--source <tmp file>`.

  Drop its Aurora-only assertions about the garden. Add `test_an_empty_allow_list_seeds_no_stream`. Extend `tests/test_agent_image.py` and `tests/test_agent_entrypoint.py` with one test each, for the COPY and for cp-if-absent: a present `console.json` is left untouched.
- [ ] **Step 2:** Run them and watch them fail.
- [ ] **Step 3:** Implement. Generate the seed once (`python3 scripts/build_console_seed.py --source .env.example`) so the build context has it.
- [ ] **Step 4:** Run the root suite and ruff (all green; record the counts).
- [ ] **Step 5: Commit:** `console: the llm console seed, generated from the allow lists and seeded once into each agent`.

---

### Task 2: The cued stub model

**Files:** Create `live/stub_llm.py` and `tests/test_live_stub.py`.

**Behaviour:** Aurora's `scripts/verify_stub_llm.py` at `42faf41`, unchanged in what it does without cues:
- It serves `POST */chat/completions` with a `list_dir` tool call, and `GET` returns 200.
- Every `VERIFY_STUB_TURNS_PER_INCARNATION`-th request (default 40) per client IP gets a plain stop.
- It sleeps `VERIFY_STUB_DELAY_SECONDS` (default 2.0) before each reply.

The **addition is cues.** With `STUB_CUE_DIR` set (default unset, so no cues):
- Before answering a client at address `A`, the stub looks for `STUB_CUE_DIR/A.json`.
- If it exists, the stub reads it and renames it to `A.json.served`. The file holds `{"name": <tool>, "arguments": <object>}`, or `{"stop": true}`.
- The stub then answers with exactly that tool call, or a plain stop.
- A malformed cue answers 500 with the parse error, and is renamed `A.json.bad`.

- [ ] **Step 1: Failing tests in `tests/test_live_stub.py`.** They run the stub in a thread on an ephemeral port and use `http.client`:
  - `test_without_a_cue_the_stub_lists_the_directory`
  - `test_every_nth_request_from_one_client_stops_the_incarnation`
  - `test_a_cue_is_served_once_as_the_named_tool_call`
  - `test_a_cue_is_served_only_to_its_own_client`, faking the client address by binding the client socket to `127.0.0.2`
  - `test_a_stop_cue_ends_the_incarnation`
  - `test_a_malformed_cue_is_a_500_and_set_aside`
  - `test_a_get_is_the_readiness_probe`
- [ ] **Step 2:** Watch them fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the root suite and ruff.
- [ ] **Step 5: Commit:** `live: Aurora's stub model, with cues that make its next reply a chosen tool call`.

---

### Task 3: The smoke orchestrator

**Files:** Create `live/stack.py` and `tests/test_live_stack.py`. Modify `.gitignore` (add `.smoke-*/`) and `docker-compose.override.example.yml`, which becomes a pointer: "the smoke stack is generated by `live/stack.py`".

**Interfaces** (`live/stack.py`):
- `class SmokeStack(agents: int = 3, recorder_overrides: dict[int, dict] | None = None)`, with these methods:
  - `prepare()` makes the scratch root `<repo>/.smoke-<pid>/`. Under it:
    - `volumes/<name>/data` for every name in `volume_images.names([f"agent_{n}" ...])`, plus `volumes/diode/data/agent_<n>/output`;
    - `cues/`;
    - `smoke.env`, holding `OPENROUTER_API_KEY=sk-smoke-dummy`, `LLM_BASE_URL=http://stub:8199/v1`, `LLM_API_KEY=sk-stub`, `SPACE_VOLUMES_DIR=<root>/volumes`, `FLEET_SLUGS=agent_1,agent_2,agent_3` and nothing else;
    - `override.yml`.
  - **The override (`override.yml`):**
    - a `stub` service: image `space-chassis-agent`, entrypoint `python /opt/live/stub_llm.py`, environment `VERIFY_STUB_PORT=8199`, `STUB_CUE_DIR=/cues`, `VERIFY_STUB_DELAY_SECONDS=0.2`, `VERIFY_STUB_TURNS_PER_INCARNATION=40`, volumes `./live:/opt/live:ro` and `<root>/cues:/cues`, `networks: [modelnet]`, read-only, caps dropped;
    - `recorder_N` gets `depends_on: [stub]` plus that recorder's `recorder_overrides[N]` environment;
    - `diode` runs `python /opt/fake/fake_diode.py`, with `./contract/fake_diode.py:/opt/fake/fake_diode.py:ro`, `AGENT_SLUGS=agent_1,agent_2,agent_3` and `networks: !override [windowside]`.
  - `compose(*args, check=True) -> CompletedProcess` runs `docker compose -p space_chassis_smoke_<pid> --env-file <root>/smoke.env -f docker-compose.yml -f <root>/override.yml --profile fleet --profile diode *args`.
  - `build()` builds `agent_1`, which builds the image, after `build_console_seed.py --source .env.example`.
  - `up()` runs `up -d stub recorder_1..N agent_1..N diode`.
  - `exec(service, *argv, stdin=None) -> CompletedProcess`
  - `logs(service) -> str`
  - `recorder_ip(n) -> str`, from `docker inspect` on `modelnet`.
  - `cue(n, tool, arguments)` writes `cues/<recorder_ip(n)>.json`.
  - `down()` runs `down -v --remove-orphans`, then removes the scratch tree. It is idempotent.
- `wait_for(predicate, *, timeout, every=1.0, what) -> value` raises `TimeoutError(f"waited {timeout}s for {what}")`.

- [ ] **Step 1: Failing offline tests in `tests/test_live_stack.py`.** These run no docker: they stub `subprocess.run` and inspect the files `prepare()` writes.
  - `test_prepare_makes_every_bind_source_for_three_agents`
  - `test_the_smoke_env_file_carries_no_real_key_and_compose_is_pointed_at_it`
  - `test_the_override_points_each_recorder_at_the_stub_and_keeps_the_fake_diode_off_worknet`
  - `test_every_compose_call_names_the_smoke_project_and_env_file`
  - `test_the_orchestrator_tears_down_even_when_setup_fails`
  - `test_down_twice_is_harmless`
  - `test_wait_for_raises_with_what_it_was_waiting_for`

  Also: `docker compose ... config -q` over the generated override parses. This is the one docker call, a parse only.
- [ ] **Step 2:** Watch them fail. **Step 3:** Implement. **Step 4:** Run the root suite and ruff.
- [ ] **Step 5: Commit:** `live: the smoke stack orchestrator, on scratch plain directories with no real credential`.

---

### Task 4: `verify_containment.sh` for the per-agent topology

**Files:** Rewrite `scripts/verify_containment.sh`. Create `tests/test_verify_containment.py`.

**Behaviour:** It runs against a stack that is up. It takes `COMPOSE` (the full compose command prefix, so it works on the smoke project) and `AGENTS` (default: every running `agent_*`). For each agent it prints PASS or FAIL lines and exits 1 on any FAIL:
- **No outward route:** `getent hosts example.com` fails, and a TCP connect to `1.1.1.1:443` fails.
- **The key is the dummy:** the agent's `/proc/1/environ` carries `OPENROUTER_API_KEY=sk-dummy`.
- **The real key is nowhere visible.** It is read from the recorder's environment with `docker inspect --format` and piped on stdin to `docker compose exec -T <agent> grep -rlF -f - /work /state /shared /etc`. It is never passed as an argument and never printed.
- **The recorder socket cannot be replaced:** it exists, a connect succeeds, and an unlink fails.
- **No sibling surface:** no other agent's `/diode/<slug>` exists in this agent, `/transcripts` is not mounted, and `/ledger` is not mounted.
- **Its own Postgres answers** (`pg_isready -h /run/agent`), and a peer's listener on `worknet` is reachable.
- **No recorder is reachable** from the agent by its service name.
- **The review panel's checks,** carried as before, when `review` is running.

`entrypoint.sh`'s `MOUNT_ROOTS` gains the agent's own `/diode/*` directory, so the unbounded-volume warning covers the window it actually binds.

- [ ] **Step 1: Failing offline tests:**
  - `test_verify_containment_passes_no_secret_in_any_argv`: every `docker`/`grep` invocation in the script is read as text. No argument interpolates the key variable, and the key travels on stdin.
  - `test_the_script_never_echoes_the_key`
  - `test_the_script_takes_its_compose_command_and_agents_from_the_environment`
  - `test_the_entrypoint_warns_about_the_agent_s_own_window_directory`, extending `test_agent_entrypoint.py`'s harness.
- [ ] **Step 2:** Watch them fail. **Step 3:** Implement. **Step 4:** Run the root suite and ruff.
- [ ] **Step 5: Commit:** `containment: the verify script for one container per agent, with the key kept off argv`.

---

### Task 5: The live acceptance suite

**Files:** Create `live/conftest.py`, `live/test_containment.py` and `live/test_acceptance.py`. Modify `CLAUDE.md` (Commands: `python3 -m pytest live -q   # the first live run: builds the image and runs the smoke stack; minutes`).

**The session fixture `stack`** runs `SmokeStack(3, recorder_overrides={3: {"RECORDER_HOURLY_MAX": "4"}})`, then `prepare()`, `build()`, `up()`, and waits until each agent's watchdog has started (the `agent_stdout.log` is growing). It yields, and finally calls `down()`.

- [ ] **Step 1: Write the live tests,** each mapped to the spec:
  - `test_the_image_builds_and_each_agent_s_postgres_answers`
  - `test_containment_holds_for_every_agent` (spec 9.6): runs `scripts/verify_containment.sh` with `COMPOSE` set to the smoke prefix, and asserts exit 0.
  - `test_an_agent_that_moves_baseline_to_its_own_code_and_calls_done_starts_fresh_on_it` (spec 9.1):
    1. Cue agent_1 with `run`: `printf '\nSMOKE_MARK = 1\n' >> agent.py && git commit -qam mark && git tag -f baseline`.
    2. Then cue `done` with `{"message": "marked"}`.
    3. Wait at most 120 s for a new incarnation.
    4. Assert `/work/agent.py` contains `SMOKE_MARK`, `/work/tombstones/` holds an archived session, and the new conversation does not contain the old one.
  - `test_a_broken_release_walks_the_ladder_to_rescue_with_a_note_at_each_step` (spec 9.2):
    1. Through `exec`, commit a syntactically valid `agent.py` that exits 1, and move `baseline` onto it.
    2. Wait for `aurora-recovery.json`'s `selected.ref` to be `refs/tags/rescue`.
    3. Assert the recovery notes for `baseline_same`, `baseline_new` and `rescue_new` were each published.
    4. Then break `rescue` too, and assert the container restarts and boots from the seed. The note says "started from the image seed".
  - `test_an_edited_watchdog_re_executes_and_a_killed_one_reseeds` (spec 9.3):
    1. Append a comment to `/work/watchdog.py`. Assert the log line `watchdog file changed; terminating agent and re-executing self`.
    2. `kill -9` the watchdog (pid 1's child under tini). Assert the container's restart count rises and `/work` is reseeded.
  - `test_reset_keeps_the_conversation_and_done_archives_it` (spec 9.4): using cues, `reset` leaves `session_context.json` and `done` moves it to `tombstones/`.
  - `test_one_agent_s_broken_release_and_a_broken_shared_module_leave_the_others_running` (spec 9.5):
    1. Break agent_2's release.
    2. Put a broken module in `/shared` that only agent_2's harness imports, via its edited `agent.py`.
    3. Assert agent_1's and agent_3's watchdogs keep making progress and their containers never restart.
  - `test_the_per_agent_cap_refuses_and_the_agent_pauses_with_jitter` (spec 9.7): agent_3's recorder has `RECORDER_HOURLY_MAX=4`. Wait for its transcript to record a 429 `request(s) per hour`, and for agent_3's watchdog to log `action pause`.
  - `test_nothing_planted_in_home_state_or_shared_runs_in_image_owned_processes` (spec 9.8):
    1. Plant `sitecustomize.py` and `usercustomize.py` in `/state`, `/shared` and `$HOME/.local/...`, each writing a marker.
    2. Plant `$HOME/.gitconfig` with `core.hooksPath` pointing at a marker-writing hook.
    3. Trigger a watchdog git restore by breaking `agent.py`.
    4. Assert no marker appears.
- [ ] **Step 2: Run the live suite.** `python3 -m pytest live -q -p no:cacheprovider`. This is the first build and the first start, so findings are expected. Each defect it shows is fixed test-first in the owning module (the entrypoint, Dockerfile, harness or recorder), with a failing offline test where one can be written, and recorded in the ledger. Record the wall time.
- [ ] **Step 3:** Run the root, harness, recorder and pump suites and ruff (all green). Commit: `live: the acceptance suite, run green against the first image`.

---

## What this plan does not do

- **Create, mount or check real volume images.** That is John's root step, with `prepare_host.sh`'s printed commands.
- **Adapt the review panel, monitor or status to the new formats (plan 4).**
- **Write the mission prompts or retire the old runtime (plan 5).** The live run uses Aurora's placeholder prompts; the stub ignores them.
- **A live fleet-cap check.** See Rulings.
