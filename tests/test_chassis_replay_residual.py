"""SV029: the two SV-015 v2 1.4.7 inequalities SV025-SV028 left unproved (test-only).

Nothing here changes the runtime, its limits or the canonical oracle; every
constant is the default. The governing design is
docs/planning-context/sv029/DESIGN.md with Astra's launch qualifications
L1-L6 (ASTRA-DESIGN-REVIEW.md).

* **Previous-base bytes `< 50,352,266`.** A retained `.prev.json` that stays
  bound while each later checkpoint sees an unbound (externally edited)
  current file makes `C_n.prev` span seven default threshold intervals of
  admitted 1 MiB direct messages. A14 replays them all.
* **Newest-base records `<= 358`.** A threshold checkpoint that dies before its
  frame, then 108 starts that each follow an external edit and die at entry
  to their threshold checkpoint's install: no newer origin commits, and every
  start adds one record.

Each counterexample passes by asserting a contradiction of the canonical
number. That is evidence against it, not a bound of any kind. N2 and N4 are
the discriminating controls.

Measurement follows SV025's observer: frame lengths and types from the
segment byte walk, blob bytes from successful returned reads tagged with the
seq `Replay.apply` was applying, and the applied sequence itself. The
runtime's `since_*` counters and classifications are compared, never used
as the oracle. Base-file, scanner and planning reads are not replay work and
are not compared with either inequality.

The crashes are in-process simulations (`Crash` from an injected filesystem
call; the abandoned writer's descriptor is then closed): not subprocess
death, not host loss.
"""

from __future__ import annotations

import hashlib
import json

import chassis_envelope as envelope
import chassis_persistence as cp
import chassis_replay as rp
import chassis_session as cs
import chassis_startup as st
import pytest
from test_chassis_bounds import NEWEST_BYTES_LT, NEWEST_RECORDS_MAX, PREV_BYTES_LT, frames, interval_work, newest_checkpoint, watch  # noqa: F401
from test_chassis_durability import Crash
from test_chassis_recovery_live import Root, establish

HEX = {name: f"{cp.TYPE_IDS[name]:02x}" for name in cp.TYPE_IDS}
MESSAGE = cs.DIRECT_MESSAGE_MAX_E  # 1,048,576: the admitted maximum of a direct message, in escaped units and here in bytes
PER_ROUND = 8  # 8 MiB of message blobs reaches RECOVERY_BYTES_MAX on the 8th unit, not before


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def edit(root: Root, label) -> bytes:
    """An external edit: a valid one-message list the runtime did not write."""
    data = rp.conversation_bytes([{"role": "user", "content": f"EDIT {label}"}])
    (root.session_dir / "conversation.json").write_bytes(data)
    return data


def checkpoints(root: Root) -> list:
    return [record for record in root.records() if record.type_name == "CHECKPOINT"]


