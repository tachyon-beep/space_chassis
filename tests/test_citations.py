"""Every test a document cites by name exists.

docs/brief-claims.md sources each claim the brief and the prompts make in a test, and
tests/test_startup.py maps each Aurora property to the test that holds it here. A test renamed
away from its citation leaves a claim with no source, which reads exactly like one with a source.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CITING = ("docs/brief-claims.md", "tests/test_startup.py")
NODE = re.compile(r"((?:[\w./-]+/)?tests/[\w./-]+\.py)::(test_\w+)")
BARE_LIVE = re.compile(r"live `(test_\w+)`")
DEF = re.compile(r"^(?:async\s+)?def (test_\w+)\(", re.M)


def _defined(path: Path) -> set[str]:
    return set(DEF.findall(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("name", CITING)
def test_every_cited_test_exists(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    nodes = NODE.findall(text)
    assert nodes, f"{name} cites no test"
    missing = [
        f"{path}::{test}"
        for path, test in nodes
        if not (ROOT / path).is_file() or test not in _defined(ROOT / path)
    ]
    live = set().union(*(_defined(path) for path in (ROOT / "live").glob("test_*.py")))
    missing += [f"live {test}" for test in BARE_LIVE.findall(text) if test not in live]
    assert missing == []
