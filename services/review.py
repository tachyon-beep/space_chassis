#!/usr/bin/env python3
"""The review panel: what an operator can read, and nothing else.

The fleet monitor answers "is the world working". This answers "what did that
agent actually think", which is a different question and needs a different
view: the conversation, the reasoning, every tool call with the result that
came back, what each turn cost, and how the supervisor and the pump treated it.

Four properties are deliberate.

* **It reads the record, never the agents.** Everything here comes from files
  written by other processes: the recorder's transcript, the supervisor's
  lifecycle log, the pump's state. An agent's account of itself is not
  evidence, and this panel does not ask for one.
* **It cannot change anything.** Every mount is read-only, the container's
  root filesystem is read-only, and there is no code path in this file that
  opens a file under the record for writing. A test asserts it at the source
  level, in the spirit of the recorder's "no header is ever written" check.
* **It has no route outward.** It sits on its own internal network with no
  gateway -- not the fleet's network, not the model's. It needs an address only
  so the operator's browser can reach it.
* **It stays cheap as the record grows.** This world's transcripts already run
  to fifteen megabytes after seventeen turns, because every request repeats the
  whole conversation. Nothing here reads a file whole: the newest turns are
  taken from a byte-bounded tail, parsed forward from a line boundary, and
  cached against the file's size and modification time.

The last point is what makes the panel usable, and it is also the subtle part.
A turn's new material is not stored as a delta -- it is the difference between
two consecutive requests. Reassembling it means knowing how many messages each
request carried, which the recorder's `open` events record exactly.
"""

from __future__ import annotations

import contextlib
import html
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

SERVICES_DIR = Path(os.environ.get("SERVICES_DIR", "/opt/services"))
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))

from common import env_int, iso, read_bounded, read_json  # noqa: E402

TRANSCRIPTS_DIR = Path(os.environ.get("TRANSCRIPTS_DIR", "/transcripts"))
TELEMETRY_DIR = Path(os.environ.get("TELEMETRY_DIR", "/telemetry"))
WORK_DIR = Path(os.environ.get("WORK_DIR", "/work"))
HOME_ROOT = Path(os.environ.get("HOME_ROOT", "/home"))
PUMP_ROOT = Path(os.environ.get("PUMP_ROOT", "/pump"))

# How much of a file's tail is read to serve one page. A turn's line holds the
# whole conversation, so a turn costs roughly the size of the conversation:
# megabytes in a real run, and growing. This window is a handful of turns at
# that size, which is enough to read the recent shape of a conversation without
# touching the whole of a file that grows without bound.
MAX_BYTES = env_int("REVIEW_MAX_BYTES", 32 * 1024 * 1024)
# The most turns one request will parse out of that window.
MAX_TURNS = env_int("REVIEW_MAX_TURNS", 200)
DEFAULT_TURNS = env_int("REVIEW_DEFAULT_TURNS", 25)
# Turns kept per agent in memory, keyed by the file's size and mtime.
CACHE_TURNS = env_int("REVIEW_CACHE_TURNS", 200)
# Per-field display caps. These are legibility, not storage: the untruncated
# record is one click away at /api/agent/<slug>/turn/<n>/raw.
TEXT_CAP = env_int("REVIEW_TEXT_CAP", 20_000)
RESULT_CAP = env_int("REVIEW_RESULT_CAP", 4_000)
ARGS_CAP = env_int("REVIEW_ARGS_CAP", 4_000)
SUMMARY_CAP = 240

TRUNCATED = "… [truncated for display; the untruncated record is at {}]"

# Providers differ, and this world has seen both spellings.
REASONING_FIELDS = ("reasoning_content", "reasoning")


# ---------------------------------------------------------------------------
# Reading, bounded
# ---------------------------------------------------------------------------
def transcript_path(slug: str) -> Path:
    return TRANSCRIPTS_DIR / slug / "agent_life_transcript.jsonl"


def events_path(slug: str) -> Path:
    return TRANSCRIPTS_DIR / slug / "events.jsonl"


def lifecycle_path(slug: str) -> Path:
    return TELEMETRY_DIR / "agents" / slug / "lifecycle.jsonl"


def file_state(path: Path) -> tuple[int, int]:
    """`(size, mtime_ns)`, or `(0, 0)` when the file is not there yet.

    This is the cache key. A poll that finds no change costs one `stat` and
    nothing else, which is what makes it affordable to ask for the newest turns
    every few seconds while a fleet is running.
    """
    try:
        stat = path.stat()
    except OSError:
        return (0, 0)
    return (stat.st_size, stat.st_mtime_ns)


