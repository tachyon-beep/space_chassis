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
    plant.run_scenario(
        world, run, 10, on_tick=lambda t, v, *_: straight.append(plant.state_hash(v))
    )

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


def test_a_fault_happens_once_so_a_scale_cannot_compound(world, tmp_path):
    """A second onset of a `scale` fault would multiply again: 1.5 x 1.5, a fault nobody declared."""
    with pytest.raises(plant.Unconfigured, match="a fault happens once"):
        scenario(world, tmp_path, f"  - {{tick: 1, fault: {HEAT}}}\n  - {{tick: 4, fault: {HEAT}}}\n")
    dt = plant.tick_seconds(world)
    values = plant.initial_values(world)
    onset = plant.FaultOnset(offset_us=0, fault=HEAT)
    with pytest.raises(plant.EffectRefused, match="a fault happens once"):
        plant.step(world, values, dt, faults=[onset, onset])
    once = plant.step(world, values, dt, faults=[onset])
    with pytest.raises(plant.EffectRefused, match="a fault happens once"):
        plant.step(world, once, dt, faults=[onset])
    with pytest.raises(plant.EffectRefused, match="a fault happens once"):
        plant.apply_fault(world, once, HEAT)
    assert once["environment_heat_w"] == pytest.approx(values["environment_heat_w"] * 1.5)


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


def test_a_window_run_breaks_the_vehicle_on_the_step_batch_mode_does_and_replays_it(tmp_path):
    """A scenario's `faults` reach the window: live, and in the record's replay."""
    import checkpoint
    import console

    # A checkpoint hashes the engine tools with the corpus, so this copy carries them too.
    copy = faulted_copy(tmp_path / "vehicle")
    shutil.copy(VEHICLE / "tools" / "plant.py", copy / "tools" / "plant.py")
    world = plant.load_world(copy)
    path = tmp_path / "faulted_coast.yaml"
    path.write_text(f"scenario: faulted_coast\nfaults:\n  - {{tick: 3, fault: {TRIP}}}\n")
    named = console.load_scenario_file(world, path)
    batch: dict[int, str] = {}
    plant.run_scenario(
        world, named.scenario, 6, on_tick=lambda t, v, _l, _g: batch.__setitem__(t, plant.state_hash(v))
    )
    state = tmp_path / "state"
    executive = console.Executive(
        world, tmp_path / "diode", phase="translunar_coast", state_dir=state, scenario_file=named
    )
    try:
        executive.attach("alpha")
        snapshot = checkpoint.capture_state(executive, checkpoint.Compatibility.current(world))
        live: dict[int, str] = {}
        for _ in range(6):
            executive.cycle()
            live[executive.tick] = plant.state_hash(executive.truth)
        assert lighting(executive.truth) == "off"
        assert executive.truth[plant.FAULT_ONSETS] == {TRIP: 1}
    finally:
        executive.close()
    # Record tick `t` is batch row `t - 1`: the same step breaks the vehicle in both.
    assert live == {t: batch[t - 1] for t in range(1, 7)}
    replayed = console.replay_record(world, snapshot, console.read_record(state), scenario=named.scenario)
    assert [(t, h) for t, h, _link in replayed.points] == sorted(live.items())
    # A replay that does not carry the file's faults is not this world's history.
    with pytest.raises(console.RecordRefused, match="compare-point"):
        console.replay_record(world, snapshot, console.read_record(state))


def run_linter(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LINTER), "--dir", str(directory)],
        capture_output=True,
        text=True,
        check=False,
    )


def refusals(out: str) -> list[str]:
    """The linter's refusal lines, from its `REFUSED` block."""
    if "REFUSED" not in out:
        return []
    block = out[out.index("REFUSED") :].split("\n\n", 1)[0]
    return [line.strip()[2:] for line in block.splitlines()[1:] if line.strip().startswith("- ")]


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


