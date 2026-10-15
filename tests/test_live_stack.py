"""live/stack.py, offline: the files it writes and the docker calls it would make.

A fake runner stands in for subprocess.run, so nothing here starts a container. The one real
docker call is `compose config -q`, which only parses the generated override against the base.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live"))

import stack as stack_module  # noqa: E402


class Runner:
    def __init__(self, fail_on: str | None = None):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.fail_on and self.fail_on in argv:
            raise subprocess.CalledProcessError(1, argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")


@pytest.fixture
def stack(tmp_path):
    runner = Runner()
    smoke = stack_module.SmokeStack(
        3, {3: {"RECORDER_HOURLY_MAX": "4"}}, root=tmp_path / "smoke", runner=runner
    )
    yield smoke, runner
    smoke._torn_down = True


def test_prepare_makes_every_bind_source_for_three_agents(stack):
    smoke, _ = stack
    smoke.prepare()
    sys.path.insert(0, str(ROOT / "scripts"))
    import volume_images  # noqa: PLC0415

    for name in volume_images.names(["agent_1", "agent_2", "agent_3"]):
        assert (smoke.volumes / name / "data").is_dir(), name
    for slug in ("agent_1", "agent_2", "agent_3"):
        assert (smoke.volumes / "diode" / "data" / slug / "output").is_dir()
    assert smoke.cues.is_dir()


def test_the_smoke_env_file_carries_no_real_key_and_compose_is_pointed_at_it(stack):
    smoke, runner = stack
    smoke.prepare()
    env = dict(line.split("=", 1) for line in (smoke.root / "smoke.env").read_text().splitlines())
    assert env["OPENROUTER_API_KEY"] == "sk-smoke-dummy"
    assert env["LLM_BASE_URL"] == "http://stub:8199/v1"
    assert env["SPACE_VOLUMES_DIR"] == str(smoke.volumes)
    assert set(env) == {
        "OPENROUTER_API_KEY",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "SPACE_VOLUMES_DIR",
        "FLEET_SLUGS",
    }
    smoke.compose("ps")
    argv = runner.calls[-1][0]
    assert argv[argv.index("--env-file") + 1] == str(smoke.root / "smoke.env")


def test_compose_runs_with_an_allowlisted_environment_whatever_the_shell_exports(
    stack, monkeypatch
):
    smoke, runner = stack
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-real-key-in-the-shell")
    monkeypatch.setenv("LLM_BASE_URL", "http://elsewhere/v1")
    monkeypatch.setenv("DOCKER_HOST", "unix:///var/run/docker.sock")
    smoke.prepare()
    smoke.compose("ps")
    env = runner.calls[-1][1]["env"]
    assert "OPENROUTER_API_KEY" not in env
    assert "LLM_BASE_URL" not in env
    assert env["DOCKER_HOST"] == "unix:///var/run/docker.sock"
    assert "PATH" in env


def test_the_override_points_each_recorder_at_the_stub_and_keeps_the_fake_diode_off_worknet(
    stack,
):
    smoke, _ = stack
    text = smoke.override_text()
    for n in (1, 2, 3):
        assert (
            f"  recorder_{n}:\n    image: {stack_module.SMOKE_IMAGE}\n    depends_on: [stub]"
            in text
        )
    assert '      RECORDER_HOURLY_MAX: "4"' in text
    assert "windowside" not in text  # the base runs the fixture on no network
    assert 'VERIFY_STUB_DELAY_SECONDS: "2.0"' in text
    assert f"      - {smoke.cues}:/cues" in text
    assert "AGENT_SLUGS: agent_1,agent_2,agent_3" in text


def test_the_generated_override_parses_against_the_base_compose(stack):
    """Needs docker on the host, like `docker compose config -q` in CLAUDE.md: absent, it fails."""
    smoke, _ = stack
    smoke.prepare()
    real = stack_module.SmokeStack(3, root=smoke.root)
    real._torn_down = True
    result = real.compose("config", "-q", check=False)
    assert result.returncode == 0, result.stderr


def test_every_compose_call_names_the_smoke_project_and_env_file(stack):
    smoke, runner = stack
    smoke.prepare()
    smoke.up()
    argv = runner.calls[-1][0]
    assert argv[:4] == ["docker", "compose", "-p", smoke.project]
    assert smoke.project.startswith("space_chassis_smoke_")
    assert argv[-10:] == [
        "stub",
        "recorder_1",
        "recorder_2",
        "recorder_3",
        "agent_1",
        "agent_2",
        "agent_3",
        "diode",
        "fleet_monitor",
        "review",
    ]


def test_the_orchestrator_tears_down_even_when_setup_fails(tmp_path):
    runner = Runner(fail_on="build")
    smoke = stack_module.SmokeStack(
        3, root=tmp_path / "smoke", runner=runner, lock=tmp_path / "lock"
    )
    with pytest.raises(subprocess.CalledProcessError):
        smoke.start()
    assert any("down" in argv for argv, _ in runner.calls)
    assert not smoke.root.exists()


def test_down_twice_is_harmless(stack):
    smoke, runner = stack
    smoke.prepare()
    smoke._torn_down = False
    smoke.down()
    smoke.down()
    assert sum("down" in argv for argv, _ in runner.calls) == 1


def test_wait_for_raises_with_what_it_was_waiting_for():
    with pytest.raises(TimeoutError, match="waited 0.2s for the impossible"):
        stack_module.wait_for(lambda: False, timeout=0.2, every=0.05, what="the impossible")
    assert stack_module.wait_for(lambda: 7, timeout=1, what="seven") == 7


def test_every_docker_call_is_bounded_so_a_wedged_daemon_cannot_hang_the_suite(stack):
    smoke, runner = stack
    smoke.prepare()
    smoke.compose("ps")
    smoke.exec("agent_1", "true")
    smoke.build()
    for argv, kwargs in runner.calls:
        assert kwargs.get("timeout"), argv
    builds = [kwargs["timeout"] for argv, kwargs in runner.calls if "build" in argv]
    others = [kwargs["timeout"] for argv, kwargs in runner.calls if "build" not in argv]
    assert min(builds) > max(others)


def test_the_smoke_stack_builds_and_runs_its_own_image_tag(stack):
    smoke, _ = stack
    text = smoke.override_text()
    services = ["stub", "diode"] + [
        f"{kind}_{n}" for kind in ("agent", "recorder") for n in (1, 2, 3)
    ]
    sys.path.insert(0, str(ROOT / "tests"))
    import compose_text  # noqa: PLC0415

    parsed = compose_text.services(text)
    for service in services:
        assert parsed[service]["image"] == stack_module.SMOKE_IMAGE, service
    assert stack_module.SMOKE_IMAGE != "space-chassis-agent"
    assert ":" in stack_module.SMOKE_IMAGE


def test_the_smoke_build_leaves_the_operator_s_console_seed_as_it_found_it(tmp_path, monkeypatch):
    seed = tmp_path / "llm_console_seed.json"
    seed.write_text('{"operator": true}\n')
    monkeypatch.setattr(stack_module, "CONSOLE_SEED", seed)
    seen = []

    def runner(argv, **kwargs):
        if "build_console_seed.py" in " ".join(argv):
            seed.write_text('{"example": true}\n')
        if "build" in argv:
            seen.append(seed.read_text())
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    smoke = stack_module.SmokeStack(3, root=tmp_path / "smoke", runner=runner)
    smoke._torn_down = True
    smoke.build()
    assert seen == ['{"example": true}\n']
    assert seed.read_text() == '{"operator": true}\n'

    seed.unlink()
    smoke.build()
    assert not seed.exists()


def test_an_interrupted_teardown_is_retried_by_the_next_down(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        if "down" in argv and len([a for a in calls if "down" in a]) == 1:
            raise KeyboardInterrupt
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    smoke = stack_module.SmokeStack(3, root=tmp_path / "smoke", runner=runner)
    smoke.prepare()
    with pytest.raises(KeyboardInterrupt):
        smoke.down()
    assert smoke.root.exists()
    smoke.down()
    assert sum("down" in argv for argv in calls) == 2
    assert not smoke.root.exists()


def _resolved(smoke) -> dict:
    """The smoke project as compose resolves it: the base file, the override and the env file."""
    real = stack_module.SmokeStack(3, root=smoke.root)
    real._torn_down = True
    result = real.compose("config", "--format", "json", check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["services"]


def test_prepare_makes_the_bind_sources_the_monitor_and_review_need(stack):
    smoke, _ = stack
    smoke.prepare()
    services = _resolved(smoke)
    for name in ("fleet_monitor", "review"):
        binds = [v for v in services[name]["volumes"] if v["type"] == "bind"]
        assert binds, name
        for bind in binds:
            source = Path(bind["source"])
            if source.is_relative_to(smoke.root):
                assert source.is_dir(), (name, bind["source"])
    monitor = services["fleet_monitor"]["environment"]
    assert monitor["AGENT_SLUGS"] == "agent_1,agent_2,agent_3"
    assert monitor["QUIET_SECONDS"] == "20"
    assert services["fleet_monitor"]["image"] == stack_module.SMOKE_IMAGE


def test_the_smoke_review_publishes_no_port(stack):
    smoke, _ = stack
    smoke.prepare()
    review = _resolved(smoke)["review"]
    assert not review.get("ports")
    assert review["image"] == stack_module.SMOKE_IMAGE


def test_recreate_restarts_one_service_alone_with_an_extra_override(stack):
    smoke, runner = stack
    smoke.prepare()
    smoke.recreate("recorder_1", {"RECORDER_TOKEN_GLOBAL_HOURLY_MAX": "1"})
    argv = runner.calls[-1][0]
    assert argv[-5:] == ["up", "-d", "--force-recreate", "--no-deps", "recorder_1"]
    extra = smoke.root / "recreate-recorder_1.yml"
    assert argv[argv.index(str(extra)) - 1] == "-f"
    assert extra.read_text() == (
        'services:\n  recorder_1:\n    environment:\n      RECORDER_TOKEN_GLOBAL_HOURLY_MAX: "1"\n'
    )


def test_every_compose_call_after_a_recreate_keeps_its_override(stack):
    # A later `up` or `exec` without the extra file would describe a different recorder_1.
    smoke, runner = stack
    smoke.prepare()
    smoke.recreate("recorder_1", {"RECORDER_TOKEN_GLOBAL_HOURLY_MAX": "1"})
    assert str(smoke.root / "recreate-recorder_1.yml") in smoke.compose_command("ps")


def test_a_recreate_override_parses_against_the_base_compose(stack):
    """Needs docker on the host, like `docker compose config -q` in CLAUDE.md: absent, it fails."""
    smoke, _ = stack
    smoke.prepare()
    smoke.recreate("recorder_1", {"RECORDER_TOKEN_GLOBAL_HOURLY_MAX": "1"})
    real = stack_module.SmokeStack(3, root=smoke.root)
    real._torn_down = True
    real.overrides = list(smoke.overrides)
    result = real.compose("config", check=False)
    assert result.returncode == 0, result.stderr
    assert 'RECORDER_TOKEN_GLOBAL_HOURLY_MAX: "1"' in result.stdout


def test_a_recreate_value_reaches_compose_exactly_whatever_it_holds(stack):
    """Needs docker on the host, like `docker compose config -q` in CLAUDE.md: absent, it fails."""
    smoke, _ = stack
    smoke.prepare()
    awkward = 'a"b$c\\d'
    smoke.recreate("recorder_1", {"RECORDER_TOKEN_GLOBAL_HOURLY_MAX": awkward})
    real = stack_module.SmokeStack(3, root=smoke.root)
    real._torn_down = True
    real.overrides = list(smoke.overrides)
    result = real.compose("config", "--format", "json", check=False)
    assert result.returncode == 0, result.stderr
    environment = json.loads(result.stdout)["services"]["recorder_1"]["environment"]
    # The printed configuration is itself a compose file, so a literal dollar is printed as `$$`;
    # an unescaped `$c` would have been interpolated away.
    assert environment["RECORDER_TOKEN_GLOBAL_HOURLY_MAX"] == awkward.replace("$", "$$")


@pytest.fixture
def vehicle_stack(tmp_path):
    runner = Runner()
    smoke = stack_module.SmokeStack(3, root=tmp_path / "smoke", runner=runner, window="vehicle")
    yield smoke, runner
    smoke._torn_down = True


def test_a_stack_names_its_window_and_refuses_any_other():
    with pytest.raises(ValueError, match="window"):
        stack_module.SmokeStack(3, window="probe")


def test_a_vehicle_stack_runs_the_vehicle_in_place_of_the_fixture(vehicle_stack):
    smoke, runner = vehicle_stack
    smoke.prepare()
    smoke.up()
    argv = runner.calls[-1][0]
    profiles = [argv[i + 1] for i, word in enumerate(argv) if word == "--profile"]
    assert profiles == ["fleet", "vehicle"], profiles
    assert "vehicle" in argv[argv.index("up") :] and "diode" not in argv[argv.index("up") :]


def test_the_vehicle_override_runs_the_vehicle_s_smoke_image_on_a_short_poll(vehicle_stack):
    smoke, _ = vehicle_stack
    text = smoke.override_text()
    assert "  vehicle:\n" in text and "  diode:\n" not in text
    block = text[text.index("  vehicle:\n") :]
    # The vehicle has its own image (plan 8): the agents' carries nothing of it to serve.
    assert f"    image: {stack_module.SMOKE_VEHICLE_IMAGE}\n" in block
    assert stack_module.SMOKE_VEHICLE_IMAGE != "space-chassis-vehicle"
    assert ":" in stack_module.SMOKE_VEHICLE_IMAGE
    # A checkpoint every 50 ticks has to come in seconds, not the operator's minutes.
    assert 'DIODE_POLL_SECONDS: "0.2"' in block


def test_the_smoke_build_builds_the_vehicle_s_image_only_when_it_is_the_window(tmp_path):
    def builds(window):
        runner = Runner()
        smoke = stack_module.SmokeStack(3, root=tmp_path / window, runner=runner, window=window)
        smoke._torn_down = True
        smoke.build()
        calls = [argv for argv, _ in runner.calls if "build" in argv]
        return [argv[argv.index("build") + 1 :] for argv in calls]

    # One build at a time (Governance, 2026-10-11): compose builds the services one call names in
    # parallel, so the vehicle's image is its own call, after the agents'.
    assert builds("vehicle") == [["agent_1"], ["vehicle"]]
    assert builds("diode") == [["agent_1"]]


@pytest.mark.parametrize("window", stack_module.WINDOWS)
def test_every_service_the_smoke_stack_starts_is_capped_and_the_sum_is_in_budget(tmp_path, window):
    """Needs docker on the host, like `docker compose config -q` in CLAUDE.md: absent, it fails.
    The caps compose resolves from the base and the override together, for what `up` starts."""
    smoke = stack_module.SmokeStack(3, root=tmp_path / "smoke", window=window)
    smoke._torn_down = True
    smoke.prepare()
    result = smoke.compose("config", "--format", "json", check=False)
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    cpus = memory = 0
    for name in smoke.services():
        service = services[name]
        assert float(service["cpus"]) > 0, name
        assert int(service["mem_limit"]) > 0, name
        assert service["memswap_limit"] == service["mem_limit"], f"{name} may swap past its cap"
        cpus += float(service["cpus"])
        memory += int(service["mem_limit"])
    assert cpus <= stack_module.STACK_CPUS + 1e-9, cpus
    assert memory <= stack_module.STACK_MEMORY, memory
    # Inside Governance's 5 CPUs and 14 GiB with the other enforced shares -- the containment
    # check's image sweep and the host side's user scope -- and a reserve left for the daemon.
    sweep_cpus = float(stack_module.SWEEP_CPUS)
    sweep_memory = stack_module.memory_bytes(stack_module.SWEEP_MEMORY)
    enforced_cpus = stack_module.STACK_CPUS + sweep_cpus + stack_module.HOST_CPUS
    enforced_memory = stack_module.STACK_MEMORY + sweep_memory + stack_module.HOST_MEMORY
    assert enforced_cpus < stack_module.BUDGET_CPUS, enforced_cpus
    assert enforced_memory < stack_module.BUDGET_MEMORY, enforced_memory


def test_the_containment_check_s_image_sweep_runs_under_the_sweep_caps():
    text = (ROOT / "scripts" / "verify_containment.sh").read_text(encoding="utf-8")
    sweep = next(line for line in text.splitlines() if "space_chassis.sweep=" in line)
    memory = stack_module.SWEEP_MEMORY
    caps = f"--cpus {stack_module.SWEEP_CPUS} --memory {memory} --memory-swap {memory}"
    assert caps in sweep, sweep
    # The readback the script demands is these caps as the kernel writes them: quota per 100 ms
    # period, memory in bytes, and no swap past it.
    quota = round(float(stack_module.SWEEP_CPUS) * 100000)
    expected = f"{quota} 100000|{stack_module.memory_bytes(memory)}|0"
    assert f'[ "$limits" != "{expected}" ]' in text, expected


def test_the_live_run_s_scope_command_caps_what_the_conftest_requires():
    command = stack_module.HOST_SCOPE_COMMAND
    assert f"CPUQuota={round(stack_module.HOST_CPUS * 100)}%" in command
    assert f"MemoryMax={stack_module.HOST_MEMORY >> 30}G" in command
    assert command.endswith("python3 -m pytest live -q")
    assert "MemorySwapMax=0" in command
    # Every place that tells someone how to run the live suite gives the command the fixtures accept.
    for name in (
        "README.md",
        "CLAUDE.md",
        "AGENTS.md",
        "governance/chassis/practice.md",
        "docker-compose.override.example.yml",
    ):
        assert command in (ROOT / name).read_text(encoding="utf-8"), name


def test_cgroup_limits_reads_cpus_memory_and_swap(tmp_path):
    (tmp_path / "cpu.max").write_text("75000 100000\n")
    (tmp_path / "memory.max").write_text("3221225472\n")
    (tmp_path / "memory.swap.max").write_text("0\n")
    assert stack_module.cgroup_limits(tmp_path) == (0.75, 3 << 30, 0)
    (tmp_path / "cpu.max").write_text("max 100000\n")
    (tmp_path / "memory.max").write_text("max\n")
    (tmp_path / "memory.swap.max").unlink()
    assert stack_module.cgroup_limits(tmp_path) == (-1.0, -1, None)


def test_the_guard_asks_the_daemon_with_a_template_it_can_execute(tmp_path):
    """Needs docker on the host. `.Labels` is a string in `docker ps --format`; `.Label` is the
    lookup. Run against every container the daemon has, so a template error cannot hide behind an
    empty listing."""
    runner = Runner()
    smoke = stack_module.SmokeStack(3, root=tmp_path / "smoke", runner=runner)
    smoke._torn_down = True
    smoke.others_running()
    template = '{{.Label "com.docker.compose.project"}}'
    asked = [argv for argv, _ in runner.calls]
    assert [
        "docker",
        "ps",
        "--filter",
        "label=com.docker.compose.project",
        "--format",
        template,
    ] in asked
    sweep = f'{{{{.Label "{stack_module.SWEEP_LABEL}"}}}}'
    assert [
        "docker",
        "ps",
        "--filter",
        f"label={stack_module.SWEEP_LABEL}",
        "--format",
        sweep,
    ] in asked
    result = subprocess.run(
        ["docker", "ps", "--all", "--format", template],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_a_second_stack_is_refused_while_the_first_holds_the_lock(tmp_path):
    lock = tmp_path / "lock"
    first = stack_module.SmokeStack(3, root=tmp_path / "one", runner=Runner(), lock=lock)
    second = stack_module.SmokeStack(3, root=tmp_path / "two", runner=Runner(), lock=lock)
    first._hold_the_lock()
    with pytest.raises(RuntimeError, match="one smoke stack at a time: another holds"):
        second.start()
    first.down()
    second.start()
    assert second._lock_fd is not None
    second.down()
    assert second._lock_fd is None


def test_the_guard_looks_again_after_the_build(tmp_path):
    class Late(Daemon):
        def __call__(self, argv, **kwargs):
            if any("build" in a for a, _ in self.calls):
                self.projects = "space_chassis_smoke_2\n"
            return super().__call__(argv, **kwargs)

    runner = Late()
    smoke = stack_module.SmokeStack(
        3, root=tmp_path / "smoke", runner=runner, lock=tmp_path / "lock"
    )
    with pytest.raises(RuntimeError, match="space_chassis_smoke_2 is running"):
        smoke.start()
    assert any("build" in argv for argv, _ in runner.calls)
    assert not any("up" in argv for argv, _ in runner.calls)
    assert smoke._lock_fd is None


def test_a_stack_without_a_per_user_runtime_directory_refuses_rather_than_guessing(tmp_path):
    smoke = stack_module.SmokeStack(
        3, root=tmp_path / "smoke", runner=Runner(), lock=tmp_path / "absent" / "lock"
    )
    smoke._torn_down = True
    with pytest.raises(RuntimeError, match="no per-user runtime directory"):
        smoke.start()
    assert stack_module.SMOKE_LOCK.parent == Path(f"/run/user/{os.getuid()}")


def test_the_scope_check_takes_the_tightest_limit_on_the_cgroup_s_path(tmp_path):
    root = tmp_path / "cgroup"
    parent, leaf = root / "user.slice", root / "user.slice" / "run.scope"
    leaf.mkdir(parents=True)
    for directory, cpu, memory, swap in (
        (parent, "35000 100000", "1073741824", "0"),
        (leaf, "max 100000", "max", "max"),
    ):
        (directory / "cpu.max").write_text(cpu + "\n")
        (directory / "memory.max").write_text(memory + "\n")
        (directory / "memory.swap.max").write_text(swap + "\n")
    assert stack_module.effective_limits(leaf, root) == (0.35, 1 << 30, 0)
    assert stack_module.effective_limits(root / "elsewhere", root) == (-1.0, -1, None)


class Daemon(Runner):
    """A daemon with running containers: `projects` carry the compose project label, `sweeps` the
    containment sweep's, and `sweep_ids` answer `docker ps -q` for this stack's sweeps."""

    def __init__(self, projects="", sweeps="", sweep_ids="", fail_on=None):
        super().__init__(fail_on)
        self.projects, self.sweeps, self.sweep_ids = projects, sweeps, sweep_ids

    def __call__(self, argv, **kwargs):
        if argv[:2] == ["docker", "ps"]:
            self.calls.append((argv, kwargs))
            if "-q" in argv:
                out = self.sweep_ids
            elif "label=com.docker.compose.project" in argv:
                out = self.projects
            else:
                out = self.sweeps
            return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")
        return super().__call__(argv, **kwargs)


def test_a_stack_will_not_start_beside_another_smoke_stack(tmp_path):
    runner = Daemon(projects="space_chassis_smoke_1_vehicle\nspace-chassis\n")
    smoke = stack_module.SmokeStack(
        3, root=tmp_path / "smoke", runner=runner, lock=tmp_path / "lock"
    )
    smoke._torn_down = True
    with pytest.raises(
        RuntimeError, match="one smoke stack at a time: space_chassis_smoke_1_vehicle"
    ):
        smoke.start()
    assert not any("build" in argv or "up" in argv for argv, _ in runner.calls)


def test_a_stack_will_not_start_beside_a_running_containment_sweep(tmp_path):
    runner = Daemon(sweeps="space_chassis_smoke_9\n")
    smoke = stack_module.SmokeStack(
        3, root=tmp_path / "smoke", runner=runner, lock=tmp_path / "lock"
    )
    smoke._torn_down = True
    with pytest.raises(RuntimeError, match=r"a containment sweep \(space_chassis_smoke_9\)"):
        smoke.start()
    assert not any("build" in argv for argv, _ in runner.calls)


def test_a_stack_ignores_its_own_project_and_the_operator_s(tmp_path):
    smoke = stack_module.SmokeStack(3, root=tmp_path / "smoke")
    smoke._torn_down = True
    smoke._runner = Daemon(projects=f"{smoke.project}\nspace-chassis\n")
    assert smoke.others_running() == []


class Leftover(Daemon):
    """A daemon whose `docker rm -f` removes the sweep unless `stuck`, and whose listings of a
    stack's containers (`ps -a -q`) answer from what is left."""

    def __init__(self, sweep_ids="", stuck=False, listing_rc=0):
        super().__init__(sweep_ids=sweep_ids)
        self.stuck, self.listing_rc = stuck, listing_rc

    def __call__(self, argv, **kwargs):
        if argv[:3] == ["docker", "rm", "-f"]:
            self.calls.append((argv, kwargs))
            if not self.stuck:
                self.sweep_ids = ""
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv[:4] == ["docker", "ps", "-a", "-q"]:
            self.calls.append((argv, kwargs))
            out = self.sweep_ids if stack_module.SWEEP_LABEL in argv[-1] else ""
            return subprocess.CompletedProcess(argv, self.listing_rc, stdout=out, stderr="")
        return super().__call__(argv, **kwargs)


