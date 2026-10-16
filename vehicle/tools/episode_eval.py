#!/usr/bin/env python3
"""The quiet-coast episode's runner and evaluator (`09-quiet-coast-episode.md` §6 and §7 steps 8-10).

**What it reads.** Only the vehicle's own record of a run: a per-tick truth trace written from
`plant.run_scenario`'s `on_tick` (the states the scenario's `episode.trace_states` names, the tick's
state hash, every stock's ledger lines and every non-zero transfer), and the scenario file the run
declared. Never a console receipt, a result file, `pending.json`, a published frame or anything an
agent can write. A window run's record is the executive's private `/state`; the adapter from its
checkpoints and journal to this trace is owed (see `docs` in the root, 09 §6) and this module states
the trace it needs rather than reading the console's files.

**What it writes.** One neutral outcome record (JSON): the class, the objective measures, the worst
value of every margin and the tick it was reached, the first violation and the chain of upstream
states that moved before it, a conservation verdict per stock, and the vehicle SHA and scenario
hash. The chassis carries the record without interpreting it.

**Classes** (09 §6), in this precedence: `apparatus_failure` (the trace is missing, torn or not
contiguous; a stock's ledger does not balance or join; a level disagrees with its ledger; the data
identity `recorder + delivered = D` breaks; a shed or a trip with no rule; a state on the episode's
path that the tick could not advance), then `physical_loss` (a loss condition in 09 §5, with its
declared dwell), then `full_success` (M and S met, no margin violated), `partial` (M met, and S
missed or a margin violated without a loss), `timeout` (M unmet at the deadline, no loss).

**The run.** `run_episode` drives `plant.run_scenario` with the policy's commands as the scenario's
script and writes the trace. It can stop at a tick and write a checkpoint with the vehicle's own
checkpoint tool (`tools/checkpoint.py`, ADR 0002's format), and a fresh process can resume from it
and append to the same trace: the restart check (09 §7) holds the two runs' hash sequences and
outcome records equal.

    python3 tools/episode_eval.py --run quiet_coast --policy a               # 120,000 ticks, ~10 min
    python3 tools/episode_eval.py --run quiet_coast --policy a --ticks 3000  # a smoke run
    python3 tools/episode_eval.py --run quiet_coast --policy a --stop-at 60000 --state-dir S
    python3 tools/episode_eval.py --run quiet_coast --policy a --resume S
    python3 tools/episode_eval.py --evaluate .scratch/episodes/quiet_coast/a/trace.jsonl.gz

Standard library and PyYAML, through `plant`; wired into nothing.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checkpoint  # noqa: E402
import plant  # noqa: E402
import yaml  # noqa: E402

VEHICLE = Path(__file__).resolve().parents[1]
TRACE_FORMAT = "vehicle.episode-trace.v1"
OUTCOME_FORMAT = "vehicle.episode-outcome.v1"
CLASSES = ("full_success", "partial", "physical_loss", "timeout", "apparatus_failure")
KELVIN = 273.15


# -------------------------------------------------------------------------------------------------
# The episode: a scenario file and a policy file, read against the world.
# -------------------------------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scenario_paths(name: str, policy: str, root: Path = VEHICLE) -> tuple[Path, Path]:
    scenario = root / "scenarios" / f"{name}.yaml"
    return scenario, root / "scenarios" / name / f"policy_{policy}.yaml"


@dataclass
class Episode:
    world: plant.World
    scenario: plant.Scenario
    spec: dict[str, Any]
    policy: dict[str, Any]
    scenario_path: Path
    policy_path: Path
    scenario_sha: str
    policy_sha: str

    @property
    def name(self) -> str:
        return self.scenario.name

    @property
    def policy_id(self) -> str:
        return str(self.policy.get("policy"))


def load_episode(
    scenario_path: Path, policy_path: Path, world: plant.World | None = None
) -> Episode:
    """The scenario with the policy's commands as its script, validated by `plant.load_scenario`."""
    world = world if world is not None else plant.load_world(VEHICLE)
    doc = yaml.safe_load(Path(scenario_path).read_text())
    policy = yaml.safe_load(Path(policy_path).read_text())
    if doc.get("script"):
        raise plant.Unconfigured(
            f"{Path(scenario_path).name}:script",
            "an episode's script is its policy's, not the scenario's",
        )
    merged = {key: doc[key] for key in ("scenario", "initial", "verbs") if key in doc}
    merged["script"] = list(policy.get("commands") or [])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(scenario_path).name
        path.write_text(yaml.safe_dump(merged, sort_keys=False))
        scenario = plant.load_scenario(world, path)
    return Episode(
        world=world,
        scenario=scenario,
        spec=dict(doc["episode"]),
        policy=policy,
        scenario_path=Path(scenario_path),
        policy_path=Path(policy_path),
        scenario_sha=sha256_file(scenario_path),
        policy_sha=sha256_file(policy_path),
    )


