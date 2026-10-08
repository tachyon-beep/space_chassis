# SV-028 design (correction round 1): one narrowly admitted `bootstrap-preserving` acknowledgement

**Status: corrected design only, for independent Astra re-review. Not implemented. No test was run. No runtime or test file was changed.**

This document replaces round 0 as a standalone proposal; it is not an overlay. The governing review is [ASTRA-INITIAL-DESIGN-REVIEW.md](ASTRA-INITIAL-DESIGN-REVIEW.md), preserved unchanged. The finding-by-finding map is in [STATUS.md](STATUS.md).

## Provenance

- **Base:** `e2a1ddae362b1a931673dd074ef94ea6b978dbc2` (SV016–SV027 accepted in their own scopes; nothing reopened).
- **Canonical text:**
  - SV-013 §2.2.2: files, CK1–CK6, the authority rule, A0–A15, the acknowledgement sentence l.558;
  - SV-013 §2.2.5: notes, identity closure, GC;
  - SV-015 v2 §1.1–§1.4: M-1…M-6, framing, tail classes, checkpoint graph, GC, transitions.
- **Accepted local evidence:** `sv023/` (witnessed carrier, intent context, SV023-02 policy), `sv024/` (fences), `sv026/` (accounting), `sv027/` (closed-boundary rotation).
- **Code read:** `services/chassis_startup.py` (whole), `chassis_persistence.py`, `chassis_session.py`, `chassis_replay.py`, `chassis_gc.py`, `chassis.py`.
- **Tests read:** `tests/test_chassis_acknowledgements.py`, `test_chassis_recovery_live.py`, `test_chassis_gc.py` (the `CutOps`/`begin`/`start` harness).

Line numbers below are at the base.

---

## 0. The corrected proposal in brief

**One pair is admitted:** `conversation_unreadable_unbound` + `bootstrap-preserving`. The stop must carry a valid SV023 witness, and the records after the witnessed newest checkpoint `C_n` must be state-neutral. Everything else stays refused.

**Phase A (the operator command):**
1. Runs a pure admission. It enumerates an **exact preservation domain**: every regular file of `session/` (top level, `ledger/`, `blobs/`, `corrupt/`) and the one named `HANDOFF.md`. Unsupported shapes are refused.
2. Preflights the exact serialized manifest, carrier and maximal recovery-context sizes, and the actual peak usage of `preserved/`.
3. Fills an owned **unfinished** set `preserved/<ack_id>.partial/` with independent copies.
4. Writes `MANIFEST` inside it.
5. **Seals** the set by renaming it to `preserved/<ack_id>/` and fencing.
6. Writes a sealed carrier, then removes STOPPED.

**Phase B (the consuming start):**
1. Re-verifies the carrier and every sealed byte.
2. Derives a **frozen plan** Π from the witnessed checkpoint state alone, before any owned record is applied: receipt, optional `possible_duplicate_spend`, one activation `EXTERNAL_DELETE{epoch: e+1, cause: "bootstrap_preserving", …}`.
3. Validates any owned prefix against Π and appends only the missing continuation.
4. **Establishes the durability** of the whole owned prefix (segment fsyncs and the `ledger/` fence). This happens even if this process wrote nothing.
5. Only then unlinks the preserved unreadable `conversation.json` and fences `session/`.
6. Retires the carrier, then any RECOVERING, then reserves IDENTITY.

**After a torn own frame:** a carrier-free restart is authenticated by a sealed, bounded `RECOVERING.witnessed` context, checked against the immutable ledger head. Duty-visible behaviour is exactly A12's (E1+S1+R1+N1, confirmed as engineering by the review).

---

## 1. Canonical facts

| Source | Text (abridged; quoted where exact) | Used for |
|---|---|---|
| SV-013 §2.2.2 l.558 | "`bootstrap-preserving` keeps every file and starts epoch+1; it is the operator's explicit choice, never automatic." | Same lineage; epoch +1 once; preservation; operator act |
| SV-013 §2.2.2 files table | `conversation.json`, `.prev.json`, `run.json`, `ledger/`, `blobs/`, `corrupt/`, `STOPPED`, `FSYNC_FAILED`, `recap.md` (session), **`HANDOFF.md` (home)** | The preservation domain includes the one named home file (§7.1) |
| SV-013 authority rule | "An unreadable file is never treated as absent … nothing bootstraps over memory that may exist." | The live name is removed only after preservation and durable activation (§9) |
| SV-013 A12 | "`EXTERNAL_DELETE{epoch+1}`; bootstrap; `prev` and ledger preserved" | The accepted empty-base precedent (E1) |
| SV-013 §2.2.5 r.3, v2 §1.4.3 | the adoption watermark is "never reset" | Notes carried (N1) |
| v2 §1.1 | M-1 process death; M-2 honest host loss (unsynced bytes and unfenced names may be lost); M-3 checksum-only detection; M-4; M-5 single writer; M-6 out of model | Crash model (§10, §14.1) |
| v2 §1.3 | TC1 own-torn rule; "`bootstrap-preserving` (D13) remains the alternative" for TC4 | Composition (§9.4); TC4 **not** admitted |
| v2 §1.4.5 | GC removes only intent-named items; `corrupt/` never GC'd | GC exclusion (§12) |
| v2 §1.4.8 | strict pre-admission caps | Capacity rule (§7.4) |

---

## 2. Accepted runtime facts this design depends on (corrected)

- **Today `bootstrap-preserving` is refused for every reason** ("not implemented … nothing was changed", `chassis_startup.py:246–247`). `IMPLEMENTED_RESOLUTIONS` (`:101–106`) is the allowlist, and `WITNESSED_RESOLUTIONS` (`:96–99`) the witnessed subset. `read_carrier` (`:290–303`), `carrier_problem` (`:506`) and `witnessed_context_problem` (`:1529`) consult these sets.
- **The A14-unbound stop and its witness:** `:1271–1274`, `stop_witness` (`:409–454`).
- **Witnessed own-prefix rule:**
  - `witnessed_evidence` (`:539–681`) allows, after the witnessed end, only `[receipt, *core]` and a strict byte prefix of the next own frame (`_next_own_frame`, `:684–694`).
  - `_recover` freezes a torn-own-frame transaction in RECOVERING with a `witnessed` context of exactly `{ack_id, receipt, after_seq}` (`:1055–1058`, `:1515–1537`).
  - Under an existing intent, a further own torn frame is set aside **without** a new RECOVERY record (`:1070–1078`).
  - Extras must be a prefix of the core, and a witnessed recovery writes nothing beyond it (`:1085–1094`).
- **Ordinary TC0 closure:** `derive_core` (`:1587–1642`) emits `RECOVERY{possible_duplicate_spend}` when `requests.last.outcome == "failed_unknown"`. The reducer then sets that outcome and `requests_next = detail.next` (`chassis_replay.py:606–616`). **Applying the spend changes the state that derived it.** This is why the plan must be frozen (§5).
- **Files that later ordinary operation replaces or removes:**
  - CK3/CK4 replace `conversation.json` and rotate `.prev.json`, removing `.prev.tmp` (`chassis_persistence.py:1505–1538`);
  - CK5 replaces `run.json`;
  - `reserve_turns` replaces `IDENTITY`;
  - `append_recap` replaces `recap.md` (`chassis.py:275–285`);
  - `write_note` replaces the `HANDOFF.md` mirror (`chassis_session.py:476–482`);
  - GC unlinks segments and blobs;
  - quarantine **rewrites a deterministic destination** in `corrupt/` (`chassis_persistence.py:1457–1481`; `_quarantine_file` `chassis_startup.py:210–226`), replacing a pre-existing file there with different bytes.
