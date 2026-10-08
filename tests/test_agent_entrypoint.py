"""The agent container's entrypoint, run for real against stub executables.

The entrypoint backgrounds a pump loop and then hands the shell to the watchdog with `exec`, so
it cannot run under `subprocess.run` with captured pipes: the loop inherits them, and the run
never sees an end of file. Each test starts it in a session of its own, with its output in
files, waits for the exec'd watchdog stub to exit, polls the call log for what the background
processes do, and kills the whole session at teardown so nothing outlives the test.
"""

import contextlib
import os
import re
import signal
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ENTRYPOINT = REPO / "containers" / "entrypoint.sh"

RECORD = 'printf "%s %s cwd=%s\\n" "$(basename "$0")" "$*" "$(pwd)" >> "$CALLS"\n'


def _stub(path, body=""):
    path.write_text("#!/bin/sh\n" + RECORD + body)
    path.chmod(0o755)


class World:
    def __init__(self, root):
        self.root = root
        for name in ("seed", "work", "state", "build", "run", "pgbin", "bin"):
            (root / name).mkdir()
        (self.root / "seed" / "watchdog.py").write_text("print('seed')\n")
        (self.root / "work" / "stale.txt").write_text("from the last run\n")
        (self.root / "build" / "artifact.o").write_text("x")
        locked = self.root / "build" / "locked"
        locked.mkdir()
        (locked / "inner").write_text("x")
        locked.chmod(stat.S_IRUSR | stat.S_IXUSR)
        self.calls = root / "calls.log"
        self.calls.write_text("")
        _stub(
            self.root / "bin" / "python",
            'case "$1" in\n'
            "  *pump.py)\n"
            '    if [ ! -e "$CALLS.pump-failed" ]; then : > "$CALLS.pump-failed"; exit 1; fi\n'
            "    exec sleep 60 ;;\n"
            "esac\n"
            "exit 0\n",
        )
        _stub(self.root / "pgbin" / "initdb", 'mkdir -p "$2" && : > "$2/PG_VERSION"\n')
        _stub(
            self.root / "pgbin" / "postgres",
            'if [ -e "$2/postmaster.pid" ]; then echo "postgres saw-pid-file" >> "$CALLS"; fi\n',
        )
        _stub(self.root / "pgbin" / "pg_isready")
        _stub(self.root / "pgbin" / "createdb")
        _stub(self.root / "bin" / "nats-server")
        _stub(self.root / "bin" / "redis-server")
        self.procs = []

    def env(self, **extra):
        env = dict(os.environ)
        env.update(
            CALLS=str(self.calls),
            PATH=f"{self.root / 'bin'}:{env['PATH']}",
            SEED_DIR=str(self.root / "seed"),
            WORK_DIR=str(self.root / "work"),
            STATE_DIR=str(self.root / "state"),
            BUILD_DIR=str(self.root / "build"),
            RUN_DIR=str(self.root / "run"),
            PUMP_BIN=str(self.root / "pump.py"),
            PG_BIN=str(self.root / "pgbin"),
            MOUNT_ROOTS="",
            PUMP_RESTART_SECONDS="0.05",
        )
        env.update(extra)
        return env

    def run(self, **extra):
        stdout = (self.root / "stdout.log").open("w")
        stderr = (self.root / "stderr.log").open("w")
        proc = subprocess.Popen(
            ["sh", str(ENTRYPOINT)],
            env=self.env(**extra),
            start_new_session=True,
            stdout=stdout,
            stderr=stderr,
        )
        self.procs.append(proc)
        proc.wait(timeout=20)
        stdout.close()
        stderr.close()
        return proc

    def lines(self):
        return self.calls.read_text().splitlines()

    def wait_for(self, predicate, deadline=10.0):
        end = time.monotonic() + deadline
        while time.monotonic() < end:
            if predicate(self.lines()):
                return True
            time.sleep(0.05)
        return predicate(self.lines())

    def stderr(self):
        return (self.root / "stderr.log").read_text()

    def close(self):
        for proc in self.procs:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(proc.pid, signal.SIGTERM)
        (self.root / "build").chmod(0o755)
        for path in (self.root / "build").rglob("*"):
            with contextlib.suppress(OSError):
                path.chmod(0o755)


@pytest.fixture
def world(tmp_path):
    instance = World(tmp_path)
    yield instance
    instance.close()


def _watchdog_calls(lines):
    return [line for line in lines if line.startswith("python watchdog.py")]


def test_the_seed_replaces_work_and_the_watchdog_runs_from_there(world):
    world.run()
    assert (world.root / "work" / "watchdog.py").exists()
    assert not (world.root / "work" / "stale.txt").exists()
    (call,) = _watchdog_calls(world.lines())
    assert call.endswith(f"cwd={world.root / 'work'}")


