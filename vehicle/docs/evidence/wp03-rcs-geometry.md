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
| DB1 | CSM/LM Spacecraft Operational Data Book, Vol. I CSM Data Book, Part I Constraints and Performance, SNA-8-D-027(I) Rev 3 (SD 68-447), 15 Apr 1970, amended to 1972 | CSM 101 and subs: flight hardware | <https://www.ibiblio.org/apollo/Documents/HSI-41539.pdf> |
| R577-3 | GSOP R-577 Section 3, Digital Autopilots, Rev. 3, Dec 1968 | COLOSSUS 1 (Rev 237) and 1A (Rev 249): flight software | <https://ibiblio.org/apollo/NARA-SW/R-577-sec3-rev3.pdf> |
| R577-6 | GSOP R-577 Section 6, Control Data, Rev. 1, Dec 1968 | COLOSSUS verification simulators | <https://www.ibiblio.org/apollo/NARA-SW/R-577-sec6-rev1.pdf> |
| R567-6 | GSOP R-567 Section 6, Control Data, Nov 1968 | LUMINARY verification simulators, LM-6 | <https://ibiblio.org/apollo/NARA-SW/R-567-sec6.pdf> |
| D-7151 | TN D-7151, Apollo Experience Report: CSM Reaction Control Systems, Taeuber and Weary, Jun 1973 | Block I and II | <https://ntrs.nasa.gov/api/citations/19730017174/downloads/19730017174.pdf> |
| E-1964 | MIT IL E-1964, Apollo CSM Reaction Control by the Digital Autopilot, Crisp and Keene, May 1966 | Block II design | <https://www.ibiblio.org/apollo/hrst/archive/1151.pdf> |

**How these were read.** The first pass read the documents' OCR text layers through a fetch
tool, because this container's network policy refused the hosts to the shell. The project's
primary-source research thread then rendered every page this record cites as an image and read
it, including the drawings; its record, with each rendered page, is
`/mnt/project-files/sources/rcs.md` and `/mnt/project-files/sources/rcs/`. Every value below is
now from a rendered page, and where the text layer had misread a sign the section says so.

