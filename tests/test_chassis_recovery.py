"""Tail classification and pure recovery outcomes (SV-020 foundation).

Contract: SV-015 v2 section 1.3 (valid prefix, later-valid-frame probe,
frontier, TC0-TC4, per-type rule, TC4 acknowledgement, call classification)
and SV-013 2.2.3's retained call texts. Fixtures: v2 4.1 Group 1 and SV-013
C-D1/C-D3. Literal tails are rebuilt from the v2 generator's construction and
checked against its published SHA-256 values.

**O1-5 is corrected here, not reproduced.** v2 4.1 lists "the 144-byte valid
frame + 10 bytes" as TC3/A2. Under v2 1.3's own contiguous-prefix scanner that
valid frame joins P and ten bytes remain: TC1, with the call **unknown** because
its INVOKING is in P (independent v2 review V2-06(2); SV-020 preflight item 3).
The genuine TC3/A2 stimulus is an *invalid* full frame plus ten bytes. Both
fixtures are kept below.

Everything is a pure simulation over bytes or temporary roots. None of it is a
chassis crash/restart run (C-1/C-K/C-T), which needs the integrated activation.
"""

from __future__ import annotations

import chassis_persistence as cp
import pytest
from test_chassis_ledger import (
    CHAIN_22,
    CHAIN_30,
    FRAME_23,
    LINEAGE,
    ZERO,
    H,
    call,
    checkpoint,
    damaged,
    done,
    message,
    new_ledger,
    p_through_22,
    record,
    scan_dir,
    scan_of,
    segment_path,
    turn_response,
)

TEN = b"0123456789"


def plan_for(scan, acknowledgement=None, read_blob=lambda sha: None):
    tail = cp.classify_tail(scan)
    return tail, cp.plan_recovery(scan, tail, read_blob=read_blob, acknowledgement=acknowledgement)


def statuses(plan):
    return [(c.call_index, c.status, c.text) for c in plan.calls]


def damage_headers(data: bytes, offsets) -> bytes:
    """The generator's damage: the second header-check character of each frame."""
    out = bytearray(data)
    for offset in offsets:
        out[offset + 33] = ord("0") if out[offset + 33] != ord("0") else ord("1")
    return bytes(out)


def group_7_frames():
    """v2 4.1 frames 23-26 exactly as the literal generator (lines 24-29) builds them."""
    f23, chain = cp.encode_frame(23, "INVOKING", {"turn_seq": 7, "call_index": 0}, CHAIN_22)
    f24, chain = cp.encode_frame(
        24, "DONE", done(7, 0, "67b48901e9e87d3f07a07f03ce74d3193c49a14c9f0e194ec114def6498d1d2d", size=10), chain
    )
    f25, chain = cp.encode_frame(25, "INVOKING", {"turn_seq": 7, "call_index": 1}, chain)
    f26, chain = cp.encode_frame(
        26, "DONE", done(7, 1, "9119942b4ef3a457141daca2fdc778ae6a7ca1e738a6992dde1a57461b2eae7b", size=29), chain
    )
    return [f23, f24, f25, f26]


def acknowledged(tmp_path, tail: bytes, resolution="continue-conservative"):
    """The operator capability exercised on a temporary stop -- never on a real run."""
    cp.write_stop(tmp_path, "ledger_tail_ambiguous", cp.tail_stop_detail(tail))
    return cp.acknowledge_stop(tmp_path, "ledger_tail_ambiguous", resolution)


UNRUN = cp.UNRUN_TEXT
UNKNOWN = cp.UNKNOWN_TEXT
DAMAGED = cp.DAMAGED_TAIL_TEXT


