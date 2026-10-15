import contextlib
import dataclasses
import functools
import gzip
import http.client
import http.server
import math
import shutil
import socket
import socketserver
import threading
import time
import urllib.request
import urllib.error
import json
import os
import sys
import datetime

import core_caps
import recorder_streams

SOCKET_PATH = os.environ.get("LLM_SOCKET_PATH", "/llm/sock/core.sock")
TRANSCRIPT_DIR = os.environ.get("TRANSCRIPT_DIR", os.path.dirname(os.path.abspath(__file__)))
TRANSCRIPT_FILE = os.path.join(TRANSCRIPT_DIR, "agent_life_transcript.jsonl")
PLAIN_TRANSCRIPT_FILE = os.path.join(TRANSCRIPT_DIR, "agent_life_transcript.txt")
TRANSCRIPT_MAX_BYTES = int(os.environ.get("TRANSCRIPT_MAX_BYTES", str(134_217_728)))
EVENTS_FILE = os.path.join(TRANSCRIPT_DIR, "events.jsonl")
EVENTS_MAX_BYTES = 16_777_216
# The recorder holds a request body whole while it forwards and records it, so
# a body is refused above this size rather than read into memory. Resource
# hygiene inside the recorder, which runs under a memory limit; not a ceiling
# on what a stream may spend.
REQUEST_MAX_BYTES = int(os.environ.get("REQUEST_MAX_BYTES", str(16_777_216)))
# A buffered upstream response is read at most this far; past it the reply is withheld (502) and
# recorded as the prefix read, its usage unknown.
RESPONSE_MAX_BYTES = int(os.environ.get("RESPONSE_MAX_BYTES", str(16_777_216)))
# Every raw body the recorder writes or prints is cut here.
RAW_RECORD_CHARS = 1_000_000
# The most of a streamed body's raw bytes the recorder keeps, for a body that
# carries no events, and the longest single event line it parses. The
# reassembled completion is held whole; the body it came from is not.
STREAM_RETAIN_BYTES = 1_048_576

_transcript_lock = threading.Lock()
_events_lock = threading.Lock()
_active_bindings = set()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
FRAMING_HEADERS = ("content-length", "transfer-encoding", "connection", "content-encoding")
RELAYED_HEADERS = ("content-type", "retry-after")
ERROR_BODY_READ_MAX = 64 * 1024
ERROR_MESSAGE_MAX = 2048
ERROR_TYPE_MAX = 256
ERROR_REASON_MAX = 64
ERROR_PLAIN_TEXT_MAX = 512
ERROR_LOG_MAX = 4096
REDIRECT_LOG_MAX = 512
REASONING_DELTA_FIELDS = ("reasoning", "reasoning_content")


def _llm_pair():
    return recorder_streams._resolve_pair(
        os.environ.get("HOST_LLM_BASE_URL"),
        os.environ.get("HOST_LLM_API_KEY"),
        os.environ.get("LLM_BASE_URL"),
        os.environ.get("LLM_API_KEY"),
        os.environ.get("OPENROUTER_API_KEY", ""),
    )


def _stream_pair():
    return recorder_streams._resolve_pair(
        os.environ.get("HOST_STREAM_BASE_URL"),
        os.environ.get("HOST_STREAM_API_KEY"),
        os.environ.get("STREAM_BASE_URL"),
        os.environ.get("STREAM_API_KEY"),
        os.environ.get("OPENROUTER_API_KEY", ""),
    )


def upstream_url():
    """Return the upstream chat-completions URL.

    When HOST_LLM_BASE_URL or LLM_BASE_URL is set (the host value first), the
    recorder forwards to that OpenAI-compatible endpoint; otherwise it
    forwards to OpenRouter.
    """
    base, _ = _llm_pair()
    if base:
        return base.rstrip("/") + "/chat/completions"
    return OPENROUTER_URL


def upstream_api_key():
    """Return the API key injected into upstream requests.

    The key resolves together with the URL. HOST_LLM_BASE_URL, when set,
    takes HOST_LLM_API_KEY (possibly empty, for no-auth local servers).
    Otherwise LLM_API_KEY applies when LLM_BASE_URL is set, and
    OPENROUTER_API_KEY when it is not.
    """
    return _llm_pair()[1]


def stream_upstream_url():
    """Return the chat-completions URL serving declared stream sockets.

    HOST_STREAM_BASE_URL or STREAM_BASE_URL (the host value first) aims
    declared streams at any OpenAI-compatible endpoint; without either they
    forward to OpenRouter. Either way the target is never inherited from the
    LLM_BASE_URL pair, which governs core.sock alone: aiming both at one
    provider is an operator decision stated twice, never a silent default.
    STREAM_UPSTREAM_URL overrides all of them for the verification harness
    and tests; leave it unset in normal operation.
    """
    override = os.environ.get("STREAM_UPSTREAM_URL", "").strip()
    if override:
        return override.rstrip("/") + "/chat/completions"
    base, _ = _stream_pair()
    if base:
        return base.rstrip("/") + "/chat/completions"
    return OPENROUTER_URL


def stream_api_key():
    """Return the API key injected into declared streams' requests.

    The key resolves together with the URL. HOST_STREAM_BASE_URL, when set,
    takes HOST_STREAM_API_KEY (possibly empty, for a no-auth local server).
    Otherwise STREAM_API_KEY applies when STREAM_BASE_URL is set, and
    OPENROUTER_API_KEY when it is not. The pair is the streams' own, so a
    declared stream never reaches core.sock's credential and never carries
    one it was not given.
    """
    return _stream_pair()[1]


def upstream_for(stream):
    """Return the (url, api_key) pair a stream's requests forward to.

    core.sock follows the configured upstream with its key; every declared
    stream follows the stream upstream with the streams' own key.
    """
    if stream == "core":
        return upstream_url(), upstream_api_key()
    return stream_upstream_url(), stream_api_key()


def build_forward_headers(headers, api_key):
    """Build the headers forwarded upstream.

    Drops hop-by-hop headers. When api_key is non-empty, overrides Authorization
    with it, so the recorder injects the real key and the agent never holds it.
    """
    hop_by_hop = {"host", "content-length", "connection", "accept-encoding"}
    forwarded = {k: v for k, v in headers.items() if k.lower() not in hop_by_hop}
    if api_key:
        forwarded["Authorization"] = f"Bearer {api_key}"
    return forwarded


