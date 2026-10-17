"""Fail unless a junit report executed at least N tests with no failures, errors or skips.

The CI jobs that run opt-in tiers (the quiet-coast episode) use it: a tier that skips is a tier that
did not run, so a skip fails the check as a failure would.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

report, least = Path(sys.argv[1]), int(sys.argv[2])
root = ET.parse(report).getroot()
suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
counts = {
    key: sum(int(s.get(key, 0)) for s in suites)
    for key in ("tests", "failures", "errors", "skipped")
}
print(counts)
if counts["tests"] < least or any(counts[k] for k in ("failures", "errors", "skipped")):
    raise SystemExit(
        f"{report} must execute at least {least} tests with zero skips, failures and errors"
    )
