# #39 claim race — decision memo after three design reviews

As of **2026-10-11**, vehicle `tachyon-beep/space_vehicle` `main` @ `f44399645fb2633e695a5d758cb5a41f43fb848c`.
Written by the vehicle line, Space Vehicle [610587], session `session_01GRfs7dVMu4v5airK6q3w9C`, for
Emmy and John. **Verify against the code before trusting any line here.** It holds no code, no commit
and no test; it used no test slot.

## Why a memo and not a fourth design

Emmy's instruction for this slice (2026-10-10) set the requirements: preserve the contract semantics,
including same-cycle variable publication as the unchanged probe observes it; no one-cycle lag; and
"if they cannot preserve them, return the concrete tradeoff for a decision before implementation".
After three independent design reviews, the exchange-based designs have not met the crash-recovery
part of that bar. This memo is that tradeoff.

| design | sha256 | review (Codex `gpt-6-astra` high, read-only) | verbatim text |
|---|---|---|---|
| v1 | `d1baec7030ca…` | REQUEST CHANGES | `.scratch/wp01-handoff/diag-contract-probe/reviews/round1-v1.md` (`f96b7990…`) |
| v2 | `dff1aafb61bcc984…6ceb` | REQUEST CHANGES (core, R, E-a, E-c) | `…/reviews/round2-v2.md` (`85ff9c20…`) |
| v3 | `5a4e5f2fda350b4d…242b` | REQUEST CHANGES (core, R, E-a, E-c) | `…/reviews/round3-v3.md` (`70548905…`) |

The designs are in the same directory (`39-design.md`, `-v2.md`, `-v3.md`). Per-round notes are in
`CHECKPOINT.md`, checkpoints 4, 6 and 8.

## What three rounds established (decision-ready, no further review needed for these)

- **Quiet cycles write nothing.** The payload is quiet only when it is an object, `commands` is exactly
  `[]`, and `variables` is type-exactly equal to the window's map (canonical JSON). Codex accepted this
  in rounds 2 and 3. **All three erasures the chassis captured were quiet-cycle rewrites**
  (`evidence-1.tar.gz`, sha256 `6e3387cd…a7e50`).
- **The exchange mechanism.** `renameat2(RENAME_EXCHANGE)` takes exactly the file present at that
  instant, and erases nothing. Codex also accepted claim-at-exchange in principle for the E families.
- **The capability check and decision 1's two branches**, written out in v3 §8. Codex judged the split
  between unsupported and interference broadly right. The 1A platform requirement is now disclosed:
  the vehicle declares no platform today (`pyproject.toml`: `requires-python = ">=3.12"`), so 1A would
  newly require Linux, `renameat2` and an exchange-capable filesystem. 1B qualifies the whole
  read-to-replace interval.

## What does not close, and why

ADR 0002 G keeps `variables` out of the checkpoint, "preserved in [the agent's] own `console.json`".
So after a crash, the only copy of a window's map is a file the agent can write. An exchange-based
claim that races an agent's write briefly leaves the vehicle's own console carrying a map that is not
the current one. Recovering the right map after a SIGKILL in that instant requires telling the
vehicle's file apart from the agent's file, using evidence the agent cannot forge and that survives
the recovery. Each round put that evidence somewhere it failed:
- v1: in memory only;
- v2: link pins in the agent-writable window directory;
- v3: private metadata that described a mutable file, and was then discarded before recovery was
  durable.

**This is an evidence problem created by where the map lives, not a coding problem.** A fourth
design along the same lines is not recommended.

## The tradeoff: three tiers for John

### Tier 1 — quiet-skip only (landable now; decision 2 becomes moot)

- **What.** Skip the rewrite on quiet cycles. Non-quiet claims stay exactly as today (read, then
  replace). No exchange, no new state, no restart change.
