# 01 — Conflict register

Every place two sources disagree about this vehicle, with one disposition each. `C-` entries
are conflicts in numbers, units, channels or verbs; `D-` entries are decisions taken where the
corpus does not agree with itself and a choice has to be made. `coupling.yaml` cites these by
ID.

Disposition shorthand: **apollo** — apollo wins per the standing rule, and the losing sentence
is quoted so the override is visible rather than silent.

---

## C — conflicts

### C-01 · DC bus band and the low-voltage event

| Source | Says |
|---|---|
| `apollo_diode.md:73` | `power.dc_bus_a_v` nominal **27.0–30.5 V**; event `<26.5` for 0.5 s |
| `electrical_diode.md:251` | `BUS_A/B` "28 V nominal; **24–32 V normal operational envelope**" |
| `electrical_diode.md:337` | `BUS_A.voltage_v` "**25.5/24.5/23.5 V tiers**" |

**apollo.** Consequence, and it is the sharpest one in the corpus: electrical's load-shed
ladder fires `DEGRADED` at `<25.5 V for 200 ms`, i.e. up to **2 V below the point apollo calls
an event**. Adopting the ladder wholesale — which `review-findings.md:188-196` recommends
generalising as *the* hysteresis template — produces a plant whose protective state machine
believes the bus is healthy across a band in which its own telemetry says an event has
occurred. `review-findings.md` #7's stability simulation is sound; its thresholds are not
reusable. **Action: re-derive the ladder inside apollo's band before generalising it.** Until
then this is `UNCONFIGURED` (see `E-BUS-PUMP` in `coupling.yaml`).

### C-02 · Bus current

`apollo_diode.md:75` gives `power.bus_a_current_a` a normal range of **10–120 A**;
`electrical_diode.md:251` rates a bus at **40 A continuous / 80 A for 1 s** and its current
sensor at ±100 A (`:261`). **apollo.** The plant must carry 120 A and the instrument must span
it, which means electrical's converter and sensor sizing are for a different vehicle — a LEO
28 V photovoltaic one, not a fuel-cell CSM.

### C-03 · Where the power comes from

`apollo_diode.md:69` — "three hydrogen/oxygen fuel-cell powerplants", with the **O₂ inventory
shared between ECLSS and the fuel cells**, and `:780-784` calls that "a particularly important
Apollo-specific interaction". `electrical_diode.md:122` abstracts generation away: "PV,
fuel-cell, RTG, external supply require different models → Abstract `GEN_A/B` source
interface."

**apollo.** This is not a detail: the O₂ → fuel cell → bus → ECLSS-pump coupling is the
cornerstone of the `simulator-design.md` §3.9 spike and of apollo's crisis chain. electrical's
abstract source is declined, and the fuel cell becomes a real node with stoichiometry
(`E-O2-FC`, `E-H2-FC`, `E-FC-WATER`, `E-FC-HEAT`).

### C-04 · Cabin pressure

`apollo_diode.md:88` — 4.8–5.2 psia, caution `<4.5`, emergency `<3.5`.
`eclss_diode.md:734` — "**Delete as generic ECLSS default**", on the grounds that current NASA
guidance puts crew-exposed total pressure above 34.5 kPa and the nominal is project-specific.

**apollo, overriding eclss explicitly.** Worth recording the arithmetic eclss does not state:
4.8–5.2 psia is **33.1–35.9 kPa**, and the NASA floor eclss adopts is 34.5 kPa (5.004 psia) —
so roughly the lower third of apollo's band sits below the modern floor. The vehicle keeps
apollo's band because the experiment is Apollo-shaped; the divergence is a real property of the
vehicle and belongs in the run record rather than being silently corrected.

### C-05 · CO₂ limit — not actually a conflict

`apollo_diode.md:90` — `eclss.co2_pp_mmhg` 0–5 normal, **>7.6 mmHg caution**.
`eclss_diode.md:735` — "**Delete as generic CO₂ criterion**"; NASA's nominal is a **one-hour
average** ppCO₂ ≤ 3 mmHg.

**Both, because they are different statistics.** The 7.6 mmHg figure is an *instantaneous alarm
threshold* on the ECS caution light; the 3 mmHg figure is a *one-hour average exposure limit*.
They do not contradict; they must not share a channel. Disposition: `eclss.co2_pp_mmhg` carries
the instantaneous value with its 7.6 mmHg caution; the rolling-window statistic is a separate
derived point with the 3 mmHg limit, and consumables' 15-minute trending window
(`consumables_diode.md:523`) is the natural place for it. This is the one entry here where
reading both documents carefully resolves the conflict instead of choosing a winner.

### C-06 · O₂ supply pressure

`apollo_diode.md:91` — 750–950 psi, event on low pressure or a >5 psi/min fall.
`eclss_diode.md:736` — "**Remove from generic interface**", because stored-gas, cryogenic and
electrolytic sources have different pressure regimes. **apollo**, since this vehicle has
cryogenic tanks. Note that C-04/C-05/C-06 are three separate deletions in one table, and taking
all three is what makes apollo's ECLSS a *vehicle* rather than a schema.

### C-07 · Physics tick

