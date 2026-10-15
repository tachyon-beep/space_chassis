# WP02 evidence: thermal, ECLSS and consumables

Research record for the thermal, ECLSS and consumables questions in
`docs/vehicle-completion/02-remaining-work.md` §M2 WP02. It is written to the standard in
[`../evidence.md`](../evidence.md). The target is the bounded quiet-coast power and cooling
episode: CSM coast, no faults. This file records searches and findings. The values themselves
live in their canonical YAML homes, and this file names those homes.

Round: 2026-10-15. Baseline before the round: `check_vehicle.py` reported 270 declared debts, and
`plant.py --readiness` reported 108/139 states configured and 192 UNCONFIGURED scalars. After the
round: 268 debts and 190 scalars, because one value was filled. That value has two debt lines,
`cfm` and `provenance.basis`.

The modelled vehicle is the Apollo 11 composite (CSM-107, LM-5). "Block II" below means the
Block II CSM, which covers every crewed CSM from Apollo 7 on. A "J-mission" document describes
Apollo 15-17 (CSM-112 and later). Those vehicles carry a third O2 and H2 tank and differ in other
ways. A J-mission source is therefore context for this vehicle unless the entry says why it
applies.

## Sources reached

| id | document | reached as | used for |
|---|---|---|---|
| D6718 | NASA TN D-6718, *Apollo Experience Report: CSM Environmental Control System*, Samonski & Tucker, March 1972 | https://ntrs.nasa.gov/api/citations/19720012252/downloads/19720012252.pdf | cabin fans (p. 14), CM leak spec (p. 4), radiator history (pp. 17, 23), cyclic accumulator (p. 10), ECS power table (p. 3) |
| SP368 | Brady et al., "Apollo CSM and LM Environmental Control Systems", *Biomedical Results of Apollo* (NASA SP-368) ch. 5 | https://ntrs.nasa.gov/api/citations/19760005606/downloads/19760005606.pdf | O2 allowance and flight use (pp. 520-522), LiOH spec (pp. 521-522), Apollo 15 water balance (p. 523), translunar heat load (p. 525), LM leak (p. 537) |
| WP1321 | Program Apollo Working Paper 1321, *Two-Gas Environmental Control for the Apollo CM*, W. E. Ellis, 12 July 1967 | https://ntrs.nasa.gov/api/citations/19700025125/downloads/19700025125.pdf | CM leak spec (p. 3), suit-circuit latent load (p. 7 Table III), fan power (p. 10 Table IV) |
| JEPS | *J Mission Electrical Power System*, training document, October 1971 | https://www.ibiblio.org/apollo/Documents/J%20Mission%20Electrical%20Power%20System%20Oct%201971.pdf | reactant/water per ampere (p. 2.6-21), cryo tank pressures and heaters (pp. 2.6-6 to 2.6-16) |
| MSC04312 | *MSC Cryogenics Symposium Papers*, MSC-04312, May 1971 (Bouman; Forester) | https://ntrs.nasa.gov/api/citations/19720016135/downloads/19720016135.pdf (Bouman alone: …/19720016136/…) | O2 pressure switch band, transducer accuracy (Bouman p. 2), pressurisation strokes (Forester p. 65) |
| AOH27 | SM2A-03 Block II Vol. 1 §2.7 ECS (basic 15 April 1969, changes to 15 October 1969) | https://www.ibiblio.org/apollo/ApolloProjectOnline/Documents/SMA2A-03-BLOCK%20II%20Volume%201%2019691015/aoh-v1-2-07-ecs.pdf | flows, regulator settings (pp. 2.7-4 to 2.7-24). The design-data tables (pp. 2.7-24 to 2.7-34) are illegible in the scan |
| NR-ECS | CSM News Reference, ECS section | https://www.nasa.gov/wp-content/uploads/static/history/alsj/CSM14_Environmental_Control_Subsystem_pp117-136.pdf | fans, pumps and radiators (pp. 119-122) |

