# Final-package review r1 (Codex reviewer, agent ae007c83a92c150af)

Recovered verbatim on 2026-10-12 from the session transcript (record 11293, 2026-10-11T13:36:13.830Z): CHECKPOINT 23 stated it was saved here, but the file was not on disk. The harness's two-space indent is removed; nothing else is changed.

---

**Request changes (Option B final package + gate proposal). No P1 identified; two P2 blockers remain.** Option B fixes the claim race, but does not establish atomic result delivery, next-read service, or exactly one result file.

Source references below use the [candidate worktree](/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9) and the [gate package](/home/john/space_chassis/.scratch/wp01-handoff/diag-contract-probe/B-sel1/gate).

| Contract statement | Verdict | Source-backed limit |
|---|---|---|
| **"Destructive and atomic"** | **True only with qualifications.** | The successful rename is atomic (`tools/console.py:4423`). Inspection, replacement-console publication, journal recording and result publication are separate operations (`:4401`, `:4473`, `:3155`, `:3164`). Claim durability is journal-dependent (`:4392`, `:4458`). |
| **"Claimed at the next read"** | **False as written.** | Window checks can skip intake (`:3100–3119`, `:4265–4273`); recovery, sweep and pending takes precede fresh reads (`:4393–4400`). Resume can read the console solely for its map (`:4667`). Intake occurs separately for each window within the cycle (`:3129`). |
| **"Exactly one result file per command"** | **False; remove the guarantee.** | Deferred acceptance and settlement generate separate verdicts/files (`:4037–4068`, `:3626–3652`, `:4798`). Malformed/over-cap batches generate one batch refusal (`:3577–3607`). Recovery can duplicate an existing receipt (`:2574–2618`, `:3291–3308`). Obligations exceeding **256 per window** evict the oldest unwritten result (`:353`, `:3255–3273`). |

A crash **after claim but before the durable cycle record** can leave no recoverable result. After recording, resume reconstructs owed results and attempts publication (`console.py:5224–5230`, `:5365`), but that is bounded recovery, not guaranteed delivery. Deduplication examines at most **4,096 entries / 256 KiB**, so multiple files can carry the same receipt `seq` (`:2494–2498`, `:2574–2584`). These are duplicates of a verdict, distinct from deferred acceptance and settlement.

With a journal, result files and their directory are synced before publication is acknowledged (`:4798–4808`; recovery `:3295–3306`). Without a journal, those barriers are omitted. Process-crash reasoning therefore cannot establish host-crash/power-loss safety; the source demonstrates ordering, not successful storage persistence under power loss.

**Exact replacement paragraphs I would accept**

For section 2.2's intake, scheduling and crash wording:

> **A successful claim takes the console atomically.** At an eligible intake visit, the vehicle inspects `console.json`. It leaves a console untouched when `commands` is an empty list and `variables` is an object, or when `variables` is absent and the vehicle has no known map. Otherwise it attempts to rename the console aside. Whatever entry occupies the name at the successful rename is the claim; the earlier inspection does not select the batch. The vehicle reads the taken entry without following links and attempts to restore an emptied console with the preserved variables, without overwriting a replacement supplied meanwhile. The console may be temporarily absent.
>
> **There is no next-read or next-cycle guarantee.** Window checks, recovery and unfinished claim or durability work can postpone intake. Nonregular files detected by the window pre-check cause that window to be skipped; this records a window failure, not a per-command result. A batch submitted during a cycle may be taken in that cycle. A replacement left at `console.json` awaits a later eligible intake attempt. Replacing a batch before it is taken supersedes it. Replace the file rather than writing in place: in-place writes can be read partially or continue into an already-taken file.
>
> **Invalid input is not a batch of executable commands.** A taken input that cannot be decoded as a console, or whose non-null `commands` value is not a list, generates a refusal verdict. Missing or null `commands` supplies no commands. A list containing a non-string element, or exceeding the batch cap, is refused as a whole with one batch-level verdict. Publication remains subject to section 2.3.
>
> **Claiming, execution and result publication are separate.** Claimed input batches are not replayed from leftover take files after a process restart. A crash after claiming but before the cycle record becomes durable can lose the batch's results. With a journal, the window directory is synced before taken commands are returned for processing, and retirement must become durable before further intake or map adoption. Without a journal, these barriers are omitted. Host-crash and power-loss persistence depends on the applicable file and directory syncs completing and the storage system honoring them.

