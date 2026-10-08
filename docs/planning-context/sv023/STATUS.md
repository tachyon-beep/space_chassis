# SV-023 status

**Accepted within the isolated temporary-fixture engineering scope.** Independent Astra acceptance: [ASTRA-ACCEPTANCE.md](ASTRA-ACCEPTANCE.md), immutable reviewed head `931d6c64367b2d9ff755eb7dd199459faf6642f3`, runtime/tests `fb638a6f4f65e382a7cdb7f691fe9cd82cbd208e`. All five findings are closed. Final narrow correction: 248 selected passes in three serial commands; preceding correction: 657 selected passes, not all rerun for the final narrow change. Historical review/worker statuses below are retained as provenance and superseded by this paragraph.

Exactly two new witnessed file-repair pairs are implemented, with checked stop evidence and durable acknowledgement closure. Invalid/conflicting carriers and unsupported resolutions remain refused. No real-session repair, acknowledgement, deletion or resumption; no main merge, deployment, live provider, exact replay-bound claim, H/T/Q or pump choice. See acceptance for evidence limits.

---


**Correction 2 (Astra SV023-05) complete; awaiting the coordinator's checkpoint and Astra re-review. Not accepted.** Review: `SV-023-Astra-correction-1-review.md` (head `aff9388`, runtime/tests `914bcfe`): SV023-01…04 closed; SV023-05 open. Fix: a no-intent TC4 carrier's consumption is decided by its exact recorded receipt, whatever the current tail. A spent permission is never applied to another tail. An unused one applies only to its exact acknowledged bytes; other continuing tails are refused before any change. No intent is written with an acknowledgement for another tail. Three new nodes failed pre-fix as traced, mutation M6 was run and restored, and the final serial runs gave 97 + 97 + 54 = 248 passes. Details: `checkpoint-002-astra-corrections.md`. Each command was submitted alone; no Git call; temporary roots only.

---

**Correction 1 (Astra SV023-01 … SV023-04) complete; awaiting the coordinator's checkpoint and Astra re-review. Not accepted.** Review: `SV-023-Astra-review.md` (head `b878ed6`, runtime/tests `c5b2ae1`), changes needed. All four findings are fixed in `services/chassis_startup.py`, with regressions written first and run alone on the reviewed runtime. Eight nodes failed as traced, including one further defect in the SV023-04 class found here: a duplicate, tail-unbound TC4 receipt after a plain process death. Final tree: 657 selected passes across 12 bounded commands (94 focused + 563 retained), no failures. Map, pre-fix outcomes, schema and ordering, tests, limits and execution provenance: `checkpoint-001-astra-corrections.md`. No Git call; temporary roots only.

- SV023-01: `read_carrier` classifies ACKNOWLEDGED (absent/old/witnessed/invalid) with types checked before dispatch. A present invalid carrier stops `acknowledgement_unverified` before any change. The old-pair schema is exact; a damaged witnessed envelope is never treated as legacy.
- SV023-02: neither command path replaces an unfinished carrier. Same-transaction retries are allowed; any other is refused byte-identically (bounded fail-closed option; no cancellation or two-transaction policy).
- SV023-03: a witnessed torn-frame RECOVERING carries a sealed `witnessed` context. Retirement order for that transaction is receipt sync, carrier, then intent. Every surviving combination is checked; nothing beyond the intent's exact core is admitted.
- SV023-04: every pair retires its carrier only over exactly one matching (reason/resolution/ack_id/TC4 tail) receipt whose segment was synced. A failed sync keeps the carrier. A TC4 carrier over a vanished tail grants nothing without its recorded receipt. Intent-core records found readable are synced before any RECOVERING removal.

Provenance correction: the initial package's V9/V10 runs overlapped (coordinator finding). They were not serial, as checkpoint 2 below implied; see checkpoint-001 §1, which also records this correction's own C10–C12 submission in one message.

---

Earlier status (kept): **Implementation and bounded validation complete; awaiting the coordinator's checkpoint and independent review. Not accepted.** Final tree: 607 selected passes across 12 bounded commands (44 new + 563 retained), no failures (RECEIPT.md §1). Mutations M1 and M3 were run and restored; `grep MUTATION services/ tests/` is empty. Changed runtime: `services/chassis_startup.py` only. New: `tests/test_chassis_acknowledgements.py`, this STATUS, RECEIPT.md. No real session was touched, and no Git call was made.

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

- V1–V12 were run on the final tree only (RECEIPT.md §1), one literal runner command each, within the unchanged caps. [Corrected later: several commands were submitted in one message and V9/V10 overlapped; not serial. See checkpoint-001 §1.]
- RECEIPT.md written: exact new pairs, schemas and domains, mechanism, reason-to-fixture and refusal matrix, crash cuts, controls, source deviations, evidence kinds, remaining limits.
- Two development failures were fixture bugs of mine (RECEIPT §1). No retained assertion was changed.
- Finding for review, not fixed (outside scope): the existing pairs' `_consume_ack` retires ACKNOWLEDGED after finding a receipt that is only readable, without syncing its segment (the SV022-01 class). The new pairs sync it. [Corrected later: it was not out of scope; fixed as SV023-04 in checkpoint-001.]

## Activation boundary

Implementation and tests run on temporary roots only. No real session is acknowledged, repaired, deleted or resumed.
