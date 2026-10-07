# SV-020 status

**Correction 1 complete; awaiting Astra re-review. Foundation inactive.**

- `afe11a0`: the interrupted, untested draft (coordinator checkpoint).
- `61833d8` / `add1627` / `4534cc0`: the draft assessed and corrected (11 items), 93 tests, receipt. The coordinator backed this up to the WIP branch (tree `3b7387f0…`). It is not accepted.
- Astra initial review: changes needed, findings SV020-01 (P1), SV020-02 (P2) and SV020-03 (P2).
- `8b897931be6986e2da9a299c63060d0925a817f3`: correction 1, with regressions written first. All 8 finding nodes that were run separately failed before the fix. Final run: **114 passed** (ledger 60, recovery 28, durability 26) through the bounded runner. Details: `checkpoint-002-astra-corrections.md` and RECEIPT §3a.
  - SV020-01: namespace fences on first use in each process, for surviving names too. `session/` is a durable-root precondition.
  - SV020-02: every acknowledged TC4 recommends the mirror check.
  - SV020-03: explicit refusal of adjacent surrogate pairs before any write; the read side is unchanged.

Preserved: canonical framing, the O1-5 correction, gate ordering, tail-bound acknowledgement, quarantine admission. Production chassis does not import the module. No `format: 2`, live gates, startup recovery or conversation-storage change. These are pure simulations and injected faults, not C-1/C-K/C-T passes.

Still staged (RECEIPT §5): global FSYNC_FAILED coverage outside `LedgerWriter`, RECOVERY_ACK-before-clear, complete replay/state/notes/frontier, response bounds, activation.

No push, main merge, deployment, account change or paid-overage use by this session.