def test_down_removes_a_containment_sweep_its_tests_left_running(tmp_path):
    runner = Leftover(sweep_ids="abc123\n")
    smoke = stack_module.SmokeStack(3, root=tmp_path / "smoke", runner=runner)
    smoke.prepare()
    smoke.down()
    listed = [argv[-1] for argv, _ in runner.calls if argv[:4] == ["docker", "ps", "-a", "-q"]]
    sweeps = f"label={stack_module.SWEEP_LABEL}={smoke.project}"
    # Stopped sweeps are removed too (`ps -a`), then the project and its sweeps are checked gone.
    assert listed == [sweeps, f"label=com.docker.compose.project={smoke.project}", sweeps]
    assert ["docker", "rm", "-f", "abc123"] in [argv for argv, _ in runner.calls]
    assert not smoke.root.exists()


def test_a_teardown_that_leaves_a_container_behind_is_not_complete_and_is_retried(tmp_path):
    runner = Leftover(sweep_ids="abc123\n", stuck=True)
    smoke = stack_module.SmokeStack(
        3, root=tmp_path / "smoke", runner=runner, lock=tmp_path / "lock"
    )
    smoke.settle_seconds = 0
    smoke.prepare()
    smoke._hold_the_lock()
    with pytest.raises(RuntimeError, match="teardown is not complete: .*abc123"):
        smoke.down()
    assert smoke.root.exists() and not smoke._torn_down and smoke._lock_fd is None
    runner.stuck = False
    smoke.down()
    assert not smoke.root.exists()


