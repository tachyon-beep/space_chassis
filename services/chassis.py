#!/usr/bin/env python3
"""The runtime a run of the duty executes inside.

This process is the boundary between the world and whatever the fleet has
decided to be. It does six things and refuses to do a seventh:

  1. decides which program *is* the duty, from AGENT_ENTRY, and refuses to run
     one that is missing or broken;
  2. frames a run: loads the conversation the last run left behind, puts the
     run's own facts in front of it, and says so in the record;
  3. drives the turns: sends the conversation, runs the tools the duty
     registered, repeats until the duty ends the run or the run's budget does;
  4. bounds the conversation so a long run does not silently forget -- what
     falls out of the window is written to a recap that keeps being sent;
  5. writes the conversation back out where the next run will find it, and
     appends a line to the supervisor's record for every turn;
  6. exposes the run's own facts (context left, turns lived, how the last run
     ended) through `run.status()`.

What it refuses to do is decide what the duty wants. There is no task
scheduler here, no role table, no queue, no notion of a leader. The program it
loads is free to be anything at all, including a program that replaces this one
as the entry point.

Exit codes are the vocabulary the supervisor reads:

    0   the run ended cleanly and the next one starts fresh
    42  the duty ended the run on purpose (usually with a handoff note)
    43  the run cannot continue and its fault is its own -- a tombstone
    44  the environment failed; pause and try again without touching anything

The chassis runs the duty in-process. A duty that deadlocks inside a turn is
therefore only bounded by its own conscience, and the supervisor's inactivity
watch is what notices a process that is alive and making no progress.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import inspect
import json
import os
import re
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

SERVICES_DIR = Path(os.environ.get("SERVICES_DIR", "/opt/services"))
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))

from common import (  # noqa: E402  (path is set up above on purpose)
    append_jsonl,
    env_int,
    env_optional_int,
    iso,
    read_bounded,
    read_json,
    utc_now,
    write_json_atomic,
    write_text_atomic,
)

EXIT_OK = 0
EXIT_HANDOFF = 42
EXIT_DUTY_FAULT = 43
EXIT_ENVIRONMENT = 44

# Exit codes 42 and 44 mean "the next run continues from here": 42 is a
# designed end, and 44 is the world's fault rather than the run's. A run that
# hits a budget is a designed end too, whatever code the duty asked for on the
# way out -- a duty that calls a turn limit an error must not cost the lineage
# its conversation.
RESUMING_EXITS = frozenset({EXIT_HANDOFF, EXIT_ENVIRONMENT})

# A lineage id names one agent's chain of runs; it is created once and carried
# in run.json. Anything else found there is replaced, and the record says so.
LINEAGE_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")

SOCKET_WAIT_SECONDS = 60

# How much of each dropped message is kept in the recap. Enough to see the
# shape of what went out of the window, not enough to become a second window.
RECAP_LINE_CHARS = 400
RECAP_MAX_BYTES = 96 * 1024

# How the recap is framed when it is sent. It is a constant because two places
# have to agree on it: `prepared_view` builds the frame, and
# `drop_stored_recap_frames` recognises -- and drops -- a frame an older run
# wrote into the conversation itself, which is where it never belonged.
RECAP_FRAME_PREFIX = (
    "Recap of conversation that has fallen out of the context window. "
    "It is a lossy record, kept because the window is not a memory:\n\n"
)


class EnvironmentFailure(Exception):
    """The recorder or the upstream is unusable; nothing about the run is at fault."""


class DutyFault(Exception):
    """The run cannot continue and the fault is its own."""


class BudgetReached(Exception):
    """The run reached a budget it was given. Not a fault."""


class TurnLimitReached(BudgetReached):
    pass


class WallLimitReached(BudgetReached):
    pass


class PersistenceFailure(Exception):
    """A checkpoint could not be written. The environment's failure, not the run's: exit 44."""


class RunTermination(SystemExit):
    """A run ended on purpose through `context.handoff()` or `context.finish()`.

    A SystemExit subclass, so a duty that wraps a handoff in `except SystemExit`
    keeps working as it always has -- and if it swallows the termination, the
    run simply continues: nothing records a termination until the exception
    reaches the runtime's own catcher. Its code is the familiar one (42 for a
    handoff, 0 for a finish); its `kind` is what tells a typed end from a bare
    `sys.exit(42)`.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(EXIT_HANDOFF if kind == "handoff" else EXIT_OK)
        self.kind = kind


class NestedTurnRefused(RuntimeError):
    """`ask()` from inside a tool. An ordinary exception: the tool's error text."""


# Exceptions a tool may raise that end the run rather than becoming the tool's
# result text. Everything that is not an `Exception` (KeyboardInterrupt, a
# bare BaseException) also passes through; these are the `Exception`s that do.
CONTROL_EXCEPTIONS = (SystemExit, KeyboardInterrupt, BudgetReached, EnvironmentFailure, DutyFault, PersistenceFailure)

# During a tool group, say() and note() are queued and appended after the
# group's last tool result, so a group is never interrupted by a message. The
# queue is bounded (SV-015 v2 section 1.4.6): a message over these limits is
# refused with an ordinary error, never dropped or shortened.
MAX_QUEUED_MESSAGES = 16
MAX_QUEUED_UNITS = 64 * 1024  # escaped units of the normalized text

# What a run's last call is told, by cause; the later calls are told they did
# not run. A call that was running when the process was interrupted has an
# outcome nobody can know.
UNKNOWN_CALL_OUTCOME = (
    "outcome unknown: the run ended while this call was running; "
    "its effects may or may not have happened"
)


def ended_call_text(stop: BaseException) -> str:
    """The result recorded for the call in which the run ended."""
    if isinstance(stop, RunTermination):
        return f"{stop.kind} accepted; run ending"
    if isinstance(stop, KeyboardInterrupt):
        return UNKNOWN_CALL_OUTCOME
    if isinstance(stop, SystemExit):
        return f"the call raised SystemExit({stop.code!r}); the run ended"
    detail = str(stop)
    return f"the call raised {type(stop).__name__}{': ' + detail if detail else ''}; the run ended"


def classify_exit(code) -> tuple[int, str, str]:
    """A bare SystemExit's (exit code, reason, note), never raising on an odd payload.

    `SystemExit(int n)` exits n (SV-013 2.2.4), labelled as having no
    termination record. No range is imposed here: what n becomes as a process
    status (300 is 44, -1 is 255) is the operating system's arithmetic, as it
    always was. A bool is an int (`True` is 1), as it always was. A string is
    a clean end whose text is the note; None is a clean end; any other payload
    is the run's own fault (43) instead of an exception inside this handler.
    """
    if code is None:
        return EXIT_OK, "exit_none", ""
    if isinstance(code, int):
        code = int(code)
        return code, f"exit_{code}_without_termination_record", ""
    if isinstance(code, str):
        return EXIT_OK, "exit_str", code
    return EXIT_DUTY_FAULT, "invalid_exit_payload", f"SystemExit({code!r})"