- **`write_bytes_durable` cleanup:** it unlinks its own temp on `OSError` (`chassis_persistence.py:985–991`). A process death leaves the temp behind.
- **CK3 retains an older known checkpoint:** `_retained_prev` (`chassis_session.py:610–625`) keeps `.prev.json` and names it as `prev` when it holds **any** known checkpoint's bytes, not only `C_n.prev`.
- **Production layout:** `session_dir = home_dir / "session"` (`chassis.py:610–612`).

---

## 3. Scope

| # | Stop | Decision | Missing semantics (not guessed) |
|---|---|---|---|
| **W1** | `conversation_unreadable_unbound`, valid witness, state-neutral suffix after `C_n` | **Admitted** | — |
| W2 | same, any non-neutral record after `C_n` | refused (`suffix_not_neutral`) | Fate of suffix-only memory; open-group closure before a base switch |
| W3 | same, no witness | refused (existing "no valid witness") | A witness for those shapes |
| C1 | `run_json_unreadable` | refused (not implemented for this resolution) | Whether bootstrapping over a bound, readable conversation is ever wanted |
| T1 | `ledger_tail_ambiguous` | refused | No note-generation reservation; hidden epoch steps; tail truncation before chain continuation |
| L | A7, A15, A2, `ledger_prefix_missing`, `ledger_unreadable`, A6, `run_json_missing`, integrity and transaction stops, `fsync_failed_previous_run`, `corrupt_quarantine_full`, `acknowledgement_unverified` | refused | No proven predecessor state, lineage, epoch or witness |

**State-neutral** means each record with `seq > C_n.seq` has type in `NEUTRAL = {LEDGER_HEADER, RUN_END, GC_INTENT, GC_DONE}` and no intent is pending. The reducer has no handler for these (`chassis_replay.py:387–396`).

The request-identity bound is the checked IDENTITY equal to the witness, never a turn maximum read from a clean ledger. A recovery repair after `C_n` is non-neutral, so W2 applies.

---

## 4. One truthful resolution registry

There is a single registry with mechanism-specific subsets, used by `acknowledge`, `read_carrier`, `carrier_problem` and `witnessed_context_problem`:

```python
RESOLUTION_MECHANISM = {
    ("ledger_tail_ambiguous", "continue-conservative"): "tail",
    ("fsync_failed_previous_run", "continue-from-bound"): "plain",
    ("corrupt_quarantine_full", "continue-from-bound"): "plain",
    ("conversation_unreadable_unbound", "continue-from-bound"): "witnessed",
    ("run_json_unreadable", "continue-from-bound"): "witnessed",
    ("conversation_unreadable_unbound", "bootstrap-preserving"): "preserving",
}
IMPLEMENTED_RESOLUTIONS = frozenset(RESOLUTION_MECHANISM)            # the complete union: 6 pairs
WITNESSED_RESOLUTIONS = {p for p, m in RESOLUTION_MECHANISM.items() if m == "witnessed"}   # unchanged, 2
PRESERVING_RESOLUTIONS = {p for p, m in RESOLUTION_MECHANISM.items() if m == "preserving"} # 1
STOP_WITNESS_RESOLUTIONS = WITNESSED_RESOLUTIONS | PRESERVING_RESOLUTIONS
WITNESSED_REASONS = {r for r, _ in STOP_WITNESS_RESOLUTIONS}         # unchanged: {A14, CK5}
```

- `acknowledge` first checks the union. Unimplemented pairs keep today's exact message. It then dispatches by mechanism.
- `read_carrier` accepts a pair only if it is in the union, and checks the exact envelope its mechanism writes.
- `witnessed_context_problem` accepts receipts whose pair is in `STOP_WITNESS_RESOLUTIONS`, with the key set its mechanism defines (§5.4).

**The one reviewed existing-test change.** `tests/test_chassis_acknowledgements.py:56–62` `SUPPORTED` gains the tuple `("conversation_unreadable_unbound", "bootstrap-preserving")`, with a comment naming SV028. This is required because `test_only_the_two_new_pairs_are_added_and_every_other_pair_is_still_refused` asserts `IMPLEMENTED_RESOLUTIONS == SUPPORTED` (`:494`). After the edit:
- `:495` (`WITNESSED_RESOLUTIONS`) is unchanged and still holds;
- the loop skips the now-implemented pair;
- `refused == len(OTHER_REASONS) * 3 - len(SUPPORTED)` stays exact (75 − 6 = 69 refusals, previously 70);
- every other assertion and message is untouched.

The removed in-loop refusal of `(A14, bootstrap-preserving)` on a repaired store is replaced by N4a's explicit `conversation_readable` case. No other existing test is edited.

---

## 5. The frozen plan Π

### 5.1 Derivation (pure; from the witnessed head only)

Let `H` be the records with `seq ≤ W.last_seq`, where `W` is the witness ledger block. `preserving_plan(H, lineage, ack_id, manifest_sha256, receipt, identity_reserved)`:

1. `C_n` = the newest CHECKPOINT in `H` (it must equal the witness tuple). `state0 = SessionState.from_wire(C_n.payload["state"])`. Every record in `H` after `C_n` must be in `NEUTRAL`.
2. `R0 = Replay([], state0.copy())`. Neutral records are no-ops; `R0.group is None`.
3. Over `H`'s clean end: `scan_H` = TC0, `tail0 = classify_tail(scan_H)`, `plan0 = plan_recovery(scan_H, tail0, read_blob)`. `spend = derive_core(R0, plan0, tail0, scan_H, None, lineage, identity_reserved=identity_reserved)`.
   - This must be `[]` or exactly `[("RECOVERY", {"kind": "possible_duplicate_spend", "detail": {"label", "next"}})]`. Anything else refuses (`plan_unexpected`).
4. `e = state0.history_epoch`. `activation = ("EXTERNAL_DELETE", {"epoch": e+1, "notices": [], "cause": "bootstrap_preserving", "ack_id": ack_id, "manifest_sha256": manifest_sha256})`.
5. **Continuation** `C = [*spend, activation]`. `continuation_sha256 = sha256(canonical_body({"continuation": [[name, payload] for …]}))`.
6. **Π = [("RECOVERY_ACK", receipt), *C]**, so `|Π| ∈ {2, 3}`. The receipt is `receipt_payload(carrier)` (`:518–523`) and names `evidence_sha256`. The evidence names `continuation_sha256`, which excludes the receipt, so the definition is not circular.

Π is computed **once per start, from `H` alone, before any owned record is applied**, and is never recomputed from a replay that applied owned records. The epoch e+1 is fixed here.

### 5.2 Owned records and positions

- **Owned records** are the records with `seq > W.last_seq`.
  - `LEDGER_HEADER`s are physical. They are validated by the scanner's chain, `first_seq` and `prev_chain` rules, and never occupy a logical position.
  - The **logical owned sequence** `O` is the non-header owned records.
- **Valid shapes of `O`:**
  - `O == Π[:k]` for some `0 ≤ k ≤ |Π|`, or
  - `O == Π + T`, where `T` is the recovery record of an intent's original torn tail (§9.4). This shape is only valid when that intent is or was present.
- Each owned record is applied **once**, to the decision replay that starts from `R0`. The continuation `Π[k:]` (+ `T`) is committed by `Session._commit`, which applies each record once more as it is written. No record is applied twice and Π is not re-derived.

### 5.3 Evidence (carrier `evidence`; fixed keys, bounded)

```json
{"witness_check": "<64 hex>", "manifest_sha256": "<64 hex>",
 "conv_sha256": "<64 hex>", "conv_bytes": n,
 "run_sha256": "<64 hex>", "state_sha256": "<64 hex>",
 "suffix": {"count": n, "types_sha256": "<64 hex>"},
 "continuation_sha256": "<64 hex>", "epoch": e+1}
```

