"""
Road routing for the Recovery Score (ported from the Smart Assign allocation engine).

RoutingProvider.matrix() returns road distance and duration for every
origin x destination pair. Modes, chosen with CAREOPS_ROUTING_MODE:

  off   (default) no routing: the Recovery Score keeps its straight-line
        proximity, so existing evaluations stay reproducible
  demo  deterministic simulated road ETA, always labelled "simulated"
  live  Ola Maps Distance Matrix (needs OLA_MAPS_API_KEY). Without a key,
        live mode fails loudly instead of silently falling back.

A pair that cannot be routed is None. Straight-line distance is never
returned as a road distance.
"""
from __future__ import annotations

import math
import os
import time as _time
from dataclasses import dataclass
from datetime import datetime, timezone

import requests


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class RouteResult:
    distance_km: float
    duration_min: float
    mode: str          # "live" | "simulated"
    source: str        # "ola_maps" | "demo"
    computed_at: str


@dataclass
class MatrixResult:
    grid: list
    status: str = "ok"  # ok | partial | failed
    error: str | None = None


def _stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _empty(o, d):
    return [[None] * len(d) for _ in o]


class DemoRoutingProvider:
    name, mode, label = "demo", "simulated", "Demo routing, not live traffic"
    CIRCUITY = 1.35  # road distance is longer than the crow flies

    def matrix(self, origins, destinations, depart_hour=None) -> MatrixResult:
        stamp = _stamp()
        peak = depart_hour is not None and (8 <= depart_hour < 11 or 17 <= depart_hour < 21)
        speed = 17.0 if peak else 24.0  # km/h, deterministic
        grid = []
        for o in origins:
            row = []
            for d in destinations:
                km = haversine_km(o[0], o[1], d[0], d[1]) * self.CIRCUITY
                row.append(RouteResult(km, km / speed * 60.0 + 3.0, "simulated", "demo", stamp))
            grid.append(row)
        return MatrixResult(grid)


class UnavailableRoutingProvider:
    name, mode, label = "ola_maps", "live", "Live routing is not configured"

    def __init__(self, reason):
        self.reason = reason

    def matrix(self, origins, destinations, depart_hour=None) -> MatrixResult:
        return MatrixResult(_empty(origins, destinations), "failed", self.reason)


class OlaMapsRoutingProvider:
    """Ola Maps Distance Matrix: GET {base}/routing/v1/distanceMatrix with
    origins/destinations as "lat,lng|lat,lng" and api_key as a query parameter.

    Response units are read as metres and seconds and sanity-checked against the
    straight line; an element failing the check is dropped, not trusted.
    ETAs are standard (not traffic-aware).
    """
    name, mode, label = "ola_maps", "live", "Live road routing (Ola Maps), standard ETA"

    def __init__(self, api_key, base_url="https://api.olamaps.io", timeout=10.0, retries=2,
                 max_elements=25, get=requests.get, sleep=_time.sleep):
        self.api_key, self.base_url = api_key, base_url.rstrip("/")
        self.timeout, self.retries, self.max_elements = timeout, retries, max_elements
        self._get_fn, self._sleep = get, sleep

    def _get(self, path, params):
        params = {**params, "api_key": self.api_key}
        last = "unknown error"
        for attempt in range(self.retries + 1):
            try:
                r = self._get_fn(f"{self.base_url}{path}", params=params, timeout=self.timeout)
            except requests.Timeout:
                last = "Ola Maps timed out"
            except requests.RequestException as e:
                last = f"Ola Maps request failed ({type(e).__name__})"
            else:
                if r.status_code in (401, 403):
                    return None, "Ola Maps rejected the API key (authentication failed)"
                if r.status_code == 429:
                    last = "Ola Maps rate limit reached"
                elif r.status_code >= 500:
                    last = f"Ola Maps server error ({r.status_code})"
                elif r.status_code >= 400:
                    return None, f"Ola Maps rejected the request ({r.status_code})"
                else:
                    try:
                        return r.json(), None
                    except ValueError:
                        return None, "Ola Maps returned a response that is not JSON"
            if attempt < self.retries:
                self._sleep(0.5 * (2 ** attempt))
        return None, last

    @staticmethod
    def _num(v):
        if isinstance(v, dict):
            v = v.get("value")
        return float(v) if isinstance(v, (int, float)) else None

    def _element(self, el, o, d, stamp):
        if not isinstance(el, dict):
            return None
        status = el.get("status")
        if status is not None and str(status).upper() not in ("OK", "SUCCESS"):
            return None
        metres, seconds = self._num(el.get("distance")), self._num(el.get("duration"))
        if metres is None or seconds is None or metres < 0 or seconds < 0:
            return None
        km, minutes = metres / 1000.0, seconds / 60.0
        line = haversine_km(o[0], o[1], d[0], d[1])
        if km + 0.3 < line * 0.9:  # a road route cannot be much shorter than the straight line
            return None
        if minutes > 0 and km / (minutes / 60.0) > 130:  # nor absurdly fast
            return None
        return RouteResult(km, minutes, "live", "ola_maps", stamp)

    def matrix(self, origins, destinations, depart_hour=None) -> MatrixResult:
        if not origins or not destinations:
            return MatrixResult([])
        grid = _empty(origins, destinations)
        per_call = max(1, self.max_elements // len(destinations))
        errors, stamp = [], _stamp()
        for start in range(0, len(origins), per_call):
            chunk = origins[start:start + per_call]
            data, err = self._get("/routing/v1/distanceMatrix", {
                "origins": "|".join(f"{a:.6f},{b:.6f}" for a, b in chunk),
                "destinations": "|".join(f"{a:.6f},{b:.6f}" for a, b in destinations),
            })
            if err or data is None:
                errors.append(err or "no data")
                if err and ("authentication" in err or "rate limit" in err):
                    break
                continue
            rows = data.get("rows") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                errors.append("Ola Maps response did not contain route rows")
                continue
            for i, row in enumerate(rows[:len(chunk)]):
                els = row.get("elements") if isinstance(row, dict) else None
                for j, el in enumerate((els or [])[:len(destinations)]):
                    grid[start + i][j] = self._element(el, chunk[i], destinations[j], stamp)
        got = sum(1 for r in grid for c in r if c is not None)
        if got == len(origins) * len(destinations):
            return MatrixResult(grid)
        if got == 0:
            return MatrixResult(grid, "failed", errors[0] if errors else "No routes could be calculated")
        return MatrixResult(grid, "partial", errors[0] if errors else "Some routes could not be calculated")


def build_routing(env=None):
    """Return a routing provider for CAREOPS_ROUTING_MODE, or None when routing is off."""
    env = os.environ if env is None else env
    mode = env.get("CAREOPS_ROUTING_MODE", "off").strip().lower()
    if mode in ("", "off"):
        return None
    if mode == "demo":
        return DemoRoutingProvider()
    if mode == "live":
        key = env.get("OLA_MAPS_API_KEY")
        if not key:
            return UnavailableRoutingProvider("CAREOPS_ROUTING_MODE is live but OLA_MAPS_API_KEY is not set")
        return OlaMapsRoutingProvider(key, env.get("OLA_MAPS_BASE_URL", "https://api.olamaps.io"))
    raise ValueError("CAREOPS_ROUTING_MODE must be off, demo or live")


# Departure hour used for each appointment time slot (affects demo peak-hour speed).
SLOT_HOUR = {"Morning": 9, "Afternoon": 14, "Evening": 18}
