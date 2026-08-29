"""Shared state schema threaded through every node in the deal review graph."""

from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ExtractedTerms(BaseModel):
    """Structured output of the Extractor agent."""

    parties: list[str] = Field(default_factory=list, description="Named parties to the deal.")
    deal_type: Optional[str] = Field(None, description="e.g. loan agreement, term sheet, vendor contract.")
    amount: Optional[str] = Field(None, description="Principal/deal amount, as stated in the document.")
    interest_rate_or_price: Optional[str] = Field(None, description="Rate, APR, or price terms if present.")
    term_length: Optional[str] = Field(None, description="Duration/term of the agreement.")
    key_clauses: list[str] = Field(default_factory=list, description="Notable clauses found (arbitration, indemnity, termination, etc.).")
    effective_date: Optional[str] = Field(None, description="Effective/start date of the agreement.")
    notes: Optional[str] = Field(None, description="Anything ambiguous or worth flagging during extraction.")


class ComplianceFinding(BaseModel):
    rule_id: str
    rule_description: str
    status: Literal["pass", "fail", "unclear"]
    evidence: Optional[str] = Field(None, description="Quote or reasoning tying the status back to the document.")


class RiskFinding(BaseModel):
    category: Literal["financial", "legal", "compliance", "operational"]
    severity: Literal["low", "medium", "high"]
    description: str
    related_rule_id: Optional[str] = None


class DealReviewState(BaseModel):
    """The single object passed between every LangGraph node."""

    # identity -- used as the filesystem-safe key for traces/audit/checkpoints.
    # Deliberately NOT derived from file_path: that can contain slashes
    # (e.g. "data/sample_deals/x.txt" or a tempfile path), which breaks
    # anything using it as a bare filename.
    deal_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])

    # input
    file_path: str
    raw_text: str = ""

    # agent outputs
    extracted_terms: Optional[ExtractedTerms] = None
    compliance_findings: list[ComplianceFinding] = Field(default_factory=list)
    risk_findings: list[RiskFinding] = Field(default_factory=list)

    # orchestrator + human loop
    draft_report: Optional[str] = None
    human_decision: Optional[Literal["approved", "rejected", "needs_edit"]] = None
    human_notes: Optional[str] = None
    final_report: Optional[str] = None

    # error handling
    errors: list[str] = Field(default_factory=list)
    needs_manual_review: bool = False
