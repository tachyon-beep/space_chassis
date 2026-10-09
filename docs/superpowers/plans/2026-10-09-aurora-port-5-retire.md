# Aurora port, plan 5: retire the old runtime, one test suite, the docs rewritten

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The space harness has one runtime, Aurora's.
- The old one is deleted: `services/chassis.py`, `supervisor.py`, `recorder.py`, `pump.py`, `tasks/`, `endurance/`, and `containers/agent.env`.
- The test suites run as one `pytest`.
- The repository's documents describe the world as it now is.
- The agent-facing text, meaning the prompts and the brief, is drafted for John's approval, not shipped.

**Architecture:**
- **Deletion order is test-first.** The shared `tests/conftest.py` imports `endurance/` and the old services at import time, so the tests are rewritten first and the code is deleted second.
- **What stays in `services/`.** The operator surfaces remain: `common`, `health`, `fleet_monitor` and `review`. The image copies those four files and nothing else.
- **What goes when the old modules do.** The bare-name clashes (`chassis`, `pump`, `recorder`) vanish with the deleted modules, so `testpaths` can take every suite.
- **One `pytest` command** runs the root suite, the harness, recorder and pump suites, and the vehicle's referee.

**Tech Stack:** Python 3, pytest, ruff, docker (for the live suite).

**Spec:** `docs/superpowers/specs/2026-10-09-aurora-port-design.md`: §6 (prompts and brief), §7 (retired), §9 (acceptance), §10 items 2–4 (open for John).

## Rulings this plan rests on

1. **The prompts and the brief are drafted, not shipped** (spec §6: "John approves the final text").
   - Drafts are written to `docs/drafts/` as complete replacement files: `system_prompt.txt`, `user_prompt.txt`, `WORLD.md` and `PROTOCOL.md`.
   - The shipped `harness/system_prompt.txt`, `harness/user_prompt.txt` and `brief/` stay exactly as they are until John approves. There is no "cannot wait" exception: nothing is deployed before he approves, so nothing is urgent.
   - Every guard in this plan exempts the shipped brief and prompts, with a comment that points to `docs/drafts/` and spec §10.2.
   - `docs/drafts/README.md` states what the shipped text still claims that is false, including `harness/system_prompt.txt:1`'s "nothing you do can damage the environment itself", the line spec §6 names.
2. **History is left as history.** These still cite retired files, and none of them is edited:
   - `docs/superpowers/plans/2026-09-12-chassis-lifespan-control.md`;
   - the untracked `docs/plans/`;
   - the frozen corpus `docs/deep_research/` (`integration/*`, which `CLAUDE.md` calls the map);
   - the vehicle submodule, which is another agent's.
3. **The operator's on-disk leftovers are the operator's.** The old `volumes/` layout and `endurance/runs/` stay where they are, as do untracked `__pycache__` directories. `.gitignore` and `.dockerignore` keep ignoring `endurance/runs/` (commented, and a permanent exception to the guards), and `prepare_host.sh` keeps refusing the old layout. A deletion is checked with `git ls-files`, never by whether a directory exists.
4. **Every test spec §9 names is mapped.** `tests/test_acceptance_map.py` holds a table from each §9 name to the tests that pin it in this repository, or to a line saying it was dropped and why (spec §3). The names are:
   - `test_watchdog`, `test_evolving_recovery`, `test_watchdog_telemetry`;
   - the chassis and recorder tests;
   - `test_pump`;
   - `test_agent_credentials`, `test_agent_dependencies`, `test_smoke`, `test_cleanliness`, `test_persistent_state`, `test_startup`;
   - the space tests kept.

   A test checks that every name in the table resolves to a real test node. Where a property has no test, one is ported:
   - `test_agent_dependencies` pins the exact manifest and the Dockerfile's COPY → `pip install -r` pair;
   - `test_startup`'s surviving groups (pump start and restart, pump placement and limits, recorder fan-out and token ceiling, shipped-template stream ceilings, mountpoints and mount roots, no transcript tooling in the workspace, prepare_host ordering) cite or gain a test each.

