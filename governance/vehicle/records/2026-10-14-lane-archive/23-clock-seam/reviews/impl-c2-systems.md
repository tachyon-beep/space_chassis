# #23 implementation review, candidate 2 — systems

Received 2026-10-12T10:43:21.469Z; saved verbatim (harness indent removed).

---

**#23 candidate 2: short systems check**

I read the diff at 8cb41f28…, the delta at 965cc5c1… and the worktree `v-23-clock`, all read only.

**Verdict: approve.** All four points hold. The documented §8 command has a wrong script path, a one-word fix to make before anyone runs it. Nothing else here blocks.

1. **Prune failure (`console.py:5727-5743`): confirmed.**
   - When an `unlink` fails with anything other than `FileNotFoundError`, the code drops the cache (`ring = None`), records a `prune` failure at the cycle's start tick (`tick − k`), and stops pruning for that cycle.
   - Publication then continues. `mirror()` calls `ring_counts()`, which rescans the directory, so the mirror and `pending.json` are written with counts taken from disk. `held` can then exceed `ring_slots`, which is a true report.
   - If the failure persists, each cycle costs that window one scan and one failure line. The failure list is a bounded deque and docker logs are capped at 10 MB.
   - P3, optional: the `break` means a stuck oldest frame also blocks pruning of newer frames, so the ring keeps growing while the failure lasts. Pre-#23 code had the same behaviour.
     - The realistic trigger is an agent putting a directory where a frame was (`EISDIR`). That heals on the rescan, because the rescan counts only regular files.
     - A regular file that genuinely cannot be deleted needs the immutable attribute, which an agent cannot set. And if the directory itself is not writable, the frame write fails before the prune is reached.
     - Skipping the stuck name and pruning on is a nicety, not a need.

2. **Feasibility gate (`measure_clock.py:474-608`): confirmed.**
   - The verdict now rests only on the realistic cases (`REALISTIC_CASES`: quiet, verdict, verdict_checkpoint, verdict_static). Each must have its worst cycle within the budget and its p99 within 0.8 of it.
   - `static_and_checkpoint` and `combined` only feed `conservative_bound_us` and do not decide the verdict.
   - Both new cases are set up correctly:
     - `verdict_static` runs with N set far away, so no checkpoint. Its setup writes commands and sets `_refresh_next = True`, giving commands, take barriers, write-ahead, the static rewrite and the ring rescan, with no checkpoint.
     - `verdict_checkpoint` runs at N = k, so every cycle crosses and checkpoints. Its setup clears `_refresh_next` before each timed cycle, which suppresses the refresh the previous crossing armed.
   - P3: requiring the worst cycle to fit the budget means a single outlier in 200 samples fails the gate, such as one fsync spike or a GC pause. That is a defensible reading of design §8, and `over_budget` is printed, so John can see that only one sample missed.

3. **§8 instructions and host-load capture (`measure_clock.py:60-90`, `host_load`): confirmed, with one fix needed.**
   - The steps cover stopping the stack, using a one-off `docker compose run --rm --no-deps --entrypoint python3 vehicle …`, checking free space, keeping the output whole and cleaning up leftovers. `host_load` records `getloadavg` and MemAvailable before and after the run. Both read host-wide values inside the container, so they describe the host.
   - **P3, fix before the run:** the command gives the relative path `tools/measure_clock.py`. The vehicle stage inherits the base stage's `WORKDIR /opt/agent` (`Dockerfile.agent`: base `WORKDIR /opt/agent`, vehicle stage `COPY … /opt/vehicle/` with no WORKDIR of its own). As written, Python would look for `/opt/agent/tools/measure_clock.py` and fail. Use `/opt/vehicle/tools/measure_clock.py`, or add `--workdir /opt/vehicle`.
   - Also state that `--state-root /state` assumes the vehicle-adoption shape. Aurora-port's vehicle service mounts no `/state`, and its root filesystem is read-only, so `mkdtemp` would fail there.
   - Because step 1 stops the stack, the host-load capture will show an idle host by construction. The docstring already says the 0.8 margin is the only allowance for a loaded deployment, so this is understood, not a defect.

4. **Second SIGTERM calls `os._exit(143)` (`console.py:2947-2955`): acceptable.**
   - The reason is right: a namespace's PID 1 ignores a default action it has not handled, so restoring `SIG_DFL` and re-raising would have done nothing in the exec shape.
   - Skipping the clean end is the same as a SIGKILL, and every write path is already safe against that:
     - the checkpoint is written atomically, so a half-written one never replaces a good one;
     - an append that was written but not yet fsynced is either a whole row, which replays, or a torn tail, which recovery handles;
     - option B's sweep and recovery handle a take left on disk;
     - a leftover temp file is the same as after SIGKILL.
   - The exit is 143. Under `unless-stopped` that is restarted unless the operator stopped the container.
   - A second SIGINT is still a `KeyboardInterrupt`; that handler is Python-level, so the PID 1 rule does not apply to it.
   - P3, wording only: the docstring cites "a cycle stuck in an fsync". A Python handler runs only between bytecodes, so it cannot interrupt a syscall blocked in the kernel in an uninterruptible wait; only SIGKILL ends that, and only once the syscall returns. What the second signal really ends promptly is a slow stop that is still making progress, such as a long replay or a slow clean end. The docstring should say that.

**Coverage.** I read `Pacer.stop`, `write_frame`'s prune loop with `ring_counts`, the clock section of `measure_clock` (case setup, gate, `host_load`, docstring), and the vehicle stage of `Dockerfile.agent`. I did not re-review fixes 2, 4, 5 and 7 (manifest-authoritative counts, `open_segment` for zero-cycle boots, test 13, the mid-cycle comment); those answer other reviewers' findings.

Files:
- `/home/john/space_chassis/.scratch/wp08-23/candidate-2/23-candidate-2.diff`
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock/tools/console.py`
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock/tools/measure_clock.py`
- `/home/john/space_chassis/Dockerfile.agent`
