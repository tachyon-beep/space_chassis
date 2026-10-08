# SV-028: second design correction required

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
