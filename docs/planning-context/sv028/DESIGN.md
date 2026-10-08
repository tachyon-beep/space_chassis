# SV-028 design: one narrowly admitted `bootstrap-preserving` acknowledgement

**Status: design only, for independent Astra review. Not implemented. No test was run. No runtime or test file was changed.**

Provenance:
- Base inspected: accepted commit `5c2366cef7851b39d5363bdadcce3e1c0b25711c` (SV016–SV027 accepted in their own scopes; `docs/planning-context/sv027/ASTRA-ACCEPTANCE.md` read, nothing reopened).
- Canonical text: SV-013 §2.2.2 (session files, CK1–CK6, the authority rule, A0–A15, the acknowledgement paragraph), SV-013 §2.2.5 (notes, identity closure, GC), SV-015 v2 §1.1–§1.4 (fault model, framing, tail classes and acknowledgement, checkpoint graph/GC/transitions). §1.3 is quoted where it names `bootstrap-preserving`.
- Accepted local design evidence: `sv023/` (witnessed carrier), `sv024/` (fences), `sv026/` (accounting), `sv027/` (closed-boundary rotation).
- Code read: `services/chassis_startup.py` (whole), `chassis_persistence.py` (framing tables, mutation layer, quarantine, conversation install), `chassis_session.py` (identity, fresh start, notes, checkpoint, collection), `chassis_replay.py` (state, reducer), `chassis_gc.py` (plan, namespace), `chassis.py` (`run`, `resume_session`, CLI, recap paths).
- Tests read: `tests/test_chassis_acknowledgements.py` (fixtures, refusal matrix, cut sweeps, CLI), `tests/test_chassis_recovery_live.py` (harness, A0/A1/A6/A12/A14, SV021-04).

---

## 0. The proposal in one paragraph

Admit exactly one new pair: **`conversation_unreadable_unbound` + `bootstrap-preserving`**. The stop must carry a valid SV023 witness, and the ledger after the witnessed newest checkpoint `C_n` may hold only **state-neutral** records (`LEDGER_HEADER`, `RUN_END`, and complete `GC_INTENT`/`GC_DONE` pairs). Everything else stays refused, and the missing semantics are named (§3).

**Phase A (the operator command).** It runs a pure admission (§4). It then copies, as independent bytes, every session file that activation or later ordinary operation could rewrite or remove into `session/preserved/<ack_id>/`. A sealed `MANIFEST` is written last. The command then makes a sealed carrier durable and removes STOPPED.

**Phase B (the consuming start).** It re-verifies the carrier, the manifest and every preserved byte before changing anything. It then writes `RECOVERY_ACK` first and the accepted TC0 closure (at most one `possible_duplicate_spend`). Then it writes **one** activation record, `EXTERNAL_DELETE{epoch: e+1, notices: [], cause: "bootstrap_preserving", ack_id, manifest_sha256}`, whose fsync is the **linearization point**.

After the linearization point, the start unlinks the now-preserved unreadable `conversation.json` and fences `session/`. Only then does it retire the carrier, reserve IDENTITY and return. The reducer, the binding rule and every later start treat the result as the already-accepted A12t path. Lineage, request identity, note state, legacy status and originals are carried from `C_n.state` unchanged. `history_epoch` advances exactly once, by one. The duty-visible semantics the source does not settle are offered as alternatives with a recommendation (§6), not chosen silently.

---

## 1. Canonical facts this design rests on

| Source | Text (abridged, exact where quoted) | Used for |
|---|---|---|
| SV-013 §2.2.2 l.558 | "`--acknowledge-stop <reason> --resolution continue-from-bound\|bootstrap-preserving`, which appends `RECOVERY_ACK{reason, resolution}` and removes `STOPPED`. `bootstrap-preserving` keeps every file and starts epoch+1; it is the operator's explicit choice, never automatic." | The resolution exists, preserves every file, advances the epoch by one, and needs an explicit operator act. **Same lineage**: it says epoch+1, not a new lineage |
| SV-013 §2.2.2 authority rule | "An unreadable file is never treated as absent … nothing bootstraps over memory that may exist." | Why the unreadable file must be *preserved* and then removed by name, not reinterpreted (§7.4) |
| SV-013 A14 row | "Ledger valid; conversation unreadable … if no bound base → `STOPPED{conversation_unreadable_unbound}`" | The admitted stop |
| SV-013 A12 row | "`EXTERNAL_DELETE{epoch+1}`; bootstrap; `prev` and ledger preserved" | The only accepted precedent for "empty base at epoch+1 over an existing lineage" |
| SV-013 §1.4 registry | `history_epoch`: "int, +1 per replacement or external edit … separates duty edits from loss" | Exactly one +1 transition, in the ledger |
| SV-013 §2.2.5 rule 3 / v2 §1.4.3 | the adoption watermark is "never reset by eviction, folding, `set_history`, edits" | Note state is carried, not reset |
| v2 §1.1 M-1…M-6 | process death, honest host loss, checksum-only corruption detection, no reversion, single writer; same-UID hostility out of model | The crash/host-loss matrix; preserved bytes are a reliability aid, not evidence |
| v2 §1.3 TC4 acknowledgement | "Resolution `bootstrap-preserving` (D13) remains the alternative." | Named for TC4 too; **not admitted here** (§3, row T1) |
| v2 §1.4.5 | "Never GC'd: `conversation.json`, `conversation.prev.json`, `corrupt/`, `STOPPED`, `FSYNC_FAILED`." Only intent-named items are removed | GC exclusion (§9) |
| v2 §1.4.8 | quarantine pre-admission is a **strict** cap: refuse before copying | The preserved-set caps are strict pre-admission too (§7.3) |
| v2 §1.2 | `RECOVERY_ACK` type 0x10 `reason, resolution`; `EXTERNAL_DELETE` 0x14 "as D13" | No new type id is needed (§6, Q5) |

---

## 2. What the accepted runtime does today

- `chassis_startup.acknowledge` (`services/chassis_startup.py:232–267`) refuses every pair outside `IMPLEMENTED_RESOLUTIONS` (`:96–106`) with "not implemented … nothing was changed". `bootstrap-preserving` is refused for every reason (module comment `:90–93`; SV021 RECEIPT l.61; SV023 STATUS item 6).
- `cp.acknowledge_stop`'s `DEFAULT_RESOLUTIONS` (`chassis_persistence.py:1011–1014`) names `bootstrap-preserving` as a low-level filter. It authorizes nothing (SV023 design item 1; pinned by `test_only_the_two_new_pairs_…`, `tests/test_chassis_acknowledgements.py:493–519`).
- **A14-unbound stop.** `_classify_base` (`chassis_startup.py:1271–1274`) raises `conversation_unreadable_unbound` when the file is unreadable and neither file holds `C_n`'s bytes, nor a previous base verifies. Its detail carries a witness only when `stop_witness` (`:409–454`) finds:
  - a strictly clean end (TC0, no A2);
  - no RECOVERING, ACKNOWLEDGED or FSYNC_FAILED;
  - no pending or unauthorized collection;
  - a valid `C_n.state`;
  - IDENTITY checked and covering every used turn.
