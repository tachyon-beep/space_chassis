"""D5, the domain-rule seam: a rule lives in `domains/<name>/rules.py` and the plant calls it.

`governance/decisions.md` D5 and `plant.md` §2. Power, comms and thermal have real rules for the
quiet coast (ADR 0003), so every rule here is a **fixture** measured against the vehicle without
power's `bus_b_v` rule: a writable copy of the definition with a `rules.py` planted in it,
the way the referee's broken-copy tests plant a broken field. Nothing in a fixture is a claim about
the vehicle; the values are arbitrary and are chosen only to be recognisable.
"""

from __future__ import annotations

import itertools
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import plant  # noqa: E402

_COUNTER = itertools.count()

# bus_b_v is an `algebraic` state power owns and the plant refuses with "its rule is not in the
# configuration": the shape of state a rule is for.
STATE = "bus_b_v"
ANCHOR = "  - id: bus_b_v\n    method: algebraic\n"


def definition(tmp_path: Path, rules: str | None = None, extra_spec: str = "") -> Path:
    """A writable copy of the definition (as `test_vehicle_config.copy_definition` makes one), with
    `rules` written to `domains/power/rules.py` and `extra_spec` appended to `bus_b_v`'s spec."""
    destination = tmp_path / f"seam{next(_COUNTER)}"
    destination.mkdir(parents=True)
    for name in (*plant.CORPUS_TOP_LEVEL, "README.md", "plant.md"):
        shutil.copy(VEHICLE / name, destination / name)
    (destination / "tools").mkdir()
    for name in ("faults.py", "console.py", "checkpoint.py"):
        shutil.copy(VEHICLE / "tools" / name, destination / "tools" / name)
    shutil.copytree(VEHICLE / "domains", destination / "domains")
    if extra_spec:
        path = destination / "domains" / "power" / "components.yaml"
        text = path.read_text()
        assert text.count(ANCHOR) == 1
        path.write_text(text.replace(ANCHOR, ANCHOR + extra_spec))
    # Power's real rules register `bus_b_v` (the quiet-coast bus solve). The fixture is the vehicle
    # without that one rule, and a planted `rules` adds to the others rather than replacing them.
    power_rules = destination / "domains" / "power" / "rules.py"
    bare = power_rules.read_text() + f"\ndel RULES[{STATE!r}]\n" if power_rules.exists() else ""
    if bare and rules is not None:
        rules = rules.replace("RULES = {", "RULES = {**RULES, ", 1)
    if bare or rules is not None:
        power_rules.write_text(bare + "\n" + (rules or ""))
    return destination


def run_linter(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "check_vehicle.py"), "--dir", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def tick(world: plant.World, values: dict | None = None) -> tuple[dict, dict[str, plant.Gap]]:
    gaps: list[plant.Gap] = []
    after = plant.step(
        world, values if values is not None else plant.initial_values(world), 0.02, gaps
    )
    return after, {gap.state.id: gap for gap in gaps}


def counts(world: plant.World) -> dict[str, int]:
    return {bucket: len(states) for bucket, states in plant.build_order(world).items()}


BUS_B_RULE = """
def bus_b_v(inputs, params, dt):
    return params["fixture_open_v"] - params["fixture_drop_v_per_w"] * inputs["bus_b_load_w"]


RULES = {"bus_b_v": bus_b_v}
"""
BUS_B_PARAMS = "    fixture_open_v: 31.0\n    fixture_drop_v_per_w: 0.001\n"


def test_the_vehicle_has_no_rule_yet_and_the_class_refusal_stands(tmp_path):
    """Without its rule, `bus_b_v` is refused by class exactly as it was before the seam."""
    # Power's real rules solve `bus_b_v`; the fixture copy is the vehicle without that one rule.
    world = plant.load_world(definition(tmp_path))
    assert STATE not in world.rules
    _, gaps = tick(world)
    assert "its rule is not in the configuration" in gaps[STATE].owed


def test_an_empty_rules_file_moves_no_bucket(tmp_path):
    """A `rules.py` that registers nothing is the seam with nothing in it: the build order is the vehicle's."""
    root = definition(tmp_path, "RULES = {}\n")
    assert counts(plant.load_world(root)) == counts(plant.load_world(definition(tmp_path)))


