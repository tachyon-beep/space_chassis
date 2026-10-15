# #39 option B, revision 4

Vehicle line, Space Vehicle [610587], 2026-10-11. **Design, no code.** It revises `39-design-B3.md`
(sha256 `ce17a97d…`).

Codex reviewed B3 in round 3 (`reviews/B-round3.md`) and found one P1. Every other round-2 fix was
confirmed at design level: the single `EEXIST` re-check, no answer until the take is durable, and
quarantine before block. Everything in B, B2 and B3 not restated here stands.

## The P1, and the change

**Finding.** B3 identified "the boot that just ended" by the record's newest segment. That is not
established early enough:
- a boot's segment header is written only with its first cycle's record (`console.py:3444`);
- a resume's `resumed` startup event does not establish a segment (`:1911–1934`).

So in Codex's ordering a take is judged against the wrong boot:
1. Boot 2 adopts console map B.
2. The console then loses its map.
3. A kill arrives before boot 2 retires the take `L` of boot 1, and before boot 2's first record.
4. Boot 3 still finds boot 1 newest, and resurrects A from `L`.

A kill during a boot's first claim has the opposite effect: valid evidence is misjudged as old.

**Change: a boot marker, written durably before any evidence is read.**
- **Where:** a one-field file in the **state directory** (vehicle-private; agents cannot reach it),
  `.boot.json`, holding `{"boot_id": <the executive's boot_id>}`.
- **When:** at every start, fresh or resume, in this order, **before** resume reads any console or
  take and before any claim:
  1. Read `.boot.json` and keep its `boot_id` as `prev` (absent or unreadable → `prev = None`).
  2. Write `.boot.json` with this boot's `boot_id` (`write_json_atomic`, file and state-directory
     `fsync`).
  3. Only then proceed: resume map recovery, then cycles.
- **Failure:** if step 2 fails, the start **refuses by name with exit 3**, through the existing
  start-path boundary. A vehicle that cannot write its own state directory cannot keep its record
  either.
- **Evidence rule** (replaces B3 §1's use of the record): a take is map evidence only if its name's
  `boot_id == prev`. Every other take is retired (removed, or quarantined).
- **Format impact:** the record and checkpoint formats are unchanged. The state directory gains one
  vehicle-private file, stated in ADR 0002 H (where the checkpoint lives) as a consequence note.

## Codex's ordering, walked

1. Boot 1 leaves take `L` (map A), with `.boot.json` = boot 1.
2. Boot 2 starts: `prev` = boot 1, then `.boot.json` = boot 2 durably, then resume. It adopts
   console map B, and is killed before retiring `L`.
3. Boot 3: `prev` = boot 2. `L` names boot 1, so it is **not evidence** and is retired. The console
   has no map, so the map is **unknown** (ADR 0002 (xxxv)), never A. ✓

**A kill during boot k's first claim.** The take names boot k, and `.boot.json` was already boot k,
so the next boot has `prev` = k and the take **is** evidence. ✓

**A kill between steps 1 and 2.** `.boot.json` still names the previous boot, so the next start sees
the same `prev`. Nothing was read or claimed in between. ✓

**Boot 2 killed after step 2 but before adopting anything.** Boot 3 has `prev` = boot 2, so boot 1's
`L` is not evidence, and the map is the console's or unknown.
- This is the unknown-map outcome after a **second** crash, which ADR 0002 already accepts. #42
  tracks why an unknown map matters.
- Re-minting `L` under boot 2's name was considered and rejected: it would resurrect A in the
  ordering above.

## Fresh start (no resume)

A fresh world retires every take it finds before its first claim: there is no map to recover in a
new world. Steps 1–2 still run, so that the next resume has a `prev`.

## Tests added

- **Codex's round-3 ordering** across three boots: the map comes back unknown, never A.
- **A kill during a boot's first claim:** the next resume uses the take's map.
- **A kill between reading and writing `.boot.json`.**
- **`.boot.json` unwritable:** exit 3, by name.
- **A fresh start over a leftover take:** the take is retired.
