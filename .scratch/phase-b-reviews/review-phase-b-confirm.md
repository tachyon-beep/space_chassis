**Land after fixes.**

**Critical:** None found.

**Important:**

1. **I3 remains partly fixed: identity retries can fail on healthy publication.** [live/test_vehicle.py:123](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/live/test_vehicle.py:123) snapshots filenames, then `_read()` retries the same vanished name. The vehicle creates random temporary files and renames them away ([console.py:446](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/docs/deep_research/vehicle/tools/console.py:446)); it also permanently prunes telemetry ([console.py:4618](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/docs/deep_research/vehicle/tools/console.py:4618)). Neither filename returns for those retries. Refresh enumeration on disappearance and parse the already-read text, while retaining mandatory `pending.json` and failures for persistently unreadable/malformed published files.

2. **I2 remains partly fixed: the command need not actually be replayed.** After choosing an early tick, [live/test_vehicle.py:199](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/live/test_vehicle.py:199) allows a 30-second result wait, frame reads and Docker inspection before killing. A checkpoint can include the command meanwhile. Later empty ticks can then satisfy `replayed > 0`, while its existing result satisfies `len(results) == 1` ([line 238](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/live/test_vehicle.py:238)). Assert that the command’s recorded cycle lies within the actual checkpoint-to-recovery interval, accounting for the receipt’s pre-increment tick convention. Tightening the kill margin helps but does not establish this.

3. **New inaccurate exit-3 case.** [README.md:287](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/README.md:287) lists a root record “whose record disagrees with the checkpoint.” Ordinary disagreement is repaired; a readable record naming a **different world** refuses ([console.py:2713](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/docs/deep_research/vehicle/tools/console.py:2713)). Narrow the wording accordingly. This is Important under the project’s rule for misleading operator guidance.

**Minor:** [README.md:289](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/README.md:289) groups recovered-checkpoint failure with stopping “mid-mission.” That checkpoint failure refuses startup before this boot claims anything ([console.py:5510](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/docs/deep_research/vehicle/tools/console.py:5510)); separate it from runtime comparison failure.

The other findings are fixed correctly:

- **I1:** Permissions/disk checks now precede abandoning a damaged world ([README:250](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/README.md:250)).
- **M4–M6:** No-claim/no-cycle replaces “writes nothing”; replay bounds acknowledge fallback/cadence failure; the banner is correctly described as logged ([README:231](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/README.md:231), [266](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/README.md:266)).
- **I2/I3 improvements:** Every window’s sequence is checked; pending JSON must parse; identity checks repeat after resume. The unknown verb produces a legitimate refusal result, and marker filename counting is sound once replay coverage is established.
- **M7:** Advancement before stopping and inspecting the captured container address the dead-vehicle concern; `exited false` correctly means exited and not OOM-killed ([test:250](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/live/test_vehicle.py:250)).
- **Opus:** Distinctive seed/all-file text coverage, fallback regex, nonexhaustive exit list, tighter margin, stale smoke descriptions/count, two-stack documentation, #39, and vehicle-before-fleet guidance are present. No concrete seed collision found; omitting scenario-name text scanning is appropriate.

Verified the fixed index/tree, supplied diff hash, and vehicle SHA. Source-only review against `console.py`/`checkpoint.py` at `f443996`; no tests, builds, containers, changes, or `.env` reads.

