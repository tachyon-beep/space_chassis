"""Archived conversations are bounded (plan 6, Task 5).

Every fresh restore copies the conversation into tombstones/ and the git directory, and the
chassis writes one more on exit 43; on the 1 GiB /work tmpfs nothing pruned them, and a full /work
makes a restore fail and the ladder end in a reseed. The watchdog keeps the newest ARCHIVE_KEEP
conversation bodies per directory within a byte budget, and touches nothing else.
"""

import os
import subprocess

import watchdog
from test_evolving_recovery import repo_at, session


def _git_dir(repo):
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--absolute-git-dir"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _archives(directory, count, *, prefix="session_recovery_", size=10, start=1000):
    os.makedirs(directory, exist_ok=True)
    names = []
    for n in range(count):
        # The chassis stamps its archives %Y%m%d_%H%M%S_%f; the watchdog with time_ns().
        stamp = f"20261009_000000_{start + n:06d}" if prefix != "session_recovery_" else start + n
        name = f"{prefix}{stamp}.json"
        path = os.path.join(directory, name)
        with open(path, "wb") as f:
            f.write(b"x" * size)
        os.utime(path, (start + n, start + n))
        names.append(name)
    return names


def _listing(directory, pattern="session_"):
    return sorted(name for name in os.listdir(directory) if name.startswith(pattern))


def test_prune_keeps_the_newest_twenty_archives_per_directory(tmp_path):
    repo_at(tmp_path)
    tombstones = tmp_path / "tombstones"
    in_tombstones = _archives(tombstones, 25)
    in_git = _archives(_git_dir(tmp_path), 25)
    removed = watchdog.prune_archives(str(tmp_path))
    assert removed == 10
    assert _listing(tombstones) == in_tombstones[5:]
    assert _listing(_git_dir(tmp_path)) == in_git[5:]


def test_prune_stops_at_the_byte_budget_and_always_keeps_the_newest(tmp_path, monkeypatch):
    repo_at(tmp_path)
    tombstones = tmp_path / "tombstones"
    monkeypatch.setattr(watchdog, "ARCHIVE_TOMBSTONE_BYTES", 100)
    names = _archives(tombstones, 3, size=40)
    watchdog.prune_archives(str(tmp_path))
    assert _listing(tombstones) == names[1:]
    # One archive larger than the whole budget is still the newest, and kept.
    big = _archives(tombstones, 1, size=500, start=5000)
    watchdog.prune_archives(str(tmp_path))
    assert _listing(tombstones) == big


def test_prune_never_touches_notes_symlinks_or_other_files(tmp_path, monkeypatch):
    repo_at(tmp_path)
    monkeypatch.setattr(watchdog, "ARCHIVE_KEEP", 1)
    tombstones = tmp_path / "tombstones"
    real = _archives(tombstones, 3, prefix="session_")
    kept = [
        "recovery_note.txt",
        "synthetic_note.txt",
        "incarnation_note.txt",
        "incarnation-1-2.txt",
        "corrupt_session_1.txt",
        "my_memory.json",
        "session_index.json",
        "session_notes.json",
    ]
    for name in kept:
        (tombstones / name).write_text("mine")
    outside = tmp_path / "outside.json"
    outside.write_text("not an archive")
    link = tombstones / "session_20261009_000000_999999.json"
    link.symlink_to(outside)
    watchdog.prune_archives(str(tmp_path))
    for name in kept:
        assert (tombstones / name).exists(), name
    assert link.is_symlink() and outside.exists()
    # The planted link, newest by its target's clock, did not take the one slot a real archive has.
    assert (tombstones / real[-1]).exists()


def test_a_tombstones_that_is_a_symlink_is_not_walked(tmp_path, monkeypatch):
    repo_at(tmp_path)
    monkeypatch.setattr(watchdog, "ARCHIVE_KEEP", 1)
    elsewhere = tmp_path.parent / f"{tmp_path.name}-elsewhere"
    names = _archives(elsewhere, 3)
    (tmp_path / "tombstones").symlink_to(elsewhere)
    watchdog.prune_archives(str(tmp_path))
    assert _listing(elsewhere) == names


