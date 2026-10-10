> **Historical record**, copied into governance on 2026-10-10 from a session scratchpad. Paths under `scratchpad/` or `/tmp/` inside it were ephemeral and may no longer exist; line numbers refer to the commits it names. Do not edit — supersede with a new dated record.

# #21 fix round 2 on 0647ee2 — confirmation findings (binding)

Sources: Codex (`gpt-6-astra` high) confirmation — **request changes**; Claude Opus confirmation —
**approve with findings** (every first-round Opus finding closed; SIGKILL stress at 0647ee2 in both
layouts: contiguous ticks, 0 records without a result, 0 results without a record, 0 duplicates;
"recorded twice" settled as the stress harness writing a claimed command back into console.json, not the
vehicle). Line numbers at 0647ee2. Fix on top, `vehicle: <finding/outcome>`, a test that fails first,
suite green at each commit, both trailers.

**G1 (P1, Codex) — F15 incomplete: private-path checks re-resolve the diode alias.** console.py:5005 saves
one destination, but :5022 → :871 resolves the original `--diode-dir` spelling again, and journal
checking does the same at :919. Retargeting an alias between the resolutions lets `--state-dir` (or
`--journal`) pass confinement against the new destination while main serves the original — private state
inside the active diode. Resolve `--diode-dir` exactly once and pass that canonical path (or the held
handle's identity) to every confinement check. Test: retarget the alias between the first resolution and
the confinement check (not only during construction, as tests:29261 does) → refused.

**G2 (P2, Codex) — F16: the anchor line must be a verifiable record line, not matching metadata.**
console.py:1895–1903 accepts any object carrying the anchor's `chain`, `boot_id`, `world_id`, `tick`.
Require the line ending at the offset to pass the record verifier's own schema for its kind (row, note or
header) AND its chain to recompute (`chain == sha256(previous chain + canonical bytes)`, reading the
preceding line bounded by `MAX_RECORD_LINE_BYTES`; a header's chain per its own rule). Test: a padded
replacement journal whose object at the offset copies the four fields → refused by name (both read paths
agree).

**G3 (P2, Codex) — F3: the obligation discriminator.** checkpoint.py:513 tests `fingerprint_only is True`;
consumers use truthiness (console.py:2361, 2418). Validation must refuse a non-bool `fingerprint_only`
(and any other field whose type consumers branch on); consumers use the same exact predicate. Test:
`"fingerprint_only": "yes"`, rehashed → corrupt by name, K2 falls back.

**G4 (P2, Codex) — F4: the no-checkpoint record scan.** console.py:4484 `listdir` has no `OSError` handling
and its caller (:5264) no cleanup. Every OSError on every start path → exit 3 naming file and errno, every
held handle closed. Test: EIO there → exit 3, no descriptor leak.

**G5 (Low–Medium, Opus N1) — a file whose every line is unreadable is skipped.** `_torn_aware_lines` (1566)
yields a fragment followed directly by another fragment as torn, and `_first_header` continues past
fragments, so a successor (or the anchored segment after its anchor) with every line damaged reads as
empty and the resume comes back short of published ticks — contradicting ADR (xxxi). Rule (refines R1):
**two fragments with no complete line between them are corruption**; a fragment followed by complete
startup-event lines and then another fragment (repeated startup kills) stays allowed. Test: damage every
line of a successor, and every line after an anchor → refused by name; the repeated-startup-kill tests
(26739, 28751) still pass.

**G6 (Low, Opus) — the rewrite line is printed before the rewrite.** console.py:4802 says "was rewritten"
before the write (~4814). Print it after the write succeeds; on failure only the failure is printed.

**G7 (Low, Opus) — F8 widened "routine" beyond what a kill can produce.** `classify_root_record` treats an
unbound tick-0 record as routine whenever T = 0, for any L. A kill after the first row leaves L ≤ 1. Bound
it: routine only when T = 0 and L ≤ 1; otherwise the existing rewrite/mismatch class. Test both sides.

**G8 (cosmetic, Opus)** — `'a''s pending.json` (4809): write "window 'a': its pending.json …".

Also (Codex, informational): F1's repeated-fragment handling has no dedicated repeated-startup-kill test
of its own — add one if G5's tests do not already cover it.

Then: README round section gains a short "confirmation round" table in the same form; ADR 0002 J
amendment for G2/G5/G7 semantics; referee count. Gate as before (three full 3.12 runs, touched tests on
3.13). Report SHAs, tests failed before, gate tails.
