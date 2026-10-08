"""Integrated O2-5 (SV-024): a rotation's new segment name lost after actual collection.

Contract: SV-015 v2 1.4.8 (a new segment is `O_EXCL`, its LEDGER_HEADER,
`fsync(file)`, `fsync(ledger/)`; until the directory sync returns its name may
vanish, and the old segment then ends TC0), the segment-rotation row of
1.4.10, and fixture O2-5 (recovery ends at the old segment; the segment is
recreated with `first_seq = last + 1`; no seq gap is reported as damage).

Evidence kind: in-process simulation in temporary roots, extending SV-022's
`CutOps`. `NameOps` also remembers each segment name created (`O_CREAT`)
since the last returned `fsync(ledger/)`. File-byte watermarks (returned file
fsyncs) and name fences (returned directory fsyncs) are kept apart. After a
process death both are handed to the next process (`inherit`); opening or
reading a file promotes neither. Simulated host loss (`host_loss`) takes back
only what neither covers: a name whose fence never returned, bytes whose
file fsync never returned. A returned file fsync keeps bytes only while the
name survives; a returned ledger/ fence keeps the name.

Collection is real: segment 0, the oldest records and their blobs are
physically gone before the armed rotation. Not a power-loss, kernel or
storage experiment; no provider; no real session.
"""

from __future__ import annotations

import errno
import json
import os
from dataclasses import dataclass
from pathlib import Path

import chassis_gc as gc
import chassis_persistence as cp
import chassis_startup as st
import pytest
from test_chassis_durability import Crash
from test_chassis_gc import CutOps, assert_a14_recovers_exactly, begin, inventory, of_type, protected, segments, start, tool_turn
from test_chassis_recovery_live import LINEAGE, Root, resume

TORN = 30  # unsynced header bytes that survive as a strict prefix (as in test_chassis_durability)
PROTECTED = ("IDENTITY", "run.json", "conversation.json", "conversation.prev.json", "HANDOFF.md")


# ---------------------------------------------------------------------------
# Fault model
# ---------------------------------------------------------------------------
class NameOps(CutOps):
    """`CutOps` plus the segment names M-2 may take back: created since their directory's last returned fsync."""

    def __init__(self, durable: dict | None = None, created: dict | None = None, unfenced: dict | None = None) -> None:
        super().__init__(durable)
        self.created: dict[str, list[str]] = {} if created is None else created
        if unfenced is not None:
            self.unfenced = unfenced

    def open(self, path, flags, mode=0o644):
        new = bool(flags & os.O_CREAT) and not os.path.exists(path)
        fd = super().open(path, flags, mode)
        if new and str(path).endswith(".svl"):
            self.created.setdefault(str(Path(path).parent), []).append(str(path))
        return fd

    def sync_dir(self, path):
        super().sync_dir(path)
        self.created[str(path)] = []  # only once the fsync returned

    def inherit(self) -> NameOps:
        """The next process after a process death: the same evidence, nothing promoted."""
        return NameOps(self.durable, self.created, self.unfenced)

    def unfenced_names(self) -> list[str]:
        return [path for paths in self.created.values() for path in paths]


def host_loss(ops: NameOps, *, names: str, data: str) -> dict:
    """Simulated M-2 over what `ops` (and every process it inherited from) left undecided.

    names: "vanish" -- every segment name no returned fsync(ledger/) covers is
    lost; "keep" -- they survive. data: "drop" -- bytes after a file's returned
    fsync are lost; "torn" -- a strict prefix of them (at most TORN) survives;
    "keep" -- they survive. Unfenced unlinks are undone. Nothing a returned
    fsync covers is touched.
    """
    taken = {"names": [], "bytes": {}, "restored": []}
    if names == "vanish":
        for path in ops.unfenced_names():
            if os.path.exists(path):
                os.unlink(path)
                taken["names"].append(Path(path).name)
    for path, size in ops.durable.items():
        if not os.path.exists(path) or data == "keep":
            continue
        now = os.path.getsize(path)
        if now > size:
            keep = size if data == "drop" else size + min(TORN, now - size - 1)
            os.truncate(path, keep)
            taken["bytes"][Path(path).name] = (now, keep)
    for items in ops.unfenced.values():
        for path, saved in items:
            Path(path).write_bytes(saved)
            taken["restored"].append(Path(path).name)
    return taken


