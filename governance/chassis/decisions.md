# Chassis — decision log

As of **2026-10-10**, `space_chassis` `aurora-port` @ `84b1c49`. This log is **append-only**. A
revised decision gets a new dated entry pointing back, never an edit in place.

- **Who** is either *John* (the owner and operator) or *coordinator* (a Space Chassis session
  deciding under John's standing delegation, and open to his revision).
- **Where** is the authoritative record. This log only indexes it.

The coordinator's smaller rulings are not repeated here. Each plan's ledger lists them, with what
each costs if wrong (`docs/superpowers/ledgers/`).

## Standing instructions and rules from John

| date | decision | where |
|---|---|---|
| 2026-10-09 | Rebuild the space harness on `~/aurora`'s setup: "replace all of the various components and entertainment options with the llm lunar mission". One container per agent, three git tiers, `done` clears context. | spec header and §1 |
| 2026-10-09 | Work natively and autonomously, with regular reviews. While Fable is limited, the review model is **Opus, plus one codex-cli run at `gpt-6-astra` high**. | session instruction; `practice.md` |
| 2026-10-09 | Never `git stash`. Never read a `.env` file (`.env.example` is fine). No `git submodule update`. No broad `git add`. | session instruction |
| 2026-10-09 | No push or merge without explicit authorisation. Later the same day, pushes of the work branches were authorised ("feel free to push"); a merge to `main` still needs John. | session instruction |
| 2026-10-09 | Root, mounts, volume-image creation and `/etc/fstab` are John's. Never run `prepare_host.sh` against the real tree; never write the real `volumes/`, `operator/` or `.env`. The real model key never goes into argv, logs or the smoke stack. | session instruction |
| 2026-10-09 | Prompt and brief text needs John's approval: implementation drafts it, and only approved text ships. | spec §6 |
| 2026-10-09 | "Deconflict with the other agent. I need both of you working." The chassis works in its own worktree and its own vehicle clone, and never touches the vehicle line's checkout. | session instruction; `practice.md` |
| 2026-10-10 | One `governance/` folder for the two lines. **The two lines divide the whole project, with no third or spill-over line; shared plumbing is split between them.** | session instruction; `../README.md` |
| 2026-10-10 | **One program (Space Aurora), two project teams, one product.** The teams are of equal importance and work together in parallel: the chassis (the Aurora containers and harness) and the vehicle (the simulation). Emmy coordinates the program. The no-third-line rule divides ownership of the work, not the product. There are no shared tasks: every task has one lead team that sets the rule, and the other team follows it where it has to do the same. | John, in this session | `../README.md` |

## The design's rulings (spec §1)

| date | decision | who | where |
|---|---|---|---|
| 2026-10-09 | Agents always hold the pen on their whole harness, the watchdog included. | John | spec §1 rulings 1–2 |
| 2026-10-09 | `done` means a new agent; churn and memory are the agents' business; the harness adds no behavioural policy beyond Aurora's. | John | spec §1 rulings 3–4 |
| 2026-10-09 | Three tiers (experimental, baseline, rescue). Each agent has its own home container in a shared world. Seed toolset: Aurora's eight tools plus a mission kit. Spend caps per agent and for the fleet, with a jittered pause on exit 44. | John | spec §1 rulings 5–8 |
| 2026-10-09 | The SV workstream's chassis half is paused; its recorder half is re-implemented in `recorder/proxy.py`. | John | spec §10.1; memory `sv-workstream-owns-chassis-persistence` |
| 2026-10-09 | Recorder (plan 4b): withhold a reply that cannot be recorded; durability on the buffered path only; keep `REQUEST_MAX_BYTES` at 16 MiB; fix the stream registry's hour rollover. | John | plan 4b; `plan-4b-ledger.md` |

## Decisions since

| date | decision | who | where |
|---|---|---|---|
| 2026-10-09 | The brief and prompt drafts are approved and ship. | John | `12a6489`; `docs/brief-claims.md` |
| 2026-10-09 | Carry out the four open long-life items and the archive gap. This authorises archive pruning as a named deviation from "watchdog ported as-is". | John | plan 6; `bbc4fb7`; filigree `space_chassis-e5b2675c98` |
| 2026-10-09 | The brief clause on bounded archives is approved and ships. | John | `1697ca9` |
| 2026-10-09 | The vehicle runs with no network (`network_mode: none`). Its deployment belongs to the chassis; the vehicle states its needs. | John, carried out by the vehicle line | `0ccc4cc`; spec §8 |
| 2026-10-09 | The operator journal stays append-only; only the derived `fleet.jsonl` rotates. | coordinator, after a security review | `cbac94f`; `plan-6-ledger.md` |
| 2026-10-09 | The vehicle's 40G `/state` image is allocated whether or not the vehicle profile runs. | coordinator | `plan-7-ledger.md`; `.env.example` |
| 2026-10-10 | Pin the agent image's Python base by digest. Relayed by the Space Vehicle session, and flagged to John for veto. | John (relayed) | `044b5c5` on `vehicle-adoption` (`e055e73` after the plan-8 rebase) |
| 2026-10-10 | A Phase B dry run against vehicle `06f08a3`, on a local branch only, with `vehicle-adoption` kept parked. Both Space Vehicle sessions agreed. | coordinator | filigree `space_chassis-93010ff54e` comment 40 |
| 2026-10-10 | **Separate images: the agents' image carries nothing of the vehicle** ("yes absolutely, we don't want any risk of information sharing"). | John | plan 8 (`docs/superpowers/plans/2026-10-10-aurora-port-8-image-split.md`); `d7a1172`, `4cb4ede`, `6e5370d` |
