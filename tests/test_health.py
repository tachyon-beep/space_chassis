"""services/health.py: the operator's signals, from recorder-shaped lines alone.

The builders here make lines in the shape recorder/proxy.py writes: a transcript line is
{"timestamp", "stream", "request", "response"} and an event is {"timestamp", "event", "stream", ...}.
Nothing the agent writes is an input.
"""

import ast
import datetime as dt
from pathlib import Path

import health

T0 = dt.datetime(2026, 10, 9, 0, 0, 0, tzinfo=dt.UTC)
SYSTEM = {"role": "system", "content": "you are an agent"}
USER = {"role": "user", "content": "begin"}
CAP = "rate limited: at most 4 request(s) per hour on this socket; next available in 3554 seconds"


def at(seconds: float) -> str:
    return (T0 + dt.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def epoch(seconds: float) -> float:
    return (T0 + dt.timedelta(seconds=seconds)).timestamp()


def assistant(call_id: str = "c1", name: str = "list_dir") -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}
        ],
    }


def tool(call_id: str = "c1", content: str = "[file] agent.py") -> dict:
    return {"role": "tool", "tool_call_id": call_id, "name": "list_dir", "content": content}


def record(messages, *, stream="core", response=None, seconds=0.0) -> dict:
    line = {
        "timestamp": at(seconds),
        "request": {"model": "m", "messages": messages},
        "response": response if response is not None else {"choices": []},
    }
    if stream is not None:
        line["stream"] = stream
    return line


def error(message: str) -> dict:
    return {"error": {"message": message}}


def fresh(seconds=0.0, system=SYSTEM):
    return record([system, USER], seconds=seconds)


def later(turns: int, seconds=0.0, system=SYSTEM, results=None):
    messages = [system, USER]
    for n in range(turns):
        messages += [assistant(f"c{n}"), (results or {}).get(n, tool(f"c{n}"))]
    return record(messages, seconds=seconds)


def test_only_the_core_loop_counts_and_a_missing_stream_is_core():
    records = [fresh(), later(1, seconds=1), record([SYSTEM, USER], stream="vision")]
    unlabelled = later(2)
    del unlabelled["stream"]
    records.append(unlabelled)
    assert len(health.core_records(records)) == 3
    assert health.core_records([{"stream": "core", "request": "not a dict"}]) == []


def test_a_refused_request_is_a_refusal_not_a_request():
    records = [fresh(), later(1, seconds=1), record([SYSTEM, USER], response=error(CAP), seconds=2)]
    assert health.is_cap_refusal(records[2])
    result = health.signals(records, [], now=epoch(10), caps={}, output_dir=None)
    assert result["refusals"] == 1
    assert result["requests_per_incarnation"] == [2]


def test_an_upstream_error_is_an_error_not_a_cap():
    outage = record([SYSTEM, USER], response=error("upstream request failed"), seconds=1)
    assert health.is_error(outage)
    assert not health.is_cap_refusal(outage)
    result = health.signals([fresh(), outage], [], now=epoch(5), caps={}, output_dir=None)
    assert result["errors"] == 1
    assert result["refusals"] == 0
    for word in ("across the fleet", "fleet ledger unavailable"):
        assert health.is_cap_refusal(record([USER], response=error(f"x {word} y")))


def test_a_conversation_without_an_assistant_message_starts_an_incarnation():
    assert health.is_fresh_start([SYSTEM, USER])
    note = {"role": "user", "content": "Recovery event 1: started from the image seed at abc."}
    assert health.is_fresh_start([SYSTEM, USER, note])
    assert not health.is_fresh_start([SYSTEM, USER, assistant(), tool()])
    groups = health.incarnations([later(3), fresh(1), later(1, seconds=2), fresh(3)])
    assert [len(group) for group in groups] == [1, 2, 1]


def test_a_reset_that_keeps_the_conversation_is_not_a_boundary():
    records = [fresh(0), later(1, seconds=1), later(2, seconds=2), later(3, seconds=40)]
    result = health.signals(records, [], now=epoch(50), caps={}, output_dir=None)
    assert result["incarnations"] == 1
    assert result["resets"] == 0


def test_requests_are_counted_per_incarnation():
    records = [fresh(0), later(1, seconds=1), fresh(2), later(1, seconds=3), later(2, seconds=4)]
    result = health.signals(records, [], now=epoch(5), caps={}, output_dir=None)
    assert result["incarnations"] == 2
    assert result["requests_per_incarnation"] == [2, 3]
    assert result["resets"] == 1


def test_a_changed_system_prompt_is_counted_once_per_change():
    other = {"role": "system", "content": "you are a different agent"}
    listed = {"role": "system", "content": [{"type": "text", "text": "parts"}]}
    records = [fresh(0), later(1, seconds=1), fresh(2, other), later(1, 3, other), fresh(4, listed)]
    result = health.signals(records, [], now=epoch(5), caps={}, output_dir=None)
    assert result["system_prompt_changes"] == 2
    assert health.system_prompt_hash(records[0]["request"]) != health.system_prompt_hash(
        records[2]["request"]
    )
    assert health.system_prompt_hash({"messages": [USER]}) is None


