"""Startup authority and recovery (SV-021 checkpoints D and E): A0-A15, tails, the recovery transaction.

Two evidence kinds, in separate sections and never mixed:

* **In-process simulation** (most of this file). A "crash" abandons a
  `Session` (its writer's fd is closed, nothing more is written) or raises
  `Crash` from an injected filesystem call; a "restart" calls `open_session`
  again on the same temporary root. Damaged bytes are written into the ledger
  file directly.
* **Real script restarts** (the last section, `test_script_*`). The runtime
  runs as `python3 services/chassis.py` against the local stub model over a
  unix socket; a process really dies (`os._exit`, SIGKILL) or a fault is
  injected by a test-only launcher, and a second process restarts on the same
  root. Tools count their own invocations in files.

Neither is a power-loss experiment: process death keeps completed writes
(M-1); host loss (M-2) is only simulated, by deleting or shortening bytes.

Fixtures are SV-013 section 3.5's FX-C (BASE, turn 7, C-1a...C-K7) and SV-015
v2 section 4.1-4.2 (O1-1...O1-6, O2-2, O2-7), at this runtime's own sequence
numbers: the shapes, texts and classifications are the oracle's, the seqs are
whatever the live owner wrote.
"""

from __future__ import annotations

import hashlib
import json

import chassis
import chassis_persistence as cp
import chassis_replay as rp
import chassis_session as cs
import chassis_startup as st
import pytest
from chassis_envelope import RawCall, RawResponse, adopt_response
from test_chassis_durability import Crash, FaultOps


class FaultOps(FaultOps):  # noqa: F811 -- the accepted class, plus unlink
    def unlink(self, path):
        self._check("unlink", path)
        super().unlink(path)


LINEAGE = "0f1e"
READ, WROTE = "x-contents", "wrote 1 characters to /work/y"
BASE = [{"role": "user", "content": "OPENING"}, {"role": "assistant", "content": "ok"}]
R7_CALLS = [("call_a", "read_file", '{"path":"x"}'), ("call_b", "write_file", '{"path":"y","text":"z"}')]


def T(call_id, name, text):  # noqa: N802
    return {"role": "tool", "tool_call_id": call_id, "name": name, "content": text}


class Root:
    def __init__(self, path) -> None:
        self.path = path
        self.session_dir = path / "session"
        self.home = path / "home"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.home.mkdir(parents=True, exist_ok=True)

    def start(self, **kwargs) -> st.Opening:
        return st.open_session(
            self.session_dir, self.home, repair=chassis.drop_stored_recap_frames, new_lineage=lambda: LINEAGE, **kwargs
        )

    def file(self, name) -> bytes:
        return (self.session_dir / name).read_bytes()

    def records(self) -> list:
        segments = cp.read_segments(self.session_dir / "ledger")
        scan = cp.scan_segments(segments, st._segment_lineage(segments) or LINEAGE)
        return list(scan.records)

    def types(self) -> list[str]:
        return [record.type_name for record in self.records()]

    def segment(self):
        return sorted((self.session_dir / "ledger").glob("*.svl"))[-1]

    def stopped(self) -> dict | None:
        path = self.session_dir / "STOPPED"
        return json.loads(path.read_text()) if path.exists() else None

    def corrupt(self) -> list:
        directory = self.session_dir / "corrupt"
        return sorted(p.name for p in directory.iterdir()) if directory.is_dir() else []

    def snapshot(self) -> dict:
        return {
            str(p.relative_to(self.path)): p.read_bytes()
            for p in sorted(self.path.rglob("*"))
            if p.is_file()
        }


def resume(opening: st.Opening):
    """What the chassis's resume does after startup: notes, an opening if empty, a checkpoint."""
    session = opening.session
    session.adopt_file_edit()
    session.adopt_notes(foreign_texts=opening.foreign_texts)
    if not session.messages:
        session.append_message("user", "OPENING")
    session.checkpoint()
    return session


def respond(session, calls=(), content=""):
    session.send(lambda: None)
    adoption = adopt_response(RawResponse(content, None, tuple(RawCall(*c) for c in calls)), session.state.requests_last["turn_seq"], session.caps)
    session.adopt(adoption)
    return adoption


def establish(root: Root):
    """BASE, bound by a checkpoint: OPENING, then a turn answering "ok"."""
    opening = root.start()
    assert opening.classification == "A4", opening
    session = resume(opening)
    respond(session, content="ok")
    session.checkpoint()
    assert session.messages == BASE
    return session


STEPS = ("REQUEST_SENT", "TURN_RESPONSE", "INVOKING0", "DONE0", "INVOKING1", "DONE1")


def partial_turn(session, steps: int):
    """Turn 7's first `steps` records, then the process stops (no checkpoint)."""
    done = 0
    if steps <= done:
        return
    session.send(lambda: None)
    done += 1
    if steps <= done:
        return
    adoption = adopt_response(RawResponse("", None, tuple(RawCall(*c) for c in R7_CALLS)), session.state.requests_last["turn_seq"])
    session.adopt(adoption)
    done += 1
    for call, text in zip(adoption.calls, (READ, WROTE), strict=True):
        if steps <= done:
            return
        session.invoke(call, lambda: None)
        done += 1
        if steps <= done:
            return
        session.record_result(call, "returned", text)
        done += 1


def r7(turn: int) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": wire, "type": "function", "function": {"name": name, "arguments": args}} for wire, name, args in R7_CALLS
        ],
    }


# ---------------------------------------------------------------------------
# A0, A1, A4-A7 (C-K5, C-K7)
# ---------------------------------------------------------------------------
def test_a4_an_absent_session_starts_a_lineage_with_an_explicit_empty_base(tmp_path):
    root = Root(tmp_path)
    opening = root.start()
    assert (opening.classification, opening.stop, opening.had_memory) == ("A4", None, False)
    assert root.types() == ["LEDGER_HEADER", "LEGACY_IMPORT"]
    assert root.records()[1].payload == {"conv_sha": None, "recap_folded": 0, "legacy": {"status": "none", "handoff_sha256": None}}
    assert not (root.session_dir / "run.json").exists(), "nothing claims format 2 before the first checkpoint"


def test_a0_a_stop_stops_without_writing_anything(tmp_path):
    root = Root(tmp_path)
    (root.session_dir / "STOPPED").write_text('{"reason": "x"}')
    before = root.snapshot()
    opening = root.start()
    assert (opening.classification, opening.stop, opening.session) == ("A0", "diagnostic_stop", None)
    assert root.snapshot() == before


def test_c_k7_a1_an_fsync_marker_stops_the_next_start(tmp_path):
    root = Root(tmp_path)
    establish(root).close()
    (root.session_dir / "FSYNC_FAILED").write_text("{}")
    opening = root.start()
    assert (opening.classification, opening.stop) == ("A1", "fsync_failed_previous_run")
    assert root.stopped()["reason"] == "fsync_failed_previous_run"
    assert root.start().classification == "A0"


def test_c_k5_a6_a_corrupt_legacy_conversation_stops_and_is_kept(tmp_path):
    root = Root(tmp_path)
    (root.session_dir / "conversation.json").write_bytes(b"{not json")
    opening = root.start()
    assert (opening.classification, opening.stop) == ("A6", "legacy_conversation_unreadable")
    assert root.file("conversation.json") == b"{not json", "never overwritten, never bootstrapped over"
    assert len(root.corrupt()) == 1 and not (root.session_dir / "ledger").exists()


def test_a7_format_2_without_a_ledger_is_a_lost_ledger(tmp_path):
    root = Root(tmp_path)
    (root.session_dir / "run.json").write_text(json.dumps({"format": 2, "lineage_id": LINEAGE}))
    (root.session_dir / "conversation.json").write_text(json.dumps(BASE, indent=2) + "\n")
    opening = root.start()
    assert (opening.classification, opening.stop) == ("A7", "ledger_missing")


