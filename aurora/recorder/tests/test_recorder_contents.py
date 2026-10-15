import subprocess

MODULES = {"proxy.py", "recorder_streams.py", "core_caps.py"}


def test_the_recorder_directory_tracks_only_its_modules_and_tests():
    tracked = subprocess.run(
        ["git", "ls-files", "."], check=True, capture_output=True, text=True
    ).stdout.split()
    assert {path for path in tracked if not path.startswith("tests/")} == MODULES
