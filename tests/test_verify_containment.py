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
    *inspect*.Image*)
        [ -n "${IMAGE_ID:-}" ] || exit 1
        echo "$IMAGE_ID"; exit 0 ;;
    *"--entrypoint find"*)
        printf '%b' "${IMAGE_SWEEP:-}"; exit "${IMAGE_SWEEP_RC:-1}" ;;
    *inspect*.Source*)
        [ -n "${MOUNT_SOURCES:-}" ] || exit 1
        printf '%s' "$MOUNT_SOURCES"; exit 0 ;;
    *inspect*.Destination*)
        [ -n "${VEHICLE_BINDS:-}" ] || exit 1
        printf '%s' "$VEHICLE_BINDS"; exit 0 ;;
    *" exec "*"/diode/.probe"*)
        [ -n "${DIODE_ROOT_VERDICT:-}" ] || exit 1
        echo "$DIODE_ROOT_VERDICT"; exit 0 ;;
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


SENTINEL_PATH = "/usr/local/bin/entrypoint.sh"


def _swept(run, sweep, rc="0", image="sha256:img"):
    env = {
        "COMPOSE": "docker compose -p probe",
        "AGENTS": "agent_1",
        "IMAGE_SWEEP": sweep,
        "IMAGE_SWEEP_RC": rc,
    }
    if image:
        env["IMAGE_ID"] = image
    return run(**env).stdout


def test_an_agent_that_can_see_the_vehicle_is_a_failure(run):
    """John, 2026-10-10: no risk of information sharing. The agent's image is swept host-side, as
    root in a throwaway container: the sentinel alone, from a search that completed, is absent."""
    assert "PASS  agent_1 has no vehicle in its image" in _swept(run, SENTINEL_PATH + "\\n")
    leaked = _swept(run, SENTINEL_PATH + "\\n/opt/vehicle\\n")
    assert "FAIL  agent_1 can read the vehicle" in leaked


def test_a_partial_or_unrun_sweep_is_a_failure_never_an_absence(run):
    unprobed = "FAIL  agent_1 could not be probed for the vehicle"
    # The sentinel, then the search failed part-way: it proves one path, not the whole image.
    assert unprobed in _swept(run, SENTINEL_PATH + "\\n", rc="1")
    assert unprobed in _swept(run, SENTINEL_PATH + "\\n", rc="137")
    assert unprobed in _swept(run, "", rc="0")  # no sentinel: the search did not run as written
    assert unprobed in _swept(run, SENTINEL_PATH + "\\n", image="")  # no image to sweep


def _sweep_args(run) -> list[str]:
    """The find arguments the script passes, read from the docker call it made."""
    _swept(run, SENTINEL_PATH + "\\n")
    line = next(
        line for line in run.argv_lines() if " run " in f" {line} " and "--entrypoint find" in line
    )
    words = line.split()
    return words[words.index("sha256:img") + 1 :]


