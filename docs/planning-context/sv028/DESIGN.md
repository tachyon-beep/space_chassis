# SV-028 design (correction round 2): one narrowly admitted `bootstrap-preserving` acknowledgement

## Governing implementation qualifications (accepted design; implemented, awaiting independent review)

Astra accepted this architecture at design head `8e30cf86` ([ASTRA-DESIGN-ACCEPTANCE.md](ASTRA-DESIGN-ACCEPTANCE.md)), subject to mandatory L1–L7. These supersede conflicting prose below.

| Id | Qualification | Where implemented |
|---|---|---|
| L1 | A post-boundary retry explicitly re-establishes the readable inherited MANIFEST before any cleanup, child `mkdir` or copy: `fsync(MANIFEST)`, then `fsync` of the partial set, `preserved/` and `session/`. The inventory is never rewritten | `_establish_inventory` |
| L2 | Phase B binds the stop through the **preserved** `session/STOPPED`, never the removed live one: membership, size/hash, parsed reason and witness, recomputed `stop_sha256`/`stop_id`/`ack_id`, then the full inventory binding. The carrier-free route stays self-contained | `preserving_verification` |
| L3 | Failures describe their completed prefix:<br>• pure admission refusals write nothing;<br>• a later refusal keeps the inventory and the copies made so far;<br>• a persistence failure attempts the best-effort marker and stops further steps;<br>• a pre-seal `E` failure never seals or publishes;<br>• Phase A never touches the live conversation | §7.4 / §8.3; `_acknowledge_preserving` |
| L4 | Exact capacity on **every** lifecycle branch before any mutation: `F = U − D + A`; invocation peak `max(U, F)`; verified owned cleanup may reduce pre-existing over-cap usage | `_acknowledge_preserving` P13 |
| L5 | Finite fixtures from the immutable assertion baseline, overridden by correction 2. Diagnostic precedence: missing source, then added path, then changed bytes | `_verify_sources` |
| L6 | The namespace model re-resolves directory identities after every undo and never resurrects descendants of a removed directory | `PreserveOps` / `host_loss_names` (test harness) |
| L7 | "cannot complete while the fixed-inventory checks fail"; the marker is best-effort; the steps are A1–A8 plus the L1 fence | §7.2, §7.4, §13 |

**Implementation calibrations** (engineering choices made while implementing; nothing semantic changed):
- **Phase A ordering.** P1–P10 run first, then the preserved/ usage walk and the lifecycle, then the branch's inventory work, then P14 and P13. All of this is pure and precedes every write.
- **Phase A persistence failure.** It attempts `FSYNC_FAILED`, as v2 §1.4.9 requires for any session sync error.
- **Phase B B0 ordering.** The owned-prefix check precedes the evidence-equality check, so a plan mismatch reports `own_prefix`.
- **Refusal tokens.** These are the leading words of each `AcknowledgementRefused` message.

See [RECEIPT.md](RECEIPT.md) for the evidence.

---

**Historical status line (round 2): corrected design only, for independent Astra re-review. Not implemented. No test was run. No runtime or test file was changed.**

This is a standalone proposal that replaces correction round 1. The governing reviews are preserved unchanged:
- [ASTRA-INITIAL-DESIGN-REVIEW.md](ASTRA-INITIAL-DESIGN-REVIEW.md) (SV028-01…05);
- [ASTRA-DESIGN-CORRECTION-1-REVIEW.md](ASTRA-DESIGN-CORRECTION-1-REVIEW.md) (SV028-06…08).

The finding map is in [STATUS.md](STATUS.md).

**What stays and what changes.**
- **Unchanged from round 1, as the residual review accepted:** activation durability (B3 before B4), the frozen plan Π and the sealed carrier-free context, the six-pair registry, and the A12-compatible E1+S1+R1+N1 semantics.
- **Changed in this round, archive transaction only:**
  - the MANIFEST is now the **durable inventory**, written before any copy and never rewritten (SV028-07, -08);
  - an explicit **dependency-establishment** step precedes the seal (SV028-06);
  - a verifiable **ownership rule** for scratch replaces the blanket `.ACKNOWLEDGED.*.tmp` exclusion (SV028-08);
  - capacity uses **exact deltas** (SV028-07);
  - the `PreserveOps` model tracks pending names by **directory identity** (SV028-06);
  - the test matrix is re-frozen.

## Provenance

- **Base:** `05cc4f8616c108855246c8c8ea13a571eb9731c8`. The residual review's SHA-256 is recorded as supplied (`64d83771…5a14`) and not recomputed, since hashing is outside the Read/Grep/Write/Edit tools.
- **Canonical text:**
  - SV-013 §2.2.2 (files, CK1–CK6, the authority rule, A0–A15, l.558) and §2.2.5;
  - SV-015 v2 §1.1–§1.4 (M-1…M-6; framing; tails; checkpoint, GC and transitions; §1.4.8 strict pre-admission; §1.4.9 FSYNC_FAILED honesty).
- **Accepted local evidence:** `sv023/`, `sv024/`, `sv026/`, `sv027/`.
- **Code:** `services/chassis_startup.py`, `chassis_persistence.py`, `chassis_session.py`, `chassis_replay.py`, `chassis_gc.py`, `chassis.py`.
- **Tests:** `tests/test_chassis_acknowledgements.py` (`AckOps`, `host_loss`), `test_chassis_gc.py` (`CutOps`, `begin`, `start`), `test_chassis_recovery_live.py` (`Root`, helpers).

---

## 0. The proposal in brief

**One pair is admitted:** `conversation_unreadable_unbound` + `bootstrap-preserving`. The stop must carry a valid SV023 witness, and the records after the witnessed newest checkpoint `C_n` must be state-neutral. Everything else stays refused.

**Phase A (the operator command):**
1. Runs a pure admission over an exact preservation domain: every regular file of `session/` (excluding `preserved/`) plus the named `HANDOFF.md`. Unsupported shapes are refused.
2. Publishes a sealed, checksummed **inventory** (`MANIFEST`) into an owned `preserved/<ack_id>.partial/`. This is the **durable snapshot boundary**.
3. Copies each inventoried file as independent bytes.
4. **Establishes every file-data and name dependency** of the set, whether a copy is new or reused.
5. Seals the set by renaming it to `preserved/<ack_id>/` and fencing. The sealed set is immutable.
6. Publishes the sealed carrier, then removes STOPPED.

**After the boundary:**
- a changed, missing or added live source refuses;
- only files proven to be transaction-owned scratch, which cannot be the only original, are ever deleted;
- the manifest is never rewritten.

**Phase B (the consuming start), unchanged from round 1:**
1. Verifies the carrier and the sealed set.
2. Derives a frozen plan Π from the witnessed head: receipt, optional `possible_duplicate_spend`, one activation `EXTERNAL_DELETE{epoch: e+1, cause: "bootstrap_preserving", …}`.
3. Appends only the missing continuation.
4. **Establishes owned durability (B3)**.
5. Only then unlinks the preserved unreadable `conversation.json`.
6. Retires the carrier, then any intent.

The duty-visible behaviour is exactly A12's.

---

## 1. Canonical facts

| Source | Text (abridged; quoted where exact) | Used for |
|---|---|---|
| SV-013 §2.2.2 l.558 | "`bootstrap-preserving` keeps every file and starts epoch+1; it is the operator's explicit choice, never automatic." | Same lineage; epoch +1 once; preservation; operator act |
| SV-013 §2.2.2 files table | the session files, including `corrupt/` and **`HANDOFF.md` (home)** | Preservation domain (§7.1) |
| SV-013 authority rule | "An unreadable file is never treated as absent … nothing bootstraps over memory that may exist." | The live name is removed only after preservation and durable activation |
| SV-013 A12 | "`EXTERNAL_DELETE{epoch+1}`; bootstrap; `prev` and ledger preserved" | E1 precedent |
| SV-013 §2.2.5 r.3 / v2 §1.4.3 | watermark "never reset" | Notes carried (N1) |
| v2 §1.1 | M-1 process death; M-2 honest host loss (bytes after the last returned fsync and names after the last returned directory fsync may be lost); M-3 checksum-only detection; M-5 single writer; M-6 out of model | Crash model (§10, §14.1), dependency fences (§7.4), snapshot boundary (§7.2) |
| v2 §1.3 | own-torn TC1 rule; TC4 names `bootstrap-preserving` as an alternative | Composition (§9.4); TC4 **not** admitted |
| v2 §1.4.5 | GC removes only intent-named items | GC exclusion (§12) |
| v2 §1.4.8 | strict pre-admission caps | Capacity (§7.5) |
| v2 §1.4.9 | on a sync error: `PersistenceFailure`, a best-effort FSYNC_FAILED marker, and "if the marker exists, the next start stops. No stronger claim" | Phase A EIO behaviour (§8.3) |

