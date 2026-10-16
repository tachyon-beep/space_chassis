"""The quiet-coast episode through the real window executive, without Docker (09-quiet-coast-episode.md §7 step 11).

D14 wants the policies driven through the window, not only in batch. This is that run with everything
but the containers: the executive (`vehicle/tools/console.py`) started as a process the way
`containers/serve_vehicle.sh` starts it -- the clock, the ring, the posture and seed, a private state
directory -- plus `--scenario-file`, which starts the world at the scenario's MET 0 and holds its verb
allow-list (`VEHICLE_SCENARIO_FILE` in the stack). Policy A goes in through the window's one uplink,
written by the operator's driver (`scripts/episode_driver.py`) exactly as an agent would write it; the
episode is judged by the vehicle's evaluator (`episode_eval.py --from-record`) on the executive's own
private record, never on a result file.

**The shortened episode** (always): the same scenario with its task shrunk to fit a few thousand ticks
-- D1 = D2 = 1,000 ticks of playback at the configured 1,024 bits a tick, the recorder loaded with
D1 + D2, a 3,000-tick contact -- and policy A with its stand-down moved from tick 90,000 to 2,500. The
stand-down is late on purpose: a window run lands each command at the cycle that takes it, after the
policy's tick, so the playback starts some ticks late and runs the recorder dry before it stops. The
run is SIGKILLed part-way (after policy A's opening commands have been taken), restarted on the same
state directory with the same scenario file, and driven on to the end. The evaluator replays the whole
record from the scenario's MET 0 and holds every tick's state hash to the record's, so a resumed run
that did not continue the killed one bit for bit is an apparatus failure; the test also holds the
record to two boots and replays it a second time to the same trace hash, with every conservation
verdict passing.

**Interlocks (ADR 0004).** The executive evaluates a declared interlock whose chain reads (threshold,
band, dwell, reading), with the dwell count in the hashed truth, and refuses INTERLOCK UNEVALUATED a
verb any of whose interlocks does not read. The batch run never meets that gate, since it applies the
scripted effects through `plant.step`. `set_evaporator_feed` and `set_coolant_pump` are evaluated and
taken; `set_power_amplifier` is still refused, because `tx_power_high` has no band and
`power.load_margin_low` watches a prose estimate. So policy A's amplifier never comes on and its class
is `timeout`: one test asserts the transport and exactly that gap, and the `full_success` assertion is
a strict xfail naming it. Policy D (the pump stopped at MET 0) needs no amplifier, and its physical
loss of the coolant loop is a real assertion, on a run killed and resumed past the point where the
coolant-supply interlock's dwell count is accumulating. Each run is made once per session and shared.

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
POLICY_A = VEHICLE / "scenarios" / "quiet_coast" / "policy_a.yaml"
SLUG = "agent_1"
M = os.environ.get("QUIET_COAST_WINDOW_M", "2")
FULL = os.environ.get("QUIET_COAST_FULL") == "1"
# The shortened episode: 1,000 ticks of playback each for D1 and D2, a 3,000-tick contact.
SHORT_TICKS = 3000
SHORT_D = 1000 * 1024
SHORT_STAND_DOWN = 2500
# Policy A's own stand-down tick, which the shortened variant moves.
STAND_DOWN = 90000
# The executive's exit for the lag backstop: a clean end the stack's restart policy resumes.
EXIT_BACKSTOP = 4


def shortened(tmp_path: Path) -> tuple[Path, Path]:
    """The scenario with its task shrunk, and policy A with its stand-down moved: every other line as is."""
    doc = yaml.safe_load(SCENARIO.read_text())
    doc["initial"]["recorder"] = 2 * SHORT_D
    episode = doc["episode"]
    episode["duration_ticks"] = SHORT_TICKS
    episode["objective"].update(deadline_tick=SHORT_TICKS, d1_bits=SHORT_D, d2_bits=SHORT_D)
    scenario = tmp_path / "quiet_coast_short.yaml"
    scenario.write_text(yaml.safe_dump(doc, sort_keys=False))
    policy = yaml.safe_load(POLICY_A.read_text())
    assert {row["tick"] for row in policy["commands"]} == {0, STAND_DOWN}
    for row in policy["commands"]:
        if row["tick"] == STAND_DOWN:
            row["tick"] = SHORT_STAND_DOWN
    policy_path = tmp_path / "policy_a_short.yaml"
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False))
    return scenario, policy_path


def evaluator(*args: str, timeout: float = 3600) -> subprocess.CompletedProcess:
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
            give_up = time.monotonic() + wall + 600
            while (episode_driver.mission_tick(window) or 0) < kill_at:
                assert time.monotonic() < give_up, (driver.log, executive.tail())
                driver.step()
                time.sleep(0.02)
            assert driver.sent == sum(1 for at, _ in policy.commands if at == 0), driver.log
            executive.kill()
        # On to the end of the judged run: every command due by then submitted (a policy's later
        # commands, past a shortened run's end, are never due).
        give_up = time.monotonic() + wall + 900
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
# Policy D's loss through the window: the coolant supply past 10 C from about tick 8,470 and held past
# its 10 s dwell by about tick 8,970 with the amplifier refused (8,686 in batch with it on); judged at
# 9,500 ticks, which is the loss and a margin, not the episode.
D_TICKS = 9500
# The one verb of the quiet-coast policies whose interlocks still cannot be read (ADR 0004): its four
# are power.bus_a_undervoltage and thermal.comm_amp_high (evaluated), tx_power_high (band UNCONFIGURED)
# and power.load_margin_low (an estimate with prose for arithmetic).
UNREADABLE = "set_power_amplifier"
UNREADABLE_REASON = (
    "ADR 0004: set_power_amplifier's interlocks tx_power_high (band UNCONFIGURED) and "
    "power.load_margin_low (point power.load_margin_w is a prose estimate) cannot be read, so the "
    "window refuses it INTERLOCK UNEVALUATED and the amplifier never comes on"
)


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


@pytest.fixture(scope="module")
def short_a(tmp_path_factory) -> WindowRun:
    return window_run(tmp_path_factory, "short_a", shortened, SHORT_TICKS, SHORT_TICKS * 2 // 5)


@pytest.fixture(scope="module")
def run_d(tmp_path_factory) -> WindowRun:
    return window_run(
        tmp_path_factory, "d", lambda _run: (SCENARIO, POLICY_D), D_TICKS, 4000, twice=False
    )


def assert_the_transport(run: WindowRun, ticks: int) -> None:
    """What a window run shows whatever its class: the record is whole and replays from the scenario's
    MET 0 to the record's own hash on every tick across the SIGKILL (a mismatch is an apparatus
    finding, and the interlocks' dwell counts are in the hashed truth), the resumed boot is on the same
    record, every stock conserves, and every command has its one result."""
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


def refusals(run: WindowRun) -> dict[str, str]:
    """Each refused command's verb and the refusal's kind, from the result files."""
    found = {}
    for name, text in run.outputs.items():
        if "state=refused" in text:
            kind = text.split(".", 1)[0].removeprefix("refused: ")
            verb = next(
                (
                    v
                    for v in (
                        "set_power_amplifier",
                        "set_evaporator_feed",
                        "set_coolant_pump",
                        "set_load",
                    )
                    if f"_{v}_" in name
                ),
                name,
            )
            found[verb] = kind
    return found


def test_policy_a_through_the_window_survives_a_sigkill_and_its_record_replays(short_a):
    """The transport holds. The evaporator's interlocks are evaluated and the feed is taken; the
    amplifier's are not all readable, so it is refused, nothing is delivered and the run is a `timeout`."""
    assert_the_transport(short_a, SHORT_TICKS)
    assert refusals(short_a) == {UNREADABLE: "INTERLOCK UNEVALUATED"}, refusals(short_a)
    assert short_a.record["class"] == "timeout", short_a.record["first_violation"]
    assert short_a.record["objective_results"]["delivered_bits_at_deadline"] == 0


