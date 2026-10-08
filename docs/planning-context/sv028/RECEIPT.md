# SV-028 implementation receipt (Opus 5.5 worker)

## Correction 1 (SV028-09, SV028-10): implemented and tested; awaiting independent immutable Astra re-review. Not accepted.

**Inputs**
- Review-archive base: `78180860cdba9e1afc68abb228a81981fbed379b`.
- Governing review: `ASTRA-IMPLEMENTATION-REVIEW.md` (SHA-256 `2cba8bda…12b2a`, as supplied).
- Targets: `sv016-context/SV-028-correction-1-bounded-targets.json`.
- The design acceptance's L1–L7 continue to govern.
- All archived reviews are unchanged.

### Changes

| File | Change |
|---|---|
| `services/chassis_startup.py` | **SV028-09:** in `_recover`, a preserving recovery projects `extra` onto its *logical* records, excluding `LEDGER_HEADER`, for the comparison with `Π + T`, the "nothing beyond the core" check, the remaining-core slice and `after_core`. `_preserving_decision`'s carrier-free completeness check uses the same projection. Every physical record, headers included, is still validated by the strict scan, replayed (charged) once and synced through `extra`. Every other mechanism keeps `logical = extra`, exactly as before.<br>**SV028-10:** new `_refuse_late`, which names the stage and what is kept ("…the transaction stopped while copying: the published inventory and the copies already made are kept; no carrier was published, nothing was activated, and STOPPED, the ledger and the live conversation are untouched"). It is used by `_copy_entry`'s hash mismatch and, through `_read_source(..., late=True)`, by every copy-time read refusal (missing, over the bound, read error). Pure-admission and old-pair refusals keep `_refuse` ("…; nothing was changed"). The `AcknowledgementRefused` docstring is corrected |
| `tests/test_chassis_bootstrap_preserving.py` | **New node** `test_sv028_an_own_torn_header_preserves_the_logical_recovery_plan[uninterrupted\|header-only-restart\|carrier-retired-restart]` with a new fixture option `empty_successor` (a cut in the real `LedgerWriter.rotate_if_full` at its header write).<br>**Strengthened** `test_sv028_a_source_change_during_copy_keeps_the_published_inventory_and_prior_copies` with retained-prefix message assertions and missing, over-limit [injected 4-byte bound] and injected-EIO read companions at the same boundary.<br>**N4a** now asserts that each pure-admission refusal ends with "nothing was changed".<br>`snapshot_unchanged` returns the message |
| docs | this section, STATUS, a DESIGN note |

No other runtime or test file changed. `services/chassis.py` and `tests/test_chassis_acknowledgements.py` are untouched in this correction.

### Pre-fix (unchanged runtime = the reviewed implementation; test changes only; one node per command)

| # | Node | Result |
|---|---|---|
| 1 | `…[uninterrupted]` | **passed** (the control) |
| 2 | `…[header-only-restart]` | **failed as predicted**, at `assert (opening.classification, opening.stop) == ("BP", None)`, with actual `Opening(classification='intent', stop='recovery_intent_mismatch', detail={'seq': 17})`. seq 17 is the replacement header |
| 3 | `…[carrier-retired-restart]` | **failed as predicted**, at the same assertion, with actual `recovery_intent_mismatch`, `{'problem': 'a retired activation must already be complete'}` |

**Setup facts asserted before each failure:**
- the real writer left an empty successor;
- the witness has `end_segment == last_segment + 1` and `end_offset == 0`, and is valid for an actual A14 stop;
- the empty file is inventoried;
- a strict 70-byte prefix of the genuine next header classifies TC1;
- after the first start, exactly one durable replacement header and RECOVERING are present;
- header-only: no logical record yet, carrier held;
- carrier-retired: carrier absent, logical `Π + T` present, conversation absent.

No setup, API or import failure occurred. The fixtures needed no correction. The earlier B0 and D1–D3 evidence stands and was not rerun.

### Final (after the runtime correction; eleven serial commands)

| Batch | Cases | Result |
|---|---|---|
| F1 | 14 | 14 passed |
| F2 | 1 | 1 passed |
| F3 | 1 | 1 passed |
| F4 | 9 | 9 passed |
| F5 | 10 | 10 passed |
| F6 | 1 | 1 passed |
| F7 | 22 | 22 passed (including the strengthened late-copy node) |
| R1 | 35 | 35 passed |
| R2 | 1 | 1 passed |
| R3 | 14 | 14 passed |
| SV028-09 | 3 | 3 passed |

