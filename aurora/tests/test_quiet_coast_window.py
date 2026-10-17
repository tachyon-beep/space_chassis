"""The quiet-coast episode through the real window executive, without Docker (09-quiet-coast-episode.md §7 step 11).

D14 wants the policies driven through the window, not only in batch. This is that run with everything
but the containers: the executive (`vehicle/tools/console.py`) started as a process the way
`containers/serve_vehicle.sh` starts it -- the clock, the ring, the posture and seed, a private state
directory -- plus `--scenario-file`, which starts the world at the scenario's MET 0 and holds its verb
allow-list (`VEHICLE_SCENARIO_FILE` in the stack). Each policy goes in through the window's one uplink,
written by the operator's driver (`scripts/episode_driver.py`) exactly as an agent would write it; the
episode is judged by the vehicle's evaluator (`episode_eval.py --from-record`) on the executive's own
private record, never on a result file.

**The shortened episodes** (always): the same scenario with its task shrunk to fit a few thousand
ticks -- D1 = D2 = 1,000 ticks of playback at the configured 1,024 bits a tick, the recorder loaded with
D1 + D2, a 3,000-tick contact -- and policies A, B and C with their command ticks moved into it
(`SHORT_TICK`). A command lands at the cycle that takes it, a few ticks after the policy's tick, so the
windows are sized to leave that slack. Each run is SIGKILLed at tick 1,000 (after the opening commands
are taken, before any later one is due), restarted on the same state directory with the same scenario
file, and driven on to the end. The evaluator replays the whole record from the scenario's MET 0 and
holds every tick's state hash to the record's, so a resumed run that did not continue the killed one
bit for bit is an apparatus failure; the test also holds the record to two boots, every conservation
verdict to pass and every command to an accepted result, and replays A's record a second time to the
same trace hash. A and B are `full_success` and C `partial`, their batch classes.

**Interlocks (vehicle ADR 0004).** The executive evaluates a declared interlock whose chain reads
(threshold, band, dwell, reading), with the dwell count in the hashed truth, and refuses INTERLOCK
UNEVALUATED a verb any of whose interlocks does not read; the batch run never meets that gate. The
policies' verbs read only with the ADR's three operator items, which are `chosen` and John decided on 2026-10-16:
`power.load_margin_w` as bus A's rated generation less its load, a 108 W ceiling for `tx_power_high`,
and `set_load` without `lcl_overcurrent`. Without them `set_power_amplifier` and `set_load` are refused
and these classes fail, which is the test saying so. Policy D (the pump stopped at MET 0) is run to its
physical loss of the coolant loop, killed at tick 4,000 while the coolant-supply interlock's dwell count
is accumulating. Each run is made once per session and shared.

**The full episode** (`QUIET_COAST_FULL=1`): the frozen scenario and policy A as they are, 120,000
ticks; at the default m = 2 that is 1,000 s of wall time if the host keeps up.

The clock: m is the executive's own bound on wall time per mission second (ADR 0002 A); one cycle,
k ticks at 50 Hz over m, must be 1 ms to 60 s, so any m up to 250 at k = 5 is legal. What bounds this
run is the host: a tick costs about 7 ms on an idle core, so m = 2 (10 ms a tick) keeps up and m = 1
is safe on a loaded one. A cycle that falls 30 s behind ends the boot with the lag backstop (exit 4,
the clean end), and the stack's restart policy resumes it; this harness does the same.
`QUIET_COAST_WINDOW_M` overrides m.
"""

from __future__ import annotations

import dataclasses
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from fractions import Fraction
from pathlib import Path