Sources: `console.py:4392–4428`, `:4448–4518`, `:3100–3169`, `:3577–3607`, `:4583–4684`.

For section 2.3, replacing both "Every command produces exactly one file" and the unconditional "one file each" refusal wording:

> **Results are published as files; neither exactly-one nor eventual delivery is guaranteed.** Each published verdict has a result file. A deferred command can produce an acceptance result and a later settlement result. A malformed or over-cap batch produces a batch-level refusal rather than a result for every element. A skipped window, interrupted processing or failed publication can leave no result.
>
> **Recovery may republish results.** Retained owed results are retried during publication and resume. The bounded search for an existing result may miss it, producing another file with the same receipt; identify duplicate verdicts by their world, window and receipt `seq`, not by filename. At most 256 owed results are retained per window; exceeding that bound abandons the oldest obligation and records the failure. Recovery can also substitute truncated text or a fingerprint explanation when the full result was not retained. These mechanisms do not guarantee one file, complete original text, or eventual delivery.

Sources: `console.py:2494–2527`, `:2574–2618`, `:3255–3308`, `:3626–3652`, `:4037–4068`, `:4779–4808`, `:5365`.

**Consolidated findings**

- **P2 — Contract overclaim:** `CONTRACT-PACKAGE-B.md:13–15,39–40` (including the "section 2.3 resolved" declaration at `:39`) must incorporate the qualifications above; section 2.3 remains unresolved under its current wording. Option B resolves the overwrite/claim race, not these result-cardinality exceptions.
- **P2 — Hidden worker retries:** `gate_lane.py:54` leaves xdist worker replacement enabled (eight replacements at `-n 2`). A collection crash without an assigned testcase can be replaced without a failed JUnit case, and the lane can then report green. Add `--max-worker-restart=0` and explicitly reject worker crashes.
- **P3 — README/ADR precision:** candidate `README.md:19447–19456` needs journal-qualified durability and must include retirement-fsync blockage (successful removal also blocks while its directory fsync fails, `console.py:4487`). ADR 0002 `:945–948` should say serving starts **with a state directory, before the first claim**, not before any window read; fresh window preparation precedes the marker (`console.py:6064–6103`).
- **P3 — Qualification policy:** `PROPOSAL-G.md:41–50` establishes tree equivalence, not the literal committed-exact-SHA gate in practice.md. Identify this as a proposed substitution requiring acceptance; hosted CI does not repeat all seven steps on both lanes.
- **P3 — Cleanup/bounds:** `PROPOSAL-G.md:156` proposes ordinary worktree removal, which refuses the intentionally dirty gate tree; specify bounded cleanup after evidence preservation and identity verification. At `:126`, 3,930 + 3,330 seconds is **2 h 1 min**, not 2 h 11 min.

**Verified:** the manifest hash `df9cd817…` and all ten entries; v7 hashes; candidate HEAD, diff, tracked tree and four file hashes. Static **551** is correct: 537 functions plus 14 parametrization cases, consistent with baseline 528/542. No README-linter rejection identified. The seven gate steps, expectations (lint text, strict 2, zero skips, JUnit 551), caps, deadlines, serial release conditions and the commit/PR draft template fit (placeholders explicit) otherwise align.

**Static review only:** no project execution, gate, linter, tests, collection, supervisor, systemd operations, worktree creation or file changes.
