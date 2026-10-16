# 0004 — Interlock evaluation: evaluate what can be read, refuse what cannot

- Status: accepted (maintainer, narrowing ADR 0001 choice C for the bounded episode, D14); the
  operator items under §Operator items are decided by John (2026-10-16 20:41Z)
- Date: 2026-10-16
- Decision owner: vehicle maintainer, under D1 (`governance/decisions.md`) and open to the operator's
  revision
- Related work package / evidence gaps: WP05 (this is its interlock slice only, not the protection
  ladder); D14, `../vehicle-completion/09-quiet-coast-episode.md` §7 step 11 (in the root `docs/`)
- Reviewers and review evidence: `tests/test_interlocks.py`; the window run
  `aurora/tests/test_quiet_coast_window.py`
- Supersedes / superseded by: narrows [0001](0001-shared-executive.md) choice C

## Question and constraints

ADR 0001 choice C: "a command it cannot guard is a command it must not accept". Until now the
executive guarded nothing. It refused every verb that declares an interlock as INTERLOCK UNEVALUATED,
because threshold evaluation was WP05's. The quiet-coast episode is D14's acceptance, and it has to
run through the window. Its policies use `set_power_amplifier`, `set_evaporator_feed`,
`set_coolant_pump` and `set_load`, and all four declare interlocks. The batch runner applies scripted
effects with `plant.step` and never meets this gate. The window does. The question is which
interlocks the executive may now evaluate, and how, without inventing a band or a reading.

## Evidence and options

The chain is already declared. An interlock names a threshold in a domain's `profiles.yaml` (by its
id, or by its domain-qualified id). The threshold carries a `comparator`, an `assert` value and
`dwell_assert_ms`. It watches a point in `points.yaml`, and the point is a reading of a state, either
directly (same unit) or through an evaluable `derivation`. That is the same rule `emit_frame` uses to
publish a channel. The episode's interlocks resolve as follows:

| interlock | verb | threshold, point | readable |
|---|---|---|---|
| `power.bus_a_undervoltage` | set_power_amplifier | below 26.5 V, 500 ms; `power.dc_bus_a_v` ← `bus_a_v` | yes |
| `thermal.comm_amp_high` | set_power_amplifier | above 60 °C, 5 s; `thermal.comm_amp_c` (K → °C expression) | yes |
| `tx_power_high` | set_power_amplifier | `assert: UNCONFIGURED` (comms profiles) | **no: no band** |
| `power.load_margin_low` | set_power_amplifier | below 100 W; `power.load_margin_w`, an `estimate` over `[dc_bus_a_v, bus_a_current_a]` whose arithmetic is prose | **no: nothing computes it** |
| `coolant_supply_high` | set_evaporator_feed, set_coolant_pump | above 10 °C, 10 s; `thermal.coolant_supply_c` (expression) | yes |
| `res.cooling_water_reserve` | set_evaporator_feed | below 2.6 kg, 10 s; `res.water_cooling_kg` ← the stock | yes |
| `pump_no_flow` | set_coolant_pump | below 0.1 L/min, 4 s; `thermal.primary_flow_l_min` (expression) | yes |
| `lcl_overcurrent` | set_load | the template family `power.lcl_[n]_current_a`, 2 ms dwell inside a 20 ms tick | **no: a family, not a channel** |

`power.load_margin_w` declares `from: fuel_cell_power_w`, and its unit (W) matches, so `emit_frame`
publishes the cell's output under the margin's name. That is generation published as margin, a frame
defect this record names and does not fix.

Options considered: (a) keep refusing every interlocked verb, which blocks the episode at the
window; (b) evaluate the readable chains and keep refusing the rest; (c) give the unreadable ones
values. That would be a band or an arithmetic with no source, so (c) is the operator's question,
below.

## Decision

