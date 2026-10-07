"""SV-023: `continue-from-bound` for the two witnessed file-repair stops (A14 and CK5).

Evidence kinds, kept apart:

* **In-process simulation** (most of this file), on temporary roots, as in
  `test_chassis_recovery_live` and `test_chassis_gc`. A "crash" raises `Crash`
  before an injected filesystem call -- process death: completed calls stay
  (M-1) -- and a "restart" calls the command or `open_session` again. Host
  loss (M-2) is only *simulated* by `host_loss`: segment bytes that no
  returned fsync covered are cut back, and renames and unlinks that no
  returned fsync of their directory covered are undone. Each restart carries
  the previous process's watermarks (`AckOps(previous)`), so readable bytes
  are never promoted to durable by being read again (the SV022-01 rule).
* **One real CLI restart section** (`test_cli_*`): the real recorder (conftest
  `Stack`), a local stub upstream and real `services/chassis.py` processes,
  including the actual `--acknowledge-stop ... --resolution
  continue-from-bound` command.

Every repair is an explicit fixture action: the damaged bytes are first copied
to the fixture's own `archive/` (outside session/), then the target file is
replaced by bytes the fixture saved before damaging it. The runtime never
repairs anything. Not a power-loss, kernel or storage experiment; no
provider; no real session.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import chassis_persistence as cp
import chassis_replay as rp
import chassis_session as cs
import chassis_startup as st
import pytest
from test_chassis_durability import Crash
from test_chassis_gc import HEADER, CutOps, collect_with, collection_ready, note, segments, tool_turn
from test_chassis_gc import begin as gc_begin
from test_chassis_gc import start as gc_start
from test_chassis_recovery_live import BASE, LINEAGE, UNRUN, Root, T, establish, partial_turn

A14, CK5 = "conversation_unreadable_unbound", "run_json_unreadable"
RESOLUTION = "continue-from-bound"
LONG = "L" * (cs.INLINE_TEXT_BYTES + 1)
KINDS = {"a14": A14, "ck5": CK5}
TARGET = {"a14": "conversation.json", "ck5": "run.json"}
DAMAGE = {
    # A14 needs neither conversation file usable (no bound base, no previous base).
    "a14": {"conversation.json": b"\x00not a conversation", "conversation.prev.json": b"\x00not one either"},
    "ck5": {"run.json": b'{"format": 2, torn'},
}
SUPPORTED = {
    ("ledger_tail_ambiguous", "continue-conservative"),
    ("fsync_failed_previous_run", "continue-from-bound"),
    ("corrupt_quarantine_full", "continue-from-bound"),
    (A14, RESOLUTION),
    (CK5, RESOLUTION),
}


# ---------------------------------------------------------------------------
# Durability model: CutOps (segment bytes, crash points) plus directory names
# ---------------------------------------------------------------------------
class AckOps(CutOps):
    """CutOps, plus the names M-2 lets a host loss take back: renames and unlinks no directory fsync covered.

    `AckOps(previous)` carries another process's watermarks across a process
    death: a restart starts from what was *durable*, not from what it can read.
    """

    def __init__(self, previous: AckOps | None = None) -> None:
        super().__init__(durable=previous.durable if previous is not None else None)
        self.names: dict[str, list] = {d: list(e) for d, e in previous.names.items()} if previous is not None else {}

    def rename(self, source, target):
        self._step("rename", target)
        before = Path(target).read_bytes() if Path(target).is_file() else None
        cp.DurableOps.rename(self, source, target)
        self.names.setdefault(str(Path(target).parent), []).append((str(target), before))

    def unlink(self, path):
        self._step("unlink", path)
        data = Path(path).read_bytes() if Path(path).is_file() else None
        cp.DurableOps.unlink(self, path)
        if data is not None:
            self.names.setdefault(str(Path(path).parent), []).append((str(path), data))

    def sync_dir(self, path):
        self._step("sync_dir", path)
        cp.DurableOps.sync_dir(self, path)
        self.names[str(path)] = []

    def abandon(self) -> None:
        """The dead process's descriptors go with it."""
        for fd in list(self.paths):
            with __import__("contextlib").suppress(OSError):
                os.close(fd)
        self.paths.clear()


def host_loss(ops: AckOps) -> None:
    """Simulated M-2: unsynced segment bytes are lost; unfenced renames and unlinks are undone, newest first."""
    for path, size in ops.durable.items():
        if os.path.exists(path) and os.path.getsize(path) > size:
            os.truncate(path, size)
    for directory, entries in ops.names.items():
        for path, before in reversed(entries):
            if before is None:
                Path(path).unlink(missing_ok=True)
            else:
                Path(path).write_bytes(before)
        ops.names[directory] = []


# ---------------------------------------------------------------------------
# Fixtures: an actual stop, an explicit repair, the expected resumption
# ---------------------------------------------------------------------------
@dataclass
class Stopped:
    root: Root
    kind: str
    reason: str
    saved: bytes  # the target's verified checkpoint bytes, kept by the fixture before damaging it
    messages: list  # memory the bound replay and its closure must give
    state: dict  # every non-history fact, in the checkpoint wire form
    next_turn: int
    witness: dict
    effects: tuple  # (REQUEST_SENT, INVOKING) counts at the stop

    @property
    def session_dir(self) -> Path:
        return self.root.session_dir

    @property
    def archive(self) -> Path:
        return self.root.path / "archive"

    def acknowledge(self, ops=None, reason=None, resolution=RESOLUTION):
        return st.acknowledge(self.session_dir, reason or self.reason, resolution, **({"ops": ops} if ops else {}))


def effects(root: Root) -> tuple:
    types = root.types()
    return types.count("REQUEST_SENT"), types.count("INVOKING")


def wire(state: rp.SessionState) -> dict:
    return state.to_wire(next_seq=1)


def receipts(root: Root) -> list:
    return [r.payload for r in root.records() if r.type_name == "RECOVERY_ACK"]


def build(root: Root, *, suffix: str = "partial", start=None):
    """C_n with a pending note, then a suffix; returns (next turn, expected memory, state wire)."""
    session = establish(root) if start is None else start
    session.write_note("N1", header=HEADER)  # a pending generation: its blob is in blobs_live
    partial_turn(session, 6)
    session.checkpoint()  # C_n
    closure = []
    if suffix == "partial":
        session.append_message("user", LONG)  # a suffix record whose text is a blob replay needs
        partial_turn(session, 4)  # request, response (2 calls), call 0 invoked and done, call 1 never invoked
        closure = [T("call_b", "write_file", UNRUN)]
    else:
        session.append_message("user", "after the checkpoint")  # nothing to close
    next_turn = session.state.requests_next["turn_seq"]
    expected = ([*session.messages, *closure], wire(session.state))
    session.close()
    return next_turn, *expected


