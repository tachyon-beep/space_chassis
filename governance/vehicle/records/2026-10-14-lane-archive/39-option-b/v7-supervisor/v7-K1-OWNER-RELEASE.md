# Owner release receipt — SPACE-20261011-B-V7-K1

Owner: Space Vehicle, `session_01GRfs7dVMu4v5airK6q3w9C` / local session `a728e992-9471-46ab-9efe-ce550d7ece5f`.
Written 2026-10-11T12:55:24Z.

**The one authorized invocation ran and ended.**
- **Unit:** `space-vehicle-b-suite-k1.service`, InvocationID `0eb412ca87ef44aaad5fc21f4c8e8885`.
- **Ran:** launched 2026-10-11T12:48:39.46Z; summary written 12:54:31Z; the unit inactive and unloaded by 12:54:38Z,
  `Result=success`.
- **Not run:** no retry, no pytest, no S1, nothing else.

**Results.** 20 of 20 controls passed, serially, with K03 last. K03's exit 4 was the expected result.

**The suite's own final proof** (`controls-summary.json`): no control units left, no decoy units left, decoy processes
ended, within the recovery deadline: `proven_clean: true`.

**The owner's independent read-only check** (`v7-K1-postrun.txt`, 12:55:00Z):
- the suite unit is not-found;
- no user unit named Space, in any state;
- no Space cgroup under `app.slice`;
- no Space-named container;
- no own process carries any of the 21 run tokens;
- the 11 unreadable own processes all predate the launch.

**Evidence:** `v7/controls-evidence/`, 122 files; manifest `v7-K1-evidence.SHA256SUMS`.

**The owner releases `SPACE-20261011-B-V7-K1`.** The slot becomes free only after **Governance's independent cleanup
verification**, per §33. K03's exit 4 does not release it by itself.