# ---------------------------------------------------------------------------
# Fixture: a rotation right after a real collection
# ---------------------------------------------------------------------------
@dataclass
class At:
    """The store as the armed rotation found it; everything before it is durable."""

    done: cp.Record  # the GC_DONE the rotation follows
    number: int  # the new segment's number
    header: bytes  # its LEDGER_HEADER frame, exactly
    state: object
    messages: list
    kept: dict
    inventory: dict
    checkpoint: cp.Record


def collected(path: Path, ops: NameOps):
    """Collection on, one-unit segments: three tool turns collect segment 0 and the oldest records; then one message."""
    path.mkdir(parents=True, exist_ok=True)
    root = Root(path)
    session = begin(root, ops=ops)
    for index in range(3):
        tool_turn(session, f"r{index}")
    assert 0 not in segments(root) and root.records()[0].seq > 1 and of_type(root, "GC_DONE"), "collection ran"
    session.append_message("user", "collect, then rotate")
    return root, session


def rotate_after_collection(root: Root, session, ops: NameOps) -> None:
    """The next checkpoint collects for real; the rotation right after its GC_DONE runs with every call armed."""
    writer = session.writer
    real = writer.open_segment

    def armed(**kwargs):
        records = root.records()
        done = records[-1]
        assert done.type_name == "GC_DONE", "the rotation follows a completed collection"
        (intent,) = [r for r in records if r.seq == done.payload["intent_seq"]]
        assert intent.payload["segments"] and not set(intent.payload["segments"]) & set(segments(root)), "it removed segments"
        number = writer.segment_no + 1
        payload = {"lineage_id": LINEAGE, "segment_no": number, "first_seq": done.seq + 1, "prev_chain": done.chain}
        frame, _chain = cp.encode_frame(done.seq + 1, "LEDGER_HEADER", payload, done.chain)
        ops.at = At(
            done, number, frame, session.state.copy(), list(session.messages), protected(session), inventory(root),
            of_type(root, "CHECKPOINT")[-1],
        )
        ops.armed = True
        real(**kwargs)

    writer.open_segment = armed
    try:
        session.checkpoint()
    finally:
        del writer.open_segment


# The armed rotation calls: 0 open(n+1, O_CREAT|O_EXCL), 1 write(header), 2 fsync(n+1), 3 fsync(ledger/).
ARMED = {"before-write": 1, "before-file-sync": 2, "before-dir-sync": 3}


def cut_rotation(path: Path, cut: str, ops: NameOps | None = None):
    """Die at `cut`. "after-fence": the rotation returned; the next unit's request gate is synced and its effect ran."""
    ops = ops or NameOps()
    root, session = collected(path, ops)
    effects: list[str] = []
    if cut == "after-fence":
        rotate_after_collection(root, session, ops)
        label = session.next_label()

        def effect():
            effects.append(label)
            ops.at.kept = protected(session)
            raise Crash()

        with pytest.raises(Crash):
            session.send(effect)
    else:
        ops.crash_at = ARMED[cut]
        with pytest.raises(Crash):
            rotate_after_collection(root, session, ops)
    ops.armed = False
    session.close()
    return root, ops, effects


# ---------------------------------------------------------------------------
# Oracle
# ---------------------------------------------------------------------------
def new_segment(root: Root, at: At) -> Path:
    return root.session_dir / "ledger" / cp.segment_name(at.number)


def shape(root: Root, at: At) -> str:
    """The new name: absent, empty, a torn header prefix, or the complete header (anything after it is separate)."""
    path = new_segment(root, at)
    if not path.exists():
        return "absent"
    data = path.read_bytes()
    if not data:
        return "empty"
    if data.startswith(at.header):
        return "complete"
    assert at.header.startswith(data), "the new segment holds bytes that are not its header's"
    return "torn"


def scan(root: Root) -> cp.LedgerScan:
    return cp.scan_segments(cp.read_segments(root.session_dir / "ledger"), LINEAGE)


def assert_old_end(root: Root, at: At) -> None:
    """The name vanished: TC0 at the GC_DONE ending the old segment, and no prefix reported missing."""
    found = scan(root)
    assert (found.stop, found.tail, cp.classify_tail(found).kind) == (None, b"", "TC0")
    last = found.records[-1]
    assert (last.seq, last.chain, last.segment, found.tail_segment) == (at.done.seq, at.done.chain, at.number - 1, at.number - 1)
    assert gc.unauthorized_prefix(found.records) is None


