# GitHub WIP backup status

This branch is a durability checkpoint, not a merge or deployment approval. John explicitly authorized GitHub backup on 2026-10-07. The coordinator verified the existing origin as `https://github.com/tachyon-beep/space_chassis.git`, with main at `fa43b25b0fd7d88a3f5e7feb3338e190078517ce`, and uses the dedicated branch `wip/sv-recorder-opus-20261008`. No force push, hook bypass, main update or deployment is authorized by this backup.

## Included work and acceptance

- SV016 accounting, strict parsing and outbound transport/header boundary: accepted at `afec0a8aab81237c6c09ef55ecf9cd205494d3f6`; independent final review is `sv016/ASTRA-ACCEPTANCE.md`.
- SV017 transcript custody: accepted at `11e0e26fd5e3e78f2b05f383a2493ef8cd8f1547`; independent final review is `sv017/ASTRA-ACCEPTANCE.md`. Final selected set at that point: 121 passed.
- SV018 deadline/resource bounds: accepted after corrections at `055345d1cd3d13845ffc12b9834787b17d67d23d`; independent final review is `sv018/ASTRA-ACCEPTANCE.md`. Final selected recorder set: **209 passed**, with three deliberate SystemExit warnings. All four Astra findings are closed. Acceptance remains conditional on the documented commissioning assumptions.

- SV019 staged chassis metadata, clean-flap behavior, typed termination, pure wire helpers and outgoing group repair: accepted at `2f0567c1e1aaa0ca900adfa5f4ce1eaa40a783a9`; independent final review is `sv019/ASTRA-ACCEPTANCE.md`. Final selected set: **161 passed**, plus **five local-stub integration checks**, no warnings. Ledger activation, notes adoption and full response-envelope adoption remain staged out.

- SV020 inactive persistence foundation: accepted at `8b897931be6986e2da9a299c63060d0925a817f3`; independent final review is `sv020/ASTRA-ACCEPTANCE.md`. Final selected set: **114 passed**. All three Astra findings are closed. Live authority/checkpoint/replay and mutation integration remain SV021 work.

The coordinator last verified remote checkpoint `b84a4bbef7b07b7dd36b6a7ebf6b6ef4fd0a8aa1`, tree `704fe01a54cc96f31c1f290851d8e927db051bc9`. Implementer statements that nothing was pushed refer to that worker's actions. This documentation update is prepared for a subsequent normal fast-forward backup; its creation does not claim that later remote verification has completed.

## Evidence and exclusions

Opus 5.5 implemented the changes; OpenAI Astra independently reviewed immutable commits. Package receipts retain source hashes, exact test scope and known limits. Original uploaded design dossiers, credential/account material, private raw logs, runtime transcripts, unrelated user files and temporary generated data are not part of this backup. The original project checkout's dirty vehicle submodule and untracked planning directory remain untouched.

Full repository testing, live-provider/TLS interoperability, real storage faults/power-loss evidence and deployment have not been completed. User-authorized bounded checks supersede the general full-suite-before-commit instruction for this phase. The Filigree store was read-only, so committed local ledgers provide tracking. No history/H/T/Q product-policy choices or held vehicle/pump recovery protocols are adopted.
