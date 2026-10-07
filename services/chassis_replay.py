"""Session state and the replay reducer: one pure function per mutating record.

Standard library only; nothing here writes, sends or invokes. Contract: SV-015
v2 section 1.4 (units, CHECKPOINT state, live facts, newest/previous-base
replay) with SV-013 sections 2.2.2-2.2.5's retained rules.

**One reducer for both directions.** The live session (`chassis_session`)
appends a record and then applies *this* reducer to its in-memory state;
recovery applies the same reducer to the records it reads back. Every message
the conversation gains is built here, from record payloads only, so a replay
of the same records produces the same list -- byte for byte once serialized,
because every message is rebuilt in one fixed key order (ledger bodies are
key-sorted; the conversation file is not).

What the reducer refuses (`ReplayMismatch`) is any record the state machine
could not have written in that position: a call answered out of order, a
message appended inside an open group, a counter that does not continue. The
caller turns that into a diagnostic stop, never a guess.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field

MAX_COUNTER = 10**12 - 1  # the ledger header's 12-digit width (chassis_persistence.MAX_SEQ)
HEX64_CHARS = frozenset("0123456789abcdef")

NOTE_PREFIX = "A previous run of you left this handoff note:\n\n"
MAX_PENDING_NOTES = 16
ORIGINALS_MAX_BYTES = 4 * 1024 * 1024
ORIGINALS_MAX_COUNT = 64
ORIGINAL_MAX_ITEM = 256 * 1024

MESSAGE_ROLES = {"user": "user", "system": "system", "notice": "user", "note": "user"}
REQUEST_OUTCOMES = ("responded", "refused", "failed_unknown", "possible_duplicate_spend")
LEGACY_STATUSES = ("none", "legacy_matched_unproven", "legacy_unadopted_unproven", "adopted_by_foreign_runtime")
NOTE_SOURCES = ("runtime", "file_edit", "legacy")

UNRUN_TEXT = "not run: the run ended before this call was invoked"
UNKNOWN_TEXT = "outcome unknown: the run ended while this call was running; its effects may or may not have happened"
DAMAGED_TAIL_TEXT = "outcome unknown: the runtime's record of this call was damaged; it may or may not have run"
SYNTH_TEXTS = {"unknown": UNKNOWN_TEXT, "unknown_damaged_tail": DAMAGED_TAIL_TEXT}
DROPPED_NOTE_NOTICE = "[runtime] a handoff note was not saved: {count} earlier notes from this run were unadopted"


class ReplayMismatch(ValueError):
    """A record the state machine could not have written here, or a blob replay cannot read."""


class StateError(ValueError):
    """A CHECKPOINT state that does not satisfy its schema or domains."""


def is_hex64(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64_CHARS


def counter(value, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= MAX_COUNTER


def conversation_bytes(messages: list) -> bytes:
    """CK1: `json.dumps(messages, indent=2) + "\\n"`, ASCII -- exactly today's writer."""
    return (json.dumps(messages, indent=2) + "\n").encode("ascii")


def conversation_sha(messages: list) -> str:
    return hashlib.sha256(conversation_bytes(messages)).hexdigest()


def returned_lost_text(original_bytes: int, sha256: str) -> str:
    return f"this call returned {original_bytes} bytes (sha256 {sha256}), but the stored result could not be recovered"


def raised_lost_text(exception_type: str, original_bytes: int, sha256: str) -> str:
    return (
        f"this call raised {exception_type}; its stored error text ({original_bytes} bytes, "
        f"sha256 {sha256}) could not be recovered"
    )


# ---------------------------------------------------------------------------
# Messages: built only here, in one key order
# ---------------------------------------------------------------------------
def ordered_assistant(message: dict) -> dict:
    """An assistant dict in the order the chassis has always written: role, content, reasoning, calls."""
    ordered = {"role": message["role"], "content": message["content"]}
    if "reasoning_content" in message:
        ordered["reasoning_content"] = message["reasoning_content"]
    if "tool_calls" in message:
        ordered["tool_calls"] = [
            {
                "id": call["id"],
                "type": call["type"],
                "function": {"name": call["function"]["name"], "arguments": call["function"]["arguments"]},
            }
            for call in message["tool_calls"]
        ]
    extra = sorted(set(message) - set(ordered))
    if extra:
        raise ReplayMismatch(f"an assistant message with unexpected keys: {extra}")
    return ordered


