# SPACE-20261011-P-DIAG-01: early stop, cleanup and release receipt (chassis, 2026-10-11)

Holder: `session_019mkPNN5J3Atit9tUA6zrNY` / `[8a7d49]`. Candidate P `af671d04…`, vehicle `f443996…`, and test
file sha256 `3b917de3…`: all exact before and after (`arm1/receipt.jsonl`).

**Arm 1 was a diagnostic abort before release. The test never ran.**

- **Admission at 00:45:07Z** was clean: 42,227 MiB available, load1 2.61, 13.2 % CPU busy, no competing
  Space process, no Compose project, no active Space scope.
- **Launch:** the original background path (`systemd-run --user --scope … &` in a non-interactive sh,
  then `wait`), through `launch.py` (`91a813dc…`).
- **The supervisor `diag.py` as run (`02d8ca49…`, preserved as `diag-r1-as-run.py`) had a defect.** It
  queried, and would have stopped, the bare unit name. `systemctl` resolves that to a nonexistent
  `.service`, so the live `.scope` read as inactive. The supervisor correctly held: no scope readback,
  so no go-file and no test. The launcher exited after its own 60 s go-wait. A 4 s control scope
  confirmed the mechanism: the bare name reads `not-found/inactive` while `<name>.scope` reads `active`.
- **The pytest log** holds only systemd-run's "Running as unit" line. The pytest result is none.
  Supervisory status: **ABORTED**, for the supervisor's own defect.

**A diagnostic finding from the arm, independent of the test.** The launcher, started through the
original path, recorded SIGINT as **inherited `SIG_IGN`**: `SigIgn 0000000001001006`, which is
SIGINT and SIGQUIT ignored. That is the same disposition the failed full run's test console would
have inherited. The supervisor process itself had `default_int_handler`.

**Cleanup, verified after the stop.**
- The scope `space-chassis-pdiag-arm1-1791679505.scope` reports `LoadState=not-found`,
  `ActiveState=inactive`: ended and collected.
- No launcher, pytest, xdist or helper process remains.
- The sh driver was killed by the supervisor's bounded wait (rc -9). The monitor never started.
- My first post-run wait loop matched its own command line, so it never ended; I stopped it.
  It owned no test process.

**The fix, held.** `diag.py` now names `<unit>.scope` for every show, stop and kill, and treats an
unloaded scope with no cgroup as ended (sha256 `4a8d2d45ad40aae64a4b56474b815b45c64657030217aaef7d1dc62a0e3d5ced`).
It was not run. Arm 1 has not executed the test once, so a re-launch of arm 1 with the fixed supervisor
needs your decision. The evidence directory `arm1/` is never reused; a re-launch would write `arm1b/`.

**RELEASE:** no owned process remains. The chassis releases the SPACE-20261011-P-DIAG-01 reservation.
Arm 2 was not run. No R, build or live run; no product or test edits.
