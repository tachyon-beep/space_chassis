import os
import sys

import pytest

HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The harness's modules are imported by their bare names (`agent`, `chassis`, `watchdog`),
# as in Aurora. `services/` carries a `chassis.py` of its own until plan 5 retires it, which
# is why these tests run as their own pytest process rather than from the root `testpaths`.
sys.path.insert(0, HARNESS_DIR)


@pytest.fixture(autouse=True)
def _chdir_harness(monkeypatch):
    monkeypatch.chdir(HARNESS_DIR)
