# The research corpus, reviewed

What `docs/deep_research/` actually contains, what it is worth, and what has to be
decided before the vehicle simulator can be built from it.

**Scope.** The twelve documents in `docs/deep_research/` — `apollo` plus eleven
subsystem specifications. Not the design (`integration/simulator-design.md`, reviewed in
`integration/review-findings.md`) and not the contract (`docs/diode-contract.md`). This
review asks one question: *if you build the far side of the window out of these documents,
what do you get, and what do you have to invent?*

**Method.** `apollo_diode.md` and both `integration/` documents were read in full. Each of
the eleven subsystem specs was read in full, its claims extracted, and the results
collated. **Every line reference and every count printed below was re-checked against the
file it names, and every piece of arithmetic was recomputed by hand.** §9 lists the checks.
Two claims from that pass were rejected and are recorded there rather than repeated.
Nothing in the repository was modified.

**A provenance note that affects every line number.** The documents end without a trailing
newline, so a reader shows one more line than `wc -l`. References use the reader's numbering.
`CLAUDE.md:37`'s "~13k lines" is stale: the corpus is **16,445 lines**.

---

## 1. The corpus at a glance

Generation order, from mtimes and confirmed by each document's backward `filecite` set.
There are no forward citations anywhere: this is a chain, not a panel.

| Document | Lines | What it actually is | Deferral dialect |
|---|---:|---|---|
| `apollo_diode.md` | 1,230 | **The only vehicle.** Coupling graph, fifteen failure chains, scenario ladder, coordination metrics, ~120 channels with bands, precisions, rates and event conditions. | ~30 × `Sim`; 12 channels literally `mission dependent` |
| `electrical_diode.md` | 1,144 | A generic 28 VDC dual-bus EPS with invented-but-self-labelled reference numbers: 37-row catalogue, load-shed ladder, 8 rules, 30 test vectors. Generation technology is an abstract `GEN_A/B`; mission duration is `Unknown` (`:120-122`). | `ref.` / `Reference`; `UNSPECIFIED` ×4 |
| `eclss_diode.md` | 755 | An authority-boundary spec with a 44-row catalogue bolted on. Declares no spacecraft assumed (`:17`, `:36`) and **deletes four of apollo's values** (§2). | `REF`; six `*-configured` variants; zero `UNSPECIFIED` |
| `gnc_diode.md` | 1,716 | An interface contract wrapped around **real mathematics** — an error-state EKF with Joseph-form update, a quintic segment generator, a quaternion feedback law, a QP allocator — on top of an absent vehicle. ~650 lines are fenced code; ~290 are prose. | `Unspecified` in prose; `configurable`, `mission-defined`; zero `UNSPECIFIED`/`RIP-REF`/`Sim` |
| `main_propulsion_diode.md` | 1,125 | An authority-and-sequencing contract: guarded state machine, 44-row point dictionary, admission pipeline, leak FSM. **No fluid physics**: two equations in the file, no thrust law, no mass flow, no blowdown. | `RIP-REF` ×32; `_cfg` symbolic bounds in 19 of 44 point rows |
| `rcs_diode.md` | 1,400 | The strongest engineering artifact of the set: 41-channel catalogue, real allocation and pulse-generation mathematics, 22-row FDIR table, safe-mode ladder — for a generic RCS service, not this vehicle. | `RIP-REF` ×9; a 23-row table whose every value is `Unknown` |
| `communcations_diode.md` | 1,371 | **Not a communications specification.** A secure-transport specification for the diode itself. `snr`, `antenna`, `pointing`, `carrier`, `S-band` appear **zero** times. | `UNSPECIFIED` ×125 |
| `thermal_diode.md` | 1,018 | A TCS schema and safety-semantics layer. Exactly one temperature, and it is a serialisation example. Its one differential equation (`:56-70`) has terms nothing can populate. | `UNSPECIFIED` ×45; `Mission supplied` ×16 |
| `consumables_diode.md` | 2,291 | Half a genuinely good resource-accounting ontology; the other half is **three serialisations of one 19-field schema** (JSON Schema, Avro, Protobuf — 590 lines) plus transport. | `UNSPECIFIED` ×24; every rule operand a `cfg()` key |
| `events_diode.md` | 1,138 | A generic event-processing stack — envelope, rule engine, SQLite store, verification — labelled "Structural, Pressure, and Sequential Events". Contains **no** staging, pyro, hatch, docking, jettison or separation event. | `mission configuration items`; `configured` |
| `avionics_diode.md` | 1,095 | An **aircraft** avionics ICD template: ARINC 429/664, GNSS, elevons, DO-178C. Its one durable contribution is seven sensor-diagnostic functions. | `ICD`; `profile`; `configured` |
| `crew_diode.md` | 1,047 | A caution/warning and crew-display contract: four alert levels, alert lifecycle with suppress/inhibit/shelve, advisory-only outputs. It supplies **no** display topology (§8). | 4 × `UNSPECIFIED`, all protobuf enum sentinels |

**How much of each is transport rather than domain.** A heading-attribution pass puts the
transport-and-meta share at roughly: avionics 81%, communications 72%, thermal 49%, main
propulsion 47%, ECLSS 43%, crew 37%, electrical 35%, events 29%, RCS 22%, consumables 13%,
GNC 8%, apollo 2%. The four highest are the four whose domain payload is thinnest. Treat
these as estimates of a judgement, not measurements.

**Placeholder census** (`UNSPECIFIED` 219 total: communications 125, thermal 45, consumables
24, GNC 6, events 5, avionics 4, electrical 4, crew 4, main propulsion 2, apollo 0, ECLSS 0,
RCS 0. `RIP-REF` 44: propulsion 32, RCS 9, thermal 3. `CRA-REF` 2, both in consumables.
`TBD`, `TO BE`, `MISSION-CONFIG`: zero). Three qualifications matter more than the totals:

- 31 of the 219 are protobuf enum sentinels (`FOO_UNSPECIFIED = 0`). The four in `crew_diode`
  are *all* sentinels: crew defers nothing through this token.
