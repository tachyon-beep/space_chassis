"""Read a compose environment file the way docker compose reads it.

Ported from Aurora's scripts/build_console_seed.py (42faf41, lines 41-93) so the volume tooling
here reads `.env` exactly as compose does: the last active assignment wins, an `export ` prefix is
not part of the name, a matched pair of quotes is stripped, and an unquoted value ends at
whitespace followed by a hash. This is operator tooling, run on the host; it ships in no image.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_QUOTED = re.compile(r"\A(?:\"([^\"]*)\"|'([^']*)')")
_INLINE_COMMENT = re.compile(r"\s#")


def _value_text(raw: str) -> str:
    """One assignment's value, read the way docker compose reads it."""
    value = raw.strip()
    quoted = _QUOTED.match(value)
    if quoted:
        return quoted.group(1) if quoted.group(1) is not None else quoted.group(2)
    return _INLINE_COMMENT.split(value, maxsplit=1)[0].strip()


def env_value(key: str, path: Path) -> str | None:
    """The value of the last active assignment of key in an environment file, or None."""
    prefix = key + "="
    value = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if line.startswith(prefix):
            value = _value_text(line[len(prefix) :])
    return value


def source_path(root: Path = REPO_ROOT) -> Path:
    """The live .env if there is one, else .env.example."""
    live = root / ".env"
    if live.exists():
        return live
    return root / ".env.example"
