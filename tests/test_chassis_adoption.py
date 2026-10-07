"""Bounded response adoption (SV-013 K-E2; SV-015 v2 section 2.3).

Pure tests of `chassis_envelope.adopt_response` and its helpers: C-B5...C-B7,
O4-1, O4-8...O4-12 and the argument/name dispositions. The literal values are
SV-015 v2's (`SV-015-literal-values-v2.json`, the literal generator's shapes)
and SV-013 section 3.5's C-B rows; no provider, file or ledger is touched
except where a test encodes a TURN_RESPONSE frame to check that it fits.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))

import chassis_envelope as env  # noqa: E402
import chassis_persistence as cp  # noqa: E402
from chassis_envelope import Caps, RawCall, RawResponse, adopt_response  # noqa: E402

K = 1024


def response(calls=(), content="", reasoning=None) -> RawResponse:
    return RawResponse(content, reasoning, tuple(RawCall(*call) for call in calls))


def calls_of(n: int, args: str = '{"path": "x"}'):
    return [(f"call_{i}", "read_file", args) for i in range(n)]


# ---------------------------------------------------------------------------
# Tool-call counts (v2 2.3 table; O4-8; C-B5, C-B7)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("n", "stored", "invokable", "limit_unrun", "omitted"),
    [(1, 1, 1, 0, 0), (16, 16, 16, 0, 0), (17, 17, 16, 1, 0), (32, 32, 16, 16, 0), (33, 32, 16, 16, 1), (256, 32, 16, 16, 224)],
)
def test_o4_8_call_counts_follow_the_table(n, stored, invokable, limit_unrun, omitted):
    adoption = adopt_response(response(calls_of(n)), turn_seq=7)
    assert not adoption.refused
    assert len(adoption.assistant.get("tool_calls", [])) == stored == len(adoption.calls)
    assert [c.admit for c in adoption.calls].count("invoke") == invokable
    assert [c.admit for c in adoption.calls].count("not_run_call_limit") == limit_unrun
    for call in adoption.calls[16:]:
        assert call.admit_text == "not run: the call limit was reached" and call.invoke_arguments is None
        assert json.loads(call.arguments)["_runtime_elided"]["bytes"] == len(b'{"path": "x"}')
    if omitted:
        assert adoption.omitted["count"] == omitted
        assert adoption.notice == f"[runtime] the response contained {n} tool calls; calls 33–{n} were not stored or run"
        objects = [
            {"id": f"call_{i}", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "x"}'}}
            for i in range(32, n)
        ]
        canonical = json.dumps(objects, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        assert adoption.omitted["sha256"] == hashlib.sha256(canonical).hexdigest()
    else:
        assert adoption.omitted is None and adoption.notice is None


def test_o4_8_negative_control_the_omitted_hash_covers_only_omitted_calls():
    a = adopt_response(response(calls_of(33)), turn_seq=7)
    changed = calls_of(33)
    changed[0] = ("call_0", "read_file", '{"path": "other"}')
    b = adopt_response(response(changed), turn_seq=7)
    assert a.omitted == b.omitted, "a stored call changed the omitted hash"
    changed[32] = ("call_32", "read_file", '{"path": "other"}')
    assert adopt_response(response(changed), turn_seq=7).omitted != a.omitted


def test_o4_8_257_calls_are_refused_with_one_notice_and_nothing_stored():
    adoption = adopt_response(response(calls_of(257)), turn_seq=7)
    assert adoption.refused and adoption.assistant is None and adoption.calls == ()
    assert adoption.notice == (
        "[runtime] the model response contained 257 tool calls (limit 256) and was not adopted; nothing was run"
    )
    # v2's three keys, plus the notice the record owes (SV021-06).
    assert adoption.refusal_payload() == {"turn_seq": 7, "reason": "too_many_calls", "count": 257, "notice": adoption.notice}


def test_c_b5_a_call_past_the_invocation_cap_is_stored_elided_and_not_run():
    caps = Caps(calls=2, calls_stored=3)
    adoption = adopt_response(response(calls_of(3)), turn_seq=7, caps=caps)
    assert [c.admit for c in adoption.calls] == ["invoke", "invoke", "not_run_call_limit"]
    third = adoption.assistant["tool_calls"][2]
    assert json.loads(third["function"]["arguments"]) == {
        "_runtime_elided": {"bytes": 13, "sha256": hashlib.sha256(b'{"path": "x"}').hexdigest()}
    }
    assert adoption.calls[2].admit_text == env.CALL_LIMIT_TEXT


def test_c_b7_more_calls_than_the_hard_cap_are_refused():
    adoption = adopt_response(response(calls_of(5)), turn_seq=7, caps=Caps(calls=2, calls_stored=3, calls_hard=4))
    assert adoption.refused and adoption.refusal_payload()["count"] == 5 and adoption.assistant is None


# ---------------------------------------------------------------------------
# Arguments (C-B6) and names
# ---------------------------------------------------------------------------
def test_c_b6_oversize_arguments_are_elided_and_the_original_offered_for_retention():
    args = '{"path":"' + "x" * 188 + '"}'
    assert len(args.encode()) == 199
    adoption = adopt_response(response([("call_a", "read_file", args)]), turn_seq=7, caps=Caps(args=160))
    (call,) = adoption.calls
    assert call.admit == "oversize_args" and call.invoke_arguments is None
    expected = '{"_runtime_elided":{"bytes":199,"sha256":"4771cad37a670d67956a31078f3653c44009363623f43e3e3239ae6cd4896fbf"}}'
    assert call.arguments == expected and len(expected.encode()) == 109
    assert call.admit_text == "error: arguments elided: 199 bytes over the CAP_ARGS limit"
    assert adoption.originals == (env.Original("args", "tool_calls[0].function.arguments", args.encode()),)
    assert "tool_calls[0].function.arguments" in adoption.normalization["truncated_fields"]


def test_the_elision_fits_its_bound_for_twelve_digit_sizes():
    longest = json.dumps({"_runtime_elided": {"bytes": 10**12 - 1, "sha256": "0" * 64}}, separators=(",", ":"))
    assert len(longest.encode()) <= 118 and env.escaped_units(longest) == 126


BAD_JSON = "error: arguments were not valid json: "


@pytest.mark.parametrize(
    ("args", "admit", "text", "verbatim"),
    [
        ("", "invoke", None, True),
        ('{"path": "x"}', "invoke", None, True),
        ("[1, 2]", "bad_args", "error: arguments must be a json object", True),
        ("{not json", "bad_args", BAD_JSON + "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)", True),
        ("{" + "x" * 511, "bad_args", BAD_JSON + "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)", True),
        ("{" + "x" * 512, "bad_args", "error: arguments were not valid json (513 bytes, elided)", False),
    ],
    ids=["empty", "object", "array", "invalid-short", "invalid-512-kept", "invalid-513-elided"],
)
def test_argument_dispositions(args, admit, text, verbatim):
    adoption = adopt_response(response([("call_a", "read_file", args)]), turn_seq=7)
    (call,) = adoption.calls
    assert (call.admit, call.admit_text) == (admit, text)
    assert call.invoke_arguments == (args if admit == "invoke" else None), "only an admitted call is ever parsed for invocation"
    if verbatim:
        assert call.arguments == args
        assert adoption.originals == ()
    else:
        assert json.loads(call.arguments)["_runtime_elided"]["bytes"] == 513
        assert adoption.originals[0].data == args.encode()


@pytest.mark.parametrize(
    ("name", "stored", "why"),
    [
        (None, "", "not a string: NoneType"),
        (42, "", "not a string: int"),
        ("", "", "empty"),
        ("n" * 65, "n" * 64, "longer than 64 escaped units"),
        ("é" * 11, "é" * 10, "longer than 64 escaped units"),
        ("read\ud800", "read?", "contained unpaired surrogates"),
    ],
    ids=["none", "int", "empty", "long-ascii", "long-bmp", "surrogate"],
)
def test_a_malformed_name_is_bad_name_and_never_invoked(name, stored, why):
    adoption = adopt_response(response([("call_a", name, '{"path": "x"}')]), turn_seq=7)
    (call,) = adoption.calls
    assert call.admit == "bad_name" and call.invoke_arguments is None
    assert call.name == stored and adoption.assistant["tool_calls"][0]["function"]["name"] == stored
    assert call.admit_text == f"error: the tool name was refused ({why}); the call was not run"
    assert env.escaped_units(call.name) <= 64


def test_a_64_unit_name_is_accepted_whole():
    adoption = adopt_response(response([("call_a", "n" * 64, "{}")]), turn_seq=7)
    assert adoption.calls[0].admit == "invoke" and adoption.calls[0].name == "n" * 64


def test_non_string_arguments_are_coerced_and_recorded():
    adoption = adopt_response(response([("call_a", "read_file", {"path": "x"})]), turn_seq=7)
    assert adoption.calls[0].arguments == '{"path": "x"}' and adoption.calls[0].admit == "invoke"
    assert adoption.normalization["coerced_fields"] == ["tool_calls[0].function.arguments"]


# ---------------------------------------------------------------------------
# Ids (O4-9, O4-12; C-B8...C-B10) inside an adoption
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("ids", "wire"),
    [
        (["call_a", "call_a"], ["call_a.rt0", "call_a.rt1"]),
        (["a", "a", "a.rt0"], ["a.rt0.1", "a.rt1", "a.rt0"]),
        (["call_a", None], ["call_a", "rt.7.rt1"]),
        (["ok", "bad\ud800", 42, {"k": 1}, "é", ""], ["ok", "rt.7.rt1", "rt.7.rt2", "rt.7.rt3", "rt.7.rt4", "rt.7.rt5"]),
    ],
    ids=["c-b8-dup", "o4-12-collide", "c-b10-missing", "o4-9-surrogate"],
)
def test_wire_ids_are_the_same_in_the_message_and_the_ledger(ids, wire):
    adoption = adopt_response(response([(i, "read_file", "{}") for i in ids]), turn_seq=7)
    assert [c["id"] for c in adoption.assistant["tool_calls"]] == wire
    assert [c.ledger["wire_id"] for c in adoption.calls] == wire
    assert len(set(wire)) == len(wire)


def test_o4_12_negative_control_seeding_only_processed_ids_collides():
    ids = ["a", "a", "a.rt0"]
    used, wire = set(), []
    for index, value in enumerate(ids):
        if ids.count(value) == 1:
            wire.append(value)
        else:
            candidate = f"{value}.rt{index}"
            while candidate in used:
                candidate += ".1"
            wire.append(candidate)
        used.add(wire[-1])
    assert wire == ["a.rt0", "a.rt1", "a.rt0"], "the oracle can fail"
    assert env.assign_wire_ids(ids, 7) != wire


def test_provider_id_repr_keeps_type_size_and_hash_never_the_value():
    assert env.provider_id_repr("call_q") == {"type": "str", "E": 6, "sha256": hashlib.sha256(b'"call_q"').hexdigest()}
    rep = env.provider_id_repr("bad\ud800")
    assert rep["type"] == "str" and "bad" not in json.dumps(rep)
    assert env.provider_id_repr(None)["type"] == "NoneType"


# ---------------------------------------------------------------------------
# Text caps and normalization (O4-1; C-B11 inside an adoption)
# ---------------------------------------------------------------------------
def test_o4_1_a_result_of_160_nuls_is_cut_in_escaped_units():
    text, info = env.stored_result("\x00" * 160, 160)
    assert text.startswith("\x00" * 8) and not text.startswith("\x00" * 9)
    assert info["truncated"] and info["kept_bytes"] == 8 and info["original_bytes"] == 160
    assert info["sha256"].startswith("b3939788") and info["sha256"].endswith("c2e4")
    assert env.escaped_units(text) == 155 and len(text.encode()) == 114
    assert len(json.dumps(text)) - 2 <= 160, "the saved conversation grows by at most the cap"


def test_c_b11_a_lone_surrogate_result_is_stored_normalized():
    text, info = env.stored_result("\ud800x", 160)
    assert text == "?x" and info["replaced_chars"] == 1


def test_content_and_reasoning_over_their_caps_are_cut_and_offered_as_originals():
    adoption = adopt_response(response(content="a" * 200 + "\ud800", reasoning="b" * 300), turn_seq=7, caps=Caps(content=128, reasoning=128))
    content, reasoning = adoption.assistant["content"], adoption.assistant["reasoning_content"]
    assert env.escaped_units(content) <= 128 and env.escaped_units(reasoning) <= 128
    assert "[truncated: kept" in content and "[truncated: kept" in reasoning
    assert adoption.normalization["truncated_fields"] == ["content", "reasoning_content"]
    assert adoption.normalization["replaced_chars"] == 1
    assert [o.field for o in adoption.originals] == ["content", "reasoning_content"]
    assert adoption.originals[0].data == ("a" * 200 + "?").encode()


def test_an_ordinary_response_is_stored_exactly_as_before():
    adoption = adopt_response(response([("call_a", "read_file", '{"path": "x"}')], content="hi"), turn_seq=7)
    assert adoption.assistant == {
        "role": "assistant",
        "content": "hi",
        "tool_calls": [{"id": "call_a", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "x"}'}}],
    }
    assert adoption.normalization == {"replaced_chars": 0, "truncated_fields": [], "coerced_fields": []}
    assert "reasoning_content" not in adopt_response(response(content="x", reasoning=""), turn_seq=7).assistant


def test_caps_refuse_values_that_cannot_hold_their_markers():
    assert env.DEFAULT_CAPS.problem() is None
    assert Caps(result=127).problem() and Caps(args=159).problem() and Caps(note=100).problem()
    assert Caps(calls=17, calls_stored=16).problem()


# ---------------------------------------------------------------------------
# Envelope and request size (O4-10, O4-11) and the ledger fit
# ---------------------------------------------------------------------------
def generator_shapes():
    """SV-015 v2 literal generator's maximal shapes, rebuilt (section C of the generator)."""
    W, N = "w" * 64, "n" * 64
    elided = json.dumps({"_runtime_elided": {"bytes": 10**12 - 1, "sha256": "0" * 64}}, separators=(",", ":"))
    assistant = {
        "role": "assistant", "content": "a" * (64 * K), "reasoning_content": "b" * (64 * K),
        "tool_calls": [{"id": W, "type": "function", "function": {"name": N, "arguments": "x" * (32 * K)}} for _ in range(16)]
        + [{"id": W, "type": "function", "function": {"name": N, "arguments": elided}} for _ in range(16)],
    }
    tools = [{"role": "tool", "tool_call_id": W, "name": N, "content": "r" * (32 * K)} for _ in range(16)] + [
        {"role": "tool", "tool_call_id": W, "name": N, "content": env.CALL_LIMIT_TEXT} for _ in range(16)
    ]
    omitted = {"role": "user", "content": env.OMITTED_NOTICE.format(count=256, first=33)}
    queued = [{"role": "user", "content": "q" * (64 * K)} for _ in range(16)]
    return assistant, tools, omitted, queued


