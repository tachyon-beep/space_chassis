# #39 option B — take by rename, republish only if absent (design note, for review before code)

Vehicle line, Space Vehicle [610587], 2026-10-11. Status: **design, no code**. It builds on tier 1
(quiet cycles write nothing; branch `codex/39-quiet-skip`, local commit `7ac9791`, gating).

John's decisions, 2026-10-11 (`governance/vehicle/decisions.md`):
- **B is the next package.** It replaces tiers 2 and 3.
- **The console may be briefly absent** while a claim takes it, and agents must detect and handle
  tearing.
- **The threat model is not adversarial.** It covers erratic agents (any rate, torn writes, odd
  shapes); cheats are data, fixed as found.

Source: the solution architect's panel opinion (`reviews/panel-architect.md` §2) and the concurrency
reviewer's variant (`reviews/panel-concurrency.md` (b)). References are to `f443996` plus tier 1.

## Why B avoids what sank v1–v3

v1–v3 put a vehicle-authored file **over** the agent's slot by exchange. After a crash, the vehicle
then had to tell its own possibly-stale file from the agent's, using evidence the agent could not
forge. B never writes over anything:
- the take is a `rename` that moves exactly the file present at that instant;
- the republish is a `link` that fails rather than replace a file.

So the console is only ever the agent's newest file, or the vehicle's copy of the map it has just
adopted. **Neither is stale, so recovery needs no ownership test.** B uses only POSIX
`rename`/`link`/`unlink`; the vehicle already uses `os.link` for noclobber results
(`write_text_atomic(noclobber=True)`, `console.py:459–461`). There is no `renameat2` or ctypes, and
no platform decision is needed.

## The claim, non-quiet path (quiet is unchanged from tier 1)

Window directory handle `root`; `n` is a per-window counter; `boot` is `Window.boot_id`.

| step | action |
|---|---|
| B0 | Read `console.json` as today (`read_ingress`, bounded, `O_NOFOLLOW \| O_NONBLOCK`). If it is quiet (tier 1), return `[]`. If `lstat` shows a **directory**, record the window's failure as today and take nothing. |
| B1 | **Take:** `os.rename("console.json", ".console.json.take.<boot>.<n>", src_dir_fd=root, dst_dir_fd=root)`. This atomically moves whatever is at the name at that instant; it moves a link as a link and follows nothing. `ENOENT` means the agent removed the file since B0: nothing is claimed, and this cycle does nothing more. |
| B2 | **Read the taken file `X`** through its private name, bounded, `O_NOFOLLOW \| O_NONBLOCK`. **`X` is the claim**, whether or not it is the file B0 read. If the agent replaced `R` before B1, `R` was superseded by the agent, as on any filesystem. `X`'s `commands` is the batch; a file that is not a console gets the one refusal result, as today; `X.variables`, if it is an object, is adopted (replace, not merge), and otherwise the map is kept. |
| B3 | **Durable** (when the record exists): `fsync` the window directory before the batch is returned, so the record's later `fsync` can never get ahead of the take (the #21 rule). |
| B4 | **Republish:** write `claimed_console()` to a private temporary (`fsync` when durable), then `os.link(tmp, "console.json")`, then unlink `tmp`. **`EEXIST` means the agent has already written a new console: leave it**, and the next cycle claims it. |
| B5 | Unlink the take name. Return the batch, or the refusal sentence. |

**Nothing after B1 may withhold the claimed batch.**
- A failure in B4 or B5 is recorded as the window's failure, **alongside** the batch's verdicts.
  `_ingest` is extended to accept a batch plus a failure.
- If B4 fails, the console stays absent until the next claim or repair republishes it. That is the
  same transient absence the contract now allows, and resume handles it (below).
