"""Arm launcher, inside the scope (grant SPACE-20261011-P-DIAG-01). Observes SIGINT's inherited
disposition with signal.getsignal (it installs no handler), restores SIG_DFL only when told to
(arm 2: the correction under test), records both, waits for the supervisor's go-file, and execs the
command. exec keeps an ignored disposition and a SIG_DFL one alike, so arm 1's path is the original
driver's: nothing here changes what the test inherits unless arm 2 asks.

usage: launch.py <restore 0|1> <go-file> <record-file> <command...>
"""

import json
import os
import signal
import sys
import time

restore, go, record, command = sys.argv[1] == "1", sys.argv[2], sys.argv[3], sys.argv[4:]


def sigign() -> str:
    with open("/proc/self/status") as status:
        return next(line.split()[1] for line in status if line.startswith("SigIgn:"))


inherited, inherited_mask = repr(signal.getsignal(signal.SIGINT)), sigign()
if restore:
    signal.signal(signal.SIGINT, signal.SIG_DFL)
with open(record, "w") as out:
    json.dump(
        {
            "pid": os.getpid(),
            "restore": restore,
            "inherited": inherited,
            "inherited_SigIgn": inherited_mask,
            "before_exec": repr(signal.getsignal(signal.SIGINT)),
            "before_exec_SigIgn": sigign(),
        },
        out,
    )
deadline = time.monotonic() + 60
while not os.path.exists(go):
    if time.monotonic() > deadline:
        sys.exit(97)  # never released: the supervisor held the arm
    time.sleep(0.2)
os.execvp(command[0], command)
