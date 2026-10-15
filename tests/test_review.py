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
    error: str | None = None,
    usage: dict | None = None,
    stream: str = "core",
) -> dict:
    """A line in the shape recorder/proxy.py writes: timestamp, stream, request, response."""
    message = response_message or assistant(response_text, calls, reasoning, finish)["message"]
    response = (
        {"error": {"message": error}}
        if error is not None
        else {
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": usage or {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        }
    )
    return {
        "timestamp": f"2026-09-12T00:00:{index:02d}.000000Z",
        "stream": stream,
        "request": {"model": "stub", "messages": messages, "tools": [{"type": "function"}]},
        "response": response,
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
    monkeypatch.setattr(review, "TRANSCRIPTS_DIR", root / "transcripts")
    monkeypatch.setattr(review, "TELEMETRY_DIR", root / "telemetry")
    monkeypatch.setattr(review, "MIRROR_DIR", root / "telemetry" / "agents")
    monkeypatch.delenv("AGENT_SLUGS", raising=False)
    monkeypatch.setattr(review, "MAX_BYTES", 1 << 20)
    monkeypatch.setattr(review, "CACHE_TURNS", 50)
    monkeypatch.setattr(review, "CONVERSATIONS", {})
    return root


# ---------------------------------------------------------------------------
# Reassembling one turn
# ---------------------------------------------------------------------------
def test_a_turn_is_read_from_the_recorder_s_line_shape(panel):
    """Every request repeats the whole conversation; a turn shows what arrived since the last reply.

    The chassis condenses and clips what it sends, so one request is not a prefix of the next;
    what is new in a request is what follows its last assistant message.
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
    )
    view = review.conversation("otter").refresh(force=True)
    assert len(view.turns) == 2

    first, latest = view.turns[0], view.turns[1]
    assert latest["response_text"] == "still looking"
    assert latest["at"] == "2026-09-12T00:00:01.000000Z"
    assert latest["context_messages"] == 4
    assert [m["text"] for m in latest["new_messages"]] == ["again"]
    assert latest["usage"]["total_tokens"] == 12
    assert first["fresh"] is True and latest["fresh"] is False


def test_a_fresh_conversation_is_marked_as_a_new_incarnation(panel):
    opening = [{"role": "system", "content": "you are"}, {"role": "user", "content": "go"}]
    carried = opening + [{"role": "assistant", "content": "x"}, {"role": "user", "content": "y"}]
    write_transcript(
        panel,
        "otter",
        [
            turn_record(0, opening),
            turn_record(1, carried),
            turn_record(2, opening),
        ],
    )
    turns = review.conversation("otter").refresh(force=True).turns
    assert [turn["fresh"] for turn in turns] == [True, False, True]
    assert turns[0]["system_hash"] == turns[2]["system_hash"]


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


def test_a_refused_turn_shows_the_refusal_and_no_calls(panel):
    """An operator's first question is usually whether the agent is working."""
    cap = "rate limited: at most 2400 request(s) per hour on this socket"
    write_transcript(
        panel,
        "otter",
        [
            turn_record(0, [{"role": "user", "content": "go"}], error=cap),
            turn_record(1, [{"role": "user", "content": "go"}], error="upstream request failed"),
        ],
    )
    refused, failed = review.conversation("otter").refresh(force=True).turns
    assert refused["refused"] is True and refused["tool_calls"] == []
    assert "rate limited" in refused["error"]
    assert failed["refused"] is False and failed["error"] == "upstream request failed"
    html = review.render_turn(refused, "otter")
    assert "rate limited" in html


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
def test_the_fleet_view_reads_the_monitor_s_signals_and_labels_claims(panel):
    """Liveness and signals are the monitor's; the agent's notes are its claim and say so."""
    slug = "otter"
    write_transcript(panel, slug, [turn_record(0, [{"role": "user", "content": "go"}])])
    signals = {
        "incarnations": 3,
        "refusals": 2,
        "tool_errors": 1,
        "tool_results": 9,
        "spend": {"requests": 40, "tokens": 900, "refused": 2},
        "caps": {"requests": 2400, "tokens": 200000000},
    }
    (panel / "telemetry" / "fleet.json").write_text(
        json.dumps(
            {
                "at": "x",
                "agents": [{"slug": slug, "liveness": "capped", "signals": signals}],
                "summary": {"agents": 1, "capped": 1},
            }
        ),
        encoding="utf-8",
    )
    tombstones = panel / "telemetry" / "agents" / slug / "work" / "tombstones"
    tombstones.mkdir(parents=True)
    (tombstones / "recovery_note.txt").write_text("Recovery event 9: <b>restored</b>\n")

    row = review.agent_row(slug)
    assert row["liveness"] == "capped"
    assert row["signals"]["incarnations"] == 3
    assert row["claims"]["recovery_note"] == {
        "value": "Recovery event 9: <b>restored</b>",
        "claim": "agent",
    }
    page = review.render_fleet([row], review.fleet_summary([row])).decode()
    assert "capped" in page and "the agent&#x27;s own claim" in page
    assert "<b>restored</b>" not in page, "a claim is text, never markup"
    agent_page = review.render_agent(row, [], 25, None).decode()
    assert "Recovery event 9" in agent_page and "the agent&#x27;s own claim" in agent_page


def test_a_symlinked_note_in_the_mirror_is_not_followed(panel, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("operator secret\n")
    tombstones = panel / "telemetry" / "agents" / "otter" / "work" / "tombstones"
    tombstones.mkdir(parents=True)
    (tombstones / "recovery_note.txt").symlink_to(secret)
    write_transcript(panel, "otter", [turn_record(0, [{"role": "user", "content": "go"}])])
    assert review.agent_row("otter")["claims"]["recovery_note"]["value"] is None


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
        assert raw["timestamp"] == "2026-09-12T00:00:00.000000Z"
        assert raw["request"]["messages"], "the raw record is untruncated"

        status, body, _ = fetch(f"{base}/health")
        assert json.loads(body)["ok"] is True


def test_an_unknown_agent_is_a_404_naming_the_record(panel):
    with serving() as base:
        with pytest.raises(urllib.error.HTTPError) as failure:
            fetch(f"{base}/agent/nobody")
        assert failure.value.code == 404
        assert b"no agent named nobody" in failure.value.read()


FIXTURE = PROJECT / "tests" / "fixtures" / "aurora_transcript.jsonl"


def test_the_panel_renders_what_a_real_run_produced(panel):
    """The head of a transcript the real recorder wrote in a live smoke run, against the stub.

    The shape is the recorder's, not a builder's guess at it: if the panel reassembles this, it
    reassembles the real thing.
    """
    directory = panel / "transcripts" / "otter"
    directory.mkdir(parents=True)
    (directory / "agent_life_transcript.jsonl").write_bytes(FIXTURE.read_bytes())
    view = review.conversation("otter").refresh(force=True)
    assert len(view.turns) >= 5
    assert view.turns[0]["fresh"] is True
    called = [call for turn in view.turns for call in turn["tool_calls"]]
    assert called and all(call["name"] for call in called)
    assert any(call.get("result") for call in called), "a result pairs from the next request"
    for turn in view.turns:
        review.render_turn(turn, "otter")
    review.render_agent(review.agent_row("otter"), view.turns, 25, None)


def test_the_fixture_carries_no_key():
    assert b"sk-" not in FIXTURE.read_bytes()


def test_the_fleet_table_shows_the_cache_share(panel):
    slug = "otter"
    write_transcript(panel, slug, [turn_record(0, [{"role": "user", "content": "go"}])])

    def publish(spend: dict) -> str:
        signals = {"incarnations": 1, "spend": spend, "caps": {}}
        (panel / "telemetry" / "fleet.json").write_text(
            json.dumps(
                {"at": "x", "agents": [{"slug": slug, "liveness": "active", "signals": signals}]}
            ),
            encoding="utf-8",
        )
        row = review.agent_row(slug)
        return review.render_fleet([row], review.fleet_summary([row])).decode()

    page = publish({"requests": 3, "cache_share": 0.2})
    assert "<th>cache</th>" in page and "<td title='cache share'>20%</td>" in page
    # A snapshot published before the cache signals existed, or an hour with nothing prompted.
    assert "<td title='cache share'>—</td>" in publish({"requests": 3})
    assert "<td title='cache share'>—</td>" in publish({"requests": 3, "cache_share": None})
