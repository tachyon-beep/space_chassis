# SV-028 Astra design correction 1 review

**Decision: changes needed; one further design-only correction before implementation.** The activation and recovery architecture is substantially corrected. Three remaining archive-transaction defects prevent accepting the complete design. These are engineering corrections within the authorized W1 package, not new user-policy decisions.

Reviewed immutable head `d47b5c19fc5a0cbdf7221c45d7b8361982734508`, tree `a6ac90064f8bc125af2122d31eb6d37330203141`, against initial design `1058c5475db656b10e0ec14bd47dae1cfc9c190b` and review-archive base `e2a1ddae362b1a931673dd074ef94ea6b978dbc2`. References below are to this head's `docs/planning-context/sv028/DESIGN.md`, unless another path is named. This was static review of immutable design/runtime objects and canonical source text. No tests, project imports, provider calls, runtime edits, workers, or real-session operations were performed. The report is the only new review deliverable.

## Prior findings and corrected architecture

| Finding | Assessment of corrected design |
|---|---|
| SV028-01, activation durability before deletion | **Addressed at design level.** B3, lines 373–378, establishes every segment containing the inherited owned prefix and the ledger namespace before B4. It runs even when no new frame is written. The explicit second-death trace and B3 EIO test address the original failure. |
| SV028-02, frozen plan and interrupted recovery | **Addressed at design level.** Sections 5 and 9 derive Π from the witnessed head before applying owned records, retain the failed-unknown spend, fix epoch to the original `e+1`, and freeze the intent anchor. The four-key preserving context binds its evidence to the receipt and reconstructible head. Carrier-free recovery requires the complete exact Π+T and an absent conversation; it cannot invent missing activation permission. T follows Π, and a further own tear under the same intent creates no second T. |
| SV028-03, preservation envelope | **Partially addressed.** The admitted namespace now includes unknown regular files, corrupt entries, ordinary temporary leftovers, and the named HANDOFF file; unsupported shapes refuse. The immutable sealed-set rule and independent inode checks are appropriate. Retry snapshot/ownership and archive durability remain open below. |
| SV028-04, capacity and serialization | **Partially addressed.** Own unfinished usage and copy scratch are counted, exact serialization is preflighted, the neutral suffix uses a fixed-size digest, and epoch/sequence domains are explicit. The equal-MANIFEST case still violates its stated byte peak. The one-file peak-RSS claim has correctly been removed. |
| SV028-05, registry and finite evidence | **Registry addressed.** One complete six-pair registry with mechanism subsets, and the narrowly reviewed old capability-pin update, is truthful. The state normalization, pending-note/no-opening control, older-known-prev behavior, and production-layout helper are corrected. The namespace model needs the concrete reused-entry discriminator below. |

The intended `EXTERNAL_DELETE` binding, same lineage, one proved epoch increment, carried pending notes, A12 resume order, and unchanged recap handling remain supportable engineering. `_retained_prev` is now described correctly: an older known checkpoint in `.prev.json` can remain named and permit collection at the first post-activation checkpoint. No new notice, H/T/Q/pump decision, broader acknowledgement reason, or permission to act on a real user session is implied.

## Blocking residual findings

### SV028-06 — P1: an inherited archive entry can be sealed without its leaf-directory fence

**Locations:** DESIGN lines 275–276, 321–332, 525–534, 563–564. Canonical SV-015 v2 §1.1 distinguishes readable bytes from data and name durability; M-2 permits loss of unfenced names.

A2 re-fences created directory names by syncing their **parents**. A3 only calls `write_bytes_durable` for destinations not already present and verified. Neither step necessarily syncs an existing leaf directory's entries when A3 reuses a readable file. Fsyncing the parent of `<partial>/session/ledger` does not establish a newly renamed file *inside* that ledger directory. Writing MANIFEST and syncing the set root, then syncing `preserved/` for the final directory rename, does not supply that missing leaf fence either.

**Concrete trace:**