| Source | Says |
|---|---|
| `apollo_diode.md:24`, `:1084` | **50 Hz** physics clock |
| `gnc_diode.md:131`, `:1671` | "Replaced by multirate GNC schedule; **100 Hz** reference inner loop" |
| `rcs_diode.md:23`, `:899` | **100 Hz** control frame |
| `events_diode.md:20`, `:80` | **200 Hz** baseline |

**50 Hz, single-rate, for now.** `gnc_diode.md:1672` concedes the point itself — "Earlier 50 Hz
physics baseline | Not removed | Remains valid for low-dynamic simulation; **not normative for
GNC**" — so this is a considered deferral rather than a contradiction. The design's stated plan
(`simulator-design.md:238-242`) stands: design the seam so rates *can* split, do not build the
machinery until a profiler says to. What must not be deferred is the interface: every domain
declares its natural rate even though the scheduler ignores it today.

### C-08 · Publication and intake rates

`apollo_diode.md:1085-1086` — 10 Hz intake (≤100 ms) and 10 Hz fast telemetry.
`gnc_diode.md:87-88` 20 Hz / ≤50 ms; `rcs_diode.md:25`, `:521-522` 20 Hz; `events_diode.md:24`
20 Hz. **apollo.** One consequence to resolve rather than ignore: `main_propulsion_diode.md:555`
wants a **≤10 ms effect-time snapshot**, which a 20 ms tick cannot produce. Resolve it as a
*sub-tick event record* — the command's own tick index plus an integer-microsecond offset from
the event queue — not as a faster telemetry frame. This is the same mechanism
`review-findings.md` #7 identifies for same-tick comparator collisions: a tie-break, not a
smaller dt.

### C-09 · Navigation publication rate

`apollo_diode.md:119-120` — position and velocity at **2 Hz**, precision 0.01 km / 0.01 m/s.
`gnc_diode.md:439` — 10 Hz. **apollo.** The estimator may run at 100 Hz internally; the agent
sees 2 Hz, and `comm`'s `max_decision_age_us` tells it how old that is.

### C-10 · Chamber pressure channel

