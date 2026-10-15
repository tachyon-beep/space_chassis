"""The bounded volumes: one loop-mounted ext4 image per kind, per agent where scoped so.

Adapted from Aurora's scripts/volume_images.py (42faf41). Aurora runs several hosts in one
container; here each agent has its own container, so a per-agent kind gives every agent its own
image, named <kind>_<slug>, and a shared kind is one image the fleet's services share. The slugs
come from the roster block scripts/roster.py writes into .env.

This manifest is the single source of the images' names, sizes and paths. Each image is a
preallocated file under SPACE_VOLUME_IMG_DIR, mounted on the host at <SPACE_VOLUMES_DIR>/<name>;
compose binds the data/ directory inside it, so a service whose image is not mounted refuses to
start instead of writing to the host disk.

Settings are read the way compose reads them: a variable present in the process environment wins,
even when empty, over the env file, and an empty value means the default. Values containing "$"
are refused, because compose would interpolate them and this module does not. The fleet is the
exception: FLEET_* is read from the env file alone, because the roster block there is the one
record of which agents the images were made for. Nothing is read at import.

This is operator tooling. It runs on the host, is invoked by no component, and ships in no image.
"""

import argparse
import math
import os
import re
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from env_file import env_value, source_path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

PER_AGENT = "per_agent"
SHARED = "shared"

# The roles that mount images: each agent and its recorder have one container per slug; the
# monitor, the review panel and the window services (the vehicle and the fake diode) see the fleet.
AGENT_ROLES = ("agent", "recorder")
FLEET_ROLES = ("monitor", "review", "window")

# The interpolation placeholder compose resolves; the generated compose carries it.
SOURCE_ROOT = "${SPACE_VOLUMES_DIR:-./volumes}"

VOLUMES_DIR_VARIABLE = "SPACE_VOLUMES_DIR"
IMG_DIR_VARIABLE = "SPACE_VOLUME_IMG_DIR"
WARN_PERCENT_VARIABLE = "SPACE_VOLUME_WARN_PERCENT"
DEFAULT_DIR = "./volumes"
# Beside volumes/, not inside it, so archiving an old volumes/ tree leaves the image files alone.
DEFAULT_IMG_DIR = "./volume-images"
DEFAULT_WARN_PERCENT = 80
CRITICAL_PERCENT = 95
# plan refuses an allocation that would leave less free than this percentage of the filesystem.
MIN_FREE_PERCENT = 10

# The uid and gid every service runs as, and the mode of the data/ directory.
SERVICE_UID = 1000
DATA_MODE = 0o755

# X-fstrim.notrim keeps the weekly fstrim.timer from discarding unused blocks through the loop
# device, which punches the backing file back to sparse.
FSTAB_OPTIONS = "loop,nofail,nosuid,nodev,X-fstrim.notrim"

# A slug names images and mount points and is interpolated into compose: the drawn alphabet only.
_SLUG = re.compile(r"[a-z][a-z0-9_]{0,31}")


class Kind(NamedTuple):
    """One kind of bounded volume.

    mounts holds (role, target, read_only, subpath). "{slug}" in a target or subpath is the agent's
    slug. A subpath binds a directory inside data/ rather than data/ itself: the shared window is
    one image, and each agent binds only its own directory in it.
    """

    name: str
    default_size: str
    size_variable: str
    scope: str
    mounts: tuple[tuple[str, str, bool, str], ...]


