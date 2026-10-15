
import sys, time, types
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import console
ready, mode, argv = Path(sys.argv[2]), sys.argv[3], sys.argv[4:]
real_claim, sleeps, claims = console.Window.claim, [0], [0]

def sleep(seconds):
    sleeps[0] += 1
    if mode == "sleep" and sleeps[0] == 2:
        ready.write_text("between cycles")
        time.sleep(120)
    return time.sleep(seconds)

def claim(self):
    claims[0] += 1
    if mode == "claim" and claims[0] == 3:
        ready.write_text("inside a cycle")
        time.sleep(120)
    return real_claim(self)

# The console's own `time`, and only its loop's sleep: the process's `time` module is untouched.
console.time = types.SimpleNamespace(sleep=sleep)
console.Window.claim = claim
sys.exit(console.main(argv))
