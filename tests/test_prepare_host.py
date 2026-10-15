"""scripts/prepare_host.sh, run in a temporary tree against logging stubs.

Adapted from Aurora's PreparedTree (tests/test_host_scripts.py, 42faf41): the script is copied into
a temporary repository whose volume tooling is a stub that logs every call, so these never create,
mount or move anything real. The roster is the real scripts/roster.py, because what lands in .env
is the point of two of the tests.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_COMMAND = "mv volumes volumes.pre-aurora-2026-10-09"

PYTHON_STUB = """#!/bin/sh
case "$1" in
*roster.py) exec "{python}" "$@" ;;
esac
script=$(basename "$1")
shift
echo "$script $*" >> "{log}"
case $1 in
plan) echo "plan report"; exit ${{STUB_PLAN:-0}} ;;
list) printf '%s\\n' "state_ibex 2G {images}/state_ibex.img {root}/state_ibex" \\
    "diode 2G {images}/diode.img {root}/diode" ;;
root) echo "{root}" ;;
fstab) echo "{images}/state_ibex.img {root}/state_ibex ext4 loop,nofail 0 2" ;;
check) echo "check report"; exit ${{STUB_CHECK:-0}} ;;
esac
"""

CREATOR_STUB = """#!/bin/sh
echo "create_volume_image.sh $*" >> "{log}"
status=${{STUB_VOLUME:-0}}
if [ "$status" = 2 ]; then
    echo "$3 is not mounted. run:"
    echo "  sudo mount -o loop,nosuid,nodev '$3' '$4'"