def verified(root: Root) -> cp.LedgerScan:
    """Strictly clean; contiguous seqs and segment numbers; every header continues its predecessor."""
    found = scan(root)
    assert found.stop is None and found.tail == b"", found.detail
    seqs = [r.seq for r in found.records]
    assert seqs == list(range(seqs[0], seqs[-1] + 1)), "a seq gap"
    numbers = segments(root)
    assert numbers == list(range(numbers[0], numbers[-1] + 1)), "a segment-number gap"
    for previous, record in zip(found.records, found.records[1:]):
        if record.type_name == "LEDGER_HEADER":
            assert record.segment == previous.segment + 1
            assert (record.payload["first_seq"], record.payload["prev_chain"]) == (previous.seq + 1, previous.chain)
    return found


def recover(root: Root, at: At, ops, *, written: list[str], label=None, torn=None, kept=PROTECTED, same_state=True):
    """The first start after the cut: it continues, writes exactly `written`, and repeats and invents nothing."""
    before = {r.seq for r in root.records()}
    events: list[str] = []
    opening = start(root, ops=ops, lifecycle=lambda event, **fields: events.append(event))
    assert opening.stop is None, opening
    assert opening.classification == "A9", opening
    records = verified(root).records
    own = [r for r in records if r.seq not in before]
    assert [r.type_name for r in own] == written, own
    assert not [r for r in records if r.type_name in ("REQUEST_SENT", "INVOKING") and r.seq in {o.seq for o in own}]
    assert not [r for r in records if r.type_name in ("GC_INTENT", "GC_DONE") and r.seq > at.done.seq], "no collection repeated"
    assert "gc_collected" not in events
    now = inventory(root)
    assert now["blobs"] == at.inventory["blobs"], "no blob removed"
    assert at.inventory["segments"] <= now["segments"] <= at.inventory["segments"] | {at.number}, "no segment removed"
    assert {name: protected(root)[name] for name in kept} == {name: at.kept[name] for name in kept}
    assert of_type(root, "CHECKPOINT")[-1] == at.checkpoint, "the newest checkpoint is the one before the cut"
    for marker in (st.RECOVERING, "STOPPED", "FSYNC_FAILED", st.ACKNOWLEDGED):
        assert not (root.session_dir / marker).exists(), marker
    session = opening.session
    assert session.messages == at.messages
    if same_state:
        assert session.state == at.state
    if "LEDGER_HEADER" in written:
        assert new_segment(root, at).read_bytes().startswith(at.header), "the reused segment's header continues GC_DONE"
    if torn is not None:
        copies = [n for n in root.corrupt() if n.startswith(f"ledger-{at.number:06d}-0-")]
        assert len(copies) == 1 and (root.session_dir / "corrupt" / copies[0]).read_bytes() == torn
        assert [r.payload["kind"] for r in own if r.type_name == "RECOVERY"] == ["torn_incomplete"]
    if label is not None:
        # The gate whose effect ran survived with its fenced name: a possible spend, never a reused label.
        assert [r.payload["label"] for r in records if r.type_name == "REQUEST_SENT"].count(label) == 1
        spends = [r for r in own if r.type_name == "RECOVERY" and r.payload["kind"] == "possible_duplicate_spend"]
        assert len(spends) == 1 and spends[0].payload["detail"]["label"] == label
        turn, attempt = label.rsplit(":", 2)[1:]
        assert session.next_label() == f"{LINEAGE}:{turn}:{int(attempt) + 1}"
    return opening


def continue_and_converge(root: Root, opening, at: At, expected: str) -> None:
    """The next dependent unit (one message, then its unit-boundary rotation), then two more starts."""
    session = opening.session
    session.append_message("user", "after recovery")
    messages = list(session.messages)
    session.close()
    found = verified(root)
    (message,) = [r for r in found.records if r.type_name == "MSG_APPEND" and r.payload.get("text") == "after recovery"]
    (header,) = [r for r in found.records if r.type_name == "LEDGER_HEADER" and r.segment == at.number]
    if expected == "absent":
        # Recreated at the next unit boundary (v2 1.4.6), after that unit's record in the old segment.
        assert (message.segment, header.seq) == (at.number - 1, message.seq + 1)
    else:
        assert (message.segment, header.seq) == (at.number, at.done.seq + 1)
    first = start(root)
    assert (first.stop, first.classification) == (None, "A9"), first
    assert first.session.messages == messages
    first.session.close()
    count, after = len(root.records()), inventory(root)
    second = start(root)
    assert second.stop is None, second
    second.session.close()
    assert len(root.records()) == count and inventory(root) == after, "a further start wrote or removed something"
    verified(root)


