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

    # The candidate must be an edge whose *only* fault is the missing value. Some edges are also
    # structurally un-integrable — a ratio into a stock, whose flux is the source's outflow and is
    # declared nowhere — and those keep a debt after the value arrives, which would make this test
    # assert the wrong thing about the wrong edge.
    if str(VEHICLE / "tools") not in sys.path:
        sys.path.insert(0, str(VEHICLE / "tools"))
    from check_vehicle import stock_flux_basis

    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    nodes = coupling["nodes"]
    candidates = []
    for edge in coupling["edges"]:
        if (edge.get("sensitivity") or {}).get("value") != "UNCONFIGURED":
            continue
        if f"coupling.yaml:edge {edge['id']}:" not in strict.stdout:
            continue
        if nodes[edge["to"]].get("kind") == "stock":
            basis, _ = stock_flux_basis(edge, nodes)
            if basis is None:
                continue
        candidates.append(str(edge["id"]))
    assert candidates, f"no coupling edge owes only a value:\n{strict.stdout[:600]}"
    edge_id = candidates[0]

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


def test_no_edge_declares_conserve_any_more():
    """The conservation machinery is dormant, and that is a fact rather than an oversight.

    `conserve` means one quantity travelling between two stocks, so there is no ratio to choose and
    nothing to owe. Two edges carried it — `E-O2-ECLSS` and `E-LM-O2-ECLSS`, each asserting that a
    kilogram of oxygen entering a cabin conserves a kilogram leaving the tank — and round 60
    converted both to `rate`, because the coupling is a *regulator's flow* now rather than a quantity
    travelling between two stocks. The driver is `cabin_o2_supply_csm`, a flow node, and a flow is
    what a rate edge applies.

    So the linter's three conservation refusals — an unset value, an undecidable dimension, anything
    other than a one-for-one ratio — have nothing left to refuse. That is worth asserting rather than
    leaving unremarked: a check with no inputs looks exactly like a check that passes, and this one
    spent its first version passing *vacuously* for a different reason (the dimension lookup returned
    nothing for six node units and the guard skipped the edge).

    The refusals themselves are still exercised by construction in the linter's own suite of tests;
    what this holds is that the vehicle no longer contains the case.
    """
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    conserving = [e["id"] for e in coupling["edges"] if e.get("kind") == "conserve"]
    assert conserving == [], f"an edge declares `conserve` again: {conserving}"

    # Both converted edges are rates now, and both drive a cabin's oxygen mass.
    edges = {e["id"]: e for e in coupling["edges"]}
    for edge_id, advances in (
        ("E-O2-ECLSS", "csm_cabin_o2_kg"),
        ("E-LM-O2-ECLSS", "lm_cabin_o2_kg"),
    ):
        assert edges[edge_id]["kind"] == "rate", edge_id
        assert edges[edge_id]["advances"] == advances, edge_id

    result = run_linter(VEHICLE)
    assert result.returncode == 0, result.stdout[-800:]


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
    text = text.replace(unset, "    rejection_w: 1500", 1)
    # **And the total has to move with it.** `load_budget.total_rejection_capacity_w` is the sum of
    # the parts that have values — it is 4,933 today because the sublimator's figure is the one
    # missing — so supplying the figure and leaving the total is a capacity the vehicle does not
    # have. `check_thermal_budget` refused this fixture the first time it ran, which is the closure
    # doing exactly what it was written for.
    text = text.replace("total_rejection_capacity_w: 4933", "total_rejection_capacity_w: 6433", 1)
    path.write_text(text)

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


