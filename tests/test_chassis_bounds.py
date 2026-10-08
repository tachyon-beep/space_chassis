"""SV025: replay work against SV-015 v2 1.4.7's exact bounds, by an independent observer (test-only).

Nothing here changes the runtime, its limits or the canonical oracle. The
canonical values are copied from `SV-015-literal-values-v2.json`
(`ledger_frame_max_bytes`, `recovery_bound_defaults`). The maximal shapes are
rebuilt from the text of its generator (lines 90-117), which was read but never
run. They are synthetic: the arithmetic of the generator's source payloads, not
runtime states.

Three evidence levels for a record size, never substituted for one another
(SV025-01). A *synthetic* shape is accepted by the encoder only, which checks
the payload schema and nothing else. A *legal-domain model* additionally
satisfies the source domains the runtime enforces or emits; a CHECKPOINT state
must validate and round-trip through `SessionState.to_wire`/`from_wire`. It is
legal, but it was not driven to through a real history. An *emitted* record
was written by the actual session code in a temporary root and is measured on
disk.

Three quantities, never substituted for one another:

* **Logical interval work**: for the records of one replay interval, their
  frame bytes plus the bytes of each blob replay opened while applying them,
  one count per (record, blob). This is the quantity v2 1.4.7 bounds.
* **Distinct blob bytes**: the same blobs, counted once by name.
* **Read calls**: every successful, returned `DurableOps.read` a start made
  (segments, blobs, the conversation files, markers), duplicates included.
  Failed or missing-file attempts are not logged. This is not a suffix
  quantity.

The observer does not depend on the writer. Frame lengths come from a byte walk
of the segment files (`49 + plen + 66` from each header). Blob bytes come from
the reads the runtime actually made while `Replay.apply` ran for a given seq.
`since_bytes` is only compared against these numbers, never used as their
oracle.

The external-edit and older-prev tests pass by asserting that a canonical
premise is contradicted. A pass there is a counterexample, not a guarantee
(docs/planning-context/sv025/RECEIPT.md). SV026 fixed restart accounting, so
the restart test now asserts the repaired behavior, and the external-edit
witness is taken in the real crash window before the startup threshold
checkpoint (docs/planning-context/sv026/).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import chassis
import chassis_envelope as envelope
import chassis_persistence as cp
import chassis_replay as rp
import chassis_session as cs
import chassis_startup as st
import pytest
from test_chassis_durability import Crash
from test_chassis_recovery_live import Root, establish, respond

# SV-015-literal-values-v2.json, copied; neither it nor its generator is edited or run.
CANON_FRAMES = {
    "TURN_RESPONSE": 680_003, "REQUEST_SENT": 208, "INVOKING": 156, "DONE": 415, "UNRUN": 254, "SYNTH": 175,
    "TERMINATION": 186, "MSG_APPEND_blob": 227, "MSG_APPEND_inline_4KiB": 4_259, "NOTE_WRITTEN": 410,
    "ORIGINAL_EVICTED": 192, "RECOVERY": 206, "HISTORY_REPLACED": 320, "CHECKPOINT": 19_978,
}
NEWEST_RECORDS_MAX, NEWEST_BYTES_LT = 358, 25_166_144
PREV_RECORDS_MAX, PREV_BYTES_LT = 717, 50_352_266

BIG = 10**12 - 1
K = 1024
W, N, Z = "w" * 64, "n" * 64, "0" * 64
LINEAGE16 = "f" * 16  # chassis.run's new lineage is uuid4().hex[:16]; the generator used 8 characters


# ---------------------------------------------------------------------------
# Shapes: the generator's maximal payloads through the runtime's own encoder
# ---------------------------------------------------------------------------
def label(lineage: str) -> str:
    return cp.request_label(lineage, BIG, BIG)


def frame(type_name: str, payload: dict) -> int:
    return len(cp.encode_frame(BIG, type_name, payload, Z)[0])


def generator_shapes(lineage: str = "f" * 8) -> dict:
    """The generator's maximal payloads (its lines 90-117), keyed by its literal names: (type, payload)."""
    elided = json.dumps({"_runtime_elided": {"bytes": BIG, "sha256": Z}}, separators=(",", ":"))
    assistant = {
        "role": "assistant", "content": "a" * (64 * K), "reasoning_content": "b" * (64 * K),
        "tool_calls": [{"id": W, "type": "function", "function": {"name": N, "arguments": "x" * (32 * K)}} for _ in range(16)]
        + [{"id": W, "type": "function", "function": {"name": N, "arguments": elided}} for _ in range(16)],
    }
    calls = [
        {"call_index": i, "provider_id_repr": {"type": "str", "E": BIG, "sha256": Z}, "wire_id": W, "name": N,
         "args_sha256": Z, "args_E": BIG, "admit": "not_run_call_limit"}
        for i in range(32)
    ]
    state = {
        "lineage_id": lineage, "next_seq": BIG, "next_turn_seq": BIG, "history_epoch": BIG, "recap_folded": BIG,
        "requests": {"last": {"turn_seq": BIG, "attempt": BIG, "label": label(lineage), "outcome": "possible_duplicate_spend"}},
        "notes": {
            "next_gen": BIG, "adopted_through": BIG,
            "pending": [{"gen": BIG, "blob": Z, "bytes": BIG, "source": "file_edit", "written_seq": BIG}] * 16,
            "handoff_md_sha256": Z, "mirror_sha256s": [Z] * 17,
        },
        "legacy": {"status": "legacy_unadopted_unproven", "handoff_sha256": Z},
        "originals": [{"sha256": Z, "bytes": BIG, "kind": "assistant_content", "turn_seq": BIG}] * 64,
        "active_group": None, "queued": [], "blobs_live": [Z] * (16 + 64),
    }
    return {
        "TURN_RESPONSE": ("TURN_RESPONSE", {
            "turn_seq": BIG, "assistant": assistant, "calls": calls, "omitted": {"count": 224, "sha256": Z},
            "normalization": {
                "replaced_chars": BIG,
                "truncated_fields": ["content", "reasoning_content"] + [f"tool_calls[{i}].function.arguments" for i in range(32)],
            },
            "original_blobs": [Z] * 17,
        }),
        "REQUEST_SENT": ("REQUEST_SENT", {"turn_seq": BIG, "attempt": BIG, "label": label(lineage)}),
        "INVOKING": ("INVOKING", {"turn_seq": BIG, "call_index": 31}),
        "DONE": ("DONE", {
            "turn_seq": BIG, "call_index": 31, "outcome": "raised:" + "T" * 64, "blob": Z,
            "original_bytes": BIG, "stored_E": BIG, "truncated": True, "replaced_chars": BIG,
        }),
        "UNRUN": ("UNRUN", {"call_key": [BIG, 31], "reason": "the run ended by handoff in call " + W}),
        "SYNTH": ("SYNTH", {"call_key": [BIG, 31], "kind": "unknown_damaged_tail"}),
        "TERMINATION": ("TERMINATION", {"call_key": [BIG, 31], "kind": "handoff", "note_gen": BIG}),
        "MSG_APPEND_blob": ("MSG_APPEND", {"kind": "notice", "blob": Z, "epoch": BIG}),
        "MSG_APPEND_inline_4KiB": ("MSG_APPEND", {"kind": "notice", "text": "t" * 4096, "epoch": BIG}),
        "NOTE_WRITTEN": ("NOTE_WRITTEN", {
            "gen": BIG, "blob": Z, "bytes": BIG, "sha256": Z, "source": "file_edit", "mirror_sha256": Z,
        }),
        "ORIGINAL_EVICTED": ("ORIGINAL_EVICTED", {"sha256": Z}),
        "RECOVERY": ("RECOVERY", {"kind": "possible_duplicate_spend", "detail": {"label": label(lineage)}}),
        "HISTORY_REPLACED": ("HISTORY_REPLACED", {"epoch": BIG, "new_blob": Z, "new_count": BIG, "new_sha256": Z}),
        "CHECKPOINT": ("CHECKPOINT", {
            "covers_seq": BIG, "chain_at_cover": Z, "conv": {"sha256": Z, "bytes": BIG},
            "prev": {"covers_seq": BIG, "conv_sha256": Z, "conv_bytes": BIG, "checkpoint_seq": BIG},
            "run_sha256": Z, "state": state,
        }),
    }


