"""Checkpoint-safe collection (SV-022): C-G1, O2-1, the reference union, O2-2 after collection, O2-4.

Evidence kind: in-process simulation in temporary roots, as in
`test_chassis_recovery_live`. A "crash" raises `Crash` from an injected
filesystem call -- process death: completed calls stay (M-1) -- and a
"restart" calls `open_session` again. Host loss (M-2) is only *simulated* by
`lose_unsynced`: segment bytes no returned fsync covered are cut back, and
unlinks no returned directory fsync covered are undone (all of them, or a
chosen subset). Collection is real -- files are unlinked -- and every
"absent" below looks at the directory or the scanned ledger, never at a
helper's set. Segments are made tiny (`segment_max = 1`: rotation at every
unit boundary) so whole segments become eligible within a few checkpoints.

Not a power-loss, kernel or storage experiment; no provider; no real session.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path

import chassis_envelope as envelope
import chassis_gc as gc
import chassis_persistence as cp
import chassis_replay as rp
import chassis_session as cs
import chassis_startup as st
import pytest
from test_chassis_checkpoint import crash_after_ck4
from test_chassis_durability import Crash
from test_chassis_recovery_live import BASE, LINEAGE, READ, UNRUN, Root, T, partial_turn, r7, respond, resume

HEADER = "# Handoff"


def note(text: str) -> str:
    return rp.NOTE_PREFIX + f"{HEADER}\n\n{text}\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
def start(root: Root, **kwargs) -> st.Opening:
    """A start with collection on and one-unit segments."""
    opening = root.start(collect=True, **kwargs)
    if opening.session is not None:
        opening.session.writer.segment_max = 1
    return opening


def begin(root: Root, **kwargs):
    """A new lineage: OPENING (C1, no previous base), then a turn answering "ok" (C2, the first collection)."""
    opening = start(root, **kwargs)
    assert opening.classification == "A4", opening
    session = resume(opening)
    respond(session, content="ok")
    session.checkpoint()
    assert session.messages == BASE
    return session


def tool_turn(session, result: str, *, content: str = ""):
    """A complete turn with one tool call, then its checkpoint (and collection)."""
    adoption = respond(session, calls=[("call_t", "read_file", '{"path":"x"}')], content=content)
    for call in adoption.calls:
        session.invoke(call, lambda: None)
        session.record_result(call, "returned", result)
    session.checkpoint()
    return adoption


def segments(root: Root) -> list[int]:
    return sorted(int(path.stem) for path in (root.session_dir / "ledger").glob("*.svl"))


def blobs(root: Root) -> set[str]:
    return set(gc.blob_names(root.session_dir / "blobs"))


def of_type(root: Root, name: str) -> list:
    return [record for record in root.records() if record.type_name == name]


def inventory(root: Root) -> dict:
    return {"segments": set(segments(root)), "blobs": blobs(root)}


def protected(root) -> dict:
    """The files collection must never touch, by content (`root`: a Root or a Session)."""
    session_dir, home = (root.session_dir, getattr(root, "home", None) or root.home_dir)
    files = [session_dir / name for name in ("IDENTITY", "run.json", "conversation.json", "conversation.prev.json")]
    files.append(home / "HANDOFF.md")
    return {path.name: (path.read_bytes() if path.exists() else None) for path in files}


def append_record(root: Root, type_name: str, payload: dict):
    """A chain-valid record written directly after the ledger's end (the session already closed)."""
    scan = cp.scan_segments(cp.read_segments(root.session_dir / "ledger"), LINEAGE)
    writer = cp.LedgerWriter.continue_after(root.session_dir, LINEAGE, scan)
    record = writer.append(type_name, payload)
    writer.close()
    return record


def last_frame_type(path: str) -> str | None:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    last = data.rstrip(b"\n").rsplit(b"\n", 1)[-1]
    return last[18:20].decode("ascii", "replace") if len(last) >= 20 else None


class CutOps(cp.DurableOps):
    """Real filesystem calls. Once armed, each mutating call is logged, and one may be a process death.

    It also remembers what M-2 would let a host loss take back: segment bytes
    after the last returned fsync, and unlinks after the last returned fsync of
    their directory (`lose_unsynced` applies that).
    """

    def __init__(self, durable: dict | None = None) -> None:
        # `durable`: another process's watermark, carried across a process death
        # (SV022-01) -- readable bytes are not promoted to durable by reopening.
        self.paths: dict[int, str] = {}
        self.armed = False
        self.log: list[tuple] = []  # (call, file name, frame type) while armed
        self.crash_at: int | None = None  # process death before armed call number n
        self.crash_when = None  # or before the first armed call matching (call, path, frame)
        self.fail_when = None  # (call, path, frame) -> OSError to raise instead, or None
        self.durable: dict[str, int] = {} if durable is None else durable
        self.unfenced: dict[str, list] = {}

    def _step(self, call, path, frame=None) -> None:
        if not self.armed:
            return
        path = str(path or "")
        if self.crash_at is not None and len(self.log) == self.crash_at:
            raise Crash()
        if self.crash_when is not None and self.crash_when(call, path, frame):
            raise Crash()
        self.log.append((call, Path(path).name, frame))
        if self.fail_when is not None:
            error = self.fail_when(call, path, frame)
            if error is not None:
                raise error

    def open(self, path, flags, mode=0o644):
        self._step("open", path)
        fd = super().open(path, flags, mode)
        self.paths[fd] = str(path)
        if str(path).endswith(".svl"):
            self.durable.setdefault(str(path), os.fstat(fd).st_size)
        return fd

    def write(self, fd, data):
        path = self.paths.get(fd, "")
        frame = bytes(data[18:20]).decode("ascii", "replace") if path.endswith(".svl") and len(data) >= 20 else None
        self._step("write", path, frame)
        return super().write(fd, data)

    def fsync(self, fd):
        path = self.paths.get(fd, "")
        self._step("fsync", path, last_frame_type(path) if path.endswith(".svl") else None)
        super().fsync(fd)
        if path.endswith(".svl"):
            self.durable[path] = os.path.getsize(path)

    def close(self, fd):
        self.paths.pop(fd, None)
        super().close(fd)

    def rename(self, source, target):
        self._step("rename", target)
        super().rename(source, target)

    def link(self, source, target):
        self._step("link", target)
        super().link(source, target)

    def unlink(self, path):
        self._step("unlink", path)
        data = Path(path).read_bytes() if Path(path).is_file() else None
        super().unlink(path)
        if data is not None:
            self.unfenced.setdefault(str(Path(path).parent), []).append((str(path), data))

    def truncate(self, path, length):
        self._step("truncate", path)
        super().truncate(path, length)

    def mkdir(self, path):
        self._step("mkdir", path)
        super().mkdir(path)

    def sync_dir(self, path):
        self._step("sync_dir", path)
        super().sync_dir(path)
        self.unfenced[str(path)] = []


def lose_unsynced(ops: CutOps, restore: str) -> None:
    """Simulated host loss (M-2): unsynced segment bytes are lost; unfenced unlinks are undone ("all" or "alternate")."""
    for path, size in ops.durable.items():
        if os.path.exists(path) and os.path.getsize(path) > size:
            os.truncate(path, size)
    for _directory, items in ops.unfenced.items():
        for path, data in items if restore == "all" else items[::2]:
            Path(path).write_bytes(data)


