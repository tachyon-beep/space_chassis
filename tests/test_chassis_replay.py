"""The pure replay reducer (SV-015 v2 1.4.4) and its state (1.4.2).

FX-C BASE/turn-7 shapes (SV-013 section 3.5) driven through
`chassis_replay.Replay` directly: exact messages and key order, out-of-order
refusals, admission-text answers, note generations, history replacement,
originals retention. Every record payload here is first checked by the
accepted `chassis_persistence.validate_payload`, so the fixtures are records
the scanner would accept. No files, no ledger, no recovery decisions: those
are `test_chassis_session.py` and `test_chassis_recovery_live.py`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))

import chassis_persistence as cp  # noqa: E402
import chassis_replay as rp  # noqa: E402
from chassis_replay import Replay, ReplayMismatch, SessionState  # noqa: E402

READ = "x-contents"
WROTE = "wrote 1 characters to /work/y"
BASE = [{"role": "user", "content": "OPENING"}, {"role": "assistant", "content": "ok"}]
R7 = {
    "role": "assistant",
    "content": "",
    "tool_calls": [
        {"id": "call_a", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"x"}'}},
        {"id": "call_b", "type": "function", "function": {"name": "write_file", "arguments": '{"path":"y","text":"z"}'}},
    ],
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def call(index, wire, name, admit="invoke", text=None):
    entry = {
        "call_index": index,
        "provider_id_repr": {"type": "str", "E": len(wire), "sha256": "0" * 64},
        "wire_id": wire,
        "name": name,
        "args_sha256": "0" * 64,
        "args_E": 2,
        "admit": admit,
    }
    if text is not None:
        entry["admit_text"] = text
    return entry


R7_CALLS = [call(0, "call_a", "read_file"), call(1, "call_b", "write_file")]


class Blobs(dict):
    def put(self, data: bytes) -> str:
        key = sha(data)
        self[key] = data
        return key

    def read(self, key):
        return self.get(key)


class Feed:
    """Records with consecutive seqs, each payload validated as the scanner would."""

    def __init__(self, start: int = 21) -> None:
        self.seq = start - 1

    def __call__(self, type_name: str, payload: dict) -> cp.Record:
        assert cp.validate_payload(type_name, payload) is None, (type_name, cp.validate_payload(type_name, payload))
        # Round-trip through the canonical body, as a record read back from disk would be.
        payload = json.loads(cp.canonical_body(payload))
        self.seq += 1
        return cp.Record(self.seq, type_name, payload, "0" * 64, 0, 0, 0)


def turn7_state() -> SessionState:
    return SessionState(lineage_id="0f1e", requests_next={"turn_seq": 7, "attempt": 1})


def turn7_records(blobs: Blobs, feed: Feed, through: int = 26) -> list:
    records = [
        feed("REQUEST_SENT", {"turn_seq": 7, "attempt": 1, "label": "0f1e:7:1"}),
        feed("TURN_RESPONSE", {"turn_seq": 7, "assistant": R7, "calls": R7_CALLS, "normalization": {}, "original_blobs": []}),
        feed("INVOKING", {"turn_seq": 7, "call_index": 0}),
        feed("DONE", done(blobs, 7, 0, READ)),
        feed("INVOKING", {"turn_seq": 7, "call_index": 1}),
        feed("DONE", done(blobs, 7, 1, WROTE)),
    ]
    return [r for r in records if r.seq <= through]


def done(blobs: Blobs, turn: int, index: int, text: str, outcome: str = "returned") -> dict:
    data = text.encode()
    return {
        "turn_seq": turn, "call_index": index, "outcome": outcome, "blob": blobs.put(data),
        "original_bytes": len(data), "stored_E": len(text), "truncated": False, "replaced_chars": 0,
    }


def T(call_id, name, text):  # noqa: N802 -- the fixture tables' shorthand
    return {"role": "tool", "tool_call_id": call_id, "name": name, "content": text}


def run(records, blobs, messages=None, state=None) -> Replay:
    replay = Replay(copy.deepcopy(messages if messages is not None else BASE), state or turn7_state(), blobs.read)
    for record in records:
        replay.apply(record)
    return replay


# ---------------------------------------------------------------------------
# A complete turn
# ---------------------------------------------------------------------------
def test_a_complete_turn_replays_to_the_exact_list_and_bytes():
    blobs = Blobs()
    replay = run(turn7_records(blobs, Feed()), blobs)
    expected = [*BASE, R7, T("call_a", "read_file", READ), T("call_b", "write_file", WROTE)]
    assert replay.messages == expected and replay.group is None
    # Key order matters for the bytes: the ledger body is key-sorted, the file is not.
    assert rp.conversation_bytes(replay.messages) == (json.dumps(expected, indent=2) + "\n").encode()
    assert list(replay.messages[2]) == ["role", "content", "tool_calls"]
    assert list(replay.messages[2]["tool_calls"][0]) == ["id", "type", "function"]
    state = replay.state
    assert state.requests_last == {"turn_seq": 7, "attempt": 1, "label": "0f1e:7:1", "outcome": "responded"}
    assert state.requests_next == {"turn_seq": 8, "attempt": 1}


def test_base_bytes_match_the_fx_c_literal():
    data = rp.conversation_bytes(BASE)
    assert len(data) == 111 and sha(data) == "31a46ba1e3fb0b28dabb60db182d4a24266a56ebf6a3dc624322ca2a1018b4de"


@pytest.mark.parametrize("through", [21, 22, 23, 24, 25], ids=["c-1a", "c-1b", "c-1c", "c-1d", "c-1e"])
def test_a_partial_turn_leaves_exactly_what_its_records_say(through):
    """The reducer alone: closure of the open group is recovery's (test_chassis_recovery_live)."""
    blobs = Blobs()
    replay = run(turn7_records(blobs, Feed(), through), blobs)
    expected_tail = {21: [], 22: [R7], 23: [R7], 24: [R7, T("call_a", "read_file", READ)], 25: [R7, T("call_a", "read_file", READ)]}
    assert replay.messages == [*BASE, *expected_tail[through]]
    if through == 21:
        assert replay.state.requests_last["outcome"] == "failed_unknown"
        assert replay.state.requests_next == {"turn_seq": 7, "attempt": 2}, "attempt+1 after a request with no response"
    else:
        assert replay.group is not None and replay.group.answered == (1 if through >= 24 else 0)