KINDS: tuple[Kind, ...] = (
    Kind("state", "2G", "SPACE_STATE_SIZE", PER_AGENT, (("agent", "/state", False, ""),)),
    Kind("pump", "512M", "SPACE_PUMP_SIZE", PER_AGENT, (("agent", "/pump", False, ""),)),
    Kind("build", "4G", "SPACE_BUILD_SIZE", PER_AGENT, (("agent", "/build", False, ""),)),
    Kind(
        "telemetry",
        "2G",
        "SPACE_TELEMETRY_SIZE",
        PER_AGENT,
        (
            ("agent", "/telemetry", False, ""),
            ("monitor", "/telemetry/agents/{slug}", True, ""),
            ("review", "/telemetry/agents/{slug}", True, ""),
        ),
    ),
    Kind(
        "transcripts",
        "4G",
        "SPACE_TRANSCRIPTS_SIZE",
        PER_AGENT,
        (
            ("recorder", "/transcripts", False, ""),
            ("monitor", "/transcripts/{slug}", True, ""),
            ("review", "/transcripts/{slug}", True, ""),
        ),
    ),
    Kind(
        "llm_sock",
        "64M",
        "SPACE_LLM_SOCK_SIZE",
        PER_AGENT,
        (("agent", "/llm/sock", True, ""), ("recorder", "/llm/sock", False, "")),
    ),
    Kind(
        "llm_console",
        "64M",
        "SPACE_LLM_CONSOLE_SIZE",
        PER_AGENT,
        (("agent", "/llm/console", False, ""), ("recorder", "/llm/console", True, "")),
    ),
    Kind("shared", "8G", "SPACE_SHARED_SIZE", SHARED, (("agent", "/shared", False, ""),)),
    Kind(
        "diode",
        "2G",
        "SPACE_DIODE_SIZE",
        SHARED,
        (
            ("agent", "/diode/{slug}", False, "{slug}"),
            ("window", "/diode", False, ""),
            ("monitor", "/diode", True, ""),
        ),
    ),
    Kind(
        "fleet_ledger",
        "64M",
        "SPACE_FLEET_LEDGER_SIZE",
        SHARED,
        (("recorder", "/ledger", False, ""),),
    ),
    Kind(
        "operator_telemetry",
        "1G",
        "SPACE_OPERATOR_TELEMETRY_SIZE",
        SHARED,
        (("monitor", "/telemetry", False, ""), ("review", "/telemetry", True, "")),
    ),
)

_SAFE_PATH = re.compile(r"[A-Za-z0-9/._+-]+")
_SIZE = re.compile(r"([0-9]+)([KMGT])")
_UNITS = {"K": 2**10, "M": 2**20, "G": 2**30, "T": 2**40}


def parse_size(text: str) -> int:
    """Return the bytes in a size such as 10G or 5000M.

    An integer followed by K, M, G or T, in IEC units as fallocate reads them.
    10GB, 1.5G, a bare number and a zero size are refused.
    """
    match = _SIZE.fullmatch(text)
    if match is None:
        raise ValueError(f"unrecognised size {text!r}: expected a whole number then K, M, G or T")
    value = int(match.group(1)) * _UNITS[match.group(2)]
    if value == 0:
        raise ValueError(f"size {text!r} is zero")
    return value


def kind(name: str) -> Kind:
    """The manifest entry of one kind, read from the table alone."""
    for entry in KINDS:
        if entry.name == name:
            return entry
    raise KeyError(name)


def _check_slugs(slugs: list[str]) -> None:
    if not slugs:
        raise SystemExit("FLEET: the roster names no agent")
    for slug in slugs:
        if not isinstance(slug, str) or not _SLUG.fullmatch(slug):
            raise SystemExit(f"FLEET: slug {slug!r} is outside [a-z][a-z0-9_]{{0,31}}")
    if len(set(slugs)) != len(slugs):
        raise SystemExit("FLEET: a slug appears twice")


def _kind_names(kind: Kind, slugs: list[str]) -> list[str]:
    if kind.scope == SHARED:
        return [kind.name]
    return [f"{kind.name}_{slug}" for slug in slugs]


def names(slugs: list[str]) -> list[str]:
    """Every image name for these agents, in manifest order. Reads no file."""
    _check_slugs(slugs)
    return [name for kind in KINDS for name in _kind_names(kind, slugs)]


