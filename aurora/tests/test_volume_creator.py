"""Aurora's image creator, ported with its tests (42faf41) to this world's service uid.

scripts/create_volume_image.sh makes one preallocated ext4 image, mounts it if `sudo -n` allows,
and otherwise prints the exact root commands for the operator. These tests run it against PATH
stubs that log every call: nothing here runs as root, mounts anything, or changes ownership. The
only change from Aurora's tests is the uid, 65532 there and 1000 here.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


# create_volume_image.sh

CREATOR = ROOT / "scripts" / "create_volume_image.sh"
MIB = 2**20
DATA_LINE = (
    "mountpoint -q '{mnt}' && [ \"$(stat -c %u:%g:%a '{mnt}')\" = 0:0:755 ] "
    "&& sudo mkdir -m 0755 '{mnt}/data' && sudo chown -h 1000:1000 '{mnt}/data'"
)


def _real(name: str) -> str:
    path = shutil.which(name)
    assert path is not None, name
    return path


class Stubs:
    """PATH stubs that log every call. Real tools a test needs are logged, then run."""

    def __init__(self, tmp_path: Path) -> None:
        self.bin = tmp_path / "bin"
        self.bin.mkdir(parents=True)
        self.log = tmp_path / "calls.log"
        self.set("sudo", "exit 1")
        self.set("mount", "exit 1")
        self.set("mountpoint", "exit 1")
        self.set("mkfs.ext4", "exit 0")
        self.set("blkid", "echo ext4")
        self.set("losetup", "exit 0")
        for name in ("fallocate", "mv", "mkdir", "chmod", "install", "rm"):
            self.passthrough(name)
        self.image_root("0 0 755")

    def set(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(f'#!/bin/sh\necho "{name} $*" >> "{self.log}"\n{body}\n', encoding="utf-8")
        path.chmod(0o755)

    def passthrough(self, name: str) -> None:
        self.set(name, f'exec "{_real(name)}" "$@"')

    def image_root(self, text: str) -> None:
        """Report a mounted image's root as text; every other stat call is the real one.

        A temporary directory stands in for the mounted image, so its real owner is
        the test user rather than the root a real image has.
        """
        self.set(
            "stat",
            f'if [ "$1" = -c ] && [ "$2" = "%u %g %a" ]; then echo "{text}"; exit 0; fi\n'
            f'exec "{_real("stat")}" "$@"',
        )

    def mounted(self, *paths: Path) -> None:
        cases = "".join(f'    "{path}") exit 0 ;;\n' for path in paths)
        self.set("mountpoint", f'for last; do :; done\ncase "$last" in\n{cases}esac\nexit 1')

    def calls(self) -> list[str]:
        if not self.log.exists():
            return []
        return self.log.read_text(encoding="utf-8").splitlines()

    def named(self, name: str) -> list[str]:
        return [call for call in self.calls() if call.split(" ", 1)[0] == name]

    def env(self) -> dict[str, str]:
        return {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}"}


@pytest.fixture
def allocating(tmp_path: Path) -> None:
    probe = tmp_path / "fallocate-probe"
    result = subprocess.run(
        [_real("fallocate"), "-l", "1M", str(probe)], capture_output=True, check=False
    )
    if result.returncode != 0:
        # Aurora skips here; this repository allows no skips, so an untested creator fails.
        pytest.fail("the temporary filesystem does not support fallocate; the creator is untested")
    probe.unlink()


def _paths(tmp_path: Path, name: str = "state") -> tuple[Path, Path]:
    return tmp_path / "volumes" / f"{name}.img", tmp_path / "volumes" / name


def _create(stubs: Stubs, img: Path, mnt: Path, size: str = "1M", name: str = "state"):
    return subprocess.run(
        ["sh", str(CREATOR), name, size, str(img), str(mnt)],
        env=stubs.env(),
        capture_output=True,
        text=True,
    )


def _allocated_image(img: Path, size: str = "1M") -> Path:
    img.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([_real("fallocate"), "-l", size, str(img)], check=True)
    return img


def _sparse_file(path: Path, length: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.truncate(length)
    return path


def _fully_allocated(path: Path) -> bool:
    st = os.stat(path)
    return st.st_blocks * 512 >= st.st_size


def _ready_mount(stubs: Stubs, mnt: Path) -> None:
    """A mount point the stubs report as mounted, holding the bound data/ directory."""
    (mnt / "data").mkdir(parents=True)
    stubs.mounted(mnt)


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def test_creator_builds_a_new_image_on_a_temporary_file_then_renames_it(
    tmp_path, allocating
) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    tmp = f"{img}.tmp"

    result = _create(stubs, img, mnt)

    assert result.returncode == 2, result.stderr
    calls = stubs.calls()
    mkfs = next(call for call in calls if call.startswith("mkfs.ext4 "))
    assert mkfs == (
        "mkfs.ext4 -q -F -m 0 "
        f"-E root_owner=0:0,nodiscard,lazy_itable_init=0,lazy_journal_init=0 {tmp}"
    )
    assert (
        calls.index(f"fallocate -l 1M {tmp}")
        < calls.index(mkfs)
        < calls.index(f"mv -T -- {tmp} {img}")
    )
    assert os.stat(img).st_size == MIB
    assert _fully_allocated(img)
    assert not Path(tmp).exists()


@pytest.mark.parametrize(
    "fallocate, reason",
    [
        ('"{truncate}" -s 2M "$3"', "not the requested"),
        ('"{truncate}" -s 1M "$3"', "allocated"),
    ],
)
def test_creator_refuses_a_temporary_file_of_the_wrong_length_or_allocation(
    tmp_path, fallocate, reason
) -> None:
    stubs = Stubs(tmp_path)
    stubs.set("fallocate", fallocate.format(truncate=_real("truncate")))
    img, mnt = _paths(tmp_path)

    result = _create(stubs, img, mnt)

    assert result.returncode == 1
    assert reason in result.stderr
    assert not img.exists()
    assert Path(f"{img}.tmp").exists()
    assert stubs.named("mv") == []


def test_creator_does_not_reformat_an_existing_ext4_image(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    _allocated_image(img)
    with img.open("r+b") as handle:
        handle.write(b"existing contents")
    _ready_mount(stubs, mnt)

    result = _create(stubs, img, mnt)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""
    for tool in ("fallocate", "mkfs.ext4", "mv", "sudo", "chmod", "rm"):
        assert stubs.named(tool) == [], tool
    assert img.read_bytes().startswith(b"existing contents")
    assert os.stat(img).st_size == MIB


@pytest.mark.parametrize("blkid", ["echo xfs", "exit 2"])
def test_creator_leaves_an_existing_image_that_is_not_ext4_alone(tmp_path, blkid) -> None:
    stubs = Stubs(tmp_path)
    stubs.set("blkid", blkid)
    img, mnt = _paths(tmp_path)
    _sparse_file(img, MIB).write_bytes(b"someone else's data")

    result = _create(stubs, img, mnt)

    assert result.returncode == 2
    assert "not reformatted" in result.stdout
    assert "remove it by hand" in result.stdout
    for tool in ("fallocate", "mkfs.ext4", "mv", "sudo", "chmod", "mkdir", "rm"):
        assert stubs.named(tool) == [], tool
    assert img.read_bytes() == b"someone else's data"
    assert not mnt.exists()


@pytest.mark.parametrize("size", ["1M", "4M"])
def test_creator_repairs_a_sparse_image_at_its_own_length(tmp_path, size) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    _sparse_file(img, 2 * MIB)
    _ready_mount(stubs, mnt)

    result = _create(stubs, img, mnt, size=size)

    assert result.returncode == 2
    assert f"  fallocate -l {2 * MIB} '{img}'" in result.stdout.splitlines()
    assert stubs.named("fallocate") == []
    assert os.stat(img).st_size == 2 * MIB
    assert not _fully_allocated(img)
    if size == "4M":
        assert f"  fallocate -l 4M '{img}'" in result.stdout.splitlines()
    else:
        assert f"fallocate -l {size}" not in result.stdout
        assert "never shrunk" in result.stderr


def test_creator_prints_the_grow_commands_and_grows_nothing(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    _allocated_image(img)
    _ready_mount(stubs, mnt)

    result = _create(stubs, img, mnt, size="2M")

    assert result.returncode == 2
    lines = result.stdout.splitlines()
    assert f"  fallocate -l 2M '{img}'" in lines
    assert any(line.startswith("  sudo losetup -c ") for line in lines)
    assert any(line.startswith("  sudo resize2fs ") for line in lines)
    assert stubs.named("fallocate") == []
    assert os.stat(img).st_size == MIB


def test_creator_never_shrinks_an_image(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    _allocated_image(img, "2M")
    _ready_mount(stubs, mnt)

    result = _create(stubs, img, mnt, size="1M")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "never shrunk" in result.stderr
    assert result.stdout == ""
    assert os.stat(img).st_size == 2 * MIB
    assert stubs.named("fallocate") == []


def test_a_new_mount_point_gets_mode_0555(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)

    _create(stubs, img, mnt)

    assert mnt.is_dir()
    assert _mode(mnt) == 0o555
    assert f"mkdir -m 0555 -- {mnt}" in stubs.calls()


def test_an_empty_unmounted_mount_point_of_the_caller_is_set_to_0555(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    _allocated_image(img)
    mnt.mkdir(mode=0o755)

    result = _create(stubs, img, mnt)

    assert result.returncode == 2
    assert stubs.named("chmod") == [f"chmod 0555 -- {mnt}"]
    assert _mode(mnt) == 0o555


def test_the_printed_chmod_does_nothing_once_the_image_is_mounted(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    stubs.set("id", "echo 4321")
    img, mnt = _paths(tmp_path)
    _allocated_image(img)
    mnt.mkdir(mode=0o755)

    result = _create(stubs, img, mnt)
    (line,) = [line.strip() for line in result.stdout.splitlines() if "chmod 0555" in line]
    sudo_log = tmp_path / "sudo-ran"
    bin_dir = tmp_path / "printed-bin"
    bin_dir.mkdir()
    for name, body in (("mountpoint", "exit 0"), ("sudo", f'echo "$*" >> "{sudo_log}"')):
        (bin_dir / name).write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    ran = subprocess.run(
        ["sh", "-c", line],
        env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
    )

    assert ran.returncode == 0
    assert not sudo_log.exists()
    assert _mode(mnt) == 0o755


def test_printed_commands_quote_a_path_with_an_apostrophe(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    img = tmp_path / "it's" / "state.img"
    mnt = tmp_path / "it's" / "state"
    _allocated_image(img)

    result = _create(stubs, img, mnt)

    def shell_quote(path: Path) -> str:
        return "'" + str(path).replace("'", "'\\''") + "'"

    assert f"  sudo mount -o loop,nosuid,nodev {shell_quote(img)} {shell_quote(mnt)}" in (
        result.stdout.splitlines()
    )


def test_an_empty_mount_point_of_another_owner_prints_the_chmod(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    stubs.set("id", "echo 4321")
    img, mnt = _paths(tmp_path)
    _allocated_image(img)
    mnt.mkdir(mode=0o755)

    result = _create(stubs, img, mnt)

    assert result.returncode == 2
    assert f"  mountpoint -q '{mnt}' || sudo chmod 0555 '{mnt}'" in result.stdout.splitlines()
    assert stubs.named("chmod") == []
    assert _mode(mnt) == 0o755


def test_a_non_empty_unmounted_mount_point_is_not_mounted_over(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    _allocated_image(img)
    mnt.mkdir()
    (mnt / "left-behind").write_text("x", encoding="utf-8")

    result = _create(stubs, img, mnt)

    assert result.returncode == 2
    assert "not mounted and not empty" in result.stdout
    assert stubs.named("sudo") == []
    assert stubs.named("chmod") == []
    assert (mnt / "left-behind").read_text(encoding="utf-8") == "x"


def test_no_chmod_reaches_a_mounted_mount_point(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    _allocated_image(img)
    mnt.mkdir(mode=0o755)
    stubs.mounted(mnt)

    result = _create(stubs, img, mnt)

    assert result.returncode == 2
    assert stubs.named("chmod") == []
    assert stubs.named("sudo") == []
    assert _mode(mnt) == 0o755


def test_a_failed_sudo_prints_the_mount_command(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    _allocated_image(img)

    result = _create(stubs, img, mnt)

    assert result.returncode == 2
    assert stubs.named("sudo") == [f"sudo -n mount -o loop,nosuid,nodev {img} {mnt}"]
    assert f"  sudo mount -o loop,nosuid,nodev '{img}' '{mnt}'" in result.stdout.splitlines()


def test_a_successful_sudo_mount_prints_no_mount_command(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    stubs.set("sudo", "exit 0")
    img, mnt = _paths(tmp_path)
    _allocated_image(img)

    result = _create(stubs, img, mnt)

    assert result.returncode == 2
    assert "sudo mount" not in result.stdout
    assert f"  {DATA_LINE.format(mnt=mnt)}" in result.stdout.splitlines()


@pytest.mark.parametrize(
    "name, size",
    [
        ("", "1M"),
        ("1state", "1M"),
        ("State", "1M"),
        ("st-ate", "1M"),
        ("st ate", "1M"),
        ("st/ate", "1M"),
        ("_state", "1M"),
        ("state", "10"),
        ("state", "10GB"),
        ("state", "1.5G"),
        ("state", "G"),
        ("state", "10g"),
        ("state", "-1G"),
        ("state", ""),
    ],
)
def test_creator_rejects_bad_names_and_sizes(tmp_path, name, size) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)

    result = _create(stubs, img, mnt, size=size, name=name)

    assert result.returncode == 1
    assert stubs.calls() == []
    assert not img.parent.exists()


def test_creator_rejects_relative_paths(tmp_path) -> None:
    stubs = Stubs(tmp_path)

    for img, mnt in (("state.img", str(tmp_path / "m")), (str(tmp_path / "s.img"), "m")):
        result = subprocess.run(
            ["sh", str(CREATOR), "state", "1M", img, mnt],
            env=stubs.env(),
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert result.returncode == 1
    assert stubs.calls() == []


def test_an_interrupted_creation_ends_in_an_image_of_the_requested_length(
    tmp_path, allocating
) -> None:
    stubs = Stubs(tmp_path)
    stubs.set("mkfs.ext4", "exit 1")
    img, mnt = _paths(tmp_path)
    tmp = Path(f"{img}.tmp")

    first = _create(stubs, img, mnt)

    assert first.returncode == 1
    assert tmp.exists()
    assert not img.exists()

    stubs.set("mkfs.ext4", "exit 0")
    second = _create(stubs, img, mnt)

    assert second.returncode == 2, second.stderr
    assert f"losetup -j {tmp}" in stubs.calls()
    assert f"rm -f -- {tmp}" in stubs.calls()
    assert os.stat(img).st_size == MIB
    assert _fully_allocated(img)
    assert not tmp.exists()


def test_an_oversized_temporary_ends_in_an_image_of_the_requested_length(
    tmp_path, allocating
) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    tmp = _sparse_file(Path(f"{img}.tmp"), 4 * MIB)

    result = _create(stubs, img, mnt)

    assert result.returncode == 2, result.stderr
    assert os.stat(img).st_size == MIB
    assert _fully_allocated(img)
    assert not tmp.exists()


@pytest.mark.parametrize(
    "losetup, remediation",
    [
        ('echo "/dev/loop7: [2049]:12 ({tmp})"', "  sudo losetup -d /dev/loop7"),
        ("exit 1", "  sudo losetup -j '{tmp}'"),
    ],
)
def test_a_temporary_that_may_be_attached_is_left_untouched(tmp_path, losetup, remediation) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    tmp = Path(f"{img}.tmp")
    tmp.parent.mkdir(parents=True)
    tmp.write_bytes(b"unfinished")
    before = os.stat(tmp)
    stubs.set("losetup", losetup.format(tmp=tmp))

    result = _create(stubs, img, mnt)

    assert result.returncode == 2
    lines = result.stdout.splitlines()
    assert remediation.format(tmp=tmp) in lines
    assert f"  rm -f '{tmp}'" in lines
    assert tmp.read_bytes() == b"unfinished"
    after = os.stat(tmp)
    assert (after.st_size, after.st_mtime_ns, after.st_ino) == (
        before.st_size,
        before.st_mtime_ns,
        before.st_ino,
    )
    for tool in ("rm", "fallocate", "mkfs.ext4", "mv", "sudo"):
        assert stubs.named(tool) == [], tool
    assert not img.exists()


@pytest.mark.parametrize("which", ["img", "tmp", "mnt", "data"])
def test_creator_refuses_a_symlink_and_touches_nothing(tmp_path, which) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    img.parent.mkdir()
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"precious")
    sentinel.chmod(0o640)
    before = os.lstat(sentinel)
    if which == "data":
        mnt.mkdir()
    link = {"img": img, "tmp": Path(f"{img}.tmp"), "mnt": mnt, "data": mnt / "data"}[which]
    link.symlink_to(sentinel)

    result = _create(stubs, img, mnt)

    assert result.returncode == 1
    assert "symlink" in result.stderr
    assert stubs.calls() == []
    after = os.lstat(sentinel)
    assert sentinel.read_bytes() == b"precious"
    assert (after.st_size, after.st_mode, after.st_uid, after.st_gid, after.st_mtime_ns) == (
        before.st_size,
        before.st_mode,
        before.st_uid,
        before.st_gid,
        before.st_mtime_ns,
    )


def _no_data_creation(stubs: Stubs, mnt: Path) -> None:
    for call in stubs.named("mkdir") + stubs.named("install"):
        assert not any(arg.endswith("/data") for arg in call.split()), call
    assert not os.path.lexists(mnt / "data")


@pytest.mark.parametrize("scenario", ["new, sudo fails", "new, sudo mounts", "existing, mounted"])
def test_the_creator_never_creates_data(tmp_path, allocating, scenario) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    if scenario == "new, sudo mounts":
        stubs.set("sudo", "exit 0")
    if scenario == "existing, mounted":
        _allocated_image(img)
        mnt.mkdir()
        stubs.mounted(mnt)

    result = _create(stubs, img, mnt)

    assert result.returncode == 2
    assert f"  {DATA_LINE.format(mnt=mnt)}" in result.stdout.splitlines()
    _no_data_creation(stubs, mnt)


def test_the_data_line_follows_the_mount_line(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)

    result = _create(stubs, img, mnt)

    lines = result.stdout.splitlines()
    mount = lines.index(f"  sudo mount -o loop,nosuid,nodev '{img}' '{mnt}'")
    assert mount < lines.index(f"  {DATA_LINE.format(mnt=mnt)}")


@pytest.mark.parametrize(
    "scenario", ["unmounted", "root-owned root", "service-owned root", "data symlink"]
)
def test_the_printed_data_line_acts_only_on_a_mounted_root_owned_image(
    tmp_path, allocating, scenario
) -> None:
    creator_stubs = Stubs(tmp_path)
    img, mnt = _paths(tmp_path)
    printed = _create(creator_stubs, img, mnt).stdout.splitlines()
    line = next(text.strip() for text in printed if "sudo mkdir" in text)
    assert line == DATA_LINE.format(mnt=mnt)
    stubs = Stubs(tmp_path / "run")
    if scenario != "unmounted":
        stubs.mounted(mnt)
    stubs.set("stat", "echo 1000:1000:755" if scenario == "service-owned root" else "echo 0:0:755")
    stubs.set("sudo", 'exec "$@"' if scenario == "data symlink" else "exit 0")
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"precious")
    before = os.lstat(sentinel)
    if scenario == "data symlink":
        mnt.chmod(0o755)
        (mnt / "data").symlink_to(sentinel)

    result = subprocess.run(["sh", "-c", line], env=stubs.env(), capture_output=True, text=True)

    mkdir = f"sudo mkdir -m 0755 {mnt}/data"
    chown = f"sudo chown -h 1000:1000 {mnt}/data"
    expected = {
        "unmounted": [],
        "root-owned root": [mkdir, chown],
        "service-owned root": [],
        "data symlink": [mkdir],
    }[scenario]
    assert stubs.named("sudo") == expected
    expected_stat = [] if scenario == "unmounted" else [f"stat -c %u:%g:%a {mnt}"]
    assert stubs.named("stat") == expected_stat
    assert stubs.named("install") == []
    assert stubs.named("chown") == []
    if scenario == "data symlink":
        assert result.returncode != 0
        assert (mnt / "data").is_symlink()
        assert sentinel.read_bytes() == b"precious"
        assert os.lstat(sentinel).st_mode == before.st_mode


@pytest.mark.parametrize(
    "root", ["1000 1000 755", "0 0 775", "0 0 757", "0 1000 755", "1000 0 755"]
)
@pytest.mark.parametrize("how", ["already mounted", "mounted by sudo"])
def test_a_mounted_image_whose_root_is_not_root_only_is_not_adopted(
    tmp_path, allocating, root, how
) -> None:
    stubs = Stubs(tmp_path)
    stubs.image_root(root)
    img, mnt = _paths(tmp_path)
    _allocated_image(img)
    if how == "already mounted":
        mnt.mkdir()
        stubs.mounted(mnt)
    else:
        stubs.set("sudo", "exit 0")

    result = _create(stubs, img, mnt)

    assert result.returncode == 2
    uid, gid, mode = root.split()
    assert f"image root is {uid}:{gid} {mode}; remove the image by hand" in result.stdout
    assert "sudo mkdir" not in result.stdout
    assert "chown" not in result.stdout
    _no_data_creation(stubs, mnt)
    assert os.stat(img).st_size == MIB


@pytest.mark.parametrize("root", ["0 0 755", "0 0 700"])
def test_a_mounted_image_with_a_root_only_image_root_is_adopted(tmp_path, allocating, root) -> None:
    stubs = Stubs(tmp_path)
    stubs.image_root(root)
    img, mnt = _paths(tmp_path)
    _allocated_image(img)
    mnt.mkdir()
    stubs.mounted(mnt)

    result = _create(stubs, img, mnt)

    assert result.returncode == 2
    assert "image root is" not in result.stdout
    assert f"  {DATA_LINE.format(mnt=mnt)}" in result.stdout.splitlines()
    assert f"stat -c %u %g %a -- {mnt}" in stubs.named("stat")


def test_an_unmounted_image_root_is_left_to_the_printed_guard(tmp_path, allocating) -> None:
    stubs = Stubs(tmp_path)
    stubs.image_root("1000 1000 755")
    img, mnt = _paths(tmp_path)
    _allocated_image(img)

    result = _create(stubs, img, mnt)

    assert result.returncode == 2
    assert "image root is" not in result.stdout
    assert f"  {DATA_LINE.format(mnt=mnt)}" in result.stdout.splitlines()
    assert not any("%u %g %a" in call for call in stubs.named("stat"))