def collection_ready(path: Path, ops: CutOps | None = None, **kwargs):
    """A session whose next checkpoint collects several segments and blobs in one intent.

    Collection is held back for three tool turns, so their segments and DONE
    blobs accumulate; two orphan blobs are never referenced at all; a pending
    note's blob is retained by state.
    """
    path.mkdir(parents=True, exist_ok=True)
    root = Root(path)
    session = begin(root, **({"ops": ops} if ops else {}), **kwargs)
    session.write_note("pending", header=HEADER)
    session.collect = False
    for index in range(3):
        tool_turn(session, f"result {index}")
    orphans = [session.writer.blobs.put(f"orphan {index}".encode()) for index in range(2)]
    session.collect = True
    session.append_message("user", "collect now")
    return root, session, orphans


def collect_with(session, ops: CutOps) -> None:
    """The next checkpoint, with every call of its collection (and the rotation after it) armed.

    `ops.kept`: the protected files as CK6 left them, when collection begins.
    """
    original = session._collect

    def armed(newest):
        ops.kept = protected(session)
        ops.armed = True
        original(newest)

    session._collect = armed
    try:
        session.checkpoint()
    finally:
        ops.armed = False


def converge(root: Root) -> dict:
    """Two restarts: both continue; the second writes and removes nothing."""
    first = start(root)
    assert first.stop is None, first
    first.session.close()
    count, after = len(root.records()), inventory(root)
    second = start(root)
    assert second.stop is None, second
    second.session.close()
    assert len(root.records()) == count, "the second restart wrote records"
    assert inventory(root) == after, "the second restart removed something"
    return after


def our_intent(root: Root, payload: dict):
    found = [r for r in root.records() if r.type_name == "GC_INTENT" and r.payload == payload]
    assert len(found) <= 1
    return found[0] if found else None


def assert_converged(root: Root, payload: dict, before: dict, after: dict, kept: dict, label: str) -> None:
    removed_segments = before["segments"] - after["segments"]
    removed_blobs = before["blobs"] - after["blobs"]
    assert removed_segments <= set(payload["segments"]), f"{label}: a segment outside the intent was removed"
    assert removed_blobs <= set(payload["blobs"]), f"{label}: a blob outside the intent was removed"
    assert protected(root) == kept, f"{label}: a protected file changed"
    intent = our_intent(root, payload)
    if intent is None:
        assert not removed_segments and not removed_blobs, f"{label}: items removed without a surviving intent"
        return
    dones = [r for r in root.records() if r.type_name == "GC_DONE" and r.payload["intent_seq"] == intent.seq]
    assert len(dones) == 1, f"{label}: {len(dones)} GC_DONE records for the intent"
    assert not set(payload["segments"]) & after["segments"], f"{label}: a listed segment survived"
    assert not set(payload["blobs"]) & after["blobs"], f"{label}: a listed blob survived"


# ---------------------------------------------------------------------------
# C-G1 and O2-1: notes after their records are collected
# ---------------------------------------------------------------------------
def adopt_n1_and_collect(root: Root):
    """N1 written, adopted by the next run, then enough checkpoints to unlink both records' segments."""
    session = begin(root)
    session.write_note("N1", header=HEADER)
    (written,) = of_type(root, "NOTE_WRITTEN")
    session.checkpoint()
    session.close()
    opening = start(root)
    opening.session.adopt_notes()
    (adopted,) = [r for r in of_type(root, "MSG_APPEND") if r.payload["kind"] == "note"]
    session = resume(opening)
    assert [m["content"] for m in session.messages].count(note("N1")) == 1
    for index in range(4):
        session.append_message("user", f"later {index}")
        session.checkpoint()
    return session, written, adopted


def test_c_g1_an_adopted_note_is_never_readopted_after_its_records_are_collected(tmp_path):
    root = Root(tmp_path)
    session, written, adopted = adopt_n1_and_collect(root)
    assert not {written.segment, adopted.segment} & set(segments(root)), "both records' segments were unlinked"
    assert not {written.seq, adopted.seq} & {r.seq for r in root.records()}
    assert written.payload["blob"] not in blobs(root), "the note's blob was collected too: only state remembers"
    assert (root.home / "HANDOFF.md").read_text() == f"{HEADER}\n\nN1\n", "the mirror is still on disk"
    session.replace_history([{"role": "user", "content": "OPENING"}])
    assert note("N1") not in [m["content"] for m in session.messages]
    session.close()
    for _run in range(2):
        session = resume(start(root))
        assert note("N1") not in [m["content"] for m in session.messages], "re-adopted after collection (R11-3)"
        assert (session.state.notes_adopted_through, session.state.notes_pending) == (1, [])
        session.close()
    assert not of_type(root, "NOTE_WRITTEN"), "the mirror was not taken for a file edit"


def test_c_g1_negative_control_state_derived_from_surviving_records_readopts(tmp_path, monkeypatch):
    """Control: restore the mirror facts only from surviving NOTE_WRITTEN records (none survive)."""
    root = Root(tmp_path)
    session, _written, _adopted = adopt_n1_and_collect(root)
    session.replace_history([{"role": "user", "content": "OPENING"}])
    session.close()
    real = rp.SessionState.from_wire

    def from_surviving_records(wire):
        state = real(wire)
        state.adopted_mirror_sha256 = state.handoff_md_sha256 = None  # nothing left to derive them from
        return state

    monkeypatch.setattr(rp.SessionState, "from_wire", staticmethod(from_surviving_records))
    session = resume(start(root))
    assert any(m["content"].endswith(f"{HEADER}\n\nN1\n") for m in session.messages if m["role"] == "user"), (
        "the control should re-adopt N1: the fixture distinguishes state from surviving records"
    )


def test_o2_1_pending_generations_outlive_their_collected_records(tmp_path):
    root = Root(tmp_path)
    session = begin(root)
    session.write_note("N1", header=HEADER)
    session.checkpoint()
    session.close()
    session = resume(start(root))  # adopted_through = 1
    gens = [session.write_note(text, header=HEADER) for text in ("N2", "N3", "N2")]
    assert gens == [2, 3, 4]
    written = [r for r in of_type(root, "NOTE_WRITTEN") if r.payload["gen"] in gens]
    assert len(written) == 3
    for index in range(4):
        session.append_message("user", f"turn {index}")
        session.checkpoint()
    newest = of_type(root, "CHECKPOINT")[-1]
    pending = newest.payload["state"]["notes"]["pending"]
    assert [entry["gen"] for entry in pending] == [2, 3, 4]
    assert not {r.seq for r in written} & {r.seq for r in root.records()}, "NOTE_WRITTEN{2,3,4} are gone"
    assert not {r.segment for r in written} & set(segments(root))
    assert {entry["blob"] for entry in pending} <= blobs(root), "every pending generation's blob is kept"
    assert pending[0]["blob"] == pending[2]["blob"] != pending[1]["blob"], "equal text, one blob, two generations"
    session.close()
    second = resume(start(root))
    contents = [m["content"] for m in second.messages]
    assert [c for c in contents if c.startswith(rp.NOTE_PREFIX)][-3:] == [note("N2"), note("N3"), note("N2")]
    assert (contents.count(note("N2")), contents.count(note("N3"))) == (2, 1)
    assert (second.state.notes_adopted_through, second.state.notes_pending) == (4, [])
    second.close()
    third = resume(start(root))
    contents = [m["content"] for m in third.messages]
    assert (contents.count(note("N2")), contents.count(note("N3"))) == (2, 1), "a third run adopts neither"


