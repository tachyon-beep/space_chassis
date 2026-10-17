# WP03 evidence: RCS jet geometry

The research record for the RCS geometry row of WP03
(`docs/vehicle-completion/02-remaining-work.md` §M2, in the repository root): where each jet is,
which way it pushes, and what it is for, so the allocator can build its wrench matrix
`B = [F_i d_i ; r_i x F_i d_i]` (`rcs_dode.md:685-693`). The standard is
[evidence.md](../evidence.md). Every landed value lives in
`domains/rcs/components.yaml#geometry` with provenance, and `check_rcs_geometry` holds each table
to the source that cross-checks it. No number below is a model input unless that block names it.
Thrust, Isp and command timing were already landed (`capability`, `components.thruster_100lbf`)
and are not re-opened here except for the finding in G-7.

## Sources

| id | document | effectivity | URL |
|---|---|---|---|
| AOH | Apollo Operations Handbook, Block II, SM2A-03-BLOCK II-(1), Vol. 1, s. 2.5 RCS and s. 2.3 SCS, 15 Oct 1969 change | CSM 106 and subs | <https://www.ibiblio.org/apollo/ApolloProjectOnline/Documents/SMA2A-03-BLOCK%20II%20Volume%201%2019691015/aoh-v1-2-05-rcs.pdf>, `.../aoh-v1-2-03-scs.pdf` |
| ODB | CSM/LM Spacecraft Operational Data Book, SNA-8-D-027(III) Rev 2, Vol. III Mass Properties, s. 2.0 | Block II CSM, LM | <https://www.nasa.gov/wp-content/uploads/static/history/alsj/SNA-8-D-027III-Rev2-CsmLmSpacecraftOperationalDataBook-Volume3-MassProperties.pdf> |
| R577-3 | GSOP R-577 Section 3, Digital Autopilots, Rev. 3, Dec 1968 | COLOSSUS 1 (Rev 237) and 1A (Rev 249): flight software | <https://ibiblio.org/apollo/NARA-SW/R-577-sec3-rev3.pdf> |
| R577-6 | GSOP R-577 Section 6, Control Data, Rev. 1, Dec 1968 | COLOSSUS verification simulators | <https://www.ibiblio.org/apollo/NARA-SW/R-577-sec6-rev1.pdf> |
| R567-6 | GSOP R-567 Section 6, Control Data, Nov 1968 | LUMINARY verification simulators, LM-6 | <https://ibiblio.org/apollo/NARA-SW/R-567-sec6.pdf> |
| D-7151 | TN D-7151, Apollo Experience Report: CSM Reaction Control Systems, Taeuber and Weary, Jun 1973 | Block I and II | <https://ntrs.nasa.gov/api/citations/19730017174/downloads/19730017174.pdf> |
| E-1964 | MIT IL E-1964, Apollo CSM Reaction Control by the Digital Autopilot, Crisp and Keene, May 1966 | Block II design | <https://www.ibiblio.org/apollo/hrst/archive/1151.pdf> |

**How these were read, and the limit it sets.** This environment's network policy refuses
`www.ibiblio.org`, `ntrs.nasa.gov` and `www.nasa.gov` to the shell, so no PDF could be downloaded
or rendered. Every value below was read from the documents' OCR text layers through a fetch tool,
as short verbatim fragments, and each was asked for twice in different forms where a sign or digit
mattered. **Figures whose data is graphical could not be read at all**; they are G-5 and G-6, and
rendering them is the next research step once a session can reach those hosts.

