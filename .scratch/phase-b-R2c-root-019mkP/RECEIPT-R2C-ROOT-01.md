# SPACE-20261011-R2C-ROOT-01: result, cleanup and release receipt (chassis, 2026-10-11)

Grant SPACE-20261011-R2C-ROOT-01 (master §27). Holder `session_019mkPNN5J3Atit9tUA6zrNY` / `[8a7d49]`. Run once from
`/home/john/space_chassis`: `nice -n 19 python3 .scratch/phase-b-R2c-root-019mkP/root.py SPACE-20261011-R2C-ROOT-01`.
Driver `root.py` `6eac1724…` and launcher `91a813dc…`, both unchanged. Selection:
`python3 -m pytest tests -q -p no:cacheprovider -n 2`. Fresh evidence in `root/`.

| | |
|---|---|
| identity before / after | R2c tree `148a31c4…`; vehicle `f443996…`, clean; test file `3b917de3…`; no unstaged or untracked paths. **Exact at both** |
| admission (03:08:37Z) | 42,048 MiB available, load1 2.48, CPU 13.3 %. No competitors, Compose projects or Space scopes |
| scope readback before go | cpu.max `200000 100000`, memory.max `8589934592`, memory.events all 0 |
| SIGINT / nice | The launcher inherited SIG_IGN and restored SIG_DFL. All scope processes ran at nice 19 in every sample. See the note below |
| released / ended | 03:08:38Z / 03:09:13Z (35 s, against a 600 s deadline) |
| monitor | 8 samples. Lowest available memory 41,705 MiB, max load1 3.07, max CPU 22.2 %, scope peak 247 MB. 0 OOM, no threshold crossed |
| **pytest (raw)** | **rc 0: 617 passed.** 0 failed, 0 errors, 0 skipped. Progress shows 617 `.`. Log sha256 `4ee78bc0…` |
| **supervision** | **held**, with no reasons |
| cleanup | **verified.** The scope was still active when cleanup began, so the supervisor stopped it (stop rc 0). It is now not-found/inactive, its cgroup is removed, the monitor has ended, sh rc 0, and no helpers remain |

**Note: why the scope was still active.** One process outlived pytest in the scope: `sleep 30` (pid 2568394), seen
from 03:08:43Z until cleanup.
- **Source:** the pre-existing root test `tests/test_journal.py::test_a_stream_that_never_ends_times_out`
  (`FAKE_SLEEP="30"`; unchanged since P). Its fake docker sleeps 30 s, and the journal times out at 1 s without
  killing that sleep.
- **What cleanup did:** the supervisor's bounded stop removed the sleep, as designed.
- **On P:** P's root run took 34 s, about as long as the sleep, so it would have ended on its own there.
- **Scope:** this is a test-hygiene leak in an existing test, not an R2c change. I have not fixed it; that is outside
  this grant.

**Note: processes ignoring SIGINT.** Two monitor entries show processes with SIGINT ignored. Both are the background
children (`sh -c 'echo $$ …'` and its `sleep 2`) that R2c's own `test_a_timed_out_group…` deliberately starts with
`&`. A non-interactive sh starts its background jobs with SIGINT ignored, so this is the test's subject, not
inheritance from the driver. Every pytest and xdist process had SIGINT at its default.

**Independent check after the run.** The scope reads `LoadState=not-found ActiveState=inactive`, and no
`space-chassis-r2c-*` cgroup exists. No launcher, driver, xdist, execnet or helper process remains. There are no
active Space scopes and no Compose projects. The worktree is still R2c exactly.

**Bounded conclusion.** R2c has a passing root suite: 617, up from P's 592, the difference being R2c's new root tests.
That advances R2c's root qualification only. The whole-suite, build and live gates remain ungranted. Nothing is
committed or published.

| evidence | sha256 |
|---|---|
| receipt.jsonl | `df6ab6d4…` |
| monitor.jsonl | `d3b0c636…` |
| launcher.json | `c75c84d4…` |
| pytest.log | `4ee78bc0…` |
| root.supervisor.out | `edd1e841…` |

**RELEASE: the chassis releases the SPACE-20261011-R2C-ROOT-01 reservation.** No retry, full-suite, build or live
run, and no product or test edit.