`apollo_diode.md:135` — `prop.chamber_pressure_pct`, **percent of nominal**, 95–105 firing,
10 Hz, event `<90`.
`main_propulsion_diode.md:193`, `:667` — **Pa**, 50–100 Hz, ±1 % FS, fault at 0.80.
**apollo's channel**, with the plant carrying Pa internally and publishing the percentage. The
band difference matters: apollo's event at 90 % and mps's fault at 80 % are ten points apart,
and the wider one (apollo's) is the one the agents will act on.

### C-11 · Thrust representation

`apollo_diode.md:136-137` — `thrust_pct_commanded` / `thrust_pct_estimated`, `%`, 10 Hz, event
on a `>5 %` discrepancy.
`main_propulsion_diode.md:195` — `thrust_est` in **newtons**, 50 Hz.
**apollo's two-channel form** — it is the commanded-versus-estimated discrepancy that the
experiment needs, and a single newton-valued channel cannot express it. Carry newtons
internally; publish both percentages.

### C-12 · Cutoff by Δv

`apollo_diode.md:141` — `prop.accumulated_dv_m_s` with a "burn cutoff target / divergence"
event. `main_propulsion_diode.md:645` — cutoff is duration-, plan- or GNC-driven; **there is no
Δv cutoff path and no accumulated-Δv channel**.
**apollo.** This is a genuine gap in mps rather than a conflict: the vehicle must accumulate Δv
and cut off on it, so `mps`'s cutoff logic gains a fourth trigger. Without it, apollo's
`accumulated_dv_m_s` channel has no producer.

### C-13 · Structural fidelity

`apollo_diode.md:753` — Structure at **Medium**: "pressure vessel, leaks, latches,
docking/staging/pyro states; **not finite-element structural mechanics**", with flexible-body
modes explicitly on the simplify list (`:815`). `events_diode.md:222`, `:225` build the
structural domain on `STRUCT_MODE_EXCITATION` ("requires model") and `STRUCT_MODEL_RESIDUAL`.
**apollo.** Decline the modal and spectral classes. The structural domain this vehicle needs is
the one apollo names — hatches, latches, docking, staging, pyro continuity, relief valves — none
of which appears in `events_diode.md` at all (`pyro`, `hatch`, `dock`, `staging`, `jettison`:
zero occurrences each). The one-way-action half of `events` is therefore authored from
`apollo_diode.md:206-213` and `:476-509`, not extracted.

### C-14 · Communications has no specification

`communcations_diode.md` contains no communications subsystem: `snr`, `antenna`, `pointing`,
`carrier` and `S-band` occur zero times, and its own open-parameter register (`:128-160`) is 33
rows of `UNSPECIFIED`. `apollo_diode.md:161-168`, `:786-790` and `:243` supply the channels,
the attitude→pointing→SNR coupling and the verbs.
**apollo**, and the `domains/comms/` five files are authored from it. The diode transport
material in `communcations_diode.md` is not wasted — it produces D-01 and D-02 — but it is a
different document wearing the domain's name.

### C-15 · Actuators and sensors the vehicle does not have

`apollo_diode.md:52`, `:147-153` — attitude is **RCS only**; navigation is IMU, star sighting
and radar. `gnc_diode.md:117`, `:317`, `:557`, `:1001` add reaction wheels, CMGs, magnetorquers
and momentum dump; `:118` adds GNSS; `:528-530` adds LiDAR and terrain-relative navigation;
`:952` adds aerosurfaces.
**apollo.** Prune all of them. This is the clearest case of a spec describing a different
vehicle class, and it is invisible unless you read both.

### C-16 · Propulsion verb authority

`apollo_diode.md:241` — `arm_engine`, `safe_engine`, `load_burn`, `start_burn`, `stop_burn`,
`set_throttle`, lowercase, with `start_burn` firing directly. `main_propulsion_diode.md:293-296`
— `ARM_BURN`/`COMMIT_BURN`/`ABORT_BURN`/`SET_THROTTLE_PROFILE`, with arm-TTL and commit
mandatory for **every** burn, and no nominal early-cutoff verb.

**apollo's verbs, lowercase, with one composition rule lifted from mps.** A burn is
interruptible and `stop_burn` exists, so it does not need arm/commit; a *staging or pyro event*
is not, so it does. Disposition: arm/commit-with-token is required exactly for the verbs whose
effects cannot be undone (`structures`, `arm_event`/`execute_event`), which is also what
`apollo_diode.md:476-509` and `diode-contract.md:167-170` say. mps's blanket requirement is
declined as over-application, and its "no early cutoff" gap is closed by C-12.

### C-17 · Units

apollo publishes imperial: `psia`, `psi`, `mmHg`, `°C`, `ft³/min`. `avionics_diode.md:165`,
`events_diode.md:177`/`:514` and `main_propulsion_diode.md:188-193` use Pa.
**SI internally; apollo's units at the boundary.** The channel name carries the unit
(`cabin_pressure_psia`) so a reader cannot be wrong about which, and the conversion happens once,
in the publisher, not in the plant and not in an agent's head.

### C-18 · Wire format

`apollo_diode.md:592-627` — JSON files, `aurora.capsule.telemetry.v1`, a flat `values{}` map
plus a parallel `quality{}` map. `thermal_diode.md:225` — "deterministic CBOR is a suitable
default… JSON is retained only as a diagnostic/test projection". `communcations_diode.md:29` —
CBOR + CDDL + COSE_Sign1. `events_diode.md:342-378` — Protobuf plus a SQLite event store.
`consumables_diode.md` ships three parallel schema artefacts for one model (JSON Schema, Avro,
Protobuf; 590 lines).

**apollo's JSON, and the filesystem contract.** A CBOR diode would break
`docs/diode-contract.md` §2 outright, and the flat-map-plus-quality-map shape is the one the
agents' brief already describes. The Protobuf schemas are not wasted: they are the most complete
field *lists* in the corpus, and field lists port to a JSON schema by deletion.

### C-19 · The command lifecycle

Six chains: `apollo:453`; `electrical:424`; `thermal:643-679`; `gnc:263-292`; `rcs:402-436`;
`crew:553-567`; `consumables:1145` in CamelCase. The load-bearing disagreement is that
`electrical` makes `REVALIDATED` **terminal** while `eclss`, `gnc`, `rcs` and `thermal` use
`REVALIDATING` as a **transient** state on the single most safety-relevant transition.
**One canonical chain — `02-canonical-vocabulary.md` V-02.** Apollo's, plus the transient
revalidation state the specs correctly insist on and the `INDETERMINATE` terminal that D-01
needs.

### C-20 · Codes, scales and severities

Five quality vocabularies, three alert severities, seven priority scales, two field names
(`severity` vs `priority`) for one concept, and three spellings of "this value is a test
injection" (`TEST` / `SIMULATED` / `TEST_INJECTED`).
**The union, in one dictionary — V-03 through V-05.** The specific casualty to fix first:
`SATURATED` — the code `apollo_diode.md:215` makes load-bearing ("publish `300.0` plus
`quality:"SATURATED"`, never the hidden 750") and `simulator-design.md:504-506` calls the
honesty exception — **does not exist in `crew_diode.md` at all**. The C&W layer we adopt
cannot represent a saturated transducer, so the enum must be the union, not crew's list.

### C-21 · Restart identity

`boot_id` exists in `communcations`, `thermal`, `consumables`, `avionics`, `events` and `crew`;
it is absent from `apollo`, `electrical`, `eclss`, `gnc`, `main_propulsion` and `rcs`. Half the
corpus cannot express a restart, which is what a receiver needs to tell loss from reboot.
**Adopt `communcations_diode.md:236-242`**: `seq` scoped to `(source_id, boot_id, stream_id)`,
increasing by exactly one, never silently reset, with a new `boot_id` on restart.

### C-22 · Mission phase is undefined

`docs/diode-contract.md:147` re-checks "gates, interlocks, allowances and **phase**" at the
moment of effect; `apollo_diode.md:439` carries `allowed_phases` on a registry entry and `:611`
publishes a `phase` string. No document defines the phase set, the transitions, or their
durations — `main_propulsion_diode.md:105` disclaims it and `gnc_diode.md:117` defers it.
**Authored in `../vehicle/mission.yaml`.** The executive's central safety predicate references a
quantity that did not exist until now.

### C-23 · Two worked examples that are wrong

`gnc_diode.md:1175-1177` places the vehicle **14.1 km below the lunar mean radius** (|r| =
1723.3 km; the only concrete trajectory in the corpus). `consumables_diode.md:2033-2048`
publishes a `time_to_critical_ms` of 4,870 s where its own `available_to_new` and
`consumption_rate` imply 8.13 × 10⁶ s — a factor of ~1670.
**Discard both.** `mission.yaml` supplies a real initial state; the linter re-derives forecasts
and fails on a mismatch, so the second class of error cannot recur silently.

### C-24 · The translunar injection that cannot reach the Moon

`mission.yaml#initial_state` recorded three published figures from `A11 Tbl 7-II`: 25,562 ft/s in
the parking orbit, 35,546 ft/s space-fixed after TLI cutoff, over a 346.87 s burn. They are
mutually consistent — the difference is 9,984 ft/s, which is the Δv the budget carried — and
**together they describe a trajectory that does not arrive.**

10,834.4 m/s from a 185 km parking orbit gives a specific energy of −2.0417 km²/s², a semi-major
axis of 97,687 km and an apogee of **188,812 km**. The Moon is at 384,400. And it is not a timing
problem that a longer coast would fix: a minimum-energy Hohmann transfer to the Moon's distance
needs **10,928.2 m/s**, so the published speed is 93.8 m/s *slower than the cheapest trajectory
that arrives at all*. The published burnout speed cannot reach the Moon at any transit time.

**The 73-hour transit wins.** Apollo 11's TLI→LOI was 73 h, `mission.yaml`'s phase ladder prices
73.0 h, and nothing in the vehicle depends on the quoted instant while the entire mission
timeline depends on the duration. The transfer that arrives in 73.0 h from r = 6,563.2 km has
**a = 254,545 km, e = 0.974216, apogee 502,526 km and a cutoff speed of 10,949.8 m/s** — 115.4 m/s
above the published figure. That is a faster-than-Hohmann transfer, which is what a three-day
translunar coast is, and its apogee is well past the Moon's orbit because the vehicle arrives
before apogee.

Three things make this worth recording rather than quietly correcting.

**The error is invisible in the budget.** The published velocities differ by 1.07 % and their
*difference* is dominated by the 7,793 m/s parking-orbit speed they share: the published Δv is
9,984 ft/s and the derived requirement is 9,983 ft/s — the same figure to four digits. So the
number that was wrong travelled through the Δv budget unnoticed, and the number that was wrong
was the one nobody prices.

**The third-body escape hatch does not open.** Solar tidal acceleration at lunar distance is
0.030 mm/s², which over 73 h is 8.0 m/s of Δv — an order of magnitude short of the 115.4 m/s gap.
A reader who suspects the two-body assumption is doing the work will find that it is not.

**The linter can now hold it.** `check_trajectory` re-derives the elements from the parking orbit
and the phase ladder and refuses an initial state whose apogee is short of the Moon, whose
eccentricity disagrees with `1 − r_p/a`, or whose cutoff speed disagrees with vis-viva. The
published figure fails all three, which is the property that makes the disposition checkable
rather than asserted.

**What this does not resolve.** Four of the six orbital elements are now determined: a, e, i and
the cutoff speed. The other two — and the free-return property, which is a constraint on them —
need a **lunar ephemeris at the arrival epoch**, which no document in the corpus contains. The
debt is smaller and it is now precise: not "a patched-conic design", which is a task, but one
datum.

### C-25 · The cabin's water vapour share

The vehicle models a crewed cabin as four conserved gases — oxygen, water vapour, carbon dioxide and
nitrogen — and the water share sets the oxygen's own partial pressure band. Two documents give it,
and they do not agree.

| Source | Says |
|---|---|
| `csm_ecs_study_guide.pdf` **PDF p. 31**, §III Pressure Suit Subsystem | the cooling process removes "the water content of the gas in excess of a **50 F dew point**" — 10 C, and water's saturation vapour pressure there is 1.228 kPa = **9.209 mmHg** |
| `lunar_module_environmental_control_subsystem.pdf` **PDF p. 44**, component 101 Heat Exchanger, performance Condition I ("two cabin fans, condensing") | "Absolute Humidity — lb H2O/lb O2 **0.0276**", at "Pressure O2 in — psia 5.0" — a mole ratio of 0.0490, i.e. **12.09–12.68 mmHg** depending on whether the quoted 5.0 psia is the oxygen's own pressure or the stream total |

**The ECS document, with the disagreement stated.** The corpus carries 9.209 mmHg, and the round that
landed it recorded the reason in the field itself: the 50 F sentence is about the **suit circuit**,
the same ECS runs the same condensing heat exchanger and water separator on the cabin, and applying
the figure to the cabin is an inference rather than a quotation. The Hamilton Standard figure is
measured *at the cabin heat exchanger*, which makes it the better source for the cabin and the worse
one for a vehicle whose two compartments share a single humidity declaration — it is an LM table, and
the CSM's cabin share would still be owed its own.

**Why it was not substituted quietly.** The band `eclss.pp_o2_mmhg` carries — 236.02 to 256.71 mmHg
of oxygen at 4.8–5.2 psia of total pressure — is the total band **less this share**, and so are the
LM's two ppO2 thresholds, the four-gas closure and both channels' ranges. Moving the share moves all
of them: 12.68 mmHg gives a band of roughly 233–253 mmHg and a nominal ppO2 near 243. A change of
that reach belongs to a round that re-derives the closure and the alarms together, and the conflict
is recorded in `domains/eclss/components.yaml:atmosphere_model.check.partial_pressure_provenance`
so that a reader of the number finds the disagreement rather than a page that does not say it.

**Resolved: the ECS document, one share for both cabins.** Put to the operator, who chose to fly
the CSM's 9.209 mmHg in both compartments rather than split the declaration or move to the LM's
figure. The reasons the decision rests on, recorded so a later round does not re-open it by
accident: the 9.209 is already the number every dependent declaration was derived from — the
`eclss.pp_o2_mmhg` band, the LM's two ppO2 thresholds, the four-gas closure and both channels'
ranges — so splitting it would re-derive six declarations to sharpen one; the Hamilton Standard
figure is an **LM** table at an LM heat exchanger, so applying it to the CSM would be the same kind
of cross-application the corpus already declines in the other direction; and the disagreement is
3–3.5 mmHg on a share whose own `partial_pressure_provenance` states that the 50 °F sentence is
about the suit circuit. **The inference is the disposition**, and the field says so. What a later
round may still do is give the LM its own share, which is a modelling change rather than a
correction to this one.

### C-26 · The RCS engine's specific impulse

| Source | Says |
|---|---|
| `lm_propulsion_rcs_study_guide.pdf` **PDF p. 90**, RCS engine specification table | "Specific impulse **275 seconds (approx)**"; "Flow rate — oxidizer **0.24** pounds/sec", "Flow rate — fuel **0.12** pounds/sec" |
| the same table, read as a flow rate | 0.36 lb/s = **0.1633 kg/s** at 100 lbf, which is an Isp of **277.9 s** — the guide corroborates itself against the corpus |
| `domains/rcs/components.yaml:thruster` | `thrust_n: 445`, `isp_s: **290**` |
| the same declaration's own relation | `mass_flow_per_thruster` = 445 / (290 x 9.80665) = **0.15647 kg/s**, which is 4.3 % below the guide's flow rate |

**Resolved: the guide's figure, at 277.8 s.** Put to the operator, who chose the published and
self-corroborating pair over the corpus's unsourced 290 s. The two numbers on p. 90 agree with each
other — 275 s (approx) and 0.36 lb/s at 100 lbf give 277.78 s — and the figure landed is **277.8**,
the reading where both are reproduced: `mass_flow_per_thruster` becomes 0.163345 kg/s, **0.03 %** from
the page's measured 0.163293, where 275 s would be 0.5 % away. What moved, together and in one
round: `vehicle.yaml#propulsion.rcs_sm/rcs_cm/rcs_lm.isp_s` (290 → 277.8), the article
`components.thruster_100lbf.isp_s` (the same 100 lbf hardware), `capability.mass_flow_per_thruster`
(0.15647 → 0.16335), the three `capability.impulse_capacity` values (1,729,109 / 318,520 / 819,051 →
**1,656,367 / 305,120 / 784,595**: the same tanks price **4.2 % less** total impulse),
`E-RCSP-RCS`'s sensitivity (0.0003516262803 → 0.0003670685) and the consumables ledger's
`rcs_firings` rate and minimum flow (0.1565 → 0.16335 kg/s). **The direction matters and is the
reason this was a decision rather than a repair**: the RCS load is one of the mission's tighter
ones, and it now spends 4.3 % faster.



---

### C-27 · The suit circuit's flow, and a recommended range that excludes it

| Source | Says |
|---|---|
| `csm_ecs_study_guide.pdf` **PDF p. 39** (printed p. 3-9), §III, the suit compressor | "In normal space operations, the operating compressor delivers approximately **35 cubic feet per minute** of suit gas at a pressure rise of 10 inches of water within the conditions of 4.93 psia and 80 F. Under emergency operating conditions, the operating compressor delivers approximately **34.5 cubic feet per minute** suit gas at a pressure rise of 6.9 inches of water" |
| `lm_ecs.txt`, the LM's suit circuit (a different circuit, and per suit) | "half of the **12 CFM** suit circuit oxygen flow will pass directly into the body of the SSA at the waist and half of the flow will pass into the helmet" |
| `apollo_diode.md:92` | `eclss.suit_loop_flow_cfm`, `ft³/min`, recommended range **27–33 `Sim`**, precision 0.5, 1 Hz, event `<20` |
| `domains/eclss/components.yaml:state suit_loop_flow_cfm` (before this round) | `initial: UNCONFIGURED` — the starting flow was owed, and the note said `apollo_diode.md:92` publishes *the band* rather than a starting value |

**Resolved: the recommendation moved, not the figure.** The 27–33 range carried the `Sim` marker —
"recommended nominal / expected range", the table's own words — and no source: it is the simulator
designer's judgement, while the compressor's delivery is a published figure for the same circuit. A
band whose centre is 30 sits 5 cfm *below* what the document says the circuit delivers, so a healthy
suit loop would read at the top of its own band and a fleet would be told to look at it. The
disposition is therefore: **`initial: 35`**, `historical`, with the page in the field; and the band
**re-anchored at 32–38** — the published design point as the centre, and the recommendation's own
half-width of 3 retained, because the width is a judgement about normal variation and the centre is
now a citation. Both published points (35 normal, 34.5 emergency) sit inside it, and apollo's `<20`
event is far below either.

**What the round could not settle, and did not assume.** The LM's 12 cfm is a *per-suit* flow in the
LM's own circuit, and `eclss.suit_loop_flow_cfm` is the CSM's; nothing in the corpus gives the CSM
circuit's per-suit split, so no attempt was made to reconcile the two numbers. Whether the CSM's
suit circuit should have its own published *indication* band (rather than a design point with a
chosen width) is open, and a CSM suit-circuit flow indication in the Apollo Operations Handbook or
the ECS specification would close it.

### C-28 · The coolant's return, and a band that put a healthy loop over its own warning

| Source | Says |
|---|---|
| `apollo_diode.md:102` | `thermal.coolant_return_c`, °C, recommended range **5–15 `Sim`**, precision 0.1, 2 Hz, event **>20** |
| `csm_ecs_study_guide.pdf` **PDF p. 74** | the glycol temperature-control valve: "if the temperature is less than 45 F the glycol temp control valve will … to mix with **the returning cold glycol** to obtain 45 F at the inlet to the evaporator"; also "**167 LBS/HR**. 45 F water-glycol entering the heat exchanger assembly", and the evaporator's outlet "maintained at 46 F" |
| `vehicle.yaml#thermal.loops.loop_primary` (before this round) | `supply_c: 7.2`, `return_c: [5, 15]`, `evaporator_outlet_c: [2.8, 7.2]`, `radiator_inlet_c: [22.8, 23.9]`, `evaporator_actuation_c: 9.4` |
| `domains/thermal/points.yaml` (before this round) | `thermal.coolant_return_c`'s derivation: *"the loop temperature after the coldplates, before the radiator"*; `thermal.radiator_inlet_c`'s: *"the loop temperature entering the radiator"* |

**Resolved: the prose was wrong about which station the return is, and no figure changed.** The two
rows name one station — the line leaving the coldplates — while the bands they are held to are
sixteen kelvin apart: the return's `[5, 15]` with a `>20` warning, and the published radiator inlet's
`[22.8, 23.9]`. If they were one station, a healthy vehicle in lunar orbit would trip
`coolant_return_high` on every pass, and the alarm would be the corpus's own. The study guide's
sentence says which sense of "return" the vehicle uses: the returning **cold** glycol, mixed up to
45 F at the evaporator inlet — the line coming back *through the radiator*, not the one leaving the
coldplates. So the loop field is renamed `radiator_outlet_c` (band unchanged), the two channel
descriptions name their stations, the heat load is `radiator_inlet − supply` rather than
`return − supply`, and `check_thermal_bindings` refuses the three shapes that let the two names
collapse: a post-load band starting below the loop's own supply, a radiator outlet warmer than the
radiator inlet, and a loop carrying both `return_c` and a named radiator station.

**What the round could not settle, and did not assume.** Three things, each with the page that would
close it. (1) The loop's heat balance is still owed — a `specific_heat_j_per_kg_k` (the corpus's
relation says "about 3,600", a mass-fraction average of 62.5/37.5 glycol-water gives ≈3.08 × 10³,
and neither is a document) and a state holding the loop's collected load; the `Sim` band was
therefore left exactly as the diode publishes it. (2) **resolved, and by the document the corpus already cited.** TN D-6718 (the Apollo experience
report the corpus takes its 200 lb/hr and 73–75 °F inlet from; **PDF p. 11**) reads: *"The coolant
system consists of a primary loop, which is operated continuously, and a secondary loop, which serves
as a backup system. The primary loop uses a centrifugal pump to circulate **200 lb/hr** of coolant
(ethylene glycol and water)"*; the flow leaving the evaporator *"is divided into a **35-lb/hr** flow
directed to the inertial measurement unit (IMU) … and a **165-lb/hr** flow is routed to the suit heat
exchanger"*; the two rejoin and *"the 200-lb/hr flow is directed through a series-parallel arrangement
of 22 coldplates"*. So the study guide's **167 lb/hr is that 165-lb/hr suit-and-cabin branch of the
same loop**, not a second circuit, and the secondary loop is a **backup** — *"may be operated at the
discretion of the crewmembers … does not have cabin-heating capability, nor does it provide cooling to
the guidance and navigation equipment"*. The corpus says so now: every loop declares a `role`, a
`backup` may not be named by a zone's `cooled_by` (selection is `set_coolant_loop`'s mode), and a
`primary` with no zone naming it is refused. (3) The study guide's "46 F as sensed at the outlet of the evaporator" is 0.6 K above
the top of the corpus's `evaporator_outlet_c: [2.8, 7.2]`, which is TN D-6718's 37–45 F range — a
deadband or a second source, and the AOH SECS schematic is what would say which.

