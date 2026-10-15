# #39 tier 1 — adoption package (formal)

As of **2026-10-11**, vehicle `tachyon-beep/space_vehicle` `main` @ `f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f`
(PR #43; its tree equals the tested head `7ac979156bc164448e9e78df7b39253c619fefaa`). **Verify against the
code before trusting any line here.**

From the vehicle line (Space Vehicle, session `session_01GRfs7dVMu4v5airK6q3w9C`), **formal**:
- the candidate passed Codex review (approve);
- the owner gate passed on both lanes (542 passed, 0 skipped);
- hosted CI is green;
- it is merged.

John approved tier 1 on 2026-10-11 (`../decisions.md`). The vehicle leads `docs/diode-contract.md`; the
chassis adopts it, and owns its brief, its fixture and the probe. The brief text is John's to approve.
Merge SHA, pins and evidence: filigree `space_chassis-93010ff54e`, comment 42.

**Pins at `f75420c`:**
- referee tests: 542 collected (528 test functions);
- `report.refuse(` sites: 882;
- `check_vehicle`: COMPOSES with 273 declared debts; `--strict` exits 2.

## `docs/diode-contract.md` §2.2

**Replace** the "Intake is destructive and atomic" bullet (lines 67–70) with:

> - **Intake is destructive and atomic.** Each cycle the vehicle reads the file. If it holds
>   something to claim, the vehicle rewrites it with `commands` emptied and `variables` preserved,
>   through a temporary file and a rename. "Something to claim" means commands, a file that is not
>   a console, or a console with no `variables` while the vehicle holds a map. A command therefore
>   takes effect **at most once**, even if the vehicle dies mid-cycle: the batch was already claimed.
>   A file whose `commands` is `[]` and which already shows the `variables` is left as it is, and its
>   `variables` are adopted.

**Replace** "A batch written while a cycle is in progress is not claimed by that cycle. It runs on
the next one." (lines 76–77) with:

> - A batch is claimed at the window's next read. **Known residual (vehicle #39):** a file replaced
>   between the vehicle's read and its rewrite of an earlier one can be lost without a result. A
>   take that cannot lose it is planned. Until it lands, write a new batch only after the previous
>   one has been claimed.

## Brief and its sourcing (the chassis's)

- **`brief/PROTOCOL.md:51–54`:** "Each pass, the far side reads the file and rewrites it…" needs the
  same two changes in the brief's voice:
  - it rewrites only when there is something to claim;
  - a batch written while the previous one is still being claimed can be lost.

  "You can tell a submitted batch from a pending one by watching `commands` return to empty" stays
  true.
- **`docs/brief-claims.md`:** the sourcing of that line points at the new §2.2 text.

## Fixture parity (the chassis's)

**`contract/fake_diode.py:207–224`** rewrites on every pass. For the fixture to model the same
contract, use the **same quiet rule**: skip the rewrite when `commands` is exactly `[]` and either
`variables` is an object (adopt it), or there is no `variables` key and no map is held. Decide it
from types alone, before adopting, so that no JSON value can raise.

## What does not change

- The probe and its assertions.
- The console's shape.
- The refusal-once rule for a file that is not a console.
- The durability order (#21).

## Next (approved direction, separate package)

Option B is a take that cannot lose a batch: rename the console aside, then republish only if
nothing is there. John has accepted that the console may be briefly absent while a claim takes it,
and agents must detect and handle such tearing. That package will bring its own contract sentence.
