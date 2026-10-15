"""The first live checks: the image builds, each agent's world is up, and the walls hold (spec 9.6)."""

import subprocess

from probes import postgres_answers, progress
from stack import REPO, allowed_environment, wait_for


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
    for n in range(1, stack.agents + 1):
        assert f"PASS  agent_{n} has no vehicle in its image" in result.stdout, n
        assert f"PASS  agent_{n} mounts nothing of the vehicle's source" in result.stdout, n


DEEP_REQUEST = r"""
import socket
body = b"[" * 100000 + b"]" * 100000
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(30)
s.connect("/llm/sock/core.sock")
s.sendall(
    b"POST /api/v1/chat/completions HTTP/1.1\r\nHost: localhost\r\n"
    b"Content-Type: application/json\r\nConnection: close\r\n"
    b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
)
reply = b""
while True:
    piece = s.recv(65536)
    if not piece:
        break
    reply += piece
print(reply.decode("utf-8", "replace"))
"""


def test_an_agent_s_deeply_nested_request_is_refused_by_its_recorder(stack):
    before = (progress(stack, 1) or {}).get("completed_at", 0)
    result = stack.exec("agent_1", "python3", "-c", DEEP_REQUEST)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("HTTP/1.0 400") or result.stdout.startswith("HTTP/1.1 400")
    assert "structure_limit" in result.stdout
    wait_for(
        lambda: (progress(stack, 1) or {}).get("completed_at", 0) > before,
        timeout=120,
        every=3,
        what="agent_1's chassis to keep completing calls",
    )
