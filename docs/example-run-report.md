# Endurance run: ten_agents

Verdict: **pass**

## Totals

- agents: 10
- turns: 427
- runs: 484
- ladder tiers reached: [1, 2]
- recap folds (conversation fell out of a window): 427
- handoffs: 824
- recorded refusals: 0
- injuries injected: 14

## Model

- requests: 427
- turns: 412
- faults served: {'transient': 9, 'malformed': 4, 'no_model': 2}

## Per agent

| agent | turns | runs | resumed | fresh | max tier | folds | handoffs | refusals | diary |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| agent_1 | 40 | 44 | 40 | 0 | 2 | 40 | 78 | 0 | 82b |
| agent_2 | 39 | 45 | 39 | 0 | 2 | 39 | 76 | 0 | 165b |
| agent_3 | 58 | 65 | 58 | 0 | 2 | 58 | 116 | 0 | 248b |
| agent_4 | 35 | 41 | 35 | 0 | 2 | 35 | 66 | 0 | 165b |
| agent_5 | 25 | 29 | 25 | 0 | 2 | 25 | 46 | 0 | 82b |
| agent_6 | 43 | 50 | 43 | 0 | 2 | 43 | 84 | 0 | 414b |
| agent_7 | 43 | 45 | 43 | 0 | 2 | 43 | 82 | 0 | 82b |
| agent_8 | 28 | 34 | 28 | 0 | 2 | 28 | 52 | 0 | 82b |
| agent_9 | 66 | 73 | 66 | 0 | 2 | 66 | 128 | 0 | 247b |
| agent_10 | 50 | 58 | 50 | 0 | 2 | 50 | 96 | 0 | 413b |

## Checks

- PASS — every agent took turns: turns per agent: [40, 39, 58, 35, 25, 43, 43, 28, 66, 50]
- PASS — turn volume reached the scenario's floor: 427 turns against a floor of 60
- PASS — the ladder's tiers were exercised: expected [1, 2], reached [1, 2]
- PASS — runs outlived turns: 484 runs across 10 agents, floor 30
- PASS — runs continued after code was rewritten: every agent that had code restored still produced runs
- PASS — handoffs were used: 824 handoff(s), floor 10
- PASS — no run gave up on the whole fleet: no agent reached the give-up rung
- PASS — refusals stayed within the scenario's budget: 0 recorded refusal(s), allowed 40

## Injuries

- 2026-09-11T18:39:19.769788Z bad_code on agent_3: wrote an unparseable duty.py (backup at .duty.py.injected-backup)
- 2026-09-11T18:39:34.343050Z crash on agent_4: Traceback (most recent call last):
  File "/home/john/space_chassis/endurance/inject.py", line 149, in <module>
    sys.exit(main(sys.argv))
             ^^^^^^^^^^^^^^
  File "/home/john/space_chassis/endurance/inject.py", line 144, in main
    print(handlers[injury](root, slug))
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/john/space_chassis/endurance/inject.py", line 60, in crash
    fo
- 2026-09-11T18:39:48.772422Z bad_code on agent_4: wrote an unparseable duty.py (backup at .duty.py.injected-backup)
- 2026-09-11T18:40:00.440743Z bad_code on agent_3: wrote an unparseable duty.py (backup at .duty.py.injected-backup)
- 2026-09-11T18:40:14.884278Z corrupt on agent_9: corrupted /tmp/sc-g9q9fl03/w/home/agent_9/session/conversation.json
- 2026-09-11T18:40:29.535978Z crash on agent_6: Traceback (most recent call last):
  File "/home/john/space_chassis/endurance/inject.py", line 149, in <module>
    sys.exit(main(sys.argv))
             ^^^^^^^^^^^^^^
  File "/home/john/space_chassis/endurance/inject.py", line 144, in main
    print(handlers[injury](root, slug))
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/john/space_chassis/endurance/inject.py", line 60, in crash
    fo
- 2026-09-11T18:40:44.409482Z corrupt on agent_1: corrupted /tmp/sc-g9q9fl03/w/home/agent_1/session/conversation.json
- 2026-09-11T18:40:56.219505Z bad_code on agent_8: wrote an unparseable duty.py (backup at .duty.py.injected-backup)
- 2026-09-11T18:41:11.031056Z unrecoverable on agent_1: refusing agent_1 for 20 seconds (refuse-agent_1.marker)
- 2026-09-11T18:41:26.054849Z crash on agent_8: Traceback (most recent call last):
  File "/home/john/space_chassis/endurance/inject.py", line 149, in <module>
    sys.exit(main(sys.argv))
             ^^^^^^^^^^^^^^
  File "/home/john/space_chassis/endurance/inject.py", line 144, in main
    print(handlers[injury](root, slug))
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/john/space_chassis/endurance/inject.py", line 60, in crash
    fo
- 2026-09-11T18:41:41.585761Z unrecoverable on agent_6: refusing agent_6 for 20 seconds (refuse-agent_6.marker)
- 2026-09-11T18:41:56.718061Z unrecoverable on agent_4: refusing agent_4 for 20 seconds (refuse-agent_4.marker)
- 2026-09-11T18:42:03.785418Z corrupt on agent_4: corrupted /tmp/sc-g9q9fl03/w/home/agent_4/session/conversation.json
- 2026-09-11T18:42:10.421928Z crash on agent_7: Traceback (most recent call last):
  File "/home/john/space_chassis/endurance/inject.py", line 149, in <module>
    sys.exit(main(sys.argv))
             ^^^^^^^^^^^^^^
  File "/home/john/space_chassis/endurance/inject.py", line 144, in main
    print(handlers[injury](root, slug))
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/john/space_chassis/endurance/inject.py", line 60, in crash
    fo

## What this does not show

The model in this run was a metronome, not a model. A passing verdict says the
machinery around a fleet survives being run hard: it does not say anything about
how an agent would fly the vehicle.
