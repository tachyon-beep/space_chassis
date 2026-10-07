# SV-020 status

**Foundation corrected and tested; awaiting independent Astra review. Not activated.**

History: the first Opus 5.5 session wrote `services/chassis_persistence.py` and stopped with `Prompt is too long` (exit 1) before running any test. The coordinator preserved that untested draft at `afe11a0` (accepted base `6f6c054f396ccbd30e940267ebc9b9e0d6e646d9`).

This session (fresh Opus 5.5 context):

- `61833d8`: assessed the draft against SV-015 v2 §1.1–1.4, D13 §2.2.2–2.2.3 and the SV-020 preflight, and corrected 11 defects (RECEIPT §1).
- `add1627`: `tests/test_chassis_ledger.py` (44), `tests/test_chassis_recovery.py` (28), `tests/test_chassis_durability.py` (21). 93 passed through the bounded runner. Three mutation controls failed as required.
- O1-5 source oracle corrected (V2-06(2)): valid INVOKING + 10 bytes → TC1 with the call unknown; invalid full frame + 10 bytes → TC3 stop. Both are kept.

Production chassis does not import the module. `run.json` has no `format`, there are no live gates, no startup recovery, and conversation storage is unchanged. These are pure simulations and injected faults, not C-1/C-K/C-T crash/restart passes. Activation prerequisites and evidence limits: RECEIPT §5–6.

No push, main merge, deployment, account change or paid-overage use.
