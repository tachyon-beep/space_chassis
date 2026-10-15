# Domain gaps: every state a tick cannot advance

As of **2026-10-15**, `main` @ `{{MAIN}}`. Generated from `python3 tools/plant.py --build-order` and
`--readiness` on that commit (the script is in the governance stream's notes; the tool is the source).
87 of 139 states cannot advance: 27 owe a value, 15 owe an edge, 45 owe a rule. Each row names the
state, its integrator class, which bucket the tick put it in, the **root** state whose gap blocks it
when that is a different state, and what is owed. Domains are in the order the work is deepest.

**Reading the buckets.** The tick runs once at t = 0 and each refusal is followed to the state blocked
on its own declaration; that root's gap is the bucket (`plant.py` `build_order`). "Value" means a
parameter the configuration can carry (`tau_s`, `initial`, a hysteresis band, a sensitivity) and is
the cheapest to close once evidence exists. "Edge" means `coupling.yaml` is missing a sensitivity or
a driver. "Rule" means domain code: an `algebraic` relation, a `discrete` state machine or a
`dynamics` equation, which `governance/decisions.md` D5 puts in `vehicle/domains/<name>/`.

| domain | states | advance | value | edge | rule | lands with |
|---|---:|---:|---:|---:|---:|---|
| gnc | 12 | 1 | 2 | 3 | 6 | WP03 evidence, then WP07 |
| rcs | 13 | 2 | 4 | 0 | 7 | WP03 evidence, then WP07 and WP05 |
| propulsion | 10 | 4 | 2 | 1 | 3 | WP03 evidence, then WP06 and WP07 |
| power | 13 | 5 | 4 | 1 | 3 | WP02 evidence, then WP04 and WP05 |
| avionics | 13 | 1 | 3 | 1 | 8 | WP05 and WP09 |
| comms | 10 | 3 | 2 | 0 | 5 | WP07 (geometry) and WP09 |
| crew | 7 | 0 | 2 | 0 | 5 | WP09 and the crew model (D-06) |
| structure | 10 | 5 | 1 | 0 | 4 | WP05 |
| thermal | 24 | 16 | 5 | 1 | 2 | WP02 evidence, then WP06 |
| eclss | 17 | 9 | 1 | 6 | 1 | WP02 evidence, then WP06 |
| consumables | 10 | 6 | 1 | 2 | 1 | WP02 evidence, then WP06 |

The 45 rules by class: 21 discrete, 10 algebraic, 7 stock, 4 lag, 3 dynamics. The seven stocks and four lags in the rule bucket are there because nothing drives them yet, which is the same work as the rule that would.

## gnc (11 of 12 blocked; WP03 evidence, then WP07)

No orbit, no attitude, no navigation. `orbital_state` needs the 6-DOF integrator class that `plant.md` §3 specifies and the plant does not implement; `attitude` and `imu_platform` have no inbound edge because the torque path (`E-RCS-DYN`) has no sensitivity, which in turn needs the jet geometry WP03 owes. `mission.yaml.initial_state.position_xyz_km` and `velocity_xyz_m_s` are `UNCONFIGURED`, so even a finished propagator has nothing to start from.

| state | class | owes | root | what |
|---|---|---|---|---|
| `gyro_bias` | lag | value |  | needs `tau_s` |
| `nav_solution` | algebraic | value |  | needs `command_value[0].selects`, `command_value[1].selects` |
| `attitude` | dynamics | edge |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `body_rate` | dynamics | edge |  | the edge has no sensitivity |
| `imu_platform` | dynamics | edge |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `imu_alignment` | discrete | rule |  | discrete rule: the alignment the platform drives once it has been started, trigger:request_imu_alignment |
| `maneuver_state` | discrete | rule |  | discrete rule: the maneuver lifecycle the guidance drives once the burn is loaded, trigger:load_burn |
| `nav_covariance` | dynamics | rule |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `nav_integrity` | discrete | rule |  | discrete rule: the ladder the covariance and the coast clock climb together |
| `orbital_state` | dynamics | rule |  | 6-DOF dynamics rule; the plant has only `dv/dt = F/m` |
| `radar` | algebraic | rule |  | algebraic rule (domain code) |

## rcs (11 of 13 blocked; WP03 evidence, then WP07 and WP05)

`thruster_thrust` is the dynamics root that blocks `prop_rcs_kg` in consumables too. The allocator (`thruster_valve`, `allocation_status`, `authority_margin`, `attitude_error`) is one piece of domain code: requested wrench → valve pattern → delivered impulse, and it needs the per-jet geometry and impulse (`domains/rcs/profiles.yaml` and `components.yaml` carry 24 and 14 `UNCONFIGURED`).

| state | class | owes | root | what |
|---|---|---|---|---|
| `allocation_status` | discrete | value |  | needs `hysteresis.assert`, `hysteresis.clear`, `hysteresis.dwell_ms` |
| `deadband_latch` | discrete | value |  | needs `hysteresis.assert`, `hysteresis.clear`, `hysteresis.dwell_ms` |
| `feed_pressure` | algebraic | value |  | needs `tank_volume_m3` |
| `pulse_width` | algebraic | value |  | needs `t_min_on_s` |
| `attitude_error` | algebraic | rule |  | algebraic rule (domain code) |
| `authority_margin` | algebraic | rule |  | algebraic rule (domain code) |
| `impulse_total` | stock | rule |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `pulse_residual` | stock | rule |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `safety_state` | discrete | rule |  | discrete rule: the ladder whose entry conditions are FDIR conclusions |
| `thruster_thrust` | dynamics | rule |  | 6-DOF dynamics rule; the plant has only `dv/dt = F/m` |
| `thruster_valve` | discrete | rule |  | discrete rule: the allocator commands each valve from the requested wrench |

## propulsion (6 of 10 blocked; WP03 evidence, then WP06 and WP07)

`E-PROP-ENG` declares `kg/s per N` and drives a lag in N, a units mismatch to fix in `coupling.yaml`. The feed and chamber lags have no driver until an engine sequence exists; `sps_burn_count` is a small discrete rule.

| state | class | owes | root | what |
|---|---|---|---|---|
| `feed_pressure_pct` | lag | value |  | needs `initial` |
| `pressurant_pressure_psi` | lag | value |  | needs `initial`, `provenance.basis` |
| `thrust_main_n` | lag | edge |  | edge units do not match the state (`advances:`/`reads:`) |
| `chamber_pressure_pct` | lag | rule |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `dps_throttle_pct` | lag | rule |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `sps_burn_count` | discrete | rule |  | discrete rule: the count of burns the engine has flown, incremented by the sequence |

## power (8 of 13 blocked; WP02 evidence, then WP04 and WP05)

The electrical solve (WP04) is `bus_a_v` and `bus_b_v`; `coolant_flow_kg_s` in thermal is blocked by `bus_a_v` too. `source_converter_v` needs an evidenced `tau_s` and `battery_usable_j_j` a derate curve with a basis (WP02). `lcl_tripped` and `load_shed_class` are the protection ladder (WP05).

| state | class | owes | root | what |
|---|---|---|---|---|
| `battery_thermal_state` | lag | value |  | needs `initial`, `tau_s` |
| `battery_usable_j_j` | algebraic | value |  | needs `derate_curve`, `provenance.basis` |
| `load_shed_class` | discrete | value |  | needs `band_value` |
| `source_converter_v` | lag | value |  | needs `tau_s` |
| `battery_charge_j` | stock | edge |  | the edge has no sensitivity |
| `bus_a_v` | algebraic | rule |  | algebraic rule (domain code) |
| `bus_b_v` | algebraic | rule |  | algebraic rule (domain code) |
| `lcl_tripped` | discrete | rule |  | discrete rule: the protection trips it and reports it on power |

## avionics (12 of 13 blocked; WP05 and WP09)

Mostly FDIR conclusions: votes, debounces, k-of-m innovation tests, time sync. All are discrete or algebraic domain code over other domains' states, so they land after those states advance, and most are also what WP09's instrument model reports on.

| state | class | owes | root | what |
|---|---|---|---|---|
| `innovation_window` | discrete | value |  | needs `band_on` |
| `instrumentation_power` | algebraic | value |  | needs `command_value[0].selects` |
| `sensor_health` | discrete | value |  | needs `band_on` |
| `compute_margin` | algebraic | edge |  | the edge has no sensitivity |
| `actuator_tracking` | discrete | rule |  | discrete rule: the shared tracking rule two domains need and neither owns |
| `bias_accumulator` | stock | rule |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `clock_offset` | algebraic | rule |  | algebraic rule (domain code) |
| `frame_sync` | discrete | rule |  | discrete rule: apollo's frame sync as the receiver reports it |
| `redundancy_vote` | discrete | rule |  | discrete rule: the majority vote's own verdict across a monitored group |
| `sample_age` | algebraic | rule |  | algebraic rule (domain code) |
| `sensor_bus_errors` | stock | rule |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `time_health` | discrete | rule |  | discrete rule: the verdict that gates an irreversible command, computed from time sync |

## comms (7 of 10 blocked; WP07 (geometry) and WP09)

`blackout` is a geometric occultation computed from the orbit, so it waits on WP07; `antenna_pointing` likewise. `carrier_lock`, `frame_loss` and `recorder` are the link model; `recorder` capacity is unset and matters if the bounded episode delivers data.

| state | class | owes | root | what |
|---|---|---|---|---|
| `link_snr` | algebraic | value |  | needs `command_value[1].selects` |
| `tx_power` | algebraic | value |  | needs `command_value[0].selects` |
| `antenna_pointing` | algebraic | rule |  | algebraic rule (domain code) |
| `blackout` | discrete | rule |  | discrete rule: the geometric occultation, computed from the orbit and the Earth's disc |
| `carrier_lock` | discrete | rule |  | discrete rule: the receiver's own statement that it holds the carrier |
| `frame_loss` | stock | rule |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `recorder` | stock | rule |  | nothing drives it: no inbound edge in `coupling.yaml` |

## crew (7 of 7 blocked; WP09 and the crew model (D-06))

Nothing advances. `crew_location` and `crew_availability` are moved by twelve commands and need the state machine; `crew_workload` reads the water edge with mismatched units; the alert lifecycle and horn are the caution-and-warning system. The perception bound in `plant.md` §8 needs the display contract `crew_diode.md:42` never supplied (conflict register D-06).

| state | class | owes | root | what |
|---|---|---|---|---|
| `breaker_panel` | discrete | value |  | needs `initial` |
| `crew_workload` | lag | value |  | needs `initial` |
| `alarm_horn` | discrete | rule |  | discrete rule: the audible half of the master alarm, driven by the lifecycle |
| `alert_lifecycle` | discrete | rule |  | discrete rule: the lifecycle the thresholds drive, which is why it is a state and not a channel |
| `crew_availability` | discrete | rule |  | discrete rule: moved by commands C, D, E, F, G, I, N, N, O, R, U, U |
| `crew_location` | discrete | rule |  | discrete rule: moved by commands C, D, E, F, G, I, N, N, O, R, U, U |
| `switch_panel` | discrete | rule |  | discrete rule: the crew throw them, and no verb writes a switch — which is what `controls |

## structure (5 of 10 blocked; WP05)

`pyro_fired`, `arm_state` and `docking_latch_state` are the irreversible-event machinery: the arm token's lifecycle and the mechanism's report. `hatch_state` only needs an `initial`.

| state | class | owes | root | what |
|---|---|---|---|---|
| `hatch_state` | discrete | value |  | needs `initial` |
| `arm_state` | discrete | rule |  | discrete rule: the token's own lifecycle: minted, then consumed by use or expired by time, trigger:arm_event |
| `docking_latch_state` | discrete | rule |  | discrete rule: the latch mechanism's own report: the verb drives the mechanism and the mechanism reports back, trigger:set_docking_latch |
| `pyro_fired` | discrete | rule |  | discrete rule: moved by event pyro_fire |
| `structural_leak_g_s` | algebraic | rule |  | algebraic rule (domain code) |

## thermal (8 of 24 blocked; WP02 evidence, then WP06)

The most complete domain. Five lags want `initial` and `lumped_mass_kg` (WP02 thermal node aggregation); `coolant_loop_t` and `zone_csm_avionics_t` wait on edge sensitivities; `heater_bank_duty` is a small algebraic rule.

| state | class | owes | root | what |
|---|---|---|---|---|
| `comm_amp_t` | lag | value |  | needs `initial` |
| `pump_1_speed_rpm` | lag | value |  | needs `initial`, `command_value[0].maps.on` |
| `zone_csm_avionics_t` | lag | value |  | needs `initial` |
| `zone_csm_service_t` | lag | value |  | needs `initial`, `lumped_mass_kg` |
| `zone_lm_descent_t` | lag | value |  | needs `initial`, `lumped_mass_kg` |
| `coolant_loop_t` | lag | edge |  | the edge has no sensitivity |
| `coolant_flow_kg_s` | lag | rule | `bus_a_v` | algebraic rule (domain code) |
| `heater_bank_duty` | algebraic | rule |  | algebraic rule (domain code) |

## eclss (8 of 17 blocked; WP02 evidence, then WP06)

Six stocks have no driver: the cabin gas and water stocks need their edges (crew metabolic flows read the crowded `crew_state` node and must name the state with `reads:`); `o2_supply_pressure_psi` needs `tau_s`.

| state | class | owes | root | what |
|---|---|---|---|---|
| `o2_supply_pressure_psi` | lag | value |  | needs `tau_s`, `provenance.basis` |
| `csm_cabin_co2_kg` | stock | edge |  | the edge reads a crowded node; needs `reads:` |
| `csm_cabin_h2o_kg` | stock | edge |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `csm_cabin_n2_kg` | stock | edge |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `lm_cabin_co2_kg` | stock | edge |  | the edge reads a crowded node; needs `reads:` |
| `lm_cabin_h2o_kg` | stock | edge |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `lm_cabin_n2_kg` | stock | edge |  | nothing drives it: no inbound edge in `coupling.yaml` |
| `suit_loop_flow_cfm` | lag | rule |  | nothing drives it: no inbound edge in `coupling.yaml` |

## consumables (4 of 10 blocked; WP02 evidence, then WP06)

`pressurant_he_kg` and `prop_main_kg` share `E-PRESS-PROP`, which has no sensitivity; `water_potable_kg` reads the crowded crew node; `prop_rcs_kg` is blocked by `rcs.thruster_thrust`.

| state | class | owes | root | what |
|---|---|---|---|---|
| `pressurant_he_kg` | stock | value |  | needs `min_flow_per_s` |
| `prop_main_kg` | stock | edge |  | the edge has no sensitivity |
| `water_potable_kg` | stock | edge |  | the edge reads a crowded node; needs `reads:` |
| `prop_rcs_kg` | stock | rule | `thruster_thrust` | 6-DOF dynamics rule; the plant has only `dv/dt = F/m` |

## The 195 unset scalars

`check_vehicle.py` lists 273 debts; 142 lines are `UNCONFIGURED` scalars (some lines cover several).
Where they sit, by file, with the count of debt lines:

| file | debts | what they mostly are |
|---|---:|---|
| `coupling.yaml` | 46 | edge sensitivities and minimum flows: the physical couplings WP02/WP03 must evidence |
| `vehicle.yaml` | 17 | mass properties and frame transforms per configuration (WP03) |
| `mission.yaml` | 9 | the initial state vector, entry corridor, contact schedule bases (WP03, WP07) |
| `channels.yaml` | 8 | open debts in prose: the `service` origin split, coverage notes |
| `domains/crew/*` | 11 | crew model parameters and points |
| `domains/rcs/*` | 12 | jet geometry, impulse, hysteresis bands |
| `domains/gnc/*` | 9 | sensor time constants, profiles |
| `domains/eclss/*`, `comms/*`, `thermal/*`, `structure/*`, `avionics/*`, `consumables/*`, `power/*` | 2–6 each | time constants, initial values, capacities |
| `presentation.yaml` | 6 | display mappings |

A value is closed only with its provenance (`vehicle/docs/evidence.md`); the debt count moves only
with a recorded reason (`vehicle/practice.md`).
