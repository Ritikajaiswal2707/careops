"""Visit reports: the safety layer can only make a report more cautious, and fails closed."""
import json

import pytest
from fastapi.testclient import TestClient

import main
import visit_report
import visit_report_eval


class FakeResp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body

    def json(self):
        if self._body is None:
            raise ValueError
        return self._body


def _llm(report):
    return lambda *a, **k: FakeResp(200, {"choices": [{"message": {"content": json.dumps(report)}}]})


def _report(**vitals):
    base = {f: None for f in visit_report.VITAL_FIELDS}
    base.update(vitals)
    return {"vitals": base, "medications": [], "observations": [], "concerns": [],
            "family_summary": "The visit went smoothly today."}


def test_routine_note_releases_family_summary():
    out = visit_report.apply_safety("BP 126/80, oxygen 97.", _report(bp_systolic=126, bp_diastolic=80, spo2_pct=97))
    assert out["needs_coordinator_review"] is False and out["family_summary"]
    assert out["vitals"]["bp_systolic"] == 126 and out["unverified_vitals"] == {}


def test_invented_vital_is_moved_out_and_sent_to_review():
    out = visit_report.apply_safety("Bank gaye, chai pi.", _report(spo2_pct=98))
    assert out["vitals"]["spo2_pct"] is None and out["unverified_vitals"] == {"spo2_pct": 98.0}
    assert out["needs_coordinator_review"] is True and out["family_summary"] is None
    assert out["draft_family_summary"]  # kept for the coordinator, not released


@pytest.mark.parametrize("note,vitals", [
    ("Oxygen 89 tha.", {"spo2_pct": 89}),
    ("BP 186/104.", {"bp_systolic": 186, "bp_diastolic": 104}),
    ("Sugar 62.", {"blood_sugar_mg_dl": 62}),
    ("Temperature 103.", {"temperature_f": 103}),
])
def test_out_of_range_vitals_force_review(note, vitals):
    out = visit_report.apply_safety(note, _report(**vitals))
    assert out["needs_coordinator_review"] and out["red_flags"] and out["family_summary"] is None


@pytest.mark.parametrize("note", ["Papa bathroom mein gir gaye the.", "seene mein dard ho raha hai",
                                  "Saans lene mein dikkat ho rahi thi", "aaj thoda confused thi"])
def test_red_flag_words_force_review_even_if_model_says_nothing(note):
    out = visit_report.apply_safety(note, _report())
    assert out["needs_coordinator_review"] and any(f.startswith("keyword:") for f in out["red_flags"])


def test_unverified_out_of_range_value_still_escalates():
    # A dangerous value the note didn't state as digits is not released, but still escalates.
    out = visit_report.apply_safety("oxygen nawaasi aa raha tha", _report(spo2_pct=89))
    assert out["vitals"]["spo2_pct"] is None and "spo2_pct=89.0" in out["red_flags"]


def test_build_report_fails_closed_without_llm(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "CAREOPS_DISABLE_EXTERNAL_LLM"):
        monkeypatch.delenv(var, raising=False)
    out = visit_report.build_report("BP 120/80, gir gaye the")
    assert out["needs_coordinator_review"] and out["family_summary"] is None
    assert out["red_flags"] == ["keyword:gir gaye"]


