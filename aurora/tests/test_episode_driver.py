"""The episode driver (scripts/episode_driver.py) against the contract's fixture, contract/fake_diode.py.

The fixture is the window: it takes the console the way the contract says (§2.2) and publishes a
state.json. Its state carries no mission clock, so each test publishes `executive.tick` the way the
vehicle's window does, and the fixture's own `consume` is the take. The verbs here are placeholders:
the driver names none and models nothing.
"""

from __future__ import annotations

import json
import os

import episode_driver
import fake_diode
import pytest

POLICY = {
    "policy": "x",
    "tick_hz": 50,
    "duration_ticks": 100,
    "commands": [
        {"tick": 0, "line": "first a=1"},
        {"tick": 0, "line": "second b=2"},
        {"tick": 10, "line": "third c=3"},
        {"tick": 60, "line": "fourth"},
    ],
}


@pytest.fixture
def side(tmp_path, monkeypatch):
    monkeypatch.setattr(fake_diode, "DIODE_DIR", tmp_path)
    side = fake_diode.AgentSide("otter")
    side.consume()  # the fixture seeds `help`; take it so the console starts empty
    return side


def publish_tick(side, tick: int) -> None:
    side.publish(fake_diode.HOURLY_MAX)
    state = json.loads(side.state_path.read_text())
    state["executive"] = {"world_id": "w", "tick": tick}
    fake_diode.write_atomic(side.state_path, json.dumps(state))


def driver(side, **kwargs) -> episode_driver.Driver:
    return episode_driver.Driver(side.root, episode_driver.Policy.from_document(POLICY), **kwargs)


def test_commands_are_submitted_when_the_published_tick_reaches_them_and_taken_in_order(side):
    d = driver(side)
    taken = []
    for tick in range(0, 101, 5):
        publish_tick(side, tick)
        d.step()
        commands, _ = side.consume()
        taken.append((tick, commands))
    submitted = [(tick, c) for tick, cs in taken for c in cs]
    assert submitted == [
        (0, "first a=1"),
        (0, "second b=2"),
        (10, "third c=3"),
        (60, "fourth"),
    ]
    assert d.done()


def test_nothing_is_written_before_the_window_publishes_a_tick(side):
    d = driver(side)
    side.state_path.unlink(missing_ok=True)
    assert d.step() == 0
    assert json.loads(side.console.read_text())["commands"] == []


def test_a_batch_not_yet_taken_is_never_replaced(side):
    d = driver(side)
    publish_tick(side, 0)
    assert d.step() == 2
    publish_tick(side, 20)
    # The vehicle has not taken the first batch: the third command waits rather than superseding it.
    assert d.step() == 0
    assert json.loads(side.console.read_text())["commands"] == ["first a=1", "second b=2"]
    commands, _ = side.consume()
    assert commands == ["first a=1", "second b=2"]
    assert d.step() == 1
    assert side.consume()[0] == ["third c=3"]


def test_an_absent_console_is_free_and_the_write_is_whole(side, monkeypatch):
    d = driver(side)
    publish_tick(side, 0)
    side.console.unlink()  # the vehicle renamed it aside to take it
    renames = []
    real = os.replace
    monkeypatch.setattr(
        os, "replace", lambda a, b: (renames.append((str(a), str(b))), real(a, b))[1]
    )
    assert d.step() == 2
    assert renames and renames[-1][1] == str(side.console), "the console is renamed into place"
    assert all(".tmp" in src for src, _ in renames)
    assert not list(side.root.glob(".console.json.*.tmp")), "no temporary is left behind"


def test_the_variables_the_console_shows_are_written_back(side):
    fake_diode.write_atomic(side.console, json.dumps({"commands": [], "variables": {"g": True}}))
    side.consume()
    d = driver(side)
    publish_tick(side, 0)
    d.step()
    assert json.loads(side.console.read_text()) == {
        "commands": ["first a=1", "second b=2"],
        "variables": {"g": True},
    }
    assert side.consume() == (["first a=1", "second b=2"], {"g": True})


def test_a_console_that_is_a_link_is_waited_out(side, tmp_path):
    d = driver(side)
    publish_tick(side, 0)
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text(json.dumps({"commands": []}))
    side.console.unlink()
    side.console.symlink_to(elsewhere)
    assert d.step() == 0
    assert json.loads(elsewhere.read_text()) == {"commands": []}, "the link's target is untouched"


def test_a_long_due_list_goes_in_batches(side):
    many = dict(POLICY, commands=[{"tick": 0, "line": f"v{i}"} for i in range(5)])
    d = episode_driver.Driver(side.root, episode_driver.Policy.from_document(many), max_batch=2)
    publish_tick(side, 0)
    batches = []
    for _ in range(4):
        d.step()
        batches.append(side.consume()[0])
    assert batches == [["v0", "v1"], ["v2", "v3"], ["v4"], []]


def test_run_finishes_when_everything_is_sent_and_the_window_reaches_the_end(side):
    d = driver(side)
    now = [0.0]
    ticks = iter(range(0, 200, 10))

    def sleep(seconds):
        now[0] += seconds
        side.consume()
        publish_tick(side, next(ticks))

    publish_tick(side, 0)
    assert d.run(poll_seconds=1.0, timeout=100.0, clock=lambda: now[0], sleep=sleep)
    assert d.done()
    assert [entry["lines"] for entry in d.log][-1] == ["fourth"]


def test_run_times_out_when_the_window_never_moves(side):
    d = driver(side)
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds

    publish_tick(side, 0)
    assert not d.run(poll_seconds=1.0, timeout=5.0, clock=lambda: now[0], sleep=sleep)


@pytest.mark.parametrize(
    "commands",
    [
        [{"tick": -1, "line": "x"}],
        [{"tick": True, "line": "x"}],
        [{"tick": 0, "line": ""}],
        [{"tick": 0, "line": "two\nlines"}],
    ],
)
def test_a_malformed_policy_is_refused(commands):
    with pytest.raises(ValueError):
        episode_driver.Policy.from_document(dict(POLICY, commands=commands))
