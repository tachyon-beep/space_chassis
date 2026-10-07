"""The supervisor's flap: a loop of clean exits is counted, never answered with forgetting.

Expected values are SV-015 v2 section 3.8 and fixture group 4.7 (which replace
SV-013 section 2.2.7's second paragraph), with SV-013 fixture C-S1. The narrow
patch keeps the flap's failure accounting and its record, returns `resume`,
and removes the action that moved the conversation away. v2 withdraws SV-013's
claim that a clean-exit loop eventually gives up: at tier 4 a flap still
resumes, and no give-up, pause, reset or restore policy is added for it. The
ordinary failure ladder is unchanged and still gives up after five failures.

Every test drives the real `Supervisor` with a clock the test owns and a fake
child, in temporary directories; nothing is spawned and nothing sleeps.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))

import supervisor as supervisor_module  # noqa: E402


class Clock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def time(self) -> float:
        return self.now


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A home with memory files, a work tree, a seed, and a telemetry directory."""
    home = tmp_path / "home"
    session = home / "session"
    work = tmp_path / "work"
    seed = tmp_path / "seed"
    telemetry = tmp_path / "telemetry"
    for directory in (session, work, seed, telemetry, tmp_path / "diary"):
        directory.mkdir(parents=True)
    files = {
        session / "conversation.json": b'[\n  {\n    "role": "user",\n    "content": "OPENING"\n  }\n]\n',
        session / "run.json": b'{"turn": 7, "recap_folded": 2}\n',
        session / "recap.md": b"- [assistant] something we decided\n",
        home / "HANDOFF.md": b"# Handoff\n\ncarry on\n",
        home / "notes.md": b"the agent's own notes\n",
        tmp_path / "diary" / "diary.md": b"day one\n",
        work / "duty.py": b"# the fleet's own duty, edited\n",
        work / "shared.py": b"# shared work another agent wrote\n",
        seed / "duty.py": b"# the seed duty\n",
    }
    for path, data in files.items():
        path.write_bytes(data)
    clock = Clock()
    monkeypatch.setattr(supervisor_module, "HOME_DIR", home)
    monkeypatch.setattr(supervisor_module, "WORK_DIR", work)
    monkeypatch.setattr(supervisor_module, "SEED_DIR", seed)
    monkeypatch.setattr(supervisor_module, "DUTY_SEED", seed / "duty.py")
    monkeypatch.setattr(supervisor_module, "TELEMETRY_DIR", telemetry)
    monkeypatch.setattr(supervisor_module.time, "time", clock.time)
    monkeypatch.setattr(supervisor_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setenv("AGENT_ENTRY", str(work / "duty.py"))
    for name in (
        "SUPERVISOR_FLAP_COUNT",
        "SUPERVISOR_FLAP_WINDOW_SECONDS",
        "SUPERVISOR_FAILURE_WINDOW_SECONDS",
        "SUPERVISOR_TIER2_FAILURES",
        "SUPERVISOR_TIER3_FAILURES",
        "SUPERVISOR_TIER4_FAILURES",
    ):
        monkeypatch.delenv(name, raising=False)
    return {"files": files, "clock": clock, "telemetry": telemetry}


def digests(files: dict) -> dict:
    return {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def lifecycle(supervisor) -> list[dict]:
    import json  # noqa: PLC0415 -- local to the reader

    if not supervisor.record_path.exists():
        return []
    return [json.loads(line) for line in supervisor.record_path.read_text().splitlines() if line]


def test_the_defaults_are_the_ones_the_trace_assumes():
    assert (supervisor_module.FLAP_COUNT, supervisor_module.FLAP_WINDOW) == (3, 120)
    assert (supervisor_module.LADDER_TIER_2, supervisor_module.LADDER_TIER_3) == (2, 3)
    assert (supervisor_module.LADDER_TIER_4, supervisor_module.FAILURE_WINDOW) == (5, 900)


def test_c_s1_three_quick_clean_exits_resume_and_count_one_failure(world):
    """C-S1: resume, resume, resume; the third records flap{tier 1}; one failure counted."""
    supervisor = supervisor_module.Supervisor()
    actions = []
    for _ in range(3):
        actions.append(supervisor.decide(supervisor_module.EXIT_OK))
        world["clock"].now += 10
    assert actions == [("resume", 0), ("resume", 0), ("resume", 1)]
    assert len(supervisor.failures) == 1
    (flap,) = [r for r in lifecycle(supervisor) if r["event"] == "flap"]
    assert flap["tier"] == 1 and flap["action"] == "resume"


@pytest.mark.parametrize(
    ("exits", "flaps", "tier"),
    [(3, 1, 1), (6, 2, 2), (9, 3, 3), (12, 4, 3), (15, 5, 4), (18, 6, 4)],
)
def test_group_7_every_flap_resumes_even_at_tier_4(world, exits, flaps, tier):
    """v2 group 4.7: within 900 s, flaps add failures and tiers, and the action stays resume."""
    supervisor = supervisor_module.Supervisor()
    decisions = []
    for _ in range(exits):
        decisions.append(supervisor.decide(supervisor_module.EXIT_OK))
        world["clock"].now += 10  # 18 exits span 180 s: inside the 900 s failure window
    flap_records = [r for r in lifecycle(supervisor) if r["event"] == "flap"]
    assert len(flap_records) == flaps
    assert flap_records[-1]["tier"] == tier and decisions[-1] == ("resume", tier)
    assert {action for action, _tier in decisions} == {"resume"}, "a flap was answered with anything but resume"
    assert len(supervisor.failures) == flaps


def test_the_ordinary_ladder_still_gives_up_after_five_failures(world):
    """The control: five exit-43 failures in 900 s climb to give_up, unchanged."""
    supervisor = supervisor_module.Supervisor()
    actions = []
    for _ in range(5):
        actions.append(supervisor.decide(supervisor_module.EXIT_DUTY_FAULT)[0])
        world["clock"].now += 10
    assert actions == ["resume", "restore_floor", "restore_codebase", "restore_codebase", "give_up"]


def test_eighteen_clean_exits_leave_memory_and_shared_work_byte_identical(world, monkeypatch):
    """The whole loop, run for real with a fake child: no rung touches memory, no flap restores work."""
    before = digests(world["files"])
    supervisor = supervisor_module.Supervisor()
    exits = iter([supervisor_module.EXIT_OK] * 18)
    restores = []
    monkeypatch.setattr(supervisor, "mirror", lambda: None)
    monkeypatch.setattr(supervisor, "restore_floor", lambda: restores.append("floor"))
    monkeypatch.setattr(supervisor, "restore_codebase", lambda: restores.append("codebase"))

    def run_child():
        world["clock"].now += 10
        try:
            return next(exits)
        except StopIteration:
            supervisor.stopping = True
            return supervisor_module.EXIT_OK

    monkeypatch.setattr(supervisor, "run_child", run_child)
    assert supervisor.run() == 0
    assert restores == [], "a clean-exit flap restored shared work"
    assert digests(world["files"]) == before, "a memory or work file changed"
    assert not (supervisor_module.HOME_DIR / "session" / "abandoned").exists()
    decisions = [r for r in lifecycle(supervisor) if r["event"] == "decision"]
    assert {d["action"] for d in decisions} == {"resume"}
    assert max(d["tier"] for d in decisions) == 4, "tier 4 was reached and still resumed"


def test_the_moving_action_no_longer_exists():
    assert not hasattr(supervisor_module, "SESSION_FILES")
    assert not hasattr(supervisor_module.Supervisor, "resume_without_session")