def test_a_domain_s_coverage_claim_must_be_true(tmp_path):
    """Every domain makes the same claim, and **eight of eleven were false**.

    Each `fault_policy.yaml` opens its `coverage` block with "Every channel this domain publishes is
    perturbed by at least one fault above, except ..." and names the exceptions. It is the most
    useful claim in the file — it says which channels a fault can never move, which is exactly what
    a fleet should know before spending an afternoon diagnosing one — and nothing read it.

    The drift is structural rather than careless: `perturbs` is edited when a fault is added and
    `unperturbed` is edited when somebody remembers, so the two part company in the direction of the
    claim being *more optimistic* than the policy. `power` said its two battery channels were
    "perturbed only indirectly through PWR-07" while PWR-07 lists both in its `perturbs`, and
    `perturbs` is a direct list because that is the only thing it can be.

    The comparison is exact, because a claim with a slack clause is a claim that cannot be checked.
    """

    def refusal(old: str, new: str, needle: str) -> None:
        definition = copy_definition(tmp_path / "coverage")
        path = definition / "domains" / "power" / "fault_policy.yaml"
        text = path.read_text()
        assert old in text, f"the fixture no longer matches {old!r}"
        path.write_text(text.replace(old, new, 1))
        out = run_linter(definition).stdout
        assert needle in out, out[-900:]

    # An exception that is not really an exception: the claim is more optimistic than the policy.
    refusal(
        'unperturbed: ["power.load_shed_class"]',
        "unperturbed: []",
        "no fault perturbs",
    )

    # The positive half: every domain's claim now holds against its own policy.
    for path in sorted((VEHICLE / "domains").glob("*/fault_policy.yaml")):
        policy = yaml.safe_load(path.read_text())
        points = yaml.safe_load((path.parent / "points.yaml").read_text())
        published = set()
        for point in points["points"]:
            published.add(re.sub(r"\[[^\]]*\]", "[]", str(point["channel"])))
        perturbed = {
            re.sub(r"\[[^\]]*\]", "[]", str(c))
            for fault in policy["faults"]
            for c in (fault.get("perturbs") or [])
        }
        declared = {re.sub(r"\[[^\]]*\]", "[]", str(x)) for x in policy["coverage"]["unperturbed"]}
        assert declared == published - perturbed, (
            f"{path.parent.name} claims {sorted(declared)} and the truth is "
            f"{sorted(published - perturbed)}"
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


def test_the_linter_refuses_a_counter_with_no_rating(tmp_path):
    """A count with no rating can be spent forever, and one was, for the life of the file.

    `accumulates:` says a stock counts what has been *spent* rather than what is held, and the
    rating is what makes "spent" mean anything. `absorber_capacity` carried the field and no
    rating, so every threshold watching it was watching a number that could not reach its floor —
    and the three ratings that would have exposed it were declared in two other files and read by
    nothing. The reverse direction is refused too: an `exhausted_at` on a stock that is *held*
    rather than counted is a rating whose subject the reader cannot identify.
    """
    definition = copy_definition(tmp_path / "counter")
    path = definition / "coupling.yaml"
    text = path.read_text()
    anchor = "    exhausted_at: 72\n"
    assert anchor in text, "the fixture no longer matches absorber_capacity_csm"
    path.write_text(text.replace(anchor, "", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "no numeric `exhausted_at`" in result.stdout

    definition = copy_definition(tmp_path / "held")
    path = definition / "coupling.yaml"
    text = path.read_text()
    anchor = '    preloaded: "the helium charge is loaded at the pad'
    assert anchor in text, "the fixture no longer matches the pressurant_he node"
    head, _, tail = text.partition(anchor)
    line, newline, rest = tail.partition("\n")
    path.write_text(f"{head}{anchor}{line}{newline}    exhausted_at: 10\n{rest}")

    result = run_linter(definition)
    assert result.returncode == 1
    assert "without `accumulates`" in result.stdout


def test_the_linter_refuses_a_fault_that_happens_to_nothing(tmp_path):
    """Every fault names what it happens *to*, and until round 42 nothing read the field.

    That is the usual cost, and this one had teeth: renaming the ECLSS absorber components left
    `ECL-04`, the *CSM's* blower failure, naming `lioh_bed_primary`, which had been the LM's
    primary cartridge. The fault went on looking plausible because every channel in its `perturbs`
    list was still real, and the linter refused none of it. A component, a state or a coupling node
    all resolve, because the field already meant all three — twelve of the vehicle's bindings name
    a node rather than an article, and they are naming the tank or the crew.
    """
    definition = copy_definition(tmp_path / "orphan")
    path = definition / "domains" / "eclss" / "fault_policy.yaml"
    text = path.read_text()
    anchor = "  - id: ECL-04-absorber-blower-failure\n    component: csm_lioh_element\n"
    assert anchor in text, "the fixture no longer matches ECL-04"
    path.write_text(
        text.replace(
            anchor, "  - id: ECL-04-absorber-blower-failure\n    component: lioh_bed_primary\n", 1
        )
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "not a component, a state or a node" in result.stdout


def test_the_two_absorbers_are_separate_counters():
    """One counter for two absorbers meant a surface crew spent the CSM's element.

    `E-ATM-ABSORB` runs from `cabin_atm` and `E-LM-ATM-ABSORB` from `lm_cabin_atm`, and the second
    edge's own note insisted the difference between them "is the edge's endpoints rather than its
    value" — while both landed on one node, which deleted exactly the distinction the note was
    defending. A leak is in one cabin; so is an absorber. The ratings were published in
    `vehicle.yaml#consumables` all along (CSM element 72 man-hours, LM primary 41) and read by
    nothing, which is also why `eclss.absorber_capacity_pct` divided by nothing while its sibling
    note cited the *LM's* 41 and 78 as the denominator of the *CSM's* channel.
    """
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    nodes = coupling["nodes"]
    for name, rating in (("absorber_capacity_csm", 72), ("absorber_capacity_lm", 41)):
        assert name in nodes, f"{name} is not a node"
        assert nodes[name]["exhausted_at"] == rating
        assert nodes[name]["kind"] == "stock"

    edges = {e["id"]: e["to"] for e in coupling["edges"]}
    assert edges["E-ATM-ABSORB"] == "absorber_capacity_csm"
    assert edges["E-LM-ATM-ABSORB"] == "absorber_capacity_lm"

    registry = yaml.safe_load((VEHICLE / "channels.yaml").read_text())
    ids = {
        c["id"]
        for section in registry.values()
        if isinstance(section, list)
        for c in section
        if isinstance(c, dict) and "id" in c
    }
    assert "eclss.absorber_capacity_pct" in ids
    assert "eclss.lm_absorber_capacity_pct" in ids, "the LM's absorber is unobservable without it"

    # The two counters have different minimum flows, which is the arithmetic consequence of the
    # crew splitting up: one crew member works the CSM's element while two work the LM's cartridge.
    stocks = {
        s["id"]: s
        for s in yaml.safe_load(
            (VEHICLE / "domains" / "consumables" / "components.yaml").read_text()
        )["state"]
    }
    assert stocks["absorber_man_hours_csm"]["min_flow_per_s"] == pytest.approx(2.78e-4)
    assert stocks["absorber_man_hours_lm"]["min_flow_per_s"] == pytest.approx(5.56e-4)


def test_the_lm_s_atmosphere_is_injectable():
    """Ten paired faults, because in `descent`, `surface` and `ascent_rendezvous` the crew are in
    the LM and no fault could move the air they were breathing.

    The pairing is the fix rather than a cabin parameter on one fault: a leak is in one cabin, and
    pairing is what lets the two diverge. The divergences are the content — the LM has no leak-rate
    channel (so an LM leak never appears in `eclss.leak_rate_g_s`, which is derived from the CSM's
    own mass balance), no regulator-position channel, and a party of two. `ECL-07-suit-loop-fan-failure`
    has no twin and should not: the suit loop is one shared circuit.
    """
    policy = yaml.safe_load((VEHICLE / "domains" / "eclss" / "fault_policy.yaml").read_text())
    faults = {f["id"]: f for f in policy["faults"]}
    lm_channels = {
        "eclss.lm_cabin_pressure_psia",
        "eclss.lm_cabin_temp_c",
        "eclss.lm_co2_pp_mmhg",
        "eclss.lm_pp_o2_mmhg",
        "eclss.lm_absorber_capacity_pct",
    }
    perturbed = {c for f in policy["faults"] for c in f["perturbs"]}
    assert lm_channels <= perturbed, f"nothing perturbs {sorted(lm_channels - perturbed)}"
    assert [i for i in faults if i.startswith("ECL-12")], "the LM twins are missing"
    # And the domain's own claim is that the exception list is empty, which is a stronger claim
    # than the four-channel one it made until round 42.
    assert policy["coverage"]["unperturbed"] == []


def test_the_two_views_of_the_cooling_machine_agree(tmp_path):
    """`vehicle.yaml#thermal` and the thermal domain describe one machine, and nothing joined them.

    Both were written, both were complete, and the vehicle-level file was read by no tool — so
    nothing was keeping them agreeing. Writing the join found it immediately: `vehicle.yaml` called
    its second loop `secondary` and gave it the **LM's** fluid, the LM's flow band and the LM's
    coolant mass, while the domain has three loops — `loop_lm` carrying exactly those figures, and
    a `loop_secondary` that is the CSM's second loop with different, chosen numbers. The
    vehicle-level file named the LM's loop "secondary" and did not mention the CSM's second loop at
    all, so a reader sizing a loop from it would have sized the wrong vehicle.
    """
    definition = copy_definition(tmp_path / "loops")
    path = definition / "vehicle.yaml"
    text = path.read_text()
    anchor = "      - id: loop_lm\n"
    assert anchor in text, "the fixture no longer matches vehicle.yaml#thermal.loops"
    path.write_text(text.replace(anchor, "      - id: loop_lmX\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "omits 'loop_lm'" in result.stdout

    definition = copy_definition(tmp_path / "fluid")
    path = definition / "vehicle.yaml"
    text = path.read_text()
    anchor = 'fluid: "65 % water / 35 % inhibited ethylene glycol"\n'
    assert anchor in text, "the fixture no longer matches the LM loop's fluid"
    path.write_text(text.replace(anchor, 'fluid: "62.5 % ethylene glycol / 37.5 % water"\n', 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "the thermal domain gives" in result.stdout


def test_the_linter_refuses_an_orphaned_section(tmp_path):
    """The thermal block's header was empty and its children were top-level keys.

    `thermal:` followed by a blank line reads as `thermal: null`, and `loops:`, `radiators:` and
    `zones:` one indent level out are orphans. Every reader that asked for
    `vehicle["thermal"]["loops"]` got `None`, so the section the file declared was empty and its
    three subsections were read by no tool at all — complete, plausible, and invisible. The audit
    that went looking for unread sections found the symptom and not the cause; this is the cause.
    """
    definition = copy_definition(tmp_path / "orphan")
    path = definition / "vehicle.yaml"
    lines = path.read_text().split("\n")
    start = next(i for i, line in enumerate(lines) if line.strip() == "loops:")
    end = next(i for i, line in enumerate(lines) if line.strip() == "comms:")
    for index in range(start, end - 6):
        if lines[index].startswith("  ") and lines[index].strip():
            lines[index] = lines[index][2:]
    lines.insert(start, "")
    path.write_text("\n".join(lines))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "declares a top-level section 'loops' that nothing reads" in result.stdout
    assert "leaves it empty" in result.stdout


def test_an_unloadable_vehicle_refuses_instead_of_crashing(tmp_path):
    """A linter that dies on the input it exists to diagnose is worse than one that misses a fault.

    `vehicle.yaml` is what every cross-file check joins against. When it failed to parse, the
    linter raised `AttributeError: 'NoneType' object has no attribute 'get'` **from inside a
    check** and the traceback replaced the report — so the one line that mattered, naming the
    parse error, was buried under a crash in a check that never got to run. The operator sees a
    traceback and concludes the tool is broken rather than the definition.
    """
    definition = copy_definition(tmp_path / "unloadable")
    path = definition / "vehicle.yaml"
    text = path.read_text()
    anchor = "  loops:\n"
    assert anchor in text, "the fixture no longer matches the thermal block"
    path.write_text(text.replace(anchor, "loops:\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1, result.stderr
    assert "does not parse" in result.stdout
    assert "could not be loaded" in result.stdout
    assert "Traceback" not in result.stderr, result.stderr[-1500:]


def test_the_coverage_blocks_checkable_claims_are_checked(tmp_path):
    """`unperturbed` was the first key in the block to be checked, and checking it made the block
    *look* read.

    Four other keys sat beside it making claims of exactly the same kind — counts and directions —
    and nothing had ever compared one of them to the policy. **Five of their first eight numeric
    claims were wrong**, in both directions: `avionics` said six of its faults crossed a domain
    boundary and four did, `comms` said four and five did, `gnc` said five and one did, and `gnc`
    separately said seven of eleven faults moved `gnc.nav_integrity` when nine do.

    `gnc.cross_domain` was the worst of them because it named three couplings that do not exist —
    `rcs.thruster_[n]_health`, `mission.met_s` and the comms blackout — and they are real
    relationships with the arrows the wrong way round, which is why the sentence read as true.

    Prose cannot be checked, so each block now declares its claim as a field.
    """
    definition = copy_definition(tmp_path / "count")
    path = definition / "domains" / "gnc" / "fault_policy.yaml"
    text = path.read_text()
    anchor = "    faults_outside: 1\n"
    assert anchor in text, "the fixture no longer matches gnc's coverage claim"
    path.write_text(text.replace(anchor, "    faults_outside: 5\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "claims 5 fault(s) perturb a channel outside" in result.stdout

    # The ladder claim is a count too, and it is the domain's thesis: a navigation fault is
    # visible because it degrades a ladder, not because it spills into another domain's channels.
    definition = copy_definition(tmp_path / "ladder")
    path = definition / "domains" / "gnc" / "fault_policy.yaml"
    text = path.read_text()
    anchor = "    faults_perturbing: 9\n"
    assert anchor in text, "the fixture no longer matches gnc's ladder claim"
    path.write_text(text.replace(anchor, "    faults_perturbing: 7\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "claims 7 fault(s) move" in result.stdout


def test_the_linter_refuses_a_false_superlative(tmp_path):
    """A superlative is a claim about all eleven domains, so it is the one that rots untouched.

    `avionics` said it had "the highest cross-domain reach of any domain on the vehicle", and by
    round 44 `eclss` had three times as many, because a life-support failure reaches every domain
    that plans around a consumable while an instrument failure reaches only what that instrument
    serves. The domain that made the claim never moved; the vehicle around it did.
    """
    definition = copy_definition(tmp_path / "superlative")
    path = definition / "domains" / "avionics" / "fault_policy.yaml"
    text = path.read_text()
    anchor = "    faults_outside: 4\n"
    assert anchor in text, "the fixture no longer matches avionics' coverage claim"
    path.write_text(text.replace(anchor, anchor + "    outbound_extreme: highest\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "claims the vehicle's highest cross-domain reach" in result.stdout


def test_the_linter_refuses_a_gated_alarm_that_is_not_gated(tmp_path):
    """A suppression a fleet is told about and the vehicle does not apply is a silence nobody can
    explain.

    `comms` suppresses three alarms for a condition it can predict — the lunar occultation — so
    that when they fire they mean something. The claim that three thresholds carry `gated_by` is
    exact, and it is the kind a threshold added later silently falsifies.
    """
    definition = copy_definition(tmp_path / "gated")
    path = definition / "domains" / "comms" / "profiles.yaml"
    text = path.read_text()
    anchor = '    gated_by: "comm.blackout_state is clear"\n'
    assert anchor in text, "the fixture no longer matches the gated thresholds"
    path.write_text(text.replace(anchor, "", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "declares no `gated_by`" in result.stdout


def test_the_linter_refuses_a_shared_rule_with_no_pointer(tmp_path):
    """One rule, one home — and a pointer, or a reader finds neither.

    `power_rule` and `thermal_rule` are declared in the avionics diagnostics and implemented in
    the power and thermal domains, because two implementations of one rule is how two domains come
    to disagree. `implemented_by` is what makes "declared here, implemented elsewhere" a fact
    rather than a claim.
    """
    definition = copy_definition(tmp_path / "shared")
    path = definition / "domains" / "avionics" / "components.yaml"
    text = path.read_text()
    anchor = "  - id: power_rule\n    implemented_by: power\n"
    assert anchor in text, "the fixture no longer matches the power_rule diagnostic"
    path.write_text(text.replace(anchor, "  - id: power_rule\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "declares no `implemented_by` domain" in result.stdout


def test_the_linter_refuses_a_key_swallowed_by_a_block_scalar(tmp_path):
    """The silent half of the duplicate-key accident: nothing collides, so nothing notices.

    `duplicate_keys` describes this accident and catches the half of it that *clashes* — a block
    scalar's content indented to the depth of the entry that follows, so the entry is absorbed and
    its keys overwrite the one above. That check needs a collision to fire. When the absorbed keys
    are new, nothing is replaced and the declaration simply **does not exist**.

    Two were found this way. `coupling.yaml`'s `C-WATER-BUDGET` lost its `stability` declaration
    into its own note, so the linter's relay-oscillation rule read it as absent and passed only
    because no member of that cycle happens to be latched. `consumables/components.yaml`'s
    `reconciliation` lost two — its `on_mismatch` rule and its whole `provenance` block — so the
    vehicle's rule about never rewriting the ledger was a sentence no reader of the parsed document
    could reach.
    """
    definition = copy_definition(tmp_path / "swallowed")
    path = definition / "domains" / "consumables" / "components.yaml"
    lines = path.read_text().split("\n")
    start = next(i for i, line in enumerate(lines) if line.strip() == "on_mismatch:")
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "provenance:")
    for index in range(start, end + 5):
        if lines[index].strip():
            lines[index] = "  " + lines[index]
    path.write_text("\n".join(lines))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "prose rather than a key" in result.stdout
    assert "on_mismatch" in result.stdout


def test_the_missions_clock_is_held_to_the_phase_ladder(tmp_path):
    """The same total is stated three times, each saying the linter holds it, and none was read.

    `phase_total_check`'s note read "the linter re-derives this and refuses a mismatch";
    `total_duration_provenance` read "sum of the phase durations below; the linter refuses a build
    where they disagree"; and `total_ticks_provenance` gave the tick count as a sentence. The
    linter does re-derive the ladder — the trajectory checks trip the moment a phase duration
    moves — but **none of the three declarations was read**: `sums_to_h` set to 999.0 passed
    silently.

    That is worse than an unchecked number, because the sentence tells the next reader not to check
    it by hand.
    """
    definition = copy_definition(tmp_path / "total")
    path = definition / "mission.yaml"
    text = path.read_text()
    anchor = "  total_ticks: 34560000\n"
    assert anchor in text, "the fixture no longer matches the tick count"
    path.write_text(text.replace(anchor, "  total_ticks: 3456\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "192 h at 50 Hz is 34,560,000" in result.stdout

    definition = copy_definition(tmp_path / "sum")
    path = definition / "mission.yaml"
    text = path.read_text()
    anchor = 'computation: "73.0 + 24.5 + 2.5 + 21.5 + 3.5 + 7.5 + 58.5 + 1.0"\n'
    assert anchor in text, "the fixture no longer matches the phase computation"
    path.write_text(text.replace(anchor, 'computation: "73.0 + 24.5"\n', 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "does not re-derive" in result.stdout


def test_the_debt_count_includes_the_files_nothing_walks(tmp_path):
    """The folder's headline number is the debt count, so an omission in it is invisible.

    The domain files are walked for unset values by `check_domain` and the coupling graph by its
    edge walk, so every literal `UNCONFIGURED` scalar was counted — **except the eleven in the two
    files nothing walks**: `mission.yaml`'s initial position, velocity and state-vector basis, and
    `vehicle.yaml`'s three minimum impulse bits, the LM sublimator's rejection and water
    consumption and its radiators. Two of them are named in a prose `open_debts` entry somewhere
    else, which is how they stayed plausible.
    """
    import sys as _sys

    _sys.path.insert(0, str(VEHICLE / "tools"))
    from check_vehicle import walk_unset

    mission = yaml.safe_load((VEHICLE / "mission.yaml").read_text())
    vehicle = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
    owed = walk_unset(mission) + walk_unset(vehicle)
    assert owed, "the fixture no longer has unset values in the top-level files"

    result = run_linter(VEHICLE)
    assert result.returncode == 0, result.stdout[-1500:]
    missing = [
        trail
        for trail in owed
        if f"mission.yaml.{trail}:" not in result.stdout
        and f"vehicle.yaml.{trail}:" not in result.stdout
    ]
    assert not missing, f"these unset values are counted by nothing: {missing}"


def test_the_linter_refuses_a_debt_that_has_been_answered(tmp_path):
    """A debt that has been paid and is still on the books is worse than no debt.

    `mission.yaml` carried `initial_state.landing_site: UNCONFIGURED` for as long as it carried the
    real thing. When the site was chosen it was declared as a **top-level** `landing_site` block —
    with the derivation, the sub-Earth geometry and a `check_landing_site` that re-derives it — and
    the placeholder twenty lines above went on reporting the site as undecided, in the same file.

    A note that has outlived its answer tells the next reader to stop looking, and the site is what
    decides whether the LM can be heard from the surface at all.
    """
    definition = copy_definition(tmp_path / "answered")
    path = definition / "mission.yaml"
    text = path.read_text()
    anchor = "  entry_corridor: UNCONFIGURED\n"
    assert anchor in text, "the fixture no longer matches initial_state's tail"
    path.write_text(text.replace(anchor, "  landing_site: UNCONFIGURED\n" + anchor, 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "while the top-level `landing_site`" in result.stdout


def _plant():
    import sys as _sys

    if str(VEHICLE / "tools") not in _sys.path:
        _sys.path.insert(0, str(VEHICLE / "tools"))
    import plant

    return plant


def test_the_stock_integrator_reads_its_driver():
    """The vehicle's most load-bearing piece of simulation code had never executed, and was wrong.

    The schedule stops at the first `algebraic` state — long before it reaches any of the 24 stock
    states — so the integrator every consumable in the mission depends on was written, reviewed and
    never run. Handed `lm_cabin_o2_kg` it returned the same 117.89792 kg whether one crew member was
    aboard or three, because it summed `sensitivity * dt` over every incoming edge and never read a
    driver. The three edges it summed were `116.86 Pa per K` (a lag relation between zone temperature
    and cabin pressure), `1.0 kg O2 per kg O2` (a conservation ratio whose flux is the tank's
    *outflow*, which the ratio does not contain) and `0.03792 kg/h per crew`. Adding
    pascals-per-kelvin to kilograms-per-hour and calling the result a mass is not an approximation;
    it is a dimension error wearing a number.

    The three computable edges are exercised here by direct call, because that is the only way to
    reach them: nothing in the schedule does.
    """
    plant = _plant()
    world = plant.load_world(VEHICLE)
    edge = next(e for e in world.edges if e.id == "E-CREW-ATM")
    assert edge.sensitivity["unit"] == "kg/h per crew"

    for crew, expected in ((0.0, 0.0), (1.0, 0.03792), (3.0, 0.11376)):
        flux = plant.stock_flux(world, edge, {edge.source: crew}, 3600.0)
        assert flux == pytest.approx(expected, rel=1e-6), f"{crew} crew gave {flux}"

    # And the per-second basis is the other half of the unit parse: `E-WATER-RAD` is `kg/s per W`.
    # It was `E-RAD-WATER` until round 61 swapped the water cycle's edges so that the stock
    # discharges through the one carrying the per-watt unit.
    rad = next(e for e in world.edges if e.id == "E-WATER-RAD")
    assert plant.stock_flux(world, rad, {rad.source: 1000.0}, 1.0) == pytest.approx(4.0816e-4)


def test_the_stock_integrator_refuses_what_is_not_a_flux():
    """Eight of the graph's fourteen stock edges cannot be integrated as written, and each refuses.

    Two kinds, and each needs a different thing declared. A **ratio whose flow is undeclared** —
    `1.0 kg O2 per kg O2` — converts the source's *outflow* into the target's inflow, and the outflow
    belongs to whichever state produces it. A **structural relation landing on a stock node** —
    `116.86 Pa per K` — lands there because the channel hangs off the node, not because anything
    flows into it: a cabin's pressure depends on its temperature and its mass, but its mass does not
    depend on its temperature.
    """
    plant = _plant()
    world = plant.load_world(VEHICLE)

    for edge_id, needle in (("E-ZONE-ATM", "'lag' edge on a stock"),):
        edge = next(e for e in world.edges if e.id == edge_id)
        with pytest.raises(plant.Unconfigured) as caught:
            plant.stock_flux(world, edge, {edge.source: 1.0}, 0.02)
        assert needle in caught.value.what, f"{edge_id}: {caught.value.what}"
        assert edge_id in str(caught.value.where) or edge_id in caught.value.what, edge_id


def test_the_stock_integrator_refuses_a_missing_driver():
    """A rate with a time basis still needs something to multiply, and the refusal names it."""
    plant = _plant()
    world = plant.load_world(VEHICLE)
    edge = next(e for e in world.edges if e.id == "E-CREW-ATM")

    with pytest.raises(plant.Unconfigured) as caught:
        plant.stock_flux(world, edge, {}, 0.02)
    assert "which nothing supplies this tick" in caught.value.what

    with pytest.raises(plant.Unconfigured) as caught:
        plant.stock_flux(world, edge, {edge.source: "three"}, 0.02)
    assert "not a number the sensitivity can multiply" in caught.value.what


def test_the_linter_and_the_plant_share_one_stock_flux_rule():
    """The plant's refusals were unreachable, so eight structural defects were invisible.

    The schedule stops at the first `algebraic` state, long before it reaches a stock, so no tool
    ever got to the integrator that refuses these edges. Eight of the vehicle's fourteen stock edges
    cannot be integrated as written and **the linter, `--strict` and the debt count all said nothing
    about them.** A defect that only a code path nobody reaches can see is a defect nobody has.

    Both tools now call `stock_flux_basis`, in the pattern `derive_schedule` already set, so a rule
    about what a stock edge means cannot come apart from the rule that checks it. This test holds
    that in place from both ends: the linter reports each edge as a debt *and* the plant refuses the
    same edge, from the same function.
    """
    plant = _plant()
    from check_vehicle import stock_flux_basis

    world = plant.load_world(VEHICLE)
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    result = run_linter(VEHICLE)
    assert result.returncode == 0, result.stdout[-1500:]

    expected = {
        "E-PLATE-BAT": "'lag' edge on a stock",
    }
    for edge_id, needle in expected.items():
        edge = next(e for e in world.edges if e.id == edge_id)
        basis, reason = stock_flux_basis(
            {
                "id": edge.id,
                "kind": edge.kind,
                "sensitivity": edge.sensitivity,
                "from": edge.source,
                "to": edge.target,
            },
            coupling["nodes"],
        )
        assert basis is None, f"{edge_id} is now integrable; update this test and the debt"
        assert needle in reason, f"{edge_id}: {reason}"
        assert f"coupling.yaml:edge {edge_id}:" in result.stdout, (
            f"{edge_id} is refused by the plant and not reported by the linter"
        )

    # Two edges the classifier refuses are *not* debts, and the distinction is the whole reason
    # `advances` exists: E-ZONE-ATM and E-ZONE-ATM-LM land on a stock node — the cabin — but they
    # drive its *pressure*, which is an algebraic state. A pressure is not a conserved quantity that
    # something flows into, so they were never fluxes, and they are correctly silent.
    for edge_id in ("E-ZONE-ATM", "E-ZONE-ATM-LM"):
        edge = next(e for e in world.edges if e.id == edge_id)
        basis, _ = stock_flux_basis(
            {"id": edge.id, "kind": edge.kind, "sensitivity": edge.sensitivity}, {}
        )
        assert basis is None, f"{edge_id} should not look like a flux"
        assert f"coupling.yaml:edge {edge_id}:" not in result.stdout, (
            f"{edge_id} drives a pressure, not a stock, and must not be reported as a stock debt"
        )

    # And the three that are integrable stay integrable, so the rule is not simply refusing.
    for edge_id in ("E-CREW-ATM", "E-LM-CREW-ATM", "E-WATER-RAD"):
        edge = next(e for e in world.edges if e.id == edge_id)
        basis, reason = stock_flux_basis(
            {
                "id": edge.id,
                "kind": edge.kind,
                "sensitivity": edge.sensitivity,
                "from": edge.source,
                "to": edge.target,
            },
            coupling["nodes"],
        )
        assert basis in ("per_second", "per_hour"), f"{edge_id}: {reason}"


def test_an_edge_says_which_state_it_advances(tmp_path):
    """Ten of the vehicle's 41 nodes hold more than one state, and the plant resolved drivers by node.

    On `cabin_atm`, which holds four gas masses, `csm_cabin_o2_kg`, `csm_cabin_n2_kg`,
    `csm_cabin_co2_kg` and `csm_cabin_h2o_kg` were all handed the same edges — the oxygen supply,
    the crew's CO2 production and a pressure/temperature relation. **Every gas integrated every
    other gas's flux**, and a nitrogen state that nothing supplies would have been filled by the
    crew's breathing.

    `advances` names the state an edge drives, and the linter requires it wherever the node holds
    more than one state a value can move. It is required rather than inferred because the inference
    is exactly what was wrong: "the only state on this node" is true today and stops being true the
    moment a second state lands, silently and in the direction of the plant integrating the wrong
    thing.
    """
    plant = _plant()
    world = plant.load_world(VEHICLE)

    def incoming(state_id: str) -> list[str]:
        state = next(s for s in world.states if s.id == state_id)
        return [
            e.id
            for e in world.edges
            if e.target == state.node
            and e.id not in world.back_edges
            and (e.advances is None or e.advances == state.id)
        ]

    # The four gas masses of one compartment now have four different answers, where before they
    # had one list between them.
    assert incoming("csm_cabin_o2_kg") == ["E-O2-ECLSS"]
    assert incoming("csm_cabin_co2_kg") == ["E-CREW-ATM"]
    assert incoming("csm_cabin_n2_kg") == [], (
        "nothing supplies nitrogen, and now nothing pretends to"
    )
    # And the pressure is driven by the thermal edge rather than by a mass flux.
    assert incoming("csm_cabin_pressure_pa") == ["E-ZONE-ATM"]

    # Removing the declaration must be refused rather than silently resolved by node.
    definition = copy_definition(tmp_path / "advances")
    path = definition / "coupling.yaml"
    text = path.read_text()
    anchor = "    advances: csm_cabin_o2_kg\n"
    assert anchor in text, "the fixture no longer matches E-O2-ECLSS"
    path.write_text(text.replace(anchor, "", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "declares no `advances`" in result.stdout


def test_the_pressure_is_a_state_on_the_cabin_node():
    """Pressure belongs where the gas masses are, and moving it there is what gave `E-ZONE-ATM`
    something to advance.

    It was a state on the `internal` sentinel, which is not a node — so the graph had nowhere to put
    the cabin's dP/dT, and the edge carried it into the *mass* node instead. A cabin's pressure
    depends on its temperature and its mass; its mass does not depend on its temperature. Promoted,
    the edge has a true declaration (`advances: csm_cabin_pressure_pa`), the relation it carries is
    stated once in the state that computes it, and the 116.86 Pa per kelvin figure survives there.
    """
    components = yaml.safe_load((VEHICLE / "domains" / "eclss" / "components.yaml").read_text())
    by_id = {s["id"]: s for s in components["state"]}
    assert by_id["csm_cabin_pressure_pa"]["node"] == "cabin_atm"
    assert by_id["lm_cabin_pressure_pa"]["node"] == "lm_cabin_atm"
    assert "116.86 Pa per kelvin" in by_id["csm_cabin_pressure_pa"]["provenance"]["relation"]

    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    edges = {e["id"]: e for e in coupling["edges"]}
    assert edges["E-ZONE-ATM"]["advances"] == "csm_cabin_pressure_pa"
    assert edges["E-ZONE-ATM-LM"]["advances"] == "lm_cabin_pressure_pa"


def test_the_stock_integrator_drains_as_well_as_fills():
    """The outbound half of the integrator was missing entirely, so every tank in the vehicle only filled.

    The README states the rule in as many words — "a back-edge *out* of a stock still drains it,
    because the stock's own integrator subtracts the flow the back-edge reads" — and no tool
    implemented any of it: `advance()` summed `incoming` and never looked at an outbound edge. Twelve
    edges leave stock nodes. With round 47's missing driver and round 49's node-level resolution, the
    stock integrator has now been wrong in four independent ways, and the reason is the same every
    time: **it never runs.**

    `E-CREW-WATER` is the one discharge the classifier can establish — `kg/h per crew`, driven by the
    crew count — and it is the edge the README says was added to stop `water_potable` rising
    forever.
    """
    plant = _plant()
    world = plant.load_world(VEHICLE)
    edge = next(e for e in world.edges if e.id == "E-CREW-WATER")
    assert edge.sensitivity["unit"] == "kg/h per crew"

    # A discharge is driven by the *consumer*, not by the stock: reading the tank's own level and
    # multiplying by a kg/h-per-crew sensitivity is how this returned zero at every crew count.
    for crew, expected in ((0.0, 0.0), (1.0, 0.094583), (3.0, 0.283749)):
        flux = plant.stock_flux(
            world, edge, {edge.source: 137.0, edge.target: crew}, 3600.0, driver_node=edge.target
        )
        assert flux == pytest.approx(expected, rel=1e-6), f"{crew} crew gave {flux}"


def test_the_linter_reports_the_discharges_it_cannot_establish(tmp_path):
    """Thirteen of the vehicle's sixteen stock edges cannot be integrated, and each is named.

    The linter reports them so they enter the debt count and fail `--strict`; the plant refuses them
    with the same words from the same function. `E-PROP-ENG` and `E-RCSP-RCS` are the pair the
    *dimensional* half of the classifier catches: `N per kg/s` reads as a rate under the time-basis
    test alone, while its numerator is a force — the number is thrust per unit of flow, stated
    backwards, so a plant multiplying it by a thrust would get N^2 per (kg/s) and call the result
    kilograms of propellant.
    """
    if str(VEHICLE / "tools") not in sys.path:
        sys.path.insert(0, str(VEHICLE / "tools"))
    from check_vehicle import stock_flux_basis

    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    nodes = coupling["nodes"]
    result = run_linter(VEHICLE)
    assert result.returncode == 0, result.stdout[-1500:]

    # The class is empty as of round 65. `E-PLATE-BAT` moved to a capacity node in round 64 and
    # `E-RAD-WATER` became `kind: limit` in this one, so there is no edge left that the classifier
    # refuses as a flux — which is the property to hold now.
    structural: set[str] = set()
    for edge_id in structural:
        edge = next(e for e in coupling["edges"] if e["id"] == edge_id)
        basis, reason = stock_flux_basis(edge, nodes)
        assert basis is None, f"{edge_id} is now integrable; update this test and the debt"
        assert f"coupling.yaml:edge {edge_id}:" in result.stdout, (
            f"{edge_id} is refused by the plant and not reported by the linter"
        )

    # The four that are computable stay computable, so the rule is not simply refusing everything.
    for edge_id in (
        "E-CREW-ATM",
        "E-LM-CREW-ATM",
        "E-CREW-WATER",
        "E-O2-DRAW",
        "E-H2-DRAW",
        "E-FC-WATER",
        "E-O2-SUPPLY-CSM",
        "E-O2-SUPPLY-LM",
        "E-O2-ECLSS",
        "E-LM-O2-ECLSS",
        "E-WATER-RAD",
        "E-PROP-ENG",
        "E-RCSP-RCS",
        "E-ATM-ABSORB",
        "E-LM-ATM-ABSORB",
        "E-CABIN-CO2-REMOVAL",
        "E-LM-CABIN-CO2-REMOVAL",
    ):
        edge = next(e for e in coupling["edges"] if e["id"] == edge_id)
        basis, reason = stock_flux_basis(edge, nodes)
        assert basis in ("per_second", "per_hour"), f"{edge_id}: {reason}"


def test_a_stock_that_carries_two_states_says_which_one_drains(tmp_path):
    """`drains` is `advances` for the outbound side, and it is required for the same reason.

    `cabin_atm` carries four gas masses, so `E-ATM-ABSORB` leaving it has four candidates to choose
    between — and it is the CO2 the absorber takes, not the nitrogen.
    """
    definition = copy_definition(tmp_path / "drains")
    path = definition / "coupling.yaml"
    text = path.read_text()
    stripped = re.sub(r"^    drains: csm_cabin_co2_kg.*\n", "", text, count=1, flags=re.M)
    assert stripped != text, "the fixture no longer matches E-ATM-ABSORB"
    path.write_text(stripped)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "declares no `drains`" in result.stdout


def test_a_ratio_refusal_names_the_flow_that_would_fix_it():
    """A refusal that names the missing node is worth more than one that describes the symptom.

    Round 50 established that a dimensionless ratio into a stock is not a flux. That is true and it
    is not actionable: five edges were refused with the same sentence and none of them said what to
    build. The test a ratio actually needs is not "is this a ratio" but **"does the graph carry the
    flow the ratio is against"** — `1.0 kg water per kg reactants` applied to a node holding
    `kg reactants per second` is water per second, which is a flux.

    Nothing in the vehicle carries one, so the refusals stand — and each now names the flow, so the
    five edges resolve into a specification rather than a diagnosis: four consumer intakes, because
    `E-O2-FC` and `E-O2-ECLSS` both draw from `o2_csm` while being the cell's draw and the cabin's
    supply respectively.
    """
    if str(VEHICLE / "tools") not in sys.path:
        sys.path.insert(0, str(VEHICLE / "tools"))
    from check_vehicle import stock_flux_basis

    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    nodes = coupling["nodes"]
    stock_nodes = {k for k, v in nodes.items() if v.get("kind") == "stock"}
    result = run_linter(VEHICLE)
    assert result.returncode == 0, result.stdout[-1500:]

    # The class is empty as of round 60, and that is the property worth holding now. Every ratio
    # that used to be refused — `E-O2-FC`, `E-H2-FC`, `E-FC-WATER`, `E-O2-ECLSS`, `E-LM-O2-ECLSS` —
    # has a flow node carrying its denominator, and each refusal named the node that would fix it,
    # which is how five vague debts became one build order and then no debts at all.
    refused_ratios = [
        e["id"]
        for e in coupling["edges"]
        if (e["from"] in stock_nodes or e["to"] in stock_nodes)
        and (e.get("sensitivity") or {}).get("value") not in (None, "UNCONFIGURED")
        and stock_flux_basis(e, nodes)[0] is None
        and "dimensionless ratio" in stock_flux_basis(e, nodes)[1]
    ]
    assert refused_ratios == [], f"a ratio is refused again: {refused_ratios}"

    # And the rule is not simply refusing ratios: one whose denominator *is* carried is computable.
    synthetic = {
        "id": "E-TEST",
        "kind": "rate",
        "from": "tank",
        "to": "sink",
        "sensitivity": {"value": 1.0, "unit": "kg water per kg reactants"},
    }
    world = {
        "tank": {"kind": "stock", "unit": "kg"},
        "driver": {"kind": "flow", "unit": "kg reactants/s"},
        "sink": {"kind": "stock", "unit": "kg"},
    }
    synthetic["from"] = "driver"
    basis, reason = stock_flux_basis(synthetic, world)
    assert basis == "per_second", reason


def test_the_build_order_is_derived_and_partitions_the_vehicle():
    """The folder's answer to "what do I implement first" has to be computed, not authored.

    An authored worklist drifts the moment anybody lands anything, and a stale build order is worse
    than none because it sends the next reader to work that is already done. So `plant.py
    --build-order` classifies every state by `advance()`'s own refusal order — the same sequence of
    tests the plant runs when it gets there — which means the two cannot disagree.

    The shape it reports is the honest one: **half the vehicle owes a rule**, and that is by
    construction, because `plant.md` §3's `algebraic`, `discrete`, `dynamics` and `hazard` classes
    are domain code the configuration deliberately does not carry. The build order is therefore not
    a list of missing numbers; it is mostly a list of missing *code*.
    """
    plant = _plant()
    world = plant.load_world(VEHICLE)
    buckets = plant.build_order(world)

    # A partition, not an approximation: every state is in exactly one bucket. A classifier written
    # as a sequence of skips finds its way past exactly the inputs nobody anticipated, which is the
    # failure this project has already met once in `conserved_dimension`.
    seen = [state.id for rows in buckets.values() for state in rows]
    assert len(seen) == len(set(seen)), "a state is classified twice"
    assert set(seen) == {s.id for s in world.states}, "a state is classified by nothing"
    assert sum(len(rows) for rows in buckets.values()) == 134

    # `ready` means what it says: only the two classes the reference plant can actually advance.
    assert {s.method for s in buckets["ready"]} <= {"lag", "stock"}
    # And a state that owes a rule is never also counted as ready.
    assert not ({s.id for s in buckets["rule"]} & {s.id for s in buckets["ready"]})

    # The counts are the vehicle's current shape, and a change here is a change in the build order
    # rather than a cosmetic difference — which is exactly what makes it worth asserting.
    #
    # `ready` fell 13 -> 11 when the ten stocks with no declared initial condition were marked
    # owed. That is the classification working: an integrator with no level to integrate from
    # cannot be advanced, so it is blocked by a *value* rather than counted as ready. It had
    # been counted as ready because the integrator never read a level, which is the defect the
    # round found — the build order was reporting a state as advanceable that could only have
    # produced a wrong number.
    assert len(buckets["ready"]) == 11
    assert len(buckets["rule"]) == 71, "half the vehicle is domain code"


def test_the_plant_reports_the_build_order():
    """The view is a CLI contract, not an internal function."""
    result = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "plant.py"), "--build-order"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "134 states, by what blocks them" in result.stdout
    for phrase in ("ready now", "owes a value", "owes an edge", "owes a rule"):
        assert phrase in result.stdout, f"{phrase!r} missing from the build order"


def test_a_state_with_an_outbound_edge_and_no_driver_is_reported():
    """Having *an* edge is not having an input, and the isolation check cannot tell the difference.

    `cabin_zone_t` has an edge — `E-ZONE-ATM` points *out* of it — so it looks connected. But
    nothing drives it, `zone_csm_cabin_t` is a `lag`, and a lag with no driver has nothing to relax
    toward. The cabin's temperature has no heat input anywhere in the graph, while the crew, the
    equipment and the loop all warm it in the prose; the state's own 2,880 s derivation reasons
    about "a 1 kW cabin load" that no edge carries.

    The check also found three nodes that look identical and are not: **`o2_lm`, `prop_rcs` and
    `pressurant_he` have no inbound edge because they are filled at the pad and never again**, which
    they say in `preloaded:`. The first version reported all seven, which is three parts noise to
    one part signal — and the declaration is exactly what separates a stock that nothing fills from
    one that is filled once.
    """
    _plant()
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    nodes = coupling["nodes"]
    # The same rule the plant uses: a *back-edge* is not a driver, because `advance()` skips them
    # when it collects a state's incoming edges. `fuel_cell` is the case that proves it — `E-O2-FC`
    # points into it, and it is the back-edge of `C-REACTANT-DRAW-O2`, so the node still has nothing
    # forward driving it. A test that counted any inbound edge would have called it driven.
    back = {cy["back_edge"] for cy in coupling["cycles"] if cy.get("back_edge")}
    forward = {e["to"] for e in coupling["edges"] if e["id"] not in back}
    driving = {"lag", "stock", "delay", "dynamics"}
    methods = {}
    for path in sorted((VEHICLE / "domains").glob("*/components.yaml")):
        for state in (yaml.safe_load(path.read_text()) or {}).get("state") or []:
            methods[state["id"]] = (state.get("method"), state.get("node"))

    undriven = [
        name
        for name in nodes
        if name not in forward
        and any(e["from"] == name for e in coupling["edges"])
        and not nodes[name].get("preloaded")
        and any(m in driving and n == name for m, n in methods.values())
    ]
    assert sorted(undriven) == ["fuel_cell", "imu"], undriven

    result = run_linter(VEHICLE)
    assert result.returncode == 0, result.stdout[-1200:]
    for name in undriven:
        assert f"coupling.yaml:node {name}: has edges but none into it" in result.stdout, name
    for name in ("o2_lm", "prop_rcs", "pressurant_he"):
        assert f"coupling.yaml:node {name}: has edges but none into it" not in result.stdout, (
            f"{name} is pre-loaded and must not be reported as undriven"
        )


def test_the_heat_inputs_are_a_partition_of_the_load_inventory(tmp_path):
    """`load_budget` names the loads as the heat inputs and nothing said which zone each one warms.

    The thermal domain declares the heat *sources* (`heater_bank_csm`'s own provenance says "the
    thermal side owns which zones it serves"), the power domain declares the *loads*, and nothing
    joined them — which is why `zone_csm_cabin_t` was a `lag` with no driver. The assignment lives
    in the thermal domain rather than as a `zone:` field on each power load, because a field there
    would be a second declaration of one fact in the file that explicitly refuses to duplicate the
    numbers.

    The property with teeth is the third: the distinct loads assigned per vehicle must sum to that
    vehicle's declared demand. It closes **exactly** — 1,723 W of CSM load and 1,007 W of LM load —
    which is what makes this a partition rather than a wish.
    """
    thermal = yaml.safe_load((VEHICLE / "domains" / "thermal" / "components.yaml").read_text())
    power = yaml.safe_load((VEHICLE / "domains" / "power" / "components.yaml").read_text())
    loads = {str(r["id"]): r for r in power["loads"]}

    seen: dict[str, set[str]] = {}
    for block in thermal["heat_inputs"].values():
        for load_id in block["loads"]:
            assert load_id in loads, f"{load_id} is not a load"
            seen.setdefault(str(loads[load_id]["vehicle"]), set()).add(load_id)
    for vehicle, expected in (("csm", 1723), ("lm", 1007)):
        total = sum(int(loads[i]["demand_w"] or 0) for i in seen[vehicle])
        assert total == expected, f"{vehicle}: {total} W assigned against {expected} W declared"
    # Nothing unaccounted: every load in the inventory heats somewhere.
    assert sum(len(ids) for ids in seen.values()) == len(loads)

    # A load assigned to no zone is a watt that heats nothing, and the check says which one.
    definition = copy_definition(tmp_path / "gap")
    path = definition / "domains" / "thermal" / "components.yaml"
    text = path.read_text()
    anchor = "    loads: [csm_imu, csm_guidance_computer, csm_instrumentation]\n"
    assert anchor in text, "the fixture no longer matches the avionics bay"
    path.write_text(
        text.replace(anchor, "    loads: [csm_guidance_computer, csm_instrumentation]\n", 1)
    )

    result = run_linter(definition)
    assert result.returncode == 1
    assert "A load assigned to no zone is a watt that heats nothing" in result.stdout
    assert "csm_imu" in result.stdout


def test_the_cabin_heat_rates_are_derived_from_the_load_inventory(tmp_path):
    """The heat-rate state is where the thermal and power domains finally meet, so it is checked there.

    `heat_inputs` assigns every load to a zone; the heat-rate state sums that zone's loads. Two
    declarations of one quantity, in two files, is exactly the shape that drifts — and it drifts in
    the quiet direction: a load re-rated in `domains/power/` would change what the cabin's equipment
    actually draws while the thermal state went on relaxing toward the old figure, modelling a cabin
    cooler than it is.

    The state's `total_w` is re-derived twice on every run: against its own `computation`, and
    against the loads `heat_inputs` assigns. `cabin_heat_lm_w` at 827 W against the CSM cabin's 733,
    with two crew rather than three, because the LM has no avionics-bay zone.
    """
    thermal = yaml.safe_load((VEHICLE / "domains" / "thermal" / "components.yaml").read_text())
    power = yaml.safe_load((VEHICLE / "domains" / "power" / "components.yaml").read_text())
    loads = {str(r["id"]): r for r in power["loads"]}
    states = {str(s["id"]): s for s in thermal["state"]}

    for state_id, zone, expected in (
        ("cabin_heat_csm_w", "csm_cabin", 733),
        ("cabin_heat_lm_w", "lm_cabin", 827),
    ):
        state = states[state_id]
        declared = sum(
            int(loads[i]["demand_w"] or 0) for i in thermal["heat_inputs"][zone]["loads"]
        )
        assert state["total_w"] == declared == expected, state_id

    # A load re-rated under the state's feet is refused rather than absorbed.
    definition = copy_definition(tmp_path / "rate")
    path = definition / "domains" / "thermal" / "components.yaml"
    text = path.read_text()
    anchor = "    total_w: 733\n"
    assert anchor in text, "the fixture no longer matches cabin_heat_csm_w"
    path.write_text(text.replace(anchor, "    total_w: 740\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert (
        "the cabin would relax toward a heat rate its equipment does not produce"
        in result.stdout.lower()
    )


def test_the_cabin_equilibrium_is_inside_its_own_limit_band(tmp_path):
    """Four declarations across three files have to agree for the cabin to be a habitable cabin.

    The heat its equipment puts in (from the power domain's load inventory, summed), the lumped
    conductance, the coolant supply temperature, and the zone's own `limit_c`. Nothing joined them,
    and the arithmetic is one line: **T = supply + Q/G**.

    Writing it found a swapped pair of fields. `loop_primary` declared `supply_c: [2.8, 7.2]` and
    `evaporator_outlet_c: 5.3`, while its own source reads *"mixed supply 45 F = 7.2 C, evaporator
    outlet 41.5 F = 5.3 C over a 37-45 F range"* — the supply carried the evaporator's span and the
    evaporator carried that span's midpoint. Taken at face value the lower end is a 2.8 C supply, and
    at 2.8 C the CSM cabin sits at **8.66 C against a 10 C floor**: the vehicle would trip its own
    cabin-low alarm on every cold pass of a nominal mission.

    `loop_lm` was worse. Its `supply_c: [1.7, 12]` was the *magnitude* of the operating range's cold
    end with its sign lost, paired with an upper bound from nowhere — and the source gives an
    operating range, not a supply temperature at all.
    """
    vehicle = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
    thermal = yaml.safe_load((VEHICLE / "domains" / "thermal" / "components.yaml").read_text())
    loops = {str(x["id"]): x for x in vehicle["thermal"]["loops"]}
    zones = {str(x["id"]): x for x in vehicle["thermal"]["zones"]}
    states = {str(s["id"]): s for s in thermal["state"]}

    for zone, loop_id, heat_id, cabin_id in (
        ("csm_cabin", "loop_primary", "cabin_heat_csm_w", "zone_csm_cabin_t"),
        ("lm_cabin", "loop_lm", "cabin_heat_lm_w", "zone_lm_cabin_t"),
    ):
        supply = loops[loop_id]["supply_c"]
        assert isinstance(supply, (int, float)), f"{loop_id}.supply_c is a band, not a supply"
        equilibrium = supply + states[heat_id]["total_w"] / states[cabin_id]["conductance_w_per_k"]
        low, high = zones[zone]["limit_c"]
        assert low < equilibrium < high, f"{zone} sits at {equilibrium:.2f} C in [{low}, {high}]"

    # And a supply that puts the cabin under its own floor is refused rather than absorbed.
    definition = copy_definition(tmp_path / "cold")
    path = definition / "vehicle.yaml"
    text = path.read_text()
    anchor = "        supply_c: 7.2\n        return_c: [5, 15]"
    assert anchor in text, "the fixture no longer matches loop_primary"
    path.write_text(text.replace(anchor, "        supply_c: 1.0\n        return_c: [5, 15]", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "trip its own cabin-low alarm" in result.stdout


def test_the_cabin_relaxes_toward_supply_plus_its_own_rise(tmp_path):
    """A cabin has two heat inputs and a `lag` takes one driver — so the two are combined upstream.

    Round 55 gave the cabins a driver and introduced an 8 K error in the same move: relaxing toward
    `Q/G` *absolute* rather than `supply + Q/G`, which is wrong in the direction that makes a warm
    cabin look nominal. The fix is not a new method but a node: `cabin_eq_csm_k` and `cabin_eq_lm_k`
    are algebraic states carrying the equilibrium, fed by two edges each — the heat rate through
    `1/G` and the coolant supply through one-for-one — and the cabins relax toward them.

    **These are the vehicle's first states whose rule is completely specified**: nothing in either is
    owed, and every term comes from a declaration that already existed.
    """
    vehicle = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
    thermal = yaml.safe_load((VEHICLE / "domains" / "thermal" / "components.yaml").read_text())
    states = {str(s["id"]): s for s in thermal["state"]}
    loops = {str(x["id"]): x for x in vehicle["thermal"]["loops"]}

    for zone, loop_id, heat, eq, cabin in (
        ("csm_cabin", "loop_primary", "cabin_heat_csm_w", "cabin_eq_csm_k", "zone_csm_cabin_t"),
        ("lm_cabin", "loop_lm", "cabin_heat_lm_w", "cabin_eq_lm_k", "zone_lm_cabin_t"),
    ):
        supply_k = loops[loop_id]["supply_c"] + 273.15
        expected = supply_k + states[heat]["total_w"] / states[cabin]["conductance_w_per_k"]
        assert states[eq]["total_k"] == pytest.approx(expected, abs=0.02), zone
        # Nothing owed: the rule's every input is a declaration that exists.
        assert "UNCONFIGURED" not in yaml.safe_dump(states[eq])

    # And the two cabins differ by exactly their heat loads' difference over G.
    delta = (states["cabin_heat_lm_w"]["total_w"] - states["cabin_heat_csm_w"]["total_w"]) / 125
    assert states["cabin_eq_lm_k"]["total_k"] - states["cabin_eq_csm_k"][
        "total_k"
    ] == pytest.approx(delta, abs=0.02)

    definition = copy_definition(tmp_path / "stale")
    path = definition / "domains" / "thermal" / "components.yaml"
    text = path.read_text()
    anchor = "    total_k: 286.21\n"
    assert anchor in text, "the fixture no longer matches cabin_eq_csm_k"
    path.write_text(text.replace(anchor, "    total_k: 290.0\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "relax toward an equilibrium its own declarations do not produce" in result.stdout


def test_the_readme_status_matches_the_tools():
    """The status section is the one place every count is written down, and it had drifted.

    Three rounds of structural work moved the state count, the node count and the debt count, and
    the commit messages carried the right figures while the README kept the old ones — which is this
    folder's own recurring finding arriving at its own status section: **a declaration no tool reads
    has already drifted.** The paragraph even said "with every one of them named", about a number
    that was two out of date.

    So every figure is derived here from the tools' own output rather than from a second counter. A
    counter written for this test would be one more declaration to drift; the linter and the plant
    already compute all of them, and a test that reads their reports cannot disagree with them.
    """
    readme = (VEHICLE / "README.md").read_text()
    lint = run_linter(VEHICLE)
    assert lint.returncode == 0, lint.stdout[-1200:]
    plant = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "plant.py"), "--readiness"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    order = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "plant.py"), "--build-order"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout

    channels, edges = re.search(r"(\d+) channels, (\d+) edges,", lint.stdout).groups()
    debts = re.search(r"with (\d+) declared debt", lint.stdout).group(1)
    states, nodes = re.search(r"world: (\d+) states over (\d+) nodes", plant).groups()
    scalars = re.search(r"UNCONFIGURED scalars\s+(\d+)", plant).group(1)
    rule = re.search(r"(\d+)\s+\d+ %\s+owes a rule", order).group(1)

    # The sentence that carries them, and the paragraphs that restate two of them.
    for needle, what in (
        (f"{channels} channels, {states} states over {nodes} scheduled nodes", "the status line"),
        (f"with {debts} declared debts", "the debt count"),
        (f"Current state: **composes, with {debts} declared debts.**", "the header"),
        (f"The **{scalars}** the plant", "the plant's narrower count"),
        (f"so {rule} of the {states} states need code", "the domain-code count"),
        (f"{states} states, by what blocks them", "the build-order view"),
    ):
        assert needle in readme, f"{what} is stale: expected {needle!r} in the README"

    # Every occurrence, not just the first. The loop above pins the *presence* of the right figure,
    # and that is what let the same paragraph keep a second, stale one for eleven rounds: line 59
    # carried "223 declared debts" and line 177 carried "252", so a test satisfied by either was
    # satisfied by a file that contradicted itself. It is this folder's own finding arriving at the
    # test that exists to catch it — a check that reads the declaration it is looking for cannot see
    # the one beside it.
    #
    # A figure the README *asserts* is unquoted; a figure it *quotes* is history. The section that
    # records this very drift says *it said "… with 254 declared debts …" while the tools said 124,
    # 45 and 252* — and those are the evidence, not a claim, so the quoted spans come out first and
    # what remains is what the file is currently telling a reader.
    # And the build-order view the README embeds, which is an *output* rather than a figure and had
    # therefore drifted further than any of them: it read "12 owes a value / 36 owes an edge / 61
    # owes a rule" against the tool's 24 / 28 / 71, under a sentence promising that "`plant.py
    # --build-order` classifies every state by `advance()`'s own refusal order ... so the two cannot
    # disagree". They disagreed by ten states in one bucket and fifteen in another. An embedded
    # transcript is the most convincing thing in a README and the least likely to be re-run.
    order_view = subprocess.run(
        [sys.executable, str(VEHICLE / "tools" / "plant.py"), "--build-order"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    # The four bucket lines are the block the README embeds; the "first of the N" listings below
    # them are the view's tail and are not quoted.
    buckets = [line for line in order_view.splitlines() if re.match(r"^\s+\d+\s+\d+ %", line)]
    assert len(buckets) == 4, buckets
    for line in buckets:
        assert line in readme, f"the README's build-order block is stale: missing {line!r}"

    asserted = re.sub(r'"[^"]*"', "", readme)
    written = re.findall(r"(\d+) declared debts?", asserted)
    assert written, "the README states no debt count at all"
    assert set(written) == {debts}, (
        f"the README states the debt count as {sorted(set(written))}; the linter says {debts}"
    )

    # And the reconciliation README's prose count of *these* tests, which is the one figure a
    # reader uses to judge how much of the definition is held in place. It said one hundred
    # twenty-six while this file held one hundred thirty-four — the same unread-prose failure one
    # directory over, and it had been wrong for eight rounds. The number is derived from this
    # module's own globals, so adding a test and forgetting the sentence fails here rather than
    # in a reader's estimate of the folder.
    reconciliation = (
        REPO / "docs" / "deep_research" / "integration" / "reconciliation" / "README.md"
    ).read_text()
    mine = len([name for name in globals() if name.startswith("test_")])
    assert mine > 100, f"the self-count found {mine} tests, which is not this file's shape"
    needle = f"One {_in_words(mine)} tests"
    assert needle in reconciliation, (
        f"the reconciliation README does not say {needle!r} about this file, which holds {mine}"
    )


def _in_words(n: int) -> str:
    """Enough of a number-to-words conversion for a count in the low hundreds.

    Written rather than imported because the alternative is a dependency the operator-side services
    are not allowed to have, and because the range is small and known: this file's test count, in
    the hundreds, spelled the way the reconciliation README spells it.
    """
    units = (
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
    )
    tens = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
    if n < 20:
        return units[n]
    if n < 100:
        return tens[n // 10] + (f"-{units[n % 10]}" if n % 10 else "")
    if n % 100 == 0:
        return "hundred"
    return f"hundred {_in_words(n % 100)}"


def test_the_registry_coverage_claim_is_data_rather_than_a_sentence(tmp_path):
    """The last vehicle-wide count in prose, and two of its three numbers were wrong.

    Each domain has made a `coverage` claim since round 42 and each is checked against its own
    faults. The *registry's* own claim was a sentence in `channels.yaml:open_debts`, and nothing
    read it: it said twelve of the twenty-two unperturbed channels are `layer: service` where the
    policy gives fifteen of twenty, and it said faults perturb **117** `service` channels where
    they perturb 42.

    That second number is the one that matters, because it was never arithmetically possible. The
    `service` layer is 57 of the registry's 148 channels, so no split of it can reach 117 — and the
    sentence sat there through several rounds of channel additions. **A number in prose has no
    reader, and a number with no reader does not have to be plausible.** The two domain-level
    claims beside it were caught the moment they became fields; this one stayed prose for thirty
    rounds longer.

    So the numbers are data now, and this test does two things the linter's own check cannot do for
    itself: it re-derives all three from the YAML rather than trusting the report, and it proves
    the check refuses the historical value by putting it back.
    """
    channels = yaml.safe_load((VEHICLE / "channels.yaml").read_text())
    coverage = channels["coverage"]

    def flatten(name: object) -> str:
        return re.sub(r"\[[^\]]*\]", "[]", str(name))

    registry, layers = set(), {}
    for section, rows in channels.items():
        if section in {"coverage", "crew_positions", "open_debts", "defaults"}:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("id"):
                registry.add(flatten(row["id"]))
                layers[flatten(row["id"])] = row.get("layer")
    assert len(registry) == 148, f"the registry is {len(registry)} channels, not 148"

    perturbed = set()
    for policy_path in sorted((VEHICLE / "domains").glob("*/fault_policy.yaml")):
        policy = yaml.safe_load(policy_path.read_text())
        for fault in policy.get("faults") or []:
            perturbed.update(flatten(c) for c in fault.get("perturbs") or [])
    unperturbed = registry - perturbed

    assert coverage["unperturbed"] == len(unperturbed)
    assert coverage["unperturbed_service_layer"] == sum(
        1 for c in unperturbed if layers.get(c) == "service"
    )
    assert coverage["perturbed_service_layer"] == sum(
        1 for c in perturbed if layers.get(c) == "service"
    )
    assert coverage["provenance"]["basis"] == "derived"

    # The sentence no longer restates them, which is the half that makes the block the only source.
    prose = " ".join(str(d) for d in channels["open_debts"])
    assert "Twelve of the 22" not in prose, "the stale count is back in the prose"
    assert "117 of the channels" not in prose, "the impossible count is back in the prose"

    # And the check refuses the historical value, at the field that carried it.
    definition = copy_definition(tmp_path / "coverage")
    path = definition / "channels.yaml"
    text = path.read_text()
    broken = text.replace("perturbed_service_layer: 42", "perturbed_service_layer: 117", 1)
    assert broken != text, "the fixture no longer matches channels.yaml"
    path.write_text(broken)

    result = run_linter(definition)
    assert result.returncode == 1, result.stdout[-900:]
    assert "channels.yaml:coverage.perturbed_service_layer" in result.stdout, result.stdout[-900:]
    assert "claims 117 and the policies give 42" in result.stdout, result.stdout[-900:]


def test_a_configuration_cannot_declare_two_different_masses(tmp_path):
    """`mass_kg` and `mass_breakdown_total_kg` are one quantity, and only one of them was checked.

    The breakdown was summed against `mass_breakdown_total_kg`, and `mass_kg` went to
    `check_propulsion` as a burn's wet mass. **Nothing required the two to agree**, so a
    configuration could declare a 400 kg disagreement and compose — and the README quotes the
    unchecked one in its mass-closure table. A fleet's trajectory and its mass closure would have
    been working from two different vehicles.

    This is the same shape the folder has found four times before (the phase sum, the cabin leak,
    the bay's mass-and-conductance, the threshold's `assert`/`clear`). The difference is that here
    *both names are right* — the breakdown's total really is the configuration's mass — so the fix
    is not to collapse them into one but to make them agree.
    """
    vehicle = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
    for cfg in vehicle["configurations"]:
        assert cfg["mass_kg"] == cfg["mass_breakdown_total_kg"], cfg["id"]
        assert sum(cfg["mass_breakdown"].values()) == cfg["mass_kg"], cfg["id"]

    definition = copy_definition(tmp_path / "mass")
    path = definition / "vehicle.yaml"
    text = path.read_text()
    broken = text.replace("mass_kg: 28807", "mass_kg: 28407", 1)
    assert broken != text, "the fixture no longer matches vehicle.yaml"
    path.write_text(broken)

    result = run_linter(definition)
    assert result.returncode == 1, result.stdout[-900:]
    assert "vehicle.yaml:configuration csm_alone" in result.stdout, result.stdout[-900:]
    assert "which are the same quantity" in result.stdout, result.stdout[-900:]


def test_an_irreversible_event_names_configurations_that_exist(tmp_path):
    """`from_configuration` and `to_configuration` say what an event irreversibly *does*, unread.

    `verb`, `arm_required` and `observable` were all checked; the two fields that say what the
    event does to the vehicle were read by nothing. Writing the join found the defect it was
    written for — `lm_ascent_jettison` ran `csm_alone -> csm_alone`, the configuration defined as
    "CSM alone *after* the LM is jettisoned" — which was only expressible because the vehicle the
    event actually begins in had no configuration at all.

    The mission spends 7.5 hours in it. `lunar_orbit_docked` is named "docked again" and declared
    `csm_alone`; `ascent_rendezvous` ended there too. All three files were individually consistent.
    """
    vehicle = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
    declared = {c["id"] for c in vehicle["configurations"]}
    assert "csm_lm_ascent_docked" in declared, "the re-docked configuration is missing again"

    events = yaml.safe_load((VEHICLE / "domains" / "structure" / "components.yaml").read_text())[
        "one_way_events"
    ]
    by_id = {e["id"]: e for e in events}
    for event in events:
        for field in ("from_configuration", "to_configuration"):
            value = event[field]
            assert value in declared or value in {"any", "depends on the device"}, (
                event["id"],
                field,
            )

    # `lm_ascent_jettison` removes the ascent stage, so it has to begin where the ascent stage is.
    jettison = by_id["lm_ascent_jettison"]
    assert jettison["from_configuration"] == "csm_lm_ascent_docked"
    assert jettison["to_configuration"] == "csm_alone"
    # And the two phases either side of it name the same vehicle, in order.
    mission = yaml.safe_load((VEHICLE / "mission.yaml").read_text())
    phases = {p["id"]: p["configurations"] for p in mission["phases"]}
    assert phases["ascent_rendezvous"] == ["lm_ascent_stage", "csm_lm_ascent_docked"]
    assert phases["lunar_orbit_docked"] == ["csm_lm_ascent_docked", "csm_alone"]

    # A dangling endpoint is refused, which is the check the live definition cannot demonstrate.
    definition = copy_definition(tmp_path / "endpoint")
    path = definition / "domains" / "structure" / "components.yaml"
    text = path.read_text()
    broken = text.replace("from_configuration: csm_lm_docked", "from_configuration: bogus_cfg", 1)
    assert broken != text, "the fixture no longer matches structure/components.yaml"
    path.write_text(broken)
    result = run_linter(definition)
    assert result.returncode == 1, result.stdout[-900:]
    assert "bogus_cfg" in result.stdout, result.stdout[-900:]


def test_a_stock_integrates_its_level_and_carries_the_residue():
    """The integrator returned the tick's flux as the tank's new value, and never read the tank.

    `stock_flux` returns a *delta* — `sensitivity x driver x dt` — and the stock branch summed
    those deltas and returned the sum as the node's value. So a tank holding 279 kg with a drain
    became `-6.4e-06` on the first tick: **the integrator did not integrate**, in the one class
    the plant claims it can advance and `--build-order` counts as "ready now". `lag` read
    `current`; `stock` did not.

    This test is `plant.md` §4's own worked example, which is this vehicle's: a 0.0064 g/s leak
    against a 1 mg quantum is 0.128 quanta per tick at the 50 Hz tick, so *"every tick rounds to
    zero and the stock never moves"* — "the leak never happens". The Bresenham residual
    accumulator is what makes it happen exactly, and the assertion below is the one that
    distinguishes the two: over a second the level must fall by the true flow to within one
    quantum, where a quantum-only implementation loses **nothing at all**.
    """
    plant = _plant()

    def make_world():
        empty = {
            "kind": "sink",
            "domain": "x",
            "unit": "W",
        }
        stock = plant.State(
            id="o2_csm_kg",
            domain="consumables",
            node="o2_csm",
            method="stock",
            unit="kg",
            spec={"quantum": 1e-6},
        )
        sink = plant.State(id="sink", domain="x", node="sink", method="lag", unit="kg", spec={})
        edge = plant.Edge(
            id="E",
            source="o2_csm",
            target="sink",
            kind="rate",
            sensitivity={"value": 0.0064e-3, "unit": "kg/s per W"},
            drains="o2_csm_kg",
        )
        return plant.World(
            root=VEHICLE,
            states=[stock, sink],
            edges=[edge],
            back_edges=set(),
            schedule=["o2_csm"],
            nodes={
                "o2_csm": {
                    "kind": "stock",
                    "domain": "consumables",
                    "unit": "kg",
                    "preloaded": "pad",
                },
                "sink": empty,
            },
            channels={},
            frame_fields=[],
            verbs={},
        )

    world = make_world()
    dt = 0.02
    values = {"o2_csm": 279.0, "sink": 1.0}
    for _ in range(50):
        values = plant.step(world, values, dt)

    moved = 279.0 - values["o2_csm"]
    quantum = 1e-6
    assert moved > 0, "the leak never happens — the accumulator is not carrying the residue"
    assert abs(moved - 6.4e-6) <= quantum, f"moved {moved}, which is more than one quantum out"

    # The level is integrated from, not replaced: 50 ticks of 0.128 quanta cannot leave a
    # 279 kg tank within a milligram of zero, which is what returning the flux would do.
    assert values["o2_csm"] > 278.0, "the level was replaced by the flux rather than integrated"
    assert "o2_csm_kg__residual" in values, "no residue is carried between ticks"


def test_every_stock_declares_where_it_starts():
    """A stock's initial amount is what the plant integrates *from*, and nothing declared one.

    The integrator bug hid this and this hid the bug. `vehicle.yaml#consumables` carries the
    loads, `coupling.yaml`'s `preloaded` prose names them a second time, the atmosphere model
    derives the cabin oxygen from the published volume and pressure — and **no state carried a
    starting amount**, because a branch that never reads a level never asks for one.

    So every stock now declares `initial`, and a numeric one must say where it came from: either
    `initial_source`, a resolvable path into the document that declares the same number, or its
    own `initial_provenance`. A figure with neither is a guess wearing a unit.
    """
    plant = _plant()
    world = plant.load_world(VEHICLE)
    stocks = [s for s in world.states if s.method == "stock"]
    assert len(stocks) == 25, f"{len(stocks)} stocks"

    seeded = plant.initial_values(world)
    # Fifteen stocks declare a value; six of them are the accumulators on the `internal`
    # sentinel — `bias_accumulator`, `sensor_bus_errors`, `frame_loss`, `recorder`,
    # `pulse_residual`, `impulse_total` — which are one shared key and are not seeded.
    declared = [s for s in stocks if isinstance(s.spec.get("initial"), (int, float))]
    assert len(declared) == 15, f"{len(declared)} stocks declare a numeric initial"
    assert len(seeded) == 9, f"{len(seeded)} stocks carry a value the plant can start from"
    # The ones the corpus can supply, and the numbers it supplies them with.
    for node, expected in (
        ("o2_csm", 279.0),
        ("o2_lm", 24.1),
        ("h2_csm", 24.5),
        ("water_potable", 14.0),
        ("water_cooling", 13.0),
        ("absorber_capacity_csm", 72.0),
        ("absorber_capacity_lm", 41.0),
    ):
        assert seeded[node] == expected, node
    # `internal` is one key shared by every state on the sentinel, so it is not seeded.
    assert "internal" not in seeded

    # Every numeric initial is grounded, and every `initial_source` resolves and agrees.
    vehicle = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    for path in sorted((VEHICLE / "domains").glob("*/components.yaml")):
        components = yaml.safe_load(path.read_text()) or {}
        for state in components.get("state") or []:
            if state.get("method") != "stock":
                continue
            assert "initial" in state, f"{state['id']} declares no initial condition"
            if state["initial"] == "UNCONFIGURED":
                assert state.get("initial_note"), f"{state['id']} is owed with no note"
                continue
            source = state.get("initial_source")
            assert source or state.get("initial_provenance"), (
                f"{state['id']} declares {state['initial']!r} with no grounding"
            )
            if not source:
                continue
            filename, dotted = source.split(":", 1)
            node = {"vehicle.yaml": vehicle, "coupling.yaml": coupling}[filename]
            for step in dotted.split("."):
                node = (
                    node[step]
                    if isinstance(node, dict)
                    else next(row for row in node if str(row.get("id")) == step)
                )
            assert abs(float(node) - float(state["initial"])) < 1e-9, (
                f"{state['id']} says {state['initial']} and {source} says {node}"
            )


def test_a_check_that_iterates_a_missing_block_is_not_a_check(tmp_path):
    """Three blocks could be deleted outright and the build stayed green.

    A deletion test — remove a block, run every tool, diff the output — found nine blocks the
    vehicle does not notice losing. Three of them were worse than unread: **the linter had code
    for them, and the code could not run.** `quality_assignment` was guarded by
    `if isinstance(quality, dict)`, `display_contract` by `or {}` and an empty loop, and
    `atmosphere_model` by an early `return` — so all three reported on nothing when the block was
    gone, which is indistinguishable from reporting that all is well.

    Between them they are four hundred lines: the quality-assignment function
    `simulator-design.md:496-508` requires, the display contract the perception bound is
    cross-checked against, and the atmosphere model that makes a cabin's contents species rather
    than one mass. Each is now refused by name when absent.
    """
    for domain, key, filename in (
        ("avionics", "quality_assignment", "components.yaml"),
        ("crew", "display_contract", "components.yaml"),
        ("eclss", "atmosphere_model", "components.yaml"),
    ):
        definition = copy_definition(tmp_path / domain)
        path = definition / "domains" / domain / filename
        lines = path.read_text().split("\n")
        start = next(i for i, line in enumerate(lines) if line.startswith(f"{key}:"))
        end = start + 1
        while end < len(lines) and not re.match(r"^[A-Za-z_]", lines[end]):
            end += 1
        removed = end - start
        assert removed > 5, f"{domain}/{key} is only {removed} lines"
        path.write_text("\n".join(lines[:start] + lines[end:]))

        result = run_linter(definition)
        assert result.returncode == 1, f"{domain}/{key} deleted and nothing noticed"
        assert f":{key}" in result.stdout, result.stdout[-900:]


def test_the_blocks_no_tool_read_name_things_that_resolve(tmp_path):
    """Three more of the nine, and what makes them worth wiring is that they are full of names.

    `consumables/ledgers` names twelve channel ids across four rows, `crew/alert_overlays` names
    three overlay ids a verb has to be able to set, and `thermal/load_budget` states a rejection
    total that is the sum of two figures in its own file. All fifteen names and the closure are
    right today — which is exactly the condition under which the sixteenth is added wrong, and
    until this round nothing read any of them.
    """
    report = run_linter(VEHICLE)
    assert report.returncode == 0, report.stdout[-900:]

    # The thermal total is a closure over its own file's parts.
    thermal = yaml.safe_load((VEHICLE / "domains" / "thermal" / "components.yaml").read_text())
    parts = [thermal["radiator_model"]["csm"]["rejection_w"]]
    parts += [
        c["rejection_w"]
        for c in thermal["components"]
        if isinstance(c.get("rejection_w"), (int, float))
    ]
    assert sum(parts) == thermal["load_budget"]["total_rejection_capacity_w"], parts

    # Every ledger channel resolves, and the resource is a coupling node.
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    raw_nodes = coupling["nodes"]
    nodes = (
        {str(n["id"]) for n in raw_nodes}
        if isinstance(raw_nodes, list)
        else {str(k) for k in raw_nodes}
    )
    assert nodes, "no coupling nodes were read"
    consumables = yaml.safe_load(
        (VEHICLE / "domains" / "consumables" / "components.yaml").read_text()
    )
    assert len(consumables["ledgers"]) == 4
    for row in consumables["ledgers"]:
        assert row["resource"] in nodes, row["resource"]

    # A deletion the checks exist to catch, in the shape a typo takes.
    definition = copy_definition(tmp_path / "ledger")
    path = definition / "domains" / "consumables" / "components.yaml"
    text = path.read_text()
    broken = text.replace('"res.ledger_o2_kg"', '"res.ledger_o2_kq"', 1)
    assert broken != text, "the fixture no longer matches consumables/components.yaml"
    path.write_text(broken)
    result = run_linter(definition)
    assert result.returncode == 1, result.stdout[-900:]
    assert "res.ledger_o2_kq" in result.stdout, result.stdout[-900:]

    # And the budget's, which is the closure that has no other reader.
    definition = copy_definition(tmp_path / "budget")
    path = definition / "domains" / "thermal" / "components.yaml"
    text = path.read_text()
    broken = text.replace("total_rejection_capacity_w: 4933", "total_rejection_capacity_w: 5933", 1)
    assert broken != text, "the fixture no longer matches thermal/components.yaml"
    path.write_text(broken)
    result = run_linter(definition)
    assert result.returncode == 1, result.stdout[-900:]
    assert "load_budget.total_rejection_capacity_w" in result.stdout, result.stdout[-900:]


def test_the_internal_sentinel_is_not_exempt_from_the_ordering_rule():
    """The rule says "each node with more than one producing state". The code said "unless internal".

    `check_domains` requires a node advanced by two or more states to declare a `state_order` or
    to claim `independent`, and the comment beside it records what the requirement is for: the
    frozen lexicographic tiebreak sorted `link_snr` before `tx_power`, on a node where transmit
    power is a term in the link budget, so the derived order computed this tick's ratio from last
    tick's power. *"Silence about them means the alphabet decides."*

    The loop implementing it read `if node and node != "internal"`, and neither `plant.md` nor
    `coupling.yaml` says why. So 54 states across nine domains stayed alphabetical. The sentinel
    is the worse place for it, not the better one: a node's producing states are at least joined
    by edges that say what feeds what, and `internal` states have no edges at all — that is what
    the sentinel means — so the alphabet was the only signal there was.

    Nine domains owe the declaration and no source in the corpus supplies it, so each is a debt
    naming its own states rather than a refusal: the honest instrument for a declaration that is
    needed and unset.
    """
    owed = []
    for components_path in sorted((VEHICLE / "domains").glob("*/components.yaml")):
        components = yaml.safe_load(components_path.read_text()) or {}
        on_sentinel = sorted(
            str(s["id"])
            for s in components.get("state") or []
            if isinstance(s, dict) and str(s.get("node")) == "internal" and s.get("id")
        )
        if len(on_sentinel) < 2:
            assert "internal_order" not in components, (
                f"{components_path.parent.name} declares an order for fewer than two sentinel states"
            )
            continue
        assert "internal_order" not in components, (
            f"{components_path.parent.name} declares one — update this test to check it"
        )
        owed.append((components_path.parent.name, on_sentinel))

    assert len(owed) == 9, f"{len(owed)} domains owe an `internal_order`: {[d for d, _ in owed]}"
    assert sum(len(s) for _, s in owed) == 54, "the sentinel's state count moved"

    result = run_linter(VEHICLE)
    assert result.returncode == 0, result.stdout[-900:]
    reported = [line for line in result.stdout.splitlines() if "internal_order:" in line]
    assert len(reported) == 9, f"{len(reported)} of 9 reported"
    for domain, states in owed:
        line = next(x for x in reported if f"domains/{domain}/" in x)
        for state in states:
            assert state in line, f"{domain}'s debt does not name {state}"


def test_vehicle_yaml_counts_its_own_open_debts():
    """The file's `VEHICLE_SECTIONS` comment said these were counted, and nothing counted them.

    `channels.yaml`, `coupling.yaml` and the eleven domains each report their `open_debts` as
    debts. `vehicle.yaml`'s **nine** were read by no code at all, and the linter's own comment
    beside the section name claimed otherwise: *"counted and printed, like every other
    `open_debts` in the folder"*. Dropping eight of the nine left the headline count unchanged.

    What was missing from the number that exists to count what is missing is not marginal — the
    inertia tensor per configuration, the thermal zones' capacities and conductances, the minimum
    impulse bit for all three RCS systems, the forty-four thrusters' geometry, the fuel cell's
    reactant consumption, the ullage motors and the power inventory's unchecked relationships.
    **A file's own statement that a section is read is not evidence that it is**, which is this
    folder's oldest finding pointed at the tool that enforces it.
    """
    vehicle = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
    entries = vehicle["open_debts"]
    assert len(entries) >= 9, f"vehicle.yaml declares only {len(entries)} open debts"

    result = run_linter(VEHICLE)
    assert result.returncode == 0, result.stdout[-900:]
    reported = [
        line
        for line in result.stdout.splitlines()
        if line.strip().startswith("- vehicle.yaml:open_debts:")
    ]
    assert len(reported) == len(entries), (
        f"{len(entries)} entries declared and {len(reported)} counted; the rest are in no number"
    )

    # The headline is the sum of the two halves, which is what makes it worth quoting.
    owed = re.search(r"OWED \(a value that is needed and unset\) — (\d+)", result.stdout)
    assert owed, result.stdout[:400]
    assert f"with {owed.group(1)} declared debt(s)" in result.stdout


def test_the_fuel_cell_reactant_chain_is_grounded_but_for_one_figure():
    """The cell's draws are nodes now, and everything downstream of them is derivable.

    The tanks the cell drains had no computable outflow: the oxygen inventory is shared between
    ECLSS and the cells and nothing said at what rate. `fc_o2_draw` and `fc_h2_draw` are flow nodes
    with the whole chain declared — and **exactly one figure in it is owed**, the cell's per-joule
    oxygen consumption, which no source publishes (`vehicle.yaml#electrical` carries a standby
    sustain flow and no operating point).

    Everything else is grounded: the hydrogen draw is the published 8:1 mass ratio, and the water is
    stoichiometry. The availability edges moved with the draws, which is what let the two
    `C-REACTANT-DRAW` cycles close again — the path is now `fuel_cell -> fc_o2_draw -> fuel_cell`
    rather than through the tank, because what limits the cell is the *draw*, not the tank level.
    """
    plant = _plant()
    world = plant.load_world(VEHICLE)
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    edges = {e["id"]: e for e in coupling["edges"]}
    nodes = coupling["nodes"]

    for node, unit in (("fc_o2_draw", "kg O2/s"), ("fc_h2_draw", "kg H2/s")):
        assert nodes[node]["kind"] == "flow" and nodes[node]["unit"] == unit

    # The chain: the cell sets the draw, the tank supplies it, and the draw limits the cell.
    assert (edges["E-FC-DRAW-O2"]["from"], edges["E-FC-DRAW-O2"]["to"]) == (
        "fuel_cell",
        "fc_o2_draw",
    )
    assert (edges["E-O2-DRAW"]["from"], edges["E-O2-DRAW"]["to"]) == ("o2_csm", "fc_o2_draw")
    assert (edges["E-O2-FC"]["from"], edges["E-O2-FC"]["to"]) == ("fc_o2_draw", "fuel_cell")
    assert (edges["E-FC-WATER"]["from"], edges["E-FC-WATER"]["to"]) == (
        "fc_o2_draw",
        "water_potable",
    )

    # Both tank drains and the water production are computable, and the water is per kg of oxygen.
    for edge_id, driver in (("E-O2-DRAW", "to"), ("E-H2-DRAW", "to"), ("E-FC-WATER", "from")):
        edge = next(e for e in world.edges if e.id == edge_id)
        node = edge.target if driver == "to" else edge.source
        flux = plant.stock_flux(
            world, edge, {edge.source: 1.0, edge.target: 1.0}, 1.0, driver_node=node
        )
        assert flux > 0, edge_id
    water = next(e for e in world.edges if e.id == "E-FC-WATER")
    assert water.sensitivity["value"] == pytest.approx(36.03056 / 31.9988, rel=1e-3)

    # The two tanks are loaded at the pad, and now say so: with the draws moved off them they had no
    # inbound edge at all, which is the state the linter refuses unless `preloaded:` explains it.
    assert nodes["o2_csm"]["preloaded"] and nodes["h2_csm"]["preloaded"]


def test_the_cabin_oxygen_supplies_are_derived_from_the_losses(tmp_path):
    """The last two ratio refusals were the cabin supplies, and both are fully grounded.

    `E-O2-ECLSS` said "1 kg enters the cabin per kg of O2" against a *level* rather than a flow, so
    nothing could apply it. `cabin_o2_supply_csm` and `cabin_o2_supply_lm` are flow nodes now, and
    what the regulator admits is what the cabin loses: the leak plus the crew's metabolic
    consumption, both published.

    **`E-O2-SUPPLY-LM` is the better-attested of the two**, because the leak datum is Apollo 11's LM
    cabin leak of 0.05 lb/hr. The CSM's own leak is published nowhere, yet `consumables` sizes
    `o2_csm_kg`'s quantum from the same 0.023 kg/h as though it were the CSM's — so the figure is
    used here, and the attribution conflict is a named debt rather than a silent assumption.
    """
    eclss = yaml.safe_load((VEHICLE / "domains" / "eclss" / "components.yaml").read_text())
    states = {str(s["id"]): s for s in eclss["state"]}
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    edges = {e["id"]: e for e in coupling["edges"]}

    for state_id, expected in (
        ("cabin_o2_supply_csm_kg_s", (0.023 + 3 * 0.91 / 24) / 3600),
        ("cabin_o2_supply_lm_kg_s", (0.05 * 0.453592 + 2 * 0.91 / 24) / 3600),
    ):
        assert states[state_id]["nominal_kg_s"] == pytest.approx(expected, rel=1e-5), state_id
        assert states[state_id]["method"] == "algebraic"

    # Every stock edge on the oxygen path computes now, and the two cabin supplies are what closed it.
    assert edges["E-O2-SUPPLY-CSM"]["to"] == "cabin_o2_supply_csm"
    assert edges["E-O2-ECLSS"]["from"] == "cabin_o2_supply_csm"
    assert edges["E-O2-SUPPLY-LM"]["to"] == "cabin_o2_supply_lm"
    assert edges["E-LM-O2-ECLSS"]["from"] == "cabin_o2_supply_lm"

    definition = copy_definition(tmp_path / "derivation")
    path = definition / "domains" / "eclss" / "components.yaml"
    text = path.read_text()
    anchor = 'computation: "(0.023 + 3 * 0.91 / 24) / 3600"'
    assert anchor in text, "the fixture no longer matches the CSM supply rule"
    path.write_text(text.replace(anchor, 'computation: "(0.023 + 3 * 0.91 / 24)"', 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "does not re-derive" in result.stdout


def test_the_water_cycle_edges_have_the_right_way_round(tmp_path):
    """One relation, two edges, and until round 61 the stock was on the wrong side of both.

    `E-RAD-WATER` said `kg/s per W` and ran *into* `water_cooling`, so the plant **filled** the tank
    with the water the radiator consumes. `E-WATER-RAD` ran out of it — the side a stock discharges
    through — carrying `kg per J`, which is the *forward* relation's unit: the edge's own note said
    "the inverse of E-RAD-WATER" and then stated the same number in the same unit.

    Swapped, the two are one relation with the stock on opposite sides: the discharge takes
    `kg/s per W` and computes, and the availability half takes `J per kg` — what a kilogram of water
    *buys*, 2.45e6 J — and is refused as a stock flux, correctly, because availability is a clamp
    rather than a slope. The linter's cycle check confirms the pair still closes
    `radiator_reject -> water_cooling -> radiator_reject`.
    """
    plant = _plant()
    world = plant.load_world(VEHICLE)
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    edges = {e["id"]: e for e in coupling["edges"]}

    assert edges["E-WATER-RAD"]["from"] == "water_cooling"
    assert edges["E-WATER-RAD"]["sensitivity"]["unit"] == "kg/s per W"
    assert edges["E-RAD-WATER"]["sensitivity"]["unit"] == "J per kg"
    assert edges["E-RAD-WATER"]["sensitivity"]["value"] == pytest.approx(2.45e6)

    # The discharge computes, and it is the *target* that drives it: the radiator's wattage sets
    # how fast the water goes.
    edge = next(e for e in world.edges if e.id == "E-WATER-RAD")
    flux = plant.stock_flux(
        world, edge, {edge.source: 100.0, edge.target: 1000.0}, 1.0, driver_node=edge.target
    )
    assert flux == pytest.approx(4.0816e-4, rel=1e-3)

    # The cycle still closes, and the linter refuses it if it stops.
    cycle = next(c for c in coupling["cycles"] if c["id"] == "C-WATER-BUDGET")
    assert set(cycle["members"]) == {"E-WATER-RAD", "E-RAD-WATER"}
    assert cycle["back_edge"] == "E-WATER-RAD"
    result = run_linter(VEHICLE)
    assert result.returncode == 0, result.stdout[-800:]


def test_the_propulsion_edges_are_stated_as_drains(tmp_path):
    """`N per kg/s` is thrust per unit of flow — an engine's *production*, under a tank's edge.

    `prop_main` and `prop_rcs` discharge through their outbound edges, and an outbound edge reads
    its **target** as the driver: the tank drains at whatever rate the thrust demands. Stated as
    `N per kg/s` the edge gave the plant a force to multiply a propellant mass by, and the
    dimensional check refused it — correctly, because N per (kg/s) is what an engine *produces*, not
    what a tank loses.

    Both reversed figures are published rather than owed: Isp 314.5 s and 290 s are in
    `vehicle.yaml#propulsion`, so `1/(Isp x g0)` closes each edge exactly and **249 became 247**.
    """
    plant = _plant()
    world = plant.load_world(VEHICLE)
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    edges = {e["id"]: e for e in coupling["edges"]}

    for edge_id, isp in (("E-PROP-ENG", 314.5), ("E-RCSP-RCS", 290.0)):
        edge = edges[edge_id]
        assert edge["sensitivity"]["unit"] == "kg/s per N", edge_id
        assert edge["sensitivity"]["value"] == pytest.approx(1.0 / (isp * 9.80665), rel=1e-9)
        # No `advances`: each target carries a single state, so the declaration is not required —
        # and it would be wrong now, because the edge reads the thrust rather than producing it.
        assert edge.get("advances") is None, edge_id

    # A thousand newtons of SPS thrust drains 1000/3084.2 kg/s of propellant.
    e = next(x for x in world.edges if x.id == "E-PROP-ENG")
    flux = plant.stock_flux(
        world, e, {e.source: 100.0, e.target: 1000.0}, 1.0, driver_node=e.target
    )
    assert flux == pytest.approx(1000.0 / (314.5 * 9.80665), rel=1e-9)

    # `prop_rcs` has no *inbound* edge at all — it is loaded at the pad and never refilled — so the
    # linter would report it undriven if the declaration were absent.
    assert coupling["nodes"]["prop_rcs"]["preloaded"]

    definition = copy_definition(tmp_path / "forward")
    path = definition / "coupling.yaml"
    text = path.read_text()
    anchor = '      unit: "kg/s per N"'
    assert anchor in text, "the fixture no longer matches the propulsion edges"
    path.write_text(text.replace(anchor, '      unit: "N per kg/s"', 1))

    # A stock-flux failure is reported as a *debt* rather than a refusal — the vehicle genuinely is
    # not finished — so the build still composes and the edge appears in the owed list by name.
    result = run_linter(definition)
    assert result.returncode == 0, result.stdout[-800:]
    assert "whose unit is 'N'" in result.stdout
    assert "coupling.yaml:edge E-PROP-ENG:" in result.stdout


def test_the_absorbers_remove_from_their_own_cabin(tmp_path):
    """One removal rate for two absorbers is the round-42 defect one layer up.

    The counters were split then; the *rate that spends them* was not. `co2_removal_kg_s` was a
    single algebraic state on the `internal` sentinel **reading both counters**, so it converted two
    beds' remaining capacity into one rate for one vehicle — and a crew on the surface spent the CSM
    element while a crew back in the CM spent the LM cartridge.

    Split into `co2_removal_csm_kg_s` and `co2_removal_lm_kg_s`, each on its own flow node, the chain
    is per-compartment end to end: the cabin loses CO2 to its own removal, the removal spends its own
    counter, and the removal rate is two thirds of the CSM's on the LM because two crew produce it
    rather than three — a *different* number, and one a shared state could not express.

    It also made the two absorber edges computable. `man-hours per kg CO2` had no time basis, so the
    classifier refused it; applied to a node carrying `kg CO2/s` it is man-hours per second, which is
    what the counter integrates. **247 became 245**, and seventeen of the twenty-one stock-adjacent
    edges now compute.
    """
    eclss = yaml.safe_load((VEHICLE / "domains" / "eclss" / "components.yaml").read_text())
    states = {str(s["id"]): s for s in eclss["state"]}
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    edges = {str(e["id"]): e for e in coupling["edges"]}
    nodes = coupling["nodes"]

    assert "co2_removal_kg_s" not in states, "the shared removal state is back"
    for state_id, node in (
        ("co2_removal_csm_kg_s", "co2_removal_csm"),
        ("co2_removal_lm_kg_s", "co2_removal_lm"),
    ):
        assert states[state_id]["node"] == node
        assert nodes[node]["kind"] == "flow" and nodes[node]["unit"] == "kg CO2/s"

    # Each removal spends its own counter, and each cabin loses CO2 to its own removal.
    assert (edges["E-ATM-ABSORB"]["from"], edges["E-ATM-ABSORB"]["to"]) == (
        "co2_removal_csm",
        "absorber_capacity_csm",
    )
    assert (edges["E-LM-ATM-ABSORB"]["from"], edges["E-LM-ATM-ABSORB"]["to"]) == (
        "co2_removal_lm",
        "absorber_capacity_lm",
    )
    assert edges["E-CABIN-CO2-REMOVAL"]["drains"] == "csm_cabin_co2_kg"
    assert edges["E-LM-CABIN-CO2-REMOVAL"]["drains"] == "lm_cabin_co2_kg"

    plant = _plant()
    world = plant.load_world(VEHICLE)
    for edge_id, driver, expected_unit in (
        ("E-ATM-ABSORB", "from", "man-hours per kg CO2"),
        ("E-CABIN-CO2-REMOVAL", "to", "kg CO2 per kg CO2"),
    ):
        edge = next(e for e in world.edges if e.id == edge_id)
        assert edge.sensitivity["unit"] == expected_unit, edge_id
        flux = plant.stock_flux(
            world,
            edge,
            {edge.source: 1.0, edge.target: 1.0},
            1.0,
            driver_node=edge.source if driver == "from" else edge.target,
        )
        assert flux > 0, edge_id


def test_the_battery_derating_is_a_capacity_not_a_flux():
    """A cold pack gives up less than it holds, and that belongs on a capacity rather than a charge.

    `E-PLATE-BAT` carried `0.0 J per K` from `coldplate_t` into `battery_energy` — a *capacity*
    relation landing on a quantity that is conserved, which the linter refused as a lag edge on a
    stock. `battery_usable_j` is the capacity node now, and the loop runs bus -> charge -> usable
    capacity -> bus: **the last step is what the bus actually draws on**, and without it `C-BAT-BUS`
    did not close and the linter said so.

    The nominal derating is 1.0 and the sensitivity is `0.0 J per K`, which the edge's own note
    already flagged as the review-findings.md #8 case: **a closure computed at nominal passes a
    fidelity decision that is wrong exactly when it matters.** In the crisis the pack is cold and the
    derating is not 1.0 — and no source publishes the curve, so it is `UNCONFIGURED` rather than
    invented.
    """
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    edges = {str(e["id"]): e for e in coupling["edges"]}
    nodes = coupling["nodes"]
    power = yaml.safe_load((VEHICLE / "domains" / "power" / "components.yaml").read_text())
    states = {str(s["id"]): s for s in power["state"]}

    assert nodes["battery_usable_j"]["kind"] == "flow"
    assert edges["E-PLATE-BAT"]["to"] == "battery_usable_j"
    assert edges["E-PLATE-BAT"]["advances"] == "battery_usable_j_j"
    assert edges["E-BAT-BUS"]["from"] == "battery_usable_j", (
        "the bus draws on usable energy, not on the raw charge"
    )
    assert states["battery_usable_j_j"]["derate_curve"] == "UNCONFIGURED"

    # The cycle it belongs to still closes, with the new step declared as a member.
    cycle = next(c for c in coupling["cycles"] if c["id"] == "C-BAT-BUS")
    assert "E-BAT-USABLE" in cycle["members"]

    result = run_linter(VEHICLE)
    assert result.returncode == 0, result.stdout[-900:]
    # And it is no longer a stock-flux debt: only the water clamp is left in that class.
    assert "against a stock denominated" not in result.stdout
    assert " is a 'lag' edge on a stock" not in result.stdout


def test_what_a_cabin_removes_is_what_its_crew_produce(tmp_path):
    """Three declarations in three files, joined for the first time.

    The crew count (`mission.yaml#crew`), the metabolic production rate
    (`vehicle.yaml#consumables.metabolic`), and the removal rate the ECLSS domain declares per
    compartment. The arithmetic is one line each — **rate = crew x kg_per_crew_day / 86400** — and
    it is the cabin equilibrium's three-way join applied to a different quantity.

    The two figures are deliberately *not* the same figure, which is the point of the round-63
    split: the CSM element removes what `size` crew produce and the LM cartridge what
    `surface_party` produce, so the LM's rate is two thirds of the CSM's on one metabolic constant.
    A single shared state could not have expressed either.
    """
    mission = yaml.safe_load((VEHICLE / "mission.yaml").read_text())
    vehicle = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
    eclss = yaml.safe_load((VEHICLE / "domains" / "eclss" / "components.yaml").read_text())
    states = {str(s["id"]): s for s in eclss["state"]}
    per_day = vehicle["consumables"]["metabolic"]["co2_kg_per_crew_day"]

    for state_id, key, expected in (
        ("co2_removal_csm_kg_s", "size", 3 * 0.91 / 86400),
        ("co2_removal_lm_kg_s", "surface_party", 2 * 0.91 / 86400),
    ):
        crew = mission["crew"][key]
        assert states[state_id]["nominal_kg_s"] == pytest.approx(crew * per_day / 86400, rel=1e-5)
        assert states[state_id]["nominal_kg_s"] == pytest.approx(expected, rel=1e-5)

    # Two thirds, on one metabolic constant — the relationship the split made visible.
    ratio = (
        states["co2_removal_lm_kg_s"]["nominal_kg_s"]
        / states["co2_removal_csm_kg_s"]["nominal_kg_s"]
    )
    assert ratio == pytest.approx(mission["crew"]["surface_party"] / mission["crew"]["size"])

    # Move the crew count and the domain's rate is refused rather than silently stale.
    definition = copy_definition(tmp_path / "crew")
    path = definition / "mission.yaml"
    text = path.read_text()
    anchor = "  surface_party: 2\n"
    assert anchor in text, "the fixture no longer matches mission.yaml#crew"
    path.write_text(text.replace(anchor, "  surface_party: 3\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "A cabin's equipment that removes a different amount" in result.stdout


def test_the_oxygen_supplies_are_checked_against_the_same_three_declarations(tmp_path):
    """The CO2 join's twin: the regulator replaces what the cabin loses, and both terms are published.

    Round 60 declared these two rates with their arithmetic and nothing checked them beyond
    re-deriving their own `computation`. They are held to the *other* files now — the crew count, the
    metabolic rate and the leak — which is the same three-way join the removal rates got in round 66,
    applied to the supply side.

    The leak is the interesting half. `vehicle.yaml#consumables.leak` was **one figure doing two
    cabins' work** while its own source named only one of them; it is per cabin now, and the CSM's is
    declared as borrowed (A11 gives one leak and it is the LM's, 0.05 lb/hr = 0.0226796 kg/h, while
    the CSM's own is published nowhere). A leak is a property of a seal rather than of a programme,
    and two cabins with one number between them read as though they had two.
    """
    mission = yaml.safe_load((VEHICLE / "mission.yaml").read_text())
    vehicle = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
    eclss = yaml.safe_load((VEHICLE / "domains" / "eclss" / "components.yaml").read_text())
    states = {str(s["id"]): s for s in eclss["state"]}
    leak = vehicle["consumables"]["leak"]
    o2 = vehicle["consumables"]["metabolic"]["o2_kg_per_crew_day"]

    assert leak["lm_kg_per_h"] == pytest.approx(0.05 * 0.453592, rel=1e-4)
    assert leak["csm_kg_per_h"] != leak["lm_kg_per_h"], "the two cabins have different seals"

    for state_id, crew_key, leak_per_h in (
        ("cabin_o2_supply_csm_kg_s", "size", leak["csm_kg_per_h"]),
        ("cabin_o2_supply_lm_kg_s", "surface_party", leak["lm_kg_per_h"]),
    ):
        crew = mission["crew"][crew_key]
        expected = (leak_per_h + crew * o2 / 24.0) / 3600.0
        assert states[state_id]["nominal_kg_s"] == pytest.approx(expected, rel=1e-5), state_id

    # A leak changed in `vehicle.yaml` is refused rather than silently absorbed.
    definition = copy_definition(tmp_path / "leak")
    path = definition / "vehicle.yaml"
    text = path.read_text()
    anchor = "    lm_kg_per_h: 0.0226796\n"
    assert anchor in text, "the fixture no longer matches the leak block"
    path.write_text(text.replace(anchor, "    lm_kg_per_h: 0.05\n", 1))

    result = run_linter(definition)
    assert result.returncode == 1
    assert "The regulator replaces what the cabin loses" in result.stdout


def test_a_channel_about_a_cabin_is_paired_or_explained(tmp_path):
    """A channel that is not paired with its twin is a *claim*, and until round 68 it was implicit.

    The vehicle has two crewed compartments, so a channel about a cabin's air is about one cabin:
    `eclss.cabin_temp_c` and `eclss.lm_cabin_temp_c` are one quantity in two rooms with no shared air
    between them. Most ECLSS channels are paired that way. **The CO2 exposure average was not** — a
    limit that governs how long a surface stay can be extended, published for the cabin the crew
    leave and none for the one they live in, and nothing could tell that from a channel that is
    legitimately single because its subject is.

    `presentation.yaml#single_cabin` names each unpaired channel with its reason, and the comparison
    is exact in both directions: an unpaired channel must be explained, and an explanation of a
    *paired* channel is stale — a reader told to expect a gap that has been closed.
    """
    registry = yaml.safe_load((VEHICLE / "channels.yaml").read_text())
    presentation = yaml.safe_load((VEHICLE / "presentation.yaml").read_text())
    published = {
        str(c["id"])
        for section in registry.values()
        if isinstance(section, list)
        for c in section
        if isinstance(c, dict) and "id" in c
    }
    eclss = {cid for cid in published if cid.startswith("eclss.")}
    paired = {
        cid for cid in eclss if ".lm_" not in cid and cid.replace("eclss.", "eclss.lm_", 1) in eclss
    }
    single = {cid for cid in eclss if ".lm_" not in cid and cid not in paired}

    assert single == set(presentation["single_cabin"]), "the declaration and the registry disagree"
    assert "eclss.co2_pp_1h_avg_mmhg" in paired, "the exposure average gained its twin in round 68"
    assert len(paired) == 6

    # An unpaired channel with no explanation is refused.
    definition = copy_definition(tmp_path / "unexplained")
    path = definition / "presentation.yaml"
    text = path.read_text()
    anchor = "  eclss.leak_rate_g_s: >-\n"
    assert anchor in text, "the fixture no longer matches single_cabin"
    stripped = re.sub(r"  eclss\.leak_rate_g_s: >-\n(?:    .*\n|\n)*", "", text, count=1)
    assert stripped != text
    path.write_text(stripped)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "does not explain" in result.stdout and "eclss.leak_rate_g_s" in result.stdout


def test_every_declared_gas_is_held_in_every_cabin(tmp_path):
    """The round-68 question one file over, and it found the same shape.

    The atmosphere model declares four gases — `o2`, `n2`, `co2`, `h2o` — and `cabin_atm` held four
    stock states while `lm_cabin_atm` held three. **There was no `lm_cabin_h2o_kg`**, and
    `lm_water_separator` sits in the same file to remove the vapour that had no state to be in: a
    component whose subject the model does not hold, which is the round-42 absorber finding arriving
    in the atmosphere.

    A cabin may legitimately lack a gas, so the rule is a declaration rather than a refusal — the
    pair goes in `atmosphere_model.absent` with its reason. Nothing is absent today, and the list is
    what keeps a future one from being silent.
    """
    eclss = yaml.safe_load((VEHICLE / "domains" / "eclss" / "components.yaml").read_text())
    gases = [str(g["id"]) for g in eclss["atmosphere_model"]["gases"]]
    assert gases == ["o2", "n2", "co2", "h2o"]

    for cabin in ("cabin_atm", "lm_cabin_atm"):
        held = {
            str(s["id"])
            for s in eclss["state"]
            if str(s.get("node")) == cabin and s.get("method") == "stock"
        }
        assert len(held) == 4, f"{cabin} holds {sorted(held)}"
        for gas in gases:
            assert any(gas in name for name in held), f"{cabin} has no state for {gas}"

    # And the LM's separator now has something to act on.
    components = {str(c["id"]) for c in eclss["components"]}
    assert "lm_water_separator" in components

    # Removing the state is refused rather than silently asymmetric.
    definition = copy_definition(tmp_path / "asymmetric")
    path = definition / "domains" / "eclss" / "components.yaml"
    text = path.read_text()
    stripped = re.sub(r"  - id: lm_cabin_h2o_kg\n(?:    .*\n|\n)*?(?=  - id: )", "", text, count=1)
    assert stripped != text, "the fixture no longer matches lm_cabin_h2o_kg"
    path.write_text(stripped)

    result = run_linter(definition)
    assert result.returncode == 1
    assert "names a species and no state to hold it" in result.stdout


def test_a_zone_temperature_is_on_a_node_or_declared(tmp_path):
    """Six zones carry a temperature state and five carry a *driver*, and the gap hid in the state's home.

    Two sat on the `internal` sentinel — which is not a node, so no edge can terminate on them, and
    `internal` has no inbound edge at all. The two crewed cabins were in exactly that position until
    round 55 gave them heat-rate nodes, and the radiator was in it until round 70 moved
    `zone_radiator_t` onto `radiator_reject`, where a node already existed and was already driven.

    Moving it was not free: `radiator_reject` then held two states, which the linter required an
    `advances` on `E-WATER-RAD` for, and a `state_order` — because rejection is
    `epsilon x sigma x A x T^4`, and the frozen lexicographic tiebreak sorts `radiator_rejection_w`
    *first*, computing the rejection from last tick's temperature. A one-tick error in a quantity
    that enters every thermal edge on the vehicle.
    """
    thermal = yaml.safe_load((VEHICLE / "domains" / "thermal" / "components.yaml").read_text())
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    states = {str(s["id"]): s for s in thermal["state"]}

    # Round 70 moved the radiator onto `radiator_reject` and back, because its only inbound edge
    # there was a back-edge. Round 71 gave the node a forward one — `E-ENV-RAD`, from the
    # environment — and round 72 took the last two zones, so the exemption list is empty and gone.
    assert states["zone_radiator_t"]["node"] == "radiator_reject"
    assert thermal.get("zones_not_on_nodes") in (None, {})
    node = coupling["nodes"]["radiator_reject"]
    assert node["state_order"] == ["zone_radiator_t", "radiator_rejection_w"]
    assert next(e for e in coupling["edges"] if e["id"] == "E-ENV-RAD")["kind"] == "algebraic"

    # A zone back on the sentinel with no explanation is refused.
    definition = copy_definition(tmp_path / "sentinel")
    path = definition / "domains" / "thermal" / "components.yaml"
    text = path.read_text()
    # The exemption list is gone, so the fixture now builds a *stale* one: a zone declared as having
    # no node while its state sits on one. That is the direction the round-70 check was missing.
    path.write_text(text.rstrip("\n") + '\nzones_not_on_nodes:\n  csm_service_bay: "stale"\n')

    result = run_linter(definition)
    assert result.returncode == 1
    # The stale direction, because the exemption list is empty now: the fixture adds an entry rather
    # than removing one.
    assert "stale exemption" in result.stdout


def test_every_thermal_zone_has_a_driver_and_the_exemption_list_is_empty(tmp_path):
    """Six zones, six nodes, six drivers — and the exemption list retired rather than left standing.

    Rounds 70 and 71 took the crewed cabins and the radiator; this round takes the two bays, whose
    heat rates were already summed (`heat_inputs` assigns 630 W to the service bay and 180 W to the
    descent stage) and whose states were on the `internal` sentinel. `service_bay_heat` and
    `descent_bay_heat` are nodes now, feeding `E-BAY-HEAT-CSM` and `E-BAY-HEAT-LM`.

    **What the edges do not carry is the conductance**, and that is declared rather than filled:
    `thermal_diode.md:965` calls every thermal constant UNSPECIFIED, so the scalar that turns watts
    into kelvin is owed and a plausible one would be exactly the invented typical-spacecraft number
    that document refuses. The zone is drivable and the missing scalar is named — which is strictly
    better than a zone that is neither.

    Chasing it also found a gap in the round-70 check: it refused a zone with no node and no
    explanation, but **not a stale explanation** — so the two bays' exemptions survived the round
    that closed them. It checks both directions now.
    """
    thermal = yaml.safe_load((VEHICLE / "domains" / "thermal" / "components.yaml").read_text())
    vehicle = yaml.safe_load((VEHICLE / "vehicle.yaml").read_text())
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    states = {str(s["id"]): s for s in thermal["state"]}

    # Every zone is on a node, so there is nothing left to exempt.
    assert thermal.get("zones_not_on_nodes") in (None, {}), (
        "the exemption list is stale: every zone has a node now"
    )
    assert states["zone_csm_service_t"]["node"] == "service_bay_zone_t"
    assert states["zone_lm_descent_t"]["node"] == "descent_bay_zone_t"
    assert states["service_bay_heat_w"]["total_w"] == 630
    assert states["descent_bay_heat_w"]["total_w"] == 180

    # And each zone's node has an inbound edge, which is the property all of this was for.
    driven = {str(e["to"]) for e in coupling["edges"]}
    for zone, state_id, node in (
        ("csm_cabin", "zone_csm_cabin_t", "cabin_zone_t"),
        ("csm_avionics_bay", "zone_csm_avionics_t", "coldplate_t"),
        ("csm_service_bay", "zone_csm_service_t", "service_bay_zone_t"),
        ("lm_cabin", "zone_lm_cabin_t", "lm_cabin_zone_t"),
        ("lm_descent_bay", "zone_lm_descent_t", "descent_bay_zone_t"),
        ("radiator_loop", "zone_radiator_t", "radiator_reject"),
    ):
        assert states[state_id]["node"] == node, zone
        assert node in driven, f"{zone}: {node} has no driver"
    assert len(vehicle["thermal"]["zones"]) == 6

    # A stale exemption is refused rather than tolerated.
    definition = copy_definition(tmp_path / "stale")
    path = definition / "domains" / "thermal" / "components.yaml"
    text = path.read_text()
    path.write_text(text.rstrip("\n") + '\nzones_not_on_nodes:\n  csm_service_bay: "stale"\n')

    result = run_linter(definition)
    assert result.returncode == 1
    assert "stale exemption" in result.stdout


def test_the_bay_conductances_owe_one_scalar_each_not_two(tmp_path):
    """`G = C/tau` with `tau` declared means the conductance and the mass are one obligation.

    The two bays' time constants are **chosen** where the cabin's is derived — the cabin's relation
    gives `C = 400 kg x 900 J/kg-K = 360,000 J/K` and `G = 125 W/K`, and `tau = C/G` follows. The
    bays have a tau and a qualitative reason ("the propellant is the mass and the tank wall is the
    path") and nothing else, so their edges carried `UNCONFIGURED` and the debt was vague.

    Naming *both* the mass and the conductance would be two debts for one unknown, since either
    determines the other given tau — so the states declare `lumped_mass_kg` alone and the edges'
    relations say how `1/G` follows from it. What is owed is one scalar per bay: the mass of the
    propellant and structure the reason already names. `thermal_diode.md:965`'s refusal to publish
    thermal constants is why it is owed rather than derived, and it is why a plausible number would
    be exactly the invented figure that document refuses.
    """
    thermal = yaml.safe_load((VEHICLE / "domains" / "thermal" / "components.yaml").read_text())
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    states = {str(s["id"]): s for s in thermal["state"]}
    edges = {str(e["id"]): e for e in coupling["edges"]}

    for state_id, edge_id, tau in (
        ("zone_csm_service_t", "E-BAY-HEAT-CSM", 7200),
        ("zone_lm_descent_t", "E-BAY-HEAT-LM", 10800),
    ):
        state = states[state_id]
        assert state["tau_s"] == tau
        assert state["lumped_mass_kg"] == "UNCONFIGURED"
        # One obligation, not two: the conductance follows from the mass and tau by division.
        assert "conductance_w_per_k" not in state, f"{state_id} declares the same unknown twice"
        assert edges[edge_id]["sensitivity"]["value"] == "UNCONFIGURED"
        assert "G = C/tau" in edges[edge_id]["sensitivity"]["relation"], edge_id

    # The cabin's, by contrast, is derived from both — which is what makes the pair the template.
    cabin = states["zone_csm_cabin_t"]
    assert cabin["conductance_w_per_k"] == 125
    assert cabin["tau_s"] == 2880
    assert "360,000 J/K" in cabin["provenance"]["relation"]


def test_a_threshold_with_no_limit_is_one_debt_not_two():
    """`assert` and `clear` are one missing limit, and the walk reported them as two.

    A comparator with no value has neither term: **twenty-six thresholds declared both
    `UNCONFIGURED`**, so the vehicle's headline count carried 26 obligations that were 13... rather,
    26 fields that were 26 halves of 26 limits — one number closes each pair. The count went from 249
    to 223 the moment the walk reported the pair once at the threshold.

    The number is the folder's headline claim, which is why a double-count in it matters more than a
    double-count anywhere else: it is the figure a reader uses to judge how much is left.
    """
    result = run_linter(VEHICLE)
    assert result.returncode == 0, result.stdout[-900:]
    owed = [
        line
        for line in result.stdout.splitlines()
        if line.strip().startswith("- domains/") and "UNCONFIGURED" in line
    ]
    paired = [line for line in owed if "one missing limit" in line]
    assert paired, "no threshold pair is reported — is the fixture still unconfigured?"
    # Every collapsed pair is reported once, at the `assert`, and never also at the `clear`.
    assert all(".assert" in line for line in paired), paired[:2]
    assert not any(line.rstrip().endswith(".clear: is UNCONFIGURED") for line in owed), (
        "a `clear` is still reported separately from its `assert`"
    )

    # And the count is the honest one, not the inflated one.
    assert "with 251 declared debt(s)" in result.stdout, result.stdout[-400:]


def test_a_note_that_only_points_at_another_entry_is_refused(tmp_path):
    """A bare `note: "as above"` is a claim whose content lives somewhere else.

    This folder's recurring finding is that **a declaration no tool reads has already drifted**, and
    a note is the one field nothing read at all — every other check looks at values. Two entries had
    drifted into a bare pointer: `recon_mismatch_o2` said only "as above" while its sibling carried
    the whole argument, and `release_allocation` said the same while `release_reservation` one entry
    above it had a sentence of its own. Neither is *wrong*, which is exactly why nothing caught them.

    The failure a bare pointer produces is positional. "Above" means whatever happens to precede it,
    so reordering a file silently repoints the note: the entry goes on looking sourced while its
    justification has moved to a different claim. It also costs the reader the sentence that says why
    this entry exists separately at all — and here `consumables_diode.md:852` refuses a universal
    tolerance *per resource*, so the two reconciliation limits are separate numbers even where the
    argument they rest on is shared.

    Four pointer notes survive in the live definition and every one of them keeps a clause, so the
    check refuses a pointer with nothing behind it rather than the pattern of its opening words.
    """
    # The clause is the whole reason the second entry exists rather than being merged into the first.
    for filename, snippet in (
        ("domains/consumables/components.yaml", "as above; the 8:1 O2:H2 mass ratio"),
        ("domains/consumables/profiles.yaml", "as above, at apollo's second propellant level"),
        ("domains/thermal/components.yaml", "as above, for the LM"),
        ("domains/thermal/profiles.yaml", "as above; 2 K wider than the CSM's upper limit"),
    ):
        assert snippet in (VEHICLE / filename).read_text(), f"{filename} lost its clause"
    result = run_linter(VEHICLE)
    assert result.returncode == 0, result.stdout[-900:]
    assert "pointer with nothing behind it" not in result.stdout

    # Break one, with a *different* pointer phrase than the two the corpus had drifted into.
    definition = copy_definition(tmp_path / "bare")
    path = definition / "domains" / "consumables" / "commands.yaml"
    text = path.read_text()
    broken = text.replace(
        'why: "the inverse of a declined verb is a declined verb"', 'why: "see above"', 1
    )
    assert broken != text, "the fixture no longer matches consumables/commands.yaml"
    path.write_text(broken)

    result = run_linter(definition)
    assert result.returncode == 1, result.stdout[-900:]
    assert "pointer with nothing behind it" in result.stdout, result.stdout[-900:]
    assert "commands.yaml:declined" in result.stdout, result.stdout[-900:]


def test_a_word_that_only_starts_like_a_pointer_is_not_one(tmp_path):
    """`as aboveboard` is one word, and the check has to know that before it may refuse anything.

    The first cut of the pattern had no word boundary, so it refused `as aboved` and `as aboveboard`
    — notes that never point anywhere. A check that refuses correct prose is worse than no check,
    because the only way to satisfy it is to rewrite a sentence that was already right.
    """
    definition = copy_definition(tmp_path / "prefix")
    path = definition / "domains" / "consumables" / "commands.yaml"
    text = path.read_text()
    broken = text.replace(
        'why: "the inverse of a declined verb is a declined verb"',
        'why: "as aboveboard, which is a single word, points at nothing and is not a pointer phrase"',
        1,
    )
    assert broken != text, "the fixture no longer matches consumables/commands.yaml"
    path.write_text(broken)

    result = run_linter(definition)
    assert result.returncode == 0, result.stdout[-900:]
    assert "pointer with nothing behind it" not in result.stdout


def test_the_two_reconciliation_tolerances_are_declared_alike():
    """Two thresholds on one channel template, and only one of them said what it measures.

    `res.recon_[resource]_kg` is a template, so `res.recon_main_propellant_kg` and `res.recon_o2_kg`
    resolve to the same registered channel with the same `unit: kg`. Both thresholds are `above` on
    `|observed - ledger|`, both are owed, both carry the same dwell — and one declared
    `point_units: "kg of |observed - ledger|"` while the other declared nothing.

    Nothing was broken by the omission: `point_units` is read as an *exemption* from the linter's
    unit-agreement check, and the O2 point agrees with its channel, so no exemption was needed. That
    is what made it invisible — the field is only ever read when it is already there, so its absence
    on one half of a matched pair cannot be detected by the check that reads it. The two entries are
    now declared alike, because a reader comparing them should not have to work out whether the
    difference is meaningful.
    """
    profiles = yaml.safe_load((VEHICLE / "domains" / "consumables" / "profiles.yaml").read_text())
    by_id = {str(t["id"]): t for t in profiles["thresholds"]}

    propellant = by_id["recon_mismatch_main_propellant"]
    oxygen = by_id["recon_mismatch_o2"]

    # The same point shape and the same comparison, which is what makes them a pair at all.
    assert propellant["point"].replace("main_propellant", "[resource]") == "res.recon_[resource]_kg"
    assert oxygen["point"].replace("o2", "[resource]") == "res.recon_[resource]_kg"
    for field in ("comparator", "assert", "clear", "dwell_assert_ms", "dwell_clear_s", "severity"):
        assert propellant[field] == oxygen[field], field

    # And the same statement of what the number is, which is the half that was missing.
    assert propellant["point_units"] == oxygen["point_units"] == "kg of |observed - ledger|"
    # Neither is a pointer at the other any more: both say why this resource is its own entry.
    for threshold in (propellant, oxygen):
        note = threshold["provenance"]["note"]
        assert "consumables_diode.md:852" in note
        assert "as above" not in note
    assert "separate entry" in propellant["provenance"]["note"]
    assert "separate entry" in oxygen["provenance"]["note"]


def test_the_debts_view_groups_by_what_each_one_wants():
    """The view that looks for round 74's class of inflation, and the answer for the prose half.

    Round 74 found twenty-six thresholds reporting `assert` and `clear` separately — one missing limit
    counted as two. `--debts` is how that is looked for now: it splits the owed list into literal
    `UNCONFIGURED` scalars and prose `open_debts`, groups the first by the field it wants and the
    second by the file that keeps it.

    **Run against the corpus the round after, the prose half is clean.** `coupling.yaml`'s nineteen
    per-edge debts and the seventeen edge ids named inside its eight `open_debts` sentences are
    *disjoint*, and the one subject named from two files — the inertia tensor, in `coupling.yaml` and
    `domains/rcs/` — is one missing datum with two genuinely different consequences, each recorded
    where it bites. That is the folder's style rather than a double-count, and it is worth being able
    to say so, because the count is the headline claim.
    """
    result = subprocess.run(
        [sys.executable, str(LINTER), "--dir", str(VEHICLE), "--debts"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "grouped by what each wants" in result.stdout
    assert "a literal `UNCONFIGURED` scalar" in result.stdout
    assert "a prose obligation in an `open_debts` list" in result.stdout
    assert "by the field it wants" in result.stdout
    assert "by the file that keeps it" in result.stdout

    owed = re.search(r"(\d+) owed, grouped", result.stdout).group(1)
    assert owed == "251", "the view must agree with the headline count"


def test_a_placeholder_inside_an_owed_entry_says_so(tmp_path):
    """`basis: UNCONFIGURED` is a *decision*, not an undecided one — and this round found nothing to settle.

    Round 75 called the 28 entries carrying it "open judgements" and proposed finishing them. They are
    correctly declared: `UNCONFIGURED` is the class for a value no source supplies, and the twenty-eight
    are owed values rather than undecided ones. That is the useful answer, and it corrects the premise.

    Two of them, though, carry a number the plant **uses** while the entry says its magnitudes are
    owed: `pressurant_pressure_psi.tau_s = 5`, integrated as a lag and the seed of PRP-03, and
    `pressurant_he_kg.quantum = 1.0e-05`, without which the fixed-point stock cannot exist. Read
    against `basis: UNCONFIGURED` those look contradictory until a reader finds the sentence that
    reconciles them — and a reader who does not cannot tell whether to use the number or ignore it.

    So an owed entry carrying a numeric *integrator parameter* must mark that parameter a placeholder:
    `tau_s`, `quantum`, `delay_s` and `lambda_per_h` are the four the plant reads, and whose absence
    stops a tick rather than merely leaving a quantity unset.
    """
    propulsion = yaml.safe_load(
        (VEHICLE / "domains" / "propulsion" / "components.yaml").read_text()
    )
    consumables = yaml.safe_load(
        (VEHICLE / "domains" / "consumables" / "components.yaml").read_text()
    )
    p_states = {str(s["id"]): s for s in propulsion["state"]}
    c_states = {str(s["id"]): s for s in consumables["state"]}

    assert p_states["pressurant_pressure_psi"]["provenance"]["basis"] == "UNCONFIGURED"
    assert "placeholder" in p_states["pressurant_pressure_psi"]["tau_s_placeholder"]
    assert c_states["pressurant_he_kg"]["provenance"]["basis"] == "UNCONFIGURED"
    assert (
        "picked because the helium feed is slow"
        in c_states["pressurant_he_kg"]["quantum_placeholder"]
    )

    definition = copy_definition(tmp_path / "unmarked")
    path = definition / "domains" / "propulsion" / "components.yaml"
    text = path.read_text()
    i = text.index("    tau_s_placeholder: >-")
    j = text.index("    provenance:", i)
    path.write_text(text[:i] + text[j:])

    result = run_linter(definition)
    assert result.returncode == 1
    assert "does not say it is a placeholder" in result.stdout


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
