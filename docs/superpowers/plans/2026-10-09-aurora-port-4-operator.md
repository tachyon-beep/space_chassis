# Aurora port, plan 4: the operator surfaces

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The operator can see what each agent is doing, and what it did, from records the agents cannot write. This covers health signals derived from the recorders' transcripts, a staleness report in `status.py`, the fleet monitor and review panel reading Aurora's formats, and an append-only operator journal of `/work`, `/shared`, restarts and watchdog lines that runs no agent code.

**Architecture:**
- One stdlib module, `services/health.py`, derives every signal from transcript and event lines.
- Three readers share it:
  - `scripts/status.py` on the host;
  - `services/fleet_monitor.py` in its container, writing `fleet.json`;
  - `services/review.py`, which renders `fleet.json` plus turns.
- `scripts/journal.py` is a host-side poller. It takes `/work/.git` out of each agent with `exec tar`, imports the objects and refs as files into a host-owned bare repository, and never opens the agent's copy with git.

**Tech Stack:** Python 3 standard library only, operator side. Host `git` and `docker compose` for the journal. pytest, and the live smoke stack from plan 3c.

**Spec:** `docs/superpowers/specs/2026-10-09-aurora-port-design.md`: §3 (the operator-surfaces row), §3.4, §5 and §9 items 3 and 8. Approved 2026-10-09.

## Rulings this plan rests on

1. **The journal does not use `docker cp`.** Spec §3.4 names it, and it cannot work: `/work` is a tmpfs mount, and `docker cp` reads the container's root filesystem, not its mounts. This was verified on 2026-10-09: a file present in a tmpfs `/work` gave `Could not find the file`, while `docker exec … tar -cf - -C /work …` streamed it.
   - The journal therefore runs `$COMPOSE exec -T <agent> tar -cf - -C /work .git`.
   - `tar` comes from the read-only image root, and `docker exec` runs with the container's configured environment, not the agent's runtime one, so the copy step runs no agent code.
   - *Cost if wrong:* one process that the agent's uid can observe or signal. It can only spoil a snapshot, and the snapshot is the agent's claim anyway.
2. **The copied `.git` is never opened by host git:** not with `--git-dir`, not as a cwd, not as the source of a `fetch`, `clone` or `bundle`. Its `config` is the agent's: `core.hooksPath`, `core.fsmonitor`, `core.sshCommand` and `include.path` would all come with it.
   - The journal creates a host-owned bare repository with a host-written config.
   - It copies `objects/` and the ref values in as files, then verifies with `git fsck` in the host repository.
   - That repository *is* the bundle. Spec §3.4's "bundled by the host's own git" is met by host git owning the store; there is no separate `git bundle` file.
3. **The recorder is not changed.** Transcript lines carry no `id`, and nothing here needs a join:
   - spend and refusals come from `events.jsonl` `close` records;
   - prompt hashes, tool errors and incarnation boundaries come from transcript request bodies;
   - tool pairing uses the ids already inside the messages.
4. **A fresh incarnation is a core request whose `messages` hold no `assistant` message.** A `reset`, an exit-0 restart, a pause and `baseline_same` all keep the conversation, so they do not count as boundaries. The only record of those is the agent's own claim: the recovery note in the mirror and the watchdog lines. Both are shown, and both are labelled as claims.
5. **Watchdog lines are the agent's claim.** The agent's stdout is tee'd into the watchdog's, so `docker logs` can be forged. The journal records them with `"claim": "agent"`. Restart counts from `docker inspect` are not claims.
6. **The journal is bounded.** A `/work/.git` stream larger than `JOURNAL_MAX_BYTES` (256 MiB) or slower than `JOURNAL_TIMEOUT_SECONDS` (120) is recorded as `skipped` and not stored. `/shared` is snapshotted only when its total size is under the same cap; otherwise it is recorded as `skipped` with that size.

## Global Constraints

