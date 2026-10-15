"""The scenario overlay and the batch script (`09-quiet-coast-episode.md` §7, step 1).

A scenario is an episode's overlay on the declared vehicle: initial-condition overrides, an
allow-list of verbs, and scripted effects keyed by tick for batch mode. Every scenario here is a
**fixture** written to `tmp_path`: `vehicle/scenarios/quiet_coast.yaml` is §7 step 8's, and its
figures wait on a feasibility run. The values below are arbitrary.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402

SCENARIO = """
scenario: fixture_coast
initial:
  o2_csm_kg: 200.0
  comm_mode: sband_low
verbs: [set_comm_mode, select_antenna]
script:
  - {tick: 2, offset_us: 5000, verb: set_comm_mode, arguments: {mode: sband_high}}
  - {tick: 4, verb: set_comm_mode, arguments: {mode: vhf}}
"""


@pytest.fixture(scope="module")
def world() -> plant.World:
    return plant.load_world(VEHICLE)


def scenario_file(tmp_path: Path, text: str = SCENARIO) -> Path:
    path = tmp_path / "fixture_coast.yaml"
    path.write_text(text)
    return path


def test_initial_conditions_replace_the_declared_ones(world, tmp_path):
    scenario = plant.load_scenario(world, scenario_file(tmp_path))
    assert scenario.name == "fixture_coast"
    values = plant.initial_values(world, scenario)
    assert values["o2_csm_kg"] == values["o2_csm"] == 200.0
    assert plant.initial_values(world)["o2_csm_kg"] == 279.0  # the vehicle itself is unchanged
    assert values["internal"]["comm_mode"] == "sband_low"


def test_the_script_applies_each_effect_at_its_tick(world, tmp_path):
    scenario = plant.load_scenario(world, scenario_file(tmp_path))
    assert [e.verb for e in scenario.effects_at(2)] == ["set_comm_mode"]
    assert scenario.effects_at(3) == []
    seen: dict[int, str] = {}
    moved: list[int] = []

    def on_tick(tick, values, ledger, gaps):
        seen[tick] = values["comm_mode"]
        if ledger.moved():
            moved.append(tick)
        plant.assert_conservation(ledger)

    plant.run_scenario(world, scenario, 6, on_tick=on_tick)
    assert seen == {
        0: "sband_low",
        1: "sband_low",
        2: "sband_high",
        3: "sband_high",
        4: "vhf",
        5: "vhf",
    }
    assert moved, "the batch run never moved a stock"


def test_a_resumed_run_reaches_the_same_state_as_an_uninterrupted_one(world, tmp_path):
    scenario = plant.load_scenario(world, scenario_file(tmp_path))
    whole = plant.run_scenario(world, scenario, 6)
    half = plant.run_scenario(world, scenario, 3)
    resumed = plant.run_scenario(world, scenario, 3, values=half, start_tick=3)
    assert plant.state_hash(resumed) == plant.state_hash(whole)


def test_a_verb_outside_the_allow_list_is_refused(world, tmp_path):
    scenario = plant.load_scenario(world, scenario_file(tmp_path))
    scenario.admit("set_comm_mode")
    with pytest.raises(plant.EffectRefused, match="not one of the episode's verbs"):
        scenario.admit("start_burn")
    everything = plant.load_scenario(world, scenario_file(tmp_path, "scenario: open\n"))
    everything.admit("start_burn")  # no `verbs:` admits every registered verb


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("initial: {no_such_state: 1.0}\n", "names a state no domain declares"),
        ("initial: {o2_csm_kg: UNCONFIGURED}\n", "never with a debt"),
        ("initial: {o2_csm_kg: -1.0}\n", "non-negative amount"),
        ("verbs: [not_a_verb]\n", "which no domain registers"),
        (
            "verbs: [select_antenna]\nscript:\n  - {tick: 0, verb: set_comm_mode, arguments: {mode: vhf}}\n",
            "which the scenario's own `verbs` refuses",
        ),
        (
            "script:\n  - {tick: -1, verb: set_comm_mode, arguments: {mode: vhf}}\n",
            "non-negative tick",
        ),
        (
            "script:\n  - {tick: 0, offset_us: 20000, verb: set_comm_mode, arguments: {mode: vhf}}\n",
            "outside the tick",
        ),
        ("script:\n  - {tick: 0, verb: get_status}\n", "is not registered"),
    ],
)
def test_a_scenario_that_names_what_the_vehicle_does_not_have_is_refused(
    world, tmp_path, text, words
):
    with pytest.raises(plant.Unconfigured, match=words.replace("`", ".").replace("(", ".")):
        plant.load_scenario(world, scenario_file(tmp_path, text))
