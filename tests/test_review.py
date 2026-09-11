"""The review panel: what an operator can read, and what it must not do.

The panel's whole value is that it shows the record faithfully and cannot touch
it, so these tests are about two things: that a turn is reassembled correctly
from two consecutive requests, and that no code path here writes anything.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))

import review  # noqa: E402


# ---------------------------------------------------------------------------
# A synthetic record
# ---------------------------------------------------------------------------
def assistant(text="", calls=None, reasoning="", finish="stop") -> dict:
    message: dict = {"role": "assistant", "content": text or None}
    if reasoning:
        message["reasoning_content"] = reasoning
    if calls:
        message["tool_calls"] = [
            {
                "id": call.get("id", f"call_{index}"),
                "type": "function",
                "function": {"name": call["name"], "arguments": call.get("arguments", "{}")},
            }
            for index, call in enumerate(calls)
        ]
    return {"role": "assistant", "message": message, "finish": finish}


def turn_record(
    index: int,
    messages: list[dict],
    *,
    response_message: dict | None = None,
    response_text: str = "",
    reasoning: str = "",
    calls: list[dict] | None = None,
    finish: str = "stop",
    status: int = 200,
    usage: dict | None = None,
    agent: str = "otter",
) -> dict:
    message = response_message or assistant(response_text, calls, reasoning, finish)["message"]
    return {
        "at": f"2026-09-12T00:00:{index:02d}Z",
        "agent": agent,
        "id": f"req{index}",
        "status": status,
        "request": {"model": "stub", "messages": messages, "tools": [{"type": "function"}]},
        "response": {
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": usage or {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        },
    }


def write_transcript(
    root: Path, slug: str, records: list[dict], events: list[dict] | None = None
) -> Path:
    directory = root / "transcripts" / slug
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "agent_life_transcript.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    if events is not None:
        (directory / "events.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
        )
    return path


@pytest.fixture
def panel(tmp_path, monkeypatch):
    """The panel pointed at a temporary record."""
    root = tmp_path / "record"
    (root / "transcripts").mkdir(parents=True)
    (root / "telemetry" / "agents").mkdir(parents=True)
    (root / "home").mkdir(parents=True)
    (root / "pump").mkdir(parents=True)
    (root / "work").mkdir(parents=True)
    monkeypatch.setattr(review, "TRANSCRIPTS_DIR", root / "transcripts")
    monkeypatch.setattr(review, "TELEMETRY_DIR", root / "telemetry")
    monkeypatch.setattr(review, "HOME_ROOT", root / "home")
    monkeypatch.setattr(review, "PUMP_ROOT", root / "pump")
    monkeypatch.setattr(review, "WORK_DIR", root / "work")
    monkeypatch.setattr(review, "MAX_BYTES", 1 << 20)
    monkeypatch.setattr(review, "CACHE_TURNS", 50)
    monkeypatch.setattr(review, "CONVERSATIONS", {})
    return root


# ---------------------------------------------------------------------------
# Reassembling one turn
# ---------------------------------------------------------------------------
def test_a_turn_shows_only_what_was_new_in_it(panel):
    """Every request repeats the whole conversation; the panel shows the delta.

    This is the central reconstruction. Turn 1 carried two messages, turn 2
    carried four, so turn 2's new material is the last two -- and the panel
    must not re-show the opening the operator already read.
    """
    opening = [{"role": "system", "content": "you are"}, {"role": "user", "content": "go"}]
    second = opening + [
        {"role": "assistant", "content": "looking"},
        {"role": "user", "content": "again"},
    ]
    write_transcript(
        panel,
        "otter",
        [
            turn_record(0, opening, response_text="looking"),
            turn_record(1, second, response_text="still looking"),
        ],
        events=[
            {"at": "x", "event": "open", "id": "req0", "messages": 2},
            {"at": "x", "event": "close", "id": "req0", "status": 200, "duration_seconds": 0.5},
            {"at": "x", "event": "open", "id": "req1", "messages": 4},
            {"at": "x", "event": "close", "id": "req1", "status": 200, "duration_seconds": 0.9},
        ],
    )
    view = review.conversation("otter").refresh(force=True)
    assert len(view.turns) == 2

    first, latest = view.turns[0], view.turns[1]
    assert latest["response_text"] == "still looking"
    assert latest["duration_seconds"] == 0.9
    assert latest["context_messages"] == 4
    new_texts = [m["text"] for m in latest["new_messages"]]
    assert new_texts == ["looking", "again"], new_texts
    assert first["delta_known"] is False, "the oldest turn cannot be separated from its history"


def test_a_tool_call_carries_the_result_that_came_back(panel):
    """A tool's output is not in the turn that called it.

    It arrives as a `role: "tool"` message in the *next* request. A panel that
    showed the call without the result would show an operator the question and
    not the answer, which is the least useful half.
    """
    opening = [{"role": "user", "content": "go"}]
    after_call = opening + [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "function": {"name": "status", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "name": "status", "content": "12 turns lived"},
        {"role": "user", "content": "next"},
    ]
    write_transcript(
        panel,
        "otter",
        [
            turn_record(0, opening, calls=[{"id": "c1", "name": "status"}], finish="tool_calls"),
            turn_record(1, after_call, response_text="understood"),
        ],
        events=[
            {"event": "open", "id": "req0", "messages": 1},
            {"event": "open", "id": "req1", "messages": 4},
        ],
    )
    view = review.conversation("otter").refresh(force=True)
    call = view.turns[0]["tool_calls"][0]
    assert call["name"] == "status"
    assert call["result"]["display"] == "12 turns lived"
    assert call["result"]["chars"] == len("12 turns lived")


def test_a_result_is_matched_by_id_even_when_the_order_is_wrong(panel):
    """Two calls in one turn must not swap their answers."""
    opening = [{"role": "user", "content": "go"}]
    after = opening + [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "a", "function": {"name": "read_file", "arguments": "{}"}},
                {"id": "b", "function": {"name": "list_dir", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "b", "name": "list_dir", "content": "the directory"},
        {"role": "tool", "tool_call_id": "a", "name": "read_file", "content": "the file"},
    ]
    write_transcript(
        panel,
        "otter",
        [
            turn_record(
                0,
                opening,
                calls=[{"id": "a", "name": "read_file"}, {"id": "b", "name": "list_dir"}],
                finish="tool_calls",
            ),
            turn_record(1, after, response_text="done"),
        ],
        events=[{"event": "open", "id": "req0", "messages": 1}],
    )
    calls = review.conversation("otter").refresh(force=True).turns[0]["tool_calls"]
    by_name = {call["name"]: call["result"]["display"] for call in calls}
    assert by_name == {"read_file": "the file", "list_dir": "the directory"}


def test_reasoning_is_read_under_either_field_name(panel):
    """Providers differ; the panel is not loyal to one spelling."""
    for field in ("reasoning_content", "reasoning"):
        message = {"role": "assistant", "content": "answer", field: "because"}
        assert review.reasoning_text(message) == "because"
    assert review.reasoning_text({"role": "assistant", "content": "answer"}) == ""


def test_malformed_tool_arguments_are_kept_as_written(panel):
    """A model emitting bad JSON is the most interesting turn, not a lost one."""
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "c", "function": {"name": "run", "arguments": "{not json"}},
        ],
    }
    calls = review.extract_calls(message, "")
    assert calls[0]["arguments"] == "{not json"
    assert calls[0]["arguments_raw"] is True
    assert calls[0]["arguments_error"], "the parse error should be reported, not hidden"
    assert "{not json" in calls[0]["arguments_display"]


def test_a_multimodal_message_is_shown_rather_than_blanked(panel):
    """Content that is a list of parts must not render as an empty turn."""
    assert review.message_text({"content": [{"text": "one"}, {"text": "two"}]}) == "one\ntwo"
    assert review.message_text({"content": [{"type": "image"}]}) == "[image]"
    assert review.message_text({"content": None}) == ""


def test_a_refused_turn_is_shown_with_its_refusal(panel):
    """An operator's first question is usually whether the agent is working."""
    write_transcript(
        panel,
        "otter",
        [turn_record(0, [{"role": "user", "content": "go"}], status=429, response_message={})],
        events=[
            {"event": "open", "id": "req0", "messages": 1},
            {
                "event": "close",
                "id": "req0",
                "status": 429,
                "refusal": "rate limited: at most 2400 request(s) per hour",
            },
        ],
    )
    turn = review.conversation("otter").refresh(force=True).turns[0]
    assert turn["status"] == 429
    assert "rate limited" in (turn["refusal"] or "")


