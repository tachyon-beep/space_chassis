"""WP09: a fault's onset reaches the hidden truth inside `plant.step`, deterministically.

Until WP09 `tools/faults.py` could place a fault in time and nothing could put it anywhere: the
schedule fed `--plan` and no fault ever changed a modelled state mid-run. The path now is

    fault_policy.yaml (the fault)  ->  scenario `faults:` / faults.injections (when)
        ->  plant.FaultOnset on step's sub-tick queue  ->  apply_fault (what, from `fault_value`)

and the property that matters most is the one `plant.md` §6 states: the same inputs reproduce
every per-tick hash, across a checkpoint and a resume as well as straight through.

The vehicle declares no `fault_value` yet (the domains own their states, and their lanes declare
their onsets), so every fixture here is a copy of the vehicle with two onsets written in: a keyed
discrete one (an LCL nuisance trip dropping `csm_lighting`) and a scaled `dynamics` one (a thermal
fault on the held `environment_heat_w`). The physics of the pairing is arbitrary; the mechanism is
what is under test.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import faults  # noqa: E402
import plant  # noqa: E402

LINTER = VEHICLE / "tools" / "check_vehicle.py"
TRIP = "PWR-03-lcl-nuisance-trip"
HEAT = "TCS-03-radiator-isolation"

POWER_ONSET = """    moved_by: ["command:set_load", "fault:PWR-03-lcl-nuisance-trip"]
    fault_value:
      - fault: PWR-03-lcl-nuisance-trip
        key: csm_lighting
        becomes: "off"
        provenance: {basis: chosen, reason: "a test fixture: the trip drops one load"}
"""
THERMAL_ONSET = """    initial: 1086.9
    moved_by: ["fault:TCS-03-radiator-isolation"]
    fault_value:
      - fault: TCS-03-radiator-isolation
        scale: 1.5
        provenance: {basis: chosen, reason: "a test fixture: the held load jumps by half"}
"""


def faulted_copy(destination: Path) -> Path:
    """The vehicle's definition, prose and claim-making tools, with the two fixture onsets."""
    destination.mkdir(parents=True)
    for name in (
        "vehicle.yaml",
        "mission.yaml",
        "coupling.yaml",
        "channels.yaml",
        "presentation.yaml",
        "README.md",
        "plant.md",
    ):
        shutil.copy(VEHICLE / name, destination / name)
    (destination / "tools").mkdir()
    for name in ("faults.py", "console.py", "checkpoint.py"):
        shutil.copy(VEHICLE / "tools" / name, destination / "tools" / name)
    shutil.copytree(
        VEHICLE / "domains", destination / "domains", ignore=shutil.ignore_patterns("__pycache__")
    )
    replace(
        destination / "domains" / "power" / "components.yaml",
        '    moved_by: ["command:set_load"]\n',
        POWER_ONSET,
    )
    replace(
        destination / "domains" / "thermal" / "components.yaml",
        "    initial: 1086.9\n",
        THERMAL_ONSET,
    )
    return destination


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert text.count(old) == 1, f"the fixture no longer matches {old!r} in {path.name}"
    path.write_text(text.replace(old, new, 1))


@pytest.fixture(scope="module")
def faulted(tmp_path_factory) -> Path:
    return faulted_copy(tmp_path_factory.mktemp("faulted") / "vehicle")


@pytest.fixture(scope="module")
def world(faulted) -> plant.World:
    return plant.load_world(faulted)


def scenario(world: plant.World, tmp_path: Path, rows: str, script: str = "") -> plant.Scenario:
    path = tmp_path / "faulted_coast.yaml"
    path.write_text(f"scenario: faulted_coast\n{script}faults:\n{rows}")
    return plant.load_scenario(world, path)


def lighting(values: dict) -> str:
    return values["load_enabled"]["csm_lighting"]


