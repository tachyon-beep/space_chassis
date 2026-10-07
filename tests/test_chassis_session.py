"""The session owner (SV-021 checkpoint C): gates, blobs, failure boundary, CK1-CK6, thresholds.

Every test drives `chassis_session.Session` in a temporary root and then
re-reads what is durable: the ledger is scanned with the accepted scanner and
replayed from an empty base with the same reducer, and the result must equal
the live session's messages and state (`assert_replays`). Faults are injected
through the accepted `FaultOps`; nothing here is a process restart (those are
in `test_chassis_recovery_live.py`) and nothing is a power-loss experiment.
"""

from __future__ import annotations

import hashlib
import json

import chassis_envelope as envelope
import chassis_persistence as cp
import chassis_replay as rp
import chassis_session as cs
import pytest
from chassis_envelope import RawCall, RawResponse, adopt_response
from test_chassis_durability import FaultOps, eio

LINEAGE = "0f1e"


def open_fresh(tmp_path, ops=None, **kwargs) -> cs.Session:
    (tmp_path / "session").mkdir(exist_ok=True)
    (tmp_path / "home").mkdir(exist_ok=True)
    return cs.Session.start_fresh(tmp_path / "session", tmp_path / "home", LINEAGE, ops=ops, **kwargs)


def ledger(session: cs.Session) -> cp.LedgerScan:
    return cp.scan_segments(cp.read_segments(session.session_dir / "ledger"), LINEAGE)


def types(session: cs.Session) -> list[str]:
    return [record.type_name for record in ledger(session).records]


def assert_replays(session: cs.Session) -> rp.Replay:
    """Durable ledger, replayed from scratch, equals the live session."""
    scan = ledger(session)
    assert scan.tail == b"" and scan.stop is None
    replay = rp.Replay([], rp.SessionState(LINEAGE), cp.BlobStore(session.session_dir / "blobs").get)
    for record in scan.records:
        replay.apply(record)
    assert replay.messages == session.messages
    assert rp.conversation_bytes(replay.messages) == rp.conversation_bytes(session.messages)
    assert replay.state.to_wire(1) == session.state.to_wire(1)
    assert (replay.group is None) == (session.group is None)
    return replay


def response(calls=(), content="") -> RawResponse:
    return RawResponse(content, None, tuple(RawCall(*call) for call in calls))


def turn(session, calls=(), *, content="", result=lambda call: f"result-{call.index}"):
    session.send(lambda: None)
    adoption = adopt_response(response(calls, content), session.state.requests_last["turn_seq"], session.caps)
    session.adopt(adoption)
    for call in adoption.calls:
        if call.admit == "invoke":
            session.invoke(call, lambda: None)
            session.record_result(call, "returned", result(call))
    session.flush()
    return adoption


TWO = [("call_a", "read_file", '{"path": "x"}'), ("call_b", "write_file", '{"path": "y", "text": "z"}')]


# ---------------------------------------------------------------------------
# Live state equals replay
# ---------------------------------------------------------------------------
def test_a_session_replays_exactly_and_its_checkpoint_binds_the_file(tmp_path):
    session = open_fresh(tmp_path)
    session.meta_source = lambda: {"agent": "a", "turn": 1}
    session.append_message("user", "OPENING")
    turn(session, TWO)
    record = session.checkpoint()
    assert types(session) == [
        "LEDGER_HEADER", "MSG_APPEND", "REQUEST_SENT", "TURN_RESPONSE",
        "INVOKING", "DONE", "INVOKING", "DONE", "CHECKPOINT",
    ]
    assert_replays(session)
    saved = (session.session_dir / "conversation.json").read_bytes()
    assert saved == rp.conversation_bytes(session.messages)
    assert record.payload["conv"] == {"sha256": hashlib.sha256(saved).hexdigest(), "bytes": len(saved)}
    meta = json.loads((session.session_dir / "run.json").read_bytes())
    assert (meta["format"], meta["writer"], meta["lineage_id"], meta["agent"]) == (2, "chassis-2", LINEAGE, "a")
    assert meta["checkpoint"] == {"covers_seq": record.seq - 1, "conv": record.payload["conv"], "prev": None, "epoch": 1}
    assert record.payload["run_sha256"] == hashlib.sha256((session.session_dir / "run.json").read_bytes()).hexdigest()
    assert record.payload["state"]["next_seq"] == record.seq + 1


