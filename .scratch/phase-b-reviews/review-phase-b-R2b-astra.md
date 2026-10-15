**Land after fixes — R2b introduces one Important blocker.**

**Critical:** None found.

**Important — normal-exit cleanup happens too late.** [live/stack.py:179](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/live/stack.py:179) calls `communicate()` before killing stragglers. It waits for EOF on both pipes. The background subshell in [tests/test_live_stack.py:701](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/tests/test_live_stack.py:701) inherits those pipes, sleeps, then creates `late` before closing them. Cleanup therefore follows the forbidden action; assertion 708 fails under ordinary execution. This is a source-established failure, not merely flaky timing. Observe leader exit while draining output, then kill descendants before awaiting their pipe EOF. Redirecting the test’s pipes would hide this defect.

**Minor — timing-dependent timeout test.** [tests/test_live_stack.py:685](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/tests/test_live_stack.py:685) lacks a child-ready handshake and relies on 0.5/2/3-second delays. Host scheduling can cause false failures or let it pass without establishing that the background child started. Synchronize readiness and verify child termination.

The remaining fixes are correct by inspection:

- Both sweep selectors now match the actual command; the readback assertion derives from `SWEEP_CPUS`/`SWEEP_MEMORY` ([tests/test_live_stack.py:404](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/tests/test_live_stack.py:404), lines 651–660).
- Listing failure exits 77 before launch; 120-second lock waits and distinct 75/76/77 explanations preserve the failure prefix ([verify_containment.sh:264](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/scripts/verify_containment.sh:264)). The new stub test checks refusal and absence of a launch.
- Teardown includes stopped sweeps and allows ongoing removal to settle ([live/stack.py:567](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/live/stack.py:567)). The lock assertion is strengthened; `_labelled`’s unused parameter is removed.

Process semantics at [live/stack.py:165](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/live/stack.py:165): the new session isolates the script’s process group. Ordinary `$(...)` subshells, `flock`, pipelines and Docker clients inherit it. Timeout or `KeyboardInterrupt` during `communicate()` kills the group, drains/reaps, and re-raises; a second interrupt can interrupt cleanup. `killpg` works after leader exit while descendants retain the group. After complete group disappearance and leader reaping, numeric PGID reuse leaves a theoretical unrelated-group kill race.

Docker containers are outside that group. Labels plus teardown cover visible running/stopped sweeps. They do **not** establish cancellation of an in-flight daemon create: an initially empty leftover scan ends polling immediately (lines 577–584). That late-create scenario remains unverified.

Both live callers use the 900-second wrapper without weakening their acceptance assertions. No privileged builder, daemon/host/security/access change, scheduler, or #39 contract change appeared.

Verified both supplied hashes, staged-tree equality and vehicle HEAD. Git-object/stdlib inspection only; no tests, builds, containers, writes or `.env` reads. Live qualification remains pending its separate grant.