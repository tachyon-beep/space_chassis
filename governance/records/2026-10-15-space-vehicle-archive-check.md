# space_vehicle archive check (D21), 2026-10-15

Question: is everything on `tachyon-beep/space_vehicle` durable on the `space_chassis` remote, so that
John can archive it? Answer: **yes**. Every ref's tip commit is on the `space_chassis` origin, and its
25 open issues are recreated here as #10 to #34. Nothing was pushed to, closed on or changed on
`space_vehicle`. Archiving is GitHub's read-only mode: it deletes nothing and can be undone.

## 1. Refs

Taken from a full mirror clone of `space_vehicle` at 06:00Z: 12 branches, 0 tags, 0 releases, no
wiki, and 12 pull-request heads (`refs/pull/*/head`).

**Method: exact commit reachability.** The absorb kept the original commits (the subtree merge moved
them under `vehicle/` in the merge, not by rewriting them), so no patch-id or tree comparison was
needed. Each tip was fetched into a chassis clone and checked with
`git merge-base --is-ancestor <tip> origin/<branch>` against `space_chassis` origin as fetched at
06:00Z (main at `e9cc63a`).

| space_vehicle ref | tip | on space_chassis main | also on |
|---|---|---|---|
| `main` | `f75420c` | yes | absorbed tip, per `CLAUDE.md` |
| `codex/39-quiet-skip` | `7ac9791` | yes | `wip/vehicle-39-quiet-skip` |
| `codex/ci-referee-timeout` | `b3c328d` | yes | `wip/vehicle-ci-referee-timeout` |
| `codex/diag-ingress-trace` | `1caab23` | **no** | `wip/vehicle-diag-ingress-trace` (tip equal) |
| `codex/vehicle-delivery-scaffold` | `d4f7d04` | yes | `wip/vehicle-vehicle-delivery-scaffold` |
| `codex/window-record-no-seed` | `e756ceb` | yes | `wip/vehicle-window-record-no-seed` |
| `codex/wp01-on-issue16` | `bdfaf8b` | yes | `wip/vehicle-wp01-on-issue16` |
| `codex/wp08-checkpoint-format` | `25fffb5` | yes | `wip/vehicle-wp08-checkpoint-format` |
| `codex/wp08-design` | `47856fa` | yes | `wip/vehicle-wp08-design` |
| `codex/wp08-encoder` | `b1feb0e` | yes | `wip/vehicle-wp08-encoder` |
| `codex/wp08-resume` | `45f4267` | yes | `wip/vehicle-wp08-resume` |
| `codex/wp08-state-dir` | `770159e` | yes | `wip/vehicle-wp08-state-dir` |

Pull-request heads: #14 `d4f7d04`, #17 `bdfaf8b`, #18 `47856fa`, #31 `b1feb0e`, #32 `25fffb5`,
#33 `770159e`, #34 `b3c328d`, #36 `e756ceb`, #37 `eb0b019`, #38 `1fec426`, #41 `45f4267`,
#43 `7ac9791`. All twelve are ancestors of chassis main.

The one ref that is not on main is `codex/diag-ingress-trace`: one commit on `8c6f71d` (an env-gated
ingress trace, labelled "diagnostic, not for merge"). Its only home here is
`wip/vehicle-diag-ingress-trace`, so that branch must not be deleted while the commit matters. The
same holds for the six local-only vehicle branches the nyx session pushed under D18
(`governance/records/2026-10-15-wip-branch-inventory.md`); they were never on `space_vehicle`.

Issue #35 names a branch `codex/window-readme-no-commentary`. It is not on `space_vehicle`'s origin
today, so there is nothing to carry.

## 2. Issues

31 issues: 25 open, 6 closed. Each open issue is recreated on `space_chassis` with a `[space_vehicle#N]`
title prefix, the original body, and a header linking back. Issue and PR numbers inside the bodies
are rewritten as `tachyon-beep/space_vehicle#N` so they do not point at unrelated chassis numbers.
Comments are not copied (four issues have one each); they stay readable on the archived originals.

| space_vehicle | space_chassis | title |
|---|---|---|
| #2 | #10 | WP02: Resolve electrical, thermal and consumable evidence blockers |
| #3 | #11 | WP03: Resolve flight, propulsion and RCS effectivity and inputs |
| #4 | #12 | WP04: Implement electrical solve and source/load coupling |
| #5 | #13 | WP05: Implement transitions, dwell, protection and FDIR |
| #6 | #14 | WP06: Implement thermal, cabin, consumable and propulsion-feed rules |
| #7 | #15 | WP07: Implement orbit, attitude, navigation and propulsion dynamics |
| #8 | #16 | WP08: Define and implement mission clock, persistence and restart continuity |
| #9 | #17 | WP09: Execute faults and instrument measured evidence |
| #10 | #18 | WP10: Implement non-vacuous conservation and cycle accounting |
| #11 | #19 | WP11: Close executable coverage and complete-vehicle gate |
| #12 | #20 | WP12: Accept full mission, scenarios, deterministic replay and performance |
| #13 | #21 | WP13: Publish accepted release evidence and hand off exact chassis adoption |
| #15 | #22 | Activate and enforce the vehicle development gate (hosted CI blocked) |
| #16 | #23 | Standalone linter depends on chassis files through ancestor and cwd lookup |
| #23 | #24 | WP08.5: The clock seam |
| #25 | #25 | WP08.7: The command budget on the mission clock |
| #26 | #26 | WP08.8: Overload: shed, dilate, stop |
| #27 | #27 | WP08.9: Pause and resume control |
| #28 | #28 | WP08.10: Downtime, graceful stop, the discontinuity record and --new-world |
| #29 | #29 | WP08.11: The phase as a function of the tick |
| #30 | #30 | WP08.12: Result filename stamps and idempotent re-publication |
| #35 | #31 | Sweep agent-facing text for design commentary |
| #39 | #32 | The claim erases a batch written between its read and its rewrite (`bug`) |
| #40 | #33 | WP08.3 (#21) review residuals |
| #42 | #34 | After a resume with no map, every gate reopens |

#22 (from #15) and #23 (from #16) carry a note that the absorb and root CI (D6) may already have
superseded them; whoever owns the vehicle line closes them if so.

Closed issues, not recreated:

| space_vehicle | title |
|---|---|
| #1 | WP01: One authoritative executive and bounded multi-window ingress |
| #19 | WP08.1: Checkpoint format v1: writer, reader, integrity and compatibility |
| #20 | WP08.2: --state-dir: the private directory, lock, journal and root-record copy |
| #21 | WP08.3: Resume mechanics: an executive constructed from a checkpoint and record |
| #22 | WP08.4: The per-cycle durable record, published-tick mark and replay-from-record |
| #24 | WP08.6: The compare-point encoder: coverage unchanged, cost below the step |

## 3. Not covered

- Comments, pull-request conversations and Actions run history are not copied. Archiving keeps them
  readable on `space_vehicle`; they would be lost only if the repository were deleted.