def test_c_d3_a_missing_done_blob_says_what_kind_of_outcome_was_lost():
    blobs = Blobs()
    feed = Feed()
    records = turn7_records(blobs, feed, 23) + [feed("DONE", done(blobs, 7, 0, "error: ValueError: boom", "raised:ValueError"))]
    blobs.clear()
    replay = run(records, blobs)
    assert replay.messages[-1] == T(
        "call_a",
        "read_file",
        "this call raised ValueError; its stored error text (23 bytes, sha256 "
        "34a19b10151df6f90ebde3dc097d33b2191107b5c4ca737051e1c0b400bdb75f) could not be recovered",
    )
    returned = rp.returned_lost_text(10, sha(READ.encode()))
    assert returned.startswith("this call returned 10 bytes (sha256 67b48901")


# ---------------------------------------------------------------------------
# Order refusals
# ---------------------------------------------------------------------------
def bad(records, blobs, state=None):
    with pytest.raises(ReplayMismatch):
        run(records, blobs, state=state)


def test_order_violations_are_refused_not_guessed():
    blobs = Blobs()
    feed = Feed()
    r21, r22, r23, r24 = turn7_records(blobs, feed, 24)
    bad([r21, r22, r24], blobs)  # DONE without INVOKING
    feed = Feed(23)
    bad([r21, r22, feed("INVOKING", {"turn_seq": 7, "call_index": 1})], blobs)  # skips the frontier call
    feed = Feed(23)
    bad([r21, r22, feed("MSG_APPEND", {"kind": "user", "text": "x", "epoch": 1})], blobs)  # inside the group
    feed = Feed(23)
    bad([r21, r22, feed("UNRUN", {"call_key": [7, 1], "reason": "x"})], blobs)  # answers call 1 before call 0
    feed = Feed(21)
    bad([feed("REQUEST_SENT", {"turn_seq": 8, "attempt": 1, "label": "0f1e:8:1"})], blobs)  # not the next identity
    feed = Feed(21)
    bad([feed("TURN_RESPONSE", {"turn_seq": 7, "assistant": R7, "calls": R7_CALLS, "normalization": {}, "original_blobs": []})], blobs)