def test_tool_errors_are_counted_from_the_new_results_only_never_twice():
    bad = tool("c0", "Error executing tool: boom")
    records = [
        fresh(0),
        later(1, seconds=1, results={0: bad}),
        later(2, seconds=2, results={0: bad}),
        later(3, seconds=3, results={0: bad, 2: tool("c2", "Error: Tool `x` is not registered.")}),
    ]
    assert health.new_tool_results(records[3]["request"]["messages"]) == [
        tool("c2", "Error: Tool `x` is not registered.")
    ]
    errors, results = health.tool_errors(records)
    assert (errors, results) == (2, 3)


def test_spend_sums_closes_inside_the_hour_and_counts_429_and_503_as_refused():
    def close(seconds, status, tokens=None, stream="core"):
        event = {"timestamp": at(seconds), "event": "close", "stream": stream, "status": status}
        if tokens is not None:
            event["usage"] = {"total_tokens": tokens}
        return event

    events = [
        close(0, 200, 1000),
        close(3700, 200, 10),
        close(3710, 429),
        close(3720, 503),
        close(3730, 200, 5, stream="vision"),
        {"timestamp": at(3740), "event": "open", "stream": "core"},
        close(3750, 200, 7),
    ]
    assert health.spend(events, now=epoch(3800)) == {"requests": 4, "tokens": 17, "refused": 2}


def test_vehicle_commands_are_counted_by_their_stamp_per_incarnation(tmp_path: Path):
    output = tmp_path / "output"
    output.mkdir()
    for name in (
        "20261009T000001_000000Z_agent_1_diode_set_mode_standby.txt",
        "20261009T000002_500000Z_agent_1_status.txt",
        "20261009T000030_000000Z_agent_1_status.txt",
        "not-a-result.txt",
        "20261009T000003_000000Z_agent_1_no_extension",
    ):
        (output / name).write_text("x")
    assert health.vehicle_commands(output, epoch(0), epoch(10)) == 2
    records = [fresh(0), later(1, seconds=5), fresh(20), later(1, seconds=40)]
    result = health.signals(records, [], now=epoch(60), caps={}, output_dir=output)
    assert result["vehicle_commands_per_incarnation"] == [2, 1]
    assert health.vehicle_commands(tmp_path / "missing", 0, 1) == 0


def test_a_timestamp_parses_with_and_without_its_fraction():
    assert health.parse_timestamp("2026-10-09T00:00:01.250000Z") == epoch(1.25)
    assert health.parse_timestamp("2026-10-09T00:00:01Z") == epoch(1)
    assert health.parse_timestamp("yesterday") is None
    assert health.parse_timestamp(None) is None


def test_liveness_reads_active_capped_idle_and_stale_from_the_two_clocks():
    quiet = 60
    assert health.liveness(5, 3, False, quiet) == "active"
    assert health.liveness(5, 3, True, quiet) == "capped"
    assert health.liveness(500, 3, False, quiet) == "idle-watchdog"
    assert health.liveness(None, 3, False, quiet) == "idle-watchdog"
    assert health.liveness(500, 500, False, quiet) == "stale"
    assert health.liveness(500, None, True, quiet) == "stale"
    assert health.liveness(None, None, False, quiet) == "unknown"


def test_signals_survive_an_empty_or_malformed_window():
    junk = [
        "not a dict",
        {"stream": "core", "request": "not a dict"},
        {"stream": "core", "request": {"messages": "not a list"}},
        {"stream": "core", "request": {"messages": [None, 3, {"role": "assistant"}]}},
        {"timestamp": "bad", "stream": "core", "request": {"messages": []}},
    ]
    for records in ([], junk):
        result = health.signals(
            records, ["junk", {"event": "close"}], now=0, caps={}, output_dir=None
        )
        assert result["spend"] == {"requests": 0, "tokens": 0, "refused": 0}
        assert isinstance(result["incarnations"], int)
    assert health.signals([], [], now=0, caps={"x": 1}, output_dir=None)["caps"] == {"x": 1}


def test_read_records_reads_the_bounded_tail(tmp_path: Path):
    path = tmp_path / "t.jsonl"
    path.write_text("".join(f'{{"n": {n}}}\n' for n in range(1000)))
    records = health.read_records(path, max_bytes=100)
    assert records and records[-1] == {"n": 999}
    assert len(records) < 1000
    assert health.read_records(tmp_path / "missing.jsonl") == []


def test_health_imports_nothing_outside_the_standard_library_and_common():
    import sys

    tree = ast.parse((Path(health.__file__)).read_text())
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        for name in names:
            assert name == "common" or name in sys.stdlib_module_names or name == "__future__", name
