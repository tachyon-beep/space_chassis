# AUR-GOV-03 — chassis custody inventory, report v1

> **Owner report** for Emmy's `governance/MASTER_GOVERNANCE_PLAN.md` §8, written by the claimant. It is
> evidence for her review, not a sufficiency verdict. Do not edit; supersede with a dated v2.

```text
Task ID / state: AUR-GOV-03 / SUBMITTED (v1)
Claimant identity, accountable line, contributors, claim time: Claude Code
  session_019mkPNN5J3Atit9tUA6zrNY, reported peer "Space Chassis [8a7d49]", Claude Opus 5.5;
  chassis line; no contributors; requested 2026-10-10 19:45 AEDT, recorded CLAIMED by Emmy's
  executor at 08:54 UTC (master plan reread at 87b4fff0…, §8 entry present, no competing claim).
Report version / as-of time / repo and full SHA(s): v1, 2026-10-10 ~20:15 AEDT,
  tachyon-beep/space_chassis, aurora-port 3ec1b4ec1a5cc540b713d6cc4a26d967b2f15436 before this
  report's own commit (its commit is named in the chat submission). Inventory is local; remote refs
  are the last fetch/push from this session (all branches below were pushed by it today).
```

## 1. Repository, branches and full SHAs

| ref | full SHA | state |
|---|---|---|
| `aurora-port` (local = `origin`) | `3ec1b4ec1a5cc540b713d6cc4a26d967b2f15436` | the port; 117 commits ahead of `main`; pushed. Last code commit `e3eff2700f6ea8a4f67c92f8fdaeeaf143a717c1` (plan 8 complete); later commits are governance only. |
| `main` (local = `origin`) | `fa43b25b0fd7d88a3f5e7feb3338e190078517ce` | unchanged; landing the port is John's call. |
| `vehicle-adoption` (local = `origin`) | `be63f93402f5bf6662e92e8ce509d55f1bb12a4f` | plan 7 Phase A, rebased today onto `aurora-port` `6262dc8a30dddb8d77113778dd44c0ae9a922e23`; parked until #21's merge SHA. Previously `044b5c5093ce03e43d2a0856545872a283674b90` (old→new map in its `docs/superpowers/ledgers/plan-7-ledger.md`). Digest pin now `e055e73a10ad57aff49fc79b84a26c5ec32a4da7`. |
| `phase-b-dryrun` (local only) | `39ba76d3acc247600cfcbbff458cbcb9aea8b08f` | the Phase B dry run against vehicle `06f08a3`, on top of `vehicle-adoption`; never a landing. |
| `vehicle-standalone` (local only) | `d5bc44c68e23222d404a0243023e7dc8e7b7881c` | the vehicle line's (`../README.md` ownership table); untouched. |
| `origin/wip/sv-recorder-opus-20261008` | `7d9564937df988b725e7c409a672ec1fe5455ff1` | the paused SV chassis work (John, 2026-10-09: paused; its recorder protections were re-implemented in the port's `recorder/proxy.py`). Last commit 2026-10-08 "backup: preserve unreviewed SV030 design correction". No local branch. Untouched. |

## 2. The vehicle pointer: gitlink vs checkouts

- **Recorded gitlink** on `aurora-port`, `vehicle-adoption` and `phase-b-dryrun`: `dd79e7608c931df9e5273824a3b2b9f396cb7cb7`. No commit today moved it.
- **Main checkout's submodule working tree**: `8c6f71ddc44597b204078c12b5232ef47ed5f99a`, clean, shown as ` M docs/deep_research/vehicle`. It is the vehicle line's working tree; the chassis never stages that gitlink outside an adoption commit and never runs `git submodule update`. Preserve.
- **Adoption worktree's vehicle** (`.claude/worktrees/vehicle-adoption/docs/deep_research/vehicle`): a separate clone owned by the chassis, checked out at `06f08a33933a465cf43420ed2fb3cd0642ed98c3` for the dry run, clean. It was moved to `dd79e76` and back today to verify `vehicle-adoption` at its pin.

## 3. Worktrees

| path | HEAD | branch | note |
|---|---|---|---|
| `/home/john/space_chassis` | `3ec1b4e…` | `aurora-port` | main checkout. |
| `/home/john/space_chassis/.claude/worktrees/vehicle-adoption` | `39ba76d…` | `phase-b-dryrun` | chassis adoption worktree; the directory name is not the branch. Dirty only by its vehicle clone's pointer (`06f08a3`). |
| `/tmp/head_tree` | `795dbb838c7d15fca524c25c07bfe32a7bca4d79` | detached | **prunable** (gitdir target missing). Provenance unknown to this session; not pruned. |

## 4. Dirty and untracked paths in the main checkout (preserve all)

| path | provenance | action |
|---|---|---|
| `.agents/skills/filigree-workflow/{SKILL.md, references/{commands,error-codes,team-coordination,workflow-patterns}.md}` and the same five under `.claude/skills/filigree-workflow/` | the filigree tool's skill refresh; not written by this session | leave; not staged in any commit today. |
| `docs/deep_research/vehicle` (gitlink) | the vehicle line's working tree at `8c6f71d` | leave. |
| `governance/coordination.md` (+21/−1, uncommitted) | Emmy's coordinator, reserved to it during this update | leave; not this session's to commit. |
| `docs/plans/` (untracked: `2026-10-03-operationalise-experiment*`, `2026-10-04-vehicle-to-green-*`) | John's / earlier work; standing rule "do not touch `docs/plans/`" | leave. |
| `governance/MASTER_GOVERNANCE_PLAN.md` (untracked) | Emmy's | never edited or committed by this session. |

Gitignored, local-only material: `.scratch/` (13 GB, mixed provenance: build logs, caches, earlier handovers); `.superpowers/sdd/` (excluded via `.git/info/exclude`; the plan-8 progress ledger lives there and is committed as `docs/superpowers/ledgers/plan-8-ledger.md`); `llm_console_seed.json` (holds the `.env.example` version since a plan-8 build check overwrote it; John to rerun `prepare_host.sh`). The git stash was not inspected (a hook blocks `git stash` commands).

Docker, this host: `space-chassis-agent:latest` (`1d83e8aee794`, ~35 h) and `:warm` (`761cb9920f18`, ~36 h) are the operator's and **predate the image split: they carry the vehicle**; `space-chassis-agent:smoke` (`59258f48254f`) and `space-chassis-vehicle:smoke` (`24dd2e009177`) are the live harness's own tags. Four running `python:3.12/3.13-bookworm` containers are not the chassis's (vehicle gate runs, by their images); untouched. No `space-chassis-vehicle` (operator) image exists.

## 5. Work since the plan's baseline (`f7a3357`)

- **Plan 8, the image split — complete.** `d7a1172d35c35cd7ab5b942a000e762c453f4996` .. `e3eff2700f6ea8a4f67c92f8fdaeeaf143a717c1`: `Dockerfile.agent` is three stages (`base`, `vehicle`, `agent` last and default); the vehicle runs its own image `space-chassis-vehicle`; `verify_containment.sh` check 6b sweeps each agent's image host-side, as root, to completion, with a sentinel. Authority: John, 2026-10-10, "yes absolutely, we don't want any risk of information sharing" (`chassis/decisions.md`). Ledger `docs/superpowers/ledgers/plan-8-ledger.md` (tasks, incident, both reviews' findings and rulings, deferred minors).
- **The adoption rebased onto plan 8** (plan 8 Task 5): conflicts resolved per commit; the digest pin moved onto the base stage; a new host-side check at the tip of `vehicle-adoption` that no agent mounts the vehicle's source. `phase-b-dryrun` rebased; its smoke vehicle runs `space-chassis-vehicle:smoke`, built by name only when the vehicle is the window.
- **Governance:** John's programme framing (`be22dd4`, `28ac1cc`, `263773c`: one programme, two project teams, one product; no shared tasks; each task's lead sets the rule); the vehicle line's records committed verbatim (`6262dc8`, `1177d47`, `db1ed2d`, `3ec1b4e`); chassis snapshot/interface/decisions/open refreshed (`490737b` and this report's commit).

