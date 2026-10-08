# SV-028 Astra correction 1 review

**Decision: accept SV028 within its reviewed, isolated W1 implementation scope.** SV028-09 and SV028-10 are closed. I found no remaining correction required for this bounded package. The accepted behavior is only witnessed `conversation_unreadable_unbound` + `bootstrap-preserving` over the specified state-neutral suffix; it does not authorize use on a real user session or expand any other resolution.

Reviewed immutable head `13f56f5b72d084c54a96635c184e3b0a2c8e041a`, tree `c77f009e78d6fb811f9de7d9a10ad1712f94db5a`, runtime/test commit `22324cf84a5c0f98f3a9259b75fa73869c01bb06`, against review-archive base `78180860cdba9e1afc68abb228a81981fbed379b`. The governing implementation review is `SV-028-Astra-implementation-review.md` (SHA-256 `2cba8bda7355240609ecd558adfa111e1b2014100921c832a06d0ed14f112b2a`), together with the accepted design's L1–L7. References below use the corrected head.

This was static review of immutable Git objects and supplied evidence. No tests, project imports, providers, workers, runtime edits or real-session operations were performed. Only this report was written.

## SV028-09: physical headers and the logical recovery plan

The correction consistently separates physical records from logical plan positions:

- `services/chassis_startup.py:1840` checks carrier-free completeness against the non-header projection of `extra`, while still requiring the complete exact remaining core and an absent live conversation.
- At `:2113`, the preserving path alone forms that projection. The comparison cursor advances only for logical records, and `:2144` uses the logical count to append the remaining core. The excess-record check and `after_core` use the same convention.
- The loop at `:2115` still calls `replay.apply` on **every physical record**, including the replacement header. Replay work totals are still carried into the session at `:2141`, and physical `extra` segments are still synced at `:2159`. Strict scan/chain/segment validation, B3, carrier-before-intent retirement and IDENTITY ordering remain intact.
- For every other mechanism, `logical = extra` and the cursor advances on every record. Its comparison, count and slicing behavior is equivalent to the previous implementation. The correction does not widen old-pair header semantics.

The three new cases under `test_sv028_an_own_torn_header_preserves_the_logical_recovery_plan` exercise the actual missing distinction. `cut_rotation_before_its_header` cuts the real writer's rotation before the header write, and the fixture then obtains a real valid A14 witness over the empty successor. It asserts the successor segment/end-offset relation and includes the empty file in the independent inventory. The subsequent fragment is an explicitly constructed strict prefix of the genuine next header, validated as TC1; this is a protocol-state fixture, not a claim to have reproduced kernel partial-write behavior.

For `header-only-restart`, the real recovery is interrupted at the receipt write after recreating the header, with RECOVERING and the carrier present and no logical owned record. For `carrier-retired-restart`, the interruption occurs before RECOVERING removal with the carrier absent, Π+T present and the conversation absent. The uninterrupted control covers successful header reconstruction without the second interruption. Each corrected case asserts exactly one physical header, exactly Π+T logically, the original fragment's digest/length/type, epoch+1 and retained state, no request/tool effect, archive independence, retired transaction files and a later A12t start writing no additional record.

The supplied pre-fix results are discriminating: the uninterrupted control passed, while the two restart cases failed after their complete setup at the successful-BP assertion, with `recovery_intent_mismatch` identifying respectively the replacement header and incomplete retired activation. The corrected final selection reports all three passing. Together with the source-level cursor analysis, this closes the finding without discarding physical replay or weakening completeness.

## SV028-10: accurate late-copy diagnostics

`services/chassis_startup.py:436` introduces `_refuse_late`; `_copy_entry` uses it for a hash mismatch and passes `late=True` to `_read_source`. The missing-source, over-limit and read-error branches select that same stage-aware helper. It states that the published inventory and completed copies are retained, with no carrier publication or activation. The exception documentation now distinguishes stages.

Pure admission and prior-pair refusals retain the original `_refuse` behavior. The change adds no filesystem operation, source repair, rollback or new marker action. Persistence failures during writes/fences still follow the existing separate boundary and retain their completed prefix; the best-effort marker guarantee is not strengthened.

The existing late-copy node now has four bounded conditions: changed bytes, missing source, an injected four-byte read bound, and an injected read error. Each condition first observes the published inventory and STOPPED copy, captures the actual exception, requires the retained-prefix wording and rejects the false “nothing was changed” phrase. It also checks that no carrier/activation/live deletion occurred. The changed-source case retains its deeper inventory/copy and retry checks. N4a now checks the unchanged pure-admission wording as well as byte-identical refusal behavior. No additional selected-node count is hidden in these finite internal companions.

## Evidence and scope

The correction diff changes only startup runtime code, the new SV028 test module and SV028 documentation. The CLI and prior acknowledgement test module are untouched. The inventory, capacity, archive dependency fences, immutable seal, saved STOPPED binding, frozen Π/context, notes/GC behavior and other L1–L7 mechanisms inspected in the initial implementation review remain unchanged. The previously reviewed real mutation controls and local recorder/CLI barrier remain part of the selected evidence.

I independently checked both changed-file hashes from Git objects against `results/SV-028-correction-1-test-receipt.json`:

| File | SHA-256 |
|---|---|
| `services/chassis_startup.py` | `6139ba93862def1bccd50990fe84290be3dc1b6d80ea7891178d7058473243ca` |
| `tests/test_chassis_bootstrap_preserving.py` | `29700faaaf9fe8d09e1d3613d01e6648659a79a385f7a78573bf9693a4b9f989` |

The receipt contains 14 commands: three pre-fix controls/discriminators and eleven final commands. Every final response reports no tool error and the observed pass-dot counts are `[14,1,1,9,10,1,22,35,1,14,3]`, totaling **111 selected cases: 61 new and 50 retained**. The recorded final series begins at event 75 after the last runtime/test edit at event 71. No later code correction, extra rerun or permission denial is recorded. This corroborates the bounded evidence; the acceptance conclusion also depends on the implementation and assertions examined above.

SV028 is accepted only for the specified temporary-root engineering behavior under the retained assumptions. Aggregate startup reads/RSS and literal numerical replay bounds remain unproved. The crash tests are simulations, not kernel/power-loss validation; arbitrary recovery after fsync error is not promised. Inherited fail-closed outcomes and carrier-temp accumulation remain disclosed. This acceptance authorizes no real-session acknowledgement, deletion or resumption, provider call, merge, deployment, other stop resolution, or held H/T/Q/pump/history policy choice.
