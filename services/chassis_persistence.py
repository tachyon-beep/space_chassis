"""The chassis persistence foundation: SVL1 ledger frames, a scanner, and durable primitives.

Standard library only. **Nothing in the production chassis imports this module
yet.** It is the reusable, tested foundation for the integrated K-D1/K-D2
activation (SV-013 section 4.1 ships them together), and it deliberately does
not activate anything: no `format: 2` in run.json, no gate in a live run, no
recovery at startup. Contracts: SV-015 v2 sections 1.1-1.4 (fault model M-1 to
M-5; framing; tail classification; checkpoint graph, durability, quarantine,
FSYNC_FAILED honesty), with SV-013 section 2.2.2-2.2.3's retained texts.

Three layers, kept apart on purpose:

* **Framing** (`encode_frame`, `read_header`, `parse_record`): exact bytes.
* **Reading** (`scan_segments`, `classify_tail`, `plan_recovery`): pure. A scan
  or a plan *recommends*; it never truncates, copies, acknowledges, bootstraps,
  invokes a tool or contacts a model.
* **Mutation** (`write_bytes_durable`, `LedgerWriter`, `BlobStore`,
  `quarantine_tail`, `install_conversation`, `write_stop`, `acknowledge_stop`):
  explicit calls, each tested on its own, every filesystem call through an
  injectable `DurableOps`.

Exception identity: `PersistenceFailure` here is this module's own (an
OSError, as SV-013 2.2.4 names it). The production chassis has its own
`PersistenceFailure`; unifying the two is part of activation, and nothing here
assumes either way.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# The frame (SV-015 v2 section 1.2)
# ---------------------------------------------------------------------------
#   HDR = "SVL1 " seq:012d " " type:02x " " plen:010d " " hck:16 " "   (49 bytes)
#         hck = sha256(bytes 0-31)[:16], the 32-byte prefix through plen's space
#   BODY = canonical JSON object, plen bytes, never containing 0x0A
#   TRL = " " chain:64 "\n"                                           (66 bytes)
#   chain_k = sha256(bytes.fromhex(chain_{k-1}) || HDR || BODY)
#   chain_0 = sha256(b"SVL1-genesis:" + lineage_id)
MAGIC = b"SVL1 "
HEADER_BYTES = 49
HASHED_PREFIX = 32
TRAILER_BYTES = 66
MIN_RECORD_BYTES = HEADER_BYTES + 2 + TRAILER_BYTES  # 117: the smallest body is `{}`
MAX_LEDGER_BODY = 1_048_576
# The header's decimal fields have fixed widths. The domains are enforced, not
# assumed: a counter that would need a 13th digit is refused, never wrapped.
MAX_SEQ = 10**12 - 1
SEGMENT_MAX = 16 * 1024 * 1024
# Segment file names are `NNNNNN.svl`; a 7th digit would make a name the
# reader does not list, so the writer refuses to rotate past this.
MAX_SEGMENT_NO = 999_999
HEADER_PATTERN = re.compile(rb"SVL1 ([0-9]{12}) ([0-9a-f]{2}) ([0-9]{10}) ([0-9a-f]{16}) ")
TRAILER_PATTERN = re.compile(rb" ([0-9a-f]{64})\n")
HEX64 = re.compile(r"[0-9a-f]{64}")

RECORD_TYPES = {
    0x01: "LEDGER_HEADER",
    0x02: "REQUEST_SENT",
    0x03: "TURN_RESPONSE",
    0x04: "RESPONSE_REFUSED",
    0x05: "INVOKING",
    0x06: "DONE",
    0x07: "TERMINATION",
    0x08: "UNRUN",
    0x09: "SYNTH",
    0x0A: "MSG_APPEND",
    0x0B: "NOTE_WRITTEN",
    0x0C: "HISTORY_REPLACED",
    0x0D: "CHECKPOINT",
    0x0E: "RUN_END",
    0x0F: "RECOVERY",
    0x10: "RECOVERY_ACK",
    0x11: "GC_INTENT",
    0x12: "GC_DONE",
    0x13: "EXTERNAL_EDIT",
    0x14: "EXTERNAL_DELETE",
    0x15: "LEGACY_IMPORT",
    0x16: "LEGACY_REIMPORT",
    0x17: "RECAP_FOLD",
    0x18: "ORIGINAL_EVICTED",
}
TYPE_IDS = {name: type_id for type_id, name in RECORD_TYPES.items()}

# Required payload keys (v2 section 1.2 table; `?` keys are optional and not
# listed). Types 13-18 are "as SV-013 2.2.2-2.2.5"; their keys here are the
# ones those sections name.
REQUIRED_KEYS = {
    "LEDGER_HEADER": ("lineage_id", "segment_no", "first_seq", "prev_chain"),
    "REQUEST_SENT": ("turn_seq", "attempt", "label"),
    "TURN_RESPONSE": ("turn_seq", "assistant", "calls", "normalization", "original_blobs"),
    "RESPONSE_REFUSED": ("turn_seq", "reason", "count"),
    "INVOKING": ("turn_seq", "call_index"),
    "DONE": (
        "turn_seq",
        "call_index",
        "outcome",
        "blob",
        "original_bytes",
        "stored_E",
        "truncated",
        "replaced_chars",
    ),
    "TERMINATION": ("call_key", "kind"),
    "UNRUN": ("call_key", "reason"),
    "SYNTH": ("call_key", "kind"),
    "MSG_APPEND": ("kind", "epoch"),
    "NOTE_WRITTEN": ("gen", "blob", "bytes", "sha256", "source", "mirror_sha256"),
    "HISTORY_REPLACED": ("epoch", "new_blob", "new_count", "new_sha256"),
    "CHECKPOINT": ("covers_seq", "chain_at_cover", "conv", "prev", "run_sha256", "state"),
    "RUN_END": ("exit", "reason"),
    "RECOVERY": ("kind", "detail"),
    "RECOVERY_ACK": ("reason", "resolution"),
    "GC_INTENT": ("records_through", "segments", "blobs"),
    "GC_DONE": ("intent_seq",),
    # SV-013 A8/A11/A12 (lines 549-553) and its retained-originals paragraph
    # (line 667) name these keys `conv_sha` and `sha`.
    "EXTERNAL_EDIT": ("epoch", "conv_sha"),
    "EXTERNAL_DELETE": ("epoch",),
    "LEGACY_IMPORT": ("conv_sha",),
    "LEGACY_REIMPORT": ("conv_sha", "unmerged_suffix"),
    "RECAP_FOLD": ("from", "to", "lines"),
    "ORIGINAL_EVICTED": ("sha",),
}
CALL_KEYS = ("call_index", "provider_id_repr", "wire_id", "name", "args_sha256", "args_E", "admit")
ADMIT_VALUES = ("invoke", "not_run_call_limit", "bad_args", "oversize_args", "bad_name")

# Numeric domains (V2-06(3)). Every integer field a record type names is a
# non-negative integer of at most 12 decimal digits (bool excluded), the width
# the header uses for seq and the maximal-shape frame sizes in v2 1.4.7 assume.
# A value outside it is refused before anything is written, never wrapped.
# Fields not listed (the assistant dict, free text) carry no width assumption
# this module relies on; the 1.4.7 recovery bound is not claimed here at all.
COUNTER_FIELDS = {
    "LEDGER_HEADER": ("segment_no", "first_seq"),
    "REQUEST_SENT": ("turn_seq", "attempt"),
    "TURN_RESPONSE": ("turn_seq",),
    "RESPONSE_REFUSED": ("turn_seq", "count"),
    "INVOKING": ("turn_seq", "call_index"),
    "DONE": ("turn_seq", "call_index", "original_bytes", "stored_E", "replaced_chars"),
    "MSG_APPEND": ("epoch",),
    "NOTE_WRITTEN": ("gen", "bytes"),
    "HISTORY_REPLACED": ("epoch", "new_count"),
    "CHECKPOINT": ("covers_seq",),
    "GC_INTENT": ("records_through",),
    "GC_DONE": ("intent_seq",),
    "EXTERNAL_EDIT": ("epoch",),
    "EXTERNAL_DELETE": ("epoch",),
    "RECAP_FOLD": ("from", "to"),
}
MINIMUM_ONE = {("LEDGER_HEADER", "first_seq"), ("REQUEST_SENT", "attempt")}


class LedgerError(ValueError):
    """A record that must not be written: unknown type, missing key, bad value, oversize."""


class PersistenceFailure(OSError):
    """A write or sync of the session store failed; the run must end 44 persistence_failure."""


def _counter(value, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= MAX_SEQ


def genesis_chain(lineage_id: str) -> str:
    return hashlib.sha256(b"SVL1-genesis:" + lineage_id.encode("utf-8")).hexdigest()


def header_check(prefix: bytes) -> str:
    """hck: the first 16 hex characters of SHA-256 over header bytes 0-31 (32 bytes)."""
    if len(prefix) != HASHED_PREFIX:
        raise ValueError("the header check covers exactly bytes 0-31")
    return hashlib.sha256(prefix).hexdigest()[:16]


def canonical_body(payload: dict) -> bytes:
    """The body bytes: canonical JSON, never a raw newline, non-finite numbers refused."""
    if not isinstance(payload, dict):
        raise LedgerError("a record body is a JSON object")
    try:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise LedgerError(f"the record body is not canonical JSON: {type(error).__name__}") from error
    body = text.encode("utf-8", "backslashreplace")
    if b"\n" in body:  # json.dumps escapes every newline in a string; this cannot happen
        raise LedgerError("a record body contains a newline")
    return body


def validate_payload(type_name: str, payload) -> str | None:
    """Why `payload` is not a valid body for `type_name`, or None.

    Every type's required keys must be present. The fields the scanner and the
    classifier read are also checked for their domain, so a record that parses
    can never make classification raise.
    """
    if not isinstance(payload, dict):
        return "body is not a JSON object"
    missing = [key for key in REQUIRED_KEYS[type_name] if key not in payload]
    if missing:
        return f"missing keys: {', '.join(missing)}"
    for key in COUNTER_FIELDS.get(type_name, ()):
        if not _counter(payload[key], minimum=1 if (type_name, key) in MINIMUM_ONE else 0):
            return key
    if type_name == "LEDGER_HEADER":
        if not isinstance(payload["lineage_id"], str) or not payload["lineage_id"]:
            return "lineage_id"
        if not isinstance(payload["prev_chain"], str) or not HEX64.fullmatch(payload["prev_chain"]):
            return "prev_chain"
    if type_name == "TURN_RESPONSE":
        calls = payload["calls"]
        if not isinstance(calls, list):
            return "calls"
        for position, call in enumerate(calls):
            if not isinstance(call, dict) or any(key not in call for key in CALL_KEYS):
                return "calls[] keys"
            if call["call_index"] != position or isinstance(call["call_index"], bool):
                return "calls[].call_index"
            if call["admit"] not in ADMIT_VALUES:
                return "calls[].admit"
    if type_name == "CHECKPOINT":
        # Invariant CKG (v2 1.4.1): a checkpoint is never written mid-group.
        state = payload["state"]
        if not isinstance(state, dict) or state.get("active_group", 0) is not None or state.get("queued") != []:
            return "state: active_group must be null and queued empty (CKG)"
    if type_name == "DONE":
        outcome = payload["outcome"]
        if not isinstance(outcome, str) or not (
            outcome == "returned" or (outcome.startswith("raised:") and len(outcome) > len("raised:"))
        ):
            return "outcome"
        if not isinstance(payload["blob"], str) or not HEX64.fullmatch(payload["blob"]):
            return "blob"
        if not isinstance(payload["truncated"], bool):
            return "truncated"
    if type_name in ("TERMINATION", "UNRUN", "SYNTH"):
        key = payload["call_key"]
        if key != "direct" and not (
            isinstance(key, list) and len(key) == 2 and all(_counter(part) for part in key)
        ):
            return "call_key"
    return None


def encode_header(seq: int, type_id: int, plen: int) -> bytes:
    if not _counter(seq, minimum=1):
        raise LedgerError(f"seq {seq!r} is outside 1..{MAX_SEQ}")
    if type_id not in RECORD_TYPES:
        raise LedgerError(f"unknown record type {type_id!r}")
    if not isinstance(plen, int) or not 2 <= plen <= MAX_LEDGER_BODY:
        raise LedgerError(f"body of {plen} bytes is outside 2..{MAX_LEDGER_BODY}")
    prefix = f"SVL1 {seq:012d} {type_id:02x} {plen:010d} ".encode("ascii")
    return prefix + header_check(prefix).encode("ascii") + b" "


def decode_body(type_name: str, body: bytes) -> tuple[dict | None, str | None]:
    """The payload a body's bytes mean, or why the scanner rejects them.

    The one rule for both directions: the encoder refuses exactly what this
    rejects, so every frame it produces is readable as written.
    """
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None, "body is not JSON"
    problem = validate_payload(type_name, payload)
    if problem:
        return None, f"body: {problem}"
    # The body must be exactly what the writer would produce for this payload:
    # json.loads alone accepts NaN, duplicate keys and other spellings, which
    # would make the decoded payload differ from what the bytes were meant to say.
    try:
        canonical = canonical_body(payload)
    except LedgerError:
        canonical = None
    if canonical != body:
        return None, "body is not canonical"
    return payload, None


def encode_frame(seq: int, type_name: str, payload: dict, prev_chain: str) -> tuple[bytes, str]:
    """One complete frame and its chain value. Refuses before anything is written.

    Unsupported representation (SV020-03): the specified body encoding (UTF-8
    with backslashreplace) is not injective. A payload whose body would not
    decode back to the same bytes and a valid payload is refused rather than
    written as a frame the scanner rejects. For this encoder that is exactly
    a string (key or value) containing a high surrogate code unit immediately
    followed by a low one: its two escapes decode as one non-BMP scalar. Lone
    surrogates and genuine non-BMP scalars round-trip and are accepted.
    """
    if type_name not in TYPE_IDS:
        raise LedgerError(f"unknown record type {type_name!r}")
    problem = validate_payload(type_name, payload)
    if problem:
        raise LedgerError(f"{type_name}: {problem}")
    if not HEX64.fullmatch(prev_chain):
        raise LedgerError("prev_chain must be 64 lowercase hex characters")
    body = canonical_body(payload)
    header = encode_header(seq, TYPE_IDS[type_name], len(body))
    _, problem = decode_body(type_name, body)
    if problem:
        raise LedgerError(f"{type_name}: unsupported representation ({problem}); the frame would not be read back as written")
    chain = hashlib.sha256(bytes.fromhex(prev_chain) + header + body).hexdigest()
    return header + body + b" " + chain.encode("ascii") + b"\n", chain


# ---------------------------------------------------------------------------
# Reading frames
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Header:
    offset: int
    seq: int
    type_id: int
    plen: int
    check_ok: bool

    @property
    def type_name(self) -> str | None:
        return RECORD_TYPES.get(self.type_id)

    @property
    def extent(self) -> int:
        return HEADER_BYTES + self.plen + TRAILER_BYTES


def read_header(data: bytes, offset: int) -> Header | None:
    """The header at `offset` if its 49 bytes have the header's grammar, else None.

    `check_ok` says whether hck matches bytes 0-31. Nothing past the header is
    read, and a declared length is never trusted until the caller checks it.
    """
    match = HEADER_PATTERN.match(data, offset)
    if match is None or match.end() - offset != HEADER_BYTES:
        return None
    seq, type_hex, plen, check = match.groups()
    prefix = data[offset : offset + HASHED_PREFIX]
    return Header(
        offset=offset,
        seq=int(seq),
        type_id=int(type_hex, 16),
        plen=int(plen),
        check_ok=header_check(prefix) == check.decode("ascii"),
    )


@dataclass(frozen=True)
class Record:
    seq: int
    type_name: str
    payload: dict
    chain: str
    offset: int
    length: int
    segment: int


@dataclass(frozen=True)
class Invalid:
    reason: str
    header: Header | None


def parse_record(data: bytes, offset: int, expected_seq: int, prev_chain: str | None, segment: int) -> Record | Invalid:
    """Parse and verify one frame. `prev_chain=None` takes it from a LEDGER_HEADER's own payload."""
    header = read_header(data, offset)
    if header is None:
        return Invalid("header grammar", None)
    if not header.check_ok:
        return Invalid("header check", header)
    if header.seq != expected_seq:
        return Invalid(f"seq {header.seq} where {expected_seq} was due", header)
    if header.type_name is None:
        return Invalid(f"unknown type {header.type_id:02x}", header)
    if not 2 <= header.plen <= MAX_LEDGER_BODY:
        return Invalid("declared body length out of range", header)
    end = offset + header.extent
    if end > len(data):
        return Invalid("frame extends past the end of the data", header)
    body = data[offset + HEADER_BYTES : offset + HEADER_BYTES + header.plen]
    trailer = TRAILER_PATTERN.fullmatch(data, offset + HEADER_BYTES + header.plen, end)
    if trailer is None or b"\n" in body:
        return Invalid("trailer", header)
    payload, problem = decode_body(header.type_name, body)
    if problem:
        return Invalid(problem, header)
    if prev_chain is None:
        prev_chain = payload.get("prev_chain") if header.type_name == "LEDGER_HEADER" else None
        if prev_chain is None:
            return Invalid("no chain to continue", header)
    computed = hashlib.sha256(bytes.fromhex(prev_chain) + data[offset : offset + HEADER_BYTES] + body).hexdigest()
    if trailer.group(1).decode("ascii") != computed:
        return Invalid("chain", header)
    return Record(header.seq, header.type_name, payload, computed, offset, header.extent, segment)


