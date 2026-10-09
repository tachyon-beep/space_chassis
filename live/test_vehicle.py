"""The vehicle as the window (plan 7, Phase B): one executive for every agent's window, a restart
that resumes the same world, containment with it running, and a stop that reaches it.

The tests share one vehicle stack and run in file order: the stop is last. Everything is read from
the host side of the window image and the vehicle's own log -- `.executive.json` in the window
root, each window's `state.json`, and the telemetry frames, which carry the boot that wrote them.
The smoke override polls every 0.2 s, so the vehicle's checkpoint (every 50 ticks) comes in
seconds; a kill after it exercises the cadence checkpoint and the replay from it.
"""

import json
import subprocess
import time

from stack import REPO, allowed_environment, wait_for

# Startup hashes the vehicle's whole configuration corpus and replays from the last checkpoint:
# seconds on a warm host, more on a cold one.
START_SECONDS = 180


def _executive(stack) -> dict | None:
    try:
        return json.loads((stack.volumes / "diode" / "data" / ".executive.json").read_text())
    except (OSError, ValueError):
        return None


def _tick(stack) -> int:
    return (_executive(stack) or {}).get("tick", -1)


def _window_world(stack, slug: str) -> str | None:
    try:
        state = json.loads((stack.volumes / "diode" / "data" / slug / "state.json").read_text())
    except (OSError, ValueError):
        return None
    return (state.get("executive") or {}).get("world_id")


def _newest_frame(stack, slug: str) -> dict | None:
    newest = None
    for path in (stack.volumes / "diode" / "data" / slug / "telemetry").glob("*.json"):
        try:
            frame = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if newest is None or frame.get("seq", -1) > newest.get("seq", -1):
            newest = frame
    return newest


def _restarts(stack) -> int:
    try:
        return stack.restart_count("vehicle")
    except subprocess.CalledProcessError:
        return -1  # between the exit and the restart, the container is not listed


def test_one_executive_serves_every_agent_s_window_under_one_world(vehicle_stack):
    stack = vehicle_stack
    wait_for(
        lambda: _tick(stack) >= 5 and all(_window_world(stack, s) for s in stack.slugs),
        timeout=START_SECONDS,
        every=2,
        what="the vehicle to publish every window",
    )
    executive = _executive(stack)
    assert sorted(executive["slugs"]) == sorted(stack.slugs), executive
    assert "vehicle" not in executive["slugs"], "a roster stack serves no window of its own"
    for slug in stack.slugs:
        assert _window_world(stack, slug) == executive["world_id"], slug
    consoles = stack.exec("vehicle", "pgrep", "-f", "[c]onsole\\.py").stdout.split()
    assert len(consoles) == 1, f"one executive serves every window, not {consoles}"


def test_containment_holds_with_the_vehicle_running(vehicle_stack):
    stack = vehicle_stack
    agents = " ".join(f"agent_{n}" for n in range(1, stack.agents + 1))
    result = subprocess.run(
        ["sh", str(REPO / "scripts" / "verify_containment.sh")],
        cwd=REPO,
        env=allowed_environment({"COMPOSE": " ".join(stack.compose_command()), "AGENTS": agents}),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS  the vehicle binds /diode and /state and nothing else" in result.stdout
    for n in range(1, stack.agents + 1):
        assert f"PASS  agent_{n} mounts nothing of the vehicle's private state" in result.stdout
        assert f"PASS  agent_{n} cannot write the window root" in result.stdout


def test_a_killed_console_resumes_the_same_world(vehicle_stack):
    stack = vehicle_stack
    # Past the first cadence checkpoint (tick 50), and not on a multiple of it.
    wait_for(lambda: _tick(stack) >= 63, timeout=START_SECONDS, every=1, what="tick 63")
    before = _executive(stack)
    frame = _newest_frame(stack, stack.slugs[0])
    restarts = _restarts(stack)
    # docker-init is PID 1; the console is its child. `docker kill` would mark the container
    # stopped by hand, and the restart policy would leave it down.
    stack.exec("vehicle", "pkill", "-9", "-f", "[c]onsole\\.py")
    wait_for(
        lambda: _restarts(stack) > restarts,
        timeout=120,
        every=1,
        what="the restart policy to bring the vehicle back",
    )

    def resumed():
        newest = _newest_frame(stack, stack.slugs[0])
        return newest if newest and newest.get("boot_id") != frame["boot_id"] else None

    after_frame = wait_for(
        resumed, timeout=START_SECONDS, every=1, what="a frame from the new boot"
    )
    after = _executive(stack)
    assert after["world_id"] == before["world_id"], "a restart resumes the world it was flying"
    assert after["tick"] > before["tick"], (before["tick"], after["tick"])
    assert after_frame["seq"] > frame["seq"], "each window's frame sequence continues"
    assert f"resumed world {before['world_id']}" in stack.logs("vehicle")
    for slug in stack.slugs:
        assert _window_world(stack, slug) == before["world_id"], slug


def test_docker_stop_reaches_the_vehicle_within_its_grace(vehicle_stack):
    stack = vehicle_stack
    started = time.monotonic()
    stack.compose("stop", "--timeout", "30", "vehicle")
    elapsed = time.monotonic() - started
    # Without docker-init the console would be PID 1, ignore SIGTERM, and wait out the 30 s.
    assert elapsed < 20, f"docker stop took {elapsed:.1f}s: the SIGTERM did not reach the console"