def inlist(msgs) -> int:
    return env.request_bytes({"m": [{"x": 1}] + msgs}) - env.request_bytes({"m": [{"x": 1}]})


def test_o4_10_the_request_form_reproduces_the_literal_envelope():
    assistant, tools, omitted, queued = generator_shapes()
    assert inlist([assistant]) == 663_951
    assert inlist(tools) == 531_024
    assert inlist([assistant, *tools]) == 1_194_975
    assert inlist([assistant, *tools, omitted, *queued]) == 2_244_201
    assert inlist([assistant, *tools]) * 1 < env.CLIENT_MAX_REQUEST_BYTES < inlist([assistant, *tools, omitted, *queued])


def test_o4_10_a_maximal_realizable_adoption_is_within_the_literal_shape():
    args = '{"k":"' + "x" * (32 * K - 12) + '"}'
    assert env.escaped_units(args) == 32 * K
    raw = response([("w" * 64, "n" * 64, args)] * 256, content="a" * (64 * K), reasoning="b" * (64 * K))
    adoption = adopt_response(raw, turn_seq=10**12 - 1)
    assistant, *_ = generator_shapes()
    assert adoption.assistant["content"] == "a" * (64 * K), "content at the cap is kept whole"
    assert inlist([adoption.assistant]) <= inlist([assistant])
    assert len(json.dumps([adoption.assistant], indent=2)) <= len(json.dumps([assistant], indent=2))