- 194 of 219 sit in three documents. Seven specs contain no deferred-requirement use of it at
  all and express deferral as prose or a `_cfg` suffix. **A token census understates deferral.**
- `Sim` is not a deferral token. `apollo:42` defines it as a *recommended baseline that is not
  an assertion about Apollo* — the opposite of `UNSPECIFIED`. The README conflates three
  different things: unimplemented, unverified, and invented-but-flagged.

**Only four of the twelve use RFC-2119 normative keywords at all** (`communcations` 22 ×
`MUST`, `electrical` 20 × `SHALL`, `events` 16 × `MUST`, `crew` 1). In the other eight you
cannot tell a binding requirement from an aspiration — which is also why the three readings of
`RIP-REF` coexist: `thermal:159` treats it as an *escape from* `UNSPECIFIED`, while
`main_propulsion:36` and `rcs:29` treat it as a default to be replaced before qualification.

**The citation apparatus is unusable.** 871 citation markers, 378 distinct, all of the form
`cite:turn24view0` / `filecite:turn0file3`. There is no bibliography, no reference list, and
no section number, revision date or clause identifier anywhere. The `filecite` markers resolve
to the other research documents; the `cite` markers resolve to web-browsing turns in the
generating session and **cannot be dereferenced at all**. Every external claim in the corpus —
NASA limits, ECSS clauses, Apollo chronology — is unverifiable by construction. The standards
*numbers* are real (CCSDS 133.0-B-2, ECSS-E-ST-31C, NIST SP 800-82r3, NASA-STD-3001,
JSC-67723); it is the claims attached to them that cannot be followed.

---

## 2. The finding that governs the rest

**The subsystem specifications are not a partially-filled vehicle. They are a different kind
of document, and three of them instruct you to delete apollo's numbers.**

`integration/README.md:21-31` states the standing rule: *"apollo supplies the vehicle and the
experiment; the subsystem specs supply the per-domain contracts. Where they disagree on a
number, apollo wins."* That reads as a tie-break for incidental conflicts. It is not.
`eclss_diode.md` disagrees with apollo on purpose, on the record, with reasons:

| apollo | eclss_diode.md | Reason given |
|---|---|---|
| `eclss.cabin_pressure_psia` 4.8–5.2 (`apollo:88`) | `:734` "**Delete as generic ECLSS default**" | "Current NASA generic crew-exposure envelope is >34.5 kPa and ≤103 kPa; mission nominal pressure is project-specific." |
| `eclss.co2_pp_mmhg` >7.6 caution (`apollo:90`) | `:735` "**Delete as generic CO₂ criterion**" | "Current NASA nominal requirement is one-hour average ppCO₂ ≤3 mmHg; off-nominal limits are program-specific." |
| `eclss.o2_supply_pressure_psi` 750–950 (`apollo:91`) | `:736` "**Remove from generic interface**" | Source architectures differ; expose sensor-declared ranges instead. |

Its executive summary says so directly (`:19`): the Apollo-style values "were historically
useful Apollo-style scenario values, but they must **not** become universal ECLSS control
thresholds." And it is arithmetically sharper than the document admits: 4.8–5.2 psia is
33.1–35.9 kPa, while the NASA floor eclss adopts is 34.5 kPa — **half of apollo's nominal band
would be illegal under eclss's own criterion.**

`thermal_diode.md:965` does the same for a whole domain: with no standalone TCS predecessor,
"prior TCS-specific values — temperature limits, heater ratings, radiator sizing, thermal-zone
definitions, sensor accuracies, sampling rates, pump characteristics, valve timings,
thermal-control algorithms and TCS command IDs — are **UNSPECIFIED**. This report does not
infer them from the communications, propulsion, GNC, ECLSS or power specifications."
`main_propulsion_diode.md:36` refuses thrust, mixture ratio, minimum impulse bit, valve
transit, throttle range, tank capacity and ignition timeout on the same grounds. `gnc_diode.md:113`
assumes "no fixed mass, inertia, thrust, aerodynamic, landing, rendezvous, or orbital model."

