# 02 — Canonical vocabulary

The names, chains, codes and scales the vehicle dictionary will key on. `corpus-review.md` §5
showed the dictionary cannot be built by extraction: eight names for the uplink, six command
lifecycles, five quality vocabularies, seven priority scales, `severity` and `priority` as two
names for one field. This file picks one of each and records what was rejected, so the linter
can refuse a domain that arrives speaking a dialect (`reconciliation/README.md`, step 4).

**Rule V-01.** An identifier is canonical if it appears in `apollo_diode.md`. Where apollo is
silent, the name is chosen here once and recorded; where apollo and a spec collide, apollo's
name wins and the spec's is listed under "rejected" so a ported domain fails loudly rather than
silently forking the vocabulary.

---

## 1 · The file surface

Straight from `docs/diode-contract.md` §2, which is frozen, and the sole reason the specs'
transport names are rejected wholesale.

| Role | Canonical | Rejected |
|---|---|---|
| Uplink | `<DIODE_DIR>/<slug>/console.json` | `/diode/command/host1.json` (`apollo:538-545`), `/eclss/cmd/<principal>/request.json` (`eclss:87-95`), `cmd/<principal>/request` (`gnc:191`), `/diode-cmd/inbox/` (`communcations:113-124`), `/rx/resource-commands/` (consumables), `/vehicle/command-in/` (`avionics:222-232`), `commands.json`, `requests.json` |
| Downlink | `<slug>/output/<stamp>_<slug>_<cmd>.txt` | `command.status` objects (`communcations:118`), `result.json` |
| Mirror | `<slug>/state.json` | `capability.snapshot` (`communcations:436-452`, as a *section* of state.json) |
| Documentation | `<slug>/HELP.md`, `<slug>/README.md` | — |
| Telemetry | `<slug>/telemetry/NNN.json` — a fixed ring | `latest.json` (`apollo:592`), `history/` + `events/` split (`apollo:593-594`), `/diode-tlm/ring/seg-0000.pb` (`events:344`), `index.json` + `latest.sig` |
| Producer's own memory | `<DIODE_DIR>/<slug>/pending.json` | `/rx/commands/` + a service-side ledger directory |

**No `latest.json`.** A mutable "latest" pointer beside an immutable ring reintroduces exactly
the rewrite race the ring exists to avoid (`communcations_diode.md:705` against `:715-716`).
The newest frame is one scan of the ring index away, and `state.json` already mirrors the
headline values at the contract's own cadence.

**`capability.snapshot` is taken, as a section of `state.json`** — machine-readable
`verb`/`available`/`irreversible`/`deferrable`/`argument_schema`/`availability_reason` replaces
a prose `HELP.md` for machines while `HELP.md` stays for agents (`communcations_diode.md:436-452`).

**The result file gains a structured block** (D-02): a fenced JSON object appended to the body
carrying `command_id`, `lifecycle_state`, `effect_met_s`, `refusal_reason`. The filename stays
exactly as the contract fixes it, which the contract already declares forward-compatible
(`diode-contract.md:253-258`).

---

## 2 · Command lifecycle — V-02

One chain. `apollo:453`'s, plus the transient revalidation state that four specs correctly
insist on, plus the `INDETERMINATE` terminal D-01 needs.

```
SEEN → PARSED → VALIDATED → ACCEPTED | REJECTED
ACCEPTED → QUEUED → REVALIDATING → EXECUTING → SUCCEEDED | FAILED | ABORTED
REVALIDATING → INHIBITED | EXPIRED | STALE_STATE | CONFLICT_SUPERSEDED
EXECUTING → INDETERMINATE            (restart with the effect unproven)
```

| Decision | Rejected |
|---|---|
| `VALIDATED` once, covering syntax, schema and authority | `AUTHORIZED` (`electrical:424`) and `AUTHENTICATED` (`rcs:406`) and `Verified` (`consumables:1145`) as three names for one stage |
| `REVALIDATING` is a **transient state** | `REVALIDATED` as a **terminal** result (`electrical:424`) — it says the same word for the opposite thing, on the transition that matters most |
| `INDETERMINATE` is a terminal state | an `EXECUTING` entry that survives a restart and means nothing (`communcations:412`, `:597`) |
| `SUCCEEDED` | `COMPLETED` (`gnc:1526`, `mps:315`) |
| `CONFLICT_SUPERSEDED` as a first-class **refusal** | silent discard (`apollo:579` is explicit that the loser must be told) |
| SCREAMING_SNAKE, everywhere | `consumables`' CamelCase, `thermal`'s Title case |

