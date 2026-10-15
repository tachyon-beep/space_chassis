**Land after fixes.** R2 fixes several R findings, but leaves a timeout/cleanup race and introduces two deterministic test failures. All source references below are to `0471251`.

**Critical:** None found.

**Important**

1. **A timed-out probe can launch a sweep after teardown.** The 900-second calls kill only the top-level shell (`live/test_containment.py:15–22`, `live/test_vehicle.py:185–192`). The substitution subshell in [verify_containment.sh:264](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/scripts/verify_containment.sh:264) can survive waiting for `flock`, then launch Docker later. Meanwhile, `live/stack.py:528–542` can observe no containers and mark teardown complete. Labels and current-container inventories do not fence this future launch. Cancel and join probe descendants before cleanup, or provide equivalent launch fencing. This leaves the orphan-sweep finding incompletely fixed.

2. **Sweep inventory fails open.** At [verify_containment.sh:267](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/scripts/verify_containment.sh:267), `[ -z "$(docker ps …)" ]` discards Docker’s exit status. A failed listing with empty stdout permits a sweep despite an existing orphan. Check listing success separately. The stub always returns success for this query (`tests/test_verify_containment.py:33–34`).

3. **Two root tests necessarily raise `StopIteration`.** [test_live_stack.py:405](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/tests/test_live_stack.py:405) and line 651 still select `--entrypoint find`; R2 uses `--entrypoint sh` (`scripts/verify_containment.sh:268`). Update both selectors while preserving their cap and label assertions.

**Minor**

- `down()` removes only running sweeps (`live/stack.py:528–533`), but rejects stopped leftovers too (`554–559`). A stopped residual therefore remains through every retry. Include stopped sweeps in removal.

The remaining fixes are sound by inspection:

- Canonical per-user smoke lock and missing-directory refusal: `live/stack.py:94,452–464`. Ancestor limits, `0::` selection and swap-zero requirement: `121–143`; `live/conftest.py:66–76`. Documentation corrections and their five-document guard are present (`tests/test_live_stack.py:411–425`).
- FD 9 remains open in the substitution subshell throughout the foreground Docker call: `flock` returning does **not** release that lock. The daemon container does not inherit it; labels cover already-running orphans, subject to the defects above.
- Docker reports **systemd / cgroup v2** on this host. Under private cgroup namespaces, the readback paths are appropriate; `20000 100000|268435456|0` matches the requested flags. This follows Docker’s [namespace documentation](https://docs.docker.com/engine/containers/runmetrics/) and [resource semantics](https://docs.docker.com/engine/containers/resource_constraints/), not an executed sweep.
- Offline tests invoke the real script and `flock`, but fabricate cgroup output and exercise `find` separately (`tests/test_verify_containment.py:48–49,91–98,265–305`). They do not establish container enforcement or timeout cleanup.
- `_only()` prevents replacement after failed teardown (`live/conftest.py:56–63`). Detected leftovers retain the root for retry; successful cleanup makes finalizers/atexit harmless. Evidence-collection exceptions can bypass fixture `down()`, leaving atexit as fallback (`145–161`).

Existing containment verdict assertions remain intact. No vehicle #39, product, host/security, scheduler or privileged-builder changes found; README explicitly excludes build/daemon enforcement.

Both supplied diff hashes matched. No tests, builds, containers, edits, Git changes or `.env` reads performed. Live qualification remains outstanding.

