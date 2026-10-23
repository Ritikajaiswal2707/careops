import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from compare_extraction_strategies import run_comparison  # noqa: E402


def test_strategy_comparison_uses_same_dataset_and_discloses_limits(tmp_path):
    output = tmp_path / "comparison.json"
    report = run_comparison(output)
    assert report["dataset"]["n"] == 103
    assert report["dataset"]["same_gold_set_for_all_strategies"] is True
    assert set(report["strategies"]) == {
        "rules_only", "saved_blind_llm_predictions", "rules_first_hybrid"
    }
    assert report["strategies"]["rules_only"]["cost_per_message_inr"] == 0.0
    assert report["strategies"]["saved_blind_llm_predictions"]["cost_per_message_inr"] is None
    assert report["strategies"]["saved_blind_llm_predictions"]["avg_latency_ms"] is None
    assert any("not a live API benchmark" in note for note in report["interpretation"])
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["error_counts"]["rules_only_intent_errors"] >= 0
