# Chassis Lifespan Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a run honest numbers about its own context and two deliberate levers over it — compact to stretch, reset to start over — without the harness ever deciding when to pull either. And keep the lineage alive long enough for the choice to matter: a conversation the upstream will accept, a checkpoint that stays a size and can be recovered, a supervisor that can see a loop, and a record a person can read.

**Architecture:** Everything the upstream receives becomes subject to one budget, so the window a run is told about is the window it actually has. On top of that honest accounting sit three primitives on `RunContext`: `compact()` replaces the middle of a conversation with a summary, `reset()` ends the conversation while keeping a note, and `status()` reports rate and composition rather than only position. Underneath them, the survival layer the live lineages under `volumes/home/` turned out to need: a conversation is repaired when it is loaded rather than trusted, pruned when it is written rather than kept whole, opened on the agent's own diary rather than on the brief alone, and left as a fallback copy behind every checkpoint. The chassis supplies mechanism; the duty and the fleet supply policy.

**Tech Stack:** Python 3.11+, standard library only on the operator side (`services/`). `pytest` for the suite. No new dependencies.

**Spec:** Filigree epic `space_chassis-c8e27e645c` ("Long-life runs: an agent's control over its own lifespan"). This plan implements `space_chassis-8da4399e69`, `space_chassis-29d9c64d2d`, `space_chassis-3c98f068b5`, `space_chassis-a5c2a27876`, `space_chassis-bbe02a114d`, `space_chassis-f83364fe22`, and the tool half of `space_chassis-3622348dc9`. Rationale for the existing design is `docs/design.md`.

### Revision 2 — what changed, and why

The first revision was reviewed by implementing Tasks 1–3 against a scratch copy and
by reading the three live lineages in `volumes/home/`. Two results drove this revision.

**Four defects in the first revision, fixed here:**

1. Task 1's `test_a_saturated_recap_is_still_sent_exactly_once` could not pass against
   Task 1's own `prepared_view`: the dedup compared the clipped copy on the way out
   against the whole copy stored in the conversation, so a saturated recap shipped
   twice. `prepared_view` now *drops* stored recap messages instead of comparing for
   equality (Task 1 Step 4).
2. Task 1 changed `fold_recap_if_needed` to call `tail_room()`, which reads
   `self.tools` and `self.output_reserve` — attributes the pre-existing test
   `test_evicted_messages_are_recorded_before_they_are_lost` never sets, because it
   builds its chassis with `object.__new__`. The test's fixture is updated in Task 1
   Step 1.
3. Task 3 changed `containers/agent.env`, which the runtime does not read:
   `docker-compose.yml` sets `CONTEXT_WINDOW_TOKENS` per agent from the operator's
   `.env`, and `containers/entrypoint.sh` exports only six variables from
   `/etc/agent.env`. The window therefore stayed at the ceiling while the new test
   went green. Task 3 now changes the three files that actually decide the value and
   asserts against all of them.
4. Task 6's `status()` calls `pinned_indices()`, which Task 5 defines; its Interfaces
   list now says so, and `previous_run_ended` is carried in memory instead of being
   read back from a `run.json` that the next turn's checkpoint overwrites.

**The endurance work the live data demanded (Tasks 8–17).** The three lineages in
`volumes/home/` (68–79 stored recap copies each, 3.8–4.9 MB conversations, 0.9–1.2 M
estimated tokens against a 200k window) got there through a loop this plan otherwise
leaves running: the model calls the `handoff` *tool*, `turn_once` raises `SystemExit`
before appending any tool result, and the exit-path checkpoint stores an assistant
message whose `tool_calls` have no results — 43, 51 and 42 of them, one per run, the
only orphaned calls in those files. Exit 42 is exempt from the supervisor's flap
guard, so 66–77 runs at 0–3 second intervals were never treated as a loop; each
resume then inserted another recap copy at index 0, which inverted the conversation's
order, and the window — which keeps the tail of the list — began preserving the
*oldest* material and dropping the recent middle. Nothing in the tree repairs a
conversation like that, and `give_up` has no memory across the supervisor restarts
the entrypoint performs.

Tasks 8–17 are those repairs, in order of endurance gained per line. They bring
`space_chassis-835d551619`, `space_chassis-80382730d2`, `space_chassis-420d18b7fa`
and `space_chassis-aa9ac4ec84` into scope; the first revision had listed them as
independent.

**Tickets.** All thirteen are filed as children of `space_chassis-c8e27e645c` and every
commit below carries its id. `835d551619` (a rung that clears a poisoned conversation),
`80382730d2` (run budgets), `420d18b7fa` (the inactivity watch) and `aa9ac4ec84` (the
`resume()` contract) already existed and are brought into scope by Tasks 8–15; the other
nine were filed for this revision and are listed in Task 0.

**Checked before delivery.** Every snippet in this revision was transcribed into a
scratch copy and run, the way a worker would, and the plan's own tests were run
against it. What that caught, and what is fixed above:

- Task 8's `test_resume_says_what_it_repaired` asserted that a stale recap is dropped
  while the fixture left no recap file — and with no file, `keep_recap` is true and the
  copy is deliberately kept. The fixture now writes one.
- Task 9's `save_conversation` renamed the checkpoint away before writing the
  replacement, so a failed write left nothing readable and the next run reported a
  fresh lineage with a full copy sitting beside it. It now stages the new checkpoint
  first and installs it last, and there is a test for the failure.
- Task 9's `prune()` could leave `recap_folded` past the end of a shorter list, where
  every later fold slices an empty range. It now clamps to the boundary it already
  computed, and a test pins it.
- Task 11's rate guard was placed after the `EXIT_HANDOFF` early return — which is
  above the `EXIT_ENVIRONMENT` branch it was told to follow — so it could never see the
  one loop it exists to catch. Task 11 Step 5 now reorders the two exit tests and puts
  the guard between them.
- Task 11's `save_ladder` used `write_json_atomic`, which `services/supervisor.py`
  does not import. Step 3 now names both imports it needs.
- Task 13's `test_a_run_can_rewrite_its_own_recap` looked for "rewrite" in a string
  that says "recap rewritten". Assertions that only ever pass are worse than none.
- Task 3 and Task 11 predicted the wrong failure text for their red steps, and Task 3's
  `grep -c` counts the anchor line as well as the ten agents. Both are corrected.

---

### Task 0: The tickets this plan closes (filed)

**Files:** none — this is tracker work, and the only part of the plan that is not TDD.

**Why it is here:** every commit below carries a `Refs` line, and a `Refs` line that
names a ticket nobody filed is how work goes missing. All of these are now children of
`space_chassis-c8e27e645c`; the four that predate this revision are marked *existing*.

| Ticket | Priority | Type | Closes with |
|---|---|---|---|
| `f976098d48` — `handoff` leaves an orphaned tool_call that poisons the next run | P1 | bug | Task 8 |
| `8c5e97f029` — The checkpoint grows without bound and reads as absent past its limit | P1 | bug | Task 9 |
| `2b52aef053` — `resume()` inserts at index 0, so the window keeps the oldest material | P1 | bug | Task 10 |
| `3cb643af8e` — Nothing counts the run rate: exit 42 is exempt from the flap guard | P1 | bug | Task 11 |
| `d96d548f41` — The supervisor forgets the ladder across restarts and never escalates | P2 | bug | Task 11 |
| `1dca8e8841` — The recap is append-only, undeduplicated, and cannot be rewritten | P2 | feature | Task 13 |
| `60a9b11711` — A fresh conversation opens on the brief alone, not on the agent's memory | P2 | feature | Task 14 |
| `13599e63b4` — Lineage-level telemetry: runs/hour, exits, tier, spend, cache hits | P3 | task | Task 16 |
| `639443e993` — The JSONL records grow without bound; readers are bounded, files are not | P4 | task | Task 17 |
| `835d551619` — No ladder rung clears a poisoned conversation on the fault path *(existing)* | P1 | bug | Tasks 8–11 |
| `420d18b7fa` — Supervisor inactivity watch (24h) outlasts a several-hour run *(existing)* | P3 | task | Task 12 |
| `80382730d2` — `RUN_MAX_SECONDS` unset: nothing bounds a run by design *(existing)* | P3 | task | Task 15 |
| `aa9ac4ec84` — `resume()` contract diverges from its comments; `previous_run_ended` is always null *(existing)* | P2 | bug | Tasks 6, 10 |

Each carries `side:operator` and `topic:endurance`. Every one of them is about how long
a lineage can run and how honestly it can see itself — none of them is about the work
the lineage chooses to do, and each description says so.

---

## Global Constraints

- **The harness stays task-agnostic.** Mechanisms only. Nothing added here may decide *when* to compact or reset, name a mission concept, or suggest a strategy. Docstrings describe what a lever does and what it costs, never when to use it.
- **Nothing in this plan is for the work.** Everything here is a condition for running for a long time: honest numbers about a run's own context, memory that stays a size and in order, a ladder that can see a loop, a record a person can read. No constant, threshold or tool added here may be tuned to a mission, a task, or a rhythm of work — the fleet builds the tooling for the work itself, and it has to do that before it starts. A change that only helps one particular job is on the far side of that line, not in this plan. Where a number has to be chosen anyway (`RUN_MAX_TURNS`, the run rate, the inactivity watch), it is chosen against the properties of the runtime — the recorder's timeout, the cost of resuming, the size of a checkpoint — and each of those is justified where it lives.
- **Operator-side services are standard library only.** `services/` may not gain a dependency. The `httpx`/`openai` imports inside `Chassis.client()` are the existing exception and stay inside that method.
- **Imports:** services do `sys.path.insert(0, SERVICES_DIR)` then `from common import ...`. Tests write `from common import ...`, `import chassis` — never `from services.common import ...`.
- **`filterwarnings = ["error::DeprecationWarning"]`** in `pyproject.toml`: any deprecation warning fails the suite.
- **Test names are full sentences stating the property under test.** Reasoning lives in module docstrings and comments; `E501` is off, so long explanatory lines are fine.
- **Every published file goes through `common.write_json_atomic`**; every read of an agent-writable file is bounded by `MAX_READ_BYTES`.
- **The exit-code contract is shared vocabulary** with `services/supervisor.py`: 0 clean, 42 handoff, 43 duty fault, 44 environment. This plan adds no new exit code.
- **Two copies of `chassis.py` exist in a container.** Do not touch `_load_runtime()` in `tasks/duty.py` or "simplify" it into an import.
- **Run the suite with** `python3 -m pytest -q` from the repo root. It needs no Docker.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `services/chassis.py` | The runtime: framing, turns, the window, the carry | Modify — budgeting, telemetry, reset, compaction, instruments, conversation repair, pruning, opening |
| `services/supervisor.py` | The ladder and the watch | Modify — the run-rate guard, a ladder that survives a restart, an honest progress signal |
| `services/common.py` | Shared file helpers | Modify — bounded rotation for the append-only records |
| `services/fleet_monitor.py` | The fleet's own rolling record | Modify — rotate `fleet.jsonl` before appending |
| `containers/agent.env` | The world's constants | Modify — window headroom, output reserve, declared model ceiling, run budgets |
| `.env.example` | The operator's copy, which compose reads | Modify — the same values, where they actually decide the container's environment |
| `docker-compose.yml` | The env each agent is given | Modify — window, ceiling, reserve, budgets, inactivity |
| `tasks/duty.py` | The fleet seed: the tools an ordinary run gets | Modify — bounded tool output, `compact`, `reset` and `rewrite_recap` tools |
| `scripts/status.py` | What the operator reads | Modify — a lineage block: runs/hour, exits, tier, spend, cache |
| `tests/test_chassis.py` | Runtime properties | Modify — one section per task |
| `tests/test_services.py` | Cross-service constants and the supervisor | Modify — the shipped-window relationship, the loop guards, rotation |
| `tests/test_observer.py` | The read-only operator surfaces | Modify — the lineage block |

### Out of scope, deliberately

- `space_chassis-a408dafc55` (the brief never mentions the window) — depends on this plan landing first, so the brief can describe levers that exist.
- `space_chassis-38a9b8f600` (no in-process backoff), `-ede8988561` (the repeat detector only catches verbatim replies), `-deae4f4801` (`reasoning_content` is resent every turn) — independent, small, and not on this plan's critical path.
- `space_chassis-835d551619`, `-80382730d2`, `-420d18b7fa` and `-aa9ac4ec84` were out of scope in revision 1 and are **in** scope here: the live data in `volumes/home/` showed all four are on the path that ends a lineage, not beside it.

---

### Task 1: One budget for everything that ships

**Files:**
- Modify: `services/chassis.py` (constants near line 82; `prepared_view` at 978; `Chassis.__init__` at 377; `Chassis.request` at 474; `Chassis.fold_recap_if_needed` at 589)
- Test: `tests/test_chassis.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `chassis.estimate_text_tokens(text: str) -> int`; `chassis.clip_recap(recap: str, budget_tokens: int) -> str`; `chassis.tail_budget(budget_tokens: int, recap_tokens: int, overhead_tokens: int, output_reserve: int) -> int`; `prepared_view(messages, budget_tokens, chunk_tokens, carried, overhead_tokens: int = 0, output_reserve: int = 0)`; `Chassis.overhead_tokens() -> int`; `Chassis.tail_room() -> int`; `Chassis.output_reserve: int`.

**Why:** `selection()` budgets pinned messages plus the moving tail. `prepared_view()` then prepends the recap *after* that arithmetic, tool schemas ride outside it in `kwargs["tools"]`, and no room is reserved for the completion. With `CONTEXT_WINDOW_TOKENS` set equal to a model's real limit, a run that fills its 96 KB recap crosses the line deterministically.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_chassis.py`, after the existing window section:

```python
def test_everything_that_ships_is_counted_against_the_window(tmp_path):
    """The window a run is told about must be the window it actually has.

    The recap, the tool schemas and the room the completion needs are all sent
    with the messages. A budget that counts only the messages is not a budget.
    """
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    for index in range(400):
        carried.append_recap([f"- [assistant] dropped turn {index} " + "r" * 300])
    messages = [message("system", "sys"), message("user", "go")] + [
        message("assistant", "a" * 4000) for _ in range(200)
    ]
    budget = 20_000
    sent = chassis.prepared_view(
        messages,
        budget_tokens=budget,
        chunk_tokens=1_000,
        carried=carried,
        overhead_tokens=2_000,
        output_reserve=4_000,
    )
    shipped = chassis.estimate_tokens(sent) + 2_000 + 4_000
    assert shipped <= budget, f"{shipped} tokens went out against a {budget} budget"


def test_the_recap_cannot_claim_more_than_its_share_of_the_window(tmp_path):
    """A recap that grows without bound becomes a second window, then a crash."""
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    for index in range(400):
        carried.append_recap([f"- [assistant] dropped turn {index} " + "r" * 300])
    budget = 20_000
    sent = chassis.prepared_view(
        messages=[message("user", "go")],
        budget_tokens=budget,
        chunk_tokens=1_000,
        carried=carried,
    )
    recap_message = next(m for m in sent if "fallen out of the context window" in str(m["content"]))
    allowance = int(budget * chassis.RECAP_WINDOW_FRACTION)
    assert chassis.estimate_text_tokens(str(recap_message["content"])) <= allowance + 100


def test_a_saturated_recap_is_still_sent_exactly_once(tmp_path):
    """The clipped copy and a stored copy are not equal, so dedup by content misses.

    A recap over its allowance is clipped on the way out. Anything that also
    stores the whole recap in the conversation therefore ships both: one paid for
    out of the budget, one pinned and never evicted.
    """
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    for index in range(400):
        carried.append_recap([f"- [assistant] dropped turn {index} " + "r" * 300])
    stored = {
        "role": "system",
        "content": (
            "Recap of conversation that has fallen out of the context window. "
            "It is a lossy record, kept because the window is not a memory:\n\n"
            + carried.recap()
        ),
    }
    sent = chassis.prepared_view(
        [stored, message("user", "go")], budget_tokens=20_000, chunk_tokens=1_000, carried=carried
    )
    recaps = [m for m in sent if "fallen out of the context window" in str(m.get("content", ""))]
    assert len(recaps) == 1, f"the recap went out {len(recaps)} times"


def test_a_clipped_recap_keeps_the_newest_material(tmp_path):
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    for index in range(400):
        carried.append_recap([f"- [assistant] event {index} " + "r" * 300])
    clipped = chassis.clip_recap(carried.recap(), budget_tokens=500)
    assert "event 399" in clipped
    assert "event 0 " not in clipped


def test_a_stored_recap_survives_when_the_recap_file_is_gone(tmp_path):
    """Dropping stale copies must not drop the only copy.

    A conversation written by an older runtime can hold a recap the file no
    longer does. That message is the whole memory of what fell out of the
    window, so exactly one of them is kept.
    """
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    stored = {
        "role": "system",
        "content": chassis.RECAP_PREFIX + "- [assistant] the only record of hour one\n",
    }
    sent = chassis.prepared_view(
        [stored, message("user", "go")], budget_tokens=20_000, chunk_tokens=1_000, carried=carried
    )
    recaps = [m for m in sent if "the only record of hour one" in str(m.get("content", ""))]
    assert len(recaps) == 1, f"the only stored memory went out {len(recaps)} times"
```

**Also update the pre-existing fold test's fixture.** `test_evicted_messages_are_recorded_before_they_are_lost`
builds its chassis with `object.__new__`, so it has no `tools` and no `output_reserve`
— and Step 6 makes `fold_recap_if_needed` read both through `tail_room()`. Add these
two lines to that test, beside its `instance.recap_folded = 0`:

```python
    instance.output_reserve = 0
    instance.tools = chassis.ToolRegistry()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_chassis.py -q -k "counted_against or share_of_the_window or saturated_recap or clipped_recap or stored_recap"`
Expected: FAIL — `AttributeError: module 'chassis' has no attribute 'RECAP_WINDOW_FRACTION'`.

- [ ] **Step 3: Add the constants and the helpers**

In `services/chassis.py`, beside `RECAP_MAX_BYTES`:

```python
# The recap is a window too, and it is not allowed to eat the one it reports on.
RECAP_WINDOW_FRACTION = 0.15
# Room held back for the completion. The window is what goes out *and* what comes
# back: a budget that spends all of it on the prompt has nowhere to put the reply.
DEFAULT_OUTPUT_RESERVE_TOKENS = 8_000
# However tight things get, a request with no conversation in it is not a request.
MIN_TAIL_TOKENS = 1_000
# The framing a recap is sent under. It is a constant because three places have to
# agree on it: the send view that writes it, the fold that must not duplicate it,
# and the repair that has to recognise a stale copy in a conversation written by an
# earlier version of this runtime.
RECAP_PREFIX = (
    "Recap of conversation that has fallen out of the context window. "
    "It is a lossy record, kept because the window is not a memory:\n\n"
)


def is_stored_recap(message: dict) -> bool:
    """Whether a message is a recap a previous runtime stored in the conversation.

    Recaps are pinned from disk on every request now, but conversations written
    before that was true hold one copy per resume: 68, 79 and 68 of them in the
    three lineages under `volumes/home/`. They are system messages, so the window
    pins them forever -- a run cannot evict its way out of them.
    """
    return message.get("role") == "system" and str(message.get("content", "")).startswith(
        RECAP_PREFIX
    )
```

Beside `estimate_tokens`:

```python
def estimate_text_tokens(text: str) -> int:
    """The same estimate as `estimate_tokens`, for text that is not a message list."""
    return len(text) // 4


def clip_recap(recap: str, budget_tokens: int) -> str:
    """The newest `budget_tokens` worth of recap, cut on a line boundary."""
    if budget_tokens <= 0:
        return ""
    limit = budget_tokens * 4
    if len(recap) <= limit:
        return recap
    return recap[-limit:].split("\n", 1)[-1]


def tail_budget(
    budget_tokens: int, recap_tokens: int, overhead_tokens: int, output_reserve: int
) -> int:
    """What is left for the conversation once everything else that ships is paid for.

    The recap, the tool schemas and the completion's room all come out of the
    same window. This is the one place that subtracts them, so the send view and
    the recap fold agree about where the edge is.
    """
    if budget_tokens <= 0:
        return budget_tokens
    return max(MIN_TAIL_TOKENS, budget_tokens - recap_tokens - overhead_tokens - output_reserve)
```

- [ ] **Step 4: Spend the budget in `prepared_view`**

Replace the body of `prepared_view`:

```python
def prepared_view(
    messages: list[dict],
    budget_tokens: int,
    chunk_tokens: int | None,
    carried: Carried,
    overhead_tokens: int = 0,
    output_reserve: int = 0,
) -> list[dict]:
    """The messages to send: the window, with the recap pinned in front.

    The recap is inserted here rather than stored in the conversation, so it is
    always current, never duplicated, and never itself evicted by the window it
    is reporting on. It is also *paid for* here: it takes its share out of the
    same budget the tail is drawn against, because both go out in one request.
    """
    recap = clip_recap(carried.recap(), int(budget_tokens * RECAP_WINDOW_FRACTION))
    room = tail_budget(budget_tokens, estimate_text_tokens(recap), overhead_tokens, output_reserve)
    indices, _ = selection(messages, room, chunk_tokens)
    kept = [messages[index] for index in indices]
    # Anything the conversation stored for itself is dropped before the current
    # copy is pinned in front. Comparing for equality is not enough: the stored
    # copy is whole and the sent one is clipped, so a recap over its allowance
    # would ship twice -- one paid for out of the budget, one pinned and never
    # evicted. This is the difference between a fleet that runs and one that does
    # not: without it, three live lineages send ~1.0M tokens into a 200k window.
    stored = [message for message in kept if is_stored_recap(message)]
    kept = [message for message in kept if not is_stored_recap(message)]
    if not recap:
        # No recap on disk: the newest stored copy is the only memory there is.
        return [stored[-1], *kept] if stored else kept
    framed = {"role": "system", "content": RECAP_PREFIX + recap}
    return [framed, *kept]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_chassis.py -q`
