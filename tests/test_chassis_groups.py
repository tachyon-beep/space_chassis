"""Atomic tool groups and structural repair of the outgoing view (SV-019 K-G1).

Contract: SV-013 section 2.2.6 "Atomic groups and repair" (SV-011 B6.2-B6.3):
every assistant message with tool calls is followed by exactly one tool
message per call; misplaced system messages move after the group; orphan tool
messages become user-role notices; selection never splits a group. SV-015 v2
section 2.3 leaves the window budget, chunking and pinned policy unchanged.

Scope, stated: `repair_structure` is pure and is applied to the *outgoing* view
only. The stored conversation is never rewritten here (durable repair at
recovery is SV-013 K-G2), so stored indices -- and the recap's fold point --
keep referring to the original messages. A synthesized result says the
outcome is unknown; it is never evidence that a past call did not run.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))

import chassis  # noqa: E402
from chassis import repair_structure  # noqa: E402


def user(text):
    return {"role": "user", "content": text}


def system(text):
    return {"role": "system", "content": text}


def asst(*ids, text=""):
    return {
        "role": "assistant",
        "content": text,
        "tool_calls": [
            {"id": i, "type": "function", "function": {"name": f"f_{i}", "arguments": "{}"}} for i in ids
        ],
    }


def tool(call_id, text="ok"):
    return {"role": "tool", "tool_call_id": call_id, "name": f"f_{call_id}", "content": text}


def well_formed(messages) -> bool:
    """Every call answered once, right after its assistant message; no stray tool messages."""
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.get("role") == "tool":
            return False
        calls = message.get("tool_calls") or []
        if message.get("role") == "assistant" and calls:
            answers = messages[index + 1 : index + 1 + len(calls)]
            if [a.get("role") for a in answers] != ["tool"] * len(calls):
                return False
            if [a.get("tool_call_id") for a in answers] != [c.get("id") for c in calls]:
                return False
            index += 1 + len(calls)
            continue
        index += 1
    return True


# ---------------------------------------------------------------------------
# repair_structure
# ---------------------------------------------------------------------------
def test_a_well_formed_list_is_returned_as_the_same_objects():
    messages = [system("s"), user("go"), asst("a", "b"), tool("a"), tool("b"), user("next")]
    repaired, notes = repair_structure(messages)
    assert notes == []
    assert all(x is y for x, y in zip(repaired, messages, strict=True))


def test_a_missing_result_is_synthesized_as_unknown_never_unrun():
    repaired, notes = repair_structure([user("go"), asst("a", "b"), tool("a"), user("then")])
    assert well_formed(repaired)
    synthetic = repaired[3]
    assert synthetic == {
        "role": "tool",
        "tool_call_id": "b",
        "name": "f_b",
        "content": chassis.REPAIRED_UNKNOWN_RESULT,
    }
    assert "unknown" in synthetic["content"] and "not run" not in synthetic["content"]
    assert notes == [{"kind": "synthetic_result", "tool_call_id": "b"}]


def test_a_system_message_inside_a_group_moves_after_it():
    note = system("a fact")
    repaired, notes = repair_structure([user("go"), asst("a", "b"), tool("a"), note, tool("b")])
    assert [m["role"] for m in repaired] == ["user", "assistant", "tool", "tool", "system"]
    assert repaired[-1] is note and well_formed(repaired)
    assert notes == [{"kind": "moved_system"}]


def test_orphan_tool_messages_become_documented_user_notices():
    stray = tool("zz", "result text")
    repaired, notes = repair_structure([user("go"), stray, asst("a"), tool("a"), tool("a", "again")])
    assert repaired[1] == {"role": "user", "content": "[orphan tool result for zz]: result text"}
    assert repaired[-1] == {"role": "user", "content": "[orphan tool result for a]: again"}
    assert well_formed(repaired)
    assert [n["kind"] for n in notes] == ["orphan", "orphan"]
    structured = repair_structure([{"role": "tool", "tool_call_id": None, "content": [{"text": "x"}]}])[0]
    assert structured == [{"role": "user", "content": '[orphan tool result for None]: [{"text": "x"}]'}]


def test_a_group_ends_at_the_first_message_that_is_not_a_tool_or_system_message():
    repaired, _notes = repair_structure([asst("a", "b"), tool("a"), user("interrupted"), tool("b")])
    assert [m["role"] for m in repaired] == ["assistant", "tool", "tool", "user", "user"]
    assert repaired[2]["content"] == chassis.REPAIRED_UNKNOWN_RESULT
    assert repaired[4]["content"].startswith("[orphan tool result for b]")


def test_results_are_paired_in_call_order_and_duplicate_call_ids_pair_one_each():
    repaired, _notes = repair_structure([asst("a", "a", "b"), tool("b", "B"), tool("a", "A1"), tool("a", "A2")])
    assert [m.get("content") for m in repaired[1:]] == ["A1", "A2", "B"]


def test_repair_is_idempotent():
    broken = [
        system("s"),
        user("go"),
        tool("stray"),
        asst("a", "b", "c"),
        system("inside"),
        tool("c"),
        tool("a"),
        tool("a", "dup"),
        user("later"),
        tool("b"),
        asst("d"),
    ]
    once, notes = repair_structure(copy.deepcopy(broken))
    twice, again = repair_structure(copy.deepcopy(once))
    assert twice == once and again == [] and notes
    assert well_formed(once)


# ---------------------------------------------------------------------------
# Group-atomic selection and the outgoing view
# ---------------------------------------------------------------------------
def groups_of(messages):
    """Each tool group as (head index, [assistant and tool member indices])."""
    groups = []
    for index, message in enumerate(messages):
        if message.get("role") == "assistant" and message.get("tool_calls"):
            members = [index]
            following = index + 1
            while following < len(messages) and messages[following].get("role") in ("tool", "system"):
                if messages[following].get("role") == "tool":
                    members.append(following)
                following += 1
            groups.append((index, members))
    return groups


def assert_group_atomic(messages, indices, start):
    """The oracle, on original indices: every group's assistant and results are all in or all out.

    Pinned system messages are exempt (they are always sent); nothing else is,
    and in particular not the last index.
    """
    chosen = set(indices)
    for head, members in groups_of(messages):
        inside = [member in chosen for member in members]
        assert all(inside) or not any(inside), f"group at {head} split: {list(zip(members, inside))}"
    assert not chassis.inside_group(messages)[start], f"the window starts inside a group at {start}"


def test_the_window_never_opens_inside_a_group_at_an_interposed_system_message():
    """Before K-G1 only a tool message was skipped; a system message inside a group was a valid start."""
    messages = [system("sys"), user("go")]
    for index in range(30):
        messages += [asst(f"c{index}"), system(f"inside {index}"), tool(f"c{index}", "r" * 200)]
    for budget in (1, 200, 400, 800, 1600):
        for chunk in (1, 50, 400):
            indices, start = chassis.selection(messages, budget, chunk)
            assert_group_atomic(messages, indices, start)


def test_an_oversized_newest_single_call_group_is_kept_whole():
    """SV019-G1-01: the minimal case. Before the fix the result was kept without its call."""
    messages = [user("go"), asst("a"), tool("a", "x" * 1000)]
    indices, start = chassis.selection(messages, 1, 1)
    assert indices == [0, 1, 2] and start == 1
    assert chassis.window_bounds(messages, 1, 1) == (1, 2), "the fold boundary is the group's head"
    carried = chassis.Carried(Path("/nonexistent/session"), Path("/nonexistent/home"))
    sent = chassis.prepared_view(messages, 1, 1, carried)
    assert sent == messages and all(x is y for x, y in zip(sent, messages, strict=True)), (
        "no orphan notice was made from a complete retained group"
    )


def test_an_oversized_newest_multi_call_group_is_kept_whole_with_its_system_messages():
    messages = [
        system("standing"),
        user("go"),
        asst("old"),
        tool("old", "o" * 300),
        user("next"),
        asst("a", "b"),
        system("inside"),
        tool("a", "x" * 800),
        tool("b", "y" * 800),
        system("after"),
    ]
    indices, start = chassis.selection(messages, 50, 10)
    assert start == 5
    assert indices == [0, 1, 5, 6, 7, 8, 9], "the older group is out whole; the newest is in whole"
    assert_group_atomic(messages, indices, start)
    carried = chassis.Carried(Path("/nonexistent/session"), Path("/nonexistent/home"))
    sent = chassis.prepared_view(messages, 50, 10, carried)
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "tool", "tool", "system", "system"]
    assert [m.get("tool_call_id") for m in sent[3:5]] == ["a", "b"]
    assert chassis.REPAIRED_UNKNOWN_RESULT not in json.dumps(sent)
    assert "orphan tool result" not in json.dumps(sent)


def test_a_trailing_system_message_does_not_split_the_newest_group():
    messages = [user("go"), asst("a"), tool("a", "x" * 1000), system("after")]
    indices, start = chassis.selection(messages, 1, 1)
    assert start == 1 and indices == [0, 1, 2, 3]


def test_an_older_group_is_dropped_whole_and_the_newest_ordinary_tail_kept():
    messages = [user("go"), asst("c0"), tool("c0", "r" * 400), user("u1 " + "u" * 400), asst("a"), tool("a", "x" * 50)]
    for budget, chunk in ((40, 1), (40, 10), (60, 25), (130, 1)):
        indices, start = chassis.selection(messages, budget, chunk)
        assert_group_atomic(messages, indices, start)
        assert {4, 5} <= set(indices), "the newest group is always sent"


def test_repeated_folding_never_folds_part_of_a_retained_oversized_group(tmp_path):
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance = object.__new__(chassis.Chassis)
    instance.context_window = 50
    instance.eviction_chunk = 10
    instance.recap_folded = 0
    instance.carried = carried
    instance.record = lambda *_args, **_kwargs: None
    instance.messages = [system("sys"), user("go")]
    for round_index in range(8):
        instance.messages += [
            user(f"ask {round_index}"),
            asst(f"a{round_index}", text=f"calling {round_index}"),
            tool(f"a{round_index}", f"huge {round_index} " + "h" * 600),
        ]
        chassis.Chassis.fold_recap_if_needed(instance)
        head = len(instance.messages) - 2
        assert instance.recap_folded <= head, "part of the newest group was folded"
        indices, start = chassis.selection(instance.messages, 50, 10)
        assert start == head and indices[-2:] == [head, head + 1]
    recap = carried.recap()
    assert "calling 7" not in recap and "huge 7" not in recap
    assert "calling 0" in recap and recap.count("huge 0") == 1


def test_the_outgoing_view_is_repaired_and_the_stored_list_is_not():
    carried = chassis.Carried(Path("/nonexistent/session"), Path("/nonexistent/home"))
    stored = [system("sys"), user("go"), asst("a", "b"), system("inside"), tool("a"), tool("x"), user("now")]
    snapshot = copy.deepcopy(stored)
    sent = chassis.prepared_view(stored, 100_000, 100, carried)
    assert stored == snapshot, "the stored conversation was changed"
    assert well_formed(sent)
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "tool", "tool", "system", "user", "user"]
    assert sent[4]["content"] == chassis.REPAIRED_UNKNOWN_RESULT
    assert sent[6]["content"].startswith("[orphan tool result for x]")


def test_pinned_material_and_the_budget_are_unchanged_by_repair():
    carried = chassis.Carried(Path("/nonexistent/session"), Path("/nonexistent/home"))
    messages = [system("standing orders"), user("the mission")]
    messages += [user(f"turn {index} " + "x" * 400) for index in range(100)]
    plain = [messages[i] for i in chassis.selection(messages, 500, 100)[0]]
    sent = chassis.prepared_view(messages, 500, 100, carried)
    assert sent == plain, "a well-formed view is sent exactly as selected"
    assert sent[0]["content"] == "standing orders" and sent[1]["content"] == "the mission"


def test_repeated_folding_records_every_evicted_message_once_with_broken_groups(tmp_path):
    """The recap's fold point stays an index into the stored list: nothing duplicated, nothing lost."""
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance = object.__new__(chassis.Chassis)
    instance.context_window = 300
    instance.eviction_chunk = 60
    instance.recap_folded = 0
    instance.carried = carried
    instance.record = lambda *_args, **_kwargs: None
    instance.messages = [system("sys"), user("go")]
    for round_index in range(25):
        instance.messages += [
            asst(f"a{round_index}", f"b{round_index}", text=f"step {round_index}"),
            tool(f"a{round_index}", f"result a{round_index} " + "y" * 150),
            system(f"note {round_index}"),
            user(f"user {round_index} " + "z" * 150),
        ]
        chassis.Chassis.fold_recap_if_needed(instance)
        sent = chassis.prepared_view(instance.messages, 300, 60, carried)
        assert well_formed(sent)
    recap = carried.recap()
    folded = instance.messages[: instance.recap_folded]
    expected = [m for m in folded if m["role"] != "system" and chassis.render_message(m)]
    assert expected, "the run was long enough to fold"
    for message in expected:
        body = chassis.render_message(message)[: chassis.RECAP_LINE_CHARS]
        assert recap.count(body) == 1, f"folded {recap.count(body)} times: {body[:40]}"
    assert "[orphan tool result" not in recap and chassis.REPAIRED_UNKNOWN_RESULT not in recap, (
        "the view's repairs never reach the stored record"
    )
    assert json.dumps(instance.messages).count("orphan tool result") == 0
