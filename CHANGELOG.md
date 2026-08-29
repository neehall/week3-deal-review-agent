# Changelog

All notable changes to this project, in the order they happened. Each entry
links the commit that made it; see `git log` for full diffs.

## [Unreleased]

### Added — expanded sample deal set across a difficulty spectrum
- Reorganized `data/sample_deals/` into four tiers: `normal/`, `failing/`,
  `edge_cases/`, `extreme/`.
- **`normal/`** — clean documents that should pass every compliance rule:
  `deal_1_clean_loan.txt` (moved), `deal_4_clean_lease.txt`,
  `deal_5_clean_termsheet.txt`.
- **`failing/`** — unambiguous, stacked violations: `deal_2_bad_rate.txt`
  (moved), `deal_6_multi_fail_creditline.txt` (fails nearly every rule at
  once, to test the report doesn't buckle under many findings),
  `deal_7_unbalanced_equipment_lease.txt` (a rate-cap violation plus a
  one-sided termination right that no rule catches — tests the risk agent's
  ability to surface risks beyond the rule engine).
- **`edge_cases/`** — technically valid but boundary/ambiguous, testing
  precision over pattern-matching: `deal_3_hidden_arbitration.txt` (moved),
  `deal_8_boundary_rate_exactly_18pct.txt` (rate at the exact cap),
  `deal_9_boundary_exactly_12mo_term.txt` (term at the exact threshold,
  rule requires *greater than* 12 months), `deal_10_conflicting_effective_dates.txt`
  (an amended-and-restated agreement citing two dates — tests which one the
  extractor resolves as current), `deal_11_ambiguous_rate_range.txt` (a
  16–21% rate range straddling the 18% cap — should be `unclear`, not a
  guessed pass/fail), `deal_12_foreign_currency_amount.txt` (EUR amount and
  comma-decimal rate in European number formatting).
- **`extreme/`** — stress-tests pipeline *mechanics*, not just compliance
  logic: `deal_13_empty_file.txt` (0 bytes — hard stop before any LLM call),
  `deal_14_whitespace_only.txt` (same failure path, non-empty bytes),
  `deal_15_gibberish_not_a_contract.txt` (no extractable deal terms at all —
  tests the pipeline degrades to `needs_manual_review` instead of crashing
  or hallucinating terms), `deal_16_extremely_long_document.txt`
  (~144K chars / ~21K words of boilerplate padding around real terms —
  tests prompt/context handling at scale), `deal_17_prompt_injection_attempt.txt`
  (a real 29.9%-rate violation with an embedded fake "system notice"
  instructing the model to mark everything as passing and hide the true
  rate — tests the agents don't follow instructions embedded in untrusted
  document content), `deal_18_binary_garbage.txt` (random bytes saved with a
  `.txt` extension — tests the loader's `errors="ignore"` decode path),
  `deal_19_unsupported_filetype.xyz` (exercises `document_loader`'s
  extension check directly; the Streamlit uploader itself blocks this
  extension at the widget level, so it can only be hit by calling
  `load_document()` directly).
- Ran the full expanded set through the live graph (not just unit tests) to
  confirm nothing crashes and to record actual pipeline behavior; results
  folded into `data/sample_deals/ANSWER_KEY.md`.

### Fixed — real bug found via the extreme test tier: `max_tokens` truncation
The first version of `deal_16_extremely_long_document.txt` (144K chars) reliably
truncated the risk/compliance agents' structured-output JSON mid-response —
`ChatAnthropic`'s default output-token cap, not a schema problem, though it
surfaced as a `pydantic.ValidationError` that looked like one. The pipeline's
retry-once/`needs_manual_review` failure handling caught it as designed, but
each retry re-sent the full oversized prompt, wasting tokens.
- `app/config.py`: `get_llm()` now sets `max_tokens=4096` explicitly instead
  of relying on the client default.
- `deal_16` resized to ~18.8K chars — ~1/8th the token cost per run, still a
  real stress test, without the evidence-quote compounding that caused the
  truncation. Re-verified clean (0 errors, no retries) after both fixes.
See `data/sample_deals/ANSWER_KEY.md` for the full writeup of this bug.

## `7e0cdc7` — Fix ModuleNotFoundError on hosted deploys by fixing sys.path in-app
`run.sh`'s `PYTHONPATH` export only helped local launches — Streamlit
Community Cloud runs `streamlit run app/streamlit_app.py` directly with no
way to set an env var before launch, so it still hit
`ModuleNotFoundError: No module named 'app'` there. Fixed at the source:
`streamlit_app.py` now inserts the repo root into `sys.path` itself before
importing any `app.*` module, so it works regardless of how or where it's
launched. Verified locally with `PYTHONPATH` explicitly unset to match
hosted-deploy conditions.

## `d304b69` — Fix run.sh: set PYTHONPATH so streamlit run can import the app package
First pass at the same bug, scoped to local launches only:
`streamlit run app/streamlit_app.py` puts the script's own directory
(`app/`) on `sys.path`, not the repo root, so `from app.graph import
get_graph` failed. `run.sh` updated to launch with `PYTHONPATH="$PWD"`.
(Superseded in practice by `7e0cdc7`, which fixes it without depending on
the launch environment — kept as defense in depth.)

## `7c0e3e8` — Add project write-up draft (prompts, iterations, learnings)
Drafted `docs/PROJECT_WRITEUP.md` — the content for the handout's required
Google Doc deliverable: overview and one-liner, the three agent prompts
verbatim with the reasoning behind each instruction, a chronological build
log (framework-first design, the OpenAI→Anthropic switch, the `deal_id`
bug, the adversarial `deal_3` test document, the observability panel),
end-to-end validation results against the answer key, and learnings.

## `67d870b` — Wire Streamlit UI to Anthropic, add per-stage observability panel and architecture docs
- Switched LLM provider from OpenAI (`ChatOpenAI`) to Anthropic
  (`ChatAnthropic`, Claude) — `app/config.py`, `requirements.txt`,
  `.env.example`. Also dropped the explicit `temperature=0` param; the
  target Claude model rejects it.
- Fixed a `deal_id` bug: every node was using `state.file_path` as the
  trace/audit filename key and LangGraph `thread_id`, which silently breaks
  once `file_path` contains a slash (any real upload path). Added a
  dedicated, UUID-based `deal_id` field to `DealReviewState` instead.
- Added `stage_summary()` / `read_trace()` / `read_audit()` to
  `app/observability.py`, and wired a per-stage trace + audit panel into
  the Streamlit UI, shown after every run and after the human-review
  resume — not just the final report.
- Added `docs/ARCHITECTURE.md`: system diagram, pipeline graph,
  human-in-the-loop sequence diagram, state schema, agent responsibility
  table, and the failure-handling / observability design written out in
  detail.
- Fixed `run.sh`'s leftover `OPENAI_API_KEY` reference and widened
  `.gitignore`'s sqlite pattern to cover the `-shm`/`-wal` WAL sidecar
  files.

## `0c90524` — Scaffold multi-agent deal review pipeline (LangGraph + LangChain)
Initial build. `FRAMEWORK.md` (one-liner + full agent framework for Project
3B) drafted and confirmed before any code, per the handout's requirement.
Then:
- LangGraph pipeline: `load_document → extractor_agent → compliance_agent
  → risk_agent → orchestrator_compile → [human review interrupt] →
  finalize`, over a single `DealReviewState`.
- SQLite checkpointing (`SqliteSaver`) for resumable human-in-the-loop
  review.
- Observability: structured JSONL trace logs, a separate decision-relevant
  audit trail, rolling per-node metrics, optional LangSmith tracing via env
  vars.
- Failure handling: hard stop on unparseable documents (no LLM calls
  spent), one retry with a repair prompt on malformed structured LLM
  output, `"unclear"` (never an auto-guessed `"pass"`) compliance status,
  a `needs_manual_review` flag threaded through state on any partial
  failure.
- Streamlit UI: upload → run → draft report → sidebar metrics →
  approve/reject/edit review flow.
- 3 synthetic sample deals (clean baseline, 3-issue rate/date/termination
  violation, buried-arbitration reasoning trap) plus a hand-written
  `ANSWER_KEY.md` for accuracy validation.
- Unit tests for the document loader and the orchestrator's merge/error
  handling logic.
