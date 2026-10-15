# Long-life follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four items the Long-life re-triage left open (filigree `space_chassis-c8e27e645c`, comment 30), and the archive-growth gap it found.

**Architecture:** There are two operator-side changes:
- the health signals read the cache and prompt usage the recorder already writes;
- the operator's own JSONL logs rotate.

There are three seed-side changes:
- a test that pins the context window's headroom against the default model;
- a test that pins the reasoning resend DeepSeek's contract requires;
- watchdog pruning of the conversation archives, which otherwise fill the `/work` tmpfs.

The seed changes are ordinary, editable code in the agent's own harness (ruling 1). They set the floor and take nothing away.

**Tech Stack:** Python 3.12 standard library; pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-aurora-port-design.md` (§1 rulings, §3.4 health signals, §4 lifecycle, §5 filesystem).

## Global Constraints

- The operator-side code (`services/`, `scripts/`) is standard library only.
- Health signals come from the recorders' transcripts and events, never from agent-written files (spec §3.4).
- Every read of an agent-written file is bounded and does not follow a planted link.
- `harness/` stays close to Aurora 42faf41: add the least, and keep the change in the seed's own style.
- No brief or prompt text changes without John (spec §6). The brief stays true; this plan adds nothing it would have to say.
- Tests are named as sentences; tests never skip for a missing docker or git.
- No push, no merge.

## Review Focus

1. **A close event whose usage is missing, a bool, negative, a float or absurd.** Spend ignores it rather than counting it or crashing. Task 1 tests it.
2. **An hour with no prompt tokens.** The cache share is `None`, and status prints `—` rather than dividing by zero. Task 1 tests it.
3. **A JSONL record bigger than the cap, a missing file, a second rotation.** The record is still written. One previous generation is kept, the older one is replaced, and nothing is ever truncated. Task 2 tests it.
4. **Pruning against the agent's own files.**
   - It deletes only the harness's own archive names, and only regular files; never a symlink, never `recovery_note.txt`, `synthetic_note.txt` or `incarnation_note.txt`, never the newest archive.
   - It never raises into recovery: an OSError is printed and swallowed.
   - Task 5 tests it.
5. **A smaller-context model set per host.** The documented rule, and the per-host window override, keep the window under that model's limit. Task 3 documents it, and its test pins the default.

---

### Task 1: Spend shows prompt, cache and incarnation rate (13599e63b4, folds 29d9c64d2d)

**Files:**
- Modify: `services/health.py` (`spend`, `signals`)
- Modify: `scripts/status.py` (`render`)
- Modify: `services/review.py` (the fleet table)
- Test: `tests/test_health.py`, `tests/test_status.py`, `tests/test_review.py`

**Interfaces:**
- Produces: `health.spend(events, now, window=3600.0) -> dict`, with these keys:
  - `requests`, `tokens`, `refused` (unchanged);
  - `prompt_tokens`, `completion_tokens`, `cached_tokens`, `priced` (closes that carried usage);
  - `cache_share` (float in 0..1, or None);
  - `mean_prompt_tokens` (int, or None).
- Produces: `signals[...]["incarnations_last_hour"]`, an int: incarnations whose first answered request falls inside the hour.

- [ ] **Step 1: Failing tests** in `tests/test_health.py`:
  - `test_spend_counts_prompt_completion_and_cached_tokens_from_core_closes`. Two core closes, with usage `{"prompt_tokens":1000,"completion_tokens":50,"total_tokens":1050,"cached_tokens":800}` and `{"prompt_tokens":3000,"completion_tokens":10,"total_tokens":3010}`, plus one stream close. Expect:
    - `prompt_tokens == 4000`, `cached_tokens == 800`, `completion_tokens == 60`;
    - `priced == 2`, `cache_share == 0.2`, `mean_prompt_tokens == 2000`.
  - `test_spend_ignores_usage_that_is_not_a_non_negative_integer`. Values `True`, `-5`, `1.5`, `"9"` and `None` contribute nothing, and a close with only such values is not `priced`.
  - `test_cache_share_is_none_when_nothing_was_prompted`.
  - `test_incarnations_last_hour_counts_fresh_starts_inside_the_hour`. Three incarnations, the first two hours old, expect 2.
- [ ] **Step 2:** Run `python3 -m pytest tests/test_health.py -q`. Expected: the four FAIL on missing keys.
- [ ] **Step 3: Implement.**
  - In `spend`, count the integer, non-bool, non-negative `prompt_tokens`, `completion_tokens` and `cached_tokens` from each close's `usage`. The recorder flattens `prompt_tokens_details.cached_tokens` into `usage.cached_tokens` (`recorder/proxy.py:1331-1338`).
  - Compute `cache_share = cached/prompt` when `prompt > 0`, and `mean_prompt_tokens = prompt // priced` when `priced`.
  - In `signals`, add `incarnations_last_hour` from each group's first timestamp.