def test_unrun_and_synth_answer_with_their_fixed_texts():
    blobs = Blobs()
    feed = Feed(23)
    records = turn7_records(blobs, Feed(), 22) + [
        feed("SYNTH", {"call_key": [7, 0], "kind": "unknown_damaged_tail"}),
        feed("UNRUN", {"call_key": [7, 1], "reason": rp.UNRUN_TEXT}),
    ]
    replay = run(records, blobs)
    assert replay.messages[-2:] == [T("call_a", "read_file", rp.DAMAGED_TAIL_TEXT), T("call_b", "write_file", rp.UNRUN_TEXT)]
    assert replay.group is None


# ---------------------------------------------------------------------------
# Calls that were never admitted for invocation
# ---------------------------------------------------------------------------
def test_not_invoked_calls_are_answered_by_their_admission_text_in_call_order():
    calls = [
        call(0, "c0", "read_file"),
        call(1, "c1", "read_file", "bad_args", "error: arguments must be a json object"),
        call(2, "c2", "read_file"),
        call(3, "c3", "read_file", "not_run_call_limit", "not run: the call limit was reached"),
    ]
    assistant = {"role": "assistant", "content": "", "tool_calls": [
        {"id": c["wire_id"], "type": "function", "function": {"name": "read_file", "arguments": "{}"}} for c in calls]}
    blobs = Blobs()
    feed = Feed()
    records = [
        feed("REQUEST_SENT", {"turn_seq": 7, "attempt": 1, "label": "0f1e:7:1"}),
        feed("TURN_RESPONSE", {"turn_seq": 7, "assistant": assistant, "calls": calls, "normalization": {}, "original_blobs": []}),
        feed("INVOKING", {"turn_seq": 7, "call_index": 0}),
        feed("DONE", done(blobs, 7, 0, READ)),
    ]
    replay = run(records, blobs)
    assert [m["content"] for m in replay.messages[3:]] == [READ, "error: arguments must be a json object"]
    assert replay.group is not None and replay.group.next_call()["call_index"] == 2
    records += [feed("INVOKING", {"turn_seq": 7, "call_index": 2}), feed("DONE", done(blobs, 7, 2, READ))]
    replay = run(records, blobs)
    assert [m["tool_call_id"] for m in replay.messages[3:]] == ["c0", "c1", "c2", "c3"]
    assert replay.messages[-1]["content"] == "not run: the call limit was reached"
    assert replay.group is None, "the group closes at its last invokable call (the accepted frontier's rule)"
    assert cp.prefix_state(tuple(records)).group is None


def test_a_response_whose_calls_are_all_refused_closes_at_once():
    calls = [call(0, "c0", "", "bad_name", "error: the tool name was refused (empty); the call was not run")]
    assistant = {"role": "assistant", "content": "", "tool_calls": [{"id": "c0", "type": "function", "function": {"name": "", "arguments": "{}"}}]}
    blobs = Blobs()
    feed = Feed()
    replay = run([
        feed("REQUEST_SENT", {"turn_seq": 7, "attempt": 1, "label": "0f1e:7:1"}),
        feed("TURN_RESPONSE", {"turn_seq": 7, "assistant": assistant, "calls": calls, "normalization": {}, "original_blobs": []}),
    ], blobs)
    assert replay.group is None and replay.messages[-1]["content"].startswith("error: the tool name was refused")


# ---------------------------------------------------------------------------
# Notes (C-N2, swallowed handoffs, foreign adoption)
# ---------------------------------------------------------------------------
def note_written(blobs: Blobs, gen: int, text: str, source="runtime") -> dict:
    data = text.encode()
    key = blobs.put(data)
    return {"gen": gen, "blob": key, "bytes": len(data), "sha256": key, "source": source, "mirror_sha256": key}