**Consequence.** "Apollo wins" is not conflict resolution; it is a decision to override the
newer documents' central stance — that they describe a *generic* mission-configurable vehicle
rather than *this* one — everywhere the two meet. That decision is probably right for this
project. It needs to be recorded as a decision, once, with its cost, rather than applied
silently case by case. The design already has the right instrument: the provenance field in
`simulator-design.md:151-156` ("whether it is apollo-anchored, a spec default, or chosen to
make the thing run"). It should be populated for the corpus itself, not only for the
dictionary that comes out of it.

The corollary matters as much: **a specification that is confidently concrete is more
dangerous here than one that is empty**, because its numbers cannot be distinguished from
apollo's without reading both. §7 gives the live example.

---

## 3. What apollo actually supplies

`integration/README.md:29-31` says apollo contains "masses, anchored ranges, the coupling
graph, failure chains, the mission profile, the scenario ladder, the coordination metrics."
Four of those six are real. **The masses are not, and neither are any mission durations.**

- `mass` appears only as a thing to be hidden (`:36`) or depleted (`:743`, `:747`) — never with
  a value. There is no inertia tensor, no centre of mass, no tank size, no Δv budget, no thrust
  level, no Isp, no burn duration. `rcs_diode.md:119-121` confirms it from the other direction,
  naming each absence and what it blocks.
- Twelve catalogue entries are literally `mission dependent` (`:119-122`, `:193-200`); the rest
  are ranges or `Sim` recommendations.
- **No mission duration appears anywhere.** The "8-day mission" and 34,560,000 ticks that carry
  `review-findings.md`'s throughput argument (§13) are the designer's inputs, not apollo's.
  The figure is plausible for the profile apollo recommends (`:1064`), but the surface stay is
  unspecified and the whole performance argument scales with it. `electrical_diode.md:121`
  independently records mission duration as `Unknown`.

What apollo *does* supply is a great deal, and it is the reason the corpus is worth reading at
all: the coupling graph (`:258-303`), fifteen failure chains with second- and third-order
consequences (`:327-343`), the stochastic hazard model with a severity ladder (`:349-384`), the
three-level epistemic doctrine (`:34-40`), the sensor model and eleven fault modes (`:647-671`),
the three-times model and jitter budgets (`:692-702`), the telemetry budget (~120 channels,
25–35 KB/s, `:863-885`), the rate set (50 Hz physics, 10 Hz fast, 1–2 Hz engineering, 0.2 Hz
slow, `:1084-1092`), the verb families (`:237-246`), the arm/commit pattern (`:476-509`), the
scenario ladder (`:1106-1225`), and twenty coordination metrics (`:1001-1022`).

**So the vehicle's globals are 100% invention, and no document plans to supply them.** This is
the largest hole in the corpus and it belongs to the missing mission-configuration document
(§6).

---

## 4. Where the corpus contradicts apollo

Each row was verified against both files. Per the standing rule apollo wins every one.

| Quantity | apollo | Conflicting document | Effect if the spec were followed |
|---|---|---|---|
| DC bus band and event | 27.0–30.5 V; event `<26.5` for 0.5 s (`:73`) | `electrical:251` "24–32 V normal operational envelope"; `:337` "25.5/24.5/23.5 V tiers" | A bus at 26.0 V alarms under apollo and is nominal under electrical. **The two disagree about when the vehicle is in trouble.** |
| Bus current | 10–120 A (`:75`) | `electrical:251` 40 A continuous; sensor ±100 A (`:261`) | apollo's normal range exceeds the rating and the instrument's range. |
| Generation | Three H₂/O₂ fuel cells; O₂ shared with ECLSS (`:69`, `:780-784`) | `electrical:122` abstracts generation as `GEN_A/B`, "PV, fuel-cell, RTG, external supply require different models" | Loses the coupling apollo calls "particularly important": O₂ → fuel cell → bus → ECLSS pumps. |
| Cabin pressure, CO₂, O₂ pressure | 4.8–5.2 psia; >7.6 mmHg; 750–950 psi (`:88-91`) | `eclss:734-736` delete all three | §2. |
| Physics tick | 50 Hz (`:24`, `:1084`) | `gnc:131` 100 Hz inner loop; `rcs:23` 100 Hz; `events:20` 200 Hz | Three different plant rates; events is 4× apollo. |
| Fast telemetry / intake | 10 Hz / ≤100 ms (`:1085-1086`) | `gnc:87-88` 20 Hz / ≤50 ms; `rcs:25`, `events:24` 20 Hz | 2× apollo's own budget. |
| Position/velocity publish | 2 Hz (`:119-120`) | `gnc:439` 10 Hz | 5× on the highest-volume inferred channel. |
| Chamber pressure | % nominal, 95–105 firing, 10 Hz, `<90` event (`:135`) | `main_propulsion:193` Pa, 50–100 Hz, ±1 % FS, fault at 0.80 | Different unit, 10× rate, 10 points wider fault band. |
| Thrust | % commanded / % estimated, 10 Hz, `discrepancy >5%` (`:136-137`) | `main_propulsion:195` newtons, 50 Hz | The discrepancy check cannot be computed across the two. |
| Δv | `prop.accumulated_dv_m_s` with a cutoff target (`:141`) | none — cutoff is duration/plan-driven (`main_propulsion:645`) | Loses the burn-accounting channel. |
| Structure fidelity | Medium; "pressure vessel, leaks, latches, docking/staging/pyro states; **not** finite-element structural mechanics" (`:753`); flexible-body modes on the simplify list (`:815`) | `events:222`, `:225` build the domain on modal excitation and model residual | Inverts the ladder for the domain and omits everything apollo asked for. |
| Comms content | 8 channels; attitude→pointing→SNR coupling (`:161-168`, `:786-790`) | `communcations_diode.md` has none of it | The spec named for the domain does not describe the domain. |
| Attitude actuation | RCS only (`:52`, `:147-153`) | `gnc:117`, `:317`, `:557`, `:1001` add wheels, CMGs, magnetorquers, momentum dump; `:118`, `:528-530`, `:952` add GNSS, LiDAR and aerosurfaces | Channels for hardware the vehicle does not have. |
| Propulsion verbs | `start_burn`, `stop_burn`, `set_throttle` (`:241`) | `main_propulsion:293-296` `ARM_BURN`/`COMMIT_BURN`/`ABORT_BURN`/`SET_THROTTLE_PROFILE` — an early stop is only an abort | Moves the operator surface a level up and removes nominal early cutoff. |
| Pressure units | psia / psi / mmHg (`:88`, `:91`, `:139`) | `avionics:165` Pa; `events:177`, `:514` Pa; `main_propulsion:188-193` Pa | Two unit systems for one vehicle. |
| Wire format | JSON `values{}` + `quality{}`, `aurora.capsule.telemetry.v1` (`:599-627`) | `thermal:225` "deterministic CBOR is a suitable default… JSON retained only as a diagnostic/test projection"; `communcations:29` CBOR + COSE_Sign1; `events:342-378` Protobuf + SQLite | A CBOR diode breaks `docs/diode-contract.md` §2 outright. |
| Command lifecycle | `SEEN → PARSED → ACCEPTED\|REJECTED → QUEUED → EXECUTING → SUCCEEDED\|FAILED\|ABORTED` (`:453`) | `electrical:424` inserts AUTHORIZED and a terminal REVALIDATED; `thermal:643-679` RECEIVED/AUTHORIZED/ADMITTED/…/VERIFYING/COMPLETED; `gnc`, `rcs`, `eclss` add REVALIDATING as a transient; `consumables` uses CamelCase | Six chains. `REVALIDATED` is terminal in one document and `REVALIDATING` transient in four — on the single most safety-relevant transition. Apollo itself has no revalidation *state* despite making effect-time recheck its central claim (`:455`). |
| Quality vocabulary | GOOD / SUSPECT / SATURATED / INVALID / INFERRED (`:215`, `:620-625`, `:688`) | `electrical:589-599` (8); `thermal:304-327` (4 + 14 bit flags); `rcs:207` (10); `events:141` + `:162` (two lists); `avionics:584-592` (7 flags); `communcations:290-291` (5, omitting SUSPECT and SATURATED); `crew:187` | Union ~14, intersection three. `SATURATED` — the code apollo makes load-bearing at `:215` and the design calls the honesty exception — is absent from `crew_diode.md` **entirely**. `TEST`(crew) = `SIMULATED`(electrical) = `TEST_INJECTED`(rcs). |
| Alert severity | Apollo defers to crew C&W (`:222`) | `crew:31` EMERGENCY/WARNING/CAUTION/ADVISORY; `events:198` INFO/ADVISORY/WARNING/CRITICAL/EMERGENCY; `avionics:516` INFO/WARNING/FAULT/CRITICAL | Union six, intersection three. A structural event carries a severity with no crew level, and `severity` vs `priority` are two field names for it. |
| Channel priority | no priority enum | `gnc` P0–P5; `main` P0–P4; `rcs` P0–P5; `electrical` P0–P4; `thermal` P1–P4; `consumables` P0–P5; `avionics`/`crew` P0–P3 | Seven scales. |
| Verb style | lowercase `set_coolant_pump`, `set_rcs_mode` (`:237-246`) | `electrical:621`, `thermal:391-395`, `rcs:362-380`, `gnc:302-321`, `main_propulsion:285-299` SCREAMING_SNAKE | The dictionary cannot key both. |
| Restart ambiguity | `seq` only (`:604`); a boolean frame-sync (`:183`) | `boot_id` in `communcations`, `thermal`, `consumables`, `avionics`, `events`, `crew` | **Six of twelve specs cannot express a restart**, which is what a receiver needs to distinguish loss from reboot. |

Two absences are holes rather than conflicts, and both are verified by grep:

- **`communcations_diode.md` is not about communications.** `snr` 0, `antenna` 0, `pointing` 0,
  `carrier` 0, `S-band` 0, `bitrate` 1 (declaring itself `UNSPECIFIED`). Its own open-parameter
  register (`:128-160`) is 33 rows of `UNSPECIFIED`. A builder given only this document can
  build a diode and cannot build a communications subsystem. `apollo:161-168` remains the only
  communications specification that exists.
- **`events_diode.md` contains no one-way actions.** `pyro` 0, `hatch` 0, `dock` 0, `staging` 0,
  `jettison` 0, `arm_event` 0, `arm_token` 0. Its only `latch` is the alert-lifecycle latch
  (`:200`, `:278`). The arm/commit-with-token shape the design adopts
  (`simulator-design.md:107-108`) comes from `apollo:476-509` and from nowhere else.

---

## 5. Where the corpus contradicts itself

**The dictionary cannot be built by extraction.** This is the most consequential cross-cutting
finding, and it is about names rather than values. The same object has a different name in
nearly every document:

- **The uplink** is `console.json` in the contract (`diode-contract.md:29`); `/diode/command/host1.json`
  in `apollo:538-545`; `/eclss/cmd/<principal>/request.json` in `eclss:87-95`; `cmd/<principal>/request`
  in `gnc:191`; `/diode-cmd/inbox/` in `communcations:113-124`; `/rx/resource-commands/` in
  consumables; `/vehicle/command-in/` in `avionics:222-232`. `console.json` appears in five
  documents and **only ever as the thing being criticised**. `consume_batch()` is named once in
  the whole corpus — `communcations:121` — as a defect, and `avionics:232` says the destructive
  intake "should remain". Two specs, opposite rulings, on the property the contract calls its own.
- **`state_revision`** is in nine specs and absent from `communcations`, `avionics` and `events`.
- **Quality codes, priority scales, alert ladders, lifecycle chains**: see §4.
- **The telemetry ring**: the contract fixes `telemetry/NNN.json`; `apollo:593` uses three
  surfaces (`latest` / `history` / `events`); `communcations` uses `/diode-tlm/ring/` with
  `.pb` segments; depth is 10–15 min in apollo (`:879`), a normative 10 min in `events:89`,
  and a 10-min baseline in `crew:265`.

**This is why the standing filter in `integration/README.md:33-42` is doing more work than it
looks.** The later documents are not merely *mentioning* the hardware dual-diode; they are built
on it. `eclss:741` makes "dual independently unidirectional telemetry and command paths"
normative; `crew:1028-1030` adopts it "as the common external boundary" and retains the
shared-volume mode "only as logical/SIL emulation"; `events:344` offers a third variant with
`requests.json` beside `console.json` and `latest.pb`/`latest.sig`/`ring/seg-0000.pb`. Applying
the filter means rewriting portions of eight documents, not ignoring a section in each.

**Internal defects worth fixing before transcription.** A representative list, every item
verified:

- **`gnc:1175-1177` puts the spacecraft inside the Moon.** The one concrete trajectory in the
  document — `MOON_J2000`, `position_m [-182340.4, 1711023.8, 94322.1]` — has |r| = 1723.3 km
  against a lunar mean radius of 1737.4 km: **14.1 km below mean radius**, with |v| = 1631.8 m/s
  against a circular 1686.7 m/s at that radius. It is labelled illustrative (`:1161`), which
  does not help: it is the only worked state vector in the corpus, and a builder who copies it
  initialises the vehicle underground.
- **`gnc`'s example cannot satisfy `gnc`.** `producer_id` is required (`:226`) and missing from
  both JSON examples and from `GncTelemetryFrame` (`:1460-1474`), which also drops
  `source_time_ns`, `quality` and `frame_revision`. Two quaternion examples have norms 0.999994
  and 0.999993 (`:1179-1184`, `:1218-1223`) while `:368` requires rejecting non-normalised
  quaternions — and no tolerance is given anywhere.
- **`gnc`'s command vocabulary is triplicated and inconsistent**: `ARM_MANEUVER`/`COMMIT_MANEUVER`
  (`:308-309`) vs `ARM_PLAN`/`COMMIT_PLAN` (`:615-616`) vs the FSM's `GENERATE/LOAD_PLAN`
  (`:635`), a name in neither list; `VALIDATE_TRAJECTORY` (`:307`) vs `VALIDATE_PLAN` (`:614`).
  The FSM has no COMMIT edge at all — `ARMED → REVALIDATING` is triggered by "execution window"
  (`:644`). The documented command set cannot drive the documented state machine.
- **`main_propulsion`'s guard table covers 14 of the ~21 transitions drawn** (`:595-632` vs
  `:638-651`), and the table is declared normative (`:634`). `:933-950` specifies an
  agent-constraint mechanism (`minimum_propellant_reserve`, `max_throttle_allowed`) for which
  the 15-verb table (`:285-299`) has no command — the GNC sibling has one (`gnc:318`).
  `pc_shutdown_fraction` mixes `Pc_nominal` with `Pc_commanded` in the same profile
  (`:665-668`). Its `oneof payload` defines 4 messages for 15 commands, with no `CommandResult`
  and no lifecycle enum.
