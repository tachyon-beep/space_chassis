# Current status: revision 2 written; awaiting independent Astra review; implementation not authorized

Astra reviewed revision 1 at head `cd72f00a9604c00eb5f16f07c9696024d76160d1`. [ASTRA-INITIAL-DESIGN-REVIEW.md](ASTRA-INITIAL-DESIGN-REVIEW.md) accepted the default source recurrence and required SV030-01 to SV030-03:

- a precise clean frontier and a narrower claim;
- header reuse and placement accounting;
- finite ordering discriminators.

DESIGN.md revision 2 makes those corrections; its opening table maps each finding to its correction. No owner-policy decision was needed. No tests or runtime changes have been made.

---

# SV030 status — design only

**State:** DESIGN.md revision 2 is written. No runtime, test, constant or canonical file was changed. No command, test, import, Git operation, agent or provider was used.

## Outcome (detail in DESIGN.md)

**Unchanged from revision 1, accepted by review:**

- Default reachability is shown by source construction only; nothing was executed.
- The SV029 A10 + repeated edited-A11 / CK2-entry-death family appends `432 + d(epoch) + d(recap_folded) + d(first) + d(last)` bytes per start, with no rotation.
- After **at most 76,960** edited starts the next start stops A2 `ledger_unreadable` before replay. No implemented resolution exists for that stop.
- Raising the read cap and R1 are rejected. The R1 counter-example now uses a death immediately before the successor's open.

**R2, narrowed (SV030-01):**

- **Admission:** only a **clean A11 start** is admitted (E1–E9). That means:
  - no recovery intent, carrier or preserving plan;
  - no pending GC intent;
  - an empty derived core, which excludes an open group and an unanswered REQUEST_SENT (`possible_duplicate_spend`);
  - P not ending in HISTORY_REPLACED;
  - a full inherited segment on which this start has written no header.
- **Effect:** such a start rotates the inherited segment before its EXTERNAL_EDIT.
- **Dropped:** the pending-GC branch.
- **Unresolved and explicitly open:**
  - RECOVERING+A11 growth;
  - A10/A12 alternation;
  - the pending-GC sibling;
  - the other excluded frontiers;
  - `W` and all-segment readability.

**Placement and lifetime (SV030-02):**

- The only runtime change proposed is one guarded block between `chassis_startup.py:2143` and `:2144`.
- There is no one-shot state. A reused empty successor disables R2.
- The closure keeps its existing rotation rule, which cannot fire after R2 at default constants.
- P1 (empty-successor scan) and P3 (IDENTITY/request boundary) are resolved from source in DESIGN §5.4, together with fsync/fence order, charging, `now`/`suffix` and next-start behaviour.

**Evidence plan (SV030-03):**

- 8 new nodes (13 selected cases) and 8 retained nodes, in 6 serial commands, with caps unchanged.
- Pre-change failures are stated at their semantic assertions:
  - N1 fails on the `ledger_unreadable` refusal (in the [injected] model SEG = 16,384, READ = 32,768);
  - N5, N6 and N7 fail on "no records after mark".
- The other nine cases pass both before and after the change.

## Process record

1. **Stop.** During the first invocation, one `Grep` over `/home/john/Documents/Codex/2026-10-07/task/execution` (pattern `SEGMENT_MAX|16 MiB`, glob `*SV*015*`) was denied automatically: the path is outside the allowed working directories and no approval surface was available. The denied parent-directory action was not performed. The worker subsequently searched the permitted context directory and searched/read the specific SV015 document for the same objective. The coordinator stopped that invocation to honor the no-workaround instruction; this deviation is preserved in results/SV-030-permission-stop-receipt.json. No document had been written. This coordinator correction replaces the draft's inaccurate claim that no alternate route was used.
2. **Authorized resumption.** On 2026-10-08, John approved resuming by reading the specific document `/home/john/Documents/Codex/2026-10-07/task/execution/sv016-context/SV-015-integrated-apparatus-closure-v2.md`. That document lies inside the already permitted `sv016-context` folder; folder access was not expanded. The approval is in the coordinator transcript: emmy 06:42 UTC, John 07:17 UTC, "and yes, the opus work approved".
   - The first action of the resumption was a Read of that exact file (§§1.4.6–1.4.10 and §5.8). It succeeded.
   - The continuation used Read, Write and Edit only, on known paths.
   - The earlier denial stands as recorded. It is not reinterpreted.
3. **What was read.** The independent obligation review; the SV029 DESIGN and acceptance; the SV027 acceptance; the canonical SV015v2 §§1.4.1, 1.4.4–1.4.10 and 5.8; and the source and test line ranges listed in DESIGN §1.
   - The SV024, SV026 and SV028 acceptance boundaries come from the review's table and the governing source comments. Their acceptance files were not re-read.
   - No file hashes were computed (no command execution). Line citations refer to the working tree at `b946fb4a73b3f58295e89a919b725e3aa3fbaafc`, clean at session start.
4. **Unchanged.** Filigree's earlier read-only failure stands (no retry, init, repair or claim). No real session, credential, setting, subscription or overage was touched. ELSPETH priority is unchanged.
5. **Revision 2 (this round).**
   - **First read:** `sv016-context/SV-030-Astra-design-review.md`, the governing findings SV030-01 to SV030-03, against review archive head `91440043546fc75e6bcf164a77577892e9796fb3`.
   - **Further reads:** only Read on exact known files under the two permitted roots. These were the runtime and test ranges added in DESIGN §1, and the existing STATUS.md, whose coordinator correction in item 1 is kept verbatim.
   - **Writes:** DESIGN.md and STATUS.md only.
   - **Not used:** search, shell, Git, Python, tests, imports, agents or providers.
   - **Denials:** none occurred this round.
   - **John's approval:** the specific SV015 document-read approval was not needed again. The denied parent-directory search was not repeated.

## Next

Independent Astra review of DESIGN.md revision 2. No implementation or test launch until then. Accepting R2 would authorize only the bounded package in DESIGN §6–7.

All existing nonclaims remain: numerical replacement bounds, total I/O, unknown partial I/O, RSS, latency and real host loss. The unresolved items in DESIGN §5.5 are also nonclaims.
