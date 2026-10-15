# #39 option B — committed-head full-development-gate proposal, G-2 (for Governance allocation)

Vehicle line, Space Vehicle (`session_01GRfs7dVMu4v5airK6q3w9C`), 2026-10-12. This revision follows
Governance MASTER §37: literal committed-head qualification; one local, unpublished candidate commit
under a recorded coordinator sequencing exception; G-2 selected. The previous revision is kept, outside
the manifest, at `G/superseded/PROPOSAL-G.r4.md`, with the unselected G-1 specs.

**Preparation only. No gate, test, collection, supervisor, `systemd-run` or worktree creation has run,
and nothing is granted by this document.** The one action taken under §37 is the local candidate
commit (§1). There is no push, PR, publication, merge, adoption or pin change.
`G` = `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate`.

## 1. The candidate: commit `7a87eb82`, local, UNQUALIFIED / UNPUBLISHED

| item | value |
|---|---|
| **commit** | **`7a87eb82cfef55dcc74248df41720883587ca7af`** |
| parent | `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f` (tier 1's merge) |
| tree | `ccc2782e350a6b9abe33d19db6884ac3fb82ec95`: candidate 5, as reviewed |
| branch | `codex/39-take-by-rename`, in the owner's topic worktree `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9`; no upstream; not pushed |
| message | byte-identical to `G/COMMIT_MESSAGE.txt` |
| author / committer | John Morrissey `<544926+tachyon-beep@users.noreply.github.com>`, 2026-10-12T01:00:01+11:00 |
| base-relative diff (`git diff f75420c`) | sha256 `0d4da11e9cbe56fcad7e09c48e027340d41f1bae438adfe8cce9dcc889a951d0` (= `B-candidate-5/B-candidate-5.diff`) |
| `tools/console.py` | `010061b2…`: **byte-identical to candidate 3** (implementation approved) |
| `tests/test_vehicle_config.py` | `f01bf285…`: **byte-identical to candidate 3**; 537 functions, 9 parametrized (14 cases), **551 collected expected** (a static AST count, not an observed gate result) |
| `README.md` | `26ee1a3b1f3d3c2c086c99e0e1fd71e7964f5d825e093688b260ae88f1ba9341` |
| ADR 0002 | `a4057405c30d37ce3f3a0bf77a9b6449a253cf335149ecddff1b5da38d825a70` |

**How the commit was made.**
1. **Before:** the topic worktree's HEAD was `f75420c`; exactly the four files were modified; the
   base-relative diff hashed to `0d4da11e…`; nothing was staged and nothing was untracked.
2. **Hooks:** no hook was active (only `.sample` files, no `core.hooksPath`) and there was no commit
   signing, so the commit started no workload.
3. **Staging:** exactly the four paths, by name. The index tree was `ccc2782e…`.
4. **Commit:** `git commit -F G/COMMIT_MESSAGE.txt`.
5. **After:** parent, tree and message were verified; the worktree was clean.

There was no amend, reset, unrelated staging or hook bypass.

The commit is **unqualified** until both full lanes pass and the final evidence review passes. If any
phase fails, it stays unqualified. A fix is a new commit (never an amend), with its own review and
allocation.

## 2. Verified evidence versus remaining qualification

| evidence | covers | status |
|---|---|---|
| design review, 5 Codex rounds | option B's design | approved |
| implementation review, candidates 0–3 | candidate 3's code and tests, identical in `7a87eb82` | **approved** |
| K (`SPACE-20261011-B-V7-K1`) | the v7 supervisor that will run this gate | 20/20; released |
| S1 (`SPACE-20261011-B-V7-S1-01`) | **its 25 selected tests** on this code | 25/25 passed, exit 0; released. Evidence for those 25 tests only: **not** for the other 526 cases, the full gate, or any contract guarantee |
| final package reviews r1–r4 | contract, driver, proposal, staging, wording | r1, r2 request changes (fixed); **r3, r4 approve** (§6) |
| local candidate commit | §1 | made under §37; **unqualified, unpublished** |
| this revision's confirmation (r5, r6) | specs, setup, proposal, relay | r5 approve with changes (P3 fixed); r6 pending (§6) |
| **full development gate, G-2, 3.12 and 3.13** | all seven steps per lane; 551 expected cases per pytest phase | **NOT RUN** |
| final review of the actual diff and gate evidence | — | after the gate |
| publication (push, PR, CI, merge) | — | **John's approval** |

## 3. Committed-head qualification (Governance §37)

- **The literal SHA is qualified.** Every phase runs in a clean, detached checkout of
  `7a87eb82cfef55dcc74248df41720883587ca7af`, as `practice.md:44,56` requires: "at the exact SHA, in a
  detached worktree". The earlier proposal to substitute an uncommitted tree's identity is
  **withdrawn**, as Governance rejected it.
- **The sequencing is an explicit exception, not compliance.** `CONTRIBUTING.md:32` and `AGENTS.md:84`
  ask for the whole suite **before** committing. Gating after the local commit does **not** literally
  meet that requirement. The earlier claim that a post-commit, pre-push gate would satisfy it is
  **removed**. The commit was made under §37's bounded sequencing exception for this one candidate,
  by the existing Vehicle owner, after the final package review.
- **Hosted CI is not a substitute.** On a pushed head it would run ruff, `check_vehicle.py` and the
  full referee on both lanes, plus a readiness diagnostic on 3.12. It does not repeat the strict,
  build-order or measure steps on both lanes. The seven local steps are the gate.

**The supervisor's identity check is unchanged.** The v7 supervisor compares `git rev-parse HEAD`
with `expect.head`, and the hash of `git diff <base>` with `expect.diff_sha256`
(`v7/supervise.py:128–136, 406, 610`). The specs therefore keep `base` = `f75420c` and the verified
base-relative diff `0d4da11e…`, and pin `expect.head` to `7a87eb82…`. For a clean checkout of
`7a87eb82`, `git diff f75420c` is exactly candidate 5's diff.

That check cannot see the index or untracked files, so `G/gate_worktree.sh` separately proves a
clean index and worktree, and no untracked non-ignored file, **before and after every allocation** (§4).

## 4. The gate: G-2, four serial allocations (selected by Governance)

**Content.** Each lane runs the repository's seven steps, from `practice.md`'s "The gate" and
`CONTRIBUTING.md`, with the lane's interpreter. They are split at one boundary only: the six static
steps, then **one whole-suite pytest invocation**.
- There is no sharding and no reduced coverage.
- The order is **G312s → G312p → G313s → G313p**.

| # | step | command (cwd = the gate worktree) | expected |
|---|---|---|---|
| 1 | ruff | `python -m ruff check . --no-cache` | 0 |
| 2 | lint | `python tools/check_vehicle.py` | 0, and "COMPOSES, with 273 declared debt(s)" |
| 3 | strict | `python tools/check_vehicle.py --strict` | 2 |
| 4 | readiness | `python tools/plant.py --readiness` | 0 |
| 5 | build-order | `python tools/plant.py --build-order` | 0 |
| 6 | measure | `python tools/measure_clock.py --samples 10` | 0 |
| 7 | pytest | `python -m pytest -n 2 --max-worker-restart=0 -q -o addopts= -rs -p no:cacheprovider --junitxml=<evidence>/junit.xml` | 0; JUnit 551/0/0/**0 skipped**; no xdist crash line |

**Departures from the practice file:**
- **`-n 2`, not `-n 6`:** the program's two-worker bound.
- **`--max-worker-restart=0`, plus independent crash detection.** xdist would otherwise replace a
  crashed worker (review r1). The flag alone does not force a failing exit: a worker that crashes
  with no test in hand leaves no failed case (review r2). So `gate_lane.py` fails the step on any xdist
  crash line, including `[gwN] node down: <error>`, the only one printed under `-q`. Review r3
  approved this.

**Interpreters** (`G/interpreters.txt`). Both are hash-locked from `requirements-dev.lock` (sha256
`6d1271054b0f9af2690b6b6427da5db04008912cb32ff7607cb31c45f611eac1`), with an identical `pip freeze`
(sha256 `4535babcc5a2e230b30d864b4af05d1838aafd5f4b5c885710b30fcd0709b4cb`): ruff 0.16.8, pytest
9.0.1, pytest-xdist 3.8.0.
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.12/bin/python`: 3.12.3
- `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.13/bin/python`: 3.13.15

**Gate worktree:** `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/gate-C-7a87eb8`,
a clean detached checkout of `7a87eb82`. It is created once, by the first allocation (G312s), and
shared by all four. It is never written to by the vehicle owner.

### Timing basis: measurements and estimates

**Measured** in tier 1's full gate at `7ac9791` (542 tests, `-n 2`, `nice 19`, this host;
`t1-evidence/gate-7ac9791-ca87a9/run-*.txt`), as Governance independently confirmed:
- **pytest:** **1,990.54 s** on 3.12 and **1,484.85 s** on 3.13;
- **whole lanes:** 2,017 s and 1,510 s;
- **the six static steps:** about 27 s and 25 s.

Also measured: S1's 25 tests took 25.75 s, with a payload peak of 559 MiB.

**Estimated, not measured:**
- the 9 new tests add about +35 s on 3.12 and +25 s on 3.13;
- candidate 7a87eb82's real duration;
- the full suite's memory peak (6 GiB is a ceiling, not a measured requirement);
- host load.

**Deadlines** are about 1.5× the measurement for pytest: 3,000 s on 3.12 and 2,300 s on 3.13. Each
static phase gets 300 s, about 11× its measurement.

| alloc | spec | lane / phase | GO deadline | payload `RuntimeMaxSec` (30 + 5 + deadline + 30) | outer `RuntimeMaxSec` (deadline + 600) + 30 s stop |
|---|---|---|---|---|---|
| G312s | `G/spec-G312s.json` | 3.12 / static (steps 1–6) | 300 s | 365 s | 900 + 30 s |
| G312p | `G/spec-G312p.json` | 3.12 / pytest (step 7, whole suite) | 3,000 s | 3,065 s | 3,600 + 30 s |
| G313s | `G/spec-G313s.json` | 3.13 / static (steps 1–6) | 300 s | 365 s | 900 + 30 s |
| G313p | `G/spec-G313p.json` | 3.13 / pytest (step 7, whole suite) | 2,300 s | 2,365 s | 2,900 + 30 s |

The outer bounds sum to **8,420 s (2 h 20 min 20 s)**, including stops and excluding the
coordination between allocations. About an hour of payload work is expected. This is not a promise
of when the programme completes.

**Bounds, every allocation:**
- **Per payload:** `CPUQuota=200%`, `MemoryMax=6G`, `MemorySwapMax=0`, `OOMPolicy=stop`, `Nice=19`,
  `CUDA_VISIBLE_DEVICES` empty, no GPU.
- **Space:** one active Space selection, and at most two pytest workers in total.
- **Others:** ELSPETH keeps priority, and Sultai's GPU reservation is untouched.

**Ordering:** strictly serial. Each next allocation needs a separate Governance grant, and launches
**only if** the previous one:
- produced its actual expected results;
- has a verified worktree identity after the run;
- has independent cleanup proof;
- was released explicitly by the owner and verified by Governance.

Any failure or abort stops the sequence. There is **no retry and no rerun to green**. Choosing G-2
reserves none of the four allocations.

### Setup and identity: `G/gate_worktree.sh` (replaces the relay's earlier prelaunch block)

The earlier expanded prelaunch block is **withdrawn**. It applied a patch to a detached base and wrote
a tree with a throwaway index. Its pipelines did not propagate a git failure, and its unconditional
cleanup could mask a prior status. The clean committed checkout removes both the patch application
and the throwaway index.

`G/gate_worktree.sh` takes one action. Every command's exit status is checked explicitly, and every
identity is compared with its expected value. A failed observation fails; empty output from a failed
command is never read as clean. It prints `OK <action> …` and exits 0 only when every check passed;
otherwise it prints `FAIL: …` to stderr and exits 1.

- **`create`** (first allocation only, under it):
  1. checks that the topic worktree belongs to the vehicle module (`--git-common-dir`) and that
     `7a87eb82` is a commit;
  2. checks that the gate worktree neither exists nor is registered;
  3. runs `git worktree add --detach <gate worktree> 7a87eb82…`;
  4. then `verify`.
- **`verify`** (before and after every allocation):
  - HEAD = `7a87eb82…`, its parent = `f75420c…` and its tree = `ccc2782e…`;
  - HEAD detached: `symbolic-ref` exits 1, and any other exit fails;
  - `git diff --cached --quiet` and `git diff --quiet` both exit 0 (1 is a difference, more than 1 an
    error; both fail);
  - `git status --porcelain=v1 --untracked-files=all` succeeds and is empty;
  - `git diff f75420c` succeeds into a temporary file, whose sha256 is `0d4da11e…`.
- **`remove`** (after the last allocation, with evidence preserved):
  1. `verify`;
  2. `timeout 60 git worktree remove <gate worktree>`, **not forced**: a clean worktree needs no
     force;
  3. checks that the path is gone and no longer registered.

Ignored files (`__pycache__/` and the like) don't count as untracked. Anything else a step leaves
behind fails `verify` after the run and blocks the next allocation.

### Pre-launch, every allocation (within 60 s of launch, under that allocation)

```sh
bash /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/gate_worktree.sh create   # G312s only; G312p, G313s, G313p use: ... gate_worktree.sh verify
cd /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate && sha256sum -c --strict SHA256SUMS
cd /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7 && sha256sum -c --strict SHA256SUMS
```

**Each must exit 0. Then check:**
- that the allocation's evidence directory, its `<x>-supervisor.out` and its unit names are absent;
- admission: MemAvailable ≥ 16 GiB; CPU busy ≤ 50% (unknown refuses); load1 ≤ 12; no matching
  Space workload, unclassified unreadable process, Space unit or container.

### Exact launch commands (one per allocation, in order)

```sh
systemd-run --user --no-block --collect --unit=space-vehicle-b-supervisor-g312s-1 -p RuntimeMaxSec=900 -p KillMode=control-group -p TimeoutStopSec=30 -p Nice=19 -p Environment=CUDA_VISIBLE_DEVICES= -p "WorkingDirectory=/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate" -p "StandardOutput=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g312s-supervisor.out" -p "StandardError=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g312s-supervisor.out" /usr/bin/python3 "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/supervise.py" "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/spec-G312s.json"
systemd-run --user --no-block --collect --unit=space-vehicle-b-supervisor-g312p-1 -p RuntimeMaxSec=3600 -p KillMode=control-group -p TimeoutStopSec=30 -p Nice=19 -p Environment=CUDA_VISIBLE_DEVICES= -p "WorkingDirectory=/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate" -p "StandardOutput=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g312p-supervisor.out" -p "StandardError=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g312p-supervisor.out" /usr/bin/python3 "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/supervise.py" "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/spec-G312p.json"
systemd-run --user --no-block --collect --unit=space-vehicle-b-supervisor-g313s-1 -p RuntimeMaxSec=900 -p KillMode=control-group -p TimeoutStopSec=30 -p Nice=19 -p Environment=CUDA_VISIBLE_DEVICES= -p "WorkingDirectory=/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate" -p "StandardOutput=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g313s-supervisor.out" -p "StandardError=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g313s-supervisor.out" /usr/bin/python3 "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/supervise.py" "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/spec-G313s.json"
systemd-run --user --no-block --collect --unit=space-vehicle-b-supervisor-g313p-1 -p RuntimeMaxSec=2900 -p KillMode=control-group -p TimeoutStopSec=30 -p Nice=19 -p Environment=CUDA_VISIBLE_DEVICES= -p "WorkingDirectory=/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate" -p "StandardOutput=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g313p-supervisor.out" -p "StandardError=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g313p-supervisor.out" /usr/bin/python3 "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/supervise.py" "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/spec-G313p.json"
```

**Each payload is** `<lane interpreter> G/gate_lane.py <lane> G/evidence-<X> 551 <phase>`. It runs in
the gate worktree, inside a transient unit named from the spec's `unit_prefix`
(`space-vehicle-b-g312s`, `-g312p`, `-g313s` or `-g313p`). The full payload lines and step commands
are in `B-sel1/G-RELAY-FINAL.md`.

### Monitoring, abort and pass

**Monitoring and abort** are the v7 supervisor's, as qualified by K:
- a sample every 5 s;
- an abort on an `oom_kill`, on MemAvailable < 10 GiB, on CPU busy > 85% or load1 > 20 for 3
  samples, on a failed lookup, or on the deadline;
- `RuntimeMaxSec` as the backstop;
- an abort is never a test result.

**Pass, per allocation:**
- **Supervisor:** exit 0; `SERVICE_RESULT=success`, `EXIT_STATUS=0`, `oom_kill` 0; cleanup verified;
  post-run identity unchanged.
- **Worktree:** `gate_worktree.sh verify` exits 0 after the run.
- **Gate:** `<lane>-<phase>-gate.json` shows every expectation met, with no worker crash.
- **Pytest phase:** the independently parsed JUnit is 551 unique cases, with 0 failures, errors and
  skips.

### Evidence, cleanup and release

**Evidence:**
- `G/evidence-<X>/`: the supervisor log, READY, TERMINAL, samples, payload output, step outputs,
  `<lane>-<phase>-gate.json`, `junit.xml` (pytest phases), summary and RELEASE;
- `G/<x>-supervisor.out`;
- the pre-launch and post-run records, and an owner release per allocation.

**Cleanup and release, as for K and S1.** The supervisor proves its unit gone. The owner checks
independently that none of these remains:
- a Space unit, cgroup or container;
- a token process;
- an unreadable process newer than the launch;
- a helper or monitor.

The owner then releases explicitly. The slot is free only after Governance's verification. An exit 4,
or any cleanup that can't be verified, keeps the slot.

**After the last allocation,** with its evidence preserved, run `gate_worktree.sh remove`. If any
phase fails, the worktree is kept for the evidence review, and its removal is a separate step.

## 5. After the gate (each its own step; nothing pre-authorised)

1. **Final independent review** of the actual commit `7a87eb82` (its diff against `f75420c`) and the
   evidence of all four phases.
2. **Qualification:** `7a87eb82` is qualified only after both full lanes pass and that review passes.
   There is no second commit; the gated SHA is the one published.
3. **Publication** — push of `codex/39-take-by-rename`, the PR (`G/PR_BODY.md`, filled from the
   evidence), hosted CI, merge — needs **John's approval**.
4. **Contract:** `G/CONTRACT-PACKAGE-B.md`, as corrected, goes to the chassis after the merge.

## 6. Review index (`/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/reviews/`)

| round | file | sha256 | verdict |
|---|---|---|---|
| r1 | `B-final-package-r1.md` (recovered verbatim from the transcript; see its header) | `29e38fe88115e3ac807325c649669398b35041bde08293b51617a1d8e4a8c419` | request changes, no P1: contract overclaims, hidden xdist retries, README/ADR precision, tree identity, worktree removal, arithmetic |
| r2 | `B-final-package-r2.md` | `20be1e14f1a28ddd15de24faada936cfde20778e4ad3263d97f92d22ed379068` | request changes, one P2: crash detection missed the xdist diagnostic |
| r3 | `B-final-package-r3.md` | `7ba6b71f47d36fb5d7f5bb75c418ebb9402293858ef6a0cff52bfd14211d2541` | approve: crash detection, the `-q` finding, manifest `0dc258a8…` |
| r4 | `B-final-package-r4.md` | `3043f59c5b3a0df8f6d40583e3288e90c653e0bb3c0e7036754f2c1c8b4ea9ba` | approve: the quiet-console wording; manifest `bbfd222b…` |
| r5 | `B-final-package-r5.md` | `eb3b9ab30ee629ae4ef7274beaa31fb1da5347b3048b2bb6f52eb430f022343b` | approve with changes, one P3: `gate_worktree.sh` ignored a failed removal of its temporary file. Fixed: both removals are now checked, keeping the original failure. Otherwise it confirmed the commit's identity, the repinned specs, the helper's fail-closed behaviour, non-forced removal, this proposal, the relay and manifest `02631b87…` |
| r6 | `B-final-package-r6.md` | (pending) | confirmation of the P3 fix and this row only |

Earlier reviews: `B-impl-candidate-3.md` (`41da8155ed3f5b16bb4d378fe6c0e896f915f8505d84bd426670b29a478fbe07`,
implementation approved) and `B-supervisor-v7.md`
(`3742b257d663fef61630af405aac4c0cd00d736fb85b7fe6a3af1e7c401b43be`, supervisor approved).

Issue #42 stays separate.
