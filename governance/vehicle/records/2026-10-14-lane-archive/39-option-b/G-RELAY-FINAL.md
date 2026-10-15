# Option B committed-head gate (G-2) — relay record for Governance (vehicle line, 2026-10-12)

Generated from the frozen specs; restates `G/SHA256SUMS` with full values. It sits outside the manifest and grants nothing. The previous relay, whose prelaunch block Governance rejected in §37, is superseded (`G/superseded/G-RELAY-FINAL.r4.md`) and must not be used.

## Identities

- **Local candidate commit (UNQUALIFIED / UNPUBLISHED):** `7a87eb82cfef55dcc74248df41720883587ca7af`; parent `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f`; tree `ccc2782e350a6b9abe33d19db6884ac3fb82ec95`; branch `codex/39-take-by-rename` in `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9`, no upstream.
- Base-relative diff (`git diff f75420c` at `7a87eb82cfef55dcc74248df41720883587ca7af`) = `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-candidate-5/B-candidate-5.diff`, sha256 `0d4da11e9cbe56fcad7e09c48e027340d41f1bae438adfe8cce9dcc889a951d0`.
- Gate worktree (to be created by G312s): `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/gate-C-7a87eb8`, a clean detached checkout of `7a87eb82cfef55dcc74248df41720883587ca7af`.
- Interpreters: `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.12/bin/python` (3.12.3) and `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.13/bin/python` (3.13.15). Lock `requirements-dev.lock` sha256 `6d1271054b0f9af2690b6b6427da5db04008912cb32ff7607cb31c45f611eac1`; identical `pip freeze` sha256 `4535babcc5a2e230b30d864b4af05d1838aafd5f4b5c885710b30fcd0709b4cb`; ruff 0.16.8, pytest 9.0.1, pytest-xdist 3.8.0.

## Frozen package `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/SHA256SUMS` — sha256 `4956e7aec8001a75df7d704fba24fe8816809e4f6f94277241c79cf3deee4b6d`

```
041db2859507f1df0b04ec2b9841489720056dba4b0a8bd1282afc4d02af5cb8  gate_lane.py
f73c046cdf62061ecc23da75aa31aa09a985e36734f8e324c838e79b3b1e8422  gate_worktree.sh
eed72a9206e09a9b99e2eca3708c80671956bb388b3fe84662ec9f2f1b94a994  spec-G312s.json
466ed9a75a283c66771f141a3ca5965323cceafd48fc3c9fc7f4fd3f2bd26aba  spec-G312p.json
c325a42359154c91271b7f7cb91b5431d7d6dc500ee66d241212716e8f8ba2e6  spec-G313s.json
39cea742a15d5b9835493765e95558db4fbf6edd0d37d1b6feebf905acc04699  spec-G313p.json
408f326f2e940b72f5f10c5b1a29bfe710fea4690ce6ead7f76c69215ab8da65  interpreters.txt
0e7bb0312d5bc4d007b6fcee103d40e61b442c72eb0045c4307e780b356f0985  COMMIT_MESSAGE.txt
5049493bcdc9f1cb43545fcbdd83ec0a04e77005aa21edbd5f07bcddde38638c  PR_BODY.md
5f2c329527395fc12d75a53ac946fc0ed0315382d996759f78c7154efd979705  CONTRACT-PACKAGE-B.md
d779b632189ca7849b93dc2ced95ce7f7f9915d4011e160d4ff97d05b88c8bac  PROPOSAL-G.md
0d4da11e9cbe56fcad7e09c48e027340d41f1bae438adfe8cce9dcc889a951d0  ../../B-candidate-5/B-candidate-5.diff
790982da4180f092a991ba7411094e06a8f03beac9d54ea92b45d743cc3f621c  ../../B-candidate-5/delta-4-to-5.diff
```

## Supervisor v7 (K-qualified), unchanged

- `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/SHA256SUMS`: `422ff9aa4ed7573fc9e79117f57e7135ac10c7f8cdfde2d44fcee53b78f55b32`
- `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/supervise.py`: `a702a4e1381f39a40385a4dcc4d159b342e13e3ee7c917cc46cc7f6b3314372b`
- `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/launch.py`: `be38cdb6bd73ea24aff1ad9338cba1d38732dfc316b5b4f68469a5874a250aae`
- `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/record.py`: `1ab08ff4818ceb78ef3e0261e9415fcf9982ab28c0ca99c851ba0ded47df2c33`
- `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/run_controls.py`: `fe6ea874c3de127311b36ac0e514d46975ba2f88f50d0f9f8b0b42f59fcd331a`

