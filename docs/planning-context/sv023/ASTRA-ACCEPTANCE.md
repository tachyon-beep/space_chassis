# SV-023 Astra correction 2 review

**Accept SV-023 within its existing isolated, temporary-root engineering scope.** SV023-05 is closed, the SV023-01…04 fixes remain intact, and this static re-review found no remaining activation blocker within the stated package. Acceptance does not authorize real-session acknowledgement, repair or deletion, main merge, deployment, live providers, or held H/T/Q/pump decisions.

Accepted immutable head: `931d6c64367b2d9ff755eb7dd199459faf6642f3`. Runtime/tests: `fb638a6f4f65e382a7cdb7f691fe9cd82cbd208e`. Correction base: `aff938862f82cc3b62beb584b6077029e9d446d5`; prior accepted foundation: `d301d139cf85961a823c874d7661a7000d563d09`. Runtime/test commit to reviewed head changes documentation only. I read static Git objects, checkpoint-002, the relevant retained control and the external test receipt. No tests, project imports, providers or runtime edits were performed; this report is the only written output.

## SV023-05 closure

At `services/chassis_startup.py:948`–961 the no-intent TC4-carrier branch now checks its **exact recorded receipt regardless of the current tail**. A match clears `tail_ack`; the carrier remains solely for the existing durable receipt retirement. Consequently a later damaged final notice follows ordinary TC2 recovery without another RECOVERY_ACK or another conservative spend transition.

Without that receipt, the permission is usable only when the current tail is nonempty and hashes to its original acknowledged bytes. A different TC0/TC1/TC2 state stops before mutation. Different TC4/A2/TC3 states retain their ordinary unacknowledged stop; the retained stale-tail test still requires this behavior. This distinction preserves refusal semantics without authorizing a different tail.

At 1009–1016 an explicit invariant also prevents serialization of a new intent whose embedded acknowledgement disagrees with its own tail. The independent TC2 transaction therefore writes `ack: null`. Recovery under an existing checked intent still uses its frozen acknowledgement, preserving exact re-derivation of an already-written original TC4 prefix.

The three new tests are discriminating:

- The fixture performs the actual TC4 stop/command/recovery, interrupts after durable intent retirement and before carrier removal, then changes one byte of the final notice body. It asserts the resulting TC2 classification and intact original receipt before testing recovery.
- Completed and interrupted variants require exactly the original tail-bound receipt, one original conservative spend transition, the correct damaged-frame recovery/hash and quarantine bytes, preserved identity, zero requests/tools, complete marker cleanup and a further startup that writes nothing.
- The interrupted variant at `tests/test_chassis_acknowledgements.py:1511` checks the new durable intent's null acknowledgement, interrupts a restart before truncation, carries durability watermarks through simulated host loss, and completes another restart. The no-receipt/different-tail control requires refusal with only STOPPED changed and no new intent or receipt.

The supplied pre-fix evidence reports all three failing as traced. The restored empty-tail-only mutation also discriminated the guard. These assertions address both the duplicate receipt and the self-invalid recovery intent, rather than merely changing the observed stop reason.

## Prior guarantees and evidence limits

The narrow runtime delta leaves fail-closed carrier classification, conflict refusal, sealed witnessed recovery context, carrier-before-intent witnessed cleanup, exact receipt matching and actual-segment durability fences unchanged. It adds no durable file, deletion candidate or GC authority. RECOVERING and ACKNOWLEDGED remain collection blockers and remain outside the ledger/blob deletion namespace.

Correction 2 reports **248 selected passes in three serial commands**: 97 acknowledgement, 97 live-recovery and 54 recovery/durability checks; worker exit 0, no denials. This is the final narrow validation set, not a claim that all 657 checkpoint-001 selections were rerun. The earlier correction's reviewed evidence remains 657 selected passes. I inspected assertions and control flow independently; I did not execute either set.

The documented limits remain honest and accepted for this tranche: only the two witnessed file-repair pairs are newly enabled; legacy stops lacking witnesses and other resolutions remain refused; conflicting unfinished acknowledgements preserve their evidence and stay stopped. A consumed carrier followed by a new ambiguous tail likewise remains stopped rather than reusing old permission. Unauthenticated append garbage fails closed. Unsynced truncation reversion is not simulated and is not claimed as tested. No exact numerical replay bound or broader bootstrap/lost-ledger recovery is accepted here.

## SV024 guard selection

The existing SV024 27-target preflight remains applicable. Retain the seven exact startup/fence/cleanup selectors listed in `results/SV-023-Astra-correction-1-review.md`, and add this now-reviewed eighth selector:

```text
tests/test_chassis_acknowledgements.py::test_sv023_05_an_interrupted_independent_tail_recovery_has_no_acknowledgement_and_converges
```

It covers independent recovery after acknowledgement cleanup was interrupted, null frozen permission, subsequent interruption and carried durability. SV023's acceptance prerequisite for the proposed O2-5 namespace package is now satisfied; this report neither implements nor accepts SV024 and requests no additional test execution.
