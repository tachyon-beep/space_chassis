# Vehicle — open items, risks and next steps

As of **2026-10-10**, `tachyon-beep/space_vehicle` main @ `64fc58c`. GitHub issues are the delivery
status of record; this is the line's working view. **Verify against the issues before trusting it.**

## In flight

| item | state | next |
|---|---|---|
| #21 WP08.3 resume | branch `codex/wp08-resume` @ `06f08a3` + fix round of 18 findings (`records/2026-10-10-wp08-3-review-fixes.md`) with the implementer | confirm review → gate both lanes → PR → CI → merge → post merge SHA on chassis filigree `space_chassis-93010ff54e` (unblocks chassis Phase B) |

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
| **Agents can read `/opt/vehicle`** (fault policies, failure chains, `console.py --plan` prints the fault schedule; default scenario/seed guessable) | **P1** | chassis (image topology; John's call) | `../chassis/open.md`; recommended: separate agent and vehicle images |
| `HELP.md` verb texts still carry designers' commentary | medium | vehicle | #35 |
| Every vehicle bump forces a new world (engine hash covers the corpus and the engine tools) | known | operator procedure | `interface.md`; `--new-world` (#28) makes it recorded |
| Process-level restart ≈ 5.5 s, dominated by YAML loading | low | vehicle | not yet an issue; matters with the clock (#23) |
| Load-sensitive tests flake on a busy host (encoder cost ratio; the interrupt test aborting xdist) | medium | vehicle | in #21's fix round |
| Two sessions driving one package collide | process | both lines | `practice.md` "One owner per branch"; close duplicate resumes |
| Usage limits cut agents off mid-task | process | vehicle | `practice.md`; resume the same agent |
| Physical evidence for M2 may be unavailable | programme | vehicle → John | `ROADMAP.md` risks: missing values stay unset; operator decides scope |

## Owner questions pending

None open as of this snapshot. The `/opt/vehicle` exposure fix (image topology) is John's decision,
raised by the chassis line.
