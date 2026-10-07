"""SVL1 ledger framing and the contiguous-prefix scanner (SV-020 foundation).

Contract: SV-015 v2 section 1.2 (frame, header check over bytes 0-31, chain,
record types and keys) and the scan part of 1.3; literal bytes from v2 4.1/4.9
and the v2 literal generator (chain preimages per the SV-020 literal-source
addendum). Pure bytes and temporary roots only. Nothing here runs the chassis,
which does not import the persistence module yet.
"""

from __future__ import annotations

import hashlib
import os

import chassis_persistence as cp
import pytest


def H(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# v2 1.2 and O1-11: INVOKING{turn_seq 7, call_index 0} at seq 23 after chain 22.
FRAME_23 = (
    b'SVL1 000000000023 05 0000000029 b315afbdc6651093 {"call_index":0,"turn_seq":7} '
    b"7a09058a05ab6426f91f3d33cc776ac0b5632cfc73b802b64a4ee5b908fafccb\n"
)
CHAIN_22 = H(b"fixture-chain-22")  # generator line 23
CHAIN_30 = H(b"fixture-chain-30")  # generator line 44
LINEAGE = "0f1e"
ZERO = "0" * 64


# -- fixture builders shared by the SV-020 test files -------------------------
def call(index, admit="invoke", name="read_file"):
    return {
        "call_index": index,
        "provider_id_repr": {"type": "str", "E": 4, "sha256": ZERO},
        "wire_id": f"c{index}",
        "name": name,
        "args_sha256": ZERO,
        "args_E": 2,
        "admit": admit,
    }


def turn_response(turn, calls):
    return {
        "turn_seq": turn,
        "assistant": {"role": "assistant", "content": ""},
        "calls": calls,
        "normalization": {"replaced_chars": 0, "truncated_fields": []},
        "original_blobs": [],
    }


def done(turn, index, blob, outcome="returned", size=10):
    return {
        "turn_seq": turn,
        "call_index": index,
        "outcome": outcome,
        "blob": blob,
        "original_bytes": size,
        "stored_E": size,
        "truncated": False,
        "replaced_chars": 0,
    }


def checkpoint(covers):
    return {
        "covers_seq": covers,
        "chain_at_cover": ZERO,
        "conv": {"sha256": ZERO, "bytes": 2},
        "prev": None,
        "run_sha256": ZERO,
        "state": {"active_group": None, "queued": []},
    }


def message(text="m"):
    return {"kind": "notice", "text": text, "epoch": 0}


def record(seq, type_name, payload, chain, segment=0):
    """A P record carrying a stated chain, for literal fixtures whose chain at P's end is given."""
    return cp.Record(seq, type_name, payload, chain, 0, 0, segment)


def scan_of(records, tail, segment=0):
    """The scan scan_segments returns for P = `records` and T = `tail` in P's own segment."""
    return cp.LedgerScan(tuple(records), records[-1].seq, records[-1].chain, tail, segment, 4096)


def p_through_22(calls=None):
    """v2 4.1 setup: 21 REQUEST_SENT{7,1}, 22 TURN_RESPONSE{7, R7} (two invokable calls); chain 22 literal."""
    return [
        record(21, "REQUEST_SENT", {"turn_seq": 7, "attempt": 1, "label": "0f1e:7:1"}, H(b"fixture-chain-21")),
        record(22, "TURN_RESPONSE", turn_response(7, calls or [call(0), call(1)]), CHAIN_22),
    ]


def damaged(data: bytes, offset: int, value: int) -> bytes:
    out = bytearray(data)
    out[offset] = value
    return bytes(out)


def raw_frame(seq, type_id, body: bytes, prev_chain: str) -> bytes:
    """A frame with a correct header check and chain around arbitrary body bytes."""
    prefix = b"SVL1 %012d %02x %010d " % (seq, type_id, len(body))
    header = prefix + cp.header_check(prefix).encode() + b" "
    return header + body + b" " + H(bytes.fromhex(prev_chain) + header + body).encode() + b"\n"


def new_ledger(tmp_path, **kwargs):
    session = tmp_path / "session"
    session.mkdir(exist_ok=True)
    return session, cp.LedgerWriter.create(session, LINEAGE, **kwargs)


def scan_dir(session):
    return cp.scan_segments(cp.read_segments(session / "ledger"), LINEAGE)


def segment_path(session, number=0):
    return session / "ledger" / cp.segment_name(number)


# -- O1-11: the exact frame and header span -----------------------------------
def test_o1_11_header_check_covers_bytes_0_to_31_and_the_literal_frame_reproduces():
    assert len(FRAME_23) == 144
    assert H(FRAME_23) == "2b3281e0565be162749998d74a63bb18b11b2c4b3f4fcf49f435c92d5eb6e7f1"
    assert FRAME_23[:32] == b"SVL1 000000000023 05 0000000029 "
    assert cp.header_check(FRAME_23[:32]) == "b315afbdc6651093" == FRAME_23[32:48].decode()
    # Negative control: v1's 33-byte span gives a different check, rejecting every valid frame.
    assert H(FRAME_23[:33])[:16] == "1090633068e00112" != FRAME_23[32:48].decode()
    with pytest.raises(ValueError):
        cp.header_check(FRAME_23[:33])

    frame, chain = cp.encode_frame(23, "INVOKING", {"turn_seq": 7, "call_index": 0}, CHAIN_22)
    assert frame == FRAME_23
    assert chain == "7a09058a05ab6426f91f3d33cc776ac0b5632cfc73b802b64a4ee5b908fafccb"
    parsed = cp.parse_record(FRAME_23, 0, 23, CHAIN_22, 0)
    assert isinstance(parsed, cp.Record)
    assert (parsed.seq, parsed.type_name, parsed.payload, parsed.chain, parsed.length) == (
        23, "INVOKING", {"call_index": 0, "turn_seq": 7}, chain, 144,
    )


def test_frame_sizes_follow_the_fixed_header_and_trailer():
    assert (cp.HEADER_BYTES, cp.HASHED_PREFIX, cp.TRAILER_BYTES) == (49, 32, 66)
    assert cp.MIN_RECORD_BYTES == 49 + len(b"{}") + 66 == 117
    assert len(cp.encode_header(1, 0x12, 2)) == 49
    assert cp.genesis_chain(LINEAGE) == H(b"SVL1-genesis:0f1e")


# -- invalid frames ------------------------------------------------------------
def _retype(frame: bytes, type_hex: bytes) -> bytes:
    prefix = frame[:18] + type_hex + frame[20:32]
    return prefix + cp.header_check(prefix).encode() + frame[48:]


@pytest.mark.parametrize(
    "data, expected_seq, prev, reason",
    [
        (damaged(FRAME_23, 33, ord("0")), 23, CHAIN_22, "header check"),
        (_retype(FRAME_23, b"ff"), 23, CHAIN_22, "unknown type ff"),
        (FRAME_23, 24, CHAIN_22, "seq 23 where 24 was due"),
        (damaged(FRAME_23, 60, ord("9")), 23, CHAIN_22, "body: missing keys: call_index"),  # O1-1a's byte
        (FRAME_23, 23, CHAIN_30, "chain"),
        (FRAME_23[:143], 23, CHAIN_22, "frame extends past the end of the data"),
        (FRAME_23[:-1] + b" ", 23, CHAIN_22, "trailer"),
        (raw_frame(23, 0x05, b"[0,7]", CHAIN_22), 23, CHAIN_22, "body: body is not a JSON object"),
        (raw_frame(23, 0x05, b'{"call_index":0}', CHAIN_22), 23, CHAIN_22, "body: missing keys: turn_seq"),
        (raw_frame(23, 0x05, b'{"call_index":true,"turn_seq":7}', CHAIN_22), 23, CHAIN_22, "body: call_index"),
        (raw_frame(23, 0x05, b'{"call_index":0,"turn_seq":7,"x":NaN}', CHAIN_22), 23, CHAIN_22, "body is not canonical"),
        (raw_frame(23, 0x05, b'{"call_index": 0,"turn_seq":7}', CHAIN_22), 23, CHAIN_22, "body is not canonical"),
        (
            raw_frame(23, 0x05, b'{"call_index":1,"call_index":0,"turn_seq":7}', CHAIN_22),
            23, CHAIN_22, "body is not canonical",
        ),
        (raw_frame(23, 0x05, b'{"call_index":0,"turn_seq":7', CHAIN_22), 23, CHAIN_22, "body is not JSON"),
    ],
    ids=[
        "header-check", "unknown-type", "seq", "body-key", "chain", "short", "trailer", "not-object",
        "missing-key", "bool-counter", "nan", "spacing", "duplicate-key", "not-json",
    ],
)
def test_an_invalid_frame_is_named_for_its_first_defect(data, expected_seq, prev, reason):
    result = cp.parse_record(data, 0, expected_seq, prev, 0)
    assert isinstance(result, cp.Invalid)
    assert result.reason == reason


def test_a_declared_body_over_the_maximum_is_refused_before_it_is_read():
    prefix = b"SVL1 %012d %02x %010d " % (23, 0x05, cp.MAX_LEDGER_BODY + 1)
    header = prefix + cp.header_check(prefix).encode() + b" "
    result = cp.parse_record(header + b"{}", 0, 23, CHAIN_22, 0)
    assert isinstance(result, cp.Invalid) and result.reason == "declared body length out of range"
    assert result.header.check_ok and result.header.plen == cp.MAX_LEDGER_BODY + 1


# -- domains: refusal before anything is written ------------------------------
@pytest.mark.parametrize("seq", [0, cp.MAX_SEQ + 1, True, -1])
def test_a_seq_outside_the_twelve_digit_header_field_is_refused(seq):
    with pytest.raises(cp.LedgerError):
        cp.encode_header(seq, 0x05, 29)


def test_the_largest_seq_still_fits_its_field():
    assert cp.encode_header(cp.MAX_SEQ, 0x05, 29)[5:17] == b"999999999999"


@pytest.mark.parametrize(
    "type_name, payload",
    [
        ("INVOKING", {"turn_seq": 10**12, "call_index": 0}),
        ("INVOKING", {"turn_seq": True, "call_index": 0}),
        ("INVOKING", {"turn_seq": -1, "call_index": 0}),
        ("INVOKING", {"turn_seq": 7}),
        ("REQUEST_SENT", {"turn_seq": 7, "attempt": 0, "label": "x"}),
        ("DONE", {**done(7, 0, ZERO), "outcome": "raised:"}),
        ("DONE", {**done(7, 0, ZERO), "blob": "not-a-hash"}),
        ("CHECKPOINT", {**checkpoint(4), "state": {"active_group": {"turn_seq": 7}, "queued": []}}),
        ("TURN_RESPONSE", turn_response(7, [call(1)])),
        ("TURN_RESPONSE", turn_response(7, [{**call(0), "admit": "maybe"}])),
        ("UNRUN", {"call_key": [7], "reason": "x"}),
        ("NOT_A_TYPE", {}),
        ("MSG_APPEND", {"kind": "notice", "text": "x", "epoch": 0, "bad": float("nan")}),
    ],
    ids=[
        "13-digit", "bool", "negative", "missing", "attempt-0", "raised-without-type", "blob", "mid-group-checkpoint",
        "call-index-order", "admit", "call-key", "unknown-type", "nan",
    ],
)
def test_an_unencodable_record_is_refused(type_name, payload):
    with pytest.raises(cp.LedgerError):
        cp.encode_frame(23, type_name, payload, CHAIN_22)


def test_an_oversize_body_is_refused_before_the_writer_writes_a_byte(tmp_path):
    session, writer = new_ledger(tmp_path)
    before = segment_path(session).read_bytes()
    with pytest.raises(cp.LedgerError):
        writer.append("MSG_APPEND", message("x" * cp.MAX_LEDGER_BODY))
    assert segment_path(session).read_bytes() == before
    assert not writer.broken
    writer.append("MSG_APPEND", message("fits"))
    assert [r.type_name for r in scan_dir(session).records] == ["LEDGER_HEADER", "MSG_APPEND"]


def test_the_writer_refuses_a_thirteenth_seq_digit_without_writing(tmp_path):
    session = tmp_path / "session"
    (session / "ledger").mkdir(parents=True)
    writer = cp.LedgerWriter(
        session, LINEAGE, next_seq=cp.MAX_SEQ - 1, prev_chain=cp.genesis_chain(LINEAGE), segment_no=-1
    )
    writer.open_segment()
    writer.append("MSG_APPEND", message())
    assert writer.next_seq == cp.MAX_SEQ + 1
    before = segment_path(session).read_bytes()
    with pytest.raises(cp.LedgerError):
        writer.append("MSG_APPEND", message())
    assert segment_path(session).read_bytes() == before


def test_the_segment_number_is_bounded_by_its_file_name_width(tmp_path):
    assert cp.segment_name(cp.MAX_SEGMENT_NO) == "999999.svl"
    with pytest.raises(cp.LedgerError):
        cp.segment_name(cp.MAX_SEGMENT_NO + 1)
    session = tmp_path / "session"
    (session / "ledger").mkdir(parents=True)
    writer = cp.LedgerWriter(session, LINEAGE, next_seq=5, prev_chain=ZERO, segment_no=cp.MAX_SEGMENT_NO)
    with pytest.raises(cp.LedgerError):
        writer.open_segment()
    assert os.listdir(session / "ledger") == []


# -- scanning ------------------------------------------------------------------
def test_writer_and_scanner_round_trip_across_a_rotation(tmp_path):
    session, writer = new_ledger(tmp_path, segment_max=300)
    writer.append("REQUEST_SENT", {"turn_seq": 1, "attempt": 1, "label": "0f1e:1:1"})
    writer.append("TURN_RESPONSE", turn_response(1, []))
    assert writer.rotate_if_full()
    writer.append("MSG_APPEND", message("after rotation"))
    scan = scan_dir(session)
    assert scan.stop is None and scan.tail == b""
    assert [(r.seq, r.type_name, r.segment) for r in scan.records] == [
        (1, "LEDGER_HEADER", 0), (2, "REQUEST_SENT", 0), (3, "TURN_RESPONSE", 0),
        (4, "LEDGER_HEADER", 1), (5, "MSG_APPEND", 1),
    ]
    assert scan.records[0].payload["prev_chain"] == cp.genesis_chain(LINEAGE)
    assert scan.records[3].payload == {
        "lineage_id": LINEAGE, "segment_no": 1, "first_seq": 4, "prev_chain": scan.records[2].chain,
    }
    assert scan.last_chain == writer.chain
    assert cp.classify_tail(scan).kind == "TC0"


def test_an_invalid_record_in_an_older_segment_stops_although_the_newest_is_clean(tmp_path):
    session, writer = new_ledger(tmp_path, segment_max=200)
    writer.append("MSG_APPEND", message("old"))
    writer.rotate_if_full()
    writer.append("MSG_APPEND", message("new"))
    old = segment_path(session, 0)
    data = old.read_bytes()
    old.write_bytes(data[:-80] + b"Z" + data[-79:])  # inside the last record's chain
    scan = scan_dir(session)
    assert scan.stop == "ledger_damaged_at" and scan.damaged_at == 2
    assert cp.classify_tail(scan).kind == "A2"


def test_bytes_after_p_in_an_older_segment_stop(tmp_path):
    session, writer = new_ledger(tmp_path, segment_max=100)
    writer.rotate_if_full()
    writer.append("MSG_APPEND", message())
    with open(segment_path(session, 0), "ab") as handle:
        handle.write(b"x")
    scan = scan_dir(session)
    assert scan.stop == "ledger_damaged_at"
    assert [r.seq for r in scan.records] == [1]


def test_another_lineages_ledger_never_forms_a_prefix(tmp_path):
    session, writer = new_ledger(tmp_path)
    appended = writer.append("MSG_APPEND", message())
    scan = cp.scan_segments(cp.read_segments(session / "ledger"), "another")
    assert scan.records == ()
    # The probe runs first: the valid frame after the rejected header is a later-valid frame.
    tail = cp.classify_tail(scan)
    assert (tail.kind, tail.later_valid_offsets) == ("A2", (appended.offset,))


def test_a_skipped_segment_number_does_not_continue_the_prefix(tmp_path):
    session, writer = new_ledger(tmp_path, segment_max=100)
    writer.rotate_if_full()
    writer.close()
    os.rename(segment_path(session, 1), segment_path(session, 2))
    scan = scan_dir(session)
    assert [r.seq for r in scan.records] == [1]
    tail = cp.classify_tail(scan)
    assert (tail.kind, tail.declared_type) == ("TC2", "LEDGER_HEADER")
    plan = cp.plan_recovery(scan, tail, read_blob=lambda sha: None)
    assert (plan.action, plan.stop_reason) == ("stop", "ledger_damaged_at")  # v2 1.4.10: header damage -> A2


def test_a_ledger_header_inside_a_segment_is_invalid():
    first, chain = cp.encode_frame(1, "LEDGER_HEADER", {
        "lineage_id": LINEAGE, "segment_no": 0, "first_seq": 1, "prev_chain": cp.genesis_chain(LINEAGE),
    }, cp.genesis_chain(LINEAGE))
    second, _ = cp.encode_frame(2, "LEDGER_HEADER", {
        "lineage_id": LINEAGE, "segment_no": 0, "first_seq": 2, "prev_chain": chain,
    }, chain)
    scan = cp.scan_segments([cp.Segment(0, first + second)], LINEAGE)
    assert [r.seq for r in scan.records] == [1]
    assert scan.tail == second
