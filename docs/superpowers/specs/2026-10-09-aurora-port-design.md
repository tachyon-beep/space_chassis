# Aurora port: the space harness rebuilt on Aurora's setup

**Status:** revision 2, 2026-10-09. The design was approved in conversation with John. Revision 1 was reviewed by three subagents: solution design, systems thinking, and a containment threat model. This revision answers them (section 11 lists the changes). The spec is awaiting John's review. No implementation is authorized by this document.

**Direction (John, 2026-10-09):** "take the 'aurora setup' and just replace all of the various components and entertainment options with the llm lunar mission". Where Aurora and the current space harness differ, Aurora wins, unless this spec names a deviation and its reason.

**Reference:** `~/aurora` at `42faf41`, in particular `watchdog.py`, `agent.py`, `chassis.py`, `command_runtime.py`, `proxy.py`, `recorder_streams.py`, `pump.py`, `entrypoint.sh`, `Dockerfile`, `docker-compose.yml`, and `docs/superpowers/plans/2026-10-05-evolving-recovery.md`.

## 1. Rulings this design rests on

These are John's words or decisions. They replace earlier space rules where the two conflict.

1. **Agents always hold the pen.** "The agent has full freedom to remove, change or add anything to the agent.py and the watchdog/supervisor will restore per whatever code it has at the time." "The intent was never to take the pen away from them."
2. **The watchdog is editable too.** "The watchdog is editable but they generally don't because they can't fix it if it breaks." The option must always be there.
3. **Done means a new agent.** "The only thing a 'done' agent does is clear the context and restart fresh with a new agent." Agents are expected to edit their own harnesses and build their own tools, memory and context management.
4. **Churn is the agents' business.** As long as they are not deficient, agents may restart as often as they choose. Trouble is caught by their own automated monitoring, by the rescue tier, and by the other agents. The harness adds no behavioural policy beyond Aurora's.
5. **Three tiers.** Aurora's experimental, baseline (release) and rescue checkpoints come across unchanged.
6. **Own home container, shared world.** Each agent has its own container and its own harness, while the vehicle window and the fleet's shared surfaces stay shared. This is John's ruling and space's existing shape. Aurora itself runs several hosts in one container (`AURORA_HOSTS`), each with its own `/workN` harness and recorder, so what carries over from Aurora is the per-host harness, not its container layout.
7. **Seed toolset (decided 2026-10-09):** Aurora's eight genesis tools plus a mission kit, so the mission is reachable from turn one (section 3.1).
8. **Spend caps (decided 2026-10-09):** keep an hourly cap per agent and one for the fleet on the main model socket, and jitter the exit-44 pause. This is cost containment, not behavioural policy (section 3.3).

## 2. Invariants

What the agent can change:

- **Everything in its own harness.** That is the git repository at `/work`: `agent.py`, `chassis.py`, `command_runtime.py`, `watchdog.py`, the prompts, and anything it adds. Nothing in the image, a test or a hook makes any of it read-only. Edits persist across a fresh start only through the checkpoint tags, which the agent moves itself.
- **Its private durable storage**, `/state`, and its own loopback servers.
- **The shared surfaces:** `/shared` and `worknet`, on equal terms with the other nine agents.

What the agent cannot reach:

- **Another agent's anything.** That covers its window, pump, recorder socket and llm console, telemetry, `/work`, `/state`, servers' data and transcripts.
  - **One rule enforces this: every per-agent volume is bound per agent** (`./volumes/<x>/<slug>`), and no agent mounts a parent directory that holds a sibling's subdirectory. The binds are what attribute an agent's actions, which `docs/diode-contract.md` already requires of the window.
- **The recorder**, the only holder of the model credential, and every transcript.
- **The image seed**, and **a reseed it cannot outlive.** A reseed is a container exit (section 4), so Docker ends every process in the container and drops the tmpfs. Nothing the agent can write outside `/work` and `/state` executes in an image-owned process:
  - The image sets `PYTHONNOUSERSITE=1` and `GIT_CONFIG_GLOBAL=/dev/null`.
  - `HOME` is on tmpfs, and `/state` is never on any import or config path.
