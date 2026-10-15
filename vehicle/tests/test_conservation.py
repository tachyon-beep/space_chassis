"""WP10: the ledger, and `assert_conservation` with an exact integer residual (`plant.md` §4, §9).

Two kinds of world. **The vehicle**, whose ready stocks drain across the conservation boundary
(`o2_csm_kg` into the fuel cell's draw, the cabin gases into removal) — so the assertion executes on
real, non-zero transfers every run. And **a fixture world** built in the test, because the vehicle
has no transfer between two stocks yet (`E-PRESS-PROP` is its only stock-to-stock edge and owes its
value): two tanks joined by a rate edge, one of them also draining to a sink. Every number in the
fixture is arbitrary and chosen to be recognisable; none is a claim about the vehicle.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402

DT = 0.02


def two_tanks() -> tuple[plant.World, dict]:
    """Tank A (10 kg) feeds tank B (2 kg) at 0.05/s of A's mass, and leaks to a sink at 2 mg/s."""
    a = plant.State(
        id="a_kg",
        domain="fixture",
        node="tank_a",
        method="stock",
        unit="kg",
        spec={"quantum": 1e-6, "initial": 10.0},
    )
    b = plant.State(
        id="b_kg",
        domain="fixture",
        node="tank_b",
        method="stock",
        unit="kg",
        spec={"quantum": 1e-6, "initial": 2.0},
    )
    feed = plant.Edge(
        id="E-A-B",
        source="tank_a",
        target="tank_b",
        kind="rate",
        sensitivity={"value": 0.05, "unit": "kg/s per kg"},
        reads="a_kg",
    )
    leak = plant.Edge(
        id="E-A-SINK",
        source="tank_a",
        target="sink",
        kind="rate",
        sensitivity={"value": 2e-6, "unit": "kg/s per W"},
    )
    world = plant.World(
        root=VEHICLE,
        states=[a, b],
        edges=[feed, leak],
        back_edges=set(),
        schedule=["tank_a", "tank_b"],
        nodes={
            "tank_a": {"kind": "stock", "domain": "fixture", "unit": "kg", "preloaded": "fixture"},
            "tank_b": {"kind": "stock", "domain": "fixture", "unit": "kg"},
            "sink": {"kind": "sink", "domain": "fixture", "unit": "W"},
        },
        channels={},
        frame_fields=[],
        verbs={},
    )
    return world, {"a_kg": 10.0, "tank_a": 10.0, "b_kg": 2.0, "tank_b": 2.0, "sink": 1.0}


def run(world: plant.World, values: dict, ticks: int) -> tuple[dict, list[plant.Ledger]]:
    ledgers = []
    for _ in range(ticks):
        ledger = plant.Ledger()
        values = plant.step(world, values, DT, [], ledger=ledger)
        ledgers.append(ledger)
    return values, ledgers


def test_the_vehicle_s_own_ticks_execute_the_assertion_on_moving_transfers():
    world = plant.load_world(VEHICLE)
    values, ledgers = run(world, plant.initial_values(world), 60)
    moving = [ledger for ledger in ledgers if ledger.moved()]
    assert moving, "no tick of the vehicle moved a stock, so the assertion never had work to do"
    for ledger in moving:
        assert plant.assert_conservation(ledger, nontrivial=True) > 0
    edges = {t.edge for ledger in moving for t in ledger.transfers if t.quanta}
    assert "E-O2-DRAW" in edges, edges

    # And across the run: the oxygen tank's count is its MET-0 count less every quantum booked out.
    o2 = next(s for s in world.states if s.id == "o2_csm_kg")
    numerator, denominator = plant.stock_quantum(o2, "o2")
    start = round(279.0 * denominator / numerator)
    out = sum(t.quanta for ledger in ledgers for t in ledger.transfers if t.source == "o2_csm_kg")
    assert out > 0
    assert round(values["o2_csm_kg"] * denominator / numerator) == start - out


def test_a_transfer_between_two_stocks_is_one_integer_at_both_ends():
    world, values = two_tanks()
    values, ledgers = run(world, values, 100)
    for ledger in ledgers:
        # Two records: the feed, booked once and held at both ends, and the leak to the sink.
        assert plant.assert_conservation(ledger, nontrivial=True) == 2
        feed = next(t for t in ledger.transfers if t.edge == "E-A-B")
        assert (feed.source, feed.target) == ("a_kg", "b_kg") and feed.quanta > 0
    # Closure over the run, exactly, in micrograms: what the pair lost is what the sink took.
    leaked = sum(t.quanta for ledger in ledgers for t in ledger.transfers if t.edge == "E-A-SINK")
    held = round(values["a_kg"] * 1e6) + round(values["b_kg"] * 1e6)
    assert held == 12_000_000 - leaked
    # 2 µg/s for 2 s is 4 µg; the accumulator may hold the last one back by a float's width.
    assert leaked in (3, 4), leaked
    assert 0.0 < values["b_kg"] - 2.0 < 10.0 - values["a_kg"]