# ---------------------------------------------------------------------------
# Scanning (v2 section 1.3): the contiguous valid prefix P and the tail T
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Segment:
    number: int
    data: bytes


@dataclass(frozen=True)
class LedgerScan:
    records: tuple[Record, ...]
    last_seq: int  # 0 when P is empty
    last_chain: str | None
    tail: bytes  # every byte after P in the newest segment
    tail_segment: int | None
    tail_offset: int
    stop: str | None = None  # an A2 stop found while scanning
    damaged_at: int | None = None
    detail: str | None = None


def scan_segments(segments: list[Segment], lineage_id: str) -> LedgerScan:
    """P and T over segments oldest first. Pure: reads bytes, changes nothing.

    Every segment starts with a LEDGER_HEADER whose seq continues the previous
    segment and whose `prev_chain` is the running chain (for the oldest
    retained segment it is taken from the header itself; for segment 0 it must
    be the lineage's genesis). An invalid record, or any byte after P, in a
    segment that is not the newest is an A2 stop.
    """
    records: list[Record] = []
    chain: str | None = None
    expected = None
    ordered = sorted(segments, key=lambda segment: segment.number)
    for position, segment in enumerate(ordered):
        newest = position == len(ordered) - 1
        offset = 0
        data = segment.data
        while offset < len(data):
            if expected is None:
                header = read_header(data, offset)
                expected = header.seq if header is not None and header.check_ok else 1
            result = parse_record(data, offset, expected, chain if offset or records else None, segment.number)
            if isinstance(result, Record) and offset == 0:
                problem = _segment_header_problem(result, segment.number, lineage_id, chain, records)
                if problem:
                    result = Invalid(problem, read_header(data, offset))
            elif isinstance(result, Record) and result.type_name == "LEDGER_HEADER":
                result = Invalid("a LEDGER_HEADER inside a segment", read_header(data, offset))
            if isinstance(result, Invalid):
                if not newest:
                    return LedgerScan(
                        tuple(records), records[-1].seq if records else 0, chain, b"", None, 0,
                        stop="ledger_damaged_at", damaged_at=expected, detail=f"segment {segment.number}: {result.reason}",
                    )
                return LedgerScan(tuple(records), records[-1].seq if records else 0, chain, data[offset:], segment.number, offset)
            records.append(result)
            chain = result.chain
            expected = result.seq + 1
            offset += result.length
        if not data and not newest:
            return LedgerScan(
                tuple(records), records[-1].seq if records else 0, chain, b"", None, 0,
                stop="ledger_damaged_at", damaged_at=expected, detail=f"segment {segment.number} is empty",
            )
    newest_number = ordered[-1].number if ordered else None
    tail_offset = len(ordered[-1].data) if ordered else 0
    return LedgerScan(tuple(records), records[-1].seq if records else 0, chain, b"", newest_number, tail_offset)


