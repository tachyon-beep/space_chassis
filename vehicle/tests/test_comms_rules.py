"""Comms rules and the quiet-coast task model (`docs/vehicle-completion/09-quiet-coast-episode.md` §1).

The recorder is a stock of bits, `play_recorder` drains it at the published 51.2 kbit/s while the
link is ok, and every bit it loses lands in the private `delivered_bits`. Both conservation and the
rate are asserted through the real step loop. The task volume is a **scenario initial** (ADR 0003
item 7), so every run here loads it through the overlay from a fixture file. The volume chosen
below is arbitrary.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402

DT = 0.02
RATE = 51_200  # bit/s, `playback_rate.play_rate_bps`
PER_TICK = 1_024  # 51,200 bit/s x 20 ms, exactly
VOLUME = 10_000_000  # bits on tape at MET 0: a fixture's task volume, not a vehicle figure

LINK_UP = [
    ("set_comm_mode", {"mode": "sband_high"}),
    ("select_antenna", {"antenna": "high_gain"}),
    ("set_telemetry_profile", {"profile": "high"}),
    ("set_power_amplifier", {"state": "on"}),
]


@pytest.fixture(scope="module")
def world() -> plant.World:
    return plant.load_world(VEHICLE)


def scenario(world, tmp_path, script, initial=None) -> plant.Scenario:
    rows = []
    for tick, verb, arguments in script:
        rows.append({"tick": tick, "verb": verb, "arguments": arguments})
    document = {
        "scenario": "comms_fixture",
        "initial": {"recorder": VOLUME, **(initial or {})},
        "script": rows,
    }
    path = tmp_path / "comms_fixture.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    return plant.load_scenario(world, path)


def run(world, scen, ticks):
    trace: list[dict] = []

    def on_tick(tick, values, ledger, gaps):
        trace.append(
            {
                "tick": tick,
                "recorder": values["recorder"],
                "delivered": values["delivered_bits"],
                "rate": values["playback_rate"],
                "link_ok": values["link_ok"],
                "transmitter_on": values["transmitter_on"],
                "tx_power": values["tx_power"],
                "amp_dissipation_w": values["amp_dissipation_w"],
                "ledger": ledger,
            }
        )

    final = plant.run_scenario(world, scen, ticks, on_tick=on_tick)
    return final, trace


def link_up_at(tick: int) -> list[tuple[int, str, dict]]:
    return [(tick, verb, arguments) for verb, arguments in LINK_UP]


def test_the_recorder_s_met0_volume_is_a_scenario_initial(world, tmp_path):
    assert plant.initial_values(world)["recorder"] == 0
    scen = scenario(world, tmp_path, [])
    start = plant.initial_values(world, scen)
    assert start["recorder"] == start["data_recorder"] == VOLUME
    assert start["delivered_bits"] == 0


def test_playback_drains_at_51_2_kbit_s_for_exactly_n_ticks_by_whole_quanta(world, tmp_path):
    play, stop = 2, 52  # play for 50 ticks
    script = [
        *link_up_at(0),
        (play, "play_recorder", {"state": "on"}),
        (stop, "play_recorder", {"state": "off"}),
    ]
    final, trace = run(world, scenario(world, tmp_path, script), 60)

    drained = [VOLUME - row["recorder"] for row in trace]
    steps = [b - a for a, b in zip([0, *drained], drained, strict=False)]
    assert set(steps) == {0, PER_TICK}
    moving = [row["tick"] for row, step in zip(trace, steps, strict=True) if step]
    # The drain reads the rate the tick before it (the recorder advances before `ground_received`),
    # so it follows each command by one tick and lasts exactly as long as the command did.
    assert moving == list(range(play + 1, stop + 1)), moving
    assert len(moving) == stop - play
    assert final["recorder"] == VOLUME - (stop - play) * PER_TICK
    assert final["delivered_bits"] == (stop - play) * PER_TICK
    for row in trace:
        assert isinstance(row["recorder"], int | float) and float(row["recorder"]).is_integer()
        assert row["rate"] == (RATE if play <= row["tick"] < stop else 0.0)


def test_recorder_plus_delivered_is_the_initial_volume_and_the_ledger_balances(world, tmp_path):
    script = [*link_up_at(0), (1, "play_recorder", {"state": "on"})]
    _, trace = run(world, scenario(world, tmp_path, script), 40)
    moved = 0
    for row in trace:
        assert row["recorder"] + row["delivered"] == VOLUME
        plant.assert_conservation(row["ledger"], nontrivial=True)
        transfer = next((t for t in row["ledger"].transfers if t.edge == "E-REC-GND"), None)
        assert transfer is not None
        assert (transfer.source, transfer.target) == ("recorder", "delivered_bits")
        moved += transfer.quanta
    assert moved == trace[-1]["delivered"] > 0


@pytest.mark.parametrize(
    "spoiler",
    [
        ("select_antenna", {"antenna": "omni_a"}),
        ("set_comm_mode", {"mode": "sband_low"}),
        ("set_telemetry_profile", {"profile": "low"}),
        ("set_power_amplifier", {"state": "off"}),
    ],
    ids=["omni", "low_mode", "low_profile", "amplifier_off"],
)
def test_no_drain_unless_the_link_is_ok_and_the_amplifier_is_on(world, tmp_path, spoiler):
    verb, arguments = spoiler
    script = [*link_up_at(0), (0, verb, arguments), (1, "play_recorder", {"state": "on"})]
    final, trace = run(world, scenario(world, tmp_path, script), 30)
    assert all(row["link_ok"] is False for row in trace)
    assert all(row["rate"] == 0.0 for row in trace)
    assert final["recorder"] == VOLUME and final["delivered_bits"] == 0


def test_no_drain_while_the_recorder_is_not_playing(world, tmp_path):
    final, trace = run(world, scenario(world, tmp_path, link_up_at(0)), 30)
    assert all(row["link_ok"] is True for row in trace)
    assert final["recorder"] == VOLUME and final["delivered_bits"] == 0


def test_set_power_amplifier_toggles_transmitter_on_through_the_step_loop(world, tmp_path):
    script = [
        (3, "set_power_amplifier", {"state": "on"}),
        (8, "set_power_amplifier", {"state": "off"}),
    ]
    _, trace = run(world, scenario(world, tmp_path, script), 12)
    states = [row["transmitter_on"] for row in trace]
    assert states == ["off"] * 3 + ["on"] * 5 + ["off"] * 4
    # The draw and the heat follow the switch in the same tick.
    assert [row["tx_power"] for row in trace] == [36.0] * 3 + [108.0] * 5 + [36.0] * 4
    assert trace[4]["amp_dissipation_w"] == pytest.approx(72 - 11.2)
    assert trace[0]["amp_dissipation_w"] == trace[-1]["amp_dissipation_w"] == 0.0


def test_the_old_selects_refusal_is_gone(world):
    after = plant.apply_command(
        world, plant.initial_values(world), "set_power_amplifier", {"state": "on"}
    )
    assert after["transmitter_on"] == "on"


def test_set_comm_mode_select_antenna_and_profile_still_move_their_states(world):
    values = plant.initial_values(world)
    for verb, arguments in LINK_UP:
        values = {**values, **plant.apply_command(world, values, verb, arguments)}
    assert values["comm_mode"] == "sband_high"
    assert values["antenna_selection"] == "high_gain"
    assert values["telemetry_rate"] == 51200


def test_delivered_bits_is_on_no_published_channel(world):
    private = {"delivered_bits", "link_ok", "playback_rate", "ground_received"}
    for channel, row in world.points.items():
        assert str(row.get("from")) not in private, channel
        derivation = row.get("derivation")
        if isinstance(derivation, dict):
            inputs = derivation.get("inputs") or {}
            assert not private & {str(v) for v in inputs.values()}, channel
    assert not any("delivered" in channel for channel in world.points)
    assert not any("delivered" in field for field in world.frame_fields)
    presentation = (VEHICLE / "presentation.yaml").read_text()
    assert "delivered_bits" not in presentation
    not_published = yaml.safe_load((VEHICLE / "domains/comms/points.yaml").read_text())[
        "not_published"
    ]
    assert "comm.delivered_bits" in {row["channel"] for row in not_published}
    # The frame's `values` are built from this registry (`presentation.yaml`), so a state no
    # point reads is a state no frame carries.
