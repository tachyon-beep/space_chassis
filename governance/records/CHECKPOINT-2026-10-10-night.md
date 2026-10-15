# Chassis checkpoint — paused for the morning flight report (2026-10-10 22:43 AEDT)

Owner: Space Chassis Claude Code session_019mkPNN5J3Atit9tUA6zrNY (peer [8a7d49]). Paused on John's
wind-down direction ("as things land lets pause and reset at the morning flight report"). No gate
exception, merge authority or new scope is granted; nothing below was rerun to green.

## Published state (origin = local)

| ref | SHA |
|---|---|
| `aurora-port` | `613557528ffc42d4ea8d4ae0a3b3a2c453825ffa` (= origin) |
| `vehicle-adoption` | `be63f93402f5bf6662e92e8ce509d55f1bb12a4f` (= origin) |
| `main` | `fa43b25b0fd7d88a3f5e7feb3338e190078517ce` (= origin) |
| `phase-b-dryrun` (local only) | `39ba76d3acc247600cfcbbff458cbcb9aea8b08f` |

Recorded vehicle gitlink on all published chassis branches: `dd79e76`. Vehicle #21 is merged on
vehicle main at `f44399645fb2633e695a5d758cb5a41f43fb848c` (PR #41; tree = tested 45f4267).

## Dirty, unpublished work (preserve all)

**Main checkout** (`aurora-port` @ 6135575):
- staged (coordinator, Emmy's — never commit with owner work): `governance/MASTER_GOVERNANCE_PLAN.md`, `governance/coordination.md` (also has unstaged edits);
- unstaged, mine: `governance/chassis/records/2026-10-10-aur-gov-04-interface-report.md` (v1.3 corrections; held for the gate);
- unstaged, vehicle line's (commit verbatim, by path, when the gate allows): `governance/vehicle/open.md`, `governance/vehicle/snapshot.md`;
- others': 10 filigree skill files, `docs/deep_research/vehicle` (vehicle line's tree at 8c6f71d), untracked `docs/plans/`.

**Adoption worktree** `.claude/worktrees/vehicle-adoption`, branch `phase-b-adoption` (local, HEAD
be63f93), Phase B candidate STAGED, uncommitted:
- frozen tree **`b29bf8af40dab08bdb890039483fb205f8fccbfe`**; diff vs vehicle-adoption saved as `.scratch/phase-b-candidate-2.diff` (sha256 `5af0d332638c2b513adf6004856d41798a2e6d2022b5659bdcc6c5f6adf17fec`); earlier tree `a1fbad19…` (`.scratch/phase-b-candidate.diff`, sha256 `7c75b3ef…`);
- gitlink staged at `f443996`; its vehicle clone checked out there, clean.

**Diagnostic worktree** `.claude/worktrees/probe-diag`, branch `diag/contract-probe-loss` (local,
HEAD 6135575): uncommitted capture patch = `.scratch/probe-diag/checkpoint-2.patch` (sha256
`8eb4c103…`, verified equal to the worktree diff at 22:42); vehicle clone at 8c6f71d. Evidence
`.scratch/probe-diag/evidence-1.tar.gz` (sha256 `6e3387cd…`) and `evidence/SUMMARY.md` (`d295dc0f…`).
Vehicle's ungated diagnostic clone: `.scratch/probe-diag/vehicle-ingress-trace` @ 1caab23 (unqualified; never adopted).

## Tests on the Phase B candidate (actual results, nice 19, single driver)

| tree | root | whole suite | live |
|---|---|---|---|
| `a1fbad19` (21:59–22:21) | 592 passed | 1941 passed | 19 passed |
| `b29bf8af` (22:22–22:42) | 592 passed | 1941 passed | 19 passed |

Logs: `.scratch/phase-b-gates/`, `.scratch/phase-b-gates-2/` (each `summary.txt` records the tree before and after).
ruff check and format clean on `b29bf8af`.

## Reviews (`.scratch/phase-b-reviews/`)

- Opus on `a1fbad19`: land after fixes (1 Important + 9 minor) — fixed in `b29bf8af`.
- Astra on `a1fbad19`: land after fixes (3 Important + 4 minor) — fixed in `b29bf8af`.
- Astra confirmation on `b29bf8af`: **land after fixes**, 3 Important still open:
  1. the identity scan retries a vanished name (vehicle temp files, pruned telemetry); re-enumerate and parse the text already read, keep pending.json mandatory;
  2. the resume test does not prove the command's cycle lies between the checkpoint and the recovery tick; assert it from the banner, retrying the setup if a checkpoint crosses before the kill;
  3. README: a root record naming a *different world* refuses (ordinary disagreement is repaired); and a recovered-tick checkpoint failure refuses the start, not a mid-mission stop (minor).
  **The second fix pass is NOT started** (paused). Then: refreeze, gates, confirmation review, squash to one adoption commit, ff `aurora-port`, push, close vehicle #16, governance refresh.

## Contract-probe diagnosis (#39)

ERASED 3/3 in traced runs (q2 on unmodified 8c6f71d matches the coordinator's failure), no delay,
0/10 untraced. The whole suite passed twice tonight on the candidate, which includes that test;
#39 stays open (vehicle-owned fix, design in review). Causation of the coordinator's original run:
inferred from an identical signature, not observed.

## Decisions open (none inferred)

- John: the filesystem/platform behaviour of an exchange-based claim (refuse by name vs a qualified fallback) — affects the vehicle and `contract/fake_diode.py`.
- John: the claim-timing rule — mechanism (A) corrective exchange needs a rule for a batch taken mid-cycle; (B) rename-take needs a contract sentence, a brief line and a probe precondition, none approved.
- John/Emmy: the commit hold — the AUR-GOV-04 v1.3 correction, the vehicle's governance files and Phase B all wait on the full-suite gate on their exact heads (now green twice for the Phase B tree) or an exception.
- John: merge `aurora-port` to `main` (proposed after Phase B); authorise the vehicle build guard.

## Processes

None of this session's are running: no pytest, codex or smoke containers of mine (checked 22:42).
Running on the host and not mine: elspeth CI pytest shards.

## Morning resumption — 2026-10-11 (Emmy's bounded resume instruction, master §14)

- 10:10 orientation: every ref, tree and hash above verified unchanged. (A no-op `git add -N .` in probe-diag
  changed nothing: status identical, patch hash still `8eb4c103…`.)
- Second fix pass DONE, in the existing worktree, two files by name: `live/test_vehicle.py` (identity scan
  re-lists on a vanished name and parses the text it read, pending.json mandatory; resume test proves
  checkpoint M <= receipt tick T < recovered N from the receipt and this boot's banner, sets up again
  if a checkpoint crosses, at most 3 attempts) and `README.md` (different-world record only; recovered-tick
  checkpoint failure is a start refusal).
- **Refrozen, STAGED, uncommitted: tree `04dff0beaa37294bc839122885f3543535520fc5`.** Diff vs
  vehicle-adoption `.scratch/phase-b-candidate-3.diff` (`f7bb4c66…`); delta vs b29bf8af
  `.scratch/phase-b-candidate-3.vs-2.diff` (`bc3dc073…`). b29bf8af evidence preserved; its tree listing
  `.scratch/phase-b-candidate-2.tree.txt` (`65c0e9ca…`). ruff clean.
- Confirmation review running, read-only: Opus subagent and Astra (`.scratch/phase-b-reviews/review-phase-b-confirm-3-*`).
- Gates: NOT started. Waiting for Governance's shared Space test slot (one selection, <=2 workers, nice 19).
  Request and live-run resource estimate: `governance/chassis/records/2026-10-11-phase-b-test-slot-request.md`.
- Committed/published: nothing new. aurora-port 6135575 = origin; vehicle-adoption be63f93 = origin.
- 10:2x confirm-3 reviews: Opus LAND (3 Minor); Astra LAND AFTER FIXES (1 Important: crossed-checkpoint retry
  must precede the positive-replay assertion). Saved: `.scratch/phase-b-reviews/review-phase-b-confirm-3-{opus,astra}.md`.
- Emmy authorised a resource-control increment (one live stack at a time; 5 CPU / 14 GiB live; serial builds
  2.5 CPU / 10 GiB; verify kernel enforcement). Done with the confirm-3 fixes as **candidate-4, STAGED,
  tree `8db6db9fc6749a7ea76126adcca65718af280874`**; `.scratch/phase-b-candidate-4.diff` (`457553b6…`),
  delta `.scratch/phase-b-candidate-4.vs-3.diff` (`77ecfbdc…`); candidate-3 tree list `phase-b-candidate-3.tree.txt`
  (`1f9e04a4…`). ruff clean. Reviews running (Opus subagent; Astra `review-phase-b-confirm-4-*`).
- Build caps: NOT enforceable on the default builder; gap and smallest option (capped docker-container buildx
  builder: privileged container, uncached rebuild) reported, awaiting Emmy. Details and gate commands:
  `governance/chassis/records/2026-10-11-phase-b-test-slot-request.md`.
- Still: no test, build or container started; nothing committed or published.
- 10:3x candidate-4 reviews: Opus LAND AFTER FIXES (Critical: `{{index .Labels}}` template invalid on this host,
  confirmed; Important: uncapped verify_containment sweep, inaccurate build statement, guard once before build);
  Astra LAND AFTER FIXES (Important: guard race needs a held reservation; build budget unenforced; overhead not an
  enforced total). Saved `review-phase-b-confirm-4-{opus,astra}.md`. Candidate-4 never gated; superseded.
- Emmy's scope correction: no privileged builder, no hard build-cap claim; split into separate increments.
- **Increment P (Phase B corrections only): tree `af671d04908817e914668750b7cd4f6f74034bf4`** = 04dff0be + its
  review fixes. Reviews: Opus LAND, Astra LAND (`review-phase-b-P-{opus,astra}.md`). Ready for root + whole suite.
- **Increment R (resource controls, on P): tree `dd16772e6d537db0baf52f9741b58b2fc17ef3c7`** = STAGED index now.
  Fixes all candidate-4 findings (Label template + filter, flock lock held start..down, re-check after build,
  capped sweep, host-side cgroup reads, scope refusal, review 0.25 CPU). Reviews running (`review-phase-b-R-*`).
  Diffs: `phase-b-P.diff` 3b1ea8cf…, `phase-b-P.vs-3.diff` 4c2684bb…, `phase-b-R.vs-P.diff` 92e57d86…,
  `phase-b-PR.diff` 94411765…; R WIP copy `.scratch/phase-b-increment-R-wip/`.
- Gate plan and slot request: `governance/chassis/records/2026-10-11-phase-b-test-slot-request.md`.
  Still no test, build or container started; nothing committed or published.
- 10:47 Grant SPACE-20261011-P-01 (master §18) received via Emmy: P root then full, -n 2, nice 19, scope 200%/8G.
  R preserved: staged tree dd16772e (object); unstaged R2 WIP saved `.scratch/phase-b-increment-R2-wip/` (R2-vs-R.diff
  e27eced6…, R2-files.tar d1476730…). P materialised exactly with `git read-tree -u --reset af671d04…` (index = worktree = P,
  vehicle f443996 clean). Gate driver + receipts: `.scratch/phase-b-gates-P-019mkP/` (gate.sh, *.receipt, *.log, *.monitor).
- P ROOT: 10:51:21–10:51:55, **592 passed, rc 0**, no skips/failures; scope readback cpu.max 200000 100000, memory.max 8 GiB,
  nice 19; tree P before and after; 0 owned processes left.
- P FULL: started 10:52:10 (unit space-chassis-p-full-1791676328.scope), readback same limits; running.
  Do NOT edit the adoption worktree until it ends. Slot stays RESERVED until the release receipt.
- P FULL ended 11:23:31: **1 failed, 1940 passed, rc 1** (no abort; worst 40,454 MiB avail, load1 5.35, CPU 37%; scope peak 3.35 GB).
  Failed: vehicle test_vehicle_config.py::test_a_run_ending_cleanly_checkpoints_..._does_not (real SIGINT; TimeoutExpired 120 s).
  CAUSE ESTABLISHED (no rerun): my gate.sh ran the scope as `… &` in non-interactive sh → SIGINT ignored, inherited through exec
  and systemd-run --scope (checked: prints 1/SIG_IGN; foreground prints default_int_handler). Result confounded; does not qualify P.
  Receipt + RELEASE: `.scratch/phase-b-gates-P-019mkP/RELEASE-RECEIPT.md` (e060944a…). Slot released by chassis.
  Corrected driver ready, unused: `gate-v2.sh` (pytest in the foreground of the scope, wrapped to restore SIG_DFL; verified prints
  default_int_handler even from a background job). A rerun needs a new grant. Worktree still at P exactly; R preserved.
- 11:39 Grant SPACE-20261011-P-DIAG-01 (master §20). Supervisor `.scratch/phase-b-diag-P-019mkP/diag.py` + `launch.py`.
  Arm 1 (00:45Z): DIAGNOSTIC ABORT BEFORE RELEASE, test never ran — supervisor queried bare unit name (systemctl → .service),
  so the scope read inactive and the go-file was withheld. Launcher recorded inherited SIGINT = SIG_IGN (SigIgn …1006).
  Cleanup verified (scope not-found, no processes). Fixed supervisor 4a8d2d45… held, unrun; as-run kept (02d8ca49…).
  Receipt `RECEIPT-arm1-stop.md` (ccbdb7ba…); reservation RELEASED; arm 2 not run. Re-launch of arm 1 needs Emmy's decision.
- 11:5x §21 supervisor corrections, in fresh parent `.scratch/phase-b-diag-P-019mkP-r2/` (old parent, arm1/, as-run and reviewed
  scripts untouched). Corrected `diag.py` sha256 d90fb3def47cc88255e96aed06d76e5963ec7540d72b93f0a3ff3416bb231697 (from 4a8d2d45;
  diff `diag-r3.vs-r2.diff` 5973f3e3…); `launch.py` byte-identical 91a813dc…. Submitted for Governance's independent review.
  Unrun; no test launched; no grant held.
- 12:0x §22: corrected supervisor `diag.py` sha256 2ead42bee98575b0d44b734c13aaf082dc7323ca70414b9b4c5a1b4ba6e1d94e
  (record_failure best-effort; terminate_scope escalates unless termination is positively verified). Prior d90fb3de kept as
  diag-d90fb3de.py. Failure-injection controls `controls.py` (no scope/process/test): 20 PASS, 0 FAIL (`controls-2ead42be.out`).
  Unrun; no grant held.
- 12:10–12:13 SPACE-20261011-P-DIAG-02 (master §23), supervisor 2ead42be… in `.scratch/phase-b-diag-P-019mkP-r2/`.
  Arm 1 (original background path; SIGINT ignored in every scope process): pytest rc 1, the same node, TimeoutExpired 120 s at
  interrupted_console — reproduced; supervision held; cleanup verified. Arm 2 (launcher restores SIG_DFL): pytest rc 0, 1 passed;
  supervision held; cleanup verified. Identity exact throughout. Finding: the P full failure is the gate driver's launch path.
  NOT qualification of P. Receipt `RECEIPT-DIAG-02.md` (19735575…); reservation RELEASED.
- 12:2x §24 full-suite adaptation: `.scratch/phase-b-full-P-019mkP/full.py` sha256
  2557d326492e27e766dc13850aef68165eaad89119a475208a266de0c721a13f (from diag 2ead42be; diff `full.vs-diag-2ead42be.diff`
  f00ad993…); launcher byte-identical 91a813dc…; evidence would go to `phase-b-full-P-019mkP/full/` (fresh). Selection
  `python3 -m pytest -q -p no:cacheprovider -n 2`, SIGINT always restored, outer deadline 5400 s. The §22 controls run
  against it: 20 PASS, 0 FAIL (`controls-full-2557d326.out`). Unrun; awaiting driver review and a separate full grant.
- 12:26–12:57 SPACE-20261011-P-FULL-01 (master §25): full.py 2557d326…, P exact. **pytest rc 0, 1941 passed**, no fail/err/skip;
  supervision held; 374 samples, no OOM, max load 5.28; SIGINT default throughout; cleanup verified; RELEASED
  (`.scratch/phase-b-full-P-019mkP/RECEIPT-P-FULL-01.md`). P now has root 592 + full 1941 on af671d04. Not committed.
  Next (needs direction): commit P under the gate; then R2 (fix R's review findings, refreeze, review, gates incl. live).
- 13:1x R2 continuation (Emmy, after §26). P preserved: refs/preserve/phase-b-P-af671d04 (tree), tree list phase-b-P.tree.txt
  (afd9c032…); R kept as refs/preserve/phase-b-R-dd16772e. R + R2 WIP restored exactly (diff e27eced6…), then finished:
  sweep flock + running-sweep refusal + in-container cap readback (verify_containment.sh), teardown leftover check
  (stack.down), MemorySwapMax=0 command everywhere incl. practice.md and the override example; tests updated/added.
  **R2 frozen STAGED: tree 0471251aaef775feaaec85c3cf2c942ce7039431** (refs/preserve/phase-b-R2-0471251a); diffs
  phase-b-R2.vs-R.diff 164e700f…, phase-b-R2.vs-P.diff 277fe6e7…; ruff clean. No tests run. Reviews running
  (review-phase-b-R2-{astra,opus}). Build readiness note: governance/chassis/records/2026-10-11-serial-build-readiness.md.
- 13:2x R2 reviews: Opus LAND AFTER FIXES (Critical: two root tests select "--entrypoint find" → StopIteration);
  Astra LAND AFTER FIXES (timed-out check's subshell can launch a sweep after teardown; sweep listing fails open;
  stale selectors; stopped sweeps not removed). Saved review-phase-b-R2-{opus,astra}.md.
- Fix pass **R2b frozen STAGED: tree 3500987ce968254dee66be2a1b5ac5ab734181bd** (refs/preserve/phase-b-R2b-3500987c):
  run_group process-group kill for the containment check, fail-closed listing (exit 77), ps -a removal, selectors,
  readback tied to constants, settle re-list, lock wait 120 s. Diffs phase-b-R2b.vs-R2.diff 5463a113…,
  phase-b-R2b.vs-P.diff 3924f3f0…; ruff clean; no tests run. Confirmation reviews running (review-phase-b-R2b-*).
- 13:3x R2b confirmations: both LAND AFTER FIXES — run_group's communicate() waits for pipe EOF, so a pipe-holding straggler
  acts before the kill (owner control reproduced: 2.0 s, acted). Saved review-phase-b-R2b-{opus,astra}.md.
- Fix **R2c frozen STAGED: tree 148a31c4951e43c1cdafdf30c15b029dc7e104a8** (refs/preserve/phase-b-R2c-148a31c4): output to
  temp files, wait on the leader only, killpg + reap in finally; tests with readiness handshake and child-ended checks.
  Owner control: timeout case killed, did not act; finished case returned 0.06 s, child gone, did not act.
  Diffs phase-b-R2c.vs-R2b.diff 240b78d1…, phase-b-R2c.vs-P.diff ef4954a1…. Residual (Astra): an in-flight daemon create
  by a killed docker client is not proven cancelled; the label + teardown + start refusal cover any container that appears.
  Confirmation reviews running (review-phase-b-R2c-*). No tests run.
- 13:4x R2c confirmations: Opus LAND, Astra LAND; no Critical/Important. Minors not taken (would need another review loop):
  test timing assumptions (1 s readiness under timeout, 1.5 s prompt-return; fail loud, never falsely pass), _ended's 5 s bound
  exceeds the child's 2 s life (the `late` assertion still catches a survivor), TimeoutExpired carries no captured output,
  text=True no-op, interrupt windows. **R2c 148a31c4 is review-complete and ready for its gates** (root + full under a grant,
  then build/live under a separate grant). Saved review-phase-b-R2c-{opus,astra}.md.
- 13:5x Root-only driver for R2c prepared, UNRUN: `.scratch/phase-b-R2c-root-019mkP/root.py` sha256
  6eac172448026b6f4fe604ba5aa205439d5099c533cf33a1976e08f0a4dfc6b9 (from full.py 2557d326; diff root.vs-full-2557d326.diff
  2de22043…, 76 lines); launcher byte-identical 91a813dc…; controls 20 PASS (controls-root.out af0825df…). Awaiting review + grant.
- 14:08–14:09 SPACE-20261011-R2C-ROOT-01 (master §27): root.py 6eac1724…, R2c exact. **pytest rc 0, 617 passed**; supervision
  held; cleanup verified (scope still active at cleanup because pre-existing tests/test_journal.py's FAKE_SLEEP=30 sleep
  outlived pytest; bounded stop removed it). RELEASED (`.scratch/phase-b-R2c-root-019mkP/RECEIPT-R2C-ROOT-01.md`).
  Next: R2c whole suite (needs a grant; adapt full.py to R2c), then build/live.