# ---------------------------------------------------------------------------
# Reading a file that grows without bound
# ---------------------------------------------------------------------------
def test_a_partial_final_line_is_not_a_turn(tmp_path):
    """A file being appended to while it is read ends mid-line; that is normal.

    Parsing it hopefully would invent a turn with a truncated body, which an
    operator would read as a corrupt record rather than as a race.
    """
    path = tmp_path / "t.jsonl"
    whole = [json.dumps({"n": n}) for n in range(4)]
    path.write_text("\n".join(whole) + "\n" + '{"n": 4, "half', encoding="utf-8")
    records, _more, _count = review.tail_jsonl(path, max_bytes=1 << 20, max_records=100)
    assert [r.get("n") for r in records] == [0, 1, 2, 3]


def test_a_bad_line_is_reported_rather_than_dropped(tmp_path):
    """One corrupt line must not silently remove a turn from the record."""
    path = tmp_path / "t.jsonl"
    path.write_text('{"n": 0}\nnot json\n{"n": 2}\n', encoding="utf-8")
    records, _more, _count = review.tail_jsonl(path, max_bytes=1 << 20, max_records=100)
    assert len(records) == 3
    assert records[1].get("__unparseable__") is True
    assert records[2]["n"] == 2


def test_the_window_is_bytes_not_the_whole_file(tmp_path):
    """The panel must not read a hundred megabytes to show twenty turns."""
    path = tmp_path / "t.jsonl"
    with open(path, "w", encoding="utf-8") as handle:
        for n in range(2000):
            handle.write(json.dumps({"n": n, "pad": "x" * 2000}) + "\n")
    size = path.stat().st_size
    records, more, _count = review.tail_jsonl(path, max_bytes=64 * 1024, max_records=10)
    assert more is True, "a window that begins mid-file must say so"
    assert len(records) == 10
    assert records[-1]["n"] == 1999
    assert size > 4_000_000, "the fixture should be far larger than the window"


