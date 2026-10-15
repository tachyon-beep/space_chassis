"""Spend accounting, ported from the SV workstream's budget properties against the port's classes.

A ticket settles once. A settle whose reservation already left the hour is reported as late and
not recharged; after compaction it is unknown. Two admissions racing for the last unit admit exactly
one, in threads and across processes. A request that never reached the upstream is cancelled,
count and all. And the declared pools keep an in-flight reservation when the clock hour turns
(John's decision 4), while a charge made outside any reservation ages out with its hour.
"""

import multiprocessing
import threading

import core_caps
import recorder_streams


class _Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_two_threads_racing_for_the_last_request_slot_admit_exactly_one():
    for _ in range(20):
        caps = core_caps.CoreCaps(request_allowance=3, token_allowance=10**12)
        for _ in range(2):
            assert caps.admit(b"{}")[0] is None
        barrier = threading.Barrier(2)
        results = []

        def race(caps=caps, barrier=barrier, results=results):
            barrier.wait()
            results.append(caps.admit(b"{}")[0])

        threads = [threading.Thread(target=race) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sorted(r is None for r in results) == [False, True]


def _reserve_in_a_process(path, barrier, queue):
    ledger = core_caps.FleetLedger(path, "racer", 100)
    barrier.wait()
    refused, _ticket = ledger.reserve(10)
    queue.put(refused is None)


def test_two_processes_racing_for_the_fleets_last_tokens_admit_exactly_one(tmp_path):
    context = multiprocessing.get_context("fork")
    for attempt in range(5):
        path = str(tmp_path / f"ledger-{attempt}.jsonl")
        assert core_caps.FleetLedger(path, "first", 100).reserve(90)[0] is None
        barrier, queue = context.Barrier(2), context.Queue()
        processes = [
            context.Process(target=_reserve_in_a_process, args=(path, barrier, queue))
            for _ in range(2)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(30)
        assert sorted(queue.get(timeout=5) for _ in range(2)) == [False, True]


def test_a_settlement_and_an_admission_have_exactly_two_possible_outcomes(tmp_path):
    for attempt in range(20):
        ledger = core_caps.FleetLedger(str(tmp_path / f"l-{attempt}.jsonl"), "a", 100)
        _, held = ledger.reserve(50)
        barrier = threading.Barrier(2)
        outcome = {}

        def settle(ledger=ledger, held=held, barrier=barrier):
            barrier.wait()
            ledger.settle(held, 0)

        def admit(ledger=ledger, barrier=barrier, outcome=outcome):
            barrier.wait()
            outcome["admitted"] = ledger.reserve(60)[0] is None

        threads = [threading.Thread(target=settle), threading.Thread(target=admit)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert ledger.used() == (60 if outcome["admitted"] else 0)


def test_a_second_settle_changes_nothing(tmp_path):
    caps = core_caps.CoreCaps(request_allowance=10, token_allowance=10**9)
    _, ticket = caps.admit(b"{}")
    assert caps.settle(ticket, 5) == "settled"
    assert caps.settle(ticket, 9) == "already_settled"
    assert caps.used()["tokens"] == 5

    ledger = core_caps.FleetLedger(str(tmp_path / "ledger.jsonl"), "a", 10**9)
    _, fleet_ticket = ledger.reserve(50)
    assert ledger.settle(fleet_ticket, 5) == "settled"
    assert ledger.settle(fleet_ticket, 9) == "already_settled"
    assert ledger.used() == 5


def test_a_settle_after_its_ticket_left_the_window_is_reported_late_not_recharged(tmp_path):
    clock = _Clock(0.0)
    caps = core_caps.CoreCaps(request_allowance=10, token_allowance=10**9, clock=clock)
    _, ticket = caps.admit(b"{}")
    reserved = caps.used()["tokens"]
    clock.now = core_caps.BUDGET_WINDOW + 1
    assert caps.settle(ticket, 5) == {"late": 5 - reserved}
    assert caps.used()["tokens"] == 0

    ledger = core_caps.FleetLedger(str(tmp_path / "ledger.jsonl"), "a", 10**9, clock=clock)
    clock.now = 0.0
    _, fleet_ticket = ledger.reserve(50)
    clock.now = core_caps.BUDGET_WINDOW + 1
    assert ledger.settle(fleet_ticket, 5) == {"late": -45}
    assert ledger.used() == 0


def test_a_settle_after_compaction_is_unknown_not_recharged(tmp_path):
    clock = _Clock(0.0)
    ledger = core_caps.FleetLedger(str(tmp_path / "ledger.jsonl"), "a", 10**9, clock=clock)
    _, old = ledger.reserve(50)
    clock.now = core_caps.BUDGET_WINDOW + 1
    ledger.reserve(1)  # an expired line makes the ledger compact
    assert ledger.settle(old, 5) == "unknown"
    assert ledger.used() == 1


def test_cancel_refunds_the_reservation_and_the_request_count():
    caps = core_caps.CoreCaps(request_allowance=10, token_allowance=10**9)
    _, ticket = caps.admit(b"{}")
    caps.cancel(ticket)
    assert caps.used() == {"requests": 0, "tokens": 0}

    registry = recorder_streams.StreamRegistry()
    registry.apply({"aux": {"budget": 5, "max_tokens": 10}}, {})
    _, refusal, stream_ticket = registry.admit("aux", b'{"model": "m", "messages": []}')
    assert refusal is None
    registry.cancel("aux", stream_ticket)
    state = registry.state(streams_enabled=True)
    assert state["streams"]["aux"]["budget"]["used"] == 0
    assert state["streams"]["aux"]["tokens"]["used"] == 0
    assert state["shared_tokens"]["used"] == 0


def test_a_declared_pool_keeps_an_in_flight_reservation_across_the_hour():
    clock = _Clock(recorder_streams.BUDGET_WINDOW - 1)
    registry = recorder_streams.StreamRegistry(clock=clock)
    registry.apply({"aux": {"budget": 5, "max_tokens": 10}}, {})
    _, refusal, ticket = registry.admit("aux", b'{"model": "m", "messages": []}')
    assert refusal is None
    held = registry.state(streams_enabled=True)["shared_tokens"]["used"]
    assert held > 0
    clock.now = recorder_streams.BUDGET_WINDOW + 1
    assert registry.state(streams_enabled=True)["shared_tokens"]["used"] == held
    registry.settle("aux", ticket, 7)
    assert registry.state(streams_enabled=True)["shared_tokens"]["used"] == 7


def test_a_charged_entry_is_not_carried_across_the_hour():
    clock = _Clock(recorder_streams.BUDGET_WINDOW - 1)
    registry = recorder_streams.StreamRegistry(clock=clock)
    registry.apply({"aux": {"budget": 5}}, {})
    registry.charge("aux", 500)
    assert registry.state(streams_enabled=True)["shared_tokens"]["used"] == 500
    clock.now = recorder_streams.BUDGET_WINDOW + 1
    assert registry.state(streams_enabled=True)["shared_tokens"]["used"] == 0


def test_a_finished_request_with_unknown_usage_is_not_carried_into_the_next_hour():
    """The security review of e70434f: unknown usage left an entry in flight forever, carried into
    every new hour, so broken streams could exhaust the shared pool for good."""
    clock = _Clock(recorder_streams.BUDGET_WINDOW - 1)
    registry = recorder_streams.StreamRegistry(clock=clock)
    registry.apply({"aux": {"budget": 50, "max_tokens": 10}}, {})
    _, refusal, ticket = registry.admit("aux", b'{"model": "m", "messages": []}')
    assert refusal is None
    registry.settle("aux", ticket, None)
    clock.now = recorder_streams.BUDGET_WINDOW + 1
    assert registry.state(streams_enabled=True)["shared_tokens"]["used"] == 0


def test_an_in_flight_reservation_is_carried_one_hour_and_no_further():
    clock = _Clock(recorder_streams.BUDGET_WINDOW - 1)
    registry = recorder_streams.StreamRegistry(clock=clock)
    registry.apply({"aux": {"budget": 50, "max_tokens": 10}}, {})
    _, refusal, _ticket = registry.admit("aux", b'{"model": "m", "messages": []}')
    assert refusal is None
    clock.now = recorder_streams.BUDGET_WINDOW + 1
    assert registry.state(streams_enabled=True)["shared_tokens"]["used"] > 0
    clock.now = 2 * recorder_streams.BUDGET_WINDOW + 1
    assert registry.state(streams_enabled=True)["shared_tokens"]["used"] == 0
