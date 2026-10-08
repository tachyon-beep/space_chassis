"""SV026: replay-work accounting and closed-unit threshold checks, against an independent oracle.

Contract: SV-015 v2 sections 1.4.1 and 1.4.7, as `docs/planning-context/sv026/DESIGN.md`
specifies the counter (with the launch qualifications at its top):

* The counter covers the records after the interval **origin**: the newest
  CHECKPOINT's own frame, or the genesis header (seq 1) before any checkpoint.
  The origin frame itself is replayed but is not in the counter; it is the
  separate, unresolved `T_origin` term. Every later LEDGER_HEADER is charged.
* Each record is charged its frame plus the blob bytes the selected reducer
  *obtained* while applying it, before the hash decision: accepted bytes, a
  wrong-hash file's bytes, the `limit + 1` probe of an over-limit file; 0 for
  a missing file. An I/O error leaves the amount unknown (`since_unmeasured`).

The oracle never reads the counter or the runtime's own `obtained` values.
Frames come from SV025's byte walk of the segment files (`frames`). Blob
amounts come from `Attempts`, a filesystem helper that logs each blob read
attempt from its own measurement, attributed to the seq whose `Replay.apply`
is running.

Evidence kind: in-process simulation in temporary roots, as in
`test_chassis_recovery_live` (a "crash" abandons a session or raises `Crash`;
a "restart" calls `open_session` again). Thresholds and read limits other
than the defaults are injected and labelled. Nothing here bounds replay work
numerically: SV025's counterexamples stand.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import chassis
import chassis_envelope as envelope
import chassis_persistence as cp
import chassis_replay as rp
import chassis_session as cs
import chassis_startup as st
import pytest
from test_chassis_bounds import frames
from test_chassis_gc import CutOps, collection_ready
from test_chassis_recovery_live import (
    BASE,
    LINEAGE,
    R7_CALLS,
    Crash,
    FaultOps,
    Root,
    append_raw,
    damaged,
    establish,
    frame_after,
    partial_turn,
    respond,
    resume,
    turn7_open,
)
from test_chassis_termination import make_run, reply  # noqa: F401 -- make_run is a fixture

HEADER = "# Handoff"
TEXT = "a" * 6000  # over INLINE_TEXT_BYTES: a MSG_APPEND whose text is a blob replay opens
RESULT = "r" * 5000  # a DONE blob of 5,000 bytes
CHECKPOINT, GC_DONE, HEADER_TYPE = "0d", "12", "01"


# ---------------------------------------------------------------------------
# The independent oracle
# ---------------------------------------------------------------------------
class Attempts(cp.DurableOps):
    """The real filesystem helper, plus a log of every blob read attempt and what it obtained.

    `reads`: (blob name, bytes obtained or None when unknown, outcome, seq being applied or None).
    The amount is this helper's own measurement: the returned length, or for a
    refused over-limit read the file's own size capped at `limit + 1`.
    """

    def __init__(self, fail=()) -> None:
        self.reads: list[tuple[str, int | None, str, int | None]] = []
        self.applies: list[int] = []
        self.applying: int | None = None
        self.fail = set(fail)

    def read(self, path, limit):
        p = Path(path)
        if p.parent.name != "blobs":
            return super().read(path, limit)
        if p.name in self.fail:
            self.reads.append((p.name, None, "io_error", self.applying))
            raise OSError(errno.EIO, "injected EIO")
        try:
            data = super().read(path, limit)
        except FileNotFoundError:
            self.reads.append((p.name, 0, "missing", self.applying))
            raise
        except cp.ReadTooLarge:
            self.reads.append((p.name, min(os.stat(path).st_size, limit + 1), "over_limit", self.applying))
            raise
        self.reads.append((p.name, len(data), "returned", self.applying))
        return data


@pytest.fixture
def attempts(monkeypatch):
    """A new `Attempts` per call; every `Replay.apply`, startup's or the live session's, is attributed to the newest."""
    current: dict = {}
    original = rp.Replay.apply

    def apply(replay, record):
        ops = current.get("ops")
        if ops is None:
            return original(replay, record)
        ops.applies.append(record.seq)
        ops.applying = record.seq
        try:
            return original(replay, record)
        finally:
            ops.applying = None

    monkeypatch.setattr(rp.Replay, "apply", apply)

    def new(fail=()) -> Attempts:
        current["ops"] = Attempts(fail)
        return current["ops"]

    return new


@dataclass(frozen=True)
class Seen:
    records: int
    frame_bytes: int
    blob_bytes: int
    unknown: int

    @property
    def total(self) -> int:
        return self.frame_bytes + self.blob_bytes


def seen(ops: Attempts | None, root: Root, lo: int, hi: int | None = None) -> Seen:
    """Every frame with lo < seq <= hi (headers included), plus the blob amounts read while applying them."""
    walked = frames(root)
    hi = max(walked) if hi is None else hi
    seqs = [seq for seq in walked if lo < seq <= hi]
    amounts = [n for _name, n, _outcome, seq in (ops.reads if ops else []) if seq is not None and lo < seq <= hi]
    return Seen(len(seqs), sum(walked[seq][1] for seq in seqs), sum(n for n in amounts if n is not None), amounts.count(None))


def origin(root: Root) -> int:
    """The interval origin: the newest CHECKPOINT's seq, or the genesis header's (1)."""
    checkpoints = [record.seq for record in root.records() if record.type_name == "CHECKPOINT"]
    return checkpoints[-1] if checkpoints else 1


def counter(session) -> tuple[int, int]:
    return (session.since_records, session.since_bytes)


def assert_counted(session, ops, root) -> Seen:
    observed = seen(ops, root, origin(root))
    assert counter(session) == (observed.records, observed.total), (counter(session), observed)
    return observed


def types_after(root: Root, seq: int) -> list[str]:
    return [record.type_name for record in root.records() if record.seq > seq]


def blob_name(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def done_turn(session, text: str = RESULT):
    """Turn 7's REQUEST_SENT, TURN_RESPONSE, INVOKING0 and DONE0 with `text`; call 1 stays open."""
    adoption = respond(session, calls=R7_CALLS)
    call = adoption.calls[0]
    session.invoke(call, lambda: None)
    session.record_result(call, "returned", text)
    return blob_name(text)


