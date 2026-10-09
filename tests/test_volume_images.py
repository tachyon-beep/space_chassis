"""The bounded-volume manifest, ported from Aurora's tests (42faf41) to one container per agent.

Aurora's tests are carried by name where the behaviour is the same, with its host count replaced
by a roster of slugs read from the env file, its variables renamed SPACE_*, and its service uid
65532 replaced by 1000. The host is faked through Probes and World: nothing here runs as root,
mounts anything, or touches the real volumes/.
"""

import ast
import math
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import volume_images  # noqa: E402
from volume_images import PER_AGENT, SHARED, Image, Kind, Probes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GIB = 2**30
PLACEHOLDER = "${SPACE_VOLUMES_DIR:-./volumes}"
UID = 1000

REG = stat.S_IFREG | 0o644
DIR = stat.S_IFDIR | 0o755
LNK = stat.S_IFLNK | 0o777

SLUGS = [
    "ibex",
    "lupin",
    "pelican",
    "corsair",
    "verbena",
    "orpiment",
    "pampero",
    "cinnabar",
    "mackerel",
    "scabious",
]

SIZE_VARIABLES = tuple(kind.size_variable for kind in volume_images.KINDS)
LITERAL_VARIABLES = (
    "SPACE_VOLUMES_DIR",
    "SPACE_VOLUME_IMG_DIR",
    *SIZE_VARIABLES,
    "SPACE_VOLUME_WARN_PERCENT",
)

SYNTHETIC = Kind("poll", "16M", "SPACE_POLL_SIZE", PER_AGENT, (("agent", "/poll", False, ""),))


def _roster_text(count: int) -> str:
    slugs = SLUGS[:count]
    lines = [f"FLEET_COUNT={count}", "FLEET_SLUGS=" + ",".join(slugs)]
    lines += [f"FLEET_{n}_SLUG={slug}" for n, slug in enumerate(slugs, start=1)]
    return "\n".join(lines) + "\n"


def _env_file(tmp_path: Path, text: str = "", count: int = 1) -> Path:
    path = tmp_path / "volumes.env"
    path.write_text(_roster_text(count) + text, encoding="utf-8")
    return path


def _plan(tmp_path: Path, count: int = 1, text: str = "", environ: dict | None = None):
    source = _env_file(tmp_path, text, count)
    return volume_images.plan(SLUGS[:count], source, {} if environ is None else environ)


def _by_name(images):
    return {image.name: image for image in images}