- `conv_*` is the manifested `session/conversation.json` entry.
- `state_sha256 = sha256(canonical(state0.to_wire(next_seq=W.last_seq+1)))`.
- The suffix is represented by count and a digest of its type list, never the list, so the carrier size is independent of suffix length (SV028-04).

The carrier is the SV023 envelope `{reason, resolution, ack_id, witness, evidence, check}` with this exact evidence key set for the preserving mechanism.

### 5.4 Sealed recovery context for the preserving mechanism

When a torn own frame forces RECOVERING, the intent's `witnessed` context for this pair is:

```json
{"ack_id": "<32 hex>", "receipt": {RECEIPT_KEYS…}, "after_seq": W.last_seq, "evidence": {§5.3 exactly}}
```

The SV023 `continue-from-bound` context keeps its exact 3 keys. `witnessed_context_problem` selects the key set from `(receipt.reason, receipt.resolution)`'s mechanism. Validation runs before use, inside the existing whole-intent checksum and `_validated_intent` domain checks (`:1470–1509`):
1. key sets are exact;
2. `receipt.ack_id == ack_id`;
3. `sha256(canonical_body(evidence)) == receipt.evidence_sha256`;
4. `evidence` passes its domain checks;
5. `after_seq ≤ intent.last_seq`.

**Carrier-free authentication** (carrier already retired, RECOVERING still present):
1. `H` = the records `≤ after_seq` (immutable, chain-verified).
2. `C_n` and `state0` come from `H`; their digest must equal `evidence.state_sha256`, and `state0.history_epoch + 1 == evidence.epoch`.
3. Π is re-derived from `H`, `ack_id`, `evidence.manifest_sha256` and `receipt`. Its `continuation_sha256` must equal `evidence.continuation_sha256`.

Any failure stops `recovery_intent_invalid`, with nothing written. No fact is guessed, the archive is not read, and absence of the live file never counts as permission.

**Why a sealed context rather than reconstruction from preserved STOPPED and MANIFEST.** The context is bounded (< 2 KiB), self-contained, covered by the intent checksum and checked against the ledger head. Reconstruction would make every carrier-free restart depend on agent-reachable `preserved/` bytes and add archive reads. Every fact Π needs is in `H` or in this context.

### 5.5 Domains and exact serialization (preflighted in Phase A before any write)

- **Counters:**
  - `e+1 ≤ MAX_COUNTER`;
  - `W.last_seq + |Π| + 1 (T) + 2 (possible headers) ≤ MAX_SEQ`;
  - the spend's `next` fields are counters.
  - Otherwise refuse `plan_out_of_domain`.
- **Exact bytes:**
  - `MANIFEST` (§7.3) ≤ `MANIFEST_READ_MAX = META_READ_MAX` (1 MiB), else `preserved_manifest_too_large`;
  - the carrier `json.dumps(…, sort_keys=True)` ≤ `MAX_MARKER_READ` (64 KiB), else `carrier_too_large`;
  - the **maximal** RECOVERING, built with this context and maximal-width placeholders (`segment = 999999`, `offset` and `tail_bytes` = 10¹²−1, 64-hex hashes), ≤ `MAX_MARKER_READ`, else `recovery_context_too_large`.
- **Shape bounds:** the witness and evidence have fixed keys and bounded fields (lineage ≤ 64 chars, 12-digit integers, 64-hex hashes), so carrier and context are each below about 3 KiB. Π's frame bodies are a few hundred bytes, far below `MAX_LEDGER_BODY`.

---

## 6. Phase A admission (pure; refusal changes nothing)

`acknowledge(session_dir, reason, resolution, *, ops=None, home_dir=None)` handles the pair through `_acknowledge_preserving`.
- `home_dir` defaults to `session_dir.parent`, the chassis's own layout rule (`chassis.py:610–612`). The CLI passes `chassis.home_dir` explicitly.
- Each refusal raises `AcknowledgementRefused` (a `LedgerError`; CLI exit 2) whose message begins with the token shown.

| # | Check | Refusal token |
|---|---|---|
| P1 | STOPPED readable within `MAX_MARKER_READ`; reason A14; `detail.witness` valid (`witness_problem`) | `stop_not_acknowledgeable` / existing "no valid witness" |
| P2 | ACKNOWLEDGED absent or **this** sealed preserving carrier. No RECOVERING, no FSYNC_FAILED | "another acknowledgement is pending" / `transaction_open` |
| P3 | Ledger lineage, strict scan, no tail, anchor and physical end equal the witness; **no owned record** | `ledger_not_witnessed` |
| P4 | No unauthorized prefix, no pending GC intent | `collection_pending_or_unauthorized` |
| P5 | `read_identity == witness.identity_reserved` | `identity_not_witnessed` |
| P6 | `C_n` tuple, chain and `run_sha256` equal the witness; state validates; every `blobs_live` blob hash-verifies | `checkpoint_not_witnessed` / `state_blob_missing` |
| P7 | Every record after `C_n` is in `NEUTRAL` | `suffix_not_neutral` |
| P8 | `run.json` SHA-256 equals `C_n.run_sha256`; format-2 fields agree | `run_json_not_witnessed` |
| P9 | `conversation.json` present, a regular file, read within `CONVERSATION_READ_MAX`, and `parse_messages` is None | `conversation_absent` / `conversation_readable` / `conversation_over_bound` |
| P10 | Neither file's SHA-256 equals `C_n.conv.sha256`, and `_previous_base` (pure) returns `(None, None)`. A `.prev.json` holding a *different* known checkpoint is allowed | `previous_base_available` |
| P11 | **Domain enumeration** (§7.1). Every path kind and name is supported; every file ≤ `PRESERVED_FILE_MAX`; inventory read #1 records size and SHA-256 | `preservation_unsupported_shape` / `preservation_unsupported_name` / `preserved_file_too_large` |
| P12 | **Own-set state** (§7.2): none, unfinished, or sealed. A sealed set must verify fully and equal the recomputed manifest; both `<ack_id>` and `<ack_id>.partial` present refuses | `preserved_set_mismatch` |
| P13 | **Capacity at actual peak** (§7.4) | `preserved_capacity:{sets\|files\|bytes}` |
| P14 | Π derivable (§5.1); domains and exact sizes (§5.5) | `plan_unexpected` / `plan_out_of_domain` / `preserved_manifest_too_large` / `carrier_too_large` / `recovery_context_too_large` |

`ack_id = sha256(STOPPED bytes ‖ "\n<reason>\n<resolution>")[:32]`, as today.

---

## 7. Preservation

### 7.1 Exact domain (admitted namespace)

The domain is enumerated with `lstat` and without following symlinks. Listing is bounded: it stops and refuses after `PRESERVED_MAX_FILES + 1` entries.

| Location | Admitted | Treatment |
|---|---|---|
| `session/` top-level regular files | any name matching `NAME = [A-Za-z0-9._:+=@,-]{1,255}`, not `.`/`..` | **copied** to `session/<name>`, including STOPPED, IDENTITY, run.json, both conversation files, recap.md, unknown names such as `agent-notes.txt`, and any temp leftovers (`.IDENTITY.<hex>.tmp`, `.prev.tmp`, `.conversation.<hex>.tmp`, …) |
| `session/ledger/`, `session/blobs/`, `session/corrupt/` | regular files with `NAME` names, no subdirectories | **copied**. `corrupt/` is included because quarantine can overwrite a deterministic destination there |
| `<home>/HANDOFF.md` | absent, or one regular file | **copied** to `home/HANDOFF.md`; the only home path read |
| `session/preserved/` | earlier sets only, in the §7.2 shapes | **not copied** (no archives inside archives). Counted for capacity; earlier sets are never modified |
| `session/ACKNOWLEDGED`, `session/.ACKNOWLEDGED.<16 hex>.tmp` | acknowledgement-transaction artifacts, not session evidence | not copied, never deleted (`ACKNOWLEDGED` must be absent or this carrier: P2) |
| any other directory, symlink, FIFO, socket or device in `session/`; a subdirectory inside `ledger/`/`blobs/`/`corrupt/`; a non-`NAME` name; a symlinked or non-regular HANDOFF | — | **refused before any mutation** |