def test_a_second_checkpoint_names_the_first_as_prev_and_keeps_the_old_file(tmp_path):
    session = open_fresh(tmp_path)
    session.append_message("user", "OPENING")
    first = session.checkpoint()
    first_bytes = (session.session_dir / "conversation.json").read_bytes()
    turn(session, content="ok")
    second = session.checkpoint()
    assert second.payload["prev"] == {
        "covers_seq": first.payload["covers_seq"],
        "conv_sha256": first.payload["conv"]["sha256"],
        "conv_bytes": first.payload["conv"]["bytes"],
        "checkpoint_seq": first.seq,
    }
    assert (session.session_dir / "conversation.prev.json").read_bytes() == first_bytes


def test_the_label_is_lineage_turn_attempt_and_the_request_is_identified_before_bytes(tmp_path):
    session = open_fresh(tmp_path)
    seen = []
    session.send(lambda: seen.append(types(session)[-1]))
    assert seen == ["REQUEST_SENT"], "the effect ran after REQUEST_SENT was durable"
    assert ledger(session).records[-1].payload == {"turn_seq": 1, "attempt": 1, "label": "0f1e:1:1"}
    assert session.next_label() == "0f1e:1:2", "a request with no recorded response is retried as attempt+1"


# ---------------------------------------------------------------------------
# Effect gates and the failure boundary (O1-7; v2 1.4.9)
# ---------------------------------------------------------------------------
def test_o1_7_a_failed_invoking_sync_never_starts_the_tool(tmp_path):
    ops = FaultOps()
    session = open_fresh(tmp_path, ops=ops)
    session.send(lambda: None)
    adoption = adopt_response(response(TWO), 1)
    session.adopt(adoption)
    ran = []
    ops.faults.append(("fsync", lambda p: p.endswith(".svl"), eio()))
    with pytest.raises(cp.PersistenceFailure):
        session.invoke(adoption.calls[0], lambda: ran.append("tool"))
    assert ran == [] and session.broken
    assert (session.session_dir / "FSYNC_FAILED").exists() and session.marker_written is True
    ops.faults.clear()
    with pytest.raises(cp.PersistenceFailure):
        session.invoke(adoption.calls[0], lambda: ran.append("tool"))
    with pytest.raises(cp.PersistenceFailure):
        session.send(lambda: ran.append("request"))
    assert ran == [], "a broken session starts no effect, even once the medium recovers"


def test_a_failed_request_sent_sync_sends_nothing(tmp_path):
    ops = FaultOps()
    session = open_fresh(tmp_path, ops=ops)
    ops.faults.append(("fsync", lambda p: p.endswith(".svl"), eio()))
    sent = []
    with pytest.raises(cp.PersistenceFailure):
        session.send(lambda: sent.append(1))
    assert sent == [] and (session.session_dir / "FSYNC_FAILED").exists()


def test_a_result_blob_is_durable_before_done_and_its_failure_writes_no_done(tmp_path):
    ops = FaultOps()
    session = open_fresh(tmp_path, ops=ops)
    session.send(lambda: None)
    adoption = adopt_response(response(TWO), 1)
    session.adopt(adoption)
    session.invoke(adoption.calls[0], lambda: None)
    ops.faults.append(("fsync", lambda p: "/blobs/." in p, eio()))
    with pytest.raises(cp.PersistenceFailure):
        session.record_result(adoption.calls[0], "returned", "x-contents")
    assert types(session)[-1] == "INVOKING", "no DONE without its blob"
    assert (session.session_dir / "FSYNC_FAILED").exists()