The two GSOP Section 6 documents are control data for MIT's verification simulators
("a control document governing the data used in the digital and hybrid simulators", R577-6
foreword), and a simulator constant does not by itself qualify flight hardware (this repository
refused R577-6's 14 ms CM minimum pulse on those grounds). Each Section 6 value landed here is
therefore one that a flight-hardware document states independently, and the YAML names both.

## G-1 SM quad station, radius, offset and cant (filled)

- **Question.** Where are the SM RCS quads, and how are their jets tilted?
- **Values.** All four quads at X_A 958.97 in; jet centreline intersection 82.68 in from the X
  axis (averaged over the jets); quads 90 deg apart, rotated -7.25 deg about +X from the Y and Z
  axes; nozzles canted 10.0 deg with the exhaust "directed away from the spacecraft surface".
- **Source.** R577-6 s. 6.4.1.3: RCRX 958.97 in, RCRAD 82.68 in, OFFSET 7.25 deg "by a negative
  rotation about the +X axis in accordance with the right-hand rule", CANT 10.0 deg.
- **Corroboration (flight hardware).** ODB Figure 2-10, printed p. 2-11: "XA = 958.97 SM/RCS
  QUAD". ODB Figure 2-5, printed p. 2-6: radii "82.36" (8)" and "83.00" (*)", whose mean is
  82.68 exactly. AOH printed p. 2.5-1: "offset from the S/C Y and Z axis by 7 degrees 15
  minutes"; "canted approximately 10 degrees away from the panel structure". E-1964 p. 9:
  "displaced -7.25 deg. in roll from structure axes".
- **Effectivity.** Block II CSM (Colossus from Apollo 8; AOH CSM 106 and subs).
- **Units, bounds.** in, deg. The radius is a mean: the jets sit at 82.36 or 83.00 in, ±0.32 in.
- **Home.** `geometry.rcs_sm.{quad_station_xa_in, quad_radius_in, quad_offset_deg, cant_deg}`.
- **Consumer.** The allocator's `r_i` and `d_i`; `E-RCS-DYN`.

## G-2 SM jet numbering, quad membership and direction (filled, derived)

- **Question.** Which quad is each SM jet on, which way does it push, and what does it do?
- **Source.** R577-3 Tables 3.2-III to 3.2-X, printed pp. 3.2-33 to 3.2-35: the DAP's jet
  selection for pitch (quads AC, jets 1-4), yaw (BD, 5-8), roll AC (13-16) and roll BD (9-12),
  X translation (AC: +1,2 / -3,4; BD: +5,6 / -7,8), Y translation (AC: +13,14 / -15,16) and Z
  translation (BD: +9,10 / -11,12), each with quad-fail rows. P. 3.2-28: "Quads A and C are
  aligned with the yaw-control (Z) axis", "Quads B and D ... the pitch-control (Y) axis"; the
  footnote on p. 3.2-1 rotates the control axes -7.25 deg from the navigation base axes.
- **Derivation.**
  1. *Membership* from the quad-fail rows: a jet still selected with a quad failed is not on it.
     Pitch, A failed: +pitch 1, -pitch 4; C failed: +pitch 3, -pitch 2. So A = {2, 3}, C = {1, 4}.
     Yaw: B = {6, 7}, D = {5, 8}. Roll AC: A = {13, 16}, C = {14, 15}. Roll BD: B = {9, 12},
     D = {10, 11}. The translation tables' quad-fail rows give the same split.
  2. *Force axis* from the translation tables.
  3. *Which end of the axis* from the torque signs, by tau = r x F with right-handed pitch, yaw
     and roll about the control Y, Z and X axes: jet 1 pushes +X and gives +pitch, so quad C is
     on +Z_c; jet 6 pushes +X and gives -yaw, so B is on +Y_c. Hence A on -Z_c, B on +Y_c,
     C on +Z_c, D on -Y_c.
  4. *Direction* in control axes: the nominal axis tilted 10 deg towards the X axis (the exhaust
     leans outward, so the thrust leans inward).
- **Validation.** The assignment is overdetermined: eight tables, and the sixteen torque signs
  must all agree with one placement of four quads. They do, and an exhaustive check of the 24
  placements finds no other that satisfies them. `check_rcs_geometry` recomputes every jet's torque from
  the landed geometry and refuses a disagreement; the test breaks a quad and a sign to see it.
- **Effectivity.** Flight software (Colossus 1/1A), Block II CSM. E-1964 (May 1966) has the
  same grouping (pitch and yaw jets also control X; A-C roll jets Y; B-D roll jets Z).
- **Home.** `geometry.rcs_sm.jets` (basis `derived`, `jets_provenance`).
- **Engine names (filled).** AOH Figure 2.5-1 "CM-SM Engine Locations", rendered
  (`/mnt/project-files/sources/rcs/aoh-fig2.5-1-cm-sm-engine-locations.png`), labels each SM engine
  with its rotation (+P A3, -P A4, CW+R A1, CCW-R A2; +Y B3, -Y B4, CW+R B1, CCW-R B2; +P C3, -P
  C4, CW+R C1, CCW-R C2; +Y D3, -Y D4, CW+R D1, CCW-R D2; "odd number engines = +rotation") and
  draws quad A on -Z, B on +Y, C on +Z, D on -Y: **the figure independently confirms the placement
  derived above**. Matching rotation and quad gives the map, landed as `aoh_name`: 1 C3, 2 A4, 3
  A3, 4 C4, 5 D3, 6 B4, 7 B3, 8 D4, 9 B1, 10 D2, 11 D1, 12 B2, 13 A1, 14 C2, 15 C1, 16 A2. AOH p.
  2.3-25's A/C roll select switches wired to "A1, A2, C1, and C2" agree (DAP jets 13-16, roll AC).
  `check_rcs_geometry` refuses a name whose quad, axis class or sign disagrees with its jet.

## G-3 LM jet positions and force axes (filled)

- **Question.** Where is each of the LM's sixteen jets and which way does it push?
- **Source.** R567-6 s. 6.4.1: the LM coordinate origin is "254 inches (6.4516 meters) below the
  RCS reference plane"; s. 6.4.1.4 positions in metres; s. 6.4.5.2 (printed pp. 6-22, 6-23)
  force vectors of 444.82 N on single axes. Names follow the table: cluster I-IV, jet U (up), D
  (down), F (fore/aft) and S (side).
- **Corroboration (flight hardware).** ODB Figure 2-12, printed p. 2-13: "RCS PITCH AND ROLL JETS
  ZE AND YE = ±66.1" and "RCS YAW JETS ZE AND YE = ±61.5" (effective geometric moment arms).
  Figure 2-13, printed p. 2-14: "XE = 254.0", "45° (TYP)". The simulator's 1.67894 m is 66.10 in,
  its 1.5621 m 61.50 in and its 6.4516 m 254.00 in. `check_rcs_geometry` holds all sixteen
  positions to those three figures.
- **Effectivity.** LM-6 simulator data (Apollo 12 era) with the ODB Rev 2 figure; the evidence
  says nothing about later LM changes to jet placement.
- **Units.** m in the YAML, as printed; the ODB check is in inches.
- **Home.** `geometry.rcs_lm` (frame `LM_XE`).
- **Thrust.** 444.82 N is 100 lbf exactly and agrees with the 445 N already declared.
- **Not printed.** No cant. R567-6 models every LM jet as pushing along one axis.

## G-4 LM jet 4's sign (derived; scan reading owed)

- **Question.** Which way does LM jet 4 (IV-S) push?
- **Printed.** Its s. 6.4.5.2 entry reads `0.0 / 444,82 / 0.0`, that is +Y. Jets 1 and 13 print a
  tilde where jets 5 and 9 print a minus; the tildes are read as minus.
- **Why the printed sign is not landed.** Jet 4 sits at Y = +1.685 m, on the outer face of
  cluster IV; a +Y force there exhausts into its own cluster. Its mirror across the Y axis,
  jet 8 (III-S, also at +Y), prints -Y. With jet 4 at +Y the side jets have three +Y
  and one -Y, and the LM has no torque-free -Y translation pair. Every other jet in the table
  pushes back across its cluster's centre.
- **Landed.** -Y, with the reason in the YAML note. `check_rcs_geometry` refuses the printed +Y
  under the exhaust-outward rule.
- **Owed.** A reading of the rendered scan of printed p. 6-22. If the scan says +Y, this is a
  conflict for the operator, not a correction.

## G-5 SM per-jet offsets (approximation kept; adds no decision)

- **Question.** Where does each SM jet sit relative to the averaged intersection?
- **Searched.** ODB Figure 2-5 (printed p. 2-6) has dimensions "3.125" (8) ±PITCH AND YAW THRUST
  LINE INTERSECTION", "6.750"", "82.36" (8)" and "83.00" (*)"; which jets each applies to is in the
  drawing, not the text. AOH printed p. 2.5-1 says the two roll engines on each quad "are
  offset-mounted to accommodate plumbing"; AOH Figure 2.5-1 (engine locations) and Figure 2.3-14
  (engine table) are graphical. D-7151 figures 1, 16 and 17 and E-1964's quad figure are
  drawings too.
- **Effect of leaving it.** The averaged model puts all four jets of a quad at one point. Using
  82.36 or 83.00 in instead of 82.68 moves a lever arm by 0.4 %; the 3.125 in and 6.750 in
  offsets change roll and cross-coupling torques by a few per cent. This is the GSOP's own model,
  so the DAP was verified against it.
- **Fidelity call (John, 13:51Z: fidelity must add options for scenarios, behaviours, decisions
  or challenges).** Per-jet offsets **add no decision**: they shift torque per jet by a few per
  cent and change no jet's role, no failure's consequence and no crew or agent option. The
  averaged model stays as a documented approximation. If ODB Figure 2-5 is rendered anyway, the
  offsets are a cheap refinement, not an owed item.

## G-6 CM jet geometry (functions filled; positions and directions owed)

- **Question.** Where are the CM's twelve jets and which way do they push?
- **Searched.** R577-6 s. 6.5.1.2 (printed p. 6-43) lists twelve positions in the CM vehicle
  frame, but the text layer has lost signs: jets 1 and 3 print identically (27.6750, 4.4211,
  -72.2846 in), as do jets 10 and 11 (32.3000, -51.9826, -50.3454 in), and jets 6, 9 and 12
  carry tildes. Thrust directions are only in "Fig. 4-20" of an external reference (s. 6.5.3.2).
  The AOH says each nozzle is "ported through the CM skin" (p. 2.5-25) and names jets by function
  (p. 2.5-36, 2.5-39), with no positions.
- **Filled: subsystem and function.** AOH Figure 2.5-1 names the CM's jets 11-16 (subsystem 1)
  and 21-26 (subsystem 2): +roll 11/21, -roll 12/22, +pitch 13/23, -pitch 14/24, +yaw 15/25, -yaw
  16/26; corroborated by AOH p. 2.3-32 (direct coils on all CM engines "except 13 and 23") and p.
  2.5-39 (dump excludes "the two + pitch engines"). This is the decision-bearing half: it is what
  a subsystem failure during entry takes away, and each subsystem alone can still turn the CM
  both ways about every axis. Landed in `geometry.rcs_cm`.
- **Still owed.** Positions and thrust directions: four positions are sign-ambiguous in the text
  layer, no direction is readable, and the figure is a sketch. They matter only for torque
  magnitudes after CM/SM separation, which the bounded quiet-coast episode does not reach.
  R577-6's ids 1-12 are not yet mapped to the AOH's 11-26.
- **Next step.** Render R577-6 p. 6-43 and find the CM jet-orientation figure (the CM ODB
  volume or the AOH's CM RCS figures).

## G-7 Finding: the CM jet is not the SM jet (operator decision)

- **What the vehicle says.** `components.thruster_100lbf`: "one component for all forty-four
  because they are the same article"; `vehicle.yaml#propulsion.rcs_cm` takes Isp 277.8 s "as
  `rcs_sm`".
- **What the sources say.** D-7151 p. 3: "the Gemini 100-pound-thrust engine was to be used on
  the Apollo CM"; p. 9: "The CM engines were ablatively cooled, limited life engines ... used in a
  buried application", expansion "9:1", against the SM engine's radiation-cooled 40:1 (p. 6);
  p. 10: the change from 40:1 "sacrificed some performance". R577-6 s. 6.5.3 models the CM jet at
  "Thrust TH 93.6 lb" and "RCISP 272.1 sec" against the SM's 99.8 lb (s. 6.4.5), simulator values.
- **Effect.** The CM's twelve jets are a different article with lower thrust and Isp; the 445 N
  and 277.8 s that C-26 applied to all forty-four overstate the CM's impulse capacity (305,120
  N s) by about 2 % if the simulator's 272.1 s is near the article's Isp. No flight-hardware CM thrust or Isp was found in the text layers read;
  the AOH defers to the CSM data book (SNA-8-D-027 Vol. I, p. 2.5-24), not reached.
- **Decided: owe** (2026-10-17, by the coordinator under John's 13:48Z delegation of obvious
  scope questions, intent "preference more fidelity where it doesn't start creating significant
  delivery risk"). The CM jet becomes its own article with thrust and Isp owed until a
  flight-hardware source (the CSM data book, SNA-8-D-027 Vol. I) gives them. Splitting with the
  R577-6 figures was rejected because it would put simulator values in as stand-ins, and keeping
  one article for all forty-four is the lowest-fidelity option. The model change raises the
  pinned debt count, so it lands after the test-figure unpin.

## Not geometry

- **SM thrust.** D-7151 p. 33: "the SM RCS engine produced 100 pounds rather than 95 pounds of
  thrust", agreeing with the declared 445 N. R577-6's 99.8 lb is its simulator constant.
- **Minimum impulse bit.** Still unpublished in the sources reached. D-7151 p. 6 gives a 9 ms
  electrical ON to full open for both valves; R577-6 gives RCONDEL 0.015 s and RCOFFDEL 0.0105 s
  thrust-step delays (simulator). Neither is a delivered impulse; nothing here changes
  `capability.minimum_command_on_s`.
