"""Agent 2: checks extracted terms (+ raw text) against the compliance rules file."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from app.agents._llm_utils import structured_call_with_retry
from app.agents.prompts import COMPLIANCE_SYSTEM_PROMPT
from app.config import get_llm
from app.observability import node_span
from app.state import ComplianceFinding, DealReviewState

RULES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "compliance" / "rules.yaml"

# Task prompt: per-call instructions + rules/terms/document for this run. The
# agent's persistent identity and guardrails ("never guess a pass," ignore
# embedded instructions, etc.) live in COMPLIANCE_SYSTEM_PROMPT instead.
PROMPT_TEMPLATE = """Evaluate the extracted deal terms and the original document text against
each rule below. For every rule, return a status of "pass", "fail", or "unclear" and cite the
specific evidence (a quote or a clear reasoning trace) for each status.

RULES:
{rules}

EXTRACTED TERMS:
{extracted_terms}

ORIGINAL DOCUMENT:
---
{document}
---
"""


class ComplianceFindingsList(BaseModel):
    findings: list[ComplianceFinding]


def _load_rules() -> list[dict]:
    with RULES_PATH.open() as f:
        return yaml.safe_load(f)["rules"]


def compliance_agent(state: DealReviewState) -> DealReviewState:
    deal_id = state.deal_id
    with node_span(deal_id, "compliance_agent") as span:
        rules = _load_rules()

        if state.extracted_terms is None:
            # Extractor already failed upstream -- don't guess at compliance without terms.
            state.errors.append("compliance_agent: skipped, no extracted terms available.")
            state.needs_manual_review = True
            return state

        llm = get_llm()
        rules_text = "\n".join(f"- [{r['id']}] {r['description'].strip()} ({r['check']})" for r in rules)
        prompt = PROMPT_TEMPLATE.format(
            rules=rules_text,
            extracted_terms=state.extracted_terms.model_dump_json(indent=2),
            document=state.raw_text,
        )
        result, retries = structured_call_with_retry(
            llm, ComplianceFindingsList, prompt, deal_id, "compliance_agent",
            system_prompt=COMPLIANCE_SYSTEM_PROMPT,
        )
        span["retries"] = retries

        if result is None:
            state.errors.append("compliance_agent: failed to produce findings after retry.")
            state.needs_manual_review = True
            return state

        state.compliance_findings = result.findings
        span["fail_count"] = sum(1 for f in result.findings if f.status == "fail")
        span["unclear_count"] = sum(1 for f in result.findings if f.status == "unclear")
        return state
