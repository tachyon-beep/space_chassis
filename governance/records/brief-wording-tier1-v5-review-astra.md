APPROVE — `74b44459de4e061908cb8c66b10e45d1226995a3cd96be7a31db35e1e1faba5b` (SHA-256 verified).

References below use **v5** = [brief-wording-tier1-v5.md](/home/john/space_chassis/.scratch/tier1-brief-draft/brief-wording-tier1-v5.md). Both supplied predecessor/review hashes also match; v4→v5 diff inspected.

1. **RESOLVED — erased batch versus partial refusal** (v5:111). D adopts the proposed distinction verbatim: the intervening batch can disappear unanswered; partially read content can receive a refusal.
2. **RESOLVED — publication guarantees and retained paragraph** (v5:87–90, 99–103). Delivery wording matches the proposal: publication is conditional, retries can duplicate `seq`, and abandonment follows exceeding 256 owed answers. The replacement paragraph differs from the proposed wording by retaining refusal examples and “Failure and success are the same shape.” This preserves the meaning: it removes “all produce one,” uses publication time, and does not override C’s delivery limits.
3. **RESOLVED — intake qualification and variables census** (v5:37–41, 122). “Once the far side’s checks let it take the file in” paraphrases “Once the window’s checks permit intake”; the meaning is preserved. “Anything else is claimed” remains subject to A’s replacement-success condition. Present non-map variables and missing variables while a map is known are correctly distinguished.
4. **RESOLVED — required writer discipline** (v5:159–161). The proposed wording is adopted, including waiting for the cleared copy before replacing a claimable submission.
5. **RESOLVED — reconciliation precision** (v5:123, 132). The receipt citation now includes line 2516, and the claim-failure statement correctly allows publication of an earlier deferral’s settlement.

**Concrete defects:** None introduced or left unresolved by this delta; no Critical, Important or Minor findings, and no replacement text required.

**Coherence:** PASS — A, B, C, the replacement for PROTOCOL.md:75–78, and D agree within their stated assumptions. Pinned `tools/console.py@f75420c` supports the distinctions and publication limits; adoption [serve_vehicle.sh:90](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/containers/serve_vehicle.sh:90) supplies `--state-dir`, supporting the journal-dependent durability wording.

**F:** PASS — v5:139–152 retains V-1..V-3 as outstanding vehicle-owned coordination requirements, neither resolved nor transferred.

**Option B:** PASS — v5:171 explicitly disclaims implementation, testing, adoption and qualification; nothing elsewhere reverses that disclaimer.

Read-only source review only: no edits, tests or collection, builds, containers, git mutations, or `.env` reads.