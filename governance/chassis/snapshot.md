# Chassis — snapshot

As of **2026-10-10**, `tachyon-beep/space_chassis` **`aurora-port` @ `84b1c49`** (pushed), with
`vehicle-adoption` @ `044b5c5` (pushed, parked) and the local dry-run branch `phase-b-dryrun` @
`397d032`. `main` is @ `fa43b25`, 100 commits behind `aurora-port`. Maintained by the Space Chassis
session. **Verify against the code before trusting any line here.** This file summarises; the
repository, its tests and its filigree issues are authoritative where they disagree.

## What the chassis is

Everything in `space_chassis` that is not the vehicle (the partition is in `../README.md`): the
world ten self-modifying agents live in, and the record of what they do there. Since the Aurora port
(spec `docs/superpowers/specs/2026-10-09-aurora-port-design.md`) the shape is as follows.

- **One container per agent, running Aurora's harness** (`harness/` → `/opt/agent` → `/work`):
  - `agent.py`, `chassis.py`, `command_runtime.py`, `watchdog.py` and the prompts;
  - a git repository with `baseline` and `rescue` tags;
  - the agent's to rewrite, the watchdog included (spec §1, rulings 1–2).
- **One recorder per agent** (`recorder/`), holding:
  - the only credential;
  - the transcript, synced before a reply is relayed;
  - the strict request bounds;
  - the per-agent and fleet spend caps (`core_caps.py`).
- **The pump** (`pump/pump.py`): scheduled and kept-alive processes per agent.
- **Per-agent bounded volume images** (`scripts/volume_images.py`): `/state`, `/pump`, `/build`,
  `/telemetry`, `/llm/console`, `/llm/sock`. There is also one shared `/shared` image and one window
  image, of which each agent binds only `/diode/<slug>`.
- **The operator surfaces, which observe and never act:**
  - `services/health.py`: signals from the transcripts only;
  - `services/fleet_monitor.py` and `services/review.py`: the panel, loopback only;
  - `scripts/status.py`;
  - `scripts/journal.py`: snapshots of `/work/.git` and `/shared`, append-only, on the host.
- **The brief** (`brief/` → `/opt/brief`) and the prompts. John approved their text on 2026-10-09;
  every claim they make is sourced in `docs/brief-claims.md`.
- **The deployment of the vehicle**: the `vehicle` compose service and `containers/serve_vehicle.sh`.
  The chassis owns the deployment and the vehicle states its needs (spec §8). See `interface.md`.

## Where it stands

| | |
|---|---|
| Plans done | Ports 1–6 (`docs/superpowers/plans/2026-10-09-aurora-port-{1..6}*.md`). The ledgers with the rulings and deferred minors are in `docs/superpowers/ledgers/plan-{4b,5,6}-ledger.md`. |
| Plan in flight | Port 7, vehicle adoption (`…-7-vehicle-adoption.md`, ledger `plan-7-ledger.md` on `vehicle-adoption`). Phase A is done, reviewed and pushed on `vehicle-adoption`. Phase B waits for the vehicle's #21 merge SHA, posted on filigree `space_chassis-93010ff54e`. |
| Vehicle pinned | `docs/deep_research/vehicle` @ `dd79e76` on `aurora-port` and `vehicle-adoption` alike. No pointer bump before the adoption commit. |
| Base image | `python:3.13-slim@sha256:70729b46…` (Python 3.13.16), pinned on `vehicle-adoption` (`044b5c5`). `aurora-port` still builds from the unpinned tag. |
| Last full runs | `aurora-port` at `ce4f5e4`: merged suite 1711 passed, live 14/14 (`plan-6-ledger.md`). Root suite 558 at `42b24f7`. `vehicle-adoption` at `b94ef44`: merged 1811 passed plus the two Phase-B pins failing as expected; live 14/14 on the pinned base (`plan-7-ledger.md`). |
| Dry run of Phase B | Against vehicle `06f08a3` (2026-10-10), on `phase-b-dryrun`: live vehicle checks 4/4 (one world, SIGKILL → resume replaying 13 ticks, containment, `docker stop`), and root suite 579/579 with the dry-run pins. Recorded in filigree `space_chassis-93010ff54e` comment 40. |
| Quality gates | Every commit runs the root suite after `git add`, plus `uvx ruff check` and `ruff format --check`. A change to the image or compose also runs `pytest live`. Each plan gets an Opus plan review, an Opus code review and one Astra (high) final review (`practice.md`). |

## Branches and checkouts

- **`/home/john/space_chassis`** is the main checkout, on `aurora-port`. Its
  `docs/deep_research/vehicle` working tree belongs to the vehicle line: it is at `8c6f71d` and shows
  `M`. The chassis never `submodule update`s it and never stages that gitlink outside an adoption
  commit.
- **`.claude/worktrees/vehicle-adoption`** is the chassis worktree for the adoption. Its vehicle is
  a separate clone (`--reference --dissociate`); it is checked out at `06f08a3` for the dry run, and
  its gitlink is not staged.
- **`origin`** carries `aurora-port`, `vehicle-adoption` and `main`, plus the paused
  `wip/sv-recorder-opus-20261008`.
