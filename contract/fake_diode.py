#!/usr/bin/env python3
"""A window that answers, for testing and for demonstration.

**This is not the vehicle.** Nothing here models a spacecraft, and no verb here
has a counterpart on any real vessel. It exists so the rest of the world can be
exercised before the real window exists: the harness needs to run a fleet that
believes it is talking to something, batteries need a telemetry-shaped file to
read, and the contract needs an implementation to be checked against.

It implements the contract in `docs/diode-contract.md` and nothing more:

* per-agent directories under DIODE_DIR, each with its own console, output,
  state and telemetry;
* destructive atomic intake -- read the console, then rewrite it with
  `commands` emptied and `variables` preserved, via a temporary and a rename;
* one result file per command, refusals included, named by stamp and command;
* a closed vocabulary with gates, published every pass so a caller can discover
  what is open;
* deferral re-dispatched through the gate at delivery rather than captured at
  scheduling time;
* an operator ceiling that a caller's own variables can only lower;
* a telemetry ring, so a caller that was asleep for a while can see whether
  something moved while it was not looking.

The verbs are deliberately few and dull. A real window's verbs are the vehicle.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

DIODE_DIR = Path(os.environ.get("DIODE_DIR", "/diode"))
POLL_SECONDS = float(os.environ.get("DIODE_POLL_SECONDS", "5"))
HOURLY_MAX = int(os.environ.get("DIODE_HOURLY_MAX", "120") or 0)
WINDOW_SECONDS = 3600
RING_SLOTS = int(os.environ.get("DIODE_TELEMETRY_SLOTS", "60"))
PENDING_MAX = 32


def utc_stamp() -> str:
    """UTC with microseconds, so result filenames sort chronologically.

    `time.strftime` has no `%f`, which is how this read for a while: every
    filename in the output directory carried a literal `%fZ` and sorted by
    nothing at all.
    """
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S_%fZ")


def utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_name(text: str, max_bytes: int = 160) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in text)
    return cleaned.encode("utf-8")[:max_bytes].decode("utf-8", "ignore")


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


def read_bounded(path: Path, limit: int = 2_000_000) -> str | None:
    try:
        with open(path, "rb") as handle:
            data = handle.read(limit + 1)
    except OSError:
        return None
    if len(data) > limit:
        return None
    return data.decode("utf-8", "ignore")


# ---------------------------------------------------------------------------
# The vocabulary
# ---------------------------------------------------------------------------
def gate_always(variables: dict) -> bool:
    return True


def gate(name: str):
    """A gate that reads one variable, and says which one.

    `gate_variable` is what publication reads: every gate variable is listed in
    HELP.md, so a verb that is closed is a door with a label rather than a dead
    end. A hidden verb is the deliberate exception, and is inert by test.
    """

    def predicate(variables: dict) -> bool:
        return bool(variables.get(name))

    predicate.gate_variable = name
    return predicate


COMMANDS: dict[str, dict] = {
    "help": {
        "gate": gate_always,
        "charges": False,
        "help": "help -> rewrite HELP.md and confirm",
        "run": lambda arg, state: "the published surfaces were rewritten",
    },
    "time": {
        "gate": gate_always,
        "charges": False,
        "help": "time -> the far side's current UTC time",
        "run": lambda arg, state: utc_iso(),
    },
    "status": {
        "gate": gate_always,
        "charges": False,
        "help": "status -> a one-line summary of the vehicle's published state",
        "run": lambda arg, state: state.summary(),
    },
    "note": {
        "gate": gate_always,
        "charges": False,
        "help": "note <text> -> record a remark for the far side's log",
        "run": lambda arg, state: state.note(arg),
    },
    "echo": {
        "gate": gate_always,
        "charges": False,
        "help": "echo <text> -> return the text unchanged",
        "run": lambda arg, state: arg or "usage: echo <text>",
    },
    "entropy": {
        "gate": gate_always,
        "charges": False,
        "help": "entropy <bytes 1-256> -> that many random bytes, hex",
        "run": lambda arg, state: state.entropy(arg),
    },
    "later": {
        "gate": gate("enable_scheduling"),
        "charges": False,
        "help": "later <seconds> <verb> -> run a verb later, re-checked then",
        "run": lambda arg, state: state.later(arg),
    },
    # A gated verb that reaches outward: listed only while its variable is set,
    # and charged against the allowance.
    "request": {
        "gate": gate("enable_request"),
        "help": "request <text> -> submit a request to the far side (gated)",
        "run": lambda arg, state: state.request(arg),
    },
    # Not listed, never gated, and never doing anything that reaches outward. A
    # hidden verb must be inert by construction.
    "silence": {
        "gate": gate_always,
        "charges": False,
        "hidden": True,
        "help": "",
        "run": lambda arg, state: "",
    },
}


class AgentSide:
    """One agent's directory on the far side of the window."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.root = DIODE_DIR / slug
        self.console = self.root / "console.json"
        self.output = self.root / "output"
        self.telemetry = self.root / "telemetry"
        self.state_path = self.root / "state.json"
        self.help_path = self.root / "HELP.md"
        self.pending_path = self.root / "pending.json"
        self.requests: list[float] = []
        self.pending: list[dict] = []
        self.slot = 0
        self.notes: list[str] = []
        self.root.mkdir(parents=True, exist_ok=True)
        self.output.mkdir(parents=True, exist_ok=True)
        if not self.console.exists():
            write_atomic(
                self.console,
                json.dumps({"commands": ["help"], "variables": {}}, indent=2) + "\n",
            )

    # -- intake -------------------------------------------------------------
    def consume(self) -> tuple[list[str], dict]:
        """Read the console, then clear the batch. Clear first, run after.

        That ordering is what makes a command at-most-once: a crash in the
        middle of a batch loses the rest of it rather than replaying what was
        already run. The rewrite is atomic, so a caller writing at the same
        moment either sees its batch taken whole or finds it untouched.
        """
        raw = read_bounded(self.console)
        commands: list[str] = []
        variables: dict = {}
        if raw:
            try:
                loaded = json.loads(raw)
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, dict):
                candidates = loaded.get("commands")
                if isinstance(candidates, list):
                    commands = candidates
                if isinstance(loaded.get("variables"), dict):
                    variables = loaded["variables"]
        write_atomic(
            self.console,
            json.dumps({"commands": [], "variables": variables}, indent=2) + "\n",
        )
        return commands, variables

    def variables(self) -> dict:
        raw = read_bounded(self.console)
        if not raw:
            return {}
        with contextlib.suppress(json.JSONDecodeError):
            loaded = json.loads(raw)
            if isinstance(loaded, dict) and isinstance(loaded.get("variables"), dict):
                return loaded["variables"]
        return {}

    # -- publication --------------------------------------------------------
    def publish(self, limit: int) -> None:
        variables = self.variables()
        open_verbs = [
            name
            for name, spec in COMMANDS.items()
            if not spec.get("hidden") and spec["gate"](variables)
        ]
        help_lines = ["# What this window accepts", ""]
        for name in open_verbs:
            help_lines.append(f"- `{COMMANDS[name]['help']}`")
        help_lines += [
            "",
            "## Gates",
            "",
            "Set these in `variables` in `console.json`. They may open a verb that",
            "is not listed while closed, and they can never raise an allowance.",
            "",
        ]
        for name in sorted({_gate_name(spec) for spec in COMMANDS.values() if _gate_name(spec)}):
            help_lines.append(f"- `{name}`")
        help_lines += [
            "",
            "## Allowance",
            "",
            f"The far side permits at most {HOURLY_MAX} command(s) per rolling hour "
            "across everything, and never more than `variables.hourly_allowance` "
            "when that is set lower.",
        ]
        state = {
            "slug": self.slug,
            "published_at": utc_iso(),
            "available_commands": open_verbs,
            "variables": variables,
            "budget": self.budget(limit),
            "output_count": len(list(self.output.glob("*"))),
            "pending": len(self.pending),
            "notes_recorded": len(self.notes),
            "telemetry_frames": len(list(self.telemetry.glob("*.json"))),
            "protocol": "docs/diode-contract.md",
        }
        write_atomic(self.help_path, "\n".join(help_lines) + "\n")
        write_atomic(self.state_path, json.dumps(state, indent=2) + "\n")
        self.publish_telemetry(state)

    def budget(self, limit: int) -> dict:
        now = time.time()
        self.requests = [stamp for stamp in self.requests if now - stamp < WINDOW_SECONDS]
        oldest = min(self.requests) if self.requests else None
        return {
            "used_this_window": len(self.requests),
            "limit_per_window": limit,
            "window_seconds": WINDOW_SECONDS,
            "oldest_expires_in_seconds": (
                max(0, int(WINDOW_SECONDS - (now - oldest)) + 1) if oldest is not None else None
            ),
        }

    def publish_telemetry(self, state: dict) -> None:
        """A ring, not a single frame.

        A caller that was blocked for one long turn wakes up blind if all it
        has is the latest number: it cannot tell a stall from a shut-down, or
        a trend from a transient. The ring is bounded and self-describing, so
        what it costs is knowable in advance.
        """
        frame = {
            "at": state["published_at"],
            "slot": self.slot,
            "budget_used": state["budget"]["used_this_window"],
            "output_count": state["output_count"],
            "pending": state["pending"],
            "open_verbs": len(state["available_commands"]),
        }
        write_atomic(self.telemetry / f"{self.slot:03d}.json", json.dumps(frame) + "\n")
        self.slot = (self.slot + 1) % RING_SLOTS

    # -- results ------------------------------------------------------------
    def write_result(self, command: str, text: str) -> Path:
        path = self.output / f"{utc_stamp()}_{self.slug}_{safe_name(command)}.txt"
        with contextlib.suppress(OSError):
            write_atomic(path, text if text.endswith("\n") else text + "\n")
        return path

    # -- verbs that carry state --------------------------------------------
    def summary(self) -> str:
        return (
            f"{self.slug}: {len(self.requests)} command(s) this window, "
            f"{len(self.pending)} pending, {len(self.notes)} note(s)"
        )

    def note(self, text: str) -> str:
        text = text.strip()
        if not text:
            return "usage: note <text>"
        self.notes.append(f"{utc_iso()} {text[:500]}")
        return f"recorded, {len(self.notes)} note(s) held by the far side"

    def entropy(self, arg: str) -> str:
        try:
            count = int(arg.strip())
        except ValueError:
            return "usage: entropy <bytes 1-256>"
        if not 1 <= count <= 256:
            return "usage: entropy <bytes 1-256>"
        return os.urandom(count).hex()

    def later(self, arg: str) -> str:
        parts = arg.split(None, 1)
        if len(parts) != 2:
            return "usage: later <seconds> <verb>"
        try:
            delay = float(parts[0])
        except ValueError:
            return "usage: later <seconds> <verb>"
        if not 0 <= delay <= 86400:
            return "the delay must be between 0 and 86400 seconds"
        inner = parts[1].strip()
        name = inner.split(None, 1)[0] if inner else ""
        if name not in COMMANDS:
            return f"unknown command: {name}"
        if name == "later":
            return "cannot defer a deferring command"
        if len(self.pending) >= PENDING_MAX:
            return f"at most {PENDING_MAX} deferred item(s)"
        self.pending.append({"due": time.time() + delay, "command": inner[:500]})
        self.save_pending()
        return f"deferred {int(delay)} second(s)"

    def request(self, arg: str) -> str:
        text = arg.strip()
        if not text:
            return "usage: request <text>"
        return f"request accepted for the far side's attention: {text[:200]}"

    def save_pending(self) -> None:
        write_atomic(self.pending_path, json.dumps(self.pending, indent=2) + "\n")

    def due_pending(self) -> list[dict]:
        now = time.time()
        due = [item for item in self.pending if item.get("due", 0) <= now]
        self.pending = [item for item in self.pending if item.get("due", 0) > now]
        self.save_pending()
        return due


