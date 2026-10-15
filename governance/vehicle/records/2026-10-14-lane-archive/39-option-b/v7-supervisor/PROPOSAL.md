# Space Vehicle — #39 option B: selection proposal v7 (systemd-owned lifecycle, for Governance allocation)

Vehicle line, Space Vehicle (session `session_01GRfs7dVMu4v5airK6q3w9C`), 2026-10-11.

**A proposal, not a run.** Nothing here has been executed: no test, collection, control, supervisor,
unit or scope. The scripts have only been compiled (`py_compile`). The only host queries made were
read-only configuration reads: `systemctl --version` (systemd 255.4), `stat -fc %T /sys/fs/cgroup`
(`cgroup2fs`), and `systemctl --user show -p DefaultOOMPolicy` (`stop`). After the supervisor's approval came one read-only capacity snapshot (`/proc`, `ps`, `systemctl --user list-units`, `docker ps`, `nvidia-smi` queries), below.

This supersedes v6, whose review (`../../reviews/B-supervisor-v6.md`) found one P2 (recovery time not
fully reserved) and asked for clearer admission wording. v6 superseded v5, which Codex approved and
Governance held in §31, and v1–v4. **v7 = v6 + that P2 fix + the wording + one narrowing** (a failed
argv read now refuses admission instead of counting as empty; on this host every unreadable process's
argv is readable, and the Codex CLI's is empty). v6/v7 make §31's three required corrections:

| §31 correction | v6 |
|---|---|
| 1. On this host some same-user processes deny `cwd`, `exe` and `environ` (EACCES): the user's systemd (PID 1594), `(sd-pam)` (1623), SSH sessions, and also two `codex` processes. So the blanket fail-closed scans would refuse K00 and could never prove cleanup | **Two separate questions, answered separately, with no suppression, no privilege and no security change.** **(a) Cleanup ownership** (supervisor and harness token proofs) asks only whether a process can belong to *this run*. Every process the run owns is created after a tick recorded just before launch, as a descendant of the unit. So an unreadable process whose start time (`/proc/<pid>/stat`) is before that tick cannot be one of them. An unreadable process that started later, or one whose start time cannot be read, stays unknown and fails: exit 4, no receipt. **This proves nothing about admission.** **(b) Resource admission** asks whether a competing Space workload is running. An unreadable process is set aside only if its readable `comm` is in the explicit list `UNREADABLE_HOST_COMMS` (`systemd`, `(sd-pam)`, `sshd`, `sshd-session`, `sshd-auth`, `codex`) **and** its argv, which must be readable (a failed read refuses), names no workload and no Space path. Any other unreadable process refuses. This is an **operational classification, not an exclusivity proof**: it rests on these processes not being workloads themselves, with any workload they have *already* started being a separate exec'd process that the scan examines under its documented limits. **It does not establish that a Codex CLI, or any other process, will not launch competing work after admission.** Exclusivity rests on Governance's one-selection allocation and on coordination with the existing owners. Continuing memory, CPU and load monitoring only mitigates later pressure: it neither reserves capacity nor detects every competing selection |
| 2. Per-control bounds summed to 6,350 s; no suite bound | **Suite budget** `suite_deadline_s = 1800` (30 min). Each control's timeout is capped at the time remaining **less `post_control_reserve_s = 120`**, so its post-run checks fit inside the suite budget, and every post-run step is itself capped at the suite deadline. No control starts with less than 90 + 120 s left. **Recovery therefore starts by 1,800 s.** **Bounded recovery**, `recovery_deadline_s = 180`, runs at the end of every suite: it stops every control-prefixed and owned decoy unit, ends the decoy process, and proves by a successful listing that none remains. It ends by 1,980 s. **Outer bound:** the harness runs as a transient service with `RuntimeMaxSec = 1800 + 180 + 60 = 2040` s, `TimeoutStopSec=30` and `KillMode=control-group`, covering every process it owns. **Worst-case wall clock:** the suite unit ends by 2,040 + 30 = 2,070 s. Every unit it started began before 1,800 s and carries its own `RuntimeMaxSec` (payloads at most 95 s, plus a 15 s stop; the decoy unit 120 s), so all have ended by then. That is **about 34.5 min at most; about 10 min expected** |
| 3. A decoy unit created before a failed start returns a handle | Decoy units are named `space-decoy-<suite token>-<n>`, and the name is **recorded before** `systemd-run` is called. Recovery and the final proof discover and stop every unit with this suite's decoy prefix, so an interrupted start is still owned, found and stopped |

The supervisor excludes, from its "Space unit present" check, the one unit it runs inside: the suite's
outer unit. Nothing else changed. §31's P3 dispositions are adopted: a late terminal acceptance is a
timing residual; a message that units "were stopped" is not proof; the dropped `release_contains` has
no consumer. All paths are absolute. `V7` =
`/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7`.

## Candidate (unchanged; implementation approval stands)

| item | value |
|---|---|
| base | `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f` |
| worktree | `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9`, branch `codex/39-take-by-rename`, uncommitted |
| frozen diff | `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-candidate-3/B-candidate-3.diff`, sha256 `0a00336feb10dcd5c8839893cabafbdc5cbea20474f918d76dc1e0eca3f2d01d`; tree `b447955f60c528e78d05c324ecc4c4317128d1a1` |

## The design change: systemd owns the lifecycle

Each run is a **transient user service** with a **unique name per run**,
`<unit_prefix>-<token[:12]>.service`, started by:

```
systemd-run --user --unit=<name> --service-type=exec --no-block -p CPUQuota=200% -p MemoryMax=6G -p MemorySwapMax=0 -p OOMPolicy=stop -p KillMode=control-group -p ExitType=cgroup -p RuntimeMaxSec=<setup+5+deadline+margin> -p TimeoutStopSec=15 -p ExecStopPost="/usr/bin/python3 V7/record.py <evidence> <token>" -p Nice=19 -p WorkingDirectory=<worktree> -p Environment=CUDA_VISIBLE_DEVICES= -p Environment=SPACE_RUN_TOKEN=<token> -p StandardOutput=file:<evidence>/payload.out -p StandardError=file:<evidence>/payload.out /usr/bin/python3 V7/launch.py <evidence> <token> <setup+5> <inject> -- <payload interpreter> <payload…>
```

| §30 / review finding | mechanism (v5, unchanged in v6 except as above) |
|---|---|
| exception-safe cleanup; a registration gap after spawning | `state["started"]` is set **before** `systemd-run`. Everything from there goes through `finally: cleanup()`. Cleanup stops the unit **by its unique name**, so it needs no PID or handle. Each cleanup step catches `BaseException`, and the loop retries until verified or its deadline. |
| a failed status lookup read as ended; release without proof; ownership; name reuse | **Release** requires all three: `systemctl show` **succeeds** with LoadState `not-found`; the recorded cgroup directory is absent; and no own-user process carries the token, where an unreadable own process is unknown and fails. **Ownership:** show succeeds, the unit is active, MainPID is in its cgroup, and the InvocationID is recorded and re-checked at every later query. **No reuse:** names are unique per run. **No process-group escalation:** `KillMode=control-group` plus `TimeoutStopSec` (SIGKILL after 15 s) take every descendant. |
| the harness abandoning a supervisor | `RuntimeMaxSec` makes systemd end the unit even if the supervisor dies. The harness timeout exceeds the supervisor's declared maximum wall time; if it ever fires, the harness stops the logged unit by name, proves it gone, and ends the suite. |
| terminal OOM window; descendants | **`ExitType=cgroup`:** the unit, and its `RuntimeMaxSec`, stay active until **every** descendant has exited (v3's P1). **`ExecStopPost=record.py`** runs after every stop, for any cause, and writes `TERMINAL.json`: systemd's `SERVICE_RESULT`, `EXIT_CODE` and `EXIT_STATUS`, plus the cgroup's `memory.peak` and `oom_kill`. `OOMPolicy=stop` makes an OOM kill `SERVICE_RESULT=oom-kill`. A record is accepted only when the unit's **final** state agrees with it: collected means success, or failed with the same `Result`. |
| deadlines | The run deadline is checked before every sleep, and sleeps are capped at the time remaining. Admission (60 s), setup (30 s, checked before every step and before GO), the GO wait (setup + 5 s), stop (15 s) and cleanup (60 s) are all bounded. **`RuntimeMaxSec` is the hard backstop.** Deadlines are checked immediately before launch and before GO; a spent cleanup budget is never stretched, and a late verification does not count. |
| signals | systemd starts services with default dispositions. The launcher still records SIGINT as received, restores it explicitly, records again, and **execs** the payload, so `ExecMainStatus` is the payload's own exit status. |
| admission | Fails closed. Its process discovery is documented exactly in `other_space_workloads`' docstring, **with the false-positive bias stated**: a shell whose argv mentions pytest and a Space path refuses admission. Units: any `*space*` unit not inactive, plus any unit with this prefix. Containers: any `*space*` container. Unknown CPU busy is unhealthy, both at admission and while monitoring. |
| reporting and post-run identity | Identity is recomputed on **every** launched path, aborts included. **The outcome is decided once:** the receipt is written first, only if cleanup was verified (a write failure means exit 4 and no receipt); then `summary.json`, carrying the final code. Logging never raises. |
| cause-specific controls | 20 controls, below. Each asserts its **cause** (abort text, systemd `Result`, terminal status, summary fields) as well as the exit code and release. Decoys exercise admission's real discovery. |

## Requested selections, in order. Each needs its own allocation.

### K: failure-injection controls (first)

**Exact commands**, run from any directory:

1. Create the suite's evidence directory:

   ```
   mkdir -p /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/controls-evidence
   ```

2. Start the suite as its own bounded unit. `--no-block` returns at once, so no client process
   waits with the suite's argv:

   ```
   systemd-run --user --no-block --collect --unit=space-vehicle-b-suite-k1 -p RuntimeMaxSec=2040 -p KillMode=control-group -p TimeoutStopSec=30 -p Nice=19 -p Environment=CUDA_VISIBLE_DEVICES= -p WorkingDirectory=/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7 -p StandardOutput=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/controls-evidence/harness.out -p StandardError=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/controls-evidence/harness.out /usr/bin/python3 /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/run_controls.py /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/controls.json
   ```

3. Completion is read from `V7/controls-evidence/controls-summary.json` and from the unit's state
   (`systemctl --user show space-vehicle-b-suite-k1.service -p ActiveState -p Result`). **While the
   suite runs, the operator issues no command whose argv names a Space workload and a Space path:
   admission would rightly refuse.**

**What the controls are:**
- **Count and order:** 20 controls, serial, in the order below. K03 is last.
- **Payloads:** one-liners only — sleep, a 256 MiB allocation under a 64M cap, or a SIGINT
  self-check. **No pytest, no vehicle test.**
- **Decoys:** a `python3` sleep in a Space directory with "pytest" in its argv; a unit named
  `space-decoy-<suite token>-1`, `sleep 120` with `RuntimeMaxSec=120`.
- **Bounds:** suite 1,800 s (recovery starts by then); recovery 180 s; outer `RuntimeMaxSec` 2,040 s
  with a 30 s stop. Per control: its declared maximum, capped at the suite time remaining less a 120 s
  post-run reserve. Worst case about 34.5 min; expected about 10 min.
- **Evidence:**
  - per control: `V7/controls-evidence/<control>/`;
  - for the suite: `V7/controls-evidence/controls-summary.json` (the per-control rows, the suite
    token, and the final proof: control units left, decoy units left, decoy processes ended, within
    the recovery deadline, proven clean) and `harness.out`.
- **Pass:** every control passed **and** the final proof is clean.

| control | forces | asserted cause and outcome |
|---|---|---|
| K00-success | nothing | exit 0, release; owned, go; `SERVICE_RESULT=success`, `EXIT_STATUS=0`, `oom_kill` 0; SIGINT not ignored after restore |
| K01-interrupt-after-launch | `KeyboardInterrupt` just after `systemd-run` | exit 3, release; abort names the interrupt; no GO |
| K02-report-raises | reporting fails | exit 3, release (the receipt attests cleanup only); no summary |
| K04-ownership-never-established | ownership hidden | exit 3, release; abort "setup deadline 30 s passed before ownership"; owned false |
| K05-caps-mismatch | caps compare false | exit 3, release; abort "caps did not read back"; owned, no GO, no samples |
| K06-pre-go-unhealthy | a pre-GO measurement of 0 MiB through `healthy()` | exit 3, release; abort "pre-GO health … MemAvailable 0 MiB" |
| K07-go-never | GO withheld | exit 3, release; launcher exits 98 (`EXIT_STATUS=98`, `NO-GO.json`) |
| K08-deadline | sleep 60 s against a 6 s deadline | exit 3, release; abort "deadline 6 s passed" |
| K08b-runtime-backstop | the supervisor's own deadline disabled | systemd ends the unit: `SERVICE_RESULT=timeout`; exit 3, release |
| K09-oom | 256 MiB in a 64M, no-swap unit | `SERVICE_RESULT=oom-kill`; abort names the OOM; exit 3, release |
| K10-terminal-missing | no terminal record is accepted (injected before any record is read) | exit 3, release; abort "no terminal record from the unit's ExecStopPost" |
| K11-identity-changes-post | post-run identity mismatch | exit 3, release; abort "the candidate changed during the run" |
| K12-sigint-ignored-inherited | SIGINT ignored before the launcher's first record | the payload checks its own disposition: `EXIT_STATUS=0`; READY shows inherited true, restored false; exit 0 |
| K13a-admission-process-decoy | a Space-looking process running | exit 2; abort names the decoy; nothing launched |
| K13b-admission-unit-decoy | a Space-named unit active | exit 2; abort names the unit; nothing launched |
| K14-admission-identity-mismatch | the expected diff hash is wrong (the real comparator, before launch) | exit 2; abort names `diff_sha256`; nothing launched |
| K15-stop-fails-once | the first `systemctl stop` fails | cleanup retries and verifies; exit 3, release; abort names the failed stop |
| K16-descendant-outlives-main | the payload exits 0, leaving a child sleeping 300 s; the supervisor's deadline disabled | `ExitType=cgroup` keeps the unit and its runtime limit alive: `SERVICE_RESULT=timeout`, `EXIT_CODE=exited`, `EXIT_STATUS=0`; exit 3, release; no token process left |
| K17-interrupt-during-cleanup | a `KeyboardInterrupt` at the first cleanup attempt | cleanup continues and verifies; exit 3, release; abort names both |
| K03-cleanup-proof-unknown (**last**) | status lookup and process reads fail during verification | **exit 4, no release**; abort names both. The harness proves the unit gone itself and ends the suite. **The slot stays held** until the owner's explicit receipt, given after the suite's final proof and the coordinator's verification |

### S1: the bounded test selection (after K passes; its own allocation)

- **Command:** `/usr/bin/python3 V7/supervise.py V7/spec-S1.json`.
- **Payload:** `<venv3.12 python> -m pytest -p no:cacheprovider -n 2 -q -rfEs -o addopts= --junitxml=V7/evidence-S1/junit.xml <the same 25 node IDs>`.
- **Expected:** 25 tests, 1 invocation, 2 workers.
- **Deadlines:** setup 30 s, run 420 s; `RuntimeMaxSec` 485 s; cleanup 60 s.
- **Measurement:** `memory.peak` is recorded by `record.py`, as a measured peak for any later qualification proposal.
- **No pass is assumed, and there is no rerun to green.**

## Bounds and why (proposals; ELSPETH keeps priority)

| bound | value | reasoning |
|---|---|---|
| CPU | `CPUQuota=200%` (2 of 24 logical CPUs), `Nice=19` | at most two workers; niced below ELSPETH's normal priority |
| memory | `MemoryMax=6G`, `MemorySwapMax=0`, `OOMPolicy=stop` | a declared ceiling, not a measured peak. An OOM stops this unit only. S1 records `memory.peak` |
| admission: MemAvailable | ≥ 16 GiB | 6 GiB ceiling + 10 GiB reserve |
| abort: MemAvailable | < 10 GiB, sampled every 5 s | **a sampled policy, not a guarantee**: other consumers can grow between samples. It bounds how long Space keeps running once memory is short; it does not reserve memory for ELSPETH |
| admission: CPU busy | ≤ 50% over 2 s; unknown refuses | refuses on an already heavily used host. ELSPETH's six workers are about 25% of 24 CPUs |
| abort: CPU busy | > 85% for 3 samples (15 s); unknown counts as busy | Space stops rather than compete on a near-saturated host |
| load1 | admission ≤ 12; abort > 20 for 3 samples | half the CPUs; sustained pressure near the CPU count |
| GPU | `CUDA_VISIBLE_DEVICES` empty | none used; Sultai's reservation untouched |
| concurrency | **one Space selection, by Governance's allocation and coordination with the existing owners.** Admission is a second, point-in-time check: it refuses on Space workloads matching its documented discovery (`other_space_workloads`), on Space-named units and on Space-named containers. It cannot see work launched after it ran | |

These bounds are this proposal's own and none is inherited.

**Capacity:**
- **Governance's own read-only check** (§31, 12:09:34 UTC): 31.04 GiB available, 17.9% CPU busy,
  load1 3.95; no Space units or containers.
- **The vehicle's read-only snapshot** (`/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v5/capacity-snapshot.txt`,
  sha256 `fdca78485f9b2f0e17a439cb66d0d7bb44cdd317022ed7d05d37448aece46ed7`), 2026-10-11T23:00:25+11:00, below.
- **CPU:** 24 logical; busy 17.9% over 5 s; load 6.48 / 5.81 / 5.76.
- **Memory:** MemTotal 61.9 GiB, MemAvailable 33.7 GiB.
- **Running now:** ELSPETH's CI test workers, about 4 CPUs, plus one long-running ELSPETH process.
- **Space:** no unit or container named Space.
- **GPU:** both GPUs idle (15 MiB used each); Space uses none.

Under the proposed bounds either would admit, leaving ELSPETH about 20 CPUs and more than 27 GiB. This
is a snapshot, not an admission. A K grant needs a fresh allocation-level admission before the suite
starts, because the decoys start before any supervisor admission (§31). Each supervisor also
re-measures at launch, and refuses if the host has changed.

## Identities

`V7/SHA256SUMS` lists every script, spec and control. The sha256 of `SHA256SUMS` itself, and of this
proposal, are given with the hand-off.

## Exit codes

- **0:** passed; the payload's own exit is in `summary.json` `terminal`.
- **2:** refused before launch.
- **3:** aborted or invalid, with cleanup verified and released.
- **4:** cleanup not verified. There is no receipt, and the slot stays held for the operator.

## Not requested here

These are each allocated separately:
- repairs, with a new frozen diff and a delta review;
- a re-run of exactly the affected selection;
- the full two-lane qualification.

Issue #42 stays separate.