Expected: PASS, including the pre-existing window and recap tests and
`test_evicted_messages_are_recorded_before_they_are_lost`, whose fixture Step 1
extends.

- [ ] **Step 6: Teach the chassis its own overhead**

In `Chassis.__init__`, beside `self.eviction_chunk`:

```python
        self.output_reserve = env_int("OUTPUT_RESERVE_TOKENS", DEFAULT_OUTPUT_RESERVE_TOKENS)
```

Then pin the eviction chunk, replacing the existing `self.eviction_chunk` line in the same method:

```python
        # Derived from the *window*, never from the room left over. `selection`
        # falls back to `budget // 8` when this is None, and the budget it is now
        # handed shrinks as the recap grows -- so leaving it None would walk the
        # chunk boundary through the whole growth phase and break exactly the
        # prefix stability `_advance_to_chunk` exists to hold still.
        self.eviction_chunk = env_optional_int("CONTEXT_WINDOW_EVICTION_TOKENS") or max(
            1, self.context_window // 8
        )
```

Add two methods beside `fold_recap_if_needed`:

```python
def overhead_tokens(self) -> int:
    """What goes out with the messages but is not a message: the tool schemas."""
    if not self.tools.schemas:
        return 0
    return len(json.dumps(self.tools.schemas, ensure_ascii=False)) // 4


def tail_room(self) -> int:
    """The budget the moving tail is actually drawn against."""
    recap = clip_recap(self.carried.recap(), int(self.context_window * RECAP_WINDOW_FRACTION))
    return tail_budget(
        self.context_window,
        estimate_text_tokens(recap),
        self.overhead_tokens(),
        self.output_reserve,
    )
```

In `Chassis.request`, replace the `send = ...` line:

```python
        send = prepared_view(
            self.messages,
            self.context_window,
            self.eviction_chunk,
            self.carried,
            self.overhead_tokens(),
            self.output_reserve,
        )
```

In `Chassis.fold_recap_if_needed`, replace the `window_bounds(...)` call so the fold boundary matches the send view:

```python
        kept_start, _ = window_bounds(self.messages, self.tail_room(), self.eviction_chunk)
```

- [ ] **Step 7: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add services/chassis.py tests/test_chassis.py
git commit -m "chassis: count the recap, the schemas and the reply against one window

The recap was prepended after the budget was spent, the tool schemas rode
outside it, and nothing was held back for the completion. A run that filled
its recap crossed a 200k limit deterministically, took a 400, and exit 43
sent it up a ladder that never clears a conversation.

The send view also drops the recap copies older runtimes stored in the
conversation itself. Comparing the clipped copy against a stored whole one
never matched, so a saturated recap shipped twice -- and the three lineages
under volumes/home/ hold 68, 79 and 68 such copies, which is why they send
~1.0M estimated tokens into a 200k window.

Refs space_chassis-8da4399e69

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 2: Record what the upstream says about the cache and the estimate

**Files:**
- Modify: `services/chassis.py` (`Chassis.__init__` at 377; `Chassis.capture_usage` at 489; `Chassis.request` at 474; `Chassis.turn_once` at 498)
- Test: `tests/test_chassis.py`

**Interfaces:**
- Consumes: `Chassis.overhead_tokens()` from Task 1.
- Produces: `chassis.cached_prompt_tokens(usage) -> int`; `Chassis.usage_totals["cached_prompt_tokens"]`; `Chassis.last_estimate: int`; `Chassis.last_prompt_tokens: int`.

**Why:** `capture_usage` keeps three integers and drops `prompt_tokens_details.cached_tokens` and DeepSeek's `prompt_cache_hit_tokens`. `_advance_to_chunk` exists entirely to hold a cacheable prefix still, and nothing reports whether it works. The same record settles whether `estimate_tokens` is accurate, which is what Task 3's headroom figure should be set from.

- [ ] **Step 1: Write the failing tests**

```python
class _Details:
    def __init__(self, cached_tokens):
        self.cached_tokens = cached_tokens


class _Usage:
    def __init__(self, prompt=100, completion=10, total=110, cached=None, native=None):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = total
        if cached is not None:
            self.prompt_tokens_details = _Details(cached)
        if native is not None:
            self.prompt_cache_hit_tokens = native


class _Response:
    def __init__(self, usage):
        self.usage = usage


def test_cache_hits_are_read_from_whichever_field_the_upstream_uses():
    """Providers disagree about where to put it, and a dropped field is a blind spot.

    The whole justification for holding the window's edge still is that a stable
    prefix gets cached. Nothing could say whether it did.
    """
    assert chassis.cached_prompt_tokens(_Usage(cached=64)) == 64
    assert chassis.cached_prompt_tokens(_Usage(native=32)) == 32
    assert chassis.cached_prompt_tokens(_Usage()) == 0


def test_usage_totals_accumulate_cache_hits():
    instance = object.__new__(chassis.Chassis)
    instance.usage_totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_prompt_tokens": 0,
    }
    instance.last_prompt_tokens = 0
    chassis.Chassis.capture_usage(instance, _Response(_Usage(prompt=100, cached=80)))
    chassis.Chassis.capture_usage(instance, _Response(_Usage(prompt=100, cached=90)))
    assert instance.usage_totals["cached_prompt_tokens"] == 170
    assert instance.usage_totals["prompt_tokens"] == 200
    assert instance.last_prompt_tokens == 100
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_chassis.py -q -k "cache_hits or usage_totals_accumulate"`
Expected: FAIL — `AttributeError: module 'chassis' has no attribute 'cached_prompt_tokens'`.

- [ ] **Step 3: Implement**

Beside `estimate_text_tokens` in `services/chassis.py`:

```python
def cached_prompt_tokens(usage) -> int:
    """How much of the prompt the upstream served from its own cache.

    Providers disagree about where to put this. OpenAI-compatible upstreams nest
    it under `prompt_tokens_details.cached_tokens`; DeepSeek reports
    `prompt_cache_hit_tokens` at the top level. Reading both is cheaper than
    caring which one is in front of us.
    """
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        value = getattr(details, "cached_tokens", None)
        if isinstance(value, int):
            return value
        if isinstance(details, dict) and isinstance(details.get("cached_tokens"), int):
            return details["cached_tokens"]
    native = getattr(usage, "prompt_cache_hit_tokens", None)
    return native if isinstance(native, int) else 0
```

In `Chassis.__init__`, replace the `usage_totals` line and add two counters:

```python
        self.usage_totals = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_prompt_tokens": 0,
        }
        self.last_estimate = 0
        self.last_prompt_tokens = 0
```

Replace `Chassis.capture_usage`:

```python
    def capture_usage(self, response) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = getattr(usage, key, None)
            if isinstance(value, int):
                self.usage_totals[key] += value
        prompt = getattr(usage, "prompt_tokens", None)
        if isinstance(prompt, int):
            self.last_prompt_tokens = prompt
        self.usage_totals["cached_prompt_tokens"] += cached_prompt_tokens(usage)
```

In `Chassis.request`, after `send = prepared_view(...)`:

```python
        self.last_estimate = estimate_tokens(send) + self.overhead_tokens()
