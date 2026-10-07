"""The recorder's accounting, driven directly, on a clock the test owns.

Every expected value here is the SV-013 dossier's fixture table (section 3.4,
R-A1...R-A14 and R-K1/R-K2), its linearizations (section 3.3, L1...L5), and the
SV-015 v2 clock-order fixture O8-4 -- written down before this code existed, so
the numbers are the oracle and the code is what is being checked.

The fixture world: sockets A and B (and C where a third is needed), a request
limit of 3 per socket, 100 tokens per socket, 150 tokens across the fleet. The
monotonic clock reads `m`; the wall clock reads `36000 + m` unless a fixture
moves it, so `0 <= m < 3600` is accounting hour 10.

Interleavings are forced with barriers rather than hoped for with sleeps: a
test that passes because a scheduler happened to be kind proves nothing.
"""

from __future__ import annotations

import inspect
import json
import threading

import pytest
import recorder as recorder_module
from recorder import KNOWN, UNKNOWN, Admitted, Budget, Refused, Usage, refusal_message
from report import count_requests

RQ, TK, G = 3, 100, 150


class FakeClock:
    """Monotonic `m`, wall `36000 + m` unless `w` is set by the fixture."""

    def __init__(self, m: float = 0.0, w: float | None = None) -> None:
        self.m = m
        self._w = w

    def at(self, m: float, w: float | None = None) -> FakeClock:
        self.m, self._w = m, w
        return self

    def monotonic(self) -> float:
        return self.m

    def wall(self) -> float:
        return 36000 + self.m if self._w is None else self._w


def world(rq=RQ, tk=TK, g=G, sockets=("A", "B", "C"), **kwargs):
    clock = FakeClock()
    budget = Budget(g, clock, **kwargs)
    for slug in sockets:
        assert budget.register(slug, rq, tk)
    return budget, clock


def known(n: int) -> Usage:
    return Usage(KNOWN, n, {"total_tokens": n})


def counters(budget: Budget, slug: str = "A") -> tuple[int, int, int]:
    snap = budget.snapshot(slug)
    return snap["requests_used"], snap["tokens_used"], snap["global_used"]


def forwarded(budget: Budget, rid: str, slug: str, est: int) -> None:
    assert isinstance(budget.admit(rid, slug, est), Admitted)
    assert budget.begin_forward(rid) is True


# ---------------------------------------------------------------------------
# R-A1...R-A14: the API-level fixtures
# ---------------------------------------------------------------------------
def test_an_estimate_larger_than_the_limit_is_refused_even_in_an_empty_window():
    """R-A1. The old check answered "allowed" for any request into an empty window."""
    budget, _ = world()
    refused = budget.admit("b1-00000001", "A", 120)
    assert refused == Refused("estimate_exceeds_limit", None, TK, 120)
    assert counters(budget) == (0, 0, 0)
    assert "can never fit" in refusal_message(refused)


def test_admission_uses_current_effective_charges_not_historical_estimates():
    """R-A2. Sum of admitted estimates reaches 130 while the invariant holds at every admission."""
    budget, clock = world()
    forwarded(budget, "01", "A", 70)
    clock.at(1)
    closed = budget.close("01", known(40))
    assert closed.kind == "settled" and closed.charge == 40 and closed.usage_class == KNOWN
    assert closed.applied == ("socket_tokens", "global") and closed.late == ()
    assert counters(budget) == (1, 40, 40)

    clock.at(2)
    forwarded(budget, "02", "A", 60)
    assert counters(budget) == (2, 100, 100)
    clock.at(3)
    budget.close("02", known(60))
    assert counters(budget) == (2, 100, 100)

    clock.at(4)
    refused = budget.admit("03", "A", 1)
    assert refused.reason == "tokens" and refused.wait == int(3600 - (4 - 0)) + 1 == 3597