def stop(root: Root, kind: str, *, start_kwargs=None) -> tuple[dict, bytes]:
    """Damage the target and take the actual stop; returns (its witness, the saved target bytes)."""
    saved = root.file(TARGET[kind])
    for name, data in DAMAGE[kind].items():
        (root.session_dir / name).write_bytes(data)
    before = root.snapshot()
    opening = root.start(**(start_kwargs or {}))
    assert (opening.stop, opening.classification) == (KINDS[kind], "A14" if kind == "a14" else "CK5"), opening
    after = root.snapshot()
    changed = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
    assert changed == {"session/STOPPED"}, f"the stop changed {changed}"
    witness = root.stopped()["detail"]["witness"]
    assert st.witness_problem(witness, KINDS[kind]) is None
    return witness, saved


def stopped(path: Path, kind: str, *, suffix: str = "partial") -> Stopped:
    path.mkdir(parents=True, exist_ok=True)
    root = Root(path)
    next_turn, messages, state = build(root, suffix=suffix)
    counts = effects(root)
    witness, saved = stop(root, kind)
    return Stopped(root, kind, KINDS[kind], saved, messages, state, next_turn, witness, counts)


def repair(ctx: Stopped) -> None:
    """The external repair, explicit: preserve the bad bytes in archive/, then restore the saved target."""
    ctx.archive.mkdir(exist_ok=True)
    for name in DAMAGE[ctx.kind]:
        (ctx.archive / f"{name}.bad").write_bytes(ctx.root.file(name))
    (ctx.session_dir / TARGET[ctx.kind]).write_bytes(ctx.saved)


def preserved(ctx: Stopped) -> dict:
    """The evidence nothing may touch: the fixture's archive and corrupt/."""
    found = {}
    for directory in (ctx.archive, ctx.session_dir / "corrupt"):
        if directory.is_dir():
            found.update({f"{directory.name}/{p.name}": p.read_bytes() for p in directory.iterdir()})
    return found


def assert_resumed(ctx: Stopped, opening, *, kept: dict | None = None) -> None:
    """The bound replay, every non-history fact, one receipt, no effect, nothing lost."""
    assert opening.stop is None and opening.classification == "A9", opening
    session = opening.session
    assert session.messages == ctx.messages, "memory is the bound checkpoint and its replayed suffix"
    assert wire(session.state) == ctx.state, "every non-history fact is the witnessed state's"
    assert session.state.history_epoch == ctx.state["history_epoch"], "no epoch transition"
    assert session.next_label() == f"{LINEAGE}:{ctx.next_turn}:1", "the next request identity is the next unused one"
    (receipt,) = receipts(ctx.root)
    assert receipt["reason"] == ctx.reason and receipt["resolution"] == RESOLUTION
    assert receipt["stop_id"] == ctx.witness["stop_id"]
    assert effects(ctx.root) == ctx.effects, "no request or tool during acknowledgement or recovery"
    for name in (st.STOPPED, st.ACKNOWLEDGED, st.RECOVERING, st.FSYNC_FAILED):
        assert not (ctx.session_dir / name).exists(), name
    assert cs.read_identity(ctx.session_dir, LINEAGE) >= ctx.witness["identity_reserved"]
    if kept is not None:
        now = preserved(ctx)
        assert {name: now.get(name) for name in kept} == kept, "preserved evidence changed"


def converge(ctx: Stopped, previous: AckOps | None = None):
    """The operator repeats the same command if the stop is still there; then two starts, the second writing nothing."""
    restart = AckOps(previous) if previous is not None else AckOps()
    if (ctx.session_dir / st.STOPPED).exists():
        assert ctx.root.stopped()["reason"] == ctx.reason, ctx.root.stopped()
        ctx.acknowledge(restart)
    opening = ctx.root.start(ops=restart)
    assert opening.stop is None, opening
    expected = list(opening.session.messages)
    opening.session.close()
    count = len(ctx.root.records())
    again = ctx.root.start()
    assert again.stop is None and again.session.messages == expected
    assert len(ctx.root.records()) == count, "the second start wrote records"
    again.session.close()
    return opening


# ===========================================================================
# The two pairs: actual stop, explicit repair, explicit acknowledgement
# ===========================================================================
@pytest.mark.parametrize("kind", sorted(KINDS))
def test_a_witnessed_file_repair_stop_resumes_from_the_bound_checkpoint(tmp_path, kind):
    ctx = stopped(tmp_path, kind)
    repair(ctx)
    kept = preserved(ctx)
    assert kept == {f"archive/{name}.bad": data for name, data in DAMAGE[kind].items()}
    carrier = ctx.acknowledge()
    assert ctx.root.stopped() is None and (ctx.session_dir / st.ACKNOWLEDGED).exists()
    assert carrier["witness"] == ctx.witness and st.carrier_problem(carrier) is None
    assert effects(ctx.root) == ctx.effects and receipts(ctx.root) == [], "the command writes no record and sends nothing"
    opening = ctx.root.start()
    assert_resumed(ctx, opening, kept=kept)
    # The receipt is the start's first record, before the closure.
    after = [r for r in ctx.root.records() if r.seq > ctx.witness["ledger"]["last_seq"]]
    assert [r.type_name for r in after] == ["RECOVERY_ACK", "UNRUN"]
    assert after[0].payload == st.receipt_payload(carrier)
    if kind == "a14":
        assert ctx.root.file("conversation.prev.json") == DAMAGE["a14"]["conversation.prev.json"], "never rewritten"
    opening.session.close()
    # Later starts are ordinary: bound, no second receipt, the same memory.
    again = ctx.root.start()
    assert again.classification == "A9" and again.session.messages == ctx.messages and len(receipts(ctx.root)) == 1


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_the_same_command_repeated_is_idempotent(tmp_path, kind):
    ctx = stopped(tmp_path, kind)
    repair(ctx)
    first = ctx.acknowledge()
    second = ctx.acknowledge()  # STOPPED is gone: the same pending carrier, its fence repeated
    assert second == first
    assert_resumed(ctx, ctx.root.start())
    with pytest.raises(cp.LedgerError):
        ctx.acknowledge()  # consumed: nothing left to acknowledge
    assert len(receipts(ctx.root)) == 1