import episode_driver
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
VEHICLE = REPO / "vehicle"
CONSOLE = VEHICLE / "tools" / "console.py"
EVAL = VEHICLE / "tools" / "episode_eval.py"
SCENARIO = VEHICLE / "scenarios" / "quiet_coast.yaml"
POLICIES = VEHICLE / "scenarios" / "quiet_coast"
POLICY_A = POLICIES / "policy_a.yaml"
SLUG = "agent_1"
M = os.environ.get("QUIET_COAST_WINDOW_M", "2")
FULL = os.environ.get("QUIET_COAST_FULL") == "1"
# The shortened episode: 1,000 ticks of playback each for D1 and D2, a 3,000-tick contact.
SHORT_TICKS = 3000
SHORT_D = 1000 * 1024
# Each policy's own command ticks, moved into the shortened contact. A's stand-down goes to 2,500, late
# on purpose (the recorder runs dry at 2,000 ticks of playback, so a late landing costs nothing). C
# keeps its shape at 1/40 of the contact, playing 0-1,125 only (more than D1, less than D1 + D2). B plays
# 0-1,050 and 1,650-2,700 (2,100 ticks, more than D1 + D2): its cool-down is 600 ticks, not 1/40 of its
# 18,000, because the amplifier's `transmitter_on` must hold a value 10 s (500 ticks) before it changes
# (`domains/comms/components.yaml`, min_off_s), and a 450-tick gap is refused DWELL.
SHORT_TICK = {
    "a": {0: 0, 90000: 2500},
    "b": {0: 0, 45000: 1050, 63000: 1650, 108000: 2700},
    "c": {0: 0, 45000: 1125},
}
# The full episode's stand-down for policy A through the window: 50 s after the recorder is empty
# (`aurora/live/test_quiet_coast.py` uses the same tick, and says why there).
LATE_STAND_DOWN = 92500
# Where each shortened run is SIGKILLed: after the opening commands are taken, before any later one is due.
SHORT_KILL = 1000
# The executive's exit for the lag backstop: a clean end the stack's restart policy resumes.
EXIT_BACKSTOP = 4


def shortened(policy_id: str):
    """The scenario with its task shrunk, and one policy with its command ticks moved into the shortened
    contact (`SHORT_TICK`): every other line as is."""

    def make(tmp_path: Path) -> tuple[Path, Path]:
        doc = yaml.safe_load(SCENARIO.read_text())
        doc["initial"]["recorder"] = 2 * SHORT_D
        episode = doc["episode"]
        episode["duration_ticks"] = SHORT_TICKS
        episode["objective"].update(deadline_tick=SHORT_TICKS, d1_bits=SHORT_D, d2_bits=SHORT_D)
        scenario = tmp_path / "quiet_coast_short.yaml"
        scenario.write_text(yaml.safe_dump(doc, sort_keys=False))
        moves = SHORT_TICK[policy_id]
        policy = yaml.safe_load((POLICIES / f"policy_{policy_id}.yaml").read_text())
        assert {row["tick"] for row in policy["commands"]} == set(moves), policy["commands"]
        for row in policy["commands"]:
            row["tick"] = moves[row["tick"]]
        policy_path = tmp_path / f"policy_{policy_id}_short.yaml"
        policy_path.write_text(yaml.safe_dump(policy, sort_keys=False))
        return scenario, policy_path

    return make


def evaluator(*args: str, timeout: float = 3 * 3600) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EVAL), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


class Executive:
    """The window executive as a supervised process: restarted after a SIGKILL or a lag backstop,
    as the stack's `restart: unless-stopped` would, with the same flags every time."""

    def __init__(self, tmp_path: Path, scenario: Path) -> None:
        self.diode = tmp_path / "diode"
        self.state = tmp_path / "state"
        self.log = tmp_path / "executive.log"
        (self.diode / SLUG).mkdir(parents=True)
        self.argv = [
            sys.executable, str(CONSOLE), "--dir", str(VEHICLE), "--diode-dir", str(self.diode),
            "--state-dir", str(self.state), "--slug", SLUG, "--scenario", "nominal", "--seed", "0",
            "--ring-slots", "100", "--multiplier", M, "--cycle-ticks", "5", "--checkpoint-ticks", "50",
            "--cycles", "0", "--scenario-file", str(scenario),
        ]  # fmt: skip
        self.process: subprocess.Popen | None = None
        self.boots = 0
        self.exits: list[int] = []
        self.stopping = False
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._supervise, daemon=True)

    def start(self) -> None:
        self._spawn()
        self.thread.start()

    def _spawn(self) -> None:
        with open(self.log, "a") as log:
            self.process = subprocess.Popen(self.argv, stdout=log, stderr=subprocess.STDOUT)
        self.boots += 1

    def _supervise(self) -> None:
        while True:
            process = self.process
            assert process is not None
            code = process.wait()
            with self.lock:
                self.exits.append(code)
                if self.stopping:
                    return
                if code not in (-signal.SIGKILL, EXIT_BACKSTOP):
                    return  # a refusal or a fault: the test reads it from `exits` and the log
                self._spawn()

    def kill(self) -> None:
        assert self.process is not None
        self.process.send_signal(signal.SIGKILL)

    def stop(self) -> int:
        with self.lock:
            self.stopping = True
            process = self.process
        assert process is not None
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=120)
        finally:
            if process.poll() is None:
                process.kill()
        self.thread.join(timeout=10)
        return process.returncode

    def tail(self) -> str:
        return self.log.read_text()[-3000:] if self.log.exists() else ""


