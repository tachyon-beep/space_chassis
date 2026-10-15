"""The quiet-coast episode through the real executive (09-quiet-coast-episode.md §7 step 11).

Policy A goes in through agent_1's window, written by the operator's driver (scripts/episode_driver.py)
the way an agent would write it, and the episode is judged by the vehicle's evaluator on the vehicle's
own record: the executive's private state directory, which the vehicle service alone mounts
(`vehicle_state`, ADR 0002 H) and the operator reads from the host. No agent mounts it, and nothing
here reads a result file. The outcome record is written to the operator's evidence directory, outside
every agent's mounts.

**Not runnable yet, and marked so (strict xfail).** The window run has to start a fresh world at the
quiet-coast scenario's MET 0: its initial overrides (the hot hold's environment and radiator, the
recorder's D1 + D2) and its verb allow-list. `vehicle/tools/console.py` starts every world from the
declared vehicle; it has no scenario overlay. The interface this test assumes is
`VEHICLE_SCENARIO_FILE`, passed by `containers/serve_vehicle.sh` to the console, naming a scenario
under `/opt/vehicle/scenarios/`; until the vehicle has it, the evaluator refuses the record at its
first tick (the replay from the scenario's MET 0 disagrees with the record's hash) and the test fails
as expected. When it passes, remove the mark.

It runs on the vehicle's smoke stack (`vehicle_stack`, after live/test_vehicle.py, whose world it
replaces), needs Docker and the vehicle image, and runs 40 minutes of mission time at m = 1: about
45 minutes of wall time. It has not been run.
"""

import json
import shutil
import subprocess
import sys

import pytest
from stack import REPO, wait_for

sys.path.insert(0, str(REPO / "scripts"))
import episode_driver  # noqa: E402

VEHICLE = REPO.parent / "vehicle"
TOOL = VEHICLE / "tools" / "episode_eval.py"
SLUG = "agent_1"
SCENARIO_IN_IMAGE = "/opt/vehicle/scenarios/quiet_coast.yaml"
EVIDENCE = REPO / ".scratch" / "live-evidence" / "quiet_coast_a"
START_SECONDS = 180


def _emptied(directory) -> None:
    """Everything under a directory removed, the directory itself kept: an agent's container binds
    its window directory, and a bind of a removed directory is a bind of nothing."""
    for path in directory.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def _fresh_world(stack) -> None:
    """A new world from the scenario's MET 0: the executive stopped, its private state and the
    windows emptied (a fresh world refuses a directory another world prepared), and the service
    recreated with the scenario named."""
    stack.compose("stop", "vehicle")
    _emptied(stack.volumes / "vehicle_state" / "data")
    root = stack.volumes / "diode" / "data"
    for path in root.iterdir():
        if path.name in stack.slugs and path.is_dir():
            _emptied(path)
            (path / "output").mkdir()
        elif path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    stack.recreate("vehicle", {"VEHICLE_SCENARIO_FILE": SCENARIO_IN_IMAGE})


@pytest.mark.xfail(
    strict=True,
    reason="console.py cannot start a world from a scenario overlay yet (VEHICLE_SCENARIO_FILE)",
)
def test_policy_a_through_the_window_is_judged_full_success_on_the_vehicle_s_own_record(
    vehicle_stack,
):
    stack = vehicle_stack
    window = stack.volumes / "diode" / "data" / SLUG
    _fresh_world(stack)
    wait_for(
        lambda: episode_driver.mission_tick(window) is not None,
        timeout=START_SECONDS,
        every=1,
        what="the vehicle to publish agent_1's window from the new world",
    )
    emitted = subprocess.run(
        [sys.executable, str(TOOL), "--run", "quiet_coast", "--policy", "a", "--emit-policy"],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    policy = episode_driver.Policy.from_document(json.loads(emitted.stdout))
    driver = episode_driver.Driver(window, policy)
    wall = policy.duration_ticks / policy.tick_hz
    assert driver.run(poll_seconds=0.05, timeout=wall + 600), (driver.sent, driver.log[-3:])
    # The record of a stopped executive: a live journal's last line can be partial.
    stack.compose("stop", "vehicle")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "driver.json").write_text(json.dumps(driver.log, indent=2), encoding="utf-8")
    judged = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--run",
            "quiet_coast",
            "--policy",
            "a",
            "--from-record",
            str(stack.volumes / "vehicle_state" / "data"),
            "--out",
            str(EVIDENCE),
        ],
        capture_output=True,
        text=True,
        timeout=3600,
        check=False,
    )
    assert judged.returncode == 0, judged.stderr[-2000:]
    record = json.loads((EVIDENCE / "outcome.json").read_text())
    assert record["class"] == "full_success", (record["apparatus"], record["first_violation"])
    assert record["objective_results"]["secondary_met"]
