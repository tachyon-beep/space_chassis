import subprocess

import pytest

import chassis
import watchdog

watchdog_Recovery = watchdog.Recovery


def git(repo, *args):
    return (
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, timeout=5)
        .stdout.decode()
        .strip()
    )


def repo_at(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "test")
    git(tmp_path, "config", "user.email", "test@localhost")
    (tmp_path / "agent.py").write_text("print('initial')\n")
    (tmp_path / ".gitignore").write_text("tombstones/\nsession_context.json\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "initial")
    git(tmp_path, "tag", "baseline")
    git(tmp_path, "tag", "rescue")
    return git(tmp_path, "rev-parse", "HEAD")


def test_the_environment_pause_is_sixty_seconds_plus_up_to_thirty_of_jitter():
    assert watchdog.environment_pause_seconds(0.0) == 60
    assert watchdog.environment_pause_seconds(0.5) == 75
    assert watchdog.environment_pause_seconds(0.999) < 90


def test_exit_44_pauses_for_the_jittered_time(monkeypatch):
    slept = []
    monkeypatch.setattr(watchdog.time, "sleep", slept.append)
    monkeypatch.setattr(watchdog.random, "random", lambda: 0.5)
    watchdog.apply_recovery("pause", 44, "hash")
    assert slept == [75]


def test_a_fresh_seed_boot_leaves_a_recovery_note_saying_so(tmp_path):
    commit = repo_at(tmp_path)
    recovery = watchdog.Recovery(str(tmp_path))
    assert recovery.seeded is True
    assert recovery.note_seed_boot() is True
    assert "started from the image seed" in recovery.state["note"]
    assert commit in recovery.state["note"]
    assert (tmp_path / "tombstones" / "recovery_note.txt").exists()


def test_a_boot_with_recovery_state_writes_no_seed_note(tmp_path):
    repo_at(tmp_path)
    watchdog.Recovery(str(tmp_path)).note_seed_boot()
    again = watchdog.Recovery(str(tmp_path))
    assert again.seeded is False
    assert again.note_seed_boot() is False


def test_the_seed_boot_note_is_delivered_once(tmp_path, monkeypatch):
    repo_at(tmp_path)
    watchdog.Recovery(str(tmp_path)).note_seed_boot()
    monkeypatch.setattr(chassis, "WORK_DIR", str(tmp_path))
    messages = []
    chassis.deliver_recovery_note(messages)
    chassis.deliver_recovery_note(messages)
    assert len(messages) == 1
    assert "image seed" in messages[0]["content"]


def test_the_watchdog_writes_the_seed_note_before_the_first_agent_starts(tmp_path, monkeypatch):
    repo_at(tmp_path)
    monkeypatch.setattr(watchdog, "Recovery", lambda: watchdog_Recovery(str(tmp_path)))

    class Started(Exception):
        pass

    def spawn():
        assert (tmp_path / "tombstones" / "recovery_note.txt").exists()
        raise Started

    monkeypatch.setattr(watchdog, "spawn_agent", spawn)
    with pytest.raises(Started):
        watchdog.run_watchdog()
