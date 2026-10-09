import hashlib
import json
import signal
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import threading
import time

from command_runtime import run_command

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHDOG_FILE = os.path.join(WORK_DIR, "watchdog.py")
AGENT_FILE = os.path.join(WORK_DIR, "agent.py")

BASELINE_REF = "refs/tags/baseline"
RESCUE_REF = "refs/tags/rescue"
EXPERIMENTAL_REF = "refs/tags/experimental"
GIT_TIMEOUT_SECONDS = 10
RECOVERY_PROBATION_SECONDS = 60
DISPLAY_REFERENCE = "baseline_reference.txt"
INACTIVITY_TIMEOUT_SECONDS = 24 * 60 * 60
FAILURE_WINDOW_SECONDS = 600
TIER2_FAILURES = 2
TIER3_FAILURES = 3

EXIT_DONE = 42
EXIT_TERMINATED = 43
EXIT_ENVIRONMENT = 44
EXIT_RESET = 45
ZERO_EXIT_FLAP_COUNT = 3
ZERO_EXIT_FLAP_WINDOW_SECONDS = 120
TERMINATED_FLAP_COUNT = 3
TERMINATED_FLAP_WINDOW_SECONDS = 600
ENVIRONMENT_PAUSE_SECONDS = 60
ENVIRONMENT_PAUSE_JITTER_SECONDS = 30

TELEMETRY_DIR = os.environ.get("TELEMETRY_DIR", "/telemetry")
TELEMETRY_KEEP = ("work", "work.tmp", "work.old")
BUILD_DIR = os.environ.get("BUILD_DIR", "/build")
MIRROR_INTERVAL_SECONDS = 5
MIRROR_EXCLUDE = ("__pycache__", ".git")

AGENT_LOG_NAME = "agent_stdout.log"
AGENT_LOG_MAX_BYTES = 2_000_000

# Archived conversations, bounded like the log above. Every fresh restore copies the conversation
# into tombstones/ and the git directory, and the chassis writes one more on exit 43; /work is a
# 1 GiB tmpfs that counts against the container's memory, and a full /work makes a restore fail
# and the ladder end in a reseed, which loses this repository's tags as well. The newest
# ARCHIVE_KEEP bodies per directory are kept within the byte budget. Only the names the harness
# itself gives its archives are pruned (the chassis stamps %Y%m%d_%H%M%S_%f, this file time_ns());
# notes, incarnation messages and any other file are never touched. The figures are yours to change.
ARCHIVE_KEEP = 20
ARCHIVE_TOMBSTONE_BYTES = 128 * 1024 * 1024
ARCHIVE_GIT_BYTES = 64 * 1024 * 1024
TOMBSTONE_ARCHIVES = (
    re.compile(r"session_\d{8}_\d{6}_\d{6}\.json"),
    re.compile(r"corrupt_session_\d{8}_\d{6}_\d{6}\.json"),
    re.compile(r"session_recovery_\d+\.json"),
)
GIT_ARCHIVES = (re.compile(r"session_recovery_\d+\.json"),)

# The liveness signal. The transcript is written by the recorder onto the
# transcripts volume, which this container does not mount, so its size here is
# always zero; the captured agent log is written by this process inside the
# working tree and grows with every line the agent prints.
ACTIVITY_FILE = os.path.join(WORK_DIR, AGENT_LOG_NAME)


def environment_pause_seconds(random_fraction):
    """The exit-44 pause: a fixed wait plus a share of the jitter, so agents sharing an upstream do not retry together."""
    return ENVIRONMENT_PAUSE_SECONDS + random_fraction * ENVIRONMENT_PAUSE_JITTER_SECONDS


def activity_size(path=None):
    """The size of the liveness signal file, or 0 when it does not exist."""
    if path is None:
        path = ACTIVITY_FILE
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def decide_tier(
    failure_times,
    now,
    window=FAILURE_WINDOW_SECONDS,
    tier2=TIER2_FAILURES,
    tier3=TIER3_FAILURES,
):
    """Map recent failures to a recovery tier (1, 2, or 3)."""
    recent = [t for t in failure_times if now - t <= window]
    n = len(recent)
    if n >= tier3:
        return 3
    if n >= tier2:
        return 2
    return 1


