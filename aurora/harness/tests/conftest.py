import os
import sys

import pytest

HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The harness's modules are imported by their bare names (`agent`, `chassis`, `watchdog`),
# as in Aurora.
sys.path.insert(0, HARNESS_DIR)


@pytest.fixture(autouse=True)
def _chdir_harness(monkeypatch):
    monkeypatch.chdir(HARNESS_DIR)
