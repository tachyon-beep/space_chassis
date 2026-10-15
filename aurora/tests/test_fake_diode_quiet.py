"""The fixture's quiet rule (#39 tier 1): a console with nothing to claim is not rewritten.

`contract/fake_diode.py` is the window the smoke stack mounts, and `docs/diode-contract.md` §2.2 now
says the vehicle rewrites the console only when it holds something to claim. The fixture models the
same contract with the same test as the vehicle's `Window.claim` (`vehicle/tools/console.py`,
`quiet`): an object whose `commands` is exactly `[]` and that already shows the map (its own
`variables` object, which is adopted, or no `variables` key while no map is held) is left as it is;
everything else is rewritten to show the held map. The last test here holds the two to one answer,
shape by shape, by driving both.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import fake_diode
import pytest

VEHICLE = Path(__file__).resolve().parents[2] / "vehicle"


@pytest.fixture
def side(tmp_path, monkeypatch):
    monkeypatch.setattr(fake_diode, "DIODE_DIR", tmp_path)
    return fake_diode.AgentSide("otter")


def write(side, payload) -> None:
    side.console.write_text(json.dumps(payload), encoding="utf-8")


def stamp(path: Path) -> tuple[int, int]:
    status = os.stat(path)
    return status.st_ino, status.st_mtime_ns


def test_a_console_with_nothing_to_claim_is_never_rewritten_so_a_batch_put_in_place_during_its_read_is_not_erased(
    side, monkeypatch
):
    """The fixture's copy of the vehicle's #39 regression test.

    Quiet consumes leave the console's inode and mtime alone. A batch that lands after a quiet read
    (written in place, or renamed over the file the way the contract asks) is still there after that
    consume and is claimed, whole, by the next one.
    """
    side.consume()  # the seed's `help`
    before = stamp(side.console)
    for _ in range(3):
        assert side.consume() == ([], {})
    assert stamp(side.console) == before

    real_read = fake_diode.read_bounded
    batch = ["help", "zzz_not_a_verb"]

    def in_place() -> None:
        write(side, {"commands": batch})

    def renamed_over() -> None:
        incoming = side.root / ".agent.console.json.tmp"
        incoming.write_text(json.dumps({"commands": batch}), encoding="utf-8")
        os.replace(incoming, side.console)

    for land in (in_place, renamed_over):
        armed = [True]

        def lands_after_the_read(path, limit=2_000_000, land=land, armed=armed):
            text = real_read(path, limit)
            if armed[0] and path == side.console:
                armed[0] = False
                land()
            return text

        monkeypatch.setattr(fake_diode, "read_bounded", lands_after_the_read)
        assert side.consume() == ([], {}), land.__name__
        assert armed == [False], land.__name__
        assert json.loads(side.console.read_text())["commands"] == batch, land.__name__
        commands, _ = side.consume()
        assert commands == batch, land.__name__
        assert json.loads(side.console.read_text()) == {"commands": [], "variables": {}}
        monkeypatch.setattr(fake_diode, "read_bounded", real_read)


def test_what_counts_as_nothing_to_claim_is_decided_by_shape_alone_and_the_console_always_shows_the_map(
    side,
):
    """The rule shape by shape, as the vehicle's test states it."""
    side.consume()
    # A map-only console: adopted (replace, not merge), and the agent's file left in place.
    write(side, {"commands": [], "variables": {"enable_request": True, "probe_marker": True}})
    written = stamp(side.console)
    assert side.consume() == ([], {"enable_request": True, "probe_marker": True})
    assert stamp(side.console) == written
    assert side.held == {"enable_request": True, "probe_marker": True} and side.variables_known
    # No `variables` while a map is held: rewritten once to show it, then quiet.
    write(side, {"commands": []})
    bare = stamp(side.console)
    side.consume()
    shown = json.loads(side.console.read_text())
    assert shown == {"commands": [], "variables": {"enable_request": True, "probe_marker": True}}
    assert stamp(side.console) != bare
    settled = stamp(side.console)
    side.consume()
    assert stamp(side.console) == settled
    # The same bare console while no map is held (a fixture started on a console it did not write).
    side.held, side.variables_known = {}, False
    write(side, {"commands": []})
    bare = stamp(side.console)
    assert side.consume() == ([], {})
    assert stamp(side.console) == bare
    assert json.loads(side.console.read_text()) == {"commands": []}
    # Shapes that are not "nothing to claim": each is rewritten to show the held map, none raises.
    side.held, side.variables_known = {"kept": 1}, True
    for shape in (
        {"variables": {"kept": 1}},
        {"commands": [], "variables": [1]},
        {"commands": [], "variables": None},
        {"commands": {}, "variables": {"kept": 1}},
        {"commands": False, "variables": {"kept": 1}},
        [],
        "not an object",
    ):
        write(side, shape)
        before = stamp(side.console)
        commands, variables = side.consume()
        assert commands == [] and variables == {"kept": 1}, shape
        assert stamp(side.console) != before, shape
        assert json.loads(side.console.read_text()) == {"commands": [], "variables": {"kept": 1}}
    # Not JSON at all, and a nest deep enough to make the decoder raise: claimed, not raised.
    for text in ("{half-written", "[" * 100_000):
        side.console.write_text(text, encoding="utf-8")
        assert side.consume() == ([], {"kept": 1})
        assert json.loads(side.console.read_text()) == {"commands": [], "variables": {"kept": 1}}


