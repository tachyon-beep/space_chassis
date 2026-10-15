#!/usr/bin/env python3
"""The operator journal: what each agent's repository and /shared looked like, kept outside them.

`/work` is a tmpfs inside each agent's container, and a reseed or a container replacement erases
it, tags, archived conversations and all. The journal is the durable record: every pass it takes
`/work/.git` out of each agent, keeps the objects and refs in a host-owned repository, records the
container's restart count and the watchdog's lines since the last pass, and snapshots `/shared`.
A reseed, a tag move or a correlated break in `/shared` becomes attributable after the fact.

**It runs no agent code.** That is the whole design:

- The repository leaves the container as a tar stream from `docker exec … tar`. `docker cp` cannot
  read a tmpfs mount; tar comes from the read-only image root, and `docker exec` runs with the
  container's configured environment, not the agent's.
- The stream is bounded in bytes and time, every member is checked before any is extracted (no
  absolute or `..` path, no link, no device, no member over the cap), and only object files, refs,
  HEAD and the two recovery files are extracted. `objects/info/` never is: its `alternates` would
  point host git at any host path the agent names.
- **The copy is never opened by git.** Its `config` is the agent's -- `core.hooksPath`,
  `core.fsmonitor`, `include.path` and the rest would come with it. Object files are copied in as
  files, ref values are parsed here in Python, and host git only ever runs on the journal's own bare
  repository, with a config this script writes, under an environment built from an allowlist.
- A full `git fsck` verifies what came in. A snapshot that fails loses its refs and every object
  this pass copied.
- `/shared` is copied to a host temp tree first: regular files, directories and symlinks (as links)
  only, with every `.git` entry dropped, so a nested repository or a `gitdir:` file is data, never a
  repository git would open.

Watchdog lines and the recovery state are written inside the agent's container -- the agent's
stdout is tee'd into the watchdog's -- so they are recorded as the agent's claim. The restart count
comes from docker and is not.

    python3 scripts/journal.py --once
    python3 scripts/journal.py --every 300
    COMPOSE="docker compose -p <project> …" AGENTS="agent_1 agent_2" python3 scripts/journal.py --once --root <dir>
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import os
import re
import select
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))
sys.path.insert(0, str(PROJECT / "scripts"))

from common import append_jsonl, read_bounded, write_text_atomic  # noqa: E402
from health import printable  # noqa: E402

JOURNAL_MAX_BYTES = 256 * 1024 * 1024
JOURNAL_TIMEOUT_SECONDS = 120
# The host repository per agent grows with every pass that brings new objects (an agent's repack
# brings its whole history again): past this, snapshots are skipped and say so.
JOURNAL_REPO_MAX_BYTES = 4 * 1024 * 1024 * 1024
MAX_MEMBERS = 200_000
JSON_BYTES = 1 << 20
WATCHDOG_LINES = 200
DOCKER_TIMEOUT_SECONDS = 60
DEFAULT_ROOT = PROJECT / "operator" / "journal"
DEFAULT_COMPOSE = "docker compose -p space-chassis"

SHA = re.compile(r"[0-9a-f]{40}")
REF_NAME = re.compile(r"(heads|tags)/[A-Za-z0-9._/-]{1,200}")
SERVICE = re.compile(r"[A-Za-z0-9_-]{1,64}")
SLUG = re.compile(r"[a-z][a-z0-9_]{0,31}")
LOOSE = re.compile(r"\.git/objects/[0-9a-f]{2}/[0-9a-f]{38}")
PACK = re.compile(r"\.git/objects/pack/pack-[0-9a-f]{40,64}\.(pack|idx)")
KEPT = {".git/HEAD", ".git/packed-refs", ".git/aurora-recovery.json", ".git/aurora-progress.json"}
WATCHDOG = re.compile(
    r"^(agent exited \(|agent stopped after inactivity|recovery exhausted|watchdog file changed"
    r"|Recovery event \d+:)"
)
HOST_CONFIG = (
    "[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n\tbare = true\n"
    "\thooksPath = /dev/null\n\tfsmonitor = false\n[gc]\n\tauto = 0\n"
)
IDENTITY = ("-c", "user.name=operator journal", "-c", "user.email=journal@localhost")


def claim(value) -> dict:
    return {"value": value, "claim": "agent"}


# ------------------------------------------------------------------ processes


def _base_env() -> dict:
    return {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG")}


def _docker_env() -> dict:
    keep = ("PATH", "HOME", "USER", "LANG", "XDG_RUNTIME_DIR")
    return {k: v for k, v in os.environ.items() if k in keep or k.startswith("DOCKER_")}


def host_git(
    repo: Path,
    *args: str,
    input: bytes | None = None,  # noqa: A002 -- subprocess's own name
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    """git on the journal's own repository, and nothing else: the only way this module runs git."""
    repo = Path(repo).resolve()
    env = _base_env()
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    if extra_env and "GIT_INDEX_FILE" in extra_env:
        env["GIT_INDEX_FILE"] = str(extra_env["GIT_INDEX_FILE"])
    return subprocess.run(
        ["git", f"--git-dir={repo}", *args],
        cwd=repo.parent,
        env=env,
        input=input,
        capture_output=True,
        timeout=JOURNAL_TIMEOUT_SECONDS,
    )


