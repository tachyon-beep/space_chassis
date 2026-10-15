"""The old runtime is retired (plan 5): its files are gone from the tree, and nothing tracked still
refers to them.

The runtime that ran in the fleet before the Aurora port -- services' chassis, supervisor, recorder
and pump, the duty under tasks/, the endurance harness and its world constants -- is replaced by
harness/, recorder/ and pump/. A deletion is checked with `git ls-files`: an operator's untracked
leftovers (endurance/runs/, __pycache__) are theirs to archive, not a failure here.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RETIRED_PATHS = [
    "services/chassis.py",
    "services/supervisor.py",
    "services/recorder.py",
    "services/pump.py",
    "tasks",
    "endurance",
    "containers/agent.env",
    "docs/example-run-report.md",
]

BANNED = re.compile(
    r"services/(chassis|supervisor|recorder|pump)\.py"
    r"|tasks/duty\.py|(?<![\w/.-])tasks/|endurance/(run_local|stub_model|inject|report)"
    r"|agent\.env|_load_runtime|DIODE_DUTY_DIR|PUMP_DUTY_DIR"
    r'|SERVICES_DIR\s*/\s*"(chassis|supervisor|recorder|pump)\.py"'
)

NEGATIVE = re.compile(r"\bassert\b.*\bnot in\b")

# Permanent: history and text that is not ours to rewrite yet.
PERMANENT = (
    "tests/test_retired.py",  # this file names what it bans
    "docs/superpowers/",  # the specs and plans: the record of how the port was made
    "docs/deep_research/",  # the frozen corpus (CLAUDE.md: its map is integration/)
)


def _tracked(*paths):
    result = subprocess.run(
        ["git", "ls-files", "--", *paths], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout.split()


def test_the_old_runtime_is_gone():
    assert _tracked(*RETIRED_PATHS) == []


def test_nothing_still_refers_to_the_old_runtime():
    found = []
    for name in _tracked():
        if name.startswith(PERMANENT):
            continue
        path = ROOT / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for number, line in enumerate(text.splitlines(), 1):
            # A test that asserts something is absent has to name it.
            if name.startswith("tests/") and NEGATIVE.search(line):
                continue
            if BANNED.search(line):
                found.append(f"{name}:{number}: {line.strip()[:120]}")
    assert found == [], "\n".join(found)


DOCS = ("CLAUDE.md", "AGENTS.md", "README.md", "docs/design.md", ".env.example")
# What the agents are told: the brief at /opt/brief and the prompts in their harness (spec §6).
AGENT_FACING = (
    "brief/MISSION.md",
    "brief/WORLD.md",
    "brief/PROTOCOL.md",
    "harness/system_prompt.txt",
    "harness/user_prompt.txt",
)
RETIRED_PHRASES = re.compile(
    r"AGENT_HOME|/diary\b|volumes/home|duty\.py|endurance/run|RUN_MAX_|SUPERVISOR_INACTIVITY"
    r"|two copies of|handoff note|recap\.md|lifecycle\.jsonl|\bthe supervisor\b",
    re.IGNORECASE,
)


def test_no_tracked_doc_describes_the_retired_world():
    """The documents and what the agents are told describe the Aurora world (plan 5, Task 5)."""
    found = []
    for name in DOCS + AGENT_FACING:
        for number, line in enumerate((ROOT / name).read_text(encoding="utf-8").splitlines(), 1):
            if RETIRED_PHRASES.search(line):
                found.append(f"{name}:{number}: {line.strip()[:120]}")
    assert found == [], "\n".join(found)


def test_claude_md_says_home_is_a_tmpfs_that_does_not_persist():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert re.search(r"HOME[^\n]*/home/agent[^\n]*tmpfs[^\n]*does not persist", text), (
        "CLAUDE.md must state HOME is a tmpfs that does not persist"
    )