def test_every_onset_row_is_held_to_its_state_and_a_quantity_takes_a_number(tmp_path):
    """The plant applies every `fault_value` row, so the linter reads every one, not the first."""
    broken = faulted_copy(tmp_path / "vehicle")
    power = broken / "domains" / "power" / "components.yaml"
    thermal = broken / "domains" / "thermal" / "components.yaml"
    # A word on a heat load: composed once, staged, and aborted the next tick in the domain's rule.
    replace(thermal, "        scale: 1.5\n", "        becomes: warm\n")
    # A second row for the same fault: a second element is fine, the same element twice is not, and
    # the second row's value is held to the vocabulary as the first's is.
    second = (
        "      - fault: PWR-03-lcl-nuisance-trip\n"
        "        key: {key}\n"
        "        becomes: {becomes}\n"
        '        provenance: {{basis: chosen, reason: "a second row"}}\n'
    )
    anchor = '        provenance: {basis: chosen, reason: "a test fixture: the trip drops one load"}\n'
    replace(
        power,
        anchor,
        anchor
        + second.format(key="csm_lighting", becomes='"off"')
        + second.format(key="csm_lighting_2", becomes='"tripped"'),
    )
    out = run_linter(broken).stdout
    for needle in (
        "makes environment_heat_w 'warm', and its `unit` ('W') is a quantity",
        "declares 'PWR-03-lcl-nuisance-trip' twice on element 'csm_lighting'",
        "makes load_enabled 'tripped', which its `unit`",
    ):
        assert needle in out, f"{needle!r} did not fire:\n{out[-3000:]}"


def test_a_discrete_state_a_domain_rule_advances_starts_from_its_declared_initial(tmp_path):
    """Seeding, beside the fault path: a ruled latch reads its own last value, so it needs one at t=0.

    The structure lane's `arm_state` and the FDIR debounce timers are the customers. The fixture gives
    power's `lcl_tripped` a starting map and a rule that holds it.
    """
    copy = faulted_copy(tmp_path / "vehicle")
    components = copy / "domains" / "power" / "components.yaml"
    anchor = '    unit: "map[load_id,enum[closed,tripped,retrying,latched]]"\n'
    replace(components, anchor, anchor + "    initial: {csm_lighting: closed}\n")
    rules = copy / "domains" / "power" / "rules.py"
    rules.write_text(
        rules.read_text()
        + '\n\ndef _held_trips(inputs, params, dt):\n    return inputs["lcl_tripped"]\n\n\n'
        + 'RULES["lcl_tripped"] = _held_trips\n'
    )
    ruled = plant.load_world(copy)
    assert "lcl_tripped" in ruled.rules
    values = plant.initial_values(ruled)
    assert values["lcl_tripped"] == {"csm_lighting": "closed"}
    gaps: list[plant.Gap] = []
    stepped = plant.step(ruled, values, plant.tick_seconds(ruled), gaps)
    assert stepped["lcl_tripped"] == {"csm_lighting": "closed"}
    assert not [g for g in gaps if g.state.id == "lcl_tripped"], gaps


HEATER_DUTY = """state:
  - id: heater_duty_commanded
    node: internal
    method: discrete
    unit: "map[zone_id,%]"
    initial: {csm_cabin: 0}
    initial_provenance: {basis: chosen, reason: "a test fixture: the heaters start off"}
    moved_by: ["command:set_heater"]
    command_value:
      - verb: set_heater
        argument: duty
        key: zone
        why: "identity: the commanded duty, as the percentage the verb carries"
    provenance: {basis: chosen, reason: "a test fixture for a carried numeric argument"}
"""