def test_a_teardown_whose_listing_fails_is_not_taken_as_complete(tmp_path):
    runner = Leftover(listing_rc=1)
    smoke = stack_module.SmokeStack(3, root=tmp_path / "smoke", runner=runner)
    smoke.settle_seconds = 0
    smoke.prepare()
    with pytest.raises(RuntimeError, match="the listing failed"):
        smoke.down()
    assert smoke.root.exists()
    smoke._torn_down = True


def test_the_containment_check_labels_its_sweep_with_the_stack_s_project(tmp_path):
    smoke = stack_module.SmokeStack(3, root=tmp_path / "smoke", runner=Runner())
    smoke._torn_down = True
    env = smoke.containment_environment()
    assert env["SWEEP_LABEL"] == smoke.project
    assert env["AGENTS"] == "agent_1 agent_2 agent_3"
    assert env["COMPOSE"] == " ".join(smoke.compose_command())
    text = (ROOT / "scripts" / "verify_containment.sh").read_text(encoding="utf-8")
    sweep = next(line for line in text.splitlines() if "space_chassis.sweep=" in line)
    assert f'--label "{stack_module.SWEEP_LABEL}=${{SWEEP_LABEL:-operator}}"' in sweep


def test_a_vehicle_stack_has_its_own_project_and_root(tmp_path):
    diode = stack_module.SmokeStack(3, runner=Runner())
    vehicle = stack_module.SmokeStack(3, runner=Runner(), window="vehicle")
    diode._torn_down = vehicle._torn_down = True
    assert vehicle.project != diode.project and vehicle.project.endswith("_vehicle")
    assert vehicle.root != diode.root


