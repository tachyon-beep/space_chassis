"""Whole runs: the recorder, the chassis and the supervisor, wired together.

These are the tests that would have caught the bugs this project found the hard
way: a supervisor launching a file that does not exist, a recorder rejecting a
path over its prefix, a refused allowance crashing the socket instead of
answering, a run that hit its turn budget losing the conversation it had.

Each one drives the real services against a stub model and then reads the
record, because the record is the only account of a run that the run cannot
edit.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from pathlib import Path

import chassis
import pytest
from conftest import Reply, Stack, ToolCall, World  # noqa: E402

PROJECT = Path(__file__).resolve().parent.parent


@pytest.fixture
def stack_of(world: World):
    """Build a stack with a chosen script, so a test can decide how a run ends."""
    opened: list[Stack] = []

    def build(script: list[Reply]) -> Stack:
        stack = Stack(world, script=script)
        stack.__enter__()
        opened.append(stack)
        return stack

    yield build
    for stack in opened:
        stack.__exit__(None, None, None)


def deliberate_script() -> list[Reply]:
    """A run with a beginning, a middle and an end it chose."""
    return [
        Reply(tool_calls=[ToolCall("status")]),
        Reply(tool_calls=[ToolCall("write_diary", {"entry": "checked in"})]),
        Reply(tool_calls=[ToolCall("handoff", {"note": "handing over deliberately"})]),
    ]


def ending_script() -> list[Reply]:
    """A model that closes the run when it has nothing left to say.

    This is what a metronome does at the end of a scenario. It exists because
    the alternative -- falling silent forever -- is indistinguishable from a
    stuck model, and a test that cannot tell the two apart tests nothing.
    """
    return [
        Reply(tool_calls=[ToolCall("status")]),
        Reply(tool_calls=[ToolCall("handoff", {"note": "the script is spent"})]),
    ]


def looping_script() -> list[Reply]:
    """A model that says exactly the same thing every single time."""
    return [Reply(text="I am thinking about it.", repeat=1000)]


def refusal_marker(world: World) -> Path:
    marker = world.root / "markers" / f"refuse-{world.slug}.marker"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}\n", encoding="utf-8")
    return marker


# ---------------------------------------------------------------------------
# The route out
# ---------------------------------------------------------------------------
def test_a_run_reaches_the_model_through_the_recorder(world, stack_of):
    """The unix socket is the only route, and it works."""
    stack = stack_of(deliberate_script())
    result = stack.run_chassis()
    assert result.returncode in (0, 42), result.stderr[-2000:]
    assert stack.transcript(), "the recorder wrote no transcript"
    assert stack.events(), "the recorder wrote no events"


def test_the_recorder_injects_a_credential_the_agent_never_has(world, stack_of):
    """The agent sends a shape; the recorder sends the key. Neither leaks."""
    stack = stack_of(deliberate_script())
    stack.run_chassis()
    transcript = (world.transcripts / world.slug / "agent_life_transcript.jsonl").read_text(
        encoding="utf-8"
    )
    events = (world.transcripts / world.slug / "events.jsonl").read_text(encoding="utf-8")
    for blob in (transcript, events):
        assert "authorization" not in blob.lower(), "a header reached the record"
        assert "sk-test" not in blob, "the recorder's key reached the record"


def test_the_record_lands_where_the_agent_cannot_write_it(world, stack_of):
    """The transcript is written by the recorder onto a volume the agent only reads."""
    stack = stack_of(deliberate_script())
    stack.run_chassis()
    assert (world.transcripts / world.slug / "agent_life_transcript.jsonl").exists()
    assert (world.telemetry / "agents" / world.slug / "lifecycle.jsonl").exists()


# ---------------------------------------------------------------------------
# How a run ends, and what that costs
# ---------------------------------------------------------------------------
def test_a_designed_handoff_carries_the_conversation_forward(world, stack_of):
    """A run that ends on purpose must not cost the lineage its memory."""
    stack = stack_of(deliberate_script())
    first = stack.run_chassis()
    assert first.returncode == 42, first.stderr[-500:]
    conversation = stack.conversation()
    assert any(message.get("role") == "assistant" for message in conversation), (
        "the conversation was not saved"
    )

    again = stack.run_chassis()
    assert again.returncode in (0, 42)
    resumed = [record for record in stack.lifecycle() if record.get("event") == "run_resumed"]
    assert resumed, f"the second run did not resume: {stack.lifecycle()[-3:]}"


def test_a_second_run_appends_to_the_conversation_rather_than_inverting_it(world, stack_of):
    """A resumed lineage keeps its transcript in order and stores no recap frames.

    One stored recap per resume, pinned and re-sent, is how a real lineage
    reached 1.33 M estimated tokens against a 200 000-token window; and a handoff
    inserted at the front is how the newest material ended up where the window
    drops first.
    """
    stack = stack_of(deliberate_script())
    first = stack.run_chassis()
    assert first.returncode == 42, first.stderr[-500:]
    second = stack.run_chassis()
    assert second.returncode in (0, 42), second.stderr[-500:]

    conversation = stack.conversation()
    assert conversation, "the second run left no conversation"
    frames = [
        message
        for message in conversation
        if str(message.get("content", "")).startswith(chassis.RECAP_FRAME_PREFIX)
    ]
    assert frames == [], f"{len(frames)} stored recap frame(s) in the conversation"

    notes = [
        index
        for index, message in enumerate(conversation)
        if "left this handoff note" in str(message.get("content", ""))
    ]
    first_assistant = next(
        index for index, message in enumerate(conversation) if message.get("role") == "assistant"
    )
    assert notes, "the second run did not open on the first run's handoff note"
    assert min(notes) > first_assistant, "the handoff note was placed in front of the transcript"


def test_a_turn_limit_ends_a_run_without_ending_the_lineage(world, stack_of):
    """A budget is not a fault. This is the difference between busy and broken."""
    stack = stack_of(deliberate_script())
    result = stack.run_chassis(extra_env={"RUN_MAX_TURNS": "1"})
    assert result.returncode == 42, (
        f"a turn limit exited {result.returncode}: {result.stderr[-400:]}"
    )
    assert stack.conversation(), "a budget-limited run lost its conversation"


def test_a_model_that_repeats_itself_ends_the_run_rather_than_spinning(world, stack_of):
    """A stuck run is indistinguishable from a busy one until something stops it.

    Without this, a model that answers identically forever burns the whole
    window and the record shows a healthy agent working the entire time.
    """
    stack = stack_of(looping_script())
    result = stack.run_chassis()
    assert result.returncode == 42, f"a looping model produced exit {result.returncode}"
    notes = "".join(
        record.get("note", "") for record in stack.lifecycle() if record.get("event") == "run_end"
    )
    assert "same reply" in notes, notes


def test_a_run_that_cannot_import_is_a_duty_fault(world, stack_of):
    """Broken code must climb the ladder, not pause forever."""
    stack = stack_of(deliberate_script())
    (world.work / "duty.py").write_text("def main(context)\n    broken\n", encoding="utf-8")
    result = stack.run_chassis()
    assert result.returncode == 43, f"unimportable code exited {result.returncode}"


# ---------------------------------------------------------------------------
# The environment's fault is not the run's
# ---------------------------------------------------------------------------
def test_an_unreachable_recorder_pauses_rather_than_climbing(world, stack_of):
    """The run was fine; the socket was not."""
    stack = stack_of(deliberate_script())
    result = stack.run_chassis(
        extra_env={
            "LLM_SOCKET_PATH": str(world.root / "no-such.sock"),
            "SOCKET_WAIT_SECONDS": "1",
        }
    )
    assert result.returncode == 44, f"an unreachable recorder exited {result.returncode}"


def test_a_refused_socket_is_an_environment_failure_and_is_recorded(world, stack_of):
    """A recorder refusing everything is the case the ladder must not climb on."""
    stack = stack_of(deliberate_script())
    refusal_marker(world)
    result = stack.run_chassis()
    assert result.returncode == 44, result.stderr[-400:]
    refusals = [event for event in stack.events() if event.get("refusal")]
    assert refusals, "the refusal was not recorded"
    closes = [event for event in stack.events() if event.get("event") == "close"]
    assert any(event.get("status") == 503 for event in closes), closes


# ---------------------------------------------------------------------------
# The supervisor
# ---------------------------------------------------------------------------
def test_the_supervisor_records_a_death_and_restarts_the_run(world, stack_of):
    """One run kills itself; the record says so and another run begins."""
    stack = stack_of(deliberate_script())
    (world.work / "duty.py").write_text(
        "import sys\n\ndef main(context):\n    sys.exit(99)\n", encoding="utf-8"
    )
    # The supervisor loops by design, so a timeout is the normal end of this
    # call; the record it left is what the test is about.
    with contextlib.suppress(subprocess.TimeoutExpired):
        stack.run_supervisor(timeout=30, extra_env={"SUPERVISOR_PAUSE_SECONDS": "1"})

    lifecycle = stack.lifecycle()
    deaths = [record for record in lifecycle if record.get("event") == "failure"]
    assert deaths, f"a run exiting 99 was not recorded as a failure: {lifecycle[-4:]}"
    assert [record for record in lifecycle if record.get("event") == "run_start"], (
        "the supervisor never started a run"
    )


def test_the_supervisor_restores_the_duty_when_it_will_not_import(world, stack_of):
    """Broken code climbs the ladder, and the rung that answers is the seed."""
    stack = stack_of(deliberate_script())
    broken = "def main(context)\n    this is not python\n"
    (world.work / "duty.py").write_text(broken, encoding="utf-8")
    with contextlib.suppress(subprocess.TimeoutExpired):
        stack.run_supervisor(timeout=30, extra_env={"SUPERVISOR_PAUSE_SECONDS": "1"})
    lifecycle = stack.lifecycle()
    restored = [record for record in lifecycle if record.get("event") == "restore_floor"]
    assert restored, f"the ladder never reached the floor restore: {lifecycle[-4:]}"
    assert (world.work / "duty.py").read_text(encoding="utf-8") != broken


def test_a_killed_run_reads_as_a_crash(world, stack_of):
    """`poll()` reports a signalled child as negative; that is not a clean exit."""
    import supervisor as supervisor_module  # noqa: PLC0415 -- local to this check

    assert supervisor_module.normalise_exit(-9) == 137
    assert supervisor_module.normalise_exit(0) == 0


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------
def test_the_lifecycle_record_says_how_each_run_ended(world, stack_of):
    """What an operator reads to tell a busy fleet from a broken one."""
    stack = stack_of(deliberate_script())
    stack.run_chassis()
    path = world.telemetry / "agents" / world.slug / "lifecycle.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    events = [record["event"] for record in records]
    assert "run_start" in events and "run_end" in events
    ended = next(record for record in records if record["event"] == "run_end")
    assert ended["exit"] == 42
    assert "turns" in ended


def test_the_operations_record_shows_what_the_run_actually_did(world, stack_of):
    """Tool calls, separately from turns, so the two can be told apart."""
    stack = stack_of(deliberate_script())
    stack.run_chassis()
    path = world.telemetry / "agents" / world.slug / "operations.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    tools = [record for record in records if record.get("kind") == "tool"]
    assert tools, f"no tool calls were recorded: {records[:3]}"
    assert any(record.get("tool") == "status" for record in tools)


def test_the_pump_runs_work_the_agent_scheduled(world, stack_of):
    """The mechanism for making work outlive the run that arranged it."""
    stack = stack_of(deliberate_script())
    entries = world.pump / world.slug / "entries.json"
    entries.write_text(
        json.dumps(
            [
                {
                    "name": "heartbeat",
                    "command": ["/bin/sh", "-c", f"date >> {world.diary}/heartbeat.txt"],
                    "mode": "interval",
                    "every_seconds": 60,
                    "enabled": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    env = dict(stack.env)
    env["PUMP_MAX_ENTRIES"] = "4"
    process = subprocess.Popen(
        [sys.executable, str(PROJECT / "services" / "pump.py")],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = 30
        for _ in range(deadline * 4):
            if (world.diary / "heartbeat.txt").exists():
                break
            import time  # noqa: PLC0415 -- bounded wait, local to this test

            time.sleep(0.25)
    finally:
        process.terminate()
        process.communicate(timeout=10)

    assert (world.diary / "heartbeat.txt").exists(), (
        "the pump did not run a scheduled entry; its output was "
        + (process.stdout.read() if process.stdout else "")[:400]
    )
    state = json.loads((world.pump / world.slug / "state.json").read_text())
    assert state["entries"]["heartbeat"]["running"] is True


def test_a_turn_that_only_called_a_tool_is_not_a_silent_turn(world, stack_of):
    """A model acting without narrating must not be read as having said nothing.

    A provider is free to return a tool call with no accompanying text, and that
    is ordinary. The seed duty reads an empty `ask()` as "the model has nothing
    to add" and hands over -- so without a way to tell the two apart, every run
    ends the moment a model stops talking between calls. This is the regression
    that found it.
    """
    stack = stack_of(
        [
            Reply(tool_calls=[ToolCall("status")]),
            Reply(text="done, nothing more to add", repeat=100),
        ]
    )
    result = stack.run_chassis()
    assert result.returncode in (0, 42)
    turns = stack.transcript()
    assert len(turns) >= 2, f"the run ended after {len(turns)} turn(s)"

    # The first turn said nothing and called a tool; a second turn followed, so
    # it was not treated as silence.
    statuses = [
        call["function"]["name"]
        for turn in turns
        for call in (
            turn.get("response", {}).get("choices", [{}])[0].get("message", {}).get("tool_calls")
            or []
        )
    ]
    assert "status" in statuses, statuses