- **The vehicle's side of the window, and the operator surfaces.**
- **Any route out.** `worknet` is `internal: true`, and no service on it also sits on a network with a gateway.

Same-uid processes inside one container can signal each other. That is accepted: it only lets an agent end itself, which is within its pen.

## 3. Components

| Aurora | Space port |
|---|---|
| **agent** (`agent.py`, `chassis.py`, `command_runtime.py`) | Ported. The seed adds the mission kit (3.1). One container per agent, one Aurora host per container. |
| **watchdog** (`watchdog.py`, in the agent's repo) | Ported as-is. Replaces `services/supervisor.py`. See section 4. |
| **entrypoint**: copy `/opt/agent` into `/work`, then `exec` the watchdog | Ported in Aurora's host-1 `exec` form, so a dead watchdog ends the container. The restart policy brings it back and the entrypoint reseeds. Aurora's in-container multi-host reseed loop is not used. |
| **`/work` tmpfs**, the harness repo with `baseline` and `rescue` tags at the seed commit | Ported, per agent. |
| **`/state`**, private and durable | Ported. Replaces space's `/home/agent` and `/diary`. The servers' data lives under it. |
| **recorder** (`proxy.py`, `recorder_streams.py`, llm console) | Ported, one per agent, with core-socket caps added (3.3). Replaces `services/recorder.py`. |
| **pump** | Ported, per agent: each container has its own `/pump` bind. Replaces `services/pump.py`. |
| **telemetry mirror** | Ported, into a per-agent directory that nothing else writes, because `mirror_work` deletes everything else under its root. It is the agent's *claim* (3.4). |
| diode (web), video, sense, stage, stage console, viewer, cloudflared, garden, books, public site, `blind_eternities.txt`, and the filigree seed entries in Aurora's `Dockerfile` | **Dropped.** |
| *(new)* **vehicle window** | Retained from space: `/diode/<slug>`, per `docs/diode-contract.md`, with a per-agent bind. Served by the vehicle workstream's service, or by `contract/fake_diode.py` under the `diode` profile. |
| *(new)* **loopback servers** | Retained from space: Postgres, NATS and Redis start inside each agent's container on `127.0.0.1`, empty, as `containers/entrypoint.sh` does today. Their data moves to `/state`. |
| *(new)* **shared world** | Retained from space: `worknet` (agents can bind ports and reach each other's services) and a shared read-write volume for joint code, mounted at `/shared`. |
| prompts | Aurora's shape, in the harness repo, so they are editable. They carry the mission (section 6). |
| *(operator surfaces)* | Retained from space: the review panel, `fleet_monitor`, `status.py`, `roster.py` and `verify_containment.sh`, adapted to Aurora's formats, plus the operator journal (3.4). |

### 3.1 Seed toolset

Aurora's eight tools stay: `read_file`, `write_file`, `validate`, `migrate`, `done`, `reset`, `list_dir`, `compact`. Three more are added as ordinary, editable code in `agent.py`:

- **file read/write anywhere the agent can see**, so it can reach `/opt/brief`, its window, `/shared`, `/state` and `/work`;
- **a command runner** built on Aurora's bounded `run_command`;
- **git**, through that command runner.

Aurora's affectless-docstring rule applies to all three. This is a deviation from Aurora's genesis set, recorded as ruling 7.

### 3.2 Image and resources

- **Image:** one agent image built in this repo from Aurora's `Dockerfile`, keeping space's mission package set (`docs/design.md` §4: Python scientific stack, C and Rust toolchains with the offline crate registry at `/vendor`, and the three servers). *Revised 2026-10-10 (John: no risk of information sharing; plan 8):* `Dockerfile.agent` has a `base` stage, an `agent` stage (the default, and the image every service but the vehicle runs) and a `vehicle` stage that alone adds `/opt/vehicle` and its serve script, tagged `space-chassis-vehicle`. Until then every agent could read the vehicle's fault policies and run `console.py --plan`.
- **uid:** agents run as uid 1000, matching the vehicle and the existing volumes.
- **Hardening:** a read-only root, all capabilities dropped, and `no-new-privileges`.
- **Limits** sized for ten agents on this host (61 GB, 24 cores), all set from `.env`:
  - 3 GB memory, 1 CPU, 1024 pids;
  - a 1 GB `/work` tmpfs, which counts against memory;
  - the defaults are space's current figures (`AGENT_CPUS` and friends).
- **Bounded volumes:** Aurora's `create_host_path: false` and `warn_if_unbounded`. Transcripts live on their own filesystem, so an agent filling a shared disk cannot silence the record.
- **Servers on a read-only root.** Space's entrypoint starts Postgres through Debian's `pg_ctlcluster`, which needs `/etc/postgresql`, `/var/run/postgresql` and `/var/log/postgresql` writable. With a read-only root and data under `/state`, the entrypoint instead runs `initdb` into `/state` once and starts `postgres` directly, with tmpfs for the run and log directories. NATS and Redis take their data directories under `/state` the same way.

### 3.3 Recorder caps

- **Per agent:** each recorder enforces an hourly request and token ceiling on its core socket, as space's recorder does today. Aurora's core socket has none.
- **Fleet:** a fleet-wide ceiling through a ledger shared by the recorders only, on a volume no agent mounts. A recorder refuses a core request when either ceiling is spent, with the response the chassis classifies as exit 44.
- **Declared streams** keep Aurora's per-stream budgets. Their global pool is also counted against the fleet ledger.
- **Exit 44** pauses for 60 s plus jitter in the seed watchdog, so ten agents do not retry in lockstep.

### 3.4 Operator journal and health signals

These are observation only. None acts on an agent.

- **Journal.** An append-only operator journal outside every agent mount records, per agent:
  - periodic snapshots of `/work`, with tags and recovery state. `/work` is tmpfs inside the container, so the snapshot is `docker cp` of the repository out to the host, then bundled there by the host's own git. Git never runs inside the agent's container for the journal, because the repository-local `.git/config` is the agent's, and `core.hooksPath` or `core.fsmonitor` would run agent code inside the journaling process. The journal runs no agent code;
  - container restart counts and the watchdog's exit lines;
  - snapshots of `/shared`.

  A reseed, a tag move or a correlated break in `/shared` becomes attributable after the fact.
- **Health signals** come from the recorders' own transcripts, never from agent-written files: requests per incarnation, conversation resets, system-prompt hash changes, tool-error rate, vehicle commands per incarnation, and spend against the caps.
- **Staleness.** `status.py` reports an agent whose transcript and container have both gone quiet. This covers a hung watchdog, which nothing inside the container will catch unless the agents build that.
- **Telemetry trust.** Telemetry and recovery notes are written from inside the agent's container, so the operator surfaces label them as the agent's own claim.

## 4. Lifecycle and recovery

Aurora's exit codes and ladder replace space's.

| Exit | Meaning | Watchdog action |
|---|---|---|
| 0 | run ended | restart, conversation kept. Three within 120 s count as a failure. |
| 42 | `done` | elective reset, fresh: archive the conversation and restart a new agent on `experimental` if eligible, else `baseline`, else `rescue`. All exit histories clear. |
| 43 | the chassis ended the incarnation (unrecoverable fault; tombstone written) | `failure(fresh_only)`: the code resets to `baseline`, or further down the ladder, with a new incarnation. Three within 600 s escalate the tier. |
| 44 | environment unusable (credit, key, upstream, or a recorder cap) | pause 60 s plus jitter, restore nothing. |
| 45 | `reset` | elective reset, keeping the conversation, on `experimental`, else `baseline`, else `rescue`. |
| other, or a signal | crash | failure ladder. |
| 24 h with no log growth | inactive | treated as a failure. |

- **Failure ladder:** baseline with the same conversation, then baseline fresh, then rescue fresh. When that is exhausted, the watchdog exits, the container ends, and the entrypoint reseeds on restart. The first boot after a reseed writes a recovery note saying it is one.
- **Failed commits:** a commit that has failed is excluded until its tag moves.
- **Probation:** recovery ends after one completed chassis call plus 60 s. A fault slower than that re-enters the ladder at its first step each time. This is Aurora's behaviour, kept, and the journal makes it visible.
- **The tags belong to the agent.** The seed creates `baseline` and `rescue` at the initial commit, and `experimental` starts absent.
- **An edited watchdog takes effect immediately:** it stops the agent and re-executes itself on the new code.
- **Archives are not durable.** Conversations are archived to `tombstones/` and the git directory, both in the `/work` tmpfs, so a reseed or a container replacement erases them. The durable records are the recorder's transcripts and the operator journal.

This replaces space's rules that a budget exhaustion exits 42 and resumes, that no rung touches the conversation, and that the supervisor never runs from `/work`. The tests enforcing those rules are retired with them.

## 5. Filesystem and network per agent

Every row except `/shared`, `/opt/brief` and `/vendor` is a per-agent bind.

| Path | What | Lifetime |
|---|---|---|
| `/work` | harness repo, tmpfs | until reseed or container replacement |
| `HOME` | tmpfs | as `/work` |
| `/state` | private durable storage, including the servers' data | permanent |
| `/shared` | the fleet's joint code, read-write | permanent, shared |
| `/diode/<slug>` | this agent's window, bound alone | the vehicle's |
| `/pump` | this agent's pump entries and state | permanent |
| `/llm/sock` (read-only), `/llm/console` | this agent's recorder socket and stream declarations | permanent |
| `/telemetry` | this agent's mirror directory | written by its watchdog |
| `/opt/brief` (read-only) | `MISSION.md`, `PROTOCOL.md`, `WORLD.md` | image |
| `/vendor` (read-only), `/build` | offline crate registry, build scratch | image, tmpfs |

- **Transcripts: open for John (section 10).** Aurora mounts none. Space deliberately gives each agent its own transcript read-only, and `brief/PROTOCOL.md` promises it. With per-agent binds, mounting an agent's own transcript alone is safe. The default is Aurora's: no mount.
- **Network deviation from Aurora:** agents join `worknet` (`internal: true`, no gateway) and nothing else, because `brief/WORLD.md` gives them a working internal network: "bind ports, run servers, reach other agents". `modelnet` and `windowside` stay closed to agents.
- **Fake-diode network:** `contract/fake_diode.py` does not join `worknet`, since its interface is the volume.
- **Roster:** the roster moves out of the shared volume to an operator directory. Each recorder is configured with its own slug, so the `.fleet/` announcements are retired.

## 6. Prompts, the brief and the mission

**The mission is assigned; the roles are not.** Aurora's world is "true, complete, and unassigned". The space world keeps "true and complete" and deliberately differs on "unassigned": the mission is the one assigned objective ("Keep the crew alive and bring them home"), while ranks, roles and the division of labour stay unassigned, as `brief/MISSION.md` already says.

**The system prompt** keeps Aurora's structure and its account of the agent's own physics: recovery, the danger of believed text, and the invitation to rewrite the prompts. Two passages change:

- The unassigned-world passages are replaced by a pointer to `/opt/brief`.
- Aurora's "nothing you do can damage the environment itself" is false here, because there is a crew behind the window. It is rewritten so that it claims safety only for the agent's own harness.

**The brief** is a fact about the world, so it stays read-only. `WORLD.md` and `PROTOCOL.md` are rewritten to describe this design: the agent's own `/work`, `/state`, the tiers, aurora's exits, no transcripts mount, and `/shared`. The current text describes the retired world.

**John approves** the final prompt text and the brief rewrite. Implementation drafts them, and drafts only.

## 7. Retired from the space harness

- `services/chassis.py`, `services/supervisor.py`, `services/recorder.py` and `services/pump.py`.
- `tasks/duty.py`, the shared-duty model, and the `_load_runtime()` workaround.
- `containers/entrypoint.sh`'s seeding, `.fleet/` announcement and supervisor start. Its server start is kept.
- The exit-code, ladder and invariant sections of `CLAUDE.md` and `docs/design.md` §6, which are rewritten.
- The P1 bugs `835d551619`, `a5c2a27876`, `3cb643af8e` and `833a01f2de`: superseded, to be closed when the port lands. The other lifespan issues are re-triaged against Aurora's `chassis.py`.

## 8. Coordination

- **SV workstream.** The SV016–SV030 work on `wip/sv-recorder-opus-20261008` rewrites the runtime this port retires. John decides whether that work pauses, or which pieces (for example the strict request accounting) carry into the recorder caps of 3.3.
- **Vehicle workstream.** A separate agent owns the vehicle repository (`docs/deep_research/vehicle/`, the code that runs inside the `vehicle` container). **The `vehicle` service's deployment — its compose entry, networks, mounts and `serve_vehicle.sh` — is this repository's**, generated by `scripts/build_compose.py` and held by `tests/test_vehicle_reconciliation.py`; the vehicle workstream states what its code needs and the chassis provides it. (Revised 2026-10-09: this bullet first asked the vehicle workstream not to put "its" service on `worknet`, while the generator and the reconciliation test put it there; a request to the owner of neither artefact stayed open.)
  - **Network: none.** The vehicle's code opens no socket and its interface is the window volume, as the fixture's is (section 5), so the service runs with `network_mode: none`. Done in the generator and its test.
  - **Vehicle-private state off the agent-writable window** (contract line 150). The vehicle reads no authority from a window; its private state lives in `--state-dir` on a volume of its own (vehicle WP08 #20). `pending.json` is still written into each window because contract §2 lists it there; it is a published copy, never read back except by a refuse-only legacy check, and carries no fault-plan input (vehicle follow-up removes the seed from it).
  - **The vehicle's stated needs:** the diode-root bind, a private volume for `--state-dir` not shared with the diode volume, and one console process serving every slug. Per-agent `/diode/<slug>` binds are accepted (vehicle ADR 0001/0002 rely on them).
- **Existing state.** The ten homes under `volumes/home/` are archived, not migrated. They came from stub-model runs.

## 9. Acceptance

**Ported Aurora tests**, passing in this repository:
- watchdog: `test_watchdog`, `test_evolving_recovery`, `test_watchdog_telemetry`
- chassis: `test_chassis_recovery`, `test_chassis_commands`, `test_compact`, `test_context_window`, `test_repair_send_view`, `test_session_persistence`, `test_file_tools`, `test_tool_registry`, `test_command_runtime`, `test_startup`, `test_persistent_state`
- recorder: `test_proxy`, `test_recorder_streams`, `test_recorder_events`, `test_recorder_console_hostile`, `test_unix_listener`, `test_upstream_selection`, `test_llm_console_seed`
- `test_pump`
- `test_agent_credentials`, `test_agent_dependencies`, `test_smoke`, and `test_cleanliness`, adapted to the mission world

**Space tests kept:** `test_vehicle_reconciliation`, `test_observer`, `test_review` (adapted).

**New end-to-end checks against the stub model:**
1. Using the seed kit, an agent edits `agent.py`, commits, moves `baseline`, calls `done`, and starts fresh on its own code.
2. A syntactically valid but broken `agent.py` walks baseline/same, then baseline/new, then rescue/new, then reseed, with a recovery note at every step, including the post-reseed boot.
3. An edited watchdog re-executes itself, and a crashing watchdog ends the container, which reseeds. A watchdog that is alive but idle is reported by `status.py`.
4. `reset` keeps the conversation; `done` archives it.
5. A broken release in one agent leaves the other agents running. A broken module in `/shared` that only one agent imports leaves the rest running, and the seed harness imports nothing from `/shared`.
6. **Containment, negative checks.** An agent cannot connect to a sibling's socket, cannot write a sibling's `/diode`, `/pump`, `/llm/console` or telemetry, and cannot read any sibling's transcript. It reaches its own loopback servers and a sibling's listener on `worknet`, and has no route or DNS out. `verify_containment.sh` is rewritten for these, and it no longer places the real key in a process's arguments inside an agent container.
7. **Caps.** A recorder refuses at the per-agent cap and at the fleet cap, and the agent pauses with jitter on 44.
8. **Survival.** Nothing written to `HOME`, `/state` or `/shared` executes in the pump, the reseeded watchdog or the ladder's git calls, and the operator journal runs no agent code.

**Stub model.** The end-to-end checks use Aurora's stub (`scripts/verify_stub_llm.py`), because it speaks the request shape Aurora's chassis sends. Space's `endurance/stub_model.py` answers on cue for the retired duty, and is either adapted to that shape or retired with it.

**Cheapest proof of a running stack:** the smoke stack of three agents, the stub model and the contract fixture as the window.

## 10. Open for John

1. **What happens to the SV workstream (section 8).** This shapes the implementation plan: the recorder work in 3.3 differs materially depending on whether SV's request accounting carries over.
   **Decided 2026-10-09 (John):** SV's chassis half (SV019–SV030: session persistence, replay, ledger, GC, bootstrap recovery) is paused; the port's Aurora chassis replaces the code it hardens, and the agents own their memory. Its recorder half carries over as a re-implementation in `recorder/proxy.py`, in priority order: structural bounds on agent-supplied request bodies, an absolute per-request deadline, the transcript made durable before the reply is relayed, and a parity check of the spend accounting under concurrency and across hour boundaries. SV's tests and design notes on `wip/sv-recorder-opus-20261008` are the specification for that work; the branch is not merged.
2. The final prompt text and the brief rewrite (section 6).
3. The cap figures: per agent per hour, fleet per hour, and the declared-stream pools.
4. Whether each agent mounts its own transcript read-only (section 5).

## 11. Changes from revision 1, and the review findings behind them

- **Postgres, NATS and Redis:** stated as per-container loopback servers, not shared, and the network deviation re-justified by agent-to-agent traffic. (solution review, critical)
- **Resources:** sized for this host instead of Aurora's 16 GB and 2 CPUs per agent. (solution review, critical)
- **Seed toolset:** the mission kit added, ruling 7. (solution review, critical; John's decision)
- **Core spend caps** and jittered 44, ruling 8. (all three reviews; John's decision)
- **Per-agent binds** for the window, pump, socket, console and telemetry, plus negative containment checks. (threat review T1–T3, T8, T10)
- **Reseed** by container exit, with `HOME` on tmpfs, no user site and no global git config. (threat review T4, T5)
- **"Archived, never deleted" corrected**, with the operator journal and recorder-derived health signals added. (systems and solution reviews)
- **Hung watchdog:** operator-side staleness report. (solution review)
- **Exit 43** described correctly (code resets to baseline); the post-reseed recovery note added. (solution review)
- **Image, uid, `/vendor`, filigree seeds, telemetry root, roster, brief and prompt falsehoods, verify-script key exposure** addressed. (solution review; threat review T9)
- **Bounded volumes** and transcripts on their own filesystem. (threat review T7)
- **Vehicle-side requests** for `pending.json` and the service's network. (threat review T3, T12)
- **Own-transcript mount** moved to John's open questions, defaulting to Aurora's no-mount; journal snapshots taken without running git in the agent's container; the read-only root and server-start interaction stated; the stub model named. (second-opinion pass)
