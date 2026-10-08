# SV-028 status

## Independent review: design correction required before implementation

Astra reviewed immutable `1058c5475db656b10e0ec14bd47dae1cfc9c190b` and requested one design-only correction round. See [ASTRA-INITIAL-DESIGN-REVIEW.md](ASTRA-INITIAL-DESIGN-REVIEW.md), findings SV028-01–05. The W1 envelope and A12-compatible E1+S1+R1+N1 semantics are supported engineering; no new owner-policy gate is required.

Required corrections: durability of inherited activation before live-file unlink; an immutable core/epoch plan and carrier-free RECOVERING reconstruction; a complete declared preservation inventory and sealed/unsealed retry distinction; physical scratch/peak capacity and exact encoded manifest/carrier bounds; truthful capability registration and corrected finite state/namespace/crash fixtures. The original design and its proposed 69-case plan below are not implementation authority.

## Design round 0: complete, awaiting independent Astra review. Not implemented. Not accepted.

- **Base inspected:** accepted commit `5c2366cef7851b39d5363bdadcce3e1c0b25711c`. SV016–SV027 are accepted in their own scopes; `sv027/ASTRA-ACCEPTANCE.md` was read and nothing in SV027 is reopened.
- **Obligation:** the deferred `bootstrap-preserving` resolution (SV021 RECEIPT l.61; SV023 STATUS item 6; SV024 RECEIPT l.139), narrowed to one admitted case.
- **Files written:** only `docs/planning-context/sv028/DESIGN.md` and this file. No runtime, test, source, literal, oracle, generator or frozen-evidence file was touched.

### Proposal in brief

**One pair is admitted:** `conversation_unreadable_unbound` + `bootstrap-preserving`. It requires a valid SV023 stop witness and a **state-neutral** ledger suffix after the witnessed newest checkpoint: only `LEDGER_HEADER`, `RUN_END` and complete `GC_INTENT`/`GC_DONE`. Every other stop/resolution stays refused; DESIGN §3 names what each is missing. That covers `run_json_unreadable`, TC4, lost/ahead/damaged ledgers, A6, and the A14 cases with a non-neutral suffix or no witness.

**The operator command (Phase A):**
- runs a pure 14-point admission (DESIGN §4);
- copies every session file that activation or later ordinary operation could rewrite or remove into `session/preserved/<ack_id>/`, as independent bytes (temp + fsync + rename + directory fence, never `link`);
- seals the set with a manifest written last;
- makes a sealed carrier durable, then removes STOPPED.

**The consuming start (Phase B):**
- re-verifies the carrier, the manifest and every preserved byte;
- writes `RECOVERY_ACK` first, then the accepted TC0 closure (at most one `possible_duplicate_spend`);
- then writes one `EXTERNAL_DELETE{epoch: e+1, notices: [], cause: "bootstrap_preserving", ack_id, manifest_sha256}`. Its fsync is the linearization point;
- then unlinks the preserved unreadable `conversation.json`, fences `session/`, retires the carrier and reserves IDENTITY.

No request or tool can happen before all of that.

**What is retained and what is reset:**
- Lineage, request identity, IDENTITY, note state, legacy status and originals are carried unchanged from the verified checkpoint state.
- Only messages (to `[]`) and `recap_folded` (to 0) reset.
- `history_epoch` advances exactly once, by one.

**Code impact:** the reducer, binding rule, GC, persistence layer, chassis CLI and every existing test are unchanged (DESIGN §10).

### Choices left for review (not silently selected)

These are DESIGN §6. The source settles the explicit operator act, the epoch+1, keeping every file and "bootstrap". It does not settle:

| Choice | Recommended | Why |
|---|---|---|
| Notice to the model | **S1**: none, exactly A12's duty-visible path | A notice (S2) stops the duty's `bootstrap()` from running; S3 needs a state-schema change |
| `recap.md` | **R1**: leave it in place, as A12 does (its bytes preserved) | R2 (remove it) would be a new mutation that diverges from A12 |
| Pending notes | **N1**: carry them and adopt each once | The source requires the watermark is never reset |
| Lineage | **The same lineage** | The source's "epoch+1" implies it |
| Activation record | **E1**: `EXTERNAL_DELETE` plus a `cause` field | E2 is a new RECOVERY kind with reducer code; E3 is a new type id (rejected) |

E1+S1+R1+N1 adds no duty-visible behaviour that the accepted A12 path lacks. S2, S3 or R2 would be decisions for John.

### Frozen test proposal (nothing run)

- **New file `tests/test_chassis_bootstrap_preserving.py`, 22 nodes:**
  - three neutral fixture variants;
  - refusal matrices;
  - ordering/fence log;
  - full cut sweeps under process death and simulated host loss;
  - second interruptions;
  - own torn frames;
  - stale/conflicting acknowledgements;
  - a conflict after the linearization point;
  - a real-CLI first-request-barrier run;
  - three monkeypatched negative controls;
  - a registry pin.
- **47 retained nodes**, listed by exact id (DESIGN §11.4): 33 SV023 acknowledgement nodes including both cut sweeps and the CLI node, plus A0/A1/A6/A12/A14/SV021-04, replay, notes, GC and SV027 rotation.
- **Total:** 69 cases in 8 serial commands, plus B0 and D1–D3 on the unchanged runtime. All run through the approved runner within the unchanged limits (120 CPU s / 180 wall s / 512 MiB AS; aggregate 50% CPU / 2 GiB / 64 tasks / nice 15). The estimate is in DESIGN §11.5.

### Not claimed

No real-session acknowledgement, repair, deletion or resumption. No power-loss, kernel or partial-I/O guarantee beyond the existing helpers. No numerical replay/segment/read bound. No other stop or resolution. No H/T/Q/pump/history policy, provider, merge or deployment. The inherited SV023-02 wedge (a persistence failure while a carrier is pending) is stated, not fixed.

### Inputs read (Read/Grep only, known checkout and context paths)

- `AGENTS.md`, `CLAUDE.md`.
- `sv016-context/SV-013-user-uploaded-dossier-2026-10-07.md` §2.2.1–§2.2.5, §2.2.9.
- `SV-015-integrated-apparatus-closure-v2.md` §1.1–§1.4, §4.1–§4.2, §5.5–§5.8.
- `SV-027-bounded-targets.json` (runner and limits).
- `docs/planning-context/sv023/` (STATUS, ASTRA-ACCEPTANCE) and `sv027/` (STATUS, ASTRA-ACCEPTANCE, DESIGN head); grep over the sv021–sv027 planning context.
- `services/chassis_startup.py` (whole), `chassis_persistence.py`, `chassis_session.py`, `chassis_replay.py`, `chassis_gc.py`, `chassis.py` (relevant ranges).
- `tests/test_chassis_acknowledgements.py`, `tests/test_chassis_recovery_live.py` (relevant ranges).

### Execution log and deviations

- No shell command, test, runner, Python, import, install, Git operation, subagent, provider, real session, credential, raw log, original checkout, account or settings action.
- No operation was denied.
- The parent task root and the results directory were not searched. The runner path in DESIGN §11.5 is quoted from `SV-027-bounded-targets.json`, not visited.
- Filigree was not used: its earlier read-only store failure stands; no retry, init, repair or claim.

**Stopping here for independent Astra review.** Implementation needs an accepted design and a separate reviewed prompt.