- **`electrical:424`** names a `REVALIDATED` lifecycle state that does not exist in its own
  `enum CommandStatus` (`:636-651`, fourteen values, none of them it). `:325` protects at 44 A
  while `:248` limits at 45 A — protection fires before the limiter engages. `:324` applies the
  bus tiers to a source converter's output.
- **`thermal:638`** calls `ACCEPTED → REVALIDATING` "the most important transition" while the
  machine's states are AUTHORIZED → ADMITTED → QUEUED → REVALIDATING (`:651-657`); `ACCEPTED`
  never exists, and `:620` offers `ABORTED` as a terminal that no state machine contains.
  `UNCONFIGURED`, declared a first-class condition at `:31` ("not 'nominal'"), never appears
  again anywhere in the document. `sample_offset_us` is `sint32` (`:302`), spanning ±35.8 min.
- **`consumables`' one worked numeric example does not close.** `available_to_new` is
  1,504,000,000 J and `consumption_rate` is 185 W (`:2033-2048`), so the implied time to
  critical is 8.13 × 10⁶ s; the published `time_to_critical_ms` is 4,870,000 ms = 4,870 s.
  **Off by a factor of ~1,670.** The other quantities in the same message are exactly consistent
  (2454 = 2514 − 60; 1504 = 2454 − 600 − 200 − 150), so the accounting is sound and the forecast
  field is decoration. Its ontology also drifts: seven behaviours are enumerated at `:19-30`,
  the catalogue uses `DEPLETING-LIFE`, `ACCUMULATOR` and `CAPACITY/BUDGET` (`:237-243`) which
  are in no vocabulary, a twelve-value enum follows at `:1433-1446`, and a pyrotechnic, a
  radiation budget and a cryptographic-key quota have no category. All twenty-one change-log
  rows are stamped "CRA v1.0.0 — 2026-09-12" (`:2291`).