- [ ] **Step 4: Failing tests** in `tests/test_status.py` and `tests/test_review.py`:
  - `test_status_shows_cache_share_and_incarnations_this_hour` asserts `cache 20%` and `inc/h 2` in the line, and `cache —` when the share is None.
  - `test_the_fleet_table_shows_the_cache_share` asserts the review fleet page has a `cache` header and `20%`.
- [ ] **Step 5:** Render.
  - `status.render` adds `f"cache {pct}"` and `f"inc/h {n}"` after `hour`.
  - The review fleet table gains a `cache` column.
  - Both read with `.get` and fall back to `—` for fleet.json files published before this change.
- [ ] **Step 6:** Run `python3 -m pytest tests/test_health.py tests/test_status.py tests/test_review.py tests/test_observer.py -q`. Expected: PASS.
- [ ] **Step 7:** Commit with the message `health: spend reads prompt and cache tokens; incarnations this hour`.

### Task 2: The operator's JSONL logs rotate (639443e993)

**Files:**
- Modify: `services/common.py` (`append_jsonl`, plus a new `JSONL_MAX_BYTES`)
- Test: `tests/test_common.py`. Create it if absent; otherwise add to the file that tests `common`.

**Interfaces:**
- Produces: `common.append_jsonl(path: Path, record: dict, max_bytes: int = JSONL_MAX_BYTES) -> None`, with `JSONL_MAX_BYTES = 64 * 1024 * 1024`.
- Produces: `common.previous_generation(path: Path) -> Path`, which returns `<stem>.1<suffix>` (`fleet.jsonl` gives `fleet.1.jsonl`).

- [ ] **Step 1: Failing tests:**
  - `test_append_rotates_to_one_previous_generation_past_the_cap`. With `max_bytes=200`, write records until rotation. Then `previous_generation(path)` exists, the current file holds the newest record, and the total line count across both files equals what was written since the last rotation boundary.
  - `test_a_second_rotation_replaces_the_previous_generation`.
  - `test_a_record_larger_than_the_cap_is_still_written_whole`.
  - `test_append_never_truncates_the_current_file_in_place`. The inode of the rotated file is the old current file's inode.
- [ ] **Step 2:** Run the tests. Expected: FAIL (TypeError on `max_bytes`, or no rotation).
- [ ] **Step 3: Implement.**
  - Before appending, if the file exists and `size + len(line)` exceeds `max_bytes` and `size > 0`, `os.replace(path, previous_generation(path))`.
  - Then append as before.
  - Update the docstring: append-only within a generation; one previous generation kept; a reader that wants more than the current generation reads both.
- [ ] **Step 4:** Run `python3 -m pytest tests/test_common.py tests/test_observer.py tests/test_journal.py -q`. Expected: PASS.
- [ ] **Step 5:** Commit with the message `common: the operator's JSONL logs rotate at 64 MiB, one previous generation kept`.

### Task 3: The window's headroom is pinned (3c98f068b5, absorbs 8da4399e69)