def _segment_header_problem(record: Record, number: int, lineage_id: str, chain: str | None, records) -> str | None:
    if record.type_name != "LEDGER_HEADER":
        return "a segment does not begin with a LEDGER_HEADER"
    payload = record.payload
    if payload["lineage_id"] != lineage_id:
        return "another lineage's segment"
    if payload["segment_no"] != number:
        return "segment number does not match its name"
    if payload["first_seq"] != record.seq:
        return "first_seq does not match the header's seq"
    if records:
        if number != records[-1].segment + 1:
            return "segment number does not follow the previous segment"
        if payload["prev_chain"] != chain:
            return "prev_chain does not continue the previous segment"
    elif number == 0 and payload["prev_chain"] != genesis_chain(lineage_id):
        return "segment 0 does not start from the lineage genesis"
    return None


# ---------------------------------------------------------------------------
# The legal-next frontier F(P)
# ---------------------------------------------------------------------------
# A reference derivation over P, for the classifier and its tests. It is a
# component: whether production derives the same frontier from its live state
# is part of the activation review, not established here.
UNIT_BOUNDARY_NEXT = frozenset(
    {
        "REQUEST_SENT", "MSG_APPEND", "NOTE_WRITTEN", "HISTORY_REPLACED", "CHECKPOINT", "RUN_END",
        "RECOVERY", "RECOVERY_ACK", "GC_INTENT", "GC_DONE", "EXTERNAL_EDIT", "EXTERNAL_DELETE",
        "LEGACY_IMPORT", "LEGACY_REIMPORT", "RECAP_FOLD", "ORIGINAL_EVICTED", "TERMINATION",
    }
)
AFTER_REQUEST_NEXT = frozenset({"TURN_RESPONSE", "RESPONSE_REFUSED", "RUN_END", "RECOVERY"})
IN_GROUP_NEXT = frozenset({"INVOKING", "UNRUN", "SYNTH", "TERMINATION", "NOTE_WRITTEN", "RUN_END", "ORIGINAL_EVICTED"})
INVOKED_CALL_NEXT = frozenset({"DONE", "SYNTH", "TERMINATION", "NOTE_WRITTEN", "RUN_END"})


@dataclass(frozen=True)
class GroupState:
    turn_seq: int
    calls: tuple[dict, ...]
    invoking: frozenset[int]
    done: dict  # call_index -> DONE payload
    closed: dict  # call_index -> ("UNRUN"|"SYNTH", payload)

    def open_calls(self) -> list[dict]:
        """Admitted calls with no DONE/UNRUN/SYNTH. A call with admit != invoke is
        never invoked and its disposition is fixed by TURN_RESPONSE itself, so it
        never keeps a group open."""
        return [
            c
            for c in self.calls
            if c["admit"] == "invoke" and c["call_index"] not in self.done and c["call_index"] not in self.closed
        ]

    def frontier_call(self) -> dict | None:
        open_calls = self.open_calls()
        return open_calls[0] if open_calls else None


