#!/usr/bin/env python3
"""The review panel: what an operator can read, and nothing else.

The fleet monitor answers "is the world working". This answers "what did that agent actually
think", which is a different question and needs a different view: the conversation, the reasoning,
every tool call with the result that came back, and what each turn cost.

Four properties are deliberate.

* **It reads the record, never the agents.** The turns come from the recorder's transcript, which
  each agent's recorder writes on a volume the agent cannot see; the fleet view comes from the
  monitor's fleet.json, derived from the same transcripts. What the agent writes about itself -- its
  recovery note in the mirror -- is shown, labelled as the agent's own claim, and read without
  following a link it planted.
* **It cannot change anything.** Every mount is read-only, the container's root filesystem is
  read-only, and there is no code path in this file that opens a file for writing. A test asserts
  it at the source level.
* **It has no route outward.** It sits on its own internal network with no gateway -- not the
  fleet's network, not the model's. It needs an address only so the operator's browser can reach it.
* **It stays cheap as the record grows.** Every request repeats the whole conversation, so a
  transcript grows fast. Nothing here reads a file whole: the newest turns are taken from a
  byte-bounded tail, parsed forward from a line boundary, and cached against the file's size and
  modification time.

A turn is one transcript line: the request the agent sent and the reply it got. The chassis
condenses and clips what it sends, so one request is not a prefix of the next; what is new in a
request is what follows its last assistant message, and a call's result is paired, by its id, from
the next request on the same stream.
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

import health  # noqa: E402
from common import env_int, iso, read_json, slugs_from_env  # noqa: E402

TRANSCRIPTS_DIR = Path(os.environ.get("TRANSCRIPTS_DIR", "/transcripts"))
TELEMETRY_DIR = Path(os.environ.get("TELEMETRY_DIR", "/telemetry"))
MIRROR_DIR = Path(os.environ.get("MIRROR_DIR", "/mirror"))
CLAIM = health.CLAIM_LABEL

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


def incoming(messages: list) -> list[dict]:
    """What this request delivers: the tool results and user messages after its last reply."""
    last = -1
    for index, message in enumerate(messages):
        if isinstance(message, dict) and message.get("role") == "assistant":
            last = index
    return [m for m in messages[last + 1 :] if isinstance(m, dict) and m.get("role") != "system"]


def turn_from(record: dict, index: int, following_request: dict | None, slug: str) -> dict:
    """One turn, as the panel shows it: what arrived, what came back, and what it cost."""
    request = record.get("request") if isinstance(record.get("request"), dict) else {}
    response = record.get("response") if isinstance(record.get("response"), dict) else {}

    choices = response.get("choices")
    choice = (
        choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    )
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}

    pointer = f"/api/agent/{slug}/turn/{index}/raw"
    calls = pair_tool_results(extract_calls(message, pointer), following_request)

    messages = request.get("messages") if isinstance(request.get("messages"), list) else []
    tools = request.get("tools") if isinstance(request.get("tools"), list) else []
    usage = response.get("usage")
    error = response.get("error")
    error_text = None
    if isinstance(error, dict):
        error_text = error.get("message") if isinstance(error.get("message"), str) else ""

    return {
        "index": index,
        "at": record.get("timestamp"),
        "stream": record.get("stream", health.CORE),
        "refused": health.is_cap_refusal(record),
        "error": clip(error_text, TEXT_CAP, pointer) if error_text is not None else None,
        "usage": usage if isinstance(usage, dict) else None,
        "finish_reason": choice.get("finish_reason"),
        "model": request.get("model"),
        "fresh": health.is_fresh_start(messages),
        "system_hash": health.system_prompt_hash(request),
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
            {"role": m.get("role"), "text": clip(message_text(m), TEXT_CAP, pointer)}
            for m in incoming(messages)
        ],
        "context_messages": len(messages),
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
                self.turns = self._build(records)
                self.more_available = more or len(records) >= CACHE_TURNS
            except OSError as error:
                self.error = f"could not read the transcript: {error}"
                self.turns, self.more_available = [], False
            return self

    def _build(self, records: list[dict]) -> list[dict]:
        """Each line a turn; a call's result comes from the next request on the same stream."""
        turns: list[dict] = []
        for offset, record in enumerate(records):
            stream = record.get("stream", health.CORE)
            following = None
            for later in records[offset + 1 :]:
                if later.get("stream", health.CORE) == stream and isinstance(
                    later.get("request"), dict
                ):
                    following = later["request"]
                    break
            turns.append(turn_from(record, offset, following, self.slug))
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
def discover_slugs() -> list[str]:
    """The agents: AGENT_SLUGS when set, else every transcript or mirror bind it was given."""
    configured = slugs_from_env("AGENT_SLUGS")
    if configured:
        return configured
    found: set[str] = set()
    for root in (TRANSCRIPTS_DIR, MIRROR_DIR):
        with contextlib.suppress(OSError):
            found |= {p.name for p in root.iterdir() if p.is_dir()}
    return sorted(found)


