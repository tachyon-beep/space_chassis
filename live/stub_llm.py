"""A stand-in model for the smoke stack: Aurora's stub (42faf41), plus cues.

Serves POST */chat/completions with a non-streaming chat completion. Almost every reply is a
tool call (list_dir), so the harness keeps looping instead of ending after one turn. Every
TURNS_PER_INCARNATION requests from one client address, the reply carries no tool call instead,
which ends that incarnation cleanly (the chassis exits 0). With a REPLY_DELAY_SECONDS of 2 and 40
turns an incarnation lasts about 85 seconds, so no more than two clean exits ever share the
watchdog's 120-second flap window: an idle agent never walks the recovery ladder by accident.

Each recorder is its own container with its own address on the model network, so turns are
counted per client address, which here means per agent.

The addition is cues. With CUE_DIR set, before answering a client at address A the stub looks
for CUE_DIR/A.json. If it is there, the stub claims it by renaming it A.json.served and answers
with exactly what it names: {"name": <tool>, "arguments": <object>} becomes that tool call (its
arguments a JSON string, as a model sends them), and {"stop": true} becomes a plain stop. A cue
that does not parse is answered with a 500 and renamed A.json.bad. A cue wins over the Nth-turn
stop, which then moves to that client's next request. The smoke tests use cues to have an agent
call run, done or reset, which no model would do on demand.

Not copied into any image; mounted read-only into the smoke stack's stub service only.
"""

import itertools
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("VERIFY_STUB_PORT", "8199"))
REPLY_DELAY_SECONDS = float(os.environ.get("VERIFY_STUB_DELAY_SECONDS", "2.0"))
TURNS_PER_INCARNATION = int(os.environ.get("VERIFY_STUB_TURNS_PER_INCARNATION", "40"))
CUE_DIR = os.environ.get("STUB_CUE_DIR", "")

_reply_ids = itertools.count(1)
_call_ids = itertools.count(1)
_turns_by_client: dict[str, int] = {}
_stop_owed: set[str] = set()
_turns_lock = threading.Lock()


class BadCue(ValueError):
    pass


def _next_turn(client: str) -> int:
    """Count one completion request from client and return its number."""
    with _turns_lock:
        turn = _turns_by_client.get(client, 0) + 1
        _turns_by_client[client] = turn
        return turn


def _claim_cue(client: str):
    """The client's cue, claimed by renaming it, or None. Raises BadCue for one that won't parse."""
    if not CUE_DIR:
        return None
    path = os.path.join(CUE_DIR, f"{client}.json")
    claimed = path + ".served"
    try:
        os.replace(path, claimed)
    except FileNotFoundError:
        return None
    try:
        with open(claimed, encoding="utf-8") as handle:
            cue = json.load(handle)
        if cue.get("stop") is True:
            return cue
        if not isinstance(cue.get("name"), str) or not isinstance(cue.get("arguments"), dict):
            raise ValueError("a cue is {name, arguments} or {stop: true}")
        return cue
    except (OSError, ValueError, AttributeError) as error:
        os.replace(claimed, path + ".bad")
        raise BadCue(str(error)) from error


def _tool_call(name: str, arguments: dict) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call_stub_{next(_call_ids)}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


STOP = {"role": "assistant", "content": "stub pausing this incarnation."}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A002 - stdlib override
        sys.stderr.write("stub_llm: " + (fmt % args) + "\n")

    def _send(self, status: int, reply: dict | None) -> None:
        payload = json.dumps(reply).encode("utf-8") if reply is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):  # noqa: N802 - stdlib override
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        try:
            request = json.loads(body or b"{}")
        except json.JSONDecodeError:
            request = {}

        if not self.path.endswith("/chat/completions"):
            self._send(404, None)
            return

        client = self.client_address[0]
        try:
            cue = _claim_cue(client)
        except BadCue as error:
            self._send(500, {"error": {"message": f"bad cue: {error}"}})
            return

        time.sleep(REPLY_DELAY_SECONDS)

        n = _next_turn(client)
        due = bool(TURNS_PER_INCARNATION) and n % TURNS_PER_INCARNATION == 0
        if cue is not None:
            if due:
                _stop_owed.add(client)
            message = STOP if cue.get("stop") else _tool_call(cue["name"], cue["arguments"])
        elif due or client in _stop_owed:
            _stop_owed.discard(client)
            message = STOP
        else:
            message = _tool_call("list_dir", {"path": "."})

        self._send(
            200,
            {
                "id": f"chatcmpl-{next(_reply_ids)}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": request.get("model") or "stub-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls" if "tool_calls" in message else "stop",
                        "message": message,
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    def do_GET(self):  # noqa: N802 - stdlib override
        # The readiness probe.
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


def make_server(host: str = "0.0.0.0", port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main():
    make_server().serve_forever()


if __name__ == "__main__":
    main()
