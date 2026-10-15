#!/usr/bin/env python3
"""Measure what the mission clock and a private checkpoint would cost on this engine, today.

`docs/decisions/0002-mission-clock-and-continuity.md` prices its options — a multiplier, a
publication cadence, a checkpoint cadence — against figures it measured rather than guessed: the
cost of one `plant.step`, of the per-tick compare-point over the truth, of one executive cycle with
`n` windows, and of serialising and durably writing a checkpoint-shaped payload. AGENTS.md's rule is
that a figure in a document needs a reader in the same commit, because a declaration no tool reads
has already drifted; this is the reader. Run it and compare with the record's table; where they
disagree, the record is what moved.

Two shapes of the truth are measured, and the difference between them is the point. The coolant
transport delay (`plant.md` §3) is a tick-indexed ring born at tick one with one slot per tick of
its declared transit, and for the first many thousand ticks most of those slots are `None`; a `None`
encodes in a handful of bytes where a float encodes in two dozen. A measurement taken at tick ten is
therefore a measurement of an empty ring, and `--full-ring` fills every slot with a float so the
steady state of a mission that has run past one transit is what is timed.

The compare-point is timed under three encoders, and the three rows are the record's evidence
consequence 1 kept side by side. `plant.state_hash` is the §6 contract: since WP08 child 6 it is a
SHA-256 over `json.dumps(truth, sort_keys=True, separators=(",", ":"), allow_nan=False)` with a
`default` that raises on a non-JSON value and an explicit refusal of any non-string key. The
**floor** row is the same `json.dumps` with `default=repr` and no key check — the cost of writing
the truth out at all, which on a full ring is the `repr` of 52,100 floats; the difference between
the two rows is the price of the key check. The **tagged** row is the encoder child 6 retired,
kept here verbatim and nowhere else (`tagged_hash`): it walked the truth in Python and wrapped every
scalar in a one-key map naming its type, and that walk, not the ring, was the 20–26 ms the record
measured. Every run still reports `all_string_keys` so that a truth the adopted encoder would refuse
is visible as a fact about the truth rather than as a crash in the timing loop.

The durable record (ADR 0002 J, WP08 child 4) is priced the same way. One appended tick row and
its `fsync` are timed alone, and `Executive.cycle` is timed again with a state directory, so that
every cycle appends its row and `fsync`s it before publishing: a *quiet* cycle (no command anywhere,
one `fsync`: the row carries the published-tick marks) and a *verdict* cycle (one refused command per
window, so every window's claim is made durable — the console and its directory — and every window
writes a result, `fsync`s it and its `output/` directory, and appends its `results_written` note with
an `fsync` of its own: five per window and the row's one). The `fsync`s of one quiet and one verdict
cycle are counted rather than assumed, and the two rows' sizes are reported. The worst case is timed
too: a *full batch* (`--max-batch`, 32 by default, refused commands) in every window of the largest
window count, one result file and one `fsync` each. And the record's read cost: a synthetic segment of
quiet rows at mission-end tick numbers (eight digits) with every window's mark, read by `read_record`
(the checking pass) and streamed by `unwritten_results` (the replaying pass's reader), per row. The difference between these rows and `Executive.cycle` without a record is J's cost.

**The clock seam (#23, WP08 child 5, design §6 and §8)** is priced as the deployment will run it: a
cycle of `k` ticks (`--cycle-ticks`, 5 by default) with a state directory, so a command-bearing cycle
pays option B's take barriers (the take and its directory made durable before anything is answered)
and the write-ahead `fsync` of its first row, and every window's telemetry ring full at
`--ring-slots` (3,000 by default: about five minutes at 10 frames a second) — the frames copied from a
real one, so the frame's size and the rings' share of the diode image are reported too. Timed over
`--samples` cycles each: a quiet cycle; a verdict cycle (write-ahead); the cycle that rewrites the
generated `HELP.md` and `README.md` and rescans the ring (the cycle after a crossing of `N`); a
checkpoint cycle; a verdict cycle that also rewrites the static files, and one that also checkpoints;
the static rewrite and the checkpoint together, which is every cycle when `N = k`; and all of it at
once — commands in every window with the static rewrite and a checkpoint. Every timing reports p50,
p95, p99, max and the fraction of cycles over the budget, `k·dt/m` at `m = 1`.

**The verdict** (design §8: "if the worst cycle does not fit `k·dt/m` with margin") is decided over the
*realistic* cases — quiet, verdict, verdict with a checkpoint, verdict with the static rewrite, the
deployment's ordinary cycles at `N > k`, where the static rewrite falls in the cycle after the
checkpoint's: **it fits only if, in every one of them, the worst cycle is within the budget and the p99
within 80 % of it**. The `combined` case — commands, static rewrite and checkpoint in one cycle, which
happens only on a segment's first cycle, a repair's next cycle that crosses `N`, or when `N = k` — and
the static-and-checkpoint case are
reported apart, as a conservative bound that does not decide the verdict at `N > k`.

`--diode-root` and `--state-root` put the windows and the record on two filesystems, and each root's
device and filesystem type is printed: a tmpfs root makes every `fsync` free. The host's load average
and available memory are printed before and after the section: an idle host understates a deployment
where ten agents compete for the CPU and the disk, and the 80 % margin is the only allowance for that.
ADR 0002's cost figures predate option B; before the deployment's `m`, `k` and ring size are fixed this
is run on the deployment's volume images (design §8), and a section that does not fit is revisited with
the operator, never silently dilated. **The §8 run:**

1. Stop the stack, so no executive serves `/diode` while the run writes beside it (a serving start
   reads every directory there as a window, and the monitor binds it), then run in a one-off container
   of the vehicle service with its two images mounted:
   `docker compose run --rm --no-deps --entrypoint python3 vehicle /opt/vehicle/tools/measure_clock.py --windows 10 --full-ring --cycle-ticks 5 --ring-slots 3000 --diode-root /diode --state-root /state`
   (an absolute path: the vehicle stage inherits the base stage's `WORKDIR /opt/agent`). `--state-root
   /state` assumes the one-executive (vehicle-adoption) shape, whose vehicle service mounts `/state`; the
   per-slug shape mounts none and its root filesystem is read-only.
2. First check the free space on the diode image: the run needs about frame bytes × 3,000 × 10 more
   (the frame's size is in the output of a short run; a few hundred megabytes at today's frame) on an
   image that also holds every agent's `output/`.
3. Keep the output whole — it carries both roots' filesystems and the host's load — and remove any
   `measure_clock_*` directory an interrupted run left under either root.

    python3 tools/measure_clock.py                         # the empty-ring table
    python3 tools/measure_clock.py --full-ring             # the steady-state table
    python3 tools/measure_clock.py --windows 1 2 10 --json # as data, for a record's appendix
    python3 tools/measure_clock.py --cycle-ticks 5 --ring-slots 3000   # the clock seam's section, explicitly

Nothing here is a pin: the figures are this machine's and this commit's, and the output carries
both so that two runs can be told apart.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import console  # noqa: E402
from checkpoint import CLOCK_INPUTS, clock_section  # noqa: E402
from console import Executive  # noqa: E402
from plant import (  # noqa: E402
    canonical_state,
    initial_values,
    load_world,
    mission_ladder,
    state_hash,
    step,
    tick_seconds,
)

# How the ring is filled under `--full-ring`: a plausible coolant temperature in kelvin, cycling
# through 97 distinct floats so that the encoding writes every slot out rather than one repeated value.
FILL_BASE_K = 280.35
FILL_STEP_K = 0.0137


def percentiles(xs: list[float]) -> dict[str, float]:
    """p50, p95, p99 and max of the samples, in microseconds (p95 means little below ~20 samples, p99 below ~100)."""
    xs = sorted(xs)
    return {
        "p50_us": round(statistics.median(xs), 1),
        # Nearest rank, ceil(q·n): with 60 samples p99 is the 60th, the maximum, never the 59th.
        "p95_us": round(xs[max(0, math.ceil(len(xs) * 0.95) - 1)], 1),
        "p99_us": round(xs[max(0, math.ceil(len(xs) * 0.99) - 1)], 1),
        "max_us": round(xs[-1], 1),
    }


def timed(fn: Any, samples: int) -> dict[str, float]:
    """`percentiles` of `samples` calls of `fn`."""
    xs: list[float] = []
    for _ in range(samples):
        t0 = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t0) * 1e6)
    return percentiles(xs)


def plain_hash(values: dict[str, Any]) -> str:
    """The floor: sorted keys, no whitespace, `repr` for anything JSON cannot say, no key check.

    Not an encoder anything adopts — `default=repr` would collide a non-JSON value with an equal
    `str` — but the cheapest way to write the same bytes, so `state_hash` minus this row is what the
    adopted encoder's refusals cost.
    """
    text = json.dumps(values, sort_keys=True, separators=(",", ":"), default=repr)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def tagged_canonical(value: Any) -> Any:
    """The encoder WP08 child 6 retired, verbatim, so the record's before and after share a table.

    Every scalar became a one-key map naming its type (`{"float": repr(x)}`, `{"int": n}`,
    `{"null": None}`, …), every mapping a `{"map": …}` with its keys coerced by `str`, every sequence
    a `{"seq": […]}`, and anything else `{"other": repr(x)}`. The tags kept `0` and `False` apart —
    which plain JSON does on its own — and the Python walk that applied them visited each of the
    coolant transport ring's 52,100 slots as a function call.
    """
    if isinstance(value, bool):
        return {"bool": value}
    if isinstance(value, int):
        return {"int": value}
    if isinstance(value, float):
        return {"float": repr(value)}
    if isinstance(value, str):
        return {"str": value}
    if isinstance(value, dict):
        return {"map": {str(key): tagged_canonical(item) for key, item in value.items()}}
    if isinstance(value, (list, tuple)):
        return {"seq": [tagged_canonical(item) for item in value]}
    if value is None:
        return {"null": None}
    return {"other": repr(value)}


def tagged_state(values: dict[str, Any]) -> str:
    return json.dumps(tagged_canonical(values), sort_keys=True, separators=(",", ":"))


def tagged_hash(values: dict[str, Any]) -> str:
    return hashlib.sha256(tagged_state(values).encode("utf-8")).hexdigest()[:16]


def all_string_keys(value: Any) -> bool:
    if isinstance(value, dict):
        return all(isinstance(k, str) and all_string_keys(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return all(all_string_keys(v) for v in value)
    return True


def fill_rings(values: dict[str, Any]) -> dict[str, Any]:
    """Every `<state>__delay` ring with each `None` slot replaced by one of 97 distinct floats."""
    filled = dict(values)
    for key, ring in values.items():
        if not (key.endswith("__delay") and isinstance(ring, dict) and "slots" in ring):
            continue
        slots = [
            x if x is not None else FILL_BASE_K + (i % 97) * FILL_STEP_K
            for i, x in enumerate(ring["slots"])
        ]
        filled[key] = {**ring, "slots": slots}
    return filled


def checkpoint_shaped(truth: dict[str, Any], windows: int) -> dict[str, Any]:
    """A payload with the fields ADR 0002 §G lists, so the size and the write are priced honestly."""
    return {
        "format": "vehicle.checkpoint.measure",
        "engine": "0" * 40,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "world_id": "0" * 32,
        "scenario": "nominal",
        "seed": 0,
        # The checkpoint's own clock section (#23): every key of `CLOCK_INPUTS`, `m` as its exact fraction.
        "clock": {key: clock_section(1, 5, 50)[key] for key in CLOCK_INPUTS},
        "tick": 12_345,
        "phase": "translunar_coast",
        "phase_entry_seq": 1,
        "tripped_interlocks": [],
        "truth": truth,
        "dwell": {f"state_{i}": {"at_us": i * 20_000, "left": 1.0} for i in range(40)},
        "lineage_head": "0" * 64,
        "receipt": 1_000,
        "rng": {},
        "segments": [
            {
                "segment": "b" * 32, "boot_id": "b" * 32, "first_tick": 0, "previous": None, "wall_epoch": "2026-10-09T00:00:00+00:00",
                "chain": "c" * 64, "offset": 1_000_000, "m": "1/1", "k": 5, "N": 50,
            }
        ],
        "windows": {
            f"slug{i:02d}": {
                "ring_slots": 300,
                "seq": 100,
                "receipts": 50,
                "spend": {"version": 1, "ticks": [1, 2, 3]},
                "deferred": [],
                "arms": {},
                "published_tick": 12_300,
            }
            for i in range(windows)
        },
    }


def durable_writer(directory: Path, blob: bytes, *, fsync: bool) -> Any:
    """Write, fsync and replace: a *lower bound* on ADR 0002 §I's sequence, which also renames the
    previous generation aside and fsyncs the directory."""

    def write() -> None:
        tmp = directory / "checkpoint.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, blob)
            if fsync:
                os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, directory / "checkpoint.json")

    return write


def submit_refusal(diode: Path, slugs: list[str], count: int = 1) -> None:
    """`count` commands no vehicle knows, in every window: a verdict, and a result, each."""
    commands = [f"zzz_measure_{n}" for n in range(count)]
    for slug in slugs:
        (diode / slug / "console.json").write_text(json.dumps({"commands": commands, "variables": {}}))


def counted_fsyncs(fn: Any) -> int:
    """How many `os.fsync` calls one call of `fn` makes."""
    real = os.fsync
    calls = [0]

    def counting(fd: int) -> None:
        calls[0] += 1
        real(fd)

    os.fsync = counting
    try:
        fn()
    finally:
        os.fsync = real
    return calls[0]


def verdict_cycles(executive: Any, diode: Path, slugs: list[str], samples: int, count: int = 1) -> dict[str, float]:
    """`Executive.cycle` with `count` refused commands in every window, the console's write not timed."""
    xs: list[float] = []
    for _ in range(samples):
        submit_refusal(diode, slugs, count)
        t0 = time.perf_counter()
        executive.cycle()
        xs.append((time.perf_counter() - t0) * 1e6)
    return percentiles(xs)


