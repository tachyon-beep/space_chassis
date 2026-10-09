# Draft for John: one clause in `brief/WORLD.md`

**Not shipped.** Spec §6: John approves brief text. The watchdog now bounds the archived
conversations (plan 6, Task 5), which is a fact about the agent's world that the brief does not yet
state. Nothing the brief says becomes false; it becomes incomplete.

`brief/WORLD.md`, the "How a run ends" table, row 42, currently:

> the conversation is archived to `/work/tombstones/` and a fresh one starts, on `experimental`,
> else `baseline`, else `rescue`, after a pause

Proposed:

> the conversation is archived to `/work/tombstones/` (the newest twenty archives are kept,
> within 128 MiB; the figures are in your `watchdog.py`) and a fresh one starts, on
> `experimental`, else `baseline`, else `rescue`, after a pause

Source: `harness/watchdog.py` `ARCHIVE_KEEP`, `ARCHIVE_TOMBSTONE_BYTES`, `prune_archives`;
`harness/tests/test_archive_pruning.py`.
