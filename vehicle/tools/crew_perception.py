"""The perception function: what a crew member could honestly say, computed before anyone composes.

`review-findings.md` #4 and `domains/crew/components.yaml`'s header put the rule in one line:

    (full_truth, crew_position, display_contract) -> perceivable_subset

and the display contract has carried the third argument since D-06 with nothing to call it. This is
the call. It is a pure function of a frame's channel values, where each person is, whether they can
answer, the contract and a seed, so the answer to an `ask_crew` is a lookup rather than a judgement
and a replay asks the same question of the same crew and gets the same answer.

What it returns has two halves, and only the first may reach whoever composes the crew's words:

  * `perceived` — the position the person is at, the readouts in front of them at the panel's
    **displayed** precision (coarser than the channel's, by the contract's own rule), the channels
    the position names as invisible, and the human channels it declares. A channel not on a panel
    here is simply absent: "there is no readout for that here" is the true answer, and the composer
    cannot leak a value it was never handed.
  * `audit` — the seeded wrongness drawn for this answer (`display_contract.wrongness`, at the
    on-demand probabilities of `CRW-02`..`CRW-04`), stated for the evaluator. It never goes to the
    composer: a perturbation the composer could see is one it could undo.

Dialogue is **per console** (D-07, John 2026-10-17): an answer is the asking console's. Delivering it
to that console alone, and counting the asks that make up a crew member's memory of an exchange, is
the executive's and the console's (`tools/console.py`), not this function's.

Standard library and PyYAML only, wired into no operator-side service, like every tool here.
"""

from __future__ import annotations

import hashlib
import random
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

# The three wrongness kinds the vehicle can produce, and the fault each one's on-demand probability
# is declared on. `wrong_module` is the fourth and carries no weight: the subset is computed before
# anybody composes, so a report from another position's instruments is unreachable by construction.
WRONGNESS_FAULTS = {
    "misheard": "CRW-02-misheard",
    "misattributed": "CRW-03-misattributed",
    "forgot": "CRW-04-forgot",
}


def load_contract(root: Path) -> tuple[dict[str, Any], dict[str, float]]:
    """The display contract, and each wrongness kind's on-demand probability from its fault."""
    components = yaml.safe_load((root / "domains/crew/components.yaml").read_text())
    faults = yaml.safe_load((root / "domains/crew/fault_policy.yaml").read_text())
    on_demand = {
        str(row["id"]): float(row["seeding"]["on_demand_p"])
        for row in faults.get("faults") or []
        if isinstance((row.get("seeding") or {}).get("on_demand_p"), (int, float))
    }
    probabilities = {kind: on_demand[fault] for kind, fault in WRONGNESS_FAULTS.items()}
    return components["display_contract"], probabilities


def _channel_pattern(channel: str) -> re.Pattern[str]:
    """A contract channel as a match over frame keys: `power.lcl_[n]_state` names every LCL's."""
    parts = re.split(r"\[[^\]]*\]", channel)
    return re.compile("^" + "[^.]+?".join(re.escape(p) for p in parts) + "$")


def displayed(value: Any, precision: Any) -> Any:
    """A reading as the panel shows it: rounded to the displayed precision, never finer.

    `exact` is a discrete shown as itself. A number is rounded half-even to a multiple of the
    precision, in decimal so 0.1 shows as 0.1 rather than as its binary neighbour."""
    if precision == "exact" or isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    step = Decimal(str(precision))
    quantised = (Decimal(str(value)) / step).quantize(Decimal(1)) * step
    return float(quantised) if step < 1 else int(quantised)


def _readouts(position: dict[str, Any], frame: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for panel in position.get("panels") or []:
        for shown in panel.get("shows") or []:
            pattern = _channel_pattern(str(shown["channel"]))
            for key in sorted(k for k in frame if pattern.match(k)):
                row = {
                    "panel": panel["id"],
                    "channel": key,
                    "value": displayed(frame[key], shown["displayed_precision"]),
                    "displayed_precision": shown["displayed_precision"],
                }
                if shown.get("units"):
                    row["units"] = shown["units"]
                rows.append(row)
    return rows


def _rng(seed: int, crew_id: str, ask_index: int) -> random.Random:
    """One stream per (run, person, ask): an answer's wrongness does not depend on anyone else's."""
    digest = hashlib.sha256(f"{seed}:{crew_id}:{ask_index}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _misheard(value: Any, rng: random.Random) -> Any:
    """A digit pair transposed, which is the contract's own example: 850 becomes 580."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    text = repr(value)
    digits = [i for i, c in enumerate(text) if c.isdigit()]
    pairs = [(a, b) for a, b in zip(digits, digits[1:], strict=False) if b == a + 1 and text[a] != text[b]]
    if not pairs:
        return value
    a, b = pairs[rng.randrange(len(pairs))]
    swapped = text[:a] + text[b] + text[a] + text[b + 1 :]
    return type(value)(float(swapped)) if isinstance(value, int) else float(swapped)


def perceive(
    frame: dict[str, Any],
    crew_id: str,
    location: dict[str, str],
    availability: dict[str, str],
    contract: dict[str, Any],
    probabilities: dict[str, float],
    seed: int,
    ask_index: int,
) -> dict[str, Any]:
    """What `crew_id` could honestly report from where they are, and the wrongness drawn for it."""
    state = availability.get(crew_id)
    station = location.get(crew_id)
    if state == "incapacitated":
        return {"perceived": {"crew_id": crew_id, "answers": False}, "audit": {"wrongness": None}}
    positions = {p["id"]: p for p in contract["positions"]}
    position = positions[station]
    rows = _readouts(position, frame)
    perceived = {
        "crew_id": crew_id,
        "answers": True,
        "position": station,
        "woken": state == "resting",
        "readouts": rows,
        "cannot_see": list(position.get("cannot_see") or []),
        "human_channels": list(position.get("human_channels") or []),
    }
    rng = _rng(seed, crew_id, ask_index)
    audit: dict[str, Any] = {"wrongness": None}
    if rng.random() < sum(probabilities.values()) and rows:
        kinds = [k for k in contract["wrongness"]["kinds"] if k["id"] in WRONGNESS_FAULTS]
        kind = rng.choices([k["id"] for k in kinds], weights=[k["weight"] for k in kinds])[0]
        index = rng.randrange(len(rows))
        target = dict(rows[index])
        if kind == "misheard":
            rows[index] = {**target, "value": _misheard(target["value"], rng)}
        elif kind == "forgot":
            del rows[index]
        else:
            others = sorted({r["panel"] for r in rows} - {target["panel"]})
            if others:
                rows[index] = {**target, "panel": others[rng.randrange(len(others))]}
        audit = {"wrongness": kind, "readout": target, "reported": rows[index] if kind != "forgot" else None}
    return {"perceived": perceived, "audit": audit}
