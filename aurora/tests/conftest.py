"""Paths for the root suite.

The operator-side modules under services/ and scripts/, and the window's fixture under contract/,
are imported by bare name, as they are when they run: `import health`, `import status`,
`import fake_diode`. Nothing here starts a process or touches Docker; the live suite is live/.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
for directory in ("contract", "scripts", "services"):
    sys.path.insert(0, str(PROJECT / directory))
