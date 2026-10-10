> **Historical record**, copied into governance on 2026-10-10 from a session scratchpad. Paths under `scratchpad/` or `/tmp/` inside it were ephemeral and may no longer exist; line numbers refer to the commits it names. Do not edit — supersede with a new dated record.

# #21 fix round on 06f08a3 — consolidated review findings (binding)

Sources: Codex astra high ×2 (Cx-A = coordinator's, Cx-B = the other session's, verbatim at
scratchpad/review-wp083-codex-666827.md), Fable (scratchpad/review-wp083-fable-666827.md), Claude
Opus (appended below when it lands), the clean gate at 06f08a3 (evidence/wp08-3-06f08a3-r2), and the
chassis dry run (filigree space_chassis-93010ff54e comment 40). Line numbers are at 06f08a3.

Fixes go in NEW commits on top of 06f08a3 (no history rewrite), each `vehicle: <finding/outcome>`,
suite green at each, each with a test that fails before it. Group by theme; roughly one commit per
numbered item below.

## Must fix

**F1. A successor whose header is damaged is skipped, dropping durable rows after the anchor** (Cx-A P1,
Cx-B P1). `_first_header()` returns `None` at the first malformed line (console.py:1789–1791) and the
anchored successor discovery skips the file (1935–1937). A file in the state directory that is
neither a verifiable successor nor provably irrelevant must REFUSE (exit 3, naming the file and the
check), never be skipped. Only these may be ignored: files with no segment header and only unchained
startup events (refused/aborted starts), and segments provably before the anchor. A torn-at-first-append
file (F2) is the existing narrow exception — keep it, and make sure it cannot be used to skip a file
that holds a complete row. Test: checkpoint boot A at T; boot B records T+1…L; damage B's header,
keep its rows; restart → exit 3 by name (both the anchored and the unanchored read agree).

**F2. Obligations leave before the result's name is durable** (Cx-A P1, Cx-B P1). Re-publication removes
obligations before the output/ directory fsync (2871–2874); the live path marks receipts `landed`
before the directory sync (4054–4061, 2762); a deduped existing result gets no directory sync. A result
leaves the obligation list (and counts as landed) only after its file AND the output/ directory are
fsync'd; a deduped existing file gets an fsync of the file and the directory before it counts. If the
directory fsync fails, the obligation stays. Test: inject EIO on the output/ directory fsync during
re-publication and during live publication; the obligation survives the following checkpoint.

**F3. Checkpoint v2 accepts values resume cannot use** (Cx-A P2). Validate in `_structure_problem` (or the
v2 schema): each obligation carries every field re-publication reads (command/body or fingerprint
fields as re-publication requires, with types); `clock.N` is a positive int. A correctly hashed but
malformed checkpoint is then refused as corrupt (K2 fallback applies), never a KeyError/TypeError.
Tests: hashed checkpoint with an obligation missing `command`; with `clock.N = []` → treated as
corrupt by name.

**F4. Record I/O errors escape as tracebacks and leak descriptors** (Cx-B P2; Cx-A P3 for the
constructor). `os.listdir` EIO at 1894 escapes `_resume` (which catches only RecordRefused) and leaks
the dup'd fd; the Executive constructor dups state/journal fds before validating `checkpoint_every`
(2496–2499, 2512–2514). Every OSError on the resume/record path becomes an exit-3 refusal naming the
file and errno; every dup is closed on every path (try/finally). Tests: EIO from listdir → exit 3,
no fd leak (count /proc/self/fd); constructor refusal → no leak.

**F5. The dedupe filter misses fingerprint-only commands with leading whitespace** (Cx-B P2). The
filename filter uses the parsed verb (2289) while original filenames come from the raw command. Build
the expected filename prefix exactly as the writer does (same sanitiser on the same raw string). Test:
six `'  zzz' + 'x'*2500` commands, kill after files synced and before the note → no duplicates.

**F6. The interrupt-mid-cycle test crashes its xdist worker** (gate at 06f08a3; chassis comment 40).
`test_a_run_ending_cleanly_checkpoints_its_last_completed_cycle_and_an_interrupt_mid_cycle_does_not`
raises a real KeyboardInterrupt from monkeypatched sleep/claim; under xdist it kills the worker and
aborts the session. Make it impossible for that test to take the worker down: run that half in a
subprocess and send SIGINT, or raise KeyboardInterrupt only inside `pytest.raises` with the console's
handler proven to catch it — whichever tests the real behaviour. Prove it with `-n 6` runs of the
whole file, three in a row, plus the test alone.

**F7. The compare-point cost ratio is load-sensitive** (gate: 3.4× > 3×; chassis: 6.0×). Child 6's
`test_the_compare_point_is_plain_sorted_json_at_the_c_encoder_s_cost` takes two medians in sequence.
Interleave the two measurements and compare minima (best-of-N), which is robust to load; keep the 3×
bound. Do not loosen the bound to pass.

## Should fix (lows)

**F8.** A kill after row 1's fsync and before the first root-record write (T=0, L=1) is journaled as
`root_record_rewritten` (tampering) (Fable 1; 4286–4313). With T=0, an unbound record at tick 0 is
routine. Test it.
**F9.** S11's "move the journal aside" sentence is reachable only on a clean diode directory (Fable 2;
5021–5072). With a verified-checkpoint-less state directory holding a record, refuse with the S11
sentence first (it names the state directory, which is the problem), before the diode/root checks.
**F10.** ADR 0002:777 claims a journal event and consecutive count for a failed clean-end checkpoint;
code writes stderr only (4903) (Cx-B P3). Make the code match the ADR (journal it) — the operator
reads the journal.
**F11.** Docs: `wall_down→wall_up` includes the vehicle's own start-up (Fable 3) — one clause; a changed
`--journal` refusal names the previous journal path (Fable 4).
**F12.** Test gaps (Cx-B): the flood test must exhaust the byte cap, not only the entry cap; B2 must
also be exercised through the B3 resume checkpoint (kill at each write step of the resume checkpoint
after a fall-back), not only through a cadence write.

