"""
Does road travel time change who the Recovery Score recommends?

For a sample of same-day recovery cases with at least two eligible candidates,
compare the top recommendation using straight-line proximity (routing off)
against road ETA (CAREOPS_ROUTING_MODE=demo or live).

    CAREOPS_ROUTING_MODE=live OLA_MAPS_API_KEY=... python model/compare_routing.py --limit 30
    CAREOPS_ROUTING_MODE=demo python model/compare_routing.py

Each case makes at most one Distance Matrix request (routes are cached).
Demo mode is a formula check, not evidence about real roads: demo ETA is a
fixed function of straight-line distance, so any ranking change it shows comes
from scoring minutes instead of km, not from road geometry. Only a live run
answers the real question.
"""
import argparse
import datetime as dt
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import capacity_recovery  # noqa: E402
from routing import build_routing  # noqa: E402

# Most recent synthetic dates first, back through August.
DATES = [(dt.date(2026, 8, 29) - dt.timedelta(days=i)).isoformat() for i in range(29)]


def find_cases(limit):
    cases = []
    for day in DATES:
        ctx = capacity_recovery.build_candidates(day, routing=None)
        for appt_id in ctx["appts"][ctx["appts"]["date"] == day]["appointment_id"]:
            ranked = capacity_recovery.recommend(appt_id, day, ctx=ctx, top_n=5)
            if len(ranked) >= 2:
                cases.append((appt_id, day))
                if len(cases) >= limit:
                    return cases
    return cases


def compare(cases, routing):
    rows, contexts = [], {}
    for appt_id, day in cases:
        if day not in contexts:
            contexts[day] = (capacity_recovery.build_candidates(day, routing=None),
                             capacity_recovery.build_candidates(day, routing=routing))
        off_ctx, on_ctx = contexts[day]
        straight = capacity_recovery.recommend(appt_id, day, ctx=off_ctx, top_n=5)
        routed = capacity_recovery.recommend(appt_id, day, ctx=on_ctx, top_n=5)
        top_routed = routed[0]
        rows.append({
            "appointment_id": appt_id,
            "date": day,
            "candidates": len(straight),
            "top_straight_line": straight[0]["provider_id"],
            "top_road": top_routed["provider_id"],
            "changed": straight[0]["provider_id"] != top_routed["provider_id"],
            "top_road_eta_min": top_routed["road_eta_min"],
            "routes_found": sum(r["road_eta_min"] is not None for r in routed),
            "routing_status": on_ctx.get("routing_status"),
        })
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Straight-line vs road-ETA recommendations")
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args(argv)

    routing = build_routing()
    if routing is None:
        print("Set CAREOPS_ROUTING_MODE=demo or live (live also needs OLA_MAPS_API_KEY).")
        return 2

    cases = find_cases(args.limit)
    rows = compare(cases, routing)
    routed_rows = [r for r in rows if r["routes_found"] > 0]
    changed = [r for r in routed_rows if r["changed"]]
    etas = sorted(r["top_road_eta_min"] for r in routed_rows if r["top_road_eta_min"] is not None)

    summary = {
        "routing": routing.label,
        "mode": routing.mode,
        "run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "cases": len(rows),
        "cases_with_routes": len(routed_rows),
        "top_pick_changed": len(changed),
        "top_pick_changed_rate": round(len(changed) / len(routed_rows), 3) if routed_rows else None,
        "median_top_eta_min": etas[len(etas) // 2] if etas else None,
        "note": ("Demo ETA is a fixed function of straight-line distance; changes reflect the scoring "
                 "formula, not real roads.") if routing.mode == "simulated" else
                "Live Ola Maps standard ETA (not traffic-aware). Provider locations are inferred centroids.",
        "rows": rows,
    }
    print(f"{routing.label}: {len(routed_rows)}/{len(rows)} cases routed; "
          f"top pick changed in {len(changed)} ({summary['top_pick_changed_rate']}); "
          f"median top ETA {summary['median_top_eta_min']} min")
    for r in changed:
        print(f"  {r['appointment_id']} {r['date']}: {r['top_straight_line']} -> {r['top_road']} "
              f"({r['top_road_eta_min']} min)")
    if rows and rows[-1]["routing_status"] and rows[-1]["routing_status"]["status"] != "ok":
        print(f"  routing status: {rows[-1]['routing_status']}")

    out = os.path.join(BASE_DIR, "..", "data", "evaluation", f"routing_comparison_{routing.mode}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"wrote {os.path.relpath(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