- **`events` contradicts its own ring design**: "Ordinary telemetry frame | 256 KiB" and
  "One-second telemetry segment | 2 MiB" (`:443-444`) against "Each segment contains the 20
  agent-facing frames for that second" (`:382`) — 20 × 256 KiB = 5 MiB. The implied stream is
  5 MB/s, two orders of magnitude above apollo's whole-vehicle 25–35 KB/s (`:872`).
- **`rcs:156`** says free drift retains "hard safing", but the only transition out of
  `FREE_DRIFT` is back to `ATTITUDE_HOLD` (`:883-884`): a fault in free drift has no drawn path
  to the safe states. `:846-851`'s residual accumulator has no clamp, so quantisation upward
  leaves a debt and the next request silently under-fires. `:794` forbids encoding a universal
  wheel percentage into software and `:798-800` supplies an 80/90/95 % table.
- **`communcations:742-747`**'s command-queue budget `B_cmd ≥ R_cmd,burst × T_outage × S_command,max`
  is dimensionally wrong unless `R_cmd,burst` is commands/second, which the symbol does not say —
  and the parallel telemetry inequality two lines later names its rate in bytes/second.
- **`eclss:374`** gives `atm.leak_rate_estimate` the unit "Pa/s or g/s" — two dimensions in one
  field — and `:289` lists `ESTIMATED` as a quality code while `:64` defines it as a kind.
- **`crew`'s prose and its schema disagree**: `response_time_budget_ms` (`:335`) and
  `latch_policy` (`:342`) are in the alert record but missing from the `AlertEvent` protobuf
  (`:606-635`), so a builder generating from the proto loses latch policy. `DATA_GAP` is asserted
  (`:269`, `:918`) and absent from the quality enum (`:526-534`). `LATCHED_CLEARED` (`:837-840`)
  has no re-assert edge, so a latched alert whose condition re-asserts during the dwell cannot
  return to active. `keep_pending()` (`:826-827`) is a named function with no semantics.
- **`avionics:503-512`** journals `ACCEPTED` twice for every scheduled command; `time_health()`
  (`:476-483`) can never return the `HOLDOVER` its own enum declares. `:378`'s
  quality-assignment function reads `s.bit_failed` — the simulator's fault state — which is
  precisely the leak `simulator-design.md:496-508` exists to prevent; it is survivable only if
  `bit_failed` is redefined as a BIT *output*.

---

## 6. What nobody wrote

- **The mission configuration.** No document supplies mass, inertia, centre of mass, tank sizes,
  mission phase durations, or the values apollo marks `mission dependent`. `simulator-design.md:601`
  still lists "mission configuration/phase" as *expected*; nothing has landed. More sharply:
  **mission phase is in the effect-time revalidation predicate** (`diode-contract.md:147`
  re-checks "gates, interlocks, allowances and phase"; `apollo:439` has an `allowed_phases`
  field) **and no document defines it.** The executive's central safety check references an
  undefined quantity. This is not a gap that more reading closes.