def test_a_scripted_fault_moves_the_truth_at_its_tick_and_the_tick_carries_it(world, tmp_path):
    run = scenario(
        world,
        tmp_path,
        f"  - {{tick: 3, fault: {TRIP}}}\n  - {{tick: 5, offset_us: 7000, fault: {HEAT}}}\n",
    )
    assert [o.fault for o in run.faults_at(3)] == [TRIP] and run.faults_at(4) == []
    start = plant.initial_values(world, run)
    heat0 = start["environment_heat_w"]
    seen: dict[int, dict] = {}

    def on_tick(tick, values, ledger, gaps):
        seen[tick] = values

    plant.run_scenario(world, run, 8, on_tick=on_tick)
    assert [lighting(seen[t]) for t in range(8)] == ["on"] * 3 + ["off"] * 5
    assert [seen[t]["environment_heat_w"] for t in range(8)] == [heat0] * 5 + [heat0 * 1.5] * 3
    # The onset is visible downstream in its own tick: bus B's load sum reads the switch after the
    # fault lands, so the 100 W lighting load leaves the bus at tick 3, not tick 4.
    assert seen[3]["bus_b_load_w"] == pytest.approx(seen[2]["bus_b_load_w"] - 100.0)
    # And the truth records what arrived, from the tick it arrived.
    assert plant.FAULT_ONSETS not in seen[2]
    assert seen[3][plant.FAULT_ONSETS] == {TRIP: 1}
    assert seen[7][plant.FAULT_ONSETS] == {TRIP: 1, HEAT: 1}


def test_a_tick_with_no_fault_due_is_the_tick_it_was_before_wp09(world):
    """No fault, no new key: a faultless run hashes exactly as it did before the queue existed."""
    dt = plant.tick_seconds(world)
    values = plant.initial_values(world)
    plain = plant.step(world, values, dt)
    assert plant.FAULT_ONSETS not in plain
    assert plant.state_hash(plant.step(world, values, dt, faults=[])) == plant.state_hash(plain)
    assert plant.state_hash(plant.step(world, values, dt, faults=None)) == plant.state_hash(plain)


def test_restart_and_replay_reproduce_every_hash_with_faults_either_side(world, tmp_path):
    """`plant.md` §6, with a fault before the checkpoint and one after it."""
    run = scenario(
        world,
        tmp_path,
        f"  - {{tick: 2, offset_us: 5000, fault: {TRIP}}}\n  - {{tick: 7, fault: {HEAT}}}\n",
    )
    straight: list[str] = []
    plant.run_scenario(world, run, 10, on_tick=lambda t, v, *_: straight.append(plant.state_hash(v)))

    first: list[str] = []
    stopped = plant.run_scenario(
        world, run, 5, on_tick=lambda t, v, *_: first.append(plant.state_hash(v))
    )
    # The checkpoint's body is JSON (`checkpoint.encode`); the resume starts from what it decodes.
    restored = json.loads(json.dumps(stopped, sort_keys=True))
    assert restored[plant.FAULT_ONSETS] == {TRIP: 1}
    second: list[str] = []
    plant.run_scenario(
        world,
        run,
        5,
        values=restored,
        start_tick=5,
        on_tick=lambda t, v, *_: second.append(plant.state_hash(v)),
    )
    assert first + second == straight
    assert len(set(straight[1:4])) == 3, "the fault at tick 2 should have changed the trace"


def test_a_fault_and_a_command_at_one_microsecond_land_fault_first(world, tmp_path):
    run = scenario(
        world,
        tmp_path,
        f"  - {{tick: 1, offset_us: 4000, fault: {TRIP}}}\n",
        script=(
            "script:\n"
            "  - {tick: 1, offset_us: 4000, verb: set_load, "
            "arguments: {load: csm_lighting, state: 'on'}}\n"
        ),
    )
    last = plant.run_scenario(world, run, 2)
    # The breaker trips and the command, stamped at the same microsecond, recloses what it finds.
    assert lighting(last) == "on"
    assert last[plant.FAULT_ONSETS] == {TRIP: 1}


def test_a_fault_the_plant_cannot_fire_is_refused_by_name(world, tmp_path):
    with pytest.raises(plant.Unconfigured, match="not declared by any domain"):
        scenario(world, tmp_path, "  - {tick: 0, fault: XYZ-99-nothing}\n")
    # Declared, but no state says what its onset does: firing it would change nothing.
    with pytest.raises(plant.Unconfigured, match="no state declares what its onset does"):
        scenario(world, tmp_path, "  - {tick: 0, fault: PWR-02-fuel-cell-degradation}\n")
    with pytest.raises(plant.Unconfigured, match="outside the tick"):
        scenario(world, tmp_path, f"  - {{tick: 0, offset_us: 20000, fault: {TRIP}}}\n")
    with pytest.raises(plant.Unconfigured, match="non-negative tick"):
        scenario(world, tmp_path, f"  - {{tick: -1, fault: {TRIP}}}\n")
    dt = plant.tick_seconds(world)
    values = plant.initial_values(world)
    with pytest.raises(plant.EffectRefused, match="integer number of microseconds"):
        plant.step(world, values, dt, faults=[plant.FaultOnset(offset_us=1.5, fault=TRIP)])
    with pytest.raises(plant.EffectRefused, match="is not a `FaultOnset`"):
        plant.step(world, values, dt, faults=[TRIP])


