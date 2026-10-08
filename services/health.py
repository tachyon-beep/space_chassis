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
from pathlib import Path

from common import MAX_READ_BYTES, tail_jsonl

CORE = "core"
QUIET_SECONDS = 900
ERROR_PREFIXES = ("Error parsing JSON arguments", "Error executing tool", "Error: Tool `")
CAP_WORDS = ("per hour", "across the fleet", "fleet ledger unavailable")
MAX_ENTRIES = 10000
RESULT_NAME = re.compile(r"^(\d{8}T\d{6})_(\d{6})Z_.+\.txt$")


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


def vehicle_commands(output_dir: Path, start: float, end: float) -> int:
    """Result files the vehicle wrote with a stamp in [start, end); each is one command."""
    count = 0
    try:
        with os.scandir(output_dir) as entries:
            for seen, entry in enumerate(entries):
                if seen >= MAX_ENTRIES:
                    break
                when = _result_time(entry.name)
                if when is not None and start <= when < end:
                    count += 1
    except OSError:
        return 0
    return count


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


def signals(records: list, events: list, *, now: float, caps: dict, output_dir) -> dict:
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

    commands = None
    if output_dir is not None:
        starts = [parse_timestamp(group[0].get("timestamp")) for group in groups]
        commands = []
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else now
            if start is None or end is None:
                commands.append(0)
            else:
                commands.append(vehicle_commands(Path(output_dir), start, end))

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
