# #23 implementation review, candidate 2 — record shape

Received 2026-10-12T10:42:59.860Z; saved verbatim (harness indent removed).

---

## Verdict for #23 candidate 2 (record shape): approve

All four points you asked about hold against my replay and anchor reasoning. The only finding is one inaccurate docstring sentence (P3).

This was read only and I ran no tests. `git diff | sha256sum` in the worktree matches the frozen `8cb41f28…f88f1a`.

**1. A header-only segment followed by the next boot's segment replays and verifies.**
- `open_segment` (`console.py:3637-3649`) calls `_append_record([], first_tick=self.tick)`. That writes the chained v3 header, with `m`, `k`, `N` from the boot's resolved clock, and adds the segment entry with the header's chain and the byte offset after the header.
- The next boot takes this segment as its predecessor (`previous`, `previous_chain`) and begins at the same tick. A header-only segment's `last_tick` is its `first_tick`, so `concatenated`'s check that the next segment begins where its predecessor ended holds, and so does its chain check.
- `_verified_lines` already accepts header-only segments. The manifest that follows is an unchained event, so the reader skips it.
- In `replay_record`, the segment yields no rows, and it is still recorded as reached and added to the body's segments with its `m`, `k`, `N`. This is the same path that already serves a boot whose first cycle was torn.
- On a fresh start the genesis checkpoint lists no segments and the header's `previous` is `None`, which the case for a replay with no anchor accepts.

**2. A checkpoint anchored at the header-only segment's end is consistent.**
- `_anchor_line_problem` (`:2172-2180`) explicitly handles an anchor that ends on a header line. It checks that the line's tick (here `first_tick`) equals the snapshot's tick, that the format and `_header_problem` (including `m`, `k`, `N`) pass, and that the chain is the header's own.
- In replay, `anchor_tick == start`, the header's chain equals the anchor's chain, and the end-of-segment `running == anchor["chain"]` check passes.
- A read from that anchor meets only the manifest event (skipped) and then end of file, or the next header in a shared `--journal` file.

**3. `open_segment` does nothing when the segment already has rows.** It is guarded by `self._segment is None`, and every `_append_record` that writes a header sets `self._segment`. It also does nothing without a journal.

**4. Test 13's wrapper is still a pure function** (`tests/test_vehicle_config.py:31880-31892`).
- `drifting` reads only its arguments: `effects`, and `truth` through `level()`, which takes the flat `mode` first and `internal.mode` second, as `plant.state_level` does.
- It changes only a shallow copy of the stepped result plus a new `internal` dict, so it mutates neither the input truth nor the real step's nested objects.
- Both representations move together, so the plant's reading and the dwell's `value_of` (internal map) agree.
- The precondition and the mutation reasoning from candidate 1 are unchanged: reporting after the loop would record `["free_drift"]` and fail both the dwell assertion and live-equals-replay.

**P3 (docstring only): "called before the clean-end checkpoint, so it lists the segment" is not always true.**
- A boot that resumed and ran no cycle already has `last_checkpoint_tick == tick` from the checkpoint it takes before serving, so `main` skips the clean-end checkpoint (`:6711`). Its header-only segment is then written after the newest checkpoint, which does not list it.
- This is still consistent. The anchor is the previous segment's end, and the header-only segment continues it from the same tick with the anchor's chain. Replay adds it to the recovered segments, and the next resume inherits the clock from that header through the "newer" rule (`_resume`, `:5880ff`).
- Suggested rewording: "…so a clean-end checkpoint, when one is taken, lists it."
