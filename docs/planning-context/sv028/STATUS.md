# SV-028 governing implementation authority

Astra accepted the architecture at `8e30cf865764f565ba4bf255a9b92f8492cdcf18`, subject to **L1–L7 in [ASTRA-DESIGN-ACCEPTANCE.md](ASTRA-DESIGN-ACCEPTANCE.md)**. Those exact qualifications supersede contradictory historical design/status text. This is bounded implementation authority only; runtime acceptance is pending.

Required: establish inherited inventory before archive mutation; bind Phase B to carrier and preserved STOPPED; report actual completed prefixes after late failure; check capacity on every lifecycle branch and distinguish max(U,F) from post-cleanup F; restore finite prior assertions with source-missing precedence; model ancestor rename reversal correctly; remove permanent-refusal and guaranteed-marker claims.

The frozen launch matrix is **58 new + 50 retained = 108 cases in ten final commands**, plus four pre-fix commands. F7 adds the five exact L1/L3 cases. No broad suite, raised resource cap, provider, real-session operation or owner-policy change. Opus implements; independent immutable Astra implementation review follows.

---

# SV-028 status: implemented and tested; awaiting the coordinator's commit and an independent immutable Astra review. Not accepted.

**Result:** 108/108 selected cases passed in the ten frozen final batches `[14, 1, 1, 9, 10, 1, 22, 35, 1, 14]` (58 new, 50 retained).
- **Pre-fix:** B0 passed; D1, D2 and D3 failed at their predicted behaviour assertions on the unchanged runtime.
- **One fixture-only failure:** the first F7 attempt failed on the `N19[sealed-after-rename-fence]` cut predicate, which also matched `E`'s read of the planted pre-existing `.ACKNOWLEDGED.*.tmp` copy. The predicate was narrowed and F7 was rerun: 22 passed.
- **Files changed:** `services/chassis_startup.py`, `services/chassis.py` (CLI `home_dir`), new `tests/test_chassis_bootstrap_preserving.py`, and the reviewed `SUPPORTED` tuple in `tests/test_chassis_acknowledgements.py`.
- **Details:** commands, mutation outcomes and limits are in [RECEIPT.md](RECEIPT.md).

## Governing implementation qualifications (ASTRA-DESIGN-ACCEPTANCE.md, SHA-256 `5228c567…4171f`, recorded as supplied)

The architecture was accepted at design head `8e30cf86`, subject to mandatory L1–L7. These supersede conflicting prose in DESIGN.md and the history below.

| Id | Qualification |
|---|---|
| **L1** | A post-boundary retry must re-establish the readable inherited MANIFEST's dependencies explicitly, **before** any cleanup, child `mkdir` or copy: `fsync(MANIFEST)`, then `fsync` of the partial set, `preserved/` and `session/`. The inventory is never rewritten. A failure takes the Phase A persistence boundary |
| **L2** | Phase B validates its binding against the carrier and witness plus the **preserved** `session/STOPPED` entry (size/hash, membership, parsed reason/witness, recomputed `stop_sha256`, `stop_id`, `ack_id`). Live STOPPED is never required or recreated. The carrier-free route stays self-contained |
| **L3** | Failure statements describe the actual completed prefix:<br>• a pure admission refusal changes nothing;<br>• a later refusal (e.g. a mid-copy source change) leaves the inventory and earlier copies in place;<br>• a persistence failure propagates, the marker is attempted best-effort, and no further transaction step runs, though earlier renames and unlinks stay visible;<br>• a pre-seal `E` failure never publishes a carrier or removes STOPPED;<br>• Phase A never removes the live conversation |
| **L4** | P12/P13 capacity admission runs on **every** lifecycle branch (none, pre-boundary, post-boundary, sealed) before any cleanup, fsync, allocation or publication. `F = U − D + A`; the invocation peak is `max(U, F)`; verified cleanup may reduce pre-existing over-cap usage, after which allocation is admitted only if `F ≤ cap` |
| **L5** | The finite fixtures are the immutable baseline (`SV-028-prior-assertion-baseline.md`), overridden by correction 2 and L1–L7. Diagnostic precedence: a missing inventoried source gives `preserved_source_missing`; an added path gives `preserved_domain_changed` |
| **L6** | The `PreserveOps` model re-resolves directory identities after every undo; it never resurrects descendants of a removed, unfenced directory. The omitted-fence mutation must lose the reused entry under the **sealed** name |
| **L7** | Wording: after a source mismatch, the acknowledgement "cannot complete while the fixed-inventory checks fail" (not "never"); the marker is best-effort; the Phase A steps are A1–A8 plus the L1 fence |