def fleet(source: Path | None = None, environ=None) -> list[str]:
    """The fleet's slugs, from the roster block in the env file alone.

    The process environment is ignored here on purpose (see the module docstring). FLEET_COUNT,
    FLEET_SLUGS and FLEET_1_SLUG..FLEET_N_SLUG must agree, and every slug must be the drawn
    alphabet, or nothing is planned.
    """
    path = source_path() if source is None else Path(source)
    if not path.is_file():
        raise SystemExit(f"FLEET: no environment file at {path}; run scripts/prepare_host.sh")
    raw_count = env_value("FLEET_COUNT", path)
    if raw_count is None or not re.fullmatch(r"[0-9]+", raw_count) or int(raw_count) < 1:
        raise SystemExit(f"FLEET_COUNT {raw_count!r} in {path} is not a whole number of at least 1")
    count = int(raw_count)
    listed = [slug for slug in (env_value("FLEET_SLUGS", path) or "").split(",") if slug]
    numbered = [env_value(f"FLEET_{n}_SLUG", path) for n in range(1, count + 1)]
    if None in numbered:
        missing = numbered.index(None) + 1
        raise SystemExit(f"FLEET_{missing}_SLUG is missing from {path}")
    if len(listed) != count or listed != numbered:
        raise SystemExit(f"FLEET_COUNT, FLEET_SLUGS and FLEET_N_SLUG disagree in {path}")
    _check_slugs(numbered)
    return numbered


def _slug_variable(index: int) -> str:
    return f"${{FLEET_{index}_SLUG:-agent_{index}}}"


def mounts_for(role: str, index: int | None, count: int) -> list[tuple[str, str, bool]]:
    """One role's bind entries, as (source, target, read_only), for the generated compose.

    An agent or a recorder is one container per index and mounts its own agent's images; the
    monitor, the review panel and the window services see the whole fleet. Each slug is the
    compose variable FLEET_<index>_SLUG, so the file does not depend on which roster was drawn,
    and each source is the interpolation placeholder for the image's data/, never a resolved path.
    """
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError(f"count must be a whole number of at least 1, not {count!r}")
    if role in AGENT_ROLES:
        if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= count:
            raise ValueError(f"{role} index {index!r} is outside 1..{count}")
        indices = [index]
    elif role in FLEET_ROLES:
        indices = list(range(1, count + 1))
    else:
        raise ValueError(f"unknown role {role!r}")
    entries = []
    for kind in KINDS:
        for mount_role, target, read_only, subpath in kind.mounts:
            if mount_role != role:
                continue
            for n in indices if kind.scope == PER_AGENT or "{slug}" in target else [None]:
                slug = _slug_variable(n) if n is not None else ""
                image = f"{kind.name}_{slug}" if kind.scope == PER_AGENT else kind.name
                inner = f"/{subpath.format(slug=slug)}" if subpath else ""
                source = f"{SOURCE_ROOT}/{image}/data{inner}"
                entries.append((source, target.format(slug=slug), read_only))
    return entries


def _raw(key: str, source: Path | None, environ) -> str | None:
    """A setting as compose sees it: the process environment first, then the env file."""
    env = os.environ if environ is None else environ
    if key in env:
        return env[key]
    path = source_path() if source is None else Path(source)
    if not path.is_file():
        return None
    return env_value(key, path)


def _setting(key: str, default: str, source: Path | None, environ) -> str:
    """A literal storage setting, with an empty or absent value meaning the default."""
    raw = _raw(key, source, environ)
    if raw is not None and "$" in raw:
        raise SystemExit(
            f"{key} must be a literal value: it contains '$', which compose would "
            "interpolate and this tooling does not"
        )
    return raw if raw else default


def _path_setting(key: str, default: str, source: Path | None, environ) -> Path:
    """A path setting, relative values resolved against the repository root.

    Compose resolves a relative bind source against the project directory, which is the
    repository root. A path with a character outside [A-Za-z0-9/._+-] is refused: an fstab line
    cannot carry whitespace, and the commands the creator prints single-quote each path, which no
    other character can break.
    """
    value = _setting(key, default, source, environ)
    path = Path(os.path.normpath(REPO_ROOT / value))
    if not _SAFE_PATH.fullmatch(str(path)):
        raise SystemExit(
            f"{key} resolves to a path with a character outside [A-Za-z0-9/._+-]: {str(path)!r}"
        )
    return path


