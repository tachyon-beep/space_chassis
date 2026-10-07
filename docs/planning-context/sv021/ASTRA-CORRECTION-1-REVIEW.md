# SV-021 Astra correction 1 review

**Changes needed.** The correction fixes the seven original discriminating traces, but three related restart/corruption cases still block acceptance of the integrated runtime. Keep SV-022 destructive GC inactive until these are corrected and independently reviewed.

Reviewed immutable documentation head `d0430590586e8c8280fcc96b32571fb0c0ad0825`, runtime/tests `06fbc40e4df3287f8995bb54713ce316164b29d7`, against `2717d7c5f6adc40c6326142efa9a40a62e3aeced`. References below are to those Git objects. Canonical scope remains SV-013 §2.2, SV-015 v2 §1.2–1.4/§2.3, the accepted independent corrections and the initial SV-021 review. Static review only: no tests, project imports, provider calls, moving-tree inspection, repository edits, merge or deployment. This report is the only output written.

## Remaining findings

### SV021-08 — P1: interrupted recovery replaces the checked identity reservation with an unchecked JSON number

**Location:** `services/chassis_startup.py:420–426`, `:460–467`, `:524–537`, `:845–850`; compare `services/chassis_session.py:72–90`.

The new IDENTITY file has a checksum and lineage/domain validation, but `_recover` discards that validated result whenever RECOVERING exists and uses `intent.identity_reserved` instead. RECOVERING is plain JSON with no checksum. `_from_intent` verifies its prefix anchor and tail hash, neither of which covers the copied reservation. The subsequent TC4 check rejects only `None`. A valid-JSON numeric corruption can therefore lower the allocation authority despite an intact, higher IDENTITY file.

**Concrete trace under the stated durable-corruption model:** the valid prefix ends after turn 49 with next identity `lineage:50:1`; IDENTITY durably reserves through turn 64. Request 50 is sent, the process dies before a response, and damage to that request's header makes the tail TC4. The operator acknowledges. Recovery writes RECOVERING with `identity_reserved: 64`, then dies before copying/truncating or appending outcome records. Change the first digit in that JSON value from `6` to `2` (a one-bit change); all anchor/tail fields and the checked IDENTITY value 64 remain intact. On restart `_recover` uses 24, and `derive_core` computes `max(next_turn 50, 25, last_visible_turn 49 + 1) = 50`, attempt 1. The already-used `lineage:50:1` is reissued. The final `reserve_turns(..., exact=True)` also trusts the lowered cached value and can replace the real high-water mark with 50.

**Required correction:** validate the reservation witness used during interrupted recovery, not just the ordinary IDENTITY read. It must be bound to the lineage and exact transaction with integrity protection and reconciled with the live checked reservation; a valid higher durable reservation must never be overwritten by an unchecked lower cached value. One simple design may require a matching valid live reservation while the intent is pending and fail closed otherwise; another may make the intent a properly validated independent witness. Preserve deterministic re-derivation, but do not obtain it by trusting an unprotected authority field. Verify every path that substitutes carrier data for allocation evidence.

Keep two obligations separate: **the validated high-water evidence bounds every possibly used identity**, while **the frozen transaction input reproduces the already-written recovery prefix exactly**. Bind the frozen witness to this lineage, prefix sequence/chain and original tail identity, and validate it before using it or truncating anything. If recovery records already exist, verify them against that validated frozen plan and append only its missing suffix; do not silently recompute a different `next` value, rewrite their meaning or bypass the prefix comparison. If current evidence and the frozen plan cannot be reconciled safely, stop before effects. Carry the actual validated high-water value forward monotonically when writing IDENTITY, independently of the value used to reproduce the plan. A checksum over the complete relevant intent, with explicit schema/domain checks and live-reservation reconciliation, is one concrete way to supply the missing integrity boundary; merely taking a larger number while ignoring an already-written prefix is not a transaction fix.

**Regression:** crash immediately after RECOVERING is durable, before any outcome record, then apply the valid-JSON numeric change while leaving IDENTITY valid and higher. Restart must stop before mutation/effect or allocate strictly beyond the checked reservation, never reuse the hidden request label. Also exercise missing/damaged/foreign IDENTITY with an outstanding intent and valid versus altered transaction fields, and a second crash during recovery. Existing missing/bad-check/foreign tests at `tests/test_chassis_recovery_live.py:1296` have no outstanding RECOVERING; the reservation-write crash test at `:1318` does not cover this override.

