# #23 clock seam — read-only mapping (Explore agent, 2026-10-12, vehicle HEAD 7a87eb8)

## Mapping for vehicle #23, the clock seam (WP08 child 5). Read only, at HEAD 7a87eb8.

V = /tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9
ADR = V/docs/decisions/0002-mission-clock-and-continuity.md

### 1. ADR 0002

**Definitions**
- **dt / tick:** `tick_hz: 50`, MET is an integer tick count (ADR:38, :65). The live deadline is "`20 ms / m`" (ADR:80).
- **Cycle (ADR:48-51):**
  > "one *publication period* — the executive claims every console, validates, steps `k` ticks with the accepted effects stamped at `offset_us = 0` of the first of them, and then publishes. "Rewritten every cycle" therefore means every `k` ticks of mission time"
- **Segment (ADR:56-57):** "one boot's stretch of a run … with its own `boot_id`, wall epoch and journal segment". This is the only definition of "wall epoch".

**A2 option text (ADR:275)**
> "The segment records a wall epoch at (re)start; tick `t` is *due* at `epoch + t·dt/m`; each cycle steps every tick that is due, up to a **catch-up burst bound** (ticks per cycle), then sleeps until the next due tick. Lag (`actual − due`) is recorded per tick; a **lag ceiling** (wall seconds behind) is C3's trigger. The two bounds are different numbers…"

**A recommendation (ADR:288-300)**
- "`m` is a run input recorded beside the seed and **required with no default**: the flag defaults to `None` (the rule `check_console_flags` already enforces for remembered flags), the checkpoint remembers it, and a first start that names nothing refuses".
- "`m` is **not published** to the windows".
- "Changing `m` between segments is permitted and journaled".

**A answers (ADR:302-314)**
- A2; `m = 1` for the first integrated run; lag ceiling 30 wall seconds.
- Burst bound:
  > "**`k` — no burst**: a scheduler that has fallen behind runs complete cycles back to back without sleeping, each claiming, stepping `k` ticks and publishing, until it is on schedule"

  The operator withdrew an interim `2k`. Shedding (C2) is "the only pressure valve". Feasibility at m=1, k=5 is about 76 ms per 100 ms cycle with ten windows (ADR:316-327).

**B (ADR:329-380)**
- ADR:353-358:
  > "**The claim cadence is the publication cadence.** Each cycle the executive claims every console once, validates, stamps the accepted effects at `offset_us = 0` of the cycle's first tick …, steps `k` ticks — the remaining `k − 1` carry no effects — and publishes. A command … takes effect at most `k` ticks of mission time after it was written"
- ADR:360-364: catching up keeps "frame spacing and command latency … exactly `k` ticks"; "`k` ticks between frames" holds "whenever the executive is not shedding".
- ADR:371: "the static `HELP.md` (78 KB) and `README.md` (7 KB) rewrites move to a much slower cadence (C)". No number is given.
- ADR:372-373: "*Chassis*: `DIODE_POLL_SECONDS` is retired".
- ADR:375: `k` is "a run input, required with no default like `m`, remembered in the checkpoint".
- Answer (ADR:379): B2, `k = 5`.

**C, shedding (ADR:387, :405)**
- Order: shed static `HELP.md`/`README.md`, then frames; never ticks, results or the mirror (`state.json`); then dilate within the ceiling; then a recorded hold.
- C1 (ADR:386): "every tick's lag is journaled and the segment's missed-deadline count is in its manifest".

**N**
- J2 (ADR:614): "a full checkpoint every `N` ticks".
- ADR:630: "**`k` and `N` are independent**".
- ADR:652: "`N` a run input required with no default (recommended `tick_hz`…)".
- Answer (ADR:656): `N = tick_hz`.
- J(xxii) (ADR:770-776): N is in `clock.N` "taken from there by a resume, until child 5 makes it a run input"; "checkpoints at the end of every cycle whose tick is a multiple of `N`".
- J(i) (ADR:665-666): "Under child 5's `k` the `k` rows of a cycle can share its one `fsync`."

**Remembered versus named (G, ADR:514-520)**
> "On a fresh start a missing `m`, `k` or `N` refuses. On a resume: … `m`, `k`, `N`, the bounds, `--max-batch` and `--closed-interlock` may be named anew and the change is journaled as a segment event"

The checkpoint's clock inputs are `m`, `k`, `N`, burst bound and lag ceiling (ADR:496).

