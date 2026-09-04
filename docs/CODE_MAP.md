# Code Map — Week 3 Project

A file-by-file index of what each source file does, at a glance. For *why*
it's built this way, see [ARCHITECTURE.md](ARCHITECTURE.md); for the
one-liner and design framework, see [FRAMEWORK.md](../FRAMEWORK.md).

---

## `app/` — application code

### Entry point

| File | What it does |
|---|---|
| [`app/streamlit_app.py`](../app/streamlit_app.py) | The Streamlit UI. Uploads a deal document, runs it through the LangGraph pipeline, shows the draft report, collects the human approve/reject/needs-edit decision, resumes the graph to finalize, and renders the per-stage observability panel (trace + audit) after every run. Inserts the repo root onto `sys.path` at the top so `app.*` imports resolve regardless of how the script is launched (local, `run.sh`, or a hosted platform like Streamlit Community Cloud). |

### Graph wiring

| File | What it does |
|---|---|
| [`app/graph.py`](../app/graph.py) | Builds and compiles the LangGraph `StateGraph`: wires the six nodes (`load_document → extractor_agent → compliance_agent → risk_agent → orchestrator_compile → finalize`) in order, adds the conditional edge that skips straight to the report on a load failure, and compiles with a `SqliteSaver` checkpointer and `interrupt_before=["finalize"]` so the graph always pauses for human review. Exposes `get_graph()`, a lazily-built module-level singleton. |
| [`app/state.py`](../app/state.py) | Defines the Pydantic schemas threaded through the graph: `DealReviewState` (the one object every node reads/writes — file path, raw text, each agent's output, human decision, errors), and the three structured-output shapes `ExtractedTerms`, `ComplianceFinding`, `RiskFinding`. |
| [`app/config.py`](../app/config.py) | Loads `.env` and builds the shared `ChatAnthropic` client (`get_llm()`). Sets `max_tokens=4096` explicitly (found necessary after a real truncation bug — see `CHANGELOG.md`) and omits `temperature` (this model rejects that param). Also computes whether LangSmith tracing is enabled from env vars. |
| [`app/observability.py`](../app/observability.py) | All logging/tracing/metrics. `trace()` and `audit()` append JSONL events to `data/traces/` and `data/audit/` respectively; `node_span()` is a context manager every graph node wraps its body in, timing it and recording start/end/error automatically; `record_metric()` rolls per-node stats into `data/metrics/summary.json`; `stage_summary()`/`read_trace()`/`read_audit()` read all of the above back for the Streamlit UI's per-run observability panel. |

### Agents (`app/agents/`)

| File | What it does |
|---|---|
| [`app/agents/_llm_utils.py`](../app/agents/_llm_utils.py) | Shared helper `structured_call_with_retry()`: calls `llm.with_structured_output(schema)`, and on failure retries once with an appended "your last response didn't parse" repair prompt. Returns `(result_or_None, retries_used)` so callers can decide what to do on total failure rather than crashing. |
| [`app/agents/extractor.py`](../app/agents/extractor.py) | **Agent 1.** Prompts the LLM to pull structured terms (parties, amount, rate, term, key clauses, effective date) out of the raw document text into an `ExtractedTerms` object. On failure, sets `needs_manual_review=True` and appends to `state.errors` rather than raising. |
| [`app/agents/compliance.py`](../app/agents/compliance.py) | **Agent 2.** Loads `data/compliance/rules.yaml`, then prompts the LLM to evaluate the extracted terms (plus the raw document, for evidence) against each rule, returning `pass`/`fail`/`unclear` per rule with cited evidence. Explicitly instructed to default to `unclear` rather than guess a `pass`. |
| [`app/agents/risk.py`](../app/agents/risk.py) | **Agent 3.** Prompts the LLM to turn the compliance findings (plus extracted terms) into severity-rated risk findings, including risks not covered by any explicit rule (e.g. an unbalanced termination clause). |
| [`app/agents/orchestrator.py`](../app/agents/orchestrator.py) | **Not an LLM call.** Deterministically merges the three agents' structured outputs into one Markdown `draft_report` string. Kept non-LLM on purpose so the final report can never contain a finding the upstream agents didn't actually produce. |

### Tools (`app/tools/`)

| File | What it does |
|---|---|
| [`app/tools/document_loader.py`](../app/tools/document_loader.py) | `load_document(file_path)` — parses PDF (`pypdf`), DOCX (`python-docx`), or TXT/MD into plain text. Raises `DocumentLoadError` (never guesses) on a missing file, unsupported extension, or a file with no extractable text. |

### Evaluation

| File | What it does |
|---|---|
| [`app/ragas_eval.py`](../app/ragas_eval.py) | `score_report_faithfulness()` — an independent, standardized cross-check on top of `ANSWER_KEY.md`'s hand-built validation, using the `ragas` framework's `Faithfulness` metric to score whether the orchestrator's draft report stays grounded in the source document. See its docstring for 3 real fixes (`max_tokens`, `thinking: disabled`, `bypass_temperature`) needed to get `ragas` working against this Claude model at all. |

---

## `data/` — non-code assets

| Path | What it is |
|---|---|
| [`data/compliance/rules.yaml`](../data/compliance/rules.yaml) | The 6 compliance rules the compliance agent checks every deal against (rate cap, required effective date, termination-clause requirement for long terms, minimum party count, arbitration-disclosure requirement, required deal amount). Synthetic, for demo purposes. |
| [`data/sample_deals/`](../data/sample_deals/) | 20 synthetic test documents in 4 tiers (`normal/`, `failing/`, `edge_cases/`, `extreme/`) plus `ANSWER_KEY.md` recording the actual observed pipeline behavior for each. See the Answer Key for what each file is designed to test. |
| `data/traces/`, `data/audit/`, `data/metrics/`, `data/checkpoints.sqlite*` | Runtime output, not source — trace/audit logs, rolling metrics, and LangGraph's checkpoint DB. Gitignored (except `.gitkeep` placeholders); regenerated by running the app. |

---

## `tests/` — unit tests

| File | What it does |
|---|---|
| [`tests/test_document_loader.py`](../tests/test_document_loader.py) | Covers `load_document()`'s error paths: missing file, unsupported extension, empty/whitespace-only file, and a normal `.txt` read — all without needing an API key. |
| [`tests/test_orchestrator.py`](../tests/test_orchestrator.py) | Covers `orchestrator_compile()`'s deterministic merge logic and its handling of partial/failed upstream state (missing terms, `needs_manual_review`, accumulated errors) — also no API key required. |

---

## `scripts/` — standalone eval runners

| File | What it does |
|---|---|
| [`scripts/run_ragas_faithfulness.py`](../scripts/run_ragas_faithfulness.py) | Runs the pipeline + `app/ragas_eval.py`'s faithfulness check over the sample deals (a cost-conscious 4-document default, or `--all`), writes `data/sample_deals/ragas_faithfulness_results.json`. |

---

## Top-level files

| File | What it does |
|---|---|
| [`FRAMEWORK.md`](../FRAMEWORK.md) | The required pre-code design doc: the one-line agent primer plus the detailed goal/steps/tools/memory/limits/human-in-the-loop/failure-handling/success-metric table. |
| [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) | Diagrams (system overview, pipeline graph, human-in-the-loop sequence, state schema) and the failure-handling/observability design, in prose. |
| [`docs/PROJECT_WRITEUP.md`](PROJECT_WRITEUP.md) | The submission write-up: overview, the 3 agent prompts with rationale, a chronological build-iteration log, validation results, and learnings. |
| [`CHANGELOG.md`](../CHANGELOG.md) | Full commit-by-commit project history. |
| [`README.md`](../README.md) | Quick-start: what the app does, setup instructions, links to the other docs. |
| [`requirements.txt`](../requirements.txt) | Python dependencies (LangGraph, LangChain, Anthropic SDK, Streamlit, document parsers, `pytest`, etc.). |
| [`run.sh`](../run.sh) | Local launch script: creates/activates the venv, installs requirements, checks `.env` exists, then runs Streamlit with `PYTHONPATH` set. |
| [`.env.example`](../.env.example) | Template for required env vars (`ANTHROPIC_API_KEY`, optional LangSmith tracing vars). |
