"""ECLSS's rules (D5, `domains/eclss/rules.py`), each against an independent analytic case.

Every expected figure is computed here from the published constant (the ECS study guide's 35 cfm
normal-space delivery, quoted in the state's `initial_provenance`) by a closed form rather than by
the rule's own step.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402

DT = 0.02
SUIT = next(
    s
    for s in yaml.safe_load((VEHICLE / "domains/eclss/components.yaml").read_text())["state"]
    if s["id"] == "suit_loop_flow_cfm"
)


@pytest.fixture(scope="module")
def world() -> plant.World:
    return plant.load_world(VEHICLE)


def walk(world, values, ticks):
    for _ in range(ticks):
        values = plant.step(world, values, DT, [], None, ledger=plant.Ledger())
    return values


def suit_flow(values):
    # Read as every reader does, by the state's own key first (`plant.state_level`): the sentinel's
    # sub-map entry is not what a frame publishes.
    return values["suit_loop_flow_cfm"]


def test_the_suit_loop_holds_the_published_delivery_while_its_compressor_runs(world):
    assert "35 cubic feet per minute" in SUIT["initial_provenance"]["source"]
    values = walk(world, plant.initial_values(world), 50)
    assert suit_flow(values) == pytest.approx(35.0)


def test_the_suit_loop_spins_down_with_its_time_constant_when_the_compressor_load_is_off(world):
    values = plant.initial_values(world)
    enabled = dict(values["load_enabled"])
    assert enabled[SUIT["compressor_load"]] == "on"
    enabled[SUIT["compressor_load"]] = "off"
    values = {**values, "load_enabled": enabled}
    ticks = 250  # 5 s, one time constant
    after = walk(world, values, ticks)
    expected = 35.0 * math.exp(-ticks * DT / SUIT["tau_s"])
    assert suit_flow(after) == pytest.approx(expected, rel=1e-6)
    # And it spins back up once the load is on again.
    enabled[SUIT["compressor_load"]] = "on"
    back = walk(world, {**after, "load_enabled": dict(enabled)}, ticks)
    recovered = 35.0 - (35.0 - expected) * math.exp(-ticks * DT / SUIT["tau_s"])
    assert suit_flow(back) == pytest.approx(recovered, rel=1e-6)


def test_the_suit_loop_advances_on_a_real_tick(world):
    gaps: list[plant.Gap] = []
    plant.step(world, plant.initial_values(world), DT, gaps)
    assert "suit_loop_flow_cfm" not in {gap.state.id for gap in gaps}
