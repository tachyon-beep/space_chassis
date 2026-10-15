Bounded, independent, read-only DELTA review of agent-facing brief text. Do not edit any file, run or collect tests, build, start containers, change git state (no checkout, fetch, submodule update, stash or add), or read any `.env` file. Reading files and `git show`/`git diff`/`git log` are fine.

Repository /home/john/space_chassis. Frozen artifact under review:
  .scratch/tier1-brief-draft/brief-wording-tier1-v4.md  sha256 78d3453ebd66d24a68495909f45bec952b1ac385dab53526b221b2bf8fb8aada
Verify the hash. Your previous review of v2 is .scratch/tier1-brief-draft/review-v2-astra.md (sha256 7236e1952d63c044eb07703b6ce1f2b26042bc85246518cc79febe23735b9e55); v3 (brief-wording-tier1-v3.md, b8249c9f...) applied it; v4 corrects v3. Compare v4's sections A (PROTOCOL.md 51-54), B (59-60), C (PROTOCOL.md:68) and D (brief-claims row) against v2/v3 and judge the delta, plus section E's reconciliation table and F/G.

Authorities: governance/vehicle/records/2026-10-11-39-tier1-adoption-package.md (483d47de...); vehicle code at f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f via `git -C docs/deep_research/vehicle show f75420c:tools/console.py` (and :tests/test_vehicle_config.py) — the working tree is NOT at f75420c; the deployment /home/john/space_chassis/.claude/worktrees/vehicle-adoption/containers/serve_vehicle.sh (passes --state-dir) versus /home/john/space_chassis/containers/serve_vehicle.sh; current brief/PROTOCOL.md, docs/brief-claims.md, docs/diode-contract.md, contract/fake_diode.py.

Check specifically:
1. Were all v2 findings resolved without introducing new overstatement?
2. Result counting (C and D): is "count answers by receipt seq, not by files" accurate — does every answer file end with a receipt line carrying seq; is a deferral answered at acceptance and at settlement; can an owed answer be written twice with the same seq; can one be given up; does anything in C/D still promise a fixed file count?
3. At-most-once with its limits beside it (A bullet 2): process-crash vs host-crash, the flush only with a journal (--state-dir), the stated reliance on the disk, "what it had not yet recorded of a claimed batch is lost and never answered" (check the durability order: claim fsync, tick row fsync, before results). Any path that runs a claimed command twice, or answers something later lost?
4. Cleared-console observation and next read (B): does the text promise anything beyond the code (single writer, rename publication, wait for the far side's cleared copy, cleared console does not identify which file was claimed, no time for the next read)?
5. Line numbers and names cited in E and D exist at f75420c and say what is claimed.
6. F: are V-1..V-3 accurate statements of the vehicle contract inconsistencies, and does the draft avoid editing the vehicle's wording or widening adoption?
7. Any implication that Option B is implemented, tested, adopted or qualified.

Output: one verdict line (APPROVE / APPROVE WITH CHANGES / REJECT), then findings ranked Critical / Important / Minor with file:line evidence and exact replacement text where you propose wording, then one line per check 1-7. Under 700 words.