def tail_jsonl(
    path: Path,
    max_bytes: int = MAX_BYTES,
    max_records: int = MAX_TURNS,
    chunk: int = 1 << 20,
) -> tuple[list[dict], bool, int]:
    """The newest records in a JSONL file, and whether there are older ones.

    Every reader in this service goes through here, so `read_lines` below has a
    single answer to "how much of the record did that cost".
    """
    return read_lines(path, max_bytes, max_records, chunk)


def read_lines(
    path: Path,
    max_bytes: int = MAX_BYTES,
    max_records: int = MAX_TURNS,
    chunk: int = 1 << 20,
) -> tuple[list[dict], bool, int]:
    """The newest records in a JSONL file: `(records, more_available, line_total)`.

    Read backwards from the end in fixed-size blocks, parsing forward from the
    first complete line in the window. Two consequences are intended:

    * a partial line -- one a writer is halfway through, which is normal on a
      file that is appended to while it is read -- is discarded rather than
      parsed hopefully;
    * a line larger than the window is reported as *not loaded* rather than
      raising or returning half a turn. A caller that is told "not loaded" can
      say so; one that is handed a truncated JSON object cannot tell the
      difference between that and a corrupt record.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return ([], False, 0)
    if size == 0:
        return ([], False, 0)

    window = b""
    position = size
    while position > 0 and len(window) < max_bytes:
        # Never read past the window: this is what keeps the work bounded by
        # `max_bytes` rather than by the size of the file.
        step = min(chunk, position, max_bytes - len(window))
        position -= step
        with open(path, "rb") as handle:
            handle.seek(position)
            block = handle.read(step)
        window = block + window

    # Drop the leading partial line -- but only when the window really does
    # begin in the middle of the file. A window that starts at byte zero begins
    # at the start of a record, and dropping it there loses a whole turn.
    if position > 0:
        first_newline = window.find(b"\n")
        if first_newline == -1:
            # One record longer than the entire window. Report it as not loaded
            # rather than handing back half of it.
            return ([], True, 0)
        window = window[first_newline + 1 :]

    lines = window.split(b"\n")
    # A file whose last byte is not a newline ends mid-record: the writer is in
    # the middle of an append, which is the normal condition of a file that is
    # written to while it is read. That trailing fragment is a race rather than
    # a corrupt record, and keeping it would put a fake error line at the top of
    # every page an operator looks at while the fleet is running.
    if lines and lines[-1] != b"":
        lines.pop()

    records: list[dict] = []
    for raw in lines:
        if not raw.strip():
            continue
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            # A line bounded by newlines on both sides is genuinely corrupt:
            # nothing was writing it, so it is reported rather than dropped.
            records.append({"__unparseable__": True, "bytes": len(raw)})
            continue
        if isinstance(record, dict):
            records.append(record)

    # "More" answers whether this window is the whole file. A window that began
    # mid-file has records before it that were not read, and a window that hit
    # the record cap has more than it is showing; either way there is more.
    total = len(records)
    trimmed = total > max_records
    return (records[-max_records:], position > 0 or trimmed, total)


def load_events(slug: str, max_bytes: int = MAX_BYTES) -> dict[str, dict]:
    """The recorder's `open`/`close` events, keyed by request id.

    `open` carries the message count of each request, which is what makes a
    turn's delta exact rather than a guess. `close` carries the status and the
    elapsed time. Both are optional: an events file that is absent, truncated
    or malformed leaves the corresponding fields null, and the panel says so
    rather than refusing to show the turn.
    """
    records, _more, _total = read_lines(events_path(slug), max_bytes=max_bytes, max_records=10_000)
    events: dict[str, dict] = {}
    for record in records:
        if record.get("__unparseable__"):
            continue
        key = record.get("id")
        if not isinstance(key, str):
            continue
        entry = events.setdefault(key, {})
        kind = record.get("event")
        if kind == "open":
            entry["messages"] = record.get("messages")
            entry["model"] = record.get("model")
            entry["opened_at"] = record.get("at")
        elif kind == "close":
            entry["status"] = record.get("status")
            entry["duration_seconds"] = record.get("duration_seconds")
            entry["usage"] = record.get("usage")
            if record.get("refusal"):
                entry["refusal"] = record["refusal"]
    return events


# ---------------------------------------------------------------------------
# One turn
# ---------------------------------------------------------------------------
def clip(text: str, cap: int, pointer: str = "") -> str:
    if not isinstance(text, str) or len(text) <= cap:
        return text if isinstance(text, str) else ""
    note = TRUNCATED.format(pointer) if pointer else "… [truncated for display]"
    return text[:cap] + "\n" + note


def message_text(message: dict) -> str:
    """A message's text, whatever shape the content arrived in.

    Multimodal content is a list of parts; a panel that showed `[object]` for
    an image-bearing turn would hide the turn. Text parts are joined and
    anything else is named.
    """
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                if isinstance(part.get("text"), str):
                    parts.append(part["text"])
                elif part.get("type"):
                    parts.append(f"[{part['type']}]")
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def reasoning_text(message: dict) -> str:
    """The model's reasoning, under whichever name the provider used."""
    for field in REASONING_FIELDS:
        value = message.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def parse_arguments(raw) -> tuple[object, str | None]:
    """A tool call's arguments, parsed if they are JSON, kept raw if they are not.

    A model that emits malformed arguments is a thing that happens, and the
    panel showing `{}` for it would hide the most interesting part of the turn.
    """
    if not isinstance(raw, str):
        return (raw if raw is not None else {}, None)
    try:
        return (json.loads(raw), None)
    except json.JSONDecodeError as error:
        return (raw, str(error))


