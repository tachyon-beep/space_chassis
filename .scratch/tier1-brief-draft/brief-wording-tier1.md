# #39 tier 1: the brief wording, for John's approval (draft)

Chassis, session `session_019mkPNN5J3Atit9tUA6zrNY`, 2026-10-11, at Emmy's request. **Draft only:** no file in
the tree has changed. Nothing is adopted, the vehicle pin is unchanged, and no test has run.

Basis:
- the vehicle's formal package `governance/vehicle/records/2026-10-11-39-tier1-adoption-package.md`
  (sha256 `483d47de…`);
- the code it describes, read at vehicle `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f` (PR #43): `tools/console.py`
  `Window` claim (`quiet`) and its docstring, and the three new tests.

The brief, the claims table, the contract and the fixture are byte-identical in the main checkout and in
the adoption worktree (R2c `148a31c4`).

## 1. `brief/PROTOCOL.md` lines 51–54, replaced

Current:

```
- **Intake is destructive and atomic.** Each pass, the far side reads the file
  and rewrites it with `commands` emptied and `variables` kept. A command
  therefore runs *at most once*. You can tell a submitted batch from a pending
  one by watching `commands` return to empty.
```

Proposed:

```
- **Intake is destructive and atomic.** Each pass, the far side reads the file.
  If it holds something to claim, the far side rewrites it whole, with
  `commands` emptied and `variables` kept, so a command runs *at most once*.
  If it holds nothing to claim, the far side leaves it untouched: nothing is
  written, and its `variables` are taken as they stand. Nothing to claim means
  `commands` is exactly `[]` and the file carries its `variables` map, or
  carries no `variables` while the far side holds none. Anything else is claimed: a batch, a file
  that is not a console, or one without `variables` when the far side holds
  them. You can tell a submitted batch from a pending one by watching
  `commands` return to empty.
```

## 2. `brief/PROTOCOL.md` lines 59–60, replaced (the conflicting next-pass promise)

Current:

```
- A batch you write while a pass is in progress is not consumed by that pass.
  It runs on the next one.
```

Proposed:

```
- A batch is claimed at the far side's next read. That holds while the file
  you replace has nothing to claim, because then no pass rewrites it. While a
  pass is rewriting the file to claim what was there, a file you put in place
  can be replaced unread. Its batch then runs nothing, and leaves no result
  file and no record. So replace the file only when the one already there has
  nothing to claim: after your previous batch has shown `commands` empty.
```

No other line of `brief/` changes:
- Lines 62–64 (write the file whole; a half-written read is refused) stay true.
- Line 84's "Rewritten every pass" is about `state.json`, `HELP.md` and `README.md`, which the change does
  not touch.
- `WORLD.md` and the prompts make no claim about the console's rewrite.

## 3. `docs/brief-claims.md`: a new row

The package says the claims table's sourcing "points at the new §2.2 text". **The table has no row for the
window's intake today**, so this is a new row, not a re-pointing. It is a change to the text John approved
on 2026-10-09.

Proposed row (after "A reply that cannot be recorded is not given"):

```
| The window claims a console that holds something to claim by rewriting it with `commands` emptied and `variables` kept, so a command runs at most once; a console with nothing to claim is left untouched and its `variables` taken; a batch is claimed at the next read, and a file put in place while an earlier claim is being rewritten can be lost with no result | `docs/diode-contract.md` §2.2 (adopted from vehicle `f75420c`, PR #43); vehicle `tools/console.py` `Window` claim (`quiet`, and its docstring's residual); vehicle `tests/test_vehicle_config.py::test_what_counts_as_nothing_to_claim_is_decided_by_shape_alone_and_the_console_always_shows_the_map` and `::test_a_console_with_nothing_to_claim_is_never_rewritten_so_a_batch_put_in_place_during_its_read_is_not_erased`; fixture `contract/fake_diode.py` `AgentSide.consume` (the same rule, landed in the adoption increment; its test goes here) |
```

**The loss clause is sourced in text, not in a test.** Its source is the contract's residual and the vehicle
docstring. No test shows a batch being lost, and the row does not claim one. A fixture test for the quiet
rule does not exist yet. It belongs in the adoption increment, and its name goes into this row when it
exists.

## 4. What the brief says changed, and where each claim comes from

| claim | before | tier 1 | source |
|---|---|---|---|
| the file is rewritten | every pass | only when it holds something to claim | contract §2.2 bullet 1 (package); `console.py` `quiet` |
| nothing to claim | (no such case) | `commands` exactly `[]`, and the file's own `variables` object, or no `variables` while the far side holds no map | package §2.2; `quiet = isinstance(commands, list) and not commands and (isinstance(variables, dict) or ("variables" not in payload and not self.variables_known))` |
| a quiet file's `variables` | kept by the rewrite | adopted without a write | package §2.2 "its `variables` are adopted"; `console.py` adopts before `if quiet: return []` |
| at most once | yes | yes, unchanged | contract §2.2; claim before act unchanged |
| a batch written during a pass runs on the next | promised outright | holds only while no rewrite is in progress; a file put in place during a claiming rewrite can be lost | package §2.2 bullet 2 (the known residual); `console.py` docstring "Residual" |
| how to avoid the loss | (not needed) | replace the file only when the one there has nothing to claim | package §2.2 bullet 2 "write a new batch only after the previous one has been claimed" |

**The claim-loss risk that remains at tier 1, exactly.**
- *When it happens.* Every pass that still rewrites the console carries it. That is a pass that reads one of:
  - a batch (`commands` not empty);
  - a file that is not a console (a broken or half-written file, a non-object, or no `commands` list);
  - a console without a `variables` key while the far side holds a map.
- *What is lost.* The rewrite is a read, then a rename over the path, and no rename can check that the file
  it replaces is the file it read. So a file the agent puts in place between that pass's read and its
  rewrite is replaced unread. It makes no result file and no record. This is true whether the agent
  renamed its file in or wrote it in place.
- *What is not at risk.* A quiet console, which is never rewritten. Every loss the chassis diagnostic traced
  was one of these quiet rewrites (three of three).
- *What is not claimed anywhere.* That the remaining window has never lost a batch, or any measured loss rate.

**Option B is not described.** The brief states the world as it is at `f75420c`. A take that cannot lose a
batch (rename aside, republish only if absent) is the vehicle's next package:
- it is not implemented on `main`, tested, adopted or qualified;
- it will bring its own contract sentence and its own brief change, including a console that can briefly
  be absent.

The contract's "a take that cannot lose it is planned" is deliberately not carried into the brief.

## 5. Dependencies: what this text needs before it may land

1. **The vehicle pin moves to `f75420c` in the same increment, or earlier.** At `f443996` the vehicle
   rewrites every pass, so "leaves it untouched" would be false.
2. **The contract's §2.2 is adopted with it, in the vehicle's wording.** The vehicle leads that wording:
   - bullet 1 replaces lines 67–70;
   - bullet 2 replaces lines 76–77.

   The brief's claims are sourced there.
3. **`contract/fake_diode.py` gets the same quiet rule, with a test, in the same increment.**
   `PROTOCOL.md:32` says "The protocol below is what any window accepts". The fixture is the window in the
   smoke stack and the contract probe, and `AgentSide.consume` (lines 198–223) still rewrites on every
   pass. Without the rule, the new brief would be false for the fixture.
4. **The probe and `diode-contract.md` §9 item 1 need no change.** "A submitted batch is claimed, and the
   console is left with `variables` preserved and `commands` empty" stays true.
5. **A question for the vehicle, not a change.** §2.1 says per-agent ingress buys "reliable transport". With
   the residual stated in §2.2, the vehicle may want to qualify that phrase. The wording is theirs, and
   adopting tier 1 does not depend on it.

6. **Driver identity, if adoption comes before the build and live gate.** `f75420c` adds 141 lines to
   `tests/test_vehicle_config.py`. The accepted drivers bind that file to `3b917de3…` and the vehicle to
   `f443996`. Moving the pin would therefore make them refuse until they are rebound and re-reviewed.

This is a separate increment from P and R2c. Their trees and the vehicle pin in their evidence (`f443996`)
are untouched.
