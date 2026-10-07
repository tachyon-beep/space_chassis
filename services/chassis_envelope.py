"""Bounded response adoption: what a model response becomes before anything runs.

Standard library only, and pure: nothing here writes a file, appends a record,
invokes a tool or contacts a model. Contract: SV-015 v2 section 2.3 (escaped
units, truncation marker, caps, tool-call counts, wire ids, request size),
with SV-013 section 2.2.6's retained rules for argument elision.

`adopt_response` turns one response into either a refusal (more calls than
`CAP_CALLS_HARD`: nothing stored, nothing run) or an `Adoption`: the exact
assistant dict to store, one disposition per stored call (`admit`), the
omitted-call hash and notice, and the originals a caller may retain. Every
stored call is answered exactly once by its caller: an invokable call by its
result, every other call by its fixed `admit_text`. Omitted calls are not in
the stored message, so they need no answer.

The text and id helpers at the top are the accepted SV-019 helpers, moved
here unchanged; `chassis` re-exports them.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Text and ids (SV-015 v2 section 2.3)
# ---------------------------------------------------------------------------
# Sizes are measured in *escaped units*: E(s) = len(json.dumps(s,
# ensure_ascii=True)) - 2. For every string that is at least its length in each
# serialized form the runtime produces or causes -- the saved conversation, a
# request, a UTF-8 record -- so a cap in escaped units bounds all of them, which
# a cap in UTF-8 bytes does not (160 NULs are 160 bytes but 960 escaped units).
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
# Caps (SV-015 v2 section 2.3) [CM]
# ---------------------------------------------------------------------------
# Fixed in code, not read from the environment: the ledger's maximal
# TURN_RESPONSE body (679,888 bytes < MAX_LEDGER_BODY) is computed from these.
@dataclass(frozen=True)
class Caps:
    content: int = 64 * 1024
    reasoning: int = 64 * 1024
    name: int = 64
    args: int = 32 * 1024
    result: int = 32 * 1024
    calls: int = 16
    calls_stored: int = 32
    calls_hard: int = 256
    note: int = 64 * 1024  # NOTE_MAX_E, v2 1.4.6

    def problem(self) -> str | None:
        """Why these caps are refused at startup (exit 43 `invalid_caps`), or None."""
        for name in ("content", "reasoning", "result", "note"):
            if getattr(self, name) < 128:
                return f"CAP_{name.upper()} is below 128 escaped units"
        if self.args < 160:
            return "CAP_ARGS is below 160 escaped units"
        if self.name < 1:
            return "CAP_NAME is below 1"
        if not 0 <= self.calls <= self.calls_stored <= self.calls_hard:
            return "the call caps are not CAP_CALLS <= CAP_CALLS_STORED <= CAP_CALLS_HARD"
        return None


DEFAULT_CAPS = Caps()

# The recorder's REQUEST_MAX_BYTES; a larger request is refused before sending.
CLIENT_MAX_REQUEST_BYTES = 2_097_152
# SV-013 2.2.6: invalid JSON arguments up to this many UTF-8 bytes are stored
# verbatim with an error result; longer ones are elided.
INVALID_ARGS_KEEP_BYTES = 512

# Fixed texts. The call-limit text and both notices are the SV-015 v2 literal
# generator's shapes; the rest are this module's, fixed so replay is exact.
CALL_LIMIT_TEXT = "not run: the call limit was reached"
OMITTED_NOTICE = "[runtime] the response contained {count} tool calls; calls {first}–{count} were not stored or run"
REFUSED_NOTICE = (
    "[runtime] the model response contained {count} tool calls (limit {limit}) and was not adopted; nothing was run"
)
OVERSIZE_ARGS_TEXT = "error: arguments elided: {bytes} bytes over the CAP_ARGS limit"
BAD_JSON_TEXT = "error: arguments were not valid json: {error}"
BAD_JSON_ELIDED_TEXT = "error: arguments were not valid json ({bytes} bytes, elided)"
NOT_OBJECT_TEXT = "error: arguments must be a json object"
BAD_NAME_TEXT = "error: the tool name was refused ({why}); the call was not run"


def elision(data: bytes) -> str:
    """`{"_runtime_elided":{"bytes":N,"sha256":H}}`, compact: <= 118 bytes, <= 126 units for N < 10^12."""
    return json.dumps(
        {"_runtime_elided": {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}},
        separators=(",", ":"),
    )


def canonical_json(value) -> bytes:
    """The ledger's canonical form, for hashing provider values of any shape."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=repr
    ).encode("utf-8", "backslashreplace")


