# Long-life follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four items the Long-life re-triage left open (filigree `space_chassis-c8e27e645c`, comment 30), and the archive-growth gap it found. Revised after the Opus plan review (2026-10-09); its findings and the rulings on them are in the ledger.

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
- No brief or prompt text changes without John (spec §6). Task 5 adds a fact about the agent's world (old archives are pruned); its brief clause is drafted in `docs/drafts/` for John, not shipped.
- Task 5 is a named deviation from spec §3 ("watchdog: ported as-is"): Aurora prunes no archive. John's goal (2026-10-09, "execute ... the gap") authorises it. It is argued as a resource bound, like `AGENT_LOG_MAX_BYTES`, not a behaviour policy (ruling 4).
- Tests are named as sentences; tests never skip for a missing docker or git.
- No push, no merge.

## Review Focus

1. **A close event whose usage is missing, a bool, negative or a float, or whose `cached_tokens` has no valid `prompt_tokens` beside it.** Spend ignores what it cannot use, and the cache share never exceeds 1. Task 1 tests it.
2. **An hour with no prompt tokens, or a fleet.json published before this change.** Status prints `—`. Task 1 tests it.
3. **A transcript tail too short to see the incarnation boundary.** Task 1 tests it:
   - `inc/h` counts only fresh starts;
   - it is marked `+` when the window is truncated;
   - it never counts the tail's first record as a start.
4. **A JSONL record bigger than the cap, a failed rotation, a second rotation.** Task 2 tests it:
   - the record is still written;
   - one previous generation is kept;
   - nothing is truncated;
   - a failed rename never stops the append.
5. **Pruning against the agent's own files.** Task 5 tests it:
   - Only the harness's conversation bodies are pruned, and only regular files in directories that are not symlinks.
   - Never `incarnation-*.txt` or the notes.
   - Never the archive just made.
   - Never an exception into recovery.
   - The exit-43 path is pruned too.

Not testable here: a smaller-context model set per host, in `.env`. Task 3 documents the rule, and its test is a tripwire on the default only.

---

### Task 1: Spend shows prompt, cache and incarnation rate (13599e63b4, folds 29d9c64d2d)

**Files:**
- Modify: `services/health.py` (`spend`, `signals`)
- Modify: `scripts/status.py` (`render`)
- Modify: `services/review.py` (the fleet table)
- Test: `tests/test_health.py`, `tests/test_status.py`, `tests/test_review.py`

**Interfaces:**
- Produces: `health.spend(events, now, window=3600.0) -> dict` with these keys:
  - `requests`, `tokens` and `refused` (unchanged);
  - `prompt_tokens`, `completion_tokens` and `cached_tokens`;
  - `priced`: closes with a valid `prompt_tokens`;
  - `cache_share`: a float in 0..1, or None;
  - `mean_prompt_tokens`: an int, or None.
- A usage value is valid when it is an int, not a bool, and >= 0. `cached_tokens` counts only when the same close has a valid `prompt_tokens`, and then at most that `prompt_tokens`.
- Produces: `signals[...]["incarnations_last_hour"]`, an int. It counts the groups whose first record `is_fresh_start` and falls inside the hour. The tail's first group, if it is not a fresh start, is not counted.

- [ ] **Step 1: Failing tests** in `tests/test_health.py`:
  - `test_spend_counts_prompt_completion_and_cached_tokens_from_core_closes`:
    - Two core closes: usage `{"prompt_tokens":1000,"completion_tokens":50,"total_tokens":1050,"cached_tokens":800}` and `{"prompt_tokens":3000,"completion_tokens":10,"total_tokens":3010}`. Plus a stream close.
    - Expect `prompt_tokens == 4000`, `cached_tokens == 800`, `completion_tokens == 60`, `priced == 2`, `cache_share == 0.2` and `mean_prompt_tokens == 2000`.
  - `test_spend_ignores_usage_that_is_not_a_non_negative_integer`: `True`, `-5`, `1.5`, `"9"` and `None` count nothing.
  - `test_cached_tokens_without_prompt_tokens_count_nothing`: a close with only `cached_tokens: 500`. Expect `cached_tokens == 0`, `priced == 0` and `cache_share is None`.
  - `test_cache_share_is_none_when_nothing_was_prompted`.
  - `test_incarnations_last_hour_counts_fresh_starts_inside_the_hour`: three fresh starts, the first two hours old. Expect 2.
  - `test_a_tail_that_opens_mid_incarnation_counts_no_start`: records whose first carries an assistant message. Expect 0.