# -- O1-1a/b, O1-2, O1-3: provable versus unprovable ---------------------------
def test_o1_1a_a_full_damaged_invoking_frame_makes_the_frontier_call_unknown():
    tail = damaged(FRAME_23, 60, ord("9"))  # byte 60: "x" of call_index -> "9"
    assert FRAME_23[60:61] == b"x"
    digest = H(tail)
    assert digest.startswith("9eb741ae") and digest.endswith("681e")  # v2 4.1 O1-1a
    tail_class, plan = plan_for(scan_of(p_through_22(), tail))
    assert (tail_class.kind, tail_class.declared_type, tail_class.length) == ("TC2", "INVOKING", 144)
    assert plan.action == "continue" and plan.quarantine_tail
    assert statuses(plan) == [(0, "unknown", DAMAGED), (1, "unrun", UNRUN)]
    assert plan.recovery_records == ({"kind": "damaged_final", "detail": {"type": "05", "bytes": 144}},)
    assert plan.next_request is None


def test_o1_1b_identical_bytes_from_another_history_classify_identically():
    durable_then_damaged = damaged(FRAME_23, 60, ord("9"))
    torn_append_with_garbage = FRAME_23[:60] + b"9" + FRAME_23[61:]  # built independently
    assert durable_then_damaged == torn_append_with_garbage
    first = plan_for(scan_of(p_through_22(), durable_then_damaged))
    second = plan_for(scan_of(p_through_22(), torn_append_with_garbage))
    assert first == second


def test_o1_2_a_short_tail_with_a_valid_header_is_provably_incomplete():
    tail_class, plan = plan_for(scan_of(p_through_22(), FRAME_23[:100]))
    assert (tail_class.kind, tail_class.declared_type, tail_class.length) == ("TC1", "INVOKING", 100)
    assert statuses(plan) == [(0, "unrun", UNRUN), (1, "unrun", UNRUN)]
    assert plan.recovery_records == ({"kind": "torn_incomplete", "detail": {"bytes": 100, "declared_type": "05"}},)


def test_o1_3_a_tail_shorter_than_a_header_is_incomplete():
    tail = FRAME_23[:23]
    assert tail == b"SVL1 000000000023 05 00"
    tail_class, plan = plan_for(scan_of(p_through_22(), tail))
    assert (tail_class.kind, tail_class.declared_type) == ("TC1", None)
    assert statuses(plan)[0] == (0, "unrun", UNRUN)


# -- O1-4, both O1-5 cases, O1-10, C-D1: stops ----------------------------------
def test_o1_4_three_hundred_bytes_with_a_failed_header_check_stop_without_acting():
    tail = damaged(FRAME_23, 33, ord("0")) + b"." * 156
    assert len(tail) == 300
    tail_class, plan = plan_for(scan_of(p_through_22(), tail))
    assert tail_class.kind == "TC4"
    assert (plan.action, plan.stop_reason) == ("stop", "ledger_tail_ambiguous")
    assert not plan.quarantine_tail and plan.calls == () and plan.recovery_records == ()


def test_o1_5_corrected_a_valid_invoking_plus_ten_bytes_extends_p_and_leaves_tc1(tmp_path):
    # Literal bytes: the frame is valid after chain 22 even with bytes following it,
    # so the scanner's per-frame rule puts it in P ...
    parsed = cp.parse_record(FRAME_23 + TEN, 0, 23, CHAIN_22, 0)
    assert isinstance(parsed, cp.Record) and parsed.length == 144
    # ... and the classifier refuses a scan that calls it a tail.
    with pytest.raises(ValueError):
        cp.classify_tail(scan_of(p_through_22(), FRAME_23 + TEN))
    # Through the real scanner on disk:
    session, writer = new_ledger(tmp_path)
    writer.append("REQUEST_SENT", {"turn_seq": 7, "attempt": 1, "label": "0f1e:7:1"})
    writer.append("TURN_RESPONSE", turn_response(7, [call(0), call(1)]))
    writer.append("INVOKING", {"turn_seq": 7, "call_index": 0})
    writer.close()
    with open(segment_path(session), "ab") as handle:
        handle.write(TEN)
    scan = scan_dir(session)
    assert scan.records[-1].type_name == "INVOKING" and scan.tail == TEN
    tail_class, plan = plan_for(scan)
    assert (tail_class.kind, tail_class.length) == ("TC1", 10)
    # The gate is in P: the call may have run. Unknown, never unrun.
    assert statuses(plan) == [(0, "unknown", UNKNOWN), (1, "unrun", UNRUN)]


