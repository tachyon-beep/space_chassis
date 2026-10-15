#!/bin/sh
# The vehicle's half of the window, as a service.
#
# `docs/deep_research/vehicle/tools/console.py` is the loop this container runs. It reads the vehicle
# configuration baked at /opt/vehicle, writes the six files of the window into the per-agent diode
# directory, and advances telemetry on its own -- which is the whole of what `contract/diode_probe.py`
# checks, and the reason this service exists rather than the fleet being pointed at the fixture
# (`contract/fake_diode.py`), which satisfies the contract and models nothing.
#
# What this script decides, and what it deliberately does not:
#
#   * **the diode directory is the one the fleet is already mounted on.** The agents read
#     `/diode/<slug>/`, which the compose file mounts from `./volumes/diode`; so does this service,
#     and the window appears inside the agents' own mount rather than beside it. A vehicle serving
#     into a directory nobody reads is a working implementation of nothing.
#   * **the slug is one window's name in that directory.** The console serves one `<slug>`, so
#     several vehicles would be several slugs; the reference stack serves one, and the fleet's
#     agents are all given that one slug by `docker-compose.yml`.
#   * **it does not initialise and exit.** `console.py --init` creates the directory and stops,
#     which is useful for a probe run by hand and useless as a service: the window has to keep
#     publishing, because "state.json is rewritten every cycle whether or not anything was
#     submitted" is what makes the mirror a mirror.
#   * **it does not fly.** Accepting a command and simulating its consequence are different claims
#     (`console.py`'s own docstring), and the physics that would follow is `plant.md`'s.
#
# The operator sets four things through the environment, all of them with the defaults the compose
# file uses:
#
#   DIODE_DIR      where the per-slug directories live          (/diode)
#   VEHICLE_SLUGS  which windows to serve, comma-separated      (roster, else `vehicle`)
#   VEHICLE_SCENARIO  the run's difficulty identity            (nominal)
#   VEHICLE_SEED   the run's master seed for the fault streams  (0)
#   DIODE_POLL_SECONDS  seconds between cycles                  (5)
#   VEHICLE_RING_SLOTS  frames per window                       (300)
#
# `--scenario` is validated by the console against `mission.yaml#scenario_postures`, so a typo here
# stops the service with a message that names the three postures rather than running a nominal
# mission under a crisis label.
set -eu

[ -f /etc/agent.env ] && . /etc/agent.env

: "${DIODE_DIR:=/diode}"
: "${VEHICLE_DIR:=/opt/vehicle}"
: "${VEHICLE_SCENARIO:=nominal}"
: "${VEHICLE_SEED:=0}"
: "${DIODE_POLL_SECONDS:=5}"
: "${VEHICLE_RING_SLOTS:=300}"

export DIODE_DIR VEHICLE_DIR VEHICLE_SCENARIO VEHICLE_SEED DIODE_POLL_SECONDS
export VEHICLE_RING_SLOTS

if [ ! -f "$VEHICLE_DIR/tools/console.py" ]; then
    echo "the vehicle is not at $VEHICLE_DIR -- this image was built without it" >&2
    exit 44
fi

# **Which slugs to serve, and why the answer is a roster rather than a name.**
#
# The console serves one `<slug>` per process, and the fleet's agents are each given their own:
# `docker-compose.yml` hands agent *n* `DIODE_DUTY_DIR=/diode/$FLEET_N_SLUG`, taken from the roster
# `scripts/roster.py` draws. So a vehicle that published into one directory called `vehicle` would be
# a working implementation of nothing -- the agents would be reading their own empty directories and
# concluding the vehicle was silent, which is the failure mode this whole side exists to prevent.
#
# Three ways to say it, in the order they win:
#
#   VEHICLE_SLUGS   an explicit comma-separated list
#   the roster      whatever `.env`'s `FLEET_N_SLUG` names, because that is what the agents were told
#   `vehicle`       the reference window, for a stack with no fleet in it
#
# The roster is read from `/diode`'s own entries as well as from the environment: an agent directory
# that exists is an agent that will look, and a name in the environment that has no directory is one
# this service can create. Both are swept, so a fleet started before or after the vehicle is served
# either way.
if [ -n "${VEHICLE_SLUGS:-}" ]; then
    SLUGS=$(printf '%s' "$VEHICLE_SLUGS" | tr ',' ' ')
else
    SLUGS=""
    for name in "$DIODE_DIR"/*; do
        [ -d "$name" ] || continue
        SLUGS="$SLUGS $(basename "$name")"
    done
    # The roster's names, from the environment `docker-compose.yml` passes to every service.
    for var in $(env | sed -n 's/^\(FLEET_[0-9][0-9]*_SLUG\)=.*/\1/p' | sort); do
        eval "value=\${$var}"
        [ -n "$value" ] && SLUGS="$SLUGS $value"
    done
    [ -n "$SLUGS" ] || SLUGS="vehicle"
fi

# Deduplicated, and `vehicle` is always served: it is the window a probe run by hand points at, and
# it costs one process to keep it there.
FINAL=""
for slug in $SLUGS vehicle; do
    case " $FINAL " in
        *" $slug "*) continue ;;
    esac
    FINAL="$FINAL $slug"
done

echo "[vehicle] serving $FINAL into $DIODE_DIR" >&2

# One console per slug, and the shell waits on all of them: a service that forked and returned would
# be a service whose container exits while its workers keep running.
PIDS=""
for slug in $FINAL; do
    # The window directory, created here rather than by the console: the console creates it too, but
    # a service that fails on its first run because a mount point is absent has failed for a reason
    # that has nothing to do with the vehicle.
    mkdir -p "$DIODE_DIR/$slug"
    python3 "$VEHICLE_DIR/tools/console.py" \
        --dir "$VEHICLE_DIR" \
        --diode-dir "$DIODE_DIR" \
        --slug "$slug" \
        --scenario "$VEHICLE_SCENARIO" \
        --seed "$VEHICLE_SEED" \
        --ring-slots "$VEHICLE_RING_SLOTS" \
        --poll "$DIODE_POLL_SECONDS" \
        --cycles 0 &
    PIDS="$PIDS $!"
done

# `wait` with no arguments waits for every child. A signal to this process (docker stop) reaches the
# children because they are in the same process group, and the trap makes the exit the shell's rather
# than a child's.
trap 'kill $PIDS 2>/dev/null || true' TERM INT
wait
