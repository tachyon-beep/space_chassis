# Vehicle — open items, risks and next steps

As of **2026-10-10**, `tachyon-beep/space_vehicle` main @ `64fc58c`. GitHub issues are the delivery
status of record; this is the line's working view. **Verify against the issues before trusting it.**

## In flight

| item | state | next |
|---|---|---|
| #21 WP08.3 resume | branch `codex/wp08-resume` @ `f12e522` (`06f08a3` + fix rounds 1–3, `records/2026-10-10-wp08-3-review-fixes{,-2,-3}.md`; gate 515 passed both lanes); round 4 (J1–J4, `…-review-fixes-4.md`) with the implementer | confirm round 4 (stopping rule) → gate both lanes → file the residuals issue → PR → CI → merge → post merge SHA on chassis filigree `space_chassis-93010ff54e` (unblocks chassis Phase B) |

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
| #35 sweep agent-facing text (HELP.md verb texts first) | deferred to the end-of-work sweep by John; clean as we go | vehicle |
| #16 standalone linter depends on chassis files | stays open until the chassis adopts and moves its reconciliation pins | chassis adoption, then vehicle closes |
| #15 activate and enforce the development gate (branch protection) | a repository settings change | **John** |

## Risks

| risk | severity | owner | note |
|---|---|---|---|
| **Agents could read `/opt/vehicle`** (fault policies, failure chains, `console.py --plan` prints the fault schedule; default scenario/seed guessable) | P1 → **image half closed** 2026-10-10 | chassis | John chose separate images; plan 8 (`d7a1172`..`e3eff27`). The window half (scenario/seed in windows at the pinned `dd79e76`) closes at the chassis's adoption; `../chassis/open.md` |
| `HELP.md` verb texts still carry designers' commentary | medium | vehicle | #35 |
| Every vehicle bump forces a new world (engine hash covers the corpus and the engine tools) | known | operator procedure | `interface.md`; `--new-world` (#28) makes it recorded |
| Process-level restart ≈ 5.5 s, dominated by YAML loading | low | vehicle | not yet an issue; matters with the clock (#23) |
| Load-sensitive tests flake on a busy host (encoder cost ratio; the interrupt test aborting xdist) | medium → fixed on the #21 branch | vehicle | F6 (subprocess and a real SIGINT), F7 (interleaved best-of-20); closes at #21's merge |
| Two sessions driving one package collide | process | both lines | `practice.md` "One owner per branch"; close duplicate resumes |
| Usage limits cut agents off mid-task | process | vehicle | `practice.md`; resume the same agent |
| Physical evidence for M2 may be unavailable | programme | vehicle → John | `ROADMAP.md` risks: missing values stay unset; operator decides scope |

## Owner questions pending

None open as of this snapshot. (The `/opt/vehicle` exposure was answered 2026-10-10: separate images.)