def tool_message(call: dict, content: str) -> dict:
    return {"role": "tool", "tool_call_id": call["wire_id"], "name": call["name"], "content": content}


def text_message(kind: str, text: str) -> dict:
    return {"role": MESSAGE_ROLES[kind], "content": text}


def note_message(text: str) -> dict:
    return {"role": "user", "content": NOTE_PREFIX + text}


# ---------------------------------------------------------------------------
# State (v2 1.4.2), with two documented additions
# ---------------------------------------------------------------------------
@dataclass
class SessionState:
    lineage_id: str
    history_epoch: int = 1
    recap_folded: int = 0
    # The identity the next REQUEST_SENT uses; `next_turn_seq` is its turn.
    requests_next: dict = field(default_factory=lambda: {"turn_seq": 1, "attempt": 1})
    requests_last: dict | None = None
    notes_next_gen: int = 1
    notes_adopted_through: int = 0
    notes_pending: list = field(default_factory=list)
    handoff_md_sha256: str | None = None
    adopted_mirror_sha256: str | None = None  # the newest adopted generation's mirror
    notes_dropped: int = 0  # 17th-note drops not yet reported (v2 1.4.6)
    legacy: dict = field(default_factory=lambda: {"status": "none", "handoff_sha256": None})
    originals: list = field(default_factory=list)

    @property
    def next_turn_seq(self) -> int:
        return self.requests_next["turn_seq"]

    def mirror_sha256s(self) -> list[str]:
        """Mirror hashes of every pending generation and of the newest adopted one (<= 17)."""
        mirrors = [self.adopted_mirror_sha256] if self.adopted_mirror_sha256 else []
        return mirrors + [entry["mirror_sha256"] for entry in self.notes_pending]

    def blobs_live(self) -> list[str]:
        return sorted({entry["blob"] for entry in self.notes_pending} | {entry["sha256"] for entry in self.originals})

    def copy(self) -> SessionState:
        return copy.deepcopy(self)

    # -- the CHECKPOINT.state wire form ----------------------------------------
    def to_wire(self, next_seq: int) -> dict:
        return {
            "lineage_id": self.lineage_id,
            "next_seq": next_seq,
            "next_turn_seq": self.next_turn_seq,
            "history_epoch": self.history_epoch,
            "recap_folded": self.recap_folded,
            "requests": {"last": copy.deepcopy(self.requests_last), "next": dict(self.requests_next)},
            "notes": {
                "next_gen": self.notes_next_gen,
                "adopted_through": self.notes_adopted_through,
                "pending": copy.deepcopy(self.notes_pending),
                "handoff_md_sha256": self.handoff_md_sha256,
                "mirror_sha256s": self.mirror_sha256s(),
                "adopted_mirror_sha256": self.adopted_mirror_sha256,
                "dropped_pending_limit": self.notes_dropped,
            },
            "legacy": dict(self.legacy),
            "originals": copy.deepcopy(self.originals),
            "active_group": None,
            "queued": [],
            "blobs_live": self.blobs_live(),
        }

    @classmethod
    def from_wire(cls, wire) -> SessionState:
        """Validate a CHECKPOINT state and rebuild it. Any violation is StateError."""
        try:
            return cls._from_wire(wire)
        except (KeyError, TypeError, AttributeError) as error:
            raise StateError(f"checkpoint state: {type(error).__name__}: {error}") from error

    @classmethod
    def _from_wire(cls, wire) -> SessionState:
        def need(ok: bool, what: str) -> None:
            if not ok:
                raise StateError(f"checkpoint state: {what}")

        need(isinstance(wire, dict), "not an object")
        need(wire["active_group"] is None and wire["queued"] == [], "active_group/queued (CKG)")
        need(isinstance(wire["lineage_id"], str) and wire["lineage_id"], "lineage_id")
        for key in ("next_seq", "next_turn_seq", "history_epoch"):
            need(counter(wire[key], minimum=1), key)
        need(counter(wire["recap_folded"]), "recap_folded")
        requests = wire["requests"]
        nxt = requests["next"]
        need(counter(nxt["turn_seq"], minimum=1) and counter(nxt["attempt"], minimum=1), "requests.next")
        need(nxt["turn_seq"] == wire["next_turn_seq"], "next_turn_seq")
        last = requests["last"]
        if last is not None:
            need(counter(last["turn_seq"], minimum=1) and counter(last["attempt"], minimum=1), "requests.last")
            need(isinstance(last["label"], str) and last["outcome"] in REQUEST_OUTCOMES, "requests.last")
        notes = wire["notes"]
        need(counter(notes["next_gen"], minimum=1) and counter(notes["adopted_through"]), "notes counters")
        pending = notes["pending"]
        need(isinstance(pending, list) and len(pending) <= MAX_PENDING_NOTES, "notes.pending size")
        expected = notes["adopted_through"] + 1
        for entry in pending:
            need(entry["gen"] == expected, "notes.pending generations are contiguous after adopted_through")
            need(is_hex64(entry["blob"]) and is_hex64(entry["mirror_sha256"]), "notes.pending hashes")
            need(counter(entry["bytes"]) and counter(entry["written_seq"], minimum=1), "notes.pending counters")
            need(entry["source"] in NOTE_SOURCES, "notes.pending source")
            expected += 1
        need(expected == notes["next_gen"], "notes.next_gen follows the pending generations")
        for key in ("handoff_md_sha256", "adopted_mirror_sha256"):
            need(notes[key] is None or is_hex64(notes[key]), f"notes.{key}")
        need(counter(notes["dropped_pending_limit"]), "notes.dropped_pending_limit")
        legacy = wire["legacy"]
        need(legacy["status"] in LEGACY_STATUSES, "legacy.status")
        need(legacy["handoff_sha256"] is None or is_hex64(legacy["handoff_sha256"]), "legacy.handoff_sha256")
        originals = wire["originals"]
        need(isinstance(originals, list) and len(originals) <= ORIGINALS_MAX_COUNT, "originals count")
        for entry in originals:
            need(is_hex64(entry["sha256"]) and counter(entry["bytes"]) and entry["bytes"] <= ORIGINAL_MAX_ITEM, "originals entry")
            need(entry["kind"] in ("assistant_content", "args") and counter(entry["turn_seq"], minimum=1), "originals entry")
        need(sum(entry["bytes"] for entry in originals) <= ORIGINALS_MAX_BYTES, "originals bytes")
        state = cls(
            lineage_id=wire["lineage_id"],
            history_epoch=wire["history_epoch"],
            recap_folded=wire["recap_folded"],
            requests_next={"turn_seq": nxt["turn_seq"], "attempt": nxt["attempt"]},
            requests_last=copy.deepcopy(last),
            notes_next_gen=notes["next_gen"],
            notes_adopted_through=notes["adopted_through"],
            notes_pending=copy.deepcopy(pending),
            handoff_md_sha256=notes["handoff_md_sha256"],
            adopted_mirror_sha256=notes["adopted_mirror_sha256"],
            notes_dropped=notes["dropped_pending_limit"],
            legacy={"status": legacy["status"], "handoff_sha256": legacy["handoff_sha256"]},
            originals=copy.deepcopy(originals),
        )
        need(state.mirror_sha256s() == notes["mirror_sha256s"], "notes.mirror_sha256s")
        need(state.blobs_live() == wire["blobs_live"], "blobs_live")
        return state