# ---------------------------------------------------------------------------
# 1. Every rotation cut after collection, with every permitted survivor
# ---------------------------------------------------------------------------
CASES = [
    ("before-write", "process-death", "empty"),
    ("before-write", ("vanish", "drop"), "absent"),
    ("before-write", ("keep", "drop"), "empty"),
    ("before-file-sync", "process-death", "complete"),
    ("before-file-sync", ("vanish", "drop"), "absent"),
    ("before-file-sync", ("keep", "drop"), "empty"),
    ("before-file-sync", ("keep", "torn"), "torn"),
    ("before-file-sync", ("keep", "keep"), "complete"),
    ("before-dir-sync", "process-death", "complete"),
    ("before-dir-sync", ("vanish", "drop"), "absent"),  # a returned file fsync does not keep the name
    ("before-dir-sync", ("keep", "drop"), "complete"),
    ("after-fence", "process-death", "complete"),
    ("after-fence", ("vanish", "drop"), "complete"),  # a returned ledger/ fence keeps the name
]
WRITTEN = {"absent": [], "empty": ["LEDGER_HEADER"], "torn": ["LEDGER_HEADER", "RECOVERY"], "complete": []}


def loss_id(loss) -> str:
    return loss if isinstance(loss, str) else f"host-{loss[0]}-{loss[1]}"


@pytest.mark.parametrize(("cut", "loss", "expected"), CASES, ids=[f"{c}-{loss_id(loss)}" for c, loss, _e in CASES])
def test_o2_5_after_gc_rotation_survivors_recover_without_a_gap(tmp_path, cut, loss, expected):
    root, ops, effects = cut_rotation(tmp_path, cut)
    at = ops.at
    if loss == "process-death":
        following = ops.inherit()
    else:
        taken = host_loss(ops, names=loss[0], data=loss[1])
        assert taken["restored"] == [], "every collection unlink was fenced before the rotation"
        assert set(taken["bytes"]) <= {cp.segment_name(at.number)}, "only the new segment held unsynced bytes"
        following = NameOps()  # after the host loss, what is on disk is what is durable
    assert shape(root, at) == expected
    torn = new_segment(root, at).read_bytes() if expected == "torn" else None
    if expected == "absent":
        assert_old_end(root, at)
    label = effects[0] if effects else None
    written = WRITTEN[expected] + (["RECOVERY"] if label else [])
    opening = recover(root, at, following, written=written, label=label, torn=torn, same_state=label is None)
    continue_and_converge(root, opening, at, expected)
    assert effects == ([label] if label else []), "no request or tool ran during recovery"


# ---------------------------------------------------------------------------
# 2. Interrupting the finishing restart on both sides of its namespace fence
# ---------------------------------------------------------------------------
SECOND = {
    "before-its-fence": lambda ops: lambda call, path, frame: call == "sync_dir" and path.endswith("/ledger"),
    "after-its-fence": lambda ops: lambda call, path, frame: any(entry[:2] == ("sync_dir", "ledger") for entry in ops.log),
    "at-its-checkpoint": lambda ops: lambda call, path, frame: call == "fsync" and frame == "0d",
}
SECOND_SHAPE = {"before-its-fence": "absent", "after-its-fence": "empty", "at-its-checkpoint": "complete"}