def test_c_n2_equal_text_generations_stay_distinct_and_are_both_adopted():
    blobs = Blobs()
    feed = Feed()
    state = turn7_state()
    first, second = note_written(blobs, 1, "check pump"), note_written(blobs, 2, "check pump")
    records = [feed("NOTE_WRITTEN", first), feed("NOTE_WRITTEN", second)]
    replay = run(records, blobs, state=state)
    assert [e["gen"] for e in replay.state.notes_pending] == [1, 2] and replay.state.notes_next_gen == 3
    assert replay.state.mirror_sha256s() == [first["mirror_sha256"], second["mirror_sha256"]]
    records += [
        feed("MSG_APPEND", {"kind": "note", "gen": 1, "blob": first["blob"], "epoch": 1}),
        feed("MSG_APPEND", {"kind": "note", "gen": 2, "blob": second["blob"], "epoch": 1}),
    ]
    replay = run(records, blobs, state=turn7_state())
    assert replay.messages[-2:] == [rp.note_message("check pump")] * 2
    assert replay.state.notes_adopted_through == 2 and replay.state.notes_pending == []
    assert replay.state.mirror_sha256s() == [second["mirror_sha256"]], "only the newest adopted mirror is kept"


def test_note_adoption_is_in_generation_order_only():
    blobs = Blobs()
    feed = Feed()
    one, two = note_written(blobs, 1, "N1"), note_written(blobs, 2, "N2")
    with pytest.raises(ReplayMismatch):
        run([feed("NOTE_WRITTEN", one), feed("NOTE_WRITTEN", two), feed("MSG_APPEND", {"kind": "note", "gen": 2, "blob": two["blob"], "epoch": 1})], blobs)
    feed = Feed()
    with pytest.raises(ReplayMismatch):
        run([feed("NOTE_WRITTEN", two)], blobs)


def test_a_foreign_adoption_advances_the_watermark_without_appending():
    blobs = Blobs()
    feed = Feed()
    one = note_written(blobs, 1, "N1")
    replay = run([feed("NOTE_WRITTEN", one), feed("MSG_APPEND", {"kind": "note", "gen": 1, "blob": one["blob"], "epoch": 1, "foreign": True})], blobs)
    assert replay.messages == BASE and replay.state.notes_adopted_through == 1


def test_a_drop_and_its_notice_are_both_records():
    blobs = Blobs()
    feed = Feed()
    notice = rp.DROPPED_NOTE_NOTICE.format(count=16)
    replay = run([feed("RECOVERY", {"kind": "note_dropped_pending_limit", "detail": {"bytes": 3}})], blobs)
    assert replay.state.notes_dropped == 1
    replay = run([
        Feed(21)("RECOVERY", {"kind": "note_dropped_pending_limit", "detail": {"bytes": 3}}),
        Feed(22)("MSG_APPEND", {"kind": "notice", "text": notice, "epoch": 1, "reports": "note_dropped_pending_limit"}),
    ], blobs)
    assert replay.state.notes_dropped == 0 and replay.messages[-1] == {"role": "user", "content": notice}


# ---------------------------------------------------------------------------
# History replacement and base switches
# ---------------------------------------------------------------------------
def test_history_replaced_installs_the_blob_and_bounds_the_fold():
    blobs = Blobs()
    new = [{"role": "user", "content": "OPENING"}]
    data = rp.conversation_bytes(new)
    state = turn7_state()
    state.recap_folded = 2
    feed = Feed()
    replay = run([feed("HISTORY_REPLACED", {"epoch": 2, "new_blob": blobs.put(data), "new_count": 1, "new_sha256": sha(data)})], blobs, state=state)
    assert replay.messages == new and replay.state.history_epoch == 2 and replay.state.recap_folded == 1
    with pytest.raises(ReplayMismatch):
        run([Feed()("HISTORY_REPLACED", {"epoch": 3, "new_blob": sha(data), "new_count": 1, "new_sha256": sha(data)})], blobs)
    with pytest.raises(ReplayMismatch, match="missing"):
        run([Feed()("HISTORY_REPLACED", {"epoch": 2, "new_blob": "1" * 64, "new_count": 1, "new_sha256": sha(data)})], blobs)


