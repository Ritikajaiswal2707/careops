import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from communication_intelligence import extract_intent  # noqa: E402


def test_development_suite_classifications():
    suite = json.loads((ROOT / "data/evaluation/parser_development_v1.json").read_text())
    failures = []
    for case in suite["cases"]:
        actual = extract_intent(case["message"])["intent"]
        if actual != case["expected_intent"]:
            failures.append((case["id"], case["message"], case["expected_intent"], actual))
    assert not failures, failures


def test_uncertain_confirmation_is_not_confirmed():
    for message in ["I cannot confirm now", "I will confirm later", "not confirmed yet"]:
        assert extract_intent(message)["intent"] == "Unclear"


def test_compound_cancel_and_move_remains_reschedule_with_cancel_flag():
    result = extract_intent("Cancel today's slot and move it to Wednesday")
    assert result["intent"] == "Reschedule"
    assert result["cancel_current"] is True
