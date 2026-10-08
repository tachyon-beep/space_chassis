# SV-024 Astra independent review

**Changes needed.** The inherited-segment fix closes the reported checkpoint/A15 trace, and the new namespace model provides useful integrated O2-5 evidence. One remaining mixed-restart trace can nevertheless strand a recoverable torn header behind a durable RECOVERING intent. SV024 is not accepted until that dependency is closed.

Reviewed immutable head `d94bc78e3cf69daec028b43fee180f88e559897d`, runtime/tests `0ac2245fc93032146a1fc19060ece18276ce9157`, against accepted `8bffe49ecf546d8581fb6e34bff6eb9e096d8841`. Inputs included immutable implementation/tests/STATUS/RECEIPT, the frozen 35-case manifest and target preflight, canonical v2 §§1.1/1.4.8/1.4.10 and O2-5, and the external final receipt. Static review only: no tests, imports, provider calls, moving-tree inspection or runtime changes. This report is the only written output.

## SV024-01: reported checkpoint defect closed

`LedgerWriter.continue_after` now marks existing readable segment bytes as inherited (`services/chassis_persistence.py:1201`). `sync_inherited` at 1302 fsyncs the open segment and clears the flag only after success. A successful append fsync also clears it. `Session.checkpoint` at `services/chassis_session.py:573` calls the fence before serialization/install/CK5; `open_segment` at persistence line 1215 calls it before leaving the inherited segment.

For the reported sequence—readable unsynced rotated header, restart, CK5 publication, interruption before CK6 sync—the new fence protects the header before run.json names its sequence. The discriminator at `tests/test_chassis_namespace.py:365`, variant `at-its-checkpoint`, carries the original file/name watermarks and checks that host loss preserves the header, drops the uncommitted checkpoint, and leaves covers_seq no greater than the ledger end. The reported pre-fix 42-versus-41 A15 failure is consistent with the old ordering.

On a new fence error `_fail` breaks the writer and attempts FSYNC_FAILED; checkpoint/rotation route that failure through the session boundary before dependent writes/effects. The static ordering is sound. The selected failed-namespace tests exercise directory fences, rather than an EIO at the newly added inherited-file fence; a focused failure assertion at that new boundary is useful when validating the correction below.

## SV024-02 — P2: RECOVERING can become durable before the unfenced torn header it names

**Location:** `services/chassis_startup.py:1008`–1026, especially the durable intent write at 1024 before `quarantine_tail` and before `continue_after` at 1043. Failure appears at `_from_intent`, lines 1132–1137.

**Concrete M-1 → M-1 → M-2 trace after actual collection:**

1. Use the same completed GC root. Rotation creates segment n+1. Its header write stores a short prefix (for example the existing 30-byte TC1 shape), then the process dies during the write. Neither its file fsync nor ledger-directory fsync has returned. The previous segment still ends at durable GC_DONE; the new name and fragment are only readable. M-1 explicitly permits an in-flight write to leave a prefix.
2. Restart with the original name and byte watermarks. The scanner sees TC1 in n+1, with P ending at the old GC_DONE. `_recover` writes and fences RECOVERING containing that old anchor and the new segment number, offset zero, fragment hash and length.
3. Kill this restart immediately after RECOVERING's session-directory fence, before the fragment's quarantine copy is durable. No ledger-directory fence or source-segment file fsync has occurred: `continue_after` is later, and `write_bytes_durable(RECOVERING)` fences session/, not ledger/ or the segment data.
4. Simulated host loss removes the unfenced n+1 name. The durable RECOVERING survives. The following scan correctly sees TC0 at the old GC_DONE, but `_from_intent` finds neither its original fragment nor its not-yet-written corrupt/ copy and stops `recovery_intent_copy_missing`. There is no supported resolution. The effect-free rotation that should be recoverable has become a permanent diagnostic stop.

Keeping the name while dropping its unsynced fragment yields the same missing-copy dependency. No arbitrary garbage, truncation reversion, rename reversion, provider effect or hostile modification is needed. This is within the integrated torn-header/mixed-restart scope, not a request for a broader persistence audit.