def test_prune_failure_never_raises_into_recovery(tmp_path, monkeypatch, capsys):
    repo_at(tmp_path)
    _archives(tmp_path / "tombstones", 25)

    def refuse(path):
        raise OSError("read-only")

    monkeypatch.setattr(watchdog.os, "remove", refuse)
    assert watchdog.prune_archives(str(tmp_path)) == 0
    assert "archive" in capsys.readouterr().out


def test_a_fresh_restore_prunes_and_keeps_the_archive_it_just_made(tmp_path):
    commit = repo_at(tmp_path)
    tombstones = tmp_path / "tombstones"
    # Older archives with mtimes in the future: only the name passed as newest can save the new one.
    older = set(_archives(tombstones, 25, start=int(4e9)))
    session(tmp_path)
    recovery = watchdog.Recovery(str(tmp_path))
    recovery.restore("baseline", commit, "elective", "test", True)
    archives = _listing(tombstones)
    assert len(archives) == 20
    made = [name for name in archives if name not in older]
    assert len(made) == 1 and made[0] in os.listdir(_git_dir(tmp_path))


def test_the_exit_43_path_is_pruned_too(tmp_path):
    # The chassis has already archived and removed the session; the restore that follows is fresh.
    commit = repo_at(tmp_path)
    _archives(tmp_path / "tombstones", 25, prefix="session_")
    recovery = watchdog.Recovery(str(tmp_path))
    recovery.restore("baseline", commit, "baseline_new", "exit 43", True)
    assert len(_listing(tmp_path / "tombstones")) == 20


def test_a_fresh_restore_prunes_before_it_copies(tmp_path, monkeypatch):
    # A /work full enough that the archive copy fails would end the ladder in a reseed; the prune
    # must make its room before the copy, not after.
    commit = repo_at(tmp_path)
    tombstones = tmp_path / "tombstones"
    _archives(tombstones, 25)
    session(tmp_path)
    at_copy = []
    copy = watchdog.shutil.copyfile

    def watched(source, destination):
        at_copy.append(len(_listing(tombstones)))
        return copy(source, destination)

    monkeypatch.setattr(watchdog.shutil, "copyfile", watched)
    watchdog.Recovery(str(tmp_path)).restore("baseline", commit, "elective", "test", True)
    assert at_copy and at_copy[0] <= watchdog.ARCHIVE_KEEP


def test_the_exit_43_archive_survives_whatever_its_clock_says(tmp_path):
    # Twenty older archives with later mtimes (a clock stepped back): the chassis's new one, the
    # newest by its name's stamp, is kept by both prunes.
    commit = repo_at(tmp_path)
    tombstones = tmp_path / "tombstones"
    _archives(tombstones, 20, prefix="session_", start=100)
    for name in _listing(tombstones):
        os.utime(tombstones / name, (4e9, 4e9))
    made = tombstones / "session_20261009_235959_000000.json"
    made.write_text("[]")
    os.utime(made, (1000, 1000))
    watchdog.Recovery(str(tmp_path)).restore("baseline", commit, "baseline_new", "exit 43", True)
    assert made.exists()
    assert len(_listing(tombstones)) == 20


def test_a_tombstones_swapped_for_a_link_mid_prune_is_not_followed(tmp_path, monkeypatch):
    # A process the agent left running moves tombstones/ into durable storage and leaves a link
    # behind, after the prune has looked at it: the deletes must not land in the new place.
    repo_at(tmp_path)
    tombstones = tmp_path / "tombstones"
    _archives(tombstones, 25)
    elsewhere = tmp_path.parent / f"{tmp_path.name}-state"
    real_listdir = os.listdir
    swapped = []

    def swap_then_list(target):
        if not swapped and str(target).endswith("tombstones") or (
            not swapped and isinstance(target, int)
        ):
            swapped.append(True)
            import shutil

            shutil.copytree(tombstones, elsewhere)
            shutil.rmtree(tombstones)
            tombstones.symlink_to(elsewhere)
        return real_listdir(target)

    monkeypatch.setattr(watchdog.os, "listdir", swap_then_list)
    watchdog.prune_archives(str(tmp_path))
    assert swapped
    assert len(_listing(elsewhere)) == 25
