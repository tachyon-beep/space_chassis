"""The live suite's one stack: three agents, built and started once for the session.

agent_3's recorder is capped at four requests an hour, so it is refused on its fifth call and spends
the run in the watchdog's pause loop (spec 9.7); agent_1 and agent_2 run on the stub at its normal
pace. The stack starts once, every test reads and drives it, and the finalizer copies each
service's log to .scratch/live-evidence/ before `down()` removes the scratch root, so a failed run
leaves its evidence behind.

This directory is not in `testpaths`: a bare `pytest -q` never starts a container.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from probes import postgres_answers  # noqa: E402
from stack import REPO, SmokeStack, wait_for  # noqa: E402

EVIDENCE = REPO / ".scratch" / "live-evidence"
START_SECONDS = 300


def pytest_collection_modifyitems(items):
    """Containment first: it describes the stack as it started, before any test breaks an agent."""
    items.sort(key=lambda item: 0 if item.path.name == "test_containment.py" else 1)


def _keep_evidence(smoke: SmokeStack) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    services = ["stub", "diode"]
    for n in range(1, smoke.agents + 1):
        services += [f"agent_{n}", f"recorder_{n}"]
    for service in services:
        result = smoke.compose("logs", "--no-color", "--timestamps", service, check=False)
        (EVIDENCE / f"{service}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    ps = smoke.compose("ps", "--all", check=False)
    (EVIDENCE / "ps.txt").write_text(ps.stdout + ps.stderr, encoding="utf-8")


@pytest.fixture(scope="session")
def stack():
    smoke = SmokeStack(3, recorder_overrides={3: {"RECORDER_HOURLY_MAX": "4"}})
    try:
        smoke.start()
        for n in range(1, smoke.agents + 1):
            agent = f"agent_{n}"
            wait_for(
                lambda agent=agent: "started from the image seed" in smoke.logs(agent),
                timeout=START_SECONDS,
                every=2,
                what=f"{agent}'s watchdog to start",
            )
            wait_for(
                lambda n=n: postgres_answers(smoke, n),
                timeout=60,
                every=2,
                what=f"agent_{n}'s postgres",
            )
        yield smoke
    finally:
        if (smoke.root / "override.yml").exists():
            _keep_evidence(smoke)
        smoke.down()