## Global Constraints

- Every task ends with the whole suite green.
- No `git stash`, no broad `git add`, no `git submodule update`. Do not touch `docs/deep_research/vehicle/` or `docs/plans/`. Do not read `.env`. No push.
- Every commit is gated on the test run, not lint alone. `-n 8` needs pytest-xdist.
- Do not deploy, and do not edit the operator's `operator/`, `volumes/` or `.env`.

## Review Focus

1. **A deletion that leaves a live reference behind.** That can be an import, a path in the Dockerfile or compose, a comment that tells an operator to run something gone, or a test that skips because its file vanished. (Task 2: a guard test that the retired paths and every reference to them are gone, outside the history ruling 2 names.)
2. **One `pytest` that silently runs fewer tests.** Collisions and a conftest that shadows another can make tests quietly disappear. (Task 3: the merged count equals the sum of the separate runs.)
3. **The image losing a file the operator services or the vehicle need.** (Task 2: image tests for `/opt/services/{common,health,fleet_monitor,review}.py` and `/opt/vehicle`.)
4. **A doc that still describes the old world.** Examples: the exit-code ladder, `/home` and `/diary`, the supervisor, the duty, the endurance harness. (Task 5: a phrase guard over the tracked docs.)
5. **Draft agent text claiming more safety than the world has.** Spec §6 calls out the "cannot damage the environment" line. (Task 4: the drafts README lists every claim the drafts make about the world, each with its source.)

---

### Task 1: Tests first: the shared conftest without the old world, and the old-runtime tests gone

**Files:**
- Rewrite: `tests/conftest.py`. Its `sys.path` holds only `services/` and `contract/` (as before), plus `scripts/` (new: the tests that import scripts add it themselves today). Drop PROJECT, `endurance/`, `World`, `Stack`, `scripted`, `tool_call` and the `stub_model` import.
- Split `tests/test_services.py`:
  - keep its diode-contract part (the `side` fixture, the `console()` helper and its 11 tests on `contract/fake_diode.py`) as `tests/test_fake_diode.py`;
  - delete the rest (pump, old recorder ceilings, supervisor ladder). The header-never-recorded property lives on at `recorder/tests/test_proxy.py:866`.
- Delete: `tests/test_chassis.py`, `tests/test_run_end_to_end.py`, `tests/test_services.py`.

- [ ] **Step 1:** Make the moves. Run the root suite (executed, not only collected); every remaining test passes, and the count drops by exactly the deleted tests (record both counts).
- [ ] **Step 2:** Commit: `tests: the shared conftest without the old world; the old runtime's tests retired`.

### Task 2: Delete the old runtime, and narrow the image

**Files:**
- Delete:
  - `services/chassis.py`, `services/supervisor.py`, `services/recorder.py`, `services/pump.py`;
  - `tasks/`;
  - `endurance/` (tracked files) and `docs/example-run-report.md`;
  - `containers/agent.env`.