def die(*_args, **_kwargs):
    raise Crash()


def once(predicate):
    """A fault predicate that matches only its first matching call, so the FSYNC_FAILED marker can still be written."""
    state = {"fired": False}

    def matches(path):
        if not state["fired"] and predicate(path):
            state["fired"] = True
            return True
        return False

    return matches


def foreign_pending(root: Root) -> None:
    """SV021-10's setup: a pending generation marked foreign by an A8 reimport, checkpointed before adoption."""
    session = establish(root)
    session.write_note("N1", header=HEADER)
    session.checkpoint()
    session.close()
    n1 = rp.NOTE_PREFIX + f"{HEADER}\n\nN1\n"
    (root.session_dir / "conversation.json").write_text(json.dumps([*BASE, {"role": "user", "content": n1}], indent=2) + "\n")
    meta = json.loads(root.file("run.json"))
    for key in ("format", "writer", "checkpoint", "history_epoch"):
        meta.pop(key)
    (root.session_dir / "run.json").write_text(json.dumps(meta))
    opening = root.start()
    assert opening.classification == "A8"
    opening.session.checkpoint()
    opening.session.close()


# ---------------------------------------------------------------------------
# A1: the live charge, unit by unit
# ---------------------------------------------------------------------------
def _write_note(session):
    session.write_note("a note", header=HEADER)


UNITS = {
    "say-inline": (None, lambda s: s.append_message("user", "x" * 100)),
    "say-blob": (None, lambda s: s.append_message("user", TEXT)),
    "done-blob": (None, done_turn),
    "note-written": (None, _write_note),
    "note-adopted": (_write_note, lambda s: s.adopt_notes()),
    "original-retained-only": (None, lambda s: respond(s, content="c" * (envelope.DEFAULT_CAPS.content + 1))),
}


@pytest.mark.parametrize("kind", list(UNITS))
def test_sv026_live_counter_equals_observed_work_per_unit_kind(tmp_path, attempts, kind):
    root = Root(tmp_path)
    establish(root).close()
    ops = attempts()
    session = root.start(ops=ops).session
    prepare, unit = UNITS[kind]
    if prepare is not None:
        prepare(session)
    mark, before = max(frames(root)), counter(session)
    unit(session)
    delta = seen(ops, root, mark)
    # (a) the unit's own charge: frame plus the blob bytes its live apply read
    assert (session.since_records - before[0], session.since_bytes - before[1]) == (delta.records, delta.total)
    if kind in ("say-inline", "note-written", "original-retained-only"):
        assert delta.blob_bytes == 0, "nothing the reducer opens"
    # (b) the whole interval after C_n, whose own frame is the origin
    assert_counted(session, ops, root)
    session.close()


# ---------------------------------------------------------------------------
# A2: restart reconstruction, including every blob read outcome
# ---------------------------------------------------------------------------
def _history_cut(session):
    with pytest.MonkeyPatch.context() as m:
        m.setattr(cp, "install_conversation", die)
        with pytest.raises(Crash):
            session.replace_history([{"role": "user", "content": "h" * 6000}])


RESTARTS = {
    "say-blob-x2": lambda s: (s.append_message("user", TEXT), s.append_message("user", TEXT)),
    "done-blob": done_turn,
    "done-missing": done_turn,
    "done-wrong-hash-larger": done_turn,
    "done-wrong-hash-smaller": done_turn,
    "done-over-limit": done_turn,
    "done-io-error": done_turn,
    "note-adopted": lambda s: (_write_note(s), s.adopt_notes()),
    "foreign-note-adopted": lambda s: s.adopt_notes(),
    "history-replaced-cut": _history_cut,
    "original-retained-only": lambda s: respond(s, content="c" * (envelope.DEFAULT_CAPS.content + 1)),
}
LIMIT = 1_000  # [injected] the restart's blob read limit for done-over-limit