# ---------------------------------------------------------------------------
# Previous-base bytes (N1, N2)
# ---------------------------------------------------------------------------
def message_round(root: Root, label: int, *, edited: bool) -> dict:
    """One start (A11 after an edit, else A9), then 8 distinct 1 MiB direct messages; the 8th's threshold checkpoint fires.

    Returns the round's checkpoint, its message blob names, the edit's blob
    name and size, and the list the checkpoint bound.
    """
    data = edit(root, label) if edited else None
    origin = newest_checkpoint(root)
    opening = root.start(collect=True)
    assert opening.classification == ("A11" if edited else "A9")
    session = opening.session
    assert newest_checkpoint(root).seq == origin.seq, "the startup unit stays below the threshold"
    shas = []
    for m in range(1, PER_ROUND + 1):
        prefix = f"{label}:{m}:"
        text = prefix + "a" * (MESSAGE - len(prefix))
        body = text.encode("utf-8")
        # Admission, measured on the actual text: escaped units at the direct maximum, bytes equal.
        assert len(body) == MESSAGE and envelope.escaped_units(text) == MESSAGE <= cs.DIRECT_MESSAGE_MAX_E
        session.append_message("user", text)
        records = root.records()
        appended = [r for r in records if r.type_name == "MSG_APPEND"][-1]
        assert appended.payload["blob"] == sha(body) and "text" not in appended.payload, "a blob, by this content"
        shas.append(sha(body))
        if m < PER_ROUND:
            assert newest_checkpoint(root).seq == origin.seq, f"no checkpoint before the 8th unit (unit {m})"
    after = [r for r in records if r.seq > appended.seq]
    assert after and after[0].type_name == "CHECKPOINT", "the 8th unit's threshold checkpoint follows it at once"
    assert all(r.type_name in ("GC_INTENT", "GC_DONE") for r in after[1:]), [r.type_name for r in after]
    checkpoint = after[0]
    edit_blob = None
    if edited:
        switch = [r for r in records if r.type_name == "EXTERNAL_EDIT" and r.seq > origin.seq]
        assert len(switch) == 1 and switch[0].payload["conv_sha"] == sha(data)
        edit_blob = (switch[0].payload["blob"], len(data))
        assert edit_blob[0] == sha(data), "the edited list was valid and needed no repair"
    # The newest-row premise holds in this interval: walked frames after the origin + known blob sizes.
    walked = frames(root)
    interval = sum(walked[s][1] for s in walked if origin.seq < s < checkpoint.seq) + PER_ROUND * MESSAGE
    interval += edit_blob[1] if edit_blob else 0
    last_unit = walked[appended.seq][1] + MESSAGE
    assert interval - last_unit < cs.RECOVERY_BYTES_MAX <= interval < NEWEST_BYTES_LT
    bound = list(session.messages)
    session.close()
    return {"checkpoint": checkpoint, "shas": shas, "edit": edit_blob, "messages": bound, "interval": interval}


def damage_and_recover(root: Root, watch, lo: int):
    """Make conversation.json unreadable (present, not JSON); A14 replays from .prev.json. The interval is fixed first."""
    walked = frames(root)
    hi = max(walked)
    (root.session_dir / "conversation.json").write_bytes(b"\x00damaged in the temporary root")
    observer = watch()
    opening = root.start(ops=observer, collect=True)
    assert (opening.classification, opening.stop) == ("A14", None)
    # The previous interval, then the suffix: each record once, in order, nothing at or below the named base's cover.
    assert [seq for seq in observer.applies if seq <= hi] == list(range(lo + 1, hi + 1))
    reads = [(name, size, seq) for kind, name, size, seq in observer.of("blob") if seq is not None and seq <= hi]
    return opening, observer, walked, hi, reads


ROUNDS = 7  # 7 x 8 MiB = 58,720,256 >= 50,352,266 from message blobs alone; 6 rounds would fall 20,618 short


