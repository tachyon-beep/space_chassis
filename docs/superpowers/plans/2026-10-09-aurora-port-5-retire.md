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
   - The shipped files stay as they are until John approves. The only exceptions are factual corrections that cannot wait, and those are listed in the drafts' README with what they change.
2. **History is left as history.** These still cite retired files, and none of them is edited:
   - `docs/superpowers/plans/2026-09-12-chassis-lifespan-control.md`;
   - the untracked `docs/plans/`;
   - the frozen corpus `docs/deep_research/` (`integration/*`, which `CLAUDE.md` calls the map);
   - the vehicle submodule, which is another agent's.
3. **The operator's on-disk leftovers are the operator's.** The old `volumes/` layout and `endurance/runs/` stay where they are. `.gitignore` keeps ignoring `endurance/runs/` until John archives it, and so does `prepare_host.sh`'s old-layout refusal.
4. **Spec §9's two missing acceptance tests are ported, adapted:**
   - `test_agent_dependencies`: the mission world's own requirements file, pinned;
   - `test_startup`: each Aurora property this world still has, mapped to its existing test or ported where none covers it.
   - Properties of Aurora components the port dropped (garden, books, further hosts) are listed as dropped, with spec §3 as the reason.

## Global Constraints

- Every task ends with the whole suite green.
- No `git stash`, no broad `git add`, no `git submodule update`. Do not touch `docs/deep_research/vehicle/` or `docs/plans/`. Do not read `.env`. No push.
- Every commit is gated on the test run, not lint alone.
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
- Rewrite: `tests/conftest.py`. Keep only the `sys.path` inserts for `services/`, `scripts/` and `contract/`. Drop `endurance/`, `World`, `Stack`, `scripted`, `tool_call` and the `stub_model` import.
- Split `tests/test_services.py`:
  - keep its diode-contract part (the `side` fixture and its 11 tests on `contract/fake_diode.py`) as `tests/test_fake_diode.py`;
  - delete the rest (pump, old recorder ceilings, supervisor ladder). The header-never-recorded property lives on at `recorder/tests/test_proxy.py:866`.
- Delete: `tests/test_chassis.py`, `tests/test_run_end_to_end.py`, `tests/test_services.py`.

- [ ] **Step 1:** Make the moves. Run the root suite; every remaining test passes, and the count drops by exactly the deleted tests (record both counts).
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
  - `scripts/roster.py`: drop the dead `mount` and `diary` fields, and the comment at :218–222;
  - `.dockerignore`: drop `endurance/runs/`;
  - `pyproject.toml`: drop the `endurance/runs` exclude.
- Create: `tests/test_retired.py`.

- [ ] **Step 1: Failing tests** in `tests/test_retired.py`:
  - `test_the_old_runtime_is_gone`: none of the deleted paths exists.
  - `test_nothing_still_refers_to_the_old_runtime`:
    - **Scope:** every tracked file outside ruling 2's history, read with `git ls-files`, excluding this test file and the spec and plans under `docs/superpowers/`.
    - **What it bans:** `services/chassis.py`, `services/supervisor.py`, `services/recorder.py`, `services/pump.py`, `tasks/duty.py`, `endurance/`, `agent.env`, `_load_runtime`, `DIODE_DUTY_DIR` and `PUMP_DUTY_DIR`.
    - Docs are covered in Task 5, so the test's allowlist names the docs Task 5 rewrites, and Task 5 empties it.
  - In `tests/test_agent_image.py`:
    - `test_the_image_carries_only_the_operator_services`: the Dockerfile's `services` COPY names exactly the four files.
    - `test_the_image_carries_no_agent_env`.
- [ ] **Step 2:** FAIL. **Step 3:** Delete and modify. **Step 4:** Run the root suite (PASS) and ruff. Rebuild the image (`docker build -f Dockerfile.agent -t space-chassis-agent:smoke .`) and run the live suite: `python3 -m pytest live -q -p no:cacheprovider`, expecting 13/13.
- [ ] **Step 5:** Commit: `retire the old runtime: services' chassis, supervisor, recorder and pump, the duty, the endurance harness`.

### Task 3: One test suite

**Files:**
- Modify:
  - `pyproject.toml`: `testpaths = ["tests", "harness/tests", "recorder/tests", "pump/tests", "docs/deep_research/vehicle/tests"]`, drop `known-third-party` and its comment, and correct the vendored-exclude comment;
  - the "own process until plan 5" comments in `harness/tests/conftest.py`, `recorder/tests/conftest.py` and `pump/tests/conftest.py`;
  - `CLAUDE.md`'s Commands block: one `python3 -m pytest -q -n 8`, plus the per-suite lines.