This is a remaining closure issue for SV021-01. The durable high-water-mark approach itself is appropriate; its interrupted-recovery trust path is incomplete.

### SV021-09 — P1: A14's restored checkpoint file conflicts with a later recorded binding on the next restart

**Location:** `services/chassis_startup.py:580–605`, `:611–618`, `:678–695`, `:730–747`.

A14 now correctly restores the newest checkpoint's own verified bytes and retains the previous bound file. However, it does not record that filesystem restoration as a new source-file binding. `_binding` still reports a later A10 adoption or external switch in the suffix. The next startup treats the runtime-restored checkpoint bytes as an external edit and replaces the recovered conversation with old content.

**Concrete trace:** C binds B. Append N and die after CK4 installs B+N but before CK6. A10 records `RECOVERY{conversation_adopted}` binding file B+N. Stop before another checkpoint. Damage conversation.json. A14 reconstructs B+N, appends its notice and restores the file to B, leaving the suffix binding at B+N. Stop again before another checkpoint. On the next start strict replay is B+N+notice, while the file is B and its latest binding is B+N. Neither comparison matches, so startup selects A11 and writes EXTERNAL_EDIT for B. N and the A14 notice are discarded/replaced without a user edit. The same conflict can follow an A11 source binding before A14.

**Required correction:** make A14's restore and source-file authority converge together across every cut. Preserve the distinction between the checkpoint snapshot used as a replay base and the current externally editable file binding. Record/restore that distinction durably so runtime-installed B is recognized on the next start without resetting logical memory. Do not simply accept every old checkpoint hash: an actual later user edit back to B must still be honored, as required by SV021-05. Do not weaken previous-base/intermediate-hash validation.

**Regression:** C(B) → interrupted CK4(B+N) → A10 → file damage → A14 → two further startups, with no checkpoint inserted between the startups. N and one A14 notice must survive, epoch must not advance spuriously, and no EXTERNAL_EDIT should appear. Add the external-edit-binding variant and cuts around the corrected restore/binding transaction. Then intentionally edit the file back to B after the recovery transaction and require a real A11. The new checkpoint tests immediately checkpoint after A10/A11, while the repeated-A14 test begins with an ordinary checkpoint binding; neither composes these transitions.

The original incorrect `prev` tuple/rotation trace is repaired, but the combined SV021-02/-04/-05 authority closure remains blocked by this new interaction.

### SV021-10 — P2: A8t loses the foreign-note adoption evidence after a reimport crash

**Location:** `services/chassis_startup.py:584–588` and `:519`; `services/chassis_session.py:475–493`.

The new consumed-reimport classification is A8t, but `Opening.foreign_texts` is populated only for A8. A crash between durable LEGACY_REIMPORT and `resume_session` thus loses the fact that the imported foreign list already contains a pending note.

**Concrete trace:** a checkpoint contains pending generation N. An older runtime appends prefix+N to its list and writes non-format-2 run.json. The new runtime starts A8 and durably reimports that list; kill it before note adoption. The next start correctly identifies the unchanged source as A8t, but returns empty `foreign_texts`. `adopt_notes` appends N again and advances its watermark. The list now contains two copies although the old-runtime match was available and no new generation was written.

**Required correction:** preserve the reimport's per-generation foreign-adoption facts through restart until consumed. Do not solve this with unrestricted text deduplication: a genuinely new equal-text generation written after the reimport must still be adopted. The evidence should follow the original imported list and the pending generations it covered, not merely whatever text happens to be in the current conversation.

**Regression:** extend the existing C-K6 fixture (`tests/test_chassis_recovery_live.py:594`) with a crash after `root.start()` returns A8 and before `resume(opening)`. Restart through A8t twice and require one visible N and one durable foreign-adoption transition. Include multiple pending generations and a later equal-text generation created after the reimport, which must not be suppressed. The current C-K6 test immediately resumes A8; the new A8t test checks base stability without pending notes.

## Original finding disposition and successful changes

