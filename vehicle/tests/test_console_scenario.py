"""The window executive takes a scenario file (`console.py --scenario-file`; 09-quiet-coast-episode.md §7).

The batch runner (`tools/episode_eval.py`) has driven the quiet-coast episode through `plant.run_scenario`
since step 8; D14's acceptance wants the policies driven through the window. So the executive takes the
same scenario file and does three things with it:

* **MET 0.** A new world's truth is `plant.initial_values(world, scenario)`, so the record of a window
  run replays from the scenario's MET 0 (`episode_eval.trace_from_record`) tick for tick.
* **The allow-list.** `Scenario.admit` is held in `Executive.validate`, which is both the acceptance check
  and the revalidation a deferral gets when it comes due: a verb outside the episode is refused with a
  result, never silently dropped, and never applied.
* **Identity.** The scenario's name and the SHA-256 of the file's bytes go into `identity.scenario_file`
  of every checkpoint. A restart that names a different file, or none, is refused (exit 3) and writes
  nothing; one that names the same file resumes. A world started without one is not given one later.

`--scenario` keeps its meaning (the fault posture); the overlay is a separate flag.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import checkpoint  # noqa: E402
import console  # noqa: E402
import episode_eval  # noqa: E402
import plant  # noqa: E402

CONSOLE = VEHICLE / "tools" / "console.py"
QUIET_COAST = VEHICLE / "scenarios" / "quiet_coast.yaml"
POLICY_A = VEHICLE / "scenarios" / "quiet_coast" / "policy_a.yaml"
CLOCK = ["--multiplier", "50", "--cycle-ticks", "5", "--checkpoint-ticks", "50", "--ring-slots", "10"]


@pytest.fixture(scope="module")
def world() -> plant.World:
    return plant.load_world(VEHICLE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def serve(tmp_path: Path, *extra: str, cycles: int = 2) -> subprocess.CompletedProcess:
    """The executive the way the stack starts it (`containers/serve_vehicle.sh`), for a few cycles."""
    (tmp_path / "diode").mkdir(exist_ok=True)
    return subprocess.run(
        [
            sys.executable, str(CONSOLE), "--dir", str(VEHICLE), "--diode-dir", str(tmp_path / "diode"),
            "--state-dir", str(tmp_path / "state"), "--slug", "alpha", *CLOCK, "--cycles", str(cycles), *extra,
        ],
        capture_output=True, text=True, timeout=600, check=False,
    )  # fmt: skip


def snapshot(*roots: Path) -> dict[str, bytes]:
    """Every file under the roots, by path, with its bytes: what a refusal must leave as it found."""
    return {
        str(path): path.read_bytes()
        for root in roots
        if root.exists()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def newest_checkpoint(world: plant.World, state: Path) -> dict:
    loaded = checkpoint.choose_generation(state, checkpoint.Compatibility.current(world))
    assert loaded is not None
    return loaded.body


def submit(window: Path, commands: list[str]) -> None:
    (window / "console.json").write_text(json.dumps({"commands": commands, "variables": {}}))


def results(window: Path) -> list[str]:
    return [path.read_text() for path in sorted((window / "output").glob("*.txt"))]


# -------------------------------------------------------------------------------------------------
# MET 0 and identity
# -------------------------------------------------------------------------------------------------


def test_a_new_world_started_from_a_scenario_file_starts_at_the_scenario_s_met_0(world, tmp_path):
    loaded = console.load_scenario_file(world, QUIET_COAST)
    executive = console.Executive(
        world, tmp_path / "diode", phase="translunar_coast", scenario_file=loaded
    )
    try:
        assert executive.truth == plant.initial_values(world, loaded.scenario)
        assert executive.truth != plant.initial_values(world)
        assert executive.truth["environment_heat_w"] == 2477.02
        assert executive.truth["recorder"] == 92_160_000
        assert executive.scenario_identity == {"name": "quiet_coast", "sha256": sha256(QUIET_COAST)}
        # `--scenario` keeps its meaning: the fault posture, unchanged by the overlay.
        assert executive.scenario == console.DEFAULT_SCENARIO
    finally:
        executive.close()


def test_the_served_world_records_its_scenario_and_its_record_replays_from_that_met_0(
    world, tmp_path
):
    ran = serve(tmp_path, "--scenario-file", str(QUIET_COAST), cycles=4)
    assert ran.returncode == 0, ran.stderr[-2000:]
    assert "scenario-file=quiet_coast:" in ran.stdout
    body = newest_checkpoint(world, tmp_path / "state")
    assert body["identity"]["scenario_file"] == {
        "name": "quiet_coast",
        "sha256": sha256(QUIET_COAST),
    }
    # The header is the identity's copy, so a reader of one line sees the scenario too.
    header = json.loads((tmp_path / "state" / "checkpoint.json").read_text().split("\n", 1)[0])
    assert header["scenario_file"] == body["identity"]["scenario_file"]
    # The posture is still the posture.
    assert body["run"]["scenario"] == "nominal"
    # The executive's own record, replayed from the scenario's MET 0, agrees on every tick's hash.
    episode = episode_eval.load_episode(QUIET_COAST, POLICY_A, world=world)
    trace = tmp_path / "trace.jsonl.gz"
    assert episode_eval.trace_from_record(episode, tmp_path / "state", trace, ticks=20) == 20
    header, rows = episode_eval.read_trace(trace)
    assert header["replay_mismatches"] == [] and [row["t"] for row in rows] == list(range(20))


def test_a_world_without_a_scenario_file_carries_no_scenario_identity(world, tmp_path):
    executive = console.Executive(world, tmp_path / "diode", phase="translunar_coast")
    try:
        body = checkpoint.capture_state(executive, checkpoint.Compatibility.current(world))
    finally:
        executive.close()
    assert "scenario_file" not in body["identity"]
    assert executive.truth == plant.initial_values(world)


@pytest.mark.parametrize(
    "value",
    [
        "quiet_coast",
        {"name": "quiet_coast"},
        {"name": "quiet_coast", "sha256": "not-a-digest"},
        {"name": 7, "sha256": "0" * 64},
        {"name": "quiet_coast", "sha256": "0" * 64, "extra": 1},
    ],
)
def test_a_checkpoint_whose_scenario_identity_is_not_a_name_and_a_digest_is_not_restored(
    world, tmp_path, value
):
    loaded = console.load_scenario_file(world, QUIET_COAST)
    executive = console.Executive(
        world, tmp_path / "diode", phase="translunar_coast", scenario_file=loaded
    )
    try:
        body = checkpoint.capture_state(executive, checkpoint.Compatibility.current(world))
    finally:
        executive.close()
    assert checkpoint._structure_problem(body) is None
    body["identity"]["scenario_file"] = value
    problem = checkpoint._structure_problem(body)
    assert problem is not None and problem[0] == "identity.scenario_file", problem


# -------------------------------------------------------------------------------------------------
# The allow-list, at acceptance and at settlement
# -------------------------------------------------------------------------------------------------


def test_a_verb_outside_the_scenario_is_refused_with_a_result_and_one_inside_is_taken(
    world, tmp_path
):
    loaded = console.load_scenario_file(world, QUIET_COAST)
    diode = tmp_path / "diode"
    executive = console.Executive(world, diode, phase="translunar_coast", scenario_file=loaded)
    try:
        executive.attach("alpha")
        window = diode / "alpha"
        submit(window, ["start_burn duration_s=1", "play_recorder state=on"])
        executive.cycle()
        texts = results(window)
    finally:
        executive.close()
    assert len(texts) == 2, texts
    refused = [text for text in texts if "state=refused" in text]
    taken = [text for text in texts if "state=accepted" in text]
    assert len(refused) == 1 and "NOT IN THIS SCENARIO" in refused[0], refused
    assert "scenario quiet_coast" in refused[0] and "'start_burn'" in refused[0]
    assert len(taken) == 1 and "recorder_play=on" in taken[0], taken


def test_a_scenario_s_window_advertises_only_the_verbs_it_admits(world, tmp_path):
    """The capability snapshot, `available_commands` and HELP.md name the scenario's verbs and no
    other: a verb the run refuses NOT IN THIS SCENARIO is not one to advertise. Without a scenario
    the whole registry is."""
    admitted = set(console.load_scenario_file(world, QUIET_COAST).scenario.verbs)
    texts = {}
    for name, loaded in (("scenario", console.load_scenario_file(world, QUIET_COAST)), ("whole", None)):
        diode = tmp_path / name
        executive = console.Executive(world, diode, phase="translunar_coast", scenario_file=loaded)
        try:
            view = executive.attach("alpha")
            executive.cycle()
            rows = view.capability()
            state = json.loads((diode / "alpha" / "state.json").read_text())
            texts[name] = (diode / "alpha" / "HELP.md").read_text()
        finally:
            executive.close()
        if loaded is not None:
            assert {row["verb"] for row in rows} == admitted
            assert set(state["available_commands"]) <= admitted
            assert "set_coolant_pump" in state["available_commands"]
        else:
            assert {row["verb"] for row in rows} > admitted
            assert "start_burn" in {row["verb"] for row in rows}
    assert "#### `set_coolant_pump`" in texts["scenario"] and "#### `start_burn`" not in texts["scenario"]
    assert "#### `start_burn`" in texts["whole"]
    for code in ("NOT IN THIS SCENARIO", "INTERLOCK TRIPPED", "INTERLOCK UNEVALUATED"):
        assert f"`{code}`" in texts["scenario"], code


def test_a_served_run_applies_only_admitted_verbs_to_its_record(world, tmp_path):
    """Through the real process and its record: the refused verb never reaches a row's effects."""
    diode, state = tmp_path / "diode", tmp_path / "state"
    ran = serve(tmp_path, "--scenario-file", str(QUIET_COAST), "--init")
    assert ran.returncode == 0, ran.stderr[-2000:]
    submit(diode / "alpha", ["start_burn duration_s=1", "set_comm_mode mode=sband_high"])
    ran = serve(tmp_path, "--scenario-file", str(QUIET_COAST), cycles=3)
    assert ran.returncode == 0, ran.stderr[-2000:]
    texts = results(diode / "alpha")
    assert any("NOT IN THIS SCENARIO" in text and "start_burn" in text for text in texts), texts
    applied = []
    with console.read_record(state) as record:
        for segment in console.concatenated(record.segments):
            for kind, row, _end in record.lines(segment):
                if kind == "row":
                    applied += [verb for _offset, verb, _arguments in row["effects"]]
    assert applied == ["set_comm_mode"], applied