def test_the_schedule_lands_on_the_tick_and_microsecond_its_decimal_names(world):
    tick_us = plant._tick_us(plant.tick_seconds(world))
    events = [
        # 0.000006 h is 21,600 µs: tick 1, 1,600 µs in.
        {"met_h": 0.000006, "fault": TRIP},
        # 1 h is 180,000 ticks exactly at 50 Hz.
        {"met_h": 1.0, "fault": HEAT},
        {"met_h": 0.5, "fault": "PWR-02-fuel-cell-degradation"},
    ]
    onsets, owed = faults.injections(world, events)
    assert tick_us == 20_000
    assert onsets == {
        1: [plant.FaultOnset(offset_us=1_600, fault=TRIP)],
        180_000: [plant.FaultOnset(offset_us=0, fault=HEAT)],
    }
    assert [e["fault"] for e in owed] == ["PWR-02-fuel-cell-degradation"]
    # A run whose tick 0 is MET tick 100,000 sees the second event 80,000 ticks in, and not the first.
    later, _ = faults.injections(world, events, met0_tick=100_000)
    assert later == {80_000: [plant.FaultOnset(offset_us=0, fault=HEAT)]}


def test_the_scheduled_onsets_join_the_scripted_ones_and_fire(world, tmp_path):
    run = scenario(world, tmp_path, f"  - {{tick: 4, fault: {HEAT}}}\n")
    onsets, _ = faults.injections(world, [{"met_h": 0.000006, "fault": TRIP}])
    both = faults.with_schedule(run, onsets)
    assert sorted(both.faults) == [1, 4] and run.faults == {4: run.faults[4]}
    last = plant.run_scenario(world, both, 5)
    assert last[plant.FAULT_ONSETS] == {TRIP: 1, HEAT: 1}
    assert lighting(last) == "off"


def test_the_window_run_refuses_a_scenario_that_carries_faults(world, faulted, tmp_path):
    import console

    path = tmp_path / "faulted_coast.yaml"
    path.write_text(f"scenario: faulted_coast\nfaults:\n  - {{tick: 3, fault: {TRIP}}}\n")
    with pytest.raises(ValueError, match="carries `faults`"):
        console.load_scenario_file(world, path)


def run_linter(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LINTER), "--dir", str(directory)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_linter_composes_a_declared_onset(faulted):
    result = run_linter(faulted)
    assert result.returncode == 0, result.stdout[-2000:]
    assert "fault_value" not in result.stdout, result.stdout[-2000:]


def test_the_linter_refuses_an_onset_it_cannot_hold_to_the_state(tmp_path):
    broken = faulted_copy(tmp_path / "vehicle")
    power = broken / "domains" / "power" / "components.yaml"
    thermal = broken / "domains" / "thermal" / "components.yaml"
    # A value outside the vocabulary, on the keyed state.
    replace(power, 'becomes: "off"\n', 'becomes: "tripped"\n')
    # A scaled onset with no provenance, on the dynamics state.
    replace(
        thermal,
        '        provenance: {basis: chosen, reason: "a test fixture: the held load jumps by half"}\n',
        "",
    )
    # A fault mover naming another domain's fault, on an algebraic state, and an orphan row.
    replace(
        power,
        "  - id: bus_a_load_w\n",
        "  - id: bus_a_load_w\n"
        '    moved_by: ["fault:TCS-01-pump-stall", "fault:PWR-03-lcl-nuisance-trip"]\n'
        "    fault_value:\n"
        "      - {fault: PWR-03-lcl-nuisance-trip, becomes: 0, provenance: {basis: chosen, reason: x}}\n"
        "      - {fault: PWR-04-orphan, becomes: 0, provenance: {basis: chosen, reason: x}}\n",
    )
    out = run_linter(broken).stdout
    for needle in (
        "makes load_enabled 'tripped', which its `unit`",
        "carries no `provenance`",
        "names fault 'TCS-01-pump-stall', which this domain's `fault_policy.yaml` does not declare",
        "declares a fault onset on bus_a_load_w, an `algebraic` state",
        "declares an onset for 'PWR-04-orphan', which `moved_by` does not name",
    ):
        assert needle in out, f"{needle!r} did not fire:\n{out[-3000:]}"