def test_external_edit_delete_and_reimport_switch_the_base():
    blobs = Blobs()
    edited = [{"role": "user", "content": "NEW"}]
    key = blobs.put(rp.conversation_bytes(edited))
    replay = run([Feed()("EXTERNAL_EDIT", {"epoch": 2, "conv_sha": key, "blob": key, "recap_folded": 0})], blobs)
    assert replay.messages == edited and replay.state.history_epoch == 2
    replay = run([Feed()("EXTERNAL_DELETE", {"epoch": 2})], blobs)
    assert replay.messages == [] and replay.state.recap_folded == 0
    replay = run([Feed()("LEGACY_REIMPORT", {"epoch": 2, "conv_sha": key, "unmerged_suffix": None, "blob": key, "recap_folded": 1})], blobs)
    assert replay.messages == edited and replay.state.recap_folded == 1


# ---------------------------------------------------------------------------
# Originals retention (v2 1.4.6: 4 MiB, 64 items, 256 KiB each)
# ---------------------------------------------------------------------------
def test_originals_are_retained_fifo_within_count_and_bytes():
    kept = rp.retain_originals([], [{"sha256": f"{i:064x}", "bytes": 1, "kind": "args", "turn_seq": 1} for i in range(65)])
    assert len(kept) == 64 and kept[0]["sha256"] == f"{1:064x}"
    big = [{"sha256": f"{i:064x}", "bytes": 256 * 1024, "kind": "args", "turn_seq": 1} for i in range(17)]
    kept = rp.retain_originals([], big)
    assert len(kept) == 16 and sum(e["bytes"] for e in kept) == 4 * 1024 * 1024


# ---------------------------------------------------------------------------
# CHECKPOINT state wire form
# ---------------------------------------------------------------------------
def full_state() -> SessionState:
    state = turn7_state()
    state.notes_pending = [
        {"gen": 2, "blob": "a" * 64, "bytes": 3, "source": "runtime", "written_seq": 33, "mirror_sha256": "b" * 64},
        {"gen": 3, "blob": "c" * 64, "bytes": 3, "source": "runtime", "written_seq": 36, "mirror_sha256": "d" * 64},
    ]
    state.notes_adopted_through, state.notes_next_gen, state.adopted_mirror_sha256 = 1, 4, "e" * 64
    state.originals = [{"sha256": "f" * 64, "bytes": 10, "kind": "args", "turn_seq": 7}]
    return state


def test_the_state_round_trips_with_the_v2_keys():
    wire = full_state().to_wire(next_seq=43)
    assert {"lineage_id", "next_seq", "next_turn_seq", "history_epoch", "recap_folded", "requests", "notes",
            "legacy", "originals", "active_group", "queued", "blobs_live"} <= set(wire)
    assert wire["notes"]["mirror_sha256s"] == ["e" * 64, "b" * 64, "d" * 64]
    assert wire["blobs_live"] == ["a" * 64, "c" * 64, "f" * 64]
    assert cp.validate_payload("CHECKPOINT", {"covers_seq": 41, "chain_at_cover": "0" * 64, "conv": {}, "prev": None, "run_sha256": "0" * 64, "state": wire}) is None
    assert SessionState.from_wire(json.loads(json.dumps(wire))).to_wire(43) == wire


@pytest.mark.parametrize(
    "mutate",
    [
        lambda w: w["notes"]["pending"].pop(0),  # gap after adopted_through
        lambda w: w["notes"]["mirror_sha256s"].pop(),
        lambda w: w.update(active_group={"turn_seq": 7}),
        lambda w: w.update(queued=[{"role": "user"}]),
        lambda w: w.update(history_epoch=10**12),
        lambda w: w.update(history_epoch=True),
        lambda w: w["requests"]["next"].update(turn_seq=9),
        lambda w: w["blobs_live"].append("9" * 64),
        lambda w: w["originals"].extend([{"sha256": "f" * 64, "bytes": 1, "kind": "args", "turn_seq": 1}] * 64),
        lambda w: w["legacy"].update(status="maybe"),
        lambda w: w.pop("notes"),
    ],
    ids=["pending-gap", "mirrors", "active-group", "queued", "epoch-13-digits", "epoch-bool", "next-turn", "blobs-live", "originals-65", "legacy", "missing-notes"],
)
def test_a_state_outside_its_schema_is_refused(mutate):
    wire = json.loads(json.dumps(full_state().to_wire(43)))
    mutate(wire)
    with pytest.raises(rp.StateError):
        SessionState.from_wire(wire)