def test_sv025_canonical_maximal_shapes_reproduce_through_the_runtime_encoder():
    """`49 + plen + 66` with the runtime's canonical body is the generator's arithmetic, shape for shape."""
    shapes = generator_shapes()
    original = shapes.pop("ORIGINAL_EVICTED")
    assert {name: frame(*shape) for name, shape in shapes.items()} == {
        name: size for name, size in CANON_FRAMES.items() if name != "ORIGINAL_EVICTED"
    }
    # The generator's ORIGINAL_EVICTED names its key `sha256`; the runtime writes `{"sha": ...}`.
    with pytest.raises(cp.LedgerError, match="missing keys: sha"):
        frame(*original)
    assert frame("ORIGINAL_EVICTED", {"sha": Z}) == 189 < CANON_FRAMES["ORIGINAL_EVICTED"]


def h(text: str) -> str:
    """A distinct 64-hex name per label (live sets are sets: equal names would collapse)."""
    return hashlib.sha256(text.encode()).hexdigest()


# -- legal-domain models: counters within the 12-digit domain the runtime accepts, every other field as emitted --
def _request_sent():
    payloads = [("REQUEST_SENT", {"turn_seq": BIG, "attempt": BIG, "label": cp.request_label(lineage, BIG, BIG)}) for lineage in (LINEAGE16, "l" * 64)]
    # LINEAGE16 has the length of chassis.run's new lineage, uuid4().hex[:16] (chassis.py:1146).
    assert st.LINEAGE_ID.fullmatch("l" * 64), "a legacy run.json lineage of 64 characters is accepted (chassis_startup.py:86)"
    return payloads