# ===========================================================================
# The refusal matrix: every refusal leaves the store byte-identical
# ===========================================================================
def _reseal(witness: dict, **changes) -> dict:
    body = {k: v for k, v in witness.items() if k != "check"}
    for key, value in changes.items():
        if "." in key:
            outer, inner = key.split(".")
            body[outer] = {**body[outer], inner: value}
        else:
            body[key] = value
    return st._sealed(body)


def _rewrite_stop(ctx: Stopped, detail) -> None:
    (ctx.session_dir / st.STOPPED).write_text(json.dumps({"reason": ctx.reason, "detail": detail}, sort_keys=True))


def _append(root: Root, type_name: str, payload: dict):
    scan = cp.scan_segments(cp.read_segments(root.session_dir / "ledger"), LINEAGE)
    writer = cp.LedgerWriter.continue_after(root.session_dir, LINEAGE, scan)
    record = writer.append(type_name, payload)
    writer.close()
    return record


def _older_replacement(ctx: Stopped) -> None:
    """A clean, chain-valid ledger that still holds C_n but lost the later records."""
    witnessed = ctx.witness["checkpoint"]["checkpoint_seq"]
    record = next(r for r in ctx.root.records() if r.seq == witnessed + 1)
    os.truncate(ctx.root.segment(), record.offset)


def _metadata_reformatted(ctx: Stopped) -> None:
    meta = json.loads(ctx.saved)
    (ctx.session_dir / "run.json").write_text(json.dumps(meta))  # same facts, not the recorded bytes


def _metadata_older(ctx: Stopped) -> None:
    meta = json.loads(ctx.saved)
    meta["checkpoint"]["covers_seq"] -= 1
    (ctx.session_dir / "run.json").write_text(json.dumps(meta, indent=2) + "\n")


def _unbound_list(ctx: Stopped) -> None:
    (ctx.session_dir / "conversation.json").write_text(json.dumps([{"role": "user", "content": "NEW"}], indent=2) + "\n")


def _drop_note_blob(ctx: Stopped) -> None:
    (blob,) = [entry["blob"] for entry in ctx.state["notes"]["pending"]]
    (ctx.session_dir / "blobs" / blob).unlink()


def _append_bytes(ctx: Stopped, data: bytes) -> None:
    with open(ctx.root.segment(), "ab") as handle:
        handle.write(data)


def _drop_suffix_blob(ctx: Stopped) -> None:
    """The long suffix message's blob. (A lost DONE result blob is not required: replay states it as lost, C-D3.)"""
    (appended,) = [r for r in ctx.root.records() if r.type_name == "MSG_APPEND" and "blob" in r.payload]
    assert appended.seq > ctx.witness["checkpoint"]["covers_seq"]
    (ctx.session_dir / "blobs" / appended.payload["blob"]).unlink()


def _pending_collection(ctx: Stopped) -> None:
    """A pending GC_INTENT after the witnessed end, under a witness resealed to match it: the GC check alone refuses."""
    intent = _append(ctx.root, "GC_INTENT", {"records_through": 0, "checkpoint_seq": 1, "segments": [], "blobs": ["0" * 64]})
    scan = cp.scan_segments(cp.read_segments(ctx.session_dir / "ledger"), LINEAGE)
    assert st.stop_witness(ctx.session_dir, ctx.reason, scan, LINEAGE, cp.DurableOps()) is None, "no witness over a pending intent"
    witness = _reseal(
        ctx.witness, **{"ledger.last_seq": intent.seq, "ledger.last_chain": intent.chain, "ledger.end_offset": scan.tail_offset}
    )
    _rewrite_stop(ctx, {"witness": witness})


REFUSALS = {
    # The requested pair, separately from the files' condition (both repaired here).
    "wrong-reason": (True, lambda ctx: None, {"reason": "other-new-reason"}),
    "wrong-resolution-bootstrap": (True, lambda ctx: None, {"resolution": "bootstrap-preserving"}),
    "wrong-resolution-conservative": (True, lambda ctx: None, {"resolution": "continue-conservative"}),
    "absent-stop": (True, lambda ctx: (ctx.session_dir / st.STOPPED).unlink(), {}),
    "legacy-stop-without-witness": (True, lambda ctx: _rewrite_stop(ctx, None), {}),
    "damaged-witness": (True, lambda ctx: _rewrite_stop(ctx, {"witness": {**ctx.witness, "identity_reserved": 1}}), {}),
    "witness-for-the-other-reason": (True, lambda ctx: _rewrite_stop(ctx, {"witness": _reseal(ctx.witness, reason=OTHER[ctx.reason])}), {}),
    # The files' condition, with the right pair.
    "not-repaired": (False, lambda ctx: None, {}),
    "changed-ledger-record": (True, lambda ctx: _append(ctx.root, "RUN_END", {"exit": 0, "reason": "x"}), {}),
    "changed-ledger-tail": (True, lambda ctx: _append_bytes(ctx, b"SVL1 0000"), {}),
    "older-replacement-ledger": (True, _older_replacement, {}),
    "empty-new-segment": (True, lambda ctx: (ctx.session_dir / "ledger" / cp.segment_name(int(ctx.root.segment().stem) + 1)).touch(), {}),
    "identity-lower": (True, lambda ctx: (ctx.session_dir / "IDENTITY").write_bytes(cs.identity_bytes(LINEAGE, ctx.witness["identity_reserved"] - 1)), {}),
    "identity-higher": (True, lambda ctx: (ctx.session_dir / "IDENTITY").write_bytes(cs.identity_bytes(LINEAGE, ctx.witness["identity_reserved"] + 1)), {}),
    "identity-damaged": (True, lambda ctx: (ctx.session_dir / "IDENTITY").write_bytes(b'{"lineage_id": "0f1e", torn'), {}),
    "identity-foreign": (True, lambda ctx: (ctx.session_dir / "IDENTITY").write_bytes(cs.identity_bytes("other", ctx.witness["identity_reserved"])), {}),
    "identity-absent": (True, lambda ctx: (ctx.session_dir / "IDENTITY").unlink(), {}),
    "resealed-lower-identity": (True, lambda ctx: _rewrite_stop(ctx, {"witness": _reseal(ctx.witness, identity_reserved=0)}), {}),
    "missing-state-blob": (True, _drop_note_blob, {}),
    "missing-suffix-blob": (True, _drop_suffix_blob, {}),
    "open-recovering": (True, lambda ctx: (ctx.session_dir / st.RECOVERING).write_text("{}"), {}),
    "pending-collection": (True, _pending_collection, {}),
    "independent-fsync-failed": (True, lambda ctx: (ctx.session_dir / st.FSYNC_FAILED).write_text("{}"), {}),
    "another-carrier-pending": (True, lambda ctx: (ctx.session_dir / st.ACKNOWLEDGED).write_text(json.dumps({"reason": "x"})), {}),
}
FILE_REFUSALS = {
    "a14": {"unbound-conversation": (True, _unbound_list, {})},
    "ck5": {"metadata-reformatted": (True, _metadata_reformatted, {}), "metadata-older-checkpoint": (True, _metadata_older, {})},
}


