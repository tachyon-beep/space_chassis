# Chassis — practice

As of **2026-10-10**, `space_chassis` `aurora-port` @ `84b1c49`. How the chassis line is worked.
**Verify against `CLAUDE.md`, `AGENTS.md` and the tests before trusting any line here.** They are
authoritative.

## The cycle

1. **Plan.** Use the writing-plans skill to write `docs/superpowers/plans/<date>-aurora-port-<n>-<topic>.md`
   from the spec. Every plan has Global Constraints and a Review Focus.
2. **Plan review.** An Opus subagent reviews the plan against the real code. Its corrections are
   committed as "plan <n>: corrections from the Opus plan review".
3. **Execute inline.** Use the executing-plans skill, with a ledger at
   `.superpowers/sdd/<plan>/progress.md`. Each task is TDD (RED, then GREEN, then the suite). Every
   deviation is ledgered as `Ruling: <what> — <why> — <cost if wrong>`. `task-done` writes the
   completion line only when the task's tests pass.
4. **Code review.** An Opus subagent reviews the range, then one fix pass. Each fix is RED→GREEN.
5. **Final review.** One Astra run through codex-cli, read-only:
   `codex exec -m gpt-6-astra -c model_reasoning_effort=high -s read-only -C <dir> -o <out> "<prompt>" < /dev/null`.
   In a worktree session, run it from a small script file. Then one fix pass.
6. **Re-grade by effect.** A minor that would mislead an operator or an agent, or let a check pass
   falsely, is re-graded Important and fixed. Other minors go to the ledger as
   `minor (deferred)`.
7. **Record.** Commit the ledger to `docs/superpowers/ledgers/plan-<n>-ledger.md`. Comment on the
   filigree issues with their commits. Closing them waits for the port to land on `main`, which is
   John's call.

## Gates on every commit

- Stage files **by name**, then run the root suite (`python3 -m pytest tests -p no:cacheprovider -n 8`)
  *after* `git add`. The retirement guard scans tracked files only.
- Run `uvx ruff check . --no-cache` and `uvx ruff format --check . --no-cache`.
- A change to the image, compose or the vehicle's deployment also runs `python3 -m pytest live -q`.
  It builds `space-chassis-agent:smoke` and runs its own compose project. The vehicle variant is
  `SmokeStack(window="vehicle")` and `live/test_vehicle.py`.
- Doc guards: `tests/test_doc_claims.py` (claims the code contradicts), `tests/test_retired.py`,
  and `tests/test_citations.py` (cited tests exist).
- The commit trailer names the model, per the session's attribution reminder.

## Hard constraints

These are John's (`decisions.md`):
- no `git stash`;
- no `.env` reads;
- no `git submodule update`;
- no broad `git add`;
- no merge to `main` without John;
- no root, mount or image creation;
- no `prepare_host.sh` against the real tree;
- the real key never in argv, logs or the smoke stack;
- brief and prompt text only as approved.

## Working beside the vehicle line

- **The main checkout's `docs/deep_research/vehicle` belongs to the vehicle line.** Never update it,
  never stage its gitlink, never `commit -a` while it shows `M`.
- **Chassis work that needs a different vehicle runs in a worktree under `.claude/worktrees/`**
  (gitignored), with its own vehicle clone. Make the clone with
  `git clone --reference <shared module store> --dissociate`, so no link is left behind. Check it
  out there, and stage the gitlink only in the adoption commit.
- **An image build copies the vehicle from its build context** (`Dockerfile.agent:76`). Build from
  the worktree whose vehicle is the one intended.
- **Coordinate on filigree `space_chassis-93010ff54e`** (CLI or MCP, `--actor space-chassis`) and by
  message (`../coordination.md`). The SHA posted on the issue is the only one that counts.

## Memory

The session's durable notes are in `~/.claude/projects/-home-john-space-chassis/memory/`. The
project memory `space-harness-is-aurora-port` tracks where the port stands.
