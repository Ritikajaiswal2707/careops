"""Tests for the metered Gemini evaluation runner, using a fake HTTP client (no network, no key)."""
import json

import metered_llm_eval
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

    out = metered_llm_eval.run("SECRET-KEY-123", "fake-model", limit=4, delay=0, post=post)
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

    out = metered_llm_eval.run("k", "m", limit=2, delay=0, post=post)
    assert out["metrics"]["json_validity_rate"] == 0.0
    assert all(p["pred_intent"] == "PARSE_ERROR" for p in out["predictions"])
    assert out["metrics"]["input_tokens_total"] is None  # missing usage -> not reported, not invented


def test_rate_limit_is_retried(monkeypatch):
    monkeypatch.setattr(metered_llm_eval.time, "sleep", lambda s: None)
    responses = iter([FakeResp(429), FakeResp(429), _ok(_gold_as_pred(HELD_OUT_SET[0]))])
    out = metered_llm_eval.run("k", "m", limit=1, delay=0, post=lambda *a, **k: next(responses))
    assert out["metrics"]["errors"] == 0
    assert out["metrics"]["intent_accuracy"] == 1.0


def test_paid_estimate_only_from_supplied_prices(monkeypatch):
    for var in ("LLM_INPUT_USD_PER_M", "LLM_OUTPUT_USD_PER_M", "USD_INR"):
        monkeypatch.delenv(var, raising=False)
    assert metered_llm_eval._paid_estimate(1000, 1000, 10, True) is None
    monkeypatch.setenv("LLM_INPUT_USD_PER_M", "1")
    monkeypatch.setenv("LLM_OUTPUT_USD_PER_M", "2")
    monkeypatch.setenv("USD_INR", "100")
    # (1000*1 + 1000*2)/1e6 USD = 0.003 USD -> 0.3 INR over 10 messages
    assert metered_llm_eval._paid_estimate(1000, 1000, 10, True) == 0.03


def test_main_without_key_does_not_simulate(monkeypatch, capsys):
    for var in ("GEMINI_API_KEY", "LLM_API_KEY", "LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    assert metered_llm_eval.main([]) == 2
    assert metered_llm_eval.main(["--provider", "gemini"]) == 2
    assert "Nothing is simulated" in capsys.readouterr().out


def _openai_ok(pred, in_tok=40, out_tok=15):
    return FakeResp(200, {
        "choices": [{"message": {"content": json.dumps(pred)}}],
        "usage": {"prompt_tokens": in_tok, "completion_tokens": out_tok},
    })


def test_openai_compatible_provider_groq_style():
    calls = iter(HELD_OUT_SET[:3])
    seen = {}

    def post(url, headers, json, timeout):
        seen["url"], seen["auth"], seen["model"] = url, headers["Authorization"], json["model"]
        return _openai_ok(_gold_as_pred(next(calls)))

    out = metered_llm_eval.run("SECRET-KEY-123", "some-model", limit=3, delay=0, post=post,
                          provider="openai", base_url="https://api.groq.com/openai/v1")
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["auth"] == "Bearer SECRET-KEY-123" and seen["model"] == "some-model"
    assert out["metrics"]["intent_accuracy"] == 1.0
    assert out["metrics"]["input_tokens_total"] == 120


def test_openai_compat_config_presets(monkeypatch):
    import openai_compat_llm
    for var in ("LLM_BASE_URL", "LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    assert openai_compat_llm.config() is None
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("LLM_MODEL", "m")
    assert openai_compat_llm.config() == ("https://openrouter.ai/api/v1", "x", "m")


def test_runtime_call_returns_none_without_config(monkeypatch):
    import openai_compat_llm
    for var in ("LLM_BASE_URL", "LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    assert openai_compat_llm.openai_compat_llm_call("kal aa jaungi") is None


def test_v2_prompt_is_sent_and_contains_no_eval_messages():
    from llm_prompt import PROMPTS
    seen = {}

    def post(url, headers, json, timeout):
        seen["system"] = json["messages"][0]["content"]
        return _openai_ok(_gold_as_pred(HELD_OUT_SET[0]))

    metered_llm_eval.run("k", "m", limit=1, delay=0, post=post, provider="openai",
                         base_url="https://x/v1", prompt="v2")
    assert seen["system"] == PROMPTS["v2"] and "No Response: ONLY" in seen["system"]
    holdout = metered_llm_eval.load_suite("holdout")
    for case in HELD_OUT_SET + holdout:
        msg = (case["message"] or "").strip()
        if len(msg) > 12:  # longer than generic one-word acks
            assert msg not in PROMPTS["v2"], f"eval message leaked into prompt: {msg}"


def test_holdout_suite_scores_intent_and_safety():
    holdout = metered_llm_eval.load_suite("holdout")
    assert len(holdout) == 30
    # Fake model that always says Confirm: every non-Confirm case is a false confirmation.
    out = metered_llm_eval.run("k", "m", delay=0, provider="openai", base_url="https://x/v1",
                               suite="holdout",
                               post=lambda *a, **k: _openai_ok({"intent": "Confirm"}))
    m = out["metrics"]
    expected_false = sum(1 for c in holdout if c["intent"] != "Confirm")
    assert out["full_set"] and out["suite"] == "holdout"
    assert m["false_confirmations"] == expected_false and m["false_cancellations"] == 0
    assert m["temporal_extraction_accuracy"] is None


def test_real_message_marked_no_response_is_counted():
    out = metered_llm_eval.run("k", "m", limit=4, delay=0, provider="openai", base_url="https://x/v1",
                               post=lambda *a, **k: _openai_ok({"intent": "No Response"}))
    assert out["metrics"]["real_message_marked_no_response"] == 4


def test_v3_changes_only_confirm_definition_and_has_no_eval_leak():
    from llm_prompt import PROMPTS
    assert "thank-you on its own does NOT confirm" in PROMPTS["v3"]
    assert "Short acknowledgements count" not in PROMPTS["v3"]
    assert PROMPTS["v3"].split("- Reschedule:")[1] == PROMPTS["v2"].split("- Reschedule:")[1]
    for suite in ("holdout", "holdout2"):
        for case in metered_llm_eval.load_suite(suite):
            msg = (case["message"] or "").strip()
            if len(msg) > 12:
                assert msg not in PROMPTS["v3"]


def test_holdout2_is_frozen_and_disjoint_from_other_sets():
    import hashlib, json as _json, os
    path = metered_llm_eval.HOLDOUT_PATHS["holdout2"]
    suite = _json.load(open(path, encoding="utf-8"))
    digest = hashlib.sha256(_json.dumps(suite["cases"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    assert digest == suite["sha256_of_cases"], "holdout2 cases were edited after freezing"
    h2 = {c["message"].strip().lower() for c in suite["cases"] if c["message"].strip()}
    others = {(c["message"] or "").strip().lower() for c in HELD_OUT_SET}
    others |= {c["message"].strip().lower() for c in metered_llm_eval.load_suite("holdout")}
    assert not (h2 & others)