```

In `Chassis.turn_once`, replace the `self.record("turn", ...)` line:

```python
        self.record(
            "turn",
            tools=len(tool_calls),
            usage=dict(self.usage_totals),
            estimated_prompt_tokens=self.last_estimate,
            actual_prompt_tokens=self.last_prompt_tokens,
            cached_prompt_tokens=cached_prompt_tokens(getattr(response, "usage", None)),
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_chassis.py -q`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS. The end-to-end tests exercise `capture_usage` against the stub, which reports no cache fields; `cached_prompt_tokens` must return 0 rather than raise.

- [ ] **Step 6: Commit**

```bash
git add services/chassis.py tests/test_chassis.py
git commit -m "chassis: record cache hits and estimate accuracy per turn

The prefix-stability work in _advance_to_chunk had no signal saying whether
it paid off, and estimate_tokens had no signal saying whether it was honest.
Both are one field on a record we already write.

Refs space_chassis-29d9c64d2d

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 3: Ship a window with headroom, and say what it is headroom beneath

**Files:**
- Modify: `containers/agent.env` (the conversation-window section)
- Modify: `.env.example` (the operator's defaults, which `docker-compose.yml` reads)
- Modify: `docker-compose.yml` (the `x-env` anchor and the ten per-agent window lines)
- Test: `tests/test_services.py`

**Interfaces:**
- Consumes: `chassis.RECAP_WINDOW_FRACTION`, `chassis.DEFAULT_OUTPUT_RESERVE_TOKENS` from Task 1.
- Produces: `MODEL_CONTEXT_CEILING_TOKENS`, `OUTPUT_RESERVE_TOKENS`, and a 160000-token `CONTEXT_WINDOW_TOKENS` in all three files.

**Why:** `CONTEXT_WINDOW_TOKENS=200000` is exactly the real limit of a 200k model, so the eviction threshold and the hard limit are the same number. The window is self-imposed; setting it below the ceiling costs only slightly earlier eviction and buys the margin that keeps a long run off the 4xx path. Declaring the ceiling makes the relationship machine-checkable instead of a matter of memory.

**Why all three files, and not `containers/agent.env` alone:** `agent.env` is documentation, not configuration. It is copied to `/etc/agent.env`; `containers/entrypoint.sh` sources it and exports exactly six variables — `WORK_DIR`, `SEED_DIR`, `AGENT_HOME`, `DIARY_DIR`, `BRIEF_DIR`, `SERVICES_DIR` — so nothing else in it reaches a process. The value a container's chassis actually reads is set by `docker-compose.yml`'s `x-env` anchor from the operator's `.env`, whose defaults are `.env.example`. A revision that changed only `agent.env` would leave every agent at the ceiling while its own test went green; the test below therefore reads all three.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_services.py`:

```python
def test_the_shipped_window_leaves_room_beneath_the_models_real_ceiling():
    """The window is an eviction threshold; the ceiling is a hard error.

    Setting them equal means the recap, the schemas and the reply have nowhere
    to come from but over the edge. This reads every place the value is decided,
    not only the file that documents it: a window set correctly in agent.env and
    left at the ceiling in docker-compose.yml is still a window at the ceiling.
    """
    import re

    def shipped(name: str) -> dict:
        env = {}
        for line in (PROJECT / name).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
        return env

    agent_env = shipped("containers/agent.env")
    operator_env = shipped(".env.example")
    for key in ("CONTEXT_WINDOW_TOKENS", "MODEL_CONTEXT_CEILING_TOKENS", "OUTPUT_RESERVE_TOKENS"):
        assert key in agent_env, f"{key} is not in containers/agent.env"
        assert key in operator_env, f"{key} is not in .env.example"
        assert agent_env[key] == operator_env[key], (
            f"{key} is {agent_env[key]} in the container copy and {operator_env[key]} "
            "in the operator's; compose reads the second and ignores the first"
        )

    ceiling = int(agent_env["MODEL_CONTEXT_CEILING_TOKENS"])
    window = int(agent_env["CONTEXT_WINDOW_TOKENS"])
    reserve = int(agent_env["OUTPUT_RESERVE_TOKENS"])

    # The window is the whole of what ships: the recap and the reply reserve come
    # *out* of it, not on top of it. What it must leave room for is the estimator
    # being wrong, since it counts serialised characters over four and the real
    # tokeniser does not. A fifth is a deliberately coarse margin until the
    # estimate-vs-actual telemetry says what it should be.
    assert window <= ceiling * 0.8, (
        f"the window ({window}) leaves no margin for estimator error beneath the "
        f"declared ceiling ({ceiling})"
    )
    assert reserve < window, "the reply reserve cannot be the whole window"

    # And the defaults compose interpolates when the operator has set nothing,
    # which are the numbers a container without a .env actually gets.
    compose = (PROJECT / "docker-compose.yml").read_text(encoding="utf-8")
    windows = {
        int(value)
        for value in re.findall(
            r"CONTEXT_WINDOW_TOKENS: \$\{HOST\d+_CONTEXT_WINDOW_TOKENS:-\$\{CONTEXT_WINDOW_TOKENS:-(\d+)\}\}",
            compose,
        )
    }
    assert windows == {window}, f"compose ships defaults {windows or '{}'}, not {window}"
    assert f"OUTPUT_RESERVE_TOKENS: ${{OUTPUT_RESERVE_TOKENS:-{reserve}}}" in compose
    assert f"MODEL_CONTEXT_CEILING_TOKENS: ${{MODEL_CONTEXT_CEILING_TOKENS:-{ceiling}}}" in compose
```

`PROJECT` is already defined at the top of `tests/test_services.py`; if it is not, add `PROJECT = Path(__file__).resolve().parent.parent`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_services.py -q -k "shipped_window"`
Expected: FAIL — `AssertionError: MODEL_CONTEXT_CEILING_TOKENS is not in containers/agent.env`. The test checks membership before it parses, so the failure is the assertion rather than a `KeyError`.

- [ ] **Step 3: Rewrite the window section of `containers/agent.env`**

Replace the `--- the conversation window ---` block:

```sh
# --- the conversation window ----------------------------------------------
# Messages older than the window stop being sent, without notice, unless the
# duty makes its own arrangement. The chassis keeps a recap of what was
# dropped and keeps sending that.
#
# Three numbers, and the relationship between them is the point:
#
#   MODEL_CONTEXT_CEILING_TOKENS  what the upstream will actually refuse past.
#                                 A hard error. Not ours to choose -- it is a
#                                 fact about LLM_MODEL, recorded here so the
#                                 other two can be checked against it.
#   CONTEXT_WINDOW_TOKENS         where the chassis starts evicting. Ours to
#                                 choose, and deliberately *below* the ceiling:
#                                 the recap and the reply are drawn from the
#                                 same budget, and the token estimate is an
#                                 estimate. Crossing the ceiling costs a 4xx,
#                                 which the runtime reads as the run's own
#                                 fault; evicting slightly early costs nothing.
#   OUTPUT_RESERVE_TOKENS         the part of the window held back for the reply.
#
# tests/test_services.py pins window <= 80% of ceiling. The margin is estimator
# error, and it is coarse on purpose until the telemetry says what it should be.
MODEL_CONTEXT_CEILING_TOKENS=200000
CONTEXT_WINDOW_TOKENS=160000
OUTPUT_RESERVE_TOKENS=8000
CONTEXT_WINDOW_EVICTION_TOKENS=
# A run of the duty ends at either of these and the supervisor starts another.
# Unset means a run ends only when the duty ends it, or when it dies.
RUN_MAX_TURNS=
RUN_MAX_SECONDS=
```

- [ ] **Step 3b: Put the same three numbers in the operator's defaults**

Replace the `--- the conversation window ---` block of `.env.example`, which is what
`docker-compose.yml` interpolates when `.env` has nothing to say:

```sh
# --- the conversation window ----------------------------------------------
# The window a run sends. What falls out of it is written to a recap that keeps
# being sent, so a long run does not simply forget. Bigger windows cost more
# per turn; the fleet can see the numbers via their own status tool.
#
# The window is deliberately below the model's real ceiling: the recap, the tool
# schemas and the reply are all drawn from the same budget, and the token
# estimate is an estimate. Crossing the ceiling costs a 4xx, which the runtime
# reads as the run's own fault; evicting slightly early costs nothing.
# tests/test_services.py pins window <= 80% of ceiling.
MODEL_CONTEXT_CEILING_TOKENS=200000
CONTEXT_WINDOW_TOKENS=160000
OUTPUT_RESERVE_TOKENS=8000
# Eviction moves in chunks of this size so the window's start holds still and
# consecutive requests share a long prefix. Defaults to an eighth of the window.
#CONTEXT_WINDOW_EVICTION_TOKENS=20000
```

- [ ] **Step 3c: And in the environment compose actually builds**

In `docker-compose.yml`, the `x-env: &env` anchor. Replace the existing
`CONTEXT_WINDOW_TOKENS: ${CONTEXT_WINDOW_TOKENS:-200000}` line:

```yaml
  CONTEXT_WINDOW_TOKENS: ${CONTEXT_WINDOW_TOKENS:-160000}
  # What the upstream refuses past. Recorded so the window can be checked
  # against it; read by tests/test_services.py, not by the runtime.
  MODEL_CONTEXT_CEILING_TOKENS: ${MODEL_CONTEXT_CEILING_TOKENS:-200000}
  # The part of the window held back for the completion.
  OUTPUT_RESERVE_TOKENS: ${OUTPUT_RESERVE_TOKENS:-8000}
```

Then the ten per-agent overrides, which each read
`${HOSTn_CONTEXT_WINDOW_TOKENS:-${CONTEXT_WINDOW_TOKENS:-200000}}` — the inner
default is the last resort when `.env` sets nothing, and it is the one that was left
at the ceiling:

```bash
# one edit per agent service, HOST1 through HOST10
sed -i 's/:-${CONTEXT_WINDOW_TOKENS:-200000}/:-${CONTEXT_WINDOW_TOKENS:-160000}/' docker-compose.yml
grep -c 'CONTEXT_WINDOW_TOKENS:-160000' docker-compose.yml   # expect 11: the x-env anchor and ten agents
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_services.py -q -k "shipped_window"`
Expected: PASS. The window is the whole of what ships — the recap (15% of it, 24000)
and the reply reserve (8000) come *out* of the 160000 rather than on top of it — and
160000 is exactly 80% of the 200000 ceiling, leaving 40000 tokens for the estimator
to be wrong in.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add containers/agent.env .env.example docker-compose.yml tests/test_services.py
git commit -m "world: give the context window headroom beneath a declared ceiling

The window was set to exactly the model's real limit, so the eviction
threshold and the hard error were the same number. Declare the ceiling,
set the window beneath it, and pin the relationship in a test.

The value lives in three places and only two of them decide anything:
containers/agent.env documents it, .env.example defaults it, and
docker-compose.yml is what the container's chassis actually reads. All
three now say 160000, and the test reads all three.

Refs space_chassis-3c98f068b5

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 4: A run can end its conversation, not only itself

**Files:**
- Modify: `services/chassis.py` (`Carried` at 108; `RunContext` at 289; `Chassis.resume` at 809)
- Test: `tests/test_chassis.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Carried.clear_recap() -> None`; `Chassis.reset_context() -> None`; `RunContext.reset(note: str) -> None`.

**Why:** Every documented exit resumes. `resume()`'s own docstring says a duty wanting a clean slate deletes the file; `run()`'s `finally` block checkpoints on every exit path and writes it straight back from memory. The only real reset in the world is the supervisor's flap guard, reached by exiting cleanly three times in two minutes. An agent that judges its context spent cannot act on the judgement.

There is a second defect in the same place: when a conversation is absent but `HANDOFF.md` exists — after a reset, and after the flap guard, which moves `conversation.json` and leaves the note — `resume()` inserts the note and then skips the bootstrap, because `self.messages` is no longer empty. The next run opens on an instruction with no world around it.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_reset_clears_the_conversation_the_exit_path_would_otherwise_rewrite(tmp_path):
    """Deleting the file does not work: the exit checkpoint writes it back.

    A reset has to empty the conversation the runtime holds, not the copy on
    disk, because the copy on disk is written from the one in memory on the way
    out of every run.
    """
    instance = object.__new__(chassis.Chassis)
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.carried.session_dir.mkdir(parents=True, exist_ok=True)
    instance.messages = [message("user", "hour one"), message("assistant", "drift")]
    instance.recap_folded = 7
    instance.turn = 40
    instance.record = lambda *_args, **_kwargs: None
    instance.carried.append_recap(["- [assistant] something old"])

    chassis.Chassis.reset_context(instance)
    instance.carried.save_conversation(instance.messages)

    assert instance.messages == []
    assert instance.recap_folded == 0
    assert instance.carried.recap() == ""
    assert not instance.carried.conversation(), "an empty conversation must not resume"


def test_a_run_with_a_note_and_no_conversation_opens_on_the_brief_as_well(tmp_path, monkeypatch):
    """A note without the opening is an instruction with no world around it.

    This is the state after a reset, and after the supervisor's flap guard,
    which moves the conversation aside and leaves HANDOFF.md where it is.
    """
    import sys
    import types

    instance = object.__new__(chassis.Chassis)
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.carried.handoff_path.parent.mkdir(parents=True, exist_ok=True)
    instance.carried.handoff_path.write_text("carry on from where the last run stopped", encoding="utf-8")
    instance.messages = []
    instance.recap_folded = 0
    instance.context = None
    instance.record = lambda *_args, **_kwargs: None

    duty = types.ModuleType("duty")
    duty.bootstrap = lambda _context: [
        {"role": "user", "content": "You are agent_1. Read the brief."}
    ]
    monkeypatch.setitem(sys.modules, "duty", duty)

    chassis.Chassis.resume(instance, {})

    contents = [str(m.get("content", "")) for m in instance.messages]
    assert any("Read the brief" in text for text in contents), "the opening was skipped"
    assert any("carry on from" in text for text in contents), "the note was lost"
    assert contents.index(next(t for t in contents if "Read the brief" in t)) < contents.index(
        next(t for t in contents if "carry on from" in t)
    ), "the note must follow the opening, not replace it"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_chassis.py -q -k "reset_clears or note_and_no_conversation"`
Expected: FAIL — `AttributeError: type object 'Chassis' has no attribute 'reset_context'`.

- [ ] **Step 3: Add `clear_recap` to `Carried`**

Beside `append_recap`:

```python
    def clear_recap(self) -> None:
        """Forget what was dropped. Only a deliberate reset should call this."""
        write_text_atomic(self.recap_path, "")
```

- [ ] **Step 4: Add `reset_context` to `Chassis`**

Beside `write_handoff`:

```python
    def reset_context(self) -> None:
        """Empty the conversation this run is holding, and the recap with it.

        Emptying the list rather than deleting the file is what makes this
        stick: `run()` checkpoints in a `finally`, so anything written to disk
        during a run is overwritten from memory on the way out. An empty list
        round-trips as empty, and `resume()` reads that as nothing to resume.

        The handoff note is deliberately untouched, and so are the diary and
        everything in the agent's home: this ends a conversation, not a lineage.
        """
        self.messages[:] = []
        self.recap_folded = 0
        self.carried.clear_recap()
        self.record("context_reset", turns=self.turn)
```

- [ ] **Step 5: Add `reset` to `RunContext`**

Beside `handoff`:

```python
    def reset(self, note: str) -> None:
        """End this run and give the next one a clean conversation, carrying `note`.

        The counterpart to `handoff`. Both end the run and both leave a note;
        the difference is what the next run inherits. After a handoff it opens
        on everything said so far. After a reset it opens on the brief and the
        note, with none of the conversation and none of the recap.

        What is written down survives either way: the diary, the codebase and
        anything else in the agent's home are untouched.
        """
        self._chassis.write_handoff(note)
        self._chassis.reset_context()
        raise SystemExit(EXIT_HANDOFF)
```

- [ ] **Step 6: Fix the opening in `resume`**

Replace the body of `Chassis.resume` from `carried = ...` down to the `return`:

```python
        carried = self.carried.conversation()
        seeded_by_duty = False
        if carried:
            self.messages.extend(carried)
            self.recap_folded = int(previous.get("recap_folded", 0) or 0)
            # The recap is deliberately NOT inserted into the conversation here.
            # `prepared_view` pins it from disk on every request, always current and
            # clipped to its share of the window. Storing a second copy used to be
            # harmless -- both were identical, so the dedup check dropped one. Now
            # that the sent copy is clipped, the two differ whenever the recap is
            # over its allowance, the dedup misses, and a saturated recap ships
            # twice: once clipped and paid for, once whole, pinned and never evicted.
            handoff = self.carried.handoff()
            if handoff:
                self.messages.insert(
                    0,
                    {
                        "role": "user",
                        "content": "A previous run of you left this handoff note:\n\n" + handoff,
                    },
                )
                seeded_by_duty = True
            return True

        # No conversation to resume: a fresh lineage, a reset, or the flap guard
        # having moved one aside. Either way the run opens on the duty's own
        # bootstrap *first* -- a note inserted in front of nothing is an
        # instruction with no world around it -- and the note follows it.
        bootstrap = getattr(sys.modules.get("duty"), "bootstrap", None)
        if callable(bootstrap):
            seeded = bootstrap(self.context)
            if isinstance(seeded, list) and seeded:
                self.messages.extend(seeded)
                seeded_by_duty = True
        if not self.messages:
            self.messages.append(
                {
                    "role": "user",
                    "content": (
                        "You are running. Nothing has been assigned to you yet. "
                        "Read /opt/brief/MISSION.md, /opt/brief/WORLD.md and "
                        "/opt/brief/PROTOCOL.md before deciding anything."
                    ),
                }
            )
        handoff = self.carried.handoff()
        if handoff:
            self.messages.append(
                {
                    "role": "user",
                    "content": "A previous run of you left this handoff note:\n\n" + handoff,
                }
            )
            seeded_by_duty = True
        return seeded_by_duty
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_chassis.py -q`
Expected: PASS.

- [ ] **Step 8: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS. `tests/test_run_end_to_end.py` exercises resume across a real run; the carried-conversation branch above is unchanged in behaviour.

- [ ] **Step 9: Commit**

```bash
git add services/chassis.py tests/test_chassis.py
git commit -m "chassis: let a run end its conversation, not only itself

Every exit path resumed. The documented escape hatch -- delete the file --
was undone by the exit-path checkpoint, so the only real reset in the world
was the supervisor's flap guard, reached by accident. Add reset() beside
handoff(), and open a conversation-less run on the brief before the note
instead of on the note alone.

Refs space_chassis-a5c2a27876

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 5: A run can replace its own middle with a summary

**Files:**
- Modify: `services/chassis.py` (`selection` at 871; `RunContext` at 289; new `Chassis.compact`)
- Test: `tests/test_chassis.py`

**Interfaces:**
- Consumes: `Chassis.reset_context` conventions from Task 4 (the record event shape).
- Produces: `chassis.pinned_indices(messages) -> set[int]`; `chassis.safe_cut(messages, index) -> int`; `Chassis.compact(summary: str, keep_last: int) -> int`; `RunContext.compact(summary: str, keep_last: int = 20) -> str`.

**Why:** `fold_recap_if_needed` writes 400 characters of every dropped message — a transcript index, not a summary. `RunContext.set_history` exists, is documented as the duty's to use, and is called nowhere. Compaction is the lever that stretches a run; reset is the lever that ends it. An agent needs both to have a real choice.

- [ ] **Step 1: Write the failing tests**

```python
def test_compaction_keeps_the_opening_and_replaces_the_middle(tmp_path):
    messages = [message("system", "standing orders"), message("user", "the opening problem")]
    messages += [message("assistant", f"turn {index}") for index in range(60)]
    instance = object.__new__(chassis.Chassis)
    instance.messages = messages
    instance.recap_folded = 0
    instance.turn = 60
    instance.record = lambda *_args, **_kwargs: None

    dropped = chassis.Chassis.compact(instance, "we tried A and B; B works", keep_last=10)

    contents = [str(m.get("content", "")) for m in instance.messages]
    assert "standing orders" in contents[0]
    assert any("the opening problem" in text for text in contents)
    assert any("we tried A and B" in text for text in contents)
    assert any("turn 59" in text for text in contents), "the recent tail was lost"
    assert not any("turn 5" == text for text in contents), "the middle was not replaced"
    assert dropped > 0


def test_compaction_never_cuts_between_a_tool_call_and_its_result():
    """Every upstream rejects an assistant tool_call with no result, and a tool
    result with no call. A cut that lands between them turns a compaction into
    a crash loop that looks like a model fault."""
    messages = [
        message("user", "go"),
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "name": "read_file", "content": "contents"},
        message("assistant", "done"),
    ]
    for index in range(len(messages) + 1):
        cut = chassis.safe_cut(messages, index)
        tail = messages[cut:]
        assert not (tail and tail[0].get("role") == "tool"), f"cut {index} orphaned a result"
        if cut > 0:
            previous = messages[cut - 1]
            assert not previous.get("tool_calls"), f"cut {index} orphaned a call"


def test_a_second_compaction_supersedes_the_first_summary(tmp_path):
    """Summaries are system messages, and system messages are pinned forever.

    Without this, every compaction leaves its summary permanently in the prefix and
    the tail loses that much room for good -- so the lever meant to buy a run more
    time costs it a little more each time it is pulled.
    """
    instance = object.__new__(chassis.Chassis)
    instance.messages = [message("user", "opening")] + [
        message("assistant", f"turn {index}") for index in range(40)
    ]
    instance.recap_folded = 0
    instance.turn = 40
    instance.record = lambda *_args, **_kwargs: None

    chassis.Chassis.compact(instance, "first summary", keep_last=10)
    instance.messages += [message("assistant", f"later {index}") for index in range(30)]
    chassis.Chassis.compact(instance, "second summary", keep_last=10)

    summaries = [m for m in instance.messages if chassis.is_summary(m)]
    assert len(summaries) == 1, f"{len(summaries)} summaries survived; they accumulate"
    assert "second summary" in str(summaries[0]["content"])
    assert any("later 29" in str(m.get("content", "")) for m in instance.messages)


def test_compaction_does_not_also_fold_what_it_summarised(tmp_path):
    """The summary and the recap must not both claim the same messages."""
    instance = object.__new__(chassis.Chassis)
    instance.messages = [message("user", "opening")] + [
        message("assistant", f"turn {index}") for index in range(40)
    ]
    instance.recap_folded = 0
    instance.turn = 40
    instance.record = lambda *_args, **_kwargs: None
    chassis.Chassis.compact(instance, "summary", keep_last=5)
    assert instance.recap_folded == len(instance.messages) - 5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_chassis.py -q -k "compaction"`
Expected: FAIL — `AttributeError: module 'chassis' has no attribute 'safe_cut'`.

- [ ] **Step 3: Extract `pinned_indices` and add `safe_cut`**

In `services/chassis.py`, above `selection`:

```python
def pinned_indices(messages: list[dict]) -> set[int]:
    """The messages a run cannot afford to lose: its standing orders and its opening.

    Every system message, plus the first user message. A run that has dropped
    its opening problem no longer knows what it is doing.
    """
    pinned = {index for index, message in enumerate(messages) if message.get("role") == "system"}
    first_user = next(
        (index for index, message in enumerate(messages) if message.get("role") == "user"), None
    )
    if first_user is not None:
        pinned.add(first_user)
    return pinned


SUMMARY_PREFIX = (
    "Summary of earlier conversation, written by the run that lived it and kept in "
    "place of it:\n\n"
)


def is_summary(message: dict) -> bool:
    """Whether a message is a compaction summary this runtime wrote."""
    return message.get("role") == "system" and str(message.get("content", "")).startswith(
        SUMMARY_PREFIX
    )


def safe_cut(messages: list[dict], index: int) -> int:
    """The first index at or after `index` where the conversation can be cut.

    Two shapes are rejected by every upstream: a tool result whose call is gone,
    and an assistant tool_call whose result is gone. `selection` already guards
    the first because the window only ever drops a prefix. Compaction can create
    the second, so this guards both.
    """
    cut = max(0, min(index, len(messages)))
    while cut < len(messages) and messages[cut].get("role") == "tool":
        cut += 1
    while 0 < cut <= len(messages) and messages[cut - 1].get("tool_calls"):
        cut += 1
        while cut < len(messages) and messages[cut].get("role") == "tool":
            cut += 1
    return min(cut, len(messages))
```

In `selection`, replace the pinned-set construction with `pinned = pinned_indices(messages)` and delete the now-duplicated `first_user` lines.

- [ ] **Step 4: Add `Chassis.compact`**

Beside `reset_context`:

```python
    def compact(self, summary: str, keep_last: int) -> int:
        """Replace everything between the opening and the last `keep_last` messages.

        The window forgets by dropping the oldest thing that will not fit, which
        is cheap and lossy in the same proportion everywhere. Compaction is the
        other trade: spend a turn deciding what mattered, and keep that instead
        of the first 400 characters of everything.

        The runtime does not decide when this is worth doing, or what a good
        summary contains. It decides only that the result is still a legal
        conversation: the opening survives, no tool call loses its result, and
        the recap does not also claim the messages the summary now covers.

        Returns how many messages were dropped.
        """
        # Prior summaries are system messages, so `pinned_indices` would keep every
        # one of them forever: compact twice and two are pinned, compact N times and
        # the tail has permanently lost N summaries' worth of room. The agent was
        # told it is replacing the middle, and the last summary is part of the
        # middle, so the new summary supersedes it.
        pinned = [
            index
            for index in sorted(pinned_indices(self.messages))
            if not is_summary(self.messages[index])
        ]
        cut = safe_cut(self.messages, max(0, len(self.messages) - max(0, keep_last)))
        prefix = [self.messages[index] for index in pinned if index < cut]
        tail = self.messages[cut:]
        dropped = len(self.messages) - len(prefix) - len(tail)
        if dropped <= 0:
            return 0
        framed = {"role": "system", "content": SUMMARY_PREFIX + summary}
        self.messages[:] = [*prefix, framed, *tail]
        # The summary now covers this material, so the recap must not fold it a
        # second time: everything before the kept tail is already accounted for.
        self.recap_folded = len(prefix) + 1
        self.record("compacted", dropped=dropped, kept=len(tail), summary_chars=len(summary))
        return dropped
```

- [ ] **Step 5: Add `RunContext.compact`**

Beside `set_history`:

```python
    def compact(self, summary: str, keep_last: int = 20) -> str:
        """Replace the middle of this conversation with `summary`, keeping the last `keep_last`.

        The opening and any standing instructions are kept whatever happens, and
        the cut is moved if it would separate a tool call from its result.

        Args:
            summary: What the replaced stretch amounted to. Nothing else survives it.
            keep_last: How many of the most recent messages to leave untouched.
        """
        dropped = self._chassis.compact(summary, keep_last)
        if not dropped:
            return "nothing was compacted: there was no middle between the opening and the tail"
        return f"compacted: {dropped} message(s) replaced by the summary, {keep_last} kept"
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_chassis.py -q`
Expected: PASS.

- [ ] **Step 7: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add services/chassis.py tests/test_chassis.py
git commit -m "chassis: give a run a way to compact its own middle

The recap keeps 400 characters of everything; set_history existed and was
called nowhere. compact() spends a turn deciding what mattered and keeps
that instead, without letting the cut orphan a tool call or letting the
recap fold what the summary already covers.

Refs space_chassis-bbe02a114d

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 6: `status()` reports rate and composition, not only position

**Files:**
- Modify: `services/chassis.py` (`Chassis.__init__` at 377; `Chassis.checkpoint` at 620; `Chassis.status` at 660; `Chassis.turn_once` at 498; `Chassis.run` finally block at 788)
- Test: `tests/test_chassis.py`

**Interfaces:**
- Consumes: `Chassis.tail_room`, `Chassis.overhead_tokens` (Task 1); `Chassis.last_prompt_tokens` (Task 2); `chassis.pinned_indices` (Task 5 Step 3 — Task 6 therefore lands after Task 5, and cannot be implemented on its own).
- Produces: `Chassis.turn_costs: list[int]`; `Chassis.previous_ended: int | None`; `Chassis.checkpoint(ended: int | None = None)`; the new `status()` keys.

**Why `previous_ended` is carried and not re-read:** `checkpoint()` rewrites `run.json` on every turn and never writes `ended`, so a run that reads the previous run's exit back out of the file sees it only until its own first turn. Measured on the first revision of this task: `ended = 42` after the exit-path checkpoint, `ended = None` one turn later. The value is taken once, at the top of the run, and reported from memory.

**Why (a pre-existing bug this fixes):** `resume()` reads `previous.get("recap_folded", 0)` but `checkpoint()` never wrote the key, so every resumed run restarted at 0 and folded the same prefix into the recap again. That is why the recap saturates far sooner than its size suggests — it is full of duplicates. The `checkpoint` rewrite below adds the key.

**Why:** `status()` reports position — turn number, tokens now, tokens left. Deciding between stretching and resetting needs rate and composition: what it is spending per turn, how many turns that leaves, how much of the window is recap rather than conversation, and whether the recap has begun discarding its own oldest material. `previous_run_ended` is advertised and permanently `null` because nothing ever writes `ended`.

- [ ] **Step 1: Write the failing tests**

```python
def test_status_reports_a_burn_rate_and_a_runway(tmp_path):
    """ "60k left" means nothing without "and you are spending 4k a turn"."""
    instance = object.__new__(chassis.Chassis)
    instance.slug, instance.name = "agent_1", "agent_1"
    instance.run_id, instance.turn = "r1", 3
    instance.entry, instance.model = "/work/duty.py", "stub"
    instance.messages = [message("user", "x" * 4000)]
    instance.context_window = 100_000
    instance.output_reserve = 8_000
    instance.eviction_chunk = None
    instance.recap_folded = 0
    instance.previous_ended = None
    instance.tools = chassis.ToolRegistry()
    instance.usage_totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_prompt_tokens": 0,
    }
    instance.turn_costs = [1000, 2000, 3000]
    instance.max_turns = instance.max_seconds = None
    instance.started_at = chassis.utc_now()
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.work_dir = instance.home_dir = instance.diary_dir = instance.duty_dir = tmp_path

    report = chassis.Chassis.status(instance)

    assert report["tokens_per_turn"] == 2000
    assert report["turns_remaining_estimate"] > 0
    assert set(report["window_composition"]) == {"recap_tokens", "pinned_tokens", "tail_tokens"}
    assert report["recap_saturated"] is False
    assert report["eviction_active"] is False


def test_status_reports_the_previous_exit_after_this_run_has_turned(tmp_path):
    """The file forgets; the run does not.

    checkpoint() writes run.json on every turn and never writes `ended`, so a
    run that read the previous exit back out of the file would see it at turn 0
    and null from turn 1 on -- which is when an agent actually asks.
    """
    instance = object.__new__(chassis.Chassis)
    instance.slug, instance.name = "agent_1", "agent_1"
    instance.run_id, instance.turn, instance.model = "r2", 1, "stub"
    instance.entry = "/work/duty.py"
    instance.messages = [message("user", "hello")]
    instance.context_window = 100_000
    instance.output_reserve = 8_000
    instance.eviction_chunk = None
    instance.recap_folded = 0
    instance.tools = chassis.ToolRegistry()
    instance.usage_totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_prompt_tokens": 0,
    }
    instance.turn_costs = []
    instance.max_turns = instance.max_seconds = None
    instance.started_at = chassis.utc_now()
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.carried.session_dir.mkdir(parents=True, exist_ok=True)
    instance.work_dir = instance.home_dir = instance.diary_dir = instance.duty_dir = tmp_path

    # The run that just ended wrote its exit code on the way out.
    chassis.Chassis.checkpoint(instance, ended=chassis.EXIT_HANDOFF)
    instance.previous_ended = instance.carried.meta().get("ended")

    # The next run takes one turn, which rewrites run.json without the key.
    instance.run_id, instance.turn = "r3", 1
    chassis.Chassis.checkpoint(instance)
    assert instance.carried.meta().get("ended") is None, "the file has moved on"

    assert chassis.Chassis.status(instance)["previous_run_ended"] == chassis.EXIT_HANDOFF


def test_a_resumed_run_does_not_fold_the_same_messages_twice(tmp_path):
    """resume() reads recap_folded from the meta; checkpoint() never wrote it.

    So every restart replayed the fold from index 0 and appended the same lines to
    the recap again, which is why a 96 KB recap holds far less history than its
    size suggests.
    """
    instance = object.__new__(chassis.Chassis)
    instance.slug, instance.name = "agent_1", "agent_1"
    instance.run_id, instance.turn, instance.model = "r1", 9, "stub"
    instance.entry = "/work/duty.py"
    instance.messages = [message("user", "hello")]
    instance.context_window = 100_000
    instance.recap_folded = 12
    instance.usage_totals = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cached_prompt_tokens": 0}
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.carried.session_dir.mkdir(parents=True, exist_ok=True)

    chassis.Chassis.checkpoint(instance)

    assert instance.carried.meta()["recap_folded"] == 12


def test_the_next_run_can_see_how_the_last_one_ended(tmp_path):
    """An agent cannot tell a clean handoff from a crash without this."""
    instance = object.__new__(chassis.Chassis)
    instance.slug, instance.name = "agent_1", "agent_1"
    instance.run_id, instance.turn, instance.model = "r1", 5, "stub"
    instance.entry = "/work/duty.py"
    instance.messages = [message("user", "hello")]
    instance.context_window = 100_000
    instance.recap_folded = 0
    instance.usage_totals = {
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "total_tokens": 2,
        "cached_prompt_tokens": 0,
    }
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.carried.session_dir.mkdir(parents=True, exist_ok=True)

    chassis.Chassis.checkpoint(instance, ended=chassis.EXIT_HANDOFF)

    assert instance.carried.meta()["ended"] == chassis.EXIT_HANDOFF
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_chassis.py -q -k "burn_rate or how_the_last_one_ended"`
Expected: FAIL — `KeyError: 'tokens_per_turn'`.

- [ ] **Step 3: Track per-turn cost**

In `Chassis.__init__`, beside `self.last_prompt_tokens`:

```python
        # The cost of recent turns, newest last. Bounded because a burn rate is
        # about the recent past: a run that has changed what it is doing should
        # not be judged on what it used to cost.
        self.turn_costs: list[int] = []
        # The exit code the previous run left in run.json, taken once at the top
        # of this run because this run's own checkpoints overwrite the key.
        self.previous_ended: int | None = None