def _recovery_spend():
    # derive_core: a request with no response is a possible spend; `next` is requests_next, its attempt + 1.
    detail = {"label": cp.request_label(LINEAGE16, BIG, BIG - 1), "next": {"turn_seq": BIG, "attempt": BIG}}
    assert rp.counter(detail["next"]["attempt"], minimum=1) and detail["next"]["attempt"] == (BIG - 1) + 1
    return [("RECOVERY", {"kind": "possible_duplicate_spend", "detail": detail})]


def _unrun_ended():
    # end_group: a later call is invokable, so its index is below CAP_CALLS (16 by default); its wire id <= 64.
    index = envelope.DEFAULT_CAPS.calls - 1
    assert envelope.WIRE_ID.fullmatch(W)
    return [("UNRUN", {"call_key": [BIG, index], "reason": f"not run: the run ended by handoff in call {W}"})]


def _note_adoption():
    # adopt_notes: one non-foreign generation, whose blob replay opens (chassis_session.py:495).
    return [("MSG_APPEND", {"kind": "note", "gen": BIG, "blob": h("note"), "epoch": BIG})]


LEGAL_MODELS = [
    # (id, canonical literal, legal-domain payloads, their exact frame sizes)
    ("request-sent-lineage16", "REQUEST_SENT", _request_sent, [216, 264]),
    ("recovery-spend-next", "RECOVERY", _recovery_spend, [270]),
    ("unrun-ended-reason", "UNRUN", _unrun_ended, [263]),
    ("note-adoption-gen", "MSG_APPEND_blob", _note_adoption, [244]),
]


@pytest.mark.parametrize(("canonical", "payloads", "expected"), [c[1:] for c in LEGAL_MODELS], ids=[c[0] for c in LEGAL_MODELS])
def test_sv025_legal_domain_models_exceed_the_canonical_maxima(canonical, payloads, expected):
    """Legal-domain payloads (not driven through a real history) whose frames exceed the literal maximum."""
    sizes = [frame(type_name, payload) for type_name, payload in payloads()]
    assert sizes == expected
    assert min(sizes) > CANON_FRAMES[canonical], "the canonical maximal shape does not dominate this legal payload"


# -- CHECKPOINT: a valid bounded state through the runtime's own serializer --
NOTE_BYTES = 64 * K  # a file_edit generation is truncate_marked to NOTE_MAX_E escaped units, so <= 65,536 UTF-8 bytes
ORIGINAL_BYTES = rp.ORIGINALS_MAX_BYTES // rp.ORIGINALS_MAX_COUNT  # 64 x 65,536 = the 4 MiB aggregate exactly


def valid_checkpoint() -> tuple[dict, int]:
    """(CHECKPOINT payload, its seq): a legal-domain model whose state is built as `SessionState` and serialized by `to_wire`."""
    covers = BIG - 2  # the record is seq covers + 1, and state.next_seq = covers + 2 <= MAX_COUNTER (chassis_session.py:589, :615)
    adopted = BIG - 17
    # The fold point is at most the message count of a list the 64 MiB reader can read back.
    per_message = len(rp.conversation_bytes([{"role": ""}] * 2)) - len(rp.conversation_bytes([{"role": ""}]))
    pending = [
        {"gen": adopted + 1 + i, "blob": h(f"note {i}"), "bytes": NOTE_BYTES, "source": "file_edit",
         "written_seq": covers - 100 + i, "mirror_sha256": h(f"mirror {i}"), "foreign": True}
        for i in range(rp.MAX_PENDING_NOTES)
    ]
    originals = [
        {"sha256": h(f"original {i}"), "bytes": ORIGINAL_BYTES, "kind": "assistant_content", "turn_seq": BIG - 64 + i}
        for i in range(rp.ORIGINALS_MAX_COUNT)
    ]
    state = rp.SessionState(
        lineage_id=LINEAGE16, history_epoch=BIG - 1, recap_folded=st.CONVERSATION_READ_MAX // per_message,
        requests_next={"turn_seq": BIG, "attempt": BIG},
        requests_last={"turn_seq": BIG, "attempt": BIG - 1, "label": cp.request_label(LINEAGE16, BIG, BIG - 1), "outcome": "possible_duplicate_spend"},
        notes_next_gen=adopted + 1 + len(pending), notes_adopted_through=adopted, notes_pending=pending,
        handoff_md_sha256=pending[-1]["mirror_sha256"], adopted_mirror_sha256=h("adopted mirror"), notes_dropped=BIG,
        legacy={"status": "legacy_unadopted_unproven", "handoff_sha256": h("legacy")}, originals=originals,
    )
    payload = {
        "covers_seq": covers, "chain_at_cover": h("chain"),
        "conv": {"sha256": h("conv"), "bytes": st.CONVERSATION_READ_MAX},
        "prev": {"covers_seq": covers - 300, "conv_sha256": h("prev conv"), "conv_bytes": st.CONVERSATION_READ_MAX, "checkpoint_seq": covers - 299},
        "run_sha256": h("run"), "state": state.to_wire(next_seq=covers + 2),
    }
    return payload, covers + 1


