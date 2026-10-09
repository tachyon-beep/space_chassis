"""The agent image's Python floor (spec §9: test_agent_dependencies, ported from Aurora at 42faf41).

Aurora's version pins its own manifest and the Dockerfile's install of it. This world's manifest is
its own -- a scientific and systems toolkit with the drivers for the database and the bus -- so the
exact list is pinned here: a change to it is a decision about capability, and should show in a
diff of this test. Aurora-only entries (its garden, books and stage dependencies, filigree,
model2vec, pypdf, netCDF4 and the like) are not part of this world.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXPECTED = [
    "openai<3",
    "httpx<1",
    "numpy",
    "scipy",
    "sympy",
    "sortedcontainers",
    "more-itertools",
    "python-dateutil",
    "networkx",
    "z3-solver",
    "skyfield",
    "jplephem",
    "sgp4",
    "pandas",
    "pyarrow",
    "duckdb",
    "aiosqlite",
    "msgpack",
    "orjson",
    "pydantic",
    "jsonschema",
    "sqlalchemy",
    "psycopg[binary,pool]",
    "asyncpg",
    "redis",
    "valkey",
    "nats-py",
    "aio-pika",
    "pyzmq",
    "psutil",
    "watchfiles",
    "tenacity",
    "uvloop",
    "anyio",
    "fastapi",
    "uvicorn",
    "websockets",
    "jinja2",
    "prompt_toolkit",
    "typer",
    "rich",
    "pyyaml",
    "tomli-w",
    "beautifulsoup4",
    "markdownify",
    "lxml",
    "pypdf",
    "pygments",
    "lark",
    "pytest",
    "pytest-asyncio",
    "pytest-timeout",
    "hypothesis",
    "ruff",
    "mypy",
    "pillow",
    "matplotlib",
]


def _requirements():
    return [
        line.strip()
        for line in (ROOT / "requirements-agent.txt").read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_the_manifest_is_exactly_the_pinned_list():
    assert _requirements() == EXPECTED


def test_the_harness_s_own_needs_are_in_it():
    for requirement in ("openai<3", "httpx<1", "pyyaml"):
        assert requirement in EXPECTED, requirement


def test_the_image_installs_the_manifest_after_copying_it():
    dockerfile = (ROOT / "Dockerfile.agent").read_text()
    copy = dockerfile.index("COPY requirements-agent.txt /opt/requirements-agent.txt")
    install = dockerfile.index("RUN pip install --no-cache-dir -r /opt/requirements-agent.txt")
    assert copy < install
    assert re.search(
        r"RUN pip install --no-cache-dir -r /opt/requirements-agent\.txt\n", dockerfile
    )