OTHER = {A14: CK5, CK5: A14}


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_every_refusal_leaves_the_store_byte_identical(tmp_path, kind):
    cases = {**REFUSALS, **FILE_REFUSALS[kind]}
    for name, (repaired, mutate, call) in cases.items():
        ctx = stopped(tmp_path / name, kind)
        if repaired:
            repair(ctx)
        mutate(ctx)
        before = ctx.root.snapshot()
        call = {**call, "reason": OTHER[ctx.reason]} if call.get("reason") == "other-new-reason" else call
        try:
            ctx.acknowledge(**call)
        except cp.LedgerError:
            pass
        else:
            raise AssertionError(f"{name}: the command was accepted")
        assert ctx.root.snapshot() == before, f"{name}: the refused command changed the store"
    # A1 keeps its authority over the refused command: the marker is still there.
    assert (tmp_path / "independent-fsync-failed" / "session" / st.FSYNC_FAILED).exists()


def test_the_refusal_matrix_control_the_unmutated_repair_is_accepted(tmp_path):
    """Control for the matrix: the same fixture without its mutation is accepted, so each refusal is the mutation's."""
    for kind in sorted(KINDS):
        ctx = stopped(tmp_path / kind, kind)
        repair(ctx)
        ctx.acknowledge()


def test_stops_without_a_safe_witness_are_recorded_as_before_and_ineligible(tmp_path):
    cases = []
    # A14 and CK5 over a torn tail (not TC0): the stop comes first, the witness is withheld.
    for kind in sorted(KINDS):
        root = Root(tmp_path / f"torn-{kind}")
        build(root)
        with open(root.segment(), "ab") as handle:
            handle.write(b"SVL1 00000000")
        cases.append((root, kind))
    # CK5 without a checked IDENTITY; CK5 with a recovery open.
    for name, damage in (("identity", lambda r: (r.session_dir / "IDENTITY").write_bytes(b"x")), ("recovering", lambda r: (r.session_dir / st.RECOVERING).write_text("{}"))):
        root = Root(tmp_path / name)
        build(root)
        damage(root)
        cases.append((root, "ck5"))
    for root, kind in cases:
        for target, data in DAMAGE[kind].items():
            (root.session_dir / target).write_bytes(data)
        opening = root.start()
        assert opening.stop == KINDS[kind], opening
        assert root.stopped()["detail"] is None, "recorded exactly as before SV-023"
        before = root.snapshot()
        with pytest.raises(cp.LedgerError, match="no valid witness"):
            st.acknowledge(root.session_dir, KINDS[kind], RESOLUTION)
        assert root.snapshot() == before


def test_an_a14_stop_over_a_pending_collection_carries_no_witness(tmp_path):
    ops = CutOps()
    root, session, _ = collection_ready(tmp_path, ops)
    ops.crash_when = lambda call, path, frame: call == "unlink"
    with pytest.raises(Crash):
        collect_with(session, ops)
    session.close()
    for target, data in DAMAGE["a14"].items():
        (root.session_dir / target).write_bytes(data)
    assert gc_start(root).stop == A14
    assert root.stopped()["detail"] is None, "a pending collection is a transaction of its own"


# ===========================================================================
# No unintended resolution expansion
# ===========================================================================
OTHER_REASONS = [
    "diagnostic_stop", "ledger_unreadable", "ledger_missing", "ledger_damaged_at", "ledger_tail_ambiguous",
    "checkpoint_ahead_of_ledger", "run_json_missing", "legacy_conversation_unreadable", "replay_mismatch",
    "checkpoint_state_invalid", "identity_unproven", "identity_inconsistent", "recovery_intent_unreadable",
    "recovery_intent_invalid", "recovery_intent_mismatch", "recovery_intent_copy_missing", "recovery_intent_damaged",
    "ledger_changed_during_recovery", "gc_intent_invalid", "ledger_prefix_missing", "acknowledgement_unverified",
    "corrupt_quarantine_full", "fsync_failed_previous_run", A14, CK5,
]


def test_only_the_two_new_pairs_are_added_and_every_other_pair_is_still_refused(tmp_path):
    assert st.IMPLEMENTED_RESOLUTIONS == SUPPORTED
    assert st.WITNESSED_RESOLUTIONS == {(A14, RESOLUTION), (CK5, RESOLUTION)}
    ctx = stopped(tmp_path, "a14")
    repair(ctx)
    real_stop = (ctx.session_dir / st.STOPPED).read_bytes()
    refused = 0
    for reason in OTHER_REASONS:
        for resolution in ("continue-from-bound", "bootstrap-preserving", "continue-conservative"):
            if (reason, resolution) in SUPPORTED:
                continue
            # A valid witness is present (for another reason): it authorizes nothing here.
            (ctx.session_dir / st.STOPPED).write_text(json.dumps({"reason": reason, "detail": {"witness": ctx.witness}}))
            before = ctx.root.snapshot()
            with pytest.raises(cp.LedgerError):
                st.acknowledge(ctx.session_dir, reason, resolution)
            assert ctx.root.snapshot() == before, (reason, resolution)
            refused += 1
    assert refused == len(OTHER_REASONS) * 3 - len(SUPPORTED)
    # The low-level generic resolution names admit e.g. continue-from-bound for a lost
    # ledger; that is not authority: the runtime's explicit allowlist refuses it.
    (ctx.session_dir / st.STOPPED).write_text(json.dumps({"reason": "ledger_missing", "detail": None}))
    assert cp.acknowledge_stop(ctx.session_dir, "ledger_missing", "continue-from-bound")["resolution"] == "continue-from-bound"
    with pytest.raises(cp.LedgerError, match="not implemented"):
        st.acknowledge(ctx.session_dir, "ledger_missing", "continue-from-bound")
    (ctx.session_dir / st.STOPPED).write_bytes(real_stop)
    ctx.acknowledge()  # the genuine stop is still acknowledgeable