# ---------------------------------------------------------------------------
# The reference union (v2 1.4.5), not newest-only
# ---------------------------------------------------------------------------
def union_scenario(root: Root):
    """Each blob kind at C4's collection: only C_p.state, only the interval, a retained original, an orphan."""
    caps = envelope.Caps(content=128)
    session = begin(root, caps=caps)
    tool_turn(session, "interval A", content="A" * 300)  # C3: original OA retained, DONE blob DA
    orphan = session.writer.blobs.put(b"orphan")  # never referenced
    tool_turn(session, "interval B", content="B" * 300)  # C4: OB evicts OA (FIFO of 1); DONE blob DB
    ids = {"OA": sha(b"A" * 300), "DA": sha(b"interval A"), "OB": sha(b"B" * 300), "DB": sha(b"interval B"), "orphan": orphan}
    return session, caps, ids


def test_reference_union_keeps_each_kind_until_it_is_eligible_in_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(rp, "ORIGINALS_MAX_COUNT", 1)
    root = Root(tmp_path)
    session, caps, ids = union_scenario(root)
    c3, c4 = of_type(root, "CHECKPOINT")[-2:]
    assert c4.payload["prev"]["checkpoint_seq"] == c3.seq
    assert ids["OA"] in c3.payload["state"]["blobs_live"] and ids["OA"] not in c4.payload["state"]["blobs_live"]
    assert ids["OB"] in c4.payload["state"]["blobs_live"]
    present = blobs(root)
    assert {ids["OA"], ids["DB"], ids["OB"]} <= present, "C_p.state, the interval and the retained original are kept"
    assert ids["orphan"] not in present and ids["DA"] not in present, "the orphan and a pre-floor DONE blob are collected"
    # A suffix blob: turn 9 runs its call, then the process dies before any checkpoint.
    adoption = respond(session, calls=[("call_s", "read_file", '{"path":"s"}')])
    session.invoke(adoption.calls[0], lambda: None)
    session.record_result(adoption.calls[0], "returned", "suffix S")
    session.close()
    ids["DS"] = sha(b"suffix S")
    records = root.records()
    basis = gc.retained_basis(records, [r for r in records if r.type_name == "CHECKPOINT"][-1])
    assert {ids["OA"], ids["DB"], ids["OB"], ids["DS"]} <= basis.retained, "C_n.state | C_p.state | interval | suffix"
    assert ids["DS"] in blobs(root)
    # The next checkpoint advances the floor past the interval: OA and DB become eligible, DS is interval now.
    session = resume(start(root, caps=caps))
    present = blobs(root)
    assert {ids["DS"], ids["OB"]} <= present and not {ids["OA"], ids["DB"]} & present
    session.append_message("user", "one more")
    session.checkpoint()
    present = blobs(root)
    assert ids["DS"] not in present and ids["OB"] in present, "DS in its turn; the retained original stays"


def test_reference_union_negative_control_newest_only_loses_the_previous_base(tmp_path, monkeypatch):
    """Control: keep refs(C_n.state) and the suffix only. C_p's original and the interval blob go, and A14 cannot recover."""
    monkeypatch.setattr(rp, "ORIGINALS_MAX_COUNT", 1)
    real = gc.retained_basis

    def newest_only(records, newest):
        basis = real(records, newest)
        if basis is None:
            return None
        retained = set(newest.payload["state"]["blobs_live"])
        for record in records:
            if record.seq > newest.payload["covers_seq"]:
                retained |= rp.record_refs(record)
        return gc.Basis(basis.newest, basis.previous, basis.floor, frozenset(retained), basis.keep_segment)

    monkeypatch.setattr(gc, "retained_basis", newest_only)
    root = Root(tmp_path)
    session, caps, ids = union_scenario(root)
    present = blobs(root)
    assert ids["OA"] not in present and ids["DB"] not in present, "the control drops C_p.state and the interval"
    session.close()
    (root.session_dir / "conversation.json").write_bytes(b"\x00garbage")
    opening = start(root, caps=caps)
    assert opening.stop == "replay_mismatch", "previous-base replay reads DB, which the control removed"


# ---------------------------------------------------------------------------
# O2-2: previous-base recovery after actual collection, and after A10/A14/A11
# ---------------------------------------------------------------------------
def assert_a14_recovers_exactly(root: Root, session, *, caps=None) -> None:
    """Turn N: request, response (2 calls), call 0 invoked and done; crash; the newest file unreadable."""
    expected = list(session.messages)
    turn = session.state.requests_next["turn_seq"]
    partial_turn(session, 4)
    session.close()
    records = root.records()
    newest = [r for r in records if r.type_name == "CHECKPOINT"][-1]
    prev = newest.payload["prev"]
    assert 0 not in segments(root) and records[0].seq > 1, "segment 0 and older records are physically gone"
    assert records[0].seq <= prev["covers_seq"] + 1, "the true previous base's whole interval is retained"
    assert sha(root.file("conversation.prev.json")) == prev["conv_sha256"]
    invoking = len(of_type(root, "INVOKING"))
    (root.session_dir / "conversation.json").write_bytes(b"\x00garbage")
    opening = start(root, **({"caps": caps} if caps else {}))
    assert opening.classification == "A14", opening
    assert opening.session.messages == [
        *expected, r7(turn), T("call_a", "read_file", READ), T("call_b", "write_file", UNRUN),
        {"role": "user", "content": st.A14_NOTICE},
    ]
    assert json.loads(root.file("conversation.json")) == expected, "the newest checkpoint's verified bytes"
    assert len(of_type(root, "INVOKING")) == invoking, "nothing was invoked again"
    opening.session.close()


def test_o2_2_previous_base_recovery_after_actual_collection(tmp_path):
    root = Root(tmp_path)
    session = begin(root)
    for index in range(3):
        tool_turn(session, f"r{index}")
    assert of_type(root, "GC_DONE"), "collection ran"
    assert_a14_recovers_exactly(root, session)


@pytest.mark.parametrize("transition", ["a10", "a14", "a11"])
def test_o2_2_previous_base_recovery_after_collection_following_a_corrected_transition(tmp_path, transition):
    root = Root(tmp_path)
    session = begin(root)
    for index in range(2):
        tool_turn(session, f"before {index}")
    if transition == "a10":
        session.append_message("user", "appended before the interrupted checkpoint")
        crash_after_ck4(root, session)
        opening = start(root)
    elif transition == "a14":
        session.close()
        (root.session_dir / "conversation.json").write_bytes(b"damaged")
        opening = start(root)
    else:
        session.close()
        (root.session_dir / "conversation.json").write_text(json.dumps([{"role": "user", "content": "NEW"}], indent=2) + "\n")
        opening = start(root)
    assert opening.classification == transition.upper(), opening
    session = opening.session
    tool_turn(session, "after 0")
    checkpoints = of_type(root, "CHECKPOINT")
    if transition == "a11":
        # SV021-02: the first checkpoint after an external edit names the
        # older bound base in .prev.json, not the CHECKPOINT record before it.
        assert checkpoints[-1].payload["prev"]["checkpoint_seq"] < checkpoints[-2].seq
        assert of_type(root, "GC_INTENT")[-1].payload["records_through"] <= checkpoints[-1].payload["prev"]["covers_seq"]
    else:
        tool_turn(session, "after 1")
    assert_a14_recovers_exactly(root, session)


