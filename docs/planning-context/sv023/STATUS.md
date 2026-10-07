# SV-023 status

**Implementation and bounded validation complete; awaiting the coordinator's checkpoint and independent review. Not accepted.** Final tree: 607 selected passes across 12 bounded commands (44 new + 563 retained), no failures (RECEIPT.md §1). Mutations M1 and M3 were run and restored; `grep MUTATION services/ tests/` is empty. Changed runtime: `services/chassis_startup.py` only. New: `tests/test_chassis_acknowledgements.py`, this STATUS, RECEIPT.md. No real session was touched, and no Git call was made.

---

Earlier status (kept): **In progress (worker). Not accepted.** Launch base `d301d139cf85961a823c874d7661a7000d563d09`, accepted SV-022 runtime `53c5c44b167f73e7aefb326fdeacfdced5839835` (final review `SV-022-Astra-correction-1-review.md` = `docs/planning-context/sv022/ASTRA-ACCEPTANCE.md`). Scope: `SV-023-Astra-preflight.md`; targets `SV-023-bounded-targets.json`. The worker makes no Git call; the coordinator commits after the worker stops.

## Checkpoint 0: design fixed, nothing active

Inputs read: the SV-023 preflight; the SV-022 acceptance and STATUS/RECEIPT; SV-013 §2.2.2 (A0–A15 and the resolution paragraph, l.558); SV-015 v2 §1.1 (M-1…M-6), the CK5 row (l.335); `services/chassis_startup.py`, `chassis_persistence.py`, `chassis_session.py`, `chassis_gc.py`, `chassis_replay.py` (state), `chassis.py` (CLI, run.json writers); the harnesses in `test_chassis_recovery_live.py`, `test_chassis_gc.py`, `test_chassis_correlation.py`.

Design (engineering decisions, listed for review in RECEIPT.md):

1. **Exactly two new pairs**, `WITNESSED_RESOLUTIONS = {(conversation_unreadable_unbound, continue-from-bound), (run_json_unreadable, continue-from-bound)}`, added to the explicit allowlist. `cp.ACK_RESOLUTIONS`/`DEFAULT_RESOLUTIONS` stay a low-level filter and authorize nothing alone.
2. **Stop witness** (new STOPPED `detail.witness`). It is captured only at those two stops, and only if the ledger scan is strictly clean (TC0, no A2), no RECOVERING/ACKNOWLEDGED/FSYNC_FAILED exists, no pending or unauthorized collection exists, the newest CHECKPOINT state validates, and IDENTITY is checked and covers every used turn. It binds lineage; ledger first/last seq, last chain, last segment, physical end (segment, offset); C_n (tuple, record chain, run_sha256); IDENTITY; a random `stop_id`; and a SHA-256 `check` over all of these (M-3). It is taken from the ledger and IDENTITY only, never from the damaged file. If any condition fails, the stop is written exactly as before and is ineligible.
3. **Pure verifier** `witnessed_evidence`. It uses the strict scanner, `gc.unauthorized_prefix`/`pending_intent`, `SessionState.from_wire`, `read_identity`, `_binding` and the strict replay plus `derive_core` for TC0. It requires everything in the witness to be unchanged; C_n directly bound (latest binding = C_n's hash, kind checkpoint or its own restore); conversation.json = C_n bytes; run.json SHA-256 = C_n.run_sha256 and its format-2 fields agree; blobs_live and suffix blobs present; replay and closure derivable. It refuses (LedgerError) with no write.
4. **Carrier** ACKNOWLEDGED (sealed with `check`). It holds reason, resolution, `ack_id` (as today: STOPPED bytes + pair), the witness and the verified evidence. Order: verify → durable carrier → STOPPED removal. A repeat with the same stop is idempotent; a repeat after STOPPED removal re-fences session/ only. Any other pending carrier is refused.
5. **Consumption at the next start**, before any classification mutation: the carrier is re-verified over the records up to the witness end. Records after it may only be this same transaction's own prefix (LEDGER_HEADER, then RECOVERY_ACK{ack_id}, then exactly derive_core's closure in order). Mismatch → new stop `acknowledgement_unverified`, which has no resolution. session/ is fenced, then RECOVERY_ACK is written **first** (once). A receipt that is readable but not written by this process has its own segment fsynced before the carrier is retired (the SV022-01 analogue). Closure then follows the accepted TC0 rules; the carrier is removed last.
6. No change to bootstrap-preserving, lost/damaged/ahead-of-ledger paths, the newer integrity stops or the three existing pairs. No truncation, rotation or deletion of ledger, blobs, corrupt/ or fixture archives.

## Checkpoint 1: implemented, focused file passing, controls run

- Design change found during implementation (point 5 of the design): a process death mid-append of the receipt or closure (M-1) leaves a torn frame after the witnessed end. With the strict TC0 check, that would have stopped the session `acknowledgement_unverified`. At consumption the verifier now accepts after the witnessed end only this transaction's own deterministic frames, optionally followed by a strict byte prefix of its next frame. That torn frame goes to the ordinary TC1 rule (RECOVERING, corrupt/ copy, RECOVERY{torn_incomplete}). A RECOVERING is accepted only if anchored at or after the witnessed end. Arbitrary garbage there is still refused (a documented limit under host loss, see RECEIPT).
- The receipt's segment is fsynced once, immediately before the carrier is retired (it covers a readable-but-unsynced receipt left by an earlier start).
- Source mutations M1 (STOPPED removed before the carrier) and M3 (no own-prefix check) were applied, run, failed as expected, and restored; `grep MUTATION` is empty.
- Next: final bounded validation on the final tree, then RECEIPT.md.

## Checkpoint 2: final validation and receipt

- V1–V12 were run on the final tree only (RECEIPT.md §1), one literal runner command each, within the unchanged caps.
- RECEIPT.md written: exact new pairs, schemas and domains, mechanism, reason-to-fixture and refusal matrix, crash cuts, controls, source deviations, evidence kinds, remaining limits.
- Two development failures were fixture bugs of mine (RECEIPT §1). No retained assertion was changed.
- Finding for review, not fixed (outside scope): the existing pairs' `_consume_ack` retires ACKNOWLEDGED after finding a receipt that is only readable, without syncing its segment (the SV022-01 class). The new pairs sync it.

## Activation boundary

Implementation and tests run on temporary roots only. No real session is acknowledged, repaired, deleted or resumed.
