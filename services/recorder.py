#!/usr/bin/env python3
"""The recorder: the credential, and the record.

One unix socket per agent, in a volume the agents mount read-only. Exactly one
route on it. The agent sends a meaningless key; this process replaces it with
the real one and forwards the request upstream. Every turn is appended to a
transcript the agent cannot write.

Three properties are load-bearing and are the reason this is a separate
container rather than a library:

* **No credential in the fleet.** The key lives in this process's environment.
  The agents' containers carry a placeholder, and no header of any request is
  ever written to the record -- bodies only.
* **The record is external.** The transcript volume is mounted read-only into
  the agents; they can read what they did and cannot change it.
* **The ceilings are here.** Allowances live in this environment, so a
  conversation cannot raise its own limit.

The transcript is the only durable account of what an agent thought, so it is
written before the response is relayed: a client that disconnects mid-stream
still leaves a record of the turn it asked for.
"""

from __future__ import annotations

import contextlib
import dataclasses
import heapq
import http.client
import itertools
import json
import math
import os
import re
import socket
import socketserver
import ssl
import sys
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

SERVICES_DIR = Path(os.environ.get("SERVICES_DIR", "/opt/services"))
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))

from common import (  # noqa: E402
    AppendResult,
    RecordStore,
    env_bool,
    env_int,
    iso,
    slugs_from_env,
)

# The canonical path, and the only one the shipped client uses. The check
# below accepts any path that ends with it, because a duty is free to write its
# own client and the fleet's SDK is not the world's business: refusing
# /v1/chat/completions would be enforcing a prefix rather than the route.
ROUTE = "/api/v1/chat/completions"
ROUTE_SUFFIX = "/chat/completions"
TRANSCRIPTS_DIR = Path(os.environ.get("TRANSCRIPTS_DIR", "/transcripts"))
SOCKET_DIR = Path(os.environ.get("SOCKET_DIR", "/llm/sock"))
# 2 MiB: a full 200,000-token window is about 0.8 MB of JSON, so this is
# roughly twice that. The memory reservation below is sized from it.
REQUEST_MAX_BYTES = env_int("REQUEST_MAX_BYTES", 2 * 1024 * 1024)
# A directory an operator can drop `refuse-<slug>.marker` into to make one
# agent's socket fail at the front door. It exists so that "the environment is
# unusable" can be tested as a condition rather than waited for as an accident.
REFUSE_DIR = Path(os.environ.get("RECORDER_REFUSE_DIR", "/tmp"))
# An upstream reachable over a unix socket instead of the network. This exists
# for two reasons, and the second is the important one: an endurance run needs
# a model that costs nothing and answers instantly, and a shim that speaks the
# API to some other backend should not have to bind a port to be used. Set
# UPSTREAM_SOCKET and the recorder talks to that instead of to LLM_BASE_URL.
UPSTREAM_SOCKET = (os.environ.get("UPSTREAM_SOCKET") or "").strip()
WINDOW_SECONDS = 3600
# How often the socket directory is checked for an agent that has just
# announced itself. Agents come up independently of this process.
POLL_SECONDS = 3

FRAMING = {"content-length", "transfer-encoding", "connection", "content-encoding"}