```

In `Chassis.turn_once`, immediately before `self.checkpoint()`:

```python
        if self.last_prompt_tokens:
            self.turn_costs.append(self.last_prompt_tokens)
            del self.turn_costs[:-8]
```

- [ ] **Step 4: Let `checkpoint` record how a run ended**

Change the signature and add the key:

```python
    def checkpoint(self, ended: int | None = None) -> None:
        self.carried.save_conversation(self.messages)
        meta = {
            "agent": self.slug,
            "name": self.name,
            "run": self.run_id,
            "turn": self.turn,
            "model": self.model,
            "updated": iso(),
            "context_tokens": estimate_tokens(self.messages),
            "context_window": self.context_window,
            "recap_folded": self.recap_folded,
            "usage": dict(self.usage_totals),
            "entry": str(self.entry),
        }
        if ended is not None:
            meta["ended"] = ended
        self.carried.save_meta(meta)
```

In `Chassis.run`'s `finally` block, replace the checkpoint call:

```python
            with contextlib.suppress(Exception):
                self.checkpoint(ended=exit_code)
```

And beside `previous = self.carried.meta()` at the top of `run()`, take the previous
run's exit while the file still holds it:

```python
        previous = self.carried.meta()
        self.previous_ended = previous.get("ended")
```

- [ ] **Step 5a: Make `context_left` agree with `status`**

`RunContext.context_left` still divides the whole window, while `status` now reports the room the tail is really drawn against — and `tasks/duty.py::_summary` puts `context_left()` into every handoff note. Replace it:

```python
    def context_left(self) -> int:
        """Estimated tokens of room left before eviction starts.

        Measured against the budget the tail is really drawn against, not the
        whole window: the recap, the tool schemas and the reply are paid for out
        of the same number, and a run told otherwise is told a larger number than
        it has.
        """
        return self._chassis.tail_room() - estimate_tokens(self._chassis.messages)
```

`chassis_budget()` is now unused; delete it.

- [ ] **Step 5: Extend `status`**

Replace `Chassis.status` (the whole method, indentation included — it is shown at its
class indentation so it can be pasted):

```python
    def status(self) -> dict:
        meta = self.carried.meta()
        recap = clip_recap(self.carried.recap(), int(self.context_window * RECAP_WINDOW_FRACTION))
        recap_tokens = estimate_text_tokens(recap)
        pinned = pinned_indices(self.messages)
        pinned_tokens = estimate_tokens([self.messages[index] for index in sorted(pinned)])
        tail_tokens = max(0, estimate_tokens(self.messages) - pinned_tokens)
        room = self.tail_room()
        left = max(0, room - estimate_tokens(self.messages))
        per_turn = sum(self.turn_costs) // len(self.turn_costs) if self.turn_costs else 0
        return {
            "agent": self.slug,
            "name": self.name,
            "run": self.run_id,
            "entry": str(self.entry),
            "model": self.model,
            "turn_this_run": self.turn,
            "turns_before_this_run": meta.get("turn"),
            # Taken from the run's own memory, not from the file: this run's
            # checkpoints have already overwritten the file's copy.
            "previous_run_ended": self.previous_ended,
            "context_window_tokens": self.context_window,
            "context_tokens_now": estimate_tokens(self.messages),
            "context_tokens_left": left,
            # What the window is made of, not just how full it is: a window that
            # is a quarter recap needs a different remedy from one that is all tail.
            "window_composition": {
                "recap_tokens": recap_tokens,
                "pinned_tokens": pinned_tokens,
                "tail_tokens": tail_tokens,
            },
            # Rate, and therefore runway. A token count with no denominator does
            # not tell a run whether it is about to end.
            "tokens_per_turn": per_turn,
            "turns_remaining_estimate": (left // per_turn) if per_turn else None,
            # The recap has a cap, and past it the oldest material is discarded
            # without notice. This is the moment that becomes true.
            "recap_saturated": len(self.carried.recap().encode("utf-8")) >= RECAP_MAX_BYTES,
            "eviction_active": self.recap_folded > 0,
            "recap_messages_folded": self.recap_folded,
            "handoff_present": self.carried.handoff_path.exists(),
            "usage_this_run": dict(self.usage_totals),
            "run_max_turns": self.max_turns,
            "run_max_seconds": self.max_seconds,
            "started": iso(self.started_at),
            "work_dir": str(self.work_dir),
            "home_dir": str(self.home_dir),
            "diary_dir": str(self.diary_dir),
            "diode_duty_dir": str(self.duty_dir),
        }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_chassis.py -q`
Expected: PASS.

- [ ] **Step 7: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add services/chassis.py tests/test_chassis.py
git commit -m "chassis: report rate and composition, and how the last run ended

status() gave position only, and previous_run_ended was advertised and always
null because nothing wrote it. A run choosing between compacting and
resetting needs its burn rate, its runway, what the window is made of, and
whether the recap has started discarding its own oldest material.

Refs space_chassis-f83364fe22

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 7: The seed duty bounds its output and exposes the two levers

**Files:**
- Modify: `tasks/duty.py` (`read_file` at 102; `run` at 206; new tools beside `handoff` at 487)
- Test: `tests/test_chassis.py`

**Interfaces:**
- Consumes: `RunContext.compact` (Task 5); `RunContext.reset` (Task 4).
- Produces: `duty.TOOL_OUTPUT_MAX_CHARS`; `duty._bounded(text: str, name: str) -> str`; the `compact` and `reset` tools.

**Why:** `run()` returns combined stdout and stderr with no bound and `read_file` defaults to the whole file, while `selection()` always keeps the last message — so one `cat` of a build log fills the window in a single turn and is checkpointed into the conversation. And the two levers added above are unreachable by a model until something registers them.

This is the fleet seed, which the fleet may rewrite. The changes stay mechanical: bound the output, name the file it was written to, register the levers, and say what they cost. Nothing here decides when to use them.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_large_tool_result_is_bounded_and_spilled_to_a_file(tmp_path, monkeypatch):
    """One `cat` of a build log must not become the whole window.

    The window always keeps the last message, so an unbounded tool result is
    not evicted -- it evicts everything else.
    """
    import sys

    sys.path.insert(0, str(PROJECT / "tasks"))
    monkeypatch.setenv("AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("WORK_DIR", str(tmp_path / "work"))
    (tmp_path / "work").mkdir(parents=True, exist_ok=True)
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    import importlib

    import duty as duty_module

    duty_module = importlib.reload(duty_module)

    result = duty_module._bounded("x" * (duty_module.TOOL_OUTPUT_MAX_CHARS * 3), "probe")

    assert len(result) < duty_module.TOOL_OUTPUT_MAX_CHARS * 2
    assert "truncated" in result
    spilled = next((tmp_path / "home" / "spill").glob("probe-*"), None)
    assert spilled is not None, "the full output was discarded rather than written down"
    assert len(spilled.read_text(encoding="utf-8")) == duty_module.TOOL_OUTPUT_MAX_CHARS * 3


def test_the_seed_duty_registers_both_lifespan_levers():
    import sys

    sys.path.insert(0, str(PROJECT / "tasks"))
    import duty as duty_module

    assert "compact" in duty_module.tools.tools
    assert "reset" in duty_module.tools.tools
```

Add `PROJECT = Path(__file__).resolve().parent.parent` at the top of `tests/test_chassis.py` if it is not already there.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_chassis.py -q -k "bounded_and_spilled or lifespan_levers"`
Expected: FAIL — `AttributeError: module 'duty' has no attribute '_bounded'`.

- [ ] **Step 3: Add the bound and the spill**

In `tasks/duty.py`, beside `WRITABLE_ROOTS`:

```python
# A tool result goes into the conversation, and the conversation's newest message
# is never evicted -- so an unbounded result does not get dropped, it drops
# everything else. Bound what is shown; keep all of it on disk.
TOOL_OUTPUT_MAX_CHARS = int(os.environ.get("TOOL_OUTPUT_MAX_CHARS", "20000"))
SPILL_DIR = HOME_DIR / "spill"


def _bounded(text: str, name: str) -> str:
    """`text` if it is small enough, otherwise its head and tail plus a path to the rest."""
    if len(text) <= TOOL_OUTPUT_MAX_CHARS:
        return text
    SPILL_DIR.mkdir(parents=True, exist_ok=True)
    path = SPILL_DIR / f"{name}-{int(time.time() * 1000)}.txt"
    path.write_text(text, encoding="utf-8")
    half = TOOL_OUTPUT_MAX_CHARS // 2
    return (
        f"{text[:half]}\n\n... truncated: {len(text)} characters in total, "
        f"all of it written to {path} ...\n\n{text[-half:]}"
    )
```

In `run()`, replace the final `return "\n".join(parts)`:

```python
    return _bounded("\n".join(parts), "run")
```

In `read_file()`, replace the final return:

```python
    return _bounded(f"{header}\n{numbered}" if numbered else f"{header}\n(empty)", "read_file")
```

- [ ] **Step 4: Register the two levers**

In `tasks/duty.py`, beside `handoff`:

```python
@tools.register
def compact(summary: str, keep_last: int = 20) -> str:
    """Replace the middle of this conversation with a summary you write.

    What you replace is gone from the conversation: only the summary remains of
    it. Your standing instructions and the opening problem are kept whatever
    happens, as are the most recent `keep_last` messages.

    Args:
        summary: What the replaced stretch amounted to. Write it for yourself.
        keep_last: How many of the most recent messages to leave untouched.
    """
    if _context is None:
        return "error: this tool is only usable inside a run"
    return _context.compact(summary, keep_last)


@tools.register
def reset(note: str) -> str:
    """End this run and give the next one a clean conversation, carrying `note`.

    Like `handoff`, this ends the run and leaves a note. Unlike `handoff`, the
    next run does not inherit this conversation or the recap of what fell out of
    it -- it opens on the brief and your note, and nothing else. Everything you
    wrote down elsewhere, the diary and the codebase included, is untouched.

    Args:
        note: What the next run needs in order to carry on without this conversation.
    """
    if _context is None:
        return "error: this tool is only usable inside a run"
    _context.reset(note)
    return "unreachable"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_chassis.py -q`
Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Check the lint and the topology**

Run:
```bash
uvx ruff check . --no-cache
uvx ruff format --check . --no-cache
docker compose --profile fleet config -q
```
Expected: clean.

- [ ] **Step 8: Prove it end to end**

Run: `python3 endurance/run_local.py endurance/scenarios/short.json`
Expected: the scenario completes and the report shows the run ending as it did before this plan.

- [ ] **Step 9: Commit**

```bash
git add tasks/duty.py tests/test_chassis.py
git commit -m "duty: bound tool output, and register compact and reset

An unbounded tool result is never evicted, because the window always keeps
the newest message -- so one cat of a build log evicted everything else.
Bound what is shown, write all of it to a file, and name the path. Register
the two lifespan levers so a model can reach them.

Refs space_chassis-3622348dc9, space_chassis-a5c2a27876, space_chassis-bbe02a114d

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 8: A conversation the upstream will accept

**Files:**
- Modify: `services/chassis.py` (`Chassis.turn_once`; `Carried`; `Chassis.resume`; new module functions beside `selection`)
- Test: `tests/test_chassis.py`

**Interfaces:**
- Consumes: `chassis.RECAP_PREFIX`, `chassis.is_stored_recap` (Task 1); the `resume()` rewrite (Task 4).
- Produces: `chassis.HANDOFF_NOTE_PREFIX`; `chassis.is_handoff_note(message) -> bool`; `chassis.repair_messages(messages, keep_recap=False, keep_note=False) -> tuple[list[dict], dict[str, int]]`; a `conversation_repaired` record event.

**Why:** the three lineages under `volumes/home/` hold **43, 51 and 42** assistant messages whose `tool_calls` have no matching `tool` result. Every one of them is a `handoff` call, and there is not one such orphan for any other tool. `turn_once` appends the assistant message, then invokes the tools in order; `handoff` raises `SystemExit` (that is how it ends a run), so the loop aborts before a result is appended and `run()`'s `finally` checkpoints the half-written turn. The next run resumes it and sends an assistant `tool_calls` with no results — the mirror image of the case `selection`'s docstring already guards, and the reason a lineage that used the *documented* way to end a run can no longer start one. Repairing on load is the other half: a conversation that is already damaged must heal rather than poison every request from here on.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_chassis.py`:

```python
def test_a_tool_that_ends_the_run_leaves_no_open_tool_call(tmp_path, monkeypatch):
    """`handoff` raises SystemExit out of the invoke loop, before any result is appended.

    The exit-path checkpoint then stores an assistant message whose tool_calls
    have no results, and every upstream rejects that on the next run. Ending a
    run on purpose is the documented path, so it must not be the way to poison
    one: the three lineages in volumes/home/ carry 43, 51 and 42 such orphans,
    all of them `handoff`.
    """
    import types

    instance = object.__new__(chassis.Chassis)
    instance.messages = []
    instance.turn = 0
    instance.tools = chassis.ToolRegistry()

    @instance.tools.register
    def end_it(note: str) -> str:
        """End the run."""
        raise SystemExit(chassis.EXIT_HANDOFF)

    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.record = lambda *_args, **_kwargs: None
    instance.operation = lambda *_args, **_kwargs: None
    instance.checkpoint = lambda *_args, **_kwargs: None
    instance.slug, instance.run_id = "agent_1", "r1"
    instance.last_had_tools = False
    instance._client = object()

    call = types.SimpleNamespace(
        id="call_1", function=types.SimpleNamespace(name="end_it", arguments='{"note": "done"}')
    )
    message = types.SimpleNamespace(content="", reasoning_content=None, tool_calls=[call])
    response = types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=message)], usage=None
    )
    monkeypatch.setattr(
        chassis.Chassis, "request", lambda self, client, use_tools=True: response
    )

    with pytest.raises(SystemExit):
        chassis.Chassis.turn_once(instance, None)

    calls = [m for m in instance.messages if m.get("tool_calls")]
    results = [m for m in instance.messages if m.get("role") == "tool"]
    assert len(calls) == 1
    assert len(results) == 1, "the run ended with an open tool call in the conversation"
    assert results[0]["tool_call_id"] == "call_1"


def test_a_conversation_with_an_orphaned_tool_call_is_repaired_on_load():
    messages = [
        message("user", "go"),
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "handoff", "arguments": "{}"}}
            ],
        },
        message("user", "the run restarted"),
    ]
    repaired, removed = chassis.repair_messages(messages)
    assert removed["orphaned_tool_calls"] == 1
    assert [m.get("role") for m in repaired] == ["user", "user"]


def test_a_tool_call_that_has_its_result_is_left_alone():
    messages = [
        message("user", "go"),
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "status", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "name": "status", "content": "ok"},
    ]
    repaired, removed = chassis.repair_messages(messages)
    assert repaired == messages
    assert not any(removed.values()), f"a well-formed conversation was edited: {removed}"


def test_repair_drops_the_recap_copies_a_previous_runtime_stored():
    messages = [
        {"role": "system", "content": chassis.RECAP_PREFIX + f"copy {index}"} for index in range(5)
    ]
    messages.append(message("user", "go"))

    repaired, removed = chassis.repair_messages(messages)

    assert removed["stored_recaps"] == 5
    assert not any(chassis.is_stored_recap(m) for m in repaired)


def test_repair_keeps_the_newest_recap_when_there_is_no_file_to_reload_it_from():
    messages = [
        {"role": "system", "content": chassis.RECAP_PREFIX + f"copy {index}"} for index in range(5)
    ]
    repaired, removed = chassis.repair_messages(messages, keep_recap=True)
    assert removed["stored_recaps"] == 4
    assert sum(1 for m in repaired if chassis.is_stored_recap(m)) == 1
    assert "copy 4" in repaired[0]["content"], "the newest copy is the one worth keeping"


def test_repair_keeps_one_handoff_note():
    def note(text: str) -> dict:
        return {"role": "user", "content": chassis.HANDOFF_NOTE_PREFIX + text}

    messages = [note("first"), message("assistant", "worked"), note("second")]
    repaired, removed = chassis.repair_messages(messages, keep_note=True)
    assert removed["old_handoff_notes"] == 1
    assert "second" in str(repaired[-1]["content"])

    repaired, removed = chassis.repair_messages(messages)
    assert removed["old_handoff_notes"] == 2, "with a note on disk, none of them are needed"
    assert not any(chassis.is_handoff_note(m) for m in repaired)


def test_resume_says_what_it_repaired(tmp_path):
    """A run that silently rewrites its own history is a run nobody can audit.

    The recap file is what the run will read instead, which is why the stored
    copy is a duplicate here and not the last resort it is when the file is gone.
    """
    instance = object.__new__(chassis.Chassis)
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.carried.append_recap(["- [assistant] what the file remembers"])
    instance.carried.save_conversation(
        [
            {"role": "system", "content": chassis.RECAP_PREFIX + "a stale copy"},
            message("user", "the opening problem"),
        ]
    )
    instance.messages = []
    instance.recap_folded = 0
    instance.context = None
    events = []
    instance.record = lambda event, **fields: events.append((event, fields))

    chassis.Chassis.resume(instance, {})

    repaired = [fields for event, fields in events if event == "conversation_repaired"]
    assert repaired, f"nothing was recorded: {events}"
    assert repaired[0]["stored_recaps"] == 1
    assert not any(chassis.is_stored_recap(m) for m in instance.messages)
    assert len(instance.messages) == 1, "the message that is not a recap was kept"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_chassis.py -q -k "open_tool_call or repaired_on_load or left_alone or repair_ or says_what_it_repaired"`
Expected: FAIL — `AttributeError: module 'chassis' has no attribute 'repair_messages'`.

- [ ] **Step 3: Add the two predicates and the repair**

In `services/chassis.py`, beside `is_stored_recap`:

```python
# The framing a handoff note is inserted under. It is a constant for the same
# reason RECAP_PREFIX is: the repair has to recognise the ones earlier runs left.
HANDOFF_NOTE_PREFIX = "A previous run of you left this handoff note:\n\n"


def is_handoff_note(message: dict) -> bool:
    """Whether a message is a handoff note a previous run inserted."""
    return message.get("role") == "user" and str(message.get("content", "")).startswith(
        HANDOFF_NOTE_PREFIX
    )
```

Beside `selection`:

```python
def repair_messages(
    messages: list[dict], keep_recap: bool = False, keep_note: bool = False
) -> tuple[list[dict], dict[str, int]]:
    """The conversation, with the damage an earlier runtime left in it removed.

    Three shapes are known, and all three are in the lineages under
    `volumes/home/`:

    * an assistant message whose `tool_calls` have no results (43, 51 and 42 of
      them, every one a `handoff`) -- rejected by every upstream, and nothing
      else in the tree will ever take it out;
    * a stored copy of the recap (68, 79 and 68 of them) -- a system message, so
      the window pins it forever and no amount of eviction reaches it;
    * an old handoff note, one per resume, none of them the current one.

    `keep_recap` and `keep_note` keep the newest of each instead of dropping all
    of them, for the case where the file a fresh copy would come from is empty
    and the stored one is the only memory left.

    Returns the repaired list and a count of what was removed, so a run can say
    what it did rather than quietly rewriting its own history.
    """
    removed = {"orphaned_tool_calls": 0, "stored_recaps": 0, "old_handoff_notes": 0}
    answered = {message.get("tool_call_id") for message in messages if message.get("role") == "tool"}
    newest = {
        "recap": max((i for i, m in enumerate(messages) if is_stored_recap(m)), default=-1),
        "note": max((i for i, m in enumerate(messages) if is_handoff_note(m)), default=-1),
    }
    repaired: list[dict] = []
    for index, message in enumerate(messages):
        calls = message.get("tool_calls") or []
        if calls and not all(call.get("id") in answered for call in calls):
            removed["orphaned_tool_calls"] += 1
            continue
        if is_stored_recap(message) and not (keep_recap and index == newest["recap"]):
            removed["stored_recaps"] += 1
            continue
        if is_handoff_note(message) and not (keep_note and index == newest["note"]):
            removed["old_handoff_notes"] += 1
            continue
        repaired.append(message)
    return repaired, removed
```

- [ ] **Step 4: Write the result before the exit travels**

In `Chassis.turn_once`, replace the tool-call loop's body:

```python
        for call in tool_calls:
            try:
                result = self.invoke(call.function.name, call.function.arguments)
            except SystemExit:
                # A tool that ends the run -- handoff, reset -- unwinds through
                # here, and the assistant message that asked for it is already in
                # the conversation. Leaving the call unanswered stores a turn no
                # upstream will accept, which is how a lineage that handed off
                # correctly stops being able to start.
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.function.name,
                        "content": "the run ended while this call was being made",
                    }
                )
                raise
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.function.name,
                    "content": result,
                }
            )
```

- [ ] **Step 5: Repair on load**

In `Chassis.resume`, replace the head of the carried branch (the version Task 4 left):

```python
        carried = self.carried.conversation()
        note = self.carried.handoff()
        seeded_by_duty = False
        if carried:
            repaired, removed = repair_messages(
                carried, keep_recap=not self.carried.recap(), keep_note=not note
            )
            if any(removed.values()):
                self.record("conversation_repaired", **removed)
            self.messages.extend(repaired)
            self.recap_folded = int(previous.get("recap_folded", 0) or 0)
            if note:
                self.messages.insert(
                    0,
                    {"role": "user", "content": HANDOFF_NOTE_PREFIX + note},
                )
                seeded_by_duty = True
            return True
