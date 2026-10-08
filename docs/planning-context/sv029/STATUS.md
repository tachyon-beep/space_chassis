# Current status: SV029 accepted within its bounded test/evidence scope

Independent Astra acceptance: reviewed head `4bd07c01f6f64aacf60353e853698461acce56e7`, test commit `8b2e5856607b3de5f1459966d5602dff5cb68bf8`. [ASTRA-ACCEPTANCE.md](ASTRA-ACCEPTANCE.md) finds no required correction. Twelve selected cases passed in two serial commands, without failure/retry/cap hit/denial. Existing runtime/tests unchanged.

Accepted counterexamples: final previous-base replay returns 58,720,256 message-blob bytes against the strict 50,352,266 claim; newest-base replay reads 365 non-origin records against 358 under the stated schedule of 108 edited interruptions. Controls return 8,388,608 message-blob bytes and 257 records. No replacement bound, PR-N proof, runtime/oracle change or real-session operation follows. All resource/kernel/policy nonclaims remain.

---

# Current status: SV029 implemented and executed (12/12 in the two manifest commands); awaiting independent immutable Astra review. Not accepted.

The test-only package follows the accepted design under L1–L6. It adds one new module, `tests/test_chassis_replay_residual.py`, with 4 nodes. Runtime code, existing tests, canonical sources, literals and the generator are unchanged. [RECEIPT.md](RECEIPT.md) has the commands and the asserted values. DESIGN.md now opens with the governing L1–L6 corrections; the draft below them is kept as history.

| Inequality (SV015v2 §1.4.7, defaults) | Executed result, conditional on review |
|---|---|
| Previous base, bytes `< 50,352,266` | **N1:** final A14 from the retained base A, spanning 7 default threshold intervals, read 56 distinct 1 MiB message blobs = **58,720,256 B**, beyond the bound regardless of frame counting. Each interval stayed under the newest-row bound. Control **N2** (immediate previous base): 8,388,608 B of blobs, total < 25,166,144 |
| Newest base, records `≤ 358` | **N3:** after a threshold checkpoint that died before its frame, 108 edited starts each dying at install entry. The final start replayed **365** records after B's frame, from B's bytes, with no previous base. Control **N4** (no edits): 257 records, constant |

**What these results are not:**

- They are counterexamples to the canonical numbers, not replacement bounds.
- N3 holds under its stated repeated edit-and-death schedule. The bound under PR-N (one interruption, no external change) is still unproved and still not refuted.
- The crashes are simulated in-process.
- RSS, latency, total I/O, `U_r`/`U_b`, `T_origin` and every SV025–SV028 nonclaim remain open.

**Contract decisions this exposes, not taken here:**

- **D1:** how the previous-base row treats a retained base that spans `k` intervals.
- **D2:** whether the newest-records row quantifies over repeated crash/edit schedules, or needs a premise such as PR-N plus a `U_r` proof.
- **D3:** whether the threshold should ever count previous-base work.

Further measurement or analysis of these remains engineering work. Changing a bound, its premises, retention semantics or threshold scope needs explicit contract/design closure.

There was no merge, deployment, real-session operation, provider call, policy choice or cap change.

---

# SV029 status (history): design accepted with launch qualifications; tests not yet implemented

Independent Astra review accepted the bounded architecture at c2cb7ebae13ac02c524b974c880a9379bde006b9. [ASTRA-DESIGN-REVIEW.md](ASTRA-DESIGN-REVIEW.md) L1–L6 govern implementation over earlier draft expectations. The matrix remains four new and eight retained cases, two serial commands, unchanged caps. Numerical evidence awaits execution and immutable review.

---

# SV029 status: design proposed; awaiting independent Astra design review. Not accepted. Nothing executed.

Base: accepted head `7936b665c4653ff61ec227ddd3d1589da31f3abe`. The deliverable is [DESIGN.md](DESIGN.md). It is a test-only proposal for the two §1.4.7 inequalities that SV025–SV028 left unproved.

## Findings (static source trace; each would be confirmed only by the proposed tests)

| Inequality | Proposed result | Mechanism |
|---|---|---|
| Previous base, bytes `< 50,352,266` | **Counterexample N1**, crash-free | `_retained_prev` (`chassis_session.py:610–625`) keeps an older bound `.prev.json` while the current file is an unbound external edit. `C_n.prev` can therefore span seven default threshold intervals of 1 MiB direct messages: ≥ 58,720,256 blob bytes. Every interval stays within the newest-row bound, so the excess comes from the span, not from an oversized unit |
| Newest base, records `≤ 358` | **Counterexample N3**, under a stated schedule | 256 inline messages; a death after CK5 (A10); then 108 starts that each follow an external edit (A11, one EXTERNAL_EDIT) and die at CK2 entry before their threshold checkpoint. `N_110 = 365`, and no default cap bounds the growth |
| Newest records under a single interruption (PR-N) | **Unproved, not refuted** | Would require actual `U_r` (with startup closure) ≤ 102 (SV025 holds 103 as unproved) |

Controls: N2 (no span gives one interval, < bound) and N4 (repeated deaths without an external change add no records, 257 ≤ 358).

A torn-CK6 (M-2) loop was traced and not selected. It is capped by `MAX_CORRUPT_FILES = 64` and would need a ≥ 39-record crashed unit.

## Proposed package

- 4 new nodes in a new `tests/test_chassis_replay_residual.py`, plus 8 named retained nodes.
- 2 commands, explicit node IDs only, unchanged runner caps.
- Estimated peak ≈ 70 MiB disk and < 200 MiB RSS, all in a temporary root.
- No runtime, oracle, literal, generator or existing-test change.

## Decisions exposed, not taken

- **D1**: how the previous-base row should treat a retained base spanning `k` intervals (restate, change the retained-prev rule, or withdraw).
- **D2**: whether the newest-records row quantifies over repeated crash/edit schedules, or needs a PR-N premise plus a `U_r` proof.
- **D3**: whether the threshold should ever see previous-base work.

These are owner/contract choices for a later dossier, not part of this package.

## This invocation

**Read:**

- Current `services/chassis_session.py`, `chassis_startup.py`, `chassis_replay.py`, `chassis_persistence.py`, `chassis.py`, `chassis_envelope.py` (relevant ranges).
- `tests/test_chassis_bounds.py`, `tests/test_chassis_recovery_live.py` (helpers and cuts), and the `tests/test_chassis_accounting.py` node list.
- The SV025–SV028 acceptances.
- SV015v2 §1.4.1–1.4.7.

**Not opened:** `chassis_gc.py`, the literal file, the generator and the SV013 dossier. They were not needed for the exact clauses, and the bound constants were checked against the SV015v2 text.

**Not done:** no tests, shell, Python, Git, imports, providers, agents or real-session operation. Only DESIGN.md and STATUS.md were written. No denial occurred.

**Retained nonclaims:** kernel/power-loss, RSS, latency, unknown partial I/O, lifetime work, `T_origin`, total startup I/O, segment read slack, U_r/U_b maxima, and every held H/T/Q/pump/history/policy choice.

**Next:** independent Astra design review of DESIGN.md. Implementation follows only on acceptance.
