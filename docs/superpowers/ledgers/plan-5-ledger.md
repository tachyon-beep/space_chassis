# SDD ledger — plan: docs/superpowers/plans/2026-10-09-aurora-port-5-retire.md
Spec: docs/superpowers/specs/2026-10-09-aurora-port-design.md §6, §7, §9, §10. Branch aurora-port. Executor: inline (Opus 5.5). Reviews: Opus + one Astra run (gpt-6-astra, high), John 2026-10-09, while Fable is limited. Plan reviewed by both before execution; corrections in aafab65.
Pre-flight: Task 1 consumes nothing; Task 2 consumes Task 1 (conftest free of the old world); Task 3 consumes Task 2 (modules deleted); Task 4 consumes Task 3 (merged suite for node resolution); Task 5 consumes Tasks 2 and 4 (allowlist, drafts README); Task 6 consumes all. No conflicts.
Task 1: Ruling: tests/test_fake_diode.py needed `import time` the old file had at top level — cost if wrong: none. Counts: root 521 → 463 (69 retired: test_chassis 22, test_run_end_to_end 17, test_services 30; 11 kept).
Task 1: complete (commits aafab65..ac7cdce, tests: python3 -m pytest tests -p no:cacheprovider -n 8 → 463 passed in 27.14s)
Task 2: Ruling: test_retired's guard skips negative assertions in tests/ (`assert … not in …`), since a test that asserts absence must name the thing — cost if wrong: a positive reference written as a negative assertion would slip through.
Task 2: Ruling: the roster printout's last column is now the slug (was the retired `private` mount); the print test is a regression guard that passed before and after — cost if wrong: none.
Task 2: live 13/13 in 5m32s on the narrowed image.
Task 2: complete (commits ac7cdce..9da39a5, tests: python3 -m pytest tests -p no:cacheprovider -n 8 → 469 passed in 27.71s)
Task 3: Ruling: the collection tests pin --rootdir and -c to the repository, since the vehicle submodule's own pytest config otherwise roots its node IDs at the submodule; and override addopts, since its -q plus a second -q prints per-file counts (an early version passed vacuously on two empty sets — caught, and _collect now asserts it named tests) — cost if wrong: none.
Task 3: merged run 1616 passed in 7m06s with -n 8.
Task 3: note: bc40855 tripped test_retired (a docstring naming a retired path; the pre-commit run passed because the file was untracked and the guard scans tracked files); fixed in the follow-up commit. Lesson: run the suite after git add, before the commit.
Task 3: complete (commits 9da39a5..c243b83, tests: python3 -m pytest tests -p no:cacheprovider -n 8 → 472 passed in 27.87s)
Task 4: the three test files pinned facts the port already had (passed on first run); the acceptance map's RED was a mutation (a mistyped node fails its row).
Task 4: note: a root-suite run showed "1 failed, 508 passed" with no name captured; six reruns 509/509. Hunting it in the background (ten runs with -rf). Same signature as plan 4's unidentified flake.
Task 4: complete (commits c243b83..dcc7e40, tests: python3 -m pytest tests -p no:cacheprovider -n 8 → 509 passed in 28.85s)
Task 4: note: the ten-run flake hunt (-rf) captured no flake; its only failures were Task 5's expected RED.
Task 5: Ruling: the doc allowlist is removed, not left as an empty tuple — same guard, no dead name — cost if wrong: none.
Task 5: Ruling: design.md §9 rewritten too (it said the roster is published at /work/roster.json; it is the operator's) — the brief says check every filesystem claim against spec §5 — cost if wrong: none.
Task 5: Ruling: .env.example's commented pump defaults corrected to compose's 32/8 (were 64/16) — the example documents the defaults — cost if wrong: none.
Task 5: Ruling: ruff 0.16 now formats code inside markdown; the frozen corpus, the vehicle submodule, old plans and test_vehicle_reconciliation.py (pre-port blank lines, bd846c9) are left unformatted; my three test files from Tasks 2 and 4 are formatted — cost if wrong: a format gate over the whole tree would fail on files this plan does not own.
Task 5: complete (commits dcc7e40..4f1c1c2, tests: python3 -m pytest tests -p no:cacheprovider -n 8 → 511 passed in 26.78s)
Task 6: live 14/14 in 6m12s (python3 -m pytest live -q -p no:cacheprovider -rf), including test_the_fleet_cap_refuses_and_the_agent_pauses.
Final review: Opus (general-purpose subagent) and one Astra run (gpt-6-astra, high), on aafab65..562c805. Neither found a Critical.
Final: re-graded Astra minor 6 (the raw API "one link away") to Important — an operator investigating an early incident is told a route exists that 404s.
Final: re-graded Opus minor 4 (WORLD draft offers /telemetry as surviving storage) to Important — the draft would tell agents to keep work where the mirror deletes it every 5 s (Review Focus 5).
Final: fixed the diode profile (ran a missing /opt/diode/diode.py, on worknet plus gateway windowside, against spec §2/§3/§5) — test_the_diode_profile_runs_the_contract_fixture_off_worknet RED→GREEN.
Final: fixed REVIEW_PORT (moved the listener, not the mapping target, so any non-default port lost the panel) — test_the_review_panel_listens_on_the_port_its_mapping_targets RED→GREEN.
Final: fixed false claims in the docs and drafts (done keeps the code; the pump's processes survive; raw history one link away; the draft prompt's "damage only yourself" and "always brought back"; /telemetry as storage) — tests/test_doc_claims.py, 9 tests RED→GREEN; the drafts README's claims table gains the three claims with sources.
Final: fixed the red ruff format gate CLAUDE.md and README advertise — `uvx ruff format --check .` 11 files → 0.
Final: Ruling: the vehicle submodule is excluded from this repository's ruff (check and format), and docs/deep_research/** and docs/superpowers/** from format — the vehicle is its own repository with its own config (its checkout is at the vehicle workstream's 8c6f71d), the corpus is frozen and the plans are history — cost if wrong: a lint slip in the vehicle is no longer caught from this side.
Final: Ruling: test_vehicle_reconciliation's vehicle-volume check compares with the diode's window bind, not its whole mount list — the diode now also mounts its fixture's source, which is not the window — cost if wrong: none.
Final: Ruling (declined by Opus): `docker compose down` without --profile in the README — left as is; Compose v2 removes the project's containers by label — cost if wrong: an operator's fleet containers survive a down.
Final: Ruling (declined by Opus): spec §5 says /build is "image, tmpfs"; the code gives each agent a /build volume image and the docs follow the code — cost if wrong: none to behaviour; the spec needs a correction.
Final: minor (deferred): SmokeStack.recreate writes values into double quotes unescaped; a `"` breaks the YAML and every later compose call, teardown included (both reviewers).
Final: minor (deferred): "no Docker needed" (CLAUDE.md, AGENTS.md, README) — tests/test_live_stack.py's config-parse tests need the compose CLI; "Tests never skip" — two tests skip.
Final: minor (deferred): the README quick start does not name scripts/build_registry.sh, which prepare_host.sh requires.
Final: minor (deferred): CLAUDE.md lists /diode/<slug> among the agent's own images (it is a subpath of one shared image), omits 43's three-in-600-s escalation and /opt/vehicle.
Final: minor (deferred): .env.example says REVIEW_MAX_BYTES 8388608 (default 33554432) and that the fleet pool runs on the clock hour (it is a rolling hour).
Final: minor (deferred): test_retired's HOME test does not check "does not persist"; the (retired) exemption is per line, not per phrase; BANNED lacks a bare "tasks" path.
Final: minor (deferred): tests/test_agent_dependencies.py's docstring calls pypdf Aurora-only while the test pins it.
Final: minor (deferred): the node IDs cited in test_startup's docstring and the drafts README are unguarded; test_acceptance_map does not compare its keys with spec §9's list.
Final: minor (deferred): the live fleet-cap test's transcript wait reads the whole file, not from the mark (the marked log wait carries the property).
Final: minor (deferred): docs/design.md §4 says the agents are told all this in brief/WORLD.md, which still describes the retired world until John approves the draft.
Final: fix pass committed; root 526/526, merged 1670/1670 (6m40s, -n 8), live 14/14, ruff check and format clean.
Task 6: complete (commits 4f1c1c2..562c805, tests: python3 -m pytest live -q → 14 passed; root 514 at commit) — written by hand after the fix pass, not by task-done.
Post-final: drafts approved by John 2026-10-09 and shipped in 12a6489; guards cover brief/ and the prompts.
Post-final: deferred minors fixed in 3cffc18; root 535, live 14/14.
