"""Shared helper for resilient structured LLM calls.

Failure policy (per FRAMEWORK.md): a structured call gets one retry with a
stricter/repair prompt. If it still fails, the caller gets None back and is
responsible for marking that section `needs_manual_review` rather than
crashing the whole pipeline run.
"""

from __future__ import annotations

from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.observability import trace

T = TypeVar("T", bound=BaseModel)


def structured_call_with_retry(
    llm,
    schema: type[T],
    prompt: str,
    deal_id: str,
    node_name: str,
    system_prompt: str | None = None,
    max_retries: int = 1,
) -> tuple[T | None, int]:
    """Returns (result_or_None, retries_used).

    `system_prompt`, when given (see app/agents/prompts.py), carries the
    agent's persistent identity/guardrails and is sent on every attempt,
    including retries -- it's the task prompt that gets a repair note
    appended, not the system prompt.
    """
    structured_llm = llm.with_structured_output(schema)
    attempt_prompt = prompt

    for attempt in range(max_retries + 1):
        try:
            messages = (
                [SystemMessage(content=system_prompt), HumanMessage(content=attempt_prompt)]
                if system_prompt
                else attempt_prompt
            )
            result = structured_llm.invoke(messages)
            return result, attempt
        except Exception as exc:  # noqa: BLE001 - LLM/parsing failures of any kind
            trace(deal_id, "llm_call_failed", node=node_name, attempt=attempt, error=str(exc))
            attempt_prompt = (
                prompt
                + "\n\nIMPORTANT: Your previous response could not be parsed into the "
                "required structured format. Respond with ONLY the fields requested, "
                "using your best interpretation of the document -- do not add commentary."
            )

    return None, max_retries + 1
