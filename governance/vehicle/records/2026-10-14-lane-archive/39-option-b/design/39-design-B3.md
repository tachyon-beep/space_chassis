# #39 option B, revision 3

Vehicle line, Space Vehicle [610587], 2026-10-11. **Design, no code.** It revises `39-design-B2.md`
(sha256 `30416367…`), which Codex reviewed in round 2 (`reviews/B-round2.md`: request changes; no
SIGKILL replay, double-answer or claim-without-result ordering found). Everything B2 says that is
not restated here stands: the base claim B0–B5, absence at B0, `prepare` and `repair` by `link`,
the `open_handles` pre-check, and the residuals.

## Round-2 findings → changes

| finding | change |
|---|---|
| **P1:** a take whose cleanup keeps failing survives a later map adoption, and a later resume resurrects its old map | **A take is map evidence only for the boot that made it** (§1). The take's name carries the **executive's** `boot_id`. At resume, a take is evidence only if that `boot_id` is the record's **newest segment** (`journal.<boot_id>.jsonl`, `console.py:302`; the segment headers carry `boot_id`, `:1345`), the boot that just ended. Any take from an earlier boot is retired. A take that outlives one resume therefore never speaks for the map again. Codex's ordering reaches the next resume with `L` from boot 1 and a newest segment from boot 2, so the map is unknown (ADR 0002 (xxxv)), never `A`. |
| P1 (the step-3 re-check) | Step 3 runs only when the console was **absent** at step 2. Its one re-check, after `EEXIST`, adopts the agent's new console's `variables` if it carries one, and otherwise keeps the map step 2 chose. It never looks for absence again. |
| **P2:** refusing after a failed barrier does not make the take durable; a power loss can restore the console and run a refused batch | **No answer until the take is durable** (§2). If B3's directory `fsync` fails, the claim answers nothing and runs nothing. The take stays pending, and the window records the failure. C0 retries the barrier each cycle, and only once it succeeds does the claim continue from B2 with that take. A power loss before the barrier can at most restore the console, which then holds a batch that was never answered. B2's "one refusal on `fsync` failure" is withdrawn. |
| **P2:** C0 can block a window indefinitely (an undeletable directory) | **Quarantine before block** (§3). When cleanup cannot remove the take, it renames the take to `.console.json.dead.<boot>.<n>`, a same-directory rename, which works where `rmtree` fails on a read-only subtree. A dead file is never evidence and **does not block**. The window records it once, with the path, and retries removing dead files at each start of the window. Claims block only if that rename also fails. That is visible every cycle as the window's recorded failure naming the take, and is cleared when the take is removed by anyone: the agent can remove it, since it is in the agent's own window, or the operator can. |
| P2: contract wording | It now states the pre-check exception and the blocked state (§4). |

## 1. Map evidence at resume (replaces B2's resume step 2)

Let `last` be the `boot_id` of the record's newest segment (the boot that ended), and `L` the take,
if any, whose name carries `last`.
1. **Retire every other take:** remove it, or quarantine it as in §3. It is a claimed batch, and the
   existing crash rule covers it.
2. **The map:**
   - if `console.json` carries a `variables` object → adopt it;
   - else if `L` carries one → adopt it;
   - else → unknown, as today.
3. **If the console was absent at step 2:**
   1. Republish it by `link`.
   2. `fsync` the directory.
   3. On `EEXIST`, run the one re-check above.
4. **Retire `L`** (remove it, or quarantine it), then `fsync` the directory. If neither works, the
   window starts blocked (§3).

**Why one boot's take is enough.** In-run, the one-take rule holds: C0 blocks a second take while
the first still exists. And a take is evidence only to the resume immediately after its boot. Its
map is then either the newest claimed map, or older than the console's own `variables`, which win.

## 2. Durability before any answer (replaces B2's B3)

| step | action |
|---|---|
| B3 | When durable, `fsync` the window directory. **Failure:** answer nothing and run nothing. The take stays pending under its name, and the window's failure is recorded. **Return no batch.** |
| C0 | When a take is pending, first retry the directory barrier. If it succeeds, continue at B2 with that take: read, adopt, answer, republish, clean up. If it fails, record and return. |

**What a crash does here.** A SIGKILL or power loss while the take is pending leaves a take that was
never answered.
- **Power loss** may restore the console instead. Its batch was never answered, so claiming it later
  is its first answer, not a replay.
- **SIGKILL:** the next resume treats the pending take as `L` (§1). Its commands are lost under the
  existing crash rule, and its map is evidence.

## 3. Cleanup, quarantine, block (replaces B2's B5 and C0 blocking)

| step | action |
|---|---|
| B5 | **Remove the take:** `unlink`, or `rmtree(dir_fd=…)` for a directory. **If that fails,** rename it to `.console.json.dead.<boot>.<n>`; dead files are never evidence and never block. **If that also fails,** the take stays and the window is **blocked**. |
| C0 | **Blocked:** retry B5 each cycle. While blocked, record the window's failure each cycle, naming the take's path and saying that removing it unblocks the window, then return. **Dead files:** try removing them when the window opens. A failure is recorded once per boot. |

The console is never touched while the window is blocked, so nothing the agent writes is lost; it
waits. The block persists across restarts until the take is gone.

## 4. Contract wording (replaces B2's)

> - **Intake is destructive and atomic.** Each cycle the vehicle reads the file. If it holds
>   something to claim (commands, a file that is not a console, or a console with no `variables`
>   while the vehicle holds a map), the vehicle **takes** it by renaming it aside. Whatever regular
>   file, or directory, is at the name at that instant is taken and claimed. It then puts back a
>   console with `commands` emptied and `variables` preserved, **unless you have already written a
>   new one, which it leaves for the next claim**. A command takes effect **at most once**, even if
>   the vehicle dies mid-cycle: the batch was claimed when it was taken. A console whose `commands`
>   is `[]` and which already shows the `variables` is left as it is.
> - **A console that is a link, a FIFO or a directory when the cycle starts is not read.** The window
>   is skipped that cycle, and its failure is published.
> - **The console can be briefly absent** while a claim takes it, and longer if the vehicle stops
>   mid-claim. Treat an absent or unreadable console as transient, and read again.
> - **Replace the file; do not write into it.** A batch you replace before it is taken is
>   superseded, as on any filesystem. Writing into the file in place can be read half-written, or
>   lost if the vehicle takes the file while you write.
> - **If the vehicle cannot clear what it took** (rare: a directory it cannot remove and cannot move
>   aside), the window stops claiming until that file is gone. The failure names it, and your
>   console waits untouched.

## 5. Tests added to B2's list

- **Codex's round-2 P1 ordering:**
  1. A take from boot 1 survives because cleanup failed.
  2. Boot 2's resume adopts console map B, and cleanup fails again.
  3. The agent writes a console with no map.
  4. A kill.

  Boot 3 must come up with the map unknown, never A.
- **The B3 barrier fails:** no result is answered, nothing runs and the take stays pending. When the
  barrier later succeeds, the batch is answered once. A simulated power loss that restores the
  console leads to one answer, not two.
- **Cleanup fails on a read-only subtree:** the take is quarantined, nothing blocks and the next
  claim proceeds. If quarantine fails too: a block that names the path every cycle and clears when
  the take is removed, including across a restart.
- **The step-3 re-check** with a console that has no map, created during resume.
