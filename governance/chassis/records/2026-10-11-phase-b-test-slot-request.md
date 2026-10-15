# Phase B: two increments, their qualification, and the test-slot request (chassis, 2026-10-11)

> **Historical as of 2026-10-14.** The current state is in `2026-10-14-chassis-lane-status.md`. The increment
> table below still shows R `dd16772e` with its reviews running; R was superseded by R2, R2b and then R2c
> `148a31c4`, which is the resource increment now staged.

Owner: Space Chassis Claude Code `session_019mkPNN5J3Atit9tUA6zrNY` (peer `[8a7d49]`). Written for
Governance's coordination of the one shared Space test slot (master plan §14), and following Emmy's
scope correction of 2026-10-11.

**Grant SPACE-20261011-P-01 (P root and full) ran and is released.** The result and release
receipt is `.scratch/phase-b-gates-P-019mkP/RELEASE-RECEIPT.md`:

| tree | selection | result |
|---|---|---|
| P | root | **592 passed** |
| P | full | **1 failed, 1940 passed** |

**The full run is confounded and does not qualify P.** Its one failure, a vehicle test that sends a
real SIGINT, was caused by the chassis gate driver: it launched pytest as a background job, which
starts with SIGINT ignored. That was checked by mechanism, not by a rerun. A corrected driver is
ready but has not been used, and a rerun needs a new grant. R, build and live: not granted.

**SPACE-20261011-P-FULL-01 (master §25), 12:26–12:57 AEDT.** P `af671d04…` **passed its whole suite: 1941
passed**, rc 0, with supervision held and cleanup verified. It ran through the reviewed driver `full.py` `2557d326…`.
The reservation is released (`.scratch/phase-b-full-P-019mkP/RECEIPT-P-FULL-01.md`, `4f03dc0e…`). With the root
suite's 592 passes on the same tree, P has its required gate. The earlier failure was the gate driver's SIGINT
inheritance, shown by DIAG-02 (`.scratch/phase-b-diag-P-019mkP-r2/RECEIPT-DIAG-02.md`). P is not committed yet.

**R2c, the resource increment (2026-10-11 ~13:45 AEDT).** Tree `148a31c4951e43c1cdafdf30c15b029dc7e104a8`,
staged and pinned as `refs/preserve/phase-b-R2c-148a31c4`. It answers every R, R2 and R2b finding. Its
confirmation reviews (Opus and Astra) both say **LAND**, with no Critical or Important findings.
- Diffs: `.scratch/phase-b-R2c.vs-P.diff` (`ef4954a1…`) and `.scratch/phase-b-R2c.vs-R2b.diff` (`240b78d1…`).
- **Root passed** under SPACE-20261011-R2C-ROOT-01 (14:08–14:09 AEDT): pytest exit 0, **617 passed**, no
  failures, errors or skips; supervision held; cleanup verified; released
  (`.scratch/phase-b-R2c-root-019mkP/RECEIPT-R2C-ROOT-01.md`, `ac0f8d10…`). Governance accepted it (master §28).
  The bounded stop also removed a `sleep 30` left by the unchanged `tests/test_journal.py::
  test_a_stream_that_never_ends_times_out`; that test is the same in P and R2c and was not changed.
- Not yet run: whole suite, build or live.
- Needs: a whole-suite grant on `148a31c4` (a full driver bound to R2c, reviewed first), and a separate
  build-and-live grant. Builds are covered in `2026-10-11-serial-build-readiness.md`.

## The two increments, kept separate (staged and uncommitted, unpublished)

They are in the adoption worktree `.claude/worktrees/vehicle-adoption`, on branch `phase-b-adoption`
(local; HEAD is `be63f93` = published `vehicle-adoption`). The vehicle clone is at `f443996`. The
staged index holds the top tree.

| increment | tree | content | reviews | qualification needed |
|---|---|---|---|---|
| **P**: the Phase B corrections | **`af671d04908817e914668750b7cd4f6f74034bf4`** | candidate-3 (`04dff0be`) plus only its review fixes | Opus **land**; Astra **land**; no Critical or Important | root and whole suite on `af671d04` |
| **R**: live-run resource controls | **`dd16772e6d537db0baf52f9741b58b2fc17ef3c7`** (on P) | caps, one stack at a time, host-scope check, capped containment sweep, serial builds | Opus and Astra **running** | root and whole suite on `dd16772e`, then live on `dd16772e` |

**Evidence**, all under `.scratch/`:

| file | sha256 |
|---|---|
| `phase-b-P.vs-3.diff` | `4c2684bb…` |
| `phase-b-P.diff` | `3b1ea8cf…` |
| `phase-b-R.vs-P.diff` | `92e57d86…` |
| `phase-b-PR.diff` | `94411765…` |

The reviews are in `.scratch/phase-b-reviews/review-phase-b-{P,R}-*`.

**Superseded and preserved:**
- `b29bf8af` (gated 2026-10-10, `.scratch/phase-b-gates-2/`);
- `04dff0be`;
- `8db6db9f` (candidate-4, which mixed both increments: Opus found 1 Critical and 3 Important, Astra
  found 3 Important; never gated).

Their diffs, tree listings and reviews are kept.

The live gate runs only on R. P's own live harness has the uncapped two-stack layout and the
guard defects, so it is not run live.

## What R enforces, each by the kernel

- **One smoke stack at a time.**
  - A lock in `$XDG_RUNTIME_DIR` (`fcntl.flock`) is shared by every checkout and session of this
    user. It is held from a stack's start to its `down`.
  - `docker ps --filter label=com.docker.compose.project --format '{{.Label "com.docker.compose.project"}}'`
    must list no other smoke project, both before the build and again before `up`. The template is
    pinned in a test and executed against every container on the daemon.
  - The vehicle's tests run last, and the vehicle's stack replaces the fixture's.
- **Per-container caps on every stack service.**
  - Compose `cpus`, plus `mem_limit` with `memswap_limit` equal to it.
  - Agents 0.75 CPU / 3 GiB; recorders 0.2 / 512 MiB; window 1.0 / 512 MiB; stub 0.2 / 256 MiB;
    fleet_monitor 0.1 / 256 MiB; review 0.25 / 512 MiB.
  - **Sum: 4.4 CPUs and 12 GiB.**
  - Checked twice:
    - offline, against the rendered `compose config`;
    - live, before any test, from each container's own cgroup read on the host side
      (`/sys/fs/cgroup/system.slice/docker-<id>.scope`).
- **The containment check's image sweep:** `--cpus 0.2 --memory 256m --memory-swap 256m`, one sweep
  at a time.
- **The host side:** the live fixtures refuse to start a stack unless this process's own cgroup caps
  it at or below 0.35 CPU and 1 GiB. The command:
  `systemd-run --user --scope -p CPUQuota=35% -p MemoryMax=1G nice -n 19 python3 -m pytest live -q`.
- **Enforced total: 4.95 CPUs and 13.25 GiB** of the 5 CPU / 14 GiB coordination figures.

## Not enforced, stated as such

- **The docker daemon's own work** (dockerd, containerd, the shims). The remaining 0.05 CPU and
  0.75 GiB is an unenforced reserve; strict isolation needs host changes, which are out of scope.
- **Image builds.** They are ordinary and serial, one compose call per image, with no claim of a
  hard aggregate cap. No privileged builder is created (Emmy, 2026-10-11). Both images are expected
  to be cache hits, since no candidate change touches a file copied into an image. Governance
  observes them under its own thresholds.

## The selections: one at a time, `nice -n 19`, inside a user scope

For root and whole suite the scope is `systemd-run --user --scope -p CPUQuota=200% -p MemoryMax=8G`.
That makes two workers a kernel limit.

| # | tree | selection | workers | expected time |
|---|---|---|---|---|
| 1 | P `af671d04` | root suite `tests/` (592) | `-n 2` | ~1–2 min |
| 2 | P `af671d04` | whole suite | `-n 2` | 30–40 min |
| 3 | R `dd16772e` | root suite (592 + R's new tests) | `-n 2` | ~1–2 min |
| 4 | R `dd16772e` | whole suite | `-n 2` | 30–40 min |
| 5 | R `dd16772e` | `live/` (19 tests), in its 0.35 CPU / 1 GiB scope | 1 | ~10–15 min, including serial cached builds |

Each tree is checked out exactly in the existing worktree before its selections. The tree is
recorded before and after, and every result is recorded as it falls. Under a 2-CPU cap the
vehicle's timing-dependent claim race (#39) may reproduce its known contract-probe failure. That
would be recorded, not rerun to green.

Selections 1–4 can be granted separately from 5.

## Not requested

No GPU work, no interference with ELSPETH or Simic, no host, daemon, security or access changes,
and no privileged builder. The vehicle line's #39 work needs no part of this slot.
