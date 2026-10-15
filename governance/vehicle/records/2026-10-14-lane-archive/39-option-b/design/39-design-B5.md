# #39 option B, revision 5

Vehicle line, Space Vehicle [610587], 2026-10-11. **Design, no code.** It revises `39-design-B4.md`
(sha256 `6102d239…`), which Codex reviewed in round 4 (`reviews/B-round4.md`). That review confirmed
two things:
- the boot marker closes round 3's P1;
- the start-up placement is feasible.

It found one P1 that needs a power loss, and two P2s. B, B2, B3 and B4 stand except where restated
here.

**Termination rule for this design** (proposed, the same as #21's): round 5 reviews only this
revision's changes. A further round is warranted only for a P1 anywhere, or a P2 inside these
changes. Anything else is filed as a residual for the implementation's review. Rationale: rounds 1–4
on B found **no SIGKILL-only replay, double-answer or claim-without-result ordering**. Rounds 2–4 each
closed the previous round's findings and found narrower ones: cross-boot evidence, then power-loss
ordering.

## Changes

| round-4 finding | change |
|---|---|
| **P1:** retiring a take was not durable, so after a power loss a take could reappear and a resume could accept its stale map | **Retirement is durable before anything else touches the map.** Whether the take is removed (`unlink` / `rmtree`) or quarantined (rename to `.dead`), it is followed by an `fsync` of the window directory. **No further claim of that window, and no quiet-cycle adoption of its `variables`, happens until that barrier succeeds.** If the barrier fails, the retirement stays pending. C0 retries it each cycle and records a failure while it is pending; the console is untouched. The same applies to resume's step 4 and to a fresh start's retirement: the window's first cycle waits for the barrier. |
| **P2:** "at every start" is unqualified | The marker is written **only by a start that will serve windows with a state directory**: after the lock, the identity check, the `serves.json` check and the journal checks have passed, and immediately before a resume's window recovery (`console.py:5035`) or a fresh start's first cycle. `--plan`, a start that refuses, and any other non-serving invocation never touch it. **With no state directory** there is no record, so there is no resume and no durable claim: no marker is written, no take is ever evidence, and every take found is retired before the first claim. |
| **P2:** the marker's pathname is not reserved | The start refuses by name, **exit 3, before any write**, when `--journal` names `<state-dir>/.boot.json`, and likewise when any other run input resolves to the marker. `open_journal_dir` (`console.py:939`) gains the check, beside its existing ones. |

## Round 4's ordering, walked

1. Take `L` (map A) is made.
2. The agent's console `U` (map B) exists durably.
3. B4 gets `EEXIST`.
4. B5 removes `L`, then **`fsync`s the directory**. If that fails, retirement is pending, and neither
   a quiet adoption nor a claim can happen.
5. Only after the barrier does a quiet cycle adopt B.

A power loss after the barrier cannot restore `L`. A power loss before it leaves `L` (map A) and `U`
(map B). `U`'s `variables` win at resume, and B was never adopted before the barrier anyway. If `U`
then loses its map through an in-place write, resume falls back to `L`. That is correct here, because
no newer map was ever adopted. ✓

## Tests added

- **Retirement barrier failure** (injected `fsync` failure after the unlink): no claim and no quiet
  adoption until the barrier succeeds, and the failure is recorded each cycle.
- **Round 4's ordering** with the barrier ordering asserted. A simulated power loss is modelled by
  re-creating `L` before the barrier and then resuming.
- **`--plan` and a refused start** leave `.boot.json` unchanged.
- **No state directory:** no marker, and every take is retired before the first claim.
- **`--journal <state-dir>/.boot.json`:** exit 3 by name, with no write.