def test_the_largest_turn_response_frame_fits_the_ledger_body_limit():
    args = '{"k":"' + "x" * (32 * K - 12) + '"}'
    raw = response([("w" * 64, "\ud800" * 64, args)] * 256, content="\x00" * 70000, reasoning="\ud800" * 70000)
    adoption = adopt_response(raw, turn_seq=10**12 - 1)
    retained = [{"sha256": "0" * 64, "bytes": 10**12 - 1, "kind": "args", "field": "tool_calls[31].function.arguments"}] * 17
    payload = adoption.turn_response_payload(retained)
    frame, _chain = cp.encode_frame(10**12 - 1, "TURN_RESPONSE", payload, "0" * 64)
    assert len(frame) - cp.HEADER_BYTES - cp.TRAILER_BYTES <= cp.MAX_LEDGER_BODY


# ---------------------------------------------------------------------------
# The activated runtime (real Chassis.run(), fake client, temporary roots)
# ---------------------------------------------------------------------------
from test_chassis_termination import make_run, reply  # noqa: E402, F401 -- make_run is a fixture

COUNT_TOOL = "\n@tools.register\ndef count(n: int) -> str:\n    \"\"\"Count.\"\"\"\n    INVOKED.append('count')\n    return 'counted'\n"


def ledger_types(run) -> list[str]:
    session = run.root / "home" / "session"
    segments = cp.read_segments(session / "ledger")
    return [r.type_name for r in cp.scan_segments(segments, run.meta()["lineage_id"]).records]


