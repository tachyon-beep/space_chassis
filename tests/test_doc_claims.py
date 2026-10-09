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
    # tests/test_live_stack.py and tests/test_compose_generated.py call the compose CLI.
    r"no Docker( needed| required)?\b": "a few offline tests parse compose with the docker CLI",
    # tests/test_vehicle_reconciliation.py importorskips yaml; a harness telemetry test skips.
    r"Tests never skip": "two tests skip",
    # core_caps.FleetLedger counts a rolling hour.
    r"on the clock hour": "the fleet pool is a rolling hour",
    # journal._wanted keeps objects, packs and refs; the archived conversations never reach it.
    r"archived\s+conversations\s+and\s+all": "the journal keeps objects and refs only",
    # /diode/<slug> is a directory inside one shared window image.
    r"`/diode/<slug>` \| that agent's own bounded volume images": "the window image is shared",
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


def test_claude_md_states_43_s_escalation_and_where_the_vehicle_lives():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| 43 |"))
    assert "600 s" in row, row  # watchdog: three 43s inside 600 s escalate the tier
    vehicle = next(line for line in text.splitlines() if "/opt/vehicle" in line)
    # The vehicle's own image alone carries it (Dockerfile.agent's stages; John, 2026-10-10).
    assert "space-chassis-vehicle" in vehicle and "no agent" in vehicle, vehicle


def test_every_default_the_example_states_is_the_one_compose_uses():
    import re as _re

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    defaults = dict(_re.findall(r"\$\{([A-Z0-9_]+):-([^}$]*)\}", compose))
    wrong = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        match = _re.fullmatch(r"#?([A-Z][A-Z0-9_]*)=(\S+)", line)
        if match and defaults.get(match[1]) and defaults[match[1]] != match[2]:
            wrong.append(f"{match[1]}: example {match[2]}, compose {defaults[match[1]]}")
    assert wrong == []


def test_the_brief_states_the_archive_bound_the_watchdog_keeps():
    # John approved the clause on 2026-10-09; its figures are the seed watchdog's own.
    text = (ROOT / "brief/WORLD.md").read_text(encoding="utf-8")
    watchdog = (ROOT / "harness/watchdog.py").read_text(encoding="utf-8")
    assert "ARCHIVE_KEEP = 20" in watchdog
    assert "ARCHIVE_TOMBSTONE_BYTES = 128 * 1024 * 1024" in watchdog
    assert "ARCHIVE_GIT_BYTES = 64 * 1024 * 1024" in watchdog
    assert "Archived conversations are bounded" in text
    assert "newest twenty" in text and "128 MiB" in text and "64 MiB" in text
    for name in ("session_recovery_<n>.json", "corrupt_session_<date>_<time>_<micro>.json"):
        assert name in text, name


def test_the_root_instructions_point_at_governance():
    for name in ("CLAUDE.md", "AGENTS.md"):
        assert "governance/README.md" in (ROOT / name).read_text(encoding="utf-8"), name


def test_the_readme_says_images_built_before_the_split_carry_the_vehicle():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "built before 2026-10-10" in text and "verify_containment.sh" in text


def test_no_document_says_the_vehicle_runs_a_console_per_window():
    # serve_vehicle.sh execs one executive for every window (plan 7, Task 1).
    for name in DOCS:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not re.search(r"one (console|process) per (slug|window)", text), name


def test_the_readme_gives_the_operator_the_vehicle_s_procedures():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    section = text[text.index("## The vehicle") :]
    section = section[: section.index("\n## ", 1)]
    for phrase in (
        "first start",
        "resumes",
        "exactly one result",
        "new world",
        "stop the fleet",
        "exit 3",
        "VEHICLE_SLUGS",
        "--closed-interlock",
        "rebuild of the vehicle image",
        "Python patch version",
        "configuration or engine code",
        "kernel update",
        "pinned by digest",
        "checkpoint interval",
        "not wired",
    ):
        assert phrase in section, phrase
    # Clearing a window keeps its directory: agent binds use create_host_path: false.
    assert "`volumes/diode/data/*`'s contents" not in section


def test_claude_md_states_the_vehicle_s_private_state_and_one_executive():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    row = next(
        line for line in text.splitlines() if "/opt/vehicle" in line and line.startswith("|")
    )
    assert "/state" in row and "one process for every window" in row, row


def test_a_new_world_archives_the_window_root_s_identity_too():
    # The window root's .executive.json binds the old world; left behind, the console refuses.
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    start = text.index("- **A deliberate new world**")
    bullet = text[start : text.index("\n- **", start + 1)]
    assert ".executive.json" in bullet, bullet