def test_a_turn_larger_than_the_window_is_not_loaded_rather_than_half_read(tmp_path):
    """A half-parsed turn is worse than an honest absence."""
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps({"n": 0, "pad": "x" * 100_000}) + "\n", encoding="utf-8")
    records, _more, _count = review.tail_jsonl(path, max_bytes=1024, max_records=10)
    assert records == [], "an oversized record should yield nothing, not a fragment"


def test_the_cache_follows_the_file(panel, monkeypatch):
    """A refresh costs one stat while nothing changes, and re-reads when it does."""
    path = write_transcript(panel, "otter", [turn_record(0, [{"role": "user", "content": "go"}])])
    view = review.conversation("otter")
    view.refresh(force=True)
    assert len(view.turns) == 1

    parses: list[str] = []
    original = review.read_lines

    def spy(target, *args, **kwargs):
        parses.append(str(target))
        return original(target, *args, **kwargs)

    monkeypatch.setattr(review, "read_lines", spy)
    view.refresh()
    assert [p for p in parses if p.endswith("agent_life_transcript.jsonl")] == [], (
        "an unchanged file should not be re-parsed"
    )

    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(turn_record(1, [{"role": "user", "content": "again"}])) + "\n")
    view.refresh()
    transcripts = [p for p in parses if p.endswith("agent_life_transcript.jsonl")]
    assert len(transcripts) == 1, f"a changed file should be re-parsed once, not {len(transcripts)}"


def test_paging_walks_backwards_through_the_window(panel):
    records = [
        turn_record(n, [{"role": "user", "content": f"turn {n}"}], response_text=f"reply {n}")
        for n in range(10)
    ]
    write_transcript(panel, "otter", records)
    view = review.conversation("otter").refresh(force=True)
    newest, loaded = view.page(3, None)
    assert [t["index"] for t in newest] == [7, 8, 9]
    assert loaded == 10
    older, _ = view.page(3, before=7)
    assert [t["index"] for t in older] == [4, 5, 6]


