# #39 tier 1: the brief wording, v5, the final draft for John's approval

Chassis, session `session_019mkPNN5J3Atit9tUA6zrNY`, 2026-10-11. **Draft only.** No file in the tree has
changed, nothing is adopted, the vehicle pin is unchanged, and no test has run. John's approval of the
wording is reserved.

**Lineage.**
- v2 `9e8b5192…` was reviewed (`review-v2-astra.md` `7236e195…`: APPROVE WITH CHANGES).
- v3 `b8249c9f…` applied that review.
- v4 `78d3453e…` corrected v3 on three points, at Emmy's request:
  - result counting;
  - putting the host-crash and journal limits beside the at-most-once claim;
  - a reconciliation of every promised behaviour against the code.
- v4 had one bounded delta review (`review-v4-astra.md` `9c228ea2…`): APPROVE WITH CHANGES, no Critical.
- **v5 applies that review's five findings and nothing else. v5 has not been reviewed again.**

**Basis.**
- The vehicle's formal package `governance/vehicle/records/2026-10-11-39-tier1-adoption-package.md`
  (`483d47de…`).
- Vehicle `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f` (PR #43), read with `git show`. Line numbers below are
  in `tools/console.py` at that commit.
- The deployment the text lands on, the adoption worktree's `containers/serve_vehicle.sh`, which passes
  `--state-dir`.

## A. `brief/PROTOCOL.md` lines 51–54, replaced by two bullets

```
- **Intake is destructive, and the claim is not atomic.** Each pass, the far
  side reads the file. If it holds something to claim, the far side then
  replaces it with a copy whose `commands` is empty and whose `variables` are
  kept. The replacement is a single rename, so you never read a half-rewritten
  file. But the read and the rename are two separate steps, and nothing ties
  the file the rename replaces to the file that was read (see below). A file
  holds nothing to claim when `commands` is exactly `[]` and it carries a
  `variables` map, or carries no `variables` while the far side holds none.
  Such a file is left untouched: nothing is written, and its `variables` map
  is taken as it stands. Once the far side's checks let it take the file in,
  anything else is claimed: a batch; a missing, unreadable or half-written
  file, or one that is not a JSON object; one with no `commands` list; one
  whose `variables` is present but not a map; or one with no `variables`
  while the far side holds a map.
- **A command runs at most once, not exactly once.** The far side replaces
  the file before it acts on any command in it, and acts on nothing in the
  file until that replacement has succeeded. If the far side's process stops
  part-way through a batch, the file it finds when it starts again is the
  replacement, so that batch is not run again. If the whole machine stops,
  this rests on the replacement having reached the disk: this far side keeps
  a record, flushes a claimed batch's replacement to disk before acting on
  it, and relies on the disk keeping what it was told to flush. A far side
  that kept no record would not flush it, and a crash of the machine could
  then undo the claim. A batch can also run less than once. It can be lost
  before it is claimed (below). And when the far side stops part-way, what it
  had not yet recorded of a claimed batch is lost and never answered. Writing
  the same command again submits it again.
```

## B. Lines 59–60, replaced (the next-pass promise withdrawn)

```
- **A batch you put in place can be lost while an earlier file is being
  claimed.** Between the far side's read and its rename, whatever you put in
  place is replaced unread. Its batch runs nothing, and nothing answers or
  records it. The file you then see shows `commands` empty, exactly as if
  your batch had been taken. That holds whether you renamed your file in or
  wrote it in place. A pass that reads a file holding nothing to claim does
  not rewrite it, so a batch renamed in over such a file is not lost this
  way: it stays until the far side next reads the file, and is claimed then
  if it is still there. Nothing says when that next read comes. Writing in
  place has no such protection: the far side can read the file half-written,
  refuse it and replace it, and the rest of your write then lands on a file
  that is no longer there. So keep to one writer, and publish each file
  whole, through a temporary file and a rename. After you put in place
  anything that holds something to claim, replace the file again, with
  anything at all, only once the far side's cleared copy has appeared. Even
  then, a cleared console shows only that some file was claimed, not that
  yours was taken or answered. Look for your batch's answers in `output/`.
```

## C. `brief/PROTOCOL.md:68` and lines 75–78, replaced (this removes "exactly one file")

Current: "Every command produces exactly one file in `output/`:". Proposed:

```
The far side answers in `output/`. Each answer is a file ending in a
`receipt:` line, whose `seq` numbers that answer for your window. Count
answers by `seq`, not by files. A deferred command is answered twice, when
it is accepted and again when it settles. An answer that could not be
published remains owed and may be written later. Retrying publication can
create another file with the same `seq`. If more than 256 answers are owed
to your window, the oldest is given up and may never be written. A batch
lost as described above has no answers at all:
```

The filename block after line 68 stays as it is. **Lines 75–78 are replaced too.** They say "submission
time", but the stamp is taken when the file is published (`write_result`, 4446–4449). And their "all produce
one" promises a file for every command, which C withdraws. Proposed:

```
The filename carries the publication time, your window name, and the
command. A refusal is answered the same way as a success: an unavailable
verb, a rate-limited call and a successful command are all answers.
**Failure and success are the same shape**, deliberately, so that the only
way to know what happened is to read it.
```

Line 80 ("Nothing waits for you. Submit, and read later.") stays.

## D. `docs/brief-claims.md`: a new row (the table has no intake row today)

```
| The window replaces a console that holds something to claim with one whose `commands` is empty and `variables` kept, by a single rename, before acting on any of its commands; a console with nothing to claim (`commands` exactly `[]` with a `variables` map, or no `variables` while the window holds none) is not written and its map is taken. A command runs at most once, not exactly once: across a vehicle process crash by the rename alone; across a host crash only because the vehicle, run with `--state-dir`, keeps a journal and so `fsync`s a claimed batch's replacement before acting. The read and rename are separate steps: a batch published between them can be erased unread and unanswered. An in-place write can instead be read partially and refused; its remaining bytes can land on the replaced inode, losing the intended batch. A cleared console does not show which file was claimed. Answers are counted by their receipt `seq`, not by files: a deferral is answered at acceptance and at settlement, an owed answer can be written twice with the same `seq`, and past 256 owed answers the oldest is given up | `docs/diode-contract.md` §2.2 as adopted from vehicle `f75420c` (PR #43); vehicle `tools/console.py`: `Window.claim` (`quiet`; the docstring's residual), `Window.claimed_console`, `read_ingress`, `write_json_atomic`, `Executive._ingest` (claim before validation; a claim that raises runs nothing), the cycle's durability order (the comment above `RecordRefused`), `Window.write_result` and `Window.receipt`, `republication` and `receipt_line`, `Executive.publish_obligations` and `Executive.owe` (`OBLIGATIONS_PER_WINDOW`), the deferral verdict in `Executive.validate`'s deferrable branch; adoption `containers/serve_vehicle.sh` (`--state-dir`); vehicle `tests/test_vehicle_config.py::test_what_counts_as_nothing_to_claim_is_decided_by_shape_alone_and_the_console_always_shows_the_map`, `::test_a_console_with_nothing_to_claim_is_never_rewritten_so_a_batch_put_in_place_during_its_read_is_not_erased`, `::test_a_resume_after_quiet_cycles_left_the_agent_s_console_in_place_adopts_its_map`; fixture `contract/fake_diode.py::AgentSide.consume` (future adoption requirement: implement the identical quiet rule and add its test before citing it as evidence) |
```

## E. Every promised behaviour, reconciled against `f75420c` and the adoption deployment

| text says | the code at `f75420c` | holds in the adoption? |
|---|---|---|
| the replacement is a single rename and is never read half-written | `write_json_atomic`: `O_EXCL` temporary file, then `os.replace` (431–466) | yes |
| the claim is not atomic | `claim`: `read_ingress`, then a separate `write_json_atomic` (4340–4370); docstring "no rename can check…" | yes |
| nothing to claim | `quiet` (4348–4352), decided from types before the map is adopted | yes |
| a quiet file is untouched and its map taken | the map is adopted at 4355–4359, before `if quiet: return []` | yes |
| what is claimed | `payload is None`: missing, unreadable, invalid or non-object, rewritten and refused (4341–4343); no `commands` list, present non-map `variables`, or missing `variables` while the map is known: not quiet, so rewritten (4363–4370). A link or non-regular console already in place when the window is checked skips intake, with no rewrite (4220–4228); A does not list it | yes |
| acts on nothing until the replacement succeeds | `_ingest` calls `claim()` first (3536). A raise propagates to the cycle's `claim` failure (3096–3105). No verdict from that newly claimed batch follows; an earlier deferral's settlement can still be published | yes |
| process crash: not run again | the rename is in place before any act; a restart reads the claimed file | yes |
| host crash: rests on the flush | `durable=commands not in (None, []) and journal is not None` (4369); with `sync_file` and `sync_dir`, the file and directory are `fsync`ed (454–466) | yes: `--state-dir` and no `--journal` give a per-boot journal (2846–2856; adoption `serve_vehicle.sh:90`). `aurora-port` HEAD's script passes neither, and there it would **not** hold |
| relies on the disk keeping the flush | not something the code can establish | an assumption about the storage, stated as one |
| what was not yet recorded is lost and never answered | durability order: claim `fsync`, then the tick row `fsync`, **before** any result (comment at 1132–1138). A stop before the row loses the cycle's decisions, and no result for them has been written | yes |
| the lost batch: unread, unanswered, unrecorded; renamed in or written in place | the docstring's residual (4335–4338). A replaced inode is gone, whether it was renamed in or written in place | yes |
| a quiet file is not rewritten, so a batch renamed in over it stays | `if quiet: return []` writes nothing; the vehicle test "…not_erased" | yes; no time for the next read is promised |
| the far side's cleared copy has nothing to claim | `claimed_console` (4380–4390) gives the known map, or no key while the map is unknown; both are quiet. A fresh window starts known and empty (4158–4163); a resume clears the map and re-adopts it from a readable console (5037–5046) | yes |
| a cleared console does not show which file was claimed | an erasing rewrite and a taking one write the same `claimed_console()` | yes |
| answers carry a receipt `seq` | `publish` writes `body + self.receipt(verdict)` (4492); `republication` adds `receipt_line` (2483–2488, 2491–2516) | yes |
| a deferral is answered twice | acceptance verdict `deferred` (4019–4040); settlement in `_settle` (3584–3624) | yes |
| an owed answer is written later, possibly twice with the same `seq` | `_owe`/`owe` (3221–3245); `publish_obligations` writes what its bounded `results_on_disk` scan did not find (3247–3280) | yes |
| an owed answer can be given up | past `OBLIGATIONS_PER_WINDOW` (256) owed answers, not after a time, the oldest is given up and recorded as a failure (3233–3245) | yes |

## F. Coordination requirements: the vehicle's wording (tracked; not edited here)

The vehicle line leads `docs/diode-contract.md`. This draft does not edit it and does not widen adoption
beyond the formal package. Three inconsistencies between the package's contract text and what the brief now
says (and the code does) are raised with the vehicle line through Governance.

| # | contract text (package §2.2 / current §2.3) | the inconsistency | requested of the vehicle line |
|---|---|---|---|
| V-1 | §2.2 bullet 1: "**Intake is destructive and atomic.**" | Only the rewrite (rename) is atomic. The read-and-claim is not, and the same package's bullet 2 states the race. | Qualify it, for example: "the rewrite is atomic; the read-and-claim is not". |
| V-2 | §2.2 bullet 2: "A batch is claimed at the window's next read." | This is unconditional. It is true only for a file not replaced during a claiming rewrite. | Make it conditional, the way the residual sentence already does. |
| V-3 | §2.3: "Every command produces exactly one file" | A deferral produces two answers. An owed answer can be written twice, or given up. A lost batch has none. This predates tier 1. | Restate it as answers counted by receipt, with those cases named. |

Optional, not a requirement: §2.1's "reliable transport".

Until V-1 to V-3 are settled, the brief is deliberately more precise than the contract sentence it cites,
and the D row cites the code alongside §2.2. Adopting tier 1 as packaged does not depend on them.

## G. Limitations, for John

1. **The disk flush is assumed to hold.** The host-crash half of at most once assumes the disk keeps what
   was flushed. The window lives on a loop-mounted volume image, and nothing here verifies that a flush goes
   through it to stable storage.
2. **The protection rests on the agent's own discipline.** Avoiding this loss requires one writer,
   publication by rename, and waiting for the far side's cleared copy before replacing a claimable
   submission. The world does not enforce that discipline.
3. **There is no chassis evidence on `f75420c` yet.** The base is code reading and the vehicle's own tests
   and gates. The q1–q3 re-run and the ≥30 gate runs need a slot grant. Nothing claims the losses have
   stopped under load.
4. **This text lands with the rest of the increment or after it.** That means the pin to `f75420c`,
   contract §2.2, and the fixture's quiet rule with its test. At `f443996` the quiet promise is false, and
   without the fixture rule it is false for the fixture window. If adoption comes before R2c's build and
   live gate, the accepted drivers need rebinding to the changed `tests/test_vehicle_config.py`.
5. **The fixture is outside "this far side".** `contract/fake_diode.py` keeps no record and flushes
   nothing. The brief's host-crash sentence describes the vehicle as deployed, not the fixture.
6. **Option B is not mentioned.** It is not implemented, tested, adopted or qualified.