- Operator-side code is **standard library only**. Every published file goes through `common.write_json_atomic`, every append through `common.append_jsonl`, and every read of an agent-writable or recorder-written file is bounded by `common.MAX_READ_BYTES` (4 MiB), through `read_bounded`, `read_json` or `tail_jsonl`.
- No request header is ever read or shown. The transcripts hold bodies only.
- The review panel never writes. `test_no_path_in_the_panel_opens_a_file_for_writing` stays binding.
- Volume paths come from `scripts/volume_images.py`: `volumes_root()`, and the `<kind>_<slug>/data` layout. Slugs come from `operator/roster.json` when present, otherwise from `transcripts_<slug>` directories under the volume root.
- Every surface labels agent-written inputs as **the agent's claim**: the mirror, recovery notes, tombstones, `agent_stdout.log`, pump `state.json` and watchdog log lines.
- Tests are full sentences. There are no skips: a test that needs docker or git fails without them, as `test_live_stack.py` does.
- The live tests run only against the smoke project. The journal writes under `<smoke root>/journal` there, never under `operator/journal`.
- Do not touch `docs/deep_research/vehicle` or `docs/plans/`. Do not read `.env`. Do not push.

## Review Focus

1. **The journal opens the agent's `.git` with host git.** No host git invocation may name a path under the extracted copy. That covers argv, cwd, `GIT_DIR` and `GIT_WORK_TREE`. (Task 5: `test_no_git_call_ever_touches_the_agent_s_copy`, with a recording `git` on `PATH`.)
2. **A hostile or oversized stream.** Each of these must be refused and recorded, never extracted or stored: tar members with `..`, absolute paths, symlinks out of the tree or device files; a stream over the cap; a stream that never ends; refs that are not 40-hex. (Task 5: `test_a_hostile_archive_is_refused`, `test_an_oversized_stream_is_skipped_not_stored`.)
3. **Signals counting a refused request as a request, or a sub-call stream as the core loop.** Every count filters `stream == "core"` (a missing stream counts as core) and separates refusals. (Task 1.)
4. **Staleness inverted.** An agent stopped mid-request must read as `idle-watchdog` while its mirror moves, and as `stale` when both have stopped. A capped agent that writes a 429 every cycle must read as `capped`, never `active`. (Task 2 offline; Task 6 live.)
5. **An agent-written field shown as fact.** Every value from the mirror, the pump or the watchdog lines must carry the claim label in JSON and in HTML. (Tasks 2–4.)

---

## File structure

| File | Responsibility |
|---|---|
| `services/health.py` (new) | Pure functions from transcript and event records to signals. Stdlib only, no I/O beyond bounded reads. |
| `scripts/status.py` (rewritten) | The host-side report: liveness, staleness, signals and claims, per agent. |
| `services/fleet_monitor.py` (rewritten) | In its container: signals per agent into `/telemetry/fleet.json` and `fleet.jsonl`. |
| `services/review.py` (adapted) | Turns from the new transcript shape, and a fleet view from `fleet.json`, with claims labelled. |
| `scripts/journal.py` (new) | The operator journal: `/work/.git` snapshots, `/shared` snapshots, restarts and watchdog lines. |
| `scripts/volume_images.py` / `scripts/build_compose.py` / `docker-compose.yml` | The monitor gains a read-only `/diode` bind, for the vehicle-command count. |
| `live/stack.py`, `live/conftest.py`, `live/test_operator.py` (new) | The smoke stack starts the monitor and review too, and the live checks for 9.3 and 9.8 run there. |
| `tests/test_health.py`, `tests/test_status.py`, `tests/test_journal.py` (new); `tests/test_observer.py`, `tests/test_review.py` (adapted); `tests/fixtures/aurora_transcript.jsonl` (new) | Offline tests. |

---

### Task 1: `services/health.py`, the signals

**Files:**
- Create: `services/health.py`, `tests/test_health.py`.