fi
exit "$status"
"""

MOUNTPOINT_STUB = """#!/bin/sh
for last; do :; done
case " ${{STUB_MOUNTED:-}} " in
*" $last "*) exit 0 ;;
esac
exit 1
"""


class PreparedTree:
    def __init__(self, tmp_path: Path) -> None:
        self.repo = tmp_path / "repo"
        self.root = self.repo / "volumes"
        self.images = self.repo / "volume-images"
        self.log = tmp_path / "prepare.log"
        self.bin = tmp_path / "bin"
        scripts = self.repo / "scripts"
        scripts.mkdir(parents=True)
        self.bin.mkdir()
        shutil.copy(ROOT / "scripts" / "prepare_host.sh", scripts / "prepare_host.sh")
        shutil.copy(ROOT / "scripts" / "roster.py", scripts / "roster.py")
        (self.repo / "vendor" / "registry").mkdir(parents=True)
        (self.repo / ".env.example").write_text("OPENROUTER_API_KEY=\n", encoding="utf-8")
        self.declare(3)
        fields = {
            "log": self.log,
            "root": self.root,
            "images": self.images,
            "python": sys.executable,
        }
        self.python = self.bin / "python-stub"
        for path, text in (
            (self.python, PYTHON_STUB),
            (scripts / "create_volume_image.sh", CREATOR_STUB),
            (self.bin / "mountpoint", MOUNTPOINT_STUB),
        ):
            path.write_text(text.format(**fields), encoding="utf-8")
            path.chmod(0o755)

    def declare(self, count: int) -> None:
        """A compose file declaring count agents, as scripts/build_compose.py would."""
        services = "".join(f"  agent_{n}:\n    image: x\n" for n in range(1, count + 1))
        (self.repo / "docker-compose.yml").write_text(f"services:\n{services}", encoding="utf-8")

    def run(self, mounted=(), **stubs) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("SPACE_", "FLEET_"))}
        env.update(
            PYTHON=str(self.python),
            PATH=f"{self.bin}:{env['PATH']}",
            ROSTER_COUNT="3",
            ROSTER_SEED="7",
            STUB_MOUNTED=" ".join(str(path) for path in mounted),
        )
        env.update({f"STUB_{key.upper()}": str(value) for key, value in stubs.items()})
        return subprocess.run(
            ["sh", str(self.repo / "scripts" / "prepare_host.sh")],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def slugs(self) -> list[str]:
        roster = json.loads((self.repo / "operator" / "roster.json").read_text())
        return [entry["slug"] for entry in roster["agents"]]


def _tree(tmp_path):
    return PreparedTree(tmp_path)


def test_prepare_host_refuses_without_the_crate_registry(tmp_path) -> None:
    tree = _tree(tmp_path)
    shutil.rmtree(tree.repo / "vendor")

    result = tree.run()

    assert result.returncode == 1
    assert "vendor/registry is missing" in result.stderr
    assert "build_registry.sh" in result.stderr


def test_prepare_host_copies_an_old_roster_into_the_operator_directory_once(tmp_path) -> None:
    tree = _tree(tmp_path)
    tree.declare(2)
    old = tree.root / "work"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "roster.py"), "--count", "2", "--seed", "3"]
        + ["--roster-dir", str(old), "--env-file", ""],
        check=True,
        capture_output=True,
    )

    result = tree.run()

    assert result.returncode == 2, result.stdout + result.stderr
    copied = tree.repo / "operator" / "roster.json"
    assert json.loads(copied.read_text()) == json.loads((old / "roster.json").read_text())
    env = (tree.repo / ".env").read_text()
    assert "FLEET_COUNT=2" in env
    for slug in tree.slugs():
        assert f"_SLUG={slug}" in env

    (old / "roster.json").write_text(json.dumps({"count": 1}))
    tree.run()
    assert json.loads(copied.read_text())["count"] == 2


def test_prepare_host_refuses_the_old_layout_and_prints_the_archive_command(tmp_path) -> None:
    tree = _tree(tmp_path)
    (tree.root / "home" / "ibex").mkdir(parents=True)
    before = sorted(str(p) for p in tree.root.rglob("*"))

    result = tree.run()

    assert result.returncode == 2
    assert ARCHIVE_COMMAND in result.stdout
    assert sorted(str(p) for p in tree.root.rglob("*")) == before
    assert not any(call.startswith(("volume_images.py plan", "create_")) for call in tree.calls())


def test_prepare_host_collects_operator_steps_and_exits_2(tmp_path) -> None:
    tree = _tree(tmp_path)

    result = tree.run(volume=2)

    assert result.returncode == 2, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    block = lines.index("steps for the operator:")
    fstab = lines.index("/etc/fstab lines that mount the images at boot:")
    mount = lines.index(
        f"  sudo mount -o loop,nosuid,nodev '{tree.images}/state_ibex.img' '{tree.root}/state_ibex'"
    )
    assert block < mount < fstab
    assert result.stdout.count("steps for the operator:") == 1
    assert "volume_images.py check" not in tree.calls()


def test_a_fatal_creator_error_stops_prepare_host(tmp_path) -> None:
    tree = _tree(tmp_path)

    result = tree.run(volume=1)

    assert result.returncode == 1
    calls = tree.calls()
    assert sum(call.startswith("create_volume_image.sh") for call in calls) == 1
    assert "volume_images.py check" not in calls


def test_a_failed_plan_creates_nothing(tmp_path) -> None:
    tree = _tree(tmp_path)

    result = tree.run(plan=1)

    assert result.returncode == 1
    assert not any(call.startswith("create_volume_image.sh") for call in tree.calls())


def test_prepare_host_makes_each_agent_s_window_and_telemetry_directories_when_the_images_are_mounted(
    tmp_path,
) -> None:
    tree = _tree(tmp_path)
    diode, telemetry = tree.root / "diode", tree.root / "operator_telemetry"
    (diode / "data").mkdir(parents=True)
    (telemetry / "data").mkdir(parents=True)

    result = tree.run(mounted=(diode, telemetry))

    assert result.returncode == 0, result.stdout + result.stderr
    for slug in tree.slugs():
        assert (diode / "data" / slug / "output").is_dir()
        assert (telemetry / "data" / "agents" / slug).is_dir()


def test_prepare_host_leaves_unmounted_window_and_telemetry_images_alone(tmp_path) -> None:
    tree = _tree(tmp_path)
    (tree.root / "diode" / "data").mkdir(parents=True)

    tree.run()

    assert list((tree.root / "diode" / "data").iterdir()) == []


def test_prepare_host_ends_with_the_check_when_nothing_is_left_for_the_operator(tmp_path) -> None:
    tree = _tree(tmp_path)

    result = tree.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert tree.calls()[-1] == "volume_images.py check"
    assert "steps for the operator" not in result.stdout


def test_a_failing_check_exits_1(tmp_path) -> None:
    tree = _tree(tmp_path)

    assert tree.run(check=1).returncode == 1


def test_a_roster_of_a_different_size_than_the_compose_declares_is_refused(tmp_path) -> None:
    # Every service binds images named for agents 1..N of the committed compose; the monitor and the
    # review panel bind them all, so a smaller roster would stop even a bare `compose up`.
    tree = _tree(tmp_path)
    tree.declare(10)

    result = tree.run()

    assert result.returncode == 1
    assert "declares 10 agents" in result.stderr
    assert not any(call.startswith("volume_images.py plan") for call in tree.calls())