def ledger_records(run) -> list:
    session = run.root / "home" / "session"
    segments = cp.read_segments(session / "ledger")
    return list(cp.scan_segments(segments, run.meta()["lineage_id"]).records)


def test_live_an_oversize_request_is_refused_locally_with_no_request_and_no_record(make_run):
    """v2 2.3 cause 1: pinned material (system messages) is sent whatever the window says."""
    main = "    for i in range(3):\n        context.note('x' * 1_000_000)\n    context.ask('go')\n"
    run = make_run([reply("never")], main=main)
    assert run.go() == 43
    assert run.client.sent == [], "nothing reached the client"
    assert "REQUEST_SENT" not in ledger_types(run), "no spend was recorded because none was possible"
    assert "request exceeds the recorder body limit" in run.run_end()["note"]


def test_live_the_correlation_label_is_the_recorded_label(make_run):
    run = make_run([reply("ok")], main="    context.ask('go')\n")
    labels = []
    real = run.client.create

    def create(**kwargs):
        labels.append(kwargs["extra_body"]["x_chassis_correlation"])
        return real(**kwargs)

    run.client.chat.completions.create = create
    run.go()
    sent = [r.payload["label"] for r in ledger_records(run) if r.type_name == "REQUEST_SENT"]
    assert labels == sent == [f"{run.meta()['lineage_id']}:1:1"]