- A B2 read that fails at the OS level is a refusal result naming the error ("the console taken
  this cycle could not be read: …"), never an exception that drops the batch.

**Absent at B0** (today: one refusal, then the claimed console written). Try B4's `link` first. On
success, write the one refusal, as today. On `EEXIST`, the agent created a console in between:
write no refusal, and the next cycle claims it.

**`prepare` and `repair`** today check with `lstat` and then `os.replace` the claimed console in
(`console.py:4280–4302`). Both become B4's `link` (noclobber), so neither can overwrite a console an
agent creates in between.

## What a reader sees

- **During a claim**, between B1 and B4, `console.json` is absent: microseconds normally, longer
  under scheduling. A reader must treat absence, or a partial file, as transient.
- **After a claim**, the console is either the vehicle's copy, with `commands: []` and the map just
  adopted from `X`, or the agent's own newer file. **There is no stale vehicle file and no lag.**
- **The unchanged probe:**
  - `read_console` returns `{}` for an absent file, so `check_batch_claimed` keeps polling until the
    republish, which carries the marker;
  - `submit`'s `os.replace` works whether or not the console exists;
  - a submission that lands during the gap makes B4 fail with `EEXIST`, and is claimed next cycle;
  - the start-up `exists()` check (`diode_probe.py:337`) can only fail if a probe starts during a
    claim. In an isolated, initially quiet run (the chassis test), the first claim is the probe's
    own first submission, so it cannot.

## Crash recovery (resume) — no ownership test

What is on disk after a SIGKILL:

| killed after | `console.json` | take name |
|---|---|---|
| B0 | the agent's (unchanged) | none |
| B1, B2 or B3 | absent, or the agent's newer file | `X` |
| B4 | the vehicle's copy, or the agent's newer file | `X` |
| B5 | either | none |

**Resume rule**, applied per window before the first cycle and replacing the console read at
`console.py:5014–5023`:
1. **Find leftovers**: every `.console.json.take.*`, read through the window handle.
2. **The map:**
   - if `console.json` exists and carries a `variables` object, adopt it. It is either the agent's
     newer file or the vehicle's copy of the map adopted from `X`; both are correct;
   - otherwise, adopt the newest leftover's `variables` object, if it has one (newest by `mtime_ns`;
     at most one claim's leftover can exist, see 4);
   - otherwise, the map is unknown, as today (ADR 0002 (xxxv)).
3. **If the console is absent**, republish it with B4's `link` (`EEXIST`: leave it).
4. **Delete every leftover, then `fsync` the directory**, before the first cycle claims anything.
   - **Its commands are not run.** It was claimed at B1, and losing it in a crash is the existing
     rule ("the batch was already claimed").
   - Because the deletion is durable before any new claim, a later boot can only ever see the
     leftovers of one claim.
   - A leftover is never offered back, so nothing is replayed.

**Codex's round-1 counterexample, walked** (read A, take B, SIGKILL):
- **Before the republish:** the console is absent, and the leftover is B. The map is B's, and a
  console carrying B's map is republished. ✓
- **After the republish:** the console carries B's map. ✓
- **The agent wrote C after the take:** C's map, or B's if C has none. ✓

The map is never reverted, and no evidence needs authenticating. (Under the threat model, an agent
writing a file named `.console.json.take.*` is a cheat to be noticed, not designed against. Its
effect is limited to that agent's own variables.)

## Residuals (disclosed)

- **In-place writers.** An agent writing *into* the console file (not replacing it) while B1 runs
  has its later bytes land in the taken file. The read at B2 may then see a partial file and refuse
  it: the existing half-written rule.
- **A crash after B1** loses that batch's commands: the existing crash rule. Its variables are
  recovered.
- **Power loss** (as distinct from SIGKILL) is covered only by the existing `fsync` order; it is not
  tested.

## Contract (vehicle leads; chassis adopts) — replaces tier 1's interim wording

> - **Intake is destructive and atomic.** Each cycle the vehicle reads the file. If it holds
>   something to claim (commands, a file that is not a console, or a console with no `variables`
>   while the vehicle holds a map), the vehicle **takes** it: it renames the file aside, atomically
>   taking whatever is there at that instant, and then puts back a console with `commands` emptied
>   and `variables` preserved, **unless you have already written a new one, which it leaves for the
>   next claim**. A command therefore takes effect **at most once**, even if the vehicle dies
>   mid-cycle: the batch was already claimed. A console whose `commands` is `[]` and which already
>   shows the `variables` is left as it is.
> - **The console can be briefly absent** while a claim takes it. Treat an absent or unreadable
>   console as transient, and read again.
> - A batch is claimed at the window's next read. A batch you replace before it is claimed is
>   superseded, as on any filesystem.

The brief (`brief/PROTOCOL.md:51–54`) and `docs/brief-claims.md` follow, in the chassis's voice.
`fake_diode.py` may keep tier 1's quiet-skip: B is the vehicle's mechanism, and the fixture "models
nothing".

## Tests

**Regression tests** (fail on `7ac9791`):
- **A batch put in place between B0 and the take, on a non-quiet claim:** today it is erased. Under B
  it is the claim; the batch read at B0 is superseded.
- **A batch written between B1 and B4:** it is never overwritten (`EEXIST`) and is claimed next
  cycle.
- **Absent console:** the vehicle's republish never overwrites an agent's console created during
  the claim. This covers `prepare` and `repair` too.

**Preservation tests:**
- the claim's durability order;
- refusing a file that is not a console;
- the directory at `console.json`;
- one result per command;
- the exactly-once SIGKILL stress.

**Crash tests:** a SIGKILL after each of B1 to B5, then resume. The map rule above must hold, no
leftover may survive the resume, no replay, and the console exists after the resume.

**The unchanged probe in process:** a submission landing in the gap.

**Stress, as evidence:** `probe_race.py`'s jittered writer must lose 0 on non-quiet claims as well.
Agent-superseded batches are counted separately.

## Questions for the reviewer

1. Can any ordering of agent replaces, in-place writes, removals or creates, and of SIGKILLs
   (including during resume and across boots), against B0–B5 and the resume rule:
   - lose a batch outside the existing crash rule and the disclosed residuals,
   - replay one,
   - answer one twice,
   - claim one without a result, or
   - revert or fabricate the map?
2. Is "nothing after B1 withholds the batch" implementable as specified, with `_ingest` accepting a
   batch plus a failure?
3. Is the resume rule's "at most one claim's leftovers" invariant sound, given the durable deletion
   before the first claim?
4. Is anything in §"What a reader sees" false against the probe's code?
5. Is the contract wording true?
