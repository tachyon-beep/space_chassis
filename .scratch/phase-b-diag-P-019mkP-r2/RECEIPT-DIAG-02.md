# SPACE-20261011-P-DIAG-02: paired result, cleanup and release receipt (chassis, 2026-10-11)

**Grant:** SPACE-20261011-P-DIAG-02 (master §23).
**Holder:** `session_019mkPNN5J3Atit9tUA6zrNY` / `[8a7d49]`.
**Supervisor:** `diag.py` sha256 `2ead42bee98575b0d44b734c13aaf082dc7323ca70414b9b4c5a1b4ba6e1d94e`, unchanged. Its
embedded "DIAG-01" label is historical; this receipt and `DIAG-02-outer-receipt.log` identify DIAG-02.
**Launcher:** `launch.py` `91a813dc…`.
**Evidence:** `.scratch/phase-b-diag-P-019mkP-r2/arm1` and `/arm2`, both fresh.
**Node:** `docs/deep_research/vehicle/tests/test_vehicle_config.py::test_a_run_ending_cleanly_checkpoints_its_last_completed_cycle_and_an_interrupt_mid_cycle_does_not`,
with `-q -p no:cacheprovider -n 2`, unchanged.
**Identity:** P `af671d04…`, vehicle `f443996…` and test file `3b917de3…` were exact before and after both arms.

| | arm 1: original background path | arm 2: SIGINT restored to SIG_DFL by the launcher |
|---|---|---|
| admission (UTC) | 01:10:57: 42,277 MiB, load1 2.43, CPU 13.4 %; no competitors, Compose projects or Space scopes | 01:13:22: 42,310 MiB, load1 2.69, CPU 13.7 %; the same |
| scope readback before go | cpu.max `200000 100000`, memory.max `8589934592`, memory.events all 0 | the same |
| launcher's SIGINT | inherited `SIG_IGN`; before exec `SIG_IGN` (SigIgn …1006) | inherited `SIG_IGN`; before exec `SIG_DFL` (SigIgn …1004) |
| scope processes at the nice check | pytest, xdist worker, execnet child and `sleep/interruptible.py` helper: all nice 19, **SIGINT ignored** | pytest, worker, child and `claim/interruptible.py` helper: all nice 19, **SIGINT not ignored** |
| released / ended | 01:10:58 / 01:13:08 | 01:13:23 / 01:13:33 |
| **pytest (raw)** | **rc 1, 1 failed**: the same node, `TimeoutExpired` "timed out after 120 seconds" at `interrupted_console`'s `process.communicate(timeout=120)`, matching the failed full run | **rc 0, 1 passed** |
| **supervision** | held; no abort reasons | held; no abort reasons |
| monitor | 27 samples; min 42,086 MiB, max load1 2.61, max CPU 17.7 %, scope peak 130 MB; no OOM | 3 samples; min 42,137 MiB, max load1 2.82, max CPU 17.6 %, scope peak 127 MB; no OOM |
| cleanup | verified: scope not-found, cgroup removed, monitor ended, sh rc 1, no helpers | verified: the same, sh rc 0 |

**Diagnostic finding.**
- The unchanged test fails when SIGINT starts ignored, as the original background launch made it: every process in the
  scope, the helper console included, ignores it.
- The same test passes when the launcher restores SIG_DFL, with nothing else changed.
- The failed full-suite run on P is therefore attributable to the gate driver's launch path, not to P or the vehicle.

**This is not qualification of P.** P's whole suite still has no valid passing run, and a broad rerun needs its own reviewed
driver and grant.

**Final cleanup, checked independently after both arms:**
- Both scopes read `LoadState=not-found ActiveState=inactive`, and no `space-chassis-pdiag-*` cgroup exists.
- No launcher, diag, xdist, execnet or helper process remains.
- The adoption worktree is still P exactly, and R (`dd16772e`) and the R2 work in progress stay preserved.

Evidence sha256: arm1 receipt `4d213597…`, pytest.log `abf5edc7…`, monitor `84a13184…`, launcher `d08ae14e…`;
arm2 receipt `c239b7ec…`, pytest.log `0e0e0139…`, monitor `06315a37…`, launcher `0dcf97b0…`.

**RELEASE: the chassis releases the SPACE-20261011-P-DIAG-02 reservation.** No retry, R, build or live run, and no
product or test edit was made.