@pytest.mark.parametrize("case", list(RESTARTS))
def test_sv026_restart_reconstructs_the_counter_exactly(tmp_path, attempts, monkeypatch, case):
    root = Root(tmp_path)
    if case == "foreign-note-adopted":
        foreign_pending(root)
    else:
        establish(root).close()
    ops = attempts()
    session = root.start(ops=ops).session
    mark, before = max(frames(root)), counter(session)
    RESTARTS[case](session)
    delta = seen(ops, root, mark)
    assert (session.since_records - before[0], session.since_bytes - before[1]) == (delta.records, delta.total), "the live charge"
    c1, last = counter(session), max(frames(root))
    session.close()  # process death, no checkpoint

    done = next((r for r in root.records() if r.type_name == "DONE"), None)
    path = root.session_dir / "blobs" / blob_name(RESULT)
    fail = ()
    if case == "done-missing":
        path.unlink()
    elif case == "done-wrong-hash-larger":
        path.write_bytes(b"L" * (3 * len(RESULT)))
    elif case == "done-wrong-hash-smaller":
        path.write_bytes(b"S" * (len(RESULT) // 2))
    elif case == "done-io-error":
        fail = (path.name,)
    ops = attempts(fail)
    with monkeypatch.context() as m:
        if case == "done-over-limit":
            m.setattr(st, "BLOB_READ_MAX", LIMIT)
        opening = root.start(ops=ops)
    assert opening.classification == "A9", opening
    session = opening.session

    if done is not None:
        # What the selected reducer obtained for DONE, from the oracle's own measurement.
        obtained = [(n, outcome) for _name, n, outcome, seq in ops.reads if seq == done.seq]
        expected = {
            "done-blob": [(len(RESULT), "returned")],
            "done-missing": [(0, "missing")],
            "done-wrong-hash-larger": [(3 * len(RESULT), "returned")],
            "done-wrong-hash-smaller": [(len(RESULT) // 2, "returned")],
            "done-over-limit": [(LIMIT + 1, "over_limit")],
            "done-io-error": [(None, "io_error")],
        }[case]
        assert obtained == expected, obtained
        lost = rp.returned_lost_text(len(RESULT), blob_name(RESULT))
        tool = next(m for m in session.messages if m.get("tool_call_id") == "call_a")
        assert tool["content"] == (RESULT if case == "done-blob" else lost), "the lost-DONE outcome is unchanged"
    if case == "foreign-note-adopted":
        note = next(r for r in root.records() if r.payload.get("kind") == "note")
        assert note.payload.get("foreign") is True
        assert [read for read in ops.reads if read[3] == note.seq] == [], "a foreign adoption opens no blob"
    if case == "original-retained-only":
        response = next(r for r in root.records() if r.type_name == "TURN_RESPONSE" and r.seq > mark)
        assert response.payload["original_blobs"] and [read for read in ops.reads if read[3] == response.seq] == []

    observed = assert_counted(session, ops, root)
    if done is not None:
        # Restart = dead process's charge, with DONE's obtained bytes replaced, plus the restart's own new records.
        new = seen(ops, root, last)
        assert new.records >= 1, "the restart closed call 1"
        second = obtained[0][0] or 0
        assert counter(session) == (c1[0] + new.records, c1[1] - len(RESULT) + second + new.total)
        assert (session.since_unmeasured, observed.unknown) == ((1, 1) if case == "done-io-error" else (0, 0))
    else:
        assert counter(session) == c1, "the dead process's charge, rebuilt exactly"
    session.close()


# ---------------------------------------------------------------------------
# A3-A5: no double count; the previous base; an earlier attempt's extras
# ---------------------------------------------------------------------------
def test_sv026_repeated_restarts_never_double_count(tmp_path, attempts):
    root = Root(tmp_path)
    establish(root).close()
    session = root.start().session
    session.append_message("user", TEXT)
    session.append_message("user", TEXT)
    session.close()
    walked = frames(root)
    counters = []
    for _restart in range(3):
        ops = attempts()
        opening = root.start(ops=ops)
        assert opening.classification == "A9"
        assert_counted(opening.session, ops, root)
        counters.append(counter(opening.session))
        opening.session.close()
        assert frames(root) == walked, "a start below the threshold writes nothing"
    assert counters[0] == counters[1] == counters[2] == (2, sum(walked[s][1] for s in walked if s > origin(root)) + 2 * len(TEXT))


def test_sv026_previous_base_recovery_counts_only_the_newest_suffix(tmp_path, attempts):
    root = Root(tmp_path)
    establish(root).close()
    a, b = [record for record in root.records() if record.type_name == "CHECKPOINT"]
    assert b.payload["prev"]["checkpoint_seq"] == a.seq
    session = root.start().session
    session.append_message("user", TEXT)
    session.append_message("user", TEXT)
    session.close()
    (root.session_dir / "conversation.json").write_bytes(b"\x00damaged in the temporary root")
    ops = attempts()
    opening = root.start(ops=ops)
    assert (opening.classification, opening.stop) == ("A14", None)
    interval = [seq for seq in ops.applies if a.payload["covers_seq"] < seq <= b.payload["covers_seq"]]
    assert interval, "the previous base's interval was replayed (on its own instance)"
    observed = assert_counted(opening.session, ops, root)
    assert observed.records == 2 + 2, "the suffix's two messages, the A14 notice and conversation_restored"
    opening.session.close()


def test_sv026_recovery_extras_from_an_earlier_attempt_are_counted_once(tmp_path, attempts):
    root = Root(tmp_path)
    session, turn = turn7_open(root)
    frame = frame_after(root, session, "INVOKING", {"turn_seq": turn, "call_index": 0})
    session.close()
    append_raw(root, damaged(frame))
    ops = FaultOps()

    def appended(path):  # the first recovery record's own fsync (SV025's semantic cut)
        return path.endswith(".svl") and ops.events[-2] == ("write", path)

    ops.faults.append(("fsync", appended, Crash()))
    with pytest.raises(Crash):
        root.start(ops=ops)
    synth = root.records()[-1]
    assert synth.type_name == "SYNTH" and (root.session_dir / st.RECOVERING).exists()
    watched = attempts()
    opening = root.start(ops=watched)
    assert opening.session is not None, opening
    assert watched.applies.count(synth.seq) == 1, "the readable extra is applied once"
    assert_counted(opening.session, watched, root)
    assert not (root.session_dir / st.RECOVERING).exists()
    opening.session.close()


# ---------------------------------------------------------------------------
# A6: the origin and every later header
# ---------------------------------------------------------------------------
SAY = "s" * 200  # inline: every such MSG_APPEND has one frame size


@pytest.mark.parametrize(
    "case", ["genesis-baseline", "pre-first-checkpoint-rotation", "post-checkpoint-header-crosses", "continue-after-reuse"]
)
def test_sv026_origin_and_headers(tmp_path, attempts, case):
    root = Root(tmp_path)
    if case in ("genesis-baseline", "pre-first-checkpoint-rotation"):
        ops = attempts()
        opening = root.start(ops=ops)
        assert opening.classification == "A4"
        session = opening.session
        for index, text in enumerate(("a", "b", "c")):
            if case == "pre-first-checkpoint-rotation" and index == 0:
                session.writer.segment_max = 1  # the next unit_end rotates: a header H after the first say
            session.append_message("user", text)
            session.writer.segment_max = cp.SEGMENT_MAX
        walked = frames(root)
        headers = [seq for seq, (type_hex, _n) in walked.items() if type_hex == HEADER_TYPE]
        assert headers[0] == 1 and len(headers) == (1 if case == "genesis-baseline" else 2), headers
        observed = assert_counted(session, ops, root)
        assert observed.records == (4 if case == "genesis-baseline" else 5), "LEGACY_IMPORT, three says (and H); never seq 1"
        c1 = counter(session)
        session.close()
        ops = attempts()
        opening = root.start(ops=ops)
        assert opening.session is not None and "CHECKPOINT" not in root.types()
        assert_counted(opening.session, ops, root)
        assert counter(opening.session) == c1, "the restart charges the same frames"
        opening.session.close()
        return

    establish(root).close()
    if case == "continue-after-reuse":
        # O2-5: the next segment's name survived, its header bytes did not.
        last = sorted((root.session_dir / "ledger").glob("*.svl"))[-1]
        (last.parent / f"{int(last.stem) + 1:06d}.svl").write_bytes(b"")
        ops = attempts()
        opening = root.start(ops=ops)
        assert opening.classification == "A9"
        walked = frames(root)
        header = max(walked)
        assert walked[header][0] == HEADER_TYPE, "continue_after reused the empty segment"
        assert_counted(opening.session, ops, root)
        assert counter(opening.session) == (1, walked[header][1])
        c1 = counter(opening.session)
        opening.session.close()
        ops = attempts()
        opening = root.start(ops=ops)
        assert_counted(opening.session, ops, root)
        assert counter(opening.session) == c1, "a later restart replays and charges the reuse header"
        opening.session.close()
        return

    # post-checkpoint-header-crosses (Astra's discriminator)
    ops = attempts()
    session = root.start(ops=ops).session
    session.writer.segment_max = 1
    session.append_message("user", SAY)  # unit_end rotates: header H after C_n
    session.writer.segment_max = cp.SEGMENT_MAX
    walked = frames(root)
    say1, header = sorted(walked)[-2:]
    assert (walked[say1][0], walked[header][0]) == ("0a", HEADER_TYPE)
    f, h = walked[say1][1], walked[header][1]
    session.bytes_max = 3 * f + h  # [injected]: three says alone stay below it; with H the third reaches it
    session.append_message("user", SAY)
    say2, before_third = max(frames(root)), counter(session)
    assert types_after(root, header) == ["MSG_APPEND"], "2f + h is below the threshold"
    session.append_message("user", SAY)
    walked = frames(root)
    assert [walked[s][0] for s in sorted(walked) if s > say2] == ["0a", CHECKPOINT], "3f + h crosses: a checkpoint at once"
    assert walked[say2][1] == walked[say2 + 1][1] == f
    session.close()
    newest_before = [s for s in sorted(walked) if walked[s][0] == CHECKPOINT][-2]
    observed = seen(ops, root, newest_before, say2)
    assert newest_before < say1 and (observed.records, observed.total) == (3, 2 * f + h)
    assert before_third == (observed.records, observed.total), "the live counter held H before the crossing"


# ---------------------------------------------------------------------------
# A7: startup closes its unit with a threshold check
# ---------------------------------------------------------------------------
STARTUP_CASES = ["crosses-bytes", "crosses-records", "below-control", "after-intent", "legacy-start", "fence-failure"]


@pytest.mark.parametrize("case", STARTUP_CASES)
def test_sv026_startup_closes_its_unit_with_a_threshold_check(tmp_path, monkeypatch, case):
    root = Root(tmp_path)
    if case == "legacy-start":
        legacy = [{"role": "user", "content": "x" * 30_000}]
        (root.session_dir / "conversation.json").write_text(json.dumps(legacy, indent=2) + "\n")
        opening = root.start(bytes_max=20_000)  # [injected]
        assert opening.classification == "A5"
        assert root.types()[-2:] == ["LEGACY_IMPORT", "CHECKPOINT"], "the import's 30 kB blob crosses at startup"
        assert counter(opening.session) == (0, 0)
        opening.session.close()
        return
    if case == "after-intent":
        session, turn = turn7_open(root)
        frame = frame_after(root, session, "INVOKING", {"turn_seq": turn, "call_index": 0})
        session.close()
        append_raw(root, damaged(frame))  # TC2: the start publishes RECOVERING
        ops, entries, events = FaultOps(), [], []
        original = cs.Session.checkpoint

        def logged(self, *args, **kwargs):
            entries.append({
                "recovering": (root.session_dir / st.RECOVERING).exists(),
                "acknowledged": (root.session_dir / st.ACKNOWLEDGED).exists(),
                "identity": cs.read_identity(root.session_dir, LINEAGE),
                "next_turn": self.state.requests_next["turn_seq"],
                "at": len(ops.events),
            })
            return original(self, *args, **kwargs)

        monkeypatch.setattr(cs.Session, "checkpoint", logged)
        opening = root.start(ops=ops, collect=True, records_max=1, lifecycle=lambda event, **f: events.append((event, f)))  # [injected]
        assert opening.session is not None, opening
        assert entries, "the startup unit ended in a threshold checkpoint"
        first = entries[0]
        used = [r.payload["turn_seq"] for r in root.records() if r.type_name == "REQUEST_SENT"]
        assert not first["recovering"] and not first["acknowledged"]
        assert first["identity"] is not None and first["identity"] >= max([*used, first["next_turn"]]), "IDENTITY covers first"
        trail = ops.events
        session_dir = str(root.session_dir)
        unlinked = trail.index(("unlink", str(root.session_dir / st.RECOVERING)))
        fenced = next(i for i in range(unlinked, len(trail)) if trail[i] == ("sync_dir", session_dir))
        temp = next(i for i in range(first["at"], len(trail)) if trail[i][0] == "open" and "/.conversation." in trail[i][1])
        assert unlinked < fenced < temp, "RECOVERING's removal is durable before the checkpoint begins"
        renames = [i for i, e in enumerate(trail) if e == ("rename", str(root.session_dir / cs.IDENTITY))]
        assert all(i < temp for i in renames), "an IDENTITY write, if one was needed, came first"
        assert not [f for e, f in events if e == "gc_refused" and "RECOVERING" in f.get("reason", "")]
        types = root.types()
        assert types.index("SYNTH") < len(types) - 1 - types[::-1].index("CHECKPOINT")
        opening.session.close()
        return

    establish(root).close()
    session = root.start().session
    for index in range(5 if case == "crosses-records" else 4):
        session.append_message("user", TEXT if case != "crosses-records" else f"say {index}")
    session.close()
    walked = frames(root)
    kwargs = {"crosses-bytes": {"bytes_max": 20_000}, "fence-failure": {"bytes_max": 20_000},
              "crosses-records": {"records_max": 4}, "below-control": {"bytes_max": 10**9}}[case]  # [injected]
    if case == "fence-failure":
        ops = FaultOps()
        original = cs.Session.checkpoint

        def arming(self, *args, **kwargs):
            ops.faults.append(("sync_dir", once(lambda p: p == str(root.session_dir)), OSError(errno.EIO, "injected EIO")))
            return original(self, *args, **kwargs)

        monkeypatch.setattr(cs.Session, "checkpoint", arming)
        with pytest.raises(cp.PersistenceFailure):
            root.start(ops=ops, **kwargs)
        assert (root.session_dir / st.FSYNC_FAILED).exists()
        assert root.types()[-1] == "MSG_APPEND", "no CHECKPOINT after the failed fence"
        monkeypatch.setattr(cs.Session, "checkpoint", original)
        opening = root.start()
        assert (opening.classification, opening.stop) == ("A1", "fsync_failed_previous_run")
        return
    opening = root.start(**kwargs)
    assert opening.classification == "A9"
    if case == "below-control":
        assert frames(root) == walked, "below the threshold nothing is written"
    else:
        assert types_after(root, max(walked)) == ["CHECKPOINT"], "the startup unit crossed: one checkpoint"
        assert counter(opening.session) == (0, 0) and opening.session.since_unmeasured == 0
    opening.session.close()


# ---------------------------------------------------------------------------
# A8: adoption and drops are closed units
# ---------------------------------------------------------------------------
def _pending(session, count: int) -> None:
    for index in range(count):
        session.write_note(f"note {index}", header=HEADER)
    session.checkpoint()


ADOPTION_CASES = ["each-generation", "file-edit", "drop-in-write_note", "drop-in-adopt_file_edit", "drop-notice", "drop-inside-group-control"]


@pytest.mark.parametrize("case", ADOPTION_CASES)
def test_sv026_adoption_and_drops_are_closed_units(tmp_path, case):
    root = Root(tmp_path)
    session = establish(root)
    if case == "each-generation":
        _pending(session, 3)
        session.close()
        session = root.start().session
        session.records_max = 2  # [injected]
        mark = origin(root)
        session.adopt_notes()
        assert types_after(root, mark) == ["MSG_APPEND", "MSG_APPEND", "CHECKPOINT", "MSG_APPEND"]
        notes = [r for r in root.records() if r.type_name == "CHECKPOINT"][-1].payload["state"]["notes"]
        assert notes["adopted_through"] == 2 and [entry["gen"] for entry in notes["pending"]] == [3]
        session.close()
        session = resume(root.start())
        assert len([r for r in root.records() if r.payload.get("kind") == "note"]) == 3, "nothing adopted twice"
    elif case == "file-edit":
        session.close()
        (root.home / "HANDOFF.md").write_text("an agent's own edit\n")
        session = root.start().session
        session.records_max = 1  # [injected]
        mark = origin(root)
        assert session.adopt_file_edit() is not None
        assert types_after(root, mark) == ["NOTE_WRITTEN", "CHECKPOINT"]
    elif case == "drop-in-write_note":
        _pending(session, rp.MAX_PENDING_NOTES)
        session.records_max = 1  # [injected]
        mark = origin(root)
        assert session.write_note("the seventeenth", header=HEADER) is None
        assert types_after(root, mark) == ["RECOVERY", "CHECKPOINT"]
    elif case == "drop-in-adopt_file_edit":
        _pending(session, rp.MAX_PENDING_NOTES)
        session.close()
        (root.home / "HANDOFF.md").write_text("an agent's edit with no room left\n")
        session = root.start().session
        session.records_max = 1  # [injected]
        mark = origin(root)
        assert session.adopt_file_edit() is None
        assert types_after(root, mark) == ["RECOVERY", "CHECKPOINT"]
    elif case == "drop-notice":
        _pending(session, rp.MAX_PENDING_NOTES)
        assert session.write_note("the seventeenth", header=HEADER) is None
        session.checkpoint()
        session.close()
        session = root.start().session
        session.records_max = rp.MAX_PENDING_NOTES + 1  # [injected]: only the drop notice reaches it
        mark = origin(root)
        session.adopt_notes()
        after = [r for r in root.records() if r.seq > mark]
        assert [r.type_name for r in after] == ["MSG_APPEND"] * (rp.MAX_PENDING_NOTES + 1) + ["CHECKPOINT"]
        assert after[-2].payload.get("reports") == "note_dropped_pending_limit"
    else:  # drop-inside-group-control
        _pending(session, rp.MAX_PENDING_NOTES)
        session.records_max = 1  # [injected]
        mark = origin(root)
        adoption = respond(session, calls=[("call_t", "read_file", '{"path":"x"}')])
        assert session.write_note("in a tool", header=HEADER) is None  # the drop, inside the open group
        assert "CHECKPOINT" not in types_after(root, mark), "CKG: no checkpoint inside a group"
        (call,) = adoption.calls
        session.invoke(call, lambda: None)
        session.record_result(call, "returned", "done")
        assert "CHECKPOINT" not in types_after(root, mark)
        session.checkpoint()  # the turn's own end
        assert types_after(root, mark)[-1] == "CHECKPOINT" and types_after(root, mark).count("CHECKPOINT") == 1
    session.close()


# ---------------------------------------------------------------------------
# A9, A11, A12: a GC unit after the reset; G2's one non-collecting follow-up
# ---------------------------------------------------------------------------
ENDED = {"exit": 0, "reason": "finish", "at": "2026-10-08T00:00:00Z", "run": "sv026"}


def frames_after(root: Root, seq: int) -> tuple[int, int]:
    walked = frames(root)
    after = [s for s in walked if s > seq]
    return len(after), sum(walked[s][1] for s in after)


@pytest.mark.parametrize("case", ["records", "final-ended", "below-control"])
def test_sv026_a_crossing_gc_unit_gets_one_non_collecting_follow_up(tmp_path, case):
    root, session, _orphans = collection_ready(tmp_path / "w")
    mark = max(frames(root))
    if case != "below-control":
        session.records_max = 2  # [injected]: the GC pair alone reaches it
    record = session.checkpoint(ended=ENDED) if case == "final-ended" else session.checkpoint()
    after = [r for r in root.records() if r.seq > mark]
    kinds = [r.type_name for r in after if r.type_name != "LEDGER_HEADER"]
    if case == "below-control":
        assert kinds == ["CHECKPOINT", "GC_INTENT", "GC_DONE"]
        assert record.seq == after[0].seq
    else:
        assert kinds == ["CHECKPOINT", "GC_INTENT", "GC_DONE", "CHECKPOINT"], "one follow-up, and it does not collect"
        follow = [r for r in after if r.type_name == "CHECKPOINT"][-1]
        assert record.seq == follow.seq, "the final record is returned"
        assert all(r.type_name == "LEDGER_HEADER" for r in after if r.seq > follow.seq), "at most the rotation after it"
        meta = json.loads(root.file("run.json"))
        assert meta["checkpoint"]["covers_seq"] == follow.payload["covers_seq"]
        assert meta.get("ended") == (ENDED if case == "final-ended" else None)
    assert counter(session) == frames_after(root, record.seq), "everything after the last checkpoint, headers included"
    session.close()


@pytest.mark.parametrize("case", ["after-checkpoint", "after-gc", "restart-after-gc"])
def test_sv026_a_reset_interval_charges_only_new_work(tmp_path, attempts, case):
    if case == "after-checkpoint":
        root = Root(tmp_path)
        establish(root).close()
        ops = attempts()
        session = root.start(ops=ops).session
        session.append_message("user", TEXT)
        session.checkpoint()
        assert counter(session) == (0, 0)
        session.append_message("user", TEXT)
        observed = assert_counted(session, ops, root)
        assert observed.blob_bytes == len(TEXT)
        assert session.replay.work_bytes > session.since_bytes, "the lifetime sum is not the interval"
        session.close()
        return
    root, session, _orphans = collection_ready(tmp_path / "w")
    session.checkpoint()
    newest = origin(root)
    assert "GC_DONE" in types_after(root, newest), "the checkpoint collected"
    assert counter(session) == frames_after(root, newest), "the GC pair (and any header) after the reset"
    session.append_message("user", "after collection")  # inline: no blob
    assert counter(session) == frames_after(root, newest)
    carried = counter(session)
    session.close()
    if case == "restart-after-gc":
        opening = root.start(collect=True)
        assert opening.classification == "A9"
        assert counter(opening.session) == carried == frames_after(root, newest), "the restart rebuilds the same work"
        opening.session.close()


FOLLOW_UP_CUTS = ["crash-before-install", "crash-after-ck5-before-frame-write", "fence-failure"]


@pytest.mark.parametrize("case", FOLLOW_UP_CUTS)
def test_sv026_follow_up_checkpoint_cuts(tmp_path, monkeypatch, case):
    ops = CutOps()
    root, session, _orphans = collection_ready(tmp_path / "w", ops=ops)
    ops.paths[session.writer.fd] = str(root.segment())
    mark = max(frames(root))
    session.records_max = 2  # [injected]
    count = {"temp": 0, "checkpoint": 0, "gc_done": False, "failed": False}

    def crash_when(call, path, frame):
        if case == "crash-before-install" and call == "open" and "/.conversation." in path:
            count["temp"] += 1
            return count["temp"] == 2  # the follow-up's CK2: the first checkpoint installed its own
        if case == "crash-after-ck5-before-frame-write" and call == "write" and frame == CHECKPOINT:
            count["checkpoint"] += 1
            return count["checkpoint"] == 2  # after its CK5, before its CHECKPOINT frame is written
        return False

    def fail_when(call, path, frame):
        if call == "write" and frame == GC_DONE:
            count["gc_done"] = True
        if case == "fence-failure" and count["gc_done"] and not count["failed"] and call == "sync_dir" and path == str(root.session_dir):
            count["failed"] = True
            return OSError(errno.EIO, "injected EIO")
        return None

    ops.crash_when, ops.fail_when, ops.armed = crash_when, fail_when, True
    if case == "fence-failure":
        with pytest.raises(cp.PersistenceFailure):
            session.checkpoint(ended=ENDED)
        ops.armed = False
        assert (root.session_dir / st.FSYNC_FAILED).exists() and session.broken
        assert root.types()[-1] == "GC_DONE", "no follow-up CHECKPOINT after the failed fence"
        session.record_run_end(0, "finish")
        assert root.types()[-1] == "GC_DONE", "and no later effect"
        session.close()
        opening = root.start()
        assert (opening.classification, opening.stop) == ("A1", "fsync_failed_previous_run")
        return
    with pytest.raises(Crash):
        session.checkpoint(ended=ENDED)
    ops.armed = False
    session.close()
    after = [r for r in root.records() if r.seq > mark]
    assert [r.type_name for r in after if r.type_name != "LEDGER_HEADER"] == ["CHECKPOINT", "GC_INTENT", "GC_DONE"], "the follow-up frame is missing"
    spent = next(r for r in after if r.type_name == "GC_INTENT").payload
    spent_names = {cp.segment_name(n) for n in spent["segments"]} | set(spent["blobs"])
    meta = json.loads(root.file("run.json"))
    assert meta["ended"] == ENDED, "the interrupted call's CK5 (or the first checkpoint's) carried the same ended"
    if case == "crash-after-ck5-before-frame-write":
        assert meta["checkpoint"]["covers_seq"] == after[-1].seq, "the follow-up's CK5 named the GC pair"
    gc_pair = frames_after(root, after[0].seq)
    restart_ops, entries = CutOps(), []
    original = cs.Session.checkpoint

    def logged(self, *args, **kwargs):
        entries.append((counter(self), kwargs.get("ended", args[0] if args else None)))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(cs.Session, "checkpoint", logged)
    restart_ops.armed = True
    opening = root.start(ops=restart_ops, collect=True, records_max=2)  # [injected]
    restart_ops.armed = False
    monkeypatch.setattr(cs.Session, "checkpoint", original)
    assert opening.classification in ("A9", "A10"), opening  # not forced: GC leaves the conversation's hash unchanged
    assert entries and entries[0] == (gc_pair, None), "the outstanding GC work, then a replacement checkpoint without ended"
    assert not [e for e in restart_ops.log if e[0] == "unlink" and e[1] in spent_names], "the spent intent is not re-run"
    written = [r for r in root.records() if r.seq > after[-1].seq]
    assert 1 <= [r.type_name for r in written].count("CHECKPOINT") <= 2 and [r.type_name for r in written].count("GC_INTENT") <= 1
    assert "ended" not in json.loads(root.file("run.json")), "a later run's checkpoint is not a final one"
    underlying = list(opening.session.messages)
    opening.session.close()
    (root.session_dir / "conversation.json").write_bytes(b"\x00damaged in the temporary root")
    opening = root.start()
    assert (opening.classification, opening.stop) == ("A14", None), opening
    assert opening.session.messages == [*underlying, {"role": "user", "content": st.A14_NOTICE}], "the ordinary A14 notice"
    newest = [r for r in root.records() if r.type_name == "CHECKPOINT"][-1]
    assert hashlib.sha256(root.file("conversation.json")).hexdigest() == newest.payload["conv"]["sha256"]
    opening.session.close()


# ---------------------------------------------------------------------------
# A10: CKG holds at every new boundary
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("case", ["live-group", "startup-closes-group-first"])
def test_sv026_no_threshold_checkpoint_inside_a_group_or_with_a_queue(tmp_path, case):
    root = Root(tmp_path)
    session = establish(root)
    mark = origin(root)
    if case == "live-group":
        session.records_max = 1  # [injected]
        adoption = respond(session, calls=[("call_t", "read_file", '{"path":"x"}')])
        session.queue_message("user", "queued during the tool")
        (call,) = adoption.calls
        session.invoke(call, lambda: None)
        session.record_result(call, "returned", "done")
        session.unit_end()  # the queue is not empty: refused by its guard
        session.flush()
        kinds = types_after(root, mark)
        assert "CHECKPOINT" not in kinds and kinds[-1] == "MSG_APPEND"
        session.checkpoint()
        session.close()
        return
    partial_turn(session, 4)  # call 1 open
    session.close()
    opening = root.start(records_max=1)  # [injected]
    kinds = types_after(root, mark)
    assert "UNRUN" in kinds and "CHECKPOINT" in kinds, kinds
    assert kinds.index("UNRUN") < kinds.index("CHECKPOINT"), "the group is closed before the threshold checkpoint"
    assert opening.session.group is None
    opening.session.close()


# ---------------------------------------------------------------------------
# CB: the production metadata callback at startup
# ---------------------------------------------------------------------------
LEGACY_KEYS = ("agent", "name", "run", "turn", "model", "updated", "context_tokens", "context_window", "usage", "entry")


def test_sv026_a_startup_checkpoint_records_metadata_of_the_recovered_conversation(make_run, tmp_path, monkeypatch):
    first = make_run([reply("ok")], main="    context.ask('go')\n", root=tmp_path / "w")
    first.go()
    home = tmp_path / "w" / "home"
    session = st.open_session(home / "session", home).session  # a direct start: four large messages, then death
    for index in range(4):
        session.append_message("user", f"{index} " + TEXT)
    recovered = list(session.messages)
    session.close()

    second = make_run([], root=tmp_path / "w")
    instance = second.chassis
    seen_session = []
    original = instance._meta_fields

    def wrapped(*args, **kwargs):
        seen_session.append(instance.session)
        return original(*args, **kwargs)

    monkeypatch.setattr(instance, "_meta_fields", wrapped)
    opening = instance._open_session(bytes_max=20_000)  # [injected]
    assert (opening.classification, opening.stop) == ("A9", None)
    assert opening.session.messages == recovered
    scan = cp.scan_segments(cp.read_segments(home / "session" / "ledger"), opening.session.lineage_id)
    assert scan.records[-1].type_name == "CHECKPOINT", "the startup unit crossed"
    assert seen_session == [None], "the callback ran once, before Chassis adopted the session"
    meta = json.loads((home / "session" / "run.json").read_text())
    assert meta["context_tokens"] == chassis.estimate_tokens(recovered) != chassis.estimate_tokens([])
    assert all(key in meta for key in LEGACY_KEYS) and meta["turn"] == 0 and "ended" not in meta
    assert (home / "session" / "conversation.json").read_bytes() == rp.conversation_bytes(recovered)
    assert second.client.sent == [], "no request: the duty and client were never involved"
    opening.session.close()
