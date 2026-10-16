"""The quiet-coast episode (`09-quiet-coast-episode.md` §7 steps 8-10): the scenario, its four
policies, the evaluator and the restart check.

Two tiers:

* **always**: the frozen declaration held against the vehicle's own profiles; every policy loads
  inside the verb allow-list; a 3,000-tick smoke run of policy A judged `timeout` with every
  conservation verdict passing; the negative controls (missing ticks, a leaking stock, a gap on the
  path, a shed with no rule, a replay mismatch) judged `apparatus_failure`; the evaluator's
  independence from result files; and the restart check at smoke scale, in fresh processes.
* **opt-in, `QUIET_COAST_FULL=1`**: the four policies at 120,000 ticks, each asserting its class;
  policy D's trace relabelled as A still judged a physical loss; and the restart check at tick
  60,000. One 120,000-tick run is about 10 minutes of wall time on an idle core (more on a shared
  host), so CI runs this tier on its own: `QUIET_COAST_FULL=1 python3 -m pytest -q -n 4
  tests/test_quiet_coast.py`. Runs are shared between xdist workers through the session's base
  temporary directory, under a lock, so each policy runs once per session.
"""

from __future__ import annotations

import fcntl
import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import episode_eval  # noqa: E402
import plant  # noqa: E402

SCENARIO = VEHICLE / "scenarios" / "quiet_coast.yaml"
TOOL = VEHICLE / "tools" / "episode_eval.py"
SMOKE_TICKS = 3000
FULL = os.environ.get("QUIET_COAST_FULL") == "1"
_full_skip = pytest.mark.skipif(
    not FULL, reason="the 120,000-tick runs are opt-in: QUIET_COAST_FULL=1"
)


def full_only(test):
    """Opt-in tier: skipped locally without QUIET_COAST_FULL=1; in CI the referee deselects it by
    its marker (`-m "not quiet_coast_full"`) and the `quiet-coast episode` job runs it."""
    return pytest.mark.quiet_coast_full(_full_skip(test))


def spec() -> dict:
    return yaml.safe_load(SCENARIO.read_text())["episode"]


@pytest.fixture(scope="module")
def world() -> plant.World:
    return plant.load_world(VEHICLE)


def episode(world, policy: str) -> episode_eval.Episode:
    return episode_eval.load_episode(
        *episode_eval.scenario_paths("quiet_coast", policy), world=world
    )


# -------------------------------------------------------------------------------------------------
# The declaration
# -------------------------------------------------------------------------------------------------


def _profile(domain: str, threshold: str) -> dict:
    doc = yaml.safe_load((VEHICLE / "domains" / domain / "profiles.yaml").read_text())
    rows = [row for row in doc.get("thresholds") or [] if row.get("id") == threshold]
    assert len(rows) == 1, threshold
    return rows[0]


def test_the_frozen_thresholds_are_the_vehicle_s_own_and_09_s():
    declared = spec()
    thresholds = declared["thresholds"]
    for name, (domain, threshold) in {
        "coldplate": ("thermal", "avionics_plate_high"),
        "comm_amp": ("thermal", "comm_amp_high"),
        "coolant_supply": ("thermal", "coolant_supply_high"),
    }.items():
        row = _profile(domain, threshold)
        assert thresholds[name]["margin"]["below_c"] == row["assert"], name
        assert thresholds[name]["loss"]["above_c"] == row["assert"], name
        assert thresholds[name]["loss"]["dwell_s"] * 1000 == row["dwell_assert_ms"], name
    assert thresholds["bus_a_v"]["margin"] == {"at_least": 27.0}
    assert thresholds["bus_a_v"]["loss"] == {"below": 26.5}
    consumables = declared["consumables"]
    for sid, threshold in {
        "o2_csm_kg": "o2_reserve_20",
        "h2_csm_kg": "h2_reserve_20",
        "water_cooling_kg": "cooling_water_reserve",
    }.items():
        assert (
            consumables[sid]["at_end"]["at_least"]
            == _profile("consumables", threshold)["reserve_floor"]
        )


