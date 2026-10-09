# Draft for John: archived conversations in `brief/WORLD.md`

**Not shipped.** Spec §6 makes the brief text John's to approve.

The watchdog now bounds the archived conversations (plan 6, Task 5). That is a fact about the agent's world the brief does not yet state. Nothing the brief says becomes false, but it becomes incomplete. The pruning runs:
- on `done` (exit 42);
- on every restore that starts a fresh conversation: exit 43, and the ladder's `baseline_new` and `rescue_new` rungs;
- once when the watchdog starts.

## Proposed change

`brief/WORLD.md`, "How a run ends", row 42, currently says:

> the conversation is archived to `/work/tombstones/` and a fresh one starts, on `experimental`,
> else `baseline`, else `rescue`, after a pause

Proposed:

> the conversation is archived to `/work/tombstones/` and a fresh one starts, on `experimental`,
> else `baseline`, else `rescue`, after a pause

Unchanged, plus one paragraph after the table:

> Archived conversations are bounded. Whenever a conversation starts fresh, the watchdog keeps the
> newest twenty in `/work/tombstones/` (within 128 MiB) and in the git directory (within 64 MiB)
> and deletes the older ones; the archive just made is always kept, even when it alone is larger
> than the budget. These names are reserved for the harness's archives, and any file bearing one
> may be deleted, whoever wrote it: `session_<date>_<time>_<micro>.json`,
> `corrupt_session_<date>_<time>_<micro>.json` and `session_recovery_<n>.json`. Notes, the
> messages `done` leaves (`incarnation-*.txt`), and files under any other name are never touched.
> A note may name an archive that has since been deleted. The figures and the names are in your
> `watchdog.py`, and yours to change.

## Sources

- `harness/watchdog.py`: `ARCHIVE_KEEP`, `ARCHIVE_TOMBSTONE_BYTES`, `ARCHIVE_GIT_BYTES`, `TOMBSTONE_ARCHIVES`, `GIT_ARCHIVES`, `prune_archives`, and its calls in `Recovery.restore` and `run_watchdog`.
- `harness/tests/test_archive_pruning.py`.
