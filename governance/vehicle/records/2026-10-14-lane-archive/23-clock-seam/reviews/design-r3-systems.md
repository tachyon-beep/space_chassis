# #23 design review r3 — systems (targeted)

Received 2026-10-12T06:04:25.014Z; saved verbatim (harness indent removed).

---

**#23 design r3: targeted confirmation (systems)**

I reviewed `DESIGN.md` at sha256 ccddc515…af0a, read only, against the r2 diff and against chassis and vehicle source.

**Verdict: approve with changes.** All of my r2 findings and notes are resolved in substance. Three small P2s remain, each a sentence or two of design text, and none needs another full round:
- **R1:** the design's wording would put the ring scan back on every cycle.
- **R2:** no chassis surface can show exit 4 today, so the design's claim that the chassis can tell a backstop from a fault is not yet true.
- **R3:** the per-slug trap forwards SIGTERM but does not wait for the console.

## r2 findings

- **N1 (ring scans): resolved, except for one wording problem (R1).** The design now keeps the held-frame list in memory, prunes by name, computes `held` and `losses` once per publication, reconciles every N ticks, measures a full 3,000-slot ring across ten windows in §8, puts ring size on the revisit list, and adds test 21.
- **N2 (cycle cost): resolved.** Row 1 carries the previous cycle's `prev_cycle_us` and `prev_end_lag_us`. The last cycle's cost goes only in the manifest, a crashed segment reports it as unknown, and test 4 compares the same population of cycles.
  - P3: say that a cycle's "end" includes the cadence checkpoint, not only publication. The checkpoint runs after `publish` (`console.py:3176-3179`), and the next cycle cannot start until it finishes. Ending at publication would under-report checkpoint cycles by about 9 ms and break `start = max(due, previous end)`.
- **N3 (per-slug backstop): resolved.** Without a state directory the backstop rebases the epoch instead of exiting.
- **N4 (exit code): resolved in the vehicle; see R2 for the chassis half.**
  - P3: say where the consecutive-backstop count persists across restarts and what resets it. Every backstop ends the process, so "consecutive" must be read back on resume, from the previous segment's manifest or the checkpoint.
- **N5 (storage): resolved.** About 33,000 files in the 2 GB shared image is now stated, and §8 measures the frame size and the ring's share of the image.
- **N6 (stop and stall parameters): resolved.** The wait cap is 100 ms. A stall is a wait at least 1 s late, or a start-lag jump of at least max(1 s, 10 periods). The handler is installed before recovery. The N = k exception is stated.
  - The handler is also what makes SIGTERM work at all in the `exec` shape. There Python is PID 1, which ignores a signal it has no handler for, so without one `docker stop` waits out the grace period and then sends SIGKILL.
- **N7 (write-ahead fsync): resolved.** §6 and §8 now measure it.
- **My notes: both resolved.**
  - At the cycle reset, pending receipts are moved into `unwritten` rather than discarded.
  - The refusal text now appends only the rows not yet durable: rows 2..j−1 on a write-ahead cycle, nothing when j = 2. The message names the last durable tick, and a failed suffix append is covered.

I also checked the other r3 changes against source, and they hold:
- Rows 2..k repeat the `receipt` counter, which replay's never-decreasing check needs (`:2419-2421`).
- The settle rule "the first boundary at or after the due tick" matches `_settle`'s `tick < due_tick` (`:3627`).
- Write-ahead is triggered whenever `windows` is non-empty.
- Inherited `m`, `k`, `N` come from the newer of the base checkpoint and the last replayed segment header.
- The backstop check runs before any handle is opened or console claimed, so no claimed batch is ever held across it.

## Is exit 4 safe under `restart: unless-stopped`?