- **Witnessed carrier (SV023).** The command verifies and then makes a sealed carrier durable before removing STOPPED (`:697–727`). The consuming start re-verifies it before any change (`:857–877`) and writes the receipt first (`:1040–1042`). It retires the carrier only over one synced matching receipt (`:1378–1408`) and then the intent (`:1129–1136`). Own torn frames go through RECOVERING with a sealed `witnessed` context (`:1055–1058`, `:1515–1537`).
- **A12** writes `EXTERNAL_DELETE{epoch+1, notices}` (`:1346–1348`). The reducer bumps the epoch once (`chassis_replay.py:352–356`) and switches to an empty base, `recap_folded` 0 (`:511–528`). `_binding` treats it as binding an absent file (`chassis_startup.py:1439–1440`). The next start is A12t (`:1266–1268`).
- **After startup.** `Chassis.resume_session` (`services/chassis.py:1322–1346`) adopts an edited HANDOFF.md, then every pending note generation. Only if the list is still empty does it call the duty's `bootstrap()` (else `DEFAULT_OPENING`). For A12 this is accepted behaviour (`test_sv021_04_one_deletion_is_consumed_once_across_restarts`, `tests/test_chassis_recovery_live.py:1119–1144`).
- **GC** names only `ledger/NNNNNN.svl` by number and `blobs/<64 hex>` by name (`chassis_gc.py:27–32`, `:161–166`, `:178–213`). It never starts while `RECOVERING`, `ACKNOWLEDGED`, `STOPPED` or `FSYNC_FAILED` exists (`chassis_session.py:120`, `:703–706`).
- **Files later operation rewrites or removes:**
  - CK3/CK4 replace `conversation.json` and rotate it into `conversation.prev.json` (`chassis_persistence.py:1505–1538`). That rotation removes a leftover `.prev.tmp` (`:1526–1528`).
  - CK5 replaces `run.json`.
  - `reserve_turns` replaces `IDENTITY` (`chassis_session.py:293–305`).
  - `append_recap` replaces `recap.md` (`chassis.py:275–285`).
  - GC unlinks old segments and blobs.

---

## 3. Which stop, and why only one

A resolution may carry lineage, request identity and note state into a new epoch only if each of those facts is **proven** by records the accepted runtime already trusts. In particular:
- request identity must be bounded by a checked IDENTITY reservation, never inferred from a ledger that is merely clean now;
- note state must be exactly a verified checkpoint state.

| # | Stop reason | Predecessor facts available | Decision | Missing semantics (reported, not guessed) |
|---|---|---|---|---|
| **W1** | `conversation_unreadable_unbound` **with valid witness, state-neutral suffix** | Lineage (witness = ledger header = run.json = state = IDENTITY). Strict TC0 end. Verified `C_n.state` (notes, requests, legacy, originals) and its blobs. IDENTITY equals the witness and covers every used turn. Suffix records do not change state (reducer has no handler for `LEDGER_HEADER`, `RUN_END`, `GC_INTENT`, `GC_DONE`: `chassis_replay.py:387–396`) | **Admitted** | Duty-visible activation details (§6) |
| W2 | same, suffix has message/request/note/recovery records (an open group, `MSG_APPEND`, `NOTE_WRITTEN`, `REQUEST_SENT`, `RECOVERY`, an earlier `RECOVERY_ACK`, `RECAP_FOLD`, …) | State after the suffix is computable by lenient replay, but the suffix's *messages* are recoverable from the ledger alone | Refused | Whether suffix-only memory (recoverable without the base) is discarded or carried into the new epoch. How an open group must close before a base switch. Whether an adoption or drop after `C_n` is re-reported. Neither SV013 nor v2 says |
| W3 | same, **no witness** (torn tail, open RECOVERING, carrier, FSYNC_FAILED, pending/unauthorized GC, unchecked IDENTITY) | None proven at the stop | Refused (existing "no valid witness" refusal) | A predecessor-fact witness for those shapes |
| C1 | `run_json_unreadable` (witnessed) | Same proof as W1 | Not admitted (one case only) | Source does not say whether bootstrapping over a *bound, readable* conversation is ever wanted for a metadata fault. `continue-from-bound` already exists |
| T1 | `ledger_tail_ambiguous` (v2 §1.3 names `bootstrap-preserving`) | Request identity bounded by IDENTITY (SV021-01) | Refused | Hidden records may hold `NOTE_WRITTEN` (no note-generation reservation exists), `HISTORY_REPLACED`/`EXTERNAL_*` (hidden epoch steps, so "epoch+1 exactly once" cannot be proven) and hidden pending notes. Continuing the chain needs P's end, which needs the tail set aside first. That is a combined transaction no source specifies |
| L1 | `ledger_missing` (A7), `checkpoint_ahead_of_ledger` (A15), `ledger_prefix_missing`, `ledger_unreadable`, `ledger_damaged_at` (A2) | No verified checkpoint state; lineage only from agent-writable run.json | Refused | A lineage-continuation authority without a ledger. Whether a *new* lineage is acceptable (SV013 says epoch+1, which implies the same lineage) |
| L2 | `replay_mismatch`, `checkpoint_state_invalid`, `identity_unproven`, `identity_inconsistent` | State or identity disproved | Refused | — |
| L3 | `legacy_conversation_unreadable` (A6) | No lineage and no epoch exist | Refused | "epoch+1" is undefined before format 2. R11-5 made this a stop on purpose |
| L4 | `run_json_missing` | Ledger and checkpoint intact, but no witness is captured for this stop | Refused | A witness for this stop (SV023 did not add one) |
| O | `fsync_failed_previous_run`, `corrupt_quarantine_full`, `recovery_intent_*`, `gc_intent_invalid`, `ledger_changed_during_recovery`, `acknowledgement_unverified` | Durability unknown, capacity, or an open transaction | Refused | — |

**On "a merely clean repaired ledger".** The request-identity bound is the checked IDENTITY reservation, equal to the witness's `identity_reserved`. It is never `max(turn_seq)` read from a clean ledger. A witness exists only over a strictly clean end with no transaction of its own (`stop_witness` conditions above). A ledger that is clean only because an earlier recovery set a tail aside still holds that recovery's `RECOVERY`/`SYNTH`/`UNRUN` records after `C_n`. They are not state-neutral, so the case is W2 and refused. A repair already *covered by* `C_n` is covered by a checkpoint state the accepted runtime treats as authority (A9). Nothing is inferred from cleanliness. No note-generation bound is inferred at all: note state is `C_n.state.notes` verbatim.

**CLI.** `argparse` is unchanged (it takes free strings). `acknowledge` gains exactly one dispatch for this one pair. All other `(reason, bootstrap-preserving)` pairs keep today's "not implemented … nothing was changed" error.

---

## 4. Admission envelope (pure; every check before any write)

`preserving_admission(session_dir, ops) -> Admission | AcknowledgementRefused` runs in this order and writes nothing. Any failure raises `AcknowledgementRefused` (a `cp.LedgerError`): CLI exit 2, and the store is byte-identical including `preserved/`.

