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
REQUEST_MAX_BYTES = env_int("REQUEST_MAX_BYTES", 16 * 1024 * 1024)
# A directory an operator can drop `refuse-<slug>.marker` into to make one
# agent's socket fail at the front door. It exists so that "the environment is
# unusable" can be tested as a condition rather than waited for as an accident.
REFUSE_DIR = Path(os.environ.get("RECORDER_REFUSE_DIR", "/tmp"))
UPSTREAM_TIMEOUT = env_int("UPSTREAM_TIMEOUT_SECONDS", 600)
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
                return conn, ("unix", 0)

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

    def __init__(self, rid: str) -> None:
        self.rid = rid
        self.started = time.monotonic()
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

        # -- the one exit -----------------------------------------------------
        def do_GET(self):  # noqa: N802 -- base class API
            exchange = Exchange(next_rid())
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
            exchange = Exchange(next_rid())
            try:
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
                if exchange.slots:
                    exchange.slots = False
                    TOTAL_SLOTS.release()
                    state.slots.release()
                self._write_close(exchange)

        def _account(self, exchange: Exchange, usage: Usage) -> None:
            exchange.accounted = budget.close(exchange.rid, usage)
            exchange.settled_at = time.monotonic()

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
        def _relay(self, status: int, headers: dict, payload: bytes) -> bool:
            """Write one response. False if the client was no longer there."""
            try:
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except OSError:
                self.close_connection = True
                return False
            return True

        def _refuse(self, exchange: Exchange, status: int, outcome: str, message: str) -> None:
            exchange.status, exchange.outcome, exchange.refusal = status, outcome, message
            body = json.dumps(
                {"error": {"message": message, "type": "recorder", "code": outcome}}
            ).encode()
            self.close_connection = True
            exchange.responded = True
            # Whether this error reached the client is not recorded as `relayed`:
            # that field is about the upstream's response.
            self._relay(status, {"Content-Type": "application/json"}, body)

        def _take_slots(self) -> bool:
            """One of this socket's slots, then one of the fleet's, waiting a bounded time.

            The socket's own slot is taken first so a busy socket waits on itself
            without holding fleet capacity while it does. If taking the second
            fails in any way -- a timeout or a raise -- the first is given back
            here, because the caller only owns the pair once this returns True.
            """
            deadline = time.monotonic() + INFLIGHT_WAIT_SECONDS
            if not state.slots.acquire(timeout=INFLIGHT_WAIT_SECONDS):
                return False
            taken = False
            try:
                taken = TOTAL_SLOTS.acquire(timeout=max(0.0, deadline - time.monotonic()))
            finally:
                if not taken:
                    state.slots.release()
            return taken

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
            body = self.rfile.read(length)
            if len(body) < length:
                # The client stopped early. Nothing partial is ever forwarded.
                self._refuse(
                    exchange,
                    400,
                    "short_body",
                    f"the request body ended after {len(body)} of {length} bytes",
                )
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

            request = parse_request(body, streaming=upstream_supports_streaming())
            if isinstance(request, RequestRefusal):
                self._refuse(exchange, request.status, request.code, request.message)
                return
            forwarded = request.forwarded
            # The estimate is over what is actually sent: the same bytes the
            # upstream will bill for its prompt.
            exchange.estimate = max(1, len(forwarded) // 4)

            if not self._take_slots():
                self._refuse(exchange, 429, "inflight", refusal_message(Refused("inflight", None)))
                return
            exchange.slots = True

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

            # Reserve against the ceilings before spending anything upstream.
            decision = budget.admit(exchange.rid, state.slug, exchange.estimate)
            if isinstance(decision, Refused):
                self._refuse(exchange, 429, decision.reason, refusal_message(decision))
                return
            exchange.admitted = True

            # The substitution. Nothing the agent sent as a header is copied:
            # the outbound set is built fresh, and never written to the record.
            headers = outbound_headers(self.headers, upstream_key(), forward_header_names())

            upstream = Upstream()
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
                status, response_headers, payload = upstream.exchange(headers, forwarded)
            except Exception as error:  # noqa: BLE001 -- reported to the client as 502
                # Bytes may have reached the provider: the estimate stays charged.
                self._account(exchange, Usage(UNKNOWN))
                log(f"{state.slug}: {exchange.rid}: upstream failure: {type(error).__name__}")
                self._refuse(
                    exchange,
                    502,
                    "upstream_transport",
                    f"the recorder could not reach the upstream ({type(error).__name__})",
                )
                return
            finally:
                upstream.close()

            exchange.upstream_status = status
            response_data = decode_payload(payload)
            exchange.usage = extract_usage(response_data)
            # Settle before the transcript and the relay, so the accounting is
            # right even when both of those fail.
            self._account(exchange, exchange.usage)
            exchange.status = status
            exchange.outcome = "ok" if 200 <= status < 300 else "upstream_http"

            exchange.recorded = append_with_custody(
                state.store,
                state.transcript,
                {
                    "at": iso(),
                    "agent": state.slug,
                    "id": exchange.rid,
                    "request": recorded,
                    "response": response_data,
                    "status": status,
                },
            )
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
            out_headers = {
                name: value
                for name, value in response_headers.items()
                if name.lower() not in FRAMING
            }
            exchange.responded = True
            exchange.relayed = self._relay(status, out_headers, payload)

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


class UnixHTTPConnection(http.client.HTTPConnection):
    """http.client over a unix socket: an upstream that needs no port."""

    def __init__(self, socket_path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(self.timeout)
            sock.connect(self.socket_path)
        except BaseException:
            sock.close()
            raise
        self.sock = sock


def upstream_connection() -> http.client.HTTPConnection:
    """An unconnected connection to the upstream: UPSTREAM_SOCKET, else LLM_BASE_URL.

    HTTPS uses the standard library's verified defaults -- certificate and
    host name both checked. Environment proxy variables are not consulted.
    """
    if UPSTREAM_SOCKET:
        return UnixHTTPConnection(UPSTREAM_SOCKET, UPSTREAM_TIMEOUT)
    target = urlsplit(upstream_url())
    if target.scheme == "https":
        return http.client.HTTPSConnection(
            target.hostname,
            target.port,
            timeout=UPSTREAM_TIMEOUT,
            context=ssl.create_default_context(),
        )
    if target.scheme == "http":
        return http.client.HTTPConnection(target.hostname, target.port, timeout=UPSTREAM_TIMEOUT)
    raise ValueError("the upstream URL must be http or https")


class Upstream:
    """One HTTP exchange, connected before anything is sent.

    Connecting is a separate step because it decides the accounting: a connect
    that fails (including a TLS handshake) has sent no request, so the
    reservation is refunded; once bytes may have left, the estimate stays
    charged whatever happens. `auto_open` is off, so http.client can never
    reconnect behind that decision: an exchange without a live connection
    fails instead. The upstream may answer with a content-length or chunked;
    http.client reads both, and a recorder that mishandled the second would
    silently truncate a streamed completion in the record.
    """

    def __init__(self) -> None:
        self.connection: http.client.HTTPConnection | None = None

    def connect(self) -> None:
        connection = upstream_connection()
        connection.auto_open = 0
        try:
            connection.connect()
        except BaseException:
            connection.close()
            raise
        self.connection = connection

    def exchange(self, headers: dict, body: bytes) -> tuple[int, dict, bytes]:
        connection = self.connection
        if connection is None or connection.sock is None:
            raise http.client.NotConnected("no upstream connection was made before sending")
        connection.request("POST", request_path(upstream_url()), body=body, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()

    def close(self) -> None:
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