**Yes.** Docker restarts on any exit code under that policy unless the operator stopped the container, and 4 is not special to it.
- **No hot loop.** Start lag can only reach 30 s after at least 30 s of wall time since the epoch, and the epoch is reset after recovery. Every backstopped run therefore lasts at least 30 s, which is more than the 10 s docker needs before it resets its restart backoff.
- **No clash with other exit codes.** The console's codes are 0, 3 and, from argparse, 2. The serve script's `exit 44` is a different case (the vehicle missing from the image). The harness's 42–45 belong to agent containers, not this one.
- **No hidden loss.** If the clean-end checkpoint itself fails, the failure is recorded and the resume replays from the older checkpoint plus the record, as for any other clean end.

## New findings

**R1 (P2). "One scan when the handle opens" would bring back a full scan on every cycle.**
- **Evidence:** `cycle()` calls `open_handles()` for every window on every cycle (`console.py:3100-3102`) and closes them all at the end (`:3181-3183`). Taken literally, "when the handle opens" means once per cycle per window: about 30,000 entries per cycle at 3,000 slots and ten windows. That is a quarter of r2's cost, but it is still a per-cycle scan.
- **Fix:** scan at boot, after a `repair`, and on the reconcile every N ticks. Add one more trigger: the opened `telemetry/` directory's identity (`st_dev`, `st_ino`) differs from the last cycle's. An agent that replaces `telemetry/` with a fresh directory does not trigger `WindowAbsent`, so without that check the in-memory list would stay stale for up to N ticks. That is harmless to prune, since `FileNotFoundError` is suppressed, but `held` would be wrong.
- Test 21 should cover "replaced directory" as well as "deleted frames".

**R2 (P2). No chassis surface can see exit 4 or `lag_backstop` today.**
- **Evidence:** `scripts/status.py:105-121` and `scripts/journal.py:544-562` inspect only agent services: `.State.Status` and `.RestartCount`. The journal keeps only log lines that match the agent watchdog's pattern. None of them looks at the `vehicle` service. The `lag_backstop` event lands in the vehicle's private `/state` record, which no operator surface mounts.
- **Exit code is the wrong signal:** I believe, but have not checked, that docker resets `.State.ExitCode` to 0 when it restarts a container, so an inspect taken after an automatic restart would not show the 4.
- **Fix:** do either of these:
  - The backstop also prints a fixed-format stderr line in both shapes, e.g. `[console] lag_backstop lag_s=… consecutive=…`. `docker compose logs vehicle` keeps it (logging is capped at 10 MB). Add to §7's chassis touch points: `status.py` and `journal.py` also report the `vehicle` service's restart count and that line.
  - The chassis reads `docker events` `die` events, which carry `exitCode`.

  Until one of these lands, the design should not say the chassis can tell a backstop from a fault.

**R3 (P2). The per-slug trap forwards SIGTERM but exits before the consoles finish.**
- **Evidence:** `containers/serve_vehicle.sh:124-125` on aurora-port is `trap 'kill $PIDS 2>/dev/null || true' TERM INT` followed by `wait`. In POSIX sh a trapped signal interrupts `wait`. The trap sends the kill, the script then reaches its end, and the shell, which is PID 1, exits. When PID 1 exits, the kernel kills every remaining process in the container immediately, so each console's graceful finish-the-cycle path is cut short. That shape has no record, so a batch claimed in that cycle is lost: the r1 P2-2 scenario again.
- **Fix:** have the trap wait for the consoles too, e.g. `trap 'kill $PIDS 2>/dev/null || true; wait' TERM INT`, and state it in §7. The `exec` shape is unaffected.

## Coverage

- **Read:** the r2→r3 diff, including §11; `console.py`'s per-cycle open and close of handles (`:3100-3102`, `:3181-3183`) and `_settle`; the chassis `scripts/status.py`, `scripts/journal.py`, `services/` (which do not mention the vehicle service) and aurora-port's `serve_vehicle.sh`.
- **Not run:** nothing, as asked. The docker behaviour cited in R2 is stated from knowledge of docker, not observed.

## Files

- `/home/john/space_chassis/.scratch/wp08-23/DESIGN.md`
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9/tools/console.py`
- `/home/john/space_chassis/containers/serve_vehicle.sh`
- `/home/john/space_chassis/scripts/status.py`
- `/home/john/space_chassis/scripts/journal.py`