# ---------------------------------------------------------------------------
# The fleet view
# ---------------------------------------------------------------------------
def test_the_fleet_view_reads_the_lifecycle_record(panel):
    """Failures and recoveries are half of what an operator needs."""
    slug = "otter"
    write_transcript(panel, slug, [turn_record(0, [{"role": "user", "content": "go"}])])
    telemetry = panel / "telemetry" / "agents" / slug
    telemetry.mkdir(parents=True, exist_ok=True)
    (telemetry / "lifecycle.jsonl").write_text(
        "\n".join(
            json.dumps(record)
            for record in (
                {"at": "x", "event": "run_start", "agent": slug},
                {
                    "at": "x",
                    "event": "decision",
                    "agent": slug,
                    "exit": 43,
                    "tier": 2,
                    "action": "restore_floor",
                },
                {"at": "x", "event": "handoff", "agent": slug},
                {"at": "x", "event": "run_end", "agent": slug, "exit": 42, "note": "handing over"},
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (panel / "home" / slug / "session").mkdir(parents=True, exist_ok=True)
    (panel / "home" / slug / "session" / "run.json").write_text(
        json.dumps({"turn": 7, "context_window": 1000, "context_tokens": 250, "model": "stub"}),
        encoding="utf-8",
    )
    (panel / "pump" / slug).mkdir(parents=True, exist_ok=True)
    (panel / "pump" / slug / "state.json").write_text(
        json.dumps({"entries": {"beat": {"running": True}}}), encoding="utf-8"
    )

    row = review.agent_row(slug)
    assert row["runs"] == 1
    assert row["last_exit"] == 42
    assert row["last_tier"] == 2
    assert row["handoffs"] == 1
    assert row["context_pressure"] == 0.25
    assert row["pump_running"] == ["beat"]
    assert review.pressure_label(row["context_pressure"]) == "25%"


def test_the_panel_finds_agents_without_being_told_them(panel):
    """Slugs are drawn at random, so a list in configuration would go stale."""
    write_transcript(panel, "mackerel", [turn_record(0, [{"role": "user", "content": "go"}])])
    (panel / "telemetry" / "agents" / "cinnabar").mkdir(parents=True, exist_ok=True)
    assert review.discover_slugs() == ["cinnabar", "mackerel"]


# ---------------------------------------------------------------------------
# It must not write
# ---------------------------------------------------------------------------
def test_no_path_in_the_panel_opens_a_file_for_writing():
    """Read-only by construction, not by convention.

    The panel mounts the record read-only and the container's root filesystem
    read-only, but a future edit could still try to write and fail silently in
    production. This asserts it at the source level, in the spirit of the
    recorder's "no header is ever written" check.
    """
    source = (PROJECT / "services" / "review.py").read_text(encoding="utf-8")
    for hazard in (
        '"w"',
        "'w'",
        '"a"',
        "'a'",
        '"wb"',
        "'wb'",
        "write_text",
        "write_bytes",
        "mkdir",
    ):
        assert hazard not in source, f"the panel contains {hazard}, which is a write"
    assert "write_json_atomic" not in source, "the panel publishes nothing"
    assert "os.replace" not in source and "os.remove" not in source and "unlink" not in source


def test_the_panel_only_serves_the_routes_it_declares(panel):
    """An unknown route is a 404 with the route list, never a file read."""
    write_transcript(panel, "otter", [turn_record(0, [{"role": "user", "content": "go"}])])
    with serving() as base:
        with pytest.raises(urllib.error.HTTPError) as failure:
            fetch(f"{base}/etc/passwd")
        assert failure.value.code == 404
        assert b"no route" in failure.value.read()


# ---------------------------------------------------------------------------
# The server
# ---------------------------------------------------------------------------
def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class serving:
    """The panel's handler on a real socket, on an ephemeral port."""

    def __enter__(self) -> str:
        self.port = free_port()
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), review.Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}
        )
        self.thread.daemon = True
        self.thread.start()
        return f"http://127.0.0.1:{self.port}"

    def __exit__(self, *_exc) -> None:
        self.server.shutdown()
        self.server.server_close()


def fetch(url: str) -> tuple[int, bytes, dict]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.read(), dict(response.headers)


