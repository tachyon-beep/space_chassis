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

The seven-plus subsystem specs are **schemas and safety semantics with no vehicle in
them** — every threshold is `UNSPECIFIED` / `RIP-REF` / `Sim` / `CRA-REF`, deferred to
"mission configuration." `apollo_diode.md` is the only document that contains an
actual spacecraft: masses, anchored ranges, the coupling graph, failure chains, the
mission profile, the scenario ladder, the coordination metrics.

> **apollo supplies the vehicle and the experiment; the subsystem specs supply the
> per-domain contracts. Where they disagree on a number, apollo wins — it is the only
> one making a claim about an actual vehicle rather than about a schema.**

## The other standing filter

All subsystem specs escalate to a **hardware dual-diode** — two simplex optical paths,
per-object cryptography, anti-replay sequence state. That argument is correct and
**inapplicable**: the diode here is emulated as a sibling container sharing a volume,
so the asymmetry is container topology, not optics. The specs' own trade tables rate
the filesystem/service pattern as the right choice for a simulation.

Treat the transport-security layer as already answered. The subsystem physics,
telemetry catalogues, interlocks, state machines and failure chains are the payload.
