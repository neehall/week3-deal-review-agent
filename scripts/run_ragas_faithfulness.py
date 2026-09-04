"""Runs the pipeline + a ragas faithfulness check over the sample deals.

    PYTHONPATH=. python scripts/run_ragas_faithfulness.py           # 1 doc/tier, 4 total
    PYTHONPATH=. python scripts/run_ragas_faithfulness.py --all     # every sample deal

Cost note: each document costs the normal 3 agent LLM calls (as any run
does) plus one extra ragas judge call to score the resulting report's
faithfulness. Defaults to one representative document per tier (4 total,
skipping extreme/deal_16_extremely_long_document.txt and the
non-LLM-reaching extreme/deal_13_empty_file.txt-style failure cases,
which have no report to score anyway) rather than the full 20-document
set -- pass --all only when you specifically want full coverage; see
data/sample_deals/ANSWER_KEY.md's own cost note for why that set isn't
looped through wholesale by default.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.graph import get_graph
from app.ragas_eval import score_report_faithfulness
from app.state import DealReviewState

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DEALS_DIR = REPO_ROOT / "data" / "sample_deals"
RESULTS_PATH = SAMPLE_DEALS_DIR / "ragas_faithfulness_results.json"

DEFAULT_SAMPLE = [
    "normal/deal_1_clean_loan.txt",
    "failing/deal_2_bad_rate.txt",
    "edge_cases/deal_3_hidden_arbitration.txt",
    "extreme/deal_17_prompt_injection_attempt.txt",
]


def _all_deal_files() -> list[str]:
    files = sorted(SAMPLE_DEALS_DIR.glob("*/*"))
    return [str(f.relative_to(SAMPLE_DEALS_DIR)) for f in files if f.suffix in (".txt", ".xyz")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="Score every sample deal, not just the default 4.")
    args = parser.parse_args()

    relative_paths = _all_deal_files() if args.all else DEFAULT_SAMPLE
    graph = get_graph()
    results = []

    for rel_path in relative_paths:
        file_path = str(SAMPLE_DEALS_DIR / rel_path)
        deal_id = "ragasfaith-" + uuid.uuid4().hex[:8]
        config = {"configurable": {"thread_id": deal_id}}
        state = DealReviewState(file_path=file_path, deal_id=deal_id)

        print(f"Running {rel_path} ...", end=" ", flush=True)
        result = graph.invoke(state, config=config)
        draft_report = result["draft_report"] if isinstance(result, dict) else result.draft_report
        raw_text = result["raw_text"] if isinstance(result, dict) else result.raw_text

        if not draft_report:
            print("no report produced (load failed) -- skipping faithfulness check")
            continue

        score = score_report_faithfulness(deal_id, rel_path, raw_text, draft_report)
        results.append(score)
        print(f"faithfulness={score.faithfulness}")

    RESULTS_PATH.write_text(json.dumps([asdict(r) for r in results], indent=2))
    print(f"\nWrote {len(results)} results to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
