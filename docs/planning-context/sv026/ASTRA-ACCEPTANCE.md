# SV-026 independent Astra implementation review

**Decision: accept the bounded SV026 implementation. No blocking correction is required. This is not acceptance of any numerical replay guarantee.**

Reviewed immutable head `a17115f89b3775ca0a34cd759be79bd1fe38c9e3`, runtime/test commit `b08830e4ce98f71fbb3b07a23f32bc391d08f030`, against accepted launch base `190a57f7cfb4227c847ba1e92b7d0ab914384a2c`. The difference between the runtime/test commit and reviewed head is only `docs/planning-context/sv026/{RECEIPT,STATUS}.md`. Review used static Git objects, canonical SV013/SV015v2 source, the accepted SV026 design and launch qualifications, and the supplied execution receipt. No tests, project imports, provider calls, runtime edits or real-session operations were performed by this reviewer.

## Implementation assessment

The five-service change implements the accepted C1–C14 architecture and preserves its expressly limited quantity. It does not redefine the canonical physical replay bound as a smaller, allegedly proved number.

| Area | Static assessment and discriminating evidence |
| --- | --- |
| Blob outcomes | `chassis_persistence.py:923–941,1087–1121` reports the existing read's obtained bytes without a second payload read. Accepted data, wrong-hash data and the over-limit probe retain their measured cost; missing/bad-name reads are zero; an I/O error whose amount is unknown returns `obtained=None`. `get` retains its bytes-or-None behavior. The DONE regressions distinguish 5,000 valid bytes, 15,000/2,500 wrong-hash bytes, a 1,001-byte injected-limit probe, missing data and unknown EIO, while preserving the lost-result semantics. They do not assume a damaged file remains within CAP_RESULT. |
| Reducer accounting | `chassis_replay.py:277–323,387–396` routes reducer blob reads through one measuring helper and charges successful applications by actual frame length plus obtained bytes. Retained-only originals and foreign note adoption do not acquire fictitious reads. Unknown amounts are counted separately. Legacy bytes-reader construction remains supported; production selected replays use the richer fetch interface. |
| Lifetime versus interval | `chassis_session.py:232–270,684–690` adds per-apply lifetime deltas and resets only the session interval after a committed checkpoint. It neither resets the reducer lifetime total nor re-adds that total at later commits. The reset tests explicitly distinguish lifetime work from the new interval; post-GC live/restart controls include GC records and headers. |
| Origin and headers | C_n's own frame, or genesis header seq 1 before the first checkpoint, is the interval origin. Other headers are charged. The writer claim is published only after the existing file and directory fences return (`chassis_persistence.py:1242–1286`), consumed at session construction and after rotation, and added to the selected replay totals rather than overwritten. Tests cover genesis, pre-first-checkpoint rotation, a reused empty segment, restart parity, and a header-dependent threshold crossing. Existing inherited-byte and namespace fence ordering is retained. |
| Selected recovery | `chassis_startup.py:1026,1083–1147,1190–1306` measures the selected replay, includes already-readable transaction extras exactly once, then adds newly committed closure records. The older previous-base interval runs on a separate instance; it is not incorrectly carried into the newest suffix counter. The former positional `_classify_base` bytes-reader contract is preserved, with the new fetch interface keyword-only. Repeated restarts, a previous-base reconstruction and an interrupted recovery prefix have discriminating tests. |
| Startup publication | The new threshold check follows `_finish_case`, required extra-record syncs, carrier/RECOVERING retirement in the existing order, and durable IDENTITY coverage (`chassis_startup.py:1123–1147`). It therefore does not put an unplanned checkpoint under a frozen recovery intent. The after-intent test checks retirement fencing before checkpoint installation and identity coverage, without demanding an unnecessary IDENTITY rewrite. Existing acknowledgement, intent-sync and missing-prefix guards remain in the retained selection. |
| Closed units | Startup, each note generation, file-edit adoption and both note-drop routes now evaluate thresholds. The group/queue guards remain effective. Per-generation tests inspect the checkpoint's adopted watermark and remaining pending list, then resume without duplicate adoption. The new check-only boundaries retain the reviewed R-D rotation deferral. |
| Startup callback | `chassis.py:1023–1041,1284–1305` supplies the list actually being installed to the metadata callback before `Chassis.session` is assigned. The extracted `_open_session` retains production wiring. CB uses the real Chassis callbacks, sees `session is None`, and asserts context tokens for the recovered list, legacy metadata keys, no ended field and no client request. |
| G2 follow-up | `chassis_session.py:628–745` reports collection success only after GC_DONE and its existing pruning. Exactly one non-collecting follow-up is permitted when that GC unit crosses a threshold. It retains `ended`, returns the final checkpoint, and rotates only after the final checkpoint. It does not change collection eligibility, reference selection or deletion authority. |

