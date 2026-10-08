import json
import os
import pathlib
import subprocess
import sys
import threading

import core_caps
import pytest
from recorder_streams import estimate_prompt_tokens

RECORDER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def test_a_core_request_without_max_tokens_reserves_the_response_reserve():
    body = b'{"messages":[]}'
    caps = core_caps.CoreCaps(10, 10**9, clock=Clock())
    refused, _ = caps.admit(body)
    assert refused is None
    assert caps.used()["tokens"] == estimate_prompt_tokens(body) + 32768

    large = b'{"messages":[],"max_tokens":100000}'
    caps = core_caps.CoreCaps(10, 10**9, clock=Clock())
    caps.admit(large)
    assert caps.used()["tokens"] == estimate_prompt_tokens(large) + 100000


def test_the_per_agent_request_ceiling_refuses_the_next_request_in_the_hour():
    clock = Clock()
    caps = core_caps.CoreCaps(2, 10**9, clock=clock)
    assert caps.admit(b"{}")[0] is None
    assert caps.admit(b"{}")[0] is None
    refused, ticket = caps.admit(b"{}")
    assert refused[0] == 429
    assert "request(s) per hour" in refused[1]
    assert ticket is None
    clock.now += 3601
    assert caps.admit(b"{}")[0] is None


def test_the_per_agent_token_ceiling_counts_settled_usage():
    caps = core_caps.CoreCaps(10, 1000, clock=Clock())
    _, ticket = caps.admit(b"{}")
    caps.settle(ticket, 1000)
    refused, _ = caps.admit(b"{}")
    assert refused[0] == 429
    assert "token(s) per hour" in refused[1]


def test_a_settle_with_unknown_usage_keeps_the_reservation():
    body = b'{"messages":[]}'
    caps = core_caps.CoreCaps(10, 10**9, clock=Clock())
    _, ticket = caps.admit(body)
    caps.settle(ticket, None)
    assert caps.used()["tokens"] == estimate_prompt_tokens(body) + 32768


def test_a_local_refusal_writes_nothing_to_the_fleet_ledger(tmp_path):
    path = tmp_path / "ledger.jsonl"
    clock = Clock()
    ledger = core_caps.FleetLedger(str(path), "a", 10**12, clock=clock)
    caps = core_caps.CoreCaps(1, 10**9, ledger=ledger, clock=clock)
    assert caps.admit(b"{}")[0] is None
    lines = path.read_text().splitlines()
    refused, _ = caps.admit(b"{}")
    assert "request(s) per hour" in refused[1]
    assert path.read_text().splitlines() == lines


def test_the_fleet_ledger_refuses_when_the_fleet_has_spent_its_hour(tmp_path):
    path = str(tmp_path / "ledger.jsonl")
    clock = Clock()
    a = core_caps.FleetLedger(path, "a", 1000, clock=clock)
    b = core_caps.FleetLedger(path, "b", 1000, clock=clock)
    refused, ticket = a.reserve(600)
    assert refused is None
    refused, _ = b.reserve(600)
    assert refused[0] == 429
    assert "across the fleet" in refused[1]
    a.settle(ticket, 100)
    assert b.reserve(600)[0] is None


def test_core_caps_consult_the_fleet_ledger(tmp_path):
    path = str(tmp_path / "ledger.jsonl")
    clock = Clock()
    other = core_caps.FleetLedger(path, "other", 1000, clock=clock)
    other.reserve(1000)
    caps = core_caps.CoreCaps(
        10, 10**9, ledger=core_caps.FleetLedger(path, "a", 1000, clock=clock), clock=clock
    )
    refused, _ = caps.admit(b"{}")
    assert "across the fleet" in refused[1]
    assert caps.used() == {"requests": 0, "tokens": 0}


def test_a_settle_keeps_the_reservation_s_time(tmp_path):
    clock = Clock(0.0)
    ledger = core_caps.FleetLedger(str(tmp_path / "ledger.jsonl"), "a", 10**9, clock=clock)
    _, ticket = ledger.reserve(500)
    clock.now = 3000.0
    ledger.settle(ticket, 400)
    assert ledger.used() == 400
    clock.now = 3601.0
    assert ledger.used() == 0


