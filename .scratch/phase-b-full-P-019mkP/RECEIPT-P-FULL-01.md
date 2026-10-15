# SPACE-20261011-P-FULL-01: result, cleanup and release receipt (chassis, 2026-10-11)

**Grant:** SPACE-20261011-P-FULL-01 (master §25).
**Holder:** `session_019mkPNN5J3Atit9tUA6zrNY` / `[8a7d49]`.
**Command, run once from `/home/john/space_chassis`:** `nice -n 19 python3 .scratch/phase-b-full-P-019mkP/full.py SPACE-20261011-P-FULL-01`.
**Driver:** `full.py` `2557d326…`, unchanged. **Launcher:** `91a813dc…`, unchanged. **Evidence:** `full/`, fresh.
**Selection:** `python3 -m pytest -q -p no:cacheprovider -n 2`, no node filter, run in the adoption worktree.

| | |
|---|---|
| identity before / after | P `af671d04…`; vehicle `f443996…` clean; test file `3b917de3…`; no unstaged or untracked paths: **exact at both** |
| admission (01:26:16Z) | 42,171 MiB available, load1 2.54, CPU 14.7 %; no competitors, Compose projects or Space scopes |
| scope readback before go | cpu.max `200000 100000`, memory.max `8589934592`, memory.events all 0 |
| SIGINT | the launcher inherited `SIG_IGN` and restored `SIG_DFL` before exec; **0** scope processes ignored SIGINT in any sample |
| nice | every scope process was at nice 19 in the 01:26:25Z check and in all 374 samples |
| released / ended | 01:26:17Z / 01:57:30Z (31 min 13 s; outer deadline 5,400 s, not reached) |
| monitor | 374 samples; min 41,217 MiB available, max load1 5.28, max CPU 27.3 %, scope peak 3.16 GB; **0 OOM**; no threshold crossed |
| **pytest (raw)** | **rc 0: 1941 passed**, 0 failed, 0 errors, 0 skipped (progress characters: 1941 `.`); log `ea5741cf…` |
| **supervision** | **held**: no abort or failure reasons; supervisor rc 0 |
| cleanup | verified by the supervisor: scope terminated (not-found and inactive), cgroup removed, monitor ended, sh rc 0, no helpers |

**Checked independently after the run:** the scope reads `LoadState=not-found ActiveState=inactive`, and no
`space-chassis-pfull-*` cgroup or active `space-chassis-*` scope exists. No launcher, full.py, xdist, execnet or helper
process remains. The worktree is still exactly P, and R (`dd16772e`) and the R2 work in progress stay preserved.

**Qualification:** with the 592-pass root result on the same unchanged tree (SPACE-20261011-P-01), P `af671d04…` now
has a passing root suite and a passing whole suite (1941). The earlier full failure's cause was established by DIAG-02.
That failure is preserved, not overwritten. Nothing was committed or published; any commit, landing or push stays
under the existing holds.

Evidence sha256:

| file | sha256 |
|---|---|
| receipt.jsonl | `e319fe44…` |
| monitor.jsonl | `0b7abe61…` |
| launcher.json | `d5e9fc70…` |
| pytest.log | `ea5741cf…` |
| full.supervisor.out | `344d8e3a…` |

**RELEASE: the chassis releases the SPACE-20261011-P-FULL-01 reservation.** There was no retry, no R, build or live
run, and no product or test edit.
