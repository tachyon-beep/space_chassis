# Risks, assumptions, dependencies and the decisions that will come back

As of **2026-10-15**, `main` @ `{{MAIN}}`. Ordered by what it does to the outcome, not by
likelihood. Each row names an owner and what would show it has happened.

## Risks

| risk | effect | owner | signal | response |
|---|---|---|---|---|
| **A physical input has no applicable source** (converter impedance, thermal node aggregation, RCS jet geometry and impulse, helium feed were already named as research blockers on 2026-10-04) | the dependent domain never passes V; a bounded episode that depends on it cannot be accepted | vehicle; John for scope | a WP02/WP03 child closes as "no applicable source" | the value stays `UNCONFIGURED`; the question goes to John as a scope decision with the options: accept a declared approximation with provenance `chosen` and a stated bound, narrow the vehicle's objective, or leave the state out of V's scope |
| **The local-only work is lost** before it is pushed (`#39` Option B, `#23`, Phase B, brief v5) | weeks of reviewed work redone | John (residual 1) | a disk or `/tmp` loss on his workstation | push now (D11) |
| **The complete vehicle misses live real time** (20 ms per tick with instruments and ten windows) | a slower-than-real-time world or a native port | vehicle; John for the target | `plant.py --mission` trend in CI artifacts crossing ~10 ms before WP09 | the route in [05-performance.md](05-performance.md); the fork (native core vs `m < 1`) is John's |
| **Review depth collapses back into rounds** once the slot regime is gone | throughput falls again | governance | more than two review rounds on a PR | the stopping rule; CI carries the mechanical checks |
| **The referee cannot run in CI** (memory, time) | gate D unenforced again | vehicle | red or timed-out lanes | fix the > 13 GB test; split the referee by domain |
| **The chassis image cannot be built where CI runs** (`deb.debian.org` blocked in the default cloud environment) | live checks and Phase B's acceptance stay manual | aurora; John for the environment | `live.yml` cannot start | select the "Space Aurora" environment for the project with that host allowed, or run `live.yml` on a self-hosted runner |
| **Flight dynamics takes longer than everything else combined** | M4 waits on one strand | vehicle | WP07 still open when WP04–WP06, WP09, WP10 close | start WP03 evidence and the 6-DOF integrator class in tranche 1, not tranche 3 |
| **Crew perception has no display contract** (`crew_diode.md:42`, conflict D-06) | `ask_crew` stays a stub; crew is 0 of 7 | vehicle | WP09 reaches crew | write the display contract as a decision record; it is design work, not research |
| **The information rule leaks through a new channel** (a fault label, a quality shortcut, a truth value in a frame) | the experiment is decorative | vehicle, aurora | a negative check fails, or a reviewer finds a field the window should not carry | the quality function's signature excludes the fault state; negative checks in the probe for every new field |
| **Two sessions on one branch** | both runs void | all | duplicate resumes | one owner per branch; session-unique scratch |

## Assumptions this suite rests on

| assumption | if wrong |
|---|---|
| The vehicle's objective stays eleven domains, 192 hours, 50 Hz | the gap map and the sizes change; John's call only |
| The evidence standard stays: no plausible defaults | relaxing it would shorten M2 and weaken V; John's call only |
| The configuration corpus has not changed since `64fc58c` | the counts here are stale; re-run the tools (they are cheap) |
| Python with multi-rate can hold 20 ms per tick | the native-core fork opens |
| The vehicle's work-package decomposition (WP01–WP13) is the right one | it was reviewed twice (2026-10-03 scaffold, 2026-10-04 programme) and matches the gap map; a repartition is not proposed |

## Dependencies outside the streams

| dependency | needed for | state |
|---|---|---|
| a session on John's machine | pushing local work; killing the watcher; the host migration into `aurora/` | waits on residual 1 |
| an environment that can build the image | live checks, Phase B acceptance, the bounded episode | the project has no environment selected (readiness review) |
| John's confirmation of the caps | any paid run | residual 2 |
| branch protection | gate D enforced | residual 3 |
| the frozen corpus and primary Apollo sources | M2 | available; applicability per question |
| an independent physics reviewer per M3 package | gate V | assigned when each package is claimed |

## Open issues carried from the lines

| issue | what | owner |
|---|---|---|
| vehicle `#40` | `#21` residuals: torn-marker authenticity; repeated cut markers on a maximum-length row (P3) | vehicle |
| vehicle `#42` | gates reopen on resume | vehicle |
| vehicle `#35` | sweep agent-facing text (HELP.md verb texts first) | vehicle, at the end-of-work sweep |
| vehicle `#16` | the standalone linter depends on chassis files; closes when the chassis's pins move | vehicle after Phase B |
| contract V-1 to V-3 | "destructive and atomic"; "claimed at the window's next read"; "exactly one file" | vehicle, with Option B |
| orphaned `sleep 30` in `test_journal.py::test_a_stream_that_never_ends_times_out` | needs an issue | aurora |
| chassis plan 7 deferred minors (`docs/superpowers/ledgers/plan-7-ledger.md` on `vehicle-adoption`) | slug-validation tests exercise one check; the vehicle bind check ignores named volumes | aurora |
| `.claude/settings.json` SessionStart hooks call `/home/john/.local/bin/filigree` | harmless failure in cloud sessions | aurora |

## Decisions that will come back to John, at the moment they arise

These are not open now. Each is named here so that nobody treats it as already decided.

| when | decision |
|---|---|
| a WP02/WP03 question closes with no applicable source | accept a `chosen` approximation with a bound, narrow the objective, or leave the state out of V |
| the bounded episode is accepted | run a paid pilot on it (residual 5): budget, model, fleet size, stop criteria |
| the complete vehicle misses 20 ms per tick after optimisation | native core, or `m < 1` |
| WP12 needs faster replay than measured | re-decide the 300-second target |
| any change to the vehicle's objective or evidence standard | his alone |
| any agent-facing text beyond the tier-1 wording already reviewed | review per `practice.md`; the brief's voice is his |
| the first model-backed preflight | the caps, and the go |
