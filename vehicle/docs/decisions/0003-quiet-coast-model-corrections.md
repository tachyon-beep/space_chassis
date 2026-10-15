# 0003 — Model corrections for the quiet-coast episode

- Status: accepted (maintainer items); operator items proposed, awaiting John
- Date: 2026-10-15
- Decision owner: vehicle maintainer for §Decision 1–5, under D1 (`governance/decisions.md`) and open
  to the operator's revision; the operator for §Decision 6–11 (scope and evidence standard)
- Related work package / evidence gaps: WP02, WP04, WP06; the bounded episode (D14);
  `../vehicle-completion/09-quiet-coast-episode.md` (in the root `docs/`)
- Reviewers and review evidence: the WP02 evidence records `docs/evidence/wp02-electrical.md` and
  `docs/evidence/wp02-thermal-eclss-consumables.md`
- Supersedes / superseded by: —

## Question and constraints

The quiet-coast episode exercises the electrical, thermal, consumables and comms paths of the CSM in
translunar coast. The WP02 research found that parts of the configured model have no Apollo
counterpart, or contradict the primary sources, in ways that are not missing values but wrong
structure. This record settles which structure the episode's rules implement. Values still come only
from the evidence records; nothing here introduces a number.

## Evidence and options

| # | finding | source |
|---|---|---|
| 1 | Apollo had no source converter: the fuel cells connect to the main buses through motor switches; `source_converter_v`'s `tau_s` has no counterpart (the corpus's "< 10 ms" at `electrical_diode.md:248` is a reference-design target) | AOH SM2A-03-Block II-(1) pp. 2.6-2, 2.6-25; `wp02-electrical.md` E-5 |
| 2 | Fuel cells 1 and 2 feed main bus A, fuel cell 3 feeds main bus B; Apollo put about two thirds of the load on the two-cell bus. The configured split (598 W A / 1,125 W B) puts bus A above its 31 V ceiling on the first tick | TN D-7609 p. 5; Apollo 15 MR §6.2; `wp02-electrical.md` |
| 3 | Reactant consumption is published per ampere (O2 2.04e-2, H2 2.57e-3, water 2.297e-2 lb/h per A); the model charges per watt at a fixed 29 V and undercounts by 7 % at 27 V | J-Mission EPS handout (Oct 1971) p. 2.6-21 |
| 4 | No rated glycol-pump speed was found; the loop flow (200 lb/h) is published | TN D-6718; `wp02-thermal-eclss-consumables.md` |
| 5 | `E-WATER-RAD` drains evaporator water for every watt the radiator rejects (2.53 kg/h; Apollo 14 evaporated 4.1 kg in the whole flight) and double-counts the radiator load; the power amplifier's 72 W is counted twice (load inventory and `E-AMP-LOAD`); `comm_amp_t` assumes 250 W dissipation against a 72 W input | `09-quiet-coast-episode.md` §"Defects" |

## Decision

Maintainer items (accepted):

1. **No converter.** Each main bus voltage is an algebraic solve of its feeding cells: per module
   `V = E₀ − R·I` with `E₀` and `R` from E-1/E-2 (a secant through the published operating-range
   endpoints, recorded as derived and bounded as such). `source_converter_v` stops being a lag on the
   episode's path; its `tau_s` stays UNCONFIGURED and is not consumed.
2. **Bus routing as flown.** Fuel cells 1–2 on bus A, 3 on bus B; the episode's load assignment
   follows the flown split. The assignment of individual loads to buses is `chosen`, bounded by the
   flown two-thirds share, until per-load bus assignment is sourced.
3. **Reactants per ampere.** The fuel-cell reactant and water transfers are computed from module
   current, not power.
4. **Pump as flow.** The glycol pump's command moves loop flow as a fraction of the published
   200 lb/h, not a speed in rpm.
5. **Defect fixes.** `E-WATER-RAD` reads the evaporator's duty, not the radiator's rejection; the
   amplifier's draw has one home (the load inventory); `comm_amp_t`'s dissipation derives from the
   amplifier's input and efficiency.

Operator items (proposed; John decides, `09-quiet-coast-episode.md` §8 and the thread of 2026-10-15):

6. B1 — the episode's scarcity is cooling margin, with data playback as the deadline.
7. B2 — the playback volume `D₁ + D₂` is `chosen`, bounded below the (unknown) recorder capacity.
8. B3 — `link_ok` is a declared episode boundary.
9. B4 — a constant sun-on-radiator hold is the declared environment.
10. B5 — zone start temperatures are the model's derived equilibrium.
11. Thermal node masses and conductances are `chosen`, constrained to reproduce the flown coast
    rejection of 1,170–1,470 W (SP-368 p. 525), each labelled with that bound.

## Acceptance and consequences

- Items 1–3: an analytic case per bus (`V` at two currents from E-1/E-2) and the per-ampere reactant
  case from the J-Mission table pass through the real step loop; bus A starts inside 26.5–31 V.
- Item 5: Apollo 14's 4.1 kg evaporated water over the mission is the sanity bound; a test fails if
  water drains while the radiator alone carries the load.
- Bus tie (`bus_tie_closed`) and the load-shed ladder (`load_shed_class`) have no Apollo automatic
  counterpart; they are outside the episode and are not changed here.
- If John rejects an operator item, the episode design changes as `09-quiet-coast-episode.md` §8
  lists; the maintainer items stand on their evidence either way.