def test_a_deferral_is_held_to_the_scenario_again_when_it_comes_due(world, tmp_path):
    """The allow-list is in `validate`, which is the settlement's revalidation too: a deferral accepted
    under a scenario that admitted it is refused at effect by one that does not. (A running world's
    scenario does not change; this swaps it in process to show the check is made at settlement.)"""
    admits = tmp_path / "admits.yaml"
    admits.write_text("scenario: admits\nverbs: [request_imu_alignment]\n")
    refuses = tmp_path / "refuses.yaml"
    refuses.write_text("scenario: refuses\nverbs: [set_comm_mode]\n")
    diode = tmp_path / "diode"
    executive = console.Executive(
        world,
        diode,
        phase="translunar_coast",
        scenario_file=console.load_scenario_file(world, admits),
    )
    try:
        executive.attach("alpha")
        window = diode / "alpha"
        submit(window, ["request_imu_alignment source=star target=LVLH"])
        executive.cycle()
        first = results(window)
        assert len(first) == 1 and "deferrable" in first[0], first
        executive.scenario_overlay = console.load_scenario_file(world, refuses).scenario
        executive.cycle()
        settled = [text for text in results(window) if text not in first]
    finally:
        executive.close()
    assert len(settled) == 1, settled
    assert "INHIBITED" in settled[0] and "NOT IN THIS SCENARIO" in settled[0], settled[0]


