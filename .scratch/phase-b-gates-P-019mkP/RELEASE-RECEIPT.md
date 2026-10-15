# Grant SPACE-20261011-P-01: result and release receipt (chassis, 2026-10-11)

Holder: Space Chassis Claude Code `session_019mkPNN5J3Atit9tUA6zrNY` / `[8a7d49]`. The tree under test was
P `af671d04908817e914668750b7cd4f6f74034bf4` with the vehicle at `f44399645fb2633e695a5d758cb5a41f43fb848c`. It was
verified before and after each selection, with a clean worktree and a clean vehicle. Driver: `gate.sh` in this
directory. Every run used `systemd-run --user --scope -p CPUQuota=200% -p MemoryMax=8G nice -n 19`, with the
limits read back from the scope's cgroup: `cpu.max 200000 100000` and `memory.max 8589934592`, nice 19.

| selection | command | start / end (AEDT) | pre-start capacity | result |
|---|---|---|---|---|
| root | `python3 -m pytest tests -q -p no:cacheprovider -n 2` | 10:51:21 / 10:51:55 | 42,034 MiB avail, load1 2.70, CPU 14 % | **592 passed, rc 0**, no skips or failures |
| full | `python3 -m pytest -q -p no:cacheprovider -n 2` | 10:52:10 / 11:23:31 | 41,741 MiB avail, load1 3.07, CPU 13 % | **1 failed, 1940 passed, rc 1** |

Monitor: one sample every 5 s, 375 samples in total during the full run. The worst values were
40,454 MiB available, load1 5.35 and 37 % CPU busy. The scope's peak memory was 3.35 GB. No abort
threshold was reached and no abort was taken.

**The failure.** The test was
`docs/deep_research/vehicle/tests/test_vehicle_config.py::test_a_run_ending_cleanly_checkpoints_its_last_completed_cycle_and_an_interrupt_mid_cycle_does_not`
(vehicle-owned). Its helper console reached "between cycles", was sent a real `SIGINT`, and did not
exit inside `communicate(timeout=120)`, so the call raised `TimeoutExpired`.

**The cause is established, and it is the chassis gate driver, not P or the vehicle.**
- `gate.sh` launched the scoped pytest as an asynchronous command (`… &`) of a non-interactive `sh`.
- POSIX shells start such commands with SIGINT ignored. An ignored disposition survives `exec`, and
  Python installs no `KeyboardInterrupt` handler for a signal that starts ignored.
- So every process in the run, including the test's console, ignored SIGINT. The helper slept its
  full 120 s against the test's 120 s timeout.
- Checked after the run, with no test rerun: `sh -c 'python3 -c "…getsignal(SIGINT)" & wait'` prints
  `1` (SIG_IGN), both directly and through `systemd-run --user --scope … &`. In the foreground it
  prints `default_int_handler`.
- This is the suite's only real-SIGINT site (one `send_signal`).
- The root selection was not affected: it has no such test.

**This full result is confounded by the driver and does not qualify P.** It is recorded as it fell,
with no retry. A corrected driver would run the scoped pytest in the foreground and the monitor in
the background. A rerun would need a new grant.

**Evidence kept:** `root.*` and `full.*` (receipt, log and monitor), `full.driver-output.txt`, and the
failed test's tmp directory, copied to `failed-tmp-test_a_run_ending_cleanly_chec0/`.

**RELEASE.** The owned processes have ended. Both scopes reported 0 processes left at the end, and
no pytest, console or helper process of this run remains. The adoption worktree stays materialised
at P exactly. R stays preserved: tree `dd16772e` is in git objects and the R2 work in progress is
in `.scratch/phase-b-increment-R2-wip/`. **The chassis releases grant SPACE-20261011-P-01's slot.**