@dataclass(frozen=True)
class PState:
    group: GroupState | None  # the open group, if any
    pending_request: dict | None  # REQUEST_SENT with no response after it
    last_turn: int


def prefix_state(records: tuple[Record, ...]) -> PState:
    """What P leaves open: a tool group, or a request without its response."""
    group: GroupState | None = None
    pending = None
    last_turn = 0
    for record in records:
        payload = record.payload
        name = record.type_name
        if name == "REQUEST_SENT":
            pending, group = payload, None
            last_turn = max(last_turn, payload["turn_seq"])
        elif name in ("TURN_RESPONSE", "RESPONSE_REFUSED"):
            pending = None
            last_turn = max(last_turn, payload["turn_seq"])
            if name == "TURN_RESPONSE":
                group = GroupState(payload["turn_seq"], tuple(payload["calls"]), frozenset(), {}, {})
        elif group is not None and name == "INVOKING" and payload["turn_seq"] == group.turn_seq:
            group = GroupState(group.turn_seq, group.calls, group.invoking | {payload["call_index"]}, group.done, group.closed)
        elif group is not None and name == "DONE" and payload["turn_seq"] == group.turn_seq:
            group = GroupState(group.turn_seq, group.calls, group.invoking, {**group.done, payload["call_index"]: payload}, group.closed)
        elif group is not None and name in ("UNRUN", "SYNTH") and isinstance(payload["call_key"], list):
            turn, index = payload["call_key"]
            if turn == group.turn_seq:
                group = GroupState(group.turn_seq, group.calls, group.invoking, group.done, {**group.closed, index: (name, payload)})
        if group is not None and not group.open_calls():
            # Every admitted call is closed: the group is over (queued messages may follow).
            group = None
    return PState(group, pending, last_turn)


def legal_next_types(records: tuple[Record, ...]) -> frozenset[str]:
    if not records:
        return frozenset({"LEDGER_HEADER"})
    state = prefix_state(records)
    if state.group is not None:
        frontier = state.group.frontier_call()
        if frontier is not None and frontier["call_index"] in state.group.invoking:
            return INVOKED_CALL_NEXT
        return IN_GROUP_NEXT
    if state.pending_request is not None:
        return AFTER_REQUEST_NEXT
    return UNIT_BOUNDARY_NEXT


def scan_frontier(scan: LedgerScan) -> frozenset[str]:
    """F(P) at the position of the tail.

    A tail that begins a segment newer than P's last record can only be that
    segment's LEDGER_HEADER, and rotation happens only at a unit boundary
    (v2 1.4.6); a tail inside P's own segment can never be a LEDGER_HEADER.
    """
    if scan.records and scan.tail_segment is not None and scan.tail_segment != scan.records[-1].segment:
        state = prefix_state(scan.records)
        at_boundary = state.group is None and state.pending_request is None
        return frozenset({"LEDGER_HEADER"}) if at_boundary else frozenset()
    return legal_next_types(scan.records)


# ---------------------------------------------------------------------------
# Tail classification TC0-TC4 (v2 section 1.3)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TailClass:
    kind: str  # TC0 | TC1 | TC2 | TC3 | TC4 | A2
    length: int
    declared_type: str | None = None
    later_valid_offsets: tuple[int, ...] = ()
    stop_reason: str | None = None
    damaged_at: int | None = None


def classify_tail(scan: LedgerScan, frontier: frozenset[str] | None = None) -> TailClass:
    """Classify the bytes after P. Pure: recommends, never acts.

    The probe for later-valid frames runs first (any → A2), skipping the
    declared extent of a first frame whose header is valid with seq = last+1
    (a quoted `SVL1 ` inside its body is content, not a frame).
    """
    if scan.stop:
        return TailClass("A2", 0, stop_reason=scan.stop, damaged_at=scan.damaged_at)
    tail = scan.tail
    length = len(tail)
    if length == 0:
        return TailClass("TC0", 0)
    if frontier is None:
        frontier = scan_frontier(scan)
    last = scan.last_seq
    if scan.records and scan.last_chain and scan.tail_segment == scan.records[-1].segment:
        # A frame that is valid after P belongs in P. A scan handed in with such
        # a "tail" is inconsistent, and classifying it would call a valid record
        # damaged; refuse instead.
        candidate = parse_record(tail, 0, last + 1, scan.last_chain, scan.tail_segment)
        if isinstance(candidate, Record) and candidate.type_name != "LEDGER_HEADER":
            raise ValueError("the tail begins with a frame that is valid after P; rescan")
    first = read_header(tail, 0)
    first_valid = (
        first is not None and first.check_ok and first.seq == last + 1 and 2 <= first.plen <= MAX_LEDGER_BODY
    )
    # The probe covers every offset, 0 included: a checked header at offset 0
    # whose seq skips ahead (a lost segment, a lost record) is a later-valid
    # frame. A first frame with seq = last+1 is the classified frame itself,
    # and offsets inside its declared extent are content, not frames -- for
    # the TC1/TC2/TC3 candidates only (type in F(P), or overlong). A first
    # frame of a type outside F(P) that fits in T gets no such exemption.
    if first_valid and (first.type_name in frontier or length > first.extent):
        skip_until = first.extent
    elif first_valid:
        skip_until = 1
    else:
        skip_until = 0
    later = []
    position = tail.find(MAGIC, 0)
    while position != -1:
        if position >= skip_until:
            header = read_header(tail, position)
            if (
                header is not None
                and header.check_ok
                and header.seq > last
                and 2 <= header.plen <= MAX_LEDGER_BODY
                and position + header.extent <= length
            ):
                later.append(position)
        position = tail.find(MAGIC, position + 1)
    if later:
        return TailClass("A2", length, later_valid_offsets=tuple(later), stop_reason="ledger_damaged_at", damaged_at=last + 1)
    declared_type = first.type_name if first_valid else None
    if length < MIN_RECORD_BYTES:
        return TailClass("TC1", length, declared_type)
    if first_valid and length > first.extent:
        return TailClass("TC3", length, declared_type, stop_reason="ledger_damaged_at", damaged_at=last + 1)
    if first_valid and declared_type in frontier:
        if length < first.extent:
            return TailClass("TC1", length, declared_type)
        return TailClass("TC2", length, declared_type)
    return TailClass("TC4", length, declared_type, stop_reason="ledger_tail_ambiguous")


# ---------------------------------------------------------------------------
# Recovery outcomes (pure)
# ---------------------------------------------------------------------------
UNRUN_TEXT = "not run: the run ended before this call was invoked"
UNKNOWN_TEXT = "outcome unknown: the run ended while this call was running; its effects may or may not have happened"
DAMAGED_TAIL_TEXT = "outcome unknown: the runtime's record of this call was damaged; it may or may not have run"
HIDDEN_TURN_NOTICE = (
    "[runtime] records after ledger seq {seq} were damaged beyond reconstruction; requests may have "
    "been answered and tools may have run that this conversation does not show"
)


def returned_lost_text(original_bytes: int, sha256: str) -> str:
    return f"this call returned {original_bytes} bytes (sha256 {sha256}), but the stored result could not be recovered"


def raised_lost_text(exception_type: str, original_bytes: int, sha256: str) -> str:
    return (
        f"this call raised {exception_type}; its stored error text ({original_bytes} bytes, "
        f"sha256 {sha256}) could not be recovered"
    )


@dataclass(frozen=True)
class CallOutcome:
    call_index: int
    wire_id: object
    name: object
    status: str  # known | known_payload_lost | unknown | unrun | not_invoked
    text: str | None


