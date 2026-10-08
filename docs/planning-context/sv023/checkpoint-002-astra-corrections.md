# SV-023 checkpoint 002: Astra correction 2 (SV023-05)

2026-10-08. Review: `SV-023-Astra-correction-1-review.md` (context directory), read in full before any edit. Reviewed head `aff938862f82cc3b62beb584b6077029e9d446d5`, runtime/tests `914bcfeb3df9453ff58579cfb91b8f4ccfcc3fbd`. SV023-01…04 are independently closed; acceptance is blocked only by SV023-05. Their fixes and all prior assertions are preserved unchanged. The worker made no Git call. **Not accepted; awaiting re-review.** Temporary roots only; no provider, no real session.

Execution: each command in §2 and §5 was submitted alone, one tool call per message, and its completed result awaited before the next. The runner was not read, changed or bypassed, and no command was retried.

## 1. The defect

`chassis_startup._recover` decided that a no-intent TC4 carrier had already been consumed only when the current tail was empty (SV023-04's guard). When a consumed TC4 carrier is left pending (RECOVERING retired, ACKNOWLEDGED not), the next start can find a nonempty tail. An M-3 change to one body byte of the final hidden-turn MSG_APPEND, header and length intact, makes an ordinary TC2. The old permission was then passed to that tail's recovery:
- `derive_core` wrote a second RECOVERY_ACK with the same `ack_id` and the damaged notice's tail hash;
- the new RECOVERING embedded an `ack` whose `tail_sha256` named the original ambiguous tail, which `_validated_intent` rejects on restart (`recovery_intent_invalid`/`ack`).

## 2. Pre-fix evidence (new nodes written first, run alone on the reviewed runtime)

| Node (`tests/test_chassis_acknowledgements.py`) | Pre-fix failure |
|---|---|
| `test_sv023_05_a_consumed_tc4_permission_is_not_applied_to_an_independent_damaged_tail` | `only the original tail-bound receipt`: a second RECOVERY_ACK, `ack_id f21e6d84…`, `tail_sha256 f55804c2…` (the damaged notice) next to the original `d13d4a8b…` |
| `test_sv023_05_an_interrupted_independent_tail_recovery_has_no_acknowledgement_and_converges` | the new RECOVERING's `ack` was the TC4 acknowledgement (`tail_sha256 d13d4a8b…`, the original ambiguous tail), not null, for the damaged notice's own TC2 tail |
| `test_sv023_05_control_without_a_recorded_receipt_a_different_present_tail_is_refused` | `Opening(classification='A9', …)`: an unused TC4 permission was applied to a different (TC1) tail and the start continued |

The fixture is a real TC4 stop, the real command, and a real recovery cut (process death) after RECOVERING's durable removal and before ACKNOWLEDGED's. Before the restart, the test checks that the ledger holds exactly the original receipt; that the final record is the hidden-turn notice; and, after the one-byte change, that the scan classifies `TC2` with declared type `MSG_APPEND` and P ending one record earlier.

## 3. Correction (`services/chassis_startup.py`, the no-intent TC4-carrier branch of `_recover` only)

The tail is classified first. Then, for a pending TC4 carrier with no existing intent:
1. **Exact receipt recorded** (`RECOVERY_ACK` payload equal to the carrier: reason, resolution, ack_id, tail_sha256), *whatever the current tail*: the permission is spent. `tail_ack = None`, so it is never applied to another tail. The carrier is kept only for the existing durable retirement in `_consume_ack` (receipt segment synced, then removed).
2. **No receipt, current tail is exactly the acknowledged bytes**: the permission applies, as before.
3. **No receipt, any other tail that would continue under it** (TC0, TC1, TC2): stop `acknowledgement_unverified` before any change. This subsumes SV023-04's empty-tail case.
4. **No receipt, a tail that stops anyway** (another TC4, TC3, A2): `tail_ack = None`; the ordinary stop applies unacknowledged. A different TC4 tail still stops `ledger_tail_ambiguous`, which the retained `test_a_stale_acknowledgement_grants_nothing` requires.

Plus an invariant: a new intent is never written with an acknowledgement whose `tail_sha256` is not its own tail's (SessionInvariant before the write).

Under an existing validated intent, nothing changes: its frozen `ack` is still used to re-derive and verify the already-written prefix. TC4 classification, the conservative closure and spend, and identity are unchanged. No operator choice is created or synthesized.

## 4. Tests and controls

- **Completed variant**: the restart carries the first process's watermarks; host loss is simulated afterwards. Assertions: exactly the original tail-bound receipt; one `possible_duplicate_spend` with next `{reserved+1, 1}`; one `damaged_final` for type `0a` bound to the damaged frame's hash; the ordinary notice `[runtime] a damaged MSG_APPEND record was lost at recovery`; the corrupt/ copy byte-equal to the damaged frame; no REQUEST_SENT/INVOKING added; IDENTITY = `reserved+1`; no ACKNOWLEDGED/RECOVERING/STOPPED/FSYNC_FAILED; next label `:reserved+1:1`; a further start writes nothing.
- **Interrupted variant**: process death immediately after the new RECOVERING's rename and session/ fence. Its `ack` must be null and its `tail_sha256` the damaged frame's. First restart (carried watermarks) dies again before truncation; simulated host loss. Second restart completes; host loss again. Then the same assertions; no `recovery_intent_invalid`.
- **Control**: no recorded receipt plus a different present (TC1) tail: refusal with only STOPPED changed, no receipt, no intent.
- **Retained controls, unchanged and passing**: `test_sv023_04_a_pending_tc4_carrier_whose_tail_is_gone_grants_nothing` (empty tail), the four `test_sv023_04_tc4_keeps_its_conservative_closure…` variants, `test_a_stale_acknowledgement_grants_nothing`, and the other recovery_live TC4 nodes.
- **Source mutation M6** (marked, run, restored; `grep MUTATION services/ tests/` empty): the receipt check made empty-tail-only again. On the completed variant, the consumed permission was mistaken for an unused one and the start stopped `acknowledgement_unverified` ("the acknowledged tail is not the ledger's") instead of recovering the independent tail.

## 5. Final runs (final tree, after M6 was restored)

`python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <targets>`, three serial commands:

| # | Targets | Result |
|---|---|---|
| D1 | `tests/test_chassis_acknowledgements.py` | 97 passed (94 prior + 3 new) |
| D2 | `tests/test_chassis_recovery_live.py` | 97 passed |
| D3 | `tests/test_chassis_recovery.py tests/test_chassis_durability.py` | 54 passed |

Total: 248 selected passes, no failures. The 657 cases of checkpoint-001 were not all rerun, as instructed. No further retained node was added: the change is confined to the no-intent TC4-carrier branch, and its ordinary path (exact tail, no receipt) is the one D2's TC4 nodes exercise. The other TC4 consumers (`test_chassis_gc.py`, `test_chassis_notes.py`) use that same path, so no concrete unresolved concern arises.

## 6. Limits

- **Consumed carrier over a new ambiguous tail.** If such a carrier is still pending when a *new* ambiguous (TC4) tail appears, the start stops `ledger_tail_ambiguous` with the carrier still pending. By the SV023-02 fail-closed rule, that new stop cannot be acknowledged while the carrier exists, and the carrier is retired only by a successful start. This is a compound case (an interrupted cleanup, then a new hidden tail) and remains stopped with both preserved.
- **No reversion claims.** Unsynced truncation reversion is still not simulated and is not claimed as tested.
- All other limits of checkpoint-001 §5 are unchanged.