@pytest.mark.parametrize("reason", ["identity_unproven", "gc_intent_invalid", "ledger_prefix_missing", "recovery_intent_invalid", "acknowledgement_unverified"])
def test_newer_integrity_stops_acquire_no_resolution(tmp_path, reason):
    root = Root(tmp_path)
    establish(root).close()
    (root.session_dir / st.STOPPED).write_text(json.dumps({"reason": reason, "detail": None}))
    before = root.snapshot()
    for resolution in ("continue-from-bound", "bootstrap-preserving", "continue-conservative"):
        with pytest.raises(cp.LedgerError, match="not implemented"):
            st.acknowledge(root.session_dir, reason, resolution)
    assert root.snapshot() == before


# ===========================================================================
# Every transaction cut, process death and simulated host loss
# ===========================================================================
def acknowledge_and_start(ctx: Stopped, ops: AckOps):
    ops.armed = True
    try:
        ctx.acknowledge(ops)
        opening = ctx.root.start(ops=ops)
    finally:
        ops.armed = False
    opening.session.close()
    return opening


def probe(path: Path, kind: str, suffix: str = "partial"):
    ctx = stopped(path, kind, suffix=suffix)
    repair(ctx)
    ops = AckOps()
    acknowledge_and_start(ctx, ops)
    return ops.log


def test_the_transaction_is_ordered_and_fenced(tmp_path):
    log = probe(tmp_path, "a14")
    calls = [(call, name, frame) for call, name, frame in log]
    carrier = next(i for i, (call, name, _f) in enumerate(calls) if call == "rename" and name == st.ACKNOWLEDGED)
    unstop = calls.index(("unlink", st.STOPPED, None))
    assert carrier < unstop and calls[carrier + 1] == ("sync_dir", "session", None), "the carrier is durable before STOPPED goes"
    assert calls[unstop + 1] == ("sync_dir", "session", None)
    receipt = calls.index(("write", "000000.svl", "10"))
    assert ("sync_dir", "session", None) in calls[unstop + 2 : receipt], "the start fences session/ before its first record"
    assert calls[receipt + 1][0] == "fsync" and calls[receipt + 2][2] == "08", "the receipt, synced, then the closure"
    retire = calls.index(("unlink", st.ACKNOWLEDGED, None))
    assert receipt < retire and calls[retire - 1] == ("fsync", "000000.svl", "08"), "the receipt's segment synced first"
    assert calls[retire + 1] == ("sync_dir", "session", None)
    assert not [c for c in calls[:retire] if c[1] == "IDENTITY"], "no reservation before the carrier is retired"


@pytest.mark.parametrize("loss", ["process-death", "host-loss"])
@pytest.mark.parametrize("kind", sorted(KINDS))
def test_every_cut_of_the_acknowledgement_converges_with_one_receipt(tmp_path, kind, loss):
    log = probe(tmp_path / "probe", kind)
    for cut in range(len(log)):
        label = f"cut {cut} before {log[cut]} ({loss})"
        ctx = stopped(tmp_path / f"cut-{cut}", kind)
        repair(ctx)
        kept = preserved(ctx)
        ops = AckOps()
        ops.crash_at = cut
        with pytest.raises(Crash):
            acknowledge_and_start(ctx, ops)
        ops.abandon()
        assert effects(ctx.root) == ctx.effects, f"{label}: an effect"
        assert len(receipts(ctx.root)) <= 1, f"{label}: a second receipt"
        if loss == "host-loss":
            host_loss(ops)
        try:
            opening = converge(ctx, ops)
        except (AssertionError, cp.LedgerError) as error:
            raise AssertionError(f"{label}: {error}") from error
        assert_resumed(ctx, opening, kept=kept)


SECOND_CUTS = {
    "receipt-unsynced/carrier-unlink": (
        lambda call, path, frame: call == "fsync" and frame == "10",
        lambda call, path, frame: call == "unlink" and path.endswith(st.ACKNOWLEDGED),
    ),
    "closure-unsynced/receipt-segment-sync": (
        lambda call, path, frame: call == "fsync" and frame == "08",
        lambda call, path, frame: call == "fsync" and path.endswith(".svl"),
    ),
    "carrier-unlink/first-fence": (
        lambda call, path, frame: call == "unlink" and path.endswith(st.ACKNOWLEDGED),
        lambda call, path, frame: call == "sync_dir",
    ),
}


@pytest.mark.parametrize("cuts", sorted(SECOND_CUTS))
def test_a_second_interruption_then_host_loss_still_converges(tmp_path, cuts):
    """Process death in the consuming start, a second one in the restart, host loss over both (carried watermarks)."""
    first, second = SECOND_CUTS[cuts]
    ctx = stopped(tmp_path, "a14")
    repair(ctx)
    ctx.acknowledge()
    p1 = AckOps()
    p1.crash_when = first
    p1.armed = True
    with pytest.raises(Crash):
        ctx.root.start(ops=p1)
    p1.abandon()
    p2 = AckOps(p1)
    p2.crash_when = second
    p2.armed = True
    with pytest.raises(Crash):
        ctx.root.start(ops=p2)
    p2.abandon()
    host_loss(p2)
    assert_resumed(ctx, converge(ctx, p2))


# ===========================================================================
# True durability watermarks across mixed crashes (the SV022-01 discriminator)
# ===========================================================================
def readable_unsynced_receipt(tmp_path):
    """A consuming start dies after writing the receipt, before its fsync: readable, not durable."""
    ctx = stopped(tmp_path, "a14", suffix="message")  # nothing to close: the receipt is the only record
    repair(ctx)
    ctx.acknowledge()
    p1 = AckOps()
    p1.crash_when = lambda call, path, frame: call == "fsync" and frame == "10"
    p1.armed = True
    with pytest.raises(Crash):
        ctx.root.start(ops=p1)
    p1.abandon()
    assert len(receipts(ctx.root)) == 1, "readable after the process death"
    return ctx, p1