def test_o1_5_genuine_tc3_an_invalid_full_frame_plus_ten_bytes_stops():
    tail = damaged(FRAME_23, 60, ord("9")) + TEN
    tail_class, plan = plan_for(scan_of(p_through_22(), tail))
    assert (tail_class.kind, tail_class.damaged_at) == ("TC3", 23)
    assert (plan.action, plan.stop_reason) == ("stop", "ledger_damaged_at")
    assert not plan.quarantine_tail


def test_o1_10_a_later_valid_frame_after_a_damaged_header_is_a2():
    frames = group_7_frames()
    tail = damage_headers(b"".join(frames), [0])
    assert len(tail) == 908
    tail_class, plan = plan_for(scan_of(p_through_22(), tail))
    assert tail_class.kind == "A2"
    assert tail_class.later_valid_offsets == (144, 454, 598)
    assert (tail_class.damaged_at, plan.action, plan.stop_reason) == (23, "stop", "ledger_damaged_at")


def _ledger_through_26(tmp_path):
    """SV-013 C-D1: a real ledger whose records 21-26 are turn 7's group."""
    session, writer = new_ledger(tmp_path)
    for _ in range(19):
        writer.append("MSG_APPEND", message())
    writer.append("REQUEST_SENT", {"turn_seq": 7, "attempt": 1, "label": "0f1e:7:1"})
    writer.append("TURN_RESPONSE", turn_response(7, [call(0), call(1)]))
    invoking = writer.append("INVOKING", {"turn_seq": 7, "call_index": 0})
    writer.append("DONE", done(7, 0, ZERO))
    writer.append("INVOKING", {"turn_seq": 7, "call_index": 1})
    writer.append("DONE", done(7, 1, ZERO))
    writer.close()
    assert invoking.seq == 23
    return session, invoking.offset


def _snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


@pytest.mark.parametrize("where", [49 + 11, 33], ids=["body", "header"])
def test_c_d1_mid_file_corruption_stops_at_23_and_touches_nothing(tmp_path, where):
    # Either damage leaves valid frames 24-26 after the damaged one: the probe finds them (A2).
    session, offset = _ledger_through_26(tmp_path)
    path = segment_path(session)
    data = path.read_bytes()
    assert data[offset + 49 + 11 : offset + 49 + 12] == b"x"  # call_index's "x"
    path.write_bytes(damage_headers(data, [offset]) if where == 33 else damaged(data, offset + where, ord("9")))
    before = _snapshot(tmp_path)
    scan = scan_dir(session)
    tail_class, plan = plan_for(scan)
    assert scan.last_seq == 22
    assert (tail_class.kind, tail_class.damaged_at, len(tail_class.later_valid_offsets)) == ("A2", 23, 3)
    assert (plan.action, plan.stop_reason, plan.calls) == ("stop", "ledger_damaged_at", ())
    assert _snapshot(tmp_path) == before  # scanning and planning wrote nothing


# -- O1-6: damaged request after a clean checkpoint -----------------------------
def test_o1_6_a_damaged_request_frame_is_possible_duplicate_spend(tmp_path):
    session, writer = new_ledger(tmp_path)
    writer.append("REQUEST_SENT", {"turn_seq": 7, "attempt": 1, "label": "0f1e:7:1"})
    writer.append("TURN_RESPONSE", turn_response(7, []))
    writer.append("CHECKPOINT", checkpoint(3))
    frame, _ = cp.encode_frame(writer.next_seq, "REQUEST_SENT", {"turn_seq": 8, "attempt": 1, "label": "0f1e:8:1"}, writer.chain)
    writer.close()
    position = frame.index(b"0f1e:8:1") + 5
    with open(segment_path(session), "ab") as handle:
        handle.write(damaged(frame, position, ord("9")))
    tail_class, plan = plan_for(scan_dir(session))
    assert (tail_class.kind, tail_class.declared_type) == ("TC2", "REQUEST_SENT")
    assert plan.next_request == {"turn_seq": 8, "attempt": 2}
    assert cp.request_label(LINEAGE, **plan.next_request) == "0f1e:8:2"  # never 0f1e:8:1 again
    assert {"kind": "possible_duplicate_spend", "detail": {"turn_seq": 8, "attempt": 2}} in plan.recovery_records