def test_d1_d2_and_w_min_are_frozen_with_their_basis():
    declared = spec()
    objective = declared["objective"]
    assert (objective["d1_bits"], objective["d2_bits"]) == (46_080_000, 46_080_000)
    assert (
        objective["basis"]["class"] == "chosen"
        and "ADR 0003 item 7" in objective["basis"]["relation"]
    )
    # 15 min of playback each at the configured rate; the two fit the 40-min contact with 600 s spare.
    assert objective["d1_bits"] == 900 * 51_200
    assert (
        (objective["d1_bits"] + objective["d2_bits"]) / 51_200
        == 1800
        <= declared["duration_ticks"] / 50
    )
    water = declared["consumables"]["water_cooling_kg"]
    assert water["at_end"]["at_least"] == 2.6 and water["basis"]["class"] == "derived"
    initial = yaml.safe_load(SCENARIO.read_text())["initial"]
    assert initial["recorder"] == objective["d1_bits"] + objective["d2_bits"]
    assert initial["environment_heat_w"] == 2477.02


@pytest.mark.parametrize("policy", "abcd")
def test_every_policy_loads_inside_the_episode_s_verbs(world, policy):
    loaded = episode(world, policy)
    assert loaded.policy_id == policy
    verbs = {effect.verb for effects in loaded.scenario.script.values() for effect in effects}
    assert verbs <= set(yaml.safe_load(SCENARIO.read_text())["verbs"])
    with pytest.raises(plant.EffectRefused):
        loaded.scenario.admit("start_burn")


def test_the_driver_s_policy_document_spells_each_command_as_a_console_line():
    document = episode_eval.policy_document(*episode_eval.scenario_paths("quiet_coast", "b"))
    assert document["tick_hz"] == 50 and document["duration_ticks"] == 120_000
    assert document["commands"][0] == {"tick": 0, "line": "set_load load=csm_lighting state=off"}
    assert {"tick": 63000, "line": "play_recorder state=on"} in document["commands"]


# -------------------------------------------------------------------------------------------------
# The smoke run, the controls and the restart check at smoke scale
# -------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def smoke(world, tmp_path_factory) -> Path:
    trace = tmp_path_factory.mktemp("smoke") / "trace.jsonl.gz"
    episode_eval.run_episode(episode(world, "a"), trace, ticks=SMOKE_TICKS)
    return trace


def judge(trace: Path) -> dict:
    return episode_eval.evaluate(trace, spec(), expected_ticks=SMOKE_TICKS)


def test_the_smoke_run_is_judged_on_its_own_trace_and_every_stock_conserves(smoke):
    record = judge(smoke)
    assert record["class"] == "timeout", record["apparatus"]
    assert record["apparatus"] == []
    results = record["objective_results"]
    # The link carries from the tick after the commands: 2,999 delivering ticks of 1,024 bits.
    assert results["delivered_bits_at_deadline"] == 2999 * 1024
    assert not results["mandatory_met"]
    conservation = record["conservation"]
    for stock in ("o2", "h2", "cooling_water", "data"):
        assert conservation[stock]["verdict"] == "pass", (stock, conservation[stock])
    assert conservation["o2"]["out"] > 0 and conservation["cooling_water"]["out"] > 0
    assert conservation["electrical_energy_trend"]["battery_charge_j"]["held"]
    assert record["ticks"] == {"start": 0, "expected": SMOKE_TICKS, "rows": SMOKE_TICKS}
    assert record["scenario_sha"] == episode_eval.sha256_file(SCENARIO)
    assert set(record) >= {
        "vehicle_sha",
        "policy_sha",
        "trace_hash",
        "margins_min",
        "first_violation",
    }
    assert record["margins_min"]["coolant_supply"]["margin"] > 0


def test_a_shed_by_command_is_not_mistaken_for_a_shed_with_no_rule(world, tmp_path):
    """Policy B's `set_load` writes `load_enabled`, which shares its node with `load_shed_class`.
    The trace reads each state by its own key, so the switch map is not read as the ladder's
    class and the smoke run is a clean `timeout`, with the shed loads off in the trace."""
    trace = tmp_path / "trace.jsonl.gz"
    episode_eval.run_episode(episode(world, "b"), trace, ticks=SMOKE_TICKS)
    record = judge(trace)
    assert record["class"] == "timeout", record["apparatus"]
    _, rows = episode_eval.read_trace(trace)
    switches = rows[0]["s"]["load_enabled"]
    assert switches["csm_lighting"] == switches["csm_comm_heaters"] == "off"
    assert all(row["s"].get("load_shed_class") is None for row in rows)


