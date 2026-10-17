"""Structure rules (`domains/structure/rules.py`): the pyros, the ring latches and the leak.

Every assertion runs through the real step loop on a scripted scenario, so a command's effect, the
rule that follows from it and the hold between commands are the plant's own. The two linter cases
at the end break a copy of the definition and assert the linter's words.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402

DEVICES = {
    "interstage_nut_1",
    "interstage_nut_2",
    "interstage_nut_3",
    "interstage_nut_4",
    "ascent_circuit_interrupter_1",
    "ascent_circuit_interrupter_2",
    "interstage_umbilical_cutter",
    "docking_ring_charge",
}
STAGING = DEVICES - {"docking_ring_charge"}
LATCHES = {f"latch_{n:02d}" for n in range(1, 13)}


@pytest.fixture(scope="module")
def world() -> plant.World:
    return plant.load_world(VEHICLE)


def state(world, sid):
    return next(s for s in world.states if s.id == sid)


def run(world, tmp_path, script, ticks, watch):
    """Run a scripted scenario and return, per tick, each watched state's value and the gaps."""
    document = {
        "scenario": "structure_fixture",
        "script": [{"tick": t, "verb": v, "arguments": a} for t, v, a in script],
    }
    path = tmp_path / "structure_fixture.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    scen = plant.load_scenario(world, path)
    trace: list[dict] = []

    def on_tick(tick, values, ledger, gaps):
        row = {sid: plant.state_level(values, state(world, sid)) for sid in watch}
        row["gaps"] = {g.state.id: f"{g.where}: {g.owed}" for g in gaps}
        trace.append(row)

    plant.run_scenario(world, scen, ticks, on_tick=on_tick)
    return trace


def test_every_device_is_unfired_and_every_latch_engaged_after_the_first_tick(world, tmp_path):
    trace = run(world, tmp_path, [], 2, ["pyro_fired", "docking_latch_state", "events_fired"])
    for row in trace:
        assert row["pyro_fired"] == dict.fromkeys(DEVICES, False)
        assert row["docking_latch_state"] == dict.fromkeys(LATCHES, "engaged")
        assert set(row["events_fired"].values()) == {False}
        assert "pyro_fired" not in row["gaps"] and "docking_latch_state" not in row["gaps"]


def test_staging_fires_the_nuts_interrupters_and_cutter_and_nothing_else_and_they_stay_fired(
    world, tmp_path
):
    """The event is the key and the device is the consequence: `execute_event` records
    `descent_stage_separation`, and the seven devices that event declares are fired from the next
    computation on. The CSM's docking ring charge belongs to a different event and stays intact; and
    nothing un-fires a device, because the record it is computed from never forgets an event."""
    script = [(2, "execute_event", {"event": "descent_stage_separation", "arm_token": "x"})]
    trace = run(world, tmp_path, script, 10, ["pyro_fired", "events_fired"])
    before, after = trace[1], trace[-1]
    assert not any(before["pyro_fired"].values())
    assert after["events_fired"]["descent_stage_separation"] is True
    assert {d for d, fired in after["pyro_fired"].items() if fired} == STAGING
    fired_ticks = [i for i, row in enumerate(trace) if row["pyro_fired"]["interstage_nut_1"]]
    assert fired_ticks == list(range(fired_ticks[0], len(trace)))


def test_ascent_jettison_fires_the_docking_ring_charge(world, tmp_path):
    script = [(1, "execute_event", {"event": "lm_ascent_jettison", "arm_token": "x"})]
    trace = run(world, tmp_path, script, 4, ["pyro_fired"])
    assert {d for d, fired in trace[-1]["pyro_fired"].items() if fired} == {"docking_ring_charge"}


def test_undocking_fires_no_pyro_and_moves_the_configuration(world, tmp_path):
    """Undocking is the probe's capture latches, released electrically, after the crew has cocked the
    twelve ring latches by hand (News Reference p. 88): no device fires, and the configuration
    machine the event moves still advances."""
    script = [(1, "execute_event", {"event": "lm_undocking", "arm_token": "x"})]
    trace = run(world, tmp_path, script, 4, ["lm_separation_state", "pyro_fired"])
    assert "pyro_fired" not in trace[-1]["gaps"]
    assert not any(trace[-1]["pyro_fired"].values())
    assert trace[-1]["lm_separation_state"] == "undocked"


