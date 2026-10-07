"""Pure text and id helpers: normalization, escaped-unit truncation, wire ids (SV-019 K-E1).

Expected values are SV-015 v2 section 2.3, which replaces SV-013's UTF-8 byte
rules: caps are measured in escaped units E(s) = len(json.dumps(s,
ensure_ascii=True)) - 2, a lone surrogate normalizes to `?`, and truncation
keeps the longest code-point prefix that fits with its marker, whose K/N/hash
are over the normalized UTF-8. Fixtures: revised C-B1...C-B4 (v2 table),
O4-1 (control characters), C-B8...C-B11, O4-9 and O4-12 (seeded `used`).

These helpers are pure. Nothing here wires them into a response envelope
(SV-013 K-E2), and nothing claims a provider accepts rewritten ids.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "services"))

import chassis  # noqa: E402
from chassis import assign_wire_ids, escaped_units, normalize_text, truncate_marked  # noqa: E402


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Escaped units and normalization
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "units"),
    [
        ("a", 1),
        ('"', 2),
        ("\\", 2),
        ("\n", 2),
        ("\t", 2),
        ("\x00", 6),
        ("\x1f", 6),
        ("\x7f", 6),  # DEL is not printable ASCII; json.dumps escapes it
        ("é", 6),
        ("€", 6),
        (" ", 6),
        ("\U0001f600", 12),
        (" ", 6),
        ("", 0),
    ],
)
def test_escaped_units_are_the_ascii_json_length(text, units):
    assert escaped_units(text) == units == len(json.dumps(text, ensure_ascii=True)) - 2


def test_a_lone_surrogate_becomes_a_question_mark_and_is_counted():
    """C-B11: `b'?x'`, one replacement (SV-011 S9e's U+FFFD was wrong)."""
    assert normalize_text("\ud800x") == ("?x", 1)
    assert normalize_text("ok") == ("ok", 0)
    halves = chr(0xD83D) + chr(0xDE00)  # a surrogate pair as two separate code points
    assert normalize_text(halves) == ("??", 2), "two lone halves are two replacements"
    assert normalize_text("\U0001f600") == ("\U0001f600", 0), "a real astral character is not a surrogate"


# ---------------------------------------------------------------------------
# Truncation with a marker, in escaped units
# ---------------------------------------------------------------------------
MARKER = "\n[truncated: kept {k} of {n} bytes; sha256 {h}]"


@pytest.mark.parametrize(
    ("text", "kept", "k", "n", "h_start", "h_end", "units", "utf8"),
    [
        ("é" * 79, "é" * 8, 16, 158, "e17ca1e8", "c0c4", 156, 123),  # C-B1
        ("é" * 80, "é" * 8, 16, 160, "4d214f0a", "5e18", 156, 123),  # C-B2
        ("é" * 81, "é" * 8, 16, 162, "dc90a767", "adc5", 156, 123),  # C-B3
        ("a" + "é" * 81, "a" + "é" * 8, 17, 163, "679adb94", "ed45", 157, 124),  # C-B4
        ("\x00" * 160, "\x00" * 8, 8, 160, "b3939788", "c2e4", 155, 114),  # O4-1
    ],
    ids=["C-B1", "C-B2", "C-B3", "C-B4", "O4-1"],
)
def test_revised_truncation_fixtures(text, kept, k, n, h_start, h_end, units, utf8):
    h = sha(text)
    assert h.startswith(h_start) and h.endswith(h_end), "the fixture's own hash"
    stored, info = truncate_marked(text, 160)
    assert stored == kept + MARKER.format(k=k, n=n, h=h)
    assert escaped_units(stored) == units <= 160
    assert len(stored.encode("utf-8")) == utf8
    assert info == {
        "truncated": True,
        "kept_bytes": k,
        "original_bytes": n,
        "sha256": h,
        "replaced_chars": 0,
        "escaped_units": units,
    }
    # The longest prefix: one more character would not fit with its marker.
    longer = text[: len(kept) + 1]
    longer_bytes = len(longer.encode("utf-8"))
    assert escaped_units(longer) + escaped_units(MARKER.format(k=longer_bytes, n=n, h=h)) > 160


def test_c_b3_and_c_b4_hashes_are_the_full_published_values():
    assert sha("é" * 81) == "dc90a767a9bc18e17db69cd71cae06b68a45222c39b9750314997297caaeadc5"
    assert sha("a" + "é" * 81) == "679adb94e2cccbd42b651fa2b8f7c5b6f21cca56d45bd2d621edf7d22e20ed45"


def test_text_within_the_cap_is_kept_whole_and_normalized():
    stored, info = truncate_marked("é" * 26, 160)  # 156 escaped units
    assert stored == "é" * 26 and info["truncated"] is False and info["escaped_units"] == 156
    stored, info = truncate_marked("\ud800x", 160)
    assert stored == "?x" and info["replaced_chars"] == 1 and not info["truncated"]


def test_truncation_measures_the_normalized_text():
    """A lone surrogate counts as `?` in K, N and the hash, never as an encoding error."""
    text = "\ud800" + "b" * 400
    normalized = "?" + "b" * 400
    stored, info = truncate_marked(text, 160)
    assert info["sha256"] == sha(normalized) and info["original_bytes"] == 401
    assert info["replaced_chars"] == 1 and stored.startswith("?b")
    assert escaped_units(stored) <= 160


def test_an_astral_character_is_never_split():
    stored, info = truncate_marked("\U0001f600" * 40, 160)
    kept = stored.split("\n[truncated")[0]
    assert kept == "\U0001f600" * len(kept) and info["kept_bytes"] == 4 * len(kept)
    assert escaped_units(stored) <= 160


def test_a_cap_too_small_for_any_marker_is_refused():
    with pytest.raises(ValueError):
        truncate_marked("x" * 1000, 100)
    assert truncate_marked("x" * 50, 100)[0] == "x" * 50, "text that fits needs no marker"


# ---------------------------------------------------------------------------
# Wire ids
# ---------------------------------------------------------------------------
def test_c_b8_duplicate_ids_are_both_rewritten():
    assert assign_wire_ids(["call_a", "call_a"], 7) == ["call_a.rt0", "call_a.rt1"]


def test_c_b9_o4_12_used_is_seeded_from_every_usable_original():
    """O4-12: seeding only the ids already processed would give a.rt0, a.rt1, a.rt0."""
    assert assign_wire_ids(["a", "a", "a.rt0"], 7) == ["a.rt0.1", "a.rt1", "a.rt0"]


def test_c_b10_a_missing_id_gets_a_turn_scoped_one():
    assert assign_wire_ids(["call_x", None], 7) == ["call_x", "rt.7.rt1"]


def test_o4_9_any_json_type_is_handled_without_encoding_or_hashing():
    ids = ["ok", "bad\ud800", 42, {"k": 1}, "é", ""]
    assert assign_wire_ids(ids, 7) == ["ok", "rt.7.rt1", "rt.7.rt2", "rt.7.rt3", "rt.7.rt4", "rt.7.rt5"]
    assert assign_wire_ids([[1], None, True, 1.5], 3) == ["rt.3.rt0", "rt.3.rt1", "rt.3.rt2", "rt.3.rt3"]


def test_valid_unique_ids_are_kept_and_generated_ids_are_bounded():
    ids = ["call_" + "x" * 59, "a:b.c-d_e", "x" * 65, "y" * 49, "y" * 49, "z" * 48, "z" * 48]
    wire = assign_wire_ids(ids, 9)
    assert wire[:2] == ids[:2], "valid unique ids are never rewritten"
    assert wire[2] == "rt.9.rt2", "over 64 characters: not usable at all"
    assert wire[3:5] == ["rt.9.rt3", "rt.9.rt4"], "a rewritten id over 48 characters is not a base"
    assert wire[5:7] == ["z" * 48 + ".rt5", "z" * 48 + ".rt6"], "48 characters is still a base"
    assert len(set(wire)) == len(wire)
    assert all(len(w) <= 64 for w in wire)
    assert chassis.WIRE_ID.fullmatch(wire[2])


def test_wire_ids_are_unique_under_adversarial_collisions():
    ids = ["a", "a", "a.rt0", "a.rt1", "a.rt0.1", None, "rt.1.rt5"]
    wire = assign_wire_ids(ids, 1)
    assert len(set(wire)) == len(wire)
    assert wire[2:5] == ["a.rt0", "a.rt1", "a.rt0.1"], "usable originals keep their spelling"
