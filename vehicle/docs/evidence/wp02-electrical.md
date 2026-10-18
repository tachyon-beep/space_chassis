# WP02 evidence: electrical

The research record for the electrical rows of WP02
(`docs/vehicle-completion/02-remaining-work.md` §M2, in the repository root), for the bounded
quiet-coast episode: CSM translunar coast, no faults. The standard is [evidence.md](../evidence.md).
Each value lives in its canonical YAML home with provenance; this file records how it was found
and what a rule must later pass. No number below is a model input unless the YAML names it.

## Sources

| id | document | effectivity | URL |
|---|---|---|---|
| AOH | Apollo Operations Handbook, Block II Spacecraft, SM2A-03-Block II-(1), section 2.6 EPS. Basic 15 Apr 1969, changed 16 Jul and 15 Oct 1969 | CSM 106 and subs (Apollo 10 on) | <https://www.ibiblio.org/apollo/ApolloProjectOnline/Documents/SMA2A-03-BLOCK%20II%20Volume%201%2019691015/aoh-v1-2-06-eps.pdf> |
| JEPS | J Mission Electrical Power System, North American Rockwell training handout, 1 Oct 1971 | J missions, CSM 112-114 (Apollo 15-17) | <https://www.ibiblio.org/apollo/Documents/J%20Mission%20Electrical%20Power%20System%20Oct%201971.pdf> |
| D-7609 | TN D-7609, Apollo Experience Report: CSM Electrical Power Distribution Subsystem, Mar 1974 | Block II, flown missions | <https://ntrs.nasa.gov/api/citations/19740011403/downloads/19740011403.pdf> |
| D-6976 | TN D-6976, Apollo Experience Report: Battery Subsystem, J. B. Trout, Sep 1972 | Block II CSM and LM | <https://ntrs.nasa.gov/api/citations/19720024228/downloads/19720024228.pdf> |
| A10C | Apollo 10 consumables analysis for the spacecraft operational trajectory, rev. 1, 9 May 1969 | Apollo 10 (CSM 106) | <https://www.nasa.gov/wp-content/uploads/static/history/afj/ap10fj/pdf/19740072794_a10-consumables-analysis-for-sc-op-traj-rev1-19690509.pdf> |
| A14MR | Apollo 14 Mission Report, section 7.2 | Apollo 14 (CSM 110) | <https://nasa.gov/wp-content/uploads/static/history/alsj/a14/a14mr07.htm> |
| A15MR | Apollo 15 Mission Report, section 6.2 | Apollo 15 (CSM 112) | <https://www.nasa.gov/wp-content/uploads/static/history/alsj/a15/a15mr-6.htm> |
| A15SC | Apollo 15 CSM Systems Checklist | Apollo 15 | <https://www.ibiblio.org/apollo/Documents/Apollo15CSMSystemsChecklist.pdf> |
| A14DB | Apollo 14 CSM Systems Data Book, 30 Nov 1970 | Apollo 14 (CSM 110) | <https://www.nasa.gov/wp-content/uploads/static/history/afj/ap14fj/pdf/csm_sys-data.pdf> |
| SP-5115 | NASA SP-5115, Fuel Cells: A Survey, 1973, ch. 4 | Apollo fuel cell (PC3A-2) | <https://ntrs.nasa.gov/api/citations/19730017318/downloads/19730017318.pdf> |
| JSC-17237 | Interbartolo, Apollo CSM Power Generation System Design Considerations, Failure Modes and Lessons Learned, 2009 | Block I and II | <https://ntrs.nasa.gov/citations/20090016297> |

Page numbers are the documents' printed page markers, read from OCR text; where the OCR is
garbled the entry says so. Shell access to these hosts is blocked from this environment, so the
graphical pages (curves) could not be rendered and read; that is the main reason values stay owed.

Corpus, cited and not edited: `apollo_diode.md:72-80` (the power channel table), `:157`
(transceiver and amplifier draws), `:341` (radiator isolation derates battery capacity);
`electrical_diode.md:248` (`SRC_CONV_A/B`, regulation transient <10 ms, ref.), `:250`
(`BAT_CONV_A/B`), `:251` (`BUS_A/B`, 24-32 V ref.), `:252` (`TIE_AB`).