def test_a_deliberately_leaking_transfer_fails_the_assertion(monkeypatch):
    """The target books one quantum more than its source sent: the vehicle gains a microgram."""

    class Leaky(dict):
        def get(self, key, default=None):
            sent = super().get(key, default)
            return None if sent is None else dataclasses.replace(sent, quanta=sent.quanta + 1)

    original = plant.Ledger.begin_segment

    def begin_segment(self):
        original(self)
        self.posted = Leaky()

    monkeypatch.setattr(plant.Ledger, "begin_segment", begin_segment)
    world, values = two_tanks()
    with pytest.raises(plant.ConservationError, match="b_kg: moved .* residual 1 of 1/1000000 kg"):
        plant.step(world, values, DT)


def test_a_ledger_that_moved_nothing_is_refused_as_vacuous():
    with pytest.raises(plant.ConservationError, match="vacuously"):
        plant.assert_conservation(plant.Ledger(), nontrivial=True)
    world, values = two_tanks()
    still = {**values, "a_kg": 0.0, "tank_a": 0.0, "sink": 0.0}
    ledger = plant.Ledger()
    plant.step(world, still, DT, ledger=ledger)
    assert ledger.transfers and not ledger.moved()
    assert plant.assert_conservation(ledger) == len(ledger.transfers)
    with pytest.raises(plant.ConservationError, match="vacuously"):
        plant.assert_conservation(ledger, nontrivial=True)


def test_the_published_level_and_its_ledger_are_one_pair():
    world, values = two_tanks()
    ledger = plant.Ledger()
    after = plant.step(world, values, DT, ledger=ledger)
    assert ledger.observed == {"a_kg": after["a_kg"], "b_kg": after["b_kg"]}
    record = ledger.as_record()
    assert {row["stock"] for row in record["stocks"]} == {"a_kg", "b_kg"}
    ledger.observed["b_kg"] += 1e-6
    with pytest.raises(plant.ConservationError, match="the observation and its ledger disagree"):
        plant.assert_conservation(ledger)


def test_one_end_of_a_transfer_alone_is_refused():
    world, values = two_tanks()
    ledger = plant.Ledger()
    plant.step(world, values, DT, ledger=ledger)
    ledger.lines = [line for line in ledger.lines if line.stock != "b_kg"]
    with pytest.raises(plant.ConservationError, match="one end of a transfer moved"):
        plant.assert_conservation(ledger)


def test_a_drain_past_empty_records_a_shortfall_and_still_balances():
    world, values = two_tanks()
    nearly = {**values, "a_kg": 3e-6, "tank_a": 3e-6, "sink": 1e4}  # asks 400 µg/tick, holds 3
    ledger = plant.Ledger()
    after = plant.step(world, nearly, DT, ledger=ledger)
    assert after["a_kg"] == 0.0
    leak = next(t for t in ledger.transfers if t.edge == "E-A-SINK")
    assert leak.quanta == 3 and leak.shortfall > 0
    assert after["a_kg__shortfall"] == pytest.approx(leak.shortfall * 1e-6)
    assert plant.assert_conservation(ledger, nontrivial=True) == 2


def test_a_target_that_cannot_advance_still_receives_what_was_sent():
    """Tank B's own flows are a gap; the microgram A sent it must land anyway, or the gap leaks."""
    world, values = two_tanks()
    world.edges.append(
        plant.Edge(
            id="E-X-B",
            source="nowhere",
            target="tank_b",
            kind="rate",
            sensitivity={"value": "UNCONFIGURED", "unit": "kg/s per W"},
        )
    )
    gaps: list[plant.Gap] = []
    ledger = plant.Ledger()
    after = plant.step(world, values, DT, gaps, ledger=ledger)
    assert [g.state.id for g in gaps] == ["b_kg"]
    feed = next(t for t in ledger.transfers if t.edge == "E-A-B")
    assert round(after["b_kg"] * 1e6) == 2_000_000 + feed.quanta
    plant.assert_conservation(ledger, nontrivial=True)


def test_energy_is_a_trend_inside_a_declared_band_and_never_raises():
    battery = plant.State(
        id="cell_j",
        domain="fixture",
        node="cell",
        method="stock",
        unit="J",
        spec={"quantum": 0.1, "initial": 1000.0},
    )
    load = plant.Edge(
        id="E-CELL-LOAD",
        source="cell",
        target="load",
        kind="rate",
        sensitivity={"value": 1.0, "unit": "J/s per W"},
    )
    world = plant.World(
        root=VEHICLE,
        states=[battery],
        edges=[load],
        back_edges=set(),
        schedule=["cell"],
        nodes={
            "cell": {"kind": "stock", "domain": "fixture", "unit": "J", "preloaded": "fixture"},
            "load": {"kind": "sink", "domain": "fixture", "unit": "W"},
        },
        channels={},
        frame_fields=[],
        verbs={},
    )
    _, ledgers = run(world, {"cell_j": 1000.0, "cell": 1000.0, "load": 50.0}, 50)
    trend = plant.energy_trend(ledgers, band_j=(-0.5, 0.0))
    assert trend["cell_j"]["ticks"] == 50
    assert trend["cell_j"]["net"] == pytest.approx(-50.0)
    assert trend["cell_j"]["outside_band"] == 50  # 1 J a tick is outside a 0.5 J band: reported