def test_a_numeric_argument_is_carried_as_its_number_and_refused_outside_its_range(tmp_path):
    """The thermal lane's ask, beside the fault path: `set_heater duty=40` makes the state 40."""
    copy = faulted_copy(tmp_path / "vehicle")
    components = copy / "domains" / "thermal" / "components.yaml"
    replace(components, "\nstate:\n", "\n" + HEATER_DUTY)
    replace(
        components,
        "internal_order: [heater_bank_duty,",
        "internal_order: [heater_duty_commanded, heater_bank_duty,",
    )
    out = run_linter(copy).stdout
    # The fixture's one refusal of its own is the dwell a discrete state owes; the carried number
    # itself must pass every check, the completeness check included. The first line keeps this from
    # passing on a linter that printed nothing.
    mentions = [line for line in out.splitlines() if "heater_duty_commanded" in line]
    assert mentions, out[-3000:]
    assert all("neither hysteresis nor dwell" in line for line in mentions), mentions
    # A keyed state the number is carried into must still say which element it sets.
    unkeyed = faulted_copy(tmp_path / "unkeyed")
    unkeyed_components = unkeyed / "domains" / "thermal" / "components.yaml"
    replace(unkeyed_components, "\nstate:\n", "\n" + HEATER_DUTY.replace("        key: zone\n", ""))
    replace(
        unkeyed_components,
        "internal_order: [heater_bank_duty,",
        "internal_order: [heater_duty_commanded, heater_bank_duty,",
    )
    assert "declares no `key` for 'set_heater'" in run_linter(unkeyed).stdout
    heated = plant.load_world(copy)
    values = plant.initial_values(heated)
    staged = plant.apply_command(
        heated,
        values,
        "set_heater",
        {"bank": "heater_bank_csm", "zone": "csm_avionics_bay", "duty": "40"},
    )
    assert staged["heater_duty_commanded"] == {"csm_cabin": 0, "csm_avionics_bay": 40}
    assert isinstance(staged["heater_duty_commanded"]["csm_avionics_bay"], int)
    # `+40` is forty; Python's parsers would also take `4_0`, ` 40` and `1e1`, which are not.
    signed = plant.apply_command(
        heated, values, "set_heater", {"bank": "heater_bank_csm", "zone": "csm_cabin", "duty": "+40"}
    )
    assert signed["heater_duty_commanded"]["csm_cabin"] == 40
    for bad, why in (
        ("150", "outside its declared range"),
        ("40.5", "is not an integer"),
        ("4_0", "plain decimal digits"),
        (" 40", "plain decimal digits"),
        ("1e1", "plain decimal digits"),
        ("", "plain decimal digits"),
    ):
        with pytest.raises(plant.EffectRefused, match=why):
            plant.apply_command(
                heated,
                values,
                "set_heater",
                {"bank": "heater_bank_csm", "zone": "csm_cabin", "duty": bad},
            )


THROTTLE = "      throttle_pct: {type: number, minimum: 10.5, maximum: 92.5}\n"
THROTTLE_BAND = (
    "      throttle_pct:\n"
    "        type: number\n"
    "        minimum: 10.5\n"
    "        maximum: 92.5\n"
    "        refused_bands:\n"
    "          - {at_or_above: 65, below: 92.5, note: the descent engine is not run here}\n"
)


def test_a_refused_band_is_a_hole_in_a_numeric_argument_s_range(tmp_path):
    """The propulsion lane's ask: `set_throttle` refuses 65 % up to, not including, 92.5 %.

    92.5 % is the descent engine's full-throttle position, so the band's upper edge is open, and
    the band names its edges rather than leaving a reader to know a convention. The verb's own
    `minimum` and `maximum` are held too: they were declared and nothing read them.
    """
    declared = {
        "type": "number",
        "minimum": 10.5,
        "maximum": 92.5,
        "refused_bands": [{"at_or_above": 65, "below": 92.5, "note": "the descent engine is not run here"}],
    }
    for good in ("10.5", "64.9", "92.5"):
        assert plant.numeric_argument("set_throttle", "throttle_pct", good, declared) == float(good)
    for bad, why in (
        ("65", r"inside its refused band \[65, 92\.5\) \(the descent engine is not run here\)"),
        ("92.4", "inside its refused band"),
        ("5", r"outside its declared range \[10\.5, 92\.5\]"),
        ("93", "outside its declared range"),
    ):
        with pytest.raises(plant.EffectRefused, match=why):
            plant.numeric_argument("set_throttle", "throttle_pct", bad, declared)
    # A number is plain decimals too: no exponent, no leading point, no `inf`.
    for bad in ("1e1", ".5", "inf", "nan", "64."):
        with pytest.raises(plant.EffectRefused, match="plain decimal digits"):
            plant.numeric_argument("set_floor", "floor", bad, {"type": "number", "minimum": 0})
    assert plant.numeric_argument("set_floor", "floor", "+0.5", {"type": "number", "minimum": 0}) == 0.5
    # A one-sided bound bounds one side.
    with pytest.raises(plant.EffectRefused, match=r"\[0, inf\]"):
        plant.numeric_argument("set_floor", "floor", "-1", {"type": "number", "minimum": 0})

    copy = faulted_copy(tmp_path / "declared")
    replace(copy / "domains" / "propulsion" / "commands.yaml", THROTTLE, THROTTLE_BAND)
    out = run_linter(copy).stdout
    assert "COMPOSES" in out and "refused_bands" not in out, out[-3000:]
    broken = faulted_copy(tmp_path / "broken")
    replace(
        broken / "domains" / "propulsion" / "commands.yaml",
        THROTTLE,
        THROTTLE_BAND.replace("below: 92.5, ", "below: 95, ").replace("at_or_above: 65, ", ""),
    )
    replace(
        broken / "domains" / "thermal" / "commands.yaml",
        '      duty: {type: integer, range: [0, 100], unit: "%"}\n',
        '      duty: {type: integer, range: [0, 100], unit: "%", refused_bands: [{above: 90, at_or_below: 110}]}\n',
    )
    out = run_linter(broken).stdout
    assert "a band names exactly one lower edge" in out, out[-3000:]
    assert "is (90, 110], which reaches past 'duty'" in out, out[-3000:]


