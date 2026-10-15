"""The vehicle as the window (plan 7, Phase B): one executive for every agent's window, a restart
that resumes the same world, containment with it running, and a stop that reaches it.

The tests share one vehicle stack and run in file order: the stop is last. Everything is read from
the host side of the window image and the vehicle's own log -- `.executive.json` in the window
root, each window's `state.json`, and the telemetry frames, which carry the boot that wrote them.
The smoke override polls every 0.2 s, so the vehicle's checkpoint (every 50 ticks) comes in
seconds; a kill after it exercises the cadence checkpoint and the replay from it.
"""

import json
import re
import subprocess
import time

from stack import REPO, SMOKE_VEHICLE_SEED, allowed_environment, wait_for

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


HIDDEN_KEYS = {"scenario", "seed", "arms", "dwell", "onset"}
SEED_TEXT = re.compile(rf"(?<![0-9]){SMOKE_VEHICLE_SEED}(?![0-9])")


def _keys_and_values(value) -> tuple[set[str], list]:
    if isinstance(value, dict):
        keys, values = set(value), []
        for item in value.values():
            inner_keys, inner_values = _keys_and_values(item)
            keys |= inner_keys
            values += inner_values
        return keys, values
    if isinstance(value, list):
        keys, values = set(), []
        for item in value:
            inner_keys, inner_values = _keys_and_values(item)
            keys |= inner_keys
            values += inner_values
        return keys, values
    return set(), [value]


def _read(path) -> str:
    """A window file's text. The vehicle replaces files whole (write, then rename), so a read sees
    the old file or the new one; one that still fails after retries is a failure, never a skip."""
    for attempt in range(5):
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            if attempt == 4:
                raise
            time.sleep(0.1)
    raise AssertionError("unreachable")


def _assert_no_window_carries_the_world_s_identity(stack) -> None:
    """John, 2026-10-10: no risk of information sharing. The identity (scenario, seed, the armed
    faults and their dwell) belongs in the window root's `.executive.json`, which no agent binds.
    Every regular file in every agent's window is read: as text, for the smoke world's distinctive
    seed; and as JSON where it is JSON, for the identity's keys and for the seed as a value."""
    executive = _executive(stack)
    assert executive is not None and str(executive.get("seed")) == SMOKE_VEHICLE_SEED, executive
    for slug in stack.slugs:
        window = stack.volumes / "diode" / "data" / slug
        parsed_pending = False
        for path in sorted(p for p in window.rglob("*") if p.is_file()):
            where = path.relative_to(stack.volumes)
            text = _read(path)
            assert not SEED_TEXT.search(text), f"{where} carries the world's seed"
            if path.suffix != ".json":
                continue
            for attempt in range(5):
                try:
                    document = json.loads(_read(path))
                    break
                except ValueError:
                    if attempt == 4:
                        raise AssertionError(f"{where} is not whole JSON after retries") from None
                    time.sleep(0.1)
            keys, values = _keys_and_values(document)
            assert not keys & HIDDEN_KEYS, f"{where} carries {sorted(keys & HIDDEN_KEYS)}"
            assert str(SMOKE_VEHICLE_SEED) not in {str(v) for v in values}, (
                f"{where} carries the seed"
            )
            parsed_pending |= path.name == "pending.json"
        assert parsed_pending, f"{slug}'s pending.json was never read whole"


def test_no_agent_window_carries_the_world_s_identity(vehicle_stack):
    """The vehicle pinned before this adoption (`dd79e76`) wrote the scenario, seed, armed faults
    and their dwell into each window's `pending.json`. Checked again after the resume, below."""
    _assert_no_window_carries_the_world_s_identity(vehicle_stack)


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


def _results_for(stack, slug: str, marker: str) -> list[str]:
    output = stack.volumes / "diode" / "data" / slug / "output"
    return sorted(p.name for p in output.glob("*.txt") if marker in p.name)


