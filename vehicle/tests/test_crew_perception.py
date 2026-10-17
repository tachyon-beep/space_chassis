"""The perception function (`tools/crew_perception.py`): what a crew member could honestly say.

Run against a real frame at MET 0, so the channels a panel shows are the ones the plant publishes.
The property under test is the bound: nothing reaches the composer that the person's position does
not display, at a precision no finer than the panel's, and the seeded wrongness is drawn the same way
twice.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import crew_perception  # noqa: E402
import plant  # noqa: E402

SEATS = {"commander": "csm_commander", "lm_pilot": "csm_lower_equipment_bay", "csm_pilot": "csm_navigator"}
AWAKE = dict.fromkeys(SEATS, "available")


@pytest.fixture(scope="module")
def frame() -> dict:
    world = plant.load_world(VEHICLE)
    emitted = plant.emit_frame(
        world,
        tick=0,
        seq=0,
        boot_id="0" * 32,
        met_s=0.0,
        sensor_time_s=0.0,
        values=plant.initial_values(world),
        quality={},
        phase="translunar_coast",
        vehicle="csm",
        state_revision=0,
    )
    return dict(emitted["values"])


@pytest.fixture(scope="module")
def contract():
    return crew_perception.load_contract(VEHICLE)


def ask(frame, contract, crew_id="commander", location=SEATS, availability=AWAKE, seed=1, index=0):
    display, probabilities = contract
    return crew_perception.perceive(frame, crew_id, location, availability, display, probabilities, seed, index)


def test_the_commander_reads_the_main_display_and_nothing_a_position_elsewhere_shows(frame, contract):
    """Every readout is a channel this position's panels list, and the CSM's cabin pressure is among
    them while the LM's is not: the bound is the contract, not whatever the frame happens to carry."""
    display, _ = contract
    out = ask(frame, contract)["perceived"]
    position = next(p for p in display["positions"] if p["id"] == "csm_commander")
    allowed = [crew_perception._channel_pattern(s["channel"]) for p in position["panels"] for s in p["shows"]]
    assert out["readouts"], "the commander's panels show channels the MET-0 frame publishes"
    for row in out["readouts"]:
        assert any(pattern.match(row["channel"]) for pattern in allowed), row["channel"]
    channels = {row["channel"] for row in out["readouts"]}
    assert "eclss.lm_cabin_pressure_psia" not in channels
    assert "eclss.lm_cabin_pressure_psia" in out["cannot_see"]


def test_the_same_person_in_the_tunnel_reads_nothing_at_all(frame, contract):
    """Sending the LM pilot to the tunnel is the cost the location rule makes real: the tunnel has no
    panels, so every readout the bay showed is gone and only the felt sense of pressure is left."""
    out = ask(frame, contract, "lm_pilot", {**SEATS, "lm_pilot": "tunnel"})["perceived"]
    assert out["position"] == "tunnel" and out["readouts"] == []
    assert any("felt" in line for line in out["human_channels"])


def test_a_reading_is_never_finer_than_the_panel_shows_it(frame, contract):
    for crew_id in SEATS:
        for row in ask(frame, contract, crew_id, seed=7)["perceived"]["readouts"]:
            precision = row["displayed_precision"]
            if precision == "exact" or not isinstance(row["value"], (int, float)) or isinstance(row["value"], bool):
                continue
            assert abs(row["value"] / precision - round(row["value"] / precision)) < 1e-9, row


def test_an_incapacitated_person_does_not_answer_and_a_sleeping_one_is_woken(frame, contract):
    assert ask(frame, contract, availability={**AWAKE, "commander": "incapacitated"})["perceived"]["answers"] is False
    woken = ask(frame, contract, availability={**AWAKE, "commander": "resting"})["perceived"]
    assert woken["answers"] is True and woken["woken"] is True


def test_the_wrongness_is_seeded_so_a_replay_asks_the_same_question_and_gets_the_same_answer(frame, contract):
    first = [ask(frame, contract, seed=3, index=i) for i in range(400)]
    again = [ask(frame, contract, seed=3, index=i) for i in range(400)]
    assert first == again
    drawn = [row["audit"]["wrongness"] for row in first if row["audit"]["wrongness"]]
    # 0.045 per answer over 400 answers: some, and far from all.
    assert 2 <= len(drawn) <= 60
    assert set(drawn) <= {"misheard", "misattributed", "forgot"}


def test_a_misheard_number_is_a_plausible_misreading_of_the_same_digits(contract):
    import random

    for value in (850, 5.0, 28.5, 1234):
        heard = crew_perception._misheard(value, random.Random(0))
        assert sorted(str(heard).replace(".0", "")) == sorted(str(value).replace(".0", "")) or heard == value


def test_the_audit_is_the_only_place_the_perturbation_is_named(frame, contract):
    for index in range(400):
        out = ask(frame, contract, seed=11, index=index)
        assert "wrongness" not in out["perceived"]
        if out["audit"]["wrongness"]:
            assert out["audit"]["readout"]["channel"]
            return
    pytest.fail("no wrongness drawn in 400 asks at 0.045 each")