Apollo has **no revalidation state at all**, despite `:455` making effect-time recheck its
central claim — the chain above is apollo's plus that addition, not apollo's alone.

---

## 3 · Channels

`<domain>.<name>[_<unit>]`, lowercase, unit suffixed where the unit is not obvious from the
name. Domains are apollo's twelve (`apollo:20`): `power`, `eclss`, `thermal`, `gnc`, `prop`,
`rcs`, `comm`, `consumables`→`res`, `avionics`, `structure`, `cw`, `mission`.

**Apollo's channel catalogue (`apollo_diode.md:71-229`) is canonical verbatim** — including the
`_pct`/`_psi`/`_c` unit suffixes, which are self-documenting and were chosen by the one document
making a claim about a vehicle. Every spec identifier renames to it:

| Spec identifier | Canonical | Source of the collision |
|---|---|---|
| `BUS_A.voltage_v` | `power.dc_bus_a_v` | `electrical:337` |
| `SRC_CONV_A.output_voltage_v` | `power.source_1_current_a` (current) / `power.dc_bus_a_v` (volts) | `electrical:324` — the same thresholds were applied to converter output and bus voltage |
| `acs.mode` | `rcs.mode` | `rcs:365` |
| `mass_est`, `mass_sigma` | `rcs.propellant_remaining_pct` (+ a separate sigma point) | `rcs:245-246` — the sigma is a *good* addition and is kept as its own point |
| `rcs.feed.<id>.pressure_abs` | `rcs.quad_<a-d>_feed_pressure_pct` | `rcs:242` — Pa absolute rejected for this vehicle; C-17 |
| `mps.*` | `prop.*` | `mps:171-242` |
| `cws.*` | `cw.*` | `crew:187` |
| `time_to_critical_ms` | `res.time_to_limit_s` | `consumables:1623` against `apollo:200` |
| `CDH.*`, `TIME.STATUS`, `SEC.DIODE_HEALTH`, `FDIR.EVENT` | `avionics.*` | `avionics:167-172` — an aircraft channel map |

Points a spec supplies that apollo lacks are **kept and named in the same style**, and they are
the specs' real contribution: `thermal.zone_<id>_t_c`, `eclss.pp_o2_mmhg`, `power.lcl_<id>_state`,
`prop.leak_state`, `avionics.sensor_bus_errors_s` (apollo has it), `gnc.estimator_rejection_reason`.
Anything a spec names that apollo neither has nor needs is deleted, not renamed (C-15).

---

## 4 · Commands — V-06

`lowercase_snake`, argument as a space-separated token, exactly as `apollo:237-246` and
`diode-contract.md:64`. Everything the specs supply is a *renaming* of an apollo verb or an
addition:

| Canonical | Spec form | Disposition |
|---|---|---|
| `set_bus_tie`, `set_breaker` | `SET_BUS_TIE` (`electrical:621`), no breaker verb | apollo name; **breaker verb added** — apollo's verb table lacks it and the hardware needs it |
| `set_coolant_pump`, `set_coolant_loop` | `SELECT_PUMP_STRING`, `SET_LOOP_MODE` (`thermal:391-395`) | apollo names |
| `set_evaporator_feed` | *no counterpart* | apollo's, and the evaporator/sublimator is **added to thermal's actuator inventory**, which lists TEC, cryocooler and PCM instead (`thermal:189-207`) |
| `arm_engine`, `safe_engine`, `load_burn`, `start_burn`, `stop_burn`, `set_throttle` | `ARM_BURN`/`COMMIT_BURN`/`ABORT_BURN`/`SET_THROTTLE_PROFILE` (`mps:293-296`) | apollo's, with arm/commit reserved for irreversible *events* (C-16); `accumulated_dv` cutoff added (C-12) |
| `set_rcs_mode auto\|manual\|free_drift` | `SET_RCS_MODE(ATT_HOLD\|TRACK\|FREE_DRIFT)` (`rcs:365`) | apollo's three modes; `ATT_HOLD`/`TRACK` become *targets*, not modes |
| `set_deadband` | `SET_CONTROL_PROFILE` (`rcs:377`) | **both** — profile selection plus the derived `rcs.deadband_deg` telemetry apollo publishes |
| `set_comm_mode`, `select_antenna`, `point_hga`, `set_power_amplifier`, `set_telemetry_profile` | *no counterpart* (`communcations_diode` has none) | apollo's, authored into `domains/comms/` (C-14) |
| `arm_event`, `execute_event` | absent from `events_diode` entirely | apollo's, with the two-step token (`apollo:476-509`) |

