**Land after fixes.**

**Remaining: Critical — none; Important — one; Minor — none.**

1. **Identity scan: fixed.** [live/test_vehicle.py:145](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/live/test_vehicle.py:145) re-lists vanished names, parses the text already read, and requires the actual window-root `pending.json` to parse successfully. Persistent read/JSON failures still fail. Successful reads consume `todo`; disappearance retries are bounded. `min(todo)`, reappearing names, and malformed JSON that subsequently vanishes introduce no defect in this sampling check. This matches the vehicle’s temporary-file publication and telemetry pruning (`console.py:446–463,4597–4622`).

2. **Replay proof: correct interval, incomplete retry fix.** The remaining **Important** defect is at [live/test_vehicle.py:312](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/live/test_vehicle.py:312): positive replay is asserted **before** the crossed-checkpoint retry at line 315.

   Example: command receipt `T=70`, pre-kill root tick `99`; checkpoint `100` completes during the subsequent inspection/log/kill calls, and the kill lands during the poll sleep. A healthy resume reports `S=N=100`, `replayed=0`. The test fails instead of retrying. The vehicle checkpoints after publication ([console.py:3150](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/docs/deep_research/vehicle/tools/console.py:3150)), then sleeps (`console.py:5424`).

   **Fix:** validate `replayed == recovered - checkpoint`, handle `checkpoint > command_tick`, then require positive replay for the qualifying attempt.

   The underlying `S <= T < N` reasoning is correct: receipts capture pre-increment ticks (`console.py:3532`), cycle rows use the incremented tick (`3121,3363`), checkpoints capture that tick ([checkpoint.py:275](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/docs/deep_research/vehicle/tools/checkpoint.py:275)), and `replayed=N−S` (`console.py:4703`). Cadence 50 comes from `mission.yaml:62` through `console.py:2791–2792`; the smoke override changes polling only. Receipt regex, unknown-verb refusal receipts, per-attempt banner counts, closure bindings, and marker-specific result counting are sound. Skipped attempts’ results cannot inflate a later marker’s count.

3. **README findings: fixed.** [README.md:288](/home/john/space_chassis/.claude/worktrees/vehicle-adoption/README.md:288) matches the different-world refusal versus rewrite classification (`console.py:2709–2722,4725–4738`). Lines 291–293 correctly describe recovered-tick checkpoint failure as startup refusal before claims (`console.py:5510–5519`). The phrases required by `tests/test_doc_claims.py:134–154` remain present. No additional overclaim found within this confirmation scope.

Verified the staged candidate matches `04dff0be…`, both supplied diff hashes match, and reviewed vehicle sources match `f443996…`. Source inspection only: no tests, builds, containers, edits, Git-state changes, or `.env` reads.