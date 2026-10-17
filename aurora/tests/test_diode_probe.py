"""The contract probe's own judgement, without a vehicle: contract/diode_probe.py.

`check_state_is_a_mirror` doctors `state.json` and judges what the window publishes next. The window
here is a few files and a clock that only moves when the probe sleeps, and the window's next cycle
lands on whichever sleep the test picks, so how long a cycle takes on the host decides nothing.
"""

from __future__ import annotations

import json

import diode_probe
import pytest


class Clock:
    """The probe's `time`: monotonic only advances by the probe's own sleeps, and each sleep may run a cycle."""

    def __init__(self, cycle=None, on_sleep: int | None = None):
        self.now = 0.0
        self.sleeps = 0
        self.cycle = cycle
        self.on_sleep = on_sleep

    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        self.sleeps += 1
        if self.cycle is not None and self.sleeps == self.on_sleep:
            self.cycle()


@pytest.fixture
def window(tmp_path):
    root = tmp_path / "diode" / "otter"
    (root / "output").mkdir(parents=True)
    state = {"available_commands": ["noop"], "variables": {"enable_noop": False}}
    (root / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return root


def probe(window, clock, monkeypatch) -> diode_probe.Probe:
    monkeypatch.setattr(diode_probe, "time", clock)
    return diode_probe.Probe(window.parent, window.name, poll_seconds=0.3, timeout=15)


def republish(window, verbs):
    def cycle():
        body = {"available_commands": verbs, "variables": {"enable_noop": False}}
        (window / "state.json").write_text(json.dumps(body), encoding="utf-8")

    return cycle


def verdicts(probe: diode_probe.Probe) -> dict[str, bool | None]:
    return {check.name: check.passed for check in probe.checks}


def test_a_window_whose_cycle_comes_round_late_still_has_its_state_rewritten(window, monkeypatch):
    """A cycle well past 1.5 polls is a slow window, not a window that reads its mirror back."""
    clock = Clock(republish(window, ["noop"]), on_sleep=12)
    subject = probe(window, clock, monkeypatch)
    subject.check_state_is_a_mirror()
    assert clock.now > subject.poll_seconds * 1.5
    assert verdicts(subject) == {
        "published state is rewritten, not read back": True,
        "editing published state does not open anything": True,
    }


def test_a_window_that_never_republishes_fails_at_the_timeout(window, monkeypatch):
    clock = Clock()
    subject = probe(window, clock, monkeypatch)
    subject.check_state_is_a_mirror()
    assert clock.now >= subject.timeout
    assert verdicts(subject) == {
        "published state is rewritten, not read back": False,
        "editing published state does not open anything": False,
    }


def test_a_window_that_reads_its_mirror_back_fails_on_its_next_publication(window, monkeypatch):
    """Republishing what was planted is reading it back, however promptly it is done."""
    clock = Clock(republish(window, ["noop", "everything_is_open"]), on_sleep=1)
    subject = probe(window, clock, monkeypatch)
    subject.check_state_is_a_mirror()
    assert clock.now < subject.timeout, "the probe waited past the publication it was judging"
    assert verdicts(subject) == {
        "published state is rewritten, not read back": False,
        "editing published state does not open anything": False,
    }
