# #39 tier 1: the brief wording, v3, for John's final approval (draft)

Chassis, session `session_019mkPNN5J3Atit9tUA6zrNY`, 2026-10-11. **Draft only.** No file in the tree has
changed, nothing is adopted, the vehicle pin is unchanged, and no test has run.

v3 is v2 (`brief-wording-tier1-v2.md`, `9e8b5192…`) with the findings of its one independent review applied
(`review-v2-astra.md`, `7236e195…`: APPROVE WITH CHANGES, no Critical). The sourcing, scope and limitations
in v2 §E–F still apply, except where §5 below corrects them. **v3 itself has not been re-reviewed.**

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
  is taken as it stands. Anything else is claimed: a batch; a missing,
  unreadable or half-written file, or one that is not a JSON object; one with
  no `commands` list; one whose `variables` is not a map; or one with no
  `variables` while the far side holds a map.
- **A command runs at most once.** The far side replaces the file before it
  acts on any command in it, and acts on nothing it failed to replace. So the
  commands of one file are not run a second time, even if the far side stops
  part-way through them. This is at most once, not exactly once: a batch can
  be lost (below), and the rest of a batch is lost when the far side stops in
  the middle of it. Writing the same command again submits it again.
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
  if it is still there. Writing in place has no such protection. The far
  side can read the file half-written, refuse it and replace it, and the
  rest of your write then lands on a file that is no longer there. So keep
  to one writer, and publish each file whole, through a temporary file and a
  rename. After you put in place anything that holds something to claim,
  replace the file again, with anything at all, only once the far side's
  cleared copy has appeared. Count a batch as taken when its answers appear
  in `output/`, not because `commands` reads empty.
```

## C. `docs/brief-claims.md`: a new row (the table has no intake row today)

```
| The window replaces a console that holds something to claim with one whose `commands` is empty and `variables` kept, by a single rename, before acting on any of its commands, so each runs at most once (not exactly once); a console with nothing to claim (`commands` exactly `[]` with a `variables` map, or no `variables` while the window holds none) is not written and its map is taken; the read and the rename are separate steps, so a file put in place between them, or one written in place and read half-written, is replaced unread with no answer | `docs/diode-contract.md` §2.2 as adopted from vehicle `f75420c` (PR #43); vehicle `tools/console.py`: `Window.claim` (`quiet`; the docstring's residual), `Window.claimed_console`, `read_ingress`, `write_json_atomic` (temporary file and rename; `fsync`ed before acting when the executive keeps a journal), `Executive._ingest` (claim before validation; a claim that raises runs nothing); `containers/serve_vehicle.sh` (`--state-dir`, so a journal); vehicle `tests/test_vehicle_config.py::test_what_counts_as_nothing_to_claim_is_decided_by_shape_alone_and_the_console_always_shows_the_map`, `::test_a_console_with_nothing_to_claim_is_never_rewritten_so_a_batch_put_in_place_during_its_read_is_not_erased`, `::test_a_resume_after_quiet_cycles_left_the_agent_s_console_in_place_adopts_its_map`; fixture `contract/fake_diode.py::AgentSide.consume` (future adoption requirement: implement the identical quiet rule and add its test before citing it as evidence) |
```

## D. `brief/PROTOCOL.md:68`, qualified (outside the vehicle's package)

Current: "Every command produces exactly one file in `output/`:". Proposed:

```
The far side answers in `output/`, one file per answer. A deferred command
is answered when it is accepted and again when it settles; a batch lost as
described above is not answered at all:
```

Execution at most once is a separate claim from how many result files there are, and v2's "exactly one file"
for each answered command was wrong.
- A deferred command publishes an acceptance verdict, and later a settlement verdict (`console.py` at
  `f75420c`, 4019–4040, 3584–3624).
- Result recovery can write a result again when its bounded scan does not find the one already on disk
  (3263–3280).

D promises no particular count.

## What changed from v2, and why (each change checked against the code)

1. **Writing in place.** v2 said a batch put in place over a quiet file is never lost.
   - That holds only for a file renamed in.
   - A file written in place can be read half-written, refused and replaced, and the rest of the write
     goes to an unlinked inode (`read_ingress`, then the `payload is None` rewrite).
   - The vehicle's "not erased" test writes after the read has finished, so it does not cover a write that
     is still in progress.
   - B now limits the protection to a file renamed in, and says to publish whole.
2. **A claim already in flight.** v2's rule was to put a new batch in only over a quiet file. But a quiet
   file the agent writes itself does not cancel a claim already under way on an earlier file that had
   something to claim. B now says: after putting in anything with something to claim, replace the file
   again only once the far side's cleared copy has appeared.
3. **Result files.** v2's D promised exactly one file per answer. The text now promises no count (see D).
4. **What gets rewritten.** A gains "one whose `variables` is not a map", which is rewritten even when the
   far side holds no map. A link or non-regular console is not on A's list:
   - one already in place when the window is checked makes the window skip intake, with no rewrite
     (`Window.open_handles`, 4220–4228; the cycle's `check` failure);
   - one that appears after the check reaches the refusal-and-rewrite path, which "unreadable" covers.
5. **Source corrections to v2 §E.**
   - `variables_known` starts as true, with an empty map, for a fresh window (4158–4163).
   - A resume sets it to false, and sets it back to true from a readable console map. Each later claim
     that carries a map adopts it.
   - The far side's own rewrite still always reads as having nothing to claim.
   - The fixture entry in C now says it is future work, not landed.

## Review verdicts, as the reviewer gave them for v2

- **Q1, atomicity: CORRECT.** The text keeps the atomic file replacement apart from the non-atomic
  read-then-claim, and nothing in it still promises an atomic claim.
- **Q2, at most once: CORRECT for execution in the adoption's deployment.** That deployment uses
  `--state-dir`, which gives a journal, which gives the `fsync`. The text separates a process crash from a
  host crash, and the reviewer found no path that runs a claimed command twice. D's result promise needed
  change 3.
- **Q3, observing a quiet file: OVERSTATES.** Every successful claim, including after a resume, leaves a
  quiet file, and an empty `commands` proves nothing about delivery. "If it is still there" makes no
  unconditional promise. Changes 1 and 2 address the overstatement.
- **Q4, the remaining loss: OVERSTATES.** The census of what gets rewritten needed change 4.
- **Option B:** clearly future; nothing implies it is implemented or qualified.
- **Names, hashes and history:** the named tests exist at `f75420c`, and the driver hash and +141-line
  note check out. The three-of-three historical losses support no claim about load.

## Unresolved limitations, for John

1. **v3 has not been reviewed.** It applies the review's changes in the wording the review proposed or
   close to it, and each change was checked against the code. Another bounded review would need its own go.
2. **The contract still says more than the brief.** The vehicle-led §2.2 still says "destructive and atomic"
   and "claimed at the window's next read". §2.3 says "Every command produces exactly one file", which a
   deferred command already contradicts; that predates tier 1. All of it is the vehicle line's wording to
   qualify.
3. **The protection rests on discipline.** One writer, publishing by rename, is the agent's own discipline;
   the world does not enforce it.
4. **There is no chassis evidence on `f75420c` yet.** The base is code reading and the vehicle's tests and
   gates. The q1–q3 re-run and the ≥30 gate runs need a slot grant. Nothing claims that losses have stopped
   under load.
5. **Same increment.** The pin, contract §2.2, and the fixture's quiet rule with its test all land with this
   text or before it. The accepted drivers would need rebinding to the new `tests/test_vehicle_config.py`
   if adoption comes before R2c's build and live gate.
6. **Option B is not mentioned, and is not implemented, tested, adopted or qualified.**
