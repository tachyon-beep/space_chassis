"""Comms rules and the quiet-coast task model (`docs/vehicle-completion/09-quiet-coast-episode.md` §1).

The recorder is a stock of bits, `play_recorder` drains it at the published 51.2 kbit/s while the
link is ok, and every bit it loses lands in the private `delivered_bits`. Both conservation and the
rate are asserted through the real step loop. The task volume is a **scenario initial** (ADR 0003
item 7), so every run here loads it through the overlay from a fixture file. The volume chosen
below is arbitrary.
"""

from __future__ import annotations

import importlib.util
import math
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


# ------------------------------------------------------------------------------------------------
# The occultation (`state blackout`, `rules.py:occulted`): computed from the orbit the plant already
# propagates, and the term `link_ok` gates playback on.
# ------------------------------------------------------------------------------------------------


def _comms_rules():
    spec = importlib.util.spec_from_file_location(
        "comms_rules_under_test", VEHICLE / "domains/comms/rules.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _state(world, state_id):
    return next(s for s in world.states if s.id == state_id)


def _moon_radius_m(world) -> float:
    return float(_state(world, "blackout").spec["moon_radius_m"])


def test_the_moon_radius_the_occultation_uses_is_the_one_the_trajectory_uses(world):
    """Four declarations of one radius: the two rule parameters, the environment row the
    trajectory's flyby check reads, and the figure `mission.yaml#comms_blackout` derives its
    half-angle from. A rule parameter is a literal on its state, so this is what joins it."""
    vehicle = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
    mission = yaml.safe_load((VEHICLE / "mission.yaml").read_text())
    environment = {row["id"]: row["value"] for row in vehicle["environment"]}
    expected = float(environment["moon_mean_radius_km"]) * 1e3
    assert _moon_radius_m(world) == expected
    assert float(_state(world, "link_ok").spec["moon_radius_m"]) == expected
    assert float(mission["comms_blackout"]["moon_radius_km"]) * 1e3 == expected


def test_blackout_is_a_registered_rule_and_reads_clear_near_the_earth(world):
    assert "blackout" in world.rules
    values = plant.initial_values(world)
    for _ in range(5):
        gaps: list = []
        values = plant.step(world, values, DT, gaps=gaps)
        assert values["blackout"] == "clear"
        assert not [g for g in gaps if g.state.id in {"blackout", "link_ok"}]


def test_the_free_return_passes_behind_the_moon_for_the_last_half_hour_of_the_coast(world):
    """The declared start flown under both bodies' gravity, sampled every 30 s through the rule's
    own geometry: exactly one occultation on the way out, at closest approach (MET 72.78-73.23 h,
    27 minutes), which is where Apollo's lunar-orbit insertion burns were made, out of contact.

    It is also a disagreement the round records rather than resolves: `mission.yaml#comms_blackout`
    lists `translunar_coast` as not affected, and the arrival is in that phase (it ends at 73.0 h).
    That block budgets a circular 100 km orbit per phase, which cannot see a flyby."""
    import trajectory

    rules = _comms_rules()
    vehicle, mission = trajectory.load(VEHICLE)
    gravity = trajectory.Gravity.from_vehicle(vehicle)
    r, v = trajectory.declared_start(mission)
    mr, mv = trajectory.moon_at_met0(vehicle, mission)
    radius = _moon_radius_m(world)
    step = 30.0
    t, previous, edges = 0.0, False, []
    while t < 80 * 3600.0:
        hidden = rules.occulted(r, mr, radius)
        assert hidden is not None
        if hidden != previous:
            edges.append(t)
            previous = hidden
        r, v, mr, mv = trajectory.rk4(gravity, r, v, mr, mv, step)
        t += step
    assert len(edges) == 2, [e / 3600 for e in edges]
    loss, acquisition = edges
    assert 72.5 * 3600 < loss < 73.0 * 3600
    assert 73.0 * 3600 < acquisition < 73.5 * 3600
    assert 25 * 60 <= acquisition - loss <= 30 * 60


def test_a_100_km_circular_lunar_orbit_is_occulted_for_the_fraction_mission_yaml_derives(world):
    """`mission.yaml#comms_blackout` derives 39.5 % of a revolution from `arcsin(R / r)` with the
    Earth at infinity. The rule puts the Earth at its real distance, which narrows the shadow by the
    angle the orbit subtends from the Earth; at 100 km that is under a tenth of a percent."""
    rules = _comms_rules()
    mission = yaml.safe_load((VEHICLE / "mission.yaml").read_text())
    block = mission["comms_blackout"]
    radius = _moon_radius_m(world)
    orbit = radius + float(block["orbit"]["altitude_km"]) * 1e3
    moon = [384_400e3, 0.0, 0.0]
    samples = 36_000
    hidden = 0
    for k in range(samples):
        angle = 2 * math.pi * k / samples
        position = [moon[0] + orbit * math.cos(angle), orbit * math.sin(angle), 0.0]
        hidden += bool(rules.occulted(position, moon, radius))
    fraction = hidden / samples
    assert fraction == pytest.approx(float(block["fraction_of_revolution"]), abs=0.002)
    half_angle = math.degrees(math.asin(radius / orbit))
    assert half_angle == pytest.approx(float(block["half_angle_deg"]), abs=0.05)


def _behind_the_moon(world) -> dict:
    """An `orbital_state` 100 km above the Moon's far side, on the Earth-Moon line."""
    start = plant.initial_values(world)["orbital_state"]
    moon = list(start["moon_position_m"])
    distance = math.sqrt(sum(x * x for x in moon))
    outward = [x / distance for x in moon]
    altitude = _moon_radius_m(world) + 100e3
    return {
        **start,
        "position_m": [moon[i] + altitude * outward[i] for i in range(3)],
        "velocity_m_s": list(start["moon_velocity_m_s"]),
    }


def test_behind_the_moon_the_link_is_down_and_playback_stops(world, tmp_path):
    """The crew-facing consequence: a vehicle whose link is otherwise configured and playing loses
    the ground at occultation, and the recorder keeps what it could not send."""
    script = [*link_up_at(0), (1, "play_recorder", {"state": "on"})]
    scen = scenario(world, tmp_path, script, initial={"orbital_state": _behind_the_moon(world)})
    final, trace = run(world, scen, 20)
    assert all(row["link_ok"] is False for row in trace)
    assert all(row["rate"] == 0.0 for row in trace)
    assert final["blackout"] == "occulted"
    assert final["recorder"] == VOLUME and final["delivered_bits"] == 0


def test_inside_the_moon_s_radius_the_occultation_is_a_named_gap_not_a_value(world):
    rules = _comms_rules()
    assert rules.occulted([1.0, 0.0, 0.0], [0.0, 0.0, 0.0], _moon_radius_m(world)) is None


# ------------------------------------------------------------------------------------------------
# The one-way light time (`state light_time_s`, `comm.light_time_s`): the vehicle's range over c.
# ------------------------------------------------------------------------------------------------

C = 299_792_458.0


def test_the_light_time_is_the_range_over_c_through_the_step_loop(world):
    values = plant.initial_values(world)
    for _ in range(3):
        values = plant.step(world, values, DT)
        r = values["orbital_state"]["position_m"]
        assert values["light_time_s"] == pytest.approx(math.sqrt(sum(x * x for x in r)) / C)
    # MET 0 is 6,563 km from the Earth's centre: hundredths of a second, not the 1.3 s constant
    # this state replaced.
    assert 0.021 < values["light_time_s"] < 0.023


def test_the_light_time_grows_from_hundredths_of_a_second_to_1_32_s_at_arrival(world):
    import trajectory

    rules = _comms_rules()
    vehicle, mission = trajectory.load(VEHICLE)
    gravity = trajectory.Gravity.from_vehicle(vehicle)
    r, v = trajectory.declared_start(mission)
    mr, mv = trajectory.moon_at_met0(vehicle, mission)
    params = {"speed_of_light_m_s": _state(world, "light_time_s").spec["speed_of_light_m_s"]}
    samples = {}
    t, step = 0.0, 60.0
    while t <= 73 * 3600.0:
        if t in (2400.0, 24 * 3600.0, 73 * 3600.0):
            samples[t] = rules.light_time_s({"orbital_state": {"position_m": r}}, params, step)
        r, v, mr, mv = trajectory.rk4(gravity, r, v, mr, mv, step)
        t += step
    assert samples[2400.0] == pytest.approx(0.058, abs=0.002)
    assert samples[24 * 3600.0] == pytest.approx(0.70, abs=0.01)
    assert samples[73 * 3600.0] == pytest.approx(1.32, abs=0.01)


def test_the_light_time_is_published_and_the_unread_constant_is_gone(world):
    assert world.points["comm.light_time_s"]["from"] == "light_time_s"
    vehicle = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
    assert "earth_moon_light_time_s" not in {row["id"] for row in vehicle["environment"]}


# ------------------------------------------------------------------------------------------------
# The link budget (`state link_snr`, `comm.snr_db`): Bellcomm's lunar-range prediction, moved by
# range, the power amplifier and the high-gain antenna's pointing loss.
# ------------------------------------------------------------------------------------------------


def _snr(
    world,
    *,
    antenna="high_gain",
    amplifier="on",
    rate=51_200,
    mode=None,
    range_m=None,
    pointing_deg=0.0,
    behind=False,
):
    """`link_snr` called directly on a hand-built snapshot, with the state's own declaration."""
    spec = _state(world, "link_snr").spec
    distance = float(spec["reference_range_m"]) if range_m is None else range_m
    moon = [384_400e3, 0.0, 0.0]
    if behind:
        position = [moon[0] + _moon_radius_m(world) + 100e3, 0.0, 0.0]
    else:
        position = [-distance, 0.0, 0.0]  # the Moon on the far side of the Earth: never occulted
    inputs = {
        "comm_mode": mode or ("sband_high" if rate == 51_200 else "sband_low"),
        "orbital_state": {"position_m": position, "moon_position_m": moon},
        "antenna_selection": antenna,
        "transmitter_on": amplifier,
        "antenna_pointing": pointing_deg,
        "telemetry_rate": rate,
    }
    params = plant.RuleParams(spec, "domains/comms/components.yaml:state link_snr")
    return _comms_rules().link_snr(inputs, params, DT), params


def test_at_lunar_range_the_budget_reproduces_bellcomm_s_margins(world):
    """CR-125670 Table II, 85-ft station: on the high-gain antenna high-rate telemetry closes with
    the amplifier on and fails with it off; on an omni only the low rate closes. The SNR is the
    12.5 dB a 1e-6 bit-error rate needs plus Bellcomm's margin."""
    cases = [
        ({"antenna": "high_gain", "amplifier": "on", "rate": 51_200}, 24.4),
        ({"antenna": "high_gain", "amplifier": "off", "rate": 51_200}, 4.4),
        ({"antenna": "omni_a", "amplifier": "on", "rate": 51_200}, 2.0),
        ({"antenna": "omni_b", "amplifier": "on", "rate": 1_600}, 13.0),
    ]
    for kwargs, expected in cases:
        snr, _ = _snr(world, **kwargs)
        assert snr == pytest.approx(expected, abs=1e-9), kwargs
    # And against apollo's two thresholds: healthy, degraded (below 8), lost (below 3).
    assert _snr(world, amplifier="off")[0] < 8 and _snr(world, antenna="omni_a")[0] < 3


def test_half_the_range_is_six_db_more(world):
    spec = _state(world, "link_snr").spec
    far, _ = _snr(world)
    near, _ = _snr(world, range_m=float(spec["reference_range_m"]) / 2)
    assert near - far == pytest.approx(20 * math.log10(2), abs=1e-9)


def test_the_pointing_loss_has_the_slope_e_geom_link_declares(world):
    """The rule's quadratic pattern and the edge's sensitivity are one relation: at the 2 deg
    operating point the derivative of the loss is the edge's dB per deg."""
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    edge = next(e for e in coupling["edges"] if e["id"] == "E-GEOM-LINK")
    h = 1e-4
    slope = (_snr(world, pointing_deg=2 + h)[0] - _snr(world, pointing_deg=2 - h)[0]) / (2 * h)
    assert slope == pytest.approx(float(edge["sensitivity"]["value"]), abs=0.005)
    # On an omni the high-gain antenna's pointing does not enter.
    assert _snr(world, antenna="omni_a", pointing_deg=5)[0] == _snr(world, antenna="omni_a")[0]


def test_no_carrier_is_a_named_gap_rather_than_a_low_snr(world):
    """Behind the Moon, in VHF or with the S-band off, there is no carrier to measure: a value
    there would be an SNR alarm every revolution, which the domain's first rule forbids."""
    for kwargs, words in (
        ({"behind": True}, "behind the Moon"),
        ({"mode": "vhf"}, "`vhf`"),
        ({"mode": "none"}, "`none`"),
        ({"antenna": "sband_steerable"}, "sband_steerable"),
    ):
        snr, params = _snr(world, **kwargs)
        assert snr is None, kwargs
        assert words in params.why_none, params.why_none


def test_the_link_budget_s_copies_agree_with_their_sources(world):
    vehicle = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
    hga = next(a for a in vehicle["comms"]["antennas"] if a["id"] == "high_gain")
    narrow = next(b for b in hga["beams"] if b["id"] == "narrow")
    spec = _state(world, "link_snr").spec
    assert float(spec["hga_beamwidth_deg"]) == float(narrow["beamwidth_deg"])
    assert float(spec["moon_radius_m"]) == _moon_radius_m(world)
    assert float(spec["reference_range_m"]) == 215_000 * 1_852


def test_through_the_step_loop_the_omni_budget_closes_and_the_hga_waits_on_pointing(
    world, tmp_path
):
    """On an omni the budget needs nothing the vehicle lacks; on the high-gain antenna it needs the
    pointing error, which no rule computes yet, and the gap names it."""

    def first_tick(initial):
        seen = []
        scen = scenario(world, tmp_path, [], initial=initial)
        plant.run_scenario(
            world, scen, 1, on_tick=lambda tick, values, ledger, gaps: seen.append((values, gaps))
        )
        return seen[0]

    values, gaps = first_tick({"antenna_selection": "omni_a"})
    assert not [g for g in gaps if g.state.id == "link_snr"]
    # MET 0, 6,563 km, amplifier off, low rate: 28.7 dB.
    assert values["link_snr"] == pytest.approx(28.7, abs=0.1)

    values, gaps = first_tick({})
    snr_gaps = [g for g in gaps if g.state.id == "link_snr"]
    assert snr_gaps and "antenna_pointing" in snr_gaps[0].owed
