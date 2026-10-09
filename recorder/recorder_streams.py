import errno
import json
import math
import os
import re
import stat
import threading
import time

CONSOLE_FILE = os.environ.get("LLM_CONSOLE_FILE", "/llm/console/console.json")
# The same console file as the agent reaches it. CONSOLE_FILE above is this
# recorder's own view; with several hosts each recorder mounts its own console
# volume at /llm/console, while the agent sees that host's console at
# /llm/consoleN. The README below is written into an agent-readable volume, so
# it must name the agent's path or it would direct one host to write another's
# console.
AGENT_CONSOLE_FILE = os.environ.get("AGENT_CONSOLE_FILE", "/llm/console/console.json")
POLL_SECONDS = 5
CONSOLE_MAX_BYTES = 65_536
MAX_STREAMS = 8
ABSENT_MAX = 16
MODEL_HISTORY_MAX = 8
DEFAULT_STREAM_BUDGET = 10
STREAM_LIMIT_MAX = 120
STREAM_TOKEN_LIMIT_MAX = 2_000_000
STREAM_TOKEN_GLOBAL_LIMIT_MAX = 20_000_000
BUDGET_WINDOW = 3600
PROMPT_BYTES_PER_TOKEN = 4
MODEL_NAME_CAP = 200
REPORTED_NAME_CAP = 80

NAME_PATTERN = re.compile(r"\A[a-z0-9][a-z0-9_-]{0,31}\Z")
RESERVED_NAMES = ("core",)
BUDGET_FIELDS = ("budget", "token_budget")
COMPOSED_FIELDS = ("model", "reasoning_effort", "temperature", "top_p", "max_tokens")
REASONING_EFFORT_LEVELS = ("none", "minimal", "low", "medium", "high")
DEFAULT_REASONING_ALLOWANCE = 8192


def _read_agent_file(path, cap):
    """Read a file another party can write. Returns (data, None) or (None, reason).

    The open does not follow a symlink and does not wait on a pipe. Only a
    regular file is read, and at most cap bytes are accepted.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as e:
        if e.errno == errno.ENOENT:
            return None, "absent"
        if e.errno == errno.ELOOP:
            try:
                os.stat(path)
            except OSError as target_error:
                if target_error.errno == errno.ENOENT:
                    return None, "absent"
            return None, "not a regular file"
        return None, "unreadable"
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None, "not a regular file"
        chunks = []
        remaining = cap + 1
        while remaining > 0:
            chunk = os.read(fd, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > cap:
            return None, "over cap"
        return data, None
    except OSError:
        return None, "unreadable"
    finally:
        os.close(fd)


def _reject_constant(name):
    raise ValueError(f"non-finite number: {name}")


def _reject_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("non-finite number")
    return value


def load_console(path=None):
    """Read the console file. Returns (declarations, enabled, error).

    A missing file is an empty, disabled console. An unreadable,
    unparseable, or wrongly-typed file returns no declarations, disabled,
    and a factual reason, so the caller keeps its current stream set rather
    than tearing it down on a torn write. enabled is True only when
    enable_streams is the literal JSON boolean true; anything else,
    including "true", 1, or null, is disabled.
    """
    if path is None:
        path = CONSOLE_FILE
    raw, reason = _read_agent_file(path, CONSOLE_MAX_BYTES)
    if reason == "absent":
        return {}, False, None
    if reason == "over cap":
        return None, False, "console is too large"
    if reason is not None:
        return None, False, "console is not readable"
    try:
        data = json.loads(
            raw.decode("utf-8"), parse_constant=_reject_constant, parse_float=_reject_float
        )
    except (ValueError, RecursionError, OverflowError):
        return None, False, "console is not valid json"
    if not isinstance(data, dict):
        return None, False, "console is not an object"
    streams = data.get("streams", {})
    if not isinstance(streams, dict):
        return None, False, "streams is not an object"
    enabled = data.get("enable_streams") is True
    return streams, enabled, None


def _number(value, low, high):
    """True when value is a non-boolean number inside the inclusive range."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high


