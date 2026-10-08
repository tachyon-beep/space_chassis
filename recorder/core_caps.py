"""The core socket's spend caps: an hour per agent, and an hour for the fleet.

Aurora's recorder budgets only the sockets an agent declares; its core socket, the one the agent's
own conversation runs on, carries no ceiling at all. That is one agent on one key. Here there are
ten agents, each behind its own recorder process, drawing on one credit pool, so one runaway agent
could spend every other agent's hour and leave all ten pausing on exit 44 together.

So the core socket gets what space's recorder already enforced: a rolling hour of requests and of
tokens per agent (`CoreCaps`), and a rolling hour of tokens for the whole fleet (`FleetLedger`).
The fleet hour has to be shared between processes, and nothing else is shared between ten
recorders, so it lives in one append-only file on a volume only the recorders mount, read and
written under `flock`.

A refusal is a 429 with a sentence saying which hour is spent and when it reopens. The harness's
chassis treats 429 as transient: it retries with backoff and then exits 44, which the watchdog
answers with a jittered pause. These are cost containment, not policy: nothing here looks at what
an agent is doing, only at what it has spent.
"""

import contextlib
import fcntl
import json
import math
import os
import threading
import time
import uuid

from recorder_streams import (
    BUDGET_WINDOW,
    check_budget,
    check_token_budget,
    rate_limited_message,
    reservation_for,
    token_limited_message,
)

DEFAULT_REQUEST_ALLOWANCE = 2400
DEFAULT_TOKEN_ALLOWANCE = 200_000_000
DEFAULT_FLEET_TOKEN_ALLOWANCE = 2_000_000_000
DEFAULT_RESPONSE_RESERVE = 32768
COMPACT_SLACK_LINES = 1024


def _valid_tokens(tokens):
    return not isinstance(tokens, bool) and isinstance(tokens, (int, float)) and tokens >= 0