@pytest.mark.parametrize("second", list(SECOND))
def test_o2_5_a_second_restart_preserves_file_and_name_durability(tmp_path, second):
    root, first, _effects = cut_rotation(tmp_path, "before-file-sync")
    at = first.at
    name = str(new_segment(root, at))
    assert shape(root, at) == "complete", "readable after the process death"
    assert first.durable[name] == 0 and name in first.unfenced_names(), "neither synced nor fenced"
    restart = first.inherit()
    restart.armed = True
    restart.crash_when = SECOND[second](restart)
    opening = None
    with pytest.raises(Crash):
        opening = start(root, ops=restart)
        resume(opening)
    if opening is not None:
        opening.session.close()
    if second == "before-its-fence":
        assert name in restart.unfenced_names() and restart.durable[name] == 0, "reading the header promoted nothing"
    else:
        assert name not in restart.unfenced_names(), "the restart's returned ledger/ fence covers the name"
    taken = host_loss(restart, names="vanish", data="drop")  # over both processes
    assert taken["restored"] == []
    observed = shape(root, at)
    if observed == "absent":
        assert_old_end(root, at)
    opening = recover(root, at, NameOps(), written=WRITTEN[observed], kept=("IDENTITY", "conversation.json", "HANDOFF.md"))
    assert observed == SECOND_SHAPE[second]
    meta = json.loads((root.session_dir / "run.json").read_text())
    assert meta["checkpoint"]["covers_seq"] <= scan(root).last_seq, "run.json never covers a record the ledger lost"
    continue_and_converge(root, opening, at, observed)


# ---------------------------------------------------------------------------
# 3. A failed namespace fence: no dependent append or effect
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("where", ["rotation", "restart"])
def test_o2_5_a_failed_namespace_fence_after_gc_allows_no_effect(tmp_path, where):
    hits = []

    def fail(call, path, frame):
        if not hits and call == "sync_dir" and path.endswith("/ledger"):
            hits.append(path)
            return OSError(errno.EIO, "injected EIO")
        return None

    sent = []
    if where == "rotation":
        ops = NameOps()
        root, session = collected(tmp_path, ops)
        ops.fail_when = fail
        with pytest.raises(cp.PersistenceFailure):
            rotate_after_collection(root, session, ops)
        at, log = ops.at, ops.log
        assert session.broken
        with pytest.raises(cp.PersistenceFailure):
            session.send(lambda: sent.append(1))
        with pytest.raises(cp.PersistenceFailure):
            session.append_message("user", "dependent")
        session.close()
        assert shape(root, at) == "complete" and verified(root).records[-1].type_name == "LEDGER_HEADER"
    else:
        root, first, _effects = cut_rotation(tmp_path, "before-dir-sync")
        at = first.at
        restart = first.inherit()
        restart.armed = True
        restart.fail_when = fail
        with pytest.raises(cp.PersistenceFailure):
            start(root, ops=restart)  # no session is returned: nothing dependent can run
        log = restart.log
        assert str(new_segment(root, at)) in restart.unfenced_names(), "a failed fence protects nothing"
    assert hits and sent == []
    failed = log.index(("sync_dir", "ledger", None))
    assert not [e for e in log[failed + 1 :] if e[0] == "write" and e[1].endswith(".svl")], "no append after the failed fence"
    assert (root.session_dir / "FSYNC_FAILED").exists(), "the persistence boundary attempted its marker"
    if where == "restart":
        host_loss(restart, names="vanish", data="drop")
        assert shape(root, at) == "absent"
        assert_old_end(root, at)
    before = root.snapshot()
    opening = start(root)
    assert (opening.classification, opening.stop) == ("A1", "fsync_failed_previous_run")
    after = root.snapshot()
    after.pop(str((root.session_dir / "STOPPED").relative_to(root.path)))
    assert after == before, "the stop changed nothing but STOPPED"
    # The operator's acknowledgement, in this temporary root: authority is kept and no effect is invented.
    st.acknowledge(root.session_dir, "fsync_failed_previous_run", "continue-from-bound")
    opening = recover(root, at, NameOps(), written=["RECOVERY_ACK"], same_state=False)
    assert opening.session.next_label() == cp.request_label(LINEAGE, at.state.requests_next["turn_seq"], at.state.requests_next["attempt"])
    continue_and_converge(root, opening, at, "absent" if where == "restart" else "complete")


# ---------------------------------------------------------------------------
# 4. O2-2 after the name loss: previous-base replay from the retained base
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("cut", "loss", "expected"),
    [("before-dir-sync", ("vanish", "drop"), "absent"), ("before-file-sync", ("keep", "torn"), "torn")],
    ids=["absent", "torn"],
)
def test_o2_5_previous_base_replay_survives_a_lost_rotation_name(tmp_path, cut, loss, expected):
    root, ops, _effects = cut_rotation(tmp_path, cut)
    at = ops.at
    host_loss(ops, names=loss[0], data=loss[1])
    assert shape(root, at) == expected
    torn = new_segment(root, at).read_bytes() if expected == "torn" else None
    opening = recover(root, at, NameOps(), written=WRITTEN[expected], torn=torn)
    assert_a14_recovers_exactly(root, opening.session)  # the intermediate hash at C_n is checked by the replay
    verified(root)


