# Chassis lane status (chassis, 2026-10-14 23:53 AEDT)

Owner: Space Chassis Claude Code `session_019mkPNN5J3Atit9tUA6zrNY`. Written at John's request ("make sure
lane durable and write out a status report"). It supersedes the increment table in
`2026-10-11-phase-b-test-slot-request.md`, which is now marked historical.

**Nothing was run, committed, pushed, published, adopted or re-pinned for this report.** The only changes are:
- this file;
- a pointer line at the top of the 2026-10-11 slot record;
- two new local refs, `refs/preserve/chassis-lane-evidence-2026-10-14` and
  `refs/preserve/chassis-lane-status-2026-10-14`.

Each ref points at a tree, not a commit, so no branch or index moved.

## Identity

| what | value |
|---|---|
| main checkout | `aurora-port` @ `613557528ffc42d4ea8d4ae0a3b3a2c453825ffa` |
| adoption worktree | `.claude/worktrees/vehicle-adoption`, branch `phase-b-adoption` (local), HEAD `be63f93` = published `vehicle-adoption` |
| worktree staged index (top tree) | **R2c `148a31c4951e43c1cdafdf30c15b029dc7e104a8`**, unchanged since 2026-10-11 |
| worktree vehicle gitlink | `f44399645fb2633e695a5d758cb5a41f43fb848c` (unchanged) |
| vehicle `origin/main` | `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f` (#39 tier 1, PR #43, 2026-10-11 21:08) |
| shared Space test slot | **FREE / RELEASED** (master §39, 2026-10-12 01:24; G312s on authorization hold, vehicle-owned) |

## Phase B increments: staged, uncommitted, unpublished

| increment | tree | preserve ref | root | whole suite | build / live |
|---|---|---|---|---|---|
| **P**, the corrections | `af671d04908817e914668750b7cd4f6f74034bf4` | `refs/preserve/phase-b-P-af671d04` | **592 passed** (P-01) | **1941 passed** (P-FULL-01, master §25–26) | not run; P is never run live (its live harness is the uncapped layout) |
| **R2c**, the resource controls, on P | `148a31c4951e43c1cdafdf30c15b029dc7e104a8` | `refs/preserve/phase-b-R2c-148a31c4` | **617 passed** (R2C-ROOT-01, accepted master §28) | **not run** | **not run** |

Superseded trees, kept: R `dd16772e` (`refs/preserve/phase-b-R-dd16772e`), R2 `0471251a`
(`refs/preserve/phase-b-R2-0471251a`) and R2b `3500987c` (`refs/preserve/phase-b-R2b-3500987c`).
Candidates `b29bf8af`, `04dff0be` and `8db6db9f` are kept as diffs and tree listings.

P and R2c stay separate atomic increments. Neither may be committed until the whole-suite gate has passed on
the exact head, or John makes an exception.

## The tier-1 brief wording (#39): correctness review closed; John's approval reserved

| file under `.scratch/tier1-brief-draft/` | sha256 | status |
|---|---|---|
| `brief-wording-tier1-v5.md` | `74b44459de4e061908cb8c66b10e45d1226995a3cd96be7a31db35e1e1faba5b` | frozen, read-only; the final text |
| `review-v5-astra.md` | `db0f5ce65d1d25deb269f54913e952ee9b7049f7a51346661bc15ff16e78e4bb` | **APPROVE** on that exact hash; all five v4 findings resolved; no defects at any level |
| `review-v5-astra.log` | `8cdab57cbef79b19c63485f83158f49f56a1eeb144b48c179d2dffeb2345e249` | Codex session `01a12abc-edee-7e01-883c-a5cc1adbfc49`; one read-only run |
| `brief-wording-tier1-v4.md` / `review-v4-astra.md` | `78d3453e…` / `9c228ea2…` | APPROVE WITH CHANGES; five findings, all applied in v5 |
| `brief-wording-tier1-v2.md` / `review-v2-astra.md` | `9e8b5192…` / `7236e195…` | APPROVE WITH CHANGES |

v5 holds five pieces of text: A and B for `brief/PROTOCOL.md` lines 51–54 and 59–60, C and C′ for line 68
and lines 75–78, and D, a new `docs/brief-claims.md` row. None of it is in the tree.

- **John's final wording approval is reserved.** Emmy cannot grant it, and a peer session cannot either.
- **It lands only with the adoption increment or after it.** That increment is a separate atomic increment
  whose order Governance sets. It must carry:
  - the gitlink moved to `f75420c`;
  - contract §2.2 as adopted;
  - `contract/fake_diode.py::AgentSide.consume` implementing the same quiet rule, with its test.

  None of these exists yet. If adoption comes before R2c's build and live gate, the accepted drivers need
  rebinding to `tests/test_vehicle_config.py` as changed at `f75420c` (+141 lines; it is now bound to
  `3b917de3…`).
- **Vehicle-owned and open.** We have neither resolved nor taken over these. They go to the vehicle line
  through Governance, and none of them blocks adopting tier 1.
  - **V-1:** contract §2.2 says intake is "destructive and atomic". Only the rename is atomic.
  - **V-2:** contract §2.2 says a batch is "claimed at the window's next read", with no condition.
  - **V-3:** contract §2.3 says "Every command produces exactly one file". This is older than tier 1:
    - a deferred command produces two files;
    - an owed answer can be written twice with the same `seq`, or given up past 256;
    - a lost batch produces none.
- **Qualifications for John.**
  - Host-crash "at most once" assumes that a flush to the loop-mounted volume image reaches the disk. This
    has not been verified.
  - Avoiding loss depends on the agent's own discipline, which the world does not enforce:
    - one writer;
    - publishing by rename;
    - waiting for the far side's cleared copy.
  - There is no chassis evidence on `f75420c`. The q1–q3 re-run and the ≥30 gate runs need a slot grant.
  - The figure 256 is the vehicle's `OBLIGATIONS_PER_WINDOW`.
  - Option B is not implemented on vehicle `main`, nor tested, adopted or qualified by the chassis.

## Vehicle-line files held for the chassis to commit verbatim (by path, when gates allow)

| file | sha256 | asks the chassis for |
|---|---|---|
| `governance/vehicle/records/2026-10-11-39-claim-race-decision-memo.md` | `0417d666cc5ef86e02c33f4909ea12af4938ac6a7ea27255fce85d1b7c33e2b1` | nothing now |
| `governance/vehicle/records/2026-10-11-39-tier1-adoption-package.md` | `483d47de01ade46d3e6bbea16f5ce04bd93ec7b7e3d5d1dab26336275850a360` | tier-1 adoption: gitlink, contract §2.2, the fixture quiet rule; the brief text is John's |
| `governance/vehicle/records/2026-10-12-23-clock-seam-slot-request.md` | `d56a71b4542f8adc3c2799b573a383430bbe59af25927c6f787b19b92aaee558` | **nothing until the vehicle merges #23** (its §7 interface change); its slot requests come after #39's G-2 |

The tracked vehicle files `decisions.md`, `open.md` and `snapshot.md` also carry uncommitted vehicle edits.
They stay as they are.

## Chassis records (untracked, on disk)

| file | sha256 |
|---|---|
| `2026-10-11-phase-b-test-slot-request.md` (now marked historical) | `57bdcd900e8f8cfb368fc5489b287bbfd925d5704121a3c0efde03f4c2e4bcf8` |
| `2026-10-11-serial-build-readiness.md` | `127c653e8611c795a4146e9dcab10d4ad655420fc7ca0e0d185436fa866ef46f` |
| this file | in the ref below |

## Durability

**Committed state is unchanged.** The lane's state now survives as follows:

1. **Staged trees.** P and R2c, with R, R2 and R2b, are held by the five `refs/preserve/phase-b-*` refs.
   Garbage collection treats those refs as reachable, whatever happens to the worktree's index.
2. **Evidence.** `.scratch/` is gitignored, and the untracked records above exist only on disk. All of it is
   now in the object store as the tree **`e21b1140cb842f438403dc6555c1cecb31417776`**, held by
   `refs/preserve/chassis-lane-evidence-2026-10-14`. It has 189 files:
   - `.scratch/tier1-brief-draft/`, everything: v1–v5, the prompts, the three reviews and their logs;
   - every `.scratch/phase-b-*` file and directory: candidate and increment diffs, tree listings, reviews,
     gate drivers, supervisor output and receipts;
   - the two chassis records;
   - the three vehicle records.

   I checked the preserved bytes of v5, its closure review, the vehicle package and the slot record against
   the sha256 values above.

   Before preserving, I scanned for key-shaped strings. The only matches are the test sentinels already in
   tracked test sources, so the logs carry no secret.

   Not included:
   - `docs/plans/`, which is outside this lane;
   - the vehicle submodule;
   - any `.env`.
3. **This report** is preserved by `refs/preserve/chassis-lane-status-2026-10-14`, a tree holding this file
   alone.

To recover a file: `git cat-file blob refs/preserve/chassis-lane-evidence-2026-10-14:<path>`.

## Waiting on

| item | needs | from |
|---|---|---|
| R2c whole suite | prepare an R2c-bound full driver from `full.py` `2557d326…`, and review it before any grant; **not prepared yet, waiting for a go** | John / Emmy |
| R2c whole-suite run | a grant for that reviewed driver, at one selection, ≤2 workers, nice 19 | Governance |
| R2c build and live | a separate grant (`2026-10-11-serial-build-readiness.md`) | Governance |
| commit of P and R2c | whole-suite gate on the exact head, then commit by path | after the above |
| tier-1 adoption increment | Governance to order it against R2c's live gate; then build the increment (gitlink, §2.2, fixture rule and test, brief text) | Governance; John for the brief text |
| tier-1 chassis evidence | q1–q3 and ≥30 gate runs on `f75420c` | a slot grant |
| V-1 to V-3 | vehicle wording | vehicle line, through Governance |
| #23 clock seam | nothing from the chassis until the vehicle merges it | vehicle line |

## Observed, not acted on

- **The orphaned `sleep 30` needs an issue.** `tests/test_journal.py::test_a_stream_that_never_ends_times_out`
  leaves a `sleep 30` running; it is the same in P and R2c. A filigree issue should record it. That has not
  been filed yet.
- **A stale filigree claim.** `space_chassis-4d7a6afd1f` ("Verify and activate vehicle scaffold CI after
  billing unblock", P1) is claimed by `claude` and stale for more than 48 hours. It was not this session's
  work, and I left it as it is.
- **The vehicle's G312s is on authorization hold** (master §39). Option B stays the vehicle's to qualify,
  and its publication is John's decision.