def extract_calls(message: dict, pointer: str) -> list[dict]:
    calls = message.get("tool_calls")
    if not isinstance(calls, list):
        return []
    out: list[dict] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        arguments, error = parse_arguments(function.get("arguments"))
        out.append(
            {
                "id": call.get("id"),
                "name": function.get("name") or "(unnamed)",
                "arguments": arguments if isinstance(arguments, str) else _jsonable(arguments),
                "arguments_raw": isinstance(arguments, str),
                "arguments_error": error,
                "arguments_display": clip(
                    arguments if isinstance(arguments, str) else json.dumps(arguments, indent=2),
                    ARGS_CAP,
                    pointer,
                ),
            }
        )
    return out


def _jsonable(value):
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value


def pair_tool_results(calls: list[dict], following_request: dict | None) -> list[dict]:
    """Attach each call's result from the request that followed it.

    A tool's output is not in the turn that called it: it arrives as a
    `role: "tool"` message in the *next* request. Pairing is by `tool_call_id`
    where the model supplied one, and by order otherwise -- an unmatched result
    is attached to the last call rather than dropped, because a result with no
    home is a fact and a missing result is a different fact.
    """
    if not calls:
        return []
    results: list[dict] = []
    if isinstance(following_request, dict):
        for message in following_request.get("messages") or []:
            if isinstance(message, dict) and message.get("role") == "tool":
                results.append(message)
    # Only the results that answer these calls: the window may include older
    # ones, and attributing a previous turn's result to this call would be worse
    # than showing nothing.
    wanted = {call["id"] for call in calls if call.get("id")}
    if wanted:
        results = [
            r for r in results if r.get("tool_call_id") in wanted or not r.get("tool_call_id")
        ]

    by_id = {r.get("tool_call_id"): r for r in results if r.get("tool_call_id")}
    unkeyed = [r for r in results if not r.get("tool_call_id")]
    for call in calls:
        result = by_id.get(call.get("id"))
        if result is None and unkeyed:
            # A result the model did not key to a call is attached in order
            # rather than dropped. It answers *something* in this turn, and a
            # result with no home is a fact while a missing one is a different
            # fact -- the panel should not conflate them.
            result = unkeyed.pop(0)
        if result is None:
            continue
        call["result"] = {
            "name": result.get("name") or call["name"],
            "display": clip(message_text(result), RESULT_CAP),
            "chars": len(message_text(result)),
        }
    return calls


def new_messages(
    request: dict, previous_request: dict | None, previous_count: int | None
) -> list[dict]:
    """The messages this request carried that the previous one did not.

    Exact when the previous request is in the window: the message counts are
    known, so the new messages are the tail of the list. When it is not -- the
    first turn of a window -- the caller gets everything, labelled as such,
    rather than a silent misattribution.
    """
    messages = request.get("messages")
    if not isinstance(messages, list):
        return []
    if previous_request is None:
        return []
    previous = previous_request.get("messages")
    if not isinstance(previous, list) or previous_count is None:
        return messages[previous_count:] if previous_count else messages
    return messages[len(previous) :]


