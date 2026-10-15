"""Keyed-map discrete states: one position per element, moved by a command naming the element.

The quiet-coast episode (`docs/vehicle-completion/09-quiet-coast-episode.md` §7, steps 1–2) needs
`load_enabled` — a position per load id, moved by `set_load` — and the plant already carries that
shape: `breaker_panel` and `hatch_state` are keyed maps a command writes one element of
(`command_value.key`). This holds it for the state the episode adds, on a **fixture**: the state is
declared in a copy of `domains/power/components.yaml`, because its MET-0 positions are research the
power evidence worker owns (the Apollo checklist), and the two positions written here are arbitrary.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402

LOAD_ENABLED = """state:
  - id: load_enabled
    node: internal
    method: discrete
    unit: "map[load_id,enum[on,off]]"
    initial: {csm_lighting: "on", csm_comm_heaters: "on"}
    moved_by: ["command:set_load"]
    command_value:
      - verb: set_load
        argument: state
        key: load
"""

READS_IT = """
def bus_b_v(inputs, params, dt):
    return 30.0 if inputs["load_enabled"]["csm_lighting"] == "off" else 29.0


RULES = {"bus_b_v": bus_b_v}
"""


def definition(tmp_path: Path, rules: str | None = None) -> Path:
    root = tmp_path / "keyed"
    root.mkdir()
    for name in plant.CORPUS_TOP_LEVEL:
        shutil.copy(VEHICLE / name, root / name)
    shutil.copytree(VEHICLE / "domains", root / "domains")
    path = root / "domains" / "power" / "components.yaml"
    text = path.read_text()
    # The vehicle declares `load_enabled` itself now (quiet-coast power rules); the fixture is
    # planted only on a definition that does not.
    if "  - id: load_enabled\n" not in text:
        assert text.count("state:\n") == 1
        path.write_text(text.replace("state:\n", LOAD_ENABLED, 1))
    if rules is not None:
        (root / "domains" / "power" / "rules.py").write_text(rules)
    return root


def test_set_load_moves_one_element_and_the_tick_holds_the_rest(tmp_path):
    world = plant.load_world(definition(tmp_path))
    start = plant.initial_values(world)
    assert start["load_enabled"]["csm_lighting"] == "on"
    assert start["load_enabled"]["csm_comm_heaters"] == "on"

    gaps: list[plant.Gap] = []
    off = plant.Effect(0, "set_load", {"load": "csm_lighting", "state": "off"})
    after = plant.step(world, start, 0.02, gaps, [off])
    assert after["load_enabled"] == {**start["load_enabled"], "csm_lighting": "off"}
    node = next(s.node for s in world.states if s.id == "load_enabled")
    assert after[node]["load_enabled"] == after["load_enabled"]
    assert "load_enabled" not in {gap.state.id for gap in gaps}

    held = plant.step(world, after, 0.02)
    assert held["load_enabled"] == after["load_enabled"]


def test_a_domain_rule_reads_a_keyed_state_element_by_element(tmp_path):
    world = plant.load_world(definition(tmp_path, READS_IT))
    start = plant.initial_values(world)
    assert plant.step(world, start, 0.02)["bus_b_v"] == 29.0
    off = plant.Effect(0, "set_load", {"load": "csm_lighting", "state": "off"})
    assert plant.step(world, start, 0.02, None, [off])["bus_b_v"] == 30.0