def test_o2_2_negative_control_the_last_two_checkpoints_are_not_the_previous_base(tmp_path, monkeypatch):
    """Control: take C_p as the CHECKPOINT before C_n. After A11 that collects the true base's interval."""

    def last_two(records, newest):
        if newest.payload["prev"] is None:
            return None
        return [r for r in records if r.type_name == "CHECKPOINT" and r.seq < newest.seq][-1]

    monkeypatch.setattr(gc, "previous_checkpoint", last_two)
    root = Root(tmp_path)
    session = begin(root)
    for index in range(2):
        tool_turn(session, f"before {index}")
    session.close()
    (root.session_dir / "conversation.json").write_text(json.dumps([{"role": "user", "content": "NEW"}], indent=2) + "\n")
    session = start(root).session
    tool_turn(session, "after 0")
    true_prev = of_type(root, "CHECKPOINT")[-1].payload["prev"]["checkpoint_seq"]
    assert true_prev not in {r.seq for r in root.records()}, "the control unlinked the true previous checkpoint"
    partial_turn(session, 4)
    session.close()
    (root.session_dir / "conversation.json").write_bytes(b"\x00garbage")
    assert start(root).stop == "conversation_unreadable_unbound", "no previous base remains"


# ---------------------------------------------------------------------------
# O2-4: interrupted collection -- every cut, process death and simulated host loss
# ---------------------------------------------------------------------------
def probe(path: Path):
    ops = CutOps()
    root, session, orphans = collection_ready(path, ops)
    collect_with(session, ops)
    session.close()
    intent = of_type(root, "GC_INTENT")[-1]
    return ops.log, intent.payload, orphans


def test_o2_4_the_collection_unit_is_ordered_and_fenced(tmp_path):
    log, payload, orphans = probe(tmp_path / "probe")
    assert len(payload["segments"]) >= 3 and len(payload["blobs"]) >= 4 and set(orphans) <= set(payload["blobs"])
    calls = [(call, frame) for call, _name, frame in log]
    intent_sync = calls.index(("fsync", "11"))
    first_unlink = next(i for i, (call, _f) in enumerate(calls) if call == "unlink")
    done_write = calls.index(("write", "12"))
    assert calls[intent_sync - 1] == ("write", "11") and intent_sync < first_unlink < done_write
    # Each segment unlink is fenced by fsync(ledger/) before the next unlink of any kind.
    names = [name for _call, name, _frame in log]
    for index, (call, name, _frame) in enumerate(log):
        if call == "unlink" and name.endswith(".svl"):
            assert log[index + 1][:2] == ("sync_dir", "ledger")
    segment_order = [int(name[:6]) for call, name, _f in log if call == "unlink" and name.endswith(".svl")]
    assert segment_order == payload["segments"] == sorted(payload["segments"]), "oldest first, exactly the list"
    blob_order = [name for call, name, _f in log if call == "unlink" and not name.endswith(".svl")]
    assert blob_order == payload["blobs"]
    after_blobs = names.index("blobs", first_unlink)
    assert log[after_blobs][0] == "sync_dir" and log[after_blobs + 1][:2] == ("sync_dir", "ledger")
    assert after_blobs + 1 < done_write and calls[done_write + 1] == ("fsync", "12")


@pytest.mark.parametrize("loss", ["process-death", "host-loss-all", "host-loss-alternate"])
def test_o2_4_every_cut_in_a_collection_converges_over_two_restarts(tmp_path, loss):
    log, payload, _orphans = probe(tmp_path / "probe")
    for cut in range(len(log)):
        label = f"cut {cut} before {log[cut]} ({loss})"
        ops = CutOps()
        ops.crash_at = cut
        root, session, _ = collection_ready(tmp_path / f"cut-{cut}", ops)
        before = inventory(root)
        with pytest.raises(Crash):
            collect_with(session, ops)
        session.close()
        undecided = ops.unfenced.get(str(root.session_dir / "ledger"), [])
        assert len(undecided) <= 1, f"{label}: more than one segment unlink was undecided at once"
        if loss != "process-death":
            lose_unsynced(ops, "all" if loss == "host-loss-all" else "alternate")
        after = converge(root)
        assert_converged(root, payload, before, after, ops.kept, label)


@pytest.mark.parametrize("second", ["first-unlink", "after-first-fence", "blob-unlink", "before-done"])
def test_o2_4_a_second_interruption_while_finishing_the_same_intent_converges(tmp_path, monkeypatch, second):
    """Crash after the intent's sync, then again inside the restart that is finishing it."""
    log, payload, _orphans = probe(tmp_path / "probe")
    ops = CutOps()
    ops.crash_when = lambda call, path, frame: call == "unlink" and path.endswith(".svl") and path.endswith(
        cp.segment_name(payload["segments"][1])
    )  # the first segment is gone and fenced; the rest of the list is not
    root, session, _ = collection_ready(tmp_path / "run", ops)
    before = inventory(root)
    with pytest.raises(Crash):
        collect_with(session, ops)
    session.close()
    assert payload["segments"][0] not in segments(root) and payload["segments"][1] in segments(root)
    restart = CutOps(durable=ops.durable)  # the first process's watermark (SV022-01)
    real = gc.unlink_intent

    def armed(session_dir, intent, ops):
        restart.armed = True
        real(session_dir, intent, ops)

    monkeypatch.setattr(gc, "unlink_intent", armed)
    restart.crash_when = {
        "first-unlink": lambda call, path, frame: call == "unlink",
        "after-first-fence": lambda call, path, frame: call == "unlink" and len(restart.log) >= 2,
        "blob-unlink": lambda call, path, frame: call == "unlink" and "/blobs/" in path,
        "before-done": lambda call, path, frame: call == "write" and frame == "12",
    }[second]
    with pytest.raises(Crash):
        start(root, ops=restart)
    lose_unsynced(restart, "all")
    monkeypatch.setattr(gc, "unlink_intent", real)
    after = converge(root)
    assert_converged(root, payload, before, after, ops.kept, second)
    assert our_intent(root, payload) is not None


def test_o2_4_a_restart_reruns_the_stored_list_and_leaves_the_leftovers(tmp_path):
    ops = CutOps()
    root = Root(tmp_path)
    session = begin(root, ops=ops, gc_batch_max=3)
    orphans = {session.writer.blobs.put(f"orphan {index}".encode()) for index in range(6)}
    session.append_message("user", "collect three")
    ops.crash_when = lambda call, path, frame: call == "unlink"
    with pytest.raises(Crash):
        collect_with(session, ops)
    session.close()
    intent = of_type(root, "GC_INTENT")[-1]
    listed = set(intent.payload["blobs"]) | set(intent.payload["segments"])
    assert len(listed) == 3
    start(root).session.close()
    present = blobs(root)
    assert not set(intent.payload["blobs"]) & present
    assert (orphans - set(intent.payload["blobs"])) <= present, "leftovers wait for a later complete transaction"