def test_a_successful_done_follows_its_blob(tmp_path):
    ops = FaultOps()
    session = open_fresh(tmp_path, ops=ops)
    session.send(lambda: None)
    adoption = adopt_response(response(TWO[:1]), 1)
    session.adopt(adoption)
    session.invoke(adoption.calls[0], lambda: None)
    mark = len(ops.events)
    session.record_result(adoption.calls[0], "returned", "x-contents")
    events = ops.events[mark:]
    blob = cp.BlobStore(session.session_dir / "blobs").dir / hashlib.sha256(b"x-contents").hexdigest()
    assert ("rename", str(blob)) in events
    renamed = events.index(("rename", str(blob)))
    fenced = events.index(("fenced", str(blob.parent)), renamed)
    done_write = next(i for i, e in enumerate(events) if e[0] == "write" and e[1].endswith(".svl"))
    assert renamed < fenced < done_write


@pytest.mark.parametrize("target", ["conversation", "run.json"])
def test_a_checkpoint_install_or_metadata_failure_breaks_the_session_and_marks(tmp_path, target):
    ops = FaultOps()
    session = open_fresh(tmp_path, ops=ops)
    session.append_message("user", "OPENING")
    if target == "conversation":
        ops.faults.append(("fsync", lambda p: ".conversation." in p, eio()))
    else:
        ops.faults.append(("rename", lambda p: p.endswith("run.json"), eio()))
    with pytest.raises(cp.PersistenceFailure):
        session.checkpoint()
    assert "CHECKPOINT" not in types(session)
    assert session.broken and (session.session_dir / "FSYNC_FAILED").exists()
    with pytest.raises(cp.PersistenceFailure):
        session.append_message("user", "more")


def test_a_failing_marker_is_attempted_once_and_never_recurses(tmp_path):
    ops = FaultOps()
    session = open_fresh(tmp_path, ops=ops)
    session.append_message("user", "OPENING")
    ops.faults.append(("fsync", lambda p: True, eio()))
    with pytest.raises(cp.PersistenceFailure):
        session.checkpoint()
    attempts = [e for e in ops.calls() if e[0] == "open" and "FSYNC_FAILED" in e[1]]
    assert len(attempts) == 1 and session.marker_written is False
    assert not (session.session_dir / "FSYNC_FAILED").exists(), "no marker claimed"


# ---------------------------------------------------------------------------
# CKG, thresholds (O2-3, C-G2) and rotation
# ---------------------------------------------------------------------------
def test_ckg_no_checkpoint_inside_a_group_or_with_queued_messages(tmp_path):
    session = open_fresh(tmp_path)
    session.send(lambda: None)
    adoption = adopt_response(response(TWO), 1)
    session.adopt(adoption)
    with pytest.raises(cs.SessionInvariant):
        session.checkpoint()
    for call in adoption.calls:
        session.invoke(call, lambda: None)
        session.record_result(call, "returned", "r")
    session.queue_message("user", "queued")
    with pytest.raises(cs.SessionInvariant):
        session.checkpoint()
    session.flush()
    record = session.checkpoint()
    assert record.payload["state"]["active_group"] is None and record.payload["state"]["queued"] == []


def test_o2_3_a_threshold_never_checkpoints_inside_a_group(tmp_path):
    session = open_fresh(tmp_path, records_max=8)
    for index in range(7):
        session.append_message("user", f"say {index}")
    assert "CHECKPOINT" not in types(session)
    turn(session, TWO)
    assert "CHECKPOINT" not in types(session), "a group's records never trigger a checkpoint inside it"
    session.unit_end()
    kinds = types(session)
    assert kinds.count("CHECKPOINT") == 1 and kinds[-1] == "CHECKPOINT"
    suffix = len(kinds) - 2  # minus LEDGER_HEADER and the CHECKPOINT itself
    assert suffix == 13 == 8 - 1 + 6, "the overshoot is at most one unit"
    for record in ledger(session).records:
        if record.type_name == "CHECKPOINT":
            assert record.payload["state"]["active_group"] is None


def test_c_g2_direct_says_checkpoint_after_records_8_and_16(tmp_path):
    session = open_fresh(tmp_path, records_max=8)
    for index in range(20):
        session.append_message("user", f"say {index}")
    kinds = types(session)
    positions = [i for i, kind in enumerate(kinds) if kind == "CHECKPOINT"]
    assert positions == [9, 18], "after the 8th and 16th say (seq 1 is the header)"
    assert len(kinds) - 1 - positions[-1] <= 8