@dataclass(frozen=True)
class RecoveryPlan:
    action: str  # continue | stop
    tail: TailClass
    stop_reason: str | None = None
    calls: tuple[CallOutcome, ...] = ()
    notices: tuple[str, ...] = ()
    recovery_records: tuple[dict, ...] = ()  # recommended RECOVERY payloads, never written here
    quarantine_tail: bool = False  # recommend copying T to corrupt/ and truncating
    next_request: dict | None = None  # {"turn_seq", "attempt"} after possible duplicate spend
    use_previous_checkpoint: bool = False
    handoff_mirror_check: bool = False


def request_label(lineage_id: str, turn_seq: int, attempt: int) -> str:
    """SV-013 2.2.3 t1: `<lineage_id>:<turn_seq>:<attempt>`."""
    return f"{lineage_id}:{turn_seq}:{attempt}"


def tail_stop_detail(tail: bytes) -> dict:
    """The STOPPED detail for a tail stop. Its hash binds a later acknowledgement to these bytes."""
    return {"bytes": len(tail), "tail_sha256": hashlib.sha256(tail).hexdigest()}


def _type_hex(type_name: str | None) -> str | None:
    return None if type_name is None else f"{TYPE_IDS[type_name]:02x}"


def plan_recovery(scan: LedgerScan, tail: TailClass, *, read_blob, acknowledgement: dict | None = None) -> RecoveryPlan:
    """The conservative outcome of P and T. Pure; `read_blob(sha) -> bytes | None` only reads.

    No outcome is inferred from which damage pattern is seen; byte-identical
    tails give identical plans. Only TC1 (provably incomplete) and the
    one-frame TC2 rule ever call a call whose gate might be in T "unrun";
    TC4, acknowledged or not, never does.

    TC4 continues only with an `acknowledgement` from `acknowledge_stop` for
    `continue-conservative` whose `tail_sha256` is this tail's. That is
    permission, not evidence; a stale acknowledgement, or any other
    resolution (bootstrap-preserving is the caller's separate choice), leaves
    the stop in place.
    """
    if tail.kind in ("A2", "TC3"):
        return RecoveryPlan("stop", tail, stop_reason="ledger_damaged_at")
    if tail.kind == "TC4" and not (
        isinstance(acknowledgement, dict)
        and acknowledgement.get("reason") == "ledger_tail_ambiguous"
        and acknowledgement.get("resolution") == "continue-conservative"
        and acknowledgement.get("tail_sha256") == hashlib.sha256(scan.tail).hexdigest()
    ):
        return RecoveryPlan("stop", tail, stop_reason="ledger_tail_ambiguous")
    if tail.kind == "TC2" and tail.declared_type == "LEDGER_HEADER":
        # v2 1.4.10, segment rotation row: header damage -> A2. A torn header
        # shorter than its declared frame is TC1 and is not affected.
        return RecoveryPlan("stop", tail, stop_reason="ledger_damaged_at")

    state = prefix_state(scan.records)
    notices: list[str] = []
    records: list[dict] = []
    next_request = None
    previous_checkpoint = False
    mirror_check = False
    damaged_invoking = tail.kind == "TC2" and tail.declared_type == "INVOKING"
    hidden = tail.kind == "TC4"

    if tail.kind == "TC1":
        records.append(
            {"kind": "torn_incomplete", "detail": {"bytes": tail.length, "declared_type": _type_hex(tail.declared_type)}}
        )
    if tail.kind == "TC2":
        records.append({"kind": "damaged_final", "detail": {"type": _type_hex(tail.declared_type), "bytes": tail.length}})
    if hidden:
        records.append({"kind": "damaged_tail_acknowledged", "detail": {"bytes": tail.length}})
        notices.append(HIDDEN_TURN_NOTICE.format(seq=scan.last_seq))
        # v2 1.3 TC4 acknowledgement, "Notes: the HANDOFF.md mirror rule above":
        # a hidden NOTE_WRITTEN and its mirror are reachable from any P.
        # Recommended only; the comparison and adoption are not done here.
        mirror_check = True

    spend = False
    if state.pending_request is not None:
        spend = True
        next_request = {"turn_seq": state.pending_request["turn_seq"], "attempt": state.pending_request["attempt"] + 1}
    if tail.kind == "TC2" and tail.declared_type in ("REQUEST_SENT", "TURN_RESPONSE"):
        spend = True
        if state.pending_request is not None:
            bump = 2 if tail.declared_type == "REQUEST_SENT" else 1
            next_request = {
                "turn_seq": state.pending_request["turn_seq"],
                "attempt": state.pending_request["attempt"] + bump,
            }
        else:
            next_request = {"turn_seq": state.last_turn + 1, "attempt": 2}
    if hidden:
        # Any number of hidden turns may follow P: a request may have been sent.
        spend = True
        if next_request is None:
            next_request = {"turn_seq": state.last_turn + 1, "attempt": 2}
    if spend:
        records.append({"kind": "possible_duplicate_spend", "detail": next_request})
    if tail.kind == "TC2" and tail.declared_type in ("MSG_APPEND", "NOTE_WRITTEN", "HISTORY_REPLACED"):
        notices.append(f"[runtime] a damaged {tail.declared_type} record was lost at recovery")
        mirror_check = tail.declared_type == "NOTE_WRITTEN"
    elif tail.kind == "TC2" and tail.declared_type == "CHECKPOINT":
        previous_checkpoint = True
    elif tail.kind == "TC2" and tail.declared_type not in ("INVOKING", "REQUEST_SENT", "TURN_RESPONSE", "DONE"):
        notices.append(f"[runtime] a damaged {tail.declared_type} record was set aside at recovery")

    calls: list[CallOutcome] = []
    if state.group is not None:
        frontier = state.group.frontier_call()
        for call in state.group.calls:
            calls.append(_call_outcome(call, state.group, frontier, damaged_invoking, hidden, read_blob))

    return RecoveryPlan(
        "continue",
        tail,
        calls=tuple(calls),
        notices=tuple(notices),
        recovery_records=tuple(records),
        quarantine_tail=tail.kind in ("TC1", "TC2", "TC4"),
        next_request=next_request,
        use_previous_checkpoint=previous_checkpoint,
        handoff_mirror_check=mirror_check,
    )


def _call_outcome(call, group: GroupState, frontier, damaged_invoking: bool, hidden: bool, read_blob) -> CallOutcome:
    index = call["call_index"]
    wire, name = call.get("wire_id"), call.get("name")
    if index in group.done:
        done = group.done[index]
        data = read_blob(done["blob"])
        if data is not None:
            return CallOutcome(index, wire, name, "known", data.decode("utf-8", "replace"))
        outcome = done["outcome"]
        if outcome == "returned":
            text = returned_lost_text(done["original_bytes"], done["blob"])
        else:
            text = raised_lost_text(outcome.split(":", 1)[1], done["original_bytes"], done["blob"])
        return CallOutcome(index, wire, name, "known_payload_lost", text)
    if index in group.closed:
        kind, payload = group.closed[index]
        if kind == "UNRUN":
            return CallOutcome(index, wire, name, "unrun", payload["reason"])
        text = DAMAGED_TAIL_TEXT if payload["kind"] == "unknown_damaged_tail" else UNKNOWN_TEXT
        return CallOutcome(index, wire, name, "unknown", text)
    if call["admit"] != "invoke":
        # Never invoked, whatever the tail. Its fixed admission text is SV-013
        # K-E2's to supply; the disposition is stated here.
        return CallOutcome(index, wire, name, "not_invoked", None)
    if hidden:
        # TC4 acknowledged: its DONE may be hidden in T as well, so every
        # not-closed admitted call is SYNTH{unknown_damaged_tail} (v2 1.3).
        return CallOutcome(index, wire, name, "unknown", DAMAGED_TAIL_TEXT)
    if index in group.invoking:
        return CallOutcome(index, wire, name, "unknown", UNKNOWN_TEXT)
    if damaged_invoking and frontier is not None and index == frontier["call_index"]:
        return CallOutcome(index, wire, name, "unknown", DAMAGED_TAIL_TEXT)
    return CallOutcome(index, wire, name, "unrun", UNRUN_TEXT)