1. P1 copies an admitted segment to `<ack>.partial/session/ledger/S`. The temp's file fsync and rename to S return; P1 dies before `sync_dir(<partial>/session/ledger)` returns.
2. P2 sees readable, hash-equal S and keeps it under §7.2/A3. All other files in that leaf are already copied, so no later A3 write incidentally fences it. A2 only establishes directory names in their parents.
3. P2 writes MANIFEST, seals the set, publishes the carrier, and completes activation and live-conversation deletion. It dies, followed by honest host loss.
4. The sealed archive's directory name survives but its S entry may disappear. Preservation is broken. If the carrier remains, the next start refuses the missing entry; if it was retired, ordinary startup need not inspect the archive. Neither outcome recovers the promised independent copy.

**Required correction:** before sealing or publishing authority, explicitly establish all file-data/name dependencies of reused copies as well as newly written ones. At minimum, a reused entry created by the known fsync-before-rename protocol still needs its containing directory fenced; state precisely how file-data durability is proven or re-established. Include all leaf directories containing kept entries. Verification is not a substitute for a returned dependency fence. Keep the seal immutable once published.

**Discriminating bounded fixture:** cut P1 after a copy rename and before its leaf fence; P2 must take the verified-destination reuse branch, finish sealing/activation, then die; apply carried M-2 loss and assert every independently inventoried archive entry still exists with exact bytes before ordinary convergence. Use a leaf with no later new copy that accidentally supplies the fence. Include a mutation that omits the reuse fence and requires this assertion to fail, and an EIO control showing that failed pre-seal dependency establishment cannot publish a carrier or delete the live conversation.

**Model requirement:** PreserveOps must retain pending file-name durability across process restarts **and across the `.partial` → sealed directory rename**. A pending entry recorded only by its old textual pathname must not become invisible to host-loss processing when an ancestor is renamed and fenced. Track directory identity or explicitly rebase pending descendant paths. Demonstrate the missing entry under the mutation after the final ancestor rename is durable. N6's single-cut sweep and N7's `archive-directory-unfenced/manifest-write` parameter do not explicitly specify this two-process reused-file transition; add the exact case rather than assuming those cover it.

### SV028-07 — P2: an equal MANIFEST is charged as reused but unconditionally rewritten

**Locations:** DESIGN lines 296–306, 331, 451, 572.

Section 7.4 sets `M=0` when an equal MANIFEST already exists. A4 nevertheless unconditionally calls `write_bytes_durable(MANIFEST)`. That helper, `services/chassis_persistence.py:975–984`, allocates and writes a new temp while the existing target still exists. The old MANIFEST plus the full new temp coexist before rename.

**Concrete trace:** P1 finishes MANIFEST but dies before sealing, or an unfenced seal rename reverts to `.partial`. P2 finds every destination and the equal MANIFEST present: D=0, N=0, M=0. Set the injected byte cap to the measured U. Admission passes at exact equality, yet A4 holds `U + len(MANIFEST)` bytes before rename. This contradicts the claimed actual-peak bound. Repeated copy-temp tests and the mismatching-destination rewrite case do not distinguish it.

**Required correction:** choose a consistent retry rule. Prefer reusing the verified equal manifest and explicitly establishing its dependencies, or budget the replacement temp's full bytes and file count. If the manifest becomes the durable inventory described in SV028-08, incorporate that lifecycle instead. Make file-count accounting use the actual allocation delta too: unconditional `+1` is not exact reuse accounting. Update the equality claim and preserve refusal-before-mutation when capacity is insufficient.

**Discriminating bounded fixture:** leave a complete equal manifest in `.partial`, inject cap=U, and observe filesystem usage at each allocation/write. A true reuse path must converge without an additional MANIFEST temp; a rewrite policy must reject at that cap and accept only at its accurately computed peak. Include a before/after directory-rename crash retry, since that is an ordinary source of this state.

### SV028-08 — P2: “first admission” inventory and pre-existing scratch ownership are not durably established

