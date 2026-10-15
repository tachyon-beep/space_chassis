# WP08.5 #23 final design: targeted independent confirmation

Recorded 2026-10-12 by space-governance-codex from independent reviewer
`/root/review_governance`, requested directly by John in coordination thread
`01a12501-b067-7581-b5b2-3d4945441dc2`.

**ACCEPT the targeted design corrections. No remaining P1/P2 in this scope.**

Design: `/home/john/space_chassis/.scratch/wp08-23/DESIGN.md`
SHA256: `4e8d0d6aaeb83319a120586fe086cd7744f0171a9f291f6b7cdb4b2dcc2787af`,
checked before and after review. Vehicle source basis: `7a87eb8`.

| Finding | Confirmation in DESIGN.md |
|---|---|
| Systems R1 / Codex cache lifetime | Resolved, lines 248-257: persistent Window cache independent of secure per-cycle handles; scans only at boot, repair, reconciliation cadence and directory-identity changes. Test 21, line 229, includes ordinary cycles without rescanning and replaced directories. |
| Systems R2 operator visibility | Resolved, lines 265-269: fixed-format stderr backstop event in both shapes; Chassis status.py/journal.py report Vehicle restart count and event. Text explicitly denies current visibility and does not rely on transient exit-code state. |
| Systems R3 SIGTERM forwarding | Resolved, lines 261-264: per-slug trap forwards and waits; direct-exec shape requires console handler specified at line 168. |
| Codex N inheritance | Resolved, lines 102-109: explicit flags override newest recovered checkpoint/header policy after replay, then joint validation. Test 7, line 197, covers fallback with newer replayed policy. |
| Codex journal independence | Resolved, lines 159-162: rebase without a state directory writes an independently configured journal and always emits stderr. |

These are design closures, not implemented behavior. Inspected source still
opens/closes handles each cycle, reinstates preselected N after restore, and
has the old forward-only Chassis trap.

Implementation acceptance: scan counts and directory replacement; checkpoint
fallback policy inheritance and explicit overrides; signal-driven completion
through both launcher shapes; observable backstop events/restart counts;
journal/no-journal rebase behavior. Full-ring deployment measurement and
separately allocated qualification remain required.

Static design/source inspection only. No tests, product execution or source
edits were performed by the reviewer. This record grants no runtime slot.

John additionally requires delivery on main or a consolidated release branch.
Shared adoption issue space_chassis-93010ff54e comment 43 records the owner
handoff and requirement for exact integration targets, commits and gate
receipts. Owner acknowledgement and implementation/landing remain pending.
