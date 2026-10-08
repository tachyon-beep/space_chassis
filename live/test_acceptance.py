"""The spec's acceptance checks (section 9), against the smoke stack.

The tests share one stack and run in file order, and the ladder's state persists for a container's
life, so each names its agent: 9.7 is agent_3 (capped from the start); 9.1 and 9.4 are agent_1;
9.2, 9.3, 9.5 and 9.8 are agent_2, which 9.2 and 9.3 reseed. A committed change to agent.py takes
effect at the next spawn, which a test forces with a SIGKILL of the agent: a signal exit steps the
ladder at once, so nothing waits out an 85-second incarnation.
"""

import re

from probes import (
    commit_and_tag,
    kill_agent,
    mark,
    progress,
    read_text,
    recovery_state,
    sh,
    wait_in_log,
    watchdog_alive,
)
from stack import wait_for

# `done` restores, clears the build area and sleeps 60 s before the next spawn.
AFTER_DONE = 150
BROKEN = "import sys\nsys.exit(1)\n"


def _note(ref: str, kind: str) -> str:
    return rf"Restored {re.escape(ref)} at [0-9a-f]+; {kind} incarnation\."


def _sessions_archived(stack, n: int) -> int:
    listing = sh(stack, n, "ls /work/tombstones 2>/dev/null || true")
    return len(
        [name for name in listing.split() if re.fullmatch(r"session_recovery_\d+\.json", name)]
    )


# --------------------------------------------------------------------- 9.7


def test_the_per_agent_cap_refuses_and_the_agent_pauses_with_jitter(stack):
    transcript = stack.volumes / "transcripts_agent_3" / "data" / "agent_life_transcript.jsonl"

    def refused():
        try:
            return "request(s) per hour" in transcript.read_text(encoding="utf-8")
        except OSError:
            return False

    wait_for(refused, timeout=180, every=3, what="a 429 for agent_3 in its transcript")
    # In agent_3's own log the refusal comes before the pause, so a pause from anything else
    # (a chassis that started before its recorder listened) cannot pass for the cap's.
    wait_in_log(stack, 3, 0, r"429 .*request\(s\) per hour", r"action pause", timeout=180)
    assert watchdog_alive(stack, 3)


# --------------------------------------------------------------------- 9.1


def test_an_agent_that_moves_baseline_to_its_own_code_and_calls_done_starts_fresh_on_it(stack):
    archived = _sessions_archived(stack, 1)
    stack.cue(
        1,
        "run",
        {
            "command": "printf '\\nSMOKE_MARK = 1\\n' >> /work/agent.py"
            " && git -C /work commit -qam mark && git -C /work tag -f baseline"
        },
    )
    wait_for(
        lambda: sh(stack, 1, "git -C /work log -1 --format=%s baseline").strip() == "mark",
        timeout=60,
        every=2,
        what="agent_1 to move baseline onto its mark",
    )
    at = mark(stack, 1)
    stack.cue(1, "done", {"message": "marked"})
    wait_in_log(
        stack,
        1,
        at,
        _note("refs/tags/baseline", "fresh"),
        r"agent starting autonomous loop",
        timeout=AFTER_DONE,
    )
    assert "SMOKE_MARK" in read_text(stack, 1, "/work/agent.py")
    assert _sessions_archived(stack, 1) > archived
    session = wait_for(
        lambda: read_text(stack, 1, "/work/session_context.json"),
        timeout=30,
        every=1,
        what="agent_1's new conversation",
    )
    assert "SMOKE_MARK" not in session


# --------------------------------------------------------------------- 9.4


def test_reset_keeps_the_conversation_and_done_archives_it(stack):
    at = mark(stack, 1)
    stack.cue(1, "reset", {})
    wait_in_log(
        stack,
        1,
        at,
        r"checkpoint reset requested; exiting",
        _note("refs/tags/baseline", "preserved"),
        r"resumed session",
        timeout=60,
    )

    archived = _sessions_archived(stack, 1)
    at = mark(stack, 1)
    stack.cue(1, "done", {"message": "archived"})
    wait_in_log(
        stack,
        1,
        at,
        _note("refs/tags/baseline", "fresh"),
        r"agent starting autonomous loop",
        timeout=AFTER_DONE,
    )
    assert _sessions_archived(stack, 1) > archived


# --------------------------------------------------------------------- 9.2


def test_a_broken_release_walks_the_ladder_to_rescue_with_a_note_at_each_step(stack):
    at = mark(stack, 2)
    commit_and_tag(stack, 2, BROKEN, "baseline", "a broken release")
    kill_agent(stack, 2)
    wait_for(
        lambda: (
            ((recovery_state(stack, 2) or {}).get("selected") or {}).get("ref")
            == "refs/tags/rescue"
        ),
        timeout=90,
        every=2,
        what="agent_2's ladder to reach rescue",
    )
    wait_in_log(
        stack,
        2,
        at,
        _note("refs/tags/baseline", "preserved"),
        _note("refs/tags/baseline", "fresh"),
        _note("refs/tags/rescue", "fresh"),
        timeout=30,
    )

    restarts = stack.restart_count("agent_2")
    at = mark(stack, 2)
    commit_and_tag(stack, 2, BROKEN, "rescue", "a broken rescue")
    kill_agent(stack, 2)
    wait_for(
        lambda: stack.restart_count("agent_2") > restarts,
        timeout=90,
        every=2,
        what="agent_2's container to restart on exhaustion",
    )
    wait_in_log(stack, 2, at, r"recovery exhausted", r"started from the image seed", timeout=120)


# --------------------------------------------------------------------- 9.3