def test_sv029_a_retained_previous_base_spanning_threshold_checkpoints_exceeds_the_previous_byte_bound(tmp_path, watch):
    root = Root(tmp_path)
    establish(root).close()
    a, b = checkpoints(root)
    a_tuple = cs.checkpoint_tuple(a)
    assert (a.payload["prev"], b.payload["prev"]) == (None, a_tuple)
    prev_file = root.file("conversation.prev.json")
    assert sha(prev_file) == a.payload["conv"]["sha256"]

    rounds = [message_round(root, r, edited=True) for r in range(1, ROUNDS + 1)]
    # Every threshold checkpoint still names A: the current file was an unbound edit each time.
    assert [r["checkpoint"].payload["prev"] for r in rounds] == [a_tuple] * ROUNDS
    assert root.file("conversation.prev.json") == prev_file
    walked = frames(root)
    after_b = [walked[s][0] for s in walked if s > b.seq]
    assert HEX["LEDGER_HEADER"] not in after_b, "one segment: no header in the interval"
    assert [s for s in walked if walked[s][0] == HEX["CHECKPOINT"] and s > a.seq] == [b.seq] + [r["checkpoint"].seq for r in rounds]
    message_shas = [s for r in rounds for s in r["shas"]]
    edit_blobs = dict(r["edit"] for r in rounds)
    assert len(set(message_shas)) == ROUNDS * PER_ROUND and len(edit_blobs) == ROUNDS

    newest = rounds[-1]["checkpoint"]
    lo = a.payload["covers_seq"]
    opening, observer, walked, hi, reads = damage_and_recover(root, watch, lo)
    # Read multiplicity, independently of interval_work's keyed sums: 63 returned reads, one per blob, one per record.
    assert len(reads) == ROUNDS * PER_ROUND + ROUNDS
    assert len({name for name, _size, _seq in reads}) == len(reads) == len({seq for _name, _size, seq in reads})
    assert {name for name, _size, _seq in reads} == set(message_shas) | set(edit_blobs)
    assert all(size == MESSAGE for name, size, _seq in reads if name in set(message_shas))
    assert all(size == edit_blobs[name] for name, size, _seq in reads if name in edit_blobs)
    raw = sum(size for _name, size, _seq in reads)

    work = interval_work(observer, walked, lo, hi)
    message_bytes = ROUNDS * PER_ROUND * MESSAGE
    assert message_bytes == 58_720_256
    assert work.records == hi - lo
    assert (work.blob_calls, work.blob_bytes, work.distinct_blob_bytes) == (len(reads), raw, raw)
    assert raw == message_bytes + sum(edit_blobs.values())
    assert work.frame_bytes == sum(walked[s][1] for s in range(lo + 1, hi + 1))
    checkpoint_frames = sum(walked[s][1] for s in range(lo + 1, hi + 1) if walked[s][0] == HEX["CHECKPOINT"])
    # The contradiction. The message blobs alone exceed the strict bound, whatever frames are counted.
    assert message_bytes >= PREV_BYTES_LT and message_bytes - PREV_BYTES_LT == 8_367_990
    assert work.total >= work.blob_bytes > message_bytes >= PREV_BYTES_LT
    # A bracket (not a bound): frames, checkpoint frames included, are small beside the blobs.
    assert 0 < checkpoint_frames < work.frame_bytes < 1_000_000

    session = opening.session
    # SV026's trigger counts only the newest suffix: it never sees this interval.
    assert session.since_bytes < cs.RECOVERY_BYTES_MAX < work.total
    assert session.messages == [*rounds[-1]["messages"], {"role": "user", "content": st.A14_NOTICE}]
    assert sha(root.file("conversation.json")) == newest.payload["conv"]["sha256"]
    assert root.file("conversation.prev.json") == prev_file
    session.close()


def test_sv029_control_an_immediately_previous_base_reads_one_interval_below_the_bound(tmp_path, watch):
    """The same apparatus, with the edit omitted in round 2: the bound file rotates, prev names C_1, one interval is read."""
    root = Root(tmp_path)
    establish(root).close()
    a, _b = checkpoints(root)
    first = message_round(root, 1, edited=True)
    c1 = first["checkpoint"]
    assert c1.payload["prev"] == cs.checkpoint_tuple(a)
    second = message_round(root, 2, edited=False)
    c2 = second["checkpoint"]
    assert c2.payload["prev"] == cs.checkpoint_tuple(c1), "the current file was bound to C_1, so CK3 rotated it"
    assert sha(root.file("conversation.prev.json")) == c1.payload["conv"]["sha256"]

    lo = c1.payload["covers_seq"]
    opening, observer, walked, hi, reads = damage_and_recover(root, watch, lo)
    assert sorted(name for name, _size, _seq in reads) == sorted(second["shas"]), "only round 2's blobs: round 1 is in the base"
    assert len({seq for _name, _size, seq in reads}) == len(reads) == PER_ROUND
    assert all(size == MESSAGE for _name, size, _seq in reads)
    work = interval_work(observer, walked, lo, hi)
    assert (work.blob_calls, work.blob_bytes, work.distinct_blob_bytes) == (PER_ROUND, PER_ROUND * MESSAGE, PER_ROUND * MESSAGE)
    assert work.frame_bytes == sum(walked[s][1] for s in range(lo + 1, hi + 1))
    # In bound: one threshold interval and its suffix.
    assert cs.RECOVERY_BYTES_MAX <= work.total < NEWEST_BYTES_LT < PREV_BYTES_LT
    session = opening.session
    assert session.messages == [*second["messages"], {"role": "user", "content": st.A14_NOTICE}]
    session.close()


# ---------------------------------------------------------------------------
# Newest-base records (N3, N4)
# ---------------------------------------------------------------------------
SAYS = cs.RECOVERY_RECORDS_MAX  # 256 inline messages: the 256th reaches the record threshold
EDITED_STARTS = 108  # starts 2..109; start 110 replays 256 + 1 + 108 = 365 records after B's frame