# ---------------------------------------------------------------------------
# The carry: what survives between runs
# ---------------------------------------------------------------------------
class Carried:
    """The two files that let a run end without ending the lineage.

    `handoff` is the note the last run left for this one. `recap` is the record
    of what the context window has dropped. Neither is a memory system: they
    are the two facts a run needs in order not to begin blind, and a duty that
    wants more durable state should write it where it likes.
    """

    def __init__(self, session_dir: Path, home_dir: Path) -> None:
        self.session_dir = session_dir
        self.home_dir = home_dir
        self.conversation_path = session_dir / "conversation.json"
        self.meta_path = session_dir / "run.json"
        self.recap_path = session_dir / "recap.md"
        self.handoff_path = home_dir / "HANDOFF.md"

    def conversation(self) -> list[dict] | None:
        data = read_json(self.conversation_path, limit=64 * 1024 * 1024)
        if not isinstance(data, list):
            return None
        # A conversation that is not a list of message-shaped mappings is worse
        # than none: it would fail every request from here on.
        for message in data:
            if not isinstance(message, dict) or not isinstance(message.get("role"), str):
                return None
        return data

    def save_conversation(self, messages: list[dict]) -> None:
        write_json_atomic(self.conversation_path, messages)

    def recap(self) -> str:
        raw = read_bounded(self.recap_path, RECAP_MAX_BYTES)
        return raw.decode("utf-8", "ignore") if raw else ""

    def append_recap(self, lines: list[str]) -> None:
        if not lines:
            return
        existing = self.recap()
        combined = (existing + "\n".join(lines) + "\n").strip() + "\n"
        if len(combined.encode("utf-8")) > RECAP_MAX_BYTES:
            # Keep the newest material; the recap is a window too.
            encoded = combined.encode("utf-8")[-RECAP_MAX_BYTES:]
            combined = encoded.decode("utf-8", "ignore")
            combined = combined.split("\n", 1)[-1]
        write_text_atomic(self.recap_path, combined)

    def handoff(self) -> str:
        raw = read_bounded(self.handoff_path, 64 * 1024)
        return raw.decode("utf-8", "ignore") if raw else ""

    def meta(self) -> dict:
        data = read_json(self.meta_path)
        return data if isinstance(data, dict) else {}

    def save_meta(self, meta: dict) -> None:
        write_json_atomic(self.meta_path, meta)


def drop_stored_recap_frames(messages: list[dict], folded: int) -> tuple[list[dict], int]:
    """Drop recap frames an older run wrote into the conversation, and re-anchor the fold.

    Until round 84, `resume()` inserted the recap into `messages` as a
    `role="system"` message and the checkpoint wrote it back, so a lineage
    accumulated one copy per resume. `selection()` pins every system message and
    sends pinned material whatever the budget says, so no copy could ever be
    evicted: one real lineage reached 84 copies, 99% of a 5.4 MB checkpoint, and
    1.33 M estimated tokens against a 200 000-token window.

    The recap is not part of the conversation -- `prepared_view()` builds the
    frame at send time from `recap.md` -- so a stored frame is dropped here, as
    the conversation is adopted. `folded` is the index the recap has already
    folded up to; it moves back by the number of frames dropped in front of it,
    so the next fold does not re-record material that is already in the recap.

    A legacy handoff note is a real message and stays where it is: this repairs
    the frames, not the agent's transcript. The forward path keeps the list
    chronological from here on.
    """
    kept: list[dict] = []
    dropped_before_fold = 0
    for index, message in enumerate(messages):
        content = message.get("content")
        is_frame = (
            message.get("role") == "system"
            and isinstance(content, str)
            and content.startswith(RECAP_FRAME_PREFIX)
        )
        if is_frame:
            if index < folded:
                dropped_before_fold += 1
            continue
        kept.append(message)
    return kept, max(0, folded - dropped_before_fold)


# ---------------------------------------------------------------------------
# The tool registry the duty uses
# ---------------------------------------------------------------------------
class ToolRegistry:
    """Maps names to functions and publishes the schemas a model can read.

    Schemas come from the signature and the docstring, the same way the
    reference seed did it, because the fleet will register tools this runtime
    has never seen and should not have to learn a schema dialect to do it.
    """

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}
        self.schemas: list[dict] = []

    def register(self, func):
        self.tools[func.__name__] = func
        self.schemas.append(schema_for(func))
        return func

    def clear(self) -> None:
        self.tools.clear()
        self.schemas.clear()


def _is_registry(candidate) -> bool:
    """Whether something can serve as this run's toolbox."""
    return (
        candidate is not None
        and hasattr(candidate, "tools")
        and hasattr(candidate, "schemas")
        and callable(getattr(candidate, "register", None))
    )


def json_type_for(annotation) -> str:
    """The JSON type for a Python annotation, unions and optionals included.

    `int | None` is an integer that may be absent, not a string. Getting this
    wrong is silent and expensive: the schema is the only documentation a model
    gets, and a number documented as a string gets sent as one.
    """
    import types
    import typing

    if annotation is inspect.Parameter.empty or annotation is inspect.Signature.empty:
        return "string"
    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is str:
        return "string"
    if annotation in {list, dict, tuple, set}:
        return "array" if annotation is not dict else "object"

    origin = typing.get_origin(annotation)
    if origin in {typing.Union, types.UnionType}:
        # An optional takes the type of the arm that is not None.
        arms = [arm for arm in typing.get_args(annotation) if arm is not type(None)]
        if len(arms) == 1:
            return json_type_for(arms[0])
        return "string"
    if origin in {list, set, tuple}:
        return "array"
    if origin is dict:
        return "object"
    if isinstance(annotation, str):
        return _json_type_for_name(annotation)
    return "string"


def _json_type_for_name(name: str) -> str:
    lowered = name.lower()
    if "bool" in lowered:
        return "boolean"
    if "int" in lowered:
        return "integer"
    if "float" in lowered:
        return "number"
    if "list" in lowered or "tuple" in lowered or "sequence" in lowered:
        return "array"
    if "dict" in lowered or "mapping" in lowered:
        return "object"
    return "string"


def schema_for(func) -> dict:
    signature = inspect.signature(func)
    doc = (func.__doc__ or "").strip()
    description = doc.split("\n\n")[0].strip() if doc else f"call {func.__name__}"
    properties: dict[str, dict] = {}
    required: list[str] = []
    for name, param in signature.parameters.items():
        if name in {"self", "cls"}:
            continue
        json_type = json_type_for(param.annotation)
        entry: dict[str, Any] = {"type": json_type, "description": param.name}
        if param.default is not inspect.Parameter.empty:
            entry["description"] += f" (default {param.default!r})"
        else:
            required.append(name)
        properties[name] = entry
    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": description or f"call {func.__name__}",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