def turn_from(
    record: dict,
    index: int,
    previous_request: dict | None,
    following_request: dict | None,
    events: dict[str, dict],
) -> dict:
    """One turn, as the panel shows it: what was new, and what came back."""
    request = record.get("request") if isinstance(record.get("request"), dict) else {}
    response = record.get("response") if isinstance(record.get("response"), dict) else {}
    request_id = record.get("id")
    event = events.get(request_id, {}) if isinstance(request_id, str) else {}

    choices = response.get("choices")
    choice = (
        choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    )
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}

    pointer = f"/api/agent/{record.get('agent', '')}/turn/{index}/raw"
    calls = pair_tool_results(extract_calls(message, pointer), following_request)

    messages = request.get("messages") if isinstance(request.get("messages"), list) else []
    previous_count = event.get("messages")
    fresh = new_messages(request, previous_request, previous_count)

    tools = request.get("tools") if isinstance(request.get("tools"), list) else []
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else event.get("usage")

    return {
        "index": index,
        # A page's index is a position inside the loaded window and moves as the
        # window does; the request id is stable for the life of the record and
        # is what anyone quoting a turn should use.
        "id": request_id,
        "at": record.get("at"),
        "status": record.get("status", event.get("status")),
        "refusal": event.get("refusal"),
        "duration_seconds": event.get("duration_seconds"),
        "usage": usage if isinstance(usage, dict) else None,
        "finish_reason": choice.get("finish_reason"),
        "model": request.get("model") or event.get("model"),
        "tools_offered": len(tools),
        "tools_offered_names": [
            t.get("function", {}).get("name")
            for t in tools
            if isinstance(t, dict) and isinstance(t.get("function"), dict)
        ],
        "response_text": clip(message_text(message), TEXT_CAP, pointer),
        "reasoning": clip(reasoning_text(message), TEXT_CAP, pointer),
        "tool_calls": calls,
        "new_messages": [
            {
                "role": m.get("role"),
                "text": clip(message_text(m), TEXT_CAP, pointer),
                "tool_calls": len(m.get("tool_calls") or [])
                if isinstance(m.get("tool_calls"), list)
                else 0,
            }
            for m in fresh
            if isinstance(m, dict)
        ],
        "context_messages": len(messages),
        "delta_known": previous_request is not None,
        "unparseable": bool(record.get("__unparseable__")),
    }


# ---------------------------------------------------------------------------
# A view over one agent
# ---------------------------------------------------------------------------
class Conversation:
    """The newest turns of one agent, cached against the file's own state.

    A rebuild parses at most `MAX_BYTES` of the tail. Consecutive requests
    against an unchanged file cost one `stat`.
    """

    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.path = transcript_path(slug)
        self.state = (0, 0)
        self.turns: list[dict] = []
        self.more_available = False
        self.total_bytes = 0
        self.parsed_at: float | None = None
        self.error: str | None = None
        self.approximate_total: int | None = None
        self._lock = threading.Lock()

    def refresh(self, force: bool = False) -> Conversation:
        state = file_state(self.path)
        with self._lock:
            if not force and state == self.state and self.parsed_at is not None:
                return self
            self.state = state
            self.total_bytes = state[0]
            self.parsed_at = time.time()
            self.error = None
            if state[0] == 0:
                self.turns, self.more_available = [], False
                return self
            try:
                records, more, _count = tail_jsonl(self.path, MAX_BYTES, CACHE_TURNS)
                events = load_events(self.slug, MAX_BYTES)
                self.turns = self._build(records, events)
                self.more_available = more or len(records) >= CACHE_TURNS
            except OSError as error:
                self.error = f"could not read the transcript: {error}"
                self.turns, self.more_available = [], False
            return self

    def _build(self, records: list[dict], events: dict[str, dict]) -> list[dict]:
        requests = [
            record.get("request") if isinstance(record.get("request"), dict) else {}
            for record in records
        ]
        turns: list[dict] = []
        for offset, record in enumerate(records):
            previous = requests[offset - 1] if offset > 0 else None
            following = requests[offset + 1] if offset + 1 < len(requests) else None
            turns.append(turn_from(record, offset, previous, following, events))
        return turns

    def page(self, limit: int, before: int | None) -> tuple[list[dict], int]:
        """The newest `limit` turns, oldest first, optionally ending before `before`.

        One order for everything that consumes this: a window of turns in the
        order they happened, with the caller free to reverse it for display.
        Two reversals in two places is how a conversation ends up rendered
        backwards with every individual check still passing.
        """
        with self._lock:
            turns = list(self.turns)
        end = len(turns) if before is None else max(0, min(before, len(turns)))
        start = max(0, end - limit)
        return (turns[start:end], len(turns))

    def raw(self, index: int) -> dict | None:
        """The untruncated record for one turn in the window."""
        with self._lock:
            if index < 0 or index >= len(self.turns):
                return None
        try:
            records, _more, _count = tail_jsonl(self.path, MAX_BYTES, CACHE_TURNS)
        except OSError:
            return None
        if index >= len(records):
            return None
        return records[index]


CONVERSATIONS: dict[str, Conversation] = {}
CONVERSATIONS_LOCK = threading.Lock()


def conversation(slug: str) -> Conversation:
    with CONVERSATIONS_LOCK:
        view = CONVERSATIONS.get(slug)
        if view is None:
            view = CONVERSATIONS[slug] = Conversation(slug)
        return view


# ---------------------------------------------------------------------------
# The fleet, and the rest of the record
# ---------------------------------------------------------------------------
def announce_dir() -> Path:
    return Path(os.environ.get("ANNOUNCE_DIR", str(WORK_DIR / ".fleet")))