def validate_declaration(name, declaration):
    """Validate one stream declaration. Returns (settings, reason).

    settings is the accepted declaration; reason states why it was rejected.
    Exactly one of the two is None.
    """
    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        return None, "invalid stream name"
    if name in RESERVED_NAMES:
        return None, "reserved name"
    if not isinstance(declaration, dict):
        return None, "declaration is not an object"
    for field in declaration:
        if field not in BUDGET_FIELDS and field not in COMPOSED_FIELDS:
            return None, f"unknown field: {field}"
    settings = {}
    for field in BUDGET_FIELDS:
        if field in declaration:
            budget = declaration[field]
            if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
                return None, f"{field} must be an integer of at least 0"
            settings[field] = budget
    if "model" in declaration:
        model = declaration["model"]
        if not isinstance(model, str) or not model.strip() or len(model) > MODEL_NAME_CAP:
            return None, f"model must be a non-empty string of at most {MODEL_NAME_CAP} characters"
        if model not in permitted_models():
            return None, "model not permitted"
        settings["model"] = model
    if "reasoning_effort" in declaration:
        if declaration["reasoning_effort"] not in REASONING_EFFORT_LEVELS:
            return None, "reasoning_effort must be one of none, minimal, low, medium, high"
        settings["reasoning_effort"] = declaration["reasoning_effort"]
    if "temperature" in declaration:
        if not _number(declaration["temperature"], 0, 2):
            return None, "temperature must be a number from 0 to 2"
        settings["temperature"] = declaration["temperature"]
    if "top_p" in declaration:
        if not _number(declaration["top_p"], 0, 1):
            return None, "top_p must be a number from 0 to 1"
        settings["top_p"] = declaration["top_p"]
    if "max_tokens" in declaration:
        tokens = declaration["max_tokens"]
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 1:
            return None, "max_tokens must be a positive integer"
        settings["max_tokens"] = tokens
    return settings, None


def evaluate_console(declarations, enabled):
    """Split raw declarations into accepted settings and rejection reasons.

    When enabled is False every declaration is rejected with
    "streams are not enabled", ahead of any other check. When the stream
    upstream's key is absent every declaration is rejected with "streams are
    not available": a served socket would only relay authentication failures.
    Otherwise declarations are considered in file order; those past
    MAX_STREAMS are rejected. Reported names are capped so a junk key cannot
    bloat the state file.
    """
    accepted = {}
    rejected = {}
    for name, declaration in declarations.items():
        reported = (name if isinstance(name, str) else str(name))[:REPORTED_NAME_CAP]
        if not enabled:
            rejected[reported] = "streams are not enabled"
            continue
        if not stream_credential_present():
            rejected[reported] = "streams are not available"
            continue
        if len(accepted) >= MAX_STREAMS:
            rejected[reported] = "stream limit reached"
            continue
        settings, reason = validate_declaration(name, declaration)
        if reason is not None:
            rejected[reported] = reason
        else:
            accepted[name] = settings
    return accepted, rejected


def _split_models(name):
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _resolve_pair(host_url, host_key, global_url, global_key, default):
    """Return the (base_url, api_key) pair an upstream resolves to.

    A non-empty host_url selects the host pair, and host_key goes with it
    even when empty. Otherwise the global pair applies; when global_url is
    empty too, base_url is empty and default is the key. A host_key without
    a host_url is ignored.
    """
    host_url = (host_url or "").strip()
    if host_url:
        return host_url, host_key or ""
    global_url = (global_url or "").strip()
    if global_url:
        return global_url, global_key or ""
    return "", default or ""


def stream_credential_present():
    """True when the recorder can serve declared streams at all.

    Declared streams forward to their own upstream, separate from core.sock's.
    With STREAM_BASE_URL (or HOST_STREAM_BASE_URL) set that upstream is explicit and its key may legitimately
    be empty, exactly as a no-auth local server is allowed for core.sock.
    Otherwise the upstream is OpenRouter and its key is required: without it no
    stream can be served, so declarations are rejected and the permitted-model
    list is published empty rather than as usable, leaving no socket whose
    requests could only relay authentication failures.
    """
    base, key = _resolve_pair(
        os.environ.get("HOST_STREAM_BASE_URL"),
        os.environ.get("HOST_STREAM_API_KEY"),
        os.environ.get("STREAM_BASE_URL"),
        os.environ.get("STREAM_API_KEY"),
        os.environ.get("OPENROUTER_API_KEY", ""),
    )
    return bool(base) or bool(key.strip())