def upstream_supports_streaming() -> bool:
    """Whether the configured upstream will answer a streamed request.

    The recorder forwards the body verbatim to the real thing, which is the
    point. A stand-in that cannot stream -- the endurance harness, or a shim in
    front of a batch-only backend -- will answer a streamed request with one
    complete body, and the recorder would then reassemble nothing: the turn
    would be recorded as empty while the model had answered perfectly well.
    Set UPSTREAM_STREAMING=0 for those, and the request goes out unstreamed.
    """
    return (os.environ.get("UPSTREAM_STREAMING") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def upstream_url() -> str:
    base = (os.environ.get("LLM_BASE_URL") or "").strip().rstrip("/")
    if base:
        return base + "/chat/completions"
    return "https://openrouter.ai/api/v1/chat/completions"


def upstream_key() -> str:
    if (os.environ.get("LLM_BASE_URL") or "").strip():
        return os.environ.get("LLM_API_KEY", "") or os.environ.get("OPENROUTER_API_KEY", "")
    return os.environ.get("OPENROUTER_API_KEY", "")


# ---------------------------------------------------------------------------
# The ceilings
# ---------------------------------------------------------------------------
# Every allowance is in memory only. Deliberately not persisted: a restart of
# the recorder granting a fresh hour to a fleet that has been hammering it is a
# smaller problem than a stale window surviving a deploy. The ceiling that
# actually matters is the upstream key's own balance. A request that was in
# flight when a previous process died shows an `open` with no `close`; nothing
# here ever fabricates the missing `close`.
#
# What the accounting bounds, stated once (the reasoning is in the SV-013
# dossier, section 2.1.3): at the instant a request is admitted, the current
# effective charges in its socket's rolling token window plus its estimate fit
# the limit, and likewise for the fleet's hour. The current effective charge of
# a request is its known actual usage once that is known, and its estimate
# otherwise. That is *not* a cap on billed tokens: a response can cost more
# than its estimate, and then later requests are refused until the window
# rolls, but nothing claws the overshoot back. A hard billed ceiling would need
# a request-side output cap and a provider guarantee, and neither is here.
MAX_TOMBSTONES = env_int("RECORDER_MAX_TOMBSTONES", 4096)
MAX_SLUGS = env_int("RECORDER_MAX_SLUGS", 32)
MAX_INFLIGHT_PER_SOCKET = env_int("RECORDER_MAX_INFLIGHT_PER_SOCKET", 2)
MAX_INFLIGHT_TOTAL = env_int("RECORDER_MAX_INFLIGHT_TOTAL", 12)
INFLIGHT_WAIT_SECONDS = env_int("RECORDER_INFLIGHT_WAIT_SECONDS", 30)
# A slug names a directory and a socket. Discovery reads names agents announce
# themselves, so the name is checked and the number of them is bounded: an
# agent announcing a thousand names must not get a thousand listeners.
SLUG_PATTERN = re.compile(r"[a-z0-9_-]{1,64}")

RESERVED = "reserved"
FORWARDING = "forwarding"
KNOWN = "known"
UNKNOWN = "unknown"


class SystemClock:
    """The production clocks. Tests inject a fake with the same two methods."""

    @staticmethod
    def monotonic() -> float:
        return time.monotonic()

    @staticmethod
    def wall() -> float:
        return time.time()


@dataclass
class Entry:
    """One admitted request in one rolling pool."""

    rid: str
    t: float  # monotonic, read under the budget lock at admission
    amount: int  # the current effective charge


class RollingPool:
    """A per-socket rolling window: requests (amount 1) or tokens.

    An entry counts while `now - t <= window`, the same inclusivity the
    recorder has always had. A limit of zero or less means the pool is closed.
    Entries arrive in lock order, and the clock is read under the lock, so the
    queue is non-decreasing in `t` and pruning from the head alone is exact.
    """

    def __init__(self, limit: int, window: float = WINDOW_SECONDS) -> None:
        self.limit = limit
        self.window = window
        self.q: deque[Entry] = deque()
        self.used = 0
        self.by_rid: dict[str, Entry] = {}

    def prune(self, now: float) -> None:
        while self.q and now - self.q[0].t > self.window:
            entry = self.q.popleft()
            self.used -= entry.amount
            del self.by_rid[entry.rid]

    def add(self, rid: str, t: float, amount: int) -> None:
        entry = Entry(rid, t, amount)
        self.q.append(entry)
        self.by_rid[rid] = entry
        self.used += amount

    def remove(self, rid: str) -> None:
        """Take a cancelled request out. O(len(q)): a deque has no keyed removal."""
        entry = self.by_rid.pop(rid, None)
        if entry is None:
            return
        self.q.remove(entry)
        self.used -= entry.amount

    def wait_for_count(self, now: float) -> int:
        """Seconds until one more entry fits, counting entries only."""
        k = len(self.q) + 1 - self.limit
        return int(self.window - (now - self.q[k - 1].t)) + 1

    def wait_for_sum(self, amount: int, now: float) -> int:
        """Seconds until `amount` more fits against the current charges alone.

        The earliest such time, not a promise: a refund can make it sooner and
        another socket's admission does not affect it, but this socket's own
        later admissions can take the room first. Defined because the caller
        has already refused an amount larger than the whole limit.
        """
        freed = 0
        for entry in self.q:
            freed += entry.amount
            if self.used - freed + amount <= self.limit:
                return int(self.window - (now - entry.t)) + 1
        raise AssertionError("an amount within the limit always fits an empty window")


class HourBucket:
    """One token pool over the whole fleet, on the clock hour.

    A fleet of ten can multiply any per-agent allowance by ten; this is the
    ceiling that does not scale with the number of agents. It empties at the
    top of the hour rather than rolling, so the fleet can plan around it. A
    limit of zero or less means unlimited -- the opposite of a per-socket
    pool's zero, and both meanings are kept as they always were.

    The hour never moves backwards: a wall clock that steps back keeps the
    current hour and its charges, rather than handing out a fresh one.
    """

    def __init__(self, limit: int, now_wall: float) -> None:
        self.limit = limit
        self.bucket = math.floor(now_wall / WINDOW_SECONDS)
        self.used = 0

    def advance(self, now_wall: float) -> None:
        hour = math.floor(now_wall / WINDOW_SECONDS)
        if hour > self.bucket:
            self.bucket, self.used = hour, 0


@dataclass
class Reservation:
    rid: str
    slug: str
    est: int
    t: float
    hour: int
    charge: int
    state: str  # RESERVED, then FORWARDING once bytes may reach the upstream


@dataclass(frozen=True)
class Usage:
    """What a response said it cost. `known` only for a validated count."""

    cls: str
    actual: int | None = None
    raw: dict | None = None


@dataclass(frozen=True)
class Admitted:
    hour: int


@dataclass(frozen=True)
class Refused:
    reason: str
    wait: int | None  # 0 for a closed pool, None for "can never fit"
    limit: int | None = None
    est: int | None = None
    clock_regressed: bool = False


@dataclass(frozen=True)
class Closed:
    kind: str  # cancelled | settled | already_final | unknown_rid
    charge: int | None = None
    usage_class: str | None = None
    applied: tuple[str, ...] = ()
    late: tuple[dict, ...] = ()
    final: dict | None = None


class Budget:
    """Every allowance the recorder enforces, behind one lock.

    One lock owns every check and every mutation, so each call is atomic and
    all seven admission checks precede any charge: two requests racing for the
    last slot cannot both be admitted, and one refused request leaves nothing
    behind. The clocks are injected and read *after* the lock is taken, so
    lock order is timestamp order. Nothing under the lock touches a file or
    the network; callers write their events after the call returns.

    A reservation lives from `admit` until its handler `close`s it, however
    long that takes. No timer expires one to make room: a request that is
    still running is still spending.
    """

    def __init__(
        self,
        global_limit: int,
        clock=None,
        *,
        max_tombstones: int | None = None,
        max_slugs: int | None = None,
        max_live: int | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._clock = clock or SystemClock()
        self._sockets: dict[str, tuple[RollingPool, RollingPool]] = {}
        self._glob = HourBucket(global_limit, self._clock.wall())
        self._live: dict[str, Reservation] = {}
        self._final: OrderedDict[str, dict] = OrderedDict()
        self._max_tombstones = max(1, MAX_TOMBSTONES if max_tombstones is None else max_tombstones)
        self._max_slugs = MAX_SLUGS if max_slugs is None else max_slugs
        # The handler's slots already bound the live set; this is the backstop
        # that keeps the bound true even for a caller that skipped them.
        self._max_live = max(1, MAX_INFLIGHT_TOTAL) if max_live is None else max_live

    @property
    def global_limit(self) -> int:
        return self._glob.limit

    def register(self, slug: str, request_limit: int, token_limit: int) -> bool:
        """Give a socket its two rolling pools. False when the slug cap is reached."""
        with self._lock:
            if slug in self._sockets:
                return True
            if len(self._sockets) >= self._max_slugs:
                return False
            self._sockets[slug] = (RollingPool(request_limit), RollingPool(token_limit))
            return True

    def limits(self, slug: str) -> tuple[int, int]:
        requests, tokens = self._sockets[slug]
        return requests.limit, tokens.limit

    def _advance(self, slug: str, now: float, now_wall: float) -> tuple[RollingPool, RollingPool]:
        self._glob.advance(now_wall)
        requests, tokens = self._sockets[slug]
        requests.prune(now)
        tokens.prune(now)
        return requests, tokens

    def admit(self, rid: str, slug: str, est: int) -> Admitted | Refused:
        if not isinstance(est, int) or isinstance(est, bool) or est < 1:
            raise ValueError(f"an estimate is a positive whole number, not {est!r}")
        with self._lock:
            now, now_wall = self._clock.monotonic(), self._clock.wall()
            requests, tokens = self._advance(slug, now, now_wall)
            glob = self._glob
            # Ids are never meant to repeat: the handler's come from one boot and
            # one counter. The budget does not rely on it. A tombstone retired
            # early still leaves the old request's rolling entries counting for
            # up to an hour; admitting the same id on top would overwrite their
            # index, so it is refused while they remain.
            if (
                rid in self._live
                or rid in self._final
                or rid in requests.by_rid
                or rid in tokens.by_rid
            ):
                return Refused("duplicate_rid", None)
            if len(self._live) >= self._max_live:
                return Refused("inflight", None, self._max_live)
            if requests.limit <= 0:
                return Refused("requests_closed", 0, requests.limit)
            if len(requests.q) + 1 > requests.limit:
                return Refused("requests", requests.wait_for_count(now), requests.limit)
            if tokens.limit <= 0:
                return Refused("tokens_closed", 0, tokens.limit, est)
            if est > tokens.limit:
                return Refused("estimate_exceeds_limit", None, tokens.limit, est)
            if tokens.used + est > tokens.limit:
                return Refused("tokens", tokens.wait_for_sum(est, now), tokens.limit, est)
            if glob.limit > 0 and est > glob.limit:
                return Refused("estimate_exceeds_global_limit", None, glob.limit, est)
            if glob.limit > 0 and glob.used + est > glob.limit:
                end = (glob.bucket + 1) * WINDOW_SECONDS
                regressed = math.floor(now_wall / WINDOW_SECONDS) < glob.bucket
                return Refused("global", int(end - now_wall) + 1, glob.limit, est, regressed)
            requests.add(rid, now, 1)
            tokens.add(rid, now, est)
            glob.used += est
            self._live[rid] = Reservation(rid, slug, est, now, glob.bucket, est, RESERVED)
            return Admitted(glob.bucket)

    def begin_forward(self, rid: str) -> bool:
        """RESERVED -> FORWARDING, or False. Only a reserved request may be sent."""
        with self._lock:
            reservation = self._live.get(rid)
            if reservation is None or reservation.state != RESERVED:
                return False
            reservation.state = FORWARDING
            return True

    def close(self, rid: str, usage: Usage | None = None) -> Closed:
        """End a reservation: cancel it if nothing was sent, settle it if it was.

        Called once per admitted request by the handler that owns it. A second
        call, or a call for a request this process never admitted, changes
        nothing and says so.
        """
        with self._lock:
            now, now_wall = self._clock.monotonic(), self._clock.wall()
            reservation = self._live.get(rid)
            if reservation is None:
                if rid in self._final:
                    return Closed("already_final", final=dict(self._final[rid]))
                return Closed("unknown_rid")
            requests, tokens = self._advance(reservation.slug, now, now_wall)
            glob = self._glob
            del self._live[rid]
            if reservation.state == RESERVED:
                # Nothing reached the provider: the request count is refunded
                # along with the tokens.
                requests.remove(rid)
                tokens.remove(rid)
                if reservation.hour == glob.bucket:
                    glob.used -= reservation.charge
                self._retire(rid, {"state": "cancelled", "est": reservation.est, "charge": 0})
                return Closed("cancelled", charge=0)
            # A known actual must be a whole non-negative count; anything else
            # is treated as unknown and the estimate stands. `extract_usage`
            # only builds valid ones, and any later usage source must too.
            known = usage is not None and usage.cls == KNOWN and _is_count(usage.actual)
            new = usage.actual if known else reservation.charge
            delta = new - reservation.charge
            applied: list[str] = []
            # A late settlement is reported only when it moves a number: a zero
            # delta has no adjustment to record, so it has no `late` entry.
            late: list[dict] = []
            entry = tokens.by_rid.get(rid)
            if entry is not None:
                tokens.used += delta
                entry.amount = new
                applied.append("socket_tokens")
            elif delta:
                late.append({"pool": "socket_tokens", "reason": "rolling_expired", "delta": delta})
            if reservation.hour == glob.bucket:
                glob.used += delta
                applied.append("global")
            elif delta:
                late.append({"pool": "global", "hour": reservation.hour, "delta": delta})
            usage_class = KNOWN if known else UNKNOWN
            reservation.charge = new
            self._retire(
                rid,
                {
                    "state": "settled",
                    "usage_class": usage_class,
                    "est": reservation.est,
                    "charge": new,
                    "hour": reservation.hour,
                },
            )
            return Closed("settled", new, usage_class, tuple(applied), tuple(late))

    def _retire(self, rid: str, final: dict) -> None:
        # Tombstones retire in the order they were made (FIFO, not
        # least-recently-used): a lookup does not keep one alive.
        self._final[rid] = final
        while len(self._final) > self._max_tombstones:
            self._final.popitem(last=False)

    def snapshot(self, slug: str) -> dict:
        with self._lock:
            now, now_wall = self._clock.monotonic(), self._clock.wall()
            requests, tokens = self._advance(slug, now, now_wall)
            return {
                "requests_used": len(requests.q),
                "tokens_used": tokens.used,
                "global_bucket": self._glob.bucket,
                "global_used": self._glob.used,
                "live": len(self._live),
                "tombstones": len(self._final),
                "token_times": [entry.t for entry in tokens.q],
            }


def refusal_message(refused: Refused) -> str:
    """The text a refused client reads. The three ordinary forms are unchanged."""
    reason, limit, wait = refused.reason, refused.limit, refused.wait
    if reason in ("requests", "requests_closed"):
        return (
            f"rate limited: at most {limit} request(s) per hour on this socket; "
            f"next available in {wait} second(s)"
        )
    if reason in ("tokens", "tokens_closed"):
        earliest = " at the earliest" if reason == "tokens" else ""
        return (
            f"rate limited: at most {limit} token(s) per hour on this socket; "
            f"next available in {wait} second(s){earliest}"
        )
    if reason == "estimate_exceeds_limit":
        return (
            f"rate limited: at most {limit} token(s) per hour on this socket; this request's "
            f"estimate of {refused.est} token(s) can never fit this limit"
        )
    if reason == "global":
        message = (
            f"rate limited: at most {limit} token(s) per hour across the fleet; "
            f"next available in {wait} second(s)"
        )
        if refused.clock_regressed:
            message += (
                " (measured on a host clock that is behind the accounting hour, "
                "so this may be longer than an hour)"
            )
        return message
    if reason == "estimate_exceeds_global_limit":
        return (
            f"rate limited: at most {limit} token(s) per hour across the fleet; this request's "
            f"estimate of {refused.est} token(s) can never fit this limit"
        )
    if reason == "inflight":
        return "too many requests in flight at the recorder; try again shortly"
    return "the recorder refused this request identifier as a duplicate"


# ---------------------------------------------------------------------------
# The request body
# ---------------------------------------------------------------------------
# A body is accepted only inside a stated domain: strict UTF-8, JSON with no
# NaN/Infinity literal and no number that overflows to one, and an object at
# the top. Outside it the request is refused here, before anything is opened
# or spent: such a body used to be forwarded, the provider would have
# rejected it, and the chassis treats a 400 as a duty fault either way.
#
# Three representations, kept apart on purpose:
#   original   -- exactly the bytes received;
#   forwarded  -- the original bytes verbatim unless a transformation applies,
#                 else one canonical ASCII re-serialization;
#   recorded   -- the parsed object after the same removals, for the transcript.
# Byte identity upstream is promised only when nothing was transformed. A body
# with a duplicated key (at any depth) is forwarded verbatim if untouched, and
# refused if it would need re-serializing, which would silently drop one of
# the values.
CORRELATION_KEY = "x_chassis_correlation"
LABEL_PATTERN = re.compile(r"[A-Za-z0-9._:-]+")
MAX_LABEL_BYTES = 128
MAX_LABEL_LRU = env_int("RECORDER_MAX_LABEL_LRU", 64)


class _NonFinite(Exception):
    pass


@dataclass(frozen=True)
class ParsedRequest:
    original: bytes
    forwarded: bytes
    recorded: dict
    transformed: bool
    duplicate_keys: bool
    label: str | None = None
    label_invalid: dict | None = None


@dataclass(frozen=True)
class RequestRefusal:
    code: str
    message: str
    status: int = 400


def _reject_constant(_name: str):
    raise _NonFinite


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise _NonFinite
    return value


def classify_label(value) -> tuple[str | None, dict | None]:
    """A valid correlation label, or the safe facts about an invalid one.

    The label is untrusted and carries no meaning here: nothing is suppressed,
    deduplicated or settled by it. An invalid one is described by its type and
    size only; its value is never written down.
    """
    if isinstance(value, str):
        size = len(value.encode("utf-8", "surrogatepass"))
        if 1 <= size <= MAX_LABEL_BYTES and LABEL_PATTERN.fullmatch(value):
            return value, None
        return None, {"type": "str", "bytes": size}
    return None, {"type": type(value).__name__, "bytes": len(_encode_label(value))}


def _encode_label(value) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=True).encode("ascii")


def _encode_forwarded(recorded: dict) -> bytes:
    return json.dumps(
        recorded, ensure_ascii=True, allow_nan=False, separators=(",", ":")
    ).encode("ascii")


def parse_request(body: bytes, *, streaming: bool) -> ParsedRequest | RequestRefusal:
    """Decide what is forwarded, what is recorded, and whether to refuse.

    Total over any bytes: every failure is a RequestRefusal with a fixed
    sentence, never an exception and never the parser's own message.
    """
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return RequestRefusal("body_not_utf8", "the request body is not valid UTF-8")
    duplicates = False

    def pairs(items):
        nonlocal duplicates
        obj = {}
        for key, value in items:
            if key in obj:
                duplicates = True
            obj[key] = value
        return obj

    try:
        parsed = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except _NonFinite:
        return RequestRefusal(
            "nonfinite_number", "the request body contains a number that is not finite"
        )
    except json.JSONDecodeError:
        return RequestRefusal("body_not_json", "the request body is not valid JSON")
    except (ValueError, RecursionError):
        # Valid JSON this process will not hold: nesting past the parser's
        # recursion limit, or an integer past the interpreter's digit limit.
        return RequestRefusal(
            "unsupported_json", "the request body nests too deeply or has an oversized number"
        )
    if not isinstance(parsed, dict):
        return RequestRefusal("body_not_object", "the request body must be a JSON object")

    recorded = dict(parsed)
    transformed = False
    label = label_invalid = None
    try:
        if CORRELATION_KEY in recorded:
            label, label_invalid = classify_label(recorded.pop(CORRELATION_KEY))
            transformed = True
        if not streaming and "stream" in recorded:
            # The upstream cannot stream: ask for one complete body instead.
            recorded.pop("stream")
            recorded.pop("stream_options", None)
            transformed = True
        if not transformed:
            return ParsedRequest(body, body, recorded, False, duplicates)
        if duplicates:
            return RequestRefusal(
                "duplicate_keys",
                "the request body repeats a key, and this request would need re-encoding",
            )
        forwarded = _encode_forwarded(recorded)
    except (ValueError, RecursionError):
        # Re-encoding walks the same structure the parser built, and the
        # encoder's recursion need not match the decoder's exactly. Whatever
        # parsed but cannot be re-encoded is refused here, never raised.
        return RequestRefusal(
            "unsupported_json", "the request body nests too deeply or has an oversized number"
        )
    return ParsedRequest(body, forwarded, recorded, True, False, label, label_invalid)


# ---------------------------------------------------------------------------
# Bounds: deadlines, the watchdog, structure and memory (SV-015 v2 sections 2.1-2.2)
# ---------------------------------------------------------------------------
# Every deadline is anchored at t0, the monotonic instant the recorder's accept
# returned for the connection, before any handler thread exists. One request
# is served per connection (the response says `Connection: close`), so t0 can
# never be reset by a later request on a kept-alive connection.
#
#   E2E_BUDGET   = CLIENT_TIMEOUT_HINT - CLIENT_MARGIN         (600 - 30 = 570)
#   UPSTREAM_ABS = t0 + E2E_BUDGET - CUSTODY_RESERVE           (t0 + 540)
#   latest start = UPSTREAM_ABS - MIN_UPSTREAM                 (t0 + 480)
#
# Headers must finish by t0 + HEADER_DEADLINE, the body by header completion +
# BODY_DEADLINE, and both by the latest start. Slot and memory waits share one
# allowance of actual waiting (INFLIGHT_WAIT_SECONDS); time spent reading the
# body does not spend it. After the `open` is recorded and before anything is
# admitted, a request past its latest start is refused 503
# deadline_insufficient. The upstream phase -- connect, TLS, send, status,
# headers, body -- ends at UPSTREAM_ABS, however late it began.
#
# What this does not bound, stated once: DNS inside a connect (no socket exists
# yet to shut down), CPU spent pre-scanning and parsing (bounded by size, not
# time), and filesystem calls (the preflight, the record appends): a stalled
# disk is reported in `close` (`deadline_overrun`, `custody_s`), not prevented.


@dataclass(frozen=True)
class Timing:
    """The deadline profile, in seconds. `from_env` is the deployed one."""

    client_timeout: float = 600.0  # RECORDER_TIMEOUT_SECONDS, the chassis client's read timeout
    client_margin: float = 30.0
    custody_reserve: float = 30.0
    min_upstream: float = 60.0
    header: float = 30.0
    body: float = 60.0
    client_write: float = 60.0
    io_timeout: float = 60.0  # per socket operation, under every phase deadline
    tick: float = 0.25

    @property
    def e2e_budget(self) -> float:
        return self.client_timeout - self.client_margin

    @property
    def upstream_offset(self) -> float:
        return self.e2e_budget - self.custody_reserve

    @classmethod
    def from_env(cls) -> Timing:
        def seconds(name: str, default: float) -> float:
            # Unset means the default. A value that is set but is not a number
            # is not quietly replaced by the default: it is carried as NaN, so
            # `timing_problems` refuses the profile at startup.
            raw = (os.environ.get(name) or "").strip()
            if not raw:
                return default
            try:
                return float(raw)
            except ValueError:
                return math.nan

        return cls(
            client_timeout=seconds("RECORDER_TIMEOUT_SECONDS", 600.0),
            client_margin=seconds("RECORDER_CLIENT_MARGIN_SECONDS", 30.0),
            custody_reserve=seconds("RECORDER_CUSTODY_RESERVE_SECONDS", 30.0),
            min_upstream=seconds("RECORDER_MIN_UPSTREAM_SECONDS", 60.0),
            header=seconds("RECORDER_HEADER_DEADLINE_SECONDS", 30.0),
            body=seconds("RECORDER_BODY_DEADLINE_SECONDS", 60.0),
            client_write=seconds("RECORDER_CLIENT_WRITE_DEADLINE_SECONDS", 60.0),
            io_timeout=seconds("RECORDER_IO_TIMEOUT_SECONDS", 60.0),
            tick=seconds("RECORDER_WATCHDOG_TICK_SECONDS", 0.25),
        )


def timing_problems(timing: Timing) -> list[str]:
    """Why a profile cannot keep its promise; empty when it can. Startup refuses on any."""
    problems = []
    # Finiteness first, before any arithmetic: NaN fails every comparison
    # (so `<= 0` cannot catch it) and an infinite value poisons every sum.
    for field in dataclasses.fields(timing):
        value = getattr(timing, field.name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            problems.append(f"{field.name} must be a finite number, not {value!r}")
        elif value <= 0:
            problems.append(f"{field.name} must be positive, not {value!r}")
    if problems:
        return problems
    if not (math.isfinite(timing.e2e_budget) and math.isfinite(timing.upstream_offset)):
        return ["the derived deadlines are not finite"]
    if timing.e2e_budget + timing.client_margin > timing.client_timeout:
        problems.append("the end-to-end budget plus the client margin exceeds the client timeout")
    if timing.upstream_offset < timing.min_upstream + timing.header:
        problems.append(
            "the upstream cutoff leaves less than MIN_UPSTREAM after the header deadline; "
            "raise RECORDER_TIMEOUT_SECONDS on both sides together"
        )
    return problems


class MonotonicClock:
    """The clock every deadline decision reads. Tests replace it with a fake."""

    @staticmethod
    def monotonic() -> float:
        return time.monotonic()


TIMING = Timing.from_env()
CLOCK = MonotonicClock()


def now() -> float:
    return CLOCK.monotonic()


@dataclass(frozen=True)
class Deadlines:
    """One request's absolute deadlines, all from its accept instant t0."""

    t0: float
    timing: Timing

    @property
    def header_end(self) -> float:
        return min(self.t0 + self.timing.header, self.latest_start)

    @property
    def upstream_abs(self) -> float:
        return self.t0 + self.timing.upstream_offset

    @property
    def latest_start(self) -> float:
        return self.upstream_abs - self.timing.min_upstream

    @property
    def e2e_end(self) -> float:
        return self.t0 + self.timing.e2e_budget

    def body_end(self, header_done: float) -> float:
        return min(header_done + self.timing.body, self.latest_start)


SHUT_INGRESS = socket.SHUT_RD  # the handler can still write its 408
SHUT_ALL = socket.SHUT_RDWR
DIAG_QUEUE = env_int("RECORDER_DIAG_QUEUE", 256)


class WatchEntry:
    """One phase deadline. `owned` until its owner cancels; `pending` until it fires."""

    __slots__ = ("deadline", "seq", "sock", "rid", "phase", "how", "owned", "pending", "fired")

    def __init__(self, deadline, seq, sock, rid, phase, how) -> None:
        self.deadline = deadline
        self.seq = seq
        self.sock = sock
        self.rid = rid
        self.phase = phase
        self.how = how
        self.owned = True
        self.pending = True
        self.fired = False


class Watchdog:
    """One recorder-wide heap of (deadline, socket, rid, phase), and one thread.

    At a deadline it marks the entry fired and shuts its socket down: SHUT_RD
    for the ingress phases, so the handler can still write its 408, SHUT_RDWR
    for the upstream and client-write phases. A blocked recv or send then
    returns and the handler classifies by the `fired` flag, not by error text.

    Ownership: whoever registers a socket cancels its entry before closing
    that socket. The shutdown happens under this watchdog's own lock, and
    cancel takes the same lock, so a shutdown can never reach a descriptor
    number that has been closed and reused by another connection.

    Enforcement touches nothing but this lock and sockets: no file, no
    record, no Budget. Its diagnostics go into a bounded deque under the same
    lock (`put_nowait`); a full deque counts `dropped`; a separate writer
    thread drains it to recorder.jsonl, and a stalled or failing writer delays
    only the diagnostics. A dropped count is cleared only by the amount a
    later readable diagnostic actually reported.
    """

    def __init__(self, *, clock=None, tick: float | None = None, queue_size: int | None = None,
                 writer=None) -> None:
        self._clock = clock
        self._tick = tick
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._heap: list[tuple[float, int, WatchEntry]] = []
        self._seq = itertools.count(1)
        self._active = 0
        self._stale = 0
        self._thread: threading.Thread | None = None
        self._stopping = False
        self.queue: deque[dict] = deque()
        self.queue_size = DIAG_QUEUE if queue_size is None else queue_size
        self.dropped = 0
        self._writer = writer
        self._writer_thread: threading.Thread | None = None
        self._diag_wake = threading.Condition(self._lock)

    # -- time -----------------------------------------------------------------
    def _now(self) -> float:
        return self._clock.monotonic() if self._clock is not None else now()

    def _tick_seconds(self) -> float:
        return self._tick if self._tick is not None else TIMING.tick

    # -- registration ---------------------------------------------------------
    def register(self, sock, deadline: float, rid: str | None, phase: str, how: int) -> WatchEntry:
        if not math.isfinite(deadline):
            # A NaN never compares due and would sit at the heap's root, so
            # nothing behind it would ever fire.
            raise ValueError("a watchdog deadline must be finite")
        with self._lock:
            entry = WatchEntry(deadline, next(self._seq), sock, rid, phase, how)
            heapq.heappush(self._heap, (deadline, entry.seq, entry))
            self._active += 1
            self._ensure_thread()
            self._wake.notify()
            return entry

    def rebind(self, entry: WatchEntry, sock) -> None:
        """Point an owned entry at the socket that replaced its own (a TLS wrap).

        If the deadline already fired, the new socket is shut down at once.
        """
        with self._lock:
            if not entry.owned:
                return
            entry.sock = sock
            if entry.fired:
                self._shutdown(entry)

    def cancel(self, entry: WatchEntry | None) -> bool:
        """Release an entry; True if it had fired. Idempotent. Call before closing its socket."""
        if entry is None:
            return False
        with self._lock:
            if entry.owned:
                entry.owned = False
                entry.sock = None
                self._active -= 1
                if entry.pending:
                    entry.pending = False
                    self._stale += 1
                    # Retire cancelled entries once they outnumber the live
                    # ones, so completed phases never pile up behind a long
                    # deadline in the heap.
                    if self._stale > 64 and self._stale > 2 * len(self._heap) - 2 * self._stale:
                        self._heap = [item for item in self._heap if item[2].pending]
                        heapq.heapify(self._heap)
                        self._stale = 0
            return entry.fired

    def counts(self) -> dict:
        with self._lock:
            return {"active": self._active, "heap": len(self._heap), "queued": len(self.queue),
                    "dropped": self.dropped}

    # -- enforcement ----------------------------------------------------------
    def _ensure_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="recorder-watchdog", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        with self._lock:
            while not self._stopping:
                self._wake.wait(self._tick_seconds())
                self._fire_due_locked()

    def fire_due(self) -> None:
        """Fire every due entry now (the loop does this every tick; tests may too)."""
        with self._lock:
            self._fire_due_locked()

    def _fire_due_locked(self) -> None:
        current = self._now()
        while self._heap and self._heap[0][0] <= current:
            _deadline, _seq, entry = heapq.heappop(self._heap)
            if not entry.pending:
                self._stale = max(0, self._stale - 1)
                continue
            entry.pending = False
            entry.fired = True
            # Still owned: the owner's cancel is what releases the socket for
            # closing, so this shutdown cannot reach a reused descriptor.
            self._shutdown(entry)
            self._put_locked(
                {"event": "request_overdue", "id": entry.rid, "phase": entry.phase,
                 "overdue_s": round(current - entry.deadline, 3)}
            )

    @staticmethod
    def _shutdown(entry: WatchEntry) -> None:
        sock = entry.sock
        if sock is None:
            return
        # Nothing raised here may reach the watchdog's loop: one bad socket
        # must not end enforcement for every other request.
        with contextlib.suppress(Exception):
            if isinstance(sock, socket.socket):
                # The base-class method on the descriptor: for a TLS socket this
                # interrupts a blocked read without touching its SSL state.
                socket.socket.shutdown(sock, entry.how)
            else:
                sock.shutdown(entry.how)

    def stop(self) -> None:
        with self._lock:
            self._stopping = True
            self._wake.notify_all()
            self._diag_wake.notify_all()

    # -- diagnostics ----------------------------------------------------------
    def put_nowait(self, record: dict) -> bool:
        with self._lock:
            return self._put_locked(record)

    def _put_locked(self, record: dict) -> bool:
        if len(self.queue) >= self.queue_size:
            self.dropped += 1
            return False
        self.queue.append(record)
        if self._writer is not None or self._writer_thread is not None:
            self._ensure_writer()
        self._diag_wake.notify()
        return True

    def start_writer(self, writer) -> None:
        with self._lock:
            self._writer = writer
            self._ensure_writer()

    def _ensure_writer(self) -> None:
        if self._writer is None:
            return
        if self._writer_thread is None or not self._writer_thread.is_alive():
            self._writer_thread = threading.Thread(
                target=self._drain, name="recorder-diagnostics", daemon=True
            )
            self._writer_thread.start()

    def _drain(self) -> None:
        while True:
            with self._lock:
                while not self.queue and not self._stopping:
                    self._diag_wake.wait(1.0)
                if self._stopping and not self.queue:
                    return
                record = self.queue.popleft()
                dropped = self.dropped
            if dropped:
                record = {**record, "diag_dropped": dropped}
            try:
                result = self._writer(record)
                readable = bool(getattr(result, "readable", False))
            except Exception:  # noqa: BLE001 -- a diagnostic's failure is not reported about
                readable = False
            if readable and dropped:
                with self._lock:
                    self.dropped -= dropped


# The writer is looked up at call time: diagnostics land in whichever
# TRANSCRIPTS_DIR is current when they are drained.
WATCHDOG = Watchdog(writer=lambda record: record_diagnostic(record))


# The process-wide bound on accepted connections, taken before a handler thread
# exists. A connection over it gets a canned 503 and is closed.
MAX_CONNECTIONS = env_int("RECORDER_MAX_CONNECTIONS", 64)
CONNECTIONS = threading.BoundedSemaphore(max(1, MAX_CONNECTIONS))
def canned_response(status: str, code: str, message: str) -> bytes:
    """A complete response for a connection that has no handler, or no parsed request."""
    body = json.dumps({"error": {"message": message, "type": "recorder", "code": code}}).encode()
    head = (
        f"HTTP/1.1 {status}\r\nContent-Type: application/json\r\nConnection: close\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    )
    return head.encode("ascii") + body


CONNECTION_REFUSED_RESPONSE = canned_response(
    "503 Service Unavailable", "connections", "the recorder has too many open connections"
)
HEADER_TIMEOUT_RESPONSE = canned_response(
    "408 Request Timeout", "header_deadline", "the request headers did not arrive in time"
)
_COUNTERS_LOCK = threading.Lock()
_COUNTERS: dict[str, int] = {}
COUNTER_FLUSH_SECONDS = 10.0
_COUNTERS_FLUSHED = [0.0]


def count_event(name: str) -> None:
    """A rate-limited counter for events with no request id (refused accepts, header stage)."""
    with _COUNTERS_LOCK:
        _COUNTERS[name] = _COUNTERS.get(name, 0) + 1
        current = time.monotonic()
        if current - _COUNTERS_FLUSHED[0] < COUNTER_FLUSH_SECONDS:
            return
        _COUNTERS_FLUSHED[0] = current
        snapshot = dict(_COUNTERS)
        _COUNTERS.clear()
    if not WATCHDOG.put_nowait({"event": "counters", **snapshot}):
        # Not lost silently: they wait for the next flush.
        with _COUNTERS_LOCK:
            for key, value in snapshot.items():
                _COUNTERS[key] = _COUNTERS.get(key, 0) + value


# -- structure: a linear pre-scan before any json.loads -----------------------
# Caps per SV-015 v2 section 2.2. The pre-scan counts, outside strings, the
# nesting depth, the containers ({ and [) and the values (each container, each
# string literal -- keys included -- and each scalar token). It allocates
# nothing per token: it indexes the bytes and skips strings with bytes.find. It
# is not a JSON validator; json.loads still decides validity afterwards.
REQUEST_CAPS = (64, 32_768, 131_072)  # depth, containers, values
RESPONSE_CAPS = (64, 8_192, 32_768)
_QUOTE, _BACKSLASH = 0x22, 0x5C
_OPEN = frozenset(b"{[")
_CLOSE = frozenset(b"}]")
_SEPARATORS = frozenset(b" \t\r\n,:")


@dataclass(frozen=True)
class Scan:
    depth: int
    containers: int
    values: int
    exceeded: str | None  # "depth" | "containers" | "values" | None


def prescan(data: bytes, caps: tuple[int, int, int]) -> Scan:
    max_depth, max_containers, max_values = caps
    depth = deepest = containers = values = 0
    in_scalar = False
    index, size = 0, len(data)
    while index < size:
        byte = data[index]
        if byte == _QUOTE:
            in_scalar = False
            values += 1
            if values > max_values:
                return Scan(deepest, containers, values, "values")
            # Skip to the closing quote that is not escaped.
            cursor = index + 1
            while True:
                quote = data.find(b'"', cursor)
                if quote < 0:
                    return Scan(deepest, containers, values, None)  # unterminated: json.loads decides
                slashes = 0
                back = quote - 1
                while back > index and data[back] == _BACKSLASH:
                    slashes += 1
                    back -= 1
                if slashes % 2 == 0:
                    break
                cursor = quote + 1
            index = quote + 1
            continue
        if byte in _OPEN:
            in_scalar = False
            depth += 1
            containers += 1
            values += 1
            deepest = max(deepest, depth)
            if depth > max_depth:
                return Scan(deepest, containers, values, "depth")
            if containers > max_containers:
                return Scan(deepest, containers, values, "containers")
            if values > max_values:
                return Scan(deepest, containers, values, "values")
        elif byte in _CLOSE:
            in_scalar = False
            depth = max(0, depth - 1)
        elif byte in _SEPARATORS:
            in_scalar = False
        elif not in_scalar:
            in_scalar = True
            values += 1
            if values > max_values:
                return Scan(deepest, containers, values, "values")
        index += 1
    return Scan(deepest, containers, values, None)


# -- memory: a reservation before parsing ---------------------------------------
MAX_RESPONSE = env_int("RECORDER_MAX_RESPONSE_BYTES", 2 * 1024 * 1024)
MEMORY_BUDGET_BYTES = env_int("RECORDER_MEMORY_BUDGET_BYTES", 768 * 1024 * 1024)
VALUE_COST = 256


def memory_for_request(body_bytes: int, values: int) -> int:
    """M_req = 33*B + 256*V (raw, decoded, parsed, forwarded and recorded forms)."""
    return 33 * body_bytes + VALUE_COST * values


def memory_for_response() -> int:
    """M_resp = 21*MAX_RESPONSE + 256*V_resp_cap, reserved up front."""
    return 21 * MAX_RESPONSE + VALUE_COST * RESPONSE_CAPS[2]


class MemoryBudget:
    """A process-wide byte reservation, waited for in arrival order of wake-ups.

    The reservation is arithmetic: it bounds what concurrent requests are
    allowed to hold by the per-request estimates above. Whether those estimates
    bound real interpreter allocation is unmeasured (commissioning C1).
    """

    def __init__(self, total: int) -> None:
        self.total = total
        self.used = 0
        self._cond = threading.Condition()

    def reserve(self, amount: int, timeout: float) -> bool:
        if amount > self.total:
            return False
        deadline = time.monotonic() + max(0.0, timeout)
        with self._cond:
            while self.used + amount > self.total:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            self.used += amount
            return True

    def release(self, amount: int) -> None:
        with self._cond:
            self.used -= amount
            self._cond.notify_all()


MEMORY = MemoryBudget(MEMORY_BUDGET_BYTES)


# -- responses: usage from JSON or SSE, honest about what was not parsed ---------
SSE_LEADING = b" \t\r\n"  # optional whitespace allowed before the first `data:`


def sse_usage(body: bytes) -> tuple[Usage, bool]:
    """(usage, structure_limit) from a server-sent-events body.

    CRLF is normalized; events are split on blank lines; each event's `data:`
    lines are joined with newlines (one optional leading space removed);
    `[DONE]` is skipped; each event is pre-scanned and parsed on its own. The
    usage is the last event's valid usage. Any event over the structure caps
    makes the whole response's usage unknown, conservatively, even if another
    event carried a valid usage. Provider dialects beyond this are unvalidated.
    """
    # Only the whitespace `is_event_stream` accepts before the first `data:`
    # is removed, so detection and extraction agree. No other line is touched,
    # and the relayed bytes are never this parsed copy.
    text = body.lstrip(SSE_LEADING).decode("utf-8", "replace").replace("\r\n", "\n")
    found = Usage(UNKNOWN)
    for event in text.split("\n\n"):
        data = [line[5:] for line in event.split("\n") if line.startswith("data:")]
        if not data:
            continue
        joined = "\n".join(part[1:] if part.startswith(" ") else part for part in data)
        if joined.strip() == "[DONE]":
            continue
        encoded = joined.encode("utf-8", "surrogatepass")
        if prescan(encoded, RESPONSE_CAPS).exceeded:
            return Usage(UNKNOWN), True
        try:
            parsed = json.loads(joined, parse_constant=_nonfinite_marker, parse_float=_float_or_marker)
        except (ValueError, RecursionError):
            continue
        usage = extract_usage(parsed)
        if usage.cls == KNOWN:
            found = usage
    return found, False


def is_event_stream(payload: bytes) -> bool:
    """By content, not Content-Type: the stub sends SSE as application/json."""
    return payload.lstrip(SSE_LEADING).startswith(b"data:")


@dataclass
class ResponseView:
    """What the record holds about one upstream response, and what it cost."""

    data: object  # the transcript's `response` field
    usage: Usage
    structure_limit: bool = False
    cap_exceeded: bool = False


def view_response(payload: bytes, truncated: bool) -> ResponseView:
    if truncated:
        # Never parsed: a prefix's usage is not evidence of what was billed.
        return ResponseView(
            {
                "raw_body": payload.decode("utf-8", "backslashreplace"),
                "raw_body_truncated": True,
                "response_cap_exceeded": True,
                "kept_bytes": len(payload),
            },
            Usage(UNKNOWN),
            cap_exceeded=True,
        )
    if is_event_stream(payload):
        usage, limited = sse_usage(payload)
        view = ResponseView(decode_payload(payload), usage, structure_limit=limited)
        return view
    if prescan(payload, RESPONSE_CAPS).exceeded:
        text = payload.decode("utf-8", "ignore")
        data = {"raw_body": text[:1_000_000], "structure_limit": True}
        if len(text) > 1_000_000:
            data["raw_body_truncated"] = True
        return ResponseView(data, Usage(UNKNOWN), structure_limit=True)
    data = decode_payload(payload)
    return ResponseView(data, extract_usage(data))


class AgentState:
    """Per-agent bookkeeping: where its record goes, and its in-flight slots."""

    def __init__(self, slug: str, transcript_dir: Path) -> None:
        self.slug = slug
        self.dir = transcript_dir / slug
        # Never the root: a name whose parent this process did not see exist
        # cannot be fenced. The root is the deployment's to provide.
        self.dir.mkdir(parents=False, exist_ok=True)
        self.store = store_for(transcript_dir)
        self.transcript = self.dir / "agent_life_transcript.jsonl"
        self.events = self.dir / "events.jsonl"
        self.slots = threading.BoundedSemaphore(max(1, MAX_INFLIGHT_PER_SOCKET))
        self._labels: OrderedDict[str, None] = OrderedDict()
        self._labels_lock = threading.Lock()

    def label_seen_before(self, label: str) -> bool:
        """Whether this socket saw the label recently. A hint for a reader, nothing more."""
        with self._labels_lock:
            seen = label in self._labels
            self._labels[label] = None
            self._labels.move_to_end(label)
            while len(self._labels) > max(0, MAX_LABEL_LRU):
                self._labels.popitem(last=False)
            return seen


class Accepted(tuple):
    """The handler's `client_address`: a unix peer has no address, but it has an accept time."""

    def __new__(cls, t0: float):
        accepted = super().__new__(cls, ("unix", 0))
        accepted.t0 = t0
        return accepted


def refuse_connection(sock) -> None:
    """A canned 503 to a connection over the bound, written briefly and once."""
    with contextlib.suppress(OSError):
        sock.settimeout(1.0)
        sock.sendall(CONNECTION_REFUSED_RESPONSE)


class Recorder(threading.Thread):
    """One listener, on one agent's socket, in its own thread."""

    def __init__(self, state: AgentState, shared: Budget, expected_key: str) -> None:
        super().__init__(daemon=True)
        self.state = state
        self.shared = shared
        self.expected_key = expected_key
        self.socket_path = SOCKET_DIR / f"{state.slug}.sock"
        self.server: socketserver.UnixStreamServer | None = None

    def run(self) -> None:
        handler = make_handler(self)

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True
            allow_reuse_address = False
            request_queue_size = 64

            def server_bind(self):
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(self.server_address)
                socketserver.UnixStreamServer.server_bind(self)
                os.chmod(self.server_address, 0o666)

            def get_request(self):
                conn, _ = self.socket.accept()
                # t0: every deadline of this connection's one request counts from here.
                return conn, Accepted(now())

            def process_request(self, request, client_address):
                # The connection bound is taken before a handler thread exists.
                if not CONNECTIONS.acquire(blocking=False):
                    refuse_connection(request)
                    count_event("connections_refused")
                    self.shutdown_request(request)
                    return
                try:
                    super().process_request(request, client_address)
                except BaseException:
                    CONNECTIONS.release()
                    raise

            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    CONNECTIONS.release()

        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        server = Server(str(self.socket_path), handler)
        self.server = server
        log(f"listening on {self.socket_path}")
        server.serve_forever(poll_interval=0.5)

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self.socket_path)


def log(message: str) -> None:
    """One line on stdout, attempted once. A log is not part of any record.

    If the log's reader has gone (a broken pipe, a closed stream), the line is
    lost and the request carries on: no outcome, status or record may depend
    on whether a container log was being read. Control exceptions still pass.
    """
    with contextlib.suppress(OSError, ValueError):
        print(f"{iso()} [recorder] {message}", flush=True)


BOOT = os.urandom(4).hex()
_RID_COUNTER = itertools.count(1)
# The fleet-wide half of the in-flight bound; each socket holds its own half.
# Together they bound the live reservations, and so the budget's memory.
TOTAL_SLOTS = threading.BoundedSemaphore(max(1, MAX_INFLIGHT_TOTAL))


def next_rid() -> str:
    """A request id unique within this process: the boot, then a counter."""
    return f"{BOOT}-{next(_RID_COUNTER):08d}"


# ---------------------------------------------------------------------------
# Custody
# ---------------------------------------------------------------------------
# Every line the recorder writes goes through one RecordStore per transcript
# root (common.RecordStore: ASCII JSON, a lock per file, a boundary check from
# disk before every append, per-slug name fencing, a typed result). The rules
# that hang on those results:
#
# * the `open` must be readable before anything is admitted or contacted, or
#   the request is refused 503 record_unavailable;
# * the free-space check before the `open` is a prediction, not a reservation:
#   below RECORDER_MIN_FREE_BYTES the request is refused 503 record_capacity
#   before anything is spent, and other writers can still fill the disk after;
# * the upstream response is relayed only if its transcript line is readable
#   (appended, appended_fsync_failed or durable); failed or partial withholds
#   it as 502 record_failed. A failed data sync lowers the evidence's quality
#   and is recorded; it does not withhold an answer whose bytes are readable;
# * a `close` that cannot be written leaves one bounded JSON line on stderr.
#
# One recorder process writes a given TRANSCRIPTS_DIR, and the directory
# already exists when it starts: its creation and durability are the host's.
RECORD_FSYNC = env_bool("RECORDER_RECORD_FSYNC", True)
MIN_FREE_BYTES = env_int("RECORDER_MIN_FREE_BYTES", 1024 * 1024 * 1024)
DIAGNOSTICS_NAME = "recorder.jsonl"
_STORES: dict[Path, RecordStore] = {}
_STORES_LOCK = threading.Lock()
_DEGRADED_REPORTED: set[tuple[Path, Path]] = set()


def store_for(root: Path) -> RecordStore:
    """The one store for a transcript root, created on first use."""
    root = Path(root)
    with _STORES_LOCK:
        store = _STORES.get(root)
        if store is None:
            # Two files per slug plus the root's diagnostics file.
            store = _STORES[root] = RecordStore(root, max_paths=2 * max(1, MAX_SLUGS) + 1)
        return store


def close_stores() -> None:
    """Close every cached descriptor: for shutdown, and for a test's teardown."""
    with _STORES_LOCK:
        stores = list(_STORES.values())
        _STORES.clear()
        _DEGRADED_REPORTED.clear()
    for store in stores:
        store.close()


def append_with_custody(store: RecordStore, path: Path, record: dict) -> AppendResult:
    """Append one record and report a newly degraded file once, without recursing.

    The append's result is the fact; the report about it is optional. Once the
    result exists it is always returned: an ordinary failure while reporting
    (a closed log, a diagnostics file that cannot be written) is contained, so
    a readable transcript is still relayed and still recorded as readable. The
    report is attempt-only evidence -- it is tried once per file per process
    and never retried or reported about in turn. Control exceptions propagate.
    """
    result = store.append_record(path, record, fsync=RECORD_FSYNC)
    if result.status == "appended_fsync_failed":
        key = (store.root, Path(path))
        with _STORES_LOCK:
            first = key not in _DEGRADED_REPORTED
            _DEGRADED_REPORTED.add(key)
        if first:
            try:
                relative = str(Path(path).relative_to(store.root))
                log(f"durability degraded: a data sync failed on {relative}")
                if Path(path).name != DIAGNOSTICS_NAME:
                    record_diagnostic({"event": "durability_degraded", "file": relative})
            except Exception:  # noqa: BLE001 -- reporting must not replace the result
                pass
    return result


def record_diagnostic(record: dict) -> AppendResult:
    """One line in TRANSCRIPTS_DIR/recorder.jsonl, the process's own record.

    It sits at the root beside the per-agent directories, so nothing that
    discovers agents by directory mistakes it for one, and nothing about the
    process lands in an agent's events. Its own failures are only logged.
    """
    path = TRANSCRIPTS_DIR / DIAGNOSTICS_NAME
    return append_with_custody(store_for(TRANSCRIPTS_DIR), path, {"at": iso(), **record})


def free_bytes(path: Path) -> int | None:
    """Bytes available to this process on the record's filesystem, or None if unknowable."""
    try:
        stats = os.statvfs(path)
    except OSError:
        return None
    return stats.f_bavail * stats.f_frsize


class Exchange:
    """One request's bookkeeping, owned by the one thread handling it.

    The flags are what make the handler's promises hold on every path,
    including an exception halfway through: an admitted request is closed in
    the budget exactly once, its slots are released exactly once, and at most
    one `close` event is attempted.
    """

    def __init__(self, rid: str, t0: float | None = None) -> None:
        self.rid = rid
        self.started = now()
        # The connection's accept instant, and every deadline derived from it.
        self.t0 = self.started if t0 is None else t0
        self.deadlines = Deadlines(self.t0, TIMING)
        # The slot and memory waits share this allowance of actual waiting.
        self.wait_left = float(INFLIGHT_WAIT_SECONDS)
        self.memory = 0
        self.memory_pool: MemoryBudget | None = None
        # When the response (or recorder error) attempt began, and when the
        # upstream's answer was in hand: elapsed_s and custody_s measure to
        # these, never to the close append that follows.
        self.ready_at: float | None = None
        self.custody_from: float | None = None
        self.settled_at: float | None = None
        self.slots = False
        self.admitted = False
        self.accounted: Closed | None = None
        # Set when a response *attempt* begins, before any byte is written.
        self.responded = False
        self.event_written = False
        # The status selected for the client, once an attempt to send it began.
        # It is not proof of delivery: a write can fail, or a control exception
        # can unwind at the start of the attempt, with this already set.
        self.status: int | None = None
        # The transcript append's result, once attempted.
        self.recorded: AppendResult | None = None
        self.outcome: str | None = None
        self.refusal: str | None = None
        self.estimate: int | None = None
        self.usage: Usage | None = None
        self.upstream_status: int | None = None
        # True only once the upstream's own response has been written to the
        # client. A recorder error that reached the client is not a relay.
        self.relayed = False


def make_handler(recorder: Recorder):
    state = recorder.state
    budget = recorder.shared

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "space-chassis-recorder/0.1"

        def log_message(self, fmt, *args):  # noqa: A003 -- base class signature
            pass

        # -- the connection: one request, headers under a deadline --------------
        def setup(self):
            super().setup()
            self.t0 = getattr(self.client_address, "t0", None)
            if self.t0 is None:
                self.t0 = now()
            self.response_started = False
            self.header_done: float | None = None
            self.connection.settimeout(TIMING.io_timeout)
            self.header_watch = WATCHDOG.register(
                self.connection,
                Deadlines(self.t0, TIMING).header_end,
                None,
                "header",
                SHUT_INGRESS,
            )

        def handle(self):
            """Exactly one request per connection: the response says Connection: close.

            A request whose headers never completed has no request to close in
            the events: if the header deadline cut it off, it gets a canned 408
            and a counter, and nothing else is invented about it.
            """
            try:
                self.handle_one_request()
                self.close_connection = True
                if self.header_done is None:
                    fired = WATCHDOG.cancel(self.header_watch)
                    if fired and not self.response_started:
                        with contextlib.suppress(OSError):
                            self.connection.settimeout(1.0)
                            self.connection.sendall(HEADER_TIMEOUT_RESPONSE)
                        count_event("header_deadline")
                    elif self.response_started:
                        count_event("header_refused")
            finally:
                WATCHDOG.cancel(self.header_watch)

        def send_response_only(self, code, message=None):
            self.response_started = True
            super().send_response_only(code, message)

        def parse_request(self):
            """The stdlib's parse, unless the header deadline cut the input short.

            A shut read side looks like the end of the request line or of the
            headers; parsing that fragment would answer a timeout with a 400
            about syntax, or treat a half-sent request as complete.
            """
            if self.header_watch.fired:
                self.close_connection = True
                return False
            parsed = super().parse_request()
            if parsed and self.header_watch.fired:
                self.close_connection = True
                return False
            return parsed

        def _begin(self) -> tuple[Exchange, bool]:
            """Headers are complete: end their phase and start the request's bookkeeping."""
            self.header_done = now()
            late = WATCHDOG.cancel(self.header_watch)
            self.close_connection = True
            return Exchange(next_rid(), self.t0), late

        # -- the one exit -----------------------------------------------------
        def do_GET(self):  # noqa: N802 -- base class API
            exchange, _late = self._begin()
            try:
                self._refuse(
                    exchange,
                    405,
                    "method_not_allowed",
                    "this socket accepts POST /api/v1/chat/completions only",
                )
            finally:
                self._finish(exchange)

        def do_POST(self):  # noqa: N802 -- base class API
            exchange, late = self._begin()
            try:
                if late:
                    # The deadline fired as the headers completed: the read
                    # side is already shut, so the body can never arrive.
                    self._refuse(
                        exchange, 408, "header_deadline", "the request headers did not arrive in time"
                    )
                    return
                self._post(exchange)
            except Exception as error:  # noqa: BLE001 -- the client still gets a status
                # Only the exception's type is kept: its text can carry a URL.
                log(f"{state.slug}: {exchange.rid}: internal error: {type(error).__name__}")
                if exchange.responded:
                    exchange.outcome = "internal_error"
                    self.close_connection = True
                else:
                    self._refuse(
                        exchange,
                        500,
                        "internal_error",
                        "the recorder failed while handling this request "
                        f"({type(error).__name__})",
                    )
            except BaseException:
                # A control exception (SystemExit, KeyboardInterrupt...) unwinds
                # through here and keeps going. Its `close` gets a fixed outcome,
                # and no status unless a response attempt had already begun.
                if not exchange.responded:
                    exchange.status = None
                exchange.outcome = "aborted"
                raise
            finally:
                self._finish(exchange)

        def _finish(self, exchange: Exchange) -> None:
            """Release what this request holds, then write its one `close`.

            A request that was admitted and never closed in the budget -- an
            exception got there first -- is closed here: cancelled if nothing
            was sent, settled at its estimate if anything may have been.
            """
            try:
                if exchange.admitted and exchange.accounted is None:
                    self._account(exchange, Usage(UNKNOWN))
            finally:
                try:
                    if exchange.memory:
                        amount, exchange.memory = exchange.memory, 0
                        exchange.memory_pool.release(amount)
                finally:
                    if exchange.slots:
                        exchange.slots = False
                        TOTAL_SLOTS.release()
                        state.slots.release()
                    self._write_close(exchange)

        def _account(self, exchange: Exchange, usage: Usage) -> None:
            exchange.accounted = budget.close(exchange.rid, usage)
            exchange.settled_at = now()

        def _write_close(self, exchange: Exchange) -> None:
            if exchange.event_written:
                return
            exchange.event_written = True
            record = {
                "at": iso(),
                "event": "close",
                "id": exchange.rid,
                "agent": state.slug,
                "status": exchange.status,
            }
            if exchange.refusal is not None:
                record["refusal"] = exchange.refusal
            accounted = exchange.accounted
            if accounted is not None:
                record["duration_seconds"] = round(exchange.settled_at - exchange.started, 3)
                settled = accounted.kind == "settled" and exchange.usage is not None
                record["usage"] = exchange.usage.raw if settled else None
            record["outcome"] = exchange.outcome
            if exchange.estimate is not None:
                record["estimate"] = exchange.estimate
            if accounted is not None:
                record["usage_class"] = accounted.usage_class or "none"
                record["charged_tokens"] = accounted.charge
                if accounted.late:
                    record["late_adjustment"] = list(accounted.late)
            if exchange.upstream_status is not None:
                record["upstream_status"] = exchange.upstream_status
            record["relayed"] = exchange.relayed
            if exchange.recorded is not None:
                record["recorded"] = exchange.recorded.status
                if exchange.recorded.dir_unsynced:
                    record["dir_unsynced"] = True
            # Measured to the response attempt (or, with none, to now): this
            # record cannot know how long its own append will take.
            ready = exchange.ready_at if exchange.ready_at is not None else now()
            record["elapsed_s"] = round(ready - exchange.t0, 3)
            if exchange.custody_from is not None:
                record["custody_s"] = round(ready - exchange.custody_from, 3)
            record["deadline_overrun"] = ready > exchange.deadlines.e2e_end
            try:
                result = append_with_custody(state.store, state.events, record)
                unrecorded = None if result.readable else result.status
            except Exception as error:  # noqa: BLE001 -- the last resort is the container log
                unrecorded = type(error).__name__
            if unrecorded is not None:
                # One bounded line, fixed keys, no request content and no header:
                # the only evidence left when the events file cannot take it.
                fallback = {
                    "id": exchange.rid,
                    "agent": state.slug,
                    "outcome": exchange.outcome,
                    "status": exchange.status,
                    "transcript": exchange.recorded.status if exchange.recorded else None,
                    "close_unrecorded": unrecorded,
                }
                # Attempted once; if stderr is gone too, nothing is left to tell.
                with contextlib.suppress(OSError, ValueError):
                    print(json.dumps(fallback), file=sys.stderr, flush=True)

        # -- replies ----------------------------------------------------------
        def _relay(self, exchange: Exchange, status: int, headers: dict, payload: bytes) -> bool:
            """Write one response under the client-write deadline. False if it did not complete.

            The phase shuts the connection both ways at its deadline; a fired
            phase is a failed write whatever the last send returned.
            """
            if exchange.ready_at is None:
                exchange.ready_at = now()
            entry = WATCHDOG.register(
                self.connection, now() + TIMING.client_write, exchange.rid, "client_write", SHUT_ALL
            )
            try:
                self.connection.settimeout(max(0.001, min(TIMING.io_timeout, TIMING.client_write)))
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)
                written = True
            except OSError:
                written = False
            finally:
                fired = WATCHDOG.cancel(entry)
            self.close_connection = True
            return written and not fired

        def _refuse(self, exchange: Exchange, status: int, outcome: str, message: str) -> None:
            exchange.status, exchange.outcome, exchange.refusal = status, outcome, message
            body = json.dumps(
                {"error": {"message": message, "type": "recorder", "code": outcome}}
            ).encode()
            self.close_connection = True
            exchange.responded = True
            # Whether this error reached the client is not recorded as `relayed`:
            # that field is about the upstream's response.
            self._relay(exchange, status, {"Content-Type": "application/json"}, body)

        def _take_slots(self, timeout: float) -> bool:
            """One of this socket's slots, then one of the fleet's, waiting at most `timeout`.

            The socket's own slot is taken first so a busy socket waits on itself
            without holding fleet capacity while it does. If taking the second
            fails in any way -- a timeout or a raise -- the first is given back
            here, because the caller only owns the pair once this returns True.
            """
            timeout = max(0.0, timeout)
            deadline = time.monotonic() + timeout
            if not state.slots.acquire(timeout=timeout):
                return False
            taken = False
            try:
                taken = TOTAL_SLOTS.acquire(timeout=max(0.0, deadline - time.monotonic()))
            finally:
                if not taken:
                    state.slots.release()
            return taken

        def _wait(self, exchange: Exchange, acquire) -> bool:
            """Spend the shared wait allowance on one acquisition, capped by the latest start."""
            cap = min(exchange.wait_left, exchange.deadlines.latest_start - now())
            started = time.monotonic()
            try:
                return acquire(max(0.0, cap))
            finally:
                exchange.wait_left = max(0.0, exchange.wait_left - (time.monotonic() - started))

        def _read_body(self, exchange: Exchange, length: int) -> bytes | None:
            """Exactly `length` bytes under the body deadline, or a refusal (returns None).

            The deadline counts from header completion and never passes the
            latest start. The watchdog shuts the read side at the deadline;
            each read also has the per-operation timeout.
            """
            end = exchange.deadlines.body_end(self.header_done)
            entry = WATCHDOG.register(self.connection, end, exchange.rid, "body", SHUT_INGRESS)
            chunks: list[bytes] = []
            got = 0
            timed_out = False
            try:
                while got < length:
                    remaining = end - now()
                    if remaining <= 0:
                        timed_out = True
                        break
                    self.connection.settimeout(max(0.001, min(TIMING.io_timeout, remaining)))
                    try:
                        chunk = self.rfile.read1(min(65536, length - got))
                    except TimeoutError:
                        timed_out = True
                        break
                    if not chunk:
                        break
                    chunks.append(chunk)
                    got += len(chunk)
            finally:
                fired = WATCHDOG.cancel(entry)
            if fired or timed_out:
                self._refuse(
                    exchange, 408, "body_deadline", "the request body did not arrive in time"
                )
                return None
            if got < length:
                # The client stopped early. Nothing partial is ever forwarded.
                self._refuse(
                    exchange,
                    400,
                    "short_body",
                    f"the request body ended after {got} of {length} bytes",
                )
                return None
            return b"".join(chunks)

        # -- the request ------------------------------------------------------
        def _post(self, exchange: Exchange) -> None:
            path = self.path.split("?", 1)[0]
            if not path.endswith(ROUTE_SUFFIX):
                self._refuse(
                    exchange,
                    404,
                    "not_found",
                    f"no route {self.path!r}; this socket serves a chat-completions "
                    f"endpoint, most simply at {ROUTE}",
                )
                return
            # Presence, not value: an empty field, or an empty one before a
            # `chunked`, is still a Transfer-Encoding and still refused.
            if self.headers.get_all("Transfer-Encoding") is not None:
                self._refuse(
                    exchange, 411, "length_required", "requests must carry a content-length"
                )
                return
            lengths = self.headers.get_all("Content-Length") or []
            if len(lengths) != 1:
                code = "missing_content_length" if not lengths else "duplicate_content_length"
                self._refuse(
                    exchange, 400, code, "requests must carry exactly one content-length"
                )
                return
            raw_length = lengths[0].strip()
            if raw_length.startswith("-") and raw_length[1:].isdigit():
                self._refuse(
                    exchange, 400, "bad_content_length", "content-length must not be negative"
                )
                return
            if not re.fullmatch(r"[0-9]{1,20}", raw_length):
                self._refuse(
                    exchange, 400, "bad_content_length", "content-length must be a whole number"
                )
                return
            length = int(raw_length)
            if length > REQUEST_MAX_BYTES:
                self._refuse(
                    exchange,
                    413,
                    "body_too_large",
                    f"request body must be at most {REQUEST_MAX_BYTES} bytes",
                )
                return
            if now() >= exchange.deadlines.latest_start:
                self._refuse(
                    exchange,
                    503,
                    "deadline_insufficient",
                    "too little of this request's time is left to reach the upstream",
                )
                return

            # A slot before the body, so the bodies held at once are bounded by
            # the slots, each at most REQUEST_MAX_BYTES.
            if not self._wait(exchange, self._take_slots):
                self._refuse(exchange, 429, "inflight", refusal_message(Refused("inflight", None)))
                return
            exchange.slots = True

            body = self._read_body(exchange, length)
            if body is None:
                return

            marker = REFUSE_DIR / f"refuse-{state.slug}.marker"
            if marker.exists():
                self._refuse(
                    exchange,
                    503,
                    "refused_by_operator",
                    "this socket is refusing every request: an operator marker is in "
                    f"place ({marker.name})",
                )
                return

            # Structure before any json.loads: a linear count, no parsing.
            scan = prescan(body, REQUEST_CAPS)
            if scan.exceeded:
                self._refuse(
                    exchange,
                    400,
                    "structure_limit",
                    f"the request body exceeds the recorder's JSON {scan.exceeded} limit",
                )
                return
            # Memory for this request and its largest possible response, before parsing.
            need = memory_for_request(len(body), scan.values) + memory_for_response()
            pool = MEMORY
            if not self._wait(exchange, lambda timeout: pool.reserve(need, timeout)):
                self._refuse(
                    exchange,
                    429,
                    "memory",
                    "the recorder has no memory free for this request; try again shortly",
                )
                return
            exchange.memory, exchange.memory_pool = need, pool

            request = parse_request(body, streaming=upstream_supports_streaming())
            if isinstance(request, RequestRefusal):
                self._refuse(exchange, request.status, request.code, request.message)
                return
            forwarded = request.forwarded
            # The estimate is over what is actually sent: the same bytes the
            # upstream will bill for its prompt.
            exchange.estimate = max(1, len(forwarded) // 4)

            recorded = request.recorded
            messages = recorded.get("messages")
            opened = {
                "at": iso(),
                "event": "open",
                "id": exchange.rid,
                "agent": state.slug,
                "model": recorded.get("model"),
                "messages": len(messages) if isinstance(messages, list) else 0,
                "bytes_in": len(body),
                "bytes_forwarded": len(forwarded),
                "estimate": exchange.estimate,
                "transformed": request.transformed,
            }
            if request.duplicate_keys:
                opened["duplicate_keys"] = True
            if request.label is not None:
                opened["client_label"] = request.label
                if state.label_seen_before(request.label):
                    opened["label_seen_before"] = True
            elif request.label_invalid is not None:
                opened["client_label_invalid"] = request.label_invalid

            # Custody before spend: a prediction that the record has room, then
            # a readable `open`. Neither failure admits or contacts anything.
            available = free_bytes(TRANSCRIPTS_DIR)
            if available is None:
                self._refuse(
                    exchange,
                    503,
                    "record_unavailable",
                    "the recorder cannot check the space for its record",
                )
                return
            if available < MIN_FREE_BYTES:
                self._refuse(
                    exchange,
                    503,
                    "record_capacity",
                    "the recorder's record is nearly out of space; nothing was sent",
                )
                return
            opened_result = append_with_custody(state.store, state.events, opened)
            if not opened_result.readable:
                log(f"{state.slug}: {exchange.rid}: open not recorded: {opened_result.status}")
                self._refuse(
                    exchange,
                    503,
                    "record_unavailable",
                    "the recorder could not record this request; nothing was sent",
                )
                return

            # The forward check: the open and the preflight are filesystem calls
            # no deadline can interrupt, so the time left is looked at again
            # before anything is admitted or contacted.
            if now() > exchange.deadlines.latest_start:
                self._refuse(
                    exchange,
                    503,
                    "deadline_insufficient",
                    "too little of this request's time is left to reach the upstream",
                )
                return

            # Reserve against the ceilings before spending anything upstream.
            decision = budget.admit(exchange.rid, state.slug, exchange.estimate)
            if isinstance(decision, Refused):
                self._refuse(exchange, 429, decision.reason, refusal_message(decision))
                return
            exchange.admitted = True

            # The substitution. Nothing the agent sent as a header is copied:
            # the outbound set is built fresh, and never written to the record.
            headers = outbound_headers(self.headers, upstream_key(), forward_header_names())

            upstream = Upstream(exchange.deadlines.upstream_abs, exchange.rid)
            try:
                try:
                    upstream.connect()
                except Exception as error:  # noqa: BLE001 -- reported to the client as 502
                    # Nothing was sent: the reservation is cancelled and refunded.
                    self._account(exchange, Usage(UNKNOWN))
                    log(f"{state.slug}: {exchange.rid}: upstream connect failed: {type(error).__name__}")
                    self._refuse(
                        exchange,
                        502,
                        "upstream_connect",
                        f"the recorder could not connect to the upstream ({type(error).__name__})",
                    )
                    return
                try:
                    if not budget.begin_forward(exchange.rid):
                        self._refuse(
                            exchange, 503, "shutting_down", "the recorder is not forwarding requests"
                        )
                        return
                    reply = upstream.exchange(headers, forwarded)
                except Exception as error:  # noqa: BLE001 -- reported to the client as 502
                    # Bytes may have reached the provider: the estimate stays charged.
                    self._account(exchange, Usage(UNKNOWN))
                    if upstream.deadline_fired:
                        message = "the upstream did not finish before the recorder's deadline"
                    else:
                        message = f"the recorder could not reach the upstream ({type(error).__name__})"
                    log(f"{state.slug}: {exchange.rid}: upstream failure: {type(error).__name__}")
                    self._refuse(exchange, 502, "upstream_transport", message)
                    return
            finally:
                upstream.close()

            status, response_headers, payload, truncated = reply
            exchange.custody_from = now()
            exchange.upstream_status = status
            view = view_response(payload, truncated)
            exchange.usage = view.usage
            # Settle before the transcript and the relay, so the accounting is
            # right even when both of those fail.
            self._account(exchange, exchange.usage)
            exchange.status = status
            exchange.outcome = "ok" if 200 <= status < 300 else "upstream_http"

            transcript = {
                "at": iso(),
                "agent": state.slug,
                "id": exchange.rid,
                "request": recorded,
                "response": view.data,
                "status": status,
                "usage": view.usage.raw,
                "usage_class": view.usage.cls,
            }
            if view.structure_limit:
                transcript["structure_limit"] = True
            exchange.recorded = append_with_custody(state.store, state.transcript, transcript)
            if not exchange.recorded.readable:
                # Record before relay: an answer with no readable record is
                # withheld. It was paid for; the accounting above says so.
                log(f"{state.slug}: {exchange.rid}: transcript not recorded: {exchange.recorded.status}")
                self._refuse(
                    exchange,
                    502,
                    "record_failed",
                    "the recorder could not record the response, so it was withheld",
                )
                return
            if view.cap_exceeded:
                # The kept prefix is recorded; the answer itself is not relayed.
                self._refuse(
                    exchange,
                    502,
                    "response_cap_exceeded",
                    f"the upstream response exceeded {MAX_RESPONSE} bytes; it was recorded in part "
                    "and not relayed",
                )
                return
            out_headers = {
                name: value
                for name, value in response_headers.items()
                if name.lower() not in FRAMING
            }
            exchange.responded = True
            exchange.relayed = self._relay(exchange, status, out_headers, payload)

    return Handler


def request_path(url: str) -> str:
    target = urlsplit(url)
    path = target.path or "/"
    if target.query:
        path += "?" + target.query
    return path


# ---------------------------------------------------------------------------
# What goes upstream
# ---------------------------------------------------------------------------
# The outbound headers are built fresh for every request by one function, for
# the unix-socket and network paths alike, and never copied from the inbound
# request: whatever the agent sent as a key, a cookie or a marker stays here.
# http.client adds Host, Content-Length and Accept-Encoding: identity. With no
# key configured, no Authorization header is sent at all.
#
# Stated narrowly: the configured key is read at send time and placed only in
# the outbound request, so the authorized upstream necessarily receives it.
# The recorder never serializes a request header into the record. A response
# body can reflect anything, headers included, and that is outside this claim.
USER_AGENT = "space-chassis-recorder/0.2"
ACCEPT_VALUES = ("application/json", "text/event-stream", "*/*")
FORWARD_HEADER_PATTERN = re.compile(r"X-[A-Za-z0-9-]{1,40}", re.IGNORECASE)
DENIED_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "openai-organization",
        "openai-project",
    }
)
MAX_FORWARD_VALUE_BYTES = 256
PRINTABLE_ASCII = re.compile(r"[\x20-\x7e]*")