def test_build_report_with_invalid_model_output_fails_closed(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.delenv("CAREOPS_DISABLE_EXTERNAL_LLM", raising=False)
    bad = lambda *a, **k: FakeResp(200, {"choices": [{"message": {"content": "sorry, here is a summary"}}]})
    out = visit_report.build_report("BP 120/80", post=bad)
    assert out["needs_coordinator_review"] and "invalid_json" in out["review_reasons"][0]
    good = visit_report.build_report("BP 120/80", post=_llm(_report(bp_systolic=120, bp_diastolic=80)))
    assert good["needs_coordinator_review"] is False and good["model"] == "m"


def test_transcribe_posts_audio_with_bearer_key(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_API_KEY", "SECRET")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    audio = tmp_path / "note.m4a"
    audio.write_bytes(b"fake audio")
    seen = {}

    def post(url, headers, files, data, timeout):
        seen.update(url=url, auth=headers["Authorization"], model=data["model"], name=files["file"][0])
        return FakeResp(200, {"text": " BP 120 by 80 "})

    text, err = visit_report.transcribe(str(audio), post=post)
    assert (text, err) == ("BP 120 by 80", None)
    assert seen["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert seen["auth"] == "Bearer SECRET" and seen["model"] == "whisper-large-v3" and seen["name"] == "note.m4a"
    assert visit_report.transcribe(str(audio), post=lambda *a, **k: FakeResp(401, {}))[1] == "transcription failed (HTTP 401)"


def test_eval_scoring_with_perfect_fake_model():
    cases = visit_report_eval.load_cases()
    it = iter(cases)

    def post(*a, **k):
        c = next(it)
        return _llm({"vitals": c["gold_vitals"], "medications": [], "observations": [], "concerns": [],
                     "family_summary": "The visit went smoothly today."})()

    out = visit_report_eval.run("k", "perfect", "https://x/v1", delay=0, post=post, sleep=lambda s: None)
    a = out["metrics"]["after_safety"]
    assert out["metrics"]["raw"]["invented_vitals"] == 0
    assert a["review_recall"] == 1.0 and a["missed_reviews"] == []
    assert a["wrong_values_released"] == 0 and a["released_summaries_with_unstated_numbers"] == []


def test_eval_suite_is_frozen():
    import hashlib
    suite = json.load(open(visit_report_eval.SUITE, encoding="utf-8"))
    digest = hashlib.sha256(json.dumps(suite["cases"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    assert digest == suite["sha256_of_cases"]


def test_api_visit_report_endpoints(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    client = TestClient(main.app)
    r = client.post("/api/visit-report", json={"transcript": "BP 120/80"})
    assert r.status_code == 200 and r.json()["needs_coordinator_review"] is True
    assert client.post("/api/visit-report", json={"transcript": "   "}).status_code == 422
    monkeypatch.setenv("CAREOPS_DISABLE_EXTERNAL_LLM", "true")
    r = client.post("/api/visit-report/audio", files={"file": ("n.m4a", b"x")})
    assert r.status_code == 503
    monkeypatch.setenv("CAREOPS_DISABLE_EXTERNAL_LLM", "false")
    assert client.post("/api/visit-report/audio", files={"file": ("n.exe", b"x")}).status_code == 422


def test_eval_does_not_write_a_run_where_every_call_failed(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_API_KEY", "placeholder")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setattr(visit_report_eval, "run", lambda *a, **k: {
        "n_cases": 30, "full_set": True, "errors": [],
        "metrics": {"n": 30, "json_valid": 0, "errors": 30,
                    "raw": {"vital_field_accuracy": 0.6, "invented_vitals": 0, "wrong_values": 0},
                    "after_safety": {"vital_field_accuracy": 0.6, "invented_vitals": 0,
                                     "wrong_values_released": 0, "review_recall": 1.0, "missed_reviews": [],
                                     "review_rate_on_routine": 1.0, "family_summaries_released": 0,
                                     "released_summaries_with_unstated_numbers": []}}})
    writes = []
    monkeypatch.setattr(visit_report_eval.json, "dump", lambda *a, **k: writes.append(1))
    assert visit_report_eval.main([]) == 1 and writes == []


@pytest.mark.parametrize("note,expected", [
    ("Sugar 62 tha, 15 min baad 88 aaya.", {"blood_sugar_mg_dl": [62.0, 88.0]}),
    ("BP 186/104, dobara 182/100.", {"bp_systolic": [186.0, 182.0], "bp_diastolic": [104.0, 100.0]}),
    ("Room number 120. BP 124/80.", {"bp_systolic": [124.0], "bp_diastolic": [80.0]}),
    ("Age 78 hai. Pulse 70, oxygen 98.", {"pulse_bpm": [70.0], "spo2_pct": [98.0]}),
    ("10 din ka course. Temperature 99.1.", {"temperature_f": [99.1]}),
])
def test_scan_readings_finds_every_reading_and_ignores_distractors(note, expected):
    assert visit_report.scan_readings(note) == expected


def test_earlier_low_reading_escalates_even_if_model_reports_the_later_one():
    note = "Sugar 62 tha, haath kaanp rahe the. Juice diya, 15 min baad 88 aaya."
    out = visit_report.apply_safety(note, _report(blood_sugar_mg_dl=88))
    assert out["needs_coordinator_review"] and out["family_summary"] is None
    assert "note mentions blood_sugar_mg_dl=62.0" in out["red_flags"]


def test_rescore_reapplies_current_safety_offline(tmp_path):
    case = next(c for c in visit_report_eval.load_cases() if c["id"] == "VR20")
    raw = {"vitals": {**{f: None for f in visit_report.VITAL_FIELDS}, "blood_sugar_mg_dl": 88},
           "family_summary": "All good today."}
    path = tmp_path / "run.json"
    path.write_text(json.dumps({"model": "m", "cases": [{"id": "VR20", "raw": raw}]}))
    out = visit_report_eval.rescore(str(path))
    a = out["metrics"]["after_safety"]
    assert out["recorded_safety_version"] == "1.0" and out["rescored_with_safety_version"] == visit_report.SAFETY_VERSION
    assert a["review_recall"] == 1.0 and a["wrong_or_invented_vitals_reaching_family"] == 0