**Consequences and children**
- ADR:1078-1080:
  > "`tools/console.py`'s `main` ("an executive always starts at tick 0"), `--poll`, `--cycles` and `--journal` change under A2, B2 and J2; … `check_console_flags`' rule covers the new remembered flags."
- Acceptance (ADR:1065-1068): per-tick lag reported as p50/p95/p99/max plus missed-deadline count. That bullet also includes shedding, the ceiling and pause, which belong to children 8 and 9.
- Child 5 row (ADR:1116): "With `m` and `k` set, the number of ticks between two frames is `k` regardless of machine load; a command lands within `k` ticks; the lag series is reported p50/p95/p99/max; a start naming no `m` refuses".
- ADR:1127-1129: "Child 5 still ships with `m`, `k` and `N` *required* and no default: the accepted values (`m = 1`, `k = 5`, `N = tick_hz`, burst `k`, ceiling 30 s) are what the deployed stack and the manifest name, not what the console assumes."
- Cross-repo item 3 (ADR:1092-1093): "`DIODE_POLL_SECONDS` retired; `m`, `k`, `N`, the burst bound and the lag ceiling passed through (required: a stack that names none refuses to start, by design)".

### 2. tools/console.py today

**Flags (main, :5458)**
- `--poll` (float, default 1.0, "seconds between cycles") :5474.
- `--cycles` (int, default 0, meaning until interrupted) :5475.
- `--journal` :5502; `--max-batch` (None) :5494; `--closed-interlock` (None) :5476.
- There are no m, k or N flags.

**Loop**
- `run()` :5752-5802. `--cycles` counts this invocation's cycles; a resume continues the tick (:5763).
- :5768-5773: `while args.cycles == 0 or ran < args.cycles: executive.cycle(); time.sleep(args.poll)`.
- No wall epoch, no monotonic clock and no lag measurement exist anywhere in console.py. "lag" only appears in instrument prose.
- Banners print `poll=…s cycles=…` at :5879-5880 (resume) and :6116 (fresh).
- Module docstring :42-44 ("One tick per cycle, multiplier undecided … `--poll` is a wall-clock sleep") and examples :182-183 use `--poll 1`.

**`Executive.cycle()` :3064-3183, exactly one tick per cycle**
1. `tick = self.tick` (:3079).
2. Per window: `open_handles`, then `_settle` deferrals (due if `self.tick >= due_tick`, :3627). Then `_ingest`, which claims and validates (:3129-3133). Effects are collected.
3. One `advance(...)` step (:3145), `self.tick += 1` (:3149), lineage.
4. `_record_cycle` (:3155) writes one tick row, with every healthy window's `published` mark, and fsyncs.
5. `_write_root_record`.
6. `window.publish()` for each window (:3159-3174).
7. Cadence checkpoint `if self.tick % self.checkpoint_every == 0` (:3178).

**Stamps**
- Receipt tick: `Verdict.tick = self.tick` at validation (`_verdict` :3557-3560). That is the pre-step tick, i.e. the tick the cycle started at.
- `offset_us`: `Effect(0, verb, arguments)` at :4094. The receipt line is `tick={verdict.tick} offset_us={offset_us}` (`Window.receipt` :4766-4776; replayed form :2498).
- Replay applies dwell at `(tick-1)*tick_us + offset_us` with the post-step row tick (:2418). This is consistent with receipt tick = start tick.
- Frame: `write_frame` :4919-4954. `met_s = executive.tick * tick_us / 1e6` is the post-step tick, and `sim_step`/`state_revision` = tick. One frame per cycle, named `{seq:03d}.json`.

**Static files**
- `publish()` :4779-4837 rewrites every cycle: results → frame → `state.json` → `HELP.md` and `README.md` (:4815-4816, from cached text generated once at :2953-2954) → `pending.json` (with `ticks`).
- The docstring (:4780-4784) says "Every cycle … a hand-edit lasts until the next cycle". This is the line to change for the slower cadence.

**Clock state and N**
- `Executive.__init__` takes `checkpoint_every` (an in-process seam), defaulting to `mission.yaml tick_hz` (:2813-2820).
- `self.clock = {"N": self.checkpoint_every}` (:2891-2892).
- The segment header has `wall_epoch: utc_now().isoformat()` (`_append_record` :3477-3483). It is written at the boot's first record append, which happens after the first step, and only when journaling. It is not a scheduler epoch.

