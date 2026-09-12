"""The vehicle definition composes, and the linter can prove it does not when it does not.

The point of these tests is not the schema. It is that `docs/deep_research/vehicle/` is a
negotiation between twelve documents that disagree, and a negotiation with no referee decays.
`simulator-design.md:141-150` specifies the referee; `thermal_diode.md:29` states the rule it
enforces — *a value that is needed and unset fails the build, loudly, naming what wants it*.
A linter that has never been seen to refuse is indistinguishable from a linter that always
passes, so two of these tests break the configuration on purpose and check that it is caught.

PyYAML is optional here on purpose: the operator-side services are standard library only, and
this must not become a reason the suite cannot run.
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parents[1]
VEHICLE = REPO / "docs" / "deep_research" / "vehicle"
LINTER = VEHICLE / "tools" / "check_vehicle.py"
FILES = (
    "vehicle.yaml",
    "mission.yaml",
    "coupling.yaml",
    "channels.yaml",
    "presentation.yaml",
)


def run_linter(vehicle_dir: Path, strict: bool = False) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(LINTER), "--dir", str(vehicle_dir)]
    if strict:
        argv.append("--strict")
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def copy_definition(destination: Path) -> Path:
    """A writable copy of the definition, without the tooling or the prose.

    The domains come too: by round 2 the definition is four top-level files plus one
    directory per landed domain, and a fixture that copied only the first four would let a
    test pass while the thing it claims to test was never read.
    """
    destination.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copy(VEHICLE / name, destination / name)
    domains = VEHICLE / "domains"
    if domains.is_dir():
        shutil.copytree(domains, destination / "domains")
    return destination


def test_the_vehicle_definition_composes():
    """The seed vehicle must be internally consistent before anything is built on it."""
    result = run_linter(VEHICLE)
    assert result.returncode == 0, f"the linter refused:\n{result.stdout}{result.stderr}"
    assert "COMPOSES" in result.stdout


def test_the_linter_refuses_a_mass_breakdown_that_does_not_sum(tmp_path):
    """Mass closure is the one invariant checkable with no plant, so it must be checked.

    A configuration whose parts do not add up is not a rounding problem: it is the vehicle
    silently changing mass between two files that both look right on their own, which is how
    a Δv budget and a tank size drift apart.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "vehicle.yaml"
    text = path.read_text()
    # +100 kg on the SM inert mass, with the stated total left alone.
    broken = text.replace("csm_sm_inert: 4037", "csm_sm_inert: 4137", 1)
    assert broken != text, "the fixture no longer matches vehicle.yaml"
    path.write_text(broken)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "mass breakdown sums to" in result.stdout


def test_the_linter_refuses_an_engine_that_cannot_fly_its_budget(tmp_path):
    """A vehicle whose trajectory cannot be flown must not compose.

    This is the check that closes the loop between `mission.yaml`'s Δv budget and
    `vehicle.yaml`'s tank: neither file is wrong alone, and together they are an impossible
    mission. Doubling every burn is the cheapest way to make that true on purpose.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "mission.yaml"
    lines = []
    for line in path.read_text().splitlines():
        m = re.match(r"^(\s*dv_m_s:\s*)([0-9.]+)(\s*)$", line)
        if m:
            line = f"{m.group(1)}{float(m.group(2)) * 2:g}{m.group(3)}"
        lines.append(line)
    path.write_text("\n".join(lines) + "\n")

    result = run_linter(definition)
    assert result.returncode == 1
    assert "cannot fly the budget" in result.stdout


def test_an_unset_value_is_a_named_debt_and_never_a_default(tmp_path):
    """A value that is needed and unset must fail loudly, naming what wants it.

    `thermal_diode.md:29` forbids a threshold silently defaulting to an invented "typical
    spacecraft" value, and `simulator-design.md:146-150` generalises it. So the debt has to
    be both *reported* — with the edge that wants it — and *retirable* by supplying a real
    value, and the two halves are what this test checks. A linter that reported debts but
    could not lose them would be a wall, not a conversation.

    The test *finds* an unconfigured edge rather than naming one, because which edges are still
    unconfigured is a fact about the configuration and moves every round — this test has been
    repointed twice for that reason, once onto `E-BUS-PUMP` and once onto `E-FC-BUS`, and both
    were closed underneath it. The report moves; the property does not.
    """
    strict = subprocess.run(
        [sys.executable, str(LINTER), "--dir", str(VEHICLE), "--strict"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert strict.returncode == 2, "unfilled debts must fail a --strict build"
    assert "OWED" in strict.stdout

    owed = re.search(r"coupling\.yaml:edge (E-[\w-]+):", strict.stdout)
    assert owed, f"no coupling edge is reported as owing a value:\n{strict.stdout[:600]}"
    edge_id = owed.group(1)
    assert edge_id in strict.stdout, "the debt must name the edge that wants the value"

    # Patch that edge, and only it, into a fully configured one. The two YAML forms in this file
    # (a flow mapping on one line, a block mapping over several) make a targeted field edit
    # fragile, so the whole list item is replaced by a freshly written one that carries the
    # endpoints and kind across.
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "coupling.yaml"
    text = path.read_text()
    start = text.index(f"  - id: {edge_id}")
    end = text.find("\n  - id: ", start)
    item = text[start : end if end != -1 else len(text)]
    # Both YAML forms appear in this file and the same field sits at a different column in each —
    # `unit:` is the first thing on its line in a block mapping and the second key of a flow
    # mapping — so nothing here is anchored to a line start. Quoted units keep their quotes: the
    # slice is re-emitted verbatim rather than reformatted.
    fields = {
        name: re.search(rf"\b{name}: ([^,\n}}]+)", item) for name in ("from", "to", "kind", "unit")
    }
    assert all(fields.values()), f"cannot read the endpoints of {edge_id} out of its own item"
    carried = {name: match.group(1).strip() for name, match in fields.items()}  # type: ignore[union-attr]
    replacement = (
        f"  - id: {edge_id}\n"
        f"    from: {carried['from']}\n"
        f"    to: {carried['to']}\n"
        f"    kind: {carried['kind']}\n"
        f"    sensitivity: {{value: 0.05, unit: {carried['unit']}, "
        'basis: chosen, reason: "test fixture only", at: nominal}\n'
    )
    path.write_text(text[:start] + replacement + text[end if end != -1 else len(text) :])

    result = run_linter(definition)
    assert f"coupling.yaml:edge {edge_id}" not in result.stdout, (
        "supplying the value must retire the debt"
    )
    assert result.returncode == 0, result.stdout[-1200:]


def test_the_derived_schedule_puts_every_producer_before_its_consumer():
    """`plant.md:71` promises a total order, and the order has to be a *tick* order.

    It was not. Kahn's algorithm took the nodes with no **successors** first, which is the *last*
    element of a topological order, so the emitted schedule was exactly reversed: all thirty-nine
    ordering constraints were violated and nothing refused it, because the only property anyone
    checked was that a cycle was absent — and a reversed topological order has no cycle either.
    The reference plant had been ticking fuel cells after the buses they feed and propellant tanks
    after the engines that drain them, and `--order` printed the reversal under the heading
    "dependencies first".

    The assertion runs against the *graph* rather than against the emitted list, so it cannot
    agree with the emitter the way a round-trip check would: it reads the edge list and the
    declared back-edges and demands that each remaining edge point forwards in the order.
    """
    result = subprocess.run(
        [sys.executable, str(LINTER), "--order"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    order = [
        match.group(1) for match in re.finditer(r"^\s*\d+\.\s+(\S+)\s+\(", result.stdout, re.M)
    ]
    assert len(order) > 30, f"the tick order did not parse:\n{result.stdout[:600]}"

    definition = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    back_edges = {
        str(cycle.get("back_edge"))
        for cycle in definition.get("cycles") or []
        if cycle.get("back_edge") is not None
    }
    position = {node: index for index, node in enumerate(order)}
    wrong = []
    for edge in definition["edges"]:
        if edge["id"] in back_edges:
            continue  # a back-edge reads last tick's value, so it is *supposed* to point backwards
        source, sink = edge["from"], edge["to"]
        if source not in position or sink not in position:
            continue  # `command_executive` and `published_evidence` are not scheduled
        if position[source] > position[sink]:
            wrong.append(f"{edge['id']} ({source} -> {sink})")
    assert not wrong, (
        f"{len(wrong)} edge(s) run backwards in the derived tick order, so the plant would "
        f"compute them from stale values: {wrong}"
    )


def test_the_linter_refuses_a_conservation_that_carries_a_ratio(tmp_path):
    """`conserve` means one quantity travelling, so there is no ratio to choose and nothing to owe.

    This check existed in `coupling.yaml`'s first version and had never once refused anything,
    because the dimension lookup returned `None` for six of the node units in that file and the
    guard was `if a and b` — so an edge the linter could not decide was an edge that passed. That
    is how `E-ATM-ABSORB` spent its life asserting cabin carbon dioxide is *conserved* into
    absorbent man-hours, and `E-PRESS-PROP` that a bladder pressurant is conserved out of a tank
    it never leaves. A check that cannot run is not a check that passed, so both halves are driven
    here: a conservation carrying a number that is not one, and one whose endpoints have no
    dimension to look up.
    """
    # Half one: a genuine one-for-one conservation, given a ratio it cannot have.
    definition = copy_definition(tmp_path / "ratio")
    path = definition / "coupling.yaml"
    text = path.read_text()
    start = text.index("  - id: E-O2-ECLSS")
    end = text.find("\n  - id: ", start)
    item = text[start:end]
    assert "kind: conserve" in item and "value: 1.0" in item, "the fixture moved off E-O2-ECLSS"
    path.write_text(text[:start] + item.replace("value: 1.0", "value: 0.9", 1) + text[end:])

    result = run_linter(definition)
    assert result.returncode == 1
    assert "conservation is one for one" in result.stdout, result.stdout[-800:]

    # Half two: the same edge, undecidable, because the cabin stops saying which of the four gas
    # masses and the pressure it holds is the one a conservation can arrive as.
    definition = copy_definition(tmp_path / "undecidable")
    path = definition / "coupling.yaml"
    text = path.read_text()
    assert text.count("    conserves: mass\n") == 2, "the cabin nodes no longer declare conserves"
    path.write_text(text.replace("    conserves: mass\n", "", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "no dimension for" in result.stdout, result.stdout[-800:]
    assert "conservation names one quantity travelling" in result.stdout


def test_the_linter_refuses_a_node_that_is_not_in_the_graph(tmp_path):
    """A node in the node list and in no edge is a declaration that looks like a connection.

    Every check this file had asked whether a node *exists* — is it declared, does it have states,
    does the schedule order it. The bus tie passed all of them while being in no edge at all: the
    coupling ran straight from `bus_b` to `bus_a`, and `E-BUSB-BUSA`'s own note said "gated by
    bus_tie" while the tie gated nothing. A membership test cannot tell that apart from a
    connection, which is the same blindness a reversed tick order had.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "coupling.yaml"
    text = path.read_text()
    # `guidance` commands the engine and the valves and is fed by the command path and the nav
    # solution — four edges, and every one of them has to go for the node to be isolated. Taking
    # only the inbound pair leaves it a *source*, which is a legitimate thing to be, so a fixture
    # that stopped there would be testing that a source composes.
    incident = [
        edge["id"]
        for edge in yaml.safe_load(text)["edges"]
        if "guidance" in (edge["from"], edge["to"])
    ]
    assert len(incident) >= 2, f"guidance is no longer connected: {incident}"
    for eid in incident:
        start = text.index(f"  - id: {eid}")
        end = text.find("\n  - id: ", start)
        text = text[:start] + text[end + 1 :]
    path.write_text(text)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "is in the node list and not in the graph" in result.stdout, result.stdout[-800:]


def test_the_linter_refuses_a_stock_that_only_drains_or_only_fills(tmp_path):
    """A stock with no producer only drains; one with no consumer only fills. Both are quiet.

    `battery_energy` was the first kind for the whole life of the graph and a reversed tick order
    is what hid it: its only inbound edge was a thermal back-edge from the coldplate. The second
    kind is quieter still — `water_potable` was produced by the fuel cell and drawn by nothing, so
    the one number a rationing crew would watch could only go up. Three tanks are legitimately
    pre-loaded and one node is legitimately a consumption counter, and each says so in a field
    rather than by omission; this drives both refusals and checks that the declarations silence
    them.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "coupling.yaml"
    text = path.read_text()

    # Take the escape hatch away from a pre-loaded tank and it is a stock nobody fills.
    stripped = text.replace(
        "    preloaded: \"the LM's oxygen is loaded at the pad",
        "    unused_note: \"the LM's oxygen is loaded at the pad",
        1,
    )
    assert stripped != text, "the fixture no longer matches o2_lm"
    path.write_text(stripped)
    result = run_linter(definition)
    assert result.returncode == 1
    assert "is a stock with no inbound edge that is not a back-edge" in result.stdout
    assert "o2_lm" in result.stdout

    # And the same for the counter: strip `accumulates:` and the absorber only ever fills.
    definition = copy_definition(tmp_path / "counter")
    path = definition / "coupling.yaml"
    text = path.read_text()
    stripped = text.replace("    accumulates: >-\n", "    unused_note: >-\n", 1)
    assert stripped != text, "the fixture no longer matches absorber_capacity"
    path.write_text(stripped)
    result = run_linter(definition)
    assert result.returncode == 1
    assert "is a stock with no outbound edge at all" in result.stdout
    assert "absorber_capacity" in result.stdout


def test_the_linter_refuses_inverted_hysteresis(tmp_path):
    """A threshold that clears on the wrong side of its assert never clears.

    `thermal_diode.md:1013` names this as a build refusal for one domain; it is generalised
    here because the failure is silent and one-sided — the alarm simply stays on, or never
    comes on, and a fleet that learns to ignore a stuck alarm has lost the channel.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "power" / "profiles.yaml"
    text = path.read_text()
    # A `below` comparator whose clear value sits *under* its assert value.
    broken = text.replace("assert: 26.5\n    clear: 27.2", "assert: 26.5\n    clear: 26.0", 1)
    assert broken != text, "the fixture no longer matches profiles.yaml"
    path.write_text(broken)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "hysteresis is inverted" in result.stdout


