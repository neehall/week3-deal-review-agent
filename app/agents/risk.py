"""Agent 3: scores risk severity and drafts a plain-English narrative summary."""

from __future__ import annotations

from pydantic import BaseModel

from app.agents._llm_utils import structured_call_with_retry
from app.agents.prompts import RISK_SYSTEM_PROMPT
from app.config import get_llm
from app.observability import node_span
from app.state import DealReviewState, RiskFinding

# Task prompt: per-call instructions + this run's terms/findings. The
# agent's persistent identity and guardrails live in RISK_SYSTEM_PROMPT.
PROMPT_TEMPLATE = """Given the extracted deal terms and the compliance findings below, identify
the concrete risks a reviewer should know about and rate each risk's severity (low, medium,
high).

EXTRACTED TERMS:
{extracted_terms}

COMPLIANCE FINDINGS:
{compliance_findings}
"""


class RiskFindingsList(BaseModel):
    findings: list[RiskFinding]


def risk_agent(state: DealReviewState) -> DealReviewState:
    deal_id = state.deal_id
    with node_span(deal_id, "risk_agent") as span:
        if state.extracted_terms is None:
            state.errors.append("risk_agent: skipped, no extracted terms available.")
            state.needs_manual_review = True
            return state

        llm = get_llm()
        findings_text = "\n".join(
            f"- [{f.rule_id}] {f.rule_description} -> {f.status} ({f.evidence or 'no evidence given'})"
            for f in state.compliance_findings
        ) or "No compliance findings available."

        prompt = PROMPT_TEMPLATE.format(
            extracted_terms=state.extracted_terms.model_dump_json(indent=2),
            compliance_findings=findings_text,
        )
        result, retries = structured_call_with_retry(
            llm, RiskFindingsList, prompt, deal_id, "risk_agent",
            system_prompt=RISK_SYSTEM_PROMPT,
        )
        span["retries"] = retries

        if result is None:
            state.errors.append("risk_agent: failed to produce findings after retry.")
            state.needs_manual_review = True
            return state

        state.risk_findings = result.findings
        span["high_severity_count"] = sum(1 for f in result.findings if f.severity == "high")
        return state
