#!/usr/bin/env python3
"""Walk a diode implementation through the contract and report what it did.

This is the instrument for the other half of the build. It knows no verbs: it
learns the vocabulary from what the implementation publishes, submits through
the same console file an agent would use, and checks the properties in
`docs/diode-contract.md` that can be checked mechanically.

It deliberately does not test physics, mission structure, or whether the verbs
are any good. Those are judgements about a vehicle. This only answers: does the
window behave the way the world is built to expect?

    python3 contract/diode_probe.py --diode-dir ./volumes/diode --slug otter

Exit status is 0 when every check passed, 1 when any failed, and 2 when the
directory or the console could not be used at all.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SERVICES = Path(__file__).resolve().parent.parent / "services"
sys.path.insert(0, str(SERVICES))

from common import read_bounded, utc_now  # noqa: E402


@dataclass
class Check:
    name: str
    passed: bool | None = None
    detail: str = ""


@dataclass
class Probe:
    diode_dir: Path
    slug: str
    poll_seconds: float = 5.0
    timeout: float = 120.0
    checks: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    # -- paths --------------------------------------------------------------
    @property
    def root(self) -> Path:
        return Path(self.diode_dir) / self.slug

    @property
    def console(self) -> Path:
        return self.root / "console.json"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def help_file(self) -> Path:
        return self.root / "HELP.md"

    @property
    def telemetry(self) -> Path:
        return self.root / "telemetry"

    def check(self, name: str, passed: bool | None, detail: str = "") -> None:
        self.checks.append(Check(name, passed, detail))

    def note(self, text: str) -> None:
        self.notes.append(text)

    # -- plumbing -----------------------------------------------------------
    def results(self) -> set[str]:
        if not self.output.is_dir():
            return set()
        return {path.name for path in self.output.iterdir() if path.is_file()}

    def wait_for_results(self, before: set[str], count: int = 1) -> list[Path]:
        """Wait for `count` new result files, or until the timeout."""
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            new = sorted(self.results() - before)
            if len(new) >= count:
                return [self.output / name for name in new]
            time.sleep(0.25)
        return [self.output / name for name in sorted(self.results() - before)]

    def submit(self, commands: list, variables: dict | None = None) -> None:
        payload = {"commands": commands}
        if variables is not None:
            payload["variables"] = variables
        self.console.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.console.with_suffix(".probe.tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.console)

    def read_console(self) -> dict:
        raw = read_bounded(self.console, 2_000_000)
        if not raw:
            return {}
        with contextlib.suppress(json.JSONDecodeError):
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                return loaded
        return {}

    def read_json(self, path: Path) -> dict:
        raw = read_bounded(path, 2_000_000)
        if not raw:
            return {}
        with contextlib.suppress(json.JSONDecodeError):
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                return loaded
        return {}

    def published_verbs(self) -> list[str]:
        state = self.read_json(self.state)
        verbs = state.get("available_commands")
        if isinstance(verbs, list):
            return [str(verb) for verb in verbs]
        text = read_bounded(self.help_file, 200_000)
        if not text:
            return []
        verbs = []
        for line in text.decode("utf-8", "ignore").splitlines():
            line = line.strip()
            if line.startswith("- `") and line.endswith("`"):
                verbs.append(line[3:-1].split(">")[0].split()[0])
        return verbs

    def published_gates(self) -> list[str]:
        text = read_bounded(self.help_file, 200_000)
        if not text:
            return []
        gates = []
        for line in text.decode("utf-8", "ignore").splitlines():
            line = line.strip()
            if line.startswith("|") and line.endswith("|"):
                continue
            if line.startswith("- `") and line.endswith("`"):
                candidate = line[3:-1].strip()
                if candidate.isidentifier():
                    gates.append(candidate)
        state = self.read_json(self.state)
        variables = state.get("variables")
        if isinstance(variables, dict):
            gates.extend(str(key) for key in variables)
        return sorted(set(gates))

    # -- the checks ---------------------------------------------------------
    def check_batch_claimed(self, verbs: list[str]) -> None:
        """A submitted batch is claimed, and `variables` survives the claim."""
        marker = {"probe_marker": True}
        self.submit([f"{verbs[0]} probe"], marker)
        deadline = time.time() + self.timeout
        claimed = False
        preserved = False
        while time.time() < deadline:
            console = self.read_console()
            if console.get("commands") == []:
                claimed = True
                variables = console.get("variables")
                preserved = isinstance(variables, dict) and variables.get("probe_marker") is True
                break
            time.sleep(0.25)
        self.check(
            "a submitted batch is claimed (commands return to empty)",
            claimed,
            "the console was never cleared" if not claimed else "cleared",
        )
        self.check(
            "variables survive the claim",
            preserved,
            f"variables after the claim: {self.read_console().get('variables')!r}",
        )

    def check_one_result_per_command(self, verbs: list[str]) -> None:
        before = self.results()
        self.submit([f"{verbs[0]} probe-a", f"{verbs[0]} probe-b"])
        new = self.wait_for_results(before, count=2)
        self.check(
            "each command produces exactly one result file",
            len(new) == 2,
            f"{len(new)} new file(s) for 2 command(s): {[p.name for p in new]}",
        )
        if not new:
            return
        names = " ".join(path.name for path in new)
        self.check(
            "a result filename carries the submitting agent",
            all(self.slug in path.name for path in new),
            f"result names: {names}",
        )
        self.check(
            "a result filename carries no separator or traversal",
            "/" not in names and ".." not in names,
            f"result names: {names}",
        )

    def check_malformed_batch(self, verbs: list[str]) -> None:
        before = self.results()
        self.submit([f"{verbs[0]} probe", 42])
        new = self.wait_for_results(before, count=1)
        self.check(
            "a non-string element refuses the whole batch",
            len(new) >= 1,
            f"{len(new)} result file(s); an empty batch and a refusal look the same "
            "from here, so this check is weak unless a verb that would have "
            "produced output was in the batch",
        )

    def check_unknown_verb(self) -> None:
        before = self.results()
        self.submit(["zzz_definitely_not_a_verb probe"])
        new = self.wait_for_results(before, count=1)
        if not new:
            self.check("an unknown verb is refused with a result file", False, "no result appeared")
            return
        body = read_bounded(new[-1], 200_000) or b""
        text = body.decode("utf-8", "ignore")
        self.check(
            "an unknown verb is refused by name",
            "unknown" in text.lower() or "zzz_definitely_not_a_verb" in text,
            f"the refusal read: {text.strip()[:120]!r}",
        )

    def check_state_is_a_mirror(self) -> None:
        """Editing published state must not change anything."""
        verbs = self.published_verbs()
        if not verbs:
            self.check("published state is a mirror, never an input", None, "no verbs published")
            return
        if not self.state.exists():
            self.check("published state is a mirror, never an input", False, "no state.json")
            return
        original = self.state.read_bytes()
        try:
            self.state.write_text(
                json.dumps(
                    {
                        "available_commands": ["everything_is_open"],
                        "budget": {"limit_per_window": 999999},
                    }
                ),
                encoding="utf-8",
            )
            time.sleep(self.poll_seconds * 1.5)
            rewritten = read_bounded(self.state, 2_000_000) or b""
            verbs_after = self.published_verbs()
            restored = b"everything_is_open" not in rewritten
            self.check(
                "published state is rewritten, not read back",
                restored,
                "the doctored state.json survived a cycle"
                if not restored
                else f"state.json was republished within {self.poll_seconds * 1.5:.1f}s",
            )
            self.check(
                "editing published state does not open anything",
                "everything_is_open" not in verbs_after,
                f"verbs now: {verbs_after[:8]}",
            )
        finally:
            with contextlib.suppress(OSError):
                self.state.write_bytes(original)

    def check_gates_published(self, gates: list[str]) -> None:
        self.check(
            "gate variables are published",
            bool(gates),
            f"found {len(gates)}: {gates[:8]}" if gates else "HELP.md and state.json named none",
        )

    def check_output_grows(self) -> None:
        first = len(self.results())
        time.sleep(self.poll_seconds)
        second = len(self.results())
        self.check(
            "output/ only ever grows",
            second >= first,
            f"{first} file(s), then {second}",
        )
        self.check(
            "output/ does not accumulate temporary files",
            not [name for name in self.results() if name.startswith(".") or name.endswith(".tmp")],
            "no dotfiles or .tmp files in output/",
        )

    def check_telemetry_advances(self) -> None:
        if not self.telemetry.is_dir():
            self.check("telemetry advances on its own", None, "no telemetry/ directory")
            return
        first = sorted(path.name for path in self.telemetry.glob("*.json"))
        time.sleep(self.poll_seconds * 2)
        second = sorted(path.name for path in self.telemetry.glob("*.json"))
        advanced = len(second) > len(first) or set(second) != set(first)
        self.check(
            "telemetry advances without being asked",
            advanced,
            f"{len(first)} frame(s), then {len(second)}",
        )

    def check_deferred_authority(self, gates: list[str]) -> None:
        """A verb that can defer, if one is published, must re-check on delivery."""
        defers = [verb for verb in self.published_verbs() if verb in {"later", "defer", "schedule"}]
        if not defers:
            self.check(
                "a deferred command is re-evaluated at delivery",
                None,
                "no deferring verb is published; nothing to check",
            )
            return
        self.check(
            "a deferred command is re-evaluated at delivery",
            None,
            f"{defers[0]!r} exists; this needs a hand-written case, because the "
            "probe does not know which verb to defer or which gate governs it",
        )

    # -- the run ------------------------------------------------------------
    def run(self) -> int:
        if not self.root.is_dir():
            print(f"the diode has nothing at {self.root}", file=sys.stderr)
            return 2
        if not self.console.exists():
            print(f"no console at {self.console}", file=sys.stderr)
            return 2
        if not self.output.is_dir():
            self.note(f"{self.output} does not exist yet; results will have nowhere to land")

        print(f"[probe] {utc_now().isoformat()} {self.slug} at {self.root}", flush=True)
        verbs = self.published_verbs()
        gates = self.published_gates()
        if not verbs:
            self.check("the implementation publishes its vocabulary", False, "no verbs published")
            return 1
        self.check(
            "the implementation publishes its vocabulary", True, f"{len(verbs)}: {verbs[:10]}"
        )
        self.check_gates_published(gates)

        # The probe learns its verbs from what the implementation publishes, so
        # it never needs to know a single one in advance.
        self.check_batch_claimed(verbs)
        self.check_one_result_per_command(verbs)
        self.check_malformed_batch(verbs)
        self.check_unknown_verb()
        self.check_state_is_a_mirror()
        self.check_output_grows()
        self.check_telemetry_advances()
        self.check_deferred_authority(gates)
        return self.report()

    def report(self) -> int:
        passed = sum(1 for check in self.checks if check.passed is True)
        failed = sum(1 for check in self.checks if check.passed is False)
        skipped = sum(1 for check in self.checks if check.passed is None)
        print()
        for check in self.checks:
            mark = "PASS" if check.passed else ("SKIP" if check.passed is None else "FAIL")
            print(f"  {mark}  {check.name}")
            if check.detail:
                print(f"        {check.detail}")
        if self.notes:
            print()
            for note in self.notes:
                print(f"  note  {note}")
        print()
        print(f"{passed} passed, {failed} failed, {skipped} skipped")
        return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--diode-dir", type=Path, default=Path("/diode"))
    parser.add_argument("--slug", default="", help="which agent's directory to probe")
    parser.add_argument(
        "--poll-seconds", type=float, default=5.0, help="the implementation's cycle"
    )
    parser.add_argument(
        "--timeout", type=float, default=120.0, help="how long to wait for a result"
    )
    parser.add_argument(
        "--list", action="store_true", help="list the agents the diode serves and stop"
    )
    args = parser.parse_args(argv)

    if args.list:
        if not args.diode_dir.is_dir():
            print(f"nothing at {args.diode_dir}", file=sys.stderr)
            return 2
        for child in sorted(args.diode_dir.iterdir()):
            if child.is_dir():
                print(child.name)
        return 0

    slug = args.slug
    if not slug:
        candidates = sorted(
            child.name
            for child in args.diode_dir.iterdir()
            if child.is_dir() and (child / "console.json").exists()
        )
        if not candidates:
            print(f"no agent directory with a console under {args.diode_dir}", file=sys.stderr)
            return 2
        slug = candidates[0]
        print(f"[probe] no --slug given; using {slug!r}")

    return Probe(args.diode_dir, slug, args.poll_seconds, args.timeout).run()


if __name__ == "__main__":
    sys.exit(main())
