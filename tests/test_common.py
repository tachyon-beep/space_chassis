"""common.append_jsonl: the operator's own logs are bounded by rotation, never by truncation.

fleet.jsonl (a line every pass of the monitor), and the journal's journal.jsonl and shared.jsonl,
sit on bounded images; each rotates to one previous generation past its cap (639443e993).
"""

import json

import common


def _lines(path):
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_append_rotates_to_one_previous_generation_past_the_cap(tmp_path):
    path = tmp_path / "fleet.jsonl"
    previous = common.previous_generation(path)
    assert previous == tmp_path / "fleet.1.jsonl"
    written_since_rotation = 0
    for n in range(10):
        before = path.stat().st_ino if path.exists() else None
        common.append_jsonl(path, {"n": n, "pad": "x" * 30}, max_bytes=200)
        rotated = before is not None and path.stat().st_ino != before
        written_since_rotation = 1 if rotated else written_since_rotation + 1
    assert previous.exists()
    assert json.loads(_lines(path)[-1])["n"] == 9
    assert len(_lines(path)) == written_since_rotation
    assert path.stat().st_size <= 200


def test_a_second_rotation_replaces_the_previous_generation(tmp_path):
    path = tmp_path / "log.jsonl"
    for n in range(3):
        common.append_jsonl(path, {"n": n, "pad": "x" * 100}, max_bytes=120)
    # Each record overflows the cap with the one before it: three generations were made, one is kept.
    assert [json.loads(line)["n"] for line in _lines(common.previous_generation(path))] == [1]
    assert [json.loads(line)["n"] for line in _lines(path)] == [2]


def test_a_record_larger_than_the_cap_is_still_written_whole(tmp_path):
    path = tmp_path / "log.jsonl"
    common.append_jsonl(path, {"big": "y" * 500}, max_bytes=100)
    common.append_jsonl(path, {"big": "z" * 500}, max_bytes=100)
    assert json.loads(_lines(path)[0])["big"] == "z" * 500
    assert json.loads(_lines(common.previous_generation(path))[0])["big"] == "y" * 500


def test_rotation_renames_and_never_truncates(tmp_path):
    path = tmp_path / "log.jsonl"
    common.append_jsonl(path, {"n": 0, "pad": "x" * 100}, max_bytes=120)
    inode = path.stat().st_ino
    common.append_jsonl(path, {"n": 1, "pad": "x" * 100}, max_bytes=120)
    assert common.previous_generation(path).stat().st_ino == inode


def test_a_failed_rotation_still_appends(tmp_path):
    path = tmp_path / "log.jsonl"
    common.previous_generation(path).mkdir()
    common.append_jsonl(path, {"n": 0, "pad": "x" * 100}, max_bytes=120)
    common.append_jsonl(path, {"n": 1, "pad": "x" * 100}, max_bytes=120)
    assert [json.loads(line)["n"] for line in _lines(path)] == [0, 1]


def test_the_cap_counts_bytes_not_characters(tmp_path):
    path = tmp_path / "log.jsonl"
    record = {"s": "é" * 40}  # 40 characters, 80 bytes in UTF-8
    line_bytes = len(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode()) + 1
    common.append_jsonl(path, record, max_bytes=line_bytes + 10)
    common.append_jsonl(path, record, max_bytes=line_bytes + 10)
    assert common.previous_generation(path).exists()