@pytest.mark.parametrize(("n", "invoked", "stored"), [(16, 16, 16), (17, 16, 17), (32, 16, 32), (33, 16, 32), (256, 16, 32), (257, 0, 0)])
def test_live_call_counts_invoke_store_and_answer_exactly(make_run, n, invoked, stored):
    calls = [(f"c{i}", "count", {"n": i}) for i in range(n)]
    run = make_run([reply(calls=calls), reply("done")], main="    context.ask('go')\n", extra=COUNT_TOOL)
    run.go()
    assert run.duty.INVOKED.count("count") == invoked
    assistants = [m for m in run.chassis.messages if m["role"] == "assistant"]
    tools = [m for m in run.chassis.messages if m["role"] == "tool"]
    if n > 256:
        assert assistants == [], "the refused response was not stored, and the turn ended"
        assert tools == [] and "RESPONSE_REFUSED" in ledger_types(run) and "INVOKING" not in ledger_types(run)
        assert any("contained 257 tool calls (limit 256)" in m["content"] for m in run.chassis.messages)
        return
    assert len(assistants[0]["tool_calls"]) == stored and len(tools) == stored, "every stored call answered once"
    assert [t["tool_call_id"] for t in tools] == [f"c{i}" for i in range(stored)]
    assert all(t["content"] == env.CALL_LIMIT_TEXT for t in tools[16:])
    assert ledger_types(run).count("INVOKING") == invoked
    if n > 32:
        notice = f"[runtime] the response contained {n} tool calls; calls 33–{n} were not stored or run"
        assert run.chassis.messages[run.chassis.messages.index(tools[-1]) + 1]["content"] == notice


def test_live_a_bad_name_or_argument_is_never_invoked(make_run):
    calls = [("c0", "count", "{not json"), ("c1", "n" * 65, {"n": 1}), ("c2", "count", {"n": 2})]
    run = make_run([reply(calls=calls), reply("done")], main="    context.ask('go')\n", extra=COUNT_TOOL)
    run.go()
    assert run.duty.INVOKED == ["count"]
    tools = [m["content"] for m in run.chassis.messages if m["role"] == "tool"]
    # The fake client JSON-encodes argument values, so "{not json" arrives as a
    # JSON string: valid JSON, not an object -- refused as bad_args all the same.
    assert tools[0] == "error: arguments must be a json object"
    assert tools[1].startswith("error: the tool name was refused") and tools[2] == "counted"
    assert ledger_types(run).count("INVOKING") == 1


def test_o4_11_two_maximal_groups_exceed_the_recorder_cap_in_the_request_form():
    assistant, tools, _omitted, _queued = generator_shapes()
    group = [assistant, *tools]
    assert inlist(group + group) == 2_389_950
    body = {"model": "stub", "messages": [{"role": "user", "content": "OPENING"}, *group, *group]}
    assert env.request_bytes(body) > env.CLIENT_MAX_REQUEST_BYTES
    assert env.request_bytes(body) >= len(json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode())
