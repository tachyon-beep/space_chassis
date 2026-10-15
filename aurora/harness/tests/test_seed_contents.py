import subprocess

RUNTIME_FILES = {
    "agent.py",
    "chassis.py",
    "command_runtime.py",
    "watchdog.py",
    "system_prompt.txt",
    "user_prompt.txt",
}


def test_the_seed_directory_tracks_only_the_runtime_files_and_its_tests():
    # harness/ becomes /opt/agent, the directory every agent boots from: a stray file here is a
    # fact about its world. The tests run from harness/, so paths are relative to it.
    tracked = subprocess.run(
        ["git", "ls-files", "."], check=True, capture_output=True, text=True
    ).stdout.split()
    assert {path for path in tracked if not path.startswith("tests/")} == RUNTIME_FILES


def test_a_session_or_tombstone_the_tests_leave_behind_is_ignored():
    for path in ("session_context.json", "tombstones/recovery_note.txt"):
        assert subprocess.run(["git", "check-ignore", "-q", path]).returncode == 0, path
