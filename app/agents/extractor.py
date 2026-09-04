"""Agent 1: pulls structured key terms out of the raw deal document text."""

from __future__ import annotations

from app.agents._llm_utils import structured_call_with_retry
from app.agents.prompts import EXTRACTOR_SYSTEM_PROMPT
from app.config import get_llm
from app.observability import node_span, trace
from app.state import DealReviewState, ExtractedTerms

# Task prompt: per-call instructions + the document itself. The agent's
# persistent identity and guardrails (never invent a value, ignore embedded
# instructions, etc.) live in EXTRACTOR_SYSTEM_PROMPT instead, so they don't
# have to be repeated here and can't drift out of sync with the other agents.
PROMPT_TEMPLATE = """Extract the fields precisely as they appear in the document below. For
key_clauses, list every notable clause type present (e.g. arbitration, indemnification,
termination, cancellation, non-renewal, confidentiality, limitation of liability) using the same
terminology the document uses, even if it appears deep in a "dispute resolution" or
similarly-named section.

DOCUMENT:
---
{document}
---
"""


def extractor_agent(state: DealReviewState) -> DealReviewState:
    deal_id = state.deal_id
    with node_span(deal_id, "extractor_agent") as span:
        llm = get_llm()
        prompt = PROMPT_TEMPLATE.format(document=state.raw_text)
        result, retries = structured_call_with_retry(
            llm, ExtractedTerms, prompt, deal_id, "extractor_agent",
            system_prompt=EXTRACTOR_SYSTEM_PROMPT,
        )
        span["retries"] = retries

        if result is None:
            state.errors.append("extractor_agent: failed to extract structured terms after retry.")
            state.needs_manual_review = True
            trace(deal_id, "extractor_fallback", reason="structured_output_failed")
            return state

        state.extracted_terms = result
        return state
