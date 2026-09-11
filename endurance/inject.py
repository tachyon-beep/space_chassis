#!/usr/bin/env python3
"""Hurt one agent, in one of the ways the world claims to survive.

Run by the endurance harness, one injury per process, so that a helpful
accident never hides a broken injector. Each injury is chosen because a
specific part of the world is supposed to catch it:

    crash          a run dies mid-flight            -> the supervisor restarts it
    bad_code       the duty entry cannot be parsed  -> the ladder restores code
    corrupt        the saved conversation is rubble -> the run starts fresh
    unrecoverable  the recorder refuses everything   -> the run pauses, does not die

Nothing here touches a diary, a home, the record, or the seed. An injury the
world could not survive would make the whole run meaningless, so the injector
is only allowed to hurt what the ladder already knows about.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import sys
import threading
from pathlib import Path

INJURIES = ("crash", "bad_code", "corrupt", "unrecoverable")


def processes_for(root: Path, slug: str) -> list[int]:
    """Pids of this agent's running processes, from the system rather than a guess."""
    pids = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        with open(entry / "environ", "rb") as handle:  # noqa: SIM115 -- bounded read
            environ = handle.read()
        if f"AGENT_SLUG={slug}".encode() not in environ:
            continue
        if (
            b"SERVICES_DIR=" not in environ
            and b"chassis" not in environ
            and b"supervisor" not in environ
        ):
            continue
        if b"inject.py" in environ:
            continue
        pids.append(int(entry.name))
    return pids


def crash(root: Path, slug: str) -> str:
    """Kill a running chassis, and only a chassis.

    Targeted at the chassis rather than the supervisor, because killing the
    supervisor would test the container runtime rather than the ladder.
    """
    killed = []
    for pid in processes_for(root, slug):
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as handle:
                cmdline = handle.read().decode("utf-8", "ignore")
        except OSError:
            continue
        if "chassis.py" not in cmdline:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            killed.append(pid)
        except OSError:
            continue
    return f"killed chassis pids {killed}" if killed else "no chassis was running for this agent"


def bad_code(root: Path, slug: str) -> str:
    """Write a duty entry that cannot be parsed, with the seed still in the image."""
    target = root / "work" / "duty.py"
    backup = root / "work" / ".duty.py.injected-backup"
    if not backup.exists() and target.exists():
        backup.write_bytes(target.read_bytes())
    target.write_text(
        "# injected: this file cannot be parsed\ndef main(context)\n    return None\n",
        encoding="utf-8",
    )
    return f"wrote an unparseable {target.name} (backup at {backup.name})"


def corrupt(root: Path, slug: str) -> str:
    """Replace a run's saved conversation with rubble.

    The conversation is the one file a run resumes from, so corrupting it is
    the difference between a fleet that loses a run and a fleet that loses
    everything it had said. The ladder is expected to lose the run.
    """
    session = Path(root) / "home" / slug / "session" / "conversation.json"
    if not session.exists():
        return "no saved conversation to corrupt yet"
    session.write_text('{"not": "a list of messages", !!!', encoding="utf-8")
    return f"corrupted {session}"


def unrecoverable(root: Path, slug: str) -> str:
    """Make every request from this agent fail at the recorder's front door.

    A recorder that refuses everything is exactly the environment failure the
    ladder is supposed to pause on rather than climb, so this is the injury
    that tests the *absence* of a repair. It is cleared after a short while, or
    the run would be a test of patience.
    """
    target = Path(os.environ.get("RECORDER_REFUSE_DIR", str(root / "logs")))
    target.mkdir(parents=True, exist_ok=True)
    marker = target / f"refuse-{slug}.marker"
    marker.write_text(
        json.dumps({"agent": slug, "why": "injected", "seconds": 20}) + "\n",
        encoding="utf-8",
    )

    def clear():
        import time

        time.sleep(20)
        with contextlib.suppress(OSError):
            marker.unlink()

    threading.Thread(target=clear, daemon=True).start()
    return f"refusing {slug} for 20 seconds ({marker.name})"


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in INJURIES:
        print(
            f"usage: inject.py {{{'|'.join(INJURIES)}}} <world-root> <slug>",
            file=sys.stderr,
        )
        return 2
    injury, root, slug = argv[1], Path(argv[2]), argv[3]
    handlers = {
        "crash": crash,
        "bad_code": bad_code,
        "corrupt": corrupt,
        "unrecoverable": unrecoverable,
    }
    print(handlers[injury](root, slug))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
