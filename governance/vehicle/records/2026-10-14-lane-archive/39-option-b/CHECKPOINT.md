# Lost-result contract-probe diagnostic — vehicle checkpoint 1 (2026-10-10 ~20:55 AEDT)

Authority: John via Emmy — the existing owners add diagnostics and fix the lost-result test, a fix preferred
to a gate exception. Driver and test/harness owner: Space Chassis [8a7d49] (session_019mkPNN5J3Atit9tUA6zrNY),
the only one running reproductions. Vehicle instrumentation and any console fix: Space Vehicle [610587]
(session_01GRfs7dVMu4v5airK6q3w9C). Agreed by message, 2026-10-10.

Test: chassis tests/test_vehicle_reconciliation.py::test_the_vehicle_passes_the_contract_probe —
"a non-string element refuses the whole batch", 0 result files, vehicle 8c6f71d, --poll 0.05, probe --timeout 15.
Hypothesis (unproven): #39 — the claim's read, then its rename over console.json, erases a batch replaced
between them. Alternative: scheduler delay.

Done (vehicle):
- Branch codex/diag-ingress-trace @ 1caab23b1034ca1113689bab6fa3dbc4127b9310 (pushed), parent 8c6f71d; tools/console.py only.
  VEHICLE_INGRESS_TRACE=<file> → JSON lines: cycle_start, claim_read, claim_replace (clobbered), claim_replaced,
  result_published, each with monotonic_ns and time_ns. Unset → no-op. Diagnostic, not for merge; referee not run.