def _docker(argv: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            argv,
            env=_docker_env(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=DOCKER_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _container(compose: list[str], service: str) -> str | None:
    result = _docker([*compose, "ps", "-q", service])
    cid = result.stdout.strip() if result is not None and result.returncode == 0 else ""
    return cid.splitlines()[0] if cid else None


# ------------------------------------------------------------------ the stream


def _parses(data: bytes) -> bool:
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
            tar.getmembers()
    except (tarfile.TarError, OSError, EOFError):
        return False
    return True


def _stop(proc: subprocess.Popen) -> None:
    with contextlib.suppress(OSError):
        proc.kill()
    with contextlib.suppress(subprocess.SubprocessError, OSError):
        proc.wait(timeout=5)


def stream_work(compose: list[str], service: str, limit: int, timeout: float) -> bytes | str:
    """`/work/.git` as a tar stream, or why not: "too large", "timed out", "exec failed: <rc>"."""
    try:
        proc = subprocess.Popen(
            [*compose, "exec", "-T", service, "tar", "-cf", "-", "-C", "/work", ".git"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_docker_env(),
        )
    except OSError as error:
        return f"exec failed: {error}"
    deadline = time.monotonic() + timeout
    fd = proc.stdout.fileno()
    chunks, total = [], 0
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _stop(proc)
                return "timed out"
            ready, _, _ = select.select([fd], [], [], min(remaining, 1.0))
            if not ready:
                continue
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                _stop(proc)
                return "too large"
            chunks.append(chunk)
        try:
            rc = proc.wait(timeout=max(1.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            _stop(proc)
            return "timed out"
    finally:
        proc.stdout.close()
    data = b"".join(chunks)
    # tar exits 1 when a file changed while it was read: the chassis rewrites its progress file
    # every turn, so a busy agent's archive is still an archive.
    if rc == 0 or (rc == 1 and _parses(data)):
        return data
    return f"exec failed: {rc}"


def _safe_ref(name: str) -> bool:
    return (
        REF_NAME.fullmatch(name) is not None
        and ".." not in name
        and "//" not in name
        and not name.endswith((".lock", "/", "."))
        and not any(part.startswith(".") or part == "" for part in name.split("/"))
    )


def _read_json(path: Path):
    raw = read_bounded(path, JSON_BYTES) if path.is_file() else None
    try:
        return json.loads(raw) if raw is not None else None
    except ValueError:
        return None


def _wanted(name: str) -> bool:
    if name in KEPT or LOOSE.fullmatch(name) or PACK.fullmatch(name):
        return True
    return name.startswith(".git/refs/") and not name.startswith(".git/objects/")


def _unpack(tar: tarfile.TarFile, into: Path) -> str | None:
    """Check every member, then extract the allowlisted ones; a refusal reason, or None."""
    try:
        members = tar.getmembers()
    except (tarfile.TarError, OSError, EOFError) as error:
        return f"refused: unreadable archive: {error}"
    if len(members) > MAX_MEMBERS:
        return f"refused: {len(members)} members"
    into.mkdir(parents=True, exist_ok=True)
    for member in members:
        # data_filter strips a leading "/" rather than refusing it; this refuses it outright.
        if member.name.startswith("/") or ".." in member.name.split("/"):
            return f"refused: {member.name}: absolute or parent path"
        if not (member.isreg() or member.isdir()):
            return f"refused: {member.name}: not a regular file or directory"
        if member.size > JOURNAL_MAX_BYTES:
            return f"refused: {member.name}: {member.size} bytes"
        try:
            tarfile.data_filter(member, str(into))
        except tarfile.FilterError as error:
            return f"refused: {member.name}: {type(error).__name__}"
    for member in members:
        if member.isreg() and _wanted(member.name):
            tar.extract(member, path=into, filter="data", set_attrs=False)
    return None


def extract(archive: bytes, into: Path) -> dict | str:
    """The archive's object files, refs and recovery files, or why it was refused."""
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            refusal = _unpack(tar, into)
    except (tarfile.TarError, OSError) as error:
        return f"refused: not a tar archive: {error}"
    if refusal is not None:
        return refusal

    dot_git = into / ".git"
    refs: dict[str, str] = {}
    packed = (
        read_bounded(dot_git / "packed-refs", JSON_BYTES)
        if (dot_git / "packed-refs").is_file()
        else None
    )
    for line in (packed or b"").decode("utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and SHA.fullmatch(parts[0]) and parts[1].startswith("refs/"):
            name = parts[1][len("refs/") :]
            if _safe_ref(name):
                refs[name] = parts[0]
    root = dot_git / "refs"
    for directory, _dirs, files in os.walk(root):
        for file in files:
            path = Path(directory) / file
            name = path.relative_to(root).as_posix()
            value = (read_bounded(path, 128) or b"").decode("utf-8", errors="replace").strip()
            if _safe_ref(name) and SHA.fullmatch(value):
                refs[name] = value
    head_raw = read_bounded(dot_git / "HEAD", 256) if (dot_git / "HEAD").is_file() else None
    head = (head_raw or b"").decode("utf-8", errors="replace").strip()
    if head.startswith("ref: "):
        head = head[len("ref: ") :]
    return {
        "refs": dict(sorted(refs.items())),
        "head": head,
        "recovery": _read_json(dot_git / "aurora-recovery.json"),
        "progress": _read_json(dot_git / "aurora-progress.json"),
    }


# ------------------------------------------------------------------ the host repository


def _ensure_repo(repo: Path) -> None:
    if not (repo / "HEAD").is_file():
        repo.parent.mkdir(parents=True, exist_ok=True)
        result = host_git(repo, "init", "--bare", "-q")
        if result.returncode:
            raise RuntimeError(f"git init failed: {result.stderr.decode(errors='replace')}")
    write_text_atomic(repo / "config", HOST_CONFIG)


def _drop_refs(repo: Path, prefix: str) -> None:
    with contextlib.suppress(subprocess.SubprocessError, OSError):
        listed = host_git(repo, "for-each-ref", "--format=%(refname)", prefix)
        for name in listed.stdout.decode(errors="replace").split():
            host_git(repo, "update-ref", "-d", name)


def _tree_bytes(root: Path) -> int:
    total = 0
    for directory, _dirs, files in os.walk(root):
        for file in files:
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(directory, file)).st_size
    return total


def import_snapshot(repo: Path, copy: Path, info: dict, stamp: str) -> str:
    """Object files in as files, refs by value, then a full fsck; a failure leaves nothing behind."""
    _ensure_repo(repo)
    source = copy / ".git" / "objects"
    incoming = (
        sum(
            path.lstat().st_size
            for path in source.rglob("*")
            if path.is_file()
            and (
                LOOSE.fullmatch(".git/objects/" + path.relative_to(source).as_posix())
                or PACK.fullmatch(".git/objects/" + path.relative_to(source).as_posix())
            )
            and not (repo / "objects" / path.relative_to(source)).exists()
        )
        if source.is_dir()
        else 0
    )
    if _tree_bytes(repo / "objects") + incoming > JOURNAL_REPO_MAX_BYTES:
        return f"skipped: repository over {JOURNAL_REPO_MAX_BYTES} bytes"
    copied: list[Path] = []
    for directory, _dirs, files in os.walk(source):
        for file in files:
            path = Path(directory) / file
            name = ".git/objects/" + path.relative_to(source).as_posix()
            if not (LOOSE.fullmatch(name) or PACK.fullmatch(name)):
                continue
            if not stat.S_ISREG(path.lstat().st_mode):
                continue
            target = repo / "objects" / path.relative_to(source)
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            os.chmod(target, 0o444)
            copied.append(target)

    def reject(step: str) -> str:
        _drop_refs(repo, f"refs/journal/{stamp}/")
        for target in copied:
            with contextlib.suppress(OSError):
                target.unlink()
        return f"rejected: {step}"

    refs = dict(info.get("refs") or {})
    head = info.get("head") or ""
    if SHA.fullmatch(head):
        refs["HEAD"] = head
    elif head.startswith("refs/") and head[len("refs/") :] in refs:
        refs["HEAD"] = refs[head[len("refs/") :]]
    for name, sha in refs.items():
        try:
            if host_git(repo, "update-ref", f"refs/journal/{stamp}/{name}", sha).returncode:
                return reject(f"update-ref {name}")
        except subprocess.SubprocessError:
            return reject(f"update-ref {name} timed out")
    try:
        if host_git(repo, "fsck", "--no-dangling", "--no-progress").returncode:
            return reject("fsck")
    except subprocess.SubprocessError:
        return reject("fsck timed out")
    return "ok"


def git_refuses(name: str) -> bool:
    """A `.git` in any spelling git treats as one: dropped from the copy so a nested repository is
    never a repository. Not the authority on what git will index -- `git add --ignore-errors` is."""
    folded = name.rstrip(". ").lower()
    return folded == ".git" or re.fullmatch(r"git~\d+", folded) is not None


def copy_regular(source: Path, target: Path, budget: int) -> int | None:
    """Copy one regular file without following a link or blocking on a FIFO, within budget."""
    try:
        handle = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(handle).st_mode):
            return None
        written = 0
        with open(target, "xb") as out:
            while chunk := os.read(handle, 1 << 20):
                written += len(chunk)
                if written > budget:
                    break
                out.write(chunk)
        if written > budget:
            target.unlink()
            return None
        return written
    except OSError:
        with contextlib.suppress(OSError):
            target.unlink()
        return None
    finally:
        os.close(handle)


def snapshot_shared(repo: Path, shared: Path, stamp: str, limit: int) -> str:
    """/shared by content: one walk into a host temp copy, links as links, git's refused names out."""
    if not shared.is_dir():
        return "absent"
    work = repo.parent / ".shared-tmp" / stamp
    index = repo.parent / ".shared-tmp" / f"{stamp}.index"
    shutil.rmtree(work, ignore_errors=True)
    total = entries = skipped = 0
    try:
        work.mkdir(parents=True)
        for directory, dirs, files in os.walk(shared):
            relative = Path(directory).relative_to(shared)
            for name in list(dirs) + files:
                entries += 1
                if entries > MAX_MEMBERS:
                    return f"skipped: over {MAX_MEMBERS} entries"
                source = Path(directory) / name
                target = work / relative / name
                is_dir = name in dirs
                if git_refuses(name):
                    skipped += 1
                    if is_dir:
                        dirs.remove(name)
                    continue
                try:
                    mode = source.lstat().st_mode
                    if stat.S_ISLNK(mode):
                        os.symlink(os.readlink(source), target)
                        if is_dir:
                            dirs.remove(name)
                    elif stat.S_ISDIR(mode):
                        target.mkdir()
                    elif stat.S_ISREG(mode):
                        if source.lstat().st_size > limit - total:
                            return f"skipped: over {limit} bytes"
                        copied = copy_regular(source, target, limit - total)
                        if copied is None:
                            skipped += 1
                        else:
                            total += copied
                    else:
                        skipped += 1
                except OSError:
                    skipped += 1
                    if is_dir and name in dirs:
                        dirs.remove(name)
        _ensure_repo(repo)
        env = {"GIT_INDEX_FILE": index}
        # git is the authority on which names it will not index; a copy of its rules here would
        # differ from it somewhere, and any difference would blind the snapshot. --ignore-errors
        # leaves those paths out (exit 1) and indexes the rest.
        added = host_git(
            repo, f"--work-tree={work}", "add", "-A", "--force", "--ignore-errors", extra_env=env
        )
        if added.returncode not in (0, 1):
            return "rejected: add"
        skipped += added.stderr.decode(errors="replace").count("unable to add")
        tree = host_git(repo, "write-tree", extra_env=env)
        if tree.returncode:
            return "rejected: write-tree"
        commit = host_git(
            repo, *IDENTITY, "commit-tree", tree.stdout.decode().strip(), "-m", f"shared {stamp}"
        )
        if commit.returncode:
            return "rejected: commit-tree"
        sha = commit.stdout.decode().strip()
        if host_git(repo, "update-ref", f"refs/journal/shared/{stamp}", sha).returncode:
            return "rejected: update-ref"
    finally:
        shutil.rmtree(work, ignore_errors=True)
        with contextlib.suppress(OSError):
            index.unlink()
    return "ok" if not skipped else f"ok: {skipped} entr(ies) skipped"


# ------------------------------------------------------------------ the containers


def _slug(compose: list[str], service: str, cid: str | None) -> str:
    if cid:
        result = _docker(
            ["docker", "inspect", "--format", "{{range .Config.Env}}{{println .}}{{end}}", cid]
        )
        for line in (result.stdout if result is not None else "").splitlines():
            if line.startswith("AGENT_SLUG="):
                value = line[len("AGENT_SLUG=") :]
                if SLUG.fullmatch(value):
                    return value
    return service


def container_events(compose: list[str], service: str, since: str | None) -> dict:
    restarts = state = None
    cid = _container(compose, service)
    if cid:
        result = _docker(["docker", "inspect", "-f", "{{.RestartCount}} {{.State.Status}}", cid])
        parts = result.stdout.split() if result is not None and result.returncode == 0 else []
        if len(parts) == 2 and parts[0].isdigit():
            restarts, state = int(parts[0]), parts[1]
    argv = [*compose, "logs", "--no-color", "--no-log-prefix"]
    if since:
        argv += ["--since", since]
    result = _docker([*argv, service])
    lines = [
        line
        for line in (result.stdout if result is not None else "").splitlines()
        if WATCHDOG.match(line)
    ]
    return {
        "restarts": restarts,
        "state": state,
        "watchdog_lines": {"lines": lines[-WATCHDOG_LINES:], "claim": "agent"},
    }


def running_agents(compose: list[str]) -> list[str]:
    result = _docker([*compose, "ps", "--format", "{{.Service}}"])
    names = (result.stdout if result is not None else "").split()
    return sorted({n for n in names if n.startswith("agent_") and SERVICE.fullmatch(n)})


def journal_once(
    compose: list[str], agents: list[str], root: Path, volumes: Path, now: dt.datetime
) -> list[dict]:
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    at = now.isoformat()
    records = []
    for service in agents:
        if not SERVICE.fullmatch(service):
            continue
        slug = _slug(compose, service, _container(compose, service))
        home = root / slug
        home.mkdir(parents=True, exist_ok=True)
        since_raw = read_bounded(home / "last_poll", 256)
        since = since_raw.decode(errors="replace").strip() if since_raw else None
        record = {
            "at": at,
            "slug": slug,
            "service": service,
            "work": None,
            "refs": {},
            "recovery": claim(None),
            "progress": claim(None),
        }
        incoming = root / ".incoming" / f"{stamp}-{service}"
        try:
            shutil.rmtree(incoming, ignore_errors=True)
            archive = stream_work(compose, service, JOURNAL_MAX_BYTES, JOURNAL_TIMEOUT_SECONDS)
            if isinstance(archive, str):
                record["work"] = archive
            else:
                info = extract(archive, incoming)
                if isinstance(info, str):
                    record["work"] = info
                else:
                    record["refs"] = info["refs"]
                    record["recovery"] = claim(info["recovery"])
                    record["progress"] = claim(info["progress"])
                    record["work"] = import_snapshot(home / "work.git", incoming, info, stamp)
        except Exception as error:  # noqa: BLE001 -- one agent's failure is a record, not a crash
            record["work"] = f"error: {type(error).__name__}: {error}"
        finally:
            shutil.rmtree(incoming, ignore_errors=True)
        record.update(container_events(compose, service, since))
        append_jsonl(home / "journal.jsonl", record)
        write_text_atomic(home / "last_poll", at + "\n")
        records.append(record)

    shared = snapshot_shared(
        root / "shared.git", volumes / "shared" / "data", stamp, JOURNAL_MAX_BYTES
    )
    append_jsonl(root / "shared.jsonl", {"at": at, "shared": shared})
    with contextlib.suppress(OSError):
        (root / ".incoming").rmdir()
    return records


def summary_line(record: dict) -> str:
    """One printable line per agent: refusal reasons can carry names the agent chose."""
    return printable(
        f"{record['at']} {record['slug']}: work {record['work']}, restarts {record.get('restarts')}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    when = parser.add_mutually_exclusive_group(required=True)
    when.add_argument("--once", action="store_true")
    when.add_argument("--every", type=float, metavar="SECONDS")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--volumes", type=Path, default=None)
    args = parser.parse_args(argv)

    import volume_images  # noqa: PLC0415 -- reads the env file only when no --volumes is given

    volumes = args.volumes or volume_images.volumes_root()
    root = args.root.resolve()
    compose = shlex.split(os.environ.get("COMPOSE") or DEFAULT_COMPOSE)
    while True:
        agents = os.environ.get("AGENTS", "").split() or running_agents(compose)
        for record in journal_once(compose, agents, root, volumes, dt.datetime.now(dt.UTC)):
            print(
                f"{record['at']} {record['slug']}: work {record['work']}, restarts {record['restarts']}"
            )
        if args.once:
            return 0
        time.sleep(args.every)


if __name__ == "__main__":
    sys.exit(main())
