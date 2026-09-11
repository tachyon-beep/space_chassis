#!/usr/bin/env python3
"""A model that answers on cue, for endurance runs and for tests.

The point of an endurance run is to exercise the world -- the recorder, the
supervisor's ladder, the window, the pump, the record -- over a span of
simulated time that would otherwise take months. A real model makes that
impossible: every run would cost money, take wall-clock time, and answer
differently each time.

So this stands in for one. It is OpenAI-compatible on the surface and
deliberately dumb underneath: it picks its next reply from a script by counting
the assistant turns already in the conversation, so the same scenario produces
the same run every time.

Three things it can do that a real model cannot:

* **answer in microseconds**, so a scenario of thousands of turns is minutes of
  wall clock rather than weeks;
* **fail on cue**, from a seeded plan, so the supervisor's ladder is exercised
  by transient errors, malformed bodies, a missing model, and a spent balance
  rather than by waiting for one to happen;
* **refuse to be spoken for**, because it never sees the mission.

It is not a model and must never be mistaken for one: no scenario here proves
anything about how a real model would fly the vehicle. What it proves is that
the machinery around one survives being run hard.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import random
import socketserver
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


# ---------------------------------------------------------------------------
# Replies
# ---------------------------------------------------------------------------
@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)

    def wire(self) -> dict:
        return {
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {"name": self.name, "arguments": json.dumps(self.arguments)},
        }


@dataclass
class Reply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish: str = "stop"
    #: How many times this reply may be given before the script moves on. Zero
    #: means the script moves on immediately after giving it once.
    repeat: int = 1

    def to_message(self, model: str) -> dict:
        message: dict = {"role": "assistant", "content": self.text or None}
        if self.tool_calls:
            message["content"] = self.text or None
            message["tool_calls"] = [call.wire() for call in self.tool_calls]
            message["finish_reason"] = "tool_calls"
        return message


def default_script() -> list[Reply]:
    """A short life: look around, record something, leave a note.

    Every tool name here belongs to the seed duty. A scenario that wants to
    exercise a fleet that has rewritten itself supplies its own script.
    """
    return [
        Reply(tool_calls=[ToolCall("status")]),
        Reply(tool_calls=[ToolCall("list_dir", {"path": "/brief"})]),
        Reply(tool_calls=[ToolCall("read_file", {"path": "/brief/MISSION.md", "max_lines": 40})]),
        Reply(
            tool_calls=[
                ToolCall("write_diary", {"entry": "A stub model is flying; noted for the record."})
            ]
        ),
        Reply(
            tool_calls=[
                ToolCall(
                    "handoff",
                    {
                        "note": "Stub script finished. Nothing was decided, because a stub cannot decide."
                    },
                )
            ]
        ),
    ]


TOOL_NAMES = {
    "status",
    "read_file",
    "write_file",
    "edit_file",
    "list_dir",
    "run",
    "spawn",
    "schedule",
    "unschedule",
    "diode",
    "diode_state",
    "diode_results",
    "write_diary",
    "read_diary",
    "handoff",
    "finish",
}


def script_from_file(path: Path) -> list[Reply]:
    """Load a scenario's reply script from JSON.

    Shape: a list of objects with `text`, `tool_calls` (name/arguments),
    `finish`, and `repeat`. Unknown tool names are refused here rather than
    being sent to a duty that would answer "no such tool": a typo in a scenario
    should fail the scenario, not become a turn that looks like the fleet
    behaving oddly.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit(f"{path}: the script must be a list of replies")
    script: list[Reply] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SystemExit(f"{path}: reply {index} is not an object")
        calls = []
        for call in item.get("tool_calls", []) or []:
            if not isinstance(call, dict) or "name" not in call:
                raise SystemExit(f"{path}: reply {index} has a malformed tool_call")
            name = str(call["name"])
            if name not in TOOL_NAMES:
                raise SystemExit(f"{path}: reply {index} calls unknown tool {name!r}")
            calls.append(ToolCall(name, call.get("arguments") or {}))
        script.append(
            Reply(
                text=str(item.get("text", "")),
                tool_calls=calls,
                finish=str(item.get("finish", "stop")),
                repeat=int(item.get("repeat", 1)),
            )
        )
    if not script:
        raise SystemExit(f"{path}: the script is empty")
    return script