- Worktree $SP/diag-ingress-ca87a9 ($SP = this session's /tmp scratchpad; ephemeral — the branch is the durable copy).
- Smoke test (throwaway directory, not the chassis test): smoke-trace.jsonl here — 100 cycles, 2 results, clobbered 0.
- Handed to the chassis with usage and the loss/delay reading.

Chassis side (theirs): console stdout/stderr kept; an audit-hook tracer around runpy on unmodified trees
(8c6f71d, dd79e76); probe submit logging (payload sha256, time_ns before/after the replace, new inode);
traced vs untraced comparison. First baseline proposed after the vehicle's #21 gates (~21:30 AEDT).

Next: the chassis hands over evidence (paths + SHA256) → the vehicle reads it → if it shows #39, a console fix
on a vehicle branch from main (#39's own PR), independent review, full exact-head gates; no assertion is
weakened. If it shows delay, the two lines look at the test's timing together.
Not touched: #21's head 45f4267 and its running gates.

## Hold (Emmy, 2026-10-10 ~21:00 AEDT)
1caab23 is UNQUALIFIED DIAGNOSTIC EVIDENCE ONLY: its commit and push did not meet the instruction's full-suite gate.
Published history is preserved, not reset. No further commits or pushes on this task until the required
repository checks and independent review pass on the exact candidate head, or John grants an exception
(none given). The chassis may continue its capture from the disclosed artifact. Quiet baselines start only
after the vehicle explicitly confirms #21 gate completion to the chassis; elapsed time is not completion.

## Checkpoint 2 (2026-10-10 ~21:50 AEDT)
- Evidence received from the chassis and verified: evidence-1.tar.gz sha256 6e3387cd9d49c41c107b07a7e56aeb2982ac3576cc60b2fbba03390cae5e7a10;
  SUMMARY.md sha256 d295dc0f3948006980bc2374699f4dd070e29de8313e47fce1c14ea23222ae9a. q1 untraced 0/10,
  q2 audit 1/10, q3 both traces 2/10; ERASED 3/3, AMBIGUOUS 0; no delay (console cycled ~53 ms). Loss, consistent with #39.
- Fix design drafted, no code: 39-design.md (one RENAME_EXCHANGE per claim, no write on quiet cycles,
  own-file identity, durability decided on what was taken, refuse-by-name where exchange is unavailable).
  Next: independent design review (Codex, read-only), then code on a branch from 45f4267 after #21 merges.
- Open with Emmy: (a) does the hold cover #21's PR, CI and merge? (b) may an unpushed local commit be the
  "exact candidate head" for gates and review?
- No commits or pushes since 1caab23.

## Checkpoint 3 (2026-10-10 ~22:05 AEDT)
- Emmy: the hold covers only the diagnostic work; #21 continues under its existing approval and normal gates.
  #21 PR #41 is open; hosted CI is running; it merges on green under the existing approval (no new authority).
- Codex design review of 39-design.md dispatched (read-only).
- Chassis review of the design: the one-cycle variables lag (step 5) would fail the unchanged probe's
  check_batch_claimed (diode_probe.py:187-211 judges variables at the first read where commands == []), so no
  lag clause may go in the contract. Candidate in-cycle closures: (A) a corrective exchange in the same cycle
  (open: what to do with a second batch it takes out); (B) rename-take plus RENAME_NOREPLACE create, which
  leaves console.json absent for microseconds — the probe reads absence as {} and keeps polling. The review
  decides; if neither closes the lag in-cycle, it goes to John and Emmy as a contract-versus-probe question.
- contract/fake_diode.py:205-222 has the same read-then-rewrite; whether it is in this slice is Emmy's call.
- Chassis on (B): diode_probe.py:360-362 exits 2 at start-up if console.json is absent, so a probe starting
  inside the absence window fails (~absence ÷ cycle, ~2e-4 per run for a 10 µs gap). Ways out: (i) bound the
  absence and accept the residual; (ii) after the contract sentence is adopted, the probe's start-up
  precondition waits briefly (a probe change: needs Emmy's sign-off as alignment, not weakening).
  The chassis prefers (ii). Also: an in-place writer racing (B)'s rename keeps writing into the taken inode,
  so its tail is lost (inside the contract's half-written rule, but a new loss mode; the old code had the
  mirror image). (A)'s second-batch recursion stands. For the reviewer's follow-up round.
- Chassis correction: brief/PROTOCOL.md "Asking" (line 38 on) describes the window's console.json to the agents.
  A B-style contract change ("may be briefly absent") therefore needs three chassis follow-ons: the brief line
  (needs John's approval), the probe's start-up precondition (Emmy), and fake_diode.py (Emmy's scope call).
  This weighs against B: A needs no contract absence clause.

## Checkpoint 4 (2026-10-10 ~22:30 AEDT)
Emmy's rules for this slice: an unpushed commit may be the candidate head only AFTER precommit checks and
independent review pass; until then freeze the diff and tree and record their hash. Preserve the contract
semantics, including same-cycle variable publication as the unchanged probe sees it; no one-cycle lag; no
probe weakening; no silent drop of a supported platform (the vehicle README supports Linux, Python 3.12
and 3.13). The chassis may align fake_diode.py and its regression tests to the accepted claim contract.

Codex design review (gpt-6-astra high, read-only, vs 45f4267): REQUEST CHANGES.
- P1: my note was wrong — the preserved map and variables_known are NOT checkpointed; a resume adopts the
  live console's variables (console.py:5014). A stale-variables console (design step 5) plus a SIGKILL
  reverts the map permanently. Rejects that residual.
- P2: inode plus identical bytes is not conclusive ownership (inode reuse). Holding an open descriptor
  prevents reuse within a boot.
- P2: the contract sentence overpromises (agent supersession, crash loss), and "runs on the next one"
  needs updating. Codex's wording: "The exchange atomically takes the file present at that instant. A later
  replacement remains available for a subsequent claim, unless the agent supersedes it. Claimed commands
  retain the existing destructive crash-loss semantics."
- Q3: refuse by name (exit 3); probe EXCHANGE and NOREPLACE on the actual window mount.
- Q4: no loss, replay or double answer in the single-race orderings; a leftover taken file does not prove
  the fsync completed; SIGKILL is not power loss.
- Quiet cycles: equality must be type-exact (False == 0 in Python); {"commands": []} without variables
  needs an explicit rule.
- P3: test list (same-byte inode reuse, missing, equal and type-different variables, malformed taken file,
  kill points around exchange, fsync, unlink and record, restart from an older checkpoint).

## PAUSE checkpoint — 2026-10-10T11:39Z (22:39 AEDT), John's wind-down ("pause and reset at the morning flight report")

Completed and published:
- #21 MERGED: PR #41 → vehicle main f44399645fb2633e695a5d758cb5a41f43fb848c (tree = tested 45f426763280aa1274732fc35f99584b4d7f9ebc).
  Hosted CI run 38044800034 green (3.12, 3.13, readiness). Owner gate at 45f4267: 539 passed and 0 skipped on both
  lanes. Implementer gate: 3× 539. Per-commit: all pass except 29becaf (bisect skip). Codex approved round 5.
  Merge SHA posted on filigree space_chassis-93010ff54e, comment 41. Issue #21 closed; residuals #40; #39 open.
- Remote heads: main f443996…; codex/wp08-resume 45f4267… (merged); codex/diag-ingress-trace 1caab23…
  (UNQUALIFIED DIAGNOSTIC EVIDENCE ONLY).

Pending (parked, nothing started):
- #39 fix: design 39-design.md (sha256 d1baec7030ca…) is Codex-reviewed (REQUEST CHANGES, checkpoint 4).
  v2 direction: a same-cycle corrective exchange, ownership by a held descriptor, type-exact equality, an
  exchange every cycle, Codex's contract wording. No code, no frozen diff, no commit.
- Decisions needed (unanswered; do not infer approval):
  (1) a filesystem without RENAME_EXCHANGE: refuse by name with exit 3 (recommended) or fall back with a
      qualified contract;
  (2) the double-race corner: (a) take it this cycle as an extra batch, with contract wording (recommended);
      (b) carry it to next cycle, a one-cycle variable lag (ruled out by Emmy); (c) swap back, which moves the
      same choice to a triple race.
- The chassis's Phase B adoption of f443996 and every chassis commit wait on the whole-suite gate, which flakes
  on #39. A gate exception is John's alone; none is granted.

Dirty, not published (preserve):
- Chassis tree (aurora-port 6135575): governance/vehicle/{snapshot,open}.md modified — mine, recording the #21
  merge and #39; the chassis commits them by path when its gate allows. Not mine, untouched: governance/
  MASTER_GOVERNANCE_PLAN.md (AM), governance/coordination.md (MM), governance/chassis/records/…aur-gov-04… (M).
- .scratch/wp01-handoff/ (gitignored): diag-contract-probe/{CHECKPOINT.md, 39-design.md, smoke-trace.jsonl};
  aur-gov-v2-notes.md; pr-wp08-3.md; gate-21.md; evidence/wp08-3-custody/ (all #21 evidence).
- Chassis evidence (the chassis's, preserved): .scratch/probe-diag/evidence-1.tar.gz (sha256 6e3387cd…a7e50),
  evidence/SUMMARY.md (d295dc0f…a222ae9a).
- Vehicle worktree $SP/diag-ingress-ca87a9 at 1caab23, clean; the submodule checkout 8c6f71d, clean (preserve;
  never `git submodule update`).

Processes: none of this session's are running — no gates, probes, Codex reviews or subagents. Background
monitors are finished. Host processes seen at the checkpoint belong to other projects and to the chassis.

Morning restart order: Emmy/John decisions (1)(2) → design v2 → Codex round 2 → freeze diff, record its hash →
gates → candidate commit → chassis q1–q3 evidence re-run on the candidate under the cap → push and PR → CI → merge
(authority as then given). Then the governance refresh (AUR-GOV-02/07 v2, aur-gov-v2-notes.md).
- Chassis, paused at the same time: Phase B staged, not committed, frozen tree b29bf8af. Root 592, whole suite
  1941 and live 19 passed on it and on its predecessor a1fbad19. Astra's confirmation review left three
  Important fixes, not started. My governance/vehicle/{open,snapshot}.md preserved uncommitted. Its checkpoint:
  /home/john/space_chassis/.scratch/CHECKPOINT-2026-10-10-night.md.

## RESUME — 2026-10-11 (Emmy's resume instruction via cloud browser, master §14)
Acknowledged. Next bounded step: write #39 design v2 (39-design-v2.md, beside v1 which stays unchanged),
built on vehicle main f443996 (read via `git show`, no new worktree, no code), covering: held-descriptor
ownership, type-exact comparison, restart variables (resume must not adopt a stale vehicle-own console),
same-cycle variable publication (no one-cycle lag), Codex's contract wording, and decision-ready
alternatives for the two pending choices. Then an independent read-only design review (Codex) before any
implementation.
Pending, John's, NOT inferred: (1) no RENAME_EXCHANGE: named exit 3 vs qualified fallback; (2) second batch
during the corrective exchange: explicit same-cycle semantics vs another independently reviewed approach.
One-cycle variable lag stays disallowed. Design parts that depend on (1)/(2) are written as conditional.
Test slot: shared, one bounded selection at a time, max two workers total across both lines, nice 19. Design
and review need no tests. If a test is needed, I claim the slot in governance/vehicle/open.md (my file) and
message the chassis first; I never take it while the chassis holds it.
Preserved: #21 / PR #41 merge evidence at f443996; 1caab23 = unqualified diagnostic evidence, not a candidate.

## Checkpoint 5 (2026-10-11, resume) — design v2 written; round-2 review running
- 39-design-v2.md written beside v1 (v1 unchanged). sha256 dff1aafb61bcc9849219a56393597877c755c1495806b850e52560e8ed636ceb.
  Built on vehicle main f443996 (read via git show into $SP/console-f443996.py, checkpoint-f443996.py; no worktree, no code).
- Decision-independent core: quiet cycles write nothing (type-exact canonical JSON; explicit near-quiet rules);
  non-quiet claims by RENAME_EXCHANGE; identity within a boot only by held descriptors r (file read) and t
  (file put in); restart variables by hard-link pins in the window dir (.console.json.own / .next) plus
  .take.<boot>.<n> leftovers that are unclaimed by construction (claim point = unlink + dir fsync before the
  record); checkpoint format unchanged; resume re-offers the newest leftover; Codex's P1 counterexample walked.
- Fact surfaced for the decisions: all three observed erasures were quiet-cycle rewrites, so quiet-skip alone
  removes the observed failure; the residual (double write within ~0.2 ms of a non-quiet read) needs exchange.
- §5: probe-visible stale interval only under condition C (agent writes twice, second inside the read->exchange
  window); argued unreachable by the unchanged probe from its code (each submit waits for claim/results).
- Decision 1 (John): capability probe is shared; 1A exit 3 by name / 1B qualified fallback, both written, none chosen.
- Decision 2 (John): families R (claim only the file read; keeps §2.2 "runs on the next one"; new, unreviewed),
  E-a (take extra batch; breaks the record's 2 x max_batch row bound, console.py:1127-1130 and cap :3566),
  E-c (put back). Owner's note marks R as the smallest contract change, as input, not a selection.
- Codex round-2 review (gpt-6-astra high, read-only) launched in background. No tests; no test slot used.

## Checkpoint 6 (2026-10-11) — Codex round 2 on v2 (dff1aafb…): REQUEST CHANGES (core, R, E-a, E-c)
Verified the hash and that the extracted sources match f443996. Read-only, no tests or syscalls run. Findings:
- P1 crash recovery loses unclaimed batches: (a) R/E-c: after swap-back the console holds X (put back by the
  vehicle), Z is the leftover take; resume sees console != .next and deletes Z as "superseded" (wrong: the
  vehicle, not the agent, moved Z). (b) E: .next repinned to T2, kill before the corrective exchange ->
  resume misidentifies T, discards X, adopts the stale map. (c) the agent replaces the console during
  resume's own re-offer exchange: no disposition. (d) No crash needed: S6 unlinks, then the promotion over an
  agent-planted .own directory fails, so claim() never returns the batch -> claimed without a result.
- P2: highest <n> gives no cross-boot ordering.
- P1 mutable content: the agent writes commands in place into T after S3; the rollback/correction exchange
  takes T out and deletes it by inode t -> Z lost. Identity must be separate from unchanged-content evidence.
  Content-only quiet detection: sound; type-exact rule and missing-variables rule: accepted.
- P2 tampering: deleting .next after S3 makes resume discard a genuine X (not variables-only).
- P1 promotion gap: claim P->Q, unlink, agent writes a batch without variables, kill before .next->.own;
  resume adopts P. Needs recoverable committed-map state.
- R: coherent supersession semantics but unsafe recovery; P2 its wording is false — a submission after cycle
  start but before that window's S0 is claimed this cycle (console.py:3053,3098,3101-3103); K exhaustion too.
- E-a/E-c: fit the exchange wording in principle; inherit the P1s. E-a needs successive claim points,
  per-batch map/validation, K-exhaustion disposition, the cap/row bound.
- Capability probe: qualified yes; generic EINVAL also means bad args; also needs hard links and dir fsync.
  P2: the "Linux-only README" claim was not substantiated in the pinned README. 1B must qualify the whole
  read-to-replace interval, not "about a millisecond".
- P2 §5 is wrong: C IS reachable by the unchanged probe. check_batch_claimed waits for clearing, not its
  result; the next check can count that late result, the malformed check can then return before its own
  claim, and the unknown-verb submit can land between the malformed batch's S0 and S3. Timeouts also break
  it. Restrict the equality invariant to vehicle-published consoles.

## Checkpoint 7 (2026-10-11) — design v3 written; Codex round 3 running
- 39-design-v3.md, sha256 5a4e5f2fda350b4d056cd472344797cc2a51ef7fbc352f37cfdf4e93fd2f242b (v1, v2 unchanged).
- Structural change (from the round-2 P1 cluster): claim-at-exchange (every exchange claims what it takes;
  crash leftovers are claimed and deleted, never re-offered; resume does no exchange); no window-dir pins;
  a vehicle-private claim intent under --state-dir (claims/<slug>.json, fsync'd before each exchange) holds
  P, known, R_sha and per-step put_ino/put_sha; "our untouched T" = held fd + bytes read back via it;
  nothing after S3 may withhold a claimed batch; steady-state resume unchanged (ADR 0002 G / (xxxv)), and
  v2's ".own" fallback map dropped.
- Retracted: the "README supports Linux only" claim (README silent; pyproject requires-python >=3.12 only).
  1A is therefore a NEW stated platform requirement (Linux, renameat2, an exchange-capable fs) for John.
- §5 corrected: the probe CAN reach C (late-result counting), but it asserts variables only in its first
  submission (diode_probe.py:356). The late-result counting is offered to the chassis as its own probe finding.
- Decision 2 tradeoff now concrete: R and E-c need a new crash-loss clause for a file the vehicle hands back
  (the alternative recovery is what round 2 broke); E-a keeps the existing clause but changes the per-cycle
  cap/row bound and has a one-cycle lag reachable only at K exhaustion by an adversarial agent.
- ADR 0002 G consequence note (vehicle maintainer's own record) drafted in §10, to record after review.
- Codex round 3 (gpt-6-astra high, read-only) launched. No tests; no test slot used.

## Checkpoint 8 (2026-10-11) — Codex round 3 on v3 (5a4e5f2f…): REQUEST CHANGES (core, R, E-a, E-c)
Source-only; hash and sources verified. P1s:
- Interrupted recovery reverts the map: resume reconstructs M, keeps stale T, deletes the takes; a kill
  before the first cycle -> the next boot finds no takes and adopts T's stale map. Recovery needs durable
  completion before discarding its evidence; partial cleanup destroys later steps' inputs.
- The intent does not prove an exchange happened: the agent edits the take file (before S3) in place, then
  a kill; the hash mismatch reads as "exchanged", and E adopts the edited map. Private metadata does not
  authenticate mutable evidence.
- E-a recovery can adopt its own stale correction input (an untouched T taken back by the correction is
  classified against T2's put, so it reads as a submission).
- R: live identity (inode) and recovery identity (R_sha only) disagree on a byte-identical replacement.
- "Nothing after S3 may withhold the batch" conflicts with durability (a window-dir fsync failure) and with
  an unreadable take; the claim()/_ingest interface returns a batch or a refusal, not both plus failures.
- Further: the directory swap-back can itself take a submission; the quiet-test failure alone does not
  correct an identified stale T (S2 rebuilds from R.variables).
P2s: §4.4 residual is not bounded to one cycle; sync claims/ and create it durably; §5 must be qualified to an
isolated, initially quiet run (the first submission can race a pre-existing non-quiet batch; C includes
in-place edits); E-a's bound must be resolved, not listed; directory-fsync EINVAL is not "unsupported".
Accepted: claim-at-exchange in principle for E; §8's split broadly; 1A/1B disclosures; §5's late-result
explanation and variables-assertion location.

## Checkpoint 9 (2026-10-11) — no v4; the tradeoff returned for decision
- Three rounds, three REQUEST CHANGES, the same P1 class each time (crash recovery of the map needs evidence
  the agent cannot forge; ADR 0002 G keeps the map only in the agent-writable console). Per Emmy's rule, the
  concrete tradeoff is returned instead of a fourth design.
- Verbatim Codex texts saved: reviews/round1-v1.md f96b7990…, round2-v2.md 85ff9c20…, round3-v3.md 70548905….
- Decision memo (mine, uncommitted; the chassis commits by path): governance/vehicle/records/2026-10-11-39-claim-race-decision-memo.md.
  Tier 1 quiet-skip only (landable now; decisions 1 and 2 moot; probe-reachable residual disclosed); tier 2
  exchange with the crash map-revert residual accepted (needs decisions 1 and 2 plus a review of the reduced
  design); tier 3 amend ADR 0002 G (a direction only). governance/vehicle/open.md #39 row updated to point at it.
- No code, commits, pushes or tests; no test slot used. Waiting on John's tier decision via Emmy.
0417d666cc5ef86e02c33f4909ea12af4938ac6a7ea27255fce85d1b7c33e2b1  governance/vehicle/records/2026-10-11-39-claim-race-decision-memo.md

## Checkpoint 10 (2026-10-11) — John asked for an architectural panel on the tier choice
Four read-only opinions (none was told the owner's recommendation), saved verbatim in reviews/panel-*.md:
determinism/replay, systems thinking, concurrency/recovery, solution architect. All four: tier 1 now, no tier 2.
New inputs: (1) a pre-existing restart defect independent of #39 — an unknown map after resume opens every gate,
so a deferral the agent blocked by closing a gate can settle (determinism); (2) tier 3 alone does not close
the race — it only makes an exchange recoverable (systems, concurrency); (3) option B, rename-take then
create-only-if-absent via link (noclobber, which already exists), revives checkpoint 3's option: no
renameat2, no decisions 1/2, no stale vehicle file, crash residual = absent console = the (xxxv) class;
cost: a brief console absence (the probe's exists() at start, brief/PROTOCOL.md needs John) (architect;
concurrency offered a root-directory variant); (4) the tier 1 conditions: the quiet test never raises, runs
before adoption, fake_diode uses the identical test, the qualifier replaces §2.2's "runs on the next one",
brief/PROTOCOL.md:51-53 and brief-claims need the same qualifier, acceptance >=30 gate runs with instrumented
early returns; (5) memo corrections: tier 3 changes the record AND the checkpoint.
The determinism reviewer wrote an extracted ADR copy to $SP/adr0002.md (scratch only).

## Checkpoint 11 (2026-10-11) — John's decisions; tier 1 drafted
- John: (1) tier 1 approved; (2) a brief console absence during a claim is acceptable — agents must detect
  and handle tearing (unblocks option B's design); (3) threat model NOT adversarial at the simulation level
  (the container is); cheats are data, fixed as found; test and check, not a hostile red team. Logged in
  governance/vehicle/decisions.md (two rows). Recommendation item: vehicle issue #42 filed (gates reopen
  after a resume with no map; verified at console.py:4513-4517, :3883).
- Tier 1 code: branch codex/39-quiet-skip from f443996, worktree $SP/t1-39-ca87a9, UNCOMMITTED.
  Window.claim: quiet = commands is exactly [] and (variables is an object -> adopted, or no variables key
  while the map is unknown), decided by isinstance only, before adoption -> return [] with no write. Three
  tests added (quiet cycles keep the inode/mtime and a batch landing during a quiet read survives and is
  claimed next cycle; shape-by-shape rule; resume adopts the agent's left-in-place console).
  ruff check clean (format --check is not a CI gate; f443996 already fails it).
  Candidate-0 diff: t1-candidate-0.diff, sha256 0973b949268ede6246480754a02f457f1313dacbbbc483e179a62901e750d416.
- No tests run: the shared slot is granted via the coordinator (coordination.md "CURRENT SLOT: FREE /
  RELEASED 14:13"); request posted in governance/vehicle/open.md (bounded selection first, full gate later).
- Codex review of candidate-0 (read-only) running.

## Checkpoint 12 (2026-10-11) — tier-1 candidate-1 approved by review; waiting for the test slot
- Codex on candidate-0 (0973b949…): approve with changes (P2 docstring residual too narrow + contract/fixture
  parity on the chassis side; P3 race test only in-place). Fixed in candidate-1: t1-candidate-1.diff
  sha256 cb40feac4eedb1c556f2024754148bf8e87d14566152eef1f4df5f1d67e5ffa4 (delta t1-candidate-0-to-1.delta).
  Codex delta confirmation: APPROVE. Verbatim: reviews/t1-candidate-0-codex.md, reviews/t1-candidate-1-codex.md.
- Contract/brief/fixture proposal drafted for the chassis: t1-contract-proposal.md (sha256 1d15b1de…), sent after gates.
- Next, in order: shared-slot grant -> bounded run (new tests pass on candidate-1; regression tests fail on
  f443996) -> local candidate commit -> full two-lane gate (serial, 2 workers) -> chassis q1–q3 re-run ->
  push/PR/CI/merge under the authority then given. Nothing committed or pushed.

## Checkpoint 13 (2026-10-11 ~19:15 AEDT) — slot granted by John; bounded run passed; candidate committed; full gate running
- Slot: granted by John ("granted"), marked HELD in governance/vehicle/open.md at 19:10 AEDT.
- Bounded run (3.12, -n 2, nice 19): candidate-1 10/10 passed (3 new + 7 claim/resume tests), exit 0;
  f443996 + the new tests: all 3 fail (inode assertions). Direct demo: on f443996 a batch landing during a
  quiet read is erased both in place and renamed-over (0 results); on candidate-1 it survives (2 results).
  Evidence: t1-evidence/{bounded-candidate1-3.12.txt, bounded-base-regression-3.12.txt, erasure-demo-3.12.txt}.
- README round entry added (#39 tier 1; referee tests 525 -> 528). Local commit on codex/39-quiet-skip:
  7ac979156bc164448e9e78df7b39253c619fefaa (UNPUSHED); its console.py+tests diff vs f443996 is byte-identical
  to reviewed candidate-1 (cb40feac…). (c3dd334 was the same commit with a malformed message, amended locally.)
- Full two-lane gate at 7ac9791 running in the background (detached worktree $SP/gate-t1-ca87a9, -n 2,
  nice 19, 3.12 then 3.13), evidence t1-evidence/gate-7ac9791-ca87a9/.
- Option B design written while the gate runs: 39-design-B.md, sha256 f32b5d149badcb1785ced4fc54d9fabdeb58a27fd31ca3681ad7cef453a4a218
  (take by rename, read the taken file as the claim, fsync, republish by link/noclobber, EEXIST leaves the
  agent's newer file; resume: console's variables if present else the leftover's, republish if absent,
  delete leftovers durably before the first claim; no ownership test, no renameat2). Codex review running.
- Option B round 1 (Codex): REQUEST CHANGES (reviews/B-round1.md). P1: a failed cleanup then further claims
  leaves a stale take that a resume would use to revert the map. P2s: undefined fsync-failure outcome;
  directory taken in a race; reconcile with open_handles' pre-check; a held-fd late write; "variables
  recovered" overpromised; contract wording. Probe claims confirmed (conditionally).
- Revision 39-design-B2.md (sha256 304163678a0882d7647e50de08723d51c463cebf5ded9f932b9f79733e259bf3): one take
  per window ever (failed cleanup blocks that window's claims, retried each cycle; the console is untouched);
  fsync failure = one refusal, no effects; non-regular takes refused and removed; wording qualified. Codex round 2 running.
- Option B round 2 (Codex on B2): REQUEST CHANGES (reviews/B-round2.md); no SIGKILL replay/double-answer/
  claim-without-result found. Remaining: P1 a take surviving cleanup failures can resurrect an old map
  across boots; P2 a refusal after a failed barrier is not durable against power loss; P2 C0 can block
  indefinitely; wording.
- Revision 39-design-B3.md (sha256 ce17a97d6fc2ecd07909c21d72675343c9d377d94923522d253f1b503e7c7661): a take is
  map evidence only for the resume right after its own boot (executive boot_id in the name vs the record's
  newest segment); no answer until the take is durable (pending take, C0 retries the barrier); quarantine
  (.dead) before block. Codex round 3 running. Tier-1 gate still on the 3.12 pytest phase.
- Option B round 3 (Codex on B3): REQUEST CHANGES, one P1 (reviews/B-round3.md): a boot's segment header is
  written only with its first cycle record (console.py:3444), so "newest segment" can name the wrong boot.
  All other round-2 fixes confirmed.
- Revision 39-design-B4.md (sha256 6102d239ad4a7e3f24b15afb3d11d7c5046a8ea48b17463c22d14cc40b649adf): a
  vehicle-private .boot.json in the state dir, read as prev then durably rewritten at every start before any
  evidence is read (failure = exit 3); a take is evidence only if its boot_id == prev. Codex round 4 running.
- Option B round 4 (Codex on B4): REQUEST CHANGES (reviews/B-round4.md): the boot marker closes round 3's P1;
  new P1 (power loss): retirement of a take was not durable; P2s: "every start" unqualified (--plan, no state
  dir); the marker path not reserved. No SIGKILL-only replay/double-answer found in any B round.
- Revision 39-design-B5.md (sha256 c255259e4717056f10e9e0eff87586cac07b76c506c5632312b0d6a24270d10e): durable
  retirement barrier before any claim or quiet adoption; marker only by serving starts with a state dir;
  marker path reserved (exit 3). Proposes #21's termination rule (round 5 scoped to these changes). Codex round 5 running.
- Option B round 5 (Codex on B5, scoped by the termination rule): APPROVE WITH CHANGES — two P3 wording
  clarifications carried to the implementation review (reviews/B-round5.md): (1) no state dir does not mean no
  journal — keep the `executive.journal is not None` durability condition (console.py:4369); (2) "refused
  starts never touch the marker" means preflight refusals only; never roll the marker back once recovery has
  begun (e.g. a later startup-checkpoint failure, :5536). No P1 anywhere, no P2 in B5's changes.
  Option B design = 39-design-B.md + B2 + B3 + B4 + B5 (read in order). DESIGN DONE; no code yet.

## Checkpoint 14 (2026-10-11 20:11 AEDT) — tier-1 gate GREEN; slot released
- Full gate at 7ac979156bc164448e9e78df7b39253c619fefaa (-n 2, nice 19): 3.12.3 and 3.13.15 each: ruff 0, lint 0
  (273 debts), strict 2 (expected), readiness/build-order/measure 0, pytest 542 passed, 0 failed/errors/skipped
  (33:10 and 24:44). Evidence t1-evidence/gate-7ac9791-ca87a9/ (run-*.txt, tests-*.xml).
- Slot released in governance/vehicle/open.md at 20:11 AEDT. Temporary worktrees removed (gate, base); the
  branch worktree $SP/t1-39-ca87a9 (codex/39-quiet-skip @ 7ac9791, unpushed) kept.
- Pending John: push/PR/merge authority for tier 1; whether to start option B code now or after the merge.
- John: "yes agree with both your recs" -> push/PR/merge tier 1 on green hosted CI; option B code after the merge.
  Pushed codex/39-quiet-skip @ 7ac9791; PR #43 (body .scratch/wp01-handoff/pr-39-tier1.md); hosted CI running
  (runs 38127644678 push, 38127660421 pull_request). After merge: post the merge SHA on filigree
  space_chassis-93010ff54e + send t1-contract-proposal.md to the chassis; then option B implementation.

## Checkpoint 15 (2026-10-11 ~21:10 AEDT) — tier 1 MERGED
- Hosted CI green (push 38127644678, PR 38127660421: 3.12, 3.13, readiness). PR #43 merged with
  --match-head-commit 7ac9791 -> main f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f (tree e6cfdbe0… = tested tree).
- Posted on filigree space_chassis-93010ff54e comment 42 (pins 542/528, 882 refuse sites; evidence; proposal).
  Messaged Space Chassis [ad1acf] (live chassis session) with the SHA and the contract proposal.
- governance/vehicle/open.md #39 row updated. Next: option B implementation on a branch from f75420c.
- Chassis [ad1acf] acknowledged tier 1; formal package published: governance/vehicle/records/2026-10-11-39-tier1-adoption-package.md
  (sha256 483d47de…); chassis adopts as its own increment in Governance's order; brief wording drafted for John.
- Option B code drafted (uncommitted) on codex/39-take-by-rename from f75420c, worktree $SP/b-39-ca87a9: take by rename,
  read the take, B3 barrier before any answer, put back by link (noclobber), retire (unlink/rmtree, else
  quarantine to .dead, else block), barrier; sweep stale takes/dead once per boot; boot marker .boot.json
  (resume before window recovery; fresh start before first cycle; --journal at it refused); recover_map at
  resume; prepare/repair noclobber; read label. 7 new tests + the fsync-order test updated. ruff clean, UNTESTED.
- Waiting for a test-slot grant (requested in governance/vehicle/open.md).

## Checkpoint 16 (2026-10-11) — Emmy: freeze + review + concrete first selection; no tests before allocation
- Frozen option-B candidate-0 (uncommitted): B-candidate-0/B-candidate-0.diff sha256 b5981141…64ea vs f75420c;
  tree a4ed929cb2052eb84a4bf77d1050971a5d8adfe7; console.py 6bee4f57…, tests 0d60ab82….
- Codex implementation review (read-only, no tests) of candidate-0 RUNNING; asked to address B5's two P3s.
- Proposal B-sel1/PROPOSAL.md: C0 (supervisor control, no-op payload, 60 s) then S1 (22 explicit tests,
  1 invocation, -n 2, nice 19, CPUQuota=200%, MemoryMax=6G, swap 0, deadline 420 s from go; admission
  MemAvailable>=16 GiB, load1<=12; abort oom_kill / MemAvailable<10 GiB / load1>20 x3 / read failure /
  deadline). supervise.py 206db6c9…, launch.sh b600a314…, spec-S1.json d0bb08a3…, spec-C0.json dc4b8c70….
  Only py_compile and sh -n were run. Nothing executed. Waiting on the review, then Governance allocation.
- Codex implementation review of B-candidate-0: REQUEST CHANGES, no P1 (reviews/B-impl-candidate-0.md); B5's two
  P3s confirmed implemented. P2s: cleanup exception (RecursionError in rmtree) could drop an answer; resume repair
  created a synthetic console hiding the take's map; tier-1 wrapper lacked label= (wrong-reason failure); the
  retirement-barrier property untested and the recovery test fabricated states. P3: sweep not durable/quarantining.
- Fixed -> B-candidate-1 (uncommitted): diff de33a520c66753a3a0dcab7d1a2c56a29df061ee55ed8f5acf5548c5f8a76ef8, tree
  56672d6d45eb83851caabaaec5a21ee2489b4755, console.py 4c7c5638…, tests 60ec38d6…; delta B-candidate-1/delta-0-to-1.diff.
  535 test functions (528 + 7). Codex delta confirmation running. The S1 spec must be re-pinned to candidate-1.
- Codex delta review of B-candidate-1: REQUEST CHANGES, no P1 (reviews/B-impl-candidate-1.md); fixes 1-3 confirmed;
  fix 4 fixtures wrong (submit always adds variables {}); fix 5 sweep barrier forgotten on retry and recovery
  ignored a failed sweep.
- Fixed -> B-candidate-2 (uncommitted): diff 64e6dc371e0b7309785db2464c5e9cca3e2f3903e01b91aefaf91716bbe2926e, tree
  1df984083e5cb23b4e1af3dac7733705c3b1fa90, console.py 78aef144…, tests 0c822552… (536 test functions). Codex delta review running.
- Codex delta review of B-candidate-2: REQUEST CHANGES (reviews/B-impl-candidate-2.md): fixes 4 and 5 confirmed;
  P2 a cycle's repair during pending recovery made a synthetic console hiding the take's map; P3 test that path.
- Fixed -> B-candidate-3 (uncommitted): diff 0a00336feb10dcd5c8839893cabafbdc5cbea20474f918d76dc1e0eca3f2d01d, tree
  b447955f60c528e78d05c324ecc4c4317128d1a1, console.py 010061b2…, tests f01bf285… (537 test functions). Delta review running.
- Codex delta review of B-candidate-3: APPROVE, no remaining P1/P2/P3 (reviews/B-impl-candidate-3.md).
- Proposal re-pinned to candidate-3: B-sel1/PROPOSAL.md sha256 (see below); S1 = 25 explicit tests (9 option B,
  3 tier 1, 13 existing), spec-S1.json efeabe5f…, spec-C0.json 32a5ec89…; supervise.py 206db6c9…, launch.sh b600a314…
  unchanged. NOTHING EXECUTED. Waiting for Governance's concrete allocation (C0 first, then S1).
8d77dbbf9eefceee0deb45909991122eab1739ea81e5d3c4c85497ba72d97247  PROPOSAL.md
- Emmy requested the full proposal pasted (browser cannot load relative paths): pasted verbatim with absolute paths,
  exact C0/S1 commands, the 25 node IDs and full hashes. Acknowledged as OPEN WORDING DEPENDENCIES ONLY (chassis
  drafting, John approves the text): tier-1 contract §2.2 "destructive and atomic" and the unconditional next-read
  sentence, and §2.3 "exactly one file", to be reconciled with f75420c behaviour. Not folded into option B; contract
  unchanged; nothing executed, adopted, published or re-pinned.

## Checkpoint 17 (2026-10-11) — Governance §30: supervisor REQUEST CHANGES; v2 prepared (nothing executed)
- §30 findings: P1 no exception-safe cleanup / reporting could block it; P1 failed status lookups read as
  ended, no ownership/cgroup proof before release; P2 admission gaps, pre-GO not checked, no timeouts/infinite
  GO wait/unbounded cleanup, `trap - INT` insufficient, terminal OOM missable, no post-run identity; validation
  gap -> deterministic failure-injection controls required; justify thresholds vs ELSPETH.
- v2 in B-sel1/v2/: supervise.py 99ec9c57…, launch.py (python launcher) 90ffbc2c…, run_controls.py cebef99d…,
  spec-S1.json 01d5220b…, controls.json e62fbd61… + controls/K00..K13 (14 controls); SHA256SUMS; PROPOSAL.md.
  Only py_compile run. Codex read-only review of v2 running. Capacity refresh deferred to the allocation request.
- Wording: Chassis drafts its brief; the Vehicle owns the contract wording; the tier-1 contract inconsistencies
  (§2.2 destructive-and-atomic, unconditional next read; §2.3 exactly one file) remain Vehicle-owned coordination
  dependencies, not transferred.
- Codex on supervisor v2: REQUEST CHANGES (reviews/B-supervisor-v2.md): P1 post-spawn registration gap and
  cleanup interruption; P1 release proof/ownership (permission errors read as absent, no cgroup proof when
  unrecorded, unit-name reuse, process-group escalation); P1 harness timeout abandons a scope; P2 terminal OOM
  window, deadlines, admission heuristics, reporting/identity, cause-specific controls.
- Decision (advisor-backed): v3 moves lifecycle enforcement to systemd (transient service, unique unit name per
  run, RuntimeMaxSec backstop, TimeoutStopSec, KillMode=control-group, OOMPolicy=stop -> Result=oom-kill,
  reset-failed + LoadState=not-found proof). Read-only host facts: systemd 255.4, cgroup2fs, DefaultOOMPolicy=stop.
- v3 prepared in B-sel1/v3/ (nothing executed; py_compile only): supervise.py 6b5076c6…, launch.py (execs payload),
  run_controls.py (cause-specific checks, independent proof, decoys, ends on exit 4/timeout/leak), spec-S1.json,
  controls.json + 18 controls (K03 last), SHA256SUMS d3483aac…, PROPOSAL.md. Codex read-only review of v3 running.

## Checkpoint 18 (2026-10-11 ~22:50 AEDT) — v3 review verified; stale relay reconciled
- v3 review VERIFIED (not restarted, no duplicate): the resumed Codex reviewer completed; its report (2026-10-11T11:46:50Z)
  states it checked SHA256SUMS d3483aac… and all 23 hashes. Saved verbatim reviews/B-supervisor-v3.md sha256 bba964e7….
  The browser's "v2" label is the agent's first-spawn label. Verdict: REQUEST CHANGES — new P1 (RemainAfterExit=yes with
  ExitType=main: a successful main exit disables RuntimeMaxSec while descendants may survive); P2 residues on all eight
  v2 findings (cleanup loop guards, InvocationID before stop and derived cgroup proof, harness log parsing before
  emergency stop, deactivating treated as terminal and premature Result capture on sample OOM, soft deadlines, admission
  omission (disclosed; not relied on alone), single final outcome in reporting, K08b/K09 qualification gaps).
- Stale relay (browser message 24, master §14) reconciled: Option B is NOT pending. John decided in this conversation
  (tier 1 approved, Option B next, console absence accepted, threat model not adversarial), tier 1 merged f75420c,
  Option B design approved (5 rounds), candidate-3 approved (implementation review), master §30 holds the supervisor.
  Nothing reverted; candidate-3 and its approval preserved; no-execution hold intact.
- Next: supervisor v4 (ExitType=cgroup, no RemainAfterExit, ExecStopPost terminal recorder) in B-sel1/v4/.
- v4 prepared (nothing executed; py_compile only): B-sel1/v4/ — ExitType=cgroup, no RemainAfterExit, ExecStopPost
  record.py -> TERMINAL.json; cleanup fully guarded, never stops a foreign InvocationID, cgroup proof recorded/derived/seen;
  harness tolerant parsing + prefix stop + finally report; outcome decided once; 20 controls (K16 descendant, K17
  cleanup interrupt; K03 last). SHA256SUMS 36f24da22d595b5d90257dda86e0d12821ed1617712d9de06f0eb8475c823a66;
  supervise.py 91ba9ba9…, record.py 1ab08ff4…, run_controls.py 4df611e2…. Codex v4 review (same reviewer, resumed) running.
- Codex on v4: REQUEST CHANGES, NO P1 (reviews/B-supervisor-v4.md): v3 P1 fixed; #1 #2 #6 #7 confirmed; P2 harness
  discovery/finally, recorder-after-publication, deadline edges, K10 bypass; P3 K16 assertion.
- v5 prepared (py_compile only): SHA256SUMS e66c1223…; supervise.py 757a610e…, run_controls.py 3d942390…. Review round
  scoped by the termination rule (another round only for a P1 anywhere or a P2 in v5's changes). Running.
- Codex on v5: APPROVE under the termination rule (reviews/B-supervisor-v5.md): no P1, no P2 in v5's changes; three P3
  residuals for the post-control review (final-state show after terminal_wait_s; exception-recovery wording; dropped
  release_contains check, unused).
- Read-only capacity snapshot after approval: B-sel1/v5/capacity-snapshot.txt (sha256 fdca7848…): 24 CPUs, busy 17.9%,
  load 6.48, MemAvailable 33.7 GiB; ELSPETH CI (4 workers) + one long ELSPETH process running; no Space units/containers;
  GPUs idle.
- Package for allocation: B-sel1/v5/PROPOSAL.md (sha256 below) + SHA256SUMS e66c1223…. NOTHING EXECUTED.
3c10398f63ba6f9bfb3fe01e3d833b57aa015fd69b0a59734aa27f5d81c5af6a  PROPOSAL.md

## Checkpoint 19 (2026-10-11) — Governance §31 REQUEST CHANGES on v5; v6 prepared (nothing executed)
- §31: (1) same-user processes deny cwd/exe/environ (EACCES): user systemd 1594, (sd-pam) 1623, sshd sessions (+ two codex,
  seen in my read-only recheck); blanket fail-closed scans would refuse K00 and block cleanup proof; (2) per-control
  bounds sum to 6,350 s: need a suite-wide bound with bounded recovery; (3) decoys created before a failed start returns
  a handle must be owned/discovered/cleaned. P3 dispositions adopted; K03 release only by owner receipt after proof.
- v6 (B-sel1/v6/; py_compile only): token proof clears unreadable processes only by start-time predating the run;
  admission sets aside unreadable processes only if comm in UNREADABLE_HOST_COMMS and argv names nothing of Space;
  suite budget 1800 s + recovery 180 s + outer transient unit space-vehicle-b-suite-k1 RuntimeMaxSec 2040 (--no-block);
  decoy names space-decoy-<suite token>-<n> recorded before start; final proof. SHA256SUMS 5fc0dcd1…, PROPOSAL.md 9a0350d7….
  Codex (same reviewer) reviewing v6, scoped.
- Codex on v6: REQUEST CHANGES, one P2 (recovery time not reserved: recovery could start ~1,890 s and outrun the 2,040 s
  outer cutoff) (reviews/B-supervisor-v6.md); cleanup-ownership rule accepted for ownership only; codex admission
  exception justified as an operational heuristic, not exclusivity; wording overstated discovery.
- Program lead clarified: cleanup ownership classification is not resource admission; an older process can launch new work.
- v7 (B-sel1/v7/; py_compile only): post_control_reserve_s 120 + every post-run step capped at the suite deadline (recovery
  starts by 1,800 s, ends by 1,980 s; worst case ~34.5 min); admission vs ownership stated separately in source and
  proposal; failed argv read refuses admission (verified read-only: unreadable processes' cmdline is readable; codex empty).
  SHA256SUMS 422ff9aa…, PROPOSAL.md ad79fee5…. Codex v7 review (scoped) running.
- Codex on v7: APPROVE (reviews/B-supervisor-v7.md): v6 P2 fixed; ownership vs admission correctly separated; failed argv
  refuses; no further round. One P3: the launch example's WorkingDirectory named v6 -> fixed (one-line diff only).
  FINAL: B-sel1/v7/SHA256SUMS 422ff9aa4ed7573fc9e79117f57e7135ac10c7f8cdfde2d44fcee53b78f55b32 (unchanged, reviewed);
  PROPOSAL.md 4fe7c40ca3e094fa64a807605feee7d02c882cc324f3256420f40a082495fdb8 (reviewed ad79fee5… + the P3 path fix).
  NOTHING EXECUTED. Waiting for a concrete Governance allocation of K (fresh allocation-level admission first).

## Checkpoint 20 (2026-10-11 23:40 AEDT) — §32: obsolete watcher retired; fresh admission evidence
- Verified PID 1664354 (bash, start 2026-10-10 10:44:40, ticks 53945734, PPID 1410330 = Claude CLI --resume=a728e992 "Space
  Vehicle", env session a728e992), polling tasks/b2em98w09.output, whose target completed 2026-10-10 10:53 (exit 0); the loop
  self-matched via pgrep -f. Output preserved; identity re-verified; SIGTERM to that PID only; confirmed gone 23:40:15.
- Found and LEFT RUNNING a second obsolete watcher, PID 1605464 (same session/parent/target, start 10:31:55) — not named by
  §32 and not matching v7's admission predicate. Awaiting instruction.
- Fresh read-only admission evidence 12:40:41 UTC: 40.72 GiB available, CPU busy 23.7%, load1 4.76; v7 predicate (reproduced
  independently, no supervisor code run) matches none; unreadable processes all set aside by the host rule (systemd, sd-pam,
  7 sshd); no Space units/containers; suite unit not-found. Record: watcher-retirement/RECORD.md, admission-snapshot.txt.
  v7 package and candidate 3 unchanged. Allocation: NONE.

## Checkpoint 21 (2026-10-11 23:48 AEDT) — K LAUNCHED ONCE under SPACE-20261011-B-V7-K1 (§33)
- Pre-launch (12:48:37–39Z, within 60 s): manifest 422ff9aa… (26 entries), proposal 4fe7c40c…, HEAD f75420c, diff 0a00336f…,
  tree b447955f, fresh evidence dirs, unit unused; admission 36.16 GiB / 21.2% / load 5.11, no matches/unclassified/units/containers.
  Record: B-sel1/v7-K1-prelaunch.txt.
- Launched 2026-10-11T12:48:39.46Z (systemd-run exit 0 at 12:48:39.49Z): space-vehicle-b-suite-k1.service, InvocationID
  0eb412ca87ef44aaad5fc21f4c8e8885, MainPID 268508, RuntimeMaxSec 2040 (34 min), TimeoutStopSec 30, KillMode control-group, Nice 19.
- NO RETRY under any outcome. Slot stays RESERVED until explicit owner release + Governance-verified cleanup (K03 exit 4 does not release).
- K COMPLETE: 20/20 controls passed (K03 exit 4 as expected); suite final proof proven_clean; unit Result=success, ended by
  12:54:38Z (launch 12:48:39Z, ~6 min). Independent owner check clean (v7-K1-postrun.txt). Evidence manifest
  v7-K1-evidence.SHA256SUMS (122 files). Owner release receipt v7-K1-OWNER-RELEASE.md written; the slot is free only after
  Governance's independent verification. Next (separately, only if allocated): S1.

## Checkpoint 22 (2026-10-12 00:15 AEDT) — S1 LAUNCHED ONCE under SPACE-20261011-B-V7-S1-01 (§35)
- Pre-launch 13:15:46–48Z: all identities matched (manifest + 26, proposal, spec 6bcb9af0…, supervisor, HEAD, diff, tree b447955f);
  evidence-S1 and s1-supervisor.out absent; unit unused; admission 37.75 GiB / 22.2% / load 5.73, clean. Record v7-S1-prelaunch.txt.
- Launched 13:15:48.19Z (systemd-run exit 0): space-vehicle-b-supervisor-s1-1.service InvocationID c121704d83e94f61ba9029f63cf0a11c,
  MainPID 479440, RuntimeMaxSec 900, TimeoutStopSec 30, KillMode control-group, Nice 19. NO RETRY. Slot held until owner release
  + Governance verification.
- S1 COMPLETE: pytest exit 0, 25 passed in 25.75s; JUnit 25 cases = the 25 selected IDs, 0 failures/errors/skips; SERVICE_RESULT
  success, oom_kill 0, memory.peak 559 MiB; caps read back; identity unchanged; supervisor exit 0, cleanup verified; independent
  owner check clean (v7-S1-postrun.txt). Evidence manifest v7/v7-S1-evidence.SHA256SUMS. Owner release v7-S1-OWNER-RELEASE.md;
  the slot is free only after Governance verification. Option B candidate-3 now has: design approved, implementation approved,
  supervisor qualified by K (20/20), S1 green. Next steps need new authority: full two-lane qualification, commit, PR.

## Checkpoint 23 (2026-10-12) — §36: S1 accepted, slot released; final integration package + gate proposal prepared
- Candidate 4 (uncommitted): candidate 3's code/tests byte-identical + README round entry (528 -> 537) + ADR 0002 (xlv).
  Diff 8d14db52…, tree 3e8c2faeb3b79cd1e06af5907c26f6cfd9211607 (B-candidate-4/).
- Gate package B-sel1/gate/ (SHA256SUMS df9cd817…): PROPOSAL-G.md, gate_lane.py, spec-G312/G313 (v7 supervisor, detached
  gate worktree gate-B4-ca87a9 with the diff applied, 551 expected (static AST), -n 2, deadlines 3300/2700, outer 3900/3300,
  serial with G313 only after G312 passes), interpreters.txt, COMMIT_MESSAGE.txt, PR_BODY.md, CONTRACT-PACKAGE-B.md.
- Nothing executed (only interpreter metadata reads and a static AST count). Codex review of the package running.
  Publication of option B needs John's approval (practice.md:24); not a preparation blocker.
- Final-package review r1 (reviews/B-final-package-r1.md): REQUEST CHANGES, no P1. P2: CONTRACT-PACKAGE-B overclaimed
  (destructive-and-atomic only with qualifications; next-read false; exactly-one false); P2 xdist hidden worker restarts; P3s.
- Fixed: candidate 5 (code/tests = candidate 3; README/ADR precision) tree ccc2782e350a6b9abe33d19db6884ac3fb82ec95, diff
  0d4da11e…; contract package rewritten with the reviewer's source-backed paragraphs; gate_lane --max-worker-restart=0 +
  crash detection + phases; PROPOSAL-G: tree-identity as proposed substitution, CI partial coverage, staging option G-2
  (static / whole-suite pytest per lane) with deadlines from measured tier-1 timings. Gate SHA256SUMS 69c681a2…. Confirmation
  review running. Nothing executed.

## Checkpoint 24 — 2026-10-12: final-package r2; xdist crash detection corrected; nothing executed

- Final-package review r2 (reviews/B-final-package-r2.md, sha256 20be1e14…): REQUEST CHANGES, no P1;
  one P2: crash detection missed `worker gwN crashed and worker restarting disabled`. Contract, README/ADR,
  proposal §3, cleanup, staging (G-2 preserves the gate), no-JUnit static specs and timings confirmed.
- **Record correction:** checkpoint 23 said r1 was saved to reviews/B-final-package-r1.md; it was not on
  disk. Recovered verbatim from the session transcript (record 11293, 2026-10-11T13:36:13.830Z), with a
  recovery header: sha256 29e38fe8….
- **Count correction:** G/SHA256SUMS has 14 entries, not 15 as I stated to the reviewer.
- Source check (installed xdist 3.8.0, `xdist/dsession.py`): under `-q` (verbosity -1), `report_line`
  (:78–80) and the `xdist:` summary (:271–272) print nothing, so the restart-disabled diagnostic the
  reviewer named never reaches the output. `[gwN] node down: <error>` (:552) prints at every verbosity.
  The driver now matches a regex over all of them; the docstring and PROPOSAL-G no longer claim the flag
  alone forces failure. Pattern checked against literal strings only (no pytest, no gate).
- Re-frozen: gate_lane.py 041db285…, PROPOSAL-G.md 1fe782f0…; G/SHA256SUMS (14 entries) 0dc258a8…
  (supersedes 69c681a2…). Specs and candidate 5 unchanged.

## Checkpoint 25 — 2026-10-12: final-package r3 APPROVE; package final; nothing executed

- reviews/B-final-package-r3.md (sha256 7ba6b71f47d36fb5d7f5bb75c418ebb9402293858ef6a0cff52bfd14211d2541): APPROVE; r2 P2 resolved; the -q finding confirmed; every
  xdist error-down caller supplies a truthy error; manifest 0dc258a8… verified (14 entries).
- Final package: G/SHA256SUMS 0dc258a8e9f48b72f98783a9de8d5a8157f31647f28046dfb2f5bcc0b5532a64; candidate 5
  diff 0d4da11e…, tree ccc2782e…. Held: Governance on tree identity; a gate allocation; John's publication approval.

## Checkpoint 26 — 2026-10-12: quiet-console wording precision; r4 APPROVE; relay record

- CONTRACT-PACKAGE-B.md §2.2: the untouched-console rule now requires an empty `commands` list on both
  branches (matches console.py:4411–4419). sha256 5f2c3295…9705.
- reviews/B-final-package-r4.md (sha256 3043f59c5b3a0df8f6d40583e3288e90c653e0bb3c0e7036754f2c1c8b4ea9ba): APPROVE; manifest verified.
- Final G/SHA256SUMS (14 entries): bbfd222b59d7a28b1da256012ff77388bb8aaa14ec6fb4dd0feaa9475609c418.
- B-sel1/G-RELAY-FINAL.md (sha256 d46c1ed6513a2cc07fab99ed135ac0490b58fbf5fc0f232545c8081226c47dc2): full paths, expanded commands and hashes, and the helper-only
  disclosure. PROPOSAL-G §6 is stale (lists only r1); disclosed there, not re-frozen.
- No gate, test, collection, supervisor or systemd run; no commit or publication.

## Checkpoint 27 — 2026-10-12 01:00 AEDT: Governance §37; local candidate commit (UNQUALIFIED / UNPUBLISHED)

- §37 (read in full): reject the tree-identity substitution; literal committed-head qualification; one
  local unpublished candidate commit under a coordinator sequencing exception; G-2 selected
  (G312s → G312p → G313s → G313p, deadlines 300/3000/300/2300); repin specs; clean detached checkout;
  replace the relay's prelaunch block (masked failures); update proposal §§2,3,5,6; re-freeze; confirming
  review; G312s only may then be considered under a separate allocation. No execution grant.
- Pre-commit checks: topic worktree $SP/b-39-ca87a9 at f75420c on codex/39-take-by-rename; exactly the four
  files modified; base-relative diff 0d4da11e…; nothing staged; no untracked. No active hooks (samples only,
  no core.hooksPath), no commit signing. A first attempt stopped before committing on my own staged-set
  check (locale `sort` order); staged set was exactly the four files and the index tree ccc2782e…;
  re-checked with LC_ALL=C and committed.
- **Commit 7a87eb82cfef55dcc74248df41720883587ca7af**, parent f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f, tree
  ccc2782e350a6b9abe33d19db6884ac3fb82ec95; message byte-identical to G/COMMIT_MESSAGE.txt (0e7bb031…); worktree
  clean after; no upstream configured. Not pushed. UNQUALIFIED until both full lanes pass and the final evidence
  review passes.

## Checkpoint 28 — 2026-10-12: committed-head G-2 package revised; confirmation r5 requested; nothing launched

- Specs G312s/G312p/G313s/G313p repinned: workdir $SP/gate-C-7a87eb8, expect.head 7a87eb82…, base f75420c and
  diff 0d4da11e… kept (the v7 identity function hashes `git diff <base>`). G-1 specs, the r4 proposal and the
  r4 relay moved to G/superseded/ (outside the manifest).
- New G/gate_worktree.sh (create / verify / remove; every exit checked, fail closed; not-forced removal)
  replaces the relay's patch-and-throwaway-index prelaunch block that §37 rejected. Only `bash -n` run on it.
- PROPOSAL-G.md rewritten (§§1–6: commit, evidence, §37 sequencing exception, G-2 only, review index r1–r5).
  PR_BODY evidence and review lines updated. G/SHA256SUMS (13 entries) 02631b87…. Relay regenerated.

## Checkpoint 29 — 2026-10-12: r5 approve with changes (one P3) fixed; r6 requested; nothing launched

- reviews/B-final-package-r5.md (eb3b9ab3…): approve with changes; P3: gate_worktree.sh ignored `rm` failure of
  its temp file. Fixed: both removals checked, original failure preserved (gate_worktree.sh f73c046c…). PROPOSAL-G
  §2/§6 updated (d779b632…). G/SHA256SUMS (13) 4956e7ae…. Relay regenerated. `bash -n` only.

## Checkpoint 30 — 2026-10-12: r6 APPROVE; committed-head G-2 package final; nothing launched

- reviews/B-final-package-r6.md (3d494e08c90635ab809c808be00ff3adaf583e6a35ff05f0e259a15a7cb91847): APPROVE; P3 resolved; manifest 4956e7ae… 13/13.
- Final: commit 7a87eb82… (UNQUALIFIED / UNPUBLISHED); G/SHA256SUMS 4956e7aec8001a75df7d704fba24fe8816809e4f6f94277241c79cf3deee4b6d;
  relay a0669a93a4b6f4694383ec64cc3a36a4b9eab71504469bccfa93057fea22153c (lists r6). PROPOSAL-G §6 shows r6 pending (not re-frozen). Next: Governance may consider G312s only.
