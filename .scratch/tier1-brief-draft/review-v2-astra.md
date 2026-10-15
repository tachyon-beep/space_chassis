**APPROVE WITH CHANGES.** Both supplied SHA-256 hashes match. No files changed; no tests, collection, builds, containers, git mutations, or `.env` reads.

References below: **Draft** = [frozen draft](/home/john/space_chassis/.scratch/tier1-brief-draft/brief-wording-tier1-v2.md); **V** = `docs/deep_research/vehicle/tools/console.py` **at f75420c**, not the working tree.

No Critical findings.

1. **Important — observing quiet does not make an in-place submission safe.** Draft:54–58 and 127–130 overstate the protection. A single writer can observe quiet, truncate the file, then finish writing after the vehicle reads partial JSON and replaces it. The completed batch is then on an unlinked inode. V:581–594, 4340–4343 implement this path. The cited test writes **after the read completes** (`tests/test_vehicle_config.py:22578–22583` at f75420c), so it does not establish safety during an in-place write.

   Replace Draft:54–58 with:
   > A pass that reads a quiet console does not rewrite it. Use one coordinated writer and publish a complete console through a temporary file and atomic rename. Writing in place can expose a partial console that the far side rejects and replaces. Wait for the far side’s cleared console before submitting again; an earlier nonquiet read can still overwrite a later publication.

   Make F.1 carry these same qualifications. An arbitrary quiet file written by the agent does not cancel an already pending nonquiet claim.

2. **Important — D still promises too many guarantees about results.** Draft:74 says every answered command produces exactly one file. A deferred command produces an acceptance verdict and later a settlement verdict; both are published (V:4019–4040, 3584–3624, 4491–4493). Result recovery can also write another copy when its bounded scan fails to find an existing receipt (V:3263–3280).

   Replace Draft:74 with:
   > Read the far side’s answers in `output/`; a deferred command can report first its acceptance and later its settlement:

   Thus execution at most once must remain distinct from result-file cardinality.

3. **Important — the rewrite census includes paths that normally never reach claim.** Draft:92–95 says links and non-regular files all reach the rewriting branch. Stable instances fail the preceding checks, and that window skips ingestion (V:4220–4228, 3074–3091). Also, a present non-map `variables` forces rewriting **even when no map is known**; Draft:36–37 and 94–95 obscure that case (V:4348–4351).

   Replace Draft:35–37 with:
   > Once the window’s checks permit intake, every other shape takes the rewrite path: a nonempty batch; a missing, unreadable or invalid console; absent or non-list `commands`; present non-map `variables`; or absent `variables` while a map is known.

   Replace Draft:92–95 with:
   > These are rewrite attempts once claim is reached. A symlink or non-regular console detected by the earlier window checks skips intake without rewriting; one introduced after those checks can instead reach the ingress-refusal path.

4. **Minor — correct two source descriptions.** Draft:99’s “becomes true only” omits initialization (V:4158–4163). Replace Draft:99–100’s first sentence with:
   > A fresh window starts with a known empty map; resume resets that knowledge, then adopts a readable console map, and later claims also adopt maps.

   Draft:65’s fixture parenthesis says “landed,” although `contract/fake_diode.py:220–223` still rewrites unconditionally. F.3 makes the dependency clear, but the row should explicitly say:
   > fixture `contract/fake_diode.py::AgentSide.consume` (future adoption requirement: implement the identical quiet rule and add its test before citing it as evidence).

**Q1 — CORRECT.** Draft:26–31 and 82–87 clearly distinguish atomic replacement from read-then-claim. V:454–465 performs temporary-file replacement; V:4340 and 4365–4370 perform separate read and write operations. No remaining atomic-claim transaction promise.

**Q2 — CORRECT for execution in the specified adoption deployment.** Claim precedes validation (V:3536–3581); a raised claim supplies no new batch. Nonempty claims receive file-and-directory durability only with a journal (V:4369, 454–465). The adoption script passes `--state-dir` at `.claude/worktrees/vehicle-adoption/containers/serve_vehicle.sh:90`, creating a journal through V:2854–2856; the main script’s invocation at `containers/serve_vehicle.sh:109–117` passes neither flag. E correctly distinguishes process-crash from host-crash protection. No duplicate retained command effect found; “not exactly once” is justified. D’s result promise needs finding 2.

**Q3 — OVERSTATES.** Successful claim rewrites satisfy quiet, including resume’s unknown-map case (V:4380–4390, 5037–5046). Empty `commands` cannot prove delivery. “If it is still there” withdraws unconditional delivery, but the quiet-observation advice needs finding 1.

**Q4 — OVERSTATES.** The read-to-rename loss applies to both renamed-in and completed in-place publications, with no result or record **for the erased batch** (V:4325–4337). Correct the rewrite census as finding 3.

Option B is clearly future, not implemented or qualified here. All three named vehicle tests exist at f75420c:22541, 22598, 22658. README:19406–19429 supports the three-of-three historical losses, not a new load guarantee. F’s driver hash and +141-line change check out; outstanding gates remain reported limitations, not independently rerun evidence.