## E-1 Fuel-cell normal operating envelope (filled)

- **Question.** Over what power range does one CSM fuel-cell power plant operate normally, and at
  what terminal voltage?
- **Value.** 400-1,420 W at 31-27 V dc at the fuel-cell terminals, endpoints paired 31 V at 400 W
  and 27 V at 1,420 W.
- **Source.** AOH p. 2.6-2: "normally supplies 400 to 1420 watts at 31 to 27 vdc (at fuel cell
  terminals)". JEPS p. 2.6-2: "from 400 to 1420 watts". The lower 563 W in the older provenance is
  TN D-7142's, repeated by SP-5115 p. 29 and JSC-17237.
- **Effectivity.** CSM 106 and subs (AOH); CSM 112-114 (JEPS). Block II only.
- **Units, bounds.** W, V. The pairing of endpoints is an interpretation of word order; it is
  stated in the YAML so the derived value below can be challenged at its root.
- **Home.** `domains/power/components.yaml#components.fc_[1-3].normal_power_w`,
  `terminal_v_at_normal_power`, `normal_envelope_provenance`.
- **Consumer.** WP04's bus solve; `power.source_[n]_current_a` bands.

## E-2 Fuel-cell source impedance (filled, derived)

- **Question.** What source impedance does a fuel-cell power plant present to a main bus?
- **Searched.** AOH section 2.6, JEPS, SP-5115 ch. 4, JSC-17237, D-7609, the ICECE 1972 paper
  "Fuel cell powerplant operation in Apollo spacecraft" (Ching, Gillis, Plauche; NTRS 19730037972,
  no download), A14DB. None gives terminal volts at a stated current in text. A14DB's contents list
  "FUEL CELL PERFORMANCE - VACUUM", a chart that would give the polarization curve, but its data
  is graphical only.
- **Value.** 0.1008 ohm per module; open-circuit intercept 32.30 V.
- **Derivation.** I_low = 400/31 = 12.903 A; I_high = 1420/27 = 52.593 A;
  R = (31 - 27)/(52.593 - 12.903) = 0.10078 ohm; E0 = 31 + R x 12.903 = 32.300 V. The secant of
  the published envelope, linear in current between its ends. It omits the polarization curve's
  curvature and is an extrapolation outside 12.9-52.6 A per module.
- **Per bus, with E-3's routing.** Main bus A (fuel cells 1 and 2 in parallel): 0.0504 ohm. Main
  bus B (fuel cell 3): 0.1008 ohm.
- **Home.** `fc_[1-3].source_resistance_ohm`, `open_circuit_intercept_v`,
  `source_resistance_provenance` (basis `derived`).
- **Consumer.** WP04: `power.bus_a_v`, `bus_b_v`; the load-step sag the flagship chain turns on.
- **Validation case (independent of the envelope).** At mission-average loads the model's terminal
  voltage must sit 0-1.0 V above the flown mean bus voltage, because the bus is downstream of the
  feeders and motor switches:

  | mission | source | A per module | flown mean bus V | predicted terminal V | bus - terminal |
  |---|---|---:|---:|---:|---:|
  | Apollo 14 | A14MR 7.2.2: 23 A per fuel cell, mean bus 29 V | 23.0 | 29.0 | 29.98 | -0.98 |
  | Apollo 15 | A15MR 6.2: 77 A average total, 28.8 V | 25.7 | 28.8 | 29.71 | -0.91 |
  | Apollo 11 | vehicle.yaml#electrical: 68.7 A at 29.4 V | 22.9 | 29.4 | 29.99 | -0.59 |

  This checks offset and plausibility, not slope: the three currents span 3 A. A slope check needs
  the vacuum performance chart, and is the next research step.
- **Finding for the coast case.** With the model's current bus split (598 W of loads on bus A,
  1,125 W on bus B), bus B's single module carries 39.8 A at 28.29 V, and bus A's two modules
  carry 9.5 A each — **below the 12.9 A normal minimum**, at 31.34 V, above the 31 V envelope.
  Apollo flew with roughly two thirds of the load on the two-module bus. Either the load
  assignment or the routing is not Apollo's, and WP04 will meet it on its first tick.