def test_a13_a_first_run_interrupted_before_its_first_checkpoint_is_replayed(tmp_path):
    """Found by the first real-process restart: no run.json yet, so not format 2 -- and not a rollback."""
    root = Root(tmp_path)
    opening = root.start()
    session = opening.session
    session.append_message("user", "OPENING")
    partial_turn(session, 3)
    session.close()
    assert not (root.session_dir / "run.json").exists()
    opening = root.start()
    assert opening.classification == "A13" and opening.stop is None
    assert opening.session.messages[-2:] == [T("call_a", "read_file", UNK), T("call_b", "write_file", UNRUN)]


def test_an_interrupted_legacy_import_is_adopted_through_its_switch_not_re_imported(tmp_path):
    root = Root(tmp_path)
    (root.session_dir / "conversation.json").write_text(json.dumps(BASE, indent=2) + "\n")
    (root.session_dir / "run.json").write_text(json.dumps({"lineage_id": "abc"}))
    (root.home / "HANDOFF.md").write_text("N0\n")
    root.start().session.close()  # LEGACY_IMPORT + NOTE_WRITTEN{legacy}, then the process stops
    opening = root.start()
    assert opening.classification == "A9t", "the legacy file is the base its own LEGACY_IMPORT binds"
    session = resume(opening)
    assert [m["content"] for m in session.messages].count(rp.NOTE_PREFIX + "N0\n") == 1
    assert root.types().count("LEGACY_IMPORT") == 1 and "LEGACY_REIMPORT" not in root.types()


def test_a_deleted_run_json_after_a_checkpoint_stops(tmp_path):
    root = Root(tmp_path)
    establish(root).close()
    (root.session_dir / "run.json").unlink()
    opening = root.start()
    assert (opening.stop, opening.classification) == ("run_json_missing", "CK5")


def test_run_json_unreadable_with_a_ledger_stops(tmp_path):
    root = Root(tmp_path)
    establish(root).close()
    (root.session_dir / "run.json").write_text("{torn")
    assert root.start().stop == "run_json_unreadable"


def test_a5_a_legacy_list_is_imported_repaired_with_its_fold(tmp_path):
    root = Root(tmp_path)
    frame = {"role": "system", "content": chassis.RECAP_FRAME_PREFIX + "old"}
    legacy = [frame, *BASE, frame]
    (root.session_dir / "conversation.json").write_text(json.dumps(legacy, indent=2) + "\n")
    (root.session_dir / "run.json").write_text(json.dumps({"lineage_id": "abc", "recap_folded": 2}))
    opening = root.start()
    assert opening.classification == "A5" and opening.had_memory
    assert opening.session.messages == BASE and opening.session.state.recap_folded == 1
    assert opening.session.lineage_id == "abc", "the legacy lineage is carried on"
    imported = root.records()[1].payload
    assert imported["conv_sha"] == hashlib.sha256(root.file("conversation.json")).hexdigest()


@pytest.mark.parametrize("in_list", [True, False], ids=["c-n3-matched", "c-n4-unadopted"])
def test_c_n3_c_n4_legacy_note_migration(tmp_path, in_list):
    root = Root(tmp_path)
    note = "# Handoff\n\nN0\n"
    (root.home / "HANDOFF.md").write_text(note)
    messages = [*BASE] + ([{"role": "user", "content": rp.NOTE_PREFIX + note}] if in_list else [])
    (root.session_dir / "conversation.json").write_text(json.dumps(messages, indent=2) + "\n")
    session = resume(root.start())
    status = root.records()[1].payload["legacy"]["status"]
    appended = [m for m in session.messages if m["content"] == rp.NOTE_PREFIX + note]
    if in_list:
        assert status == "legacy_matched_unproven" and "NOTE_WRITTEN" not in root.types()
    else:
        # SV021-03: the legacy generation is carried by LEGACY_IMPORT itself.
        imported = root.records()[1].payload
        assert status == "legacy_unadopted_unproven" and imported["note"]["gen"] == 1
        assert "NOTE_WRITTEN" not in root.types()
    assert len(appended) == 1, "matched: not re-appended; unadopted: adopted once"
    session.close()
    again = resume(root.start())
    assert [m["content"] for m in again.messages].count(rp.NOTE_PREFIX + note) == 1, "never adopted a second time"


# ---------------------------------------------------------------------------
# C-1a...C-1f: a crash at every point of turn 7
# ---------------------------------------------------------------------------
UNK, UNRUN = rp.UNKNOWN_TEXT, rp.UNRUN_TEXT
C1 = {
    1: [],
    2: [T("call_a", "read_file", UNRUN), T("call_b", "write_file", UNRUN)],
    3: [T("call_a", "read_file", UNK), T("call_b", "write_file", UNRUN)],
    4: [T("call_a", "read_file", READ), T("call_b", "write_file", UNRUN)],
    5: [T("call_a", "read_file", READ), T("call_b", "write_file", UNK)],
    6: [T("call_a", "read_file", READ), T("call_b", "write_file", WROTE)],
}


@pytest.mark.parametrize("steps", sorted(C1), ids=["c-1a", "c-1b", "c-1c", "c-1d", "c-1e", "c-1f"])
def test_c_1_a_crash_at_each_point_of_a_turn_recovers_exactly(tmp_path, steps):
    root = Root(tmp_path)
    session = establish(root)
    turn = session.state.requests_next["turn_seq"]
    partial_turn(session, steps)
    session.close()
    opening = root.start()
    assert opening.classification == "A9", "the file is bound to the newest checkpoint; the suffix is replayed"
    messages = opening.session.messages
    expected = BASE + ([r7(turn)] if steps >= 2 else []) + C1[steps]
    assert messages == expected
    recovered = [r for r in root.records() if r.type_name in ("SYNTH", "UNRUN", "RECOVERY")]
    if steps == 1:
        (spend,) = recovered
        assert spend.payload == {"kind": "possible_duplicate_spend", "detail": {"label": f"{LINEAGE}:{turn}:1", "next": {"turn_seq": turn, "attempt": 2}}}
        assert opening.session.next_label() == f"{LINEAGE}:{turn}:2", "C-1a: the label is never reused"
    # Recovery invokes nothing and sends nothing: it has no client and no tools.
    session = resume(opening)
    count = len(root.records())
    session.close()
    again = root.start()
    assert again.session.messages == session.messages and len(root.records()) == count, "a second start adds nothing"