def test_a_readable_unsynced_receipt_is_synced_before_its_carrier_is_retired(tmp_path):
    ctx, p1 = readable_unsynced_receipt(tmp_path)
    p2 = AckOps(p1)  # the first process's watermark, not what p2 can read
    p2.armed = True
    opening = ctx.root.start(ops=p2)
    opening.session.close()
    calls = [(call, name) for call, name, _frame in p2.log]
    retire = calls.index(("unlink", st.ACKNOWLEDGED))
    assert ("fsync", "000000.svl") in calls[:retire], "the receipt's own segment is synced before the carrier goes"
    assert not [c for c in calls if c == ("write", "000000.svl")], "the receipt is not written twice"
    host_loss(p2)
    assert len(receipts(ctx.root)) == 1, "the receipt survives the host loss"
    assert_resumed(ctx, converge(ctx))


def test_negative_control_without_the_receipt_sync_a_host_loss_loses_the_receipt(tmp_path, monkeypatch):
    ctx, p1 = readable_unsynced_receipt(tmp_path)
    monkeypatch.setattr(st, "_sync_record", lambda *args: None)
    p2 = AckOps(p1)
    ctx.root.start(ops=p2).session.close()
    host_loss(p2)
    assert receipts(ctx.root) == [] and not (ctx.session_dir / st.ACKNOWLEDGED).exists(), (
        "the control retires the carrier over a receipt that was never durable: a false completion"
    )


def test_negative_control_initializing_durability_from_readable_bytes_hides_the_loss(tmp_path, monkeypatch):
    """Control for the harness itself: a restart that starts from what it can read sees no loss to prevent."""
    ctx, _p1 = readable_unsynced_receipt(tmp_path)
    monkeypatch.setattr(st, "_sync_record", lambda *args: None)
    fresh = AckOps()  # forgets the first process's watermark
    ctx.root.start(ops=fresh).session.close()
    host_loss(fresh)
    assert len(receipts(ctx.root)) == 1, "with promoted watermarks the missing sync is invisible"


def unstopped_unfenced(tmp_path):
    """The command dies after unlinking STOPPED, before its fence; a start then dies before retiring the carrier."""
    ctx = stopped(tmp_path, "ck5")
    repair(ctx)
    p1 = AckOps()
    p1.crash_when = lambda call, path, frame: call == "sync_dir" and p1.log and p1.log[-1][:2] == ("unlink", st.STOPPED)
    p1.armed = True
    with pytest.raises(Crash):
        ctx.acknowledge(p1)
    p1.abandon()
    assert ctx.root.stopped() is None and (ctx.session_dir / st.ACKNOWLEDGED).exists()
    p2 = AckOps(p1)
    p2.crash_when = lambda call, path, frame: call == "unlink" and path.endswith(st.ACKNOWLEDGED)
    p2.armed = True
    with pytest.raises(Crash):
        ctx.root.start(ops=p2)
    p2.abandon()
    assert len(receipts(ctx.root)) == 1
    host_loss(p2)
    return ctx, p2


def test_the_consuming_start_fences_stopped_removal_before_its_receipt(tmp_path):
    ctx, p2 = unstopped_unfenced(tmp_path)
    assert ctx.root.stopped() is None, "STOPPED's removal was fenced before the receipt was written"
    assert len(receipts(ctx.root)) == 1
    assert_resumed(ctx, converge(ctx, p2))


def test_negative_control_without_the_session_fences_stopped_returns_over_a_durable_receipt(tmp_path, monkeypatch):
    def no_namespace_fence(writer):
        writer.namespace_fenced = True

    monkeypatch.setattr(st, "_fence_session", lambda *args: None)
    monkeypatch.setattr(cp.LedgerWriter, "_fence_namespace", no_namespace_fence)
    ctx, _p2 = unstopped_unfenced(tmp_path)
    monkeypatch.undo()
    assert ctx.root.stopped() is not None and len(receipts(ctx.root)) == 1, "STOPPED came back over a durable receipt"
    with pytest.raises(cp.LedgerError):
        ctx.acknowledge()  # and the operator can no longer acknowledge it: the store moved on


# ===========================================================================
# This transaction's own torn frame (M-1) vs a changed tail
# ===========================================================================
def _carrier(ctx: Stopped) -> dict:
    return json.loads((ctx.session_dir / st.ACKNOWLEDGED).read_text())


def _own_frames(ctx: Stopped) -> list[bytes]:
    """The exact frames the consuming start appends: the receipt, then the closure (UNRUN of call 1)."""
    last = ctx.root.records()[-1]
    receipt, chain = cp.encode_frame(last.seq + 1, "RECOVERY_ACK", st.receipt_payload(_carrier(ctx)), last.chain)
    unrun, _chain = cp.encode_frame(
        last.seq + 2, "UNRUN", {"call_key": [ctx.next_turn - 1, 1], "reason": rp.UNRUN_TEXT}, chain
    )
    return [receipt, unrun]


@pytest.mark.parametrize("torn", ["receipt", "closure"])
def test_a_torn_frame_of_this_transaction_is_set_aside_by_the_ordinary_rule(tmp_path, torn):
    ctx = stopped(tmp_path, "a14")
    repair(ctx)
    ctx.acknowledge()
    receipt, unrun = _own_frames(ctx)
    with open(ctx.root.segment(), "ab") as handle:
        handle.write(receipt[:70] if torn == "receipt" else receipt + unrun[:70])
    opening = ctx.root.start()
    assert_resumed(ctx, opening)
    kinds = [r.payload.get("kind") for r in ctx.root.records() if r.type_name == "RECOVERY"]
    assert "torn_incomplete" in kinds, "the torn append is recorded as torn, never as content"
    assert [n for n in ctx.root.corrupt() if n.startswith("ledger-")], "its bytes are kept in corrupt/"


def test_a_crash_inside_setting_aside_its_own_torn_frame_converges(tmp_path):
    ctx = stopped(tmp_path, "a14")
    repair(ctx)
    ctx.acknowledge()
    receipt, _unrun = _own_frames(ctx)
    with open(ctx.root.segment(), "ab") as handle:
        handle.write(receipt[:70])
    p1 = AckOps()
    p1.crash_when = lambda call, path, frame: call == "truncate"
    p1.armed = True
    with pytest.raises(Crash):
        ctx.root.start(ops=p1)
    p1.abandon()
    assert (ctx.session_dir / st.RECOVERING).exists()
    assert_resumed(ctx, converge(ctx, p1))


