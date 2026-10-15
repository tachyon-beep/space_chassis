# Owner release receipt — SPACE-20261011-B-V7-S1-01

Owner: Space Vehicle, `session_01GRfs7dVMu4v5airK6q3w9C` / local session `a728e992-9471-46ab-9efe-ce550d7ece5f`.
Written 2026-10-11T13:17:14Z.

**The one authorized invocation ran and ended.**
- **Outer unit:** `space-vehicle-b-supervisor-s1-1.service`, InvocationID `c121704d83e94f61ba9029f63cf0a11c`.
- **Ran:** launched 2026-10-11T13:15:48.19Z; finished, `Result=success`, `ExecMainStatus=0`, inactive and
  unloaded by 13:16:33Z.
- **Payload unit:** `space-vehicle-b-s1-0a704983bae8.service`, InvocationID `5d2bbdd7b7154a9b967f85fa7e22343a`.
- **Not run:** no retry and no other execution.

**Result.** pytest exited 0: "25 passed in 25.75s".
- **JUnit:** `tests=25 failures=0 errors=0 skipped=0`, 25 unique test cases, identical to the 25 selected node IDs.
- **systemd:** `SERVICE_RESULT=success`, `EXIT_STATUS=0`, `oom_kill` 0, `memory.peak` 586,248,192 bytes (559 MiB).
- **Caps read back:** `cpu.max 200000 100000`, `memory.max 6442450944`, `memory.swap.max 0`.
- **Identity after the run:** HEAD `f75420c`, diff `0a00336f…`, both unchanged.
- **Supervisor:** exit 0; cleanup verified on its first attempt; `RELEASE.txt` present.

**Cleanup, owner's independent read-only check** (`v7-S1-postrun.txt`):
- the outer unit is not-found;
- no user unit named Space, in any state;
- no Space cgroup;
- no Space-named container;
- no process carries the run token;
- no unreadable own process started after the launch;
- the owner's background waiter has ended; no helper or monitor remains.

**Evidence:**
- `v7/evidence-S1/`, manifest `v7/v7-S1-evidence.SHA256SUMS`;
- `v7/s1-supervisor.out`, empty: the supervisor prints nothing on success.

**The owner releases `SPACE-20261011-B-V7-S1-01`.** The slot becomes free only after Governance's
independent verification of units, cgroups, helpers and monitors (§35).