def _find_under(args: list[str], root) -> list[str]:
    rooted = [
        str(root)
        if a == "/"
        else a.replace(SENTINEL_PATH, f"{root}{SENTINEL_PATH}").replace(
            "/opt/vehicle", f"{root}/opt/vehicle"
        )
        for a in args
    ]
    result = subprocess.run(["find", *rooted], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return [line.removeprefix(str(root)) for line in result.stdout.splitlines()]


def test_the_sweep_finds_its_sentinel_and_every_vehicle_file_it_names(run, tmp_path):
    args = _sweep_args(run)
    root = tmp_path / "image"
    (root / "usr" / "local" / "bin").mkdir(parents=True)
    (root / "usr" / "local" / "bin" / "entrypoint.sh").write_text("#!/bin/sh\n")
    assert _find_under(args, root) == [SENTINEL_PATH]
    planted = [
        "/opt/vehicle",
        "/usr/local/bin/serve_vehicle.sh",
        "/srv/a/mission.yaml",
        "/srv/b/vehicle.yaml",
        "/srv/c/coupling.yaml",
        "/srv/d/plant.md",
        "/srv/e/fault_policy.yaml",
    ]
    for path in planted:
        target = root / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("vehicle")
    assert sorted(_find_under(args, root)) == sorted([SENTINEL_PATH, *planted])


def test_an_agent_that_mounts_the_vehicle_s_state_is_a_failure(run):
    """Read host-side: an agent's own /state makes the target useless from inside."""
    clean = run(
        COMPOSE="docker compose -p probe",
        AGENTS="agent_1",
        MOUNT_SOURCES="/v/state_x/data /v/diode/data/x ",
    )
    assert "PASS  agent_1 mounts nothing of the vehicle's private state" in clean.stdout
    leaked = run(
        COMPOSE="docker compose -p probe",
        AGENTS="agent_1",
        MOUNT_SOURCES="/v/state_x/data /v/vehicle_state/data ",
    )
    assert "FAIL  agent_1 mounts the vehicle's private state" in leaked.stdout
    blind = run(COMPOSE="docker compose -p probe", AGENTS="agent_1")
    assert "FAIL  agent_1's mounts could not be inspected" in blind.stdout


def test_an_agent_that_mounts_the_vehicle_s_source_is_a_failure(run):
    """John, 2026-10-10: no risk of information sharing. The image carries none of the vehicle, so
    a bind from a vehicle checkout, or of a directory holding this one's, is the way back."""
    probe = {"COMPOSE": "docker compose -p probe", "AGENTS": "agent_1"}
    clean = run(**probe, MOUNT_SOURCES="/v/state_x/data /v/diode/data/x /srv/build_x ")
    assert "PASS  agent_1 mounts nothing of the vehicle's source" in clean.stdout
    for leak in (
        "/home/someone/space_chassis/docs/deep_research/vehicle",
        "/elsewhere/docs/deep_research/vehicle/tools",
        str(REPO),
        str(REPO / "docs"),
        "/",
    ):
        leaked = run(**probe, MOUNT_SOURCES=f"/v/state_x/data {leak} ")
        assert "FAIL  agent_1 mounts the vehicle's source" in leaked.stdout, leak
    blind = run(**probe)
    assert "FAIL  agent_1's mounts could not be inspected for the vehicle's source" in blind.stdout


def test_the_window_root_write_probe_fails_closed(run):
    refused = run(COMPOSE="docker compose -p probe", AGENTS="agent_1", DIODE_ROOT_VERDICT="refused")
    assert "PASS  agent_1 cannot write the window root" in refused.stdout
    wrote = run(COMPOSE="docker compose -p probe", AGENTS="agent_1", DIODE_ROOT_VERDICT="wrote")
    assert "FAIL  agent_1 can write the window root" in wrote.stdout
    silent = run(COMPOSE="docker compose -p probe", AGENTS="agent_1")
    assert "FAIL  agent_1 could not be probed for writing the window root" in silent.stdout


def test_the_vehicle_binds_its_window_and_its_state_and_nothing_else(run):
    exact = run(COMPOSE="docker compose -p probe", AGENTS="agent_1", VEHICLE_BINDS="/state /diode ")
    assert "PASS  the vehicle binds /diode and /state and nothing else" in exact.stdout
    wider = run(
        COMPOSE="docker compose -p probe", AGENTS="agent_1", VEHICLE_BINDS="/diode /state /shared "
    )
    assert "FAIL  the vehicle binds '/diode /shared /state'" in wider.stdout
    absent = run(COMPOSE="docker compose -p probe", AGENTS="agent_1", ABSENT="vehicle")
    assert "SKIP  the vehicle is not running" in absent.stdout


def test_an_agent_bound_to_the_vehicle_state_image_root_is_a_failure(run):
    result = run(
        COMPOSE="docker compose -p probe",
        AGENTS="agent_1",
        MOUNT_SOURCES="/v/state_x/data /v/vehicle_state ",
    )
    assert "FAIL  agent_1 mounts the vehicle's private state" in result.stdout


def test_the_window_root_probe_says_nothing_when_it_cannot_run(run, tmp_path):
    """The probe's own text, run where none of its tools exist, must not read as a refusal."""
    run(COMPOSE="docker compose -p probe", AGENTS="agent_1")
    probe = next(line for line in run.argv_lines() if "/diode/.probe" in line)
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
    assert out.splitlines()[-1:] != ["refused"], out