| # | Check | Code reused |
|---|---|---|
| P1 | STOPPED readable within `MAX_MARKER_READ`; `reason == conversation_unreadable_unbound`; `detail.witness` passes `witness_problem(…, reason)` | `cp.acknowledge_stop`, `witness_problem` (`:457–497`) |
| P2 | `read_carrier` is `absent`, or the *same* preserving carrier (same `ack_id`: idempotent retry, §8.1). Any other carrier refuses ("another acknowledgement is pending", SV023-02). No `RECOVERING`, no `FSYNC_FAILED` | `read_carrier` (`:274–303`) |
| P3 | Ledger: the oldest header's lineage equals the witness. Strict scan, no stop, no tail. Head anchor `(first_seq, last_seq, last_chain, last_segment)` equals the witness. Physical end `(end_segment, end_offset)` equals the witness. **No record after the witnessed end** | as `witnessed_evidence` `:570–587` |
| P4 | `gc.unauthorized_prefix(head) is None`; `gc.pending_intent(head) is None` | `:603–609` |
| P5 | `read_identity == witness.identity_reserved` | `:610–612` |
| P6 | Newest CHECKPOINT tuple, chain and `run_sha256` equal `witness.checkpoint`. `SessionState.from_wire` validates. Every `blobs_live` blob reads and hash-verifies | `:613–620`, `:649–652` |
| P7 | **State-neutral suffix:** every record with `seq > C_n.seq` has type in `NEUTRAL = {LEDGER_HEADER, RUN_END, GC_INTENT, GC_DONE}`. Every `GC_INTENT` there has its `GC_DONE` (already implied by P4) | new |
| P8 | `run.json` within `META_READ_MAX`; SHA-256 equals `C_n.run_sha256`; `format == 2`, `lineage_id`, `checkpoint.covers_seq`, `checkpoint.conv` agree | as `:633–648` |
| P9 | `conversation.json` **present**, a regular file (`lstat`), read within `CONVERSATION_READ_MAX`, and `parse_messages(data) is None`. Each failure has its own refusal text:<br>• **absent:** "the ordinary start is A12; no acknowledgement is needed";<br>• **readable list:** "the stop no longer holds";<br>• **over the bound:** "cannot be preserved under the bounded read" | `read_conversation` (`:175–182`) |
| P10 | **Still unbound**: neither file's SHA-256 equals `C_n.conv.sha256`, and `_previous_base` yields `(None, None)`. A `replay_mismatch` there also refuses: the case is no longer A14-unbound | `_previous_base` (`:1284–1307`, reads only) |
| P11 | **Immutable inventory** (§7.2). Every entry is a regular file (`lstat`, no symlink followed), read once under its own bound, recorded as `(path, bytes, sha256)`. Any `ReadTooLarge`/`OSError` refuses | new |
| P12 | **Strict caps** (§7.3): existing preserved usage (excluding this `ack_id`'s own directory) + this inventory ≤ `PRESERVED_MAX_{SETS,FILES,BYTES}` | new |
| P13 | **Own namespace**: `preserved/<ack_id>/` is absent, or holds only names in this inventory plus `write_bytes_durable` temp names for them (`.<name>.<16 hex>.tmp`). If its `MANIFEST` exists, it is byte-equal to the manifest recomputed now. Anything else refuses ("a different preservation exists; it is never replaced") | new |
| P14 | Core derivable: `derive_core` over `Replay([], C_n.state)` + neutral suffix, for TC0, gives only `RECOVERY{possible_duplicate_spend}` or nothing (no group can be open) | `derive_core` (`:1587–1642`) |

`ack_id = sha256(STOPPED bytes ‖ "\n<reason>\n<resolution>")[:32]`, as today (`:718`). Each stop has a random `stop_id`, so a later stop with the same reason gets a different `ack_id`.

---

## 5. What authorizes each state field

`e = C_n.state.history_epoch`. Neutral suffix ⇒ the state at the witnessed end equals `C_n.state` except `next_seq`.

| Field | After activation | Authorizing canonical fact(s) | Proven by |
|---|---|---|---|
| `lineage_id` | **retained** | SV013 l.558 "starts epoch+1" (same lineage); §1.4 registry | P3, P5, P6, P8: one lineage in header chain, run.json, state and IDENTITY |
| ledger `seq`/chain | continued (`last+1`) | v2 §1.2 chain; §1.4.8 | P3 strict TC0 end = witness |
| `history_epoch` | **e → e+1, once** | SV013 l.558; A12 row; registry "+1 per replacement or external edit" | One activation record. The reducer asserts `payload.epoch == state.epoch + 1` (`chassis_replay.py:353`). The own-prefix check (§8.2) forbids a second one |
| conversation messages | **reset to `[]`** (the loss) | SV013 l.558 "bootstrap"; A12 | Old bytes preserved and hash-verified before the linearization point (LP); the live name is removed only after LP |
| `recap_folded` | reset to 0 | `_switch_base` (the fold index refers to the lost list) | reducer |
| `requests.next`, `requests.last` | **retained** (+ `possible_duplicate_spend` if `last.outcome == failed_unknown`, exactly as an ordinary TC0 start) | SV013 §2.2.3 "no automatic replay … attempt+1"; v2 §1.4.3 | P6 state + P14 |
| IDENTITY | retained; raised only by the existing exact reservation at the end of startup (never lowered) | SV021-01 (accepted) | P5 = witness, and witness ≥ every used turn |
| `notes.next_gen`, `adopted_through`, `pending[]` (with blobs), `handoff_md_sha256`, `adopted_mirror_sha256`, `dropped_pending_limit` | **retained** | D13 §2.2.5 rule 3; v2 §1.4.3 "never reset" | P6 (blobs verified), P7 (no note record after `C_n`) |
| `legacy` | retained | v2 §1.4.3 | P6 |
| `originals[]` (+ blobs) | retained (FIFO ages them out) | v2 §1.4.6 | P6 |
| `active_group`, `queued` | null / `[]` | v2 §1.4.1 CKG | P7 (no group can open after `C_n`) |
| `conversation.prev.json` | untouched by activation; replaced later by ordinary CK3 | SV013 A12 "prev … preserved" | preserved copy first |
| `run.json` | untouched until the next ordinary CK5 | CK5 | preserved copy first; covers ≤ last seq ⇒ no A15 |
| `recap.md` | untouched (recommended R1, §6) | — (not settled) | preserved copy first |
| `corrupt/` | untouched | v2 §1.4.5 never GC'd | not copied (§7.2) |

---

## 6. Activation semantics: settled vs. unsettled (alternatives and recommendation)

The source settles four things:
- it is the operator's explicit act;
- every file is kept;
- the epoch advances by one;
- "bootstrap" follows.

It does **not** settle the five choices below. Each one is presented for review; the recommendation is labelled and is not silently implemented.

**Q1: what the model sees.**
- **S1 (recommended): exactly A12's duty-visible path.** Empty base, `notices: []`; `resume_session` adopts pending notes once; `bootstrap()` runs only if nothing was adopted, else the duty continues from the notes; `DEFAULT_OPENING` as A12. *Why:* it adds no new model-visible text or ordering. Everything the duty sees is already accepted behaviour (`test_sv021_04_…`). The operator/apparatus distinction is recorded in the ledger (`RECOVERY_ACK`, `cause`) and lifecycle, not in the conversation.
- S2: A12 plus one carried runtime notice in the activation record (e.g. "[runtime] the saved conversation could not be read and had no bound copy; an operator started a new history epoch; the earlier files were preserved"). *Cost:* the list is then non-empty, so `bootstrap()` never runs. That is a duty-visible change of the bootstrap contract (an RV-15-class register item).
- S3: the notice is deferred until after bootstrap/adoption through a new state flag. *Cost:* a `SessionState` schema and reducer change, which is larger.

**Q2: `recap.md`.**
- **R1 (recommended):** leave it in place, exactly as A12 does. Its pre-activation bytes are preserved.
- R2: remove it at activation (the new epoch starts with no recap). That is a new runtime mutation outside ledger authority and diverges from A12.

**Q3: pending notes.**
- **N1 (recommended, and canonically required):** carry them and adopt each once (watermark never reset).
- N2 (drop or mark adopted) contradicts D13 rule 3 and v2 §1.4.3 and is not offered.

**Q4: lineage.**
- **Same lineage (recommended, canonical "epoch+1").**
- A new lineage is rejected: it contradicts the text. It would also need a new IDENTITY, a new label space and recorder-correlation semantics no source specifies.

**Q5: the activation record.**
- **E1 (recommended):** `EXTERNAL_DELETE` with additive fields `cause: "bootstrap_preserving"`, `ack_id`, `manifest_sha256`, and `notices: []`. `REQUIRED_KEYS` (`epoch`) is unchanged and `validate_payload` accepts extra keys (`chassis_persistence.py:198–250`). The reducer, `_binding`, `SWITCH_RECORDS`, replay and every later start are unchanged. The only cost is the name ("delete"), disambiguated by `cause`. No consumer outside the chassis reads `EXTERNAL_DELETE` (only `services/chassis_*.py` reference it).
- E2: a new `RECOVERY{kind: "bootstrap_preserving"}` with a new reducer branch (epoch step + base switch) and a new `_binding` branch. Clearer name, more code on the replay path.
- E3: a new type id 0x19. Rejected: it changes the v2 §1.2 type table.

If the reviewer prefers S2/S3 or R2, those are duty-visible changes and should go to John rather than be accepted as engineering. **E1+S1+R1+N1 adds no duty-visible behaviour that A12 does not already have.**

---

## 7. Preservation: engineering layout, not memory

### 7.1 Distinction

`session/preserved/<ack_id>/` is an **operator-side engineering archive**:
- written once;
- never read by classification, replay, base selection, note adoption or any model-facing path;
- never a base and never authority;
- never named by GC;
- never counted by quarantine.

Its only reader is this acknowledgement's own verification (Phase A retry, Phase B before LP and the post-LP unlink check). Like everything under the agent's home, it is a reliability aid, not evidence (M-6 [X]). The **duty-visible** consequences are entirely §5/§6: empty base at epoch e+1, notes carried, identity carried. Changing the archive layout would change no duty-visible fact. Changing §6 would.

### 7.2 Inventory (closed, explicit, non-recursive)

Exactly the session files that activation or any later ordinary runtime path may rewrite or remove:

| Entry | Presence | Per-file read bound (existing constant) |
|---|---|---|
| `conversation.json` | required (P9) | `CONVERSATION_READ_MAX` 64 MiB |
| `conversation.prev.json` | if present | `CONVERSATION_READ_MAX` |
| `.prev.tmp` | if present (CK3 removes it, `chassis_persistence.py:1526–1528`) | `CONVERSATION_READ_MAX` |
| `run.json` | required (P8) | `META_READ_MAX` 1 MiB |
| `IDENTITY` | required (P5) | `MAX_MARKER_READ` 64 KiB |
| `STOPPED` | required (P1) | `MAX_MARKER_READ` |
| `recap.md` | if present | `META_READ_MAX` [CM] (the writer caps it at 96 KiB, `chassis.py:104`) |
| `ledger/NNNNNN.svl` | every name `read_segments` lists | `MAX_SEGMENT_READ` |
| `blobs/<64 hex>` | every name `gc.blob_names` lists | `BLOB_READ_MAX` 64 MiB |

**Not inventoried, preserved in place.** No runtime path writes or removes these:
- `corrupt/*` (v2 §1.4.5; only quarantine writes there, never deletes);
- unknown top-level names;
- non-canonical names in `ledger/` and `blobs/`;
- other temp leftovers;
- `preserved/` itself;
- `home/HANDOFF.md` (outside `session/`, not touched by activation; its note facts are in `C_n.state`).

No path outside `session/` is read or written, and no directory is walked recursively.

### 7.3 Caps [CM] (strict pre-admission, no eviction)

`PRESERVED_MAX_SETS = 4`, `PRESERVED_MAX_FILES = 16_384` (all sets, temp names included), `PRESERVED_MAX_BYTES = 512 MiB` (all sets). These are chosen engineering values, not source values; tests inject small ones.
- At or over a cap the command refuses with nothing written (v2 §1.4.8's strict rule, applied to this namespace).
- Old sets are **never** evicted.
- A session too large to preserve stays stopped; the operator can still repair externally and use `continue-from-bound`.
- A file over its per-file bound refuses (P9/P11): never a partial copy.

### 7.4 Why the live `conversation.json` name is removed (after LP)

After activation the base is "empty at epoch e+1", bound as an absent file (`_binding`, EXTERNAL_DELETE). If the unreadable file stayed under its name, every later start would see "ledger valid, conversation unreadable" → A14 → stop again. The authority rule forbids treating an unreadable file as absent. So the transaction preserves the bytes (hash-verified copy), records LP, then unlinks the live name and fences `session/`. The bytes are kept, and no runtime path treats unreadable as absent.

### 7.5 Manifest and carrier schemas (engineering; sealed with SHA-256 `check` over all other fields, as SV023)

```json
MANIFEST = {"version": 1, "ack_id": "<32 hex>", "reason": "conversation_unreadable_unbound",
            "resolution": "bootstrap-preserving", "stop_sha256": "<64 hex>", "witness_check": "<64 hex>",
            "lineage_id": "<id>",
            "entries": [{"path": "<fixed name | ledger/NNNNNN.svl | blobs/<64 hex>>", "bytes": n, "sha256": "<64 hex>"}, ...],
            "totals": {"files": k, "bytes": b}, "check": "<64 hex>"}
```

- `entries` are sorted by path.
- `path` is validated against the fixed names and the two patterns: no `/` other than the one subdirectory separator, no `..`, no absolute path.
- `MANIFEST` is read under `META_READ_MAX` (1 MiB), so its size is bounded. An entry encodes to about 160 bytes, which allows roughly 6,000 entries per set; a larger inventory refuses (P12). The bound is a [CM] choice. 64 KiB was rejected: about 400 entries is fewer blobs than an ordinary session holds, because every tool result is a blob.

The carrier `ACKNOWLEDGED` keeps the SV023 envelope keys exactly (`CARRIER_KEYS`: `reason, resolution, ack_id, witness, evidence, check`). For this pair, `evidence` has exactly these keys:

```json
{"witness_check", "manifest_sha256", "conv_sha256" (the manifest's conversation.json entry),
 "run_sha256", "state_sha256" (C_n.state at next_seq = last+1),
 "suffix_types" (list), "core_sha256" (canonical [[name, payload], ...] of derive_core + activation), "epoch": e+1}
```

The receipt is unchanged `receipt_payload(carrier)` (`:518–523`, `RECEIPT_KEYS`): `{reason, resolution, ack_id, stop_id, evidence_sha256}`. **Exactly one** such `RECOVERY_ACK` is ever written.

The activation record is `EXTERNAL_DELETE{"epoch": e+1, "notices": [], "cause": "bootstrap_preserving", "ack_id": …, "manifest_sha256": …}`.

---

## 8. The transaction

### 8.1 Phase A: `--acknowledge-stop conversation_unreadable_unbound --resolution bootstrap-preserving`

1. **A0 admission** (§4, pure; inventory read #1 computes sizes and hashes).
2. **A1 namespace.**
   - `mkdir preserved/` if absent, then `fsync(session/)`;
   - `mkdir preserved/<ack_id>/` if absent, then `fsync(preserved/)`;
   - `mkdir ledger/` and `blobs/` inside it if absent, then `fsync(<ack_id>/)`.
   - Every fence runs whether or not the directory existed (the SV020-01 rule).
3. **A2 copies**, in sorted path order, for each entry:
   - bounded read #2;
   - require `(bytes, sha256)` equal to the inventory;
   - `cp.write_bytes_durable(dest, data)`: `O_EXCL` temp → write all → fsync → rename → fsync(dir). Destinations are always rewritten, even if present, so each name is re-fenced.
   - **Never `link()`**: copies are new inodes, independent of the mutable live files (segments are `O_APPEND` and truncated by quarantine; other files are renamed over).
4. **A3 `MANIFEST`** via `write_bytes_durable`. The set is complete only once this directory fence returns.
5. **A4 carrier** `ACKNOWLEDGED` via `write_bytes_durable` (fsync `session/`).
6. **A5 retire STOPPED**: `cp.clear_stop` (unlink, fsync `session/`).

**Retry (idempotent).** The same command recomputes the same `ack_id` and inventory:
- **STOPPED present:** redo A1–A6 over the same names. P13 admits only this transaction's own names; temps are never deleted.
- **STOPPED absent and the same carrier held:** only re-fence `session/` and return the carrier (as `_acknowledge_witnessed` `:709–711`).
- **Anything else:** refuse.

Phase A writes no ledger record and contacts nothing.

### 8.2 Phase B: the consuming start (inside `open_session`, before any model call)

1. **B0 classify.** `read_carrier` returns the new kind `preserving`.
2. **B0 `_verify_preserving`** (pure until its final fence):
   - check the carrier seal and pair;
   - the `MANIFEST` bytes hash equals `evidence.manifest_sha256`, and its seal and paths are valid;
   - **every** preserved entry reads back under its bound with the manifested size and hash (read #3);
   - P3–P8, P10 and P14 hold again over the records up to the witnessed end;
   - bytes after the witnessed end may only be this transaction's own: segment headers, then a prefix of `[RECOVERY_ACK(receipt), *derive_core, EXTERNAL_DELETE(activation)]`, optionally followed by a strict byte prefix of the next own frame or a RECOVERING anchored at or after the witnessed end with the `witnessed` context. This is SV023's `_next_own_frame` rule, extended by one planned record;
   - `conversation.json`: before LP (no activation record in the own prefix) it must be present with the manifested bytes; after LP it must be absent or have the manifested bytes;
   - the recomputed `evidence` equals the carrier's.
   - Any failure stops `acknowledgement_unverified` (only STOPPED written; carrier and preserved set kept). Success fences `session/`.
3. **B1 decision.** `_recover` takes a direct decision, case **`BP`**, instead of `_classify_base` (which would raise A14 again):
   - replay = `Replay([], C_n.state)` + neutral suffix (+ own extras);
   - `checkpoints` = the known tuples above the collection floor, as `_classify_base` computes them;
   - `core = [RECOVERY_ACK(receipt), *derive_core(...), ("EXTERNAL_DELETE", activation)]`, minus any prefix already written.
   - The same decision is taken when the transaction context comes from a surviving RECOVERING `witnessed` context naming this pair (after the carrier was retired).
4. **B2 records.** Each record is committed and synced in order. **LP = the activation frame's fsync returning.**
5. **B3 completion** (`_finish_case("BP")`):
   - if `conversation.json` exists, re-read it bounded, require the manifested hash and that its preserved copy verifies;
   - `unlink`; `fsync(session/)`;
   - an absent file is already done.
6. **B4 retirement.**
   - Readable extras' segments are synced (as `:1124–1128`).
   - `_consume_ack`: exactly one matching receipt; its segment fsynced; `unlink ACKNOWLEDGED`; `fsync(session/)`.
   - Then RECOVERING is removed if present (carrier first, then intent: SV023-03 order).
7. **B5** ordinary end of startup: exact IDENTITY reservation (never lower), `unit_end()` (SV026/SV027).
8. **Return** `Opening("BP", session)`.
9. `Chassis.run` then records `run_start`, constructs the client, loads the duty and calls `resume_session` (§6 S1). The first request can only happen after this.

**No request or tool before complete activation.** Phase A and Phase B write no `REQUEST_SENT`/`INVOKING` and call no client. Any failure before B5 returns a stop or raises `PersistenceFailure` before `open_session` returns, and `run()` ends 44 before the client is constructed (`chassis.py:1152–1157`).

### 8.3 Crash, host-loss and failure cuts

M-1 = process death (completed calls stay). M-2 = honest host loss (simulated with carried watermarks: unsynced bytes and unfenced names are undone).

| Cut | Store after | Next action / outcome |
|---|---|---|
| A0 (admission) | unchanged | refused or retried |
| A1–A2 any call (temp written, rename, dir fence) | partial own set; STOPPED present | start: A0 (`diagnostic_stop`). Retry: P13 admits only own names; every entry rewritten. Under M-2 unfenced names vanish and are recreated |
| A3 before or after MANIFEST rename/fence | as above; MANIFEST maybe present | retry: an equal MANIFEST is accepted, otherwise refused (P13) |
| A4 before carrier fence | carrier may vanish (M-2); STOPPED present | A0; retry rewrites the carrier |
| A5 STOPPED unlinked, unfenced | STOPPED may return (M-2) | A0; retry with the same carrier held and STOPPED present re-verifies and redoes A5 |
| B0 before fence | unchanged | restart re-verifies |
| B2 receipt/spend/activation: torn write (M-1 strict prefix) | own torn frame | TC1 rule under RECOVERING with the `witnessed` context (SV023-03 path) |
| B2 written, fsync not returned | readable, not durable | process death: kept as own prefix. M-2: cut; restart writes it again (never twice: own-prefix match) |
| after LP, before unlink | epoch e+1 durable; unreadable file present | restart: post-LP rule, B3 unlink |
| unlink, unfenced | file may return (M-2) | restart: bytes = manifest, unlink again |
| after fence, before carrier unlink | carrier present | restart verifies (file absent allowed post-LP) and retires |
| carrier unlinked, unfenced | carrier may return (M-2) | as above |
| after carrier retirement, RECOVERING present (torn-frame path only) | intent with `witnessed` context | restart takes the BP decision from the context; the core is already written; removes the intent |
| after all retirement, before IDENTITY | ordinary store | ordinary start: A12t, nothing written; IDENTITY reserved |
| **EIO** at any Phase B sync | `PersistenceFailure`; FSYNC_FAILED attempted | next start A1. The A1 acknowledgement is refused while the carrier is pending (**inherited** SV023-02 bounded policy, accepted; no cancellation semantics added) |
| **EIO** in Phase A | `PersistenceFailure` from `write_bytes_durable`; CLI exit 44 | STOPPED still present; retry idempotent |

- **Second interruption.** Any Phase B cut followed by a second cut in the restart, then M-2 over both with carried watermarks, converges. The own-prefix rule is over the union of what survived, and nothing after LP is undone by re-deriving.
- **Stale or conflicting acknowledgements:**
  - a different stop's carrier pending: refuse;
  - a SV023 witnessed carrier pending: refuse;
  - a consumed acknowledgement repeated: no STOPPED, refuse;
  - an old preserving carrier replayed over a later stop with the same reason: `ack_id`/`stop_id` differ; refuse at the command; at start `acknowledgement_unverified`;
  - store changed between command and start (conversation repaired to `C_n` bytes, ledger record appended, IDENTITY changed, preserved copy or MANIFEST damaged): start `acknowledgement_unverified`, nothing activated.
- **Post-LP conflict** (a readable list written under the name by a same-UID writer, M-6): stop `acknowledgement_unverified`, nothing unlinked. Fail-closed, with no resolution (as SV023).

**Partial I/O.** No new guarantee is claimed. Copies use the existing temp+rename helper, the set is complete only after the manifest fence, and every byte is re-verified by SHA-256 before LP. A damaged preserved byte (M-3) is detected and fails closed, and is never repaired, truncated or deleted.

---

## 9. GC exclusion; no automatic loss of preserved evidence

1. The GC namespace is segment numbers in `ledger/` and 64-hex names in `blobs/` only. `preserved/` is outside it and can never be named (`chassis_gc.py:27–32`).
2. No collection starts while `STOPPED` or `ACKNOWLEDGED` exists (`GC_BLOCKERS`). Admission refuses a pending intent (P4).
3. After activation, ordinary GC may later collect pre-activation **live** segments and blobs per v2 §1.4.5. Their preserved copies remain.
   - The first post-activation checkpoint names `prev = null`: `conversation.json` is absent and `.prev.json` holds no known checkpoint's bytes (P10). So nothing is collected there.
   - Collection starts at the following checkpoint.
4. Nothing in the runtime ever deletes from `preserved/`. The command never replaces another set. Temp leftovers are never removed. Caps refuse; they never evict.
5. Quarantine usage counts `corrupt/` only (`chassis_persistence.py:1413–1417`). `preserved/` changes no quarantine admission.

---

## 10. Source-to-change map (smallest coherent additions)

| File | Change |
|---|---|
| `services/chassis_startup.py` | **Constants:** `PRESERVING = "bootstrap-preserving"`, `PRESERVING_RESOLUTIONS = {(conversation_unreadable_unbound, PRESERVING)}` (a *separate* set: `IMPLEMENTED_RESOLUTIONS` and `WITNESSED_RESOLUTIONS` stay as pinned by retained tests), `PRESERVED = "preserved"`, `NEUTRAL_SUFFIX`, three caps, `MANIFEST_VERSION`.<br>**`acknowledge`:** one dispatch for the exact pair before the existing allowlist check.<br>**New pure functions:** `preserving_admission`, `preserved_inventory`, `manifest_problem`, `preserving_evidence` (factored with `witnessed_evidence`'s shared ledger/IDENTITY/checkpoint/run.json checks; conversation rule and planned list differ).<br>**New mutation:** `_acknowledge_preserving` (A1–A5).<br>**`read_carrier` / `carrier_problem`:** recognize the pair and exact evidence keys (kind `preserving`).<br>**`witnessed_context_problem`:** accept the pair.<br>**`_Context.open`, `_verify_preserving`:** verify the carrier.<br>**`_recover`:** take the BP decision (B1) and accept case `BP` where it now accepts `A9`/`A9t` for a witnessed carrier.<br>**`_finish_case("BP")`:** the B3 unlink.<br>**`_consume_ack`:** treat the preserving receipt as the witnessed one (no fallback commit).<br>Module docstring section |
| `services/chassis_persistence.py` | none (`write_bytes_durable`, `clear_stop`, `read_segments`, bounds reused) |
| `services/chassis_replay.py`, `chassis_session.py`, `chassis_gc.py`, `common.py` | none (E1) |
| `services/chassis.py` | none required. Optional docstring sentence at the CLI. `argparse` is unchanged |
| tests | **new file only:** `tests/test_chassis_bootstrap_preserving.py`. No existing test edited (§11.4 shows the retained pins still hold) |

There are no new record types, no `REQUIRED_KEYS` change, no reducer change, no new durable file in `session/` other than the `preserved/` namespace, and no constant or literal change from SV013/SV015.

---

## 11. Finite temporary-root fixture plan

### 11.1 Fixtures (all in `tmp_path`, harnesses from accepted modules only)

Helpers come from `test_chassis_recovery_live` (`Root`, `establish`, `partial_turn`, `LINEAGE`), `test_chassis_acknowledgements` (`AckOps`, `host_loss`, `stop`, `DAMAGE["a14"]`, `receipts`, `effects`) and `test_chassis_gc` (`collection_ready`, `collect_with`, `segments`).

Each neutral fixture:
1. runs `establish`;
2. writes a pending note `N1`;
3. completes one tool turn (`partial_turn(6)`);
4. then follows its variant:
   - **`run-end`**: `checkpoint()` (`C_n`), `record_run_end(0, "main_returned")`. Suffix after `C_n` = `[RUN_END]`.
   - **`collected-and-rotated`**: with `collect=True` and an injected `segment_max = 1`, the `C_n` closure writes `GC_INTENT, GC_DONE, LEDGER_HEADER`, then `RUN_END`. The fixture **asserts** (non-vacuity) that at least one `GC_INTENT` and one `LEDGER_HEADER` follow `C_n`, and that the intent named a segment.
   - **`failed-unknown-request`**: `send(lambda: None)` with no response, `checkpoint()`, `RUN_END`. `C_n.state.requests.last.outcome == "failed_unknown"`.

Then both conversation files are damaged (`DAMAGE["a14"]`). The actual start must stop `conversation_unreadable_unbound` with a valid witness, and only `session/STOPPED` may change (the accepted `stop` helper).

Non-neutral fixtures for refusal reuse the accepted `stopped(..., suffix="partial"|"message")`.

### 11.2 New nodes (22) in `tests/test_chassis_bootstrap_preserving.py`

| # | Node | Asserts |
|---|---|---|
| N1 ×3 | `test_sv028_bootstrap_preserving_starts_exactly_one_new_epoch[run-end\|collected-and-rotated\|failed-unknown-request]` | **Preserved set:** every inventory file's pre-command bytes equal its copy, and the manifest entries are exact. Every copy has `st_nlink == 1` and an `st_ino` different from the live file.<br>**Ledger:** after the witnessed end it holds exactly `[RECOVERY_ACK, (RECOVERY possible_duplicate_spend)?, EXTERNAL_DELETE]` (spend only in the third variant). The receipt equals `receipt_payload(carrier)`, and the activation payload is exact.<br>**State:** `history_epoch == e+1`; messages `[]`; `wire(state)` equals the witnessed `C_n` state except `history_epoch`/`recap_folded`; `next_label()` is `lineage:<next turn>:1` (variant 3: the same turn, `attempt+1`); IDENTITY ≥ witness; `REQUEST_SENT`/`INVOKING` counts unchanged.<br>**Files:** `conversation.json` absent; `.prev.json` unchanged; no STOPPED/ACKNOWLEDGED/RECOVERING/FSYNC_FAILED; `corrupt/` unchanged.<br>**Later starts:** a second start is `A12t` and writes nothing |
| N2 | `test_sv028_resume_after_activation_matches_the_a12_duty_visible_path` | Through the accepted `resume()` helper, the duty-visible list equals that of an A12 control built from the same fixture (deleted, not damaged): the note adopted once at `epoch e+1`, then the opening. Recommendation S1 is checked directly |
| N3 | `test_sv028_preserved_bytes_survive_later_collection_and_are_never_candidates` | After activation and two `collect=True` checkpoints, a `GC_INTENT` names pre-activation segments/blobs (non-vacuous) that are gone from the live store, while the `preserved/` tree is byte-identical. No intent names any `preserved/` path. Quarantine `usage()` is unchanged |
| N4 ×2 | `test_sv028_every_envelope_refusal_leaves_the_store_byte_identical`<br>`test_sv028_every_capacity_and_namespace_refusal_leaves_the_store_byte_identical` | One node per family iterates its cases. Each case requires `LedgerError` matching its own reason text, and the whole root snapshot (including `preserved/`) unchanged.<br>**Envelope:** suffix partial-turn, message, note-written, earlier-receipt; conversation now readable; now absent; over its bound [injected]; previous base available; legacy stop without witness; damaged witness; ledger record appended; ledger garbage tail; IDENTITY changed; blob missing; run.json changed; pending collection; RECOVERING open; FSYNC_FAILED present; another carrier pending; the pair with `run_json_unreadable`, `ledger_tail_ambiguous`, `ledger_missing`.<br>**Capacity/namespace:** bytes, files and sets caps [injected]; a symlink entry; a foreign name in the own directory; a different MANIFEST in the own directory |
| N5 | `test_sv028_the_command_and_the_activation_are_ordered_and_fenced` | From the `AckOps` log:<br>• every copy's rename is followed by its directory fence, before the MANIFEST rename and fence;<br>• then the carrier rename + `sync_dir(session)`, then `unlink STOPPED` + `sync_dir`;<br>• in the start: `sync_dir(session)` before the receipt write; receipt fsync, then activation write and fsync (LP), then `unlink conversation.json` + `sync_dir(session)`, then the receipt segment fsync, then `unlink ACKNOWLEDGED` + `sync_dir`, then IDENTITY;<br>• no `link()` call into `preserved/` |
| N6 ×2 | `test_sv028_every_cut_converges_to_one_receipt_and_one_activation[process-death\|host-loss]` | Sweep every logged call of command and start (the `run-end` fixture). After the cut (and simulated M-2), converge: repeat the command if STOPPED is present, start, then a second start writes nothing.<br>Each converged store has exactly one `RECOVERY_ACK` and one `EXTERNAL_DELETE{cause}`, epoch `e+1`, a verified preserved set, no effect, and **no** preserved file whose bytes differ from the inventory.<br>Before-LP cuts leave the live `conversation.json` unchanged |
| N7 ×3 | `test_sv028_a_second_interruption_then_host_loss_still_converges[receipt-unsynced/activation-write\|activation-unsynced/conversation-unlink\|conversation-unlink-unfenced/carrier-unlink]` | As the accepted SV023 second-interruption test, with carried watermarks |
| N8 ×2 | `test_sv028_an_own_torn_frame_is_set_aside_by_the_ordinary_rule[receipt\|activation]` | A torn own frame leads to RECOVERING with the `witnessed` context naming this pair, a corrupt/ copy and `RECOVERY{torn_incomplete}`, then converges. One receipt, one activation |
| N9 | `test_sv028_stale_or_conflicting_acknowledgements_grant_nothing` | Iterates:<br>• a pending SV023 carrier, then this command: refused;<br>• this carrier pending, then `continue-from-bound`: refused;<br>• repeated after STOPPED removal: fence only, the same carrier;<br>• consumed, then repeated: refused;<br>• old carrier over a later same-reason stop: refused, and the start gives `acknowledgement_unverified`;<br>• between command and start: conversation repaired, record appended, preserved copy byte flipped, MANIFEST byte flipped. Each gives `acknowledgement_unverified`, only STOPPED written, nothing activated;<br>• independent FSYNC_FAILED: A1, then A1 acknowledgement refused "pending", store unchanged |
| N10 | `test_sv028_a_conflict_after_the_linearization_point_fails_closed` | Crash after LP, then a readable list written under the name: stop, nothing unlinked, carrier kept |
| N11 | `test_sv028_cli_bootstrap_preserving_behind_the_first_request_barrier` | Real CLI (`Loop` world, stub model, as `:974–1020`): stop exit 44 → `--acknowledge-stop … --resolution bootstrap-preserving` exit 0, no traffic → restart behind the first-request barrier: no traffic, carrier and STOPPED gone, receipt + activation in the ledger → release → the label is `lineage:<next>:1`, not seen before. The preserved set verifies |
| N12 ×3 | `test_sv028_negative_control_hardlinked_copies_are_detected`<br>`test_sv028_negative_control_without_the_neutral_suffix_check_suffix_memory_is_dropped`<br>`test_sv028_negative_control_retiring_the_carrier_before_the_unlink_fence_restops_after_host_loss` | Monkeypatched mutations (restored by pytest) under which N1's independence assertion, the W2 refusal and the N6 host-loss cut respectively fail. Each control shows its assertion is the one that discriminates |
| N13 | `test_sv028_exactly_one_pair_is_added` | `PRESERVING_RESOLUTIONS == {(A14, "bootstrap-preserving")}`; `IMPLEMENTED_RESOLUTIONS`/`WITNESSED_RESOLUTIONS` unchanged; every other `(reason, bootstrap-preserving)` from the accepted `OTHER_REASONS` list still raises "not implemented" with the store unchanged |

### 11.3 Pre-fix discriminators (unchanged runtime, before any runtime edit; one node per command)

| Id | Node | Expected on the base |
|---|---|---|
| B0 | `tests/test_chassis_recovery_live.py::test_c_k3_a12_a_deleted_list_is_a_clean_slate_with_everything_kept` | pass (the A12 behaviour S1 relies on) |
| D1 | `N1[run-end]` | fails at the acceptance call: `LedgerError … not implemented` (behaviour: the pair is refused today) |
| D2 | `N4` envelope node | fails at the first `match=` assertion: the base refuses with "not implemented", not the case's own reason. This shows the matrix checks *why*, not only *that* |
| D3 | `N11` | fails at `ack.returncode == 0` (base returns 2) |

The base passes several new nodes by construction: the remaining N4 node and the stale-acknowledgement parts of N9 (refused anyway). Those are post-change controls, not discriminators. Their discriminating power comes from N12.

### 11.4 Retained nodes (47), selected explicitly

**R1, `tests/test_chassis_acknowledgements.py` (32):**
- `test_a_witnessed_file_repair_stop_resumes_from_the_bound_checkpoint[a14]`, `[ck5]`
- `test_the_same_command_repeated_is_idempotent[a14]`
- `test_every_refusal_leaves_the_store_byte_identical[a14]`, `[ck5]`. Its `wrong-resolution-bootstrap` case runs on a *repaired* (readable) conversation, so the new path refuses it at P9 with no change. Its CK5 case is not the admitted pair.
- `test_the_refusal_matrix_control_the_unmutated_repair_is_accepted`
- `test_stops_without_a_safe_witness_are_recorded_as_before_and_ineligible`
- `test_an_a14_stop_over_a_pending_collection_carries_no_witness`
- `test_only_the_two_new_pairs_are_added_and_every_other_pair_is_still_refused`. It still holds: the separate set leaves both pinned sets unchanged, and `(A14, bootstrap-preserving)` on its repaired store is refused at P9, so `refused` keeps its count.
- `test_newer_integrity_stops_acquire_no_resolution[identity_unproven]`, `[gc_intent_invalid]`, `[ledger_prefix_missing]`, `[recovery_intent_invalid]`, `[acknowledgement_unverified]`
- `test_the_transaction_is_ordered_and_fenced`
- `test_every_cut_of_the_acknowledgement_converges_with_one_receipt[a14-process-death]`, `[a14-host-loss]`
- `test_a_second_interruption_then_host_loss_still_converges[carrier-unlink/first-fence]`, `[closure-unsynced/receipt-segment-sync]`, `[receipt-unsynced/carrier-unlink]`
- `test_a_stale_permission_never_authorizes_a_changed_store[valid-record]`, `[file-damaged-again]`
- `test_an_old_carrier_cannot_unlock_a_later_stop_with_the_same_reason`
- `test_an_independent_fsync_failure_after_the_acknowledgement_keeps_a1_authority`
- `test_sv023_01_a_present_carrier_that_does_not_verify_stops_before_any_change[a14-reason-an-old-pair]`, `[a14-wrong-check]`
- `test_sv023_02_a_later_acknowledgement_never_replaces_an_unfinished_carrier[a14-failed-first-fence]`, `[a14-independent-marker]`
- `test_sv023_03_every_cut_after_an_own_torn_frame_converges[receipt-process-death]`, `[closure-host-loss]`
- `test_sv023_04_a_failed_receipt_sync_keeps_the_carrier_and_takes_the_persistence_boundary`
- `test_sv023_05_an_interrupted_independent_tail_recovery_has_no_acknowledgement_and_converges`

**R2 (1):** `tests/test_chassis_acknowledgements.py::test_cli_acknowledgement_and_restart_behind_the_first_request_barrier`

**R3 (14):**
- `tests/test_chassis_recovery_live.py::test_a0_a_stop_stops_without_writing_anything`, `::test_c_k7_a1_an_fsync_marker_stops_the_next_start`, `::test_c_k5_a6_a_corrupt_legacy_conversation_stops_and_is_kept`, `::test_c_k3_a12_a_deleted_list_is_a_clean_slate_with_everything_kept`, `::test_a14_o2_2_an_unreadable_file_is_rebuilt_from_the_previous_base`, `::test_sv021_04_one_deletion_is_consumed_once_across_restarts`
- `tests/test_chassis_replay.py::test_external_edit_delete_and_reimport_switch_the_base`
- `tests/test_chassis_notes.py::test_c_n1_a_note_is_adopted_by_the_next_run_once`, `::test_an_agent_edit_to_handoff_md_is_adopted_once_as_a_new_generation`
- `tests/test_chassis_gc.py::test_o2_1_pending_generations_outlive_their_collected_records`, `::test_c_g1_an_adopted_note_is_never_readopted_after_its_records_are_collected`, `::test_o2_4_every_cut_in_a_collection_converges_over_two_restarts[process-death]`
- `tests/test_chassis_rotation.py::test_sv027_every_closed_boundary_rotates_a_full_segment[startup-a9-clean]`, `::test_sv027_rotation_failures_and_crashes_at_the_new_boundaries[startup-inherited-fsync-eio]`

Node ids follow the accepted manifests' convention (inner parametrize first). The implementer confirms each by static AST check before running, as SV027 did.

### 11.5 Commands and resource estimate

Every command is the approved runner with literal targets, one per message, serial:

```
python3 /home/john/Documents/Codex/2026-10-07/task/results/SV-016-bounded-check.py --cpu 23 <targets>
```

The limits are unchanged: 120 CPU s / 180 wall s / 512 MiB AS per process; aggregate 50% CPU / 2 GiB / 64 tasks / nice 15.

| Cmd | Content | Cases | Estimate |
|---|---|---|---|
| B0, D1, D2, D3 | pre-fix, one node each | 4 | < 5 s CPU each; D3 ≈ 10–20 s wall (CLI world) |
| F1 | N1×3, N2, N3, N4×2, N5, N9, N10, N13 | 11 | ≈ 60 fixture builds × ≤ 0.2 s ⇒ ≲ 15 s CPU |
| F2 | N6[process-death] | 1 | ~10 inventory files ⇒ ≈ 65 command + ≈ 30 start calls ≈ 95 cuts × (build + stop + converge ≈ 0.2 s) ≈ 20 s CPU |
| F3 | N6[host-loss] | 1 | as F2 |
| F4 | N7×3, N8×2, N12×3 | 8 | ≲ 15 s CPU |
| F5 | N11 | 1 | ≈ 10–20 s wall, as the accepted CLI node |
| R1 | 32 retained acknowledgement nodes | 32 | SV023 ran 97 of these nodes in one command within the caps |
| R2 | retained CLI node | 1 | ≈ 10–20 s wall |
| R3 | 14 retained nodes | 14 | ≲ 20 s CPU |

The final total is **22 new + 47 retained = 69 cases in 8 commands**, plus 4 pre-fix commands. Fixture data is KB-sized, memory is negligible against 512 MiB, and every caps test uses injected tiny caps.

Production cost of one acknowledgement:
- Phase A reads the inventory twice and writes it once.
- Phase B reads the preserved set once.
- Disk grows by the set size, bounded by `PRESERVED_MAX_BYTES`.
- Peak memory is one file at a time (≤ the 64 MiB per-file bound) plus overhead.

---

## 12. Risks, limits and what is not claimed

1. **Duty-visible semantics (§6) are unsettled by the source.** E1+S1+R1+N1 is a recommendation that adds no behaviour A12 lacks. S2/S3/R2 would be owner decisions.
2. `EXTERNAL_DELETE` reuse is honest only with `cause`. A future reader that ignores `cause` would read "duty deletion". No such reader exists today. E2 is the clean alternative at the cost of reducer code.
3. **Preserved bytes double disk use**, and caps make the resolution unavailable for large sessions (fail-closed; `continue-from-bound` after external repair remains).
4. **Inherited wedges, not fixed here:**
   - a Phase B persistence failure leads to an A1 stop whose acknowledgement is refused while the carrier is pending (SV023-02's accepted bounded policy);
   - a post-LP M-6 conflict stops with no resolution.
   - Neither is new, and no cancellation semantics are added.
5. **M-6:** `preserved/` is agent-reachable; it is a reliability aid, not evidence. TOCTOU between the inventory and copy reads is detected by hash equality, assuming M-5 (STOPPED prevents chassis writes during Phase A).
6. **Shared-verifier factoring could regress SV023.** Mitigated by R1/R2 (33 retained acknowledgement nodes, including both cut sweeps and the CLI).
7. **Not claimed:** any real-session acknowledgement, deletion or resumption; power-loss/kernel behaviour (M-2 is simulated); partial-I/O guarantees beyond the existing helpers; numerical replay, segment or read bounds (SV025/SV026/SV027 qualifications stand); coverage of any other stop or resolution; H/T/Q/pump/history policy; provider behaviour; merge or deployment.

## 13. Questions for Astra

1. Accept W1's restriction to a state-neutral suffix (W2 refused) as the narrow case?
2. Accept E1+S1+R1+N1 as engineering, or route S2/S3/R2 to John?
3. Accept the separate `PRESERVING_RESOLUTIONS` set (no existing test edited), or prefer widening `IMPLEMENTED_RESOLUTIONS` with a reviewed edit of the pinned test?
4. Accept the post-LP unlink of the live name (§7.4) as required by the authority rule?
5. Accept the [CM] caps, the 1 MiB manifest bound (≈ 6,000 entries per set) and the per-file bounds?
6. Are the 69 cases and 8 + 4 commands sufficient, and are D1–D3 meaningful discriminators?
