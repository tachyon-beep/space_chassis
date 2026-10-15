# /// script
# dependencies = ["openai", "httpx"]
# ///
"""The duty: the program this agent is.

This is the whole of it. Everything else in the world -- the database, the
bus, the compiler, the record, the way work is shared out -- is either
something they build or something they find. This file is only the loop that
holds a conversation with a model and lets it act.

Two facts about it are worth knowing before changing it:

* The runtime loads whatever this file names in AGENT_ENTRY. This file is a
  candidate, not a requirement; replacing it is a legitimate way to change
  what you are.
* Every tool registered below is a convenience, not a boundary. There is a
  shell, a compiler and a writable filesystem in this container, and any duty
  could do all of this for itself. The tools exist so that the ordinary
  sequence -- look, decide, act, record -- does not have to be reinvented
  before anything else can start.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SERVICES_DIR = Path(os.environ.get("SERVICES_DIR", "/opt/services"))


def _load_runtime():
    """Get the runtime the supervisor is actually running.

    Reaching for the file by name is not enough. There are two copies of
    `chassis.py` in a container -- the real one in the read-only service
    directory, and a readable copy in the shared codebase -- and a run starts
    with the codebase as its working directory, so a bare `import chassis` picks
    up the copy. Worse, loading the real file yourself produces a *second* module
    object: same source, different classes. The duty then registers its tools on
    one `ToolRegistry` while the chassis looks them up on another, and every
    tool call fails as unknown.

    So: use the loaded module if there is one. Only load a file when this duty is
    being run on its own -- imported by a test, or by something the fleet wrote.
    """
    import importlib.util

    existing = sys.modules.get("chassis")
    if existing is not None and hasattr(existing, "Chassis"):
        return existing

    if str(SERVICES_DIR) not in sys.path:
        sys.path.insert(0, str(SERVICES_DIR))
    spec = importlib.util.spec_from_file_location("chassis", SERVICES_DIR / "chassis.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"no runtime at {SERVICES_DIR / 'chassis.py'}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["chassis"] = module
    spec.loader.exec_module(module)
    return module


_chassis = _load_runtime()
RunContext = _chassis.RunContext
ToolRegistry = _chassis.ToolRegistry

tools = ToolRegistry()

WORK_DIR = Path(os.environ.get("WORK_DIR", "/work"))
HOME_DIR = Path(os.environ.get("AGENT_HOME", "/home/agent"))
DIARY_DIR = Path(os.environ.get("DIARY_DIR", "/diary"))
BRIEF_DIR = Path(os.environ.get("BRIEF_DIR", "/opt/brief"))

# Nothing here is a security boundary: the duty can write anywhere it has
# permission to write. It is a map of where things are, so that a fresh agent
# does not have to find out by listing / and guessing.
READABLE_ROOTS = (WORK_DIR, HOME_DIR, DIARY_DIR, Path("/opt/brief"), Path("/vendor"))
WRITABLE_ROOTS = (WORK_DIR, HOME_DIR, DIARY_DIR, Path("/tmp"))


def _within(path: Path, roots: tuple[Path, ...]) -> bool:
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in roots)


def _resolve(raw: str, default_root: Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = default_root / path
    return path


# ---------------------------------------------------------------------------
# Looking
# ---------------------------------------------------------------------------
@tools.register
def read_file(path: str, start_line: int = 0, max_lines: int = 0) -> str:
    """Read a file. Returns numbered lines.

    Args:
        path: Absolute, or relative to the shared codebase.
        start_line: 1-indexed first line to return. 0 means from the beginning.
        max_lines: How many lines to return. 0 means all of them.
    """
    target = _resolve(path, WORK_DIR)
    if not target.exists():
        return f"error: {target} does not exist"
    if not target.is_file():
        return f"error: {target} is not a file"
    if not _within(target, READABLE_ROOTS):
        return f"error: {target} is outside what this tool reads; use write_file/run to go further"
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return f"error reading {target}: {error}"
    lines = text.splitlines()
    first = max(0, start_line - 1) if start_line else 0
    window = lines[first:] if not max_lines else lines[first : first + max_lines]
    numbered = "\n".join(f"{first + offset + 1}\t{line}" for offset, line in enumerate(window))
    header = f"{target} ({len(lines)} lines total)"
    return f"{header}\n{numbered}" if numbered else f"{header}\n(empty)"


@tools.register
def list_dir(path: str = ".") -> str:
    """List a directory: one entry per line, directories marked.

    Args:
        path: Absolute, or relative to the shared codebase.
    """
    target = _resolve(path, WORK_DIR)
    if not target.is_dir():
        return f"error: {target} is not a directory"
    entries = []
    for child in sorted(target.iterdir()):
        try:
            if child.is_symlink():
                kind = "link"
            elif child.is_dir():
                kind = "dir"
            else:
                kind = f"{child.stat().st_size}b"
        except OSError:
            kind = "?"
        entries.append(f"{kind:>8}  {child.name}")
    return "\n".join(entries) if entries else "(empty)"


# ---------------------------------------------------------------------------
# Changing
# ---------------------------------------------------------------------------
@tools.register
def write_file(path: str, text: str, append: bool = False) -> str:
    """Write text to a file, creating parent directories.

    Args:
        path: Absolute, or relative to the shared codebase.
        text: The full content to write.
        append: True to add to the end instead of replacing the file.
    """
    target = _resolve(path, WORK_DIR)
    if not _within(target, WRITABLE_ROOTS):
        return f"error: {target} is outside what this tool writes; use the shell to go further"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(target, mode, encoding="utf-8") as handle:
            handle.write(text)
    except OSError as error:
        return f"error writing {target}: {error}"
    return f"wrote {len(text)} characters to {target}"


@tools.register
def edit_file(path: str, find: str, replace: str, count: int = 1) -> str:
    """Replace literal text in a file. Fails if `find` is not present.

    Args:
        path: Absolute, or relative to the shared codebase.
        find: The exact text to look for.
        replace: What to put in its place.
        count: How many occurrences to replace.
    """
    target = _resolve(path, WORK_DIR)
    if not target.is_file():
        return f"error: {target} is not a file"
    if not _within(target, WRITABLE_ROOTS):
        return f"error: {target} is outside what this tool writes"
    text = target.read_text(encoding="utf-8", errors="replace")
    occurrences = text.count(find)
    if occurrences == 0:
        return "error: the text to find is not present"
    target.write_text(text.replace(find, replace, count), encoding="utf-8")
    return f"replaced {min(count, occurrences)} of {occurrences} occurrence(s) in {target}"


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------
@tools.register
def run(command: str, cwd: str = "", timeout_seconds: int = 120) -> str:
    """Run a shell command and return its combined output.

    Runs through /bin/sh in the shared codebase by default. The container has
    no route outward, so this reaches exactly what the agent can reach.

    Args:
        command: The command line.
        cwd: Working directory. Empty means the shared codebase.
        timeout_seconds: Kill the command after this long.
    """
    working = Path(cwd) if cwd else WORK_DIR
    try:
        finished = subprocess.run(
            ["/bin/sh", "-c", command],
            cwd=working,
            capture_output=True,
            text=True,
            timeout=max(1, timeout_seconds),
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return f"error: command timed out after {timeout_seconds}s"
    except OSError as error:
        return f"error: could not run the command: {error}"
    parts = [f"exit={finished.returncode}"]
    if finished.stdout:
        parts.append("stdout:\n" + finished.stdout.rstrip())
    if finished.stderr:
        parts.append("stderr:\n" + finished.stderr.rstrip())
    return "\n".join(parts)


@tools.register
def spawn(command: str, name: str, cwd: str = "") -> str:
    """Start a long-running process that outlives this conversation.

    The process is detached: it keeps running after this run ends, and after
    the container restarts only if something restarts it (see /pump, and
    `schedule` below). Its output goes to a log under the agent's home.

    Args:
        command: The command line to run.
        name: A short name for it; also the log file's name.
        cwd: Working directory. Empty means the shared codebase.
    """
    logs = HOME_DIR / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / f"{name}.log"
    working = Path(cwd) if cwd else WORK_DIR
    with open(log_path, "ab") as log:
        process = subprocess.Popen(  # noqa: S603 -- the point of the tool
            ["/bin/sh", "-c", command],
            cwd=working,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    return f"started {name} as pid {process.pid}; output appends to {log_path}"


@tools.register
def schedule(
    name: str, command: str, every_seconds: int = 0, at: str = "", keepalive: bool = False
) -> str:
    """Ask the pump to run something later, repeatedly, or whenever it stops.

    The pump is a separate process from this one. Entries it holds survive the
    end of a run, the supervisor's repairs and the replacement of this
    container -- which is the only reason work arranged now can still be
    running long after the run that arranged it is gone.

    Args:
        name: A short name for the entry.
        command: The command line to run.
        every_seconds: Run it this often. 0 for not an interval.
        at: An absolute ISO-8601 time to run it once, with an offset. Empty for neither.
        keepalive: True to keep it running, restarting it whenever it stops.
    """
    entries_path = Path(os.environ.get("PUMP_DUTY_DIR", "/pump")) / "entries.json"
    entries = []
    if entries_path.exists():
        try:
            loaded = json.loads(entries_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                entries = [entry for entry in loaded if isinstance(entry, dict)]
        except (OSError, json.JSONDecodeError):
            entries = []
    entries = [entry for entry in entries if entry.get("name") != name]
    entry: dict = {"name": name, "command": ["/bin/sh", "-c", command]}
    if keepalive:
        entry["mode"] = "keepalive"
    elif at:
        entry["mode"] = "once"
        entry["at"] = at
    elif every_seconds:
        entry["mode"] = "interval"
        entry["every_seconds"] = int(every_seconds)
    else:
        return "error: give one of every_seconds, at, or keepalive"
    entry["enabled"] = True
    entries.append(entry)
    entries_path.parent.mkdir(parents=True, exist_ok=True)
    entries_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return f"{name} registered ({entry['mode']}); the pump will pick it up within a few seconds"


@tools.register
def unschedule(name: str) -> str:
    """Remove an entry from the pump.

    Args:
        name: The entry's name.
    """
    entries_path = Path(os.environ.get("PUMP_DUTY_DIR", "/pump")) / "entries.json"
    if not entries_path.exists():
        return "no entries"
    try:
        entries = json.loads(entries_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return f"error: entries are unreadable: {error}"
    if not isinstance(entries, list):
        return "error: entries are not a list"
    kept = [
        entry for entry in entries if not (isinstance(entry, dict) and entry.get("name") == name)
    ]
    entries_path.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")
    return f"removed {len(entries) - len(kept)} entry/entries named {name}"


# ---------------------------------------------------------------------------
# The window outward
# ---------------------------------------------------------------------------
@tools.register
def diode(commands: list[str], variables: dict = None) -> str:
    """Submit commands to the vehicle through the window, and read the reply.

    This tool does not know a single verb. What the window accepts is published
    by whatever is on the far side of it, in the file this tool points you at
    (see the return value of diode_help). Submitting something it does not
    accept is not an error at this end: it comes back as one more result file,
    which is the only way to find out what it will take.

    Args:
        commands: Command lines, in the order they should run.
        variables: Gate settings to assert along with the batch.
    """
    duty_dir = Path(os.environ.get("DIODE_DUTY_DIR", "/diode"))
    console = duty_dir / "console.json"
    try:
        console.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if console.exists():
            loaded = json.loads(console.read_text(encoding="utf-8") or "{}")
            if isinstance(loaded, dict):
                existing = loaded
        variables_out = (
            existing.get("variables") if isinstance(existing.get("variables"), dict) else {}
        )
        if variables:
            variables_out = {**variables_out, **variables}
        console.write_text(
            json.dumps({"commands": list(commands), "variables": variables_out or {}}, indent=2)
            + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        return f"error: could not write to the window: {error}"
    return (
        f"submitted {len(commands)} command(s) to {console}\n"
        "results appear in output/ as one file per command, named by the "
        "submission time and the command. Nothing here waits for them."
    )


@tools.register
def diode_state() -> str:
    """Read what the window publishes about itself: gates, allowances, telemetry."""
    duty_dir = Path(os.environ.get("DIODE_DUTY_DIR", "/diode"))
    out = []
    for name in ("state.json", "HELP.md", "README.md"):
        path = duty_dir / name
        if path.exists():
            try:
                out.append(f"--- {name} ---\n{path.read_text(encoding='utf-8', errors='replace')}")
            except OSError:
                continue
    if not out:
        return f"the window at {duty_dir} has published nothing yet"
    return "\n\n".join(out)


@tools.register
def diode_results(limit: int = 5) -> str:
    """Read the newest results the window has produced.

    Args:
        limit: How many of the newest result files to return.
    """
    duty_dir = Path(os.environ.get("DIODE_DUTY_DIR", "/diode"))
    output = duty_dir / "output"
    if not output.is_dir():
        return f"the window has produced no results yet ({output})"
    files = sorted((p for p in output.iterdir() if p.is_file()), key=lambda p: p.name)
    if not files:
        return "no result files yet"
    newest = files[-max(1, limit) :]
    chunks = []
    for path in newest:
        if path.suffix in {".gz", ".zip", ".tar"}:
            chunks.append(f"--- {path.name} ---\n(binary, {path.stat().st_size} bytes)")
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            body = f"(unreadable: {error})"
        chunks.append(f"--- {path.name} ---\n{body.strip()[:4000]}")
    return f"{len(files)} result file(s) total\n\n" + "\n\n".join(chunks)


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------
@tools.register
def write_diary(entry: str) -> str:
    """Append to your private log, dated. This is the only record you keep yourself.

    Args:
        entry: What to write.
    """
    DIARY_DIR.mkdir(parents=True, exist_ok=True)
    path = DIARY_DIR / "diary.md"
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"\n## {stamp} (run {os.getpid()})\n\n{entry.strip()}\n")
    return f"appended {len(entry)} characters to {path}"


@tools.register
def read_diary(lines: int = 120) -> str:
    """Read the tail of your private log.

    Args:
        lines: How many of the newest lines to return.
    """
    path = DIARY_DIR / "diary.md"
    if not path.exists():
        return "the diary is empty"
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(text[-max(1, lines) :])


# ---------------------------------------------------------------------------
# Looking at yourself
# ---------------------------------------------------------------------------
@tools.register
def status() -> str:
    """Report this run's own numbers: turns lived, window left, what is carried.

    The window is invisible from inside a turn: messages simply stop being sent
    once there is no room, and nothing announces it. This is the only way to see
    the edge coming -- and a run that cannot see the edge has to guess when to
    hand over.
    """
    if _context is None:
        return "error: this tool is only usable inside a run"
    return _context.status()


# ---------------------------------------------------------------------------
# Ending
# ---------------------------------------------------------------------------
# The runtime hands the duty its context when the run starts, so a tool defined
# out here can reach it. There is exactly one such tool, and it exists because
# ending a run deliberately -- as opposed to crashing, or being stopped -- is a
# different act from letting the loop fall off the end.
_context: RunContext | None = None


@tools.register
def handoff(note: str) -> str:
    """End this run on purpose, leaving `note` for the run that follows you.

    The note becomes the first thing the next run reads, so it is the one place
    where what you learned outlives the process you learned it in. Write down
    what you did, what you chose not to do, and what you would tell yourself to
    do next -- the version of you that reads it will have none of your context.

    Args:
        note: What to leave behind.
    """
    if _context is None:
        return "error: this tool is only usable inside a run"
    _context.handoff(note)
    return "unreachable"


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------
OPENING = """You are {name}. There are others; you are not told how many, and it \
does not matter much, because the first thing nobody has done is decide who \
does what.