# ---------------------------------------------------------------------------
# Faults
# ---------------------------------------------------------------------------
@dataclass
class Faults:
    """A seeded plan of things going wrong.

    Rates are per request. `hang_seconds` is the one that matters most for a
    supervisor test: a request that never returns is how a run becomes alive
    and useless rather than crashed and obvious.
    """

    transient_every: int = 0
    malformed_every: int = 0
    no_model_every: int = 0
    exhausted_every: int = 0
    hang_every: int = 0
    hang_seconds: float = 900.0
    seed: int = 1

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def fault_for(self, request_index: int) -> str | None:
        if self.transient_every and request_index % self.transient_every == 0:
            return "transient"
        if self.malformed_every and request_index % self.malformed_every == 0:
            return "malformed"
        if self.no_model_every and request_index % self.no_model_every == 0:
            return "no_model"
        if self.exhausted_every and request_index % self.exhausted_every == 0:
            return "exhausted"
        if self.hang_every and request_index % self.hang_every == 0:
            return "hang"
        return None


# ---------------------------------------------------------------------------
# The server
# ---------------------------------------------------------------------------
class Stub:
    def __init__(
        self,
        script: list[Reply] | None = None,
        faults: Faults | None = None,
        model_name: str = "stub",
        time_scale: float = 1.0,
        think_seconds: float = 0.0,
        journal: Path | None = None,
        ending: bool = False,
    ) -> None:
        self.script = script or default_script()
        self.faults = faults or Faults()
        self.model_name = model_name
        self.time_scale = max(0.0, time_scale)
        self.think_seconds = think_seconds
        self.journal = journal
        # Whether to close a run once the script is spent. A scenario that is
        # testing the *ladder* wants a run to end so the next one starts and the
        # rungs get exercised; a scenario testing the window wants a run to keep
        # going. Both are legitimate, so it is a scenario's choice.
        self.ending = ending
        self.requests = 0
        self.turns = 0
        self.faults_seen: dict[str, int] = {}
        self._lock = threading.Lock()

    # -- choosing a reply ---------------------------------------------------
    def reply_for(self, messages: list[dict]) -> Reply:
        """Pick the next reply by counting the assistant turns already present.

        Counting what is in the conversation rather than tracking a cursor is
        what makes the stub stateless with respect to retries: a resent request
        gets the same answer, which is the behaviour a recorder or a supervisor
        test needs.
        """
        # The script advances on the last assistant turn it was given, not on
        # the number of assistant turns present. Counting turns cannot advance
        # when the script repeats a reply with no tool calls -- the turn is
        # appended, the count goes up, and the same index is chosen again, so a
        # scenario whose script is one looping reply loops forever.
        assistant_turns = sum(1 for message in messages if message.get("role") == "assistant")
        index = max(0, assistant_turns - 1)
        remaining = index
        for reply in self.script:
            span = max(1, reply.repeat)
            if remaining < span:
                return reply
            remaining -= span
        # Past the end of the script the stub never invents a next step -- that
        # would be the harness making the fleet's decisions for it -- and never
        # repeats the last one, because that would spin a run until a budget
        # killed it and turn every scenario into the same scenario.
        if self.ending:
            # A metronome that knows when to stop: it closes the run, which is
            # what the duty's own handoff tool does, so the ladder's
            # designed-end path is exercised rather than simulated.
            return Reply(
                text="Script spent.",
                tool_calls=[
                    ToolCall(
                        "handoff",
                        {
                            "note": (
                                "The stub model's script is spent, so this run was closed on "
                                "purpose rather than left spinning. A real model would keep "
                                "going until something it decided."
                            )
                        },
                    )
                ],
            )
        # Otherwise: nothing to say, which the duty treats as the end of a run.
        return Reply(text="", finish="stop")

    def record(self, kind: str, **fields) -> None:
        if self.journal is None:
            return
        with (
            contextlib.suppress(OSError),
            open(self.journal, "a", encoding="utf-8") as handle,
        ):
            handle.write(json.dumps({"at": time.time(), "kind": kind, **fields}) + "\n")

    # -- the request --------------------------------------------------------
    def handle(self, body: bytes) -> tuple[int, bytes, float]:
        with self._lock:
            self.requests += 1
            request_index = self.requests
        fault = self.faults.fault_for(request_index)
        if fault:
            with self._lock:
                self.faults_seen[fault] = self.faults_seen.get(fault, 0) + 1
            self.record("fault", fault=fault, index=request_index)
            if fault == "transient":
                return (
                    429,
                    json.dumps({"error": {"message": "temporary overload, retry"}}).encode(),
                    0.0,
                )
            if fault == "malformed":
                return 200, b'{"choices": [{"message": {"role": "assist', 0.0
            if fault == "no_model":
                return (
                    404,
                    json.dumps(
                        {"error": {"message": f"model {self.model_name} not found"}}
                    ).encode(),
                    0.0,
                )
            if fault == "exhausted":
                return (
                    402,
                    json.dumps(
                        {"error": {"message": "insufficient credits to run this request"}}
                    ).encode(),
                    0.0,
                )
            if fault == "hang":
                time.sleep(self.faults.hang_seconds)
                return 504, json.dumps({"error": {"message": "gave up waiting"}}).encode(), 0.0

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 400, json.dumps({"error": {"message": "body was not json"}}).encode(), 0.0
        messages = payload.get("messages") if isinstance(payload, dict) else None
        if not isinstance(messages, list):
            return 400, json.dumps({"error": {"message": "messages must be a list"}}).encode(), 0.0

        reply = self.reply_for(messages)
        delay = self.think_seconds
        if self.time_scale and self.time_scale != 1.0:
            delay = self.think_seconds * self.time_scale
        if delay:
            time.sleep(delay)

        prompt_tokens = max(1, len(body) // 4)
        completion_text = reply.text or json.dumps([call.name for call in reply.tool_calls])
        completion_tokens = max(1, len(completion_text) // 4)
        message = reply.to_message(self.model_name)
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"

        if payload.get("stream"):
            with self._lock:
                self.turns += 1
            chunks = [
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": self.model_name,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": reply.text or ""},
                            "finish_reason": None,
                        }
                    ],
                },
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": self.model_name,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": reply.finish}],
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    },
                },
            ]
            body_out = (
                "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
            )
            self.record("turn", index=request_index, tools=[c.name for c in reply.tool_calls])
            return 200, body_out.encode(), delay

        completion = {
            "id": completion_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.model_name,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": "tool_calls" if reply.tool_calls else reply.finish,
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
        with self._lock:
            self.turns += 1
        self.record("turn", index=request_index, tools=[c.name for c in reply.tool_calls])
        return 200, json.dumps(completion).encode(), delay


def make_handler(stub: Stub):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "stub-model/0.1"

        def log_message(self, fmt, *args):  # noqa: A003 -- base class API
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

        def do_GET(self):  # noqa: N802 -- base class API
            if self.path == "/stats":
                stats = {
                    "requests": stub.requests,
                    "turns": stub.turns,
                    "faults": stub.faults_seen,
                }
                self._send(200, json.dumps(stats).encode())
                return
            self._send(404, b'{"error": {"message": "no such route"}}')

        def do_POST(self):  # noqa: N802 -- base class API
            if not self.path.endswith("/chat/completions"):
                self._send(404, b'{"error": {"message": "the only route is chat/completions"}}')
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            status, payload, _delay = stub.handle(body)
            self._send(status, payload)

    return Handler


class StubServer:
    """A stub model on a TCP port or a unix socket."""

    def __init__(
        self, stub: Stub, socket_path: Path | None = None, port: int = 0, host: str = "127.0.0.1"
    ) -> None:
        self.stub = stub
        handler = make_handler(stub)
        if socket_path is not None:
            socket_path = Path(socket_path)
            socket_path.parent.mkdir(parents=True, exist_ok=True)
            with contextlib.suppress(FileNotFoundError):
                socket_path.unlink()

            class UnixServer(ThreadingHTTPServer):
                address_family = __import__("socket").AF_UNIX
                daemon_threads = True
                allow_reuse_address = False

                def server_bind(self):
                    # The base class looks up the bind address's canonical host
                    # name to fill in `server_name`, and for an AF_UNIX address
                    # that is the socket's path: a reverse lookup that can stall
                    # and, on a host with a slow resolver, raise. Both are
                    # avoided by stating the name, which nothing here reads.
                    self.server_name = "stub-model"
                    self.server_port = 0
                    socketserver.UnixStreamServer.server_bind(self)
                    os.chmod(self.server_address, 0o666)

                def get_request(self):
                    conn, _ = self.socket.accept()
                    return conn, ("unix", 0)

            self.httpd = UnixServer(str(socket_path), handler)
            self.url = "http://localhost"
            self.socket_path = socket_path
        else:
            self.httpd = ThreadingHTTPServer((host, port), handler)
            self.httpd.daemon_threads = True
            host, bound = self.httpd.server_address[:2]
            self.url = f"http://{host}:{bound}"
            self.socket_path = None
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self) -> StubServer:
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.socket_path is not None:
            with contextlib.suppress(FileNotFoundError):
                self.socket_path.unlink()

    def __enter__(self) -> StubServer:
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()


