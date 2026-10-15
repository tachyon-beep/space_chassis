#!/bin/sh
# Grant SPACE-20261011-P-01 (master plan §18): one owned selection on tree P, in a capped user scope,
# with the pre-start checks and §17/§18's five-second monitoring and abort thresholds.
# Usage: gate.sh <name> <pytest arguments...>
set -u
name=$1; shift
W=/home/john/space_chassis/.claude/worktrees/vehicle-adoption
E=/home/john/space_chassis/.scratch/phase-b-gates-P-019mkP
P=af671d04908817e914668750b7cd4f6f74034bf4
V=f44399645fb2633e695a5d758cb5a41f43fb848c
LOG=$E/$name.receipt
OUT=$E/$name.log
MON=$E/$name.monitor
unit=space-chassis-p-$name-$(date +%s)
say() { printf '%s %s\n' "$(date -Iseconds)" "$*" >> "$LOG"; }

cpu_busy() {  # percent busy over 2 s, from /proc/stat
    set -- $(head -1 /proc/stat); shift; t1=0; for x in "$@"; do t1=$((t1 + x)); done; i1=$(($4 + $5))
    sleep 2
    set -- $(head -1 /proc/stat); shift; t2=0; for x in "$@"; do t2=$((t2 + x)); done; i2=$(($4 + $5))
    echo $(( (100 * ((t2 - t1) - (i2 - i1))) / (t2 - t1) ))
}
mem_avail_mib() { awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo; }
load1() { cut -d' ' -f1 /proc/loadavg; }

identity() {
    tree=$(git -C "$W" write-tree)
    git -C "$W" update-index -q --refresh
    clean=$(git -C "$W" diff --quiet && echo clean || echo DIRTY)
    vehicle=$(git -C "$W/docs/deep_research/vehicle" rev-parse HEAD)
    vclean=$(git -C "$W/docs/deep_research/vehicle" status --porcelain | wc -l)
    echo "tree=$tree worktree=$clean vehicle=$vehicle vehicle-dirty-paths=$vclean"
    [ "$tree" = "$P" ] && [ "$clean" = clean ] && [ "$vehicle" = "$V" ] && [ "$vclean" = 0 ]
}

say "grant SPACE-20261011-P-01 selection=$name command: python3 -m pytest $*"
id=$(identity); ok=$?; say "before: $id"
[ $ok -eq 0 ] || { say "HOLD: candidate identity is not P"; exit 90; }
mem=$(mem_avail_mib); ld=$(load1); busy=$(cpu_busy)
say "capacity: MemAvailable=${mem}MiB load1=$ld cpu-busy=${busy}%"
others=$(pgrep -af 'pytest' | grep -v "$unit" | grep -E 'space_chassis|space_vehicle' || true)
smoke=$(docker ps --filter label=com.docker.compose.project --format '{{.Label "com.docker.compose.project"}}' | grep -c '^space_chassis_smoke_' || true)
say "competing Space drivers: ${others:-none}; smoke projects running: $smoke"
[ "$mem" -ge 20480 ] || { say "HOLD: MemAvailable < 20 GiB"; exit 91; }
awk "BEGIN {exit !($ld < 12)}" || { say "HOLD: load1 >= 12"; exit 91; }
[ "$busy" -lt 75 ] || { say "HOLD: CPU busy >= 75%"; exit 91; }
[ -z "$others" ] && [ "$smoke" -eq 0 ] || { say "HOLD: a competing Space driver"; exit 92; }

cd "$W" || exit 93
say "start: unit=$unit.scope systemd-run --user --scope -p CPUQuota=200% -p MemoryMax=8G nice -n 19 python3 -m pytest $*"
systemd-run --user --scope --unit="$unit" -p CPUQuota=200% -p MemoryMax=8G \
    nice -n 19 python3 -m pytest "$@" > "$OUT" 2>&1 &
driver=$!
sleep 3
cg=$(systemctl --user show -p ControlGroup --value "$unit.scope")
say "scope readback: cgroup=$cg cpu.max=$(cat /sys/fs/cgroup$cg/cpu.max 2>&1) memory.max=$(cat /sys/fs/cgroup$cg/memory.max 2>&1) nice=$(ps -o ni= -p $(cat /sys/fs/cgroup$cg/cgroup.procs 2>/dev/null | head -1) 2>/dev/null)"

strikes=0; aborted=""
while kill -0 "$driver" 2>/dev/null; do
    mem=$(mem_avail_mib); ld=$(load1); busy=$(cpu_busy)
    procs=$(cat /sys/fs/cgroup$cg/cgroup.procs 2>/dev/null | wc -l)
    cur=$(cat /sys/fs/cgroup$cg/memory.current 2>/dev/null || echo -)
    printf '%s mem=%sMiB load1=%s busy=%s%% scope-procs=%s scope-mem=%s\n' "$(date -Iseconds)" "$mem" "$ld" "$busy" "$procs" "$cur" >> "$MON"
    if [ "$mem" -lt 12288 ]; then aborted="MemAvailable ${mem}MiB < 12 GiB"; fi
    if [ "$busy" -gt 85 ] || awk "BEGIN {exit !($ld > 20)}"; then strikes=$((strikes + 1)); else strikes=0; fi
    [ $strikes -ge 3 ] && aborted="CPU busy >85% or load1 >20 for three samples"
    if [ -n "$aborted" ]; then
        say "ABORT: $aborted; stopping $unit.scope (owned processes only)"
        systemctl --user stop "$unit.scope"
        break
    fi
    sleep 3  # with cpu_busy's 2 s sample: one sample every ~5 s
done
wait "$driver"; rc=$?
left=$(cat /sys/fs/cgroup$cg/cgroup.procs 2>/dev/null | wc -l)
say "end: rc=$rc ${aborted:+aborted} result: $(tail -1 "$OUT")"
id=$(identity); say "after: $id"
say "owned processes left in scope: $left"
exit $rc
