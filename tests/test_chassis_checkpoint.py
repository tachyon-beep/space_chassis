"""The checkpoint protocol CK1-CK6 and its reference graph (SV-013 2.2.2; SV-015 v2 1.4.2-1.4.5).

Injected-fault and file-inspection tests in temporary roots. GC is disabled
in this runtime: the reference-graph tests show the graph a later GC must keep
is complete for what replay reads (newest base, previous base, retained
suffix, pending notes); they are not C-G1/O2-4 GC passes.
"""

from __future__ import annotations

import json

import chassis
import chassis_persistence as cp
import chassis_replay as rp
import chassis_startup as st
from test_chassis_recovery_live import BASE, FaultOps, Root, establish, partial_turn, resume


def test_ck1_ck6_happen_in_order_with_their_fences(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    ops = FaultOps()
    session.ops = session.writer.ops = ops
    ops.paths[session.writer.fd] = str(root.segment())
    session.append_message("user", "one more")
    mark = len(ops.events)
    session.checkpoint()
    events = ops.calls()[len([e for e in ops.events[:mark] if e[0] != "fenced"]) :]
    session_dir = str(root.session_dir)

    def first(predicate):
        return next(i for i, event in enumerate(events) if predicate(event))

    temp_fsync = first(lambda e: e[0] == "fsync" and ".conversation." in e[1])  # CK2
    prev_link = first(lambda e: e[0] == "link" and e[1].endswith(".prev.tmp"))  # CK3
    prev_rename = first(lambda e: e[0] == "rename" and e[1].endswith("conversation.prev.json"))
    install = first(lambda e: e[0] == "rename" and e[1].endswith("/conversation.json"))  # CK4
    install_fence = first(lambda e: e[0] == "sync_dir" and e[1] == session_dir)
    run_json = first(lambda e: e[0] == "rename" and e[1].endswith("/run.json"))  # CK5
    record = first(lambda e: e[0] == "write" and e[1].endswith(".svl"))  # CK6
    record_sync = first(lambda e: e[0] == "fsync" and e[1].endswith(".svl"))
    assert temp_fsync < prev_link < prev_rename < install < install_fence < run_json < record < record_sync


def test_the_conversation_stays_a_plain_list_in_todays_serialization(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    data = root.file("conversation.json")
    assert data == (json.dumps(session.messages, indent=2) + "\n").encode()
    # The pre-ledger runtime's reader still reads it (rollback stays possible).
    carried = chassis.Carried(root.session_dir, root.home)
    assert carried.conversation() == BASE


def test_run_json_keeps_the_legacy_keys_and_mirrors_the_checkpoint(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    session.meta_source = lambda _messages: {"agent": "a", "name": "n", "run": "r", "turn": 3}
    record = session.checkpoint(ended={"exit": 0, "reason": "finish", "at": "t", "run": "r"})
    meta = json.loads(root.file("run.json"))
    assert {k: meta[k] for k in ("agent", "name", "run", "turn")} == {"agent": "a", "name": "n", "run": "r", "turn": 3}
    assert meta["ended"]["reason"] == "finish" and meta["format"] == 2 and meta["writer"] == "chassis-2"
    assert meta["checkpoint"] == {
        "covers_seq": record.payload["covers_seq"], "conv": record.payload["conv"],
        "prev": record.payload["prev"], "epoch": record.payload["state"]["history_epoch"],
    }


def test_each_checkpoint_chains_to_the_previous_and_the_state_validates(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    partial_turn(session, 6)
    session.checkpoint()
    checkpoints = [r for r in root.records() if r.type_name == "CHECKPOINT"]
    for older, newer in zip(checkpoints, checkpoints[1:]):
        assert newer.payload["prev"]["checkpoint_seq"] == older.seq
        assert newer.payload["prev"]["conv_sha256"] == older.payload["conv"]["sha256"]
        assert newer.payload["chain_at_cover"] == next(r.chain for r in root.records() if r.seq == newer.payload["covers_seq"])
    for checkpoint in checkpoints:
        rp.SessionState.from_wire(checkpoint.payload["state"])


class Reads:
    """A blob reader that remembers what replay asked for."""

    def __init__(self, session_dir) -> None:
        self.store = cp.BlobStore(session_dir / "blobs")
        self.read: set[str] = set()

    def __call__(self, sha):
        self.read.add(sha)
        return self.store.get(sha, 64 * 1024 * 1024)


def test_the_retained_reference_graph_covers_every_blob_replay_reads(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    session.write_note("pending across checkpoints", header="# Handoff")
    session.checkpoint()
    partial_turn(session, 6)
    session.append_message("user", "x" * 5000)  # a message blob
    session.replace_history([*session.messages])  # HISTORY_REPLACED blob, then a checkpoint
    partial_turn(session, 4)  # a suffix with a DONE blob
    session.close()
    records = root.records()
    retained = rp.retained_refs(records)
    newest = [r for r in records if r.type_name == "CHECKPOINT"][-1]
    pending = newest.payload["state"]["notes"]["pending"]
    assert pending and {e["blob"] for e in pending} <= retained, "pending note blobs are kept by C_n.state alone"
    # Previous-base replay (A14) reads the interval up to C_n and the suffix: all of it retained.
    (root.session_dir / "conversation.json").write_bytes(b"unreadable")
    reads = Reads(root.session_dir)
    context = st._Context(root.session_dir, root.home, cp.DurableOps(), lambda *a, **k: None,
                          chassis.drop_stored_recap_frames, None, cp.Quarantine(root.session_dir / "corrupt"))
    decision = context._classify_base(tuple(records), (), True, "0f1e", reads)
    assert decision.case == "A14"
    assert reads.read and reads.read <= retained
    # Every blob a retained record names exists.
    for sha in retained:
        assert (root.session_dir / "blobs" / sha).exists()


def crash_after_ck4(root: Root, session) -> None:
    """Process death after CK4 installed the new file, before CK5/CK6."""
    from test_chassis_durability import Crash  # noqa: PLC0415

    ops = FaultOps()
    session.ops = session.writer.ops = ops
    ops.paths[session.writer.fd] = str(root.segment())
    ops.faults.append(("sync_dir", lambda p: p.endswith("/session"), Crash()))
    try:
        session.checkpoint()
    except Crash:
        pass
    session.close()


def assert_prev_is_bound_and_a14_rebuilds(root: Root, session) -> None:
    import hashlib  # noqa: PLC0415

    newest = [r for r in root.records() if r.type_name == "CHECKPOINT"][-1]
    prev = newest.payload["prev"]
    assert prev is not None, "the newest checkpoint names no previous base"
    retained = hashlib.sha256(root.file("conversation.prev.json")).hexdigest()
    assert retained == prev["conv_sha256"], "conversation.prev.json is not the snapshot `prev` advertises"
    expected = list(session.messages)
    session.close()
    (root.session_dir / "conversation.json").write_bytes(b"damaged")
    opening = root.start()
    assert opening.classification == "A14", opening
    assert opening.session.messages[: len(expected)] == expected
    assert opening.session.messages[-1]["content"] == st.A14_NOTICE
    opening.session.close()


def test_sv021_02_the_previous_base_survives_a10_and_the_next_checkpoint(tmp_path):
    """Astra SV021-02: C(B) -> append -> crash after CK4(N) -> A10 -> next checkpoint -> A14."""
    root = Root(tmp_path)
    session = establish(root)
    session.append_message("user", "appended before the interrupted checkpoint")
    crash_after_ck4(root, session)
    opening = root.start()
    assert opening.classification == "A10"
    session = opening.session
    session.append_message("user", "after the recovery")
    session.checkpoint()
    assert_prev_is_bound_and_a14_rebuilds(root, session)


def test_sv021_02_the_previous_base_survives_an_a14_repair_and_the_next_checkpoint(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    partial_turn(session, 6)
    session.checkpoint()
    session.close()
    (root.session_dir / "conversation.json").write_bytes(b"damaged")
    opening = root.start()
    assert opening.classification == "A14"
    session = opening.session
    session.append_message("user", "after the repair")
    session.checkpoint()
    assert_prev_is_bound_and_a14_rebuilds(root, session)


def test_sv021_02_the_previous_base_survives_an_external_edit_and_the_next_checkpoint(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    partial_turn(session, 6)
    session.checkpoint()
    session.close()
    (root.session_dir / "conversation.json").write_text(json.dumps([{"role": "user", "content": "NEW"}], indent=2) + "\n")
    opening = root.start()
    assert opening.classification == "A11"
    session = opening.session
    session.append_message("user", "after the edit")
    session.checkpoint()
    assert_prev_is_bound_and_a14_rebuilds(root, session)


def test_sv021_02_the_previous_base_survives_a_rollback_reimport_and_the_next_checkpoint(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    partial_turn(session, 6)
    session.checkpoint()
    session.close()
    meta = json.loads(root.file("run.json"))
    for key in ("format", "writer", "checkpoint", "history_epoch"):
        meta.pop(key)
    (root.session_dir / "run.json").write_text(json.dumps(meta))
    (root.session_dir / "conversation.json").write_text(json.dumps([{"role": "user", "content": "old runtime"}], indent=2) + "\n")
    opening = root.start()
    assert opening.classification == "A8"
    session = opening.session
    session.append_message("user", "after the reimport")
    session.checkpoint()
    assert_prev_is_bound_and_a14_rebuilds(root, session)


def test_o2_2_previous_base_replay_reads_the_interval_and_the_suffix_only(tmp_path):
    root = Root(tmp_path)
    session = establish(root)  # C_p
    partial_turn(session, 6)
    session.checkpoint()  # C_n
    partial_turn(session, 4)
    session.close()
    records = root.records()
    newest = [r for r in records if r.type_name == "CHECKPOINT"][-1]
    floor = newest.payload["prev"]["covers_seq"]
    read = [r for r in records if r.seq > floor]
    # Interval (C_p's record ... turn 7) + C_n's record + the turn-8 suffix: the oracle's "21-32" shape.
    kinds = [r.type_name for r in read]
    assert kinds == ["CHECKPOINT", "REQUEST_SENT", "TURN_RESPONSE", "INVOKING", "DONE", "INVOKING", "DONE",
                     "CHECKPOINT", "REQUEST_SENT", "TURN_RESPONSE", "INVOKING", "DONE"]
    (root.session_dir / "conversation.json").write_bytes(b"unreadable")
    opening = root.start()
    assert opening.classification == "A14"
    session = resume(opening)
    assert session.messages[-1]["role"] in ("user", "tool")