def test_the_vehicle_override_parses_against_the_base_compose(vehicle_stack):
    """Needs docker on the host, like `docker compose config -q` in CLAUDE.md: absent, it fails."""
    smoke, _ = vehicle_stack
    smoke.prepare()
    real = stack_module.SmokeStack(3, root=smoke.root, window="vehicle")
    real._torn_down = True
    result = real.compose("config", "--format", "json", check=False)
    assert result.returncode == 0, result.stderr
    vehicle = json.loads(result.stdout)["services"]["vehicle"]
    assert vehicle["image"] == stack_module.SMOKE_VEHICLE_IMAGE
    assert vehicle["build"]["target"] == "vehicle"
    assert vehicle["environment"]["VEHICLE_SLUGS"] == "agent_1,agent_2,agent_3"


def _ended(pidfile, seconds: float = 5.0) -> bool:
    """The process whose pid the child wrote is gone (or a zombie), within a bound."""
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except OSError:
            return True
        if state == "Z":
            return True
        time.sleep(0.05)
    return False


def _child(tmp_path) -> tuple[str, Path, Path, Path]:
    """A background child that says it started (its pid), then acts two seconds later; it
    keeps the group's stdout and stderr open, as a real straggler would."""
    ready, pidfile, late = tmp_path / "ready", tmp_path / "pid", tmp_path / "late"
    child = f"sh -c 'echo $$ > {pidfile}; touch {ready}; sleep 2; touch {late}' &"
    return child, ready, pidfile, late


