#!/usr/bin/env python3
"""Name the fleet.

Ten agents arrive together with no history and no leader. What they are given
is a name each, drawn at random from a pool and shared by nobody: the point is
that there is no order in the naming, so nothing about the names says who
decides anything. Deciding that is the mission's first problem.

Names are not identities the agents chose and not ranks: they are how one agent
can refer to another, and how a stale lock or a half-finished job can be
attributed to whoever left it. The roster is the operator's bookkeeping: it is
written to operator/roster.json and into .env, which compose and the volume
tooling read. Each agent is given its own name through its environment.

Names are assigned once and then name the volume images. Re-running this with
--force renames the fleet on paper while the images keep the old names, so it is
refused unless asked for explicitly. Running it again without --force re-reads
the existing roster and, when --env-file is given, writes its block into that
file, so a fresh .env still names the fleet the images were made for.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

CATEGORIES: dict[str, tuple[str, ...]] = {
    "animal": (
        "otter",
        "heron",
        "badger",
        "marten",
        "kestrel",
        "wombat",
        "lynx",
        "pelican",
        "ibex",
        "shrew",
        "cormorant",
        "polecat",
        "jackdaw",
        "numbat",
        "caracal",
        "gannet",
        "sable",
        "tapir",
        "raven",
        "quokka",
    ),
    "car": (
        "kombi",
        "cortina",
        "impala",
        "marina",
        "granada",
        "corsair",
        "capri",
        "sunbeam",
        "trabant",
        "niva",
        "amica",
        "kadett",
        "viva",
        "pallas",
        "legacy",
        "corvair",
        "zorba",
        "raptor",
        "dormobile",
        "sulky",
    ),
    "flower": (
        "aster",
        "lupin",
        "clover",
        "freesia",
        "verbena",
        "alstroemeria",
        "scabious",
        "agapanthus",
        "cosmos",
        "hellebore",
        "nigella",
        "phlox",
        "gentian",
        "anemone",
        "crocus",
        "sorrel",
        "mullein",
        "bugloss",
        "wattle",
        "boronia",
    ),
    "colour": (
        "ochre",
        "umber",
        "verdigris",
        "cerulean",
        "amaranth",
        "saffron",
        "puce",
        "celadon",
        "carmine",
        "gamboge",
        "russet",
        "mazarine",
        "puce_drab",
        "solferino",
        "watchet",
        "isabelline",
        "cinnabar",
        "orpiment",
        "smalt",
        "glaucous",
    ),
    "weather": (
        "squall",
        "monsoon",
        "sirocco",
        "mistral",
        "harmattan",
        "chinook",
        "bora",
        "khamsin",
        "nor_easter",
        "doldrums",
        "halcyon",
        "mackerel",
        "virga",
        "graupel",
        "hoarfrost",
        "williwaw",
        "zephyr",
        "gregale",
        "levanter",
        "pampero",
    ),
}

# Words that would read as a claim about a member rather than a label. None of
# the pools above carries one, and this is the reminder not to add one.
FORBIDDEN = frozenset({"lead", "leader", "chief", "captain", "prime", "alpha", "first"})

DEFAULT_COUNT = 10
ROSTER_JSON = "roster.json"
ROSTER_ENV = "roster.env"
UNUSED_JSON = "roster.unused.json"


def candidates() -> list[tuple[str, str]]:
    """Every pool word as (category, word), excluding anything forbidden."""
    out: list[tuple[str, str]] = []
    for category, words in CATEGORIES.items():
        for word in words:
            if word in FORBIDDEN:
                continue
            out.append((category, word))
    return out


def draw(count: int, seed: int | None = None) -> list[dict[str, str]]:
    """Draw `count` distinct names, mixing the pools rather than cycling them.

    Sampling from the whole pool rather than taking one per category keeps the
    mixture unpredictable: a roster can legitimately come out as eight animals
    and two colours, and nothing about the composition should be read as
    intent.
    """
    pool = candidates()
    if count > len(pool):
        raise SystemExit(f"asked for {count} names; the pools hold {len(pool)}")
    rng = random.Random(seed)
    picked = rng.sample(pool, count)
    # Shuffle again so the pick order does not correlate with category order.
    rng.shuffle(picked)
    return [{"category": category, "name": name} for category, name in picked]


def slugs(names: list[dict[str, str]]) -> list[str]:
    """Names usable as directory components: lower case, no separators."""
    return ["".join(c if c.isalnum() else "_" for c in n["name"]).strip("_") for n in names]


def build(count: int, seed: int | None) -> dict:
    names = draw(count, seed)
    entries = []
    for index, (entry, slug) in enumerate(zip(names, slugs(names), strict=True), start=1):
        entries.append(
            {
                "agent": f"agent_{index}",
                "name": entry["name"],
                "slug": slug,
                "category": entry["category"],
            }
        )
    return {
        "count": count,
        "seed": seed,
        "note": (
            "Names are drawn at random and carry no rank. The service identifiers "
            "(agent_1, agent_2) are bookkeeping and are not what an agent is called."
        ),
        "agents": entries,
    }


# The roster lives in .env rather than beside it, and that is not tidiness
# either. Compose reads .env with no flags; a separate file needs
# `--env-file roster.env` on every command, and a stack started without it hands
# every agent the fallback slug -- so agent_1's binds would name images that
# were never created for it, and with `create_host_path: false` it would not
# start. One file, read by default, cannot be forgotten.
ROSTER_BEGIN = "# --- the fleet roster (generated: do not edit by hand) ---"
ROSTER_END = "# --- end of the fleet roster ---"


_TOKEN = re.compile(r"[a-z][a-z0-9_]{0,31}")


def validate(roster: dict) -> dict:
    """Refuse a roster that is not one this script could have drawn.

    The roster is written into .env, which compose hands to every service, and its slugs name
    volume images and mount points. A roster carried forward from the old layout lived in a volume
    every agent could write, so nothing in it is trusted: the count is a positive whole number,
    the agents are exactly agent_1..agent_N in order, every name and slug is the drawn alphabet
    (lower-case letters, digits and underscores, starting with a letter), and no slug repeats.
    Anything else -- a newline that would add a variable, a path that climbs out -- is refused.
    """
    count = roster.get("count") if isinstance(roster, dict) else None
    agents = roster.get("agents") if isinstance(roster, dict) else None
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise SystemExit(f"roster refused: count {count!r} is not a positive whole number")
    if not isinstance(agents, list) or len(agents) != count:
        raise SystemExit(f"roster refused: count {count} does not match its agents")
    seen = set()
    for n, entry in enumerate(agents, start=1):
        if not isinstance(entry, dict) or entry.get("agent") != f"agent_{n}":
            raise SystemExit(f"roster refused: entry {n} is not agent_{n}")
        for field in ("name", "slug"):
            value = entry.get(field)
            if not isinstance(value, str) or not _TOKEN.fullmatch(value):
                raise SystemExit(f"roster refused: agent_{n} has an unusable {field} {value!r}")
        if entry["slug"] in seen:
            raise SystemExit(f"roster refused: slug {entry['slug']!r} appears twice")
        seen.add(entry["slug"])
    return roster


def roster_env_text(roster: dict) -> str:
    validate(roster)
    lines = [
        ROSTER_BEGIN,
        "# Drawn by scripts/roster.py from pools of animals, cars, flowers, colour",
        "# names and weather. The names carry no rank and mean nothing but",
        "# identity: deciding who does what is the mission's, not the world's.",
        "# Redrawing with a different seed renames the fleet on paper only; the",
        "# directories keep the names they were created with.",
        f"FLEET_COUNT={roster['count']}",
        "FLEET_NAMES=" + ",".join(a["name"] for a in roster["agents"]),
        "FLEET_SLUGS=" + ",".join(a["slug"] for a in roster["agents"]),
    ]
    for entry in roster["agents"]:
        n = entry["agent"].split("_")[1]
        lines.append(f"FLEET_{n}_NAME={entry['name']}")
        lines.append(f"FLEET_{n}_SLUG={entry['slug']}")
    lines.append(ROSTER_END)
    return "\n".join(lines) + "\n"


def update_env_file(env_path: Path, roster: dict) -> None:
    """Put the roster's names into .env, replacing any previous roster block.

    Idempotent: a second run replaces the block rather than appending a second
    copy, because duplicate keys in a .env file resolve to the last one and a
    stale first copy would be read by nothing but the eye.
    """
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    block = roster_env_text(roster)
    if ROSTER_BEGIN in existing and ROSTER_END in existing:
        before, _, rest = existing.partition(ROSTER_BEGIN)
        _stale, _, after = rest.partition(ROSTER_END)
        existing = before + block + after.lstrip("\n")
    else:
        existing = existing.rstrip("\n") + "\n\n" + block
    env_path.write_text(existing, encoding="utf-8")


def write_roster(roster: dict, roster_dir: Path, env_path: Path | None) -> None:
    roster_dir.mkdir(parents=True, exist_ok=True)
    (roster_dir / ROSTER_JSON).write_text(json.dumps(roster, indent=2) + "\n", encoding="utf-8")
    if env_path is not None:
        update_env_file(env_path, roster)


def print_roster(roster: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(roster, indent=2))
        return
    width = max(len(a["name"]) for a in roster["agents"])
    print(f"{'service':<9}  {'name':<{width}}  {'pool':<8}  slug")
    for entry in roster["agents"]:
        print(
            f"{entry['agent']:<9}  {entry['name']:<{width}}  "
            f"{entry['category']:<8}  {entry['slug']}"
        )
    print(f"\n{roster['count']} agents, seed {roster['seed']}, no ranks.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--count", type=int, default=DEFAULT_COUNT, help=f"agents (default {DEFAULT_COUNT})"
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="draw deterministically from this seed"
    )
    parser.add_argument(
        "--roster-dir",
        default=os.environ.get("ROSTER_DIR", "./operator"),
        help="where roster.json is written: the operator's directory, not a volume",
    )
    parser.add_argument("--work-dir", default=None, help="deprecated: use --roster-dir")
    parser.add_argument(
        "--env-file",
        default="./.env",
        help="the compose environment file the roster is written into; pass '' to skip",
    )
    parser.add_argument("--json", action="store_true", help="print the roster as json and stop")
    parser.add_argument(
        "--print", dest="show", action="store_true", help="print an existing roster and stop"
    )
    parser.add_argument("--force", action="store_true", help="re-draw even if a roster exists")
    args = parser.parse_args(argv)

    if args.work_dir is not None:
        print("--work-dir is deprecated: the roster lives in --roster-dir now", file=sys.stderr)
        args.roster_dir = args.work_dir
    roster_dir = Path(args.roster_dir)
    existing = roster_dir / ROSTER_JSON
    env_path = Path(args.env_file) if args.env_file else None

    if args.show or (existing.exists() and not args.force and args.seed is None):
        if not existing.exists():
            print(f"no roster at {existing}", file=sys.stderr)
            return 1
        roster = validate(json.loads(existing.read_text(encoding="utf-8")))
        if env_path is not None and not args.show:
            update_env_file(env_path, roster)
        print_roster(roster, args.json)
        return 0

    roster = build(args.count, args.seed)
    write_roster(roster, roster_dir, env_path)
    print_roster(roster, args.json)
    if env_path is not None:
        print(f"\nwrote {env_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
