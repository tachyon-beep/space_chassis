"""Notes and their identity closure across restarts (C-N1, C-N2, O2-1, O2-6; D13 2.2.5 rules 1-4).

Evidence kind: in-process simulation, as in `test_chassis_recovery_live.py`
(whose `Root`/`resume` harness this reuses): each "run" is `open_session` +
the chassis's resume steps on one temporary root. GC is disabled in this
runtime, so nothing here is a C-G1/O2-4 (GC) pass; the O2-1 checks are about
the checkpoint state carrying pending notes, which a later GC would rely on.
"""

from __future__ import annotations

import hashlib

import chassis_replay as rp
import chassis_startup as st
from test_chassis_recovery_live import BASE, Root, append_raw, damaged, establish, resume

HEADER = "# Handoff"


def note_texts(session) -> list[str]:
    return [m["content"][len(rp.NOTE_PREFIX):] for m in session.messages if m["content"].startswith(rp.NOTE_PREFIX)]


def run(root: Root):
    opening = root.start()
    assert opening.session is not None, opening
    return resume(opening)


def test_c_n1_a_note_is_adopted_by_the_next_run_once(tmp_path):
    root = Root(tmp_path)
    first = establish(root)
    first.write_note("N1", header=HEADER)
    first.checkpoint()
    first.close()
    second = run(root)
    assert note_texts(second) == [f"{HEADER}\n\nN1\n"]
    second.close()
    third = run(root)
    assert note_texts(third) == [f"{HEADER}\n\nN1\n"], "not appended again (CH11)"