# -- O1-8, O1-9: ambiguous multi-record tails and acknowledgement ----------------
def test_o1_8_both_calls_ran_behind_damaged_headers_and_stay_unknown_after_acknowledgement(tmp_path):
    frames = group_7_frames()
    assert [len(f) for f in frames] == [144, 310, 144, 310]
    assert frames[0] == FRAME_23
    offsets = [0, 144, 454, 598]
    tail = damage_headers(b"".join(frames), offsets)
    assert H(tail) == "20a64606574b4661c3b3689935a71189d032b945a419c6e81f9e7c1926710672"
    assert not any(cp.read_header(tail, o).check_ok for o in offsets)
    scan = scan_of(p_through_22(), tail)

    tail_class, plan = plan_for(scan)
    assert tail_class.kind == "TC4"
    assert (plan.action, plan.stop_reason, plan.quarantine_tail) == ("stop", "ledger_tail_ambiguous", False)

    _, plan = plan_for(scan, acknowledgement=acknowledged(tmp_path, tail))
    assert plan.action == "continue"
    # v1's rule (TC2 applied to the frontier) would call call_b unrun -- false, it ran.
    assert statuses(plan) == [(0, "unknown", DAMAGED), (1, "unknown", DAMAGED)]
    assert cp.HIDDEN_TURN_NOTICE.format(seq=22) in plan.notices
    assert {"kind": "damaged_tail_acknowledged", "detail": {"bytes": 908}} in plan.recovery_records
    assert plan.quarantine_tail


def _lost_response_tail():
    """v2 O1-9 frames 31-32, as the literal generator (lines 45-50) builds them."""
    assistant = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "call_q", "type": "function",
                        "function": {"name": "write_file", "arguments": '{"path":"q","text":"1"}'}}],
    }
    response = {
        "turn_seq": 8,
        "assistant": assistant,
        "calls": [{
            "call_index": 0,
            "provider_id_repr": {"type": "str", "E": 6, "sha256": H(b'"call_q"')},
            "wire_id": "call_q",
            "name": "write_file",
            "args_sha256": H(b'{"path":"q","text":"1"}'),
            "args_E": 24,
            "admit": "invoke",
        }],
        "normalization": {"replaced_chars": 0, "truncated_fields": []},
        "original_blobs": [],
    }
    f31, chain = cp.encode_frame(31, "TURN_RESPONSE", response, CHAIN_30)
    f32, _ = cp.encode_frame(32, "INVOKING", {"turn_seq": 8, "call_index": 0}, chain)
    assert [len(f31), len(f32)] == [674, 144]
    return damage_headers(f31 + f32, [0, len(f31)])


def test_o1_9_a_lost_response_and_invocation_give_spend_and_the_hidden_turn_notice(tmp_path):
    tail = _lost_response_tail()
    assert (len(tail), H(tail)) == (818, "35d55b60e1231292a6b2c70ba828c4738748217585fd56ee7eb3c54708419b95")
    scan = scan_of([record(30, "REQUEST_SENT", {"turn_seq": 8, "attempt": 1, "label": "0f1e:8:1"}, CHAIN_30)], tail)
    tail_class, plan = plan_for(scan)
    assert (tail_class.kind, plan.action) == ("TC4", "stop")

    _, plan = plan_for(scan, acknowledgement=acknowledged(tmp_path, tail))
    assert plan.action == "continue"
    assert plan.calls == ()  # no call can be listed: none is known, none is called unrun
    assert cp.request_label(LINEAGE, **plan.next_request) == "0f1e:8:2"
    assert {"kind": "possible_duplicate_spend", "detail": {"turn_seq": 8, "attempt": 2}} in plan.recovery_records
    notice = cp.HIDDEN_TURN_NOTICE.format(seq=30)
    assert notice in plan.notices and "tools may have run" in notice