def discover_slugs() -> list[str]:
    """Every agent that has ever run, from the record rather than a list.

    Same reasoning as the recorder and the monitor: the names are drawn at
    random, so repeating them in configuration is a way to go stale. Here the
    transcript directory is also the list of agents that have actually spoken.
    """
    found: set[str] = set()
    if TRANSCRIPTS_DIR.is_dir():
        found |= {p.name for p in TRANSCRIPTS_DIR.iterdir() if p.is_dir()}
    agents = TELEMETRY_DIR / "agents"
    if agents.is_dir():
        found |= {p.name for p in agents.iterdir() if p.is_dir()}
    announced = announce_dir()
    if announced.is_dir():
        found |= {p.stem for p in announced.glob("*.agent")}
    return sorted(found)


def fleet_rows() -> list[dict]:
    rows = []
    for slug in discover_slugs():
        rows.append(agent_row(slug))
    return rows


def agent_row(slug: str) -> dict:
    """One agent's operational facts, from the record."""
    view = conversation(slug).refresh()
    lifecycle, _more, _count = tail_jsonl(lifecycle_path(slug), 512 * 1024, 400)
    ends = [r for r in lifecycle if r.get("event") == "run_end" and not r.get("__unparseable__")]
    decisions = [r for r in lifecycle if r.get("event") == "decision"]
    handoffs = [r for r in lifecycle if r.get("event") == "handoff"]
    meta = read_json(HOME_ROOT / slug / "session" / "run.json") or {}
    pump = read_json(PUMP_ROOT / slug / "state.json") or {}
    entries = pump.get("entries") if isinstance(pump.get("entries"), dict) else {}
    running = [
        name
        for name, record in entries.items()
        if isinstance(record, dict) and record.get("running")
    ]
    last = ends[-1] if ends else {}
    summary = read_bounded(HOME_ROOT / slug / "HANDOFF.md", 4096)

    context_window = meta.get("context_window")
    context_tokens = meta.get("context_tokens")
    pressure = None
    if isinstance(context_window, int) and context_window > 0 and isinstance(context_tokens, int):
        pressure = min(1.0, round(context_tokens / context_window, 4))

    return {
        "slug": slug,
        "turns_loaded": len(view.turns),
        "approximate_total": view.approximate_total,
        "more_available": view.more_available,
        "transcript_bytes": view.total_bytes,
        "transcript_error": view.error,
        "runs": sum(1 for r in lifecycle if r.get("event") == "run_start"),
        "last_exit": last.get("exit"),
        "last_note": (last.get("note") or "")[:SUMMARY_CAP],
        "last_tier": (decisions[-1].get("tier") if decisions else None),
        "handoffs": len(handoffs),
        "handoff_present": bool(summary),
        "handoff_head": (summary.decode("utf-8", "ignore")[:SUMMARY_CAP] if summary else ""),
        "context_pressure": pressure,
        "model": meta.get("model"),
        "turn_checkpoint": meta.get("turn"),
        "pump_running": running,
        "pump_entries": len(entries),
        "modified_at": (
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(view.state[1] / 1e9))
            if view.state[1]
            else None
        ),
    }


def fleet_summary(rows: list[dict]) -> dict:
    return {
        "at": iso(),
        "agents": len(rows),
        "turns": sum(row["turns_loaded"] for row in rows),
        "runs": sum(row["runs"] for row in rows),
        "bytes": sum(row["transcript_bytes"] for row in rows),
        "exits": sorted({row["last_exit"] for row in rows if row["last_exit"] is not None}),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
PAGE_STYLE = """
:root { color-scheme: dark; }
body { margin: 0; padding: 1.5rem; background: #14161a; color: #d8dee9;
       font: 14px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; }
a { color: #88c0d0; text-decoration: none; }
a:hover { text-decoration: underline; }
h1 { font-size: 1.25rem; font-weight: 600; margin: 0 0 1rem; }
h2 { font-size: 1rem; font-weight: 600; margin: 1.5rem 0 .5rem; color: #a3be8c; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid #26292f; }
th { color: #81a1c1; font-weight: 600; }
.turn { border: 1px solid #26292f; border-radius: 6px; margin: .75rem 0; background: #191c21; }
.turn > summary { cursor: pointer; padding: .6rem .8rem; display: block; }
.turn > summary::marker { color: #4c566a; }
.turn .body { padding: 0 .8rem .8rem; }
.meta { color: #7b8794; }
.warn { color: #ebcb8b; }
.bad { color: #bf616a; }
.ok { color: #a3be8c; }
pre { white-space: pre-wrap; word-wrap: break-word; margin: .4rem 0;
      padding: .6rem; background: #101216; border-radius: 4px; border-left: 3px solid #3b4252; }
pre.said { border-left-color: #5e81ac; }
pre.thought { border-left-color: #b48ead; color: #c9b6cf; }
pre.task { border-left-color: #d08770; }
pre.run { border-left-color: #a3be8c; }
.note { color: #7b8794; margin: 1rem 0; }
form { margin: .5rem 0; }
input, button { background: #22262c; color: #d8dee9; border: 1px solid #3b4252;
                border-radius: 4px; padding: .25rem .5rem; font: inherit; }
"""


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def position_label(index: int, loaded: int, approximate_total: int | None) -> str:
    """Where a turn sits in a conversation, from a bounded read.

    The panel reads a tail, so the exact number of turns before the window is
    not known without reading the whole file -- which is the thing the window
    exists to avoid. The label says so rather than implying a precision it does
    not have. The request id, shown beside it, is exact.
    """
    if not approximate_total or approximate_total <= loaded:
        return f"turn {index + 1} of {loaded}"
    return f"turn {index + 1} of about {approximate_total}"


def pressure_label(pressure) -> str:
    """How full the conversation is against the window it is sent in.

    Worth showing because it is the number that predicts, better than anything
    else here, when an agent is about to start losing the beginning of its own
    conversation. An em dash means the checkpoint has not said yet.
    """
    if not isinstance(pressure, float | int):
        return "—"
    return f"{int(round(pressure * 100))}%"


def page(title: str, body: str, *, refresh: int | None = None) -> bytes:
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        f"<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)}</title>{meta}<style>{PAGE_STYLE}</style></head><body>"
        f"{body}</body></html>"
    ).encode()