Reached and empty for these questions: the Apollo 11 Mission Report PDFs at nasa.gov
(`a11mr_NoMissingPages_19700008096.pdf`, `apollo50th/pdf/A11_MissionReport.pdf`). Their text layer
stops in section 4 or 5, and section 8 (CSM performance) is image-only to the fetch tool. The same
holds for the Apollo 16 Mission Report (`tothemoon.im-ldi.com`) past section 5. SM2A-03
`SM2A-03-BK-II-(1).pdf` at nasa.gov has a table of contents and no body text. `aoh_csm-014_vol1.pdf`
at ibiblio did not fetch. NASA CR-102883 (MDA thermal model) treats the CSM as boundary nodes
only. NASA 19730010156 (Carson) covers the PLSS pump, not the CSM glycol pump.

The frozen corpus offers context only. `thermal_diode.md:7` and `:965` declare every thermal
constant UNSPECIFIED and refuse to infer them. `consumables_diode.md:140-157` and `:852` declare the
platform, the thresholds and the reconciliation tolerance UNSPECIFIED. `eclss_diode.md:734-735`
deletes the Apollo pressure and CO2 values as generic defaults. `apollo_diode.md:84`, `:88`, `:91`
and `:97` give the cabin at 5 psia and 70-75 F, the 750-950 psi O2 supply indication, two glycol
loops, 37-45 F out of the evaporator and about 24 gal/h. The YAML already carries all of them.

## Resolved

### E1 — CSM cabin fan flow (`domains/eclss/components.yaml` `ventilation_fan.cfm`)

- **Question:** what volumetric flow does the CM cabin fan move?
- **Value:** **86 ft³/min per fan at 5 psia**, two fans (`fans_installed: 2`). Basis `historical`.
- **Source:** D6718 printed p. 14, "Environmental Control System Description": "Each fan has a
  capacity of 86 cu ft/min at 5 psia".
- **Effectivity:** Block II CSM. The report was written after the Block II flights. No
  CSM-107-specific rating was found.
- **Bounds:** 86 is a capacity at 5 psia. The fan curve is not published, so the delivered flow
  across 4.8-5.2 psia is not bounded more tightly than "about 86".
- **Rejected:** AOH27 p. 2.7-4, 150/100 cfm. That is the post-landing ventilation fan.
  NR-ECS p. 119 says "dual fans" and gives no flow. WP1321 p. 10 gives the blowers' 76 W of
  power, which is context only.
- **Consumer:** the ventilation state. Its rule is owed in WP06.
- **Validation case for the rule:** two fans on move 172 cfm, so the 208 ft³ (5.9 m³) cabin turns
  over in about 1.2 min. With one fan the turnover takes about 2.4 min. A fan commanded off moves
  nothing.
- **Found while filling it:** ECL-07 in `domains/eclss/fault_policy.yaml` binds `ventilation_fan` but
  describes the suit-circuit fan, with the suit compressor's 85 W. The fault and the component name
  different machines. This is recorded and not fixed here.

## Validated (value unchanged, a second source agrees)

### C1 — fuel-cell reactant draw and water production per ampere-hour

- **Question:** O2, H2 and water mass per ampere-hour of fuel-cell output.
- **Model:** `coupling.yaml` `E-FC-DRAW-O2` = 8.8619e-8 kg/J and `E-FC-DRAW-H2` = 1.1166e-8 kg/J
  (from the Mission E consumables analysis), and `E-FC-WATER` = 1.126 kg water per kg O2.
- **Second source:** JEPS p. 2.6-21, "Reactant Consumption and Water Production": O2 = 2.04e-2·I,
  H2 = 2.57e-3·I and H2O = 2.297e-2·I lb/hr, or 10.42 cc per ampere-hour.
- **Check:** at the rated 29 V the model gives 0.020397 lb O2, 0.0025700 lb H2 and 0.022967 lb water
  per ampere-hour. All three agree to 0.01 %. The cross-check is recorded in
  `domains/consumables/components.yaml` under `consumers.fuel_cell_o2.provenance.cross_check`.
