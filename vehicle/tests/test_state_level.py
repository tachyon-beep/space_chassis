"""`plant.state_level` on a node several states share reads a state by its own key only.

The node key of a shared node is a keyed state's container (`_stage_element` writes
`values[node][state.id]`), so a fallback to it handed a sibling's value to a state with none of its
own: `load_shed_class` read `{"load_enabled": {...}}` after one `set_load`, back when it had no
rule. It has one now (the crew's switches, read against MET 0), so it reads its own value.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402


@pytest.fixture(scope="module")
def world() -> plant.World:
    return plant.load_world(VEHICLE)


def by_id(world: plant.World) -> dict[str, plant.State]:
    return {state.id: state for state in world.states}


def test_a_shared_state_with_no_value_of_its_own_reads_none_not_its_sibling_s(world):
    states = by_id(world)
    values = plant.initial_values(world)
    effect = plant.Effect(0, "set_load", {"load": "csm_lighting", "state": "off"})
    after = plant.step(
        world, values, plant.tick_seconds(world), [], [effect], ledger=plant.Ledger()
    )
    # The container is there, holding the keyed sibling...
    assert after["load_shed_state"]["load_enabled"]["csm_lighting"] == "off"
    # ...and the sibling reads its own map, while the class reads its own value, not the map.
    assert plant.state_level(after, states["load_enabled"])["csm_lighting"] == "off"
    assert plant.state_level(after, states["load_shed_class"]) == "P3"
    # A state on a shared node with no value of its own reads none rather than the container.
    del after["load_shed_class"]
    assert plant.state_level(after, states["load_shed_class"]) is None


def test_the_world_marks_exactly_the_states_on_crowded_nodes(world):
    for state in world.states:
        alone = state.node == "internal" or len(world.states_on(state.node)) == 1
        assert state.shared is not alone, state.id
    assert by_id(world)["load_shed_class"].shared


def test_a_state_alone_on_its_node_still_reads_the_node_key():
    state = plant.State(id="x", domain="d", node="n", method="lag", unit="K", spec={})
    assert plant.state_level({"n": 3.0}, state) == 3.0
    assert plant.state_level({"n": 3.0, "x": 4.0}, state) == 4.0