def test_a_command_value_with_when_moves_only_the_state_its_call_names(tmp_path):
    """The propulsion lane's bug, beside the fault path: `arm_engine engine=sps` armed all three."""
    copy = faulted_copy(tmp_path / "vehicle")
    components = copy / "domains" / "propulsion" / "components.yaml"
    text = components.read_text()
    entry = "      - verb: arm_engine\n        argument: state\n"
    assert text.count(entry) == 3
    parts = text.split(entry)
    text = parts[0] + "".join(
        entry + f"        when: {{engine: {engine}}}\n" + rest
        for engine, rest in zip(("sps", "dps", "aps"), parts[1:], strict=True)
    )
    components.write_text(text)
    out = run_linter(copy).stdout
    assert ".when" not in out, out[-3000:]
    routed = plant.load_world(copy)
    values = plant.initial_values(routed)
    arguments = {"engine": "sps", "state": "armed"}
    staged = plant.apply_command(routed, values, "arm_engine", arguments)
    assert staged["sps_state"] == "armed"
    assert "dps_state" not in staged and "aps_state" not in staged
    assert {s.id for s in plant.command_targets(routed, "arm_engine", arguments)} >= {"sps_state"}
    assert not {"dps_state", "aps_state"} & {
        s.id for s in plant.command_targets(routed, "arm_engine", arguments)
    }
    # Without arguments the answer is every state the verb can move, as before.
    assert {"sps_state", "dps_state", "aps_state"} <= {
        s.id for s in plant.command_targets(routed, "arm_engine")
    }
    # A call that omits the routing argument is refused, not taken as moving no state.
    with pytest.raises(plant.EffectRefused, match=r"routes its effect on \['engine'\], which this call omits"):
        plant.apply_command(routed, values, "arm_engine", {"state": "armed"})
    # A route on a value the argument cannot take is refused by name.
    components.write_text(text.replace("when: {engine: aps}", "when: {engine: lmde}", 1))
    assert "is 'lmde', which 'engine' cannot take" in run_linter(copy).stdout
    # And a route on an optional argument is refused, since a call may leave it out.
    components.write_text(text)
    commands = copy / "domains" / "propulsion" / "commands.yaml"
    replace(
        commands,
        "      engine: {type: enum, values: [sps, dps, aps]}\n      state: {type: enum, values: [armed, safe]}\n",
        "      engine: {type: enum, values: [sps, dps, aps], optional: true}\n      state: {type: enum, values: [armed, safe]}\n",
    )
    assert "names 'engine', an optional argument of 'arm_engine'" in run_linter(copy).stdout