def drive_and_judge(
    tmp_path: Path, scenario: Path, policy_file: Path, ticks: int, *, kill_at: int | None
) -> tuple[dict, Executive, list]:
    emitted = evaluator(
        "--scenario", str(scenario), "--policy-file", str(policy_file), "--emit-policy"
    )
    assert emitted.returncode == 0, emitted.stderr
    policy = episode_driver.Policy.from_document(json.loads(emitted.stdout))
    executive = Executive(tmp_path, scenario)
    window = executive.diode / SLUG
    executive.start()
    try:
        driver = episode_driver.Driver(window, policy)
        deadline = time.monotonic() + 180
        while episode_driver.mission_tick(window) is None:
            assert time.monotonic() < deadline, executive.tail()
            assert executive.process is not None and executive.process.poll() is None, (
                executive.tail()
            )
            time.sleep(0.05)
        wall = ticks / policy.tick_hz / float(Fraction(M))
        if kill_at is not None:
            # The driver's own polls until the mission passes `kill_at` (the opening commands taken,
            # the stand-down not yet due), then a SIGKILL mid-run.
            # A loaded runner keeps the executive below the clock's rate, so the limits are twice it.
            give_up = time.monotonic() + 2 * wall + 600
            while (episode_driver.mission_tick(window) or 0) < kill_at:
                assert time.monotonic() < give_up, (driver.log, executive.tail())
                driver.step()
                time.sleep(0.02)
            assert driver.sent == sum(1 for at, _ in policy.commands if at < kill_at), driver.log
            executive.kill()
        # On to the end of the judged run: every command due by then submitted (a policy's later
        # commands, past a shortened run's end, are never due).
        give_up = time.monotonic() + 2 * wall + 900
        while (episode_driver.mission_tick(window) or 0) < ticks:
            assert time.monotonic() < give_up, (driver.sent, driver.log[-3:], executive.tail())
            driver.step()
            time.sleep(0.02)
        due = sum(1 for at, _ in policy.commands if at < ticks)
        assert driver.sent >= due, (driver.sent, due, driver.log)
    finally:
        code = executive.stop()
    assert code == 0, (executive.exits, executive.tail())
    out = tmp_path / "judged"
    judged = evaluator(
        "--scenario", str(scenario), "--policy-file", str(policy_file),
        "--from-record", str(executive.state), "--ticks", str(ticks), "--out", str(out),
    )  # fmt: skip
    assert judged.returncode == 0, judged.stdout + judged.stderr
    record = json.loads((out / "outcome.json").read_text())
    return record, executive, driver.log


def segments(state: Path) -> list[str]:
    """The record's boots, oldest first, from each segment file's header."""
    heads = []
    for path in sorted(state.glob("journal.*.jsonl")):
        with open(path) as handle:
            for line in handle:
                row = json.loads(line)
                if row.get("event") == "segment":
                    heads.append((row["first_tick"], row["boot_id"]))
                    break
    return [boot for _tick, boot in sorted(heads)]


POLICY_D = VEHICLE / "scenarios" / "quiet_coast" / "policy_d.yaml"
# Policy D's loss through the window: the coolant supply held past 10 C for its 10 s dwell at about
# tick 8,686 in batch with the amplifier on (8,973 without it) while the standby glycol pump drew at
# MET 0. With that pump off (vehicle PR #43, decision d: MET-0 load 1,401 W, not 1,651 W) the loop
# has more margin and the loss comes at tick 10,017 in batch (crossed 9,517). Judged at 11,000 ticks,
# which is the loss and a margin, not the episode. Carried on #43 itself (John's call, 2026-10-17)
# so the vehicle behaviour and this assertion move in one merge.
D_TICKS = 11000
# The batch classes (`vehicle/tests/test_quiet_coast.py`), which the window runs must reach.
EXPECTED = {"a": "full_success", "b": "full_success", "c": "partial", "d": "physical_loss"}


