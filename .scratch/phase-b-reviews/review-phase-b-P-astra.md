**Land.** All candidate-3 findings are correctly addressed; no introduced defect or weakened acceptance assertion found in P’s delta.

Evidence below is from chassis tree `af671d0` and vehicle commit `f443996`.

- **Critical:** None.
- **Important — replay race fixed:** `live/test_vehicle.py:316–327` checks `replayed == recovered - checkpoint` before retrying when `checkpoint > command_tick`. This correctly permits the crossed-checkpoint case with zero replay to retry. Acceptance still requires `checkpoint <= command_tick < recovered`, positive replay, and exactly one result (`328–331`). Exhausting the attempts still fails (`334`). This matches the vehicle’s replay calculation and banner (`tools/console.py:4702–4704,5525–5528`).
- **Minor — README fixed:** `README.md:285–290` now qualifies repair as occurring beside a checkpoint, from the recovered world, with refusal if rewriting fails. The different-world refusal remains explicit. This matches `tools/console.py:4916–4922,5000–5007`; without a checkpoint, an unreadable record still refuses (`5552–5556`).
- **Minor — malformed-then-vanished comment fixed:** `live/test_vehicle.py:159–166` explains the existing retry/removal behavior without changing it. The text seed check precedes JSON parsing (`155`); disappearance triggers relisting (`145–149`); `pending.json` must still be read whole (`174`). Vehicle JSON publication uses completed temporary files renamed into place (`tools/console.py:446–463,504–505`).
- **Minor — diagnostics fixed:** `live/test_vehicle.py:150–152` retains failure on the fifth unsuccessful read and explicitly names the path and error. The added assertions at `268` and `305` diagnose missing/unreadable executive records before indexing.

The delta’s SHA-256 matches the supplied value and contains only README and live-test changes; no resource-control changes. Static Git-object review only: no tests, builds, containers, edits, Git-state changes, or `.env` reads.