# AUR-GOV-07 — vehicle capability and debt report (report v1)

As of **2026-10-10T09:34Z** (20:34 AEDT). Claimant: **Space Vehicle**, Claude Code
`session_01GRfs7dVMu4v5airK6q3w9C` = local session `a728e992-9471-46ab-9efe-ce550d7ece5f` = peer
`[610587]` (the same owner as AUR-GOV-02; the alias mapping is this session's own attribution line).
Accountable line: vehicle. Criteria: `../../MASTER_GOVERNANCE_PLAN.md` §4 (AUR-GOV-07), claim §11.
Read-only report: no implementation, merge or paid run was made for it.

**Versions.** Merged vehicle `origin/main` = `64fc58c71ab52c2ababafdeb9430feddaa8a69c2` (hosted CI:
success). #21 head `45f426763280aa1274732fc35f99584b4d7f9ebc` (pushed, unmerged). The chassis runs
`dd79e7608c931df9e5273824a3b2b9f396cb7cb7` (gitlink on chassis `main` `fa43b25…` and `aurora-port`).
`git diff 64fc58c 45f4267 -- '*.yaml' domains/ plant.md` is empty: **the configuration corpus is
identical** on `main` and #21's head, so the model measures below hold for both. They do **not** hold
for `dd79e76`, which predates 54 commits.

## 1. Three different measures (never one percentage)

Source: `tools/plant.py --readiness` and `--build-order`, and `tools/check_vehicle.py`, run in the
owner's gate at `f12e522dda31ea5ad8aa8944095e61814b40eac1` on 2026-10-10 06:36Z, Python 3.12.3 and
3.13.15, identical output on both lanes (same corpus as `64fc58c`). Durable copies:
`.scratch/wp01-handoff/evidence/wp08-3-custody/scratch-evidence/wp08-3-f12e522-ca87a9/{readiness,build-order,run}-3.1{2,3}.txt`.

| measure | value | what it means |
|---|---|---|
| **configured** states | 108 / 139 fully configured; 31 carry a debt; 69 / 81 edges carry a sensitivity; **195 UNCONFIGURED scalars** | the configuration declares a value; says nothing about whether a tick moves it |
| **advancing** states | **52 / 139** advance on a real tick ("ready now"); 87 cannot | of the 87: 27 owe a value, 15 owe an edge (a coupling with no sensitivity, or a state nothing drives), 45 owe a rule (`algebraic`, `discrete`, `dynamics` or `hazard` domain code) |
| **accepted** physics | **none** | no state has passed gate V's independent physics, protection, conservation, fault and instrument checks; there is no acceptance record |

World: 139 states over 59 nodes, 81 edges, eleven domains. Registry (from `snapshot.md` at
`64fc58c`, tool-generated then; not re-measured here): 148 channels in 5 cadence classes, 38 withheld
truths, 128 declared faults, 15 failure chains, 8 phases.

## 2. Lint debt

`check_vehicle.py`: composes, **273 declared debts**, exit 0. `--strict`: **exit 2** — expected while
honest debts remain, and a hard fail of gate V, not a pass. `report.refuse(` call sites: 882. Each
declared debt is a named missing value or rule in the corpus. None is invented: per `ROADMAP.md`
("Keep the programme honest"), a value without evidence stays unset.

## 3. Acceptance gates (`docs/completion.md` at `64fc58c`)

| gate | evidence required (abridged) | state | evidence / gap | next owner → action |
|---|---|---|---|---|
| **D** reproducible development | locked deps; lint exit 0; all referee tests pass, none skipped; both lanes; independent PR review | **met per merged PR**, not enforced | every merged package has had both-lane gates with zero skips and independent review; hosted CI green at `64fc58c`. **Not enforced**: branch protection inactive (#15) | **John** → #15 (a settings change) |
| **I** integrated slice | the deployed-path executive advances one authoritative state; two windows command and observe it; deterministic arbitration and receipts; evidence from stepped truth | **delivered in parts, not accepted** | WP01 (#17, `0ad1ff5`): one executive, bounded multi-window ingress, arbitration, receipts. No gate-I acceptance record; M1 also needs WP08 (#8). Ingress has a contract defect, **#39** (below) | vehicle → finish WP08, fix #39, then record gate I |
| **V** complete vehicle | strict lint exit 0; no executable-state gaps; every phase/command exercised; independent physics/protection/conservation/fault/instrument checks | **not met** | strict exit 2; 87 / 139 states cannot advance; WP04–WP07, WP09–WP11 not started | vehicle; M2 evidence first (§5) |
| **M** accepted mission | full nominal and degraded missions through the same executive; deterministic replay; restart continuity; measured budgets | **not met** | replay-from-record (#38) and resume (#21, unmerged) are parts of it; WP12 not started | vehicle, after V |
| **E** experiment apparatus | exact vehicle/chassis/image SHAs; containment and diode probes; preflight; protocol | **not the vehicle's to claim** (joint, chassis/operator) | the vehicle must never claim E from referee results | chassis/operator |

## 4. M1 (WP01, WP08) completion and residuals

- **WP01 (#1): closed** (#17 `0ad1ff5`; #36 `f81fe2c` took run identity out of the windows; #37 `2b66af0`).
- **WP08 (#8): open.** Children closed: 1 (#19, checkpoint format), 2 (#20, `--state-dir`), 4 (#22,
  durable record), 6 (#24, encoder). **In flight: 3 (#21).** Open: 5 (#23 clock seam), 7 (#25 budget
  on the mission clock), 8 (#26 overload), 9 (#27 pause), 10 (#28 downtime, graceful stop,
  `--new-world`), 11 (#29 phase from tick), 12 (#30 result stamps).
- **Stated limitations carried by #21** (its PR body): the record prefix before a checkpoint's anchor
  is attested by the checkpoint, not re-read; the budget's wall clock restarts with the process (→ #25);
  no graceful SIGTERM or recorded new-world path (→ #28); scheduled-event and phase-boundary restart
  points not exercisable until faults are scheduled and the phase moves (→ #29, WP09); a process
  restart costs ≈ 5.5 s, mostly YAML loading.

## 5. M2–M5 dependencies and missing physical evidence

| milestone | packages | depends on | state |
|---|---|---|---|
| M2 evidenced physical inputs | WP02 (#2) electrical/thermal/consumables; WP03 (#3) flight/propulsion/RCS | — (runs alongside M1) | **not started** |
| M3 complete executable vehicle | WP04 (#4) → WP05 (#5); WP06 (#6); WP07 (#7); WP09 (#9); WP10 (#10); WP11 (#11) | WP02, WP03, WP01, WP08 | not started |
| M4 accepted mission | WP12 (#12) | WP11 | not started |
| M5 release and handoff | WP13 (#13) | WP12 | not started |

**Missing physical evidence** is the debt in §1–2: the 195 UNCONFIGURED scalars and the 27 states
owing a value are mostly physical inputs (time constants, initial values, lumped masses, derate
curves, provenance bases). The first blocked states, in schedule order, include `pressurant_he_kg`
(needs `min_flow_per_s`), `zone_lm_descent_t` and `zone_csm_service_t` (`initial`, `lumped_mass_kg`),
`source_converter_v` (`tau_s`), `battery_usable_j_j` (`derate_curve`, `provenance.basis`), and
`o2_supply_pressure_psi` (`tau_s`, `provenance.basis`). The full list is in the readiness output.
`ROADMAP.md` risks: where evidence is unavailable, values stay unset, and **scope is the operator's
decision**.

## 6. #21 findings and dispositions

Five review rounds after a design review (records in `records/`): code review of `06f08a3`
(F1–F18, R1–R5) → confirmations at `0647ee2` (G1–G8), `d0a20dc` (H1–H3), `f12e522` (J1–J4, J1a),
`a38cee1` (K1–K2), and **`45f4267`: approve, no P1 or P2** (Codex `gpt-6-astra` high, scoped to the round-5
diff by the binding termination rule). Every P1 and P2 was fixed with a test that failed first.
**Residuals (P3, open): #40** — the torn-tail marker gives syntax, not authenticity (inside the trust
model); two successive one-byte cuts on a maximum-length row refuse by name.

**Found while probing #21, not #21's: #39 (P2, open)** — the claim reads `console.json`, then renames
the emptied console over it. A batch an agent replaces in between is erased: no result, no record, no
trace. That contradicts the contract (§2.2: such a batch "runs on the next one"). Evidence: 40 of
6,296 batches lost in a no-kill probe at `--poll 0` with jittered writes; 0 of 1,703 without the
jitter. The defect is on `main` and in `dd79e76`. Exposure at the chassis's 5 s poll: ≈ 2 × 10⁻⁵ per
submission. Probe and fix directions are in the issue.

**Input to the coordinator's §12 blocker (not established):** `test_the_vehicle_passes_the_contract_probe`
failed with "a non-string element refuses the whole batch", **0 result files**. That is #39's
signature: a batch the probe wrote, erased by the claim, leaves no result. The probe runs the
submodule checkout `8c6f71d`, which has the same `claim` code, at `DIODE_POLL_SECONDS=0.05`. Heavy
concurrent host load, including the owner's own #21 gates running then, widens the claim window. A
check that would separate this from other causes: whether the probe's console write landed inside a
claim. Not run here.

## 7. #21 checkpoint at 09:34Z (completed vs queued)

| evidence | state |
|---|---|
| per-commit full suites, 3.12, `98bd804..2c3a70a` | **completed**: every commit passes except `29becaf` (documented; `git bisect skip`); last `2c3a70a` 539 passed |
| per-commit at `36fdd91` | **queued** (owner job, starts after the implementer's gate) |
| implementer gate at `45f4267`, three full 3.12 runs | **runs 1 and 2 completed** (539 passed each); run 3 running |
| owner gate at `45f4267`, both lanes | **queued** (starts after the implementer's gate); output `…/evidence/wp08-3-45f4267-ca87a9/` |
| owner probes and SIGKILL stress at `45f4267` | **completed**: clean (`…/wp08-3-custody/scratch-evidence/wp08-3-45f4267-stress/SUMMARY.md`) |
| PR, hosted CI, merge, merge SHA on `space_chassis-93010ff54e` | **not started**; the PR body is drafted (`.scratch/wp01-handoff/pr-wp08-3.md`) |

## 8. Decisions needed

- **#15** branch protection (John): gate D is met per PR but not enforced.
- **M2 evidence scope** (operator, per `ROADMAP.md`): when a physical input has no evidence, does it
  stay unset — keeping that state from advancing — or does the operator accept a declared
  approximation? Not yet asked for a specific value; it becomes live when WP02 or WP03 starts.
- None needed for #21 or #39.

## 9. Next atomic slices (vehicle)

1. Land #21: gates → PR → CI → merge → merge SHA. Unblocks chassis Phase B.
2. **#39**, the claim race.
3. WP08 children #23 → #25–#30, closing M1 and gate I.
4. M2 (WP02, WP03) evidence research can run alongside.
