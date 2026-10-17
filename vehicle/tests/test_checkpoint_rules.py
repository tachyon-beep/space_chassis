"""A checkpoint refuses to resume across a domain-rule change (D5; ADR 0002 I's `engine`).

`checkpoint.engine_identity` hashed the corpus and the three engine tools, and the domain rules in
`domains/<name>/rules.py` were neither: a run checkpointed before a rule changed would resume after it
with physics nobody had checkpointed under. They are hashed now, beside the corpus.
"""

from __future__ import annotations

import dataclasses
import shutil
import sys
from pathlib import Path

import pytest

VEHICLE = Path(__file__).resolve().parents[1]
if str(VEHICLE / "tools") not in sys.path:
    sys.path.insert(0, str(VEHICLE / "tools"))
import checkpoint  # noqa: E402
import plant  # noqa: E402


def engine_copy(destination: Path) -> Path:
    """What the engine identity reads, copied: the corpus, the domains and the engine tools."""
    destination.mkdir(parents=True)
    for name in plant.CORPUS_TOP_LEVEL:
        shutil.copy(VEHICLE / name, destination / name)
    shutil.copytree(VEHICLE / "domains", destination / "domains")
    (destination / "tools").mkdir()
    for name in checkpoint.ENGINE_TOOLS:
        shutil.copy(VEHICLE / name, destination / name)
    return destination


def test_every_domain_rule_file_is_part_of_the_engine():
    rules = [p.relative_to(VEHICLE).as_posix() for p in plant.domain_rule_files(VEHICLE)]
    assert {"domains/comms/rules.py", "domains/power/rules.py", "domains/thermal/rules.py"} <= set(
        rules
    )
    assert rules == sorted(rules)


def test_a_rule_change_changes_the_engine_and_a_byte_elsewhere_in_the_domain_folder_does_not(
    tmp_path,
):
    copy = engine_copy(tmp_path / "vehicle")
    baseline = checkpoint.engine_identity(copy)
    assert baseline == checkpoint.engine_identity(VEHICLE), "the copy is the engine, byte for byte"

    # Not a rule: a stray file in a domain folder is not physics.
    (copy / "domains" / "thermal" / "NOTES.txt").write_text("a reader's note\n")
    assert checkpoint.engine_identity(copy) == baseline

    # A rule: one comment changes the bytes a run would execute under.
    rules = copy / "domains" / "thermal" / plant.RULES_FILE
    rules.write_text(rules.read_text() + "\n# a rule change\n")
    changed = checkpoint.engine_identity(copy)
    assert changed != baseline

    # A rule file added where there was none is a change too, and so is one removed.
    rules.write_text((VEHICLE / "domains" / "thermal" / plant.RULES_FILE).read_text())
    assert checkpoint.engine_identity(copy) == baseline
    added = copy / "domains" / "crew" / plant.RULES_FILE
    added.write_text("RULES = {}\n")
    assert checkpoint.engine_identity(copy) != baseline
    added.unlink()
    (copy / "domains" / "comms" / plant.RULES_FILE).unlink()
    assert checkpoint.engine_identity(copy) != baseline


def test_a_checkpoint_refuses_to_resume_across_a_rule_change(tmp_path):
    """What a checkpoint is stamped with (`Compatibility.current`) moves in `engine` and nowhere
    else when a rule changes; `test_each_checkpoint_incompatibility_is_refused_with_no_fallback`
    holds that a checkpoint whose `engine` differs is refused by name and never fallen back from."""
    copy = engine_copy(tmp_path / "vehicle")
    stamped = checkpoint.Compatibility.current(plant.load_world(copy))
    rules = copy / "domains" / "power" / plant.RULES_FILE
    rules.write_text(rules.read_text() + "\n# a rule change\n")
    resuming = checkpoint.Compatibility.current(plant.load_world(copy))
    assert resuming.engine != stamped.engine
    assert dataclasses.replace(resuming, engine=stamped.engine) == stamped


def test_an_unreadable_domains_folder_raises_rather_than_hashing_fewer_rules(tmp_path, monkeypatch):
    copy = engine_copy(tmp_path / "vehicle")
    real = plant.os.scandir

    def failing(path):
        if Path(path) == copy / "domains" / "power":
            raise OSError(5, "Input/output error", str(path))
        return real(path)

    monkeypatch.setattr(plant.os, "scandir", failing)
    with pytest.raises(OSError, match="power"):
        plant.domain_rule_files(copy)
