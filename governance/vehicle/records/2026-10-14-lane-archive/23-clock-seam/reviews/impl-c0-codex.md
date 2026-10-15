# #23 implementation review, candidate 0 — Codex reviewer of record

Received 2026-10-12T10:16:46.926Z; saved verbatim (harness indent removed).

---

**Request changes (issue #23 implementation, candidate 0).** No P1 found. The worktree diff matches the frozen SHA `fd81861b…`. Static inspection only; no tests or repository programs run, and no files changed. Paths below are in the worktree `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/v-23-clock`.

- **P2 — Ring deletion failure corrupts the cache.** The oldest entry is removed from memory *before* `unlink`. EIO/EACCES leaves that frame on disk but forgotten; subsequent cycles prune newer frames and report incorrect `held`/`losses` until reconciliation. Remove the cache entry only after successful deletion or ENOENT, or invalidate on failure. `tools/console.py:5603`

- **P2 — Backstop logging can escape as a traceback.** `journal_event()` can raise `RecordUnwritable`, but its invocation inside the `LagBackstop` handler is outside the sibling refusal handler. An unrecoverable append therefore exits through an uncaught exception instead of the named exit-3 refusal. Protect this write and test append/rollback failure. `tools/console.py:6533`

- **P2 — Reader enforcement of the row invariant is incomplete.** Rows 2…k need not repeat row 1's `receipt` counter or `lag_us`. Replay rejects only decreasing counters, so a rechained interior suffix can introduce an unissued counter increase. This contradicts design section 4's reader-verified invariant. Add per-cycle equality checks and mutation tests. `tools/console.py:1574`, `tools/console.py:2522`

- **P2 — Crashed-segment summaries omit stalls and backstops.** The reader returns only lag/cost statistics, contrary to design section 2. Test 4 explicitly compares against an oracle lacking these fields, so it permits the divergence; it also never checks clean-end manifest percentiles. `tools/console.py:2998`, `tests/test_vehicle_config.py:31399`

- **P2 — The feasibility instrument can report a misleading fit.** Verdict cycles and static/checkpoint cycles are measured separately, then their maximum becomes `worst_fits_budget`. It never measures commands/take barriers/write-ahead **together with** static rewriting and checkpointing, as required by section 8. Add that combined workload before using the result for deployment. `tools/measure_clock.py:443`

- **P2 — One existing test is expected to fail.** The journal-fsync failure test still expects "stopped at tick 1". The new writer commits only after durability, so failure of the first append leaves tick **0**. Update the assertion and verify truth/lineage remain at the durable boundary. `tests/test_vehicle_config.py:26541`, `tools/console.py:3952`

- **P2 — Important new tests do not establish their claimed cases.** Test 13 never establishes a target that continues changing after step 1, leaving the original dwell defect insufficiently guarded. Test 19 signals **before** `real_claim`, using `k=1`; it does not exercise shutdown after claiming a batch during a partially stepped multi-tick cycle. Test 7 changes only `k`, leaving named `m`/`N` and mixed-policy validation uncovered. `tests/test_vehicle_config.py:31808`, `:29091`, `:31545`

- **P3 — Ordinary suffix-write failure reports the wrong durable tick.** If row 1 is durable but appending rows 2…k fails, `_commit` is bypassed and stderr names the cycle's starting tick. Recovery reaches one tick further. Preserve/report that durable prefix as the compare-point refusal path already does. `tools/console.py:3939`

- **P3 — The adapted interrupt test has a timing dependency.** Its sleep rendezvous requires a wait immediately after claim count 2. If those cycles fall sufficiently behind the real 100 ms schedule, that rendezvous is skipped permanently. Inject deterministic time as well as the sleeper. `tests/test_vehicle_config.py:29085`

**Looks structurally consistent:** the three header propagation sites, per-cycle receipt accumulation, write-ahead ordering, compare-point refusal suffix, post-replay inheritance, carried-forward costs, and normal pacing/signal paths. **Checkpoint v3 is justified:** format incompatibility is classified before the new body shape is checked, avoiding erroneous corruption/fallback treatment of v2 checkpoints. `tools/checkpoint.py:1036`