class CheckpointWriteDeath(cp.DurableOps):
    """Process death at the write of a CHECKPOINT frame, before any of its bytes (the accepted ck6-before-write cut)."""

    def __init__(self) -> None:
        self.armed = False
        self.fired = 0

    def write(self, fd, data):
        if self.armed and bytes(data[:5]) == cp.MAGIC and bytes(data[18:20]) == HEX["CHECKPOINT"].encode("ascii"):
            self.armed = False
            self.fired += 1
            raise Crash()
        return super().write(fd, data)


@pytest.fixture
def probes(monkeypatch):
    """Pass-through probes: checkpoint-entry counters, each start's base case, and every writer a start opened."""
    entries: list = []
    cases: list = []
    writers: list = []
    checkpoint = cs.Session.checkpoint
    finish = st._Context._finish_case
    continue_after = cp.LedgerWriter.continue_after

    def logged(self, *args, **kwargs):
        entries.append((self.since_records, self.since_bytes))
        return checkpoint(self, *args, **kwargs)

    def finishing(self, session, decision, *args, **kwargs):
        cases.append(decision.case)
        return finish(self, session, decision, *args, **kwargs)

    def opened(*args, **kwargs):
        writer = continue_after(*args, **kwargs)
        writers.append(writer)
        return writer

    monkeypatch.setattr(cs.Session, "checkpoint", logged)
    monkeypatch.setattr(st._Context, "_finish_case", finishing)
    monkeypatch.setattr(cp.LedgerWriter, "continue_after", staticmethod(opened))
    return {"entries": entries, "cases": cases, "writers": writers, "monkeypatch": monkeypatch}


def interrupted_threshold_checkpoint(root: Root, probes):
    """B newest; 256 inline messages; the 256th's threshold checkpoint dies before its frame.

    CK3 has rotated B's bytes into .prev.json, CK4 installed the longer list,
    CK5 covers the last message: an A10 setup, with B still the newest origin.
    """
    establish(root).close()
    b = newest_checkpoint(root)
    death = CheckpointWriteDeath()
    opening = root.start(ops=death)
    assert opening.classification == "A9"
    session = opening.session
    assert (session.since_records, session.since_bytes) == (0, 0)
    for i in range(SAYS - 1):
        session.append_message("user", f"say {i}")
    assert session.since_records == SAYS - 1 and newest_checkpoint(root).seq == b.seq
    death.armed = True
    probes["entries"].clear()
    with pytest.raises(Crash):
        session.append_message("user", f"say {SAYS - 1}")
    assert death.fired == 1 and [e[0] for e in probes["entries"]] == [SAYS]
    listed = list(session.messages)
    session.close()
    probes["writers"].clear()
    walked = frames(root)
    assert [walked[s][0] for s in walked if s > b.seq] == [HEX["MSG_APPEND"]] * SAYS, "no checkpoint frame, no header"
    assert all("text" in r.payload for r in root.records() if r.seq > b.seq), "inline: no blobs"
    assert root.file("conversation.json") == rp.conversation_bytes(listed), "CK4 installed the new list"
    assert sha(root.file("conversation.prev.json")) == b.payload["conv"]["sha256"], "CK3 kept B's bytes"
    meta = json.loads(root.file("run.json"))["checkpoint"]
    assert (meta["covers_seq"], meta["conv"]["sha256"]) == (max(walked), sha(root.file("conversation.json"))), "CK5 ran"
    return b


def measured_start(root: Root, watch, probes, b, *, dies: bool):
    """One start, its interval fixed first. Returns (N: records applied after B's frame, the start's new records, opening)."""
    walked = frames(root)
    end = max(walked)
    files = {name: root.file(name) for name in ("conversation.json", "conversation.prev.json", "run.json")}
    assert sha(files["conversation.prev.json"]) == b.payload["conv"]["sha256"], "B's exact bytes: a newest-base replay"
    probes["entries"].clear()
    probes["cases"].clear()
    observer = watch()
    opening = None
    if dies:
        fired = []

        def install_death(*_args, **_kwargs):
            fired.append(True)
            raise Crash()  # process death at CK2 entry, before any install work

        with probes["monkeypatch"].context() as m:
            m.setattr(cp, "install_conversation", install_death)
            with pytest.raises(Crash):
                root.start(ops=observer)
        assert len(fired) == 1
        for writer in probes["writers"]:
            writer.close()
        probes["writers"].clear()
        assert {name: root.file(name) for name in files} == files, "the dying start changed no file the cut precedes"
    else:
        opening = root.start(ops=observer)
    # B's own frame, then each later record once, in order; nothing at or below B's cover (no previous base).
    assert [seq for seq in observer.applies if seq <= end] == list(range(b.seq, end + 1))
    assert HEX["LEDGER_HEADER"] not in [walked[s][0] for s in range(b.seq + 1, end + 1)]
    assert len(probes["cases"]) == 1
    new = [r for r in root.records() if r.seq > end]
    return end - b.seq, new, opening


