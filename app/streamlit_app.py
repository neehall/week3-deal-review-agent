"""Streamlit UI for the Multi-Agent Deal Review Pipeline.

Upload a deal document -> pipeline runs (extract -> compliance -> risk ->
compile) -> pauses for human review -> you approve/reject/request edits ->
graph resumes and finalizes.
"""

from __future__ import annotations

import tempfile
import time
import uuid
from pathlib import Path

import streamlit as st

from app.graph import get_graph
from app.observability import load_metrics_summary, read_audit, stage_summary
from app.state import DealReviewState

STAGE_LABELS = {
    "load_document": "1. Load Document",
    "extractor_agent": "2. Extractor Agent",
    "compliance_agent": "3. Compliance Agent",
    "risk_agent": "4. Risk Agent",
    "orchestrator_compile": "5. Orchestrator Compile",
    "finalize": "6. Finalize (post human review)",
}
STATUS_ICON = {"ok": "✅", "error": "❌", "running": "⏳"}


def render_observability(deal_id: str) -> None:
    """Per-stage trace + audit trail for this run -- observability at every step."""
    st.subheader("🔍 Observability — every stage of this run")

    stages = stage_summary(deal_id)
    if not stages:
        st.caption("No trace events recorded yet.")
    for stage in stages:
        label = STAGE_LABELS.get(stage["node"], stage["node"])
        icon = STATUS_ICON.get(stage["status"], "•")
        duration = f"{stage['duration_ms']} ms" if stage["duration_ms"] is not None else "—"
        extras = ", ".join(
            f"{k}={v}" for k, v in stage.items()
            if k in ("fail_count", "unclear_count", "high_severity_count") and v is not None
        )
        header = f"{icon} **{label}** — {duration}"
        if stage["retries"]:
            header += f" · {stage['retries']} retry(ies)"
        if extras:
            header += f" · {extras}"
        with st.expander(header, expanded=(stage["status"] == "error")):
            if stage["error"]:
                st.error(stage["error"])
            else:
                st.caption("Completed without error.")

    audit_events = read_audit(deal_id)
    with st.expander(f"📋 Audit trail ({len(audit_events)} events)"):
        if audit_events:
            for ev in audit_events:
                st.text(f"[{ev.get('ts', '?')}] {ev.get('event', '?')} — "
                        + ", ".join(f"{k}={v}" for k, v in ev.items() if k not in ("ts", "event", "deal_id")))
        else:
            st.caption("No audit events recorded yet.")

st.set_page_config(page_title="Deal Review Agent", layout="wide")
st.title("📄 Multi-Agent Deal Review Pipeline")
st.caption("Extractor → Compliance Checker → Risk Analyst → Orchestrator → Human Review")

with st.sidebar:
    st.subheader("Pipeline Metrics")
    metrics = load_metrics_summary()
    if metrics:
        for node, stats in metrics.items():
            st.metric(
                label=node,
                value=f"{stats['avg_duration_ms']} ms avg",
                delta=f"{stats['errors']} errors / {stats['runs']} runs",
                delta_color="inverse",
            )
    else:
        st.caption("No runs yet.")

if "deal_id" not in st.session_state:
    st.session_state.deal_id = None
    st.session_state.state = None
    st.session_state.awaiting_review = False

uploaded = st.file_uploader("Upload a deal document", type=["pdf", "docx", "txt", "md"])

col_run, col_reset = st.columns([1, 1])
run_clicked = col_run.button("Run pipeline", disabled=uploaded is None)
if col_reset.button("Reset"):
    st.session_state.deal_id = None
    st.session_state.state = None
    st.session_state.awaiting_review = False
    st.rerun()

if run_clicked and uploaded is not None:
    suffix = Path(uploaded.name).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded.read())
    tmp.close()

    deal_id = f"{Path(uploaded.name).stem}-{uuid.uuid4().hex[:8]}"
    st.session_state.deal_id = deal_id
    config = {"configurable": {"thread_id": deal_id}}

    graph = get_graph()
    # deal_id must match the checkpointer thread_id above, so trace/audit files
    # line up with the run they belong to.
    initial_state = DealReviewState(file_path=tmp.name, deal_id=deal_id)

    with st.spinner("Running extraction, compliance, and risk analysis..."):
        start = time.monotonic()
        result = graph.invoke(initial_state, config=config)
        elapsed = round(time.monotonic() - start, 1)

    st.session_state.state = result
    st.session_state.awaiting_review = True
    st.success(f"Draft report ready in {elapsed}s. Review below before it's finalized.")

if st.session_state.awaiting_review and st.session_state.state:
    state = st.session_state.state
    st.markdown("---")
    st.markdown(state["draft_report"] if isinstance(state, dict) else state.draft_report)
    st.markdown("---")
    render_observability(st.session_state.deal_id)
    st.markdown("---")

    st.subheader("Human Review — required before this report is final")
    notes = st.text_area("Notes (optional)")
    c1, c2, c3 = st.columns(3)

    def _resume(decision: str) -> None:
        config = {"configurable": {"thread_id": st.session_state.deal_id}}
        graph = get_graph()
        graph.update_state(config, {"human_decision": decision, "human_notes": notes})
        final_state = graph.invoke(None, config=config)
        st.session_state.state = final_state
        st.session_state.awaiting_review = False
        st.rerun()

    if c1.button("✅ Approve"):
        _resume("approved")
    if c2.button("✏️ Needs edit"):
        _resume("needs_edit")
    if c3.button("❌ Reject"):
        _resume("rejected")

elif st.session_state.state and not st.session_state.awaiting_review:
    state = st.session_state.state
    final_report = state["final_report"] if isinstance(state, dict) else state.final_report
    decision = state["human_decision"] if isinstance(state, dict) else state.human_decision

    st.markdown("---")
    if decision == "approved":
        st.success("Report approved and finalized.")
        st.markdown(final_report)
    elif decision == "rejected":
        st.error("Report rejected. Nothing was finalized.")
    else:
        st.warning("Marked as needs edit. Nothing was finalized -- re-run with corrections.")

    st.markdown("---")
    render_observability(st.session_state.deal_id)