1. **Evaluate what can be read** (`plant.resolve_interlock`). An interlock is readable when its
   threshold resolves, its comparator is `above` or `below`, its `assert` is a number, its point is a
   registered channel (not a template family) read from a state, and the point is not an estimate
   with prose for arithmetic. The threshold must also be a level on that channel. A threshold says
   when it is not, in the two fields the linter's band check already reads as that statement. A
   `gated_by` condition is not data, so it is not evaluated. `point_units` whose leading unit (before
   the first `,` or `:`) is not the channel's own names another quantity: `tie_dv_limit` compares
   the difference between the buses against `power.dc_bus_a_v`, and a rate threshold compares a
   per-minute change against a level. Comparing the channel's level against either `assert` would
   guard the wrong quantity, so both stay unevaluated. The rule is conservative by construction: a
   spelling difference (`psid` against the channel's `psi`, for `cabin_dp_low`) also leaves a
   threshold unevaluated, and that refuses more, never less. The reading is `plant.point_reading`, which applies `emit_frame`'s three
   answers to one channel.
2. **The dwell is history in the truth.** At the end of every tick (`plant.step`), the plant advances
   `values["__interlock_dwell"][threshold]`: the consecutive ticks the reading has been past `assert`.
   It is reset to 0 inside the band or when there is no number. Every readable threshold some verb
   names is tracked (`plant.watched_interlocks`). The count is checkpointed and hashed with the rest
   of the truth, so a restart carries it and a replay of the record reproduces it. Nothing was added
   to the checkpoint, the record or the evaluator for this.
3. **Tripped** means count × tick ≥ the assert dwell, with count ≥ 1 (so a zero dwell trips after one
   tick past the band). `Executive.validate` refuses a verb with `INTERLOCK TRIPPED`, naming the
   interlock, its threshold and its point, and never the reading. This happens at acceptance and
   again at settlement, because `validate` is the revalidation too.
4. **Refuse what cannot be read.** If any declared interlock of a verb is unreadable, or has no
   reading this tick, the verb is refused `INTERLOCK UNEVALUATED` as before. The refusal lists only the
   unreadable interlocks, each with the first link of its chain that fails. This check comes before
   the tripped check: a command one of whose guards cannot be evaluated is not accepted.
5. **The operator's `--closed-interlock` still wins.** It closes the verb in the capability snapshot
   before any of this is asked.

Limitations, stated rather than modelled:
- The `clear` value, `dwell_clear_s` and `latched` are not evaluated. A threshold trips while its
  reading has been past `assert` for the dwell, and stops tripping when the reading returns inside
  `assert`. It does not wait for `clear` and does not latch. That is the protection ladder's
  behaviour (WP05 proper).
- At MET 0 there is no history, so nothing is tripped on the first validation, even for a reading
  already past its band.
- `pump_no_flow`'s note says it is "evaluated only while the pump is commanded on". That condition
  is prose in `point_units` (`L/min, evaluated only while ...`), not a `gated_by` field, so the
  threshold is evaluated unconditionally. That direction is safe: a condition on when a threshold
  applies can only narrow when it trips, so ignoring it refuses more, never less. The cost is that a
  stopped pump's zero flow trips it after 4 s, and `set_coolant_pump` is then refused, so restarting
  a stopped pump through the window is blocked. No policy in the episode restarts one. The condition
  is owed as a declared field.

## Operator items (decided by John, 2026-10-16 20:41Z)

The episode's verbs that stay refused under the decision above, and the answer for each, as John
chose them ("Chosen values", 2026-10-16 20:41Z). Each is a `chosen` value or a structural change,
not evidence. They are implemented in their own commit on top of the decision, which stands without
them.

1. **`power.load_margin_w` becomes an evaluable expression** (`domains/power/points.yaml`): the rated
   output of the two fuel-cell modules on main bus A less the bus's load,
   `fc_1.rated_w + fc_2.rated_w - bus_a_load_w`. `rated_w` is 1,420 W per module, the top of the AOH
   p. 2.6-2 normal envelope (WP02 E-1), and the routing is the flown normal one (TN D-7609 p. 5).
   It reads from `bus_a_load_w` instead of `fuel_cell_power_w`, so the frame stops publishing the
   cells' output under the margin's name: the same edit fixes the frame defect above, and cannot be
   split from it. What it omits: a module's capacity above its normal envelope, a failed or switched
   module (the routing is static), and bus B. `domains/power/components.yaml#fuel_cell_power_w`'s note speaks
   of "three 1,420 W modules against this figure", a whole-vehicle margin; the interlock's inputs
   were bus A's, and this follows them.
2. **`tx_power_high` gets `assert: 108`** (`domains/comms/profiles.yaml`, `assert_provenance.basis:
   chosen`): one constant ceiling at the chain's highest configured DC input, the sourced 36 W
   transceiver plus 72 W amplifier as the inventory and `tx_power`'s rule read them. A ceiling at
   72 W would trip 2 s after the amplifier came on under that reading and then refuse turning it
   off, so 72 W is the ceiling only if the open question resolves the other way: whether
   apollo_diode.md:157's 72 W already includes the transceiver. The threshold's note still asks
   for a limit per transmitter and mode; a constant is the narrower guard. `point_units` now opens
   with the channel's unit, because the comparison is against the channel's level. `clear` stays
   owed. The model never draws above 108 W (no hot-amplifier draw yet), so in this model the
   guard never trips. Found on the way: `comm.tx_power_w`'s registry range is [0, 100] W, and the
   chain reads 108 W with the amplifier on.
3. **`set_load` declares no interlock** (`domains/power/commands.yaml`). Its `lcl_overcurrent`
   watches a per-load current-limiting switch that is this model's choice, not Apollo's
   (`components.yaml#lcl`: "Apollo had mechanical breakers plus the PDU"), on a template family
   with a 2 ms dwell inside a 20 ms tick, so the verb could never be guarded. ADR 0003 left the bus
   tie and the load-shed ladder, which have no Apollo automatic counterpart, outside the episode;
   this follows that precedent. `set_breaker` keeps the interlock.

With the three, `set_power_amplifier` and `set_load` are evaluated, and policies A, B and C reach
their batch classes through the window (`aurora/tests/test_quiet_coast_window.py`).

## Acceptance and consequences

- `tests/test_interlocks.py`: the episode's interlocks resolve, or name the link that fails, as in the
  table. The count advances only while the reading is past the band, trips exactly at the dwell, and
  is part of the state hash. A readable interlock inside its band lets the command through. A tripped
  one refuses by name with no value. One unreadable interlock refuses the verb as unevaluated. An
  operator's closed interlock still wins.
- `aurora/tests/test_quiet_coast_window.py`: through the real executive, with a SIGKILL and a resume,
  every tick of the record replays to its hash. That includes the dwell counts. Policy D reaches its
  physical loss of the coolant loop. Without the operator items, policy A is a `timeout` there,
  because `set_power_amplifier` is refused unevaluated; with them, A and B are `full_success` and C `partial`.
- The referee's tests that asserted the old "has a reading this tick ... not implemented in this slice
  (WP05)" sentence (`set_bus_tie`'s `tie_dv_limit`, `set_relief_valve`'s `cabin_dp_low`) now assert
  the link this decision names: a difference between buses, and `psid` against `psi`. The arm and
  fire refusals list only the unreadable interlocks, which for both verbs is all of them.