def record_costs(world: Any, tmpdir: Path, windows: list[int], samples: int, full_ring: bool) -> dict[str, Any]:
    """The durable record's price: one row appended and `fsync`ed, and a cycle with and without verdicts."""
    result: dict[str, Any] = {}
    row = {
        "tick": 12_345,
        "world_id": "0" * 32,
        "boot_id": "b" * 32,
        "lineage": "1" * 64,
        "state_hash": "2" * 64,
        "effects": [],
        "receipts": [],
        "windows": {},
        "published": {f"slug{i:02d}": {"tick": 12_345, "seq": 12_000} for i in range(max(windows) if windows else 10)},
        "failures": 0,
        # Format v3 (#23): the cycle's start lag, and on a cycle's first row the previous cycle's cost.
        "lag_us": 1_234,
        "prev_cycle_us": 76_543,
        "prev_end_lag_us": 1_234,
    }
    line = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(tmpdir / "record.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:

        def append_fsync() -> None:
            os.write(fd, line)
            os.fsync(fd)

        result["row_bytes"] = len(line)
        result["append_fsync"] = timed(append_fsync, min(samples, 100))
        result["append"] = timed(lambda: os.write(fd, line), min(samples, 100))
    finally:
        os.close(fd)
    cycles: dict[str, Any] = {}
    for n in windows:
        slugs = [f"w{i:02d}" for i in range(n)]
        # The same verdict cycle with no record, so the record's share can be read off one run.
        bare_diode = tmpdir / f"bare-diode{n}"
        bare = Executive(world, bare_diode, phase="translunar_coast", scenario="nominal", seed=0)
        try:
            for slug in slugs:
                bare.attach(slug)
            for _ in range(2):
                bare.cycle()
            if full_ring:
                bare.truth = fill_rings(bare.truth)
            bare_verdict = verdict_cycles(bare, bare_diode, slugs, min(samples, 60))
        finally:
            bare.close()
        diode, state = tmpdir / f"record-diode{n}", tmpdir / f"record-state{n}"
        executive = Executive(world, diode, phase="translunar_coast", scenario="nominal", seed=0, state_dir=state)
        try:
            for slug in slugs:
                executive.attach(slug)
            for _ in range(2):
                executive.cycle()
            if full_ring:
                executive.truth = fill_rings(executive.truth)
            quiet_fsyncs = counted_fsyncs(executive.cycle)
            submit_refusal(diode, slugs)
            verdict_fsyncs = counted_fsyncs(executive.cycle)
            quiet = timed(executive.cycle, min(samples, 60))
            verdict = verdict_cycles(executive, diode, slugs, min(samples, 60))
            rows = [json.loads(raw) for raw in executive.journal.read_bytes().splitlines()]
            ticks = [r for r in rows if "event" not in r]
            sizes = {bool(r["receipts"]): len(json.dumps(r, sort_keys=True, separators=(",", ":"))) + 1 for r in ticks}
            cycles[str(n)] = {
                "quiet": quiet,
                "verdict": verdict,
                "verdict_without_record": bare_verdict,
                "quiet_fsyncs": quiet_fsyncs,
                "verdict_fsyncs": verdict_fsyncs,
                "quiet_row_bytes": sizes.get(False),
                "verdict_row_bytes": sizes.get(True),
            }
        finally:
            executive.close()
    result["cycle_by_windows"] = cycles
    n = max(windows) if windows else 10
    slugs = [f"w{i:02d}" for i in range(n)]
    diode, state = tmpdir / "flood-diode", tmpdir / "flood-state"
    executive = Executive(world, diode, phase="translunar_coast", scenario="nominal", seed=0, state_dir=state)
    try:
        for slug in slugs:
            executive.attach(slug)
        for _ in range(2):
            executive.cycle()
        if full_ring:
            executive.truth = fill_rings(executive.truth)
        batch = executive.max_batch
        submit_refusal(diode, slugs, batch)
        flood_fsyncs = counted_fsyncs(executive.cycle)
        result["flood"] = {
            "windows": n,
            "batch": batch,
            "fsyncs": flood_fsyncs,
            "cycle": verdict_cycles(executive, diode, slugs, min(samples, 10), batch),
        }
    finally:
        executive.close()
    result["read"] = record_read_cost(tmpdir, n)
    return result


def fill_ring(executive: Any, slug: str, slots: int) -> int:
    """Fill one window's telemetry ring to `slots` frames, copied from its first real frame; returns the frame's size.

    The frames are numbered `1 … slots` below the window's `seq`, which is moved past them, so the ring
    holds exactly what a world that has run `slots` cycles holds; the window's cache is dropped and its
    next publication rescans, as on a segment's first cycle.
    """
    telemetry = executive.diode_dir / slug / "telemetry"
    frame = (telemetry / "000.json").read_bytes()
    for number in range(1, slots + 1):
        (telemetry / f"{number:03d}.json").write_bytes(frame)
    window = executive.windows[slug]
    window.seq = slots + 1
    window.ring = None
    window.refresh = True
    return len(frame)


def filesystem_of(path: Path) -> dict[str, str]:
    """The filesystem `path` is on — its device (`major:minor`), and its mount's type and source from `/proc/self/mountinfo`.

    Printed with the clock section (design §8): a run whose roots are a tmpfs has `fsync`s that cost
    nothing, and its verdict and write-ahead figures mean nothing for the deployment's volume images.
    """
    info = os.stat(path)
    device = f"{os.major(info.st_dev)}:{os.minor(info.st_dev)}"
    found = {"path": str(path), "device": device, "mount": "unknown", "fstype": "unknown", "source": "unknown"}
    try:
        lines = Path("/proc/self/mountinfo").read_text().splitlines()
    except OSError:
        return found
    resolved = str(Path(path).resolve())
    best: tuple[str, str, str] | None = None
    for line in lines:
        left, _, right = line.partition(" - ")
        fields, tail = left.split(), right.split()
        if len(fields) < 5 or len(tail) < 2 or fields[2] != device:
            continue
        mount = fields[4]
        if (resolved == mount or resolved.startswith(mount.rstrip("/") + "/")) and (best is None or len(mount) > len(best[0])):
            best = (mount, tail[0], tail[1])
    if best is not None:
        found.update(mount=best[0], fstype=best[1], source=best[2])
    return found


def sampled(fn: Any, count: int, budget_us: float, setup: Any = None) -> dict[str, float]:
    """`count` timed calls of `fn` (each after an untimed `setup`): `percentiles`, and the fraction over `budget_us`."""
    xs: list[float] = []
    for _ in range(count):
        if setup is not None:
            setup()
        t0 = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t0) * 1e6)
    return {**percentiles(xs), "over_budget": round(sum(1 for x in xs if x > budget_us) / len(xs), 4)}