def test_the_watchdog_is_the_one_exec_and_the_last_line():
    lines = [line.strip() for line in ENTRYPOINT.read_text().splitlines()]
    assert [line for line in lines if line][-1] == 'exec "$PYTHON" watchdog.py'
    assert len([line for line in lines if line.startswith("exec ")]) == 1


def test_the_pump_loop_is_started_before_the_exec(world):
    text = ENTRYPOINT.read_text()
    (loop,) = [line for line in text.splitlines() if "$PUMP_BIN" in line and "while" in line]
    assert loop.rstrip().endswith("&")
    assert text.index(loop) < text.index('exec "$PYTHON" watchdog.py')
    world.run()
    assert world.wait_for(
        lambda lines: any(line.startswith("python ") and "pump.py" in line for line in lines)
    )
    assert _watchdog_calls(world.lines())


def test_a_crashing_pump_is_restarted_by_the_loop(world):
    world.run()
    assert world.wait_for(lambda lines: len([line for line in lines if "pump.py" in line]) >= 2)


def test_the_build_area_is_emptied_without_being_removed(world):
    world.run()
    assert (world.root / "build").is_dir()
    assert list((world.root / "build").iterdir()) == []


def test_postgres_is_initialised_once_under_state_and_started_from_the_versioned_bin(world):
    data = world.root / "state" / "postgres"
    world.run()
    assert world.wait_for(lambda lines: any(line.startswith("createdb ") for line in lines))
    lines = world.lines()
    assert any(line.startswith(f"initdb -D {data} ") for line in lines)
    assert any(line.startswith(f"postgres -D {data} -k {world.root / 'run'} ") for line in lines)
    world.calls.write_text("")
    world.run()
    assert world.wait_for(lambda lines: any(line.startswith("postgres ") for line in lines))
    assert not any(line.startswith("initdb ") for line in world.lines())


def test_a_stale_postmaster_pid_is_cleared_before_postgres_starts(world):
    data = world.root / "state" / "postgres"
    data.mkdir()
    (data / "PG_VERSION").write_text("17\n")
    (data / "postmaster.pid").write_text("12\n")
    world.run()
    assert world.wait_for(lambda lines: any(line.startswith("postgres -D") for line in lines))
    assert "postgres saw-pid-file" not in world.lines()
    assert not (data / "postmaster.pid").exists()


def test_nats_and_redis_keep_their_data_under_state(world):
    world.run()
    state = world.root / "state"
    assert world.wait_for(
        lambda lines: (
            any(line.startswith("nats-server ") for line in lines)
            and any(line.startswith("redis-server ") for line in lines)
        )
    )
    (nats,) = [line for line in world.lines() if line.startswith("nats-server ")]
    (redis,) = [line for line in world.lines() if line.startswith("redis-server ")]
    assert f"-sd {state / 'nats'}" in nats and "-a 127.0.0.1" in nats
    assert f"--dir {state / 'redis'}" in redis and "--bind 127.0.0.1" in redis
    assert (state / "nats").is_dir()
    assert (state / "redis").is_dir()
    assert (world.root / "run" / "logs").is_dir()


def test_a_server_that_fails_to_start_does_not_stop_the_handoff(world):
    for path in (
        world.root / "pgbin" / "initdb",
        world.root / "bin" / "nats-server",
        world.root / "bin" / "redis-server",
    ):
        _stub(path, "exit 1\n")
    world.run()
    assert _watchdog_calls(world.lines())


def test_a_mount_root_on_the_host_filesystem_draws_the_factual_warning(world):
    root = world.root / "state"
    reference = world.root / "reference"
    reference.mkdir()
    sentence = f"warning: {root} shares a filesystem with the host; its size boundary is absent"
    world.run(MOUNT_ROOTS=str(root), UNBOUNDED_REFERENCE=str(reference))
    assert sentence in world.stderr()
    assert _watchdog_calls(world.lines())
    world.calls.write_text("")
    world.run(MOUNT_ROOTS=str(root), UNBOUNDED_REFERENCE="/proc")
    assert sentence not in world.stderr()


def test_the_entrypoint_names_state_only_for_the_servers():
    for line in ENTRYPOINT.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not ("STATE_DIR" in line or "/state" in line):
            continue
        assert re.search(r"postgres|nats|redis|MOUNT_ROOTS|STATE_DIR[:=]", line), line


def test_no_harness_or_recorder_module_names_state():
    modules = [
        "harness/agent.py",
        "harness/chassis.py",
        "harness/watchdog.py",
        "pump/pump.py",
        "recorder/proxy.py",
        "recorder/recorder_streams.py",
        "recorder/core_caps.py",
    ]
    for module in modules:
        assert '"/state' not in (REPO / module).read_text(), module