---

## 2. Accepted runtime facts this design depends on

- `bootstrap-preserving` is refused today for every reason ("not implemented … nothing was changed", `chassis_startup.py:246–247`). The allowlist `IMPLEMENTED_RESOLUTIONS` is at `:101–106` and `WITNESSED_RESOLUTIONS` at `:96–99`. They are consulted by `read_carrier` (`:290–303`), `carrier_problem` (`:506`) and `witnessed_context_problem` (`:1529`).
- The A14-unbound stop and its witness: `:1271–1274`; `stop_witness` (`:409–454`).
- **Witnessed own-prefix and intent mechanics:**
  - `witnessed_evidence` (`:539–681`) and `_next_own_frame` (`:684–694`);
  - a RECOVERING `witnessed` context (`:1055–1058`, `:1515–1537`);
  - an own tear under an existing intent is set aside with no record (`:1070–1078`);
  - extras must be a prefix of the core (`:1085–1094`).
- `derive_core` (`:1587–1642`) emits the spend for `failed_unknown`. Applying it changes `requests.last.outcome` (`chassis_replay.py:606–616`).
- **`write_bytes_durable`** (`chassis_persistence.py:967–991`) writes in this order:
  1. creates an `O_EXCL` temp `.<name>.<16 hex>.tmp` next to the target;
  2. writes all bytes;
  3. **fsyncs the file**;
  4. renames the temp onto the target;
  5. fsyncs the directory.

  On `OSError` it unlinks its temp. A final name it creates therefore exists only after that file's data fsync returned. The new temp coexists with any existing target until the rename.
- **Later ordinary operation replaces or removes:**
  - CK3/CK4 replace `conversation.json` and `.prev.json`, removing `.prev.tmp`;
  - CK5 replaces `run.json`;
  - `reserve_turns` replaces IDENTITY;
  - `append_recap` replaces `recap.md` (`chassis.py:275–285`);
  - `write_note` replaces the HANDOFF mirror (`chassis_session.py:476–482`);
  - GC unlinks segments and blobs;
  - quarantine rewrites a deterministic `corrupt/` destination (`chassis_persistence.py:1457–1481`, `chassis_startup.py:210–226`).
- `_retained_prev` (`chassis_session.py:610–625`) keeps and names any known checkpoint found in `.prev.json`.
- The production layout is `session_dir = home_dir / "session"` (`chassis.py:610–612`).

---

## 3. Scope

| # | Stop | Decision | Missing semantics (not guessed) |
|---|---|---|---|
| **W1** | `conversation_unreadable_unbound`, valid witness, state-neutral suffix after `C_n` | **Admitted** | — |
| W2 | same, any non-neutral record after `C_n` | refused (`suffix_not_neutral`) | Suffix-only memory; open-group closure before a base switch |
| W3 | same, no witness | refused ("no valid witness") | A witness for those shapes |
| C1 | `run_json_unreadable` | refused (not implemented for this resolution) | Bootstrapping over a bound, readable conversation |
| T1 | `ledger_tail_ambiguous` | refused | No note-generation reservation; hidden epoch steps |
| L | A7, A15, A2, `ledger_prefix_missing`, `ledger_unreadable`, A6, `run_json_missing`, integrity and transaction stops, `fsync_failed_previous_run`, `corrupt_quarantine_full`, `acknowledgement_unverified` | refused | No proven predecessor state, lineage, epoch or witness |

**State-neutral** means every record with `seq > C_n.seq` is in `NEUTRAL = {LEDGER_HEADER, RUN_END, GC_INTENT, GC_DONE}`, with no pending intent. The request-identity bound is the checked IDENTITY equal to the witness, never a turn maximum read from a clean ledger.

---

## 4. One truthful resolution registry (unchanged from round 1)

```python
RESOLUTION_MECHANISM = {
    ("ledger_tail_ambiguous", "continue-conservative"): "tail",
    ("fsync_failed_previous_run", "continue-from-bound"): "plain",
    ("corrupt_quarantine_full", "continue-from-bound"): "plain",
    ("conversation_unreadable_unbound", "continue-from-bound"): "witnessed",
    ("run_json_unreadable", "continue-from-bound"): "witnessed",
    ("conversation_unreadable_unbound", "bootstrap-preserving"): "preserving",
}
IMPLEMENTED_RESOLUTIONS = frozenset(RESOLUTION_MECHANISM)             # the complete union: 6 pairs
WITNESSED_RESOLUTIONS = {p for p, m in RESOLUTION_MECHANISM.items() if m == "witnessed"}    # unchanged, 2
PRESERVING_RESOLUTIONS = {p for p, m in RESOLUTION_MECHANISM.items() if m == "preserving"}  # 1
STOP_WITNESS_RESOLUTIONS = WITNESSED_RESOLUTIONS | PRESERVING_RESOLUTIONS
WITNESSED_REASONS = {r for r, _ in STOP_WITNESS_RESOLUTIONS}          # unchanged: {A14, CK5}
```