def test_sv025_a_valid_current_checkpoint_state_round_trips_and_exceeds_the_literal():
    """Legal-domain model: validates and round-trips through the actual serializer, then is measured."""
    payload, seq = valid_checkpoint()
    wire = payload["state"]
    assert rp.SessionState.from_wire(wire).to_wire(next_seq=wire["next_seq"]) == wire, "validates and round-trips"
    notes = wire["notes"]
    assert [entry["gen"] for entry in notes["pending"]] == list(range(notes["adopted_through"] + 1, notes["next_gen"]))
    assert len(notes["pending"]) == rp.MAX_PENDING_NOTES and all(entry["bytes"] <= NOTE_BYTES for entry in notes["pending"])
    sizes = [entry["bytes"] for entry in wire["originals"]]
    assert len(sizes) == rp.ORIGINALS_MAX_COUNT and max(sizes) <= rp.ORIGINAL_MAX_ITEM and sum(sizes) == rp.ORIGINALS_MAX_BYTES
    assert wire["blobs_live"] == sorted(set(wire["blobs_live"])) and len(wire["blobs_live"]) == rp.MAX_PENDING_NOTES + rp.ORIGINALS_MAX_COUNT
    assert len(notes["mirror_sha256s"]) == rp.MAX_PENDING_NOTES + 1
    prev = payload["prev"]
    assert prev["covers_seq"] < prev["checkpoint_seq"] <= payload["covers_seq"] < seq == payload["covers_seq"] + 1
    assert wire["next_seq"] == seq + 1 <= rp.MAX_COUNTER and all(entry["written_seq"] <= payload["covers_seq"] for entry in notes["pending"])
    assert frame_at(seq, payload) == 21_173 > CANON_FRAMES["CHECKPOINT"]


def frame_at(seq: int, payload: dict) -> int:
    return len(cp.encode_frame(seq, "CHECKPOINT", payload, Z)[0])


def _generator_model(payload):
    # The SV025 first-round model: the generator's synthetic state plus the current keys.
    state = generator_shapes(LINEAGE16)["CHECKPOINT"][1]["state"]
    state["requests"]["next"] = {"turn_seq": BIG, "attempt": BIG}
    state["notes"]["pending"] = [{**entry, "mirror_sha256": Z, "foreign": True} for entry in state["notes"]["pending"]]
    state["notes"]["adopted_mirror_sha256"], state["notes"]["dropped_pending_limit"] = Z, BIG
    payload["state"] = state


def _noncontiguous_generation(payload):
    pending = payload["state"]["notes"]["pending"]
    pending[0]["gen"], pending[1]["gen"] = pending[1]["gen"], pending[0]["gen"]


def _repeated_live_set(payload):
    live = payload["state"]["blobs_live"]
    payload["state"]["blobs_live"] = [live[0]] * len(live)


def _oversize_original(payload):
    payload["state"]["originals"][0]["bytes"] = rp.ORIGINAL_MAX_ITEM + 1


INVALID_STATES = [
    ("generator-model", _generator_model),
    ("noncontiguous-generation", _noncontiguous_generation),
    ("repeated-live-set", _repeated_live_set),
    ("oversize-original", _oversize_original),
]