def utc_timestamp():
    """The current UTC time as an ISO-8601 string with a trailing Z."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def archive_name(path, stamp=None):
    """Return the timestamped gzip archive name for a transcript path."""
    if stamp is None:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    root, ext = os.path.splitext(path)
    return f"{root}-{stamp}{ext}.gz"


# The recorder's own system calls, indirected so tests can fault them without touching the
# process-wide os module.
_os_write = os.write
_fdatasync = os.fdatasync
_fsync = os.fsync
_statvfs = os.statvfs

# The JSON transcript's append results. A line is readable when it was written whole.
READABLE = frozenset({"appended", "appended_fsync_failed", "durable"})
RECORDER_MIN_FREE_BYTES = int(os.environ.get("RECORDER_MIN_FREE_BYTES", str(64 * 1024 * 1024)))

_fenced = set()
_append_locks = {}
_append_locks_guard = threading.Lock()
_degraded_reported = False


def _fsync_directory(directory):
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        _fsync(descriptor)
    finally:
        os.close(descriptor)


def _append_lock(path):
    with _append_locks_guard:
        return _append_locks.setdefault(path, threading.Lock())


def append_record(path, line):
    """Append one line durably. Returns failed | partial | appended | appended_fsync_failed | durable.

    A torn tail left by a dead writer is repaired with a newline first, so every line starts on a
    boundary. The whole buffer goes out through short writes and EINTR. The data is synced, and on
    a path's first append in this process (and after any failure) its directory is synced too,
    with the parent when makedirs had to create it. durable means all of that returned.
    """
    with _append_lock(path):
        directory = os.path.dirname(path) or "."
        try:
            created = not os.path.isdir(directory)
            os.makedirs(directory, exist_ok=True)
            fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC, 0o644)
        except OSError:
            _fenced.discard(path)
            return "failed"
        try:
            buffer = line if line.endswith(b"\n") else line + b"\n"
            size = os.fstat(fd).st_size
            if size and os.pread(fd, 1, size - 1) != b"\n":
                buffer = b"\n" + buffer
            written = 0
            while written < len(buffer):
                try:
                    count = _os_write(fd, buffer[written:])
                except InterruptedError:
                    continue
                except OSError:
                    _fenced.discard(path)
                    return "partial" if written else "failed"
                if count == 0:
                    _fenced.discard(path)
                    return "partial" if written else "failed"
                written += count
            try:
                _fdatasync(fd)
            except OSError:
                _fenced.discard(path)
                return "appended_fsync_failed"
            if path not in _fenced:
                try:
                    _fsync_directory(directory)
                    if created:
                        _fsync_directory(os.path.dirname(os.path.abspath(directory)))
                except OSError:
                    return "appended"
                _fenced.add(path)
            return "durable"
        finally:
            os.close(fd)


def record_capacity_ok():
    """Whether the transcript volume has room for the exchange the recorder is about to pay for."""
    try:
        st = _statvfs(TRANSCRIPT_DIR)
    except OSError:
        return True
    return st.f_bavail * st.f_frsize >= RECORDER_MIN_FREE_BYTES


def rotate_if_needed(path, max_bytes=None):
    """Archive a transcript to gzip and truncate it once it reaches max_bytes.

    Returns the archive path, or None when no rotation happened. The file is
    compressed in chunks and the archive is renamed into place before the
    live file is truncated. On failure the live file is left unchanged.
    """
    if max_bytes is None:
        max_bytes = TRANSCRIPT_MAX_BYTES
    tmp = None
    try:
        if not os.path.exists(path) or os.path.getsize(path) < max_bytes:
            return None
        final = archive_name(path)
        if os.path.exists(final):
            return None
        tmp = final + ".tmp"
        with open(path, "rb") as src, gzip.open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst, 65536)
        # The archive is durable before the live file is cut: a crash between the two must not
        # lose the lines it holds.
        descriptor = os.open(tmp, os.O_RDONLY)
        try:
            _fsync(descriptor)
        finally:
            os.close(descriptor)
        os.rename(tmp, final)
        _fsync_directory(os.path.dirname(final) or ".")
        with open(path, "w", encoding="utf-8"):
            pass
        return final
    except Exception as e:
        print(f"Error rotating transcript: {e}", file=sys.stderr)
        if tmp is not None:
            try:
                os.remove(tmp)
            except Exception:
                pass
        return None


def request_id():
    """A random hex token pairing one request's open and close events."""
    return os.urandom(8).hex()


