"""What the live tests ask of a running agent, in one place.

`docker compose logs` is append-only across a container's restarts, and the first boot already
prints the lines a later test waits for (`started from the image seed`, `resumed session`). So
every log assertion is made on what was printed after a mark: `mark()` before the trigger,
`since()` after it.
"""

import json
import re

from stack import SmokeStack, wait_for

PG_ISREADY = (
    'for b in /usr/lib/postgresql/*/bin/pg_isready; do exec "$b" -q -h /run/agent; done; exit 1'
)
# The agent the watchdog spawned: `<python> /work/agent.py`, never the watchdog or a shell.
AGENT_PROCESS = " /work/agent\\.py$"


def agent(n: int) -> str:
    return f"agent_{n}"


def postgres_answers(stack: SmokeStack, n: int) -> bool:
    return stack.exec(agent(n), "sh", "-c", PG_ISREADY).returncode == 0


def sh(stack: SmokeStack, n: int, script: str) -> str:
    """Run a shell script in agent n as the agent's user; fail loudly if it fails."""
    result = stack.exec(agent(n), "sh", "-c", script)
    assert result.returncode == 0, f"agent_{n}: {script}\n{result.stdout}{result.stderr}"
    return result.stdout


def read_text(stack: SmokeStack, n: int, path: str) -> str | None:
    result = stack.exec(agent(n), "cat", path)
    return result.stdout if result.returncode == 0 else None


def read_json(stack: SmokeStack, n: int, path: str):
    text = read_text(stack, n, path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def mark(stack: SmokeStack, n: int) -> int:
    return len(stack.logs(agent(n)))


def since(stack: SmokeStack, n: int, at: int) -> str:
    return stack.logs(agent(n))[at:]


def wait_in_log(stack: SmokeStack, n: int, at: int, *patterns: str, timeout: float) -> str:
    """Wait until the patterns appear in order after the mark; return the log since the mark."""

    def found():
        text = since(stack, n, at)
        position = 0
        for pattern in patterns:
            match = re.compile(pattern).search(text, position)
            if match is None:
                return None
            position = match.end()
        return text

    return wait_for(found, timeout=timeout, every=2, what=f"agent_{n} to log {patterns}")


def kill_agent(stack: SmokeStack, n: int) -> None:
    """SIGKILL the spawned agent: a signal exit, so the ladder steps at once."""
    result = stack.exec(agent(n), "pkill", "-9", "-f", AGENT_PROCESS)
    assert result.returncode == 0, f"no agent process in agent_{n}: {result.stderr}"


def watchdog_alive(stack: SmokeStack, n: int) -> bool:
    return stack.exec(agent(n), "pgrep", "-P", "1", "-f", "watchdog\\.py").returncode == 0


def commit_and_tag(stack: SmokeStack, n: int, text: str, tag: str, message: str) -> None:
    """Replace /work/agent.py with text, commit it, and move tag onto the commit."""
    result = stack.exec(
        agent(n),
        "sh",
        "-c",
        f"cd /work && cat > agent.py && git commit -qam '{message}' && git tag -f {tag} >/dev/null",
        stdin=text,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def recovery_state(stack: SmokeStack, n: int):
    return read_json(stack, n, "/work/.git/aurora-recovery.json")


def progress(stack: SmokeStack, n: int):
    return read_json(stack, n, "/work/.git/aurora-progress.json")