# -------------------------------------------------------------------------------------------------
# The trace: gzip JSON lines. One header, then one row per tick.
#
#   {"t": tick, "h": state_hash, "s": {state: value, ...only those that changed},
#    "L": {stock: [before, after]}, "E": [[edge, source, target, quanta], ...non-zero], "g": [ids]}
#
# `L` is in the stock's quanta, the tick's first line's `before` and last line's `after`; `E` is every
# transfer that moved; `g` is the trace states the tick reported a gap on. A resumed run appends a
# `{"segment": n, "start_tick": t}` line and writes its first row in full.
# -------------------------------------------------------------------------------------------------


class TraceWriter:
    def __init__(
        self,
        path: Path,
        episode: Episode,
        *,
        append: bool = False,
        met0: dict[str, Any] | None = None,
    ) -> None:
        """`met0` is the values before the first tick: its traced states go in the header, so a state a
        command moves on tick 0 shows as moved (row 0 is already the state after that tick)."""
        self.path = Path(path)
        self.states = [str(s) for s in episode.spec["trace_states"]]
        by_id = {state.id: state for state in episode.world.states}
        missing = [sid for sid in self.states if sid not in by_id]
        if missing:
            raise plant.Unconfigured(
                "episode.trace_states", f"names {missing}, which no domain declares"
            )
        self.by_id = {sid: by_id[sid] for sid in self.states}
        self.world = episode.world
        self.previous: dict[str, Any] | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Held open for the run, one line a tick, and closed by `close()` in the runner's `finally`.
        # A resumed run appends a second gzip member, which `gzip.open` reads as one stream.
        if append and not self.path.exists():
            raise FileNotFoundError(
                f"{self.path}: a resumed run appends to its trace, and there is none"
            )
        self.handle = gzip.open(self.path, "at" if append else "wt", encoding="utf-8")  # noqa: SIM115
        if not append:
            if met0 is None:
                raise ValueError("a new trace records the MET-0 states it starts from")
            quanta = {}
            for state in episode.world.states:
                if state.method == "stock" and state.spec.get("quantum") is not None:
                    numerator, denominator = plant.stock_quantum(state, state.id)
                    quanta[state.id] = f"{numerator}/{denominator}"
            self._line(
                {
                    "format": TRACE_FORMAT,
                    "episode": episode.name,
                    "policy": episode.policy_id,
                    "vehicle_sha": checkpoint.git_commit(VEHICLE),
                    "scenario_sha": episode.scenario_sha,
                    "policy_sha": episode.policy_sha,
                    "tick_hz": episode.spec.get("tick_hz"),
                    "states": self.states,
                    "met0": {sid: self.level(met0, state) for sid, state in self.by_id.items()},
                    "quanta": quanta,
                }
            )

    def _line(self, row: dict[str, Any]) -> None:
        self.handle.write(
            json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        )

    def level(self, values: dict[str, Any], state: plant.State) -> Any:
        """A state's own value: by its id, or on the sentinel, or by a node only it occupies.

        `plant.state_level`, which no longer falls back to the key of a node several states share:
        `load_shed_class`, which never advances, used to read `load_shed_state`'s key once `set_load`
        wrote it, and a switch map looked like a shed with no rule (`tests/test_state_level.py`).
        """
        return plant.state_level(values, state)

    def segment(self, number: int, start_tick: int) -> None:
        self._line({"segment": number, "start_tick": start_tick})

    def on_tick(
        self, tick: int, values: dict[str, Any], ledger: plant.Ledger, gaps: list[plant.Gap]
    ) -> None:
        current = {sid: self.level(values, state) for sid, state in self.by_id.items()}
        if self.previous is None:
            changed = current
        else:
            changed = {
                sid: v for sid, v in current.items() if self.previous.get(sid, object()) != v
            }
        self.previous = current
        lines: dict[str, list[int]] = {}
        for line in sorted(ledger.lines, key=lambda row: row.segment):
            if line.stock in lines:
                lines[line.stock][1] = line.after
            else:
                lines[line.stock] = [line.before, line.after]
        transfers = [[t.edge, t.source, t.target, t.quanta] for t in ledger.transfers if t.quanta]
        row: dict[str, Any] = {
            "t": tick,
            "h": plant.state_hash(values),
            "s": changed,
            "L": lines,
            "E": transfers,
        }
        gapped = sorted({gap.state.id for gap in gaps if gap.state.id in self.by_id})
        if gapped:
            row["g"] = gapped
        self._line(row)

    def close(self) -> None:
        self.handle.close()


