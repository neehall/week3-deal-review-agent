# Sample Deal Answer Key

Used to validate the pipeline's accuracy (target: ≥8/10 planted issues caught across
all three docs combined). Not read by the agents — reference only, for testing.

## deal_1_clean_loan.txt — baseline (should pass cleanly)
- R1 rate 9.5% → **pass**
- R2 effective date present (Jan 15, 2026) → **pass**
- R3 term 24mo > 12mo, has termination clause (Section 4) → **pass**
- R4 two parties named → **pass**
- R5 arbitration referenced AND disclosed as a clause (Section 5) → **pass**
- R6 amount stated ($250,000) → **pass**
- Expected: 0 issues flagged.

## deal_2_bad_rate.txt — 3 planted issues
- R1 rate 24.0% > 18% cap → **FAIL** (planted)
- R2 effective date explicitly omitted → **FAIL** (planted)
- R3 term 18mo > 12mo, no termination/cancellation clause anywhere → **FAIL** (planted)
- R4 two parties named → pass
- R5 no arbitration referenced → n/a / pass
- R6 amount stated ($500,000) → pass
- Expected: 3 issues flagged (R1, R2, R3).

## deal_3_hidden_arbitration.txt — 2-3 planted issues, 1 ambiguous edge case
- R1 no rate/price stated (services contract, rate card not attached) → n/a / pass
- R2 effective date present (March 1, 2026) → pass
- R3 term 36mo > 12mo; text uses "non-renewal" notice, not "termination"/"cancellation"
  — **ambiguous by design**: a naive keyword check fails this, an LLM reading for
  substance should recognize the non-renewal notice provision functions as an
  early-exit mechanism. Correct behavior: flag as `unclear` at minimum, ideally
  reasons through it. **This tests whether the compliance agent reasons over
  substance vs. pattern-matching a keyword.**
- R4 two parties named → pass
- R5 arbitration clause IS in the raw text (Section 3) — tests whether the
  Extractor correctly pulls it into `key_clauses` (it should) → **FAIL if the
  extractor misses it (planted trap)**, pass if extracted correctly
- R6 amount/pricing not stated, rate card "not attached to this excerpt" → **FAIL** (planted)
- Expected: 2 hard failures (R3-ish/unclear, R6), plus R5 is a check on extractor
  completeness rather than a document defect.

## Total planted issues to catch: ~5-6 across the 3 docs
Use this to compute a rough catch-rate when validating end to end.