## Reviews (`/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/reviews/`)

- `B-impl-candidate-3.md`: `41da8155ed3f5b16bb4d378fe6c0e896f915f8505d84bd426670b29a478fbe07`
- `B-supervisor-v7.md`: `3742b257d663fef61630af405aac4c0cd00d736fb85b7fe6a3af1e7c401b43be`
- `B-final-package-r1.md`: `29e38fe88115e3ac807325c649669398b35041bde08293b51617a1d8e4a8c419`
- `B-final-package-r2.md`: `20be1e14f1a28ddd15de24faada936cfde20778e4ad3263d97f92d22ed379068`
- `B-final-package-r3.md`: `7ba6b71f47d36fb5d7f5bb75c418ebb9402293858ef6a0cff52bfd14211d2541`
- `B-final-package-r4.md`: `3043f59c5b3a0df8f6d40583e3288e90c653e0bb3c0e7036754f2c1c8b4ea9ba`
- `B-final-package-r5.md`: `eb3b9ab30ee629ae4ef7274beaa31fb1da5347b3048b2bb6f52eb430f022343b`
- `B-final-package-r6.md`: `3d494e08c90635ab809c808be00ff3adaf583e6a35ff05f0e259a15a7cb91847`

r6 approves the package at manifest `4956e7ae…`. `PROPOSAL-G.md` §6 (inside the manifest) still shows r6 as pending; it was not re-frozen for that status line.

## Run records already held

- `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7-K1-prelaunch.txt`: `4de53749bbd132f80e50dc7ea13c8605a4952d14d9df374ec20147b8691059f9`
- `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7-K1-postrun.txt`: `c2edea86b56e8a5ec5a43e0075a268568d531a4883e1b68a19dbffc74a104829`
- `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7-K1-OWNER-RELEASE.md`: `06c4483f6c506eb72470bb0521ca3d090b98a72e6c68c0a3387f141bc5a8ba59`
- `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7-S1-prelaunch.txt`: `7d11f97ce4cc911c0c365b51e4cb387fe07fece46bc1843d39a68b6d1df32aed`
- `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7-S1-postrun.txt`: `c0b5963133ede7d1778ff4e81411c49105591aa282fd38c827b163effd69d253`
- `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7-S1-OWNER-RELEASE.md`: `5d9021cb5047fd47c9553de2594aaf4e1e8adcaf8b12d4473c1ab88e94dea059`

S1 is evidence that its **25 selected tests** passed on this code (JUnit 25/0/0/0, 25.752 s, peak 559 MiB). It is not evidence for the other 526 cases, the full gate, or any contract guarantee.

## Setup, identity and cleanup: `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/gate_worktree.sh` (sha256 `f73c046cdf62061ecc23da75aa31aa09a985e36734f8e324c838e79b3b1e8422`)

Every command's exit status is checked and every identity compared; it prints `OK …` and exits 0 only if all pass, else `FAIL: …` and exit 1. See `PROPOSAL-G.md` §4.

```
bash /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/gate_worktree.sh create   # under G312s only, before its launch
bash /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/gate_worktree.sh verify   # before G312p, G313s, G313p, and after every allocation
bash /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/gate_worktree.sh remove   # after the last allocation, evidence preserved
cd /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate && sha256sum -c --strict SHA256SUMS   # every allocation, exit 0
cd /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7 && sha256sum -c --strict SHA256SUMS   # every allocation, exit 0
```

## The four allocations, strictly serial, each separately granted

### G312s — `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/spec-G312s.json` sha256 `eed72a9206e09a9b99e2eca3708c80671956bb388b3fe84662ec9f2f1b94a994`

- Outer unit `space-vehicle-b-supervisor-g312s-1`; payload unit prefix `space-vehicle-b-g312s`; id `SPACE-VEHICLE-B-G312s`.
- Expect HEAD `7a87eb82cfef55dcc74248df41720883587ca7af`, base `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f`, diff `0d4da11e9cbe56fcad7e09c48e027340d41f1bae438adfe8cce9dcc889a951d0`; workdir `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/gate-C-7a87eb8`.
- Phase `static`; GO deadline 300 s; payload RuntimeMaxSec 365 s; outer RuntimeMaxSec 900 s + 30 s stop.
- CPUQuota 200%, MemoryMax 6G, MemorySwapMax 0, Nice 19, CUDA_VISIBLE_DEVICES empty; admission MemAvailable ≥ 16384 MiB, CPU busy ≤ 50%, load1 ≤ 12; abort MemAvailable < 10240 MiB, CPU > 85% or load1 > 20 for 3 samples, oom_kill, failed lookup, deadline.
- Fresh paths (must be absent before launch): `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G312s/`, `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g312s-supervisor.out`. Static phase: no JUnit.