# ---------------------------------------------------------------------------
# The context a duty is handed
# ---------------------------------------------------------------------------
class RunContext:
    """Everything a duty is given, and the only door it needs to the world.

    The duty is a Python program in a container with a shell, a compiler and a
    writable filesystem, so this class is a convenience rather than a
    boundary: every method here is something a duty could do for itself. It
    exists so that the ordinary path -- read, write, run, call the model, say
    you are done -- does not have to be reinvented, not so that anything is
    forbidden.
    """

    def __init__(self, chassis: Chassis, tools: ToolRegistry) -> None:
        self._chassis = chassis
        self.tools = tools
        self.work_dir = chassis.work_dir
        self.home_dir = chassis.home_dir
        self.diary_dir = chassis.diary_dir
        self.duty_dir = chassis.duty_dir
        self.started = utc_now()

    # -- the run's own facts ------------------------------------------------
    def status(self) -> str:
        """Everything this run knows about itself, as text."""
        chassis = self._chassis
        return json.dumps(chassis.status(), indent=2)

    def turn(self) -> int:
        return self._chassis.turn

    def last_turn_had_tools(self) -> bool:
        """Whether the previous turn asked for a tool.

        An empty reply with tool calls is a model that acted without narrating,
        which is ordinary. An empty reply with neither is a model with nothing
        to add, and a duty reading that as anything else spins.
        """
        return self._chassis.last_had_tools

    def context_left(self) -> int:
        """Estimated tokens of room left in the window before eviction starts."""
        return chassis_budget(self._chassis) - estimate_tokens(self._chassis.messages)

    def model(self) -> str:
        return self._chassis.model

    # -- filling the conversation ------------------------------------------
    def say(self, text: str) -> None:
        """Append a user-role message without calling the model.

        From inside a tool it is queued and appended after the turn's last tool
        result (at most 16 queued, each at most 64 KiB in escaped units;
        beyond that it raises ValueError).
        """
        self._chassis.add_message("user", text)

    def note(self, text: str) -> None:
        """Append a system-role message -- a fact for the model, not a turn.

        Queued like `say` when called from inside a tool.
        """
        self._chassis.add_message("system", text)

    def history(self) -> list[dict]:
        """The conversation so far. A copy; edits here do not take effect."""
        return [dict(message) for message in self._chassis.messages]

    def set_history(self, messages: list[dict]) -> None:
        """Replace the conversation. The duty owns it and may prune it.

        Not from inside a tool: a turn's tool results belong to the turn that
        asked for them, so replacing the history under them raises RuntimeError.
        """
        if self._chassis.active_group is not None:
            raise RuntimeError("history cannot be replaced during a tool call")
        if not isinstance(messages, list):
            raise ValueError("history must be a list of messages")
        self._chassis.messages[:] = messages
        # The recap's fold point is an index into the list: it cannot point past
        # the end of the one that replaced it.
        self._chassis.recap_folded = min(self._chassis.recap_folded, len(messages))

    def ask(self, text: str, tools: bool = True) -> str:
        """One model call with `text` as the newest user message; returns its text.

        Not from inside a tool: a nested turn would interleave a second turn's
        messages into the first one's tool group, so it raises
        NestedTurnRefused, which the calling tool sees as an ordinary error.
        """
        if self._chassis.active_group is not None:
            raise NestedTurnRefused("nested turn not supported")
        return self._chassis.turn_once(text, use_tools=tools)

    # -- ending the run -----------------------------------------------------
    def handoff(self, note: str) -> None:
        """End this run on purpose, leaving `note` for the run that follows.

        Raises RunTermination (a SystemExit): from a tool, the call is answered
        "handoff accepted; run ending" and any later calls in the same turn are
        answered "not run"; the run exits 42.
        """
        self._chassis.write_handoff(note)
        raise RunTermination("handoff")

    def finish(self, note: str = "") -> None:
        """End this run cleanly. The next run starts, and resumes if it can.

        Raises RunTermination (a SystemExit) with exit 0, as `handoff` does.
        """
        if note:
            self._chassis.write_handoff(note)
        raise RunTermination("finish")


def estimate_tokens(messages: list[dict]) -> int:
    """A cheap estimate of the conversation's size, in the units the window is in.

    Serialised length over four. It does not need to be right; it needs to be
    monotone in the thing that matters, which is how much text is being sent.
    """
    return len(json.dumps(messages, ensure_ascii=False)) // 4


def chassis_budget(chassis: Chassis) -> int:
    return chassis.context_window


# ---------------------------------------------------------------------------
# Text and ids: pure helpers (SV-015 v2 section 2.3)
# ---------------------------------------------------------------------------
# Sizes are measured in *escaped units*: E(s) = len(json.dumps(s,
# ensure_ascii=True)) - 2. For every string that is at least its length in each
# serialized form the runtime produces or causes -- the saved conversation, a
# request, a UTF-8 record -- so a cap in escaped units bounds all of them, which
# a cap in UTF-8 bytes does not (160 NULs are 160 bytes but 960 escaped units).
#
# These are pure functions. Wiring them into stored responses is a later step
# (SV-013 K-E2); `queue_message` uses E for its admission bound.
TRUNCATION_MARKER = "\n[truncated: kept {kept} of {total} bytes; sha256 {digest}]"
WIRE_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
WIRE_BASE = re.compile(r"[A-Za-z0-9_.:-]{1,48}")


def _unit_cost(character: str) -> int:
    code = ord(character)
    if character in '"\\\n\r\t\b\f':
        return 2
    if code < 0x20 or code == 0x7F:
        return 6  # \u00XX: controls, and DEL, which json.dumps also escapes
    if code < 0x80:
        return 1  # printable ASCII
    if code < 0x10000:
        return 6  # \uXXXX
    return 12  # a surrogate pair of \uXXXX escapes


def escaped_units(text: str) -> int:
    """E(text): the length of `text` as ASCII-escaped JSON, without its quotes."""
    return sum(_unit_cost(character) for character in text)


def normalize_text(text: str) -> tuple[str, int]:
    """Lone surrogates become `?`; returns the text and how many were replaced.

    `text.encode("utf-8", "replace")` maps each code point in U+D800-U+DFFF to
    `?`. Nothing else changes, so the result always encodes as UTF-8.
    """
    replaced = sum(1 for character in text if 0xD800 <= ord(character) <= 0xDFFF)
    if not replaced:
        return text, 0
    return text.encode("utf-8", "replace").decode("utf-8"), replaced


def truncate_marked(text: str, cap: int) -> tuple[str, dict]:
    """Normalize `text`, then keep it whole or cut it with a marker, within `cap` units.

    Over the cap, the result is the longest code-point prefix p of the
    normalized text such that E(p) + E(marker) <= cap, followed by the marker
    `"\\n[truncated: kept K of N bytes; sha256 H]"`, where K is p's UTF-8
    length and N and H are the normalized original's UTF-8 length and SHA-256.
    A code-point prefix is always valid UTF-8, so no character is ever split.
    A cap too small for the marker itself raises ValueError: the caller's
    configuration is wrong, and no silent shortening is better than that.
    """
    normalized, replaced = normalize_text(text)
    costs = [_unit_cost(character) for character in normalized]
    units = sum(costs)
    encoded = normalized.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    info = {
        "truncated": False,
        "kept_bytes": len(encoded),
        "original_bytes": len(encoded),
        "sha256": digest,
        "replaced_chars": replaced,
        "escaped_units": units,
    }
    if units <= cap:
        return normalized, info

    unit_prefix = [0]
    byte_prefix = [0]
    for character, cost in zip(normalized, costs, strict=True):
        unit_prefix.append(unit_prefix[-1] + cost)
        byte_prefix.append(byte_prefix[-1] + len(character.encode("utf-8")))

    def marker(length: int) -> str:
        return TRUNCATION_MARKER.format(kept=byte_prefix[length], total=len(encoded), digest=digest)

    def fits(length: int) -> bool:
        return unit_prefix[length] + escaped_units(marker(length)) <= cap

    if not fits(0):
        raise ValueError(f"a cap of {cap} escaped units cannot hold the truncation marker")
    # The cost is non-decreasing in the prefix length (the marker's K only
    # grows), so the longest fitting prefix is found by bisection.
    low, high = 0, len(normalized)
    while low < high:
        middle = (low + high + 1) // 2
        if fits(middle):
            low = middle
        else:
            high = middle - 1
    stored = normalized[:low] + marker(low)
    info.update(truncated=True, kept_bytes=byte_prefix[low], escaped_units=escaped_units(stored))
    return stored, info


def assign_wire_ids(ids: list, turn_seq: int) -> list[str]:
    """Collision-free wire ids for one response's tool calls (SV-015 v2 section 2.3).

    An original id is kept if it is a string of 1-64 characters from
    `[A-Za-z0-9_.:-]` and occurs exactly once. Every usable original is
    reserved *before* any replacement is generated, so a replacement can never
    take a name a later original keeps. Anything else -- a duplicate, a missing
    id, a non-string, a lone surrogate -- gets `<base>.rt<i>`, with `.<k>` added
    until it is unused. The base is the original when it is a valid string of
    at most 48 characters, else `rt.<turn_seq>`. Any JSON type is accepted;
    nothing is encoded or hashed, so nothing here can raise on odd input.
    """

    def usable(value) -> bool:
        return isinstance(value, str) and WIRE_ID.fullmatch(value) is not None and ids.count(value) == 1

    used = {value for value in ids if usable(value)}
    wire: list[str] = []
    for index, value in enumerate(ids):
        if usable(value):
            wire.append(value)
            continue
        base = value if isinstance(value, str) and WIRE_BASE.fullmatch(value) else f"rt.{turn_seq}"
        candidate = f"{base}.rt{index}"
        suffix = 1
        while candidate in used:
            candidate = f"{base}.rt{index}.{suffix}"
            suffix += 1
        wire.append(candidate)
        used.add(candidate)
    return wire


