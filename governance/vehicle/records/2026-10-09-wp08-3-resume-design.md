> **Historical record**, copied into governance on 2026-10-10 from a session scratchpad. Paths under `scratchpad/` or `/tmp/` inside it were ephemeral and may no longer exist; line numbers refer to the commits it names. Do not edit — supersede with a new dated record.

# WP08 child 3 (#21): resume — design note (phase 1)

Base: vehicle `main` 64fc58c (worktree branch `codex/wp08-resume`). Every `file:line` below is at
that commit. Nothing in the repository was edited; two feasibility probes ran in scratch
(`scratchpad/probe-wp083/`), and their findings are §0.

## 0. What the probes showed (both block the naive design)

**P1: resume works mechanically.** I ran an in-process world with two windows and a command script:
checkpoint at tick 5, killed between cycles at tick 9, `choose_generation` → `read_record` →
`replay_record` → a fresh `Executive` → `attach` ×2 → `restore_state`, then continued to tick 20.
Per-tick `(state_hash, lineage_head)` for ticks 1–20 equal the uninterrupted run's. `truth`,
`lineage_head`, every window's `receipts`, `accepted` and `deferred` are equal. `seq` continues
(9 → 20, frames 0…19). The two segments concatenate (0–9, 9–20). A replay of the whole record from
the tick-5 checkpoint also matches the uninterrupted run.

**F1: `attach()` regresses a resumed window before `restore_state` can run.** Just after `attach`,
the probe found `state.json.executive = {world_id: null, tick: 0}`, `pending.json = {ticks: 0,
seq: 0, world_id: null}`, and the root record set to `world_id: null, tick: 0`. Two calls do this.
`attach` → `Window.prepare` (console.py:3321–3354) rewrites the mirror and `pending.json` with tick-0
values. `attach` → `_write_root_record(self.tick)` (2252) writes the unbound record. But
`restore_state` refuses unless every window is already attached (checkpoint.py:322–333). So the
resume must attach **without preparing and without writing the root record**, then restore, then
write the root record from the recovered state. Before the first resumed cycle, the resume writes
nothing in a window except re-published results and a re-made missing directory. `prepare` already
leaves an existing `console.json` alone (3351–3354), so unclaimed commands survive.