def log_event(event, stream, **fields):
    """Append one telemetry event; failures never affect the request.

    Events carry names, counts, statuses, durations, and token totals only,
    never message content or headers.
    """
    entry = {
        "timestamp": utc_timestamp(),
        "event": event,
        "stream": stream,
    }
    entry.update(fields)
    try:
        with _events_lock:
            os.makedirs(os.path.dirname(EVENTS_FILE) or ".", exist_ok=True)
            with open(EVENTS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            if event == "bind":
                _active_bindings.add(stream)
            elif event == "unbind":
                _active_bindings.discard(stream)
            if rotate_if_needed(EVENTS_FILE, EVENTS_MAX_BYTES) is not None:
                with open(EVENTS_FILE, "a", encoding="utf-8") as f:
                    for name in sorted(_active_bindings):
                        checkpoint = {
                            "timestamp": entry["timestamp"],
                            "event": "bind",
                            "stream": name,
                        }
                        f.write(json.dumps(checkpoint) + "\n")
    except Exception as e:
        print(f"Error writing event: {e}", file=sys.stderr)


def passthrough_headers(items):
    """The upstream response headers the recorder relays.

    Only RELAYED_HEADERS pass; the framing the recorder sets itself is
    never among them.
    """
    return [
        (k, v)
        for k, v in items
        if k.lower() in RELAYED_HEADERS and k.lower() not in FRAMING_HEADERS
    ]


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Return a 3xx to the caller as an HTTPError instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = str(newurl)[:REDIRECT_LOG_MAX]
        print(f"upstream redirect refused: {code} to {target}", file=sys.stderr, flush=True)
        return None


@dataclasses.dataclass(frozen=True)
class Timing:
    """The request deadlines, in seconds from the start of a request (SV O3, per request here).

    The harness's client gives a reply up to client_timeout; the recorder answers inside it with
    margin to spare. The upstream phase ends at t0 + upstream however late it began, and no
    request starts its upstream phase later than t0 + latest_start.
    """

    client_timeout: float = 600
    margin: float = 30
    upstream: float = 540
    latest_start: float = 480
    operation: float = 60


def timing_from_environment():
    def number(name, default):
        raw = os.environ.get(name, "").strip()
        try:
            return float(raw) if raw else default
        except ValueError:
            return float("nan")

    base = Timing()
    return Timing(
        client_timeout=number("RECORDER_CLIENT_TIMEOUT", base.client_timeout),
        margin=number("RECORDER_DEADLINE_MARGIN", base.margin),
        upstream=number("RECORDER_UPSTREAM_DEADLINE", base.upstream),
        latest_start=number("RECORDER_LATEST_START", base.latest_start),
        operation=number("RECORDER_OPERATION_TIMEOUT", base.operation),
    )


def timing_problems(timing):
    """Why a timing profile cannot work; empty when it can."""
    problems = []
    for field in dataclasses.fields(timing):
        value = getattr(timing, field.name)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            problems.append(f"{field.name} is not a finite number")
        elif value < 0 or (value == 0 and field.name != "margin"):
            problems.append(f"{field.name} must be positive")
    if problems:
        return problems
    if timing.latest_start >= timing.upstream:
        problems.append("latest_start must be earlier than upstream")
    if timing.upstream > timing.client_timeout - timing.margin:
        problems.append("upstream must end inside client_timeout - margin")
    if timing.operation > timing.upstream:
        problems.append("operation must not exceed upstream")
    return problems


TIMING = timing_from_environment()
DEADLINE_CLOCK = time.monotonic
# The per-operation socket timeout runs this far past the deadline, so the timer, not the socket,
# is what ends a request at its deadline.
OPERATION_GRACE = 1.0


def _shut(sock):
    """Shut a socket for both directions; whatever state it is in, quietly."""
    if sock is None:
        return
    with contextlib.suppress(OSError, ValueError, AttributeError):
        socket.socket.shutdown(sock, socket.SHUT_RDWR)


class Deadline:
    """One request's clock, and the socket its timer shuts at t0 + upstream."""

    def __init__(self, timing=None, clock=None):
        self.timing = timing if timing is not None else TIMING
        self.clock = clock if clock is not None else DEADLINE_CLOCK
        self.t0 = self.clock()
        self.connected = False
        self.fired = False
        self._sock = None
        self._lock = threading.Lock()
        self._timer = None

    def elapsed(self):
        return self.clock() - self.t0

    def left(self):
        return self.t0 + self.timing.upstream - self.clock()

    def may_start(self):
        return self.clock() - self.t0 <= self.timing.latest_start

    def operation_timeout(self):
        return max(0.05, min(self.timing.operation, self.left() + OPERATION_GRACE))

    def arm(self):
        self._timer = threading.Timer(max(0.0, self.left()), self.fire)
        self._timer.daemon = True
        self._timer.name = "recorder-deadline"
        self._timer.start()

    def disarm(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def fire(self):
        with self._lock:
            self.fired = True
            sock = self._sock
        _shut(sock)

    def register(self, sock):
        """The upstream socket now exists: the request counts as sent from here on."""
        with self._lock:
            self._sock = sock
            self.connected = True
            fired = self.fired
        if fired:
            _shut(sock)


class WatchedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, deadline=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._deadline = deadline

    def connect(self):
        super().connect()
        if self._deadline is not None:
            self._deadline.register(self.sock)


class WatchedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, deadline=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._deadline = deadline

    def connect(self):
        # The TLS wrap replaces the socket object; the wrapped one is what the timer must shut.
        super().connect()
        if self._deadline is not None:
            self._deadline.register(self.sock)


class _WatchedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        connection = functools.partial(WatchedHTTPConnection, deadline=getattr(req, "deadline", None))
        return self.do_open(connection, req)


class _WatchedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        connection = functools.partial(WatchedHTTPSConnection, deadline=getattr(req, "deadline", None))
        return self.do_open(connection, req, context=self._context)


_FORWARD_OPENER = urllib.request.build_opener(_RefuseRedirects, _WatchedHTTPHandler, _WatchedHTTPSHandler)


def forward_open(req, timeout=60):
    """Open an upstream request without following redirects.

    A request carrying a `deadline` attribute registers its upstream socket with it, so the
    deadline's timer can cut the exchange at any phase.
    """
    return _FORWARD_OPENER.open(req, timeout=timeout)


_real_forward_open = forward_open


def _capped_text(value, limit):
    """value encoded to at most limit bytes, cut on a character boundary."""
    return value.encode("utf-8", errors="replace")[:limit].decode("utf-8", errors="ignore")


def _error_fields(status, body):
    """The reduced error object for an upstream error body."""
    error = {"message": "upstream error", "code": status}
    if 300 <= status < 400 or len(body) >= ERROR_BODY_READ_MAX:
        return error
    text = body.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except (ValueError, RecursionError):
        plain = text.strip()
        if (
            plain
            and plain[0] not in "{["
            and len(plain.encode("utf-8")) <= ERROR_PLAIN_TEXT_MAX
            and "<" not in plain
            and "{" not in plain
        ):
            error["message"] = plain
        return error
    if not isinstance(parsed, dict):
        return error
    inner = parsed.get("error")
    inner = inner if isinstance(inner, dict) else {}
    for candidate in (
        inner.get("message"),
        parsed.get("message"),
        parsed.get("detail"),
        parsed.get("error"),
    ):
        if isinstance(candidate, str):
            error["message"] = _capped_text(candidate, ERROR_MESSAGE_MAX)
            break
    if isinstance(inner.get("type"), str):
        error["type"] = _capped_text(inner["type"], ERROR_TYPE_MAX)
    reason = inner.get("code")
    if not isinstance(reason, str):
        reason = parsed.get("code")
    if isinstance(reason, str):
        error["reason"] = _capped_text(reason, ERROR_REASON_MAX)
    return error


def sanitised_error(status, body, headers):
    """The error body and headers relayed to the agent for an upstream error.

    The body is reduced to a message, the status, and an optional error type
    and reason; every other field is dropped. A body with no usable message
    is replaced by a fixed one. The raw body goes to stderr, never onward.
    """
    print(
        f"upstream error body ({status}): {body[:ERROR_LOG_MAX].decode('utf-8', errors='replace')}",
        file=sys.stderr,
        flush=True,
    )
    try:
        error = _error_fields(status, body)
    except Exception:
        error = {"message": "upstream error", "code": status}
    relayed = [("Content-Type", "application/json")]
    relayed += [(k, v) for k, v in passthrough_headers(headers) if k.lower() == "retry-after"]
    return json.dumps({"error": error}).encode("utf-8"), relayed


def iter_response_chunks(response, size=65536):
    """Yield an upstream response body in the pieces it arrives in.

    read1 returns what a single underlying read produced, so a piece leaves
    for the client as soon as the upstream sends it. An empty piece is the
    end of the body.
    """
    reader = getattr(response, "read1", None)
    if reader is None:
        reader = response.read
    while True:
        piece = reader(size)
        if not piece:
            return
        yield piece


class _DeadlinePassed(Exception):
    pass


def relay_chunks(writer, response, record, size=65536, deadline=None):
    """Relay a response body to the client with chunked transfer framing.

    Each piece is fed to the record as it passes, so nothing holds the body
    whole. Returns the exception that ended the relay early, or None. Each
    frame is written in one call, so a failed write leaves no partial frame,
    and the terminating chunk is written only when the body ended.
    """
    error = None
    try:
        for piece in iter_response_chunks(response, size):
            if deadline is not None and deadline.fired:
                raise _DeadlinePassed("upstream deadline")
            record.feed(piece)
            writer.write(b"%X\r\n" % len(piece) + piece + b"\r\n")
        # A socket shut at the deadline reads as an end of body: only the flag can tell.
        if deadline is not None and deadline.fired:
            raise _DeadlinePassed("upstream deadline")
        writer.write(b"0\r\n\r\n")
    except Exception as e:
        error = e
    record.finish()
    return error


class _Ambiguous(ValueError):
    pass


def _no_duplicates(pairs):
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise _Ambiguous("a key appears twice in one object")
    # A parser that matches fields ignoring case, with Unicode folding (Go's encoding/json
    # merges "messages", "Messages" and "meſſages"), would read two of these keys as one.
    if not all(key.isascii() for key in keys):
        raise _Ambiguous("a key is not ascii")
    folded = [key.lower() for key in keys]
    if len(set(folded)) != len(folded):
        raise _Ambiguous("two keys differ only in case")
    return dict(pairs)


def _no_constants(name):
    raise _Ambiguous(f"{name} is not a json number")


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise _Ambiguous(f"{text[:40]} overflows a double")
    return value


def strict_request(body):
    """Why a request body is not one strict JSON object, or None.

    The transcript must record what the upstream read. A body that parsers can read two ways -- a
    key given twice, NaN or Infinity, a number that overflows a double, a lone surrogate -- or that
    is not valid UTF-8 JSON at all, is refused before anything is admitted, so no exchange happens
    that the record does not show.
    """
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return "request body is not a json object"
    try:
        data = json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_constant=_no_constants,
            parse_float=_finite_float,
        )
    except _Ambiguous as e:
        return f"ambiguous_json: {e}"
    except (ValueError, RecursionError):
        return "request body is not a json object"
    if not isinstance(data, dict):
        return "request body is not a json object"
    try:
        # A lone surrogate parses here and is read differently, or refused, by other parsers.
        json.dumps(data, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError:
        return "ambiguous_json: a string carries a lone surrogate"
    except (ValueError, RecursionError):
        return "request body is not a json object"
    return None


def raw_record(data):
    """A body that is not recorded as JSON: as text, cut at RAW_RECORD_CHARS."""
    text = data.decode("utf-8", errors="replace")
    if len(text) > RAW_RECORD_CHARS:
        return {"raw_body": text[:RAW_RECORD_CHARS], "raw_body_truncated": True}
    return {"raw_body": text}


def sse_payload(line):
    """The JSON object a data: line carries, or None.

    The terminating [DONE] event, comments, blank lines, and any payload that
    is not a JSON object yield None.
    """
    line = line.strip()
    if not line.startswith(b"data:"):
        return None
    data = line[len(b"data:") :].strip()
    if not data or data == b"[DONE]":
        return None
    if recorder_streams.over_caps(data, recorder_streams.RESPONSE_CAPS) is not None:
        return None
    try:
        payload = json.loads(data.decode("utf-8", errors="replace"))
    except (ValueError, RecursionError):
        return None
    return payload if isinstance(payload, dict) else None


def _delta_index(fragment, position):
    """The index a delta fragment belongs to, defaulting to its position."""
    index = fragment.get("index")
    if isinstance(index, int) and not isinstance(index, bool):
        return index
    return position


def _accumulate_tool_calls(accumulated, fragments):
    """Merge one delta's tool-call fragments into the calls built so far.

    Fragments key on the index they carry; arguments concatenate, and id,
    type, and name are taken from the first fragment supplying them.
    """
    for position, fragment in enumerate(fragments):
        if not isinstance(fragment, dict):
            continue
        call = accumulated.setdefault(
            _delta_index(fragment, position),
            {"id": None, "type": "function", "name": None, "arguments": []},
        )
        if call["id"] is None and isinstance(fragment.get("id"), str):
            call["id"] = fragment["id"]
        if isinstance(fragment.get("type"), str):
            call["type"] = fragment["type"]
        function = fragment.get("function")
        if not isinstance(function, dict):
            continue
        if call["name"] is None and isinstance(function.get("name"), str):
            call["name"] = function["name"]
        if isinstance(function.get("arguments"), str):
            call["arguments"].append(function["arguments"])


def _accumulate_choice(accumulated, choice):
    """Merge one streamed choice into the message built for its index."""
    if choice.get("finish_reason") is not None:
        accumulated["finish_reason"] = choice["finish_reason"]
    delta = choice.get("delta")
    if not isinstance(delta, dict):
        return
    if accumulated["role"] is None and isinstance(delta.get("role"), str):
        accumulated["role"] = delta["role"]
    if isinstance(delta.get("content"), str):
        accumulated["content"].append(delta["content"])
    for field in REASONING_DELTA_FIELDS:
        if isinstance(delta.get(field), str):
            accumulated["reasoning"].setdefault(field, []).append(delta[field])
    if isinstance(delta.get("tool_calls"), list):
        _accumulate_tool_calls(accumulated["tool_calls"], delta["tool_calls"])


def _render_choice(index, accumulated):
    """The completed choice object for one accumulated stream index."""
    message = {"role": accumulated["role"] or "assistant"}
    for field, parts in accumulated["reasoning"].items():
        message[field] = "".join(parts)
    message["content"] = "".join(accumulated["content"]) or None
    if accumulated["tool_calls"]:
        message["tool_calls"] = [
            {
                "id": call["id"],
                "type": call["type"],
                "function": {
                    "name": call["name"] or "",
                    "arguments": "".join(call["arguments"]),
                },
            }
            for _, call in sorted(accumulated["tool_calls"].items())
        ]
    return {"index": index, "message": message, "finish_reason": accumulated["finish_reason"]}


class StreamRecord:
    """The completion a streamed response describes, rebuilt as its bytes pass.

    Each piece of the body is fed in the order it arrives; events are parsed
    line by line, so an event split across two pieces still decodes, and only
    the reassembled completion is held: content and reasoning fragments
    concatenate, tool calls reassemble on the index their fragments carry,
    the finish reason is the one a chunk set, and usage comes from the event
    carrying it. The body itself is not kept, beyond a prefix of at most
    STREAM_RETAIN_BYTES for a body that turns out to carry no events. A single
    line longer than that is dropped rather than held.
    """

    def __init__(self):
        self._completion = {"object": "chat.completion"}
        self._choices = {}
        self._tail = b""
        self._dropping = False
        self.raw = b""
        self.raw_bytes = 0
        self.raw_truncated = False
        self.events = 0

    def feed(self, piece):
        """Take the next piece of the body."""
        limit = STREAM_RETAIN_BYTES
        self.raw_bytes += len(piece)
        if len(self.raw) < limit:
            self.raw += piece[: limit - len(self.raw)]
        if self.raw_bytes > limit:
            self.raw_truncated = True
        data = (self._tail + piece).replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        lines = data.split(b"\n")
        self._tail = lines.pop()
        for line in lines:
            if self._dropping:
                self._dropping = False
                continue
            self._line(line)
        if len(self._tail) > limit:
            self._tail = b""
            self._dropping = True

    def finish(self):
        """Take a trailing event the body ended without a newline after."""
        if self._tail and not self._dropping:
            self._line(self._tail)
        self._tail = b""
        self._dropping = False

    def _line(self, line):
        payload = sse_payload(line)
        if payload is None:
            return
        self.events += 1
        completion = self._completion
        for field in ("id", "created", "model"):
            if field not in completion and payload.get(field) is not None:
                completion[field] = payload[field]
        if isinstance(payload.get("usage"), dict):
            completion["usage"] = payload["usage"]
        entries = payload.get("choices")
        if not isinstance(entries, list):
            return
        for position, choice in enumerate(entries):
            if not isinstance(choice, dict):
                continue
            index = _delta_index(choice, position)
            if index not in self._choices:
                self._choices[index] = {
                    "role": None,
                    "content": [],
                    "reasoning": {},
                    "tool_calls": {},
                    "finish_reason": None,
                }
            _accumulate_choice(self._choices[index], choice)

    def completion(self):
        """The completed chat-completion object the events described so far.

        The usage field is absent when no event carried one.
        """
        completion = dict(self._completion)
        completion["choices"] = [
            _render_choice(index, self._choices[index]) for index in sorted(self._choices)
        ]
        return completion


def reconstruct_completion(chunks):
    """Rebuild a completed chat-completion object from a body's pieces.

    Pieces may be bytes or text. The result is the shape a buffered exchange
    has, so a streamed exchange is recorded like one.
    """
    record = StreamRecord()
    for chunk in chunks:
        record.feed(chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
    record.finish()
    return record.completion()


def stream_response_data(record):
    """The response object recorded for a relayed body.

    Deltas are reassembled into a completed object. A body that carried no
    events is recorded as itself, so an upstream answering a streamed request
    with a whole document, or with an error, is not lost from the transcript;
    one longer than the record kept is recorded as the prefix it kept, marked
    truncated.
    """
    completion = record.completion()
    if completion["choices"] or "usage" in completion:
        return completion
    text = record.raw.decode("utf-8", errors="replace")
    if not record.raw_truncated:
        try:
            data = json.loads(text)
        except (ValueError, RecursionError):
            data = None
        if isinstance(data, dict):
            return data
        return {"raw_body": text}
    return {"raw_body": text, "raw_body_truncated": True}


class ProxyHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 300

    def log_message(self, format, *args):
        sys.stdout.write(
            f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {self.client_address[0]} - {format % args}\n"
        )
        sys.stdout.flush()

    def do_POST(self):
        deadline = Deadline()
        if self.path != "/api/v1/chat/completions":
            self.send_error(404, "Not Found")
            return

        if self.headers.get("Transfer-Encoding"):
            self._refuse_and_close(411, "request body must carry a content-length")
            return

        raw_length = self.headers.get("Content-Length", "0")
        try:
            content_length = int(raw_length)
        except ValueError:
            self._refuse_and_close(400, "content-length must be an integer")
            return
        if content_length < 0:
            self._refuse_and_close(400, "content-length must not be negative")
            return
        if content_length > REQUEST_MAX_BYTES:
            self._refuse_and_close(413, f"request body must be at most {REQUEST_MAX_BYTES} bytes")
            return
        req_body = self.rfile.read(content_length)
        stream = getattr(self.server, "stream_name", "core")
        registry = getattr(self.server, "registry", None)

        # Structure before anything parses the body: nothing is admitted, reserved or forwarded.
        over = recorder_streams.over_caps(req_body, recorder_streams.REQUEST_CAPS)
        if over is not None:
            req_data = raw_record(req_body)
            event_id = request_id()
            started = time.monotonic()
            log_event("open", stream, id=event_id, model=None, messages=0)
            log_event(
                "close",
                stream,
                id=event_id,
                status=400,
                duration_seconds=round(time.monotonic() - started, 3),
                elapsed_s=round(deadline.elapsed(), 3),
            )
            self._finish_local(stream, req_data, 400, f"structure_limit: {over} over its limit")
            return

        problem = strict_request(req_body)
        if problem is not None:
            req_data = raw_record(req_body)
            event_id = request_id()
            log_event("open", stream, id=event_id, model=None, messages=0)
            log_event(
                "close",
                stream,
                id=event_id,
                status=400,
                elapsed_s=round(deadline.elapsed(), 3),
                refusal=problem[:200],
            )
            self._finish_local(stream, req_data, 400, problem)
            return

        if not record_capacity_ok():
            # A reply that could not be recorded would be withheld after it was paid for; with the
            # volume this full, refuse before paying (plan 4b ruling 5).
            req_data = raw_record(req_body[:4096])
            event_id = request_id()
            log_event("open", stream, id=event_id, model=None, messages=0)
            log_event(
                "close", stream, id=event_id, status=503, elapsed_s=round(deadline.elapsed(), 3)
            )
            self._finish_local(
                stream,
                req_data,
                503,
                f"record_capacity: under {RECORDER_MIN_FREE_BYTES} bytes free for the transcript",
            )
            return

        refused = None
        ticket = None
        fleet_ticket = None
        caps = getattr(self.server, "core_caps", None)
        fleet = getattr(self.server, "fleet", None)
        if stream == "core":
            if caps is not None:
                refused, ticket = caps.admit(req_body)
        elif registry is not None:
            # The fleet is asked before the stream's own hour is charged, so a fleet refusal
            # costs the stream nothing, as Aurora's own shared-pool refusal costs no request.
            if fleet is not None:
                declared = registry.state()["streams"].get(stream)
                if declared is not None:
                    # Reserve on the body the stream will forward, composed from its declaration,
                    # so the fleet holds what the stream itself holds.
                    composed, error = recorder_streams.compose_body(
                        req_body, declared["settings"], recorder_streams.reasoning_allowance()
                    )
                    refused, fleet_ticket = fleet.reserve(
                        recorder_streams.reservation_for(
                            req_body if error else composed, declared["tokens"]["allowance"]
                        )
                    )
            if refused is None:
                req_body, refused, ticket = registry.admit(stream, req_body)
                if refused is not None and fleet is not None:
                    fleet.settle(fleet_ticket, 0)

        try:
            req_data = json.loads(req_body.decode("utf-8"))
        except Exception:
            req_data = None
        if not isinstance(req_data, dict):
            req_data = raw_record(req_body)

        event_id = request_id()
        messages = req_data.get("messages")
        started = time.monotonic()
        log_event(
            "open",
            stream,
            id=event_id,
            model=req_data.get("model"),
            messages=len(messages) if isinstance(messages, list) else 0,
        )

        if refused is not None:
            status_code, message = refused
            log_event(
                "close",
                stream,
                id=event_id,
                status=status_code,
                duration_seconds=round(time.monotonic() - started, 3),
                elapsed_s=round(deadline.elapsed(), 3),
                refusal=message[:200],
            )
            self._finish_local(stream, req_data, status_code, message)
            return

        if not deadline.may_start():
            # Too late to give the upstream its time: refused before contact, and refunded.
            self._cancel(stream, registry, caps, fleet, ticket, fleet_ticket)
            log_event(
                "close",
                stream,
                id=event_id,
                status=503,
                duration_seconds=round(time.monotonic() - started, 3),
                elapsed_s=round(deadline.elapsed(), 3),
            )
            self._finish_local(
                stream,
                req_data,
                503,
                f"deadline_insufficient: {deadline.elapsed():.1f} s gone of a "
                f"{deadline.timing.latest_start:g} s start allowance",
            )
            return

        target_url, target_key = upstream_for(stream)
        headers_to_forward = build_forward_headers(self.headers, target_key)

        req = urllib.request.Request(
            target_url,
            data=req_body,
            headers=headers_to_forward,
            method="POST",
        )
        req.deadline = deadline

        response_body = b""
        response_code = 500
        response_headers = []
        relayed = None
        upstream_refused = False
        opened = False
        refund = False

        deadline.arm()
        try:
            with forward_open(req, timeout=deadline.operation_timeout()) as res:
                opened = True
                response_code = res.status
                response_headers = passthrough_headers(res.getheaders())
                if req_data.get("stream") is True:
                    relayed = self._relay(response_code, response_headers, res, deadline)
                else:
                    response_body = res.read(RESPONSE_MAX_BYTES + 1)
                    # A socket shut at the deadline reads as an end of body: only the flag can tell.
                    if deadline.fired:
                        raise _DeadlinePassed("upstream deadline")
        except urllib.error.HTTPError as e:
            response_code = e.code
            try:
                raw_error = e.read(ERROR_BODY_READ_MAX)
            except Exception:
                raw_error = b""
            finally:
                e.close()
            response_body, response_headers = sanitised_error(
                response_code, raw_error, e.headers.items()
            )
            upstream_refused = True
        except Exception as e:
            if deadline.fired:
                response_code = 502
                message = f"upstream_deadline: no complete reply within {deadline.timing.upstream:g} s"
            else:
                detail = repr(e)
                if target_key:
                    for form in (
                        target_key,
                        repr(target_key)[1:-1],
                        repr(repr(target_key)[1:-1])[1:-1],
                    ):
                        detail = detail.replace(form, "[key]")
                print(f"proxy error: {detail}", file=sys.stderr, flush=True)
                response_code = 500
                message = "proxy error"
                # Nothing reached the upstream, so nothing was generated: refund it.
                refund = not opened and not deadline.connected
            response_body = json.dumps({"error": {"message": message}}).encode("utf-8")
            response_headers = [("Content-Type", "application/json")]
        finally:
            deadline.disarm()

        untrusted = False
        if relayed is not None:
            res_data = stream_response_data(relayed)
        elif len(response_body) > RESPONSE_MAX_BYTES:
            # Withheld: a prefix is not the answer. Recorded as read, its usage unknown.
            res_data = raw_record(response_body[:RESPONSE_MAX_BYTES])
            res_data["raw_body_truncated"] = True
            untrusted = True
            response_code = 502
            response_body = json.dumps(
                {"error": {"message": f"response_too_large: over {RESPONSE_MAX_BYTES} bytes"}}
            ).encode("utf-8")
            response_headers = [("Content-Type", "application/json")]
        elif recorder_streams.over_caps(response_body, recorder_streams.RESPONSE_CAPS) is not None:
            # Relayed as the upstream sent it, recorded raw, and its claimed usage not trusted.
            res_data = raw_record(response_body)
            res_data["structure_limit"] = True
            untrusted = True
        else:
            try:
                res_data = json.loads(response_body.decode("utf-8"))
            except Exception:
                res_data = raw_record(response_body)

        close_fields = {
            "id": event_id,
            "status": response_code,
            "duration_seconds": round(time.monotonic() - started, 3),
            "elapsed_s": round(deadline.elapsed(), 3),
        }
        usage = res_data.get("usage") if isinstance(res_data, dict) and not untrusted else None
        if isinstance(usage, dict):
            recorded = {
                key: usage[key]
                for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cache_discount")
                if isinstance(usage.get(key), (int, float))
            }
            details = usage.get("prompt_tokens_details")
            if isinstance(details, dict):
                recorded.update(
                    {
                        key: details[key]
                        for key in ("cached_tokens", "cache_write_tokens")
                        if isinstance(details.get(key), (int, float))
                    }
                )
            close_fields["usage"] = recorded

        # An upstream that answered with an error status generated nothing,
        # so the request settles at zero. A request whose usage is unknown
        # for any other reason - a relay that broke, a transport failure
        # after the request may have been received - keeps its reservation.
        spent = usage.get("total_tokens") if isinstance(usage, dict) else None
        if isinstance(spent, bool) or not isinstance(spent, (int, float)):
            spent = 0 if upstream_refused else None
        settled = None
        if refund:
            self._cancel(stream, registry, caps, fleet, ticket, fleet_ticket)
        elif registry is not None and stream != "core":
            registry.settle(stream, ticket, spent)
            if fleet is not None:
                settled = fleet.settle(fleet_ticket, spent)
        elif stream == "core" and caps is not None:
            settled = caps.settle(ticket, spent)
        if isinstance(settled, dict) and "late" in settled:
            close_fields["late_adjustment"] = settled["late"]
        elif settled == "unknown":
            close_fields["late_adjustment"] = "unknown"

        try:
            record = self.log_transcript(
                req_data, res_data, stream=stream, after_relay=relayed is not None
            )
        except Exception as e:  # noqa: BLE001 -- a record that cannot be written is "failed"
            print(f"Error writing transcript: {type(e).__name__}: {e}", file=sys.stderr)
            record = "failed"
        close_fields["record"] = record
        if relayed is None and record not in READABLE:
            # John's rule: every reply an agent acts on is on record. This one is not, so the
            # agent does not get it; what it cost is charged above all the same.
            close_fields["status"] = 502
            close_fields["upstream_status"] = response_code
            response_code = 502
            response_body = json.dumps(
                {
                    "error": {
                        "message": "record_failed: the recorder could not write this exchange "
                        "to the transcript"
                    }
                }
            ).encode("utf-8")
            response_headers = [("Content-Type", "application/json")]
        log_event("close", stream, **close_fields)

        if relayed is None:
            self.send_response(response_code)
            for k, v in response_headers:
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

    def _refuse_and_close(self, status_code, message):
        """Answer a request whose body was not read, and close the connection.

        The unread body would otherwise be parsed as the next request line.
        """
        body = json.dumps({"error": {"message": message}}).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    @staticmethod
    def _cancel(stream, registry, caps, fleet, ticket, fleet_ticket):
        """Refund a request that never reached the upstream: its reservation and its count."""
        if stream == "core":
            if caps is not None:
                caps.cancel(ticket)
            return
        if registry is not None:
            registry.cancel(stream, ticket)
        if fleet is not None:
            fleet.settle(fleet_ticket, 0)

    def _relay(self, response_code, response_headers, res, deadline=None):
        """Stream an upstream response to the client and return its record.

        The response is framed as chunked transfer encoding rather than by
        length, since its size is unknown until it ends. Nothing here raises:
        once framing has begun the client cannot be told anything else, so a
        relay that ends early only closes the connection.
        """
        record = StreamRecord()
        try:
            self.send_response(response_code)
            for k, v in response_headers:
                self.send_header(k, v)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
        except Exception:
            self.close_connection = True
            return record
        error = relay_chunks(self.wfile, res, record, deadline=deadline)
        if error is not None:
            self.close_connection = True
        return record

    def _finish_local(self, stream, req_data, status_code, message):
        """Answer a request locally with a factual error and record the exchange."""
        res_data = {"error": {"message": message}}
        body = json.dumps(res_data).encode("utf-8")
        try:
            # Nothing was spent on a local answer, so it is relayed whether or not it is recorded.
            self.log_transcript(req_data, res_data, stream=stream)
        except Exception as e:  # noqa: BLE001
            print(f"Error writing transcript: {type(e).__name__}: {e}", file=sys.stderr)
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _display_text(content):
        """A message's content as text.

        A multimodal message carries a list of parts rather than a string, and
        a length test over that list counts parts, not characters, so the
        display caps below would not bound an embedded data URL.
        """
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        try:
            return json.dumps(content, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(content)

    def log_transcript(self, request_data, response_data, stream="core", *, after_relay=False):
        """Append the exchange to the JSON transcript and return the append's result.

        The JSON transcript is the record, written through append_record; the plain-text copy and
        the stdout dump stay best-effort. A streamed reply is recorded after it was relayed, and
        its line says so.
        """
        global _degraded_reported
        with contextlib.suppress(OSError):
            os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

        entry = {
            "timestamp": utc_timestamp(),
            "stream": stream,
            "request": request_data,
            "response": response_data,
        }
        if after_relay:
            entry["recorded_after_relay"] = True

        with _transcript_lock:
            try:
                line = json.dumps(entry, ensure_ascii=True, allow_nan=False).encode("ascii")
            except (TypeError, ValueError) as e:
                print(f"Error writing transcript: {e}", file=sys.stderr)
                result = "failed"
            else:
                result = append_record(TRANSCRIPT_FILE, line)
            if result in READABLE:
                print(f"Recorded transaction in: {os.path.basename(TRANSCRIPT_FILE)}")
            else:
                print(f"Error writing transcript: {result}", file=sys.stderr)
            if result == "appended_fsync_failed" and not _degraded_reported:
                _degraded_reported = True
                print(
                    "transcript durability degraded: a data sync failed; lines are written "
                    "but may not survive a crash",
                    file=sys.stderr,
                    flush=True,
                )
            rotate_if_needed(TRANSCRIPT_FILE)


        # Everything below is display, best-effort: the record above is written whatever shape the
        # agent's messages or the upstream's reply take, and a display that cannot render them
        # must not cost the exchange its record, its close event or its reply.
        try:
            print("\n" + "=" * 80)
            print(f"PROXY INTERCEPTED REQUEST | Model: {request_data.get('model')}")
            print("=" * 80)
            for msg in request_data.get("messages", []):
                role = msg.get("role", "unknown").upper()
                content = self._display_text(msg.get("content", ""))
                tool_calls = msg.get("tool_calls")
                name = msg.get("name")
                name_suffix = f" (Name: {name})" if name else ""

                if content:
                    display_content = (
                        content
                        if len(content) < 1500
                        else content[:1500] + "\n... [TRUNCATED FOR CONSOLE DISPLAY] ..."
                    )
                    print(f"[{role}{name_suffix}]: {display_content}")
                if tool_calls:
                    print(f"[{role} TOOL CALLS]:")
                    for tc in tool_calls:
                        print(
                            f"  - ID: {tc.get('id')} | Function: {tc.get('function', {}).get('name')} | Args: {tc.get('function', {}).get('arguments')}"
                        )
            print("-" * 80)

            print("PROXY INTERCEPTED RESPONSE")
            print("=" * 80)
            choices = response_data.get("choices", [])
            if choices:
                choice = choices[0]
                message = choice.get("message", {})
                reasoning = message.get("reasoning_content") or message.get("reasoning")
                content = message.get("content")
                tool_calls = message.get("tool_calls")

                if reasoning:
                    print(f"[REASONING]: {reasoning}")
                if content:
                    print(f"[ASSISTANT]: {content}")
                if tool_calls:
                    print("[ASSISTANT TOOL CALLS]:")
                    for tc in tool_calls:
                        print(
                            f"  - ID: {tc.get('id')} | Function: {tc.get('function', {}).get('name')} | Args: {tc.get('function', {}).get('arguments')}"
                        )
            elif "error" in response_data:
                print(f"ERROR: {json.dumps(response_data.get('error'))}")
            else:
                print(f"[RAW RESPONSE]: {json.dumps(response_data)[:500]}")
            print("=" * 80 + "\n")
            sys.stdout.flush()


            plain_log_lines = []
            timestamp = entry["timestamp"]
            plain_log_lines.append("=" * 80)
            plain_log_lines.append(f"TRANSACTION | {timestamp} | Model: {request_data.get('model')}")
            plain_log_lines.append("=" * 80)

            plain_log_lines.append("--- REQUEST MESSAGES ---")
            for msg in request_data.get("messages", []):
                role = msg.get("role", "unknown").upper()
                content = self._display_text(msg.get("content", ""))
                tool_calls = msg.get("tool_calls")
                name = msg.get("name")
                name_suffix = f" (Name: {name})" if name else ""

                if role == "TOOL":
                    plain_log_lines.append(f"[{role}{name_suffix}]: [Tool call output omitted]")
                else:
                    if content:
                        plain_log_lines.append(f"[{role}{name_suffix}]: {content}")
                    else:
                        plain_log_lines.append(f"[{role}{name_suffix}]: [No text content]")

                if tool_calls:
                    tc_names = [tc.get("function", {}).get("name", "unknown") for tc in tool_calls]
                    plain_log_lines.append(f"[{role} TOOL CALLS]: {', '.join(tc_names)}")

            plain_log_lines.append("-" * 40)
            plain_log_lines.append("--- RESPONSE ---")

            choices = response_data.get("choices", [])
            if choices:
                choice = choices[0]
                message = choice.get("message", {})
                reasoning = message.get("reasoning_content") or message.get("reasoning")
                content = message.get("content")
                tool_calls = message.get("tool_calls")

                if reasoning:
                    plain_log_lines.append(f"[THINKING/REASONING]: {reasoning}")
                if content:
                    plain_log_lines.append(f"[ASSISTANT RESPONSE]: {content}")
                if tool_calls:
                    tc_names = [tc.get("function", {}).get("name", "unknown") for tc in tool_calls]
                    plain_log_lines.append(f"[TOOL CALLS INITIATED]: {', '.join(tc_names)}")
            elif "error" in response_data:
                plain_log_lines.append(f"ERROR: {json.dumps(response_data.get('error'))}")
            else:
                plain_log_lines.append("[NO RESPONSE CHOICES]")

            plain_log_lines.append("=" * 80 + "\n\n")
            plain_log_content = "\n".join(plain_log_lines)

            with _transcript_lock:
                try:
                    with open(PLAIN_TRANSCRIPT_FILE, "a", encoding="utf-8") as f:
                        f.write(plain_log_content)
                    print(
                        f"Recorded plain text transaction in: {os.path.basename(PLAIN_TRANSCRIPT_FILE)}"
                    )
                except Exception as e:
                    print(f"Error writing plain transcript: {e}", file=sys.stderr)
                rotate_if_needed(PLAIN_TRANSCRIPT_FILE)
        except Exception as e:  # noqa: BLE001 -- display only
            print(f"Error displaying transcript: {type(e).__name__}: {e}", file=sys.stderr)
        return result


class UnixHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Multi-threaded HTTP server bound to a unix domain socket.

    HTTPServer.server_bind unpacks server_address[:2] as a host and port, which
    on a filesystem path yields two characters and then attempts to resolve the
    first as a hostname. AF_UNIX accept() also reports an empty peer address,
    which the handler's logging indexes. Both are handled here so the request
    handler itself needs no changes.
    """

    address_family = socket.AF_UNIX
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        try:
            os.unlink(self.server_address)
        except FileNotFoundError:
            pass
        socketserver.TCPServer.server_bind(self)
        os.chmod(self.server_address, 0o660)
        self.server_name = "unix"
        self.server_port = 0

    def get_request(self):
        conn, _ = self.socket.accept()
        return conn, ("unix", 0)


def sweep_stale_sockets(sock_dir, keep):
    """Unlink socket files in the directory that no server is serving."""
    try:
        names = os.listdir(sock_dir)
    except OSError:
        return
    for name in names:
        if not name.endswith(".sock") or name in keep:
            continue
        try:
            os.unlink(os.path.join(sock_dir, name))
        except OSError:
            pass


_FLEET = None


def bind_stream(registry, servers, sock_dir, name):
    """Bind one declared stream's socket and start serving it."""
    path = os.path.join(sock_dir, f"{name}.sock")
    try:
        server = UnixHTTPServer(path, ProxyHTTPRequestHandler)
    except OSError as e:
        registry.reject(name, f"bind failed: {type(e).__name__}")
        return
    server.stream_name = name
    server.registry = registry
    server.fleet = _FLEET
    try:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    except BaseException:
        server.server_close()
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    servers[name] = server


def poll_once(registry, servers, sock_dir, console_path, state_path):
    """Read the console, apply the diff to the sockets, and write the state files."""
    declarations, enabled, error = recorder_streams.load_console(console_path)
    if declarations is not None:
        accepted, rejected = recorder_streams.evaluate_console(declarations, enabled)
        _added, removed = registry.apply(accepted, rejected)
        for name in removed:
            server = servers.pop(name, None)
            if server is not None:
                server.shutdown()
                server.server_close()
            try:
                os.unlink(os.path.join(sock_dir, f"{name}.sock"))
            except OSError:
                pass
            log_event("unbind", name)
        for name in accepted:
            if name in servers:
                continue
            try:
                bind_stream(registry, servers, sock_dir, name)
            except Exception as e:
                registry.reject(name, f"bind failed: {type(e).__name__}")
                print(f"bind fault for {name}: {type(e).__name__}", file=sys.stderr, flush=True)
                continue
            if name in servers:
                log_event("bind", name)
    recorder_streams.write_models(sock_dir)
    recorder_streams.write_state(
        state_path, registry.state(streams_enabled=enabled, console_error=error)
    )


def poll_safely(registry, servers, sock_dir, console_path, state_path):
    """Run one poll. A fault is logged and the current stream set is kept."""
    try:
        poll_once(registry, servers, sock_dir, console_path, state_path)
    except Exception as e:
        print(f"poll fault: {type(e).__name__}: {e!r}", file=sys.stderr, flush=True)


def main():
    problems = timing_problems(TIMING)
    if problems:
        print(f"error: recorder timing: {'; '.join(problems)}", file=sys.stderr, flush=True)
        sys.exit(1)
    if (
        not os.environ.get("HOST_LLM_BASE_URL", "").strip()
        and not os.environ.get("LLM_BASE_URL", "").strip()
        and not os.environ.get("OPENROUTER_API_KEY")
    ):
        print("error: set OPENROUTER_API_KEY, or LLM_BASE_URL for an OpenAI-compatible upstream")
        sys.exit(1)
    for kind in ("LLM", "STREAM"):
        host_url = os.environ.get(f"HOST_{kind}_BASE_URL", "").strip()
        host_key = os.environ.get(f"HOST_{kind}_API_KEY", "").strip()
        if host_url and not host_key:
            print(
                f"warning: host upstream configured without a key (HOST_{kind}_BASE_URL)",
                file=sys.stderr,
                flush=True,
            )
        elif host_key and not host_url:
            print(
                f"warning: host key configured without an upstream (HOST_{kind}_API_KEY)",
                file=sys.stderr,
                flush=True,
            )
    if (
        "HOST_OPENROUTER_KEY_SET" in os.environ
        and not os.environ.get("HOST_LLM_BASE_URL", "").strip()
        and (
            os.environ.get("LLM_BASE_URL", "").strip()
            or not os.environ["HOST_OPENROUTER_KEY_SET"].strip()
        )
    ):
        print(
            "warning: this host's core upstream key is shared with the first host",
            file=sys.stderr,
            flush=True,
        )

    socket_path = os.environ.get("LLM_SOCKET_PATH", SOCKET_PATH)
    sock_dir = os.path.dirname(socket_path) or "."
    os.makedirs(sock_dir, exist_ok=True)

    print("=" * 60)
    print("      TRANSCRIPT PROXY SERVER")
    print("=" * 60)
    print(f"Listening on:  {socket_path}")
    print(f"Forwarding to: {upstream_url()}")
    print(f"Streams to:    {stream_upstream_url()}")
    print(f"Logging to:    {TRANSCRIPT_FILE}")
    print("-" * 60)

    global _FLEET
    try:
        caps, _FLEET = core_caps.caps_from_environment()
    except ValueError as e:
        print(f"error: {e}")
        sys.exit(1)

    registry = recorder_streams.StreamRegistry()
    core = UnixHTTPServer(socket_path, ProxyHTTPRequestHandler)
    core.stream_name = "core"
    core.registry = registry
    core.core_caps = caps
    core.fleet = _FLEET
    sweep_stale_sockets(sock_dir, keep={os.path.basename(socket_path)})
    recorder_streams.write_readme(sock_dir)
    recorder_streams.write_models(sock_dir)
    threading.Thread(target=core.serve_forever, daemon=True).start()
    log_event("bind", "core")

    servers = {}
    state_path = os.path.join(sock_dir, "streams.json")
    try:
        while True:
            poll_safely(registry, servers, sock_dir, recorder_streams.CONSOLE_FILE, state_path)
            time.sleep(recorder_streams.POLL_SECONDS)
    except KeyboardInterrupt:
        print("\nShutting down proxy server...")
    finally:
        core.server_close()
        for server in servers.values():
            server.server_close()
        try:
            os.unlink(socket_path)
        except OSError:
            pass


if __name__ == "__main__":
    main()
