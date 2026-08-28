"""Agent 1: pulls structured key terms out of the raw deal document text."""

from __future__ import annotations

from app.agents._llm_utils import structured_call_with_retry
from app.config import get_llm
from app.observability import node_span, trace
from app.state import DealReviewState, ExtractedTerms

PROMPT_TEMPLATE = """You are a contract analyst extracting structured terms from a deal document.
Read the document below and extract the fields precisely as they appear. If a field is not
present in the document, leave it null/empty -- never invent a value. For key_clauses, list
every notable clause type present (e.g. arbitration, indemnification, termination, cancellation,
non-renewal, confidentiality, limitation of liability) using the same terminology the document
uses, even if it appears deep in a "dispute resolution" or similarly-named section.

DOCUMENT:
---
{document}
---
"""


def extractor_agent(state: DealReviewState) -> DealReviewState:
    deal_id = state.file_path
    with node_span(deal_id, "extractor_agent") as span:
        llm = get_llm()
        prompt = PROMPT_TEMPLATE.format(document=state.raw_text)
        result, retries = structured_call_with_retry(
            llm, ExtractedTerms, prompt, deal_id, "extractor_agent"
        )
        span["retries"] = retries

        if result is None:
            state.errors.append("extractor_agent: failed to extract structured terms after retry.")
            state.needs_manual_review = True
            trace(deal_id, "extractor_fallback", reason="structured_output_failed")
            return state

        state.extracted_terms = result
        return state
