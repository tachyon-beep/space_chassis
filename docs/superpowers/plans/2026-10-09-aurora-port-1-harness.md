# Aurora Port, Plan 1: The Agent Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring Aurora's agent harness (`agent.py`, `chassis.py`, `command_runtime.py`, `watchdog.py`) into this repository as the seed every agent starts from, with the spec's mission kit and its two watchdog changes, all tested without Docker.

**Architecture:** The harness lives in a new top-level `harness/` directory, which later becomes `/opt/agent` in the image (plan 3). Its tests live in `harness/tests/` and run as their own pytest process, because `services/` still carries a `chassis.py` of its own until plan 5 retires it. Vendored files stay byte-close to Aurora at `42faf41`; every space change is a small, named addition with its own test.

**Tech Stack:** Python 3.12 on the host, 3.13 in the image; `openai` and `httpx` (already the chassis's dependencies); pytest; git.

**Spec:** `docs/superpowers/specs/2026-10-09-aurora-port-design.md` (approved, `aca36df`). Reference implementation: `~/aurora` at `42faf41`.

## The programme this plan belongs to

The spec covers five subsystems. Each gets its own plan, written when the one before it lands, and each produces software that passes its own tests.

| Plan | Delivers | Spec sections |
|---|---|---|
| **1. Harness (this plan)** | the agent's seed repo contents, mission kit, watchdog changes | 3, 3.1, 4 |
| 2. Recorder | Aurora's `proxy.py` and `recorder_streams.py`, core-socket caps, fleet ledger | 3.3 |
| 3. Containers | image, entrypoint, per-agent binds, loopback servers, pump, the three-agent smoke stack, `verify_containment.sh`, end-to-end acceptance 1–8 | 2, 3.2, 5, 9 |
| 4. Operator surfaces | journal, recorder-derived health signals, staleness, the adapted review, status and monitor tools | 3.4 |
| 5. Retirement and words | remove the old runtime, merge `harness/tests` into the root suite, rewrite `CLAUDE.md`, `docs/design.md` and the brief, draft the prompts for John | 6, 7 |

Plan 2's shape depends on John's open question about the SV workstream (spec section 10, item 1). This plan does not.

## Global Constraints

- The vendored files come from `~/aurora` at commit `42faf41`, through `git -C ~/aurora show 42faf41:<path>`. Never copy from the Aurora working tree, which has uncommitted changes.
- **Comments in `agent.py` may only be commented-out code**, never prose. Aurora's `test_agent_comments_are_only_disabled_code` enforces it.
- **Tool docstrings are load-bearing and affectless.** `ToolRegistry` turns them into the schemas the model sees. Aurora's voiced-fragment tests in `test_cleanliness.py` apply to every registered tool, including new ones.
- **No transport identity in `agent.py`**: no provider, model, base URL, header or request loop (`test_transport_identity_stays_in_the_chassis`).
- **Nothing under `harness/` except the runtime files gets into the image**, so `harness/` holds no README, provenance note or test data that an agent would read as a fact about its world. Provenance goes in commit messages and `CLAUDE.md`.
- **Test names are full sentences** stating the property, as in the rest of this repository.
- **No skips and no xfails.** Deprecation warnings are errors (`filterwarnings = ["error::DeprecationWarning"]` in the root `pyproject.toml` applies to `harness/tests` too).
- **The harness is excluded from the root ruff run.** It is vendored code kept close to upstream for re-syncing, and upstream is not lint-clean under its own settings.

## Review Focus

These five inputs follow from the spec, and none of Aurora's tests exercises them. Each has a test in the task named.

1. **A huge or binary file passed to `read_path`** must return a bounded, decoded result, not flood the context window or raise. (Task 2: `test_read_path_bounds_a_large_file_and_says_where_it_stopped`, `test_read_path_decodes_bytes_that_are_not_utf8`)
2. **`write_path` into a directory that does not exist** must return an error string, not raise out of the tool. (Task 2: `test_write_path_into_a_missing_directory_is_an_error_string`)
3. **A `run` command that never ends**, or a requested timeout above 120 s, must stop at the 120-second cap and report a timeout. (Task 2: `test_run_caps_the_timeout_at_120_seconds`, `test_run_reports_a_timeout_and_returns`)
4. **`run` with a zero or negative timeout** must return an error string. (Task 2: `test_run_rejects_a_timeout_that_is_not_positive`)
5. **A seed-boot note** must reach the agent exactly once, not on every restart, and must not appear when recovery state already exists. (Task 3: `test_the_seed_boot_note_is_delivered_once`, `test_a_boot_with_recovery_state_writes_no_seed_note`)

---

## File structure

| Path | Responsibility |
|---|---|
| `harness/agent.py` | Aurora's agent: tool registry, genesis tools, prompt loading; plus the mission kit (Task 2) |
| `harness/chassis.py` | Aurora's substrate: model client, request loop, context window, send-view repair, tombstones. Vendored unchanged. |
| `harness/command_runtime.py` | Aurora's bounded command runner. Vendored unchanged. |
| `harness/watchdog.py` | Aurora's watchdog: tags, ladder, mirror; plus the jittered pause and the seed-boot note (Task 3) |
| `harness/system_prompt.txt`, `harness/user_prompt.txt` | Aurora's prompts, vendored as placeholders. Plan 5 drafts the mission text for John. |
| `harness/tests/conftest.py` | puts `harness/` first on `sys.path` and runs each test from `harness/` |
| `harness/tests/test_*.py` | Aurora's harness tests, plus `test_mission_kit.py` and `test_space_watchdog.py` |
| `pyproject.toml` | ruff excludes `harness` |
| `CLAUDE.md` | one command line and one provenance line |

---

### Task 1: Vendor Aurora's harness and its tests

**Files:**
- Create: `harness/agent.py`, `harness/chassis.py`, `harness/command_runtime.py`, `harness/watchdog.py`, `harness/system_prompt.txt`, `harness/user_prompt.txt`
- Create: `harness/tests/conftest.py`
- Create, from Aurora's `tests/`: `test_watchdog.py`, `test_evolving_recovery.py`, `test_watchdog_telemetry.py`, `test_chassis_recovery.py`, `test_chassis_commands.py`, `test_compact.py`, `test_context_window.py`, `test_repair_send_view.py`, `test_session_persistence.py`, `test_file_tools.py`, `test_tool_registry.py`, `test_command_runtime.py`, `test_cleanliness.py`, `test_condense_duplicates.py`
- Modify: `pyproject.toml` (the `[tool.ruff]` exclude list), `CLAUDE.md` (the Commands block)

**Interfaces:**
- Produces: the module names `agent`, `chassis`, `command_runtime` and `watchdog`, importable inside `harness/tests`; Aurora's public functions, unchanged (`watchdog.Recovery`, `watchdog.plan_recovery`, `watchdog.apply_recovery`, `chassis.deliver_recovery_note`, `command_runtime.run_command`).

- [ ] **Step 1: Copy the runtime files at the pinned commit**

```bash
mkdir -p harness/tests
for f in agent.py chassis.py command_runtime.py watchdog.py system_prompt.txt user_prompt.txt; do
  git -C ~/aurora show 42faf41:$f > harness/$f
done
for t in test_watchdog test_evolving_recovery test_watchdog_telemetry test_chassis_recovery \
         test_chassis_commands test_compact test_context_window test_repair_send_view \
         test_session_persistence test_file_tools test_tool_registry test_command_runtime \
         test_cleanliness test_condense_duplicates; do
  git -C ~/aurora show 42faf41:tests/$t.py > harness/tests/$t.py
done
```

- [ ] **Step 2: Write `harness/tests/conftest.py`**

  It inserts the `harness/` directory at `sys.path[0]` at import time, and adds an autouse fixture that `monkeypatch.chdir`s into `harness/`, as Aurora's conftest does into its repository root. It has no stage-cache fixture: that is Aurora's, and the stage is dropped.

- [ ] **Step 3: Remove the two tests that belong to later plans**

  Delete these two functions, and record in the commit message where each one goes:
  - `test_duplicate_stock_agent_is_removed` from `harness/tests/test_cleanliness.py`. It reads Aurora's `Dockerfile`, and plan 3 re-adds it against this repository's `Dockerfile`.
  - `test_reasoning_effort_levels_match_the_recorder` from `harness/tests/test_context_window.py`. It reads Aurora's recorder, and plan 2 re-adds it.

- [ ] **Step 4: Run the vendored suite**

  Run: `python3 -m pytest harness/tests -q -p no:cacheprovider`
  Expected: `185 passed`, with no warnings promoted to errors. That count was measured on a scratch copy at `42faf41` on 2026-10-09. A different count means the copy differs from the commit.

- [ ] **Step 5: Confirm the old suite is untouched and still separate**

  Run: `python3 -m pytest tests -q -p no:cacheprovider`
  Expected: the same result as before this task. The root `testpaths` in `pyproject.toml` is unchanged and does not include `harness/tests`.

- [ ] **Step 6: Exclude the harness from ruff, and document the command**

  - In `pyproject.toml`, add `"harness"` to `[tool.ruff] exclude`, with a one-line comment: vendored from Aurora at `42faf41` and kept close to upstream.
  - In `CLAUDE.md`'s Commands block, add `python3 -m pytest harness/tests -q   # the Aurora harness: its own process until plan 5 retires services/chassis.py`.

  Run: `uvx ruff check . --no-cache`
  Expected: the same findings as before this task, and none under `harness/`.

- [ ] **Step 7: Commit**

```bash
git add harness pyproject.toml CLAUDE.md
git commit -m "harness: vendor Aurora's agent, chassis, command runtime and watchdog at 42faf41

(body: the source commit; 185 tests pass in harness/tests; the two tests that
read Aurora's Dockerfile and recorder move to plans 3 and 2.)"
```

---

### Task 2: The mission kit

The spec's ruling 7: Aurora's eight tools, plus file access anywhere the agent can see, a bounded command runner, and git through that runner. These are ordinary, editable code in `agent.py`.

**Files:**
- Modify: `harness/agent.py` (three new tools after `compact`, before `_load_prompt`)
- Modify: `harness/tests/test_tool_registry.py` (the pinned surface)
- Create: `harness/tests/test_mission_kit.py`

**Interfaces:**
- Consumes: `command_runtime.run_command(command, *, cwd, shell, timeout, output_limit, decode_output=True) -> dict`, with keys `status` (`"completed"` or `"timeout"`), `returncode`, `stdout`, `stderr`, `output_truncated` (`{"stdout": bool, "stderr": bool}`). It raises `ValueError` for a timeout that is not finite and positive, and caps a larger one at 120 s.
- Produces, in `agent.py`:
  - `MISSION_KIT_OUTPUT_LIMIT = 65536` (bytes)
  - `read_path(path: str, line_number: int = 0) -> str`
  - `write_path(path: str, text: str, mode: Literal["overwrite", "append"] = "overwrite") -> str`
  - `run(command: str, timeout: int = 120) -> str`

- [ ] **Step 1: Write the failing tests in `harness/tests/test_mission_kit.py`**

```python
import agent

def test_read_path_reads_a_file_outside_the_harness_with_line_numbers(tmp_path):
    p = tmp_path / "brief.md"; p.write_text("one\ntwo\n")
    assert agent.read_path(str(p)) == "1: one\n2: two\n"
    assert agent.read_path(str(p), 2) == "2: two\n"

def test_read_path_bounds_a_large_file_and_says_where_it_stopped(tmp_path):
    p = tmp_path / "big.txt"; p.write_text("x" * 200_000)
    out = agent.read_path(str(p))
    assert len(out.encode()) < agent.MISSION_KIT_OUTPUT_LIMIT + 200
    assert out.endswith(f"[file is 200000 bytes; output stops at {agent.MISSION_KIT_OUTPUT_LIMIT}]")

def test_read_path_decodes_bytes_that_are_not_utf8(tmp_path):
    p = tmp_path / "raw.bin"; p.write_bytes(b"ok\xff\xfe\n")
    assert agent.read_path(str(p)).startswith("1: ok")

def test_read_path_on_a_missing_file_is_an_error_string(tmp_path):
    assert agent.read_path(str(tmp_path / "absent")).startswith("error reading ")

def test_write_path_overwrites_then_appends(tmp_path):
    p = tmp_path / "note.txt"
    assert agent.write_path(str(p), "a") == f"wrote 1 bytes to {p}"
    agent.write_path(str(p), "b", mode="append")
    assert p.read_text() == "ab"

def test_write_path_into_a_missing_directory_is_an_error_string(tmp_path):
    assert agent.write_path(str(tmp_path / "no" / "such" / "f"), "x").startswith("error writing ")

def test_run_reports_status_exit_and_both_streams():
    out = agent.run("echo out; echo err >&2; exit 3")
    assert out.splitlines()[:2] == ["status: completed", "exit: 3"]
    assert "stdout:\nout\n" in out and "stderr:\nerr\n" in out

def test_run_reports_a_timeout_and_returns():
    out = agent.run("sleep 30", timeout=1)
    assert out.startswith("status: timeout after 1 s")

def test_run_caps_the_timeout_at_120_seconds(monkeypatch):
    # The cap is command_runtime's COMMAND_TIMEOUT_SECONDS (120), read at call time;
    # lowering it to 1 shows a 900-second request stopping at the cap.
    import command_runtime
    monkeypatch.setattr(command_runtime, "COMMAND_TIMEOUT_SECONDS", 1)
    out = agent.run("sleep 30", timeout=900)
    assert out.startswith("status: timeout after 1 s")

def test_run_rejects_a_timeout_that_is_not_positive():
    assert agent.run("true", timeout=0).startswith("error: timeout must be")

def test_run_marks_truncated_output():
    out = agent.run(f"head -c {agent.MISSION_KIT_OUTPUT_LIMIT + 10} /dev/zero | tr '\\0' x")
    assert "[stdout truncated]" in out

def test_git_works_through_run(tmp_path):
    out = agent.run(f"git init -q {tmp_path} && git -C {tmp_path} status --short")
    assert out.splitlines()[:2] == ["status: completed", "exit: 0"]
```

- [ ] **Step 2: Run them and see them fail**

  Run: `python3 -m pytest harness/tests/test_mission_kit.py -q -p no:cacheprovider`
  Expected: every test fails with `AttributeError: module 'agent' has no attribute ...`.

- [ ] **Step 3: Implement the three tools in `harness/agent.py`**

  - **Import:** `from command_runtime import run_command`, placed at module level beside the existing imports. Do not use `chassis`, which would carry transport identity into `agent.py`.
  - **`read_path`:**
    - Opens in binary and reads at most `MISSION_KIT_OUTPUT_LIMIT` bytes, then decodes with `errors="replace"`.
    - Numbers lines exactly as `read_file` does, including its out-of-range message.
    - When the file is larger than the limit, it appends `\n[file is {size} bytes; output stops at {MISSION_KIT_OUTPUT_LIMIT}]`.
    - Exceptions become `f"error reading {path}: {e}"`.
  - **`write_path`:** writes the text as UTF-8 (`"w"` or `"a"`) and returns `f"wrote {n} bytes to {path}"`, where `n` is the encoded length. It never creates parent directories. Exceptions become `f"error writing {path}: {e}"`.
  - **`run`:**
    - Calls `run_command(command, cwd=os.path.dirname(os.path.abspath(__file__)), shell=True, timeout=timeout, output_limit=MISSION_KIT_OUTPUT_LIMIT)`. The timeout reported on a timeout is the result's own `timeout_seconds`, which is the value after the cap.
    - On completion it returns `status: completed`, `exit: N`, `stdout:` and its text, then `stderr:` and its text. On timeout the first line is `status: timeout after {timeout_seconds} s`.
    - Each truncated stream appends `[stdout truncated]` or `[stderr truncated]`.
    - `ValueError` becomes `"error: timeout must be a positive number of seconds"`.
  - **Paths:** all three resolve paths with the existing `_resolve_path`.
  - **Docstrings:** first line, then an `Args:` block, in the style of `read_file`. They are affectless, name no surface the agent has not met, and contain no prose comments.

- [ ] **Step 4: Update the pinned surface in `harness/tests/test_tool_registry.py`**

  Rename `test_genesis_surface_is_exactly_eight_tools_in_order` to `test_genesis_surface_is_aurora_s_eight_tools_then_the_mission_kit`. Its list becomes Aurora's eight in their order, followed by `"read_path"`, `"write_path"`, `"run"`.

- [ ] **Step 5: Run the harness suite**

  Run: `python3 -m pytest harness/tests -q -p no:cacheprovider`
  Expected: `197 passed`: 185 plus 12 in `test_mission_kit.py`. The renamed registry test replaces its original, so the count does not change for it. The cleanliness tests now cover the three new tools' docstrings, and `test_agent_comments_are_only_disabled_code` still passes.

- [ ] **Step 6: Commit**

```bash
git add harness/agent.py harness/tests/test_mission_kit.py harness/tests/test_tool_registry.py
git commit -m "harness: seed the mission kit -- read_path, write_path and run beside Aurora's eight"
```

---

### Task 3: The watchdog's two space changes

The spec's 3.3 and section 4: the exit-44 pause gains jitter so ten agents do not retry in lockstep, and the first boot from the image seed leaves a recovery note saying so.

**Files:**
- Modify: `harness/watchdog.py`
- Create: `harness/tests/test_space_watchdog.py`

**Interfaces:**
- Consumes: `watchdog.Recovery(work_dir)` and its `state`, `note(reason, ref, commit, fresh)`, `path`; `watchdog.apply_recovery(action, ret, own_hash, recovery)`; `chassis.deliver_recovery_note(messages)`, which reads `state["note"]` from `.git/aurora-recovery.json` and delivers it once.
- Produces, in `watchdog.py`:
  - `ENVIRONMENT_PAUSE_JITTER_SECONDS = 30`
  - `environment_pause_seconds(random_fraction: float) -> float`, returning `ENVIRONMENT_PAUSE_SECONDS + random_fraction * ENVIRONMENT_PAUSE_JITTER_SECONDS`
  - `Recovery.seeded: bool`, true when no recovery state file existed at construction
  - `Recovery.note_seed_boot(self) -> bool`

- [ ] **Step 1: Write the failing tests in `harness/tests/test_space_watchdog.py`**

  Reuse the `git` and `repo_at` helpers by copying them from `test_evolving_recovery.py`, as Aurora's own tests do.

```python
def test_the_environment_pause_is_sixty_seconds_plus_up_to_thirty_of_jitter():
    assert watchdog.environment_pause_seconds(0.0) == 60
    assert watchdog.environment_pause_seconds(0.5) == 75
    assert watchdog.environment_pause_seconds(0.999) < 90

def test_exit_44_pauses_for_the_jittered_time(monkeypatch):
    slept = []
    monkeypatch.setattr(watchdog.time, "sleep", slept.append)
    monkeypatch.setattr(watchdog.random, "random", lambda: 0.5)
    watchdog.apply_recovery("pause", 44, "hash")
    assert slept == [75]

def test_a_fresh_seed_boot_leaves_a_recovery_note_saying_so(tmp_path):
    commit = repo_at(tmp_path)
    recovery = watchdog.Recovery(str(tmp_path))
    assert recovery.seeded is True
    assert recovery.note_seed_boot() is True
    assert "started from the image seed" in recovery.state["note"]
    assert commit in recovery.state["note"]
    assert (tmp_path / "tombstones" / "recovery_note.txt").exists()

def test_a_boot_with_recovery_state_writes_no_seed_note(tmp_path):
    repo_at(tmp_path)
    watchdog.Recovery(str(tmp_path)).note_seed_boot()
    again = watchdog.Recovery(str(tmp_path))
    assert again.seeded is False and again.note_seed_boot() is False

def test_the_seed_boot_note_is_delivered_once(tmp_path, monkeypatch):
    repo_at(tmp_path)
    watchdog.Recovery(str(tmp_path)).note_seed_boot()
    monkeypatch.setattr(chassis, "WORK_DIR", str(tmp_path))
    messages = []
    chassis.deliver_recovery_note(messages)
    chassis.deliver_recovery_note(messages)
    assert len(messages) == 1 and "image seed" in messages[0]["content"]

def test_the_watchdog_writes_the_seed_note_before_the_first_agent_starts(tmp_path, monkeypatch):
    repo_at(tmp_path)
    monkeypatch.setattr(watchdog, "Recovery", lambda: watchdog_Recovery(str(tmp_path)))
    class Started(Exception): pass
    def spawn():
        assert (tmp_path / "tombstones" / "recovery_note.txt").exists()
        raise Started
    monkeypatch.setattr(watchdog, "spawn_agent", spawn)
    with pytest.raises(Started):
        watchdog.run_watchdog()
```

  (`watchdog_Recovery` is the original class, captured at module import as `watchdog_Recovery = watchdog.Recovery` before any monkeypatching.)

- [ ] **Step 2: Run them and see them fail**

  Run: `python3 -m pytest harness/tests/test_space_watchdog.py -q -p no:cacheprovider`
  Expected: failures on the missing `environment_pause_seconds`, `seeded`, `note_seed_boot` and `random` names. `test_exit_44_pauses_for_the_jittered_time` fails with `[60] != [75]`.

- [ ] **Step 3: Implement in `harness/watchdog.py`**

  - `import random` with the other imports.
  - Add `ENVIRONMENT_PAUSE_JITTER_SECONDS = 30` beside `ENVIRONMENT_PAUSE_SECONDS`, and the function `environment_pause_seconds`.
  - In `apply_recovery`, the `pause` branch sleeps `environment_pause_seconds(random.random())`.
  - In `Recovery.__init__`, set `self.seeded = True` in the existing `FileNotFoundError` branch, and `False` otherwise.
  - Extract the body of `Recovery.note` after the text is built into `Recovery._publish(self, note: str) -> None`. That body sets `state["note"]`, saves, prints, and writes `tombstones/recovery_note.txt`. `note()` then calls it, so its output is unchanged.
  - Implement `note_seed_boot`. When `seeded` is false, it returns `False`. Otherwise it resolves `HEAD`'s commit with the existing `git_command`, then publishes exactly `f"Recovery event {time.time_ns()}: started from the image seed at {commit}; fresh incarnation."`. It does not use `note()`, whose "Restored …" wording would be false for a boot that restored nothing. It then sets `self.seeded = False` and returns `True`.
  - In `run_watchdog`, call `recovery.note_seed_boot()` immediately after `recovery = Recovery()` and before `spawn_agent()`.

- [ ] **Step 4: Run the harness suite**

  Run: `python3 -m pytest harness/tests -q -p no:cacheprovider`
  Expected: `203 passed`, which is 197 plus 6. Aurora's ladder tests still pass unchanged. A fresh repository now writes a seed note on its first `Recovery`, but only when `note_seed_boot()` is called, so `test_evolving_recovery`'s phase and note assertions are unaffected.

- [ ] **Step 5: Commit**

```bash
git add harness/watchdog.py harness/tests/test_space_watchdog.py
git commit -m "harness: jitter the exit-44 pause and note a boot from the image seed"
```

---

## What this plan does not do

These are deliberately left to later plans, so a reviewer should not expect them here:
- No image, entrypoint or compose change (plan 3).
- No recorder (plan 2).
- No end-to-end run against a model (plan 3's smoke stack, with Aurora's `scripts/verify_stub_llm.py`).
- No prompt text (plan 5).
- No removal of `services/` (plan 5).

When this plan is done, the repository holds a tested harness that nothing runs yet. That is the intended state.