# ---------------------------------------------------------------------------
# 5. Controls: the cut mapping, and an oracle that detects an unfenced effect
# ---------------------------------------------------------------------------
def test_o2_5_the_rotation_calls_are_exactly_the_mapped_cuts(tmp_path):
    root, ops, effects = cut_rotation(tmp_path, "after-fence")
    name = cp.segment_name(ops.at.number)
    assert ops.log[:4] == [("open", name, None), ("write", name, "01"), ("fsync", name, "01"), ("sync_dir", "ledger", None)]
    gate = ops.log.index(("write", name, "02"))
    assert gate > 3 and ops.log[gate + 1 :] == [("fsync", name, "02")], "the effect ran right after its synced gate"
    assert len(effects) == 1


class IneffectiveLedgerFence(NameOps):
    """Control: once armed, fsync(ledger/) returns but is taken to protect no name (a rotation without its fence)."""

    def sync_dir(self, path):
        if self.armed and str(path).endswith("/ledger"):
            CutOps.sync_dir(self, path)
            return
        super().sync_dir(path)


def test_o2_5_negative_control_an_ineffective_rotation_fence_loses_an_effects_gate(tmp_path):
    """The `after-fence` oracle discriminates: without a name fence, an effect's gate can vanish with the name."""
    root, ops, effects = cut_rotation(tmp_path, "after-fence", IneffectiveLedgerFence())
    at = ops.at
    host_loss(ops, names="vanish", data="drop")
    assert effects and shape(root, at) == "absent", "the control loses the new name"
    assert effects[0] not in [r.payload["label"] for r in of_type(root, "REQUEST_SENT")], "the effect ran; its gate is gone"
    opening = start(root)
    assert opening.stop is None
    assert opening.session.next_label() == effects[0], "the control would reuse the label of a request that was sent"
    opening.session.close()


# ---------------------------------------------------------------------------
# 6. Astra SV024-02: a published RECOVERING depends only on durable inputs
# ---------------------------------------------------------------------------
class ShortHeaderWrite(NameOps):
    """M-1: once armed, the rotation's header write stores only TORN bytes, and the process dies inside it."""

    def write(self, fd, data):
        path = self.paths.get(fd, "")
        if self.armed and path.endswith(".svl") and bytes(data[18:20]) == b"01":
            self._step("write", path, "01")
            cp.DurableOps.write(self, fd, bytes(data[:TORN]))
            raise Crash()
        return super().write(fd, data)


def partial_header(path: Path):
    """After actual collection, the rotation's in-flight header write leaves a prefix: watermark 0, name unfenced."""
    ops = ShortHeaderWrite()
    root, session = collected(path, ops)
    with pytest.raises(Crash):
        rotate_after_collection(root, session, ops)
    ops.armed = False
    session.close()
    at = ops.at
    name = str(new_segment(root, at))
    assert new_segment(root, at).read_bytes() == at.header[:TORN], "an in-flight prefix (M-1), readable"
    assert ops.durable[name] == 0 and name in ops.unfenced_names(), "neither synced nor fenced"
    return root, ops, at, name


def published(ops: NameOps):
    """Process death at the first call after RECOVERING's rename and its fsync(session/) returned."""
    return lambda call, path, frame: ops.log[-2:] == [("rename", st.RECOVERING, None), ("sync_dir", "session", None)]


@pytest.mark.parametrize("variant", ["name-lost", "name-kept-data-lost", "interrupted-again"])
def test_sv024_02_a_partial_header_behind_a_published_intent_converges(tmp_path, variant):
    root, first, at, name = partial_header(tmp_path)
    fragment = at.header[:TORN]
    restart = first.inherit()  # both maps carried: nothing promoted by the restart's read
    restart.armed = True
    restart.crash_when = published(restart)
    with pytest.raises(Crash):
        start(root, ops=restart)
    assert (root.session_dir / st.RECOVERING).exists() and not root.corrupt(), "the intent is durable; no copy exists yet"
    last = restart
    if variant == "interrupted-again":
        third = restart.inherit()
        third.armed = True
        third.crash_when = lambda call, path, frame: any(entry[0] == "truncate" for entry in third.log)
        with pytest.raises(Crash):
            start(root, ops=third)  # finishes the copy and the truncation, dies before the truncation's fsync
        assert len(root.corrupt()) == 1 and new_segment(root, at).read_bytes() == b""
        last = third
    fenced, synced = name not in last.unfenced_names(), last.durable.get(name)
    taken = host_loss(last, names="keep" if variant == "name-kept-data-lost" else "vanish", data="drop")
    assert taken["restored"] == []
    opening = recover(root, at, NameOps(), written=["LEDGER_HEADER", "RECOVERY"], torn=fragment)
    assert fenced and synced == TORN, "the fragment the intent names was synced and its name fenced before the intent"
    assert not taken["names"] and not taken["bytes"], "the host loss could take nothing the intent depends on"
    continue_and_converge(root, opening, at, "torn")