@pytest.mark.parametrize("corrupt", [c[1] for c in INVALID_STATES], ids=[c[0] for c in INVALID_STATES])
def test_sv025_encoder_acceptance_alone_does_not_validate_a_checkpoint_state(corrupt):
    """Each is encoded without complaint, yet is not a state the runtime can hold: shape validation is insufficient."""
    payload, seq = valid_checkpoint()
    corrupt(payload)
    assert frame_at(seq, payload) > 0, "the encoder's schema check accepts it"
    with pytest.raises(rp.StateError):
        rp.SessionState.from_wire(payload["state"])


# -- emitted records: written by the actual session code, measured on disk --
def test_sv025_emitted_records_exceed_the_canonical_maxima(tmp_path):
    """An inline control-character message and a DONE for an exception with a 1,000-character class name, as written."""
    root = Root(tmp_path)
    session = establish(root)
    session.append_message("user", "\x01" * cs.INLINE_TEXT_BYTES)  # 4,096 UTF-8 bytes: inline, each escaped as \u0001

    error_type = type("T" * 1000, (Exception,), {})

    def boom():
        raise error_type("boom")

    # chassis.Chassis.invoke_outcome itself turns the exception into (outcome, text); _run_group's order follows.
    tools = SimpleNamespace(tools=SimpleNamespace(tools={"boom": boom}), operation=lambda *_args, **_fields: None)
    (call,) = respond(session, calls=[("call_0", "boom", "{}")]).calls
    outcome, text = session.invoke(call, lambda: chassis.Chassis.invoke_outcome(tools, call.name, call.invoke_arguments))
    session.record_result(call, outcome, text)
    session.close()

    walked = frames(root)
    records = {record.seq: record for record in root.records()}
    inline = next(r for r in records.values() if r.type_name == "MSG_APPEND" and r.payload.get("text", "").startswith("\x01"))
    assert "blob" not in inline.payload and inline.payload["text"] == "\x01" * cs.INLINE_TEXT_BYTES
    assert walked[inline.seq][1] == 24_726 > CANON_FRAMES["MSG_APPEND_inline_4KiB"]
    done = next(r for r in records.values() if r.type_name == "DONE")
    assert done.payload["outcome"] == "raised:" + "T" * 1000
    assert done.payload["stored_E"] == done.payload["original_bytes"] == len(f"error: {'T' * 1000}: boom") <= envelope.DEFAULT_CAPS.result
    assert walked[done.seq][1] == 1_313 > CANON_FRAMES["DONE"]


# -- the default admission split behind the originals count (SV025-02) --
def test_sv025_default_caps_admit_at_most_18_new_originals_per_response():
    """Calls 0-15 can each offer one original; calls 16-31 are not_run_call_limit first; content and reasoning only if truncated."""
    caps = envelope.DEFAULT_CAPS
    # 32 distinct malformed JSON strings of 603 bytes: over INVALID_ARGS_KEEP_BYTES, under CAP_ARGS.
    calls = tuple(envelope.RawCall(f"call_{i}", "tool", "{" + f"{i:02d}" + "x" * 600) for i in range(caps.calls_stored))
    truncated = envelope.adopt_response(envelope.RawResponse("c" * (caps.content + 1), "r" * (caps.reasoning + 1), calls), 7)
    whole = envelope.adopt_response(envelope.RawResponse("c" * caps.content, "r" * caps.reasoning, calls), 7)
    assert [call.admit for call in truncated.calls] == ["bad_args"] * caps.calls + ["not_run_call_limit"] * (caps.calls_stored - caps.calls)
    arguments = [f"tool_calls[{i}].function.arguments" for i in range(caps.calls)]
    assert [original.field for original in truncated.originals] == ["content", "reasoning_content", *arguments]
    assert [original.field for original in whole.originals] == arguments, "a field at its cap is not truncated and offers no original"
    assert len({original.data for original in truncated.originals}) == len(truncated.originals) == 18
    assert all(len(original.data) <= rp.ORIGINAL_MAX_ITEM for original in truncated.originals), "Session.adopt would retain all 18"


# ---------------------------------------------------------------------------
# The observer
# ---------------------------------------------------------------------------
class Observer(cp.DurableOps):
    """The real filesystem helper, plus a log of every returned read. Keeps no data.

    `reads`: (kind, name, bytes, the seq being replayed or None).
    `applies`: the seq of every `Replay.apply`, in order (set by the `watch` fixture).
    """

    def __init__(self) -> None:
        self.reads: list[tuple[str, str, int, int | None]] = []
        self.applies: list[int] = []
        self.applying: int | None = None

    def read(self, path, limit):
        data = super().read(path, limit)
        p = Path(path)
        if p.suffix == ".svl":
            kind = "segment"
        elif p.parent.name == "blobs":
            kind = "blob"
        elif p.name in ("conversation.json", "conversation.prev.json"):
            kind = "conversation"
        else:
            kind = "other"
        self.reads.append((kind, p.name, len(data), self.applying))
        return data

    def of(self, kind: str) -> list:
        return [read for read in self.reads if read[0] == kind]