def monitor_rows() -> dict[str, dict]:
    """The monitor's published view, by slug: liveness and signals, from the transcripts."""
    snapshot = read_json(TELEMETRY_DIR / "fleet.json") or {}
    agents = snapshot.get("agents") if isinstance(snapshot, dict) else None
    if not isinstance(agents, list):
        return {}
    return {a["slug"]: a for a in agents if isinstance(a, dict) and isinstance(a.get("slug"), str)}


def fleet_rows() -> list[dict]:
    published = monitor_rows()
    return [agent_row(slug, published.get(slug)) for slug in discover_slugs()]


def agent_row(slug: str, published: dict | None = None) -> dict:
    """One agent: the monitor's signals, the panel's own view of the transcript, and its claim."""
    if published is None:
        published = monitor_rows().get(slug) or {}
    view = conversation(slug).refresh()
    note = health.read_claim(MIRROR_DIR / slug, "work/tombstones/recovery_note.txt")
    return {
        "slug": slug,
        "liveness": published.get("liveness", "unknown"),
        "signals": published.get("signals") if isinstance(published.get("signals"), dict) else {},
        "claims": {
            "recovery_note": health.claim(
                note.decode("utf-8", errors="replace").strip() if note is not None else None
            )
        },
        "turns_loaded": len(view.turns),
        "approximate_total": view.approximate_total,
        "more_available": view.more_available,
        "transcript_bytes": view.total_bytes,
        "transcript_error": view.error,
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
        "bytes": sum(row["transcript_bytes"] for row in rows),
        "liveness": {
            state: sum(1 for row in rows if row["liveness"] == state) for state in health_states()
        },
    }


def health_states() -> tuple[str, ...]:
    return ("active", "capped", "idle-watchdog", "stale", "unknown")


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


def page(title: str, body: str, *, refresh: int | None = None) -> bytes:
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        f"<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)}</title>{meta}<style>{PAGE_STYLE}</style></head><body>"
        f"{body}</body></html>"
    ).encode()


def _claim_cell(claim: dict | None, cap: int = SUMMARY_CAP) -> str:
    value = claim.get("value") if isinstance(claim, dict) else None
    if value is None:
        return "<span class=meta>—</span>"
    text = str(value).splitlines()[0] if str(value) else ""
    return f"<span class=warn title='{esc(CLAIM)}'>{esc(text[:cap])}*</span>"


def _percent(share) -> str:
    """A share in 0..1 as a whole percentage; anything else, including a snapshot from before
    the monitor published one, is a dash."""
    if isinstance(share, (int, float)) and not isinstance(share, bool) and 0 <= share <= 1:
        return f"{round(100 * share)}%"
    return "—"