**Locations:** DESIGN lines 253–262, 275–276, 319–331, 535, 572.

The preservation promise is the copied domain **at first admission**, but its inventory is only in memory until MANIFEST is written last. Retry recomputes the inventory and deletes a destination whose bytes differ. M-5 single writer does not make bytes immutable under M-3, and the stop witness does not bind every admitted unknown file or corrupt entry.

**Concrete trace:** first admission hashes `agent-notes.txt = X`; A3 creates a durable independent copy X; the process dies before MANIFEST. The live file subsequently changes to Y through detectable corruption, while STOPPED and the witnessed ledger remain unchanged. Retry hashes Y as a fresh inventory, classifies archived X as mismatching scratch, deletes it, and seals Y. The only surviving original bytes X were discarded, despite the declared first-admission preservation contract. The second read within one invocation detects only changes relative to that invocation's inventory; it does not solve this cross-restart case.

**Required correction:** define a durable snapshot boundary and bind the exact intended inventory before a retry may discard or replace previously copied evidence. A bounded, checksummed inventory established before copying is one straightforward engineering direction; its publication, validity/refusal rules, capacity, and crash cuts must be specified. An in-memory admission that dies before any durable inventory cannot be treated as an enduring snapshot authority. After that boundary, changed source bytes or mismatching inventory must fail closed without deleting the only preserved original. Do not silently switch to a newer snapshot under the same acknowledgement identity. Owned partial-write temps can still be cleaned when ownership and their lack of unique pre-resolution evidence are established.

The companion ownership issue is the blanket exclusion of every `session/.ACKNOWLEDGED.<16hex>.tmp` (lines 257, 262). The basename proves a syntactic resemblance to an acknowledgement temp, not that this transaction created it. Such a file may predate first admission; it is admitted without even a carrier/content/transaction binding. “Never deleted” is narrower than the independent snapshot contract used for other unknown and temp files. Preserve pre-existing unproven temp-shaped files in the durable inventory, or refuse them, or give an explicit verifiable ownership rule. New artifacts demonstrably created by this transaction may be separately excluded. The independent test inventory must not merely repeat the same unproved filename exclusion.

**Discriminating bounded fixtures:** interrupt after an independently copied ordinary unknown file but before completion; change only its live bytes and retry. Assert refusal/preservation of X under the chosen durable inventory rule, with no permission, activation or deletion. Include changed/missing/corrupt inventory cases. Plant a pre-existing valid-temp-shaped ACKNOWLEDGED filename containing distinct bytes and prove that it is independently preserved or refused unchanged. Retain a separate successful cleanup case for a temp known to have been created by this transaction, so correction does not ban bounded scratch cleanup wholesale.

## Test plan and launch gate

The exact current proposal is **36 new + 50 retained = 86 selected cases in nine final commands**, plus four pre-fix commands. I checked the declared command arithmetic: `[14,1,1,9,10,1,35,1,14]`. These are proposed cases, not executed results. The selected retained groups sensibly cover prior acknowledgement refusals, receipt/intent retirement, recovery authority, notes, GC and startup rotation; no broad new regression sweep is requested.

Revise the finite matrix for the three traces above, and then recount the exact commands. Retain N7's activation-readable second-death case, N8's failed-unknown spend/torn-context cases, N14's pre-unlink EIO, truthful registry checks, older-known-prev actual collection, and the CLI first-request barrier. For the archive model, make the reused-leaf and ancestor-rename negative control explicit. Narrow fixtures and injected small caps suffice; preserve the existing runner/resource limits and serial execution.

The revised serialization/domain checks, fixed-size suffix commitment and explicit unproved aggregate RSS/read costs are appropriate. They do not establish kernel power-loss behavior, replay numeric bounds, arbitrary corruption recovery, a real-session operating permission, or other held policy. Source semantics do not require a new owner choice for these remaining archive corrections. Implementation should remain held until the revised transaction, ownership/snapshot boundary, capacity equation and discriminating cuts agree in one design.