def _st(mode: int, *, size: int = 0, blocks: int | None = None, uid=0, gid=0, dev=1):
    return SimpleNamespace(
        st_mode=mode,
        st_size=size,
        st_blocks=-(-size // 512) if blocks is None else blocks,
        st_uid=uid,
        st_gid=gid,
        st_dev=dev,
    )


def _vfs(*, fsid=1, frsize=4096, blocks=0, bfree=None, bavail=None, files=1000, ffree=1000):
    bfree = blocks if bfree is None else bfree
    return SimpleNamespace(
        f_fsid=fsid,
        f_frsize=frsize,
        f_blocks=blocks,
        f_bfree=bfree,
        f_bavail=bfree if bavail is None else bavail,
        f_files=files,
        f_ffree=ffree,
    )


def _canonical(path: Path) -> str:
    return os.path.join(os.path.realpath(path.parent), path.name)


class World:
    """An injected host: lstat entries, mountinfo, loop backing files and statvfs."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.entries: dict[Path, SimpleNamespace] = {repo: _st(DIR, dev=1)}
        self.mounts: list[str] = []
        self.backing: dict[str, str] = {}
        self.vfs: dict[Path, SimpleNamespace] = {}
        self.lstat_calls: list[Path] = []
        self.statvfs_calls: list[Path] = []

    def _lstat(self, path):
        self.lstat_calls.append(Path(path))
        return self.entries.get(Path(path))

    def _statvfs(self, path):
        self.statvfs_calls.append(Path(path))
        return self.vfs[Path(path)]

    def probes(self) -> Probes:
        return Probes(
            lstat=self._lstat,
            statvfs=self._statvfs,
            mountinfo=lambda: "".join(self.mounts),
            backing_file=self.backing.get,
        )

    def healthy(self, image: Image, loop: int, used: int = 10, inodes: int = 1) -> None:
        self.entries[image.img] = _st(REG, size=image.size_bytes)
        self.entries[image.mnt] = _st(DIR, dev=100 + loop)
        self.entries[image.data] = _st(DIR, uid=UID, gid=UID, dev=100 + loop)
        self.mounts.append(
            f"{40 + loop} 1 7:{loop} / {_canonical(image.mnt)} rw,nosuid,nodev shared:1 "
            f"- ext4 /dev/loop{loop} rw\n"
        )
        self.backing[f"loop{loop}"] = _canonical(image.img)
        self.vfs[image.mnt] = _vfs(blocks=100, bfree=100 - used, files=100, ffree=100 - inodes)


def _image(tmp_path: Path, name: str = "state_ibex") -> Image:
    volumes = tmp_path / "volumes"
    return Image(
        name, name, "1G", GIB, volumes / f"{name}.img", volumes / name, volumes / name / "data"
    )


def _check_one(tmp_path: Path, mutate=None, warn: int = 80):
    world = World(tmp_path / "repo")
    image = _image(tmp_path)
    world.healthy(image, 3)
    if mutate is not None:
        mutate(world, image)
    return world, volume_images.check_image(image, world.probes(), warn, world.repo)


def _failures(result) -> list[str]:
    return [verdict.text for verdict in result.verdicts if not verdict.ok]


def _slug(n: int) -> str:
    return f"${{FLEET_{n}_SLUG:-agent_{n}}}"


# names and the table


def test_seven_images_per_agent_and_five_shared_make_75_at_ten_and_26_at_three() -> None:
    assert len(volume_images.names(SLUGS)) == 75
    assert len(volume_images.names(SLUGS[:3])) == 26


def test_each_agent_s_images_are_named_by_its_slug() -> None:
    assert volume_images.names(["ibex", "lupin"]) == [
        "state_ibex",
        "state_lupin",
        "pump_ibex",
        "pump_lupin",
        "build_ibex",
        "build_lupin",
        "telemetry_ibex",
        "telemetry_lupin",
        "transcripts_ibex",
        "transcripts_lupin",
        "llm_sock_ibex",
        "llm_sock_lupin",
        "llm_console_ibex",
        "llm_console_lupin",
        "shared",
        "diode",
        "fleet_ledger",
        "operator_telemetry",
        "vehicle_state",
    ]


def test_the_table_holds_the_bounded_volume_figures() -> None:
    table = {
        kind.name: (kind.default_size, kind.size_variable, kind.scope)
        for kind in volume_images.KINDS
    }

    assert table == {
        "state": ("2G", "SPACE_STATE_SIZE", PER_AGENT),
        "pump": ("512M", "SPACE_PUMP_SIZE", PER_AGENT),
        "build": ("4G", "SPACE_BUILD_SIZE", PER_AGENT),
        "telemetry": ("2G", "SPACE_TELEMETRY_SIZE", PER_AGENT),
        "transcripts": ("4G", "SPACE_TRANSCRIPTS_SIZE", PER_AGENT),
        "llm_sock": ("64M", "SPACE_LLM_SOCK_SIZE", PER_AGENT),
        "llm_console": ("64M", "SPACE_LLM_CONSOLE_SIZE", PER_AGENT),
        "shared": ("8G", "SPACE_SHARED_SIZE", SHARED),
        "diode": ("2G", "SPACE_DIODE_SIZE", SHARED),
        "fleet_ledger": ("64M", "SPACE_FLEET_LEDGER_SIZE", SHARED),
        "operator_telemetry": ("1G", "SPACE_OPERATOR_TELEMETRY_SIZE", SHARED),
        "vehicle_state": ("40G", "SPACE_VEHICLE_STATE_SIZE", SHARED),
    }


def _gib(size_bytes: int) -> str:
    """A GiB figure as the docs write it, with no trailing zeros."""
    return f"{size_bytes / GIB:.4f}".rstrip("0").rstrip(".")


def _total(scope: str) -> int:
    return sum(
        volume_images.parse_size(kind.default_size)
        for kind in volume_images.KINDS
        if kind.scope == scope
    )


def test_the_default_plan_for_ten_agents_totals_177_gibibytes() -> None:
    # The vehicle's private state (40G) is allocated with or without the vehicle profile.
    assert _total(PER_AGENT) == math.floor(12.625 * GIB)
    assert _total(SHARED) == math.floor(51.0625 * GIB)
    assert 10 * _total(PER_AGENT) + _total(SHARED) == math.floor(177.3125 * GIB)


def test_the_documented_image_totals_match_the_manifest() -> None:
    per_agent, shared = _total(PER_AGENT), _total(SHARED)
    ten = _gib(shared + 10 * per_agent)
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    comments = " ".join(line[1:].strip() for line in env.splitlines() if line.startswith("#"))

    assert (
        f"By default each agent's images are {_gib(per_agent)}G and the shared ones {_gib(shared)}G,"
        f" so the total is {ten}G for ten agents."
    ) in comments


def test_the_manifest_does_not_import_the_compose_generator_at_module_level() -> None:
    tree = ast.parse((ROOT / "scripts" / "volume_images.py").read_text(encoding="utf-8"))
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)

    assert "build_compose" not in imported


# the fleet


def test_the_fleet_is_read_from_the_env_file(tmp_path: Path) -> None:
    assert volume_images.fleet(_env_file(tmp_path, count=3), {}) == SLUGS[:3]


@pytest.mark.parametrize(
    "text",
    [
        "FLEET_COUNT=2\nFLEET_SLUGS=ibex,lupin\nFLEET_1_SLUG=ibex\n",
        "FLEET_COUNT=2\nFLEET_SLUGS=ibex\nFLEET_1_SLUG=ibex\nFLEET_2_SLUG=lupin\n",
        "FLEET_COUNT=2\nFLEET_SLUGS=ibex,lupin\nFLEET_1_SLUG=ibex\nFLEET_2_SLUG=pelican\n",
        "FLEET_COUNT=2\nFLEET_SLUGS=ibex,ibex\nFLEET_1_SLUG=ibex\nFLEET_2_SLUG=ibex\n",
        "FLEET_COUNT=0\nFLEET_SLUGS=\n",
        "FLEET_COUNT=two\n",
        "FLEET_SLUGS=ibex\nFLEET_1_SLUG=ibex\n",
    ],
)
def test_a_roster_block_that_disagrees_with_itself_is_refused(tmp_path: Path, text: str) -> None:
    source = tmp_path / "volumes.env"
    source.write_text(text, encoding="utf-8")

    with pytest.raises(SystemExit, match="FLEET"):
        volume_images.fleet(source, {})


@pytest.mark.parametrize("slug", ["../x", "a/b", "with space", "Ibex", "9lives", ""])
def test_a_slug_outside_the_name_alphabet_is_refused_before_any_path_is_built(
    tmp_path: Path, slug: str
) -> None:
    source = tmp_path / "volumes.env"
    source.write_text(f"FLEET_COUNT=1\nFLEET_SLUGS={slug}\nFLEET_1_SLUG={slug}\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="FLEET"):
        volume_images.fleet(source, {})
    with pytest.raises(SystemExit):
        volume_images.plan([slug], _env_file(tmp_path), {})


def test_a_slug_carrying_a_newline_is_refused_by_plan(tmp_path: Path) -> None:
    # An env file cannot carry a newline inside a value, so this one can only arrive in a list.
    with pytest.raises(SystemExit):
        volume_images.plan(["x\ny"], _env_file(tmp_path), {})


def test_a_fleet_count_in_the_process_environment_is_ignored(tmp_path: Path) -> None:
    source = _env_file(tmp_path, count=3)

    assert volume_images.fleet(source, {"FLEET_COUNT": "10", "FLEET_SLUGS": "x"}) == SLUGS[:3]


# mounts_for


def _source(name: str, index: int | None = None, subpath: str = "") -> str:
    image = name if index is None else f"{name}_{_slug(index)}"
    return f"{PLACEHOLDER}/{image}/data{subpath}"


def test_an_agent_mounts_its_own_images_and_the_shared_ones() -> None:
    assert volume_images.mounts_for("agent", 2, 10) == [
        (_source("state", 2), "/state", False),
        (_source("pump", 2), "/pump", False),
        (_source("build", 2), "/build", False),
        (_source("telemetry", 2), "/telemetry", False),
        (_source("llm_sock", 2), "/llm/sock", True),
        (_source("llm_console", 2), "/llm/console", False),
        (_source("shared"), "/shared", False),
        (_source("diode", subpath=f"/{_slug(2)}"), f"/diode/{_slug(2)}", False),
    ]


def test_a_recorder_mounts_its_agent_s_record_socket_console_and_the_ledger() -> None:
    assert volume_images.mounts_for("recorder", 3, 10) == [
        (_source("transcripts", 3), "/transcripts", False),
        (_source("llm_sock", 3), "/llm/sock", False),
        (_source("llm_console", 3), "/llm/console", True),
        (_source("fleet_ledger"), "/ledger", False),
    ]


def test_the_monitor_writes_operator_telemetry_and_reads_every_agent_s_record() -> None:
    assert volume_images.mounts_for("monitor", None, 2) == [
        (_source("telemetry", 1), f"/mirror/{_slug(1)}", True),
        (_source("telemetry", 2), f"/mirror/{_slug(2)}", True),
        (_source("transcripts", 1), f"/transcripts/{_slug(1)}", True),
        (_source("transcripts", 2), f"/transcripts/{_slug(2)}", True),
        (_source("diode"), "/diode", True),
        (_source("operator_telemetry"), "/telemetry", False),
    ]
    review = volume_images.mounts_for("review", None, 2)
    assert (_source("operator_telemetry"), "/telemetry", True) in review
    assert all(read_only for _source_, _target, read_only in review)


def test_the_shared_window_is_bound_whole_only_by_the_window_services_and_by_subdirectory_for_agents() -> (
    None
):
    assert volume_images.mounts_for("window", None, 10) == [(_source("diode"), "/diode", False)]
    for index in range(1, 11):
        windows = [m for m in volume_images.mounts_for("agent", index, 10) if "/diode" in m[1]]
        assert windows == [
            (_source("diode", subpath=f"/{_slug(index)}"), f"/diode/{_slug(index)}", False)
        ]
    for role in ("recorder", "review"):
        index = 1 if role == "recorder" else None
        assert not any("diode" in m[0] for m in volume_images.mounts_for(role, index, 10))
    # The monitor counts the vehicle's result files, and only reads them.
    assert [m for m in volume_images.mounts_for("monitor", None, 10) if "diode" in m[0]] == [
        (_source("diode"), "/diode", True)
    ]


def test_mounts_for_emits_placeholders_not_resolved_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPACE_VOLUMES_DIR", "/elsewhere/volumes")
    entries = [
        entry
        for role, indices in (
            ("agent", (1, 2, 10)),
            ("recorder", (1, 4)),
            ("monitor", (None,)),
            ("review", (None,)),
            ("window", (None,)),
            ("vehicle", (None,)),
        )
        for index in indices
        for entry in volume_images.mounts_for(role, index, 10)
    ]

    assert entries
    for source, _target, _read_only in entries:
        assert source.startswith(PLACEHOLDER + "/")
        assert "/data" in source
        assert str(ROOT) not in source
        assert "/elsewhere" not in source


def test_mounts_for_refuses_an_index_outside_the_count_or_a_missing_one() -> None:
    for role, index, count in (("agent", 0, 1), ("agent", 3, 2), ("recorder", None, 2)):
        with pytest.raises(ValueError):
            volume_images.mounts_for(role, index, count)


# settings


def test_the_env_file_applies_when_the_environment_lacks_the_variable(tmp_path: Path) -> None:
    images = _by_name(_plan(tmp_path, text="SPACE_STATE_SIZE=3G\n"))

    assert images["state_ibex"].size == "3G"
    assert images["state_ibex"].size_bytes == 3 * GIB


def test_the_environment_wins_over_the_env_file(tmp_path: Path) -> None:
    images = _by_name(
        _plan(tmp_path, text="SPACE_STATE_SIZE=3G\n", environ={"SPACE_STATE_SIZE": "5G"})
    )

    assert images["state_ibex"].size == "5G"


def test_an_empty_environment_value_wins_and_means_the_default(tmp_path: Path) -> None:
    images = _by_name(
        _plan(
            tmp_path,
            text="SPACE_STATE_SIZE=3G\nSPACE_VOLUMES_DIR=/srv/other\n",
            environ={"SPACE_STATE_SIZE": "", "SPACE_VOLUMES_DIR": ""},
        )
    )

    assert images["state_ibex"].size == "2G"
    assert images["state_ibex"].mnt == ROOT / "volumes" / "state_ibex"


def test_an_empty_file_value_means_the_default(tmp_path: Path) -> None:
    images = _by_name(_plan(tmp_path, text="SPACE_STATE_SIZE=\nSPACE_VOLUMES_DIR=''\n"))

    assert images["state_ibex"].size == "2G"
    assert images["state_ibex"].mnt == ROOT / "volumes" / "state_ibex"


@pytest.mark.parametrize("variable", LITERAL_VARIABLES)
@pytest.mark.parametrize("origin", ["environment", "file"])
def test_a_value_containing_a_dollar_is_refused(tmp_path: Path, variable: str, origin: str) -> None:
    value = "${BASE}/x"
    environ = {variable: value} if origin == "environment" else {}
    source = _env_file(tmp_path, f"{variable}={value}\n" if origin == "file" else "")

    if variable == "SPACE_VOLUME_WARN_PERCENT":
        with pytest.raises(SystemExit, match=variable):
            volume_images.warn_percent(source, environ)
    else:
        with pytest.raises(SystemExit, match=variable):
            volume_images.plan(SLUGS[:1], source, environ)


def test_relative_directories_resolve_against_the_repository_root(tmp_path: Path) -> None:
    images = _by_name(
        _plan(
            tmp_path,
            environ={
                "SPACE_VOLUMES_DIR": "mounts/here",
                "SPACE_VOLUME_IMG_DIR": "./images/../imgs",
            },
        )
    )

    assert images["state_ibex"].mnt == ROOT / "mounts" / "here" / "state_ibex"
    assert images["state_ibex"].data == ROOT / "mounts" / "here" / "state_ibex" / "data"
    assert images["state_ibex"].img == ROOT / "imgs" / "state_ibex.img"


def test_the_defaults_place_mount_points_under_volumes_and_images_beside_it(
    tmp_path: Path,
) -> None:
    images = _by_name(_plan(tmp_path, count=2))

    assert images["transcripts_lupin"].img == ROOT / "volume-images" / "transcripts_lupin.img"
    assert images["transcripts_lupin"].mnt == ROOT / "volumes" / "transcripts_lupin"
    assert images["shared"].img == ROOT / "volume-images" / "shared.img"
    assert volume_images.volumes_root(_env_file(tmp_path), {}) == ROOT / "volumes"


def test_absolute_directories_are_kept(tmp_path: Path) -> None:
    images = _by_name(
        _plan(tmp_path, environ={"SPACE_VOLUMES_DIR": "/srv/v", "SPACE_VOLUME_IMG_DIR": "/srv/i"})
    )

    assert images["pump_ibex"].mnt == Path("/srv/v/pump_ibex")
    assert images["pump_ibex"].img == Path("/srv/i/pump_ibex.img")


@pytest.mark.parametrize("variable", ["SPACE_VOLUMES_DIR", "SPACE_VOLUME_IMG_DIR"])
@pytest.mark.parametrize("value", ["/srv/my volumes", "/srv/tab\there", "with space"])
def test_a_path_containing_whitespace_is_refused(tmp_path: Path, variable: str, value: str) -> None:
    with pytest.raises(SystemExit, match=variable):
        _plan(tmp_path, environ={variable: value})


@pytest.mark.parametrize("variable", ["SPACE_VOLUMES_DIR", "SPACE_VOLUME_IMG_DIR"])
@pytest.mark.parametrize(
    "value", ["/srv/it's", "/srv/a;b", "/srv/a&b", "/srv/a`b", "/srv/a\\b", "/srv/é"]
)
def test_a_path_with_a_shell_significant_character_is_refused(
    tmp_path: Path, variable: str, value: str
) -> None:
    with pytest.raises(SystemExit, match=variable):
        _plan(tmp_path, environ={variable: value})


def test_a_path_of_allowed_characters_is_kept(tmp_path: Path) -> None:
    images = _by_name(_plan(tmp_path, environ={"SPACE_VOLUMES_DIR": "/srv/v+1_2.x-y"}))

    assert images["pump_ibex"].mnt == Path("/srv/v+1_2.x-y/pump_ibex")


def _aliased_images(tmp_path: Path) -> dict:
    images = tmp_path / "images"
    images.mkdir()
    (images / "state_ibex.img").touch()
    (images / "build_ibex.img").symlink_to("state_ibex.img")
    return {"SPACE_VOLUME_IMG_DIR": str(images)}


def test_fstab_refuses_an_image_alias_through_a_symlinked_leaf(tmp_path: Path) -> None:
    environ = _aliased_images(tmp_path)

    with pytest.raises(SystemExit, match="state and build resolve to the same image path"):
        volume_images.main(["fstab"], source=_env_file(tmp_path), environ=environ)


def test_fstab_refuses_a_mount_alias_through_a_symlinked_leaf(tmp_path: Path) -> None:
    volumes = tmp_path / "volumes"
    volumes.mkdir()
    (volumes / "state_ibex").mkdir()
    (volumes / "build_ibex").symlink_to("state_ibex", target_is_directory=True)

    with pytest.raises(SystemExit, match="state and build resolve to the same mount point"):
        volume_images.main(
            ["fstab"], source=_env_file(tmp_path), environ={"SPACE_VOLUMES_DIR": str(volumes)}
        )


def test_two_images_on_one_mount_point_are_refused(tmp_path: Path) -> None:
    first, second = _image(tmp_path, "state_ibex"), _image(tmp_path, "pump_ibex")
    second = second._replace(mnt=first.mnt, data=first.data)

    with pytest.raises(
        SystemExit, match="state_ibex and pump_ibex resolve to the same mount point"
    ):
        volume_images._refuse_aliases([first, second])


def test_every_subcommand_built_on_plan_refuses_an_alias(tmp_path: Path) -> None:
    environ = _aliased_images(tmp_path)
    for command in ("list", "fstab", "plan", "check"):
        with pytest.raises(SystemExit, match="same image path"):
            volume_images.main([command], source=_env_file(tmp_path), environ=environ)


def test_check_fails_two_mounted_images_sharing_one_backing_file(tmp_path: Path) -> None:
    world = World(tmp_path / "repo")
    first, second = _image(tmp_path, "state_ibex"), _image(tmp_path, "pump_ibex")
    world.healthy(first, 3)
    world.healthy(second, 4)
    world.backing["loop4"] = world.backing["loop3"]

    results = volume_images.check([first, second], world.probes(), 80, world.repo)

    assert [result.ready for result in results] == [False, False]
    assert any(
        "backing file" in failure and "pump_ibex" in failure for failure in _failures(results[0])
    )
    assert any(
        "backing file" in failure and "state_ibex" in failure for failure in _failures(results[1])
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1K", 2**10),
        ("5000M", 5000 * 2**20),
        ("10G", 10 * GIB),
        ("2T", 2 * 2**40),
        ("08M", 8 * 2**20),
    ],
)
def test_parse_size_reads_iec_units(text: str, expected: int) -> None:
    assert volume_images.parse_size(text) == expected


@pytest.mark.parametrize(
    "text", ["10GB", "1.5G", "10", "10g", "G", "", " 10G", "10G ", "10GiB", "0G", "-1G", "1e3M"]
)
def test_parse_size_refuses_anything_else(text: str) -> None:
    with pytest.raises(ValueError):
        volume_images.parse_size(text)


def test_an_unparseable_size_is_refused_naming_its_variable(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="SPACE_TRANSCRIPTS_SIZE"):
        _plan(tmp_path, environ={"SPACE_TRANSCRIPTS_SIZE": "32GB"})


def test_the_warn_percentage_defaults_to_80_and_is_validated(tmp_path: Path) -> None:
    source = _env_file(tmp_path)

    assert volume_images.warn_percent(source, {}) == 80
    assert volume_images.warn_percent(source, {"SPACE_VOLUME_WARN_PERCENT": "70"}) == 70
    for bad in ("abc", "0", "101", "7.5"):
        with pytest.raises(SystemExit, match="SPACE_VOLUME_WARN_PERCENT"):
            volume_images.warn_percent(source, {"SPACE_VOLUME_WARN_PERCENT": bad})


# subcommands


def test_list_prints_name_size_image_and_mount_point(tmp_path: Path, capsys) -> None:
    source = _env_file(tmp_path, "SPACE_VOLUMES_DIR=/srv/v\nSPACE_VOLUME_IMG_DIR=/srv/i\n")

    assert volume_images.main(["list"], source=source, environ={}) == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 12
    assert lines[0] == "state_ibex 2G /srv/i/state_ibex.img /srv/v/state_ibex"
    assert "build_ibex 4G /srv/i/build_ibex.img /srv/v/build_ibex" in lines


def test_list_reads_the_fleet_from_the_env_file(tmp_path: Path, capsys) -> None:
    source = _env_file(tmp_path, count=2)

    assert volume_images.main(["list"], source=source, environ={}) == 0

    assert len(capsys.readouterr().out.splitlines()) == 19


def test_names_prints_the_fleet_s_image_names(tmp_path: Path, capsys) -> None:
    source = _env_file(tmp_path, count=3)

    assert volume_images.main(["names"], source=source, environ={}) == 0

    assert capsys.readouterr().out.split() == volume_images.names(SLUGS[:3])


def test_root_prints_the_resolved_volumes_directory(tmp_path: Path, capsys) -> None:
    source = _env_file(tmp_path, "SPACE_VOLUMES_DIR=relative/v\n")

    assert volume_images.main(["root"], source=source, environ={}) == 0

    assert capsys.readouterr().out.strip() == str(ROOT / "relative" / "v")


def test_fstab_lines_carry_absolute_paths_and_the_mount_options(tmp_path: Path, capsys) -> None:
    source = _env_file(tmp_path, "SPACE_VOLUMES_DIR=v\nSPACE_VOLUME_IMG_DIR=/srv/i\n", count=2)

    assert volume_images.main(["fstab"], source=source, environ={}) == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 19
    assert (
        lines[0] == f"/srv/i/state_ibex.img {ROOT}/v/state_ibex ext4 "
        "loop,nofail,nosuid,nodev,X-fstrim.notrim 0 2"
    )
    for line in lines:
        img, mnt, fstype, options, dump, passno = line.split(" ")
        assert img.startswith("/") and mnt.startswith("/")
        assert (fstype, options, dump, passno) == (
            "ext4",
            "loop,nofail,nosuid,nodev,X-fstrim.notrim",
            "0",
            "2",
        )


# plan


def _single_kind(monkeypatch: pytest.MonkeyPatch, size: str = "8G") -> None:
    monkeypatch.setattr(
        volume_images,
        "KINDS",
        (Kind("solo", size, "SPACE_SOLO_SIZE", SHARED, (("agent", "/solo", False, ""),)),),
    )


def _plan_world(tmp_path: Path, total_gib: int, free_gib: float):
    world = World(tmp_path / "repo")
    world.entries[tmp_path] = _st(DIR)
    world.vfs[tmp_path] = _vfs(blocks=total_gib * GIB // 4096, bavail=int(free_gib * GIB) // 4096)
    return world


def _solo_plan(tmp_path: Path):
    return volume_images.plan(
        SLUGS[:1],
        _env_file(tmp_path),
        {"SPACE_VOLUMES_DIR": str(tmp_path / "v"), "SPACE_VOLUME_IMG_DIR": str(tmp_path / "v")},
    )


def test_plan_admits_new_images_that_leave_a_tenth_free(tmp_path, monkeypatch) -> None:
    _single_kind(monkeypatch)
    world = _plan_world(tmp_path, total_gib=100, free_gib=18)

    lines, ok = volume_images.plan_report(_solo_plan(tmp_path), world.probes())

    assert ok, lines
    assert any("solo 8G new, 8.0 GiB to allocate" in line for line in lines)
    assert world.statvfs_calls == [tmp_path]


def test_plan_refuses_new_images_that_would_leave_under_a_tenth_free(tmp_path, monkeypatch) -> None:
    _single_kind(monkeypatch)
    world = _plan_world(tmp_path, total_gib=100, free_gib=17.9)

    lines, ok = volume_images.plan_report(_solo_plan(tmp_path), world.probes())

    assert not ok
    assert any(line.startswith("refused:") for line in lines)


def test_plan_counts_the_unallocated_part_of_a_sparse_image(tmp_path, monkeypatch) -> None:
    _single_kind(monkeypatch)
    image = _solo_plan(tmp_path)[0]
    world = _plan_world(tmp_path, total_gib=100, free_gib=15)
    world.entries[image.img.parent] = _st(DIR)
    world.vfs[image.img.parent] = world.vfs[tmp_path]
    world.entries[image.img] = _st(REG, size=8 * GIB, blocks=2 * GIB // 512)

    lines, ok = volume_images.plan_report([image], world.probes())

    assert not ok
    assert any("solo 8G exists, 6.0 GiB to allocate" in line for line in lines)

    world.entries[image.img] = _st(REG, size=8 * GIB)
    lines, ok = volume_images.plan_report([image], world.probes())
    assert ok, lines
    assert any("solo 8G exists, 0.0 B to allocate" in line for line in lines)


def test_plan_counts_the_growth_a_larger_configured_size_asks_for(tmp_path, monkeypatch) -> None:
    _single_kind(monkeypatch)
    image = _solo_plan(tmp_path)[0]
    world = _plan_world(tmp_path, total_gib=100, free_gib=13)
    world.entries[image.img.parent] = _st(DIR)
    world.vfs[image.img.parent] = world.vfs[tmp_path]
    world.entries[image.img] = _st(REG, size=4 * GIB)

    lines, ok = volume_images.plan_report([image], world.probes())

    assert not ok
    assert any("solo 8G exists, 4.0 GiB to allocate" in line for line in lines)


def test_plan_refuses_an_image_path_that_is_not_a_regular_file(tmp_path, monkeypatch) -> None:
    _single_kind(monkeypatch)
    image = _solo_plan(tmp_path)[0]
    world = _plan_world(tmp_path, total_gib=100, free_gib=90)
    world.entries[image.img] = _st(LNK)

    lines, ok = volume_images.plan_report([image], world.probes())

    assert not ok
    assert any("is not a regular file" in line for line in lines)


def test_plan_checks_each_filesystem_against_its_own_images(tmp_path, monkeypatch) -> None:
    _single_kind(monkeypatch)
    images = volume_images.plan(
        SLUGS[:1],
        _env_file(tmp_path),
        {"SPACE_VOLUMES_DIR": str(tmp_path / "v"), "SPACE_VOLUME_IMG_DIR": str(tmp_path / "a")},
    )
    other = images[0]._replace(name="other", img=tmp_path / "b" / "other.img")
    world = World(tmp_path / "repo")
    for directory, fsid, free in (("a", 1, 50), ("b", 2, 5)):
        world.entries[tmp_path / directory] = _st(DIR)
        world.vfs[tmp_path / directory] = _vfs(
            fsid=fsid, blocks=100 * GIB // 4096, bavail=free * GIB // 4096
        )

    lines, ok = volume_images.plan_report([images[0], other], world.probes())

    assert not ok
    refusals = [line for line in lines if line.startswith("refused:")]
    assert len(refusals) == 1
    assert str(tmp_path / "b") in refusals[0]


def test_plan_subcommand_exits_1_when_refused(tmp_path, monkeypatch, capsys) -> None:
    _single_kind(monkeypatch)
    world = _plan_world(tmp_path, total_gib=100, free_gib=10)
    environ = {
        "SPACE_VOLUMES_DIR": str(tmp_path / "v"),
        "SPACE_VOLUME_IMG_DIR": str(tmp_path / "v"),
    }

    status = volume_images.main(
        ["plan"], source=_env_file(tmp_path), environ=environ, probes=world.probes()
    )

    assert status == 1
    assert "refused:" in capsys.readouterr().out


# check


def test_a_healthy_image_is_ready(tmp_path: Path) -> None:
    _world, result = _check_one(tmp_path)

    assert result.ready, _failures(result)
    assert result.fill == [("used", 10, ""), ("inodes", 1, "")]


def _unmounted(world, image):
    world.mounts.clear()


def _wrong_backing(world, image):
    world.backing["loop3"] = "/somewhere/else.img"


def _shared_device(world, image):
    world.entries[image.mnt].st_dev = world.entries[world.repo].st_dev


def _not_loop(world, image):
    world.mounts[0] = world.mounts[0].replace("/dev/loop3", "/dev/nvme0n1p3")


def _not_ext4(world, image):
    world.mounts[0] = world.mounts[0].replace(" - ext4 ", " - xfs ")


def _sparse(world, image):
    world.entries[image.img].st_blocks = 8


def _root_owner(world, image):
    world.entries[image.mnt].st_uid = UID


def _root_group(world, image):
    world.entries[image.mnt].st_gid = UID


def _root_group_writable(world, image):
    world.entries[image.mnt].st_mode = stat.S_IFDIR | 0o775


def _root_other_writable(world, image):
    world.entries[image.mnt].st_mode = stat.S_IFDIR | 0o757


def _data_missing(world, image):
    del world.entries[image.data]


def _data_misowned(world, image):
    world.entries[image.data].st_uid = 1234


def _data_wrong_group(world, image):
    world.entries[image.data].st_gid = 0


def _data_wrong_mode(world, image):
    world.entries[image.data].st_mode = stat.S_IFDIR | 0o700


def _data_a_file(world, image):
    world.entries[image.data] = _st(REG, uid=UID, gid=UID)


def _image_missing(world, image):
    del world.entries[image.img]


def _image_symlink(world, image):
    world.entries[image.img] = _st(LNK)


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (_unmounted, "image is not mounted"),
        (_wrong_backing, "is backed by /somewhere/else.img"),
        (_shared_device, "shares the repository's device"),
        (_not_loop, "mounted filesystem is ext4 on /dev/nvme0n1p3"),
        (_not_ext4, "mounted filesystem is xfs"),
        (_sparse, "image is sparse"),
        (_root_owner, f"image root is {UID}:0"),
        (_root_group, f"image root is 0:{UID}"),
        (_root_group_writable, "mode 0775"),
        (_root_other_writable, "mode 0757"),
        (_data_missing, "data/ is missing"),
        (_data_misowned, f"data/ is a directory 1234:{UID}"),
        (_data_wrong_group, f"data/ is a directory {UID}:0"),
        (_data_wrong_mode, "mode 0700"),
        (_data_a_file, "data/ is a regular file"),
        (_image_missing, "is missing"),
        (_image_symlink, "is a symlink"),
    ],
)
def test_check_fails_an_image_that_is_not_ready(tmp_path, mutate, expected) -> None:
    _world, result = _check_one(tmp_path, mutate)

    assert not result.ready
    assert any(expected in failure for failure in _failures(result)), _failures(result)


def test_check_reports_a_symlinked_mount_point_without_following_it(tmp_path: Path) -> None:
    def symlinked(world, image):
        world.entries[image.mnt] = _st(LNK)

    world, result = _check_one(tmp_path, symlinked)
    image = result.image

    assert not result.ready
    assert any("is a symlink" in failure for failure in _failures(result))
    assert world.statvfs_calls == []
    assert image.data not in world.lstat_calls


def test_check_reports_a_symlinked_data_directory_without_following_it(tmp_path: Path) -> None:
    def symlinked(world, image):
        world.entries[image.data] = _st(LNK)

    _world, result = _check_one(tmp_path, symlinked)

    assert not result.ready
    assert "data/ is a symlink" in _failures(result)


def test_check_with_the_host_probes_refuses_real_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target"
    (target / "data").mkdir(parents=True)
    volumes = tmp_path / "volumes"
    volumes.mkdir()
    image = _image(tmp_path)
    image.img.write_bytes(b"")
    image.mnt.symlink_to(target)

    result = volume_images.check_image(image, Probes(), 80)

    assert not result.ready
    assert any("is a symlink" in failure for failure in _failures(result))

    image.mnt.unlink()
    image.mnt.mkdir()
    image.data.symlink_to(target / "data")
    result = volume_images.check_image(image, Probes(), 80)
    assert not result.ready
    assert "image is not mounted" in _failures(result)
    assert image.data.is_symlink()


@pytest.mark.parametrize(
    "used, level", [(79, ""), (80, "WARN"), (94, "WARN"), (95, "CRITICAL"), (100, "CRITICAL")]
)
def test_fill_levels_warn_at_80_and_turn_critical_at_95(tmp_path, used, level) -> None:
    def fill(world, image):
        world.vfs[image.mnt] = _vfs(blocks=100, bfree=100 - used, files=100, ffree=100 - used)

    _world, result = _check_one(tmp_path, fill)

    assert result.ready
    assert result.fill == [("used", used, level), ("inodes", used, level)]


def test_the_warn_percentage_moves_the_warning_but_not_critical(tmp_path) -> None:
    def fill(world, image):
        world.vfs[image.mnt] = _vfs(blocks=100, bfree=25, files=100, ffree=100)

    _world, result = _check_one(tmp_path, fill, warn=70)
    assert result.fill[0] == ("used", 75, "WARN")

    _world, result = _check_one(tmp_path, fill, warn=99)
    assert result.fill[0] == ("used", 75, "")
    assert volume_images.fill_level(96, 99) == "CRITICAL"


def test_check_subcommand_reads_the_warn_percentage_and_exits_on_readiness(
    tmp_path, monkeypatch, capsys
) -> None:
    _single_kind(monkeypatch)
    environ = {
        "SPACE_VOLUMES_DIR": str(tmp_path / "v"),
        "SPACE_VOLUME_IMG_DIR": str(tmp_path / "v"),
        "SPACE_VOLUME_WARN_PERCENT": "60",
    }
    source = _env_file(tmp_path)
    image = volume_images.plan(SLUGS[:1], source, environ)[0]
    world = World(volume_images.REPO_ROOT)
    world.healthy(image, 5, used=65)

    status = volume_images.main(["check"], source=source, environ=environ, probes=world.probes())

    out = capsys.readouterr().out
    assert status == 0, out
    assert "used 65% WARN" in out
    assert "check: 1 image(s) ready" in out

    del world.entries[image.data]
    status = volume_images.main(["check"], source=source, environ=environ, probes=world.probes())
    out = capsys.readouterr().out
    assert status == 1
    assert "FAIL  data/ is missing" in out
    assert "check: 1 of 1 image(s) not ready" in out


def test_mountinfo_parsing_unescapes_and_keeps_the_topmost_mount() -> None:
    text = (
        "36 1 8:3 / /srv/a\\040b rw - ext4 /dev/sda3 rw\n"
        "37 36 7:1 / /srv/a\\040b rw shared:2 master:1 - ext4 /dev/loop1 rw\n"
        "malformed line\n"
    )

    assert volume_images.mounts_by_point(text) == {"/srv/a b": ("ext4", "/dev/loop1")}


# data-driven


def test_a_kind_added_to_the_table_reaches_every_subcommand(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(volume_images, "KINDS", volume_images.KINDS + (SYNTHETIC,))
    environ = {
        "SPACE_VOLUMES_DIR": str(tmp_path / "v"),
        "SPACE_VOLUME_IMG_DIR": str(tmp_path / "v"),
    }
    source = _env_file(tmp_path, count=2)
    world = World(volume_images.REPO_ROOT)
    world.entries[tmp_path] = _st(DIR)
    world.vfs[tmp_path] = _vfs(blocks=10**9)

    assert volume_images.names(SLUGS[:2])[-2:] == ["poll_ibex", "poll_lupin"]
    assert (f"{PLACEHOLDER}/poll_{_slug(2)}/data", "/poll", False) in volume_images.mounts_for(
        "agent", 2, 2
    )

    outputs = {}
    for command in ("list", "names", "fstab", "plan", "check"):
        volume_images.main([command], source=source, environ=environ, probes=world.probes())
        outputs[command] = capsys.readouterr().out

    poll = tmp_path / "v" / "poll_lupin"
    assert f"poll_lupin 16M {poll}.img {poll}" in outputs["list"]
    assert "poll_lupin" in outputs["names"].split()
    assert (
        f"{poll}.img {poll} ext4 loop,nofail,nosuid,nodev,X-fstrim.notrim 0 2" in outputs["fstab"]
    )
    assert f"poll_lupin 16M new, 16.0 MiB to allocate: {poll}.img" in outputs["plan"]
    assert "poll_lupin: not ready" in outputs["check"]
    assert len(volume_images.plan(SLUGS[:2], source, environ)) == 21


# ignore files and image allow-list


def test_volumes_and_images_stay_out_of_git_and_the_image_build_context() -> None:
    for name in (".gitignore", ".dockerignore"):
        lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
        assert "volumes/" in lines, name
        assert "volume-images/" in lines, name


def test_no_image_copies_the_host_volume_tooling() -> None:
    for dockerfile in ROOT.glob("Dockerfile*"):
        text = dockerfile.read_text(encoding="utf-8")
        for name in ("volume_images.py", "create_volume_image.sh", "env_file.py"):
            assert name not in text, f"{dockerfile.name} names {name}"
        assert "scripts/" not in text, dockerfile.name


@pytest.mark.parametrize("role", ["agent", "recorder", "monitor", "review", "window", "vehicle"])
def test_no_service_binds_a_target_inside_another_of_its_binds(role: str) -> None:
    """Docker makes a nested bind's mountpoint inside the outer volume: in a read-only one it
    cannot, and the service never starts; in a writable one it litters the volume."""
    for index in (1, 3) if role in ("agent", "recorder") else (None,):
        targets = [target for _source, target, _ro in volume_images.mounts_for(role, index, 3)]
        for outer in targets:
            for inner in targets:
                assert not inner.startswith(outer.rstrip("/") + "/"), (role, outer, inner)
