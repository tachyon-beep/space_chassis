# #39 tier 1: the brief wording, v2, for John's approval (draft)

Chassis, session `session_019mkPNN5J3Atit9tUA6zrNY`, 2026-10-11. This revises v1 (`brief-wording-tier1.md`,
`11a9b1e7…`) after Emmy's correctness note on atomicity, at-most-once, the next read, and what an empty
`commands` shows.

**Draft only.** No file in the tree has changed, nothing is adopted, the vehicle pin is unchanged, and no
test has run.

Basis:
- the vehicle's formal package `governance/vehicle/records/2026-10-11-39-tier1-adoption-package.md`
  (`483d47de…`);
- vehicle `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f` (PR #43), read with `git show` from the main
  checkout's vehicle clone. In `tools/console.py`:
  - `Window.claim`, with its docstring and the `quiet` test;
  - `Window.claimed_console`;
  - `write_json_atomic`;
  - `Executive._ingest`, and the cycle's `claim` failure handling;
  - the resume's `variables_known` handling.
- the adoption worktree's `containers/serve_vehicle.sh`, which passes `--state-dir`, so the executive keeps
  a journal.

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
  is taken as it stands. Anything else is claimed: a batch, a file that is
  missing or is not a console, or one whose `variables` is absent or not a map
  while the far side holds one.
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
  place is replaced unread. Its batch runs nothing, and leaves no result file
  and no record. The file you then see shows `commands` empty, exactly as if
  your batch had been taken. That holds whether you renamed your file in or
  wrote it in place. A file that holds nothing to claim is never rewritten,
  so a batch put in place over one is not lost this way: it stays until the
  far side next reads the file, and is claimed then if it is still there. The
  far side's own rewrite always leaves the file holding nothing to claim. Put
  a new batch in place only over a file in that state. Count a batch as taken
  when its results appear in `output/`, not because `commands` reads empty.
```

## C. `docs/brief-claims.md`: a new row (the table has no intake row today)

```
| The window replaces a console that holds something to claim with one whose `commands` is empty and `variables` kept, by a single rename, before acting on any of its commands, so each runs at most once (not exactly once); a console with nothing to claim (`commands` exactly `[]` with a `variables` map, or no `variables` while the window holds none) is not written and its map is taken; the read and the rename are separate steps, so a file put in place between them is replaced unread, with no result | `docs/diode-contract.md` §2.2 as adopted from vehicle `f75420c` (PR #43); vehicle `tools/console.py`: `Window.claim` (`quiet`; the docstring's residual), `Window.claimed_console`, `write_json_atomic` (temporary file and rename; `fsync`ed before acting when the executive keeps a journal), `Executive._ingest` (claim before validation; a claim that raises runs nothing); `containers/serve_vehicle.sh` (`--state-dir`, so a journal); vehicle `tests/test_vehicle_config.py::test_what_counts_as_nothing_to_claim_is_decided_by_shape_alone_and_the_console_always_shows_the_map`, `::test_a_console_with_nothing_to_claim_is_never_rewritten_so_a_batch_put_in_place_during_its_read_is_not_erased`, `::test_a_resume_after_quiet_cycles_left_the_agent_s_console_in_place_adopts_its_map`; fixture `contract/fake_diode.py` `AgentSide.consume` (the same rule, landed in the adoption increment; its test goes here) |
```

## D. One more line that the new text contradicts (flagged, not in the package)

`brief/PROTOCOL.md:68` says "Every command produces exactly one file in `output/`". B now says a lost batch
leaves no result file, and A says the rest of a stopped batch is lost. The proposed minimal wording:

```
Every command the far side answers produces exactly one file in `output/`:
```

This change is also John's to approve. Whether the far side answers each remaining command after a restart
is not settled here, and nothing above relies on it.

## E. Each claim, and its source

- **The replacement is atomic, but the claim is not.**
  - `write_json_atomic` writes a temporary file and then calls `os.replace`, so a reader of the path sees
    either the old file or the new one.
  - `claim` calls `read_ingress` and then `write_json_atomic`. These are two steps, and nothing checks
    that the file replaced is the file that was read. The docstring says so: "no rename can check that the
    file it replaces is the file it read."
  - v1 kept the contract's "destructive and atomic". v2 says which part is atomic.
- **What counts as nothing to claim.** It comes from `quiet = isinstance(commands, list) and not commands and
  (isinstance(variables, dict) or ("variables" not in payload and not self.variables_known))`. A `variables`
  that is present but not a dict is claimed, which is why the text says "map".
- **What is claimed.** A missing or unreadable file, a link, a non-regular, oversized or invalid file, and a
  non-object all go through the `payload is None` branch, which rewrites and returns the refusal. A file
  with no `commands` list, or with a non-map or missing `variables` while the map is known, is rewritten by
  the main path.
- **A quiet file's map is taken.** The map is adopted before `if quiet: return []`.
- **The far side's own rewrite is always quiet.** `claimed_console` gives `{"commands": [], "variables":
  <the known map>}` when the map is known, and `{"commands": []}` when it is not; both match `quiet`.
  `variables_known` becomes true only by adopting a dict from the console, and a resume resets it to
  false. The vehicle's test `..._the_console_always_shows_the_map` covers this.
- **At most once.**
  - `_ingest` calls `claim()` before any validation or effect.
  - If `claim` raises (a failed rewrite or `fsync`), the cycle records a `claim` failure and runs none of
    that window's batch.
  - A batch's claim is `fsync`ed, file and directory, before the record says it was answered, when the
    executive keeps a journal (`durable=commands not in (None, []) and self.executive.journal is not None`).
    The adoption's `serve_vehicle.sh` passes `--state-dir`, and with that and no `--journal` the executive
    keeps a per-boot journal segment.
  - **Scope.** Against a crash of the vehicle process, at most once follows from the rename alone. Against
    a host crash it rests on that `fsync`, so it holds for the adoption's configuration (`--state-dir`).
    It does **not** hold for `containers/serve_vehicle.sh` at today's `aurora-port` HEAD, which passes
    neither flag. Tier 1 is to land on the adoption, so the brief's claim is scoped to it.
- **"Even if the far side stops part-way."** "Clear before you act" (contract §2.2, unchanged) states it,
  and so does the claim-before-act order in `_ingest`. A claim whose `fsync` fails after its rename
  succeeded raises, and runs nothing. That is a loss, which is consistent with at most once.
- **The lost batch.** The source is the docstring's residual: "every rewrite that remains … still erases a
  file the agent put in place between its read and its rewrite". The package's §2.2 bullet 2 says the
  same. The claim is that a loss can happen, not a rate. No test shows a loss.
- **An empty `commands` doesn't prove a take.** A rewrite that erased a batch writes the same
  `{"commands": [], …}` as one that took it, so the results in `output/` are the only per-batch evidence.
- **The next read.** The vehicle test `..._a_batch_put_in_place_during_its_read_is_not_erased` covers a
  quiet console that isn't rewritten, so the batch stays. "Claimed then if it is still there" makes no
  promise about when the next read comes, or that it comes at all, for example while the far side is down.

## F. Limitations and dependencies, for John

1. **The rule assumes a single writer.** "Put a new batch in place only over a file that holds nothing to
   claim" removes the far-side race only when the agent is the only other writer, and checks the state
   before it writes. Two of the agent's own processes can still overwrite each other. That is theirs to
   order, and the brief does not mention it.
2. **The vehicle-led contract wording still says "destructive and atomic" and "claimed at the window's next
   read".**
   - The brief is now more precise than its source.
   - Suggested to the vehicle line, not required for tier 1:
     - bullet 1: "the rewrite is atomic; the read-and-claim is not";
     - bullet 2: make "next read" conditional on the file not having been replaced during a claim.
   - The wording is theirs.
3. **Same increment.** The pin to `f75420c`, contract §2.2, and the fixture's quiet rule with its test all
   land with the brief, or before it. At `f443996` "left untouched" is false. Without the fixture rule, the
   brief would be false for the fixture window (`PROTOCOL.md:32`, "what any window accepts").
4. **Evidence base.** The base is code reading at `f75420c`, plus the vehicle's unit tests and gates. Two
   things are not yet done:
   - the chassis's own q1–q3 re-run on `f75420c`;
   - the ≥30 gate runs, which need a slot grant.

   Nothing here claims that losses have stopped under load.
5. **Option B is not mentioned.** It is not implemented on `main`, tested, adopted or qualified.
6. **Test drivers.** If adoption comes before R2c's build and live gate, `f75420c` changes
   `tests/test_vehicle_config.py` (+141 lines). The accepted drivers bind that file to `3b917de3…`, so they
   would need rebinding and review.