def volumes_root(source: Path | None = None, environ=None) -> Path:
    """The resolved SPACE_VOLUMES_DIR, under which every image is mounted."""
    return _path_setting(VOLUMES_DIR_VARIABLE, DEFAULT_DIR, source, environ)


def warn_percent(source: Path | None = None, environ=None) -> int:
    """The fill percentage at or above which check prints WARN."""
    raw = _setting(WARN_PERCENT_VARIABLE, str(DEFAULT_WARN_PERCENT), source, environ)
    if not re.fullmatch(r"[0-9]+", raw) or not 1 <= int(raw) <= 100:
        raise SystemExit(f"{WARN_PERCENT_VARIABLE} must be a whole number from 1 to 100")
    return int(raw)


class Image(NamedTuple):
    """One image of the layout: its file, its mount point and the bound data/."""

    name: str
    kind: str
    size: str
    size_bytes: int
    img: Path
    mnt: Path
    data: Path


def plan(slugs: list[str], source: Path | None = None, environ=None) -> list[Image]:
    """Every image for these agents, with its size and resolved paths."""
    _check_slugs(slugs)
    if source is None:
        source = source_path()
    root = volumes_root(source, environ)
    img_dir = _path_setting(IMG_DIR_VARIABLE, DEFAULT_IMG_DIR, source, environ)
    images = []
    for kind in KINDS:
        size = _setting(kind.size_variable, kind.default_size, source, environ)
        try:
            size_bytes = parse_size(size)
        except ValueError as error:
            raise SystemExit(f"{kind.size_variable}: {error}") from error
        for name in _kind_names(kind, slugs):
            mnt = root / name
            images.append(
                Image(name, kind.name, size, size_bytes, img_dir / f"{name}.img", mnt, mnt / "data")
            )
    _refuse_aliases(images)
    return images


def _refuse_aliases(images: list[Image]) -> None:
    """Refuse two images that resolve to one image file or one mount point.

    Two mounts sharing one data/ directory would let a service that clears its
    own volume clear another's, so the layout is refused before anything is
    created.
    """
    for label, key in (
        ("image path", lambda image: image.img),
        ("mount point", lambda image: image.mnt),
    ):
        seen: dict[str, Image] = {}
        for image in images:
            canonical = os.path.realpath(key(image))
            earlier = seen.setdefault(canonical, image)
            if earlier is not image:
                raise SystemExit(
                    f"{earlier.kind} and {image.kind} resolve to the same {label}: {canonical}"
                    if earlier.kind != image.kind
                    else f"{earlier.name} and {image.name} resolve to the same {label}: {canonical}"
                )


def list_lines(images: list[Image]) -> list[str]:
    """NAME SIZE IMG MNT per image, the form prepare_host.sh reads."""
    return [f"{image.name} {image.size} {image.img} {image.mnt}" for image in images]


def fstab_lines(images: list[Image]) -> list[str]:
    """One /etc/fstab line per image, mounting it at boot."""
    return [f"{image.img} {image.mnt} ext4 {FSTAB_OPTIONS} 0 2" for image in images]


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except OSError:
        return None


def _mountinfo() -> str:
    return Path("/proc/self/mountinfo").read_text(encoding="utf-8", errors="surrogateescape")


def _backing_file(device: str) -> str | None:
    try:
        text = Path(f"/sys/block/{device}/loop/backing_file").read_text(
            encoding="utf-8", errors="surrogateescape"
        )
    except OSError:
        return None
    return text.rstrip("\n")


@dataclass(frozen=True)
class Probes:
    """The host inspections plan and check make; tests replace any of them.

    lstat returns None for a path that cannot be inspected, and never follows a
    link.
    """

    lstat: Callable[[Path], os.stat_result | None] = _lstat
    statvfs: Callable[[Path], os.statvfs_result] = os.statvfs
    mountinfo: Callable[[], str] = _mountinfo
    backing_file: Callable[[str], str | None] = _backing_file


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(value) < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"


