"""Durable writes, effect gates, rotation fences and quarantine admission (SV-020 foundation).

Contract: SV-015 v2 1.2 (effect gates), 1.4.8 (creation/rotation fences,
blob-before-reference, quarantine pre-admission), 1.4.9 (FSYNC_FAILED
honesty) and 1.4.10's rotation/gate rows; SV-013 CK2-CK4. Fixtures O1-7, O2-5
and O2-7.

Faults are injected through `DurableOps` inside temporary roots: an `OSError`
from a chosen call, or `Crash` (a BaseException no handler catches) standing in
for process death at that point, followed by deleting or shortening exactly the
bytes the fault model says may be lost. No real power loss, kernel behaviour
or chassis restart is exercised; these are not C-1/C-K/C-T passes.
"""

from __future__ import annotations

import errno
import json
import os

import chassis_persistence as cp
import common
import pytest
from test_chassis_ledger import LINEAGE, call, done, message, new_ledger, scan_dir, segment_path, turn_response


class Crash(BaseException):
    """Process death at the injected point."""


class FaultOps(cp.DurableOps):
    """Real filesystem calls, recorded in order; any of them can be made to fail."""

    def __init__(self):
        self.paths: dict[int, str] = {}
        self.events: list[tuple] = []
        self.faults: list[tuple] = []  # (operation, path predicate, exception)

    def _check(self, operation, path):
        self.events.append((operation, str(path)))
        for name, matches, error in self.faults:
            if name == operation and matches(str(path)):
                raise error

    def open(self, path, flags, mode=0o644):
        self._check("open", path)
        fd = super().open(path, flags, mode)
        self.paths[fd] = str(path)
        return fd

    def write(self, fd, data):
        self._check("write", self.paths.get(fd))
        return super().write(fd, data)

    def fsync(self, fd):
        self._check("fsync", self.paths.get(fd))
        super().fsync(fd)

    def close(self, fd):
        self.paths.pop(fd, None)
        super().close(fd)

    def rename(self, source, target):
        self._check("rename", target)
        super().rename(source, target)

    def link(self, source, target):
        self._check("link", target)
        super().link(source, target)

    def truncate(self, path, length):
        self._check("truncate", path)
        super().truncate(path, length)

    def sync_dir(self, path):
        self._check("sync_dir", path)
        super().sync_dir(path)


def eio():
    return OSError(errno.EIO, "injected EIO")


def segment(path: str) -> bool:
    return path.endswith(".svl")


def anything(path: str) -> bool:
    return True


def start_turn_7(tmp_path, ops):
    session, writer = new_ledger(tmp_path, ops=ops)
    writer.append("REQUEST_SENT", {"turn_seq": 7, "attempt": 1, "label": "0f1e:7:1"})
    writer.append("TURN_RESPONSE", turn_response(7, [call(0), call(1)]))
    return session, writer


def plan_of(session):
    scan = scan_dir(session)
    tail = cp.classify_tail(scan)
    return scan, cp.plan_recovery(scan, tail, read_blob=lambda sha: None)


def outcomes(plan):
    return [(c.call_index, c.status) for c in plan.calls]


# -- O1-7: a failed gate sync never permits its effect --------------------------
def test_o1_7_a_failed_invoking_sync_does_not_start_the_tool_and_attempts_the_marker(tmp_path):
    ops = FaultOps()
    session, writer = start_turn_7(tmp_path, ops)
    started = []
    ops.faults.append(("fsync", segment, eio()))
    with pytest.raises(cp.PersistenceFailure):
        writer.gate("INVOKING", {"turn_seq": 7, "call_index": 0}, lambda: started.append("tool"))
    assert started == []
    assert writer.broken and writer.marker_written is True
    assert json.loads((session / "FSYNC_FAILED").read_text())["detail"].startswith("OSError")
    with pytest.raises(cp.PersistenceFailure):
        writer.append("MSG_APPEND", message())  # a broken writer accepts nothing more


def test_o1_7_when_the_marker_fails_too_nothing_durable_is_claimed_and_the_call_is_unknown(tmp_path):
    ops = FaultOps()
    session, writer = start_turn_7(tmp_path, ops)
    started = []
    ops.faults.append(("fsync", anything, eio()))
    with pytest.raises(cp.PersistenceFailure):
        writer.gate("INVOKING", {"turn_seq": 7, "call_index": 0}, lambda: started.append("tool"))
    assert started == []
    marker_attempts = [e for e in ops.events if e[0] == "open" and ".FSYNC_FAILED." in e[1]]
    assert marker_attempts, "the best-effort marker was not attempted"
    assert writer.marker_written is False
    assert sorted(p.name for p in session.iterdir()) == ["ledger"]  # no marker, no temp left
    # Process-only restart: the unsynced INVOKING is readable. Unknown, never unrun.
    scan, plan = plan_of(session)
    assert scan.records[-1].type_name == "INVOKING"
    assert outcomes(plan) == [(0, "unknown"), (1, "unrun")]