# ---------------------------------------------------------------------------
# Durable mutation
# ---------------------------------------------------------------------------
class DurableOps:
    """Every filesystem call the mutation helpers make, so a test can fail any of them."""

    def open(self, path: str, flags: int, mode: int = 0o644) -> int:
        return os.open(path, flags, mode)

    def write(self, fd: int, data) -> int:
        return os.write(fd, data)

    def fsync(self, fd: int) -> None:
        os.fsync(fd)

    def close(self, fd: int) -> None:
        os.close(fd)

    def rename(self, source: str, target: str) -> None:
        os.replace(source, target)

    def link(self, source: str, target: str) -> None:
        os.link(source, target)

    def unlink(self, path: str) -> None:
        os.unlink(path)

    def mkdir(self, path: str) -> None:
        os.mkdir(path, 0o755)

    def truncate(self, path: str, length: int) -> None:
        os.truncate(path, length)

    def sync_dir(self, path: str) -> None:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def read(self, path: str, limit: int) -> bytes:
        """At most `limit` bytes; a longer file is refused, never partly trusted."""
        with open(path, "rb") as handle:
            data = handle.read(limit + 1)
        if len(data) > limit:
            raise ReadTooLarge(f"{Path(path).name} is larger than {limit} bytes")
        return data


class ReadTooLarge(OSError):
    """A store file exceeds the read bound its caller set."""


# Read bounds [CM], chosen here. A segment rotates at a unit boundary once it
# reaches SEGMENT_MAX, so it can exceed that by one unit's frames; the bound
# below leaves room for that without claiming a maximal unit shape (K-E2).
MAX_SEGMENT_READ = 2 * SEGMENT_MAX
MAX_BLOB_READ = 16 * 1024 * 1024  # v2 1.4.6 SET_HISTORY_MAX, the largest blob kind
MAX_MARKER_READ = 64 * 1024


def _write_all(ops: DurableOps, fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            written = ops.write(fd, view)
        except InterruptedError:
            continue
        if not written:
            raise OSError("a write accepted no bytes")
        view = view[written:]


def write_bytes_durable(path: Path, data: bytes, *, ops: DurableOps | None = None, mode: int = 0o644) -> None:
    """Temp `O_EXCL` → write all → fsync → rename → fsync(directory) (SV-013 2.2.2).

    Any failure raises PersistenceFailure and leaves the target either as it
    was or replaced whole; a temp left behind is removed when possible.
    """
    ops = ops or DurableOps()
    path = Path(path)
    temp = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    fd = None
    try:
        fd = ops.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, mode)
        _write_all(ops, fd, data)
        ops.fsync(fd)
        ops.close(fd)
        fd = None
        ops.rename(str(temp), str(path))
        ops.sync_dir(str(path.parent))
    except OSError as error:
        if fd is not None:
            with contextlib.suppress(OSError):
                ops.close(fd)
        with contextlib.suppress(OSError):
            ops.unlink(str(temp))
        raise PersistenceFailure(f"durable write of {path.name} failed: {type(error).__name__}: {error}") from error


def mark_fsync_failed(session_dir: Path, detail: str, *, ops: DurableOps | None = None) -> bool:
    """Best-effort FSYNC_FAILED marker (v2 1.4.9). True only if the marker write returned.

    The marker goes through the same failing medium. If it fails, nothing is
    claimed: the next start sees what a process death would leave.
    """
    try:
        write_bytes_durable(Path(session_dir) / "FSYNC_FAILED", json.dumps({"detail": detail}).encode(), ops=ops)
    except PersistenceFailure:
        return False
    return True


def write_stop(session_dir: Path, reason: str, detail=None, *, ops: DurableOps | None = None) -> None:
    write_bytes_durable(Path(session_dir) / "STOPPED", json.dumps({"reason": reason, "detail": detail}, sort_keys=True).encode(), ops=ops)


ACK_RESOLUTIONS = {
    "ledger_tail_ambiguous": ("continue-conservative", "bootstrap-preserving"),
}
DEFAULT_RESOLUTIONS = ("continue-from-bound", "bootstrap-preserving")


def acknowledge_stop(session_dir: Path, reason: str, resolution: str, *, ops: DurableOps | None = None) -> dict:
    """The operator's acknowledgement capability: verify the stop, return the RECOVERY_ACK payload.

    It checks that a STOPPED record with this reason exists and that the
    resolution is one this reason allows. It is a capability for an operator
    to exercise, not a decision this module or a test makes about any real
    stop. It does **not** append the record or
    remove STOPPED: the caller does both, in that order, through the ledger
    writer and `clear_stop`. Acknowledgement grants permission to continue; it
    adds no evidence about what the damaged bytes held.
    """
    ops = ops or DurableOps()
    stopped = Path(session_dir) / "STOPPED"
    try:
        record = json.loads(ops.read(str(stopped), MAX_MARKER_READ).decode("utf-8"))
        if not isinstance(record, dict):
            raise ValueError("STOPPED is not an object")
    except (OSError, ValueError) as error:
        raise LedgerError(f"no readable STOPPED record to acknowledge: {type(error).__name__}") from error
    if record.get("reason") != reason:
        raise LedgerError(f"the stop is {record.get('reason')!r}, not {reason!r}")
    if resolution not in ACK_RESOLUTIONS.get(reason, DEFAULT_RESOLUTIONS):
        raise LedgerError(f"{resolution!r} is not a resolution for {reason!r}")
    acknowledgement = {"reason": reason, "resolution": resolution}
    detail = record.get("detail")
    if isinstance(detail, dict) and isinstance(detail.get("tail_sha256"), str):
        # Binds the acknowledgement to the bytes that were stopped on: a later,
        # different damaged tail is a new stop, not covered by this one.
        acknowledgement["tail_sha256"] = detail["tail_sha256"]
    return acknowledgement


def clear_stop(session_dir: Path, *, ops: DurableOps | None = None) -> None:
    ops = ops or DurableOps()
    try:
        ops.unlink(str(Path(session_dir) / "STOPPED"))
        ops.sync_dir(str(session_dir))
    except OSError as error:
        raise PersistenceFailure(f"STOPPED could not be removed durably: {error}") from error


