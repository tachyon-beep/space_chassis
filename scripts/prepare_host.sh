#!/bin/sh
# Prepare the host for the stack: the roster, the environment file, and the bounded volume images.
#
# Every volume an agent or a recorder writes is a preallocated ext4 image, loop-mounted under
# volumes/ (scripts/volume_images.py is the manifest). This script draws the fleet's names, plans
# the images against the free disk, creates the ones that are missing, and checks them. Mounting an
# image and creating its data/ directory need root; this script never runs sudo itself. The image
# creator tries `sudo -n mount` and otherwise prints the exact commands, and they are collected
# here into one block for the operator, followed by the /etc/fstab lines that mount them at boot.
#
# Exit status: 0 when every image is ready; 2 when the operator has steps to run (the block above
# says which), or when the old layout must be archived first; 1 on any error.
#
# Re-running is safe: an existing roster is kept (REROLL=1 draws again), existing images are
# neither reformatted nor shrunk, and a ready image is left alone.
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$REPO_DIR"
PYTHON=${PYTHON:-python3}
ARCHIVE=volumes.pre-aurora-2026-10-09

echo "== the crate registry"
if [ ! -d vendor/registry ]; then
    echo "   vendor/registry is missing." >&2
    echo "   Rebuild it with: ./scripts/build_registry.sh" >&2
    exit 1
fi
echo "   $(ls vendor/registry/*.crate 2>/dev/null | wc -l) crates"

echo "== environment"
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   wrote .env from .env.example -- set OPENROUTER_API_KEY before starting"
else
    echo "   .env exists, kept (its roster block is refreshed below)"
fi

echo "== the roster"
# The names go into .env, which compose and the volume tooling read with no flags. The roster file
# itself is the operator's bookkeeping, in operator/. A roster from the old layout, which lived in
# a volume every agent could write, is carried forward once and validated before it reaches .env.
mkdir -p operator
if [ -f volumes/work/roster.json ] && [ ! -f operator/roster.json ]; then
    cp volumes/work/roster.json operator/roster.json
    echo "   copied the roster out of volumes/work into operator/"
fi
if [ -f operator/roster.json ] && [ "${REROLL:-0}" != "1" ]; then
    "$PYTHON" scripts/roster.py --roster-dir operator --env-file .env
    echo "   .env refreshed from the existing roster"
else
    ROSTER_SEED=${ROSTER_SEED:-$(date +%s)}
    "$PYTHON" scripts/roster.py --count "${ROSTER_COUNT:-10}" --seed "$ROSTER_SEED" \
        --roster-dir operator --env-file .env
    echo "   seed $ROSTER_SEED (rerun with REROLL=1 to draw again)"
fi

# docker-compose.yml declares a fixed number of agents, and every one of its services binds images
# named for agents 1..N -- the monitor and the review panel bind them all -- so a roster of any other
# size would leave even a bare `compose up` unable to start. Regenerate the compose for another size
# (scripts/build_compose.py) rather than drawing one here.
declared=$(grep -c '^  agent_[0-9][0-9]*:$' docker-compose.yml || true)
drawn=$(sed -n 's/^FLEET_COUNT=//p' .env | tail -n 1)
if [ "$drawn" != "$declared" ]; then
    echo "   the roster names ${drawn:-no} agents, but docker-compose.yml declares $declared agents;" >&2
    echo "   draw $declared (ROSTER_COUNT=$declared REROLL=1), or regenerate the compose for $drawn" >&2
    exit 1
fi

ROOT=$("$PYTHON" scripts/volume_images.py root)

echo "== the old layout"
# Before the images, the volumes were plain directories under volumes/. None of these is ever an
# image mount point now -- per-agent images are <kind>_<slug> -- so any of them means the old tree
# is still in place. It is archived, never migrated, and only by the operator: this script moves
# nothing. It must happen before the first image is mounted, while volumes/ can still be moved.
old=""
for name in work home diary pump transcripts telemetry llm_sock; do
    if [ -e "$ROOT/$name" ]; then
        old="$old $ROOT/$name"
    fi
done
if [ -n "$old" ]; then
    echo "   the old volume layout is still here:$old"
    echo "   it holds the stub-model runs from before the Aurora port; archive it, then rerun:"
    echo ""
    echo "     mv volumes $ARCHIVE"
    echo ""
    exit 2
fi
echo "   none"

echo "== the images"
"$PYTHON" scripts/volume_images.py plan || exit 1
list=$("$PYTHON" scripts/volume_images.py list) || exit 1
block=$(mktemp)
trap 'rm -f "$block"' EXIT
printf '%s\n' "$list" | while read -r name size img mnt; do
    [ -n "$name" ] || continue
    set +e
    output=$(sh scripts/create_volume_image.sh "$name" "$size" "$img" "$mnt" 2>&1)
    status=$?
    set -e
    case $status in
        0) [ -z "$output" ] || printf '%s\n' "$output" ;;
        2) printf '%s\n' "$output" >> "$block" ;;
        *)
            printf '%s\n' "$output" >&2
            echo "   creating $name failed with status $status" >&2
            exit 1
            ;;
    esac
done || exit 1

echo "== each agent's window and telemetry directories"
# Inside the shared window image each agent binds only its own directory, and inside the operator's
# telemetry image the review panel binds each agent's telemetry at agents/<slug>. data/ belongs to
# uid 1000, so these need no root -- but only once the image is really mounted there.
slugs=$(sed -n 's/^FLEET_SLUGS=//p' .env | tail -n 1 | tr ',' ' ')
made=0
for slug in $slugs; do
    if mountpoint -q "$ROOT/diode" && [ -d "$ROOT/diode/data" ]; then
        mkdir -p "$ROOT/diode/data/$slug/output"
        made=1
    fi
    if mountpoint -q "$ROOT/operator_telemetry" && [ -d "$ROOT/operator_telemetry/data" ]; then
        mkdir -p "$ROOT/operator_telemetry/data/agents/$slug"
        made=1
    fi
done
if [ "$made" = 1 ]; then
    echo "   made for: $slugs"
else
    echo "   not yet: the window and operator telemetry images are not mounted"
fi

if [ -s "$block" ]; then
    echo ""
    echo "steps for the operator:"
    cat "$block"
fi
echo ""
echo "/etc/fstab lines that mount the images at boot:"
"$PYTHON" scripts/volume_images.py fstab || exit 1

if [ -s "$block" ]; then
    echo ""
    echo "Run the steps above, then rerun scripts/prepare_host.sh."
    exit 2
fi

echo ""
"$PYTHON" scripts/volume_images.py check || exit 1

cat <<'NEXT'

Next:
  1. put the model credential in .env (OPENROUTER_API_KEY, or LLM_BASE_URL + LLM_API_KEY)
  2. docker compose --profile fleet up --build
  3. watch it: python3 scripts/status.py

The fleet starts as ten agents on an internal network with no route outward, each on its own
bounded volumes. Whether a window exists at all is the vehicle's business; without one the stack
still runs and nothing can leave.
NEXT
