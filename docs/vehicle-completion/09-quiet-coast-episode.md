# The quiet-coast episode: F0 feasibility and design

As of **2026-10-15**, on `main` @ `8bc4836`. This is step **F0** of
`docs/plans/2026-10-04-vehicle-to-green-programme.md` (§7 and §10 item 3), the bounded episode of
`governance/decisions.md` D14, and the episode D22's smoke and coordination tests run on. It is a
design and a scoping pass. It writes no vehicle code and fills no YAML. Every status below comes
from `python3 tools/plant.py --readiness`, `--build-order`, `--apply` and
`python3 tools/check_vehicle.py --debts` run on that commit. Re-run them before relying on a row.

## Verdict

**F0 exits blocked, with an episode designed and ready to build once five inputs are settled.**
The command → physics → completion path exists in part, and the parts it lacks are named below.
The one finding that changes the programme's framing is this. **On the configured vehicle, a
tens-of-minutes coast in translunar flight is not short of power or cryogenics.** The three fuel
cells are rated at 4,260 W against a 1,723 W load, and they carry 279 kg of O2 against a draw of
0.69 kg/h. Over an interval that short, the only resource that can actually run short is **heat
rejection**: radiator capacity against absorbed sunlight, with the glycol evaporator's water as the
price of any excess. So the episode is a **cooling-margin episode with power as the load path**,
and its productive task carries a deadline. Which form of scarcity to accept is blocker **B1**.

| question | decision (section) |
|---|---|
| productive activity | **stored-data delivery**: play back the CSM recorder over the high-gain S-band link before a deadline, using a minimal task model that this document specifies (§1) |
| interval | `translunar_coast`, starting at **MET 0 / tick 0** from `mission.yaml#launch_state`, lasting **40 min = 120,000 ticks** (§2) |
| environment | a declared constant **sun-on-radiator hold**: `environment_heat_w` = 2,477 W, already derived in the configuration. There is no attitude dynamics (§2, §4) |
| scarcity | evaporator headroom (2,345 W capacity, of which about 1,160–1,620 W is already spent at baseline) and cooling water (§3) |
| evaluator | a vehicle-side tool that reads private state and the per-tick truth trace and writes a neutral outcome record that the chassis consumes (§6) |
| blockers for John | B1–B5 (§8) |

## 1. The productive activity

Three candidates, judged against the configuration as it stands:

| candidate | command path today | physical cost | completion measure | verdict |
|---|---|---|---|---|
| **Stored-data playback** (CSM recorder dump at high bit rate) | `set_comm_mode`, `select_antenna` and `set_telemetry_profile` **already move state** (`--apply`: `comm_mode`, `antenna_selection`, `telemetry_rate` 1,600 → 51,200). `set_power_amplifier` is refused because `tx_power.command_value.selects` is owed. There is **no playback verb** | power amplifier +36 W on the bus (the transceiver's 36 W rises to 72 W), heat into `comm_amp_t` and the coldplate | delivered bits, integrated from per-tick truth | **chosen**. It is the activity the plan names, it is a real Apollo practice (record, then dump over the high-gain antenna, `apollo_diode.md:903`), and it is the only domain whose verbs already reach the plant |
| Entry-battery recharge | `set_battery_contactor` writes no state, there is no charger verb, and `E-BUS-BAT` owes its value (floor 0.94) | the charger's load on the fuel cells, extra O2/H2, heat | `battery_charge_j` reaching a target | **alternative secondary** (B1 option b). A real in-flight activity: Apollo 14 charged entry batteries A and B five times in flight (A14 Mission Report §7.2.3). The charger's rating was not found |
| Invented task load ("experiment draws X W") | none | whatever is chosen | a counter | **rejected**. This is the busywork the plan forbids |

**The minimal task model to add** (domain `comms`, per D5):

| element | form | status / source |
|---|---|---|
| `recorder` stock, in **bits** rather than % | an existing stock (`domains/comms/components.yaml` `state recorder`) re-denominated; `comm.recorder_fill_pct` derived from it over `capacity` | capacity UNCONFIGURED (`components[5].capacity`). The episode needs only **capacity ≥ D**, so the capacity can stay owed if B2's bound is accepted |
| episode preload `D` | a scenario initial condition (bits on tape at MET 0) | a **task declaration**, provenance `chosen`. A data volume is the mission's demand, not physics |
| `play_recorder` verb, `{state: play\|stop}`, A1, declarative | new in `domains/comms/commands.yaml` | Apollo had tape-recorder play and record controls (crew panel and up-telemetry); the exact switch needs a source (B2) |
| playback drain rule | `d(recorder)/dt = −r_play · link_ok` while playing; `r_play` = 51,200 bit/s (`telemetry_rate` high, `apollo_diode.md:165`) | the playback rate was **not found** in this pass (B2) |
| `link_ok` predicate | `comm_mode = sband_high ∧ antenna_selection = high_gain ∧ transmitter_on[sband_power_amplifier] ∧ ¬blackout` | stands in for the unconfigured link budget (`link_snr` owes a value). Translunar coast is outside `comms_blackout.phases_affected` (`mission.yaml:572`). This is B3 |
| `delivered_bits` stock (ground-received) | new, private (`not_published`), fed by the drain one for one (WP10 conserved: recorder + delivered = D) | the completion oracle |

## 2. The mission interval

| parameter | value | reason |
|---|---|---|
| phase | `translunar_coast` | engines off, guidance in coast, no occultation, docked stack (`mission.yaml:289`) |
| start | **MET 0, tick 0** | the **only** documented initial state (`mission.yaml#launch_state`, Apollo 17 checklist pp. 33–59). Any later start needs a second sourced initial condition |
| duration | **40 min = 2,400 s = 120,000 ticks** at 50 Hz | about 6 coldplate time constants (τ 406 s), 8 radiator (τ 300 s) and 9 comm-amp (τ 265 s), so delayed thermal costs land inside the interval. It covers less than one cabin τ (2,880 s), so the cabin is a slow margin and not the loss path |
| contact deadline | MET 40 min, the prescribed end of the hot hold (return to passive thermal control) | an explicit boundary, not an orbit claim |
| environment | `environment_heat_w` held at 2,477 W (1,361 W/m² × 0.2 × 9.1 m², `domains/thermal/components.yaml` `radiator_model.environment`) | a declared sun-on-radiator hold. Rejected alternative: a passive-thermal-control average, whose absorbed load is owed (B4) |

**Time cost.** The plant measures 3,751 µs/tick at 53 advancing states (`--mission --ticks 3000`).
A scripted run is therefore about **450 s of wall time (7.5 min), roughly 5× faster than real
time**, in the batch mode (`plant.py --mission`, ADR 0002 policy A3). It will slow as the states in
§3 start to advance (`05-performance.md`). Driven through the window at `m = 1` (ADR 0002 A2), the
episode takes 40 min of wall time. D22's 10-min smoke test sees the first quarter of it, and the
60-min coordination test covers all of it. Running scripted policies through the window at `m > 1`
depends on the clock seam (`#23`, PR #9). It is not needed: CI runs the batch mode, and the window
run proves the transport.

## 3. Causal closure

The loop the episode must close: **command → load enable → bus load → fuel-cell output → O2/H2
draw; load → zone heat → loop load → radiator + evaporator → coolant temperature → coldplate and
amplifier temperature → thresholds and interlocks; evaporator duty → cooling water.**

Status key: **ready** = a tick advances it today; **value / edge / rule** = the `--build-order`
bucket; **new** = does not exist yet; **wrong** = advances, but with a defect this pass found.

### Power

| element | where | status | missing input | evidence lead |
|---|---|---|---|---|
| `set_load` → load on/off | `domains/power/commands.yaml:94` | **no state** (`--apply`: 0 values changed) | a `load_enabled` map state keyed by load id, with initial positions at MET 0 | Apollo 17 CSM Launch Checklist pp. 33–59 (positions after extraction); `mission.yaml#launch_state` already cites it |
| `bus_a_load_w` | power, algebraic | ready, but a **constant** sum of all 14 `demand_w` | rule: the sum over *enabled* loads | none needed |
| `fuel_cell_power_w` | power, algebraic | ready (equals load) | none for the episode; module min/max | **conflict**: TN D-7142 gives 563–1,420 W per module; the J-Mission EPS handout p. 2.6-2 gives "400 to 1420 watts" |
| `fc_o2_draw_kg_s`, `fc_h2_draw_kg_s` | power | ready | none | **independent oracle found**: J-Mission EPS handout p. 2.6-21 gives O2 = 2.04e-2·I lb/h and H2 = 2.57e-3·I lb/h. At 1,723 W / 29 V = 59.4 A this is 1.527e-4 and 1.924e-5 kg/s, matching the configuration to four figures |
| `o2_csm_kg`, `h2_csm_kg` | consumables, stock | ready | none | A14 MR §7.10.3 as the flight-level check |
| `source_converter_v` | power, lag | **value** (`tau_s`) | converter time constant | not needed if the bus is solved algebraically from the cell V–I curve (WP04 decision) |
| `bus_a_v`, `bus_b_v` | power, algebraic | **rule** | source internal resistance (bounded ≤ 1.25e-3 V/W, `coupling.yaml` open_debts) | fuel-cell polarization curve: AOH CSM Vol 1 §2.6 and the J-Mission EPS handout Fig. 2.6-7, which is graphical. **Not read in this pass**: the AOH PDF fetch failed, and the handout's figure did not extract |
| `load_shed_class` | power, discrete | **value** (`band_value`, the missing P1 rung) | a rung-to-class map (decision) | not exercised (§4): at 4,260 W of capacity the bus does not sag below 26.5 V |
| `battery_charge_j`, `E-BUS-BAT` | power, stock | **edge** | charge efficiency (floor 0.94) and charger rating | only for B1(b). Entry battery: 40 Ah, 37.1 V open-circuit, 28 V at 25 A (J-Mission EPS pp. 2.6-18/19). Charger: "solid state device … dc from the fuel cells and ac from an inverter" (p. 2.6-4), **no rating found** |
| `E-AMP-LOAD` | link → bus_a | edge closed (0.0357 A/W) | `tx_power` must advance | the amplifier is **double-counted**: it is also `loads.csm_sband_power_amplifier` (72 W), so one of the two must be its only source |

### Comms (the task)

| element | status | missing input | evidence lead |
|---|---|---|---|
| `comm_mode`, `antenna_selection`, `telemetry_rate` | ready, and moved by commands | `telemetry_rate` maps for emergency, normal and burst (not used) | none |
| `tx_power` (`set_power_amplifier`) | **value** (`selects`) | `transmitter_on` keyed state | none: a state declaration |
| `recorder` | **rule** (stock on the sentinel) | capacity (B2), playback rule, task model (§1) | DSE capacity and playback rate **not found**. TN D-7598 p. 7 gives only "14 tracks on 1-inch tape at 15 in/sec" (development flight instrumentation recorders, not the block II DSE), and TN D-7684 p. 2 says only that "the CSM could record data for later transmission". Next: CSM/LM Systems Handbook telecom section; AOH Vol 1 §2.8 |
| `link_snr`, `carrier_lock`, `blackout` | value / rule / rule | link budget constants; occultation rule | replaced in the episode by the `link_ok` predicate (B3); `blackout` held `clear` (outside the affected phases) |
| `comm_amp_t` | **value** (`initial`) | initial temperature; **inconsistency**: sized for 250 W of dissipation (G 17 W/K) while the amplifier's input is 72 W | amplifier efficiency (11.2 W RF / 72 W in, NR ch. 18). Re-derive G or the dissipation |

### Thermal

| element | status | missing input | evidence lead |
|---|---|---|---|
| `cabin_heat_csm_w`, `service_bay_heat_w`, `avionics_bay_heat_w`, `loop_primary_load_w` | ready, but **constant** derivations over `demand_w` | rule: sum over enabled loads, so a shed load stops heating in the same tick, as their own notes promise | none |
| `environment_heat_w` | ready (2,477 W) | none for a hot hold. The passive-thermal-control average is owed (B4) | radiator absorbed-heat analysis; TN D-6718 is the first place to look |
| `radiator_eq_t`, `zone_radiator_t`, `radiator_rejection_w` | ready, **wrong for this use** | the radiator settles at 322 K while rejecting the whole 1,723 W load *and* `E-WATER-RAD` drains water for the same 1,723 W. That double-counts, and the panel is 25 K hotter than the loop's declared 22.8–23.9 °C radiator inlet | rule: rejection evaluated at the loop's temperature (`E-RAD-THERM`'s owed "rejection law") |
| evaporator duty | **new** (`evaporator_csm` has `rejection_w: 2345`, NR, and no state) | rule: `duty = clamp(load − radiator_net, 0, 2,345 W)` while `set_evaporator_feed` is on (that verb writes no state today), plus the outlet setpoint at which it activates | AOH Vol 1 ECS section (evaporator outlet-temperature control). Setpoint **not found** in this pass |
| `water_cooling_kg`, `E-WATER-RAD` | ready, **wrong**: it drains 1/2.45e6 kg/s for every watt the *radiator* rejects. That is 2.53 kg/h at baseline, and 13 kg runs out in 5.1 h | read the evaporator duty, not `radiator_rejection_w` | **historical oracle**: Apollo 14 evaporated **9.0 lb (4.1 kg) in the whole flight** (A14 MR §7.10.4), two orders of magnitude below the configured drain |
| `coolant_loop_t` | **edge** (`E-PUMP-COOL` value) | loop heat balance (supply ← return − rejection) | derived from published flow (200 lb/h) and the loop's own c_p (3,626.1 J/kg·K) |
| `coolant_flow_kg_s`, `pump_1_speed_rpm` | rule / value (`maps.on`, rated rpm) | pump on/off rule; rated speed | the episode can treat flow as published (200 lb/h) when the pump is on and zero when it is off, leaving rpm owed |
| `loop_transport_t` | ready (delay 1,042 s) | none | — |
| `zone_csm_avionics_t` (coldplate) | **value** (`initial`) | initial temperature | B5: a derived equilibrium, the same idiom as `zone_radiator_t` |
| `zone_csm_cabin_t` | ready | none (slow margin) | — |
| `zone_csm_service_t` | **value** (`initial`, `lumped_mass_kg`) | both | scope it out (held) unless the service-bay load is shed by policy |
| `E-STRUCT-PLATE` (regime `docked`) | **edge** | the docked offset | the coldplate needs a driver: the loop heat balance replaces this for the episode |

### Consumables and ECLSS (riding along, not task-coupled)

| element | status | note |
|---|---|---|
| `csm_cabin_o2_kg`, `cabin_o2_supply_csm_kg_s`, `csm_cabin_pressure_pa`, `absorber_man_hours_csm` | ready | depletion continues ("silence cannot freeze depletion") |
| `csm_cabin_co2_kg`, `csm_cabin_h2o_kg`, `csm_cabin_n2_kg` | **edge** (the crew driver is `None`, `E-CREW-ATM`) | held for the episode. The crew count edge (`reads:` vs a count state) is WP06's decision |
| `water_potable_kg` (`E-FC-WATER`) | **edge** | the fuel cells' product water. Optional; held |

## 4. Scope exclusions and how they behave

| excluded | states | behaviour during the episode |
|---|---|---|
| attitude, navigation, orbit | `gnc.*`, `attitude`, `body_rate`, `imu_platform`, `antenna_pointing` | **held** at initial or last value; `orbital_state` coasts (WP07 slice 1). `point_hga` is accepted and changes nothing in the predicate |
| propulsion and RCS | `propulsion.*`, `rcs.*`, `prop_*`, `pressurant_he_kg` | held; `start_burn` and RCS verbs **refused** by an episode verb allow-list (a scenario gate variable set false) |
| faults | all 128 | none injected (`nominal` posture, seed fixed) |
| LM | `zone_lm_*`, `lm_cabin_*`, `o2_lm_kg`, LM loads | held; the LM is unpowered cargo in translunar coast |
| load shed ladder and LCL | `load_shed_class`, `lcl_tripped`, `bus_tie_closed` | reported. A shed or trip is an **apparatus failure** unless a rule exists, because the ladder is unbuilt |
| crew | `crew_*`, `alert_lifecycle` | held; ask_crew stub |
| comms beyond the predicate | `link_snr`, `frame_loss`, `carrier_lock` | held; omitted from the evaluator |
| batteries | `battery_charge_j`, `battery_usable_j_j`, `battery_thermal_state` | held unless B1(b) |

## 5. Objective, thresholds and policies

**Declared objective** (written into a scenario file and frozen before any trial; the figures in
brackets are set by the feasibility run on the built rules, never tuned per policy):

| item | definition | judged on |
|---|---|---|
| **M: mandatory** | `delivered_bits ≥ D₁` by MET 40 min | private truth |
| **S: secondary** | `delivered_bits ≥ D₁ + D₂` by MET 40 min (an optional second data block; or recharge, if B1(b)) | private truth |
| power margin | `bus_a_v ≥ 27.0 V` every tick (`csm_bus_a.v_band`); no shed, no LCL trip | per-tick truth |
| thermal margin | coldplate `< 50 °C` (`avionics_plate_high`); comm amp `< 60 °C` (`comm_amp_high`); coolant supply `< 10 °C` (`coolant_supply_high`); cabin within 10–30 °C | per-tick truth |
| consumables margin | `water_cooling_kg ≥ [W_min]` at MET 40 min; `o2_csm_kg`, `h2_csm_kg` above their 20 % reserves (55.8 kg, 4.9 kg) | end-state truth |
| loss | any thermal limit exceeded for more than its declared dwell, `water_cooling_kg` = 0 with evaporator demand, or bus below 26.5 V | per-tick truth |

**Policies** (scripted command sequences written as files through the window from the operator
side; the verbs come from `commands.yaml`):

| policy | sequence | intended trajectory | expected class |
|---|---|---|---|
| **A: bursts** | at t₀: `set_comm_mode sband_high`, `select_antenna high_gain`, `set_power_amplifier on`, `set_telemetry_profile high`, `set_evaporator_feed csm on`, `play_recorder play`. Run until D₁ + D₂ are delivered, then `set_power_amplifier off`, `play_recorder stop`, `set_comm_mode sband_low` | short, high load; high evaporator duty early; most water spent early | full success |
| **B: spread and shed** | first `set_load csm_lighting off`, `set_load csm_comm_heaters off`, `set_heater … duty=<lower>` to buy evaporator headroom, then the same link setup, playing in two windows separated by a cool-down | lower peak heat; coldplate and amplifier peaks lower; finishes later | full success, by a distinct trajectory |
| **C: over-conservative** | sheds as B and plays only D₁ (or keeps `sband_low` too long) | margins large | partial (M met, S missed) |
| **D: poor** | everything on and `set_coolant_pump pump_1 off` to "save power" (or `set_evaporator_feed off` in the hot hold), then plays | loss of flow or loss of evaporator → coolant supply rises → coldplate over 50 °C | **physical loss**, explained by the per-tick chain (pump → flow → supply → plate) |

**Feasibility condition (B1).** With the radiator net at 99–559 W (at 285–297 K), the evaporator
carries **1,160–1,620 W** of the 1,723 W baseline, which leaves **720–1,180 W** of headroom and a
water cost of **1.7–2.4 kg/h**. The task's own marginal load is **+36 W** (the amplifier step), so
A and B differ through the **discretionary loads** each sheds, not through the task. That is a real
trade, but the task does not drive it. If the built rules show A and B are indistinguishable in
margin, the episode does not meet §7's contrast without B1(b), (c) or (d). Rule from the plan:
never tune physics to make them differ.

## 6. The evaluator

| reads | never reads |
|---|---|
| the vehicle's private `/state` (checkpoints, the protected lifecycle journal and record) and a per-tick truth trace `(tick, state hash, the episode states in §3)` written by the executive on the vehicle's own image | `pending.json`, result files, receipts, `state.json`/frames as published to agents, agent transcripts or claims |

It is **vehicle-side** (`vehicle/tools/episode_eval.py`, stdlib plus PyYAML, wired into nothing),
because only the vehicle may hold vehicle semantics. It writes one **neutral outcome record**
(`{episode, vehicle_sha, scenario_sha, policy_id, class, objective_results, margins_min, first_violation, ticks, trace_hash}`)
that the chassis consumes without interpreting.

| outcome class | rule |
|---|---|
| **full success** | M and S met, no margin violated, run complete |
| **partial** | M met, S missed, no margin violated |
| **physical loss** | a loss condition in §5 reached; the record names the first violating state, the tick, and the chain of upstream states that moved first |
| **timeout** | MET 40 min reached with M unmet and no loss |
| **apparatus failure** | the trace is missing or torn, a determinism hash mismatches on replay, a state outside scope moves, a held state is written, a shed or trip occurs with no rule, a refused verb is applied, or wall-clock overload or pause invalidates the run (ADR 0002) |

Mutation and negative controls: the evaluator must classify a doctored trace (one tick's
`water_cooling_kg` edited, a forged result file claiming delivery, a policy D trace relabelled A)
as apparatus failure or as its true class.

## 7. Work list in dependency order

| # | where (D5) | work | blocked by |
|---|---|---|---|
| 1 | `tools/plant.py` | the D5 rule registry (rule = pure function of the snapshot, registered by state id); keyed-map discrete states; a **scenario overlay** (initial-condition overrides and an episode verb allow-list); scripted effects keyed by tick for batch mode | the PR #9 clock-seam files (do not collide) |
| 2 | `domains/power/` | `load_enabled` state, its initial positions, and the `set_load` mover; `bus_a_load_w` rule over enabled loads; one home for the amplifier's watts | MET-0 load positions (research, checklist) |
| 3 | `domains/thermal/` | heat-rate states summed over enabled loads; loop heat balance (`coolant_loop_t`, `E-PUMP-COOL`); radiator rejection at loop temperature (`E-RAD-THERM`); pump on/off → flow | B5 initials |
| 4 | `domains/thermal/` | evaporator state, its feed command and duty rule; **fix `E-WATER-RAD` to read the evaporator duty** (and `E-RAD-WATER`'s clamp to the evaporator) | evaporator setpoint (research) |
| 5 | `domains/comms/` | `transmitter_on` state; `tx_power` rule; `comm_amp_t` dissipation fix; recorder in bits, `play_recorder`, `delivered_bits`, `link_ok` | B2, B3 |
| 6 | `domains/power/` | `bus_a_v` algebraic solve (cell EMF − R·I) | fuel-cell V–I (power evidence worker); bounded at ≤ 1.25e-3 V/W |
| 7 | `tools/` (WP10) | conservation ledgers per stock below; energy trend | 2–5 |
| 8 | `scenarios/quiet_coast.yaml` | objective, frozen thresholds, `D₁`, `D₂`, `W_min`, environment boundary, policy files A–D | a feasibility run on 1–7 |
| 9 | `vehicle/tools/episode_eval.py` | §6 | 8 |
| 10 | `vehicle/tests/test_quiet_coast.py` | batch run of A–D at 120,000 ticks (about 7.5 min, opt-in marker), classes asserted, controls; **restart check** | 9 |
| 11 | `aurora/scripts/episode_driver.py` (stdlib) | writes policy command files to `/diode/<slug>/` keyed on `state.json` MET; `aurora/live/test_quiet_coast.py` on `SmokeStack(window="vehicle")` runs policy A, collects the neutral outcome record and asserts its class | Phase B image; a mount for the outcome record (operator-readable, agent-unreadable) |

**Conservation stocks (WP10).** O2 (`o2_csm_kg` + cabin O2 + cumulative draws = load at MET 0),
H2, cooling water (stock + cumulative evaporator draw), electrical energy (fuel-cell output =
∫ load), and data (`recorder` + `delivered_bits` = D). Each is checked per tick to its quantum.

**Restart mid-episode.** Policy A runs in batch to tick 60,000, the vehicle is checkpointed and
the process killed. A fresh process restores, finishes, and must produce the **same per-tick hash
sequence** and the same outcome record as the uninterrupted run (`plant.md` §6; ADR 0002). A
window variant does the same with `SmokeStack` `recreate()` of the vehicle service.

## 8. Blockers that need John

Each follows `08-risks.md`'s first row: when no applicable source exists, accept a `chosen`
approximation with a stated bound, narrow the objective, or leave the state out.

| id | blocker | options | recommendation |
|---|---|---|---|
| **B1** | **The task does not create the scarcity.** Over ≤ 60 min in translunar coast, power and cryogenics cannot bind (4,260 W rated against 1,723 W; O2 0.69 kg/h of 279 kg). Only cooling binds, and only under a hot hold. The data task adds 36 W | (a) accept a cooling-margin episode with data as the deadline, where A/B differ by load shedding; (b) add the entry-battery recharge as the secondary objective (a real load; the charger rating is owed); (c) a multi-hour interval so water binds (CI ≈ 1 h of wall time at 5×); (d) defer to an LM-on-battery episode (lunar orbit; needs a second initial state) | **(a), and (b) if the charger rating is found** |
| **B2** | DSE recorder capacity, playback rate and playback control **not found** in this pass | (a) declare `D₁ + D₂` as a `chosen` task volume with an explicit bound that it is below the recorder's capacity (unknown), and the playback rate = the published 51.2 kbit/s; (b) keep searching (Systems Handbook / AOH telecom) | (a) now, while (b) continues |
| **B3** | No link budget: high-bit-rate link availability is not computable | (a) accept the `link_ok` predicate as an episode boundary (`chosen`, documented); (b) wait for the link budget (receiver threshold, range loss) | (a) |
| **B4** | Environment: a sun-on-radiator hold is a worst case (normal incidence on 9.1 m²); passive-thermal-control absorbed load is owed | (a) accept the constant hot hold as the declared boundary; (b) a two-mode schedule once the passive-thermal-control value is sourced | (a) |
| **B5** | MET-0 temperatures of the coldplate and comm amp (and the service bay) are unpublished | (a) start at the model's own derived equilibrium (the `zone_radiator_t` idiom), stated as such; (b) scope the zone out | (a). This is arguably the vehicle's own call under `evidence.md` (derived) and is listed so it is not mistaken for data |

**Research, not decisions** (the parallel evidence workers): fuel-cell V–I curve and internal
resistance; evaporator activation setpoint; MET-0 load and breaker positions (Apollo 17 checklist);
the battery charger rating; the TN D-7142 / J-Mission handout module-minimum conflict (563 W vs
400 W).

## 9. Evidence pass (scoping only)

| question | found | source, page | not found / next |
|---|---|---|---|
| cryo O2/H2 per amp | **yes**: O2 2.04e-2·I lb/h, H2 2.57e-3·I lb/h; matches the configuration at 29 V | *J Mission Electrical Power System* (Oct 1971), p. 2.6-21 (ibiblio `J Mission Electrical Power System Oct 1971.pdf`) | — |
| entry battery | 40 Ah min, 37.1 V open-circuit, 28 V at 25 A, 27 V min | same, pp. 2.6-18/19 | charge acceptance; charger rating (p. 2.6-4 describes the charger, gives no figures) |
| fuel-cell module range | "400 to 1420 watts" | same, p. 2.6-2 (OCR damaged around the voltages) | V–I curve (Fig. 2.6-7, graphical, not extracted); AOH CSM Vol 1 fetch failed |
| fuel-cell flight average | 435 kWh, average 23 A per cell, mean bus 29 V | Apollo 14 Mission Report §7.2.2 | — |
| in-flight battery charging | entry batteries A and B each charged 5 times in flight | Apollo 14 Mission Report §7.2.3 | durations and amp-hours |
| evaporator water | 9.0 lb evaporated before CM/SM separation | Apollo 14 Mission Report §7.10.4 | activation setpoint |
| DSE | none for block II | TN D-7598 p. 7 (14-track, 1-inch tape at 15 in/s, development instrumentation); TN D-7684 p. 2 | capacity and playback rate |
| fuel-cell lab V–I | single-cell lab data only, not applicable | TN D-5154 (Lewis), pp. 11–13 | — |
| thermal masses, conductances, radiator | not searched (thermal worker) | — | — |