def test_the_routes_serve_html_and_json(panel):
    write_transcript(
        panel,
        "otter",
        [
            turn_record(
                0,
                [{"role": "user", "content": "go"}],
                response_text="thinking",
                reasoning="because the window is nearly full",
                calls=[{"id": "c1", "name": "status"}],
                finish="tool_calls",
            ),
            turn_record(
                1,
                [
                    {"role": "user", "content": "go"},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {"id": "c1", "function": {"name": "status", "arguments": "{}"}}
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "c1",
                        "name": "status",
                        "content": "12 turns lived",
                    },
                ],
                response_text="now I know",
            ),
        ],
        events=[{"event": "open", "id": "req0", "messages": 1}],
    )

    with serving() as base:
        status, body, headers = fetch(f"{base}/")
        assert status == 200 and headers["Content-Length"] == str(len(body))
        assert b"otter" in body and b"Read-only" in body

        status, body, _ = fetch(f"{base}/agent/otter")
        assert status == 200
        assert b"thought" in body, "reasoning should be labelled"
        assert b"because the window is nearly full" in body
        assert b"12 turns lived" in body, "the tool result should be shown"
        assert b"tool call" in body

        status, body, headers = fetch(f"{base}/api/agent/otter")
        payload = json.loads(body)
        # Oldest first, because a reader starts at the beginning of a
        # conversation, not at the end of it.
        assert [turn["index"] for turn in payload["turns"]] == [0, 1]
        first, second = payload["turns"]
        assert first["response_text"] == "thinking"
        assert first["reasoning"].startswith("because")
        assert first["tool_calls"][0]["result"]["display"] == "12 turns lived"
        assert second["response_text"] == "now I know"

        status, body, _ = fetch(f"{base}/api/fleet")
        fleet = json.loads(body)
        assert [row["slug"] for row in fleet["agents"]] == ["otter"]

        status, body, _ = fetch(f"{base}/api/agent/otter/turn/0/raw")
        raw = json.loads(body)
        assert raw["id"] == "req0"
        assert raw["request"]["messages"], "the raw record is untruncated"

        status, body, _ = fetch(f"{base}/health")
        assert json.loads(body)["ok"] is True


def test_an_unknown_agent_is_a_404_naming_the_record(panel):
    with serving() as base:
        with pytest.raises(urllib.error.HTTPError) as failure:
            fetch(f"{base}/agent/nobody")
        assert failure.value.code == 404
        assert b"no agent named nobody" in failure.value.read()


def test_the_panel_renders_what_a_real_run_produced(panel):
    """The strongest check available without Docker: drive the real stack.

    A chassis run through the real recorder writes a transcript this panel has
    never seen, in the shape a provider actually produced. If the panel can
    reassemble that, it can reassemble the real thing.
    """
    from conftest import Reply, Stack, ToolCall, World  # noqa: PLC0415

    world = World(panel.parent / "real-world")
    # Three turns, because a tool's *result* is carried by the request that
    # follows it: a run that stops after one call never records one, and a test
    # built on it would be checking the wrong thing entirely.
    script = [
        Reply(
            tool_calls=[ToolCall("status")],
            reasoning="I should look at my own numbers before deciding anything.",
        ),
        Reply(tool_calls=[ToolCall("write_diary", {"entry": "checked in"})]),
        Reply(text="Enough looking for now.", finish="stop", repeat=1000),
    ]
    with Stack(world, script=script) as stack:
        stack.run_chassis(timeout=60)

    import review as panel_module  # noqa: PLC0415 -- re-import is the same module

    original = {
        "TRANSCRIPTS_DIR": panel_module.TRANSCRIPTS_DIR,
        "TELEMETRY_DIR": panel_module.TELEMETRY_DIR,
    }
    panel_module.TRANSCRIPTS_DIR = world.transcripts
    panel_module.TELEMETRY_DIR = world.telemetry
    panel_module.CONVERSATIONS.clear()
    try:
        view = panel_module.conversation(world.slug).refresh(force=True)
        assert view.turns, "the panel found no turns in a transcript the real stack wrote"

        # Find the turns by what they did, not by their position: a supervisor
        # is free to restart a run, so a transcript can hold several runs and
        # the interesting turn is not always the first.
        def turn_with(tool: str) -> dict:
            for turn in view.turns:
                if any(call["name"] == tool for call in turn["tool_calls"]):
                    return turn
            raise AssertionError(f"no turn called {tool}: {[t['tool_calls'] for t in view.turns]}")

        status = turn_with("status")
        assert "I should look at my own numbers" in status["reasoning"], status
        called = next(call for call in status["tool_calls"] if call["name"] == "status")
        assert called.get("result"), "the tool result should be paired from the following request"
        assert "turn" in called["result"]["display"].lower() or "{" in called["result"]["display"]

        # A second tool, to show the pairing is not a special case for one name.
        written = next(
            call for call in turn_with("write_diary")["tool_calls"] if call["name"] == "write_diary"
        )
        assert written.get("result"), "the second tool's result was not paired"
        assert "appended" in written["result"]["display"], written["result"]
    finally:
        panel_module.TRANSCRIPTS_DIR = original["TRANSCRIPTS_DIR"]
        panel_module.TELEMETRY_DIR = original["TELEMETRY_DIR"]
        panel_module.CONVERSATIONS.clear()
