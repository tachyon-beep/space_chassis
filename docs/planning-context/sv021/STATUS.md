# SV-021 status

**Integrated adoption implemented on the isolated WIP branch; committed; awaiting independent review.** 465 selected passes across 9 bounded runs (RECEIPT.md §1); no failures on the final tree.

Base: accepted `437b52d765269dbfb127505e27d6b8dca4ed99e6` (branch `sv016/recorder-cleared`, read from `.git/refs`). Foundation acceptance and its limits: `docs/planning-context/sv020/ASTRA-ACCEPTANCE.md`.

## Coordinator checkpoint

The worker completed with exit 0. Its two repository-location Git checks were denied by its CLI, and it made no commits. The coordinator used the already-authorized commit workflow after the worker stopped: runtime/tests `3b145c6aea18a0fc537de9cd74fe1adc539039f6`. No runtime/test bytes were changed by committing. R1–R9 results below refer to the tested files committed here; the final foundation docstring-only edit was followed by another 114-pass foundation run. No redundant full repetition was performed solely to assign a commit ID. Astra reviews immutable objects next. No merge or deployment occurred.

Files changed or added relative to `437b52d`:

- new: `services/chassis_envelope.py`, `services/chassis_replay.py`, `services/chassis_session.py`, `services/chassis_startup.py`
- new: `tests/test_chassis_adoption.py`, `tests/test_chassis_replay.py`, `tests/test_chassis_session.py`, `tests/test_chassis_checkpoint.py`, `tests/test_chassis_notes.py`, `tests/test_chassis_recovery_live.py`
- modified: `services/chassis.py`, `services/chassis_persistence.py`, `tests/test_chassis_recovery.py` (one frontier assertion), `tests/test_chassis_metadata.py` (first test, deliberately)
- new docs: `docs/planning-context/sv021/STATUS.md`, `docs/planning-context/sv021/RECEIPT.md`

## Development checkpoints (combined into one coherent runtime/test commit)

- **A — K-E2 pure adoption.** `chassis_envelope.py`; `chassis.py` re-imports the moved SV019 helpers (same function objects); `test_chassis_adoption.py` (pure part). Inactive.
- **B — state + replay reducer.** `chassis_replay.py`, `test_chassis_replay.py`. Inactive.
- **C — session owner.** `chassis_session.py`, `test_chassis_session.py`. Inactive.
- **D — startup authority, recovery transaction, acknowledgements.** `chassis_startup.py`; foundation edits in `chassis_persistence.py` + `test_chassis_recovery.py`; `test_chassis_recovery_live.py` (simulations), `test_chassis_notes.py`, `test_chassis_checkpoint.py`. Inactive.
- **E — activation.** `chassis.py` (every mutation through the session; startup before the socket and the duty; `--acknowledge-stop`), `test_chassis_metadata.py`, the runtime tests in `test_chassis_adoption.py`, the real script-restart section of `test_chassis_recovery_live.py`, the TERMINATION-order and authority fixes found by E's runs.

A–D were developed and tested while `chassis.py` imported nothing from them except the moved helpers; E is one step. Committing E without A–D, or D without E's fixes (TERMINATION before DONE; the `unpublished`/`run_json_missing` authority), would ship a known defect.

## Activation boundary (what is live after E)

Live in `chassis.run()`: startup classification A0–A15 (with v2 tail classes, previous-base replay, A15) before the recorder socket or the duty is touched; REQUEST_SENT before request bytes, with the request sized locally first; response adoption (TURN_RESPONSE / RESPONSE_REFUSED) before any tool; INVOKING before each tool body; blob before DONE; every message, note, history replacement, recap fold, termination and checkpoint as ledger records through one owner; CK1–CK6; threshold checkpoints and segment rotation at unit boundaries; FSYNC_FAILED attempted once on any persistence failure; `format: 2`/`writer`/`checkpoint` published at CK5 with the CHECKPOINT that follows.

Not live / deferred: destructive GC (disabled; retains everything; `retained_refs` is computed and tested only); acknowledgement resolutions other than the three in RECEIPT §3 (refused, no change); no claim of the v2 1.4.7 numeric recovery bounds, bounded total disk, C-G1/O2-4, recorder-side label recording, provider compatibility, deployment or power-loss behaviour. Details: RECEIPT.md §3 and §5.

## If work resumes

The worker reports a consistent implementation and the selected checks pass. Independent Astra review is pending; acceptance is not assumed. The coordinator will preserve the review and route any corrections back to Opus. Candidate follow-ups (not started): GC execution with C-G1/O2-4 crash tests; the deferred acknowledgement resolutions; closing the remaining 1.4.7 domain assumptions before any bound is claimed; a recorder-in-the-loop restart test for the label portion of C-1a/O1-6.

No push, main merge, deployment, account change or paid-overage use by this session.
