# SV029 independent Astra implementation review

**Decision: accept the bounded test/evidence package. No blocking correction is required.** The inspected fixtures and supplied execution evidence establish the two stated default-current-runtime counterexamples and their controls. Acceptance is evidence against the exact numerical claims; it is not a replacement guarantee or permission to change the runtime or contract.

Reviewed immutable head `4bd07c01f6f64aacf60353e853698461acce56e7`, tree `20d447b562d11c8971d77b81f1e43fc7a06e395c`; test commit `8b2e5856607b3de5f1459966d5602dff5cb68bf8`; accepted design base `7224b36fb4ae343aa5273eeeed1a93a3d3149d3b`. The base-to-head diff contains only the new `tests/test_chassis_replay_residual.py` and `docs/planning-context/sv029/{DESIGN,STATUS,RECEIPT}.md`. The test-commit-to-head diff is documentation only. Runtime services and all existing tests/helpers are unchanged.

Review was static: immutable Git objects, governing L1–L6, relevant accepted runtime/helper paths and `results/SV-029-implementation-test-receipt.json`. I ran no tests, collection, project imports, providers or workers and made no repository edits. This report is the only written output.

## Counterexamples and discrimination

| Quantity | Accepted evidence in this package | Control |
|---|---|---|
| Previous-base bytes `< 50,352,266` | Final A14 reads 56 distinct 1 MiB message blobs: **58,720,256 bytes**, already **8,367,990** beyond the strict limit before edit blobs or frames. C₇.prev still names A. | Omitting the second edit lets C₂.prev name C₁. A14 opens only round 2's eight message blobs: **8,388,608 bytes**, with frames-plus-blobs below 25,166,144. |
| Newest-base records `≤ 358` | After one checkpoint-frame interruption and 108 edited starts interrupted at checkpoint-install entry, the final start applies **365 records after B's own checkpoint frame**, or 366 including it. | With no later external edits, repeated install-entry interruptions add nothing after the first adoption; replay stays at **257** non-origin records. |

These are finite histories at the current default constants. They are not proofs about all histories or all possible schedules.

### Previous-base bytes: reachable construction and independent returned-byte attribution

`message_round` (`tests/test_chassis_replay_residual.py:71–115`) uses real startup, real direct-message admission and the unchanged session writer. It checks each actual text's UTF-8 and escaped lengths, its content hash and the resulting blob reference. The first seven messages leave the checkpoint unchanged; the eighth is immediately followed by the automatic checkpoint, with only possible GC records afterward. Threshold comparisons use independently walked frames and known actual blob sizes, not the session's counters.

The main fixture (`:135–190`) proves that every round's checkpoint names A's exact tuple, the previous file remains A, no extra checkpoint or rotation header is introduced, and all 56 message blobs and seven edit blobs have distinct identities. Collection is enabled without bypassing its real retention logic. The accepted reference union after A's cover preserves the necessary span.

`damage_and_recover` fixes its byte-walk endpoint before damaging the current file and opening A14 (`:118–129`). The observer returned by `watch()` is the same object used for reads. Applied sequences through that endpoint must equal the entire ordered range after A's cover, once each. The main fixture separately requires 63 raw returned blob calls, 63 names and 63 applying sequences; it checks the exact name set and each returned length. Raw bytes must equal both the logical and distinct sums. This closes the existing helper's potential deduplication ambiguity: a set/dictionary total alone would not have established once-only replay.

Every checkpoint frame in the observed previous-base interval is included in the walked total. The primary contradiction is stronger than any disputed frame convention because the message blobs alone exceed the bound. The per-round threshold interval calculation uses the accepted since-origin convention; it is not presented here as a new physical replay theorem.

The A14 result also verifies the final messages plus the normal notice, restoration of C₇'s bound conversation hash, preservation of A, and a current since-byte counter below the threshold. That last assertion establishes the separation from the older interval's work; it does not convert that counter into a global I/O measure. N2 (`:193–221`) uses the same machinery and proves the actual changed previous tuple and the smaller returned-read set, so its control is not merely a smaller arbitrary input.

