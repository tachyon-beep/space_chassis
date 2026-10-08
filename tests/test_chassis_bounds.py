"""SV025: replay work against SV-015 v2 1.4.7's exact bounds, by an independent observer (test-only).

Nothing here changes the runtime, its limits or the canonical oracle. The
canonical values are copied from `SV-015-literal-values-v2.json`
(`ledger_frame_max_bytes`, `recovery_bound_defaults`). The maximal shapes are
rebuilt from the text of its generator (lines 90-117), which was read but never
run.

Three quantities, never substituted for one another:

* **Logical interval work**: for the records of one replay interval, their
  frame bytes plus the bytes of each blob replay opened while applying them,
  one count per (record, blob). This is the quantity v2 1.4.7 bounds.
* **Distinct blob bytes**: the same blobs, counted once by name.
* **Read calls**: every `DurableOps.read` a start made (segments, blobs, the
  conversation files, markers), duplicates included. This is not a suffix
  quantity.

The observer does not depend on the writer. Frame lengths come from a byte walk
of the segment files (`49 + plen + 66` from each header). Blob bytes come from
the reads the runtime actually made while `Replay.apply` ran for a given seq.
`since_bytes` is only compared against these numbers, never used as their
oracle.

The restart, external-edit and older-prev tests pass by asserting that a
canonical premise is contradicted. A pass there is a counterexample, not a
guarantee (docs/planning-context/sv025/RECEIPT.md).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import chassis_persistence as cp
import chassis_replay as rp
import chassis_session as cs
import chassis_startup as st
import pytest
from test_chassis_recovery_live import Root, establish

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


def current_checkpoint() -> dict:
    """The generator's CHECKPOINT with the state keys this runtime writes (`SessionState.to_wire`)."""
    payload = generator_shapes(LINEAGE16)["CHECKPOINT"][1]
    state = payload["state"]
    state["requests"]["next"] = {"turn_seq": BIG, "attempt": BIG}
    notes = state["notes"]
    notes["pending"] = [{**entry, "mirror_sha256": Z, "foreign": True} for entry in notes["pending"]]
    notes["adopted_mirror_sha256"] = Z
    notes["dropped_pending_limit"] = BIG
    return payload


CURRENT_SHAPES = [
    # (id, canonical literal, the runtime payloads, their exact frame sizes)
    ("request-sent-lineage16", "REQUEST_SENT", lambda: [
        ("REQUEST_SENT", {"turn_seq": BIG, "attempt": BIG, "label": label(LINEAGE16)}),
        ("REQUEST_SENT", {"turn_seq": BIG, "attempt": BIG, "label": label("l" * 64)}),  # a legacy run.json lineage
    ], [216, 264]),
    ("recovery-spend-next", "RECOVERY", lambda: [
        ("RECOVERY", {"kind": "possible_duplicate_spend", "detail": {"label": label(LINEAGE16), "next": {"turn_seq": BIG, "attempt": BIG}}}),
    ], [270]),
    ("unrun-ended-reason", "UNRUN", lambda: [
        ("UNRUN", {"call_key": [BIG, 31], "reason": f"not run: the run ended by handoff in call {W}"}),
    ], [263]),
    ("done-exception-type", "DONE", lambda: [
        ("DONE", {**generator_shapes()["DONE"][1], "outcome": "raised:" + "T" * 1000}),
    ], [1_351]),
    ("msg-append-inline-control", "MSG_APPEND_inline_4KiB", lambda: [
        ("MSG_APPEND", {"kind": "notice", "text": "\x01" * cs.INLINE_TEXT_BYTES, "epoch": BIG}),
    ], [24_739]),
    ("note-adoption-gen", "MSG_APPEND_blob", lambda: [
        ("MSG_APPEND", {"kind": "note", "gen": BIG, "blob": Z, "epoch": BIG}),
    ], [244]),
    ("checkpoint-current-state", "CHECKPOINT", lambda: [("CHECKPOINT", current_checkpoint())], [21_746]),
]


@pytest.mark.parametrize(("canonical", "shapes", "expected"), [c[1:] for c in CURRENT_SHAPES], ids=[c[0] for c in CURRENT_SHAPES])
def test_sv025_current_serializer_shapes_exceed_the_canonical_maxima(canonical, shapes, expected):
    """Payloads this runtime can write whose frames exceed the literal maximum used in U_b and the bounds."""
    sizes = [frame(type_name, payload) for type_name, payload in shapes()]
    assert sizes == expected
    assert min(sizes) > CANON_FRAMES[canonical], "the canonical maximal shape does not dominate this runtime payload"


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