def test_sv029_repeated_edited_starts_dying_before_their_checkpoint_grow_the_newest_suffix_past_358(tmp_path, watch, probes):
    root = Root(tmp_path)
    b = interrupted_threshold_checkpoint(root, probes)
    counts = []

    n, new, _ = measured_start(root, watch, probes, b, dies=True)
    assert probes["cases"] == ["A10"] and n == SAYS
    assert [(r.type_name, r.payload["kind"]) for r in new] == [("RECOVERY", "conversation_adopted")]
    assert [e[0] for e in probes["entries"]] == [n + 1]
    counts.append(n)

    for j in range(2, 2 + EDITED_STARTS):
        data = edit(root, j)
        n, new, _ = measured_start(root, watch, probes, b, dies=True)
        assert probes["cases"] == ["A11"] and n == j + 255
        assert [r.type_name for r in new] == ["EXTERNAL_EDIT"] and new[0].payload["conv_sha"] == sha(data)
        assert [e[0] for e in probes["entries"]] == [j + 256], "checkpoint entry: the replay plus its one new core record"
        counts.append(n)
    assert counts == [SAYS] + [j + 255 for j in range(2, 2 + EDITED_STARTS)]
    assert counts.index(NEWEST_RECORDS_MAX + 1) == 103, "start 104 is the first to read 359"

    n, new, opening = measured_start(root, watch, probes, b, dies=False)
    assert opening.classification == "A9t" and probes["cases"] == ["A9t"]
    # The contradiction: 365 records after B's own frame (366 with it), against <= 358.
    assert n == SAYS + 1 + EDITED_STARTS == 365 > NEWEST_RECORDS_MAX
    assert [e[0] for e in probes["entries"]] == [365], "no new core: the counter is the replay"
    assert [r.type_name for r in new] == ["CHECKPOINT"], "the first committed origin after B"
    interval = [r for r in root.records() if b.seq < r.seq < new[0].seq]
    kinds = [r.type_name for r in interval]
    assert (kinds.count("MSG_APPEND"), kinds.count("RECOVERY"), kinds.count("EXTERNAL_EDIT"), len(kinds)) == (SAYS, 1, EDITED_STARTS, 365)
    session = opening.session
    assert (session.since_records, session.since_bytes) == (0, 0) and session.group is None
    assert not (root.session_dir / "corrupt").exists()
    session.close()
    probes["writers"].clear()


def test_sv029_control_repeated_deaths_without_an_external_change_add_no_records(tmp_path, watch, probes):
    root = Root(tmp_path)
    b = interrupted_threshold_checkpoint(root, probes)
    n, new, _ = measured_start(root, watch, probes, b, dies=True)
    assert probes["cases"] == ["A10"] and n == SAYS and [r.type_name for r in new] == ["RECOVERY"]
    assert [e[0] for e in probes["entries"]] == [SAYS + 1]
    for _ in range(3):
        n, new, _ = measured_start(root, watch, probes, b, dies=True)
        assert probes["cases"] == ["A9t"] and n == SAYS + 1 and new == []
        assert [e[0] for e in probes["entries"]] == [SAYS + 1], "no new core: the adoption binds the unchanged file"
    n, new, opening = measured_start(root, watch, probes, b, dies=False)
    assert opening.classification == "A9t" and n == SAYS + 1 <= NEWEST_RECORDS_MAX
    assert [e[0] for e in probes["entries"]] == [SAYS + 1]
    assert [r.type_name for r in new] == ["CHECKPOINT"]
    assert opening.session.since_records == 0
    assert not (root.session_dir / "corrupt").exists()
    opening.session.close()
    probes["writers"].clear()