**Total:** `[14, 1, 1, 9, 10, 1, 22, 35, 1, 14, 3]` = **111 passed** (61 new + 50 retained), with no failures and no reruns. Altogether 14 runner commands were issued in this correction (3 pre-fix + 11 final), each alone, through the approved runner under the unchanged limits.

### What the new evidence shows, and its limits

- **Header node, after correction:**
  - exactly one physical replacement header (seq = witnessed end + 1);
  - logical owned records exactly `Π + T`, with T's `tail_sha256` and byte count those of the original fragment and `declared_type "01"`;
  - the fragment is kept in `corrupt/`;
  - epoch e+1 once, and the §11 state and next label;
  - no request or tool effect;
  - carrier and RECOVERING retired;
  - the independent inventory is preserved byte-exactly as new inodes;
  - a later ordinary restart (A12t) writes nothing.
- **Late-copy node:** at the late boundary (MANIFEST and the STOPPED copy already exist, as asserted at the moment the fault is injected), each of the four conditions refuses with its token and the retained-prefix message, never "nothing was changed". There is no carrier, receipt or live-conversation change, and the prefix stays. A retry is a pure admission and keeps "nothing was changed".
- **Not claimed:** RSS, aggregate reads, numerical replay bounds and kernel power-loss behaviour remain unproved, as before. Old mechanisms were not changed to treat headers logically. SV023's witnessed path keeps its prior behaviour, verified by the 36 retained acknowledgement nodes.
- **Provenance:** Read/Grep/Write/Edit plus the approved runner only. No Git, Python, install, subagent or reviewer. No denial. Filigree not used.

**Stopping for the coordinator's commits/backups and independent Astra re-review.**

---

# Implementation round (history)

**Status:** implemented and tested within the frozen bounded matrix; awaiting the coordinator's commit/backup and an independent immutable Astra review. **Not accepted.**

## Inputs and scope

- **Base:** committed `a70620ae0c496276864e1da20179f88d0c9d3e2b`.
- **Governing review:** `ASTRA-DESIGN-ACCEPTANCE.md` (SHA-256 `5228c567…4171f`, as supplied), whose L1–L7 qualifications govern. Also used: `sv016-context/SV-028-bounded-targets.json` and `SV-028-prior-assertion-baseline.md`.
- **Implemented:** exactly the admitted pair (`conversation_unreadable_unbound` + `bootstrap-preserving`, W1) and the complete truthful registry. Every other pair and reason (including TC4) is still refused with the existing "not implemented" message.

