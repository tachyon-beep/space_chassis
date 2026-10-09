"""Claims the documents and the drafts must not make, because the code says otherwise.

Plan 5's final review found each of these in text that had just been rewritten: a `done` that keeps
the agent's code, a pump whose processes survive a restart, a raw API that reaches past the
panel's window, and agent-facing text that promised safety for more than the agent's own harness.
Each pattern names the claim; the reason is the code that makes it false.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ("CLAUDE.md", "AGENTS.md", "README.md", "docs/design.md", ".env.example")
# What the agents are told, and the table of its claims with their sources (spec §6).
AGENT_FACING = ("harness/system_prompt.txt", "brief/WORLD.md", "docs/brief-claims.md")

FALSE = {
    # watchdog.Recovery.elective restores a checkpoint and cleans the tree; uncommitted work goes.
    r"on the same code": "done restores a checkpoint tag",
    r"`done` only clears the context": "done restores a checkpoint tag",
    # pump.restore_records: no entry is restored as running; a spent `once` stays spent.
    r"surviving everything": "the pump's processes die with the container",
    r"keeps\s+running\s+across": "the pump's processes die with the container",
    r"pump survives runs, repairs and restarts": "the pump's processes die with the container",
    # review.Transcript.raw reads the same bounded tail as the page.
    r"one\s+(?:link|click)\s+away": "the raw API serves only the loaded window",
    # The agent can damage /shared, its siblings' services, the window image and the fleet's pool;
    # nothing brings back a watchdog it leaves hung.
    r"What you can damage on this side is yourself": "agents can damage each other",
    r"always\s+be\s+brought\s+back": "a hung watchdog is brought back by nothing",
}


@pytest.mark.parametrize("name", DOCS + AGENT_FACING)
def test_no_document_makes_a_claim_the_code_contradicts(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    found = [
        f"{name}: {pattern!r} ({reason})"
        for pattern, reason in FALSE.items()
        if re.search(pattern, text)
    ]
    assert found == []


def test_the_prompt_names_where_one_agent_can_harm_another():
    text = (ROOT / "harness/system_prompt.txt").read_text(encoding="utf-8")
    assert "/shared" in text and "fleet" in text


def test_the_brief_does_not_offer_telemetry_as_storage():
    # watchdog.mirror_work deletes everything under the mirror it did not put there.
    text = (ROOT / "brief/WORLD.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| `/telemetry`"))
    assert "Yes." not in row and "deleted" in row, row


def test_the_prompts_point_at_the_brief():
    # Spec §6: the unassigned-world passages are replaced by a pointer to /opt/brief.
    prompts = [
        (ROOT / "harness" / name).read_text(encoding="utf-8")
        for name in ("system_prompt.txt", "user_prompt.txt")
    ]
    assert any("/opt/brief" in text for text in prompts)