**Interfaces (Produces):**
- `CORE = "core"`.
- `ERROR_PREFIXES = ("Error parsing JSON arguments", "Error executing tool", "Error: Tool `")`.
- `core_records(records: list[dict]) -> list[dict]`: records whose `stream` is `"core"` or absent, and whose `request` is a dict holding a `messages` list.
- `is_refusal(record: dict) -> bool`: `response` is a dict with an `error` dict.
- `is_fresh_start(messages: list) -> bool`: no message has `role == "assistant"`.
- `incarnations(records: list[dict]) -> list[list[dict]]`: core, non-refused records, split before every fresh start. Records before the first fresh start form the first group.
- `system_prompt_hash(request: dict) -> str | None`: sha256 hex of `messages[0]["content"]` when its role is `system`. A non-string content is hashed as `json.dumps(..., sort_keys=True)`.
- `new_tool_results(messages: list) -> list[dict]`: the `role == "tool"` messages after the last assistant message.
- `tool_errors(records) -> tuple[int, int]`: `(errors, results)` over `new_tool_results` of every core, non-refused request. An error is a content string starting with one of `ERROR_PREFIXES`.
- `spend(events: list[dict], now: float, window: float = 3600.0) -> dict`: over `close` events with `stream` core or absent and a timestamp within `window` of `now`. Returns `{"requests": int, "tokens": int, "refused": int}`: tokens from `usage.total_tokens`, refused from `status` 429 or 503.
- `vehicle_commands(output_dir: Path, start: float, end: float) -> int`: files named `^\d{8}T\d{6}_\d{6}Z_.+\.txt$` whose stamp falls in `[start, end)`. The directory is read at most `MAX_ENTRIES = 10000` entries deep.
- `parse_timestamp(text: str) -> float | None`: the recorder's ISO `…Z` form, to epoch seconds.
- `signals(records, events, *, now: float, caps: dict, output_dir: Path | None) -> dict`. Returns these keys:
  - `incarnations` (int)
  - `requests_per_incarnation` (list of int)
  - `resets` (int: fresh starts after the first)
  - `system_prompt_changes` (int: hash changes between consecutive core requests)
  - `tool_errors`, `tool_results` (int)
  - `refusals` (int)
  - `vehicle_commands_per_incarnation` (list of int, or `None` without `output_dir`)
  - `spend` (`spend()`'s dict)
  - `caps` (echoed)
  - `last_request_at` (epoch float or `None`)
  - `window` (`{"records": n, "first_at": t, "last_at": t}`)
- `read_records(path: Path, max_bytes: int = MAX_READ_BYTES) -> list[dict]`: the bounded tail of a JSONL file, through `common.tail_jsonl`.
- `QUIET_SECONDS = 900`.
- `liveness(transcript_age: float | None, mirror_age: float | None, last_refused: bool, quiet: float) -> str`: the one rule, used by `status.py` and the monitor. It returns one of:
  - `"active"`: transcript age below `quiet` and the last core record not refused;
  - `"capped"`: transcript age below `quiet` and the last record refused;
  - `"idle-watchdog"`: transcript quiet or absent, mirror age below `quiet`;
  - `"stale"`: both quiet;
  - `"unknown"`: no transcript and no mirror.

- [ ] **Step 1: Write the failing tests.**
  - A builder `record(messages, *, stream="core", response=None, at="2026-10-09T00:00:00.000000Z")` makes recorder-shaped lines: `{"timestamp", "stream", "request": {"model": "m", "messages": …}, "response": …}`.
  - Tests:
    - `test_only_the_core_loop_counts_and_a_missing_stream_is_core`
    - `test_a_refused_request_is_a_refusal_not_a_request`: response `{"error": {"message": "rate limited: at most 4 request(s) per hour on this socket"}}`.
    - `test_a_conversation_without_an_assistant_message_starts_an_incarnation`
    - `test_a_reset_that_keeps_the_conversation_is_not_a_boundary`
    - `test_requests_are_counted_per_incarnation`
    - `test_a_changed_system_prompt_is_counted_once_per_change`
    - `test_tool_errors_are_counted_from_the_new_results_only_never_twice`: the same error result carried in three later requests counts once.
    - `test_spend_sums_closes_inside_the_hour_and_counts_429_and_503_as_refused`
    - `test_vehicle_commands_are_counted_by_their_stamp_per_incarnation`: slugs with underscores (`agent_1`), and a file with a bad name ignored.
    - `test_liveness_reads_active_capped_idle_and_stale_from_the_two_clocks`: a table over `liveness()`.
    - `test_signals_survive_an_empty_or_malformed_window`: `[]`, non-dict lines, `request` not a dict, `messages` not a list.
    - `test_health_imports_nothing_outside_the_standard_library_and_common`: an AST check.
- [ ] **Step 2:** Run `python3 -m pytest tests/test_health.py -q -p no:cacheprovider`. Expected: FAIL (`ModuleNotFoundError: health`).
- [ ] **Step 3:** Implement `services/health.py`.
- [ ] **Step 4:** Run it again, expecting PASS. Then run the root suite and `uvx ruff check . --no-cache`.
- [ ] **Step 5:** Commit: `health: the operator's signals, derived from the recorder's transcripts alone`.

### Task 2: `scripts/status.py`, liveness and staleness

**Files:**
- Rewrite: `scripts/status.py`.
- Create: `tests/test_status.py`.
- Modify: `tests/test_observer.py`. Drop its status tests that build the old home, diary and lifecycle world, and keep the not-a-grader AST check over the rewritten file.

**Interfaces:**
- Consumes `health.*` (including `health.liveness` and `health.QUIET_SECONDS`), `volume_images.volumes_root()`, `common.read_json`, `common.read_bounded`.
- Produces:
  - `ROSTER_PATH` (unchanged name, pinned by `test_roster_location.py`).
  - `discover(volumes: Path, roster_path: Path) -> list[tuple[str, str]]`: `(slug, name)` pairs.
  - `agent_row(slug, name, volumes: Path, now: float, quiet: float, caps: dict, container: dict | None) -> dict`. Keys:
    - `slug`, `name`, `liveness`;
    - `transcript_age`, `mirror_age`;
    - `signals`;
    - `container` (`{"state", "restarts"}` or `None`);
    - `claims`: `{"recovery_note", "incarnation_note", "pump_running"}`, each value a dict `{"value": …, "claim": "agent"}`.
  - `container_info(compose: list[str], service: str) -> dict | None`: through `docker inspect` of `compose ps -q`; `None` on any failure.
  - `main(argv) -> int`, with flags:
    - `--json`, `--verbose`;
    - `--volumes PATH` (default `volume_images.volumes_root()`);
    - `--quiet-seconds N`;
    - `--compose "<prefix>"` (default `docker compose -p space-chassis`);
    - `--no-docker`.
- Inputs per agent, under `<volumes>`:
  - the transcript: `transcripts_<slug>/data/agent_life_transcript.jsonl` and `events.jsonl`;
  - the mirror: `telemetry_<slug>/data/work`, whose age is the newest mtime of the directory itself and of `work/agent_stdout.log`;
  - the claims: `telemetry_<slug>/data/work/tombstones/recovery_note.txt` and `incarnation_note.txt`, both bounded, and `pump_<slug>/data/state.json`, counting `entries.*.running`;
  - the vehicle's output: `diode/data/<slug>/output`.
- Caps come from the environment variables `RECORDER_HOURLY_MAX` and `RECORDER_TOKEN_HOURLY_MAX` when set, otherwise the compose defaults (2400 and 200000000). `.env` is never read.
- Each agent is one line: name, liveness, ages, incarnations, requests in the last hour against the cap, and refusals. A `*` marks each claim, with a footnote: "* the agent's own claim".

- [ ] **Step 1: Failing tests.** `tests/test_status.py` builds a new-layout volume tree in `tmp_path`.
  - `test_a_capped_agent_writing_a_refusal_every_cycle_reads_capped_not_active`
  - `test_status_reads_the_new_volume_layout_and_labels_every_claim`: JSON output; every `claims` value carries `"claim": "agent"`.
  - `test_slugs_come_from_the_roster_or_else_the_transcript_directories`
  - `test_status_survives_an_empty_volume_root`: exit 0, no rows.
  - `test_without_docker_the_container_column_is_absent_not_a_failure`: `--no-docker`, and a `--compose` whose binary does not exist.
  - `test_status_never_reads_the_env_file`: `.env` in a temporary `PROJECT` holds a marker key; the output never names it, and the file's atime need not be checked. Implement by checking that `env_file` is not imported (an AST check).
- [ ] **Step 2:** Run `python3 -m pytest tests/test_status.py tests/test_observer.py tests/test_roster_location.py -q -p no:cacheprovider`. Expected: FAIL.
- [ ] **Step 3:** Rewrite `scripts/status.py`.
- [ ] **Step 4:** PASS. Run the root suite and ruff.
- [ ] **Step 5:** Commit: `status: liveness and staleness from the transcript and the mirror, with the agent's claims labelled`.

### Task 3: `services/fleet_monitor.py`, signals into `fleet.json`

**Files:**
- Rewrite: `services/fleet_monitor.py`.
- Modify:
  - `scripts/volume_images.py`: the `diode` kind gains `("monitor", "/diode", True, "")`;
  - `tests/test_volume_images.py` / `tests/test_compose_generated.py`: the monitor's binds;
  - `docker-compose.yml`: regenerated with `python3 scripts/build_compose.py`;
  - `tests/test_observer.py`: the monitor tests, on the new shape.

**Interfaces:**
- Consumes `health.*`.
- Produces `fleet.json`:
  ```
  {"at": iso, "agents": [{"slug", "name", "signals", "transcript_age", "mirror_age",
    "liveness", "claims": {...}}], "summary": {"agents", "active", "capped",
    "idle_watchdog", "stale", "refusals_last_hour"}}
  ```
  It is written with `write_json_atomic` to `/telemetry/fleet.json`. One `{"at", "summary"}` line is appended to `/telemetry/fleet.jsonl` per pass.
- Liveness is `health.liveness`, the same rule `status.py` uses.
- Environment:
  - `TRANSCRIPTS_DIR=/transcripts`, `MIRROR_DIR=/telemetry/agents`, `DIODE_DIR=/diode`, `TELEMETRY_DIR=/telemetry`;
  - `AGENT_SLUGS`, `AGENT_NAME_<slug>`;
  - `MONITOR_INTERVAL_SECONDS`, `QUIET_SECONDS`;
  - `RECORDER_HOURLY_MAX`, `RECORDER_TOKEN_HOURLY_MAX`.
- Removed: `HOME_ROOT`, `DIARY_ROOT`, `ANNOUNCE_DIR`, `PUMP_ROOT`, `WORK_DIR`, `count_work`, and lifecycle reading.

- [ ] **Step 1: Failing tests** (in `tests/test_observer.py`):
  - `test_the_monitor_publishes_signals_for_every_agent_in_the_new_shape`
  - `test_the_monitor_labels_every_mirror_value_as_the_agent_s_claim`
  - `test_the_monitor_never_writes_outside_its_telemetry_directory`: replaces the `.fleet` check.
  - `test_the_monitor_mounts_the_window_read_only` (compose).
  - The not-a-grader AST check, kept, over the new file.
- [ ] **Step 2:** FAIL. **Step 3:** Implement and regenerate compose. **Step 4:** PASS, then the root suite and ruff.
- [ ] **Step 5:** Commit: `monitor: the fleet's signals from the transcripts, with the window mounted read-only for the command count`.

### Task 4: `services/review.py`, the new transcript shape

**Files:**
- Modify: `services/review.py`, `tests/test_review.py`.
- Create: `tests/fixtures/aurora_transcript.jsonl`.

**Interfaces:**
- **A turn** is one core transcript line:
  - `index`: the line's ordinal within the bounded window;
  - `at`: the line's `timestamp`;
  - `incoming`: `health.new_tool_results` plus any trailing `user` messages after the last assistant;
  - `calls`: from `response.choices[0].message.tool_calls`;
  - results paired from the *next* core line's `incoming`, by `tool_call_id`;
  - `refused`: `health.is_refusal`;
  - `fresh`: `health.is_fresh_start`;
  - `system_hash`.
- `new_messages`' exact-prefix rule is removed: it is wrong under the chassis's condensed send view.
- `Conversation` keeps its byte-bounded window, cache and paging, and keys turns by `index`.
- **The fleet view** reads `TELEMETRY_DIR/fleet.json` from the monitor: liveness, signals and claims, with a "the agent's own claim" label on every claim cell. It reads no lifecycle file.
- **The agent view** shows the recovery note from `MIRROR_DIR/<slug>/work/tombstones/recovery_note.txt`, bounded and labelled as a claim.
- **Routes** are unchanged: `/`, `/api/fleet`, `/api/agent/<slug>`, `/api/agent/<slug>/turn/<n>/raw`.
- **The fixture:** the first 40 core lines of `transcripts_agent_1/data/agent_life_transcript.jsonl` from a live smoke run.
  - `live/conftest.py`'s evidence step copies each transcript into `.scratch/live-evidence/transcript_agent_<n>.jsonl` (bounded to 2 MiB). This change lands in this task.
  - Run `python3 -m pytest live -q -p no:cacheprovider` once.
  - Copy the lines into the fixture with `head -n 40`.
  - Check that the copy contains no `sk-` string other than `sk-dummy`. The stub's requests carry no key, because transcripts are bodies only.

- [ ] **Step 1: Failing tests:**
  - `test_a_turn_is_read_from_the_recorder_s_line_shape`
  - `test_tool_results_pair_with_the_next_request_by_call_id`
  - `test_a_refused_turn_shows_the_refusal_and_no_calls`
  - `test_a_fresh_conversation_is_marked_as_a_new_incarnation`
  - `test_the_fleet_view_reads_the_monitor_s_signals_and_labels_claims`
  - `test_the_panel_renders_what_a_real_run_produced`: replaced. It reads the checked-in fixture and renders every turn without an error, and the first turn is `fresh`.
  - Keep, adapted to the new shape: the malformed-arguments tests, the partial-line tests, the bounded-window tests, the cache, paging, route allow-list and 404 tests, and `test_no_path_in_the_panel_opens_a_file_for_writing`.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. Make the fixture with the live run above. **Step 4:** PASS, then the root suite and ruff.
- [ ] **Step 5:** Commit: `review: turns from the recorder's line shape and the fleet from the monitor, claims labelled`.

### Task 5: `scripts/journal.py`, the operator journal

**Files:**
- Create: `scripts/journal.py`, `tests/test_journal.py`.
- Modify: `CLAUDE.md` (Commands).

**Interfaces:**
- **Constants:** `JOURNAL_MAX_BYTES = 256 * 1024 * 1024`, `JOURNAL_TIMEOUT_SECONDS = 120`, `DEFAULT_ROOT = PROJECT / "operator" / "journal"`.
- **Git environment.** `host_git(repo: Path, *args: str, input: bytes | None = None) -> subprocess.CompletedProcess` runs `git --git-dir=<repo> <args>` with:
  - `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0`;
  - cwd = the journal root.
  - It is the only way this module runs git.
- **`stream_work(compose: list[str], service: str, limit: int, timeout: float) -> bytes | str`:**
  - runs `compose + ["exec", "-T", service, "tar", "-cf", "-", "-C", "/work", ".git"]`;
  - reads stdout up to `limit + 1` bytes;
  - returns the bytes, or a reason string: `"too large"`, `"timed out"` or `"exec failed: <rc>"`.
- **`extract(archive: bytes, into: Path) -> dict | str`:**
  - uses `tarfile` with `filter="data"`;
  - extracts only members under `.git/objects/`, `.git/refs/`, `.git/packed-refs`, `.git/HEAD`, `.git/aurora-recovery.json` and `.git/aurora-progress.json`;
  - returns `{"refs": {name: sha}, "head": str, "recovery": dict | None, "progress": dict | None}`, or a refusal reason string;
  - parses refs in Python from the loose ref files and `packed-refs`, keeping only `^[0-9a-f]{40}$` values.
- **`import_snapshot(repo: Path, copy: Path, info: dict, stamp: str) -> str`:**
  - creates `repo` with `git init --bare` through `host_git` on first use, then writes its `config` itself (`core.hooksPath=/dev/null`, `core.fsmonitor=false`);
  - copies loose objects and packs from `copy/.git/objects` into `repo/objects` that are not already present, as plain file copies;
  - runs `host_git(repo, "update-ref", f"refs/journal/{stamp}/{name}", sha)` for each ref, and `refs/journal/{stamp}/HEAD` when HEAD is a sha or a resolvable ref;
  - runs `host_git(repo, "fsck", "--no-dangling", "--connectivity-only")`;
  - on failure, deletes the `refs/journal/{stamp}/` refs and returns `"rejected: fsck"`; otherwise returns `"ok"`.
- **`snapshot_shared(repo: Path, shared: Path, stamp: str, limit: int) -> str`:**
  - if the total size is over `limit`, returns `"skipped: <bytes> bytes"`;
  - otherwise copies the tree into a host temp directory, symlinks as links and never followed;
  - then runs `host_git(repo, "--work-tree=<tmp>", "add", "-A", "--force")`, then `write-tree`, `commit-tree` and `update-ref refs/journal/shared/{stamp}`.
  - The agent-written tree is only ever a temp copy's *content*. Its `.git*` files are data, never config: a `.gitattributes` filter has no host config to name it.
- **`container_events(compose, service, since: str) -> dict`:**
  - `{"restarts": int | None, "state": str | None}` from `docker inspect`;
  - `"watchdog_lines"`: lines from `compose logs --no-color --no-log-prefix --since <since> <service>` that match `^(agent exited \(|agent stopped after inactivity|recovery exhausted|watchdog file changed|Recovery event \d+:)`, capped at 200 lines;
  - `"claim": "agent"` attached to `watchdog_lines`.
- **`journal_once(compose, agents, root: Path, volumes: Path, now: datetime) -> list[dict]`:**
  - one record per agent, appended to `root/<slug>/journal.jsonl`:
    ```
    {"at", "slug", "service", "work": "ok"|<reason>, "refs": {...}, "recovery": {...,"claim":"agent"},
     "restarts", "state", "watchdog_lines": {"lines": [...], "claim": "agent"}}
    ```
  - one `/shared` record appended to `root/shared.jsonl`;
  - `root/<slug>/last_poll` holds the `since` value for the next pass.
- **`main(argv)`:**
  - `--once` or `--every SECONDS`;
  - `--root` (default `DEFAULT_ROOT`);
  - `--volumes` (default `volumes_root()`);
  - `COMPOSE` env (default `docker compose -p space-chassis`);
  - `AGENTS` env (default: every running `agent_*`).
  - The slug for a service is read from `compose exec -T <service> printenv AGENT_SLUG`, falling back to the service name.
- **Extracted copies** live under `root/.incoming/<stamp>-<service>/`. They are removed in `finally`, and `root/.incoming` is never a cwd or a git path.

- [ ] **Step 1: Failing tests** in `tests/test_journal.py`.
  - **The fixture:**
    - A real git repository in `tmp_path` (made with the test's own git, under an env that ignores global config) with a commit, tags `baseline` and `rescue`, and `aurora-recovery.json` in `.git`.
    - Its `.git/config` is planted with `core.fsmonitor = <marker script>`, `core.hooksPath = <dir with marker hooks for every hook name>`, and `include.path = <file that sets core.sshCommand to a marker script>`.
    - A fake `docker` on `PATH` answers `exec -T agent_1 tar …` with `tar -cf - -C <that repo's parent> .git`, plus `ps`, `inspect` and `logs` with canned output.
    - A recording `git` on `PATH` logs argv, cwd, `GIT_DIR` and `GIT_WORK_TREE`, then execs the real git.
  - **Tests:**
    - `test_a_snapshot_lands_in_the_host_repository_with_its_tags`: `refs/journal/<stamp>/tags/baseline` resolves to the source commit.
    - `test_no_git_call_ever_touches_the_agent_s_copy`: no recorded call has argv, cwd, `GIT_DIR` or `GIT_WORK_TREE` under `.incoming`, and no call is `fetch`, `clone`, `bundle`, `pull` or `remote`.
    - `test_nothing_planted_in_the_agent_s_git_config_runs`: no marker file after a snapshot.
    - `test_a_hostile_archive_is_refused`: parametrised over members `../escape`, `/abs`, a symlink to `/etc`, and a device node. Nothing is written outside `.incoming`, and the record says `refused`.
    - `test_refs_that_are_not_object_ids_are_ignored`
    - `test_an_oversized_stream_is_skipped_not_stored`: `limit` set low.
    - `test_a_stream_that_never_ends_times_out`: the fake `docker` sleeps; `timeout` set to 1.
    - `test_a_corrupt_object_is_rejected_by_fsck_and_leaves_no_refs`
    - `test_watchdog_lines_are_recorded_as_the_agent_s_claim_and_restarts_are_not`
    - `test_shared_is_snapshotted_by_content_and_its_gitattributes_run_nothing`: plants `.gitattributes` `* filter=evil` and `.git/config` inside `shared`.
    - `test_the_journal_is_append_only`: two passes give two lines, and the first is unchanged.
    - `test_the_incoming_copy_is_removed_even_when_import_fails`
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS, then the root suite and ruff.
- [ ] **Step 5:** Add to `CLAUDE.md` Commands: `python3 scripts/journal.py --once   # the operator journal: /work/.git, /shared, restarts, watchdog lines`. Commit: `journal: snapshots of each agent's repository and of /shared, imported as data into host-owned git`.

### Task 6: The live checks for 9.3 and 9.8, and the monitor and review in the smoke stack

**Files:**
- Modify: `live/stack.py`, `tests/test_live_stack.py` (offline), `live/conftest.py`.
- Create: `live/test_operator.py`.
- `SmokeStack.up()` also starts `fleet_monitor` and `review`.
- The override gives:
  - `review`: `ports: !reset []`, `image: SMOKE_IMAGE`, and `environment` `AGENT_SLUGS`;
  - `fleet_monitor`: `image: SMOKE_IMAGE`, `AGENT_SLUGS`, `MONITOR_INTERVAL_SECONDS: "5"`, `QUIET_SECONDS: "20"`.
- `prepare()` creates their bind sources (`operator_telemetry/data`).
- **Offline test:** `test_the_smoke_review_publishes_no_port`.
- **The state the live tests start from** (they sort after `test_acceptance.py`):
  - agent_1 is on its marked baseline, active;
  - agent_2 has been reseeded, with the `/state` and `/shared` plants still in place;
  - agent_3 is capped and pausing.

- [ ] **Step 1: Write the live tests.**
  - `test_status_reports_an_agent_stopped_mid_loop_as_an_idle_watchdog_and_a_frozen_one_as_stale` (spec 9.3):
    1. `kill -STOP` agent_1's agent process (`pkill -STOP -f ' /work/agent\.py$'`).
    2. Wait at most 90 s for `python3 scripts/status.py --json --volumes <smoke volumes> --quiet-seconds 20 --compose "<smoke prefix>"` to report agent_1 `idle-watchdog`.
    3. Then `kill -STOP` the watchdog (`pgrep -P 1 -f '[w]atchdog\.py'`) and wait at most 90 s for `stale`.
    4. `kill -CONT` both in a `finally`, and wait for agent_1 to be `active` again.
    5. Also assert that agent_3 reads `capped` or `idle-watchdog` (between pause cycles), and never `active`.
  - `test_the_journal_snapshots_every_agent_and_runs_no_agent_code` (spec 9.8, the journal half):
    1. Plant in agent_2's `/work/.git/config` `core.fsmonitor` and `core.hooksPath` pointing at marker scripts under `/shared/markers-journal/`.
    2. Run `python3 scripts/journal.py --once --root <smoke root>/journal --volumes <smoke volumes>` with `COMPOSE` set to the smoke prefix and an allowlisted environment.
    3. Assert each agent's `journal.jsonl` has a `work: ok` record whose refs include `tags/baseline` and `tags/rescue`.
    4. Assert agent_3's restarts are recorded.
    5. Assert no marker exists in `<volumes>/shared/data/markers-journal`. Neither the host nor the containers may create one.
  - `test_the_monitor_publishes_signals_and_review_serves_them`:
    1. Wait at most 60 s for `<volumes>/operator_telemetry/data/fleet.json` to list three agents, with agent_3's `signals.refusals > 0` and agent_1's `incarnations >= 2`.
    2. `compose exec -T review python3 -c "<urllib GET http://127.0.0.1:8090/api/fleet>"` returns that JSON.
- [ ] **Step 2:** Run `python3 -m pytest live -q -p no:cacheprovider`. Fix each defect test-first in its owning module, and ledger it.
- [ ] **Step 3:** Run the root, harness, recorder and pump suites and ruff. Commit: `live: status, the journal, the monitor and review against the smoke stack`.

---

## What this plan does not do

- Retire `services/chassis.py`, `supervisor.py`, `recorder.py`, `pump.py`, `tasks/` or the old conftest `Stack` (plan 5).
- Rewrite `CLAUDE.md`'s operator-side and exit-code sections, `docs/design.md`, the brief or the prompts (plan 5; prompts need John).
- Schedule the journal: a cron or systemd timer is John's. `--every` is offered.
- Index transcripts across rotation. The signals read the bounded tail of the live file and state their window.