def test_a_registered_rule_advances_its_state_from_its_snapshot_and_its_declaration(tmp_path):
    root = definition(tmp_path, BUS_B_RULE, BUS_B_PARAMS)
    world = plant.load_world(root)
    assert STATE in world.rules
    assert world.rules[STATE].source == "domains/power/rules.py"

    after, gaps = tick(world)
    assert STATE not in gaps, gaps.get(STATE)
    expected = 31.0 - 0.001 * after["bus_b_load_w"]
    assert after[STATE] == pytest.approx(expected) and after["bus_b"] == after[STATE]

    # The worklist moves by exactly that state: out of "owes a rule", into "ready now".
    before = counts(plant.load_world(definition(tmp_path)))
    now = counts(world)
    assert now["ready"] == before["ready"] + 1 and now["rule"] == before["rule"] - 1, (before, now)


def test_a_rule_reads_this_tick_s_value_of_a_state_scheduled_before_it(tmp_path):
    """Gauss-Seidel (`plant.md` §2): the rule is called in the derived order, after its producer."""
    root = definition(tmp_path, BUS_B_RULE, BUS_B_PARAMS)
    world = plant.load_world(root)
    order = [s.id for s in world.states]
    assert order.index("bus_b_load_w") < order.index(STATE)
    started = plant.initial_values(world)
    computed = started["bus_b_load_w"]
    # Last tick's value is planted wrong; the producer recomputes it before the rule reads it.
    stale = {**started, "bus_b_load_w": computed + 500.0}
    after, _ = tick(world, stale)
    assert after[STATE] == pytest.approx(31.0 - 0.001 * computed)


def test_rules_are_called_in_the_derived_tick_order(tmp_path):
    rules = BUS_B_RULE.replace(
        'RULES = {"bus_b_v": bus_b_v}',
        'def lcl_tripped(inputs, params, dt):\n    return "fixture"\n\n\n'
        'RULES = {"bus_b_v": bus_b_v, "lcl_tripped": lcl_tripped}',
    )
    world = plant.load_world(definition(tmp_path, rules, BUS_B_PARAMS))
    called: list[str] = []
    for state_id, rule in list(world.rules.items()):

        def recording(inputs, params, dt, _id=state_id, _fn=rule.function):
            called.append(_id)
            return _fn(inputs, params, dt)

        world.rules[state_id] = plant.DomainRule(state_id, rule.domain, recording, rule.source)
    tick(world, plant.initial_values(world))
    fixture = ("bus_b_v", "lcl_tripped")
    walk = [s.id for s in world.states if s.id in fixture]
    called = [state_id for state_id in called if state_id in fixture]
    # `initial_values` resolves `algebraic` rules at t=0 (bus_b_v), then the tick walks both.
    assert called[-2:] == walk == ["bus_b_v", "lcl_tripped"], called


def test_a_read_the_domain_does_not_declare_is_a_named_gap(tmp_path):
    rules = "def bus_b_v(inputs, params, dt):\n    return inputs['cabin_zone_t']\n\nRULES = {'bus_b_v': bus_b_v}\n"
    _, gaps = tick(plant.load_world(definition(tmp_path, rules)))
    assert (
        "reads 'cabin_zone_t', which domain 'power' neither owns nor declares" in gaps[STATE].owed
    )


def test_an_input_with_no_value_is_a_gap_that_names_it(tmp_path):
    # `battery_usable_j_j` is power's own and has no value this tick: it owes its `derate_curve`.
    # `bus_a_v` was the example until the comms rules gave bus A its `transmitter_on` and the bus
    # solve a value (and `source_converter_v`, off the episode's path, is seeded at its `initial`).
    rules = "def bus_b_v(inputs, params, dt):\n    return inputs['battery_usable_j_j']\n\nRULES = {'bus_b_v': bus_b_v}\n"
    _, gaps = tick(plant.load_world(definition(tmp_path, rules)))
    assert gaps[STATE].needs == "battery_usable_j_j"
    assert "has no value this tick" in gaps[STATE].owed


