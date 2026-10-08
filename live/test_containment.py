"""The first live checks: the image builds, each agent's world is up, and the walls hold (spec 9.6)."""

import subprocess

from probes import postgres_answers
from stack import REPO, allowed_environment


def test_the_image_builds_and_each_agent_s_postgres_answers(stack):
    for n in range(1, stack.agents + 1):
        assert postgres_answers(stack, n), f"agent_{n}'s postgres does not answer"


def test_containment_holds_for_every_agent(stack):
    agents = " ".join(f"agent_{n}" for n in range(1, stack.agents + 1))
    result = subprocess.run(
        ["sh", str(REPO / "scripts" / "verify_containment.sh")],
        cwd=REPO,
        env=allowed_environment({"COMPOSE": " ".join(stack.compose_command()), "AGENTS": agents}),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS  agent_3 has no trace of its recorder's real key" in result.stdout
