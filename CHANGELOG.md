# Changelog

All notable changes to this project, in the order they happened. Each entry
links the commit that made it; see `git log` for full diffs.

## [Unreleased]

### Changed — compliance rule/prompt fixes from Week 4's systematic evaluation
- `data/compliance/rules.yaml`, R1: previously silent on what to do when a
  deal type has no rate/price dimension at all (a lease charging flat
  rent, a flat-fee services contract) — the compliance agent
  inconsistently marked these `unclear` instead of `pass`. R1's
  description now explicitly distinguishes "no rate dimension exists"
  (pass) from "a rate might exist but isn't disclosed" (unclear), and
  adds guidance for a rate stated as a range (evaluate the upper bound
  against the cap, since that's what the agreement as written permits).
- `app/agents/prompts.py`, `COMPLIANCE_SYSTEM_PROMPT`: added rules 1a/1b,
  generalizing the not-applicable-vs-unclear distinction beyond R1, and
  explicitly separating "no rate named anywhere" (pass) from "a rate is
  named but not disclosed, e.g. deferred to an unattached exhibit"
  (still unclear).
- Found and fixed via a 34-case golden-dataset evaluation in the sibling
  Week 4 Project (not in this repo) — baseline vs. 3-fix comparison,
  `unclear_count_correct` +19.3pp, task completion 73.5% → 94.1%. One
  regression was also found and reported honestly rather than hidden: on
  `data/sample_deals/extreme/deal_18_binary_garbage.txt`, the fixes'
  "prefer unclear" language over-generalized, producing all-unclear
  findings instead of the intended mix of confident fails and unclears
  for a genuinely garbled document — flagged as an open follow-up, not
  yet fixed. Full analysis: see the Week 4 Project's
  `docs/failure_analysis.md` and `docs/phase4_improvement_report.md`.
- `data/sample_deals/ANSWER_KEY.md` was not updated to match — its
  per-file expected results describe this repo's pre-Week-4 behavior.
  Two entries in it were independently found to be mis-transcribed
  errors (not behavior drift) during the Week 4 evaluation: `deal_7`'s
  expected fail count, and `deal_15`'s expected fail/unclear split. See
  the Week 4 Project's `data/golden_dataset/cases.json` for the
  corrected, re-verified values.

### Added — ragas-based independent evaluation
- `app/ragas_eval.py`: scores the orchestrator's draft report for
  groundedness in the source document using the `ragas` framework's
  `Faithfulness` metric — not a RAG-specific check, since Faithfulness
  only needs a (response, context) pair, which maps directly onto this
  pipeline's own "never fabricate a value" guardrail. An independent,
  standardized cross-check layered on top of `ANSWER_KEY.md`'s hand-built
  validation (that checks compliance *correctness*; this checks
  *groundedness*).
- `scripts/run_ragas_faithfulness.py`: runs it over a cost-conscious
  4-document default sample (`--all` for the full set), writes
  `data/sample_deals/ragas_faithfulness_results.json`.
- Getting `ragas` to actually produce a score against this Claude model
  (rather than an exception) took 3 real fixes, each hit for real before
  being fixed: a `400 temperature is deprecated` error (ragas'
  `LangchainLLMWrapper` force-sets `.temperature`; fixed with
  `bypass_temperature=True`), then an `LLMDidNotFinishException` at
  `max_tokens=4096` and again at `8192` (adaptive thinking consuming the
  whole output budget on hidden reasoning; fixed with
  `thinking={"type": "disabled"}` on the `ChatAnthropic` client — the
  LangChain equivalent of the raw-SDK `output_config={"effort": "low"}`
  fix the Week 2 project already uses for the identical failure mode).
  Full detail in `app/ragas_eval.py`'s docstring.
- Real run against the 4-document sample scored 0.44–0.81 faithfulness —
  moderate, not uniformly high, and read honestly rather than smoothed
  over in `data/sample_deals/ANSWER_KEY.md`'s new ragas section: `ragas`'
  Faithfulness metric is built for RAG Q&A (where a good answer closely
  paraphrases retrieved text), and this pipeline's draft report is
  deliberately *not* a paraphrase — it's structured judgment output
  (verdicts, severity labels, a synthesized risk narrative), which its
  NLI-based claim checker scores more conservatively than literal
  entailment would. The useful signal is relative/diagnostic (a report
  that invents a term would score near 0), not a pass/fail threshold.

## `83efff1` — Expand sample deals to 4-tier test suite, fix max_tokens truncation bug

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

## `90f44b9` — Add module docstrings to test files for at-a-glance readability
`tests/test_document_loader.py` and `tests/test_orchestrator.py` got a
one-line module docstring each, matching the readability pass already
done everywhere else in the codebase.

## `6158c80` — Add datasets-used section and clarify deliverables checklist against handout
The handout requires a "datasets used" section in the project doc;
`docs/PROJECT_WRITEUP.md` mentioned the sample deals in passing but had no
dedicated section — added one. Also expanded the deliverables checklist to
distinguish supporting docs from the handout's 3 actually-required
deliverables (Google Doc, video, GitHub link) plus the form submission
itself, none of which were tracked as outstanding action items before.

## `1f923a8` — Add docs/CODE_MAP.md: file-by-file index of what each source file does
A table-form index, one row per source file, grouped by directory —
organized the same way as this changelog's own file-tier groupings.
Linked from the README alongside the other docs.

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
