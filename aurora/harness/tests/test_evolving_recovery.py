import json
import subprocess
import time
from pathlib import Path

import pytest

import chassis
import watchdog


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
    (tmp_path / "other.py").write_text("initial\n")
    (tmp_path / ".gitignore").write_text("tombstones/\nsession_context.json\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "initial")
    git(tmp_path, "tag", "baseline")
    git(tmp_path, "tag", "rescue")
    return git(tmp_path, "rev-parse", "HEAD")


def session(repo):
    path = repo / "session_context.json"
    path.write_text(json.dumps([{"role": "user", "content": "remember"}]))
    return path


def test_exact_recovery_ladder_same_new_rescue_even_equal_tags(tmp_path):
    initial = repo_at(tmp_path)
    saved = session(tmp_path)
    recovery = watchdog.Recovery(str(tmp_path))
    recovery.failure("broken migration")
    assert recovery.state["phase"] == "baseline_same"
    assert saved.exists()
    assert "preserved incarnation" in recovery.state["note"]
    reloaded = watchdog.Recovery(str(tmp_path))
    reloaded.failure("baseline same failed")
    assert reloaded.state["phase"] == "baseline_new"
    assert not saved.exists()
    assert list((tmp_path / ".git").glob("session_recovery_*.json"))
    reloaded.failure("baseline new failed")
    assert reloaded.state["phase"] == "rescue_new"
    assert reloaded.state["selected"]["commit"] == initial
    with pytest.raises(watchdog.RestoreError, match="exhausted"):
        watchdog.Recovery(str(tmp_path)).failure("rescue failed")


def test_distinct_rescue_sticky_done_and_ref_promotion_independent(tmp_path):
    initial = repo_at(tmp_path)
    (tmp_path / "agent.py").write_text("broken baseline\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "candidate")
    git(tmp_path, "tag", "-f", "baseline")
    broken = git(tmp_path, "rev-parse", "baseline")
    assert git(tmp_path, "rev-parse", "rescue") == initial
    recovery = watchdog.Recovery(str(tmp_path))
    for reason in ("current", "same", "new"):
        recovery.failure(reason)
    assert recovery.state["selected"]["ref"] == watchdog.RESCUE_REF
    assert recovery.state["failed"][watchdog.BASELINE_REF] == broken
    reloaded = watchdog.Recovery(str(tmp_path))
    reloaded.elective("done", fresh=True)
    assert reloaded.state["selected"]["commit"] == initial
    git(tmp_path, "tag", "-f", "baseline", initial)
    reloaded.elective("done after changed baseline", fresh=True)
    assert reloaded.state["selected"]["ref"] == watchdog.BASELINE_REF
    assert git(tmp_path, "rev-parse", "rescue") == initial


def test_experimental_elective_only_and_failed_commit_not_reselected(tmp_path):
    initial = repo_at(tmp_path)
    (tmp_path / "agent.py").write_text("experimental\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "experiment")
    git(tmp_path, "tag", "experimental")
    recovery = watchdog.Recovery(str(tmp_path))
    recovery.elective("reset", fresh=False)
    assert recovery.state["selected"]["ref"] == watchdog.EXPERIMENTAL_REF
    assert recovery.state["phase"] == "elective"
    recovery.failure("experimental broken migration")
    assert recovery.state["phase"] == "baseline_same"
    assert recovery.state["selected"]["commit"] == initial
    recovery.elective("done", fresh=True)
    assert recovery.state["selected"]["ref"] == watchdog.BASELINE_REF
    git(tmp_path, "tag", "-d", "experimental")
    recovery.elective("opt out", fresh=True)
    assert recovery.state["selected"]["ref"] == watchdog.BASELINE_REF


def test_elective_baseline_then_failure_starts_same_incarnation(tmp_path):
    repo_at(tmp_path)
    recovery = watchdog.Recovery(str(tmp_path))
    recovery.elective("done", fresh=True)
    session(tmp_path)
    recovery.failure("broken migration")
    assert recovery.state["phase"] == "baseline_same"
    assert "preserved incarnation" in recovery.state["note"]


def test_missing_refs_exhaust_and_failed_reset_never_cleans(tmp_path, monkeypatch):
    repo_at(tmp_path)
    (tmp_path / "untracked").write_text("keep")
    called = []
    real = watchdog.git_command

    def command(directory, *args):
        called.append(args[0])
        if args[0] == "reset":
            raise watchdog.RestoreError("reset obstruction")
        return real(directory, *args)

    monkeypatch.setattr(watchdog, "git_command", command)
    with pytest.raises(watchdog.RestoreError, match="reset obstruction"):
        watchdog.git_reset_all(str(tmp_path))
    assert "clean" not in called
    assert (tmp_path / "untracked").exists()
    git(tmp_path, "tag", "-d", "baseline", "rescue")
    with pytest.raises(watchdog.RestoreError, match="exhausted"):
        watchdog.Recovery(str(tmp_path)).failure("missing refs")


def test_git_timeout_is_checked_and_bounded(tmp_path, monkeypatch):
    repo_at(tmp_path)

    def timed_out(*args, **kwargs):
        assert kwargs["timeout"] == watchdog.GIT_TIMEOUT_SECONDS
        return {"status": "timeout", "returncode": -9, "stderr": b"\xff"}

    monkeypatch.setattr(watchdog, "run_command", timed_out)
    with pytest.raises(watchdog.RestoreError, match="timeout"):
        watchdog.git_reset_all(str(tmp_path))


def test_pause_preserves_recovery_evidence_and_session(tmp_path, monkeypatch):
    repo_at(tmp_path)
    saved = session(tmp_path)
    recovery = watchdog.Recovery(str(tmp_path))
    recovery.failure("broken")
    before = json.loads(Path(recovery.path).read_text())
    monkeypatch.setattr(watchdog.time, "sleep", lambda _: None)
    assert watchdog.apply_recovery("pause", 44, "hash", recovery) == "hash"
    assert json.loads(Path(recovery.path).read_text()) == before
    assert saved.exists()


def test_fresh_harness_failure_does_not_select_experimental(tmp_path):
    repo_at(tmp_path)
    git(tmp_path, "tag", "experimental")
    recovery = watchdog.Recovery(str(tmp_path))
    recovery.failure("harness ended incarnation", fresh_only=True)
    assert recovery.state["phase"] == "baseline_new"
    assert recovery.state["selected"]["ref"] == watchdog.BASELINE_REF


@pytest.mark.parametrize("content", [None, "{bad json", "{}", "[1]", '[{"foo":"bar"}]'])
def test_corrupt_or_missing_session_note_is_honest(tmp_path, content):
    repo_at(tmp_path)
    if content is not None:
        (tmp_path / "session_context.json").write_text(content)
    recovery = watchdog.Recovery(str(tmp_path))
    recovery.failure("broken")
    assert "saved conversation unavailable" in recovery.state["note"]
    assert "fresh incarnation" in recovery.state["note"]


def test_session_and_evidence_survive_changed_ignore_rule_and_tracked_session(tmp_path):
    repo_at(tmp_path)
    # A deliberately tracked historical session must not overwrite the current conversation.
    (tmp_path / ".gitignore").write_text("")
    saved = session(tmp_path)
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "tracked state")
    git(tmp_path, "tag", "-f", "baseline")
    saved.write_text(json.dumps([{"role": "user", "content": "current context"}]))
    recovery = watchdog.Recovery(str(tmp_path))
    recovery.failure("preserve tracked session")
    assert "current context" in saved.read_text()
    recovery.failure("fresh retry")
    # A tracked old session must not resurrect a supposedly fresh incarnation.
    assert not saved.exists()
    assert json.loads(Path(recovery.path).read_text())["evidence"]["reason"] == "fresh retry"


def test_progress_requires_new_completed_round_and_probation(tmp_path, monkeypatch):
    repo_at(tmp_path)
    recovery = watchdog.Recovery(str(tmp_path))
    recovery.failure("broken")
    Path(recovery.progress_path).write_text(json.dumps({"pid": 123, "completed_at": 0}))
    monkeypatch.setattr(watchdog, "RECOVERY_PROBATION_SECONDS", 0)
    recovery.observe_progress(123)
    assert recovery.state["phase"] == "baseline_same"
    Path(recovery.progress_path).write_text(
        json.dumps({"pid": 123, "completed_at": time.monotonic()})
    )
    recovery.observe_progress(123)
    assert recovery.state["phase"] is None


def test_reference_export_uses_baseline_without_git_or_stock(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    repo_at(repo)
    (repo / "agent.py").write_text("working changes\n")
    telemetry = tmp_path / "telemetry"
    telemetry.mkdir()
    watchdog.mirror_work(str(repo), str(telemetry))
    assert (telemetry / "work" / "baseline_reference.txt").read_text() == "print('initial')\n"
    assert not (telemetry / "work" / ".git").exists()
    assert not (telemetry / "work" / "agent_stock.py").exists()


def test_recovery_note_delivered_again_for_fresh_event(tmp_path, monkeypatch):
    repo_at(tmp_path)
    recovery = watchdog.Recovery(str(tmp_path))
    monkeypatch.setattr(chassis, "WORK_DIR", str(tmp_path))
    recovery.failure("same reason")
    first = []
    chassis.deliver_recovery_note(first)
    chassis.deliver_recovery_note(first)
    assert len(first) == 1
    recovery.elective("same reason", fresh=True)
    fresh = []
    chassis.deliver_recovery_note(fresh)
    assert len(fresh) == 1
    assert first[0]["content"] != fresh[0]["content"]


def test_actual_restored_agents_boot_in_order_without_model_calls(tmp_path):
    import sys

    initial = repo_at(tmp_path)
    rescue_code = (
        "import pathlib; print('rescue boot'); pathlib.Path('booted').write_text('rescue')"
    )
    (tmp_path / "agent.py").write_text(rescue_code)
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "rescue")
    git(tmp_path, "tag", "-f", "rescue")
    (tmp_path / "agent.py").write_text(
        "import pathlib,sys; print('baseline boot',pathlib.Path('session_context.json').exists()); "
        "sys.exit(9)"
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "broken baseline")
    git(tmp_path, "tag", "-f", "baseline")
    (tmp_path / "agent.py").write_text("def (broken migration")
    session(tmp_path)
    recovery = watchdog.Recovery(str(tmp_path))
    results = []
    for reason in ("broken current syntax", "same failed", "fresh failed"):
        recovery.failure(reason)
        results.append(
            subprocess.run(
                [sys.executable, str(tmp_path / "agent.py")],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=2,
            )
        )
    assert results[0].returncode == results[1].returncode == 9
    assert results[0].stdout.strip() == "baseline boot True"
    assert results[1].stdout.strip() == "baseline boot False"
    assert results[2].returncode == 0
    assert (tmp_path / "booted").read_text() == "rescue"
    assert recovery.state["selected"]["commit"] != initial