class BlobStore:
    """`blobs/<sha256>`, written durably before any record names them."""

    def __init__(self, blobs_dir: Path, *, ops: DurableOps | None = None) -> None:
        self.dir = Path(blobs_dir)
        self.ops = ops or DurableOps()
        self.fenced = False  # whether this store's fsync of blobs/'s parent has returned

    def ensure(self) -> None:
        """blobs/ exists and its name is durable in its parent (SV020-01).

        A directory that survived a process death may still be lost by a host
        loss until its parent's fsync returns, so the fence runs on first use
        whether or not the directory already exists; only a returned fence is
        cached.
        """
        if self.fenced:
            return
        try:
            if not self.dir.is_dir():
                self.ops.mkdir(str(self.dir))
            self.ops.sync_dir(str(self.dir.parent))
        except OSError as error:
            raise PersistenceFailure(f"blobs/ could not be made durable: {error}") from error
        self.fenced = True

    def put(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        self.ensure()
        write_bytes_durable(self.dir / sha, data, ops=self.ops)
        return sha

    def get(self, sha: str) -> bytes | None:
        if not HEX64.fullmatch(sha or ""):
            return None
        try:
            data = self.ops.read(str(self.dir / sha), MAX_BLOB_READ)
        except OSError:  # missing, unreadable, or over the bound: the payload is lost
            return None
        return data if hashlib.sha256(data).hexdigest() == sha else None


def segment_name(number: int) -> str:
    if not isinstance(number, int) or isinstance(number, bool) or not 0 <= number <= MAX_SEGMENT_NO:
        raise LedgerError(f"segment number {number!r} is outside 0..{MAX_SEGMENT_NO}")
    return f"{number:06d}.svl"


def read_segments(ledger_dir: Path, *, ops: DurableOps | None = None, limit: int = MAX_SEGMENT_READ) -> list[Segment]:
    """Every `NNNNNN.svl` in ledger/, each read under `limit` (ReadTooLarge otherwise: a stop)."""
    ops = ops or DurableOps()
    segments = []
    for path in sorted(Path(ledger_dir).glob("*.svl")):
        stem = path.stem
        if len(stem) == 6 and stem.isdigit():
            segments.append(Segment(int(stem), ops.read(str(path), limit)))
    return segments


class LedgerWriter:
    """Appends SVL1 frames: every record synced, every gate synced before its effect.

    A writer that has seen any write or sync error is broken and refuses every
    later append: the bytes it may have left are the next start's to classify.
    """

    def __init__(
        self,
        session_dir: Path,
        lineage_id: str,
        *,
        next_seq: int,
        prev_chain: str,
        segment_no: int,
        ops: DurableOps | None = None,
        segment_max: int = SEGMENT_MAX,
    ) -> None:
        self.session_dir = Path(session_dir)
        self.ledger_dir = self.session_dir / "ledger"
        self.lineage_id = lineage_id
        self.next_seq = next_seq
        self.chain = prev_chain
        self.segment_no = segment_no
        self.ops = ops or DurableOps()
        self.segment_max = segment_max
        self.fd: int | None = None
        self.segment_bytes = 0
        self.broken = False
        # None until a failure; then whether the best-effort FSYNC_FAILED
        # marker write returned (v2 1.4.9). False claims nothing durable.
        self.marker_written: bool | None = None
        # Whether this writer's fsyncs of session/ and ledger/ have returned:
        # names this process found (ledger/, segments) are not durable until then.
        self.namespace_fenced = False
        self.blobs = BlobStore(self.session_dir / "blobs", ops=self.ops)

    # -- starting -------------------------------------------------------------
    @classmethod
    def create(cls, session_dir: Path, lineage_id: str, *, ops: DurableOps | None = None, segment_max: int = SEGMENT_MAX) -> LedgerWriter:
        """A new lineage: ledger/ (fenced in session/), segment 0 from the genesis chain.

        The fence runs even when ledger/ survived an earlier attempt (SV020-01).
        An existing *empty* segment 0 (its creation's header was torn and has
        been set aside) is reused; any other existing segment 0 is refused.
        """
        writer = cls(session_dir, lineage_id, next_seq=1, prev_chain=genesis_chain(lineage_id), segment_no=-1, ops=ops, segment_max=segment_max)
        if not writer.ledger_dir.is_dir():
            try:
                writer.ops.mkdir(str(writer.ledger_dir))
            except OSError as error:
                raise PersistenceFailure(f"ledger/ could not be created: {error}") from error
        writer._fence_namespace()
        first = writer.ledger_dir / segment_name(0)
        writer.open_segment(reuse_empty=first.exists())
        return writer

    @classmethod
    def continue_after(cls, session_dir: Path, lineage_id: str, scan: LedgerScan, *, ops: DurableOps | None = None, segment_max: int = SEGMENT_MAX) -> LedgerWriter:
        """Continue after a scan whose tail has been resolved (no stop, nothing after P).

        If the newest segment is an empty file after P's segment (its creation
        or header was lost and the torn header quarantined), that segment
        number is reused: its LEDGER_HEADER is written with first_seq = last+1
        and fenced, exactly as a rotation would (O2-5).

        Before it returns -- so before any gate can run -- the writer fsyncs
        session/ and ledger/ (SV020-01): a complete segment found readable may
        be one whose rotation died before its directory fsync, and its name is
        not durable until a fence returns. A fence failure raises
        PersistenceFailure and no writer is returned.
        """
        if scan.stop or scan.tail:
            raise LedgerError("the ledger has an unresolved tail or stop; recover first")
        if not scan.records:
            raise LedgerError("an empty ledger is created, not continued")
        last = scan.records[-1]
        writer = cls(session_dir, lineage_id, next_seq=last.seq + 1, prev_chain=last.chain, segment_no=last.segment, ops=ops, segment_max=segment_max)
        writer._fence_namespace()
        if scan.tail_segment is not None and scan.tail_segment != last.segment:
            if scan.tail_segment != last.segment + 1 or scan.tail_offset != 0:
                raise LedgerError("the newest segment does not follow the last record's segment")
            writer.open_segment(reuse_empty=True)
            return writer
        path = writer.ledger_dir / segment_name(last.segment)
        try:
            writer.fd = writer.ops.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CLOEXEC)
        except OSError as error:
            raise PersistenceFailure(f"the newest segment could not be opened: {error}") from error
        writer.segment_bytes = last.offset + last.length
        return writer

    def open_segment(self, *, reuse_empty: bool = False) -> None:
        """Rotate: new file O_EXCL, its LEDGER_HEADER, fsync the file, then fsync ledger/.

        Until the directory sync returns, the new name may vanish (M-2); the
        previous segment then ends at its last record (TC0), and the next
        writer recreates this segment number with the same first_seq.
        `reuse_empty` is for an existing empty file only (O2-5's surviving name).
        Every refusal (number or seq width, a non-empty file to reuse) happens
        before any byte is written.
        """
        self._usable()
        self._fence_namespace()
        number = self.segment_no + 1
        path = self.ledger_dir / segment_name(number)
        payload = {"lineage_id": self.lineage_id, "segment_no": number, "first_seq": self.next_seq, "prev_chain": self.chain}
        frame, chain = encode_frame(self.next_seq, "LEDGER_HEADER", payload, self.chain)
        flags = os.O_WRONLY | os.O_APPEND | os.O_CLOEXEC | (0 if reuse_empty else os.O_CREAT | os.O_EXCL)
        try:
            fd = self.ops.open(str(path), flags)
        except OSError as error:
            # No byte was written, so nothing is in doubt: no FSYNC_FAILED marker.
            self.broken = True
            raise PersistenceFailure(f"segment {path.name} could not be opened: {error}") from error
        if reuse_empty and os.fstat(fd).st_size != 0:
            with contextlib.suppress(OSError):
                self.ops.close(fd)
            raise LedgerError("the segment to reuse is not empty")
        try:
            _write_all(self.ops, fd, frame)
            self.ops.fsync(fd)
            self.ops.sync_dir(str(self.ledger_dir))
        except OSError as error:
            self._fail(fd, error)
        if self.fd is not None:
            with contextlib.suppress(OSError):
                self.ops.close(self.fd)
        self.fd, self.segment_no, self.segment_bytes = fd, number, len(frame)
        self.chain, self.next_seq = chain, self.next_seq + 1

    # -- appending ------------------------------------------------------------
    def append(self, type_name: str, payload: dict) -> Record:
        """One synced record. Encoding refusals (LedgerError) happen before any byte is written."""
        self._usable()
        if type_name == "LEDGER_HEADER":
            raise LedgerError("segment headers are written by open_segment")
        frame, chain = encode_frame(self.next_seq, type_name, payload, self.chain)
        self._fence_namespace()
        offset = self.segment_bytes
        try:
            _write_all(self.ops, self.fd, frame)
            self.ops.fsync(self.fd)
        except OSError as error:
            self._fail(None, error)
        record = Record(self.next_seq, type_name, payload, chain, offset, len(frame), self.segment_no)
        self.segment_bytes += len(frame)
        self.chain, self.next_seq = chain, self.next_seq + 1
        return record

    def rotate_if_full(self) -> bool:
        """Rotate once the segment has reached segment_max. Call only at a unit boundary (v2 1.4.6)."""
        self._usable()
        if self.segment_bytes < self.segment_max:
            return False
        self.open_segment()
        return True

    def gate(self, type_name: str, payload: dict, effect):
        """Append a gate record; only after its sync returns is `effect()` called.

        If the append or its sync fails, the effect is not called and
        PersistenceFailure propagates (the run ends 44).
        """
        if type_name not in ("REQUEST_SENT", "INVOKING"):
            raise LedgerError(f"{type_name} is not an effect gate")
        self.append(type_name, payload)
        return effect()

    def append_with_blob(self, type_name: str, data: bytes, build) -> Record:
        """Blob before reference: the blob is durable before the record naming it is written.

        A blob that cannot be made durable is a persistence failure like any
        other sync error: the record is never written and the writer is broken.
        """
        self._usable()
        try:
            sha = self.blobs.put(data)
        except PersistenceFailure as error:
            self._fail(None, error)
        return self.append(type_name, build(sha))

    def close(self) -> None:
        if self.fd is not None:
            with contextlib.suppress(OSError):
                self.ops.close(self.fd)
            self.fd = None

    def _fence_namespace(self) -> None:
        """fsync(session/) for the ledger/ name, then fsync(ledger/) for the segment names.

        Once per writer, before its first write (SV020-01); cached only after
        both return. session/ itself is a durable-root precondition. A failure
        is a sync error: the writer is broken and nothing dependent runs.
        """
        if self.namespace_fenced:
            return
        try:
            self.ops.sync_dir(str(self.session_dir))
            self.ops.sync_dir(str(self.ledger_dir))
        except OSError as error:
            self._fail(None, error)
        self.namespace_fenced = True

    # -- failure --------------------------------------------------------------
    def _usable(self) -> None:
        if self.broken:
            raise PersistenceFailure("the ledger writer failed earlier and accepts nothing more")

    def _fail(self, fd, error: OSError):
        self.broken = True
        if fd is not None:
            with contextlib.suppress(OSError):
                self.ops.close(fd)
        self.marker_written = mark_fsync_failed(self.session_dir, f"{type(error).__name__}: {error}", ops=self.ops)
        raise PersistenceFailure(f"ledger write failed: {type(error).__name__}: {error}") from error