- Modify:
  - `Dockerfile.agent`: copy only `services/{common,health,fleet_monitor,review}.py` to `/opt/services/`, and drop the `agent.env` COPY and chmod;
  - `containers/serve_vehicle.sh`: drop the `agent.env` source, and correct the stale comments at :12–18 and :61;
  - `services/common.py`: drop `env_optional_int`, `slugify`, `env_defaults` and `env_bool` if nothing uses them, and correct the docstring;
  - `scripts/roster.py`: drop the `mount` and `diary` fields, the comment at :218–222, and `print_roster`'s `private` column (:309, :313), which reads `mount`;
  - `Dockerfile.agent`: the stale comments at :62–63 ("until the port retires them") and :73–76 (the world's constants);
  - `.gitignore`: the comment at :18–19 that cites `docs/example-run-report.md`;
  - `pyproject.toml`: drop `known-third-party` and its comment, correct the vendored-exclude comment and the vehicle count (344, not 312). The `endurance/runs` exclude stays, under ruling 3;
  - the "own process until plan 5" comments in `harness/tests/conftest.py`, `recorder/tests/conftest.py` and `pump/tests/conftest.py`.
- Create: `tests/test_retired.py`.

- [ ] **Step 1: Failing tests** in `tests/test_retired.py`:
  - `test_the_old_runtime_is_gone`: `git ls-files` lists none of the deleted paths (`services/chassis.py`, `services/supervisor.py`, `services/recorder.py`, `services/pump.py`, `tasks`, `endurance`, `containers/agent.env`, `docs/example-run-report.md`). Untracked leftovers do not count (ruling 3).
  - `test_nothing_still_refers_to_the_old_runtime`:
    - **Scope:** every tracked file outside ruling 2's history, read with `git ls-files`, excluding this test file and the spec and plans under `docs/superpowers/`.
    - **What it bans:** `services/chassis.py`, `services/supervisor.py`, `services/recorder.py`, `services/pump.py`, `tasks/duty.py`, `endurance/run_local`, `endurance/stub_model`, `agent.env`, `_load_runtime`, `DIODE_DUTY_DIR`, `PUMP_DUTY_DIR`, and a path built to them (`SERVICES_DIR / "chassis.py"`, `"tasks"`).
    - **Permanent exceptions,** each commented:
      - `.gitignore` and `.dockerignore`'s `endurance/runs/` (ruling 3);
      - the shipped `brief/` and `harness/*_prompt.txt` (ruling 1);
      - `docs/drafts/` (it quotes what the shipped text says).
    - **Temporary allowlist:** the docs Task 5 rewrites. Task 5 empties it.
  - In `tests/test_agent_image.py`:
    - `test_the_image_carries_only_the_operator_services`: the Dockerfile's `services` COPY names exactly the four files.
    - `test_the_image_carries_no_agent_env`.
    - `test_the_image_still_carries_the_vehicle`: the `/opt/vehicle` COPY and `serve_vehicle.sh` are in place.
  - `test_the_roster_prints_without_its_retired_columns`: `scripts/roster.py` (not `--json`) prints, on a temporary roster.
- [ ] **Step 2:** FAIL. **Step 3:** Delete and modify. **Step 4:** Run the root suite (PASS) and ruff. Rebuild the image (`docker build -f Dockerfile.agent -t space-chassis-agent:smoke .`) and run the live suite: `python3 -m pytest live -q -p no:cacheprovider`, expecting 13/13.
- [ ] **Step 5:** Commit: `retire the old runtime: services' chassis, supervisor, recorder and pump, the duty, the endurance harness`.

### Task 3: One test suite

**Files:**
- Modify:
  - `pyproject.toml`: `testpaths = ["tests", "harness/tests", "recorder/tests", "pump/tests", "docs/deep_research/vehicle/tests"]`;
  - `CLAUDE.md`'s Commands block: one `python3 -m pytest -q -n 8` (needs pytest-xdist), plus the per-suite lines.
- Create: `tests/test_one_suite.py`.

- [ ] **Step 1: Failing tests:**
  - `test_a_bare_pytest_collects_every_suite`:
    - A bare `pytest --collect-only -q` lets `testpaths` decide what to collect. Its set of node IDs must equal the union of the per-directory collections.
    - Every collection subprocess must exit 0.
    - It is a slow test (about six collections); the docstring says so.
  - `test_each_bare_module_name_resolves_to_its_own_directory`: in the merged process, `chassis`, `pump`, `proxy`, `core_caps` and `recorder_streams` import from `harness/`, `pump/` and `recorder/`. It runs as a subprocess, with the merged `sys.path` set up by the conftests.
  - `test_the_shared_hostile_inputs_are_identical`: `recorder/tests/hostile_inputs.py` and `pump/tests/hostile_inputs.py` are byte for byte the same. In one process the first import wins.
- [ ] **Step 2:** FAIL: before `testpaths` changes, the bare collection holds only `tests/` and the vehicle. **Step 3:** Merge. **Step 4:** Run the merged suite for real, `python3 -m pytest -q -n 8 -p no:cacheprovider` (all suites, vehicle included), record the count, and run ruff. The green run is the proof; the collection tests guard it.
- [ ] **Step 5:** Commit: `one test suite: the harness, recorder, pump and root suites in one pytest`.

### Task 4: Spec §9's missing acceptance tests, and the agent-facing drafts

**Files:**
- Create: `tests/test_agent_dependencies.py`, `tests/test_startup.py`, `docs/drafts/README.md`, `docs/drafts/system_prompt.txt`, `docs/drafts/user_prompt.txt`, `docs/drafts/WORLD.md`, `docs/drafts/PROTOCOL.md`.

**`tests/test_acceptance_map.py`** (ruling 4): the §9 table, and a test that every cited node exists.

**`test_agent_dependencies`** ports Aurora's (`git -C ~/aurora show 42faf41:tests/test_agent_dependencies.py`):
- it pins the exact list in `requirements-agent.txt` as it stands, which includes the harness's own `openai<3` and `httpx<1`, and `pyyaml` for the vehicle console;
- it pins the Dockerfile's `COPY requirements-agent.txt` before `pip install -r`, at `Dockerfile.agent:25–26`;
- Aurora-only properties are listed as dropped.

**`test_startup`** walks Aurora's `tests/test_startup.py` property by property.
- A property this world keeps either cites its existing test, in a mapping table in the module docstring, or is ported.
- A property of a dropped component (garden, books, further hosts, per-host supervisor, the stage) is listed as dropped, citing spec §3.
- The pump is the main survivor:
  - the entrypoint starts the pump before the watchdog;
  - a crashing pump is restarted;
  - the image ships the pump outside `/work`, and pre-creates `/pump`;
  - the pump volume is the agent's alone;
  - the agent receives the pump limits.

**The drafts (spec §6).** Each is a complete replacement for its shipped file.

The prompts keep Aurora's structure, its account of recovery, its warning about the danger of believed text, and its invitation to rewrite the prompts. Then:
- the unassigned-world passages become a pointer to `/opt/brief`;
- the "cannot damage the environment" line becomes a claim of safety for the agent's own harness only;
- the mission is assigned, and roles are not.

`WORLD.md` and `PROTOCOL.md` describe:
- `/work`, the harness repository, with `baseline`, `rescue` and `experimental`;
- `/state`, the durable store;
- `HOME` (`/home/agent`), a tmpfs that does not survive a restart. The old brief promised a durable private home, and this is the fact most likely to mislead an agent;
- `/pump` and `/build`;
- the exits 0/42/43/44/45 and what each does;
- `done` and `reset`;
- `/shared` and `/diode/<slug>`;
- `/llm/sock` and `/llm/console`;
- that no transcript is mounted (open question §10.4).

`docs/drafts/README.md`:
- lists every claim the drafts make about the world, each with the file or test that makes it true;
- lists the open choices for John (§10 items 2–4);
- states that nothing here is shipped.

- [ ] **Step 1:** Write the map and the ported tests. They pass against the current tree (they pin facts the port already has); record that. The map's resolution test fails on a name typed wrong, which is its own RED.
- [ ] **Step 2:** Write the drafts and their README.
- [ ] **Step 3:** Commit: `acceptance: the dependencies and startup properties pinned; the prompts and brief drafted for John`.

### Task 5: The documents describe the world as it is

**Files:**
- Rewrite: `CLAUDE.md`, `AGENTS.md`, `README.md`.
- Modify:
  - `docs/design.md`: §3, §5, §6, §7, §8a, §10, §11;
  - `.env.example`: the window and recap wording; remove `RUN_MAX_*` and `SUPERVISOR_INACTIVITY_SECONDS`; correct the review text;
  - `tests/test_retired.py`: empty the doc allowlist.
- Not modified: `brief/`, `harness/*_prompt.txt` (ruling 1).

**CLAUDE.md** keeps its shape (Commands; the scope boundary; operator side vs fleet side; the exit-code contract; imports and style; deliberate non-features; Filigree) with each section's facts replaced:
- the exit codes are Aurora's: 0 restart, 42 done, 43 terminated, 44 pause, 45 reset, plus the flap rule;
- the ladder is `baseline_same` → `baseline_new` → `rescue_new` → reseed;
- the operator-vs-fleet table becomes:
  - the image: `/opt/agent` seed repository, `/usr/local/bin/pump.py`, `/usr/local/lib/recorder`, `/opt/services`, `/opt/brief`, `/opt/vehicle`;
  - per agent: `/work` tmpfs, `/state`, `/pump`, `/build`, `/telemetry`, `/llm/sock`, `/llm/console`, `/diode/<slug>`;
  - shared: `/shared`;
  - the operator: transcripts, the ledger, `operator_telemetry` and the journal;
- the "two copies of `chassis.py`" gotcha is gone;
- the non-features keep worknet's one hard rule and the empty servers.

**design.md** sections that described the old runtime are rewritten from the spec, §2 included (it says transcripts and lifecycle records are mounted read-only into agents; by default no transcript is mounted). Every filesystem and trust claim is checked against spec §5. Each rewritten section ends with a pointer to the spec section it summarises.

- [ ] **Step 1: Failing test:** `test_no_tracked_doc_describes_the_retired_world`, a phrase guard over `CLAUDE.md`, `AGENTS.md`, `README.md`, `docs/design.md` and `.env.example` (not `brief/`: ruling 1).
  - It bans: `AGENT_HOME`, `/diary`, `volumes/home`, `duty.py`, `endurance/run`, `RUN_MAX_`, `SUPERVISOR_INACTIVITY`, `two copies of`, `handoff note`, `recap.md`, `lifecycle.jsonl`, and `the supervisor` (as the old runtime's process).
  - `/home/agent` and "handoff" are current vocabulary (HOME is a tmpfs at `/home/agent`; the entrypoint hands off to the watchdog), so they are not banned. The CLAUDE.md table must say `HOME=/home/agent` is a tmpfs that does not persist; a second test asserts that line.
  - A line marked `(retired)` is exempt only for the phrase it names, and only where it says what replaced it.
- [ ] **Step 2:** FAIL. **Step 3:** Rewrite. **Step 4:** Run the whole suite and ruff.
- [ ] **Step 5:** Commit: `docs: the repository describes the Aurora world`.

### Task 6: The live run, and the final review

- [ ] **Step 1:** Add the live fleet-cap check that spec §9.7 requires and plan 3c deferred: `test_the_fleet_cap_refuses_and_the_agent_pauses`.
  - It is the last test in `live/test_operator.py`. It recreates `recorder_1` with a tiny `RECORDER_TOKEN_GLOBAL_HOURLY_MAX` and nothing else changed (`compose up -d --force-recreate --no-deps recorder_1`, with an extra override file).
  - It then waits for a 429 `across the fleet` in agent_1's transcript, followed by `action pause` in its log since the mark.
  - `SmokeStack` gains `recreate(service, environment)`, with an offline test.
- [ ] **Step 2:** Rebuild the image and run the live suite: `python3 -m pytest live -q -p no:cacheprovider`, expecting 14/14.
- [ ] **Step 3:** Final review: Opus and one Astra run (John's instruction, 2026-10-09, while Fable is limited); one fix pass.

---

## What this plan does not do

- Ship the prompts or the brief. John approves the text (spec §6).
- Merge the branch, push, or close the superseded filigree issues. Those happen when the port lands, which is John's call.
- Archive the operator's old `volumes/` or `endurance/runs/` (ruling 3).
- Edit history (ruling 2).