def test_c_d3_a_missing_done_blob_is_known_payload_lost(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    partial_turn(session, 2)
    adoption_calls = session.group.calls
    call = next(c for c in adopt_response(RawResponse("", None, tuple(RawCall(*c) for c in R7_CALLS)), 7).calls)
    session.invoke(call, lambda: None)
    session.record_result(call, "raised:ValueError", "error: ValueError: boom")
    session.close()
    assert adoption_calls[0]["wire_id"] == "call_a"
    (root.session_dir / "blobs" / hashlib.sha256(b"error: ValueError: boom").hexdigest()).unlink()
    opening = root.start()
    assert opening.session.messages[-2] == T(
        "call_a", "read_file",
        "this call raised ValueError; its stored error text (23 bytes, sha256 "
        "34a19b10151df6f90ebde3dc097d33b2191107b5c4ca737051e1c0b400bdb75f) could not be recovered",
    )


# ---------------------------------------------------------------------------
# Tails (O1-1...O1-6, C-D1)
# ---------------------------------------------------------------------------
def frame_after(root: Root, session, type_name: str, payload: dict) -> bytes:
    return cp.encode_frame(session.writer.next_seq, type_name, payload, session.writer.chain)[0]


def append_raw(root: Root, data: bytes) -> None:
    with open(root.segment(), "ab") as handle:
        handle.write(data)


def damaged(frame: bytes, offset: int = 60) -> bytes:
    data = bytearray(frame)
    data[offset] = ord("9") if data[offset] != ord("9") else ord("8")
    return bytes(data)


def turn7_open(root: Root):
    session = establish(root)
    partial_turn(session, 2)
    turn = session.replay.group.turn_seq
    return session, turn


@pytest.mark.parametrize("history", ["o1-1a-durable-then-damaged", "o1-1b-torn-garbage"])
def test_o1_1_a_damaged_final_invoking_is_unknown_and_later_calls_unrun(tmp_path, history):
    """1a and 1b are the same bytes; the classifier sees no history, so the outcome is one."""
    root = Root(tmp_path)
    session, turn = turn7_open(root)
    frame = frame_after(root, session, "INVOKING", {"turn_seq": turn, "call_index": 0})
    session.close()
    append_raw(root, damaged(frame))
    opening = root.start()
    assert opening.classification == "A9"
    assert opening.session.messages[-2:] == [T("call_a", "read_file", rp.DAMAGED_TAIL_TEXT), T("call_b", "write_file", UNRUN)]
    recovery = next(r for r in root.records() if r.type_name == "RECOVERY")
    assert recovery.payload["kind"] == "damaged_final" and recovery.payload["detail"]["type"] == "05"
    assert recovery.payload["detail"]["bytes"] == len(frame)
    assert len(root.corrupt()) == 1 and not (root.session_dir / st.RECOVERING).exists()


def test_o1_2_a_torn_invoking_is_unrun(tmp_path):
    root = Root(tmp_path)
    session, turn = turn7_open(root)
    frame = frame_after(root, session, "INVOKING", {"turn_seq": turn, "call_index": 0})
    session.close()
    append_raw(root, frame[:100])
    opening = root.start()
    assert opening.session.messages[-2:] == [T("call_a", "read_file", UNRUN), T("call_b", "write_file", UNRUN)]
    recovery = next(r for r in root.records() if r.type_name == "RECOVERY")
    assert recovery.payload["kind"] == "torn_incomplete" and recovery.payload["detail"]["bytes"] == 100


def test_o1_5_corrected_a_valid_frame_plus_ten_bytes_is_tc1_and_its_call_unknown(tmp_path):
    root = Root(tmp_path)
    session, turn = turn7_open(root)
    frame = frame_after(root, session, "INVOKING", {"turn_seq": turn, "call_index": 0})
    session.close()
    append_raw(root, frame + b"0123456789")
    opening = root.start()
    assert opening.session.messages[-2:] == [T("call_a", "read_file", UNK), T("call_b", "write_file", UNRUN)]


def test_o1_5_an_invalid_full_frame_plus_ten_bytes_is_tc3_a_stop(tmp_path):
    root = Root(tmp_path)
    session, turn = turn7_open(root)
    frame = frame_after(root, session, "INVOKING", {"turn_seq": turn, "call_index": 0})
    session.close()
    append_raw(root, damaged(frame) + b"0123456789")
    before = root.snapshot()
    opening = root.start()
    assert (opening.stop, opening.session) == ("ledger_damaged_at", None)
    after = root.snapshot()
    after.pop("session/STOPPED")
    assert after == before, "nothing truncated or copied on a stop"


def test_c_d1_damage_followed_by_valid_records_is_a2(tmp_path):
    root = Root(tmp_path)
    session, _turn = turn7_open(root)
    session.close()
    path = root.segment()
    data = bytearray(path.read_bytes())
    turn_response = next(r for r in root.records() if r.type_name == "TURN_RESPONSE")
    data[turn_response.offset + 60] ^= 0x01
    path.write_bytes(bytes(data))
    opening = root.start()
    assert opening.stop == "ledger_damaged_at" and root.stopped()["detail"]["damaged_at"] == turn_response.seq


def test_o1_4_an_ambiguous_tail_stops_without_truncation_then_continues_conservatively(tmp_path):
    root = Root(tmp_path)
    session, turn = turn7_open(root)
    session.close()
    garbage = bytes(range(256)) + bytes(44)  # 300 bytes; no valid header
    append_raw(root, garbage)
    reserved = cs.read_identity(root.session_dir, LINEAGE)
    before = root.file(f"ledger/{root.segment().name}")
    opening = root.start()
    assert (opening.classification, opening.stop) == ("TC4", "ledger_tail_ambiguous")
    assert root.file(f"ledger/{root.segment().name}") == before and root.corrupt() == []
    assert root.stopped()["detail"]["tail_sha256"] == hashlib.sha256(garbage).hexdigest()
    st.acknowledge(root.session_dir, "ledger_tail_ambiguous", "continue-conservative")
    assert root.stopped() is None and (root.session_dir / st.ACKNOWLEDGED).exists()
    opening = root.start()
    messages = opening.session.messages
    assert messages[-3:-1] == [T("call_a", "read_file", rp.DAMAGED_TAIL_TEXT), T("call_b", "write_file", rp.DAMAGED_TAIL_TEXT)]
    assert messages[-1]["content"].startswith("[runtime] records after ledger seq") and "tools may have run" in messages[-1]["content"]
    kinds = [(r.type_name, r.payload.get("kind")) for r in root.records()]
    assert ("RECOVERY_ACK", None) in kinds and ("RECOVERY", "damaged_tail_acknowledged") in kinds
    spend = next(r for r in root.records() if r.payload.get("kind") == "possible_duplicate_spend")
    # SV021-01: above every turn the durable reservation covered (it covered
    # every request the hidden bytes could hold), not a length formula.
    assert spend.payload["detail"]["next"] == {"turn_seq": reserved + 1, "attempt": 1} and reserved >= turn
    assert not (root.session_dir / st.ACKNOWLEDGED).exists() and not (root.session_dir / st.RECOVERING).exists()


def test_a_stale_acknowledgement_grants_nothing(tmp_path):
    root = Root(tmp_path)
    session, _turn = turn7_open(root)
    session.close()
    append_raw(root, bytes(300))
    root.start()
    st.acknowledge(root.session_dir, "ledger_tail_ambiguous", "continue-conservative")
    append_raw(root, b"x")  # the tail is no longer the acknowledged bytes
    opening = root.start()
    assert opening.stop == "ledger_tail_ambiguous" and opening.session is None


def test_unimplemented_resolutions_are_refused_and_change_nothing(tmp_path):
    root = Root(tmp_path)
    (root.session_dir / "STOPPED").write_text(json.dumps({"reason": "ledger_missing", "detail": None}))
    before = root.snapshot()
    with pytest.raises(cp.LedgerError, match="not implemented"):
        st.acknowledge(root.session_dir, "ledger_missing", "bootstrap-preserving")
    assert root.snapshot() == before


def test_o1_6_a_damaged_request_after_a_checkpoint_is_a_possible_spend(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    turn = session.state.requests_next["turn_seq"]
    frame = frame_after(root, session, "REQUEST_SENT", {"turn_seq": turn, "attempt": 1, "label": f"{LINEAGE}:{turn}:1"})
    session.close()
    append_raw(root, damaged(frame))
    opening = root.start()
    spend = next(r for r in root.records() if r.payload.get("kind") == "possible_duplicate_spend")
    assert spend.payload["detail"] == {"label": f"{LINEAGE}:{turn}:1", "next": {"turn_seq": turn, "attempt": 2}}
    assert opening.session.next_label() == f"{LINEAGE}:{turn}:2"


# ---------------------------------------------------------------------------
# The conversation's authority (C-K1...C-K4, C-K6, A14/O2-2)
# ---------------------------------------------------------------------------
def test_c_k2_a11_an_edited_list_is_adopted_as_an_edit(tmp_path):
    root = Root(tmp_path)
    establish(root).close()
    (root.session_dir / "conversation.json").write_text(json.dumps([{"role": "user", "content": "NEW"}], indent=2) + "\n")
    opening = root.start()
    assert opening.classification == "A11"
    edit = root.records()[-1]
    assert edit.type_name == "EXTERNAL_EDIT" and edit.payload["epoch"] == 2 and edit.payload["notices"] == []
    assert opening.session.messages == [{"role": "user", "content": "NEW"}]


def test_a11_with_an_unmerged_suffix_closes_its_group_then_says_so(tmp_path):
    root = Root(tmp_path)
    session, _turn = turn7_open(root)
    session.close()
    (root.session_dir / "conversation.json").write_text(json.dumps([{"role": "user", "content": "NEW"}], indent=2) + "\n")
    opening = root.start()
    assert opening.classification == "A11"
    assert root.types()[-3:] == ["UNRUN", "UNRUN", "EXTERNAL_EDIT"]
    (notice,) = root.records()[-1].payload["notices"]
    assert "call_a (read_file): not run" in notice and "call_b (write_file): not run" in notice
    assert opening.session.messages == [{"role": "user", "content": "NEW"}, {"role": "user", "content": notice}]


def test_c_k3_a12_a_deleted_list_is_a_clean_slate_with_everything_kept(tmp_path):
    root = Root(tmp_path)
    establish(root).close()
    prev = root.file("conversation.prev.json")
    (root.session_dir / "conversation.json").unlink()
    opening = root.start()
    assert opening.classification == "A12" and opening.session.messages == []
    assert root.types()[-1] == "EXTERNAL_DELETE" and root.file("conversation.prev.json") == prev


def test_c_k4_a15_a_checkpoint_ahead_of_the_ledger_stops(tmp_path):
    root = Root(tmp_path)
    establish(root).close()
    meta = json.loads(root.file("run.json"))
    meta["checkpoint"]["covers_seq"] = len(root.records()) + 5
    (root.session_dir / "run.json").write_text(json.dumps(meta))
    assert root.start().stop == "checkpoint_ahead_of_ledger"


def test_a14_o2_2_an_unreadable_file_is_rebuilt_from_the_previous_base(tmp_path):
    root = Root(tmp_path)
    session = establish(root)  # C_p binds BASE
    partial_turn(session, 6)
    session.checkpoint()  # C_n binds BASE + turn 7
    turn7 = list(session.messages)
    partial_turn(session, 4)  # turn 8: request, response, call 0 invoked and done
    session.close()
    assert json.loads(root.file("conversation.prev.json")) == BASE
    (root.session_dir / "conversation.json").write_bytes(b"\x00garbage")
    opening = root.start()
    assert opening.classification == "A14"
    tail = opening.session.messages[len(turn7):]
    assert tail[1:3] == [T("call_a", "read_file", READ), T("call_b", "write_file", UNRUN)]
    assert tail[-1]["content"] == st.A14_NOTICE
    # SV021-02: the unreadable file is replaced by the newest checkpoint's own
    # (hash-verified) bytes -- bound again -- and the suffix replays on top.
    assert json.loads(root.file("conversation.json")) == turn7, "the unreadable file was replaced by C_n"
    assert json.loads(root.file("conversation.prev.json")) == BASE, "the bound previous base is not rotated away"
    expected = list(opening.session.messages)
    opening.session.close()
    again = root.start()
    assert again.classification == "A9" and again.session.messages == expected
    assert [m["content"] for m in expected].count(st.A14_NOTICE) == 1
    assert any(name.startswith("conversation-") for name in root.corrupt())


def test_o2_2_a_previous_base_that_does_not_reach_the_newest_hash_stops(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    partial_turn(session, 6)
    session.checkpoint()
    session.close()
    (root.session_dir / "blobs" / hashlib.sha256(READ.encode()).hexdigest()).unlink()
    (root.session_dir / "conversation.json").write_bytes(b"garbage")
    opening = root.start()
    assert opening.stop == "replay_mismatch", "the interval replay no longer hashes to C_n"


def test_a14_without_any_bound_base_stops(tmp_path):
    root = Root(tmp_path)
    establish(root).close()
    (root.session_dir / "conversation.json").write_bytes(b"garbage")
    (root.session_dir / "conversation.prev.json").write_bytes(b"garbage too")
    assert root.start().stop == "conversation_unreadable_unbound"


def test_c_k6_a8_a_rollback_is_reimported_with_its_notes(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    session.write_note("N1", header="# Handoff")
    session.checkpoint()
    session.close()
    note_text = (root.home / "HANDOFF.md").read_text()
    # An older runtime ran: it appended the note itself, two turns, and dropped `format`.
    old = [*BASE, {"role": "user", "content": rp.NOTE_PREFIX + note_text}, {"role": "assistant", "content": "old 1"}, {"role": "assistant", "content": "old 2"}]
    (root.session_dir / "conversation.json").write_text(json.dumps(old, indent=2) + "\n")
    meta = json.loads(root.file("run.json"))
    for key in ("format", "writer", "checkpoint", "history_epoch"):
        meta.pop(key)
    (root.session_dir / "run.json").write_text(json.dumps(meta))
    opening = root.start()
    assert opening.classification == "A8"
    reimport = root.records()[-1]
    assert reimport.type_name == "LEGACY_REIMPORT" and reimport.payload["unmerged_suffix"] is None
    session = resume(opening)
    assert session.messages[: len(old)] == old
    assert [m["content"] for m in session.messages].count(rp.NOTE_PREFIX + note_text) == 1, "adopted_by_foreign_runtime: not appended again"
    assert next(r for r in root.records() if r.payload.get("kind") == "note").payload.get("foreign") is True


# ---------------------------------------------------------------------------
# CK1-CK6 crash cuts (C-K1)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("cut", "expected"),
    [
        ("ck2-temp", "A9"),
        ("ck3-prev", "A9"),
        ("ck4-install", "A10"),
        ("ck5-run-json", "A10"),
        ("ck6-before-write", "A10"),
        ("ck6-written-unsynced", "A9"),  # M-1: a completed write is visible to the next process
    ],
)
def test_checkpoint_crash_cuts_classify_by_the_bound_rule(tmp_path, cut, expected):
    root = Root(tmp_path)
    session = establish(root)
    partial_turn(session, 6)
    final = list(session.messages)
    ops = FaultOps()
    session.ops = ops
    session.writer.ops = ops
    ops.paths[session.writer.fd] = str(root.segment())  # the segment it opened before the swap
    predicate = {
        "ck2-temp": ("fsync", lambda p: ".conversation." in p),
        "ck3-prev": ("rename", lambda p: p.endswith("conversation.prev.json")),
        "ck4-install": ("sync_dir", lambda p: p.endswith("/session")),
        "ck5-run-json": ("sync_dir", lambda p: p.endswith("/session")),
        "ck6-before-write": ("write", lambda p: p.endswith(".svl")),
        "ck6-written-unsynced": ("fsync", lambda p: p.endswith(".svl")),
    }[cut]
    if cut == "ck5-run-json":
        calls = {"n": 0}
        operation, matches = predicate

        def second(path, matches=matches):
            if matches(path):
                calls["n"] += 1
                return calls["n"] == 2
            return False

        predicate = (operation, second)
    ops.faults.append((predicate[0], predicate[1], Crash()))
    with pytest.raises(Crash):
        session.checkpoint()
    session.close()
    opening = root.start()
    assert opening.classification == expected
    assert opening.session.messages == final
    if expected == "A10":
        assert "EXTERNAL_EDIT" not in root.types()


# ---------------------------------------------------------------------------
# The recovery transaction: crash cuts inside recovery itself
# ---------------------------------------------------------------------------
CUTS = [
    ("after-intent", ("write", lambda p: "/corrupt/." in p)),
    ("after-copy", ("truncate", lambda p: p.endswith(".svl"))),
    ("after-truncate", ("write", lambda p: p.endswith(".svl"))),
    ("after-first-record", ("fsync", lambda p: p.endswith(".svl"))),
]


@pytest.mark.parametrize("tc", ["tc2-invoking", "tc4-acknowledged"])
@pytest.mark.parametrize("cut", CUTS, ids=[c[0] for c in CUTS])
def test_a_crash_inside_recovery_never_turns_unknown_into_unrun(tmp_path, cut, tc):
    root = Root(tmp_path)
    session, turn = turn7_open(root)
    frame = frame_after(root, session, "INVOKING", {"turn_seq": turn, "call_index": 0})
    session.close()
    if tc == "tc2-invoking":
        append_raw(root, damaged(frame))
        expected = [T("call_a", "read_file", rp.DAMAGED_TAIL_TEXT), T("call_b", "write_file", UNRUN)]
    else:
        append_raw(root, bytes(300))
        root.start()
        st.acknowledge(root.session_dir, "ledger_tail_ambiguous", "continue-conservative")
        expected = [T("call_a", "read_file", rp.DAMAGED_TAIL_TEXT), T("call_b", "write_file", rp.DAMAGED_TAIL_TEXT)]
    name, (operation, matches) = cut
    ops = FaultOps()
    if name == "after-first-record":
        seen = {"n": 0}

        def nth(path, matches=matches):
            if matches(path):
                seen["n"] += 1
                return seen["n"] == 2
            return False

        matches = nth
    ops.faults.append((operation, matches, Crash()))
    with pytest.raises(Crash):
        root.start(ops=ops)
    opening = root.start()
    assert opening.session is not None, opening
    messages = opening.session.messages
    assert messages[len(BASE) + 1 : len(BASE) + 3] == expected
    if tc == "tc4-acknowledged":
        assert messages[-1]["content"].startswith("[runtime] records after ledger seq"), "the hidden-turn notice survives the cut"
    closures = [r for r in root.records() if r.type_name in ("SYNTH", "UNRUN")]
    assert len(closures) == 2, "nothing written twice"
    assert not (root.session_dir / st.RECOVERING).exists()
    assert len([n for n in root.corrupt() if n.startswith("ledger-")]) == 1


def test_acknowledgement_crash_cuts_never_invent_permission(tmp_path):
    root = Root(tmp_path)
    session, _turn = turn7_open(root)
    session.close()
    append_raw(root, bytes(300))
    root.start()
    ops = FaultOps()
    ops.faults.append(("sync_dir", lambda p: p.endswith("/session"), Crash()))  # after ACKNOWLEDGED's rename
    with pytest.raises(Crash):
        st.acknowledge(root.session_dir, "ledger_tail_ambiguous", "continue-conservative", ops=ops)
    assert root.stopped() is not None
    assert root.start().classification == "A0", "STOPPED is removed last; until then nothing continues"
    ops = FaultOps()
    ops.faults.append(("unlink", lambda p: p.endswith("STOPPED"), Crash()))
    with pytest.raises(Crash):
        st.acknowledge(root.session_dir, "ledger_tail_ambiguous", "continue-conservative", ops=ops)
    assert root.start().classification == "A0"
    st.acknowledge(root.session_dir, "ledger_tail_ambiguous", "continue-conservative")
    assert root.start().session is not None


def test_an_fsync_acknowledgement_is_transcribed_once(tmp_path):
    root = Root(tmp_path)
    establish(root).close()
    (root.session_dir / "FSYNC_FAILED").write_text("{}")
    root.start()
    st.acknowledge(root.session_dir, "fsync_failed_previous_run", "continue-from-bound")
    assert not (root.session_dir / "FSYNC_FAILED").exists()
    ops = FaultOps()
    ops.faults.append(("unlink", lambda p: p.endswith(st.ACKNOWLEDGED), Crash()))
    with pytest.raises(Crash):
        root.start(ops=ops)
    opening = root.start()
    assert opening.classification == "A9"
    assert root.types().count("RECOVERY_ACK") == 1 and not (root.session_dir / st.ACKNOWLEDGED).exists()


# ---------------------------------------------------------------------------
# Quarantine admission (O2-7)
# ---------------------------------------------------------------------------
def test_o2_7_a_full_quarantine_copies_nothing_and_truncates_nothing(tmp_path):
    root = Root(tmp_path)
    session, turn = turn7_open(root)
    frame = frame_after(root, session, "INVOKING", {"turn_seq": turn, "call_index": 0})
    session.close()
    append_raw(root, frame[:100])
    corrupt = root.session_dir / "corrupt"
    corrupt.mkdir()
    for index in range(2):
        (corrupt / f"old-{index}").write_bytes(b"x")
    segment_before = root.segment().read_bytes()
    full = cp.Quarantine(corrupt, max_files=2)
    opening = root.start(quarantine=full)
    assert opening.stop == "corrupt_quarantine_full"
    assert root.segment().read_bytes() == segment_before and sorted(p.name for p in corrupt.iterdir()) == ["old-0", "old-1"]
    st.acknowledge(root.session_dir, "corrupt_quarantine_full", "continue-from-bound")
    opening = root.start(quarantine=cp.Quarantine(corrupt, max_files=3))
    assert opening.session.messages[-2:] == [T("call_a", "read_file", UNRUN), T("call_b", "write_file", UNRUN)]


# ===========================================================================
# Real script restarts (evidence kind: process death and restart, local stub)
# ===========================================================================
SCRIPT_DUTY = '''
import os
import chassis

tools = chassis.ToolRegistry()


def _count(name):
    with open(os.path.join(os.environ["COUNT_DIR"], name), "a") as handle:
        handle.write("x")


@tools.register
def read_file(path: str) -> str:
    """Read."""
    _count("read_file")
    return "x-contents"


@tools.register
def act(what: str) -> str:
    """Act."""
    _count("act")
    if what == "die":
        os._exit(137)  # process death inside the tool body
    return "acted"


@tools.register
def write_file(path: str, text: str) -> str:
    """Write."""
    _count("write_file")
    return "wrote"


def main(context):
    if os.environ.get("ASK") == "1":
        context.ask("go")
'''

# A test-only launcher: patches the persistence layer's fsync in this process,
# then runs the real runtime as __main__ exactly as the supervisor would.
FAULT_LAUNCHER = '''
import os, runpy, sys
services = sys.argv[1]
sys.path.insert(0, services)
import chassis_persistence as cp
real = cp.DurableOps.fsync
wanted, nth = os.environ["FAIL_FSYNC_TYPE"].encode(), int(os.environ["FAIL_FSYNC_NTH"])
seen = [0]
def fsync(self, fd):
    path = os.readlink(f"/proc/self/fd/{fd}")
    if path.endswith(".svl"):
        with open(path, "rb") as handle:
            last = handle.read().rstrip(b"\\n").rsplit(b"\\n", 1)[-1]
        if last[18:20] == wanted:
            seen[0] += 1
            if seen[0] == nth:
                raise OSError(5, "injected EIO on the gate sync")
    real(self, fd)
cp.DurableOps.fsync = fsync
sys.argv = [os.path.join(services, "chassis.py")]
runpy.run_path(sys.argv[0], run_name="__main__")
'''


class ScriptWorld:
    """One temporary root, one local stub, many real `chassis.py` processes."""

    def __init__(self, replies, *, hold_first: bool = False, hold_request: int | None = None) -> None:
        hold_request = 1 if hold_first else hold_request
        import tempfile  # noqa: PLC0415
        import threading  # noqa: PLC0415

        from stub_model import Stub, StubServer  # noqa: PLC0415 -- conftest's path

        class Recording(Stub):
            def __init__(inner, *args, **kwargs):  # noqa: N805
                super().__init__(*args, **kwargs)
                inner.bodies = []
                inner.release = threading.Event()

            def handle(inner, body):  # noqa: N805
                inner.bodies.append(json.loads(body))
                if hold_request is not None and len(inner.bodies) == hold_request:
                    inner.release.wait(60)  # the test kills the runtime meanwhile
                return super().handle(body)

        self.root = __import__("pathlib").Path(tempfile.mkdtemp(prefix="sv21-", dir="/tmp"))
        for name in ("work", "home", "telemetry", "diary", "diode", "counts"):
            (self.root / name).mkdir()
        (self.root / "work" / "duty.py").write_text(SCRIPT_DUTY, encoding="utf-8")
        (self.root / "launch.py").write_text(FAULT_LAUNCHER, encoding="utf-8")
        self.stub = Recording(script=replies)
        self.server = StubServer(self.stub, socket_path=self.root / "model.sock").start()

    def close(self) -> None:
        import shutil  # noqa: PLC0415

        self.stub.release.set()
        self.server.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def env(self, **extra) -> dict:
        import os  # noqa: PLC0415

        env = dict(os.environ)
        for name in ("RUN_MAX_TURNS", "RUN_MAX_SECONDS", "CONTEXT_WINDOW_EVICTION_TOKENS", "AGENT_ENTRY"):
            env.pop(name, None)
        env.update(
            {
                "SERVICES_DIR": str(SERVICES), "AGENT_SLUG": "agent_r", "AGENT_NAME": "restart",
                "WORK_DIR": str(self.root / "work"), "AGENT_HOME": str(self.root / "home"),
                "DIARY_DIR": str(self.root / "diary"), "DIODE_DUTY_DIR": str(self.root / "diode"),
                "TELEMETRY_DIR": str(self.root / "telemetry"), "LLM_SOCKET_PATH": str(self.root / "model.sock"),
                "LLM_BASE_URL": "http://localhost/v1", "LLM_MODEL": "stub", "OPENROUTER_API_KEY": "sk-dummy",
                "SOCKET_WAIT_SECONDS": "5", "RECORDER_TIMEOUT_SECONDS": "60", "CONTEXT_WINDOW_TOKENS": "200000",
                "COUNT_DIR": str(self.root / "counts"),
            }
        )
        env.update(extra)
        return env

    def command(self, launcher: bool, *args) -> list:
        import sys  # noqa: PLC0415

        if launcher:
            return [sys.executable, str(self.root / "launch.py"), str(SERVICES), *args]
        return [sys.executable, str(SERVICES / "chassis.py"), *args]

    def run(self, *args, launcher: bool = False, **extra):
        import subprocess  # noqa: PLC0415

        return subprocess.run(
            self.command(launcher, *args), cwd=str(self.root / "work"), env=self.env(**extra),
            capture_output=True, text=True, timeout=60,
        )

    def counts(self) -> dict:
        return {p.name: len(p.read_text()) for p in (self.root / "counts").iterdir()}

    def lifecycle(self) -> list[dict]:
        path = self.root / "telemetry" / "agents" / "agent_r" / "lifecycle.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []

    def last_end(self) -> dict:
        return [r for r in self.lifecycle() if r["event"] == "run_end"][-1]

    @property
    def session_dir(self):
        return self.root / "home" / "session"

    def conversation(self) -> list:
        return json.loads((self.session_dir / "conversation.json").read_text())

    def records(self) -> list:
        segments = cp.read_segments(self.session_dir / "ledger")
        return list(cp.scan_segments(segments, st._segment_lineage(segments)).records)


SERVICES = __import__("pathlib").Path(__file__).resolve().parent.parent / "services"


def three_calls(middle: str):
    from stub_model import Reply, ToolCall  # noqa: PLC0415

    return [
        Reply(tool_calls=[ToolCall("read_file", {"path": "x"}), ToolCall("act", {"what": middle}), ToolCall("write_file", {"path": "y", "text": "z"})])
    ]


@pytest.fixture
def script_world():
    opened = []

    def build(replies, **kwargs):
        world = ScriptWorld(replies, **kwargs)
        opened.append(world)
        return world

    yield build
    for world in opened:
        world.close()


def test_script_process_death_inside_a_tool_is_unknown_and_nothing_is_replayed(script_world):
    world = script_world(three_calls("die"))
    first = world.run(ASK="1")
    assert first.returncode == 137, first.stdout[-2000:] + first.stderr[-2000:]
    assert world.counts() == {"read_file": 1, "act": 1}
    second = world.run(ASK="0")
    assert second.returncode == 0, second.stdout[-2000:] + second.stderr[-2000:]
    tools = [m for m in world.conversation() if m["role"] == "tool"]
    assert [m["content"] for m in tools] == ["x-contents", rp.UNKNOWN_TEXT, rp.UNRUN_TEXT]
    assert world.counts() == {"read_file": 1, "act": 1}, "no tool was invoked again by recovery"
    assert len(world.stub.bodies) == 1, "recovery sent nothing"
    kinds = [r.type_name for r in world.records()]
    assert kinds.count("INVOKING") == 2 and "SYNTH" in kinds and "UNRUN" in kinds


def test_script_a_failed_gate_sync_starts_nothing_and_the_marker_stops_the_next_start(script_world):
    world = script_world(three_calls("act"))
    first = world.run(ASK="1", launcher=True, FAIL_FSYNC_TYPE="05", FAIL_FSYNC_NTH="2")
    assert first.returncode == 44, first.stdout[-2000:] + first.stderr[-2000:]
    assert world.last_end()["reason"] == "persistence_failure"
    assert world.counts() == {"read_file": 1}, "the tool behind the failed INVOKING sync never started"
    assert (world.session_dir / "FSYNC_FAILED").exists()
    second = world.run(ASK="1")
    assert second.returncode == 44 and world.last_end()["reason"] == "diagnostic_stop"
    assert json.loads((world.session_dir / "STOPPED").read_text())["reason"] == "fsync_failed_previous_run"
    assert len(world.stub.bodies) == 1 and world.counts() == {"read_file": 1}, "no request, no tool while stopped"
    ack = world.run("--acknowledge-stop", "fsync_failed_previous_run", "--resolution", "continue-from-bound")
    assert ack.returncode == 0, ack.stdout + ack.stderr
    third = world.run(ASK="0")
    assert third.returncode == 0, third.stdout[-2000:] + third.stderr[-2000:]
    tools = [m["content"] for m in world.conversation() if m["role"] == "tool"]
    # O1-7: the INVOKING bytes are readable after a process-only restart, so
    # the call is unknown (never unrun), though it did not start.
    assert tools == ["x-contents", rp.UNKNOWN_TEXT, rp.UNRUN_TEXT]
    assert world.counts() == {"read_file": 1} and len(world.stub.bodies) == 1
    assert [r.type_name for r in world.records()].count("RECOVERY_ACK") == 1


def test_script_a_crash_with_a_request_in_flight_retries_under_a_new_attempt_label(script_world):
    import subprocess  # noqa: PLC0415
    import time  # noqa: PLC0415

    from stub_model import Reply  # noqa: PLC0415

    world = script_world([Reply(text="fine")], hold_first=True)
    process = subprocess.Popen(world.command(False), cwd=str(world.root / "work"), env=world.env(ASK="1"),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.time() + 30
    while not world.stub.bodies and time.time() < deadline:
        time.sleep(0.05)
    assert world.stub.bodies, "the request never arrived"
    process.kill()
    process.communicate(timeout=30)
    world.stub.release.set()
    first_label = world.stub.bodies[0][chassis.CORRELATION_KEY]
    lineage, turn, attempt = first_label.rsplit(":", 2)
    assert attempt == "1"
    second = world.run(ASK="1")
    assert second.returncode == 0, second.stdout[-2000:] + second.stderr[-2000:]
    assert world.stub.bodies[1][chassis.CORRELATION_KEY] == f"{lineage}:{turn}:2", "C-1a: the label is never reused"
    spend = [r for r in world.records() if r.type_name == "RECOVERY"]
    assert [r.payload["kind"] for r in spend] == ["possible_duplicate_spend"]
    sent = [r for r in world.records() if r.type_name == "REQUEST_SENT"]
    assert [r.payload["label"] for r in sent] == [first_label, f"{lineage}:{turn}:2"]


def test_script_an_ambiguous_tail_stops_until_acknowledged_then_continues_with_its_notices(script_world):
    from stub_model import Reply  # noqa: PLC0415

    world = script_world([Reply(text="fine")])
    assert world.run(ASK="1").returncode == 0
    lineage = json.loads((world.session_dir / "run.json").read_text())["lineage_id"]
    reserved = cs.read_identity(world.session_dir, lineage)
    segment = sorted((world.session_dir / "ledger").glob("*.svl"))[-1]
    with open(segment, "ab") as handle:
        handle.write(bytes(300))
    stopped = world.run(ASK="1")
    assert stopped.returncode == 44 and world.last_end()["note"] == "ledger_tail_ambiguous"
    assert len(world.stub.bodies) == 1 and segment.read_bytes().endswith(bytes(300)), "no request; nothing truncated"
    ack = world.run("--acknowledge-stop", "ledger_tail_ambiguous", "--resolution", "continue-conservative")
    assert ack.returncode == 0, ack.stdout + ack.stderr
    third = world.run(ASK="1")
    assert third.returncode == 0, third.stdout[-2000:] + third.stderr[-2000:]
    request = world.stub.bodies[1]
    assert any(str(m.get("content", "")).startswith("[runtime] records after ledger seq") for m in request["messages"])
    _lineage, turn, attempt = request[chassis.CORRELATION_KEY].rsplit(":", 2)
    assert (int(turn), attempt) == (reserved + 1, "1"), "above every turn the durable reservation covered (SV021-01)"


# ===========================================================================
# SV-021 correction 1: regressions for Astra SV021-01, -04, -05, -06
# (written and run against the reviewed code first; RECEIPT.md §6)
# ===========================================================================
def damage_from(path, first_seq: int, lineage: str | None = None) -> None:
    """Corrupt the header check (byte 33) of every frame with seq >= first_seq, in place."""
    segments = cp.read_segments(path.parent)
    records = cp.scan_segments(segments, lineage or st._segment_lineage(segments)).records
    data = bytearray(path.read_bytes())
    for record in records:
        if record.seq >= first_seq and record.segment == int(path.stem):
            offset = record.offset + 33
            data[offset] = ord("0") if data[offset] != ord("0") else ord("1")
    path.write_bytes(bytes(data))


def turn_of(label: str) -> int:
    return int(label.rsplit(":", 2)[1])


def test_sv021_01_a_second_smaller_ambiguous_tail_never_reuses_an_identity(tmp_path):
    """Astra SV021-01: two TC4 recoveries, the first large, the second small, a request between them."""
    root = Root(tmp_path)
    session = establish(root)
    session.close()
    prefix_end = root.records()[-1].seq
    append_raw(root, bytes(117_000))
    assert root.start().stop == "ledger_tail_ambiguous"
    st.acknowledge(root.session_dir, "ledger_tail_ambiguous", "continue-conservative")
    session = root.start().session
    first_label = session.next_label()
    session.send(lambda: None)  # a request under the skipped identity; the process then dies
    session.close()
    assert not (root.session_dir / st.RECOVERING).exists() and root.corrupt(), "the first recovery finished normally"
    damage_from(root.segment(), prefix_end + 1)
    opening = root.start()
    assert opening.stop == "ledger_tail_ambiguous"
    st.acknowledge(root.session_dir, "ledger_tail_ambiguous", "continue-conservative")
    opening = root.start()
    if opening.stop is not None:
        assert opening.stop == "identity_unproven", "only a fail-closed stop is acceptable"
        return
    assert turn_of(opening.session.next_label()) > turn_of(first_label), (
        f"{opening.session.next_label()} can reuse {first_label}"
    )


def test_sv021_04_one_deletion_is_consumed_once_across_restarts(tmp_path):
    """Astra SV021-04: a durable note adopted after a deletion survives restarts before any checkpoint."""
    root = Root(tmp_path)
    session = establish(root)
    session.write_note("N", header="# Handoff")
    session.checkpoint()
    session.close()
    (root.session_dir / "conversation.json").unlink()
    opening = root.start()
    assert opening.classification == "A12"
    session = opening.session
    session.adopt_file_edit()
    session.adopt_notes()
    session.append_message("user", "after the deletion")
    session.close()  # dies before any checkpoint
    for _restart in range(2):
        opening = root.start()
        contents = [m["content"] for m in opening.session.messages]
        assert contents == [rp.NOTE_PREFIX + "# Handoff\n\nN\n", "after the deletion"], contents
        assert opening.session.state.history_epoch == 2 and root.types().count("EXTERNAL_DELETE") == 1
        opening.session.close()
    session = resume(root.start())  # installs a conversation and checkpoints it
    session.close()
    (root.session_dir / "conversation.json").unlink()
    opening = root.start()
    assert opening.classification == "A12" and opening.session.state.history_epoch == 3
    assert root.types().count("EXTERNAL_DELETE") == 2, "a later real deletion is still a deletion"


def write_list(root: Root, contents: list[str]) -> None:
    messages = [{"role": "user", "content": text} for text in contents]
    (root.session_dir / "conversation.json").write_text(json.dumps(messages, indent=2) + "\n")


def test_sv021_05_an_edit_back_to_an_earlier_source_is_still_an_edit(tmp_path):
    """Astra SV021-05: X -> Y -> X across pre-checkpoint startups."""
    root = Root(tmp_path)
    establish(root).close()
    for step, (contents, epoch) in enumerate([(["X"], 2), (["Y"], 3), (["X"], 4)]):
        write_list(root, contents)
        opening = root.start()
        assert opening.classification == "A11", (step, opening.classification)
        assert [m["content"] for m in opening.session.messages] == contents
        assert opening.session.state.history_epoch == epoch
        opening.session.close()
    opening = root.start()  # the file is unchanged since the last adoption
    assert [m["content"] for m in opening.session.messages] == ["X"]
    assert root.types().count("EXTERNAL_EDIT") == 3, "no duplicate transition for an unchanged file"


def start_33(root: Root):
    session = establish(root)
    session.send(lambda: None)
    adoption = adopt_response(
        RawResponse("", None, tuple(RawCall(f"c{i}", "read_file", "{}") for i in range(33))),
        session.state.requests_last["turn_seq"],
    )
    session.adopt(adoption)
    return session, adoption


OMITTED_33 = "[runtime] the response contained 33 tool calls; calls 33–33 were not stored or run"


def assert_one_notice(root: Root, text: str) -> None:
    for _restart in range(2):
        opening = root.start()
        assert opening.session is not None, opening
        contents = [m["content"] for m in opening.session.messages]
        assert contents.count(text) == 1, contents[-4:]
        opening.session.close()
    session = resume(root.start())
    assert [m["content"] for m in session.messages].count(text) == 1


def test_sv021_06_an_omitted_calls_notice_survives_a_crash_after_the_last_done(tmp_path):
    root = Root(tmp_path)
    session, adoption = start_33(root)
    for call in adoption.calls:
        if call.admit == "invoke":
            session.invoke(call, lambda: None)
            session.record_result(call, "returned", "r")
    session.close()  # dies before the group's flush
    assert_one_notice(root, OMITTED_33)
    tools = [m for m in resume(root.start()).messages if m["role"] == "tool"]
    assert len(tools) == 32, "stored calls answered once; the omitted call gets no answer"


def test_sv021_06_an_omitted_calls_notice_survives_a_crash_inside_a_tool(tmp_path):
    root = Root(tmp_path)
    session, adoption = start_33(root)
    session.invoke(adoption.calls[0], lambda: None)
    session.close()  # dies inside the first tool
    assert_one_notice(root, OMITTED_33)
    assert [r.type_name for r in root.records()].count("INVOKING") == 1, "nothing invoked again"


def test_sv021_06_a_refusal_notice_survives_a_crash_after_response_refused(tmp_path, monkeypatch):
    import contextlib  # noqa: PLC0415

    root = Root(tmp_path)
    session = establish(root)
    session.send(lambda: None)
    adoption = adopt_response(
        RawResponse("", None, tuple(RawCall(f"c{i}", "read_file", "{}") for i in range(257))),
        session.state.requests_last["turn_seq"],
    )

    def die(*_args, **_kwargs):
        raise Crash()

    monkeypatch.setattr(session, "_append", die)  # process death after RESPONSE_REFUSED, if a later write exists
    with contextlib.suppress(Crash):
        session.adopt(adoption)
    session.close()
    assert "RESPONSE_REFUSED" in root.types()
    assert_one_notice(root, adoption.notice)


def test_sv021_01_script_a_second_ambiguous_tail_never_reuses_an_observed_label(script_world):
    """Astra SV021-01 with real processes: the first skipped label is observed by the stub, then lost."""
    import subprocess  # noqa: PLC0415
    import time  # noqa: PLC0415

    from stub_model import Reply  # noqa: PLC0415

    world = script_world([Reply(text="fine")], hold_request=2)
    assert world.run(ASK="1").returncode == 0
    prefix_end = world.records()[-1].seq
    segment = sorted((world.session_dir / "ledger").glob("*.svl"))[-1]
    with open(segment, "ab") as handle:
        handle.write(bytes(117_000))
    assert world.run(ASK="1").returncode == 44
    assert world.run("--acknowledge-stop", "ledger_tail_ambiguous", "--resolution", "continue-conservative").returncode == 0
    process = subprocess.Popen(world.command(False), cwd=str(world.root / "work"), env=world.env(ASK="1"),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.time() + 30
    while len(world.stub.bodies) < 2 and time.time() < deadline:
        time.sleep(0.05)
    assert len(world.stub.bodies) == 2, "the request under the skipped identity never arrived"
    process.kill()
    process.communicate(timeout=30)
    world.stub.release.set()
    observed = world.stub.bodies[1][chassis.CORRELATION_KEY]
    segment = sorted((world.session_dir / "ledger").glob("*.svl"))[-1]
    damage_from(segment, prefix_end + 1)
    assert world.run(ASK="1").returncode == 44 and world.last_end()["note"] == "ledger_tail_ambiguous"
    assert world.run("--acknowledge-stop", "ledger_tail_ambiguous", "--resolution", "continue-conservative").returncode == 0
    final = world.run(ASK="1")
    if final.returncode == 44:
        assert world.last_end()["note"] == "identity_unproven" and len(world.stub.bodies) == 2
        return
    assert final.returncode == 0, final.stdout[-2000:] + final.stderr[-2000:]
    sent = world.stub.bodies[2][chassis.CORRELATION_KEY]
    assert turn_of(sent) > turn_of(observed), f"{sent} can reuse the observed {observed}"


# -- SV021-01: the reservation itself (post-fix behaviour, fail-closed cases) --
def two_tc4(root: Root):
    """The SV021-01 trace up to the second acknowledgement; returns the first skipped label."""
    session = establish(root)
    session.close()
    prefix_end = root.records()[-1].seq
    append_raw(root, bytes(117_000))
    root.start()
    st.acknowledge(root.session_dir, "ledger_tail_ambiguous", "continue-conservative")
    session = root.start().session
    label = session.next_label()
    session.send(lambda: None)
    session.close()
    damage_from(root.segment(), prefix_end + 1)
    root.start()
    st.acknowledge(root.session_dir, "ledger_tail_ambiguous", "continue-conservative")
    return label


def test_sv021_01_with_a_valid_reservation_the_second_recovery_continues_above_it(tmp_path):
    root = Root(tmp_path)
    first = two_tc4(root)
    reserved = cs.read_identity(root.session_dir, LINEAGE)
    assert reserved >= turn_of(first), "the first skipped turn was reserved before its request"
    opening = root.start()
    assert opening.stop is None
    assert opening.session.state.requests_next == {"turn_seq": reserved + 1, "attempt": 1}
    sent = [r.payload["turn_seq"] for r in root.records() if r.type_name == "REQUEST_SENT"]
    assert max(sent) < reserved + 1 and cs.read_identity(root.session_dir, LINEAGE) >= reserved + 1


@pytest.mark.parametrize("damage", ["missing", "bad-check", "foreign-lineage"])
def test_sv021_01_without_a_valid_reservation_an_ambiguous_tail_stops_and_changes_nothing(tmp_path, damage):
    root = Root(tmp_path)
    two_tc4(root)
    path = root.session_dir / cs.IDENTITY
    if damage == "missing":
        path.unlink()
    elif damage == "bad-check":
        path.write_text(path.read_text().replace('"turns_reserved_through": ', '"turns_reserved_through": 1'))
    else:
        path.write_bytes(cs.identity_bytes("another", 10**9))
    before = root.snapshot()
    opening = root.start()
    assert (opening.stop, opening.session) == ("identity_unproven", None)
    after = root.snapshot()
    stopped = after.pop("session/STOPPED")
    assert json.loads(stopped)["reason"] == "identity_unproven"
    before.pop("session/ACKNOWLEDGED", None)
    after.pop("session/ACKNOWLEDGED", None)
    assert after == before, "no truncation, no intent, no record, no new identity"


def test_sv021_01_a_crash_during_the_reservation_sends_nothing(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    session.identity_reserved = session.state.requests_next["turn_seq"] - 1  # force a reservation write
    ops = FaultOps()
    session.ops = ops
    ops.faults.append(("rename", lambda p: p.endswith("/" + cs.IDENTITY), Crash()))
    sent = []
    with pytest.raises(Crash):
        session.send(lambda: sent.append(1))
    session.close()
    assert sent == [] and root.types().count("REQUEST_SENT") == 1, "neither the record nor the request"
    assert cs.read_identity(root.session_dir, LINEAGE) is not None, "the old reservation is intact"
    opening = root.start()
    assert opening.stop is None and opening.session.state.requests_next["turn_seq"] == 2


def test_sv021_01_a_damaged_reservation_with_a_clean_ledger_is_rebuilt_from_it(tmp_path):
    root = Root(tmp_path)
    establish(root).close()
    (root.session_dir / cs.IDENTITY).write_text("{torn")
    opening = root.start()
    assert opening.stop is None
    assert cs.read_identity(root.session_dir, LINEAGE) >= opening.session.state.requests_next["turn_seq"]


# -- SV021-05: a legacy reimport followed by an edit, and an unpublished import followed by one --
def test_sv021_05_a_rollback_then_an_edit_is_adopted_and_then_stable(tmp_path):
    root = Root(tmp_path)
    establish(root).close()
    meta = json.loads(root.file("run.json"))
    for key in ("format", "writer", "checkpoint", "history_epoch"):
        meta.pop(key)
    (root.session_dir / "run.json").write_text(json.dumps(meta))
    write_list(root, ["old runtime"])
    assert root.start().classification == "A8"
    write_list(root, ["edited after the reimport"])
    opening = root.start()
    assert opening.classification == "A8" and [m["content"] for m in opening.session.messages] == ["edited after the reimport"]
    opening.session.close()
    opening = root.start()
    assert opening.classification == "A8t" and root.types().count("LEGACY_REIMPORT") == 2


def test_sv021_05_an_edit_after_an_unpublished_import_is_an_edit(tmp_path):
    root = Root(tmp_path)
    write_list(root, ["legacy"])
    root.start().session.close()  # LEGACY_IMPORT; no checkpoint yet
    write_list(root, ["edited"])
    opening = root.start()
    assert opening.classification == "A11" and [m["content"] for m in opening.session.messages] == ["edited"]
    opening.session.close()
    assert root.start().classification == "A9t"


# -- SV021-06: the 256-call cut right after TURN_RESPONSE --
def test_sv021_06_a_256_call_response_owes_its_notice_from_turn_response_on(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    session.send(lambda: None)
    session.adopt(adopt_response(
        RawResponse("", None, tuple(RawCall(f"c{i}", "read_file", "{}") for i in range(256))),
        session.state.requests_last["turn_seq"],
    ))
    session.close()  # dies right after TURN_RESPONSE, before any tool
    assert_one_notice(root, "[runtime] the response contained 256 tool calls; calls 33–256 were not stored or run")
    assert "INVOKING" not in root.types(), "recovery invoked nothing"
    checkpoints = [r for r in root.records() if r.type_name == "CHECKPOINT"]
    assert checkpoints[-1].payload["state"]["active_group"] is None
