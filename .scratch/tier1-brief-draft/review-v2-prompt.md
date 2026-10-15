Bounded, independent, read-only correctness review of a draft of agent-facing brief text. Do not edit any file, run tests, collect tests, build, start containers, change git state (no checkout, fetch, submodule update, stash or add), or read any `.env` file. Reading files and `git show`/`git diff`/`git log` are fine.

Repository: /home/john/space_chassis (chassis). The draft under review is frozen:
  .scratch/tier1-brief-draft/brief-wording-tier1-v2.md  sha256 9e8b5192f740ce7de27a69a258fb477a0e5d1aa61391dacbed05c49de136daae
Verify the hash first. Review sections A (two replacement bullets for brief/PROTOCOL.md lines 51-54), B (replacement for lines 59-60), C (a new docs/brief-claims.md row) and D (a proposed line-68 qualifier). Sections E and F are the author's sourcing and limitations; check them as claims too.

Authorities to check against:
1. The vehicle's formal adoption package: governance/vehicle/records/2026-10-11-39-tier1-adoption-package.md (sha256 483d47de01ade46d3e6bbea16f5ce04bd93ec7b7e3d5d1dab26336275850a360).
2. Vehicle code at f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f (PR #43), read with `git -C docs/deep_research/vehicle show f75420c:tools/console.py` (and `:tests/test_vehicle_config.py`, `:README.md`); `git -C docs/deep_research/vehicle diff f44399645fb2633e695a5d758cb5a41f43fb848c f75420c` shows the tier-1 change. Do not check out; the main checkout's vehicle working tree is NOT at f75420c.
3. Current text: brief/PROTOCOL.md, docs/brief-claims.md, docs/diode-contract.md §2.2, contract/fake_diode.py (AgentSide.consume).
4. The deployment the text is to land on: /home/john/space_chassis/.claude/worktrees/vehicle-adoption/containers/serve_vehicle.sh (passes --state-dir) versus /home/john/space_chassis/containers/serve_vehicle.sh (aurora-port HEAD, passes neither --state-dir nor --journal).
5. Existing evidence summarised in the package and the vehicle README's #39 section (the chassis diagnostic traced three of three losses to quiet-cycle rewrites at f443996).

Answer these four questions specifically, each with a verdict (CORRECT / OVERSTATES / UNDERSTATES / WRONG) and file:line evidence:
Q1 Atomicity. Does the text correctly distinguish the atomic file replacement (temporary file + os.replace) from the non-atomic read-then-claim? Is any wording still readable as an atomic claim transaction?
Q2 At-most-once scope. Is "a command runs at most once" exactly as strong as f75420c supports: claim before act; a raised claim runs nothing; durability (fsync file+dir) only when the executive keeps a journal; the adoption's --state-dir giving a journal; process crash vs host crash; "not exactly once". Look for any path where a claimed command could run twice, or where the text promises more (e.g. results) than the code gives.
Q3 Quiet-state observation. Is it true that the far side's own rewrite always leaves the console in the quiet shape (claimed_console vs the `quiet` predicate, variables_known transitions including resume)? Is it true that putting a batch in place only over a quiet file avoids the far-side erase race, and that an empty `commands` does not by itself prove a batch was taken? Is "claimed then if it is still there" free of an unconditional next-read guarantee? Is anything implied about observing `commands` empty that the evidence does not establish?
Q4 Remaining nonquiet claim loss. Is the residual stated completely and no more broadly than the code: which passes still rewrite (batch, missing/unreadable/not-a-console, no `commands` list, `variables` absent or non-map while the map is known), the read-to-rename window, renamed-in vs written-in-place, no result and no record? Is any rewriting path omitted or any non-rewriting path wrongly included?

Also: does any part of the draft imply that Option B (take by rename, republish only if absent) is implemented, tested, adopted or qualified? Is the claims row's source list accurate (names exist at f75420c; the fixture entry is correctly marked as future)? Any other false or misleading statement for an agent reader.

Output: a short verdict line (APPROVE / APPROVE WITH CHANGES / REJECT), then findings ranked Critical / Important / Minor, each with evidence and, where you propose wording, the exact replacement text. Then the four Q verdicts. Keep it bounded: under 900 words.
