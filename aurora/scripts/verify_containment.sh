#!/bin/sh
# Check the world's safety properties against a running stack: one container per agent, each with
# its own recorder on a network the agent cannot see.
#
# Read this as a list of the claims the design makes, each turned into a command that either
# succeeds or does not. It is deliberately shallow: it does not try to prove an agent cannot
# escape, it checks that the walls are where the documentation says they are.
#
#   sh scripts/verify_containment.sh                    # every running agent_*
#   AGENTS="agent_1 agent_4" sh scripts/...             # chosen agents
#   COMPOSE="docker compose -p <project> --env-file <file> -f <a> -f <b>" sh scripts/...
#
# COMPOSE is the whole compose command prefix, so the script checks whichever project it names (the
# smoke stack in live/stack.py passes its own). It is split on spaces, so no path in it may
# contain one. `--all` is accepted and ignored: every running agent is the default now.
#
# The real key is the one secret here. It never enters an agent's container -- the agent is what is
# contained, and a key piped into a process there is a key handed to a same-uid reader of that
# process -- and it is never held in a shell variable, passed as an argument or printed. The agent's
# files come out as a tar stream, and a host-side search reads the key from `docker inspect` itself.
#
# Every check fails closed. A negative probe ("cannot connect", "cannot unlink") prints a verdict
# word from inside the container, and only that word passes: an exec that did not run, or ran and
# said nothing, is a FAIL, never evidence that the wall holds.
set -u

PROJECT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT"

: "${COMPOSE:=docker compose}"
# Where an agent can write, and /etc: every place a leaked key could come to rest.
KEY_PATHS="/work /state /shared /pump /build /telemetry /llm/console /diode /home /etc"
PEER_PORT=9099

PASS=0
FAIL=0
SKIP=0