@pytest.mark.parametrize("keep", [0, 100], ids=["absent", "short"])
def test_o1_7_after_host_loss_the_unsynced_gate_may_vanish_and_unrun_is_then_true(tmp_path, keep):
    ops = FaultOps()
    session, writer = start_turn_7(tmp_path, ops)
    end_of_p = segment_path(session).stat().st_size
    started = []
    ops.faults.append(("fsync", anything, eio()))
    with pytest.raises(cp.PersistenceFailure):
        writer.gate("INVOKING", {"turn_seq": 7, "call_index": 0}, lambda: started.append("tool"))
    os.truncate(segment_path(session), end_of_p + keep)  # M-2: unsynced bytes absent or a prefix
    tail_kind = cp.classify_tail(scan_dir(session)).kind
    _, plan = plan_of(session)
    assert started == [] and tail_kind == ("TC0" if keep == 0 else "TC1")
    assert outcomes(plan) == [(0, "unrun"), (1, "unrun")]


@pytest.mark.parametrize("operation", ["write", "fsync"])
def test_a_failed_request_gate_never_sends(tmp_path, operation):
    ops = FaultOps()
    session, writer = new_ledger(tmp_path, ops=ops)
    sent = []
    ops.faults.append((operation, segment, eio()))
    with pytest.raises(cp.PersistenceFailure):
        writer.gate("REQUEST_SENT", {"turn_seq": 1, "attempt": 1, "label": "0f1e:1:1"}, lambda: sent.append(1))
    assert sent == []


def test_a_gate_calls_its_effect_only_after_the_frame_sync_returned(tmp_path):
    ops = FaultOps()
    session, writer = start_turn_7(tmp_path, ops)
    seen = []
    result = writer.gate("INVOKING", {"turn_seq": 7, "call_index": 0}, lambda: seen.append(list(ops.events)) or "ran")
    assert result == "ran"
    assert seen[0][-2:] == [("write", str(segment_path(session))), ("fsync", str(segment_path(session)))]
    with pytest.raises(cp.LedgerError):
        writer.gate("DONE", done(7, 0, "0" * 64), lambda: seen.append("never"))
    assert len(seen) == 1


# -- blob before reference -----------------------------------------------------
def test_a_blob_is_durable_before_the_record_that_names_it(tmp_path):
    ops = FaultOps()
    session, writer = start_turn_7(tmp_path, ops)
    writer.append("INVOKING", {"turn_seq": 7, "call_index": 0})
    mark = len(ops.events)
    record = writer.append_with_blob("DONE", b"result text", lambda sha: done(7, 0, sha, size=11))
    events = ops.events[mark:]
    blobs = str(session / "blobs")
    blob_path = f"{blobs}/{record.payload['blob']}"
    order = [events.index(("rename", blob_path)), events.index(("sync_dir", blobs)),
             events.index(("write", str(segment_path(session))))]
    assert order == sorted(order)
    assert (session / "blobs" / record.payload["blob"]).read_bytes() == b"result text"


def test_a_blob_that_cannot_be_made_durable_is_never_referenced(tmp_path):
    ops = FaultOps()
    session, writer = start_turn_7(tmp_path, ops)
    writer.append("INVOKING", {"turn_seq": 7, "call_index": 0})
    ops.faults.append(("fsync", lambda path: "/blobs/" in path, eio()))
    with pytest.raises(cp.PersistenceFailure):
        writer.append_with_blob("DONE", b"result text", lambda sha: done(7, 0, sha, size=11))
    assert writer.broken and writer.marker_written is True
    assert list((session / "blobs").iterdir()) == []
    _, plan = plan_of(session)
    assert outcomes(plan) == [(0, "unknown"), (1, "unrun")]  # no DONE: the call stays unknown


def test_write_bytes_durable_fences_and_a_failure_leaves_the_old_file(tmp_path):
    ops = FaultOps()
    target = tmp_path / "run.json"
    cp.write_bytes_durable(target, b"one", ops=ops)
    kinds = [e[0] for e in ops.events]
    assert kinds == ["open", "write", "fsync", "rename", "sync_dir"]
    ops.faults.append(("fsync", anything, eio()))
    with pytest.raises(cp.PersistenceFailure):
        cp.write_bytes_durable(target, b"two", ops=ops)
    assert target.read_bytes() == b"one"
    assert [p.name for p in tmp_path.iterdir()] == ["run.json"]


