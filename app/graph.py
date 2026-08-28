"""LangGraph wiring: load -> extract -> compliance -> risk -> compile -> [human] -> finalize.

Human-in-the-loop: the graph is compiled with `interrupt_before=["finalize"]`.
Callers (the Streamlit app) run the graph up to that point, show the draft
report, collect a human decision via `update_state`, then resume with
`invoke(None, config)` to run `finalize`. The SqliteSaver checkpointer makes
this resumable across app restarts -- a review paused mid-way isn't lost.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from app.agents.compliance import compliance_agent
from app.agents.extractor import extractor_agent
from app.agents.orchestrator import orchestrator_compile
from app.agents.risk import risk_agent
from app.observability import audit, node_span, trace
from app.state import DealReviewState
from app.tools.document_loader import DocumentLoadError, load_document

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "checkpoints.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_document_node(state: DealReviewState) -> DealReviewState:
    deal_id = state.file_path
    with node_span(deal_id, "load_document"):
        try:
            state.raw_text = load_document(state.file_path)
            audit(deal_id, "document_loaded", chars=len(state.raw_text))
        except DocumentLoadError as exc:
            # Hard stop: never guess at document content. No retry -- a parse
            # failure won't fix itself; the user needs to re-upload.
            state.errors.append(f"load_document: {exc}")
            state.needs_manual_review = True
            audit(deal_id, "document_load_failed", error=str(exc))
        return state


def route_after_load(state: DealReviewState) -> str:
    """Cheapest possible failure point: don't spend LLM calls on a doc that failed to load."""
    if state.errors:
        trace(state.file_path, "routing", decision="abort_after_load_failure")
        return "orchestrator_compile"  # still produce a report explaining the failure
    return "extractor_agent"


def finalize_node(state: DealReviewState) -> DealReviewState:
    deal_id = state.file_path
    with node_span(deal_id, "finalize"):
        if state.human_decision == "approved":
            state.final_report = state.draft_report
            audit(deal_id, "review_finalized", decision="approved", notes=state.human_notes)
        elif state.human_decision == "rejected":
            state.final_report = None
            audit(deal_id, "review_finalized", decision="rejected", notes=state.human_notes)
        else:
            # needs_edit or no decision recorded -- stays open, nothing finalized.
            audit(deal_id, "review_pending", decision=state.human_decision, notes=state.human_notes)
        return state


def build_graph():
    graph = StateGraph(DealReviewState)

    graph.add_node("load_document", load_document_node)
    graph.add_node("extractor_agent", extractor_agent)
    graph.add_node("compliance_agent", compliance_agent)
    graph.add_node("risk_agent", risk_agent)
    graph.add_node("orchestrator_compile", orchestrator_compile)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("load_document")
    graph.add_conditional_edges(
        "load_document",
        route_after_load,
        {"extractor_agent": "extractor_agent", "orchestrator_compile": "orchestrator_compile"},
    )
    graph.add_edge("extractor_agent", "compliance_agent")
    graph.add_edge("compliance_agent", "risk_agent")
    graph.add_edge("risk_agent", "orchestrator_compile")
    graph.add_edge("orchestrator_compile", "finalize")
    graph.add_edge("finalize", END)

    # Direct sqlite3.Connection rather than SqliteSaver.from_conn_string(...) --
    # the latter is a contextmanager helper meant for short-lived `with` blocks,
    # which doesn't fit this module-level singleton's lifetime.
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return graph.compile(checkpointer=checkpointer, interrupt_before=["finalize"])


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
