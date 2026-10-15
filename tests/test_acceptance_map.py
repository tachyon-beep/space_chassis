"""Spec §9's acceptance list, mapped to where each property is held in this repository.

§9 names Aurora's tests to port and space's tests to keep. Some ported whole, some were renamed or
split as they were adapted to the mission world, and some belong to Aurora components the port
dropped (spec §3). Every name maps to test nodes that exist, or to a stated reason. A name typed
wrong, or a test renamed away from its row, fails here.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

ACCEPTANCE = {
    # watchdog
    "test_watchdog": ["harness/tests/test_watchdog.py", "harness/tests/test_space_watchdog.py"],
    "test_evolving_recovery": ["harness/tests/test_evolving_recovery.py"],
    "test_watchdog_telemetry": ["harness/tests/test_watchdog_telemetry.py"],
    # chassis
    "test_chassis_recovery": ["harness/tests/test_chassis_recovery.py"],
    "test_chassis_commands": ["harness/tests/test_chassis_commands.py"],
    "test_compact": ["harness/tests/test_compact.py"],
    "test_context_window": ["harness/tests/test_context_window.py"],
    "test_repair_send_view": ["harness/tests/test_repair_send_view.py"],
    "test_session_persistence": ["harness/tests/test_session_persistence.py"],
    "test_file_tools": ["harness/tests/test_file_tools.py", "harness/tests/test_mission_kit.py"],
    "test_tool_registry": ["harness/tests/test_tool_registry.py"],
    "test_command_runtime": ["harness/tests/test_command_runtime.py"],
    "test_startup": ["tests/test_startup.py"],
    "test_persistent_state": [
        "tests/test_agent_entrypoint.py::test_no_harness_or_recorder_module_names_state",
        "tests/test_agent_entrypoint.py::test_the_entrypoint_names_state_only_for_the_servers",
    ],
    # recorder
    "test_proxy": ["recorder/tests/test_proxy.py"],
    "test_recorder_streams": ["recorder/tests/test_recorder_streams.py"],
    "test_recorder_events": ["recorder/tests/test_recorder_events.py"],
    "test_recorder_console_hostile": ["recorder/tests/test_recorder_console_hostile.py"],
    "test_unix_listener": ["recorder/tests/test_unix_listener.py"],
    "test_upstream_selection": ["recorder/tests/test_upstream_selection.py"],
    "test_llm_console_seed": ["tests/test_console_seed.py"],
    # pump
    "test_pump": ["pump/tests/test_pump.py"],
    # adapted to the mission world
    "test_agent_credentials": [
        "tests/test_compose_generated.py::test_the_agent_environment_carries_no_credential_and_the_dummy_key",
    ],
    "test_agent_dependencies": ["tests/test_agent_dependencies.py"],
    "test_smoke": [
        "harness/tests/test_cleanliness.py",
        "live/test_acceptance.py",
        "live/test_containment.py",
    ],
    "test_cleanliness": ["harness/tests/test_cleanliness.py"],
    # space tests kept
    "test_vehicle_reconciliation": ["tests/test_vehicle_reconciliation.py"],
    "test_observer": ["tests/test_observer.py"],
    "test_review": ["tests/test_review.py"],
}

DEF = re.compile(r"^(?:async\s+)?def (test_\w+)\(", re.M)


@pytest.mark.parametrize("name", sorted(ACCEPTANCE))
def test_every_acceptance_name_resolves_to_real_tests(name):
    targets = ACCEPTANCE[name]
    assert targets, name
    for target in targets:
        path, _, function = target.partition("::")
        file = ROOT / path
        assert file.is_file(), (name, path)
        defined = set(DEF.findall(file.read_text(encoding="utf-8")))
        assert defined, (name, path, "holds no tests")
        if function:
            assert function in defined, (name, target)
