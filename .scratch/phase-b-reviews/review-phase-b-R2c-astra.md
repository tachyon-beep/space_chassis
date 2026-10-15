**land**

**Critical:** None.

**Important:** None in the R2c delta. The pipe-EOF defect is fixed in [live/stack.py:172](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/live/stack.py:172): output goes to temporary files, and `wait(timeout)` observes only the leader. The `finally` kills the group before output is read, including on timeout or `KeyboardInterrupt`.

**Minor:**

- **Timing-dependent tests:** [tests/test_live_stack.py:714](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/tests/test_live_stack.py:714) allows only one second for child startup; line 730 measures startup and scheduling within the 1.5-second prompt-return limit. Both can fail on a heavily loaded host despite correct cleanup. The readiness handshake improves validity but does not remove those scheduling assumptions.
- **Timeout diagnostics regress:** `wait()` raises `TimeoutExpired` without captured stdout/stderr; exception propagation then closes the temporary files ([live/stack.py:177](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/live/stack.py:177)). This loses diagnostic output, but does not compromise cleanup or the current caller’s assertions.

Other requested checks: context managers close both files on exceptional paths, including failed `Popen`; text-mode temporary files are valid subprocess destinations, with `seek(0)` preparing their subsequent reads. Repeated `wait()` safely returns the cached status. An already-vanished group produces the suppressed `ProcessLookupError`. A single interrupt during the first wait reaches cleanup; repeated interrupts can still interrupt cleanup. The narrow PGID-reuse race after leader reaping already existed in R2b. Output remains unbounded: capture now consumes temporary storage, and successful completion still reads everything into memory.

The tests preserve inherited stdout/stderr, establish readiness, check child termination, and retain the no-late-action assertion ([tests/test_live_stack.py:700](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/tests/test_live_stack.py:700)). No substantive assertion is weakened; reducing the final sleep to 2.5 seconds still exceeds the child’s two-second delay.

Verified the delta hash, staged-index equality, vehicle pin, and two-file scope. Read-only source review; no tests, builds, containers, or `.env` reads. Owner control results were supplied evidence, not independently reproduced.