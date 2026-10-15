"""live/stub_llm.py: Aurora's stub model, plus cues that make its next reply a chosen tool call.

The stub runs in a thread on an ephemeral loopback port. A cue is keyed by the requesting
client's address -- in the smoke stack, the recorder's -- so one is faked here by binding the
client socket to 127.0.0.2.
"""

import http.client
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "live"))

import stub_llm  # noqa: E402


@pytest.fixture
def stub(tmp_path, monkeypatch):
    monkeypatch.setattr(stub_llm, "REPLY_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(stub_llm, "TURNS_PER_INCARNATION", 3)
    monkeypatch.setattr(stub_llm, "CUE_DIR", str(tmp_path))
    monkeypatch.setattr(stub_llm, "_turns_by_client", {})
    monkeypatch.setattr(stub_llm, "_stop_owed", set())
    server = stub_llm.make_server("127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], tmp_path
    server.shutdown()
    server.server_close()


def _ask(port, source="127.0.0.1", path="/v1/chat/completions"):
    connection = http.client.HTTPConnection(
        "127.0.0.1", port, timeout=5, source_address=(source, 0)
    )
    connection.request("POST", path, body=json.dumps({"model": "m", "messages": []}))
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, (json.loads(body) if body else None)


def _message(reply):
    return reply["choices"][0]["message"]


def _cue(directory, client, payload):
    (directory / f"{client}.json").write_text(json.dumps(payload))


def test_without_a_cue_the_stub_lists_the_directory(stub):
    port, _ = stub
    status, reply = _ask(port)
    assert status == 200
    call = _message(reply)["tool_calls"][0]
    assert call["function"]["name"] == "list_dir"
    assert json.loads(call["function"]["arguments"]) == {"path": "."}


def test_every_nth_request_from_one_client_stops_the_incarnation(stub):
    port, _ = stub
    replies = [_ask(port)[1] for _ in range(3)]
    assert [r["choices"][0]["finish_reason"] for r in replies] == [
        "tool_calls",
        "tool_calls",
        "stop",
    ]
    assert "tool_calls" not in _message(replies[2])


def test_a_cue_is_served_once_as_the_named_tool_call(stub):
    port, cues = stub
    _cue(cues, "127.0.0.1", {"name": "run", "arguments": {"command": "git status"}})
    first = _message(_ask(port)[1])["tool_calls"][0]
    assert first["function"]["name"] == "run"
    assert isinstance(first["function"]["arguments"], str)
    assert json.loads(first["function"]["arguments"]) == {"command": "git status"}
    assert (cues / "127.0.0.1.json.served").exists()
    assert not (cues / "127.0.0.1.json").exists()
    second = _message(_ask(port)[1])["tool_calls"][0]
    assert second["function"]["name"] == "list_dir"


def test_a_cue_is_served_only_to_its_own_client(stub):
    port, cues = stub
    _cue(cues, "127.0.0.2", {"name": "done", "arguments": {"message": "x"}})
    other = _message(_ask(port, source="127.0.0.1")[1])["tool_calls"][0]
    assert other["function"]["name"] == "list_dir"
    own = _message(_ask(port, source="127.0.0.2")[1])["tool_calls"][0]
    assert own["function"]["name"] == "done"


def test_a_stop_cue_ends_the_incarnation(stub):
    port, cues = stub
    _cue(cues, "127.0.0.1", {"stop": True})
    reply = _ask(port)[1]
    assert reply["choices"][0]["finish_reason"] == "stop"


def test_a_cue_on_the_nth_turn_wins_and_the_stop_moves_to_the_next_request(stub):
    port, cues = stub
    _ask(port)
    _ask(port)
    _cue(cues, "127.0.0.1", {"name": "reset", "arguments": {}})
    third = _ask(port)[1]
    assert _message(third)["tool_calls"][0]["function"]["name"] == "reset"
    fourth = _ask(port)[1]
    assert fourth["choices"][0]["finish_reason"] == "stop"


def test_a_malformed_cue_is_a_500_and_set_aside(stub):
    port, cues = stub
    (cues / "127.0.0.1.json").write_text("{not json")
    status, _ = _ask(port)
    assert status == 500
    assert (cues / "127.0.0.1.json.bad").exists()
    assert _ask(port)[0] == 200


def test_a_get_is_the_readiness_probe(stub):
    port, _ = stub
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", "/")
    assert connection.getresponse().status == 200
    connection.close()


def test_any_other_path_is_not_found(stub):
    port, _ = stub
    assert _ask(port, path="/v1/embeddings")[0] == 404
