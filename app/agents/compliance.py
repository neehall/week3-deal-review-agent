"""Agent 2: checks extracted terms (+ raw text) against the compliance rules file."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from app.agents._llm_utils import structured_call_with_retry
from app.config import get_llm
from app.observability import node_span
from app.state import ComplianceFinding, DealReviewState

RULES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "compliance" / "rules.yaml"

PROMPT_TEMPLATE = """You are a compliance reviewer. Evaluate the extracted deal terms and the
original document text against each rule below. For every rule, return a status of "pass",
"fail", or "unclear" (use "unclear" whenever the document doesn't give you enough information
to be certain -- never guess a "pass" to fill a gap). Cite the specific evidence (a quote or a
clear reasoning trace) for each status.

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
    deal_id = state.file_path
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
            llm, ComplianceFindingsList, prompt, deal_id, "compliance_agent"
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
