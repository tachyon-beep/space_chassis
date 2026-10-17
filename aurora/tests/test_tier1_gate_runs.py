"""#39, the chassis's evidence: the q1–q3 re-run, and ≥ 30 gate runs with instrumented early returns.

**What was measured before.** On 2026-10-10 the chassis ran `test_the_vehicle_passes_the_contract_probe`
ten times in each of three modes against vehicle `8c6f71d`: q1 untraced (0/10 failed), q2 with the
console under an audit hook (`tests/trace_console.py`; 1/10), q3 with that and the probe's own submit
trace (2/10). All three losses were ERASED batches, each renamed over by a quiet cycle's rewrite
(`governance/vehicle/records/2026-10-14-lane-archive/39-option-b/CHECKPOINT.md`, checkpoint 2). Tier 1
(vehicle `f75420c`) stopped a quiet cycle from writing at all, and option B (PR #9) stopped every
claim from writing over a file: the console is taken aside by a rename, and the emptied console is put
back by a link that never replaces one (`docs/diode-contract.md` §2.2). John's acceptance for tier 1
includes "≥ 30 gate runs with instrumented early returns" (`governance/vehicle/decisions.md`,
2026-10-11), and D8 qualifies option B by the same runs, written as a test.

**What a run is here.** One unchanged `contract/diode_probe.py` walk of one window, as the gate's test
makes it, against the executive started the way `containers/serve_vehicle.sh` starts it (its clock,
ring, scenario, seed and a private state directory). To be fast enough for CI, each mode starts one
executive serving ten windows and walks all ten at once, one probe per window, so the three modes are
thirty gate runs in well under a minute. Ten windows on one executive is a harder schedule than the
gate's one: every cycle claims and publishes for all ten, which widens the gap between a console's
clearing and its results.

**Instrumented early returns.** The probe's `wait_for_results` returns as soon as it has counted
enough new files, and a file is new if it was not there before the check. So a check can count a
previous batch's late result and return before its own batch is claimed or answered, and the probe's
next submit then lands over that batch (`governance/vehicle/records/2026-10-11-39-claim-race-decision-memo.md`,
tier 1). Each run's probe is a subclass that changes nothing it does and records:

* every early return: a wait that counted a result belonging to another batch;
* for every submit, whether the console it replaced still held an unclaimed batch.

**What must hold.** Under option B a claim takes whatever is at `console.json` when it renames it, so
the only way a batch can go unanswered is to be replaced before it is taken (the contract: "Replacing
a batch before it is taken supersedes it"). So every batch each probe submitted is answered, unless the
next submit replaced it while the console still showed it unclaimed; a batch lost otherwise fails the
test. Every probe check that failed must follow an early return in its run. After the probes stop,
each window's console must keep its inode and mtime while the executive goes on cycling (a console
with nothing to claim is left as it is). In the traced modes the console must never be renamed over
(`console_replace`), every claim is a take of `console.json` (`console_take`), there is at most one
take per submitted batch and at least one per batch that was not superseded, and the emptied console
is put back by a link (`console_link`) no more often than there was a take or an absent console.

The run's record goes to `TIER1_GATE_EVIDENCE/<mode>-<ns>/<mode>.json` when that is set, and every
failure message carries it. `TIER1_GATE_VEHICLE` points the runs at another vehicle checkout; it must
take the clock flags (`f75420c` and earlier do not, so they cannot be run here any more).
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import diode_probe
import pytest

REPO = Path(__file__).resolve().parents[2]
AURORA = Path(__file__).resolve().parents[1]
VEHICLE = Path(os.environ.get("TIER1_GATE_VEHICLE") or REPO / "vehicle")
MODES = ("q1", "q2", "q3")
WINDOWS = 10
RUNS = WINDOWS * len(MODES)
PUBLISHED = ("console.json", "state.json", "HELP.md", "pending.json")
# How the stack serves the vehicle (`containers/serve_vehicle.sh`, its defaults): the clock (#23, which
# replaced `--poll`) at m = 1, k = 5, N = 50, the ring, the scenario and the seed, and a private state
# directory, so the claim's take is made durable as it is in the stack.
SERVED = {
    "--scenario": "nominal",
    "--seed": "0",
    "--ring-slots": "3000",
    "--multiplier": "1",
    "--cycle-ticks": "5",
    "--checkpoint-ticks": "50",
    "--cycles": "0",
}
# One cycle at those settings: k ticks at the vehicle's 50 Hz, at m = 1.
CYCLE = 5 / 50
# Each probe check that reads results, by the index of the submit it waits on. Only these can
# be failed by counting a result from another batch.
CHECK_SUBMIT = {
    "each command produces exactly one result file": 1,
    "a result filename carries the submitting agent": 1,
    "a result filename carries no separator or traversal": 1,
    "a non-string element refuses the whole batch": 2,
    "an unknown verb is refused with a result file": 3,
    "an unknown verb is refused by name": 3,
}


def safe_name(text: str) -> str:
    """The contract's result-name rule (§2.3): every non-alphanumeric character becomes `_`."""
    cleaned = "".join(char if char.isalnum() else "_" for char in text)
    return cleaned.encode("utf-8")[:160].decode("utf-8", "ignore")


