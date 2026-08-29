"""Loads environment config and constructs the shared LLM client."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

# LangSmith tracing turns on automatically via these env vars if set -- no
# extra code required. We just make sure .env is loaded before any LangChain
# import touches the environment.
LANGSMITH_ENABLED = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true" and bool(
    os.getenv("LANGCHAIN_API_KEY")
)


def get_llm() -> ChatAnthropic:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    # Note: this model rejects an explicit `temperature` param ("temperature is
    # deprecated for this model") -- omit it and use the API default rather
    # than forcing temperature=0 for determinism.
    #
    # max_tokens is set explicitly (rather than left at the client default,
    # which is too low for this pipeline's structured outputs) after an
    # extreme-edge-case test document surfaced real truncation: a long
    # source document produces long verbatim evidence quotes in
    # ComplianceFindingsList/RiskFindingsList, and the default cap cut the
    # response off mid-JSON -- a real (if boring) `max_tokens` stop reason,
    # not a hallucination. 4096 covers this pipeline's largest realistic
    # structured output with headroom, without being open-ended enough to
    # waste tokens/cost on runaway generations.
    return ChatAnthropic(model=ANTHROPIC_MODEL, max_tokens=4096)