PRE_INTENT = {
    "segment-fsync": lambda name: lambda call, path, frame: call == "fsync" and path == name,
    "ledger-fence": lambda name: lambda call, path, frame: call == "sync_dir" and path.endswith("/ledger"),
}


@pytest.mark.parametrize("fence", list(PRE_INTENT))
def test_sv024_02_a_failed_pre_intent_fence_publishes_nothing(tmp_path, fence):
    root, first, at, name = partial_header(tmp_path)
    fragment = at.header[:TORN]
    restart = first.inherit()
    restart.armed = True
    hits = []
    matches = PRE_INTENT[fence](name)

    def fail(call, path, frame):
        if not hits and matches(call, path, frame):
            hits.append(path)
            return OSError(errno.EIO, "injected EIO")
        return None

    restart.fail_when = fail
    with pytest.raises(cp.PersistenceFailure):
        start(root, ops=restart)
    assert hits
    assert not (root.session_dir / st.RECOVERING).exists() and ("rename", st.RECOVERING, None) not in restart.log, "no intent"
    assert not [e for e in restart.log if e[0] == "truncate" or (e[0] == "write" and e[1].endswith(".svl"))]
    assert not root.corrupt() and new_segment(root, at).read_bytes() == fragment, "no copy, no truncation"
    assert (root.session_dir / "FSYNC_FAILED").exists(), "the persistence boundary attempted its marker"
    before = root.snapshot()
    opening = start(root)
    assert (opening.classification, opening.stop) == ("A1", "fsync_failed_previous_run")
    after = root.snapshot()
    after.pop(str((root.session_dir / "STOPPED").relative_to(root.path)))
    assert after == before, "the stop changed nothing but STOPPED"
    st.acknowledge(root.session_dir, "fsync_failed_previous_run", "continue-from-bound")
    opening = recover(root, at, NameOps(), written=["LEDGER_HEADER", "RECOVERY", "RECOVERY_ACK"], torn=fragment, same_state=False)
    continue_and_converge(root, opening, at, "torn")


def test_sv024_01_a_failed_inherited_segment_fsync_publishes_no_checkpoint(tmp_path):
    root, first, _effects = cut_rotation(tmp_path, "before-file-sync")
    at = first.at
    name = str(new_segment(root, at))
    restart = first.inherit()
    hits = []

    def fail(call, path, frame):
        if not hits and call == "fsync" and path == name:
            hits.append(path)
            return OSError(errno.EIO, "injected EIO")
        return None

    restart.fail_when = fail
    opening = start(root, ops=restart)
    assert opening.stop is None, opening
    session = opening.session
    files, numbers = protected(root), segments(root)
    restart.armed = True  # the first checkpoint, through its inherited-segment fence
    with pytest.raises(cp.PersistenceFailure):
        session.checkpoint()
    assert hits == [name] and session.broken and session.writer.broken
    assert protected(root) == files, "no CK2-CK5 publication after the failed fence"
    assert of_type(root, "CHECKPOINT")[-1] == at.checkpoint and segments(root) == numbers, "no CHECKPOINT, no rotation"
    assert [e for e in restart.log if e[0] in ("rename", "link")] == [("rename", "FSYNC_FAILED", None)]
    assert not [e for e in restart.log if e[0] == "write" and e[1].endswith(".svl")]
    sent = []
    with pytest.raises(cp.PersistenceFailure):
        session.send(lambda: sent.append(1))
    with pytest.raises(cp.PersistenceFailure):
        session.append_message("user", "dependent")
    session.close()
    assert sent == [] and (root.session_dir / "FSYNC_FAILED").exists()
    assert start(root).classification == "A1"
