# Aurora Port, Plan 2: The Recorder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring Aurora's recorder (`proxy.py`, `recorder_streams.py`) into this repository, then add the spec's spend caps on the core socket: an hourly per-agent request and token ceiling, and a fleet-wide token ceiling shared by the ten recorders through a ledger only the recorders can reach.

**Architecture:** The recorder lives in a new `recorder/` directory, the operator side that no agent mounts. Its tests live in `recorder/tests/` and run as their own pytest process, with `harness/` also on the path (two of Aurora's recorder tests import the harness's `chassis`). The vendored files stay byte-close to Aurora at `42faf41`. The caps are a new module, `recorder/core_caps.py`, with a small, named hook in `proxy.py`'s request handler.

**Tech Stack:** Python standard library (`fcntl`, `json`, `threading`), `httpx` in tests; pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-aurora-port-design.md` (approved, `aca36df`), section 3.3. Plan 1 (`docs/superpowers/plans/2026-10-09-aurora-port-1-harness.md`) is complete on `aurora-port`.

**Executor ruling on spec section 10, item 1 (open SV-workstream question):** the SV branch's request accounting lives in `services/recorder.py`, which this port retires. This plan builds the caps fresh on Aurora's recorder. If John later wants SV pieces carried over, they replace `core_caps.py` behind the same interface. Cost if wrong: one module.

## Global Constraints

- **Vendored at a pinned commit:** `recorder/proxy.py` and `recorder/recorder_streams.py` come from `git -C ~/aurora show 42faf41:<path>`. Every change to them is a named hook in a task below.
- **Standard library only on the operator side**, as everywhere in this repository's services. `httpx` appears only in tests.
- **No request header is ever written to the record**, only bodies. Aurora's `test_proxy.py` already holds this, and it must keep passing.
- **A cap refusal is HTTP 429** with an `{"error": {"message": ...}}` body. Aurora's chassis classifies 429 as transient, retries five times with backoff, then exits 44 (`harness/chassis.py` `classify_error`). No chassis change is needed for the spec's "refused with the response the chassis classifies as exit 44".
- **Environment names** are the ones space's recorder already uses, defaults included:
  - `RECORDER_HOURLY_MAX` (core requests per agent per hour, default 2400);
  - `RECORDER_TOKEN_HOURLY_MAX` (core tokens per agent per hour, default 200000000);
  - `RECORDER_TOKEN_GLOBAL_HOURLY_MAX` (fleet tokens per hour, default 2000000000).

  New names:
  - `FLEET_LEDGER_PATH` (unset means no fleet cap, for a single-agent run);
  - `AGENT_SLUG` (the agent this recorder serves);
  - `RECORDER_CORE_RESPONSE_RESERVE` (default 32768).

  John sets the real figures (spec section 10, item 3); these defaults only keep today's behaviour.
- **Test names are full sentences. No skips and no xfails.** Deprecation warnings are errors.
- **Ruff excludes only the vendored files**, `recorder/proxy.py` and `recorder/recorder_streams.py`, not the whole directory. This is the lesson from plan 1's review (deferred minor). New code is linted.

## Review Focus

1. **A response with no usage** (a relay cut short, or a transport failure after forwarding) must keep its core reservation, not settle at zero. Otherwise truncation becomes a way to spend unmetered. (Task 2: `test_a_settle_with_unknown_usage_keeps_the_reservation`)
2. **Ten recorders reserving at once** must not lose a write or double-count. The ledger is read and written under one `flock`. (Task 2: `test_two_processes_reserving_concurrently_both_land_in_the_ledger`)
3. **A missing, empty or corrupt ledger file** must not crash a recorder or refuse every request. A corrupt line is skipped, and the file is rewritten from the valid lines on the next compaction. (Task 2: `test_a_corrupt_ledger_line_is_skipped_not_fatal`)
4. **A core request carrying no `max_tokens`** (Aurora's chassis sends none) must reserve the prompt estimate plus `RECORDER_CORE_RESPONSE_RESERVE`, not the whole hourly allowance. Otherwise ten agents would block each other on reservations alone. (Task 2: `test_a_core_request_without_max_tokens_reserves_the_response_reserve`)
5. **A fleet refusal of a declared stream** must release that stream's own reservation, so the stream's per-hour window is not charged for a request that never went upstream. (Task 3: `test_a_fleet_refusal_of_a_declared_stream_releases_its_stream_reservation`)

---

## File structure

| Path | Responsibility |
|---|---|
| `recorder/proxy.py` | Aurora's recorder, plus the hook in `do_POST` and `main()` (Task 3) |
| `recorder/recorder_streams.py` | Aurora's declared-stream registry. Vendored unchanged. |
| `recorder/core_caps.py` | `FleetLedger` (cross-process hourly token pool), `CoreCaps` (per-agent core ceilings plus the ledger), `caps_from_environment()` |
| `recorder/tests/conftest.py` | puts `recorder/` and `harness/` on `sys.path`, and runs each test from `recorder/` |
| `recorder/tests/test_*.py` | Aurora's recorder tests, plus `test_core_caps.py`, `test_core_caps_in_proxy.py`, `test_recorder_contents.py` |
| `harness/tests/` | unchanged; the reasoning-effort agreement test is re-added in `recorder/tests` |

---

### Task 1: Vendor Aurora's recorder and its tests

**Files:**
- Create: `recorder/proxy.py`, `recorder/recorder_streams.py` (from `42faf41`)
- Create, from Aurora's `tests/` at `42faf41`: `test_proxy.py`, `test_recorder_streams.py`, `test_recorder_console_hostile.py`, `test_unix_listener.py`, `test_upstream_selection.py`, `test_recorder_events.py` (adapted, step 3), `hostile_inputs.py`
- Create: `recorder/tests/conftest.py`, `recorder/tests/test_recorder_contents.py`, `recorder/tests/test_harness_agreement.py`
- Modify: `pyproject.toml` (ruff `exclude`), `CLAUDE.md` (Commands block)

**Interfaces:**
- Produces: the modules `proxy` and `recorder_streams`, importable in `recorder/tests`. Aurora's public names are unchanged, in particular `proxy.ProxyHTTPRequestHandler`, `proxy.UnixHTTPServer`, `recorder_streams.StreamRegistry`, `recorder_streams.estimate_prompt_tokens(body_bytes) -> int`, `recorder_streams.reservation_for(composed_bytes, allowance) -> int`, `recorder_streams.BUDGET_WINDOW` (3600).

- [ ] **Step 1: Copy at the pinned commit**

```bash
mkdir -p recorder/tests
for f in proxy.py recorder_streams.py; do git -C ~/aurora show 42faf41:$f > recorder/$f; done
for t in test_proxy test_recorder_streams test_recorder_console_hostile test_unix_listener \
         test_upstream_selection test_recorder_events hostile_inputs; do
  git -C ~/aurora show 42faf41:tests/$t.py > recorder/tests/$t.py