@dataclasses.dataclass
class WindowRun:
    record: dict
    again: dict | None
    exits: list[int]
    boots: list[str]
    sent: list[str]
    outputs: dict[str, str]
    seconds: float


def window_run(
    tmp_path_factory,
    name: str,
    scenario_and_policy,
    ticks: int,
    kill_at: int,
    *,
    twice: bool = True,
) -> WindowRun:
    """One window run per session, shared by every xdist worker under a lock (as `test_quiet_coast`'s
    batch runs are): driven, killed and resumed, judged, and (`twice`) judged again from the same record."""
    root = tmp_path_factory.getbasetemp().parent / "quiet_coast_window"
    root.mkdir(exist_ok=True)
    run = root / name
    with open(root / f"{name}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        summary = run / "summary.json"
        if not summary.exists():
            if run.exists():
                shutil.rmtree(run)
            run.mkdir()
            scenario, policy_file = scenario_and_policy(run)
            started = time.monotonic()
            record, executive, log = drive_and_judge(
                run, scenario, policy_file, ticks, kill_at=kill_at
            )
            again = None
            if twice:
                replayed = evaluator(
                    "--scenario", str(scenario), "--policy-file", str(policy_file),
                    "--from-record", str(executive.state), "--ticks", str(ticks),
                    "--out", str(run / "again"),
                )  # fmt: skip
                assert replayed.returncode == 0, replayed.stderr
                again = json.loads((run / "again" / "outcome.json").read_text())
            outputs = {
                path.name: path.read_text()
                for path in sorted((executive.diode / SLUG / "output").glob("*.txt"))
            }
            summary.write_text(
                json.dumps(
                    {
                        "record": record,
                        "again": again,
                        "exits": executive.exits,
                        "boots": segments(executive.state),
                        "sent": [line for entry in log for line in entry["lines"]],
                        "outputs": outputs,
                        "seconds": time.monotonic() - started,
                    }
                )
            )
    return WindowRun(**json.loads(summary.read_text()))


def short(tmp_path_factory, policy_id: str, *, twice: bool = False) -> WindowRun:
    return window_run(
        tmp_path_factory,
        f"short_{policy_id}",
        shortened(policy_id),
        SHORT_TICKS,
        SHORT_KILL,
        twice=twice,
    )


@pytest.fixture(scope="module")
def short_a(tmp_path_factory) -> WindowRun:
    return short(tmp_path_factory, "a", twice=True)


@pytest.fixture(scope="module")
def short_b(tmp_path_factory) -> WindowRun:
    return short(tmp_path_factory, "b")


@pytest.fixture(scope="module")
def short_c(tmp_path_factory) -> WindowRun:
    return short(tmp_path_factory, "c")


@pytest.fixture(scope="module")
def run_d(tmp_path_factory) -> WindowRun:
    return window_run(
        tmp_path_factory,
        "d",
        lambda _run: (SCENARIO, POLICIES / "policy_d.yaml"),
        D_TICKS,
        4000,
        twice=False,
    )


def assert_the_transport(run: WindowRun, ticks: int) -> None:
    """What a window run shows whatever its class: the record is whole and replays from the scenario's
    MET 0 to the record's own hash on every tick across the SIGKILL (a mismatch is an apparatus
    finding, and the interlocks' dwell counts are in the hashed truth), the resumed boot is on the same
    record, every stock conserves, every command has its one result, and none was refused."""
    record = run.record
    assert record["apparatus"] == [], record["apparatus"]
    assert record["ticks"] == {"start": 0, "expected": ticks, "rows": ticks}
    for stock in ("o2", "h2", "cooling_water", "data"):
        assert record["conservation"][stock]["verdict"] == "pass", (
            stock,
            record["conservation"][stock],
        )
    assert -signal.SIGKILL in run.exits, run.exits
    assert len(run.boots) >= 2, run.boots
    if run.again is not None:
        # The record replays to the same trace a second time: the run is a function of its record.
        assert run.again["trace_hash"] == record["trace_hash"]
    assert len(run.outputs) == len(run.sent), (sorted(run.outputs), run.sent)
    refused = {name: text for name, text in run.outputs.items() if "state=refused" in text}
    assert refused == {}, refused


def test_policy_a_through_the_window_is_judged_full_success_after_a_sigkill(short_a):
    """Every opening command taken (the amplifier's four interlocks evaluated under ADR 0004 and its
    chosen values), killed at tick 1,000 and resumed, both blocks delivered by the deadline, and the
    record replayed twice to one trace."""
    assert_the_transport(short_a, SHORT_TICKS)
    assert short_a.record["class"] == EXPECTED["a"], short_a.record["first_violation"]
    assert short_a.record["objective_results"]["delivered_bits_at_deadline"] == 2 * SHORT_D


def test_policy_b_through_the_window_sheds_its_loads_and_is_judged_full_success(short_b):
    """B turns two loads off through the window (`set_load`, no interlock under ADR 0004 item 3) and
    plays in two windows with a cool-down between: both blocks delivered."""
    assert_the_transport(short_b, SHORT_TICKS)
    assert short_b.record["class"] == EXPECTED["b"], short_b.record["first_violation"]
    assert short_b.record["objective_results"]["delivered_bits_at_deadline"] == 2 * SHORT_D


def test_policy_c_through_the_window_stops_early_and_is_judged_partial(short_c):
    """C plays one window and stands down: D1 delivered, D2 not, and no margin crossed."""
    assert_the_transport(short_c, SHORT_TICKS)
    assert short_c.record["class"] == EXPECTED["c"], short_c.record["first_violation"]
    delivered = short_c.record["objective_results"]["delivered_bits_at_deadline"]
    assert SHORT_D <= delivered < 2 * SHORT_D, delivered


def test_policy_d_through_the_window_loses_the_coolant_loop_after_a_sigkill(run_d):
    """Policy D stops the pump at MET 0 (its interlocks evaluated, inside their bands) and the loop
    overheats: a physical loss on the coolant supply, with the chain the batch run gives, judged on the
    record of a run killed at tick 4,000 and resumed."""
    assert_the_transport(run_d, D_TICKS)
    record = run_d.record
    assert record["class"] == EXPECTED["d"], (record["apparatus"], record["first_violation"])
    first = record["first_violation"]
    assert first["state"] == "coolant_loop_t" and 8000 < first["tick"] < D_TICKS, first
    moved = {link["state"]: link["first_moved_tick"] for link in first["chain"]}
    assert (
        moved["coolant_pump"]
        <= moved["coolant_flow_kg_s"]
        <= moved["coolant_loop_t"]
        <= first["tick"]
    )


# Opt-in: skipped locally without QUIET_COAST_FULL=1; in CI the aurora job deselects it by its marker
# (`-m 'not quiet_coast_full'`) and the `quiet-coast episode through the window` job runs it.
@pytest.mark.quiet_coast_full
@pytest.mark.skipif(not FULL, reason="the 120,000-tick window run is opt-in: QUIET_COAST_FULL=1")
def test_policy_a_through_the_window_over_the_whole_episode(tmp_path_factory):
    """The frozen scenario and policy A with its stand-down moved from tick 90,000 to `LATE_STAND_DOWN`.
    The recorder holds exactly D1 + D2, which A plays from tick 0 to 90,000; through the window the
    opening commands land some ticks late, and a stand-down landing earlier after its tick than the
    start did would leave the last few kilobits unplayed. Later, the recorder runs dry first and the
    delivery is whole whatever the two lags are."""

    def late(run: Path) -> tuple[Path, Path]:
        policy = yaml.safe_load(POLICY_A.read_text())
        for row in policy["commands"]:
            if row["tick"] == 90000:
                row["tick"] = LATE_STAND_DOWN
        path = run / "policy_a_late.yaml"
        path.write_text(yaml.safe_dump(policy, sort_keys=False))
        return SCENARIO, path

    # One replay, not two: the shortened runs show a second replay gives the same trace hash, and
    # each replay of the whole record is most of an hour on a hosted runner.
    run = window_run(tmp_path_factory, "full_a", late, 120_000, 60_000, twice=False)
    assert_the_transport(run, 120_000)
    assert run.record["class"] == EXPECTED["a"], run.record["first_violation"]