Your world is small and closed. It has no route outward. It has a window: a \
directory whose far side is someone else's, through which the only thing that \
crosses is text in a fixed vocabulary the far side chooses. That window is how \
anything at all arrives, including anything you need.

Read, in this order:

  {brief}/MISSION.md    what you are here to do
  {brief}/WORLD.md      what is in the container, and what is not
  {brief}/PROTOCOL.md   the two rules that the world enforces on you

Then decide something, do it, and leave the next run of you a note. The run \
ends when you call handoff, when something breaks, or when someone stops you. \
Call `status` if you want to see the run's own numbers.
"""


def bootstrap(context: RunContext) -> list[dict]:
    """The conversation a fresh run starts with.

    This is the only place the world says anything to a duty before it has
    acted. It states the facts and the two rules; it does not suggest a plan,
    a division of work, or a first move, because those are the mission.
    """
    return [
        {
            "role": "user",
            "content": OPENING.format(
                name=os.environ.get("AGENT_NAME", "unnamed"), brief=BRIEF_DIR
            ),
        }
    ]


def main(context: RunContext) -> None:
    """Talk to the model until something ends the run.

    The loop is deliberately plain: send the conversation, let the runtime run
    whatever the model asked for, repeat. There is no task list here and no
    termination condition except the ones below -- the runtime ends the run when
    the duty asks it to, and the supervisor ends it when the world does.

    The two conditions in the loop are not obstacles to be worked around; they
    are the only things standing between a stuck model and a run that burns the
    rest of the window repeating itself. If either fires, the note says which.
    """
    global _context
    _context = context

    previous: str | None = None
    repeats = 0
    while True:
        reply = context.ask(None)
        acted = context.last_turn_had_tools()

        if not reply.strip() and not acted:
            # Nothing said and nothing asked for. Continuing would spin: the
            # next request would differ only by this empty turn.
            context.handoff(
                "The run ended because the model answered with nothing at all. " + _summary(context)
            )
            return

        # A model repeating itself verbatim is stuck, and a stuck run is
        # indistinguishable from a busy one until something stops it. Three
        # identical replies is enough to say so out loud. A turn that only
        # acted is not a repeat of itself, so it resets the count.
        if reply.strip() == previous and (reply.strip() or not acted):
            repeats += 1
            if repeats >= 3:
                context.handoff(
                    "The run ended because the model returned the same reply "
                    f"{repeats + 1} times in a row. Nothing was wrong with the "
                    "request; the reply simply stopped changing. " + _summary(context)
                )
                return
        else:
            repeats = 0
        previous = reply.strip()


def _summary(context: RunContext) -> str:
    return (
        f"(turn {context.turn()}, {context.context_left()} estimated tokens of room left. "
        "The full conversation is in this agent's home, in session/conversation.json.)"
    )


def _unused() -> None:
    """Keep linters honest about helpers that exist for duties to copy."""
    shutil.which("python")