**Resume**
- `resume_executive` :5089. N comes from `checkpoint_every or body["clock"]["N"]` (:5148); after `restore_state` it does `executive.clock = {**executive.clock, "N": …}` (:5205-5206).
- Named changes are journaled at :5232-5238: `run_inputs["max_batch"] = [old, new]` and `run_inputs["tripped_interlocks"]`. They go into the `resumed` event's `"run_inputs"` (:5291) and `Resumption.run_inputs` (:5027). **This is where an m/k/N change slots in.** `main` passes only `max_batch` and `closed_interlocks` into it (:5843-5855).
- `identity_refusal` :4960-4989 refuses a changed scenario, seed, phase, ring or slugs. m/k/N must not go there, because they may change.

**`check_console_flags`** (`V/tools/check_vehicle.py:18321-18438`)
- Rule: a flag whose dest is remembered must default to None.
- The remembered set is the root-record keys plus `_checkpoint_run_keys` (:18280-18302), which reads **only the `run` dict literal in `capture_state`**, with `CHECKPOINT_RUN_FLAG_DESTS = {"tripped_interlocks": "closed_interlock"}` (:18277).
- The `clock` section (m, k, N, burst_bound, lag_ceiling_s) is not read. To cover new `--m/--k/--N` flags, the check needs extending to the `clock` keys, or the clock values need to move into `run`, plus a dest mapping.
- The console's own explanation of the rule is at console.py:257-271; `resolve_remembered` is at :364.

**tools/measure_clock.py**
- Times `plant.step`, three compare-point encoders (contract, floor, tagged), `Executive.cycle` with and without a record at 1/2/10 windows (one tick per cycle), quiet, verdict and full-batch cycles with counted fsyncs, the checkpoint-shaped write, and the record read cost per row.
- `timed()` reports p50, p95 and max only, not p99 (:86-98).
- It is cost measurement, not lag. It calls `Executive(...)` and `.cycle()` directly (:295-343).
- Its `checkpoint_shaped` clock uses lowercase `"n"` and has no `burst_bound` (:178), which is inconsistent with `CLOCK_INPUTS`.

### 3. tools/checkpoint.py

- `CLOCK_INPUTS = ("m", "k", "N", "burst_bound", "lag_ceiling_s")` (:134). All keys always exist; they are null until child 5, except N (docstring :28-31).
- `capture_state` (:273-318):
  - `run` = {scenario, seed, phase, phase_entry_seq, tripped_interlocks, max_batch, allowance_ceiling} (:293-301).
  - `clock = {name: executive.clock.get(name)}` (:302).
- `restore_state` sets `executive.clock = dict(body["clock"])` (:366).
- Structure schema: `clock: dict.fromkeys(CLOCK_INPUTS, object)` (:425). The only clock validation is that `clock.N` is a positive int (:517-519). Nothing validates m or k yet.
- The header carries `tick_hz` as a compatibility field (:950).

### 4. Chassis (/home/john/space_chassis, checked out on `aurora-port` at 6135575)

- `containers/serve_vehicle.sh`: one console per slug.
  - `DIODE_POLL_SECONDS` default 5 (:32, :44, :47).
  - Launch at :109-117 passes `--dir --diode-dir --slug --scenario --seed --ring-slots --poll "$DIODE_POLL_SECONDS" --cycles 0`.
- Branch `vehicle-adoption`: `serve_vehicle.sh` `exec`s one console with `--state-dir /state`, `--poll "$DIODE_POLL_SECONDS"`, `--cycles 0` and repeated `--slug` (:41, :56, :87-104).
- `docker-compose.yml` sets `DIODE_POLL_SECONDS: ${DIODE_POLL_SECONDS:-5}` on the `diode` fixture (:1896) and on `vehicle` (:1934). They are generated by `scripts/build_compose.py:284` (diode) and `:324` (vehicle), on both branches. `.env.example:126` has `#DIODE_POLL_SECONDS=5`.
- **`contract/fake_diode.py:40` also reads `DIODE_POLL_SECONDS`.** Only the vehicle's use can be retired.
- `contract/diode_probe.py:390`: `--poll-seconds` (default 5, "the implementation's cycle").
- Chassis tests pinning it, in `tests/test_vehicle_reconciliation.py`:
  - :206-212 launches `console.py --poll 0.05`.
  - :571/:573 sets `DIODE_POLL_SECONDS="0.05"`.
  - :610 (:622 on vehicle-adoption) asserts `argv[argv.index("--poll")+1] == "0.05"`.
  - :623 on vehicle-adoption asserts `--cycles 0`.
