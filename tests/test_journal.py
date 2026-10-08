"""scripts/journal.py: the operator journal, which takes data out of the agents and runs none of it.

The agent's `/work/.git` is a repository whose config is the agent's. The fixture plants that
config with everything that makes git run code -- an fsmonitor, a hooks path covering every hook,
and an include that sets an ssh command -- and plants `objects/info/alternates` pointing at a host
directory. A positive control shows the plants are live when git opens that repository. The journal
must take the repository out through a fake `docker` (a tar stream, as `docker exec … tar` gives
it), import it as files into a host-owned bare repository, and never open the copy with git: a
recording `git` on PATH logs every invocation, and no marker may ever appear.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import zlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import journal  # noqa: E402

REAL_GIT = shutil.which("git")
CLEAN = {
    "PATH": os.environ["PATH"],
    "HOME": "/nonexistent",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}
HOOKS = [
    "applypatch-msg",
    "pre-applypatch",
    "post-applypatch",
    "pre-commit",
    "pre-merge-commit",
    "prepare-commit-msg",
    "commit-msg",
    "post-commit",
    "pre-rebase",
    "post-checkout",
    "post-merge",
    "pre-push",
    "pre-receive",
    "update",
    "proc-receive",
    "post-receive",
    "post-update",
    "reference-transaction",
    "push-to-checkout",
    "pre-auto-gc",
    "post-rewrite",
    "sendemail-validate",
    "fsmonitor-watchman",
    "p4-changelist",
    "p4-prepare-changelist",
    "p4-post-changelist",
    "p4-pre-submit",
    "post-index-change",
]
NOW = dt.datetime(2026, 10, 9, 12, 0, 0, tzinfo=dt.UTC)

FAKE_DOCKER = r"""#!/bin/sh
. "__FAKE_ENV__"
case "$*" in
    *" exec -T "*" tar "*)
        [ -n "${FAKE_SLEEP:-}" ] && sleep "$FAKE_SLEEP"
        if [ -n "${FAKE_TAR_FILE:-}" ]; then cat "$FAKE_TAR_FILE"; else tar -cf - -C "$FAKE_REPO_PARENT" .git; fi
        exit "${FAKE_TAR_RC:-0}" ;;
    *" ps --format"*) printf 'agent_1\n'; exit 0 ;;
    *" ps -q "*) for last in "$@"; do :; done; printf 'cid-%s\n' "$last"; exit 0 ;;
    *inspect*Config.Env*) printf 'PATH=/usr/bin\nAGENT_SLUG=otter_one\n'; exit 0 ;;
    *inspect*RestartCount*) printf '3 running\n'; exit 0 ;;
    *" logs "*) cat "$FAKE_LOGS"; exit 0 ;;