def doctored(smoke: Path, tmp_path: Path, edit) -> Path:
    with gzip.open(smoke, "rt") as handle:
        lines = [json.loads(line) for line in handle]
    lines = edit(lines)
    out = tmp_path / "doctored.jsonl.gz"
    with gzip.open(out, "wt") as handle:
        for line in lines:
            handle.write(json.dumps(line) + "\n")
    return out


def _rows(lines):
    return [line for line in lines if "t" in line]


def test_a_trace_with_missing_ticks_is_an_apparatus_failure(smoke, tmp_path):
    trace = doctored(
        smoke, tmp_path, lambda lines: [ln for ln in lines if ln.get("t") not in (1000, 1001)]
    )
    record = judge(trace)
    assert record["class"] == "apparatus_failure"
    assert any("2 missing" in line for line in record["apparatus"]), record["apparatus"]


def test_a_trace_without_its_met0_states_is_an_apparatus_failure(smoke, tmp_path):
    """Row 0 is the state after tick 0, so a loss chain needs MET 0 to see a tick-0 command move."""
    with gzip.open(smoke, "rt") as handle:
        header = json.loads(handle.readline())
    assert sorted(header["met0"]) == sorted(header["states"])

    def drop(lines):
        del lines[0]["met0"]
        return lines

    record = judge(doctored(smoke, tmp_path, drop))
    assert record["class"] == "apparatus_failure"
    assert any("MET-0" in line for line in record["apparatus"]), record["apparatus"]


def test_a_missing_trace_is_an_apparatus_failure(tmp_path):
    assert judge(tmp_path / "nothing.jsonl.gz")["class"] == "apparatus_failure"


def test_a_stock_that_leaks_is_an_apparatus_failure(smoke, tmp_path):
    def leak(lines):
        # One tick's cooling water loses ten quanta that no transfer explains.
        row = _rows(lines)[1500]
        before, after = row["L"]["water_cooling_kg"]
        row["L"]["water_cooling_kg"] = [before, after - 10]
        return lines

    record = judge(doctored(smoke, tmp_path, leak))
    assert record["class"] == "apparatus_failure"
    assert record["conservation"]["cooling_water"]["verdict"] == "fail"
    assert record["conservation"]["cooling_water"]["first_failure"]["tick"] == 1500


def test_an_edited_level_is_an_apparatus_failure(smoke, tmp_path):
    def edit(lines):
        _rows(lines)[2000]["s"]["water_cooling_kg"] = 12.5
        return lines

    record = judge(doctored(smoke, tmp_path, edit))
    assert record["class"] == "apparatus_failure"
    assert any("water_cooling_kg" in line for line in record["apparatus"])


def test_a_gap_on_the_path_and_a_shed_with_no_rule_are_apparatus_failures(smoke, tmp_path):
    def gap(lines):
        _rows(lines)[10]["g"] = ["bus_a_v"]
        return lines

    def shed(lines):
        _rows(lines)[20]["s"]["load_shed_class"] = "P3"
        return lines

    for edit, words in ((gap, "bus_a_v could not advance"), (shed, "a shed or trip with no rule")):
        record = judge(doctored(smoke, tmp_path, edit))
        assert record["class"] == "apparatus_failure"
        assert any(words in line for line in record["apparatus"]), record["apparatus"]


def test_a_record_replay_that_disagrees_is_an_apparatus_failure(smoke, tmp_path):
    def mismatch(lines):
        return [*lines, {"replay_mismatch": 7, "why": "fixture"}]

    record = judge(doctored(smoke, tmp_path, mismatch))
    assert record["class"] == "apparatus_failure"


