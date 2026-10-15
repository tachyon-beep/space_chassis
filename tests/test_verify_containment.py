"""scripts/verify_containment.sh, offline: run for real against a fake `docker` on PATH.

The fake records every argv it is given and whatever arrives on its stdin, answers the few
questions the script asks (which services run, which container is which, the recorder's
environment) with a sentinel standing in for the real key, and fails everything else. Whether the
probes pass is a question for a live stack; what these tests hold is where the key travels: on a
pipe, never in an argv, never on the script's own output.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "verify_containment.sh"
SENTINEL = "sk-or-v1-sentinel-not-a-real-key-0123456789"

FAKE_DOCKER = r"""#!/bin/sh
{ printf '%s' "$*" | tr '\n' ' '; printf '\n'; } >> "$CALLS"
case " $* " in
    *" exec "*) cat >> "$STDIN_LOG" ;;
esac
case "$*" in
    *inspect*Config.Env*)
        printf 'PATH=/usr/bin\nOPENROUTER_API_KEY=%s\nLLM_API_KEY=\n' "$SENTINEL"; exit 0 ;;
    *" config"*)
        printf 'services:\n  recorder_1:\n    environment:\n      OPENROUTER_API_KEY: %s\n' "$SENTINEL"
        exit 0 ;;
    *" ps --format"*)
        printf '%b' "${SERVICES-agent_1\nagent_2\nrecorder_1\nrecorder_2\n}"; exit 0 ;;
    *" ps -q "*)
        for last in "$@"; do :; done
        case " ${ABSENT:-} " in *" $last "*) exit 0 ;; esac
        printf 'cid-%s\n' "$last"; exit 0 ;;
    *" exec "*" tar "*)
        [ -n "${TAR_CONTENT:-}" ] || exit 1
        printf '%s' "$TAR_CONTENT"
        # A whole archive ends in two zero blocks; a stream cut off mid-way does not.
        [ -n "${TAR_TRUNCATED:-}" ] || head -c 1024 /dev/zero
        exit 0 ;;
    *" exec "*"/opt/vehicle"*)
        [ -n "${VEHICLE_SIGHT:-}" ] || exit 1
        echo "$VEHICLE_SIGHT"; exit 0 ;;
    *" exec "*getent*)
        [ -n "${GETENT_RC:-}" ] || exit 1
        echo "rc=$GETENT_RC"; exit 0 ;;