class FleetLedger:
    """The fleet's rolling hour of tokens, shared by every recorder through one file.

    Each line is one reservation or the settle that replaced it: the latest line for a ticket
    wins, and keeps the reservation's time, so spend ages from when it was reserved. The lock
    file is opened on every call, because `flock` only excludes between distinct open file
    descriptions; a thread lock covers the handler threads inside one recorder.
    """

    def __init__(self, path, agent, allowance, clock=time.time):
        self.path = path
        self.agent = agent
        self.allowance = allowance
        self._clock = clock
        self._thread_lock = threading.Lock()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    @contextlib.contextmanager
    def _locked(self):
        with self._thread_lock, open(self.path + ".lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def _read(self, now):
        """Return (live entries by ticket, line count, whether any line expired or was unreadable)."""
        latest = {}
        lines = 0
        stale = False
        try:
            with open(self.path, encoding="utf-8") as f:
                for raw in f:
                    lines += 1
                    try:
                        entry = json.loads(raw)
                        stamp, ticket, tokens = entry["t"], entry["ticket"], entry["tokens"]
                    except (ValueError, TypeError, KeyError):
                        stale = True
                        continue
                    if not (
                        isinstance(stamp, (int, float))
                        and isinstance(ticket, str)
                        and _valid_tokens(tokens)
                    ):
                        stale = True
                        continue
                    latest[ticket] = entry
        except FileNotFoundError:
            pass
        live = {}
        for ticket, entry in latest.items():
            if now - entry["t"] < BUDGET_WINDOW:
                live[ticket] = entry
            else:
                stale = True
        return live, lines, stale

    def _append(self, entry):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _compact_if_needed(self, live, lines, stale):
        if not stale and lines <= 2 * len(live) + COMPACT_SLACK_LINES:
            return
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as f:
            for entry in live.values():
                f.write(json.dumps(entry) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, self.path)

    def _refusal(self, live, now):
        oldest = min((entry["t"] for entry in live.values()), default=None)
        remaining = 0 if oldest is None else max(0, math.ceil(BUDGET_WINDOW - (now - oldest)))
        return (
            429,
            f"rate limited: at most {self.allowance} token(s) per hour across the fleet"
            f"; next available in {remaining} seconds",
        )

    def reserve(self, tokens):
        """Hold tokens against the fleet's hour. Returns (refusal, ticket)."""
        with self._locked():
            now = self._clock()
            live, lines, stale = self._read(now)
            if sum(entry["tokens"] for entry in live.values()) + tokens > self.allowance:
                return self._refusal(live, now), None
            ticket = f"{self.agent}:{uuid.uuid4().hex}"
            entry = {"t": now, "agent": self.agent, "ticket": ticket, "tokens": int(tokens)}
            self._append(entry)
            live[ticket] = entry
            self._compact_if_needed(live, lines + 1, stale)
            return None, ticket

    def settle(self, ticket, tokens):
        """Replace a reservation with what was spent. Unknown usage leaves the reservation."""
        if ticket is None or not _valid_tokens(tokens):
            return
        with self._locked():
            now = self._clock()
            live, lines, stale = self._read(now)
            if ticket not in live:
                return
            entry = dict(live[ticket], tokens=int(tokens))
            self._append(entry)
            live[ticket] = entry
            self._compact_if_needed(live, lines + 1, stale)

    def used(self):
        with self._locked():
            live, _, _ = self._read(self._clock())
        return sum(entry["tokens"] for entry in live.values())


class CoreCaps:
    """One agent's rolling hour on its core socket, and its share of the fleet's.

    Both per-agent checks are read first and commit nothing, then the fleet is asked, which is
    the one write another process can see, and only then is the request stamped. So a refusal
    from this agent's own hour costs the fleet nothing, and nothing has to be handed back.
    """

    def __init__(
        self,
        request_allowance,
        token_allowance,
        ledger=None,
        response_reserve=DEFAULT_RESPONSE_RESERVE,
        clock=time.time,
    ):
        self.request_allowance = request_allowance
        self.token_allowance = token_allowance
        self.ledger = ledger
        self.response_reserve = response_reserve
        self._clock = clock
        self._lock = threading.Lock()
        self._requests = []
        self._tokens = []
        self._ticket = 0

    def admit(self, body):
        """Charge one core request. Returns (refusal, ticket)."""
        reserved = reservation_for(body, self.response_reserve)
        with self._lock:
            now = self._clock()
            tokens_ok, tokens = check_token_budget(self._tokens, now, self.token_allowance)
            if not tokens_ok:
                self._tokens = tokens
                return (429, token_limited_message(self.token_allowance, tokens, now)), None
            requests_ok, requests = check_budget(self._requests, now, self.request_allowance)
            if not requests_ok:
                self._requests = requests
                return (429, rate_limited_message(self.request_allowance, requests, now)), None
            fleet_ticket = None
            if self.ledger is not None:
                refused, fleet_ticket = self.ledger.reserve(reserved)
                if refused is not None:
                    return refused, None
            self._ticket += 1
            self._requests = requests
            tokens.append((now, reserved, self._ticket))
            self._tokens = tokens
            return None, (self._ticket, fleet_ticket)

    def settle(self, ticket, tokens):
        """Replace a request's reservation with what it spent; unknown usage keeps it."""
        if ticket is None or not _valid_tokens(tokens):
            return
        local, fleet_ticket = ticket
        with self._lock:
            self._tokens = [
                (stamp, int(tokens) if held == local else spent, held)
                for stamp, spent, held in self._tokens
            ]
        if self.ledger is not None:
            self.ledger.settle(fleet_ticket, tokens)

    def used(self):
        with self._lock:
            now = self._clock()
            requests = [stamp for stamp in self._requests if now - stamp < BUDGET_WINDOW]
            tokens = [entry for entry in self._tokens if now - entry[0] < BUDGET_WINDOW]
        return {"requests": len(requests), "tokens": sum(entry[1] for entry in tokens)}


def _env_int(name, default):
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


def caps_from_environment():
    """Build this recorder's caps from its environment. Returns (CoreCaps, FleetLedger or None)."""
    ledger = None
    path = os.environ.get("FLEET_LEDGER_PATH", "").strip()
    if path:
        agent = os.environ.get("AGENT_SLUG", "").strip()
        if not agent:
            raise ValueError("FLEET_LEDGER_PATH is set but AGENT_SLUG is not")
        ledger = FleetLedger(
            path,
            agent,
            _env_int("RECORDER_TOKEN_GLOBAL_HOURLY_MAX", DEFAULT_FLEET_TOKEN_ALLOWANCE),
        )
    caps = CoreCaps(
        _env_int("RECORDER_HOURLY_MAX", DEFAULT_REQUEST_ALLOWANCE),
        _env_int("RECORDER_TOKEN_HOURLY_MAX", DEFAULT_TOKEN_ALLOWANCE),
        ledger=ledger,
        response_reserve=_env_int("RECORDER_CORE_RESPONSE_RESERVE", DEFAULT_RESPONSE_RESERVE),
    )
    return caps, ledger