def _submit(stack, slug: str, command: str) -> None:
    """As an agent submits: the whole file written aside, then renamed over console.json."""
    console = stack.volumes / "diode" / "data" / slug / "console.json"
    staging = console.with_name(".console.json.live.tmp")
    staging.write_text(json.dumps({"commands": [command]}) + "\n", encoding="utf-8")
    staging.replace(console)


def test_a_killed_console_resumes_the_same_world(vehicle_stack):
    stack = vehicle_stack
    # Past the first cadence checkpoint (every 50 ticks) and early in an interval, so a command
    # submitted now and the kill after it both fall inside the ticks the resume must replay.
    wait_for(
        lambda: _tick(stack) >= 60 and 5 <= _tick(stack) % 50 <= 20,
        timeout=START_SECONDS,
        every=0.1,
        what="a tick early in a checkpoint interval",
    )
    # One recorded command, run before the kill: the resume replays its cycle and must not run it
    # again, so it ends with exactly one result. An unknown verb is refused, and a refusal is a
    # result. (A batch replaced inside a claim can be erased, vehicle #39; then no result appears
    # here at all and this fails saying so.)
    marker = f"live_resume_{time.time_ns()}"
    _submit(stack, stack.slugs[0], f"{marker} probe")
    wait_for(
        lambda: _results_for(stack, stack.slugs[0], marker),
        timeout=30,
        every=0.1,
        what="a result for the submitted command (none: see vehicle #39 if this recurs)",
    )
    before = _executive(stack)
    frames = {slug: _newest_frame(stack, slug) for slug in stack.slugs}
    assert all(frames.values()), frames
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
        newest = {slug: _newest_frame(stack, slug) for slug in stack.slugs}
        fresh = all(
            frame and frame.get("boot_id") != frames[slug]["boot_id"]
            for slug, frame in newest.items()
        )
        return newest if fresh else None

    after_frames = wait_for(
        resumed, timeout=START_SECONDS, every=1, what="a frame from the new boot in every window"
    )
    after = _executive(stack)
    assert after["world_id"] == before["world_id"], "a restart resumes the world it was flying"
    assert after["tick"] > before["tick"], (before["tick"], after["tick"])
    for slug in stack.slugs:
        assert after_frames[slug]["seq"] > frames[slug]["seq"], f"{slug}'s frame sequence continues"
        assert _window_world(stack, slug) == before["world_id"], slug
    log = stack.logs("vehicle")
    assert f"resumed world {before['world_id']}" in log
    replayed = re.search(
        r"resumed world \S+ at tick \d+ \(checkpoint \S+ at tick \d+(?:, fell back)?, replayed (\d+)",
        log,
    )
    assert replayed and int(replayed[1]) > 0, "the resume replayed the ticks after its checkpoint"
    results = _results_for(stack, stack.slugs[0], marker)
    assert len(results) == 1, (
        f"a recorded command has exactly one result after the replay: {results}"
    )
    _assert_no_window_carries_the_world_s_identity(stack)


def test_docker_stop_reaches_the_vehicle_within_its_grace(vehicle_stack):
    stack = vehicle_stack
    # Running and advancing now, so a fast stop is the stop's doing and not a vehicle already gone.
    tick = _tick(stack)
    wait_for(lambda: _tick(stack) > tick, timeout=60, every=0.2, what="the vehicle to advance")
    container = stack.container_id("vehicle")
    started = time.monotonic()
    stack.compose("stop", "--timeout", "30", "vehicle")
    elapsed = time.monotonic() - started
    # Without docker-init the console would be PID 1, ignore SIGTERM, and wait out the 30 s.
    assert elapsed < 20, f"docker stop took {elapsed:.1f}s: the SIGTERM did not reach the console"
    state = stack.run(
        ["docker", "inspect", "-f", "{{.State.Status}} {{.State.OOMKilled}}", container]
    )
    assert state.stdout.split() == ["exited", "false"], state.stdout