Launch:
```
systemd-run --user --no-block --collect --unit=space-vehicle-b-supervisor-g312s-1 -p RuntimeMaxSec=900 -p KillMode=control-group -p TimeoutStopSec=30 -p Nice=19 -p Environment=CUDA_VISIBLE_DEVICES= -p "WorkingDirectory=/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate" -p "StandardOutput=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g312s-supervisor.out" -p "StandardError=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g312s-supervisor.out" /usr/bin/python3 "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/supervise.py" "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/spec-G312s.json"
```
Payload (started by the supervisor, cwd = gate worktree):
```
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.12/bin/python /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/gate_lane.py 3.12 /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G312s 551 static
```
Gate steps it runs (cwd `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/gate-C-7a87eb8`; each step's output to `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G312s/3.12-<step>.out`):
```
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.12/bin/python -m ruff check . --no-cache    # ruff: exit 0
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.12/bin/python tools/check_vehicle.py    # lint: exit 0 and output contains `COMPOSES, with 273 declared debt(s)`
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.12/bin/python tools/check_vehicle.py --strict    # strict: exit 2
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.12/bin/python tools/plant.py --readiness    # readiness: exit 0
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.12/bin/python tools/plant.py --build-order    # build-order: exit 0
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.12/bin/python tools/measure_clock.py --samples 10    # measure: exit 0
```
Pass: supervisor exit 0, SERVICE_RESULT=success, EXIT_STATUS=0, oom_kill 0, cleanup verified; `gate_worktree.sh verify` exit 0 after the run; `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G312s/3.12-static-gate.json` passed. Then the owner's independent cleanup check, explicit owner release and Governance verification before the next allocation is even considered. No retry; any failure, abort or exit 4 stops the sequence; unverified cleanup keeps the slot.

### G312p — `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/spec-G312p.json` sha256 `466ed9a75a283c66771f141a3ca5965323cceafd48fc3c9fc7f4fd3f2bd26aba`

- Outer unit `space-vehicle-b-supervisor-g312p-1`; payload unit prefix `space-vehicle-b-g312p`; id `SPACE-VEHICLE-B-G312p`.
- Expect HEAD `7a87eb82cfef55dcc74248df41720883587ca7af`, base `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f`, diff `0d4da11e9cbe56fcad7e09c48e027340d41f1bae438adfe8cce9dcc889a951d0`; workdir `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/gate-C-7a87eb8`.
- Phase `pytest`; GO deadline 3000 s; payload RuntimeMaxSec 3065 s; outer RuntimeMaxSec 3600 s + 30 s stop.
- CPUQuota 200%, MemoryMax 6G, MemorySwapMax 0, Nice 19, CUDA_VISIBLE_DEVICES empty; admission MemAvailable ≥ 16384 MiB, CPU busy ≤ 50%, load1 ≤ 12; abort MemAvailable < 10240 MiB, CPU > 85% or load1 > 20 for 3 samples, oom_kill, failed lookup, deadline.
- Fresh paths (must be absent before launch): `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G312p/`, `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g312p-supervisor.out`. JUnit `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G312p/junit.xml` must parse to 551 unique cases, 0 failures, errors and skips.

Launch:
```
systemd-run --user --no-block --collect --unit=space-vehicle-b-supervisor-g312p-1 -p RuntimeMaxSec=3600 -p KillMode=control-group -p TimeoutStopSec=30 -p Nice=19 -p Environment=CUDA_VISIBLE_DEVICES= -p "WorkingDirectory=/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate" -p "StandardOutput=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g312p-supervisor.out" -p "StandardError=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g312p-supervisor.out" /usr/bin/python3 "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/supervise.py" "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/spec-G312p.json"
```
Payload (started by the supervisor, cwd = gate worktree):
```
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.12/bin/python /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/gate_lane.py 3.12 /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G312p 551 pytest
```
Gate steps it runs (cwd `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/gate-C-7a87eb8`; each step's output to `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G312p/3.12-<step>.out`):
```
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.12/bin/python -m pytest -n 2 --max-worker-restart=0 -q -o addopts= -rs -p no:cacheprovider --junitxml=/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G312p/junit.xml    # pytest: exit 0; JUnit 551/0/0/0; no xdist crash line
```
Pass: supervisor exit 0, SERVICE_RESULT=success, EXIT_STATUS=0, oom_kill 0, cleanup verified; `gate_worktree.sh verify` exit 0 after the run; `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G312p/3.12-pytest-gate.json` passed. Then the owner's independent cleanup check, explicit owner release and Governance verification before the next allocation is even considered. No retry; any failure, abort or exit 4 stops the sequence; unverified cleanup keeps the slot.

### G313s — `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/spec-G313s.json` sha256 `c325a42359154c91271b7f7cb91b5431d7d6dc500ee66d241212716e8f8ba2e6`

- Outer unit `space-vehicle-b-supervisor-g313s-1`; payload unit prefix `space-vehicle-b-g313s`; id `SPACE-VEHICLE-B-G313s`.
- Expect HEAD `7a87eb82cfef55dcc74248df41720883587ca7af`, base `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f`, diff `0d4da11e9cbe56fcad7e09c48e027340d41f1bae438adfe8cce9dcc889a951d0`; workdir `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/gate-C-7a87eb8`.
- Phase `static`; GO deadline 300 s; payload RuntimeMaxSec 365 s; outer RuntimeMaxSec 900 s + 30 s stop.
- CPUQuota 200%, MemoryMax 6G, MemorySwapMax 0, Nice 19, CUDA_VISIBLE_DEVICES empty; admission MemAvailable ≥ 16384 MiB, CPU busy ≤ 50%, load1 ≤ 12; abort MemAvailable < 10240 MiB, CPU > 85% or load1 > 20 for 3 samples, oom_kill, failed lookup, deadline.
- Fresh paths (must be absent before launch): `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G313s/`, `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g313s-supervisor.out`. Static phase: no JUnit.

Launch:
```
systemd-run --user --no-block --collect --unit=space-vehicle-b-supervisor-g313s-1 -p RuntimeMaxSec=900 -p KillMode=control-group -p TimeoutStopSec=30 -p Nice=19 -p Environment=CUDA_VISIBLE_DEVICES= -p "WorkingDirectory=/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate" -p "StandardOutput=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g313s-supervisor.out" -p "StandardError=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g313s-supervisor.out" /usr/bin/python3 "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/supervise.py" "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/spec-G313s.json"
```
Payload (started by the supervisor, cwd = gate worktree):
```
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.13/bin/python /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/gate_lane.py 3.13 /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G313s 551 static
```
Gate steps it runs (cwd `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/gate-C-7a87eb8`; each step's output to `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G313s/3.13-<step>.out`):
```
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.13/bin/python -m ruff check . --no-cache    # ruff: exit 0
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.13/bin/python tools/check_vehicle.py    # lint: exit 0 and output contains `COMPOSES, with 273 declared debt(s)`
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.13/bin/python tools/check_vehicle.py --strict    # strict: exit 2
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.13/bin/python tools/plant.py --readiness    # readiness: exit 0
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.13/bin/python tools/plant.py --build-order    # build-order: exit 0
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.13/bin/python tools/measure_clock.py --samples 10    # measure: exit 0
```
Pass: supervisor exit 0, SERVICE_RESULT=success, EXIT_STATUS=0, oom_kill 0, cleanup verified; `gate_worktree.sh verify` exit 0 after the run; `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G313s/3.13-static-gate.json` passed. Then the owner's independent cleanup check, explicit owner release and Governance verification before the next allocation is even considered. No retry; any failure, abort or exit 4 stops the sequence; unverified cleanup keeps the slot.

### G313p — `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/spec-G313p.json` sha256 `39cea742a15d5b9835493765e95558db4fbf6edd0d37d1b6feebf905acc04699`

- Outer unit `space-vehicle-b-supervisor-g313p-1`; payload unit prefix `space-vehicle-b-g313p`; id `SPACE-VEHICLE-B-G313p`.
- Expect HEAD `7a87eb82cfef55dcc74248df41720883587ca7af`, base `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f`, diff `0d4da11e9cbe56fcad7e09c48e027340d41f1bae438adfe8cce9dcc889a951d0`; workdir `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/gate-C-7a87eb8`.
- Phase `pytest`; GO deadline 2300 s; payload RuntimeMaxSec 2365 s; outer RuntimeMaxSec 2900 s + 30 s stop.
- CPUQuota 200%, MemoryMax 6G, MemorySwapMax 0, Nice 19, CUDA_VISIBLE_DEVICES empty; admission MemAvailable ≥ 16384 MiB, CPU busy ≤ 50%, load1 ≤ 12; abort MemAvailable < 10240 MiB, CPU > 85% or load1 > 20 for 3 samples, oom_kill, failed lookup, deadline.
- Fresh paths (must be absent before launch): `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G313p/`, `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g313p-supervisor.out`. JUnit `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G313p/junit.xml` must parse to 551 unique cases, 0 failures, errors and skips.

Launch:
```
systemd-run --user --no-block --collect --unit=space-vehicle-b-supervisor-g313p-1 -p RuntimeMaxSec=2900 -p KillMode=control-group -p TimeoutStopSec=30 -p Nice=19 -p Environment=CUDA_VISIBLE_DEVICES= -p "WorkingDirectory=/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate" -p "StandardOutput=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g313p-supervisor.out" -p "StandardError=file:/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/g313p-supervisor.out" /usr/bin/python3 "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/v7/supervise.py" "/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/spec-G313p.json"
```
Payload (started by the supervisor, cwd = gate worktree):
```
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.13/bin/python /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/gate_lane.py 3.13 /home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G313p 551 pytest
```
Gate steps it runs (cwd `/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/gate-C-7a87eb8`; each step's output to `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G313p/3.13-<step>.out`):
```
/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/venv3.13/bin/python -m pytest -n 2 --max-worker-restart=0 -q -o addopts= -rs -p no:cacheprovider --junitxml=/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G313p/junit.xml    # pytest: exit 0; JUnit 551/0/0/0; no xdist crash line
```
Pass: supervisor exit 0, SERVICE_RESULT=success, EXIT_STATUS=0, oom_kill 0, cleanup verified; `gate_worktree.sh verify` exit 0 after the run; `/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate/evidence-G313p/3.13-pytest-gate.json` passed. Then the owner's independent cleanup check, explicit owner release and Governance verification before the next allocation is even considered. No retry; any failure, abort or exit 4 stops the sequence; unverified cleanup keeps the slot.


## What has and has not run since the previous relay (§37 work)

**Actions under §37:** one local commit `7a87eb82…` in the topic worktree (`git add` of the four paths by name; `git write-tree` to check the index tree; `git commit -F G/COMMIT_MESSAGE.txt`). A first attempt stopped **before** committing on my own staged-set check (a locale `sort` order artifact); nothing was committed by it, and the re-check with `LC_ALL=C` passed.

**Helper-only preparation checks (none is a repository gate, test, collection, supervisor, systemd or qualification run):**
1. Read-only git: `rev-parse`, `status --porcelain`, `diff f75420c` into a scratch file and `sha256sum` (= `0d4da11e…`), `diff --cached --quiet`, `config --get core.hooksPath` / `commit.gpgsign`, `ls` of the module's hooks directory, `log -1`, `worktree list`, `cat-file commit HEAD` (message comparison), `rev-parse --abbrev-ref @{upstream}` (none).
2. Reads: MASTER §37; `v7/supervise.py` identity function; the vehicle `.gitignore`, `CONTRIBUTING.md:30–33`, `AGENTS.md:83–85`, `practice.md:39–44,56`; the session transcript (to recover this generator).
3. `bash -n gate_worktree.sh` (syntax only; exit 0), after writing it and again after the r5 P3 fix (both temporary-file removals now checked). `gate_worktree.sh` itself has **not** been run in any mode. No shellcheck is installed.
4. File writes: four G-2 specs repinned (workdir, `expect.head`); G-1 specs, the r4 proposal and the r4 relay moved to `G/superseded/`; `gate_worktree.sh` new; `PROPOSAL-G.md` rewritten; `PR_BODY.md` evidence and review lines updated; `G/SHA256SUMS` re-frozen (13 entries); `CHECKPOINT.md` 27–29; `reviews/B-final-package-r5.md` and `-r6.md`; this file.

**Not run:** `gate_worktree.sh`, worktree creation, any repository gate step, pytest or collection, the supervisor, `systemd-run`, push, PR, publication or pin change.
