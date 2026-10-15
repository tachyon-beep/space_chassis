# AGENTS.md — Space Aurora

One repository, three streams. Read the stream's own `AGENTS.md` before touching anything in it.

| folder | stream | read first |
|---|---|---|
| `vehicle/` | the vehicle sim | `vehicle/AGENTS.md` |
| `aurora/` | the Aurora container world | `aurora/AGENTS.md` |
| `governance/` | deconfliction and reporting between agents: ownership, coordination, status, decisions | `governance/README.md` |

`docs/` is how the project works (index: `docs/README.md`): the design, the window's contract, specs,
plans, ledgers and the frozen corpus `docs/deep_research/` (cite it; never edit it). Write plans and
design documents there; report status and coordinate in `governance/`.

## How to work

- **One worktree per piece of work**: `make worktree STREAM=<vehicle|aurora|governance> TOPIC=<name>`
  creates `.claude/worktrees/<stream>-<name>` on branch `<stream>/<name>`. Never work in another
  agent's worktree or in the main checkout's working tree while someone else is.
- **Stay in your stream.** A branch changes one stream's folder. A contract change is the one
  cross-stream change and is named as such.
- **Run the one suite before you commit**: `make test` (both streams) and `make lint`.
- **Governance first.** `governance/README.md` says who owns what, what is decided and what is open.
  Report your status and coordinate there. Nothing in `governance/` may reach an image.