**Why the 22 cases miss it:** the torn-header case first applies a simulated host loss with `keep/torn`, then creates a fresh NameOps model (`namespace.py:316,338–341`); that surviving fragment/name is legitimately the post-host-loss baseline. The second-restart matrix starts from a *complete* unsynced header (`365–370`) and never enters the torn-header RECOVERING path. Neither carries an M-1 partial header through a second interrupted recovery and then loses its name. Receipt §9's untraced recovery-intent caveat does not resolve this concrete counterexample.

**Bounded correction:** establish durable recoverability of every input a published RECOVERING depends on before publishing it. For this witness, preserve the original segment's exact fragment bytes and required namespace fences first, or make a pre-admitted durable quarantine copy available first while separately preserving the prefix anchor. Keep the existing copy-before-truncate rule, admission cap, exact hash validation and no-effect recovery semantics. If a pre-intent fence/copy fails, take the persistence boundary before durable intent publication or truncation. Do not silently discard an unmatched intent or guess its missing tail.

**Discriminating regressions:** add a small partial-write injector for the new header, not a host-loss setup that promotes the fragment to the durable baseline. Assert its file watermark remains zero and its name remains unfenced after the first process death. Carry both into the recovery, cut immediately after the intent becomes durable, then apply (a) name loss and (b) kept name/data loss. Restart twice. Require convergence, exact retained fragment evidence once it has become a durable dependency, contiguous seq/chain, unchanged checkpoint/identity/state, no repeated collection and no requests/tools. Add a pre-intent persistence-error control proving no truncation or dependent publication, and retain the existing checkpoint/A15 discriminator. A source mutation or the current immutable runtime should expose the missing dependency in these new fixtures. All can remain in bounded temporary-root nodes.

## Model, retained guarantees and evidence assessment

NameOps correctly separates file-byte watermarks, created-name fences and unlink fences for its declared slice. `inherit()` shares the evidence maps across process death; opening an already tracked segment uses `setdefault`, preserving an existing zero watermark. A file sync does not protect an unfenced name, while a returned directory fence does not promote unsynced file bytes. After a simulated host loss, the surviving on-disk image is reasonably treated as the next durable baseline. The model's lack of rename/truncation-reversion simulation is explicit; neither is needed for SV024-02.

The integrated assertions verify physical prior collection, nonzero oldest segment, old-end TC0 after name loss, recreated sequence/chain, exact new records, checkpoint/identity preservation, no recovery effects and no repeated GC. The completed-fence case uses a real local callback gated by REQUEST_SENT and checks its surviving gate, one possible-spend transition and next attempt. The ineffective-fence control and reported restored source mutation distinguish a vanished effect gate. Previous-base cases invoke the retained A14 oracle on the actual retained tuple. No previous-base selection, GC reference union, deletion authority or acknowledgement policy is changed by the patch.

The external receipt reports **58 selected passes in seven serial commands: 35 retained, one conditional recorder/chassis process case, and 22 new**. The conditional selection is justified by the checkpoint change before the real script's first request. I did not rerun them. Namespace crashes are in-process fault injection, and host/name/byte losses are simulated; actual separate-process evidence comes from the conditional local recorder/chassis test, which does not simulate name loss. These results establish the enumerated cases, not every recovery composition.

## Acceptance boundary

Preserve SV024-01, close SV024-02, publish the bounded regression evidence and submit an immutable correction for review. No broad suite or new policy choice is required. SV025 remains preflight only and cannot launch on an assumption of SV024 acceptance.

Real power-loss/storage evidence, unsimulated reversion cases, exact replay bounds, broader bootstrap/lost-ledger resolutions, real-session operations, merge/deployment, providers and H/T/Q/pump work remain outside acceptance. The fact that a general recovery-intent dependency was previously unclaimed does not exempt the now-concrete O2-5 mixed-restart failure.
