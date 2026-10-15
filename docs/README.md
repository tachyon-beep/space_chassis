# docs/ — how Space Aurora works

The project's documents, for both build streams. Status, coordination and decision records are in
`../governance/`; the code is in `../vehicle/` and `../aurora/`.

| document | what it is | owner |
|---|---|---|
| `design.md` | Why the world is shaped the way it is: the rationale behind every rule in `aurora/` and the vehicle boundary (§8) | chassis line |
| `diode-contract.md` | **The window's contract**: the one interface between the vehicle and the container. The vehicle implements it; `aurora/contract/diode_probe.py` probes it | vehicle line; a change needs the chassis to adopt it |
| `brief-claims.md` | Every claim the agents' brief and prompts make, each sourced to the test that holds it (tests named relative to `aurora/`) | chassis line |
| `superpowers/specs/` | Designs; `2026-10-09-aurora-port-design.md` is the world as it now is | chassis line |
| `superpowers/plans/`, `superpowers/ledgers/` | The aurora-port plans and the ledgers of how each was executed | chassis line |
| `plans/` | Programme plans, including `2026-10-15-three-stream-restructure.md` (the repository's layout and the worktree convention) | the line that wrote each |
| `deep_research/` | **The frozen corpus** the vehicle was built from; `integration/corpus-review.md` is its map. Cite it, never edit it | vehicle line |

The vehicle's own working notes (`../vehicle/docs/`: completion, evidence, release, decisions) are
the vehicle line's and stay in `vehicle/`, which its rule keeps self-contained; moving them is that
line's call.
