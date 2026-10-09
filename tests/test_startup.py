"""How an agent's container starts (spec §9: test_startup, ported from Aurora at 42faf41).

Aurora's test_startup holds the order a host comes up in. Property by property:

| Aurora property | here |
|---|---|
| host preparation builds offline assets before the garden | dropped: no garden (spec §3) |
| every quick start runs host preparation before compose | ported below |
| the container verifier builds vendor assets before images | prepare_host refuses without the registry: tests/test_prepare_host.py::test_prepare_host_refuses_without_the_crate_registry |
| the entrypoint starts the pump before the watchdog | tests/test_agent_entrypoint.py::test_the_pump_loop_is_started_before_the_exec |
| the watchdog is what the entrypoint execs | tests/test_agent_entrypoint.py::test_the_watchdog_is_the_one_exec_and_the_last_line |
| a crashing pump is restarted by the loop | tests/test_agent_entrypoint.py::test_a_crashing_pump_is_restarted_by_the_loop |
| the image ships the pump outside the workspace | tests/test_agent_image.py::test_the_pump_and_the_recorder_ship_outside_the_seed |
| the image pre-creates the pump mountpoint | tests/test_agent_image.py::test_every_mountpoint_is_made_and_owned_by_the_agent |
| the pump volume is the agent's alone | tests/test_compose_generated.py::test_no_agent_mounts_another_agents_surface |
| the agent receives the pump resource limits | ported below |
| the recorder bounds its connection fan-out | ported below (pids and memory; plan 4b ruling 3 adds no connection count) |
| the recorder receives the operator token ceiling | ported below |
| the shipped template permits models out of the box | differs: the template ships the allow lists empty; which models, and the cap figures, are John's (spec §10.3) |
| the shipped template states both stream ceilings | ported below (the keys; their figures are John's) |
| books baked read-only, the garden names them | dropped: no books, no garden (spec §3) |
| the workspace ships no transcript tooling | tests/test_agent_image.py::test_the_agent_image_copies_exactly_the_six_runtime_files_into_the_seed |
| further hosts: loops, trees, sockets, consoles | dropped: one host per container (spec §3) |
| one shared build area | differs: /build is each agent's own (spec §5) |
| the per-host supervisor, a failed tree restore | dropped: the watchdog in the entrypoint's exec form (spec §4) |
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

import compose_text  # noqa: E402

SERVICES = compose_text.services((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")


def test_every_quick_start_runs_host_preparation_before_compose():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.index("scripts/prepare_host.sh") < readme.index("docker compose")


def test_the_agent_receives_the_pump_resource_limits():
    environment = SERVICES["agent_1"]["environment"]
    assert environment["PUMP_MAX_ENTRIES"] == "${PUMP_MAX_ENTRIES:-32}"
    assert environment["PUMP_MAX_CONCURRENT"] == "${PUMP_MAX_CONCURRENT:-8}"
    assert "PUMP_MAX_ENTRIES" in EXAMPLE and "PUMP_MAX_CONCURRENT" in EXAMPLE


def test_the_recorder_bounds_its_threads_and_memory():
    # Under keep-alive a connection holds a thread for its life, and the pids cgroup counts them.
    recorder = SERVICES["recorder_1"]
    assert str(recorder["pids_limit"]) == "512"
    assert recorder["mem_limit"] == "512m"


def test_the_recorder_receives_the_operator_token_ceiling():
    assert SERVICES["recorder_1"]["environment"]["STREAM_TOKEN_HOURLY_MAX"] == (
        "${STREAM_TOKEN_HOURLY_MAX:-}"
    )
    assert "STREAM_TOKEN_HOURLY_MAX" not in SERVICES["agent_1"]["environment"]


def test_the_shipped_template_states_both_stream_ceilings():
    lines = EXAMPLE.splitlines()
    for key in ("STREAM_HOURLY_MAX", "STREAM_TOKEN_HOURLY_MAX"):
        assert any(line.startswith(key + "=") for line in lines), key
