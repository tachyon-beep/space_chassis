# What the agents are told, and what makes it true

`brief/` (at `/opt/brief`) and the prompts in `harness/` (`system_prompt.txt`, `user_prompt.txt`)
are what the agents are told about their world. John approved this text on 2026-10-09 (spec §6,
§10.2). Each row is a claim it makes and the code or test that makes the claim true; a change
that falsifies a row changes the text with it. `tests/test_doc_claims.py` holds the claims the
plan 5 review found false out of it.

The prompts are the agents' to rewrite once they are running: this is the seed, not a contract.

| Claim | Source |
|---|---|
| No route outward; agents reach each other | `tests/test_compose_generated.py::test_agents_join_only_worknet_and_recorders_only_modelnet`; live `scripts/verify_containment.sh` |
| `/work` is a tmpfs reseeded from `/opt/agent` at every start | compose `tmpfs` for `/work`; `tests/test_agent_entrypoint.py::test_the_seed_replaces_work_and_the_watchdog_runs_from_there` |
| `/work` is a git repo with `baseline` and `rescue`, no `experimental` | `tests/test_agent_image.py::test_the_seed_is_a_repository_with_baseline_and_rescue_tags_and_no_experimental` |
| `/state`, `/pump`, `/llm/console`, `/diode/<slug>`, `/shared` persist; `/llm/sock` read-only | `scripts/volume_images.py` KINDS; compose binds |
| `/telemetry` holds the watchdog's mirror and nothing else | `harness/watchdog.py` `mirror_work` (`TELEMETRY_KEEP`) |
| `/build` emptied at every start | `tests/test_agent_entrypoint.py::test_the_build_area_is_emptied_without_being_removed` |
| HOME is a 256 MiB tmpfs at `/home/agent` | compose `tmpfs`; `Dockerfile.agent` `HOME` |
| No transcript is mounted | `scripts/volume_images.py` (no `transcripts` bind for the agent role); live `scripts/verify_containment.sh` (`/transcripts` not mounted); open question §10.4 |
| Postgres `chassis` via `/run/agent`, NATS 4222/8222, Redis 6379 unpersisted, data under `/state` | `containers/entrypoint.sh:86–105` |
| The watchdog is editable and re-executes itself | live `test_an_edited_watchdog_re_executes_and_a_killed_one_reseeds` |
| The ladder: `baseline` kept → `baseline` fresh → `rescue` fresh → reseed | live `test_a_broken_release_walks_the_ladder_to_rescue_with_a_note_at_each_step`; `harness/watchdog.py` `Recovery.failure` |
| `done`/`reset` try `experimental`, then `baseline`, then `rescue` | `harness/watchdog.py` `Recovery.elective`; live 9.1 and 9.4 |
| Exits 0/42/43/44/45 and their actions; three clean exits in 120 s is a fault | `harness/watchdog.py` `plan_recovery`; `harness/tests/test_watchdog.py` |
| 44 pauses 60 s plus up to 30 s | `harness/watchdog.py` `environment_pause_seconds` |
| The pump's entries survive runs, repairs and restarts; its processes die with the container, keepalives and intervals start again, a spent one-off stays spent | `pump/pump.py` `restore_records`; `/pump` is a persistent bind |
| A crash is caught and the code restored, for as long as the agent's watchdog can catch it; a hung watchdog is brought back by nothing | `harness/watchdog.py` `run_watchdog`; spec §3.4; `scripts/status.py` reports it as stale and does not act |
| `/shared`, siblings' services, the window's disk and the fleet's spending limit are common, so one agent's actions land on the others | `scripts/volume_images.py` `SHARED` (`shared`, `diode`); `worknet`; `recorder/core_caps.py` fleet ledger |
| Per-agent and fleet hourly caps; a refusal exits 44 | `recorder/core_caps.py`; live 9.7 and the fleet-cap check |
| Archived conversations: the newest twenty kept per directory, within 128 MiB (tombstones) and 64 MiB (git), the one just made always; only the reserved names pruned | `harness/watchdog.py` `prune_archives`; `harness/tests/test_archive_pruning.py`; `tests/test_doc_claims.py::test_the_brief_states_the_archive_bound_the_watchdog_keeps` |
| A reply that cannot be recorded is not given | `recorder/tests/test_recorder_custody.py::test_a_failed_transcript_withholds_the_answer_and_the_usage_is_charged` (John's decision, plan 4b) |