@pytest.fixture
def watch(monkeypatch):
    """A new Observer per call. Every Replay.apply, startup's or the live session's, is attributed to the newest one."""
    current: dict = {}
    original = rp.Replay.apply

    def apply(replay, record):
        observer = current.get("observer")
        if observer is None:
            return original(replay, record)
        observer.applies.append(record.seq)
        observer.applying = record.seq
        try:
            return original(replay, record)
        finally:
            observer.applying = None

    monkeypatch.setattr(rp.Replay, "apply", apply)

    def new() -> Observer:
        current["observer"] = Observer()
        return current["observer"]

    return new


def frames(root: Root) -> dict[int, tuple[str, int]]:
    """seq -> (type hex, frame length), from the segment bytes alone: `49 + plen + 66` per header."""
    walked = {}
    for path in sorted((root.session_dir / "ledger").glob("*.svl")):
        data = path.read_bytes()
        offset = 0
        while offset < len(data):
            header = data[offset : offset + cp.HEADER_BYTES]
            seq, type_hex, plen = int(header[5:17]), header[18:20].decode("ascii"), int(header[21:31])
            walked[seq] = (type_hex, cp.HEADER_BYTES + plen + cp.TRAILER_BYTES)
            offset += walked[seq][1]
        assert offset == len(data), f"{path.name} does not end on a frame boundary"
    return walked


@dataclass(frozen=True)
class Work:
    records: int
    frame_bytes: int
    blob_bytes: int  # logical: each (record, blob) replay opened, once
    distinct_blob_bytes: int
    blob_calls: int  # read calls, duplicates included

    @property
    def total(self) -> int:
        return self.frame_bytes + self.blob_bytes


def interval_work(observer: Observer, walked: dict, lo: int, hi: int) -> Work:
    """What replay actually did for lo < seq <= hi: records applied, their frames, the blobs opened while applying them."""
    seqs = sorted({seq for seq in observer.applies if lo < seq <= hi})
    opened = [(seq, name, size) for kind, name, size, seq in observer.reads if kind == "blob" and seq is not None and lo < seq <= hi]
    logical = {(seq, name): size for seq, name, size in opened}
    distinct = {name: size for _seq, name, size in opened}
    return Work(len(seqs), sum(walked[seq][1] for seq in seqs), sum(logical.values()), sum(distinct.values()), len(opened))


def newest_checkpoint(root: Root):
    return [record for record in root.records() if record.type_name == "CHECKPOINT"][-1]


# ---------------------------------------------------------------------------
# The threshold, in one process and across a restart (injected small threshold)
# ---------------------------------------------------------------------------
SMALL = 20_000  # bytes_max for the structural controls; not the default constant
TEXT = "a" * 6000  # over INLINE_TEXT_BYTES: a MSG_APPEND whose text is a blob replay opens


def test_sv025_positive_an_ordinary_unit_crosses_the_byte_threshold_once(tmp_path, watch):
    """In one process the counter is the observed work after C_n's frame, and the overshoot is under one unit."""
    root = Root(tmp_path)
    establish(root).close()
    observer = watch()
    opening = root.start(ops=observer, bytes_max=SMALL)
    session = opening.session
    assert (opening.classification, session.since_bytes) == ("A9", 0)
    ck = newest_checkpoint(root).seq

    def observed():
        walked = frames(root)
        units = [seq for seq, (type_hex, _length) in walked.items() if seq > ck and type_hex == "0a"]
        return units, walked, interval_work(observer, walked, ck, max(units))

    for unit in (1, 2, 3):
        session.append_message("user", TEXT)
        units, walked, work = observed()
        assert len(units) == unit and max(walked) == units[-1], "no checkpoint below the threshold"
        assert (work.records, work.blob_bytes, work.blob_calls) == (unit, unit * len(TEXT), unit)
        assert session.since_bytes == work.total < SMALL
    session.append_message("user", TEXT)
    units, walked, work = observed()
    assert len(units) == 4 and walked[units[-1] + 1][0] == "0d", "the fourth unit checkpoints at once"
    one_unit = walked[units[-1]][1] + len(TEXT)
    assert SMALL <= work.total < SMALL + one_unit
    assert session.since_bytes == 0
    session.close()