def render_fleet(rows: list[dict], summary: dict) -> bytes:
    head = (
        "<h1>space_chassis — the fleet</h1>"
        f"<p class=note>{esc(summary['agents'])} agent(s), {esc(summary['runs'])} run(s), "
        f"{esc(summary['turns'])} turn(s) in view, "
        f"{summary['bytes'] / 1e6:.1f} MB of transcript. Read-only: this panel opens the "
        "record, and nothing it does can change it.</p>"
    )
    if not rows:
        return page(
            "space_chassis — the fleet",
            head + "<p class=note>No agent has spoken yet. Once one takes a turn, its "
            "conversation appears here.</p>",
            refresh=10,
        )
    cells = "".join(
        "<tr>"
        f"<td><a href='/agent/{esc(r['slug'])}'>{esc(r['slug'])}</a></td>"
        f"<td>{esc(r['runs'])}</td>"
        f"<td>{esc(r['turns_loaded'])}{'…' if r['more_available'] else ''}</td>"
        f"<td class='{'ok' if r['last_exit'] in (0, 42) else 'bad' if r['last_exit'] else 'meta'}'>"
        f"{esc(r['last_exit'])}</td>"
        f"<td>{esc(r['last_tier'])}</td>"
        f"<td>{pressure_label(r['context_pressure'])}</td>"
        f"<td>{', '.join(esc(x) for x in r['pump_running']) or '—'}</td>"
        f"<td>{r['transcript_bytes'] / 1e6:.1f} MB</td>"
        "</tr>"
        for r in rows
    )
    table = (
        "<table><tr><th>agent</th><th>runs</th><th>turns</th><th>last exit</th><th>tier</th>"
        "<th>window</th><th>scheduled</th><th>transcript</th></tr>" + cells + "</table>"
    )
    return page("space_chassis — the fleet", head + table, refresh=15)