def test_an_open_failure_writes_no_marker_because_no_byte_is_in_doubt(tmp_path):
    ops = FaultOps()
    session, writer = new_ledger(tmp_path, ops=ops, segment_max=1)
    ops.faults.append(("open", segment, OSError(errno.ENOSPC, "injected")))
    with pytest.raises(cp.PersistenceFailure):
        writer.rotate_if_full()
    assert writer.broken and not (session / "FSYNC_FAILED").exists()


# -- O2-5: a rotation whose new name is lost before its directory fence --------
def _rotate_and_die(tmp_path):
    ops = FaultOps()
    session, writer = new_ledger(tmp_path, ops=ops, segment_max=100)
    writer.append("MSG_APPEND", message("last in segment 0"))
    ops.faults.append(("sync_dir", lambda path: path.endswith("/ledger"), Crash()))
    with pytest.raises(Crash):
        writer.rotate_if_full()
    assert segment_path(session, 1).exists()  # the header was written and synced; the name was not
    return session


def _continue_and_append(session):
    scan = scan_dir(session)
    assert cp.classify_tail(scan).kind == "TC0"
    writer = cp.LedgerWriter.continue_after(session, LINEAGE, scan, segment_max=100)
    if writer.segment_no == 0:  # the name was lost: the next unit boundary rotates again
        assert writer.rotate_if_full()
    writer.append("MSG_APPEND", message("first in segment 1"))
    writer.close()
    scan = scan_dir(session)
    assert scan.stop is None and scan.tail == b"" and cp.classify_tail(scan).kind == "TC0"
    assert [r.seq for r in scan.records] == list(range(1, len(scan.records) + 1))  # no seq gap
    header = scan.records[2]
    assert (header.segment, header.type_name, header.payload["first_seq"]) == (1, "LEDGER_HEADER", 3)
    assert header.payload["prev_chain"] == scan.records[1].chain


def test_o2_5_a_lost_segment_name_ends_at_the_old_segment_and_is_recreated(tmp_path):
    session = _rotate_and_die(tmp_path)
    os.unlink(segment_path(session, 1))  # M-2: the unfenced name vanished
    scan = scan_dir(session)
    assert [r.segment for r in scan.records] == [0, 0] and scan.stop is None
    _continue_and_append(session)


def test_o2_5_a_surviving_empty_segment_is_reused_with_the_same_first_seq(tmp_path):
    session = _rotate_and_die(tmp_path)
    os.truncate(segment_path(session, 1), 0)  # the name survived; its header bytes did not
    _continue_and_append(session)


def test_o2_5_a_torn_segment_header_is_set_aside_then_the_segment_reused(tmp_path):
    session = _rotate_and_die(tmp_path)
    os.truncate(segment_path(session, 1), 30)
    scan = scan_dir(session)
    tail = cp.classify_tail(scan)
    assert (tail.kind, scan.tail_segment, scan.tail_offset) == ("TC1", 1, 0)
    plan = cp.plan_recovery(scan, tail, read_blob=lambda sha: None)
    result = cp.quarantine_tail(session, scan, plan, cp.Quarantine(session / "corrupt"))
    assert result.applied and segment_path(session, 1).stat().st_size == 0
    _continue_and_append(session)


def test_segment_0_can_be_recreated_only_when_empty(tmp_path):
    session = tmp_path / "session"
    (session / "ledger").mkdir(parents=True)
    segment_path(session, 0).write_bytes(b"")
    cp.LedgerWriter.create(session, LINEAGE).close()
    assert [r.type_name for r in scan_dir(session).records] == ["LEDGER_HEADER"]
    before = segment_path(session, 0).read_bytes()
    with pytest.raises(cp.LedgerError):
        cp.LedgerWriter.create(session, LINEAGE)
    assert segment_path(session, 0).read_bytes() == before


# -- O2-7 and quarantine ---------------------------------------------------------
def _torn_tail(tmp_path):
    session, writer = new_ledger(tmp_path)
    writer.append("REQUEST_SENT", {"turn_seq": 1, "attempt": 1, "label": "0f1e:1:1"})
    frame, _ = cp.encode_frame(writer.next_seq, "TURN_RESPONSE", turn_response(1, []), writer.chain)
    writer.close()
    with open(segment_path(session), "ab") as handle:
        handle.write(frame[:100])
    scan = scan_dir(session)
    tail = cp.classify_tail(scan)
    assert tail.kind == "TC1"
    return session, scan, cp.plan_recovery(scan, tail, read_blob=lambda sha: None)


def _fill(corrupt, count, size=10):
    corrupt.mkdir()
    for number in range(count):
        (corrupt / f"old-{number}.bin").write_bytes(b"q" * size)