def _allocated(st: os.stat_result) -> int:
    return st.st_blocks * 512


def _existing_ancestor(path: Path, probes: Probes) -> Path:
    while probes.lstat(path) is None and path != path.parent:
        path = path.parent
    return path


def plan_report(images: list[Image], probes: Probes | None = None) -> tuple[list[str], bool]:
    """Report what allocation remains and whether the filesystems have room for it.

    The bytes still to allocate are a new image's size, plus, for an existing
    image, its unallocated part and any growth its configured size asks for.
    Each filesystem holding images must keep at least a tenth of its size free
    after the allocation. An existing image path that is not a regular file is
    refused.
    """
    probes = probes or Probes()
    lines = []
    ok = True
    filesystems: dict[object, list] = {}
    for image in images:
        st = probes.lstat(image.img)
        if st is None:
            state, need = "new", image.size_bytes
        elif not stat.S_ISREG(st.st_mode):
            lines.append(f"{image.name}: refused: {image.img} exists and is not a regular file")
            ok = False
            continue
        else:
            holes = max(0, st.st_size - _allocated(st))
            growth = max(0, image.size_bytes - st.st_size)
            state, need = "exists", holes + growth
        anchor = _existing_ancestor(image.img.parent, probes)
        fs = probes.statvfs(anchor)
        entry = filesystems.setdefault(fs.f_fsid, [anchor, fs, 0])
        entry[2] += need
        lines.append(f"{image.name} {image.size} {state}, {_human(need)} to allocate: {image.img}")
    for anchor, fs, need in filesystems.values():
        free = fs.f_bavail * fs.f_frsize
        total = fs.f_blocks * fs.f_frsize
        after = free - need
        share = math.floor(after * 100 / total) if total else 0
        lines.append(
            f"filesystem of {anchor}: {_human(free)} free of {_human(total)}; "
            f"{_human(need)} to allocate leaves {share}% free"
        )
        if total == 0 or after * 100 < total * MIN_FREE_PERCENT:
            lines.append(
                f"refused: allocating {_human(need)} on {anchor} would leave less than "
                f"{MIN_FREE_PERCENT}% of it free"
            )
            ok = False
    return lines, ok


_ESCAPE = re.compile(r"\\([0-7]{3})")
_LOOP = re.compile(r"/dev/(loop[0-9]+)")


def _unescape(field: str) -> str:
    return _ESCAPE.sub(lambda match: chr(int(match.group(1), 8)), field)


def mounts_by_point(text: str) -> dict[str, tuple[str, str]]:
    """Map each mount point in mountinfo text to its (fstype, source).

    A later line for the same mount point is the mount stacked on top, which is
    the one a path resolves to, so it replaces the earlier one.
    """
    mounts = {}
    for line in text.splitlines():
        left, separator, right = line.partition(" - ")
        fields = left.split(" ")
        tail = right.split(" ")
        if not separator or len(fields) < 5 or len(tail) < 2:
            continue
        mounts[_unescape(fields[4])] = (tail[0], _unescape(tail[1]))
    return mounts


def _canonical(path: Path) -> str:
    """The path as the kernel reports it: its directories resolved, its own name kept."""
    return os.path.join(os.path.realpath(path.parent), path.name)


class Verdict(NamedTuple):
    ok: bool
    text: str


class ImageCheck(NamedTuple):
    """One image's readiness verdicts and its fill readings."""

    image: Image
    verdicts: list[Verdict]
    fill: list[tuple[str, int, str]]

    @property
    def ready(self) -> bool:
        return all(verdict.ok for verdict in self.verdicts)


def _percent(used: int, whole: int) -> int:
    return math.ceil(used * 100 / whole) if whole > 0 else 0


def fill_level(percent: int, warn: int) -> str:
    """CRITICAL at 95% or more, WARN at the warn percentage or more, else empty."""
    if percent >= CRITICAL_PERCENT:
        return "CRITICAL"
    if percent >= warn:
        return "WARN"
    return ""