def test_acknowledgement_is_bound_to_the_stopped_bytes_and_resolution(tmp_path):
    tail = damage_headers(b"".join(group_7_frames()), [0, 144, 454, 598])
    scan = scan_of(p_through_22(), tail)
    stale = acknowledged(tmp_path, tail + b"x")
    assert plan_for(scan, acknowledgement=stale)[1].action == "stop"
    unbound = {"reason": "ledger_tail_ambiguous", "resolution": "continue-conservative"}
    assert plan_for(scan, acknowledgement=unbound)[1].action == "stop"
    bootstrap = acknowledged(tmp_path, tail, resolution="bootstrap-preserving")
    assert plan_for(scan, acknowledgement=bootstrap)[1].action == "stop"  # the caller's separate path
    assert (tmp_path / "STOPPED").exists()  # acknowledging removes nothing


def test_acknowledge_stop_checks_the_stop_it_is_given(tmp_path):
    with pytest.raises(cp.LedgerError):
        cp.acknowledge_stop(tmp_path, "ledger_tail_ambiguous", "continue-conservative")
    cp.write_stop(tmp_path, "ledger_damaged_at", {"seq": 23})
    with pytest.raises(cp.LedgerError):
        cp.acknowledge_stop(tmp_path, "ledger_tail_ambiguous", "continue-conservative")
    with pytest.raises(cp.LedgerError):
        cp.acknowledge_stop(tmp_path, "ledger_damaged_at", "continue-conservative")
    assert cp.acknowledge_stop(tmp_path, "ledger_damaged_at", "continue-from-bound") == {
        "reason": "ledger_damaged_at", "resolution": "continue-from-bound",
    }


def test_acknowledged_tc4_never_invokes_a_call_admission_refused():
    calls = [call(0), call(1, admit="bad_args")]
    tail = damage_headers(b"".join(group_7_frames()), [0, 144, 454, 598])
    scan = scan_of(p_through_22(calls), tail)
    ack = {"reason": "ledger_tail_ambiguous", "resolution": "continue-conservative", "tail_sha256": H(tail)}
    _, plan = plan_for(scan, acknowledgement=ack)
    assert statuses(plan) == [(0, "unknown", DAMAGED), (1, "not_invoked", None)]


def test_acknowledged_tc4_at_a_unit_boundary_lists_no_call_but_assumes_spend():
    records = [record(40, "CHECKPOINT", checkpoint(39), CHAIN_30)]
    tail = damaged(FRAME_23, 33, ord("0")) + b"." * 40
    scan = scan_of(records, tail)
    ack = {"reason": "ledger_tail_ambiguous", "resolution": "continue-conservative", "tail_sha256": H(tail)}
    _, plan = plan_for(scan, acknowledgement=ack)
    assert plan.calls == ()
    assert cp.HIDDEN_TURN_NOTICE.format(seq=40) in plan.notices
    assert any(r["kind"] == "possible_duplicate_spend" for r in plan.recovery_records)


# -- C-D3 and the DONE rows ---------------------------------------------------
CD3_SHA = "34a19b10151df6f90ebde3dc097d33b2191107b5c4ca737051e1c0b400bdb75f"


def _p_with_done(outcome, blob=CD3_SHA, size=23):
    return p_through_22() + [
        record(23, "INVOKING", {"turn_seq": 7, "call_index": 0}, H(b"23")),
        record(24, "DONE", done(7, 0, blob, outcome=outcome, size=size), H(b"24")),
    ]


