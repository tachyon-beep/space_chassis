#!/usr/bin/env python3
"""Drive one window from the operator's side with a scripted policy: the quiet-coast episode's driver.

`docs/vehicle-completion/09-quiet-coast-episode.md` §7 step 11. A policy is the vehicle's (its files
live in `vehicle/scenarios/<episode>/`); this driver names no verb and models nothing. It reads the
policy as the vehicle tool prints it (`python3 vehicle/tools/episode_eval.py --run quiet_coast
--policy a --emit-policy`):

    {"policy": "a", "tick_hz": 50, "duration_ticks": 120000,
     "commands": [{"tick": 0, "line": "<verb> key=value ..."}, ...]}

and submits each command line through the window's one uplink, `/diode/<slug>/console.json`, once
the mission clock the window publishes (`state.json`'s `executive.tick`, MET = tick / tick_hz) has
reached the command's tick. The contract (`docs/diode-contract.md` §2.2) sets how:

* **the console is written whole**, to a temporary in the window directory, then renamed over
  `console.json`: never in place, because an in-place write can be read partially or continue into
  a file the vehicle has already taken;
* **a batch is never replaced before it is taken.** Replacing a console that still holds commands
  supersedes them, so the driver writes only while the console is absent (the vehicle may have
  renamed it aside) or holds an empty `commands` list; otherwise it waits for the take;
* **`variables` are preserved**: the driver writes back the map the console last showed, and no
  `variables` key when it has never seen one;
* **there is no next-cycle guarantee**, so a command lands at the tick the vehicle takes it, which
  can be later than the policy's: the window run is judged on its own record, never on the batch
  run's timing.

The driver reads the window's published files without following links (`health.read_claim`) and
bounds every read. It never reads a result file: what happened is the vehicle's record, judged by the
vehicle's evaluator (`vehicle/tools/episode_eval.py --from-record`), never by receipts.

    python3 scripts/episode_driver.py --window /diode/agent_1 --policy policy_a.json
    python3 scripts/episode_driver.py --window ... --policy ... --poll-seconds 0.05 --timeout 3000

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))

from common import write_json_atomic  # noqa: E402
from health import read_claim  # noqa: E402

CONSOLE = "console.json"
STATE = "state.json"
# A console or a state file larger than this is not one the driver reads.
READ_LIMIT = 4 << 20
# The most command lines the driver puts in one console; a longer due list waits for the next take.
MAX_BATCH = 8


@dataclass
class Policy:
    policy: str
    tick_hz: float
    duration_ticks: int
    commands: list[tuple[int, str]]

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> Policy:
        commands = []
        for index, row in enumerate(document.get("commands") or []):
            tick, line = row.get("tick"), row.get("line")
            if not isinstance(tick, int) or isinstance(tick, bool) or tick < 0:
                raise ValueError(f"commands[{index}]: tick {tick!r} is not a non-negative integer")
            if not isinstance(line, str) or not line.strip() or "\n" in line:
                raise ValueError(f"commands[{index}]: {line!r} is not one command line")
            commands.append((tick, line.strip()))
        hz = document.get("tick_hz")
        if not isinstance(hz, int | float) or isinstance(hz, bool) or hz <= 0:
            raise ValueError(f"tick_hz {hz!r} is not a positive rate")
        # Stable: commands due at one tick keep the policy's order (a shed before a play).
        commands.sort(key=lambda item: item[0])
        return cls(
            policy=str(document.get("policy")),
            tick_hz=float(hz),
            duration_ticks=int(document.get("duration_ticks") or 0),
            commands=commands,
        )


def _read_json(window: Path, name: str) -> tuple[bool, Any]:
    """(present, value): absent or unreadable is (False, None); present but not JSON is (True, None)."""
    raw = read_claim(window, name, READ_LIMIT)
    if raw is None:
        return False, None
    try:
        return True, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return True, None


def mission_tick(window: Path) -> int | None:
    """The tick the window last published (`state.json`'s `executive.tick`), or None if unreadable."""
    _, state = _read_json(window, STATE)
    if not isinstance(state, dict):
        return None
    tick = (state.get("executive") or {}).get("tick")
    if isinstance(tick, int) and not isinstance(tick, bool) and tick >= 0:
        return tick
    return None


@dataclass
class Driver:
    window: Path
    policy: Policy
    max_batch: int = MAX_BATCH
    sent: int = 0
    # The map the console last showed, and whether one has been seen.
    variables: dict[str, Any] = field(default_factory=dict)
    variables_known: bool = False
    log: list[dict[str, Any]] = field(default_factory=list)

    def due(self, tick: int) -> list[str]:
        """The command lines due at `tick` and not yet submitted, in policy order, at most a batch."""
        lines = []
        for at, line in self.policy.commands[self.sent :]:
            if at > tick or len(lines) >= self.max_batch:
                break
            lines.append(line)
        return lines

    def console_free(self) -> bool:
        """Whether a batch may be written now: the console is absent, or it holds no commands.

        Anything else -- a batch not yet taken, a file that is not a console, a link -- is waited out:
        replacing it would supersede what it holds."""
        present, console = _read_json(self.window, CONSOLE)
        if not present:
            # Absent (taken and not yet restored), or not a regular file: only absence is free.
            return not (self.window / CONSOLE).is_symlink() and not (self.window / CONSOLE).exists()
        if not isinstance(console, dict):
            return False
        variables = console.get("variables")
        if isinstance(variables, dict):
            self.variables, self.variables_known = variables, True
        commands = console.get("commands")
        return isinstance(commands, list) and not commands

    def submit(self, lines: list[str]) -> None:
        console: dict[str, Any] = {"commands": lines}
        if self.variables_known:
            console["variables"] = self.variables
        write_json_atomic(self.window / CONSOLE, console)

    def step(self) -> int:
        """One poll: submit what is due if the console is free. Returns the lines submitted."""
        tick = mission_tick(self.window)
        if tick is None or self.done():
            return 0
        lines = self.due(tick)
        if not lines or not self.console_free():
            return 0
        self.submit(lines)
        self.sent += len(lines)
        self.log.append({"tick": tick, "met_s": tick / self.policy.tick_hz, "lines": lines})
        return len(lines)

    def done(self) -> bool:
        return self.sent >= len(self.policy.commands)

    def run(
        self,
        *,
        poll_seconds: float,
        timeout: float,
        until_tick: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> bool:
        """Poll until every command is submitted and the window has reached `until_tick` (default the
        policy's duration), or until `timeout` wall seconds pass. Returns whether it finished."""
        end_tick = self.policy.duration_ticks if until_tick is None else until_tick
        deadline = clock() + timeout
        while clock() < deadline:
            self.step()
            tick = mission_tick(self.window)
            if self.done() and tick is not None and tick >= end_tick:
                return True
            sleep(poll_seconds)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--window", type=Path, required=True, help="the window directory, /diode/<slug>"
    )
    parser.add_argument(
        "--policy", type=Path, required=True, help="the policy JSON (--emit-policy)"
    )
    parser.add_argument("--poll-seconds", type=float, default=0.05)
    parser.add_argument(
        "--timeout", type=float, default=3600.0, help="wall seconds before giving up"
    )
    parser.add_argument("--until-tick", type=int, help="stop once the window reaches this tick")
    args = parser.parse_args(argv)
    policy = Policy.from_document(json.loads(args.policy.read_text(encoding="utf-8")))
    driver = Driver(args.window, policy)
    finished = driver.run(
        poll_seconds=args.poll_seconds, timeout=args.timeout, until_tick=args.until_tick
    )
    for entry in driver.log:
        print(f"tick {entry['tick']} (MET {entry['met_s']:.2f} s): {'; '.join(entry['lines'])}")
    if not finished:
        print(
            f"timed out: {driver.sent} of {len(policy.commands)} command(s) submitted",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
