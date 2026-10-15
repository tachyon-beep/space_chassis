# integration/

Notes and planning for the **vehicle simulator** — the far side of the window that
`space_chassis` deliberately does not contain.

The parent folder holds the ChatGPT deep-research subsystem specifications. This
folder holds the work of turning those into one coherent, runnable vehicle: the
design, the reconciliation notes, and the open questions.

| File | What it is |
|---|---|
| `simulator-design.md` | The living design. Sections presented and approved one at a time; not yet complete. |

Planned, as the remaining specs land:

| File | What it will be |
|---|---|
| `reconciliation/<domain>.md` | Per-spec notes: what was taken, what was declined, what conflicted with apollo. |
| `open-questions.md` | Anything that needs John's decision, accumulated rather than asked twice. |

## The one rule that governs everything here

The eleven subsystem specs are **schemas and safety semantics with no vehicle in
them** — every threshold is `UNSPECIFIED` / `RIP-REF` / `Sim` / `CRA-REF`, deferred to
"mission configuration." `apollo_diode.md` is the only document that contains an
actual spacecraft: anchored ranges, the coupling graph, failure chains, the
mission profile, the scenario ladder, the coordination metrics.

> **apollo supplies the vehicle and the experiment; the subsystem specs supply the
> per-domain contracts. Where they disagree on a number, apollo wins — it is the only
> one making a claim about an actual vehicle rather than about a schema.**

**Three corrections to the paragraph above, from `corpus-review.md` — read it before
using this rule.** (1) apollo has no masses, no inertia, no centre of mass, no thrust and
no mission duration: `integration/README.md` previously said it did, and the globals are
therefore invented, not extracted. (2) All three spec dialects are real but the census
undercounts deferral badly — seven specs defer in prose or a `_cfg` suffix, and `Sim` is
not a deferral token at all but a flag on an *invented* number. (3) "Apollo wins" is not a
tie-break: `eclss_diode.md:19` and `:734-736` **delete** apollo's cabin pressure, CO₂ and
O₂-supply values on purpose, and `thermal_diode.md:965` refuses its whole domain. Applying
the rule means overriding the newer documents' stated stance, and that is a decision to be
recorded once rather than rediscovered per conflict. The conflict register is in
`reconciliation/01-conflict-register.md`.

## The other standing filter

All subsystem specs escalate to a **hardware dual-diode** — two simplex optical paths,
per-object cryptography, anti-replay sequence state. That argument is correct and
**inapplicable** as a *transport*: the diode here is emulated as a sibling container
sharing a volume, so the asymmetry is container topology, not optics. The specs' own trade
tables rate the filesystem/service pattern as the right choice for a simulation
(`electrical_diode.md:442`, `main_propulsion_diode.md:248`).

Treat the transport-security layer as already answered. The subsystem physics,
telemetry catalogues, interlocks, state machines and failure chains are the payload.

**But the filter is narrower than it looks, in two ways.** First, the later specs do not
merely mention the dual diode — `eclss_diode.md:741` makes it normative and
`crew_diode.md:1028-1030` adopts it as the common external boundary, so applying the filter
is a rewrite of portions of eight documents rather than a skip of one section each. Second,
`communcations_diode.md:102` welds two arguments together, and only one of them is optics:
it also attacks the *crash semantics* of destructive intake ("whose destructive rewrite
requires the receiver to write into the sender-owned channel"). That second argument
survives the filter and points at a real hole in `diode-contract.md` §2.2, where a batch
claimed and then lost produces no result file at all — so an agent cannot tell "lost" from
"still pending", against the contract's own rule that a refusal is a result. The remedy
costs one durable acceptance ledger and an `INDETERMINATE` state, with no mount change and
no cryptography; see `reconciliation/01-conflict-register.md`.