- **The plant.** No document names an integrator: `RK4`, `Runge`, `Verlet`, `semi-implicit`,
  `symplectic`, `leapfrog` and `forward Euler` appear **zero times across the whole corpus**, and
  `gnc:127` says dynamics fidelity is "Unspecified — interface semantics are invariant across
  simple point-mass simulations and 6-DOF high-fidelity vehicles". The 50 Hz single-rate 6-DOF
  choice, and therefore the entire method question in `review-findings.md` §6, is an unsourced
  integration decision rather than an extraction. `gnc:1672` is the only place a source even
  acknowledges the question, and it demotes the 50 Hz baseline to "not normative for GNC".
- **A channel-mapping layer.** No spec maps its identifiers onto apollo's: `acs.mode` vs
  `rcs.mode`, `mass_est` vs `rcs.propellant_remaining_pct`, `pressure_abs` vs `feed_pressure_pct`,
  `BUS_A.voltage_v` vs `power.dc_bus_a_v`, `mps.*` vs `prop.*`, `cws.*` vs `cw.*`,
  `time_to_critical_ms` vs `res.time_to_limit_s`. The dictionary needs a crosswalk that does not
  exist.
- **`coupling.yaml`.** The design calls this "the one nothing supplies" (`simulator-design.md:138`).
  Correct: apollo has the graph as a mermaid diagram (`:258-303`) and no document has it as data.
  The prior review (§8) adds that topology alone cannot bound fidelity without per-edge gains
  evaluated at crisis operating points.
- **The crew display contract.** `simulator-design.md:561-564` claims `crew_diode` defines "which
  panel shows what, in which module". It does not. `crew:42` says display topology "was not
  supplied" and "remains configuration item"; **`module` appears zero times in the file** and
  `panel` once, as a widget name (`:367`). Table `:352-370` lists display *widget types* with
  source signals and rates — no location, no station, no per-point grouping. The third argument
  of `review-findings.md:100`'s perception function must be authored, not extracted.
- **Load inventory.** `electrical:216-224` names eight loads. A twelve-domain vehicle needs
  wattages, priorities and shedding sequences per load.
- **Thermal parameters.** `thermal`'s own equation (`:56-70`) has `C_i` and `Q` terms with no way
  to populate them, and the evaporator/sublimator — the Apollo LM water boiler, behind apollo's
  `set_evaporator_feed` verb (`:239`) — is absent from its actuator inventory (`:189-207`), which
  lists TEC, cryocooler and PCM instead.
- **Propulsion physics.** `main_propulsion` has a throttle *command* and a thrust *estimate*
  (`:195`) with no relation between them: no throttle→thrust law, no mass flow, no blowdown, no
  cutoff tail-off, no Isp. The design's fidelity claim — "propulsion (tank/feed/valve states,
  **thrust response**; no combustion chemistry)" at High-medium (`simulator-design.md:337`) — is
  **half supported by its own source**, which refuses the thrust half at `:36`.
- **Communications and the irreversible-event taxonomy.** §4.
- **Hazard rates.** Apollo supplies the only ones (`:363-374`). The word "hazard" does not appear
  in `eclss_diode.md` at all.
- **The stoichiometric transformation.** apollo's fuel cell is `O₂ + H₂ → power + water + heat`
  (`:849-855`). `consumables`' `TRANSFER` is logistical (`:739-782`) with no transformation
  object, so the single most Apollo-specific coupling cannot be expressed in its model.
- **An owner for the attitude inner loop.** `rcs:23` and `gnc:852-927` both claim attitude
  control and allocation at 100 Hz, with different conflict domains and interlocks.
  `simulator-design.md:91-97` resolves it by fiat, which is fine, but the reconciliation note
  should say so.

---

## 7. What is genuinely worth taking

The corpus is not worthless; it is mislabelled. Setting aside the transport pages, the deferral
registers and the standards inventories, what remains is a set of **schemas, safety semantics,
algorithms, fault libraries and test vectors** that the design's dictionary-plus-linter
architecture needs and that apollo does not contain. In rough order of value:

1. **`gnc`'s mathematics**, which is real and was checked: the quintic coefficients (`:738-749`,
   all six boundary conditions verified over 200 random parameter sets, max residual 8e-12); the
   error-state EKF with Joseph-form covariance update (`:759-811`); the quaternion feedback law
   (`:856-862`); the constrained QP allocator (`:890-922`); NIS gating (`:844-848`); and the
   bandwidth budget (`:1110-1120`, every row re-derived: 32.3 kB/s = 259 kbit/s, 323 with
   framing, ~28 MiB per 15 min). Also `:1616-1653`, **38 concrete integration-test rows** — the
   most directly reusable single artifact in the corpus.
2. **`avionics:371-509`** — seven diagnostic functions (`sensor_health`, `redundant_vote`,
   `estimator_innovation_rule`, `cusum_rule`, `actuator_tracking`, `power_rule`, `thermal_rule`,
   `time_health`). This is the **only** place in the corpus that supplies the diagnostics apollo
   demands and never specifies: apollo says a silently biased sensor must stay `GOOD` until a
   real diagnostic catches it (`:688`) and lists eleven fault modes (`:661-671`) without saying
   what detects any of them. Caveat in §5.
3. **`rcs:804-853` + `:674-694`** — pulse generation with a residual accumulator, minimum on/off
   time and fire/release hysteresis. apollo's RCS is a boolean valve and a scalar deadband;
   without this, firings are free and chatter is unbounded. `rcs:264-277`'s pulse-resolution
   acquisition rule (`f ≥ max(3/T_min, f_FDIR)`) fixes a real apollo gap, and `rcs:1015`'s
   "hysteresis and dwell are mandatory" is a rule apollo never states.
4. **`main_propulsion:695-702`** — a six-state leak FSM (`NOMINAL → SUSPECT → CORROBORATING →
   CONFIRMED → ISOLATED → UNCONTAINED`) that counts evidence rather than flipping a boolean, and
   `:322-339`'s ordered admission pipeline, which is implementable verbatim as the command
   executive.
