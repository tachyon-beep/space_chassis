"""Root-suite supervisor for Phase B increment R2c: the accepted full-suite supervisor (`full.py`,
master plan §25, `2557d326…`) bound to R2c's tree and the root suite only. One run per call:

  python3 root.py <grant id>

It runs `python3 -m pytest tests -q -p no:cacheprovider -n 2` from the adoption root, in a scope of
CPUQuota=200% and MemoryMax=8G, at nice 19, through the original launch path with the unchanged
launcher always restoring SIGINT to SIG_DFL (DIAG-02's arm 2: an asynchronous list in a
non-interactive sh starts its command with SIGINT ignored). The suite does not start until the
scope's limits read back exactly and the monitor has taken a healthy sample: the launcher waits for
a go-file. A ten-minute outer safety deadline runs from the go-file (P's root suite under the same
caps took 34 seconds) and changes no test timeout. The suite's result and the supervision's
result are reported separately; any abort, deadline, monitor failure, drift or unverified cleanup
is a supervisory abort, never a test result. Nothing outside the run's own scope, sh and monitor is
ever signalled.
"""

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

GRANT = sys.argv[1]
assert GRANT.startswith("SPACE-"), GRANT
ARM = "root"
HERE = Path(__file__).resolve().parent
WORKTREE = Path("/home/john/space_chassis/.claude/worktrees/vehicle-adoption")
VEHICLE = WORKTREE / "docs/deep_research/vehicle"
CANDIDATE_TREE = "148a31c4951e43c1cdafdf30c15b029dc7e104a8"  # R2c
VEHICLE_SHA = "f44399645fb2633e695a5d758cb5a41f43fb848c"
TEST_FILE = VEHICLE / "tests/test_vehicle_config.py"
TEST_SHA = "3b917de30861c432c467d92d6a75b1faf7b31cd0e62626dfde095997110c4a53"
CPU_MAX, MEMORY_MAX = "200000 100000", "8589934592"
OUTER_DEADLINE = 600
EVIDENCE = HERE / ARM
EVIDENCE.mkdir(exist_ok=False)  # session-unique, never reused: a second call refuses
RECEIPT = EVIDENCE / "receipt.jsonl"
UNIT = f"space-chassis-r2c-root-{int(time.time())}"
# systemctl resolves a bare name to `.service`: every query, stop and kill names the scope itself.
SCOPE = f"{UNIT}.scope"


def note(event: str, **fields) -> None:
    line = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **fields}
    with open(RECEIPT, "a") as out:
        out.write(json.dumps(line) + "\n")
    print(json.dumps(line), flush=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv, timeout=60, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd)


# ------------------------------------------------------------------ host readings


def cpu_times() -> tuple[int, int, int]:
    fields = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
    return sum(fields), fields[3] + fields[4], fields[4]  # total, idle+iowait, iowait


def host_sample(previous):
    now = cpu_times()
    total, idle, iowait = (now[i] - previous[i] for i in range(3))
    meminfo = dict(
        (line.split(":")[0], int(line.split()[1])) for line in Path("/proc/meminfo").read_text().splitlines()
    )
    pressure = Path("/proc/pressure/memory").read_text().splitlines()[0]
    return now, {
        "cpu_busy": round(100 * (total - idle) / total, 1) if total else None,
        "iowait": round(100 * iowait / total, 1) if total else None,
        "mem_available_mib": meminfo["MemAvailable"] // 1024,
        "load1": float(Path("/proc/loadavg").read_text().split()[0]),
        "memory_pressure": pressure,
    }


def proc_info(pid: str) -> dict:
    status = dict(
        (line.split(":", 1)[0], line.split(":", 1)[1].strip())
        for line in Path(f"/proc/{pid}/status").read_text().splitlines()
        if ":" in line
    )
    stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    return {
        "pid": int(pid),
        "comm": status.get("Name"),
        "state": status.get("State", "?").split()[0],
        "rss_kib": int(status.get("VmRSS", "0 kB").split()[0]),
        "nice": int(stat[16]),
        "SigIgn": status.get("SigIgn"),
        "sigint_ignored": bool(int(status.get("SigIgn", "0"), 16) & (1 << (signal.SIGINT - 1))),
        "cmd": cmd[:160],
    }