def test_o2_4_negative_control_a_fresh_scan_at_restart_removes_items_outside_the_intent(tmp_path, monkeypatch):
    """Control: re-run by recomputing the unreferenced set instead of the stored list."""
    ops = CutOps()
    root = Root(tmp_path)
    session = begin(root, ops=ops, gc_batch_max=3)
    orphans = {session.writer.blobs.put(f"orphan {index}".encode()) for index in range(6)}
    session.append_message("user", "collect three")
    ops.crash_when = lambda call, path, frame: call == "unlink"
    with pytest.raises(Crash):
        collect_with(session, ops)
    session.close()
    real = gc.unlink_intent

    def fresh_scan(session_dir, intent, ops):
        records = [r for r in root.records() if r.type_name != "GC_INTENT" or r.payload != intent]
        basis = gc.retained_basis(records, [r for r in records if r.type_name == "CHECKPOINT"][-1])
        names = sorted(name for name in blobs(root) if name not in basis.retained)
        real(session_dir, {**intent, "blobs": names}, ops)

    monkeypatch.setattr(gc, "unlink_intent", fresh_scan)
    start(root).session.close()
    intent = of_type(root, "GC_INTENT")[-1]
    assert (orphans - set(intent.payload["blobs"])) & blobs(root) == set(), "the control removed the leftovers too"


# ---------------------------------------------------------------------------
# Failed deletion gate and fences: the persistence boundary
# ---------------------------------------------------------------------------
FAILURES = {
    "intent-fsync": lambda call, path, frame: call == "fsync" and frame == "11",
    "segment-unlink": lambda call, path, frame: call == "unlink" and path.endswith(".svl"),
    "ledger-fence": lambda call, path, frame: call == "sync_dir" and path.endswith("/ledger"),
    "blob-unlink": lambda call, path, frame: call == "unlink" and "/blobs/" in path,
    "blobs-fence": lambda call, path, frame: call == "sync_dir" and path.endswith("/blobs"),
}


@pytest.mark.parametrize("target", sorted(FAILURES))
def test_a_failed_intent_sync_unlink_or_fence_breaks_the_session_without_a_false_done(tmp_path, target):
    ops = CutOps()
    root, session, _ = collection_ready(tmp_path, ops)
    before = inventory(root)
    hits = []

    def fail(call, path, frame):
        if not hits and FAILURES[target](call, path, frame):
            hits.append((call, path))
            return OSError(errno.EIO, "injected EIO")
        return None

    ops.fail_when = fail
    with pytest.raises(cp.PersistenceFailure):
        collect_with(session, ops)
    assert hits and session.broken
    failed_at = next(i for i, entry in enumerate(ops.log) if entry[0] == hits[0][0] and entry[1] == Path(hits[0][1]).name)
    later = ops.log[failed_at + 1 :]
    assert not [e for e in later if e[0] == "unlink"], "nothing is removed after the failure"
    assert not [e for e in ops.log if e[2] == "12"], "no GC_DONE"
    if target == "intent-fsync":
        assert not [e for e in ops.log if e[0] == "unlink"], "no unlink without a synced intent"
    assert [e for e in ops.log if e[0] == "rename" and e[1] == "FSYNC_FAILED"] == [("rename", "FSYNC_FAILED", None)]
    assert (root.session_dir / "FSYNC_FAILED").exists()
    sent = []
    with pytest.raises(cp.PersistenceFailure):
        session.send(lambda: sent.append(1))
    assert sent == [], "no request after the failure"
    session.close()
    removed = before["blobs"] - blobs(root)
    assert removed <= set(of_type(root, "GC_INTENT")[-1].payload["blobs"])
    # The next start stops on the marker (A1) and changes nothing.
    stopped = inventory(root)
    opening = start(root)
    assert (opening.classification, opening.stop) == ("A1", "fsync_failed_previous_run")
    assert inventory(root) == stopped
    # After the operator's acknowledgement the readable intent is finished from its own list.
    st.acknowledge(root.session_dir, "fsync_failed_previous_run", "continue-from-bound")
    payload = of_type(root, "GC_INTENT")[-1].payload
    after = converge(root)
    assert_converged(root, payload, before, after, ops.kept, target)
    assert our_intent(root, payload) is not None


def test_a_failed_fence_whose_marker_also_fails_leaves_what_a_process_death_leaves(tmp_path):
    ops = CutOps()
    root, session, _ = collection_ready(tmp_path, ops)
    before = inventory(root)
    ops.fail_when = lambda call, path, frame: (
        OSError(errno.EIO, "injected EIO")
        if (call == "sync_dir" and path.endswith("/ledger")) or (call == "rename" and path.endswith("FSYNC_FAILED"))
        else None
    )
    with pytest.raises(cp.PersistenceFailure):
        collect_with(session, ops)
    assert session.marker_written is False and not (root.session_dir / "FSYNC_FAILED").exists()
    session.close()
    payload = of_type(root, "GC_INTENT")[-1].payload
    # v2 1.4.9: no marker, no stop -- the next start finishes the readable intent.
    after = converge(root)
    assert_converged(root, payload, before, after, ops.kept, "marker failed")
    assert our_intent(root, payload) is not None


# ---------------------------------------------------------------------------
# Intent validation and corruption: deletion authority
# ---------------------------------------------------------------------------
def planned(tmp_path):
    """A clean ledger ending at a checkpoint (collection off), its valid plan, and the facts it rests on."""
    root, session, orphans = collection_ready(tmp_path)
    session.collect = False
    session.writer.segment_max = cp.SEGMENT_MAX  # no rotation after it: the ledger ends at this checkpoint
    session.checkpoint()
    records = root.records()
    plan = gc.plan_collection(records, active_segment=session.writer.segment_no, blob_names=blobs(root))
    basis = gc.retained_basis(records, records[-1])
    return root, session, records, plan.payload, basis


def test_the_plan_is_valid_and_names_only_eligible_items(tmp_path):
    root, session, records, payload, basis = planned(tmp_path)
    assert gc.intent_problem(payload, records, active_segment=session.writer.segment_no) is None
    assert payload["records_through"] == records[-1].payload["prev"]["covers_seq"] == basis.floor
    assert payload["checkpoint_seq"] == records[-1].seq
    assert max(payload["segments"]) < basis.keep_segment <= session.writer.segment_no
    pending = records[-1].payload["state"]["notes"]["pending"][0]["blob"]
    assert pending in basis.retained and pending not in payload["blobs"]
    assert not set(payload["blobs"]) & basis.retained
    assert set(payload["blobs"]) == blobs(root) - basis.retained