**Every registry entry declares its authority, and that declaration is two fields, not one.**

```yaml
verb: set_coolant_pump
argument_schema: {loop: enum[primary, secondary], state: enum[on, off]}
allowed_phases: [translunar_coast, lunar_orbit, descent, surface, ascent, rendezvous, return]
gate:        {kind: preference, variable: pump_primary}      # agent-writable, may only close
interlocks:  [thermal.pump_dry_run, power.bus_undervoltage]  # service-owned, never a preference
conflict_domain: thermal.primary_pump
irreversible: false
idempotent: true
execution_class: declarative
maximum_queue_age_s: 60
help: "..."
```

`gate` and `interlocks` are separate fields because `eclss_diode.md:741` and
`thermal_diode.md:823-826` require it (D-03), and because `contract/diode_probe.py` cannot tell
an agent-writable gate from a service-owned interlock without the declaration. **A verb with a
physical effect may not have an empty `interlocks` list without an explicit
`interlocks: none — reviewed`**, so that "we forgot" and "there are none" are distinguishable.

---

## 5 · Sample quality, sample kind, and injection — V-03

Three orthogonal axes. The corpus collapses them — `eclss:289` lists `ESTIMATED` as a quality
while `:64` defines it as a kind, and `thermal:474-476` sets both bit 8 and the provenance field
on the same point — and the collapse is what makes `crew_diode`'s quality enum unable to express
`SATURATED` (C-20).

**`quality`** — how much this sample is to be trusted, assigned **only** by a function that
cannot see the simulator's fault state (`simulator-design.md:496-508`). A silently biased sensor
stays `GOOD`:

| Code | Meaning |
|---|---|
| `GOOD` | within configured range, no diagnostic objection |
| `SUSPECT` | a real diagnostic objects — redundancy disagreement, rate-of-change implausibility, estimator innovation |
| `STALE` | older than the point's `max_decision_age_us` |
| `SATURATED` | pinned at a limit. **Carries an inequality, not a value**: publish `300.0` + `SATURATED`, never the hidden 750 (`apollo:215`). The single most load-bearing code in the corpus, and absent from `crew_diode` entirely |
| `OUT_OF_RANGE` | outside the configured engineering range, not pinned |
| `INVALID` | the channel is not producing a reading |
| `UNKNOWN` | the publisher cannot say; treated as `STALE` by every consumer |
| `SUBSTITUTED` | a redundant source is standing in; the substitute is named |

**`kind`** — how the number was produced, never used to gate trust:
`MEASUREMENT` · `ESTIMATE` · `COMMAND_ECHO` · `SERVICE_STATE` · `SIMULATED`.

`SERVICE_STATE` is the fourth epistemic kind `eclss:65` adds to apollo's A/I/T, and it earns its
place: a valve's commanded position is neither a measurement nor an estimate of the physical
world.

**`injected: true`** — a boolean on the frame, for white-team-injected values, so a test
injection is distinguishable from a fault without being announced to the agents. `TEST`,
`TEST_INJECTED` and `SIMULATED`-as-a-quality are all rejected as quality codes.

**Rejected outright:** `DEGRADED` as a quality (it is a subsystem *mode*), `FAULT` as a quality
(it is a conclusion, and `design.md:211-214` forbids publishing conclusions), and `ESTIMATED` as
a quality.

---

## 6 · Alert severity — V-04

One ladder, four annunciated levels, and the field is named **`severity`**. `crew_diode.md`'s
`priority` is rejected: seven documents use `severity`, and `priority` collides with the
frame-publication scale in §7.

| Level | Meaning | Absorbs |
|---|---|---|
| `EMERGENCY` | immediate awareness or action; emergency response available | `events:198` EMERGENCY, `avionics:516` CRITICAL |
| `WARNING` | safety-critical abnormal, prompt action | `events:198` CRITICAL, `avionics:516` FAULT |
| `CAUTION` | abnormal, timely action, more margin | `crew:386` |
| `ADVISORY` | situation awareness, no immediate cue | `crew:387` |

`INFO` exists only as a **non-annunciated** record class — it never lights a panel. This keeps
the design's adopted four levels (`simulator-design.md:544`) exactly as they are while giving
`events:198`'s five a home. `crew:433`'s rule survives intact and is generalised: **stale,
missing, invalid or unknown evidence never satisfies a clear predicate** — "sensor disappeared"
is not "hazard disappeared".

