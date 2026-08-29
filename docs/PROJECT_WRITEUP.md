# Project Write-Up — Multi-Agent Deal Review Pipeline

**Week 3 Project — Mastering Agentic AI Certification**
**Project 3B, Track 2 (LangChain + LangGraph)**
**Repo:** https://github.com/neehall/week3-deal-review-agent

> This doc is written to be copy-pasted into the required Google Doc
> deliverable. Section headers map to what the handout asks for: overview,
> prompts used, iterations, and learnings.

---

## 1. Overview

### The one-liner
My agent helps a **deal reviewer / underwriter** do **extract → check →
risk-flag → summarize a deal document** in a **Streamlit web app**, replacing
the **2–4 hours of manual read-through, clause-hunting, and cross-checking
against a compliance checklist** that a human analyst does today. It does
**term extraction, compliance rule-checking, and risk flagging** on its own
using **4 tools** (document loader, term extractor, compliance
rule-checker, risk/summary generator), hands off to a human **before the
final review is marked "approved" or sent onward**, and I know it works
because a reviewer can get a **structured deal review report in under 5
minutes** that correctly flagged **all planted compliance/risk issues** in
every test document I ran it against.

### Why this use case
I do this kind of review manually today, and the failure mode I wanted to
solve for wasn't "can an LLM summarize a contract" — it's "can a pipeline be
trusted enough that a human only has to *verify* flags instead of
*re-deriving* them from scratch." That's why the design leans so heavily on:
structured (not freeform) outputs at every step, a rule engine the LLM is
checked against rather than trusted blindly, and a hard human-approval gate
before anything is called final.

### Architecture (see `docs/ARCHITECTURE.md` for full diagrams)

```
load_document → extractor_agent → compliance_agent → risk_agent
    → orchestrator_compile → [INTERRUPT: human review] → finalize
```

- **State**: one `DealReviewState` (Pydantic) threaded through every
  LangGraph node — no side-channel data passing.
- **3 LLM agents** (Extractor, Compliance, Risk) each use
  `with_structured_output` against a Pydantic schema, not freeform text.
- **Orchestrator** is deliberately *not* an LLM call — a deterministic merge
  of the three agents' structured outputs into one report, so it can never
  hallucinate a finding the upstream agents didn't produce.
- **Human-in-the-loop**: the graph is compiled with
  `interrupt_before=["finalize"]`. Nothing is marked final until a reviewer
  explicitly approves, rejects, or requests edits in the Streamlit UI.
- **Persistence**: LangGraph's `SqliteSaver` checkpoints state per
  `deal_id` (thread), so a review paused mid-way survives an app restart.
- **Observability**: three separate JSONL/JSON outputs (trace, audit,
  metrics) plus optional LangSmith, all rendered live in the UI as a
  per-stage panel after every run.

### Tech stack
LangGraph + LangChain, Anthropic (Claude) as the LLM provider, Streamlit for
the UI, Pydantic for schemas, `pypdf`/`python-docx` for document parsing,
SQLite for checkpointing, `pytest` for tests.

---

## 2. Prompts used

Every agent uses `llm.with_structured_output(Schema)` rather than parsing
freeform text — the prompt's job is to constrain *reasoning*, not *format*.

### Extractor agent
```
You are a contract analyst extracting structured terms from a deal document.
Read the document below and extract the fields precisely as they appear. If a field is not
present in the document, leave it null/empty -- never invent a value. For key_clauses, list
every notable clause type present (e.g. arbitration, indemnification, termination, cancellation,
non-renewal, confidentiality, limitation of liability) using the same terminology the document
uses, even if it appears deep in a "dispute resolution" or similarly-named section.

DOCUMENT:
---
{document}
---
```
Output schema: `ExtractedTerms` (parties, deal_type, amount,
interest_rate_or_price, term_length, key_clauses, effective_date, notes).