def test_an_event_whose_devices_are_unset_is_a_gap_on_the_pyros_and_names_its_list(world, tmp_path):
    """`pyro_fire` names no device, so its list is owed. Executing it does not invent `[]`: the pyro
    state refuses, naming the list."""
    script = [(1, "execute_event", {"event": "pyro_fire", "arm_token": "x"})]
    trace = run(world, tmp_path, script, 4, ["pyro_fired"])
    assert "pyro_fired" not in trace[0]["gaps"]
    assert "fires_pyro_fire" in trace[-1]["gaps"]["pyro_fired"]


def test_the_ring_follows_the_all_drive_and_a_one_drive_is_recorded_without_moving_a_latch(
    world, tmp_path
):
    script = [
        (1, "set_docking_latch", {"interface": "docking_interface", "latch": "all", "state": "release"}),
        (4, "set_docking_latch", {"interface": "docking_interface", "latch": "one", "state": "engage"}),
        (7, "set_docking_latch", {"interface": "docking_interface", "latch": "all", "state": "engage"}),
    ]
    trace = run(world, tmp_path, script, 10, ["docking_latch_state", "latch_drive"])
    assert set(trace[2]["docking_latch_state"].values()) == {"released"}
    assert trace[5]["latch_drive"] == {"all": "release", "one": "engage"}
    assert set(trace[5]["docking_latch_state"].values()) == {"released"}
    assert set(trace[-1]["docking_latch_state"].values()) == {"engaged"}
    assert len(trace[-1]["docking_latch_state"]) == 12


def test_the_arm_window_is_the_arm_expiry_threshold(world):
    """The rule's `ttl_s` and the interlock's assert are one number: a token the rule still calls
    armed must not be one the interlock calls expired, or the reverse."""
    profiles = yaml.safe_load((VEHICLE / "domains/structure/profiles.yaml").read_text())
    expiry = next(t for t in profiles["thresholds"] if t["id"] == "arm_expiry")
    assert state(world, "arm_state").spec["ttl_s"] == expiry["assert"]


def test_the_leak_rule_reads_the_seal_floor_from_the_hatch_interlock(world):
    profiles = yaml.safe_load((VEHICLE / "domains/structure/profiles.yaml").read_text())
    floor = next(t for t in profiles["thresholds"] if t["id"] == "hatch_open_with_pressure")
    assert state(world, "structural_leak_g_s").spec["pressure_floor_psid"] == floor["assert"]


# --- the linter: a constant is the value a command sets -------------------------------------------


def copy_definition(destination: Path) -> Path:
    """The definition and the prose the linter reads, as `test_vehicle_config.copy_definition`."""
    destination.mkdir(parents=True)
    for name in ("vehicle.yaml", "mission.yaml", "coupling.yaml", "channels.yaml",
                 "presentation.yaml", "README.md", "plant.md"):
        shutil.copy(VEHICLE / name, destination / name)
    (destination / "tools").mkdir()
    for name in ("faults.py", "console.py", "checkpoint.py"):
        shutil.copy(VEHICLE / "tools" / name, destination / "tools" / name)
    shutil.copytree(VEHICLE / "domains", destination / "domains")
    return destination


def lint(directory: Path) -> str:
    result = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "check_vehicle.py"), "--dir", str(directory)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout + result.stderr


def break_arm_constant(tmp_path: Path, replacement: str | None) -> str:
    copy = copy_definition(tmp_path / "copy")
    path = copy / "domains/structure/components.yaml"
    text = path.read_text()
    old = "        constant: armed\n"
    assert text.count(old) == 1
    path.write_text(text.replace(old, replacement or ""))
    return lint(copy)


def test_a_command_whose_constant_the_state_holds_is_not_refused_by_the_vocabulary_rule(tmp_path):
    """`arm_event`'s arguments name an event and can never reach `none/armed/expired/consumed`; the
    value it writes is its constant. The mover rule asked only the arguments, and refused the one
    command on the vehicle that sets this state for the reason a trigger cannot — the unbroken copy
    shows the constant now counts among what the verb can express (the fault-injection lane's form
    of the same fix, adopted so the two branches agree)."""
    out = lint(copy_definition(tmp_path / "copy"))
    assert "arm_state.moved_by: names 'arm_event'" not in out


def test_a_constant_the_state_cannot_hold_is_refused_where_it_is_declared(tmp_path):
    out = break_arm_constant(tmp_path, "        constant: primed\n")
    assert "arm_state.command_value[arm_event].constant: is 'primed'" in out
    assert "cannot hold" in out


