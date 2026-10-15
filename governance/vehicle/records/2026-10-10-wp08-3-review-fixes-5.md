> **Historical record**, copied into governance on 2026-10-10 from a session scratchpad. Paths under `scratchpad/` or `/tmp/` inside it were ephemeral and may no longer exist; line numbers refer to the commits it names. Do not edit — supersede with a new dated record.

# #21 fix round 5 on a38cee1 — Codex confirmation of round 4 (binding)

Source: Codex (`gpt-6-astra` high) — request changes on one P2; J1, J1a, J2's routing, J3's bounds and J4's
stack cleanup confirmed; no P1. Coordinator's own evidence at a38cee1: Opus's all-damaged and torn-newline
probes behave; SIGKILL stress ×15 in both layouts clean (state-dir 748 ticks, 646 receipts; journal 601
ticks, 476 receipts; contiguous, replay from genesis equal at every tick, 0 duplicates, 0 recorded without
result, 0 result without record). Line numbers at a38cee1. Fix on top, `vehicle: <finding/outcome>`, a test
that fails first, suite green at each commit, both trailers.

**K1 (P2) — a close in cleanup replaces the rollback's `RecordUnwritable`.** `append_journal_line`'s
`finally: os.close(fd)` (console.py:1029) runs after `append_or_restore` raises `RecordUnwritable`
(:1088); if the close fails too, its `OSError` replaces it, and the advisory handlers (`checkpoint_failed`
:3217, `results_republished` :5038) swallow the replacement as an ordinary advisory failure: the run
continues with a fragment at the record's end, the next row follows it, and the next start refuses the
record as corrupt. A failing disk presents exactly this way (writeback errors surface at `close`). The
clean end likewise returns 0 instead of 3. Fix: **a close in cleanup never replaces an exception already
propagating** — the discipline `_StartPath.closing` applies, now on every record-write path: on the
exception path, `suppress(OSError)` around the close and re-raise the original; on the no-exception path a
close failure still raises. That covers the inner `close(fd)` and the outer `close(opened)` (:1034) here;
grep every `finally:` / `except BaseException:` + `os.close` pair on a path that writes the record or the
checkpoint (`_record_handle`, the checkpoint writer, the segment opener) and apply the same. Tests: extend
the holding tests at tests:30142, :30183 and :30210 with a concurrent close failure (partial write → write
EIO → truncate EIO → close EIO): `checkpoint_or_record` raises `RecordUnwritable` and the run stops; the
`results_republished` case refuses the resume; the clean end exits 3 by name.

**K2 (P3, trivial, same function as J1a).** `checkpoint.py:189` `path.read_bytes()` raises without its
path on an `EIO`; attach it (`exc.filename = str(path)` when `None`, or re-raise naming it). One test: EIO
on the read → the refusal names the file.

**J4 leftovers (only if each is a one-line `suppress` while a refusal is in flight; otherwise residual):**
an explicit early `close()` after a refusal can replace that refusal or escape `main` — the lock-write
failure then close failure at :5410 escapes through `prepared()` (:5771), outside H2's handler; B3
(:5514), attach (:5717) and genesis (:5741) can replace their refusal with a close error.

**Residual (not fixed; one vehicle issue, listed in the PR):** J3's repeated interrupted terminator — a
maximum-length row cut to `limit − 1` bytes, then two successive start-ups each cut after writing only
`#`, leaves `limit + 1` unterminated bytes that the reader refuses (by name: no silent loss); the
crafted-startup-object trust-model point from round 4; any J4 combination not fixed above.

**Termination (binding).** Round 5's confirmation is scoped to `git diff a38cee1..<round-5 head>`: K1,
K2, any J4 leftovers and regressions. A sixth round happens only for a P1 anywhere or a P2 inside the
round-5 diff; everything else goes to the residuals issue.

Not a finding: the engine identity changes across these commits (`plant.py` and `console.py` are hashed),
so a checkpoint from an earlier commit is a different engine — designed behaviour; the chassis retakes its
pins from the merge SHA.

Then: README round table (fifth round), ADR 0002 J amendment if the semantics move (K1 states the cleanup
rule), referee count. Gate: let the f620f0a per-commit run finish; run the per-commit suite at a38cee1 and
at each round-5 commit; three full 3.12 runs at the round-5 head, touched tests on 3.13. Don't spend the
three full runs at a38cee1. Report SHAs, tests that failed first, choices, gate tails, and the name of the
gate summary file you write.