def provider_id_repr(value) -> dict:
    """What TURN_RESPONSE keeps of a provider id: its type, size and hash, never the raw value."""
    text = json.dumps(value, ensure_ascii=True, default=repr)
    return {
        "type": type(value).__name__,
        "E": len(text) - 2,
        "sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
    }


def request_bytes(body: dict) -> int:
    """S = len(json.dumps(body)): default separators, ASCII escapes (v2 2.3's local check form).

    This is >= the bytes of the same body from any Python json encoder, with
    any ensure_ascii and compact or default separators.
    """
    return len(json.dumps(body))


# ---------------------------------------------------------------------------
# A response, as received
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RawCall:
    provider_id: object
    name: object
    arguments: object


@dataclass(frozen=True)
class RawResponse:
    content: object
    reasoning: object
    calls: tuple[RawCall, ...]


def raw_from_message(message) -> RawResponse:
    """Read an SDK message without trusting its shape; any attribute may be missing."""
    calls = []
    for call in getattr(message, "tool_calls", None) or ():
        function = getattr(call, "function", None)
        calls.append(
            RawCall(
                getattr(call, "id", None),
                getattr(function, "name", None),
                getattr(function, "arguments", None),
            )
        )
    return RawResponse(
        getattr(message, "content", None),
        getattr(message, "reasoning_content", None),
        tuple(calls),
    )


# ---------------------------------------------------------------------------
# Adoption
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Original:
    """Bytes a field had before truncation or elision, offered for retention."""

    kind: str  # assistant_content | args
    field: str
    data: bytes


@dataclass(frozen=True)
class StoredCall:
    index: int
    wire_id: str
    name: str
    arguments: str  # what the stored message carries (possibly the elision)
    invoke_arguments: str | None  # what an invocation parses; None when admit != invoke
    admit: str  # invoke | not_run_call_limit | bad_args | oversize_args | bad_name
    admit_text: str | None
    ledger: dict


@dataclass(frozen=True)
class Adoption:
    turn_seq: int
    count: int
    refused: bool
    assistant: dict | None
    calls: tuple[StoredCall, ...] = ()
    omitted: dict | None = None
    notice: str | None = None
    normalization: dict = field(default_factory=dict)
    originals: tuple[Original, ...] = ()

    def refusal_payload(self) -> dict:
        return {"turn_seq": self.turn_seq, "reason": "too_many_calls", "count": self.count}

    def turn_response_payload(self, retained: list[dict]) -> dict:
        """The TURN_RESPONSE body. `retained`: [{sha256, bytes, kind, field}] actually stored as blobs."""
        payload = {
            "turn_seq": self.turn_seq,
            "assistant": self.assistant,
            "calls": [call.ledger for call in self.calls],
            "normalization": self.normalization,
            "original_blobs": [item["sha256"] for item in retained],
            "originals": retained,
        }
        if self.omitted is not None:
            payload["omitted"] = self.omitted
        return payload


def _coerce_text(value, field_name: str, coerced: list[str]) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    coerced.append(field_name)
    return json.dumps(value, ensure_ascii=False, default=repr)


def _name_disposition(raw, caps: Caps) -> tuple[str, str | None, int]:
    """(stored name, why it is refused or None, replaced characters)."""
    if not isinstance(raw, str):
        return "", f"not a string: {type(raw).__name__}", 0
    name, replaced = normalize_text(raw)
    if not name:
        return "", "empty", 0
    if escaped_units(name) > caps.name:
        kept, units = [], 0
        for character in name:
            cost = _unit_cost(character)
            if units + cost > caps.name:
                break
            kept.append(character)
            units += cost
        return "".join(kept), f"longer than {caps.name} escaped units", replaced
    if replaced:
        return name, "contained unpaired surrogates", replaced
    return name, None, 0