def test_the_linter_refuses_a_command_that_hides_its_interlocks(tmp_path):
    """Gates and interlocks are separate fields, and 'none' has to be written deliberately.

    This is D-03, and it exists because `contract/diode_probe.py` cannot tell an
    agent-writable gate from a service-owned interlock. An omitted `interlocks` key is
    indistinguishable from an empty one at the point of use, and only one of those is a
    reviewed decision.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "power" / "commands.yaml"
    text = path.read_text()
    line = "    interlocks: [bus_a_undervoltage, load_margin_negative]\n"
    assert line in text, "the fixture no longer matches commands.yaml"
    path.write_text(text.replace(line, "", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "declares no interlocks" in result.stdout


def test_the_linter_refuses_a_point_that_invents_a_channel(tmp_path):
    """A domain may not fork the vocabulary; a new channel is registered, not declared here.

    This is the check that keeps `corpus-review.md` §5 from happening again — eight documents
    naming one object eight ways is what a registry exists to prevent, and a domain that adds
    a local name is the same failure one scale down.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "power" / "points.yaml"
    text = path.read_text()
    broken = text.replace(
        "  - channel: power.dc_bus_a_v",
        "  - channel: power.my_own_bus_volts",
        1,
    )
    assert broken != text, "the fixture no longer matches points.yaml"
    path.write_text(broken)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "is not a registered channel" in result.stdout


def test_an_unset_domain_value_is_a_debt_named_by_its_path(tmp_path):
    """Every unset value in a domain is reported, with the path that reaches it.

    `thermal_diode.md:29` forbids a threshold silently defaulting to an invented value and
    `plant.md` §11 generalises the rule to the whole vehicle. The *path* is the part that makes
    the rule usable: "something is unset" is not actionable, and
    `components.yaml.radiator_model.environment.lunar_ir_w_m2` is.
    """
    strict = run_linter(VEHICLE, strict=True)
    assert strict.returncode == 2, "the thermal domain's real debts must fail a strict build"
    assert "domains/thermal/components.yaml" in strict.stdout
    assert "is UNCONFIGURED" in strict.stdout

    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "thermal" / "components.yaml"
    text = path.read_text()
    # The sublimator's rejection is the domain's one genuinely unpublished figure.
    unset = "    rejection_w: UNCONFIGURED"
    assert unset in text, "the fixture no longer matches the thermal components"
    path.write_text(text.replace(unset, "    rejection_w: 1500", 1))

    result = run_linter(definition, strict=True)
    assert "sublimator_lm" not in result.stdout, "supplying the value must retire the debt"