- **Restart.** Unchanged. A skipped write leaves the console as the agent wrote it, and today's resume
  adopts that console's `variables` (`console.py:5014–5023`). A non-quiet claim still writes the map
  it read, so the console and the in-memory map agree, as today.
- **Fixes.** Every observed erasure: the chassis's lost-result probe failures were all quiet-cycle
  rewrites.
- **Residual (unchanged from today on non-quiet cycles).** A second agent write that lands inside a
  **non-quiet** claim's read-to-rewrite interval (about 0.2 ms, which scheduling can lengthen) is
  still erased without a result. **It can be reached by the unchanged probe.** Codex's round-2
  schedule does it: the probe counts a late result, returns early, and its next submission lands
  inside the previous batch's claim. That needs a much narrower coincidence than today's
  every-idle-cycle exposure, but the rate is not zero and has not been measured.
- **Contract.** One honest qualifier on §2.2, the vehicle's to write and the chassis's to adopt:
  "Each cycle the vehicle reads the file and, if it holds anything to claim, rewrites it … A batch
  replaced while the vehicle is claiming an earlier one may be lost without a result."
- **Decision 1:** not needed (no exchange). **Decision 2:** moot.
- **Chassis:** `contract/fake_diode.py` can take the same quiet-skip. The probe stays unchanged.

### Tier 2 — exchange, with the crash residual accepted in the contract

- **What.** v3's decision-independent core (quiet-skip, claim by exchange, held-descriptor identity)
  with **no crash-recovery machinery**. Resume stays as today: the console's `variables` win.
- **Residual, disclosed and accepted, not designed around.** A vehicle crash in the instant after a
  raced claim may revert that window's map to an earlier one until the agent rewrites it. This is
  Codex round 1's P1, carried as a named residual.
- **Several round-3 P1s describe behaviour today's code already has.** For example, a directory
  `fsync` failure after the rename loses the claimed batch without a result (`write_text_atomic`,
  `console.py:463–468`; the exception propagates out of `claim()` to the window's recorded failure,
  `:3103–3105`). Tier 2 changes none of that, and says so.
- **Still needs:** decision 1, decision 2 (R, E-a or E-c, as written in v3 §9, with their contract
  sentences), a fourth review of the reduced design, and then the gates.

### Tier 3 — the structural fix: amend ADR 0002 G (a direction, not a design)

- **What.** The committed map becomes authoritative in vehicle-private state, so the console is
  never the map's source of truth at a resume. This is the only direction in which the evidence
  problem goes away.
- **Cost.** It reverses a recorded maintainer decision (ADR 0002 G, "answer as recommended"). It needs
  its own design and review cycle, which must still say how the first cycle after a restart avoids
  adopting the vehicle's own stale console, and probably a record or checkpoint change only just
  landed by #21.
- **Combinable:** tier 1 now, then tier 3 later as its own package.

## Decisions requested

1. **Which tier** (John). Tiers 1 and 3 can be combined. Tier 2 also needs decisions 1 and 2.
2. **Decisions 1 and 2 stand as written** (v3 §8–§9) and are pending. Neither is selected here.
3. **A gate exception** for the chassis's whole-suite gate stays John's alone. None is assumed. Tier 1
   is the shortest path to removing the observed flake without one.

## Next steps once a tier is chosen

- **Code:** a vehicle worktree on a branch from `f443996`.
- **Freeze:** the diff and tree are frozen and hashed.
- **Review:** an independent Codex review of the **chosen** tier's frozen diff. No further design
  rounds are run on tiers not chosen.
- **Gates:** the gates in the shared slot (one bounded selection at a time, at most two workers in
  total across the lines, `nice -n 19`), claimed in this folder's `open.md` and never while the
  chassis holds it.
- **Then:** the chassis's q1–q3 evidence re-run on the candidate, under its cap; push, PR, CI and
  merge only under the authority then given.

`1caab23` (`codex/diag-ingress-trace`) remains unqualified diagnostic evidence, not a candidate.
