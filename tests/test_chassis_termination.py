"""Typed termination and the tool group's control flow (SV-019 K-B1).

Contract: SV-013 section 2.2.4, message and exit portions only. Fixtures C-T1...C-T8
use SV-013 section 3.5's shapes: `T(id, name, text)` is the tool message, and
the fake tools answer "x-contents" and "wrote 1 characters to /work/y".

What these tests do **not** cover, because this package does not implement
it: the ledger (`NOTE_WRITTEN`, `TERMINATION`, `UNRUN`, `DONE` records),
note generations and exactly-once adoption, and crash classification. The
handoff note keeps its legacy storage (`HANDOFF.md`). Where a C-T row names a
ledger record, only its message and exit portion is asserted here.

Every run is the real `Chassis.run()` against a scripted fake client and a
duty file in a temporary root. No provider, no socket, no subprocess.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))

import chassis  # noqa: E402

READ = "x-contents"
WROTE = "wrote 1 characters to /work/y"

DUTY = '''
import sys
chassis = sys.modules["chassis"]
tools = chassis.ToolRegistry()
CONTEXT = None
INVOKED = []


@tools.register
def read_file(path: str) -> str:
    """Read."""
    INVOKED.append("read_file")
    return "x-contents"


@tools.register
def write_file(path: str, text: str) -> str:
    """Write."""
    INVOKED.append("write_file")
    return "wrote 1 characters to /work/y"


@tools.register
def handoff(note: str) -> str:
    """Hand off."""
    INVOKED.append("handoff")
    CONTEXT.handoff(note)
    return "unreachable"


@tools.register
def act(what: str) -> str:
    """Do whatever the test says."""
    INVOKED.append("act")
    return BEHAVIOUR(CONTEXT, what)


def BEHAVIOUR(context, what):
    return "acted"

{extra}

def main(context):
    global CONTEXT
    CONTEXT = context
{main}
'''

ASK_TWICE = '    context.ask("go")\n    context.ask("again")\n'


def reply(content="", calls=()):
    tool_calls = [
        SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(args)))
        for call_id, name, args in calls
    ]
    message = SimpleNamespace(content=content, tool_calls=tool_calls or None, reasoning_content=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


class FakeClient:
    def __init__(self, replies) -> None:
        self.replies = list(replies)
        self.sent: list[list[dict]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.sent.append(copy.deepcopy(kwargs["messages"]))
        if not self.replies:
            return reply("nothing more")
        return self.replies.pop(0)


class Run:
    """A chassis, its fake client, and readers for what it left behind."""

    def __init__(self, root: Path, instance: chassis.Chassis, client: FakeClient) -> None:
        self.root = root
        self.chassis = instance
        self.client = client
        self.exit: int | None = None

    def go(self) -> int:
        self.exit = self.chassis.run()
        return self.exit

    @property
    def duty(self):
        return sys.modules["duty"]

    def lifecycle(self) -> list[dict]:
        path = self.root / "telemetry" / "agents" / "agent_t" / "lifecycle.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line]

    def run_end(self) -> dict:
        (end,) = [r for r in self.lifecycle() if r["event"] == "run_end"]
        return end

    def saved(self) -> list[dict]:
        return json.loads((self.root / "home" / "session" / "conversation.json").read_text())

    def meta(self) -> dict:
        return json.loads((self.root / "home" / "session" / "run.json").read_text())

    def after_first_assistant(self) -> list[dict]:
        messages = self.chassis.messages
        first = next(i for i, m in enumerate(messages) if m.get("role") == "assistant")
        return messages[first + 1 :]


@pytest.fixture
def make_run(tmp_path, monkeypatch):
    def build(replies, *, main=ASK_TWICE, extra="", root=None, env=None) -> Run:
        base = root or tmp_path
        for name in ("work", "home", "telemetry", "diary", "diode"):
            (base / name).mkdir(parents=True, exist_ok=True)
        (base / "work" / "duty.py").write_text(DUTY.format(extra=extra, main=main), encoding="utf-8")
        settings = {
            "AGENT_SLUG": "agent_t",
            "AGENT_NAME": "tester",
            "WORK_DIR": str(base / "work"),
            "AGENT_HOME": str(base / "home"),
            "DIARY_DIR": str(base / "diary"),
            "DIODE_DUTY_DIR": str(base / "diode"),
            "AGENT_ENTRY": str(base / "work" / "duty.py"),
            "TELEMETRY_DIR": str(base / "telemetry"),
            "LLM_MODEL": "stub",
            "CONTEXT_WINDOW_TOKENS": "200000",
        }
        settings.update(env or {})
        for name, value in settings.items():
            monkeypatch.setenv(name, value)
        for name in ("RUN_MAX_TURNS", "RUN_MAX_SECONDS", "CONTEXT_WINDOW_EVICTION_TOKENS"):
            if name not in settings:
                monkeypatch.delenv(name, raising=False)
        instance = chassis.Chassis()
        client = FakeClient(replies)
        monkeypatch.setattr(instance, "client", lambda: client)
        return Run(base, instance, client)

    return build


def T(call_id, name, text):  # noqa: N802 -- the fixture tables' own shorthand
    return {"role": "tool", "tool_call_id": call_id, "name": name, "content": text}


def paired(messages) -> bool:
    """Every assistant tool call has exactly one tool result, immediately after it."""
    _repaired, notes = chassis.repair_structure(messages)
    return notes == [] and not any(m.get("role") == "tool" for m in messages[:1])


# ---------------------------------------------------------------------------
# C-T1...C-T8
# ---------------------------------------------------------------------------
def test_c_t1_a_handoff_from_a_tool_answers_every_call_and_runs_no_more(make_run):
    run = make_run(
        [
            reply(
                calls=[
                    ("call_a", "read_file", {"path": "x"}),
                    ("call_h", "handoff", {"note": "N1"}),
                    ("call_c", "write_file", {"path": "y", "text": "z"}),
                ]
            )
        ]
    )
    assert run.go() == chassis.EXIT_HANDOFF
    assert run.after_first_assistant() == [
        T("call_a", "read_file", READ),
        T("call_h", "handoff", "handoff accepted; run ending"),
        T("call_c", "write_file", "not run: the run ended by handoff in call call_h"),
    ]
    assert run.duty.INVOKED == ["read_file", "handoff"], "a call after the handoff was invoked"
    assert run.run_end()["reason"] == "handoff" and run.meta()["ended"]["reason"] == "handoff"
    assert run.saved() == run.chassis.messages, "the saved list is the in-memory one"
    assert "N1" in (run.root / "home" / "HANDOFF.md").read_text(), "legacy handoff storage kept"


def test_c_t2_a_duty_that_swallows_the_handoff_continues_without_a_false_end(make_run):
    main = (
        "    try:\n"
        "        context.handoff('N2')\n"
        "    except SystemExit:\n"
        "        pass\n"
        "    context.ask('carry on')\n"
    )
    run = make_run([reply("still here")], main=main)
    assert run.go() == chassis.EXIT_OK
    end = run.run_end()
    assert end["reason"] == "main_returned", "the swallowed handoff was recorded as the end"
    assert run.chassis.messages[-1] == {"role": "assistant", "content": "still here"}
    assert "N2" in (run.root / "home" / "HANDOFF.md").read_text()


def test_c_t3_a_bare_sys_exit_42_is_not_a_handoff(make_run):
    extra = "def BEHAVIOUR(context, what):\n    sys.exit(42)\n"
    run = make_run(
        [reply(calls=[("call_s", "act", {"what": "exit"}), ("call_c", "write_file", {"path": "y", "text": "z"})])],
        extra=extra,
    )
    assert run.go() == 42
    assert run.after_first_assistant() == [
        T("call_s", "act", "the call raised SystemExit(42); the run ended"),
        T("call_c", "write_file", "not run: the run ended in call call_s"),
    ]
    assert run.run_end()["reason"] == "exit_42_without_termination_record"
    assert run.duty.INVOKED == ["act"]


def test_c_t4_an_invalid_exit_payload_is_the_runs_fault_not_an_escape(make_run):
    extra = "def BEHAVIOUR(context, what):\n    raise SystemExit(['x'])\n"
    run = make_run([reply(calls=[("call_s", "act", {"what": "exit"})])], extra=extra)
    assert run.go() == chassis.EXIT_DUTY_FAULT
    assert run.after_first_assistant() == [T("call_s", "act", "the call raised SystemExit(['x']); the run ended")]
    assert run.run_end()["reason"] == "invalid_exit_payload"


def test_c_t5_a_nested_ask_is_refused_as_the_tools_error_and_the_turn_goes_on(make_run):
    extra = "def BEHAVIOUR(context, what):\n    return context.ask('x')\n"
    run = make_run(
        [reply(calls=[("call_n", "act", {"what": "ask"}), ("call_a", "read_file", {"path": "x"})]), reply("done")],
        extra=extra,
    )
    assert run.go() == chassis.EXIT_OK
    after = run.after_first_assistant()
    assert after[:2] == [
        T("call_n", "act", "error: NestedTurnRefused: nested turn not supported"),
        T("call_a", "read_file", READ),
    ]
    assert len(run.client.sent) == 2, "the nested ask made no request"


def test_c_t6_a_note_from_a_tool_lands_after_all_of_the_groups_results(make_run):
    extra = "def BEHAVIOUR(context, what):\n    context.note('tool note')\n    return 'noted'\n"
    run = make_run(
        [reply(calls=[("call_n", "act", {"what": "note"}), ("call_a", "read_file", {"path": "x"})]), reply("done")],
        extra=extra,
    )
    run.go()
    assert run.after_first_assistant()[:3] == [
        T("call_n", "act", "noted"),
        T("call_a", "read_file", READ),
        {"role": "system", "content": "tool note"},
    ]
    assert paired(run.chassis.messages)


def test_c_t7_history_cannot_be_replaced_from_inside_a_tool(make_run):
    extra = "def BEHAVIOUR(context, what):\n    context.set_history([])\n    return 'replaced'\n"
    run = make_run([reply(calls=[("call_r", "act", {"what": "reset"})]), reply("done")], extra=extra)
    run.go()
    after = run.after_first_assistant()
    assert after[0] == T("call_r", "act", "error: RuntimeError: history cannot be replaced during a tool call")
    assert run.chassis.messages[0]["role"] == "user", "the history survived"


def test_c_t8_an_interrupt_during_a_call_leaves_its_outcome_unknown(make_run):
    extra = "def BEHAVIOUR(context, what):\n    raise KeyboardInterrupt\n"
    run = make_run(
        [
            reply(
                calls=[
                    ("call_a", "read_file", {"path": "x"}),
                    ("call_b", "act", {"what": "interrupt"}),
                    ("call_c", "write_file", {"path": "y", "text": "z"}),
                ]
            )
        ],
        extra=extra,
    )
    assert run.go() == chassis.EXIT_ENVIRONMENT
    assert run.after_first_assistant() == [
        T("call_a", "read_file", READ),
        T("call_b", "act", chassis.UNKNOWN_CALL_OUTCOME),
        T("call_c", "write_file", "not run: the run ended in call call_b"),
    ]
    assert run.run_end()["reason"] == "interrupted"
    assert "may or may not" in chassis.UNKNOWN_CALL_OUTCOME and "not run" not in chassis.UNKNOWN_CALL_OUTCOME


# ---------------------------------------------------------------------------
# Every control exception reaches its owner, with every call answered once
# ---------------------------------------------------------------------------
CONTROL = [
    ("raise chassis.EnvironmentFailure('gone')", 44, "environment", "the call raised EnvironmentFailure: gone; the run ended"),
    ("raise chassis.DutyFault('broken')", 43, "duty_fault", "the call raised DutyFault: broken; the run ended"),
    ("raise chassis.TurnLimitReached('cap')", 42, "turn_limit", "the call raised TurnLimitReached: cap; the run ended"),
    ("raise chassis.WallLimitReached('clock')", 42, "wall_limit", "the call raised WallLimitReached: clock; the run ended"),
    ("raise chassis.PersistenceFailure('disk')", 44, "persistence_failure", "the call raised PersistenceFailure: disk; the run ended"),
    ("raise GeneratorExit()", 43, "run_traceback", "the call raised GeneratorExit; the run ended"),
    ("raise Odd('strange')", 43, "run_traceback", "the call raised Odd: strange; the run ended"),
    ("raise SystemExit(None)", 0, "exit_none", "the call raised SystemExit(None); the run ended"),
    ("raise SystemExit('bye')", 0, "exit_str", "the call raised SystemExit('bye'); the run ended"),
    ("raise SystemExit(300)", 300, "exit_300_without_termination_record", "the call raised SystemExit(300); the run ended"),
    ("raise SystemExit(-1)", -1, "exit_-1_without_termination_record", "the call raised SystemExit(-1); the run ended"),
    ("raise SystemExit(True)", 1, "exit_1_without_termination_record", "the call raised SystemExit(True); the run ended"),
    ("raise SystemExit([1])", 43, "invalid_exit_payload", "the call raised SystemExit([1]); the run ended"),
    ("context.finish('done')", 0, "finish", "finish accepted; run ending"),
]


@pytest.mark.parametrize(("statement", "code", "reason", "text"), CONTROL, ids=[c[2] + "-" + str(i) for i, c in enumerate(CONTROL)])
def test_every_control_exception_ends_the_run_with_every_call_answered(make_run, statement, code, reason, text):
    extra = (
        "class Odd(BaseException):\n    pass\n\n"
        f"def BEHAVIOUR(context, what):\n    {statement}\n"
    )
    run = make_run(
        [
            reply(
                calls=[
                    ("call_a", "read_file", {"path": "x"}),
                    ("call_x", "act", {"what": "end"}),
                    ("call_c", "write_file", {"path": "y", "text": "z"}),
                ]
            )
        ],
        extra=extra,
    )
    assert run.go() == code
    how = "by finish " if reason == "finish" else ""
    assert run.after_first_assistant() == [
        T("call_a", "read_file", READ),
        T("call_x", "act", text),
        T("call_c", "write_file", f"not run: the run ended {how}in call call_x"),
    ]
    assert run.duty.INVOKED == ["read_file", "act"], "a later call was invoked"
    assert run.run_end()["reason"] == reason and run.meta()["ended"]["reason"] == reason
    assert paired(run.chassis.messages) and run.saved() == run.chassis.messages


def test_an_ordinary_tool_exception_is_still_the_models_text(make_run):
    extra = "def BEHAVIOUR(context, what):\n    raise ValueError('boom')\n"
    run = make_run([reply(calls=[("call_b", "act", {"what": "x"})]), reply("ok")], extra=extra)
    assert run.go() == chassis.EXIT_OK
    assert run.after_first_assistant()[0] == T("call_b", "act", "error: ValueError: boom")


# ---------------------------------------------------------------------------
# Direct ends from main
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("main", "code", "reason"),
    [
        ("    context.handoff('direct note')\n", 42, "handoff"),
        ("    context.finish('all done')\n", 0, "finish"),
        ("    context.finish()\n", 0, "finish"),
        ("    raise SystemExit(42)\n", 42, "exit_42_without_termination_record"),
        ("    raise SystemExit(['bad'])\n", 43, "invalid_exit_payload"),
        ("    context.ask('one')\n", 0, "main_returned"),
    ],
)
def test_direct_ends_from_main_are_typed(make_run, main, code, reason):
    run = make_run([reply("fine")], main=main)
    assert run.go() == code
    assert run.run_end()["reason"] == reason
    ended = run.meta()["ended"]
    assert (ended["exit"], ended["reason"], ended["run"]) == (code, reason, run.chassis.run_id)


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------
def test_queued_messages_keep_their_order_and_the_seventeenth_is_refused(make_run):
    extra = (
        "def BEHAVIOUR(context, what):\n"
        "    for index in range(17):\n"
        "        (context.say if index % 2 else context.note)(f'q{index}')\n"
        "    return 'queued'\n"
    )
    run = make_run([reply(calls=[("call_q", "act", {"what": "q"})]), reply("done")], extra=extra)
    run.go()
    after = run.after_first_assistant()
    assert after[0]["content"].startswith("error: ValueError: at most 16 messages")
    queued = after[1:17]
    assert [m["content"] for m in queued] == [f"q{i}" for i in range(16)]
    assert [m["role"] for m in queued] == ["system" if i % 2 == 0 else "user" for i in range(16)]
    assert "q16" not in json.dumps(run.chassis.messages), "the refused message was not added anywhere"


@pytest.mark.parametrize(
    ("text", "accepted"),
    [
        ("x" * 65536, True),
        ("x" * 65537, False),
        ("é" * 10922, True),  # 65,532 escaped units
        ("é" * 10923, False),  # 65,538 escaped units, though only 21,846 UTF-8 bytes
        ("\x00" * 10923, False),
    ],
    ids=["ascii-at-cap", "ascii-over", "bmp-at-cap", "bmp-over", "controls-over"],
)
def test_a_queued_message_is_measured_in_escaped_units(make_run, text, accepted):
    extra = f"TEXT = {text!r}\n\ndef BEHAVIOUR(context, what):\n    context.say(TEXT)\n    return 'queued'\n"
    run = make_run([reply(calls=[("call_q", "act", {"what": "q"})]), reply("done")], extra=extra)
    run.go()
    after = run.after_first_assistant()
    if accepted:
        assert after[0]["content"] == "queued" and after[1] == {"role": "user", "content": text}
    else:
        assert after[0]["content"].startswith("error: ValueError: a message queued during a tool call is at most 65536")
        assert after[1] == {"role": "user", "content": "again"}, (
            "nothing was appended for the refused message: next is the duty's own second ask"
        )


def test_a_message_queued_before_a_handoff_is_flushed_after_the_group(make_run):
    extra = "def BEHAVIOUR(context, what):\n    context.say('before leaving')\n    context.handoff('bye')\n"
    run = make_run(
        [reply(calls=[("call_x", "act", {"what": "x"}), ("call_c", "write_file", {"path": "y", "text": "z"})])],
        extra=extra,
    )
    assert run.go() == 42
    assert run.after_first_assistant() == [
        T("call_x", "act", "handoff accepted; run ending"),
        T("call_c", "write_file", "not run: the run ended by handoff in call call_x"),
        {"role": "user", "content": "before leaving"},
    ]
    assert run.saved() == run.chassis.messages


def test_say_and_note_outside_a_group_append_at_once(make_run):
    main = "    context.say('direct')\n    context.note('a fact')\n    context.ask('go')\n"
    run = make_run([reply("ok")], main=main)
    run.go()
    contents = [m.get("content") for m in run.chassis.messages]
    assert contents.index("direct") < contents.index("a fact") < contents.index("go")


# ---------------------------------------------------------------------------
# Persistence failures are not hidden successes
# ---------------------------------------------------------------------------
def test_a_failed_final_checkpoint_becomes_persistence_failure(make_run, monkeypatch):
    run = make_run([reply("ok")], main="    context.finish('done')\n")

    def broken(_messages):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(run.chassis.carried, "save_conversation", broken)
    assert run.go() == chassis.EXIT_ENVIRONMENT
    assert run.run_end()["reason"] == "persistence_failure"
    assert [r for r in run.lifecycle() if r["event"] == "checkpoint_failed"]


def test_a_failed_turn_checkpoint_ends_the_run_as_an_environment_failure(make_run, monkeypatch):
    run = make_run([reply("ok"), reply("again")])
    calls = {"n": 0}
    real = run.chassis.carried.save_conversation

    def flaky(messages):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(5, "Input/output error")
        return real(messages)

    monkeypatch.setattr(run.chassis.carried, "save_conversation", flaky)
    assert run.go() == chassis.EXIT_ENVIRONMENT
    assert run.run_end()["reason"] == "persistence_failure"
    assert len(run.client.sent) == 1, "no further turn after the failed checkpoint"


# ---------------------------------------------------------------------------
# SV019-B1-03: SystemExit(int n) -> n, as SV-013 2.2.4 says
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, (0, "exit_0_without_termination_record", "")),
        (42, (42, "exit_42_without_termination_record", "")),
        (300, (300, "exit_300_without_termination_record", "")),
        (-1, (-1, "exit_-1_without_termination_record", "")),
        (True, (1, "exit_1_without_termination_record", "")),
        (False, (0, "exit_0_without_termination_record", "")),
        (None, (0, "exit_none", "")),
        ("bye", (0, "exit_str", "bye")),
        (["x"], (43, "invalid_exit_payload", "SystemExit(['x'])")),
        (1.5, (43, "invalid_exit_payload", "SystemExit(1.5)")),
    ],
)
def test_an_integer_exit_is_passed_on_unchanged(code, expected):
    """No range is imposed: what the process status becomes is the shell's arithmetic, not a policy here."""
    assert chassis.classify_exit(code) == expected


