# #23 design review r2 — Codex reviewer of record

Received 2026-10-12T06:00:49.840Z; saved verbatim (harness indent removed).

---

**Request changes (issue #23 design, r2).** The hash matches `c0fcfe06…` and source remains `7a87eb8`. Most r1 findings are addressed, but the write-ahead and timing rules cannot both be implemented as written.

Remaining findings, by severity:

- **P1 — Final cycle cost cannot be recorded in advance.** [DESIGN:64](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:64) requires completed `cycle_us = end − start` on every row, while [DESIGN:110](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:110) fsyncs row 1 **before** steps 2…k. Even quiet cycles record before publication finishes. The append path chains rows before writing them (`console.py:3485–3504`). Record cost in a subsequent completion event and define incomplete-cycle statistics; a crashed prefix cannot supply its eventual cost. Tests 4 and 9 need those semantics.

- **P2 — The refusal path would append an already-durable row again.** [DESIGN:42](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:42) says to append rows 1…j−1 after refusal, but command-bearing cycles already fsynced row 1. Specify **only the unwritten suffix**, with no append for `j=2`. Repeating row 1 fails the reader's tick-order check (`console.py:1765–1771`). Also specify preservation and reporting of the durable prefix if the suffix append fails; the current error message reads `executive.tick` (`:5779–5784`).

- **P2 — The deferral promise needs a resume exception.** [DESIGN:47](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:47) promises settlement at `a+k`. Accept at tick 0 with `k=5`, crash after tick 2, then resume with unchanged `k`: subsequent starts are 2 and 7, so `_settle` executes at **7**, not the advertised 5 (`console.py:3626–3628`). Preserve the due tick, but promise the first cycle boundary **at or after** it across resumes. Add an unaligned-resume test; the planned `k=1` case hides this.

- **P2 — Static/checkpoint separation is impossible for permitted inputs.** [DESIGN:54](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:54) promises their costs never share a cycle, while `N=k` is permitted (`:83`) and checkpoints every cycle. First-cycle and repair rewrites can also overlap checkpoints. State exceptions or constrain inputs, and cover the boundary cases.

- **P3 — Tighten record and comparison invariants.** [DESIGN:105](/home/john/space_chassis/.scratch/wp08-23/DESIGN.md:105) should explicitly require subsequent rows to **repeat the global receipt counter**; replay requires it on every row (`console.py:2419–2421`). Test 14 (`DESIGN:173–175`) must exclude row chains and checkpoint byte offsets: changing timing changes chained bytes (`console.py:1177–1185`) and potentially their encoded lengths.

**r1 confirmation status:**

| R1 finding | R2 assessment |
|---|---|
| Receipt protocol (P1) | **Resolved in principle:** row-1 state, per-cycle accumulation, chained header inputs and checkpoint segment mirroring address it (`DESIGN:101–117`); the new write-ahead conflicts remain above. |
| Frame gap (P2) | **Resolved for the partial-prefix case** (`:120–122`). Downtime affects wall time, not the tick-gap formula. |
| Crashed summary and manifest (P2) | **Partially resolved:** metadata, percentiles and manifest location are explicit (`:72–75`); completed-cost reconstruction remains blocked (the P1 above). |
| `k` bound and ADR J amendment (P2) | **Resolved** (`:28–30`, `:58–60`). |
| Test preservation and injected clock (P2) | **Addressed** (`:142–150`); correct test 14 as above. SIGINT assertions must now reflect graceful completion. |
| Probe timing (P2) | **Resolved:** cadence and observation deadline are separated (`:213–214`). |
| Documentation (P3) | **Resolved:** omitted living documents are listed (`:210–211`). |

**New mechanisms:** the first-step dwell rule matches live/replay bookkeeping (`console.py:2418`, `:4109–4111`). Rotation advances correctly within an unaligned segment. The backstop and signal handler are buildable by routing boundary stops through common clean-end handling, then returning **3 for backstop**; existing early exception returns bypass that handling (`:5779–5798`). Neither John's 30-second backstop nor the 3,000-slot choice introduces a static blocker. Row-1 invariant, per-cycle reader accumulation and RECORD_FORMAT v3 (m, k, N in chained header, mirrored in checkpoint segments) are buildable subject to the P1/P2 items above.

No files changed; no tests, collection, linters or repository tools run.
