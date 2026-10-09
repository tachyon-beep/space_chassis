#!/bin/sh
# The vehicle's half of the window, as a service.
#
# `docs/deep_research/vehicle/tools/console.py` is the executive this container runs: one process
# for every window, which reads the vehicle configuration baked at /opt/vehicle, writes the six
# files of each window into the shared window image, keeps its own private state (checkpoints, the
# lock, the durable per-cycle record) under /state, and resumes the same world after a restart. That
# is the whole of what `contract/diode_probe.py` checks of a window, and the reason this service
# exists rather than the fleet being pointed at the fixture (`contract/fake_diode.py`), which
# satisfies the contract and models nothing.
#
# What this script decides, and what it deliberately does not:
#
#   * **the window root is the one the fleet is already mounted on.** Each agent binds only its own
#     `/diode/<slug>/` from the shared window image; this service binds the whole image, so every
#     agent's window appears inside that agent's own mount.
#   * **one executive serves every window.** Every window commands the one world, and the executive
#     takes an exclusive lock on its state directory, so a second process would refuse.
#   * **the slug set is the world's identity.** The vehicle records it in its checkpoint, and a
#     restart whose set differs refuses (exit 3). So it comes from VEHICLE_SLUGS alone -- the roster
#     compose passes -- and never from a scan of the window root, where a stray directory would turn
#     every restart into a crash loop. Order does not matter; duplicates are dropped.
#   * **`vehicle` is served only when there is no roster.** It is the window a probe run by hand
#     points at, in a stack with no fleet in it. Beside a fleet it would be a command authority on
#     the one world that no agent holds, and a probe that submits commands through it would actuate
#     the spacecraft the fleet is flying with nobody to attribute it to.
#   * **no `--phase`.** A resume takes the phase from the checkpoint; naming one that disagrees
#     refuses.
#   * **it `exec`s the console**, so it is the container's process under docker-init and `docker
#     stop`'s SIGTERM reaches it directly.
#   * **it does not fly.** Accepting a command and simulating its consequence are different claims
#     (`console.py`'s own docstring), and the physics that would follow is `plant.md`'s.
#
# The operator sets these through the environment, all with the defaults the compose file uses:
#
#   DIODE_DIR           the window root                                  (/diode)
#   VEHICLE_STATE_DIR   the executive's private state                    (/state)
#   VEHICLE_SLUGS       the windows to serve, comma-separated            (the roster, else `vehicle`)
#   VEHICLE_SCENARIO    the run's difficulty identity                    (nominal)
#   VEHICLE_SEED        the run's master seed for the fault streams      (0)
#   DIODE_POLL_SECONDS  seconds between cycles                           (5)
#   VEHICLE_RING_SLOTS  frames per window                                (300)
#
# The scenario, the seed, the ring and the slug set are the world's identity: a restart that names
# any of them differently refuses rather than flying a different world under the same name.
set -eu

: "${DIODE_DIR:=/diode}"
: "${VEHICLE_DIR:=/opt/vehicle}"
: "${VEHICLE_STATE_DIR:=/state}"
: "${VEHICLE_SCENARIO:=nominal}"
: "${VEHICLE_SEED:=0}"
: "${DIODE_POLL_SECONDS:=5}"
: "${VEHICLE_RING_SLOTS:=300}"

if [ ! -f "$VEHICLE_DIR/tools/console.py" ]; then
    echo "the vehicle is not at $VEHICLE_DIR -- this image was built without it" >&2
    exit 44
fi

# The roster's names, in the order given, each once; `vehicle` only when there is no roster.
SLUGS=""
for slug in $(printf '%s' "${VEHICLE_SLUGS:-}" | tr ',' ' '); do
    # The roster's own alphabet (scripts/roster.py): a name that is not one path component never
    # reaches the vehicle.
    case "$slug" in
        [a-z]*) ;;
        *) echo "VEHICLE_SLUGS names '$slug', which is not a roster slug" >&2; exit 2 ;;
    esac
    case "$slug" in
        *[!a-z0-9_]*) echo "VEHICLE_SLUGS names '$slug', which is not a roster slug" >&2; exit 2 ;;
    esac
    if [ "${#slug}" -gt 32 ]; then
        echo "VEHICLE_SLUGS names '$slug', which is not a roster slug" >&2
        exit 2
    fi
    case " $SLUGS " in
        *" $slug "*) continue ;;
    esac
    SLUGS="$SLUGS $slug"
done
[ -n "$SLUGS" ] || SLUGS=" vehicle"

set -- \
    --dir "$VEHICLE_DIR" \
    --diode-dir "$DIODE_DIR" \
    --state-dir "$VEHICLE_STATE_DIR" \
    --scenario "$VEHICLE_SCENARIO" \
    --seed "$VEHICLE_SEED" \
    --ring-slots "$VEHICLE_RING_SLOTS" \
    --poll "$DIODE_POLL_SECONDS" \
    --cycles 0
for slug in $SLUGS; do
    # The window directory, created here rather than left to the console, so a missing mount point
    # fails for a reason that names it.
    mkdir -p "$DIODE_DIR/$slug"
    set -- "$@" --slug "$slug"
done

echo "[vehicle] serving$SLUGS into $DIODE_DIR, state in $VEHICLE_STATE_DIR" >&2
exec python3 "$VEHICLE_DIR/tools/console.py" "$@"
