# AGENTS.md — Space Aurora

One repository, three streams. Read the stream's own `AGENTS.md` before touching anything in it.

| folder | stream | read first |
|---|---|---|
| `vehicle/` | the vehicle sim | `vehicle/AGENTS.md` |
| `aurora/` | the Aurora container world | `aurora/AGENTS.md` |
| `governance/` | plans, decisions, status, records | `governance/README.md` |

`docs/diode-contract.md` (the window's contract) and `docs/deep_research/` (the frozen corpus) are
the border the two build streams share. Cite them; never edit the corpus.

## How to work

- **One worktree per piece of work**: `make worktree STREAM=<vehicle|aurora|governance> TOPIC=<name>`
  creates `.claude/worktrees/<stream>-<name>` on branch `<stream>/<name>`. Never work in another
  agent's worktree or in the main checkout's working tree while someone else is.
- **Stay in your stream.** A branch changes one stream's folder. A contract change is the one
  cross-stream change and is named as such.
- **Run the one suite before you commit**: `make test` (both streams) and `make lint`.
- **Governance first.** `governance/README.md` says who owns what, what is decided and what is open.
  Nothing in `governance/` may reach an image.
