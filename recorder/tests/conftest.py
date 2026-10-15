import os
import sys

import pytest

RECORDER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_DIR = os.path.join(os.path.dirname(RECORDER_DIR), "harness")
TESTS_DIR = os.path.join(RECORDER_DIR, "tests")

# Aurora's recorder tests import `proxy` and `recorder_streams` by bare name, two of them import
# the harness's `chassis`, and one imports `hostile_inputs` from beside them. insert(0) puts the
# last insert first, so these go in reverse: recorder/, then harness/, then recorder/tests.
# `services/` has a `chassis.py` of its own until plan 5, which is why this is its own process.
for path in (TESTS_DIR, HARNESS_DIR, RECORDER_DIR):
    sys.path.insert(0, path)


@pytest.fixture(autouse=True)
def _chdir_recorder(monkeypatch):
    monkeypatch.chdir(RECORDER_DIR)
