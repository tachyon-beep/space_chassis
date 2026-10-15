"""Place each probe submit on the console's timeline: claimed, erased, or never touched.

`python3 tests/read_probe_trace.py RUN_DIR` reads `probe-trace.jsonl` and `console-trace.jsonl`
(written by `test_the_vehicle_passes_the_contract_probe` under CONTRACT_PROBE_TRACE=1) and prints,
for every submit, what became of the inode it left at `console.json`:

- CLAIMED: the console opened that inode for reading (its claim read), after the submit;
- ERASED: the console replaced that inode without ever having read it — a claim that read the file
  before the submit and rewrote it after, so the batch never ran (the lost-update shape);
- UNTOUCHED: neither, by the end of the trace (still waiting, or the console stopped).

It also prints the results published after each submit, so a late claim and its late result can be
told from an erased batch with none. Diagnostics only; it asserts nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def main() -> int:
    run = Path(sys.argv[1])
    submits = load(run / "probe-trace.jsonl")
    console = load(run / "console-trace.jsonl")
    if not submits or not console:
        print(f"no traces in {run} (probe {len(submits)}, console {len(console)} lines)")
        return 2
    # Inode numbers are reused once a file is gone, so only the console's *next* claim after a
    # submit can speak for it: the first rewrite of console.json once the submit's replace has
    # finished, and the read that rewrite belongs to.
    t0 = submits[0]["monotonic_ns_before"]
    erased = 0
    for index, submit in enumerate(submits):
        inode, began, ended = (
            submit["inode"],
            submit["monotonic_ns_before"],
            submit["monotonic_ns_after"],
        )
        rewrite = next(
            (e for e in console if e["event"] == "console_replace" and e["monotonic_ns"] >= ended),
            None,
        )
        if rewrite is None:
            fate = "UNTOUCHED (no claim after it)"
        else:
            read = [
                e
                for e in console
                if e["event"] == "console_open" and e["monotonic_ns"] < rewrite["monotonic_ns"]
            ][-1:]
            read = read[0] if read else None
            if read is None:
                fate = "AMBIGUOUS (a rewrite with no read)"
            elif read["monotonic_ns"] >= ended and read.get("inode") == inode:
                fate = f"CLAIMED  read +{(read['monotonic_ns'] - ended) / 1e6:.1f} ms"
            elif read["monotonic_ns"] < ended and rewrite.get("inode_before") == inode:
                erased += 1
                fate = (
                    f"ERASED   the claim read inode {read.get('inode')} at "
                    f"{(read['monotonic_ns'] - began) / 1e6:+.1f} ms and rewrote over this submit's inode "
                    f"at {(rewrite['monotonic_ns'] - ended) / 1e6:+.1f} ms"
                )
            else:
                fate = (
                    f"AMBIGUOUS read {read.get('inode')} at {(read['monotonic_ns'] - began) / 1e6:+.1f} ms, "
                    f"rewrite over {rewrite.get('inode_before')}"
                )
        nxt = submits[index + 1]["monotonic_ns_before"] if index + 1 < len(submits) else None
        results = [
            e
            for e in console
            if e["event"] == "result_publish"
            and e["monotonic_ns"] >= ended
            and (nxt is None or e["monotonic_ns"] < nxt)
        ]
        print(
            f"#{index:02d} +{(ended - t0) / 1e9:8.3f}s inode {inode} {submit['commands'][:2]}: {fate}; "
            f"{len(results)} result(s) before the next submit"
        )
    print(f"{erased} erased of {len(submits)} submits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