def test_a_fixture_started_on_a_console_left_in_place_adopts_its_map(tmp_path, monkeypatch):
    """A quiet pass leaves the agent's own console in place; a fixture started on it takes its map."""
    monkeypatch.setattr(fake_diode, "DIODE_DIR", tmp_path)
    (tmp_path / "otter").mkdir()
    console = tmp_path / "otter" / "console.json"
    console.write_text(json.dumps({"commands": [], "variables": {"enable_request": True}}))
    left = stamp(console)
    side = fake_diode.AgentSide("otter")
    assert not side.variables_known
    assert side.consume() == ([], {"enable_request": True})
    assert stamp(console) == left
    assert side.variables() == {"enable_request": True}


SHAPES = (
    {"commands": [], "variables": {}},
    {"commands": [], "variables": {"a": True}},
    {"commands": [], "variables": {"a": 0, "b": False}},
    {"commands": []},
    {"commands": ["x"]},
    {"commands": ["x"], "variables": {"a": True}},
    {"commands": [42], "variables": {}},
    {"commands": [], "variables": [1]},
    {"commands": [], "variables": None},
    {"commands": [], "variables": "map"},
    {"commands": {}, "variables": {}},
    {"commands": False, "variables": {}},
    {"commands": None},
    {"commands": 0, "variables": {}},
    {"variables": {}},
    {},
    [],
    "text",
    0,
)


def test_the_fixture_and_the_vehicle_agree_on_what_is_nothing_to_claim(tmp_path, side):
    """Parity, not a copy of the rule: both windows are driven over the same shapes.

    For each shape, with the window holding a map and with it holding none, one vehicle cycle (whose
    claim is `Window.claim`) and one fixture `consume` must agree on whether the console is
    rewritten, and on the map each then holds.
    The vehicle is imported from `vehicle/tools`, as its own referee does; nothing in it is changed.
    """
    tools = str(VEHICLE / "tools")
    if tools not in sys.path:
        sys.path.append(tools)
    import console as vehicle_console
    import plant

    world = plant.load_world(VEHICLE)
    executive = vehicle_console.Executive(world, tmp_path / "diode", phase="translunar_coast")
    window = executive.attach("alpha")
    alpha = tmp_path / "diode" / "alpha" / "console.json"
    disagreements, outcomes = [], set()
    for known in (True, False):
        for shape in SHAPES:
            held = {"kept": 1} if known else {}
            window.variables, window.variables_known, window._honoured = dict(held), known, None
            side.held, side.variables_known = dict(held), known
            alpha.write_text(json.dumps(shape), encoding="utf-8")
            write(side, shape)
            vehicle_before, fixture_before = stamp(alpha), stamp(side.console)
            executive.cycle()
            side.consume()
            vehicle_rewrote = stamp(alpha) != vehicle_before
            fixture_rewrote = stamp(side.console) != fixture_before
            outcomes.add(vehicle_rewrote)
            if vehicle_rewrote != fixture_rewrote:
                disagreements.append((known, shape, vehicle_rewrote, fixture_rewrote))
            assert window.variables_known == side.variables_known, (known, shape)
            assert window.variables == side.held, (known, shape)
            if vehicle_rewrote:
                assert json.loads(alpha.read_text()) == json.loads(side.console.read_text()), shape
    failures = list(executive.failures)
    executive.close()
    assert disagreements == []
    assert outcomes == {True, False}, "the shapes never reached one side of the rule"
    assert failures == []