- [ ] **Step 2:** Run `python3 -m pytest tests/test_health.py -q`. Expected: the six FAIL.
- [ ] **Step 3:** Implement as the Interfaces say. The recorder flattens `prompt_tokens_details.cached_tokens` into `usage.cached_tokens` (`recorder/proxy.py:1331-1338`).
- [ ] **Step 4: Failing tests:**
  - `test_status_shows_cache_share_prompt_size_and_incarnations_this_hour` (`tests/test_status.py`):
    - The line holds `cache 20%`, `prompt 2000` and `inc/h 2`.
    - It holds `inc/h 2+` when `window.truncated`.
    - It holds `cache —` and `prompt —` for None and for a fleet.json that lacks the keys.
  - `test_the_fleet_table_shows_the_cache_share` (`tests/test_review.py`): a `cache` header and `20%`.
- [ ] **Step 5:** Render.
  - `status.render` adds `cache`, `prompt` and `inc/h` after `hour`.
  - The review fleet table gains a `cache` column.
  - Both read with `.get` and print `—` when a value is missing.
- [ ] **Step 6:** Run `python3 -m pytest tests/test_health.py tests/test_status.py tests/test_review.py tests/test_observer.py -q`. Expected: PASS.
- [ ] **Step 7:** Commit with the message `health: spend reads prompt and cache tokens; incarnations this hour`.

Not done, and said so on the issue: the issue's ladder give-up count and checkpoint size.
- The ladder state is in `.git`, which the mirror excludes, and it is agent-writable.
- The session is the agent's claim.

Spec §3.4 keeps signals to the recorders' lines, and the journal already records container restarts and the watchdog's exit lines.

### Task 2: The operator's JSONL logs rotate (639443e993)

**Files:**
- Modify: `services/common.py` (`append_jsonl`, plus new `JSONL_MAX_BYTES` and `previous_generation`)
- Create: `tests/test_common.py`

**Interfaces:**
- Produces: `common.append_jsonl(path: Path, record: dict, max_bytes: int = JSONL_MAX_BYTES) -> None`, with `JSONL_MAX_BYTES = 64 * 1024 * 1024`.
- Produces: `common.previous_generation(path: Path) -> Path`, which returns `<stem>.1<suffix>`.

- [ ] **Step 1: Failing tests:**
  - `test_append_rotates_to_one_previous_generation_past_the_cap`. With `max_bytes=200`, write ten records. Then:
    - the previous generation exists;
    - the current file's last line is the tenth record;
    - lines(current) + lines(previous) == the records written since the first rotation began, counted by the test.
  - `test_a_second_rotation_replaces_the_previous_generation`.
  - `test_a_record_larger_than_the_cap_is_still_written_whole`.
  - `test_rotation_renames_and_never_truncates`: the previous generation's inode is the old current file's.
  - `test_a_failed_rotation_still_appends`: the previous-generation path is a directory, and the record is appended.
  - `test_the_cap_counts_bytes_not_characters`: non-ASCII records rotate by their UTF-8 size.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Measure the line as `len(line.encode("utf-8")) + 1`.
  - Rotate when the file exists, is non-empty, and `size + that` exceeds `max_bytes`, using `os.replace` to the previous generation.
  - Suppress an OSError from the rename, then append.
  - The docstring states three things:
    - append-only within a generation, with one previous generation kept;
    - a single writer per file (the fleet monitor; one journal pass at a time);
    - nothing in production reads these files, so no reader changes. 639443e993's "readers read both generations" applies to people and `live/` only.
- [ ] **Step 4:** Run `python3 -m pytest tests/test_common.py tests/test_observer.py tests/test_journal.py -q`. Expected: PASS.
- [ ] **Step 5:** Commit with the message `common: the operator's JSONL logs rotate at 64 MiB, one previous generation kept`.

### Task 3: The window's headroom on the default model (3c98f068b5, absorbs 8da4399e69)

OpenRouter's `/api/v1/models` gave these figures on 2026-10-09; the raw lines are in the ledger:

| Model | Context | Top provider | Max completion |
|---|---|---|---|
| `deepseek/deepseek-v4-pro` | 1,048,576 | 1,024,000 | 384,000 |
| `deepseek/deepseek-v3.2` | 163,840 | | |

**Files:**
- Create: `tests/test_window_headroom.py`. It stays in the root suite, which already parses compose, so the vendored harness suite stays clean.
- Modify: `.env.example` (the window section) and `docs/design.md` §6 (the conversation window).