# ---------------------------------------------------------------------------
# Quarantine (v2 1.4.8): admission before any copy or truncation
# ---------------------------------------------------------------------------
MAX_CORRUPT_FILES = 64  # [CM] chosen here: SV-013/SV-015 name the caps, not their values
MAX_CORRUPT_BYTES = 64 * 1024 * 1024


@dataclass
class Quarantine:
    corrupt_dir: Path
    max_files: int = MAX_CORRUPT_FILES
    max_bytes: int = MAX_CORRUPT_BYTES
    ops: DurableOps = field(default_factory=DurableOps)

    def usage(self) -> tuple[int, int]:
        if not Path(self.corrupt_dir).is_dir():
            return 0, 0
        files = [path for path in Path(self.corrupt_dir).iterdir() if path.is_file()]
        return len(files), sum(path.stat().st_size for path in files)

    def admits(self, size: int) -> bool:
        count, used = self.usage()
        return count + 1 <= self.max_files and used + size <= self.max_bytes


@dataclass(frozen=True)
class QuarantineResult:
    applied: bool
    stop_reason: str | None
    copy: Path | None


def quarantine_tail(
    session_dir: Path, scan: LedgerScan, plan: RecoveryPlan, quarantine: Quarantine, *, ops: DurableOps | None = None
) -> QuarantineResult:
    """Copy T to corrupt/ and truncate the segment to the end of P -- or, at capacity, neither.

    Only for a plan that continues and recommends it (TC1, TC2, acknowledged
    TC4); a stop -- an unacknowledged TC4 among them -- is never truncated
    here. At capacity: no copy, **no truncation**,
    `STOPPED{corrupt_quarantine_full}`; the tail bytes stay where they are.
    The segment is re-read first, so the bytes truncated are exactly the
    bytes copied, and the copy -- name, directory and parent fences -- is
    durable before the truncation.
    """
    ops = ops or DurableOps()
    if plan.action != "continue" or not plan.quarantine_tail:
        raise LedgerError(f"the recovery plan ({plan.action}, {plan.tail.kind}) does not set the tail aside")
    if scan.stop or not scan.tail or scan.tail_segment is None:
        raise LedgerError("there is no classified tail to set aside")
    if plan.tail.length != len(scan.tail):
        raise LedgerError("the plan was made for a different tail")
    session_dir = Path(session_dir)
    segment_path = session_dir / "ledger" / segment_name(scan.tail_segment)
    current = ops.read(str(segment_path), MAX_SEGMENT_READ)
    if current[scan.tail_offset :] != scan.tail:
        raise LedgerError("the segment changed after it was scanned")
    if not quarantine.admits(len(scan.tail)):
        write_stop(session_dir, "corrupt_quarantine_full", {"bytes": len(scan.tail)}, ops=ops)
        return QuarantineResult(False, "corrupt_quarantine_full", None)
    corrupt = Path(quarantine.corrupt_dir)
    # corrupt/'s name is fenced in its parent on every call, whether it is new
    # or survived a process death (SV020-01): truncation removes the only other
    # copy of the tail, so it must never depend on an unfenced name.
    try:
        if not corrupt.is_dir():
            ops.mkdir(str(corrupt))
        ops.sync_dir(str(corrupt.parent))
    except OSError as error:
        raise PersistenceFailure(f"corrupt/ could not be made durable: {error}") from error
    # The name carries the content hash: a second recovery at the same offset
    # with different bytes gets its own file and never replaces earlier evidence.
    digest = hashlib.sha256(scan.tail).hexdigest()[:16]
    copy = corrupt / f"ledger-{scan.tail_segment:06d}-{scan.tail_offset}-{digest}.bin"
    write_bytes_durable(copy, scan.tail, ops=ops)
    fd = None
    try:
        ops.truncate(str(segment_path), scan.tail_offset)
        fd = ops.open(str(segment_path), os.O_WRONLY | os.O_CLOEXEC)
        ops.fsync(fd)
    except OSError as error:
        raise PersistenceFailure(f"the segment could not be truncated durably: {error}") from error
    finally:
        if fd is not None:
            with contextlib.suppress(OSError):
                ops.close(fd)
    return QuarantineResult(True, None, copy)


# ---------------------------------------------------------------------------
# The conversation file (SV-013 CK1-CK4)
# ---------------------------------------------------------------------------
def conversation_bytes(messages: list) -> bytes:
    """CK1: the plain list exactly as the chassis writes it today through
    `common.write_json_atomic` (indent 2, ASCII escapes, trailing newline)."""
    return (json.dumps(messages, indent=2) + "\n").encode("ascii")


def install_conversation(session_dir: Path, data: bytes, *, ops: DurableOps | None = None) -> str:
    """CK2-CK4: temp fsync; the old file kept as conversation.prev.json; rename; fsync(session/).

    Returns the installed bytes' SHA-256. The name `conversation.json` is never
    absent between the two renames: the previous inode is hard-linked aside
    before the new file replaces it.
    """
    ops = ops or DurableOps()
    session_dir = Path(session_dir)
    target = session_dir / "conversation.json"
    temp = session_dir / f".conversation.{secrets.token_hex(8)}.tmp"
    fd = None
    try:
        fd = ops.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC)
        _write_all(ops, fd, data)
        ops.fsync(fd)
        ops.close(fd)
        fd = None
        if target.exists():
            previous_temp = session_dir / ".prev.tmp"
            with contextlib.suppress(FileNotFoundError):
                ops.unlink(str(previous_temp))
            ops.link(str(target), str(previous_temp))
            ops.rename(str(previous_temp), str(session_dir / "conversation.prev.json"))
        ops.rename(str(temp), str(target))
        ops.sync_dir(str(session_dir))
    except OSError as error:
        if fd is not None:
            with contextlib.suppress(OSError):
                ops.close(fd)
        raise PersistenceFailure(f"the conversation could not be installed: {type(error).__name__}: {error}") from error
    return hashlib.sha256(data).hexdigest()