### Newest records: semantic cuts, base identity and exact core deltas

The initial fault wrapper matches the real CHECKPOINT frame header and raises before writing it (`:230–242`). The prefix helper (`:269–300`) establishes B normally, closes that session, starts A9, then appends 256 inline messages. It requires exactly one fault, checkpoint-entry count 256, no checkpoint/header after B, the installed enlarged conversation, B's bytes in `.prev.json`, and CK5 metadata covering the last actual message. These assertions discriminate the intended CK6-before-write state from a setup failure or a different crash cut.

`measured_start` (`:303–339`) captures the entry endpoint and files first. Every dying attempt reaches the real `cp.install_conversation` call once and fails at its entry, before installation work. The conversation files and run metadata must stay unchanged across that attempt. The fixture closes every writer opened by an abandoned start using a pass-through wrapper around the real `continue_after`; normal sessions and the prefix session are also closed. The probes record classification and counters while calling the unchanged implementation.

Each measured start requires B's bound bytes and the exact ordered apply sequence from B.seq through the original endpoint, with no earlier applications and no header. This identifies a newest-checkpoint replay even though the matching bytes are physically in the file named `conversation.prev.json`. It does not accidentally measure reconstruction from the older checkpoint named by B.prev.

N3 (`:342–373`) checks the full L1 table: first A10 adds exactly one `conversation_adopted` record and reaches 257; edited starts j = 2…109 add exactly one EXTERNAL_EDIT and reach j + 256; the final unchanged A9t reaches checkpoint entry at 365, adds no core and commits the first new checkpoint. The independent entry count excludes all records created by that start. The final ledger interval is exactly 256 messages, one adoption and 108 edits. Counters reset to zero afterward, no group remains, and no quarantine directory exists. N4 (`:376–393`) proves that the unchanged-file attempts add zero records and remain at 257. It does not claim a bound for every single-interruption history.

## L1–L6 and provenance

All mandatory launch qualifications are satisfied within the reviewed scope: corrected per-start deltas; independent read multiplicity and base attribution; real semantic cuts and writer cleanup; corrected cumulative-resource estimates without raised caps; exactly four new and eight retained explicit nodes without collection; and calibrated claims in the current documentation. The constants remain the accepted defaults: 256 records, 8 MiB recovery bytes, 1 MiB direct messages and the unchanged default admission/segment settings. The new module changes only test-local observation and fault hooks, not admission, thresholds, caps or the expected canonical inequalities.

The supplied coordinator receipt records exactly two serial final commands, returning four and eight pass dots, with no failed attempt, retry, cap hit or denial. The last test edit is event 34, before the first test command at event 38; subsequent edits are documentation. It also records 47 baseline service/test files unchanged. The immutable diff independently confirms that the sole test change is the new file.

I verified all four immutable file hashes against the receipt. The new test's SHA-256 is:

`8366e4b372dcae17ab8b93420d6d65e40c6e56c53c826f4203c13648dc56657e`

The numerical values above follow from inspected assertions backed by the reported successful executions; the runner printed only pass dots. There are no independently printed timing, RSS or I/O measurements. The 280 MiB build-plus-final message-blob estimate is kept separate from N1's final recovery quantity. The tests simulate interruptions in process; they are not actual subprocess restart or host-loss evidence.

## Acceptance boundary and remaining obligations

Together with the retained SV025 counterexamples, this closes the residual evidence question for the four exact canonical replay rows on the accepted implementation: none can be claimed as a general guarantee. It does not establish a replacement bound, `U_r`/`U_b`, PR-N, origin-frame treatment, total startup I/O, partial-I/O cost, segment-read slack, RSS or latency. It does not require rerunning earlier counterexamples merely to repeat their accepted evidence.

No runtime/source/oracle change, real-session operation, provider use, merge, deployment or held H/T/Q/pump/history/previous-file choice follows from this acceptance. Further analysis remains engineering work; changing guarantees, premises or accepted behavior requires its concrete contract/design review. The separately saved next-obligation review is a planning aid for segment readability under interrupted checkpoints, not an implementation launch or a reopened defect in the already accepted SV027 placement package.
