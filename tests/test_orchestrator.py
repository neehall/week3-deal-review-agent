"""Unit tests for orchestrator_compile()'s deterministic merge and its
handling of partial/failed upstream state.

No API key required -- the orchestrator makes no LLM call.
"""

from app.agents.orchestrator import orchestrator_compile
from app.state import ComplianceFinding, DealReviewState, ExtractedTerms, RiskFinding


def _sample_state() -> DealReviewState:
    return DealReviewState(
        file_path="test-deal",
        extracted_terms=ExtractedTerms(
            parties=["A Corp", "B LLC"],
            deal_type="loan agreement",
            amount="$100,000",
            interest_rate_or_price="24%",
            term_length="18 months",
            key_clauses=[],
            effective_date=None,
        ),
        compliance_findings=[
            ComplianceFinding(rule_id="R1", rule_description="Rate cap", status="fail", evidence="24% > 18%"),
            ComplianceFinding(rule_id="R2", rule_description="Effective date required", status="fail"),
        ],
        risk_findings=[
            RiskFinding(category="compliance", severity="high", description="Rate exceeds cap", related_rule_id="R1"),
        ],
    )


def test_orchestrator_includes_all_findings():
    state = orchestrator_compile(_sample_state())
    assert "R1" in state.draft_report
    assert "R2" in state.draft_report
    assert "Rate exceeds cap" in state.draft_report
    assert "24%" in state.draft_report


def test_orchestrator_flags_manual_review():
    state = _sample_state()
    state.needs_manual_review = True
    state.errors = ["extractor_agent: failed to extract structured terms after retry."]
    result = orchestrator_compile(state)
    assert "manual review is required" in result.draft_report.lower()
    assert "Pipeline Errors" in result.draft_report


def test_orchestrator_handles_missing_extraction_gracefully():
    state = DealReviewState(file_path="test-deal-empty")
    result = orchestrator_compile(state)
    assert "did not complete" in result.draft_report