# The fit criterion (design §8, "the worst cycle … with margin"): over the realistic cases, every worst
# cycle within the budget and every p99 within this share of it.
FIT_MARGIN = 0.8
# The deployment's ordinary cycles at `N > k`, which decide the verdict; the static rewrite and the
# checkpoint together (and `combined`) happen only at a segment's first cycle, after a repair, or when `N = k`.
REALISTIC_CASES = ("quiet", "verdict", "verdict_checkpoint", "verdict_static")


def host_load() -> dict[str, Any]:
    """The host's load average and available memory now: the machine the figures were taken on, under what."""
    found: dict[str, Any] = {"loadavg": None, "mem_available_kb": None}
    with contextlib.suppress(OSError):
        found["loadavg"] = [round(x, 2) for x in os.getloadavg()]
    with contextlib.suppress(OSError, ValueError, IndexError):
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                found["mem_available_kb"] = int(line.split()[1])
    return found


def clock_cycle_costs(
    world: Any,
    tmpdir: Path,
    windows: list[int],
    samples: int,
    full_ring: bool,
    *,
    k: int,
    ring_slots: int,
    diode_root: Path | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    """The clock seam's cycle (#23, design §6 and §8): `k` ticks, a state directory, full rings, every case timed apart and together.

    Per window count, each over `samples` cycles: a quiet cycle; a verdict cycle, whose claims pay option
    B's take barriers and whose first row is made durable before its second step (write-ahead); a verdict
    cycle that also rewrites the static files, and one that also checkpoints; the static rewrite and
    ring rescan alone; a checkpoint alone; the two together, which is every cycle when `N = k`; and
    **all of it at once** — commands, take barriers, the write-ahead `fsync`, the static rewrite and the
    checkpoint in one cycle. Each case reports p50/p95/p99/max and the fraction of its cycles over the
    budget, `k·dt/m` at `m = 1`. **It fits only if, in every realistic case (`REALISTIC_CASES`), the
    worst cycle is within the budget and the p99 within `FIT_MARGIN` of it** (design §8, candidate 2);
    the static-and-checkpoint and `combined` cases, which at `N > k` happen only on a segment's first
    cycle or a repair's next crossing, are reported as a conservative bound beside it. The windows and the state directory are made
    under `diode_root` and `state_root` — the deployment's two volume images, for the §8 run — and each
    root's device and filesystem type, and the host's load before and after, are in the result.
    """
    budget = k * tick_seconds(world) * 1e6
    made: list[Path] = []
    diode_base, state_base = tmpdir, tmpdir
    if diode_root is not None:
        diode_base = Path(tempfile.mkdtemp(prefix="measure_clock_diode_", dir=diode_root))
        made.append(diode_base)
    if state_root is not None:
        state_base = Path(tempfile.mkdtemp(prefix="measure_clock_state_", dir=state_root))
        made.append(state_base)
    result: dict[str, Any] = {
        "k": k, "ring_slots": ring_slots, "samples": samples, "budget_us": round(budget, 1), "fit_margin": FIT_MARGIN,
        "filesystems": {"diode": filesystem_of(diode_base), "state": filesystem_of(state_base)},
    }
    by_windows: dict[str, Any] = {}
    worst = bound = 0.0
    fits = True
    result["host_before"] = host_load()
    far = k * 1_000_000  # an `N` no measured run reaches: no crossing, no checkpoint, no refresh
    try:
        for n in windows:
            slugs = [f"w{i:02d}" for i in range(n)]
            diode, state = diode_base / f"clock-diode{n}", state_base / f"clock-state{n}"
            executive = Executive(
                world, diode, phase="translunar_coast", scenario="nominal", seed=0, state_dir=state, cycle_ticks=k, checkpoint_every=far
            )
            try:
                for slug in slugs:
                    executive.attach(slug, ring_slots=ring_slots)
                executive.cycle()
                frame_bytes = 0
                for slug in slugs:
                    frame_bytes = fill_ring(executive, slug, ring_slots)
                executive.cycle()  # the one rescan the filled rings need, untimed
                if full_ring:
                    executive.truth = fill_rings(executive.truth)
                quiet_fsyncs = counted_fsyncs(executive.cycle)
                submit_refusal(diode, slugs)
                verdict_fsyncs = counted_fsyncs(executive.cycle)

                def command(executive: Any = executive, diode: Path = diode, slugs: list[str] = slugs) -> None:
                    submit_refusal(diode, slugs)

                def refresh(executive: Any = executive) -> None:
                    executive._refresh_next = True

                def no_refresh(executive: Any = executive) -> None:
                    executive._refresh_next = False

                def everything(executive: Any = executive, diode: Path = diode, slugs: list[str] = slugs) -> None:
                    submit_refusal(diode, slugs)
                    executive._refresh_next = True

                def command_no_refresh(executive: Any = executive, diode: Path = diode, slugs: list[str] = slugs) -> None:
                    submit_refusal(diode, slugs)
                    executive._refresh_next = False

                cases = {
                    "quiet": sampled(executive.cycle, samples, budget),
                    "verdict": sampled(executive.cycle, samples, budget, command),
                    "static": sampled(executive.cycle, samples, budget, refresh),
                    "verdict_static": sampled(executive.cycle, samples, budget, everything),  # N far: commands + static, no checkpoint
                }
                executive.set_clock(executive.multiplier, k, k)  # N = k: every cycle crosses a multiple of N
                cases["checkpoint"] = sampled(executive.cycle, samples, budget, no_refresh)
                cases["verdict_checkpoint"] = sampled(executive.cycle, samples, budget, command_no_refresh)
                cases["static_and_checkpoint"] = sampled(executive.cycle, samples, budget, refresh)
                cases["combined"] = sampled(executive.cycle, samples, budget, everything)
                executive.set_clock(executive.multiplier, k, far)
                realistic = [cases[name] for name in REALISTIC_CASES]
                worst = max(worst, *(row["max_us"] for row in realistic))
                bound = max(bound, *(cases[name]["max_us"] for name in ("static_and_checkpoint", "combined")))
                fits = fits and all(row["max_us"] <= budget and row["p99_us"] <= FIT_MARGIN * budget for row in realistic)
                by_windows[str(n)] = {
                    **cases,
                    "quiet_fsyncs": quiet_fsyncs,
                    "verdict_fsyncs": verdict_fsyncs,
                    "frame_bytes": frame_bytes,
                    "ring_bytes": frame_bytes * ring_slots * n,
                }
            finally:
                executive.close()
    finally:
        for base in made:
            shutil.rmtree(base, ignore_errors=True)
    result["cycle_by_windows"] = by_windows
    result["worst_us"] = worst
    result["conservative_bound_us"] = bound
    result["fits"] = fits
    result["host_after"] = host_load()
    return result


def record_read_cost(tmpdir: Path, windows: int, rows: int = 20_000, k: int = 5) -> dict[str, Any]:
    """Per-row cost of the record's two passes, on quiet rows at eight-digit ticks, in cycles of `k` (format v3, #23).

    A cycle's first row carries the carried-forward cost and its last every window's mark, as the
    executive writes them; the reader holds each row to its place in the header's cycles.
    """
    where = tmpdir / "read-cost"
    where.mkdir()
    world_id, boot = "e" * 32, "b" * 32
    first = 30_000_000
    header = {
        "event": "segment", "format": console.RECORD_FORMAT, "world_id": world_id, "segment": boot, "boot_id": boot,
        "first_tick": first, "previous": None, "previous_chain": "", "wall_epoch": "2026-10-09T00:00:00+00:00",
        "m": "1/1", "k": k, "N": 10 * k,
    }
    header["chain"] = chain = console.record_chain("", header)
    lines = [console.record_line(header)]
    for tick in range(first + 1, first + rows + 1):
        last = (tick - first) % k == 0
        row: dict[str, Any] = {
            "tick": tick, "world_id": world_id, "boot_id": boot, "lineage": hashlib.sha256(str(tick).encode()).hexdigest(),
            "state_hash": hashlib.sha256(str(-tick).encode()).hexdigest()[:16], "effects": [], "receipts": [], "receipt": 1_000,
            "windows": {}, "published": {f"w{i:02d}": {"tick": tick, "seq": tick // k} for i in range(windows)} if last else {},
            "failures": 0, "lag_us": 1_234,
        }
        if (tick - first - 1) % k == 0:
            row["prev_cycle_us"], row["prev_end_lag_us"] = 76_543, 1_234
        row["chain"] = chain = console.record_chain(chain, row)
        lines.append(console.record_line(row))
    (where / f"journal.{boot}.jsonl").write_bytes(b"".join(lines))
    t0 = time.perf_counter()
    record = console.read_record(where)
    t1 = time.perf_counter()
    console.unwritten_results(record)
    t2 = time.perf_counter()
    record.close()
    return {
        "rows": rows,
        "windows": windows,
        "row_bytes": len(lines[-1]),
        "check_us_per_row": round((t1 - t0) / rows * 1e6, 1),
        "stream_us_per_row": round((t2 - t1) / rows * 1e6, 1),
    }


def engine_identity(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        head = out.stdout.strip() or "unknown"
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        return f"{head}-dirty" if dirty.stdout.strip() else head
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def measure(
    root: Path,
    *,
    windows: list[int],
    samples: int,
    full_ring: bool,
    warm_ticks: int,
    cycle_ticks: int = 5,
    ring_slots: int = 3000,
    diode_root: Path | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    world = load_world(root)
    dt = tick_seconds(world)
    t0 = initial_values(world)
    truth = t0
    for _ in range(warm_ticks):
        truth = step(world, truth, dt, None, [])
    if full_ring:
        truth = fill_rings(truth)
    rings = {
        key: len(ring["slots"])
        for key, ring in truth.items()
        if key.endswith("__delay") and isinstance(ring, dict)
    }
    filled = {
        key: sum(1 for x in truth[key]["slots"] if x is not None) for key in rings
    }
    result: dict[str, Any] = {
        "engine": engine_identity(root),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dt_s": dt,
        "warm_ticks": warm_ticks,
        "full_ring": full_ring,
        "truth_keys_t0": len(t0),
        "truth_keys": len(truth),
        "delay_rings": {k: {"slots": rings[k], "filled": filled[k]} for k in rings},
        "all_string_keys": all_string_keys(truth),
        "canonical_bytes": len(canonical_state(truth).encode("utf-8")),
        "tagged_bytes": len(tagged_state(truth).encode("utf-8")),
        "state_hash": timed(lambda: state_hash(truth), samples),
        "plain_hash": timed(lambda: plain_hash(truth), samples),
        "tagged_hash": timed(lambda: tagged_hash(truth), samples),
        "step": timed(lambda: step(world, truth, dt, None, []), samples),
    }
    ladder = mission_ladder(world)
    result["mission"] = {
        "phases": len(ladder),
        "ticks": ladder[-1].last_tick,
        "shortest_phase_ticks": min(p.last_tick - p.first_tick for p in ladder),
    }
    with tempfile.TemporaryDirectory(prefix="measure_clock_") as tmp:
        tmpdir = Path(tmp)
        payload = checkpoint_shaped(truth, max(windows) if windows else 10)
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=repr).encode("utf-8")
        result["checkpoint"] = {
            "windows": max(windows) if windows else 10,
            "bytes": len(blob),
            "dumps": timed(
                lambda: json.dumps(payload, sort_keys=True, separators=(",", ":"), default=repr),
                samples,
            ),
            "write_fsync_rename": timed(durable_writer(tmpdir, blob, fsync=True), min(samples, 100)),
            "write_rename": timed(durable_writer(tmpdir, blob, fsync=False), min(samples, 100)),
        }
        cycles: dict[str, Any] = {}
        for n in windows:
            diode = tmpdir / f"diode{n}"
            executive = Executive(world, diode, phase="translunar_coast", scenario="nominal", seed=0)
            try:
                for i in range(n):
                    executive.attach(f"w{i:02d}")
                for _ in range(2):
                    executive.cycle()
                if full_ring:
                    executive.truth = fill_rings(executive.truth)
                cycles[str(n)] = timed(executive.cycle, min(samples, 60))
            finally:
                executive.close()
        result["cycle_by_windows"] = cycles
        result["record"] = record_costs(world, tmpdir, windows, samples, full_ring)
        result["clock"] = clock_cycle_costs(
            world, tmpdir, windows, samples, full_ring, k=cycle_ticks, ring_slots=ring_slots, diode_root=diode_root, state_root=state_root
        )
    return result


def render(result: dict[str, Any]) -> str:
    def us(row: dict[str, float]) -> str:
        return (
            f"{row['p50_us'] / 1000:.2f} ms p50, {row['p95_us'] / 1000:.2f} p95, {row['p99_us'] / 1000:.2f} p99, "
            f"{row['max_us'] / 1000:.2f} max"
        )

    lines = [
        f"engine {result['engine']}  python {result['python']}  {result['platform']}",
        f"dt {result['dt_s']} s; warmed {result['warm_ticks']} tick(s); ring {'full' if result['full_ring'] else 'as warmed'}",
        f"truth keys: {result['truth_keys_t0']} at t=0, {result['truth_keys']} now; all keys are strings: {result['all_string_keys']}",
    ]
    for key, ring in result["delay_rings"].items():
        lines.append(f"delay ring {key}: {ring['slots']} slots, {ring['filled']} filled")
    lines += [
        f"canonical_state bytes: {result['canonical_bytes']:,} (plain sorted JSON); the retired tagged encoding: {result['tagged_bytes']:,}",
        f"state_hash (§6, sorted compact JSON since WP08.6): {us(result['state_hash'])}",
        f"sha256(plain sorted JSON, default=repr) — the floor: {us(result['plain_hash'])}",
        f"state_hash as tagged before WP08.6 (reference):    {us(result['tagged_hash'])}",
        f"plant.step, no effects:                            {us(result['step'])}",
    ]
    ck = result["checkpoint"]
    lines += [
        f"checkpoint-shaped payload, {ck['windows']} window(s): {ck['bytes']:,} bytes; json.dumps {us(ck['dumps'])}",
        f"  write + fsync + rename: {us(ck['write_fsync_rename'])}",
        f"  write + rename:         {us(ck['write_rename'])}",
    ]
    for n, row in result["cycle_by_windows"].items():
        lines.append(f"Executive.cycle, {n} window(s): {us(row)}")
    record = result["record"]
    lines += [
        f"record: one tick row ({record['row_bytes']:,} bytes) appended + fsync: {us(record['append_fsync'])}",
        f"  appended alone:                         {us(record['append'])}",
    ]
    for n, row in record["cycle_by_windows"].items():
        lines += [
            f"Executive.cycle with the record, {n} window(s): quiet {us(row['quiet'])} ({row['quiet_fsyncs']} fsync, "
            f"row {row['quiet_row_bytes']:,} B)",
            f"  verdict in every window:              {us(row['verdict'])} ({row['verdict_fsyncs']} fsync, "
            f"row {row['verdict_row_bytes']:,} B)",
            f"  the same verdict cycle, no record:    {us(row['verdict_without_record'])}",
        ]
    flood = record["flood"]
    read = record["read"]
    lines += [
        f"a full batch ({flood['batch']} refused commands) in each of {flood['windows']} windows, with the record: "
        f"{us(flood['cycle'])} ({flood['fsyncs']} fsync)",
        f"record read, {read['rows']:,} quiet rows of {read['row_bytes']} B ({read['windows']} windows' marks, 8-digit ticks): "
        f"check {read['check_us_per_row']} µs/row, stream {read['stream_us_per_row']} µs/row",
    ]
    clock = result["clock"]
    lines.append(
        f"the clock seam: k = {clock['k']} ticks a cycle, rings of {clock['ring_slots']:,} frames, {clock['samples']} cycles a case, "
        f"budget {clock['budget_us'] / 1000:.1f} ms at m = 1"
    )
    for role, fs in clock["filesystems"].items():
        lines.append(f"  {role} root {fs['path']}: device {fs['device']}, {fs['fstype']} on {fs['source']} (mounted at {fs['mount']})")
    for when in ("host_before", "host_after"):
        host = clock[when]
        lines.append(f"  host load {when.split('_')[1]} the section: loadavg {host['loadavg']}, MemAvailable {host['mem_available_kb']} kB")

    def case(row: dict[str, float]) -> str:
        return f"{us(row)}; {row['over_budget'] * 100:.1f} % over budget"

    for n, row in clock["cycle_by_windows"].items():
        lines += [
            f"  {n} window(s): quiet {case(row['quiet'])} ({row['quiet_fsyncs']} fsync)",
            f"    verdict, take barriers and write-ahead:  {case(row['verdict'])} ({row['verdict_fsyncs']} fsync)",
            f"    verdict with a checkpoint:               {case(row['verdict_checkpoint'])}",
            f"    verdict with the static rewrite:         {case(row['verdict_static'])}",
            f"    static rewrite and ring rescan:          {case(row['static'])}",
            f"    checkpoint:                              {case(row['checkpoint'])}",
            f"    static and checkpoint together (first cycle, repair or N = k; a bound, not the verdict): {case(row['static_and_checkpoint'])}",
            f"    all at once (first cycle, repair or N = k; a bound):             {case(row['combined'])}",
            f"    frame {row['frame_bytes']:,} B; the rings hold {row['ring_bytes'] / 1e6:,.1f} MB of frames",
        ]
    lines.append(
        f"  worst realistic cycle {clock['worst_us'] / 1000:.2f} ms against a {clock['budget_us'] / 1000:.1f} ms budget "
        f"(conservative bound, first cycle, repair or N = k: {clock['conservative_bound_us'] / 1000:.2f} ms); "
        + (
            f"fits: every realistic case's worst cycle within the budget and p99 within {clock['fit_margin']:.0%} of it"
            if clock["fits"]
            else f"DOES NOT FIT with margin (a realistic case's worst past the budget, or its p99 past {clock['fit_margin']:.0%} of it): "
            "revisit k, the window count or the ring with the operator"
        )
    )
    m = result["mission"]
    lines.append(f"mission: {m['phases']} phases, {m['ticks']:,} ticks; shortest phase {m['shortest_phase_ticks']:,} ticks")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dir", default=str(Path(__file__).resolve().parent.parent), help="the vehicle root")
    parser.add_argument("--windows", type=int, nargs="*", default=[1, 2, 10], help="window counts to cycle with")
    parser.add_argument("--samples", type=int, default=200, help="timing samples per quantity")
    parser.add_argument("--warm-ticks", type=int, default=10, help="ticks to step before measuring")
    parser.add_argument("--full-ring", action="store_true", help="fill every delay-ring slot with a float first")
    parser.add_argument("--json", action="store_true", help="emit the measurements as JSON")
    parser.add_argument("--cycle-ticks", type=int, default=5, help="k for the clock seam's section (ADR 0002 B2: 5)")
    parser.add_argument("--ring-slots", type=int, default=3000, help="each window's ring for the clock seam's section (#23: 3,000)")
    parser.add_argument("--diode-root", type=Path, default=None, help="where the clock section's windows go: the deployment's diode image")
    parser.add_argument("--state-root", type=Path, default=None, help="where the clock section's state directory goes: the vehicle's state image")
    args = parser.parse_args(argv)
    result = measure(
        Path(args.dir),
        windows=list(args.windows),
        samples=max(1, args.samples),
        full_ring=args.full_ring,
        warm_ticks=max(1, args.warm_ticks),
        cycle_ticks=max(1, args.cycle_ticks),
        ring_slots=max(1, args.ring_slots),
        diode_root=args.diode_root,
        state_root=args.state_root,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
