#!/bin/sh
# The agent container's first process, in Aurora's form.
#
# Five jobs, in order, and then the container belongs to the watchdog:
#
#   1. say which mount roots have no size boundary. A root on the same filesystem as the plain
#      host bind at UNBOUNDED_REFERENCE is not one of the bounded volume images, and a fact is
#      worth one line on stderr. It never stops the start. `/diode/*` is a glob on purpose: the
#      window is bound at /diode/<slug>, and /diode itself is only the image's directory.
#   2. empty the build area. It is a scratch volume; nothing in it is meant to outlive the
#      container, and starting from nothing is cheaper than reasoning about what a dead build
#      left behind.
#   3. start the servers the world carries: postgres, nats, redis. They are present, running and
#      *empty* -- deciding what any of it is for is the first real question the mission has, and
#      this script will not answer it. Postgres keeps its cluster under STATE_DIR, the agent's own
#      durable store, so its databases outlive a restart. Redis runs with persistence off and NATS
#      without JetStream, as they always have here: their directories under STATE_DIR are where
#      either would keep data if it were configured to. Logs live on the run tmpfs, because logs in
#      the durable store grow without bound. Each server is guarded and in the background: one
#      that will not start is the agent's to notice, not a reason to stop or delay the world.
#   4. start the pump, in a loop that restarts it, so work the agent scheduled keeps running
#      while the agent is mid-conversation, dead, or being repaired.
#   5. reseed /work from the image and exec the watchdog. The seed is a git repository with
#      baseline and rescue tags; the watchdog restores from whichever tags the agent has moved.
#      `exec` is the point: when the watchdog dies the container ends, the restart policy brings
#      it back, and this script reseeds -- the only rung below rescue.
#
# Every path and binary has an override whose default is the real one, so the script can be run
# against stubs in a temporary directory (tests/test_agent_entrypoint.py).
set -u

: "${SEED_DIR:=/opt/agent}"
: "${WORK_DIR:=/work}"
: "${STATE_DIR:=/state}"
: "${BUILD_DIR:=/build}"
: "${RUN_DIR:=/run/agent}"
: "${PUMP_BIN:=/usr/local/bin/pump.py}"
: "${PYTHON:=python}"
: "${MOUNT_ROOTS:=/state /shared /diode/* /pump /build /telemetry /llm/console /llm/sock}"
: "${UNBOUNDED_REFERENCE:=/vendor/registry}"
: "${PUMP_RESTART_SECONDS:=5}"
: "${PG_READY_TRIES:=20}"
: "${LLM_CONSOLE_DIR:=/llm/console}"
: "${CONSOLE_SEED:=/usr/local/share/space/llm_console_seed.json}"
if [ -z "${PG_BIN:-}" ]; then
    for candidate in /usr/lib/postgresql/*/bin; do
        PG_BIN=$candidate
        break
    done
fi
: "${PG_BIN:=/usr/lib/postgresql/bin}"

# --- 1. mount roots without a size boundary ---------------------------------
if reference=$(stat -c %d "$UNBOUNDED_REFERENCE" 2>/dev/null); then
    for root in $MOUNT_ROOTS; do
        [ -d "$root" ] || continue
        device=$(stat -c %d "$root" 2>/dev/null) || continue
        if [ "$device" = "$reference" ]; then
            echo "warning: $root shares a filesystem with the host; its size boundary is absent" >&2
        fi
    done
fi

# --- 2. the build area ------------------------------------------------------
if [ -d "$BUILD_DIR" ]; then
    chmod -R u+rwX "$BUILD_DIR" 2>/dev/null || true
    find "$BUILD_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
fi

# --- 3. the servers the world carries ---------------------------------------
mkdir -p "$STATE_DIR/nats" "$STATE_DIR/redis" "$RUN_DIR/logs" 2>/dev/null || true
(
    # A container that was killed leaves postmaster.pid behind, and in a fresh container its pid
    # can belong to something else; nothing but this script can hold this data directory here.
    if [ -e "$STATE_DIR/postgres/PG_VERSION" ]; then
        rm -f "$STATE_DIR/postgres/postmaster.pid"
    else
        # initdb writes PG_VERSION before it has built anything else, and a SIGKILL during the
        # first start skips its own cleanup. Building aside and moving into place only on
        # success means a half-built cluster is never the one that gets started.
        rm -rf "$STATE_DIR/postgres.init" "$STATE_DIR/postgres"
        "$PG_BIN/initdb" -D "$STATE_DIR/postgres.init" --auth=trust -U "$(id -un)" \
            >> "$RUN_DIR/logs/postgres.log" 2>&1 || exit 0
        mv "$STATE_DIR/postgres.init" "$STATE_DIR/postgres" || exit 0
    fi
    "$PG_BIN/postgres" -D "$STATE_DIR/postgres" -k "$RUN_DIR" -c listen_addresses=127.0.0.1 \
        >> "$RUN_DIR/logs/postgres.log" 2>&1 &
    tries=0
    until "$PG_BIN/pg_isready" -q -h "$RUN_DIR" 2>/dev/null; do
        tries=$((tries + 1))
        if [ "$tries" -ge "$PG_READY_TRIES" ]; then
            # The server's own log is on the run tmpfs; this line is what survives on the
            # container's log.
            echo "postgres did not answer on $RUN_DIR; see $RUN_DIR/logs/postgres.log" >&2
            exit 0
        fi
        sleep 0.5
    done
    # One empty database owned by this user, whom initdb made the superuser, so a client can
    # connect with no credential it does not have. No tables, no roles, no schema.
    "$PG_BIN/createdb" -h "$RUN_DIR" chassis >> "$RUN_DIR/logs/postgres.log" 2>&1 || true
) &
nats-server -a 127.0.0.1 -p 4222 -m 8222 -sd "$STATE_DIR/nats" \
    >> "$RUN_DIR/logs/nats.log" 2>&1 &
redis-server --bind 127.0.0.1 --port 6379 --dir "$STATE_DIR/redis" --save '' --appendonly no \
    >> "$RUN_DIR/logs/redis.log" 2>&1 &

# --- 4. the pump ------------------------------------------------------------
( while true; do "$PYTHON" "$PUMP_BIN" || true; sleep "$PUMP_RESTART_SECONDS"; done ) &

# --- 5. the console, the harness, and the hand-off ---------------------------
# The llm console is the agent's own file once it exists: seeded only when absent, so a restart
# never reverts what the agent tuned or removed. Best-effort: a damaged console volume must not
# stop the container from starting.
[ -e "$LLM_CONSOLE_DIR/console.json" ] || cp "$CONSOLE_SEED" "$LLM_CONSOLE_DIR/console.json" || echo "warning: could not seed the llm console" >&2
find "$WORK_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
cp -r "$SEED_DIR/." "$WORK_DIR/"
cd "$WORK_DIR" || exit 1
exec "$PYTHON" watchdog.py
