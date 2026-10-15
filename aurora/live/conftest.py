"""The live suite's stacks: three agents, built and started once for the session, with the contract
fixture as the window; and, for live/test_vehicle.py, the same fleet with the vehicle as the window.

agent_3's recorder is capped at four requests an hour, so it is refused on its fifth call and spends
the run in the watchdog's pause loop (spec 9.7); agent_1 and agent_2 run on the stub at its normal
pace. The stack starts once, every test reads and drives it, and the finalizer copies each
service's log to .scratch/live-evidence/ before `down()` removes the scratch root, so a failed run
leaves its evidence behind. The vehicle's stack replaces the fixture's (one stack at a time), and the
fixture's evidence is kept then.

This directory is not in `testpaths`: a bare `pytest -q` never starts a container.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from probes import postgres_answers  # noqa: E402
from stack import (  # noqa: E402
    CAPS,
    HOST_CPUS,
    HOST_MEMORY,
    HOST_SCOPE_COMMAND,
    REPO,
    STACK_CPUS,
    STACK_MEMORY,
    SmokeStack,
    effective_limits,
    memory_bytes,
    own_cgroup,
    wait_for,
)

EVIDENCE = REPO / ".scratch" / "live-evidence"
START_SECONDS = 300
TRANSCRIPT_HEAD_BYTES = 2 << 20


def pytest_collection_modifyitems(items):
    """Containment first: it describes the stack as it started, before any test breaks an agent.
    The vehicle's last: its stack replaces the fixture's (one stack at a time), so every test of
    the fixture's stack runs before it goes."""
    order = {"test_containment.py": 0, "test_vehicle.py": 2}
    items.sort(key=lambda item: order.get(item.path.name, 1))


# The stacks this session started. Starting one takes down any other first, keeping its evidence:
# Governance's budget (2026-10-11) is one smoke stack at a time, and SmokeStack.start refuses to
# start beside another smoke project anyway.
_UP: list[SmokeStack] = []


def _only(smoke: SmokeStack) -> None:
    for other in _UP:
        try:
            if (other.root / "override.yml").exists():
                _keep_evidence(other)
        finally:
            other.down()
    _UP[:] = [smoke]


def _assert_inside_the_host_scope() -> None:
    """pytest and the docker clients it runs are the host side of the live run's budget: this
    process must be in a cgroup that caps them -- itself or an ancestor, read from the kernel, not
    taken on trust -- with no swap past the memory cap.

    The budget is the shared host's. A GitHub Actions runner (the manual live-stack workflow) is a
    disposable machine of its own, with no user systemd to make the scope, so the host-side check
    is the one thing it skips; every container's own caps are still read and held."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return
    cpus, memory, swap = effective_limits(own_cgroup())
    inside = 0 < cpus <= HOST_CPUS + 1e-9 and 0 < memory <= HOST_MEMORY and swap == 0
    assert inside, (
        f"the live run must be inside a capped user scope (this one: {cpus} CPUs, {memory} bytes, "
        f"swap {swap}); "
        f"run it as: {HOST_SCOPE_COMMAND}"
    )


def _keep_evidence(smoke: SmokeStack) -> None:
    # The vehicle stack's evidence beside the fixture stack's, never over it.
    evidence = EVIDENCE if smoke.window == "diode" else EVIDENCE / smoke.window
    evidence.mkdir(parents=True, exist_ok=True)
    services = ["stub", smoke.window]
    for n in range(1, smoke.agents + 1):
        services += [f"agent_{n}", f"recorder_{n}"]
    for service in services:
        result = smoke.compose("logs", "--no-color", "--timestamps", service, check=False)
        (evidence / f"{service}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    # The head of each transcript, for fixtures: bodies only, never a header, and a dummy key.
    for n in range(1, smoke.agents + 1):
        source = smoke.volumes / f"transcripts_agent_{n}" / "data" / "agent_life_transcript.jsonl"
        try:
            with open(source, "rb") as handle:
                head = handle.read(TRANSCRIPT_HEAD_BYTES)
        except OSError:
            continue
        (evidence / f"transcript_agent_{n}.jsonl").write_bytes(head)
    ps = smoke.compose("ps", "--all", check=False)
    (evidence / "ps.txt").write_text(ps.stdout + ps.stderr, encoding="utf-8")


def _assert_within_budget(smoke: SmokeStack) -> None:
    """What the kernel enforces, read from each container's cgroup, not what compose was asked:
    every service capped, no swap past its memory, its cap the one assigned, the sum in budget."""
    caps = smoke.enforced_caps()
    for service, (cpus, memory, swap) in caps.items():
        kind = service.rsplit("_", 1)[0] if service[-1].isdigit() else service
        kind = "window" if kind in ("diode", "vehicle") else kind
        want_cpus, want_memory = CAPS[kind]
        want_bytes = memory_bytes(want_memory)
        assert cpus == float(want_cpus), f"{service} enforces {cpus} CPUs, not {want_cpus}"
        assert memory == want_bytes, f"{service} enforces {memory} bytes, not {want_memory}"
        assert swap == 0, f"{service} may swap {swap} bytes past its memory limit"
    assert sum(c for c, _, _ in caps.values()) <= STACK_CPUS + 1e-9, caps
    assert sum(m for _, m, _ in caps.values()) <= STACK_MEMORY, caps


def _started(smoke: SmokeStack) -> None:
    _assert_inside_the_host_scope()
    _only(smoke)
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
    _assert_within_budget(smoke)


@pytest.fixture(scope="session")
def stack():
    smoke = SmokeStack(3, recorder_overrides={3: {"RECORDER_HOURLY_MAX": "4"}})
    try:
        _started(smoke)
        yield smoke
    finally:
        if (smoke.root / "override.yml").exists():
            _keep_evidence(smoke)
        smoke.down()


@pytest.fixture(scope="session")
def vehicle_stack():
    """The same fleet with the vehicle as its window: its own project, scratch root and /state."""
    smoke = SmokeStack(3, window="vehicle")
    try:
        _started(smoke)
        yield smoke
    finally:
        if (smoke.root / "override.yml").exists():
            _keep_evidence(smoke)
        smoke.down()