def test_a_byte_threshold_counts_frames_and_replayed_blobs(tmp_path):
    session = open_fresh(tmp_path, bytes_max=10_000)
    session.append_message("user", "x" * 9_900)  # one blob of 9,900 bytes plus its frame
    assert types(session)[-1] == "CHECKPOINT"


def test_rotation_happens_only_at_a_unit_boundary(tmp_path):
    session = open_fresh(tmp_path)
    session.writer.segment_max = 600
    session.append_message("user", "OPENING")
    turn(session, TWO)
    records = ledger(session).records
    group = [r for r in records if r.type_name in ("REQUEST_SENT", "TURN_RESPONSE", "INVOKING", "DONE")]
    assert len({r.segment for r in group}) == 1, "a turn's records are never split by rotation"
    session.unit_end()
    session.append_message("user", "after")
    assert ledger(session).records[-1].segment > group[-1].segment
    assert_replays(session)


# ---------------------------------------------------------------------------
# Control exceptions: every stored call answered once, durable
# ---------------------------------------------------------------------------
THREE = [*TWO, ("call_c", "write_file", '{"path": "z", "text": "q"}')]


@pytest.mark.parametrize(
    ("stop", "first_kind"),
    [(KeyboardInterrupt(), "SYNTH"), (SystemExit(42), "DONE"), (RuntimeError("x"), "DONE")],
    ids=["interrupt", "system-exit", "other"],
)
def test_ending_a_group_answers_the_call_and_unruns_the_rest(tmp_path, stop, first_kind):
    session = open_fresh(tmp_path)
    session.send(lambda: None)
    adoption = adopt_response(response(THREE), 1)
    session.adopt(adoption)
    first, middle, last = adoption.calls
    session.invoke(first, lambda: None)
    session.record_result(first, "returned", "x-contents")
    session.invoke(middle, lambda: None)
    session.end_group(middle, stop, ended_text="ended", how="")
    assert session.group is None
    kinds = types(session)
    assert kinds[-2:] == [first_kind, "UNRUN"]
    assert session.messages[-1]["content"] == "not run: the run ended in call call_b"
    if first_kind == "SYNTH":
        assert session.messages[-2]["content"] == rp.UNKNOWN_TEXT
    else:
        assert ledger(session).records[-2].payload["outcome"] == f"raised:{type(stop).__name__}"
    assert_replays(session)


def test_a_typed_end_in_a_tool_records_done_termination_and_unrun(tmp_path):
    session = open_fresh(tmp_path)
    session.send(lambda: None)
    adoption = adopt_response(response(THREE), 1)
    session.adopt(adoption)
    first, handoff, _later = adoption.calls
    session.invoke(first, lambda: None)
    session.record_result(first, "returned", "x-contents")
    session.invoke(handoff, lambda: None)
    gen = session.write_note("N1", header="# Handoff")
    session.end_group(handoff, SystemExit(42), ended_text="handoff accepted; run ending", how="by handoff ", termination=("handoff", gen))
    kinds = types(session)
    assert kinds[-5:] == ["INVOKING", "NOTE_WRITTEN", "TERMINATION", "DONE", "UNRUN"]
    assert ledger(session).records[-3].payload == {"call_key": [1, 1], "kind": "handoff", "note_gen": 1}
    assert session.messages[-1]["content"] == "not run: the run ended by handoff in call call_b"
    assert_replays(session)


def test_a_typed_end_in_the_last_call_of_a_group_is_recorded_while_the_call_is_open(tmp_path):
    """Regression (found by the local-stub run): the answer of the last call closes the group."""
    session = open_fresh(tmp_path)
    session.send(lambda: None)
    adoption = adopt_response(response([("call_h", "handoff", '{"note": "n"}')]), 1)
    session.adopt(adoption)
    (only,) = adoption.calls
    session.invoke(only, lambda: None)
    gen = session.write_note("n", header="# Handoff")
    session.end_group(only, SystemExit(42), ended_text="handoff accepted; run ending", how="by handoff ", termination=("handoff", gen))
    assert types(session)[-3:] == ["NOTE_WRITTEN", "TERMINATION", "DONE"] and session.group is None
    assert_replays(session)


