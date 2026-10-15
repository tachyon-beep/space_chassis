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
import importlib.util
import inspect
import json
import os
import sys
import time
import traceback
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
        """Append a user-role message without calling the model."""
        self._chassis.messages.append({"role": "user", "content": text})

    def note(self, text: str) -> None:
        """Append a system-role message -- a fact for the model, not a turn."""
        self._chassis.messages.append({"role": "system", "content": text})

    def history(self) -> list[dict]:
        """The conversation so far. A copy; edits here do not take effect."""
        return [dict(message) for message in self._chassis.messages]

    def set_history(self, messages: list[dict]) -> None:
        """Replace the conversation. The duty owns it and may prune it."""
        if not isinstance(messages, list):
            raise ValueError("history must be a list of messages")
        self._chassis.messages[:] = messages

    def ask(self, text: str, tools: bool = True) -> str:
        """One model call with `text` as the newest user message; returns its text."""
        return self._chassis.turn_once(text, use_tools=tools)

    # -- ending the run -----------------------------------------------------
    def handoff(self, note: str) -> None:
        """End this run on purpose, leaving `note` for the run that follows."""
        self._chassis.write_handoff(note)
        raise SystemExit(EXIT_HANDOFF)

    def finish(self, note: str = "") -> None:
        """End this run cleanly. The next run starts, and resumes if it can."""
        if note:
            self._chassis.write_handoff(note)
        raise SystemExit(EXIT_OK)


def estimate_tokens(messages: list[dict]) -> int:
    """A cheap estimate of the conversation's size, in the units the window is in.

    Serialised length over four. It does not need to be right; it needs to be
    monotone in the thing that matters, which is how much text is being sent.
    """
    return len(json.dumps(messages, ensure_ascii=False)) // 4


def chassis_budget(chassis: Chassis) -> int:
    return chassis.context_window


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
        for call in tool_calls:
            result = self.invoke(call.function.name, call.function.arguments)
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.function.name,
                    "content": result,
                }
            )
        self.checkpoint()
        self.record("turn", tools=len(tool_calls), usage=dict(self.usage_totals))
        self.check_budgets()
        return content

    def invoke(self, name: str, arguments: str) -> str:
        """Run one registered tool by name. Every failure becomes text.

        A tool that raises is information the model can act on, so the error is
        handed back rather than ending the run -- except for the two ends the
        duty can ask for, which travel as SystemExit.
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
        except SystemExit:
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
    def checkpoint(self) -> None:
        self.carried.save_conversation(self.messages)
        self.carried.save_meta(
            {
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
            }
        )

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
        meta = self.carried.meta()
        return {
            "agent": self.slug,
            "name": self.name,
            "run": self.run_id,
            "entry": str(self.entry),
            "model": self.model,
            "turn_this_run": self.turn,
            "turns_before_this_run": meta.get("turn"),
            "previous_run_ended": meta.get("ended"),
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
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.home_dir.mkdir(parents=True, exist_ok=True)
        previous = self.carried.meta()
        self.record(
            "run_start", entry=str(self.entry), model=self.model, window=self.context_window
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
        note = ""
        try:
            main(self.context)
            note = "the run's main() returned without ending the run"
        except SystemExit as stop:
            if isinstance(stop.code, str):
                exit_code, note = EXIT_OK, stop.code
            else:
                exit_code = int(stop.code or EXIT_OK)
            if not note:
                note = self.last_handoff
        except TurnLimitReached as reached:
            exit_code, note = EXIT_HANDOFF, str(reached)
        except WallLimitReached as reached:
            exit_code, note = EXIT_HANDOFF, str(reached)
        except DutyFault as fault:
            exit_code = EXIT_DUTY_FAULT
            note = str(fault)
        except EnvironmentFailure as failure:
            exit_code = EXIT_ENVIRONMENT
            note = str(failure)
        except KeyboardInterrupt:
            exit_code = EXIT_ENVIRONMENT
            note = "interrupted"
        except BaseException as error:  # noqa: BLE001 -- the run ends; the record survives
            exit_code = EXIT_DUTY_FAULT
            note = f"{type(error).__name__}: {error}"
            self.record(
                "run_traceback",
                traceback="".join(traceback.format_exception(error))[-8000:],
            )
        finally:
            with contextlib.suppress(Exception):
                self.checkpoint()
            if resumed and exit_code not in RESUMING_EXITS:
                # The run ended in a way that does not carry the conversation.
                # The checkpoint stays on disk -- it is the record of what this
                # run was thinking, and the ladder may want it -- but the next
                # run will not open it.
                self.record("run_ended_unresumable", exit=exit_code)
            self.record(
                "run_end",
                exit=exit_code,
                note=note[:2000],
                turns=self.turn,
                usage=dict(self.usage_totals),
            )
            print(
                f"[chassis] run ended: exit={exit_code} turns={self.turn} note_chars={len(note)} {note[:300]}",
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
            self.recap_folded = folded

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
    while start < len(messages) - 1 and messages[start].get("role") == "tool":
        start += 1

    return sorted(pinned | set(range(start, len(messages)))), start


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
    """
    indices, _ = selection(messages, budget_tokens, chunk_tokens)
    kept = [messages[index] for index in indices]
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
    sys.exit(main())