def test_c_d3_a_raised_result_whose_blob_is_missing_keeps_the_raised_wording(tmp_path):
    store = cp.BlobStore(tmp_path / "blobs")
    scan = cp.LedgerScan(tuple(_p_with_done("raised:ValueError")), 24, H(b"24"), b"", 0, 4096)
    _, plan = plan_for(scan, read_blob=store.get)
    assert statuses(plan)[0] == (
        0,
        "known_payload_lost",
        "this call raised ValueError; its stored error text (23 bytes, sha256 "
        "34a19b10151df6f90ebde3dc097d33b2191107b5c4ca737051e1c0b400bdb75f) could not be recovered",
    )
    assert statuses(plan)[1] == (1, "unrun", UNRUN)


def test_a_returned_result_whose_blob_is_missing_says_returned(tmp_path):
    store = cp.BlobStore(tmp_path / "blobs")
    scan = cp.LedgerScan(tuple(_p_with_done("returned")), 24, H(b"24"), b"", 0, 4096)
    _, plan = plan_for(scan, read_blob=store.get)
    assert statuses(plan)[0][2] == (
        "this call returned 23 bytes (sha256 34a19b10151df6f90ebde3dc097d33b2191107b5c4ca737051e1c0b400bdb75f), "
        "but the stored result could not be recovered"
    )


def test_a_present_blob_is_the_known_result_and_a_corrupted_one_is_payload_lost(tmp_path):
    store = cp.BlobStore(tmp_path / "blobs")
    sha = store.put(b"file contents")
    scan = cp.LedgerScan(tuple(_p_with_done("returned", blob=sha, size=13)), 24, H(b"24"), b"", 0, 4096)
    assert statuses(plan_for(scan, read_blob=store.get)[1])[0] == (0, "known", "file contents")
    (tmp_path / "blobs" / sha).write_bytes(b"file c0ntents")
    assert statuses(plan_for(scan, read_blob=store.get)[1])[0][1] == "known_payload_lost"


def test_a_damaged_final_done_leaves_its_invoked_call_unknown():
    invoking_chain = H(b"23")
    records = p_through_22() + [record(23, "INVOKING", {"turn_seq": 7, "call_index": 0}, invoking_chain)]
    frame, _ = cp.encode_frame(24, "DONE", done(7, 0, ZERO), invoking_chain)
    tail = damaged(frame, frame.index(b'"returned"') + 2, ord("x"))
    tail_class, plan = plan_for(scan_of(records, tail))
    assert (tail_class.kind, tail_class.declared_type) == ("TC2", "DONE")
    assert statuses(plan) == [(0, "unknown", UNKNOWN), (1, "unrun", UNRUN)]


@pytest.mark.parametrize(
    "type_name, payload, expect",
    [
        ("CHECKPOINT", checkpoint(30), "previous_checkpoint"),
        ("NOTE_WRITTEN", {"gen": 2, "blob": ZERO, "bytes": 3, "sha256": ZERO, "source": "runtime", "mirror_sha256": ZERO}, "mirror"),
        ("MSG_APPEND", message(), "notice"),
    ],
)
def test_tc2_at_a_unit_boundary_follows_the_per_type_rule(type_name, payload, expect):
    records = [record(30, "TURN_RESPONSE", turn_response(8, []), CHAIN_30)]
    frame, _ = cp.encode_frame(31, type_name, payload, CHAIN_30)
    tail = frame[:-3] + (b"00\n" if frame[-3:-1] != b"00" else b"11\n")  # chain damaged
    tail_class, plan = plan_for(scan_of(records, tail))
    assert (tail_class.kind, tail_class.declared_type, plan.action) == ("TC2", type_name, "continue")
    assert plan.use_previous_checkpoint == (expect == "previous_checkpoint")
    assert plan.handoff_mirror_check == (expect == "mirror")
    assert bool(plan.notices) == (expect != "previous_checkpoint")
    assert plan.next_request is None