def permitted_models():
    """The models a declaration may set, from the environment.

    STREAM_MODEL_ALLOW_TEXT and STREAM_MODEL_ALLOW_VISION are comma-separated
    lists of model identifiers; their union is the permitted set. Both unset
    or empty permits none: a declaration that sets model is rejected, and
    requests on every socket keep the model field they were sent with. The
    recorder holds no default-model knowledge of its own, so there is nothing
    to fall back to. Without the stream upstream's key the permitted set is
    empty regardless of the lists.
    """
    if not stream_credential_present():
        return []
    merged = []
    for item in _split_models("STREAM_MODEL_ALLOW_TEXT") + _split_models(
        "STREAM_MODEL_ALLOW_VISION"
    ):
        if item not in merged:
            merged.append(item)
    return merged


def model_catalog():
    """The models.json entries: each permitted model, marked with whether it
    accepts image content in messages (membership in the vision list)."""
    vision = _split_models("STREAM_MODEL_ALLOW_VISION")
    return [{"id": item, "image_input": item in vision} for item in permitted_models()]


def stream_limit_max():
    """The operator ceiling on any stream's hourly allowance, from the environment."""
    raw = os.environ.get("STREAM_HOURLY_MAX", "").strip()
    if not raw:
        return STREAM_LIMIT_MAX
    try:
        return max(0, int(raw))
    except ValueError:
        return STREAM_LIMIT_MAX


def stream_token_limit_max():
    """The operator ceiling on any stream's hourly token allowance, from the environment."""
    raw = os.environ.get("STREAM_TOKEN_HOURLY_MAX", "").strip()
    if not raw:
        return STREAM_TOKEN_LIMIT_MAX
    try:
        return max(0, int(raw))
    except ValueError:
        return STREAM_TOKEN_LIMIT_MAX


def global_token_limit_max():
    """The operator ceiling on tokens spent across all declared sockets per clock hour.

    One pool over every declared socket together, whatever names they carry,
    so the namespace cannot multiply the per-stream allowances. The window is
    the clock hour: the pool empties at the top of each hour rather than
    rolling. core.sock is outside it.
    """
    raw = os.environ.get("STREAM_TOKEN_GLOBAL_HOURLY_MAX", "").strip()
    if not raw:
        return STREAM_TOKEN_GLOBAL_LIMIT_MAX
    try:
        return max(0, int(raw))
    except ValueError:
        return STREAM_TOKEN_GLOBAL_LIMIT_MAX


def shared_limited_message(allowance, now, window=BUDGET_WINDOW):
    """The refusal sentence for a spent shared pool, with the time to the hour."""
    remaining = max(0, math.ceil(window - (now % window)))
    return (
        f"rate limited: at most {allowance} token(s) per hour across the declared sockets"
        f"; next available in {remaining} seconds"
    )


def effective_allowance(settings):
    """The allowance actually enforced: the declared budget clamped by the ceiling."""
    return min(settings.get("budget", DEFAULT_STREAM_BUDGET), stream_limit_max())


def effective_token_allowance(settings):
    """The token allowance actually enforced: the declared budget clamped by the ceiling.

    An undeclared token_budget is the ceiling itself, so a declaration lowers
    the allowance and never raises it.
    """
    ceiling = stream_token_limit_max()
    return min(settings.get("token_budget", ceiling), ceiling)


def budget_status(history, now, window=BUDGET_WINDOW):
    """Use of a stream's allowance over the window.

    The history is pruned here rather than trusted, so a stream that went
    quiet reports its true in-window use.
    """
    recent = [t for t in history if now - t < window]
    if not recent:
        return {"used": 0, "window_seconds": window, "oldest_expires_in_seconds": None}
    expires = max(0, math.ceil(window - (now - min(recent))))
    return {"used": len(recent), "window_seconds": window, "oldest_expires_in_seconds": expires}


def check_budget(history, now, allowance, window=BUDGET_WINDOW):
    """Rolling-window check. Returns (allowed, new_history).

    Drops entries older than the window; allows when fewer than allowance
    remain, appending now when allowed.
    """
    recent = [t for t in history if now - t < window]
    if len(recent) >= allowance:
        return False, recent
    recent.append(now)
    return True, recent