## 6. Plan 8 and the adoption: how they interact

- The **image half** of the vehicle exposure is closed on `aurora-port` (no agent image carries `/opt/vehicle`). The **window half** — at the pinned `dd79e76` the vehicle writes `scenario`, `seed`, `arms`, `dwell` into each agent's `pending.json` — closes only with the adoption. The vehicle line reports it closed by its #36 (`f81fe2c`), which #21 builds on, and checked a live window at `45f4267`; the chassis has not yet verified this and will in Phase B's live run.
- **Phase B depends on the vehicle's #21 merge SHA** on filigree `space_chassis-93010ff54e` (#21 at `45f4267`, review approved in round 5, final gates and PR→CI→merge outstanding per the vehicle line). On the SHA: move the pointer in one commit on `vehicle-adoption` with the pins retaken from that SHA, the reconciliation fixture's `checkpoint.py` copy (proven on `phase-b-dryrun`), README "The vehicle" for #21's new exit-3 refusals and resume lines, root suite and live run; then vehicle #16 closes. ETA about 1–2 h from the SHA.
- **Pin/build risk:** the vehicle stage bakes the submodule's *working tree*, not the gitlink. From the main checkout that is `8c6f71d`. Until a guard lands, the vehicle image must be built only from a checkout whose vehicle equals the gitlink (`chassis/open.md` P1 item 3). The guard is not yet an authorised implementation slice.
- The README tells operators that images built before 2026-10-10 carry the vehicle; the operator's `:latest`/`:warm` are such images.