- Create: `tests/test_one_suite.py`.

- [ ] **Step 1: Failing test:** `test_one_pytest_collects_every_suite`.
  - It runs `pytest --collect-only -q` once for the merged `testpaths` and once per directory, and asserts the merged count equals the sum.
  - `hostile_inputs.py` exists byte-identical in `recorder/tests` and `pump/tests`, so a second test, `test_the_shared_hostile_inputs_are_identical`, holds them the same. In one process the first import wins.
- [ ] **Step 2:** FAIL: the merged count is lower. **Step 3:** Merge. **Step 4:** Run `python3 -m pytest -q -n 8 -p no:cacheprovider` (all suites, vehicle included) and record the count. Ruff.
- [ ] **Step 5:** Commit: `one test suite: the harness, recorder, pump and root suites in one pytest`.

### Task 4: Spec §9's missing acceptance tests, and the agent-facing drafts

**Files:**
- Create: `tests/test_agent_dependencies.py`, `tests/test_startup.py`, `docs/drafts/README.md`, `docs/drafts/system_prompt.txt`, `docs/drafts/user_prompt.txt`, `docs/drafts/WORLD.md`, `docs/drafts/PROTOCOL.md`.

**`test_agent_dependencies`** ports Aurora's (`git -C ~/aurora show 42faf41:tests/test_agent_dependencies.py`) to this world's `requirements-agent.txt`:
- every requirement the harness itself imports is present (`openai<3`, `httpx<1`);
- `pyyaml` is present, for the vehicle console;
- the file parses, with one requirement per line.

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
- `/state`;
- the exits 0/42/43/44/45 and what each does;
- `done` and `reset`;
- `/shared` and `/diode/<slug>`;
- `/llm/sock` and `/llm/console`;
- that no transcript is mounted (open question §10.4).

`docs/drafts/README.md`:
- lists every claim the drafts make about the world, each with the file or test that makes it true;
- lists the open choices for John (§10 items 2–4);
- states that nothing here is shipped.

- [ ] **Step 1:** Write the two tests. They pass against the current tree (they pin facts the port already has); record that.
- [ ] **Step 2:** Write the drafts and their README.
- [ ] **Step 3:** Commit: `acceptance: the dependencies and startup properties pinned; the prompts and brief drafted for John`.

### Task 5: The documents describe the world as it is

**Files:**
- Rewrite: `CLAUDE.md`, `AGENTS.md`, `README.md`.
- Modify:
  - `docs/design.md`: §3, §5, §6, §7, §8a, §10, §11;
  - `.env.example`: the window and recap wording; remove `RUN_MAX_*` and `SUPERVISOR_INACTIVITY_SECONDS`; correct the review text;
  - `brief/WORLD.md` and `brief/PROTOCOL.md`: factual corrections only, those listed in `docs/drafts/README.md` as unable to wait;
  - `tests/test_retired.py`: empty the doc allowlist.

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

**design.md** sections that described the old runtime are rewritten from the spec. Each rewritten section ends with a pointer to the spec section it summarises.

- [ ] **Step 1: Failing test:** `test_no_tracked_doc_describes_the_retired_world`, a phrase guard over `CLAUDE.md`, `AGENTS.md`, `README.md`, `docs/design.md`, `.env.example` and `brief/`.
  - It bans: `supervisor`, `duty.py`, `/diary`, `/home/agent` used as the agent's home, `endurance/`, `RUN_MAX_`, `two copies of`, `handoff`, `recap.md`.
  - It allows each phrase where a line marks it historical with `(retired)`.
- [ ] **Step 2:** FAIL. **Step 3:** Rewrite. **Step 4:** Run the whole suite and ruff.
- [ ] **Step 5:** Commit: `docs: the repository describes the Aurora world`.

### Task 6: The live run, and the final review

- [ ] **Step 1:** Rebuild the image and run the live suite: `python3 -m pytest live -q -p no:cacheprovider`, expecting 13/13.
- [ ] **Step 2:** Final review: Opus and one Astra run (John's instruction, 2026-10-09, while Fable is limited); one fix pass.

---

## What this plan does not do

- Ship the prompts or the brief. John approves the text (spec §6).
- Merge the branch, push, or close the superseded filigree issues. Those happen when the port lands, which is John's call.
- Archive the operator's old `volumes/` or `endurance/runs/` (ruling 3).
- Edit history (ruling 2).