def rate_limited_message(allowance, history, now, window=BUDGET_WINDOW):
    """The refusal sentence, with a countdown when a pruned stamp supplies one."""
    message = f"rate limited: at most {allowance} request(s) per hour on this socket"
    status = budget_status(history, now, window)
    if status["oldest_expires_in_seconds"] is not None:
        message += f"; next available in {status['oldest_expires_in_seconds']} seconds"
    return message


def token_status(history, now, window=BUDGET_WINDOW):
    """Use of a stream's token allowance over the window.

    The history is (timestamp, tokens, ticket) triples and is pruned here rather
    than
    trusted, so a stream that went quiet reports its true in-window spend.
    """
    recent = [entry for entry in history if now - entry[0] < window]
    if not recent:
        return {"used": 0, "window_seconds": window, "oldest_expires_in_seconds": None}
    expires = max(0, math.ceil(window - (now - min(entry[0] for entry in recent))))
    return {
        "used": sum(entry[1] for entry in recent),
        "window_seconds": window,
        "oldest_expires_in_seconds": expires,
    }


def check_token_budget(history, now, allowance, window=BUDGET_WINDOW):
    """Rolling-window check. Returns (allowed, new_history).

    Drops entries older than the window; allows while the tokens spent inside
    it remain below allowance.
    """
    recent = [entry for entry in history if now - entry[0] < window]
    return sum(entry[1] for entry in recent) < allowance, recent


