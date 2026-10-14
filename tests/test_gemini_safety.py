"""Regression tests for safe Gemini API-key handling and failure behaviour."""
import json

import requests

import gemini_llm


def _valid_prediction():
    return {
        "intent": "Reschedule",
        "cancel_current": False,
        "preferred_day": None,
        "next_week": False,
        "relative_day": "tomorrow",
        "offset_days": None,
        "reason": None,
    }


def test_gemini_key_is_sent_in_header_not_url(monkeypatch):
    secret = "test-secret-not-a-real-key"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(_valid_prediction())}]}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(gemini_llm.requests, "post", fake_post)
    result = gemini_llm.gemini_llm_call("Could we reschedule for tomorrow?")

    assert result == _valid_prediction()
    assert secret not in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == secret
    assert "params" not in captured


def test_gemini_provider_failure_returns_none_and_does_not_log_key(monkeypatch, caplog):
    secret = "test-secret-not-a-real-key"
    monkeypatch.setenv("GEMINI_API_KEY", secret)

    def fake_post(*args, **kwargs):
        raise requests.Timeout(f"failure including {secret}")

    monkeypatch.setattr(gemini_llm.requests, "post", fake_post)
    assert gemini_llm.gemini_llm_call("reschedule") is None
    assert secret not in caplog.text
    assert "Timeout" in caplog.text


def test_missing_optional_anthropic_sdk_escalates_without_exposing_key(monkeypatch, capsys):
    import sys
    import hybrid_extraction

    secret = "test-anthropic-secret-not-a-real-key"
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-secret-not-a-real-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    monkeypatch.setattr(gemini_llm, "gemini_llm_call", lambda message: None)
    monkeypatch.setitem(sys.modules, "anthropic", None)

    assert hybrid_extraction.default_llm_call("ambiguous request") is None
    logged = capsys.readouterr().out
    assert "ModuleNotFoundError" in logged
    assert secret not in logged
    assert "test-gemini-secret-not-a-real-key" not in logged