The two GSOP Section 6 documents are control data for MIT's verification simulators
("a control document governing the data used in the digital and hybrid simulators", R577-6
foreword), and a simulator constant does not by itself qualify flight hardware (this repository
refused R577-6's 14 ms CM minimum pulse on those grounds). Each Section 6 value landed here is
therefore one that a flight-hardware document states independently, and the YAML names both.

## G-1 SM quad station, radii, offset and cant (filled)

- **Question.** Where are the SM RCS quads, and how are their jets tilted?
- **Values.** All four quads at X_A 958.97 in; pitch and yaw thrust lines meet 82.36 in from the
  X axis and roll thrust lines 83.00 in; quads 90 deg apart, rotated -7.25 deg about +X from the
  Y and Z axes; nozzles canted 10 deg with the exhaust "directed away from the spacecraft
  surface".
- **Source (flight hardware).** DB1 Figure 4.3-2, printed p. 4.3-31, and ODB Figure 2-5, printed
  p. 2-6, "Service Module RCS Thrust Chamber Locations" (the same drawing): "(θ) ±PITCH AND YAW
  THRUST LINE INTERSECTION" at X_A 958.97, radius 82.36 in; "(*) ±ROLL THRUST LINE INTERSECTION"
  radius 83.00 in; "10° (TYP)"; "7° 15' (TYP) (4 PLACES)". ODB Figure 2-10, printed p. 2-11: "XA =
  958.97 SM/RCS QUAD".
- **Corroboration.** R577-6 s. 6.4.1.3: RCRX 958.97 in, RCRAD 82.68 in (the mean of 82.36 and
  83.00, "averaged"), OFFSET 7.25 deg "by a negative rotation about the +X axis", CANT 10.0 deg.
  AOH printed p. 2.5-1: "offset from the S/C Y and Z axis by 7 degrees 15 minutes", "canted
  approximately 10 degrees away from the panel structure". E-1964 p. 9: "displaced -7.25 deg. in
  roll from structure axes".
- **Effectivity.** Block II CSM.
- **Home.** `geometry.rcs_sm.{quad_station_xa_in, pitch_yaw_radius_in, roll_radius_in,
  quad_offset_deg, cant_deg}`.
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
- **Engine names (filled).** DB1 Table 4.3-12 "Service Module RCS Control Definitions", printed
  p. 4.3-28, lists the SM engines in the DAP's order with quad, translation and rotation: 1 C3,
  2 A4, 3 A3, 4 C4, 5 D3, 6 B4, 7 B3, 8 D4, 9 B1, 10 D2, 11 D1, 12 B2, 13 A1, 14 C2, 15 C1, 16 A2,
  matching the derived table on every jet. AOH Figure 2.5-1 "CM-SM Engine Locations" draws quad A
  on -Z, B on +Y, C on +Z, D on -Y, **the placement derived above**, and AOH Figure 2.3-14 "SM
  Jet Functions" repeats the map. Landed as `aoh_name`; `check_rcs_geometry` refuses a name whose
  quad, axis class or sign disagrees with its jet. The names make DB1's named-jet rules
  addressable, for example s. 3.3.1.2.2: "the service module RCS jet B3 (-X) must be deactivated
  while the lunar module rendezvous radar is operated" (DAP jet 7).

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

## G-4 LM jet 4's sign (filled)

- **Question.** Which way does LM jet 4 (IV-S) push?
- **Read.** The rendered R567-6 p. 6-22 prints jet 4 as `0.0 / -444.82 / 0.0`, that is -Y, and
  jets 1 and 13 as `-444.82` on X. The OCR text layer had dropped those minus signs.
- **Prediction it confirms.** The first pass landed -Y before the scan was read, because +Y at
  Y = +1.685 m would exhaust into the jet's own cluster and leave the side jets no torque-free -Y
  pair. `check_rcs_geometry` keeps that rule: every LM jet's force points back across its
  cluster's centre.

## G-5 SM per-jet offsets (approximation kept; adds no decision)

- **Question.** Does any SM jet sit off its class's intersection point?
- **Read.** DB1 Figure 4.3-2's View 1 (one quad detailed) dimensions each roll engine's centre
  line 0.94 in fore or aft of X_A 958.97; its 3.125 in and 6.750 in dimensions lie along lines of
  action and move no torque. Whether View 1 is typical of all four quads is not printed.
- **Fidelity call** (John, 13:51Z and 13:59Z: fidelity must add a signal, a confounder or an
  option). The 0.94 in offsets give each roll firing a cross-axis torque of about 1 % of its roll
  torque and change no jet's role, no failure's consequence and no crew or agent option: **adds
  no decision**. Not modelled; recorded in the YAML note.

## G-6 CM jet geometry (filled)

- **Question.** Where are the CM's twelve jets, which way do they push, and what does each do?
- **Positions (flight hardware).** DB1 Figure 4.4-2 "Command Module RCS Thrust Chamber
  Locations", printed p. 4.4-15, CSM 101 and subs: the thrust-exit-plane points A-N with RCS
  system A or B, and note (1), the two roll engines at G and at H share the intersection point
  of their centrelines. Every coordinate equals R577-6 s. 6.5.1.2's (printed pp. 6-42, 6-43,
  rendered), whose text layer had lost the signs that made jets 1 and 3 look identical.