# ---------------------------------------------------------------------------
# SV019-B1-01: what is queued is what was measured
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("count", "accepted"),
    [(10, True), (65536, True), (65537, False)],
    ids=["few-surrogates", "surrogates-at-cap", "surrogates-over-cap"],
)
def test_queued_text_is_stored_normalized_exactly_as_it_was_measured(make_run, count, accepted):
    extra = (
        f"TEXT = chr(0xD800) * {count} + 'ok'\n\n"
        "def BEHAVIOUR(context, what):\n    context.say(TEXT[: len(TEXT) - 2] if len(TEXT) > 100 else TEXT)\n"
        "    return 'queued'\n"
    )
    run = make_run([reply(calls=[("call_q", "act", {"what": "q"})]), reply("done")], extra=extra)
    run.go()
    after = run.after_first_assistant()
    expected = "?" * count + ("ok" if count <= 100 else "")
    if accepted:
        assert after[0] == T("call_q", "act", "queued") and after[1] == {"role": "user", "content": expected}
        assert chassis.escaped_units(after[1]["content"]) <= chassis.MAX_QUEUED_UNITS
        assert after[2] == {"role": "user", "content": "again"}, "queue order kept"
    else:
        assert after[0]["content"].startswith("error: ValueError: a message queued during a tool call is at most 65536")
        assert after[1] == {"role": "user", "content": "again"}, "refused, not truncated or dropped silently"
    for messages in (run.chassis.messages, run.saved(), *run.client.sent):
        assert not any(0xD800 <= ord(ch) <= 0xDFFF for m in messages for ch in str(m.get("content", ""))), (
            "an unnormalized surrogate was retained"
        )