def test_two_admissions_racing_for_the_last_request_slot_admit_exactly_one():
    """R-A3 / L1. Behind a barrier, so both threads really are at the door together."""
    budget, clock = world()
    for rid, m in (("01", 0), ("02", 1)):
        clock.at(m)
        forwarded(budget, rid, "A", 1)
        budget.close(rid, known(1))
    clock.at(5)
    barrier = threading.Barrier(2)
    results: dict[str, object] = {}

    def admit(rid: str) -> None:
        barrier.wait()
        results[rid] = budget.admit(rid, "A", 1)

    threads = [threading.Thread(target=admit, args=(rid,)) for rid in ("03", "04")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    outcomes = sorted(results.values(), key=lambda r: isinstance(r, Refused))
    assert isinstance(outcomes[0], Admitted)
    assert outcomes[1] == Refused("requests", int(3600 - (5 - 0)) + 1, RQ)
    assert outcomes[1].wait == 3596
    assert counters(budget)[0] == 3


def test_two_sockets_racing_for_the_fleets_last_tokens_admit_exactly_one():
    """R-A4 / L2. The loser's own socket counters are untouched."""
    budget, clock = world()
    forwarded(budget, "b-1", "B", 60)
    forwarded(budget, "c-1", "C", 60)
    assert budget.snapshot("A")["global_used"] == 120
    clock.at(5)
    barrier = threading.Barrier(2)
    results: dict[str, object] = {}

    def admit(rid: str, slug: str) -> None:
        barrier.wait()
        results[slug] = budget.admit(rid, slug, 20)

    threads = [
        threading.Thread(target=admit, args=("a-2", "A")),
        threading.Thread(target=admit, args=("b-2", "B")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    winner = next(slug for slug, r in results.items() if isinstance(r, Admitted))
    loser = "B" if winner == "A" else "A"
    assert results[loser] == Refused("global", int(39600 - 36005) + 1, G, 20)
    assert results[loser].wait == 3596
    assert budget.snapshot("A")["global_used"] == 140
    loser_before = (1, 60) if loser == "B" else (0, 0)
    assert counters(budget, loser)[:2] == loser_before


def test_a_settlement_in_the_next_hour_corrects_the_hour_it_was_charged_to():
    """R-A5. The rolling entry is two seconds old and corrected; the global hour has turned."""
    budget, clock = world()
    clock.at(3599.0)
    forwarded(budget, "01", "A", 50)
    clock.at(3601.0)
    closed = budget.close("01", known(80))
    assert closed.applied == ("socket_tokens",)
    assert closed.late == ({"pool": "global", "hour": 10, "delta": 30},)
    snap = budget.snapshot("A")
    assert snap["tokens_used"] == 80
    assert (snap["global_bucket"], snap["global_used"]) == (11, 0)


def test_a_settlement_after_its_entry_left_the_window_is_reported_late_not_recharged():
    """R-A6. No other request moved the clock along: the close itself advances it."""
    budget, clock = world()
    forwarded(budget, "01", "A", 50)
    clock.at(3600.5)
    closed = budget.close("01", known(80))
    assert closed.applied == ()
    assert closed.late == (
        {"pool": "socket_tokens", "reason": "rolling_expired", "delta": 30},
        {"pool": "global", "hour": 10, "delta": 30},
    )
    snap = budget.snapshot("A")
    assert snap["tokens_used"] == 0
    assert (snap["global_bucket"], snap["global_used"]) == (11, 0)


def test_a_settlement_two_hours_later_still_knows_its_hour():
    """R-A7. The reservation carries its own hour; nothing was pruned out from under it."""
    budget, clock = world()
    forwarded(budget, "01", "A", 50)
    clock.at(7300)
    assert clock.wall() == 43300
    closed = budget.close("01", known(80))
    assert closed.late == (
        {"pool": "socket_tokens", "reason": "rolling_expired", "delta": 30},
        {"pool": "global", "hour": 10, "delta": 30},
    )
    snap = budget.snapshot("A")
    assert (snap["global_bucket"], snap["global_used"]) == (12, 0)


def test_a_second_close_changes_nothing_and_an_evicted_tombstone_is_unknown():
    """R-A8. There is no everlasting "already settled" promise beyond the tombstone bound."""
    budget, clock = world()
    forwarded(budget, "01", "A", 70)
    clock.at(1)
    budget.close("01", known(40))
    before = counters(budget)
    again = budget.close("01", known(1))
    assert again.kind == "already_final"
    assert again.final["state"] == "settled" and again.final["charge"] == 40
    assert counters(budget) == before
    assert budget.close("b1-99999999").kind == "unknown_rid"

    small, _ = world(max_tombstones=2)
    for rid in ("01", "02", "03"):
        forwarded(small, rid, "A", 1)
        small.close(rid, known(1))
    assert small.snapshot("A")["tombstones"] == 2
    assert small.close("01").kind == "unknown_rid"
    assert small.close("03").kind == "already_final"


def test_a_duplicate_request_id_is_refused_without_a_charge():
    """R-A9. A live reservation is never overwritten, and neither is a tombstone."""
    budget, _ = world()
    assert isinstance(budget.admit("01", "A", 10), Admitted)
    assert budget.admit("01", "A", 10) == Refused("duplicate_rid", None)
    assert counters(budget) == (1, 10, 10)
    budget.close("01")
    assert budget.admit("01", "A", 10) == Refused("duplicate_rid", None)
    assert counters(budget) == (0, 0, 0)


def test_cancelling_a_reservation_refunds_everything_and_forbids_sending():
    """R-A10. Nothing reached the provider, so the request itself is refunded too."""
    budget, _ = world()
    assert isinstance(budget.admit("01", "A", 30), Admitted)
    closed = budget.close("01")
    assert closed.kind == "cancelled" and closed.charge == 0
    assert counters(budget) == (0, 0, 0)
    assert budget.begin_forward("01") is False


def test_a_wall_clock_that_steps_back_keeps_the_accounting_hour():
    """R-A11. A reset here would hand a fresh hour to whoever moved the clock."""
    budget, clock = world()
    forwarded(budget, "b-1", "B", 60)
    forwarded(budget, "c-1", "C", 60)
    clock.at(10)
    forwarded(budget, "a-1", "A", 20)
    assert budget.snapshot("A")["global_used"] == 140
    clock.at(20, w=28820)
    refused = budget.admit("a-2", "A", 20)
    assert refused.reason == "global"
    assert refused.wait == int(39600 - 28820) + 1 == 10781
    assert refused.clock_regressed is True
    assert "behind the accounting hour" in refusal_message(refused)
    assert budget.snapshot("A")["global_bucket"] == 10


def test_an_estimate_larger_than_the_fleet_limit_can_never_fit():
    """R-A12. A "next available in N seconds" here would be a false promise."""
    budget, _ = world(tk=1000)
    refused = budget.admit("01", "A", 160)
    assert refused == Refused("estimate_exceeds_global_limit", None, G, 160)
    assert "can never fit" in refusal_message(refused)


def test_zero_closes_a_socket_pool_and_unlimits_the_fleet_pool():
    """R-A13. Both meanings of zero are kept exactly as they were."""
    closed, _ = world(rq=0)
    refused = closed.admit("01", "A", 1)
    assert refused == Refused("requests_closed", 0, 0)
    assert "next available in 0 second(s)" in refusal_message(refused)

    unlimited, _ = world(g=0, tk=10**7)
    assert isinstance(unlimited.admit("01", "A", 10**6), Admitted)


def test_a_forward_wall_jump_is_applied_before_any_check_and_shown_by_snapshot():
    """R-A14. The rolling windows run on monotonic time and do not care about the wall."""
    budget, clock = world()
    forwarded(budget, "01", "A", 100)
    assert budget.snapshot("A")["global_used"] == 100
    clock.at(10, w=43210)
    refused = budget.admit("02", "A", 1)
    assert refused.reason == "tokens" and refused.wait == int(3600 - 10) + 1 == 3591
    snap = budget.snapshot("A")
    assert (snap["global_bucket"], snap["global_used"]) == (12, 0)


# ---------------------------------------------------------------------------
# L3...L5: the remaining linearizations
# ---------------------------------------------------------------------------
def test_a_settlement_and_an_admission_have_exactly_two_possible_outcomes():
    """L3, both serial orders, then the race: the race must land on one of them."""
    def fresh():
        budget, _ = world()
        forwarded(budget, "01", "A", 70)
        return budget

    close_first = fresh()
    close_first.close("01", known(40))
    assert isinstance(close_first.admit("02", "A", 60), Admitted)
    assert counters(close_first)[1] == 100

    admit_first = fresh()
    assert admit_first.admit("02", "A", 60).reason == "tokens"
    admit_first.close("01", known(40))
    assert counters(admit_first)[1] == 40

    for _ in range(50):
        budget = fresh()
        barrier = threading.Barrier(2)
        results = {}

        def settle(budget=budget, barrier=barrier):
            barrier.wait()
            budget.close("01", known(40))

        def admit(budget=budget, barrier=barrier, results=results):
            barrier.wait()
            results["02"] = budget.admit("02", "A", 60)

        threads = [threading.Thread(target=settle), threading.Thread(target=admit)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        tokens = counters(budget)[1]
        if isinstance(results["02"], Admitted):
            assert tokens == 100
        else:
            assert results["02"].reason == "tokens" and tokens == 40


def test_forwarding_and_cancelling_one_reservation_cannot_both_win():
    """L4. Forwarded-and-settled, or cancelled-and-never-sent: nothing in between."""
    for _ in range(50):
        budget, _ = world()
        assert isinstance(budget.admit("01", "A", 30), Admitted)
        barrier = threading.Barrier(2)
        results = {}

        def forward(budget=budget, barrier=barrier, results=results):
            barrier.wait()
            results["forward"] = budget.begin_forward("01")

        def cancel(budget=budget, barrier=barrier, results=results):
            barrier.wait()
            results["close"] = budget.close("01")

        threads = [threading.Thread(target=forward), threading.Thread(target=cancel)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        if results["forward"]:
            assert results["close"].kind == "settled" and results["close"].charge == 30
            assert counters(budget) == (1, 30, 30)
        else:
            assert results["close"].kind == "cancelled"
            assert counters(budget) == (0, 0, 0)


def test_an_admitted_request_that_never_connected_is_refunded():
    """L5 at the API: the handler closes before begin_forward when connect fails."""
    budget, _ = world()
    assert isinstance(budget.admit("01", "A", 40), Admitted)
    assert budget.close("01", Usage(UNKNOWN)).kind == "cancelled"
    assert counters(budget) == (0, 0, 0)


# ---------------------------------------------------------------------------
# O8-4: the clocks are read under the lock, in lock order
# ---------------------------------------------------------------------------
class SequenceClock:
    """Returns 0, 1, 2... per monotonic read, and checks it is read under the lock."""

    def __init__(self) -> None:
        self.reads = 0
        self.budget: Budget | None = None
        self.unlocked_reads = 0
        self.override: float | None = None

    def monotonic(self) -> float:
        if self.budget is not None and not self.budget._lock.locked():
            self.unlocked_reads += 1
        if self.override is not None:
            return self.override
        value = float(self.reads)
        self.reads += 1
        return value

    def wall(self) -> float:
        return 36000.0


def test_the_budget_methods_take_no_caller_timestamps():
    """A caller cannot hand in a stale `now`: there is no parameter to hand it in through."""
    for name in ("admit", "begin_forward", "close", "snapshot"):
        parameters = inspect.signature(getattr(Budget, name)).parameters
        assert not {"now", "now_wall", "t"} & set(parameters), name


def test_the_first_caller_to_take_the_lock_reads_the_earlier_time():
    """O8-4. A arrives first and stalls; B locks first and so stamps first: deque [0, 1].

    The negative control is the contract this replaces: A computes `now = 0`
    before stalling, B stamps 1, and the deque becomes [1, 0] -- an expired
    entry hidden behind a live head that head-only pruning never reaches.
    """
    clock = SequenceClock()
    budget = Budget(G, clock)
    clock.budget = budget
    budget.register("A", RQ, TK)
    clock.reads = 0
    a_arrived, b_done = threading.Event(), threading.Event()
    results = {}

    def caller_a():
        a_arrived.set()
        b_done.wait(5)  # stalled after arriving, before taking the lock
        results["A"] = budget.admit("a", "A", 10)

    thread = threading.Thread(target=caller_a)
    thread.start()
    a_arrived.wait(5)
    results["B"] = budget.admit("b", "A", 10)
    b_done.set()
    thread.join(5)
    assert isinstance(results["A"], Admitted) and isinstance(results["B"], Admitted)
    clock.override = 0.0
    assert budget.snapshot("A")["token_times"] == [0.0, 1.0]
    assert clock.unlocked_reads == 0, "a clock was read outside the budget lock"

    clock.override = 3600.5
    snap = budget.snapshot("A")
    assert snap["token_times"] == [1.0], "the head expired first and only the head"
    assert snap["tokens_used"] == 10


# ---------------------------------------------------------------------------
# Waits, windows and live reservations
# ---------------------------------------------------------------------------
def test_the_rolling_window_still_counts_an_entry_exactly_one_hour_old():
    budget, clock = world(rq=1)
    forwarded(budget, "01", "A", 1)
    clock.at(3600.0)
    assert budget.admit("02", "A", 1).reason == "requests"
    clock.at(3600.001)
    assert isinstance(budget.admit("03", "A", 1), Admitted)


def test_a_token_wait_is_the_earliest_second_at_which_current_charges_fit():
    """Three 30-token entries, 50 more wanted: the second-oldest has to go, not just the first."""
    budget, clock = world(rq=10)
    for rid, m in (("01", 0), ("02", 10), ("03", 20)):
        clock.at(m)
        forwarded(budget, rid, "A", 30)
    clock.at(30)
    refused = budget.admit("04", "A", 50)
    assert refused.reason == "tokens" and refused.wait == int(3600 - (30 - 10)) + 1 == 3581
    clock.at(30 + refused.wait - 1)
    assert budget.admit("05", "A", 50).reason == "tokens"
    clock.at(30 + refused.wait)
    assert isinstance(budget.admit("06", "A", 50), Admitted)


def test_a_request_wait_is_exact_at_its_boundary():
    budget, clock = world(rq=1)
    forwarded(budget, "01", "A", 1)
    clock.at(4)
    refused = budget.admit("02", "A", 1)
    assert refused.wait == 3597
    clock.at(4 + refused.wait - 1)
    assert budget.admit("03", "A", 1).reason == "requests"
    clock.at(4 + refused.wait)
    assert isinstance(budget.admit("04", "A", 1), Admitted)


def test_a_forward_wall_jump_empties_the_fleet_hour():
    budget, clock = world(tk=1000)
    forwarded(budget, "01", "A", 140)
    assert budget.admit("02", "A", 20).reason == "global"
    clock.at(1, w=39600.0)
    assert isinstance(budget.admit("03", "A", 20), Admitted)
    assert budget.snapshot("A")["global_used"] == 20


def test_an_unknown_usage_keeps_the_estimate_and_an_overshoot_blocks_later_admissions():
    """Known replaces the estimate, unknown keeps it; overshoot is refusal, not a billed cap."""
    budget, clock = world()
    forwarded(budget, "01", "A", 40)
    closed = budget.close("01", Usage(UNKNOWN))
    assert closed.usage_class == UNKNOWN and closed.charge == 40
    forwarded(budget, "02", "A", 10)
    budget.close("02", known(500))
    assert counters(budget)[1] == 540, "the actual over the limit is recorded, not clipped"
    assert budget.admit("03", "A", 1).reason == "tokens"


def test_a_long_running_reservation_is_never_expired_to_make_room():
    """A request still running is still spending: only its handler ends it."""
    budget, clock = world(max_live=1)
    forwarded(budget, "01", "A", 10)
    clock.at(10_000)
    assert budget.snapshot("A")["live"] == 1
    assert budget.admit("02", "A", 1).reason == "inflight"
    closed = budget.close("01", known(10))
    assert closed.kind == "settled"
    assert budget.snapshot("A")["live"] == 0
    assert isinstance(budget.admit("03", "A", 1), Admitted)


def test_cancelling_a_middle_reservation_keeps_the_window_in_order():
    budget, clock = world(rq=10, tk=1000)
    for rid, m in (("01", 0), ("02", 1), ("03", 2)):
        clock.at(m)
        assert isinstance(budget.admit(rid, "A", 10 * (m + 1)), Admitted)
    budget.close("02")
    snap = budget.snapshot("A")
    assert snap["token_times"] == [0, 2]
    assert (snap["requests_used"], snap["tokens_used"]) == (2, 40)


def test_the_slug_count_is_bounded():
    budget = Budget(G, FakeClock(), max_slugs=2)
    assert budget.register("a", RQ, TK) and budget.register("b", RQ, TK)
    assert budget.register("a", RQ, TK), "re-registering a known slug is not a new slug"
    assert budget.register("c", RQ, TK) is False


def test_an_estimate_must_be_a_positive_whole_number():
    budget, _ = world()
    for bad in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            budget.admit("01", "A", bad)


def test_the_slug_pattern_accepts_the_rosters_names_and_nothing_path_shaped():
    pattern = recorder_module.SLUG_PATTERN
    for good in ("agent_1", "otter", "rain-cloud", "x" * 64):
        assert pattern.fullmatch(good)
    for bad in ("", "../x", "Otter", "a b", "x" * 65, "a/b", "a.sock"):
        assert not pattern.fullmatch(bad)


# ---------------------------------------------------------------------------
# R-0: the report counts requests by what was opened
# ---------------------------------------------------------------------------
def test_the_report_counts_opened_ids_not_half_the_lines():
    """R-K1. Pre-parse refusals write a `close` with no `open`."""
    events = [
        {"event": "close", "id": "a", "status": 404},
        {"event": "close", "id": "b", "status": 413},
        {"event": "open", "id": "c"},
        {"event": "close", "id": "c", "status": 200},
    ]
    assert len(events) // 2 == 2, "the negative control"
    assert count_requests(events) == 1


def test_the_report_ignores_boot_style_lines():
    """R-K2. Boot markers live in recorder.jsonl now; an old-style one is not a request."""
    events = [
        {"event": "recorder_start", "boot": "b1"},
        {"event": "recorder_start", "boot": "b2"},
        {"event": "close", "id": None, "status": 404},
    ]
    assert count_requests(events) == 0


def test_the_report_counts_an_unmatched_open_once_and_a_duplicate_id_once():
    events = [
        {"event": "open", "id": "x"},
        {"event": "open", "id": "x"},
        {"event": "close", "id": "x"},
        {"event": "open", "id": "died-in-flight"},
        {"event": "open", "id": 7},
        {"event": "open", "id": None},
        {"event": "open"},
    ]
    assert count_requests(events) == 2


def test_the_report_keeps_its_other_fields(tmp_path):
    import report  # noqa: PLC0415 -- the module under test, imported where used

    directory = tmp_path / "transcripts" / "otter"
    directory.mkdir(parents=True)
    lines = [
        {"event": "close", "id": "r1", "status": 429, "refusal": "rate limited: ..."},
        {"event": "open", "id": "r2"},
        {"event": "close", "id": "r2", "status": 200},
    ]
    (directory / "events.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in lines) + "{torn", encoding="utf-8"
    )
    (directory / "agent_life_transcript.jsonl").write_text('{"id":"r2"}\n', encoding="utf-8")
    metrics = report.agent_metrics(tmp_path, "otter")
    assert metrics["requests"] == 1
    assert metrics["turns"] == 1
    assert metrics["refusals"] == 1
    assert metrics["agent"] == "otter"
