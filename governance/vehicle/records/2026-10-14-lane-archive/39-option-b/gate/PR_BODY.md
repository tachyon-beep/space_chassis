## Outcome and linked work

**Work package / child issue:** #39 (claim race), option B. Tier 1 is #43, merged at `f75420c`.

**Concrete trigger and resulting behaviour.** After tier 1, a batch replaced between a **non-quiet**
claim's read and its rewrite was still erased: no result, no record. The claim now **takes** the
console by `rename` and answers what it took. It never writes over a file:
- **Take:** the console is renamed to `.console.json.take.<boot>.<n>`. What was taken is the claim.
- **Durable before answered:** the window directory is `fsync`ed before anything is answered. If that
  fails, nothing runs and the take waits.
- **Put back by `link`:** the emptied console returns only where none is. A console the agent wrote
  meanwhile is left for the next claim.
- **Retire durably:** the take is removed, or moved aside to `.console.json.dead.*`, and the removal
  is made durable before the window claims or adopts anything more. One take per window, ever: a take
  that can be neither removed nor moved aside blocks its window and names itself every cycle.
- **Resume:** the map comes from the console's own `variables`, else from the take of the boot that
  just ended (the new state-directory marker `.boot.json`), else it stays unknown. An older take is
  never evidence.
- **`prepare` and `repair`** create a console only where none is.

**Scope and prerequisites:** `tools/console.py` and `tests/test_vehicle_config.py` (9 new tests), the
README round entry, and ADR 0002 (xlv). **The console can be briefly absent while a claim takes it.** Option B fixes the claim race only: it
adds no exactly-one or next-read delivery guarantee (see the contract package).
John accepted this; agents read an absent console as transient.

## Evidence

- **Source SHA and exact validation commands/results:** `7a87eb82cfef55dcc74248df41720883587ca7af`
  (parent `f75420c`, tree `ccc2782e…`), gated at that exact SHA in a clean detached worktree. This
  local commit was made before the gate under a recorded Governance sequencing exception (§37):
  `CONTRIBUTING.md` asks for the whole suite before committing, which this order does not literally
  meet. Full development gate on both lanes, as four serial allocations (3.12 static, 3.12 pytest,
  3.13 static, 3.13 pytest), in the order:
  1. ruff
  2. check_vehicle
  3. `--strict`
  4. readiness
  5. build-order
  6. measure
  7. pytest `-n 2 --max-worker-restart=0`

  Results: `<filled from the gate evidence>`.
- **Full referee:** `<collected 551 expected> / <passed> / 0 failed / 0 skipped`, per lane.
- **Normal linter and strict/readiness status:** COMPOSES with 273 declared debts; `--strict` exit 2
  (expected while honest debts remain).
- **Applicable acceptance evidence:**
  - a bounded selection of the 25 tests most exposed to the change passed under a reviewed systemd
    supervisor (2 CPUs, 6 GiB, no swap, nice 19), peak 559 MiB;
  - the supervisor's 20 failure-injection controls passed first.
- **Independent reviewer and resolved blocking findings:** Codex (`gpt-6-astra` high), with every
  blocking finding resolved:
  - design: five rounds;
  - implementation: candidates 0 to 3, candidate 3 approved;
  - final package: rounds 1–2 request changes, all fixed; rounds 3–4 approve; committed-head
    revision `<verdict>`;
  - final diff and evidence review: `<verdict>`.

## Decisions and limits

**Provenance / decision records:** John's decisions (2026-10-11): option B; console absence accepted;
a non-adversarial threat model. ADR 0002 (xlv).

**Remaining gates, risks and incomplete behaviour:**
- **In-place writers:** an agent writing into the console, rather than replacing it, can be read
  half-written, or lose its tail.
- **Crash after a take:** that batch's commands are lost (the existing crash rule).
- **Second crash:** one before the console shows a recovered map can leave the map unknown (#42).
- **Power loss:** covered only by the `fsync` order, and not tested.

**Parent reconciliation/pointer impact (handled in a separate chassis commit):** the chassis adopts
this SHA with option B's contract wording, sent as a separate vehicle-owned package. The pins move
to 537 test functions / 551 collected, with `report.refuse(` sites unchanged.

Development green does not imply complete-vehicle or mission acceptance.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01GRfs7dVMu4v5airK6q3w9C