- **Effectivity:** the J-mission document describes the same Block II powerplant design. Its
  three-tank capacities are not used.
- **Validation case for the WP04/WP06 rule:** 25 A for 1 h draws 0.510 lb O2 and 0.0643 lb H2 and
  makes 0.574 lb of water. The rule has to be per ampere, not per watt at an assumed voltage.

### C2 — cryogenic tank quantities (`vehicle.yaml` `consumables.csm.o2_kg` and `h2_kg`)

The A11 loads are already declared from the mission report: 615.0 lb O2 = 279 kg, and
54.1 lb H2 = 24.5 kg. Bouman (MSC04312 p. 1) gives the basic two-tank system as "320 pounds of
oxygen per tank, and 28 pounds of hydrogen per tank" of useful stored consumables. Both loads sit
below two tanks' capacity (640 lb and 56 lb), which is consistent. Values unchanged.

## Bounded, value unchanged

### E3 — CSM cabin leak (`vehicle.yaml` `consumables.leak.csm_kg_per_h` = 0.023, borrowed from the LM)

- **Specification bound:** D6718 p. 4 gives "0.2-lb/hr maximum external leakage", and WP1321
  p. 3 gives 0.2 lb/hr at 5 psia. That puts the value in **(0, 0.0907] kg/h**. SP368 p. 520 gives
  an allowance of 4.8 lb/day, the same figure, and says flown use was lower "primarily because of
  lower cabin leakage".
- **Flight figure found:** SP368 Table 2, p. 522, Apollo 15 (12.3 days). The OCR prints seven values
  for eight rows. Read in source order, with the "one CM puncture" row empty, the values sum to the
  table's 108.9 lb total. That reading puts cabin leakage at **5.9 lb = 2.68 kg, i.e. 0.0091 kg/h**.
  It is an inference from the layout and a J-mission CM, so it is context only.
- **LM:** SP368 p. 537 gives 14-23 g/h over Apollo 11-17. `lm_kg_per_h` (22.7 g/h, the A11
  figure) sits at the top of that range, which corroborates it.
- **Validation case:** with no other draws, the CM's O2 makeup should hold 5.0 ± 0.2 psia at a
  regulator flow equal to leak plus metabolic use. SP368 Table 1 gives A11's whole-mission ECS O2
  as 82 lb over 8 d 3 h, about 0.42 lb/h. Metabolic use, leak, purges and repressurisation must all
  fit inside it. The model's crew-plus-leak supply is 0.30 lb/h.
- **Question for John (E3):** keep the borrowed 0.023 kg/h (inside the spec bound) or adopt the
  Apollo 15 reading (0.0091 kg/h). Both are approximations of a CSM-107 figure that was not found.
  The Apollo 11 Mission Report §8.9 (p. 8-23) probably carries it, but it was unreadable to the
  fetch tool. A text copy of that page would close the question.

## Still UNCONFIGURED

Each entry names its options, following `docs/vehicle-completion/08-risks.md`: (a) accept a
declared approximation with basis `chosen` and a stated bound, (b) narrow the objective, or (c)
leave the state out of V's scope.

### T1 — thermal node aggregation (WP06; it blocks the quiet-coast thermal closure)

Owed: `thermal.zone_csm_service_t` (`initial`, `lumped_mass_kg`), `zone_lm_descent_t` (`initial`,
`lumped_mass_kg`), `zone_csm_avionics_t.initial`, `comm_amp_t.initial`, and the sensitivities on
`E-STRUCT-PLATE`, `E-BAY-HEAT-CSM`, `E-BAY-HEAT-LM` and `E-PUMP-COOL`.