def test_a_timed_out_group_leaves_nothing_behind_that_can_act_later(tmp_path):
    """The containment check's timeout must not leave a waiting subshell to launch a sweep after
    the test has moved on: run_group kills the whole process group."""
    child, ready, pidfile, late = _child(tmp_path)
    script = f"{child} while [ ! -e {ready} ]; do sleep 0.05; done; sleep 30"
    with pytest.raises(subprocess.TimeoutExpired):
        stack_module.run_group(["sh", "-c", script], env=dict(os.environ), cwd=tmp_path, timeout=1)
    assert ready.exists(), "the child never started, so this proves nothing"
    assert _ended(pidfile), "the child outlived the timeout"
    time.sleep(2.5)
    assert not late.exists(), "a descendant outlived the timeout and acted"


def test_a_finished_group_s_stragglers_are_killed_too(tmp_path):
    """The leader exits while a child still holds its output open: the group is killed at the
    leader's exit, not after the child has finished."""
    child, ready, pidfile, late = _child(tmp_path)
    script = f"{child} while [ ! -e {ready} ]; do sleep 0.05; done; echo started"
    began = time.monotonic()
    result = stack_module.run_group(
        ["sh", "-c", script], env=dict(os.environ), cwd=tmp_path, timeout=10
    )
    assert time.monotonic() - began < 1.5, "the wait outlasted the leader"
    assert result.returncode == 0 and result.stdout.strip() == "started"
    assert _ended(pidfile), "the straggler outlived its leader"
    time.sleep(2.5)
    assert not late.exists(), "a straggler outlived its leader and acted"


def test_the_live_tests_run_the_containment_check_in_its_own_group():
    for name in ("test_containment.py", "test_vehicle.py"):
        text = (ROOT / "live" / name).read_text(encoding="utf-8")
        assert "stack.containment_check()" in text and "verify_containment.sh" not in text, name