def mutations(payload, basis, active, pending_blob):
    segments_, blobs_ = payload["segments"], payload["blobs"]
    return {
        "path string": ({**payload, "segments": ["../IDENTITY"]}, "segment name"),
        "negative segment": ({**payload, "segments": [-1]}, "segment name"),
        "bool segment": ({**payload, "segments": [True]}, "segment name"),
        "seven-digit segment": ({**payload, "segments": [1_000_000]}, "segment name"),
        "protected file as blob": ({**payload, "blobs": ["IDENTITY"]}, "blob name"),
        "traversal as blob": ({**payload, "blobs": ["../" + "a" * 61]}, "blob name"),
        "upper-case hex": ({**payload, "blobs": ["A" * 64]}, "blob name"),
        "duplicate segment": ({**payload, "segments": [*segments_, segments_[-1]]}, "order or duplicate"),
        "unsorted segments": ({**payload, "segments": segments_[::-1]}, "order or duplicate"),
        "duplicate blob": ({**payload, "blobs": [*blobs_, blobs_[-1]]}, "order or duplicate"),
        "extra key": ({**payload, "path": "x"}, "keys"),
        "missing key": ({k: v for k, v in payload.items() if k != "blobs"}, "keys"),
        "empty": ({**payload, "segments": [], "blobs": []}, "batch size"),
        "cover too high": ({**payload, "records_through": basis.floor + 1}, "cover"),
        "cover too low": ({**payload, "records_through": basis.floor - 1}, "cover"),
        "another checkpoint": ({**payload, "checkpoint_seq": basis.previous.seq}, "not after its checkpoint"),
        "first retained segment": ({**payload, "segments": [*segments_, basis.keep_segment]}, "protected segment"),
        "active segment": ({**payload, "segments": [*segments_, active]}, "protected segment"),
        "retained blob": ({**payload, "blobs": sorted([*blobs_, pending_blob])}, "retained blob"),
        "over the batch": ({**payload, "segments": [], "blobs": [f"{n:064x}" for n in range(gc.GC_BATCH_MAX + 1)]}, "batch size"),
    }


def test_invalid_intents_are_refused_before_any_unlink(tmp_path):
    root, session, records, payload, basis = planned(tmp_path)
    pending_blob = records[-1].payload["state"]["notes"]["pending"][0]["blob"]
    for name, (bad, expected) in mutations(payload, basis, session.writer.segment_no, pending_blob).items():
        assert gc.intent_problem(bad, records, active_segment=session.writer.segment_no) == expected, name
    with pytest.raises(cp.LedgerError):
        gc.unlink_intent(root.session_dir, {**payload, "segments": ["../IDENTITY"]}, cp.DurableOps())


def test_an_intent_over_the_body_cap_is_refused(monkeypatch):
    monkeypatch.setattr(gc, "GC_BATCH_MAX", 20_000)
    payload = {"records_through": 1, "checkpoint_seq": 3, "segments": [], "blobs": [f"{n:064x}" for n in range(20_000)]}
    assert len(cp.canonical_body(payload)) > cp.MAX_LEDGER_BODY
    assert gc.structure_problem(payload) == "body size"


def test_the_live_owner_refuses_an_invalid_plan_and_removes_nothing(tmp_path, monkeypatch):
    root, session, _ = collection_ready(tmp_path)
    events = []
    session.lifecycle = lambda event, **fields: events.append((event, fields))
    real = gc.plan_collection

    def protected_segment(records, **kwargs):
        plan = real(records, **kwargs)
        return gc.Plan({**plan.payload, "segments": [*plan.payload["segments"], kwargs["active_segment"]]}, 0)

    monkeypatch.setattr(gc, "plan_collection", protected_segment)
    before = inventory(root)
    intents = len(of_type(root, "GC_INTENT"))
    session.checkpoint()
    assert ("gc_refused", {"reason": "protected segment"}) in events
    assert len(of_type(root, "GC_INTENT")) == intents and inventory(root)["blobs"] == before["blobs"]


def write_intent(tmp_path, change):
    root, session, records, payload, basis = planned(tmp_path)
    session.close()
    bad = change(payload, basis, records)
    append_record(root, "GC_INTENT", bad)
    return root, bad


@pytest.mark.parametrize(
    "case",
    ["retained blob", "first retained segment", "cover", "records after it", "two pending"],
)
def test_startup_refuses_an_invalid_pending_intent_and_changes_nothing_but_stopped(tmp_path, case):
    def change(payload, basis, records):
        if case == "retained blob":
            pending = records[-1].payload["state"]["notes"]["pending"][0]["blob"]
            return {**payload, "blobs": sorted([*payload["blobs"], pending])}
        if case == "first retained segment":
            return {**payload, "segments": [*payload["segments"], basis.keep_segment]}
        if case == "cover":
            return {**payload, "records_through": basis.floor + 1}
        return payload

    root, bad = write_intent(tmp_path, change)
    if case == "records after it":
        append_record(root, "RUN_END", {"exit": 0, "reason": "after the intent"})
    if case == "two pending":
        append_record(root, "GC_INTENT", bad)
    before = root.snapshot()
    opening = start(root)
    assert (opening.stop, opening.session) == ("gc_intent_invalid", None), opening
    after = root.snapshot()
    stopped = str((root.session_dir / "STOPPED").relative_to(root.path))
    assert json.loads(after.pop(stopped))["reason"] == "gc_intent_invalid"
    assert after == before, "nothing removed, copied or written but STOPPED"


