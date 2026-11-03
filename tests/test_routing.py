"""Road routing: demo is labelled simulated, live never fakes a route, Recovery Score uses ETA."""
import pytest

import capacity_recovery
import routing


class FakeResp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body

    def json(self):
        if self._body is None:
            raise ValueError
        return self._body


def test_build_routing_modes():
    assert routing.build_routing({}) is None
    assert routing.build_routing({"CAREOPS_ROUTING_MODE": "off"}) is None
    assert isinstance(routing.build_routing({"CAREOPS_ROUTING_MODE": "demo"}), routing.DemoRoutingProvider)
    unavailable = routing.build_routing({"CAREOPS_ROUTING_MODE": "live"})
    assert isinstance(unavailable, routing.UnavailableRoutingProvider)
    assert unavailable.matrix([(1, 1)], [(2, 2)]).status == "failed"
    with pytest.raises(ValueError):
        routing.build_routing({"CAREOPS_ROUTING_MODE": "fast"})


def test_demo_is_simulated_and_slower_at_peak():
    p = routing.DemoRoutingProvider()
    off_peak = p.matrix([(12.97, 77.59)], [(12.93, 77.62)], depart_hour=14).grid[0][0]
    peak = p.matrix([(12.97, 77.59)], [(12.93, 77.62)], depart_hour=9).grid[0][0]
    assert off_peak.mode == "simulated" and peak.duration_min > off_peak.duration_min


def test_ola_parses_metres_seconds_and_drops_implausible_elements():
    body = {"rows": [
        {"elements": [{"status": "OK", "distance": 6000, "duration": 900}]},
        {"elements": [{"status": "OK", "distance": 10, "duration": 900}]},  # far shorter than straight line
    ]}
    calls = []

    def get(url, params, timeout):
        calls.append(params)
        return FakeResp(200, body)

    p = routing.OlaMapsRoutingProvider("SECRET", get=get, sleep=lambda s: None)
    out = p.matrix([(12.97, 77.59), (12.95, 77.60)], [(12.93, 77.62)])
    assert out.status == "partial"
    good = out.grid[0][0]
    assert good.mode == "live" and good.distance_km == 6.0 and good.duration_min == 15.0
    assert out.grid[1][0] is None
    assert calls[0]["api_key"] == "SECRET" and calls[0]["origins"].count("|") == 1


def test_ola_auth_failure_is_not_retried_and_never_falls_back():
    calls = []

    def get(url, params, timeout):
        calls.append(1)
        return FakeResp(401, {})

    out = routing.OlaMapsRoutingProvider("bad", get=get, sleep=lambda s: None).matrix([(1, 1)], [(2, 2)])
    assert out.status == "failed" and "authentication" in out.error and len(calls) == 1
    assert out.grid == [[None]]


def _a_recoverable_case():
    """Find an appointment with at least two eligible candidates on its own date."""
    ctx = capacity_recovery.build_candidates("2026-08-29", routing=None)
    appts = ctx["appts"]
    for appt_id in appts[appts["date"] == "2026-08-29"]["appointment_id"]:
        ranked = capacity_recovery.recommend(appt_id, "2026-08-29", ctx=ctx, top_n=5)
        if ranked and all(r["distance_km"] is not None and not r["is_current_provider"] for r in ranked):
            return appt_id
    pytest.skip("no multi-candidate case in synthetic data")


def test_recovery_score_uses_road_eta_and_says_so():
    appt_id = _a_recoverable_case()
    ctx = capacity_recovery.build_candidates("2026-08-29", routing=routing.DemoRoutingProvider())
    ranked = capacity_recovery.recommend(appt_id, "2026-08-29", ctx=ctx, top_n=5)
    assert all(r["route_source"] == "simulated" and r["road_eta_min"] is not None for r in ranked)
    assert all(any("min by road (simulated)" in reason for reason in r["reasons"]) for r in ranked)
    # Routes are cached: a second call makes no new matrix request.
    cached = len(ctx["route_cache"])
    capacity_recovery.recommend(appt_id, "2026-08-29", ctx=ctx, top_n=5)
    assert len(ctx["route_cache"]) == cached


def test_failed_live_routing_keeps_straight_line_and_labels_it():
    appt_id = _a_recoverable_case()
    ctx = capacity_recovery.build_candidates("2026-08-29",
                                             routing=routing.UnavailableRoutingProvider("no key"))
    ranked = capacity_recovery.recommend(appt_id, "2026-08-29", ctx=ctx, top_n=5)
    assert all(r["route_source"] == "straight_line" and r["road_eta_min"] is None for r in ranked)
    assert ctx["routing_status"]["status"] == "failed"
    assert all(any("road route unavailable" in reason for reason in r["reasons"]) for r in ranked)


def test_routing_off_matches_previous_scores():
    appt_id = _a_recoverable_case()
    off = capacity_recovery.recommend(appt_id, "2026-08-29",
                                      ctx=capacity_recovery.build_candidates("2026-08-29", routing=None), top_n=5)
    assert all(r["route_source"] == "straight_line" for r in off)
    assert all(any("km from patient (inferred)" in reason for reason in r["reasons"]) for r in off)


def test_compare_routing_demo_runs(monkeypatch, tmp_path):
    import compare_routing
    cases = compare_routing.find_cases(3)
    assert cases
    rows = compare_routing.compare(cases, routing.DemoRoutingProvider())
    assert len(rows) == len(cases) and all(r["routes_found"] > 0 for r in rows)
    monkeypatch.delenv("CAREOPS_ROUTING_MODE", raising=False)
    assert compare_routing.main(["--limit", "1"]) == 2


def test_compare_routing_does_not_write_failed_runs(monkeypatch):
    import compare_routing
    monkeypatch.setenv("CAREOPS_ROUTING_MODE", "live")
    monkeypatch.delenv("OLA_MAPS_API_KEY", raising=False)
    writes = []
    monkeypatch.setattr(compare_routing.json, "dump", lambda *a, **k: writes.append(1))
    assert compare_routing.main(["--limit", "2"]) == 1
    assert writes == []
