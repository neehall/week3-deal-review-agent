# Multi-Agent Deal Review Pipeline

Week 3 Project — Mastering Agentic AI Certification. Project 3B, Track 2 (LangChain + LangGraph).

See [FRAMEWORK.md](FRAMEWORK.md) for the one-liner and full agent framework this build follows,
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for diagrams (graph, human-in-the-loop
sequence, state schema) and the failure-handling / observability design in detail, and
[docs/PROJECT_WRITEUP.md](docs/PROJECT_WRITEUP.md) for the submission write-up (prompts used,
build iterations, learnings), [CHANGELOG.md](CHANGELOG.md) for the full change history, and
[docs/CODE_MAP.md](docs/CODE_MAP.md) for a file-by-file index of what each source file does.

## What it does

Upload a deal document (loan agreement, term sheet, vendor contract) and the pipeline:

1. **Extractor agent** pulls structured terms (parties, amount, rate, term, key clauses).
2. **Compliance agent** checks those terms against `data/compliance/rules.yaml`.
3. **Risk agent** scores severity and drafts a plain-English risk narrative.
4. **Orchestrator** merges all three into one report — deterministically, no LLM call, so it can never introduce a finding the upstream agents didn't produce.
5. **Human review** — the graph pauses here. A reviewer approves, rejects, or requests edits before anything is finalized.

## Architecture

```
load_document → extractor_agent → compliance_agent → risk_agent
    → orchestrator_compile → [INTERRUPT: human review] → finalize
```

Built as a LangGraph `StateGraph` over a single `DealReviewState` (see `app/state.py`),
checkpointed to SQLite (`data/checkpoints.sqlite`) so a review paused mid-way is resumable,
not lost.

## Observability

- **Trace logs** (`data/traces/<deal_id>.jsonl`) — every node's start/end/duration/errors.
- **Audit log** (`data/audit/<deal_id>.jsonl`) — decision-relevant events only: document
  loaded, review finalized, who approved/rejected and when.
- **Metrics** (`data/metrics/summary.json`) — rolling avg duration and error count per node,
  shown live in the Streamlit sidebar.
- **LangSmith** — set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` in `.env` to also
  get full LangSmith traces. Optional; everything above works without it.
- **In-app observability panel** — after every run (and again after the human-review resume),
  the Streamlit UI shows a per-stage breakdown (status, duration, retries, error) plus the full
  audit trail for that `deal_id`, so every stage of a given run is inspectable, not just the
  final report.

## Failure handling

| Failure | Behavior |
|---|---|
| Document fails to parse | Hard stop before any LLM call; reported in the draft report. |
| LLM structured output fails | One retry with a repair prompt; on 2nd failure, node's output is left empty and `needs_manual_review=True` is set, but the pipeline still produces a report explaining what's missing rather than crashing. |
| Compliance rule can't be evaluated from available terms | Marked `unclear`, never silently passed. |
| Human review not yet submitted | Graph stays interrupted; nothing is finalized until an explicit decision is recorded. |

## Setup

```bash
cp .env.example .env   # add your ANTHROPIC_API_KEY
./run.sh
```

## Test data

`data/sample_deals/` has 20 synthetic documents across 4 tiers (normal, failing, edge_cases,
extreme) with an `ANSWER_KEY.md` describing exactly what should be flagged — used to validate
the compliance/risk agents' accuracy end to end.

## Independent evaluation (ragas)

This isn't a RAG system — no corpus, no retrieval step — but `ragas`' `Faithfulness` metric
doesn't require one: it only asks whether every claim in a piece of text traces back to a given
context, which maps directly onto this pipeline's own "never fabricate a value" guardrail.
`app/ragas_eval.py` scores the orchestrator's draft report for groundedness against the source
document, as a standardized cross-check layered on top of `ANSWER_KEY.md`'s own hand-built
validation (that checks compliance *correctness*; this checks *groundedness*).

```bash
PYTHONPATH=. python scripts/run_ragas_faithfulness.py           # 1 doc/tier, 4 total
PYTHONPATH=. python scripts/run_ragas_faithfulness.py --all     # every sample deal
```

Real run against the default 4-document sample: faithfulness scored 0.46–0.81, not uniformly
high. That's an honest, informative result rather than a bug — see
`data/sample_deals/ANSWER_KEY.md`'s ragas section for why a metric built for RAG Q&A (where a
good answer closely paraphrases retrieved text) scores a structured compliance report — verdict
labels, severity tags, synthesized risk narrative — more conservatively than a literal quote
would score.

## Tests

```bash
source .venv/bin/activate
pytest
```

Covers the document loader and the orchestrator's merge/error-handling logic without
requiring an API key. The agent nodes themselves are exercised via the sample deals + UI.