def adopt_response(raw: RawResponse, turn_seq: int, caps: Caps = DEFAULT_CAPS) -> Adoption:
    """The bounded, stored form of one response (v2 2.3 table). Pure; never raises on provider data."""
    count = len(raw.calls)
    if count > caps.calls_hard:
        return Adoption(
            turn_seq,
            count,
            True,
            None,
            notice=REFUSED_NOTICE.format(count=count, limit=caps.calls_hard),
        )

    replaced_total = 0
    truncated_fields: list[str] = []
    coerced: list[str] = []
    originals: list[Original] = []

    def bounded(value, field_name: str, cap: int) -> str:
        nonlocal replaced_total
        text = _coerce_text(value, field_name, coerced)
        stored, info = truncate_marked(text, cap)
        replaced_total += info["replaced_chars"]
        if info["truncated"]:
            truncated_fields.append(field_name)
            originals.append(Original("assistant_content", field_name, normalize_text(text)[0].encode("utf-8")))
        return stored

    assistant: dict = {"role": "assistant", "content": bounded(raw.content, "content", caps.content)}
    if raw.reasoning is not None and raw.reasoning != "":
        assistant["reasoning_content"] = bounded(raw.reasoning, "reasoning_content", caps.reasoning)

    stored_raw = raw.calls[: caps.calls_stored]
    omitted_raw = raw.calls[caps.calls_stored :]
    wire_ids = assign_wire_ids([call.provider_id for call in stored_raw], turn_seq)

    calls: list[StoredCall] = []
    message_calls: list[dict] = []
    for index, call in enumerate(stored_raw):
        name, why, name_replaced = _name_disposition(call.name, caps)
        replaced_total += name_replaced
        if why is not None and isinstance(call.name, str) and name != call.name:
            truncated_fields.append(f"tool_calls[{index}].function.name")
        args_text = _coerce_text(call.arguments, f"tool_calls[{index}].function.arguments", coerced)
        args_text, args_replaced = normalize_text(args_text)
        replaced_total += args_replaced
        args_bytes = args_text.encode("utf-8")
        args_units = escaped_units(args_text)
        stored_args = args_text
        invoke_args: str | None = None
        admit_text: str | None = None

        if index >= caps.calls:
            admit, admit_text = "not_run_call_limit", CALL_LIMIT_TEXT
            stored_args = elision(args_bytes)
        elif why is not None:
            admit, admit_text = "bad_name", BAD_NAME_TEXT.format(why=why)
            if args_units > caps.args:
                stored_args = elision(args_bytes)
        elif args_units > caps.args:
            admit, admit_text = "oversize_args", OVERSIZE_ARGS_TEXT.format(bytes=len(args_bytes))
            stored_args = elision(args_bytes)
            originals.append(Original("args", f"tool_calls[{index}].function.arguments", args_bytes))
        else:
            try:
                parsed = json.loads(args_text or "{}")
            except ValueError as error:
                admit = "bad_args"
                if len(args_bytes) > INVALID_ARGS_KEEP_BYTES:
                    admit_text = BAD_JSON_ELIDED_TEXT.format(bytes=len(args_bytes))
                    stored_args = elision(args_bytes)
                    originals.append(Original("args", f"tool_calls[{index}].function.arguments", args_bytes))
                else:
                    admit_text = BAD_JSON_TEXT.format(error=error)
            else:
                if isinstance(parsed, dict):
                    admit, invoke_args = "invoke", args_text
                else:
                    admit, admit_text = "bad_args", NOT_OBJECT_TEXT
        if stored_args != args_text:
            truncated_fields.append(f"tool_calls[{index}].function.arguments")

        ledger = {
            "call_index": index,
            "provider_id_repr": provider_id_repr(call.provider_id),
            "wire_id": wire_ids[index],
            "name": name,
            "args_sha256": hashlib.sha256(args_bytes).hexdigest(),
            "args_E": args_units,
            "admit": admit,
        }
        if admit_text is not None:
            ledger["admit_text"] = admit_text
        calls.append(StoredCall(index, wire_ids[index], name, stored_args, invoke_args, admit, admit_text, ledger))
        message_calls.append(
            {"id": wire_ids[index], "type": "function", "function": {"name": name, "arguments": stored_args}}
        )

    if message_calls:
        assistant["tool_calls"] = message_calls

    omitted = None
    notice = None
    if omitted_raw:
        objects = [
            {"id": call.provider_id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
            for call in omitted_raw
        ]
        omitted = {"count": len(omitted_raw), "sha256": hashlib.sha256(canonical_json(objects)).hexdigest()}
        notice = OMITTED_NOTICE.format(count=count, first=caps.calls_stored + 1)

    normalization = {
        "replaced_chars": replaced_total,
        "truncated_fields": truncated_fields,
        "coerced_fields": coerced,
    }
    return Adoption(turn_seq, count, False, assistant, tuple(calls), omitted, notice, normalization, tuple(originals))


def stored_result(value, cap: int) -> tuple[str, dict]:
    """A tool's result as stored: `str()`, normalized, then the marker contract within `cap`."""
    text = "" if value is None else str(value)
    return truncate_marked(text, cap)
