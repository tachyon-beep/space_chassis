**Land after fixes.** R fixes most candidate-4 defects, but the shared reservation and single-sweep budget still have gaps. References below are to tree `dd16772e`.

**Critical:** None found.

**Important**

- **The lock is not shared consistently across sessions.** [live/stack.py:92](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/live/stack.py:92) selects either `$XDG_RUNTIME_DIR` or `/tmp`. Same-user sessions with different environments acquire different locks; both post-build checks can finish before either `up()` at lines 434–435. Concurrent builds and stacks therefore remain possible. Use one canonical per-user location. The fallback also uses a global filename with mode `0600`, preventing another UID from opening it after its creator exits. `O_NOFOLLOW` correctly rejects symlinks.

- **One sweep at a time is only guaranteed on the normal path.** [verify_containment.sh:260](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/scripts/verify_containment.sh:260) correctly requests CPU, memory and swap limits, and its loop is synchronous. However, concurrent script invocations have no sweep reservation. More significantly, the 900-second shell timeout in `live/test_containment.py:16–23` does not guarantee cleanup of its child Docker client/container. An orphan sweep has neither a Compose project label nor tracked teardown, so it can survive stack shutdown and overlap another sweep undetected. Track and clean up sweeps, and serialize their lifetime. Their actual cgroup limits also receive no runtime readback; `tests/test_live_stack.py:402–407` checks command text only.

**Minor**

- **The scope check rejects valid inherited caps.** [live/conftest.py:69](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/live/conftest.py:69) reads only the leaf returned by `own_cgroup()`. A leaf containing `max` beneath a sufficiently capped ancestor is refused despite kernel enforcement. Walk the v2 ancestors; [kernel documentation](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html) establishes hierarchical enforcement. The documented direct `systemd-run --scope` invocation avoids this particular problem.

**Candidate-4 disposition and gate impact**

- **Template fixed:** `.Label` plus the label filter is correct (`live/stack.py:379–386`). I executed the corrected template against existing containers successfully.
- **Reservation partly fixed:** acquisition precedes prepare/build; both daemon checks exist. Separate opens contend even within one process under [Linux flock semantics](https://man7.org/linux/man-pages/man2/flock.2.html). The remaining defect is lock identity above.
- **Build/overhead claims corrected:** builds are serial (`live/stack.py:350–355`); README:218–222 explicitly excludes builds and daemon work from enforcement. No privileged builder or aggregate build-cap claim was introduced.
- **Evidence teardown fixed:** `_only` uses `finally` (`live/conftest.py:56–63`). Fixture ordering, vehicle-only selections, normal atexit cleanup and `recreate()` retaining cap overrides appear sound.
- **Host-side reads corrected:** `live/stack.py:395–405` uses the full container ID and the [documented systemd/v2 default path](https://docs.docker.com/engine/containers/runmetrics/). Restart-time disappearance can still fail setup; it cannot falsely pass.
- **Caps rebalanced without weakening assertions:** review receives 0.25 CPU; stack totals are 4.4 CPUs/12 GiB. Runtime adequacy remains untested. The `after is None` correction belongs to P.

No out-of-scope changes found. Saved-diff SHA-256 matched. Docker reported systemd/v2. No tests, builds, containers, file changes or `.env` reads performed.