def test_an_edited_watchdog_re_executes_and_a_killed_one_reseeds(stack):
    at = mark(stack, 2)
    sh(stack, 2, "printf '\\n# edited by the smoke test\\n' >> /work/watchdog.py")
    wait_in_log(
        stack,
        2,
        at,
        r"watchdog file changed; terminating agent and re-executing self",
        timeout=30,
    )

    restarts = stack.restart_count("agent_2")
    at = mark(stack, 2)
    stack.exec("agent_2", "sh", "-c", "kill -9 $(pgrep -P 1 -f '[w]atchdog\\.py')")
    wait_for(
        lambda: stack.restart_count("agent_2") > restarts,
        timeout=60,
        every=2,
        what="agent_2's container to restart after its watchdog was killed",
    )
    wait_in_log(stack, 2, at, r"started from the image seed", timeout=120)
    assert "edited by the smoke test" not in read_text(stack, 2, "/work/watchdog.py")


# --------------------------------------------------------------------- 9.5


def test_one_agent_s_broken_release_and_a_broken_shared_module_leave_the_others_running(stack):
    restarts = {n: stack.restart_count(f"agent_{n}") for n in (1, 3)}
    before = (progress(stack, 1) or {}).get("completed_at", 0)

    sh(
        stack,
        2,
        "printf 'raise RuntimeError(\"a broken shared module\")\\n' > /shared/smoke_broken.py",
    )
    at = mark(stack, 2)
    commit_and_tag(
        stack,
        2,
        "import sys\nsys.path.insert(0, '/shared')\nimport smoke_broken  # noqa\n",
        "baseline",
        "a release that imports a broken shared module",
    )
    kill_agent(stack, 2)
    wait_in_log(
        stack, 2, at, r"a broken shared module", _note("refs/tags/rescue", "fresh"), timeout=90
    )

    wait_for(
        lambda: (progress(stack, 1) or {}).get("completed_at", 0) > before,
        timeout=180,
        every=3,
        what="agent_1's chassis to complete another call",
    )
    for n, count in restarts.items():
        assert stack.restart_count(f"agent_{n}") == count, f"agent_{n} restarted"
    assert watchdog_alive(stack, 3)


# --------------------------------------------------------------------- 9.8

PLANT = (
    "import os\n"
    "os.makedirs('/shared/markers', exist_ok=True)\n"
    "open(os.path.join('/shared/markers', '{where}-{name}-%d' % os.getpid()), 'w').close()\n"
)
HOOK = "#!/bin/sh\nmkdir -p /shared/markers && : > /shared/markers/git-hook-$$\n"


def test_nothing_planted_in_home_state_or_shared_runs_in_image_owned_processes(stack):
    user_site = sh(stack, 2, "python3 -c 'import site; print(site.getusersitepackages())'").strip()
    places = {"state": "/state", "shared": "/shared", "home": user_site}
    for where, directory in places.items():
        sh(stack, 2, f"mkdir -p '{directory}'")
        for name in ("sitecustomize", "usercustomize"):
            stack.exec(
                "agent_2",
                "sh",
                "-c",
                f"cat > '{directory}/{name}.py'",
                stdin=PLANT.format(where=where, name=name),
            )
    stack.exec(
        "agent_2",
        "sh",
        "-c",
        "mkdir -p /shared/hooks && cat > /shared/hooks/reference-transaction",
        stdin=HOOK,
    )
    sh(
        stack,
        2,
        "chmod +x /shared/hooks/reference-transaction"
        " && cp /shared/hooks/reference-transaction /shared/hooks/post-checkout"
        " && printf '[core]\\n\\thooksPath = /shared/hooks\\n' > \"$HOME/.gitconfig\"",
    )
    markers = stack.volumes / "shared" / "data" / "markers"
    _assert_no_markers(markers)

    # A reset is an elective restore, so the watchdog's git runs whatever phase 9.5 left: a kill
    # here, inside rescue's probation, would exhaust the ladder and reseed with cp, not git.
    at = mark(stack, 2)
    stack.cue(2, "reset", {})
    wait_in_log(
        stack,
        2,
        at,
        r"checkpoint reset requested; exiting",
        r"Restored refs/tags/\w+ at [0-9a-f]+",
        r"agent (starting|resuming)",
        timeout=90,
    )
    _assert_no_markers(markers)

    # The pump, restarted by the entrypoint's loop with the plants in place.
    pumps = sh(stack, 2, "pgrep -f '[p]ump\\.py' || true").split()
    assert pumps, "agent_2 runs no pump"
    stack.exec("agent_2", "pkill", "-f", "pump\\.py")
    wait_for(
        lambda: set(sh(stack, 2, "pgrep -f '[p]ump\\.py' || true").split()) - set(pumps),
        timeout=30,
        every=1,
        what="agent_2's pump to be restarted",
    )
    _assert_no_markers(markers)

    # A reseeded watchdog, booting with the /state and /shared plants still on their volumes (HOME
    # is a tmpfs, so its plants go with the old container): a broken rescue exhausts the ladder.
    restarts = stack.restart_count("agent_2")
    at = mark(stack, 2)
    commit_and_tag(stack, 2, BROKEN, "rescue", "a broken rescue, to reseed with the plants")
    kill_agent(stack, 2)
    wait_for(
        lambda: stack.restart_count("agent_2") > restarts,
        timeout=90,
        every=2,
        what="agent_2 to reseed with the plants in place",
    )
    wait_in_log(
        stack, 2, at, r"started from the image seed", r"agent starting autonomous loop", timeout=120
    )
    _assert_no_markers(markers)


def _assert_no_markers(markers) -> None:
    found = sorted(path.name for path in markers.iterdir()) if markers.exists() else []
    assert not found, found