| Initial finding | Correction assessment |
|---|---|
| SV021-01, repeated-TC4 allocation | Length-derived skip removed. New requests reserve a turn durably before REQUEST_SENT and its effect. Ordinary missing/damaged/foreign reservation paths fail closed for TC4; repeated large/small tails have pure and real-process regressions. **Not fully closed:** SV021-08 bypasses the checked witness during an interrupted recovery. |
| SV021-02, false previous-base binding | `_retained_prev` chooses a checkpoint tuple from the actual retained file hash and skips rotation when it would overwrite a newer verified base. A14 restores verified checkpoint bytes; the intermediate hash remains checked. The original A10/A14/A11/A8 → checkpoint → A14 cases are discriminated. **Local defect closed; integrated authority remains blocked by SV021-09.** |
| SV021-03, interrupted legacy import | **Original A5 loss closed.** LEGACY_IMPORT carries its pending generation and already-durable note blob in the same record that marks the mirror processed. The reducer validates and restores the generation; the reference graph includes its blob. The before/after-adoption fixtures distinguish the former gap. A8's separate restart regression is SV021-10. |
| SV021-04, repeated deletion | **Original trace closed.** Latest binding records a consumed absence, retains durable post-deletion messages/notes on repeated starts, and a later actual deletion after checkpoint advances the epoch. Keep these assertions while correcting SV021-09. |
| SV021-05, stale source hash | **Original trace closed.** The classifier consults the latest binding rather than membership in all historical hashes. X→Y→X, rollback edits and unpublished-import edits are covered. Do not reintroduce historical-hash acceptance to solve SV021-09. |
| SV021-06, missing notices | **Closed.** RESPONSE_REFUSED owns its notice atomically. TURN_RESPONSE owns the omission notice, and the reducer appends it when the final stored call is answered, including admission-only and recovery closure. It precedes queued messages and is no longer volatile Session state. New cuts after adoption, inside a call and after DONE exercise replay convergence. |
| SV021-07, shallow history copy | **Closed.** `copy.deepcopy` detaches nested supported history values. The real-tool fixture changes nested call fields and nested user content, then checks live/ledger/file equality and A14 recovery. |

The documented assertion changes follow the corrected record contracts: notices now belong to response records, the legacy generation belongs to import, A9t identifies an already-consumed import, and reservation-derived identity replaces the rejected length formula. I found no reason to restore those old expectations. Foundation `install_conversation(..., rotate=False)` retains its temp/file/directory fences while intentionally skipping CK3; it does not relax the write barrier.

## Evidence and next correction boundary

The receipt reports 12 pre-fix regression failures, including the real-process repeated-TC4 case, and 488 selected passes over nine bounded final batches with five real script restart cases. I inspected the changed implementation and relevant assertions independently; these remain reported runs, not runs reproduced by this review. The three findings above are static execution/corruption traces and their proposed regressions have not been run here.

Return only these three focused closure cases to Opus. Preserve the successful changes and existing assertions. Use temporary roots, fault injection, the approved bounded runner and local effects; a fresh broad suite, live provider or deployment is unnecessary. Freeze the next runtime/test commit and obtain independent re-review before acceptance.

## Effects on the later SV-022 GC boundary

- **IDENTITY is protected allocation authority**, not an orphan blob. It and any corrected integrity/transaction carrier must survive collection. GC must not rely on rebuilding uniqueness from a prefix it has deleted; the final accepted checkpoint/allocator contract must state what remains sufficient.
- **RECOVERY{conversation_adopted}.detail.blob and LEGACY_IMPORT.note.blob** are added references. `record_refs` includes both at `chassis_replay.py:609–614`. The latter also enters pending checkpoint state. Any additional repair binding or per-generation foreign-adoption state from this correction needs the same closure analysis.
- **C_n.prev may now name an older actual retained checkpoint**, rather than the immediately preceding checkpoint. Collection must follow that exact tuple and retain its full replay interval; it must not assume “the last two CHECKPOINT records” are sufficient. Existing exact replay-bound nonclaims remain important.
- The latest source binding currently depends on the retained post-checkpoint suffix. A future collector must preserve it until a new checkpoint legitimately supersedes it, including any pending authority transaction added for SV021-09/-10.

Destructive GC remains disabled; no C-G1/O2-4, bounded-total-disk or exact numerical replay-work claim is accepted. Deferred acknowledgement resolutions remain refused. Recorder-in-loop label evidence, provider compatibility, deployed ordering, real power loss, kernel/storage commissioning, main merge, deployment and pump/H/T/Q work remain outside this acceptance. SV-022 may proceed only after the remaining SV-021 correction is accepted.
