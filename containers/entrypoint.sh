#!/bin/sh
# The world's first process. Everything below it is either the supervisor's
# business, the pump's business, or the duty's.
#
# Three jobs, in order:
#
#   1. seed the floor -- the shared codebase and this agent's home, once. The
#      marker file is what makes it "once": a fleet that deletes everything it
#      was given should get an empty directory back, not a resurrection, and
#      the difference between those two is whether this script tests for a
#      marker or for emptiness.
#   2. start the servers the world carries: postgres, nats, redis. They are
#      present, running and *empty*. No schema, no subjects, no roles, no
#      tables -- deciding what any of it is for is the first real question the
#      mission has to answer, and this script will not answer it.
#   3. start the pump and the supervisor. The pump runs whatever the agent has
#      scheduled; the supervisor runs the duty and repairs it when it hurts
#      itself.
#
# It is also the one place that decides what "the duty" is. AGENT_ENTRY names
# it, defaulting to the seed at $SEED_DIR/duty.py. The agents may replace that
# file; the supervisor re-reads it every time a run ends, which is how a
# rewrite becomes the next incarnation.
set -eu

[ -f /etc/agent.env ] && . /etc/agent.env

: "${WORK_DIR:=/work}"
: "${SEED_DIR:=/opt/agent}"
: "${AGENT_HOME:=/home/agent}"
: "${DIARY_DIR:=/diary}"
: "${BRIEF_DIR:=/opt/brief}"
: "${SERVICES_DIR:=/opt/services}"
export WORK_DIR SEED_DIR AGENT_HOME DIARY_DIR BRIEF_DIR SERVICES_DIR

AGENT_ENTRY="${AGENT_ENTRY:-$WORK_DIR/duty.py}"
export AGENT_ENTRY

LOG_DIR="$AGENT_HOME/logs"
mkdir -p "$LOG_DIR" "$DIARY_DIR" /run/agent

log() { printf '%s [entrypoint] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# Declare this agent to the recorder.
#
# The recorder serves whichever agents announce themselves, rather than reading
# a list of names, so the fleet's names (drawn at random, and different every
# time the roster is redrawn) are stated in exactly one place: here, by the
# agent that was given one. The announcement lands in the shared codebase
# because that is the directory an agent can write and the recorder can read;
# the socket directory itself is mounted read-only into the fleet, so an agent
# cannot create its own listener there and should not be able to.
if [ -n "${AGENT_SLUG:-}" ]; then
    mkdir -p "$WORK_DIR/.fleet" 2>/dev/null || true
    printf '%s\n' "$AGENT_SLUG" > "$WORK_DIR/.fleet/${AGENT_SLUG}.agent" 2>/dev/null || true
fi

# --- 1. the floor ----------------------------------------------------------
if [ ! -f "$WORK_DIR/.seeded" ]; then
    log "seeding $WORK_DIR from $SEED_DIR"
    cp -a "$SEED_DIR/." "$WORK_DIR/" 2>/dev/null || true
    date -u +%Y-%m-%dT%H:%M:%SZ > "$WORK_DIR/.seeded"
fi
mkdir -p "$AGENT_HOME/session" "$AGENT_HOME/logs" "$DIARY_DIR"
if [ ! -f "$AGENT_HOME/.seeded" ]; then
    [ -d "$SEED_DIR/home" ] && cp -a "$SEED_DIR/home/." "$AGENT_HOME/" 2>/dev/null || true
    date -u +%Y-%m-%dT%H:%M:%SZ > "$AGENT_HOME/.seeded"
fi

# --- 2. the servers the world carries --------------------------------------
start_servers() {
    if ! pg_isready -q 2>/dev/null; then
        log "starting postgresql"
        cluster=$(ls /etc/postgresql 2>/dev/null | head -1)
        [ -n "$cluster" ] && pg_ctlcluster "$cluster" main start >/dev/null 2>&1 || true
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            pg_isready -q 2>/dev/null && break
            sleep 1
        done
    fi
    # One empty database owned by this container's user, so a client can
    # connect with no credential it does not have. No tables, no roles, no
    # extensions, no schema.
    if pg_isready -q 2>/dev/null; then
        whoami >/dev/null && createuser -s "$(id -un)" 2>/dev/null || true
        createdb -O "$(id -un)" chassis 2>/dev/null || true
    fi

    if ! nc -z 127.0.0.1 4222 2>/dev/null; then
        log "starting nats-server"
        mkdir -p "$AGENT_HOME/.nats"
        nats-server -a 127.0.0.1 -p 4222 -m 8222 -sd "$AGENT_HOME/.nats" \
            >> "$LOG_DIR/nats.log" 2>&1 &
    fi
    if ! nc -z 127.0.0.1 6379 2>/dev/null; then
        log "starting redis-server"
        mkdir -p "$AGENT_HOME/.redis"
        redis-server --bind 127.0.0.1 --port 6379 --dir "$AGENT_HOME/.redis" \
            --save '' --appendonly no >> "$LOG_DIR/redis.log" 2>&1 &
    fi
}
start_servers

# --- 3. the window, the pump, the supervisor -------------------------------
# If an operator mounted a diode implementation, run it. It is the only thing
# in this container with a route outward, and the only thing that talks to the
# vehicle. Killing it is allowed and is a decision with consequences.
if [ -n "${DIODE_ENTRY:-}" ] && [ -f "$DIODE_ENTRY" ]; then
    log "starting diode: $DIODE_ENTRY"
    python "$DIODE_ENTRY" >> "$LOG_DIR/diode.log" 2>&1 &
fi

log "starting pump for ${PUMP_DUTY_DIR:-/pump}"
python "$SERVICES_DIR/pump.py" >> "$LOG_DIR/pump.log" 2>&1 &
PUMP_PID=$!

shutdown() {
    log "stopping"
    [ -n "${PUMP_PID:-}" ] && kill -TERM "$PUMP_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    exit 0
}
trap shutdown TERM INT

log "work=$WORK_DIR home=$AGENT_HOME name=${AGENT_NAME:-$AGENT_SLUG} entry=$AGENT_ENTRY \
socket=${LLM_SOCKET_PATH:-none}"
while true; do
    set +e
    python "$SERVICES_DIR/supervisor.py" >> "$LOG_DIR/supervisor.log" 2>&1
    rc=$?
    set -e
    # Keep the supervisor's log bounded; its tail is what anyone reads.
    if [ -f "$LOG_DIR/supervisor.log" ] && [ "$(wc -c < "$LOG_DIR/supervisor.log")" -gt 2000000 ]; then
        tail -c 500000 "$LOG_DIR/supervisor.log" > "$LOG_DIR/supervisor.log.tmp" \
            && mv "$LOG_DIR/supervisor.log.tmp" "$LOG_DIR/supervisor.log"
    fi
    if [ "$rc" -eq 1 ]; then
        log "supervisor exhausted its ladder; pausing before the next attempt"
        sleep 60
    else
        sleep 3
    fi
done