def test_a_delay_state_owes_its_delay(tmp_path):
    """A transport delay is its own method, and it owes a delay the way a lag owes a tau.

    plant.md §3 grew from six methods to seven when the first delay element landed: a lag
    forgets its history exponentially and a delay *is* its history. The linter refused the
    state by name, which is why the seventh class exists rather than being smuggled in as a
    lag with a long time constant.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "thermal" / "components.yaml"
    text = path.read_text()
    line = "    delay_s: 1042\n"
    assert line in text, "the fixture no longer matches the thermal loop"
    path.write_text(text.replace(line, "", 1))

    result = run_linter(definition, strict=True)
    assert result.returncode == 2
    assert "loop_transport_t" in result.stdout
    assert "has no delay" in result.stdout


def test_the_linter_refuses_a_claim_quantity(tmp_path):
    """D-04 has to be a build refusal, not a paragraph.

    Declining the claims lifecycle while leaving its fields in the schema would be a decline in
    name only: `available_to_new` is the aggregate every other agent's claims leave behind, so
    publishing it hands the fleet the deconfliction primitive `design.md` §8 deliberately
    withholds. The corpus's schema makes all four fields required, which means the next person
    to port a row from it will add one back unless the linter says no.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "channels.yaml"
    text = path.read_text()
    anchor = "  - id: res.time_to_limit_s"
    assert anchor in text, "the fixture no longer matches channels.yaml"
    path.write_text(
        text.replace(
            anchor,
            "  - id: res.available_to_new_prop_main_kg\n"
            "    unit: kg\n    layer: estimate\n    precision: 0.01\n    rate_hz: 0.2\n"
            "    priority: P4\n    provenance:\n      basis: historical\n"
            '      source: "consumables_diode.md:1568-1575"\n' + anchor + "\n",
            1,
        )
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "is a claim quantity" in result.stdout


def test_a_domain_point_may_instantiate_a_registered_template(tmp_path):
    """A concrete channel resolves against a templated registry entry, and a wrong one does not.

    `res.recon_[resource]_kg` is one registry entry answering for `res.recon_o2_kg` and
    `res.recon_main_propellant_kg`. Comparing normalised strings does not do that, and the
    first version of the resolver quietly refused every residual the consumables domain
    published — a check that was too strict in a way that would have looked like a missing
    feature rather than a broken rule.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "consumables" / "points.yaml"
    text = path.read_text()
    assert "res.o2_remaining_kg" in text
    path.write_text(text.replace("res.o2_remaining_kg", "res.o2_remaining_grams", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "is not a registered channel" in result.stdout
    assert "res.recon_o2_kg" not in result.stdout, "template instantiation must still resolve"


def test_the_linter_refuses_a_crew_readout_the_position_cannot_perceive(tmp_path):
    """The display contract and the perception bound are one bound written in two files.

    `channels.yaml#crew_positions` says which channels a person at a station could honestly
    report; `domains/crew/components.yaml#display_contract` says what the panel in front of
    them actually shows. A readout in the second and not the first is a leak — the crew would
    be reading a gauge that is not there — and `review-findings.md` #4 is explicit that this
    cannot be cleaned up once a fleet has learned to trust the answer. The channel chosen here
    is on the commander's own `not_perceivable` list, so the fixture is the leak at its worst.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "crew" / "components.yaml"
    text = path.read_text()
    anchor = '            - {channel: eclss.suit_loop_flow_cfm, displayed_precision: 1, units: "ft3/min"}'
    assert anchor in text, "the fixture no longer matches domains/crew/components.yaml"
    path.write_text(
        text.replace(
            anchor,
            anchor + "\n"
            "            - {channel: thermal.avionics_plate_c, displayed_precision: 0.1, units: degC}",
            1,
        )
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "cannot perceive" in result.stdout


def test_the_linter_refuses_a_crew_position_nobody_can_be_located_at(tmp_path):
    """A station added to the bound but not to the location channel is a station with no index.

    D-06 makes the position the third argument of the perception function, so the position list
    and the `crew.location_[id]` vocabulary have to be the same list. Drift here is silent in
    the worst way: a fleet asks a crew member at the new station a question, the answer is
    bounded by a perceivable set nothing else refers to, and no check objects because both
    files are individually well-formed.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "channels.yaml"
    text = path.read_text()
    assert "\nopen_debts:\n" in text, "the fixture no longer matches channels.yaml"
    path.write_text(
        text.replace(
            "\nopen_debts:\n",
            "\n  - id: csm_left_seat\n"
            "    perceivable: [cw.master_alarm]\n"
            "    not_perceivable: [eclss.cabin_pressure_psia]\n"
            "    note: a station added without a matching location channel\n"
            "\nopen_debts:\n",
            1,
        )
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "csm_left_seat" in result.stdout
    # Both writers of the station vocabulary must object: the channel that indexes a report to
    # a station, and the state that decides which bound is applied at runtime.
    assert "state crew_location" in result.stdout, result.stdout


def test_the_linter_refuses_a_raw_thruster_verb(tmp_path):
    """`rcs_dode.md:369`'s forbidden list has to be a build refusal, not a paragraph.

    The architectural claim at `rcs_dode.md:9` is that RCS is an attitude-and-wrench *execution
    service* and not a remote thruster-firing bus. That claim is true exactly as long as no domain
    can register a verb that names a thruster and a duration, and a design note saying so is a
    convention — which is what `simulator-design.md` §7 says will rot. Same reasoning as D-04's
    forbidden channels: declining a capability while permitting its name is a decline in name
    only.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "rcs" / "commands.yaml"
    text = path.read_text()
    anchor = "  - verb: set_rcs_mode"
    assert anchor in text, "the fixture no longer matches domains/rcs/commands.yaml"
    path.write_text(
        text.replace(
            anchor,
            "  - verb: fire_thruster\n"
            "    argument_schema:\n"
            "      thruster: {type: integer}\n"
            "      duration_us: {type: integer}\n"
            "    authority: A3\n"
            "    gate: {kind: preference, variable: rcs_test_enable}\n"
            "    interlocks: none - reviewed\n"
            "    conflict_domain: rcs.test\n"
            "    allowed_phases: [surface]\n"
            "    irreversible: false\n"
            "    idempotent: false\n"
            "    execution_class: immediate\n"
            "    maximum_queue_age_s: 5\n"
            "    help: a raw pulse\n"
            "    provenance:\n"
            "      basis: historical\n"
            '      source: "rcs_dode.md:369"\n' + anchor,
            1,
        )
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "is a forbidden form" in result.stdout
    assert "fire_thruster" in result.stdout


def test_the_linter_refuses_an_interlock_that_resolves_to_nothing(tmp_path):
    """An interlock that names no threshold is never evaluated, and silently.

    The failure this catches is the worst shape a declaration fault can have: the verb advertises
    a guard, the executive looks it up, finds nothing, and either passes or crashes. Three domains
    shipped a flat `other_domain_thing` that resolved nowhere — `eclss_cabin_pressure_low` against
    an eclss threshold named `cabin_pressure_caution` — while the vocabulary's own example is
    dotted (`thermal.pump_dry_run`). This test points one at a threshold that does not exist on
    either side of the qualifier.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "rcs" / "commands.yaml"
    text = path.read_text()
    anchor = "interlocks: [rcs_uncommanded_rate]"
    assert anchor in text, "the fixture no longer matches domains/rcs/commands.yaml"
    path.write_text(text.replace(anchor, "interlocks: [gnc.attitude_target_sanity]", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "resolves to no threshold" in result.stdout


def test_the_linter_refuses_a_verb_that_advertises_no_arguments(tmp_path):
    """`capability.snapshot` publishes the argument schema, so an empty one is a wrong answer.

    Six domains wrote their schema keys one level too shallow under an empty `argument_schema:`,
    which parses, satisfies every other rule, and tells a machine that ten verbs take no
    arguments. A fleet would find out by calling one wrong.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "rcs" / "commands.yaml"
    text = path.read_text()
    anchor = "      mode: {type: enum, values: [auto, manual, free_drift]}\n"
    assert anchor in text, "the fixture no longer matches domains/rcs/commands.yaml"
    path.write_text(text.replace(anchor, "    mode: {type: enum, values: [auto, manual]}\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "argument_schema" in result.stdout


def test_the_linter_refuses_a_guard_on_evidence_that_cannot_arrive(tmp_path):
    """Invariant D is only real if a guard demanding impossible freshness is a build failure.

    `mission_diode.md:1292` makes a hazardous effect on stale evidence a safety failure, and
    applying that rule mechanically is what found the registry's own `decision_age_ms` table
    was unsatisfiable: it demanded P1 evidence within 100 ms on three P1 channels that publish
    at 1 Hz, so those guards could never have passed. This test slows the bus channel down and
    leaves the transition's requirement alone, which is the same defect arriving from the other
    side.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "channels.yaml"
    text = path.read_text()
    anchor = "  - id: power.dc_bus_a_v\n"
    assert anchor in text, "the fixture no longer matches channels.yaml"
    head, _, tail = text.partition(anchor)
    block, _, rest = tail.partition("  - id: ")
    path.write_text(
        head + anchor + block.replace("rate_hz: 10", "rate_hz: 0.5", 1) + "  - id: " + rest
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "every sample would already be too old" in result.stdout


def test_the_linter_refuses_a_phase_that_redeclares_allowed_verbs(tmp_path):
    """Two lists for one relation drifted 197 places apart, so the second one is refused.

    A phase cannot be authoritative about what its verbs permit: permission lives on the verb
    (`apollo_diode.md:439`), the phase side cannot know whether a verb's guards are satisfiable,
    and a fleet is told the answer at runtime by the capability snapshot in `state.json`. The
    field was deleted rather than synchronised, and this is the check that keeps it deleted.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "mission.yaml"
    text = path.read_text()
    anchor = "  - id: descent\n"
    assert anchor in text, "the fixture no longer matches mission.yaml"
    path.write_text(
        text.replace(anchor, anchor + "    allowed_verbs: [set_rcs_mode, make_coffee]\n", 1)
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "second source of truth" in result.stdout


def test_the_linter_refuses_a_posture_the_registry_does_not_carry(tmp_path):
    """The posture enum and the posture machine are one vocabulary written in two files.

    `mission.posture` is what the executive publishes and `mission.yaml#postures` is what it may
    take. Drift here is silent in the same way the crew station vocabulary was: a posture the
    mission can enter and the channel cannot name, or a value the channel offers that no
    transition produces — and either way the fleet is shown a posture that means nothing.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "mission.yaml"
    text = path.read_text()
    anchor = "  - id: aborted\n"
    assert anchor in text, "the fixture no longer matches mission.yaml"
    head, _, tail = text.partition(anchor)
    block, _, rest = tail.partition("  - id: ")
    path.write_text(head + "  - id: parked\n" + block + "  - id: " + rest)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "parked" in result.stdout


def test_the_linter_refuses_a_quality_function_that_can_see_the_fault_state(tmp_path):
    """`simulator-design.md:496-508`, made mechanical — and nothing implemented it before.

    The clause is that quality is assigned only by a function that cannot see the simulator's
    fault state, so that a silently biased sensor stays GOOD. The corpus review lists it among
    what nobody wrote. `avionics_diode.md:371-388` supplies a function that satisfies it, and
    there are exactly two ways to break the property: read a fault-state parameter, or emit a
    code that is not a quality. This test does the first; the second is the subtle one, because
    the document's own function returns FAULT from the same branch that returns SUSPECT.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "avionics" / "components.yaml"
    text = path.read_text()
    anchor = "  parameters: [sample, now_mono]\n"
    assert anchor in text, "the fixture no longer matches domains/avionics/components.yaml"
    path.write_text(text.replace(anchor, "  parameters: [sample, now_mono, fault_state]\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "cannot satisfy simulator-design.md:496-508" in result.stdout


def test_the_linter_refuses_a_quality_code_that_is_a_conclusion(tmp_path):
    """A conclusion published as a quality is the collapse `design.md:211-214` exists to stop.

    The vehicle publishes both — a quality code per sample on the frame, and
    `avionics.sensor_health_[class]` per instrument — and the whole value of having both is that
    a fleet can tell "this reading is doubtful" from "this instrument is dead". A rule table that
    emitted `FAULT` as a quality would delete that difference at the one place it is decided.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "avionics" / "components.yaml"
    text = path.read_text()
    anchor = "      quality: INVALID\n"
    assert anchor in text, "the fixture no longer matches domains/avionics/components.yaml"
    path.write_text(text.replace(anchor, "      quality: FAULT\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "not a canonical quality code" in result.stdout


def test_the_linter_refuses_an_irreversible_verb_that_ignores_the_clock(tmp_path):
    """`avionics_diode.md:496-508`'s `TIME_UNTRUSTED`, which no other document has.

    An irreversible action with a time-tagged deadline has that deadline measured against the
    vehicle's clock, so a drifted clock is a one-shot with an unknown arming window. The clause
    is the last of the document's ten ordered authorization requirements and the only one that
    is absent from `mission_diode.md`'s eight-term predicate, so it is declared on the verb and
    the linter requires the declaration on every irreversible verb.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "structure" / "commands.yaml"
    text = path.read_text()
    anchor = "    irreversible: true\n    requires_time_sync: true\n"
    assert anchor in text, "the fixture no longer matches domains/structure/commands.yaml"
    path.write_text(text.replace(anchor, "    irreversible: true\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "unknown deadline" in result.stdout


def test_the_linter_refuses_an_antenna_the_vehicle_does_not_have(tmp_path):
    """A selectable channel value has to be hardware the vehicle declares.

    `comm.antenna`'s four members are `vehicle.yaml#comms.antennas`, and the binding is the same
    one the phase, posture and crew-station vocabularies get — for the same reason. An antenna a
    fleet can select and the vehicle does not have is a command surface over nothing, and the
    error is invisible in both files: the enum looks like a vocabulary and the antenna list looks
    like an inventory, and only the pair is wrong.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "channels.yaml"
    text = path.read_text()
    anchor = '    unit: "enum[high_gain,omni_a,omni_b,sband_steerable]"\n'
    assert anchor in text, "the fixture no longer matches channels.yaml"
    path.write_text(text.replace(anchor, '    unit: "enum[high_gain,omni_a,omni_b]"\n', 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "cannot select 'sband_steerable'" in result.stdout


def test_the_linter_refuses_a_channel_whose_state_cannot_hold_its_values(tmp_path):
    """A published state and the machine behind it are one vocabulary written in two files.

    This is the general form of the crew-station, phase, posture and antenna bindings, and it
    found three real defects the moment it was added: `eclss.cabin_regulator_state` published
    three of the regulator's four positions, so a *closed* regulator — a cabin isolated from its
    supply, which is the configuration Apollo 13 flew — was a state the vehicle could be in and
    could not report. The other two were in `domains/structure/`: apollo's single `stage_state`
    channel covers a fact two machines produce, and `abandoned` (the descent stage left on the
    surface) belonged to neither machine the channel was pointed at.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "channels.yaml"
    text = path.read_text()
    anchor = '    unit: "enum[primary,emergency,isolated,closed]"\n'
    assert anchor in text, "the fixture no longer matches channels.yaml"
    path.write_text(text.replace(anchor, '    unit: "enum[primary,emergency,isolated]"\n', 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "its own state cannot hold" in result.stdout


def test_a_projection_of_a_state_is_a_note_rather_than_a_refusal(tmp_path):
    """A channel derived from a state need not republish the state's vocabulary.

    `cw.active_lights` reports which system lamps are lit, which is derived from the alert
    lifecycle and is not the lifecycle's own value set. Refusing that would be the check
    over-reaching; the rule the linter uses instead is that *overlapping but unequal* is a fork
    and *disjoint* is a projection, and it says which it decided so the judgement is auditable.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "channels.yaml"
    text = path.read_text()
    anchor = "  - id: cw.active_lights\n"
    assert anchor in text, "the fixture no longer matches channels.yaml"
    # The channel currently publishes a vocabulary *disjoint* from the lifecycle's, which is a
    # projection and is exactly what must not be refused. The test first confirms that, then
    # makes the vocabulary overlap without matching — which is the defect.
    assert run_linter(definition).returncode == 0, "a disjoint projection must not be refused"

    head, _, tail = text.partition(anchor)
    block, _, rest = tail.partition("  - id: ")
    broken = block.replace(
        '    unit: "list[enum[ECS,RCS,DC_BUS,PROP,GUIDANCE]]"',
        '    unit: "list[enum[asserted,cleared]]"',
        1,
    )
    assert broken != block, "the fixture no longer matches cw.active_lights"
    path.write_text(head + anchor + broken + "  - id: " + rest)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "its own state cannot hold" in result.stdout


def test_the_linter_refuses_an_initial_state_that_cannot_reach_the_moon(tmp_path):
    """The published TLI figures describe a trajectory that does not arrive, and now it shows.

    `mission.yaml` carried three mutually consistent numbers from `A11 Tbl 7-II` — 25,562 ft/s in
    the parking orbit, 35,546 ft/s after cutoff, a 9,984 ft/s difference — and together they give
    an apogee of 188,812 km against a Moon at 384,400. It is not a timing problem: a minimum-energy
    Hohmann transfer needs 10,928.2 m/s, so the published 10,834.4 is 93.8 m/s *slower* than the
    cheapest trajectory that arrives at all. Conflict C-24 records the disposition; this is the
    check that makes it mechanical rather than a paragraph.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "mission.yaml"
    text = path.read_text()
    # The conic the published speed actually gives: a = 97,687 km, e = 0.932814.
    for old, new in (
        ("    semi_major_axis_km: 254545", "    semi_major_axis_km: 97687"),
        ("    eccentricity: 0.974216", "    eccentricity: 0.932814"),
        ("    speed_at_cutoff_m_s: 10949.8", "    speed_at_cutoff_m_s: 10834.4"),
    ):
        assert old in text, old
        text = text.replace(old, new, 1)
    path.write_text(text)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "cannot arrive at any transit time" in result.stdout


def test_the_linter_rederives_the_osculating_elements(tmp_path):
    """A state vector is checkable arithmetic, so the linter checks it rather than trusting it.

    The four elements were solved from the parking orbit and the phase ladder, which means all four
    are re-derivable: `e = 1 - r_p/a`, vis-viva at cutoff, Kepler's equation for the arrival radius,
    and the ladder's own coast duration. A disagreement in any of them means a published figure or a
    phase duration moved, and the error is otherwise invisible — the elements look like a state
    vector and nothing else in the vehicle reads them.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "mission.yaml"
    text = path.read_text()
    old = "    eccentricity: 0.974216\n"
    assert old in text, "the fixture no longer matches mission.yaml"
    path.write_text(text.replace(old, "    eccentricity: 0.965000\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "1 - r_p/a" in result.stdout


def test_the_linter_refuses_a_cadence_class_that_disagrees_with_the_registry(tmp_path):
    """The fleet's view is a summary of the registry, and a summary can drift from its source.

    `presentation.yaml` declares how many channels fall in each cadence class, which is the only
    statement anywhere of what a frame's membership looks like at each rate. It is a *count*, so it
    is checkable, and a count that disagrees with the registry is worse than no count: a fleet
    reading the summary would plan against four cadences the vehicle does not have.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "presentation.yaml"
    text = path.read_text()
    anchor = "members: 85,"
    assert anchor in text, "the fixture no longer matches presentation.yaml"
    path.write_text(text.replace(anchor, "members: 84,", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "cadence class" in result.stdout


def test_the_linter_refuses_a_mirror_that_exceeds_its_bound(tmp_path):
    """`state.json` is rewritten every cycle, so its membership is a cost and the bound is a rule.

    The mirror carries the vehicle's own software state — service channels at P0 and P1 — and the
    bound is what makes adding a twentieth a decision with a number attached rather than silent
    growth. This test lowers the bound below the set the rule derives.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "presentation.yaml"
    text = path.read_text()
    anchor = "  bound: 24\n"
    assert anchor in text, "the fixture no longer matches presentation.yaml"
    path.write_text(text.replace(anchor, "  bound: 12\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "rewritten every cycle" in result.stdout


def test_the_linter_refuses_a_mapping_that_publishes_truth(tmp_path):
    """`docs/diode-contract.md:202` publishes truth never, and the mapping is where that is decided.

    The registry has four kinds of channel and the contract has three layers. Mapping any kind to
    T would say that a class of channel is published as ground truth — which is the one thing the
    window exists to prevent, and which no domain's `not_published` section could undo once the
    mapping said otherwise.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "presentation.yaml"
    text = path.read_text()
    anchor = "    measurement: A\n"
    assert anchor in text, "the fixture no longer matches presentation.yaml"
    path.write_text(text.replace(anchor, "    measurement: T\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "publishes truth never" in result.stdout


def test_the_help_generator_covers_every_verb_and_every_absence():
    """`HELP.md` is generated, so its coverage is a property rather than a hope.

    `docs/diode-contract.md:275-279` makes `HELP.md` the only place a verb name may appear, which
    means a verb the generator misses is a verb no fleet can discover and an absence it mislabels
    is a capability a fleet will never try. The generator's first run found exactly that: it listed
    `set_telemetry_profile` under "verbs this vehicle does not have" while `domains/comms/`
    implements it, because a domain declining a verb means *not mine* rather than *not this
    vehicle's*. That is now a heading of its own, and this test holds the partition.
    """
    generator = VEHICLE / "tools" / "generate_help.py"
    result = subprocess.run(
        [sys.executable, str(generator)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    text = result.stdout

    verbs: dict[str, str] = {}
    declined: set[str] = set()
    for path in sorted((VEHICLE / "domains").glob("*/commands.yaml")):
        commands = yaml.safe_load(path.read_text())
        for verb in commands.get("commands") or []:
            verbs[str(verb["verb"])] = path.parent.name
        for refused in commands.get("not_implemented") or commands.get("declined") or []:
            declined.add(str(refused["verb"]))

    for name in verbs:
        assert f"#### `{name}`" in text, f"{name} is implemented but has no HELP entry"
    for name in declined:
        assert f"`{name}`" in text, f"{name} was considered and refused but is not documented"

    # The partition: a verb some domain implements must never appear under the absent heading,
    # whatever another domain says about it.
    absent = text.split("## Verbs this vehicle does not have")[1].split("## Verbs another")[0]
    for name, owner in verbs.items():
        assert f"`{name}` (" not in absent, f"{name} is implemented by {owner} but listed as absent"
    if any(name in declined for name in verbs):
        assert "## Verbs another domain owns" in text, (
            "a verb declined by one domain and implemented by another has no heading of its own"
        )


def test_the_linter_refuses_a_verb_that_is_both_offered_and_denied(tmp_path):
    """One file cannot register a verb while the other says the vehicle does not have it.

    Declining a verb *another* domain owns is legitimate — it means "not mine" — which is why the
    check is scoped to one domain rather than to the vehicle. Within a domain there is no such
    reading: the registry would offer the verb and the help text would deny it, and which one a
    fleet believed would depend on which file it happened to read.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "thermal" / "commands.yaml"
    text = path.read_text()
    anchor = "  - verb: set_radiator\n"
    assert anchor in text, "the fixture no longer matches domains/thermal/commands.yaml"
    path.write_text(text.replace(anchor, "  - verb: set_heater\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "both registered and declined" in result.stdout


def test_the_linter_refuses_a_residual_cycle_in_the_schedule(tmp_path):
    """`plant.md:71` promises the linter emits a total order; a residual cycle means none exists.

    The promise was unkept for several rounds, and deriving the order is what found three separate
    undeclared loops: `comms <-> power` through the amplifier load and the bus voltage, the
    hydrogen half of the fuel-cell reactant cycle, and — in the other direction — that a *domain*
    order cannot be derived at all, because coarsening the node graph into domains creates cycles
    the physics does not have. The schedule is now over nodes, and this test removes a back-edge
    declaration to confirm that a real loop is refused rather than ordered arbitrarily.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "coupling.yaml"
    text = path.read_text()
    anchor = "  - id: C-COMM-BUS\n"
    assert anchor in text, "the fixture no longer matches coupling.yaml"
    head, _, tail = text.partition(anchor)
    block, _, rest = tail.partition("  - id: ")
    path.write_text(
        head
        + block.replace("    back_edge: E-BUS-COMM\n", "    back_edge: null\n", 1)
        + "  - id: "
        + rest
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "does not exist" in result.stdout


def test_the_linter_refuses_a_cycle_that_does_not_close(tmp_path):
    """A cycle whose members do not form a loop reads as a decision and changes nothing.

    `C-BAT-THERMAL` named `E-BUS-GNC` — bus to the avionics computer — as its third member, which
    leads nowhere near the coldplate, so the declaration named three edges of which only two were
    on the loop. The check asks the question nobody had asked of any of the five cycles: does the
    back-edge's `to` actually reach its `from` through the other members?
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "coupling.yaml"
    text = path.read_text()
    old = "    members: [E-PLATE-BAT, E-BAT-BUS, E-BUS-PUMP, E-PUMP-COOL, E-COOL-TRANSPORT, E-TRANSPORT-PLATE]"
    assert old in text, "the fixture no longer matches C-BAT-THERMAL"
    path.write_text(text.replace(old, "    members: [E-PLATE-BAT, E-BAT-BUS, E-BUS-GNC]", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "does not close" in result.stdout


def test_every_crew_member_has_a_station_in_every_vehicle_they_can_board():
    """Which *station*, not merely which vehicle — and the two are different questions.

    `location_phase_default: csm` says all three crew are in the CSM before undocking, and it is
    correct. But `ask_crew`'s perception bound is computed per **station**, and
    `domains/crew/components.yaml#display_contract` gives the CSM's three stations three different
    panel sets and three different `cannot_see` lists — so a question asked from "csm" is a question
    asked from nowhere. The corpus named three crew and three stations and never said who sat where.

    The map is `chosen`, with its reasoning in the file, and these assertions are the parts of it
    that are not a matter of choice: the vocabulary, the surface party, and that no two people are
    given one seat.
    """
    mission = yaml.safe_load((VEHICLE / "mission.yaml").read_text())
    stations = {
        str(p.get("id"))
        for p in yaml.safe_load((VEHICLE / "channels.yaml").read_text()).get("crew_positions") or []
    }
    people = mission["crew"]["positions"]
    assert len(people) == 3, people

    for person in people:
        declared = person.get("stations")
        assert declared, f"{person['id']} has no station map"
        for vehicle, station in declared.items():
            assert station in stations, f"{person['id']}: {station!r} is not a crew position"
            if vehicle == "lm":
                assert person["goes_to_surface"], (
                    f"{person['id']} has an LM station and does not go to the surface"
                )
        if person["goes_to_surface"]:
            assert "lm" in declared, f"{person['id']} goes to the surface with no LM station"
        else:
            assert "lm" not in declared, f"{person['id']} has an LM station and never boards"
        assert person.get("stations_provenance", {}).get("reason"), (
            f"{person['id']}'s station map is a decision and states no reason"
        )

    # No two crew share a seat: one station means one perception bound.
    for vehicle in ("csm", "lm"):
        seated = [p["stations"][vehicle] for p in people if vehicle in p.get("stations", {})]
        assert len(seated) == len(set(seated)), f"two crew share a {vehicle} seat: {seated}"


def test_the_plant_reports_where_each_crew_member_is_and_where_it_cannot():
    """The projection the perception bound needs, and the gap it makes visible.

    Three declarations answer "what can this person tell me right now" and none answered it alone:
    `vehicle.yaml#configurations` says which vehicle carries crew, `mission.yaml#phases` lists the
    configurations a phase passes through, and the station map says which seat each person takes.
    Keying on (phase, configuration) rather than on phase is what makes `lunar_orbit` answerable —
    it runs from docked to undocked, so "where is the commander" has two true answers and reporting
    neither would be worse than reporting both.

    The last assertion is the one worth keeping: `descent` and `surface` name only LM
    configurations, so the CSM pilot is placed by no configuration in either. That is a gap in the
    corpus rather than in this function, and it is now a value the plant computes rather than a
    paragraph in a debt list.
    """
    result = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "plant.py"), "--crew"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "translunar_coast" in out and "csm_lower_equipment_bay" in out
    # A phase that spans a docking reports both of its configurations.
    assert out.count("lunar_orbit ") >= 2 or out.count("  lunar_orbit") >= 2, out[:600]
    # Every crew member is placed in every phase — and the two that could not place the CM pilot
    # until `also_present` existed are asserted by *name*, because "every crew member placed" would
    # pass just as well if the phase lists had been rewritten instead.
    summary = out.split("\n\n", 1)[1]
    assert "UNPLACED" not in summary, summary
    for phase in ("descent", "surface"):
        line = next((ln for ln in summary.splitlines() if ln.strip().startswith(phase)), None)
        assert line and "every crew member placed" in line, line
        assert "'csm'" in line and "'lm'" in line, (
            f"{phase} places everyone without the CSM being present, which is the gap the "
            f"`also_present` declaration exists to close: {line}"
        )


def test_every_objective_says_who_settles_it_and_from_what(tmp_path):
    """A challenge whose definition of success is prose has no score.

    The `term` field is prose and should be — it is what a person reads. What it could not do is say
    *who* settles the objective or *from what*: four of the nine terms named a channel inside a
    sentence, `thermal_margin` ("worst zone margin, all phases") named none at all, and the three
    outcome objectives were sentences no machine can read.

    `evaluated_by` is the boundary this folder draws everywhere else, applied to scoring. The
    interesting declaration is `crew_survive`, which is `far_side` and names `crew.available`: the
    vehicle contributes an availability state that distinguishes resting from incapacitated and
    **cannot say "dead"**, because `apollo_diode.md:754` puts a model of a person out of scope. An
    objective whose contribution is narrower than its term is a thing the scorer needs to know, and
    saying so is the point.
    """
    counter = iter(range(8))

    def refusal(objective: str, old: str, new: str, needle: str) -> None:
        definition = copy_definition(tmp_path / f"obj{next(counter)}")
        path = definition / "mission.yaml"
        text = path.read_text()
        assert old in text, f"the fixture no longer matches {old!r}"
        path.write_text(text.replace(old, new, 1))
        out = run_linter(definition).stdout
        assert needle in out, out[-800:]
        assert objective in out, out[-800:]

    refusal(
        "o2_margin",
        "    evaluated_by: vehicle\n    channels: [res.o2_remaining_kg]",
        "    channels: [res.o2_remaining_kg]",
        "evaluated_by None",
    )
    refusal(
        "o2_margin",
        "    evaluated_by: vehicle\n    channels: [res.o2_remaining_kg]",
        "    evaluated_by: vehicle",
        "settled by the vehicle",
    )
    refusal(
        "o2_margin",
        "channels: [res.o2_remaining_kg]",
        "channels: [res.o2_imaginary_kg]",
        "not a registered channel",
    )

    # And the shipped objectives are all evaluable, which is the positive half.
    mission = yaml.safe_load((VEHICLE / "mission.yaml").read_text())
    for objective in mission["objectives"]:
        assert objective["evaluated_by"] in {"vehicle", "far_side", "external"}, objective
        if objective["evaluated_by"] == "vehicle":
            assert objective.get("channels"), objective
        if objective["kind"] == "margin":
            assert objective.get("sense"), objective


def test_the_linter_refuses_a_tightening_profile_that_widens(tmp_path):
    """D-05's narrowing rule, and the defect that made it worth checking.

    `thermal_diode.md:823-826` states it as a design constraint rather than a preference: "the model
    that reasons about the spacecraft must not also be able to rewrite the limits by which its
    reasoning is constrained". Each domain's `profile_selection` says the second half in its own
    words — "An agent may select a profile revision and may never edit one" — and an alternative
    profile exists so that an agent wanting more margin has somewhere legitimate to go.

    **The direction a factor moves depends on the comparator, and one number cannot do both.**
    Tightening a *ceiling* means lowering it; tightening a *floor* means raising it. Three of the
    four domains had chosen whichever direction suited the thresholds they happened to have, so
    `power`'s `tight` profile — selected by a fleet that wanted warning *earlier* — dropped the bus
    undervoltage ladder from 26.5 V to 23.85 V and widened the envelope it was supposed to narrow.
    A profile whose name promises margin and whose arithmetic delivers less of it is worse than no
    profile: it is a decision an agent can make in good faith and lose by.
    """
    counter = iter(range(8))

    def refusal(old: str, new: str, needle: str) -> str:
        definition = copy_definition(tmp_path / f"prof{next(counter)}")
        path = definition / "domains" / "power" / "profiles.yaml"
        text = path.read_text()
        assert old in text, f"the fixture no longer matches {old!r}"
        path.write_text(text.replace(old, new, 1))
        out = run_linter(definition).stdout
        assert needle in out, out[-800:]
        return out

    # The needle is short because the report word-wraps: "lowers a floor" can straddle a line.
    refusal("below: 1.1111", "below: 0.9", "below factor of 0.9")
    refusal("below: 1.1111", "below: 0.9", "lowers")
    refusal("above: 0.9", "above: 1.1", "above factor of 1.1")
    refusal("selectable_by: A1", "selectable_by: A9", "not one of")
    # A profile applied to both comparators has to say which way each one moves.
    refusal(
        "      factors:\n        below: 1.1111\n        above: 0.9\n",
        "",
        "declares no `factors`",
    )


def test_no_verb_may_edit_a_threshold(tmp_path):
    """D-05 stated as a refusal, and vacuous today — which is the point.

    Every verb mentions thresholds only in its `interlocks`, which is the legitimate direction: a
    verb is *guarded by* a limit, never the thing that writes one. None declares a write at all.
    That is one line of a future domain away from being false, and the thing it protects is the
    experiment — an agent that can widen its own envelope has not been tested on the envelope.
    """
    definition = copy_definition(tmp_path / "immutable")
    path = definition / "domains" / "power" / "commands.yaml"
    text = path.read_text()
    assert "  - verb: set_load\n" in text, "the fixture no longer matches set_load"
    path.write_text(
        text.replace(
            "  - verb: set_load\n", "  - verb: set_load\n    writes: [bus_a_undervoltage]\n", 1
        )
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "D-05" in result.stdout, result.stdout[-700:]
    assert "bus_a_undervoltage" in result.stdout


def test_the_linter_refuses_an_alarm_inside_its_channel_s_band(tmp_path):
    """The check that could not be written until `range_kind` existed, and what it found.

    `range` carries two meanings and the numbers do not distinguish them. On a physical channel it
    is an acceptable operating *band* and every alarm fires outside it — cabin pressure ranges
    4.8-5.2 psia with events at <4.5 and <3.5. On a reserve channel it is the quantity's full
    *scale* and the alarms fire inside it — `rcs.propellant_remaining_pct` ranges 0-100 with a
    reserve at <25, which is inside a full span and correct. So "an alarm must lie outside its
    channel's range" would refuse 34 legitimate thresholds, which is how the ambiguity was found:
    the check was written, it refused things that were right, and the missing piece turned out to
    be the field rather than the thresholds.

    Two exemptions, and both are the threshold *saying* it measures something else: a `point_units`
    differing from the channel's own unit covers the six rate thresholds that watch a level channel
    with a per-minute limit, and `gated_by` covers a threshold the schema forced onto a channel it
    is not about. Without one of the two, an alarm inside its own band has nothing to explain it.
    """

    def refusal(old: str, new: str, needle: str) -> str:
        definition = copy_definition(tmp_path / f"band{abs(hash((old, new))) % 10000}")
        path = definition / "domains" / "power" / "profiles.yaml"
        text = path.read_text()
        assert old in text, f"the fixture no longer matches {old!r}"
        path.write_text(text.replace(old, new, 1))
        out = run_linter(definition).stdout
        assert needle in out, out[-800:]
        return out

    # `bus_a_undervoltage` asserts at 26.5 on a band of 27.0-30.5 — outside, and correct.
    refusal("assert: 26.5", "assert: 28.0", "inside the region")

    # And the exemption: the same threshold, told to say it measures something else, passes.
    definition = copy_definition(tmp_path / "exempt")
    path = definition / "domains" / "power" / "profiles.yaml"
    text = path.read_text()
    path.write_text(
        text.replace(
            "assert: 26.5",
            'assert: 28.0\n    point_units: "a different quantity from the channel\'s own"',
            1,
        )
    )
    assert "inside the region" not in run_linter(definition).stdout


def test_the_linter_refuses_a_range_it_cannot_read(tmp_path):
    """Every numeric range declares whether it is a band or a scale, and a band has width.

    The field was assigned by evidence rather than by taste — a range with an alarm strictly inside
    it cannot be a band, so it is a scale — and the rule's blind spot is a channel whose range is a
    band *and wrong*. One was found that way: `thermal.zone_[id]_t_c` declared `[5, 40]` while four
    of its own thresholds asserted inside it and `lm_descent_freeze` asserted below minus five,
    because it is a six-zone template and no single band describes six zones.
    """

    def refusal(old: str, new: str, needle: str) -> None:
        definition = copy_definition(tmp_path / f"rk{abs(hash((old, new))) % 10000}")
        path = definition / "channels.yaml"
        text = path.read_text()
        assert old in text, f"the fixture no longer matches {old!r}"
        path.write_text(text.replace(old, new, 1))
        out = run_linter(definition).stdout
        assert needle in out, out[-800:]

    # A numeric range with no `range_kind` at all. The declaration sits under a comment block, so
    # the removal is by pattern rather than by the two adjacent lines.
    definition = copy_definition(tmp_path / "noKind")
    path = definition / "channels.yaml"
    text = path.read_text()
    stripped = re.sub(
        r"(    range: \[27\.0, 30\.5\]\n)(    #.*?\n)*    range_kind: band\n",
        r"\1",
        text,
        count=1,
    )
    assert stripped != text, "the fixture no longer matches the bus voltage range"
    path.write_text(stripped)
    out = run_linter(definition).stdout
    assert "range_kind None" in out, out[-800:]
    # A band with no width is not a band.
    refusal("    range: [248, 269]", "    range: [248, 248]", "no width")


def test_the_linter_holds_the_power_inventory_to_its_own_arithmetic(tmp_path):
    """`demand_w`, `inrush_w`, `bus`, `rated_w`, `ah` and `v_nominal` were read by nothing.

    Seventeen components and twenty-five loads, so the whole quantitative inventory was a set of
    numbers with no arithmetic between them. The linter has enforced the *mass* closure since the
    beginning; these are the same check one domain over, and the load budget happens to close
    (CSM 1723 W, LM 1007 W) with nothing keeping it closed.

    The fourth relationship is the one with teeth: `power.battery_soc_pct` is a percentage whose
    denominator was declared nowhere, and `battery_charge_j` is a stock with no capacity, so what
    the vehicle carries in joules existed only as a product nobody computed. It is declared now —
    and the LM's is declared in *three* parts, because the descent batteries are jettisoned with
    the descent stage and the ascent flies on 16,576 Wh against a 3.5-hour phase.
    """

    def refusal(old: str, new: str, needle: str) -> str:
        definition = copy_definition(tmp_path / f"power{abs(hash((old, new))) % 10000}")
        path = definition / "domains" / "power" / "components.yaml"
        text = path.read_text()
        assert old in text, f"the fixture no longer matches {old!r}"
        path.write_text(text.replace(old, new, 1))
        out = run_linter(definition).stdout
        assert needle in out, out[-800:]
        return out

    refusal("csm_total_demand_w: 1723", "csm_total_demand_w: 1800", "its loads sum to")
    refusal("bus: csm_bus_a", "bus: csm_bus_z", "no component of class")
    refusal("csm_battery_energy_wh: 3360", "csm_battery_energy_wh: 3000", "its cells carry")
    # The staged split is the number that decides whether the ascent can be flown.
    refusal(
        "lm_battery_energy_ascent_stage_wh: 16576",
        "lm_battery_energy_ascent_stage_wh: 20000",
        "against a stated total",
    )


def test_the_linter_refuses_an_electrical_inventory_that_drifted(tmp_path):
    """One machine in two files, and no sentence saying so.

    `vehicle.yaml#electrical` is the vehicle-level view — what it carries, with the mass each item
    contributes to the mass closure. `domains/power/components.yaml` is the domain's view: the same
    hardware, one entry per unit, with the bus each load sits on. Both are right, they agreed on
    every comparable quantity when this check was written, and **nothing was keeping them
    agreeing** — which is the whole of the problem. A battery re-rated in one file and not the other
    is two machines wearing one name, and the mass closure would go on summing the mass of the one
    nobody flies.

    The voltage assertion is the one that is not a plain equality, and it is the interesting one:
    the two files express the same cell in the shapes their readers need — a group carries a
    *range* (open-circuit down to loaded), a unit carries the nominal it is modelled at — and the
    claim the two shapes make about each other is that the nominal lies inside the range.
    """

    def refusal(rel: str, old: str, new: str, needle: str) -> str:
        definition = copy_definition(tmp_path / f"elec{abs(hash((old, new))) % 10000}")
        path = definition / rel
        text = path.read_text()
        assert old in text, f"the fixture no longer matches {old!r}"
        path.write_text(text.replace(old, new, 1))
        out = run_linter(definition).stdout
        assert needle in out, out[-800:]
        return out

    refusal("vehicle.yaml", "modules: 3", "modules: 4", "declares 4 module(s)")
    refusal("vehicle.yaml", "power_w_each: 1420", "power_w_each: 1200", "is rated")
    refusal(
        "vehicle.yaml",
        "lm_ascent:\n      domain_group: battery_lm_ascent\n      count: 2\n      ah: 296",
        "lm_ascent:\n      domain_group: battery_lm_ascent\n      count: 2\n      ah: 300",
        "is 296 Ah",
    )
    refusal(
        "vehicle.yaml",
        "v: 28\n      mass_kg_each: 56.7",
        "v: 24\n      mass_kg_each: 56.7",
        "is modelled at",
    )
    # The range/nominal claim: a nominal outside the loaded range is not inside it.
    refusal("vehicle.yaml", "min_loaded_v: 27", "min_loaded_v: 30", "not inside it")
    # And a link that names nothing.
    refusal(
        "vehicle.yaml",
        "domain_group: battery_csm",
        "domain_group: battery_nope",
        "matches no component",
    )


def test_the_linter_rederives_the_lunar_blackout(tmp_path):
    """The vehicle's one derived figure, and nothing was re-doing its arithmetic.

    `mission.yaml#comms_blackout`'s comment makes the claim in as many words: "Apollo's
    loss-of-signal was about 45 minutes per revolution. The two figures differ by the orbit's
    eccentricity and by the Earth's own 1.8-degree disc... so the derivation is right to within the
    effects it deliberately omits, and that is a **stronger** statement than a citation would be."
    It is stronger only if somebody redoes the arithmetic, and no tool read the block at all —
    which is exactly the arrangement that let `E-RAD-WATER` say 3.8e-7 while its own relation
    computed 4.082e-7, a 7 % disagreement nobody could see.

    The block's inputs were not data either: `mu_moon = 4902.8` lived inside the `relation`
    sentence, so the derivation could not be reproduced from the file without parsing prose.
    """
    definition = copy_definition(tmp_path / "blackout")
    path = definition / "mission.yaml"
    text = path.read_text()
    for name, value in (
        ("orbit", "{altitude_km: 100, period_min: 117.8}"),
        ("moon_radius_km", "1737.4"),
        ("mu_moon_km3_s2", "4902.8"),
    ):
        assert f"{name}: {value}" in text or f"{name}: {{{value}}}" in text or value in text, name

    broken = text.replace("duration_min: 46.5", "duration_min: 43.0", 1)
    assert broken != text, "the fixture no longer matches comms_blackout"
    path.write_text(broken)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "its own derivation gives" in result.stdout, result.stdout[-700:]
    assert "duration_min" in result.stdout


def test_the_linter_rederives_where_the_earth_is_from_the_landing_site(tmp_path):
    """The site decides one thing nothing else does: whether the LM can be heard at all.

    The coordinates are `chosen` — `apollo_diode.md:1206` asks that the scenario not match a
    historical site closely enough for a fleet to take the shortcut, and the corpus carries no
    coordinates for any site, flown or otherwise, so there is nothing to check the *choice* against.
    The geometry the choice produces is another matter, and it is what this covers: the Earth's
    elevation from the site, the libration envelope around it, and how far it moves across the
    surface phase.

    The last of those is the assertion that makes the model mean something. At 0.075 deg/h, the
    sub-Earth point crosses 1.6 degrees in the 21.5-hour surface stay — so the LM is in contact
    throughout or never, and a site whose link appeared and disappeared inside one phase would be a
    different mission rather than a different number.
    """

    def refusal(old: str, new: str, needle: str) -> str:
        definition = copy_definition(tmp_path / f"site{abs(hash((old, new))) % 1000}")
        path = definition / "mission.yaml"
        text = path.read_text()
        assert old in text, f"the fixture no longer matches {old!r}"
        path.write_text(text.replace(old, new, 1))
        out = run_linter(definition).stdout
        assert needle in out, out[-700:]
        return out

    refusal(
        "earth_elevation_deg: 41.3",
        "earth_elevation_deg: 30.0",
        "the geometry gives",
    )
    refusal("longitude_deg: 47.5", "longitude_deg: 150.0", "below the horizon")
    refusal(
        "elevation_variation_over_surface_deg: 1.61",
        "elevation_variation_over_surface_deg: 0.01",
        "moves it",
    )

    # And a site whose *mean* link is fine but whose envelope is not: at lat 0 that is lon 85,
    # where the Earth stands 5 degrees up and libration takes it 2.9 below.
    definition = copy_definition(tmp_path / "envelope")
    path = definition / "mission.yaml"
    text = path.read_text()
    text = text.replace("latitude_deg: 12.4", "latitude_deg: 0.0", 1)
    text = text.replace("longitude_deg: 47.5", "longitude_deg: 85.0", 1)
    text = text.replace("earth_elevation_deg: 41.3", "earth_elevation_deg: 5.0", 1)
    path.write_text(text)
    out = run_linter(definition).stdout
    assert "libration envelope" in out, out[-700:]


def test_the_two_halves_of_the_vehicle_have_opposite_comms(tmp_path):
    """The site's consequence, and the reason it is worth a decision rather than a default.

    In orbit the CSM is silent 46.5 minutes in every 117.8 — 39 % of the time. On the surface the
    LM is not silent at all, because a near-side site has the Earth permanently in view. So during
    `descent` and `surface` a fleet hears the LM and not the CSM, and the two trade places at the
    orbit's cadence during `lunar_orbit`. That is what a 100 km orbit and a near-side landing site
    do, and it is why the LM-as-lifeboat decision is affordable: the half of the vehicle the crew
    would move into is the half that can always be talked to.
    """
    result = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "plant.py"), "--blackout"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "never loses the link" in out, out
    assert "(12.4, 47.5)" in out, out
    assert "41.3 deg" in out and "1.61 deg" in out, out
    assert "silent 39 %" in out, out


def test_the_plant_computes_the_second_clock():
    """A phase declares one duration and an orbit declares another, and nothing joined them.

    "Affects `surface`" and "costs `surface` eight and a half hours of contact" are different
    statements, and only the second tells a fleet what it is planning around. The projection's own
    docstring says what it must not be read as — the figure is for a vehicle in a 100 km circular
    lunar orbit for the whole phase, which is the CSM and only the CSM, because the LM is on the
    surface for most of `surface` and a vehicle on the surface near the sub-Earth point has the
    Earth fixed in its sky.
    """
    result = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "plant.py"), "--blackout"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    for phase in ("lunar_orbit", "descent", "surface", "ascent_rendezvous", "lunar_orbit_docked"):
        assert phase in out, phase
    for phase in ("translunar_coast", "transearth_coast", "entry"):
        assert phase not in out, f"{phase} is declared not affected and appears anyway"

    # The arithmetic is the derivation's own: 46.5 min silent per 117.8 min revolution.
    descent = next(ln for ln in out.splitlines() if ln.strip().startswith("descent"))
    minutes = 2.5 * 60
    revolutions = minutes / 117.8
    assert f"{minutes:7.1f}" in descent, descent
    assert f"{revolutions:5.2f} rev" in descent, descent
    assert f"{revolutions * 46.5:6.1f}" in descent, descent


def test_the_linter_refuses_a_crew_the_configuration_cannot_hold(tmp_path):
    """The crew are described twice, in two files, and nothing had compared the two.

    `mission.yaml#crew` is a personnel model — `size`, `surface_party`, `goes_to_surface`,
    `location_phase_default`. `vehicle.yaml#configurations` is a hardware model — `crew_aboard` and
    `crew_in`. Both are right, they overlap on every question a fleet can ask, and **all five fields
    were read by nothing**: not by a tool, not by the other file, not by a sentence in any document.

    Each mutation here is a way the two could disagree while both looking complete, and the two
    that are not simple mismatches are the interesting ones. `crew_in` is anchored to the *station*
    vocabulary's own prefixes, because otherwise the check is circular — `crew_in` validated against
    `location_phase_default` and that against `crew_in` — and a configuration saying the crew are in
    a `cockpit` would agree with a mission saying the same.
    """
    counter = iter(range(4))

    def refusal(rel: str, old: str, new: str) -> str:
        definition = copy_definition(tmp_path / f"crew{next(counter)}")
        path = definition / rel
        text = path.read_text()
        assert old in text, f"the fixture no longer matches {rel}"
        path.write_text(text.replace(old, new, 1))
        return run_linter(definition).stdout

    out = refusal("mission.yaml", "surface_party: 2", "surface_party: 3")
    assert "is the party the LM carries" in out, out[-600:]

    out = refusal("mission.yaml", "size: 3", "size: 4")
    assert "nobody is standing in" in out, out[-600:]

    out = refusal("vehicle.yaml", "crew_in: csm", "crew_in: cockpit")
    assert "not the prefix of any station" in out, out[-600:]

    out = refusal("mission.yaml", "goes_to_surface: false", "waved_at_surface: false")
    assert "does not say whether" in out, out[-600:]


def test_the_linter_refuses_a_channel_nothing_publishes(tmp_path):
    """Every registered channel must have a declared source, or the vehicle publishes nothing.

    This is the check whose absence let 27 channels sit in the registry with no producer: a
    threshold watching a value nobody computes, a crew position told it can read a gauge that does
    not exist, a failure chain whose first clue is never emitted. Every other check runs from a
    name *to* the registry; this is the one that runs back.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "presentation.yaml"
    text = path.read_text()
    anchor = "  - channel: mission.abort_latched\n"
    assert anchor in text, "the fixture no longer matches presentation.yaml"
    head, _, tail = text.partition(anchor)
    block, _, rest = tail.partition("  - channel: ")
    path.write_text(head + block + "  - channel: " + rest)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "nothing publishes it" in result.stdout


def test_the_linter_refuses_a_key_written_twice(tmp_path):
    """A duplicate key is how an absorbed list item destroys the entry above it.

    PyYAML accepts a duplicate and lets the last one win, which makes it the quietest structural
    fault in the format — and it is the *signature* of this repository's recurring one, where a
    block scalar's content is indented to the same depth as a list item that follows, so the item
    is absorbed into the prose and its keys collide with the entry above. It found 49 of them
    across five files, including two whole cycles and 21 point entries.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "mission.yaml"
    text = path.read_text()
    anchor = "  post_injection_speed_m_s: 10834"
    assert anchor in text, "the fixture no longer matches mission.yaml"
    path.write_text(text.replace(anchor, "  met_at_state: 0.0\n" + anchor, 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "a second time in the same mapping" in result.stdout


def test_the_linter_refuses_a_multi_state_node_with_no_declared_order(tmp_path):
    """Ten nodes are advanced by more than one state, and the tiebreak silently decided all ten.

    This is not ambiguity, it is a wrong answer waiting to happen: the frozen lexicographic rule
    sorts `link_snr` before `tx_power`, and transmit power is a term in the link budget — so the
    derived order would compute every signal-to-noise ratio from last tick's power. Each node
    with more than one producing state now declares either its order or that it has none, and
    `independent` is a permitted answer that has to carry a reason.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "coupling.yaml"
    text = path.read_text()
    anchor = "    state_order: [tx_power, link_snr]\n"
    assert anchor in text, "the fixture no longer matches the `link` node"
    path.write_text(text.replace(anchor, "", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "declares no `state_order`" in result.stdout


def test_the_linter_refuses_a_state_order_that_is_not_the_group(tmp_path):
    """The declaration has to be the group, in the order it advances — no more and no less.

    A `state_order` missing a state leaves that state to the tiebreak, which is the defect the
    declaration exists to remove; one naming a state the node does not carry would order a state
    that advances something else.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "coupling.yaml"
    text = path.read_text()
    anchor = (
        "    state_order: [pyro_fired, lm_separation_state, descent_stage_state, configuration]\n"
    )
    assert anchor in text, "the fixture no longer matches `structure_config`"
    path.write_text(
        text.replace(anchor, "    state_order: [lm_separation_state, configuration]\n", 1)
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "has to be the group" in result.stdout


def test_the_derived_order_puts_transmit_power_before_the_link_budget(tmp_path):
    """The order is derived, so it is checkable: `tx_power` advances before `link_snr`.

    The `--order` view is the artifact `plant.md:71` promises, and the intra-node order is the
    part the tiebreak would have got wrong. Asserting the pair rather than the whole 39-node list
    keeps the test about the property rather than about the current shape of the graph.
    """
    result = subprocess.run(
        [sys.executable, str(LINTER), "--dir", str(VEHICLE), "--order"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    section = result.stdout.split("32. link")[1] if "32. link" in result.stdout else result.stdout
    assert "tx_power" in section and "link_snr" in section, result.stdout[-2000:]
    assert section.index("tx_power") < section.index("link_snr"), (
        "transmit power has to advance before the link budget it is a term of"
    )
    assert "[order undeclared]" not in result.stdout, (
        "every multi-state node declares its order, so nothing is left to the tiebreak"
    )


def test_the_linter_refuses_an_event_nothing_implements(tmp_path):
    """A dictionary that promises an alarm the vehicle does not raise is worse than silence.

    `channels.yaml`'s `events` field is apollo's prose and the thresholds are the machine-readable
    form of the same promises, and nothing joined them. The audit that did found **53 of 118
    channels declaring events that no threshold watched** — some genuine holes, some publications,
    and some implemented by a threshold on *another* channel that measures the same quantity from
    a different domain's side. Each channel with events now declares which kind it is, and the
    kinds are checkable.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "power" / "profiles.yaml"
    text = path.read_text()
    anchor = "  - id: bus_a_current_high\n"
    assert anchor in text, "the fixture no longer matches domains/power/profiles.yaml"
    head, _, tail = text.partition(anchor)
    block, _, rest = tail.partition("\n  - id: ")
    path.write_text(head + rest)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "no threshold watches it" in result.stdout


def test_the_linter_refuses_an_event_class_with_nothing_to_classify(tmp_path):
    """A class on a channel with no events is a field somebody filled in because it was there.

    The reverse direction matters because it is how a classification rots: a channel's events are
    removed or renamed and the class stays, and a class with nothing behind it reads as a claim
    that something is monitoring a channel nobody described.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "channels.yaml"
    text = path.read_text()
    anchor = "  - id: comm.link_mode\n"
    assert anchor in text, "the fixture no longer matches channels.yaml"
    head, _, tail = text.partition(anchor)
    block, _, rest = tail.partition("  - id: ")
    broken = re.sub(r"^    events: \[.*\]\n", "", block, count=1, flags=re.M)
    assert broken != block, "the fixture no longer matches comm.link_mode"
    path.write_text(head + anchor + broken + "  - id: " + rest)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "no events" in result.stdout


def test_the_linter_refuses_a_realised_by_that_names_no_threshold(tmp_path):
    """`realised_by` is the commonest class, and the one that has to name its implementer.

    `eclss.cabin_temp_c` and `thermal.zone_[id]_t_c` are one cabin temperature seen from two
    domains' sides, so the eclss channel's "<10, >30" event is kept by the *thermal* domain's
    `csm_cabin_low`/`csm_cabin_high`. Naming them makes the claim checkable rather than plausible;
    a `realised_by` with nothing named is an assertion that something, somewhere, is watching.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "channels.yaml"
    text = path.read_text()
    anchor = "    event_thresholds: [csm_cabin_low, csm_cabin_high]\n"
    assert anchor in text, "the fixture no longer matches eclss.cabin_temp_c"
    path.write_text(text.replace(anchor, "    event_thresholds: [no_such_threshold]\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "no domain declares a threshold by that id" in result.stdout


def test_the_linter_refuses_a_point_whose_source_exists_nowhere(tmp_path):
    """A `from` that resolves to nothing silently skips the enum binding.

    This is the check that surfaced the vehicle's oldest surviving duplication: `eclss.cabin_temp_c`
    and `thermal.zone_csm_cabin_t` were **one cabin temperature published twice**, produced by one
    state and read by two sets of thresholds. It survived because the two points named their
    sources differently — one a state, the other a coupling node — and nothing compared them. The
    same check found `power.battery_temp_c` naming a state that exists nowhere while two thresholds
    watched it, and the crew's switch and breaker channels naming *the hatch*.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "power" / "points.yaml"
    text = path.read_text()
    anchor = "  - channel: power.battery_temp_c\n    from: battery_thermal_state\n"
    assert anchor in text, "the fixture no longer matches domains/power/points.yaml"
    path.write_text(
        text.replace(anchor, "  - channel: power.battery_temp_c\n    from: no_such_state\n", 1)
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "neither a state in this domain nor a coupling node" in result.stdout


def test_the_linter_refuses_a_point_that_reads_another_domains_state(tmp_path):
    """A point reads a state it owns or a coupling node, and never a peer's state directly.

    Reading across the window's internal boundary bypasses the edge that is supposed to carry the
    value, and it hides a missing producer: the crew's `controls.switches` and `controls.breakers`
    both named the structure domain's `hatch_state`, so two channels had no source of their own and
    the crew domain had no switch or breaker state at all.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "crew" / "points.yaml"
    text = path.read_text()
    anchor = "  - channel: controls.switches\n    from: switch_panel\n"
    assert anchor in text, "the fixture no longer matches domains/crew/points.yaml"
    path.write_text(
        text.replace(anchor, "  - channel: controls.switches\n    from: hatch_state\n", 1)
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "a state in another domain" in result.stdout


def test_the_reference_plant_loads_the_whole_world():
    """The configuration is implementable, and this is the evidence rather than the claim.

    `tools/plant.py` loads every state in the definition over the derived schedule, builds a frame
    in apollo's shape from the declared field list, and walks the tick in schedule order until it
    reaches something it cannot compute — where it says exactly what is missing instead of
    guessing. It imports the linter's `derive_schedule`, so the plant and the linter cannot
    disagree about the order.

    The counts are checked *against the definition* rather than against literals, because a
    literal here goes stale on every round that lands a node — this test has already been edited
    once for that reason, when promoting `guidance` to a service node took the schedule from 39
    nodes to 40. What must not move is the agreement: the plant's world is the coupling graph's
    world, down to the last node and edge.
    """
    result = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "plant.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    definition = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    states = 0
    for path in (VEHICLE / "domains").glob("*/*.yaml"):
        states += len((yaml.safe_load(path.read_text()) or {}).get("state") or [])
    # An edge leaving `command_executive` is a command and `published_evidence` is the sink;
    # neither holds state and neither is scheduled, which is why the two counts differ.
    scheduled = len(definition["nodes"]) - 2
    assert f"{states} states" in result.stdout, result.stdout
    assert f"{len(definition['edges'])} edges" in result.stdout, result.stdout
    assert f"the tick order is {scheduled} nodes" in result.stdout, result.stdout


def test_the_reference_plant_publishes_the_gate_variable_map():
    """The mirror publishes *instantiations*, and §9 check 5 depends on it.

    `presentation.yaml#mirror.variables_are_templated` states the rule and the failure it prevents:
    "a refusal that named the template rather than the instantiation —
    `reserve_floor_<resource>_enable` instead of `reserve_floor_water_cooling_enable` — would be a
    name a fleet cannot act on." So the assertion is not just that the map exists but that **no raw
    template survives into it**, and that closing one instantiation closes the whole verb and names
    the instantiation rather than the template.
    """
    result = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "plant.py"), "--state"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert set(state) >= {"vehicle", "available_commands", "variables", "capability"}

    variables = state["variables"]
    assert len(variables) > len(state["capability"]), (
        "the gate variable map is no larger than the verb list, so the templates did not expand"
    )
    raw = [name for name in variables if "<" in name or ">" in name]
    assert not raw, f"the mirror published {len(raw)} unexpanded templates: {raw[:4]}"
    for row in state["capability"]:
        assert row["gate_variables"], f"{row['verb']} declares a gate with no instantiation"
        for name in row["gate_variables"]:
            assert name in variables, f"{name} is a gate the mirror does not publish"

    # Closing one instantiation closes the verb, and the refusal names the instantiation.
    one = "reserve_floor_water_cooling_enable"
    assert one in variables, "the fixture no longer matches set_reserve_policy's gate"
    result = subprocess.run(
        [
            sys.executable,
            str(VEHICLE / "tools" / "plant.py"),
            "--state",
            "--closed-gate",
            one,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    closed = json.loads(result.stdout)
    row = next(r for r in closed["capability"] if r["verb"] == "set_reserve_policy")
    assert row["available"] is False
    assert one in row["availability_reason"], row["availability_reason"]
    assert "<" not in row["availability_reason"], "the refusal named the template"
    assert "set_reserve_policy" not in closed["available_commands"]


def test_the_linter_refuses_a_gate_template_that_cannot_expand(tmp_path):
    """A gate variable a fleet never sees is a closed gate it cannot name.

    Ten verbs were in this state: eight wrote a bare `<id>` where their own argument was named
    `antenna`, `source`, `load`, `breaker`, `battery`, `engine`, `pump`, `hatch` or `loop`, and two
    declared their values as a sentence — `set_load`'s `load` was
    `[any id in components.yaml#loads]`, which instantiates to nothing. Nothing checked that a
    template *could* expand, so both were invisible until something tried to publish the map.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "propulsion" / "commands.yaml"
    text = path.read_text()
    broken = text.replace("engine_<engine>_arm_enable", "engine_<id>_arm_enable", 1)
    assert broken != text, "the fixture no longer matches arm_engine"
    path.write_text(broken)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "names no enum argument" in result.stdout, result.stdout[-800:]

    # And the other half: values described rather than listed.
    definition = copy_definition(tmp_path / "described")
    path = definition / "domains" / "power" / "commands.yaml"
    text = path.read_text()
    start = text.index("      load:\n        type: enum")
    end = text.index("      state: {type: enum, values: [on, off]}", start)
    path.write_text(
        text[:start]
        + "      load: {type: enum, values: [any id in components.yaml#loads]}\n"
        + text[end:]
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "describing its values" in result.stdout or "describes" in result.stdout, result.stdout[
        -800:
    ]


def test_a_declared_interlock_is_not_a_closed_one():
    """A guard is checked when a command arrives, not standing between a fleet and its verbs.

    The first version of `capability_snapshot` read `commands.yaml`'s `interlocks` list as a
    condition and reported every verb carrying one as unavailable — **32 of this vehicle's 58**,
    including `arm_engine`, `start_burn`, `load_burn`, `set_attitude_target` and
    `set_coolant_pump`, each with an `availability_reason` naming an interlock that was not
    tripped. A fleet reading that `state.json` would have concluded the vehicle was nearly
    unusable, and the console built on it refused all 32 by name.

    Nothing caught it, and the reason is worth keeping: the contract probe submits an *available*
    verb and an *unknown* one, so a snapshot that hides half the vocabulary from itself passes
    every check. **Passing the instrument is not the same as being correct**, and the assertion
    that would have caught this is about the size of the published set rather than about any
    single verb.
    """
    result = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "plant.py"), "--state"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    rows = state["capability"]
    available = [row for row in rows if row["available"]]
    assert len(available) > len(rows) * 0.8, (
        f"only {len(available)} of {len(rows)} verbs are available with no live state; a declared "
        "interlock is being read as a closed one"
    )
    # A guarded verb is available, and its reason says the guard is checked later rather than now.
    guarded = [row for row in available if "interlock(s) checked" in row["availability_reason"]]
    assert guarded, "no verb reports an interlock that is checked at request time"
    assert not [row for row in available if row["availability_reason"].startswith("interlock:")]

    # Supplying the live state that trips one closes exactly that verb.
    result = subprocess.run(
        [
            sys.executable,
            str(VEHICLE / "tools" / "plant.py"),
            "--state",
            "--closed-interlock",
            "rcs_authority_floor",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    tripped = json.loads(result.stdout)
    row = next(r for r in tripped["capability"] if r["verb"] == "request_translation")
    assert row["available"] is False
    assert "rcs_authority_floor" in row["availability_reason"]
    assert len(tripped["available_commands"]) == len(state["available_commands"]) - 1


def test_the_fault_schedule_is_keyed_by_name_not_by_position():
    """Adding a fault must not move any existing fault's events.

    `simulator-design.md:190-198` fixes the stream key as `(master_seed, domain, component_id,
    purpose)` and gives the reason: "Twelve domains arrive incrementally over months. With a shared
    generator — or index-keyed derivation — adding thruster 9 reshuffles every existing stream and
    silently invalidates every prior run." That is the property that makes a recorded run
    comparable to a later one, and it is the kind of property that is true until somebody writes
    `random.Random(seed)` once.

    The check appends a synthetic fault rather than editing a domain, which is the same question
    without mutating the corpus — and it asserts the probe itself drew events, because a comparison
    between two empty schedules proves nothing.
    """
    result = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "faults.py"), "--check", "--seed", "20260912"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "NAME-KEYING HOLDS" in result.stdout, result.stdout
    assert "nothing" not in result.stdout, result.stdout


def test_the_scenario_posture_scales_the_fault_schedule():
    """`apollo_diode.md:370-374`'s difficulty scaling, which nothing applied.

    Three postures differ by 10x in critical hazard and 20x in demand failure, the fault policies
    carry the *nominal* baselines as though they were absolute, and the scheduler read the policies
    and never the postures — so a `crisis` run and a `nominal` run produced the same faults, and the
    experiment's difficulty knob did nothing.

    The check that matters most is the arithmetic rather than the counts: the critical and
    noncritical columns must move by the **same** factor, because the 118 policies declare a bare
    `hazard` and no class, and 19 of the 58 sit between the two baselines. It holds today because
    these particular numbers move together, and the linter now refuses a table where they do not.
    """

    def run(posture: str) -> dict:
        result = subprocess.run(
            [
                sys.executable,
                str(VEHICLE / "tools" / "faults.py"),
                "--seed",
                "20260912",
                "--posture",
                posture,
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    nominal, degraded, crisis = (run(p) for p in ("nominal", "degraded", "crisis"))
    assert nominal["hazard_factor"] == 1.0 and nominal["on_demand_factor"] == 1.0
    assert degraded["hazard_factor"] == 5.0, degraded["hazard_factor"]
    assert crisis["hazard_factor"] == 10.0, crisis["hazard_factor"]
    # Demand failure scales by its own factor: 1e-4 -> 2e-3 is x20 where the hazards move x10.
    assert crisis["on_demand_factor"] == 20.0, crisis["on_demand_factor"]

    counts = [len(p["events"]) for p in (nominal, degraded, crisis)]
    assert counts == sorted(counts) and counts[0] < counts[-1], counts


def test_the_posture_places_a_guaranteed_fault_rather_than_sampling_for_it():
    """`seeded_faults`: "one guaranteed major primary", and apollo says why it is guaranteed.

    `apollo_diode.md:368`: a common-cause event is "explicitly seeded rather than relying on tiny
    random probability". At the nominal critical hazard a 192-hour mission expects 0.0038 events
    from any one fault, so a posture that promised a major failure and then sampled for it would
    deliver an empty mission almost every time.

    The crisis posture's *optional* half is asserted to be absent by default, because "optional"
    is read as the GM's decision — crisis carries `gm_disposition: white_team` — rather than a draw
    at a rate the posture does not declare for a whole mission. Seat it with `--sensor-defect`.
    """

    def run(posture: str, *extra: str) -> dict:
        result = subprocess.run(
            [
                sys.executable,
                str(VEHICLE / "tools" / "faults.py"),
                "--seed",
                "20260912",
                "--posture",
                posture,
                "--json",
                *extra,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    assert not [e for e in run("nominal")["events"] if e.get("guaranteed")], (
        "the nominal posture seeds nothing, by its own `seeded_faults: none`"
    )
    for posture in ("degraded", "crisis"):
        placed = [e for e in run(posture)["events"] if e.get("guaranteed")]
        assert len(placed) == 1, f"{posture} placed {len(placed)} guaranteed fault(s)"
        assert 0 <= placed[0]["met_h"] <= 192.0, placed[0]

    crisis = run("crisis")
    assert "optional latent sensor defect" in crisis["seeded_faults"]
    assert not [e for e in crisis["events"] if "optional" in str(e.get("guaranteed"))], (
        "the optional defect was seated without being asked for"
    )
    seated = run("crisis", "--sensor-defect")
    optional = [e for e in seated["events"] if "optional" in str(e.get("guaranteed"))]
    assert len(optional) == 1, optional
    assert optional[0]["kind"] == "instrument", optional[0]


def test_every_declared_fault_is_either_scheduled_or_armed():
    """The 118 policies split into the ones a rate can schedule and the ones a trigger arms.

    The split matters because sampling an `on_demand_p` fault from a rate would be inventing a rate
    the domain deliberately did not give: `CRW-05-wrong-module-attempt` seeds at `p=1` on "any
    ask_crew whose subject is outside the position's perceivable set", which is not a random event
    at all — it is the certain consequence of an invalid question. A scheduler that treated it as
    stochastic would sometimes let a fleet ask an unanswerable question for free.

    The expected stochastic count is asserted as a **rate**, not a number: 2.1 events over the
    mission is one to three faults per run and a 12 % chance of none, which is a challenge with
    adversity rather than a challenge that is reliably quiet.
    """
    result = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "faults.py"), "--seed", "1"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    header = re.search(r"(\d+) declared faults: (\d+) stochastic, (\d+) armed", result.stdout)
    assert header, result.stdout
    declared, stochastic, armed = (int(g) for g in header.groups())
    assert declared == stochastic + armed
    assert declared > 100, f"only {declared} faults are declared"
    assert armed > 30, "no fault is conditional, which contradicts the policy files"

    # The same seed must produce the same schedule, twice.
    again = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "faults.py"), "--seed", "1", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    repeat = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "faults.py"), "--seed", "1", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert again.stdout == repeat.stdout, "the same seed produced two different schedules"

    events = json.loads(again.stdout)["events"]
    for event in events:
        assert event["perturbs"], f"{event['fault']} perturbs nothing, so it cannot be diagnosed"
        assert 0 <= event["met_h"] <= 192.0, event


def test_the_linter_refuses_a_fault_whose_detection_was_swallowed(tmp_path):
    """Four faults had an empty `detection:` with its three children left at fault level.

    That is the absorbed-list-item shape arriving in a fault policy, and it survived because
    nothing read `detection`: `component`, `mechanism` and `perturbs` were checked and the whole
    diagnostic half of all 118 faults was not. The refusal names the shape rather than the field,
    because the field is present and empty — which is exactly what makes it hard to see.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "domains" / "power" / "fault_policy.yaml"
    lines = path.read_text().split("\n")
    start = next(
        i for i, line in enumerate(lines) if line.strip() == "- id: PWR-01-source-regulation-loss"
    )
    det = next(i for i in range(start, len(lines)) if lines[i] == "    detection:")
    for k in range(det + 1, det + 4):
        if lines[k].startswith("      "):
            lines[k] = lines[k][2:]
    path.write_text("\n".join(lines))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "not a mapping" in result.stdout
    assert "PWR-01-source-regulation-loss" in result.stdout


def test_an_irreversible_event_cannot_fire_without_a_valid_arm_token(tmp_path):
    """Arm-then-commit, on the vehicle's only irreversible verbs.

    `arm_event`'s own help fixes the contract: "Arming does nothing physical: it returns a
    short-lived token bound to this specific event, and it is the only verb on the vehicle whose
    result carries a [token]." Nothing minted one and nothing checked one, so `execute_event` —
    which fires the pyros, the undocking and the staging — accepted any `arm_token`, including
    none. `requires_arm` was enforced by the linter on the *state* and on no *path*, which left
    F-15 (premature staging) reachable by one unarmed command.

    Four things are asserted, and the last two are what make a token a token: it is consumed by
    use, and it is bound to the event it was minted for.
    """
    diode = tmp_path / "diode"
    window = diode / "armed"
    console = [
        sys.executable,
        str(VEHICLE / "tools" / "console.py"),
        "--diode-dir",
        str(diode),
        "--slug",
        "armed",
        "--phase",
        "lunar_orbit",  # `execute_event` is not allowed in every phase, and the gate comes first
    ]
    subprocess.run([*console, "--init"], capture_output=True, check=False)

    def run(command: str) -> str:
        for existing in (window / "output").glob("*.txt"):
            existing.unlink()
        (window / "console.json").write_text(
            json.dumps({"commands": [command], "variables": {}}), encoding="utf-8"
        )
        subprocess.run([*console, "--cycles", "1", "--poll", "0"], capture_output=True, check=False)
        bodies = [p.read_text() for p in (window / "output").glob("*.txt")]
        assert len(bodies) == 1, bodies
        return bodies[0]

    assert "not armed" in run("execute_event event=pyro_fire arm_token=guess")

    armed = run("arm_event event=pyro_fire")
    token = re.search(r"Token: ([0-9a-f]+)", armed)
    assert token, armed
    assert "only result" in armed, armed

    fired = run(f"execute_event event=pyro_fire arm_token={token.group(1)}")
    assert "succeeded" in fired and "consumed" in fired, fired

    # A consumed token is not authority to fire again.
    assert "not armed" in run(f"execute_event event=pyro_fire arm_token={token.group(1)}")
    # And a token is bound to one event.
    assert "not armed" in run(f"execute_event event=lm_undocking arm_token={token.group(1)}")


def test_a_deferred_command_settles_later_and_reports_its_own_result(tmp_path):
    """The contract requires asynchronous completion, and V-02 requires the re-check at effect time.

    "A command that takes longer than one cycle — a burn, a deploy, a self-test — completes
    asynchronously and reports when it is done." A result written at acceptance is a claim about
    the future dressed as a report, so `request_translation` must produce **two** files: an
    acceptance at tick 0 and a settlement at tick 1, the second written by a different process.

    That second process is the point of the test. `pending.json` is "the vehicle's own deferral
    queue" and the console wrote it every cycle and read it never, so a deferral could not survive
    a restart and — since the console is a process per invocation — could never settle at all. The
    same root cause reset the tick counter, which made an absolute `due_tick` meaningless in the
    next run and restarted `seq`, so a second run's frames overwrote the first run's in the ring.
    """
    diode = tmp_path / "diode"
    window = diode / "deferred"
    console = [
        sys.executable,
        str(VEHICLE / "tools" / "console.py"),
        "--diode-dir",
        str(diode),
        "--slug",
        "deferred",
    ]
    subprocess.run([*console, "--init"], capture_output=True, check=False)
    (window / "console.json").write_text(
        json.dumps({"commands": ["request_translation frame=body"], "variables": {}}),
        encoding="utf-8",
    )

    def results() -> list[str]:
        return sorted(p.read_text() for p in (window / "output").glob("*.txt"))

    subprocess.run([*console, "--cycles", "1", "--poll", "0.05"], capture_output=True, check=False)
    first = results()
    assert len(first) == 1, first
    assert "deferrable" in first[0], first[0]

    subprocess.run([*console, "--cycles", "1", "--poll", "0.05"], capture_output=True, check=False)
    second = results()
    assert len(second) == 2, (
        "the deferral did not settle in a second process, so `pending.json` is not being read back"
    )
    settled = [b for b in second if "deferrable" not in b]
    assert len(settled) == 1, second
    assert "succeeded" in settled[0] and "re-checked" in settled[0], settled[0]


def test_a_deferred_command_that_waited_too_long_expires(tmp_path):
    """V-02's `EXPIRED`, and `maximum_queue_age_s` is declared once per verb.

    It was read only by the generator that prints it — 58 declarations reaching a document and
    nothing else — so no command had ever expired. The age is wall-clock because a monotonic
    reading is meaningless in the process that restores the queue, and a queue that cannot be
    restored is not a queue.
    """
    diode = tmp_path / "diode"
    window = diode / "expired"
    console = [
        sys.executable,
        str(VEHICLE / "tools" / "console.py"),
        "--diode-dir",
        str(diode),
        "--slug",
        "expired",
    ]
    subprocess.run([*console, "--init"], capture_output=True, check=False)
    subprocess.run([*console, "--cycles", "1", "--poll", "0.05"], capture_output=True, check=False)

    pending = window / "pending.json"
    state = json.loads(pending.read_text())
    state["pending"] = [
        {
            "verb": "request_translation",
            "command": "request_translation frame=body",
            "accepted_tick": 0,
            "due_tick": state["ticks"],
            "accepted_at": "2020-01-01T00:00:00+00:00",
            "maximum_queue_age_s": 600,
        }
    ]
    pending.write_text(json.dumps(state), encoding="utf-8")
    for existing in (window / "output").glob("*.txt"):
        existing.unlink()

    subprocess.run([*console, "--cycles", "1", "--poll", "0.05"], capture_output=True, check=False)
    bodies = [p.read_text() for p in (window / "output").glob("*.txt")]
    assert len(bodies) == 1, bodies
    assert "EXPIRED" in bodies[0], bodies[0]
    assert "maximum_queue_age_s of 600" in bodies[0], bodies[0]


def test_the_conflict_policy_is_first_valid_wins_and_the_loser_is_told(tmp_path):
    """`apollo_diode.md:578-579`: first valid command in a domain wins, and the loser is told.

    The policy is one sentence and the second half is what makes it a policy: "Later commands are
    **not** silently discarded: they receive `CONFLICT_SUPERSEDED`." V-02 lists that as a
    first-class refusal and explicitly rejects "silent discard (`apollo:579` is explicit that the
    loser must be told)".

    The 58 `conflict_domain` declarations reached nobody until the console read them, and the
    consequence was not a wrong answer but an undefined one: every command was accepted, so two
    agents commanding one actuator in one tick both succeeded. The template makes it sharper than
    that — `prop.<engine>.run` is one domain per engine, so two agents starting *different* engines
    must both be accepted, and a rule that keyed on the verb name would refuse the second.
    """
    diode = tmp_path / "diode"
    window = diode / "conflict"
    console = [
        sys.executable,
        str(VEHICLE / "tools" / "console.py"),
        "--diode-dir",
        str(diode),
        "--slug",
        "conflict",
    ]
    subprocess.run([*console, "--init"], capture_output=True, check=False)

    def run(commands: list[str]) -> list[str]:
        for existing in (window / "output").glob("*.txt"):
            existing.unlink()
        (window / "console.json").write_text(
            json.dumps({"commands": commands, "variables": {}}), encoding="utf-8"
        )
        subprocess.run([*console, "--cycles", "1", "--poll", "0"], capture_output=True, check=False)
        return sorted(p.read_text() for p in (window / "output").glob("*.txt"))

    # Same domain, two verbs: the first wins and the second says so by name.
    bodies = run(["start_burn engine=sps", "stop_burn engine=sps"])
    assert len(bodies) == 2, bodies
    assert sum("accepted" in b for b in bodies) == 1, bodies
    loser = next(b for b in bodies if "accepted" not in b)
    assert "CONFLICT_SUPERSEDED" in loser, loser
    assert "prop.sps.run" in loser, loser
    assert "start_burn" in loser, "the refusal must name what superseded it"

    # Different instantiations of the same template are different domains, so both are accepted.
    bodies = run(["start_burn engine=sps", "start_burn engine=dps"])
    assert len(bodies) == 2, bodies
    assert all("accepted" in b for b in bodies), bodies

    # And the claim is per tick: the superseded command succeeds on the next one.
    bodies = run(["stop_burn engine=sps"])
    assert len(bodies) == 1 and "accepted" in bodies[0], bodies


def test_the_vehicle_passes_the_contract_probe(tmp_path):
    """The window is frozen, shared, and this is the only thing that proves the vehicle meets it.

    `contract/diode_probe.py` is the repository's instrument for the far side of the wall, and
    until `tools/console.py` existed there was nothing to point it at: the vehicle declared a
    conformance table for §9's twelve checks and had never been walked through one of them. The
    probe is deliberately blind to physics — "it only answers: does the window behave the way the
    world is built to expect?" — so a console that claims batches, writes one result per command,
    republishes its state every cycle and advances telemetry on its own is exactly what it tests.

    The assertion is `0 failed` rather than "exit 0", because the probe exits 0 with skips and the
    skip here is real: no deferring verb is reachable at this phase, so §9 check 9 has nothing to
    test. A test that demanded zero skips would be demanding the probe lie.
    """
    diode = tmp_path / "diode"
    console = subprocess.Popen(
        [
            sys.executable,
            str(VEHICLE / "tools" / "console.py"),
            "--diode-dir",
            str(diode),
            "--slug",
            "probe_target",
            "--cycles",
            "600",
            "--poll",
            "0.05",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Wait for everything the window is supposed to contain, because the probe reads the
        # vocabulary from `state.json` and the gates from `HELP.md` *and* `state.json` — and the
        # console announces itself by writing `console.json` **last**, so that a reader attaching
        # at any instant finds a vehicle that can already answer. The first version of the console
        # created the console first and published on its first cycle, and a probe attaching in that
        # gap reported "HELP.md and state.json named none" for a vehicle about to name 226 gates.
        window = diode / "probe_target"
        expected = ("console.json", "state.json", "HELP.md", "pending.json")
        deadline = time.time() + 20
        while time.time() < deadline:
            if all((window / name).exists() for name in expected):
                break
            time.sleep(0.1)
        for name in expected:
            assert (window / name).exists(), f"the console never published {name}"

        probe = subprocess.run(
            [
                sys.executable,
                str(REPO / "contract" / "diode_probe.py"),
                "--diode-dir",
                str(diode),
                "--slug",
                "probe_target",
                "--poll-seconds",
                "0.3",
                "--timeout",
                "15",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert probe.returncode == 0, probe.stdout[-2500:]
        assert "0 failed" in probe.stdout, probe.stdout[-2500:]
        assert "an unknown verb is refused by name" in probe.stdout
        assert "variables survive the claim" in probe.stdout
        # The gate set the probe reads must be the *instantiated* one and nothing else: 226 names,
        # not 58 templates and not 58 verbs mistaken for gates because HELP.md listed them in the
        # form the probe scans.
        gates = re.search(r"gate variables are published\n\s+found (\d+):", probe.stdout)
        assert gates, probe.stdout[-1500:]
        assert int(gates.group(1)) > 200, (
            f"the probe found {gates.group(1)} gate variables; the templates did not expand"
        )
    finally:
        console.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            console.wait(timeout=10)


def test_the_reference_plant_stops_at_a_named_debt(tmp_path):
    """A plant that cannot compute something says what it would need, and never defaults.

    The refusals *are* the build order: they are raised in the order the schedule reaches the
    states, so the first one printed is the first thing to supply. A loader that tolerated a
    missing field would be a loader that had decided a default, which is the one thing this folder
    exists to prevent.
    """
    result = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "plant.py"), "--readiness"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "states fully configured" in result.stdout

    # The build order is in schedule order, and the first blocked state is the first the schedule
    # reaches rather than the first in the file. Which states are blocked moves as values land; the
    # order is the property, so the assertion is on `gnc` sitting before the first `needs`.
    blocked = result.stdout.split("blocked states, in the order")[1]
    assert "needs" in blocked, blocked[:400]
    assert "gnc" in blocked.split("needs")[0], blocked[:400]

    # The first tick stops at a named thing in a named file, and says why. That *shape* is the
    # property under test — which thing it stops at is a fact about the configuration and moves
    # every time a value lands. A stop that named nothing would be a loader that gave up silently;
    # one that named a file that does not exist would be a stop nobody could act on.
    stopped = result.stdout.split("stops at the first thing it cannot compute:")[1]
    named = re.search(r"domains/[\w/.-]+\.yaml:state \w+", stopped)
    assert named, f"the stop names no state: {stopped[:400]!r}"
    where = named.group(0).split(":state")[0]
    assert (VEHICLE / where).exists(), f"the stop names {where}, which is not a file it read"
    why = stopped.split(named.group(0), 1)[1]
    assert len(why.split()) > 5, f"the stop names a place but not a reason: {why[:200]!r}"


def test_the_reference_plant_emits_a_frame_in_the_declared_shape():
    """`presentation.yaml#frame` is a contract only if something can produce a frame from it.

    The emitter builds the envelope from the declared field list and refuses when a declared field
    has no producer — so the frame contract is checked in the same direction as everything else:
    the declaration has to be satisfiable, not merely plausible.
    """
    result = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "plant.py"), "--frame"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    for field in ("schema", "seq", "boot_id", "met_s", "values", "quality", "phase", "vehicle"):
        assert f"{field}:" in result.stdout, f"the frame has no {field!r}"
    assert "aurora.capsule.telemetry.v1" in result.stdout


def test_the_linter_rederives_a_derived_edge_sensitivity(tmp_path):
    """A `derived` value whose arithmetic is stated has to re-derive, on every run.

    This check exists because of one found by hand: `E-RAD-WATER` declared 3.8e-7 while the
    relation beside it computed `1/2.45e6 = 4.082e-7`, and the two had disagreed by 7 % since the
    edge was written. A relation is prose and prose cannot be evaluated — but a `computation` can,
    so sixteen edges now state theirs in a form the linter evaluates, in the same idiom the
    propulsion check uses for the rocket equation and the trajectory check for the ellipse.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "coupling.yaml"
    text = path.read_text()
    anchor = '      computation: "1 / 2.45e6"\n'
    assert anchor in text, "the fixture no longer matches E-WATER-RAD"
    path.write_text(text.replace(anchor, '      computation: "1 / 2.9e6"\n', 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "does not re-derive" in result.stdout


def test_the_linter_refuses_a_computation_it_cannot_evaluate(tmp_path):
    """The expression is arithmetic over literals, and nothing else.

    A `computation` is evaluated by the linter, so it must not be able to name anything: a
    relation that reached a variable would make the check depend on state it does not have, and a
    relation that reached a *function* would make the configuration executable.
    """
    definition = copy_definition(tmp_path / "vehicle")
    path = definition / "coupling.yaml"
    text = path.read_text()
    anchor = '      computation: "1 / 28"\n'
    assert anchor in text, "the fixture no longer matches E-AMP-LOAD"
    injected = (
        "      computation: "
        + chr(34)
        + "__import__(chr(111)+chr(115)).getpid()"
        + chr(34)
        + chr(10)
    )
    path.write_text(text.replace(anchor, injected, 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "cannot evaluate" in result.stdout


def test_every_vehicle_yaml_parses():
    """A file that does not parse is not a definition, and the linter's report is too late.

    This is a cheap guard with an embarrassing history: a flow mapping whose closing brace
    count is wrong parses on the way in and fails on the way out, and the author only finds out
    when something downstream refuses. One second here beats a debugging round later.
    """
    files = sorted(VEHICLE.glob("*.yaml")) + sorted(VEHICLE.glob("domains/*/*.yaml"))
    assert files, "no vehicle definition files found"
    broken = []
    for path in files:
        try:
            yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:  # noqa: PERF203 - one bad file should not hide the rest
            broken.append(f"{path.relative_to(VEHICLE)}: {str(exc).splitlines()[0]}")
    assert not broken, "unparseable vehicle files:\n" + "\n".join(broken)
