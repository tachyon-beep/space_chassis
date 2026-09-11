#!/bin/sh
# Prepare the host for the stack: the durable directories, their ownership, the
# roster, and the environment file.
#
# Two of these steps are not tidiness.
#
# The directories under ./volumes are bind-mounted into containers that run as
# uid 1000 and drop every capability, so they cannot chown anything themselves.
# A bind-mount source that does not exist is created by the Docker daemon as
# root -- including each agent's home and diary, whose names come from the
# roster and therefore cannot be known until it has been drawn. So they are all
# created here, and owned correctly, before compose ever runs. The failure this
# prevents looks like an agent that cannot write its own home.
#
# Re-running is safe: existing directories and an existing roster are kept.
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$REPO_DIR"

OWNER_UID=${AGENT_UID:-1000}
OWNER_GID=${AGENT_GID:-1000}

echo "== durable directories"
for dir in work diode pump transcripts telemetry llm_sock home diary; do
    mkdir -p "volumes/$dir"
done
mkdir -p volumes/telemetry/agents

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
# The names go into .env, which compose reads with no flags. A separate roster
# file would need `--env-file` on every command, and a stack started without it
# hands every agent the fallback name: agent_1 is handed /home/agent_1 while its
# real directory is /home/mazarine, and it comes up unable to write its home.
if [ -f volumes/work/roster.json ] && [ "${REROLL:-0}" != "1" ]; then
    python3 scripts/roster.py --print --work-dir volumes/work
    python3 scripts/roster.py --work-dir volumes/work --env-file .env >/dev/null
    echo "   .env refreshed from the existing roster"
else
    ROSTER_SEED=${ROSTER_SEED:-$(date +%s)}
    python3 scripts/roster.py --count "${FLEET_COUNT:-10}" --seed "$ROSTER_SEED" \
        --work-dir volumes/work --env-file .env
    echo "   seed $ROSTER_SEED (rerun with REROLL=1 to draw again)"
fi

echo "== each agent's own directories"
# The names come from the roster, which is why this runs after it. Each agent
# gets a home with somewhere for its session and its logs, a diary, and a pump
# directory with a log directory, because a directory the pump cannot write is a
# schedule that silently does nothing.
python3 - "$REPO_DIR" <<'PYTHON'
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
roster = json.loads((repo / "volumes" / "work" / "roster.json").read_text(encoding="utf-8"))
for entry in roster["agents"]:
    slug = entry["slug"]
    for path in (
        repo / "volumes" / "home" / slug / "session",
        repo / "volumes" / "home" / slug / "logs",
        repo / "volumes" / "diary" / slug,
        repo / "volumes" / "pump" / slug / "log",
        repo / "volumes" / "diode" / slug / "output",
        repo / "volumes" / "telemetry" / "agents" / slug,
        repo / "volumes" / "telemetry" / "work" / slug,
    ):
        path.mkdir(parents=True, exist_ok=True)
print(f"   {len(roster['agents'])} home(s), diary(s), pump and telemetry directory(ies)")
PYTHON

if [ "$(id -u)" -eq 0 ]; then
    chown -R "$OWNER_UID:$OWNER_GID" volumes/work volumes/diode volumes/pump volumes/llm_sock \
        volumes/home volumes/diary
    chown -R "$OWNER_UID:$OWNER_GID" volumes/transcripts volumes/telemetry
    echo "   ownership set to $OWNER_UID:$OWNER_GID"
else
    echo "   not root: leaving ownership alone. If the stack cannot write its own"
    echo "   homes, run: sudo chown -R $OWNER_UID:$OWNER_GID $REPO_DIR/volumes"
fi

cat <<'NEXT'

Next:
  1. put the model credential in .env (OPENROUTER_API_KEY, or LLM_BASE_URL + LLM_API_KEY)
  2. docker compose --profile fleet up --build
  3. watch it: python3 scripts/status.py

The fleet starts as ten agents on an internal network with no route outward.
Whether a window exists at all is the diode's business; without one the stack
still runs and nothing can leave.
NEXT
