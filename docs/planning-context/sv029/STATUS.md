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