def test_sv025_a_restart_carries_outstanding_suffix_bytes(tmp_path, watch):
    """SV026 replaced SV025's structural counterexample (a restart forgot the suffix's bytes).

    The restart rebuilds exactly what the dead process had counted after C_n's
    frame, and the threshold fires across the restart at the fourth unit.
    """
    root = Root(tmp_path)
    establish(root).close()
    opening = root.start(bytes_max=SMALL)
    session = opening.session
    assert (opening.classification, session.since_records, session.since_bytes) == ("A9", 0, 0), "C_n's frame is the origin"
    session.append_message("user", TEXT)
    session.append_message("user", TEXT)
    carried = session.since_bytes
    assert carried == 12_428 < SMALL, "SV025's executed value for these two units"
    session.close()  # process death before any checkpoint
    ck = newest_checkpoint(root)

    observer = watch()
    opening = root.start(ops=observer, bytes_max=SMALL)
    session = opening.session
    walked = frames(root)
    outstanding = interval_work(observer, walked, ck.payload["covers_seq"], max(walked))
    assert opening.classification == "A9"
    assert (outstanding.records, outstanding.blob_bytes) == (3, 2 * len(TEXT)), "C_n's frame and both messages, replayed"
    assert (session.since_records, session.since_bytes) == (2, carried) == (2, outstanding.total - walked[ck.seq][1])
    session.append_message("user", TEXT)
    assert newest_checkpoint(root).seq == ck.seq, "three units stay below the threshold"
    session.append_message("user", TEXT)
    walked = frames(root)
    new = newest_checkpoint(root)
    assert new.seq == max(walked) > ck.seq, "the fourth unit, across the restart, checkpoints at once"
    crossing = sum(walked[seq][1] for seq in walked if ck.seq < seq < new.seq) + 4 * len(TEXT)
    one_unit = walked[new.seq - 1][1] + len(TEXT)
    assert SMALL <= crossing < SMALL + one_unit
    assert (session.since_records, session.since_bytes) == (0, 0)
    session.close()

    opening = root.start(bytes_max=SMALL)
    assert opening.classification == "A9" and newest_checkpoint(root).seq == new.seq
    assert (opening.session.since_records, opening.session.since_bytes) == (0, 0)
    opening.session.close()


# ---------------------------------------------------------------------------
# Default constants: a large base switch in the suffix (A11)
# ---------------------------------------------------------------------------
TARGET = 27 * 1024 * 1024  # 28,311,552 bytes of valid ASCII list, below the 64 MiB conversation and blob read bounds


def test_sv025_a_27_mib_external_edit_blob_alone_exceeds_the_newest_byte_bound(tmp_path, watch, monkeypatch):
    """An accepted external edit puts the whole list in a suffix blob that replay opens: one blob > 25,166,144 bytes.

    SV026: startup now closes its unit with a threshold check, so the A11
    start checkpoints at once. The witness is therefore taken in the real
    pre-checkpoint crash window: that start dies at CK2 entry of its threshold
    checkpoint, after EXTERNAL_EDIT's fsync returned and before any checkpoint
    byte, and the next start replays the 27 MiB blob before its own checkpoint.
    """
    root = Root(tmp_path)
    establish(root).close()
    filler = TARGET - len(rp.conversation_bytes([{"role": "user", "content": ""}]))
    data = rp.conversation_bytes([{"role": "user", "content": "x" * filler}])
    assert len(data) == TARGET and TARGET < st.CONVERSATION_READ_MAX == cs.BLOB_READ_MAX
    edited = hashlib.sha256(data).hexdigest()
    (root.session_dir / "conversation.json").write_bytes(data)
    del data
    prev_bytes = len(root.file("conversation.prev.json"))
    entries = []
    original = cs.Session.checkpoint

    def logged(self, *args, **kwargs):
        entries.append((self.since_records, self.since_bytes))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(cs.Session, "checkpoint", logged)

    def die(*_args, **_kwargs):
        raise Crash()

    observer = watch()
    with monkeypatch.context() as m:
        m.setattr(cp, "install_conversation", die)  # process death at CK2 entry
        with pytest.raises(Crash):
            root.start(ops=observer)
    walked = frames(root)
    edit = max(walked)
    assert walked[edit][0] == "13", "the last record is the EXTERNAL_EDIT: no checkpoint byte was written"
    assert observer.of("blob") == [("blob", edited, TARGET, edit)], "the live reducer re-reads the blob it has just written"
    # The startup unit crossed the default threshold and its checkpoint began.
    assert entries == [(1, walked[edit][1] + TARGET)] and entries[0][1] >= cs.RECOVERY_BYTES_MAX

    entries.clear()
    newest = newest_checkpoint(root)  # C_n, before this start writes its own threshold checkpoint
    observer = watch()
    opening = root.start(ops=observer)
    session = opening.session
    assert opening.classification == "A9t"
    suffix = interval_work(observer, walked, newest.payload["covers_seq"], edit)
    # Neither file holds C_n, so this went through _previous_base: A's interval, then the suffix, each record once.
    assert [seq for seq in observer.applies if seq <= edit] == list(range(newest.payload["prev"]["covers_seq"] + 1, edit + 1))
    assert observer.of("blob") == [("blob", edited, TARGET, edit)]
    assert (suffix.records, suffix.blob_bytes, suffix.distinct_blob_bytes, suffix.blob_calls) == (2, TARGET, TARGET, 1)
    # The contradiction: the suffix after C_n alone is past the newest-row bound.
    assert suffix.total > suffix.blob_bytes >= NEWEST_BYTES_LT
    # The counter rebuilt at this start is that suffix after C_n's frame (the origin); it crosses, so one checkpoint.
    assert entries == [(1, suffix.total - walked[newest.seq][1])]
    after = frames(root)
    assert {seq: after[seq] for seq in walked} == walked and [after[seq][0] for seq in after if seq > edit] == ["0d"]
    # Separate I/O, not the suffix quantity: the base-file reads (the excluded term), the checkpoint's own
    # hashing of both files (CK3's choice), and the scanner.
    assert observer.of("conversation") == [
        ("conversation", "conversation.json", TARGET, None),
        ("conversation", "conversation.prev.json", prev_bytes, None),
    ] * 2
    assert [read[:3] for read in observer.of("segment")] == [("segment", "000000.svl", sum(n for _t, n in walked.values()))] * 2
    assert (session.since_records, session.since_bytes) == (0, 0)
    assert rp.conversation_sha(session.messages) == edited
    session.close()


