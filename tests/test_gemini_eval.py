"""Tests for the metered Gemini evaluation runner, using a fake HTTP client (no network, no key)."""
import json

import gemini_eval
from llm_vs_baseline_eval import HELD_OUT_SET


class FakeResp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


def _ok(pred, in_tok=50, out_tok=20, fenced=False):
    text = json.dumps(pred)
    if fenced:
        text = f"```json\n{text}\n```"
    return FakeResp(200, {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": in_tok, "candidatesTokenCount": out_tok},
    })


def _gold_as_pred(case):
    return {k: case[k] for k in ("intent", "cancel_current", "preferred_day", "next_week",
                                  "relative_day", "offset_days", "reason")}


def test_perfect_fake_model_scores_100_and_counts_tokens():
    calls = iter(HELD_OUT_SET[:4])

    def post(url, headers, json, timeout):
        assert headers["x-goog-api-key"] == "SECRET-KEY-123"
        assert "SECRET-KEY-123" not in url  # key never in the URL
        return _ok(_gold_as_pred(next(calls)), fenced=True)

    out = gemini_eval.run("SECRET-KEY-123", "fake-model", limit=4, delay=0, post=post)
    m = out["metrics"]
    assert out["model"] == "fake-model" and out["n_cases"] == 4 and not out["full_set"]
    assert m["intent_accuracy"] == 1.0 and m["json_validity_rate"] == 1.0
    assert m["cancel_current_accuracy"] == 1.0
    assert m["input_tokens_total"] == 200 and m["output_tokens_total"] == 80
    assert m["actual_spend_inr"] == 0.0
    assert out["misclassified"] == []


def test_invalid_json_is_scored_as_error_not_guessed():
    def post(url, headers, json, timeout):
        return FakeResp(200, {"candidates": [{"content": {"parts": [{"text": "sure! it's a reschedule"}]}}]})

    out = gemini_eval.run("k", "m", limit=2, delay=0, post=post)
    assert out["metrics"]["json_validity_rate"] == 0.0
    assert all(p["pred_intent"] == "PARSE_ERROR" for p in out["predictions"])
    assert out["metrics"]["input_tokens_total"] is None  # missing usage -> not reported, not invented


def test_rate_limit_is_retried(monkeypatch):
    monkeypatch.setattr(gemini_eval.time, "sleep", lambda s: None)
    responses = iter([FakeResp(429), FakeResp(429), _ok(_gold_as_pred(HELD_OUT_SET[0]))])
    out = gemini_eval.run("k", "m", limit=1, delay=0, post=lambda *a, **k: next(responses))
    assert out["metrics"]["errors"] == 0
    assert out["metrics"]["intent_accuracy"] == 1.0


def test_paid_estimate_only_from_supplied_prices(monkeypatch):
    for var in ("GEMINI_INPUT_USD_PER_M", "GEMINI_OUTPUT_USD_PER_M", "USD_INR"):
        monkeypatch.delenv(var, raising=False)
    assert gemini_eval._paid_estimate(1000, 1000, 10, True) is None
    monkeypatch.setenv("GEMINI_INPUT_USD_PER_M", "1")
    monkeypatch.setenv("GEMINI_OUTPUT_USD_PER_M", "2")
    monkeypatch.setenv("USD_INR", "100")
    # (1000*1 + 1000*2)/1e6 USD = 0.003 USD -> 0.3 INR over 10 messages
    assert gemini_eval._paid_estimate(1000, 1000, 10, True) == 0.03


def test_main_without_key_does_not_simulate(monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert gemini_eval.main([]) == 2
    assert "Nothing is simulated" in capsys.readouterr().out