done
```

- [ ] **Step 2: Write `recorder/tests/conftest.py`**

  Insert `recorder/`, then `harness/`, then `recorder/tests` (for `hostile_inputs`) at the front of `sys.path` at import time, so `recorder/` wins. Add an autouse fixture that `monkeypatch.chdir`s into `recorder/`.

- [ ] **Step 3: Adapt `test_recorder_events.py` to the dropped stage**

  It imports `from stage import data as stage_data`. Delete that import and the one stage-only test, `test_event_rotation_checkpoints_active_bindings_for_the_stage_fold`. In `test_event_timestamp_parses_back_to_an_epoch` and `test_transcript_timestamp_parses_back_to_an_epoch`, replace `stage_data.parse_epoch(x) is not None` with `datetime.datetime.fromisoformat(x.replace("Z", "+00:00"))`, imported at the top. Record the adaptation in the commit message.

- [ ] **Step 4: Write the two contents tests**

  - **`test_recorder_contents.py`:** `test_the_recorder_directory_tracks_only_its_modules_and_tests`. `git ls-files .`, run from `recorder/`, minus `tests/`, equals `{"proxy.py", "recorder_streams.py", "core_caps.py"}`. It fails until Task 2 creates `core_caps.py`; write it now, and expect it to fail in Step 5.
  - **`test_harness_agreement.py`:** `test_the_harness_and_the_recorder_agree_on_reasoning_effort_levels`, which is the test plan 1 held back. It asserts `chassis.REASONING_EFFORT_LEVELS == recorder_streams.REASONING_EFFORT_LEVELS` and that `"minimal"` is in them.

- [ ] **Step 5: Run the vendored suite**

  Run: `python3 -m pytest recorder/tests -p no:cacheprovider`
  Expected: `1 failed, 364 passed`. The 351 measured for the five unchanged files on a scratch copy on 2026-10-09, plus the 12 kept events tests, plus the agreement test, make 364 passing; with the contents test, 365 are collected. The 12 events tests were not run in that probe, because they could not import without the stage, so a different count there is a finding to rule on, not a typo. The one failure is `test_the_recorder_directory_tracks_only_its_modules_and_tests`, on the missing `core_caps.py`.

- [ ] **Step 6: Lint scope and command**

  - Add `"recorder/proxy.py", "recorder/recorder_streams.py"` to `[tool.ruff] exclude`, with a one-line comment: vendored from Aurora at `42faf41`.
  - Add to CLAUDE.md's Commands: `python3 -m pytest recorder/tests -q   # Aurora's recorder and the spend caps: its own process, like harness/tests`.

  Run: `uvx ruff check . --no-cache`. Expected: `All checks passed!`, so the new conftest and tests lint clean.