def daemons() -> dict:
    found = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            comm = Path(f"/proc/{pid}/comm").read_text().strip()
            if comm in ("dockerd", "containerd"):
                stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
                rss = Path(f"/proc/{pid}/statm").read_text().split()[1]
                found[comm] = {
                    "pid": int(pid),
                    "cpu_ticks": int(stat[11]) + int(stat[12]),
                    "rss_kib": int(rss) * os.sysconf("SC_PAGE_SIZE") // 1024,
                }
        except OSError:
            continue
    return found


def competitors(mine: set[int]) -> list[str]:
    """Space test/build/helper processes not this supervisor's own (by command and directory)."""
    pattern = re.compile(r"pytest|execnet|xdist|interruptible\.py|console\.py|docker build|buildx|compose (up|build)")
    found = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) in mine:
            continue
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            continue
        if "claude-" in cmd or "shell-snapshots" in cmd:
            continue  # session shells quoting these words, not drivers
        space = any(s in cmd + " " + cwd for s in ("space_chassis", "space_vehicle", "pytest-of-john"))
        if space and pattern.search(cmd):
            found.append(f"{pid}: {cmd[:120]} (cwd {cwd})")
    return found


def ancestry() -> set[int]:
    pids, pid = set(), os.getpid()
    while pid > 1:
        pids.add(pid)
        pid = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
    return pids


def identity() -> dict:
    tree = run(["git", "-C", str(WORKTREE), "write-tree"]).stdout.strip()
    run(["git", "-C", str(WORKTREE), "update-index", "-q", "--refresh"])
    unstaged = run(["git", "-C", str(WORKTREE), "diff", "--quiet"]).returncode
    porcelain = run(["git", "-C", str(WORKTREE), "status", "--porcelain", "--untracked-files=all"]).stdout
    untracked = [line for line in porcelain.splitlines() if line.startswith("??")]
    vehicle = run(["git", "-C", str(VEHICLE), "rev-parse", "HEAD"]).stdout.strip()
    vehicle_dirty = run(["git", "-C", str(VEHICLE), "status", "--porcelain"]).stdout.strip()
    result = {
        "tree": tree,
        "unstaged_clean": unstaged == 0,
        "untracked": untracked,
        "vehicle": vehicle,
        "vehicle_clean": vehicle_dirty == "",
        "test_file_sha256": sha(TEST_FILE),
    }
    result["ok"] = (
        tree == CANDIDATE_TREE
        and unstaged == 0
        and not untracked
        and vehicle == VEHICLE_SHA
        and vehicle_dirty == ""
        and result["test_file_sha256"] == TEST_SHA
    )
    return result


def unit_state() -> dict:
    try:
        shown = run(["systemctl", "--user", "show", "-p", "ActiveState,LoadState,ControlGroup", SCOPE], timeout=20)
    except (subprocess.TimeoutExpired, OSError) as error:
        return {"error": f"{type(error).__name__}: {error}"}
    if shown.returncode != 0:
        return {"error": shown.stderr.strip()}
    return dict(line.split("=", 1) for line in shown.stdout.splitlines() if "=" in line)


def live_infos(pids) -> list[dict]:
    """proc_info for each pid still there: one that exits between the listing and the read is
    skipped, never an error."""
    infos = []
    for pid in pids or []:
        try:
            infos.append(proc_info(pid))
        except (OSError, ValueError, IndexError):
            continue
    return infos


def record_failure(supervision: list, error: BaseException) -> None:
    """Best-effort reporting of a failure after the launch: it never raises, so the cleanup that
    follows it always runs. The verdict entry is kept even when the receipt cannot be written."""
    try:
        reason = f"supervisor error after the launch: {type(error).__name__}: {error}"
    except BaseException:  # noqa: BLE001 - an error whose text cannot be made is still an error
        reason = "supervisor error after the launch: (undescribable)"
    try:
        supervision.append(reason)
    except BaseException:  # noqa: BLE001, S110 - nothing here may stop the cleanup
        pass
    try:
        note("supervisor-error", error=reason)
    except BaseException:  # noqa: BLE001, S110 - the receipt is best-effort; the cleanup is not
        pass