def test_an_unconfigured_parameter_is_refused_rather_than_handed_to_the_rule(tmp_path):
    rules = "def bus_b_v(inputs, params, dt):\n    return params['fixture_r']\n\nRULES = {'bus_b_v': bus_b_v}\n"
    root = definition(tmp_path, rules, "    fixture_r: UNCONFIGURED\n")
    _, gaps = tick(plant.load_world(root))
    assert gaps[STATE].where.endswith(f"state {STATE}.fixture_r")
    assert "UNCONFIGURED" in gaps[STATE].owed


def test_a_rule_that_returns_nothing_is_a_gap_not_a_value(tmp_path):
    rules = "def bus_b_v(inputs, params, dt):\n    return None\n\nRULES = {'bus_b_v': bus_b_v}\n"
    after, gaps = tick(plant.load_world(definition(tmp_path, rules)))
    assert "returned no value" in gaps[STATE].owed and STATE not in after


def test_a_rule_cannot_write_its_snapshot(tmp_path):
    rules = "def bus_b_v(inputs, params, dt):\n    inputs['bus_b_v'] = 1.0\n    return 1.0\n\nRULES = {'bus_b_v': bus_b_v}\n"
    with pytest.raises(RuntimeError, match="domains/power/rules.py"):
        tick(plant.load_world(definition(tmp_path, rules)))


REFUSED = """
import math


def anything(inputs, params, dt):
    return math.pi


RULES = {
    "cabin_heat_csm_w": anything,      # thermal's, not power's
    "no_such_state": anything,         # declared nowhere
    "battery_charge_j": anything,      # power's, but a stock: the plant integrates it
    "fc_o2_draw_kg_s": anything,       # power's, but its derivation already computes it
    "bus_tie_closed": anything,        # power's, but commanded: the effect path moves it
    "bus_b_v": 3.0,                    # not a function
}
"""


def test_the_loader_and_the_linter_refuse_every_inadmissible_registration(tmp_path):
    root = definition(tmp_path, REFUSED)
    refusals = dict(plant.rule_refusals(root))
    where = "domains/power/rules.py:RULES"
    expected = {
        f"{where}['cabin_heat_csm_w']": "which domain 'thermal' owns and 'power' does not",
        f"{where}['no_such_state']": "a state no domain declares",
        f"{where}['battery_charge_j']": "is a rule for a `stock` state",
        f"{where}['fc_o2_draw_kg_s']": "its `provenance.derivation` already computes",
        f"{where}['bus_tie_closed']": "the effect path",
        f"{where}['bus_b_v']": "not a function",
    }
    assert set(refusals) == set(expected), refusals
    for key, words in expected.items():
        assert words in refusals[key], (key, refusals[key])

    with pytest.raises(plant.Unconfigured, match="no domain declares"):
        plant.load_world(root)

    result = run_linter(root)
    assert result.returncode == 1, result.stdout[-1500:]
    for key in expected:
        assert key in result.stdout, key


@pytest.mark.parametrize(
    ("source", "words"),
    [
        ("import time\n", "imports 'time'"),
        ("import random\n", "imports 'random'"),
        ("from datetime import datetime\n", "imports 'datetime'"),
        ("import os.path\n", "imports 'os.path'"),
        ("import yaml\n", "imports 'yaml'"),
        ("def f(i, p, dt):\n    return open('x').read()\n", "uses 'open'"),
        ("def f(i, p, dt):\n    return __builtins__\n", "uses '__builtins__'"),
        ("def f(i, p, dt):\n    return f.__globals__\n", "'__globals__'"),
        ("N = 0\ndef f(i, p, dt):\n    global N\n    N += 1\n    return N\n", "`global`"),
        ("from . import sibling\n", "relative import"),
    ],
)
def test_a_rule_file_that_could_read_a_clock_randomness_or_a_file_is_refused(
    tmp_path, source, words
):
    root = definition(tmp_path, source + "\nRULES = {}\n")
    refusals = plant.rule_refusals(root)
    assert refusals and all(where.startswith("domains/power/rules.py:") for where, _ in refusals)
    assert any(words in why for _, why in refusals), refusals


def test_the_linter_accepts_an_admissible_rule_and_its_debt_count_does_not_move(tmp_path):
    real = run_linter(VEHICLE)
    fixture = run_linter(definition(tmp_path, BUS_B_RULE))
    assert fixture.returncode == real.returncode == 0, fixture.stdout[-1500:]
    assert fixture.stdout.splitlines()[-1] == real.stdout.splitlines()[-1]