- [ ] **Step 7: Commit**, with the message saying where each adapted or held-back test went. Leave the contents test failing at this commit; Task 2 makes it pass.

---

### Task 2: `core_caps.py` — the per-agent ceilings and the fleet ledger

**Files:**
- Create: `recorder/core_caps.py`, `recorder/tests/test_core_caps.py`

**Interfaces:**
- Consumes: `recorder_streams.check_budget`, `check_token_budget`, `estimate_prompt_tokens`, `rate_limited_message`, `token_limited_message`, `BUDGET_WINDOW`.
- Produces:
  - `class FleetLedger`, with `__init__(self, path: str, agent: str, allowance: int, clock=time.time)` and these methods:
    - `reserve(self, tokens: int) -> tuple[tuple[int, str] | None, str | None]` returns `(refusal, ticket)`. The refusal is `(429, f"rate limited: at most {allowance} token(s) per hour across the fleet; next available in {s} seconds")`.
    - `settle(self, ticket: str | None, tokens) -> None`
    - `used(self) -> int`
  - `class CoreCaps`, with `__init__(self, request_allowance: int, token_allowance: int, ledger: FleetLedger | None = None, response_reserve: int = 32768, clock=time.time)` and these methods:
    - `admit(self, body: bytes) -> tuple[tuple[int, str] | None, object | None]` returns `(refusal, ticket)`.
    - `settle(self, ticket, tokens) -> None`
  - `def reservation(body: bytes, response_reserve: int) -> int` is the prompt estimate plus the body's own positive integer `max_tokens` if it has one, else plus `response_reserve`.
  - `def caps_from_environment() -> tuple[CoreCaps, FleetLedger | None]` reads the Global Constraints names.