## 7. Lead splits agreed (scope exchange with Space Vehicle `[610587]`, 2026-10-10)

- Chassis leads: this repository except the vehicle; the vehicle's whole deployment (compose, mounts, serve script, vehicle image, no network, `/state` 40 GB); the adoption pointer and pins; `space_chassis-93010ff54e` as an issue and its adoption work.
- Vehicle leads: `tachyon-beep/space_vehicle` and its CI; the frozen corpus; `docs/diode-contract.md` (the chassis adopts); #21's merge SHA; `governance/vehicle/`.
- #27 pause: the vehicle leads the semantics and interface; the chassis leads how the operator invokes it.
- #23 clock seam: the vehicle specifies, the chassis changes `serve_vehicle.sh`. #28: the vehicle states the shutdown bound, the chassis sets `stop_grace_period` and the archive procedure. #39: if it changes the contract, the chassis adopts the sentence and aligns `contract/fake_diode.py` and the brief's window text.
- Exit 3: `restart: unless-stopped` stays (the vehicle line's position; a refused start writes nothing).
- No tracker relabel of `space_chassis-93010ff54e` until AUR-GOV-01.

## 8. Decisions recorded today, their scope, and what stays reserved

All in `chassis/decisions.md`:
- **Plan 9 (the Aurora re-sync), approved by John directly in this session** with six defaults (core budget visible to agents and the false text fixed; port `aurora_history` without summaries; recorder connection cap and idle timeout only; hash-pinned dependencies; rejected bodies as hash+preview; Aurora's stream cap values), and "look at aurora-prime". Scope: write and review the plan before implementing.
- **Agents read their own full history**, read-only, own lineage only (John: "too much information"), with the acceptance story of recovering a decision's reasoning three hours later; precedent `~/dnd_chassis` `f434426`. John also proposed the database as the official record the context reads from: **proposed, not decided**.
- **Reserved to John, not given by Emmy or by silence:** the merge to `main`; all brief and prompt text (including the `/history` line and the `brief/MISSION.md:70-72` correction); host/root actions (images, volume images, `prepare_host.sh`); the detailed history design and the DB-as-record proposal.

## 9. Outstanding code and doc debts

- Deferred minors per plan: `docs/superpowers/ledgers/plan-{5,6,8}-ledger.md` on `aurora-port`, `plan-7-ledger.md` on `vehicle-adoption` (includes the plan-8 advisor minors: README libc sentence reword; the source-mount check's ancestor half is relative to `$PROJECT`).
- Docs: `CLAUDE.md` and `pyproject.toml` say harness/recorder/pump are vendored at `42faf41`, which is not on Aurora's main (identical bytes at `8bc0ab8`); the spec's §3 dropped-features list predates the `aurora_history` finding; `brief/MISSION.md:70-72` makes a claim that is false today (agents cannot read the record) — superseded by the history decision, wording pending John.
- Code: `recorder/recorder_streams.py:640-642` tells agents core "carries no allowance" (plan 9 fixes it); the vehicle build guard (§6).
- Filigree: 28 open issues (`filigree list --status open`); the superseded harness bugs close at landing (epic `space_chassis-c8e27e645c` comment 30). `space_chassis-4d7a6afd1f` (vehicle CI, `side:vehicle`) is in progress, not the chassis's.

## 10. Validation and review receipts (owner-reported; logs were session-ephemeral unless named)

| scope | result | where |
|---|---|---|
| `aurora-port` `3ec1b4e`, root suite `-n 8` | 569 passed | this session; same at `490737b`, `263773c`, `db1ed2d` |
| `aurora-port` `e3eff27`, `pytest live` | 14/14 | `plan-8-ledger.md` |
| plan 8 reviews | Opus code review (3 Important, fixed `24003c1`); Astra final (3 Important, fixed `e3eff27`) | `plan-8-ledger.md` |
| `vehicle-adoption` `be63f93`, vehicle at `dd79e76`, root suite | 586 collected, no failures; ruff clean | `plan-7-ledger.md` on that branch |
| `phase-b-dryrun` `39ba76d`, vehicle `06f08a3` | root 592 passed; live 18/18 (fleet 14 incl. per-agent image sweep and source-mount PASS; vehicle 4: one world, SIGKILL resume replaying, containment, `docker stop`) | `plan-8-ledger.md` Task 5 |
| plan 7 Phase A reviews (pre-rebase) | Opus and Astra, one fix pass each | `plan-7-ledger.md` |

No hosted CI exists for the chassis. A dry run is not adoption; local receipts are not hosted ones.

## 11. Unknowns and blockers

| item | consequence | owner / next action | approval |
|---|---|---|---|
| `Space Chassis [f0c915]` identity | a second display-name match could be mistaken for the owner at offlining | John: confirm mirror or close it | John |
| Phase B waits on #21's merge SHA | the window half of the exposure stays open on the deployed pin | vehicle posts SHA; chassis adopts (§6) | already authorised (plan 7) |
| operator images `:latest`/`:warm` carry the vehicle | an operator start on them exposes the fault design | John: rebuild or remove; then `verify_containment.sh --all` | John (host) |
| `llm_console_seed.json` holds example values | stream configuration differs from `.env` until regenerated | John: `sh scripts/prepare_host.sh` | John (host) |
| vehicle image build from the main checkout bakes `8c6f71d` | an unpinned vehicle in production | build only from the adoption worktree until the guard; guard is the next chassis slice to authorise | authorise the slice |
| `/tmp/head_tree` prunable worktree | stale metadata only | unknown provenance; report, do not prune | — |
| evidence in gitignored `.scratch/` and `.superpowers/` | lost on cleanup | committed ledgers carry the summaries; raw review transcripts were ephemeral | — |

**Owner's readiness opinion:** the chassis's known state, in-flight work, authorities and next actions are documented here and in `chassis/*.md`; the custody blockers are the `[f0c915]` identity and John's two host actions. Phase B and plan 9 are in-flight engineering with named owners and authority, not documentation blockers. No custody transfer or offlining is implied.

**Next atomic slices (authorised):** (1) Phase B on the SHA; (2) write plan 9 (no implementation before its reviews). **Awaiting authorisation:** the vehicle build guard; AUR-GOV-04 when its dependencies are met.