The default model `deepseek/deepseek-v4-pro` has a context of 1,048,576 tokens, and 1,024,000 at OpenRouter's top provider. Its completion ceiling is 384,000. Both are from OpenRouter's public `/api/v1/models`, 2026-10-09. The default window of 200,000 is therefore far from parity.

The real risk is a smaller-context model set per host. `deepseek/deepseek-v3.2` is 163,840, below the default window.

**Files:**
- Create: `harness/tests/test_window_headroom.py`
- Modify: `.env.example` (the window section)
- Modify: `docs/design.md` §6 (the conversation window)

- [ ] **Step 1: Failing test:** `test_the_default_window_leaves_room_for_the_tools_and_a_full_reply_on_the_default_model`.
  - Read the window default from `docker-compose.yml` (`${CONTEXT_WINDOW_TOKENS:-N}`).
  - Estimate the seed's tool-schema tokens as `len(json.dumps(agent.tools.schemas)) // 4`.
  - Assert `window + schemas + 384_000 <= 1_024_000`.
  - Also assert `schemas > 0`, so the estimate is not vacuous.
  - The constants carry their source and date in a comment.
  - RED: first run it with the window read from the wrong pattern, or write the assertion against a 900,000 window, to watch it fail. Record which in the ledger.
- [ ] **Step 2:** In the `.env.example` window section, state the rule:
  - the window, plus the tool schemas (about N tokens in the seed), plus the model's reply, must fit the model's context;
  - for a host given a smaller-context model, lower that host's window with `HOSTn_CONTEXT_WINDOW_TOKENS`.
  - Name v3.2's 163,840 as the example.
- [ ] **Step 3:** In design.md §6 "The conversation window", add a bullet:
  - the window counts messages only;
  - tool schemas and the reply sit outside it;
  - an overflow is a 400 that the chassis repairs once and then ends as exit 43, with a fresh conversation;
  - the default leaves room on the default model.
- [ ] **Step 4:** Run `python3 -m pytest harness/tests/test_window_headroom.py tests/test_doc_claims.py tests/test_startup.py -q`. Expected: PASS.
- [ ] **Step 5:** Commit with the message `window: the default's headroom on the default model is pinned and the rule documented`.

### Task 4: The reasoning resend is the provider's contract (deae4f4801)

DeepSeek's thinking-mode guide says that when the model made a tool call, the assistant's `reasoning_content` must be sent back in every later request; with tools present, omitting it is a 400. OpenRouter accepts `reasoning_content` as an alias of `reasoning` and says preserving it matters for tool calls. The seed keeps reasoning only on tool-call messages (`harness/chassis.py:522-525`), so it does what the contract asks.

**Files:**
- Create: `harness/tests/test_reasoning_contract.py`
- Modify: `docs/design.md` §6

- [ ] **Step 1: Test:** `test_the_send_view_keeps_reasoning_on_tool_call_messages_and_drops_none`. Build a history:
  - system;
  - user;
  - assistant with `tool_calls` and `reasoning_content`;
  - tool result;
  - assistant without tool calls (no reasoning).

  Pass it through `repair_send_view(clip_to_window(condense_duplicate_tool_results(history), 200000))` and assert the tool-call message still carries `reasoning_content`. It pins a property the code has, so its RED is a mutation: delete the key in a copy and watch it fail.
- [ ] **Step 2:** In design.md §6, add a bullet that reasoning rides on tool-call messages because the provider requires it, with sources. Aurora's last-resort repair strips it, which may itself be refused; that is the agents' code to change.
- [ ] **Step 3:** Run `python3 -m pytest harness/tests/test_reasoning_contract.py -q`. Expected: PASS.
- [ ] **Step 4:** Commit with the message `reasoning: the resend DeepSeek's contract requires is pinned and documented`.

### Task 5: Archived conversations are bounded (the gap)