- [ ] **Step 1: Test** `test_the_default_window_leaves_room_for_the_tools_and_a_full_reply_on_the_default_model`.
  - Read the innermost default of `agent_1`'s `CONTEXT_WINDOW_TOKENS` from `docker-compose.yml`, through `compose_text`. It is nested as `${HOST1_…:-${CONTEXT_WINDOW_TOKENS:-N}}`.
  - Measure the seed's schemas with a subprocess in `harness/`: `python3 -c "import agent, json; print(len(json.dumps(agent.tools.schemas)))"`. Count tokens as chars/4.
  - Assert `1.25 * (window + schemas) + 384_000 <= 1_024_000`. The 1.25 is the margin for the chars/4 estimator undercounting JSON.
  - Also assert `schemas > 0`.
  - RED: run it once with the constant 1_024_000 replaced by 500_000, and record the failure in the ledger. It is a tripwire on the default, and its docstring says so.
- [ ] **Step 2:** In `.env.example`, state the rule. The window, plus the tool schemas (about N tokens in the seed), plus the reply, all with a margin, must fit the model's context. A host given a smaller model lowers `HOSTn_CONTEXT_WINDOW_TOKENS`; v3.2's 163,840 is below the default.
- [ ] **Step 3:** In design.md §6 "The conversation window", add a bullet:
  - the window counts messages only;
  - tool schemas and the reply sit outside it;
  - an overflow is a 400, which the chassis repairs once (at the same budget) and then ends as exit 43 with a fresh conversation;
  - the default leaves room on the default model.
- [ ] **Step 4:** Run `python3 -m pytest tests/test_window_headroom.py tests/test_doc_claims.py tests/test_startup.py -q`. Expected: PASS.
- [ ] **Step 5:** Commit with the message `window: the default's headroom on the default model is pinned and the rule documented`.

### Task 4: The reasoning resend is the provider's contract (deae4f4801)

The sources:
- DeepSeek's thinking-mode guide (api-docs.deepseek.com/guides/thinking_mode): when the model made a tool call, its `reasoning_content` must be sent back in every later request; with tools present, omitting it is a 400.
- OpenRouter (openrouter.ai/docs/use-cases/reasoning-tokens): it accepts `reasoning_content` as an alias of `reasoning`, and preserving it matters for tool calls.

The seed keeps reasoning on tool-call messages and resends it (`harness/chassis.py:522-525`). `harness/tests/test_session_persistence.py::test_tool_loop_resends_assistant_reasoning_content` already pins that through `run_agent_loop`, so no new test.

**Files:**
- Modify: `docs/design.md` §6