- **Searched:** D6718, SP368, AOH27, NR-ECS, CR-102883, the A11 and A16 mission reports (sections
  8 and 6 not readable), and searches for a CSM thermal math model on NTRS. No source reached gives
  a node capacity, a conductance, or a MET-0 bay, coldplate or amplifier temperature for any CSM.
  The best lead is still `TIR 580-S-7159`, *Apollo Service Module Thermal Model Handbook (Block
  2)*, 5 October 1967. Only its catalogue entry is known (`source_audit` in the YAML).
- **What is evidenced in aggregate, and only in aggregate:** SP368 p. 525 says that in the
  translunar and transearth coasts under PTC the CSM's heat load and rejection "ranged between 1170
  and 1470 watts (4000 and 5000 Btu/hr)", and the radiator outlet "seldom exceeded 283°K (50°F)".
  D6718 p. 23 gives Apollo 8 lunar-orbit radiator outlet between about 18 F and 65 F. D6718
  p. 17 says pin-fin coldplates were redesigned from 1.0 to 3.0 W/in² average dissipation. These
  numbers constrain the loop as a whole. They are not node masses or conductances. A lumped mass
  inferred from them would be a choice.
- **Validation finding (not a fix):** the model's CSM loop load is 1,723 W
  (`loop_primary_load_w`), which is 17-47 % above the 1,170-1,470 W flown in coast. The
  radiator's 322 K equilibrium surface temperature (`radiator_eq_t`) is computed for the
  bad-attitude solar load of 2,477 W, not for PTC. A quiet-coast episode at MET 0 in this environment starts in a hotter regime
  than flight. The power worker was told about the load difference; the pump loads (250 W each)
  look large against D6718 Table II, whose OCR columns cannot be aligned.
- **Question for John (T1):** for the quiet-coast episode, choose one.
  (a) Chosen lumps: declare the service-bay and coldplate masses as `chosen`, bounded by the
  aggregate above. The coast heat balance must then reproduce 1,170-1,470 W of rejection with
  the outlet ≤ 283 K, and that becomes the acceptance case.
  (b) Narrow: the episode uses only the cabin and the loop, whose constants are derived. The
  service bay, avionics plate and amplifier are held at their equilibria and dropped from the
  objective.
  (c) Out of scope: remove the bays from V until TIR 580-S-7159 or an equivalent is read.

### T2 — glycol pump rated speed (`thermal.pump_1_speed_rpm` `initial` and `command_value.on`, `E-CMD-PUMP`)

