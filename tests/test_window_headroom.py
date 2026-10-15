"""The conversation window leaves room for the tools and a full reply on the default model.

The chassis's window counts messages only: the tool schemas and the model's reply sit outside it,
and a request past the model's context is a 400 that the chassis repairs once, at the same budget,
and then ends as exit 43 with a fresh conversation (3c98f068b5, 8da4399e69). This is a tripwire on
the shipped default, not a check of a deployment: a host given a smaller model in `.env` (where
`HOSTn_CONTEXT_WINDOW_TOKENS` lowers its window) is the operator's to fit, by the rule
`.env.example` states.

The default model's figures are OpenRouter's public /api/v1/models for `deepseek/deepseek-v4-pro`
on 2026-10-09: context 1,048,576, 1,024,000 at the top provider, and a completion ceiling of
384,000. chars/4 undercounts JSON-heavy content, hence the 1.25 margin.
"""

import re
import subprocess
import sys
from pathlib import Path

import compose_text

ROOT = Path(__file__).resolve().parent.parent
MODEL_CONTEXT = 1_024_000
MODEL_MAX_REPLY = 384_000
ESTIMATOR_MARGIN = 1.25


def _default_window() -> int:
    services = compose_text.services((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    value = services["agent_1"]["environment"]["CONTEXT_WINDOW_TOKENS"]
    # `${HOST1_CONTEXT_WINDOW_TOKENS:-${CONTEXT_WINDOW_TOKENS:-200000}}`: the innermost default.
    match = re.search(r":-(\d+)\}+$", value)
    assert match, value
    return int(match[1])


def _schema_tokens() -> int:
    result = subprocess.run(
        [sys.executable, "-c", "import agent, json; print(len(json.dumps(agent.tools.schemas)))"],
        cwd=ROOT / "harness",
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return int(result.stdout.strip()) // 4


def test_the_default_window_leaves_room_for_the_tools_and_a_full_reply_on_the_default_model():
    window = _default_window()
    schemas = _schema_tokens()
    assert schemas > 0
    assert ESTIMATOR_MARGIN * (window + schemas) + MODEL_MAX_REPLY <= MODEL_CONTEXT, (
        window,
        schemas,
    )