def test_the_evaluator_reads_no_result_file(smoke, tmp_path):
    """09 §6: receipts are never evidence. A run directory full of forged results claiming delivery
    judges the same as one with none, and deleting them changes nothing."""
    run = tmp_path / "run"
    (run / "output").mkdir(parents=True)
    trace = run / "trace.jsonl.gz"
    trace.write_bytes(smoke.read_bytes())
    for name in ("20261015T000000_000000Z_agent_1_play_recorder.txt", "pending.json", "state.json"):
        (run / "output" / name).write_text(
            "delivered_bits = 92160000; secondary met; full_success\n"
        )
    (run / "console.json").write_text(json.dumps({"commands": ["play_recorder state=on"]}))
    with_files = judge(trace)
    for path in sorted(run.rglob("*")):
        if path.is_file() and path != trace:
            path.unlink()
    assert judge(trace) == with_files
    assert with_files["class"] == "timeout"


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), "--run", "quiet_coast", *args],
        capture_output=True,
        text=True,
        timeout=3600,
        check=False,
    )


def _hashes(trace: Path) -> list[tuple[int, str]]:
    _, rows = episode_eval.read_trace(trace)
    return [(row["t"], row["h"]) for row in rows]


def restart_check(policy: str, ticks: int, stop_at: int, whole, tmp_path: Path) -> None:
    """Stop at `stop_at`, checkpoint with the vehicle's checkpoint tool, resume in a fresh process,
    and hold the per-tick hash sequence and the outcome record to the uninterrupted run's.

    `whole` is the uninterrupted run's trace, or a callable that returns it, called after the split
    run so the two can run side by side."""
    run = tmp_path / "split"
    state = tmp_path / "state"
    tick_args = ["--ticks", str(ticks)] if ticks != spec()["duration_ticks"] else []
    first = _cli(
        "--policy",
        policy,
        *tick_args,
        "--stop-at",
        str(stop_at),
        "--state-dir",
        str(state),
        "--out",
        str(run),
    )
    assert first.returncode == 0, first.stderr[-2000:]
    assert (state / "checkpoint.json").exists()
    second = _cli("--policy", policy, *tick_args, "--resume", str(state), "--out", str(run))
    assert second.returncode == 0, second.stderr[-2000:]
    split = run / "trace.jsonl.gz"
    if callable(whole):
        whole = whole()
    assert _hashes(split) == _hashes(whole)
    expected = ticks if tick_args else None
    split_record = episode_eval.evaluate(split, spec(), expected_ticks=expected)
    whole_record = episode_eval.evaluate(whole, spec(), expected_ticks=expected)
    assert split_record == whole_record
    assert split_record["class"] != "apparatus_failure", split_record["apparatus"]