- **Searched:** D6718 pp. 3 and 11, AOH27 pp. 2.7-17 to 2.7-24, and NR-ECS p. 122 ("three
  centrifugal-type pumps" in one housing). None gives an rpm or a pump curve. AOH27's design-data
  table is illegible in the scan.
- **Question for John (T2):** (a) model the pump's state as a fraction of the published 200 lb/hr
  flow (on = 1, off = 0) and drop rpm. This is a model change, not a value. (b) Choose an rpm with
  a stated bound. (c) Keep it unset and leave pump speed out of the episode.

### T3 — radiator environment (`radiator_model.csm.absorbed_environment_w`, `environment.lunar_ir_w_m2`, `environment.albedo_load_w`)

These are lunar-orbit terms. The quiet-coast episode is a translunar coast, where they are zero to
first order. They were not researched this round. They are out of scope for the episode, not
for V.

### E2 — O2 supply line time constant (`eclss.o2_supply_pressure_psi.tau_s`, `provenance.basis`)

- **Found:** MSC04312 (Bouman p. 2): heaters switch on at 865 psig and off at 935 psig, relief
  cracks at 973 psig, and the transducer reads 50-1,050 psig ±2.5 % of full scale. Forester p. 65
  (Apollo 12 and 14 data): pressurisation strokes last "about four minutes". JEPS pp. 2.6-14 to
  2.6-16: 900 +35 psia design pressure, caution above 950 or below 800 psia, and 53 W heater
  elements.
- **Why it stays unset:** the published behaviour is a relay-controlled cycle between switch points.
  Its period depends on heater power, heat leak, draw and fluid density. No source gives a
  first-order lag toward 900.
- **Question for John (E2):** (a) replace the lag with a bang-bang heater rule between 865 and 935
  psig, validated against a pressurisation stroke of about 4 minutes. This is a WP06 rule change.
  (b) Choose a `tau_s` with a bound and accept a lag approximation. (c) Hold the indication
  constant at 900 for the quiet coast, which is within the transducer's ±25 psi.

### E4 — condensing heat exchanger removal rate (`eclss` `condensing_heat_exchanger.removal_kg_h`)

- **Found:** WP1321 p. 7 Table III gives a Block II ECS computer case: 1 suited and 2 cabin crew,
  518 + 896 Btu/hr metabolic, and a suit heat-exchanger **latent load of 818 Btu/hr**. At about
  1,060 Btu/lb of latent heat that is about 0.77 lb/h, or 0.35 kg/h, at a 62.8 F cabin dew point.
  D6718 p. 10 Table V gives the cyclic accumulator at 130 cc per actuation every 10 min, a
  **removal capacity of 0.78 kg/h**. SP368 p. 518 limits cabin relative humidity to 40-70 %.
- **Why it stays unset:** the first figure is a design operating point and the second is a
  capacity. The model's field is a rate, and at steady state the removal equals the crew's vapour
  production, which is not modelled. `test_a_bounded_search_record_is_what_the_corpus_now_carries`
  also holds this component at `UNCONFIGURED`. This entry was not edited.
- **Question for John (E4):** make the exchanger a capacity, bounded by 0.78 kg/h, and give the
  crew a vapour source (about 0.35 kg/h for three crew at the WP1321 case). Or keep the humidity
  stock out of the quiet-coast objective.

### E5 — CO2 absorber capacity (validation finding)

SP368 pp. 521-522 gives the CSM LiOH specification: "a maximum average removal rate of 0.064 kg/hr
(0.142 lb/hr) for 24 hours" and "1.54 kg (3.4 lb) total for 93 percent utilization". Elements were
changed every 24 h, staggered every 12 h. At the model's 0.91 kg CO2 per crew-day, 1.54 kg is
about **40.6 man-hours per element**. The model's single CSM counter is rated 72 man-hours
(`csm_lioh_element`, from NR/PSR). Two elements staggered in parallel share three crew, about
36 man-hours each per 24 h, so the 72 figure reads as the pair, not one element. This is
recorded and not changed. The counter semantics are a WP06 question.

### Consumables, other

- `pressurant_he_kg.min_flow_per_s` and `consumers.pressurant_blowdown` belong to WP03
  (propulsion) and are out of scope for a coast with no burns. Not researched.
- `reconciliation.tolerance_kg`: the O2 pressure transducer accuracy (±2.5 % FS, Bouman p. 2) is the
  only instrument figure found. JEPS p. 2.6-13 describes capacitance quantity probes and gives no
  accuracy. The per-resource tolerance stays unset.
- Water balance validation case: SP368 Table 3 (Apollo 15, 12.3 days) gives fuel-cell production
  of 520 lb, about 1.76 lb/h. AOH27 p. 2.7-14 gives fuel-cell water into the ECS at about 1.5 lb/h.
  The model's product water at its 1,723 W demand is 0.619 kg/h = 1.36 lb/h. Its demand already
  exceeds the flight thermal load (T1), so this comparison constrains the electrical demand, not
  the reactant law (C1).
- Metabolic O2: SP368 p. 520 gives the allowance as 0.82 kg (1.8 lb) per man-day. The model carries
  0.91 kg (`vehicle.yaml#consumables.metabolic`, NR planning rate). The two are recorded side by
  side and the value is unchanged.

## Movement in the tools

- Debts 270 → 268. UNCONFIGURED scalars 192 → 190. The state and readiness buckets did not move,
  because the fan's ventilation state has no state row yet.
- `docs/deep_research/integration/reconciliation/README.md:93` ("Composes with 270 declared
  debts") moves to 268, before the parallel electrical round's own change. It is not edited here.
