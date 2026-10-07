# SV-019 chassis package (K-A1, K-A2, K-B1, K-E1, K-G1) — STATUS

Ledger for SV-019 (Filigree not used). Branch `sv016/recorder-cleared`, base `764d70e2c3c3379a12a3c7cd1305f98c748a8893` (R-B3 accepted at `055345d`; coordinator's acceptance/backup docs preserved). I make no push, merge or deployment; the coordinator backs up consistent commits to the authorized WIP branch, which is not readiness.

Contracts: SV-013 §2.2.2/2.2.4 and §4.1 (K-A1), §2.2.7 first paragraph with SV-015 v2 §3.8/§4.7 superseding the give-up claim (K-A2), §2.2.4 message/exit portion only (K-B1), SV-015 v2 §2.3 (K-E1, replacing SV-013's UTF-8 rules), §2.2.6 atomic groups/repair with v2 §2.3's unchanged window policy (K-G1). Preflight: `../sv016-context/SV-019-Astra-preflight.json` (staging exception: no `format`/`writer`/`checkpoint` authority markers before K-D). Targets: `SV-019-bounded-targets.json`.

| Unit | State | Where |
|---|---|---|
| K-A2 narrow flap fix | done `71b2644` | `services/supervisor.py`; `tests/test_supervisor_flap.py`; one legacy assertion updated |
| K-E1 pure helpers | done `43edf30` | `tests/test_chassis_wire.py` |
| K-G1 pure repair / group-atomic view | done `5788a1e` | `tests/test_chassis_groups.py` |
| K-A1 metadata + K-B1 termination | done `1f9f1d7` | `tests/test_chassis_termination.py`, `tests/test_chassis_metadata.py`; seed handoff docstring |
| Complete selected set | 126 passed, no warnings | `RECEIPT.md` §2 |
| Receipt | done | `RECEIPT.md` |
| Correction 1: SV019-G1-01, B1-01, B1-02, B1-03 + CH1/repair wording | done `2f0567c`; 161 passed + 5 integration passed, no warnings | `checkpoint-002-astra-corrections.md`, `RECEIPT.md` §3a |

Full run log, the contract → test map, staged exclusions and limits: `RECEIPT.md`. A denied `git stash` meant K-B1/K-A1 pre-fix evidence is by source, not by run (receipt §2).

## Runs (bounded runner, `--cpu 23`)

1. `tests/test_supervisor_flap.py` pre-fix → failed at C-S1: third clean exit returned `('resume_without_session', 1)`.
2. After the fix: `tests/test_supervisor_flap.py` + the 7 legacy supervisor nodes of `test_services.py` → 18 passed.