LEAK_SOURCES = """state:
  - id: leak_sources_g_s
    node: internal
    method: discrete
    unit: "map[leak_id,g/s]"
    initial: {lm_hatch_seal: 0.0, vessel: 0.0}
    initial_provenance: {basis: chosen, reason: "a test fixture: no leak at MET 0"}
    moved_by: ["fault:STR-01-hatch-seal-leak", "fault:STR-11-structural-thermal-cycling"]
    fault_value:
      - {fault: STR-01-hatch-seal-leak, key: lm_hatch_seal, becomes_from: magnitude}
      - {fault: STR-11-structural-thermal-cycling, key: vessel, becomes_from: magnitude}
    provenance: {basis: chosen, reason: "a test fixture for a fault's declared magnitude"}
"""


def test_an_onset_can_take_the_fault_policy_s_own_magnitude(tmp_path):
    """Structure's leaks, beside the fault path: the size is the policy's, not a copy of it."""
    copy = faulted_copy(tmp_path / "vehicle")
    components = copy / "domains" / "structure" / "components.yaml"
    replace(components, "\nstate:\n", "\n" + LEAK_SOURCES)
    replace(
        components,
        "internal_order: [relief_valve_state,",
        "internal_order: [leak_sources_g_s, relief_valve_state,",
    )
    out = run_linter(copy).stdout
    assert "leak_sources_g_s.fault_value" not in out, out[-3000:]
    leaking = plant.load_world(copy)
    values = plant.initial_values(leaking)
    stepped = plant.step(
        leaking,
        values,
        plant.tick_seconds(leaking),
        faults=[plant.FaultOnset(offset_us=0, fault="STR-01-hatch-seal-leak")],
    )
    assert stepped["leak_sources_g_s"] == {"lm_hatch_seal": 0.0055556, "vessel": 0.0}
    # A magnitude in another unit is refused rather than converted.
    policy = copy / "domains" / "structure" / "fault_policy.yaml"
    text = policy.read_text()
    marker = '      magnitude: 0.00055556\n      magnitude_unit: "g/s"\n'
    assert text.count(marker) == 1
    policy.write_text(text.replace(marker, marker.replace('"g/s"', '"g/h"')))
    assert "takes the fault's magnitude in 'g/h' into leak_sources_g_s" in run_linter(copy).stdout


def test_an_interlock_on_a_point_read_from_a_coupling_node_is_evaluated(tmp_path):
    """The propulsion lane's ask, beside the fault path: `prop_cutoff_guard_5` reads `prop_main`.

    A point may not name another domain's state, so a cross-domain reading names the node, and
    `point_reading` reads one by its derivation. The threshold's `point_units` still has to name the
    channel's unit, which the fixture states plainly.
    """
    copy = faulted_copy(tmp_path / "vehicle")
    replace(
        copy / "domains" / "propulsion" / "profiles.yaml",
        'point_units: "% remaining, checked at burn start"',
        'point_units: "%"',
    )
    guarded = plant.load_world(copy)
    interlock, problem = plant.resolve_interlock(guarded, "prop_cutoff_guard_5")
    assert problem is None and interlock is not None, problem
    assert interlock.point == "prop.propellant_remaining_pct"
    values = plant.initial_values(guarded)
    assert plant.point_reading(guarded, interlock.point, values) == 100.0
    stepped = plant.step(guarded, values, plant.tick_seconds(guarded))
    assert stepped[plant.INTERLOCK_DWELL][interlock.key] == 0
    assert not plant.interlock_tripped(guarded, interlock, stepped)


def test_every_sentinel_state_s_two_copies_agree_after_a_tick(world):
    """The ECLSS lane's finding, beside the fault path: a walk kept only the last sentinel entry.

    `values[id]` and `values["internal"][id]` are one value written twice, and a tick that advanced
    two sentinel states left the first one's sub-map entry where it was.
    """
    dt = plant.tick_seconds(world)
    values = plant.initial_values(world)
    for _ in range(3):
        values = plant.step(world, values, dt)
    sentinel, _ = world.sentinel_states()
    inner = values["internal"]
    stale = [
        s.id for s in sentinel if s.id in values and s.id in inner and inner[s.id] != values[s.id]
    ]
    assert not stale, stale