**Why it's worded this way:** the "never invent a value" instruction and the
explicit null/empty fallback exist because the compliance agent downstream
treats a missing field as evidence, not as "try harder to guess." The
`key_clauses` instruction ("even if it appears deep in a dispute-resolution
section") was added specifically after a test document (`deal_3`) buried its
arbitration clause under a "DISPUTE RESOLUTION" heading rather than a
section literally titled "Arbitration" — an earlier version of the prompt
missed it.

### Compliance agent
```
You are a compliance reviewer. Evaluate the extracted deal terms and the
original document text against each rule below. For every rule, return a status of "pass",
"fail", or "unclear" (use "unclear" whenever the document doesn't give you enough information
to be certain -- never guess a "pass" to fill a gap). Cite the specific evidence (a quote or a
clear reasoning trace) for each status.

RULES:
{rules}

EXTRACTED TERMS:
{extracted_terms}

ORIGINAL DOCUMENT:
---
{document}
---
```
Output schema: `ComplianceFindingsList` → list of `ComplianceFinding`
(rule_id, rule_description, status, evidence).

**Why it's worded this way:** "never guess a pass to fill a gap" is the
single most load-bearing line in the whole system. A naive compliance
checker defaults ambiguous cases to "pass" because that's the path of least
resistance; this one is instructed to default to `"unclear"` instead, which
routes it toward human review rather than a false clean bill of health. Feeding
both the extracted terms *and* the raw document (not just the structured
extraction) lets the agent catch cases where the extraction was too
conservative to flag something the raw text actually supports.

### Risk agent
```
You are a risk analyst. Given the extracted deal terms and the compliance
findings below, identify the concrete risks a reviewer should know about, and rate each risk's
severity (low, medium, high). Every "fail" compliance finding should map to at least one risk
finding; "unclear" findings should generally map to a low/medium risk noting the ambiguity
rather than being ignored. Also flag any risk not caught by the compliance rules but visible in
the terms themselves (e.g. an unusually short notice period, an unbalanced termination right).

EXTRACTED TERMS:
{extracted_terms}

COMPLIANCE FINDINGS:
{compliance_findings}
```
Output schema: `RiskFindingsList` → list of `RiskFinding` (category,
severity, description, related_rule_id).

**Why it's worded this way:** the "every fail should map to at least one
risk" instruction forces traceability between the two agents' outputs — a
reviewer can always trace a risk narrative back to the specific rule that
triggered it. The last sentence ("also flag any risk not caught by the
compliance rules") is what lets the pipeline surface things like
"36-month lock-in with no early-termination right" in `deal_3`, which isn't
a rule violation but is exactly the kind of thing a human reviewer would
want called out.

### Repair prompt (retry path)
On a malformed/empty structured-output response, `app/agents/_llm_utils.py`
appends this to the original prompt and retries once:
```
IMPORTANT: Your previous response could not be parsed into the
required structured format. Respond with ONLY the fields requested,
using your best interpretation of the document -- do not add commentary.
```

---

## 3. Iterations

Roughly chronological, kept to the decisions that actually changed the
build (not every file write):

1. **Framework before code.** Per the handout's requirement, I drafted
   `FRAMEWORK.md` (the one-liner + detailed table) *before* writing any
   LangGraph code, and confirmed it with a human checkpoint before
   scaffolding. This directly shaped the graph shape — the "human-in-the-loop"
   field in the framework became the `interrupt_before=["finalize"]` design,
   not an afterthought bolted on later.

2. **Observability as a first-class design pass, not a bolt-on.** After the
   initial agent/graph scaffold, I stopped to explicitly design failure
   handling, tracing, audit, and metrics *before* writing more pipeline
   code — driven by the "falls over on first tool failure" grading
   criterion. This produced the three-way split (trace vs. audit vs.
   metrics) and the retry-once-then-flag-for-manual-review policy that
   every agent follows.

3. **LLM provider switch: OpenAI → Anthropic.** The build started on
   `langchain-openai`/`ChatOpenAI`, then switched to
   `langchain-anthropic`/`ChatAnthropic` (Claude). This touched
   `app/config.py`, `requirements.txt`, `.env.example`, and `README.md`.
   One wrinkle: the target Claude model rejects an explicit `temperature`
   parameter ("temperature is deprecated for this model"), so `get_llm()`
   was changed to omit it and use the API default rather than forcing
   `temperature=0` for determinism.

4. **`deal_id` bug found during the switch.** Every node originally used
   `state.file_path` as the key for trace/audit filenames and LangGraph
   `thread_id`. That breaks as soon as `file_path` contains a slash (a
   `data/sample_deals/...` path, or any tempfile path) — the underlying
   filesystem write would silently target the wrong nested location. Fixed
   by adding a dedicated `deal_id: str` field to `DealReviewState`
   (UUID-based, filesystem-safe by construction) and threading it through
   every node and the Streamlit UI's `thread_id`, instead of reusing
   `file_path` for something it was never meant for.

5. **Synthetic test data with a deliberate reasoning trap.** Built 3 sample
   deals with a hand-written `ANSWER_KEY.md`:
   - `deal_1_clean_loan.txt` — a clean baseline, should pass every rule.
   - `deal_2_bad_rate.txt` — 3 planted, unambiguous violations (rate cap,
     missing effective date, missing termination clause).
   - `deal_3_hidden_arbitration.txt` — buries an arbitration clause under a
     "DISPUTE RESOLUTION" heading and uses "non-renewal notice" instead of
     the literal words "termination"/"cancellation," specifically to test
     whether the extractor/compliance agents reason over substance or
     pattern-match keywords. This is the test that caught the extractor gap
     described in iteration 1's prompt fix.

6. **Per-stage observability panel in the UI.** Originally the Streamlit app
   only showed the sidebar's rolling metrics summary. Added
   `stage_summary()`/`read_trace()`/`read_audit()` to
   `app/observability.py` and a per-run panel (status/duration/retries/error
   per node, plus the full audit trail) shown after every run and again
   after the human-review resume — so a given run is inspectable end to end,
   not just its final report.

7. **Architecture documentation pass.** Added `docs/ARCHITECTURE.md` with
   diagrams (system overview, pipeline graph, human-in-the-loop sequence,
   state schema, agent responsibility table) once the design had stabilized
   enough to be worth diagramming accurately.

8. **A 4-tier sample deal set (normal / failing / edge_cases / extreme), and a
   real bug found by it.** Expanded from 3 sample deals to 20, organized by
   difficulty: clean baselines, unambiguous multi-rule failures, boundary/
   ambiguous edge cases (rate exactly at the cap, term exactly at the
   threshold, conflicting dates, a rate range straddling the cap, foreign
   currency formatting), and "extreme" cases targeting pipeline *mechanics*
   rather than compliance logic (empty file, gibberish input, binary
   garbage, an unsupported extension, and a document containing an embedded
   prompt-injection attempt instructing the model to hide a real violation).
   Running the full set through the live graph surfaced a genuine bug: an
   early, 144K-character version of the "extremely long document" test case
   reliably truncated the risk/compliance agents' structured output mid-JSON
   — `ChatAnthropic`'s default `max_tokens` cap, not a schema bug, though it
   surfaced as a `pydantic.ValidationError` that looked like one at first
   glance. Fixed by setting `max_tokens=4096` explicitly in `app/config.py`
   and resizing the test document to ~18.8K characters (still a real stress
   test, at roughly 1/8th the token cost and without the evidence-quote
   compounding that caused the truncation). Full writeup in
   `data/sample_deals/ANSWER_KEY.md`.

9. **Housekeeping caught while verifying end-to-end.** Running a full smoke
   test surfaced two small drifts: `run.sh`'s error message still referenced
   `OPENAI_API_KEY` after the provider switch, and `.gitignore` only
   excluded `data/checkpoints.sqlite` and not its `-shm`/`-wal` sidecar
   files (SQLite's WAL mode). Both fixed before the first push.

---

## 4. Testing & validation

Two layers:

- **Unit tests** (`tests/test_document_loader.py`,
  `tests/test_orchestrator.py`, 7 tests, no API key required) — cover
  document parsing edge cases and the orchestrator's deterministic
  merge/error-handling logic.
- **End-to-end validation against the answer key** — ran the full graph
  (real Claude calls) against all 3 sample deals:
  - `deal_1` (clean baseline) → 0 findings flagged, as expected.
  - `deal_2` (3 planted issues) → all 3 caught (rate cap, missing date,
    missing termination clause), each with correct evidence citations.
  - `deal_3` (hidden-arbitration trap) → arbitration clause correctly
    extracted despite being buried in a "Dispute Resolution" section;
    ambiguous rate question correctly marked `unclear` rather than a false
    pass; missing-amount and no-termination-right issues both caught; risk
    agent correctly surfaced the 36-month lock-in risk that isn't covered
    by any explicit rule.
  - Also verified the full human-in-the-loop resume path (`update_state` →
    `invoke(None, ...)`) correctly finalizes on approval and correctly
    withholds `final_report` on rejection.

---

## 5. Learnings

- **The framework-first requirement wasn't busywork.** Writing the
  human-in-the-loop field down explicitly, before any code, is what made
  `interrupt_before=["finalize"]` the obvious implementation instead of
  something retrofitted after the fact. The "what should it never do?"
  field directly became the orchestrator's no-LLM-call design decision.
- **"Never guess a pass" is worth more than clever prompting.** The single
  highest-leverage prompt change in this build wasn't a formatting
  instruction — it was explicitly telling the compliance agent to default
  to `"unclear"` over `"pass"` when evidence is thin. Structured output
  schemas keep the *shape* honest; the prompt has to keep the *epistemics*
  honest.
- **A deliberately adversarial test document earns its keep.**
  `deal_3_hidden_arbitration.txt` caught a real extraction gap
  (`deal_3`'s arbitration clause) that the two straightforward test
  documents never would have surfaced, because it was designed to look like
  something a keyword-matcher would miss but a careful reader wouldn't.
- **Reusing an identifier for a purpose it wasn't designed for causes silent
  bugs, not loud ones.** The `file_path`-as-`deal_id` bug never crashed
  anything — trace/audit files just would have quietly landed in the wrong
  place once a real (slash-containing) path was used. It only surfaced
  because the observability layer existed to make output-in-the-wrong-place
  visible in the first place, which reinforced why building observability
  early (not after "the real bugs") was the right call.
- **An adversarial test document is only useful if it's also cheap to
  re-run.** The first version of the "extreme long document" test case was
  144K characters — it found a real bug (`max_tokens` truncation), but at a
  size that made every re-run expensive and, worse, was itself the reason
  the bug fired (long input → long echoed evidence quotes → truncated
  output). Resizing it to ~18.8K characters kept the stress test genuine
  while cutting the token cost roughly 8x. The lesson generalizes: an
  extreme-case fixture should be *just* extreme enough to exercise the
  mechanism you're testing, not maximally extreme for its own sake.
- **Deterministic orchestration is a trust feature, not a shortcut.**
  Making the orchestrator a plain merge function instead of a 4th LLM call
  was originally a cost/latency decision; in practice it turned out to be
  more important as a *correctness guarantee* — a reviewer can trust that
  every line in the final report traces back to one of the three agents'
  actual structured output, with no chance of report-writing hallucination.

---

## 6. Deliverables checklist

- [x] Framework primer + table (`FRAMEWORK.md`)
- [x] Working code (LangGraph + LangChain, Track 2), pushed to GitHub:
      https://github.com/neehall/week3-deal-review-agent
- [x] Architecture diagrams (`docs/ARCHITECTURE.md`)
- [x] This write-up (prompts, iterations, learnings)
- [ ] ≤5-minute video demo — *to be recorded separately*