```

The branch that follows reads the note from the variable the new head already set, so
the second `self.carried.handoff()` call and its literal prefix go away, and the two
places that insert a note can never drift apart:

```python
        if note:
            self.messages.append({"role": "user", "content": HANDOFF_NOTE_PREFIX + note})
            seeded_by_duty = True
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_chassis.py -q`
Expected: PASS.

- [ ] **Step 7: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS. `tests/test_run_end_to_end.py` drives a real `handoff` through the stub, so the orphan fix is exercised end to end: the conversation it leaves must now be one the recorder will accept on the next run.

- [ ] **Step 8: Commit**

```bash
git add services/chassis.py tests/test_chassis.py
git commit -m "chassis: never checkpoint a turn the upstream will reject

handoff raises SystemExit out of turn_once's invoke loop, so the assistant
message that asked for it was stored with no result and the next run sent a
tool_call nothing answered. The three lineages in volumes/home/ carry 43, 51
and 42 of those, all of them handoff -- the documented way to end a run was
the way to poison one.

The result is now written before the exit travels, and resume() repairs the
conversations already damaged: orphaned calls go, the recap copies earlier
runtimes stored go, and the old notes go, with the newest of each kept only
when there is no file to reload it from. What was removed is recorded.

Refs space_chassis-f976098d48

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 9: A conversation that stays a size, and a checkpoint that can be recovered

**Files:**
- Modify: `services/chassis.py` (constants near line 82; `Carried`; new `Chassis.prune`; `Chassis.checkpoint`; `Chassis.resume`)
- Test: `tests/test_chassis.py`

**Interfaces:**
- Consumes: `chassis.pinned_indices` (Task 5 Step 3); the repair on load (Task 8); `Chassis.checkpoint(ended=...)` and the `recap_folded` it persists (Task 6 — this task lands after it, and its `checkpoint` snippet is written against that signature).
- Produces: `chassis.CONVERSATION_LIMIT`; `Carried.backup_path`; `Carried.staged_path`; `Carried.recovered`; `Carried.conversation_problem() -> str | None`; `Chassis.prune() -> int`; the `conversation_refused`, `conversation_recovered` and `conversation_pruned` record events.

**Why:** two failure modes, one file.

*It never stops growing.* `checkpoint()` writes every message the run has ever held, including the ones the window dropped thousands of turns ago. `mackerel`'s checkpoint is 4.89 MB and grows about 62 KB per resume; `selection` and `estimate_tokens` re-serialise the whole list several times a turn (measured: 39 ms and 13 ms at that size, both scaling with the file rather than the window).

*And then it stops reading at all.* `Carried.conversation()` reads with a 64 MB limit, and `read_bounded` returns `None` for a file that is *larger* than the limit — deliberately, so the two cases cannot be confused. `conversation()` maps that `None` to "no conversation", which is the same answer it gives for a fresh lineage, so at roughly a thousand resumes a lineage silently starts over with nothing in the record to say it happened. The `.bak` is what makes the write that replaces a conversation recoverable; `conversation_problem()` is what makes a refusal visible instead of silent.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_chassis.py`:

```python
def test_a_checkpoint_keeps_the_conversation_it_replaced(tmp_path):
    """The write that replaces a lineage's whole memory is the one write worth a fallback."""
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    first = [message("user", "hour one")]
    second = [message("user", "hour two")]
    carried.save_conversation(first)
    carried.save_conversation(second)

    assert carried.conversation() == second
    assert carried.backup_path.exists(), "the checkpoint it replaced was thrown away"
    assert chassis.read_json(carried.backup_path) == first


def test_a_checkpoint_write_that_fails_leaves_the_last_one_readable(tmp_path, monkeypatch):
    """The write that replaces a lineage's whole memory is the one write that must not lose it.

    Renaming the checkpoint aside before writing the replacement leaves nothing
    at all when the write then fails -- and `conversation()` cannot tell that
    from a lineage that has never run.
    """
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    carried.save_conversation([message("user", "hour one")])
    carried.save_conversation([message("user", "hour two")])

    def explode(*_args, **_kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(chassis, "write_json_atomic", explode)

    with pytest.raises(OSError):
        carried.save_conversation([message("user", "hour three")])

    assert carried.conversation() == [message("user", "hour two")], (
        "the checkpoint vanished behind a failed write"
    )


def test_a_conversation_the_supervisor_moved_aside_is_not_resurrected(tmp_path):
    """The flap guard moves conversation.json and leaves everything else alone.

    The fallback is for a checkpoint that is there and unreadable. Treating a
    missing one as recoverable would undo the only reset the world had before
    this plan, and would undo the rung Task 11 adds.
    """
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    carried.save_conversation([message("user", "hour one")])
    carried.save_conversation([message("user", "hour two")])
    assert carried.backup_path.exists(), "the fixture needs a fallback to ignore"

    abandoned = tmp_path / "session" / "abandoned"
    abandoned.mkdir()
    carried.conversation_path.rename(abandoned / "conversation.json")

    assert carried.conversation() is None, "a conversation the ladder set aside came back"
    assert carried.conversation_problem() is None, "nothing was refused; it was moved"


def test_a_refused_checkpoint_falls_back_to_the_copy_it_replaced(tmp_path):
    """An unusable checkpoint is not the same thing as no history."""
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    carried.save_conversation([message("user", "hour one")])
    carried.save_conversation([message("user", "hour two")])
    carried.conversation_path.write_text("{ truncated", encoding="utf-8")

    assert carried.conversation() == [message("user", "hour one")]
    assert carried.recovered is True
    assert carried.conversation_problem() == "not json"


def test_an_unreadable_checkpoint_says_which_way_it_is_unreadable(tmp_path, monkeypatch):
    """A fresh lineage and a lost one look identical from inside a run."""
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    carried.session_dir.mkdir(parents=True, exist_ok=True)
    assert carried.conversation_problem() is None, "absent is not a problem, it is a beginning"

    for rubbish, expected in (
        ("not json at all", "not json"),
        ('{"not": "a list"}', "not a list of messages"),
        ("[1, 2, 3]", "a message with no role"),
        ('[{"no_role": true}]', "a message with no role"),
    ):
        carried.conversation_path.write_text(rubbish, encoding="utf-8")
        assert carried.conversation() is None
        assert carried.conversation_problem() == expected, rubbish

    # Oversized, without writing 64 MB to a test's temporary directory.
    monkeypatch.setattr(chassis, "CONVERSATION_LIMIT", 64)
    carried.conversation_path.write_text("x" * 65, encoding="utf-8")
    assert carried.conversation() is None
    assert "larger than" in carried.conversation_problem()


def test_a_checkpoint_drops_what_the_recap_already_holds(tmp_path):
    """`recap_folded` is the boundary: before it, the recap is the record.

    mackerel's checkpoint is 4.89 MB of messages the window stopped sending long
    ago, and it is re-serialised several times a turn. Past the reader's limit it
    is not slow, it is gone.
    """
    instance = object.__new__(chassis.Chassis)
    instance.slug, instance.name = "agent_1", "agent_1"
    instance.run_id, instance.turn, instance.model = "r1", 20, "stub"
    instance.entry = "/work/duty.py"
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.carried.session_dir.mkdir(parents=True, exist_ok=True)
    instance.messages = [message("system", "sys"), message("user", "opening")]
    instance.messages += [message("assistant", f"turn {index}") for index in range(20)]
    instance.recap_folded = 12
    instance.context_window = 100_000
    instance.usage_totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_prompt_tokens": 0,
    }
    instance.record = lambda *_args, **_kwargs: None

    chassis.Chassis.checkpoint(instance)

    stored = instance.carried.conversation()
    assert len(stored) == 12, f"the checkpoint kept {len(stored)} of 22"
    assert stored[0]["content"] == "sys", "a pinned message was pruned"
    assert stored[1]["content"] == "opening", "the opening problem was pruned"
    assert stored[-1]["content"] == "turn 19", "the newest message was pruned"
    assert instance.recap_folded == 2, "the fold pointer did not move with the list"


def test_pruning_keeps_what_the_recap_has_not_recorded(tmp_path):
    """Everything the recap has not seen stays, however old it is."""
    instance = object.__new__(chassis.Chassis)
    instance.slug, instance.name = "agent_1", "agent_1"
    instance.run_id, instance.turn, instance.model = "r1", 3, "stub"
    instance.entry = "/work/duty.py"
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.carried.session_dir.mkdir(parents=True, exist_ok=True)
    instance.messages = [message("user", f"turn {index}") for index in range(6)]
    instance.recap_folded = 0
    instance.context_window = 100_000
    instance.usage_totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_prompt_tokens": 0,
    }
    instance.record = lambda *_args, **_kwargs: None

    chassis.Chassis.checkpoint(instance)

    assert len(instance.carried.conversation()) == 6


