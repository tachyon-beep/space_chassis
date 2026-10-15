# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository. It is
the map; each stream has its own guidance, which Claude Code loads when you work inside it.

## Three streams

| folder | stream | guidance |
|---|---|---|
| `vehicle/` | the vehicle sim: configuration, reference plant, console, linter, referee | `vehicle/AGENTS.md` |
| `aurora/` | the Aurora container world: harness, recorder, pump, operator services, image, compose | `aurora/CLAUDE.md` |
| `governance/` | plans, decisions, status, records; the source of truth for what is decided and where each line stands | `governance/README.md` |

`docs/diode-contract.md` and the frozen corpus `docs/deep_research/` are the border both build
streams cite by repository-relative path. Read `docs/deep_research/integration/corpus-review.md`
before any of the corpus; never edit the corpus.

Start at `governance/README.md`. Every path and task has one owning line: the chassis line owns
`aurora/` and governance outside `governance/vehicle/`; the vehicle line owns `vehicle/`,
`docs/diode-contract.md`, `docs/deep_research/` and `governance/vehicle/`.

## Commands (from the root)

```sh
make setup                 # once: pip install -r requirements-dev.txt
make test                  # the one suite, both streams: python3 -m pytest -q -n 8; no containers
make test-aurora           # aurora/ only
make test-vehicle          # vehicle/ only
make lint                  # uvx ruff check and format check; vehicle/ under its own config
make worktree STREAM=aurora TOPIC=<name>   # a worktree for one piece of work (below)
```

The stack and the operator's scripts run from `aurora/`; see `aurora/CLAUDE.md`.

## Worktrees, not repositories

Agents share one clone and work in git worktrees under `.claude/worktrees/` (gitignored), one per
piece of work, on a branch named for its stream: `vehicle/<topic>`, `aurora/<topic>`,
`governance/<topic>`. A branch touches only its stream's folder; a change to `docs/diode-contract.md`
is the one cross-stream change and says so. Never work in another session's worktree.

The vehicle was a submodule of `tachyon-beep/space_vehicle` until 2026-10-15; it is now ordinary
files under `vehicle/`, absorbed with its history at `8c6f71d`. Later commits from that repository
come in with `git subtree pull --prefix=vehicle <url> <ref>`. Plan and rationale:
`governance/plans/2026-10-15-three-stream-restructure.md`.

## Filigree

`filigree` tracks the work: `filigree session-context` at session start. Claim atomically
(`start-work` / `start-next-work`, or `work_start` over MCP), never as a claim followed by a status
update. On `SCHEMA_MISMATCH`, tell the user and do not retry. Full reference: the
**filigree-workflow** skill and `aurora/CLAUDE.md`.