# ---------------------------------------------------------------------------
# Default constants: the actual retained previous checkpoint
# ---------------------------------------------------------------------------
ROUNDS, MESSAGES = 3, 240  # static minimum for this shape: 3 rounds x 236 (718 records)


def test_sv025_the_retained_previous_base_can_be_older_than_the_last_checkpoint(tmp_path, watch):
    """After external edits the retained .prev.json still holds A, so every later prev names A and A14 replays from it."""
    root = Root(tmp_path)
    establish(root).close()
    first, second = [record for record in root.records() if record.type_name == "CHECKPOINT"]
    a = cs.checkpoint_tuple(first)
    assert (first.payload["prev"], second.payload["prev"]) == (None, a)
    prev_file = root.file("conversation.prev.json")
    for k in range(ROUNDS):
        (root.session_dir / "conversation.json").write_bytes(rp.conversation_bytes([{"role": "user", "content": f"EDIT {k}"}]))
        opening = root.start(collect=True)
        assert opening.classification == "A11"
        session = opening.session
        for i in range(MESSAGES):
            session.append_message("user", f"round {k} message {i}")
        # SV026: C_n's own frame is the interval origin, so the EXTERNAL_EDIT and the messages are counted.
        assert session.since_records == MESSAGES + 1 < cs.RECOVERY_RECORDS_MAX, "no threshold checkpoint fired"
        record = session.checkpoint()
        assert record.payload["prev"] == a, "the retained file still holds A's bytes, so prev names A"
        final = list(session.messages)
        session.close()
    assert root.file("conversation.prev.json") == prev_file
    walked = frames(root)
    covers = [seq - 1 for seq, (type_hex, _length) in walked.items() if type_hex == "0d"]
    assert [high - low for low, high in zip(covers, covers[1:], strict=False)] == [3, 242, 242, 242]
    newest = newest_checkpoint(root)
    assert newest.payload["prev"] == a

    (root.session_dir / "conversation.json").write_bytes(b"\x00damaged in the temporary root")
    observer = watch()
    opening = root.start(ops=observer, collect=True)
    assert (opening.classification, opening.stop) == ("A14", None)
    replayed = [seq for seq in observer.applies if seq <= newest.seq]
    assert replayed == list(range(a["covers_seq"] + 1, newest.seq + 1)), "A's interval, then the suffix, each once"
    # The contradiction: the actual previous-base replay reads more than 717 records.
    assert len(replayed) == 730 > PREV_RECORDS_MAX
    edits = [seq for seq, (type_hex, _length) in walked.items() if type_hex == "13"]
    assert sorted(seq for _kind, _name, _size, seq in observer.of("blob") if seq is not None and seq <= newest.seq) == edits
    session = opening.session
    assert session.messages == [*final, {"role": "user", "content": st.A14_NOTICE}]
    assert hashlib.sha256(root.file("conversation.json")).hexdigest() == newest.payload["conv"]["sha256"]
    assert root.file("conversation.prev.json") == prev_file
    session.close()
