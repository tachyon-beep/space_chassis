"""Staged run metadata: lineage, fold progress and how the last run ended (SV-019 K-A1).

Contract: SV-013 sections 2.2.2/2.2.4 and 4.1, with the staging exception
from the SV-019 preflight: run.json gains `lineage_id`, `recap_folded` and
`ended`, and deliberately **not** `format`, `writer` or `checkpoint` -- those
mark the ledger's authority (K-D), and a ledger-aware runtime's rule A7 would
read them, with no ledger present, as a lost ledger. The conversation stays a
plain list written exactly as before.

Runs use the termination tests' harness: the real `Chassis.run()`, a scripted
fake client, temporary roots.
"""

from __future__ import annotations

import json

import chassis
import pytest
from test_chassis_termination import make_run, reply  # noqa: F401 -- make_run is a fixture

STATUS_DUTY = "STATUS = []\n"
STATUS_MAIN = "    STATUS.append(json.loads(context.status()))\n    context.ask('go')\n"
IMPORT_JSON = "import json\n"


def test_run_json_gains_the_staged_keys_and_no_authority_markers(make_run):
    run = make_run([reply("ok")], main="    context.finish('done')\n")
    run.go()
    meta = run.meta()
    for key in ("agent", "name", "run", "turn", "model", "updated", "context_tokens", "context_window", "usage", "entry"):
        assert key in meta, f"existing key {key} was lost"
    assert chassis.LINEAGE_ID.fullmatch(meta["lineage_id"])
    assert meta["recap_folded"] == 0
    assert meta["ended"] == {"exit": 0, "reason": "finish", "at": meta["ended"]["at"], "run": run.chassis.run_id}
    assert not {"format", "writer", "checkpoint", "history_epoch"} & set(meta), (
        "a ledger authority marker was published before the ledger exists"
    )


def test_the_conversation_is_still_a_plain_list_written_as_before(make_run):
    run = make_run([reply("ok")], main="    context.ask('go')\n")
    run.go()
    raw = (run.root / "home" / "session" / "conversation.json").read_text()
    assert isinstance(json.loads(raw), list)
    assert raw == json.dumps(run.chassis.messages, indent=2) + "\n"


def test_the_lineage_is_stable_and_the_next_run_sees_how_this_one_ended(make_run, tmp_path):
    first = make_run([reply("ok")], main="    context.handoff('see you')\n", root=tmp_path / "w")
    first.go()
    first_meta = first.meta()
    second = make_run(
        [reply("again")], main=STATUS_MAIN, extra=IMPORT_JSON + STATUS_DUTY, root=tmp_path / "w"
    )
    second.go()
    (status,) = second.duty.STATUS
    assert status["previous_run_ended"] == first_meta["ended"]
    assert status["previous_run_ended"]["reason"] == "handoff"
    assert status["turns_before_this_run"] == first_meta["turn"]
    assert status["lineage_id"] == first_meta["lineage_id"] == second.meta()["lineage_id"]


def test_an_invalid_lineage_is_replaced_and_the_record_says_so(make_run, tmp_path):
    session = tmp_path / "w" / "home" / "session"
    session.mkdir(parents=True)
    (session / "run.json").write_text(json.dumps({"lineage_id": "not a valid id!"}))
    run = make_run([reply("ok")], main="    context.ask('go')\n", root=tmp_path / "w")
    run.go()
    lineage = run.meta()["lineage_id"]
    assert lineage != "not a valid id!" and chassis.LINEAGE_ID.fullmatch(lineage)
    assert [r for r in run.lifecycle() if r["event"] == "lineage_started"]


FOLD_ENV = {"CONTEXT_WINDOW_TOKENS": "300", "CONTEXT_WINDOW_EVICTION_TOKENS": "60"}


def asks(prefix: str, count: int) -> str:
    return "".join(f"    context.ask('{prefix} question {i} ' + 'q' * 120)\n" for i in range(count))


def test_fold_progress_survives_checkpoint_and_resume_without_duplicate_lines(make_run, tmp_path):
    """Before K-A1 run.json never held `recap_folded`, so every resume folded from 0 again."""
    replies = [reply(f"first answer {i} " + "a" * 120) for i in range(12)]
    first = make_run(replies, main=asks("first", 12), root=tmp_path / "w", env=FOLD_ENV)
    first.go()
    folded = first.meta()["recap_folded"]
    assert folded > 0 and folded == first.chassis.recap_folded
    recap_after_first = first.chassis.carried.recap()

    replies = [reply(f"second answer {i} " + "b" * 120) for i in range(12)]
    second = make_run(replies, main=asks("second", 12), root=tmp_path / "w", env=FOLD_ENV)
    second.go()
    recap = second.chassis.carried.recap()
    assert recap.startswith(recap_after_first.strip()[:200]), "the first run's recap was kept"
    lines = [line for line in recap.splitlines() if line.startswith("- [")]
    assert len(lines) == len(set(lines)), "a message was folded into the recap twice"
    assert second.meta()["recap_folded"] == second.chassis.recap_folded >= folded


def test_a_fold_point_past_a_shortened_conversation_is_clamped(make_run, tmp_path):
    session = tmp_path / "w" / "home" / "session"
    session.mkdir(parents=True)
    (session / "conversation.json").write_text(
        json.dumps([{"role": "user", "content": "kept"}, {"role": "assistant", "content": "only two"}], indent=2) + "\n"
    )
    (session / "run.json").write_text(json.dumps({"recap_folded": 50, "lineage_id": "abc123"}))
    run = make_run([reply("ok")], main=STATUS_MAIN, extra=IMPORT_JSON + STATUS_DUTY, root=tmp_path / "w")
    run.go()
    (status,) = run.duty.STATUS
    assert status["recap_messages_folded"] == 2


def test_a_startup_failure_before_main_writes_no_end_and_touches_no_memory(make_run, tmp_path):
    """Documented: the terminal `finally` covers what follows `main(context)`, not loading the duty."""
    session = tmp_path / "w" / "home" / "session"
    session.mkdir(parents=True)
    saved = json.dumps([{"role": "user", "content": "memory"}], indent=2) + "\n"
    (session / "conversation.json").write_text(saved)
    (session / "run.json").write_text('{"lineage_id": "abc123", "turn": 4}')
    run = make_run([], root=tmp_path / "w")
    (run.root / "work" / "duty.py").write_text("x = 1\n")  # no main
    with pytest.raises(chassis.DutyFault):
        run.go()
    assert (session / "conversation.json").read_text() == saved
    assert json.loads((session / "run.json").read_text()) == {"lineage_id": "abc123", "turn": 4}
    assert not [r for r in run.lifecycle() if r["event"] == "run_end"]