# -------------------------------------------------------------------------------------------------
# A file that is not a window run's scenario
# -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "words"),
    [
        (
            "scenario: s\nscript:\n  - {tick: 0, verb: set_comm_mode, arguments: {mode: vhf}}\n",
            "carries a `script`",
        ),
        ("scenario: s\nverbs: [no_such_verb]\n", "not a scenario this vehicle runs"),
        ("scenario: s\ninitial: {no_such_state: 1}\n", "not a scenario this vehicle runs"),
    ],
)
def test_a_file_that_is_not_a_window_run_s_scenario_is_refused_before_anything_is_written(
    tmp_path, text, words
):
    bad = tmp_path / "bad.yaml"
    bad.write_text(text)
    ran = serve(tmp_path, "--scenario-file", str(bad))
    assert ran.returncode == 3, ran.stdout + ran.stderr
    assert words in ran.stderr, ran.stderr
    assert not (tmp_path / "state").exists()
    assert list((tmp_path / "diode").iterdir()) == []


def test_a_missing_scenario_file_is_refused_by_name(tmp_path):
    ran = serve(tmp_path, "--scenario-file", str(tmp_path / "absent.yaml"))
    assert ran.returncode == 3 and "cannot be read" in ran.stderr, ran.stderr


# -------------------------------------------------------------------------------------------------
# Resume
# -------------------------------------------------------------------------------------------------


@pytest.fixture
def served(tmp_path) -> Path:
    """A world served from the quiet-coast scenario for two cycles, stopped cleanly."""
    ran = serve(tmp_path, "--scenario-file", str(QUIET_COAST))
    assert ran.returncode == 0, ran.stderr[-2000:]
    return tmp_path


def test_a_resume_naming_the_same_scenario_file_resumes_the_world(world, served):
    before = newest_checkpoint(world, served / "state")["identity"]
    ran = serve(served, "--scenario-file", str(QUIET_COAST))
    assert ran.returncode == 0, ran.stderr[-2000:]
    assert f"resumed world {before['world_id']} at tick {before['tick']}" in ran.stdout
    after = newest_checkpoint(world, served / "state")["identity"]
    assert after["world_id"] == before["world_id"] and after["tick"] == before["tick"] + 10
    assert after["scenario_file"] == before["scenario_file"]