- **Rejected.** `csm_coolant_pump_1`'s 0.05 ohm (a `chosen` figure inside a reason string, not a
  source; it happens to equal the two-module bus A value). electrical_diode.md:248's converter
  figures (a reference design for hardware Apollo did not carry).

## E-3 Which fuel cell feeds which bus (filled)

- **Question.** Which main bus does each fuel cell normally feed?
- **Value.** fc_1 and fc_2 on main bus A, fc_3 on main bus B.
- **Source.** D-7609 p. 5: "the normal configurations were with fuel cells 1 and 2 on main bus A
  and with fuel cell 3 on main bus B"; A15MR 6.2, the same, 3.5 h before lift-off. AOH p. 2.6-2 gives
  the switchable set (fc 1 to A; fc 2 to A and B; fc 3 to B), and p. 2.6-38 six motor switches.
- **Effectivity.** Block II flown missions.
- **Home.** `fc_[1-3].normal_bus`, `normal_bus_provenance`.
- **Consumer.** WP04; closes the "source set" half of `bus_b_v`'s note (the battery half remains).
- **Validation case.** Total CSM coast current lies in the 60-80 A D-7609 p. 2 gives "between SPS
  burns"; the model's 1,723 W at 28 V is 61.5 A, inside it.

## E-4 CSM entry battery electrical points (recorded)

- **Values.** 20 silver oxide-zinc cells; 40 Ah minimum (25 A for 60 min); open circuit 37.2 V
  (AOH p. 2.6-17) or 37.1 V (JEPS p. 2.6-19); loaded 29 V at 35 A (AOH) or 28 V at 25 A (JEPS),
  27 V minimum in both; qualified ambient 50-110 F; planned 40 Ah in flight, 45 Ah postlanding
  (AOH p. 2.6-16; A10C Table 8-I p. 40). Charge terminates at 39.5-39.8 V (AOH p. 2.6-33; A15SC
  S/1-3); the bus-off battery check reads 31.5-38 V at <3 A (A15SC S/1-2).
- **Home.** `components.battery_csm_1.cells`, `open_circuit_v`, `loaded_points`,
  `qualified_ambient_f`, `capacity_planning_ah`, `electrical_provenance`.
- **Disagreement recorded, not resolved.** D-6976 Table I gives 29 V nominal and p. 3 "40 A-h
  (1160 W-h each)"; the model's `v_nominal` is 28, so `load_budget.csm_battery_energy_wh` (3,360)
  is 3.4 % below 3,480 Wh. Changing it moves `battery_charge_j`'s initial and its derived checks; it
  belongs with E-6.
- **Not derived.** A battery internal resistance from (OCV - V_loaded)/I gives 0.234 ohm (AOH)
  and 0.364 ohm (JEPS): the two handbooks disagree by 55 %, and the secant includes polarization.
- **Decided (2026-10-17, power lane).** The bus solves take the JEPS secant, 37.1 V open circuit
  and 0.364 ohm, for J-mission effectivity (CSM 112-114); recorded by the coordinator under John's
  delegation of 13:48Z. Batteries A and B tie onto main buses A and B by `set_source`, each a
  Thevenin source behind its diodes (`domains/power/rules.py:solve_sources`). Battery C's two-bus
  feed and the charge it spends (`battery_charge_j`, whose charger edge `E-BUS-BAT` is still owed)
  are not yet modelled.
