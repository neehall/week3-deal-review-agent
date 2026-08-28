"""Observability: structured logs, audit trail, and lightweight metrics.

Three distinct outputs, kept separate on purpose:
  - trace (data/traces/<deal_id>.jsonl):  everything, for debugging.
  - audit (data/audit/<deal_id>.jsonl):   only decision-relevant events, for review.
  - metrics (data/metrics/summary.json):  aggregated counters/timers across runs.

LangSmith tracing is enabled automatically by LangGraph/LangChain when
LANGCHAIN_TRACING_V2=true and LANGCHAIN_API_KEY are set in the environment --
no extra code needed here beyond loading .env. This module is the always-on
fallback that works with zero external accounts.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

BASE_DIR = Path(__file__).resolve().parent.parent
TRACE_DIR = BASE_DIR / "data" / "traces"
AUDIT_DIR = BASE_DIR / "data" / "audit"
METRICS_PATH = BASE_DIR / "data" / "metrics" / "summary.json"

for _dir in (TRACE_DIR, AUDIT_DIR, METRICS_PATH.parent):
    _dir.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def trace(deal_id: str, event: str, **fields: Any) -> None:
    """Debug-grade event log. Call liberally."""
    record = {"ts": _now(), "deal_id": deal_id, "event": event, **fields}
    _append_jsonl(TRACE_DIR / f"{deal_id}.jsonl", record)


def audit(deal_id: str, event: str, **fields: Any) -> None:
    """Decision-relevant event log -- what an auditor/reviewer would want to see."""
    record = {"ts": _now(), "deal_id": deal_id, "event": event, **fields}
    _append_jsonl(AUDIT_DIR / f"{deal_id}.jsonl", record)


@contextmanager
def node_span(deal_id: str, node_name: str) -> Iterator[dict[str, Any]]:
    """Wrap a graph node's body; records duration, status, and errors to the trace.

    Usage:
        with node_span(deal_id, "extractor_agent") as span:
            ... do work ...
            span["retries"] = 1  # optional extra fields
    """
    start = time.monotonic()
    span: dict[str, Any] = {}
    trace(deal_id, "node_start", node=node_name)
    try:
        yield span
    except Exception as exc:  # noqa: BLE001 - re-raised after logging
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        trace(deal_id, "node_error", node=node_name, duration_ms=duration_ms, error=str(exc), **span)
        record_metric(node_name, duration_ms=duration_ms, status="error")
        raise
    else:
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        trace(deal_id, "node_end", node=node_name, duration_ms=duration_ms, status="ok", **span)
        record_metric(node_name, duration_ms=duration_ms, status="ok")


def record_metric(node_name: str, duration_ms: float, status: str) -> None:
    """Append a run's timing/status to the rolling metrics summary file."""
    summary: dict[str, Any] = {}
    if METRICS_PATH.exists():
        try:
            summary = json.loads(METRICS_PATH.read_text())
        except json.JSONDecodeError:
            summary = {}

    node_stats = summary.setdefault(node_name, {"runs": 0, "errors": 0, "total_duration_ms": 0.0})
    node_stats["runs"] += 1
    node_stats["total_duration_ms"] += duration_ms
    if status == "error":
        node_stats["errors"] += 1
    node_stats["avg_duration_ms"] = round(node_stats["total_duration_ms"] / node_stats["runs"], 1)

    METRICS_PATH.write_text(json.dumps(summary, indent=2))


def load_metrics_summary() -> dict[str, Any]:
    if not METRICS_PATH.exists():
        return {}
    try:
        return json.loads(METRICS_PATH.read_text())
    except json.JSONDecodeError:
        return {}
