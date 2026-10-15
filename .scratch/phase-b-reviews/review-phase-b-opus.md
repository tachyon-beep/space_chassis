# Opus review of the Phase B candidate, frozen tree a1fbad19 (2026-10-10), as handed back

Verdict: land after fixes. No Critical. Read-only; no tests.

Checks out: serve_vehicle.sh flags match console.py's parser at f443996 (5118-5205), no --phase;
identity_refusal (4630-4658) matches README; compose (restart unless-stopped, init, /state apart
from /diode, network none). Pins 882 refuse sites, 525 test functions at f443996; no other stale
pins. Containment: identity only in root .executive.json (3497-3510); pending.json and state.json
carry none (4499-4518, 4540-4555); world_id random uuid (2875). libc sentence correct
(checkpoint.py:81-83, 219-221); listed exit-3 cases map to code.

Important 1: identity-leak test reads only key names and only *.json (misses values, renamed keys,
HELP.md, README.md, output/ bodies). Suggest a distinctive scenario/seed and a text scan of every
window file, keeping the key scan.

Minor: 2 resume banner is stdout (print, 5413), only fell-back/root-record/pending lines stderr;
3 exit-3 list incomplete (UncomparableState 5430-5436, legacy-window 5650-5676, lock held, root
record vs checkpoint, --journal mismatch, recovered-tick checkpoint unwritable 5513-5520);
4 "refused start writes nothing" overstated (serves.json 5489, journaled events 4977-4980, root
record 5002); 5 resume regex misses ", fell back" (5527-5528); 6 kill margin tick%50<=35 may cross
a checkpoint on a slow host, suggest <=25; 7 stale text: pyproject 344 tests, README:204 smoke
stack "everything except the vehicle", conftest "one stack", governance/chassis interface.md and
open.md still dd79e76 / window half open; 8 two session-scoped stacks run at once (cost
undocumented); 9 README restart bullet blames lost commands only on a crash (#39); 10 a new world's
first start can be refused by an agent-written legacy pending.json: start the vehicle before the
fleet.

Declined: live pass/fail, verify_containment on a vehicle stack, journal growth vs 40G /state,
whether prepare_host.sh clears vehicle_state, whether governance lands in this commit.