---

## 7 · Priority — V-05

One scale, P0 highest, used for publication and shedding. Seven scales in the corpus
(`gnc` P0–P5, `main` P0–P4, `rcs` P0–P5, `electrical` P0–P4, `thermal` P1–P4, `consumables`
P0–P5, `avionics`/`crew` P0–P3) reduce to:

| Class | Contents | Apollo class (`apollo:863-870`) |
|---|---|---|
| `P0` | abort, safing, S0 actions, the abort/safe-hold queue reserve | — |
| `P1` | alarms, command results, immediate event records | Events |
| `P2` | fast control: bus V/I, attitude and rates, active propulsion states | Fast control, 10 Hz |
| `P3` | engineering: pressures, flows, temperatures, comm metrics | Engineering, 2 Hz |
| `P4` | slow resources and derived margins | Slow resources, 0.2 Hz |
| `P5` | bulk history, diagnostics, non-safety trend archives | — |

`avionics_diode.md:145`'s shed rule is adopted with it: *a lower-priority telemetry failure must
never delay a higher-priority control computation*, and `:943`'s acceptance test — saturating P3
telemetry must cause no missed P0/P1 deadline — becomes a test vector.

**Queue reserve** (`rcs:519`, `:531`): command flooding must never evict reserved abort and
safe-hold capacity.

---

## 8 · Time, sequence and identity — V-07

- **MET is an integer tick count.** `t += 0.02` in float64 over 34.56 M ticks accumulates and
  destroys exact comparisons ("is this a 1 Hz publish tick"). The specs already use integer-ms
  MET (`eclss:259`, `:269`); follow them, with integer microseconds for sub-tick events.
- **Three times per sample**: physical, sample, publish. Every frame carries `sample_time_ns`
  and `publish_time_ns`; the difference is jitter, and two values in one frame need not describe
  the same instant (`apollo:692-706`). Each point carries `max_decision_age_us`
  (`communcations:265`).
- **Sequence identity is the triple** `(source_id, boot_id, stream_id)` with `seq` increasing by
  exactly one and never silently resetting (C-21, `communcations:236-242`).
- **Frame envelope** is apollo's (`:599-627`) plus `boot_id`, `injected` and a `kind` map beside
  the `quality` map: `schema`, `seq`, `boot_id`, `sim_step`, `met_s`, `state_revision`,
  `vehicle`, `phase`, `values{}`, `quality{}`, `kind{}`.

---

## 9 · Authority — V-08

`S0` above everything (service-owned, unreachable by any command, `eclss:432`, `thermal:39-44`,
`crew:162`) and the agent ladder `A0`–`A3` (`electrical:415-418`, refined by `gnc:345`):

| Level | Scope |
|---|---|
| `S0` | safety kernel: local protection, automatic safing, emergency inhibit. Not delegable, not disableable |
| `A0` | observe: telemetry, diagnostics, acknowledgement. No physical effect |
| `A1` | reversible configuration within an existing mode |
| `A2` | mission-significant execution: arm/commit, isolation, profile activation |
| `A3` | mode changes with vehicle-wide effect |

`min(agent, operator)` holds: an agent may lower its own ceiling and never raise it
(`diode-contract.md:143-144`). The `SET_AGENT_BUDGET_CAP` / `SET_AGENT_CONSTRAINT` pattern
(`consumables:1018`, `gnc:318`) is adopted as ceiling *intersection*; the MPS sibling's version
of it, which specifies constraints but omits the verb, is a defect and not a model
(`main_propulsion_diode.md:933-950`).

---

## 9b · Fault kind — V-09

One union, ten members, and §10 has been promising it since it was written: "**a code not in the
union** — a quality, kind, severity, lifecycle state or priority that is not one of the above".
There *was* no union for `kind` on a fault, so the field was free text and drifted into eleven
values across the 118 entries in `domains/*/fault_policy.yaml`. Nothing read it, which is why
nobody noticed.

| Kind | Meaning | Was |
|---|---|---|
| `discrete` | an element fails to a state and stays there | as written (34) |
| `instrument` | the measurement is wrong while the system may be healthy | as written (26) |
| `continuous_degradation` | a quantity drifts over time | as written (22) |
| `latent_then_acute` | nothing observable until a demand, then hard | as written (13) **+ `latent` (2)** |
| `sustained` | a persistent off-nominal condition that does not drift | **`continuous` (6)** |
| `emergent` | arises from the interaction of otherwise healthy parts | as written (10) |
| `transient` | appears and clears | as written (2) |
| `accounting` | the numbers are wrong and the hardware is fine | as written (1) |
| `procedural` | a process is wrong | as written (1) |
| `environmental` | the environment, not the vehicle | as written (1) |

