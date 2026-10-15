"""Build the LLM console seed copied into the agent image.

Ported from Aurora (42faf41); its .env reading now comes from scripts/env_file.py.

The seed declares one stream per model the operator permits. The allow lists
are environment, the seed is a file, and a hand-kept file drifts from them
silently: a declaration naming a model the recorder does not permit is rejected
with "model not permitted" and its socket simply never appears. Generating the
seed from the same lists the recorder reads removes that class of mismatch.
"""

import argparse
import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from env_file import env_value, source_path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = REPO_ROOT / "llm_console_seed.json"

ALLOW_TEXT = "STREAM_MODEL_ALLOW_TEXT"
ALLOW_VISION = "STREAM_MODEL_ALLOW_VISION"

# recorder_streams.MAX_STREAMS: evaluate_console walks declarations in file
# order and rejects everything past it.
MAX_STREAMS = 8

# A declared budget only ever lowers: effective_allowance takes the minimum of
# it and the operator ceiling, and the entrypoint seeds the console once and
# never again. A seeded value tracking the current ceiling would therefore
# outlive it and cap a later, higher ceiling; a value at or above the highest
# ceiling the template recommends leaves the ceiling in charge.
TOKEN_BUDGET = 2000000
BUDGET = 1200
MAX_TOKENS = 32768


def split_models(raw: str | None) -> list[str]:
    """Split one allow list the way the recorder splits it."""
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def declarations(text_models: list[str], vision_models: list[str]) -> dict:
    """One declaration per permitted model, named ordinally by modality.

    The two lists are merged the way permitted_models() merges them, so a model
    named in both is one permitted model and gets one socket. Names are ordinal
    rather than model-tier: a tier name bakes a vendor lineup into an
    agent-readable surface and goes stale when a list changes, where an ordinal
    stays accurate and routes to models.json, which publishes each socket's
    model and image_input flag.
    """
    streams = {}
    counts = {"text": 0, "vision": 0}
    seen = set()
    for model in text_models + vision_models:
        if model in seen:
            continue
        seen.add(model)
        modality = "vision" if model in vision_models else "text"
        counts[modality] += 1
        streams[f"{modality}_{counts[modality]}"] = {
            "model": model,
            "token_budget": TOKEN_BUDGET,
            "budget": BUDGET,
            "max_tokens": MAX_TOKENS,
        }
    if len(streams) > MAX_STREAMS:
        raise SystemExit(
            f"{len(streams)} permitted models exceeds the recorder's limit of {MAX_STREAMS} "
            f"streams; shorten {ALLOW_TEXT} or {ALLOW_VISION}"
        )
    return streams


def build(dest: Path | None = None, source: Path | None = None) -> dict:
    """Write the seed for the permitted models and return it.

    The file is replaced atomically so a partially written seed is never copied
    into an image or read by the entrypoint.
    """
    if dest is None:
        dest = DEFAULT_DEST
    if source is None:
        source = source_path()
    seed = {
        "enable_streams": True,
        "streams": declarations(
            split_models(env_value(ALLOW_TEXT, source)),
            split_models(env_value(ALLOW_VISION, source)),
        ),
    }
    text = json.dumps(seed, indent=2) + "\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(dest.parent), prefix=dest.name, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(temporary, 0o644)
        os.replace(temporary, dest)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(temporary)
        raise
    return seed


def main(argv: list[str] | None = None) -> None:
    """Build the default seed.

    --source names the environment file to read instead of .env, or
    .env.example when there is none.
    """
    parser = argparse.ArgumentParser(prog="build_console_seed.py", description=__doc__)
    parser.add_argument("--source", type=Path, help="the environment file to read")
    args = parser.parse_args(argv)
    source = source_path() if args.source is None else args.source
    if not source.is_file():
        raise SystemExit(f"{source}: no such file")
    seed = build(source=source)
    print(f"console seed: {len(seed['streams'])} stream(s) from {source.name} -> {DEFAULT_DEST}")


if __name__ == "__main__":
    main()