def forward_header_names() -> tuple[str, ...]:
    """RECORDER_FORWARD_HEADERS: extra X- headers an operator chose to pass on.

    Empty by default. A name is kept only if it is an X- name of at most forty
    characters and not a credential's name; anything else is ignored. Header
    names ignore case, so two spellings of one name are one name: the first
    spelling is kept.
    """
    names: dict[str, str] = {}
    for item in (os.environ.get("RECORDER_FORWARD_HEADERS") or "").split(","):
        name = item.strip()
        if FORWARD_HEADER_PATTERN.fullmatch(name) and name.lower() not in DENIED_HEADERS:
            names.setdefault(name.lower(), name)
    return tuple(names.values())


def outbound_headers(inbound, key: str, extra: tuple[str, ...] = ()) -> dict[str, str]:
    """The headers sent upstream; `inbound` is the request's header message.

    Accept is passed on only as one of three exact values; an allowlisted X-
    header only when it appears once with a printable value of at most 256
    bytes. Every comparison ignores case.
    """
    accept = "application/json"
    values = inbound.get_all("Accept") or []
    if len(values) == 1 and values[0].strip().lower() in ACCEPT_VALUES:
        accept = values[0].strip().lower()
    headers = {
        "Content-Type": "application/json",
        "Accept": accept,
        "User-Agent": USER_AGENT,
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"
    sent = {name.lower() for name in headers}
    for name in extra:
        if name.lower() in DENIED_HEADERS or not FORWARD_HEADER_PATTERN.fullmatch(name):
            continue
        if name.lower() in sent:
            continue
        sent.add(name.lower())
        values = inbound.get_all(name) or []
        if len(values) != 1:
            continue
        value = values[0]
        if PRINTABLE_ASCII.fullmatch(value) and len(value) <= MAX_FORWARD_VALUE_BYTES:
            headers[name] = value
    return headers


# Name resolution and socket creation for the network path, looked up at call
# time so a test can supply an immediate resolver and socket doubles.
RESOLVE = socket.getaddrinfo
NEW_SOCKET = socket.socket


class WatchedConnection:
    """A connection whose every socket is owned and watched before it blocks.

    The owner (`Upstream`) supplies three callbacks: `on_socket` registers or
    rebinds the socket with the watchdog, `on_release` cancels that entry and
    then closes the socket, and `time_left` gives the seconds left in the
    upstream phase (raising once there are none). A deadline can then shut
    down whatever the connection is blocked in: a unix-socket connect, each
    TCP connect attempt, a TLS handshake, the send, the status line, the body.

    TCP is connected here rather than by `socket.create_connection`, which
    would reuse one timeout for every resolved address with no socket to
    watch until it returned: an attempt that began before the deadline
    could be followed by a fresh one after it. Here each address gets its
    own watched socket and only the time left; once none is left no further
    attempt begins. Name resolution runs once, first, and cannot be
    interrupted -- no socket exists yet [X].
    """

    on_socket = None
    on_release = None
    time_left = None

    def _tell(self, sock) -> None:
        if self.on_socket is not None:
            self.on_socket(sock)

    def _release(self, sock) -> None:
        if self.on_release is not None:
            self.on_release(sock)
        else:
            with contextlib.suppress(OSError):
                sock.close()

    def _attempt_timeout(self) -> float:
        if self.time_left is None:
            return self.timeout
        return max(0.001, min(TIMING.io_timeout, self.time_left()))

    def _tcp_connect(self) -> None:
        addresses = RESOLVE(self.host, self.port, 0, socket.SOCK_STREAM)
        failure: OSError | None = None
        for family, kind, proto, _canonical, address in addresses:
            timeout = self._attempt_timeout()  # raises once the phase has no time left
            sock = NEW_SOCKET(family, kind, proto)
            self.sock = sock
            self._tell(sock)  # watched before it can block
            try:
                sock.settimeout(timeout)
                sock.connect(address)
            except OSError as error:
                failure = error
                self.sock = None
                self._release(sock)  # its watch is cancelled before it is closed
                continue
            with contextlib.suppress(OSError):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            return
        if failure is not None:
            raise failure
        raise OSError("the upstream name resolved to no address")


class UnixHTTPConnection(WatchedConnection, http.client.HTTPConnection):
    """http.client over a unix socket: an upstream that needs no port."""

    def __init__(self, socket_path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # Owned by the connection from here: a watching owner cancels its
        # deadline and then closes it through close(), never the other way round.
        self.sock = sock
        try:
            self._tell(sock)
            sock.settimeout(self.timeout)
            sock.connect(self.socket_path)
        except BaseException:
            if self.on_socket is None:
                self.sock = None
                sock.close()
            raise


class TCPHTTPConnection(WatchedConnection, http.client.HTTPConnection):
    def connect(self) -> None:
        self._tcp_connect()


class TLSHTTPConnection(WatchedConnection, http.client.HTTPSConnection):
    """HTTPS over the same watched TCP attempts, with the handshake watched too.

    The wrapped socket replaces the raw one in the watch before the handshake
    starts; the context is the standard library's verified default, and the
    host name is both the SNI and the name the certificate must match.
    """

    def connect(self) -> None:
        self._tcp_connect()
        wrapped = self._context.wrap_socket(
            self.sock, server_hostname=self.host, do_handshake_on_connect=False
        )
        self.sock = wrapped
        self._tell(wrapped)  # rebind ownership before the handshake can block
        wrapped.settimeout(self._attempt_timeout())
        wrapped.do_handshake()


def upstream_connection() -> http.client.HTTPConnection:
    """An unconnected connection to the upstream: UPSTREAM_SOCKET, else LLM_BASE_URL.

    HTTPS uses the standard library's verified defaults -- certificate and
    host name both checked. Environment proxy variables are not consulted.
    """
    timeout = TIMING.io_timeout
    if UPSTREAM_SOCKET:
        return UnixHTTPConnection(UPSTREAM_SOCKET, timeout)
    target = urlsplit(upstream_url())
    if target.scheme == "https":
        return TLSHTTPConnection(
            target.hostname, target.port, timeout=timeout, context=ssl.create_default_context()
        )
    if target.scheme == "http":
        return TCPHTTPConnection(target.hostname, target.port, timeout=timeout)
    raise ValueError("the upstream URL must be http or https")


def host_header(connection: http.client.HTTPConnection) -> str:
    """Host as http.client would send it: the port only when it is not the default."""
    try:
        host = connection.host.encode("ascii").decode("ascii")
    except UnicodeEncodeError:
        host = connection.host.encode("idna").decode("ascii")
    if ":" in host:
        host = f"[{host}]"
    if connection.port == connection.default_port:
        return host
    return f"{host}:{connection.port}"


class UpstreamDeadline(TimeoutError):
    """The upstream phase reached its absolute deadline."""


class Upstream:
    """One HTTP exchange, connected before anything is sent, inside one deadline.

    Connecting is a separate step because it decides the accounting: a connect
    that fails (including a TLS handshake) has sent no request, so the
    reservation is refunded; once bytes may have left, the estimate stays
    charged whatever happens. `auto_open` is off and the request is sent by an
    explicit loop on the connected socket, so nothing can reconnect behind
    that decision: an exchange without a live connection fails instead.

    The whole phase -- connect, handshake, send, status line, headers, body --
    ends at the request's absolute upstream deadline: each socket operation
    gets the per-operation timeout or the time left, whichever is smaller, and
    the watchdog shuts the socket both ways at the deadline. The body is read
    up to MAX_RESPONSE bytes plus one byte of lookahead, chunked or not; more
    than that is reported as truncated, never read on.
    """

    def __init__(self, deadline: float | None = None, rid: str | None = None) -> None:
        self.deadline = now() + TIMING.upstream_offset if deadline is None else deadline
        self.rid = rid
        self.connection: http.client.HTTPConnection | None = None
        self.entry: WatchEntry | None = None
        self.fired = False  # a released attempt's watch had fired

    @property
    def deadline_fired(self) -> bool:
        return self.fired or (self.entry is not None and self.entry.fired)

    def _watch(self, sock) -> None:
        """Watch a new socket, or move the watch onto the socket that replaced it."""
        if self.entry is None:
            self.entry = WATCHDOG.register(sock, self.deadline, self.rid, "upstream", SHUT_ALL)
        else:
            WATCHDOG.rebind(self.entry, sock)

    def _release(self, sock) -> None:
        """A failed attempt: end its watch first, then close it."""
        if WATCHDOG.cancel(self.entry):
            self.fired = True
        self.entry = None
        with contextlib.suppress(OSError):
            sock.close()

    def _time_left(self) -> float:
        remaining = self.deadline - now()
        if remaining <= 0 or self.deadline_fired:
            raise UpstreamDeadline("the upstream deadline has passed")
        return remaining

    def _arm(self, sock) -> None:
        sock.settimeout(max(0.001, min(TIMING.io_timeout, self._time_left())))

    def connect(self) -> None:
        connection = upstream_connection()
        connection.auto_open = 0
        connection.timeout = max(0.001, min(TIMING.io_timeout, self._time_left()))
        connection.on_socket = self._watch
        connection.on_release = self._release
        connection.time_left = self._time_left
        self.connection = connection
        connection.connect()
        # Resolution and the connect may have used the time up: checked again
        # here, so no request byte is ever sent after the deadline.
        self._time_left()

    def exchange(self, headers: dict, body: bytes) -> tuple[int, dict, bytes, bool]:
        connection = self.connection
        if connection is None or connection.sock is None:
            raise http.client.NotConnected("no upstream connection was made before sending")
        sock = connection.sock
        lines = [f"POST {request_path(upstream_url())} HTTP/1.1", f"Host: {host_header(connection)}",
                 "Accept-Encoding: identity"]
        for name, value in headers.items():
            if any(ch in f"{name}{value}" for ch in "\r\n\0"):
                raise ValueError("an outbound header contains a line break")
            lines.append(f"{name}: {value}")
        lines.append(f"Content-Length: {len(body)}")
        view = memoryview("\r\n".join(lines).encode("latin-1") + b"\r\n\r\n" + body)
        while view:
            self._arm(sock)
            sent = sock.send(view)
            view = view[sent:]
        response = http.client.HTTPResponse(sock, method="POST")
        try:
            self._arm(sock)
            response.begin()
            status, response_headers = response.status, dict(response.getheaders())
            limit = MAX_RESPONSE + 1
            parts: list[bytes] = []
            got = 0
            while got < limit:
                self._arm(sock)
                chunk = response.read1(min(65536, limit - got))
                if not chunk:
                    break
                parts.append(chunk)
                got += len(chunk)
            if got <= MAX_RESPONSE and response.length:
                raise http.client.IncompleteRead(b"", response.length)
        finally:
            response.close()
        if self.deadline_fired:
            # A shut socket reads as an end of body: only the flag can tell.
            raise UpstreamDeadline("the upstream deadline passed while reading")
        payload = b"".join(parts)
        truncated = len(payload) > MAX_RESPONSE
        return status, response_headers, payload[:MAX_RESPONSE], truncated

    def close(self) -> None:
        # The watchdog entry is released before the socket is closed: a
        # deadline can then never reach a descriptor number already reused.
        WATCHDOG.cancel(self.entry)
        if self.connection is not None:
            with contextlib.suppress(OSError):
                self.connection.close()


def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def extract_usage(response) -> Usage:
    """What a decoded JSON response says it cost, if it says so in whole numbers.

    `total_tokens` when it is a non-negative integer (a boolean is not one);
    otherwise prompt plus completion when both are; otherwise unknown, and the
    estimate stands. The raw dict is kept either way for the record.
    """
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return Usage(UNKNOWN)
    total = usage.get("total_tokens")
    if _is_count(total):
        return Usage(KNOWN, total, usage)
    prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if _is_count(prompt) and _is_count(completion):
        return Usage(KNOWN, prompt + completion, usage)
    return Usage(UNKNOWN, None, usage)


def _nonfinite_marker(literal: str) -> dict:
    return {"__nonfinite__": literal}


def _float_or_marker(text: str):
    value = float(text)
    return value if math.isfinite(value) else {"__nonfinite__": text}


def decode_payload(payload: bytes):
    """Decode an upstream body for the record, keeping an unreadable one as text.

    The record's job is fidelity, not prettiness: a body that is not JSON is
    stored as what it was, marked truncated, rather than dropped. A NaN or
    Infinity literal, or a number that overflows to one, is kept as
    `{"__nonfinite__": "<literal>"}` so the record line stays strict JSON
    (SV-013 section 2.1.7's rule, taken here only because the custody
    serializer refuses non-finite numbers). JSON the parser will not hold
    (nesting or digit limits) is kept as text.
    """
    if not payload:
        return None
    try:
        return json.loads(
            payload.decode("utf-8"),
            parse_constant=_nonfinite_marker,
            parse_float=_float_or_marker,
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        text = payload.decode("utf-8", "ignore")
        record = {"raw_body": text[:1_000_000]}
        if len(text) > 1_000_000:
            record["raw_body_truncated"] = True
        return record


ANNOUNCE_DIR = Path(os.environ.get("ANNOUNCE_DIR", "/work/.fleet"))


def discover_slugs() -> list[str]:
    """Which agents to serve, from the announcements they left.

    A list in the environment would have to repeat the fleet's random names, and
    a rename would silently desynchronise the two. Instead each agent writes its
    own name into a directory both sides share, and the recorder serves whatever
    it finds -- so the name is stated once, by the agent that owns it.

    A `*.sock` already sitting in the socket directory is served too, which is
    how a deployment that creates them itself is picked up. AGENT_SLUGS is
    honoured when set, which is what the endurance harness uses.
    """
    configured = slugs_from_env("AGENT_SLUGS")
    if configured:
        return configured
    found = {path.stem for path in ANNOUNCE_DIR.glob("*.agent")} if ANNOUNCE_DIR.is_dir() else set()
    if SOCKET_DIR.is_dir():
        found |= {path.stem for path in SOCKET_DIR.glob("*.sock")}
    return sorted(found)


def main() -> int:
    """Serve one socket per agent, discovering them as they announce themselves.

    The fleet may not have started yet: compose brings the recorder up first and
    an agent announces itself whenever it gets there. So the set of listeners is
    something that grows, not something decided at startup.

    Each agent's socket is swept before it is bound. A bound socket file with no
    listener behind it stalls every client that connects to it, which is what a
    previous incarnation of this process leaves behind -- and only this
    recorder's own sockets are swept, because a second recorder may be serving
    other agents in the same directory.
    """
    if not TRANSCRIPTS_DIR.is_dir():
        # The record's root is the deployment's: created and made durable on the
        # host. A root this process created could vanish with its parent.
        print(
            f"[recorder] refusing to start: the transcript directory {TRANSCRIPTS_DIR} "
            "does not exist, and the recorder does not create it",
            file=sys.stderr,
            flush=True,
        )
        return 1
    problems = timing_problems(TIMING)
    if problems:
        # A profile that cannot keep its own deadline promise is refused
        # rather than run: the client would give up before the recorder does.
        print(
            "[recorder] refusing to start: inconsistent deadline profile: " + "; ".join(problems),
            file=sys.stderr,
            flush=True,
        )
        return 1
    shared = Budget(env_int("RECORDER_TOKEN_GLOBAL_HOURLY_MAX", 20_000_000))
    # Every allowance starts empty in a new process; this line is how a reader
    # tells one boot's request ids from the next. It is never written into an
    # agent's events, and no `close` is ever written for a previous boot.
    record_diagnostic({"event": "recorder_start", "boot": BOOT, "pid": os.getpid()})
    SOCKET_DIR.mkdir(parents=True, exist_ok=True)
    configured = slugs_from_env("AGENT_SLUGS")
    recorders: dict[str, Recorder] = {}
    refusals_reported: set[str] = set()
    waiting_reported = False
    while True:
        wanted = configured or discover_slugs()
        for slug in wanted:
            if slug in recorders:
                continue
            reason = None
            if not SLUG_PATTERN.fullmatch(slug):
                reason = "slug_pattern"
            elif not shared.register(
                slug,
                env_int("RECORDER_HOURLY_MAX", 1200),
                env_int("RECORDER_TOKEN_HOURLY_MAX", 4_000_000),
            ):
                reason = "max_slugs"
            if reason is not None:
                # Reported once per reason, and without the name: a name an
                # agent announced is not something to copy into the record.
                if reason not in refusals_reported:
                    refusals_reported.add(reason)
                    record_diagnostic({"event": "slug_refused", "reason": reason})
                    log(f"not serving an announced agent: {reason}")
                continue
            with contextlib.suppress(OSError):
                (SOCKET_DIR / f"{slug}.sock").unlink()
            recorder = Recorder(AgentState(slug, TRANSCRIPTS_DIR), shared, "")
            recorders[slug] = recorder
            recorder.start()
            log(f"serving {slug} on {recorder.socket_path} ({len(recorders)} now)")
        if not wanted and not waiting_reported:
            print(
                "[recorder] waiting for an agent to announce itself: nothing in "
                f"{ANNOUNCE_DIR} and no *.sock in {SOCKET_DIR}.",
                file=sys.stderr,
                flush=True,
            )
            waiting_reported = True
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