BURN_MOVERS = """    moved_by:
      - "command:arm_engine"
      - "command:start_burn"
      - "logic:the ignition sequence carries the engine to mainstage once its chamber has built"
    ignition_to_mainstage_s: 0.1
    command_value:
      - verb: start_burn
        argument: engine
        constant: ignition
        when: {engine: sps}
        why: "a test fixture: the start command opens the sequence at ignition"
"""
SECOND_COMMAND_VALUE = "    command_value:\n      - verb: arm_engine\n"
SEQUENCE_TIMER = """  - id: sps_sequence_elapsed_s
    node: internal
    method: dynamics
    unit: s
    initial: 0.0
    initial_provenance: {basis: chosen, reason: "a test fixture: no sequence is running at MET 0"}
    provenance: {basis: chosen, reason: "a test fixture: the time the engine has spent in ignition"}
"""
BURN_RULES = '''"""A test fixture: the SPS ignition-to-mainstage sequence."""


def sps_state(inputs, params, dt):
    held = inputs["sps_state"]
    if held == "ignition" and inputs["sps_sequence_elapsed_s"] >= params["ignition_to_mainstage_s"]:
        return "mainstage"
    return held


def sps_sequence_elapsed_s(inputs, params, dt):
    if inputs["sps_state"] == "ignition":
        return inputs["sps_sequence_elapsed_s"] + dt
    return 0.0


RULES = {"sps_state": sps_state, "sps_sequence_elapsed_s": sps_sequence_elapsed_s}
'''


def test_a_commanded_machine_with_a_rule_runs_a_timed_sequence_after_the_command(tmp_path):
    """The propulsion lane's burn sequence, beside the fault path: the shape exists with no new engine.

    A discrete state with `command:` movers *and* a `logic:` mover is not effect-owned, so it may
    have a rule; the command writes the machine at its stamp, the rule carries it on from there,
    and the seeding above gives the rule its starting position. `start_burn` opens ignition and the
    rule moves to mainstage once the sequence timer has run, ticks later, in replay order.
    """
    copy = faulted_copy(tmp_path / "vehicle")
    components = copy / "domains" / "propulsion" / "components.yaml"
    text = components.read_text()
    head, tail = text.split("  - id: sps_state\n", 1)
    replace_once = '    moved_by:\n      - "command:arm_engine"\n'
    assert tail.count(replace_once) >= 1
    tail = tail.replace(replace_once, BURN_MOVERS, 1)
    # The state's own `command_value` follows; its entries join the one above rather than a second key.
    tail = tail.replace(SECOND_COMMAND_VALUE, "      - verb: arm_engine\n", 1)
    components.write_text(head + SEQUENCE_TIMER + "  - id: sps_state\n" + tail)
    replace(
        components,
        "internal_order: [dps_throttle_pct,",
        "internal_order: [sps_sequence_elapsed_s, dps_throttle_pct,",
    )
    (copy / "domains" / "propulsion" / "rules.py").write_text(BURN_RULES)
    out = run_linter(copy).stdout
    # The one state added moves the README's state counts, which the fixture does not rewrite.
    refused = refusals(out)
    assert all(line.startswith("README.md:") for line in refused), refused

    burning = plant.load_world(copy)
    dt = plant.tick_seconds(burning)
    values = plant.initial_values(burning)
    assert values["sps_state"] == "off" and values["sps_sequence_elapsed_s"] == 0.0
    start = [plant.Effect(offset_us=0, verb="start_burn", arguments={"engine": "sps"})]
    seen = []
    for tick in range(10):
        values = plant.step(burning, values, dt, effects=start if tick == 1 else None)
        seen.append(values["sps_state"])
    assert seen[0] == "off" and seen[1] == "ignition"
    assert "mainstage" in seen and seen[-1] == "mainstage"
    # 0.1 s of ignition at 20 ms a tick: the sentinel timer runs after the machine in each tick, so
    # the machine reads five ticks of it on the sixth.
    assert seen.index("mainstage") - seen.index("ignition") == 5, seen
    # Only the SPS: start_burn routes on `engine`, so the other machines did not move.
    assert values["dps_state"] == "off" and values["aps_state"] == "off"


