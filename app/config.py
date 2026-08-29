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
    return ChatAnthropic(model=ANTHROPIC_MODEL)