def terminate_scope(steps: list) -> bool:
    """Stop the owned scope, then SIGKILL it, each bounded, unless its end is positively verified
    first. True only when the unit reads not-found, inactive or failed; an unanswered or failed
    lookup is never an end, so it escalates, and an end never verified returns False."""

    def ended() -> bool:
        state = unit_state()
        return state.get("LoadState") == "not-found" or state.get("ActiveState") in ("inactive", "failed")

    def wait_for_end(seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if ended():
                return True
            time.sleep(0.5)
        return ended()

    if ended():
        return True
    try:
        stopped = run(["systemctl", "--user", "stop", SCOPE], timeout=40)
        steps.append({"stop_rc": stopped.returncode, "stderr": stopped.stderr.strip()})
    except (subprocess.TimeoutExpired, OSError) as error:
        steps.append({"stop_error": f"{type(error).__name__}: {error}"})
    if wait_for_end(15):
        return True
    try:
        killed = run(["systemctl", "--user", "kill", "--signal=SIGKILL", SCOPE], timeout=20)
        steps.append({"sigkill_rc": killed.returncode})
    except (subprocess.TimeoutExpired, OSError) as error:
        steps.append({"sigkill_error": f"{type(error).__name__}: {error}"})
    return wait_for_end(15)


def cgroup_procs(cgroup: str) -> list[str] | None:
    """The scope's processes; None when unreadable (never taken as zero)."""
    try:
        return Path(f"/sys/fs/cgroup{cgroup}/cgroup.procs").read_text().split()
    except OSError:
        return None


# ------------------------------------------------------------------ the arm

supervision: list[str] = []  # every reason the supervision did not hold; empty = it held
note(
    "start",
    arm=ARM,
    grant=GRANT,
    unit=UNIT,
    selection="python3 -m pytest tests -q -p no:cacheprovider -n 2",
    supervisor_sha256=sha(Path(__file__)),
    launcher_sha256=sha(HERE / "launch.py"),
    supervisor_sigint=repr(signal.getsignal(signal.SIGINT)),
    supervisor_SigIgn=proc_info(str(os.getpid()))["SigIgn"],
)

# Admission, fresh for this arm.
before = identity()
note("identity-before", **before)
previous = cpu_times()
time.sleep(2)
previous, host = host_sample(previous)
mine = ancestry()
rivals = competitors(mine)
compose = run(["docker", "ps", "--filter", "label=com.docker.compose.project", "--format", '{{.Label "com.docker.compose.project"}}'])
projects = compose.stdout.split() if compose.returncode == 0 else None
active_units = run(["systemctl", "--user", "list-units", "--type=scope", "--state=active", "--no-legend", "space-chassis-*"]).stdout.strip()
note("admission", host=host, competitors=rivals, compose_projects=projects, compose_rc=compose.returncode, active_space_scopes=active_units)
hold = []
if not before["ok"]:
    hold.append("candidate identity is not P exactly")
if host["mem_available_mib"] < 20480:
    hold.append("MemAvailable < 20 GiB")
if host["load1"] >= 12:
    hold.append("load1 >= 12")
if host["cpu_busy"] >= 75:
    hold.append("CPU busy >= 75%")
if rivals:
    hold.append("a competing Space process")
if projects is None:
    hold.append("the Compose project listing failed")
elif projects:
    hold.append(f"Compose projects running: {projects}")
if active_units:
    hold.append("an active space-chassis scope")
if hold:
    note("HOLD", reasons=hold)
    sys.exit(90)

go, record, log = EVIDENCE / "go", EVIDENCE / "launcher.json", EVIDENCE / "pytest.log"
restore = "1"  # always: the full suite runs with SIGINT at its default
scoped = (
    f"systemd-run --user --scope --unit={UNIT} -p CPUQuota=200% -p MemoryMax=8G "
    f"python3 {HERE / 'launch.py'} {restore} {go} {record} "
    "nice -n 19 python3 -m pytest tests -q -p no:cacheprovider -n 2"
)
# The original driver's path: an asynchronous list in a non-interactive sh, then `wait` for it.
shell = f"{scoped} > {log} 2>&1 &\nwait $!"
# Defined before anything that can fail, so cleanup can always run against them.
driver = None
cgroup = None
released = None
watcher = None
stop = threading.Event()
heartbeat = [0.0]
abort: list[str] = []
started = time.monotonic()
try:
    note("launch", sh=shell)
    driver = subprocess.Popen(["sh", "-c", shell], cwd=WORKTREE, start_new_session=False)

    # The scope, its exact limits, and the launcher's record, before anything runs.
    cgroup = None
    while time.monotonic() - started < 20:
        state = unit_state()
        if state.get("ActiveState") == "active" and state.get("ControlGroup") and record.exists():
            cgroup = state["ControlGroup"]
            break
        time.sleep(0.2)
    limits = {}
    if cgroup:
        try:
            limits = {
                "cpu.max": Path(f"/sys/fs/cgroup{cgroup}/cpu.max").read_text().strip(),
                "memory.max": Path(f"/sys/fs/cgroup{cgroup}/memory.max").read_text().strip(),
                "memory.events": Path(f"/sys/fs/cgroup{cgroup}/memory.events").read_text().split(),
            }
        except OSError as error:
            limits = {"error": str(error)}
    launcher = json.loads(record.read_text()) if record.exists() else None
    note("scope", cgroup=cgroup, limits=limits, launcher=launcher)
    if not cgroup:
        supervision.append("the scope did not become active with its launcher record")
    elif limits.get("cpu.max") != CPU_MAX or limits.get("memory.max") != MEMORY_MAX:
        supervision.append(f"the scope's limits are not {CPU_MAX} / {MEMORY_MAX}")

    # The monitor: one sample every five seconds; a failed read of a live scope is a failure.
    oom_before = None


    def monitor() -> None:
        global oom_before
        prev = cpu_times()
        strikes = 0
        ticks = os.sysconf("SC_CLK_TCK")
        last_daemons = daemons()
        try:
            while not stop.is_set():
                time.sleep(5 if heartbeat[0] else 0.5)
                prev_, host = host_sample(prev)
                prev = prev_
                procs = cgroup_procs(cgroup)
                state = unit_state()
                if "error" in state:
                    raise RuntimeError(f"the scope's state cannot be read: {state['error']}")
                active = state.get("ActiveState") == "active"
                if procs is None and active and unit_state().get("ActiveState") == "active":
                    raise RuntimeError("the live scope's cgroup.procs is unreadable")
                events = {}
                try:
                    raw = Path(f"/sys/fs/cgroup{cgroup}/memory.events").read_text().split()
                    events = dict(zip(raw[::2], map(int, raw[1::2])))
                    current = int(Path(f"/sys/fs/cgroup{cgroup}/memory.current").read_text())
                except OSError:
                    if active and unit_state().get("ActiveState") == "active":
                        raise
                    active, current = False, None
                if oom_before is None:
                    oom_before = events.get("oom_kill", 0)
                infos = live_infos(procs)
                now_daemons = daemons()
                daemon_cpu = {
                    name: {
                        "cpu_pct_of_one": round(
                            100 * (d["cpu_ticks"] - last_daemons.get(name, d)["cpu_ticks"]) / ticks / 5, 1
                        ),
                        "rss_kib": d["rss_kib"],
                    }
                    for name, d in now_daemons.items()
                }
                last_daemons = now_daemons
                sample = {
                    "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    **host,
                    "scope_active": active,
                    "scope_memory_current": current,
                    "scope_memory_events": events,
                    "scope_procs": infos,
                    "driver_sh": {"pid": driver.pid, "returncode": driver.poll()},
                    "daemons": daemon_cpu,
                }
                with open(EVIDENCE / "monitor.jsonl", "a") as out:
                    out.write(json.dumps(sample) + "\n")
                heartbeat[0] = time.monotonic()
                if host["mem_available_mib"] < 12288:
                    abort.append(f"MemAvailable {host['mem_available_mib']} MiB < 12 GiB")
                strikes = strikes + 1 if (host["cpu_busy"] > 85 or host["load1"] > 20) else 0
                if strikes >= 3:
                    abort.append("CPU busy > 85% or load1 > 20 for three samples")
                if events.get("oom_kill", 0) > oom_before or events.get("oom", 0) > 0:
                    abort.append(f"an OOM in the owned scope: {events}")
                if not active:
                    return
        except Exception as error:  # noqa: BLE001 - a monitor that cannot see is a monitor failure
            abort.append(f"monitor failure: {type(error).__name__}: {error}")


    watcher = threading.Thread(target=monitor, daemon=True)
    if not supervision:
        watcher.start()
        while not heartbeat[0] and watcher.is_alive() and time.monotonic() - started < 40:
            time.sleep(0.2)
        if not heartbeat[0]:
            supervision.append("the monitor took no first sample")
        else:
            first = json.loads((EVIDENCE / "monitor.jsonl").read_text().splitlines()[0])
            note("monitor-first-sample", sample=first)
            if abort:
                supervision.append(f"the first sample is not healthy: {abort}")
            if not first.get("scope_active"):
                supervision.append("the first sample does not see the scope active")
            if not watcher.is_alive():
                supervision.append("the monitor ended before the test was released")

    # Release the test only now.
    released = None
    if not supervision:
        go.write_text("go\n")
        released = time.monotonic()
        note("released", outer_deadline_s=OUTER_DEADLINE)
        niced = False
        while driver.poll() is None:
            elapsed = time.monotonic() - released
            if not niced and elapsed > 8:
                procs = live_infos(cgroup_procs(cgroup))
                pytest_procs = [p for p in procs if "pytest" in p["cmd"] or "execnet" in p["cmd"]]
                note("nice-check", procs=procs)
                if not pytest_procs or any(p["nice"] != 19 for p in procs):
                    supervision.append("the scope's processes are not all at nice 19")
                niced = True
            if abort:
                supervision.extend(abort)
            if not watcher.is_alive() and driver.poll() is None:
                try:  # the scope ended and the monitor with it: the sh's `wait` returns a moment later
                    driver.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    supervision.append(abort[-1] if abort else "the monitor stopped while the test ran")
            if heartbeat[0] and time.monotonic() - heartbeat[0] > 20 and driver.poll() is None:
                supervision.append("the monitor's heartbeat is stale")
            if elapsed > OUTER_DEADLINE:
                supervision.append("the ten-minute outer deadline passed")
            if supervision:
                break
            time.sleep(1)

except BaseException as error:  # noqa: BLE001 - any failure after the launch still cleans up
    record_failure(supervision, error)

# Cleanup: bounded, and verified from the unit and its cgroup, never assumed.
cleanup = {"steps": []}
if cgroup is None:
    # The scope never came up: release nothing, but find it if it exists.
    cgroup = unit_state().get("ControlGroup") or None
cleanup["scope_terminated"] = terminate_scope(cleanup["steps"])
driver_rc = None
if driver is not None:
    try:
        driver_rc = driver.wait(timeout=30)
    except subprocess.TimeoutExpired:
        driver.kill()
        driver_rc = driver.wait(timeout=10)
        cleanup["steps"].append("the sh driver was killed after the scope ended")
stop.set()
if watcher is not None and watcher.ident:
    watcher.join(timeout=15)
# A monitor failure that arrived as the test ended, or during the join, is part of the verdict.
supervision.extend(abort)
final = unit_state()
procs_after = cgroup_procs(cgroup) if cgroup else None
cgroup_gone = bool(cgroup) and not Path(f"/sys/fs/cgroup{cgroup}").exists()
helpers = [
    line
    for line in run(["pgrep", "-af", "interruptible.py|xdist|execnet"]).stdout.splitlines()
    if "pytest-of-john" in line or "space_chassis" in line
]
cleanup.update(
    {
        "unit": final,
        "cgroup_removed": cgroup_gone,
        "cgroup_procs_after": procs_after,
        "monitor_thread_alive": watcher is not None and watcher.is_alive(),
        "driver_sh_rc": driver_rc,
        "remaining_helpers": helpers,
    }
)
ended = final.get("LoadState") == "not-found" or final.get("ActiveState") in ("inactive", "failed")
cleanup["verified"] = (
    cleanup["scope_terminated"]
    and ended
    and (cgroup_gone or procs_after == [] or (cgroup is None and final.get("LoadState") == "not-found"))
    and not (watcher is not None and watcher.is_alive())
    and not helpers
)
note("cleanup", **cleanup)
if not cleanup["verified"]:
    supervision.append("cleanup is not verified")

after = identity()
note("identity-after", **after)
if not after["ok"]:
    supervision.append("the candidate drifted")

text = log.read_text(errors="replace") if log.exists() else ""
progress = "".join(re.sub(r"\s*\[\s*\d+%\]$", "", line) for line in text.splitlines() if re.fullmatch(r"[.FEsxX]+\s+\[\s*\d+%\]", line))
test = {
    "pytest_rc": driver_rc if released else None,
    "ran": released is not None,
    "outcomes": {c: progress.count(c) for c in set(progress)},
    "failed": re.findall(r"^FAILED (\S+)", text, re.MULTILINE),
    "errors": re.findall(r"^ERROR (\S+)", text, re.MULTILINE),
    "pytest_log_sha256": sha(log) if log.exists() else None,
}
supervision = list(dict.fromkeys(supervision))
note("result", test=test, supervision="held" if not supervision else "ABORTED", reasons=supervision)
sys.exit(0 if not supervision else 2)
