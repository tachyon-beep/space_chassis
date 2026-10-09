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
    r"|tasks/duty\.py|endurance/(run_local|stub_model|inject|report)"
    r"|agent\.env|_load_runtime|DIODE_DUTY_DIR|PUMP_DUTY_DIR"
    r'|SERVICES_DIR\s*/\s*"(chassis|supervisor|recorder|pump)\.py"'
)

NEGATIVE = re.compile(r"\bassert\b.*\bnot in\b")

# Permanent: history and text that is not ours to rewrite yet.
PERMANENT = (
    "tests/test_retired.py",  # this file names what it bans
    "docs/superpowers/",  # the specs and plans: the record of how the port was made
    "docs/deep_research/",  # the frozen corpus (CLAUDE.md: its map is integration/)
    "brief/",  # agent-facing: shipped as is until John approves docs/drafts/ (spec §6, §10.2)
    "harness/system_prompt.txt",  # likewise
    "harness/user_prompt.txt",  # likewise
    "docs/drafts/",  # quotes what the shipped text still says
)

# Temporary: the documents plan 5's Task 5 rewrites. Task 5 empties this.
REWRITTEN_IN_TASK_5 = ("CLAUDE.md", "AGENTS.md", "README.md", "docs/design.md", ".env.example")


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
        if name.startswith(PERMANENT) or name in REWRITTEN_IN_TASK_5:
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
