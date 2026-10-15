# Vehicle — open items, risks and next steps

As of **2026-10-10**, `tachyon-beep/space_vehicle` main @ `64fc58c`. GitHub issues are the delivery
status of record; this is the line's working view. **Verify against the issues before trusting it.**

## In flight

| item | state | next |
|---|---|---|
| #21 WP08.3 resume | **merged** 2026-10-10: PR #41, `f44399645fb2633e695a5d758cb5a41f43fb848c` (tree = tested `45f4267`); hosted CI green; SHA posted on `space_chassis-93010ff54e` comment 41 | chassis Phase B (adoption) |
| #39 claim race / chassis contract-probe failure | **John 2026-10-11: tier 1 approved** (quiet cycles write nothing), option B next, no tier 2; threat model not adversarial (`decisions.md`). Tier 1 drafted on branch `codex/39-quiet-skip` from `f443996` (worktree `$SP/t1-39-ca87a9`, uncommitted); candidate-0 (`0973b949…`) Codex: approve with changes; **candidate-1** diff sha256 `cb40feac…ffa4` (`t1-candidate-1.diff`): ruff check clean, **Codex: approve** (reviews in `.scratch/wp01-handoff/diag-contract-probe/reviews/t1-*`); contract/brief/fixture proposal for the chassis drafted (`t1-contract-proposal.md`, sent after gates) | **Shared test slot RELEASED by the vehicle 20:11 AEDT** (granted by John 19:10; bounded run passed; full gate at `7ac9791`: 542 passed, 0 skipped, both lanes; evidence `.scratch/wp01-handoff/diag-contract-probe/t1-evidence/`). Was: (1) bounded selection: the 3 new tests on candidate-0 and the 2 regression tests on `f443996` (must fail), plus the claim/resume tests, 3.12, `-n 2`, `nice -n 19`, ~5 min; (2) later, the full two-lane gate (539 tests; at 2 workers ~50 min on 3.12, ~35 min on 3.13, serially). Then candidate commit → chassis q1–q3 re-run under its cap → push/PR/CI/merge under the authority then given; contract §2.2 sentence and `brief/PROTOCOL.md:51-53` qualifier to the chassis after review |

## Next by dependency (WP08, M1)

| child | issue | depends on | note |
|---|---|---|---|
| 5 clock seam | #23 | — | `m`, `k`, `N` required flags, fixed-rate scheduler; retires `--poll` (a chassis delta) |
| 7 budget on mission clock | #25 | 1, 3 | closes the "budget wall clock resets at restart" residual |
| 8 overload shed/dilate/hold | #26 | 5, 6 | |
| 9 pause | #27 | 5 | control mechanism to be named with the chassis |
| 10 downtime, graceful SIGTERM, `--new-world`, retention | #28 | 3, 5 | gives the operator a recorded new-world path; graceful stop |
| 11 phase from tick | #29 | — (3 for restart) | |
| 12 MET result stamps, idempotent re-publication | #30 | 4 | makes re-publication an exact-name lookup |

Then M2 (WP02, WP03 evidence — not started), M3 (WP04–WP07, WP09–WP11), M4 (WP12), M5 (WP13). The
first integrated run at `m = 1` with ten windows is feasible since WP08.6 (#24).

## Open issues outside WP08

| issue | state | owner of the next move |
|---|---|---|
| **#39 the claim erases a batch written between its read and its rewrite** (silent command loss; on `main` and the chassis's `dd79e76`) | filed 2026-10-10 with a probe; fix directions: take by exchange (`renameat2`) or by rename and re-create without clobbering | vehicle (leads; a contract sentence, if one is needed, is the vehicle's to write and the chassis's to adopt) — next after #21 |
| #40 #21 review residuals (torn-marker authenticity; repeated cut markers on a maximum-length row) | P3, inside the trust model / power-loss-grade | vehicle |
| #35 sweep agent-facing text (HELP.md verb texts first) | deferred to the end-of-work sweep by John; clean as we go | vehicle |
| #16 standalone linter depends on chassis files | stays open until the chassis adopts and moves its reconciliation pins | chassis adoption, then vehicle closes |
| #15 activate and enforce the development gate (branch protection) | a repository settings change | **John** |

## Risks

| risk | severity | owner | note |
|---|---|---|---|
| **Agents could read `/opt/vehicle`** (fault policies, failure chains, `console.py --plan` prints the fault schedule; default scenario/seed guessable) | P1 → **image half closed** 2026-10-10 | chassis | John chose separate images; plan 8 (`d7a1172`..`e3eff27`). The window half (scenario/seed in windows at the pinned `dd79e76`) closes at the chassis's adoption; `../chassis/open.md` |
| **Silent command loss in the claim** (a batch replaced between the claim's read and its rewrite gets no result) | **P2**, rare (≈ 2 × 10⁻⁵ per submission at a 5 s poll) | vehicle | #39; pre-existing in every vehicle the chassis has run |
| `HELP.md` verb texts still carry designers' commentary | medium | vehicle | #35 |
| Every vehicle bump forces a new world (engine hash covers the corpus and the engine tools) | known | operator procedure | `interface.md`; `--new-world` (#28) makes it recorded |
| Process-level restart ≈ 5.5 s, dominated by YAML loading | low | vehicle | not yet an issue; matters with the clock (#23) |
| Load-sensitive tests flake on a busy host (encoder cost ratio; the interrupt test aborting xdist) | medium → fixed on the #21 branch | vehicle | F6 (subprocess and a real SIGINT), F7 (interleaved best-of-20); closes at #21's merge |
| Two sessions driving one package collide | process | both lines | `practice.md` "One owner per branch"; close duplicate resumes |
| Usage limits cut agents off mid-task | process | vehicle | `practice.md`; resume the same agent |
| Physical evidence for M2 may be unavailable | programme | vehicle → John | `ROADMAP.md` risks: missing values stay unset; operator decides scope |

## Owner questions pending

None open as of this snapshot. (The `/opt/vehicle` exposure was answered 2026-10-10: separate images.)