def test_o2_7_at_the_file_cap_nothing_is_copied_or_truncated(tmp_path):
    session, scan, plan = _torn_tail(tmp_path)
    corrupt = session / "corrupt"
    _fill(corrupt, 2)
    before = segment_path(session).read_bytes()
    result = cp.quarantine_tail(session, scan, plan, cp.Quarantine(corrupt, max_files=2))
    assert (result.applied, result.stop_reason, result.copy) == (False, "corrupt_quarantine_full", None)
    assert segment_path(session).read_bytes() == before  # the tail stays byte-identical
    assert sorted(p.name for p in corrupt.iterdir()) == ["old-0.bin", "old-1.bin"]
    assert json.loads((session / "STOPPED").read_text())["reason"] == "corrupt_quarantine_full"


def test_the_byte_cap_is_strict_with_no_overshoot(tmp_path):
    session, scan, plan = _torn_tail(tmp_path)
    corrupt = session / "corrupt"
    _fill(corrupt, 1, size=10)
    before = segment_path(session).read_bytes()
    refused = cp.quarantine_tail(session, scan, plan, cp.Quarantine(corrupt, max_bytes=10 + 100 - 1))
    assert not refused.applied and segment_path(session).read_bytes() == before
    (session / "STOPPED").unlink()
    admitted = cp.quarantine_tail(session, scan, plan, cp.Quarantine(corrupt, max_bytes=10 + 100))
    assert admitted.applied and admitted.copy.read_bytes() == scan.tail
    assert segment_path(session).read_bytes() == before[: scan.tail_offset]
    assert cp.classify_tail(scan_dir(session)).kind == "TC0"


def test_the_copy_is_durable_before_the_truncation(tmp_path):
    session, scan, plan = _torn_tail(tmp_path)
    ops = FaultOps()
    cp.quarantine_tail(session, scan, plan, cp.Quarantine(session / "corrupt"), ops=ops)
    corrupt = str(session / "corrupt")
    order = [ops.events.index(("sync_dir", corrupt)), ops.events.index(("truncate", str(segment_path(session))))]
    assert order == sorted(order)
    ops = FaultOps()
    (tmp_path / "second").mkdir()
    session2, scan2, plan2 = _torn_tail(tmp_path / "second")
    before = segment_path(session2).read_bytes()
    ops.faults.append(("sync_dir", lambda path: path.endswith("/corrupt"), eio()))
    with pytest.raises(cp.PersistenceFailure):
        cp.quarantine_tail(session2, scan2, plan2, cp.Quarantine(session2 / "corrupt"), ops=ops)
    assert segment_path(session2).read_bytes() == before  # copy not proven: no truncation


def test_an_unacknowledged_ambiguous_tail_is_never_truncated(tmp_path):
    session, writer = new_ledger(tmp_path)
    writer.close()
    with open(segment_path(session), "ab") as handle:
        handle.write(b"SVL1 " + b"9" * 200)
    scan = scan_dir(session)
    tail = cp.classify_tail(scan)
    plan = cp.plan_recovery(scan, tail, read_blob=lambda sha: None)
    assert (tail.kind, plan.action) == ("TC4", "stop")
    before = segment_path(session).read_bytes()
    with pytest.raises(cp.LedgerError):
        cp.quarantine_tail(session, scan, plan, cp.Quarantine(session / "corrupt"))
    assert segment_path(session).read_bytes() == before and not (session / "corrupt").exists()
    other = cp.plan_recovery(scan, cp.TailClass("TC1", 3), read_blob=lambda sha: None)
    with pytest.raises(cp.LedgerError):
        cp.quarantine_tail(session, scan, other, cp.Quarantine(session / "corrupt"))


# -- the conversation file (CK1-CK4) --------------------------------------------
def test_conversation_bytes_match_what_the_chassis_writes_today(tmp_path):
    messages = [{"role": "user", "content": "café ☃"}, {"role": "assistant", "content": "ok"}]
    common.write_json_atomic(tmp_path / "today.json", messages)
    assert cp.conversation_bytes(messages) == (tmp_path / "today.json").read_bytes()


def test_installing_keeps_the_previous_file_and_fences_the_directory(tmp_path):
    ops = FaultOps()
    first = cp.conversation_bytes([{"role": "user", "content": "1"}])
    second = cp.conversation_bytes([{"role": "user", "content": "2"}])
    assert cp.install_conversation(tmp_path, first, ops=ops) == cp.hashlib.sha256(first).hexdigest()
    mark = len(ops.events)
    cp.install_conversation(tmp_path, second, ops=ops)
    assert (tmp_path / "conversation.json").read_bytes() == second
    assert (tmp_path / "conversation.prev.json").read_bytes() == first
    kinds = [e[0] for e in ops.events[mark:]]
    assert kinds.index("link") < kinds.index("rename") and kinds[-1] == "sync_dir"
    ops.faults.append(("fsync", anything, eio()))
    with pytest.raises(cp.PersistenceFailure):
        cp.install_conversation(tmp_path, first, ops=ops)
    assert (tmp_path / "conversation.json").read_bytes() == second