def test_a_stale_fold_pointer_does_not_end_up_past_the_end(tmp_path):
    """`recap_folded` can outlive the conversation it indexed.

    A pointer left beyond the end of a shorter list makes every later fold slice
    an empty range, so the messages that should have been recorded as they fell
    out of the window are simply lost.
    """
    instance = object.__new__(chassis.Chassis)
    instance.slug, instance.name = "agent_1", "agent_1"
    instance.run_id, instance.turn, instance.model = "r1", 9, "stub"
    instance.entry = "/work/duty.py"
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.carried.session_dir.mkdir(parents=True, exist_ok=True)
    instance.messages = [message("assistant", f"turn {index}") for index in range(4)]
    instance.recap_folded = 9
    instance.context_window = 100_000
    instance.usage_totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_prompt_tokens": 0,
    }
    instance.record = lambda *_args, **_kwargs: None

    chassis.Chassis.checkpoint(instance)

    assert instance.recap_folded <= len(instance.messages), (
        f"the fold pointer sits at {instance.recap_folded} of {len(instance.messages)}"
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_chassis.py -q -k "keeps_the_conversation_it_replaced or refused_checkpoint or unreadable_checkpoint or drops_what_the_recap or keeps_what_the_recap"`
Expected: FAIL — `AttributeError: 'Carried' object has no attribute 'backup_path'`.

- [ ] **Step 3: Give the carry a limit, a fallback and a voice**

In `services/chassis.py`, beside `RECAP_MAX_BYTES`:

```python
# The largest conversation the runtime will read back. Over this, `read_bounded`
# refuses the file rather than loading it -- which is right, and is also why the
# refusal has to be visible: it used to be indistinguishable from a fresh start.
CONVERSATION_LIMIT = 64 * 1024 * 1024
```

Beside `Carried`:

```python
def _valid_messages(data) -> bool:
    """Whether a parsed checkpoint is a list of message-shaped mappings.

    A conversation that is not is worse than none: it would fail every request
    from here on, and the failure would look like a model fault.
    """
    return isinstance(data, list) and all(
        isinstance(message, dict) and isinstance(message.get("role"), str) for message in data
    )
```

Replace `Carried.__init__`'s path list and `conversation`/`save_conversation`:

```python
    def __init__(self, session_dir: Path, home_dir: Path) -> None:
        self.session_dir = session_dir
        self.home_dir = home_dir
        self.conversation_path = session_dir / "conversation.json"
        self.backup_path = session_dir / "conversation.previous.json"
        self.staged_path = session_dir / "conversation.staged.json"
        self.meta_path = session_dir / "run.json"
        self.recap_path = session_dir / "recap.md"
        self.handoff_path = home_dir / "HANDOFF.md"
        # Whether the last read came from a fallback rather than the checkpoint.
        self.recovered = False

    def conversation(self) -> list[dict] | None:
        """The checkpoint, or the copy that can stand in for it.

        Three states, and they are not the same state:

        * a checkpoint that reads -> that is the conversation;
        * a checkpoint that is *there* and unreadable -> the copy it replaced is
          tried, because a corrupt file is not the same thing as no history;
        * no checkpoint at all -> a staged one, if a write was interrupted
          between moving the old checkpoint aside and installing the new one;
          otherwise nothing, which is a fresh lineage or a conversation the
          supervisor deliberately set aside.

        The last case is why the fallback is not used for a missing checkpoint:
        the flap guard *moves* `conversation.json` to start a lineage over, and
        reading the previous copy then would resurrect the conversation the
        ladder just set aside. `self.recovered` says when a fallback was used.
        """
        self.recovered = False
        data = read_json(self.conversation_path, limit=CONVERSATION_LIMIT)
        if _valid_messages(data):
            return data
        if self.conversation_path.exists():
            fallback = read_json(self.backup_path, limit=CONVERSATION_LIMIT)
            if _valid_messages(fallback):
                self.recovered = True
                return fallback
        else:
            staged = read_json(self.staged_path, limit=CONVERSATION_LIMIT)
            if _valid_messages(staged):
                self.recovered = True
                return staged
        return None

    def conversation_problem(self) -> str | None:
        """Why the checkpoint could not be used, or None when there was nothing to use.

        A fresh lineage and a lost conversation are the same three lines of code
        from inside a run, and they are not the same event. This is what the
        record needs in order to say which one happened.
        """
        if not self.conversation_path.exists():
            return None
        raw = read_bounded(self.conversation_path, CONVERSATION_LIMIT)
        if raw is None:
            return f"larger than {CONVERSATION_LIMIT} bytes"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "not json"
        if not isinstance(data, list):
            return "not a list of messages"
        # A list of things that are not mappings is the same problem one level
        # down: whatever it is, it has no role to send.
        return "a message with no role" if not _valid_messages(data) else None

    def save_conversation(self, messages: list[dict]) -> None:
        """Write the checkpoint without ever leaving the lineage without one.

        The new conversation is written to a sibling first, the checkpoint it
        replaces is moved aside, and only then is the new one installed. That
        order matters more than it looks: renaming the checkpoint away *before*
        writing the replacement -- which is what this did in the first draft of
        this task -- leaves nothing readable at all if the write then fails, and
        the run after it reports a fresh lineage while a complete copy sits
        beside it. `conversation()` reads the staged file for exactly that case.
        """
        write_json_atomic(self.staged_path, messages)
        if self.conversation_path.exists():
            with contextlib.suppress(OSError):
                os.replace(self.conversation_path, self.backup_path)
        os.replace(self.staged_path, self.conversation_path)
```

`read_bounded` is already imported from `common`; add `read_json` to the same import if
it is not there.

**Where a reset's conversation goes.** `RunContext.reset()` empties the list and the
exit-path checkpoint writes it, so the copy that was there is renamed to
`conversation.previous.json` on the way past. The next run reads the empty checkpoint —
a valid, empty conversation — and never consults the fallback, so the reset is a reset;
what is left behind is for whoever wants to read what the run that ended itself was
thinking. That is the same bargain the supervisor's flap guard makes when it moves a
conversation into `session/abandoned/`.

- [ ] **Step 4: Prune before writing**

Beside `checkpoint`:

```python
    def prune(self) -> int:
        """Drop from the stored conversation what the recap already holds.

        `recap_folded` is the boundary: everything before it has been written
        into the recap, so the conversation no longer has to carry it. Pinned
        messages stay wherever they are -- they are sent on every request
        whatever their age -- and everything the recap has not seen stays too,
        because dropping it would drop the only copy.
        """
        boundary = min(self.recap_folded, len(self.messages))
        if boundary <= 0:
            return 0
        pinned = pinned_indices(self.messages)
        doomed = {index for index in range(boundary) if index not in pinned}
        if not doomed:
            return 0
        self.messages[:] = [
            message for index, message in enumerate(self.messages) if index not in doomed
        ]
        # `boundary`, not the pointer itself: a stale pointer from a longer
        # conversation would otherwise end up past the end of this one, and every
        # fold after it would slice an empty range.
        self.recap_folded = boundary - len(doomed)
        self.record("conversation_pruned", dropped=len(doomed), kept=len(self.messages))
        return len(doomed)
```

and call it first thing in `checkpoint`:

```python
    def checkpoint(self, ended: int | None = None) -> None:
        self.prune()
        self.carried.save_conversation(self.messages)
```

- [ ] **Step 5: Say when a conversation was refused or recovered**

In `Chassis.resume`, the check belongs immediately after the read, because that is
where the answer exists — a run that fell back to the previous checkpoint did read a
conversation, and a run that read nothing is the one that has to explain itself:

```python
        carried = self.carried.conversation()
        if carried is None:
            problem = self.carried.conversation_problem()
            if problem:
                self.record(
                    "conversation_refused",
                    reason=problem,
                    fallback=self.carried.backup_path.exists(),
                )
        elif self.carried.recovered:
            self.record("conversation_recovered", messages=len(carried))
        note = self.carried.handoff()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_chassis.py -q`
Expected: PASS, including the pre-existing `test_a_conversation_that_is_not_a_list_of_messages_is_refused`, which has no backup to fall back to and still reads as absent.

- [ ] **Step 7: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS. `tests/test_run_end_to_end.py` starts each run in a world whose `session/` is shared with the previous one, so the backup path is exercised across a real restart.

- [ ] **Step 8: Commit**

```bash
git add services/chassis.py tests/test_chassis.py
git commit -m "chassis: bound the checkpoint, and make losing one visible

checkpoint() wrote every message the run had ever held, including the ones
the window stopped sending thousands of turns ago: mackerel's file is 4.89 MB
and grows ~62 KB per resume, re-serialised several times a turn. Past the
reader's 64 MB limit read_bounded refuses the file, conversation() calls that
'no conversation', and the lineage silently starts over -- the same answer it
gives for a world that has never run.

What the recap already holds is now pruned before the write, the copy being
replaced is kept as conversation.previous.json, and a refusal or a recovery
is recorded rather than inferred.

Refs space_chassis-8c5e97f029

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 10: The list is a history, and the window is its end

**Files:**
- Modify: `services/chassis.py` (`Chassis.resume`; the `selection` docstring)
- Test: `tests/test_chassis.py`

**Interfaces:**
- Consumes: the `resume()` rewrite (Task 4) and the repair on load (Task 8).
- Produces: no new names. It pins an invariant the rest of the file already assumes.

**Why:** `selection` walks the message list backwards from the end and keeps the tail: the newest material is what the window is *for*. `resume()` puts new material at the front (`insert(0, ...)` for the note, and for the recap before Task 4), so every resume inverts the list it reasons about. The live lineages show the result exactly: `mackerel`'s handoff notes run newest at index 1 to oldest at index 142, and the window it built kept indices 147–217 of 218 — the agent's oldest material — while dropping the middle. `test_window_keeps_the_opening_and_the_system_message` asserts `sent[-1] is messages[-1]` under the comment "the newest message must always be sent", and after any resume that assertion was passing while meaning the opposite.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_chassis.py`:

```python
def test_a_resumed_conversation_is_in_the_order_it_happened(tmp_path):
    """insert(0, ...) is how the list stopped being a history.

    mackerel's handoff notes run newest at index 1 to oldest at index 142, and
    `selection` keeps the end of the list -- so the window it built preserved the
    agent's first hour and dropped its last.
    """
    instance = object.__new__(chassis.Chassis)
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.carried.session_dir.mkdir(parents=True, exist_ok=True)
    instance.carried.save_conversation(
        [message("user", "the opening problem"), message("assistant", "work")]
    )
    instance.carried.handoff_path.parent.mkdir(parents=True, exist_ok=True)
    instance.carried.handoff_path.write_text("carry on from where the last run stopped", encoding="utf-8")
    instance.messages = []
    instance.recap_folded = 0
    instance.context = None
    instance.record = lambda *_args, **_kwargs: None

    chassis.Chassis.resume(instance, {})

    contents = [str(m.get("content", "")) for m in instance.messages]
    assert contents[0] == "the opening problem", "the oldest thing said is the first thing held"
    assert contents[-1].startswith(chassis.HANDOFF_NOTE_PREFIX), (
        "the note is the newest thing said, so it is the last thing held"
    )


def test_the_window_keeps_the_newest_material_after_a_resume(tmp_path):
    """`selection` walks the list backwards, so the tail of the list is now.

    Anything that puts new material at the front turns the window inside out:
    the run reads its own first hour and loses the turn it just took.
    """
    instance = object.__new__(chassis.Chassis)
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.carried.session_dir.mkdir(parents=True, exist_ok=True)
    history = [message("system", "standing orders"), message("user", "the opening problem")]
    history += [message("assistant", f"turn {index} " + "x" * 400) for index in range(200)]
    instance.carried.save_conversation(history)
    instance.carried.handoff_path.parent.mkdir(parents=True, exist_ok=True)
    instance.carried.handoff_path.write_text("carry on", encoding="utf-8")
    instance.messages = []
    instance.recap_folded = 0
    instance.context = None
    instance.record = lambda *_args, **_kwargs: None

    chassis.Chassis.resume(instance, {})
    sent = chassis.prepared_view(instance.messages, 500, 100, instance.carried)

    assert sent[-1] is instance.messages[-1], "the newest message was not the one kept"
    assert any(m is instance.messages[-2] for m in sent), "the turn before the note was dropped"
    assert not any(m is instance.messages[10] for m in sent), "an old turn was kept instead"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_chassis.py -q -k "order_it_happened or newest_material_after_a_resume"`
Expected: FAIL — `AssertionError: the note is the newest thing said, so it is the last thing held`.

- [ ] **Step 3: Append the note instead of inserting it**

In `Chassis.resume`'s carried branch, replace the insert:

```python
            if note:
                # Appended, not inserted. `selection` keeps the tail of the list,
                # so new material at the front is material the window drops
                # first -- which is how the live lineages ended up reading their
                # first hour and forgetting their last.
                self.messages.append({"role": "user", "content": HANDOFF_NOTE_PREFIX + note})
                seeded_by_duty = True
```

- [ ] **Step 4: Write the invariant down where it is depended on**

In `selection`'s docstring, after the paragraph about the moving tail:

```
    The list is assumed to be in the order it happened, and the end of it is now:
    `resume()` appends to it and nothing anywhere inserts at the front. Every
    sentence above depends on that, and the one place it is easy to break is the
    line that puts a handoff note into a conversation.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_chassis.py -q`
Expected: PASS, including Task 4's `test_a_run_with_a_note_and_no_conversation_opens_on_the_brief_as_well`, which asserts the same ordering for the no-conversation case.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS. `tests/test_run_end_to_end.py::test_a_designed_handoff_carries_the_conversation_forward` resumes a real conversation and asserts the second run opened it.

- [ ] **Step 7: Commit**

```bash
git add services/chassis.py tests/test_chassis.py
git commit -m "chassis: keep the conversation in the order it happened

resume() inserted the handoff note at index 0, and selection keeps the tail of
the list -- so the window preserved the oldest material and dropped the recent
middle. mackerel's notes run newest at index 1 and the window it built kept
indices 147..217 of 218, the first hour of its life, while the turn before the
note was what went.

The note is appended, the invariant is written where it is depended on, and
two tests hold it for the resumed case as well as the fresh one.

Refs space_chassis-2b52aef053

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 11: The ladder sees a loop, and remembers it climbed

**Files:**
- Modify: `services/supervisor.py` (constants near line 67; `Supervisor.__init__` at 110; new `ladder_path`/`load_ladder`/`save_ladder`/`exhausted`; `Supervisor.decide` at 203; `Supervisor.run` at 344)
- Test: `tests/test_services.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `supervisor.RUNRATE_COUNT`, `RUNRATE_WINDOW`, `GIVE_UP_LIMIT`, `LADDER_STATE_FILE`; `Supervisor.runs`, `Supervisor.runrate_warned_at`, `Supervisor.give_ups`; `Supervisor.ladder_path()`, `load_ladder()`, `save_ladder()`, `exhausted() -> bool`; the `runrate` record event.

**Why:** the flap guard counts clean exits, and `decide()` returns early for exit 42 — the *designed* way for a run to end — clearing the failure history on the way past. So a lineage that hands off every few seconds is never a loop no matter how long it does it: the three lineages under `volumes/home/` wrote 66–77 handoff notes at 0–3 second intervals, each after "turn 1", and the record shows 9 handoffs and 2 environment pauses, every one of them a healthy decision.

**Why the ladder needs a memory:** `give_up` returns 1, and `containers/entrypoint.sh` sleeps sixty seconds and starts a *new* supervisor with `self.failures = []`. The ladder then resumes the same conversation, climbs the same four rungs and gives up again — the loop the ladder cannot see because it cannot remember. Counting give-ups in the agent's own telemetry directory is what makes the second one different from the first: by then the duty and the codebase have been restored twice and changed nothing, and the conversation is the only suspect left.

**What the rate guard is not:** it is a bound on churn, not a claim about how often a lineage *should* start a run. A fleet that hands off every eight seconds on purpose — because that is how it has decided to work — will warn once and see a second burst inside the same window; that second burst is what moves the conversation aside, and the move keeps the recap and the newest note. The guard says nothing about what a run is for, and nothing here is a substitute for the fleet deciding its own cadence.

This is the rung `space_chassis-835d551619` asks for, reached by evidence rather than by accident: the conversation is *moved*, never deleted, exactly as `resume_without_session()` already does, and the recap and the newest note survive it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_services.py`:

```python
def test_a_handoff_loop_is_a_loop_however_clean_each_run_looked(monkeypatch):
    """Exit 42 is exempt from the flap guard, and that exemption is the blind spot.

    The live lineages ran 66-77 times at 0-3 second intervals and not one of
    those runs was treated as a loop, because every exit was a designed end.
    """
    supervisor = supervisor_module.Supervisor()
    monkeypatch.setattr(supervisor_module, "RUNRATE_COUNT", 3)
    monkeypatch.setattr(supervisor_module, "RUNRATE_WINDOW", 300)

    actions = [supervisor.decide(supervisor_module.EXIT_HANDOFF)[0] for _ in range(6)]

    assert actions == [
        "resume",
        "resume",
        "resume",  # the window filled once: warned, and recorded
        "resume",
        "resume",
        "resume_without_session",  # it filled again: the conversation is the suspect
    ]


def test_a_lineage_running_at_a_human_pace_is_not_a_loop(monkeypatch):
    """The guard is a rate, not a count: the runs it must not touch are the slow ones."""
    supervisor = supervisor_module.Supervisor()
    monkeypatch.setattr(supervisor_module, "RUNRATE_COUNT", 3)
    monkeypatch.setattr(supervisor_module, "RUNRATE_WINDOW", 300)
    supervisor.runs = [time.time() - 3600, time.time() - 1800, time.time() - 900]

    action, _ = supervisor.decide(supervisor_module.EXIT_HANDOFF)

    assert action == "resume"


def test_a_restarted_supervisor_does_not_forget_the_ladder(tmp_path, monkeypatch):
    """The entrypoint starts a new process after every exhausted ladder."""
    monkeypatch.setattr(supervisor_module, "TELEMETRY_DIR", tmp_path)
    first = supervisor_module.Supervisor()
    first.give_ups = 1
    first.failures = [time.time()]
    first.save_ladder()

    second = supervisor_module.Supervisor()

    assert second.give_ups == 1, "a fresh process is a ladder that has forgotten itself"
    assert len(second.failures) == 1


def test_the_second_give_up_sets_the_conversation_aside_instead_of_exiting(tmp_path, monkeypatch):
    """After two exhausted ladders, the conversation is the only suspect left.

    The move keeps the recap and the newest note, so most of the memory survives
    it -- which is what makes this different from giving up on the lineage.
    """
    monkeypatch.setattr(supervisor_module, "TELEMETRY_DIR", tmp_path)
    supervisor = supervisor_module.Supervisor()
    supervisor.record = lambda *_args, **_kwargs: None
    monkeypatch.setattr(supervisor_module, "GIVE_UP_LIMIT", 2)

    assert supervisor.exhausted() is True, "the first exhausted ladder exits for the container"
    assert supervisor.exhausted() is False, "the second clears the conversation instead"
    assert supervisor_module.Supervisor().give_ups == 2, "the count did not outlive the process"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_services.py -q -k "handoff_loop or human_pace or restarted_supervisor or second_give_up"`
Expected: FAIL — `AttributeError: <module 'supervisor'> has no attribute 'RUNRATE_COUNT'`. The first failure is the monkeypatch, not the missing `self.runs`: `monkeypatch.setattr` refuses to create an attribute that does not exist, which is also a reminder that Steps 3 and 4 have to land before the tests can say anything.

- [ ] **Step 3: Add the constants**

In `services/supervisor.py`, beside `FLAP_WINDOW`. The import line needs **both**
`read_json` and `write_json_atomic` — it carries neither today, and `load_ladder` and
`save_ladder` use one each:

```python
from common import (  # noqa: E402
    append_jsonl,
    env_int,
    iso,
    read_json,
    write_json_atomic,
    write_text_atomic,
)
```

```python
# A run that starts again seconds later is not a lineage making progress, whatever
# its exit code said. Exit 42 -- the designed way for a run to end -- is exempt
# from the flap guard on purpose, so the flap guard cannot see this: the three
# lineages under volumes/home/ ran 66-77 times at 0-3 second intervals and not
# once was it treated as a loop.
RUNRATE_COUNT = env_int("SUPERVISOR_RUNRATE_COUNT", 10)
RUNRATE_WINDOW = env_int("SUPERVISOR_RUNRATE_WINDOW_SECONDS", 300)
# Give-ups are counted across supervisor restarts. The entrypoint starts a fresh
# supervisor after every exhausted ladder, and a fresh process with an empty
# failure list is a ladder that has forgotten it already gave up.
GIVE_UP_LIMIT = env_int("SUPERVISOR_GIVE_UP_LIMIT", 2)
LADDER_STATE_FILE = "ladder.json"
```

- [ ] **Step 4: Give the ladder a file**

In `Supervisor.__init__`, beside `self.failures`, then the three methods beside
`operations_size`:

```python
        self.runs: list[float] = []
        self.runrate_warned_at = 0.0
        self.give_ups = 0
        self.load_ladder()
```

```python
    # -- the ladder's memory ------------------------------------------------
    def ladder_path(self) -> Path:
        return TELEMETRY_DIR / "agents" / self.slug / LADDER_STATE_FILE

    def load_ladder(self) -> None:
        """What the last supervisor process knew, so the ladder does not restart with it."""
        data = read_json(self.ladder_path())
        if not isinstance(data, dict):
            return
        self.give_ups = int(data.get("give_ups", 0) or 0)
        self.failures = [
            float(stamp) for stamp in data.get("failures", []) if isinstance(stamp, (int, float))
        ]

    def save_ladder(self) -> None:
        with contextlib.suppress(OSError):
            write_json_atomic(
                self.ladder_path(),
                {"give_ups": self.give_ups, "failures": self.failures, "updated": iso()},
            )

    def exhausted(self) -> bool:
        """Whether an exhausted ladder exits, or sets the conversation aside instead.

        The first time, the container should decide: exiting is the honest answer
        for a ladder that has already restored the duty and the codebase. The
        second time, those restores have been done again and changed nothing, so
        the conversation is the only suspect left -- and it is set aside, as the
        flap guard already does, rather than exiting into a loop the entrypoint
        restarts sixty seconds later.
        """
        self.give_ups += 1
        self.save_ladder()
        return self.give_ups < GIVE_UP_LIMIT
```

- [ ] **Step 5: Count every run, not only the clean ones**

In `Supervisor.decide`, first move the two independent exit tests into the order the
guard needs. `EXIT_HANDOFF` is tested **before** `EXIT_ENVIRONMENT` today, and the
handoff branch returns `resume` immediately — so a guard placed after it would never
see a handoff loop, which is the only loop that matters here. Swap them (they cannot
both be true, so nothing else changes) and then put the guard between the environment
pause and the handoff branch.

At the top of `decide`, beside the two existing window prunes:

```python
        self.runs = [stamp for stamp in self.runs if now - stamp <= RUNRATE_WINDOW]
        self.runs.append(now)
```

Then, in place of the existing `if code == EXIT_HANDOFF:` block, this order:

```python
        if code == EXIT_ENVIRONMENT:
            self.record("environment", exit=code, pause=ENVIRONMENT_PAUSE)
            return "pause", 0

        if len(self.runs) >= RUNRATE_COUNT:
            self.runs.clear()
            if self.runrate_warned_at and now - self.runrate_warned_at <= RUNRATE_WINDOW:
                self.record(
                    "runrate",
                    exit=code,
                    runs=RUNRATE_COUNT,
                    seconds=RUNRATE_WINDOW,
                    action="resume_without_session",
                )
                self.save_ladder()
                return "resume_without_session", self.tier_for(len(self.failures))
            # Once is a burst. Warn, record it, and let the run it belongs to
            # finish deciding what to do; twice inside one window is a loop.
            self.runrate_warned_at = now
            self.record(
                "runrate", exit=code, runs=RUNRATE_COUNT, seconds=RUNRATE_WINDOW, action="warned"
            )

        if code == EXIT_HANDOFF:
            self.failures.clear()
            self.record("handoff", exit=code)
            return "resume", 0
```

The rest of the method — `EXIT_OK` and the failure ladder — is unchanged and still
runs after the guard. An environment pause is decided before the guard counts it,
because a run that paused is waiting on the world rather than looping.

- [ ] **Step 6: Escalate a repeated give-up**

In `Supervisor.run`'s loop, replace the `give_up` branch:

```python
            if action == "give_up":
                self.mirror()
                if self.exhausted():
                    self.record("give_up", tier=tier, give_ups=self.give_ups)
                    log("the ladder is exhausted; exiting for the container to decide")
                    return 1
                self.record(
                    "give_up", tier=tier, give_ups=self.give_ups, action="resume_without_session"
                )
                log("the ladder is exhausted again; setting the conversation aside")
                self.resume_without_session()
                continue
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_services.py -q`
Expected: PASS, including the pre-existing `test_repeated_clean_exits_are_treated_as_a_loop`, which fires three clean exits against a default `RUNRATE_COUNT` of ten and is untouched by the new guard.

- [ ] **Step 8: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS. The `Supervisor()` instances the tests build write their ladder file under the suite's temporary telemetry directories, and a missing one reads as a ladder that has never climbed.

- [ ] **Step 9: Commit**

```bash
git add services/supervisor.py tests/test_services.py
git commit -m "supervisor: see the loop a designed ending hides

decide() clears the failure history and resumes on exit 42, so a lineage that
hands off every three seconds is never a loop however long it does it: the
live lineages ran 66-77 times at 0-3 second intervals and the record calls
every one of them healthy.

Runs are now counted by rate whatever their exit code, warned once and then
answered with resume_without_session; the failure history and the give-up count
are written to the agent's telemetry directory so the supervisor the entrypoint
starts after an exhausted ladder is not a ladder with no memory; and a second
exhausted ladder sets the conversation aside instead of exiting into the same
sixty-second loop.

Refs space_chassis-835d551619, space_chassis-3cb643af8e, space_chassis-d96d548f41

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 12: Progress the supervisor can actually see

**Files:**
- Modify: `services/supervisor.py` (`INACTIVITY_SECONDS` at 67; `operations_size` at 152; `run_child` at 157)
- Modify: `containers/agent.env`, `.env.example` (line 79), `docker-compose.yml` (line 52)
- Test: `tests/test_services.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Supervisor.progress_size() -> int` (replacing `operations_size`); `SUPERVISOR_INACTIVITY_SECONDS` shipped as 900 everywhere.

**Why:** the watchdog measures progress by the growth of `operations.jsonl`, and the chassis writes that file only when a tool runs. The three lineages under `volumes/home/` called a tool five times each in their entire lives, and **all three have no `operations.jsonl` at all** — so the signal the supervisor waits on is not slow, it is absent, and a run that is thinking or retrying looks exactly like one that is wedged. `lifecycle.jsonl` grows on every turn (the chassis records one per turn), so it is the signal that was meant.

**Why the threshold moves too:** `space_chassis-420d18b7fa` states the case — 24 hours of silence is longer than the several-hour run it is watching, so an agent that wedges in its first hour burns a day of wall clock and its share of the hourly allowance before anything notices. The threshold belongs relative to the slowest legitimate turn, not to the length of a run: a model call is bounded by `RECORDER_TIMEOUT_SECONDS` (600 s default), so fifteen minutes is two timeouts and change.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_services.py`:

```python
def test_a_run_that_never_calls_a_tool_is_still_making_progress(tmp_path, monkeypatch):
    """Progress was measured by operations.jsonl, which is empty for the runs that need it.

    All three live lineages have no operations.jsonl: they called a tool five
    times each in their whole lives and handed off in between. To the supervisor
    they were indistinguishable from a run that had wedged on its first request.
    """
    monkeypatch.setattr(supervisor_module, "TELEMETRY_DIR", tmp_path)
    supervisor = supervisor_module.Supervisor()
    assert supervisor.progress_size() == 0

    supervisor.record("turn")

    assert supervisor.progress_size() > 0, "a run that is thinking looks wedged"


def test_the_inactivity_watch_is_shorter_than_the_runs_it_watches():
    """24 hours of silence is not a watchdog for a several-hour run.

    The threshold is set against the slowest legitimate turn -- a model call is
    bounded by the recorder's timeout -- not against the length of a run.
    """
    values = {}
    for name in ("containers/agent.env", ".env.example"):
        for line in (PROJECT / name).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("SUPERVISOR_INACTIVITY_SECONDS="):
                values[name] = int(line.partition("=")[2])

    assert set(values) == {"containers/agent.env", ".env.example"}, (
        f"the default is missing from {sorted(values)}"
    )
    assert len(set(values.values())) == 1, f"the two copies disagree: {values}"
    for name, seconds in values.items():
        assert 0 < seconds <= 3600, f"{name} waits {seconds}s of silence before acting"

    shipped = values[".env.example"]
    compose = (PROJECT / "docker-compose.yml").read_text(encoding="utf-8")
    assert f"SUPERVISOR_INACTIVITY_SECONDS: ${{SUPERVISOR_INACTIVITY_SECONDS:-{shipped}}}" in compose
    source = (PROJECT / "services" / "supervisor.py").read_text(encoding="utf-8")
    assert f'env_int("SUPERVISOR_INACTIVITY_SECONDS", {shipped})' in source, (
        "the code fallback and the shipped default have drifted apart"
    )
```

`containers/agent.env` does not carry a supervisor setting today; Step 3 adds
`SUPERVISOR_INACTIVITY_SECONDS=900` to it so the container copy says the same thing as the
operator's. If you would rather it not, drop it from the loop and assert the two places
that do carry it instead.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_services.py -q -k "never_calls_a_tool or inactivity_watch"`
Expected: FAIL — `AttributeError: 'Supervisor' object has no attribute 'progress_size'`.

- [ ] **Step 3: Count both records, and wait minutes rather than a day**

In `services/supervisor.py`, replace the constant and the method, and both of
`run_child`'s call sites:

```python
# How long a run may make no progress at all before it is ended. Measured against
# the slowest legitimate turn rather than the length of a run: one model call is
# bounded by RECORDER_TIMEOUT_SECONDS, so this is two timeouts and change. The
# old default was a day, which is longer than the runs it watches.
INACTIVITY_SECONDS = env_int("SUPERVISOR_INACTIVITY_SECONDS", 900)
```

```python
    def progress_size(self) -> int:
        """How much this run has written down since it started.

        Two files, because one of them is silent for exactly the runs that need
        watching: operations.jsonl grows only when a tool runs, and the three
        lineages under volumes/home/ called a tool five times each and have no
        operations.jsonl at all. lifecycle.jsonl grows on every turn, whether or
        not the model asked for anything.

        The supervisor appends to that same file, so it moves this number too --
        but it writes at run boundaries, when there is no child to watch, and a
        run that wedges between them moves neither file.
        """
        return sum(
            path.stat().st_size
            for path in (self.operations_path, self.record_path)
            if path.exists()
        )
```

In `run_child`, both `last_size = self.operations_size()` and `size = self.operations_size()`
become `self.progress_size()`, and the docstring's "Progress is measured by the
operations record growing" becomes "Progress is measured by either record growing: a turn
the model took is progress whether or not it called a tool."

Then the same 900 in the two shipped defaults:

```sh
# containers/agent.env, in the world-constants section
SUPERVISOR_INACTIVITY_SECONDS=900
```

```sh
# .env.example
# How long a run may make no progress at all before the supervisor ends it.
# Measured against the slowest legitimate turn, not the length of a run: one
# model call is bounded by the recorder's timeout.
SUPERVISOR_INACTIVITY_SECONDS=900
```

```yaml
# docker-compose.yml, the x-env anchor
  SUPERVISOR_INACTIVITY_SECONDS: ${SUPERVISOR_INACTIVITY_SECONDS:-900}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_services.py -q -k "never_calls_a_tool or inactivity_watch"`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS. `tests/conftest.py` already sets `SUPERVISOR_INACTIVITY_SECONDS=600` for the
end-to-end worlds, so nothing there waits longer than a test is willing to run.

- [ ] **Step 6: Commit**

```bash
git add services/supervisor.py containers/agent.env .env.example docker-compose.yml tests/test_services.py
git commit -m "supervisor: watch a signal that moves, and watch it sooner

Progress was measured by operations.jsonl, which the chassis writes only when a
tool runs. The three live lineages called a tool five times each and have no
operations.jsonl at all, so the watchdog they were under could never have fired
for the right reason. lifecycle.jsonl grows on every turn, so both records now
count.

The threshold follows: a day of silence is longer than the runs it watches. A
model call is bounded by the recorder's timeout, so the default is fifteen
minutes, shipped in all three places the value is decided.

Refs space_chassis-420d18b7fa

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 13: A recap that can be told what it is for

**Files:**
- Modify: `services/chassis.py` (`Carried.append_recap` at 145; new `Carried.set_recap`; `RunContext` at 291)
- Modify: `tasks/duty.py` (a tool beside `handoff`)
- Test: `tests/test_chassis.py`

**Interfaces:**
- Consumes: the `recap_folded` fix in `checkpoint` (Task 6).
- Produces: `Carried.set_recap(text) -> int`; `RunContext.rewrite_recap(text) -> str`; a `rewrite_recap` tool in the seed duty.

**Why:** the recap is the only record of everything the window has dropped, and it is sent with every request forever. Two things are wrong with it that the pointer fix does not reach:

*It repeats itself.* `resume()` read `recap_folded` from `run.json`, which nothing ever wrote, so every restart folded the same prefix again — which is why `mackerel`'s 96 KB recap holds far less history than 96 KB of history. Task 6 makes the pointer persist; this makes the file not depend on the pointer being right, because a duplicate line is a line that has stopped being a summary of anything.

*It can only grow.* `append_recap` is the only writer, so a run whose recap has saturated can watch it discard its own oldest material and has no way to say what the whole of it amounted to. `set_recap` is that lever, and the seed duty registers it so a model can reach it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_chassis.py`:

```python
def test_folding_the_same_message_twice_does_not_repeat_it(tmp_path):
    """The fold pointer was never persisted, so every restart folded the same prefix again.

    Task 6 fixes the pointer. The file should not depend on the pointer being
    right: a recap that repeats itself is not a smaller record, it is a worse one.
    """
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    lines = ["- [assistant] we chose the second option", "- [user] go"]

    carried.append_recap(lines)
    carried.append_recap(lines)

    assert carried.recap().count("we chose the second option") == 1
    assert carried.recap().count("- [user] go") == 1


def test_a_recap_can_be_rewritten_and_stays_under_its_cap(tmp_path):
    """The lever that lets a run say what its past amounted to instead of listing it."""
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    for index in range(200):
        carried.append_recap([f"- [assistant] event {index} " + "r" * 900])
    assert len(carried.recap().encode("utf-8")) <= chassis.RECAP_MAX_BYTES

    written = carried.set_recap("what mattered: we chose the second option\n")

    assert written == len("what mattered: we chose the second option\n")
    assert carried.recap().strip() == "what mattered: we chose the second option"

    written = carried.set_recap("r" * (chassis.RECAP_MAX_BYTES * 2))
    assert written <= chassis.RECAP_MAX_BYTES, "a rewrite is not allowed past the cap"


def test_a_run_can_rewrite_its_own_recap(tmp_path):
    instance = object.__new__(chassis.Chassis)
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.record = lambda *_args, **_kwargs: None
    instance.work_dir = instance.home_dir = instance.diary_dir = instance.duty_dir = tmp_path
    context = chassis.RunContext(instance, chassis.ToolRegistry())

    said = context.rewrite_recap("what mattered")

    assert "what mattered" in instance.carried.recap()
    assert said.startswith("recap rewritten"), said


def test_the_seed_duty_exposes_the_recap_lever():
    import sys

    sys.path.insert(0, str(PROJECT / "tasks"))
    import duty as duty_module

    assert "rewrite_recap" in duty_module.tools.tools
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_chassis.py -q -k "folding_the_same or rewritten_and_stays or rewrite_its_own_recap or recap_lever"`
Expected: FAIL — `AttributeError: 'Carried' object has no attribute 'set_recap'`.

- [ ] **Step 3: Dedupe the lines, and add the other direction**

In `Carried`, replace `append_recap` and add `set_recap`:

```python
    def append_recap(self, lines: list[str]) -> None:
        if not lines:
            return
        existing = self.recap()
        seen = set(existing.splitlines())
        # A line already in the recap is already reported. The fold pointer is
        # meant to prevent a second fold of the same message, and for as long as
        # run.json never carried `recap_folded` it did not -- so the file itself
        # is where a repeat has to be caught.
        fresh = [line for line in lines if line not in seen]
        if not fresh:
            return
        combined = (existing + "\n".join(fresh) + "\n").strip() + "\n"
        if len(combined.encode("utf-8")) > RECAP_MAX_BYTES:
            # Keep the newest material; the recap is a window too.
            encoded = combined.encode("utf-8")[-RECAP_MAX_BYTES:]
            combined = encoded.decode("utf-8", "ignore")
            combined = combined.split("\n", 1)[-1]
        write_text_atomic(self.recap_path, combined)

    def set_recap(self, text: str) -> int:
        """Replace the recap with `text`, keeping the newest end of it under the cap.

        The recap is the record of everything the window has dropped and it is
        sent on every request, so a run that can only append to it has a lever
        with one direction. This is the other one.
        """
        combined = text.strip() + "\n" if text.strip() else ""
        if len(combined.encode("utf-8")) > RECAP_MAX_BYTES:
            encoded = combined.encode("utf-8")[-RECAP_MAX_BYTES:]
            combined = encoded.decode("utf-8", "ignore").split("\n", 1)[-1]
        write_text_atomic(self.recap_path, combined)
        return len(combined)
```

- [ ] **Step 4: Put it on the context**

In `RunContext`, beside `set_history`:

```python
    def rewrite_recap(self, text: str) -> str:
        """Replace the recap of what has fallen out of the window with `text`.

        The recap is sent with every request and is the only record of the turns
        the window has dropped. Whatever is written here is all of it from now on.
        """
        chars = self._chassis.carried.set_recap(text)
        self._chassis.record("recap_rewrite", chars=chars)
        return f"recap rewritten: {chars} characters"
```

- [ ] **Step 5: Register it in the seed duty**

In `tasks/duty.py`, beside `handoff`:

```python
@tools.register
def rewrite_recap(text: str) -> str:
    """Replace the recap of what has fallen out of your context window.

    The recap is sent with every request and is the only record of the turns the
    window has dropped. What you write replaces all of it.

    Args:
        text: The recap, in full, as you want it kept.
    """
    if _context is None:
        return "error: this tool is only usable inside a run"
    return _context.rewrite_recap(text)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_chassis.py -q`
Expected: PASS, including the pre-existing `test_a_recap_that_outgrows_its_cap_keeps_the_newest_material`, which appends 200 distinct lines and so is untouched by the dedupe.

- [ ] **Step 7: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add services/chassis.py tasks/duty.py tests/test_chassis.py
git commit -m "chassis: let a run say what its recap is for

The recap is the only record of what the window dropped and it is sent on every
request. It repeated itself -- the fold pointer was never persisted, so every
restart folded the same prefix again -- and it could only grow, which is how a
96 KB recap came to hold far less history than 96 KB of history.

Repeated lines are dropped on the way in, and set_recap/rewrite_recap is the
lever that lets a run replace the whole of it. The seed duty registers it.

Refs space_chassis-1dca8e8841

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 14: A fresh conversation opens on what the lineage already knows

**Files:**
- Modify: `services/chassis.py` (a constant near line 84; new `Chassis.diary_tail`; `Chassis.resume`)
- Test: `tests/test_chassis.py`

**Interfaces:**
- Consumes: the ordering rule (Task 10); the `resume()` rewrite (Tasks 4 and 8).
- Produces: `chassis.DIARY_TAIL_CHARS`; `chassis.DIARY_TAIL_PREFIX`; `Chassis.diary_tail(limit_chars=DIARY_TAIL_CHARS) -> str`.

**Why:** every reset in the world is a step off a cliff. After `reset()` (Task 4), after the flap guard, and after the rung Task 11 adds, the conversation is gone and the next run opens on the bootstrap and a note — while the diary, which is the one thing the agent writes for itself and which survives every rung by design, goes unread. The note is one run's worth of memory; the diary is the lineage's. This is the difference between starting over and starting from nothing.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_chassis.py`:

```python
def test_a_fresh_conversation_opens_on_the_agents_own_diary(tmp_path, monkeypatch):
    """The brief says what the world is; the diary says what this lineage did.

    The diary is the one piece of memory that survives every reset, and nothing
    reads it back. A run that opens on the brief alone starts from nothing it did
    not already know.
    """
    import sys
    import types

    instance = object.__new__(chassis.Chassis)
    instance.carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance.diary_dir = tmp_path / "diary"
    instance.diary_dir.mkdir(parents=True, exist_ok=True)
    (instance.diary_dir / "diary.md").write_text(
        "## hour one\nwe chose the second option\n", encoding="utf-8"
    )
    instance.carried.handoff_path.parent.mkdir(parents=True, exist_ok=True)
    instance.carried.handoff_path.write_text("carry on from where the last run stopped", encoding="utf-8")
    instance.messages = []
    instance.recap_folded = 0
    instance.context = None
    instance.record = lambda *_args, **_kwargs: None

    duty = types.ModuleType("duty")
    duty.bootstrap = lambda _context: [
        {"role": "user", "content": "You are agent_1. Read the brief."}
    ]
    monkeypatch.setitem(sys.modules, "duty", duty)

    chassis.Chassis.resume(instance, {})

    contents = [str(m.get("content", "")) for m in instance.messages]
    assert any("Read the brief" in text for text in contents), "the opening was skipped"
    assert any("we chose the second option" in text for text in contents), "the diary was not read"
    assert contents[-1].startswith(chassis.HANDOFF_NOTE_PREFIX), "the note is the newest thing said"


def test_a_run_with_no_diary_opens_on_the_brief_alone(tmp_path):
    """A missing diary is not an empty message; it is nothing to say."""
    instance = object.__new__(chassis.Chassis)
    instance.diary_dir = tmp_path / "diary"

    assert chassis.Chassis.diary_tail(instance) == ""


def test_what_a_run_opens_on_is_bounded(tmp_path):
    """The diary is unbounded by design, and what a run reads back is not."""
    instance = object.__new__(chassis.Chassis)
    instance.diary_dir = tmp_path
    (tmp_path / "diary.md").write_text("x" * 1_000_000, encoding="utf-8")

    tail = chassis.Chassis.diary_tail(instance)

    assert tail, "a large diary should still yield its tail"
    assert len(tail) <= chassis.DIARY_TAIL_CHARS
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_chassis.py -q -k "opens_on_the_agents_own_diary or no_diary or opens_on_is_bounded"`
Expected: FAIL — `AttributeError: module 'chassis' has no attribute 'DIARY_TAIL_CHARS'`.

- [ ] **Step 3: Read the tail of the diary**

In `services/chassis.py`, beside `RECAP_MAX_BYTES`:

```python
# How much of the agent's own diary a run with no conversation opens on. The
# diary is the one piece of memory that survives every reset -- the conversation
# is moved aside, the recap can be cleared, the diary is the agent's own -- and it
# is read here in its tail, because the newest part of it is what a run needs to
# carry on from.
DIARY_TAIL_CHARS = 4_000
DIARY_TAIL_PREFIX = "The tail of your own diary, written by earlier runs of you:\n\n"
```

and beside `status`:

```python
    def diary_tail(self, limit_chars: int = DIARY_TAIL_CHARS) -> str:
        """The newest part of this agent's diary, or "" when there is not one.

        Read from the end and bounded: the diary grows for as long as the lineage
        lives, and what a run needs from it is the most recent part of it. It
        reads at most `limit_chars * 4` bytes, which is 16 KB against the 4 MB a
        `read_bounded` call is allowed -- the helper reads from the start of a
        file, and the end is the half worth having here.
        """
        path = self.diary_dir / "diary.md"
        limit_bytes = limit_chars * 4
        try:
            size = path.stat().st_size
            with open(path, "rb") as handle:
                if size > limit_bytes:
                    handle.seek(size - limit_bytes)
                raw = handle.read(limit_bytes)
        except OSError:
            return ""
        return raw.decode("utf-8", "ignore")[-limit_chars:]
```

- [ ] **Step 4: Open on it**

In `Chassis.resume`'s no-conversation branch, between the bootstrap and the note:

```python
        diary = self.diary_tail()
        if diary.strip():
            self.messages.append(
                {"role": "user", "content": DIARY_TAIL_PREFIX + diary}
            )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_chassis.py -q`
Expected: PASS, including `test_a_reset_clears_the_conversation_the_exit_path_would_otherwise_rewrite`
and Task 10's ordering tests.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS. `tests/test_run_end_to_end.py` writes diary entries through the stub, so the
opening it produces for a world that has run before is now three messages rather than two.

- [ ] **Step 7: Commit**

```bash
git add services/chassis.py tests/test_chassis.py
git commit -m "chassis: open a fresh conversation on what the lineage already knows

Every reset was a cliff: the conversation is moved, the recap can be cleared,
and the next run opened on the brief alone while the diary -- the one piece of
memory that survives every rung, written by the agent for itself -- went
unread. The note is one run's worth of memory; the diary is the lineage's.

A run with no conversation now opens on the bootstrap, the tail of its own
diary, and the note, in that order, with the tail read from the end and bounded.

Refs space_chassis-60a9b11711

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 15: Ship the budgets, and let a budget stop leave a note

**Files:**
- Modify: `containers/agent.env`, `.env.example`, `docker-compose.yml` (the `x-env` anchor)
- Modify: `services/chassis.py` (`Chassis.run`'s budget branches at 782; new `Chassis.budget_note`)
- Test: `tests/test_services.py`, `tests/test_run_end_to_end.py`

**Interfaces:**
- Consumes: `Chassis.tail_room` (Task 1); the `write_handoff` that already exists.
- Produces: `RUN_MAX_TURNS=400` and `RUN_MAX_SECONDS=21600` shipped in all three files; `Chassis.budget_note() -> str`; a handoff note written when a run stops on a budget.

**Why the budgets:** the machinery is built, tested, and switched off. `TurnLimitReached` and `WallLimitReached` map to `EXIT_HANDOFF`, which resumes the lineage and does not climb the ladder — and both defaults ship empty, so a run ends only when it ends itself or when something breaks it. The difference matters at the far end: a run that stops on a budget exits 42 with its conversation intact, while a run that runs into the window exits 43 and climbs a ladder that, on the evidence in `volumes/home/`, ends in `give_up`. Converting deaths into handoffs is the cheapest endurance in this plan.

Six hours and four hundred turns are operator settings, not laws, and they are not claims about how work should be paced. What they are for: a lineage that checkpoints itself at a known cadence hands over deliberately instead of running until something breaks it, and a run bounded this way is resumable — exit 42 — where a run that runs into the window is a fault that climbs the ladder. The turn bound exists because a cheap turn is the one failure a wall clock cannot catch. A host that measures its own cadence and wants different numbers sets `HOSTn_*` for its agent; a fleet that wants a different rhythm changes them without touching anything else in this plan.

**Why the note:** a budget stop is a designed end, and the note is the whole of what carries across it — but `run()` only ever put it in the record. `write_handoff` is what the next run reads, and it was never called on this path, so the run after a budget stop opened on the handoff from two runs ago.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_services.py`:

```python
def test_the_shipped_run_budgets_are_on():
    """A lineage that stops itself at a known cadence is a lineage that resumes.

    Both budgets shipped empty, so a run ended only when it ended itself or when
    something broke it -- and something breaking it is what climbs the ladder.
    """
    values = {}
    for name in ("containers/agent.env", ".env.example"):
        for line in (PROJECT / name).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(("RUN_MAX_TURNS=", "RUN_MAX_SECONDS=")):
                key, _, value = line.partition("=")
                values[key] = value

    assert set(values) == {"RUN_MAX_TURNS", "RUN_MAX_SECONDS"}, f"missing from a shipped file: {values}"
    turns, seconds = int(values["RUN_MAX_TURNS"]), int(values["RUN_MAX_SECONDS"])
    assert 0 < turns <= 10_000, f"{turns} turns is not a bound a run can reach"
    assert 0 < seconds <= 86_400, f"{seconds}s is a day or more, which is what this replaces"

    compose = (PROJECT / "docker-compose.yml").read_text(encoding="utf-8")
    assert f"RUN_MAX_TURNS: ${{RUN_MAX_TURNS:-{turns}}}" in compose
    assert f"RUN_MAX_SECONDS: ${{RUN_MAX_SECONDS:-{seconds}}}" in compose
```

Add to `tests/test_run_end_to_end.py`:

```python
def test_a_run_stopped_by_its_budget_leaves_the_next_one_a_note(world, stack_of):
    """A budget stop is a designed end, so it mustn't look like a crash to the run after it.

    The note went to the record and nowhere else, so the run that followed opened
    on the handoff from two runs ago -- and the run after a budget stop is the one
    most likely to need to know why the last one ended.
    """
    stack = stack_of(deliberate_script())

    result = stack.run_chassis(extra_env={"RUN_MAX_TURNS": "1"})

    assert result.returncode == 42, result.stderr[-400:]
    note = (world.home / "HANDOFF.md").read_text(encoding="utf-8")
    assert "turn" in note, f"the budget stop left no note: {note!r}"
    assert "room left" in note, f"the note does not say what the run had: {note!r}"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_services.py tests/test_run_end_to_end.py -q -k "shipped_run_budgets or stopped_by_its_budget"`
Expected: FAIL — `KeyError: 'RUN_MAX_TURNS'` in `tests/test_services.py`, and `FileNotFoundError` for the note in `tests/test_run_end_to_end.py`.

- [ ] **Step 3: Ship the numbers**

```sh
# containers/agent.env, replacing the two empty lines under the window section
# A run of the duty ends at either of these and the supervisor starts another.
# A budget stop is a designed end: exit 42, the conversation resumes, and the
# note says why. Six hours and four hundred turns are long enough for a session
# of work and short enough that a lineage checkpoints itself at a known cadence.
RUN_MAX_TURNS=400
RUN_MAX_SECONDS=21600
```

```sh
# .env.example, replacing the commented pair under --- how a run ends ---
# A run ends at the first of these and another starts in the same home. A budget
# stop is a designed end: the conversation resumes and the handoff note says why.
# Set either to empty for a run that ends only when it ends itself.
RUN_MAX_TURNS=400
RUN_MAX_SECONDS=21600
```

```yaml
# docker-compose.yml, the x-env anchor
  RUN_MAX_TURNS: ${RUN_MAX_TURNS:-400}
  RUN_MAX_SECONDS: ${RUN_MAX_SECONDS:-21600}
```

- [ ] **Step 4: Write the note a budget stop owes the next run**

In `services/chassis.py`, beside `write_handoff`:

```python
    def budget_note(self) -> str:
        """What a run that stopped on a budget owes the run that follows it.

        A budget stop is a designed end, so this note is the whole of what carries
        across it: how far this run got, what it spent, and how much window it had
        left. It says what happened, not what to do about it.
        """
        spent = self.usage_totals.get("prompt_tokens", 0) + self.usage_totals.get("completion_tokens", 0)
        left = max(0, self.tail_room() - estimate_tokens(self.messages))
        return (
            f"This run stopped on a budget after {self.turn} turn(s), having spent about "
            f"{spent} tokens. It had about {left} estimated tokens of room left in the window."
        )
```

and in `Chassis.run`, both budget branches:

```python
        except TurnLimitReached as reached:
            exit_code, note = EXIT_HANDOFF, str(reached)
            self.write_handoff(f"{note}. {self.budget_note()}")
        except WallLimitReached as reached:
            exit_code, note = EXIT_HANDOFF, str(reached)
            self.write_handoff(f"{note}. {self.budget_note()}")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_services.py tests/test_run_end_to_end.py -q`
Expected: PASS, including `test_a_turn_limit_ends_a_run_without_ending_the_lineage`, which already asserts the exit code and the surviving conversation.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS. Every end-to-end world is given `RUN_MAX_TURNS`/`RUN_MAX_SECONDS` by
`containers/agent.env` only in a container; the suite's worlds set their own environment, so
the scripted runs are unaffected.

- [ ] **Step 7: Commit**

```bash
git add containers/agent.env .env.example docker-compose.yml services/chassis.py tests/test_services.py tests/test_run_end_to_end.py
git commit -m "world: bound a run by design, and let the bound leave a note

TurnLimitReached and WallLimitReached already map to exit 42, which resumes the
lineage instead of climbing the ladder, and both budgets shipped empty -- so a
run ended only when it ended itself or when something broke it, and something
breaking it is the path that reaches give_up.

Six hours and four hundred turns, in the three files that decide them. And a
run that stops on a budget now writes the handoff note the next run reads: it
went to the record and nowhere else, so the run after a budget stop opened on
the note from two runs ago.

Refs space_chassis-80382730d2

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 16: A lineage an operator can see

**Files:**
- Modify: `scripts/status.py` (`agent_row` at 106; `render` at 165; new `recent`)
- Test: `tests/test_observer.py`

**Interfaces:**
- Consumes: the `turn` record's `actual_prompt_tokens` and `cached_prompt_tokens` (Task 2); the ladder file (Task 11).
- Produces: `status.recent(records, seconds) -> int`; the `runs_last_hour`, `conversation_bytes`, `tokens_per_turn`, `cache_pct` and `give_ups` row keys, and their columns.

**Why:** nothing in this plan is visible while it is happening. The record from the live fleet says nine handoffs and two pauses in two and a half minutes — every decision a healthy one — while the conversation grew to 4.89 MB and the window it was sent into was 200k tokens. Answering "is this lineage working or spinning?" meant reading `conversation.json` by hand and comparing handoff-note timestamps. `agent_row` already reads the record and already has turns, runs, resumed and the last exit; what it lacks is a *rate*, what a turn costs, how much of the prompt came from cache, how many times the ladder gave up, and the size of the file that hits the reader's own limit at 64 MB.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_observer.py`:

```python
def test_the_status_reader_shows_the_lineage_not_only_the_run(tmp_path, monkeypatch):
    """One run's numbers cannot show a lineage that spends without progressing.

    The live fleet's record read as healthy -- nine decided handoffs, two
    environment pauses -- while it ran eleven times in two and a half minutes and
    its checkpoint grew to 4.89 MB. A rate, a cost per turn, a cache share, a
    ladder count and the size of the conversation are what make that visible
    without reading the files by hand.
    """
    from datetime import datetime, timedelta, timezone

    root = build_world(tmp_path / "volumes", ["agent_1"])
    monkeypatch.setenv("SC_VOLUMES", str(root))

    import status as status_module  # noqa: PLC0415 -- imported after the env is set

    monkeypatch.setattr(status_module, "VOLUMES", root)

    telemetry = root / "telemetry" / "agents" / "agent_1"
    now = datetime.now(timezone.utc)
    records = [
        {"event": "run_start", "at": (now - timedelta(minutes=30)).isoformat()},
        {
            "event": "turn",
            "at": (now - timedelta(minutes=29)).isoformat(),
            "actual_prompt_tokens": 1000,
            "cached_prompt_tokens": 900,
        },
        {
            "event": "turn",
            "at": (now - timedelta(minutes=28)).isoformat(),
            "actual_prompt_tokens": 3000,
            "cached_prompt_tokens": 1500,
        },
        {"event": "run_end", "at": (now - timedelta(minutes=27)).isoformat(), "exit": 42},
    ]
    (telemetry / "lifecycle.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )
    (telemetry / "ladder.json").write_text(json.dumps({"give_ups": 2}), encoding="utf-8")

    row = status_module.agent_row("agent_1", status_module.roster())

    assert row["runs_last_hour"] == 1
    assert row["tokens_per_turn"] == 2000
    assert row["cache_pct"] == 60, "2400 of 4000 prompt tokens were served from cache"
    assert row["give_ups"] == 2
    assert row["conversation_bytes"] == 1000

    rendered = status_module.render([row], verbose=True)
    assert "runs/h" in rendered
    assert "cache" in rendered
    assert "give-up" in rendered
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_observer.py -q -k "lineage_not_only_the_run"`
Expected: FAIL — `KeyError: 'runs_last_hour'`.

- [ ] **Step 3: Read the rate, the cost and the ladder**

In `scripts/status.py`, at the top beside the other helpers:

```python
def recent(records: list[dict], seconds: int) -> int:
    """How many of these records are newer than the window, by their own clock.

    A rate is the number that separates a working lineage from a spinning one:
    the live fleet's record showed nine handoffs in two and a half minutes, and
    every one of them was a healthy decision.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    count = 0
    for record in records:
        stamp = record.get("at")
        if not isinstance(stamp, str):
            continue
        try:
            at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        count += 1 if at >= cutoff else 0
    return count
```

with `from datetime import datetime, timedelta, timezone` added to the imports, and in
`agent_row`, beside `run_ends`:

```python
    starts = [record for record in decisions if record.get("event") == "run_start"]
    turns = [record for record in decisions if record.get("event") == "turn"]
    prompted = [
        record.get("actual_prompt_tokens") or record.get("estimated_prompt_tokens") or 0
        for record in turns
    ]
    cached = [record.get("cached_prompt_tokens") or 0 for record in turns]
    ladder = read_json(telemetry / "ladder.json") or {}
```

and in the returned dictionary:

```python
        # Rate, cost and the two things that decide whether a lineage has room:
        # what a turn spends, and how big the conversation it sends has become.
        "runs_last_hour": recent(starts, 3600),
        "conversation_bytes": size_of(home / "session" / "conversation.json"),
        "tokens_per_turn": (sum(prompted) // len(prompted)) if prompted else None,
        "cache_pct": round(100 * sum(cached) / sum(prompted)) if sum(prompted) else None,
        "give_ups": ladder.get("give_ups") if isinstance(ladder.get("give_ups"), int) else None,
```

- [ ] **Step 4: Show them**

In `render`, add the columns to the header and the row, and the ladder to the verbose
line:

```python
    lines = [
        f"{'agent':<9}  {'name':<{width}}  {'turns':>6}  {'runs':>5}  {'runs/h':>6}  "
        f"{'res':>4}  {'ctx%':>5}  {'conv':>9}  {'tok/t':>7}  {'cache':>5}  "
        f"{'diary':>7}  {'out':>4}  {'window':<6} last"
    ]
```

```python
        lines.append(
            f"{row['agent']:<9}  {row['name'] or '-':<{width}}  {row['turns']:>6}  "
            f"{row['runs']:>5}  {row['runs_last_hour']:>6}  {row['resumed']:>4}  "
            f"{row['context_pct'] if row['context_pct'] is not None else '-':>5}  "
            f"{row['conversation_bytes']:>9}  "
            f"{row['tokens_per_turn'] if row['tokens_per_turn'] is not None else '-':>7}  "
            f"{row['cache_pct'] if row['cache_pct'] is not None else '-':>5}  "
            f"{row['diary_bytes']:>7}  {row['results']:>4}  "
            f"{'yes' if row['window_ready'] else 'no':<6} {row['last_end']}"
        )
```

```python
            lines.append(
                f"{'':<9}  exits: {history or '-'} | pump: {pump} | "
                f"handoff: {'yes' if row['handoff'] else 'no'} | recap: {row['recap_bytes']}b | "
                f"ladder: {row['give_ups'] if row['give_ups'] is not None else 0} give-up(s)"
            )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_observer.py -q`
Expected: PASS, including `test_the_status_reader_reports_from_the_record`, whose row now
carries five more keys and whose rendered output still contains the name and the note.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Look at the fleet as it is now**

Run: `python3 scripts/status.py --verbose`
Expected: one line per agent in `volumes/`, with the three stranded lineages showing their
conversation size, their run rate and their ladder count — the numbers that were invisible
until they were read by hand.

- [ ] **Step 8: Commit**

```bash
git add scripts/status.py tests/test_observer.py
git commit -m "status: show the lineage, not only the run

The reader had turns, runs, resumed and the last exit, and the live fleet read
as healthy through all of it: nine decided handoffs and two environment pauses
while it ran eleven times in two and a half minutes and its checkpoint grew to
4.89 MB. Seeing that meant reading conversation.json by hand.

A rate, a cost per turn, the cache share, the ladder's give-up count and the
size of the conversation are now columns, all of them read from the record.

Refs space_chassis-13599e63b4

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

### Task 17: Let the records end, without ending the history

**Files:**
- Modify: `services/common.py` (beside `append_jsonl` at 121)
- Modify: `services/chassis.py` (`Chassis.record`, `Chassis.operation`), `services/supervisor.py` (`Supervisor.record`), `services/fleet_monitor.py` (its `append_jsonl` call)
- Modify: `scripts/status.py` (`agent_row`'s read)
- Test: `tests/test_services.py`, `tests/test_observer.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `common.ROTATE_BYTES`; `common.rotate_jsonl(path, max_bytes=ROTATE_BYTES) -> bool`; readers that read `<name>.1<ext>` as well as the live file.

**Why:** this is the smallest item in the revision and the one with the longest horizon. `append_jsonl` is deliberately append-only — "a record of what happened is not something a later event should rewrite" — and it never ends: `lifecycle.jsonl`, `operations.jsonl` and `fleet.jsonl` grow for as long as the world runs. Reads are already bounded (`tail_jsonl`), so nothing breaks at a year; what breaks is a directory that has to be explained to whoever finds it. Rotation is not rewriting: the file is *renamed*, and one generation is kept beside the live one, so both the operator's history and the append-only property survive. The readers change with it, or a rotation would look like an agent that has never run.

- [ ] **Step 1: Write the failing tests**

The first two go in `tests/test_services.py`; the third, which needs the status reader,
goes in `tests/test_observer.py` beside the other reader tests:

```python
def test_a_record_that_outgrows_its_cap_keeps_the_last_generation(tmp_path):
    """Append-only is the point; unbounded is not.

    The file is renamed rather than truncated: what a reader loses is bounded and
    old, and what an operator loses is nothing, because both files are still
    there to be read.
    """
    from common import append_jsonl, rotate_jsonl, tail_jsonl

    path = tmp_path / "lifecycle.jsonl"
    for index in range(50):
        append_jsonl(path, {"index": index})
    size = path.stat().st_size

    assert rotate_jsonl(path, max_bytes=size - 1) is True
    assert not path.exists(), "the live file was not moved aside"
    rotated = tmp_path / "lifecycle.1.jsonl"
    assert len(tail_jsonl(rotated, max_bytes=1 << 20)) == 50, "history was dropped, not moved"

    append_jsonl(path, {"index": 50})
    assert [record["index"] for record in tail_jsonl(path, max_bytes=1 << 20)] == [50]


def test_a_record_under_its_cap_is_left_exactly_where_it_is(tmp_path):
    from common import append_jsonl, rotate_jsonl

    path = tmp_path / "lifecycle.jsonl"
    append_jsonl(path, {"index": 0})

    assert rotate_jsonl(path, max_bytes=1 << 20) is False
    assert path.exists()
    assert not (tmp_path / "lifecycle.1.jsonl").exists()
```

```python
def test_the_status_reader_still_sees_the_generation_before_a_rotation(tmp_path, monkeypatch):
    """A rotation that read as a fresh lineage would be worse than the growth."""
    root = tmp_path / "volumes"
    (root / "work").mkdir(parents=True)
    (root / "work" / "roster.json").write_text('{"agents": []}\n', encoding="utf-8")
    (root / "home" / "agent_1" / "session").mkdir(parents=True)
    telemetry = root / "telemetry" / "agents" / "agent_1"
    telemetry.mkdir(parents=True)
    (telemetry / "lifecycle.1.jsonl").write_text(
        json.dumps({"event": "run_start"}) + "\n", encoding="utf-8"
    )
    (telemetry / "lifecycle.jsonl").write_text(
        json.dumps({"event": "run_start"}) + "\n"
        + json.dumps({"event": "run_end", "exit": 42}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SC_VOLUMES", str(root))

    import status as status_module  # noqa: PLC0415 -- imported after the env is set

    monkeypatch.setattr(status_module, "VOLUMES", root)

    row = status_module.agent_row("agent_1", status_module.roster())

    assert row["runs"] == 2, "the rotated generation was not read"
    assert row["last_end"] == 42
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_services.py tests/test_observer.py -q -k "outgrows_its_cap or under_its_cap or generation_before_a_rotation"`
Expected: FAIL — `ImportError: cannot import name 'rotate_jsonl' from 'common'`.

- [ ] **Step 3: Add the rotation**

In `services/common.py`, beside `append_jsonl`:

```python
# How large a record may grow before the generation before it is set aside. The
# files are append-only and each event is small, so this is a horizon rather than
# a limit: a year of turns is a few megabytes.
ROTATE_BYTES = 8 * 1024 * 1024


def rotate_jsonl(path: Path, max_bytes: int = ROTATE_BYTES) -> bool:
    """Move a record aside when it has outgrown its cap, and say whether it did.

    Renamed, never truncated: `<name>.1<ext>` holds the generation that was live,
    the live file starts again, and both are readable. Append-only is preserved
    because nothing edits a record -- the whole file moves.
    """
    try:
        if path.stat().st_size <= max_bytes:
            return False
    except OSError:
        return False
    rotated = path.with_name(f"{path.stem}.1{path.suffix}")
    try:
        os.replace(path, rotated)
    except OSError:
        return False
    return True
```

- [ ] **Step 4: Rotate before every append**

In `Chassis.record` and `Chassis.operation`, before `append_jsonl`:

```python
            rotate_jsonl(self.lifecycle_path)
```
```python
            rotate_jsonl(self.operations_path)
```

In `Supervisor.record`, before `append_jsonl`:

```python
            rotate_jsonl(self.record_path)
```

In `services/fleet_monitor.py`, before its `append_jsonl(FLEET_PATH, ...)`:

```python
        rotate_jsonl(FLEET_PATH)
```

Each of these is inside the existing `contextlib.suppress(OSError)` / `try`, so a
rotation that fails is contained exactly as an append that fails is.

- [ ] **Step 5: Read both generations**

In `scripts/status.py`'s `agent_row`, extend both reads. The live file is the newest
generation, but between a rotation and the next append it is empty — so the reader falls
back to the one beside it rather than reporting an agent that has never run:

```python
    decisions = tail_jsonl(telemetry / "lifecycle.jsonl", max_bytes=256 * 1024) + tail_jsonl(
        telemetry / "lifecycle.1.jsonl", max_bytes=64 * 1024
    )
```

```python
    ended = last_event(telemetry / "lifecycle.jsonl") or last_event(telemetry / "lifecycle.1.jsonl")
```

In `common.tail_jsonl`'s callers elsewhere nothing changes: a reader that wants the
current state reads the live file, which is the newest generation by construction.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_services.py tests/test_observer.py -q`
Expected: PASS.

- [ ] **Step 7: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add services/common.py services/chassis.py services/supervisor.py services/fleet_monitor.py scripts/status.py tests/test_services.py
git commit -m "records: rotate the append-only files and read both generations

lifecycle.jsonl, operations.jsonl and fleet.jsonl grow for as long as the world
runs. Reads were already bounded, so nothing broke -- but a record that never
ends is a directory somebody has to explain.

Rotation renames the file and keeps one generation beside it, so the
append-only property holds and no history is edited away; the supervisor, the
chassis, the monitor and the status reader all know about the sibling.

Refs space_chassis-639443e993

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XcxR6BZekMUeEuzX41eSZo"
```

---

## Verification

After Task 17, all of this must hold:

```bash
python3 -m pytest -q                                    # whole suite green
uvx ruff check . --no-cache                             # clean
uvx ruff format --check . --no-cache                    # clean, once docs/ is excluded
docker compose --profile fleet config -q                # topology still parses
python3 endurance/run_local.py endurance/scenarios/short.json   # end to end
python3 scripts/status.py --verbose                     # the lineage columns exist
```

`uvx ruff format --check .` refuses this plan's own markdown: ruff formats Python
blocks inside Markdown, and the long one-liners in the snippets above are not what
it would write. Either run `uvx ruff format` over this file as the last step, or add
`"docs/superpowers/plans"` to `[tool.ruff] exclude` in `pyproject.toml` — with a
comment saying why, because a formatter that rewrites a plan's code blocks is a
formatter that can silently disagree with the code the plan produced.

Then the same check against the live world, which is the point of Tasks 8–12:

```bash
python3 - <<'PY'
import json, pathlib, sys
sys.path.insert(0, "services")
import chassis
for home in sorted(pathlib.Path("volumes/home").glob("*")):
    conv = home / "session" / "conversation.json"
    if not conv.exists():
        continue
    messages = json.loads(conv.read_text())
    repaired, removed = chassis.repair_messages(messages, keep_recap=True, keep_note=True)
    sent = chassis.prepared_view(repaired, 160_000, None, chassis.Carried(conv.parent, home), 2_000, 8_000)
    print(f"{home.name}: {len(messages)} -> {len(repaired)} messages, {removed}, "
          f"{chassis.estimate_tokens(sent)} estimated tokens shipped")
PY
```

Expected: every lineage well under the window, at most one recap and one note kept,
and an empty `removed` count for orphaned calls only if those conversations were
already repaired by a run. Before this plan the same three files ship 0.94–1.23 M
estimated tokens into a 200k window.

Then update the tickets:

```bash
filigree --actor claude close space_chassis-8da4399e69 --reason="One budget now covers the recap, the tool schemas and the reply reserve; prepared_view drops the recap copies earlier runtimes stored, and fold_recap_if_needed agrees on the edge."
filigree --actor claude close space_chassis-29d9c64d2d --reason="Cache hits and estimate-vs-actual prompt tokens are recorded on every turn event, and the status reader shows the cache share."
filigree --actor claude close space_chassis-3c98f068b5 --reason="Window set to 160k beneath a declared 200k ceiling in the container copy, the operator's defaults and the compose anchor; the relationship is pinned by test_the_shipped_window_leaves_room_beneath_the_models_real_ceiling."
filigree --actor claude close space_chassis-a5c2a27876 --reason="RunContext.reset() ends the conversation and survives the exit-path checkpoint; a conversation-less run opens on the brief, the diary tail and the note, in that order."
filigree --actor claude close space_chassis-bbe02a114d --reason="RunContext.compact() replaces the middle over set_history, guarding tool-call pairing and the recap boundary."
filigree --actor claude close space_chassis-f83364fe22 --reason="status() reports burn rate, runway, window composition, recap saturation and how the previous run ended, carried in memory so it survives the run's own first checkpoint."
filigree --actor claude close space_chassis-3622348dc9 --reason="Tool output bounded with spill-to-file in the seed duty; compact, reset and rewrite_recap registered as tools."
filigree --actor claude close space_chassis-835d551619 --reason="A conversation that provokes a deterministic fault now has a rung that sets it aside: repair on load, pruning at the checkpoint, a run-rate guard that sees a handoff loop, and an escalation after a repeated exhausted ladder. The conversation is moved, never deleted."
filigree --actor claude close space_chassis-420d18b7fa --reason="Progress is measured by either record growing rather than by tool calls alone, and the inactivity default is fifteen minutes in all three places it is decided."
filigree --actor claude close space_chassis-80382730d2 --reason="RUN_MAX_TURNS=400 and RUN_MAX_SECONDS=21600 ship in the container copy, the operator's defaults and the compose anchor, and a budget stop now writes the handoff note the next run reads."
filigree --actor claude close space_chassis-aa9ac4ec84 --reason="resume() appends, so the list is the history it is read as; previous_run_ended is carried in memory rather than read from a file this run's own checkpoints overwrite."
```

And the nine filed for this revision, each closed by the task that implements it:

```bash
filigree --actor claude close space_chassis-f976098d48 --reason="turn_once writes the tool result before SystemExit travels, and resume() repairs a conversation it loads -- orphaned calls, stored recap copies and old notes -- recording what it removed."
filigree --actor claude close space_chassis-8c5e97f029 --reason="checkpoint() prunes what the recap already holds, every write stages the new conversation before installing it and keeps the one it replaced, and a refused or recovered checkpoint is recorded rather than inferred."
filigree --actor claude close space_chassis-2b52aef053 --reason="resume() appends the handoff note, so the list is the history selection() is written against; two tests pin the order and the window that follows from it."
filigree --actor claude close space_chassis-3cb643af8e --reason="Every run counts toward a rate whatever its exit code, the first burst warns and a second inside the window answers with resume_without_session, which moves the conversation and keeps the recap and the newest note."
filigree --actor claude close space_chassis-d96d548f41 --reason="Failures and a give-up count live in the agent's telemetry directory and are read at startup, so the first exhausted ladder exits and the second sets the conversation aside instead of looping."
filigree --actor claude close space_chassis-1dca8e8841 --reason="Repeated recap lines are dropped on the way in at any size, and set_recap/rewrite_recap plus a seed tool let a run replace the whole recap instead of only appending to it."
filigree --actor claude close space_chassis-60a9b11711 --reason="A run with no conversation opens on the bootstrap, the bounded tail of its own diary and the handoff note, in that order, and a world with no diary opens on the brief alone."
filigree --actor claude close space_chassis-13599e63b4 --reason="status.py carries runs/hour, the checkpoint's size, mean prompt tokens per turn, the cache share and the ladder's give-up count, all read from the record."
filigree --actor claude close space_chassis-639443e993 --reason="Records rotate to a sibling generation by rename, never truncation, and the status reader reads both generations so a rotation does not read as a lineage that has never run."
```

## What this plan does not settle

- **What the fleet is for.** Nothing here knows what any of this is in aid of, and that is the point rather than an omission. This plan is the substrate a lineage needs in order to keep running long enough to matter — honest numbers about its own context, memory that stays a size and in order, a ladder that can see a loop, and a record a person can read. The tooling for the actual work is the fleet's to design and build, before it starts and while it runs, and a change that only helps one particular job belongs on that side of the line. If a later revision of this plan finds itself tuning a threshold to a work rhythm, or adding a tool the fleet should have written for itself, it has left its scope.
- **When to compact or reset.** Deliberately absent. The chassis supplies levers and numbers; judging the moment is the fleet's, and the harness stays task-agnostic.
- **A conversation that arrives poisoned some other way than the three ways Tasks 8–10 know about.** They repair what the live fleet actually produced — orphaned calls, stored recaps, repeated notes — and Tasks 9 and 11 bound and clear the rest. A fourth shape nobody has seen yet still has to be found by reading the record, which is now the thing Task 16 makes readable.
- **Telling agents any of this exists.** The brief never mentions the context window (`space_chassis-a408dafc55`), and that ticket depends on this plan landing. Until it does, the levers exist and a run has to find them through its own `status` tool.
- **Reset or compaction directed by another agent.** Nothing here lets one agent reach into another's conversation; see the open question recorded on the epic.
- **The seed duty reaching a world that has already been seeded.** `tasks/duty.py` is copied into `/work` once (`.seeded`), so the tools Tasks 7 and 13 add reach a live fleet only through the supervisor's restore rung or the fleet's own rewrite. That is the world's design, not this plan's, but it means the new levers are not in the hands of the three stranded lineages until something restores the duty.
- **Pinned system messages other than the recap.** `RunContext.note()` appends a `system` message, and `selection` pins every system message forever. A duty that calls `note()` once a turn grows the pinned set without bound, exactly as the stored recap copies did. Nothing here bounds it, because nothing in the tree calls `note()` in a loop — it is the next footgun on this list, not this plan's.