## Frozen implementation matrix (from `sv016-context/SV-028-bounded-targets.json`; frozen before any run)

- **Pre-fix, on the unchanged runtime, one node per command:**
  - B0 = `tests/test_chassis_recovery_live.py::test_c_k3_a12_a_deleted_list_is_a_clean_slate_with_everything_kept` (expected: pass);
  - D1 = `…bootstrap_preserving.py::test_sv028_bootstrap_preserving_starts_exactly_one_new_epoch[run-end]` (expected: fails at the acceptance call, `LedgerError … not implemented`);
  - D2 = `…::test_sv028_every_envelope_refusal_names_its_reason_and_changes_nothing` (expected: fails at its first reason-token match);
  - D3 = `…::test_sv028_cli_bootstrap_preserving_behind_the_first_request_barrier` (expected: fails at `returncode == 0`, base exits 2).
- **Final:** ten serial commands of sizes `[14, 1, 1, 9, 10, 1, 22, 35, 1, 14]` = **108 cases** (58 new in `tests/test_chassis_bootstrap_preserving.py`, 50 retained), using exactly the manifest's literal node ids.
- **The only existing-test edit:** the `SUPPORTED` tuple in `tests/test_chassis_acknowledgements.py:56–62`.

---

# SV-028 status (history): correction round 2 complete, awaiting independent Astra re-review. Not implemented. Not accepted.

- **Base:** `05cc4f8616c108855246c8c8ea13a571eb9731c8`.
- **Governing residual review:** [ASTRA-DESIGN-CORRECTION-1-REVIEW.md](ASTRA-DESIGN-CORRECTION-1-REVIEW.md). Its SHA-256 is recorded as supplied (`64d8377115b5eb71d12249c9182470d9ad9858d3413880cdde2e6b74acfa5a14`) and not recomputed: hashing is outside Read/Grep/Write/Edit.
- **Both archived reviews are unchanged.** All earlier STATUS history is kept below.
- **Files written:** `DESIGN.md` (standalone rewrite) and this file. No runtime, test, source, literal or oracle file was touched.

### Session provenance

The first round-2 session was interrupted after writing DESIGN.md and before updating STATUS.md. The coordinator verified that launcher 1425383, process 1425390 and its scope are dead, and that no completion receipt exists.

This resumed session:
- inspected the surviving DESIGN.md by Grep;
- confirmed the round-2 rewrite and all follow-up edits were present: step renumbering A7/A8, the A4 refusal wording, and the corrected N19 boundary companions with the stale contradictory sentence absent;
- left DESIGN.md unchanged;
- wrote only this section.

### Finding → resolution map