esac
exit 1
"""


class Run:
    def __init__(self, root: Path):
        self.root = root
        self.calls = root / "calls.log"
        self.stdin_log = root / "stdin.log"
        self.calls.write_text("")
        self.stdin_log.write_text("")
        bin_dir = root / "bin"
        bin_dir.mkdir()
        docker = bin_dir / "docker"
        docker.write_text(FAKE_DOCKER)
        docker.chmod(0o755)
        self.path = f"{bin_dir}:{os.environ['PATH']}"

    def __call__(self, **extra) -> subprocess.CompletedProcess:
        env = {
            "PATH": self.path,
            "HOME": str(self.root),
            "CALLS": str(self.calls),
            "STDIN_LOG": str(self.stdin_log),
            "SENTINEL": SENTINEL,
            **extra,
        }
        return subprocess.run(
            ["sh", str(SCRIPT)],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def argv_lines(self) -> list[str]:
        return self.calls.read_text().splitlines()

    def exec_targets(self) -> set[str]:
        """The service each `compose exec` ran in: the word after `exec` and its flag."""
        targets = set()
        for line in self.argv_lines():
            words = line.split()
            if "exec" in words:
                after = words[words.index("exec") + 1 :]
                targets.add(after[1] if after[0] in ("-T", "-d") else after[0])
        return targets


@pytest.fixture
def run(tmp_path):
    return Run(tmp_path)


def test_verify_containment_passes_no_secret_in_any_argv(run):
    run(COMPOSE="docker compose -p probe", AGENTS="agent_1", TAR_CONTENT="file bytes")
    lines = run.argv_lines()
    assert lines, "the script made no docker calls"
    assert not [line for line in lines if SENTINEL in line]


def test_the_real_key_never_enters_an_agent_container(run):
    """The agent is what is contained: a key piped into a process there is a key handed to it."""
    result = run(COMPOSE="docker compose -p probe", AGENTS="agent_1", TAR_CONTENT="file bytes")
    assert SENTINEL not in run.stdin_log.read_text()
    assert "PASS  agent_1 has no trace of its recorder's real key" in result.stdout


def test_a_real_key_on_an_agent_s_disk_is_a_failure(run):
    planted = f"header {SENTINEL} trailer"
    result = run(COMPOSE="docker compose -p probe", AGENTS="agent_1", TAR_CONTENT=planted)
    assert "FAIL  agent_1 holds its recorder's real key on disk" in result.stdout
    assert result.returncode == 1
    assert SENTINEL not in result.stdout + result.stderr


def test_a_probe_that_cannot_run_is_a_failure_never_a_pass(run):
    """Every exec fails with no output: a check that cannot run must not report the wall holds."""
    result = run(COMPOSE="docker compose -p probe", AGENTS="agent_1")
    assert "PASS" not in result.stdout, result.stdout
    assert result.returncode == 1


def test_the_script_never_echoes_the_key(run):
    result = run(COMPOSE="docker compose -p probe", AGENTS="agent_1 agent_2")
    assert SENTINEL not in result.stdout
    assert SENTINEL not in result.stderr
    assert "real key" in result.stdout


def test_the_script_takes_its_compose_command_and_agents_from_the_environment(run):
    prefix = "compose -p probe_project --env-file /nonexistent/smoke.env"
    run(COMPOSE=f"docker {prefix}", AGENTS="agent_2")
    lines = run.argv_lines()
    assert lines
    for line in lines:
        assert line.startswith(prefix) or line.startswith("inspect "), line
    assert run.exec_targets() == {"agent_2", "review"}
    assert not [line for line in lines if " ps -q agent_1" in line]


def test_without_agents_it_checks_every_running_agent(run):
    run(COMPOSE="docker compose -p probe")
    assert run.exec_targets() == {"agent_1", "agent_2", "review"}


def test_a_run_that_checked_no_agent_is_not_a_success(run):
    result = run(COMPOSE="docker compose -p probe", SERVICES="recorder_1\\n")
    assert result.returncode == 2
    assert "no agent" in result.stdout + result.stderr
    result = run(COMPOSE="docker compose -p probe", AGENTS="agent_9", ABSENT="agent_9")
    assert result.returncode == 2


def test_a_truncated_archive_is_not_a_clean_search(run):
    result = run(
        COMPOSE="docker compose -p probe",
        AGENTS="agent_1",
        TAR_CONTENT="file bytes",
        TAR_TRUNCATED="1",
    )
    assert "FAIL  agent_1 could not be searched for its recorder's real key" in result.stdout


def test_a_resolver_probe_that_is_missing_its_binary_is_a_failure(run):
    result = run(COMPOSE="docker compose -p probe", AGENTS="agent_1", GETENT_RC="127")
    assert "PASS  agent_1 cannot resolve outside names" not in result.stdout
    assert "FAIL  agent_1 could not be probed for name resolution" in result.stdout
    result = run(COMPOSE="docker compose -p probe", AGENTS="agent_1", GETENT_RC="2")
    assert "PASS  agent_1 cannot resolve outside names" in result.stdout


def test_an_agent_that_can_see_the_vehicle_is_a_failure(run):
    """John, 2026-10-10: no risk of information sharing. An agent's image carries nothing of it."""
    absent = run(COMPOSE="docker compose -p probe", AGENTS="agent_1", VEHICLE_SIGHT="absent")
    assert "PASS  agent_1 has no vehicle in its image" in absent.stdout
    present = run(COMPOSE="docker compose -p probe", AGENTS="agent_1", VEHICLE_SIGHT="present")
    assert "FAIL  agent_1 can read the vehicle" in present.stdout
    silent = run(COMPOSE="docker compose -p probe", AGENTS="agent_1")
    assert "FAIL  agent_1 could not be probed for the vehicle" in silent.stdout


def test_the_vehicle_probe_says_nothing_when_it_cannot_run(run, tmp_path):
    """The probe's own text, run where none of its tools exist, must not read as an absence."""
    run(COMPOSE="docker compose -p probe", AGENTS="agent_1")
    probe = next(line for line in run.argv_lines() if "/opt/vehicle" in line)
    script = probe.split(" -c ", 1)[1]
    empty = tmp_path / "empty-path"
    empty.mkdir()
    out = subprocess.run(
        ["/bin/sh", "-c", script],
        env={"PATH": str(empty)},
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    assert out.splitlines()[-1:] != ["absent"], out