- **Consumer.** WP04 (battery on bus during burns, entry); none in the coast episode, where the
  batteries are off the main buses (D-7609; A10C: two batteries in parallel only "during ascent and
  each SPS maneuver").

## E-5 `power.source_converter_v` tau_s (closed: the state is retired)

- **Decided.** John, 2026-10-17 (power lane, PR #43, decision c "retire"): option (a). The
  converter state, its node, its edge `E-BUS-CONV` and its fault PWR-01 are removed; the bus solve
  is the cells' terminal relation.

- **Question.** The converter's regulation time constant.
- **Finding.** Apollo has no source converter: fuel cells connect to the main buses through motor
  switches and "the application and removal of fuel cell loads causes the terminal voltage to
  decrease and increase, respectively" (AOH p. 2.6-25). The only time figure in reach is
  electrical_diode.md:248's "regulation transient <10 ms" for a reference-design regulator,
  shorter than one 20 ms tick. The slow effect Apollo does describe, terminal voltage recovering as
  skin temperature follows load (AOH p. 2.6-25), has no published time constant; JEPS p. 2.6-30
  gives only an open-circuit skin cooling rate of about 6 F/h.
- **Decision owed (operator).** (a) Make the source state the algebraic terminal relation
  V = E0 - R I using E-2's values, which needs no tau and is what the 50 Hz algebraic verdict
  (`review-findings.md` #5) assumes anyway; or (b) keep a converter and source a tau for one.
- **Validation case for (a).** A 72 W amplifier step on bus B at the coast point (39.8 A) moves the
  bus by 0.1008 x 72/28.29 = 0.26 V within one tick.

## E-6 `power.battery_usable_j_j` derate curve and basis (UNCONFIGURED)

- **Question.** Deliverable fraction of the 40 Ah versus pack temperature.
- **Searched.** AOH 2.6; JEPS; D-6976 (figs. 4-6 are discharge characteristics and a separation
  comparison, graphical, not temperature); A10C. Only: rated minimum 40 Ah across the 50-110 F
  qualified ambient. D-6976 p. 13 shows LM descent batteries at about 37 F on Apollo 13 delivering
  5-6 % above specified capacity at low load, which is a different battery and is context only.
- **Why not filled.** A flat 1.0 over 50-110 F is supported, but the edge that reads this state
  (`E-PLATE-BAT`) exists for the hot crisis case outside the qualification, and a curve with the
  half that matters missing would look complete.
- **Next source.** The CSM/LM Spacecraft Operational Data Book vol. I EPS pages (the ibiblio copy
  "CSM_Data_Book_Part_I_Rev_3_Partial.pdf" could not be fetched).
- **Corpus citation fix.** The state's note cites `electrical_diode.md:341` for the derating
  sentence; the sentence is `apollo_diode.md:341`.

## E-7 `power.battery_thermal_state` initial and tau_s (UNCONFIGURED)

- **Question.** Pack temperature at MET 0 and its thermal time constant.
- **Found.** Passive cooling, "mild thermal environment of the CM cabin" (D-6976 p. 5); qualified
  50-110 F (10-43.3 C). No CSM battery temperature telemetry, no pack thermal mass. Bounds only.
- **Owner.** WP02's thermal-aggregation row (pack mass, specific heat, mounting conductance).

## E-8 `power.bus_tie_closed` `auto` (UNCONFIGURED; operator decision)

- **Finding.** Apollo's MAIN BUS TIE switches tie batteries A/C and B/C to the main buses (motor
  switches S1, S2; AOH Fig. 2.6-1 note and p. 2.6-16; JEPS p. 2.6-3). Section 2.6 describes no
  direct main-bus-A-to-B tie. The real switch's AUTO position is not described in any text reached;
  a NASSP page says it switches to battery on an EDS abort, uncited, so it is a pointer and not a
  source.
- **Decision owed.** Keep the model's A-B tie as electrical_diode.md:252's `TIE_AB` and define
  `auto`, or re-model the tie as Apollo's battery-to-main-bus tie.
- **Decided.** Decision a "apollo", 2026-10-17 (power lane; recorded by the coordinator under John's
  delegation of 13:48Z): re-model the tie as Apollo's battery-to-main-bus tie (MAIN BUS TIE BAT A/C,
  BAT B/C), with fuel cell 2's cross-feed (AOH p. 2.6-38's six motor switches). Not yet built; the
  battery resistance is JEPS's 0.364 ohm for J-mission effectivity (AOH prints 0.234 ohm).

## E-9 `power.load_shed_class` `band_value` (closed: no automatic ladder)

- **Finding.** Apollo had no automatic shed ladder; the crew shed load by checklist. Published
  envelope: DC undervoltage caution below 26.25 V (AOH p. 2.6-5; D-7609 p. 8); sustained 26.5-30.0 V,
  limits 26.5-31.0 V (JEPS p. 2.6-26; AOH p. 2.6-27 prints 26.2-31.0); checklist range 26.5-31 V
  (A15SC S/1-2); "use batts only when main bus volts < 24.5" (A15SC EMER/1-7). The model's 26.5 V
  top tier is apollo_diode.md:73's event, 0.25 V above the flown caution; that difference is a
  conflict-register matter and is not changed here.