# ---------------------------------------------------------------------------
# The chassis
# ---------------------------------------------------------------------------
class Chassis:
    def __init__(self) -> None:
        self.slug = os.environ.get("AGENT_SLUG", "agent")
        self.name = os.environ.get("AGENT_NAME", self.slug)
        self.work_dir = Path(os.environ.get("WORK_DIR", "/work"))
        self.home_dir = Path(os.environ.get("AGENT_HOME", "/home/agent"))
        self.diary_dir = Path(os.environ.get("DIARY_DIR", "/diary"))
        self.session_dir = self.home_dir / "session"
        self.duty_dir = Path(os.environ.get("DIODE_DUTY_DIR", f"/diode/{self.slug}"))
        self.entry = Path(os.environ.get("AGENT_ENTRY", str(self.work_dir / "duty.py")))
        self.model = os.environ.get("LLM_MODEL", "deepseek/deepseek-v4-pro")
        self.context_window = env_int("CONTEXT_WINDOW_TOKENS", 200_000)
        self.eviction_chunk = env_optional_int("CONTEXT_WINDOW_EVICTION_TOKENS")
        self.max_turns = env_optional_int("RUN_MAX_TURNS")
        self.max_seconds = env_optional_int("RUN_MAX_SECONDS")
        self.run_id = f"{int(time.time())}-{os.getpid()}"
        self.turn = 0
        self.messages: list[dict] = []
        self.tools = ToolRegistry()
        self.context: RunContext | None = None
        self.recap_folded = 0
        # The tool group in progress (the turn number), or None. While it is set
        # nothing may land between a call and its result: ask() and
        # set_history() are refused and say()/note() wait in `queued`.
        self.active_group: int | None = None
        self.queued: list[dict] = []
        # What the previous run left in run.json, read once at the start; the
        # file is rewritten by every checkpoint of this run.
        self.previous_meta: dict | None = None
        self.lineage_id: str | None = None
        self.started_at = utc_now()
        self.usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.last_handoff = ""
        # Whether the last turn asked for a tool. A turn that calls a tool
        # without narrating is not a turn that said nothing, and a duty that
        # reads an empty `ask()` as silence would end every run the moment a
        # model stopped talking to itself between calls.
        self.last_had_tools = False
        self.carried = Carried(self.session_dir, self.home_dir)
        self.telemetry_dir = Path(os.environ.get("TELEMETRY_DIR", "/telemetry"))
        self.lifecycle_path = self.telemetry_dir / "agents" / self.slug / "lifecycle.jsonl"
        self.operations_path = self.telemetry_dir / "agents" / self.slug / "operations.jsonl"

    # -- the record ---------------------------------------------------------
    def record(self, event: str, **fields) -> None:
        """Append one line to the supervisor's record of what this run did.

        The record is outside the fleet's reach by mount, not by convention:
        the agents read this directory and cannot write it.
        """
        with contextlib.suppress(OSError):
            append_jsonl(
                self.lifecycle_path,
                {
                    "at": iso(),
                    "event": event,
                    "agent": self.slug,
                    "name": self.name,
                    "run": self.run_id,
                    "turn": self.turn,
                    **fields,
                },
            )

    def operation(self, kind: str, **fields) -> None:
        """Append one line to the record of *operations* -- tool calls, edits,
        commands -- as opposed to turns. Agent-writable sources; recorded here
        because a record an agent can rewrite is not a record."""
        with contextlib.suppress(OSError):
            append_jsonl(
                self.operations_path,
                {
                    "at": iso(),
                    "agent": self.slug,
                    "run": self.run_id,
                    "turn": self.turn,
                    "kind": kind,
                    **fields,
                },
            )

    # -- the model ----------------------------------------------------------
    def client(self):
        """An OpenAI-compatible client aimed at the recorder's socket.

        The key sent here is deliberately meaningless: the recorder substitutes
        the real one. Nothing in this container knows a credential worth
        having.
        """
        import httpx
        from openai import OpenAI

        socket_path = os.environ.get("LLM_SOCKET_PATH", "/llm/sock/duty.sock")
        wait = env_int("SOCKET_WAIT_SECONDS", SOCKET_WAIT_SECONDS)
        deadline = time.time() + wait
        while not os.path.exists(socket_path):
            if time.time() > deadline:
                raise EnvironmentFailure(
                    f"model socket {socket_path} did not appear within {wait}s"
                )
            time.sleep(0.5)
        return OpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY", "sk-dummy"),
            base_url=os.environ.get("LLM_BASE_URL", "http://localhost/api/v1"),
            timeout=float(env_int("RECORDER_TIMEOUT_SECONDS", 600)),
            max_retries=0,
            http_client=httpx.Client(transport=httpx.HTTPTransport(uds=socket_path)),
        )

    def request(self, client, use_tools: bool = True):
        """One completion request, with the window applied and send-view repaired."""
        self.fold_recap_if_needed()
        send = prepared_view(self.messages, self.context_window, self.eviction_chunk, self.carried)
        kwargs: dict[str, Any] = {"model": self.model, "messages": send}
        if use_tools and self.tools.schemas:
            kwargs["tools"] = self.tools.schemas
            kwargs["tool_choice"] = "auto"
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as error:  # noqa: BLE001 -- classified, not swallowed
            raise classify(error) from error
        self.capture_usage(response)
        return response

    def capture_usage(self, response) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        for key in self.usage_totals:
            value = getattr(usage, key, None)
            if isinstance(value, int):
                self.usage_totals[key] += value

    def turn_once(self, text: str | None = None, use_tools: bool = True) -> str:
        """Add an optional user message, then run one assistant turn.

        Returns the assistant's text. Tool calls are executed here, in order,
        and their results appended as tool messages, which is what keeps a duty
        from having to implement the calling convention itself.
        """
        if self.active_group is not None:
            raise NestedTurnRefused("nested turn not supported")
        client = self._client
        if text is not None:
            self.messages.append({"role": "user", "content": text})
        response = self.request(client, use_tools=use_tools)
        choice = response.choices[0] if response.choices else None
        if choice is None:
            raise EnvironmentFailure("the upstream returned no choices")
        message = choice.message
        content = message.content or ""
        reasoning = getattr(message, "reasoning_content", None)
        assistant: dict[str, Any] = {"role": "assistant", "content": content}
        tool_calls = getattr(message, "tool_calls", None) or []
        if reasoning:
            assistant["reasoning_content"] = reasoning
        if tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in tool_calls
            ]
        self.messages.append(assistant)
        self.last_had_tools = bool(tool_calls)
        self.turn += 1
        if tool_calls:
            # Every stored call gets exactly one result, in memory, whatever
            # ends the run: the call it ended in is told why, and every later
            # call is told it did not run -- and is not invoked.
            self.active_group = self.turn
            try:
                for position, call in enumerate(tool_calls):
                    try:
                        result = self.invoke(call.function.name, call.function.arguments)
                    except BaseException as stop:
                        self.messages.append(self.tool_message(call, ended_call_text(stop)))
                        how = f"by {stop.kind} " if isinstance(stop, RunTermination) else ""
                        for later in tool_calls[position + 1 :]:
                            self.messages.append(
                                self.tool_message(later, f"not run: the run ended {how}in call {call.id}")
                            )
                        raise
                    self.messages.append(self.tool_message(call, result))
            finally:
                self.close_group()
        self.checkpoint()
        self.record("turn", tools=len(tool_calls), usage=dict(self.usage_totals))
        self.check_budgets()
        return content

    @staticmethod
    def tool_message(call, content: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": call.id,
            "name": call.function.name,
            "content": content,
        }

    # -- messages a duty adds -------------------------------------------------
    def add_message(self, role: str, text) -> None:
        """Append now, or queue until the tool group in progress has all its results."""
        if self.active_group is None:
            self.messages.append({"role": role, "content": text})
            return
        self.queue_message(role, text)

    def queue_message(self, role: str, text) -> None:
        """Hold a message until the group closes, within the queue's bounds.

        Refusal is an ordinary ValueError, which a tool sees as its error text:
        nothing is dropped, shortened or reordered behind the duty's back. The
        text is normalized (a lone surrogate becomes `?`), and that normalized
        text is both what is measured, in escaped units, and what is queued.
        """
        if not isinstance(text, str):
            raise ValueError("a message queued during a tool call must be text")
        if len(self.queued) >= MAX_QUEUED_MESSAGES:
            raise ValueError(
                f"at most {MAX_QUEUED_MESSAGES} messages can be queued during one tool call group"
            )
        # The text that is measured is the text that is stored: normalized, so
        # a lone surrogate is `?` both in the bound and in the conversation.
        normalized, _replaced = normalize_text(text)
        units = escaped_units(normalized)
        if units > MAX_QUEUED_UNITS:
            raise ValueError(
                f"a message queued during a tool call is at most {MAX_QUEUED_UNITS} escaped "
                f"units; this one is {units}"
            )
        self.queued.append({"role": role, "content": normalized})

    def close_group(self) -> None:
        """End the tool group in progress and append what it queued, in order."""
        self.active_group = None
        if self.queued:
            self.messages.extend(self.queued)
            self.queued = []

    def invoke(self, name: str, arguments: str) -> str:
        """Run one registered tool by name. Every ordinary failure becomes text.

        A tool that raises an ordinary exception is information the model can
        act on, so the error is handed back rather than ending the run. What
        passes through instead are the ends of a run: SystemExit (including a
        typed handoff or finish), KeyboardInterrupt, a budget, an environment
        failure, a duty fault, a persistence failure, and anything that is not
        an `Exception` at all.
        """
        import inspect

        func = self.tools.tools.get(name)
        if func is None:
            known = sorted(self.tools.tools)
            self.operation("tool_unknown", tool=name, registered=len(known), names=known[:40])
            if known:
                return (
                    f"error: no tool named {name!r} is registered; this run has "
                    f"{len(known)} tool(s): {', '.join(known)}"
                )
            return (
                f"error: no tool named {name!r} is registered, and this run has no "
                "tools at all: nothing in the duty registered any"
            )
        try:
            kwargs = json.loads(arguments or "{}")
        except json.JSONDecodeError as error:
            self.operation("tool_bad_args", tool=name, error=str(error))
            return f"error: arguments were not valid json: {error}"
        if not isinstance(kwargs, dict):
            return "error: arguments must be a json object"
        signature = inspect.signature(func)
        unknown = set(kwargs) - set(signature.parameters)
        if unknown:
            return f"error: {name} does not take {', '.join(sorted(unknown))}"
        try:
            result = func(**kwargs)
        except CONTROL_EXCEPTIONS:
            raise
        except Exception as error:  # noqa: BLE001 -- the model is told, not the log
            self.operation("tool_error", tool=name, error=f"{type(error).__name__}: {error}")
            return f"error: {type(error).__name__}: {error}"
        text = "" if result is None else str(result)
        self.operation("tool", tool=name, chars=len(text))
        return text

    # -- the window ---------------------------------------------------------
    def fold_recap_if_needed(self) -> None:
        """Record what the coming eviction will drop, before it drops it.

        The window is not a memory: messages that fall out of it stop being
        sent and are otherwise gone. This is the one place that notices, and
        what it notices goes into a recap that keeps being sent -- so a run
        that has been going for a long time can see the shape of what it no
        longer has.
        """
        kept_start, _ = window_bounds(self.messages, self.context_window, self.eviction_chunk)
        if kept_start <= self.recap_folded:
            return
        lines = []
        for message in self.messages[self.recap_folded : kept_start]:
            role = message.get("role", "?")
            if role == "system":
                # Pinned material is never evicted, so folding it would record
                # something the run can still read. It is also how the recap
                # used to fold *itself*: every resume stored another recap frame
                # as a system message and the fold range ran straight across
                # them (round 84). `drop_stored_recap_frames` removes the frames
                # already in the file; this keeps a new one from starting.
                continue
            body = render_message(message)
            if not body:
                continue
            if len(body) > RECAP_LINE_CHARS:
                body = body[:RECAP_LINE_CHARS] + " …"
            lines.append(f"- [{role}] {body}")
        self.carried.append_recap(lines)
        self.recap_folded = kept_start
        self.record("recap_fold", dropped=len(lines), at_index=kept_start)

    # -- budgets ------------------------------------------------------------
    def check_budgets(self) -> None:
        if self.max_turns is not None and self.turn >= self.max_turns:
            raise TurnLimitReached(f"run reached {self.max_turns} turns")
        if self.max_seconds is not None:
            elapsed = (utc_now() - self.started_at).total_seconds()
            if elapsed >= self.max_seconds:
                raise WallLimitReached(f"run reached {self.max_seconds} seconds")

    # -- state --------------------------------------------------------------
    def checkpoint(self, ended: dict | None = None) -> None:
        """Write the conversation (a plain list, as always) and run.json.

        run.json gains three additive keys: `lineage_id` (stable across runs),
        `recap_folded` (how far the recap has folded, so a resumed run does not
        fold the same messages again) and, on the final checkpoint, `ended`
        (`{exit, reason, at, run}`). It deliberately does **not** gain
        `format`, `writer` or `checkpoint`: those mark the ledger's authority
        (SV-013 2.2.2), and publishing them before the ledger exists would make
        a later ledger-aware runtime read this file as a lost ledger.

        A filesystem error becomes PersistenceFailure (exit 44); anything else,
        such as a message a duty made unserializable, propagates as it is.
        """
        meta = {
            "agent": self.slug,
            "name": self.name,
            "run": self.run_id,
            "turn": self.turn,
            "model": self.model,
            "updated": iso(),
            "context_tokens": estimate_tokens(self.messages),
            "context_window": self.context_window,
            "usage": dict(self.usage_totals),
            "entry": str(self.entry),
            "lineage_id": self.lineage_id,
            "recap_folded": self.recap_folded,
        }
        if ended is not None:
            meta["ended"] = ended
        try:
            self.carried.save_conversation(self.messages)
            self.carried.save_meta(meta)
        except OSError as error:
            raise PersistenceFailure(
                f"the checkpoint could not be written: {type(error).__name__}: {error}"
            ) from error

    def write_handoff(self, note: str) -> None:
        self.home_dir.mkdir(parents=True, exist_ok=True)
        # Recorded here rather than at the exit: a note that unwinds through
        # frames of SystemExit arrives at the exit path as an empty string, and
        # the record would say a run ended for no reason. This is the moment the
        # reason actually exists.
        self.last_handoff = note.strip()
        write_text_atomic(
            self.carried.handoff_path,
            f"# Handoff, left {iso()} by run {self.run_id} (turn {self.turn})\n\n{note.strip()}\n",
        )
        self.record("handoff", chars=len(note))

    def status(self) -> dict:
        # The previous run's facts as they were when this run started; this
        # run's own checkpoints have rewritten run.json since.
        meta = self.previous_meta if getattr(self, "previous_meta", None) is not None else self.carried.meta()
        return {
            "agent": self.slug,
            "name": self.name,
            "run": self.run_id,
            "entry": str(self.entry),
            "model": self.model,
            "turn_this_run": self.turn,
            "turns_before_this_run": meta.get("turn"),
            "previous_run_ended": meta.get("ended"),
            "lineage_id": getattr(self, "lineage_id", None) or meta.get("lineage_id"),
            "context_window_tokens": self.context_window,
            "context_tokens_now": estimate_tokens(self.messages),
            "context_tokens_left": max(0, self.context_window - estimate_tokens(self.messages)),
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

    # -- loading the duty ---------------------------------------------------
    def load_duty(self):
        """Import AGENT_ENTRY as a module and insist it is runnable.

        A duty that cannot be imported, or that has no `main`, is a fault of
        the run rather than of the world: exit 43 sends the supervisor down its
        ladder, where the last resort is the pristine copy in the image.
        """
        entry = self.entry
        if not entry.exists():
            raise DutyFault(f"the duty entry {entry} does not exist")
        if not entry.is_file():
            raise DutyFault(f"the duty entry {entry} is not a file")
        spec = importlib.util.spec_from_file_location("duty", entry)
        if spec is None or spec.loader is None:
            raise DutyFault(f"the duty entry {entry} could not be loaded")
        module = importlib.util.module_from_spec(spec)
        sys.modules["duty"] = module
        try:
            spec.loader.exec_module(module)
        except SystemExit:
            raise
        except Exception as error:
            raise DutyFault(
                f"the duty entry raised on import: {type(error).__name__}: {error}"
            ) from error
        main = getattr(module, "main", None)
        if not callable(main):
            raise DutyFault(f"the duty entry {entry} defines no callable main(context)")
        return module, main

    # -- the run ------------------------------------------------------------
    def run(self) -> int:
        """Start, run the duty's main, and end -- with the end recorded on every path main reaches.

        What the terminal `finally` covers, stated exactly: everything from the
        moment `main(context)` is called. Failures before that -- creating the
        session and home directories, reading run.json, connecting to the
        recorder, loading the duty, binding its tools, and `resume` (including
        a duty's `bootstrap`) -- leave the process through `main()`'s handlers
        or a traceback with no `ended` metadata and no `run_end` record, and,
        deliberately, no checkpoint: nothing has been loaded that could be
        written back without risking the saved conversation.
        """
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.home_dir.mkdir(parents=True, exist_ok=True)
        previous = self.carried.meta()
        self.previous_meta = previous
        lineage = previous.get("lineage_id")
        if isinstance(lineage, str) and LINEAGE_ID.fullmatch(lineage):
            self.lineage_id = lineage
        else:
            self.lineage_id = uuid.uuid4().hex[:16]
            self.record("lineage_started", lineage_id=self.lineage_id)
        self.record(
            "run_start",
            entry=str(self.entry),
            model=self.model,
            window=self.context_window,
            lineage_id=self.lineage_id,
        )

        self._client = self.client()
        module, main = self.load_duty()
        # A duty may register tools at import or through the registry it is
        # handed; both are supported because both are obvious things to do.
        for candidate in ("tools", "TOOLS"):
            registry = getattr(module, candidate, None)
            # By shape, not by class: a duty that reached for the runtime itself
            # may hold a registry built from an equal-but-distinct class, and
            # silently ignoring it would leave the run with no tools at all --
            # which looks exactly like a model that will not stop calling them.
            if _is_registry(registry):
                self.tools = registry
                break
        self.context = RunContext(self, self.tools)
        # A duty loaded from the codebase may have reached for the runtime by
        # name while the codebase held a readable copy of it, in which case two
        # module objects exist and only one of them has the tools. Saying which
        # one this run is using turns a silent no-tools run into a sentence.
        self.record(
            "runtime_bound",
            chassis_module=str(getattr(sys.modules.get("chassis"), "__file__", "?")),
            duty_module=str(getattr(module, "__file__", "?")),
            registry_id=id(self.tools),
            registered=len(self.tools.tools),
            registry_is_ours=isinstance(self.tools, ToolRegistry),
            duty_registry_id=id(getattr(module, "tools", None)),
            duty_registry_is_ours=isinstance(getattr(module, "tools", None), ToolRegistry),
            chassis_class_id=id(ToolRegistry),
            duty_class_id=id(getattr(getattr(module, "ToolRegistry", None), "__mro__", (None,))[0]),
        )

        resumed = self.resume(previous)
        self.record("run_resumed" if resumed else "run_fresh", messages=len(self.messages))

        exit_code = EXIT_OK
        reason = "main_returned"
        note = ""
        try:
            main(self.context)
            note = "the run's main() returned without ending the run"
        except RunTermination as stop:
            # Typed, and distinct from a bare sys.exit(42): this is the only
            # path that records a handoff or a finish as the reason.
            exit_code, reason, note = stop.code, stop.kind, self.last_handoff
        except SystemExit as stop:
            exit_code, reason, note = classify_exit(stop.code)
            if not note:
                note = self.last_handoff
        except TurnLimitReached as reached:
            exit_code, reason, note = EXIT_HANDOFF, "turn_limit", str(reached)
        except WallLimitReached as reached:
            exit_code, reason, note = EXIT_HANDOFF, "wall_limit", str(reached)
        except BudgetReached as reached:
            exit_code, reason, note = EXIT_HANDOFF, "budget", str(reached)
        except DutyFault as fault:
            exit_code, reason, note = EXIT_DUTY_FAULT, "duty_fault", str(fault)
        except EnvironmentFailure as failure:
            exit_code, reason, note = EXIT_ENVIRONMENT, "environment", str(failure)
        except PersistenceFailure as failure:
            exit_code, reason, note = EXIT_ENVIRONMENT, "persistence_failure", str(failure)
        except KeyboardInterrupt:
            exit_code, reason, note = EXIT_ENVIRONMENT, "interrupted", "interrupted"
        except BaseException as error:  # noqa: BLE001 -- the run ends; the record survives
            exit_code, reason = EXIT_DUTY_FAULT, "run_traceback"
            note = f"{type(error).__name__}: {error}"
            self.record(
                "run_traceback",
                traceback="".join(traceback.format_exception(error))[-8000:],
            )
        finally:
            # End-of-run order: anything still queued is appended, then the
            # final checkpoint records how the run ended, then the record.
            self.close_group()
            ended = {"exit": exit_code, "reason": reason, "at": iso(), "run": self.run_id}
            try:
                self.checkpoint(ended=ended)
            except PersistenceFailure as failure:
                # Not a hidden success: the end could not be recorded where the
                # next run reads it, which is the environment's failure.
                self.record("checkpoint_failed", error=str(failure)[:500])
                if exit_code != EXIT_ENVIRONMENT:
                    exit_code, reason = EXIT_ENVIRONMENT, "persistence_failure"
            except Exception as error:  # noqa: BLE001 -- recorded, and the exit says so
                self.record("checkpoint_failed", error=f"{type(error).__name__}: {error}"[:500])
                if exit_code not in (EXIT_DUTY_FAULT, EXIT_ENVIRONMENT):
                    exit_code, reason = EXIT_DUTY_FAULT, "checkpoint_failed"
            if resumed and exit_code not in RESUMING_EXITS:
                # The run ended with an exit that is not one of the resuming
                # codes (42, 44), and the record says so. It is a label, not a
                # reset: the checkpoint stays on disk and the next run's
                # `resume()` adopts any readable conversation whatever this
                # exit was. No memory-reset policy hangs on this record.
                self.record("run_ended_unresumable", exit=exit_code)
            self.record(
                "run_end",
                exit=exit_code,
                reason=reason,
                note=note[:2000],
                turns=self.turn,
                usage=dict(self.usage_totals),
            )
            print(
                f"[chassis] run ended: exit={exit_code} reason={reason} turns={self.turn} "
                f"note_chars={len(note)} {note[:300]}",
                flush=True,
            )
        return exit_code

    def resume(self, previous: dict) -> bool:
        """Rebuild the conversation, or start one, and frame it.

        Resume is the default because losing a long conversation to a
        supervisor restart would make endurance impossible. A duty that wants a
        clean slate deletes the file; one that wants to steer its own opening
        writes its own.

        **The conversation is chronological, and this method is what keeps it
        that way.** `selection()` reads the end of the list as *now* and the
        beginning as what the window drops first, so everything added here is
        appended. Two things used to be inserted at the front, and both were
        defects:

        * **The recap is not part of the conversation.** It is a view of what
          the window dropped, and `prepared_view()` pins it into every request.
          Stored here it was written to the checkpoint and re-sent forever -- a
          `role="system"` message is pinned, so nothing could evict it. One real
          lineage accumulated 84 copies and 1.33 M estimated tokens against a
          200 000-token window, and `fold_recap_if_needed` then folded the
          copies back into the recap.
        * **The handoff note is the newest thing a run has to read, not the
          oldest.** Inserted at the front it took the pinned "opening problem"
          slot that `selection()` reserves for the first user message -- the one
          message the pin exists to protect.

        A conversation an older run left behind may still hold stored recap
        frames; they are dropped as it is adopted, and the fold point moves back
        with them.
        """
        loaded = self.carried.conversation() or []
        folded = int(previous.get("recap_folded", 0) or 0)
        carried, folded = drop_stored_recap_frames(loaded, folded)
        if len(carried) != len(loaded):
            # A repair, not a silent edit: the record says how many frames went.
            self.record(
                "conversation_repaired",
                dropped=len(loaded) - len(carried),
                kept=len(carried),
            )
        seeded_by_duty = False
        if carried:
            self.messages.extend(carried)
            # The fold point persists in run.json, so a resumed run does not
            # fold the same messages twice. A duty may have shortened the file
            # between runs; the point then cannot lie past its end.
            self.recap_folded = min(folded, len(carried))

        handoff = self.carried.handoff()
        if handoff:
            self.messages.append(
                {
                    "role": "user",
                    "content": "A previous run of you left this handoff note:\n\n" + handoff,
                }
            )
            seeded_by_duty = True

        if not self.messages:
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
        return bool(carried or seeded_by_duty)


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------
def selection(
    messages: list[dict], budget_tokens: int, chunk_tokens: int | None = None
) -> tuple[list[int], int]:
    """Which messages a request would send, and where the moving window starts.

    Returns `(indices, start)`: everything to send, in order, and the index from
    which the tail of the conversation is kept whole. The two differ because the
    send view is **not** a contiguous range.

    System messages and the first user message are *pinned* once they exist --
    the run's standing instructions and its opening problem. They are sent
    whether or not the budget would have room for them at their age, and they
    are the one thing a long run cannot afford to lose: a run that has dropped
    its opening problem no longer knows what it is doing.

    Everything else is a moving tail. Its start advances in chunks counted from
    the beginning of the history, so the boundary holds still for several turns
    instead of creeping one message per turn. That is the difference between
    consecutive requests sharing a cacheable prefix and re-reading the prompt
    every time.

    The tail never opens on a tool result whose call has been dropped. Every
    upstream rejects a tool message with no assistant call in front of it, so a
    window that opened on one would turn a long run into a crash loop -- and the
    crash would look like a model fault rather than a windowing one.
    """
    if budget_tokens <= 0:
        return list(range(len(messages))), 0
    if chunk_tokens is None:
        configured = env_optional_int("CONTEXT_WINDOW_EVICTION_TOKENS")
        chunk_tokens = configured if configured else max(1, budget_tokens // 8)

    pinned = {index for index, message in enumerate(messages) if message.get("role") == "system"}
    first_user = next(
        (index for index, message in enumerate(messages) if message.get("role") == "user"), None
    )
    if first_user is not None:
        pinned.add(first_user)

    def length(index: int) -> int:
        return len(json.dumps(messages[index], ensure_ascii=False))

    running = sum(length(index) for index in pinned)
    start = len(messages)
    for index in range(len(messages) - 1, -1, -1):
        if index in pinned:
            continue
        running += length(index)
        if (running // 4) > budget_tokens and index < len(messages) - 1:
            start = index + 1
            break
        start = index

    start = _advance_to_chunk(start, length, chunk_tokens)
    start = _whole_unit_start(messages, start)

    return sorted(pinned | set(range(start, len(messages)))), start


def _whole_unit_start(messages: list[dict], start: int) -> int:
    """Move a window start that falls inside a tool group to a unit boundary.

    A group (an assistant message with tool calls, and the tool and system
    messages after it) is sent whole or not at all. If the start falls inside
    a group, it moves forward to the next unit when there is one -- the group
    it cut is older and is dropped whole -- and otherwise back to the group's
    head: that group is the newest material, and it is kept whole even when it
    alone exceeds the estimated window (SV-015 v2 section 2.3 accepts that one
    newest unit can). A standalone tool message, answering nothing, is skipped
    as before. The index returned is into the original list, so the recap's
    fold boundary is the same group boundary.
    """
    within = inside_group(messages)

    def tail(index: int) -> bool:
        return within[index] or messages[index].get("role") == "tool"

    if start >= len(messages) or not tail(start):
        return start
    following = next((index for index in range(start + 1, len(messages)) if not tail(index)), None)
    if following is not None:
        return following
    head = start
    while head > 0 and within[head]:
        head -= 1
    return head if within[start] else start


def inside_group(messages: list[dict]) -> list[bool]:
    """For each message, whether it sits inside a tool group (after the group's head).

    A group is an assistant message with tool calls and the run of tool and
    system messages that follows it. Only the assistant message is a unit
    boundary.
    """
    flags = [False] * len(messages)
    open_group = False
    for index, message in enumerate(messages):
        role = message.get("role")
        if open_group and role in ("tool", "system"):
            flags[index] = True
            continue
        open_group = role == "assistant" and bool(message.get("tool_calls"))
    return flags


# What the outgoing view says for a call with no recorded result. It is a
# statement of ignorance, not of non-execution: the call may well have run.
REPAIRED_UNKNOWN_RESULT = (
    "outcome unknown: no result for this call is in the conversation; "
    "it may or may not have run"
)
ORPHAN_NOTICE = "[orphan tool result for {call_id}]: {content}"


def repair_structure(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """A copy of `messages` with tool results ordered and paired, and what was changed.

    What this repairs is ordering and pairing only. It does not make duplicate
    or invalid provider ids valid, and it does not establish that any provider
    accepts the result: provider schema and id acceptance stay unvalidated.

    Every assistant message with tool calls is followed at once by exactly one
    tool message per call, in call order. A missing result is synthesized with
    REPAIRED_UNKNOWN_RESULT; a system message found inside a group moves to
    just after it; a tool message that answers no pending call -- a stray, or
    a second answer to the same call -- becomes a user-role notice
    `"[orphan tool result for <id>]: <content>"` at the same place. Messages
    that need no change are the same objects. Repair is idempotent.

    This is the *outgoing view*. It never edits the stored conversation, whose
    indices the recap's fold point refers to, and a synthesized result is
    never evidence that a call did not run.
    """
    repaired: list[dict] = []
    notes: list[dict] = []

    def orphan(message: dict) -> dict:
        content = message.get("content")
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        notes.append({"kind": "orphan", "tool_call_id": message.get("tool_call_id")})
        return {"role": "user", "content": ORPHAN_NOTICE.format(call_id=message.get("tool_call_id"), content=text)}

    index = 0
    while index < len(messages):
        message = messages[index]
        role = message.get("role")
        calls = message.get("tool_calls") if role == "assistant" else None
        if not calls:
            repaired.append(orphan(message) if role == "tool" else message)
            index += 1
            continue
        following = index + 1
        while following < len(messages) and messages[following].get("role") in ("tool", "system"):
            following += 1
        trailing = messages[index + 1 : following]
        unmatched = [item for item in trailing if item.get("role") == "tool"]
        repaired.append(message)
        for call in calls:
            call_id = call.get("id") if isinstance(call, dict) else None
            match = next((item for item in unmatched if item.get("tool_call_id") == call_id), None)
            if match is not None:
                unmatched = [item for item in unmatched if item is not match]
                repaired.append(match)
                continue
            function = call.get("function") if isinstance(call, dict) else None
            name = function.get("name") if isinstance(function, dict) else None
            repaired.append(
                {"role": "tool", "tool_call_id": call_id, "name": name, "content": REPAIRED_UNKNOWN_RESULT}
            )
            notes.append({"kind": "synthetic_result", "tool_call_id": call_id})
        seen_tool = False
        for item in reversed(trailing):
            if item.get("role") == "tool":
                seen_tool = True
            elif seen_tool:
                notes.append({"kind": "moved_system"})
        for item in trailing:
            if item.get("role") == "system":
                repaired.append(item)
            elif any(item is stray for stray in unmatched):
                repaired.append(orphan(item))
        index = following
    return repaired, notes


def _advance_to_chunk(start: int, length, chunk_tokens: int) -> int:
    """Move the window's start forward, but only in whole chunks of history.

    The number of chunks is derived from how much history there is in total, so
    it steps up by one *per chunk of added material* rather than per turn. That
    is what makes the boundary hold still while a conversation grows a message
    at a time -- and a boundary that holds still is what lets consecutive
    requests share a long prefix instead of re-reading the whole prompt.

    Deriving the edge from the live start instead would make it a constant, the
    start would follow the budget one message per turn, and the cache would
    never see the same prefix twice.
    """
    if chunk_tokens <= 0:
        return start
    chunk_chars = 4 * chunk_tokens
    total_chars = 0
    for index in range(start):
        total_chars += length(index)
    if total_chars < chunk_chars:
        return start
    edge = (total_chars // chunk_chars) * chunk_chars
    consumed = 0
    moved = start
    for index in range(start):
        if index >= start or consumed >= edge:
            break
        consumed += length(index)
        moved = index + 1
    return moved


def window_bounds(
    messages: list[dict], budget_tokens: int, chunk_tokens: int | None = None
) -> tuple[int, int]:
    """The moving tail of the window, as `(start index, count)`.

    The pinned messages are not part of this range; `selection` returns the full
    send view. This narrower helper exists because the recap needs only the tail
    boundary -- what is about to fall out of the moving part.
    """
    if budget_tokens <= 0:
        return 0, len(messages)
    _, start = selection(messages, budget_tokens, chunk_tokens)
    return start, max(0, len(messages) - start)


def prepared_view(
    messages: list[dict],
    budget_tokens: int,
    chunk_tokens: int | None,
    carried: Carried,
) -> list[dict]:
    """The messages to send: the window, with the recap pinned in front.

    The recap is inserted here rather than stored in the conversation, so it is
    always current, never duplicated, and never itself evicted by the window it
    is reporting on.

    The selected messages are then repaired as a view (`repair_structure`):
    every call answered once, in place, and nothing stray -- so a conversation
    a duty edited, or a run that ended mid-group, still sends tool results in
    a well-ordered, fully paired form. That is ordering and pairing only;
    whether a provider accepts the request (its schema, its ids) is not
    established here. The stored list is not touched.
    """
    indices, _ = selection(messages, budget_tokens, chunk_tokens)
    kept, _repairs = repair_structure([messages[index] for index in indices])
    recap = carried.recap()
    if not recap:
        return kept
    framed = {"role": "system", "content": RECAP_FRAME_PREFIX + recap}
    if any(message.get("content") == framed["content"] for message in kept):
        return kept
    return [framed, *kept]


def render_message(message: dict) -> str:
    """A message as one line of recap-sized text."""
    content = message.get("content")
    if isinstance(content, list):
        content = " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    text = str(content or "")
    calls = message.get("tool_calls") or []
    if calls:
        names = ", ".join(str(call.get("function", {}).get("name", "?")) for call in calls)
        text = f"{text} [called: {names}]".strip()
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# Fault classification
# ---------------------------------------------------------------------------
EXHAUSTION_PHRASES = (
    "insufficient credit",
    "insufficient_quota",
    "quota exceeded",
    "exceeded your current quota",
)


def classify(error: Exception) -> Exception:
    """Turn a client exception into one the run's caller can act on.

    A refusal from the recorder arrives as a 429 whose body names the limit it
    hit, and that sentence is the whole diagnosis. It travels with the note, so
    an operator reading the lifecycle record or the review panel sees which
    ceiling stopped the run rather than only that something did.
    """
    """Turn a client exception into one the run's caller can act on.

    The one judgement worth stating: a spent balance is not the run's fault.
    Repairing the request changes nothing, so it must not tombstone the run --
    it pauses it, which is what exit 44 means.
    """
    status = getattr(error, "status_code", None)
    text = str(error).lower()
    if any(phrase in text for phrase in EXHAUSTION_PHRASES):
        return EnvironmentFailure(f"the model budget is spent: {error}")
    if status in (402, 408, 409, 429):
        return EnvironmentFailure(f"transient upstream status {status}: {error}")
    if isinstance(status, int) and 500 <= status < 600:
        return EnvironmentFailure(f"upstream fault {status}: {error}")
    if status is None:
        return EnvironmentFailure(f"the recorder could not be reached: {error}")
    return DutyFault(f"the request was refused and repairing it is the duty's job: {error}")


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the duty once.")
    parser.add_argument("--status", action="store_true", help="print this run's facts and exit")
    parser.add_argument("--entry", help="override AGENT_ENTRY for this run")
    args = parser.parse_args(argv)

    chassis = Chassis()
    if args.entry:
        chassis.entry = Path(args.entry)
    if args.status:
        print(json.dumps(chassis.status(), indent=2))
        return EXIT_OK

    print(
        f"[chassis] {chassis.slug} ({chassis.name}) run {chassis.run_id} "
        f"entry={chassis.entry} model={chassis.model}",
        flush=True,
    )
    try:
        return chassis.run()
    except EnvironmentFailure as failure:
        print(f"[chassis] environment failure: {failure}", flush=True)
        return EXIT_ENVIRONMENT
    except DutyFault as fault:
        print(f"[chassis] duty fault: {fault}", flush=True)
        return EXIT_DUTY_FAULT


if __name__ == "__main__":
    # Launched as a script (as the supervisor does), this module is
    # `__main__`. A duty that imports `chassis` -- or the seed's
    # `_load_runtime`, which looks in sys.modules first -- must get *this*
    # module, not a second copy of the same file: a second copy has its own
    # exception classes, so a duty's `chassis.EnvironmentFailure` would not be
    # the class this runtime catches, and its ToolRegistry not the one it
    # reads. Binding the name before any duty code is loaded keeps one runtime.
    sys.modules["chassis"] = sys.modules[__name__]
    sys.exit(main())