def render_turn(turn: dict, slug: str, position: str | None = None) -> str:
    pos = position or f"#{turn['index']}"
    status = turn.get("status")
    status_class = "ok" if status == 200 else ("bad" if status and status >= 400 else "meta")
    usage = turn.get("usage") or {}
    tokens = usage.get("total_tokens")
    pieces = [
        f"<b>{esc(pos)}</b> ",
        f"<span class=meta>{esc(turn['at'])}</span> ",
        f"<span class={status_class}>status {esc(status)}</span> ",
    ]
    if turn.get("duration_seconds") is not None:
        pieces.append(f"<span class=meta>{turn['duration_seconds']}s</span> ")
    if tokens:
        pieces.append(
            f"<span class=meta>{esc(tokens)} tokens "
            f"({esc(usage.get('prompt_tokens'))}+{esc(usage.get('completion_tokens'))})</span> "
        )
    pieces.append(f"<span class=meta>ctx {esc(turn['context_messages'])} msgs</span> ")
    if turn.get("finish_reason"):
        pieces.append(f"<span class=meta>{esc(turn['finish_reason'])}</span> ")
    if turn.get("tool_calls"):
        names = ", ".join(esc(c["name"]) for c in turn["tool_calls"])
        pieces.append(f"<span class=meta>→ {names}</span>")
    if turn.get("reasoning"):
        pieces.append(" <span class=meta>[thought]</span>")
    if turn.get("refusal"):
        pieces.append(f" <span class=bad>{esc(turn['refusal'])}</span>")

    if turn.get("unparseable"):
        return (
            f"<details class=turn><summary>{''.join(pieces)}"
            "<span class=bad> unparseable record</span></summary>"
            "<div class=body><p class=note>This line is not valid JSON. It is shown as a "
            "placeholder so one bad line does not hide the turns around it.</p></div></details>"
        )

    body: list[str] = []
    if turn.get("reasoning"):
        body.append("<h2>reasoning</h2>")
        body.append(f"<pre class=thought>{esc(turn['reasoning'])}</pre>")
    if turn.get("response_text"):
        body.append("<h2>said</h2>")
        body.append(f"<pre class=said>{esc(turn['response_text'])}</pre>")
    for call in turn.get("tool_calls") or []:
        body.append(f"<h2>tool call — {esc(call['name'])}</h2>")
        if call.get("arguments_error"):
            body.append(
                f"<p class=warn>arguments were not valid JSON ({esc(call['arguments_error'])}); "
                "the raw string is shown</p>"
            )
        body.append(f"<pre>{esc(call.get('arguments_display'))}</pre>")
        result = call.get("result")
        if result:
            body.append(
                f"<h2>result — {esc(result['name'])} "
                f"<span class=meta>{esc(result['chars'])} chars</span></h2>"
            )
            body.append(f"<pre class=run>{esc(result['display'])}</pre>")
        else:
            body.append(
                "<p class=note>No result is recorded for this call. A result appears in the "
                "record only once the next request carries it, so the newest turn of a "
                "conversation can be waiting for one.</p>"
            )
    for message in turn.get("new_messages") or []:
        if message.get("role") == "assistant":
            continue
        body.append(f"<h2>{esc(message.get('role'))}</h2>")
        body.append(f"<pre class=task>{esc(message.get('text'))}</pre>")
    if not body:
        body.append("<p class=note>This turn carries no new text.</p>")
    if not turn.get("delta_known"):
        body.append(
            "<p class=note>This is the oldest turn in the loaded window, so what was new in "
            "it cannot be separated from what came before.</p>"
        )
    if turn.get("tools_offered"):
        names = ", ".join(esc(n) for n in (turn.get("tools_offered_names") or []) if n)
        body.append(
            f"<p class=note>{esc(turn['tools_offered'])} tool(s) were offered to the model: "
            f"{names}</p>"
        )
    body.append(
        f"<p class=note><a href='/api/agent/{esc(slug)}/turn/{turn['index']}/raw'>raw record</a>"
        "</p>"
    )
    return (
        f"<details class=turn><summary>{''.join(pieces)}</summary>"
        f"<div class=body>{''.join(body)}</div></details>"
    )


def render_agent(row: dict, turns: list[dict], limit: int, before: int | None) -> bytes:
    slug = row["slug"]
    head = [
        f"<h1>{esc(slug)}</h1>",
        "<p class=note>",
        f"{esc(row['runs'])} run(s) · last exit "
        f"<span class='{'ok' if row['last_exit'] in (0, 42) else 'meta'}'>"
        f"{esc(row['last_exit'])}</span>",
        f" · tier {esc(row['last_tier'])}",
        f" · {row['transcript_bytes'] / 1e6:.1f} MB of transcript",
        f" · <a href='/'>fleet</a> · <a href='/api/agent/{esc(slug)}'>json</a>",
        "</p>",
    ]
    if row.get("last_note"):
        head.append(
            f"<p class=note>the last run ended: {esc(row['last_note'])} "
            "(this is the supervisor's record, not the agent's account)</p>"
        )
    if row.get("transcript_error"):
        head.append(f"<p class=bad>{esc(row['transcript_error'])}</p>")

    oldest = turns[0]["index"] if turns else None
    nav = []
    if oldest not in (None, 0):
        nav.append(f"<a href='/agent/{esc(slug)}?before={oldest}&limit={limit}'>← older</a>")
    if before is not None:
        nav.append(f"<a href='/agent/{esc(slug)}?limit={limit}'>newest →</a>")
    if nav:
        head.append(f"<p class=note>{' · '.join(nav)}</p>")
    if row["more_available"]:
        head.append(
            "<p class=note>Older turns are in the raw file and outside this window. This panel "
            "reads a bounded tail of it, because a transcript records the whole conversation "
            "on every turn and grows without bound.</p>"
        )

    total = row.get("approximate_total")
    body = "".join(
        render_turn(
            turn,
            slug,
            position_label(turn["index"], len(turns), total),
        )
        for turn in reversed(turns)
    )
    if not turns:
        body = (
            "<p class=note>No turns in the window yet. If this agent is running, its first "
            "turn will appear shortly.</p>"
        )
    return page(f"{slug} — space_chassis", "".join(head) + body, refresh=10 if not turns else None)