def is_flapping(
    times,
    now,
    count=ZERO_EXIT_FLAP_COUNT,
    window=ZERO_EXIT_FLAP_WINDOW_SECONDS,
):
    """True when enough timestamps cluster within the window to count as a failure.

    Used for both exit-0 timestamps and harness-termination (exit 43)
    timestamps; the caller supplies the relevant history and thresholds.
    """
    recent = [t for t in times if now - t <= window]
    return len(recent) >= count


def plan_recovery(ret, zero_exit_times, terminated_exit_times, failure_times, now):
    """Map an agent exit code to a recovery action and updated exit history.

    Returns (action, zero_exit_times, terminated_exit_times, failure_times).
    A completed incarnation (42) clears all histories. A harness termination
    (43) archives and records the timestamp; when terminations cluster
    within TERMINATED_FLAP_WINDOW_SECONDS the terminated history is cleared
    and the fault is escalated through the tier ladder instead, so an
    environment that kills every incarnation cannot loop forever. An
    environment failure (44) pauses. An isolated exit 0 restarts; flapping
    exit-0s and crashes escalate through tier1/tier2/tier3.
    """
    if ret == EXIT_RESET:
        return "checkpoint_reset", zero_exit_times, terminated_exit_times, failure_times
    if ret == EXIT_DONE:
        return "archive_reset", [], [], []
    if ret == EXIT_TERMINATED:
        terminated_exit_times = terminated_exit_times + [now]
        if not is_flapping(
            terminated_exit_times,
            now,
            count=TERMINATED_FLAP_COUNT,
            window=TERMINATED_FLAP_WINDOW_SECONDS,
        ):
            return "recover_new", zero_exit_times, terminated_exit_times, failure_times
        terminated_exit_times = []
        failure_times = failure_times + [now]
        tier = decide_tier(failure_times, now)
        return f"tier{tier}", zero_exit_times, terminated_exit_times, failure_times
    if ret == EXIT_ENVIRONMENT:
        return "pause", zero_exit_times, terminated_exit_times, failure_times
    if ret == 0:
        zero_exit_times = zero_exit_times + [now]
        if not is_flapping(zero_exit_times, now):
            return "restart", zero_exit_times, terminated_exit_times, failure_times
        zero_exit_times = []
    failure_times = failure_times + [now]
    tier = decide_tier(failure_times, now)
    return f"tier{tier}", zero_exit_times, terminated_exit_times, failure_times


def _restore_owner_access(path):
    """Add owner read/write/execute to a directory. Symbolic links are skipped."""
    if os.path.islink(path):
        return
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return
    if not stat.S_ISDIR(mode):
        return
    try:
        os.chmod(path, mode | stat.S_IRWXU)
    except OSError:
        pass


def _force_rmtree(path):
    """Remove a directory tree, restoring owner access where a mode denies it.

    A directory whose mode withholds execute cannot be traversed and one that
    withholds write cannot be emptied, so a plain removal stops there. The
    first pass removes what it can; when anything is left, owner access is
    restored over the remainder top-down and the removal is repeated. A
    symbolic link root is removed as a link and never walked, and links
    inside the tree are removed as links, so no mode outside the tree is
    ever changed and a planted link cannot wedge later replacements.
    Returns True when the tree is gone.
    """
    if os.path.islink(path):
        try:
            os.unlink(path)
        except OSError:
            pass
        return not os.path.lexists(path)
    shutil.rmtree(path, ignore_errors=True)
    if not os.path.lexists(path):
        return True
    _restore_owner_access(path)
    for parent, dirs, _files in os.walk(path):
        for name in dirs:
            _restore_owner_access(os.path.join(parent, name))
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.lexists(path)


def clear_build_dir(build_dir=BUILD_DIR):
    """Remove the contents of the build directory, keeping the directory.

    Called at the archive-and-reset boundary alongside git_reset_all. Does nothing when the directory does not exist. Directory
    modes that deny removal are restored first. Symbolic links are removed as
    links and never followed.
    """
    if not os.path.isdir(build_dir):
        return
    for name in os.listdir(build_dir):
        path = os.path.join(build_dir, name)
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                _force_rmtree(path)
            else:
                os.remove(path)
        except OSError:
            pass


