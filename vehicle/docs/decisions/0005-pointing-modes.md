# 0005 — Attitude as pointing modes behind `set_attitude_target`

- Status: proposed
- Date: 2026-10-17
- Decision owner: John (sprint lane 7, GNC+RCS; arc review decision 5, "modes, not 6-DOF")
- Related work package / evidence gaps: `E-RCS-DYN`; `domains/rcs/components.yaml#open_debts`;
  PR #44 (SM RCS geometry); `/mnt/project-files/sources/rcs.md`
- Reviewers and review evidence: `tests/test_gnc_rcs_rules.py`
- Supersedes / superseded by: none

## Question and constraints

The vehicle published an attitude and an attitude error and could not change either: `E-RCS-DYN`
was unconfigured for want of an inertia tensor, `set_attitude_target` moved no state, and the
quiet-coast vehicle "starts in PTC" by assertion. The arc review chose pointing modes over a 6-DOF
allocator. The modes have to expose four trades a fleet can actually make: the thermal roll against
a comms hold, when to leave the roll for a burn attitude, which safe vector to take, and the
propellant each slew costs against the translation reserve.

## Evidence and options

- GSOP R-577 Section 3 Rev. 3 (COLOSSUS DAP), s. 3.2.2.1, printed p. 3.2-6, Noun 46: deadband 0.5
  or 5.0 deg; maneuver rate 0.05, 0.2, 0.5 or 4.0 deg/s. s. 3.2.3, p. 3.2-27: 14 ms minimum firing
  and the minimum-impulse limit cycle.
- Apollo 11 Mission Report (MSC-00171), printed p. 4-3: docked maneuvers at 2 deg/s inside a 0.5
  deg deadband; PTC at 0.3 deg/s about +X toward the ecliptic north pole, after which all sixteen SM
  auto switches go off.
- Data Book SNA-8-D-027(I) Rev. 3 via `sources/rcs.md`: 0.00545 lb per 14 ms PGNCS pulse against a
  4.2 N s minimum impulse, so a pulse burns propellant at an effective 173 s, not 277.8 s.
- `vehicle.yaml#mass_properties`: the docked stack's tensor with its products of inertia.

Options weighed: a kinematic rate law (the attitude moves at the commanded rate; cheap, but the PTC
roll never cones and a slew costs nothing physical); a full allocator over forty-four jets (the
6-DOF the arc review declined); and a rigid body driven by the DAP's couples, which is what is
taken.

## Decision

`rcs` decides a torque and `gnc` integrates it through the full inertia tensor.

- `rcs.attitude_target`, `target_frame`, `slew_rate_limit` and `control_profile` hold the request.
  `held_target` resolves it once, when it changes: `current`, an inertial frame, or BODY relative to
  the attitude at the moment of the command. An unreadable quaternion keeps the old target.
- `rcs.control_torque` is a rate-limited eigenaxis slew: it steers the rate toward
  `min(rate limit, sqrt(2 alpha theta))` along the error axis and asks for the torque that gets there
  this tick, scaled uniformly to the couple limits in the control axes (rotated -7.25 deg from body).
  Inside the deadband and below a rate floor it asks for nothing.
- `gnc.body_rate` integrates Euler's equation with a midpoint step, and `gnc.attitude` integrates
  the rate exactly over the tick. The PTC roll cones on its own because of the products of inertia.
- `rcs.thruster_thrust` spreads the torque over the SM jets of the DAP's couples. In the hold it
  carries the minimum-impulse limit cycle's average instead, at `dw / (4 deadband)` pulses per
  second per axis. `thrust_total_n` is the scalar the drain reads, with hold pulses priced at the
  pulse's own propellant. `impulse_total` books delivered impulse, so in a long hold the two
  gauges diverge; that is real and it is a confounder.
- `rate_limit_deg_s` is a required enum of the DAP's selections, with 2.0 standing for the flown
  4.0 (Apollo 11's docked rate). `set_deadband`'s four profiles each land on one of the DAP's two
  deadbands; `tight` differs from `nominal` by its threshold factors, not its band.

## Acceptance and consequences

- A 10 deg pitch slew at 0.5 deg/s on the docked stack peaks at 0.5 deg/s, settles inside 0.05
  deg, and costs 2.4 to 3.0 kg of RCS propellant (`test_a_commanded_slew_reaches_its_target_and_the_tank_pays_for_it`).
- A ten-minute torque-free PTC spin keeps its energy and momentum to 1e-6 and cones.
- Holding at 0.5 deg costs ten times as much as at 5 deg, about 3.2 and 0.32 kg/day.
- The controller reads truth, not the navigation estimate, until `gnc.nav_solution` exists; LVLH
  targets are recorded and not flown; only the docked stack's inertia is carried; the deadband's
  wander is not simulated. Each is an `open_debts` entry in `domains/rcs/components.yaml`.
- Two engine needs remain for the fault-injection lane: carrying an array argument as its value
  (the quaternion), and seeding a ruled `dynamics` state's declared vector or record at t=0.
