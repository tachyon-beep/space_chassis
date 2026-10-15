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


def _plant(tmp_path, agents, count=None):
    (tmp_path / "operator").mkdir(exist_ok=True)
    roster = {"count": len(agents) if count is None else count, "seed": 1, "agents": agents}
    (tmp_path / "operator" / "roster.json").write_text(json.dumps(roster))
    (tmp_path / ".env").write_text("KEEP=1\n")


def _entry(n, slug, name=None):
    return {"agent": f"agent_{n}", "name": name or slug, "slug": slug, "category": "animal"}


def _refused(tmp_path):
    result = _roster("--roster-dir", "operator", "--env-file", ".env", cwd=tmp_path)
    assert result.returncode != 0
    assert "roster" in result.stderr
    assert (tmp_path / ".env").read_text() == "KEEP=1\n"


def test_a_roster_carrying_an_environment_injection_is_refused_and_env_untouched(tmp_path):
    # The roster prepare_host carries forward came from a volume every agent could write: a slug
    # with a newline would put any variable into the environment compose hands every service.
    _plant(tmp_path, [_entry(1, "x\nLLM_BASE_URL=http://elsewhere")])
    _refused(tmp_path)


def test_a_roster_slug_that_climbs_out_of_a_path_is_refused(tmp_path):
    _plant(tmp_path, [_entry(1, "../x")])
    _refused(tmp_path)


def test_a_roster_whose_agents_are_not_numbered_one_to_n_is_refused(tmp_path):
    _plant(tmp_path, [{"agent": "agent_1;x", "name": "ibex", "slug": "ibex", "category": "animal"}])
    _refused(tmp_path)


def test_a_roster_whose_count_disagrees_with_its_agents_is_refused(tmp_path):
    _plant(tmp_path, [_entry(1, "ibex")], count=2)
    _refused(tmp_path)


def test_a_roster_with_a_repeated_slug_is_refused(tmp_path):
    _plant(tmp_path, [_entry(1, "ibex"), _entry(2, "ibex")])
    _refused(tmp_path)


def test_the_roster_prints_without_its_retired_columns(tmp_path):
    """print_roster read the retired `mount` field (plan 5): a regression guard on the printout."""
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "roster.py"),
            "--count",
            "2",
            "--seed",
            "1",
            "--roster-dir",
            str(tmp_path / "operator"),
            "--env-file",
            str(tmp_path / "test.env"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "2 agents, seed 1" in result.stdout