def estimate_prompt_tokens(body_bytes, divisor=PROMPT_BYTES_PER_TOKEN):
    """A coarse token count for a request body, from its size.

    The recorder holds no tokenizer, and a reservation only has to be a
    defensible upper-bound stand-in until the response reports its usage. Four
    bytes per token is the usual rough ratio for this family of models.
    """
    return max(1, len(body_bytes) // divisor)


def reservation_for(composed_bytes, allowance):
    """The tokens held against a stream's window while one request is in flight.

    A request is admitted before anyone knows what it will spend, so admitting
    on the window alone lets every request in flight see a window none of the
    others has charged yet - and with keep-alive the agent holds many
    connections open at once. The reservation is the prompt estimate plus what
    the response is permitted to be, so concurrent requests contend for the
    same allowance instead of each seeing it empty. It is replaced by the real
    usage when the request settles.

    What the response is permitted to be is read from the composed body, the
    one actually forwarded: its max_tokens, whether declared or the request's
    own, already carrying the reasoning allowance when the composed request
    reasons. A composed body with no max_tokens permits whatever the upstream
    will produce, so it holds the stream's whole hourly allowance.
    """
    reserved = estimate_prompt_tokens(composed_bytes)
    try:
        data = json.loads(composed_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        data = None
    tokens = data.get("max_tokens") if isinstance(data, dict) else None
    if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens > 0:
        return reserved + tokens
    return reserved + allowance


# Structure caps, from the SV workstream (R-B3): (depth, containers, values). A body small in
# bytes can be enormous in structure, and deeper than the parser's recursion allows; the pre-scan
# refuses it before anything parses it.
REQUEST_CAPS = (64, 32_768, 131_072)
RESPONSE_CAPS = (64, 8_192, 32_768)
# Everything but strings: one structural byte, or one run of scalar text. No alternative can
# backtrack, so a search is linear in what it skips.
_STRUCTURE = re.compile(rb'[\[{]|[\]}]|"|[^\s,:\[\]{}"]+')


def _string_end(data, position):
    """The index just past the closing quote of the string whose body starts at position.

    A quote closes the string when the run of backslashes before it is even. Each quote and each
    backslash is looked at once, so the walk is linear; a string that never closes runs to the end.
    """
    while True:
        quote = data.find(b'"', position)
        if quote == -1:
            return len(data)
        run = 0
        back = quote - 1
        while back >= position and data[back] == 0x5C:
            run += 1
            back -= 1
        position = quote + 1
        if run % 2 == 0:
            return position


def _structure(data, caps=None):
    """Walk a JSON-ish body: (depth, containers, values, first cap exceeded).

    A string, escapes and all, is one value, so punctuation inside it is not structure. Nothing is
    validated. With caps, the walk stops at the first cap exceeded. The security review of 91065d6
    found the earlier single-regex form quadratic on strings that cannot close; this one is linear.
    """
    depth = deepest = containers = values = 0
    position = 0
    while True:
        match = _STRUCTURE.search(data, position)
        if match is None:
            break
        token = match.group()
        position = match.end()
        first = token[:1]
        if first in (b"[", b"{"):
            depth += 1
            containers += 1
            values += 1
            deepest = max(deepest, depth)
        elif first in (b"]", b"}"):
            depth = max(0, depth - 1)
            continue
        elif first == b'"':
            values += 1
            position = _string_end(data, position)
        else:
            values += 1
        if caps is not None:
            if deepest > caps[0]:
                return deepest, containers, values, "depth"
            if containers > caps[1]:
                return deepest, containers, values, "containers"
            if values > caps[2]:
                return deepest, containers, values, "values"
    return deepest, containers, values, None


def prescan(data):
    """(max depth, containers, values) of a body, without parsing it."""
    deepest, containers, values, _ = _structure(data)
    return deepest, containers, values


def over_caps(data, caps):
    """The first cap a body exceeds ("depth", "containers", "values"), or None."""
    return _structure(data, caps)[3]


def token_limited_message(allowance, history, now, window=BUDGET_WINDOW):
    """The refusal sentence, with a countdown when a pruned stamp supplies one."""
    message = f"rate limited: at most {allowance} token(s) per hour on this socket"
    status = token_status(history, now, window)
    if status["oldest_expires_in_seconds"] is not None:
        message += f"; next available in {status['oldest_expires_in_seconds']} seconds"
    return message


def reasoning_allowance():
    """The operator's reasoning token allowance, from the environment.

    The upstream counts reasoning tokens inside max_tokens, so a small
    response cap can be consumed entirely by reasoning before any visible
    output. Composition adds this allowance on top of a capped request's
    max_tokens so the cap bounds the response. Zero disables the addition.
    """
    raw = os.environ.get("STREAM_REASONING_ALLOWANCE", "").strip()
    if not raw:
        return DEFAULT_REASONING_ALLOWANCE
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_REASONING_ALLOWANCE


def compose_body(body_bytes, settings, allowance=0):
    """Replace declared fields in a JSON-object request body.

    Returns (composed_bytes, error). Only fields in COMPOSED_FIELDS are
    applied; the budget paces the socket and never enters the body. A body
    that is not a JSON object cannot be composed and is refused.

    When the composed request carries a positive integer max_tokens and its
    reasoning effort is not "none", allowance is added to the forwarded
    max_tokens: the requested value bounds the response rather than being
    shared with reasoning. streams.json continues to report the declared
    value.

    A streamed request additionally asks for its usage in the final event,
    which the upstream omits otherwise, so a stream's token spend is known.
    """
    try:
        data = json.loads(body_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        data = None
    if not isinstance(data, dict):
        return None, "request body is not a json object"
    for field in COMPOSED_FIELDS:
        if field in settings:
            data[field] = settings[field]
    tokens = data.get("max_tokens")
    if (
        allowance
        and isinstance(tokens, int)
        and not isinstance(tokens, bool)
        and tokens >= 1
        and data.get("reasoning_effort") != "none"
    ):
        data["max_tokens"] = tokens + allowance
    if data.get("stream") is True:
        options = data.get("stream_options")
        if not isinstance(options, dict):
            options = {}
        options["include_usage"] = True
        data["stream_options"] = options
    return json.dumps(data).encode("utf-8"), None


README_TEMPLATE = """the sockets in this directory are model endpoints. each accepts POST
/api/v1/chat/completions and nothing else.

core.sock is always present and forwards requests unmodified.

core.sock and the declared sockets are served by different upstream
endpoints: a model identifier accepted on one may not be accepted on the
other.

additional sockets appear when a declaration in %CONSOLE% is
accepted. that file has two fields:
  enable_streams: boolean
  streams: an object mapping a name to its configuration

a declaration is not served unless enable_streams is true.

each accepted declaration is served at <name>.sock. configuration fields:
  budget: integer, requests allowed per hour on that socket
  token_budget: integer, tokens allowed per hour on that socket. a request is
  admitted while the hour's spend is below it; the response that crosses it
  completes. a request in flight counts the most it is permitted to spend
  until its usage is known: its prompt and its max_tokens, or the whole
  hourly allowance when it has no max_tokens. the usage then replaces that
  count, so the hour's spend can go down as well as up.
  model: string
  reasoning_effort: one of none, minimal, low, medium, high
  temperature: number from 0 to 2
  top_p: number from 0 to 1
  max_tokens: positive integer. it bounds the response; reasoning does not
  count against it unless reasoning_effort is none.

the declared sockets also share one token pool across all of them together,
whatever their names: a fixed number of tokens per clock hour, emptied at
the top of each hour rather than rolling. its size, use, and remaining
percentage are published in streams.json as shared_tokens. core.sock is
outside the pool and carries no allowance of any kind.

a name that was served and is no longer declared keeps an entry in
streams.json with the status absent and the time it stopped being served.
the entry names no socket: the socket is gone.

each served socket's entry states model_since, the time its current model
was set, and previous_models, the models that name was served with before
it and when each stopped.

declared values replace the corresponding fields of each request on that
socket. the current sockets, their settings, and their use are in
streams.json. the model identifiers a declaration may set are listed in
models.json; each entry states whether that model accepts image content
in messages.
"""


def readme_text(console_path=None):
    """The socket directory's protocol description, naming the agent's console path.

    Defaults to AGENT_CONSOLE_FILE, which is the single-host path unless the
    operator's compose override gives this recorder its host's own.
    """
    return README_TEMPLATE.replace("%CONSOLE%", console_path or AGENT_CONSOLE_FILE)


README_TEXT = readme_text("/llm/console/console.json")


def render_state(
    accepted,
    rejected,
    histories,
    now,
    streams_enabled,
    console_error=None,
    token_histories=None,
    absent=None,
    models=None,
):
    """The streams.json document describing every socket in the directory.

    A name that has been served and is no longer declared keeps a row stating
    when it went, so a reader sees a departure rather than a hole.
    """
    token_histories = token_histories or {}
    absent = absent or {}
    models = models or {}
    streams = {"core": {"socket": "core.sock", "status": "active"}}
    for name, settings in accepted.items():
        streams[name] = {
            "socket": f"{name}.sock",
            "status": "active",
            "settings": {k: v for k, v in settings.items() if k not in BUDGET_FIELDS},
            "budget": {
                "allowance": effective_allowance(settings),
                **budget_status(histories.get(name, []), now),
            },
            "tokens": {
                "allowance": effective_token_allowance(settings),
                **token_status(token_histories.get(name, []), now),
            },
        }
        record = models.get(name)
        if record is not None:
            streams[name]["model_since"] = int(record["since"])
            streams[name]["previous_models"] = [
                {"model": entry["model"], "until": int(entry["until"])}
                for entry in record["previous"]
            ]
    for name, reason in rejected.items():
        streams[name] = {"status": "rejected", "reason": reason}
    for name, since in absent.items():
        if name not in streams:
            streams[name] = {"status": "absent", "absent_since": int(since)}
    state = {"streams_enabled": streams_enabled, "streams": streams}
    if console_error is not None:
        state["console_error"] = console_error
    return state


def write_state(path, state):
    """Write the state document via a rename, so a reader never sees a torn file."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def write_readme(sock_dir):
    """Write the socket directory's protocol description."""
    with open(os.path.join(sock_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme_text())


def write_models(sock_dir):
    """Write the permitted-model list beside streams.json.

    The document carries the identifiers a declaration may set, each marked
    with whether the model accepts image content in messages. It is
    replaced via a rename, and only when its content differs, so the poll
    loop can call this every cycle: the file exists from startup and changes
    only when the permitted list does. The unchanged path also removes any
    temporary left by a write interrupted before its rename, so no stray
    file persists on the directory. Returns True when a write happened.
    """
    path = os.path.join(sock_dir, "models.json")
    tmp = path + ".tmp"
    document = {"models": model_catalog()}
    try:
        with open(path, "r", encoding="utf-8") as f:
            if json.load(f) == document:
                try:
                    os.remove(tmp)
                except FileNotFoundError:
                    pass
                return False
    except (OSError, ValueError):
        pass
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(document, f, indent=2)
    os.replace(tmp, path)
    return True


class StreamRegistry:
    """The live stream set: settings, rejections, and budget histories.

    Request threads read settings and charge budgets while the poll thread
    applies console changes, so every access holds the lock.
    """

    def __init__(self, clock=time.time):
        self._lock = threading.Lock()
        self._settings = {}
        self._rejected = {}
        self._histories = {}
        self._ticket = 0
        self._token_histories = {}
        self._shared_hour = None
        self._shared_entries = []
        self._absent = {}
        self._models = {}
        self._clock = clock

    def _shared_roll(self, now):
        """Empty the shared pool when the clock hour has turned.

        The pool's window is the clock hour, not a rolling one. A reservation
        in flight across the boundary is simply forgotten with the old hour's
        entries; its settle then finds no entry and changes nothing. Called
        with the lock already held.
        """
        hour = int(now // BUDGET_WINDOW)
        if hour != self._shared_hour:
            self._shared_hour = hour
            self._shared_entries = []

    def _shared_used(self):
        """Tokens held against the shared pool this hour. Lock already held."""
        return sum(spent for _, spent in self._shared_entries)

    def _prune_histories(self, now):
        """Age out spent stamps and forget the streams left with none.

        A name that is no longer declared keeps its charge until its stamps
        leave the window, so removing a stream from the agent-writable console
        and declaring it again does not buy a second allowance inside the same
        hour. The request and token windows are pruned independently: a stream
        may have spent tokens in an hour it made few requests, or the reverse.
        Called with the lock already held.
        """
        kept = {}
        for name, history in self._histories.items():
            recent = [t for t in history if now - t < BUDGET_WINDOW]
            if recent or name in self._settings:
                kept[name] = recent
        self._histories = kept
        kept = {}
        for name, history in self._token_histories.items():
            recent = [entry for entry in history if now - entry[0] < BUDGET_WINDOW]
            if recent or name in self._settings:
                kept[name] = recent
        self._token_histories = kept

    def _note_models(self, accepted, now):
        """Record when each name's model was set, and the ones it replaced.

        A response carries nothing that distinguishes one model from another,
        so a name whose model changed is otherwise indistinguishable from one
        that did not.
        """
        for name, settings in accepted.items():
            model = settings.get("model")
            record = self._models.get(name)
            if record is None:
                self._models[name] = {"model": model, "since": now, "previous": []}
            elif record["model"] != model:
                record["previous"].append({"model": record["model"], "until": now})
                del record["previous"][:-MODEL_HISTORY_MAX]
                record["model"] = model
                record["since"] = now
        for name in list(self._models):
            if name not in self._settings and name not in self._absent:
                del self._models[name]

    def _note_absent(self, removed, now):
        """Stamp departed names and forget the oldest beyond ABSENT_MAX.

        A name that is declared or rejected again is no longer a departure.
        """
        for name in removed:
            self._absent[name] = now
        for name in list(self._absent):
            if name in self._settings or name in self._rejected:
                del self._absent[name]
        if len(self._absent) > ABSENT_MAX:
            oldest = sorted(self._absent.items(), key=lambda item: item[1])
            for name, _since in oldest[: len(self._absent) - ABSENT_MAX]:
                del self._absent[name]

    def apply(self, accepted, rejected):
        """Adopt a console evaluation. Returns (added, removed) stream names."""
        with self._lock:
            added = [name for name in accepted if name not in self._settings]
            removed = [name for name in self._settings if name not in accepted]
            self._settings = {name: dict(settings) for name, settings in accepted.items()}
            self._rejected = dict(rejected)
            now = self._clock()
            self._note_absent(removed, now)
            self._note_models(accepted, now)
            self._prune_histories(now)
            return added, removed

    def reject(self, name, reason):
        """Record a stream the poll loop could not serve."""
        with self._lock:
            self._settings.pop(name, None)
            self._rejected[name] = reason
            self._prune_histories(self._clock())

    def admit(self, stream, body):
        """Compose and charge one request. Returns (body, refusal).

        refusal is None when the request may be forwarded, else a
        (status, message) pair. A body that fails composition is refused
        before any budget charge. The token window is read first, so a
        refusal on the hour's spend costs no request, and a stream that has
        exhausted both reports the token ceiling. That window is read before
        the response exists, so a request admitted just under the ceiling
        carries the window over it by its whole spend.
        """
        with self._lock:
            settings = self._settings.get(stream)
            settings = dict(settings) if settings is not None else None
        if settings is None:
            return body, (503, "stream not available"), None
        composed, error = compose_body(body, settings, reasoning_allowance())
        if error is not None:
            return body, (400, error), None
        allowance = effective_allowance(settings)
        token_allowance = effective_token_allowance(settings)
        reserved = reservation_for(composed, token_allowance)
        with self._lock:
            now = self._clock()
            tokens = self._token_histories.get(stream, [])
            allowed, tokens = check_token_budget(tokens, now, token_allowance)
            self._token_histories[stream] = tokens
            if not allowed:
                return body, (429, token_limited_message(token_allowance, tokens, now)), None
            self._shared_roll(now)
            shared_allowance = global_token_limit_max()
            if self._shared_used() >= shared_allowance:
                return body, (429, shared_limited_message(shared_allowance, now)), None
            history = self._histories.get(stream, [])
            allowed, history = check_budget(history, now, allowance)
            self._histories[stream] = history
            if not allowed:
                return body, (429, rate_limited_message(allowance, history, now)), None
            self._ticket += 1
            ticket = self._ticket
            tokens.append((now, reserved, ticket))
            self._shared_entries.append((ticket, reserved))
        return composed, None, ticket

    def settle(self, stream, ticket, tokens):
        """Replace a request's reservation with what it actually spent.

        tokens of None leaves the reservation standing, which is what a
        streamed response reports when its usage event never arrives - a
        client that disconnected, or an upstream that faulted. Charging zero
        there would make truncation a way to spend without being metered.
        """
        if ticket is None:
            return
        if isinstance(tokens, bool) or not isinstance(tokens, (int, float)) or tokens < 0:
            return
        tokens = int(tokens)
        with self._lock:
            self._shared_roll(self._clock())
            self._shared_entries = [
                (held, tokens if held == ticket else spent) for held, spent in self._shared_entries
            ]
            history = self._token_histories.get(stream)
            if not history:
                return
            self._token_histories[stream] = [
                (stamp, tokens, held) if held == ticket else (stamp, spent, held)
                for stamp, spent, held in history
            ]

    def cancel(self, stream, ticket):
        """Refund a request that never reached the upstream: its reservation and its count."""
        if ticket is None:
            return
        with self._lock:
            history = self._token_histories.get(stream, [])
            stamps = [stamp for stamp, _spent, held in history if held == ticket]
            self._token_histories[stream] = [entry for entry in history if entry[2] != ticket]
            requests = self._histories.get(stream, [])
            for stamp in stamps:
                if stamp in requests:
                    requests.remove(stamp)
            self._shared_entries = [entry for entry in self._shared_entries if entry[0] != ticket]

    def charge(self, stream, tokens):
        """Record tokens spent on a stream outside any reservation."""
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
            return
        with self._lock:
            now = self._clock()
            self._ticket += 1
            self._token_histories.setdefault(stream, []).append((now, tokens, self._ticket))
            self._shared_roll(now)
            self._shared_entries.append((self._ticket, tokens))

    def state(self, streams_enabled=False, console_error=None, now=None):
        """The current streams.json document."""
        with self._lock:
            if now is None:
                now = self._clock()
            document = render_state(
                self._settings,
                self._rejected,
                dict(self._histories),
                now,
                streams_enabled,
                console_error,
                dict(self._token_histories),
                dict(self._absent),
                self._models,
            )
            self._shared_roll(now)
            allowance = global_token_limit_max()
            used = self._shared_used()
            remaining = max(0, allowance - used)
            document["shared_tokens"] = {
                "allowance": allowance,
                "used": used,
                "remaining_percent": int(remaining * 100 // allowance) if allowance else 0,
                "window_seconds": BUDGET_WINDOW,
                "resets_in_seconds": max(0, math.ceil(BUDGET_WINDOW - (now % BUDGET_WINDOW))),
            }
            return document