- [ ] **Step 1:** In design.md §6, add a bullet:
  - reasoning rides on tool-call messages because the provider requires it (both sources, plus the existing test's name);
  - a reply with no content carries its reasoning as content (`chassis.py:522`);
  - Aurora's last-resort repair strips reasoning (`chassis.py:299`), which a provider enforcing the contract may refuse. That is the agents' code to change.
- [ ] **Step 2:** Run `python3 -m pytest tests/test_doc_claims.py tests/test_citations.py -q`. Expected: PASS.
- [ ] **Step 3:** Commit with the message `reasoning: the resend is DeepSeek's contract, documented`.

### Task 5: Archived conversations are bounded (the gap)

The archive files have three writers, and nothing prunes them:
- every fresh restore copies the conversation into `tombstones/session_recovery_*.json` and into the git directory (`harness/watchdog.py:432-439`);
- the chassis writes `tombstones/session_<stamp>.json` on exit 43 (`chassis.py:346`);
- an unreadable session becomes `corrupt_session_*.json`.

They sit on the 1 GiB `/work` tmpfs, which counts against the 3 GB memory limit. A full `/work` makes `restore` fail with ENOSPC. That exhausts the ladder and forces a reseed, which erases the agent's own tag moves, a worse loss than old archives.

The git-directory copies also count against the journal's 256 MiB `tar` limit (`scripts/journal.py:64,175`). The journal's extractor discards them anyway, so it stops reading them.

**Files:**
- Modify: `harness/watchdog.py`. It gets `ARCHIVE_KEEP`, `ARCHIVE_TOMBSTONE_BYTES`, `ARCHIVE_GIT_BYTES` and `prune_archives`, called from `Recovery.restore` whenever `fresh` and once at watchdog start.
- Modify: `scripts/journal.py` (`stream_work`): `tar --exclude=./.git/session_recovery_*`, or the member form tar needs for `-C /work .git`, verified by a test.
- Modify: `README.md`. Its journal paragraph says "archived conversations and all"; the extractor keeps objects and packs only.
- Create: `harness/tests/test_archive_pruning.py`.
- Draft: `docs/drafts/WORLD-archives.md`, one clause for `brief/WORLD.md:87` ("the newest twenty are kept"), for John.

**Interfaces:**
- Produces:
  - `watchdog.ARCHIVE_KEEP = 20`;
  - `watchdog.ARCHIVE_TOMBSTONE_BYTES = 128 * 1024 * 1024`;
  - `watchdog.ARCHIVE_GIT_BYTES = 64 * 1024 * 1024`;
  - `watchdog.prune_archives(work_dir=WORK_DIR, keep_newest=None) -> int`, which returns the number of files removed. `keep_newest` names an archive that is kept whatever its mtime.
- The patterns:
  - `tombstones/`: `session_*.json` (both writers) and `corrupt_session_*.json`;
  - the git directory, from `git rev-parse --absolute-git-dir` as `Recovery` resolves it (`watchdog.py:378`): `session_recovery_*.json`.
- Never `incarnation-*.txt`, `corrupt_session_*.txt` or any note.
- The budget arithmetic: 128 MiB + 64 MiB is 192 MiB of the 1 GiB tmpfs, and the git-directory share stays well inside the journal's limit even before the exclude.
- The byte rule walks newest first:
  - keep while `kept < ARCHIVE_KEEP` and `bytes + size <= budget`;
  - stop at the first file over budget, and remove it and everything older;
  - the newest is always kept.

- [ ] **Step 1: Failing tests:**
  - `test_prune_keeps_the_newest_twenty_archives_per_directory`: 25 files in each directory, with ascending mtimes. 20 remain in each.
  - `test_prune_stops_at_the_byte_budget_and_always_keeps_the_newest`.
  - `test_prune_never_touches_notes_symlinks_or_other_files`. It checks:
    - `recovery_note.txt`, `synthetic_note.txt` and `incarnation_note.txt`;
    - `incarnation-1-2.txt` and `corrupt_session_1.txt`;
    - a symlink named `session_x.json`;
    - `my_memory.json`;
    - a `tombstones` that is a symlink to elsewhere, which is not walked.
  - `test_prune_failure_never_raises_into_recovery`: monkeypatch `os.remove` to raise. Expect 0 removed and a printed line.
  - `test_a_fresh_restore_prunes_and_keeps_the_archive_it_just_made`. It uses a git repo (`repo_at`, imported from `test_evolving_recovery`) and 25 older archives with newer mtimes than the session's. After `restore(..., fresh=True)`, 20 remain, including the new one.
  - `test_the_exit_43_path_is_pruned_too`: no session file, 25 chassis `session_<stamp>.json` files, then `restore(..., fresh=True)`. 20 remain.
  - `tests/test_journal.py::test_the_journal_tar_leaves_out_the_archived_conversations`: the command `stream_work` builds excludes `session_recovery_*` under `.git`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement.
  - `lstat` each directory and skip it unless it is a real directory.
  - Collect regular files matching the patterns, sorted newest first by `(mtime_ns, name)`, with `keep_newest` placed first.
  - Catch OSError per file and per directory.
  - Print `pruned N archive(s)` when N > 0.
  - The docstring states the ENOSPC reason, the precedent of `AGENT_LOG_MAX_BYTES`, and that the agent can change the figures.
- [ ] **Step 4:** Run `python3 -m pytest harness/tests -q -n 8` and `python3 -m pytest tests/test_journal.py -q`. Expected: PASS.
- [ ] **Step 5:** Commit with the message `watchdog: archived conversations are bounded; the journal skips them`.

### Task 6: Reviews, the whole suite, the live run

- [ ] **Step 1:** Run the whole suite (`python3 -m pytest -q -n 8`), ruff check and format, and `python3 -m pytest live -q`. Expected: green, live 14/14.
- [ ] **Step 2: Opus subagent review** of the execution range against this plan and the spec. Then one fix pass, each fix RED→GREEN.
- [ ] **Step 3: Final review:** one Astra (high) run through codex-cli, read-only. Then one fix pass.
- [ ] **Step 4: Filigree.**
  - File the gap.
  - Comment on each of the five issues with the commits, and state Task 1's two omissions on 13599e63b4.
  - Closing waits for the port to land, which is John's call.