def render_fleet(rows: list[dict], summary: dict) -> bytes:
    states = ", ".join(f"{count} {state}" for state, count in summary["liveness"].items() if count)
    head = (
        "<h1>space_chassis — the fleet</h1>"
        f"<p class=note>{esc(summary['agents'])} agent(s): {esc(states) or 'none seen'}; "
        f"{esc(summary['turns'])} turn(s) in view, "
        f"{summary['bytes'] / 1e6:.1f} MB of transcript. Read-only: this panel opens the "
        "record, and nothing it does can change it. Liveness and signals are the monitor's, "
        f"from the recorders' transcripts; * marks {esc(CLAIM)}.</p>"
    )
    if not rows:
        return page(
            "space_chassis — the fleet",
            head + "<p class=note>No agent has spoken yet. Once one takes a turn, its "
            "conversation appears here.</p>",
            refresh=10,
        )

    def cells(r: dict) -> str:
        signals = r["signals"]
        spend = signals.get("spend") if isinstance(signals.get("spend"), dict) else {}
        caps = signals.get("caps") if isinstance(signals.get("caps"), dict) else {}
        state = r["liveness"]
        kind = "ok" if state == "active" else "bad" if state == "stale" else "warn"
        return (
            "<tr>"
            f"<td><a href='/agent/{esc(r['slug'])}'>{esc(r['slug'])}</a></td>"
            f"<td class={kind}>{esc(state)}</td>"
            f"<td>{esc(signals.get('incarnations', '—'))}</td>"
            f"<td>{esc(spend.get('requests', '—'))}/{esc(caps.get('requests', '—'))}</td>"
            f"<td title='cache share'>{esc(_percent(spend.get('cache_share')))}</td>"
            f"<td>{esc(signals.get('refusals', '—'))}</td>"
            f"<td>{esc(signals.get('tool_errors', '—'))}/{esc(signals.get('tool_results', '—'))}</td>"
            f"<td>{esc(r['turns_loaded'])}{'…' if r['more_available'] else ''}</td>"
            f"<td>{r['transcript_bytes'] / 1e6:.1f} MB</td>"
            f"<td>{_claim_cell(r['claims'].get('recovery_note'))}</td>"
            "</tr>"
        )

    table = (
        "<table><tr><th>agent</th><th>liveness</th><th>incarnations</th><th>hour / cap</th>"
        "<th>cache</th><th>refusals</th><th>tool errors</th><th>turns</th><th>transcript</th>"
        "<th>last note*</th></tr>" + "".join(cells(r) for r in rows) + "</table>"
    )
    return page("space_chassis — the fleet", head + table, refresh=15)


def render_turn(turn: dict, slug: str, position: str | None = None) -> str:
    pos = position or f"#{turn['index']}"
    usage = turn.get("usage") or {}
    tokens = usage.get("total_tokens")
    pieces = [f"<b>{esc(pos)}</b> ", f"<span class=meta>{esc(turn['at'])}</span> "]
    if turn.get("stream") not in (None, health.CORE):
        pieces.append(f"<span class=meta>stream {esc(turn['stream'])}</span> ")
    if turn.get("fresh"):
        pieces.append("<span class=ok>new conversation</span> ")
    if turn.get("error") is not None:
        label = "refused" if turn.get("refused") else "error"
        pieces.append(f"<span class=bad>{label}: {esc(turn['error'])}</span> ")
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
    signals = row["signals"]
    spend = signals.get("spend") if isinstance(signals.get("spend"), dict) else {}
    head = [
        f"<h1>{esc(slug)}</h1>",
        "<p class=note>",
        f"{esc(row['liveness'])} · {esc(signals.get('incarnations', '—'))} incarnation(s) · "
        f"{esc(spend.get('requests', '—'))} request(s) this hour · "
        f"{esc(signals.get('refusals', '—'))} refusal line(s)",
        f" · {row['transcript_bytes'] / 1e6:.1f} MB of transcript",
        f" · <a href='/'>fleet</a> · <a href='/api/agent/{esc(slug)}'>json</a>",
        "</p>",
    ]
    note = row["claims"].get("recovery_note", {}).get("value")
    if note:
        head.append(
            f"<p class=warn>last recovery note*: {esc(note[:TEXT_CAP])}<br>"
            f"<span class=meta>* {esc(CLAIM)}: written inside the agent's container</span></p>"
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
