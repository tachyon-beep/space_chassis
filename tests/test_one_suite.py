"""One pytest runs every suite (plan 5): the root, the harness, the recorder, the pump, the vehicle.

They ran as separate processes while the old runtime's services/chassis.py, recorder.py and pump.py
shared bare module names with Aurora's. With those retired, `testpaths` takes every directory. What
can still go wrong is quiet: a suite collected short, or a bare name importing from the wrong
directory. These tests hold both. They are slow (several full collections); the green merged run is
the proof, and these guard it.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITES = [
    "tests",
    "harness/tests",
    "recorder/tests",
    "pump/tests",
    "docs/deep_research/vehicle/tests",
]
PLUGIN = """
import json, os, sys

def pytest_collection_finish(session):
    names = ("chassis", "agent", "watchdog", "command_runtime", "pump", "proxy",
             "core_caps", "recorder_streams", "health", "common")
    found = {name: getattr(sys.modules.get(name), "__file__", None) for name in names}
    with open(os.environ["MODULE_REPORT"], "w") as f:
        json.dump(found, f)
"""


def _collect(*paths, env=None):
    result = subprocess.run(
        # addopts already carries -q; a second -q prints per-file counts, not node IDs.
        # The vehicle submodule carries its own pytest config; one rootdir and one config make the
        # node IDs of a directory collected alone comparable with the merged run's.
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            f"--rootdir={ROOT}",
            "-c",
            str(ROOT / "pyproject.toml"),
            *paths,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    found = {line for line in result.stdout.splitlines() if "::" in line}
    assert found, "the collection named no tests"
    return found


def test_a_bare_pytest_collects_every_suite():
    merged = _collect()
    union = set()
    for suite in SUITES:
        union |= _collect(suite)
    assert merged == union, sorted(union - merged)[:20]


def test_each_bare_module_name_resolves_to_its_own_directory(tmp_path):
    import os

    (tmp_path / "module_report_plugin.py").write_text(PLUGIN)
    report = tmp_path / "modules.json"
    env = dict(os.environ, PYTHONPATH=str(tmp_path), MODULE_REPORT=str(report))
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "module_report_plugin",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
        check=True,
    )
    found = json.loads(report.read_text())
    expected = {
        "chassis": "harness/chassis.py",
        "agent": "harness/agent.py",
        "watchdog": "harness/watchdog.py",
        "pump": "pump/pump.py",
        "proxy": "recorder/proxy.py",
        "core_caps": "recorder/core_caps.py",
        "recorder_streams": "recorder/recorder_streams.py",
        "health": "services/health.py",
        "common": "services/common.py",
    }
    for name, relative in expected.items():
        assert found.get(name) == str(ROOT / relative), (name, found.get(name))


def test_the_shared_hostile_inputs_are_identical():
    # In one process the first `import hostile_inputs` wins, so the two copies must not drift.
    recorder_copy = (ROOT / "recorder" / "tests" / "hostile_inputs.py").read_bytes()
    pump_copy = (ROOT / "pump" / "tests" / "hostile_inputs.py").read_bytes()
    assert recorder_copy == pump_copy
