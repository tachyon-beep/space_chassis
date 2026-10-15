# #23 implementer report, candidate 2

Received 2026-10-12T10:41:26.121Z; saved verbatim (harness indent removed).

---

## #23 candidate 2: report

Candidate 2 is done in the same worktree (`/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock`), uncommitted. All three required fixes and all five P3 items are in. As before, the only things run were `py_compile` and `ruff check`; nothing was committed, stashed or pushed. Each fix is logged in `/home/john/space_chassis/.scratch/wp08-23/IMPLEMENTATION-LOG.md` under "Candidate 2".

### git diff --stat 7a87eb82
```
 README.md                                          |   83 +-
 .../decisions/0002-mission-clock-and-continuity.md |  117 +-
 tests/test_vehicle_config.py                       | 1699 ++++++++++++++++++--
 tools/check_vehicle.py                             |   77 +-
 tools/checkpoint.py                                |  140 +-
 tools/console.py                                   | 1366 +++++++++++++---
 tools/generate_help.py                             |    4 +-
 tools/generate_readme.py                           |    4 +-
 tools/measure_clock.py                             |  363 ++++-
 9 files changed, 3486 insertions(+), 367 deletions(-)
```
Referee tests: 537 → 564.

### Fixes
1. **Second SIGTERM for PID 1** (`tools/console.py:2955`, `Pacer.stop`). A second SIGTERM now writes `[console] a second SIGTERM: stopping now, without a clean end` to stderr, flushes it, and calls `os._exit(128 + SIGTERM)`, which is 143. The docstring explains why the default action is not used: a namespace's PID 1 ignores a default action it has not handled. A second SIGINT still raises `KeyboardInterrupt`. The test now asserts exit 143 and the stderr line (tests:32522).
2. **The manifest's counts are authoritative** (`console.py:3097`, `segment_summaries`).
   - A segment with a manifest takes its stall and backstop counts from the manifest.
   - A crashed segment reports the journaled counts and adds `"counts": "journaled"` to mark them as a lower bound.
   - Test 4 (:31437) expects that marker on the crashed segment and exact equality with the manifest on the clean one.
   - The rolled-back backstop-write test (:32357) now asserts reader == manifest even though the event was lost.
   - Test 20 already compared reader with manifest and needed no change.
3. **Feasibility gate** (`tools/measure_clock.py`).
   - Two new cases: `verdict_static` (commands plus the static rewrite) and `verdict_checkpoint` (commands plus a checkpoint).
   - `REALISTIC_CASES` (:478) is quiet, verdict, verdict_checkpoint and verdict_static.
   - The run fits only if, in every realistic case, the worst cycle ≤ budget **and** p99 ≤ 0.8 · budget (:591).
   - `static_and_checkpoint` and `combined` are reported as `conservative_bound_us`, labelled as not deciding the verdict at N > k.
   - The rule is stated in the module docstring and in `clock_cycle_costs`'s docstring.
4. **Zero-cycle boots.** I chose to write the header first, via `Executive.open_segment` (`console.py:3637`), called on every clean end before the clean-end checkpoint (:6710). This keeps the record's rules simplest:
   - a header-only segment is already a shape every reader accepts (a torn first cycle leaves one), so no new rule;
   - every manifest then belongs to a segment;
   - the reader never has to list files outside the record.

   New test: `test_a_boot_that_backstops_in_its_first_wait_leaves_a_header_only_segment_its_manifest_belongs_to` (:32532). It checks the reader's summary equals the manifest's (0 cycles, 1 stall, 1 backstop) and that the next boot continues from that segment.
5. **Test 13** (:31880). The step wrapper reads `mode` the way `plant.state_level` does (the flat key first). It moves both the flat `mode` (when present) and `internal.mode`, and is still a pure function of its arguments.
6. **Ring prune failure** (`console.py:5741`). A persistent `unlink` failure drops the cache, is recorded as a `prune` failure at the cycle's start tick, and the publication carries on: the mirror and `pending.json` are still written, with counts from a rescan. The ring test (:32307) is renamed and now asserts the `prune` failure, one rescan in the same publication, held 4 / losses 0 at tick 4, and the prune at tick 5 with no further scan.
7. **Mid-cycle premise** (`console.py:1597`). A comment at the skip now says every anchor sits at a cycle boundary (genesis, cadence and clean-end checkpoints, or a dead segment's end), so the skip exists only because the read has no first row.
8. **§8 instructions** (`measure_clock.py:73`). The documented steps now cover:
   - running with the stack stopped, via `docker compose run --rm --no-deps --entrypoint python3 vehicle …`;
   - checking free space first (about frame bytes × 3,000 × 10);
   - keeping the output whole and removing leftovers from an interrupted run.

   `host_load` (:481) captures `os.getloadavg()` and MemAvailable before and after the section, and both are printed.

The README round entry and ADR 0002 (xlvi) are updated for fixes 1–4.

### New judgment calls
- **The lower-bound marker is a separate key**, `"counts": "journaled"`, on the crashed segment's summary. The `stalls` and `backstops` names are unchanged, so a clean segment's summary stays exactly equal to its manifest's.
- **A malformed manifest falls back.** If a manifest's own counts are not counts, the reader uses the journaled counts with the marker.
- **`open_segment` runs on every clean end with a journal**, not only after a backstop: a stop before the first cycle leaves the same gap.
- **The prune failure is recorded at the cycle's start tick** (`tick − k`), like the other window failures.
- **How the two new cases are set up:** `verdict_static` is timed with N set far away (commands plus refresh, no checkpoint). `verdict_checkpoint` is timed at N = k with the refresh suppressed.

### Checks
- `py_compile` on every `tools/*.py` and on `tests/test_vehicle_config.py`: all compile.
- `ruff check tools/ tests/ --no-cache`: all checks passed.
- No test, no repository program, no systemd and no docker was run.