def _kind_of(st: os.stat_result) -> str:
    if stat.S_ISLNK(st.st_mode):
        return "a symlink"
    if stat.S_ISDIR(st.st_mode):
        return "a directory"
    if stat.S_ISREG(st.st_mode):
        return "a regular file"
    return "neither a file nor a directory"


def check_image(
    image: Image,
    probes: Probes,
    warn: int,
    repo_root: Path = REPO_ROOT,
    mounts: dict[str, tuple[str, str]] | None = None,
) -> ImageCheck:
    """Inspect one image without root and without following a link."""
    verdicts: list[Verdict] = []
    fill: list[tuple[str, int, str]] = []
    if mounts is None:
        mounts = mounts_by_point(probes.mountinfo())

    img = probes.lstat(image.img)
    if img is None:
        verdicts.append(Verdict(False, f"image {image.img} is missing"))
    elif not stat.S_ISREG(img.st_mode):
        verdicts.append(Verdict(False, f"image {image.img} is {_kind_of(img)}"))
    else:
        verdicts.append(Verdict(True, f"image {image.img} is a regular file"))
        allocated = _allocated(img)
        verdicts.append(
            Verdict(True, "image is fully allocated")
            if allocated >= img.st_size
            else Verdict(False, f"image is sparse: {allocated} of {img.st_size} bytes allocated")
        )

    mnt = probes.lstat(image.mnt)
    if mnt is None:
        verdicts.append(Verdict(False, f"mount point {image.mnt} is missing"))
        return ImageCheck(image, verdicts, fill)
    if not stat.S_ISDIR(mnt.st_mode):
        verdicts.append(Verdict(False, f"mount point {image.mnt} is {_kind_of(mnt)}"))
        return ImageCheck(image, verdicts, fill)
    verdicts.append(Verdict(True, f"mount point {image.mnt} is a directory"))

    mounted = mounts.get(_canonical(image.mnt))
    if mounted is None:
        verdicts.append(Verdict(False, "image is not mounted"))
        return ImageCheck(image, verdicts, fill)
    verdicts.append(Verdict(True, "image is mounted"))

    fstype, device = mounted
    loop = _LOOP.fullmatch(device)
    if fstype != "ext4" or loop is None:
        verdicts.append(Verdict(False, f"mounted filesystem is {fstype} on {device}"))
    else:
        verdicts.append(Verdict(True, f"mounted filesystem is ext4 on {device}"))
        backing = probes.backing_file(loop.group(1))
        verdicts.append(
            Verdict(True, f"{device} is backed by this image")
            if backing == _canonical(image.img)
            else Verdict(False, f"{device} is backed by {backing}, not {image.img}")
        )

    repo = probes.lstat(repo_root)
    if repo is None:
        verdicts.append(Verdict(False, f"repository root {repo_root} could not be inspected"))
    elif mnt.st_dev != repo.st_dev:
        verdicts.append(Verdict(True, "mount is a device other than the repository's"))
    else:
        verdicts.append(Verdict(False, "mount shares the repository's device"))

    owner = f"{mnt.st_uid}:{mnt.st_gid} mode {stat.S_IMODE(mnt.st_mode):04o}"
    if mnt.st_uid == 0 and mnt.st_gid == 0 and not mnt.st_mode & 0o022:
        verdicts.append(Verdict(True, f"image root is {owner}"))
    else:
        verdicts.append(
            Verdict(
                False, f"image root is {owner}; it must be 0:0 and not group- or other-writable"
            )
        )

    data = probes.lstat(image.data)
    expected = f"{SERVICE_UID}:{SERVICE_UID} mode {DATA_MODE:04o}"
    if data is None:
        verdicts.append(Verdict(False, f"data/ is missing; it must be a directory {expected}"))
    elif not stat.S_ISDIR(data.st_mode):
        verdicts.append(Verdict(False, f"data/ is {_kind_of(data)}"))
    else:
        found = f"{data.st_uid}:{data.st_gid} mode {stat.S_IMODE(data.st_mode):04o}"
        correct = (
            data.st_uid == SERVICE_UID
            and data.st_gid == SERVICE_UID
            and stat.S_IMODE(data.st_mode) == DATA_MODE
        )
        verdicts.append(
            Verdict(True, f"data/ is a directory {found}")
            if correct
            else Verdict(False, f"data/ is a directory {found}; it must be {expected}")
        )

    vfs = probes.statvfs(image.mnt)
    used = vfs.f_blocks - vfs.f_bfree
    used_percent = _percent(used, used + vfs.f_bavail)
    inode_percent = _percent(vfs.f_files - vfs.f_ffree, vfs.f_files)
    fill.append(("used", used_percent, fill_level(used_percent, warn)))
    fill.append(("inodes", inode_percent, fill_level(inode_percent, warn)))
    return ImageCheck(image, verdicts, fill)


