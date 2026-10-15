# #23 design review r3 — Codex (targeted)

Received 2026-10-12T06:05:40.624Z; saved verbatim (harness indent removed).

---

**Approve with changes (issue #23 design, r3).** Confirmed design SHA `ccddc515…` against source `7a87eb8`. All five of my r2 findings are resolved at design level:

| R2 finding | Resolution |
|---|---|
| P1 cycle cost | Carried-forward measurements and unknown final crashed-cycle cost remove the impossible write-ahead requirement ([DESIGN:75](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:75)). |
| P2 refusal path | Only the unwritten suffix is appended; failures report the durable prefix ([DESIGN:43](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:43)). |
| P2 deferrals | Settlement and test 10 now cover the first boundary at/after due across an unaligned resume ([DESIGN:50](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:50), [:197](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:197)). |
| P2 static/checkpoint overlap | Exceptions are explicit and included in measurement ([DESIGN:60](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:60)). |
| P3 counter/comparison rules | Later rows repeat the counter; test 14 excludes timing, chains and offsets ([DESIGN:122](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:122), [:205](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:205)). |

Three bounded corrections remain in the additional section 11 edits:

- **P2 — Contradictory `N` inheritance.** [DESIGN:101–106](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:101) first selects the newest checkpoint/header policy, then says `N` comes only from the flag or checkpoint. Specify **explicit flags → newest recovered clock policy**, then validate the resulting inputs together. Current `console.py:5148` selects `N` before replay and `:5205–5206` reinstates it afterward. Add a fallback test proving newer header values survive.

- **P2 — Ring-cache lifetime must be independent of handles.** [DESIGN:244](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:244) associates opening handles with boot/repair, but handles open **every cycle** (`console.py:3100–3102`, `:4232–4243`) and close afterward (`:3181–3183`). Specify a persistent `Window` cache, retaining secure per-cycle opens, with scans initially, after repair, on directory-identity changes and every `N` ticks. Test ordinary cycles without rescanning and directory replacement.

- **P3 — No state directory does not necessarily mean no journal.** [DESIGN:155](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:155) overlooks independent `--journal` support (`console.py:2802–2804`, `:5503`). The rebase should record its event there when configured, with stderr as the no-journal fallback.

Exit 4 for the backstop and the per-slug rebase are buildable. The three header propagation sites match the source (`console.py:2093–2097`, `:2453–2457`, `:3476–3483`). With these corrections, I see no remaining architectural blocker in this targeted scope.

Static inspection only; no tests, repository tools or file changes.