def test_two_processes_reserving_concurrently_both_land_in_the_ledger(tmp_path):
    path = str(tmp_path / "ledger.jsonl")
    script = (
        "import sys; sys.path.insert(0, sys.argv[1]); import core_caps; "
        "ledger = core_caps.FleetLedger(sys.argv[2], sys.argv[3], 10**12); "
        "[ledger.reserve(1) for _ in range(50)]"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", script, RECORDER_DIR, path, name])
        for name in ("p1", "p2")
    ]
    assert [proc.wait(timeout=60) for proc in procs] == [0, 0]
    tickets = {json.loads(line)["ticket"] for line in pathlib.Path(path).read_text().splitlines()}
    assert len(tickets) == 100
    assert core_caps.FleetLedger(path, "reader", 10**12).used() == 100


def test_threads_in_one_process_reserving_concurrently_all_land(tmp_path):
    path = str(tmp_path / "ledger.jsonl")
    ledger = core_caps.FleetLedger(path, "a", 10**12)

    def work():
        for _ in range(25):
            ledger.reserve(1)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    tickets = {json.loads(line)["ticket"] for line in pathlib.Path(path).read_text().splitlines()}
    assert len(tickets) == 200
    assert ledger.used() == 200


def test_a_corrupt_ledger_line_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "ledger.jsonl"
    clock = Clock()
    valid = {"t": clock.now, "agent": "x", "ticket": "x:1", "tokens": 70}
    path.write_text("not json\n" + json.dumps(valid) + "\n")
    ledger = core_caps.FleetLedger(str(path), "a", 1000, clock=clock)
    assert ledger.used() == 70
    assert ledger.reserve(10)[0] is None


def test_the_ledger_compacts_expired_and_superseded_lines(tmp_path):
    path = tmp_path / "ledger.jsonl"
    clock = Clock()
    ledger = core_caps.FleetLedger(str(path), "a", 10**12, clock=clock)
    for _ in range(1100):
        _, ticket = ledger.reserve(5)
        ledger.settle(ticket, 3)
    clock.now += 3601
    ledger.reserve(5)
    assert len(path.read_text().splitlines()) == 1


def test_a_ledger_path_without_an_agent_slug_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEET_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    monkeypatch.delenv("AGENT_SLUG", raising=False)
    with pytest.raises(ValueError, match="AGENT_SLUG"):
        core_caps.caps_from_environment()
    monkeypatch.delenv("FLEET_LEDGER_PATH")
    caps, ledger = core_caps.caps_from_environment()
    assert ledger is None
    assert isinstance(caps, core_caps.CoreCaps)


def test_a_core_request_cannot_reserve_less_than_the_response_reserve():
    # The agent writes its own chassis, so the body's max_tokens is its claim; a duplicate key
    # can even differ between this parser and the upstream's. The reserve is a floor.
    for body in (b'{"max_tokens":1}', b'{"max_tokens":100000,"max_tokens":1}'):
        caps = core_caps.CoreCaps(10, 10**9, clock=Clock())
        caps.admit(body)
        assert caps.used()["tokens"] == estimate_prompt_tokens(body) + 32768, body


def test_an_unreachable_ledger_refuses_with_503_instead_of_raising(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.mkdir()
    refused, ticket = core_caps.FleetLedger(str(path), "a", 10**9).reserve(10)
    assert refused == (503, "fleet ledger unavailable")
    assert ticket is None


def test_a_ledger_whose_directory_cannot_be_made_still_constructs(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    ledger = core_caps.FleetLedger(str(blocker / "ledger.jsonl"), "a", 10**9)
    assert ledger.reserve(10)[0] == (503, "fleet ledger unavailable")


def test_a_settle_that_cannot_reach_the_ledger_keeps_the_reservation_and_returns(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = core_caps.FleetLedger(str(path), "a", 10**9)
    _, ticket = ledger.reserve(10)
    path.unlink()
    path.mkdir()
    ledger.settle(ticket, 3)
    path.rmdir()