def check(
    images: list[Image],
    probes: Probes | None = None,
    warn: int = DEFAULT_WARN_PERCENT,
    repo_root: Path = REPO_ROOT,
) -> list[ImageCheck]:
    """Inspect every image; see check_image."""
    probes = probes or Probes()
    mounts = mounts_by_point(probes.mountinfo())
    results = [check_image(image, probes, warn, repo_root, mounts) for image in images]
    backed: dict[str, list[ImageCheck]] = {}
    for result in results:
        mounted = mounts.get(_canonical(result.image.mnt))
        loop = _LOOP.fullmatch(mounted[1]) if mounted and mounted[0] == "ext4" else None
        backing = probes.backing_file(loop.group(1)) if loop else None
        if backing:
            backed.setdefault(os.path.realpath(backing), []).append(result)
    for backing, group in backed.items():
        if len(group) > 1:
            for result in group:
                others = ", ".join(r.image.name for r in group if r is not result)
                result.verdicts.append(
                    Verdict(False, f"backing file {backing} is shared with {others}")
                )
    return results


def check_report(results: list[ImageCheck]) -> tuple[list[str], bool]:
    """Format check results. Fill readings never decide readiness."""
    lines = []
    for result in results:
        lines.append(f"{result.image.name}: {'ready' if result.ready else 'not ready'}")
        for verdict in result.verdicts:
            lines.append(f"  {'ok  ' if verdict.ok else 'FAIL'}  {verdict.text}")
        for label, percent, level in result.fill:
            lines.append(f"  {label} {percent}%{' ' + level if level else ''}")
    failing = sum(1 for result in results if not result.ready)
    if failing:
        lines.append(f"check: {failing} of {len(results)} image(s) not ready")
    else:
        lines.append(f"check: {len(results)} image(s) ready")
    return lines, failing == 0


def main(
    argv: list[str] | None = None,
    *,
    source: Path | None = None,
    environ=None,
    probes: Probes | None = None,
) -> int:
    """Run one subcommand and return its exit status."""
    parser = argparse.ArgumentParser(
        prog="volume_images.py", description="The bounded volume images and their mounts."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("list", "print NAME SIZE IMG MNT for each image"),
        ("fstab", "print an /etc/fstab line for each image"),
        ("plan", "report the allocation still needed and refuse it without room"),
        ("check", "report whether each image is ready; needs no root"),
        ("names", "print the image names of the fleet in the env file"),
    ):
        commands.add_parser(name, help=text)
    commands.add_parser("root", help="print the resolved SPACE_VOLUMES_DIR")
    args = parser.parse_args(argv)

    if source is None:
        source = source_path()
    if args.command == "root":
        print(volumes_root(source, environ))
        return 0

    slugs = fleet(source, environ)
    if args.command == "names":
        print("\n".join(names(slugs)))
        return 0
    images = plan(slugs, source, environ)
    if args.command == "list":
        print("\n".join(list_lines(images)))
        return 0
    if args.command == "fstab":
        print("\n".join(fstab_lines(images)))
        return 0

    if args.command == "plan":
        lines, ok = plan_report(images, probes)
    else:
        warn = warn_percent(source, environ)
        lines, ok = check_report(check(images, probes, warn))
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
