import os
import sys

import pytest

PUMP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(PUMP_DIR, "tests")

# Aurora's pump tests import `pump` and `hostile_inputs` by bare name. insert(0) puts the last
# insert first, so pump/ goes in last.
for path in (TESTS_DIR, PUMP_DIR):
    sys.path.insert(0, path)


@pytest.fixture(autouse=True)
def _chdir_pump(monkeypatch):
    monkeypatch.chdir(PUMP_DIR)
