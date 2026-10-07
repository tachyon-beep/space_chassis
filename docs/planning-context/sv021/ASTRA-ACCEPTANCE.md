# SV-021 Astra correction 2 review

**Accept the staged SV-021 implementation at this immutable checkpoint.** SV021-08, SV021-09 and SV021-10 are closed; the earlier seven findings remain closed. I found no further acceptance-blocking defect in the focused correction and its affected recovery paths. This accepts the isolated WIP chassis package and its stated limits, not destructive GC, main merge, deployment or live-provider operation.

Reviewed documentation head `24f452a491ed7f24837990236337698478749c5d`, runtime/tests `f3812dc9d351a231a0f0879f86c9807f0a6a6634`, against `d0430590586e8c8280fcc96b32571fb0c0ad0825`. Runtime/test bytes are identical between the runtime checkpoint and documentation head; their diff contains only five planning documents. References below identify paths and lines in the reviewed Git objects, not a moving checkout.

Review authority remains the canonical SV-013 dossier, SV-015 integrated closure v2 and its accepted independent corrections, the SV-020 foundation acceptance, and the two preceding SV-021 reviews. I inspected immutable implementation and assertion changes, checkpoint-002 and RECEIPT §7. This was static review: no tests, project imports, provider calls, runtime edits or deployment. The only output written is this report.

## Finding closure

### SV021-08 — closed: checked frozen recovery input and monotone allocation evidence

`services/chassis_startup.py:415–438`, `:468–529`, `:533–548`, `:788–839` now separate the two required obligations. RECOVERING has an exact top-level schema and a checksum covering all nine input fields. Before its fields become authority, validation checks the checksum, lineage, prefix and tail domains, reservation domain and acknowledgement binding to this tail. The prefix sequence/chain and actual original tail are then checked against the ledger or quarantined copy. An altered numeric reservation no longer overrides an intact IDENTITY file.

The validated frozen reservation drives deterministic recovery-core derivation (`:888–943`). Existing core records remain compared with that plan before only its missing suffix is appended (`:495–519`); the fix does not replace this comparison with a newly chosen live number. A valid live reservation lower than the frozen witness stops as `identity_inconsistent`. Missing, damaged or foreign live IDENTITY can be restored from the checked transaction witness. The final reservation target includes the checked live/frozen maximum and the ledger/state floor, while the write decision uses what the live file actually held. Consequently a lower cached input cannot overwrite the higher checked allocation authority.

The new assertions at `tests/test_chassis_recovery_live.py:1419–1613` distinguish the original failure: hidden turn 20, reservation 64, crash immediately after durable RECOVERING, then valid-JSON mutation 64→14. The additional parameterized cases require altered intent fields to stop without changing the tree except STOPPED, cover missing/bad-check/foreign live IDENTITY under a valid intent, reject a valid lower live value, and restart again after a second crash inside the recovery core. The completion assertions require a next turn above 64, no lowered reservation and one spend closure. These assertions exercise the transaction defect rather than merely checking that a number increased.

### SV021-09 — closed: A14 restores file authority without replacing logical memory

`services/chassis_startup.py:698–723` appends a durable `RECOVERY{conversation_restored, detail{conv_sha}}` before installing the restored file. `_binding` recognizes that latest transition (`:758–777`). The reducer validates its hash but leaves logical memory unchanged (`services/chassis_replay.py:588–592`). Thus restored checkpoint bytes B are a recognized file binding while suffix messages and the A14 notice continue to replay above B. This does not weaken the actual previous-base or intermediate-hash checks.

The A10 and external-edit variants (`tests/test_chassis_recovery_live.py:1456–1497`) restart twice without inserting a checkpoint and assert preserved messages, no spurious EXTERNAL_EDIT and stable epoch. Cuts after the notice and after the binding but before physical restore require convergence over three startups, one notice and one restoration binding (`:1640–1665`). The pre-checkpoint case binds its replay. The real-edit regression first establishes a later checkpoint binding and then writes old B back; A11 must adopt B (`:1685–1698`). This is the clarified, observable hash-authority regression. Rewriting the currently bound bytes identically remains indistinguishable; no mtime authority was introduced.