| Finding | Resolution (DESIGN section) | Discriminators (§14.3) |
|---|---|---|
| **SV028-06** reused copy sealed without its leaf-directory fence | **Data durability.** A final destination name exists only after `write_bytes_durable`'s file fsync returned. Hash verification gives integrity, not durability (§7.4).<br>**Dependency step `E`.** It fsyncs every set file, then every fixed directory leaves-first (`session/ledger`, `blobs`, `corrupt` → `session`, `home` → set root), then `preserved/`, then `session/`. It runs before every seal and again on a sealed set before each carrier publication. Every existing fixed subdirectory is re-fenced in its parent on retry (§8.2). The seal is a rename + `fsync(preserved/)`.<br>**EIO** follows v2 §1.4.9: `PersistenceFailure`, FSYNC_FAILED best-effort, exit 44. Nothing is sealed, published or deleted, and STOPPED and the live conversation are untouched.<br>**`PreserveOps`** keys pending names by directory identity, so they survive the `.partial` → sealed rename (§14.1) | **N16** ×3 `[reused-leaf-converges \| omit-reuse-fence-mutation \| eio-before-seal]`: the exact P1 → P2 → P3 trace, a single-entry corrupt leaf with no incidental write (asserted from the log), and host loss before convergence.<br>**N17**: harness control for carrying pending names across an ancestor rename |
| **SV028-07** equal MANIFEST charged as reused but rewritten | **Selected rule: verified reuse plus dependency fencing.** The MANIFEST is the inventory, written once, never rewritten (`A_M = 0` when present).<br>**Exact deltas:** `peak = U − D + A_M + ΣA_C` for files and bytes; deletions before allocations; temps are the files they become (§7.5).<br>A complete set gives `D = A = 0`, `peak = U`: accepted at `cap = U`, refused below, with no mutation | **N19** ×3 `[complete-partial-before-rename \| rename-unfenced-then-host-loss \| sealed-after-rename-fence]`: no `O_CREAT` or write under `preserved/` at `cap = U`; `U_bytes − 1` and `U_files − 1` refuse unchanged. N15 `rewrite-peak` and `repeated-copy-temp-crashes` updated to the exact formula |
| **SV028-08** inventory not durable; temp-name ownership | **Durable snapshot boundary.** A sealed, checksummed MANIFEST (inventory) is published at A2 before any subdirectory or copy (§7.2). It binds `ack_id`, `stop_sha256`, `stop_id`, `witness_check`, `lineage_id`, the pair and the entries; it is validated on every retry and in Phase B.<br>**Lifecycle:** none / pre-boundary (owned MANIFEST temps only) / post-boundary / sealed (immutable).<br>**After the boundary:** a changed, missing or added live source refuses (`preserved_source_changed` / `…_missing` / `preserved_domain_changed`). A copy X is never replaced by Y and nothing is deleted. A mismatching destination is rewritten only when its live source just verified.<br>**Ownership rule:** only `.<B>.<16 hex>.tmp` in the own partial set, for `B` an inventory destination in that directory or `MANIFEST`, and not itself a destination. Never sole evidence. Anything else refuses `preserved_scratch_unowned`.<br>**`.ACKNOWLEDGED.<16 hex>.tmp`:** the blanket exclusion is removed. A pre-existing one is ordinary inventoried evidence; carrier artifacts exist only after the seal (§7.1) | **N18** ×10 `[source-changed-after-copy \| source-missing \| domain-gained-file \| inventory-corrupt \| inventory-foreign-binding \| inventory-missing-with-copies \| corrupted-copy-with-verified-source \| pre-existing-acknowledged-temp-preserved \| owned-copy-temp-cleanup \| owned-inventory-temp-cleanup]`.<br>N3a's independent inventory now includes the planted pre-existing temp |

### Preserved directions (unchanged)

These stay as they were in round 1:
- B3 before B4 activation durability;
- the frozen plan Π and the four-key carrier-free context;
- T after Π;
- the six-pair registry and the one `SUPPORTED` edit;
- E1+S1+R1+N1 (A12 resume order: pending notes preempt bootstrap);
- older-known-prev actual collection;
- the exact serialization checks;
- the candid unproved RSS and aggregate-read limits.

The retained nodes are kept explicitly: N7 `activation-readable/after-unlink-fence`, N8 spend and torn-context cases, N14 (B3 EIO), N13 registry, N3b, N11 CLI barrier.

The only renamed parameter is N7 `archive-directory-unfenced/manifest-write` → `…/inventory-write`, because the MANIFEST is now the inventory.

### Re-frozen plan (nothing run)

- **53 new** (the 36 from round 1 plus N16 ×3, N17, N18 ×10, N19 ×3) and **50 retained**.
- **103 cases in 10 serial commands** `[14, 1, 1, 9, 10, 1, 17, 35, 1, 14]`, plus B0 and D1–D3.
- The runner and resource caps are unchanged. The only change from round 1 (86 in 9) is the new F7 command of 17 nodes.

### Remaining blockers and limits

**No design blocker is known to this worker.** Implementation stays held for independent re-review.

Stated limits (DESIGN §15):
- RSS is unproved; aggregate reads are listed;
- capacity is an admission rule over logical sizes;
- a Phase A or Phase B EIO leaves FSYNC_FAILED and a stopped session (SV023-02 class);
- [superseded by L7] after a post-boundary source change this acknowledgement cannot complete while the fixed-inventory checks fail, with its partial set kept and counted; the marker is best-effort;
- M-6 is out of model.

### Execution log

- Read, Grep and Edit only, on the known checkout paths.
- No test, Python, Bash, Git, provider, real session, credential or settings action. No denial. No parent-root search.
- Filigree not used.

---

# SV-028: second design correction required (history)

Independent Astra review of `d47b5c19fc5a0cbdf7221c45d7b8361982734508` found three remaining archive-transaction defects. [ASTRA-DESIGN-CORRECTION-1-REVIEW.md](ASTRA-DESIGN-CORRECTION-1-REVIEW.md) is the governing residual review: SV028-06 requires reused-copy dependency fences before sealing; SV028-07 requires accurate equal-manifest retry allocation accounting; SV028-08 requires a durable inventory/ownership boundary before copied evidence can be discarded on retry. Activation/recovery corrections are accepted at design level. No implementation authority yet; these are bounded engineering corrections, not new owner policy.

