# SDD ledger — plan: docs/superpowers/plans/2026-10-09-aurora-port-7-vehicle-adoption.md
Spec: aurora-port design §5 and §8. Requirements: .scratch/vehicle-adoption/PACKAGE.md (main checkout), and filigree space_chassis-93010ff54e comments 37–38.
Setup: worktree .claude/worktrees/vehicle-adoption, branch vehicle-adoption, with the vehicle cloned at 64fc58c. Executor: inline (Opus 5.5).
John, 2026-10-09: "Deconflict with the other agent. I need both of you working."
Plan reviewed by an Opus subagent (2 Critical, 6 Important). Corrections are in 2e6b4fe, together with the vehicle session's revised §3 (comment 38).
Baseline at 64fc58c: root and harness suites green except the two pins Phase B moves (test_the_changelog_row_for_the_linter_is_held_against_the_linter, test_the_reconciliation_readme_states_the_vehicle_suite_s_test_count).
Ruling: the 40G vehicle_state image is always allocated, because the volume plan has no notion of a profile, and this is stated in the docs. Cost if wrong: 40G on a host that never runs the vehicle.
Pre-flight: Task 2 consumes Task 1's VEHICLE_STATE_DIR. Task 3 consumes Task 2's vehicle_state name. Task 4 documents all three. No conflicts.
Task 1: complete (commits 2e6b4fe..1f6cc8b, tests: tests/test_vehicle_reconciliation.py + test_agent_image.py → 15 passed, 2 failed = the Phase B pins only). RED: 4 consoles forked; GREEN: one exec'd. Ruling: slug validation is in-script ([a-z], [a-z0-9_], ≤32) and exits 2 naming the slug — cost if wrong: none (console also validates).
Task 2: complete (commits 1f6cc8b..c3dd304, tests: python3 -m pytest tests -n 8 → 562 passed, 2 failed = the Phase B pins). Ruling: the plan missed more pinned counts (74→75 at ten, 25→26 at three, list 11→12, list/fstab 18→19) — updated with the new kind — cost if wrong: none. Fixed a test-helper bug (split(':') broke on '${…:-…}'; now rsplit).
Task 3: complete (commits c3dd304..c469e79, tests: tests/test_verify_containment.py → 13 passed). Ruling: the fake docker answers the new inspect/probe queries only when the test sets them, so the existing 'a probe that cannot run is never a pass' test keeps its meaning — cost if wrong: none. .executive.json needs no change: agents see only /diode/<slug>; diode_probe --list prints directories; the monitor reads /diode/<slug> only.
Task 4: complete (commits c469e79..5fa729b, tests: python3 -m pytest tests -n 8 → 568 passed, 2 failed = the Phase B pins). Note: README's restart procedures describe #21's behaviour; Phase A lands only with #21.
Ledger correction: Task 4's commit is 3212c90 (5fa729b was the pre-amend id).
Opus code review (phase A): no Critical; 2 Important.
Final(Opus): fixed I1 README silent on image rebuilds (Python/libc in the checkpoint) — README test phrases RED→GREEN.
Final(Opus): fixed I2 slug globbing — set -f; servable test with VEHICLE_SLUGS='*' from a non-empty cwd RED→GREEN.
Final(Opus): re-graded minor "first-start wording deletes slug dirs" to Important (an operator procedure that breaks the fleet's binds) — fixed, guarded.
Final(Opus): re-graded minor "--closed-interlock documented but not wired" to Important (operator told to do what the service cannot) — README says how; plus "checkpoint interval". Commit b4121f5.
Final(Opus): minor (deferred): validation test exercises only the first-character check (add a.b or a/../b).
Final(Opus): minor (deferred): mkdir -p runs before the console validates the set (a mistyped valid slug leaves a stray dir).
Final(Opus): minor (deferred): vehicle bind check filters on Type=bind (a named volume would pass); /vehicle_state/ match needs no trailing slash.
Final(Opus): minor (deferred): the containment fake answers any container id; the empty ps -q path is untested offline.
Final(Opus): minor (deferred): serve(hold=...) parameter unused.
Final(Opus): Phase B note: build the image from the worktree only — Dockerfile.agent copies docs/deep_research/vehicle from the build context, and the main checkout's is the other session's.
Final(Opus): open for John: the agent image's base is python:3.13-slim with no digest pin; any --pull rebuild can make the vehicle's checkpoint incompatible.
Phase A full run (before the Astra fixes): merged 1811 passed, 2 failed (the Phase B pins); live 14/14.
Astra final review (phase A): no Critical; 1 Important.
Final(Astra): fixed new-world procedure omitting the root .executive.json — test_a_new_world_archives_the_window_root_s_identity_too RED→GREEN.
Final(Astra): re-graded minor "root-write probe reads a missing touch as refused" to Important (a containment check failing open, against the script's own rule) — test_the_window_root_probe_says_nothing_when_it_cannot_run RED→GREEN.
Final(Astra): re-graded minor "vehicle-state check misses an image-root bind" to Important (a false PASS on the property it claims) — test_an_agent_bound_to_the_vehicle_state_image_root_is_a_failure RED→GREEN. Commit b94ef44; root 571 passed + the 2 pins.
Final(Astra): minor (deferred): the vehicle mount check ignores named volumes (bind-only); the compose test's substring match shares the weakness.
Final(Astra): minor (deferred): slug tests do not protect the alphabet and length checks (a.b, a/../../escape, 33 chars) — also Opus.
Task 5: Phase A reviewed (Opus + Astra), one fix pass each.
Live containment on b94ef44: ...                                                                      [100%]
