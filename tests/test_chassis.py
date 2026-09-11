"""The runtime: what a run is, and what survives one.

These are the properties that decide whether a lineage can last months rather
than minutes, so each test names the failure it is preventing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))

import chassis  # noqa: E402


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------
def message(role: str, text: str) -> dict:
    return {"role": role, "content": text}


def test_window_keeps_the_opening_and_the_system_message(tmp_path):
    """A run's standing instructions and its opening problem are never dropped.

    A run that has lost its opening problem no longer knows what it is doing,
    and it will not notice: the window is invisible from inside the turn.
    """
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    messages = [message("system", "you are"), message("user", "the mission")]
    messages += [message("assistant", f"turn {index} " + "x" * 400) for index in range(200)]

    sent = chassis.prepared_view(messages, 500, 100, carried)

    assert sent[0]["content"] == "you are", "the system message was not first"
    assert any(m["content"] == "the mission" for m in sent), "the opening user message was dropped"
    assert len(sent) < len(messages), "nothing was evicted, so the budget was not applied"
    assert sent[-1] is messages[-1], "the newest message must always be sent"
    # And the tail is what was bounded: the pinned pair is not what took the room.
    start, kept = chassis.window_bounds(messages, budget_tokens=500, chunk_tokens=100)
    assert kept < len(messages) - 2


def test_window_never_opens_on_an_orphaned_tool_result():
    """A tool result whose call was evicted is rejected by every upstream.

    A window that opens on one turns a long run into a crash loop, and the
    crash looks like a model problem rather than a windowing one.
    """
    messages = [message("system", "sys"), message("user", "go")]
    for index in range(50):
        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": f"c{index}", "function": {"name": "status", "arguments": "{}"}}
                ],
            }
        )
        messages.append(
            {"role": "tool", "tool_call_id": f"c{index}", "name": "status", "content": "ok"}
        )
    for budget in (200, 400, 800, 1600, 4000):
        start, _ = chassis.window_bounds(messages, budget_tokens=budget, chunk_tokens=50)
        assert messages[start]["role"] != "tool", (
            f"a window with budget {budget} opened on a tool result"
        )


def test_eviction_moves_in_chunks_so_the_prefix_is_stable():
    """Chunked eviction is what keeps consecutive requests cacheable.

    Evicting one message at a time moves the window's start every single turn.
    """
    messages = [message("system", "sys"), message("user", "go")]
    messages += [message("assistant", "y" * 400) for _ in range(100)]
    starts = [chassis.window_bounds(messages[: 50 + index], 1000, 400)[0] for index in range(20)]
    assert len(set(starts)) < len(starts), "the window start moved on every step"


def test_a_disabled_window_sends_everything():
    messages = [message("user", "a"), message("assistant", "b")]
    assert chassis.window_bounds(messages, budget_tokens=0) == (0, 2)


# ---------------------------------------------------------------------------
# The recap: the difference between a long run and a long run that forgot
# ---------------------------------------------------------------------------
def test_evicted_messages_are_recorded_before_they_are_lost(tmp_path):
    """The window is not a memory. Something has to notice what fell out of it."""
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    instance = object.__new__(chassis.Chassis)
    instance.context_window = 200
    instance.eviction_chunk = 50
    instance.recap_folded = 0
    instance.carried = carried
    instance.slug = "agent_1"
    instance.telemetry_dir = tmp_path / "telemetry"
    instance.lifecycle_path = tmp_path / "telemetry" / "lifecycle.jsonl"
    instance.messages = [message("system", "sys"), message("user", "go")]
    instance.messages += [
        message("assistant", f"the answer is {index} " + "z" * 300) for index in range(40)
    ]
    instance.record = lambda *_args, **_kwargs: None

    chassis.Chassis.fold_recap_if_needed(instance)

    recap = carried.recap()
    assert recap.strip(), "nothing was folded into the recap"
    assert instance.recap_folded > 0
    assert "the answer is 0" in recap, "the oldest material is exactly what should be there"


def test_the_recap_is_pinned_into_every_request(tmp_path):
    """A recap that is not sent is not a memory; it is a file."""
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    carried.append_recap(["- [assistant] we decided the second console is the backup"])
    messages = [message("system", "sys"), message("user", "go")] + [
        message("assistant", "f" * 200) for _ in range(50)
    ]
    sent = chassis.prepared_view(messages, budget_tokens=300, chunk_tokens=50, carried=carried)
    assert any("the second console is the backup" in str(m.get("content", "")) for m in sent)


def test_the_recap_is_not_duplicated_when_it_is_already_in_the_conversation(tmp_path):
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    carried.append_recap(["- [assistant] something"])
    recap = carried.recap()
    pinned = {
        "role": "system",
        "content": (
            "Recap of conversation that has fallen out of the context window. "
            "It is a lossy record, kept because the window is not a memory:\n\n" + recap
        ),
    }
    messages = [pinned, message("system", "sys"), message("user", "go")]
    sent = chassis.prepared_view(messages, budget_tokens=100_000, chunk_tokens=10, carried=carried)
    assert sum(1 for m in sent if m.get("content") == pinned["content"]) == 1


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------
def test_a_conversation_round_trips(tmp_path):
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    messages = [message("user", "hello"), message("assistant", "hi")]
    carried.save_conversation(messages)
    assert carried.conversation() == messages


def test_a_conversation_that_is_not_a_list_of_messages_is_refused(tmp_path):
    """A corrupt checkpoint must read as absent, not as a conversation.

    Loading it would fail every request from then on, which turns a bad file
    into a dead agent -- exactly the failure the ladder cannot see.
    """
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    carried.session_dir.mkdir(parents=True, exist_ok=True)
    for rubbish in ('{"not": "a list"}', "[1, 2, 3]", '[{"no_role": true}]', "not json at all"):
        carried.conversation_path.write_text(rubbish, encoding="utf-8")
        assert carried.conversation() is None, f"{rubbish!r} was accepted as a conversation"


def test_the_handoff_is_what_the_next_run_opens_with(tmp_path):
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    carried.handoff_path.parent.mkdir(parents=True, exist_ok=True)
    carried.handoff_path.write_text("attack the thermal problem first", encoding="utf-8")
    assert "thermal" in carried.handoff()


def test_a_recap_that_outgrows_its_cap_keeps_the_newest_material(tmp_path):
    """The recap is a window too, and it must fail the same way: newest kept."""
    carried = chassis.Carried(tmp_path / "session", tmp_path / "home")
    for index in range(200):
        carried.append_recap([f"- [assistant] event {index} " + "p" * 900])
    size = len(carried.recap().encode("utf-8"))
    assert size <= chassis.RECAP_MAX_BYTES, f"the recap grew to {size} bytes"
    assert "event 199" in carried.recap(), "the newest line was lost instead of the oldest"


# ---------------------------------------------------------------------------
# Exit-code semantics: the vocabulary the supervisor reads
# ---------------------------------------------------------------------------
def test_a_run_that_hits_its_turn_limit_resumes_rather_than_tombstones():
    """A budget is not a fault.

    If a turn limit tombstoned the run, the ladder would climb on a fleet that
    was merely busy, and the counting would eventually reset a lineage whose
    conversation was perfectly good.
    """
    assert chassis.EXIT_HANDOFF in chassis.RESUMING_EXITS
    assert chassis.EXIT_ENVIRONMENT in chassis.RESUMING_EXITS
    assert chassis.EXIT_DUTY_FAULT not in chassis.RESUMING_EXITS


def test_environment_failures_are_not_the_run_s_fault():
    """A spent balance and an unreachable recorder must pause, not tombstone."""
    for status in (402, 408, 429, 500, 503):
        error = type("E", (Exception,), {"status_code": status})(f"status {status}")
        assert isinstance(chassis.classify(error), chassis.EnvironmentFailure)

    spent = Exception("insufficient credits to run this request")
    assert isinstance(chassis.classify(spent), chassis.EnvironmentFailure)

    refused = type("E", (Exception,), {"status_code": 400})("bad tool schema")
    assert isinstance(chassis.classify(refused), chassis.DutyFault)


def test_a_duty_that_cannot_be_imported_is_a_duty_fault(tmp_path):
    """Broken code must climb the ladder; it must not pause forever."""
    from conftest import World  # noqa: PLC0415 -- the fixture module lives beside the tests

    world = World(tmp_path / "w")
    (world.work / "duty.py").write_text("def main(context)\n    return\n", encoding="utf-8")
    instance = object.__new__(chassis.Chassis)
    instance.entry = world.work / "duty.py"
    with pytest.raises(chassis.DutyFault):
        chassis.Chassis.load_duty(instance)


def test_a_duty_without_a_main_is_a_duty_fault(tmp_path):
    world_marker = tmp_path / "w"
    world_marker.mkdir()
    entry = world_marker / "duty.py"
    entry.write_text("x = 1\n", encoding="utf-8")
    instance = object.__new__(chassis.Chassis)
    instance.entry = entry
    with pytest.raises(chassis.DutyFault):
        chassis.Chassis.load_duty(instance)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
def test_a_tool_that_raises_is_reported_to_the_model_not_the_process():
    """Every tool failure is information; only a duty's own end is an exit."""
    from chassis import ToolRegistry  # noqa: PLC0415 -- local to this test's subject

    registry = ToolRegistry()

    @registry.register
    def explode() -> str:
        """Always fails."""
        raise ValueError("boom")

    instance = object.__new__(chassis.Chassis)
    instance.tools = registry
    instance.turn = 0
    instance.slug = "agent_1"
    instance.run_id = "test"
    instance.operations_path = Path("/nonexistent/operations.jsonl")

    result = chassis.Chassis.invoke(instance, "explode", "{}")
    assert "ValueError" in result and "boom" in result
    assert "no tool named" in chassis.Chassis.invoke(instance, "missing", "{}")
    assert "not valid json" in chassis.Chassis.invoke(instance, "explode", "{not json")


def test_tool_schemas_come_from_the_signature_and_the_docstring():
    from chassis import ToolRegistry  # noqa: PLC0415 -- local to this test's subject

    registry = ToolRegistry()

    @registry.register
    def probe(path: str, count: int = 3) -> str:
        """Probe something.

        Args:
            path: where to look
        """
        return path

    schema = registry.schemas[0]["function"]
    assert schema["name"] == "probe"
    assert schema["description"].startswith("Probe something")
    assert schema["parameters"]["required"] == ["path"]
    assert schema["parameters"]["properties"]["count"]["type"] == "integer"