def test_without_the_constant_the_vocabulary_rule_refuses_the_mover_again(tmp_path):
    """Delete the constant and the entry is the identity form, which the arguments decide — and
    they cannot express a token's position, so the old refusal is back. The exemption is the
    constant, not the verb."""
    out = break_arm_constant(tmp_path, None)
    assert "arm_state.moved_by: names 'arm_event', whose arguments can take" in out


# --- the tunnel: two hatches and a ring between two cabins -----------------------------------------


def ring(state):
    return (1, "set_docking_latch", {"interface": "docking_interface", "latch": "all", "state": state})


def hatch(tick, vehicle, which, position):
    return (tick, "set_hatch_valve", {"vehicle": vehicle, "hatch": which, "state": position})


def test_all_four_hatches_start_latched_and_the_leak_is_zero(world, tmp_path):
    trace = run(world, tmp_path, [], 2, ["hatch_state", "structural_leak_g_s"])
    assert trace[-1]["hatch_state"] == dict.fromkeys(
        ["hatch_crew_csm", "hatch_crew_lm", "hatch_tunnel_csm", "hatch_tunnel_lm"], "latched"
    )
    assert trace[-1]["structural_leak_g_s"] == 0.0


def test_cocking_the_ring_for_undocking_with_both_tunnel_hatches_shut_loses_nothing(world, tmp_path):
    """The News Reference's undocking order (p. 88): the CM crewman cocks all twelve ring latches
    and closes both hatches, and the probe's capture latches hold the LM until release. With the
    tunnel shut at both ends an unsealed ring has nothing behind it."""
    script = [ring("release"), (4, "execute_event", {"event": "lm_undocking", "arm_token": "x"})]
    trace = run(world, tmp_path, script, 8, ["docking_latch_state", "structural_leak_g_s"])
    assert set(trace[3]["docking_latch_state"].values()) == {"released"}
    for row in trace:
        assert "structural_leak_g_s" not in row["gaps"], row["gaps"]
        assert row["structural_leak_g_s"] == 0.0


def test_an_open_tunnel_hatch_is_sealed_by_the_ring_and_unsealed_without_it(world, tmp_path):
    """Open the CM's forward hatch on a latched ring and the tunnel joins the cabin: no loss. Release
    the ring with that hatch still open and the cabin is behind an unseated seal — the confounder a
    crew has to tell apart from a cabin leak, and the debt is the tunnel's."""
    script = [hatch(1, "csm", "hatch_tunnel_csm", "open"),
              (5, "set_docking_latch", {"interface": "docking_interface", "latch": "all", "state": "release"})]
    trace = run(world, tmp_path, script, 9, ["hatch_state", "structural_leak_g_s"])
    assert trace[3]["hatch_state"]["hatch_tunnel_csm"] == "open"
    assert trace[3]["structural_leak_g_s"] == 0.0
    owed = trace[-1]["gaps"]["structural_leak_g_s"]
    assert "hatch_tunnel_csm" in owed and "unseated ring seal" in owed


def test_after_undocking_an_open_tunnel_hatch_faces_space(world, tmp_path):
    script = [(1, "execute_event", {"event": "lm_undocking", "arm_token": "x"}),
              hatch(4, "lm", "hatch_tunnel_lm", "open")]
    trace = run(world, tmp_path, script, 8, ["lm_separation_state", "structural_leak_g_s"])
    assert trace[-1]["lm_separation_state"] == "undocked"
    owed = trace[-1]["gaps"]["structural_leak_g_s"]
    assert "hatch_tunnel_lm" in owed and "nothing docked beyond it" in owed


# --- the count the guards read -------------------------------------------------------------------


def test_the_engaged_count_is_a_reading_the_docking_latches_point_can_give(world, tmp_path):
    """`structure.docking_latches` is a count over a map, so it had no reading. It reads its own
    count state now: twelve on the hard-docked stack, none once the ring is cocked for undocking."""
    script = [(1, "set_docking_latch", {"interface": "docking_interface", "latch": "all", "state": "release"})]
    trace = run(world, tmp_path, script, 5, ["latches_engaged"])
    assert trace[0]["latches_engaged"] == 12
    assert trace[-1]["latches_engaged"] == 0
    values = plant.initial_values(world)
    after = plant.step(world, values, plant.tick_seconds(world), [])
    assert plant.point_reading(world, "structure.docking_latches", after) == 12


def test_the_seal_count_is_one_figure_in_two_places(world):
    spec = state(world, "latches_engaged").spec
    assert spec["seal_threshold"] == state(world, "structural_leak_g_s").spec["seal_min_engaged"] == 3
    assert spec["burn_threshold"] == 9