**Pre-resolution evidence** is exactly the domain's copied files at the first admission. **Transaction-owned artifacts** are:
- the unfinished set `preserved/<ack_id>.partial/` and everything in it;
- the carrier and its temp names.

The **sealed set** `preserved/<ack_id>/` is immutable after sealing. A whole-home or recursive backup is not performed.

`PRESERVED_FILE_MAX = 64 MiB` [CM], equal to the largest runtime per-file bound (conversation and blob). A larger file refuses rather than being partially copied.

### 7.2 Set lifecycle and retry policy

Each set mirrors the domain: `<set>/session/…`, `<set>/session/ledger/…`, `<set>/session/blobs/…`, `<set>/session/corrupt/…`, `<set>/home/HANDOFF.md`, and `<set>/MANIFEST`. Set directory names must match `[0-9a-f]{32}` or `[0-9a-f]{32}\.partial`. Any other shape under `preserved/` refuses (P11).

| Own state at admission | Action |
|---|---|
| none | create `<ack_id>.partial/`, then fill and seal |
| **unfinished** (`<ack_id>.partial/` only) | **Owned-scratch cleanup**, only after full admission passes: unlink every file in it that is a temp name, not a domain destination or `MANIFEST`, a destination whose bytes differ (bounded read), or a `MANIFEST` differing from the recomputed one; `fsync` each touched directory. Then fill the missing destinations and seal. Verified destinations are kept, never rewritten. Unknown shapes inside refuse (P11), never deleted |
| **sealed** (`<ack_id>/` only) | verify the `MANIFEST` seal, that it equals the manifest recomputed from the live domain (STOPPED was present throughout, M-5), and every entry's bytes. Any mismatch refuses `preserved_set_mismatch`, **untouched: never repaired or rewritten**. On success, re-fence `preserved/` and continue at the carrier step |
| both | refuse |

`write_bytes_durable`'s own `OSError` cleanup of its temp is consistent with this rule: that temp is owned scratch. A process death leaves the temp, and the next admission's cleanup removes it.

### 7.3 MANIFEST (sealed, exact)

```json
{"version": 1, "ack_id", "reason", "resolution", "stop_sha256", "witness_check", "lineage_id",
 "entries": [{"path": "session/<name>" | "session/ledger/<name>" | "session/blobs/<name>" | "session/corrupt/<name>" | "home/HANDOFF.md",
              "bytes": n, "sha256": "<64 hex>"}, …],      # sorted by path; NAME rule enforced
 "totals": {"files": k, "bytes": b}, "check": "<64 hex>"}
```

It is serialized canonically and its exact length is preflighted (P14).

### 7.4 Capacity at actual peak (strict, admission-time)

The caps are [CM]: `PRESERVED_MAX_SETS = 4`, `PRESERVED_MAX_FILES = 16 384`, `PRESERVED_MAX_BYTES = 512 MiB`, over all of `preserved/`, temp names included.

Admission measures actual usage `U` (files and bytes; `lstat` walk of `preserved/` at depth ≤ 4) and plans:
- `D` = owned scratch to delete (unfinished own set only);
- `N` = destinations still to write (count and bytes);
- `M` = manifest bytes, if not already present and equal.

Peak usage is `U − D + N + M`. There is no double-holding: every deletion precedes every allocation, each copy temp is renamed onto an **absent** destination, and verified destinations are never rewritten.

| Quantity | Requirement |
|---|---|
| Files | `U_files − D_files + N_count + 1 ≤ MAX_FILES` |
| Bytes | `U_bytes − D_bytes + N_bytes + M ≤ MAX_BYTES` |
| Sets | distinct set ids present, plus 1 if the own set is absent, ≤ `MAX_SETS` |

- Equality is allowed (an exact cap).
- If it fails, refuse with nothing deleted or written.
- Repeated deaths cannot accumulate scratch: each retry's cleanup removes the previous scratch before any new allocation, so live scratch never exceeds one in-flight temp.
- This is an admission rule over measured usage, not a filesystem quota. An M-6 writer can exceed it.
- The carrier and its temps live in `session/`, not `preserved/`. Each leftover carrier temp is under 3 KiB, and repeated carrier-write deaths can accumulate them, as with the accepted SV023 carriers (inherited, stated).

---

## 8. Phase A transaction

