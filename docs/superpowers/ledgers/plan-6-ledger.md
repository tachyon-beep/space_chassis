# SDD ledger — plan: docs/superpowers/plans/2026-10-09-aurora-port-6-long-life.md
Spec: docs/superpowers/specs/2026-10-09-aurora-port-design.md. Branch aurora-port. Executor: inline (Opus 5.5). Goal set by John 2026-10-09: plan and execute the four open long-life items and the archive gap; Opus subagent review; Astra high (codex-cli) final review.
Plan reviewed by an Opus subagent before execution (verdict: revise); corrections in a502eae.
Ruling: Task 5 is a deviation from spec §3 ("watchdog ported as-is"); John's goal authorises executing the gap; argued as a resource bound (ENOSPC on /work breaks the ladder) — cost if wrong: one function to revert.
Evidence (OpenRouter /api/v1/models, 2026-10-09, curl): "deepseek/deepseek-v4-pro 1048576 1024000 384000" (context_length, top_provider.context_length, top_provider.max_completion_tokens); "deepseek/deepseek-v3.2 163840 163840 147456".
Pre-flight: tasks share no interfaces (health/status/review; common; root test + docs; docs; watchdog + journal + README + draft). Pre-flight: no shared interfaces.
Task 1: Ruling: the review cache cell carries title='cache share' so its dash is testable apart from other empty cells — cost if wrong: none. Existing spend tests now compare the three original keys (spend gained keys).
Task 1: complete (commits a502eae..a676641, tests: python3 -m pytest tests -p no:cacheprovider -n 8 → 545 passed in 27.53s)
Task 2: complete (commits a676641..7cc4807, tests: python3 -m pytest tests -p no:cacheprovider -n 8 → 551 passed in 52.11s)
Task 3: RED by mutation (MODEL_CONTEXT 500_000 → AssertionError (200000, 1274)), restored GREEN. Schemas measured at 5098 chars ≈ 1274 tokens.
Task 3: complete (commits 7cc4807..245a932, tests: python3 -m pytest tests -p no:cacheprovider -n 8 → 552 passed in 36.35s)
Task 2: Ruling (after a background security review of 7cc4807, 'audit-log-erasure'): rotation is opt-in (max_bytes=None default); only fleet.jsonl rotates; journal.jsonl and shared.jsonl stay append-only per spec 3.4 — they are on the host disk (operator/journal), not the 1 GiB image as the re-triage said. Fixed in cbac94f, tests RED→GREEN (test_without_a_cap_append_never_rotates, test_the_fleet_monitor_rotates_its_summary_log) — cost if wrong: the journal's files grow on the host disk unbounded (bounded per pass by JOURNAL caps).
Task 4: Ruling: added docs/design.md to test_citations' CITING so the docs-only task has a RED ("cites no test") → GREEN — cost if wrong: none.
Task 4: complete (commits cbac94f..ab251d4, tests: python3 -m pytest tests -p no:cacheprovider -n 8 → 556 passed in 38.50s)
Task 5: Ruling: fresh_session now returns the archive name it made (None when there was no session), passed to prune_archives as keep_newest — the plan's "pass the just-created archive explicitly" — cost if wrong: none.
Task 5: Ruling: the journal test's fake docker now runs the journal's own tar arguments (with /work mapped to the test repo) instead of a fixed `tar -cf - .git`, so the exclude is tested behaviourally; the other 34 journal tests pass unchanged — cost if wrong: none.
Task 5: Ruling: a false-claim pattern ("archived conversations and all") guards the README fix — cost if wrong: none.
Task 5: complete (commits ab251d4..bbc4fb7, tests: python3 -m pytest tests harness/tests -p no:cacheprovider -n 8 → 774 passed in 39.45s)
Opus code review (a502eae..bbc4fb7): no Critical; 3 Important.
Final(Opus): re-graded minor "session_*.json catches agent-chosen names" to Important — an agent's tombstones/session_index.json would be deleted (lost agent data).
Final(Opus): fixed I1 prune after the copy it makes room for — test_a_fresh_restore_prunes_before_it_copies RED→GREEN.
Final(Opus): fixed I2 symlink test vacuous under lstat→stat — assertion added; mutation now fails it.
Final(Opus): fixed I3 brief draft covers 42, 43, fresh rungs and the patterns (draft, not shipped).
Final(Opus): fixed exact archive-name patterns — test_prune_never_touches_notes_symlinks_or_other_files (session_index.json) RED→GREEN. Commit cda245e; root+harness 775/775.
Final(Opus): minor (deferred): tests/test_common.py docstring still says journal.jsonl/shared.jsonl rotate.
Final(Opus): minor (deferred): notes can name archives that were pruned (stated in the draft).
Final(Opus): minor (deferred): README journal paragraph omits the recovery state the journal also keeps.
Final(Opus): minor (deferred): sort-by-name and drop-one-continue mutations survive the pruning tests.
Final(Opus): minor (deferred): the incarnations-per-hour test does not pin that the group's first timestamp is used.
Final(Opus): minor (deferred): test_status_reads_a_snapshot_published_before_the_cache_signals is misnamed (status computes live).
Final(Opus): minor (deferred): append_jsonl's docstring should say the second rotation discards the older generation.
Pre-fix full run (at cda245e's predecessor tree): merged 1708/1708 in 9m24s; live 14/14.
Final review: Astra (gpt-6-astra, high, codex-cli) on a502eae..cda245e: no Critical; 2 Important.
Final(Astra): fixed exit-43 archive lost to the first prune — test_the_exit_43_archive_survives_whatever_its_clock_says RED→GREEN.
Final(Astra): fixed directory-swap race (lstat check then path ops) — fd with O_NOFOLLOW; test_a_tombstones_swapped_for_a_link_mid_prune_is_not_followed RED→GREEN.
Final(Astra): re-graded minor 6 (draft overstates the bound and protection) to Important — agent-facing text for John's approval promised more than the code gives; fixed in the draft. Commit ce4f5e4.
Final(Astra): minor (deferred): the headroom test assumes the default model's limits without asserting the default model is deepseek-v4-pro.
Final(Astra): minor (deferred): test_the_cap_counts_bytes_not_characters cannot tell bytes from characters at its cap (use 150); test_the_fleet_monitor_rotates_its_summary_log accepts max_bytes=None.
Final(Astra): minor (deferred): pruning tests do not separate name order from mtime order, or cut-at-budget from drop-and-continue; the hourly test does not pin the first timestamp (also Opus).
Final(Astra): minor (deferred): DeepSeek's contract (with tools present) asks for reasoning from non-tool assistant turns too; the seed keeps it on tool calls only — design.md should say so.
Task 6: complete — merged 1711/1711 (6m35s), live 14/14 on ce4f5e4; Opus review and Astra final review done, one fix pass each; filigree comments 31-35 and issue e5b2675c98 filed.
Post-final: the archive clause approved by John and shipped in 1697ca9.
