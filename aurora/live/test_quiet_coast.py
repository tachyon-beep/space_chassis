"""The quiet-coast episode through the real executive (09-quiet-coast-episode.md §7 step 11).

Policy A goes in through agent_1's window, written by the operator's driver (scripts/episode_driver.py)
the way an agent would write it, and the episode is judged by the vehicle's evaluator on the vehicle's
own record: the executive's private state directory, which the vehicle service alone mounts
(`vehicle_state`, ADR 0002 H) and the operator reads from the host. No agent mounts it, and nothing
here reads a result file. The outcome record is written to the operator's evidence directory, outside
every agent's mounts.

**The scenario overlay exists** (`console.py --scenario-file`, passed as `VEHICLE_SCENARIO_FILE` by
`containers/serve_vehicle.sh` and declared in compose): the world starts at the quiet-coast scenario's
MET 0 and holds its verb allow-list, and the evaluator replays the record from that MET 0.
No xfail: the executive evaluates the interlocks of every verb policy A sends (vehicle ADR 0004),
with the ADR's three `chosen` operator items, which John decided on 2026-10-16; without them `set_power_amplifier` is
refused INTERLOCK UNEVALUATED and this fails. `tests/test_quiet_coast_window.py` shows the same run,
shortened and with a SIGKILL, without Docker.

It runs on the vehicle's smoke stack (`vehicle_stack`, after live/test_vehicle.py, whose world it
replaces), needs Docker and the vehicle image, and runs 40 minutes of mission time at m = 1: about
45 minutes of wall time. Its first run on a hosted runner (2026-10-16) drove the whole episode
and failed only on reading the 0600 record from the host, which the walk below answers.
"""

import json
import shutil
import subprocess
import sys

from stack import REPO, wait_for

sys.path.insert(0, str(REPO / "scripts"))
import episode_driver  # noqa: E402

VEHICLE = REPO.parent / "vehicle"
TOOL = VEHICLE / "tools" / "episode_eval.py"
SLUG = "agent_1"
SCENARIO_IN_IMAGE = "/opt/vehicle/scenarios/quiet_coast.yaml"
EVIDENCE = REPO / ".scratch" / "live-evidence" / "quiet_coast_a"
START_SECONDS = 180
# 50 s after policy A's recorder is empty; batch-judged `full_success` with the frozen scenario.
LATE_STAND_DOWN = 92500


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
    document = json.loads(emitted.stdout)
    # The stand-down moved from tick 90,000 to `LATE_STAND_DOWN`. The recorder holds exactly D1 + D2,
    # which policy A plays from tick 0 to 90,000; through the window the opening commands land some
    # ticks after MET 0 (the world is running before the driver first sees it), and a stand-down that
    # landed sooner after its own tick would leave the last kilobits unplayed: `partial` by a cycle's
    # timing, not by the policy. Later, the recorder runs dry first and the delivery is whole.
    for row in document["commands"]:
        if row["tick"] == 90000:
            row["tick"] = LATE_STAND_DOWN
    policy = episode_driver.Policy.from_document(document)
    driver = episode_driver.Driver(window, policy)
    wall = policy.duration_ticks / policy.tick_hz
    # The executive keeps the mission clock, not the wall's: on a loaded hosted runner the world ran
    # at about 0.6 of real time (2026-10-17: MET 1,850 s after 3,000 s of wall), so the driver gets
    # twice the episode's wall time, and the failure says how far the world got.
    deadline = 2 * wall
    assert driver.run(poll_seconds=0.05, timeout=deadline), (
        episode_driver.mission_tick(window),
        driver.sent,
        driver.log[-1:],
    )
    # The record of a stopped executive: a live journal's last line can be partial.
    stack.compose("stop", "vehicle")
    # The executive writes its journal 0600 as the image's uid 1000, and a 0600 create mode masks
    # the runner's default ACL entry, so the host cannot read the record. The vehicle's own user
    # opens what it wrote to the host, in a one-off container on the same mount: modes, not bytes,
    # and the evaluator verifies every line's hash. `/state` itself is the host's directory, which
    # that user does not own and the host can already read, so the walk starts below it.
    opened = stack.compose(
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--entrypoint",
        "find",
        "vehicle",
        "/state",
        "-mindepth",
        "1",
        "-user",
        "1000",
        "-exec",
        "chmod",
        "go+rX",
        "{}",
        "+",
        check=False,
    )
    assert opened.returncode == 0, (opened.stdout[-2000:], opened.stderr[-2000:])
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
        timeout=5400,
        check=False,
    )
    assert judged.returncode == 0, judged.stderr[-2000:]
    record = json.loads((EVIDENCE / "outcome.json").read_text())
    assert record["class"] == "full_success", (record["apparatus"], record["first_violation"])
    assert record["objective_results"]["secondary_met"]