5. **`communcations:236-242`, `:265`, `:393-412`** — sequence scoped to
   `(source_id, boot_id, stream_id)` so a receiver can tell loss from reboot without trusting a
   clock; a per-point `max_decision_age_us`; and `INDETERMINATE` with the rule that an entry left
   `EXECUTING` across a restart is treated as indeterminate and never auto-replayed. This last
   one closes a hole in the contract (§8).
6. **`thermal:106-129`** — `ThermalZonePolicy`, a 21-field config schema with each field marked
   mission-supplied or mandatory: the shape the dictionary's per-domain config needs.
7. **`thermal:823-826`** — "Ordinary agents cannot change threshold values; they select
   versioned, pre-certified profiles… the model that reasons about the spacecraft must not also
   be able to rewrite the limits by which its reasoning is constrained." The best single safety
   idea in the corpus, and directly implementable as a read-only profile store.
8. **`thermal:709-723` and `:774`** — the ten-step temperature decision procedure and min/max
   credible-sensor voting: the minimum credible sensor for cold protection, the maximum for hot,
   so averaging cannot hide an extreme. `thermal:346` "a mean must never erase an excursion"
   belongs in the publisher's contract, and `main_propulsion:887-905` reaches the same rule from
   the bandwidth side.
9. **Freshness and staleness as mechanism** — `avionics:145` + `:943` (channel priority with an
   explicit shed order, and the acceptance test that saturating low-priority telemetry causes no
   missed high-priority deadline); `events:63` (a stale snapshot must not satisfy a
   safety-critical precondition; every such precondition declares a maximum data age);
   `crew:38`, `:273`, `:433` (stale or invalid data cannot silently become last-known-good and
   cannot clear a safety alert). Together these turn "stale evidence" from a convention into a
   check.
10. **The fault and test-vector libraries**: `electrical:986-1019` (30 vectors written as
    injection → expected → pass criterion), `thermal:906-941` (30 written against configuration
    symbols, so they instantiate with any threshold set), `events:979-997` plus the rule that
    golden vectors cover `threshold ± ε`, `rcs:948-1011`, `main_propulsion:995-1022`, and
    `avionics:292-311`'s validator order.
11. **Small additions the design has not yet noticed**: `events:1005-1013` adds timestamp
    freeze, timestamp jump and sequence duplication/gap to apollo's eleven fault modes;
    `eclss:65` adds a fourth epistemic kind (`SERVICE_STATE`) and `:381` adds `INCOMPLETE_WINDOW`
    for gaps in a rolling average; `avionics:176` requires discrete states to be edge-triggered
    *and* periodically reconciled; `avionics:192` requires dual source/monotonic clocks so a time
    discontinuity cannot make a safety dwell expire instantly; `gnc:431` separates a datum's
    quality from its estimator-inclusion, and `:441` adds `frame_revision` against silently
    changed frame definitions; `consumables:786-793` splits loss four ways (decay,
    leak-suspected, capacity-derate, loss); `consumables:1141` "unknown does not imply zero, but
    it also does not authorize optimistic use"; `consumables:1176-1178` indeterminate claims must
    not be auto-retried.

**The one recommendation to refuse.** `review-findings.md:188-196` proposes generalising
`electrical:814-890` as the template for hysteresis and dwell across the vehicle. Do not, without
re-anchoring it first. That ladder fires `DEGRADED` at `<25.5 V for 200 ms`, but apollo fires an
*event* at `<26.5 V for 0.5 s` (`:73`). Adopting it wholesale produces a plant whose protective
state machine believes the bus is healthy across a 2 V band in which its own telemetry says an
event has occurred — a self-inconsistent vehicle, in the one place the experiment most needs
consistency.

---

## 8. Bookkeeping in this repository that is now wrong

Small, but each is a claim a reader will trust.

| Site | Says | Truth |
|---|---|---|
| `docs/diode-contract.md:232` | "eight subsystem studies" | Eleven. The list omits avionics, events and crew, and §7 does not carry their findings. |
| `README.md:146` | same eight, same omission | as above |
| `CLAUDE.md:37` | "`docs/deep_research/` (~13k lines)" | 16,445 lines |
| `integration/README.md:29` | apollo contains "masses" | No mass, inertia, CoM, thrust or duration (§3) |
| `integration/simulator-design.md:4` | "Specs landed: apollo, electrical, eclss, gnc, main_propulsion, rcs, communications, thermal, consumables, crew" | `avionics_diode.md` and `events_diode.md` are on disk and unlisted; `:601` still lists them as *expected* |
| `integration/simulator-design.md:244` | "from `consumables`' seven kinds", then names four | The seven are Stock, Rate/capacity, Buffer, Inventory, Entitlement, Margin, Opportunity (`consumables:19-30`). Inventory, Entitlement and Opportunity are silently dropped. |
| `integration/simulator-design.md:254-257` | declines the claims lifecycle because "exposing reservations as verbs hands the fleet a ready-made deconfliction primitive… it must not publish them" | The decline is incomplete and, as written, self-defeating. `RESERVE_RESOURCE`, `RELEASE_RESERVATION`, `REQUEST_ALLOCATION`, `RELEASE_ALLOCATION` are four agent-facing verbs (`consumables:1008-1011`), **and** `reserved`, `allocated`, `committed` and `available_to_new` are *required* fields of the schema being adopted (`consumables:1568-1575`). `available_to_new` is what other agents' claims leave behind — publishing it hands over exactly the primitive the design means to withhold. Declining claims means editing the schema and dropping four verbs, not declining a feature. |
| `integration/simulator-design.md:561-564` | `crew_diode` defines "which panel shows what, in which module" | It defines no such thing; `crew:42` says topology was not supplied (§6). The `perceivable_subset` bound cannot be extracted. |
| `integration/simulator-design.md:556` | lists three advisory decision outputs | The enum is `NONE`/`ADVISORY_ONLY`/`CREW_ACTION_REQUIRED`/`REQUEST_SAFE_ACTION` (`crew:470-474`). Minor, but it is the fourth value that keeps an ordinary state from reading as an advisory. |
| `brief/PROTOCOL.md:115-118` | "The window is not a channel to another agent" | With `ask_crew` (`simulator-design.md:388-406`), say whether crew dialogue is **per console or shared**. If shared, ten agents can write prose into a vehicle surface and read it back — a world-supplied message bus, which `design.md` §8 refuses to supply. If per console, say so: the experimental consequence is entirely different. |
| `contract/diode_probe.py` check 5 | certifies the gate-variable pattern | The specs require the opposite for physical verbs — interlocks exclusively service-owned (`eclss:741`, `thermal:823-826`, `crew:162`). The probe cannot distinguish an agent-writable gate from a service-owned interlock, so checks 5 and 8 together will certify a design the corpus forbids. The vehicle should have to declare which is which. |

