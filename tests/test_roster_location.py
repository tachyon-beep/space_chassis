"""The roster lives in the operator's directory, not in a volume the agents share.

Under the Aurora port every agent has its own harness and nothing is shared by default, so the
names are the operator's bookkeeping: drawn into `operator/roster.json` and written into `.env`,
which compose and the volume tooling read.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROSTER = REPO / "scripts" / "roster.py"
SLUG = re.compile(r"[a-z][a-z0-9_]*")


def _roster(*args, cwd):
    return subprocess.run(
        [sys.executable, str(ROSTER), *args], cwd=cwd, capture_output=True, text=True, timeout=30
    )


def _env_slugs(path):
    text = path.read_text()
    count = int(re.search(r"^FLEET_COUNT=(\d+)$", text, re.M).group(1))
    return [re.search(rf"^FLEET_{n}_SLUG=(\S+)$", text, re.M).group(1) for n in range(1, count + 1)]


def test_the_roster_is_written_to_the_operator_directory(tmp_path):
    result = _roster(
        "--count",
        "3",
        "--seed",
        "1",
        "--roster-dir",
        "operator",
        "--env-file",
        ".env",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    roster = json.loads((tmp_path / "operator" / "roster.json").read_text())
    assert [entry["slug"] for entry in roster["agents"]] == _env_slugs(tmp_path / ".env")


def test_the_old_work_dir_flag_still_writes_but_says_it_is_deprecated(tmp_path):
    result = _roster(
        "--count", "2", "--seed", "1", "--work-dir", "old", "--env-file", "", cwd=tmp_path
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "old" / "roster.json").exists()
    assert "--work-dir is deprecated" in result.stderr


def test_every_drawn_slug_fits_the_image_name_alphabet():
    sys.path.insert(0, str(REPO / "scripts"))
    import roster  # noqa: PLC0415

    for seed in range(200):
        for slug in roster.slugs(roster.draw(roster.DEFAULT_COUNT, seed)):
            assert SLUG.fullmatch(slug), slug


def test_status_reads_the_operator_roster():
    sys.path.insert(0, str(REPO / "scripts"))
    import status  # noqa: PLC0415

    assert status.ROSTER_PATH == REPO / "operator" / "roster.json"


def test_an_existing_roster_refreshes_the_env_block(tmp_path):
    _roster(
        "--count", "3", "--seed", "7", "--roster-dir", "operator", "--env-file", "", cwd=tmp_path
    )
    result = _roster("--roster-dir", "operator", "--env-file", "fresh.env", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    roster = json.loads((tmp_path / "operator" / "roster.json").read_text())
    assert _env_slugs(tmp_path / "fresh.env") == [entry["slug"] for entry in roster["agents"]]