def discard_session(work_dir=WORK_DIR):
    """Remove a saved session file so a faulty session is not resumed."""
    try:
        os.remove(os.path.join(work_dir, "session_context.json"))
    except OSError:
        pass


def _mirror_ignore(directory, names):
    """Return the names copytree skips: MIRROR_EXCLUDE entries and special files.

    Only regular files, directories and symbolic links are mirrored; sockets,
    FIFOs and device nodes are left out. Entries are inspected with lstat, so
    nothing is followed.
    """
    skipped = set(shutil.ignore_patterns(*MIRROR_EXCLUDE)(directory, names))
    for name in names:
        if name in skipped:
            continue
        try:
            mode = os.lstat(os.path.join(directory, name)).st_mode
        except OSError:
            continue
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
            skipped.add(name)
    return skipped


def mirror_work(src=None, dest_root=None):
    """Copy the working tree into the telemetry mirror, replacing the prior copy.

    Symbolic links are copied as links and never followed. Does nothing when
    the destination root does not exist. Excludes MIRROR_EXCLUDE entries.
    Copied directory modes are reproduced, so the replaced copies are removed
    through _force_rmtree; a mode that denies removal would otherwise leave
    the previous copy in place and stop every later replacement. Each pass
    also removes destination-root entries outside TELEMETRY_KEEP, so the
    volume holds only what this file writes.
    """
    if src is None:
        src = WORK_DIR
    if dest_root is None:
        dest_root = TELEMETRY_DIR
    if not os.path.isdir(dest_root):
        return
    for name in os.listdir(dest_root):
        if name in TELEMETRY_KEEP:
            continue
        stray = os.path.join(dest_root, name)
        if os.path.isdir(stray) and not os.path.islink(stray):
            _force_rmtree(stray)
        else:
            try:
                os.unlink(stray)
            except OSError:
                pass
    dest = os.path.join(dest_root, "work")
    tmp = os.path.join(dest_root, "work.tmp")
    old = os.path.join(dest_root, "work.old")
    _force_rmtree(tmp)
    try:
        shutil.copytree(src, tmp, symlinks=True, ignore=_mirror_ignore)
    except OSError as exc:
        print(f"telemetry mirror: copy failed: {exc}", file=sys.stderr, flush=True)
        _force_rmtree(tmp)
        return
    export_display_reference(src, tmp)
    _force_rmtree(old)
    try:
        if os.path.isdir(dest):
            os.rename(dest, old)
        os.rename(tmp, dest)
    except OSError:
        _force_rmtree(tmp)
        return
    _force_rmtree(old)


def export_display_reference(work_dir, mirror_dir):
    """Export bounded baseline source as nonexecutable display data, never as a backstop."""
    path = os.path.join(mirror_dir, DISPLAY_REFERENCE)
    try:
        if os.path.lexists(path):
            if os.path.isdir(path) and not os.path.islink(path):
                _force_rmtree(path)
            else:
                os.unlink(path)
        commit = resolve_checkpoint(work_dir, BASELINE_REF)
        blob = f"{commit}:agent.py"
        size = int(git_command(work_dir, "cat-file", "-s", blob))
        if size > 1_000_000:
            return
        source = git_command(work_dir, "show", blob)
        with open(path, "xb") as f:
            f.write(source)
    except (RestoreError, OSError, ValueError):
        pass