Two merges and one rename, and each is argued from the data rather than from taste.

**`latent` merges into `latent_then_acute`.** The distinction was never real, and the proof is in
one domain: `PWR-05-bus-tie-stuck-closed` was `latent_then_acute` and `PWR-06-bus-tie-stuck-open`
was `latent` — the same contactor, the same failure class, opposite directions — and PWR-06's own
mechanism text reads "cross-support between buses is unavailable **when it is needed**", which is
the definition of the kind it was not given. `STR-07-relief-valve-stuck-closed` is the same shape.

**`continuous` renames to `sustained`, and the rename is the point.** `continuous` and
`continuous_degradation` look like the same word, and the six entries behind the first are
something else entirely: "the amplifier runs hot", "the link budget closes but thinly", "a feed
branch loses pressure". A hot amplifier does not *drift*; it is a persistent off-nominal condition,
and an agent that read `continuous` as `continuous_degradation` would wait for a trend that never
comes. The pair is also a collision with the plant's own vocabulary — `plant.md` §3's integrator
classes include `continuous`, and a fault kind that means something else under a word the rest of
the folder uses for a state class is exactly the fork §3 exists to prevent.

## 10 · What the linter refuses on vocabulary

`simulator-design.md:141-150` lists what the linter refuses a build for — missing limits,
duplicate IDs, unit mismatches, inverted hysteresis, unresolved dependencies. This vocabulary
adds three more, and they are the ones that catch this corpus:

1. **A code not in the union** — a quality, kind, severity, lifecycle state or priority that is
   not one of the above is a vocabulary fault, reported with the offending domain and the name
   it should have used. **This paragraph was the promise and not the implementation for a long
   time**: `kind` on a fault (§9b) had no union at all and had drifted to eleven values, and
   `severity` — declared 138 times, and the field that decides what a crew actually sees — was
   read by nothing, with the word appearing in the linter only inside comments. Enforcing it found
   one threshold of the 138 with no severity at all. Both are refusals now, and the lesson is in
   the shape of the failure rather than in the values: a rule written down and not implemented is
   indistinguishable from a rule that is satisfied, because nothing is checking either one.
2. **A channel with no canonical name** — every point in `domains/*/points` must resolve to a
   canonical channel, either apollo's verbatim or an explicitly registered addition. An
   unresolved identifier is a fork of the vocabulary, not a new point.
3. **A verb with an implicit gate** — `gate` and `interlocks` are both required fields, and
   `interlocks: none` must be written deliberately (D-03).
4. **A withheld truth that is registered** — every domain's `points.yaml#not_published` names what
   the vehicle refuses to publish, and a name in that list that is also in the channel registry is
   truth on the wire. This is `plant.md` §7's boundary and it is the one invariant the design rests
   on; the section had been written, referenced twice by `presentation.yaml`, and read by nothing.
5. **A failure chain whose clue is withheld** — `points.yaml#not_published` says what the vehicle
   refuses to publish and `coupling.yaml#failure_chains` says what a fleet has to work out; a chain
   whose first published clue is a withheld channel is a chain nobody can start on. Being
   *registered* was the only question asked, and it is not the same claim.
6. **A crew the configuration cannot hold** — `mission.yaml#crew` and
   `vehicle.yaml#configurations` are a personnel model and a hardware model of the same three
   people, and **all five of their fields were read by nothing**. `surface_party` must be the count
   of `goes_to_surface`, `size` must be the largest `crew_aboard`, and `crew_in` must be a prefix
   the *station* vocabulary uses — anchored there rather than to `location_phase_default`, because
   the two would otherwise validate each other and a configuration naming a `cockpit` would agree
   with a mission naming the same.
7. **A conflict domain nothing can be refused in** — `apollo_diode.md:578-579` makes
   `conflict_domain` a runtime policy ("first valid command received wins for that tick", and the
   loser "receive[s] `CONFLICT_SUPERSEDED`"), so a verb declaring one that cannot be expanded is a
   verb whose collisions are undefined.

And one that is not about names at all: **a value that is needed and unset fails the build,
naming what wants it** — `thermal_diode.md:29`'s rule, generalised by
`simulator-design.md:146-150`. `UNCONFIGURED` is a build failure, never a default.