The implementation does not alter the durable intent/carrier/IDENTITY schemas, the previous-base preservation rule, replay outcomes, external-edit policy, GC plan validation, or the live request/effect gates. The new checkpoint placements occur after the reviewed closure and durability conditions.

## Test and crash evidence

The new oracle is usefully independent of the runtime counter. `tests/test_chassis_accounting.py:73–150` logs read attempts at the filesystem adapter, attributes them to `Replay.apply` sequence numbers, and obtains frame lengths from the separate byte walk. For the over-limit fixture it measures the static file size capped at `limit+1`, rather than reading the runtime's `obtained` field. The fixtures label injected thresholds/read limits. These are finite selected-work measurements, not a total-startup I/O meter or a concurrent-file-mutation model.

The G2 crash fixtures implement the launch qualification precisely: one cut is before the second install and the other is **before writing the follow-up CHECKPOINT frame after CK5**. They require the follow-up frame to be absent; reconstruct the outstanding GC pair; require replacement checkpointing without inherited `ended`; forbid repeating unlinks from the spent intent; bound replacement checkpoint/collection counts; and verify subsequent A14 recovery including its normal notice. They allow A9 or A10 rather than imposing A10 on an unchanged conversation hash. The fence-failure control requires FSYNC_FAILED, no follow-up frame, no later RUN_END, and A1 on restart. These are simulated process/failure cuts in temporary roots, not new real-host power-loss evidence.

The SV025 changes are justified behavior updates, not deleted counterexamples:

- The former restart-accounting counterexample now asserts `(2, 12,428)` carried across restart and checkpointing at the fourth unit.
- The 27 MiB external-edit witness now dies at CK2 entry after the edit is durable but before the threshold checkpoint writes a frame. The following start still reads the 28,311,552-byte suffix blob, exceeding 25,166,144 bytes, before checkpointing. The test captures the old C_n before that start changes the checkpoint.
- The retained older-previous-base witness still establishes 730 records versus the proposed 717 bound. Its since-checkpoint assertion changes only to respect the accepted origin convention.

The supplied `results/SV-026-implementation-test-receipt.json` contains 35 development/final commands. Its final 12 outputs have no error flag and contain dot counts `30,16,8,24,24,16,8,6,11,2,8,8`, totaling **161 selected cases: 48 new, 16 bounds, 97 retained**. The final source/test bytes are the reviewed runtime/test commit. I inspected the assertions and receipt; I did not independently execute these commands.

The receipt appropriately distinguishes the original counterexample pass, nine pre-fix behavioral failures and the staged callback failure at **0 versus 6,100**, from the final passing selection. P4/P5 are combined reconstruction/read-cost discriminators, not isolated mutations of the read-cost mechanism. The wrong checkpoint-origin fixture and temporary private-reader API regression are disclosed and corrected. The final relevant selection follows the last runtime edit. No broader or conditional suite execution is inferred from these counts.

## Scope of acceptance and remaining obligations

This accepts the reviewed engineering repair and bounded evidence on the isolated WIP. It does not authorize real-session deletion or acknowledgement, provider activity, merge, deployment, or a new H/T/Q/pump/history policy.

The following remain explicit limitations, not closure claims:

- `T_origin`: the physical checkpoint/genesis frame is outside this since-origin trigger counter and remains a term in any eventual physical replay proof.
- Only the selected successful replay interval is charged. Scanner reads, base files, older previous-base reconstruction, verification/planning reads and abandoned candidates are not a global I/O guarantee.
- `since_unmeasured` records unknown partial I/O; its missing byte amount is not covered by the byte threshold. A completed checkpoint resets that interval marker along with the other counters.
- R-D: the new check-only boundaries can defer rotation until an existing rotation point. Segment overshoot/read slack is not proved.
- Changed damaged-blob sizes, repeated CK4–CK6 ADOPT accumulation, the older previous-base span and admitted large external edits remain relevant to the unresolved proof/contract work.

None of the four canonical §1.4.7 inequalities, U_r/U_b, RSS, latency or total startup I/O is proved by SV026. The two retained exact SV025 counterexamples continue to refute the corresponding bounds. Constants, source generators and golden oracles remain unchanged. Further numerical closure needs its own explicit design/source decision where the current admitted behavior contradicts the proposed bound; this acceptance supplies no such decision.