Every `done`, and every fresh restore, copies the conversation into `tombstones/` and into the git directory (`harness/watchdog.py:432-439`). The chassis also writes `session_*.json` on exit 43, and `corrupt_session_*`. `done` writes `incarnation-*.txt`. Nothing prunes any of them. They live on the 1 GiB `/work` tmpfs, which counts against the 3 GB memory limit, and the mirror copies `tombstones/` to `/telemetry` every 5 s.

**Files:**
- Modify: `harness/watchdog.py`, adding `ARCHIVE_KEEP`, `ARCHIVE_MAX_BYTES` and `prune_archives`, with a call from `fresh_session` and from `run_watchdog`'s start.
- Create: `harness/tests/test_archive_pruning.py`

**Interfaces:**
- Produces:
  - `watchdog.ARCHIVE_KEEP = 20`;
  - `watchdog.ARCHIVE_MAX_BYTES = 256 * 1024 * 1024`;
  - `watchdog.ARCHIVE_PATTERNS = ("session_*.json", "corrupt_session_*", "incarnation-*.txt")` for `tombstones/`, and `("session_recovery_*.json",)` for the git directory;
  - `watchdog.prune_archives(work_dir=WORK_DIR) -> int`, which returns the number of files removed.

- [ ] **Step 1: Failing tests:**
  - `test_prune_keeps_the_newest_twenty_archives_per_directory`. Create 25 `session_recovery_<n>.json` files in tombstones and 25 in `.git`, with ascending mtimes. After pruning, the newest 20 remain in each.
  - `test_prune_keeps_the_newest_archives_within_the_byte_budget`. Use a monkeypatched `ARCHIVE_MAX_BYTES` and three files of 40% each; the newest two remain. The newest always remains, even when it alone exceeds the budget.
  - `test_prune_never_touches_the_notes_symlinks_or_other_files`. Check `recovery_note.txt`, `synthetic_note.txt`, `incarnation_note.txt`, a symlink named `session_x.json`, and `my_memory.json`.
  - `test_prune_failure_never_raises_into_recovery`. Use an unreadable directory, or monkeypatch `os.remove` to raise OSError; expect a return of 0 and a printed line.
  - `test_a_fresh_session_archive_prunes_the_old_ones`. `Recovery.fresh_session` with 25 existing archives leaves 20 plus the new one, within the cap.
- [ ] **Step 2:** Run the tests. Expected: FAIL (no `prune_archives`).
- [ ] **Step 3: Implement `prune_archives`.**
  - For each directory, collect regular files only (`os.lstat`, `stat.S_ISREG`) matching its patterns, sorted newest first by `(mtime, name)`.
  - Keep while `kept < ARCHIVE_KEEP` and `bytes + size <= ARCHIVE_MAX_BYTES`; always keep the first.
  - Remove the rest, then print `pruned N archive(s)` when N > 0.
  - Catch OSError per file and per directory.
  - Call it after the copy in `fresh_session`, and once at watchdog start.
  - The docstring says why: the tmpfs counts against memory, the mirror copies `tombstones/`, and the agent can change the figures.
- [ ] **Step 4:** Run `python3 -m pytest harness/tests -q -n 8`. Expected: PASS.
- [ ] **Step 5:** Commit with the message `watchdog: archived conversations are bounded, newest twenty within 256 MiB`.

### Task 6: Reviews, the whole suite, the live run

- [ ] **Step 1:** Run the whole suite (`python3 -m pytest -q -n 8`), ruff check and format, and `python3 -m pytest live -q`. Expected: green, with live at 14/14.
- [ ] **Step 2: Opus subagent review** of the branch range against this plan and the spec. Then one fix pass, each fix RED→GREEN.
- [ ] **Step 3: Final review: one Astra (high) run with codex-cli,** read-only. Then one fix pass.
- [ ] **Step 4: Filigree.**
  - File the gap.
  - Comment on each of the five issues with the commits that address them.
  - Closing waits for the port to land, which is John's call.