def read_trace(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The header and the tick rows, in file order. A missing or unreadable trace raises."""
    header: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            if "format" in item and header is None:
                header = item
            elif "t" in item:
                rows.append(item)
            elif "replay_mismatch" in item:
                mismatches.append(item)
    if header is None:
        raise ValueError(f"{path}: no trace header")
    return dict(header, replay_mismatches=mismatches), rows


# -------------------------------------------------------------------------------------------------
# The run.
# -------------------------------------------------------------------------------------------------


def _batch_executive(episode: Episode, tick: int, truth: dict[str, Any]) -> SimpleNamespace:
    """The executive-shaped object `checkpoint.capture_state` reads, for a batch run with no window."""
    return SimpleNamespace(
        tick=tick,
        truth=truth,
        dwell={},
        lineage_head=plant.state_hash(truth),
        receipt=0,
        seed=0,
        world_id=f"batch:{episode.name}:{episode.policy_id}",
        scenario=episode.name,
        phase=str(episode.spec.get("phase")),
        tripped=set(),
        max_batch=1,
        allowance_ceiling=1,
        windows={},
        clock=checkpoint.clock_section(1, 1, 1),
    )


def write_batch_checkpoint(
    episode: Episode, state_dir: Path, tick: int, truth: dict[str, Any]
) -> Path:
    compat = checkpoint.Compatibility.current(episode.world)
    body = checkpoint.capture_state(
        _batch_executive(episode, tick, truth), compat, git_commit=checkpoint.git_commit(VEHICLE)
    )
    return checkpoint.write_checkpoint(Path(state_dir), body)


def read_batch_checkpoint(episode: Episode, state_dir: Path) -> tuple[int, dict[str, Any]]:
    compat = checkpoint.Compatibility.current(episode.world)
    loaded = checkpoint.choose_generation(
        Path(state_dir), compat, world_id=f"batch:{episode.name}:{episode.policy_id}"
    )
    if loaded is None:
        raise FileNotFoundError(f"{state_dir}: no checkpoint to resume from")
    executive = _batch_executive(episode, 0, {})
    checkpoint.restore_state(executive, loaded.body)
    return int(executive.tick), executive.truth


def run_episode(
    episode: Episode,
    trace_path: Path,
    *,
    ticks: int | None = None,
    stop_at: int | None = None,
    state_dir: Path | None = None,
    resume: Path | None = None,
) -> dict[str, Any]:
    """Run the episode (or a part of it) and write its trace; returns the final values.

    `ticks` caps the run's end (default: the episode's duration). `stop_at` ends it early and writes a
    checkpoint into `state_dir`; `resume` reads one and appends to the existing trace.
    """
    end = int(ticks if ticks is not None else episode.spec["duration_ticks"])
    start = int(episode.spec.get("start_tick", 0))
    values = None
    met0 = None if resume is not None else plant.initial_values(episode.world, episode.scenario)
    writer = TraceWriter(trace_path, episode, append=resume is not None, met0=met0)
    try:
        if resume is not None:
            start, values = read_batch_checkpoint(episode, resume)
            writer.segment(2, start)
        last = end if stop_at is None else min(int(stop_at), end)
        values = plant.run_scenario(
            episode.world,
            episode.scenario,
            last - start,
            values=values,
            start_tick=start,
            on_tick=writer.on_tick,
        )
    finally:
        writer.close()
    if stop_at is not None:
        if state_dir is None:
            raise ValueError("--stop-at writes a checkpoint, and needs a --state-dir")
        write_batch_checkpoint(episode, state_dir, last, values)
    return values


def trace_from_record(
    episode: Episode, state_dir: Path, trace_path: Path, *, ticks: int | None = None
) -> int:
    """A window run's trace, regenerated from the executive's own record in its private `/state`.

    The window run's executive (`tools/console.py`) keeps a durable record, one row per tick with the
    effects it applied in their stamps and the tick's `state_hash`, in `journal.<boot>.jsonl` under its
    state directory, which only the vehicle service mounts and the operator reads from the host. This
    replays that record through `plant.step` from the scenario's MET-0 values and writes the same
    per-tick trace a batch run writes, holding every tick's hash to the record's. The record's tick
    `t` is the state after `t` ticks, which is the batch trace's row `t - 1`.

    A tick whose hash disagrees ends the trace with a `replay_mismatch` line, which the evaluator
    reads as an apparatus failure: the record and the scenario are not one run (the executive did not
    start from this scenario's MET 0, or the record is not the vehicle's). The replay stops after
    `ticks` (default the episode's duration), because the executive runs on past the episode. Read
    the record of a stopped executive: a live journal's last line can be partial. Returns the ticks
    written.
    """
    import console  # the executive's record reader; imported here so a batch run never loads it

    world = episode.world
    dt = plant.tick_seconds(world)
    truth = plant.initial_values(world, episode.scenario)
    through = int(ticks if ticks is not None else episode.spec["duration_ticks"])
    writer = TraceWriter(trace_path, episode, met0=truth)
    written = 0
    try:
        with console.read_record(Path(state_dir)) as record:
            for segment in console.concatenated(record.segments):
                for kind, row, _end in record.lines(segment):
                    if kind != "row" or row["tick"] < 1:
                        continue
                    if written >= through:
                        return written
                    if row["tick"] != written + 1:
                        writer._line(
                            {
                                "replay_mismatch": row["tick"],
                                "why": f"the record skips from tick {written} to {row['tick']}",
                            }
                        )
                        return written
                    effects = [
                        plant.Effect(offset, verb, dict(arguments))
                        for offset, verb, arguments in row["effects"]
                    ]
                    ledger = plant.Ledger()
                    gaps: list[plant.Gap] = []
                    truth = plant.step(world, truth, dt, gaps, effects or None, ledger=ledger)
                    if plant.state_hash(truth) != row["state_hash"]:
                        writer._line(
                            {
                                "replay_mismatch": row["tick"],
                                "why": "the replay from the scenario's MET 0 disagrees with the record's state_hash",
                            }
                        )
                        return written
                    writer.on_tick(row["tick"] - 1, truth, ledger, gaps)
                    written += 1
    finally:
        writer.close()
    return written


# -------------------------------------------------------------------------------------------------
# The evaluator.
# -------------------------------------------------------------------------------------------------


@dataclass
class Findings:
    apparatus: list[str] = field(default_factory=list)

    def fail(self, sentence: str) -> None:
        if len(self.apparatus) < 50:
            self.apparatus.append(sentence)


def _q(text: str) -> Fraction:
    return Fraction(text)


def _iter_states(rows: list[dict[str, Any]]) -> Iterator[tuple[int, dict[str, Any]]]:
    current: dict[str, Any] = {}
    for row in rows:
        current.update(row.get("s") or {})
        yield row["t"], current


def evaluate(
    trace_path: Path, spec: dict[str, Any], *, expected_ticks: int | None = None
) -> dict[str, Any]:
    """The neutral outcome record of one trace against the episode's declaration."""
    findings = Findings()
    record: dict[str, Any] = {
        "format": OUTCOME_FORMAT,
        "episode": None,
        "policy_id": None,
        "vehicle_sha": None,
        "scenario_sha": None,
        "policy_sha": None,
        "class": None,
    }
    try:
        header, rows = read_trace(Path(trace_path))
    except (OSError, ValueError, EOFError) as exc:
        record.update(
            {
                "class": "apparatus_failure",
                "apparatus": [f"the trace is missing or unreadable: {exc}"],
            }
        )
        return record
    if header.get("format") != TRACE_FORMAT:
        findings.fail(f"the trace's format is {header.get('format')!r}, not {TRACE_FORMAT}")
    for mismatch in header.get("replay_mismatches") or []:
        findings.fail(
            f"the record replay stopped at its tick {mismatch.get('replay_mismatch')}: {mismatch.get('why')}"
        )
    record.update(
        {
            "episode": header.get("episode"),
            "policy_id": header.get("policy"),
            "vehicle_sha": header.get("vehicle_sha"),
            "scenario_sha": header.get("scenario_sha"),
            "policy_sha": header.get("policy_sha"),
        }
    )
    hz = spec.get("tick_hz") or header.get("tick_hz")
    if not hz:
        record.update(
            {
                "class": "apparatus_failure",
                "apparatus": ["neither the spec nor the trace gives tick_hz"],
            }
        )
        return record
    dt = 1.0 / float(hz)
    start = int(spec.get("start_tick", 0))
    duration = int(expected_ticks if expected_ticks is not None else spec["duration_ticks"])
    objective = spec["objective"]
    deadline = min(int(objective["deadline_tick"]), start + duration)

    # --- the trace is whole: every tick from the start to the end, once, in order.
    ticks = [row["t"] for row in rows]
    if ticks != list(range(start, start + duration)):
        missing = sorted(set(range(start, start + duration)) - set(ticks))
        extra = len(ticks) - len(set(ticks))
        findings.fail(
            f"the trace is not the run's {duration} ticks from {start}: {len(ticks)} rows, "
            f"{len(missing)} missing (first {missing[:5]}), {extra} repeated"
        )
    record["ticks"] = {"start": start, "expected": duration, "rows": len(rows)}
    record["trace_hash"] = hashlib.sha256(
        "".join(f"{row['t']}:{row.get('h')}\n" for row in rows).encode()
    ).hexdigest()

    quanta = {stock: _q(text) for stock, text in (header.get("quanta") or {}).items()}
    unmodelled = set(spec.get("unmodelled") or [])
    held = set(spec.get("held") or [])
    reported: set[str] = set()

    # --- conservation, per stock: each tick's lines balance against its transfers, the ticks join,
    #     and the level the trace carries is the ledger's count times its quantum.
    stock_state: dict[str, dict[str, Any]] = {}
    d_total = int(objective["d1_bits"]) + int(objective["d2_bits"])
    data_identity_ok = True
    recorder_id, delivered_id = objective["recorder_state"], objective["delivered_state"]
    energy_j = 0.0
    battery_first: float | None = None
    battery_last: float | None = None
    thresholds = spec.get("thresholds") or {}
    worst: dict[str, dict[str, Any]] = {}
    over_since: dict[str, int | None] = dict.fromkeys(thresholds)
    losses: list[dict[str, Any]] = []
    margin_violations: list[dict[str, Any]] = []
    first_moved: dict[str, int] = {}
    # MET 0, before the first tick: a state a command moves on tick 0 has moved by row 0.
    initial_values: dict[str, Any] = dict(header.get("met0") or {})
    if "met0" not in header:
        findings.fail("the trace's header carries no MET-0 states (`met0`)")
    mandatory_tick = secondary_tick = None
    delivered_at_deadline = None
    final: dict[str, Any] = {}

    for row, (tick, state) in zip(rows, _iter_states(rows), strict=True):
        net: dict[str, int] = {}
        for edge, source, target, count in row.get("E") or []:
            if not isinstance(count, int) or count < 0:
                findings.fail(f"tick {tick}: transfer {edge} moves {count!r} quanta")
                continue
            if source is not None:
                net[source] = net.get(source, 0) - count
            if target is not None:
                net[target] = net.get(target, 0) + count
        lines = row.get("L") or {}
        for stock in net:
            if stock not in lines:
                findings.fail(f"tick {tick}: {stock} has a transfer booked and no ledger line")
        for stock, (before, after) in lines.items():
            book = stock_state.setdefault(
                stock,
                {
                    "initial": before,
                    "last": None,
                    "in": 0,
                    "out": 0,
                    "ok": True,
                    "first_failure": None,
                },
            )
            moved = net.get(stock, 0)
            problem = None
            if after - before != moved:
                problem = f"moved {after - before} quanta and its transfers explain {moved}"
            elif book["last"] is not None and before != book["last"]:
                problem = f"starts at {before} quanta and the tick before ended at {book['last']}"
            elif after < 0:
                problem = f"holds {after} quanta"
            elif (
                stock in state
                and stock in quanta
                and isinstance(state[stock], int | float)
                and abs(float(state[stock]) - float(after * quanta[stock]))
                > float(quanta[stock]) / 2
            ):
                # The level the tick published is its count times the quantum (WP10); half a quantum
                # is the float's rounding of that product and nothing else.
                problem = f"the trace carries {state[stock]!r} and its ledger {after} quanta"
            if problem is not None and book["ok"]:
                book["ok"] = False
                book["first_failure"] = {"tick": tick, "why": problem}
                findings.fail(f"{stock}: tick {tick}: {problem}")
            book["last"] = after
            # Net per tick: a stock both fed and drained in one tick books the difference.
            book["in"] += max(moved, 0)
            book["out"] += max(-moved, 0)
        # The data identity: what left the recorder reached the ground, bit for bit.
        if (
            data_identity_ok
            and recorder_id in state
            and delivered_id in state
            and int(state[recorder_id]) + int(state[delivered_id]) != d_total
        ):
            data_identity_ok = False
            findings.fail(
                f"tick {tick}: recorder {state[recorder_id]} + delivered {state[delivered_id]} "
                f"!= D1 + D2 = {d_total}"
            )
        # Electrical energy, a trend (plant.md §4): what the buses delivered, and the battery.
        load = (state.get("bus_a_load_w") or 0.0) + (state.get("bus_b_load_w") or 0.0)
        energy_j += float(load) * dt
        if "battery_charge_j" in state:
            battery_first = state["battery_charge_j"] if battery_first is None else battery_first
            battery_last = state["battery_charge_j"]
        # A state on the path that did not advance; a shed or a trip with no rule.
        for gapped in row.get("g") or []:
            if gapped not in unmodelled and gapped not in held and gapped not in reported:
                reported.add(gapped)
                findings.fail(
                    f"tick {tick}: {gapped} could not advance (a gap on the episode's path)"
                )
        for sid in unmodelled:
            if state.get(sid) is not None and sid not in reported:
                reported.add(sid)
                findings.fail(f"tick {tick}: {sid} = {state[sid]!r}, a shed or trip with no rule")
        for sid in held:
            if (
                sid in state
                and sid in initial_values
                and state[sid] != initial_values[sid]
                and sid not in reported
            ):
                reported.add(sid)
                findings.fail(
                    f"tick {tick}: {sid}, held by the episode's scope, moved to {state[sid]!r}"
                )
        # First movement of every state, for the loss chain.
        for sid, value in state.items():
            if sid not in initial_values:
                initial_values[sid] = value
            elif sid not in first_moved and value != initial_values[sid]:
                first_moved[sid] = tick
        # Objective.
        delivered = state.get(delivered_id)
        if delivered is not None and tick < deadline:
            if mandatory_tick is None and delivered >= int(objective["d1_bits"]):
                mandatory_tick = tick
            if secondary_tick is None and delivered >= d_total:
                secondary_tick = tick
            delivered_at_deadline = delivered
        # Margins and losses.
        for name, rule in thresholds.items():
            value = state.get(rule["state"])
            if not isinstance(value, int | float):
                continue
            _judge(name, rule, float(value), tick, dt, worst, over_since, losses, margin_violations)
        final = state

    # Consumables at the end.
    consumables = spec.get("consumables") or {}
    for sid, rule in consumables.items():
        value = final.get(sid)
        floor = (rule.get("at_end") or {}).get("at_least")
        if isinstance(value, int | float) and floor is not None:
            worst[f"{sid}_at_end"] = {
                "state": sid,
                "value": value,
                "limit": floor,
                "margin": float(value) - float(floor),
                "tick": rows[-1]["t"] if rows else None,
            }
            if value < floor:
                margin_violations.append(
                    {"name": f"{sid}_at_end", "state": sid, "tick": rows[-1]["t"], "value": value}
                )
        if (rule.get("loss") or {}).get("empty_with_demand"):
            # Judged from the run: water at zero while the feed is on.
            for tick, state in _iter_states(rows):
                feed = state.get(rule["loss"]["empty_with_demand"]) or {}
                if state.get(sid) is not None and state[sid] <= 0 and feed.get("csm") == "on":
                    losses.append(
                        {"name": f"{sid}_empty", "state": sid, "tick": tick, "value": state[sid]}
                    )
                    break

    record["objective_results"] = {
        "d1_bits": int(objective["d1_bits"]),
        "d2_bits": int(objective["d2_bits"]),
        "deadline_tick": deadline,
        "delivered_bits_at_deadline": delivered_at_deadline,
        "mandatory_met": mandatory_tick is not None,
        "mandatory_tick": mandatory_tick,
        "secondary_met": secondary_tick is not None,
        "secondary_tick": secondary_tick,
    }
    record["margins_min"] = worst
    record["margin_violations"] = margin_violations
    record["conservation"] = _conservation_verdicts(
        stock_state, quanta, data_identity_ok, energy_j, battery_first, battery_last
    )

    first = min(losses, key=lambda loss: (loss["tick"], loss["name"])) if losses else None
    if first is not None:
        chain = []
        for sid in (spec.get("chains") or {}).get(first["state"], [first["state"]]):
            if sid in first_moved and first_moved[sid] <= first["tick"]:
                chain.append({"state": sid, "first_moved_tick": first_moved[sid]})
        first = dict(first, chain=sorted(chain, key=lambda link: link["first_moved_tick"]))
    record["first_violation"] = first

    if findings.apparatus:
        verdict = "apparatus_failure"
    elif losses:
        verdict = "physical_loss"
    elif mandatory_tick is None:
        verdict = "timeout"
    elif secondary_tick is not None and not margin_violations:
        verdict = "full_success"
    else:
        verdict = "partial"
    record["class"] = verdict
    record["apparatus"] = findings.apparatus
    return record


def _limit_k(rule: dict[str, Any], key: str) -> float:
    return float(rule[key]) + KELVIN


def _judge(name, rule, value, tick, dt, worst, over_since, losses, margin_violations) -> None:
    margin = rule.get("margin") or {}
    loss = rule.get("loss") or {}
    if "at_least" in margin:
        distance = value - float(margin["at_least"])
        limit = float(margin["at_least"])
    elif "below_c" in margin:
        limit = _limit_k(margin, "below_c")
        distance = limit - value
    elif "between_c" in margin:
        low, high = (float(x) + KELVIN for x in margin["between_c"])
        distance = min(value - low, high - value)
        limit = [low, high]
    else:
        return
    row = worst.get(name)
    if row is None or distance < row["margin"]:
        worst[name] = {
            "state": rule["state"],
            "value": value,
            "limit": limit,
            "margin": distance,
            "tick": tick,
        }
    if distance < 0 and not any(v["name"] == name for v in margin_violations):
        margin_violations.append(
            {"name": name, "state": rule["state"], "tick": tick, "value": value}
        )
    if (
        "below" in loss
        and value < float(loss["below"])
        and not any(item["name"] == name for item in losses)
    ):
        losses.append(
            {
                "name": name,
                "state": rule["state"],
                "tick": tick,
                "crossed_tick": tick,
                "value": value,
            }
        )
    if "above_c" in loss:
        if value > _limit_k(loss, "above_c"):
            if over_since[name] is None:
                over_since[name] = tick
            dwell_ticks = float(loss.get("dwell_s", 0.0)) / dt
            if (tick - over_since[name] + 1) > dwell_ticks and not any(
                item["name"] == name for item in losses
            ):
                losses.append(
                    {
                        "name": name,
                        "state": rule["state"],
                        "tick": tick,
                        "crossed_tick": over_since[name],
                        "value": value,
                    }
                )
        else:
            over_since[name] = None


def _conservation_verdicts(
    stock_state, quanta, data_ok, energy_j, battery_first, battery_last
) -> dict[str, Any]:
    def stock(sid: str) -> dict[str, Any]:
        book = stock_state.get(sid)
        if book is None:
            return {"verdict": "absent", "why": "no ledger line in the trace"}
        q = quanta.get(sid, Fraction(1))
        identity = book["initial"] + book["in"] - book["out"] == book["last"]
        return {
            "verdict": "pass" if book["ok"] and identity else "fail",
            "initial": float(book["initial"] * q),
            "final": float(book["last"] * q),
            "in": float(book["in"] * q),
            "out": float(book["out"] * q),
            "quantum": str(q),
            "first_failure": book["first_failure"],
        }

    verdicts = {
        "o2": dict(
            stock("o2_csm_kg"),
            note="the tank; cabin O2 enters from an unbooked source (E-O2-ECLSS) and is not judged against it",
        ),
        "h2": stock("h2_csm_kg"),
        "cooling_water": stock("water_cooling_kg"),
        "data": {
            "verdict": "pass"
            if data_ok
            and stock("recorder")["verdict"] == "pass"
            and stock("delivered_bits")["verdict"] == "pass"
            else "fail",
            "identity": "recorder + delivered_bits = D1 + D2, every tick",
            "recorder": stock("recorder"),
            "delivered_bits": stock("delivered_bits"),
        },
        "electrical_energy_trend": {
            "verdict": "trend",
            "note": "a trend, never an assertion (plant.md §4): the energy the two main buses delivered, and the battery, which the episode holds",
            "bus_energy_j": energy_j,
            "battery_charge_j": {
                "first": battery_first,
                "last": battery_last,
                "held": battery_first == battery_last,
            },
        },
    }
    others = {
        sid: stock(sid)
        for sid in sorted(stock_state)
        if sid not in {"o2_csm_kg", "h2_csm_kg", "water_cooling_kg", "recorder", "delivered_bits"}
    }
    verdicts["other_stocks"] = {sid: row["verdict"] for sid, row in others.items()}
    return verdicts


def policy_document(scenario_path: Path, policy_path: Path) -> dict[str, Any]:
    """A policy as the operator's driver reads it, in JSON because the driver is standard library:
    each command as the console line `verb key=value ...` (keys sorted, as the executive spells a
    command), keyed by tick, with the mission's tick rate and the episode's length."""
    spec = yaml.safe_load(Path(scenario_path).read_text())["episode"]
    policy = yaml.safe_load(Path(policy_path).read_text())
    commands = []
    for row in policy.get("commands") or []:
        arguments = row.get("arguments") or {}
        line = " ".join(
            [str(row["verb"]), *(f"{key}={arguments[key]}" for key in sorted(arguments))]
        )
        commands.append({"tick": int(row["tick"]), "line": line})
    return {
        "episode": Path(scenario_path).stem,
        "policy": str(policy.get("policy")),
        "tick_hz": spec.get("tick_hz"),
        "duration_ticks": spec.get("duration_ticks"),
        "commands": commands,
    }


def write_outcome(record: dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


# -------------------------------------------------------------------------------------------------
# The CLI.
# -------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--run", metavar="SCENARIO", help="run a scenario by name (scenarios/<name>.yaml)"
    )
    parser.add_argument("--policy", help="the policy id (scenarios/<name>/policy_<id>.yaml)")
    parser.add_argument("--ticks", type=int, help="end the run (and judge it) at this many ticks")
    parser.add_argument("--stop-at", type=int, help="stop at this tick and write a checkpoint")
    parser.add_argument("--state-dir", type=Path, help="where --stop-at writes its checkpoint")
    parser.add_argument("--resume", type=Path, metavar="STATE_DIR", help="resume from a checkpoint")
    parser.add_argument(
        "--out", type=Path, help="the run's directory (trace.jsonl.gz, outcome.json)"
    )
    parser.add_argument("--evaluate", type=Path, metavar="TRACE", help="judge an existing trace")
    parser.add_argument("--scenario", type=Path, help="the scenario file for --evaluate")
    parser.add_argument("--expect", choices=CLASSES, help="exit 1 unless the outcome is this class")
    parser.add_argument(
        "--from-record",
        type=Path,
        metavar="STATE_DIR",
        help="a window run: regenerate the trace from the executive's record in its private state directory",
    )
    parser.add_argument(
        "--emit-policy",
        action="store_true",
        help="print the policy as the operator's driver reads it",
    )
    args = parser.parse_args(argv)

    if args.emit_policy:
        if not args.run or not args.policy:
            parser.error("--emit-policy needs --run and --policy")
        print(json.dumps(policy_document(*scenario_paths(args.run, args.policy)), indent=2))
        return 0

    if args.evaluate is not None:
        scenario = args.scenario or scenario_paths("quiet_coast", "a")[0]
        spec = yaml.safe_load(scenario.read_text())["episode"]
        out = args.out or args.evaluate.with_name("outcome.json")
    else:
        if not args.run or not args.policy:
            parser.error("--run and --policy, or --evaluate")
        scenario, policy = scenario_paths(args.run, args.policy)
        episode = load_episode(scenario, policy)
        run_dir = args.out or VEHICLE / ".scratch" / "episodes" / args.run / args.policy
        trace = run_dir / "trace.jsonl.gz"
        if args.from_record is not None:
            written = trace_from_record(episode, args.from_record, trace, ticks=args.ticks)
            print(f"replayed {written} tick(s) of the record in {args.from_record} -> {trace}")
            return _judge_and_write(trace, episode.spec, run_dir / "outcome.json", args)
        began = time.monotonic()
        run_episode(
            episode,
            trace,
            ticks=args.ticks,
            stop_at=args.stop_at,
            state_dir=args.state_dir,
            resume=args.resume,
        )
        wall = time.monotonic() - began
        print(
            f"ran {episode.name} policy {episode.policy_id} in {wall:.1f} s of wall time -> {trace}"
        )
        if args.stop_at is not None and args.stop_at < (
            args.ticks or episode.spec["duration_ticks"]
        ):
            print(f"stopped at tick {args.stop_at}; checkpoint in {args.state_dir}")
            return 0
        return _judge_and_write(trace, episode.spec, run_dir / "outcome.json", args)
    return _judge_and_write(args.evaluate, spec, out, args)


def _judge_and_write(trace: Path, spec: dict[str, Any], out: Path, args: argparse.Namespace) -> int:
    record = evaluate(trace, spec, expected_ticks=args.ticks)
    write_outcome(record, out)
    print(f"{record['class']}: {out}")
    for line in record.get("apparatus") or []:
        print(f"  apparatus: {line}")
    if args.expect is not None and record["class"] != args.expect:
        print(f"expected {args.expect}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