ok()   { PASS=$((PASS + 1)); printf '  PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL + 1)); printf '  FAIL  %s\n' "$1"; }
skip() { SKIP=$((SKIP + 1)); printf '  SKIP  %s\n' "$1"; }

[ "${1:-}" = "--all" ] && shift

if ! $COMPOSE ps --format '{{.Service}}' >/dev/null 2>&1; then
    echo "no compose project here; is the stack up?" >&2
    exit 2
fi

: "${AGENTS:=$($COMPOSE ps --format '{{.Service}}' 2>/dev/null | grep '^agent_' | sort -t_ -k2,2n -u)}"

in_agent() {
    agent=$1
    shift
    $COMPOSE exec -T "$agent" "$@"
}

# A probe's verdict: the last line it printed, or nothing if it could not run.
verdict() {
    agent=$1
    shift
    $COMPOSE exec -T "$agent" "$@" 2>/dev/null | tail -n 1
}

# Search stdin (a tar stream of an agent's files) for the recorder's credentials. The key is read
# here, on the host, from `docker inspect`; it is never in this shell. Exit 0 found, 1 searched a
# whole archive and clean, 2 nothing (or not all of it) to search, or no key to search for.
search_for_key() {
    python3 -c '
import subprocess, sys
env = subprocess.run(
    ["docker", "inspect", "--format", "{{range .Config.Env}}{{println .}}{{end}}", sys.argv[1]],
    capture_output=True,
).stdout.decode(errors="replace")
keys = []
for line in env.splitlines():
    name, _, value = line.partition("=")
    if name in ("OPENROUTER_API_KEY", "LLM_API_KEY") and value:
        keys.append(value.encode())
if not keys:
    sys.exit(2)
keep = max(map(len, keys)) - 1
tail, last, total = b"", b"", 0
while chunk := sys.stdin.buffer.read(1 << 20):
    total += len(chunk)
    window = tail + chunk
    if any(key in window for key in keys):
        sys.exit(0)
    tail = window[-keep:] if keep else b""
    last = (last + chunk)[-1024:]
# A whole archive ends in two zero blocks; a stream cut off mid-way has not been searched.
sys.exit(1 if total and last == bytes(1024) else 2)
' "$1"
}

recorder_has_key() {
    docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$1" 2>/dev/null \
        | grep -q -e '^OPENROUTER_API_KEY=.' -e '^LLM_API_KEY=.'
}

CHECKED=0
for agent in $AGENTS; do
    echo "== $agent"
    cid=$($COMPOSE ps -q "$agent" 2>/dev/null)
    if [ -z "$cid" ]; then
        skip "$agent is not running"
        continue
    fi
    CHECKED=$((CHECKED + 1))
    recorder="recorder_${agent#agent_}"

    # 1. No outward route. The connection is authoritative: a bridge always has a gateway line,
    #    which proves nothing, and resolution failing is reported but is not the wall.
    case $(verdict "$agent" python3 -c '
import socket
try:
    socket.create_connection(("1.1.1.1", 443), 3)
except OSError:
    print("blocked")
else:
    print("connected")') in
        blocked) ok "$agent cannot open a connection outward" ;;
        connected) bad "$agent opened a connection to a public address" ;;
        *) bad "$agent could not be probed for an outward connection" ;;
    esac
    case $(verdict "$agent" sh -c 'timeout 5 getent hosts example.com >/dev/null 2>&1; echo "rc=$?"') in
        rc=0) bad "$agent resolved a public name" ;;
        rc=126 | rc=127) bad "$agent could not be probed for name resolution" ;;
        rc=*) ok "$agent cannot resolve outside names" ;;
        *) bad "$agent could not be probed for name resolution" ;;
    esac

    # 2. The agent's own key is the dummy.
    if in_agent "$agent" sh -c 'tr "\0" "\n" < /proc/1/environ' 2>/dev/null | grep -qx 'OPENROUTER_API_KEY=sk-dummy'; then
        ok "$agent carries the dummy key"
    else
        bad "$agent does not carry the dummy key"
    fi

    # 3. The recorder's real key is nowhere the agent can see. The search runs on the host.
    rcid=$($COMPOSE ps -q "$recorder" 2>/dev/null)
    if [ -z "$rcid" ]; then
        skip "$recorder is not running, so there is no real key to look for"
    elif ! recorder_has_key "$rcid"; then
        skip "$recorder carries no key, so there is nothing to leak"
    else
        $COMPOSE exec -T "$agent" tar -cf - --ignore-failed-read $KEY_PATHS 2>/dev/null \
            | search_for_key "$rcid" >/dev/null 2>&1
        case $? in
            0) bad "$agent holds its recorder's real key on disk" ;;
            1) ok "$agent has no trace of its recorder's real key" ;;
            *) bad "$agent could not be searched for its recorder's real key" ;;
        esac
    fi

    # 4. The recorder's socket answers and cannot be replaced: the directory is a read-only bind.
    if in_agent "$agent" python3 -c 'import socket; s = socket.socket(socket.AF_UNIX); s.connect("/llm/sock/core.sock")' >/dev/null 2>&1; then
        ok "$agent reaches its recorder's socket"
    else
        bad "$agent cannot connect to /llm/sock/core.sock"
    fi
    case $(verdict "$agent" python3 -c '
import os
try:
    os.unlink("/llm/sock/core.sock")
except OSError:
    print("refused")
else:
    print("unlinked")') in
        refused) ok "$agent cannot unlink its recorder's socket" ;;
        unlinked) bad "$agent unlinked its recorder's socket" ;;
        *) bad "$agent could not be probed for unlinking its recorder's socket" ;;
    esac

    # 5. No sibling surface: the only window and socket mounts are its own, and neither the record
    #    nor the fleet ledger is mounted at all.
    mounts=$(in_agent "$agent" sh -c 'awk "{ print \$2 }" /proc/self/mounts' 2>/dev/null)
    slug=$(in_agent "$agent" sh -c 'printf %s "$AGENT_SLUG"' 2>/dev/null)
    windows=$(printf '%s\n' "$mounts" | grep '^/diode' | tr '\n' ' ')
    if [ -n "$slug" ] && [ "$windows" = "/diode/$slug " ]; then
        ok "$agent mounts only its own window, /diode/$slug"
    else
        bad "$agent's window mounts are '${windows}', not /diode/${slug:-<no slug>} alone"
    fi
    sockets=$(printf '%s\n' "$mounts" | grep '^/llm/sock' | tr '\n' ' ')
    if [ "$sockets" = "/llm/sock " ]; then
        ok "$agent mounts only its own recorder's socket directory"
    else
        bad "$agent's socket mounts are '$sockets', not /llm/sock alone"
    fi
    entries=$(in_agent "$agent" ls -A /diode 2>/dev/null)
    if [ -n "$slug" ] && [ "$entries" = "$slug" ]; then
        ok "$agent sees nothing under /diode but its own window"
    else
        bad "$agent's /diode holds '$entries', not ${slug:-<no slug>} alone"
    fi
    # The window root is the vehicle's: an agent writes only inside its own window.
    # A missing `touch` says nothing, which fails: only a write that was tried and refused passes.
    case $(verdict "$agent" sh -c 'command -v touch >/dev/null 2>&1 || exit 0; if touch /diode/.probe 2>/dev/null; then rm -f /diode/.probe; echo wrote; else echo refused; fi') in
        refused) ok "$agent cannot write the window root" ;;
        wrote) bad "$agent can write the window root" ;;
        *) bad "$agent could not be probed for writing the window root" ;;
    esac
    # The vehicle's private state (checkpoints, lock, durable record: hidden truth) is bound into
    # no agent. Read host-side: the agent's own /state makes a target check from inside useless.
    sources=$(docker inspect -f '{{range .Mounts}}{{.Source}} {{end}}' "$($COMPOSE ps -q "$agent" 2>/dev/null)" 2>/dev/null)
    if [ -z "$sources" ]; then
        bad "$agent's mounts could not be inspected"
    elif printf '%s ' "$sources" | grep -qE '/vehicle_state(/| )'; then
        bad "$agent mounts the vehicle's private state"
    else
        ok "$agent mounts nothing of the vehicle's private state"
    fi
    # Nor its source (John, 2026-10-10: no risk of information sharing). The image carries none of
    # it (6b), so a bind is the one way back: any mount from inside a vehicle checkout, or of a
    # directory that holds this one's (the repository, docs/, ...). Read from the same sources.
    if [ -z "$sources" ]; then
        bad "$agent's mounts could not be inspected for the vehicle's source"
    else
        exposed=""
        for source in $sources; do
            case "$source/" in */deep_research/vehicle/*) exposed=$source ;; esac
            case "$PROJECT/docs/deep_research/vehicle/" in "${source%/}"/*) exposed=$source ;; esac
        done
        if [ -n "$exposed" ]; then
            bad "$agent mounts the vehicle's source ($exposed)"
        else
            ok "$agent mounts nothing of the vehicle's source"
        fi
    fi
    for private in /transcripts /ledger; do
        if ! printf '%s\n' "$mounts" | grep -qx /; then
            bad "$agent's mount table could not be read, so $private is unchecked"
        elif printf '%s\n' "$mounts" | grep -q "^$private\(/\|$\)"; then
            bad "$agent has $private mounted"
        else
            ok "$agent has no $private mount"
        fi
    done

    # 6. Its own Postgres answers. The versioned binary, as the entrypoint uses it: the /usr/bin
    #    wrapper wants /etc/postgresql, which this image never configures.
    if in_agent "$agent" sh -c 'for b in /usr/lib/postgresql/*/bin/pg_isready; do "$b" -q -h /run/agent && exit 0; done; exit 1' >/dev/null 2>&1; then
        ok "$agent's own postgres answers"
    else
        bad "$agent's postgres does not answer on /run/agent"
    fi

    # 6b. Nothing of the vehicle in the agent's image (John, 2026-10-10: no risk of information
    #     sharing): no /opt/vehicle, no serve script, and none of the vehicle's files by name. The
    #     agent's root is read-only, so its filesystem outside its mounts is its image, and the image
    #     is swept from the host side: as root, in a throwaway container with no network, so no
    #     directory the agent cannot list can hide a file it could still open. The search must
    #     complete (find exits 0) and find a sentinel every image has, the entrypoint: the sentinel
    #     alone is absent, the sentinel and anything else present, and anything else fails.
    image=$(docker inspect -f '{{.Image}}' "$($COMPOSE ps -q "$agent" 2>/dev/null)" 2>/dev/null)
    sweep=""
    swept=1
    if [ -n "$image" ]; then
        sweep=$(docker run --rm --network none --user 0 --entrypoint find "$image" / -xdev \( -path /usr/local/bin/entrypoint.sh -o -path /opt/vehicle -o -name serve_vehicle.sh -o -name mission.yaml -o -name vehicle.yaml -o -name coupling.yaml -o -name plant.md -o -name fault_policy.yaml \) -print 2>/dev/null)
        swept=$?
    fi
    if [ "$swept" -ne 0 ]; then
        bad "$agent could not be probed for the vehicle"
    elif [ "$sweep" = /usr/local/bin/entrypoint.sh ]; then
        ok "$agent has no vehicle in its image"
    else
        case "$sweep" in
            *"/usr/local/bin/entrypoint.sh"*) bad "$agent can read the vehicle" ;;
            *) bad "$agent could not be probed for the vehicle" ;;
        esac
    fi

    # 7. No recorder is reachable by name: they live on modelnet, which no agent joins.
    case $(verdict "$agent" sh -c "timeout 5 getent hosts $recorder >/dev/null 2>&1; echo rc=\$?") in
        rc=0) bad "$agent can resolve $recorder" ;;
        rc=126 | rc=127) bad "$agent could not be probed for resolving $recorder" ;;
        rc=*) ok "$agent cannot resolve $recorder" ;;
        *) bad "$agent could not be probed for resolving $recorder" ;;
    esac