esac
exit 1
"""


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        [REAL_GIT, *args], cwd=cwd, env=CLEAN, capture_output=True, text=True, check=True
    ).stdout


def marker_script(path: Path, markers: Path, name: str) -> Path:
    path.write_text(f"#!/bin/sh\n: > '{markers}/{name}-'$$\n")
    path.chmod(0o755)
    return path


class World:
    def __init__(self, root: Path):
        self.root = root
        self.markers = root / "markers"
        self.markers.mkdir()
        self.parent = root / "agent"
        self.work = self.parent
        self.parent.mkdir()
        git("init", "-q", "-b", "main", str(self.parent))
        (self.parent / "agent.py").write_text("print('the agent')\n")
        git("add", "agent.py", cwd=self.parent)
        git("-c", "user.name=a", "-c", "user.email=a@b", "commit", "-qm", "seed", cwd=self.parent)
        git("tag", "baseline", cwd=self.parent)
        git("tag", "rescue", cwd=self.parent)
        self.commit = git("rev-parse", "HEAD", cwd=self.parent).strip()
        dot_git = self.parent / ".git"
        (dot_git / "aurora-recovery.json").write_text(
            json.dumps({"phase": None, "selected": {"ref": "refs/tags/baseline"}})
        )
        hooks = root / "hooks"
        hooks.mkdir()
        for hook in HOOKS:
            marker_script(hooks / hook, self.markers, f"hook-{hook}")
        fsmonitor = marker_script(root / "fsmonitor.sh", self.markers, "fsmonitor")
        ssh = marker_script(root / "ssh.sh", self.markers, "ssh")
        include = root / "included.config"
        include.write_text(f"[core]\n\tsshCommand = {ssh}\n")
        with open(dot_git / "config", "a") as config:
            config.write(
                f"[core]\n\tfsmonitor = {fsmonitor}\n\thooksPath = {hooks}\n"
                f"[include]\n\tpath = {include}\n"
            )
        self.alternate = root / "host_objects"
        self.alternate.mkdir()
        (dot_git / "objects" / "info").mkdir(exist_ok=True)
        (dot_git / "objects" / "info" / "alternates").write_text(f"{self.alternate}\n")

        self.bin = root / "bin"
        self.bin.mkdir()
        self.fake_env = root / "fake.env"
        self.settings: dict[str, str] = {}
        docker = self.bin / "docker"
        docker.write_text(FAKE_DOCKER.replace("__FAKE_ENV__", str(self.fake_env)))
        docker.chmod(0o755)
        self.git_log = root / "git-calls.jsonl"
        recorder = self.bin / "git"
        recorder.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            f"with open({str(self.git_log)!r}, 'a') as log:\n"
            "    log.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(),\n"
            "        'GIT_DIR': os.environ.get('GIT_DIR'),\n"
            "        'GIT_WORK_TREE': os.environ.get('GIT_WORK_TREE')}) + '\\n')\n"
            f"os.execv({REAL_GIT!r}, [{REAL_GIT!r}, *sys.argv[1:]])\n"
        )
        recorder.chmod(0o755)
        self.logs = root / "logs.txt"
        self.logs.write_text(
            "agent starting autonomous loop\n"
            "agent exited (44); action pause\n"
            "Recovery event 12: started from the image seed at abc; fresh incarnation.\n"
            "calling tool run with args: {}\n"
        )
        self.journal = root / "journal"
        self.volumes = root / "volumes"
        (self.volumes / "shared" / "data").mkdir(parents=True)

    def environment(self, monkeypatch) -> None:
        """The fake docker reads its settings from a file: the journal hands docker an allowlist."""
        monkeypatch.setenv("PATH", f"{self.bin}:{os.environ['PATH']}")
        self.fake(FAKE_REPO_PARENT=str(self.parent), FAKE_LOGS=str(self.logs))

    def fake(self, **settings: str) -> None:
        self.settings.update(settings)
        self.fake_env.write_text(
            "".join(f"{key}='{value}'\n" for key, value in self.settings.items())
        )

    def once(self, now: dt.datetime = NOW) -> list[dict]:
        return journal.journal_once(
            ["docker", "compose", "-p", "probe"], ["agent_1"], self.journal, self.volumes, now
        )

    def git_calls(self) -> list[dict]:
        if not self.git_log.exists():
            return []
        return [json.loads(line) for line in self.git_log.read_text().splitlines()]

    def marks(self) -> list[str]:
        return sorted(path.name for path in self.markers.iterdir())


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = World(tmp_path)
    w.environment(monkeypatch)
    return w


def host_repo(world: World) -> Path:
    return world.journal / "otter_one" / "work.git"


def test_the_planted_config_does_run_when_git_opens_the_copy(world):
    git("--git-dir", str(world.parent / ".git"), "--work-tree", str(world.parent), "status")
    assert any(name.startswith("fsmonitor") for name in world.marks())


def test_a_snapshot_lands_in_the_host_repository_with_its_tags(world):
    record = world.once()[0]
    assert record["work"] == "ok", record
    assert record["slug"] == "otter_one"
    stamp = "20261009T120000Z"
    for tag in ("baseline", "rescue"):
        resolved = git(
            "--git-dir", str(host_repo(world)), "rev-parse", f"refs/journal/{stamp}/tags/{tag}"
        )
        assert resolved.strip() == world.commit
    assert record["refs"]["tags/baseline"] == world.commit
    assert record["recovery"]["claim"] == "agent"
    assert record["recovery"]["value"]["selected"]["ref"] == "refs/tags/baseline"
    lines = (world.journal / "otter_one" / "journal.jsonl").read_text().splitlines()
    assert json.loads(lines[0]) == record


def test_no_git_call_ever_touches_the_agent_s_copy(world):
    world.once()
    calls = world.git_calls()
    assert calls, "the journal ran no git at all"
    incoming = str(world.journal / ".incoming")
    for call in calls:
        for value in [
            *call["argv"],
            call["cwd"],
            call["GIT_DIR"] or "",
            call["GIT_WORK_TREE"] or "",
        ]:
            assert incoming not in value, call
            assert str(world.parent) not in value, call
        assert not {"fetch", "clone", "bundle", "pull", "remote"} & set(call["argv"]), call


def test_nothing_planted_in_the_agent_s_git_config_runs(world):
    world.once()
    world.once(NOW + dt.timedelta(minutes=5))
    assert world.marks() == []


def _archive(*members: tuple[tarfile.TarInfo, bytes | None]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        head = tarfile.TarInfo(".git/HEAD")
        head.size = len(b"ref: refs/heads/main\n")
        tar.addfile(head, io.BytesIO(b"ref: refs/heads/main\n"))
        for info, data in members:
            tar.addfile(info, io.BytesIO(data) if data is not None else None)
    return buffer.getvalue()


def _regular(name: str, data: bytes = b"x") -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    return info, data


def _special(name: str, kind: bytes, target: str = "") -> tuple[tarfile.TarInfo, None]:
    info = tarfile.TarInfo(name)
    info.type = kind
    info.linkname = target
    return info, None


@pytest.mark.parametrize(
    "member",
    [
        _regular("../escape"),
        _regular("/abs"),
        _special(".git/refs/tags/evil", tarfile.SYMTYPE, "/etc"),
        _special(".git/objects/ab/link", tarfile.LNKTYPE, "/etc/passwd"),
        _special(".git/dev", tarfile.CHRTYPE),
    ],
    ids=["dotdot", "absolute", "symlink", "hardlink", "device"],
)
def test_a_hostile_archive_is_refused(world, tmp_path, monkeypatch, member):
    archive = tmp_path / "hostile.tar"
    archive.write_bytes(_archive(member))
    world.fake(FAKE_TAR_FILE=str(archive))
    record = world.once()[0]
    assert record["work"].startswith("refused"), record
    assert not (tmp_path / "escape").exists()
    assert not Path("/abs").exists()
    assert not host_repo(world).exists() or not list((host_repo(world) / "refs").rglob("*"))


def test_refs_that_are_not_object_ids_or_safe_names_are_ignored(world, tmp_path):
    tags = world.parent / ".git" / "refs" / "tags"
    (tags / "not-a-sha").write_text("hello\n")
    (tags / "x.lock").write_text(world.commit + "\n")
    (world.parent / ".git" / "refs" / "heads" / "evil..name").write_text(world.commit + "\n")
    info = journal.extract(
        journal.stream_work(["docker", "compose", "-p", "probe"], "agent_1", 1 << 30, 60),
        tmp_path / "into",
    )
    assert isinstance(info, dict), info
    assert set(info["refs"]) == {"heads/main", "tags/baseline", "tags/rescue"}


def test_objects_info_alternates_is_never_copied(world):
    record = world.once()[0]
    assert record["work"] == "ok"
    assert not (host_repo(world) / "objects" / "info" / "alternates").exists()


def test_a_busy_agent_s_tar_exit_1_is_still_a_snapshot(world, monkeypatch):
    world.fake(FAKE_TAR_RC="1")
    assert world.once()[0]["work"] == "ok"
    world.fake(FAKE_TAR_RC="2")
    assert world.once(NOW + dt.timedelta(minutes=1))[0]["work"] == "exec failed: 2"


def test_an_oversized_stream_is_skipped_not_stored(world, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL_MAX_BYTES", 1024)
    record = world.once()[0]
    assert record["work"] == "too large"
    assert not host_repo(world).exists()


def test_a_stream_that_never_ends_times_out(world, monkeypatch):
    world.fake(FAKE_SLEEP="30")
    monkeypatch.setattr(journal, "JOURNAL_TIMEOUT_SECONDS", 1)
    started = dt.datetime.now()
    record = world.once()[0]
    assert record["work"] == "timed out"
    assert (dt.datetime.now() - started).total_seconds() < 20


def _corrupt_one_blob(dot_git: Path) -> None:
    blob = git("--git-dir", str(dot_git), "rev-parse", "HEAD:agent.py").strip()
    path = dot_git / "objects" / blob[:2] / blob[2:]
    path.chmod(0o644)
    path.write_bytes(zlib.compress(b"blob 7\x00forged!"))


def test_a_corrupt_blob_is_rejected_by_fsck_and_leaves_no_refs_or_objects(world):
    _corrupt_one_blob(world.parent / ".git")
    record = world.once()[0]
    assert record["work"].startswith("rejected"), record
    repo = host_repo(world)
    refs = git("--git-dir", str(repo), "for-each-ref", "--format=%(refname)")
    assert refs.strip() == ""
    loose = [p for p in (repo / "objects").rglob("*") if p.is_file() and "pack" not in p.parts]
    assert loose == []


def test_watchdog_lines_are_recorded_as_the_agent_s_claim_and_restarts_are_not(world):
    record = world.once()[0]
    assert record["restarts"] == 3
    assert record["state"] == "running"
    assert record["watchdog_lines"] == {
        "lines": [
            "agent exited (44); action pause",
            "Recovery event 12: started from the image seed at abc; fresh incarnation.",
        ],
        "claim": "agent",
    }


def test_shared_is_snapshotted_by_content_and_its_gitattributes_run_nothing(world):
    shared = world.volumes / "shared" / "data"
    (shared / "notes.txt").write_text("joint work\n")
    (shared / ".gitattributes").write_text("* filter=evil diff=evil\n")
    nested = shared / "lib" / ".git"
    nested.mkdir(parents=True)
    fsmonitor = marker_script(world.root / "nested.sh", world.markers, "nested")
    (nested / "config").write_text(f"[core]\n\tfsmonitor = {fsmonitor}\n")
    (shared / "lib" / "code.py").write_text("x = 1\n")
    (shared / "other").mkdir()
    (shared / "other" / ".git").write_text("gitdir: /etc\n")
    os.mkfifo(shared / "pipe")
    (shared / "link").symlink_to("/etc/passwd")

    world.once()
    record = json.loads((world.journal / "shared.jsonl").read_text().splitlines()[0])
    assert record["shared"] == "ok: 1 special file(s) skipped", record
    listing = git(
        "--git-dir",
        str(world.journal / "shared.git"),
        "ls-tree",
        "-r",
        "--name-only",
        "refs/journal/shared/20261009T120000Z",
    ).split()
    assert {"notes.txt", ".gitattributes", "lib/code.py", "link"} <= set(listing)
    assert not [
        name for name in listing if ".git/" in name or name.endswith("/.git") or name == ".git"
    ]
    assert "pipe" not in listing
    assert world.marks() == []


def test_shared_over_its_cap_is_skipped(world, monkeypatch):
    (world.volumes / "shared" / "data" / "big").write_bytes(b"x" * 4096)
    monkeypatch.setattr(journal, "JOURNAL_MAX_BYTES", 1024)
    world.fake(FAKE_TAR_FILE="/dev/null")
    world.once()
    record = json.loads((world.journal / "shared.jsonl").read_text().splitlines()[0])
    assert record["shared"].startswith("skipped:")


def test_host_git_ignores_an_exported_git_dir(world, monkeypatch, tmp_path):
    victim = tmp_path / "victim.git"
    git("init", "-q", "--bare", str(victim))
    before = sorted(str(p) for p in victim.rglob("*"))
    monkeypatch.setenv("GIT_DIR", str(victim))
    monkeypatch.setenv("GIT_ALTERNATE_OBJECT_DIRECTORIES", str(victim / "objects"))
    assert world.once()[0]["work"] == "ok"
    assert sorted(str(p) for p in victim.rglob("*")) == before


def test_the_journal_is_append_only(world):
    world.once()
    path = world.journal / "otter_one" / "journal.jsonl"
    first = path.read_text().splitlines()
    world.once(NOW + dt.timedelta(minutes=5))
    second = path.read_text().splitlines()
    assert len(second) == 2 and second[0] == first[0]


def test_the_incoming_copy_is_removed_even_when_import_fails(world, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("import blew up")

    monkeypatch.setattr(journal, "import_snapshot", explode)
    record = world.once()[0]
    assert record["work"].startswith("error"), record
    incoming = world.journal / ".incoming"
    assert not incoming.exists() or list(incoming.iterdir()) == []


def test_extracted_files_are_never_executable_or_special(world, tmp_path):
    info = journal.extract(
        journal.stream_work(["docker", "compose", "-p", "probe"], "agent_1", 1 << 30, 60),
        tmp_path / "into",
    )
    assert isinstance(info, dict)
    for path in (tmp_path / "into").rglob("*"):
        mode = path.lstat().st_mode
        assert stat.S_ISREG(mode) or stat.S_ISDIR(mode), path