def test_sv025_a_restart_forgets_outstanding_suffix_bytes(tmp_path, watch):
    """Records since C_n are rebuilt at startup; their bytes are not, so the suffix grows past bytes_max unchecked."""
    root = Root(tmp_path)
    establish(root).close()
    opening = root.start(bytes_max=SMALL)
    session = opening.session
    assert (opening.classification, session.since_records, session.since_bytes) == ("A9", 1, 0)
    session.append_message("user", TEXT)
    session.append_message("user", TEXT)
    carried = session.since_bytes
    assert carried < SMALL
    session.close()  # process death before any checkpoint
    ck = newest_checkpoint(root)

    observer = watch()
    opening = root.start(ops=observer, bytes_max=SMALL)
    session = opening.session
    walked = frames(root)
    outstanding = interval_work(observer, walked, ck.payload["covers_seq"], max(walked))
    assert opening.classification == "A9"
    assert (outstanding.records, outstanding.blob_bytes) == (3, 2 * len(TEXT)), "C_n's frame and both messages, replayed"
    assert outstanding.total - walked[ck.seq][1] == carried, "after C_n's frame: exactly what the dead process had counted"
    assert (session.since_records, session.since_bytes) == (3, 0), "records rebuilt from the suffix; bytes restart at zero"
    session.append_message("user", TEXT)
    session.append_message("user", TEXT)
    assert session.since_bytes == carried < SMALL
    session.close()

    observer = watch()
    opening = root.start(ops=observer, bytes_max=SMALL)
    walked = frames(root)
    outstanding = interval_work(observer, walked, ck.payload["covers_seq"], max(walked))
    assert [type_hex for type_hex, _length in walked.values()].count("0d") == 2, "no checkpoint was written while it grew"
    assert newest_checkpoint(root).seq == ck.seq
    assert (outstanding.records, outstanding.blob_bytes) == (5, 4 * len(TEXT))
    # The contradiction: replay work after C_n's frame is past bytes_max, and no threshold ever fired.
    assert outstanding.total - walked[ck.seq][1] >= SMALL > carried
    opening.session.close()


# ---------------------------------------------------------------------------
# Default constants: a large base switch in the suffix (A11)
# ---------------------------------------------------------------------------
TARGET = 27 * 1024 * 1024  # 28,311,552 bytes of valid ASCII list, below the 64 MiB conversation and blob read bounds


def test_sv025_a_27_mib_external_edit_blob_alone_exceeds_the_newest_byte_bound(tmp_path, watch):
    """An accepted external edit puts the whole list in a suffix blob that replay opens: one blob > 25,166,144 bytes."""
    root = Root(tmp_path)
    establish(root).close()
    filler = TARGET - len(rp.conversation_bytes([{"role": "user", "content": ""}]))
    data = rp.conversation_bytes([{"role": "user", "content": "x" * filler}])
    assert len(data) == TARGET and TARGET < st.CONVERSATION_READ_MAX == cs.BLOB_READ_MAX
    edited = hashlib.sha256(data).hexdigest()
    (root.session_dir / "conversation.json").write_bytes(data)
    del data
    prev_bytes = len(root.file("conversation.prev.json"))

    observer = watch()
    opening = root.start(ops=observer)
    session = opening.session
    walked = frames(root)
    edit = max(walked)
    assert opening.classification == "A11" and walked[edit][0] == "13", "the last record is the EXTERNAL_EDIT"
    assert observer.of("blob") == [("blob", edited, TARGET, edit)], "the live reducer re-reads the blob it has just written"
    # Startup evaluates no threshold: the counter is past RECOVERY_BYTES_MAX and nothing checkpoints.
    assert session.since_bytes == walked[edit][1] + TARGET >= session.bytes_max == cs.RECOVERY_BYTES_MAX
    assert rp.conversation_sha(session.messages) == edited
    session.close()
    del opening, session

    observer = watch()
    opening = root.start(ops=observer)
    session = opening.session
    assert opening.classification == "A9t"
    assert frames(root) == walked, "the restart wrote nothing"
    newest = newest_checkpoint(root)
    suffix = interval_work(observer, walked, newest.payload["covers_seq"], edit)
    # Neither file holds C_n, so this went through _previous_base: A's interval, then the suffix, each record once.
    assert observer.applies == list(range(newest.payload["prev"]["covers_seq"] + 1, edit + 1))
    assert observer.of("blob") == [("blob", edited, TARGET, edit)]
    assert (suffix.records, suffix.blob_bytes, suffix.distinct_blob_bytes, suffix.blob_calls) == (2, TARGET, TARGET, 1)
    # The contradiction: the suffix after C_n alone is past the newest-row bound.
    assert suffix.total > suffix.blob_bytes >= NEWEST_BYTES_LT
    # Separate I/O, not the suffix quantity: the base-file reads (the excluded term) and the scanner.
    assert observer.of("conversation") == [
        ("conversation", "conversation.json", TARGET, None),
        ("conversation", "conversation.prev.json", prev_bytes, None),
    ]
    assert [read[:3] for read in observer.of("segment")] == [("segment", "000000.svl", sum(n for _t, n in walked.values()))] * 2
    assert (session.since_records, session.since_bytes) == (2, 0)
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
        assert session.since_records == MESSAGES + 2 < cs.RECOVERY_RECORDS_MAX, "no threshold checkpoint fired"
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
