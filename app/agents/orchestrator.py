"""Orchestrator: merges the three agents' outputs into one structured report.

Deliberately not an LLM call -- deterministic merge keeps the report grounded
in exactly what the upstream agents produced, with no chance of the
orchestrator itself hallucinating a finding. This also makes it cheap and
fast, and easy to unit test.
"""

from __future__ import annotations

from app.observability import node_span
from app.state import DealReviewState


def orchestrator_compile(state: DealReviewState) -> DealReviewState:
    deal_id = state.file_path
    with node_span(deal_id, "orchestrator_compile"):
        terms = state.extracted_terms
        lines: list[str] = ["# Deal Review Report", ""]

        if state.needs_manual_review:
            lines.append(
                "> ⚠️ One or more pipeline steps could not complete automatically. "
                "This report is **incomplete** -- manual review is required before any decision."
            )
            lines.append("")

        lines.append("## Extracted Terms")
        if terms:
            lines.append(f"- **Deal type:** {terms.deal_type or '_not stated_'}")
            lines.append(f"- **Parties:** {', '.join(terms.parties) or '_not stated_'}")
            lines.append(f"- **Amount:** {terms.amount or '_not stated_'}")
            lines.append(f"- **Rate/Price:** {terms.interest_rate_or_price or '_not stated_'}")
            lines.append(f"- **Term length:** {terms.term_length or '_not stated_'}")
            lines.append(f"- **Effective date:** {terms.effective_date or '_not stated_'}")
            lines.append(f"- **Key clauses:** {', '.join(terms.key_clauses) or '_none found_'}")
            if terms.notes:
                lines.append(f"- **Extractor notes:** {terms.notes}")
        else:
            lines.append("_Extraction did not complete._")
        lines.append("")

        lines.append("## Compliance Findings")
        if state.compliance_findings:
            fails = [f for f in state.compliance_findings if f.status == "fail"]
            unclear = [f for f in state.compliance_findings if f.status == "unclear"]
            lines.append(f"**{len(fails)} failed, {len(unclear)} unclear, "
                         f"{len(state.compliance_findings) - len(fails) - len(unclear)} passed.**")
            lines.append("")
            for f in state.compliance_findings:
                icon = {"pass": "✅", "fail": "❌", "unclear": "❓"}[f.status]
                lines.append(f"- {icon} **[{f.rule_id}]** {f.rule_description} — {f.status}")
                if f.evidence:
                    lines.append(f"  - _Evidence: {f.evidence}_")
        else:
            lines.append("_Compliance check did not complete._")
        lines.append("")

        lines.append("## Risk Findings")
        if state.risk_findings:
            severity_order = {"high": 0, "medium": 1, "low": 2}
            for f in sorted(state.risk_findings, key=lambda r: severity_order[r.severity]):
                lines.append(f"- **[{f.severity.upper()} / {f.category}]** {f.description}"
                             + (f" (ref: {f.related_rule_id})" if f.related_rule_id else ""))
        else:
            lines.append("_Risk analysis did not complete._")
        lines.append("")

        if state.errors:
            lines.append("## Pipeline Errors")
            for err in state.errors:
                lines.append(f"- {err}")
            lines.append("")

        state.draft_report = "\n".join(lines)
        return state