@pytest.mark.parametrize("change", ["garbage-tail", "valid-record", "file-damaged-again", "identity-raised"])
def test_a_stale_permission_never_authorizes_a_changed_store(tmp_path, change):
    ctx = stopped(tmp_path, "a14")
    repair(ctx)
    carrier = ctx.acknowledge()
    receipt, _unrun = _own_frames(ctx)
    if change == "garbage-tail":
        with open(ctx.root.segment(), "ab") as handle:
            handle.write(bytes(len(receipt[:70])))  # as long as a torn receipt, but not its bytes
    elif change == "valid-record":
        _append(ctx.root, "RUN_END", {"exit": 0, "reason": "x"})
    elif change == "file-damaged-again":
        (ctx.session_dir / "conversation.json").write_bytes(b"\x00damaged again")
    else:
        (ctx.session_dir / "IDENTITY").write_bytes(cs.identity_bytes(LINEAGE, ctx.witness["identity_reserved"] + 64))
    before = ctx.root.snapshot()
    opening = ctx.root.start()
    assert (opening.stop, opening.classification) == ("acknowledgement_unverified", "ACK"), opening
    after = ctx.root.snapshot()
    assert {n for n in set(before) | set(after) if before.get(n) != after.get(n)} == {"session/STOPPED"}
    assert receipts(ctx.root) == [] and _carrier(ctx) == carrier, "nothing was transcribed or consumed"
    for reason in (A14, "acknowledgement_unverified"):
        with pytest.raises(cp.LedgerError):
            st.acknowledge(ctx.session_dir, reason, RESOLUTION)
    assert ctx.root.snapshot() == after


def test_negative_control_without_the_evidence_check_a_stale_permission_is_transcribed(tmp_path, monkeypatch):
    ctx = stopped(tmp_path, "a14")
    repair(ctx)
    ctx.acknowledge()
    _append(ctx.root, "RUN_END", {"exit": 0, "reason": "x"})  # the bound input changed after the acknowledgement
    monkeypatch.setattr(
        st._Context, "_verify_carrier", lambda self, carrier: st.Witnessed(carrier, st.receipt_payload(carrier), ())
    )
    opening = ctx.root.start()
    assert opening.stop is None and len(receipts(ctx.root)) == 1, "the control consumes a permission for another store"


def test_an_old_carrier_cannot_unlock_a_later_stop_with_the_same_reason(tmp_path):
    ctx = stopped(tmp_path, "a14")
    repair(ctx)
    ctx.acknowledge()
    old = (ctx.session_dir / st.ACKNOWLEDGED).read_bytes()
    assert_resumed(ctx, ctx.root.start())
    # Later, the same damage again: a new stop with the same textual reason.
    witness, _saved = stop(ctx.root, "a14")
    assert witness["stop_id"] != ctx.witness["stop_id"]
    (ctx.session_dir / st.ACKNOWLEDGED).write_bytes(old)  # the stale carrier, replayed
    before = ctx.root.snapshot()
    assert ctx.root.start().classification == "A0", "STOPPED still stops every start"
    with pytest.raises(cp.LedgerError, match="another acknowledgement is pending"):
        ctx.acknowledge()
    assert ctx.root.snapshot() == before
    (ctx.session_dir / st.STOPPED).unlink()  # even with the stop removed by hand
    opening = ctx.root.start()
    assert opening.stop == "acknowledgement_unverified" and len(receipts(ctx.root)) == 1


def test_an_independent_fsync_failure_after_the_acknowledgement_keeps_a1_authority(tmp_path):
    ctx = stopped(tmp_path, "ck5")
    repair(ctx)
    ctx.acknowledge()
    (ctx.session_dir / st.FSYNC_FAILED).write_text("{}")
    opening = ctx.root.start()
    assert (opening.classification, opening.stop) == ("A1", "fsync_failed_previous_run")
    assert receipts(ctx.root) == [] and (ctx.session_dir / st.FSYNC_FAILED).exists()


# ===========================================================================
# After actual collection: foreign notes, mirrors, the true previous tuple
# ===========================================================================
def collected_stop(path: Path, kind: str):
    """A collected lineage whose newest checkpoint holds a foreign pending generation (A8) and a runtime one."""
    root = Root(path)
    session = gc_begin(root)
    session.write_note("N1", header=HEADER)
    session.checkpoint()
    session.close()
    (root.session_dir / "conversation.json").write_text(json.dumps([*BASE, {"role": "user", "content": note("N1")}], indent=2) + "\n")
    meta = json.loads(root.file("run.json"))
    for key in ("format", "writer", "checkpoint", "history_epoch"):
        meta.pop(key)
    (root.session_dir / "run.json").write_text(json.dumps(meta))
    opening = gc_start(root)
    assert opening.classification == "A8"
    session = opening.session
    session.checkpoint()  # the foreign generation is checkpoint state
    session.write_note("N2", header=HEADER)
    for index in range(3):
        tool_turn(session, f"r{index}")
    partial_turn(session, 4)
    assert 0 not in segments(root) and root.records()[0].seq > 1, "segment 0 and the oldest records are gone"
    assert not [r for r in root.records() if r.type_name == "NOTE_WRITTEN"], "both notes' records were collected"
    assert [r for r in root.records() if r.type_name == "GC_DONE"]
    pending = session.state.notes_pending
    assert [(e["gen"], e.get("foreign")) for e in pending] == [(1, True), (2, None)]
    next_turn = session.state.requests_next["turn_seq"]
    messages = [*session.messages, T("call_b", "write_file", UNRUN)]
    state = wire(session.state)
    session.close()
    counts = effects(root)
    witness, saved = stop(root, kind, start_kwargs={"collect": True})
    return Stopped(root, kind, KINDS[kind], saved, messages, state, next_turn, witness, counts)


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_both_pairs_after_actual_collection(tmp_path, kind):
    ctx = collected_stop(tmp_path, kind)
    newest = ctx.witness["checkpoint"]
    repair(ctx)
    kept = preserved(ctx)
    ctx.acknowledge()
    opening = gc_start(ctx.root)
    assert_resumed(ctx, opening, kept=kept)
    session = opening.session
    assert session.state.history_epoch == 2 and session.state.mirror_sha256s() == ctx.state["notes"]["mirror_sha256s"]
    adopted = session.adopt_notes()
    contents = [m["content"] for m in session.messages]
    assert adopted == [2] and contents.count(note("N1")) == 1 and contents.count(note("N2")) == 1, "foreign mark kept"
    def newest_done() -> int:  # collection removes older GC_DONE records with their segments: compare seqs
        return max(r.seq for r in ctx.root.records() if r.type_name == "GC_DONE")

    collected = newest_done()
    tool_turn(session, "after")
    checkpoints = [r for r in ctx.root.records() if r.type_name == "CHECKPOINT"]
    assert checkpoints[-1].payload["prev"] == {k: newest[k] for k in ("covers_seq", "conv_sha256", "conv_bytes", "checkpoint_seq")}
    assert newest_done() > checkpoints[-1].seq > collected, "ordinary collection resumes after the new checkpoint"
    expected = list(session.messages)
    session.close()
    # Ordinary recovery afterwards: A14 from the true previous base, no stop, no genesis replay.
    (ctx.session_dir / "conversation.json").write_bytes(b"\x00garbage")
    again = gc_start(ctx.root)
    assert again.classification == "A14" and again.stop is None, again
    assert again.session.messages == [*expected, {"role": "user", "content": st.A14_NOTICE}]
    assert 0 not in segments(ctx.root) and ctx.root.records()[0].seq > 1
    assert len(receipts(ctx.root)) == 1


