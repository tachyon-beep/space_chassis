# Integration: what the chassis must do to fly the vehicle

As of **2026-10-15**, `main` @ `0036b88`. The chassis (`aurora/`) owns the vehicle's deployment and
adopts the vehicle by exact SHA; the vehicle states its needs (`governance/vehicle/interface.md`).
This file lists the integration work between today's chassis, which runs a pre-WP01 vehicle, and
gate E, the accepted experiment apparatus.

## Where the two sides are

| | chassis runs | vehicle is |
|---|---|---|
| vehicle commit | `dd79e76` in the reconciliation pins (`aurora/tests/test_vehicle_reconciliation.py`); the image bakes whatever `vehicle/` holds at build time | `f75420c` at `vehicle/` (tier 1 of `#39` included) |
| serve script | one `console.py` per slug, no `/state` | one executive for every window, `--state-dir /state` (WP01, WP08) |
| contract §2.2 | "runs on the next one" | tier 1's quiet-cycle qualifier (vehicle `#39`), not yet adopted |
| fixture | `aurora/contract/fake_diode.py` without the quiet rule | — |
| brief | `brief/PROTOCOL.md` lines 51–78 pre-tier-1 | wording v5 reviewed APPROVE, in `.scratch/tier1-brief-draft/` on John's machine |

## The adoption steps, in order

### 1. Push the staged work (D11; needs residual decision 1)

From John's machine: Phase B's P (`refs/preserve/phase-b-P-af671d04`) and R2c
(`refs/preserve/phase-b-R2c-148a31c4`) as commits on `wip/aurora/phase-b`; the tier-1 brief v5; the
`.scratch/phase-b-*` evidence and drivers. Until this happens no cloud session can continue Phase B.

### 2. Phase B: adopt the stepping vehicle (chassis; plan 7)

What the adoption commit carries, from `chassis/interface.md` and the Phase B records, rebased from
`f44399`/`vehicle-adoption` onto `vehicle/` at `f75420c`:

- `containers/serve_vehicle.sh` `exec`s one `tools/console.py` with every `--slug`, `--state-dir
  /state`, `--ring-slots`, `--poll`, `--cycles 0`, no `--phase`, under `init: true`;
- the `/state` 40G image, mounted by the vehicle service alone; `network_mode: none`; `read_only`,
  `cap_drop ALL`, `mem_limit 512m`, `restart: unless-stopped` (exit 3 is a refusal that writes nothing);
- the reconciliation pins retaken from `f75420c` (test count, `report.refuse` sites, the fixture
  copying `tools/checkpoint.py`);
- the base image pinned by digest (`python:3.13-slim@sha256:70729b46…`, John 2026-10-10);
- `verify_containment.sh`: no agent writes the window root, mounts `vehicle_state` or the vehicle's
  source; the vehicle binds `/diode` and `/state` and nothing else;
- R2c's per-run resource controls for the live stack (one live stack, 5 CPUs / 14 GiB);
- README "The vehicle": first start, restart, deliberate new world, exit 3.

**Accepts:** the root suite and the whole suite green in CI; the live vehicle checks (one world
across windows, SIGKILL then resume replaying ticks, containment, `docker stop`) passing against the
built image. P passed root 592 and full 1,941; R2c passed root 617; its full and live runs never
happened (slot regime). They happen now.

### 3. Tier 1 of `#39` (chassis adopts; D7)

In the same commit as step 2 or the next: contract §2.2's qualifier replaces "runs on the next one";
`fake_diode.py::AgentSide.consume` implements the identical quiet test with a test; `brief/PROTOCOL.md`
A, B, C, C′ and the `brief-claims.md` row D from wording v5. Chassis evidence: the q1–q3 re-run and
the ≥ 30 gate runs with instrumented early returns, written as a test.

### 4. Option B of `#39` (vehicle, then chassis; D8)

Vehicle: push `7a87eb82`, run CI, settle V-1 to V-3 (the contract's "destructive and atomic",
"claimed at the window's next read", "exactly one file" sentences) in the same change, merge.
Chassis: adopt with `CONTRACT-PACKAGE-B.md` (`governance/vehicle/records/2026-10-14-lane-archive/39-option-b/gate/`):
the fixture's take-by-rename, the brief's tearing sentence ("a brief absence of `console.json` during
a claim is accepted; agents must detect and handle tearing", John 2026-10-11).

### 5. `#23` clock seam (vehicle, then chassis)

Vehicle: commit and push candidate 3a, run the referee (564 expected), run `measure_clock` with ten
windows at `m = 1`, merge. Chassis delta (`#23` design §7): `serve_vehicle.sh` passes `--m 1 --k 5
--n 50 --ring-slots 3000` and drops `--poll`; `stop_grace_period` covers the interim 30 s lag backstop
(exit 4 is a refusal, not a crash); README documents exit 4. Everything the vehicle publishes per
cycle at k = 5 is unchanged for the agents.

### 6. The remaining WP08 chassis deltas

| vehicle child | chassis side |
|---|---|
| `#27` pause | the operator's invocation (the vehicle names the mechanism: flag, signal or file); a `scripts/` command and a README line |
| `#28` downtime, `--new-world`, retention | `stop_grace_period` from the vehicle's shutdown bound; the `/state` archive procedure; the deliberate-new-world runbook replaces today's manual one |
| `#26` overload | nothing, unless the vehicle asks for a CPU reservation |
| `#30` MET result stamps | `fake_diode.py` result naming follows; `brief-claims.md` if the brief names the stamp format |

### 7. Faults and instruments (WP09) reach the window

No chassis code, but two things to verify at adoption: the window carries no fault label, quality
shortcut or truth (the contract probe and `verify_containment.sh` gain negative checks for the new
fields), and `brief/WORLD.md`'s description of telemetry quality matches what the instruments publish.

### 8. Gate E: the accepted experiment apparatus (chassis and operator)

After V and M (`vehicle/docs/completion.md`): exact vehicle, chassis and image SHAs recorded
together; containment and diode probes on the built stack; the campaign-ready chassis (caps,
transcripts, journal, operator stop); a bounded stub preflight, then a model-backed preflight under
the confirmed caps (residual 2); a fixed trial protocol and an objective evaluator that reads the
vehicle's private evidence, never agents' self-report (`docs/plans/2026-10-04-vehicle-to-green-programme.md`
§7). A vehicle PR never claims E.

## The bounded episode's chassis needs (D14)

The quiet-coast episode needs from the chassis: the smoke stack with the real vehicle image
(`SmokeStack(window="vehicle")`), scripted policies driven through the window from the operator side
(a `scripts/` driver, not an agent), and the evaluator reading `/state`. The three chassis survival
items the programme named (handoff with full tool history, bounded request paths, persisted caps)
were addressed by the Aurora port (plans 4b, 6, 9) and are verified by the operator suite; what
remains is the live run on a built image, which needs an environment that can build it
(`deb.debian.org` allowed).

## Chassis questions settled by D15

Each agent mounts its own transcript read-only; `scripts/journal.py --every 300` becomes a compose
service; the base-image pin lands with Phase B. The cap figures remain John's (D16).