def test_c_n2_equal_text_generations_are_both_adopted(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    session.write_note("check pump", header=HEADER)
    session.write_note("check pump", header=HEADER)
    session.checkpoint()
    session.close()
    assert note_texts(run(root)) == [f"{HEADER}\n\ncheck pump\n"] * 2, "a hash dedupe would drop the second"


def test_o2_1_swallowed_handoffs_stay_pending_through_checkpoints_and_are_adopted_once(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    session.write_note("N2", header=HEADER)  # the duty swallowed the RunTermination
    session.checkpoint()
    session.write_note("N3", header=HEADER)
    session.checkpoint()
    session.checkpoint()
    newest = [r for r in root.records() if r.type_name == "CHECKPOINT"][-1]
    pending = newest.payload["state"]["notes"]["pending"]
    assert [entry["gen"] for entry in pending] == [1, 2]
    for entry, text in zip(pending, ("N2", "N3"), strict=True):
        assert session.read_blob(entry["blob"]).decode() == f"{HEADER}\n\n{text}\n"
        assert entry["blob"] in newest.payload["state"]["blobs_live"]
    first_note = next(r for r in root.records() if r.type_name == "NOTE_WRITTEN")
    assert first_note.seq <= newest.payload["prev"]["covers_seq"], (
        "NOTE_WRITTEN{N2} is GC-eligible by seq, yet its text survives in C_n.state alone"
    )
    session.close()
    second = run(root)
    assert note_texts(second) == [f"{HEADER}\n\nN2\n", f"{HEADER}\n\nN3\n"]
    second.close()
    assert note_texts(run(root)) == [f"{HEADER}\n\nN2\n", f"{HEADER}\n\nN3\n"]


def test_o2_6_a_seventeenth_note_is_dropped_and_reported_after_the_sixteen(tmp_path):
    events = []
    root = Root(tmp_path)
    session = establish(root)
    session.lifecycle = lambda event, **fields: events.append(event)
    for index in range(1, 17):
        assert session.write_note(f"N{index}", header=HEADER) == index
    blobs_before = sorted(p.name for p in (root.session_dir / "blobs").iterdir())
    assert session.write_note("N17", header=HEADER) is None
    assert sorted(p.name for p in (root.session_dir / "blobs").iterdir()) == blobs_before, "no blob for N17"
    assert events == ["note_dropped_pending_limit"]
    session.close()  # no checkpoint: the drop survives in the ledger suffix
    second = run(root)
    texts = [m["content"] for m in second.messages]
    notes = [t for t in texts if t.startswith(rp.NOTE_PREFIX)]
    assert len(notes) == 16 and "N17" not in "".join(texts)
    assert texts[-1] == "[runtime] a handoff note was not saved: 16 earlier notes from this run were unadopted"
    assert texts.index(texts[-1]) > max(texts.index(n) for n in notes)
    second.close()
    third = run(root)
    assert [m["content"] for m in third.messages].count(texts[-1]) == 1, "reported once"


def test_runtime_mirrors_are_never_adopted_as_edits(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    session.write_note("N1", header=HEADER)
    session.checkpoint()
    session.close()
    second = run(root)  # adopts gen 1; HANDOFF.md is its mirror
    second.write_note("N2", header=HEADER)
    second.checkpoint()
    second.close()
    third = run(root)  # adopts gen 2; HANDOFF.md is gen 2's mirror
    third.close()
    fourth = run(root)
    assert note_texts(fourth) == [f"{HEADER}\n\nN1\n", f"{HEADER}\n\nN2\n"]
    assert not [r for r in root.records() if r.payload.get("source") == "file_edit"]


def test_a_mirror_never_written_leaves_the_previous_mirror_in_place_and_unadopted(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    session.write_note("N1", header=HEADER)
    session.checkpoint()
    session.close()
    run(root).close()
    old_mirror = (root.home / "HANDOFF.md").read_bytes()
    session = run(root)
    session.write_note("N2", header=HEADER)
    (root.home / "HANDOFF.md").write_bytes(old_mirror)  # as if the run died before the mirror write
    session.close()
    after = run(root)
    assert note_texts(after) == [f"{HEADER}\n\nN1\n", f"{HEADER}\n\nN2\n"], "N2 adopted from the ledger; N1's mirror not re-adopted"


def test_an_agent_edit_to_handoff_md_is_adopted_once_as_a_new_generation(tmp_path):
    root = Root(tmp_path)
    establish(root).close()
    (root.home / "HANDOFF.md").write_text("written by the agent\n")
    second = run(root)
    assert note_texts(second) == ["written by the agent\n"]
    edit = next(r for r in root.records() if r.payload.get("source") == "file_edit")
    assert edit.payload["mirror_sha256"] == hashlib.sha256(b"written by the agent\n").hexdigest()
    second.close()
    (root.home / "HANDOFF.md").unlink()
    third = run(root)
    assert note_texts(third) == ["written by the agent\n"], "a deleted HANDOFF.md adopts nothing"


def test_a_damaged_final_note_record_is_noticed_and_its_mirror_adopted_once(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    session.write_note("N1", header=HEADER)
    note = root.records()[-1]
    assert note.type_name == "NOTE_WRITTEN"
    session.close()
    path = root.segment()
    data = path.read_bytes()
    path.write_bytes(data[: note.offset] + damaged(data[note.offset : note.offset + note.length], offset=80))
    opening = root.start()
    assert opening.classification == "A9"
    session = resume(opening)
    contents = [m["content"] for m in session.messages]
    assert "[runtime] a damaged NOTE_WRITTEN record was lost at recovery" in contents
    assert note_texts(session) == [f"{HEADER}\n\nN1\n"], "TC2 NOTE_WRITTEN: HANDOFF.md adopted once as a file edit"
    session.close()
    assert note_texts(run(root)) == [f"{HEADER}\n\nN1\n"]


def test_the_watermark_survives_set_history_and_external_edits(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    session.write_note("N1", header=HEADER)
    session.checkpoint()
    session.close()
    second = run(root)
    second.replace_history([{"role": "user", "content": "OPENING"}])
    second.close()
    third = run(root)
    assert note_texts(third) == [], "C-G1's state half: set_history never resets the watermark"
    third.close()
    (root.session_dir / "conversation.json").write_text('[\n  {\n    "role": "user",\n    "content": "NEW"\n  }\n]\n')
    fourth = run(root)
    assert note_texts(fourth) == [] and fourth.state.notes_adopted_through == 1


def test_an_unadopted_note_survives_a_crash_with_an_open_tool_group(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    from test_chassis_recovery_live import partial_turn  # noqa: PLC0415

    partial_turn(session, 3)  # call_a invoked
    session.write_note("from inside the tool", header=HEADER)
    session.close()
    second = run(root)
    assert note_texts(second) == [f"{HEADER}\n\nfrom inside the tool\n"]
    assert second.messages[len(BASE) + 1]["content"] == rp.UNKNOWN_TEXT


def test_a_pending_note_and_a_tail_ambiguity_both_survive_acknowledgement(tmp_path):
    root = Root(tmp_path)
    session = establish(root)
    session.write_note("N1", header=HEADER)
    session.close()
    append_raw(root, bytes(200))
    assert root.start().stop == "ledger_tail_ambiguous"
    st.acknowledge(root.session_dir, "ledger_tail_ambiguous", "continue-conservative")
    second = run(root)
    assert note_texts(second) == [f"{HEADER}\n\nN1\n"]
    assert any(m["content"].startswith("[runtime] records after ledger seq") for m in second.messages)