done

# 8. The fleet can reach each other on worknet, because a control layer needs somewhere to run:
#    this is the property that must NOT be sealed.
set -- $AGENTS
if [ $# -ge 2 ]; then
    listener=$1
    caller=$2
    echo "== $caller reaches $listener on worknet"
    if $COMPOSE exec -d "$listener" nc -lk "$PEER_PORT" >/dev/null 2>&1; then
        reached=no
        for _ in 1 2 3 4 5; do
            if in_agent "$caller" nc -z -w3 "$listener" "$PEER_PORT" >/dev/null 2>&1; then
                reached=yes
                break
            fi
            sleep 1
        done
        if [ "$reached" = yes ]; then
            ok "$caller reached a listener on $listener:$PEER_PORT"
        else
            bad "$caller could not reach a listener on $listener:$PEER_PORT"
        fi
        in_agent "$listener" pkill -f "nc -lk $PEER_PORT" >/dev/null 2>&1
    else
        bad "could not start a listener on $listener"
    fi
fi

echo "== the vehicle binds its window and its state"
vehicle=$($COMPOSE ps -q vehicle 2>/dev/null)
if [ -z "$vehicle" ]; then
    skip "the vehicle is not running"
else
    binds=$(docker inspect -f '{{range .Mounts}}{{if eq .Type "bind"}}{{.Destination}} {{end}}{{end}}' "$vehicle" 2>/dev/null \
        | tr ' ' '\n' | sed '/^$/d' | sort | tr '\n' ' ' | sed 's/ $//')
    if [ "$binds" = "/diode /state" ]; then
        ok "the vehicle binds /diode and /state and nothing else"
    elif [ -z "$binds" ]; then
        bad "the vehicle's binds could not be inspected"
    else
        bad "the vehicle binds '$binds', not /diode and /state alone"
    fi
fi

echo "== the review panel reads and does not write"
if [ -z "$($COMPOSE ps -q review 2>/dev/null)" ]; then
    skip "the review panel is not running"
else
    # It must have no route out and no view of a recorder.
    case $(verdict review python3 -c '
import socket
try:
    socket.create_connection(("1.1.1.1", 443), 3)
except OSError:
    print("blocked")
else:
    print("connected")') in
        blocked) ok "the review panel has no route outward" ;;
        connected) bad "the review panel reached a public address" ;;
        *) bad "the review panel could not be probed for an outward connection" ;;
    esac
    case $(verdict review sh -c 'timeout 4 getent hosts recorder_1 >/dev/null 2>&1; echo "rc=$?"') in
        rc=0) bad "the review panel can see a recorder" ;;
        rc=126 | rc=127) bad "the review panel could not be probed for seeing a recorder" ;;
        rc=*) ok "the review panel cannot see a recorder" ;;
        *) bad "the review panel could not be probed for seeing a recorder" ;;
    esac
    # Its mounts are read-only, so the record cannot be amended from here.
    for record in /transcripts /telemetry; do
        case $(verdict review sh -c "if touch $record/.probe 2>/dev/null; then rm -f $record/.probe; echo wrote; else echo refused; fi") in
            refused) ok "the review panel cannot write to $record" ;;
            wrote) bad "the review panel can write to $record" ;;
            *) bad "the review panel could not be probed for writing to $record" ;;
        esac
    done
    # And it can read: a panel that is sealed out of its own subject is useless.
    if $COMPOSE exec -T review test -d /transcripts >/dev/null 2>&1; then
        ok "the review panel can read the transcripts"
    else
        bad "the review panel cannot see the transcripts"
    fi

    # The compose file asks for a loopback binding. Whether the daemon granted it is a separate
    # question: an environment whose Docker does not forward published ports leaves the mapping
    # inert, and inert is not exposed, so the check fails only on a binding that is explicitly not
    # loopback.
    ports=$($COMPOSE ps review --format '{{.Ports}}' 2>/dev/null)
    if [ -z "$ports" ]; then
        skip "the review panel has no port mapping"
    elif printf '%s' "$ports" | grep -qE '(^|[^0-9.])(0\.0\.0\.0|\[::\]|\*)'; then
        bad "the review panel is bound to every host interface: $ports"
    elif printf '%s' "$ports" | grep -q '127.0.0.1'; then
        ok "the review panel is bound to host loopback: $ports"
    else
        skip "the panel's port is mapped but not listening on the host ($ports)"
    fi
fi

echo
printf '%d passed, %d failed, %d skipped\n' "$PASS" "$FAIL" "$SKIP"
# A run that reached no agent checked none of the walls: that is not a pass.
if [ "$CHECKED" -eq 0 ]; then
    echo "no agent container was checked; is the fleet up?" >&2
    exit 2
fi
[ "$FAIL" -eq 0 ] || exit 1
