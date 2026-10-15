"""live/stack.py, offline: the files it writes and the docker calls it would make.

A fake runner stands in for subprocess.run, so nothing here starts a container. The one real
docker call is `compose config -q`, which only parses the generated override against the base.
"""

import json
import subprocess
import sys
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
    smoke = stack_module.SmokeStack(3, root=tmp_path / "smoke", runner=runner)
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