**The linter should refuse on vocabulary faults.** `simulator-design.md:141-150` lists what the
linter refuses a build for — missing limits, duplicate IDs, unit mismatches, inverted hysteresis,
unresolved dependencies. Given §5, it should also refuse when a code is outside the union of
quality vocabularies, when a lifecycle state is not in the canonical chain, or when a priority
falls outside the chosen scale. That is the mechanism that catches a corpus with six lifecycle
chains and seven priority scales, and it costs one table.

**One scope observation.** Decision #1 in `simulator-design.md:47` is that the vehicle lives in a
separate repository. Sixteen thousand lines of vehicle specification currently sit inside a
repository whose central invariant is "this repository builds everything except the vehicle"
(`README.md:12`, `CLAUDE.md:29-33`). Nothing depends on them: a grep for `deep_research` across
`*.py`, `*.sh`, `*.yml` and `*.toml` returns **zero** hits. `docs/superpowers/specs` already
carried a note that the design "relocates to the vehicle repo once that exists". Moving
`deep_research/` when that repo is created is free now and awkward later.

---

## 9. Method, coverage and confidence

**Verified by hand** (re-read in the file during this review, not taken from a summary): the
ECLSS deletions and both arithmetic checks (`eclss:467-470`, 13.5 psi/min = 1.5513 kPa/s, exact);
the bus-band conflict (`apollo:73` vs `electrical:251`, `:337`); `electrical:122`'s generation
deferral and `:121`'s `Unknown` mission duration; the missing enum value (`electrical:424` vs
`:636-651`); the CBOR default and profile rule (`thermal:225`, `:823-826`); thermal's governing
equation (`:56-70`); the `sample_offset_us` type (`:302`); consumables' seven behaviours
(`:19-30`), required claims fields (`:1568-1575`), four claim verbs (`:1008-1011`) and failed
worked example (`:2033-2048`); the events frame-size contradiction (`:382` vs `:443-444`); the
RCS `FREE_DRIFT` dead end (`:883-884`); the GNC example's radius (recomputed: 1723.3 km,
−14.1 km altitude) and its escape-hatch row (`:1671-1672`); the GNC bandwidth budget (re-derived
row by row); the crew display-topology sentence (`:42`) and the `module`/`panel`/`SATURATED`
counts (0/1/0); the mission-phase gap (`diode-contract.md:147`); the communications absence set
and the events one-way-action absence set (grep counts printed in §4); the placeholder and
normative-keyword censuses; the citation census (871 markers, 378 distinct, no bibliography) and
the four `deep_research` code-reference greps; and the prior review's load-bearing citations
(`consumables:523`, `thermal:965`, `electrical:814-890`), all of which are accurate.

**Two claims rejected in this pass**, recorded because the corpus invites them:

- *"There is not one differential equation in 13,572 lines."* False. `thermal_diode.md:56-70` is
  a lumped thermal energy balance, `consumables` carries conservation and reconciliation
  identities, and `main_propulsion:220-227` is a sampling rule. The accurate statement is
  narrower and still damning: **the specs contain a handful of equations and no plant** — no
  integrator, no dynamics, and no parameters with which to populate any of them.
- *"avionics is cited by zero specs."* `crew:5` cites eight predecessor files including an
  avionics one. What is true is that avionics landed second-to-last and no earlier document can
  have incorporated it — a consequence of the chain order, not a finding.

**Not verified.** The Apollo historical and NASA-derived figures in `apollo_diode.md` are
untraceable through the corpus, and I did not confirm them against NASA sources. The "8-day
mission" throughput argument in `review-findings.md` §13 inherits that uncertainty and its
inputs are the designer's, not apollo's. Two dated standards are worth checking before they
reach a bibliography: `rcs_diode.md:106` ("JSC-67723 Rev. A, June 22, 2026") and
`communcations_diode.md:51`'s SP 800-82 revision-status paragraph. Both are in the class of
confidently-specific, date-sensitive claims that this corpus's citation style makes unfalsifiable.
The per-document transport/meta percentages in §1 are a heading-attribution estimate, not a
measurement.

**The honest number, as a judgement.** Against the six pieces in `simulator-design.md:3.0`:
the **instruments** are substantially supplied (apollo's model, the fault libraries, the quality
and diagnostics material); the **executive** is half-supplied (the contract specifies it, and
`main_propulsion:322-339` and `gnc`'s guard material implement parts of it); the **dictionary**'s
per-domain rows are transcription-with-renaming, while its names, code unions, coupling and
globals are decision. The **plant**, the **window's vehicle side** and the **white-team plane**
are invention, and they are the largest artifacts. So: on the order of **one quarter extraction,
three quarters invention**, and the extracted quarter is the *shape* of interfaces rather than
their contents. That is not a criticism of the corpus — it is what a set of per-domain interface
contracts is — but it is the number to plan against, and it is why §2's decision needs to be
made explicitly rather than discovered one conflict at a time.

**What this review does not do.** It does not re-derive the design's numerical claims
(`review-findings.md` already does that, and its citations hold up), does not assess the mission
profile or scenario ladder beyond noting the missing durations, and does not decide the open
questions in §8 — those are John's.