**F2: a torn first append crash-loops.** `_append_record` writes a boot's header and its first row
in one `write` (2548–2564). Suppose a kill tears that write in a segment file that holds only
startup events (the resumed boot's `resumed` event, below) or nothing. Then `read_record` refuses:
`corrupt … not a JSON object and no segment precedes it` (`_verified_lines`, 1576–1578). The probe
reproduced this, and every later restart would refuse the same way. The fix: at the end of a file, a
torn line with `header is None` is a boot torn before its header, and it is dropped. This is safe
because nothing of that cycle was published: the row's `fsync` comes before `_write_root_record`
and `publish` (2364–2373).

## 1. Recovery procedure (and what it reuses)

`main` keeps everything up to `choose_generation` (3790–3929): canonicalise, open the state
directory once (`state_fd`), lock, check `serves.json`, choose the generation. The `#21` refusal
(3985–3993) is replaced by the following, in this order.

1. **Cheap refusals first, with nothing replayed and nothing written.**
   - `--init` refuses (§6).
   - Named flags are compared with the checkpoint body (§4).
   - A *readable* root record naming another world refuses (`reconcile_root_record`'s `"refuse"`,
     2051–2056). It needs only `world_id`, so it stays ahead of the replay.
   - `--plan` answers from the checkpoint's identity, as it does now (3994–3996, 4036–4073), but
     only after the flag check.
2. **Read the record through the held handle.**
   - With `--state-dir` alone: `read_record(state_path, dir_fd=state_fd)` (1667–1714).
   - With an explicit `--journal`: today's `dir_fd=` form *lists* `journal.*.jsonl` (1681), which
     is wrong for an explicit file, and the path form re-resolves the path. I add a `names=` argument
     so the file is read through `journal_fd` by name. The record is read from where this boot will
     write it. If an operator changes `--journal` across a restart, the record no longer reaches the
     checkpoint's last segment, and `replay_record`'s `join` check (1833–1838) refuses by name.
3. **Replay.** `replay_record(world, chosen.body, record)` (1789–1942), unchanged. It advances every
   recorded row after the snapshot tick `T` through to the last durable row `L` with `advance` and
   `dwell_after_effect`. It holds each tick to its compare-point and lineage link, and it applies the
   counters, window deltas and published marks. It returns a checkpoint-shaped body at `L` whose
   `segments` carry the chain reached. A `RecordRefused` exits 3: "the record cannot continue the
   checkpoint at <file>: <refusal>".
4. **The tail between the last durable row and the published tick is empty.** Since child 4, every
   cycle writes a row (ADR 0002 J amendment (i), lines 662–665). `published_tick` is set only after
   that row's `fsync` (`_record_cycle`, 2469–2471), and a mark is its row's own tick (`_row_problem`,
   1384). So every published tick is ≤ `L`. J rule 2's "step effect-free ticks to the published
   tick" (633–636) is vacuous, and the resume asserts `max(published_tick) ≤ L` rather than stepping.
   Under child 5's `k`, all `k` rows of a cycle still precede its publication, so this stays true.
   **Mission time resumes at `L` (F1).**
5. **Re-publication list.** `[u for u in unwritten_results(record) if u["tick"] >= T]` (1945–1973;
   `u["tick"]` is the row's tick − 1). §2 says why the domain is "after the snapshot".
6. **Root record, against the recovered state** (#20 note 1). The expected record is
   `root_record_from_checkpoint(replayed.body)` (2011–2031), whose tick is `L`, not the snapshot's.
   - **agree**: no event.
   - **routine**: every identity key in `ROOT_RECORD_IDENTITY` agrees except `tick`, with
     `T ≤ record.tick ≤ L`. This is the normal restart, because the record is rewritten every tick
     after the row (2365). The genesis case also counts: `world_id: null, tick: 0` beside a tick-0
     checkpoint. It is recorded *inside* the `resumed` event (§3) as `root_record: "routine: tick X in
     [T, L]"` and rewritten. No `root_record_rewritten` event, so that event keeps meaning
     "tampered or damaged".
   - **anything else**: the existing rules (`reconcile_root_record`, 2047–2060) apply: rewrite plus a
     `root_record_rewritten` event, written first (3949–3971). `tick > L` falls here too, because
     `fsync`ed rows do not vanish.
   - **EISDIR**: a directory planted at `.executive.json` stays a refusal by name. The resume is
     designed for the chassis's per-slug mounts. Its `aurora-port` compose binds each agent to
     `diode/data/<slug>` only (docker-compose.yml:82–83 and the nine like it), so the root is the
     vehicle's (the child-2 reasoning in ADR 0002 H, 557–561). Chassis `main` (fa43b25) still mounts
     `./volumes/diode:/diode` on every agent, so there it would be an agent-held stop button. That is
     a precondition the chassis adoption must state (R3).
7. **Construct** (`resume_executive`, a new module function that `main` and the tests both call):
   - `Executive(world, diode_dir, phase=body.run.phase, scenario, seed, max_batch=…,
     record_slugs={slug: ring_slots}, state_dir=state_path, state_fd, journal, journal_dir_fd,
     boot_id)`. The phase must be the checkpoint's or `restore_state` refuses (checkpoint.py:335–340).
   - `attach(slug, ring_slots=…, prepare=False)` for each of the checkpoint's slugs (F1).
   - `restore_state(executive, replayed.body)` (checkpoint.py:316–371) sets world, tick, truth, dwell,
     lineage, receipt counter, segments, clock, rng, each window's `seq`/`receipts`/`deferred`/`arms`/
     `published_tick`/spend.
   - Then the operator's live inputs (§4): `max_batch` if named, `tripped |= named interlocks`.
8. **Journal, then write.**
   - The `resumed` startup event (§3) is appended to this boot's segment file with
     `append_journal_line(…, dir_fd=…)` (927–955).
   - Then any `root_record_rewritten` event.
   - Then the root record is rewritten: `write_json_atomic(RECORD_FILE, executive.root_record(),
     dir_fd=diode_fd)`. "No rewrite goes unjournaled" (3940–3945) still holds.
   - Then `serves.json` is written (`serves_refusal`, 3885–3896).
9. **One pass over the windows, with handles.** For each window: `open_handles` (`WindowAbsent` →
   `prepare`, the live path at 2315–2325), then:
   - **(a) prime `variables`.** `read_ingress("console.json", dir_fd=root)` (516–547), read without
     claiming; set `window.variables` only if `variables` is an object. ADR 0002 G keeps `variables`
     out of the checkpoint (lines 503–505) and in the agent's own console, which the claim preserved
     (3393–3398). Without priming, the first resumed cycle settles due deferrals with every gate at its
     default, because `_settle` runs before `_ingest` (2333–2342). The uninterrupted run would have
     used the preserved map.
   - **(b) re-publish** that window's unwritten results (§2).
   - **(c) close.**

   A window that cannot be opened is a recorded failure (`_record_failure`), **not a refused start**.
   A planted link or file in an agent's window must not hold the vehicle dark at every restart (ADR
   0002 H's stop-button reasoning). Today's "any failure at attach refuses" (4169–4175) stays for
   fresh starts only.
10. **Banner and lock line.** The banner says "resumed world W at tick L (checkpoint T, replayed
    L−T, republished n)". Then the loop runs as today, with the cadence in §5.

**Commands across the downtime.** Unclaimed commands sit in `console.json` untouched (the probe and
3351–3354). The first resumed cycle claims them after due deferrals settle, and they are validated
against the truth at `L` and stamped at `offset_us = 0` of tick `L`. No mission time passed (F1), so
no deferral came due and no queue aged during the gap.

**Claimed but unrecorded at the crash** (kill after the claim's durable rewrite, 3393–3398, and
before the row's `fsync`): **lost, with no result.** This is the contract's own rule
(diode-contract.md:67–72: "the batch was already claimed … A crash mid-batch loses the rest of that
batch; it never replays it") and ADR 0002 J (viii) (683–684). Deferrals that cycle settled are not
lost: their removal was never recorded, so the replayed queue still holds them and they settle on
the first resumed cycle.

**This is where chassis commitment 1 must be qualified.** "Every claimed command has exactly one
result" holds for every command **whose cycle's row is durable**. Closing the gap would mean
recording the raw batch durably before the claim's rewrite — a new row type (`vehicle.record.v3`)
and one more `fsync` per commanded cycle — which the contract does not require. I recommend against
it.

## 2. Re-publication, exactly once

**Recording the re-publication itself is the crux.** A `results_written` note is bound to its own
segment's boot and its row's receipts (1555–1564). The resumed boot therefore cannot note the dead
boot's receipts. It cannot append to the dead segment (that breaks `previous_chain`, 1746), and its
own first row's receipts are its own. Options:

- **(a)** A chained carry-over note as the new segment's first line, with the subset check moved to
  the concatenated pass. That is `vehicle.record.v3`.
- **(b)** An unchained `results_republished` startup event that `unwritten_results` honours.
- **(c, recommended)** Make re-publication idempotent on disk and leave the record alone.
  - **Bound the domain.** Re-publish only verdicts in rows after the snapshot tick `T`. Every
    checkpoint is taken at a cycle boundary after every window's publication (§5), so each row at or
    before `T` was already published, or failed live.
  - **Dedupe on disk.** Before writing, look in the window's `output/` handle for the exact receipt
    line `receipt: world=W seq=<local> window=<slug> tick=<t> offset_us=<o> state=<s>\n`. That line
    is unique per (world, window, local) (`Window.receipt`, 3475–3485).
  - **How the lookup works.** Only names of the form `<stamp>_<slug>_<sanitise(recorded command
    prefix)>…` are candidates. Each candidate must be a regular file (`lstat` through the handle),
    and only its last 512 bytes are read.
  - **What it closes now.** It makes a second resume after a partial re-publication write nothing
    new. It also closes J (iii)'s residual window (a kill after the result file and before its note),
    with wall-stamped names, before child 12. Child 12's exact-name skip (#30) can replace it later.
  - **Order** (rule 3): write the files, each `fsync`ed (`write_text_atomic(…, sync_file=True)`),
    `fsync` `output/`, then a `results_republished` startup event (window, local, tick, written or
    already on disk) for the operator. The dedupe does not depend on that event.
  - **Bodies.** The recorded body is written, then the receipt block. If the body was cut
    (`body_sha256` present), one sentence says it was recorded to 4 KiB and gives the hash and length.
    A fingerprint-only receipt (1214–1220) produces one result: the file name uses the recorded verb
    prefix, and the body says the vehicle decided the command (state, receipt) but kept only its
    fingerprint, with both hashes. That is still one result per command.

**Residual, named in the test:**
- **When it can happen.** A kill after a result file and before its note, followed by the agent
  deleting that file during the downtime.
- **What happens.** The result is re-published once more.
- **Why accept it.** The contract lets agents clean up `output/`, and the window is a single cycle's.
- **Planted copies.** An agent can also plant a fake copy to suppress its *own* re-publication. That
  is self-harm only.

## 3. Boot, segment and downtime

- **What changes and what continues.**
  - A new `boot_id` is drawn in `main` (3900).
  - Each `Window.boot_id` is new because the `Window` is new (3254), so frames show the restart.
  - `world_id` is restored. `seq` continues at `mark.seq + 1` (replay 1914–1918; L1). `000.json` is
    never rewritten, and `ring_frames`/`ring_losses` (3586–3615) count the old boot's frames below
    `seq`.
  - If the crash came after the row and before the frame, that frame number is never written and
    shows as one loss. That is "a mark overstated … is safe", J (ii).
- **Segment.** The header is written with the first resumed row (2532–2547). Its `previous` and
  `previous_chain` come from `segments[-1]`, which `restore_state` set from the replayed body, and
  its `first_tick` is `L`. `concatenated` (1717–1751) then joins it. If the last segment the replay
  reached is header-only, (xviii) keeps it in the history.
- **The `resumed` startup event** is unchained and the operator's; `_verified_lines` skips it,
  1533–1534. It carries:
  - `wall_up` (now), `wall_down`, `wall_down_source`, `tick: L`, `previous_boot`.
  - `checkpoint: {file, tick: T, fell_back}` and `replayed: L−T`.
  - The root-record class, `run_inputs` changes, and pending.json advisories (§4).
- **`wall_down` is a proxy**, because rows carry no wall stamp; only headers carry `wall_epoch`
  (2544). It is the `st_mtime` of the predecessor's segment file, `os.stat(name, dir_fd=…)`: the
  time of its last `fsync`ed append, within one cycle of the crash. The source is labelled in the
  event. Child 10 (#28) may refine it (for example, a wall stamp in rows would be a v3 format). The
  record leaves no other trace of the gap: the trace is tick-keyed.

## 4. Flags, identity and the legacy checks

- **Identity.** Before anything else on a bound directory, `main` compares named flags with the
  checkpoint body. Any disagreement exits 3 with one stderr sentence that names the flag, both
  values and the file:
  > `--seed names 7 and the checkpoint /state/checkpoint.json records 3 for world <id>: a restart
  > resumes the world its state directory holds, and a different world is the operator's
  > --new-world (#28), not a changed flag`
  - **`--slug`**: `set(named) != set(body.windows)`, both sets shown sorted. `--slug` named nothing
    (`args.slug is None`, 3668–3673) resolves to the checkpoint's set on a resume and to `["vehicle"]`
    on a fresh start.
  - **`--scenario`, `--seed`**: compared with `body.run`.
  - **`--ring-slots`**: compared per window with `body.windows[s].ring_slots`. This is the existing
    sentence (4081–4088), now fed from the checkpoint.
  - **`--phase`**: the default becomes `None` (it is `"translunar_coast"` at 3674). Resolution goes
    named → checkpoint (resume) → `DEFAULT_PHASE = "translunar_coast"` (fresh). A named phase that
    differs from the checkpoint's refuses. Until child 11 the phase is constant, so this is plain
    equality.
- **Remembered, and changeable on a restart.** These are G's "may be named anew … journaled as a
  segment event" (514–520).
  - **`--max-batch`**: the default becomes `None` (it is `DEFAULT_MAX_BATCH` at 3697, so "named
    anew" is undetectable today). Resolution goes named → checkpoint → `DEFAULT_MAX_BATCH`.
  - **`--closed-interlock`**: the default becomes `None` (it is `[]` at 3680). A resume takes the
    **union** of the checkpoint's `tripped_interlocks` and the named ones. G says the flag "asserts a
    tripped interlock across a restart", so a restart never silently un-trips one. No flag can clear
    one; that is an ADR silence (§8).
  - Changes go in the `resumed` event as `run_inputs: {max_batch: [old, new], tripped_interlocks:
    [old, new]}`, and the next checkpoint captures the new values (`run`, checkpoint.py:278–286).
  - `check_console_flags` reads only `root_record`/`pending.json` keys (check_vehicle.py:18291+), so
    it does not force these three. Child 5's acceptance names that rule. Here the three defaults
    change by hand and a parser test pins them; extending the linter is left to child 5.
- **Legacy `pending.json` checks become advisory** beside a verified checkpoint (H, 552–553; #20
  note 2).
  - On a resume, every slug is the checkpoint's (the identity check comes first), so the refuse-only
    check (4090–4121) never fires: it runs only for slugs the record does not name, and `record =
    expected` (3996).
  - What replaces it: each window's `pending.json` is read with `read_json_bounded` through its
    handle. A `world_id` naming another world, or `ticks > L`, becomes an `advisories` entry in the
    `resumed` event and never a refusal.
  - The `bound` refusal (4123–4130) and the fresh-start legacy check stay, gated on
    `checkpoint_found is None`.
- **`--init`** on a directory whose state holds a checkpoint exits 3: "<state> holds world W at tick
  T, which a start without --init resumes; --init prepares an unbound directory (ADR 0001)". This
  keeps ADR 0001's "a bound record refuses every start, `--init` included".
- **`--plan`** passes the identity check, then answers from the checkpoint, with no replay and no
  write in the diode directory.
- **A fresh start (no checkpoint) on a state directory whose `journal.*.jsonl` holds a segment
  header** exits 3. One state directory is one world's (H). Without this, the new world's first
  segment is a second root, and every later resume refuses in `_chain` (1650–1652). The check reads
  only the first header line of each file. Event-only files from refused starts do not count.

## 5. Writing checkpoints (commitment 5)

- **Where.** `Executive.checkpoint()` runs `capture_state(self, self.compat,
  git_commit=self.git_commit)` and then `write_checkpoint(self.state_dir, body,
  dir_fd=self.state_fd)`.
  - `compat` and `git_commit` are computed once, in `__init__`. Measured here:
    `Compatibility.current` 4.5 ms and `git_commit` 1.9 ms, so they are not repeated every `N` ticks.
  - It runs only with a state directory. An explicit `--journal` alone has nowhere to put one.
- **Cadence.** At the **end of `cycle()`**, after the publication loop, when
  `self.tick % N == 0`.
  - It has to be at the end, because the checkpoint's segment `chain` must include the cycle's
    `results_written` notes. Those are appended inside `publish` (3503–3508), and replay's anchor
    check compares the chain after every line at tick `T` (1871–1876, 1921–1922). The end of the
    cycle is also when every window has published, which §2's domain needs.
  - `RecordUnwritable` propagates before it (2374–2375), so no checkpoint outruns the record.
  - Measured on the warmed ring: capture 5.3 ms + write 6.8 ms. The ADR estimated ≈ 9 ms (322–323).
- **`N` is not a flag here** (child 5 makes it one). `N = tick_hz` from `mission.yaml`, the accepted
  value (656–657). It is held as `executive.clock = {"N": N}`, so `capture_state` records it in
  `clock.N` (checkpoint.py:287), and a resume takes it from `body.clock.N` (`null` → `tick_hz`).
  - An in-process `checkpoint_every=` keyword exists for tests only; `main` never passes it.
- **Genesis checkpoint.** A fresh start with `--state-dir` (not `--init`) writes one at tick 0,
  after `serves.json` and the attaches and before the first cycle.
  - Without it, a crash before tick `N` finds a bound root record and no checkpoint, so choice D
    refuses (4123–4130) and the vehicle crash-loops dark.
  - With it, `segments` is `[]`, and `replay_record`'s "no anchor" branch (1830–1832) accepts a
    first segment with `previous: null`.
- **At a clean end**, a checkpoint is written:
  - when `--cycles` is exhausted;
  - on `KeyboardInterrupt` **only if it arrived between cycles**. Mid-cycle, the window counters can
    be ahead of truth: `_verdict` increments before the step (2610–2612 vs 2354). The executive keeps
    an `in_cycle` flag for this.

  Graceful SIGTERM is child 10.
- **A failed write** (`CheckpointRefused` subclasses, `ValueError`/`TypeError`) is a recorded
  failure under the stage `checkpoint`, on stderr, and **the run goes on**, as for the root record
  (2593–2606).
  - The record is what makes the run durable. `write_checkpoint` leaves a verifying generation at
    every step (checkpoint.py:621–635), so a failure costs only recovery time.
  - A failed clean-end checkpoint does not change the exit code.

## 6. Staying fd-relative (#20 note 3)

**One handle each, opened once in `main`:**
- **`state_fd`**: lock (3844), `serves.json` (1976–2008), `choose_generation(…, dir_fd=)` (3924),
  `read_record(…, dir_fd=)`, the `resumed` and republished events, the segment
  (`journal_dir_fd = dup(state_fd)`, 2146–2148), the cadence writes (`write_checkpoint(…,
  dir_fd=self.state_fd)`), and the mtime for `wall_down`.
- **`journal_fd`**: the explicit journal, read through it by `names=` (§1.2).
- **`diode_fd`**: the root record and the windows.

**Two remaining path re-resolutions, fixed in passing:**
- `Executive.__init__` reopens the diode directory with `open_directory(self.diode_dir.resolve())`
  (2213). `main` will pass `diode_fd=` (duplicated) instead.
- `serves.json` compares and writes `str(diode_dir.resolve())` (3915, 2006). It will use
  `diode_canonical.path`, which is already in hand (3799).

**The proof** is a test that counts `os.open`/`realpath` on the state directory's spelling across a
resume, extending `test_a_start_opens_its_state_dir_and_its_journal_directory_once_each`.

## 7. Oracle and kill injection

- **The oracle is the uninterrupted run's own compare-points.**
  - `recorded_run` (tests:25196) gives `(state_hash(truth), lineage_head)` and `window_counters`
    after each cycle, read from the live executive, never from the record or the replay. A second
    executive gets the same script and runs the same number of cycles.
  - The lineage excludes `world_id` (`lineage_link`, 1101–1106), so two independent executives
    agree.
  - Compared at every tick up to `T+100`:
    - the compare-point and lineage head;
    - `truth` and `dwell` dicts, the global and per-window receipt counters, `accepted`, `deferred`,
      `published_tick`;
    - the set of `(window, local, state, tick, command)` parsed from receipt lines in `output/`.
  - Not compared: `world_id`, `boot_id`, arm tokens (salted with `Window.boot_id`, 3074), wall
    stamps. `seq` must satisfy `resumed ≥ oracle`, and equal it unless a marked frame was lost at
    the kill.
- **Kill points.** These are in-process `SimulatedKill(BaseException)` hooks, the established
  pattern (tests:25561). After the kill, `executive.close()` stands in for the process ending, and
  `resume_executive` runs on the same directories.
  - K0, between cycles: no hook.
  - K1, after the claim and before the row: hook at `Executive._record_cycle` entry. The oracle is
    the script **minus that batch** (contract §2.2). Deferrals settled in that cycle settle on
    resume.
  - K2, after the row and before any result: hook at `Window.write_result`.
  - K3, after a result file and before its note: hook at `Executive._note_window_results`. The
    result is on disk; the dedupe must not write a second.
  - K4, after results and note, before the frame and mirror: hook at `Window.write_frame`. One frame
    number is lost; `met_s` never decreases.
  - K5, mid-checkpoint: `checkpoint._after_step` raising at each of `STEPS` during a cadence write.
    The resume reaches the same `L` whichever generation `choose_generation` returns.
  - K6, after a cadence checkpoint and before the next row: hook at the next cycle's
    `Window.open_handles`. The resume is at exactly `T`, with zero replayed rows.
  - K7, a torn first append: truncate the resumed boot's segment mid-header (F2).
- **Real process boundary.** One subprocess test starts `console.py`, waits for ≥ `2N` rows, sends
  SIGKILL, and restarts with the same arguments. Its oracle is an in-process uninterrupted quiet run
  of the same length, compared at every tick of the concatenated record.

## 8. Where the ADR is silent: recommended choices

| # | Silence | Recommendation |
|---|---|---|
| S1 | Where `wall_down` comes from | mtime of the predecessor's segment, labelled (§3) |
| S2 | A crash before the first cadence checkpoint | genesis checkpoint at tick 0 (§5) |
| S3 | Checkpoint at a clean end | `--cycles` exhausted; KeyboardInterrupt only between cycles (§5) |
| S4 | A checkpoint write that fails | recorded failure; the run continues (§5) |
| S5 | How re-publication is recorded and deduped | domain after the snapshot tick, receipt-line dedupe, an operator event; no record format change (§2) |
| S6 | Corrupt current checkpoint with a verifying previous one | use `choose_generation` unchanged: it already falls back (checkpoint.py:877–896, landed in child 1) and the record is never pruned, so the replay from the previous generation reaches the same `L`; `fell_back` goes in the `resumed` event. Commitment 3's exit 3 holds when **no** verifying previous generation exists (both corrupt, incompatible, foreign). Child 10 owns K2's test and the `--new-world` message. **Flag for the reviewers:** this is the ADR's K answer, and it is more available than the literal commitment |
| S7 | A root record ahead of the checkpoint | "routine" = agrees except a tick in `[T, L]` (§1.6) |
| S8 | `variables` across a restart | primed read-only from the console (§1.9a). If an agent rewrote `variables` during the downtime, a deferral due on the first resumed cycle sees the new map where an uninterrupted run would have seen the old one. Validation is not replayed, so this is not a determinism break |
| S9 | A window that cannot be prepared on resume | recorded skip, never a refused start (§1.9) |
| S10 | Commands claimed but not recorded at the crash | lost, per the contract; commitment 1 is qualified (§1) |
| S11 | A fresh start on a state directory that already holds a record | refuse (§4) |
| S12 | `--closed-interlock` on a resume | union; clearing one is WP05's or child 10's question |
| S13 | `--slug` named nothing on a resume | the checkpoint's set |
| S14 | The budget's wall clock (`Window.started`, 3255; the mirror at 3553–3558) | resets at a restart; this is child 7's (E2) |
| S15 | Arm tokens salted with the old `boot_id` | survive as stored strings (G1). `execute_event` compares strings (2976–2990). This cannot be reached today because `arm_event` is refused as an unevaluated interlock |
| S16 | `seq` when publication fails after the mark | optional one-line live alignment: if `publish` raised before `write_frame`, set `seq = mark.seq + 1`, so a live checkpoint and a replay agree on the next frame number. Not required for any acceptance item; reviewers may drop it |
| S17 | Retention and pruning | not here. The README handed it to "child 3 or 10" (README.md:19073–19079); I pick child 10 (R1) |

## 9. Risks

- **R1, restart time.** `read_record` verifies every segment end to end, and `replay_record`'s join
  re-streams the anchor segment, so a restart costs about 25 µs × rows × 2–3 passes
  (ADR 0002 (xx), 756–759). That is ≈ 3.6–5.4 min after a one-day boot and ≈ 30–45 min near mission
  end. F1 freezes mission time, so this is availability, not physics. Mitigation for child 10:
  - skip segments wholly before the checkpoint's anchor;
  - a byte offset in the checkpoint's segment entry for an in-segment seek;
  - retention.
- **R2.** The re-publication dedupe trusts `output/`, which the agent writes. The harm is limited to
  that agent (§2).
- **R3.** The EISDIR refusal and the foreign-world refusal assume the per-slug mounts. Chassis
  `main` does not have them yet; `aurora-port` does. The chassis adoption must ship them.
- **R4, engine identity.** Any change to the corpus or to `plant.py`/`console.py`/`faults.py` makes
  every saved world incompatible (exit 3, by design, I). Until child 10's `--new-world`, the
  operator's only exit is to clear both the state directory and the diode directory by hand. The
  chassis must not roll the vehicle image under a live world.
- **R5.** Every refused start opens one startup-event file; a crash loop grows the state directory
  (child 2's Opus 4). That is left for retention in child 10.
- **R6.** Restore changes semantics in places tests already pin: the `#21` refusal test (tests:24300)
  and any test that asserts `--phase`/`--max-batch` defaults. They are rewritten in the same commits,
  not deleted.

## 10. Tests (full-sentence names)

**Library, in-process:**
1. `test_a_world_killed_between_cycles_resumes_from_its_checkpoint_and_record_and_equals_the_uninterrupted_run_at_every_tick_to_t_plus_100`
2. `test_a_kill_after_the_tick_row_and_before_any_result_resumes_at_that_tick_and_publishes_each_recorded_result_exactly_once`
3. `test_a_kill_after_a_result_file_and_before_its_note_does_not_publish_that_result_a_second_time`
4. `test_a_second_resume_after_a_partial_re_publication_writes_nothing_new`
5. `test_a_kill_after_the_results_and_before_the_frame_continues_seq_past_the_marked_frame_and_met_s_never_decreases`
6. `test_a_batch_claimed_in_a_cycle_whose_row_never_became_durable_is_lost_and_never_replayed_while_its_settling_deferrals_are_kept`
7. `test_a_resumed_executive_keeps_world_tick_receipts_spend_deferrals_and_arms_and_changes_every_boot_id`
8. `test_no_window_local_receipt_number_is_issued_twice_across_a_resume`
9. `test_a_deferral_accepted_before_a_kill_settles_at_its_due_tick_after_the_resume_as_in_the_uninterrupted_run`
10. `test_a_dwell_started_before_a_kill_refuses_and_releases_at_the_same_ticks_after_the_resume`
11. `test_resuming_rewrites_no_window_file_to_an_earlier_tick_than_the_window_last_showed`
12. `test_a_resumed_window_honours_the_gate_variables_its_console_preserved_on_its_first_cycle`
13. `test_a_window_that_cannot_be_opened_on_resume_is_a_recorded_skip_and_the_world_resumes`
14. `test_a_boot_torn_before_its_segment_header_is_dropped_and_the_record_still_resumes`

**Cadence:**

15. `test_the_executive_checkpoints_every_n_ticks_at_the_end_of_a_cycle_and_records_n_in_its_clock_inputs`
16. `test_a_new_world_checkpoints_at_tick_zero_so_a_kill_before_its_first_cadence_resumes_instead_of_refusing`
17. `test_a_kill_at_every_step_of_a_cadence_checkpoint_resumes_to_the_same_tick_and_state`
18. `test_a_kill_between_a_checkpoint_and_the_next_row_resumes_at_the_checkpoints_tick`
19. `test_a_run_ending_cleanly_checkpoints_its_last_completed_cycle_and_an_interrupt_mid_cycle_does_not`
20. `test_a_checkpoint_that_cannot_be_written_is_a_recorded_failure_and_the_ticks_go_on`

**`main`, by subprocess:**

21. `test_a_restart_with_the_same_arguments_resumes_the_same_world_and_journals_the_downtime_gap`
22. `test_a_console_killed_with_sigkill_and_restarted_resumes_and_matches_an_uninterrupted_run_tick_for_tick`
23. `test_a_restart_naming_another_scenario_seed_ring_bound_phase_or_slug_set_refuses_with_one_sentence_naming_the_flag_and_both_values`
24. `test_a_restart_naming_a_new_max_batch_or_closed_interlock_is_accepted_and_journaled`
25. `test_a_corrupt_or_incompatible_checkpoint_with_no_verifying_previous_generation_refuses_naming_the_file_and_the_check`
26. `test_a_root_record_between_the_checkpoints_tick_and_the_recovered_tick_is_routine_and_any_other_disagreement_is_still_a_mismatch_or_a_refusal`
27. `test_beside_a_verified_checkpoint_a_legacy_windows_pending_json_is_advisory_and_never_refuses`
28. `test_a_resume_reads_and_writes_its_state_only_through_the_one_held_state_directory_handle`
29. `test_init_refuses_on_a_saved_world_and_plan_answers_from_its_checkpoint_after_the_identity_check`
30. `test_a_fresh_start_on_a_state_directory_that_holds_a_record_and_no_checkpoint_refuses`
31. `test_phase_max_batch_and_closed_interlock_default_to_none_so_a_restart_can_tell_named_from_unnamed`

**Changed, not added.** `test_beside_a_verified_checkpoint_the_root_record_is_rewritten_and_the_start_still_refuses_until_resume_lands` becomes "…is rewritten and the world resumes". `test_no_window_file_carries_hidden_state_before_or_after_a_checkpoint_and_a_restart` gains a real resume.

## 11. Commit plan (one PR; each commit `vehicle: …`, suite green at each)

1. `vehicle: a boot torn before its segment header no longer refuses the record`. This is F2 in
   `_verified_lines`, with test 14 (record-level half).
2. `vehicle: an executive resumes from a checkpoint and its record without first republishing tick
   zero`. This adds `resume_executive`, `attach(prepare=False)`, variables priming, recorded-skip
   windows, the root record from the recovered state and the `read_record(names=)` form, with tests
   1, 5–14.
3. `vehicle: results a crash left unwritten are republished once`. This is §2, with tests 2–4.
4. `vehicle: the executive checkpoints every N ticks, at a world's start and at a clean end`. This
   is §5, with tests 15–20.
5. `vehicle: a restart on a saved world resumes it instead of refusing`. This wires `main`:
   identity refusals, the `None` defaults, `--init`/`--plan`, routine and mismatch root-record
   classes, legacy advisories, the `resumed` event and the fresh-start refusal, with the fd-relative
   fixes and tests 21–31 plus the two rewritten tests.
6. `vehicle: resume documented`. This covers the `console.py` docstring ("No resume yet" →
   resume; 45–52, 115–125, 143–146), dated amendments to ADR 0001 choice D (86–92, 108–116) and ADR
   0002 (J rule 2's empty tail; S1–S17 as decided), and the README round section above
   `## The invariants…` with the referee-test count. Child 4's ADR (xi)/(xx) left the
   `tools/measure_clock.py` row for "a checkpointing cycle" as a candidate; I would add it only if a
   reviewer wants the cost pinned.

**Out of scope, by name:**
- graceful SIGTERM, the K2 fallback test, `--new-world`, retention and pruning: child 10 (#28);
- `m`, `k`, the required `N` flag and extending `check_console_flags`: child 5 (#23);
- budget semantics: child 7;
- phase from the tick: child 11;
- MET-stamped names: child 12 (#30).

---

## Addendum: coordinator decisions (2026-10-09), binding on implementation

**A1. Restart cost is bounded by `N` rows, in this child (R1 moves in scope).** One segment per boot
means the live boot's segment *is* the record, so skipping earlier segments does not bound anything.
The checkpoint's segment anchor records `(segment name, byte offset just after the last line of cycle
T — after its results_written notes — and the chain at that offset)`. Resume opens that segment
through the state-dir handle, seeks to the offset, and verifies forward from the recorded chain;
segments wholly before the anchor are not read. `read_record` gains a from-anchor form (the
end-to-end form stays for offline replay). The offset is a line boundary by construction (checkpoint
at end of cycle). **Integrity argument, to be written in the module docstring and attacked by
review:** the prefix before the offset is attested by the checkpoint, which lives in the same private
state directory and is itself verified (I); trusting the prefix adds no party the checkpoint did not
already trust. If child 1's schema refuses the new field, bump `vehicle.checkpoint.v1` → `v2` rather
than shimming (no deployed vehicle has ever written a checkpoint). A test pins the cost: a resume
after a long boot reads O(N) rows (count lines read, not wall time).

**A2. Commitment 1 is qualified, as the contract allows** (`docs/diode-contract.md:67–72`; ADR 0002
J (viii)): every command whose cycle's record row became durable has exactly one result; a batch
claimed and lost before its row is lost with no result. The test name states exactly that property;
the ADR amendment states it; the chassis package is corrected.

**A3. K2 fallback stays (ADR K), and its test is in this child**: corrupt current generation,
verified previous, record covering the gap → the same tick, state hash and lineage head as the
uninterrupted run. Both generations unusable → exit 3 naming the file and the check. The
`--new-world` message and flag remain child 10's.

**A4. `--closed-interlock` across a restart is the union of the saved and named sets** — a restart
that omits the flag cannot silently un-trip one; clearing one is a new world until WP05. Recorded as
an explicit choice in the ADR amendment (the issue's "named anew are journaled" is met: additions are
journaled). `--max-batch` named anew replaces and is journaled.

**A5. Re-publication dedupe (§2 option c) is accepted with a bound.** The scan of an agent-writable
`output/` runs while mission time is frozen for every window, so it must be bounded per window:
candidates are found by exact expected-name prefix, `lstat` through the handle, at most a fixed count
of candidates and bytes read per result; past the bound, write the result (a duplicate lands only on
that agent and is the lesser harm). State the bound and test a window whose `output/` is flooded with
candidate-named entries.

**A6. Lint.** `--phase`, `--max-batch`, `--closed-interlock` become remembered (in the checkpoint).
Extend `check_console_flags`' source of remembered keys to the checkpoint body as needed; do **not**
exempt any flag from the `None`-default rule to make lint pass.

**A7. Torn header (blocker 2) tests** cover a torn header as the file's only line, and a torn header
preceded by unchained startup-event lines.

**A8. Precondition stated in docs:** the kept refusals (EISDIR at `.executive.json`, a readable
foreign world) assume the per-slug mounts (chassis `adf38d6`, on `aurora-port`).

---

## Addendum B: after the design reviews (Codex astra high; Claude Opus), 2026-10-09 — binding

Both reviews: approve with changes. Where they converge the change is required; each item names its
sources (C = Codex finding, O = Opus finding).

**B1. Genesis is mandatory** (C2, O-B1). A fresh start with `--state-dir` writes the tick-0 checkpoint
before the first cycle; if it fails, exit 3 by name while nothing is bound. The log-and-continue
policy applies only to cadence and clean-end writes.

**B2. A fallback never rotates a corrupt generation over the good one** (C1, O-B2). When
`choose_generation` fell back, the resume renames the unverified current aside to a non-generation
name (e.g. `checkpoint.rejected.<boot_id>.json`) through `state_fd`, fsyncs the directory, and
records it in the `resumed` event — all before any checkpoint write. Test: fall back, then kill at
every step of the next checkpoint write, restart → resumes.

**B3. A resume checkpoint before serving** (C4, O-H2). After replay, flag reconciliation and
re-publication, and before the first resumed cycle claims anything, write a checkpoint at `L`. It makes
named run-input changes (`--closed-interlock` additions, `--max-batch`) durable, bounds the next
resume's replay to zero, and bounds re-publication. If it fails, exit 3 (nothing has been claimed
this boot). For the fallback path, nothing further is needed once this checkpoint exists.

**B4. Result obligations are checkpointed** (C3, O-M3). The checkpoint carries the private list of
results that are durable in the record but not confirmed written (a result whose write failed live,
or a re-publication that failed). Re-publication's domain is that list ∪ `unwritten_results` after
`T`; a result leaves the list only when written (or a recorded, bounded give-up — say which). The
fleet's outcome then does not depend on which generation was chosen. If child 1's
`_structure_problem` refuses the new section, bump the format to `vehicle.checkpoint.v2`.

**B5. The A1 anchor, specified** (C5, O-B3). The segment entry gains `offset`. The from-anchor read
seeds header (from the entry and the body's `world_id`), `chain = anchor.chain`, `last_tick = T`,
empty receipts/notes; validates at the seek point: regular file opened `O_NOFOLLOW` through
`state_fd`, integer offset ≤ size, the byte before it is `\n` (or offset 0 for an empty-after-header
case you define), the first row after it (if any) is `T+1`; finds successors by reading only each
journal file's first header line and restricts `_chain`/`concatenated` to the anchor and its
descendants, keeping the duplicate-id, fork, predecessor-chain and tick-seam checks across later
segments. `unwritten_results` gets the same from-anchor form. A checkpoint taken before the current
boot's header exists anchors at the predecessor's end. **Stated limitation** (docstring and ADR
amendment): the unread prefix is attested, not re-verified; a rewrite below the anchor that keeps its
boundary and tail is undetectable by resume by design; full end-to-end verification remains
available offline. Cost statement: O(L−T) rows across all passes (check, replay, unwritten) —
normally ≤ N, ≈ 0 after B3, larger only after cadence checkpoint failures. The cost test counts lines
read across all passes.

**B6. The output/ scan is bounded as a whole** (C6, O-M1). One `scandir` pass per window, a cap on
entries examined (not just candidates) and on bytes read, shared per window; files opened
`O_NOFOLLOW|O_NONBLOCK` through the `output/` handle and `fstat`-checked regular (no `lstat`-then-open).
Past the cap, write the result. The flooded-directory test includes non-candidate names. Exactly-once
is then: exactly one result per recorded command, except in that window's own pathological cases
(its agent deleting or forging files in its own `output/`, or flooding past the cap → at most a
duplicate in its own window). State that in the ADR amendment.

**B7. Directory repair is not initialisation** (C7). A missing `output/` or `telemetry/` is re-made
without `prepare()`'s tick-0 writes; `pending.json`, the mirror and the root record are never
regressed by repair.

**B8. Torn tails in a shared explicit `--journal`** (C8). Startup appends are newline-safe after an
unterminated tail; the verifier's handling of a torn line followed by startup events is defined
narrowly; a damaged segment the anchor requires is never discarded. Test repeated startup kills with
`--journal`.

**B9. Root record at L = 0** (O-M2): say which record is written; "routine" accepts `world_id: null`
with tick 0 only when T = L = 0.

**B10. A6 mapping** (C): `--closed-interlock` ↔ checkpoint `tripped_interlocks`; the lint source must
know the mapping.

**B11. Operator-facing choices, decided by the coordinator under the owner's standing delegation:**
- A world's slug set is fixed (O-M4); adding an agent is a new world. README and A8.
- Cadence checkpoint failures (O-M5, S4): the run continues (the record stays authoritative and
  resume stays correct, only slower); each failure is journaled and written to stderr with the
  consecutive-failure count, so `docker compose logs vehicle` shows it.
- S11: a fresh start over a record with no checkpoint exits 3; the message says exactly what to move
  aside.
- S14 (the budget's wall clock resets at a restart) is a stated residual, closed by child 7 (#25).
- S16 is required (O-Low). Also from O-Low: write `serves.json` before the `resumed` event; take
  `wall_down` from the newest journal file's mtime; note that the per-row `failures` count resets per
  boot; an unreadable console at resume must not lead the first claim to rewrite `console.json` to `{}`.

**B12. Tests to add** (O): arm token from before the kill passes the token check after resume
(refusal is INTERLOCK UNEVALUATED, not "not armed"); `000.json` keeps its inode and the first resumed
mirror's `ring.held`/`losses` equal the `telemetry/` listing; a deferral expires on the first resumed
cycle by simulated age, not the wall gap; a resume omitting `--closed-interlock` keeps the trips; a
resume with `--journal` plus `--state-dir`; a resume of a resumed world whose boot tore at its first
append, then a third boot; an unopenable `output/` at resume is a recorded obligation published once
later; run-input change survives a second resume; a kill between window A's and window B's claims;
B1, B2, B5 offset refusals. State explicitly that scheduled-event/phase-boundary restart points are
not applicable yet (`advance` applies no fault schedule).

**B13. Commit plan (O-H1), suite green at each:** (1) torn-header fix + A7/B8; (2) the anchor: offset,
from-anchor read, cost test (B5); (3) `resume_executive` + B7, B9; (4) re-publication + B4, B6;
(5) cadence (in-process via `checkpoint_every=`) + B2 + the A3 test; (6) `main`: genesis (B1), resume
checkpoint (B3), flags/identity, A6/B10 lint, and every existing test whose meaning changes, by name
(the reviewer listed tests around lines 24194, 24300, 24350, 24403, 24490, 24598, 24647, 24699,
24733, 24931 — none may hang under `--cycles 0`); (7) docs, ADR amendment, README round section.
