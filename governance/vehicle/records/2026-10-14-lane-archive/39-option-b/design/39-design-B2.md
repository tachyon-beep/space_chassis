# #39 option B, revision 2 — take by rename, republish only if absent

Vehicle line, Space Vehicle [610587], 2026-10-11. **Design, no code.** This revises `39-design-B.md`
(sha256 `f32b5d14…`, unchanged), which Codex returned with request changes
(`reviews/B-round1.md`). The base design, John's decisions and the probe analysis stand as written
there. This note gives the full corrected claim and resume, and maps each finding to its fix.

## Findings → changes

| round-1 finding | change |
|---|---|
| **P1:** a B5 unlink failure, then further claims, leaves an old take that a later resume treats as the map | **One take per window, ever.** A take that cannot be cleaned up **stops that window's claims** until it is. The cleanup is retried at the start of each cycle, and the failure is recorded each cycle. The console is not touched meanwhile, so nothing is lost: it is claimed once the take is gone. "At most one take" then holds in-run as well as across boots, and `mtime` ordering is no longer used. |
| **P2:** the B3 `fsync` failure outcome is undefined | If the directory `fsync` fails after a take, the batch's commands **do not run**. The window gets **one refusal result** ("the claim of this batch could not be made durable: <errno>; none of it ran"), and cleanup proceeds. The record can never outrun the take, and the batch is answered, not dropped. Today this path raises out of `claim()` and the batch is lost without a result (`write_text_atomic`, `console.py:463–468`), so this is an improvement. |
| **P2:** a directory swapped in between B0 and B1, or any non-regular file taken | B2 refuses it with one result, as today's not-a-console rule does. Cleanup removes a non-directory with `unlink`, and a directory with `shutil.rmtree(name, dir_fd=root)`. Anything at the console's name is the claim's to take, and the agent put it there. A cleanup that fails is the one-take rule above. |
| **P2:** reconcile with `open_handles`' pre-check (`console.py:4220–4227`) | **Unchanged.** A link, FIFO or other non-regular console present when the cycle opens the window is that window's recorded failure for the cycle, as today, so nothing is taken. B meets such a file only when it is swapped in during the claim, and then B2 refuses it. |
| **P2:** a held descriptor can finish a complete write after B2, which cleanup discards | **Disclosed as a residual,** next to the in-place rule: writing into the console file in place, rather than replacing it, can lose the batch or be read half-written. |
| **P2:** "variables are recovered" overpromises; the resume deletes its fallback evidence | **Qualified.** The map is recovered from the take when the console carries none, and the resume makes it durable where it can (below). A second crash before the console shows the map can leave it unknown, which is the outcome ADR 0002 (xxxv) already accepts. #42 tracks why an unknown map matters. |
| **P2:** the contract should name the claim point and the directory exception | The wording below says this. |

## The claim (non-quiet path; tier 1's quiet rule unchanged)

| step | action |
|---|---|
| C0 | **Pending cleanup first.** If this window's take name from an earlier cycle still exists, retry its cleanup. If that fails, record the window's failure and **return without claiming**. The console is untouched and stays for later. |
| B0 | Read `console.json` as today. If it is quiet, return `[]`. |
| B1 | **Take:** rename `console.json` to `.console.json.take.<boot>.<n>`, through the window handle. **A successful rename is the claim point.** `ENOENT` means nothing is claimed this cycle. |
| B2 | Read the taken file through its private name, bounded and following no link. **It is the claim**, whatever B0 read. Not a console (including a directory, a link or a FIFO) → one refusal, as today. Its `variables` object, if it has one, is adopted; otherwise the map is kept. An OS error reading it → one refusal naming the error. |
| B3 | When durable, `fsync` the window directory. **If this fails** → one refusal naming it, and the commands do not run. |
| B4 | **Republish** by `link` from a private temporary, `fsync`ed when durable. `EEXIST` means the agent's newer console is left for the next claim. A failure is recorded alongside the batch's verdicts. The console stays absent until the next claim or repair. |
| B5 | **Cleanup:** `unlink` the take, or `rmtree` it if it is a directory. A failure is recorded alongside the verdicts and leaves the take pending (C0). |
| — | Return the batch or the refusal. `_ingest` takes a result plus an optional recorded failure, and **no exception after B1 drops a claimed batch**. |