- `acknowledge` checks the union first (unimplemented pairs keep today's exact message), then dispatches by mechanism.
- `read_carrier` and `witnessed_context_problem` check the envelope and context key set of each mechanism.

**The one reviewed existing-test change.** `tests/test_chassis_acknowledgements.py:56–62` `SUPPORTED` gains `("conversation_unreadable_unbound", "bootstrap-preserving")`. Then:
- `:494` holds;
- `:495` is unchanged;
- the loop skips the new pair;
- `refused == 25 × 3 − 6 = 69` (previously 70).

The removed in-loop refusal is replaced by N4a's `conversation_readable` case.

---

## 5. The frozen plan Π (unchanged from round 1)

### 5.1 Derivation (pure; from the witnessed head `H` = the records `≤ W.last_seq`)

1. `C_n` is the newest CHECKPOINT in `H` and equals the witness tuple. `state0 = SessionState.from_wire(C_n.state)`. Every record after `C_n` in `H` is in `NEUTRAL`.
2. `R0 = Replay([], state0.copy())`, with `group = None`.
3. `spend = derive_core(R0, plan_recovery(scan_H, TC0), TC0, scan_H, None, lineage, identity_reserved=W.identity)`. It must be `[]` or exactly one `RECOVERY{possible_duplicate_spend}`; anything else refuses (`plan_unexpected`).
4. `activation = ("EXTERNAL_DELETE", {"epoch": e+1, "notices": [], "cause": "bootstrap_preserving", "ack_id", "manifest_sha256"})`, with `e = state0.history_epoch`.
5. `C = [*spend, activation]`; `continuation_sha256 = sha256(canonical_body({"continuation": C}))`.
6. **Π = [("RECOVERY_ACK", receipt), *C]**, with `receipt = receipt_payload(carrier)`. The receipt names `evidence_sha256`, and the evidence names `continuation_sha256`, which excludes the receipt, so the definition is not circular.

Π is computed once per start from `H` alone, **before** any owned record is applied, and is never re-derived from a replay that applied owned records.

### 5.2 Owned records

`LEDGER_HEADER`s after `W` are physical. The logical owned sequence `O` (non-header records with `seq > W.last_seq`) must be `Π[:k]`, or `Π + T` under an intent (§9.4). Each owned record is applied once to the decision replay. The continuation `Π[k:]` (+ `T`) is committed by `Session._commit`.

### 5.3 Carrier evidence (fixed keys, bounded)

```json
{"witness_check", "manifest_sha256", "conv_sha256", "conv_bytes", "run_sha256",
 "state_sha256": "sha256(canonical(state0.to_wire(next_seq=W.last_seq+1)))",
 "suffix": {"count": n, "types_sha256": "<64 hex>"}, "continuation_sha256", "epoch": e+1}
```

The carrier is `{reason, resolution, ack_id, witness, evidence, check}`.

### 5.4 Sealed carrier-free context

`RECOVERING.witnessed` for this pair is `{"ack_id", "receipt", "after_seq", "evidence"}`. Validation, inside the existing whole-intent checksum and domain checks:
1. key sets are exact;
2. `receipt.ack_id == ack_id`;
3. `sha256(canonical(evidence)) == receipt.evidence_sha256`;
4. `after_seq ≤ intent.last_seq`.

Carrier-free authentication re-derives Π from `H`, `ack_id`, `evidence.manifest_sha256` and `receipt`, and requires:
- `continuation_sha256` matches;
- `state0`'s digest equals `evidence.state_sha256`;
- `e+1 == evidence.epoch`.

Otherwise it stops `recovery_intent_invalid`.

### 5.5 Domains and exact serialization (preflighted before any write)

- **Counters:**
  - `e+1 ≤ MAX_COUNTER`;
  - `W.last_seq + |Π| + 1 + 2 ≤ MAX_SEQ`.
  - Otherwise refuse `plan_out_of_domain`.
- **Exact bytes:**
  - the canonical `MANIFEST` ≤ `MANIFEST_READ_MAX = META_READ_MAX` (1 MiB) → `preserved_manifest_too_large`;
  - the carrier ≤ `MAX_MARKER_READ` → `carrier_too_large`;
  - the maximal RECOVERING with this context (`segment = 999999`, offsets 10¹²−1, 64-hex hashes) ≤ `MAX_MARKER_READ` → `recovery_context_too_large`.
- **Retry with an existing MANIFEST.** Its exact bytes are what was published. They are re-read under `MANIFEST_READ_MAX` and never re-serialized for writing. The carrier and context checks still run.

---

## 6. Phase A admission (pure; refusal changes nothing)

`acknowledge(session_dir, reason, resolution, *, ops=None, home_dir=None)`:
- `home_dir` defaults to `session_dir.parent` (`chassis.py:610–612`); the CLI passes `chassis.home_dir`.
- Refusals raise `AcknowledgementRefused` (a `LedgerError`; CLI exit 2) with a leading token.

| # | Check | Refusal token |
|---|---|---|
| P1 | STOPPED readable, reason A14, valid witness | `stop_not_acknowledgeable` / "no valid witness" |
| P2 | ACKNOWLEDGED absent or **this** sealed preserving carrier; no RECOVERING; no FSYNC_FAILED | "another acknowledgement is pending" / `transaction_open` |
| P3 | Ledger lineage, strict scan, no tail, anchor and physical end equal the witness; no owned record | `ledger_not_witnessed` |
| P4 | No unauthorized prefix, no pending GC | `collection_pending_or_unauthorized` |
| P5 | `read_identity == witness.identity_reserved` | `identity_not_witnessed` |
| P6 | `C_n` equals the witness; state valid; `blobs_live` hash-verify | `checkpoint_not_witnessed` / `state_blob_missing` |
| P7 | Neutral suffix | `suffix_not_neutral` |
| P8 | `run.json` equals `C_n.run_sha256`; format-2 fields agree | `run_json_not_witnessed` |
| P9 | `conversation.json` present, regular, within `CONVERSATION_READ_MAX`, unparseable as a message list | `conversation_absent` / `conversation_readable` / `conversation_over_bound` |
| P10 | Neither file is `C_n`'s bytes; `_previous_base` returns `(None, None)` (an older known checkpoint in `.prev.json` is allowed) | `previous_base_available` |
| P11 | **Domain** (§7.1): every kind and name supported; every file ≤ `PRESERVED_FILE_MAX`. Read #1 records size and SHA-256 | `preservation_unsupported_shape` / `…_name` / `preserved_file_too_large` |
| P12 | **Own-set state and inventory binding** (§7.2, §7.3) | `preserved_inventory_invalid` / `…_missing` / `preserved_domain_changed` / `preserved_source_changed` / `preserved_source_missing` / `preserved_set_mismatch` / `preserved_scratch_unowned` |
| P13 | **Capacity**, exact deltas (§7.5) | `preserved_capacity:{sets\|files\|bytes}` |
| P14 | Π derivable; domains and exact sizes (§5.5) | `plan_unexpected` / `plan_out_of_domain` / `preserved_manifest_too_large` / `carrier_too_large` / `recovery_context_too_large` |

`ack_id = sha256(STOPPED bytes ‖ "\n<reason>\n<resolution>")[:32]`, as today.

---

## 7. Preservation

### 7.1 Exact domain

The domain is enumerated with `lstat` and without following symlinks; listing stops and refuses at `PRESERVED_MAX_FILES + 1` entries.

| Location | Admitted | Treatment |
|---|---|---|
| `session/` top-level regular files | names matching `NAME = [A-Za-z0-9._:+=@,-]{1,255}`, not `.` or `..` | **inventoried and copied** to `session/<name>`. This includes STOPPED, IDENTITY, run.json, both conversation files, recap.md, unknown names, every temp leftover, and **any `.ACKNOWLEDGED.<16 hex>.tmp` present at the boundary**: a temp-shaped name proves nothing about ownership, so it is ordinary evidence |
| `session/ledger/`, `session/blobs/`, `session/corrupt/` | regular files with `NAME` names; no subdirectories | inventoried and copied |
| `<home>/HANDOFF.md` | absent, or one regular file | inventoried and copied as `home/HANDOFF.md` |
| `session/preserved/` | earlier sets in the §7.3 shapes | **not copied** (no archives inside archives); counted for capacity; never modified |
| `session/ACKNOWLEDGED` | must be absent at the boundary (P2) | — |
| anything else in `session/`: other directories, symlinks, FIFOs, sockets, devices, nested directories, non-`NAME` names; a symlinked or non-regular HANDOFF | — | **refused before any mutation** |

`PRESERVED_FILE_MAX = 64 MiB` [CM].

**Evidence versus transaction artifacts.**
- **Pre-resolution evidence** is exactly the inventory published at the boundary (§7.2).
- **Transaction artifacts** are everything this acknowledgement creates afterwards: the `preserved/<ack_id>…` tree; and, **after the seal only**, `ACKNOWLEDGED` and any `.ACKNOWLEDGED.<16 hex>.tmp` from writing it.
- Because the carrier is written only after the seal's fence returns (A7), no carrier artifact of this transaction can exist while a live-domain comparison is made (those happen only before the seal). No name-based exclusion is used.
- Carrier artifacts created after the seal are never inventoried and never deleted.

### 7.2 The durable inventory: the snapshot boundary

**Publication.** The `MANIFEST` (§7.3) is the inventory. It is written once, at A2:
1. `write_bytes_durable(preserved/<ack_id>.partial/MANIFEST)`;
2. this happens after `<ack_id>.partial`'s own name is fenced in `preserved/`, and `preserved/`'s in `session/`;
3. it is **before** any mirrored subdirectory or copy exists.

**The boundary** is the return of that write's directory fence. Before it there is no enduring snapshot: an admission that dies earlier leaves at most owned `MANIFEST` temps, and the next admission starts afresh. After it, the snapshot is fixed for this `ack_id` and is **never replaced or rewritten**.

**Binding.** The `MANIFEST` binds:
- `ack_id` (from the STOPPED bytes);
- `stop_sha256` (STOPPED's SHA-256);
- `stop_id`;
- `witness_check`;
- `lineage_id`;
- `reason` and `resolution`;
- the sorted entries `(path, bytes, sha256)` and totals.

A SHA-256 `check` seals all other fields. The carrier's `evidence.manifest_sha256` later binds its exact bytes.

**Validation** (every retry before any mutation; Phase B on the sealed set):
1. read the file under `MANIFEST_READ_MAX`;
2. canonical JSON; the seal verifies;
3. version 1;
4. every binding field equals the value recomputed from the current STOPPED and witness;
5. paths match the §7.3 grammar, are sorted and unique;
6. totals agree.

A failure refuses `preserved_inventory_invalid` (corrupt or foreign binding) and changes nothing.

**Lifecycle of the own set** (`<ack_id>` names):

| State | Recognized by | Retry action (only after the full admission passes) |
|---|---|---|
| none | no `<ack_id>*` directory | fresh path (§8.1) |
| **pre-boundary** | `<ack_id>.partial/` with no `MANIFEST`, containing only regular files named `.MANIFEST.<16 hex>.tmp` and no subdirectory | delete those owned temps, `fsync(<partial>)`, then continue at A2 |
| pre-boundary, any other content | — | refuse `preserved_inventory_missing`, unchanged |
| **post-boundary** | `<ack_id>.partial/MANIFEST` validates | §8.2 |
| **sealed** | `<ack_id>/MANIFEST` validates and every entry verifies | §8.2 (sealed branch); never modified |
| sealed but damaged, or both `<ack_id>` and `<ack_id>.partial` | — | refuse `preserved_set_mismatch`, unchanged |

**Ownership rule** (verifiable, bounded). A file under `preserved/<ack_id>.partial/` is **owned scratch** iff all of the following hold:
- its directory is one of the set's fixed directories;
- its name is `.<B>.<16 hex>.tmp`, where `B` is `MANIFEST` (set root only) or the basename of an inventory destination in that same directory;
- its path is **not** itself an inventory destination.

Owned scratch can never be the only original:
- before the boundary, no copy exists, so the only owned files are `MANIFEST` temps, which hold no evidence;
- after the boundary, a copy temp holds bytes read from a live source that **this same admission has just verified** equal to its inventory entry.

A post-boundary retry deletes owned scratch **only after** all live sources verify. Any other unexpected file in the partial tree refuses `preserved_scratch_unowned`, unchanged.

**After the boundary, sources must match the inventory.** A post-boundary retry re-enumerates the live domain and requires:
- the **same path set** as the inventory, else `preserved_domain_changed`;
- every live source exists, else `preserved_source_missing`;
- every live source's bytes hash to its entry, else `preserved_source_changed`.

A source that changed from X to Y therefore refuses. It never replaces an already-copied X, and nothing is deleted. A destination copy whose bytes differ from its entry may be deleted and rewritten **only if** its live source verified in this admission, so the surviving live original is the evidence. A sealed set is never compared with the live domain again (post-seal changes cannot affect it) and is never modified.

The consequence is stated plainly (L7): after a post-boundary refusal, this acknowledgement cannot complete while the fixed-inventory checks fail. There is no durable terminal-refusal marker; an exact restoration of the original source bytes would let them pass, but this package neither performs one nor ever switches to a new snapshot. Its partial set is kept, never deleted, and counts toward capacity. The session stays stopped. The operator may still use `continue-from-bound` after an external repair; SV023's path does not inspect `preserved/`.

### 7.3 Set layout and `MANIFEST` schema

```
preserved/<ack_id>.partial/  or  preserved/<ack_id>/
  MANIFEST
  session/<name> ; session/ledger/<name> ; session/blobs/<name> ; session/corrupt/<name>
  home/HANDOFF.md
```

The fixed directories are the set root, `session`, `session/ledger`, `session/blobs`, `session/corrupt` and `home`. Each subdirectory exists only if some entry needs it, so there are at most 6 per set. Set directory names must match `[0-9a-f]{32}` or `[0-9a-f]{32}\.partial`; any other shape under `preserved/` refuses.

```json
{"version": 1, "ack_id", "reason", "resolution", "stop_sha256", "stop_id", "witness_check", "lineage_id",
 "entries": [{"path": "<grammar above>", "bytes": n, "sha256": "<64 hex>"}, …],
 "totals": {"files": k, "bytes": b}, "check": "<64 hex>"}
```

It is serialized canonically (sorted keys, compact separators).

### 7.4 Dependency establishment `E` and the seal (SV028-06)

**File data.** A destination's final name is created only by `write_bytes_durable`, which fsyncs the file before the rename. A **present** destination therefore had its data fsync return in the process that renamed it. A reused destination still has a **name** that may be unfenced if its writer died before the directory fsync. `E` re-establishes both explicitly; verification by hash establishes integrity, not durability.

**`E(root)`**, where `root` is the partial or sealed set directory being relied on:
1. For every file in the set (`MANIFEST` and every entry): open read-only and `fsync`. This uniformly re-establishes data durability, including for reused files.
2. `fsync` every fixed directory that exists, **leaves first**: `session/ledger`, `session/blobs`, `session/corrupt`, then `session` and `home`, then the set root. This makes every file name, and each subdirectory's name in its parent, durable.
3. `fsync(preserved/)`, which covers the set root's name, then `fsync(session/)`, which covers `preserved/`'s name.

`E` allocates nothing and is idempotent.

**Where `E` runs.**
- **Fresh and post-boundary retry:** after all copies (A5), before the seal.
- **Sealed retry:** again on the sealed tree before the carrier is (re)published.
- Every Phase A invocation that publishes or re-publishes authority therefore has just had `E` return over exactly the set the carrier will name.

**Seal (A6):** `rename(<ack_id>.partial, <ack_id>)`, then `fsync(preserved/)`. The rename moves one entry of `preserved/`. The subtree's entries were fenced inside their own directories by `E`, so they survive the rename.

**EIO.** Any `E`, seal or copy failure follows v2 §1.4.9:
- `PersistenceFailure` is raised;
- FSYNC_FAILED is attempted in `session/` (best-effort);
- the CLI exits 44.

**The transaction stops at the failing step (L3).**
- A **pre-seal** `E` failure never seals, publishes a carrier or removes STOPPED.
- A **late** failure leaves its completed prefix visible:
  - a seal-fence error follows the seal rename;
  - a carrier-fence error leaves a readable carrier;
  - a STOPPED-retirement fence error follows the unlink.
- `write_bytes_durable`'s own temp cleanup and the best-effort marker attempt are the only operations after the failure.
- Phase A never removes the live conversation.
- If the marker's own write returned, later retries refuse `transaction_open` (P2) and starts obey the existing STOPPED/FSYNC_FAILED priorities. The marker's persistence is best-effort, not guaranteed after an arbitrary I/O failure.

This is an inherited bounded fail-closed outcome (the SV023-02 class); no stronger claim is made about a later fsync after an error (E-K2).

### 7.5 Capacity with exact deltas (SV028-07)

The caps are [CM]: `PRESERVED_MAX_SETS = 4`, `PRESERVED_MAX_FILES = 16 384` (regular files, temps included), `PRESERVED_MAX_BYTES = 512 MiB` (logical `st_size`, not block allocation), over all of `preserved/`. Directories are not counted; they are bounded structurally (≤ 6 per set, plus `preserved/`).

Admission measures **actual** usage `U = (U_files, U_bytes)` by an `lstat` walk of `preserved/`, including the own partial set and its leftovers. It then plans:

| Symbol | What | Applies when |
|---|---|---|
| `D` | owned scratch to delete, plus mismatching destinations to delete (each with its live source verified) | post-boundary retry, or pre-boundary `MANIFEST` temps |
| `A_M` | `(1, len(MANIFEST))` | only when the `MANIFEST` is **absent** (fresh or pre-boundary). An existing valid `MANIFEST` is reused and never rewritten: `A_M = (0, 0)` |
| `A_C` | `(1, entry.bytes)` per destination absent or deleted under `D`; `(0, 0)` per reused verified destination | always |

**Order.**
1. All deletions first, each directory fsynced after its unlinks.
2. Then allocations only. Each allocation is one `write_bytes_durable` whose temp exists only while its target is absent, so there is no double-holding, and the temp **is** the file it becomes.
3. `E` and the seal allocate nothing.

Usage is therefore at most `U` during deletions and non-decreasing afterwards, so the transaction's allocation peak is the final usage:

```
peak_files = U_files − D_files + A_M.files + Σ A_C.files
peak_bytes = U_bytes − D_bytes + A_M.bytes + Σ A_C.bytes
sets       = |distinct set ids present| + (1 if no own set exists)
```

**Admission** requires `peak_files ≤ MAX_FILES`, `peak_bytes ≤ MAX_BYTES` and `sets ≤ MAX_SETS`, with equality allowed. Otherwise it refuses with nothing deleted or written.

- An existing `U` above a cap is never increased: deletions only reduce it, and an allocation is admitted only if the final usage fits.
- A complete post-boundary partial set or a sealed set gives `D = A = 0`, so `peak = U`. **It is accepted at `cap = U` and allocates nothing** (no temp, no write) before `E` and the seal.
- A failed `write_bytes_durable` unlinks its own temp. A process death leaves at most one in-flight temp, which the next admission counts in `U` and deletes as owned scratch (counted in `D`), so scratch does not accumulate across retries.
- This is an admission rule over measured usage, not a quota. M-6 can exceed it.
- The carrier and its temps live in `session/` (< 3 KiB each, outside these caps). Carrier-write deaths can accumulate such temps, inherited as with SV023.

---

## 8. Phase A transaction

### 8.1 Fresh path

1. **A0** Admission, P1–P14 (pure; read #1 hashes the domain).
2. **A1** `mkdir preserved/` if absent, then `fsync(session/)`. `mkdir <ack_id>.partial/`, then `fsync(preserved/)`.
3. **A2** **Boundary**: `write_bytes_durable(<partial>/MANIFEST)`.
4. **A3** `mkdir` each needed fixed subdirectory, each followed by `fsync(parent)`.
5. **A4** Copies, in sorted path order:
   - read #2 under the bound;
   - require size and hash equal to the entry, else refuse `preserved_source_changed` (an `AcknowledgementRefused`, not a persistence failure). Nothing is deleted, and later retries refuse by §7.2;
   - `write_bytes_durable(dest)`. **Never `link()`.**
6. **A5** `E(<partial>)`.
7. **A6** **Seal**: `rename(<partial>, preserved/<ack_id>)`, then `fsync(preserved/)`.
8. **A7** Carrier `write_bytes_durable(session/ACKNOWLEDGED)`.
9. **A8** `clear_stop`: unlink STOPPED, then `fsync(session/)`.

### 8.2 Retry (STOPPED present)

Admission P1–P11 and P14 run first, then the §7.2 lifecycle state is identified.

- **none or pre-boundary:** delete the owned `MANIFEST` temps (pre-boundary only), then the fresh path from A1 (its fences re-run).
- **post-boundary (partial with a valid MANIFEST):**
  1. live domain = inventory; every live source verifies;
  2. classify every file in the partial tree:
     - **reuse** (destination equals its entry);
     - **delete** (owned scratch, or a mismatching destination with a verified source);
     - **missing**;
     - **unowned**: refuse.
  3. P13 with `A_M = 0`;
  4. deletions, each directory fsynced;
  5. A3: every needed fixed subdirectory, `mkdir` if absent, **`fsync(parent)` whether or not it existed**;
  6. A4 for missing destinations only;
  7. A5 `E`;
  8. A6 seal; A7; A8.
- **sealed:** validate the `MANIFEST` and every entry (no live comparison); `E(<ack_id>)`; `fsync(preserved/)`; then A7 if this carrier is absent (a held identical carrier is kept); A8.

**STOPPED absent and this carrier held:** re-fence `session/` and return the carrier.

### 8.3 Phase A failure behaviour

| Failure | Behaviour |
|---|---|
| refusal | no write |
| any `PersistenceFailure` | §7.4 EIO: marker attempted, exit 44; no seal, carrier, STOPPED removal or deletion |
| process death | the next admission identifies the lifecycle state |

Phase A writes no ledger record and contacts nothing.

---

## 9. Phase B transaction (unchanged from round 1 except the set verification wording)

### 9.1 Order (fresh start and restart alike)

**B0** Verify, then fence:
- the carrier seal, pair and evidence;
- the **sealed** set: `MANIFEST` bytes hash to `evidence.manifest_sha256` and validate (§7.2), and every entry reads back with its size and hash;
- P3–P8 and P10 over `H`;
- Π derived from `H`, and the evidence recomputed and equal;
- owned `O ≤` anchor `= Π[:k]`;
- a tail without an intent is a strict prefix of the next own frame (`_next_own_frame`, `planned = Π`);
- RECOVERING, if present, is anchored `≥ W.last_seq` with this pair's context;
- **conversation rule:** activation not yet owned ⇒ present with `evidence.conv_sha256`; activation owned ⇒ absent or with that hash.

A failure stops `acknowledgement_unverified{problem}` (only STOPPED written). On success, `fsync(session/)`.

**B1** Decision `BP`:
- replay = `R0` + neutral records + owned records in `p0`, each applied once;
- core = `Π[k:] + T` (`T` only under an intent);
- the existing tail and intent mechanics are unchanged.

**B2** Commit `core[len(extra):]`, each synced.

**B3 Establish owned durability:** fsync every segment from `W`'s last segment through the active one, then `fsync(ledger/)`. This runs even when nothing was written. A failure takes the session failure boundary, and **`conversation.json` is untouched**.

**B4** If `conversation.json` exists:
- require `evidence.conv_sha256`, else stop `conversation_changed`;
- unlink it;
- `fsync(session/)`.

If it is absent, `fsync(session/)` anyway.

**B5** `_consume_ack` (one matching receipt, its segment fsynced, unlink ACKNOWLEDGED, fence), then remove RECOVERING.

**B6** Exact IDENTITY reservation, then `unit_end()`. Return `Opening("BP")`. No `REQUEST_SENT`/`INVOKING` is written and no client is constructed before this.

**Three notions, kept apart:**
- *readable* activation: its frame is present;
- *established*: B3 returned in this process;
- *completed*: B4 fenced and the carrier is retired.

Linearization of the new epoch is the first returned fsync covering the activation frame.

### 9.2 Restart with nothing to write

`k = |Π|`: B0, then B1 with an empty core, then B3 establishes the inherited activation, then B4, B5, B6.

### 9.3 Carrier-free (RECOVERING present, ACKNOWLEDGED absent)

1. Validate the intent and its context (§5.4).
2. The owned records must be exactly `Π + T`, and `conversation.json` must be absent. Otherwise stop `recovery_intent_mismatch`; **nothing missing is written**.
3. B3, B4 (fence the absence), remove RECOVERING, B6.

### 9.4 Composition with torn-tail recovery

- `T = [RECOVERY{torn_incomplete, detail + tail_sha256}]`, built from the intent's original tail.
- `T` is placed **after** Π.
- The intent freezes `k`, the tail and the context.
- A further own tear under that intent is set aside with no record (`:1070–1078`), so there is at most one `T`.
- B0 checks `O ≤` anchor; `_recover` checks the extras against `Π[k:] + T`.

### 9.5 Traces

| Trace | Outcome |
|---|---|
| receipt torn | intent at `W.last`; core = Π + T |
| spend torn | intent at Π[0]; core = Π[1:] + T |
| spend readable | `k = 2`; core = [activation]; the spend is never re-derived away |
| …spend readable, then host loss | `k = 1`, or the spend-torn path |
| activation torn | core = [activation] + T |
| **activation readable** | §9.2: B3 establishes it, then B4 |
| …then a second death after B4's fence, then host loss | the activation survives (B3 returned) and the start converges |
| …second death inside B3 | the conversation is intact; the activation may be lost and is rewritten |
| failed B3 | `PersistenceFailure`; no unlink; FSYNC_FAILED; A1 (SV023-02) |
| second tear under the intent | set aside with no record; core from I1 |
| carrier absent, RECOVERING present | §9.3 |

---

## 10. Crash, host-loss and name-loss cuts

| Cut | Outcome |
|---|---|
| A0, refusal | unchanged |
| A1 (mkdir or fence) | under M-2 a lost name means none or pre-boundary: retry |
| A2 inside `write_bytes_durable` (temp written or renamed, directory unfenced) | pre-boundary (only owned `MANIFEST` temps), or `MANIFEST` present but its name unfenced. Under M-2 the name may vanish, reverting to pre-boundary. A **readable** valid `MANIFEST` is a boundary for the retry, which re-fences it in `E` before relying on the seal |
| A3–A4 (subdirectory names, copy temps, renames, unfenced leaf directories) | post-boundary retry: reuse verified destinations, delete owned scratch, re-fence every subdirectory in its parent, copy the missing ones |
| A5 (`E`) before return | no seal: retry runs `E` again |
| A6 rename unfenced | under M-2 it may revert to `.partial` with a complete set: post-boundary retry, `D = A = 0`, then `E` and re-seal |
| A7 carrier, A8 STOPPED unlink unfenced | STOPPED returns: sealed retry, `E`, then re-publish or keep the carrier |
| Phase B | §9.5; B3 precedes B4 |

**Invariants checked immediately after every cut** (and after simulated host loss):
1. If `conversation.json` is absent, the complete Π is within the durable ledger.
2. If ACKNOWLEDGED (this carrier) exists, the sealed set exists with **every** inventory entry at its exact bytes in the durability model.
3. No file of the post-boundary inventory has lost its last copy: each entry exists either live, with its inventory hash, or in the set.

---

## 11. State authority after activation (unchanged)

The comparison uses `wire(x) = x.to_wire(next_seq=1)`. Physical sequence and chain are asserted separately.

| Field | After | Authority / proof |
|---|---|---|
| lineage | retained | P3–P8 |
| `history_epoch` | `e+1` once | frozen Π; reducer `chassis_replay.py:353` |
| messages, `recap_folded` | `[]`, 0 | `_switch_base`; old bytes sealed |
| `requests.next` | retained from `C_n` (attempt+1 after a failed request) | P6 + Π |
| `requests.last` | retained; in failed-unknown, `outcome = possible_duplicate_spend` | Π's spend |
| IDENTITY | retained; exact reservation | P5 |
| notes, legacy, originals | retained | P6, P7 |
| group / queue | none | P7 |

`next_label() = lineage:<C_n.next.turn>:<C_n.next.attempt>`.

## 12. Duty-visible semantics and GC (unchanged)

**E1+S1+R1+N1** apply. Pending notes preempt the bootstrap callback; with no pending note, bootstrap or the default opening runs. No notice, new ordering or held-policy choice is introduced.

**GC:**
- `preserved/` is outside the GC namespace;
- STOPPED and ACKNOWLEDGED block collection;
- after activation, ordinary GC applies. `_retained_prev` may name an older known checkpoint at the first post-activation checkpoint, so collection may start there.

---

## 13. Source-to-change map

| File | Change |
|---|---|
| `services/chassis_startup.py` | **Registry (§4).**<br>**`acknowledge`:** `home_dir`.<br>**Envelopes:** carrier, evidence, context.<br>**New pure functions:** `preserving_plan`, `preserving_admission`, `preservation_domain`, `preserved_usage`, `inventory_bytes` / `inventory_problem`, `set_lifecycle`, `owned_scratch`, `preserving_evidence`.<br>**New mutation:** `_acknowledge_preserving` (A1–A8 plus the L1 inherited-inventory fence, §8.2) and `_establish_set_dependencies` (`E`).<br>**`_Context`:** `_verify_preserving`, the BP decision, `_establish_owned_durability` (B3), `_finish_case("BP")`, the carrier-free path.<br>**`_consume_ack`:** treat the preserving receipt like the witnessed one |
| `services/chassis.py` | CLI passes `home_dir=chassis.home_dir` (`:1765`) |
| other services | none |
| `tests/test_chassis_acknowledgements.py` | the one `SUPPORTED` tuple (§4) |
| `tests/test_chassis_bootstrap_preserving.py` | new (§14) |

---

## 14. Finite temporary-root test plan (frozen; nothing run)

### 14.1 Harness (test-local)

**`HomeRoot(Root)`**: `home = path`, `session = path/"session"` (the production layout), so the default home is correct and calls use the unchanged signature.

**`PreserveOps(AckOps)`** (SV028-06 model). It records pending namespace changes **keyed by directory identity** `(st_dev, st_ino)` of the containing directory, not by path text:
- `mkdir` (a new child directory);
- `open(O_CREAT)` of a new path (a new child file);
- file and **directory** renames: the source name removed, the target name added, and the replaced target's prior content if any;
- unlinks.

A returned `sync_dir(path)` clears the pending set of that path's **current** directory identity. Segment byte watermarks are inherited from `CutOps`.

**`host_loss_names(ops)`**:
1. Walks the temporary root once to map current directory identities to paths. This is how a pending child of `<ack>.partial/session/ledger` is found under `<ack>/session/ledger` after the ancestor rename.
2. Undoes each directory's pending changes newest first:
   - new children are removed (directories with their subtrees);
   - renames are reversed;
   - unlinked files are restored with their bytes;
   - unsynced segment bytes are truncated (existing rule).

**`PreserveOps(previous)`** carries the identity-keyed pending sets and the byte watermarks across processes.

**Independent declared inventory.** The test computes this itself, never through the production selector:
- before the command;
- every regular file under `session/` outside `preserved/`, plus `HANDOFF.md`;
- recorded as `{path: (bytes, st_dev, st_ino)}`.

Snapshot timing alone excludes later carrier artifacts; no name filter is applied.

### 14.2 Fixtures

All neutral fixtures use `HomeRoot`, `establish`, a pending note `N1` (unless stated), one complete tool turn, then:

| Fixture | Construction | Suffix after `C_n` |
|---|---|---|
| `run-end` | `checkpoint()` (`C_n`), `record_run_end(0, …)` | `[RUN_END]` |
| `collected-and-rotated` | `test_chassis_gc.begin`, a note, two `tool_turn`s, `record_run_end`. The fixture asserts at least one `GC_INTENT` naming a segment, and a `LEDGER_HEADER`, after `C_n` | non-vacuous GC and header |
| `failed-unknown-request` | `send` without a response, `checkpoint()`, `record_run_end` | `[RUN_END]`; `outcome failed_unknown`, `next (t, 2)` |
| `no-pending-note` | `run-end` without `N1` | `[RUN_END]` |
| `older-known-prev` | C1, C2, C3 = `C_n`; `.prev.json` = C1's bytes; only `conversation.json` damaged | — |
| **planted** | `session/agent-notes.txt`, `recap.md`, `HANDOFF.md`, `Y` at `corrupt/conversation-<sha256(X)[:16]>`, and **`session/.ACKNOWLEDGED.0123456789abcdef.tmp` with distinct bytes** | — |
| **single-entry corrupt leaf** | exactly one regular file in `session/corrupt/`, so `<partial>/session/corrupt/` holds one destination and no later copy writes there. The fixture asserts this | — |

Each fixture then damages `conversation.json` (and `.prev.json` except in `older-known-prev`). The actual start must stop A14-unbound with a valid witness, changing only STOPPED.

### 14.3 New nodes: `tests/test_chassis_bootstrap_preserving.py` (53)

**Unchanged from round 1 (36), parameters as stated; assertions updated where noted:**

| Id | Node | Notes |
|---|---|---|
| N1 ×3 | `test_sv028_bootstrap_preserving_starts_exactly_one_new_epoch[run-end\|collected-and-rotated\|failed-unknown-request]` | Set = independent inventory; copies' inodes are not pre-command inodes and have `st_nlink == 1`; protocol records exactly Π; §11 state; `A12t` later |
| N2 ×2 | `test_sv028_resume_after_activation_matches_the_same_state_a12_path[pending-note\|no-pending-note]` | pending: `[note]`, no opening; none: `["OPENING"]` |
| N3a | `test_sv028_every_declared_pre_resolution_file_survives_later_ordinary_replacement` | planted fixture. The independent inventory **includes the pre-existing `.ACKNOWLEDGED.<hex>.tmp`**, which is preserved byte-exactly in the set and never deleted live |
| N3b | `test_sv028_an_older_known_previous_file_is_retained_and_collection_follows_the_reference_graph` | actual collection at the first post-activation checkpoint |
| N4a | `test_sv028_every_envelope_refusal_names_its_reason_and_changes_nothing` | as round 1 |
| N4b | `test_sv028_every_unsupported_shape_is_refused_before_any_mutation` | as round 1, plus `preserved_scratch_unowned` (a non-owned file in the own partial) |
| N5 | `test_sv028_the_command_and_the_activation_are_ordered_and_fenced` | **revised order:** `mkdir` + fences < `MANIFEST` (boundary) < subdirectory fences < copies < `E` (every set-file fsync, then leaf, parent and root directory fsyncs, `preserved/`, `session/`) < seal rename + `fsync(preserved)` < carrier < STOPPED unlink + fence; Phase B as round 1 (B3 before B4); no `link` |
| N6 ×2 | `test_sv028_every_cut_converges_to_one_receipt_and_one_activation[process-death\|host-loss]` | §10 invariants 1–3 checked at each cut, then convergence |
| N7 ×4 | `test_sv028_a_second_interruption_then_host_loss_still_converges[activation-readable/after-unlink-fence\|receipt-unsynced/activation-write\|archive-directory-unfenced/inventory-write\|conversation-unlink-unfenced/carrier-unlink]` | the third parameter is renamed from `…/manifest-write` because the MANIFEST is now the inventory |
| N8 ×5 | `test_sv028_an_own_partial_prefix_composes_with_the_frozen_plan[receipt-torn\|spend-torn\|spend-readable\|activation-torn\|carrier-absent-recovering-present]` | — |
| N9 | `test_sv028_stale_or_conflicting_acknowledgements_grant_nothing` | — |
| N10 | `test_sv028_a_conflict_after_activation_fails_closed` | — |
| N11 | `test_sv028_cli_bootstrap_preserving_behind_the_first_request_barrier` | — |
| N12 ×4 | `test_sv028_mutation_control[hardlinked-copies\|no-neutral-suffix-check\|no-pre-unlink-sync\|plan-from-mutated-replay]` | — |
| N13 | `test_sv028_the_registry_is_one_truthful_union` | — |
| N14 | `test_sv028_a_failed_pre_unlink_sync_leaves_the_conversation_and_takes_the_persistence_boundary` | — |
| N15 ×6 | `test_sv028_capacity_and_serialization_bounds[repeated-copy-temp-crashes\|rewrite-peak\|manifest-exact-limit\|manifest-over-limit\|long-neutral-suffix\|cap-boundary]` | **`rewrite-peak`** is now a post-boundary retry with one destination byte-flipped and its live source verified: it is deleted before its temp is written, and usage never exceeds the §7.5 formula. **`repeated-copy-temp-crashes`**: usage at every allocation ≤ the formula, and the owned temps of each death are counted in `D` and deleted |

**New in round 2 (17):**

| Id | Node (exact parameters) | Asserts |
|---|---|---|
| N16 ×3 | `test_sv028_a_reused_copy_is_fenced_before_the_seal[reused-leaf-converges\|omit-reuse-fence-mutation\|eio-before-seal]` | Single-entry corrupt-leaf fixture.<br>**P1** (the command, `PreserveOps`) crashes on the `sync_dir` of `<partial>/session/corrupt` inside that copy's `write_bytes_durable`, after its rename.<br>**P2** = `PreserveOps(P1)` runs the command to completion. Its log must show **no** `open(O_CREAT)`, `write` or `rename` in that leaf (the reuse branch, with no incidental fence from a later copy).<br>**P3** = `PreserveOps(P2)` runs the consuming start to completion (activation, unlink, carrier retired).<br>Then `host_loss_names(P3)` with all carried pending sets, **before** any further start.<br>• `reused-leaf-converges`: every independently inventoried entry, including the reused one, exists in the **sealed** set with exact bytes; then ordinary convergence.<br>• `omit-reuse-fence-mutation`: `_establish_set_dependencies` is patched to skip directory fsyncs of leaves holding only reused entries. The same assertion must **fail**: the reused entry is missing after host loss, because its pending name survived the ancestor `.partial` → sealed rename.<br>• `eio-before-seal`: P2 gets `EIO` on that leaf's fsync inside `E`. Then: `PersistenceFailure`; no sealed directory; no ACKNOWLEDGED; STOPPED present; `conversation.json` present with its original bytes; FSYNC_FAILED present; a retry refuses `transaction_open` with the store unchanged |
| N17 | `test_sv028_preserve_ops_carries_pending_child_names_across_an_ancestor_rename` | Harness control: create `a/b/`, fence its creation; create `a/b/f` unfenced; rename `a` → `c`; fence the parent of `c`; host loss. `c/b/f` is gone, and `c/b/` remains. The same with `sync_dir(c/b)` before host loss: `f` remains |
| N18 ×10 | `test_sv028_the_durable_inventory_binds_every_retry[source-changed-after-copy\|source-missing\|domain-gained-file\|inventory-corrupt\|inventory-foreign-binding\|inventory-missing-with-copies\|corrupted-copy-with-verified-source\|pre-existing-acknowledged-temp-preserved\|owned-copy-temp-cleanup\|owned-inventory-temp-cleanup]` | Planted fixture.<br>• `source-changed-after-copy`: P1 dies after copying `agent-notes.txt` (X) and before `E`; the live file is set to Y; the retry refuses `preserved_source_changed`. The **whole root snapshot is unchanged**: the X copy is kept, no carrier, STOPPED present, conversation present.<br>• `source-missing`: the live file is deleted; refuse `preserved_source_missing`, unchanged.<br>• `domain-gained-file`: a new live regular file; refuse `preserved_domain_changed`.<br>• `inventory-corrupt`: one `MANIFEST` byte flipped; refuse `preserved_inventory_invalid`, untouched.<br>• `inventory-foreign-binding`: `MANIFEST` resealed with another `stop_sha256`; refuse `preserved_inventory_invalid`.<br>• `inventory-missing-with-copies`: a partial set planted with a copy and no `MANIFEST`; refuse `preserved_inventory_missing`, untouched.<br>• `corrupted-copy-with-verified-source`: a reused destination byte-flipped with its live source intact; the retry deletes and recopies; the set equals the inventory.<br>• `pre-existing-acknowledged-temp-preserved`: the planted `.ACKNOWLEDGED.<hex>.tmp` is in the published inventory and the sealed set, and the live file is still present after completion.<br>• `owned-copy-temp-cleanup`: P1 dies after a copy temp's write and before its rename; the retry deletes exactly that temp (asserted gone, and counted in `D`) and converges.<br>• `owned-inventory-temp-cleanup`: P1 dies after the `MANIFEST` temp's write and before its rename; the partial set holds only `.MANIFEST.<hex>.tmp`; the retry deletes it, publishes the inventory and converges |
| N19 ×3 | `test_sv028_an_equal_manifest_retry_allocates_nothing_at_cap_u[complete-partial-before-rename\|rename-unfenced-then-host-loss\|sealed-after-rename-fence]` | A run is cut so the own set is complete:<br>• before the seal rename;<br>• after an unfenced rename, then `host_loss_names` (reverting to `.partial`);<br>• after the rename's fence (sealed).<br>The caps are injected to the measured `U` (files and bytes). The retry is **accepted**, and the `PreserveOps` log shows **no** `open(O_CREAT)` or `write` under `preserved/` (in particular no `MANIFEST` temp). Measured usage equals `U` after every logged call. Then convergence. Boundary companions in the same node, each on a fresh copy of the same cut state: with `bytes cap = U_bytes − 1` the retry refuses `preserved_capacity:bytes`; with `files cap = U_files − 1` it refuses `preserved_capacity:files`. Both leave the whole root snapshot unchanged. This pins the selected rule: verified reuse with dependency fencing allocates exactly nothing, and it is admitted at `cap = U` and not below |

The N19 companions follow from the single admission predicate `peak ≤ cap`, where `peak = U − D + A`. With `D = A = 0`, `peak = U`, so the retry is accepted at `cap = U` and refused below it. A refusal changes nothing. A rewrite policy (rejected here) would need `peak = U + len(MANIFEST)` and would refuse at `cap = U`. N19 therefore distinguishes the two rules.

**Total new: 36 + 17 = 53.** N12 and N16[`omit-reuse-fence-mutation`] are the mutation controls. N17 is the model control.

**Collection on the old runtime.** Only accepted test modules are imported. D1–D3 call `st.acknowledge(session_dir, reason, "bootstrap-preserving")` or the CLI with no new keyword. New attributes are referenced only inside N13, N15, N16 and N19 bodies.

### 14.4 Retained nodes (50; unchanged from round 1)

**R1, `tests/test_chassis_acknowledgements.py` (35):**
- `test_a_witnessed_file_repair_stop_resumes_from_the_bound_checkpoint[a14]`, `[ck5]`
- `test_the_same_command_repeated_is_idempotent[a14]`
- `test_every_refusal_leaves_the_store_byte_identical[a14]`, `[ck5]`
- `test_the_refusal_matrix_control_the_unmutated_repair_is_accepted`
- `test_stops_without_a_safe_witness_are_recorded_as_before_and_ineligible`
- `test_an_a14_stop_over_a_pending_collection_carries_no_witness`
- `test_only_the_two_new_pairs_are_added_and_every_other_pair_is_still_refused` (with the §4 edit)
- `test_newer_integrity_stops_acquire_no_resolution[identity_unproven]`, `[gc_intent_invalid]`, `[ledger_prefix_missing]`, `[recovery_intent_invalid]`, `[acknowledgement_unverified]`
- `test_the_transaction_is_ordered_and_fenced`
- `test_every_cut_of_the_acknowledgement_converges_with_one_receipt[a14-process-death]`, `[a14-host-loss]`
- `test_a_second_interruption_then_host_loss_still_converges[carrier-unlink/first-fence]`, `[closure-unsynced/receipt-segment-sync]`, `[receipt-unsynced/carrier-unlink]`
- `test_a_stale_permission_never_authorizes_a_changed_store[valid-record]`, `[file-damaged-again]`
- `test_an_old_carrier_cannot_unlock_a_later_stop_with_the_same_reason`
- `test_an_independent_fsync_failure_after_the_acknowledgement_keeps_a1_authority`
- `test_sv023_01_a_present_carrier_that_does_not_verify_stops_before_any_change[a14-reason-an-old-pair]`, `[a14-wrong-check]`
- `test_sv023_01_a_damaged_old_pair_carrier_also_fails_closed[unknown-pair]`
- `test_sv023_01_control_a_valid_old_pair_carrier_is_still_consumed`
- `test_sv023_02_a_later_acknowledgement_never_replaces_an_unfinished_carrier[a14-failed-first-fence]`, `[a14-independent-marker]`
- `test_sv023_02_control_an_old_pair_retry_of_the_same_stop_is_still_supported`
- `test_sv023_03_every_cut_after_an_own_torn_frame_converges[receipt-process-death]`, `[closure-host-loss]`
- `test_sv023_04_a_failed_receipt_sync_keeps_the_carrier_and_takes_the_persistence_boundary`
- `test_sv023_05_an_interrupted_independent_tail_recovery_has_no_acknowledgement_and_converges`

**R2 (1):** `test_cli_acknowledgement_and_restart_behind_the_first_request_barrier`

**R3 (14):**
- `test_chassis_recovery_live.py`: `test_a0_a_stop_stops_without_writing_anything`, `test_c_k7_a1_an_fsync_marker_stops_the_next_start`, `test_c_k5_a6_a_corrupt_legacy_conversation_stops_and_is_kept`, `test_c_k3_a12_a_deleted_list_is_a_clean_slate_with_everything_kept`, `test_a14_o2_2_an_unreadable_file_is_rebuilt_from_the_previous_base`, `test_sv021_04_one_deletion_is_consumed_once_across_restarts`
- `test_chassis_replay.py::test_external_edit_delete_and_reimport_switch_the_base`
- `test_chassis_notes.py`: `test_c_n1_a_note_is_adopted_by_the_next_run_once`, `test_an_agent_edit_to_handoff_md_is_adopted_once_as_a_new_generation`
- `test_chassis_gc.py`: `test_o2_1_pending_generations_outlive_their_collected_records`, `test_c_g1_an_adopted_note_is_never_readopted_after_its_records_are_collected`, `test_o2_4_every_cut_in_a_collection_converges_over_two_restarts[process-death]`
- `test_chassis_rotation.py`: `test_sv027_every_closed_boundary_rotates_a_full_segment[startup-a9-clean]`, `test_sv027_rotation_failures_and_crashes_at_the_new_boundaries[startup-inherited-fsync-eio]`

### 14.5 Pre-fix (unchanged; one node per command)

| Id | Node | Expected |
|---|---|---|
| B0 | `test_c_k3_a12_a_deleted_list_is_a_clean_slate_with_everything_kept` | pass |
| D1 | `N1[run-end]` | fails: `LedgerError … not implemented` |
| D2 | `N4a` | fails at its first reason-token `match` (a reason-specific refusal control) |
| D3 | `N11` | fails at `returncode == 0` |

### 14.6 Commands and resource estimate

The approved runner is used with literal targets, one per message, serially, under unchanged caps (120 CPU s / 180 wall s / 512 MiB AS; aggregate 50% CPU / 2 GiB / 64 tasks / nice 15).

| Cmd | Content | Cases | Estimate |
|---|---|---|---|
| F1 | N1×3, N2×2, N3a, N3b, N4a, N4b, N5, N9, N10, N13, N14 | 14 | ≲ 20 s CPU |
| F2 | N6[process-death] | 1 | ≈ 160 logged calls (copies + `E` adds about 22 fsyncs) × ≈ 0.25 s ≈ 40 s CPU |
| F3 | N6[host-loss] | 1 | as F2, plus an identity walk per cut ≈ 45 s CPU |
| F4 | N7×4, N8×5 | 9 | ≲ 15 s |
| F5 | N12×4, N15×6 | 10 | ≲ 20 s |
| F6 | N11 | 1 | 10–20 s wall |
| **F7** | **N16×3, N17, N18×10, N19×3** | **17** | ≈ 40 fixture builds, three-process traces ≲ 30 s CPU |
| R1 | retained acknowledgement nodes | 35 | as SV023 |
| R2 | retained CLI node | 1 | 10–20 s wall |
| R3 | retained recovery, notes, GC, rotation | 14 | ≲ 20 s |

Commands `[14, 1, 1, 9, 10, 1, 17, 35, 1, 14]`: **53 new + 50 retained = 103 cases in 10 commands, plus 4 pre-fix commands.** The change from round 1 (86 in 9) is exactly the 17 new F7 nodes.

---

## 15. Limits (candid) and what is not claimed

1. **RSS is unproved.** Phase A and Phase B hold all segment bytes (`read_segments`), the parsed scan, replay states, one domain file or set entry at a time (≤ 64 MiB), and the inventory.
2. **Aggregate reads:**
   - Phase A fresh: all segments, the domain twice;
   - post-boundary retry: all segments, the live domain once (verification) plus the partial tree's existing files once, plus missing copies;
   - sealed retry: the set once;
   - Phase B: all segments, plus the set once.

   `E` adds one fsync per set file plus ≤ 8 directory fsyncs.
3. **Capacity** is an admission rule over measured logical sizes, not a quota or a block-allocation bound.
4. **Inherited fail-closed outcomes:**
   - a Phase A or Phase B persistence failure leaves FSYNC_FAILED and the session stopped (SV023-02 class);
   - after a post-boundary source change this acknowledgement cannot complete while the fixed-inventory checks fail (L7); its partial set is kept and counted;
   - the FSYNC_FAILED marker is best-effort: its persistence is conditional on its own write returning;
   - a post-activation M-6 conflict stops;
   - carrier temps can accumulate.
5. **M-6:** `preserved/` is agent-reachable and is a reliability aid, not evidence.
6. **Not claimed:** real-session operation; kernel or power-loss behaviour (M-2 is simulated); any guarantee after an fsync error (E-K2); partial-I/O guarantees beyond the existing helpers; numerical replay, segment or read bounds; any other stop; TC4; H/T/Q/pump/history; provider behaviour, merge or deployment.

## 16. Questions for Astra

1. Is `MANIFEST`-as-inventory, published before any copy and never rewritten, an acceptable durable snapshot boundary (§7.2)?
2. Does `E` (§7.4), run before every seal and every carrier publication, fully establish reused-entry dependencies?
3. Is the ownership rule (§7.2) verifiable enough, and is treating pre-existing `.ACKNOWLEDGED.*.tmp` as ordinary evidence acceptable?
4. Do the exact-delta capacity equation and N19 resolve SV028-07?
5. Is the identity-keyed `PreserveOps` model (N17) sufficient, and are 103 cases in 10 + 4 commands adequate?