def test_a_run_restarted_from_a_checkpoint_in_a_fresh_process_is_the_same_run_smoke(
    smoke, tmp_path
):
    restart_check("a", SMOKE_TICKS, SMOKE_TICKS // 2, smoke, tmp_path)


def test_a_window_run_s_record_replays_into_the_same_trace_and_a_foreign_start_is_refused(
    world, tmp_path
):
    """The window run's trace comes from the executive's private record (`--from-record`): replayed
    from the scenario's MET 0, every tick's hash held to the record's. A real executive runs 100 ticks;
    a scenario that starts where it started (the declared vehicle) replays all of them, and the
    quiet-coast scenario, whose MET 0 the executive did not start from, is refused at its first tick."""
    diode, state = tmp_path / "diode", tmp_path / "state"
    diode.mkdir()
    ran = subprocess.run(
        [
            sys.executable, str(VEHICLE / "tools" / "console.py"), "--diode-dir", str(diode),
            "--state-dir", str(state), "--slug", "alpha", "--multiplier", "50", "--cycle-ticks", "5",
            "--checkpoint-ticks", "50", "--cycles", "20", "--scenario", "nominal", "--seed", "0",
            "--ring-slots", "10",
        ],
        capture_output=True, text=True, timeout=600, check=False,
    )  # fmt: skip
    assert ran.returncode == 0, ran.stderr[-2000:]
    plain_doc = yaml.safe_load(SCENARIO.read_text())
    plain_doc["initial"] = {}
    plain = tmp_path / "plain.yaml"
    plain.write_text(yaml.safe_dump(plain_doc))
    policy = tmp_path / "policy_z.yaml"
    policy.write_text("policy: z\ncommands: []\n")
    replayed = episode_eval.load_episode(plain, policy, world=world)
    assert (
        episode_eval.trace_from_record(replayed, state, tmp_path / "plain.jsonl.gz", ticks=100)
        == 100
    )
    header, rows = episode_eval.read_trace(tmp_path / "plain.jsonl.gz")
    assert header["replay_mismatches"] == [] and [row["t"] for row in rows] == list(range(100))
    foreign = tmp_path / "qc.jsonl.gz"
    assert episode_eval.trace_from_record(episode(world, "a"), state, foreign, ticks=100) == 0
    record = episode_eval.evaluate(foreign, spec(), expected_ticks=100)
    assert record["class"] == "apparatus_failure"
    assert any("record replay stopped at its tick 1" in line for line in record["apparatus"])


# -------------------------------------------------------------------------------------------------
# The full episode: opt-in
# -------------------------------------------------------------------------------------------------

EXPECTED = {"a": "full_success", "b": "full_success", "c": "partial", "d": "physical_loss"}


def full_run(policy: str, tmp_path_factory) -> tuple[Path, dict]:
    """One 120,000-tick run per policy per session, shared by every xdist worker under a lock."""
    root = tmp_path_factory.getbasetemp().parent / "quiet_coast_full"
    root.mkdir(exist_ok=True)
    run = root / policy
    with open(root / f"{policy}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not (run / "outcome.json").exists():
            done = _cli("--policy", policy, "--out", str(run))
            assert done.returncode == 0, done.stderr[-2000:]
            (run / "stdout.txt").write_text(done.stdout)
    return run / "trace.jsonl.gz", json.loads((run / "outcome.json").read_text())


@full_only
@pytest.mark.parametrize("policy", "abcd")
def test_each_policy_reaches_its_class_over_the_whole_episode(policy, tmp_path_factory):
    _, record = full_run(policy, tmp_path_factory)
    assert record["class"] == EXPECTED[policy], (record["apparatus"], record["first_violation"])
    for stock in ("o2", "h2", "cooling_water", "data"):
        assert record["conservation"][stock]["verdict"] == "pass", stock
    results = record["objective_results"]
    d1, d2 = results["d1_bits"], results["d2_bits"]
    if policy in "ab":
        assert results["secondary_met"] and not record["margin_violations"]
        # The policies stop the playback on the tick the record runs out, not after it.
        assert results["delivered_bits_at_deadline"] == d1 + d2
    if policy == "c":
        assert results["mandatory_met"] and not results["secondary_met"]
        assert results["delivered_bits_at_deadline"] == d1
    if policy == "d":
        first = record["first_violation"]
        assert first["state"] == "coolant_loop_t"
        # The per-tick chain explains it: the pump stopped, the flow fell, then the supply rose.
        moved = {link["state"]: link["first_moved_tick"] for link in first["chain"]}
        assert (
            moved["coolant_pump"]
            <= moved["coolant_flow_kg_s"]
            <= moved["coolant_loop_t"]
            <= first["tick"]
        )


@full_only
def test_a_and_b_succeed_by_distinct_trajectories(tmp_path_factory):
    a = full_run("a", tmp_path_factory)[1]
    b = full_run("b", tmp_path_factory)[1]
    assert a["trace_hash"] != b["trace_hash"]
    # A finishes first; B sheds and finishes later having spent less cooling water.
    assert a["objective_results"]["secondary_tick"] < b["objective_results"]["secondary_tick"]
    assert a["conservation"]["cooling_water"]["out"] > b["conservation"]["cooling_water"]["out"]


@full_only
def test_policy_d_s_trace_relabelled_as_a_is_still_a_physical_loss(tmp_path_factory, tmp_path):
    trace, _ = full_run("d", tmp_path_factory)

    def relabel(lines):
        lines[0]["policy"] = "a"
        return lines

    record = episode_eval.evaluate(doctored(trace, tmp_path, relabel), spec())
    assert record["policy_id"] == "a" and record["class"] == "physical_loss"


@full_only
def test_policy_a_restarted_at_tick_60000_in_a_fresh_process_is_the_same_run(
    tmp_path_factory, tmp_path
):
    restart_check(
        "a",
        spec()["duration_ticks"],
        60_000,
        lambda: full_run("a", tmp_path_factory)[0],
        tmp_path,
    )