- `governance/chassis/records/2026-10-10-aur-gov-04-interface-report.md:112`: "#23 clock seam | `m/k/N` flags; retires `--poll` | change `serve_vehicle.sh` to the vehicle's spec | vehicle specifies, chassis implements".
- **Interface delta:** drop `--poll` and `DIODE_POLL_SECONDS` from the vehicle service. Add required m/k/N, e.g. new `VEHICLE_M/K/N` env vars passed through `serve_vehicle.sh`, compose and `build_compose.py`. If none are named, the container exits 3 and loops under `restart: unless-stopped`, by design. Keep `--cycles 0`. Fix the three chassis test pins.

### 5. Vehicle tests pinning `--poll` / `--cycles` (V/tests/test_vehicle_config.py)

Ninety `"--poll"` literals, mostly `"--poll", "0"`. Function names with def line and hit count:

- `test_a_deferred_command_that_waited_too_long_expires` 5734 (1)
- `test_a_run_can_say_which_scenario_it_is` 10872 (5)
- `test_the_telemetry_ring_is_bounded_and_accounts_for_its_losses` 11060 (6)
- `test_a_restart_may_not_re_bound_the_ring_and_says_so` 11173 (3)
- `test_the_window_s_sixth_file_is_generated_from_the_configuration` 11239 (2)
- `test_a_state_the_compare_point_refuses_stops_the_run_at_its_last_consistent_tick` 21338 (1)
- `test_one_world_per_directory_is_enforced_by_a_lock_and_a_binding` 22147 (6)
- `test_the_entrypoint_serves_two_slugs_from_one_executive` 22326 (2)
- `test_the_boot_marker_is_written_by_a_serving_start_and_its_name_cannot_be_a_journal` 23107 (2)
- helper `start` 24639 (2)
- `test_the_lock_moves_into_the_state_dir_…` 24734 (2)
- `test_without_a_state_dir_the_lock_and_the_journal_are_where_they_were` 24825 (1)
- `test_a_journal_that_cannot_take_the_event_…` 25212 (1)
- `test_an_explicit_journal_inside_the_diode_dir_…` 25281 (1)
- `test_a_state_dir_or_journal_spelled_through_the_diode_dir_…` 25413 (1)
- `test_a_symlink_loop_…` 25472 (1)
- `test_every_write_the_start_makes_for_itself_…` 25497 (1)
- `test_a_state_dir_reached_through_a_link_…` 25591 (1)
- `test_a_link_flipped_in_a_tight_loop_…` 25632 (1)
- `test_a_component_swapped_…` 25673 (1)
- `test_a_start_opens_its_state_dir_and_its_journal_directory_once_each` 25712 (1)
- `test_a_record_that_cannot_be_made_durable_stops_the_run_…` 26481 (1)
- `test_a_restart_with_the_same_arguments_resumes_…` 28796 (2)
- `test_a_console_killed_with_sigkill_…` 28843 (2)
- `test_a_restart_naming_another_scenario_seed_ring_bound_phase_or_slug_set_…` 28880 (6)
- `test_a_restart_naming_a_new_max_batch_or_closed_interlock_is_accepted_journaled_…` 28916 (3). This is the template for an m/k/N change test; it asserts `run_inputs` at :28929/:28933.
- `test_a_corrupt_or_incompatible_checkpoint_…` 28936 (1)
- `test_a_new_worlds_genesis_checkpoint_is_mandatory_…` 28967 (1)
- `test_a_resume_checkpoints_the_recovered_tick_…` 28993 (2)
- helper `interrupted_console` 29068 (1)
- `test_a_run_ending_cleanly_checkpoints_…` 29095 (1)
- `test_a_resume_reads_and_writes_its_state_only_through_…` 29170 (1)
- `test_a_resumed_world_whose_boot_tore_…` 29222 (4)
- `test_a_successor_whose_header_is_damaged_…` 29300 (1)
- `test_an_io_error_on_the_resume_path_…` 29594 (1)
- `test_a_state_directory_holding_a_record_and_no_checkpoint_…` 29807 (1)
- `test_the_diode_directory_is_resolved_once_…` 29858 (2)
- `test_a_clean_end_checkpoint_that_cannot_be_written_…` 29895 (1)
- `test_a_restart_naming_another_journal_…` 29921 (3)
- `test_the_confinement_checks_use_the_one_resolution_…` 29945 (1)
- `test_an_io_error_scanning_a_fresh_state_directory_…` 30193 (1)
- helper `start_path_scenario` 30490 (4)
- `test_a_window_directory_is_checked_through_the_held_diode_handle_…` 30570 (2)
- `test_a_corpus_directory_that_cannot_be_listed_…` 30647 (2)
- `test_a_clean_ends_checkpoint_event_written_in_part_…` 30830 (3)
- `test_a_close_that_fails_on_the_way_out_…` 30940 (1)
- `test_a_refusal_is_reported_when_the_executive_then_fails_to_close` 31043 (1)
- `test_a_corpus_file_that_cannot_be_read_…` 31095 (1)