| File | Change |
|---|---|
| `services/chassis_startup.py` | • **Registry:** `RESOLUTION_MECHANISM` with exact subsets.<br>• **`acknowledge`:** mechanism dispatch and `home_dir`.<br>• **`read_carrier`:** `preserving` kind.<br>• **Phase A:** domain, inventory/MANIFEST, lifecycle, ownership, capacity, `E`, seal, carrier.<br>• **Phase B:** `preserving_verification` (B0, with L2's preserved-stop binding), the BP decision (`Π[k:] + T`), B3 `_establish_owned_durability`, B4 `_complete_preserving`, the carrier-free `preserving_from_context`.<br>• **Intent context:** the preserving four-key context in `witnessed_context_problem` and the intent body.<br>• **Docstring.** |
| `services/chassis.py` | the CLI passes `home_dir=chassis.home_dir` (one call site, plus a comment) |
| `tests/test_chassis_bootstrap_preserving.py` | **new**, 58 nodes |
| `tests/test_chassis_acknowledgements.py` | only the reviewed `SUPPORTED` tuple, `(A14, "bootstrap-preserving")`, with a comment |
| docs | `DESIGN.md` (governing header plus L3/L7 wording), `STATUS.md`, this file. Both archived reviews and the acceptance are unchanged |

No other runtime or test file was edited. No assertion was weakened.

## Commands (actual, serial, one per message)

The runner was `python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <literal manifest targets>`, under the unchanged limits. It stops at the first failure.

| # | Run | Runtime | Result |
|---|---|---|---|
| 1 | B0 `test_c_k3_a12_a_deleted_list_is_a_clean_slate_with_everything_kept` | unchanged | **1 passed** (as predicted) |
| 2 | D1 `…starts_exactly_one_new_epoch[run-end]` | unchanged | **failed as predicted**: the fixture built a real witnessed A14 stop; `ctx.acknowledge()` raised `LedgerError: 'bootstrap-preserving' for 'conversation_unreadable_unbound' is not implemented` |
| 3 | D2 `…every_envelope_refusal_names_its_reason_and_changes_nothing` | unchanged | **failed as predicted**: the first case (`suffix-partial-turn`) built its fixture and failed at `pytest.raises(match="suffix_not_neutral")` with the base's "not implemented" message |
| 4 | D3 `…cli_bootstrap_preserving_behind_the_first_request_barrier` | unchanged | **failed as predicted**: a real run stopped with exit 44 and a valid witness; the CLI returned **2** ("acknowledgement refused: … not implemented") at `assert ack.returncode == 0` |
| 5 | F1 (14) | changed | 14 passed |
| 6 | F2 N6[process-death] | changed | 1 passed |
| 7 | F3 N6[host-loss] | changed | 1 passed |
| 8 | F4 (9) | changed | 9 passed |
| 9 | F5 (10) | changed | 10 passed |
| 10 | F6 N11 (real CLI) | changed | 1 passed |
| 11 | F7 (22), first attempt | changed | 16 passed, **1 failed** (`N19[sealed-after-rename-fence]`), 5 not run (runner stops at the first failure). See below |
| 12 | F7 (22), after the fixture fix | changed | **22 passed** |
| 13 | R1 (35 retained) | changed | 35 passed |
| 14 | R2 (retained SV023 CLI) | changed | 1 passed |
| 15 | R3 (14 retained) | changed | 14 passed |

**Final:** `[14, 1, 1, 9, 10, 1, 22, 35, 1, 14]` = **108 passed** (58 new + 50 retained) in ten final batches, plus four pre-fix commands. No broader selection and no full-file run was made. No final batch was repeated except F7, after its failure.

All D1–D3 failures were behaviour failures with complete setup: no import, arity or collection error. The new module imports only accepted test helpers, and the tests call the command with its unchanged signature (the `HomeRoot` production layout makes the default home correct).

## The one failure and its fix (test fixture only)

`N19[sealed-after-rename-fence]` builds its "sealed, before the carrier" state by crashing at the first `open` of a file whose name starts `.ACKNOWLEDGED.`. In the planted fixture, the pre-existing `session/.ACKNOWLEDGED.0123456789abcdef.tmp` is evidence: it is inventoried and copied. `E` opens its copy read-only to fsync it, before the seal, and that `open` matched first. The crash therefore happened inside `E`, so the precondition `assert ctx.sealed.is_dir()` failed correctly.

The runtime behaved as specified: the temp-shaped file was inventoried and its copy fenced. The fix narrows the predicate to the carrier's own temp: `Path(path).parent == ctx.session_dir`. The edit is confined to that test's lambda. The 16 F7 cases already passed and F1–F6 do not execute it, so those were not rerun; the whole F7 batch was rerun (22 passed).

## How L1–L7 and the mutation obligations are exercised (inside the named nodes)

**L1**
- `test_sv028_a_readable_inherited_inventory_is_established_before_archive_mutation`:
  - P1 dies after the MANIFEST rename and before its fence;
  - P2 (carried pending names) logs `fsync(MANIFEST)` and `sync_dir(partial)` before any child `mkdir` or unlink;
  - a second death before the establishment returns, followed by host loss, loses the inventory; nothing was created and the retry converges;
  - a death right after the establishment, followed by host loss, keeps the inventory byte-identical and converges.

**L2**
- N1 ×3 runs Phase B with live STOPPED absent.
- N9 `preserved-stop-binding`: the preserved STOPPED is replaced with its MANIFEST entry and the carrier digest made consistent. The start stops `acknowledgement_unverified` with a `stop_binding` problem, and nothing is activated.

**L3**
- `…late_phase_a_io_failure_preserves_the_completed_prefix[seal-fence|carrier-fence|stop-retirement-fence]`: EIO at each exact fence. The asserted prefix is (sealed set, no carrier, STOPPED) / (sealed, readable carrier, STOPPED) / (sealed, carrier, no STOPPED). Only marker operations and the helper's temp cleanup follow the failure. The live conversation and evidence are intact, and the marker is present.
- `…a_source_change_during_copy_keeps_the_published_inventory_and_prior_copies`: the source changes after the STOPPED copy and before the agent-notes copy. The command refuses `preserved_source_changed`; the inventory and the earlier copies are kept; there is no carrier and no activation; a retry refuses unchanged.
- N16 `eio-before-seal`: no seal, carrier or STOPPED removal; the conversation is intact; the marker is present; the retry refuses `transaction_open`.

**L4**
- N19 ×3 (complete-partial, reverted rename, sealed): at caps equal to the measured `U`, there is no `O_CREAT` or write under `preserved/` and usage equals `U` after every call. At `U_bytes − 1` and `U_files − 1` the command refuses, unchanged, by executing the capacity predicate on the post-boundary and **sealed** branches.
- N15 `cap-boundary` includes the L4 extension:
  - `U > cap` with two owned temps;
  - both deletions precede the first allocation, and usage falls monotonically until then;
  - every post-allocation sample is ≤ cap;
  - the observed peak = `max(U, F)` = `U`.
- N15 `repeated-copy-temp-crashes` and `rewrite-peak`: samples are never above the computed peak, and a mismatching destination is deleted before its replacement's temp.

**L5**
- N4a has 22 cases and N4b has 10 shapes plus the damaged sealed set and the unowned scratch, as in the baseline (refusals change nothing).
- N18 ×10: missing gives `preserved_source_missing`, added gives `preserved_domain_changed`, changed gives `preserved_source_changed`.

**L6**
- N17 covers four model controls: a fenced ancestor rename loses an unfenced child; a fenced child survives; an unfenced rename is reversed with the child re-resolved under the old path; and a removed unfenced directory is not resurrected.
- N16 `omit-reuse-fence-mutation`: P1 dies after the corrupt copy's rename and before its leaf fence. P2 takes the reuse branch (the log shows no create, write or rename in that leaf). With `E` patched to skip that leaf's fsync, P3 completes activation. Before host loss the pending name resolves under the **sealed** path; after host loss the reused entry is missing under the sealed name. In the unmutated control (`reused-leaf-converges`) it survives.

**L7**
- Wording updated in DESIGN (§7.2, §7.4, §13, §15) and STATUS.

**Mutation controls.** Each was run inside its pytest node, and each node passed because the protecting assertion **failed** under the mutation:

| Mutation | Observed under the mutation |
|---|---|
| hard-linked copies | the live segment append changed the "preserved" segment |
| neutral-suffix check removed | a message suffix was activated and its memory dropped (the refusal no longer happened) |
| B3 removed | the N7 activation-readable trace no longer converges: the activation was lost while the conversation was gone |
| plan derived after owned records | the spend-readable trace stops `acknowledgement_unverified` with `own_prefix` |
| omitted reuse fence (N16) | the reused entry is lost under the sealed name |

No mutation was applied to a source file; all were monkeypatches restored by pytest.

## Limits (unchanged by this implementation; not claimed)

- **RSS is unproved.** Phase A and Phase B hold all segment bytes, the parsed scan, replay states, one file or set entry at a time (≤ 64 MiB) and the inventory.
- **Aggregate reads are not bounded.** A fresh Phase A reads the domain twice; Phase B reads the sealed set once.
- **Capacity** is an admission rule over measured logical sizes, not a quota.
- **M-2 is simulated** by the test harness. No kernel or power-loss behaviour is claimed, and nothing is claimed after an fsync error (E-K2).
- **Inherited fail-closed outcomes:**
  - a Phase A or Phase B persistence failure leaves FSYNC_FAILED (best-effort) and a stopped session (SV023-02 class);
  - after a post-boundary mismatch the acknowledgement cannot complete while the fixed-inventory checks fail;
  - carrier-write temps can accumulate.
- **M-6 is out of model.**
- **No real-session** acknowledgement, deletion or resumption. No provider, merge or deployment. No numeric replay, segment or read bound. No held H/T/Q/pump/history choice.
- **Hashes not recorded here.** Hashing is outside the permitted tool set; the coordinator's immutable commit identifies the bytes.

## Execution provenance

- Read/Grep/Write/Edit on known checkout and context paths, plus Bash only through the approved runner with literal manifest targets, one command per message.
- No Git call, Python, install, subagent or reviewer.
- No operation was denied.
- Filigree not used.

**Stopping for the coordinator's commit/backup and independent Astra review.**