def test_a_broken_session_writes_nothing_when_a_group_ends(tmp_path):
    ops = FaultOps()
    session = open_fresh(tmp_path, ops=ops)
    session.send(lambda: None)
    adoption = adopt_response(response(TWO), 1)
    session.adopt(adoption)
    ops.faults.append(("fsync", lambda p: p.endswith(".svl"), eio()))
    with pytest.raises(cp.PersistenceFailure):
        session.invoke(adoption.calls[0], lambda: None)
    before = types(session)
    session.end_group(adoption.calls[0], KeyboardInterrupt(), ended_text="", how="")
    assert types(session) == before


# ---------------------------------------------------------------------------
# Response adoption, live (C-B5..7, O4-8)
# ---------------------------------------------------------------------------
def test_33_calls_store_32_run_16_and_flush_the_notice_before_queued_messages(tmp_path):
    session = open_fresh(tmp_path)
    calls = [(f"c{i}", "read_file", "{}") for i in range(33)]
    session.send(lambda: None)
    adoption = adopt_response(response(calls), 1)
    session.adopt(adoption)
    invoked = []
    for call in adoption.calls:
        if call.admit == "invoke":
            session.invoke(call, lambda call=call: invoked.append(call.index))
            session.record_result(call, "returned", "r")
    session.queue_message("user", "queued")
    session.flush()
    assert invoked == list(range(16))
    kinds = types(session)
    assert kinds.count("INVOKING") == 16 and kinds.count("DONE") == 16 and "UNRUN" not in kinds
    tools = [m for m in session.messages if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tools] == [f"c{i}" for i in range(32)], "every stored call answered once, in order"
    assert all(m["content"] == envelope.CALL_LIMIT_TEXT for m in tools[16:])
    assert [m["content"] for m in session.messages[-2:]] == [
        "[runtime] the response contained 33 tool calls; calls 33–33 were not stored or run",
        "queued",
    ]
    assert ledger(session).records[2].payload["omitted"]["count"] == 1
    assert_replays(session)


def test_257_calls_are_refused_durably_and_nothing_runs(tmp_path):
    session = open_fresh(tmp_path)
    session.send(lambda: None)
    adoption = adopt_response(response([(f"c{i}", "read_file", "{}") for i in range(257)]), 1)
    session.adopt(adoption)
    # SV021-06: the notice is part of RESPONSE_REFUSED itself, never a second write.
    assert types(session)[-1] == "RESPONSE_REFUSED" and "MSG_APPEND" not in types(session)
    assert ledger(session).records[-1].payload["notice"] == adoption.notice
    assert session.messages == [{"role": "user", "content": adoption.notice}]
    assert session.state.requests_next == {"turn_seq": 2, "attempt": 1}
    assert_replays(session)


def test_retained_originals_are_blobbed_first_and_evicted_fifo(tmp_path, monkeypatch):
    monkeypatch.setattr(rp, "ORIGINALS_MAX_COUNT", 2)
    session = open_fresh(tmp_path, caps=envelope.Caps(content=128))
    for index in range(3):
        turn(session, content=f"{index}" * 300)
    kinds = types(session)
    assert kinds.count("ORIGINAL_EVICTED") == 1
    evicted = next(r for r in ledger(session).records if r.type_name == "ORIGINAL_EVICTED").payload["sha"]
    assert evicted == hashlib.sha256(b"0" * 300).hexdigest()
    assert [o["sha256"] for o in session.state.originals] == [hashlib.sha256(f"{i}".encode() * 300).hexdigest() for i in (1, 2)]
    for original in session.state.originals:
        assert session.read_blob(original["sha256"]) is not None
    assert_replays(session)


def test_an_original_over_256_kib_is_not_retained(tmp_path):
    events = []
    session = open_fresh(tmp_path, lifecycle=lambda event, **fields: events.append(event))
    turn(session, content="x" * (256 * 1024 + 1))
    assert session.state.originals == [] and events == ["original_not_retained"]