Tests that pin one tick per cycle, cadence or static files:
- `test_the_executive_checkpoints_every_n_ticks_at_the_end_of_a_cycle_and_records_n_in_its_clock_inputs` 28548 asserts 49 cycles = no checkpoint, 50 = tick 50, and `clock.N == 50`.
- `test_the_window_s_sixth_file_is_generated_from_the_configuration` 11239 checks README/HELP written (:11330-11333).
- `test_the_ring_counts_frames_by_number_and_survives_the_thousandth` 23299.
- `test_a_kill_after_a_cycles_results_and_before_its_frame_continues_seq_past_the_marked_frame_and_met_s_never_decreases` 27758.
- `test_a_record_with_one_missing_cycle_refuses_replay_by_name` 25935.
- `test_every_publishing_window_has_its_published_tick_marked_durably_before_its_frame_or_mirror` 26278.
- The file has 220 `.cycle()` calls; essentially all assume one cycle = one tick.

### Ambiguities and contradictions

1. **A2 option text versus its answer.** ADR:275 says "steps every tick that is due, up to a burst bound, then sleeps". The answer (ADR:305-308) and the issue say whole k-tick cycles back to back with burst = k. The answer governs. It is unclear whether a separate burst flag is wanted at all: the issue's required flags are only m, k and N, while `CLOCK_INPUTS` and ADR:1092 also list burst bound and lag ceiling. The ceiling belongs to child 8 (#26).
2. **Epoch on a resume.** `epoch + t·dt/m` with absolute t would make a resumed segment instantly far behind. "The segment records a wall epoch at (re)start" implies `epoch + (t − segment_first_tick)·dt/m`, but this is not stated. The only existing `wall_epoch` is a UTC stamp taken at the first record append, after the first step and only when journaling. It is not a monotonic scheduler epoch.
3. **"Lag per tick" and "missed deadline" are undefined for k ticks stepped together.** Is "actual" each tick's step completion or the cycle's? Is a miss `lag > 0` or something else against `20 ms / m`? Where the series and percentiles are reported (journal rows, an event, the clean-end summary) is also unspecified.
4. **Checkpoint cadence.** `tick % N == 0` at :3178 only fires if k divides N. Fine for 5 and 50, but an arbitrary k (or a resume at a tick not aligned to k) can skip it. Either require k | N or use "crossed a multiple of N".
5. **Receipt tick.** Today it is already the cycle's start (pre-step) tick with offset 0. The frame then describes start + k, and `met_s` is post-step. "First tick of the claiming cycle" matches today's convention, but the issue's wording could be read as start + 1.
6. **Deferrals.** They are checked once per cycle, so with k > 1 a deferral due mid-cycle settles up to k − 1 ticks late. The ADR does not address this.
7. **Static-file cadence.** The value is unspecified ("much slower cadence"). C2 sheds those files first, which belongs to child 8.
8. **Required flags with no default.** It is unclear whether `--init`, `--plan` and `--plan-json` also refuse without m/k/N; the ADR says only "a first start". Tests use `--poll 0` for fast runs, and A3 is excluded as the live policy, so the tests will need a large m or an in-process seam such as the existing `checkpoint_every`.
9. **`DIODE_POLL_SECONDS` retirement.** The chassis fixture `fake_diode.py` still uses it, so only the vehicle service's use can go.
10. **`check_console_flags`** reads only the checkpoint's `run` section. It will not hold the clock flags unless it is extended (see §2).
11. **Record rows.** The record is one row per tick and every row needs a `published` key. With k ticks per cycle only the last row carries marks; J(i) allows the k rows to share one fsync. Today `_record_cycle` and replay's "missing" check (:2405-2408) assume one row per cycle.
12. **ADR:1065-1068** folds shedding, the ceiling hold and pause into the same acceptance bullet as the lag report. Only the lag and missed-count part is child 5's; the rest is children 8 and 9 (#26, #27).
