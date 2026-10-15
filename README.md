# Space Aurora

One program building one product: a fleet of self-modifying agents, and the spacecraft they fly.
One repository, two build streams plus governance.

| stream | folder | what it builds | start at |
|---|---|---|---|
| **vehicle sim** | `vehicle/` | The mission simulator: one spacecraft behind per-agent windows. Configuration, reference plant, console, linter and referee. | `vehicle/AGENTS.md`, `vehicle/README.md` |
| **Aurora container** | `aurora/` | The world the fleet lives in: each agent's harness, the recorder, the pump, the operator services, the image, the compose topology and the vehicle's deployment. | `aurora/README.md`, `aurora/AGENTS.md` |
| **governance** | `governance/` | Plans, decisions, status and records for both lines. Never reaches an image. | `governance/README.md` |

`docs/` is the border the two build streams share, not a stream: `docs/diode-contract.md` (the
window's contract: the vehicle implements it, the container probes it) and `docs/deep_research/`
(the frozen corpus the vehicle was built from, cited by path, never edited).

## Running it

```sh
make setup         # once: pip install -r requirements-dev.txt (openai, httpx, PyYAML, pytest, ruff)
make test          # the one suite: both streams (python3 -m pytest -q -n 8); no containers
make test-aurora   # the container stream only
make test-vehicle  # the vehicle stream only (its referee and linter)
make lint          # ruff check and format check (via uvx)
```

The stack itself runs from `aurora/` (`cd aurora && docker compose …`); `aurora/README.md` has the
operator's commands.

## Working in parallel: worktrees, not repositories

One clone per host. Each agent works in its own git worktree, on its own branch, inside one stream:

```sh
make worktree STREAM=vehicle TOPIC=clock-seam      # = git worktree add .claude/worktrees/vehicle-clock-seam -b vehicle/clock-seam
cd .claude/worktrees/vehicle-clock-seam
```

- The branch prefix names the stream (`vehicle/…`, `aurora/…`, `governance/…`), and a branch touches
  only its stream's folder. A change to `docs/diode-contract.md` is the one cross-stream change, and
  says so in its title.
- Worktrees share one object store; `.claude/worktrees/` is gitignored. There is no submodule and no
  second clone: adopting a vehicle change is merging its branch.
- The plan behind this layout: `governance/plans/2026-10-15-three-stream-restructure.md`.
