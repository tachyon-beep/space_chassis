> **Historical record**, copied into governance on 2026-10-10 from a session scratchpad. Paths under `scratchpad/` or `/tmp/` inside it were ephemeral and may no longer exist; line numbers refer to the commits it names. Do not edit — supersede with a new dated record.

# #21 fix round 4 on f12e522 — Codex confirmation of round 3 (binding)

Source: Codex (`gpt-6-astra` high) — request changes on two P2; H1, H2, H3 confirmed; no P1, no regression
from round 3. Coordinator's own evidence at f12e522: Opus's all-damaged and torn-newline probes behave;
SIGKILL stress ×15 in both layouts clean (contiguous ticks, whole-record replay from genesis equal at every
tick, 0 duplicates, 0 recorded-without-result, 0 result-without-record). Gate at f12e522 running. Line
numbers at f12e522. Fix on top, `vehicle: <finding/outcome>`, a test that fails first, suite green at each
commit, both trailers.

**J1 (P2) — a transient configuration read error poisons every later checkpoint's identity.**
`tools/plant.py:379` (`corpus_files`) uses `glob`, which swallows an EIO and silently drops entries;
`tools/checkpoint.py:179` hashes the short list; `tools/console.py:3095–3099` caches that identity and
stamps it on every later checkpoint (genesis 5608, B3 5380, cadence), so every later restart refuses as
incompatible — a world lost to one transient error. Fix: enumerate the corpus explicitly (`os.scandir` /
`os.walk` with an `onerror` that raises, or equivalent) so an unreadable directory or file raises with its
path, never shortens the list; an error computing the identity at a start is a start refusal by name (H2's
boundary); at a cadence checkpoint it is a checkpoint failure (journaled, run continues) and never a cached
wrong identity. Tests: EIO on a `scandir` of a corpus directory during (a) the start's identity, (b) genesis,
(c) a B3 resume checkpoint → refusal by name / no checkpoint written with a short identity; after healthy
I/O returns, the next start resumes. Include configuration enumeration in the H2 injection set (drop the
exclusion at tests:29851–29854).

**J2 (P2) — a partial advisory append corrupts the next durable row.** `console.py:3124–3133` suppresses
errors appending `checkpoint_failed`; after a partial write the cached record handle (3325–3326) appends
the next row straight after the fragment (3387–3389), producing an unparseable plain-newline line that
recovery refuses as corruption. Fix (one discipline for every append to the record file, advisory or
chained): note the file offset before the append; on any error or short write, `ftruncate` back to that
offset and fsync, restoring a clean tail; if the truncate itself fails, the record is unwritable — stop
the run before another cycle (`RecordUnwritable`). Do not paper over it with a terminator before a chained
row (that breaks H1's predicate). Test: fail a cadence checkpoint, write its failure event partially then
raise EIO; the next cycle's row lands on a clean line and a resume reads it; and the truncate-fails case
stops the run.

**Should fix if small (P3, same code):**
- **J3.** An exactly maximum-length row cut before its newline and then marked exceeds the reader's line
  limit by one byte (3382, 1565), so a legitimate extreme-size crash sequence can refuse. Let the reader
  allow `MAX_RECORD_LINE_BYTES + len(TORN_TAIL_TERMINATOR)` for a marked line (or make the writer's limit
  leave room). Test at the boundary.
- **J4.** `close()` errors can escape the start path's stack cleanup (5631–5637), and a parent-close error
  in `walk_open_dir` can leak the newly opened child (849–857). Close everything, suppressing close errors
  after the first exception, and include `close` in the injection set.

**Residual (not fixed here; filed as one vehicle issue and listed in the PR):** markers give syntax, not
authenticity — a crafted startup object need not really be unchained or from a new boot
(`_startup_event()` 1738–1741 excludes two event names); this is inside the stated trust model (the state
directory is private; the unread prefix is attested by the checkpoint).

Then: README round table extended (fourth round); ADR 0002 J amendment for J1/J2; referee count. Gate:
three full 3.12 runs, touched tests on 3.13. Report SHAs, tests failed before, choices, gate tails.
