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
import json
import os
import socket
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path

SERVICES_DIR = Path(os.environ.get("SERVICES_DIR", "/opt/services"))
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))

from common import (  # noqa: E402
    append_jsonl,
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

HOP_BY_HOP = {"host", "content-length", "connection", "accept-encoding", "transfer-encoding"}
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


class Allowance:
    """A rolling-window counter, in memory only.

    Deliberately not persisted: a restart of the recorder granting a fresh hour
    to a fleet that has been hammering it is a smaller problem than a stale
    window surviving a deploy. The ceiling that actually matters is the
    upstream key's own balance.
    """

    def __init__(self, limit: int, window: int = WINDOW_SECONDS) -> None:
        self.limit = limit
        self.window = window
        self._events: list[tuple[float, int]] = []
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        self._events = [event for event in self._events if event[0] >= cutoff]

    def check(self, tokens: int = 0) -> tuple[bool, int]:
        """Would `tokens` more fit? Returns (allowed, seconds until room).

        A limit of zero or less means the pool is closed, and that is answered
        before anything else looks at the window: an empty event list has no
        oldest stamp, and asking for one is how a switched-off pool becomes a
        crash instead of a refusal.
        """
        if self.limit <= 0:
            return False, 0
        now = time.time()
        with self._lock:
            self._prune(now)
            if not self._events:
                return True, 0
            used = sum(amount for _, amount in self._events)
            oldest = min(stamp for stamp, _ in self._events)
            if len(self._events) >= self.limit:
                return False, max(0, int(self.window - (now - oldest)) + 1)
            if tokens and used + tokens > self.limit:
                return False, max(0, int(self.window - (now - oldest)) + 1)
            return True, 0

    def charge(self, tokens: int = 0) -> None:
        with self._lock:
            now = time.time()
            self._prune(now)
            self._events.append((now, tokens))


class AgentState:
    """Per-agent bookkeeping: its allowance, and where its record goes."""

    def __init__(self, slug: str, transcript_dir: Path) -> None:
        self.slug = slug
        self.dir = transcript_dir / slug
        self.dir.mkdir(parents=True, exist_ok=True)
        self.transcript = self.dir / "agent_life_transcript.jsonl"
        self.events = self.dir / "events.jsonl"
        self.requests = Allowance(env_int("RECORDER_HOURLY_MAX", 1200))
        self.per_agent_tokens = Allowance(env_int("RECORDER_TOKEN_HOURLY_MAX", 4_000_000))


class SharedTokens:
    """One token pool over the whole fleet, on the clock hour.

    A fleet of ten can multiply any per-agent allowance by ten; this is the
    ceiling that does not scale with the number of agents. It empties at the
    top of the hour rather than rolling, so the fleet can plan around it.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._hour = int(time.time() // WINDOW_SECONDS)
        self._used = 0
        self._lock = threading.Lock()

    def check(self, tokens: int) -> tuple[bool, int]:
        with self._lock:
            hour = int(time.time() // WINDOW_SECONDS)
            if hour != self._hour:
                self._hour, self._used = hour, 0
            if self.limit <= 0 or self._used + tokens <= self.limit:
                return True, 0
            remaining = int(WINDOW_SECONDS - (time.time() % WINDOW_SECONDS)) + 1
            return False, remaining

    def charge(self, tokens: int) -> None:
        with self._lock:
            self._used += tokens


class Recorder(threading.Thread):
    """One listener, on one agent's socket, in its own thread."""

    def __init__(self, state: AgentState, shared: SharedTokens, expected_key: str) -> None:
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
    print(f"{iso()} [recorder] {message}", flush=True)


def make_handler(recorder: Recorder):
    state = recorder.state
    shared = recorder.shared

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "space-chassis-recorder/0.1"

        def log_message(self, fmt, *args):  # noqa: A003 -- base class signature
            pass

        def _send(
            self, status: int, payload: bytes, content_type: str = "application/json"
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(payload)

        def _refuse(self, status: int, message: str, request_id: str | None = None) -> None:
            body = json.dumps({"error": {"message": message, "type": "recorder"}}).encode()
            self.close_connection = True
            self._send(status, body)
            with contextlib.suppress(OSError):
                append_jsonl(
                    state.events,
                    {
                        "at": iso(),
                        "event": "close",
                        "id": request_id,
                        "agent": state.slug,
                        "status": status,
                        "refusal": message,
                    },
                )

        def do_GET(self):  # noqa: N802 -- base class API
            self._refuse(405, "this socket accepts POST /api/v1/chat/completions only")

        def do_POST(self):  # noqa: N802 -- base class API
            started = time.monotonic()
            path = self.path.split("?", 1)[0]
            if not path.endswith(ROUTE_SUFFIX):
                self._refuse(
                    404,
                    f"no route {self.path!r}; this socket serves a chat-completions "
                    f"endpoint, most simply at {ROUTE}",
                )
                return
            transfer = self.headers.get("Transfer-Encoding")
            if transfer:
                self._refuse(411, "requests must carry a content-length")
                return
            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length or "")
            except ValueError:
                self._refuse(400, "content-length must be a whole number")
                return
            if length < 0:
                self._refuse(400, "content-length must not be negative")
                return
            if length > REQUEST_MAX_BYTES:
                self._refuse(413, f"request body must be at most {REQUEST_MAX_BYTES} bytes")
                return
            body = self.rfile.read(length)

            marker = REFUSE_DIR / f"refuse-{state.slug}.marker"
            if marker.exists():
                request_id = os.urandom(8).hex()
                self._refuse(
                    503,
                    "this socket is refusing every request: an operator marker is in "
                    f"place ({marker.name})",
                    request_id,
                )
                return

            request_id = os.urandom(8).hex()
            try:
                parsed = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = {"raw_body": body.decode("utf-8", "ignore")[:2000]}

            model = parsed.get("model") if isinstance(parsed, dict) else None
            messages = parsed.get("messages") if isinstance(parsed, dict) else None
            append_jsonl(
                state.events,
                {
                    "at": iso(),
                    "event": "open",
                    "id": request_id,
                    "agent": state.slug,
                    "model": model,
                    "messages": len(messages) if isinstance(messages, list) else 0,
                },
            )

            # Reserve against the ceilings before spending anything upstream.
            estimate = max(1, len(body) // 4)
            allowed, wait = state.requests.check()
            if not allowed:
                self._refuse(
                    429,
                    f"rate limited: at most {state.requests.limit} request(s) per hour on this "
                    f"socket; next available in {wait} second(s)",
                    request_id,
                )
                return
            allowed, wait = state.per_agent_tokens.check(estimate)
            if not allowed:
                self._refuse(
                    429,
                    f"rate limited: at most {state.per_agent_tokens.limit} token(s) per hour on "
                    f"this socket; next available in {wait} second(s)",
                    request_id,
                )
                return
            allowed, wait = shared.check(estimate)
            if not allowed:
                self._refuse(
                    429,
                    f"rate limited: at most {shared.limit} token(s) per hour across the fleet; "
                    f"next available in {wait} second(s)",
                    request_id,
                )
                return
            state.requests.charge()
            state.per_agent_tokens.charge(estimate)
            shared.charge(estimate)

            if not upstream_supports_streaming():
                # Drop the streaming request rather than let it garble the
                # record. A streaming *response* from the upstream is relayed as
                # it arrives; this only governs what is asked for.
                try:
                    asked = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    asked = None
                if isinstance(asked, dict) and asked.pop("stream", None) is not None:
                    asked.pop("stream_options", None)
                    body = json.dumps(asked).encode("utf-8")

            headers = {}
            for name, value in self.headers.items():
                if name.lower() in HOP_BY_HOP:
                    continue
                headers[name] = value
            # The substitution. Anything the agent sent as a key is discarded
            # here and never appears in a transcript.
            key = upstream_key()
            if key:
                headers["Authorization"] = f"Bearer {key}"

            status, response_headers, payload = 0, {}, b""
            try:
                if UPSTREAM_SOCKET:
                    status, response_headers, payload = send_over_unix(
                        UPSTREAM_SOCKET, upstream_url(), headers, body
                    )
                else:
                    request = urllib.request.Request(
                        upstream_url(), data=body, headers=headers, method="POST"
                    )
                    with urllib.request.urlopen(request, timeout=UPSTREAM_TIMEOUT) as response:
                        status = response.status
                        response_headers = dict(response.headers.items())
                        payload = response.read()
            except urllib.error.HTTPError as error:
                status = error.code
                response_headers = dict(error.headers.items()) if error.headers else {}
                payload = error.read() if error.fp else b""
            except Exception as error:  # noqa: BLE001 -- reported to the client as 502
                log(f"{state.slug}: upstream failure: {type(error).__name__}: {error}")
                self._refuse(502, f"the recorder could not reach the upstream: {error}", request_id)
                self._settle(request_id, started, None, 0)
                return

            response_data = decode_payload(payload)
            append_jsonl(
                state.transcript,
                {
                    "at": iso(),
                    "agent": state.slug,
                    "id": request_id,
                    "request": parsed,
                    "response": response_data,
                    "status": status,
                },
            )
            usage = None
            if isinstance(response_data, dict):
                usage = response_data.get("usage")
            spent = 0
            if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
                spent = usage["total_tokens"]
                # Replace the estimate with what was actually billed.
                state.per_agent_tokens.charge(max(0, spent - estimate))
            self._settle(request_id, started, usage, status)

            out_headers = {
                name: value
                for name, value in response_headers.items()
                if name.lower() not in FRAMING
            }
            self.send_response(status)
            for name, value in out_headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(payload)

        def _settle(self, request_id: str, started: float, usage, status: int) -> None:
            append_jsonl(
                state.events,
                {
                    "at": iso(),
                    "event": "close",
                    "id": request_id,
                    "agent": state.slug,
                    "status": status,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "usage": usage if isinstance(usage, dict) else None,
                },
            )

    return Handler


def send_over_unix(
    socket_path: str, url: str, headers: dict, body: bytes
) -> tuple[int, dict, bytes]:
    """One HTTP exchange over a unix socket, hand-rolled.

    Written out rather than pulled from a library because there is very little
    to it and the framing rules are the point: the upstream may answer with a
    content-length or with chunked encoding, and a recorder that mishandled the
    second would silently truncate a streamed completion in the record.
    """
    import http.client
    from urllib.parse import urlsplit

    target = urlsplit(url)
    request_path = target.path or "/"
    if target.query:
        request_path += "?" + target.query

    connection = http.client.HTTPConnection("localhost", timeout=UPSTREAM_TIMEOUT)
    connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.sock.settimeout(UPSTREAM_TIMEOUT)
    connection.sock.connect(socket_path)
    try:
        connection.request("POST", request_path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        with contextlib.suppress(OSError):
            connection.close()


def decode_payload(payload: bytes):
    """Decode an upstream body for the record, keeping an unreadable one as text.

    The record's job is fidelity, not prettiness: a body that is not JSON is
    stored as what it was, marked truncated, rather than dropped.
    """
    if not payload:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
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
    shared = SharedTokens(env_int("RECORDER_TOKEN_GLOBAL_HOURLY_MAX", 20_000_000))
    SOCKET_DIR.mkdir(parents=True, exist_ok=True)
    configured = slugs_from_env("AGENT_SLUGS")
    recorders: dict[str, Recorder] = {}
    waiting_reported = False
    while True:
        wanted = configured or discover_slugs()
        for slug in wanted:
            if slug in recorders:
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