# ---------------------------------------------------------------------------
# Messages, history, folds
# ---------------------------------------------------------------------------
def test_direct_messages_are_normalized_bounded_and_blobbed_when_long(tmp_path):
    session = open_fresh(tmp_path)
    session.append_message("user", "bad\ud800")
    session.append_message("system", "y" * 5000)
    with pytest.raises(ValueError):
        session.append_message("user", "\x00" * (cs.DIRECT_MESSAGE_MAX_E // 6 + 1))
    with pytest.raises(ValueError):
        session.append_message("user", 42)
    records = ledger(session).records
    assert records[1].payload["text"] == "bad?" and "blob" in records[2].payload
    assert session.messages == [{"role": "user", "content": "bad?"}, {"role": "system", "content": "y" * 5000}]
    assert_replays(session)


def test_set_history_is_blobbed_then_checkpointed_and_bad_lists_write_nothing(tmp_path):
    session = open_fresh(tmp_path)
    session.append_message("user", "OPENING")
    for bad in ([{"content": "no role"}], "not a list", [{"role": "user", "content": object()}]):
        with pytest.raises(ValueError):
            session.replace_history(bad)
    assert "HISTORY_REPLACED" not in types(session)
    session.replace_history([{"role": "user", "content": "NEW", "extra": [1, 2]}])
    assert types(session)[-2:] == ["HISTORY_REPLACED", "CHECKPOINT"]
    assert session.messages == [{"role": "user", "content": "NEW", "extra": [1, 2]}] and session.state.history_epoch == 2
    assert_replays(session)


def test_a_recap_fold_is_a_record_the_replay_follows(tmp_path):
    session = open_fresh(tmp_path)
    for index in range(4):
        session.append_message("user", f"m{index}")
    session.record_fold(0, 3, 3)
    assert session.state.recap_folded == 3
    with pytest.raises(cs.SessionInvariant):
        session.record_fold(0, 4, 1)
    assert_replays(session)


def test_run_end_is_best_effort(tmp_path):
    ops = FaultOps()
    session = open_fresh(tmp_path, ops=ops)
    ops.faults.append(("fsync", lambda p: p.endswith(".svl"), eio()))
    session.record_run_end(0, "main_returned")  # no exception escapes
    assert session.broken


# ---------------------------------------------------------------------------
# Astra SV021-07: the public history is a detached copy
# ---------------------------------------------------------------------------
from test_chassis_termination import make_run, reply  # noqa: E402, F401 -- make_run is a fixture

TAMPER = '''
def BEHAVIOUR(context, what):
    history = context.history()
    for message in history:
        for call in message.get("tool_calls", []):
            call["id"] = "X"
            call["function"]["name"] = "renamed"
            call["function"]["arguments"] = "TAMPERED"
        content = message.get("content")
        if isinstance(content, dict):
            content["nested"].append("TAMPERED")
    return "looked"
'''


def test_sv021_07_editing_the_history_copy_inside_a_tool_changes_nothing(make_run):
    import chassis_startup as st  # noqa: PLC0415

    main = (
        "    context.set_history([{'role': 'user', 'content': {'nested': ['kept']}}])\n"
        "    context.ask('go')\n"
        "    context.ask('again')\n"
    )
    run = make_run(
        [reply(calls=[("call_a", "act", {"what": "x"})]), reply(calls=[("call_b", "act", {"what": "y"})]), reply("done")],
        main=main,
        extra=TAMPER,
    )
    run.go()
    messages = run.chassis.messages
    assert messages[0] == {"role": "user", "content": {"nested": ["kept"]}}
    calls = [call for m in messages for call in m.get("tool_calls", [])]
    assert [(c["id"], c["function"]["name"], c["function"]["arguments"]) for c in calls] == [
        ("call_a", "act", '{"what": "x"}'),
        ("call_b", "act", '{"what": "y"}'),
    ]
    session_dir = run.root / "home" / "session"
    # SV-022: the run collects, so the ledger's replay is startup's own (newest
    # checkpoint + suffix), not a genesis replay of records it has collected.
    opening = st.open_session(session_dir, run.root / "home")
    assert opening.classification == "A9", opening
    assert opening.session.messages == messages == json.loads((session_dir / "conversation.json").read_text())
    opening.session.close()
    # A previous-base rebuild must reach the newest checkpoint's hash.
    (session_dir / "conversation.json").write_bytes(b"damaged")
    opening = st.open_session(session_dir, run.root / "home")
    assert opening.classification == "A14", opening