def faults_from_env() -> Faults:
    def number(name: str, default: float = 0.0) -> float:
        raw = (os.environ.get(name) or "").strip()
        try:
            return float(raw) if raw else default
        except ValueError:
            return default

    def whole(name: str, default: int = 0) -> int:
        return int(number(name, default))

    return Faults(
        transient_every=whole("STUB_TRANSIENT_EVERY"),
        malformed_every=whole("STUB_MALFORMED_EVERY"),
        no_model_every=whole("STUB_NO_MODEL_EVERY"),
        exhausted_every=whole("STUB_EXHAUSTED_EVERY"),
        hang_every=whole("STUB_HANG_EVERY"),
        hang_seconds=number("STUB_HANG_SECONDS", 900.0),
        seed=whole("STUB_SEED", 1),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A model that answers on cue.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("STUB_PORT", "11434")))
    parser.add_argument(
        "--host",
        default=os.environ.get("STUB_HOST", "127.0.0.1"),
        help="bind address; use 0.0.0.0 to be reachable from another container",
    )
    parser.add_argument("--unix", type=Path, help="serve on a unix socket instead of a port")
    parser.add_argument("--script", type=Path, help="a json reply script")
    parser.add_argument("--journal", type=Path, help="append one line per request here")
    parser.add_argument(
        "--time-scale", type=float, default=float(os.environ.get("STUB_TIME_SCALE", "1"))
    )
    parser.add_argument("--think-seconds", type=float, default=0.0)
    parser.add_argument(
        "--ending",
        action="store_true",
        help="close a run once the script is spent, instead of falling silent",
    )
    args = parser.parse_args(argv)

    script = script_from_file(args.script) if args.script else default_script()
    stub = Stub(
        script=script,
        faults=faults_from_env(),
        time_scale=args.time_scale,
        think_seconds=args.think_seconds,
        journal=args.journal,
        ending=args.ending,
    )
    server = StubServer(stub, socket_path=args.unix, port=args.port, host=args.host).start()
    print(
        f"[stub-model] {server.url} ({len(script)} replies) — not a model, a metronome", flush=True
    )
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