# -- the later-valid-frame probe and quoted frames ------------------------------
def test_a_quoted_frame_inside_a_tc2_body_is_content_but_after_a_bad_header_it_stops():
    inner, _ = cp.encode_frame(99, "INVOKING", {"turn_seq": 9, "call_index": 0}, ZERO)
    records = [record(30, "TURN_RESPONSE", turn_response(8, []), CHAIN_30)]
    outer, _ = cp.encode_frame(31, "MSG_APPEND", {"kind": "notice", "text": inner.decode(), "epoch": 0}, CHAIN_30)
    assert inner[:49] in outer
    epoch_digit = outer.index(b'"epoch":0') + len(b'"epoch":')
    body_damaged = damaged(outer, epoch_digit, ord("1"))
    tail_class, _ = plan_for(scan_of(records, body_damaged))
    assert (tail_class.kind, tail_class.declared_type) == ("TC2", "MSG_APPEND")
    # Negative control: with the outer header unreadable, the quoted header is a later-valid frame.
    tail_class, plan = plan_for(scan_of(records, damaged(outer, 33, ord("0") if outer[33:34] != b"0" else ord("1"))))
    assert tail_class.kind == "A2" and tail_class.later_valid_offsets == (outer.index(inner[:49]),)
    assert plan.action == "stop"


# -- the frontier: a reference derivation, and an injectable component ---------
def test_the_reference_frontier_follows_the_turn_state_machine():
    base = [record(1, "LEDGER_HEADER", {"lineage_id": LINEAGE, "segment_no": 0, "first_seq": 1, "prev_chain": ZERO}, ZERO)]
    req = record(2, "REQUEST_SENT", {"turn_seq": 1, "attempt": 1, "label": "0f1e:1:1"}, ZERO)
    resp = record(3, "TURN_RESPONSE", turn_response(1, [call(0), call(1, admit="bad_args")]), ZERO)
    inv = record(4, "INVOKING", {"turn_seq": 1, "call_index": 0}, ZERO)
    fin = record(5, "DONE", done(1, 0, ZERO), ZERO)
    assert cp.legal_next_types(()) == {"LEDGER_HEADER"}
    assert cp.legal_next_types(tuple(base)) == cp.UNIT_BOUNDARY_NEXT
    assert cp.legal_next_types(tuple(base + [req])) == cp.AFTER_REQUEST_NEXT
    assert cp.legal_next_types(tuple(base + [req, resp])) == cp.IN_GROUP_NEXT
    assert cp.legal_next_types(tuple(base + [req, resp, inv])) == cp.INVOKED_CALL_NEXT
    # The bad_args call is never invoked, so it does not hold the group open.
    assert cp.legal_next_types(tuple(base + [req, resp, inv, fin])) == cp.UNIT_BOUNDARY_NEXT
    assert "INVOKING" not in cp.INVOKED_CALL_NEXT  # calls run one at a time


def test_a_caller_supplied_frontier_decides_between_tc2_and_tc4():
    tail = damaged(FRAME_23, 60, ord("9"))
    scan = scan_of(p_through_22(), tail)
    assert cp.classify_tail(scan, frozenset({"INVOKING"})).kind == "TC2"
    assert cp.classify_tail(scan, frozenset({"DONE"})).kind == "TC4"


# -- purity --------------------------------------------------------------------
def test_scanning_classifying_and_planning_a_torn_tail_change_no_file(tmp_path):
    session, writer = new_ledger(tmp_path)
    writer.append("REQUEST_SENT", {"turn_seq": 1, "attempt": 1, "label": "0f1e:1:1"})
    frame, _ = cp.encode_frame(writer.next_seq, "TURN_RESPONSE", turn_response(1, []), writer.chain)
    writer.close()
    with open(segment_path(session), "ab") as handle:
        handle.write(frame[:60])
    before = _snapshot(tmp_path)
    tail_class, plan = plan_for(scan_dir(session))
    assert (tail_class.kind, plan.action, plan.quarantine_tail) == ("TC1", "continue", True)
    assert plan.next_request == {"turn_seq": 1, "attempt": 2}  # the request may have been answered
    assert _snapshot(tmp_path) == before  # a recommendation, not a mutation