# ---------------------------------------------------------------------------
# The open tool group (never in a checkpoint: CKG)
# ---------------------------------------------------------------------------
@dataclass
class Group:
    turn_seq: int
    calls: list
    answered: int = 0  # calls 0..answered-1 have their tool message
    invoking: set = field(default_factory=set)

    def next_call(self) -> dict | None:
        return self.calls[self.answered] if self.answered < len(self.calls) else None


def retain_originals(originals: list, added: list) -> list:
    """FIFO within ORIGINALS_MAX_COUNT and ORIGINALS_MAX_BYTES (each item already <= ORIGINAL_MAX_ITEM)."""
    kept = originals + added
    while len(kept) > ORIGINALS_MAX_COUNT or sum(entry["bytes"] for entry in kept) > ORIGINALS_MAX_BYTES:
        kept = kept[1:]
    return kept


class Replay:
    """Messages + state + open group, advanced one record at a time by `apply`."""

    def __init__(self, messages: list, state: SessionState, read_blob, *, lenient: bool = False) -> None:
        self.messages = messages
        self.state = state
        self.group: Group | None = None
        self.read_blob = read_blob  # sha -> bytes | None
        # Lenient: the base list is unknown (it is about to be replaced by an
        # external edit, deletion or reimport), so checks against its length
        # are skipped; the state and group are still exact.
        self.lenient = lenient

    # -- helpers -------------------------------------------------------------
    def _blob(self, sha: str, what: str) -> bytes:
        data = self.read_blob(sha)
        if data is None:
            raise ReplayMismatch(f"the blob for {what} ({sha}) is missing or damaged")
        return data

    def _blob_list(self, sha: str, what: str, count=None) -> list:
        data = self._blob(sha, what)
        try:
            messages = json.loads(data.decode("ascii"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ReplayMismatch(f"the blob for {what} is not a conversation") from error
        if not isinstance(messages, list) or conversation_bytes(messages) != data:
            raise ReplayMismatch(f"the blob for {what} is not a conversation in the fixed serialization")
        if count is not None and len(messages) != count:
            raise ReplayMismatch(f"the blob for {what} has {len(messages)} messages, not {count}")
        return messages

    def _text(self, payload: dict, what: str) -> str:
        if "text" in payload:
            return payload["text"]
        return self._blob(payload["blob"], what).decode("utf-8")

    def _require_boundary(self, name: str) -> None:
        if self.group is not None:
            raise ReplayMismatch(f"{name} inside the open tool group of turn {self.group.turn_seq}")

    def _epoch(self, payload: dict, *, step: int) -> None:
        if payload["epoch"] != self.state.history_epoch + step:
            raise ReplayMismatch(f"epoch {payload['epoch']} does not follow {self.state.history_epoch}")
        if step:
            self.state.history_epoch = payload["epoch"]

    def _answer(self, call_index: int, message: dict) -> None:
        group = self.group
        if group is None or group.next_call() is None or group.next_call()["call_index"] != call_index:
            raise ReplayMismatch(f"call {call_index} answered out of order")
        self.messages.append(message)
        group.answered += 1
        self._answer_not_invoked()

    def _answer_not_invoked(self) -> None:
        """A call with admit != invoke is answered by its admission text when its turn comes."""
        group = self.group
        while group.next_call() is not None and group.next_call()["admit"] != "invoke":
            call = group.next_call()
            self.messages.append(tool_message(call, call["admit_text"]))
            group.answered += 1
        if group.next_call() is None:
            self.group = None

    def _call_in_group(self, call_key) -> int:
        if self.group is None or not isinstance(call_key, list) or call_key[0] != self.group.turn_seq:
            raise ReplayMismatch(f"call {call_key!r} is not in the open group")
        return call_key[1]

    # -- the reducer -----------------------------------------------------------
    def apply(self, record) -> None:
        name, payload = record.type_name, record.payload
        handler = getattr(self, f"_on_{name.lower()}", None)
        if handler is not None:
            handler(record, payload)

    def _on_request_sent(self, record, payload) -> None:
        self._require_boundary("REQUEST_SENT")
        identity = {"turn_seq": payload["turn_seq"], "attempt": payload["attempt"]}
        if identity != self.state.requests_next:
            raise ReplayMismatch(f"request {identity} is not the next identity {self.state.requests_next}")
        self.state.requests_last = {**identity, "label": payload["label"], "outcome": "failed_unknown"}
        # Until its response is recorded, the next attempt at this turn is attempt+1.
        self.state.requests_next = {"turn_seq": identity["turn_seq"], "attempt": identity["attempt"] + 1}

    def _responded(self, payload, outcome: str) -> None:
        last = self.state.requests_last
        if last is None or last["outcome"] != "failed_unknown" or last["turn_seq"] != payload["turn_seq"]:
            raise ReplayMismatch(f"a response for turn {payload['turn_seq']} without its request")
        last["outcome"] = outcome
        self.state.requests_next = {"turn_seq": payload["turn_seq"] + 1, "attempt": 1}

    def _on_turn_response(self, record, payload) -> None:
        self._responded(payload, "responded")
        self.messages.append(ordered_assistant(payload["assistant"]))
        added = [
            {"sha256": item["sha256"], "bytes": item["bytes"], "kind": item["kind"], "turn_seq": payload["turn_seq"]}
            for item in payload.get("originals", [])
        ]
        self.state.originals = retain_originals(self.state.originals, added)
        calls = payload["calls"]
        if calls:
            self.group = Group(payload["turn_seq"], copy.deepcopy(calls))
            self._answer_not_invoked()

    def _on_response_refused(self, record, payload) -> None:
        self._responded(payload, "refused")

    def _on_invoking(self, record, payload) -> None:
        group = self.group
        call = group.next_call() if group is not None and group.turn_seq == payload["turn_seq"] else None
        if call is None or call["call_index"] != payload["call_index"] or call["admit"] != "invoke":
            raise ReplayMismatch(f"INVOKING {payload['turn_seq']}/{payload['call_index']} is not the frontier call")
        group.invoking.add(payload["call_index"])

    def _on_done(self, record, payload) -> None:
        group = self.group
        if group is None or group.turn_seq != payload["turn_seq"] or payload["call_index"] not in group.invoking:
            raise ReplayMismatch(f"DONE {payload['turn_seq']}/{payload['call_index']} without its INVOKING")
        data = self.read_blob(payload["blob"])
        if data is not None:
            text = data.decode("utf-8", "replace")
        elif payload["outcome"] == "returned":
            text = returned_lost_text(payload["original_bytes"], payload["blob"])
        else:
            text = raised_lost_text(payload["outcome"].split(":", 1)[1], payload["original_bytes"], payload["blob"])
        self._answer(payload["call_index"], tool_message(group.next_call(), text))

    def _on_unrun(self, record, payload) -> None:
        index = self._call_in_group(payload["call_key"])
        self._answer(index, tool_message(self.group.next_call() or {"wire_id": None, "name": None}, payload["reason"]))

    def _on_synth(self, record, payload) -> None:
        index = self._call_in_group(payload["call_key"])
        kind = payload["kind"]
        if kind not in SYNTH_TEXTS:
            raise ReplayMismatch(f"SYNTH kind {kind!r}")
        self._answer(index, tool_message(self.group.next_call() or {"wire_id": None, "name": None}, SYNTH_TEXTS[kind]))

    def _on_termination(self, record, payload) -> None:
        if payload["call_key"] != "direct":
            self._call_in_group(payload["call_key"])

    def _on_msg_append(self, record, payload) -> None:
        self._require_boundary("MSG_APPEND")
        self._epoch(payload, step=0)
        kind = payload["kind"]
        if kind not in MESSAGE_ROLES:
            raise ReplayMismatch(f"MSG_APPEND kind {kind!r}")
        if kind != "note":
            self.messages.append(text_message(kind, self._text(payload, "a message")))
            if payload.get("reports") == "note_dropped_pending_limit":
                # The notice and the end of the drop count are one record.
                self.state.notes_dropped = 0
            return
        notes = self.state
        gen = payload["gen"]
        if gen != notes.notes_adopted_through + 1 or not notes.notes_pending or notes.notes_pending[0]["gen"] != gen:
            raise ReplayMismatch(f"note {gen} is not the next pending generation")
        entry = notes.notes_pending.pop(0)
        if payload.get("blob") != entry["blob"]:
            raise ReplayMismatch(f"note {gen}'s MSG_APPEND names another blob")
        if not payload.get("foreign"):
            self.messages.append(note_message(self._blob(entry["blob"], f"note {gen}").decode("utf-8")))
        notes.notes_adopted_through = gen
        notes.adopted_mirror_sha256 = entry["mirror_sha256"]

    def _on_note_written(self, record, payload) -> None:
        notes = self.state
        if payload["gen"] != notes.notes_next_gen:
            raise ReplayMismatch(f"note generation {payload['gen']} where {notes.notes_next_gen} was due")
        if len(notes.notes_pending) >= MAX_PENDING_NOTES:
            raise ReplayMismatch("a note past MAX_PENDING_NOTES")
        if payload["source"] not in NOTE_SOURCES:
            raise ReplayMismatch(f"note source {payload['source']!r}")
        notes.notes_pending.append(
            {
                "gen": payload["gen"],
                "blob": payload["blob"],
                "bytes": payload["bytes"],
                "source": payload["source"],
                "written_seq": record.seq,
                "mirror_sha256": payload["mirror_sha256"],
            }
        )
        notes.notes_next_gen = payload["gen"] + 1
        notes.handoff_md_sha256 = payload["mirror_sha256"]

    def _on_history_replaced(self, record, payload) -> None:
        self._require_boundary("HISTORY_REPLACED")
        messages = self._blob_list(payload["new_blob"], "the replaced history", payload["new_count"])
        if hashlib.sha256(conversation_bytes(messages)).hexdigest() != payload["new_sha256"]:
            raise ReplayMismatch("HISTORY_REPLACED's hash does not match its blob")
        self._epoch(payload, step=1)
        self.messages[:] = messages
        self.state.recap_folded = min(self.state.recap_folded, len(messages))

    def _switch_base(self, payload, name: str) -> None:
        self._require_boundary(name)
        messages = self._blob_list(payload["blob"], name) if payload.get("blob") else []
        self.messages[:] = messages
        folded = payload.get("recap_folded", 0)
        if not counter(folded) or folded > len(messages):
            raise ReplayMismatch(f"{name}'s recap_folded is outside the list")
        self.state.recap_folded = folded

    def _on_external_edit(self, record, payload) -> None:
        self._epoch(payload, step=1)
        self._switch_base(payload, "EXTERNAL_EDIT")
        self._append_carried_notices(payload)

    def _on_external_delete(self, record, payload) -> None:
        self._epoch(payload, step=1)
        self._switch_base({}, "EXTERNAL_DELETE")
        self._append_carried_notices(payload)

    def _on_legacy_import(self, record, payload) -> None:
        self._switch_base(payload, "LEGACY_IMPORT")
        legacy = payload.get("legacy")
        if legacy is not None:
            if legacy.get("status") not in LEGACY_STATUSES:
                raise ReplayMismatch("LEGACY_IMPORT's legacy status")
            self.state.legacy = {"status": legacy["status"], "handoff_sha256": legacy.get("handoff_sha256")}
            if legacy.get("handoff_sha256") is not None:
                # The legacy HANDOFF.md has been processed (matched, or adopted
                # by the NOTE_WRITTEN{legacy} that follows): never a file edit.
                self.state.handoff_md_sha256 = legacy["handoff_sha256"]

    def _on_legacy_reimport(self, record, payload) -> None:
        self._epoch(payload, step=1)
        self._switch_base(payload, "LEGACY_REIMPORT")
        legacy = payload.get("legacy")
        if legacy is not None:
            if legacy.get("status") not in LEGACY_STATUSES:
                raise ReplayMismatch("LEGACY_REIMPORT's legacy status")
            self.state.legacy = {"status": legacy["status"], "handoff_sha256": legacy.get("handoff_sha256")}
        self._append_carried_notices(payload)

    def _append_carried_notices(self, payload) -> None:
        """Recovery notices carried by a base switch, appended after the new base.

        A switch replaces the list, so a notice appended before it would be
        lost; carrying them in the switch record keeps switch and notices one
        durable step (SV021).
        """
        for text in payload.get("notices", []):
            if not isinstance(text, str):
                raise ReplayMismatch("a carried notice is not text")
            self.messages.append(text_message("notice", text))

    def _on_recap_fold(self, record, payload) -> None:
        self._require_boundary("RECAP_FOLD")
        within = self.lenient or payload["to"] <= len(self.messages)
        if payload["from"] != self.state.recap_folded or not payload["from"] < payload["to"] or not within:
            raise ReplayMismatch(f"RECAP_FOLD {payload['from']}->{payload['to']} does not continue {self.state.recap_folded}")
        self.state.recap_folded = payload["to"]

    def _on_recovery(self, record, payload) -> None:
        kind, detail = payload["kind"], payload["detail"]
        if kind == "possible_duplicate_spend":
            last = self.state.requests_last
            if last is not None and last["outcome"] == "failed_unknown":
                last["outcome"] = "possible_duplicate_spend"
            nxt = detail.get("next") if isinstance(detail, dict) else None
            if nxt is not None:
                if not (counter(nxt.get("turn_seq"), minimum=1) and counter(nxt.get("attempt"), minimum=1)):
                    raise ReplayMismatch("possible_duplicate_spend names an invalid next request")
                self.state.requests_next = {"turn_seq": nxt["turn_seq"], "attempt": nxt["attempt"]}
        elif kind == "note_dropped_pending_limit":
            # SV021 addition: v2 1.4.6 names the drop but no record; without
            # one, a drop after the newest checkpoint would vanish on replay.
            self.state.notes_dropped += 1

    def _on_original_evicted(self, record, payload) -> None:
        if any(entry["sha256"] == payload["sha"] for entry in self.state.originals):
            raise ReplayMismatch("ORIGINAL_EVICTED names an original that is still retained")


def checkpoint_records(records) -> list:
    return [record for record in records if record.type_name == "CHECKPOINT"]


# ---------------------------------------------------------------------------
# The reference graph (v2 1.4.5): what a later GC must keep
# ---------------------------------------------------------------------------
def record_refs(record) -> set[str]:
    """Every blob a record names (and replay may read)."""
    payload, name = record.payload, record.type_name
    refs: set[str] = set()
    if name == "DONE" or name == "NOTE_WRITTEN":
        refs.add(payload["blob"])
    elif name == "MSG_APPEND" and "blob" in payload:
        refs.add(payload["blob"])
    elif name == "HISTORY_REPLACED":
        refs.add(payload["new_blob"])
    elif name in ("EXTERNAL_EDIT", "LEGACY_IMPORT", "LEGACY_REIMPORT") and payload.get("blob"):
        refs.add(payload["blob"])
    elif name == "TURN_RESPONSE":
        refs.update(payload["original_blobs"])
    elif name == "CHECKPOINT":
        refs.update(payload["state"]["blobs_live"])
    return refs


def retained_refs(records) -> set[str]:
    """refs(C_n.state) | refs(C_p.state) | refs(records after C_p.covers_seq).

    GC is disabled in this runtime; this is the graph a later GC must keep,
    computed so its completeness can be tested now.
    """
    checkpoints = checkpoint_records(records)
    if not checkpoints:
        return set().union(*(record_refs(r) for r in records)) if records else set()
    newest = checkpoints[-1]
    prev = newest.payload["prev"]
    floor = prev["covers_seq"] if prev else 0
    refs = set(newest.payload["state"]["blobs_live"])
    older = next((r for r in records if prev and r.seq == prev["checkpoint_seq"]), None)
    if older is not None:
        refs |= set(older.payload["state"]["blobs_live"])
    for record in records:
        if record.seq > floor:
            refs |= record_refs(record)
    return refs
