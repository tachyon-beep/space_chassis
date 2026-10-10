> **Historical record**, copied into governance on 2026-10-10 from a session scratchpad. Paths under `scratchpad/` or `/tmp/` inside it were ephemeral and may no longer exist; line numbers refer to the commits it names. Do not edit — supersede with a new dated record.

# #21 fix round 3 on d0a20dc — Codex confirmation findings (binding)

Source: Codex (`gpt-6-astra` high) confirmation of round 2 — request changes; G2, G3, G6, G7, G8
confirmed. Coordinator's own re-run of the Opus probes at d0a20dc: an all-damaged successor refuses by
name (anchored read, whole read, resume); the torn-newline probe still resumes 3→3→5 with a joined
whole-record read. Line numbers at d0a20dc. Fix on top, `vehicle: <finding/outcome>`, a test that fails
first, suite green at each commit, both trailers.

**H1 (P2) — G5's adjacency rule refuses a legitimate crash loop at start-up.** console.py:1599 rejects two
adjacent fragments, but the startup writer (1010–1011) produces them in a shared journal when two
successive resumes are killed mid-way through their `resumed` event: boot 2 terminates boot 1's cut
tail with `#\n` and is itself cut; boot 3 terminates that one. A third resume then refuses as corrupt.
**Replace the adjacency rule with the terminator rule (supersedes R1's position test and G5):** an
unparseable line is a torn fragment if and only if it is (a) the file's final, unterminated line, or
(b) a line that ends with `TORN_TAIL_TERMINATOR` — i.e. a cut tail a later writer marked. An unparseable
line ending in a plain `\n` is corruption, wherever it is. Every reader (anchored, whole-record, replay,
first-header discovery) uses this one predicate. The writer must therefore always mark a cut tail with
the terminator before appending (check every append site: `append_journal_line`, `_record_handle`, any
other). Tests: (i) two and three successive resumes killed mid-`resumed`-event in a shared journal →
the next resume succeeds and the whole-record read joins; (ii) the same with kills mid-header and
mid-first-row; (iii) every line of a successor damaged with plain newlines (the Opus probe) → refused;
(iv) a damaged line in the middle of a segment → refused; (v) the state-dir layout's own-file cut tail
(unterminated last line) still reads as torn.

**H2 (P2) — G4: close the class, not the call.** `open_private_dir` (5098) → `walk_open_dir` (827 root open,
849 fstat) can still raise past main and leak the already-open journal descriptor; the constructor's new
diagnostic (5517) drops `exc.filename`. Restructure `main`'s start path so that every held descriptor is
registered in one `contextlib.ExitStack` (or equivalent) the moment it is opened, and one boundary
`except OSError` turns any error from the start path into exit 3 naming `exc.filename` (or the path being
opened) and the errno, after the stack closes everything. Test it systematically: parametrize an EIO
injection over each OS call on the start path (`os.open`, `os.fstat`, `os.listdir`/`scandir`, `os.read`,
`os.write`, `os.fsync`, `os.rename`/`replace`, `os.mkdir` as reached) for a fresh start, a resume and
`--init`; each → exit 3 with the filename, and no descriptor outlives `main` (count `/proc/self/fd`).

**H3 (P3) — G1 leftover: a by-name symlink check in `attach`.** console.py:2906 checks `root.is_symlink()`
through the original spelling; with the alias retargeted after the diode handle is open, attach refuses
falsely. Make every check about a window directory go through the held diode handle (`os.lstat(slug,
dir_fd=diode_fd)` / `O_NOFOLLOW` opens), never a path built from `--diode-dir`'s spelling. Grep for any
other `Path(diode_dir) / …` or `self.diode_dir / …` filesystem access on the live path and convert it.
Test: retarget the alias to a directory containing an `alpha` symlink after the open → attach proceeds
against the held handle (and a symlink inside the held directory still refuses).

Then: README "confirmation round" table extended; ADR 0002 J amendment for the terminator rule (and say it
supersedes (xxxi)/G5's adjacency wording); referee count. Gate: three full 3.12 runs, touched tests on
3.13. Report SHAs, tests failed before, choices, gate tails.

## Coordinator refinements (binding)

- **H1 predicate, tightened to match the writer:** a `#\n`-terminated fragment may be followed only by a
  new boot's unchained startup event, a segment header, another terminated fragment, or EOF — never by a
  chained row or note; a terminated fragment followed by a chained line refuses. And make the design's
  `max(published_tick) ≤ L` a named refusal, not an `assert`, since this predicate now decides `L`.
- **H1 test with real resumes:** at least one of tests (i)/(ii) must use real `resume_executive` boots with
  their B3 resume checkpoints between the kills (not synthetic files), so it proves the anchor sits after
  the last intact line, before the marked fragment and the startup events — an anchor after the fragment
  would make G2 refuse every resume after a start-up kill.
- **H2:** register each descriptor with the path it was opened for, so a refusal from an fd-based call
  (`fsync`, `fstat`, where `exc.filename` is `None`) still names the file. Scope the boundary
  `except OSError` to the start path only; once the first cycle claims, OSErrors keep their existing
  per-cycle handling.
- **Stopping rule:** this is the last fix round before the PR. If its confirmation finds only P3,
  cosmetic or trust-model points, they are filed as one vehicle issue and listed in the PR as residuals.