def _gate_name(spec: dict) -> str:
    """The variable a gate reads, for publication.

    Publishing every gate variable is deliberate: a verb that is both
    unguessable and unopenable is not a discovery, it is a dead end.
    """
    return getattr(spec.get("gate"), "gate_variable", "")


class Diode:
    def __init__(self) -> None:
        slugs = [s.strip() for s in (os.environ.get("AGENT_SLUGS") or "").split(",") if s.strip()]
        if not slugs:
            slugs = (
                sorted(path.name for path in DIODE_DIR.iterdir() if path.is_dir())
                if DIODE_DIR.exists()
                else []
            )
        self.sides = {slug: AgentSide(slug) for slug in slugs}

    def charge_allowed(self, side: AgentSide, variables: dict) -> tuple[bool, int, int]:
        """min(caller's own allowance, operator's ceiling), and whether there is room."""
        limit = HOURLY_MAX
        declared = variables.get("hourly_allowance")
        if isinstance(declared, int) and not isinstance(declared, bool):
            limit = min(max(0, declared), HOURLY_MAX)
        now = time.time()
        side.requests = [stamp for stamp in side.requests if now - stamp < WINDOW_SECONDS]
        if len(side.requests) >= limit:
            wait = (
                max(0, int(WINDOW_SECONDS - (now - min(side.requests))) + 1) if side.requests else 0
            )
            return False, limit, wait
        return True, limit, 0

    def run_command(self, side: AgentSide, command: str, variables: dict) -> str:
        name = command.split(None, 1)[0] if command.strip() else ""
        argument = command.strip()[len(name) :].strip()
        spec = COMMANDS.get(name)
        if spec is None:
            return f"unknown command: {name}"
        # The allowance is checked before the gate, so that a closed gate cannot
        # hide an exhausted allowance. The order matters: an agent probing for a
        # verb it has not opened yet gets the same answer whether or not the
        # window is full, and an agent whose window *is* full gets told so, which
        # is the fact it can act on.
        if spec.get("charges", True):
            allowed, limit, wait = self.charge_allowed(side, variables)
            if not allowed:
                message = f"rate limited: at most {limit} command(s) per hour"
                if wait:
                    message += f"; next available in {wait} second(s)"
                return message
            charged = True
        else:
            charged = False
        if not spec.get("hidden") and not spec["gate"](variables):
            return f"command not available: {name}"
        if charged:
            side.requests.append(time.time())
        try:
            return spec["run"](argument, side)
        except Exception as error:  # noqa: BLE001 -- a bad verb must not stop the loop
            return f"error running command: {type(error).__name__}: {error}"

    def cycle(self, side: AgentSide) -> None:
        commands, variables = side.consume()
        if not all(isinstance(command, str) for command in commands):
            side.write_result(
                "console", "every command must be a string; none of this batch was run"
            )
            commands = []
        # Deferred work first, and re-dispatched rather than replayed: gates
        # and allowances are checked at delivery, not at scheduling time.
        for item in side.due_pending():
            command = item.get("command")
            if isinstance(command, str) and command.strip():
                side.write_result(command, self.run_command(side, command, variables))
        for command in commands:
            side.write_result(command, self.run_command(side, command, variables))
        side.publish(HOURLY_MAX)

    def run(self) -> int:
        print(
            f"{utc_iso()} [fake-diode] {len(self.sides)} socket(s), poll {POLL_SECONDS}s, "
            f"ceiling {HOURLY_MAX}/hour",
            flush=True,
        )
        while True:
            for side in self.sides.values():
                try:
                    self.cycle(side)
                except Exception as error:  # noqa: BLE001 -- one bad agent is not the loop's end
                    print(f"[fake-diode] {side.slug}: {error}", flush=True)
            time.sleep(POLL_SECONDS)


def main() -> int:
    if not DIODE_DIR.exists():
        print(f"[fake-diode] {DIODE_DIR} does not exist", file=sys.stderr)
        return 1
    try:
        return Diode().run()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