- **Directions (derived from the drawing's angles).** Section M-M: yaw and aft pitch engines at
  "47° TRUE" from the radial towards +X; roll engines in the X_C 32.3 plane at α 46° 24' 10" and
  β 56° 22' 28" either side of the radial through H (θ_c 315° 55') and G (224° 05'); forward
  pitch engines drawn perpendicular to X, exhausting -Z, with an in-plane tilt the drawing does
  not dimension (taken as zero). Thrust is the negative of the exhaust.
- **Functions and subsystems.** AOH Figures 2.5-1 and 2.3-14: +pitch 13/23, -pitch 14/24, +yaw
  15/25, -yaw 16/26, +roll 11/21, -roll 12/22, subsystem 1 = 11-16 (DB1's system A).
  Corroborated by AOH p. 2.3-32 (direct coils on all CM engines "except 13 and 23") and p. 2.5-39
  (the dump excludes "the two + pitch engines").
- **Validation.** Every derived vector turns the CM the way its engine's function says, about the
  R577-6 simulator CG (41.7, -0.4, 5.6 in), and the vectors reproduce R577-6 s. 6.11.2's
  hybrid-simulator moment-arm table to 0.05 ft on ten of twelve jets. The two rows that differ
  (its jets 1 and 11) disagree with their own mirror jets, so the simulator table is read as wrong
  there. `check_rcs_geometry` rebuilds each vector from the angles and checks its torque sign.
- **Fidelity.** Lands: every CM pitch and yaw jet also turns the CM a little about the other two
  axes, and the two subsystems' couplings cancel only when both fire. A single-subsystem entry
  therefore shows a cross-coupling that reads like a misaligned or failed jet: a confounder.
  Not modelled: the nozzle extensions' alignment angles (DB1 Table 4.4-3, 0.74-8.23 deg in vacuum)
  and the thrust's fall with altitude during entry (same table), both for the CM article's lane.
- **Home.** `geometry.rcs_cm`.

## G-7 The CM jet is not the SM jet (decided and landed: split)

- **What the vehicle says.** `components.thruster_100lbf`: one component for all forty-four
  because they are the same article; `vehicle.yaml#propulsion.rcs_cm` takes 445 N and 277.8 s
  "as `rcs_sm`".
- **What the sources say.** DB1 Table 4.4-1 "Command Module RCS Engine Vacuum Steady-State
  Performance", printed p. 4.4-9 (Rocketdyne qualification data, no nozzle extension): thrust
  96.0 lb (+3.6/-3.7), Isp 272.0 ± 6.9 s, O/F 2.09, flow 0.353 lb/s, expansion ratio 9.00. AOH
  printed p. 2.5-47: "Nominal thrust 93 pounds", "Expansion ratio 9 to 1", "Cooling Ablation".
  D-7151 pp. 3, 9-10: Gemini-derived, ablatively cooled, 9:1 against the SM engine's 40:1. For
  comparison DB1 Table 4.3-1, printed p. 4.3-17, gives the SM engine 102.8 lb (+3.4/-3.8) and
  277.3 (+8.8/-13.6) s.
- **Decision.** The coordinator first chose *owe* under John's 13:48Z delegation of obvious scope
  questions, because the article's flight figures had not been found and the only figures to hand
  were R577-6's simulator constants. With DB1's flight-hardware figures in hand the answer is
  **split**: the CM engine becomes its own article at 96.0 lb (427.0 N) and 272.0 s, a
  declaration only. It landed after the test-figure unpin as `components.thruster_cm`, with
  `vehicle.yaml#propulsion.rcs_cm` at 427 N and 272.0 s and `thruster_100lbf` reduced to the
  thirty-two SM and LM thrusters. The CM's `capability.impulse_capacity` moved from 305,120 to
  298,750 N·s. The shared `prop_rcs` node and its one drain edge `E-RCSP-RCS` still price every
  newton at the SM and LM article's 277.8 s, so a CM firing draws 2 % less propellant there than
  its engine does; that is the coupling's to carry, and the edge's comment says so.
- **Not changed.** The SM article stays at C-26's 445 N and 277.8 s: DB1's 102.8 lb and 277.3 s
  are inside its published tolerance of D-7151's 100 lb rating and the Isp agrees to 0.2 %. A
  change there is a number, not a decision, and C-26 is the operator's.

## Not geometry: the minimum impulse bit (recorded; lands after the unpin)

- **SM.** DB1 Figure 4.3-3 "Service Module RCS Engine Vacuum Total Impulse Versus Electrical ON
  Time", printed p. 4.3-32, digitised by the research thread: 0.95 lbf·s nominal (0.81-1.12) at
  15 ms, about 4.2 N·s (3.6-5.0). DB1 s. 4.3.4: PGNCS minimum impulse is a 14 ms pulse, and the SCS
  minimum pulse is "11.5 to 18.5 milliseconds each, depending on the command module electrical bus
  supply voltage". Integrating the AOH Figure 2.5-9 typical 15 ms history gives about 1.2 lbf·s.
- **CM.** DB1 Figure 4.4-6 starts at 20 ms: about 1.4 lbf·s nominal there. Nothing shorter is
  published.
- **LM.** LM AOH LMA790-3-LM10, printed p. 2.4-10: "the minimum pulse for TCA firing (at 21 volts)
  is 13 milliseconds"; integrating its Figure 2.4-8 curve gives about 0.59 lbf·s. This conflicts
  with `capability.minimum_command_on_s.rcs_lm`'s 10 ms from the LM study guide; the two may
  describe different supply voltages.
- **Why it matters (fidelity).** The pulse a minimum command delivers grows with the ON time, and
  the SCS ON time grows as the CM bus sags: a sagging bus makes every minimum pulse bigger and
  spends RCS propellant faster with no RCS fault, which reads like a slow leak in the propellant
  gauge. That is a cross-system confounder, so it is worth the GNC and RCS lane's rule. The values
  are curve readings, not published numbers, so they land as `historical` with the reading's band
  when the debt count can move.