def test_a_torn_or_damaged_intent_is_never_deletion_authority(tmp_path):
    for variant in ("torn", "damaged"):
        path = tmp_path / variant
        root, session, records, payload, _basis = planned(path)
        session.close()
        scan = cp.scan_segments(cp.read_segments(root.session_dir / "ledger"), LINEAGE)
        frame, _chain = cp.encode_frame(scan.last_seq + 1, "GC_INTENT", payload, scan.last_chain)
        if variant == "torn":
            frame = frame[: len(frame) // 2]
        else:
            frame = frame[:60] + (b"0" if frame[60:61] != b"0" else b"1") + frame[61:]
        with open(root.segment(), "ab") as handle:
            handle.write(frame)
        before = inventory(root)
        opening = start(root)
        assert opening.stop is None, opening
        kinds = [r.payload["kind"] for r in of_type(root, "RECOVERY")]
        assert kinds[-1] == ("torn_incomplete" if variant == "torn" else "damaged_final"), variant
        assert inventory(root) == before, f"{variant}: nothing removed"
        assert not [r for r in root.records() if r.type_name == "GC_INTENT" and r.payload == payload]
        if variant == "damaged":
            assert opening.session.messages[-1]["content"] == "[runtime] a damaged GC_INTENT record was set aside at recovery"
        opening.session.close()


def test_a_valid_intent_whose_done_was_damaged_is_finished_once(tmp_path):
    root, session, records, payload, _basis = planned(tmp_path)
    session.close()
    intent = append_record(root, "GC_INTENT", payload)
    scan = cp.scan_segments(cp.read_segments(root.session_dir / "ledger"), LINEAGE)
    frame, _chain = cp.encode_frame(scan.last_seq + 1, "GC_DONE", {"intent_seq": intent.seq}, scan.last_chain)
    frame = frame[:-10] + b"0" * 9 + b"\n"  # a full GC_DONE frame with a broken chain: TC2
    with open(root.segment(), "ab") as handle:
        handle.write(frame)
    before, kept = inventory(root), protected(root)
    after = converge(root)
    assert_converged(root, payload, before, after, kept, "damaged done")
    assert [r.payload["kind"] for r in of_type(root, "RECOVERY")][-1] == "damaged_final"


# ---------------------------------------------------------------------------
# Rotation, retained headers, and gaps collection did not make
# ---------------------------------------------------------------------------
def test_rotation_continues_from_a_nonzero_oldest_segment_and_partly_retained_segments_stay_whole(tmp_path):
    root = Root(tmp_path)
    session = begin(root)
    for index in range(4):
        tool_turn(session, f"r{index}")
    present = segments(root)
    assert 0 not in present and present[0] >= 3, "segment 0 and several whole old segments were unlinked"
    records = root.records()
    prev = of_type(root, "CHECKPOINT")[-1].payload["prev"]
    holder = next(r for r in records if r.seq == prev["checkpoint_seq"])
    assert holder.segment in present, "the segment holding C_p's record is kept"
    straddling = [r for r in records if r.segment == holder.segment]
    assert straddling[0].type_name == "LEDGER_HEADER" and straddling[0].seq <= prev["covers_seq"] < holder.seq, (
        "C_p's segment straddles the floor and is kept whole, header first"
    )
    session.close()
    for _restart in range(2):
        session = start(root).session
        assert session is not None
        tool_turn(session, "after the restart")
        session.close()
    records = root.records()
    assert [r.seq for r in records] == list(range(records[0].seq, records[-1].seq + 1)), "seq continues"
    assert segments(root)[0] > present[0], "rotation and collection go on from a nonzero oldest segment"


def test_gaps_collection_did_not_make_still_stop(tmp_path):
    root = Root(tmp_path)
    session = begin(root)
    for index in range(4):
        tool_turn(session, f"r{index}")
    session.close()
    present = segments(root)
    ledger = root.session_dir / "ledger"
    # A middle segment missing: the strict scanner stops (A2).
    middle = ledger / cp.segment_name(present[len(present) // 2])
    saved = middle.read_bytes()
    middle.unlink()
    opening = start(root)
    assert (opening.classification, opening.stop) == ("A2", "ledger_damaged_at")
    middle.write_bytes(saved)
    (root.session_dir / "STOPPED").unlink()
    # The oldest present segment missing: no retained intent names it.
    (ledger / cp.segment_name(present[0])).unlink()
    opening = start(root)
    assert (opening.classification, opening.stop) == ("A2", "ledger_prefix_missing")


def test_a_lineage_that_never_collected_does_not_accept_a_missing_segment_0(tmp_path):
    root = Root(tmp_path)
    opening = root.start()  # collection off
    session = resume(opening)
    session.writer.segment_max = 1
    for index in range(3):
        session.append_message("user", f"m{index}")
    session.checkpoint()
    session.close()
    assert 0 in segments(root) and len(segments(root)) > 2
    (root.session_dir / "ledger" / cp.segment_name(0)).unlink()
    assert root.start().stop == "ledger_prefix_missing"


def test_a_gap_among_listed_segments_is_refused_not_reinterpreted(tmp_path):
    """Outside the fenced order (only a suffix of the list can survive): a lost middle unlink."""
    ops = CutOps()
    root, session, _ = collection_ready(tmp_path, ops)
    ledger = root.session_dir / "ledger"
    saved = {number: (ledger / cp.segment_name(number)).read_bytes() for number in segments(root)}
    ops.crash_when = lambda call, path, frame: call == "write" and frame == "12"  # every unlink done, no GC_DONE
    with pytest.raises(Crash):
        collect_with(session, ops)
    session.close()
    payload = of_type(root, "GC_INTENT")[-1].payload
    assert len(payload["segments"]) >= 3
    # An impossible cut under the fenced order: the second listed segment's
    # unlink did not persist while the first's and the third's did.
    middle = payload["segments"][1]
    (ledger / cp.segment_name(middle)).write_bytes(saved[middle])
    before = inventory(root)
    opening = start(root)
    assert (opening.classification, opening.stop) == ("A2", "ledger_damaged_at"), opening
    assert inventory(root) == before, "the refusal removed nothing"


# ---------------------------------------------------------------------------
# State and identity restored without their source records
# ---------------------------------------------------------------------------
def test_restored_state_and_identity_without_their_source_records(tmp_path):
    root = Root(tmp_path)
    session = begin(root)
    sources: set[int] = set()

    def written(name, kind=None):
        found = {r.seq for r in root.records() if r.type_name == name and (kind is None or r.payload.get("kind") == kind)}
        assert found, name
        sources.update(found)

    def refused():
        raise ConnectionError("no answer")

    with pytest.raises(ConnectionError):
        session.send(refused)  # failed_unknown: the retry is attempt 2
    respond(session, content="answered on attempt 2")
    written("REQUEST_SENT")
    session.checkpoint()
    session.write_note("N1", header=HEADER)
    written("NOTE_WRITTEN")
    session.checkpoint()
    session.close()
    opening = start(root)
    opening.session.adopt_notes()  # adoption: watermark and mirror
    written("MSG_APPEND", "note")
    session = resume(opening)
    session.record_fold(0, 2, 2)
    written("RECAP_FOLD")
    session.replace_history([*session.messages, {"role": "user", "content": "replaced"}])  # epoch 2
    written("HISTORY_REPLACED")
    for index in range(4):
        session.append_message("user", f"later {index}")
        session.checkpoint()
    assert not sources & {r.seq for r in root.records()}, "every source record is physically gone"
    assert not of_type(root, "REQUEST_SENT")
    state, messages, label = session.state.copy(), list(session.messages), session.next_label()
    assert (state.history_epoch, state.recap_folded, state.notes_adopted_through) == (2, 2, 1)
    assert state.adopted_mirror_sha256 is not None and state.requests_last["attempt"] == 2
    reserved = cs.read_identity(root.session_dir, LINEAGE)
    session.close()
    opening = start(root)
    assert opening.classification == "A9"
    assert opening.session.state == state and opening.session.messages == messages
    assert opening.session.next_label() == label
    opening.session.close()
    # The SV021-01 allocator after collection: hidden records above P allocate above IDENTITY.
    with open(root.segment(), "ab") as handle:
        handle.write(bytes(300))
    assert start(root).stop == "ledger_tail_ambiguous"
    st.acknowledge(root.session_dir, "ledger_tail_ambiguous", "continue-conservative")
    opening = start(root)
    assert opening.stop is None, opening
    assert opening.session.next_label() == f"{LINEAGE}:{reserved + 1}:1"
    assert cs.read_identity(root.session_dir, LINEAGE) >= reserved + 1


# ---------------------------------------------------------------------------
# Bounded batches
# ---------------------------------------------------------------------------
def test_a_backlog_is_collected_in_bounded_batches_without_recursion(tmp_path):
    root = Root(tmp_path)
    session = begin(root, gc_batch_max=4)
    remaining = {session.writer.blobs.put(f"orphan {index}".encode()) for index in range(10)}
    rounds = 0
    while remaining:
        last = root.records()[-1].seq
        session.append_message("user", f"unit {rounds}")
        session.checkpoint()
        intent = of_type(root, "GC_INTENT")[-1]
        assert len(intent.payload["segments"]) + len(intent.payload["blobs"]) <= 4
        assert len(cp.canonical_body(intent.payload)) <= cp.MAX_LEDGER_BODY
        removed = remaining - blobs(root)
        assert removed == remaining & set(intent.payload["blobs"]), "exactly this batch's list"
        remaining -= removed
        added = [r.type_name for r in root.records() if r.seq > last]
        assert added == ["MSG_APPEND", "LEDGER_HEADER", "CHECKPOINT", "GC_INTENT", "GC_DONE", "LEDGER_HEADER"], (
            "one unit, one checkpoint, one GC unit: collection never checkpoints again"
        )
        rounds += 1
        assert rounds <= 15
    assert rounds >= 3, "ten orphans need several batches of at most four"


def test_the_planner_bounds_a_long_backlog_to_one_batch(tmp_path):
    root, session, records, _payload, basis = planned(tmp_path)
    names = [f"{n:064x}" for n in range(10_000)]
    plan = gc.plan_collection(records, active_segment=session.writer.segment_no, blob_names=names)
    items = len(plan.payload["segments"]) + len(plan.payload["blobs"])
    assert items == gc.GC_BATCH_MAX and plan.leftover == len(plan.payload["segments"]) + 10_000 - gc.GC_BATCH_MAX
    assert len(cp.canonical_body(plan.payload)) < cp.MAX_LEDGER_BODY
    assert plan.payload["blobs"] == sorted(plan.payload["blobs"]) and plan.payload["blobs"][0] == names[0]
    assert gc.intent_problem(plan.payload, records) is None


# ---------------------------------------------------------------------------
# Astra SV022-01: a readable intent is made durable before a restart unlinks
# ---------------------------------------------------------------------------
def readable_unsynced_intent(tmp_path):
    """GC_INTENT fully written, its fsync never returned, then process death (M-1): readable, not durable."""
    first = CutOps()
    root, session, _ = collection_ready(tmp_path, first)
    first.crash_when = lambda call, path, frame: call == "fsync" and frame == "11"
    with pytest.raises(Crash):
        collect_with(session, first)
    session.close()
    intent = of_type(root, "GC_INTENT")[-1]
    assert first.durable[str(root.session_dir / "ledger" / cp.segment_name(intent.segment))] < intent.offset + intent.length
    return root, first, intent


def test_sv022_01_a_restart_syncs_the_readable_intent_before_its_first_unlink(tmp_path):
    """Astra's trace: unsynced intent -> process death -> restart unlinks one fenced segment -> crash -> host loss."""
    root, first, intent = readable_unsynced_intent(tmp_path)
    before = inventory(root)
    restart = CutOps(durable=first.durable)  # syncs that returned in either process, nothing else
    restart.armed = True
    restart.crash_when = lambda call, path, frame: call == "unlink" and any(e[0] == "unlink" for e in restart.log)
    with pytest.raises(Crash):
        start(root, ops=restart)  # dies after the first segment unlink and its ledger/ fence, before GC_DONE
    assert intent.payload["segments"][0] not in segments(root)
    lose_unsynced(restart, "all")
    after = converge(root)
    assert_converged(root, intent.payload, before, after, first.kept, "SV022-01")
    assert our_intent(root, intent.payload) is not None, "the deletion's authority survived the host loss"
    log = restart.log
    first_unlink = next(i for i, entry in enumerate(log) if entry[0] == "unlink")
    gate = [i for i, entry in enumerate(log) if entry == ("fsync", cp.segment_name(intent.segment), "11")]
    assert gate and gate[0] < first_unlink, "the intent's own segment is synced before the first unlink"
    assert log[first_unlink + 1][:2] == ("sync_dir", "ledger")


def test_sv022_01_a_failed_restart_intent_sync_removes_nothing(tmp_path):
    root, first, intent = readable_unsynced_intent(tmp_path)
    before = inventory(root)
    restart = CutOps(durable=first.durable)
    restart.armed = True
    hits = []

    def fail(call, path, frame):
        if not hits and call == "fsync" and frame == "11":
            hits.append(path)
            return OSError(errno.EIO, "injected EIO")
        return None

    restart.fail_when = fail
    with pytest.raises(cp.PersistenceFailure):
        start(root, ops=restart)
    assert hits == [str(root.session_dir / "ledger" / cp.segment_name(intent.segment))]
    assert not [e for e in restart.log if e[0] == "unlink"], "no unlink after a failed gate"
    assert not [e for e in restart.log if e[2] == "12"], "no GC_DONE"
    assert inventory(root) == before
    assert (root.session_dir / "FSYNC_FAILED").exists(), "the persistence boundary attempted its marker"
    assert start(root).classification == "A1"


# ---------------------------------------------------------------------------
# Astra SV022-02: an intent's segments must be a prefix of the surviving ones
# ---------------------------------------------------------------------------
def skipping(payload, how):
    segments_ = payload["segments"]
    return {**payload, "segments": segments_[1:] if how == "front" else [segments_[0], *segments_[2:]]}


def test_sv022_02_a_list_skipping_a_surviving_segment_is_refused_and_a_partial_prefix_is_not(tmp_path):
    root, session, records, payload, _basis = planned(tmp_path)
    assert len(payload["segments"]) >= 3
    for how in ("front", "interior"):
        assert gc.intent_problem(skipping(payload, how), records, active_segment=session.writer.segment_no) == "segment prefix", how
    # A restart after a partial prefix deletion: the leading listed segments are already gone.
    removed = set(payload["segments"][:2])
    remaining = [r for r in records if r.segment not in removed]
    assert gc.intent_problem(payload, remaining, active_segment=session.writer.segment_no) is None


@pytest.mark.parametrize("how", ["front", "interior"])
def test_sv022_02_startup_refuses_a_pending_intent_that_would_leave_a_gap(tmp_path, how):
    root, _bad = write_intent(tmp_path, lambda payload, basis, records: skipping(payload, how))
    before = root.snapshot()
    opening = start(root)
    assert (opening.stop, opening.session) == ("gc_intent_invalid", None), opening
    assert opening.detail["problem"] == "segment prefix"
    after = root.snapshot()
    stopped = str((root.session_dir / "STOPPED").relative_to(root.path))
    assert json.loads(after.pop(stopped))["reason"] == "gc_intent_invalid"
    assert after == before, "nothing removed, copied or written but STOPPED"


def test_sv022_02_the_live_owner_refuses_a_skipping_plan_before_publishing_it(tmp_path, monkeypatch):
    root, session, _ = collection_ready(tmp_path)
    events = []
    session.lifecycle = lambda event, **fields: events.append((event, fields))
    real = gc.plan_collection

    def front_skipping(records, **kwargs):
        plan = real(records, **kwargs)
        return gc.Plan(skipping(plan.payload, "front"), 0)

    monkeypatch.setattr(gc, "plan_collection", front_skipping)
    before = inventory(root)
    intents = len(of_type(root, "GC_INTENT"))
    session.checkpoint()
    assert ("gc_refused", {"reason": "segment prefix"}) in events
    assert len(of_type(root, "GC_INTENT")) == intents, "no GC_INTENT was published"
    after = inventory(root)
    assert before["segments"] <= after["segments"] and after["blobs"] == before["blobs"], "nothing was removed"
