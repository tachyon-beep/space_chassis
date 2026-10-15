# #39 option B — contract package (vehicle-owned wording; DRAFT until option B merges)

Vehicle line, 2026-10-12. This revision is corrected after the independent review
(`../../reviews/B-final-package-r1.md`). The earlier draft overclaimed and is withdrawn.

- **Ownership.** The vehicle owns and leads `docs/diode-contract.md`. The chassis adopts the wording,
  and owns its brief, fixture and probe. The brief's text is John's to approve.
- **Relation to tier 1.** This package supersedes tier 1's (`governance/vehicle/records/2026-10-11-39-tier1-adoption-package.md`)
  once option B merges. It is not sent before then.

**What option B does and does not change.** Option B fixes the overwrite and claim race: a claim never
writes over a file. It does **not** make result delivery atomic. It does not guarantee service at the
next read, and it does not guarantee exactly one result file per command. The source shows several
result-cardinality and delivery exceptions that are independent of the claim. **None of those
guarantees is restored here.** References are to `tools/console.py` in candidate 5, whose code is
identical to candidate 3.

## The three statements, reconciled against the source

| contract statement (current `aurora-port` text) | with option B | source-backed limit |
|---|---|---|
| §2.2 "Intake is destructive and atomic" | **true only with qualifications**: the successful rename is atomic | inspection, putting the console back, journal recording and result publication are separate operations (`:4423`, `:4401`, `:4473`, `:3155`, `:3164`). Claim durability depends on a journal (`:4392`, `:4458`) |
| §2.2 "A batch written while a cycle is in progress … runs on the next one" | **false as written; replaced** | window checks can skip intake (`:3100–3119`, `:4265–4273`). Recovery, the sweep and pending takes come before fresh reads (`:4393–4400`). Intake is per window within a cycle (`:3129`) |
| §2.3 "Every command produces exactly one file" | **false; removed** | a deferral produces an acceptance result and a later settlement result (`:4037–4068`, `:3626–3652`). A malformed or over-cap batch gets one batch-level refusal (`:3577–3607`). Recovery can duplicate a receipt (`:2574–2618`, `:3291–3308`). At most 256 obligations are kept per window, beyond which the oldest is dropped (`:353`, `:3255–3273`). A crash before the cycle's record is durable can lose results |

## Proposed §2.2 text (replacing the intake, scheduling and crash bullets)

> **A successful claim takes the console atomically.** At an eligible intake visit, the vehicle
> inspects `console.json`. It leaves a console untouched only when `commands` is an empty list and
> either `variables` is an object, or the `variables` key is absent and the vehicle has no known map.
> A nonempty, missing or null `commands` is never left untouched on either branch. Otherwise it
> attempts to rename the console aside. Whatever entry occupies the name at the
> successful rename is the claim; the earlier inspection does not select the batch. The vehicle reads
> the taken entry without following links. It then attempts to restore an emptied console with the
> preserved variables, without overwriting a replacement supplied meanwhile. The console may be
> temporarily absent.
>
> **There is no next-read or next-cycle guarantee.** Window checks, recovery, and unfinished claim
> or durability work can postpone intake. A non-regular file found by the window pre-check causes that
> window to be skipped; this records a window failure, not a per-command result. A batch submitted
> during a cycle may be taken in that cycle. A replacement left at `console.json` awaits a later
> eligible intake attempt. Replacing a batch before it is taken supersedes it. Replace the file rather
> than writing in place: in-place writes can be read partially, or continue into an already-taken
> file.
>
> **Invalid input is not a batch of executable commands.** A taken input that cannot be decoded as a
> console, or whose non-null `commands` value is not a list, generates a refusal verdict. Missing or
> null `commands` supplies no commands. A list containing a non-string element, or exceeding the batch
> cap, is refused as a whole, with one batch-level verdict. Publication remains subject to §2.3.
>
> **Claiming, execution and result publication are separate.** Claimed input batches are not
> replayed from leftover take files after a process restart. A crash after claiming but before the
> cycle record becomes durable can lose the batch's results. With a journal, the window directory is
> synced before taken commands are returned for processing, and retirement must become durable before
> further intake or map adoption. Without a journal, these barriers are omitted. Host-crash and
> power-loss persistence depends on the applicable file and directory syncs completing, and on the
> storage system honouring them.

Sources: `console.py:4392–4428`, `:4448–4518`, `:3100–3169`, `:3577–3607`, `:4583–4684`.

## Proposed §2.3 text

This replaces both "Every command produces exactly one file" and the unconditional "one file each"
refusal wording.

> **Results are published as files; neither exactly-one nor eventual delivery is guaranteed.** Each
> published verdict has a result file. A deferred command can produce an acceptance result and a
> later settlement result. A malformed or over-cap batch produces a batch-level refusal rather than a
> result for every element. A skipped window, interrupted processing or failed publication can leave
> no result.
>
> **Recovery may republish results.** Retained owed results are retried during publication and at
> resume. The bounded search for an existing result may miss it, producing another file with the same
> receipt. Identify duplicate verdicts by their world, window and receipt `seq`, not by filename. At
> most 256 owed results are retained per window; exceeding that bound abandons the oldest obligation
> and records the failure. Recovery can also substitute truncated text, or a fingerprint explanation,
> when the full result was not retained. These mechanisms do not guarantee one file, complete original
> text, or eventual delivery.

Sources: `console.py:2494–2527`, `:2574–2618`, `:3255–3308`, `:3626–3652`, `:4037–4068`, `:4779–4808`,
`:5365`.

## Consequences elsewhere in the contract (chassis to adopt)

- **§9's probe list** says "every command in a batch produces exactly one result file" (`docs/diode-contract.md:288`).
  The probe checks this for the batches it submits: plain, non-deferred commands with no crash. It
  therefore remains a valid check of that case. The sentence needs a qualifier naming that scope.
  **The probe itself is unchanged.**
- **§2.2's malformed-batch bullet** ("exactly one result file records that", `:74`) stays true for one
  published verdict, subject to the new §2.3.

## For the chassis (its own adoption, in its own increment, in Governance's order)

- **Brief:** `brief/PROTOCOL.md:51–54` and `docs/brief-claims.md` need the same meaning in the brief's
  voice — absence is transient; replace, don't write in place; no exactly-one or next-read promise — for
  John to approve.
- **Fixture:** `contract/fake_diode.py` may keep tier 1's quiet rule. Option B is the vehicle's
  mechanism.
- **Pins:** 537 test functions, 551 collected (to be confirmed by the gate); `report.refuse(` sites
  882, unchanged.
