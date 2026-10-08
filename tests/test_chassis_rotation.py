"""SV027: segment rotation at every closed unit boundary (closes SV026's R-D).

Contract: SV-015 v2 section 1.4.6 ("rotate at a unit boundary when >= SEGMENT_MAX")
over section 1.4.1's units, with section 1.4.8's durability. As
`docs/planning-context/sv027/DESIGN.md` specifies (its L1-L5 qualifications
govern), every boundary that checks the checkpoint threshold also rotates a full
segment: startup (recovery and legacy import), each adopted note generation,
the drop notice, a file-edit adoption and both note drops. One closure writes
at most one threshold checkpoint, one G2 follow-up and one header; a header is
charged to the interval it opens and evaluated at the next closure; nothing
rotates inside a tool group or with queued messages.

Evidence kind: in-process simulation in temporary roots, as in
`test_chassis_recovery_live` (a "crash" abandons a session or raises `Crash`;
a "restart" calls `open_session` again), plus one real `Chassis.run()` against
a fake client (`test_chassis_termination.make_run`). Segment sizes and
thresholds other than the defaults are injected and labelled. A full segment
at the default 16 MiB is not built here: the rule is the same comparison.

Nothing here bounds a segment: what a full segment may still receive before
its closure (the rest of a unit, the closure's checkpoint and GC frames, a
startup core, crash loops) is not bounded, and MAX_SEGMENT_READ's slack is not
proved.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os

import chassis_persistence as cp
import chassis_replay as rp
import chassis_session as cs
import chassis_startup as st
import pytest
from test_chassis_bounds import frames
from test_chassis_recovery_live import (
    LINEAGE,
    Crash,
    FaultOps,
    Root,
    append_raw,
    damaged,
    establish,
    frame_after,
    respond,
    resume,
    turn7_open,
)
from test_chassis_termination import make_run, reply  # noqa: F401 -- make_run is a fixture

HEADER = "# Handoff"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def small_segments(monkeypatch, size: int = 1):
    """[injected] Every LedgerWriter built inside the block gets `segment_max = size` (the SMALL_SEGMENTS pattern)."""
    original = cp.LedgerWriter.__init__

    def init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.segment_max = size

    monkeypatch.setattr(cp.LedgerWriter, "__init__", init)
    try:
        yield
    finally:
        monkeypatch.setattr(cp.LedgerWriter, "__init__", original)


def once(predicate):
    """A fault predicate that matches its first matching call only (the FSYNC_FAILED marker can still be written)."""
    state = {"fired": False}

    def matches(path):
        if not state["fired"] and predicate(path):
            state["fired"] = True
            return True
        return False

    return matches


def after(root: Root, seq: int) -> list:
    return [record for record in root.records() if record.seq > seq]


def types_after(root: Root, seq: int) -> list[str]:
    return [record.type_name for record in after(root, seq)]


def counter(session) -> tuple[int, int]:
    return (session.since_records, session.since_bytes)


def segment_path(session_dir, number: int):
    return session_dir / "ledger" / cp.segment_name(number)


def pending(session, count: int) -> list[int]:
    gens = [session.write_note(f"note {index}", header=HEADER) for index in range(count)]
    session.checkpoint()
    return gens


def ledger_records(session_dir) -> list:
    segments = cp.read_segments(session_dir / "ledger")
    return list(cp.scan_segments(segments, st._segment_lineage(segments)).records)


# ---------------------------------------------------------------------------
# R1: every closed boundary rotates a full segment
# ---------------------------------------------------------------------------
R1_CASES = [
    "startup-a9-clean", "startup-after-intent", "legacy-import", "file-edit",
    "generations-and-notice", "drop-in-write_note", "drop-in-adopt_file_edit",
]


@pytest.mark.parametrize("case", R1_CASES)
def test_sv027_every_closed_boundary_rotates_a_full_segment(tmp_path, monkeypatch, case):
    root = Root(tmp_path)
    ledger = str(root.session_dir / "ledger")

    if case == "startup-a9-clean":
        session = establish(root)
        session.close()
        last = root.records()[-1]
        assert last.type_name == "CHECKPOINT"
        ops = FaultOps()
        with small_segments(monkeypatch):  # [injected] the inherited segment is full
            opening = root.start(ops=ops)
        assert opening.classification == "A9"
        written = after(root, last.seq)
        assert [r.type_name for r in written] == ["LEDGER_HEADER"], "the startup closure rotates the inherited full segment"
        (header,) = written
        assert (header.segment, header.seq, header.payload["first_seq"]) == (last.segment + 1, last.seq + 1, last.seq + 1)
        assert header.payload["prev_chain"] == last.chain
        assert counter(opening.session) == (1, frames(root)[header.seq][1]), "the header is charged to the new interval"
        old, new = str(segment_path(root.session_dir, last.segment)), str(segment_path(root.session_dir, header.segment))
        opened = ops.events.index(("open", new))
        assert ("fsync", old) in ops.events[:opened], "the inherited bytes are synced before rotating away (SV024)"
        assert ("sync_dir", ledger) in ops.events[opened:], "the new name is fenced"
        opening.session.close()
        again = root.start()  # defaults: a header-only segment is not full
        assert again.classification == "A9" and root.records()[-1].seq == header.seq, "nothing more is written"
        again.session.close()
        return

    if case == "startup-after-intent":
        session, turn = turn7_open(root)
        frame = frame_after(root, session, "INVOKING", {"turn_seq": turn, "call_index": 0})
        session.close()
        append_raw(root, damaged(frame))  # TC2: the start publishes RECOVERING
        last = root.records()[-1]
        ops, entries = FaultOps(), []
        original = cp.LedgerWriter.open_segment

        def watched(self, *args, **kwargs):
            entries.append({
                "recovering": (root.session_dir / st.RECOVERING).exists(),
                "acknowledged": (root.session_dir / st.ACKNOWLEDGED).exists(),
                "identity": cs.read_identity(root.session_dir, LINEAGE),
            })
            return original(self, *args, **kwargs)

        monkeypatch.setattr(cp.LedgerWriter, "open_segment", watched)
        with small_segments(monkeypatch):  # [injected]
            opening = root.start(ops=ops)
        assert opening.session is not None, opening
        written = after(root, last.seq)
        assert written and written[-1].type_name == "LEDGER_HEADER", "the recovery closure ends in one rotation"
        assert [r.type_name for r in written].count("LEDGER_HEADER") == 1
        core = written[:-1]
        assert core and all(r.segment == last.segment for r in core), "the recovery unit is never split"
        (entry,) = entries
        used = [r.payload["turn_seq"] for r in root.records() if r.type_name == "REQUEST_SENT"]
        assert not entry["recovering"] and not entry["acknowledged"], "rotation only after the transaction is retired"
        assert entry["identity"] is not None and entry["identity"] >= max([*used, opening.session.state.requests_next["turn_seq"]])
        trail = ops.events
        new = str(segment_path(root.session_dir, written[-1].segment))
        unlinked = trail.index(("unlink", str(root.session_dir / st.RECOVERING)))
        fenced = next(i for i in range(unlinked, len(trail)) if trail[i] == ("sync_dir", str(root.session_dir)))
        opened = trail.index(("open", new))
        assert unlinked < fenced < opened, "RECOVERING's removal is durable before the new segment exists"
        renames = [i for i, e in enumerate(trail) if e == ("rename", str(root.session_dir / cs.IDENTITY))]
        assert all(i < opened for i in renames), "an IDENTITY write, if one was needed, came first"
        opening.session.close()
        return

    if case == "legacy-import":
        legacy = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        (root.session_dir / "conversation.json").write_text(json.dumps(legacy, indent=2) + "\n")
        with small_segments(monkeypatch):  # [injected]; no legacy handoff; default thresholds
            opening = root.start()
        assert opening.classification == "A5"
        assert root.types() == ["LEDGER_HEADER", "LEGACY_IMPORT", "LEDGER_HEADER"], "the import closes with a rotation"
        imported = rp.conversation_bytes(legacy)
        (record,) = [r for r in root.records() if r.type_name == "LEGACY_IMPORT"]
        assert (root.session_dir / "blobs" / record.payload["blob"]).stat().st_size == len(imported)
        walked = frames(root)
        expected = (2, walked[2][1] + len(imported) + walked[3][1])  # L1: only H1 (the origin) is excluded
        assert counter(opening.session) == expected
        opening.session.close()
        again = root.start()  # default limits
        assert counter(again.session) == expected and len(root.types()) == 3, "the same counter, no further header"
        again.session.close()
        return

    session = establish(root)
    if case == "file-edit":
        session.close()
        (root.home / "HANDOFF.md").write_text("an agent's own edit\n")
        session = root.start().session
        session.writer.segment_max = 1  # [injected]
        mark = root.records()[-1].seq
        assert session.adopt_file_edit() is not None
        assert types_after(root, mark) == ["NOTE_WRITTEN", "LEDGER_HEADER"]
    elif case == "generations-and-notice":
        pending(session, rp.MAX_PENDING_NOTES)
        assert session.write_note("the seventeenth", header=HEADER) is None
        session.checkpoint()
        session.close()
        session = root.start().session
        session.writer.segment_max = 1  # [injected]
        mark = root.records()[-1].seq
        session.adopt_notes()
        assert types_after(root, mark) == ["MSG_APPEND", "LEDGER_HEADER"] * (rp.MAX_PENDING_NOTES + 1), (
            "each generation and the notice close with a rotation"
        )
        session.close()
        session = resume(root.start())
        notes = [r for r in root.records() if r.type_name == "MSG_APPEND" and r.payload.get("kind") == "note"]
        assert len(notes) == rp.MAX_PENDING_NOTES, "nothing adopted twice"
    elif case == "drop-in-write_note":
        pending(session, rp.MAX_PENDING_NOTES)
        session.writer.segment_max = 1  # [injected]
        mark = root.records()[-1].seq
        assert session.write_note("the seventeenth", header=HEADER) is None
        assert types_after(root, mark) == ["RECOVERY", "LEDGER_HEADER"]
    else:  # drop-in-adopt_file_edit
        pending(session, rp.MAX_PENDING_NOTES)
        session.close()
        (root.home / "HANDOFF.md").write_text("an agent's edit with no room left\n")
        session = root.start().session
        session.writer.segment_max = 1  # [injected]
        mark = root.records()[-1].seq
        assert session.adopt_file_edit() is None
        assert types_after(root, mark) == ["RECOVERY", "LEDGER_HEADER"]
    session.close()


# ---------------------------------------------------------------------------
# R2: one closure's bounded work
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("case", ["startup-crossing", "generation-crossing", "header-evaluated-next"])
def test_sv027_one_closure_writes_at_most_one_checkpoint_one_follow_up_and_one_header(tmp_path, monkeypatch, case):
    root = Root(tmp_path)
    session = establish(root)

    if case == "startup-crossing":
        orphan = session.writer.blobs.put(b"sv027 unreferenced evidence")  # collectible: no record or state names it
        for index in range(2):
            session.append_message("user", f"say {index}")
        session.close()
        last = root.records()[-1]
        with small_segments(monkeypatch):  # [injected] with records_max 2 and collection on
            opening = root.start(collect=True, records_max=2)
        assert opening.classification == "A9"
        assert types_after(root, last.seq) == ["CHECKPOINT", "GC_INTENT", "GC_DONE", "CHECKPOINT", "LEDGER_HEADER"], (
            "G2's follow-up, then exactly one rotation, and nothing after it"
        )
        (intent,) = [r for r in after(root, last.seq) if r.type_name == "GC_INTENT"]
        assert orphan in intent.payload["blobs"] and not (root.session_dir / "blobs" / orphan).exists()
        opening.session.close()
        return

    if case == "generation-crossing":
        pending(session, 3)
        session.close()
        session = root.start(collect=True).session
        session.records_max = 1  # [injected]
        session.writer.segment_max = 1  # [injected]
        # Logged as written, from the adoption entry (no startup closure is
        # counted): collection here legitimately unlinks earlier generations'
        # segments, so a later read of the ledger cannot show the sequence.
        written: list[str] = []
        real_append, real_open = cp.LedgerWriter.append, cp.LedgerWriter.open_segment

        def append(self, type_name, payload):
            record = real_append(self, type_name, payload)
            written.append(type_name)
            return record

        def open_segment(self, *args, **kwargs):
            real_open(self, *args, **kwargs)
            written.append("LEDGER_HEADER")

        monkeypatch.setattr(cp.LedgerWriter, "append", append)
        monkeypatch.setattr(cp.LedgerWriter, "open_segment", open_segment)
        session.adopt_notes()
        monkeypatch.setattr(cp.LedgerWriter, "append", real_append)
        monkeypatch.setattr(cp.LedgerWriter, "open_segment", real_open)
        closures, current = [], []
        for name in written:
            if name == "MSG_APPEND" and current:
                closures.append(current)
                current = []
            current.append(name)
        closures.append(current)
        assert len(closures) == 3 and written.count("LEDGER_HEADER") == 3
        for closure in closures:
            assert closure[0] == "MSG_APPEND" and closure[-1] == "LEDGER_HEADER" and closure.count("LEDGER_HEADER") == 1
            assert 1 <= closure.count("CHECKPOINT") <= 2 and closure.count("GC_INTENT") <= 1
        assert not any(a == b == "LEDGER_HEADER" for a, b in zip(written, written[1:]))
        session.close()
        return

    # header-evaluated-next
    session.append_message("user", "one")
    session.close()
    say = root.records()[-1]
    with small_segments(monkeypatch):  # [injected] with records_max 2
        opening = root.start(records_max=2)
    session = opening.session
    assert types_after(root, say.seq) == ["LEDGER_HEADER"], "rotated; the header does not trigger a checkpoint itself"
    walked = frames(root)
    assert counter(session) == (2, walked[say.seq][1] + walked[say.seq + 1][1]), "over, evaluated at the next closure"
    session.writer.segment_max = cp.SEGMENT_MAX
    session.append_message("user", "two")
    assert types_after(root, say.seq) == ["LEDGER_HEADER", "MSG_APPEND", "CHECKPOINT"]
    session.close()


# ---------------------------------------------------------------------------
# R3: no rotation inside a group or with queued messages
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("case", ["drop-inside-group", "queued-messages"])
def test_sv027_no_rotation_inside_a_group_or_with_a_queue(tmp_path, case):
    root = Root(tmp_path)
    session = establish(root)
    if case == "drop-inside-group":
        pending(session, rp.MAX_PENDING_NOTES)
    session.writer.segment_max = 1  # [injected]
    mark = root.records()[-1].seq
    adoption = respond(session, calls=[("call_t", "read_file", '{"path":"x"}')])
    (call,) = adoption.calls
    if case == "drop-inside-group":
        assert session.write_note("in a tool", header=HEADER) is None  # the drop, inside the open group
        session.invoke(call, lambda: None)
        session.record_result(call, "returned", "done")
        assert "LEDGER_HEADER" not in types_after(root, mark), "no rotation inside the group"
        session.checkpoint()  # the turn's own end
        written = types_after(root, mark)
        assert written.count("LEDGER_HEADER") == 1 and written[-2:] == ["CHECKPOINT", "LEDGER_HEADER"]
        assert written.index("RECOVERY") < written.index("DONE")
    else:
        session.queue_message("user", "queued")
        session.invoke(call, lambda: None)
        session.record_result(call, "returned", "done")
        assert session.replay.group is None and session.queue
        (root.home / "HANDOFF.md").write_text("an agent's edit\n")
        before = root.records()[-1].seq
        assert session.adopt_file_edit() is not None
        assert types_after(root, before) == ["NOTE_WRITTEN"], "the queue guard: no rotation before the flush"
        session.flush()
        session.checkpoint()
        assert types_after(root, before) == ["NOTE_WRITTEN", "MSG_APPEND", "CHECKPOINT", "LEDGER_HEADER"]
    session.close()


# ---------------------------------------------------------------------------
# R4: at the default segment size the new boundaries add no event
# ---------------------------------------------------------------------------
def test_sv027_a_nonfull_segment_adds_no_event_at_the_new_boundaries(tmp_path, monkeypatch):
    root = Root(tmp_path)
    session = establish(root)
    pending(session, 2)
    session.close()
    (root.home / "HANDOFF.md").write_text("an agent's edit\n")
    last = root.records()[-1]
    names = sorted(p.name for p in (root.session_dir / "ledger").glob("*.svl"))
    ops, windows = FaultOps(), []
    original = cp.LedgerWriter.rotate_if_full

    def watched(self):
        start = len(ops.events)
        result = original(self)
        windows.append((result, ops.events[start:]))
        return result

    monkeypatch.setattr(cp.LedgerWriter, "rotate_if_full", watched)
    session = root.start(ops=ops).session  # defaults
    assert session.adopt_file_edit() is not None
    session.adopt_notes()
    assert len(windows) == 5, "the startup closure, the file edit and three generations each check rotation"
    assert all(result is False and events == [] for result, events in windows), "a non-full check does no I/O"
    assert types_after(root, last.seq) == ["NOTE_WRITTEN", "MSG_APPEND", "MSG_APPEND", "MSG_APPEND"]
    assert sorted(p.name for p in (root.session_dir / "ledger").glob("*.svl")) == names
    inherited = str(segment_path(root.session_dir, last.segment))
    assert [e for e in ops.events if e[0] == "open" and e[1].endswith(".svl")] == [("open", inherited)]
    assert ops.before(("fenced", str(root.session_dir)), ("open", inherited))
    assert ops.before(("fenced", str(root.session_dir / "ledger")), ("open", inherited))
    session.close()


# ---------------------------------------------------------------------------
# R5: the new failure and crash compositions
# ---------------------------------------------------------------------------
R5_CASES = [
    "startup-inherited-fsync-eio", "startup-ledger-fence-eio", "startup-name-lost-is-recreated",
    "generations-fence-eio-chassis", "generations-crash-converges",
]
MARKED_MAIN = '    import os\n    open(os.path.join(os.environ["WORK_DIR"], "main-entered"), "w").close()\n    context.ask("go")\n'
MARKED_BOOTSTRAP = (
    "def bootstrap(context):\n    import os\n"
    '    open(os.path.join(os.environ["WORK_DIR"], "bootstrap-entered"), "w").close()\n    return None\n'
)


@pytest.mark.parametrize("case", R5_CASES)
def test_sv027_rotation_failures_and_crashes_at_the_new_boundaries(tmp_path, monkeypatch, make_run, case):
    if case == "generations-fence-eio-chassis":
        _generations_fence_eio_chassis(tmp_path, monkeypatch, make_run)
        return
    root = Root(tmp_path)
    ledger = str(root.session_dir / "ledger")
    session = establish(root)

    if case == "generations-crash-converges":
        gens = pending(session, 3)
        session.close()
        ops = FaultOps()
        session = root.start(ops=ops).session
        session.writer.segment_max = 1  # [injected]
        mark = root.records()[-1].seq
        new = segment_path(root.session_dir, session.writer.segment_no + 1)
        ops.faults.append(("sync_dir", once(lambda p: p == ledger and new.exists()), Crash()))
        with pytest.raises(Crash):  # process death at the fence of the header after generation 1
            session.adopt_notes()
        assert types_after(root, mark) == ["MSG_APPEND", "LEDGER_HEADER"]
        session.close()
        for _restart in range(2):
            session = resume(root.start())
            adopted = [r.payload["gen"] for r in root.records() if r.type_name == "MSG_APPEND" and r.payload.get("kind") == "note"]
            assert adopted == gens, "each generation adopted exactly once"
            assert (session.state.notes_adopted_through, session.state.notes_pending) == (gens[-1], [])
            session.close()
        return

    session.close()
    last = root.records()[-1]
    old, new = segment_path(root.session_dir, last.segment), segment_path(root.session_dir, last.segment + 1)
    ops, seen = FaultOps(), {}
    original = cp.LedgerWriter.open_segment

    def armed(self, *args, **kwargs):
        seen["inherited"] = self.inherited
        if case == "startup-inherited-fsync-eio":
            ops.faults.append(("fsync", once(lambda p: p == str(old)), OSError(errno.EIO, "injected EIO")))
        elif case == "startup-ledger-fence-eio":
            ops.faults.append(("sync_dir", once(lambda p: p == ledger and new.exists()), OSError(errno.EIO, "injected EIO")))
        else:
            ops.faults.append(("sync_dir", once(lambda p: p == ledger and new.exists()), Crash()))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(cp.LedgerWriter, "open_segment", armed)
    expected = Crash if case == "startup-name-lost-is-recreated" else cp.PersistenceFailure
    with small_segments(monkeypatch), pytest.raises(expected):  # [injected] the inherited segment is full
        root.start(ops=ops)
    monkeypatch.setattr(cp.LedgerWriter, "open_segment", original)
    assert seen["inherited"] is True, "the cut is in the startup rotation of the inherited segment"

    if case == "startup-inherited-fsync-eio":
        assert not new.exists() and root.records()[-1].seq == last.seq, "nothing was created or written"
    elif case == "startup-ledger-fence-eio":
        written = after(root, last.seq)
        assert [(r.type_name, r.segment, r.seq) for r in written] == [("LEDGER_HEADER", last.segment + 1, last.seq + 1)]
    if case != "startup-name-lost-is-recreated":
        assert (root.session_dir / st.FSYNC_FAILED).exists()
        opening = root.start()
        assert (opening.classification, opening.stop) == ("A1", "fsync_failed_previous_run")
        return

    # startup-name-lost-is-recreated: the header was durable, its name was not fenced
    assert not (root.session_dir / st.FSYNC_FAILED).exists()
    (lost,) = after(root, last.seq)
    os.unlink(new)  # simulated M-2: the unfenced name vanished
    assert root.records()[-1].seq == last.seq
    with small_segments(monkeypatch):  # [injected]
        opening = root.start()
    assert opening.classification == "A9"
    (header,) = after(root, last.seq)
    assert header.type_name == "LEDGER_HEADER" and (header.segment, header.seq) == (lost.segment, lost.seq)
    assert header.payload == lost.payload, "recreated with the same first_seq and prev_chain"
    seqs = [r.seq for r in root.records()]
    assert seqs == list(range(seqs[0], seqs[-1] + 1))
    opening.session.close()


def _generations_fence_eio_chassis(tmp_path, monkeypatch, make_run):
    """L3: a real Chassis.run whose adoption rotation fails at its ledger/ fence makes no request and runs no main."""
    base = tmp_path / "w"
    first = make_run([reply("ok")], main="    context.ask('go')\n", root=base)
    assert first.go() == 0
    home = base / "home"
    session_dir = home / "session"
    assert not [r for r in ledger_records(session_dir) if r.type_name == "NOTE_WRITTEN"], "a main return writes no note"
    direct = st.open_session(session_dir, home).session  # two pending generations, checkpointed
    gens = pending(direct, 2)
    through = direct.state.notes_adopted_through
    direct.close()
    offset = len(first.lifecycle())

    second = make_run([], main=MARKED_MAIN, extra=MARKED_BOOTSTRAP, root=base)
    ledger = str(session_dir / "ledger")
    pre = ledger_records(session_dir)[-1].seq
    state = {"armed": False, "reached": False}
    real_adopt, real_sync = cs.Session.adopt_notes, cp.DurableOps.sync_dir

    def adopt_notes(self):
        state.update(entry=ledger_records(session_dir)[-1].seq, segment=self.writer.segment_no,
                     pending=[e["gen"] for e in self.state.notes_pending], through=self.state.notes_adopted_through)
        state["armed"] = True
        try:
            return real_adopt(self)
        finally:
            state["armed"] = False

    def sync_dir(self, path):
        armed = state["armed"] and not state["reached"] and str(path) == ledger
        if armed and segment_path(session_dir, state["segment"] + 1).exists():
            state["reached"] = True
            raise OSError(errno.EIO, "injected EIO at the adoption header's ledger/ fence")
        return real_sync(self, path)

    monkeypatch.setattr(cs.Session, "adopt_notes", adopt_notes)
    monkeypatch.setattr(cp.DurableOps, "sync_dir", sync_dir)
    with small_segments(monkeypatch), pytest.raises(cp.PersistenceFailure):  # [injected] every writer
        second.go()
    monkeypatch.setattr(cp.DurableOps, "sync_dir", real_sync)
    assert state["reached"], "the cut was the adoption header's fence"
    assert (state["pending"], state["through"]) == (gens, through)
    records = ledger_records(session_dir)
    entry = [r for r in records if r.seq > state["entry"]]
    assert [r.type_name for r in entry] == ["MSG_APPEND", "LEDGER_HEADER"] and entry[0].payload["gen"] == gens[0]
    assert not [r for r in records if r.type_name == "MSG_APPEND" and r.payload.get("gen") in gens[1:]], "later generations stay pending"
    newest = [r for r in records if r.type_name == "CHECKPOINT"][-1]
    assert [e["gen"] for e in newest.payload["state"]["notes"]["pending"]] == gens
    assert not [r for r in records if r.seq > pre and r.type_name in ("REQUEST_SENT", "INVOKING", "CHECKPOINT", "RUN_END")]
    assert second.client.sent == []
    work = base / "work"
    assert not (work / "main-entered").exists() and not (work / "bootstrap-entered").exists()
    events = [e["event"] for e in second.lifecycle()[offset:]]
    assert "run_start" in events and "runtime_bound" in events
    assert not {"run_resumed", "run_fresh", "turn", "run_end"} & set(events)
    assert (session_dir / st.FSYNC_FAILED).exists()
    opening = st.open_session(session_dir, home)
    assert (opening.classification, opening.stop) == ("A1", "fsync_failed_previous_run")