**Absent at B0:**
1. Try B4's `link`.
2. On success → the one refusal, as today.
3. On `EEXIST` → no refusal; the next cycle claims the agent's console.

**`prepare` and `repair`** republish by `link`, so neither overwrites a console an agent creates in
between.

## Resume (per window, before the first cycle; replaces the console read at `console.py:5014–5023`)

1. **There is at most one take**: the one-take rule holds in-run, and the steps below enforce it
   across boots. Call it `L`.
2. **The map:**
   - `console.json` exists and carries a `variables` object → adopt it. It is either the agent's
     newer file, or the vehicle's copy of the map it took.
   - Otherwise, if `L` carries a `variables` object → adopt it.
   - Otherwise → the map is unknown, as today.
3. **If `console.json` is absent**, republish it with the adopted map by `link`, then `fsync` the
   directory. On `EEXIST`, the agent wrote one: go back to step 2 once with the new console.
4. **Clean up `L`**, then `fsync` the directory. Its commands do not run: it was claimed at its
   take, and the existing crash rule covers it. If cleanup fails, the window starts with a pending
   cleanup (C0).

**Codex's counterexample** (read A, take B, SIGKILL):
- **Absent console:** the map is B's, republished. ✓
- **The vehicle's copy present:** B's map. ✓
- **The agent wrote C after the take:** C's map, or B's if C has none. ✓

**Round-1's P1 ordering** (claim X adopts A; X's cleanup fails; …) can no longer reach "claim Y":
the window stops claiming until X is cleaned up.

## Contract wording (replaces B's draft; vehicle leads, chassis adopts)

> - **Intake is destructive and atomic.** Each cycle the vehicle reads the file. If it holds
>   something to claim (commands, a file that is not a console, or a console with no `variables`
>   while the vehicle holds a map), the vehicle **takes** it by renaming it aside. Whatever is at
>   the name at that instant is taken and claimed, and so is a directory. Then it puts back a console
>   with `commands` emptied and `variables` preserved, **unless you have already written a new one,
>   which it leaves for the next claim**. A command therefore takes effect **at most once**, even if
>   the vehicle dies mid-cycle: the batch was claimed when it was taken. A console whose `commands`
>   is `[]` and which already shows the `variables` is left as it is.
> - **The console can be briefly absent** while a claim takes it, and longer if the vehicle stops
>   mid-claim. Treat an absent or unreadable console as transient, and read again.
> - **Replace the file; do not write into it.** A batch you replace before it is taken is
>   superseded, as on any filesystem. Writing into the file in place can be read half-written, or
>   lost if the vehicle takes the file while you write.
> - A claim that cannot be made durable is refused: one result, and none of the batch runs.

## Residuals (disclosed)

- **In-place writers:** their writes can be read half-written, or lost after B2.
- **A crash after the take:** that batch's commands are lost (the existing crash rule).
- **A second crash** before the console shows a recovered map: the map can be unknown (ADR 0002
  (xxxv); #42).
- **Power loss:** only the `fsync` order covers it, and it is not tested.

## Tests added to B's list

- **A failed cleanup:** the window stops claiming, its console is untouched, and claims resume after
  cleanup. Also the round-1 P1 ordering: no revert after a resume.
- **A failed `fsync` after the take:** one refusal, no effects, and the record carries the refusal.
- **A directory or a FIFO swapped in between B0 and B1:** one refusal, and the directory is removed.
- **Resume with the console present but without `variables`, plus a take:** the take's map is
  adopted.
- **Resume with a pending cleanup that fails:** the window starts blocked, with a recorded failure.
