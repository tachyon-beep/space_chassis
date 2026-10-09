"""The operator's health signals, derived from the recorder's own lines and nothing an agent writes.

Every input here is written by an agent's recorder, in its own container, onto a volume the agent
cannot see: the transcript (one line per exchange, `{"timestamp", "stream", "request",
"response"}`) and the event log (`open`/`close` per request, with status and usage). The agent's
own account of itself -- its mirror, its notes, its watchdog's lines -- is not read here; the
surfaces that show those label them as the agent's claim.

What the lines can and cannot say:

- **Only the core loop counts.** A declared stream (`stream` other than "core") is a sub-call the
  agent built, not its loop; a line with no stream is core, as older lines were.
- **An error is not a request, and only the cap's wording makes it a cap.** A refused request and an
  upstream outage both answer with an `error` body; the recorder's cap refusals say "per hour",
  "across the fleet" or "fleet ledger unavailable". Refusals are counted in lines, not attempts:
  every client and chassis retry writes one.
- **A fresh incarnation is a request with no assistant message.** A reset, a clean restart, a pause
  and the ladder's first rung all keep the conversation, so none of them is a boundary here; the
  only record of those is the agent's own.
- **A vehicle command is a tool call that touches `/diode/`,** read from the recorder's copy of the
  reply. The vehicle's result files sit in a directory the agent writes, so their count is shown
  only as the agent's claim.
- **A tool error is counted once,** from the tool results that follow the request's last assistant
  message: older results ride along in every later request and would otherwise count again.

Standard library only, plus `common`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import stat
from pathlib import Path

from common import MAX_READ_BYTES, tail_jsonl

CORE = "core"
QUIET_SECONDS = 900
ERROR_PREFIXES = ("Error parsing JSON arguments", "Error executing tool", "Error: Tool `")
CAP_WORDS = ("per hour", "across the fleet", "fleet ledger unavailable")
MAX_ENTRIES = 10000
WINDOW_MARK = "/diode/"
RESULT_NAME = re.compile(r"^(\d{8}T\d{6})_(\d{6})Z_.+\.txt$")
NOTE_BYTES = 64 * 1024
CLAIM_LABEL = "the agent's own claim"


def read_records(path: Path, max_bytes: int = MAX_READ_BYTES) -> list[dict]:
    """The bounded tail of a JSONL file, from a line boundary; nothing if it cannot be read."""
    try:
        return [record for record in tail_jsonl(Path(path), max_bytes) if isinstance(record, dict)]
    except OSError:
        return []


def parse_timestamp(text) -> float | None:
    """The recorder's `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`, as epoch seconds."""
    if not isinstance(text, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.timestamp()


def _messages(record) -> list | None:
    if not isinstance(record, dict):
        return None
    request = record.get("request")
    if not isinstance(request, dict):
        return None
    messages = request.get("messages")
    return messages if isinstance(messages, list) else None


def core_records(records: list) -> list[dict]:
    """The core loop's lines: stream "core" or none, with a request that carries messages."""
    return [
        record
        for record in records
        if _messages(record) is not None and record.get("stream", CORE) == CORE
    ]


def _error_message(record: dict) -> str | None:
    response = record.get("response")
    if not isinstance(response, dict):
        return None
    error = response.get("error")
    if not isinstance(error, dict):
        return None
    message = error.get("message")
    return message if isinstance(message, str) else ""


def is_error(record: dict) -> bool:
    return _error_message(record) is not None


def is_cap_refusal(record: dict) -> bool:
    message = _error_message(record)
    return message is not None and any(word in message for word in CAP_WORDS)


def is_fresh_start(messages: list) -> bool:
    return not any(isinstance(m, dict) and m.get("role") == "assistant" for m in messages)


def incarnations(records: list) -> list[list[dict]]:
    """The core requests that were answered, split before every fresh start."""
    groups: list[list[dict]] = []
    for record in core_records(records):
        if is_error(record):
            continue
        if not groups or is_fresh_start(_messages(record)):
            groups.append([])
        groups[-1].append(record)
    return groups


def system_prompt_hash(request) -> str | None:
    messages = request.get("messages") if isinstance(request, dict) else None
    if not isinstance(messages, list) or not messages:
        return None
    first = messages[0]
    if not isinstance(first, dict) or first.get("role") != "system":
        return None
    content = first.get("content")
    text = content if isinstance(content, str) else json.dumps(content, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def new_tool_results(messages: list) -> list[dict]:
    """The tool results this request delivers: those after its last assistant message."""
    last = -1
    for index, message in enumerate(messages):
        if isinstance(message, dict) and message.get("role") == "assistant":
            last = index
    return [m for m in messages[last + 1 :] if isinstance(m, dict) and m.get("role") == "tool"]


def tool_errors(records: list) -> tuple[int, int]:
    errors = results = 0
    for record in core_records(records):
        if is_error(record):
            continue
        for result in new_tool_results(_messages(record)):
            results += 1
            content = result.get("content")
            if isinstance(content, str) and content.startswith(ERROR_PREFIXES):
                errors += 1
    return errors, results


def spend(events: list, now: float, window: float = 3600.0) -> dict:
    """Core closes inside the hour: requests, tokens from usage, and 429/503 refusals."""
    total = {"requests": 0, "tokens": 0, "refused": 0}
    for event in events:
        if not isinstance(event, dict) or event.get("event") != "close":
            continue
        if event.get("stream", CORE) != CORE:
            continue
        when = parse_timestamp(event.get("timestamp"))
        if when is None or not now - window <= when <= now:
            continue
        total["requests"] += 1
        if event.get("status") in (429, 503):
            total["refused"] += 1
        usage = event.get("usage")
        tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens > 0:
            total["tokens"] += tokens
    return total


def _result_time(name: str) -> float | None:
    match = RESULT_NAME.match(name)
    if match is None:
        return None
    try:
        stamp = dt.datetime.strptime(match.group(1) + match.group(2), "%Y%m%dT%H%M%S%f")
    except ValueError:
        return None
    return stamp.replace(tzinfo=dt.UTC).timestamp()


def window_calls(record: dict) -> int:
    """Tool calls in this reply whose arguments touch the window: the vehicle-command signal.

    Read from the recorder's copy of the reply, so the agent cannot forge or delete it; a heuristic,
    because a command is whatever writes the window's console and the harness has no diode tool.
    """
    response = record.get("response")
    choices = response.get("choices") if isinstance(response, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return 0
    message = choices[0].get("message")
    calls = message.get("tool_calls") if isinstance(message, dict) else None
    if not isinstance(calls, list):
        return 0
    count = 0
    for call in calls:
        function = call.get("function") if isinstance(call, dict) else None
        arguments = function.get("arguments") if isinstance(function, dict) else None
        if isinstance(arguments, str) and WINDOW_MARK in arguments:
            count += 1
    return count


def window_results(root: Path, slug: str) -> dict | None:
    """The vehicle's result files in the agent's output directory: one bounded, no-follow scan.

    The directory is the agent's to write, so the count is its claim: results can be forged or
    deleted, and a flood of names stops the scan at MAX_ENTRIES (`capped`).
    """
    fd = _walk(Path(root), [slug, "output"])
    if fd is None:
        return None
    count, capped = 0, False
    try:
        with os.scandir(fd) as entries:
            for seen, entry in enumerate(entries):
                if seen >= MAX_ENTRIES:
                    capped = True
                    break
                if _result_time(entry.name) is not None:
                    count += 1
    except OSError:
        return None
    finally:
        os.close(fd)
    return {"count": count, "capped": capped}


def liveness(
    transcript_age: float | None, mirror_age: float | None, last_capped: bool, quiet: float
) -> str:
    """Two clocks: the recorder's (the agent is talking) and the mirror's (the watchdog is up)."""
    if transcript_age is not None and transcript_age < quiet:
        return "capped" if last_capped else "active"
    if mirror_age is not None and mirror_age < quiet:
        return "idle-watchdog"
    if transcript_age is None and mirror_age is None:
        return "unknown"
    return "stale"


def signals(records: list, events: list, *, now: float, caps: dict) -> dict:
    core = core_records(records)
    groups = incarnations(records)

    changes, previous = 0, None
    for record in core:
        if is_error(record):
            continue
        digest = system_prompt_hash(record["request"])
        if digest is None:
            continue
        if previous is not None and digest != previous:
            changes += 1
        previous = digest

    errors, results = tool_errors(records)
    refusals = sum(1 for record in core if is_cap_refusal(record))
    other_errors = sum(1 for record in core if is_error(record) and not is_cap_refusal(record))

    commands = [sum(window_calls(record) for record in group) for group in groups]

    times = [t for t in (parse_timestamp(r.get("timestamp")) for r in core) if t is not None]
    lines = [r for r in records if isinstance(r, dict)]
    stamps = [t for t in (parse_timestamp(r.get("timestamp")) for r in lines) if t is not None]
    return {
        "incarnations": len(groups),
        "requests_per_incarnation": [len(group) for group in groups],
        "resets": max(0, len(groups) - 1),
        "system_prompt_changes": changes,
        "tool_errors": errors,
        "tool_results": results,
        "refusals": refusals,
        "errors": other_errors,
        "vehicle_commands_per_incarnation": commands,
        "spend": spend(events, now),
        "caps": caps,
        "last_request_at": max(times) if times else None,
        "last_capped": bool(core) and is_cap_refusal(core[-1]),
        "window": {
            "records": len(lines),
            "first_at": min(stamps) if stamps else None,
            "last_at": max(stamps) if stamps else None,
        },
    }


def _walk(root: Path, parts: list[str]) -> int | None:
    """A directory fd for root/parts, refusing a symlink at every step below root."""
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return None
    try:
        for part in parts:
            if part in ("", ".", ".."):
                raise OSError("unsafe path component")
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
    except OSError:
        os.close(fd)
        return None
    return fd


def read_claim(root: Path, relative: str, limit: int = NOTE_BYTES) -> bytes | None:
    """An agent-written file under root, never through a symlink, a FIFO or past limit.

    The agent controls every name below root, so each step is opened with O_NOFOLLOW from the
    directory before it, and the file itself must be a regular file: a link to the operator's own
    files, or a FIFO that would hang the reader, reads as nothing.
    """
    *parents, name = relative.split("/")
    fd = _walk(Path(root), parents)
    if fd is None:
        return None
    try:
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except OSError:
        os.close(fd)
        return None
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            return None
        chunks, total = [], 0
        while total <= limit:
            chunk = os.read(handle, limit + 1 - total)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks) if total <= limit else None
    except OSError:
        return None
    finally:
        os.close(handle)
        os.close(fd)


def claim_age(root: Path, relative: str, now: float) -> float | None:
    """The mtime age of an agent-written entry, by lstat through no-follow directories."""
    *parents, name = relative.split("/")
    fd = _walk(Path(root), parents)
    if fd is None:
        return None
    try:
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
    except OSError:
        return None
    finally:
        os.close(fd)
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        return None
    return max(0.0, now - info.st_mtime)


def _note(root: Path, relative: str) -> str | None:
    raw = read_claim(root, relative)
    return raw.decode("utf-8", errors="replace").strip() if raw is not None else None


def printable(text) -> str:
    """Agent-written text made safe for a terminal: whitespace to spaces, controls to '?'."""
    if text is None:
        return "-"
    out = []
    for char in str(text):
        if char in "\t\n\r":
            out.append(" ")
        elif ord(char) < 0x20 or 0x7F <= ord(char) < 0xA0:
            out.append("?")
        else:
            out.append(char)
    return "".join(out)


def claim(value) -> dict:
    """A value the agent wrote about itself, labelled so no surface shows it as fact."""
    return {"value": value, "claim": "agent"}


def agent_view(
    transcripts: Path,
    mirror: Path,
    *,
    now: float,
    quiet: float,
    caps: dict,
    pump_state: Path | None = None,
    window: tuple[Path, str] | None = None,
) -> dict:
    """One agent, as status.py and the monitor both see it.

    `transcripts` is the recorder's directory for this agent; `mirror` is the root the watchdog
    renames `work` into every few seconds -- its own mtime is the watchdog's clock, because the
    copied tree carries the source's mtimes. Everything read from under `mirror`, and the pump's
    state, is the agent's claim.
    """
    records = read_records(Path(transcripts) / "agent_life_transcript.jsonl")
    events = read_records(Path(transcripts) / "events.jsonl")
    found = signals(records, events, now=now, caps=caps)
    last = found["last_request_at"]
    transcript_age = max(0.0, now - last) if last is not None else None
    # The recorder writes the transcript; its size and mtime are the recorder's, not the agent's.
    # A window that began mid-file is marked, so no surface shows a partial count as whole, and a
    # newest line larger than the whole window still leaves the file's own clock to read.
    try:
        written = (Path(transcripts) / "agent_life_transcript.jsonl").stat()
    except OSError:
        written = None
    found["window"]["truncated"] = written is not None and written.st_size > MAX_READ_BYTES
    if transcript_age is None and written is not None and written.st_size > 0:
        transcript_age = max(0.0, now - written.st_mtime)
    mirror = Path(mirror)
    work = _walk(mirror, ["work"])
    if work is None:
        mirror_age = None
    else:
        os.close(work)
        try:
            mirror_age = max(0.0, now - mirror.stat().st_mtime)
        except OSError:
            mirror_age = None
    claims = {
        "recovery_note": claim(_note(mirror, "work/tombstones/recovery_note.txt")),
        "incarnation_note": claim(_note(mirror, "work/tombstones/incarnation_note.txt")),
        "agent_log_age": claim(claim_age(mirror, "work/agent_stdout.log", now)),
    }
    if window is not None:
        claims["window_results"] = claim(window_results(*window))
    if pump_state is not None:
        raw = read_claim(Path(pump_state).parent, Path(pump_state).name, MAX_READ_BYTES)
        try:
            state = json.loads(raw) if raw is not None else None
        except ValueError:
            state = None
        entries = state.get("entries") if isinstance(state, dict) else None
        claims["pump_running"] = claim(
            sum(1 for e in entries.values() if isinstance(e, dict) and e.get("running") is True)
            if isinstance(entries, dict)
            else None
        )
    return {
        "liveness": liveness(transcript_age, mirror_age, found["last_capped"], quiet),
        "transcript_age": transcript_age,
        "mirror_age": mirror_age,
        "signals": found,
        "claims": claims,
    }