@dataclasses.dataclass
class InstrumentedProbe(diode_probe.Probe):
    """The probe, unchanged in what it does, recording its submits and its early returns."""

    submits: list[dict] = dataclasses.field(default_factory=list)
    early: list[dict] = dataclasses.field(default_factory=list)

    def owns(self, index: int, name: str) -> bool:
        """Whether result file `name` answers submit `index` (by the command in its name)."""
        commands = self.submits[index]["commands"]
        if not all(isinstance(command, str) for command in commands):
            # A malformed batch is answered by one refusal, named for the batch, not a command.
            return name.endswith(f"_{self.slug}_malformed_batch.txt")
        return any(name.endswith(f"_{self.slug}_{safe_name(c)}.txt") for c in commands)

    def submit(self, commands: list, variables: dict | None = None) -> None:
        # An absent console (a claim's take, before the emptied one is put back) reads as `{}`:
        # nothing unclaimed is there to replace.
        held = self.read_console().get("commands")
        self.submits.append(
            {
                "commands": list(commands),
                "over_unclaimed": isinstance(held, list) and bool(held),
                "at": time.monotonic(),
            }
        )
        super().submit(commands, variables)

    def wait_for_results(self, before: set[str], count: int = 1) -> list[Path]:
        new = super().wait_for_results(before, count)
        index = len(self.submits) - 1
        foreign = [path.name for path in new if not self.owns(index, path.name)]
        if foreign:
            self.early.append(
                {
                    "submit": index,
                    "counted": foreign,
                    "own_batch_claimed": self.read_console().get("commands") == [],
                }
            )
        return new


def test_the_runs_serve_the_vehicle_the_way_the_stack_does():
    """The flags above are the serve script's own defaults, so the runs judge the stack's window."""
    script = (AURORA / "containers" / "serve_vehicle.sh").read_text(encoding="utf-8")
    defaults = {
        "--scenario": "VEHICLE_SCENARIO",
        "--seed": "VEHICLE_SEED",
        "--ring-slots": "VEHICLE_RING_SLOTS",
        "--multiplier": "VEHICLE_MULTIPLIER",
        "--cycle-ticks": "VEHICLE_CYCLE_TICKS",
        "--checkpoint-ticks": "VEHICLE_CHECKPOINT_TICKS",
    }
    for flag, variable in defaults.items():
        assert f'{flag} "${variable}"' in script, flag
        assert f': "${{{variable}:={SERVED[flag]}}}"' in script, (flag, SERVED[flag])
    assert "--cycles 0" in script and '--state-dir "$VEHICLE_STATE_DIR"' in script