# ---------------------------------------------------------------------------
# SV019-B1-02: the runtime launched as a script, as the supervisor launches it
# ---------------------------------------------------------------------------
SCRIPT_DUTY = '''
import json, os, sys
{runtime}
tools = chassis.ToolRegistry()
CONTEXT = None
INVOKED = []


def _note(name):
    INVOKED.append(name)
    path = os.environ["TRACE_FILE"]
    with open(path, "w") as handle:
        json.dump({{
            "invoked": INVOKED,
            "same_module": sys.modules["chassis"] is sys.modules.get("__main__"),
        }}, handle)


@tools.register
def read_file(path: str) -> str:
    """Read."""
    _note("read_file")
    return "x-contents"


@tools.register
def write_file(path: str, text: str) -> str:
    """Write."""
    _note("write_file")
    return "wrote"


@tools.register
def act(what: str) -> str:
    """Act."""
    _note("act")
{act}


def main(context):
    global CONTEXT
    CONTEXT = context
    _note("main")
{main}
'''

IMPORT_RUNTIME = "import chassis"
SEED_RUNTIME = (
    "existing = sys.modules.get('chassis')\n"
    "assert existing is not None and hasattr(existing, 'Chassis'), 'no loaded runtime'\n"
    "chassis = existing"
)


def script_run(duty_runtime: str, act: str, main: str, replies) -> dict:
    """Run `python3 services/chassis.py` in a temporary world against the local stub model."""
    import shutil  # noqa: PLC0415 -- this harness only
    import subprocess  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    from stub_model import Stub, StubServer  # noqa: PLC0415 -- the local stub, on conftest's path

    root = Path(tempfile.mkdtemp(prefix="sv19-", dir="/tmp"))  # short: a unix socket path is capped
    try:
        for name in ("work", "home", "telemetry", "diary", "diode"):
            (root / name).mkdir()
        (root / "work" / "duty.py").write_text(
            SCRIPT_DUTY.format(runtime=duty_runtime, act=act, main=main), encoding="utf-8"
        )
        server = StubServer(Stub(script=replies), socket_path=root / "model.sock").start()
        env = dict(os.environ)
        for name in ("RUN_MAX_TURNS", "RUN_MAX_SECONDS", "CONTEXT_WINDOW_EVICTION_TOKENS", "AGENT_ENTRY"):
            env.pop(name, None)
        env.update(
            {
                "SERVICES_DIR": str(PROJECT / "services"),
                "AGENT_SLUG": "agent_s",
                "AGENT_NAME": "script",
                "WORK_DIR": str(root / "work"),
                "AGENT_HOME": str(root / "home"),
                "DIARY_DIR": str(root / "diary"),
                "DIODE_DUTY_DIR": str(root / "diode"),
                "TELEMETRY_DIR": str(root / "telemetry"),
                "LLM_SOCKET_PATH": str(root / "model.sock"),
                "LLM_BASE_URL": "http://localhost/v1",
                "LLM_MODEL": "stub",
                "OPENROUTER_API_KEY": "sk-dummy",
                "SOCKET_WAIT_SECONDS": "5",
                "RECORDER_TIMEOUT_SECONDS": "30",
                "CONTEXT_WINDOW_TOKENS": "200000",
                "TRACE_FILE": str(root / "trace.json"),
            }
        )
        try:
            done = subprocess.run(
                [sys.executable, str(PROJECT / "services" / "chassis.py")],
                cwd=str(root / "work"),
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
            )
        finally:
            server.stop()
        lifecycle = root / "telemetry" / "agents" / "agent_s" / "lifecycle.jsonl"
        records = [json.loads(line) for line in lifecycle.read_text().splitlines() if line] if lifecycle.exists() else []
        conversation = root / "home" / "session" / "conversation.json"
        return {
            "code": done.returncode,
            "output": done.stdout[-3000:] + done.stderr[-3000:],
            "run_end": next((r for r in records if r["event"] == "run_end"), None),
            "messages": json.loads(conversation.read_text()) if conversation.exists() else [],
            "trace": json.loads((root / "trace.json").read_text()) if (root / "trace.json").exists() else {},
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def three_calls():
    from stub_model import Reply, ToolCall  # noqa: PLC0415

    return [
        Reply(
            tool_calls=[
                ToolCall("read_file", {"path": "x"}),
                ToolCall("act", {"what": "end"}),
                ToolCall("write_file", {"path": "y", "text": "z"}),
            ]
        )
    ]


SCRIPT_CASES = [
    ("raise chassis.EnvironmentFailure('gone')", 44, "environment", "the call raised EnvironmentFailure: gone; the run ended", ""),
    ("raise chassis.TurnLimitReached('cap')", 42, "turn_limit", "the call raised TurnLimitReached: cap; the run ended", ""),
    ("raise chassis.DutyFault('broken')", 43, "duty_fault", "the call raised DutyFault: broken; the run ended", ""),
    ("raise chassis.RunTermination('handoff')", 42, "handoff", "handoff accepted; run ending", "by handoff "),
    ("CONTEXT.finish('done')", 0, "finish", "finish accepted; run ending", "by finish "),
    ("raise SystemExit(300)", 300 & 0xFF, "exit_300_without_termination_record", "the call raised SystemExit(300); the run ended", ""),
    ("raise SystemExit(-1)", (-1) & 0xFF, "exit_-1_without_termination_record", "the call raised SystemExit(-1); the run ended", ""),
]


@pytest.mark.parametrize("runtime", [IMPORT_RUNTIME, SEED_RUNTIME], ids=["import-chassis", "seed-load-runtime"])
@pytest.mark.parametrize(
    ("act", "status", "reason", "text", "how"),
    SCRIPT_CASES,
    ids=[case[2] for case in SCRIPT_CASES],
)
def test_script_mode_controls_from_an_imported_runtime_reach_their_owner(runtime, act, status, reason, text, how):
    """SV019-B1-02: before the fix `import chassis` in a script-launched run was a second module."""
    result = script_run(runtime, f"    {act}", "    context.ask('go')\n", three_calls())
    assert result["trace"].get("same_module") is True, result["output"]
    assert result["code"] == status, result["output"]
    assert result["run_end"]["reason"] == reason, result["output"]
    tool_messages = [m for m in result["messages"] if m.get("role") == "tool"]
    assert [m["content"] for m in tool_messages] == [
        "x-contents",
        text,
        f"not run: the run ended {how}in call {tool_messages[1]['tool_call_id']}",
    ]
    assert result["trace"]["invoked"] == ["main", "read_file", "act"], "a later call was invoked"


def test_script_mode_a_swallowed_handoff_continues_and_ends_as_main_returned():
    from stub_model import Reply  # noqa: PLC0415

    main = "    try:\n        context.handoff('N')\n    except SystemExit:\n        pass\n    context.ask('go')\n"
    result = script_run(IMPORT_RUNTIME, "    return 'unused'", main, [Reply(text="fine")])
    assert result["code"] == 0, result["output"]
    assert result["run_end"]["reason"] == "main_returned"
    assert result["messages"][-1]["role"] == "assistant"