1. **A0** Admission, P1–P14 (pure; inventory read #1).
2. **A1** Cleanup of owned scratch, if any (§7.2).
3. **A2** Directories:
   - `mkdir preserved/` if absent, then `fsync(session/)`;
   - `mkdir <ack_id>.partial/` if absent, then `fsync(preserved/)`;
   - each mirrored subdirectory needed, each followed by `fsync` of its parent.
   - Every fence runs even if the directory already existed (SV020-01).
4. **A3** Copies, in sorted path order, for every destination not already present and verified:
   - bounded read #2;
   - require size and SHA-256 equal to the inventory, else refuse `preserved_source_changed` (scratch is left for the next cleanup);
   - `write_bytes_durable(dest, data)`: `O_EXCL` temp, write all, fsync, rename, fsync(dir).
   - **Never `link()`**: copies are new inodes.
5. **A4** `write_bytes_durable(<ack_id>.partial/MANIFEST)`.
6. **A5** **Seal**: `rename(<ack_id>.partial, <ack_id>)`, then `fsync(preserved/)`. From here the set is immutable.
7. **A6** Carrier: `write_bytes_durable(session/ACKNOWLEDGED)`.
8. **A7** Retire STOPPED: unlink, then `fsync(session/)` (`cp.clear_stop`).

**Retry.**
- STOPPED present: redo from A0 with the §7.2 branch.
- STOPPED absent and this carrier held: re-fence `session/` and return the carrier (as `:709–711`).
- Anything else refuses.

Phase A writes no ledger record and contacts nothing.

---

## 9. Phase B transaction (consuming start; before any model call)

### 9.1 Uniform order (fresh run and restart alike)

**B0 Verify (pure), then fence.** `read_carrier` yields kind `preserving`. `_verify_preserving` checks, in order:
1. the carrier seal, pair and evidence keys;
2. the sealed set: the `MANIFEST` bytes hash equals `evidence.manifest_sha256`; the seal and paths are valid; **every** entry reads back under its bound with the manifested size and hash (read #3);
3. P3–P8 and P10 over `H` (the records `≤ W.last_seq`);
4. Π derived from `H` (§5.1), and the recomputed evidence equals the carrier's;
5. the owned sequence `O` (excluding records after an own intent's anchor, which `_recover` checks) is `Π[:k]`;
6. a tail, if there is no intent, is a strict byte prefix of the next own frame (`_next_own_frame` with `planned = Π`, written `= k`; a header at a segment boundary). If `k = |Π|`, no tail is allowed;
7. RECOVERING, if present, is anchored at or after `W.last_seq` with this pair's sealed context (§5.4);
8. **conversation rule:**
   - if Π's activation is **not** among the owned records, `conversation.json` must be present with `evidence.conv_sha256`;
   - if it **is** present, the file may be absent or have that hash.

Any failure stops `acknowledgement_unverified` with a problem token (`carrier`, `manifest`, `preserved_entry:<path>`, `ledger`, `own_prefix`, `conversation_changed`, `evidence_changed`). Only STOPPED is written; the carrier and the set are kept. On success, `fsync(session/)`.

**B1 Decision `BP`.** `_recover` takes the BP decision in place of `_classify_base`:
- replay = `R0` + `H`'s neutral records + the owned records in `p0`, each applied once;
- `checkpoints` = the known tuples above the collection floor, as `_classify_base` computes them;
- **core = Π[k:] + T**, where `k` = the owned logical records in `p0` and `T = []` unless an intent exists (§9.4);
- the SV023 receipt-prepend line (`:1040–1042`), `GC_DONE` prepend and `ADOPT` do not apply.

The existing tail and intent mechanics (`:1044–1094`) run unchanged: an own torn tail with no intent writes RECOVERING with the §5.4 context, then quarantines; extras must be a prefix of the core and never exceed it.

**B2 Continuation.** `Session._commit` each record of `core[len(extra):]`, each synced.

**B3 Establish owned durability** (new, before any destructive step):
- for every segment from `W`'s last segment through the active segment, open read-only and `fsync`;
- then `fsync(ledger/)`. The writer has already fenced `session/` for `ledger/`'s name (`continue_after`).
- When this returns, every owned record, including an activation **inherited** from an earlier process whose fsync never returned, is durable with its name.
- It runs even when this process wrote nothing.
- A failure goes through the session failure boundary (FSYNC_FAILED attempted, `PersistenceFailure`, exit 44). **`conversation.json` is untouched.**

**B4 Complete:**
- if `conversation.json` exists: bounded read, require `evidence.conv_sha256` (else stop `acknowledgement_unverified{conversation_changed}`, nothing unlinked), unlink it, `fsync(session/)`;
- if it is absent: `fsync(session/)` anyway, which makes durable an absence that an earlier process may have left unfenced.

**B5 Retire:**
- sync readable extras' segments (already covered by B3);
- `_consume_ack`: exactly one matching receipt, its segment fsynced, unlink ACKNOWLEDGED, `fsync(session/)`;
- then remove RECOVERING if present (carrier first, then intent: the SV023-03 order).

**B6** Exact IDENTITY reservation (never lower), then `unit_end()` (SV026/SV027). Return `Opening("BP", session)`.

**Three distinct notions, kept apart:**
- *readable activation*: its frame is present and valid;
- *established activation*: B3 returned in this process, covering it;
- *completed activation*: B4 fenced and the carrier is retired.

A process may establish a frame that an earlier process wrote and whose fsync never returned. That is legitimate, and nothing destructive precedes it. **Linearization of the new epoch** is the first returned fsync covering the activation frame. The runtime acts destructively only after its own B3 has returned.

No `REQUEST_SENT`/`INVOKING` is written and no client is constructed before B6 returns (`chassis.py:1152–1170`).

### 9.2 Restart that writes no core record

Here `k = |Π|` (the activation is readable from an earlier process, no tail). The order is:
1. B0 (fence);
2. B1 with an empty core;
3. B2 writes nothing;
4. B3 fsyncs the inherited segment(s) and `ledger/`, which establishes the activation;
5. B4 unlink and fence, B5, B6.

### 9.3 Carrier-free restart (RECOVERING present, ACKNOWLEDGED absent)

1. `_validated_intent` validates the intent and its §5.4 context (domain, checksum, digests).
2. Π is re-derived from `H` and authenticated (§5.4).
3. The owned logical records must be **exactly** `Π + T`. The carrier is retired only after B4, so the transaction is complete. Anything shorter or different stops `recovery_intent_mismatch`; **no missing Π record is written without a carrier**.
4. `conversation.json` must be absent, else stop `recovery_intent_mismatch`.
5. B3, B4 (fence of absence), remove RECOVERING, B6.

### 9.4 Composition with ordinary torn-tail recovery

- **Where `T` sits.** The recovery record of the intent's original torn tail is `T = [("RECOVERY", {"kind": "torn_incomplete", "detail": {…plan detail, "tail_sha256": intent.tail_sha256}})]`, built as `derive_core` builds recovery records (`:1620–1623`), never a spend.
- **Ordering.** `T` is placed **after** the whole of Π. This mirrors `derive_core`'s order: closure first, then recovery records.
- **Freezing.** The intent freezes the anchor (the last owned record before the tear: `k` is fixed), the original tail and the context. So `core = Π[k:] + T` is the same at every restart.
- **Tears under an existing intent.** A tear of the intent's own continuation is set aside under that same intent with **no new record** (`:1070–1078`). There is therefore at most one `T` per transaction.
- **B0 check.** B0 checks only `O ≤ anchor` against Π. Records after the anchor are checked by `_recover` against `core`. `T` can never appear `≤` an anchor, so B0's list and B1's comparison agree.

### 9.5 Explicit traces

`k` is the owned logical count. "dies" means M-1; host loss means M-2 with carried watermarks.

| Trace | Start 1 | Next start | Result |
|---|---|---|---|
| **receipt torn** | dies mid-write of Π[0] | B0: `k=0`, tail is a prefix of Π[0]. `_recover` writes intent (anchor `W.last`, context), quarantines the tail, commits Π[0..] + T. Then B3, B4, B5, B6 | owned = Π + [T(torn_incomplete, declared RECOVERY_ACK)] |
| **spend torn** (failed-unknown) | Π[0] synced; dies mid-Π[1] | intent anchored at Π[0]; core = Π[1:] + T | owned = Π + T; the spend applied once |
| **spend readable** | Π[0] synced; Π[1] written, not synced; dies | `k=2`; core = Π[2:] = [activation]; the spend is **not** re-derived away | owned = Π |
| **spend readable, then host loss** | as above, then M-2 cuts Π[1] whole or to a prefix | `k=1` (cut whole) or the spend-torn path | converges |
| **activation torn** | dies mid-activation | intent at the last owned record; core = [activation] + T | owned = Π + T |
| **activation readable** (SV028-01) | activation written, not synced; dies | §9.2: B3 establishes it, then unlink | correct |
| **…then second death after the unlink fence, then host loss** | start 2 dies after B4's `fsync(session/)`, before B5 | B3 had returned in start 2, so the activation survives host loss. Start 3: B0 (activation present, file absent: allowed), B3, B4 (fence absence), B5 | converges; one activation |
| **…second death inside B3, then host loss** | start 2 dies before B3's fsync returns | the file was never unlinked. Host loss may cut the activation, so start 3 has `k ≤ 2` and rewrites it | converges |
| **failed B3 sync** | EIO at B3 | `PersistenceFailure`; the conversation is intact; FSYNC_FAILED, then A1 (inherited SV023-02 policy: the A1 acknowledgement is refused while the carrier is pending) | no unlink |
| **second tear under the intent** | after a receipt tear, start 2 dies mid-activation | start 3: intent I1 present; the own tear is set aside without a record; core from I1 = Π[0:] + T(t1); extras = [Π[0]] | owned = Π + T(t1) |
| **carrier absent, RECOVERING present** | start dies after carrier retirement, before RECOVERING removal | §9.3 | intent removed; nothing written |

---

## 10. Crash, host-loss and name-loss cuts

| Cut | Outcome |
|---|---|
| A0 or refusal | unchanged |
| A1–A4 (cleanup unlinks, mkdirs, copy temps, renames, `MANIFEST`), including unfenced directory or file names lost under M-2 | STOPPED present: A0 at start. Retry: admission, then cleanup of owned scratch, then refill. A lost `<ack_id>.partial` name simply means none |
| A5 rename unfenced | under M-2 it may revert to `.partial` with a complete `MANIFEST`. Retry verifies and re-seals |
| A6 carrier unfenced, or A7 STOPPED unlink unfenced | STOPPED present again: A0. Retry finds the sealed set and this carrier, then re-verifies and re-fences |
| B0 | nothing written |
| B2 records (torn or unsynced) | §9.5 |
| B3 before return | file intact; activation possibly lost: rewritten |
| B4 unlink unfenced | under M-2 the file returns with the manifested bytes: unlink again after B3 |
| B5 carrier unlink unfenced | the carrier returns: B0 allows an absent file because the activation is present and established |
| after B5, intent removal unfenced | §9.3 |
| after all | ordinary A12t start, nothing written |

**Invariant at every cut** (asserted immediately after the cut and any simulated host loss, before convergence): if `conversation.json` is absent, then the ledger, as the durability model leaves it, holds the complete Π, with the activation inside the returned-fsync watermark. In addition, every sealed set equals the pre-command domain.

---

## 11. State authority after activation

`e = C_n.state.history_epoch`. The comparison is normalized as `wire(x) = x.to_wire(next_seq=1)`, the accepted helper's normalization. The physical sequence and chain are asserted separately: the first owned record has `first_seq/seq = W.last_seq + 1`, and the chain is verified by the strict scanner.

| Field | After | Authority / proof |
|---|---|---|
| lineage | retained | l.558; one lineage across header, run.json, state and IDENTITY (P3–P8) |
| `history_epoch` | `e+1` exactly once | frozen Π; the reducer asserts `epoch == e+1` (`chassis_replay.py:353`); the own-prefix rules forbid a second activation |
| messages, `recap_folded` | `[]`, 0 | `_switch_base`; the old bytes are sealed in the set before B4 |
| `requests.next` | **retained from `C_n`** (after a failed request, `send` had already advanced it to attempt+1) | P6 + Π |
| `requests.last` | retained; **in the failed-unknown variant its `outcome` becomes `possible_duplicate_spend`** | Π's spend, applied once |
| IDENTITY | retained; raised only by the exact reservation | P5; SV021-01 |
| notes (next_gen, adopted_through, pending + blobs, mirrors, handoff sha, dropped) | retained | P6, P7; never-reset rule |
| legacy, originals | retained | P6 |
| active_group / queued | null / `[]` | P7 |

So `wire(after) == wire(state0)` with `history_epoch = e+1`, `recap_folded = 0` and (failed-unknown only) `requests.last.outcome = "possible_duplicate_spend"`. Its `next_label()` is `lineage:<C_n.requests.next.turn_seq>:<C_n.requests.next.attempt>`, i.e. `lineage:t:2` in the failed-unknown variant.

---

## 12. Duty-visible semantics (resolved as engineering) and GC

**E1+S1+R1+N1**, as confirmed by the review:
- `EXTERNAL_DELETE` with an exact `cause`/`ack_id`/`manifest_sha256` binding;
- A12's resume order: `adopt_file_edit`, then `adopt_notes`, then `bootstrap()` (or `DEFAULT_OPENING`) **only if the list is still empty**;
- `recap.md` left in place (its bytes sealed);
- notes carried.

S1 therefore means **pending notes make the conversation non-empty and preempt the bootstrap callback**. A session with no pending note gets the bootstrap or default opening. Nothing promises a bootstrap despite pending memory. No new notice, ordering or held-policy choice is introduced. Each real session still needs its operator's explicit choice; this package authorizes temporary-root implementation and tests only.

**GC (corrected).**
- `preserved/` is outside the GC namespace (`chassis_gc.py:27–32`).
- `STOPPED` and `ACKNOWLEDGED` block collection during the transaction (`chassis_session.py:120`, `:703–706`).
- A pending intent is refused (P4).
- After activation, ordinary §1.4.5 GC applies unchanged to the live store. The first post-activation checkpoint names as `prev` whatever `_retained_prev` finds: **an older known checkpoint still in `.prev.json` is kept and named**, so collection may begin at that first checkpoint. No first- or second-checkpoint prediction is made.
- Quarantine usage counts `corrupt/` only.

---

## 13. Source-to-change map

| File | Change |
|---|---|
| `services/chassis_startup.py` | **Registry (§4).**<br>**`acknowledge`:** `home_dir` keyword (default `session_dir.parent`); dispatch by mechanism.<br>**`read_carrier` / `carrier_problem`:** mechanism envelopes; evidence keys (§5.3).<br>**`witnessed_context_problem`:** per-mechanism key sets (§5.4).<br>**New pure functions:** `preserving_plan`, `preserving_admission`, `preservation_domain`, `preserved_usage`, `manifest_bytes`/`manifest_problem`, `preserving_evidence`.<br>**New mutation:** `_acknowledge_preserving` (A1–A7).<br>**`_Context`:** `_verify_preserving` (B0); BP decision in `_recover`; `_establish_owned_durability` (B3); `_finish_case("BP")` (B4); carrier-free path (§9.3); `_consume_ack` treats the preserving receipt like the witnessed one.<br>Module docstring |
| `services/chassis.py` | CLI: pass `home_dir=chassis.home_dir` to `acknowledge` (one call site, `:1765`) |
| `services/chassis_persistence.py`, `chassis_replay.py`, `chassis_session.py`, `chassis_gc.py`, `common.py` | none |
| `tests/test_chassis_acknowledgements.py` | the one `SUPPORTED` tuple (§4) |
| `tests/test_chassis_bootstrap_preserving.py` | new (§14) |

There are no new record types, no `REQUIRED_KEYS` change and no reducer change.

---

## 14. Finite temporary-root test plan (frozen; nothing run)

### 14.1 Harness

The harness is test-local, built from accepted helpers only.

- **`HomeRoot(Root)`**: `home = path`, `session = path/"session"` (the production layout). `acknowledge` can then be called with its unchanged positional signature, and the default home is correct. `snapshot()` covers the whole domain.
- **`PreserveOps(AckOps)`** (extends `test_chassis_acknowledgements.AckOps`/`CutOps`). It additionally records, per parent directory, until that directory's returned `sync_dir`:
  - directories created by `mkdir`;
  - file names created by `open(O_CREAT)` on a new path;
  - **directory renames**.
- **`host_loss_names(ops)`** undoes those newest-first:
  - removes unfenced created directories (with their subtrees) and unfenced new file names;
  - renames unfenced directory renames back;
  - applies the existing byte and rename/unlink rules.
- **Watermarks** (segment bytes and pending names) are carried across processes by `PreserveOps(previous)`.
- **Scope.** This models M-2 for every namespace this package creates. Non-segment file bytes are written by `write_bytes_durable` (fsync before rename), so their loss is modelled through name loss.
- **Independent declared inventory.** The test computes, before the command and **without** the production selector: every regular file under `session/` excluding `preserved/` and acknowledgement artifacts, plus `HANDOFF.md`, as `{path: (bytes, st_dev, st_ino)}`.

### 14.2 Fixtures

All neutral fixtures use `HomeRoot`, `establish`, a pending note `N1` (unless stated), one complete tool turn (`partial_turn(6)`), then:

| Fixture | Construction | Suffix after `C_n` | Notes |
|---|---|---|---|
| `run-end` | `checkpoint()` (`C_n`), `record_run_end(0, "main_returned")` | `[RUN_END]` | — |
| `collected-and-rotated` | `test_chassis_gc.begin` (collect, `segment_max = 1`), note, two `tool_turn`s, `record_run_end` | contains `GC_INTENT`, `GC_DONE`, `LEDGER_HEADER`, `RUN_END` | the fixture **asserts** at least one `GC_INTENT` naming a segment and one `LEDGER_HEADER` after `C_n` (non-vacuity) |
| `failed-unknown-request` | `session.send(lambda: None)` without a response, `checkpoint()`, `record_run_end` | `[RUN_END]` | `C_n.requests.last.outcome == "failed_unknown"`, `requests.next = (t, 2)` |
| `no-pending-note` | as `run-end` without `N1` | `[RUN_END]` | — |
| `older-known-prev` | checkpoints C1, C2, C3 = `C_n`; `.prev.json` replaced by C1's saved bytes; only `conversation.json` damaged | — | `C_n.prev` names C2, so the case is unbound (P10) while `.prev.json` holds known C1 |
| **planted** additions (N3a) | `session/agent-notes.txt`; `recap.md`; `HANDOFF.md`; a file `Y` at `corrupt/conversation-<sha256(X)[:16]>` | — | `X` is the garbage a later A14 quarantine will write there |

Each fixture then damages `conversation.json` (and `.prev.json` except in `older-known-prev`). The actual start must stop A14-unbound with a valid witness, changing only `session/STOPPED` (the accepted `stop` pattern).

### 14.3 New nodes: `tests/test_chassis_bootstrap_preserving.py` (36)

| Id | Node (exact parameters) | Asserts |
|---|---|---|
| N1 ×3 | `test_sv028_bootstrap_preserving_starts_exactly_one_new_epoch[run-end\|collected-and-rotated\|failed-unknown-request]` | **Sealed set:** byte-equal to the independent inventory (§14.1); every copy has an `st_ino` not among the **pre-command** live inodes, and `st_nlink == 1`.<br>**Protocol records** (non-header owned) exactly Π (spend only in failed-unknown); headers asserted separately; no later records at default limits.<br>**State:** §11 normalized equality; `next_label()` as §11.<br>**Files and effects:** `conversation.json` absent; no STOPPED/ACKNOWLEDGED/RECOVERING/FSYNC_FAILED; effect counts unchanged.<br>**Later start:** `A12t`, writes nothing |
| N2 ×2 | `test_sv028_resume_after_activation_matches_the_same_state_a12_path[pending-note\|no-pending-note]` | Through the accepted `resume()` helper: the BP list equals a same-state A12 control (conversation **deleted**). With a pending note: exactly `[note N1]`, **no opening**. Without: `["OPENING"]` |
| N3a | `test_sv028_every_declared_pre_resolution_file_survives_later_ordinary_replacement` | Planted fixture, activation, then ordinary operations: `write_note` (replaces HANDOFF), `append_recap` (`chassis.py:275`), two checkpoints (run.json, `.prev` rotation, IDENTITY), collection, then `X` written into `conversation.json` and a start that classifies A14 and quarantines `X` over planted `Y`. The sealed set still equals the independent inventory, including `agent-notes.txt` and `Y` |
| N3b | `test_sv028_an_older_known_previous_file_is_retained_and_collection_follows_the_reference_graph` | `older-known-prev`. The first post-activation checkpoint names C1 as `prev`. Its collection (asserted present) names exactly items eligible under `gc.retained_basis`, none under `preserved/`, and the set is unchanged |
| N4a | `test_sv028_every_envelope_refusal_names_its_reason_and_changes_nothing` | One node over cases, each matching its token, with the full root snapshot unchanged:<br>• `suffix_not_neutral` ×4 (partial-turn, message, note-written, earlier receipt);<br>• `conversation_readable`, `conversation_absent`, `conversation_over_bound` [injected];<br>• `previous_base_available`, no-witness, damaged witness;<br>• `ledger_not_witnessed` ×2 (appended record, garbage tail);<br>• `identity_not_witnessed`, `state_blob_missing`, `run_json_not_witnessed`, `collection_pending_or_unauthorized`, `transaction_open` ×2;<br>• another carrier pending;<br>• the pair with `run_json_unreadable` / `ledger_tail_ambiguous` / `ledger_missing` ("not implemented") |
| N4b | `test_sv028_every_unsupported_shape_is_refused_before_any_mutation` | A symlink in `session/`; a subdirectory in `ledger/`, `blobs/` or `corrupt/`; an unknown top-level directory; a FIFO; a bad name; a symlinked HANDOFF; a foreign shape under `preserved/`; both `<ack>` and `<ack>.partial`; a damaged sealed own set (`preserved_set_mismatch`, untouched) |
| N5 | `test_sv028_the_command_and_the_activation_are_ordered_and_fenced` | From the log:<br>• copies (each rename then directory fence) < `MANIFEST` < seal rename + `sync_dir(preserved)` < carrier + `sync_dir(session)` < STOPPED unlink + fence;<br>• start: `sync_dir(session)` < receipt write and fsync < (spend) < activation write and fsync < **B3 segment fsync + `sync_dir(ledger)`** < `unlink conversation.json` + `sync_dir(session)` < receipt-segment fsync < ACKNOWLEDGED unlink + fence < IDENTITY;<br>• no `link` call |
| N6 ×2 | `test_sv028_every_cut_converges_to_one_receipt_and_one_activation[process-death\|host-loss]` | `run-end` with planted files. Sweep every logged call of A and B. At each cut (and after `host_loss_names` in host-loss mode), the §10 invariant holds **immediately**. Then converge: repeat the command if STOPPED is present; start; a second start writes nothing. Final: one receipt, one activation, §11 state, the set equals the inventory |
| N7 ×4 | `test_sv028_a_second_interruption_then_host_loss_still_converges[activation-readable/after-unlink-fence\|receipt-unsynced/activation-write\|archive-directory-unfenced/manifest-write\|conversation-unlink-unfenced/carrier-unlink]` | Carried byte and name watermarks over both processes, then host loss, then two restarts. The first parameter is the **exact SV028-01 trace**: P1 crashes on the activation fsync (frame `"14"`); P2 (carried) crashes on the first call after B4's `sync_dir(session)` |
| N8 ×5 | `test_sv028_an_own_partial_prefix_composes_with_the_frozen_plan[receipt-torn\|spend-torn\|spend-readable\|activation-torn\|carrier-absent-recovering-present]` | The §9.5 rows. The spend cases use `failed-unknown-request`. Owned records are exactly Π or Π + [T] with the intent's tail hash; exactly one spend; epoch `e+1` |
| N9 | `test_sv028_stale_or_conflicting_acknowledgements_grant_nothing` | A SV023 carrier pending, then this command: refused. This carrier pending, then `continue-from-bound`: refused. Repeat after STOPPED removal: fence only. Consumed, then repeat: refused. An old carrier over a later same-reason stop: refused, then `acknowledgement_unverified`. Changed between command and start (conversation repaired, record appended, sealed byte flipped, `MANIFEST` byte flipped): `acknowledgement_unverified`, nothing activated. Independent FSYNC_FAILED: A1, and the A1 acknowledgement refused "pending" |
| N10 | `test_sv028_a_conflict_after_activation_fails_closed` | Activation established (crash after B3), then a readable list under the name: stop `conversation_changed`, nothing unlinked, carrier kept |
| N11 | `test_sv028_cli_bootstrap_preserving_behind_the_first_request_barrier` | Real CLI (`Loop`, as `test_cli_acknowledgement…`): stop exit 44; command exit 0, no traffic; restart behind the barrier: no traffic, carrier and STOPPED gone, Π in the ledger; release: the label is `lineage:<next>:1`, unseen. The sealed set verifies against the independent inventory |
| N12 ×4 | `test_sv028_mutation_control[hardlinked-copies\|no-neutral-suffix-check\|no-pre-unlink-sync\|plan-from-mutated-replay]` | Each patches one mechanism and requires the protecting assertion to **fail**:<br>• `link` for copies: an ordinary append to the active segment changes the "preserved" segment;<br>• P7 disabled: the W2 fixture activates and drops suffix memory;<br>• B3 a no-op: N7[activation-readable…] does not converge;<br>• Π derived after own extras: the spend-readable trace stops `own_prefix` |
| N13 | `test_sv028_the_registry_is_one_truthful_union` | `IMPLEMENTED_RESOLUTIONS` = the 6 pairs; mechanism subsets exact; every other `(reason, resolution)` over the accepted `OTHER_REASONS` list raises "not implemented" with the store unchanged |
| N14 | `test_sv028_a_failed_pre_unlink_sync_leaves_the_conversation_and_takes_the_persistence_boundary` | EIO at B3's segment fsync (restart with the activation readable): `PersistenceFailure`; `conversation.json` still has the manifested bytes; FSYNC_FAILED exists; the next start is A1 |
| N15 ×6 | `test_sv028_capacity_and_serialization_bounds[repeated-copy-temp-crashes\|rewrite-peak\|manifest-exact-limit\|manifest-over-limit\|long-neutral-suffix\|cap-boundary]` | Five crashes, each right after a copy temp write: `preserved/` usage never exceeds the computed peak, and the sixth attempt converges. An existing mismatching destination is deleted before its temp (peak = the formula). Injected `MANIFEST_READ_MAX` equal to the exact length: accepted; one below: `preserved_manifest_too_large`, unchanged. 2,000 appended `RUN_END`s: the carrier size is unchanged and under the bound. Bytes cap at exact equality: accepted; minus one: refused, unchanged |

N1 ×3, N2 ×2, N3a, N3b, N4a, N4b, N5, N6 ×2, N7 ×4, N8 ×5, N9, N10, N11, N12 ×4, N13, N14, N15 ×6 = **36**.

**Collection on the old runtime.** The new module defines `HomeRoot`/`PreserveOps` locally and imports only accepted test modules. D1–D3 call `st.acknowledge(session_dir, reason, "bootstrap-preserving")` or the CLI, with no new keyword, and reference no new runtime attribute at import or setup. New attributes (e.g. `PRESERVING_RESOLUTIONS`) are referenced only inside N13 and N15.

### 14.4 Retained nodes (50)

**R1, `tests/test_chassis_acknowledgements.py` (35):**
- `test_a_witnessed_file_repair_stop_resumes_from_the_bound_checkpoint[a14]`, `[ck5]`
- `test_the_same_command_repeated_is_idempotent[a14]`
- `test_every_refusal_leaves_the_store_byte_identical[a14]`, `[ck5]`. Its `wrong-resolution-bootstrap` case on a repaired store is now refused by P9 `conversation_readable`; its assertions (`LedgerError`, byte-identical) are unchanged.
- `test_the_refusal_matrix_control_the_unmutated_repair_is_accepted`
- `test_stops_without_a_safe_witness_are_recorded_as_before_and_ineligible`
- `test_an_a14_stop_over_a_pending_collection_carries_no_witness`
- `test_only_the_two_new_pairs_are_added_and_every_other_pair_is_still_refused` (**with the §4 `SUPPORTED` edit**)
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

Ids follow the accepted manifests' convention (inner parametrize first). Each is confirmed by static AST before running.

### 14.5 Pre-fix (unchanged runtime; one node per command)

| Id | Node | Expected |
|---|---|---|
| B0 | `test_c_k3_a12_a_deleted_list_is_a_clean_slate_with_everything_kept` | pass |
| D1 | `N1[run-end]` | fails at the acceptance call: `LedgerError … not implemented` |
| D2 | `N4a` | fails at its first reason-token `match` (the base says "not implemented"). This is a reason-specific refusal control, **not** evidence of activation safety |
| D3 | `N11` | fails at `ack.returncode == 0` (the base returns 2) |

Activation-safety evidence comes from N6–N8, N12 and N14 after the change. N12 is the mutation evidence that those assertions discriminate.

### 14.6 Commands and resource estimate

Each command is the approved runner with literal targets, one per message, serially, under the unchanged caps (120 CPU s / 180 wall s / 512 MiB AS; aggregate 50% CPU / 2 GiB / 64 tasks / nice 15).

| Cmd | Content | Cases | Estimate |
|---|---|---|---|
| F1 | N1×3, N2×2, N3a, N3b, N4a, N4b, N5, N9, N10, N13, N14 | 14 | ≈ 70 fixture builds ≲ 20 s CPU |
| F2 | N6[process-death] | 1 | ≈ 120 logged calls (≈ 14 domain files) × ≈ 0.25 s ≈ 30 s CPU |
| F3 | N6[host-loss] | 1 | as F2 |
| F4 | N7×4, N8×5 | 9 | ≲ 15 s CPU |
| F5 | N12×4, N15×6 | 10 | ≲ 20 s CPU |
| F6 | N11 | 1 | ≈ 10–20 s wall |
| R1 | retained acknowledgement nodes | 35 | SV023 ran 97 of these in one command within the caps |
| R2 | retained CLI node | 1 | ≈ 10–20 s wall |
| R3 | retained recovery, notes, GC, rotation | 14 | ≲ 20 s CPU |

**Totals: 36 new + 50 retained = 86 cases in 9 commands, plus 4 pre-fix commands.** Fixture data is KB-sized and the caps are injected small. These are proposed counts only.

---

## 15. Limits (candid) and what is not claimed

1. **RSS is unproved.** Admission and Phase B hold:
   - every segment's bytes (`read_segments`, up to `MAX_SEGMENT_READ` each);
   - the scan's parsed records;
   - replay states;
   - one domain file at a time (≤ 64 MiB);
   - the manifest.

   Phase B also verifies the whole set. No peak-memory bound is claimed.
2. **Aggregate reads per acknowledgement:**
   - Phase A reads all segments and the domain twice (hash pass and copy pass);
   - Phase B reads all segments (as any start does) and the sealed set once, plus a bounded read of `conversation.json`.

   Disk use grows by the set, within §7.4's admission bound.
3. **Inherited wedges (not changed):**
   - a persistence failure while a carrier is pending leads to an A1 stop whose acknowledgement is refused (SV023-02);
   - a post-activation M-6 conflict stops with no resolution;
   - carrier-temp leftovers in `session/` can accumulate across repeated carrier-write deaths.
4. **M-6:** `preserved/` is agent-reachable and is a reliability aid, not evidence. The caps are an admission rule, not a quota.
5. **Not claimed:** real-session acknowledgement, deletion or resumption; kernel or power-loss behaviour (M-2 is simulated); partial-I/O guarantees beyond the existing helpers; numerical replay, segment or read bounds; any other stop or resolution; TC4 widening; H/T/Q/pump/history policy; provider behaviour, merge or deployment.

## 16. Questions for Astra

1. Is the sealed four-key preserving context (§5.4), authenticated against the ledger head, an acceptable resolution of carrier-free resumption?
2. Is the domain (§7.1) the right preservation promise? It covers all of `session/` (excluding `preserved/` and carrier artifacts) plus the named `HANDOFF.md`, and refuses unsupported shapes.
3. Are the `.partial`, then seal-by-rename, then immutable lifecycle and the owned-scratch cleanup (§7.2) acceptable?
4. Is the one `SUPPORTED` edit the right capability-pin change?
5. Are 86 cases in 9 + 4 commands sufficient, including the `PreserveOps` name-loss model?