---

# SV-028 status

## Correction round 1: complete, awaiting independent Astra re-review. Not implemented. Not accepted.

- **Base:** `e2a1ddae362b1a931673dd074ef94ea6b978dbc2`.
- **Governing review:** [ASTRA-INITIAL-DESIGN-REVIEW.md](ASTRA-INITIAL-DESIGN-REVIEW.md), preserved unchanged. The supplied SHA-256 is `1cf32505e185e718a82b68acc32e8e7e7d4f538a37fc400beb6812b931ab7e5e`. It is recorded as supplied and not recomputed: hashing is outside the Read/Grep/Write/Edit tools of this round.
- **Files written:** `DESIGN.md` (rewritten as a standalone corrected proposal) and this file. No runtime, test, source, literal, oracle, generator or frozen-evidence file was touched.

### Finding → resolution map

| Finding | Resolution (DESIGN section) |
|---|---|
| **SV028-01** destructive completion before inherited activation durability | **New B3 "establish owned durability"** (§9.1): fsync every segment from the witnessed end's segment through the active one, then `fsync(ledger/)`. It runs on every start, including one that writes nothing (§9.2), and **before** any unlink. On failure the persistence boundary is taken and `conversation.json` is untouched.<br>B4 then unlinks and fences, or fences an absence already present. Readable, established and completed activation are kept as separate notions; linearization is the first returned fsync covering the activation.<br>Discriminators: the exact two-process trace N7[`activation-readable/after-unlink-fence`] with carried watermarks; N14 (failed pre-unlink sync, no unlink); N5 asserts the new order; N12[`no-pre-unlink-sync`] mutation control; the §10 invariant checked at every cut in N6 |
| **SV028-02** plan recomputed from a mutated replay; carrier-free intent | **Frozen plan Π** (§5.1): derived once from the witnessed head alone, before any owned record is applied. It is receipt, optional spend, then the activation; the epoch e+1 is fixed there. Owned records are validated against Π and applied once; only `Π[k:]` (+ `T`) is appended; headers are physical, not logical (§5.2).<br>**Carrier-free path:** a sealed four-key `witnessed` context `{ack_id, receipt, after_seq, evidence}`, authenticated by the receipt's evidence digest and re-derivation of Π from the immutable ledger head (§5.4, §9.3). No missing record is written without a carrier.<br>**Composition with torn-tail recovery:** `T` comes after Π, one per intent; tears under an existing intent add no record (§9.4).<br>Traces: §9.5. Tests: N8 ×5; mutation control N12[`plan-from-mutated-replay`] |
| **SV028-03** preservation promise vs closed inventory | **Exact domain** (§7.1): every regular file of `session/` (top level, `ledger/`, `blobs/`, `corrupt/`) plus the named `HANDOFF.md` (SV-013's files table), copied. `preserved/` is counted, not copied. Carrier artifacts are excluded, never deleted. Unsupported kinds, depth or names are refused before any mutation. No whole-home backup.<br>Pre-resolution evidence and owned scratch are distinguished. **Lifecycle:** unfinished `.partial` (owned scratch, cleaned and refilled), then seal by rename, then immutable sealed set: verified and re-fenced, never repaired (§7.2).<br>Tests: N3a compares an **independent** declared inventory, including an unknown name, a planted `corrupt/` overwrite destination, recap and HANDOFF, across the later ordinary replacements. Pre-command inodes are snapshotted. N12[`hardlinked-copies`] uses a real in-place segment append |
| **SV028-04** capacity and serialization | **Actual-peak admission** (§7.4): measured usage of all of `preserved/`, including own scratch, minus planned owned cleanup, plus remaining writes, plus manifest. Deletions precede allocations and copies never overwrite, so there is no double-holding. Exact-cap equality is allowed, and this is stated to be an admission rule, not a quota. `write_bytes_durable`'s own temp cleanup is reconciled.<br>**Exact preflight** of the serialized MANIFEST, carrier and maximal RECOVERING before any write, with specific refusal tokens. The suffix is represented by count and digest (§5.3, §5.5).<br>The one-file RSS claim is removed; RSS and aggregate reads are stated candidly (§15). Tests: N15 ×6 |
| **SV028-05** registry and proof plan | **One registry** with mechanism subsets; `IMPLEMENTED_RESOLUTIONS` is the true 6-pair union (§4). **One reviewed existing-test change:** the `SUPPORTED` tuple in `test_chassis_acknowledgements.py:56–62` (refused count 70 → 69). The removed in-loop refusal is replaced by N4a.<br>**Corrections:**<br>• N1 state normalization (`to_wire(next_seq=1)`), the failed-unknown outcome, and physical/protocol separation (§11);<br>• N2 "note, no opening", plus a `no-pending-note` control;<br>• the `PreserveOps` name-loss model (mkdir, `O_CREAT`, directory rename), carried across processes;<br>• N6 asserts at the cut, then after convergence;<br>• the first-checkpoint `prev=null` claim is removed (`_retained_prev` keeps an older known checkpoint), and N3b covers it with a reference-graph assertion;<br>• D1–D3 collect on the old runtime (`HomeRoot` production layout, no new keyword) |

### Engineering resolved within W1/A12

- E1+S1+R1+N1 are applied as confirmed by the review. S1 is stated precisely: pending notes preempt the bootstrap callback; with no pending note, bootstrap or the default opening runs.
- No owner gate is introduced. TC4 and every other reason stay refused.
- `HANDOFF.md` comes from the trusted home: the default is `session_dir.parent`, the chassis layout rule (`chassis.py:610–612`), and the CLI passes `chassis.home_dir` explicitly.

### Re-frozen plan (nothing run)

- **36 new nodes:** N1 ×3, N2 ×2, N3a, N3b, N4a, N4b, N5, N6 ×2, N7 ×4, N8 ×5, N9, N10, N11, N12 ×4, N13, N14, N15 ×6.
- **50 retained nodes:** R1 35 (including the edited capability pin and three added SV023-01/-02 old-pair controls), R2 1, R3 14.
- **Totals:** **86 cases in 9 commands**, plus B0 and D1–D3, under the unchanged runner and caps (DESIGN §14). Count changes from round 0 (22 + 47 = 69 in 8) are explicit in DESIGN §14.3–§14.6.

### Execution log and deviations

- Read/Grep/Write/Edit only, on the known checkout and `sv016-context` paths.
- No test, Python, Bash, Git, provider, real session, credential, raw log, original checkout, account or settings action.
- No operation was denied. The parent task root and the results directory were not searched.
- Filigree not used (its earlier read-only failure stands).

**Stopping for independent Astra re-review.** Implementation needs an accepted design and a separate reviewed prompt.

---

## Independent review: design correction required before implementation (history)

Astra reviewed immutable `1058c5475db656b10e0ec14bd47dae1cfc9c190b` and requested one design-only correction round. See [ASTRA-INITIAL-DESIGN-REVIEW.md](ASTRA-INITIAL-DESIGN-REVIEW.md), findings SV028-01–05. The W1 envelope and A12-compatible E1+S1+R1+N1 semantics are supported engineering; no new owner-policy gate is required.

Required corrections: durability of inherited activation before live-file unlink; an immutable core/epoch plan and carrier-free RECOVERING reconstruction; a complete declared preservation inventory and sealed/unsealed retry distinction; physical scratch/peak capacity and exact encoded manifest/carrier bounds; truthful capability registration and corrected finite state/namespace/crash fixtures. The original design and its proposed 69-case plan below are not implementation authority.

## Design round 0 (history; superseded by correction round 1)

- **Base inspected:** accepted commit `5c2366cef7851b39d5363bdadcce3e1c0b25711c`. SV016–SV027 are accepted in their own scopes; `sv027/ASTRA-ACCEPTANCE.md` was read and nothing in SV027 is reopened.
- **Obligation:** the deferred `bootstrap-preserving` resolution (SV021 RECEIPT l.61; SV023 STATUS item 6; SV024 RECEIPT l.139), narrowed to one admitted case.
- **Files written:** only `docs/planning-context/sv028/DESIGN.md` and this file.
- **Proposal (superseded):**
  - one pair, W1;
  - a closed canonical-name inventory copied to `preserved/<ack_id>/`, with the manifest written last;
  - receipt, spend?, then activation `EXTERNAL_DELETE{e+1, cause}`;
  - then unlink before syncing the readable own extras (the SV028-01 defect);
  - a plan derived after applying owned extras (SV028-02);
  - a separate preserving set to avoid editing the capability pin (SV028-05);
  - 22 new + 47 retained = 69 cases in 8 commands.
- **Execution:** no shell, test, Git, provider or real-session action. No denial. Filigree not used.
