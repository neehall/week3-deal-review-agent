"""Ragas-based faithfulness check for the deal review pipeline.

This isn't a RAG system in the classic retrieve-then-generate sense --
there's no corpus, no retrieval step. But ragas' Faithfulness metric
doesn't actually require retrieval; it only asks whether every claim in a
piece of generated text traces back to a given context. That maps
directly onto this pipeline's own most-repeated guardrail -- "never
invent a value," "never fabricate a compliance rule that isn't in the
source document" (see FRAMEWORK.md, app/agents/prompts.py) -- by treating
the source deal document as the context and the orchestrator's draft
report as the response, then asking whether every claim in the report is
actually grounded in the document.

This is an independent, standardized cross-check layered on top of the
project's own hand-built validation
(data/sample_deals/ANSWER_KEY.md) -- that answer key checks *compliance
correctness* (did the pipeline catch the planted issues); this checks
*groundedness* (did it invent anything the source document doesn't say).
The two are complementary, not redundant: a report can be perfectly
grounded and still miss an issue, or catch every issue while embellishing
one piece of evidence.

Usage: run the graph as normal to get a completed DealReviewState (raw_text
+ draft_report), then pass both to score_report_faithfulness(). See
scripts/run_ragas_faithfulness.py for scoring the sample deal set.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

from langchain_anthropic import ChatAnthropic

from app.config import ANTHROPIC_MODEL

# ragas.metrics still exposes Faithfulness via this path with a deprecation
# warning as of ragas 0.4.x (see app/agents/prompts.py's sibling note in
# the Week 2 project) -- silenced here rather than left to print on every run.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from ragas import EvaluationDataset, evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness


@dataclass
class FaithfulnessResult:
    deal_id: str
    file_path: str
    faithfulness: float | None  # None if there was nothing to score


def score_report_faithfulness(deal_id: str, file_path: str, raw_text: str, draft_report: str | None) -> FaithfulnessResult:
    """Scores one already-completed run's draft_report for groundedness in raw_text.

    A separate ragas judge call per deal -- not free, but small (one report,
    one document) compared to the pipeline's own 3 agent calls that already
    produced the report being checked.
    """
    if not draft_report or not raw_text:
        return FaithfulnessResult(deal_id, file_path, None)

    dataset = EvaluationDataset.from_list(
        [
            {
                "user_input": "Produce a structured deal review report grounded only in this document.",
                "response": draft_report,
                "retrieved_contexts": [raw_text],
            }
        ]
    )
    # A dedicated client, not app.config.get_llm() -- three fixes were
    # needed before this actually produced a score instead of an
    # exception, each confirmed by hitting it for real:
    #   1. max_tokens=8192, not get_llm()'s 4096. Faithfulness is itself
    #      multi-step (decomposes the response into atomic statements,
    #      then verifies each one against the context) and even 8192
    #      wasn't the fix on its own -- see #2.
    #   2. thinking={"type": "disabled"}. Even at 8192, adaptive thinking
    #      was consuming the whole budget on hidden reasoning before
    #      writing a visible answer -- LLMDidNotFinishException, the same
    #      failure mode config.GENERATION_MODEL's comment in the Week 2
    #      project describes (there fixed via the raw Anthropic SDK's
    #      output_config={"effort": "low"}; ChatAnthropic's equivalent
    #      lever is this `thinking` field, not an "effort" kwarg).
    #   3. bypass_temperature=True below. ragas' wrapper otherwise sets
    #      langchain_llm.temperature on every call for judge determinism,
    #      but this Claude model rejects an explicit temperature param
    #      outright (see app/config.py's get_llm() -- same reason it's
    #      omitted there) and raises a 400 instead of just ignoring it.
    llm = LangchainLLMWrapper(
        ChatAnthropic(model=ANTHROPIC_MODEL, max_tokens=8192, thinking={"type": "disabled"}),
        bypass_temperature=True,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = evaluate(dataset=dataset, metrics=[Faithfulness()], llm=llm, show_progress=False)

    df = result.to_pandas()
    return FaithfulnessResult(deal_id, file_path, _clean(df.iloc[0].get("faithfulness")))


def _clean(value) -> float | None:
    """ragas returns NaN (not None) for a metric it couldn't score --
    normalize to None so json.dumps() doesn't choke on it downstream."""
    if value is None:
        return None
    try:
        if value != value:  # NaN != NaN
            return None
    except TypeError:
        return None
    return float(value)
