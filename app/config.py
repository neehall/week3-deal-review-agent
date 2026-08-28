"""Loads environment config and constructs the shared LLM client."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# LangSmith tracing turns on automatically via these env vars if set -- no
# extra code required. We just make sure .env is loaded before any LangChain
# import touches the environment.
LANGSMITH_ENABLED = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true" and bool(
    os.getenv("LANGCHAIN_API_KEY")
)


def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return ChatOpenAI(model=OPENAI_MODEL, temperature=temperature)