def test_the_same_bytes_under_another_path_are_the_same_scenario(world, served):
    copy = served / "elsewhere.yaml"
    copy.write_bytes(QUIET_COAST.read_bytes())
    ran = serve(served, "--scenario-file", str(copy))
    assert ran.returncode == 0, ran.stderr[-2000:]


def test_a_resume_naming_a_different_scenario_file_is_refused_and_writes_nothing(world, served):
    other = served / "other.yaml"
    other.write_bytes(QUIET_COAST.read_bytes() + b"# one byte of difference is another world\n")
    before = snapshot(served / "state", served / "diode")
    ran = serve(served, "--scenario-file", str(other))
    assert ran.returncode == 3, ran.stdout + ran.stderr
    assert sha256(other) in ran.stderr and sha256(QUIET_COAST) in ran.stderr, ran.stderr
    assert "different file is a different world" in ran.stderr
    assert snapshot(served / "state", served / "diode") == before


def test_a_resume_naming_no_scenario_file_is_refused_and_writes_nothing(served):
    before = snapshot(served / "state", served / "diode")
    ran = serve(served)
    assert ran.returncode == 3, ran.stdout + ran.stderr
    assert "names no --scenario-file" in ran.stderr and "'quiet_coast'" in ran.stderr, ran.stderr
    assert snapshot(served / "state", served / "diode") == before


def test_a_world_started_without_a_scenario_is_not_given_one_on_restart(tmp_path):
    ran = serve(tmp_path)
    assert ran.returncode == 0, ran.stderr[-2000:]
    before = snapshot(tmp_path / "state", tmp_path / "diode")
    ran = serve(tmp_path, "--scenario-file", str(QUIET_COAST))
    assert ran.returncode == 3, ran.stdout + ran.stderr
    assert "never laid over a running one" in ran.stderr, ran.stderr
    assert snapshot(tmp_path / "state", tmp_path / "diode") == before


# -------------------------------------------------------------------------------------------------
# The evaluator holds the record to the episode
# -------------------------------------------------------------------------------------------------


def test_a_record_of_a_world_started_from_another_scenario_file_is_an_apparatus_failure(
    world, tmp_path
):
    other = tmp_path / "other.yaml"
    other.write_bytes(QUIET_COAST.read_bytes() + b"# another file\n")
    ran = serve(tmp_path, "--scenario-file", str(other))
    assert ran.returncode == 0, ran.stderr[-2000:]
    episode = episode_eval.load_episode(QUIET_COAST, POLICY_A, world=world)
    trace = tmp_path / "trace.jsonl.gz"
    assert episode_eval.trace_from_record(episode, tmp_path / "state", trace, ticks=10) == 0
    record = episode_eval.evaluate(trace, episode.spec, expected_ticks=10)
    assert record["class"] == "apparatus_failure"
    assert any("started from scenario" in line for line in record["apparatus"]), record


def test_a_record_that_applies_a_verb_the_episode_refuses_is_an_apparatus_failure(world, tmp_path):
    """A world served without the overlay applied `select_antenna`; an episode whose verbs refuse it
    judges the record an apparatus failure at that tick (09 §6: "a refused verb is applied")."""
    diode = tmp_path / "diode"
    ran = serve(tmp_path, "--init")
    assert ran.returncode == 0, ran.stderr[-2000:]
    submit(diode / "alpha", ["select_antenna antenna=omni_b"])
    ran = serve(tmp_path, cycles=3)
    assert ran.returncode == 0, ran.stderr[-2000:]
    assert any("state=accepted" in text for text in results(diode / "alpha"))
    plain = tmp_path / "plain.yaml"
    plain.write_text(
        QUIET_COAST.read_text()
        .split("\ninitial:", 1)[0]
        .replace("scenario: quiet_coast", "scenario: plain\nverbs: [set_comm_mode]")
        + "\n"
        + "episode:"
        + QUIET_COAST.read_text().split("\nepisode:", 1)[1]
    )
    policy = tmp_path / "policy_z.yaml"
    policy.write_text("policy: z\ncommands: []\n")
    episode = episode_eval.load_episode(plain, policy, world=world)
    trace = tmp_path / "trace.jsonl.gz"
    written = episode_eval.trace_from_record(episode, tmp_path / "state", trace, ticks=15)
    record = episode_eval.evaluate(trace, episode.spec, expected_ticks=15)
    assert record["class"] == "apparatus_failure"
    assert written < 15
    assert any("select_antenna" in line and "refuse" in line for line in record["apparatus"]), record