## Then
README round section: add the fix round's findings in the same "each a test that failed first" form
and the referee count; ADR 0002 amendment for any changed semantics (F1's refusal, F2's ordering,
F3's validation). Gate as before. Report SHAs, which tests failed before each fix, gate tails.

## From the Claude Opus code review (approve with findings; probes under scratchpad/review-wp083-code-opus/)

**F13 (Medium, must fix). A newline-terminated torn tail in a shared `--journal` becomes a permanent
crash loop.** `append_journal_line` (994) and `_record_handle` (3013–3014) end an unterminated tail with
`\n`. A write torn exactly after a complete row's or header's closing `}` is read as torn (L excludes
it), then the next boot's `\n` turns the fragment into a valid line, and every later resume and the
offline read refuse (`overlap: segment C begins at tick 3, before …` / `chain: 2 segments name A as
their predecessor`; repro `probe_newline.py`). Terminate an unterminated tail with a byte sequence that
can never parse as a line (e.g. `b"#\n"`) at both sites; the verifier treats such a line as the torn
fragment it is. Test: strip the final `\n` from a complete row and from a header in a shared journal,
resume, run, resume again, then a whole-record read — all succeed.

**F14 (should fix). A resume's anomalies never reach stderr.** `_resume` rewrites a mismatched root
record (4541–4548) and records `pending.json` advisories (4486–4496) only in the private journal; a
fall-back shows only in the stdout banner. `docker compose logs vehicle` is the operator's view: one
stderr line for the `rewrite` class, one per advisory, one for a fall-back naming the rejected file.

**F15 (should fix). Two path re-resolutions design §6 said would be fixed were not.** `Executive.__init__`
opens `self.diode_dir.resolve()` (2582); `write_serves_record` writes `Path(diode_dir).resolve()` (2353)
while `main` compares against `diode_canonical.path` (4850). Write `diode_canonical.path`; pass a dup'd
`diode_fd`. Same canonicalisation on both sides, or every restart could refuse "serves another diode
directory".

**F16 (should fix). An explicit `--journal` anchor checks only the byte before the offset** (`read_record`
1859, `anchor_name = names[0]`). A different file of exactly `offset` bytes resumes at T with zero rows.
Require that the line ending at `offset` is a verifiable line whose chain equals the anchor's `chain`
(this also strengthens F1's seek-point validation for the state-dir layout).

**F17 (docs/wording).** ADR (xxix)'s `variables` residual: the loss applies to "a console that carries no
`variables` object at the resume" (a contract-legal `{"commands": [...]}`), not only an unreadable one —
reword; the per-row `failures` count resetting per boot goes in the ADR and README; `wall_up` is stamped
after replay (fold into F11's clause); the `--ring-slots` refusal's "for window 'a' for world W" reads
awkwardly — rephrase.

**F18 (tests).** Beyond F12: the flood test must fail with a no-op `results_on_disk` (decoys ≥ 512 B
totalling past 256 KiB, plus a case asserting `found == {local}`); `OBLIGATIONS_PER_WINDOW`'s give-up
gets a test; 28186 gets an uninterrupted-run oracle for `met_s`; 27030 compares counters per tick, not
only at 160; the fd test 28478 must also catch builtin `open()` / `Path.read_*` (e.g. audit hook via
`sys.addaudithook` on `open`).

## Coordinator rulings (binding; override anything above they touch)

**R1. One rule for an unparseable line (F1, F13, F16 together).** An unparseable line in a record file is
a torn fragment only if it is the last line of its file, or it is followed only by a new boot's
unchained startup events and then that boot's segment header. Anywhere else — in particular followed by
a complete row — it is corruption and refuses by name. F13's terminator (`#\n` after an unterminated
tail) produces exactly such a fragment. The anchored read, the whole-record read and `replay_record` all
apply this one rule (one helper, not three copies). A file that is not a verifiable successor and not
provably irrelevant refuses (F1). The line ending at the anchor offset must verify with the anchor's
chain (F16).

**R2. F2's ordering includes the note.** The `results_written` note is appended only for results whose
file fsync AND output/ directory fsync succeeded; a result whose directory fsync failed stays owed and is
not noted. `landed`, the obligation list and the note all follow the same barrier.

**R3. F6 is a subprocess receiving a real SIGINT**, for both halves (clean end checkpoints; interrupt
mid-cycle does not). Not a BaseException subclass (tests nothing: the console catches KeyboardInterrupt
specifically) and not a KeyboardInterrupt subclass (pytest/xdist still treat it as an interrupt).

**R4. F3's refusal says what failed**, e.g. "body verifies; `obligations[3]` lacks `command`", so the
operator does not go looking for a bad disk. Classifying it as corrupt (K2 fallback applies) is right.

**R5. Commits — fix on top, grouped, nine or so**, each with its failing-first test(s):
(1) record integrity: F1 + F13 + F16 under R1; (2) durability ordering: F2 under R2; (3) refusals not
tracebacks: F3 + F4 under R4; (4) dedupe and its tests: F5 + F12 + F18; (5) F6 under R3; (6) F7;
(7) operator view: F8 + F9 + F14; (8) paths: F15; (9) docs: F10 + F11 + F17, README round section
("the review round", each finding a test that failed first, referee count) and ADR 0002 amendment for
F1/F2/F3/F13 semantics.
