# Week 3 Project — Agent Framework

## Project 3B: Multi-Agent Deal Review Pipeline

### The Primer (one-liner)

My agent helps a **deal reviewer / underwriter** do **extract → check → risk-flag →
summarize a deal document** in a **Streamlit web app**, replacing the **2–4 hours of
manual read-through, clause-hunting, and cross-checking against a compliance
checklist that a human analyst does today**. It does **term extraction, compliance
rule-checking, and risk flagging** on its own using **4 tools** (document loader,
term extractor, compliance rule-checker, risk/summary generator), hands off to a
human **before the final review is marked "approved" or sent onward**, and I'll
know it works when a reviewer can get a **structured deal review report in under
5 minutes** that correctly flags **at least 8 of 10 planted compliance/risk issues**
in a test deal document.

---

### The Framework

| Field | Fill in |
|---|---|
| **Agent goal** | Takes a deal document (contract, term sheet, loan agreement) and produces a structured, risk-rated compliance review that a human can approve or reject. |
| **Where do people use it?** | Web app (Streamlit) — upload a document, get a review report. |
| **What steps does it take, in order?** | 1) Ingest & parse the deal document. 2) **Agent 1 (Extractor)** pulls key terms (parties, amount, term length, rate, key clauses, obligations). 3) **Agent 2 (Compliance Checker)** checks extracted terms against a compliance rules set (e.g. required disclosures, rate/term limits, missing-clause checks) — flags pass/fail per rule. 4) **Agent 3 (Risk Analyst)** scores/flags risks (financial, legal, compliance severity) and drafts a plain-English summary. 5) **Orchestrator** sequences the above, merges outputs into one structured report, and pauses for human review before finalizing. |
| **What can it actually do?** | (a) Parse/load document — *read*. (b) Extract structured terms via LLM — *read*. (c) Check terms against a compliance ruleset — *read*. (d) Generate risk score + summary — *read*. (e) Save/export the finished report to disk — *write*. (f) (Optional) Re-run a step if flagged incomplete — *read*, agent-internal. |
| **What does it need to remember?** | Within a single review run: the full extracted-term state, compliance findings, and risk flags, passed through LangGraph state across nodes. Across runs (persistent): a small history of past reviews (deal ID → verdict) so the app can show "past reviews" — session/light persistent store (e.g. local JSON/SQLite), not full long-term memory. |
| **What should it never do?** | Never mark a deal "approved" or push a decision downstream (e.g. to a CRM/loan system) without human sign-off. Never fabricate a compliance rule or term that isn't in the source document. Never silently drop a section of the document from review. |
| **Human-in-the-loop** | After the Orchestrator compiles the draft report (all 3 agents done) and before the report is marked final/approved — the human reviewer sees the flags, can edit/override, and explicitly approves. This is a LangGraph `interrupt` point. |
| **What happens when something breaks?** | If document parsing fails (bad file, empty extraction) → stop and ask the user to re-upload, don't guess. If an agent step returns malformed/empty output → retry once with a stricter prompt, then surface a "needs manual review" flag on that section rather than failing silently. |
| **How do you know it worked?** | A reviewer can upload a deal doc and get a structured, correctly-flagged review in under 5 minutes, catching ≥8/10 planted issues in a test document — validated against 2–3 sample deals with known "answer keys." |

---

### Build track: Track 2 — LangChain + LangGraph

- **State**: a single `DealReviewState` (TypedDict/Pydantic) threaded through the graph — holds raw doc text, extracted terms, compliance findings, risk findings, final report, and a `human_approved` flag.
- **Graph shape**: `extract → compliance_check → risk_analysis → orchestrator_compile → [interrupt: human review] → finalize`
- **Orchestrator**: implemented as a LangGraph node (not a 4th LLM agent necessarily) that merges the three agents' structured outputs into one report — could also be a light LLM pass for narrative summary.
- **Interface**: Streamlit, matching the Week 2 project's stack.