# ---------------------------------------------------------------------------
# The server
# ---------------------------------------------------------------------------
AGENT_ROUTE = re.compile(r"^/agent/(?P<slug>[A-Za-z0-9_-]+)/?$")
AGENT_API = re.compile(r"^/api/agent/(?P<slug>[A-Za-z0-9_-]+)/?$")
RAW_API = re.compile(r"^/api/agent/(?P<slug>[A-Za-z0-9_-]+)/turn/(?P<index>\d+)/raw/?$")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "space-chassis-review/0.1"

    def log_message(self, fmt, *args):  # noqa: A003 -- base class API
        pass

    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(payload)

    def _json(self, status: int, data) -> None:
        self._send(
            status, json.dumps(data, indent=2, default=str).encode("utf-8"), "application/json"
        )

    def _html(self, status: int, payload: bytes) -> None:
        self._send(status, payload, "text/html; charset=utf-8")

    def do_GET(self):  # noqa: N802 -- base class API
        parts = urlsplit(self.path)
        route = unquote(parts.path)
        query = parse_qs(parts.query)

        if route in ("/", "/index.html"):
            rows = fleet_rows()
            self._html(200, render_fleet(rows, fleet_summary(rows)))
            return
        if route == "/api/fleet":
            rows = fleet_rows()
            self._json(200, {"summary": fleet_summary(rows), "agents": rows})
            return
        if route == "/health":
            self._json(200, {"ok": True, "agents": len(discover_slugs()), "at": iso()})
            return
        if route == "/robots.txt":
            self._send(200, b"User-agent: *\nDisallow: /\n", "text/plain; charset=utf-8")
            return

        match = RAW_API.match(route)
        if match:
            view = conversation(match.group("slug")).refresh()
            record = view.raw(int(match.group("index")))
            if record is None:
                self._json(404, {"error": "that turn is not in the loaded window"})
                return
            self._json(200, record)
            return

        match = AGENT_API.match(route) or AGENT_ROUTE.match(route)
        if match:
            slug = match.group("slug")
            if slug not in discover_slugs():
                self._json(404, {"error": f"no agent named {slug} in the record"})
                return
            row = agent_row(slug)
            limit = _bounded(query, "limit", DEFAULT_TURNS, 1, MAX_TURNS)
            before = _optional_int(query, "before")
            view = conversation(slug).refresh()
            turns, loaded = view.page(limit, before)
            if route.startswith("/api/"):
                # Oldest first: `page` already yields a window in the order it
                # happened, and an API consumer wants a conversation in that
                # order. The page below reverses it for display, because the
                # thing an operator wants on opening a panel is what just
                # happened -- and exactly one of the two is allowed to reverse.
                self._json(
                    200,
                    {
                        "agent": row,
                        "turns": turns,
                        "turns_in_window": loaded,
                        "before": before,
                        "limit": limit,
                        "oldest_first": True,
                    },
                )
                return
            # The page, unlike the API, is newest first: the thing an operator
            # wants on opening a panel is what just happened.
            self._html(200, render_agent(row, turns, limit, before))
            return

        self._json(
            404,
            {
                "error": f"no route {route}",
                "routes": [
                    "GET /",
                    "GET /agent/<slug>",
                    "GET /api/fleet",
                    "GET /api/agent/<slug>",
                    "GET /api/agent/<slug>/turn/<n>/raw",
                    "GET /health",
                ],
            },
        )

    def do_HEAD(self):  # noqa: N802 -- base class API
        self.do_GET()


def _bounded(query: dict, name: str, default: int, low: int, high: int) -> int:
    values = query.get(name)
    if not values:
        return default
    try:
        return max(low, min(high, int(values[0])))
    except (TypeError, ValueError):
        return default


def _optional_int(query: dict, name: str) -> int | None:
    values = query.get(name)
    if not values:
        return None
    try:
        return int(values[0])
    except (TypeError, ValueError):
        return None


def log(message: str) -> None:
    print(f"{iso()} [review] {message}", flush=True)


def main() -> int:
    port = env_int("REVIEW_PORT", 8090)
    bind = os.environ.get("REVIEW_BIND", "0.0.0.0")  # noqa: S104 -- the container's own interface
    # A first pass, so the operator sees an error at startup rather than on a
    # page load, and so the log says how much of the record was found.
    slugs = discover_slugs()
    warmed = []
    for slug in slugs:
        view = conversation(slug).refresh(force=True)
        warmed.append(f"{slug}: {len(view.turns)} turn(s) in the window")
    log(
        f"read-only panel on {bind}:{port}; {len(slugs)} agent(s); "
        f"window {MAX_BYTES // 1024 // 1024} MB per agent"
    )
    for line in warmed:
        log(f"  {line}")
    if not slugs:
        log("nothing in the record yet; the panel will pick agents up as they speak")

    server = ThreadingHTTPServer((bind, port), Handler)
    server.daemon_threads = True
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        server.shutdown()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