- **Decided.** Decision b "crew", 2026-10-17 (power lane, PR #43; John chose fidelity, and the
  coordinator recorded the option under John's delegation of 13:48Z). The three chosen shed tiers
  (25.5, 24.5 and 23.5 V) and `E-BUS-SHED` are retired. `bus_a_undervoltage` and
  `bus_b_undervoltage` remain cautions, as AOH p. 2.6-38's "for indication only" caution was.
  `load_shed_class` is now the most critical class among the loads on at MET 0 that the crew's
  `load_enabled` has off, with no band, so `band_value` is no longer owed. The crew's 24.5 V
  battery cue (A15SC EMER/1-7) belongs to the battery-on-the-bus work.

## E-10 Fuel-cell reactant rate (existing value, independently validated)

- **Source.** JEPS p. 2.6-21 and AOH pp. 2.6-18/19: O2 = 2.04e-2 lb per A-h, H2 = 2.57e-3 lb per
  A-h, per fuel cell; at 60 A, 1.224 lb O2/h and 0.1542 lb H2/h.
- **Check.** The model's 8.8619e-8 kg O2 per joule at 60 A x 29 V = 1,740 W gives 0.5551 kg/h =
  1.2238 lb O2/h, and over 7.9365, 0.15420 lb H2/h: both agree with the table to four figures.
- **Finding for WP04.** The table is per **ampere**. The model's draw is per **watt** at a fixed
  29 V, so at 27 V terminal the per-watt figure undercounts the reactant by 7 %. The rule should
  read the stack current.

## E-11 Load draws (not changed)

- **Question.** Per-equipment CSM draws.
- **Searched.** AOH 2.6 (gives only 81 W of continuous heaters to one assembly and inverter
  ratings: 1,250 VA each, low-voltage shutdown 16-19 V dc); A14DB (circuit-breaker maps, no
  ratings; glycol pumps on AC buses 1/2); A15SC (emergency power-down DC amps table, OCR
  unreadable); A10C (current profile as a figure only).
- **Validation for the inventory as a whole.** Flown CSM averages: Apollo 11 2.02 kW; Apollo 14
  69 A at 29 V = 2.0 kW; Apollo 15 77 A at 28.8 V = 2.22 kW; coast 60-80 A (D-7609 p. 2). The
  model's 1,723 W is inside the coast band at its low end.
- **Finding.** The CSM glycol pumps are AC loads behind the inverters (A14DB), while the model puts
  them on DC bus B at 250 W each; a DC-side figure would need inverter efficiency, which no text
  reached gives. The `chosen` draws stay as declared and are listed for WP04.
- **Leads from the WP02 thermal/consumables research (reported there, not re-read here).** TN D-6718
  (<https://ntrs.nasa.gov/api/citations/19720012252/downloads/19720012252.pdf>) p. 3 Table II, "ECS
  Power Summary", whose OCR cannot be aligned row-to-value with confidence but is consistent with a
  glycol pump of tens of watts rather than 250 W; Program Apollo WP-1321
  (<https://ntrs.nasa.gov/api/citations/19700025125/downloads/19700025125.pdf>) p. 10 Table IV: suit
  compressor 104 W including its inverter share, cabin blowers 76 W; SP-368 ch. 5
  (<https://ntrs.nasa.gov/api/citations/19760005606/downloads/19760005606.pdf>) p. 525: CSM coast heat
  load under PTC 1,170-1,470 W. These are the next step for the pump, fan and suit-compressor rows,
  and the last is a second independent bound on the coast total besides the flown currents above.

## Not electrical evidence

- `comms.tx_power` `selects` and `avionics.instrumentation_power` `selects` are switch-position
  states the model lacks (which transmitter, which profile), not values.
- `thermal.pump_1_speed_rpm` `initial`/`maps.on` needs a rated speed for a glycol pump; none found.
- `profiles.yaml#source_current_anomaly` assert/clear: Apollo had no such alarm. The normal
  envelope's minimum (12.9 A per module, E-1) is a candidate assert but there is no source for a
  clear, so both stay owed.