The existing O2-2 assertion changing A9 to A9t is justified: the source is now bound by the recorded restoration. Its exact-memory assertion remains intact.

### SV021-10 — closed: foreign adoption belongs to pending generations

`services/chassis_startup.py:675–691` includes the matching pending generation numbers in the same LEGACY_REIMPORT record as the imported list. The reducer marks those entries (`services/chassis_replay.py:530–540`), checkpoint validation carries the optional true-only flag (`:210–220`), and `Session.adopt_notes` consumes that per-generation fact (`services/chassis_session.py:475–496`). The volatile `Opening.foreign_texts` path is removed from both startup and the active chassis caller.

The discriminating fixture has N1 and N2 already present in the foreign list, creates equal-text generation 3 after reimport, stops before adoption, and restarts through A8t twice. It requires one N2, two N1 copies, and foreign flags only for generations 1 and 2 (`tests/test_chassis_recovery_live.py:1500–1532`). A separate fixture checkpoints before adoption and verifies that the mark survives and is consumed (`:1702` onward). This preserves original-list evidence without suppressing a later equal-text generation.

## Integrated disposition and evidence limits

These closures remove the remaining qualifications on SV021-01's repeated-TC4 identity protection, SV021-02/-04/-05's file-authority convergence, and SV021-03's migration/note closure. Correction 2 leaves the previously accepted response-owned notices, deep history copy, request/tool gates, response/request bounds and true retained-previous-base selection intact. No new H/T/Q or pump policy choice is required by these corrections.

RECEIPT §7 reports four discriminating pre-fix failures followed by 511 selected passes over nine bounded batches, including 97 recovery checks and five real script restarts. I reviewed the relevant assertions independently; I did not reproduce these runs. `git diff --check` found no whitespace errors in the immutable correction. The process-restart evidence remains distinct from power-loss or kernel/storage commissioning evidence.

Only three acknowledgement resolutions remain implemented; unsupported resolutions, including the new integrity stops, remain refused. This is safe explicit deferral for this staged activation. Destructive GC remains disabled, and exact numerical replay-work bounds and bounded total session disk remain unclaimed. These are remaining packages, not concealed achievements or blockers to the bounded SV-021 acceptance. Recorder-in-loop correlation, provider compatibility and deployed ordering are not established by this review.

## Dependencies retained for SV-022

The existing SV-022 preflight may now use this accepted checkpoint as its base, subject to its separate implementation and review boundary. Acceptance here does not activate collection.

- Protect `IDENTITY` and any pending sealed `RECOVERING` as allocation/transaction authority, not orphan blobs. Finish or refuse pending recovery before GC. Collection must not make reconstruction from deleted request records a prerequisite for label uniqueness.
- Preserve the latest file-binding suffix until a later checkpoint supersedes it. `conversation_restored.detail.conv_sha` is a file hash, not a blob reference. Its record must remain available wherever startup still needs that binding.
- Carry `notes.pending[].foreign` with its exact generation until adoption consumes it. Pending blobs remain referenced by checkpoint state even when a foreign mark avoids appending their text; collection must not discard their replay/state obligations early.
- Retain `RECOVERY{conversation_adopted}.detail.blob` and `LEGACY_IMPORT.note.blob` under the reference union already implemented by `record_refs` (`services/chassis_replay.py:610–630`).
- Follow the actual `C_n.prev` tuple, which can name an older checkpoint, and retain its full replay interval. Do not substitute the last two CHECKPOINT records. The C-G1/O2-4 transaction, partial-unlink restart path and post-collection recovery fixtures remain to be implemented and independently accepted.

No remaining SV-021 correction is requested. Keep the staging restrictions while preparing the concrete SV-022 package.