@pytest.mark.xfail(strict=True, reason=UNREADABLE_REASON)
def test_policy_a_through_the_window_is_judged_full_success(short_a):
    assert short_a.record["class"] == "full_success", short_a.record["first_violation"]
    assert short_a.record["objective_results"]["delivered_bits_at_deadline"] == 2 * SHORT_D


def test_policy_d_through_the_window_loses_the_coolant_loop_after_a_sigkill(run_d):
    """Policy D stops the pump at MET 0 (its interlocks evaluated, inside their bands) and the loop
    overheats: a physical loss on the coolant supply, with the chain the batch run gives, judged on the
    record of a run killed at tick 4,000 and resumed."""
    assert_the_transport(run_d, D_TICKS)
    assert refusals(run_d) == {UNREADABLE: "INTERLOCK UNEVALUATED"}, refusals(run_d)
    record = run_d.record
    assert record["class"] == "physical_loss", (record["apparatus"], record["first_violation"])
    first = record["first_violation"]
    assert first["state"] == "coolant_loop_t" and 8000 < first["tick"] < D_TICKS, first
    moved = {link["state"]: link["first_moved_tick"] for link in first["chain"]}
    assert (
        moved["coolant_pump"]
        <= moved["coolant_flow_kg_s"]
        <= moved["coolant_loop_t"]
        <= first["tick"]
    )


@pytest.mark.skipif(not FULL, reason="the 120,000-tick window run is opt-in: QUIET_COAST_FULL=1")
@pytest.mark.xfail(strict=True, reason=UNREADABLE_REASON)
def test_policy_a_through_the_window_over_the_whole_episode(tmp_path_factory):
    run = window_run(tmp_path_factory, "full_a", lambda _run: (SCENARIO, POLICY_A), 120_000, 60_000)
    assert_the_transport(run, 120_000)
    assert run.record["class"] == "full_success", (run.record["first_violation"], refusals(run))