def _tee_stream(stream, log_path, max_bytes=AGENT_LOG_MAX_BYTES):
    """Copy a binary stream to stdout and append it to a size-capped log file."""
    for line in iter(stream.readline, b""):
        sys.stdout.write(line.decode("utf-8", errors="replace"))
        sys.stdout.flush()
        try:
            if os.path.exists(log_path) and os.path.getsize(log_path) > max_bytes:
                with open(log_path, "rb") as f:
                    kept = f.read()[-max_bytes // 2 :]
                with open(log_path, "wb") as f:
                    f.write(kept)
            with open(log_path, "ab") as f:
                f.write(line)
        except OSError:
            pass
    stream.close()


class RestoreError(RuntimeError):
    pass


def git_command(work_dir, *args):
    """Run bounded Git plumbing; unsuccessful commands never count as a restore."""
    try:
        result = run_command(
            ["git", "-C", work_dir, *args],
            timeout=GIT_TIMEOUT_SECONDS,
            output_limit=1_000_000,
            decode_output=False,
        )
    except OSError as exc:
        raise RestoreError(f"git {args[0]} failed: {exc}") from exc
    if result["status"] == "timeout" or result["returncode"]:
        detail = result["stderr"][-4096:].decode("utf-8", errors="replace")
        raise RestoreError(
            f"git {args[0]} {result['status']} exit {result['returncode']}: {detail}"
        )
    return result["stdout"]


def resolve_checkpoint(work_dir, ref):
    """Resolve an exact tag to a commit and require the agent entry point."""
    commit = git_command(work_dir, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    git_command(work_dir, "cat-file", "-e", f"{commit}:agent.py")
    return commit


def restore_agent_only(work_dir=WORK_DIR):
    """Checked single-file restore retained for callers; runtime restores full checkpoints."""
    commit = resolve_checkpoint(work_dir, BASELINE_REF)
    git_command(work_dir, "checkout", commit, "--", "agent.py")
    return commit


def git_reset_all(work_dir=WORK_DIR, ref=BASELINE_REF):
    """Restore a complete commit, preserving ignored files and explicit session/evidence paths."""
    commit = resolve_checkpoint(work_dir, ref)
    git_command(work_dir, "reset", "--hard", "--quiet", commit)
    git_command(work_dir, "clean", "-fdq", "-e", "tombstones/", "-e", "session_context.json")
    return commit


def _prune_directory(directory, patterns, budget, keep_newest):
    """Remove the archives past the newest ARCHIVE_KEEP within budget; return how many went."""
    try:
        if not stat.S_ISDIR(os.lstat(directory).st_mode):
            return 0
        names = os.listdir(directory)
    except OSError:
        return 0
    found = []
    for name in names:
        if not any(pattern.fullmatch(name) for pattern in patterns):
            continue
        try:
            st = os.lstat(os.path.join(directory, name))
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode):
            found.append((name == keep_newest, st.st_mtime_ns, name, st.st_size))
    found.sort(reverse=True)
    kept = used = removed = 0
    for index, (_newest, _mtime, name, size) in enumerate(found):
        if index == 0 or (kept < ARCHIVE_KEEP and used + size <= budget):
            kept += 1
            used += size
            continue
        # The first archive over the count or the budget, and everything older, goes.
        for _n, _m, old_name, _s in found[index:]:
            try:
                os.remove(os.path.join(directory, old_name))
                removed += 1
            except OSError as exc:
                print(f"archive prune failed for {old_name}: {exc}", flush=True)
        break
    return removed


def prune_archives(work_dir=WORK_DIR, keep_newest=None):
    """Bound the archived conversations in tombstones/ and the git directory; never raise.

    keep_newest names the archive just made, kept whatever its modification time says.
    """
    removed = 0
    try:
        removed += _prune_directory(
            os.path.join(work_dir, "tombstones"),
            TOMBSTONE_ARCHIVES,
            ARCHIVE_TOMBSTONE_BYTES,
            keep_newest,
        )
        try:
            git_dir = git_command(work_dir, "rev-parse", "--absolute-git-dir").decode().strip()
        except Exception as exc:
            print(f"archive prune skipped the git directory: {exc}", flush=True)
        else:
            removed += _prune_directory(git_dir, GIT_ARCHIVES, ARCHIVE_GIT_BYTES, keep_newest)
    except Exception as exc:
        print(f"archive prune failed: {exc}", flush=True)
    if removed:
        print(f"pruned {removed} archive(s)", flush=True)
    return removed


class Recovery:
    """Persist the finite code recovery ladder separately from elective checkpoint selection."""

    def __init__(self, work_dir=WORK_DIR):
        self.work_dir = work_dir
        git_dir = git_command(work_dir, "rev-parse", "--absolute-git-dir").decode().strip()
        self.path = os.path.join(git_dir, "aurora-recovery.json")
        self.progress_path = os.path.join(git_dir, "aurora-progress.json")
        self.state = {"phase": None, "selected": None, "failed": {}, "note": ""}
        self.seeded = False
        try:
            with open(self.path, encoding="utf-8") as f:
                saved = json.load(f)
            if not isinstance(saved, dict) or not isinstance(saved.get("failed"), dict):
                raise ValueError("invalid recovery state")
            self.state.update(saved)
        except FileNotFoundError:
            self.seeded = True
        except (OSError, ValueError) as exc:
            raise RestoreError(f"cannot read recovery state: {exc}") from exc
        self.started = time.monotonic()

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f)
        os.replace(tmp, self.path)

    def note(self, reason, ref, commit, fresh):
        note = (
            f"Recovery event {time.time_ns()}: {reason}. Restored {ref} at {commit}; "
            f"{'fresh' if fresh else 'preserved'} incarnation."
        )
        self._publish(note)

    def note_seed_boot(self):
        """Note a start from the image seed, once: nothing was restored, so note() does not fit."""
        if not self.seeded:
            return False
        commit = git_command(self.work_dir, "rev-parse", "--verify", "HEAD").decode().strip()
        self._publish(
            f"Recovery event {time.time_ns()}: started from the image seed at {commit}; "
            "fresh incarnation."
        )
        self.seeded = False
        return True

    def _publish(self, note):
        self.state["note"] = note
        self.save()
        print(note, flush=True)
        tombstones = os.path.join(self.work_dir, "tombstones")
        try:
            os.makedirs(tombstones, exist_ok=True)
            with open(os.path.join(tombstones, "recovery_note.txt"), "w", encoding="utf-8") as f:
                f.write(note + "\n")
        except OSError as exc:
            print(f"recovery evidence write failed: {exc}", flush=True)

    def fresh_session(self):
        session = os.path.join(self.work_dir, "session_context.json")
        if os.path.exists(session):
            tombstones = os.path.join(self.work_dir, "tombstones")
            os.makedirs(tombstones, exist_ok=True)
            archive_name = f"session_recovery_{time.time_ns()}.json"
            shutil.copyfile(session, os.path.join(os.path.dirname(self.path), archive_name))
            os.replace(session, os.path.join(tombstones, archive_name))
            return archive_name
        return None

    def evidence(self, reason):
        try:
            with open(os.path.join(self.work_dir, AGENT_LOG_NAME), "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - 8192))
                tail = f.read(8192).decode("utf-8", errors="replace")
        except OSError:
            tail = "(no agent log)"
        self.state["evidence"] = {"reason": reason, "log_tail": tail}
        self.save()

    def eligible(self, ref):
        commit = resolve_checkpoint(self.work_dir, ref)
        if self.state["failed"].get(ref) == commit:
            raise RestoreError(f"{ref} at {commit} already failed")
        return commit

    def restore(self, ref, commit, phase, reason, fresh):
        if not fresh:
            try:
                with open(
                    os.path.join(self.work_dir, "session_context.json"), encoding="utf-8"
                ) as f:
                    session = json.load(f)
                if not isinstance(session, list) or not all(
                    isinstance(m, dict) and m.get("role") in ("system", "user", "assistant", "tool")
                    for m in session
                ):
                    raise ValueError("invalid conversation")
            except (OSError, ValueError):
                fresh = True
                reason += "; saved conversation unavailable"
        if fresh:
            # Pruned whenever the conversation starts fresh, including after exit 43, whose
            # archive the chassis has already written: once first, to make room for the copy,
            # and again after it, keeping the archive just made whatever its clock says.
            prune_archives(self.work_dir)
            prune_archives(self.work_dir, keep_newest=self.fresh_session())
        session_path = os.path.join(self.work_dir, "session_context.json")
        pending_session = self.path + ".session"
        if not fresh:
            shutil.copyfile(session_path, pending_session)
        try:
            git_reset_all(self.work_dir, commit)
            if fresh:
                discard_session(self.work_dir)
        finally:
            if not fresh and os.path.exists(pending_session):
                os.replace(pending_session, session_path)
        self.state.update(phase=phase, selected={"ref": ref, "commit": commit})
        self.started = time.monotonic()
        self.note(reason, ref, commit, fresh)
        return commit

    def failure(self, reason, fresh_only=False):
        """Baseline/same → baseline/new → rescue/new → image, without decaying retries."""
        self.evidence(reason)
        phase = self.state["phase"]
        selected = self.state["selected"]
        if selected and (
            phase in ("baseline_new", "rescue_new")
            or (phase == "elective" and selected["ref"] == EXPERIMENTAL_REF)
        ):
            self.state["failed"][selected["ref"]] = selected["commit"]
            self.save()
        steps = [
            (BASELINE_REF, "baseline_same", False),
            (BASELINE_REF, "baseline_new", True),
            (RESCUE_REF, "rescue_new", True),
        ]
        start = {"baseline_same": 1, "baseline_new": 2, "rescue_new": 3}.get(phase, 0)
        if phase is None and fresh_only:
            start = 1
        for ref, target_phase, fresh in steps[start:]:
            try:
                commit = self.eligible(ref)
                return self.restore(ref, commit, target_phase, reason, fresh)
            except (RestoreError, OSError) as exc:
                reason += f"; {target_phase}: {exc}"
                self.evidence(reason)
        raise RestoreError(f"recovery exhausted; existing image backstop required: {reason}")

    def elective(self, reason, fresh):
        """Optional experimental → eligible baseline → rescue at intentional full reset boundaries."""
        for ref in (EXPERIMENTAL_REF, BASELINE_REF, RESCUE_REF):
            try:
                commit = self.eligible(ref)
                phase = "elective"
                return self.restore(ref, commit, phase, reason, fresh)
            except (RestoreError, OSError) as exc:
                if ref != EXPERIMENTAL_REF:
                    reason += f"; {exc}"
        raise RestoreError(f"no eligible reset checkpoint: {reason}")

    def observe_progress(self, pid):
        """Require completed chassis work and a stable probation before ending the incident."""
        if self.state["phase"] is None:
            return
        try:
            with open(self.progress_path, encoding="utf-8") as f:
                progress = json.load(f)
            if (
                progress["pid"] != pid
                or progress["completed_at"] < self.started
                or time.monotonic() - self.started < RECOVERY_PROBATION_SECONDS
            ):
                return
        except (OSError, ValueError, KeyError):
            return
        self.state["phase"] = None
        self.save()


def file_hash(path):
    """Content hash of a file, or '' if it cannot be read."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""


def sanitize_stdin(agent_path):
    """Replace any stdin reads with a harmless 'Beep' return."""
    if not os.path.exists(agent_path):
        return
    try:
        with open(agent_path, "r", encoding="utf-8") as f:
            content = f.read()

        patterns = [
            r"input\s*\(",
            r"sys\.stdin\.read",
            r"sys\.stdin\.readline",
            r'open\s*\(\s*"/dev/stdin"',
        ]
        detected = False
        for pat in patterns:
            if re.search(pat, content):
                if "_safe_input" not in content:
                    detected = True
                    break

        if detected:
            safe_function = '''
import builtins
import io
_original_input = builtins.input
def _safe_input(prompt=""):
    """Always returns 'Beep' without waiting for real input."""
    return "Beep"
builtins.input = _safe_input
sys.stdin = io.StringIO("Beep\\n")
'''
            content, applied = re.subn(
                r"(import sys\r?\n)", r"\1" + safe_function + "\n", content, count=1
            )
            if applied:
                with open(agent_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print("Detected stdin access attempt. Patched input() to always return Beep.")
            else:
                print("Detected stdin access attempt; no import sys line to patch.")
    except Exception as e:
        print(f"Error sanitizing stdin: {e}")


def spawn_agent():
    sanitize_stdin(AGENT_FILE)
    proc = subprocess.Popen(
        [sys.executable, AGENT_FILE],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log_path = os.path.join(WORK_DIR, AGENT_LOG_NAME)
    threading.Thread(target=_tee_stream, args=(proc.stdout, log_path), daemon=True).start()
    return proc


def terminate_process(proc):
    """Stop the supervised process group before restoring code."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            break
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            continue
        if sig == signal.SIGTERM:
            continue


def reap_children(agent):
    """Reap exited children so orphaned grandchildren do not become zombies.

    This watchdog is PID 1 (container init). A plain Python init does not reap
    reparented orphans; they stay zombies and eventually exhaust the cgroup pid
    limit. waitpid(-1, WNOHANG) reaps any exited child. If it reaps the managed
    agent, translate the wait status into Popen.returncode so a later
    agent.poll() still reports the exit (otherwise poll() would hit ECHILD and
    wrongly treat the agent as still running).

    The agent is not the only child here. entrypoint.sh starts the scheduler at
    /usr/local/bin/pump.py in a background loop before exec'ing this file, so
    that loop is also a child of PID 1, and processes the scheduler starts
    reparent here when their own parent exits. Both arrive through this
    waitpid, which is why the reaped pid is compared against the agent's rather
    than assumed to be it.
    """
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except OSError:
            return
        if pid == 0:
            return
        if agent is not None and pid == agent.pid and agent.returncode is None:
            if os.WIFSIGNALED(status):
                agent.returncode = -os.WTERMSIG(status)
            elif os.WIFEXITED(status):
                agent.returncode = os.WEXITSTATUS(status)
            else:
                agent.returncode = status


def apply_recovery(action, ret, own_hash, recovery=None):
    """Apply a checked reset or advance the persistent recovery ladder."""
    if action == "pause":
        time.sleep(environment_pause_seconds(random.random()))
        return own_hash
    if action == "restart":
        return own_hash
    if recovery is None:
        recovery = Recovery()
    if action in ("archive_reset", "checkpoint_reset"):
        recovery.elective(f"intentional exit {ret}", fresh=action == "archive_reset")
        if action == "archive_reset":
            clear_build_dir()
            time.sleep(60 if ret == EXIT_DONE else 10)
    else:
        recovery.failure(f"BROKEN-CODE/MIGRATION exit {ret}", fresh_only=action == "recover_new")
    return file_hash(WATCHDOG_FILE)


def run_watchdog():
    """Supervise code recovery and preserve the finite ladder across self-reexec."""
    recovery = Recovery()
    recovery.note_seed_boot()
    prune_archives()
    own_hash = file_hash(WATCHDOG_FILE)
    failures = []
    zero_exits = []
    terminated_exits = []
    agent = spawn_agent()
    mirror_work()
    last_mirror = time.time()
    last_size = activity_size()
    last_activity = time.time()

    while True:
        time.sleep(2)
        if time.time() - last_mirror >= MIRROR_INTERVAL_SECONDS:
            mirror_work()
            last_mirror = time.time()

        current_hash = file_hash(WATCHDOG_FILE)
        if current_hash != own_hash:
            time.sleep(0.2)
            if file_hash(WATCHDOG_FILE) == current_hash:
                print("watchdog file changed; terminating agent and re-executing self")
                terminate_process(agent)
                sys.stdout.flush()
                os.execv(sys.executable, [sys.executable, WATCHDOG_FILE])

        reap_children(agent)
        ret = agent.poll()
        if ret is not None:
            now = time.time()
            action, zero_exits, terminated_exits, failures = plan_recovery(
                ret, zero_exits, terminated_exits, failures, now
            )
            print(f"agent exited ({ret}); action {action}")
            terminate_process(agent)
            own_hash = apply_recovery(action, ret, own_hash, recovery)
            agent = spawn_agent()
            last_size = activity_size()
            last_activity = time.time()
            continue

        recovery.observe_progress(agent.pid)
        size = activity_size()
        if size != last_size:
            last_size = size
            last_activity = time.time()
        elif time.time() - last_activity > INACTIVITY_TIMEOUT_SECONDS:
            print("inactivity timeout; treating as failure")
            terminate_process(agent)
            ret = agent.poll()
            ret = -1 if ret is None else ret
            now = time.time()
            action, zero_exits, terminated_exits, failures = plan_recovery(
                ret, zero_exits, terminated_exits, failures, now
            )
            print(f"agent stopped after inactivity ({ret}); action {action}")
            terminate_process(agent)
            own_hash = apply_recovery(action, ret, own_hash, recovery)
            agent = spawn_agent()
            last_size = activity_size()
            last_activity = time.time()


if __name__ == "__main__":
    try:
        run_watchdog()
    except RestoreError as exc:
        print(str(exc), flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        print("watchdog terminated by user")