**Ledger format.** `FLEET_LEDGER_PATH` is a JSON-lines file, and `FLEET_LEDGER_PATH + ".lock"` is the `flock` target. Each line is `{"t": <epoch>, "agent": <slug>, "ticket": <slug>:<uuid4 hex>, "tokens": <int>}`. A later line with the same ticket replaces the earlier one: that is a settle. Every `reserve` and `settle` takes `fcntl.LOCK_EX` on the lock file, reads the file, and drops lines outside `BUDGET_WINDOW` and lines that do not parse. `reserve` refuses when in-window use plus the reservation would exceed the allowance; otherwise it appends. When dropped lines exist, the file is rewritten atomically through `common`-style temp-and-`os.replace`. Implement that locally; `services/common.py` is retired in plan 5. The window is rolling, matching the per-agent windows; Aurora's clock-hour shared pool is not used here.

- [ ] **Step 1: Write the failing tests in `recorder/tests/test_core_caps.py`.** The clock is injected; there are no sleeps.
  - `test_a_core_request_without_max_tokens_reserves_the_response_reserve`: `reservation(b'{"messages":[]}', 32768) == estimate_prompt_tokens(body) + 32768`, and a body with `"max_tokens": 100` reserves the estimate plus 100.
  - `test_the_per_agent_request_ceiling_refuses_the_next_request_in_the_hour`: allowance 2. Two admits succeed, the third returns `(429, ...)` with `"request(s) per hour"` in the message. At `clock + 3601` it is admitted again.
  - `test_the_per_agent_token_ceiling_counts_settled_usage`: token allowance 1000. Admit, then settle 1000. The next admit refuses with `"token(s) per hour"`.
  - `test_a_settle_with_unknown_usage_keeps_the_reservation`: `settle(ticket, None)` leaves the reserved amount counted.
  - `test_the_fleet_ledger_refuses_when_the_fleet_has_spent_its_hour`: two `FleetLedger`s on one path, for agents a and b, allowance 1000. a reserves 600; b's reserve of 600 is refused with `"across the fleet"`; after a settles at 100, b's 600 is admitted.
  - `test_core_caps_consult_the_fleet_ledger`: `CoreCaps` with a ledger whose allowance is already spent refuses with `"across the fleet"`, and charges neither per-agent window.
  - `test_two_processes_reserving_concurrently_both_land_in_the_ledger`: two `multiprocessing` processes each reserve 50 times on one path, with a large allowance. The file then holds 100 distinct tickets.
  - `test_a_corrupt_ledger_line_is_skipped_not_fatal`: write `"not json\n"` plus one valid in-window line. `used()` equals the valid line's tokens, and a reserve succeeds.
  - `test_no_ledger_path_means_no_fleet_cap`: `caps_from_environment()` with `FLEET_LEDGER_PATH` unset returns a ledger of `None`, and with it set returns a `FleetLedger` whose agent is `AGENT_SLUG`.

- [ ] **Step 2:** Run `python3 -m pytest recorder/tests/test_core_caps.py -p no:cacheprovider`. Expected: every test fails on `ModuleNotFoundError: No module named 'core_caps'`.

- [ ] **Step 3: Implement `recorder/core_caps.py`** to the interfaces above.
  - `CoreCaps.admit` checks, in order: the per-agent token window, then the fleet ledger reservation, then the per-agent request window. A refusal at a later check releases what the earlier checks held.
  - `CoreCaps` is thread-safe with one `threading.Lock`, because the proxy's server is threading.
  - The module docstring says why the ledger exists: ten recorder processes, one credit pool.

- [ ] **Step 4:** Run `python3 -m pytest recorder/tests -p no:cacheprovider`. Expected: `374 passed`. That is 364, plus the Task 1 contents test now passing, plus 9 here.

- [ ] **Step 5:** Run `uvx ruff check . --no-cache` (expected: clean), then commit: `recorder: per-agent core ceilings and a fleet ledger the recorders share`.

---

### Task 3: The hook in `proxy.py`

**Files:**
- Modify: `recorder/proxy.py`, in `ProxyHTTPRequestHandler.do_POST` and `main()`
- Create: `recorder/tests/test_core_caps_in_proxy.py`

