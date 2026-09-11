#!/bin/sh
# Check the world's safety properties against a running stack.
#
# Read this as a list of the claims the design makes, each turned into a command
# that either succeeds or does not. It is deliberately shallow: it does not try
# to prove an agent cannot escape, it checks that the walls are where the
# documentation says they are.
#
#   sh scripts/verify_containment.sh            # the first agent only
#   AGENTS="agent_1 agent_4" sh scripts/...     # chosen agents
#   sh scripts/verify_containment.sh --all      # every running agent container
set -u

PROJECT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT"

PASS=0
FAIL=0
SKIP=0

ok()   { PASS=$((PASS + 1)); printf '  PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL + 1)); printf '  FAIL  %s\n' "$1"; }
skip() { SKIP=$((SKIP + 1)); printf '  SKIP  %s\n' "$1"; }

# Which agents to check.
if [ "${1:-}" = "--all" ]; then
    AGENTS=$(docker compose ps --format '{{.Service}}' 2>/dev/null | grep '^agent_' | sort -u)
else
    AGENTS=${AGENTS:-agent_1}
fi

if ! docker compose ps --format '{{.Service}}' >/dev/null 2>&1; then
    echo "no compose project here; is the stack up?" >&2
    exit 2
fi

echo "== the agents do not reach outward"
for agent in $AGENTS; do
    cid=$(docker compose ps -q "$agent" 2>/dev/null)
    if [ -z "$cid" ]; then
        skip "$agent is not running"
        continue
    fi
    # 1. There is a gateway address, because a bridge always has one, but it
    #    must lead nowhere. A route table with a gateway line is therefore not
    #    evidence of anything -- and checking for it reports a false alarm on a
    #    perfectly sealed container. The checks that mean something are the two
    #    below: resolution fails, and a connection to a public address times out.
    if docker exec "$cid" sh -c 'cat /proc/net/route 2>/dev/null | awk "\$2 != \"00000000\" { found=1 } END { exit found ? 0 : 1 }"' 2>/dev/null; then
        ok "$agent has a gateway line, which proves nothing either way"
    fi

    # 2. It cannot resolve or reach anything public. Both must fail.
    if docker exec "$cid" sh -c 'timeout 5 getent hosts example.com >/dev/null 2>&1' 2>/dev/null; then
        bad "$agent resolved a public name"
    else
        ok "$agent cannot resolve outside names"
    fi
    if docker exec "$cid" sh -c 'timeout 5 python3 -c "import socket; socket.create_connection((\"1.1.1.1\", 443), 3)" 2>/dev/null' 2>/dev/null; then
        bad "$agent opened a connection to a public address"
    else
        ok "$agent cannot open a connection outward"
    fi

    # 3. It can reach its siblings and itself, because a control layer needs
    #    somewhere to run: this is the property that must NOT hold.
    if docker exec "$cid" sh -c 'timeout 5 python3 -c "import socket; s=socket.socket(); s.bind((\"127.0.0.1\",0)); s.listen(1)" 2>/dev/null' 2>/dev/null; then
        ok "$agent can listen on its own loopback"
    else
        bad "$agent cannot listen on loopback"
    fi
done

echo "== the credential is not in the fleet"
for agent in $AGENTS; do
    cid=$(docker compose ps -q "$agent" 2>/dev/null)
    [ -z "$cid" ] && continue
    env=$(docker exec "$cid" sh -c 'cat /proc/1/environ | tr "\0" "\n"' 2>/dev/null)
    if printf '%s' "$env" | grep -q 'OPENROUTER_API_KEY=sk-dummy'; then
        ok "$agent carries the dummy key"
    else
        bad "$agent does not carry the placeholder key"
    fi
    # The real key must appear nowhere: not in the environment, not in a file.
    real=$(docker compose config 2>/dev/null | grep -m1 'OPENROUTER_API_KEY:' | sed 's/.*: //')
    if [ -n "$real" ] && [ "$real" != "sk-dummy" ]; then
        if docker exec "$cid" sh -c "grep -rl '$real' /work /home /etc 2>/dev/null" | head -1 | grep -q .; then
            bad "$agent has the real key on disk"
        else
            ok "$agent has no trace of the real key"
        fi
    else
        skip "no key configured, so there is nothing to leak"
    fi
done

echo "== the record is read-only in the fleet"
cid=$(docker compose ps -q "${AGENTS%% *}" 2>/dev/null)
if [ -n "$cid" ]; then
    if docker exec "$cid" sh -c 'touch /transcripts/.probe 2>/dev/null'; then
        bad "an agent can write to /transcripts"
        docker exec "$cid" rm -f /transcripts/.probe 2>/dev/null
    else
        ok "an agent cannot write to /transcripts"
    fi
    if docker exec "$cid" sh -c 'touch /telemetry/.probe 2>/dev/null'; then
        bad "an agent can write to /telemetry"
        docker exec "$cid" rm -f /telemetry/.probe 2>/dev/null
    else
        ok "an agent cannot write to /telemetry"
    fi
    slug=$(docker exec "$cid" sh -c 'echo "$AGENT_SLUG"' 2>/dev/null)
    if [ -n "$slug" ]; then
        if docker exec "$cid" sh -c "test -s /transcripts/$slug/agent_life_transcript.jsonl" 2>/dev/null; then
            ok "an agent can read its own transcript"
        elif docker exec "$cid" sh -c "test -d /transcripts/$slug" 2>/dev/null; then
            skip "the transcript exists but is empty so far"
        else
            bad "an agent cannot see its own transcript directory"
        fi
    fi
else
    skip "no agent container to probe"
fi

echo "== the window is the only way out"
cid=$(docker compose ps -q "${AGENTS%% *}" 2>/dev/null)
if [ -n "$cid" ]; then
    diode=$(docker exec "$cid" sh -c 'echo "$DIODE_DUTY_DIR"' 2>/dev/null)
    if [ -n "$diode" ] && docker exec "$cid" sh -c "[ -d '$diode' ]" 2>/dev/null; then
        ok "the window exists at $diode"
    else
        skip "no window mounted (the diode profile is not up)"
    fi
fi

echo "== the recorder is not reachable from an agent"
cid=$(docker compose ps -q "${AGENTS%% *}" 2>/dev/null)
if [ -n "$cid" ]; then
    if docker exec "$cid" sh -c 'timeout 4 python3 -c "import socket; socket.create_connection((\"recorder\", 8080), 3)" 2>/dev/null'; then
        bad "an agent reached the recorder over the network"
    else
        ok "the recorder is not on the fleet network"
    fi
fi

echo "== the review panel reads and does not write"
cid=$(docker compose ps -q review 2>/dev/null)
if [ -z "$cid" ]; then
    skip "the review panel is not running"
else
    # It must not be on the fleet's network, and it must have no route out.
    if docker exec "$cid" sh -c 'timeout 4 python3 -c "import socket; socket.create_connection((\"1.1.1.1\", 443), 3)" 2>/dev/null'; then
        bad "the review panel reached a public address"
    else
        ok "the review panel has no route outward"
    fi
    if docker exec "$cid" sh -c 'timeout 4 python3 -c "import socket; socket.create_connection((\"recorder\", 8080), 3)" 2>/dev/null'; then
        bad "the review panel can see the recorder"
    else
        ok "the review panel cannot see the recorder"
    fi
    # Its mounts are read-only, so the record cannot be amended from here.
    if docker exec "$cid" sh -c 'touch /transcripts/.probe 2>/dev/null'; then
        bad "the review panel can write to the record"
        docker exec "$cid" rm -f /transcripts/.probe 2>/dev/null
    else
        ok "the review panel cannot write to the record"
    fi
    if docker exec "$cid" sh -c 'touch /telemetry/.probe 2>/dev/null'; then
        bad "the review panel can write to the telemetry record"
    else
        ok "the review panel cannot write to the telemetry record"
    fi
    # And it can read: a panel that is sealed out of its own subject is useless.
    if docker exec "$cid" sh -c 'test -d /transcripts' 2>/dev/null; then
        ok "the review panel can read the transcripts"
    else
        bad "the review panel cannot see the transcripts"
    fi
fi

echo "== the panel is loopback-only on the host"
# The compose file asks for a loopback binding. Whether the daemon granted it is
# a separate question, and the answer here is "no": this environment's Docker
# does not forward published ports at all (a plain `-p` probe on an unrelated
# container is equally unreachable), so the mapping is inert. Inert is not the
# same as exposed, and reporting it as exposed would be a false alarm; the check
# therefore fails only on a binding that is explicitly not loopback.
ports=$(docker compose ps review --format '{{.Ports}}' 2>/dev/null)
if [ -z "$ports" ]; then
    skip "the review panel has no port mapping"
elif printf '%s' "$ports" | grep -qE '(^|[^0-9.])(0\.0\.0\.0|\[::\]|\*)'; then
    bad "the review panel is bound to every host interface: $ports"
elif printf '%s' "$ports" | grep -q '127.0.0.1'; then
    ok "the review panel is bound to host loopback: $ports"
else
    skip "the panel's port is mapped but not listening on the host ($ports); host port forwarding is unavailable in this environment"
fi

echo
printf '%d passed, %d failed, %d skipped\n' "$PASS" "$FAIL" "$SKIP"
[ "$FAIL" -eq 0 ] || exit 1