### C-29 · The loop's heat load: the electrical demand against the rejection requirement

| Source | Says |
|---|---|
| `domains/power/components.yaml#load_budget` and the zone heat rates summed in round 41 | the CSM's demand is **1,723 W** — `loop_primary_load_w`, the sum over the zones that name the loop |
| TN D-6718 **PDF p. 17** | the Blk I radiator's "3700-Btu/hr capability as compared to the **4850-Btu/hr requirement** for an average earth-orbital environment" = **1,421.4 W** |
| TN D-6718 **PDF p. 11** and NR | the loop's published flow (200 lb/hr) and its rise (45 °F mixed supply to the 73–75 °F radiator inlet, 28 °F = 15.5556 K) |

**Recorded rather than reconciled, and the arithmetic is why.** `Q = m_dot * c_p * dT` is exact. Over
the document's own flow and rise, the 4,850 Btu/hr requirement gives `c_p` = **3,626 J/kg·K** — inside
the range a 62.5/37.5 glycol-water mixture can have, and 0.7 % from the "about 3,600" the corpus
carried as prose — while the 1,723 W electrical demand gives **4,394 J/kg·K**, above water's 4,182 and
impossible for any aqueous glycol mixture. So the loop's *thermal* load is not the zones' electrical
demand, and the 302 W between the two is real: some electrical energy leaves the vehicle without
becoming heat in a compartment (the S-band amplifier's radiated power, light through the windows), and
the 4,850 Btu/hr requirement is an average rather than a peak.

**The consequence is a reading, not an error.** With `c_p` = 3,626.1, the loop's inlet is
`7.2 + 1,723 / (0.0252 x 3,626.1)` = **26.06 °C** at MET 0, above the loop's declared
`radiator_inlet_c: [22.8, 23.9]` design band and below the channel's own 35 °C caution. The band is
the design point at which the radiator carries the requirement alone; a vehicle at its full electrical
demand makes the **evaporator** take the difference, which is what `thermal.evaporator_rejection_w`
(2,345 W) and the `water_cooling` budget are for.

**What would settle it** is a coolant heat-fraction per load — how much of each load's electrical
input becomes heat in its compartment rather than leaving as RF or light — or a peak-load figure for
the lunar mission to set against the earth-orbital average. Neither is in any document read so far;
both are named here rather than assumed, and `loop_primary_load_w` keeps its meaning (the zones'
demand) with the gap recorded instead of absorbed.

---

## D — decisions

### D-01 · Take the durable acceptance ledger; decline the mounts and the cryptography

`communcations_diode.md:102` welds two arguments together. The mount split, per-object
signatures and anti-replay are the inapplicable transport-security layer. But it also attacks
the **crash semantics** of destructive intake — "whose destructive rewrite requires the receiver
to write into the sender-owned channel" — and that argument survives the filter, because
`docs/diode-contract.md:67-72` accepts exactly the consequence: *"A crash mid-batch loses the
rest of that batch; it never replays it."*

A batch claimed and then lost produces **no result file at all**, so an agent cannot distinguish
"lost" from "still pending" — a hole in the contract's own rule that "a refusal is a result"
(`:101`). Remedy, at the cost of one file and no crypto: the vehicle keeps a **private durable
acceptance ledger** keyed by command text; an entry left `EXECUTING` across a restart is
`INDETERMINATE` and is never auto-replayed (`communcations_diode.md:412`, `:597`). The console
file stays agent-owned and destructive; the ledger is the vehicle's own memory of what it
claimed. This is a change to the *vehicle's* side of the contract and requires nothing from the
contract itself.

### D-02 · Keep `output/<result>.txt`; add a structured block inside it

`communcations_diode.md:118` demotes the result file: "`output/*.txt` is no longer the
authoritative command result." For ten LLM agents a file whose *name* carries the command and
whose body is prose is a better surface than a status object, and the contract already fixes it
(`diode-contract.md:83-96`). Take the machine-readable argument without the demotion: append a
fenced JSON block — correlation id, lifecycle state, effect tick, refusal reason — to the
existing body. `diode-contract.md:253-258` already declares the filename forward-compatible
with exactly this.

### D-03 · Interlocks are service-owned; gates are preferences; the vehicle must say which

`eclss_diode.md:741` — "Safety interlocks become exclusively service-owned state… Agent-writable
variables are inappropriate as life-protection gates." `thermal_diode.md:823-826` generalises
it: ordinary agents select *versioned pre-certified profiles*, never threshold values, because
"the model that reasons about the spacecraft must not also be able to rewrite the limits by which
its reasoning is constrained."

`diode-contract.md` §3 already concedes this for physical verbs (`variables` "is not where
interlocks live"). What is missing is a *declaration*: every verb's registry entry must say
whether its gate is an agent-writable preference or a service-owned interlock. Without that
field, `contract/diode_probe.py` checks 5 and 8 will certify a design the corpus forbids, because
they cannot tell the two apart.

### D-04 · Decline the claims lifecycle *and* strip its fields

`simulator-design.md:254-257` declines consumables' claims lifecycle because "exposing
reservations as verbs hands the fleet a ready-made deconfliction primitive… The vehicle may use
claims internally; it must not publish them." The reasoning is right and the scope is wrong:
`RESERVE_RESOURCE`, `RELEASE_RESERVATION`, `REQUEST_ALLOCATION` and `RELEASE_ALLOCATION` are
agent-facing verbs (`consumables_diode.md:1008-1011`), **and** `reserved`, `allocated`,
`committed` and `available_to_new` are *required* fields of the schema being adopted
(`:1568-1575`). `available_to_new` is precisely the aggregate other agents' claims leave behind,
so publishing it hands over the primitive the design means to withhold. Declining claims means
editing the schema and dropping four verbs — not declining a feature.

### D-05 · The read-only profile store

Implement `thermal_diode.md:823-826` as a mechanism, not a convention: thresholds, limits,
hysteresis bands and dwells live in versioned profile objects that agents can *select* and the
executive enforces. An agent that could write a limit could widen its own envelope, and
`SIMULATED`/`TEST` modes make that failure look like a physics result.

### D-06 · The crew display contract must be authored

`simulator-design.md:561-564` claims `crew_diode.md` supplies "which panel shows what, in which
module". It does not: `crew_diode.md:42` says display topology "was not supplied" and "remains
configuration item"; `module` occurs zero times in the file and `panel` once, as a widget name
(`:367`); `:352-370` is a list of display *widget types* with source signals and rates.

This matters more than a documentation error, because the crew are the vehicle's most valuable
and least checkable sensor. `review-findings.md` #4 requires the perception bound to be computed
as `(full_truth, crew_position, display_contract) → perceivable_subset` **before** the GM
composes, so that excluded truth never enters its context window. That third argument now has to
be written: per module, which readouts exist, at what precision, and therefore what a crew member
standing there could honestly report. Until it exists, `ask_crew` cannot be safely enabled.

### D-07 · Decide what crew dialogue is a channel *to*

`brief/PROTOCOL.md:115-118` tells agents the window "is not a channel to another agent". With
`ask_crew` in the vocabulary (`simulator-design.md:388-406`) that needs to be either true by
construction or explicitly untrue. **Per-console dialogue** keeps it true and makes the crew a
private sensor. **Shared dialogue** makes the crew a broadcast surface ten agents can write prose
into and read back — a world-supplied message bus, which `design.md` §8 refuses to supply, and
which the `perceivable_subset` bound does not cover because it bounds what the crew may *perceive*,
not what they may *repeat*. Recommendation: per console, with the crew's own knowledge of an
exchange being part of the vehicle state. This is John's call and is carried as an open question.

### D-08 · Small adoptions that cost nothing and close real holes

| From | Take | Why |
|---|---|---|
| `communcations_diode.md:236-242` | `seq` + `boot_id` + `stream_id` | half the corpus cannot express a restart (C-21) |
| `communcations_diode.md:265` | per-point `max_decision_age_us` | makes "stale evidence" enforceable rather than prose |
| `events_diode.md:192-211` | `detection_latency_ns`, `rule_hash`, typed `links` | gives the metric ladder its timestamps (`apollo_diode.md:934-945`) |
| `events_diode.md:1005-1013` | timestamp freeze/jump, sequence duplication/gap | three fault modes apollo's eleven lack |
| `thermal_diode.md:774` | min/max credible-sensor voting | averaging must not hide an extreme; minimum sensor for cold protection, maximum for hot |
| `thermal_diode.md:346`, `main_propulsion_diode.md:887` | a mean must never erase an excursion | decimation must carry min/max and event overlap |
| `avionics_diode.md:190` | `age_limit_ms` per point | pairs with the stale-precondition rule |
| `events_diode.md:63` | stale data must not satisfy a safety precondition | absence of evidence never satisfies a clear predicate |
| `main_propulsion_diode.md:695-702` | evidence-counting leak FSM | corroboration before condemnation, matching `apollo_diode.md:333` |
| `avionics_diode.md:176`, `:192` | edge-triggered **and** reconciled discretes; dual source/monotonic clocks | a lost edge must not leave a consumer permanently wrong; a clock jump must not expire a dwell |

Each of these is cheap, none is a design change, and every one of them closes a hole that would
otherwise be discovered as a confusing run.

### D-09 · The plant: method split by model form, fidelity closure at the crisis point

No document names an integrator — `RK4`, `Verlet`, `Runge`, `Euler` and `symplectic` occur zero
times across the corpus — so the method is a decision, not an extraction. Adopt
`review-findings.md` §5's split by **model form** rather than by rate: algebraic nodal solve for
the electrical network, exponential-map first-order lags for thermal and actuator states, exact
fixed-point stocks with a residual accumulator, semi-implicit or Verlet 6-DOF with RK4 in burns,
a sub-tick integer-microsecond event queue for latched discretes, and cumulative-hazard draws
for stochastic failures. Two constraints carry over from that review and are non-negotiable
because they were verified numerically: **forward Euler on 6-DOF accumulates ~1 % semi-major-axis
error over eight days**, and **a fixed-point stock with quantum `q` cannot represent a flow below
`q/dt`** — the dead zone that would silently delete a slow O₂ leak, which is the phenomenon the
ledger-versus-observation pair exists to reveal.

### D-10 · What the GM may touch

`simulator-design.md` §6: the GM acts on **truth** and on **dialogue**, never on the published
mirror. It can break a pump and it can have someone mention a noise; it cannot write a telemetry
value. The moment the GM can edit published evidence, no inference from evidence is reliable and
the epistemic structure is decorative. Disposition changes (default / white team / adversarial)
are recorded in the run record, so any finding can be conditioned on operator intervention.

---

## Where a source was read correctly

For balance, and so the next pass does not re-litigate them. `simulator-design.md` §3.7's
ledger-versus-observation pair is an accurate reading of `consumables_diode.md:55-65`; the
decline of `Quantity{mantissa, exponent10, unit_code}` as an *accumulation* format is correct
(`review-findings.md:42-58`); §8's four alert levels, alert lifecycle, stale-data rules and
advisory-only outputs all verify verbatim against `crew_diode.md:31`, `:382-387`, `:439-445`,
`:38`, `:273`, `:470-474`; and every hard citation in `review-findings.md` checked against its
source during this pass was accurate.