def start_executive(mode: str, evidence: Path, slugs: list[str]) -> subprocess.Popen:
    console = [str(VEHICLE / "tools" / "console.py"), "--dir", str(VEHICLE)]
    console += ["--diode-dir", str(evidence / "diode"), "--state-dir", str(evidence / "state")]
    for flag, value in SERVED.items():
        console += [flag, value]
    for slug in slugs:
        (evidence / "diode" / slug).mkdir(parents=True, exist_ok=True)
        console += ["--slug", slug]
    if mode in ("q2", "q3"):
        console = [
            str(AURORA / "tests" / "trace_console.py"),
            str(evidence / "console-trace.jsonl"),
            str(evidence / "diode"),
            *console,
        ]
    return subprocess.Popen(
        [sys.executable, *console],
        stdout=(evidence / "console.stdout").open("wb"),
        stderr=(evidence / "console.stderr").open("wb"),
    )


def stamp(path: Path) -> tuple[int, int] | None:
    try:
        status = os.stat(path)
    except FileNotFoundError:
        return None
    return status.st_ino, status.st_mtime_ns


def read_json(path: Path) -> dict:
    with contextlib.suppress(OSError, ValueError):
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            return loaded
    return {}


@pytest.mark.parametrize("mode", MODES)
def test_tier_1_holds_over_gate_runs_with_instrumented_early_returns(mode, tmp_path):
    assert RUNS >= 30
    evidence = tmp_path
    if os.environ.get("TIER1_GATE_EVIDENCE"):
        evidence = Path(os.environ["TIER1_GATE_EVIDENCE"]) / f"{mode}-{time.time_ns()}"
        evidence.mkdir(parents=True)
    slugs = [f"gate{index:02d}" for index in range(WINDOWS)]
    diode = evidence / "diode"
    executive = start_executive(mode, evidence, slugs)
    probes = {
        slug: InstrumentedProbe(
            diode,
            slug,
            poll_seconds=0.3,
            timeout=15,
            trace=(evidence / f"probe-trace-{slug}.jsonl") if mode == "q3" else None,
        )
        for slug in slugs
    }
    exit_codes: dict[str, int] = {}
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not all(
            (diode / slug / name).exists() for slug in slugs for name in PUBLISHED
        ):
            assert executive.poll() is None, (evidence / "console.stderr").read_text()[-2000:]
            time.sleep(0.1)
        for slug in slugs:
            for name in PUBLISHED:
                assert (diode / slug / name).exists(), f"{slug} never published {name}"

        def walk(slug: str) -> None:
            exit_codes[slug] = probes[slug].run()

        with contextlib.redirect_stdout(io.StringIO()):
            threads = [threading.Thread(target=walk, args=(slug,)) for slug in slugs]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=120)
        assert sorted(exit_codes) == slugs, "a probe did not finish"

        # Settle: every console claimed, then long enough for any result still owed to land.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and any(
            read_json(diode / slug / "console.json").get("commands") != [] for slug in slugs
        ):
            time.sleep(CYCLE)
        time.sleep(20 * CYCLE)

        # Quiet cycles write nothing: the consoles stay put while the executive keeps cycling.
        consoles = {slug: stamp(diode / slug / "console.json") for slug in slugs}
        states = {slug: stamp(diode / slug / "state.json") for slug in slugs}
        time.sleep(20 * CYCLE)
        moved = [
            slug
            for slug in slugs
            if consoles[slug] is None or stamp(diode / slug / "console.json") != consoles[slug]
        ]
        cycled = [slug for slug in slugs if stamp(diode / slug / "state.json") != states[slug]]
        assert executive.poll() is None, "the executive stopped"
    finally:
        executive.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            executive.wait(timeout=10)

    runs = []
    for slug in slugs:
        probe = probes[slug]
        results = sorted(path.name for path in (diode / slug / "output").iterdir())
        lost = []
        for index, submit in enumerate(probe.submits):
            if any(probe.owns(index, name) for name in results):
                continue
            lost.append(
                {
                    "submit": index,
                    "commands": [repr(c) for c in submit["commands"]],
                    "superseded": index + 1 < len(probe.submits)
                    and probe.submits[index + 1]["over_unclaimed"],
                }
            )
        failed = [check.name for check in probe.checks if check.passed is False]
        unexplained = [
            name
            for name in failed
            if name not in CHECK_SUBMIT
            or not any(early["submit"] <= CHECK_SUBMIT[name] for early in probe.early)
        ]
        runs.append(
            {
                "window": slug,
                "exit": exit_codes[slug],
                "failed_checks": failed,
                "unexplained_failures": unexplained,
                "early_returns": probe.early,
                "submits_over_unclaimed": sum(s["over_unclaimed"] for s in probe.submits),
                "lost": lost,
                "results": len(results),
            }
        )
    trace = []
    if mode in ("q2", "q3"):
        trace = [
            json.loads(line)
            for line in (evidence / "console-trace.jsonl").read_text().splitlines()
            if line.strip()
        ]
    count = {
        kind: sum(1 for event in trace if event["event"] == kind)
        for kind in ("console_open", "console_take", "console_link", "console_replace")
    }
    submits = sum(len(probes[slug].submits) for slug in slugs)
    flagged = sum(run["submits_over_unclaimed"] for run in runs)
    record = {
        "mode": mode,
        "runs": runs,
        "consoles_moved_while_quiet": moved,
        "windows_cycled_while_watched": len(cycled),
        "console_trace": {**count, "submits": submits, "submits_over_unclaimed": flagged},
    }
    (evidence / f"{mode}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    where = f"\n{json.dumps(record, indent=1)[-6000:]}\n(evidence: {evidence})"

    assert len(runs) == WINDOWS, where
    assert [run for run in runs if [x for x in run["lost"] if not x["superseded"]]] == [], (
        "a batch went unanswered that was never replaced before its take" + where
    )
    assert [run for run in runs if run["unexplained_failures"]] == [], where
    assert len(cycled) == WINDOWS, (
        "the executive did not cycle while the consoles were watched" + where
    )
    assert moved == [], "a console with nothing to claim was rewritten" + where
    if mode in ("q2", "q3"):
        assert count["console_open"] > 0, "the tracer saw nothing" + where
        assert count["console_replace"] == 0, "a claim renamed over console.json" + where
        # Each submitted batch is taken at most once; only a batch replaced before its take is not.
        assert submits - flagged <= count["console_take"] <= submits, where
        # The emptied console goes back once per take, plus each window's first publication.
        assert count["console_link"] <= count["console_take"] + WINDOWS, where


def test_the_instrument_counts_a_previous_batch_s_late_result_as_an_early_return(tmp_path):
    """The instrument itself, without a vehicle: a wait that counts another batch's result is recorded."""
    window = tmp_path / "diode" / "otter"
    (window / "output").mkdir(parents=True)
    (window / "console.json").write_text(json.dumps({"commands": [], "variables": {}}))
    probe = InstrumentedProbe(tmp_path / "diode", "otter", poll_seconds=0.01, timeout=1)
    probe.submit(["verb probe"], {"probe_marker": True})
    before = probe.results()
    probe.submit(["verb probe-a", "verb probe-b"])
    assert probe.submits[-1]["over_unclaimed"], "the first batch was never claimed"
    for name in ("1_otter_verb_probe.txt", "2_otter_verb_probe_a.txt"):
        (window / "output" / name).write_text("answer\n")
    assert len(probe.wait_for_results(before, count=2)) == 2
    assert probe.early == [
        {"submit": 1, "counted": ["1_otter_verb_probe.txt"], "own_batch_claimed": False}
    ]
    probe.submit(["verb probe", 42])
    before = probe.results()
    (window / "output" / "3_otter_malformed_batch.txt").write_text("refused\n")
    probe.wait_for_results(before)
    assert len(probe.early) == 1, "the malformed batch's own refusal was counted as foreign"