def test_a_dynamics_state_starts_from_its_declared_vector(tmp_path):
    """The GNC lane's ask: a quaternion and a body rate start where their `initial` says.

    The scalar seed above skipped anything that was not a number, so a `dynamics` state's vector
    started as nothing and its rule's first read of itself was a gap.
    """
    copy = faulted_copy(tmp_path / "vehicle")
    components = copy / "domains" / "gnc" / "components.yaml"
    replace(
        components,
        "  - id: attitude\n    node: vehicle_dynamics\n    method: dynamics\n",
        "  - id: attitude\n    node: vehicle_dynamics\n    method: dynamics\n"
        "    initial: [0.7071067811865476, 0.0, -0.7071067811865476, 0.0]\n",
    )
    replace(
        components,
        "  - id: body_rate\n    node: vehicle_dynamics\n    method: dynamics\n",
        "  - id: body_rate\n    node: vehicle_dynamics\n    method: dynamics\n    initial: [0.0, 0.1, 0.0]\n",
    )
    vectored = plant.load_world(copy)
    values = plant.initial_values(vectored)
    assert values["attitude"] == [0.7071067811865476, 0.0, -0.7071067811865476, 0.0]
    assert values["body_rate"] == [0.0, 0.1, 0.0]
    declared = next(state for state in vectored.states if state.id == "body_rate").spec["initial"]
    values["body_rate"][1] = 9.0
    assert declared == [0.0, 0.1, 0.0]
    # A vector in the truth hashes and survives the checkpoint's JSON like any other value.
    assert plant.state_hash(values) == plant.state_hash(json.loads(json.dumps(values)))


def test_a_zone_cooled_by_space_is_in_no_loop_s_load_and_says_why(tmp_path):
    """The thermal lane's ask: the SM service bay is not on the glycol loop.

    `cooled_by: space` is accepted with a `cooled_by_note`, the exemption's reason, and the bay
    leaves the primary loop's collected load; without the note it is refused.
    """
    bay = "        cooled_by: loop_primary\n        heat_state: service_bay_heat_w\n"
    noted = tmp_path / "noted"
    copy_noted = faulted_copy(noted)
    replace(
        copy_noted / "vehicle.yaml",
        bay,
        "        cooled_by: space\n        cooled_by_note: radiates through the SM skin\n"
        "        heat_state: service_bay_heat_w\n",
    )
    out = run_linter(copy_noted).stdout
    assert "zones.csm_service_bay.cooled_by" not in out, out[-3000:]
    bare = faulted_copy(tmp_path / "bare")
    replace(bare / "vehicle.yaml", bay, "        cooled_by: space\n        heat_state: service_bay_heat_w\n")
    out = run_linter(bare).stdout
    assert "is 'space' without a `cooled_by_note`" in out, out[-3000:]


def test_a_dark_reads_state_is_named_and_blamed(world):
    """The GNC lane's ask: an edge whose `reads:` state is dark this tick names that state.

    The gap used to say the driver "was never declared" beside the `reads:` that declares it, and
    its `needs` named the node, so `blame` filed the stock under itself instead of the dark state.
    """
    edge = next(e for e in world.edges if e.id == "E-REC-GND")
    with pytest.raises(plant.Unconfigured) as caught:
        plant.stock_flux(world, edge, {}, 0.02)
    assert "reads `playback_rate` (this edge's `reads:`), which has no value this tick" in caught.value.what
    assert "never declared" not in caught.value.what
    assert caught.value.needs == "playback_rate"

    by_id = {state.id: state for state in world.states}
    received, rate = by_id["delivered_bits"], by_id["playback_rate"]
    stock = plant.Gap(state=received, where="w", owed=caught.value.what, needs="playback_rate")
    upstream = plant.Gap(state=rate, where="w", owed="its rule is owed", needs=None)
    assert plant.blame(world, [stock, upstream])[received.id] is upstream