def test_negative_control_a_reset_note_fact_is_caught_by_the_state_comparison(tmp_path, monkeypatch):
    """Control: drop the per-generation foreign mark when state is rebuilt; the full-state comparison must fail."""
    real = rp.SessionState.from_wire.__func__

    def forget_foreign(cls, wire_state):
        state = real(cls, wire_state)
        for entry in state.notes_pending:
            entry.pop("foreign", None)
        return state

    ctx = collected_stop(tmp_path, "ck5")
    repair(ctx)
    monkeypatch.setattr(rp.SessionState, "from_wire", classmethod(forget_foreign))
    ctx.acknowledge()
    opening = gc_start(ctx.root)
    with pytest.raises(AssertionError, match="non-history fact"):
        assert_resumed(ctx, opening)


def test_negative_control_a_reset_request_identity_is_caught_by_the_label_assertion(tmp_path, monkeypatch):
    real = st.derive_core

    def reset_identity(*args, **kwargs):
        return [*real(*args, **kwargs), ("RECOVERY", {"kind": "possible_duplicate_spend", "detail": {"label": "x", "next": {"turn_seq": 1, "attempt": 2}}})]

    monkeypatch.setattr(st, "derive_core", reset_identity)
    ctx = stopped(tmp_path, "a14")
    repair(ctx)
    ctx.acknowledge()
    opening = ctx.root.start()
    assert opening.stop is None
    with pytest.raises(AssertionError):
        assert_resumed(ctx, opening)
    assert opening.session.next_label() == f"{LINEAGE}:1:2", "the control reissues turn 1"


def test_negative_control_without_the_witness_seal_a_changed_witness_is_accepted(tmp_path, monkeypatch):
    ctx = stopped(tmp_path, "ck5")
    repair(ctx)
    lowered = {**ctx.witness, "identity_reserved": 0}
    _rewrite_stop(ctx, {"witness": lowered})
    (ctx.session_dir / "IDENTITY").write_bytes(cs.identity_bytes(LINEAGE, 0))
    with pytest.raises(cp.LedgerError, match="check"):
        ctx.acknowledge()
    monkeypatch.setattr(st, "_check_ok", lambda value: True)
    ctx.acknowledge()  # the control accepts a witness whose sealed facts changed


# ===========================================================================
# One real CLI restart (evidence kind: real processes, local recorder and stub)
# ===========================================================================
SERVICES = Path(__file__).resolve().parent.parent / "services"


def test_cli_acknowledgement_and_restart_behind_the_first_request_barrier():
    from stub_model import Reply  # noqa: PLC0415
    from test_chassis_correlation import Loop, assert_stripped  # noqa: PLC0415

    world = Loop([Reply(text="fine", repeat=100)])
    try:
        world.finish(world.popen(ASKS="1"))
        lineage = json.loads((world.session_dir / "run.json").read_text())["lineage_id"]
        assert world.sent() == [f"{lineage}:1:1"]
        archive = world.root / "archive"
        archive.mkdir()
        for turn, kind in ((2, "ck5"), (3, "a14")):
            reason = KINDS[kind]
            saved = (world.session_dir / TARGET[kind]).read_bytes()
            for name, data in DAMAGE[kind].items():
                (world.session_dir / name).write_bytes(data)
            traffic = (len(world.opens()), len(world.stub.bodies))
            stopped_run = world.popen(ASKS="1")
            out, err = stopped_run.communicate(timeout=60)
            assert stopped_run.returncode == 44, out[-2000:] + err[-2000:]
            stop_record = json.loads((world.session_dir / st.STOPPED).read_text())
            assert stop_record["reason"] == reason and st.witness_problem(stop_record["detail"]["witness"], reason) is None
            for name in DAMAGE[kind]:  # the fixture's explicit repair
                (archive / f"{kind}-{name}.bad").write_bytes((world.session_dir / name).read_bytes())
            (world.session_dir / TARGET[kind]).write_bytes(saved)
            ack = subprocess.run(
                [sys.executable, str(SERVICES / "chassis.py"), "--acknowledge-stop", reason, "--resolution", RESOLUTION],
                cwd=str(world.world.work), env=world.env(), capture_output=True, text=True, timeout=60,
            )
            assert ack.returncode == 0, ack.stdout + ack.stderr
            assert (len(world.opens()), len(world.stub.bodies)) == traffic, "the command contacted nothing"
            process, release = world.behind_a_barrier(ASKS="1")
            assert (len(world.opens()), len(world.stub.bodies)) == traffic, "acknowledgement and recovery contacted nothing"
            acks = [r.payload for r in world.records() if r.type_name == "RECOVERY_ACK"]
            assert [p["reason"] for p in acks][-1] == reason and len(acks) == turn - 1
            assert not (world.session_dir / st.ACKNOWLEDGED).exists() and not (world.session_dir / st.STOPPED).exists()
            release.touch()
            world.finish(process)
            label = world.sent()[-1]
            assert label == f"{lineage}:{turn}:1", "the next permitted identity"
            assert world.opens()[-1]["client_label"] == label and not world.opens()[-1].get("label_seen_before")
        labels = [event["client_label"] for event in world.opens()]
        assert labels == [f"{lineage}:{turn}:1" for turn in (1, 2, 3)]
        assert sorted(p.name for p in archive.iterdir()) == ["a14-conversation.json.bad", "a14-conversation.prev.json.bad", "ck5-run.json.bad"]
        assert_stripped(world)
    finally:
        world.close()