**Interfaces:**
- Consumes: Task 2's `CoreCaps.admit/settle`, `FleetLedger.reserve/settle`, `caps_from_environment()`, and `reservation()`.
- Produces: `server.core_caps` (a `CoreCaps` or `None`) and `server.fleet` (a `FleetLedger` or `None`), set on every `UnixHTTPServer` that `main()` creates, the core socket and each stream socket. Both default to absent, read with `getattr(..., None)`, so Aurora's own tests, which build servers without them, keep passing unchanged.

- [ ] **Step 1: Write the failing tests**, reusing `test_recorder_events.py`'s `transcripts`, `fake_upstream` and `_post` patterns. Copy them, as Aurora's tests do.
  - `test_the_core_socket_refuses_with_429_once_its_hour_is_spent`: a server with `core_caps = CoreCaps(1, 10**9)`. The first POST gets 200 and the second gets 429, with the refusal message in the body. The transcript records both exchanges, and neither contains a header.
  - `test_a_core_refusal_never_reaches_the_upstream`: a counting `forward_open` stays at one call after the refused second request.
  - `test_the_core_settles_the_reported_usage`: the fake upstream reports `total_tokens: 8`, so after one POST the caps' token window holds exactly 8.
  - `test_an_upstream_error_settles_the_core_at_zero`: the fake upstream raises `HTTPError(500)`, so the token window holds 0.
  - `test_a_fleet_refusal_of_a_declared_stream_releases_its_stream_reservation`: a stream server with a registry carrying one declared stream and `fleet` set to a spent `FleetLedger`. The POST gets 429 `"across the fleet"`, and `registry` reports the stream's token use as 0 afterwards.
  - `test_without_caps_the_core_socket_behaves_as_aurora_s`: a server with neither attribute set forwards and records as before. This is the regression guard for the vendored behaviour.

- [ ] **Step 2:** Run `python3 -m pytest recorder/tests/test_core_caps_in_proxy.py -p no:cacheprovider`. Expected: the cap tests fail (200 instead of 429; the windows are empty), and `test_without_caps_the_core_socket_behaves_as_aurora_s` passes. It is a guard, so passing before the change is correct for it.

- [ ] **Step 3: Implement the hook in `do_POST`.**
  - **Core:** for the core stream with `core_caps` set, `refused, ticket = core_caps.admit(req_body)`.
  - **Declared streams:** after a successful `registry.admit`, when `fleet` is set, run `fleet_refused, fleet_ticket = fleet.reserve(reservation(req_body, recorder_streams.stream_token_limit_max()))`. On refusal, call `registry.settle(stream, ticket, 0)` and use the fleet refusal.
  - **Settling:** move the existing `spent` computation out of the streams-only branch, so it is computed once. Then settle each holder that is present: the registry for streams, `core_caps` for core, and `fleet` for a stream's fleet ticket.
  - **In `main()`:** call `caps_from_environment()` once. Attach `core_caps` to the core server and `fleet` to the core server and every stream server. `bind_stream` creates stream servers, so set the attribute there through a module-level `_FLEET` that `main()` assigns.
  - The diff to `proxy.py` stays within `do_POST`, `bind_stream` and `main`.

- [ ] **Step 4:** Run `python3 -m pytest recorder/tests -p no:cacheprovider`. Expected: `380 passed`, which is 374 plus 6. Then run `python3 -m pytest harness/tests -p no:cacheprovider` (expected: `210 passed`, unchanged) and `uvx ruff check . --no-cache` (expected: clean).

- [ ] **Step 5: Commit:** `recorder: hold the core socket and the declared streams to the caps`.

---

## What this plan does not do

- No container, compose service or volume (plan 3). That includes the recorder-only ledger volume and each recorder's per-agent socket and transcript binds.
- No llm-console seed generation, and none of Aurora's `test_llm_console_seed.py`, which reads Aurora's Dockerfile, `prepare_host.sh` and entrypoint (plan 3).
- No removal of `services/recorder.py` (plan 5).
- No cap figures beyond today's defaults (John, spec section 10, item 3).
